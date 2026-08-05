"""OpenRouter audio client (OpenAI-compatible /chat/completions with inline audio).

A third Stage-1 transcription backend alongside Gemini and Groq. OpenRouter has **no
speech-to-text endpoint** — audio rides inside a normal chat completion as a base64
``input_audio`` content part — so every model here is *an LLM transcribing*, which
re-introduces the two failure modes this pipeline was hardened against (the output-token
ceiling and phrase-repetition loops). The reason to accept that trade is
``xiaomi/mimo-v2.5``: a 131k output ceiling (2x Gemini's 65,535) at roughly $0.014 per
hour of audio, which repaired a lesson Gemini could not transcribe at any chunk size.

⚠️ FIDELITY CAVEAT — read before using this on a code-dense course. MiMo mis-renders
English technical vocabulary embedded in Portuguese speech, and unlike Groq's Whisper
(which garbles words into obvious nonsense, ``any`` -> "N") **its errors are fluent**: on
a TypeScript lesson it wrote the type ``unknown`` as ``any`` in 7/7 occurrences, producing
grammatical, plausible, semantically inverted text that passes every automated guard here
-- loop detection, finish reason, word count, diacritics. See ``scripts/jargon_audit.py``
for the check that does catch it.

Selected with ``--provider openrouter``. Stage 2 (compilation) is unaffected — that
remains the Claude subscription, never an API.
"""
from __future__ import annotations

import base64
import sys
import time
from pathlib import Path

import httpx

from . import audio, config

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

# A 429 whose reset is longer than this (from the `retry-after` header, when the body
# doesn't name the window) is treated as a stop-the-batch cap, not something to sleep
# through mid-run: per-minute limits reset well under this; per-hour/day don't.
STOP_IF_RETRY_AFTER_OVER_SEC = 300.0

# Real lecture narration runs ~150-200 words/min. A transcript far under this means the
# model answered from the text prompt alone without ever receiving the audio — a silent
# HTTP-200 failure seen live on nvidia/nemotron-*-omni:free, whose provider accepts the
# request, drops the audio part, and replies "please send the audio file".
MIN_WORDS_PER_MIN = 30.0

# ...but the ratio is meaningless on a very short segment, and `ffmpeg -f segment` emits a
# sliver whenever a lesson runs just past a multiple of the chunk length. A 1622s lesson at
# 540s leaves a 2.0s tail; the model returned the single word actually spoken there and the
# floor read 28.2 wpm, failing the whole 27-minute lesson (dynamodb-single-table lesson 10,
# 2026-08-04). The guard has no power down here anyway: the silent-drop apology it exists to
# catch is ~8 words, which on a 2s chunk scores 240 wpm and sails through. Below this
# duration, trust the chunk.
MIN_DURATION_FOR_WPM_SEC = 30.0

# OpenRouter accepts a `format` hint next to the base64 payload. Stage 1 always hands us
# a normalized mono MP3, so mp3 is both the default and the overwhelmingly common case.
_AUDIO_FORMATS = {".mp3": "mp3", ".wav": "wav"}


class DailyQuotaExhausted(RuntimeError):
    """An OpenRouter limit that won't clear within this run — an exhausted credit balance
    (402) or a per-day/hour rate cap. Mirrors ``gemini_client.DailyQuotaExhausted`` and
    ``groq_client.DailyQuotaExhausted``: the batch stops cleanly and resumes on the next
    run (finished transcripts are skipped) instead of erroring every remaining file.

    402 is the common one and it is NOT only about running out mid-run: OpenRouter gates
    *all* audio requests behind a minimum balance (~$0.50), and that gate applies even to
    ``:free`` models and to a 15-second clip."""


class AudioNotReceived(RuntimeError):
    """The provider returned a successful completion that cannot be a real transcript of
    the submitted audio. Raised so the batch records a per-file error rather than writing
    a confident-looking stub over a valid lesson."""


