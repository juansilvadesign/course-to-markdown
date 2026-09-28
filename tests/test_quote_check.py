"""Known-good and known-bad legs for the speaker-tag extension to quote_check.py's entry
parser (2026-09-28).

`quotes()` used to accept at most one bare `(cleaned)` tag between the closing quote and
the attribution dash. A course with more than one speaker needs to say WHO said a line, so
the parser now accepts one or more parenthetical tags -- `- "..." (Fulano) — stem` or
`- "..." (Sicrana) (cleaned) — stem` -- and records any tag that isn't exactly "(cleaned)"
as the entry's `speaker`. A tag may hold no parentheses or quote characters, so a quote can
never hide inside one and get silently sliced out of the parsed text.

    .venv/bin/python -m unittest tests.test_quote_check -v
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import tempfile
import unittest

from scripts import quote_check as qc

# Synthetic, public-repo-safe transcript: no real course, host, or participant names.
# "da dor do cliente" is spoken contiguously on purpose, so the EXACT leg starts on a
# clean word boundary rather than relying on a substring landing mid-word.
LESSON_TEXT = ("Fulano abre a aula dizendo que o posicionamento nasce da dor do cliente, "
               "nao do produto em si. Sicrana completa lembrando que o conteudo so vende "
               "quando resolve essa dor de verdade, com exemplos reais do dia a dia.")


def parse_one(line):
    """quotes() on a pack holding exactly one entry under the Quotes section."""
    [entry] = qc.quotes(f"## Quotes worth keeping\n{line}")
    return entry


def grade(quote_lines):
    """Run quote_check.main() over one synthetic pack; return the verdict lines, in order."""
    with tempfile.TemporaryDirectory() as tmp:
        course = pathlib.Path(tmp)
        (course / "01-abertura.transcript.txt").write_text(LESSON_TEXT, encoding="utf-8")
        pack = course / "workshop.pack.md"
        pack.write_text("## Quotes worth keeping\n" + "\n".join(quote_lines) + "\n",
                        encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            qc.main(str(course), "*.pack.md")
    return [ln.strip() for ln in out.getvalue().splitlines() if ln.strip().startswith("[")]


class TaggedEntryParsing(unittest.TestCase):
    """Direct checks on quotes() -- the dict shape a tagged entry produces."""

    def test_single_speaker_tag_is_recorded_and_not_cleaned(self):
        q = parse_one('- "da dor do cliente" (Fulano) — 01-abertura')
        self.assertEqual(q["marker"], "-")
        self.assertEqual(q["cite"], "01-abertura")
        self.assertEqual(q["speaker"], "Fulano")
        self.assertFalse(q["cleaned"])

    def test_speaker_tag_and_cleaned_tag_combine(self):
        q = parse_one('- "da dor do cliente" (Sicrana) (cleaned) — 01-abertura')
        self.assertEqual(q["speaker"], "Sicrana")
        self.assertTrue(q["cleaned"])

    def test_cleaned_only_tag_is_unchanged_from_before_tags_existed(self):
        # Regression: this exact shape worked before speaker tags existed.
        q = parse_one('- "da dor do cliente" (cleaned) — 01-abertura')
        self.assertTrue(q["cleaned"])
        self.assertIsNone(q["speaker"])

    def test_untagged_entry_is_unchanged_from_before_tags_existed(self):
        # Regression: the common case, no tags at all.
        q = parse_one('- "da dor do cliente" — 01-abertura')
        self.assertFalse(q["cleaned"])
        self.assertIsNone(q["speaker"])
        self.assertEqual(q["cite"], "01-abertura")

    def test_bare_bold_label_line_is_still_non_dash(self):
        # A pack section can carry a `**Name**` speaker-label line on its own; it must keep
        # failing the gate as a contract nit, not be swallowed as if it were a tagged entry.
        q = parse_one("**Fulano**")
        self.assertEqual(q["marker"], "NON-DASH")


class MalformedTag(unittest.TestCase):
    """The leg that must FAIL. A parenthesized span is not a clean tag just by looking like one."""

    def test_tag_holding_a_quote_character_is_unparsed_not_laundered(self):
        # If the tag pattern allowed a quote character inside, `("b")` would be accepted as a
        # tag and the outer quote text would be silently mis-sliced around it. Refusing to
        # match -- same as any other malformed dash line -- is the safe outcome.
        q = parse_one('- "a" ("b") — stem')
        self.assertEqual(q["marker"], "UNPARSED")


class TaggedEntryGrading(unittest.TestCase):
    """End-to-end: a tagged entry is graded against the transcript exactly like an untagged one."""

    def test_speaker_tagged_quote_matching_the_transcript_is_exact(self):
        v = grade(['- "da dor do cliente" (Fulano) — 01-abertura'])
        self.assertEqual(len(v), 1, v)
        self.assertTrue(v[0].startswith("[EXACT] (Fulano)"), v)

    def test_speaker_tagged_quote_with_one_word_changed_is_not_exact(self):
        # Same tag, same citation -- only "cliente" became "mercado". The tag must not
        # exempt the entry from the word-level check.
        v = grade(['- "da dor do mercado" (Fulano) — 01-abertura'])
        self.assertEqual(len(v), 1, v)
        self.assertTrue(v[0].startswith("[NOT-EXACT]"), v)


if __name__ == "__main__":
    unittest.main()
