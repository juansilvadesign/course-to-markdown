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

import unittest

from scripts.pack_fidelity import check_quote, normalize, resolve_cite

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
