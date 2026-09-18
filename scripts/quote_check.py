"""Independent quote check (second instrument beside pack_fidelity.py Gate Q).

For each dash-marked entry in `## Quotes worth keeping`:
  EXACT      -> the quote (whitespace-collapsed, NFC, case-folded) is a substring of the CITED transcript
  ELSEWHERE  -> not in the cited lesson, but exact in ANOTHER lesson of the course (misattribution)
  NOT-EXACT  -> best word-window alignment in the cited lesson, with the word-level edit script,
                so a human can see whether edits are deletions (disfluency/boundary) or INSERTIONS
                (words the speaker never said -- the synthesized-quote failure).
  NO-CITE / BAD-CITE -> the citation is missing or names no transcript in the course.

Usage: quote_check.py <course_dir> [pack_glob]
"""
import difflib
import pathlib
import re
import sys
import unicodedata


def norm(s):
    s = unicodedata.normalize("NFC", s).casefold()
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", s).strip()


def words(s):
    return re.findall(r"[\w'-]+", norm(s))


def quotes(pack_text):
    out, on = [], False
    for ln in pack_text.splitlines():
        if ln.startswith("## "):
            on = ln.strip() == "## Quotes worth keeping"
            continue
        if not on or not ln.strip():
            continue
        s = ln.strip()
        if not s.startswith("- "):
            out.append({"raw": s, "marker": "NON-DASH"})
            continue
        m = re.match(r'-\s*["“](.+?)["”]\s*(\(cleaned\))?\s*(?:[—–]\s*(\S+))?\s*$', s)
        if not m:
            out.append({"raw": s, "marker": "UNPARSED"})
            continue
        out.append({"raw": s, "marker": "-", "text": m.group(1), "cleaned": bool(m.group(2)),
                    "cite": unicodedata.normalize("NFC", m.group(3)) if m.group(3) else None})
    return out


def best_window(qw, tw):
    """Window of the transcript that explains the MOST quote words (then the smallest window).

    Optimising SequenceMatcher.ratio() instead is wrong: ratio rewards a short window, so a
    span with a few dropped fillers loses to a truncated window that leaves quote words
    unmatched -- which then read as PACK-ONLY (invented) words. Sizes are a CONTINUOUS range:
    a gap in the range (the first version skipped n+5) forces exactly that failure.
    """
    n = len(qw)
    best = (-1, 0, 0, 0)  # (matched, -size, i, size)
    for size in range(max(1, n - 3), n + 16):
        for i in range(0, max(1, len(tw) - size + 1)):
            win = tw[i:i + size]
            sm = difflib.SequenceMatcher(None, qw, win, autojunk=False)
            m = sum(b.size for b in sm.get_matching_blocks())
            key = (m, -size)
            if key > best[:2]:
                best = (m, -size, i, size)
    m, _, i, size = best
    return m, i, size


def main(course, glob="*.pack.v2*.md"):
    course = pathlib.Path(course)
    trs = {unicodedata.normalize("NFC", p.name.removesuffix(".transcript.txt")): p
           for p in course.rglob("*.transcript.txt")}
    tnorm = {k: norm(p.read_text(encoding="utf-8")) for k, p in trs.items()}
    for pack in sorted(course.glob(glob)):
        print(f"=== {pack.name}")
        for q in quotes(pack.read_text(encoding="utf-8")):
            if q["marker"] != "-":
                print(f"  [{q['marker']}] {q['raw'][:140]}")
                continue
            qt, cite = norm(q["text"]), q["cite"]
            tag = " (cleaned)" if q["cleaned"] else ""
            if not cite:
                print(f"  [NO-CITE]{tag} \"{q['text'][:90]}\"")
                continue
            if cite not in tnorm:
                print(f"  [BAD-CITE]{tag} cite={cite!r}")
                continue
            if qt in tnorm[cite]:
                print(f"  [EXACT]{tag} {len(qt.split())}w — {cite}")
                continue
            elsewhere = [k for k, t in tnorm.items() if qt in t and k != cite]
            if elsewhere:
                print(f"  [ELSEWHERE]{tag} cited {cite} but exact in {elsewhere}")
                continue
            qw, tw = words(q["text"]), words(trs[cite].read_text(encoding="utf-8"))
            matched, i, size = best_window(qw, tw)
            win = tw[i:i + size]
            sm = difflib.SequenceMatcher(None, qw, win, autojunk=False)
            r = sm.ratio()
            if matched == len(qw) and size == len(qw):
                print(f"  [WORD-EXACT]{tag} {len(qw)}w, punctuation/case-only difference — {cite}")
                continue
            # a = pack words, b = transcript window.  'delete' = words ONLY IN THE PACK (speaker never
            # said them here); 'insert' = transcript words the pack DROPPED; 'replace' = both.
            edits = []
            for op, a1, a2, b1, b2 in sm.get_opcodes():
                if op == "equal":
                    continue
                label = {"delete": "PACK-ONLY", "insert": "DROPPED", "replace": "CHANGED"}[op]
                edits.append(f"{label}: pack{qw[a1:a2]} transcript{win[b1:b2]}")
            pack_only = sum(a2 - a1 for op, a1, a2, b1, b2 in sm.get_opcodes() if op in ("delete", "replace"))
            # The window is minimal, so every DROPPED run is INTERIOR. Disfluency cleanup drops 1-3
            # words; a long interior run means two spans were joined (a stitched quotation).
            gap = max([b2 - b1 for op, a1, a2, b1, b2 in sm.get_opcodes() if op in ("insert", "replace")] or [0])
            flags = []
            if pack_only:
                flags.append("PACK-ONLY-WORDS")
            if gap >= 5:
                flags.append(f"LONG-INTERIOR-GAP({gap})")
            if matched < 0.6 * len(qw):
                flags.append("NOT-LOCATED")
            print(f"  [NOT-EXACT]{tag} ratio={r:.3f} matched={matched}/{len(qw)} pack-only-words={pack_only} "
                  f"max-dropped-run={gap} {' '.join(flags)} — {cite}")
            for e in edits:
                print(f"      {e}")


if __name__ == "__main__":
    main(*sys.argv[1:])
