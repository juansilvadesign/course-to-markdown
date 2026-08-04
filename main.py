#!/usr/bin/env python3
"""course-to-markdown: course videos/audio -> verbatim transcript -> compressed Markdown notes (Gemini)."""
from __future__ import annotations

import os
import sys

# Force UTF-8 filesystem handling before anything touches accented lesson paths
# (ó, ç, ã, í…). Some launch environments (cron, a bare shell, CI) run under an
# ASCII "C" locale, which makes subprocess/ffmpeg calls on accented filenames raise
# "'ascii' codec can't encode". Re-exec once in UTF-8 mode when needed; this is a
# no-op when the locale is already UTF-8.
if not sys.flags.utf8_mode and (sys.getfilesystemencoding() or "").lower() not in ("utf-8", "utf8"):
    os.environ["PYTHONUTF8"] = "1"
    os.execv(sys.executable, [sys.executable, "-X", "utf8", *sys.argv])

import argparse
from pathlib import Path

from course_to_markdown import config
from course_to_markdown.pipeline import Options, run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="course-to-markdown",
        description=(
            "Course video/audio -> audio -> verbatim transcript (Gemini). "
            "Transcripts (folder structure mirrored) are then handed to the knowledge-compiler "
            "Claude agent for compilation. Use --gemini-format for the legacy single-provider .md."
        ),
    )
    p.add_argument("input", nargs="?", default=str(config.DEFAULT_INPUT_DIR),
                   help="Media file or folder of media files (default: ./input).")
    p.add_argument("-o", "--output", default=str(config.DEFAULT_OUTPUT_DIR),
                   help="Output directory for .md and .transcript.txt (default: ./output).")
    p.add_argument("--provider", choices=["openrouter", "gemini", "groq"],
                   default=config.DEFAULT_PROVIDER,
                   help=f"Stage-1 transcription backend (default: {config.DEFAULT_PROVIDER}). "
                        "'openrouter' = base64 audio -> xiaomi/mimo-v2.5 (cheapest, 131k output "
                        "ceiling; needs OPENROUTER_API_KEY + a funded balance); "
                        "'gemini' = audio->text via the gemini-2.5-flash Files API; "
                        "'groq' = Groq Whisper (cheaper, faster STT, needs GROQ_API_KEY). "
                        "NOTE: for code-dense courses prefer 'gemini' — openrouter/MiMo "
                        "mis-renders English technical terms fluently (unknown -> any).")
    p.add_argument("--model", default=None,
                   help="Transcription model. Default depends on --provider: "
                        f"{config.DEFAULT_OPENROUTER_MODEL} (openrouter) / "
                        f"{config.DEFAULT_MODEL} (gemini) / {config.DEFAULT_GROQ_MODEL} (groq).")
    p.add_argument("--language", default=None,
                   help="Optional language hint, e.g. 'Portuguese' or 'English' (default: auto / preserve).")
    p.add_argument("--thinking-budget", type=int, default=config.DEFAULT_THINKING_BUDGET,
                   help="Gemini 2.5 thinking budget in tokens (default: 0 = off).")
    p.add_argument("--keep-audio", action="store_true",
                   help="Keep the extracted .norm.mp3 in the output dir (default: discarded).")
    p.add_argument("--overwrite", action="store_true",
                   help="Regenerate even if the .md already exists.")
    p.add_argument("--retranscribe", action="store_true",
                   help="Re-run transcription even if a .transcript.txt already exists.")
    p.add_argument("--gemini-format", action="store_true",
                   help="Legacy: also have Gemini compile a .md note (default: stop at the transcript "
                        "and let the knowledge-compiler Claude agent do it).")
    p.add_argument("--dry-run", action="store_true",
                   help="Extract audio and report what would run; skip all Gemini calls.")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    target = Path(args.input).expanduser()
    if not target.exists():
        print(f"Input not found: {target}", file=sys.stderr)
        return 2

    # --gemini-format is a Gemini-only legacy path (text->note); the others are transcribe-only.
    if args.gemini_format and args.provider != "gemini":
        print("Error: --gemini-format is a Gemini-only legacy path; run it with "
              "--provider gemini.", file=sys.stderr)
        return 2

    # Per-provider default model (kept out of argparse so the default tracks --provider).
    _PROVIDER_DEFAULT_MODEL = {
        "openrouter": config.DEFAULT_OPENROUTER_MODEL,
        "groq": config.DEFAULT_GROQ_MODEL,
        "gemini": config.DEFAULT_MODEL,
    }
    model = args.model or _PROVIDER_DEFAULT_MODEL[args.provider]

    opts = Options(
        output_dir=Path(args.output).expanduser(),
        provider=args.provider,
        model=model,
        thinking_budget=args.thinking_budget,
        language=args.language,
        keep_audio=args.keep_audio,
        overwrite=args.overwrite,
        retranscribe=args.retranscribe,
        gemini_format=args.gemini_format,
        dry_run=args.dry_run,
    )

    try:
        results = run(target, opts)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not results:
        return 1

    errors = sum(1 for r in results if r.status == "error")
    processed = sum(1 for r in results if r.status == "done")
    skipped = sum(1 for r in results if r.status == "skipped")
    dry = sum(1 for r in results if r.status == "dry-run")
    print(f"\nSummary: {processed} processed, {skipped} skipped, {dry} dry-run, "
          f"{errors} errors (of {len(results)}).")
    return 1 if errors and not processed else 0


if __name__ == "__main__":
    raise SystemExit(main())
