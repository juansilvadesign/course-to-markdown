#!/usr/bin/env python
"""Audit transcripts for the fluent-substitution failure that every other guard misses.

Why this exists
---------------
Stage 1's guards catch *broken* output: a non-STOP finish reason, an 8-word phrase
repeated 50+ times, an empty file, a transcript too short for its audio. They all pass
on output that is fluent and wrong.

On a real TypeScript lesson, ``xiaomi/mimo-v2.5`` transcribed the type ``unknown`` as
``any`` in 7 of 7 occurrences, producing:

    "a diferença tá em que any permite que você acesse qualquer coisa e any não permite"

Grammatical, plausible, and semantically inverted — and Stage 2 would faithfully compress
that into a WRONG rule in the knowledge library. Groq's Whisper has the same class of
defect but garbles words into obvious nonsense (``any`` -> "N"), which is self-announcing.
MiMo's is not. Hence this audit.

Modes
-----
``--reference`` diffs English-term counts against a transcript of the same lesson from
another provider. This is the strongest signal and the only one that proves a loss.

Without a reference it runs two heuristics that need no ground truth:

1. **Contrast collision** — the same technical term on both sides of a contrastive
   construction ("X permite ... e X não permite"). A term cannot contrast with itself, so
   this is near-certain evidence one side was substituted.
2. **Orphaned pair member** — terms that are taught as contrasting pairs (any/unknown,
   let/const, interface/type). One appearing repeatedly while its partner never appears is
   suspicious in a course that teaches the distinction.

Heuristics flag candidates for human review; they do not prove a defect, and they cannot
find a substitution that happens to be self-consistent.

Usage
-----
    jargon_audit.py <transcript-or-dir> [--reference <transcript-or-dir>]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Terms taught as contrasting pairs. Seeing one a lot and never the other is a smell.
PAIRS = [
    ("any", "unknown"),
    ("interface", "type"),
    ("let", "const"),
    ("null", "undefined"),
]

# English technical vocabulary worth counting in a PT transcript.
TERMS = [
    "any", "unknown", "never", "void", "null", "undefined", "readonly",
    "interface", "type", "enum", "generic", "string", "number", "boolean",
    "strict", "tsconfig", "typescript", "javascript", "compiler", "build",
    "react", "hook", "state", "props", "component", "context", "reducer",
    "async", "await", "promise", "callback", "closure", "middleware",
    "docker", "container", "deploy", "token", "cookie", "header", "payload",
]

def count(text: str, term: str) -> int:
    return len(re.findall(rf"\b{re.escape(term)}\b", text, re.I))


def contrast_collisions(text: str) -> list[str]:
    """Sentences where one term is both asserted and negated — a substituted contrast."""
    hits: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for term in {t for pair in PAIRS for t in pair}:
            # "<term> <verb> ... e <term> não <verb>"
            pat = (rf"\b{term}\b[^.!?]{{0,80}}?\b(permite|aceita|recebe|deixa|pode)\b"
                   rf"[^.!?]{{0,80}}?\be\s+(?:o\s+|a\s+)?{term}\b\s+n[ãa]o\b")
            if re.search(pat, sentence, re.I):
                hits.append(f"[{term}] {' '.join(sentence.split())[:160]}")
                break
    return hits


def orphaned_pairs(text: str, min_hits: int = 3) -> list[str]:
    out: list[str] = []
    for a, b in PAIRS:
        ca, cb = count(text, a), count(text, b)
        if ca >= min_hits and cb == 0:
            out.append(f"{a}x{ca} but {b}x0 — is '{b}' being transcribed as '{a}'?")
        elif cb >= min_hits and ca == 0:
            out.append(f"{b}x{cb} but {a}x0 — is '{a}' being transcribed as '{b}'?")
    return out


def reference_diff(text: str, ref: str) -> list[str]:
    out: list[str] = []
    for t in TERMS:
        a, b = count(ref, t), count(text, t)
        if a >= 3 and b == 0:
            out.append(f"'{t}': reference x{a} -> audited x0  (TERM LOST)")
        elif a >= 5 and b < a * 0.4:
            out.append(f"'{t}': reference x{a} -> audited x{b}  (down {100*(1-b/a):.0f}%)")
    return out


def transcripts(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(target.rglob("*.transcript.txt"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--reference", default=None,
                    help="Same-lesson transcript (or matching tree) from another provider.")
    a = ap.parse_args()

    target = Path(a.target)
    files = transcripts(target)
    if not files:
        print(f"No transcripts under {target}", file=sys.stderr)
        return 2

    flagged = 0
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        notes: list[str] = []

        if a.reference:
            ref_path = Path(a.reference)
            if ref_path.is_dir() and target.is_dir():
                ref_path = ref_path / f.relative_to(target)
            if ref_path.exists():
                notes += reference_diff(text, ref_path.read_text(encoding="utf-8",
                                                                 errors="replace"))

        notes += [f"contrast collision: {h}" for h in contrast_collisions(text)]
        notes += orphaned_pairs(text)

        if notes:
            flagged += 1
            rel = f.relative_to(target) if target.is_dir() else f.name
            print(f"\n!! {rel}")
            for n in notes:
                print(f"     {n}")

    print(f"\n{'='*54}")
    print(f"scanned {len(files)} transcript(s); {flagged} flagged for human review")
    print("heuristics flag candidates, they do not prove a defect")
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
