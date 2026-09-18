"""Print the manifest-ordered lesson table (stem, title, chars) for a Stage-2 dispatch prompt.

manifest.json is the ordering authority; longest line and largest file are printed so
the prompt can state the Read budget. Run from the project root:
    .venv/bin/python scripts/lesson_table.py <course> [...]
"""
import json, sys, pathlib, unicodedata
nfc = lambda s: unicodedata.normalize("NFC", s)
for c in sys.argv[1:]:
    out = pathlib.Path("output/jstack-lives") / c
    man = json.loads((pathlib.Path("input/jstack-lives") / c / "manifest.json").read_text(encoding="utf-8"))
    print("=" * 80); print(c)
    for k, v in man["lessons"].items():
        if "/" not in k:
            print(f"  course entry: {k} title={v.get('title')!r}")
    multi = len({k.split('/')[0] for k in man["lessons"] if "/" in k}) > 1
    tot = 0; n = 0
    for k, v in man["lessons"].items():
        if "/" not in k:
            continue
        mod, stem = k.split("/")
        p = out / mod / f"{stem}.transcript.txt"
        ch = len(p.read_text(encoding="utf-8"))
        tot += ch; n += 1
        big = max(len(l) for l in p.read_text(encoding="utf-8").splitlines() or [""])
        title = (v.get("title") or "").strip()
        if multi:
            print(f"| {n} | {mod} | {stem} | {title} | {ch:,} |")
        else:
            print(f"| {n} | {stem} | {title} | {ch:,} |")
    print(f"  total {tot:,} chars = {tot/3.7/1000:.1f}k tok; longest line/file max shown below")
    mx = max(((len(l), p.name) for p in out.rglob('*.transcript.txt') for l in p.read_text(encoding='utf-8').splitlines()), default=(0,''))
    lg = max(((len(p.read_text(encoding='utf-8')), p.name) for p in out.rglob('*.transcript.txt')))
    print(f"  longest line {mx[0]:,} ({mx[1]}); largest file {lg[0]:,} ({lg[1]})")
