"""Known-bad legs for the book lane's digest quote gate (scripts/digest_quote_check.py).

A book digest keeps its candidate quotes nested under each chapter, so the gate reads every
`- "…" — <id>` line wherever it sits and grades it with quote_check's exact-substring rules
against `<id>.transcript.txt`. The first version of these legs lived in a session scratchpad
and died with it; these are the executable replacement. The chapter text is synthetic on
purpose: this repo is public, and book text never enters it.

    .venv/bin/python -m unittest tests.test_digest_quote_check -v
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import tempfile
import unicodedata
import unittest

from scripts import digest_quote_check as dqc

CHAPTERS = {
    "ch01": ("The first rule of the workshop is simple: measure twice and cut once, because "
             "wood does not grow back. Everything else in this chapter follows from that habit."),
    "ch02": ("Nenhuma produção começa sem direção. Quem planeja a semana inteira no domingo "
             "chega na segunda com a cabeça leve e as mãos livres para o trabalho que importa."),
    "ch03": ("A good bench holds the work still. A sharp chisel removes only what you ask it "
             "to remove. A clean floor keeps the offcuts from hiding the pencil you just dropped."),
}


def verdicts(digest_lines, glob="digest.md", extra_files=None):
    """Grade a synthetic book folder; return only the verdict lines, in order."""
    with tempfile.TemporaryDirectory() as tmp:
        book = pathlib.Path(tmp)
        for cid, text in CHAPTERS.items():
            (book / f"{cid}.transcript.txt").write_text(text, encoding="utf-8")
        (book / "digest.md").write_text("\n".join(digest_lines) + "\n", encoding="utf-8")
        for name, text in (extra_files or {}).items():
            (book / name).write_text(text, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            dqc.check(str(book), glob)
    return [ln.strip() for ln in out.getvalue().splitlines() if ln.strip().startswith("[")]


class KnownGood(unittest.TestCase):
    """The permit path: a real quote passes wherever it sits in the digest."""

    def test_quote_nested_deep_under_a_chapter_is_graded(self):
        v = verdicts(["## Chapters", "### ch01 — Rule one", "- **Candidate quotes (2–4):**",
                      '      - "measure twice and cut once, because wood does not grow back" — ch01'])
        self.assertEqual(len(v), 1)
        self.assertTrue(v[0].startswith("[EXACT]") and v[0].endswith("— ch01"), v)

    def test_curly_quotes_and_decomposed_accents_still_match(self):
        said = "Quem planeja a semana inteira no domingo chega na segunda com a cabeça leve"
        v = verdicts([f'- “{unicodedata.normalize("NFD", said)}” — ch02'])
        self.assertTrue(v[0].startswith("[EXACT]"), v)

    def test_cleaned_marker_is_carried_into_the_verdict(self):
        v = verdicts(['- "measure twice and cut once" (cleaned) — ch01'])
        self.assertTrue(v[0].startswith("[EXACT] (cleaned)"), v)


class KnownBad(unittest.TestCase):
    """The legs that must FAIL. A gate that cannot fail is decoration."""

    def test_misattributed_quote_is_named_with_its_real_chapter(self):
        v = verdicts(['- "A sharp chisel removes only what you ask it to remove." — ch01'])
        self.assertTrue(v[0].startswith("[ELSEWHERE]"), v)
        self.assertIn("ch03", v[0])

    def test_inserted_word_is_flagged_as_pack_only(self):
        v = verdicts(['- "measure twice and always cut once, because wood does not grow back" — ch01'])
        self.assertTrue(v[0].startswith("[NOT-EXACT]"), v)
        self.assertIn("PACK-ONLY-WORDS", v[0])

    def test_stitched_quote_is_flagged_by_its_interior_gap(self):
        v = verdicts(['- "A good bench holds the work still. A clean floor keeps the offcuts from '
                      'hiding the pencil" — ch03'])
        self.assertTrue(v[0].startswith("[NOT-EXACT]"), v)
        self.assertIn("LONG-INTERIOR-GAP", v[0])
        self.assertNotIn("PACK-ONLY-WORDS", v[0])

    def test_fabricated_quote_is_not_located(self):
        v = verdicts(['- "Every craftsman should buy the most expensive saw they can afford" — ch01'])
        self.assertTrue(v[0].startswith("[NOT-EXACT]"), v)
        self.assertIn("NOT-LOCATED", v[0])

    def test_citation_to_a_missing_chapter_is_bad_cite(self):
        v = verdicts(['- "measure twice and cut once" — ch99'])
        self.assertTrue(v[0].startswith("[BAD-CITE]"), v)

    def test_quote_line_the_parser_cannot_read_is_reported_not_skipped(self):
        v = verdicts(["- \"measure twice and cut once\" — ch01 (the book's motto)"])
        self.assertEqual(len(v), 1, "a malformed quote line vanished from the report")
        self.assertTrue(v[0].startswith("[UNPARSED]"), v)


class PackGlobKeepsTheSectionParser(unittest.TestCase):

    PACK = "\n".join([
        "## Core ideas",
        '- "A sharp chisel removes only what you ask it to remove." — ch01',
        "## Quotes worth keeping",
        '- "measure twice and cut once, because wood does not grow back" — ch01',
    ])

    def test_pack_is_graded_on_its_quotes_section_only(self):
        v = verdicts([], glob="*.pack.md", extra_files={"book.pack.md": self.PACK})
        self.assertEqual(len(v), 1, v)
        self.assertTrue(v[0].startswith("[EXACT]"), v)

    def test_digest_parser_is_restored_after_a_digest_run(self):
        section_parser = dqc.quote_check.quotes
        verdicts(['- "measure twice and cut once" — ch01'])
        self.assertIs(dqc.quote_check.quotes, section_parser)


if __name__ == "__main__":
    unittest.main()
