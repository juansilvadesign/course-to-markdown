"""Known-good and known-bad legs for the 2026-09-18 gate REPORTING fix (TASKS.md 5.7).

Two gates printed `[ok]` over nothing. Gate S did it on 18 of 69 courses, where
no slug term reached the 0.8 share and the term list was empty. Gate Q did it on
35 packs whose quote entries opened with ">", "*" or "1.": the parser kept only
"-" lines, so a populated section parsed to zero quotes and read as a clean pass
while hiding two real MISATTRIBUTED.

The fix grades every marker, reports the non-dash ones as a contract nit,
reports a line that yields no quote instead of dropping it, and prints `skip`
when a gate cannot run. The widened parser READS more, so these legs pin both
directions: what it now reads must be graded like any "-" quote (it must still
be able to fail), and nothing it cannot read may come back as `ok`.

    python3 -m unittest tests.test_pack_fidelity_reporting -v
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from scripts.pack_fidelity import (audit_course, gate_q_status, gate_s_status,
                                   scan_quotes)

SAID_IN_MOCKS = ("Mocks sao spies e stubs ao mesmo tempo, e por isso voce "
                 "consegue observar os dois comportamentos")
SAID_IN_FAKES = ("Os fakes sao uma implementacao simplificada porem "
                 "funcional do contrato original")
NEVER_SAID = "Este texto jamais foi dito por ninguem em lugar algum deste curso inteiro"

LESSONS = {"05-mocks": SAID_IN_MOCKS, "12-fakes": SAID_IN_FAKES}


def _pack(quote_lines: list[str] | None) -> str:
    """A minimal pack; `None` omits the Quotes section entirely."""
    parts = ["---", "title: x", "---", "", "## TL;DR", "resumo", ""]
    if quote_lines is not None:
        parts += ["## Quotes worth keeping", *quote_lines, ""]
    parts += ["## See also", "- nada", ""]
    return "\n".join(parts)


class _Course(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)

    def audit(self, packs: dict[str, str], lessons: dict[str, str] = LESSONS,
              name: str = "curso-de-testes") -> dict:
        course = self.root / "output" / "jstack-lives" / name
        (course / "1000-conteudo").mkdir(parents=True)
        for stem, text in lessons.items():
            (course / "1000-conteudo" / f"{stem}.transcript.txt").write_text(
                text, encoding="utf-8")
        for fname, text in packs.items():
            (course / fname).write_text(text, encoding="utf-8")
        return audit_course(course, "*.pack.v2*.md", False)


class EveryMarkerIsRead(unittest.TestCase):

    def test_each_marker_in_the_corpus_parses_and_is_recorded(self):
        for line, marker in [(f'- "{SAID_IN_MOCKS}" — 05-mocks', "-"),
                             (f'*   "{SAID_IN_MOCKS}" — 05-mocks', "*"),
                             (f'> "{SAID_IN_MOCKS}" — 05-mocks', ">"),
                             (f'1. "{SAID_IN_MOCKS}" — 05-mocks', "N."),
                             (f'12) "{SAID_IN_MOCKS}" — 05-mocks', "N)")]:
            scan = scan_quotes(_pack([line]))
            self.assertEqual(len(scan["quotes"]), 1, line)
            self.assertEqual(scan["quotes"][0]["cite"], "05-mocks", line)
            self.assertEqual(scan["quotes"][0]["marker"], marker, line)
            self.assertEqual(scan["unparsed"], [], line)

    def test_cleaned_label_before_the_dash_keeps_the_bare_cite(self):
        scan = scan_quotes(_pack([f'- "{SAID_IN_MOCKS}" (cleaned) — 05-mocks']))
        self.assertEqual(scan["quotes"][0]["cite"], "05-mocks")

    def test_bare_blockquote_spacer_is_layout_not_an_entry(self):
        # The real shape in dominando-os-react-hooks: entries separated by ">".
        scan = scan_quotes(_pack([f'> "{SAID_IN_MOCKS}" — 05-mocks', ">",
                                  f'> "{SAID_IN_FAKES}" — 12-fakes']))
        self.assertEqual(len(scan["quotes"]), 2)
        self.assertEqual(scan["unparsed"], [])


class WidenedParserMustStillFail(_Course):
    """A quote behind a non-dash marker is graded like any other -- it can FAIL."""

    def test_misattribution_behind_a_blockquote_is_caught(self):
        # THE load-bearing leg: the exact defect the silent zero was hiding.
        res = self.audit({"curso.pack.v2.md": _pack([f'> "{SAID_IN_MOCKS}" — 12-fakes'])})
        self.assertEqual(res["gate_q"]["by_verdict"], {"MISATTRIBUTED": 1})
        self.assertEqual(res["gate_q"]["status"], "FLAG")

    def test_fabrication_behind_an_asterisk_is_caught(self):
        res = self.audit({"curso.pack.v2.md": _pack([f'*   "{NEVER_SAID}" — 05-mocks'])})
        self.assertEqual(res["gate_q"]["by_verdict"], {"NOT_FOUND": 1})
        self.assertEqual(res["gate_q"]["status"], "FLAG")


class NothingUnreadReadsOk(_Course):

    def test_clean_dash_pack_is_ok(self):
        # Known-good: the conforming case must stay green, or the flag is noise.
        res = self.audit({"curso.pack.v2.md": _pack([f'- "{SAID_IN_MOCKS}" — 05-mocks',
                                                      f'- "{SAID_IN_FAKES}" — 12-fakes'])})
        self.assertEqual(res["gate_q"]["by_verdict"], {"VERBATIM": 2})
        self.assertEqual(res["gate_q"]["status"], "ok")

    def test_verbatim_quotes_behind_a_non_dash_marker_still_flag(self):
        # Every quote is real and correctly cited; the marker alone is the nit.
        res = self.audit({"curso.pack.v2.md": _pack([f'> "{SAID_IN_MOCKS}" — 05-mocks'])})
        self.assertEqual(res["gate_q"]["by_verdict"], {"VERBATIM": 1})
        self.assertEqual(res["gate_q"]["status"], "FLAG")
        self.assertEqual(res["gate_q"]["packs"][0]["markers"], {">": 1})

    def test_truncated_entry_is_reported_not_dropped(self):
        # The real shape: 11 v1 packs end mid-quote with no closing mark.
        res = self.audit({"curso.pack.v2.md": _pack([f'- "{SAID_IN_MOCKS}" — 05-mocks',
                                                      '-   "A minha recomend'])})
        self.assertEqual(res["gate_q"]["total"], 1)
        self.assertEqual(res["gate_q"]["packs"][0]["unparsed"], ['-   "A minha recomend'])
        self.assertEqual(res["gate_q"]["status"], "FLAG")

    def test_missing_section_is_skip_not_ok(self):
        res = self.audit({"curso.pack.v2.md": _pack(None)})
        self.assertEqual(res["gate_q"]["total"], 0)
        self.assertEqual(res["gate_q"]["status"], "skip")

    def test_empty_section_is_a_note_not_a_pass(self):
        res = self.audit({"curso.pack.v2.md": _pack([])})
        self.assertEqual(res["gate_q"]["status"], "note")

    def test_shard_missing_its_section_flags_even_if_the_other_half_is_clean(self):
        res = self.audit({"curso.pack.v2-a.md": _pack([f'- "{SAID_IN_MOCKS}" — 05-mocks']),
                          "curso.pack.v2-b.md": _pack(None)})
        self.assertEqual(res["gate_q"]["by_verdict"], {"VERBATIM": 1})
        self.assertEqual(res["gate_q"]["status"], "FLAG")


class GateSSaysWhenItCannotRun(_Course):

    def test_empty_term_list_is_skip_not_ok(self):
        # Two topics, neither in >= 80% of lessons: nothing to track.
        lessons = {"01-alpha": "alpha " * 20, "02-alpha": "alpha " * 20,
                   "03-beta": "beta " * 20, "04-beta": "beta " * 20}
        res = self.audit({"c.pack.v2.md": _pack([])}, lessons, name="alpha-e-beta")
        self.assertEqual(res["gate_s"]["subject_terms"], [])
        self.assertEqual(res["gate_s"]["status"], "skip")

    def test_a_real_substitution_still_flags(self):
        # Known-bad: the Zustand->Svelte shape. The relabel must not disable FLAG.
        lessons = {f"0{i}-aula": "a gente usa zustand aqui " * 5 for i in range(1, 5)}
        lessons["05-configurando-a-devtools"] = "Aqui o Svelte guarda o estado. " * 6
        res = self.audit({"c.pack.v2.md": _pack([])}, lessons, name="zustand-na-pratica")
        self.assertEqual(res["gate_s"]["subject_terms"], ["zustand"])
        self.assertEqual(res["gate_s"]["status"], "FLAG")
        self.assertIn("Svelte x6", res["gate_s"]["findings"][0]["substitution_candidates"])

    def test_tracked_term_present_everywhere_is_ok(self):
        lessons = {f"0{i}-aula": "a gente usa zustand aqui" for i in range(1, 6)}
        res = self.audit({"c.pack.v2.md": _pack([])}, lessons, name="zustand-na-pratica")
        self.assertEqual(res["gate_s"]["status"], "ok")

    def test_status_functions_directly(self):
        self.assertEqual(gate_s_status({"subject_terms": [], "findings": []}), "skip")
        self.assertEqual(gate_s_status({"subject_terms": ["x"], "findings": [
            {"substitution_candidates": []}]}), "note")
        self.assertEqual(gate_q_status({"by_verdict": {}, "total": 0, "packs": []}), "note")


if __name__ == "__main__":
    unittest.main()
