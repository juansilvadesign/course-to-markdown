"""Groq Whisper speech-to-text client (OpenAI-compatible /audio/transcriptions).

An alternative Stage-1 transcription backend to Gemini. Groq's ``whisper-large-v3-turbo``
is a purpose-built STT model: cheaper per hour of audio than an LLM, faster, and free of
the LLM failure modes this pipeline had to engineer around on Gemini (the 64k output-token
ceiling and the long-audio phrase-repetition loops). Audio is POSTed directly as multipart
form-data — no Files API, no upload/poll/delete dance.

Selected with ``--provider groq``; Gemini stays the default. Stage 2 (compilation) is
unaffected — that remains the Claude subscription, never an API.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

from . import config

GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# A 429 whose reset is longer than this (from the `retry-after` header, when the body
# doesn't name the window) is treated as a stop-the-batch cap, not something to sleep
# through mid-run: per-minute limits reset well under this; per-hour/day don't.
STOP_IF_RETRY_AFTER_OVER_SEC = 300.0


class DailyQuotaExhausted(RuntimeError):
    """A Groq rate limit that won't clear within this run — the per-DAY cap (RPD/ASD) or a
    long per-HOUR audio cap (ASH). Mirrors ``gemini_client.DailyQuotaExhausted``: the batch
    stops cleanly and resumes on the next run (finished transcripts are skipped) instead of
    erroring every remaining file until the window resets. For our model the binding cap is
    audio-seconds/day (~8 h on the free tier) — see `knowledge/sources/groq-rate-limits.md`."""


# Full language name -> ISO-639-1 for the optional hint Whisper accepts (improves
# accuracy + latency). Unknown names fall through to auto-detect (hint omitted).
_LANG_CODES = {
    "portuguese": "pt", "english": "en", "spanish": "es", "french": "fr",
    "german": "de", "italian": "it", "dutch": "nl", "japanese": "ja",
    "chinese": "zh", "korean": "ko", "russian": "ru",
}

# httpx infers most of these, but m4a/mp3 are worth pinning explicitly.
_CONTENT_TYPES = {
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav",
    ".flac": "audio/flac", ".ogg": "audio/ogg", ".opus": "audio/ogg",
    ".webm": "audio/webm", ".aac": "audio/aac",
}


def _lang_code(language: str | None) -> str | None:
    if not language:
        return None
    l = language.strip().lower()
    if l in _LANG_CODES:
        return _LANG_CODES[l]
    if len(l) == 2 and l.isalpha():  # already an ISO-639-1 code
        return l
    return None


def _content_type(path: Path) -> str:
    return _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _rate_limit_stops_run(resp) -> bool:
    """True if a 429 is a per-hour/day cap that won't clear during this run (→ stop the
    batch); False for a transient per-minute/second limit (→ back off and retry).

    Groq's 429 body names the window, e.g. ``... requests per day (RPD): Limit 2000 ...``
    or ``... audio seconds per hour (ASH): ...``. Stop on day/hour, retry on minute/second;
    when the body is unparseable, fall back to the ``retry-after`` magnitude."""
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


def transcribe_file(audio_path: Path, model: str, language: str | None, api_key: str,
                    *, max_attempts: int = 4, max_sleep: float = 60.0) -> str:
    """Transcribe one (already-normalized, already-chunked) audio file via Groq.

    Retries transient 429/5xx and network errors (honoring ``Retry-After``); raises
    RuntimeError on persistent or non-retryable failure so the batch records a per-file
    error and keeps going (a re-run skips transcripts that already exist on disk).
    """
    timeout = httpx.Timeout(config.REQUEST_TIMEOUT_MS / 1000.0)
    code = _lang_code(language)
    attempt = 0
    while True:
        try:
            with audio_path.open("rb") as fh:
                files = {"file": (audio_path.name, fh, _content_type(audio_path))}
                data = {"model": model, "response_format": "json", "temperature": "0"}
                if code:
                    data["language"] = code
                resp = httpx.post(
                    GROQ_TRANSCRIBE_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files=files, data=data, timeout=timeout,
                )
            if resp.status_code == 200:
                return (resp.json().get("text") or "").strip()
            # A per-day (RPD/ASD) or long per-hour (ASH) cap won't clear this run — stop the
            # batch cleanly (resumable) rather than erroring every remaining file in turn.
            if resp.status_code == 429 and _rate_limit_stops_run(resp):
                raise DailyQuotaExhausted(
                    f"Groq rate limit won't clear within this run "
                    f"(retry-after={resp.headers.get('retry-after') or '?'}s): {resp.text[:200]}")
            # Transient (per-minute 429 / 5xx) — back off and retry.
            if resp.status_code in (429, 500, 502, 503, 504):
                attempt += 1
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"Groq transcription failed after {attempt} attempts: "
                        f"HTTP {resp.status_code} {resp.text[:200]}")
                retry_after = resp.headers.get("retry-after")
                sleep_s = min(float(retry_after) if retry_after else 2.0 * attempt, max_sleep)
                print(f"  ! groq: HTTP {resp.status_code}; retry {attempt}/{max_attempts} "
                      f"in {sleep_s:.0f}s", file=sys.stderr)
                time.sleep(sleep_s)
                continue
            # Non-retryable (401/403/413/422…): fail fast with the body for diagnosis.
            raise RuntimeError(
                f"Groq transcription error: HTTP {resp.status_code} {resp.text[:300]}")
        except httpx.RequestError as e:
            attempt += 1
            if attempt >= max_attempts:
                raise RuntimeError(
                    f"Groq request error after {attempt} attempts: {e}") from e
            sleep_s = min(2.0 * attempt, max_sleep)
            print(f"  ! groq: {e.__class__.__name__}; retry {attempt}/{max_attempts} "
                  f"in {sleep_s:.0f}s", file=sys.stderr)
            time.sleep(sleep_s)
