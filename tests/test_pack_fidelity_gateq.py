"""Known-bad corpus for Gate Q's citation resolver (TASKS.md 5.7).

Gate Q could not tell ``UNCITED`` from "a citation it failed to PARSE": three
valid quotes were reported UNCITED while the tool's own ``found_in`` named the
exact lesson cited, because the agents buried the slug inside a descriptive
phrase and ``resolve_cite`` never tested ``folded in want``.

Teaching the resolver to find a slug ANYWHERE in the entry LOOSENS the gate, so
it needs its own known-bad legs -- the previous round's planted fixtures were
ad hoc and did not survive, which is why the re-proof had to be rebuilt from
scratch. These are the legs that must fail, kept executable so the next person
who touches the resolver re-proves it in one command.

    python3 -m unittest tests.test_pack_fidelity_gateq -v
"""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts.pack_fidelity import (check_quote, normalize, resolve_cite,
                                   resolve_ordinal)

# A synthetic course. `05-mocks` is a strict prefix of `05-mocks-avancados`,
# which is the shadowing case the longest-match rule exists for.
SAID_IN_MOCKS = ("Mocks sao spies e stubs ao mesmo tempo, e por isso voce "
                 "consegue observar os dois comportamentos")
SAID_IN_FAKES = ("Os fakes sao uma implementacao simplificada porem "
                 "funcional do contrato original")

TRANSCRIPTS = {
    "01-introducao": normalize("Nesta aula a gente monta o ambiente de testes"),
    "05-mocks": normalize(SAID_IN_MOCKS),
    "05-mocks-avancados": normalize("Aqui a gente aprofunda o uso de spies"),
    "12-fakes": normalize(SAID_IN_FAKES),
}


class BuriedSlugRepair(unittest.TestCase):
    """The defect this change exists to fix."""

    def test_slug_buried_mid_phrase_resolves(self):
        cite = ("a definicao-chave que separa o Mock classico (Sinon) do uso "
                "coloquial em Vitest/Jest (licao: `04-test-doubles/05-mocks`")
        self.assertEqual(resolve_cite(cite, TRANSCRIPTS), "05-mocks")

    def test_accented_slug_resolves_through_folding(self):
        # The real pack wrote the accented form; the stem carries the accents
        # too, so both sides must fold before they can meet.
        transcripts = {"01-criando-códigos-mais-testáveis": normalize("texto")}
        cite = "a tese do bloco inteiro (licao: `06-di/01-criando-codigos-mais-testaveis`"
        self.assertEqual(resolve_cite(cite, transcripts),
                         "01-criando-códigos-mais-testáveis")


class LooseningMustNotDisableTheGate(unittest.TestCase):
    """The legs that must still FAIL. A gate that cannot fail is decoration."""

    def test_misattribution_is_not_rescued(self):
        # Words live in 05-mocks; the citation names 12-fakes. The resolver
        # must report what was CITED, not what would make the pack look right.
        quote = {"text": SAID_IN_MOCKS,
                 "cite": "uma frase importante (licao: `03-modulo/12-fakes`"}
        result = check_quote(quote, TRANSCRIPTS)
        self.assertEqual(result["verdict"], "MISATTRIBUTED")
        self.assertEqual(result["resolved_cite"], "12-fakes")
        self.assertEqual(result["found_in"], ["05-mocks"])

    def test_invented_quote_is_not_laundered_by_a_valid_slug(self):
        # A correct citation must not make fabricated words locatable.
        quote = {"text": ("Este texto jamais foi dito por ninguem em lugar "
                          "algum deste curso inteiro"),
                 "cite": "licao: `04-test-doubles/05-mocks`"}
        self.assertEqual(check_quote(quote, TRANSCRIPTS)["verdict"], "NOT_FOUND")

    def test_resolution_is_blind_to_where_the_quote_was_found(self):
        # THE load-bearing leg. The cite names two lessons, one of which is the
        # host. Longest match wins and it is the NON-host, so the verdict stays
        # MISATTRIBUTED. Had the resolver consulted `hosts` to break the tie it
        # would return 05-mocks and manufacture a VERBATIM out of an ambiguous
        # citation -- and MISATTRIBUTED would become unreachable.
        quote = {"text": SAID_IN_MOCKS,
                 "cite": "compare `05-mocks` com `05-mocks-avancados`"}
        result = check_quote(quote, TRANSCRIPTS)
        self.assertEqual(result["resolved_cite"], "05-mocks-avancados")
        self.assertEqual(result["verdict"], "MISATTRIBUTED")


class MatchPrecision(unittest.TestCase):

    def test_longest_match_wins_over_its_own_prefix(self):
        cite = "veja a licao `05-mocks-avancados` para o caso dificil"
        self.assertEqual(resolve_cite(cite, TRANSCRIPTS), "05-mocks-avancados")

    def test_boundary_guard_blocks_an_embedded_lookalike(self):
        # `01-introducao` sits inside `101-introducao-antiga`, but it is not a
        # citation of it. Without the boundary guard this resolves.
        cite = "veja o arquivo 101-introducao-antiga do repositorio"
        self.assertIsNone(resolve_cite(cite, TRANSCRIPTS))

    def test_a_purely_descriptive_cite_stays_unresolved(self):
        # No slug, no ordinal -- genuinely unlocatable, and UNCITED is correct.
        # The loosening must not invent a resolution for it.
        cite = "mantra repetido sobre schema rigido"
        self.assertIsNone(resolve_cite(cite, TRANSCRIPTS))

    def test_absent_cite_stays_none(self):
        self.assertIsNone(resolve_cite(None, TRANSCRIPTS))


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------- ordinals

