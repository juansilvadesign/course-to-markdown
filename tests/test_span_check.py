"""Known-bad legs for the Curriculum attribution check (scripts/span_check.py).

The coverage gate proves every lesson HAS a Curriculum line; span_check asks whether each
line's backticked spans were spoken in the lesson it cites. It exists because a pack filed
lesson 10's decodeURIComponent and IAM-permission steps under lesson 09 and coverage passed
it (2026-09-18). Its first known-bad fixtures held real transcript text and died with a
session scratchpad; these legs run on a synthetic course, since this repo is public.

    .venv/bin/python -m unittest tests.test_span_check -v
"""
from __future__ import annotations

import ast
import contextlib
import io
import pathlib
import re
import tempfile
import unicodedata
import unittest

from scripts.span_check import main

LESSONS = {
    # "component" and "cache" live here on purpose: a check that accepts ANY matching word,
    # or that credits a span to a lesson holding only part of it, would be fooled.
    "09-upload-para-o-s3": "Nesta aula a gente cria o bucket e faz o upload do arquivo com uma presigned URL. "
                           "Cada component do formulário manda um arquivo, e o cache do navegador guarda a prévia.",
    # decode / URI / component are spoken apart, so only the camelCase split can join them.
    "10-permissoes-e-download": "Agora a gente ajusta a IAM policy do bucket e usa o decode no URI, um component "
                                "por vez, para ler o nome do arquivo.",
    # "get the user info": getUserInfo needs the camel split; `userinfo` needs the squashed text.
    "11-sessao-do-usuario": "Para ler o perfil, a gente chama get the user info no backend e guarda a sessão. "
                            "O user name vem junto.",
    # "API taxa" squashes to "...apitaxa...", which contains "pita": a 4-letter token must not match it.
    "12-configuração": "Aqui a gente faz a configuração do ambiente e usa a API taxa por hora. Cada ação conta.",
}


