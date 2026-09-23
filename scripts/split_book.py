"""Split one book (.txt or .pdf) into one `<id>.transcript.txt` per section, for the book lane.

    .venv/bin/python scripts/split_book.py input/books/<book>.pdf --slug <slug> --dry-run
    .venv/bin/python scripts/split_book.py input/books/<book>.pdf --slug <slug>

Writes output/books/<slug>/<id>.transcript.txt plus chapters.json (ids and titles in book order),
which is what the digest brief (scripts/DIGEST-BRIEF.md) reads. The suffix is deliberate:
quote_check.py resolves a `— ch03` citation against ch03.transcript.txt, so book quotes get the
course gate unchanged.

Text (these rules reproduce the 2026-09-23 splits of the first three books byte for byte):
  - CRLF -> LF, and a run of blank lines collapses to one.
  - PDF: the text layer (pypdfium2), pages joined with "\\n". A PDFium U+FFFE between two word
    characters is a real hyphen and becomes "-"; any other U+FFFE stays and is counted.
  - A bilingual book (CJK on 20-80% of its lines) loses its CJK lines; --cjk keep|drop overrides.
Sections:
  - A heading is a line holding only a section word: `CHAPTER 7`, `Capítulo 7`, `INTRODUCTION`...
    A table of contents packs its entries close together, so a heading whose next heading-like line
    follows within DENSE_CHARS is a TOC entry, not a section. TOC entries supply the titles.
  - Everything before the first section is `front-matter`, a TOC there included. A TOC heading
    (Contents, Sumário) between two sections starts an omitted region that runs to the next one.
  - After the last chapter of the 1..N sequence, the first back-matter heading (Notes, Index,
    Acknowledgments, About the Author...) ends the book; --end-at can end it earlier.
It refuses (exit 2, writes nothing) when it can't trust the split: no chapter 1, a chapter out of
sequence, a front or end section in the wrong place or repeated, an ISBN inside the first or last
section (a copyright page or publisher ads leaked in), or an output folder that already holds chapters.
"""
from __future__ import annotations

import argparse
import bisect
import json
import pathlib
import re
import sys
import unicodedata
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[1]
DENSE_CHARS = 400        # a TOC entry's next heading-like line is this close (see mark_dense)
SHORT_SECTION = 500      # a section shorter than this is reported: a subheading read as a heading?
CJK = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")
PDFIUM_HYPHEN = re.compile(r"(?<=\w)\ufffe(?=\w)")  # same rule as image-to-markdown's img2md/reconcile.py
ISBN = re.compile(r"\bISBN\b|(?<!\d)97[89](?:[-\s]?\d){10}(?!\d)", re.I)

NUMBERED = {"chapter": r"chapter|cap[ií]tulo|cap\.", "part": r"part|parte"}
NAMED = {
    "foreword": r"foreword", "preface": r"preface|pref[aá]cio", "prologue": r"prologue|pr[oó]logo",
    "intro": r"introduction|introdu[çc][ãa]o", "conclusion": r"conclusion|conclus[ãa]o",
    "epilogue": r"epilogue|ep[ií]logo", "afterword": r"afterword|posf[aá]cio",
    "appendix": r"appendix|ap[êe]ndice|anexo",
}
FRONT = {"foreword", "preface", "prologue", "intro"}      # must come before Chapter 1
END = {"conclusion", "epilogue", "afterword", "appendix"}  # must come after the last chapter
BACK = (r"notes|endnotes|notas(?: finais)?|bibliography|bibliografia|references|refer[êe]ncias|index|"
        r"[íi]ndice remissivo|acknowledge?ments|agradecimentos|about the authors?|"
        r"sobre (?:o|a|os|as) autor(?:a|es|as)?")
TOC = r"contents|table of contents|sum[áa]rio|[íi]ndice"
WORD_NUMBERS = {w: i for i, w in enumerate(
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split(), 1)}
WORD_NUMBERS.update({w: i for i, w in enumerate(
    "um dois três quatro cinco seis sete oito nove dez onze doze treze catorze quinze dezesseis "
    "dezessete dezoito dezenove vinte".split(), 1)})
WORD_NUMBERS.update({"uma": 1, "duas": 2, "tres": 3, "quatorze": 14})


