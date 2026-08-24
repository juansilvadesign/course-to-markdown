#!/usr/bin/env python3
"""Fidelity evidence for Stage-2 packs (TASKS.md phase 5.4).

Phase 5.3's ``pack_coverage.py`` proves no lesson was silently DROPPED. It says
nothing about whether the body is faithful, and it cannot: a consistency gate
compares a pack against itself. This script gathers the evidence a human needs
to answer the correctness question, against the only artifact that saw 100% of
every course -- the transcripts.

Why not diff v2 against v1
--------------------------
v1 was written by a compiler that read a median 37% of each course, and 7 of the
19 v1 packs are truncated stubs of 358-1286 bytes. Where v2 and v1 agree, that
agreement covers only the slice v1 saw -- it corroborates the partiality, not the
pack. v1 is still worth reading, but only for the narrower question "did v2 keep
what v1 got right", which ``--v1-diff`` reports separately.

THE THREE GATES
---------------
Gate Q (quote provenance).  Every entry under ``## Quotes worth keeping`` claims
    to be something a human said. That is mechanically checkable: the words are
    either in a transcript or they are not. Separates NOT_FOUND (a fabrication
    candidate) from MISATTRIBUTED (right words, wrong lesson) because those are
    different defects with very different severity.

Gate S (subject-term dropout).  Catches the substitution class, which is the one
    corruption a v1/v2 diff structurally cannot see: a transcript that renders
    "Zustand" as "Svelte" reads perfectly and diffs clean. Its signature is not
    in the pack, it is in the transcript -- the course's own subject term appears
    in every lesson except one. Flags that lesson and lists the capitalized terms
    unique to it as the substitution candidates.

Gate T (token measurement).  Reports each pack's measured token estimate. 27 of
    29 v2 packs exceeded course.md's old ~2k cap, which was evidence the cap was
    mis-set for these lives rather than 27 agents misjudging. RESOLVED 2026-08-24:
    the cap is now ~3.5k, the corpus's measured p90, and both the verifier and
    these scripts count chars/3.7 (they previously disagreed by a median 1.42x).
    RECORDED, NEVER GRADED -- an overage does not fail a pack here.

WHAT THIS PROVES AND WHAT IT DOES NOT
-------------------------------------
A green Gate Q proves the quotes were spoken, not that the pack's ANALYSIS is
sound. A green Gate S proves no lesson dropped its subject term, not that the
transcript is clean -- it samples one failure shape out of many. Nothing here
promotes a pack. The verdict is a human's (phase 5.4).

Usage
-----
    .venv/bin/python scripts/pack_fidelity.py output/jstack-lives/<course>
    .venv/bin/python scripts/pack_fidelity.py output/jstack-lives/<course> --v1-diff
    .venv/bin/python scripts/pack_fidelity.py output/jstack-lives --all --json report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

# Shared with pack_coverage.py -- keep in step if either moves.
TOKEN_CAP = 3500
CHARS_PER_TOKEN = 3.7

# A quote fragment shorter than this cannot discriminate; it will match by luck.
MIN_FRAGMENT_CHARS = 25

# A slug token must reach this share of lessons before its ABSENCE from one is
# a signal rather than noise. At 0.5 a 25-lesson course flags its own setup
# lesson for not saying "login", which is unremarkable and buries the real hit.
SUBJECT_TERM_MIN_SHARE = 0.8

# A substitution candidate must be REPEATED in the lesson. The documented case
# says "Svelte" 6 times; incidental tooling mentioned once ("Autoprefixer") is
# the noise this threshold removes.
MIN_CANDIDATE_REPEATS = 3

# Word-sequence similarity above which a missing fragment counts as a rewording
# of a real passage rather than an invention. Calibrated against three verified
# cases (a pluralised verb, a fixed misspeak, a removed stutter) and one planted
# fabrication, which scores far below it.
REWORD_SIMILARITY = 0.6

# Compilers elide with [...], [�], a bare ..., or a bare �. Missing the BARE
# forms cost a full false-positive round: 5 quotes were reported NOT_FOUND (i.e.
# fabricated) when both of their fragments were verbatim in the transcript, one
# sentence apart. An alarming false positive reads as diligence -- be generous
# about what counts as an elision, and let MIN_FRAGMENT_CHARS carry the rigor.
ELISION = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]|\(\s*(?:\.\.\.|…)\s*\)|\.{3,}|…")

# Square brackets do TWO opposite jobs in these packs and conflating them costs
# a false fabrication report either way:
#   "[...]"        -> text was REMOVED, so the sides are not contiguous (split)
#   "[o índice]"   -> text was ADDED for clarity and was never spoken, so the
#                     sides ARE contiguous once it is dropped (remove)
# Treating an insertion as quoted speech makes the fragment unmatchable, which
# reads as an invented quote. Two of the four NOT_FOUND hits in the 19-course
# run were exactly this.
INSERTION = re.compile(r"\[[^\]\n]*\]")
_SPLIT_SENTINEL = "\x00"

# Course-slug words that carry no subject signal.
SLUG_STOPWORDS = {
    "a", "as", "ao", "aos", "com", "como", "da", "das", "de", "do", "dos", "e",
    "em", "entendendo", "introducao", "na", "nas", "no", "nos", "o", "os",
    "para", "por", "que", "se", "sem", "um", "uma", "the", "and", "of", "to",
    "in", "on", "criando", "utilizando", "usando", "implementando", "vamos",
    "configurando", "sao", "nossa", "nosso", "seus", "suas", "conteudo",
    "melhor", "minha", "opiniao", "pratica", "certo", "jeito", "falar",
}

# Capitalized words that are prose, not product names -- Gate S noise floor.
NOT_A_PRODUCT = {
    "Bom", "Entao", "Então", "Agora", "Aqui", "Beleza", "Certo", "Vamos", "Ola",
    "Olá", "Isso", "Esse", "Essa", "Este", "Esta", "Mas", "Porque", "Quando",
    "Como", "Onde", "Qual", "Quais", "Para", "Por", "Com", "Sem", "Depois",
    "Antes", "Legal", "Perfeito", "Show", "Massa", "Tipo", "Tudo", "Nao", "Não",
    "Sim", "Ai", "Aí", "Ah", "Oh", "Ok", "Ta", "Tá", "Ne", "Né", "Pronto",
    "Primeiro", "Segundo", "Terceiro", "Ultimo", "Último", "Galera", "Pessoal",
    "Bem", "Muito", "Cada", "Toda", "Todo", "Todos", "Todas", "Outro", "Outra",
}


def fold(text: str) -> str:
    """Accent-strip + lowercase. FOR MATCHING ONLY, never for output."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Fold, then flatten every non-alphanumeric run to one space.

    Punctuation and quote style are exactly what a transcriber varies, so
    matching through them is the point -- the question is "was this said", not
    "was this typeset identically".
    """
    return re.sub(r"[^a-z0-9]+", " ", fold(text)).strip()


def read_section(pack_text: str, heading: str) -> list[str]:
    """Return the lines of one ``## Heading`` section, exclusive of the heading."""
    out: list[str] = []
    inside = False
    for line in pack_text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line.strip().lower() == heading.strip().lower()
            continue
        if inside:
            out.append(line)
    return out