class TruncatedGeneration(RuntimeError):
    """The generation stopped for any reason other than a natural end.

    In practice this is the repetition loop: the model falls into an 8-word cycle (seen
    repeated 7,600x) and runs to the output ceiling. Measured at roughly 1-in-6 on
    *byte-identical* requests at temperature 0, so it is stochastic, not a property of the
    audio -- retrying the same request is the fix, and shrinking the chunk is not
    (300s chunks looped exactly as 540s ones did)."""


def _audio_format(path: Path) -> str:
    return _AUDIO_FORMATS.get(path.suffix.lower(), "mp3")


def _rate_limit_stops_run(resp) -> bool:
    """True if a 429 is a per-hour/day cap that won't clear during this run (→ stop the
    batch); False for a transient per-minute/second limit (→ back off and retry)."""
    text = (resp.text or "").lower()
    if "per day" in text or "per hour" in text:
        return True
    if "per minute" in text or "per second" in text:
        return False
    retry_after = resp.headers.get("retry-after")
    try:
        return retry_after is not None and float(retry_after) > STOP_IF_RETRY_AFTER_OVER_SEC
    except ValueError:
        return False


def _extract_text(payload: dict, model: str) -> str:
    """Pull the transcript out of a 200 response, rejecting the shapes that aren't one.

    A provider can return HTTP 200 carrying an error-shaped body with no ``choices`` at
    all; indexing that blindly kills the whole batch mid-run.
    """
    choices = payload.get("choices") or []
    if not choices:
        err = (payload.get("error") or {}).get("message") or str(payload)[:200]
        raise RuntimeError(f"OpenRouter returned 200 with no choices ({model}): {err}")

    choice = choices[0]
    finish = choice.get("finish_reason")
    text = ((choice.get("message") or {}).get("content") or "").strip()

    # Mirrors the Gemini guard: a truncated generation is never a valid transcript. The
    # whole point of MiMo's 131k ceiling is that this should not fire.
    if finish not in ("stop", "STOP", None, ""):
        raise TruncatedGeneration(
            f"OpenRouter finish_reason={finish!r} ({model}) — truncated or filtered "
            f"generation, not a complete transcript ({len(text.split())} words)")
    return text


