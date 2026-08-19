#!/usr/bin/env python3
"""Content-based coverage reconciliation for Stage-2 packs (TASKS.md phase 5.3).

The reconciliation this replaces counted folder membership: it asserted that
every transcript sits under a course that *has* a pack, and called that 100%
coverage. It never asserted that a lesson's content reached the compiler. Under
the forbidden script's 60k-char prompt slice it demonstrably had not -- coverage
was 22-66%, median 37%, and nothing downstream announced it.

This script asserts something narrower but real: that every lesson transcript in
a course is *individually accounted for* in its pack's ``## Curriculum`` spine,
matched by title rather than by counting files.

WHAT THIS PROVES AND WHAT IT DOES NOT
-------------------------------------
A matched curriculum line proves the lesson reached the compiler's input and
survived into the pack's spine. It does NOT prove the lesson's body was
compressed faithfully -- that is a correctness question, and a consistency gate
cannot answer it. Read the ratio as "no lesson was silently dropped", never as
"the pack is right". The remaining fidelity check is human review (phase 5.4).

Usage
-----
    .venv/bin/python scripts/pack_coverage.py output/jstack-lives
    .venv/bin/python scripts/pack_coverage.py output/jstack-lives --pack-glob '*.pack.v2.md'
    .venv/bin/python scripts/pack_coverage.py output/jstack-lives/<course> -v
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
import unicodedata
from pathlib import Path

REQUIRED_KEYS = ("title", "author", "type", "domain", "source", "compiled")
REQUIRED_SECTIONS = ("## TL;DR", "## Curriculum", "## How to apply")

# MVP build date -- no pack in this project can legitimately predate it.
PROJECT_EPOCH = _dt.date(2026, 6, 19)

# course.md's soft cap, and a PT-BR chars-per-token rule of thumb.
TOKEN_CAP = 2000
CHARS_PER_TOKEN = 3.7

# Words too common in these course titles to carry matching signal.
STOPWORDS = {
    "a", "as", "ao", "aos", "com", "como", "da", "das", "de", "do", "dos", "e",
    "em", "entendendo", "introducao", "na", "nas", "no", "nos", "o", "os", "para",
    "por", "que", "se", "sem", "um", "uma", "the", "and", "of", "to", "in", "on",
    "criando", "utilizando", "usando", "implementando", "configurando", "sao",
    "nossa", "nosso", "seus", "suas", "conteudo",
}


def _fold(text: str) -> str:
    """Lowercase and strip accents -- FOR MATCHING ONLY, never for output."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", _fold(text))
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def lesson_title(path: Path) -> str:
    """Human title from a transcript filename, minus ordering prefix."""
    stem = path.name.removesuffix(".transcript.txt")
    return re.sub(r"^\d+[-_]", "", stem).replace("-", " ")