def load_transcripts(course_dir: Path) -> dict[str, str]:
    """Map lesson stem -> normalized transcript text."""
    transcripts: dict[str, str] = {}
    for path in sorted(course_dir.rglob("*.transcript.txt")):
        stem = path.name.removesuffix(".transcript.txt")
        transcripts[stem] = normalize(path.read_text(encoding="utf-8", errors="replace"))
    return transcripts


def load_transcripts_raw(course_dir: Path) -> dict[str, str]:
    """Map lesson stem -> raw transcript text (Gate S needs original casing)."""
    return {
        p.name.removesuffix(".transcript.txt"): p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(course_dir.rglob("*.transcript.txt"))
    }


# ---------------------------------------------------------------- Gate Q

def split_quote(text: str) -> list[str]:
    """Normalized fragments of a quote, honouring elisions and insertions.

    Elisions break the quote into pieces that must each be found; insertions are
    editorial and are simply dropped, leaving the surrounding words contiguous.
    """
    t = ELISION.sub(_SPLIT_SENTINEL, text)
    t = INSERTION.sub(" ", t)
    return [normalize(part) for part in t.split(_SPLIT_SENTINEL)]


def parse_quotes(pack_text: str) -> list[dict]:
    """Pull (text, cited lesson) pairs out of ``## Quotes worth keeping``."""
    quotes = []
    for line in read_section(pack_text, "## Quotes worth keeping"):
        line = line.strip()
        if not line.startswith("-"):
            continue
        body = line.lstrip("-").strip()
        # The closing quote is the one followed by the attribution dash or the
        # end of the line -- NOT simply the last quote character present. A
        # greedy match swallows an attribution that itself contains quotes
        # (e.g. ... — lesson 08, *Title* (transcript truncates it as "setVal"))
        # and then reports the citation text as an unquotable fragment.
        m = re.match(r"[\"“”](.+?)[\"“”]\s*(?=[—–]|$)", body)
        if not m:
            m = re.search(r"[\"“”](.+)[\"“”]", body)
        if not m:
            continue
        text = m.group(1)
        tail = body[m.end():]
        cite = None
        cm = re.search(r"[—–-]\s*(.+?)\s*$", tail)
        if cm:
            cite = cm.group(1).strip().strip("().")
        quotes.append({"text": text, "cite": cite})
    return quotes