class Refusal(Exception):
    """The split can't be trusted; the message says what to fix."""


@dataclass
class Heading:
    line: int
    pos: int
    kind: str          # chapter | part | named | back | toc
    key: object        # int for chapter/part, an id for named, the line for back/toc
    form: str          # heading (alone on its line) | toc (number or name followed by a title)
    title: str | None
    dense: bool = False
    crowded: bool = False


@dataclass
class Section:
    id: str
    title: str
    first: int         # 0-based line index, inclusive
    last: int          # exclusive
    text: str


@dataclass
class Omitted:
    first: int
    last: int
    why: str
    chars: int


def roman(s):
    vals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
    total = prev = 0
    for ch in reversed(s):
        v = vals[ch]
        total, prev = (total - v, prev) if v < prev else (total + v, v)
    back, n = "", total
    for v, r in ((100, "c"), (90, "xc"), (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while n >= v:
            back, n = back + r, n - v
    return total if back == s else None


def number(tok):
    t = tok.casefold()
    if t.isdigit():
        return int(t)
    if t in WORD_NUMBERS:
        return WORD_NUMBERS[t]
    return roman(t) if re.fullmatch(r"[ivxlc]+", t) else None


def clean_title(t):
    return re.sub(r"[\s:\-–—]+$", "", t).strip()


def classify(line):
    """(kind, key, form, title) for a heading-like line, else None."""
    s = line.strip()
    if not s or len(s) > 160:
        return None
    for kind, words in NUMBERED.items():
        m = re.match(rf"^(?:{words})\s+(\S+?)[.:]?$", s, re.I)
        if m and len(s) <= 60 and (n := number(m.group(1))):
            return kind, n, "heading", None
        m = re.match(rf"^(?:{words})\s+(\S+?)(?:\s*[:.\-–—]\s*|\s+)(\S.*)$", s, re.I)
        if m and (n := number(m.group(1))):
            return kind, n, "toc", clean_title(m.group(2))
    for key, words in NAMED.items():
        m = re.match(rf"^(?:{words})(?:\s+([a-z]|\d{{1,2}}))?[.:]?$", s, re.I)
        if m and len(s) <= 60:
            return "named", key + (f"-{m.group(1).lower()}" if m.group(1) else ""), "heading", None
        m = re.match(rf"^(?:{words})\s*[:\-–—]\s*(\S.*)$", s, re.I)
        if m:
            return "named", key, "toc", clean_title(m.group(1))
    if re.match(rf"^(?:{BACK})[.:]?$", s, re.I):
        return "back", s, "heading", None
    if re.match(rf"^(?:{TOC})[.:]?$", s, re.I):
        return "toc", s, "heading", None
    return None


def normalize(pages, is_pdf, cjk="auto"):
    """Join raw page texts into the text the split works on; return (text, stats)."""
    stats = {"fffe_to_hyphen": 0, "fffe_left": 0, "cjk_lines_dropped": 0}
    pages = [p.replace("\r\n", "\n").replace("\r", "\n") for p in pages]
    if is_pdf:
        stats["fffe_to_hyphen"] = sum(len(PDFIUM_HYPHEN.findall(p)) for p in pages)
        pages = [PDFIUM_HYPHEN.sub("-", p) for p in pages]
        stats["fffe_left"] = sum(p.count("\ufffe") for p in pages)
    lines = [ln for p in pages for ln in p.split("\n") if ln.strip()]
    share = sum(1 for ln in lines if CJK.search(ln)) / max(1, len(lines))
    stats["cjk_line_share"] = round(share, 3)
    if cjk == "drop" or (cjk == "auto" and 0.2 <= share <= 0.8):
        kept = []
        for p in pages:
            ls = p.split("\n")
            stats["cjk_lines_dropped"] += sum(1 for ln in ls if CJK.search(ln))
            kept.append("\n".join(ln for ln in ls if not CJK.search(ln)))
        pages = kept
    text = "\n".join(pages)
    stats["blank_runs_collapsed"] = len(re.findall(r"\n{3,}", text))
    return re.sub(r"\n{3,}", "\n\n", text), stats


def read_book(path, cjk="auto"):
    path = pathlib.Path(path)
    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium  # only the PDF path needs it
        pdf = pdfium.PdfDocument(str(path))
        try:
            pages = [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
        finally:
            pdf.close()
        return normalize(pages, True, cjk)
    return normalize([path.read_text(encoding="utf-8-sig")], False, cjk)


def mark_dense(heads):
    """Two readings of "inside a table of contents".

    `dense` (two other heading-like lines within DENSE_CHARS, either side) picks the TOC lines
    that may lend a section its title. `crowded` (the NEXT heading-like line within DENSE_CHARS)
    decides whether a heading can start a section: a real heading is followed by its body, while
    a TOC entry is followed by the next entry. A two-sided test is wrong for that job, because a
    book's first heading often sits right after the TOC and would be counted as part of it.
    """
    pos = [h.pos for h in heads]
    for k, h in enumerate(heads):
        near = bisect.bisect_right(pos, h.pos + DENSE_CHARS) - bisect.bisect_left(pos, h.pos - DENSE_CHARS) - 1
        h.dense = near >= 2
        h.crowded = k + 1 < len(heads) and heads[k + 1].pos - h.pos <= DENSE_CHARS


def region(lines, a, b):
    return "\n".join(lines[a:b]).strip("\n") + "\n"


def label(line):
    return line.strip().split()[0].rstrip(".:").capitalize()


def fallback_title(lines, h):
    """The first wordy line under the heading, if it is short enough to be a title, not prose."""
    for ln in lines[h.line + 1:h.line + 6]:
        s = ln.strip()
        if s and re.search(r"\w", s):
            return s if len(s) <= 70 else None
    return None


def section_title(lines, h, toc_titles):
    lab = label(lines[h.line])
    if h.kind in ("chapter", "part"):
        t = toc_titles.get((h.kind, h.key)) or fallback_title(lines, h)
        return f"{lab} {h.key}: {t}" if t else f"{lab} {h.key}"
    t = toc_titles.get(("named", h.key.split("-")[0])) or fallback_title(lines, h)
    if t and t.lower().startswith("by "):
        return f"{lab} {t}"
    return f"{lab}: {t}" if t else lab


def isbn_line(lines, a, b):
    return next((i for i in range(a, b) if ISBN.search(lines[i])), None)


def context(lines, i, before=3):
    out, j = [], i - 1
    while j >= 0 and len(out) < before:
        if lines[j].strip():
            out.append(f"      L{j + 1}: {lines[j].strip()[:80]!r}")
        j -= 1
    return "\n".join(reversed(out))


def split(text, end_at=None, front_extra=None, ignore=()):
    """Plan the sections of a normalized book text. Raises Refusal when the plan can't be trusted."""
    lines = text.split("\n")
    starts, p = [], 0
    for ln in lines:
        starts.append(p)
        p += len(ln) + 1
    heads = [Heading(i, starts[i], *c) for i, ln in enumerate(lines)
             if ln.strip() not in ignore and (c := classify(ln))]
    mark_dense(heads)
    toc_titles = {}
    for h in heads:
        if h.form == "toc" and h.dense and h.title:
            toc_titles.setdefault((h.kind, h.key), h.title)
    cands = [h for h in heads if h.form == "heading" and (h.kind in ("back", "toc") or not h.crowded)]
    seen = "\n".join(f"      L{h.line + 1}: {lines[h.line].strip()[:60]!r} ({h.kind})" for h in cands[:40])

    expected, chapters, strays = 1, [], []
    for h in cands:
        if h.kind == "chapter":
            if h.key == expected:
                chapters.append(h)
                expected += 1
            else:
                strays.append(h)
    if not chapters:
        raise Refusal("no `Chapter 1` / `Capítulo 1` heading on a line of its own, outside a table "
                      f"of contents.\n    headings seen:\n{seen or '      none'}")
    last = chapters[-1]

    end, end_why = len(lines), "end of text"
    back = next((h for h in cands if h.kind == "back" and h.line > last.line), None)
    if back:
        end, end_why = back.line, f"back matter from {lines[back.line].strip()!r}"
    if end_at is not None:
        hit = next((i for i in range(last.line + 1, len(lines)) if lines[i].strip().startswith(end_at)), None)
        if hit is None:
            raise Refusal(f"--end-at {end_at!r}: no line after L{last.line + 1} "
                          f"({lines[last.line].strip()!r}) starts with it.")
        if hit < end:
            end, end_why = hit, f"--end-at {end_at!r}"

    problems = [f"L{h.line + 1} {lines[h.line].strip()!r}: chapter {h.key} is out of the 1..N sequence"
                for h in strays if h.line < end]
    named = [h for h in cands if h.kind in ("named", "part") and h.line < end]
    start = min([chapters[0].line] + [h.line for h in named])
    ids, used = {}, set()
    for h in named:
        base = h.key.split("-")[0] if h.kind == "named" else "part"
        if base in FRONT and h.line > chapters[0].line:
            problems.append(f"L{h.line + 1} {lines[h.line].strip()!r}: a {base} after Chapter 1")
        if base in END and h.line < last.line:
            problems.append(f"L{h.line + 1} {lines[h.line].strip()!r}: a {base} before the last chapter")
        sid = f"part{h.key}" if h.kind == "part" else h.key
        if sid in used and base == "appendix":
            k = 2
            while f"{sid}-{k}" in used:
                k += 1
            sid = f"{sid}-{k}"
        elif sid in used:
            problems.append(f"L{h.line + 1} {lines[h.line].strip()!r}: a second `{sid}` heading")
        used.add(sid)
        ids[h.line] = sid
    if problems:
        raise Refusal("the headings don't form a clean book structure:\n" +
                      "\n".join(f"    {p}" for p in problems) +
                      "\n    If a line above is a subheading, pass --ignore-heading '<the exact line>'."
                      f"\n    headings seen:\n{seen}")
    for h in chapters:
        ids[h.line] = f"ch{h.key:02d}"

    bounds = sorted([h for h in chapters] + named +
                    [h for h in cands if h.kind == "toc" and start < h.line < end], key=lambda h: h.line)
    sections, omitted = [], []
    front = region(lines, 0, start) if start > 0 else ""
    front_title = "Front matter (bibliographic use only)"
    if front_extra:
        first, lastp = front_extra
        a = next((i for i in range(end, len(lines)) if lines[i].strip().startswith(first)), None)
        b = next((i for i in range(a, len(lines)) if lines[i].strip().startswith(lastp)), None) if a is not None else None
        if a is None or b is None:
            raise Refusal(f"--front-extra: no block from a line starting {first!r} to one starting "
                          f"{lastp!r} in the omitted text after L{end}.")
        front = front.rstrip("\n") + "\n\n" + region(lines, a, b + 1)
        front_title = "Front matter + the copyright block from the end of the book (bibliographic use only)"
    if front.strip():
        sections.append(Section("front-matter", front_title, 0, start, front))
    for k, h in enumerate(bounds):
        nxt = bounds[k + 1].line if k + 1 < len(bounds) else end
        if h.kind == "toc":
            omitted.append(Omitted(h.line, nxt, f"table of contents {lines[h.line].strip()!r}",
                                   len(region(lines, h.line, nxt))))
            continue
        sections.append(Section(ids[h.line], section_title(lines, h, toc_titles), h.line, nxt,
                                region(lines, h.line, nxt)))
    if end < len(lines):
        omitted.append(Omitted(end, len(lines), end_why, len(region(lines, end, len(lines)))))

    body = [s for s in sections if s.id != "front-matter"]
    for s, edge in ((body[0], "first"), (body[-1], "last")):
        i = isbn_line(lines, s.first, s.last)
        if i is not None:
            hint = ("pass --end-at with the start of the first line that is NOT the book"
                    if edge == "last" else "check where the front matter really ends")
            raise Refusal(f"an ISBN sits inside the {edge} section `{s.id}` at L{i + 1}: "
                          f"{lines[i].strip()[:80]!r}\n    so a copyright page or publisher ads leaked into "
                          f"it; {hint}. The lines before it:\n{context(lines, i)}")
    warnings = [f"`{s.id}` is only {len(s.text)} chars: a subheading read as a heading?"
                for s in body if len(s.text) < SHORT_SECTION and not s.id.startswith("part")]
    warnings += [f"`{s.id}` contains an ISBN at L{i + 1}: {lines[i].strip()[:60]!r}" for s in body[1:-1]
                 if (i := isbn_line(lines, s.first, s.last)) is not None]
    fi = ISBN.search(front)
    tail = isbn_line(lines, end, len(lines))
    return {"sections": sections, "omitted": omitted, "warnings": warnings, "end_why": end_why,
            "front_isbn": front[max(0, fi.start() - 40):fi.end() + 25].replace("\n", " ") if fi else None,
            "tail_isbn": (tail, lines[tail].strip()) if tail is not None else None}


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def report(src, stats, plan, out_dir):
    print(f"split_book.py — {src.name}")
    print(f"  normalized: {stats}")
    print(f"  sections ({len(plan['sections'])}):")
    for s in plan["sections"]:
        print(f"    {s.id:<14} L{s.first + 1:>6}–L{s.last:<6} {len(s.text):>8,} chars  {s.title[:70]}")
    print("  omitted:" if plan["omitted"] else "  omitted: nothing")
    for o in plan["omitted"]:
        print(f"    L{o.first + 1:>6}–L{o.last:<6} {o.chars:>8,} chars  {o.why}")
    if plan["front_isbn"]:
        print(f"  front matter ISBN: …{plan['front_isbn']}…")
    else:
        print("  front matter ISBN: NONE", end="")
        if plan["tail_isbn"]:
            line, text = plan["tail_isbn"]
            print(f" — the omitted text has one at L{line + 1}: {text[:60]!r}. Pull its copyright block "
                  "in with --front-extra '<first line of the block>' '<the ISBN line>'.")
        else:
            print(" — the digest will report the ISBN as not printed.")
    for w in plan["warnings"]:
        print(f"  WARNING: {w}")
    print(f"  output: {out_dir}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book", help="input/books/<book>.txt or .pdf")
    ap.add_argument("--slug", help="output folder name (default: from the file name)")
    ap.add_argument("--title", help="book title for chapters.json (default: from the file name)")
    ap.add_argument("--out", default=str(ROOT / "output" / "books"), help="parent folder (default: output/books)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    ap.add_argument("--end-at", metavar="PREFIX", help="end the book at the first line after the last chapter that starts with PREFIX")
    ap.add_argument("--front-extra", nargs=2, metavar=("FIRST", "LAST"),
                    help="append the omitted block from the line starting FIRST to the line starting LAST to front-matter")
    ap.add_argument("--ignore-heading", action="append", default=[], metavar="LINE",
                    help="a line that looks like a heading but isn't one (exact text, repeatable)")
    ap.add_argument("--cjk", choices=("auto", "drop", "keep"), default="auto",
                    help="CJK lines: drop them in a bilingual book (auto), always, or never")
    args = ap.parse_args(argv)

    src = pathlib.Path(args.book)
    title = args.title or re.sub(r"\s*\(.*$", "", src.stem).strip()
    out_dir = pathlib.Path(args.out) / (args.slug or slugify(title))
    text, stats = read_book(src, args.cjk)
    try:
        plan = split(text, args.end_at, args.front_extra, set(args.ignore_heading))
    except Refusal as e:
        print(f"REFUSED — nothing written. {src.name}:\n  {e}", file=sys.stderr)
        return 2
    report(src, stats, plan, out_dir)
    if args.dry_run:
        print("DRY RUN — nothing written.")
        return 0
    if out_dir.exists() and any(out_dir.glob("*.transcript.txt")):
        print(f"REFUSED — {out_dir} already holds chapter files; packs may cite them. "
              "Move the folder away first if you mean to re-split.", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    for s in plan["sections"]:
        (out_dir / f"{s.id}.transcript.txt").write_text(s.text, encoding="utf-8")
    flags = {k: v for k, v in (("end_at", args.end_at), ("front_extra", args.front_extra),
                               ("ignore_heading", args.ignore_heading), ("cjk", args.cjk)) if v and v != "auto"}
    note = "Split by scripts/split_book.py. Omitted: " + ("; ".join(
        f"{o.why}, L{o.first + 1}–L{o.last} ({o.chars} chars)" for o in plan["omitted"]) or "nothing") + "."
    meta = {"title": title, "source_file": src.name, "note": note,
            "split": {"tool": "scripts/split_book.py", "flags": flags, "normalized": stats},
            "chapters": [{"id": s.id, "title": s.title, "chars": len(s.text)} for s in plan["sections"]]}
    (out_dir / "chapters.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {len(plan['sections'])} chapter files + chapters.json to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