def check(curriculum, extra_sections=""):
    """Grade one synthetic pack; return (flags, totals, lines_read, numbered)."""
    with tempfile.TemporaryDirectory() as tmp:
        course = pathlib.Path(tmp)
        for stem, text in LESSONS.items():
            (course / f"{stem}.transcript.txt").write_text(text, encoding="utf-8")
        pack = course / "course.pack.v2.md"
        pack.write_text(f"## TL;DR\nSynthetic.\n{extra_sections}\n## Curriculum\n{curriculum}\n\n## See also\n- none\n",
                        encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(str(course), str(pack))
    text = out.getvalue()
    flags = re.findall(r"#\s*(\d+)\s+(BAD-STEM|ELSEWHERE|UNSPOKEN)\s+(.*)", text)
    totals = ast.literal_eval(re.search(r"totals: (\{.*?\})", text).group(1))
    read, numbered = map(int, re.search(r"curriculum lines read (\d+)/(\d+)", text).groups())
    return flags, totals, read, numbered


class KnownGood(unittest.TestCase):
    """The permit path: spans spoken in their own lesson pass, however they were spoken."""

    def test_spans_spoken_in_their_own_lesson_are_ok(self):
        flags, totals, read, numbered = check("\n".join([
            "1. Upload — `presigned` URL e `bucket`. Exercise: upload a file — 09-upload-para-o-s3",
            "2. Permissões — `IAM policy` e `decodeURIComponent`. Exercise: read the name — 10-permissoes-e-download",
            "3. Sessão — `getUserInfo`, `userinfo` e `const userName`. Exercise: read the profile — 11-sessao-do-usuario",
        ]))
        self.assertEqual(flags, [])
        self.assertEqual(totals, {"OK": 7, "ELSEWHERE": 0, "UNSPOKEN": 0})
        self.assertEqual((read, numbered), (3, 3))

    def test_a_stem_written_in_decomposed_accents_still_resolves(self):
        stem = unicodedata.normalize("NFD", "12-configuração")
        flags, totals, _, _ = check(f"1. Configuração — `configuração`. Exercise: set it up — {stem}")
        self.assertEqual(flags, [])
        self.assertEqual(totals["OK"], 1)

    def test_a_short_accented_word_is_graded_not_dropped(self):
        # Folding accents is what leaves `ação` a token at all; unfolded, it splits into scraps
        # too short to grade, and the span silently drops out of the count.
        flags, totals, _, _ = check("1. Configuração — `ação`. Exercise: none — 12-configuração")
        self.assertEqual((flags, totals["OK"]), ([], 1))

    def test_a_two_letter_span_is_not_graded(self):
        # Tokens under 3 letters are ignored: `S3` is spoken as "S três" and would false-alarm.
        flags, totals, _, _ = check("1. Upload — `S3`. Exercise: none — 09-upload-para-o-s3")
        self.assertEqual((flags, sum(totals.values())), ([], 0))

    def test_spans_outside_the_curriculum_are_not_graded(self):
        # A numbered, stem-ended line in another section: only the section decides it's skipped.
        flags, totals, _, _ = check("1. Upload — `bucket`. Exercise: upload — 09-upload-para-o-s3",
                                    extra_sections="\n## Frameworks / models\n1. Redis — `redisCache` — 11-sessao-do-usuario\n")
        self.assertEqual(flags, [])
        self.assertEqual(sum(totals.values()), 1)


class KnownBad(unittest.TestCase):
    """The legs that must FAIL. A gate that cannot fail is decoration."""

    def test_content_bleed_is_elsewhere_and_names_the_real_lesson(self):
        # The 2026-09-18 shape: lesson 10's step filed under lesson 09, which shares one word.
        flags, totals, _, _ = check("1. Upload — `decodeURIComponent`. Exercise: read the name — 09-upload-para-o-s3")
        self.assertEqual([(n, v) for n, v, _ in flags], [("1", "ELSEWHERE")])
        self.assertIn("10-permissoes-e-download", flags[0][2])
        self.assertEqual(totals["OK"], 0)

    def test_a_three_letter_acronym_is_graded(self):
        # The other half of the 2026-09-18 bleed: the IAM step, filed under the wrong lesson.
        flags, _, _, _ = check("1. Upload — `IAM`. Exercise: set permissions — 09-upload-para-o-s3")
        self.assertEqual([(n, v) for n, v, _ in flags], [("1", "ELSEWHERE")])
        self.assertIn("10-permissoes-e-download", flags[0][2])

    def test_a_span_no_single_lesson_spoke_is_unspoken(self):
        # "cache" was spoken in lesson 09 and "redis" nowhere: partial evidence is not a match.
        flags, _, _, _ = check("1. Sessão — `redisCache`. Exercise: cache the profile — 11-sessao-do-usuario")
        self.assertEqual([(n, v) for n, v, _ in flags], [("1", "UNSPOKEN")])

    def test_a_short_token_never_matches_across_a_word_boundary(self):
        flags, _, _, _ = check("1. Configuração — `pita`. Exercise: none — 12-configuração")
        self.assertEqual([(n, v) for n, v, _ in flags], [("1", "UNSPOKEN")])

    def test_a_stem_that_names_no_lesson_is_bad_stem(self):
        flags, totals, _, _ = check("1. Nada — `bucket`. Exercise: none — 99-nao-existe")
        self.assertEqual([(n, v) for n, v, _ in flags], [("1", "BAD-STEM")])
        self.assertEqual(sum(totals.values()), 0)

    def test_a_line_it_could_not_read_shows_in_the_ratio(self):
        # A check that read nothing must not look like a clean one.
        _, _, read, numbered = check("\n".join([
            "1. Upload — `bucket`. Exercise: upload — 09-upload-para-o-s3",
            "2. Permissões, with no lesson stem at the end",
        ]))
        self.assertEqual((read, numbered), (1, 2))


if __name__ == "__main__":
    unittest.main()