def best_fuzzy_window(fragment: str, transcripts: dict[str, str]) -> dict:
    """Find the transcript passage a missing fragment most nearly matches.

    Turns a bare NOT_FOUND into actionable evidence, and it must be FUZZY rather
    than prefix-based: the real divergences in this corpus are a pluralised verb
    or a removed stutter, which break an exact prefix at word two while leaving
    the passage obviously the same sentence. A prefix test called all three of
    those fabrications.

    Anchors on the fragment's rarest word, then scores word-sequence similarity
    over a window around each occurrence. Returns the best match with the actual
    transcript text, so a human compares passages instead of grepping.
    """
    words = fragment.split()
    if not words:
        return {"ratio": 0.0, "lesson": None, "excerpt": ""}

    # Corpus frequency, so we anchor on the most discriminating word. Counted
    # over STEMS for the same reason the comparison is stemmed -- anchoring on
    # an exact inflected form never visits the lesson holding the other form.
    freq = Counter()
    tokenized = {}
    for stem, body in transcripts.items():
        toks = body.split()
        tokenized[stem] = toks
        freq.update({t[:6] for t in toks})
    # The anchor must actually OCCUR, or there is no window to score. A missing
    # plural ("idempotentes") is exactly the word most likely to be absent, and
    # it is also the rarest -- so anchoring on the rarest word unconditionally
    # scores the very cases this function exists to explain as 0.0.
    present = [w for w in words if freq.get(w[:6], 0)]
    if not present:
        return {"ratio": 0.0, "lesson": None, "excerpt": ""}
    anchor = min(present, key=lambda w: (freq[w[:6]], -len(w)))[:6]

    span = max(len(words), 8)
    best = {"ratio": 0.0, "lesson": None, "excerpt": ""}
    for stem, toks in tokenized.items():
        for i, tok in enumerate(toks):
            if tok[:6] != anchor:
                continue
            lo, hi = max(0, i - span), min(len(toks), i + span)
            window = toks[lo:hi]
            # Compare STEMS, so Portuguese inflection does not read as invention.
            # "sejam idempotentes" vs the spoken "seja idempotente" is a two-word
            # fragment in which BOTH words are inflected differently -- an exact
            # word comparison scores it 0 and reports a real quote as fabricated.
            sm = SequenceMatcher(None, [w[:6] for w in words],
                                 [w[:6] for w in window])
            blocks = [b for b in sm.get_matching_blocks() if b.size]
            # Score COVERAGE OF THE FRAGMENT, not similarity to the window. The
            # window is deliberately wider than the fragment, so a symmetric
            # ratio punishes a perfect match for the context around it.
            matched = sum(b.size for b in blocks)
            ratio = matched / len(words)
            if ratio <= best["ratio"]:
                continue
            if blocks:
                s = max(0, blocks[0].b - 3)
                e = min(len(window), blocks[-1].b + blocks[-1].size + 3)
                excerpt = " ".join(window[s:e])
            else:
                excerpt = " ".join(window)
            best = {"ratio": round(ratio, 3), "lesson": stem, "excerpt": excerpt}
    return best


