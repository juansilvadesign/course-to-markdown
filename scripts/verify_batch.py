"""Post-dispatch disk + contract checks for a Stage-2 batch (TASKS.md §5.7).

Per course: files written since dispatch and any stray write below the course
root, v1 evidence byte-identity against a baseline captured BEFORE dispatch,
frontmatter keys, `compiled` vs the asserted date AND the file's mtime, section
order, Curriculum titles and stems vs manifest order, quote markers and cites,
See-also resolution (and v1-pack cites), ASCII-folded PT words, CJK leakage.
Complements (never replaces) pack_coverage.py and pack_fidelity.py.

Run from the course-to-markdown project root with .venv/bin/python:
    sha256sum output/jstack-lives/<c>/<c>.pack.md > v1_baseline.txt   # BEFORE dispatch
    .venv/bin/python scripts/verify_batch.py <course> [...] \
        --dispatch 2026-09-18T16:04:00 --expect-date 2026-09-18 --v1-baseline v1_baseline.txt
"""
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import unicodedata

import argparse

# Filled from the command line in __main__ (see the docstring).
ROOT = INPUT = REPO = DISPATCH = EXPECT_DATE = None
V1_SHA: dict = {}
SECTIONS = ["## TL;DR", "## Core ideas", "## Curriculum", "## Capabilities unlocked",
            "## Frameworks / models", "## Quotes worth keeping", "## How to apply", "## See also"]
FM_KEYS = ["title", "author", "type", "domain", "source", "compiled", "tokens_estimate"]
# Unambiguous ASCII-folded forms of common PT words (never valid unaccented).
FOLDED = ["nao", "voce", "voces", "codigo", "aplicacao", "aplicacoes", "configuracao", "informacao",
          "informacoes", "funcao", "tambem", "usuario", "usuarios", "licao", "producao",
          "integracao", "invalidacao", "permissoes", "autorizacao", "formularios", "validacoes", "opiniao",
          "estilizacao", "sessao", "padrao", "versao", "atencao", "solucao", "questao", "entao",
          "possivel", "facil", "unico", "rapido", "logica"]
# Dropped: pratica / especifico / modulo / voltara are valid unaccented verb forms.


def nfc(s):
    return unicodedata.normalize("NFC", s)


def section(text, head):
    lines, on = [], False
    for ln in text.splitlines():
        if ln.startswith("## "):
            on = ln.strip() == head
            continue
        if on:
            lines.append(ln)
    return lines