def transcribe_file(audio_path: Path, model: str, language: str | None, api_key: str,
                    *, max_attempts: int = 4, max_sleep: float = 60.0) -> str:
    """Transcribe one (already-normalized, already-chunked) audio file via OpenRouter.

    Retries transient 429/5xx, network errors (honoring ``Retry-After``), and the
    silent audio-drop described in ``_assert_audio_was_received``; raises RuntimeError on
    persistent or non-retryable failure so the batch records a per-file error and keeps
    going (a re-run skips transcripts that already exist on disk).
    """
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Create one at https://openrouter.ai/keys "
            "and add it to .env.")

    from . import prompts  # local import: prompts pulls the knowledge-compiler reference

    timeout = httpx.Timeout(config.REQUEST_TIMEOUT_MS / 1000.0)
    b64 = base64.b64encode(audio_path.read_bytes()).decode()
    body = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompts.transcription_prompt(language)},
                {"type": "input_audio",
                 "input_audio": {"data": b64, "format": _audio_format(audio_path)}},
            ],
        }],
        "temperature": 0,
        "max_tokens": config.OPENROUTER_MAX_OUTPUT_TOKENS,
        # Transcription needs no chain-of-thought, and reasoning tokens are billed whether
        # or not any transcript comes back. Leaving this on produced finish_reason="length"
        # with zero content on 22 lessons. `exclude` would still generate (and bill) it.
        "reasoning": {"enabled": False},
        # Mistral/Voxtral rejects temperature=0 unless top_p is explicitly 1
        # ("top_p must be 1 when using greedy sampling", code 3054). top_p=1 is the
        # neutral default everywhere else, so this is safe to send to every model.
        "top_p": 1,
        "usage": {"include": True},
    }
    if config.OPENROUTER_PROVIDERS:
        # Hard pin, no fallbacks: see config.OPENROUTER_PROVIDERS for the measured
        # cost/quality gap between backends serving this same model.
        body["provider"] = {"only": config.OPENROUTER_PROVIDERS, "allow_fallbacks": False}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": "course-to-markdown",
    }

    attempt = 0
    while True:
        try:
            resp = httpx.post(OPENROUTER_CHAT_URL, json=body, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                try:
                    text = _extract_text(resp.json(), model)
                    _assert_audio_was_received(text, audio_path, model)
                except (AudioNotReceived, TruncatedGeneration) as flaw:
                    # Two distinct HTTP-200 failures, both *stochastic per request* rather
                    # than properties of the file, and both measured on jstack-lives:
                    #   ~7%  the provider silently drops the audio and apologises fluently
                    #   ~17% the model falls into a repetition loop and runs to the ceiling
                    # Byte-identical requests at temperature 0 succeed on retry, so retrying
                    # is the whole fix. Without it each batch leaves residue needing a pass.
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    sleep_s = min(2.0 * attempt, max_sleep)
                    reason = ("provider dropped the audio"
                              if isinstance(flaw, AudioNotReceived) else "generation looped")
                    print(f"  ! openrouter: {reason}; retry "
                          f"{attempt}/{max_attempts} in {sleep_s:.0f}s", file=sys.stderr)
                    time.sleep(sleep_s)
                    continue
                return text
            # An exhausted (or never-funded) balance won't clear this run — stop the batch
            # cleanly rather than erroring every remaining file in turn.
            if resp.status_code == 402:
                raise DailyQuotaExhausted(
                    f"OpenRouter credit limit ({model}): {resp.text[:300]}")
            if resp.status_code == 429 and _rate_limit_stops_run(resp):
                raise DailyQuotaExhausted(
                    f"OpenRouter rate limit won't clear within this run "
                    f"(retry-after={resp.headers.get('retry-after') or '?'}s): {resp.text[:200]}")
            if resp.status_code in (429, 500, 502, 503, 504):
                attempt += 1
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"OpenRouter transcription failed after {attempt} attempts: "
                        f"HTTP {resp.status_code} {resp.text[:200]}")
                retry_after = resp.headers.get("retry-after")
                sleep_s = min(float(retry_after) if retry_after else 2.0 * attempt, max_sleep)
                print(f"  ! openrouter: HTTP {resp.status_code}; retry {attempt}/{max_attempts} "
                      f"in {sleep_s:.0f}s", file=sys.stderr)
                time.sleep(sleep_s)
                continue
            # Non-retryable (400/401/403/413/422…): fail fast with the body for diagnosis.
            raise RuntimeError(
                f"OpenRouter transcription error: HTTP {resp.status_code} {resp.text[:300]}")
        except httpx.RequestError as e:
            attempt += 1
            if attempt >= max_attempts:
                raise RuntimeError(
                    f"OpenRouter request error after {attempt} attempts: {e}") from e
            sleep_s = min(2.0 * attempt, max_sleep)
            print(f"  ! openrouter: {e.__class__.__name__}; retry {attempt}/{max_attempts} "
                  f"in {sleep_s:.0f}s", file=sys.stderr)
            time.sleep(sleep_s)


def _assert_audio_was_received(text: str, audio_path: Path, model: str) -> None:
    """Reject a fluent 200 that cannot be a transcript of this audio.

    Catches the silent-drop class: the request succeeds, ``finish_reason`` is ``stop``,
    and the model politely explains it has no audio. Without this the batch writes that
    apology to disk as a finished lesson.
    """
    duration = audio.probe_duration(audio_path)
    if not duration or duration <= 0:
        return
    if duration < MIN_DURATION_FOR_WPM_SEC:
        return
    wpm = len(text.split()) / (duration / 60.0)
    if wpm < MIN_WORDS_PER_MIN:
        raise AudioNotReceived(
            f"{model} returned {len(text.split())} words for {duration/60:.1f} min of audio "
            f"({wpm:.1f} wpm, floor {MIN_WORDS_PER_MIN:.0f}) — the provider almost certainly "
            f"did not receive the audio. First 120 chars: {text[:120]!r}")
