"""Run quote_check.py over a book folder, for digests as well as packs.

quote_check.quotes() only reads the `## Quotes worth keeping` section of a pack. A digest keeps its
candidate quotes nested under each chapter, so for digest.md every `- "…" — <id>` line is checked,
wherever it sits. Packs (`*.pack.md`) go through the unmodified section parser.

Book chapters are `<id>.transcript.txt` on purpose: that is the suffix quote_check resolves a
`— ch03` citation against, so book quotes get the course gate unchanged (book lane, 2026-09-23).

Usage: digest_quote_check.py <book_dir> [glob]   (default glob: digest.md)
"""
import pathlib
import re
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import quote_check  # noqa: E402

QUOTE_LINE = re.compile(r'^\s*[-*]\s*["“](.+?)["”]\s*(\(cleaned\))?\s*[—–]\s*(\S+)\s*$')
# A list item that OPENS like a quote. One QUOTE_LINE can't parse (a trailing note after the
# citation, a missing dash) is reported UNPARSED instead of being skipped: a gate that cannot
# see a quote would otherwise print nothing about it, which reads exactly like a pass.
QUOTE_LIKE = re.compile(r'^\s*[-*]\s*["“]')


def all_quote_lines(text):
    out = []
    for ln in text.splitlines():
        m = QUOTE_LINE.match(ln)
        if m:
            out.append({"raw": ln.strip(), "marker": "-", "text": m.group(1), "cleaned": bool(m.group(2)),
                        "cite": unicodedata.normalize("NFC", m.group(3))})
        elif QUOTE_LIKE.match(ln):
            out.append({"raw": ln.strip(), "marker": "UNPARSED"})
    return out


def check(book_dir, glob="digest.md"):
    """Print quote_check's verdicts for `glob` in `book_dir`.

    The digest parser is swapped in only for this call, so a later pack check in the same
    process still gets quote_check's own section parser.
    """
    if glob.endswith(".pack.md"):
        return quote_check.main(book_dir, glob)
    section_parser = quote_check.quotes
    quote_check.quotes = all_quote_lines
    try:
        return quote_check.main(book_dir, glob)
    finally:
        quote_check.quotes = section_parser


if __name__ == "__main__":
    check(*sys.argv[1:])