def parse_pack(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    front: dict[str, str] = {}
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            for line in raw[3:end].splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    front[k.strip()] = v.strip().strip('"').strip("'")
    curriculum: list[str] = []
    in_section = False
    for line in raw.splitlines():
        if line.startswith("## "):
            in_section = line.strip().lower().startswith("## curriculum")
            continue
        if in_section and line.strip():
            curriculum.append(line.strip())
    return {"raw": raw, "front": front, "curriculum": curriculum}


def check_course(
    course: Path, pack_glob: str, verbose: bool, expect_today: bool = False
) -> tuple[bool, list[str], list[str]]:
    lessons = sorted(course.rglob("*.transcript.txt"))
    packs = sorted(course.glob(pack_glob))
    problems: list[str] = []
    warnings: list[str] = []

    if not lessons:
        return True, [], []
    if not packs:
        return False, [f"NO PACK matching {pack_glob!r} ({len(lessons)} lessons unreached)"], []

    merged = "\n".join(p.read_text(encoding="utf-8") for p in packs)
    parsed = [parse_pack(p) for p in packs]
    all_curriculum = [line for p in parsed for line in p["curriculum"]]

    # --- structural checks (per pack) ---
    today = _dt.date.today()
    for pack, data in zip(packs, parsed):
        for key in REQUIRED_KEYS:
            if key not in data["front"]:
                problems.append(f"{pack.name}: missing frontmatter key `{key}`")
        compiled = data["front"].get("compiled", "")
        # A legitimate pack carries the date it was actually compiled on, which is
        # usually NOT today -- only implausible dates are evidence of invention.
        # PROJECT_EPOCH is the MVP build date: nothing here can predate it.
        if compiled:
            try:
                when = _dt.date.fromisoformat(compiled)
            except ValueError:
                problems.append(f"{pack.name}: `compiled: {compiled}` is not an ISO date")
            else:
                if when < PROJECT_EPOCH:
                    problems.append(
                        f"{pack.name}: `compiled: {compiled}` predates the project "
                        f"({PROJECT_EPOCH}) -- the documented invented-date failure"
                    )
                elif when > today:
                    problems.append(f"{pack.name}: `compiled: {compiled}` is in the future")
                elif expect_today and when != today:
                    problems.append(
                        f"{pack.name}: `compiled: {compiled}` is not today ({today}) "
                        "-- expected for a pack written by this run"
                    )
        for section in REQUIRED_SECTIONS:
            if section.lower() not in data["raw"].lower():
                problems.append(f"{pack.name}: missing section `{section}`")
        if len(pack.read_bytes()) < 1500:
            problems.append(
                f"{pack.name}: only {len(pack.read_bytes())}B -- likely truncated"
            )

        # --- token budget (advisory) ---
        # course.md caps a pack at ~2k tokens and says to SPLIT by module cluster
        # rather than ship one oversized pack. Over-cap is a judgment call, so it
        # warns rather than fails -- but a WRONG tokens_estimate is not judgment,
        # it is a false number in the frontmatter, and downstream budgeting reads it.
        actual = round(len(data["raw"]) / CHARS_PER_TOKEN)
        claimed_raw = data["front"].get("tokens_estimate", "")
        claimed = int(m.group()) if (m := re.search(r"\d+", claimed_raw)) else None
        if claimed is not None and not (0.65 * actual <= claimed <= 1.5 * actual):
            warnings.append(
                f"{pack.name}: `tokens_estimate: {claimed}` vs ~{actual} actual "
                f"({claimed / actual:.0%}) -- restate it honestly"
            )
        if actual > TOKEN_CAP * 1.25:
            warnings.append(
                f"{pack.name}: ~{actual} tokens is over the ~{TOKEN_CAP} cap -- "
                "course.md says split by module cluster and cross-link"
            )

    # --- diacritic sanity: PT-BR substance must not be ASCII-folded ---
    if not re.search(r"[áàâãéêíóôõúüç]", merged, re.IGNORECASE):
        problems.append("no PT-BR diacritics anywhere -- body may have been ASCII-folded")

    # --- content-based coverage: every lesson accounted for in the spine ---
    curriculum_tokens = [_tokens(line) for line in all_curriculum]
    unmatched: list[str] = []
    for lesson in lessons:
        want = _tokens(lesson_title(lesson))
        if not want:
            continue
        best = max(
            (len(want & have) / len(want) for have in curriculum_tokens),
            default=0.0,
        )
        if best < 0.34:
            unmatched.append(f"{lesson.parent.name}/{lesson.name} (best overlap {best:.0%})")

    covered = len(lessons) - len(unmatched)
    ratio = covered / len(lessons)
    if unmatched:
        problems.append(
            f"coverage {covered}/{len(lessons)} ({ratio:.0%}) -- "
            f"{len(unmatched)} lesson(s) absent from the Curriculum spine"
        )
        if verbose:
            problems.extend(f"    unreached: {u}" for u in unmatched)

    return not problems, problems, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="a course folder, or a tree of them")
    ap.add_argument("--pack-glob", default="*.pack.md", help="pack filename glob (default: %(default)s)")
    ap.add_argument("-v", "--verbose", action="store_true", help="name every unreached lesson")
    ap.add_argument(
        "--expect-today",
        action="store_true",
        help="also require `compiled` == today (use when verifying a fresh run)",
    )
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 2

    own = list(args.root.glob("*.transcript.txt")) or list(args.root.rglob("*.transcript.txt"))
    if list(args.root.glob(args.pack_glob)) or (own and not any(d.is_dir() for d in args.root.iterdir())):
        courses = [args.root]
    else:
        courses = sorted(d for d in args.root.iterdir() if d.is_dir() and any(d.rglob("*.transcript.txt")))
        if not courses:
            courses = [args.root]

    failed = 0
    warned = 0
    for course in courses:
        ok, problems, warns = check_course(
            course, args.pack_glob, args.verbose, args.expect_today
        )
        if ok:
            n = len(list(course.rglob("*.transcript.txt")))
            print(f"PASS  {course.name}  ({n} lessons)")
        else:
            failed += 1
            print(f"FAIL  {course.name}")
            for p in problems:
                print(f"      {p}")
        for w in warns:
            warned += 1
            print(f"      WARN  {w}")

    print()
    print(f"{len(courses) - failed}/{len(courses)} courses pass" + (f", {warned} advisory warning(s)." if warned else "."))
    print(
        "NOTE: a matched Curriculum line proves the lesson was not silently dropped.\n"
        "      It does NOT prove the body was compressed faithfully -- that is human\n"
        "      review (phase 5.4). A consistency gate is not a correctness gate."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
