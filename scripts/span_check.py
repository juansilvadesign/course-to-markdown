"""Per-Curriculum-line attribution check (orchestrator-side instrument, not committed).

A Curriculum line ends with the bare stem of the lesson it describes. The coverage
gate proves every lesson HAS a line; it cannot see a line describing ANOTHER lesson's
content (found 2026-09-18: the S3 pack put lesson 10's decodeURIComponent and IAM
permission steps under lesson 09). For each backticked span in line N:
  OK         its distinctive words were all spoken in lesson N
  ELSEWHERE  not all in lesson N, but all in some other lesson  -> content bleed
  UNSPOKEN   not all in any single lesson -> normalised spoken form or invention (human)
Word presence is a SET test (lenient on order) -- it can miss bleed, it should not invent it.

Usage: span_check.py <course_dir> [pack_path ...]
"""
import pathlib
import re
import sys
import unicodedata

STOP = {"the", "and", "for", "const", "new", "true", "false", "null", "return", "await",
        "async", "function", "import", "export", "from", "type", "string", "number", "com",
        "que", "uma", "para", "dos", "das", "nos", "nas", "por", "json", "http", "https"}


def fold(s):
    d = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in d if not unicodedata.combining(c))


def words(text):
    t = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)   # URIComponent -> URI Component
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t)         # decodeURI -> decode URI
    return [w for w in re.findall(r"[a-z0-9]+", fold(t)) if len(w) >= 3 and w not in STOP]


def main(course, *packs):
    course = pathlib.Path(course)
    lessons, squashed = {}, {}
    for p in course.rglob("*.transcript.txt"):
        key, raw = unicodedata.normalize("NFC", p.name.removesuffix(".transcript.txt")), p.read_text(encoding="utf-8")
        lessons[key] = set(words(raw))
        # Spoken "user info" / camel getUserInfo never yield the token `userinfo`; a squashed
        # substring test finds them. Only for tokens >= 5 chars: a short one would match
        # across word boundaries by accident. (Known-good leg: 2 false ELSEWHERE without it.)
        squashed[key] = re.sub(r"[^a-z0-9]", "", fold(raw))

    def spoken(t, key):
        return t in lessons[key] or (len(t) >= 5 and t in squashed[key])
    packs = [pathlib.Path(p) for p in packs] or sorted(course.glob("*.pack.v2*.md"))
    for pack in packs:
        print(f"=== {pack.name}")
        on, counts = False, {"OK": 0, "ELSEWHERE": 0, "UNSPOKEN": 0}
        numbered = matched = 0
        for ln in pack.read_text(encoding="utf-8").splitlines():
            if ln.startswith("## "):
                on = ln.strip() == "## Curriculum"
                continue
            if on and re.match(r"\s*\d+\.\s", ln):
                numbered += 1
            m = re.match(r"\s*(\d+)\.\s.*—\s*(\S+)\s*$", ln) if on else None
            if not m:
                continue
            matched += 1
            n, stem = m.group(1), unicodedata.normalize("NFC", m.group(2))
            if stem not in lessons:
                print(f"  #{n} BAD-STEM {stem!r}")
                continue
            for span in re.findall(r"`([^`]+)`", ln):
                toks = words(span)
                if not toks:
                    continue
                if all(spoken(t, stem) for t in toks):
                    counts["OK"] += 1
                    continue
                where = [s for s in lessons if s != stem and all(spoken(t, s) for t in toks)]
                missing = [t for t in toks if not spoken(t, stem)]
                v = "ELSEWHERE" if where else "UNSPOKEN"
                counts[v] += 1
                print(f"  #{n:>2} {v:9s} `{span}` missing-in-cited={missing}"
                      + (f" found-in={[w[:40] for w in where][:3]}" if where else ""))
        # A check that read nothing must not look like a clean one.
        print(f"  totals: {counts}  (curriculum lines read {matched}/{numbered}, spans {sum(counts.values())})")


if __name__ == "__main__":
    main(*sys.argv[1:])