def resolve_cite(cite: str | None, transcripts: dict[str, str]) -> str | None:
    """Match a citation to a lesson stem.

    Citations come in two shapes: the filename slug (``07-gerando-o-client``)
    and the markdown-italicised lesson TITLE (``*Gerando o Client Secret*``).
    Matching only the first shape mislabels every pack that uses the second.
    """
    if not cite:
        return None
    want = fold(cite.strip().strip("*_ ").strip())
    if not want:
        return None
    for stem in transcripts:
        folded = fold(stem)
        if folded.startswith(want) or want.startswith(folded) or want in folded:
            return stem
    # Title form: drop the numeric prefix from the stem and compare word sets.
    want_words = {w for w in re.split(r"[^a-z0-9]+", want) if len(w) > 2}
    if not want_words:
        return None
    best, best_score = None, 0.0
    for stem in transcripts:
        stem_words = {w for w in re.split(r"[^a-z0-9]+", fold(stem)) if len(w) > 2}
        stem_words.discard("transcript")
        if not stem_words:
            continue
        score = len(want_words & stem_words) / len(want_words)
        if score > best_score:
            best, best_score = stem, score
    return best if best_score >= 0.6 else None


def check_quote(quote: dict, transcripts: dict[str, str]) -> dict:
    """Locate a quote's fragments in the corpus and grade the attribution."""
    fragments = [f for f in split_quote(quote["text"]) if f]
    if not fragments:
        return {**quote, "verdict": "EMPTY", "found_in": [], "weak": True,
                "resolved_cite": None, "missing_fragments": [], "near_miss": None}

    # Elision splits a quote into smaller pieces, which makes matching EASIER.
    # If no piece is long enough to discriminate, a match is luck, not evidence.
    weak = max(len(f) for f in fragments) < MIN_FRAGMENT_CHARS

    # A lesson satisfies the quote only if it contains EVERY fragment.
    hosts = [stem for stem, body in transcripts.items()
             if all(f in body for f in fragments)]

    missing = [f for f in fragments
               if not any(f in body for body in transcripts.values())]

    near_miss = None
    if missing:
        near_miss = {"fragment": missing[0],
                     **best_fuzzy_window(missing[0], transcripts)}

    cited = resolve_cite(quote["cite"], transcripts)

    if missing:
        # A passage that is clearly the same sentence with a word changed was
        # REWORDED (a pluralised verb, a removed stutter); one with no close
        # passage anywhere was INVENTED. Very different defects.
        ratio = near_miss["ratio"] if near_miss else 0.0
        if ratio >= REWORD_SIMILARITY:
            verdict = "REWORDED"
        elif len(missing[0]) < MIN_FRAGMENT_CHARS:
            # Too few words to support a fabrication claim EITHER WAY. The
            # verified example is "sejam idempotentes" against the spoken "ela
            # seja idempotente": both words inflected, so a two-word fragment
            # scores 0.5 whether it was reworded or invented. Calling that
            # NOT_FOUND would put an unsupportable accusation in front of a
            # human, and the alarming answer is the one that survives review.
            verdict = "INCONCLUSIVE"
        else:
            verdict = "NOT_FOUND"
    elif weak:
        verdict = "WEAK_MATCH"
    elif not hosts:
        # Every fragment exists, but no single lesson holds all of them --
        # the quote was stitched together from more than one lesson.
        verdict = "STITCHED"
    elif cited and cited in hosts:
        verdict = "VERBATIM"
    elif cited:
        verdict = "MISATTRIBUTED"
    else:
        verdict = "UNCITED"

    return {
        **quote,
        "verdict": verdict,
        "found_in": hosts,
        "resolved_cite": cited,
        "missing_fragments": missing,
        "near_miss": near_miss,
        "weak": weak,
    }


# ---------------------------------------------------------------- Gate S

def subject_terms(course_dir: Path, transcripts: dict[str, str]) -> list[str]:
    """Slug words that appear in enough lessons that an absence is a signal."""
    tokens = [t for t in re.split(r"[^a-z0-9]+", fold(course_dir.name))
              if t and t not in SLUG_STOPWORDS and len(t) > 2]
    n = len(transcripts) or 1
    keep = []
    for tok in dict.fromkeys(tokens):
        hits = sum(1 for body in transcripts.values() if tok in body)
        if hits / n >= SUBJECT_TERM_MIN_SHARE:
            keep.append(tok)
    return keep