def main(courses):
    for c in courses:
        d = ROOT / c
        print("=" * 100)
        print(c)
        # 1. What changed on disk since dispatch (anywhere under the course dir)
        changed = [p for p in d.rglob("*") if p.is_file()
                   and dt.datetime.fromtimestamp(p.stat().st_mtime) >= DISPATCH]
        print(f"  files modified since dispatch: {[str(p.relative_to(d)) for p in changed]}")
        stray = [p for p in changed if p.parent != d]
        print(f"  stray writes below course root: {len(stray)} {[str(p.relative_to(d)) for p in stray]}")
        # 2. v1 evidence byte-identity
        v1 = d / f"{c}.pack.md"
        if not v1.exists():
            print("  v1: absent"); v1 = None
        sha = hashlib.sha256(v1.read_bytes()).hexdigest() if v1 else None
        print(f"  v1 sha256 identical: {(sha == V1_SHA[c]) if c in V1_SHA else 'no-baseline'}  ({(sha or 'none')[:8]}…)  mtime={dt.datetime.fromtimestamp(v1.stat().st_mtime) if v1 else None}")
        # 3. v2 presence
        v2s = sorted(d.glob("*.pack.v2*.md"))
        if not v2s:
            print("  !! NO v2 PACK AT COURSE ROOT")
            continue
        for v2 in v2s:
            text = v2.read_text(encoding="utf-8")
            mt = dt.datetime.fromtimestamp(v2.stat().st_mtime)
            print(f"  v2: {v2.name}  {v2.stat().st_size} B  {len(text)} chars  mtime={mt:%Y-%m-%d %H:%M:%S}")
            # frontmatter
            fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
            front = {}
            if fm:
                for ln in fm.group(1).splitlines():
                    if ":" in ln:
                        k, v = ln.split(":", 1)
                        front[k.strip()] = v.strip()
            missing = [k for k in FM_KEYS if k not in front]
            print(f"  frontmatter keys missing: {missing}")
            print(f"  compiled={front.get('compiled')!r} (expect {EXPECT_DATE}; mtime date {mt:%Y-%m-%d}) "
                  f"-> {'OK' if front.get('compiled') == EXPECT_DATE == f'{mt:%Y-%m-%d}' else 'CHECK'}")
            print(f"  author={front.get('author')!r} type={front.get('type')!r} domain={front.get('domain')!r}")
            print(f"  source={front.get('source')!r}")
            print(f"  source resolves: {(REPO / front.get('source','').strip('\"')).exists()}")
            print(f"  tokens_estimate raw={front.get('tokens_estimate')!r}  bare-int={front.get('tokens_estimate','').isdigit()}")
            measured = round(len(text) / 3.7)
            print(f"  Gate-T measured now: {measured}")
            # sections + order
            heads = [ln.strip() for ln in text.splitlines() if ln.startswith("## ")]
            print(f"  sections: {heads}")
            print(f"  section order == contract: {heads == SECTIONS}")
            # curriculum
            man = json.loads((INPUT / c / 'manifest.json').read_text())
            stems = [nfc(k.split('/')[-1]) for k in man['lessons'] if '/' in k]
            titles = [nfc(v.get('title', '')).strip().casefold() for k, v in man['lessons'].items() if '/' in k]
            cur = [ln for ln in section(text, "## Curriculum") if re.match(r"\s*\d+\.", ln)]
            ends = []
            for ln in cur:
                m = re.search(r"—\s*(\S+)\s*$", nfc(ln))
                ends.append(m.group(1) if m else None)
            got_titles = []
            for ln in cur:
                m = re.search(r"\*\*(.+?)\*\*", nfc(ln))
                got_titles.append(m.group(1).strip().casefold() if m else None)
            print(f"  curriculum lines: {len(cur)} / manifest lessons with transcript: {len(stems)}")
            print(f"  curriculum bold titles == manifest titles, in order: {got_titles == titles}")
            if got_titles != titles:
                for i, (g, w) in enumerate(zip(got_titles + [None] * 99, titles)):
                    if g != w:
                        print(f"    #{i+1} got {g!r} want {w!r}")
            n_stem = sum(e is not None for e in ends)
            print(f"  curriculum lines ending in a stem: {n_stem}/{len(cur)}; stems == manifest order: {ends == stems}")
            # quotes
            ql = [ln for ln in section(text, "## Quotes worth keeping") if ln.strip()]
            dash = [ln for ln in ql if ln.strip().startswith("- ")]
            other = [ln for ln in ql if not ln.strip().startswith("- ")]
            print(f"  quote lines: {len(ql)} dash-marked: {len(dash)} non-dash: {len(other)} cleaned: {sum('(cleaned)' in ln for ln in dash)}")
            for ln in other:
                print(f"    NON-DASH: {ln[:120]}")
            for ln in dash:
                m = re.search(r"—\s*(\S+)\s*$", nfc(ln))
                st = m.group(1) if m else None
                print(f"    cite={st!r:75s} in-course={st in stems}")
            # see also
            sa = "\n".join(section(text, "## See also"))
            paths = re.findall(r"(knowledge/[^\s`)\]]+?\.md)", sa)
            for p in paths:
                ok = (REPO / p).exists()
                v1cite = p.endswith(".pack.md")
                print(f"  see-also {'OK ' if ok else 'MISSING'} {'V1-CITE!' if v1cite else ''} {p}")
            if not paths:
                print(f"  see-also: no knowledge/ paths found; raw: {sa[:300]!r}")
            # ascii folding
            body = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)   # drop frontmatter
            body = re.sub(r"`[^`]*`", " ", body)                                   # drop code spans
            body = re.sub(r"\S*[/\\]\S*", " ", body)                              # drop paths
            body = re.sub(r"[\wÀ-ÿ]+(?:-[\wÀ-ÿ]+){2,}", " ", body)                  # drop slugs/stems
            words = re.findall(r"[A-Za-zÀ-ÿ]+", body.lower())
            folded = {w: words.count(w) for w in FOLDED if w in words}
            print(f"  ascii-folded PT words: {folded}")
            cjk = re.findall(r"[぀-ヿ㐀-䶿一-鿿]", text)
            print(f"  CJK chars in pack: {len(cjk)}")


def parse_baseline(path):
    """`sha256sum` output -> {course: sha}; the course is the pack's parent folder."""
    out = {}
    for ln in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"([0-9a-f]{64})\s+\*?(.+)$", ln.strip())
        if m:
            out[pathlib.Path(m.group(2)).parent.name] = m.group(1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("courses", nargs="+")
    # Required on purpose: a defaulted dispatch time makes the stray-write check
    # silently compare against the wrong moment and pass.
    ap.add_argument("--dispatch", required=True, type=dt.datetime.fromisoformat,
                    help="local time just BEFORE dispatch; files newer than this are the batch's writes")
    ap.add_argument("--expect-date", default=dt.date.today().isoformat(),
                    help="the literal `compiled:` date the prompts asserted (default: today)")
    ap.add_argument("--v1-baseline", type=pathlib.Path,
                    help="`sha256sum` of the v1 packs, captured BEFORE dispatch")
    ap.add_argument("--root", type=pathlib.Path, default=pathlib.Path("output/jstack-lives"))
    ap.add_argument("--input", type=pathlib.Path, default=pathlib.Path("input/jstack-lives"))
    ap.add_argument("--repo", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[4],
                    help="root that `source:` and See-also paths are relative to (default: the parent monorepo)")
    args = ap.parse_args()
    ROOT, INPUT, REPO = args.root, args.input, args.repo
    DISPATCH, EXPECT_DATE = args.dispatch, args.expect_date
    V1_SHA = parse_baseline(args.v1_baseline) if args.v1_baseline else {}
    main(args.courses)
