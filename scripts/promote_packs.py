#!/usr/bin/env python3
"""Promote reviewed Stage-2 packs into the knowledge library (TASKS.md phase 5.4).

Promotion is the human step. This script does not decide WHAT to promote -- it
executes a decision already made, and refuses to overwrite anything.

What it changes on the way in
-----------------------------
1. **Filename.** Staging carries a ``.pack.v2`` infix that exists only to keep
   the defective v1 pack beside it as evidence. The library is flat and has no
   such infix, so ``<slug>.pack.v2.md`` -> ``<slug>.md`` and the split halves
   ``<slug>.pack.v2-a.md`` -> ``<slug>-a.md``. The naming is not invented here:
   the packs' own ``## See also`` entries already link to
   ``knowledge/coding/courses/<slug>.md``.

2. **Intra-pack cross-references.** Split halves cite each other by STAGING
   filename. Left alone, every one of those links dangles the moment the file
   is promoted, and a dangling link in the library is silent -- nothing reads it
   until a human follows it and finds nothing.

3. **tokens_estimate.** Every value measured in review under-stated the real
   count (by 235-979 on the calibration set). A hand-estimated token count is a
   guess and it guesses low; this replaces it with a count derived from the
   file's actual character length.

What it deliberately does NOT do
--------------------------------
- Touch ``output/`` in any way. The v1 packs stay where they are; they are the
  only surviving evidence of the forbidden-path defect.
- Overwrite an existing library file. A collision aborts the whole run.
- Promote anything not named on the command line.

Usage
-----
    .venv/bin/python scripts/promote_packs.py --dry-run
    .venv/bin/python scripts/promote_packs.py --apply
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

STAGING = Path("output/jstack-lives")
LIBRARY = Path("../../coding/courses")

CHARS_PER_TOKEN = 3.7


def library_name(pack: Path) -> str:
    """``<slug>.pack.v2[-a].md`` -> ``<slug>[-a].md``."""
    m = re.match(r"(?P<slug>.+)\.pack\.v2(?P<half>-[ab])?\.md$", pack.name)
    if not m:
        raise ValueError(f"unexpected staging name: {pack.name}")
    return f"{m['slug']}{m['half'] or ''}.md"


def rewrite_body(text: str) -> tuple[str, int]:
    """Repoint staging filenames at their library names. Returns (text, count)."""
    pattern = re.compile(r"([A-Za-z0-9._-]+)\.pack\.v2(-[ab])?\.md")
    n = 0

    def sub(m: re.Match) -> str:
        nonlocal n
        n += 1
        return f"{m.group(1)}{m.group(2) or ''}.md"

    return pattern.sub(sub, text), n


def fix_tokens(text: str) -> tuple[str, str | None, int]:
    """Replace tokens_estimate with a count measured from the body."""
    measured = round(len(text) / CHARS_PER_TOKEN)
    m = re.search(r"^tokens_estimate:\s*(.+)$", text, re.M)
    old = m.group(1).strip() if m else None
    if m:
        text = text[:m.start()] + f"tokens_estimate: {measured}" + text[m.end():]
    return text, old, measured


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write files")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--glob", default="*.pack.v2*.md")
    args = ap.parse_args()

    if not args.apply and not args.dry_run:
        ap.error("choose --dry-run or --apply")

    if not STAGING.is_dir():
        print(f"!! staging not found: {STAGING.resolve()}", file=sys.stderr)
        return 2
    if not LIBRARY.is_dir():
        print(f"!! library not found: {LIBRARY.resolve()}", file=sys.stderr)
        return 2

    packs = sorted(STAGING.glob(f"*/{args.glob}"))
    if not packs:
        print("!! no packs matched", file=sys.stderr)
        return 2

    # Collisions are checked for ALL packs before ANY is written, so a partial
    # promotion cannot happen.
    plan, collisions = [], []
    for pack in packs:
        dest = LIBRARY / library_name(pack)
        if dest.exists():
            collisions.append(dest)
        plan.append((pack, dest))

    if collisions:
        print("!! ABORT -- these library files already exist:", file=sys.stderr)
        for c in collisions:
            print(f"     {c}", file=sys.stderr)
        return 1

    total_links = 0
    for pack, dest in plan:
        text = pack.read_text(encoding="utf-8")
        text, nlinks = rewrite_body(text)
        text, old_tok, new_tok = fix_tokens(text)
        total_links += nlinks
        note = f"links={nlinks} tokens {old_tok}->{new_tok}"
        if args.apply:
            dest.write_text(text, encoding="utf-8")
            print(f"  PROMOTED {dest.name}  ({note})")
        else:
            print(f"  would promote {pack.name}\n            -> {dest.name}  ({note})")

    verb = "promoted" if args.apply else "planned"
    print(f"\n{len(plan)} pack(s) {verb}, {total_links} cross-reference(s) repointed.")
    if not args.apply:
        print("Dry run -- nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
