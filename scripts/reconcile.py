#!/usr/bin/env python3
"""Reconcile a batch's media against its manifest and transcripts (TASKS.md 3.6 + 3.7).

Answers the one question a folder listing cannot: is this batch actually finished?
Folder presence, a 200 catalog response, and a few `done` manifest entries all lie
independently, so this compares four sources and reports where they disagree.

3.6 reconciliation   media count == non-empty transcript count, per course
3.7 failure sweep    no failed/non-terminal manifest entries, no .part, no zero-byte
                     transcript, no media without a transcript

Exit 0 only when every course is clean, so it can gate a promotion step.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(SCRIPT_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_PROJECT_ROOT))

from course_to_markdown.config import MEDIA_EXTS

TERMINAL = {"done", "skipped", "unavailable", "no-video"}


def media_files(course: Path) -> list[Path]:
    return sorted(p for p in course.rglob("*")
                  if p.is_file() and p.suffix.lower() in MEDIA_EXTS)


def transcript_for(media: Path, course_in: Path, course_out: Path) -> Path:
    relative = media.relative_to(course_in)
    return course_out / relative.parent / f"{relative.stem}.transcript.txt"


def manifest_problems(course: Path) -> list[str]:
    path = course / "manifest.json"
    if not path.exists():
        return ["missing manifest.json"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ["unreadable manifest.json"]
    problems = []
    states = manifest.get("lessons") or {}
    failed = [k for k, v in states.items() if (v or {}).get("status") == "failed"]
    pending = [k for k, v in states.items()
               if (v or {}).get("status") not in TERMINAL
               and (v or {}).get("status") != "failed"]
    if failed:
        problems.append(f"{len(failed)} failed manifest entr(ies)")
    if pending:
        problems.append(f"{len(pending)} non-terminal manifest entr(ies)")
    return problems


def ghost_downloads(course: Path) -> list[str]:
    """Interrupted downloads the manifest has no memory of.

    A killed downloader leaves `<lesson>.mp4.part` / `.ytdl` behind without ever writing
    a manifest entry, so the course reads as 100% `done` with the lesson simply absent.
    This is the one incompleteness a manifest scan structurally cannot see.
    """
    path = course / "manifest.json"
    if not path.exists():
        return []
    try:
        known = set(json.loads(path.read_text(encoding="utf-8")).get("lessons") or {})
    except (json.JSONDecodeError, OSError):
        return []
    ghosts = set()
    for leftover in list(course.rglob("*.part")) + list(course.rglob("*.ytdl")):
        stem = leftover.name.split(".")[0]
        relative = str((leftover.parent / stem).relative_to(course))
        if relative not in known:
            ghosts.add(relative)
    return sorted(ghosts)


def numbering_gaps(course: Path) -> list[str]:
    """Missing numeric prefixes inside a lesson folder, e.g. 05 and 09 absent from 01..11.

    Advisory only -- upstream does sometimes retire a lesson -- but a gap is the cheapest
    signal that the catalog holds more than this folder does, and it needs no cookie.
    """
    gaps = []
    for folder in {p.parent for p in course.rglob("*") if p.suffix.lower() in MEDIA_EXTS}:
        numbers = set()
        for item in folder.iterdir():
            head = item.name.split("-", 1)[0]
            if head.isdigit() and len(head) <= 3:
                numbers.add(int(head))
        if len(numbers) < 3:
            continue
        low, high = min(numbers), max(numbers)
        absent = [n for n in range(low, high + 1) if n not in numbers]
        if absent:
            where = folder.relative_to(course)
            gaps.append(f"{where or '.'}: {', '.join(f'{n:02d}' for n in absent)}")
    return sorted(gaps)


def audit(course_in: Path, course_out: Path) -> dict:
    media = media_files(course_in)
    missing, empty = [], []
    for item in media:
        transcript = transcript_for(item, course_in, course_out)
        if not transcript.is_file():
            missing.append(item.relative_to(course_in))
        elif transcript.stat().st_size == 0:
            empty.append(item.relative_to(course_in))
    partials = list(course_in.rglob("*.part"))
    done = len(media) - len(missing) - len(empty)
    return {
        "media": len(media),
        "done": done,
        "missing": missing,
        "empty": empty,
        "partials": partials,
        "manifest": manifest_problems(course_in),
        "ghosts": ghost_downloads(course_in),
        "gaps": numbering_gaps(course_in),
    }


def run(args) -> int:
    input_root = Path(args.input_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    if not input_root.is_dir():
        raise SystemExit(f"Input root not found: {input_root}")

    courses = [c for c in sorted(input_root.iterdir()) if c.is_dir() and media_files(c)]
    if not courses:
        raise SystemExit(f"No course folders with media under {input_root}")

    dirty, total_media, total_done, advised = [], 0, 0, 0
    for course in courses:
        report = audit(course, output_root / course.name)
        total_media += report["media"]
        total_done += report["done"]
        flags = []
        if report["missing"]:
            flags.append(f"{len(report['missing'])} missing transcript(s)")
        if report["empty"]:
            flags.append(f"{len(report['empty'])} zero-byte transcript(s)")
        if report["partials"]:
            flags.append(f"{len(report['partials'])} .part file(s)")
        for ghost in report["ghosts"]:
            flags.append(f"interrupted download with NO manifest entry: {ghost}")
        flags += report["manifest"]
        advisories = [f"numbering gap, verify against the catalog -> {g}"
                      for g in report["gaps"]]

        mark = "ok  " if not flags else "!!  "
        print(f"{mark}{report['done']:3d}/{report['media']:<3d}  {course.name}")
        for flag in flags:
            print(f"         - {flag}")
        for note in advisories:
            print(f"         ? {note}")
        advised += len(advisories)
        if flags:
            dirty.append(course.name)
            if args.verbose:
                for item in report["missing"][:args.verbose]:
                    print(f"           missing: {item}")

    print("=" * 60)
    print(f"{total_done}/{total_media} transcripts across {len(courses)} course(s); "
          f"{len(dirty)} course(s) need attention")
    if advised:
        print(f"{advised} numbering gap(s) marked '?' -- only the catalog listing can "
              f"settle those, and that needs a live session.")
    if dirty:
        print("re-run those courses; main.py skips what is already on disk.")
    return 1 if dirty else 0


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input_root", help="Batch root, e.g. input/jstack-lives.")
    parser.add_argument("output_root", help="Matching output root, e.g. output/jstack-lives.")
    parser.add_argument("-v", "--verbose", type=int, default=0, metavar="N",
                        help="Also list up to N missing lesson paths per course.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
