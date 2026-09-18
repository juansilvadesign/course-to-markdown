"""Derive the HELD cohort from the coverage gate, never from "has no v2 pack" (TASKS.md §5.7).

held = v1 coverage FAILs that carry no `*.pack.v2*.md` yet, cheapest first, with the
PASS split. Run from the project root:
    .venv/bin/python scripts/pack_coverage.py output/jstack-lives --pack-glob '*.pack.md' > cov_v1.txt
    .venv/bin/python scripts/held_cohort.py cov_v1.txt
"""
import re, sys, pathlib
root = pathlib.Path("output/jstack-lives")
txt = pathlib.Path(sys.argv[1]).read_text()
fails = re.findall(r"^FAIL  (\S+)", txt, re.M)
passes = re.findall(r"^PASS  (\S+)", txt, re.M)
print(f"FAIL={len(fails)} PASS={len(passes)}")
held = []
for c in fails:
    d = root / c
    v2 = sorted(p.name for p in d.glob("*.pack.v2*.md"))
    if v2:
        continue
    trs = sorted(d.rglob("*.transcript.txt"))
    chars = sum(len(p.read_text(encoding="utf-8")) for p in trs)
    held.append((chars / 3.7 / 1000, len(trs), c))
held.sort()
print(f"held={len(held)}  total={sum(h[0] for h in held):.1f}k tok  lessons={sum(h[1] for h in held)}")
for k, n, c in held:
    print(f"{k:7.1f}k  {n:3d}  {c}")
# PASS split
pw = sum(1 for c in passes if list((root/c).glob('*.pack.v2*.md')))
print(f"PASS with v2={pw} without={len(passes)-pw}")