def _course(tmp: pathlib.Path, layout: dict[str, list[str]]) -> pathlib.Path:
    """Build output/ transcripts + the input/ manifest that orders them."""
    course = tmp / "output" / "jstack-lives" / "curso"
    keys = []
    for module, lessons in layout.items():
        for lesson in lessons:
            (course / module).mkdir(parents=True, exist_ok=True)
            (course / module / f"{lesson}.transcript.txt").write_text(
                "conteudo da aula", encoding="utf-8")
            keys.append(f"{module}/{lesson}")
    manifest = tmp / "input" / "jstack-lives" / "curso"
    manifest.mkdir(parents=True, exist_ok=True)
    (manifest / "manifest.json").write_text(
        json.dumps({"lessons": {k: {"status": "done"} for k in keys}}),
        encoding="utf-8")
    return course


# The real shape that broke the naive resolver: module 1 unnumbered, module 2
# numbered, so `01-…` exists but is NOT the first lesson.
MIXED = {"01-configurando": ["1000-o-que-e-e-por-que-usar",
                             "1000-configurando-a-identity"],
         "02-com-anexo": ["01-conhecendo-o-formato-mime",
                          "05-simplificando-com-o-nodemailer"]}


class OrdinalResolution(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _t(self, course):
        return {p.name.removesuffix(".transcript.txt"): normalize("conteudo da aula")
                for p in course.rglob("*.transcript.txt")}

    def test_mixed_numbering_REFUSES_rather_than_guessing(self):
        # THE load-bearing leg. Measured on the real corpus, a naive
        # "ordinal N -> prefix N" rule answered `01-conhecendo-o-formato-mime`
        # here; the quote actually lives in `1000-o-que-e-e-por-que-usar`.
        # A wrong answer flips a compliant quote to MISATTRIBUTED, so refusing
        # is the only safe outcome when position and prefix disagree.
        course = _course(self.tmp, MIXED)
        got = resolve_ordinal("Lição 1", course, self._t(course))
        self.assertIsNone(got)
        self.assertNotEqual(got, "01-conhecendo-o-formato-mime")

    def test_module_qualifier_disambiguates_a_repeated_number(self):
        course = _course(self.tmp, {"01-um": ["01-alpha", "02-beta"],
                                    "02-dois": ["01-gamma", "02-delta"]})
        t = self._t(course)
        self.assertEqual(resolve_ordinal("(Módulo 2, aula 01", course, t), "01-gamma")
        self.assertEqual(resolve_ordinal("(Módulo 1, aula 02", course, t), "02-beta")

    def test_unique_prefix_resolves_when_nothing_is_unnumbered(self):
        course = _course(self.tmp, {"01-um": ["01-alpha", "02-beta", "03-gamma"]})
        self.assertEqual(resolve_ordinal("lição 03", course, self._t(course)), "03-gamma")

    def test_repeated_number_without_a_module_qualifier_refuses(self):
        course = _course(self.tmp, {"01-um": ["07-alpha"], "02-dois": ["07-beta"]})
        self.assertIsNone(resolve_ordinal("aula 07", course, self._t(course)))

    def test_all_unnumbered_uses_manifest_POSITION_not_filename_sort(self):
        # Every lesson is `1000-`, so position is the only possible referent.
        # Filename sort would order these alphabetically -- manifest order is
        # the authority, and here the two disagree.
        course = _course(self.tmp, {"01-um": ["1000-zebra", "1000-alpha"]})
        t = self._t(course)
        self.assertEqual(resolve_ordinal("Lição 1", course, t), "1000-zebra")
        self.assertEqual(resolve_ordinal("Lição 2", course, t), "1000-alpha")

    def test_out_of_range_and_absent_ordinals_refuse(self):
        course = _course(self.tmp, {"01-um": ["1000-a", "1000-b"]})
        t = self._t(course)
        self.assertIsNone(resolve_ordinal("Lição 99", course, t))
        self.assertIsNone(resolve_ordinal("uma frase sem ordinal", course, t))

    def test_missing_manifest_degrades_to_refusal(self):
        course = _course(self.tmp, {"01-um": ["01-alpha"]})
        (self.tmp / "input" / "jstack-lives" / "curso" / "manifest.json").unlink()
        self.assertIsNone(resolve_ordinal("lição 01", course, self._t(course)))


class UnresolvedIsNotUncited(unittest.TestCase):
    """A reference we cannot machine-resolve is a contract nit; NO reference is
    the §5.4 FAIL. Conflating them is what made compliant packs read as a wave
    of fabrication alarms."""

    def test_absent_reference_is_UNCITED(self):
        quote = {"text": SAID_IN_MOCKS, "cite": None}
        self.assertEqual(check_quote(quote, TRANSCRIPTS)["verdict"], "UNCITED")

    def test_unresolvable_reference_is_UNRESOLVED_CITE(self):
        quote = {"text": SAID_IN_MOCKS, "cite": "mantra repetido sobre spies"}
        self.assertEqual(check_quote(quote, TRANSCRIPTS)["verdict"], "UNRESOLVED_CITE")