def subject_dropout(transcripts: dict[str, str], raw: dict[str, str],
                    terms: list[str]) -> list[dict]:
    """Lessons missing a subject term the rest of the course uses throughout."""
    findings = []
    # Capitalized-token counts per lesson, for the candidate list.
    per_lesson_caps = {
        stem: Counter(w for w in re.findall(r"\b[A-Z][A-Za-zÀ-ÿ0-9.+#-]{2,}\b", body)
                      if w not in NOT_A_PRODUCT)
        for stem, body in raw.items()
    }
    # How many lessons each capitalized token appears in at all.
    spread = Counter()
    for caps in per_lesson_caps.values():
        spread.update(caps.keys())

    for term in terms:
        for stem, body in transcripts.items():
            if term in body:
                continue
            # A suspect is near-unique to this lesson, repeated inside it, AND
            # absent from the lesson's own title. That last filter is what
            # separates signal from noise: "CORS x10" in a lesson titled
            # "resolvendo-o-problema-de-cors" is the lesson doing its job, while
            # "Svelte x6" in one titled "configurando-a-devtools" is a
            # transcription substitution. Without it the real hit sits eighth in
            # a list of the lesson's own topic words.
            title = fold(stem)
            counts = per_lesson_caps.get(stem, Counter())
            candidates = sorted(
                ((w, n) for w, n in counts.items()
                 if spread[w] <= 2 and n >= MIN_CANDIDATE_REPEATS
                 and fold(w) not in title),
                key=lambda kv: -kv[1],
            )
            findings.append({
                "lesson": stem,
                "absent_term": term,
                "substitution_candidates": [f"{w} x{n}" for w, n in candidates[:8]],
            })
    # Findings with a repeated near-unique candidate come first -- that is the
    # documented substitution shape; the rest are usually a benign off-topic lesson.
    findings.sort(key=lambda f: not f["substitution_candidates"])
    return findings


# ---------------------------------------------------------------- Gate T

def measure(pack_path: Path) -> dict:
    text = pack_path.read_text(encoding="utf-8", errors="replace")
    chars = len(text)
    declared = None
    m = re.search(r"^tokens_estimate:\s*~?\s*([\d,]+)", text, re.M)
    if m:
        declared = int(m.group(1).replace(",", ""))
    return {
        "pack": pack_path.name,
        "bytes": pack_path.stat().st_size,
        "chars": chars,
        "measured_tokens": round(chars / CHARS_PER_TOKEN),
        "declared_tokens": declared,
        "over_cap": round(chars / CHARS_PER_TOKEN) > TOKEN_CAP,
    }


# ---------------------------------------------------------------- driver

def audit_course(course_dir: Path, pack_glob: str, v1_diff: bool) -> dict:
    packs = sorted(course_dir.glob(pack_glob))
    transcripts = load_transcripts(course_dir)
    raw = load_transcripts_raw(course_dir)

    if not packs:
        return {"course": course_dir.name, "error": f"no pack matching {pack_glob}"}
    if not transcripts:
        return {"course": course_dir.name, "error": "no transcripts found"}

    quotes: list[dict] = []
    measurements: list[dict] = []
    for pack in packs:
        text = pack.read_text(encoding="utf-8", errors="replace")
        for q in parse_quotes(text):
            quotes.append({**check_quote(q, transcripts), "pack": pack.name})
        measurements.append(measure(pack))

    terms = subject_terms(course_dir, transcripts)
    result = {
        "course": course_dir.name,
        "lessons": len(transcripts),
        "packs": [p.name for p in packs],
        "gate_q": {
            "total": len(quotes),
            "by_verdict": dict(Counter(q["verdict"] for q in quotes)),
            "quotes": quotes,
        },
        "gate_s": {
            "subject_terms": terms,
            "findings": subject_dropout(transcripts, raw, terms),
        },
        "gate_t": measurements,
    }

    if v1_diff:
        v1 = course_dir / f"{course_dir.name}.pack.md"
        if v1.exists():
            v1_text = v1.read_text(encoding="utf-8", errors="replace")
            v2_norm = normalize("\n".join(
                p.read_text(encoding="utf-8", errors="replace") for p in packs))
            # NOT a defect list. v1 and v2 chose quotes from different amounts of
            # the course (42% vs 100% on this cohort), so a different selection is
            # the expected outcome. These are the passages v1 thought worth keeping
            # that v2 did not -- a human decides whether the IDEA survived
            # elsewhere in v2 or was genuinely lost.
            unique_to_v1 = [q["text"] for q in parse_quotes(v1_text)
                            if normalize(q["text"])[:60] not in v2_norm]
            result["v1_diff"] = {
                "v1_bytes": v1.stat().st_size,
                "v1_truncated": v1.stat().st_size < 1500,
                "v1_quotes_absent_from_v2": unique_to_v1,
            }
        else:
            result["v1_diff"] = {"error": "no v1 pack"}

    return result


