"""Preflight courses before a Stage-2 dispatch (TASKS.md §5.7): manifest vs transcripts,
lesson/module ORDER (manifest is the authority; `1000-` stems sort alphabetically),
CJK leakage, v2 collisions, Gate S subject terms, the v1 hash to baseline, the author line.

    .venv/bin/python scripts/preflight_courses.py <course> [...]   # from the project root
"""
import json, re, sys, pathlib, unicodedata, hashlib, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pack_fidelity as pf
nfc = lambda s: unicodedata.normalize("NFC", s)
for c in sys.argv[1:]:
    out = pathlib.Path("output/jstack-lives") / c
    inp = pathlib.Path("input/jstack-lives") / c
    man = json.loads((inp / "manifest.json").read_text(encoding="utf-8"))
    print("=" * 90); print(c)
    print(f"  manifest title: {man.get('title')!r}")
    keys = list(man["lessons"])
    trs = sorted(out.rglob("*.transcript.txt"))
    tkeys = [nfc(str(p.relative_to(out)).removesuffix(".transcript.txt")) for p in trs]
    mkeys = [nfc(k) for k in keys]
    print(f"  manifest entries: {len(mkeys)}  transcripts: {len(tkeys)}")
    print(f"  manifest-only: {[k for k in mkeys if k not in tkeys]}")
    print(f"  transcript-only: {[k for k in tkeys if k not in mkeys]}")
    lessons = [k for k in mkeys if k in tkeys]
    print(f"  lesson order == filename order: {lessons == sorted(lessons)}")
    mods = list(dict.fromkeys(k.split('/')[0] for k in lessons))
    print(f"  modules (manifest order): {mods}  == sorted: {mods == sorted(mods)}")
    stems = [k.split('/')[-1] for k in lessons]
    print(f"  duplicate stems across modules: {sorted({s for s in stems if stems.count(s) > 1})}")
    print(f"  `1000-` lessons: {sum(s.startswith('1000-') for s in stems)}/{len(stems)}  1000- modules: {[m for m in mods if m.startswith('1000-')]}")
    cjk = {}
    tot = 0
    for p in trs:
        t = p.read_text(encoding="utf-8")
        tot += len(t)
        n = len(re.findall(r"[぀-ヿ㐀-䶿一-鿿가-힯]", t))
        if n: cjk[p.name] = n
    print(f"  CJK/Hangul chars: {cjk or 0}   total chars {tot:,} = {tot/3.7/1000:.1f}k tok")
    print(f"  v2 collision: {[p.name for p in out.glob('*.pack.v2*.md')]}")
    t = pf.load_transcripts(out)
    print(f"  Gate S subject_terms: {pf.subject_terms(out, t)}")
    v1 = out / f"{c}.pack.md"
    print(f"  v1: {hashlib.sha256(v1.read_bytes()).hexdigest()}  {v1.stat().st_size} B  mtime={dt.datetime.fromtimestamp(v1.stat().st_mtime)}")
    desc = sorted(inp.glob("00-*.description.md"))
    for d in desc:
        a = [ln for ln in d.read_text(encoding="utf-8").splitlines() if "Autor" in ln]
        print(f"  course description: {d.name}  author line: {a}")
