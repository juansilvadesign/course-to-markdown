"""Orchestration: per-file pipeline and recursive batch runner.

Default output is the verbatim transcript (`.transcript.txt`), which is handed off to
the knowledge-compiler Claude agent for compilation. Letting Gemini also write a `.md`
note is opt-in via `gemini_format` (the legacy single-provider path).
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import (audio, config, formatter, gemini_client, groq_client,
               openrouter_client, transcribe)


REPETITION_NGRAM_WORDS = 8
MAX_REPEATED_NGRAM = 50


def max_repeated_ngram(text: str, size: int = REPETITION_NGRAM_WORDS) -> int:
    """Return the highest frequency of one exact word n-gram in a transcript."""
    words = re.findall(r"\w+", text.casefold())
    if size < 1 or len(words) < size:
        return 0
    counts = Counter(
        tuple(words[index : index + size])
        for index in range(len(words) - size + 1)
    )
    return max(counts.values(), default=0)


def _transcribe_one(client, path: Path, opts: Options) -> str:
    """Transcribe a single (already-normalized, already-chunked) audio file with the
    selected provider."""
    if opts.provider == "openrouter":
        return openrouter_client.transcribe_file(
            path, opts.model, opts.language, config.get_openrouter_api_key())
    if opts.provider == "groq":
        return groq_client.transcribe_file(
            path, opts.model, opts.language, config.get_groq_api_key())
    # Gemini via the Files API (upload -> generate -> delete).
    uploaded = gemini_client.upload_and_wait(client, path)
    try:
        return transcribe.transcribe(
            client, uploaded, opts.model, opts.thinking_budget, opts.language)
    finally:
        gemini_client.delete_file(client, uploaded)


def _transcribe_audio(client, audio_path: Path, work_dir: Path, opts: Options) -> str:
    """Transcribe one normalized audio file, chunking long ones.

    A single long upload (30-45 min) both risks the output-token ceiling and pushes the
    model into repetition loops. Files over the threshold are split into ~10-min chunks,
    each transcribed independently, then concatenated. Chunking benefits both providers
    (Gemini's failure modes; Groq's per-file size limit).
    """
    duration = audio.probe_duration(audio_path)
    if duration is None or duration <= config.AUDIO_CHUNK_THRESHOLD_SEC:
        return _transcribe_one(client, audio_path, opts)

    chunks = audio.split_audio(audio_path, config.AUDIO_CHUNK_LENGTH_SEC, work_dir / "chunks")
    if not chunks:
        return _transcribe_one(client, audio_path, opts)
    print(f"      (long: {duration/60:.0f} min -> {len(chunks)} chunks)")
    parts = [p.strip() for p in (_transcribe_one(client, c, opts) for c in chunks) if p and p.strip()]
    return "\n".join(parts)


def _ascii_name(stem: str) -> str:
    """ASCII-safe filename for the uploaded temp audio.

    The Gemini Files API sends the upload filename in an ASCII-only HTTP header, so
    accented lesson names (``módulo``, ``composição``…) raise UnicodeEncodeError on
    upload. We transliterate accents for the temporary upload artifact only — the
    output transcript keeps the original accented lesson name.
    """
    ascii_stem = (
        unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    )
    ascii_stem = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in ascii_stem).strip("-._")
    return ascii_stem or "audio-" + hashlib.sha1(stem.encode("utf-8")).hexdigest()[:8]


@dataclass
class Options:
    output_dir: Path
    provider: str = config.DEFAULT_PROVIDER  # "openrouter" (default) | "gemini" | "groq"
    model: str = config.DEFAULT_MODEL
    thinking_budget: int | None = config.DEFAULT_THINKING_BUDGET
    language: str | None = None
    keep_audio: bool = False
    overwrite: bool = False
    retranscribe: bool = False
    gemini_format: bool = False  # opt-in: also let Gemini write a .md note
    dry_run: bool = False


@dataclass
class Result:
    source: Path
    status: str  # done | skipped | dry-run | error
    transcript_path: Path | None = None
    markdown_path: Path | None = None
    error: str | None = None


def collect_inputs(target: Path) -> tuple[Path, list[Path]]:
    """Return (root, media_files). Recurses into subfolders for directory targets.

    `root` is the path that output structure is mirrored against: the directory itself
    for a folder target, or the file's parent for a single-file target.
    """
    if target.is_file():
        return target.parent, [target]
    if target.is_dir():
        files = sorted(
            p for p in target.rglob("*")
            if p.is_file() and p.suffix.lower() in config.MEDIA_EXTS
        )
        return target, files
    return target, []


def process_file(client, src: Path, rel: Path, opts: Options) -> Result:
    """Process one media file. `rel` is its path relative to the input root, so the
    course/module/lesson folder structure is recreated under the output dir."""
    out_subdir = opts.output_dir / rel.parent
    out_subdir.mkdir(parents=True, exist_ok=True)
    stem = rel.stem
    txt_path = out_subdir / f"{stem}.transcript.txt"
    md_path = out_subdir / f"{stem}.md"

    # Skip if the relevant final artifact already exists.
    final_path = md_path if opts.gemini_format else txt_path
    if final_path.exists() and not opts.overwrite and not opts.retranscribe:
        return Result(src, "skipped",
                      transcript_path=txt_path if txt_path.exists() else None,
                      markdown_path=md_path if md_path.exists() else None)

    work_dir = Path(tempfile.mkdtemp(prefix="course2md_"))
    audio_out = (out_subdir if opts.keep_audio else work_dir) / f"{_ascii_name(stem)}.norm.mp3"
    try:
        # 1. Extract / normalize audio.
        audio.normalize_to_audio(src, audio_out)
        if opts.dry_run:
            return Result(src, "dry-run")

        # 2. Transcript (reuse an existing one unless --retranscribe).
        if txt_path.exists() and not opts.retranscribe:
            transcript = txt_path.read_text(encoding="utf-8")
        else:
            transcript = _transcribe_audio(client, audio_out, work_dir, opts)
            if not transcript:
                return Result(src, "error", error="empty transcript from model")
            repeated = max_repeated_ngram(transcript)
            if repeated >= MAX_REPEATED_NGRAM:
                return Result(
                    src,
                    "error",
                    error=(
                        f"repetition loop detected: one "
                        f"{REPETITION_NGRAM_WORDS}-word sequence repeated "
                        f"{repeated} times"
                    ),
                )
            txt_path.write_text(transcript, encoding="utf-8")

        # Default: stop here. The transcript is the hand-off to the knowledge-compiler agent.
        if not opts.gemini_format:
            return Result(src, "done", transcript_path=txt_path)

        # 3. (opt-in) Let Gemini also compile a .md note.
        md = formatter.format_markdown(
            client, transcript, src.name, opts.model, opts.thinking_budget, opts.language)
        if not md:
            return Result(src, "error", transcript_path=txt_path,
                          error="empty markdown from model")
        md_path.write_text(md + "\n", encoding="utf-8")
        return Result(src, "done", transcript_path=txt_path, markdown_path=md_path)

    except (gemini_client.DailyQuotaExhausted, groq_client.DailyQuotaExhausted,
            openrouter_client.DailyQuotaExhausted):
        raise  # propagate: the whole batch must stop (every remaining call would 429/402)
    except Exception as e:  # noqa: BLE001 - keep the batch alive
        return Result(src, "error", error=str(e))
    finally:
        # work_dir holds temp audio + chunks; audio_out lives elsewhere only if keep_audio.
        shutil.rmtree(work_dir, ignore_errors=True)


def _print_result(res: Result) -> None:
    icon = {"done": "[ok]", "skipped": "[--]", "dry-run": "[..]",
            "error": "[!!]"}.get(res.status, "[??]")
    if res.status == "done":
        out = res.markdown_path or res.transcript_path
        detail = f"-> {out.name}" if out else ""
    elif res.status == "skipped":
        detail = "(exists; use --overwrite)"
    elif res.status == "dry-run":
        detail = "(audio extracted OK; Gemini calls skipped)"
    elif res.status == "error":
        detail = f"ERROR: {res.error}"
    else:
        detail = ""
    print(f"  {icon} {res.status} {detail}")


def run(target: Path, opts: Options) -> list[Result]:
    root, inputs = collect_inputs(target)
    if not inputs:
        print(f"No media files found at: {target}", file=sys.stderr)
        return []

    # Provider setup (dry-run never touches any API). Groq and OpenRouter are stateless
    # per request, so they need no client object — just a validated key up front.
    client = None
    if not opts.dry_run:
        if opts.provider == "openrouter":
            if not config.get_openrouter_api_key():
                raise RuntimeError(
                    "Provider 'openrouter' selected but OPENROUTER_API_KEY is not set. "
                    "Add it to .env (see .env.example) or the environment.")
        elif opts.provider == "groq":
            if not config.get_groq_api_key():
                raise RuntimeError(
                    "Provider 'groq' selected but GROQ_API_KEY is not set. "
                    "Add it to .env (see .env.example) or the environment.")
        else:
            client = gemini_client.get_client()

    results: list[Result] = []
    for i, src in enumerate(inputs, 1):
        rel = src.relative_to(root)
        print(f"[{i}/{len(inputs)}] {rel}")
        try:
            res = process_file(client, src, rel, opts)
        except (gemini_client.DailyQuotaExhausted, groq_client.DailyQuotaExhausted,
                openrouter_client.DailyQuotaExhausted):
            done = sum(1 for r in results if r.status == "done")
            print(f"  [stop] {opts.provider}: rate/quota limit won't clear this run — stopping "
                  f"after {done} new. Re-run later to resume (finished files are skipped).",
                  file=sys.stderr)
            break
        _print_result(res)
        results.append(res)
    return results