def render(res: dict) -> None:
    if "error" in res:
        print(f"  !! {res['course']}: {res['error']}")
        return

    q = res["gate_q"]
    counts = q["by_verdict"]
    # UNCITED and WEAK_MATCH are bookkeeping, not fidelity defects.
    bad = sum(counts.get(k, 0) for k in ("NOT_FOUND", "REWORDED", "STITCHED",
                                         "MISATTRIBUTED", "INCONCLUSIVE"))
    flag = "FLAG" if bad else "ok  "
    print(f"\n=== {res['course']}  ({res['lessons']} lessons, {len(res['packs'])} pack file(s))")
    print(f"  Gate Q  [{flag}] {q['total']} quotes -> " +
          ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for item in q["quotes"]:
        if item["verdict"] == "VERBATIM":
            continue
        print(f"       - {item['verdict']}: \"{item['text'][:86]}...\"")
        print(f"         cited={item['cite']!r} -> resolved={item['resolved_cite']!r} "
              f"found_in={item['found_in'][:2]}")
        nm = item.get("near_miss")
        if nm:
            print(f"         pack claims:   {nm['fragment'][:88]!r}")
            print(f"         transcript has: {nm['excerpt'][:88]!r}")
            print(f"         similarity {nm['ratio']} in {nm['lesson']}")

    s = res["gate_s"]
    strong = [f for f in s["findings"] if f["substitution_candidates"]]
    sflag = "FLAG" if strong else ("note" if s["findings"] else "ok  ")
    print(f"  Gate S  [{sflag}] subject terms {s['subject_terms']} "
          f"({len(strong)} with a repeated near-unique candidate, "
          f"{len(s['findings']) - len(strong)} bare)")
    for f in s["findings"]:
        if not f["substitution_candidates"]:
            continue
        print(f"       - '{f['absent_term']}' ABSENT from {f['lesson']}")
        print(f"         repeated terms unique to it: {f['substitution_candidates']}")
    bare = [f["lesson"] for f in s["findings"] if not f["substitution_candidates"]]
    if bare:
        print(f"         (no candidate, likely off-topic lesson: {bare[:4]})")

    print("  Gate T  (recorded, not graded)")
    for m in res["gate_t"]:
        mark = "over cap" if m["over_cap"] else "within cap"
        print(f"       - {m['pack']}: {m['measured_tokens']} tok measured, "
              f"{m['declared_tokens']} declared ({mark})")

    if "v1_diff" in res:
        v = res["v1_diff"]
        if "error" in v:
            print(f"  v1 diff  {v['error']}")
        else:
            note = " TRUNCATED STUB - nothing to compare" if v["v1_truncated"] else ""
            print(f"  v1 diff  v1={v['v1_bytes']}B{note} (informational, not a defect list)")
            for t in v["v1_quotes_absent_from_v2"]:
                print(f"       - v1 kept, v2 did not: \"{t[:80]}...\"")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", type=Path, help="a course dir, or a tree with --all")
    ap.add_argument("--all", action="store_true", help="treat target as a tree of courses")
    ap.add_argument("--pack-glob", default="*.pack.v2*.md")
    ap.add_argument("--v1-diff", action="store_true", help="also report v1 regression")
    ap.add_argument("--json", type=Path, help="write the full report as JSON")
    args = ap.parse_args()

    if args.all:
        courses = sorted(d for d in args.target.iterdir()
                         if d.is_dir() and list(d.glob(args.pack_glob)))
    else:
        courses = [args.target]

    results = [audit_course(c, args.pack_glob, args.v1_diff) for c in courses]
    for r in results:
        render(r)

    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        print(f"\nJSON -> {args.json}")

    flagged = [r for r in results if "error" not in r and (
        any(qq["verdict"] != "VERBATIM" for qq in r["gate_q"]["quotes"])
        or r["gate_s"]["findings"])]
    print(f"\n{len(results)} course(s) audited, {len(flagged)} carrying at least one flag.")
    print("This is EVIDENCE, not a verdict. Promotion is a human decision (5.4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
