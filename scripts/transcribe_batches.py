#!/usr/bin/env python3
"""Transcribe the direct child course folders of one completed Stage 0 batch.

Each child gets its own `main.py` subprocess and matching output root, so a
bounded number of courses can run concurrently without two workers touching the
same transcript. Re-running is safe because `main.py` skips existing outputs.

Run this only after the corresponding Stage 0 batch exits. It deliberately
refuses `.part` files and dirty manifests, but a manifest cannot prove that an
upstream downloader process is no longer adding brand-new lessons.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

SCRIPT_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(SCRIPT_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_PROJECT_ROOT))

from course_to_markdown.config import MEDIA_EXTS, PROJECT_ROOT


@dataclass(frozen=True)
class Batch:
    name: str
    input_dir: Path
    output_dir: Path


def discover_batches(input_root: Path, output_root: Path) -> list[Batch]:
    batches: list[Batch] = []
    for child in sorted(input_root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        has_media = any(
            path.is_file() and path.suffix.lower() in MEDIA_EXTS
            for path in child.rglob("*")
        )
        if has_media:
            batches.append(Batch(child.name, child, output_root / child.name))
    return batches


def validate_batch(batch: Batch) -> list[str]:
    errors: list[str] = []
    partials = list(batch.input_dir.rglob("*.part"))
    if partials:
        errors.append(f"{len(partials)} partial download(s)")

    manifest_path = batch.input_dir / "manifest.json"
    if not manifest_path.exists():
        errors.append("missing manifest.json")
        return errors
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        errors.append("unreadable manifest.json")
        return errors
    states = (manifest.get("lessons") or {}).values()
    failed = sum(state.get("status") == "failed" for state in states)
    if failed:
        errors.append(f"{failed} failed manifest lesson(s)")
    return errors


def command_for(batch: Batch, args) -> list[str]:
    command = [
        sys.executable,
        "-u",
        str(PROJECT_ROOT / "main.py"),
        str(batch.input_dir),
        "-o",
        str(batch.output_dir),
        "--provider",
        args.provider,
    ]
    if args.language:
        command += ["--language", args.language]
    if args.model:
        command += ["--model", args.model]
    return command


def missing_transcripts(batch: Batch) -> list[Path]:
    missing: list[Path] = []
    for media in batch.input_dir.rglob("*"):
        if not media.is_file() or media.suffix.lower() not in MEDIA_EXTS:
            continue
        relative = media.relative_to(batch.input_dir)
        transcript = (
            batch.output_dir
            / relative.parent
            / f"{relative.stem}.transcript.txt"
        )
        if not transcript.is_file() or transcript.stat().st_size == 0:
            missing.append(relative)
    return missing


def run_batch(batch: Batch, args, logs_dir: Path) -> tuple[str, int, Path]:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"transcribe-{batch.name}.log"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("\n=== resumable run ===\n")
        handle.flush()
        completed = subprocess.run(
            command_for(batch, args),
            cwd=PROJECT_ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
        missing = missing_transcripts(batch)
        if missing:
            handle.write(
                f"\n[reconcile] {len(missing)} media file(s) still lack a "
                "non-empty transcript\n"
            )
            handle.flush()
    return batch.name, completed.returncode or (3 if missing else 0), log_path


def run(args) -> int:
    input_root = Path(args.input_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    if not input_root.is_dir():
        raise SystemExit(f"Input batch root not found: {input_root}")
    if args.jobs < 1:
        raise SystemExit("--jobs must be at least 1")

    batches = discover_batches(input_root, output_root)
    if not batches:
        raise SystemExit(f"No direct child course folders with media under {input_root}")

    invalid = [
        (batch.name, problems)
        for batch in batches
        if (problems := validate_batch(batch))
    ]
    if invalid:
        for name, problems in invalid:
            print(f"[blocked] {name}: {', '.join(problems)}", file=sys.stderr)
        raise SystemExit(
            "Batch validation failed. Finish/retry Stage 0 before transcription fan-out."
        )

    logs_dir = PROJECT_ROOT / ".logs" / f"{input_root.name}-transcription"
    logs_dir.mkdir(parents=True, exist_ok=True)
    lock_path = logs_dir / ".fanout.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(
                f"Another fan-out run holds {lock_path}; do not overlap batches."
            ) from None

        print(
            f"[fan-out] {len(batches)} course(s) | jobs={args.jobs} | "
            f"{input_root} -> {output_root}",
            flush=True,
        )
        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(run_batch, batch, args, logs_dir): batch
                for batch in batches
            }
            for future in as_completed(futures):
                batch = futures[future]
                try:
                    name, returncode, log_path = future.result()
                except Exception as error:  # noqa: BLE001 - let other courses finish.
                    failures.append(batch.name)
                    print(
                        f"[error] {batch.name}: {type(error).__name__}",
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
                state = "clean" if returncode == 0 else f"exit {returncode}"
                print(f"[{state}] {name} -> {log_path}", flush=True)
                if returncode:
                    failures.append(name)

    if failures:
        print(
            f"[summary] {len(batches) - len(failures)}/{len(batches)} clean; "
            f"retry needed: {', '.join(failures)}",
            file=sys.stderr,
        )
        return 1
    print(f"[summary] {len(batches)}/{len(batches)} clean", flush=True)
    return 0


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Transcribe direct child course folders with bounded concurrency."
    )
    parser.add_argument("input_root", help="Batch root, e.g. input/jstack-lives.")
    parser.add_argument("output_root", help="Matching output root, e.g. output/jstack-lives.")
    parser.add_argument("--jobs", type=int, default=3, help="Concurrent courses (default: 3).")
    parser.add_argument(
        "--provider",
        choices=("gemini", "groq"),
        default="gemini",
    )
    parser.add_argument("--model")
    parser.add_argument("--language", default="Portuguese")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
