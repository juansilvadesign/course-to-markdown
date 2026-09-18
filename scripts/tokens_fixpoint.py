"""Set tokens_estimate to round(len(text)/3.7) and iterate: writing the number changes the
text it measures (a SELF-DESCRIBING field is a fixed point, not a reading).

    .venv/bin/python scripts/tokens_fixpoint.py output/jstack-lives/<c>/<c>.pack.v2.md
"""
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
for i in range(10):
    text = p.read_text(encoding="utf-8")
    m = re.search(r"^tokens_estimate:\s*(.+)$", text, re.M)
    declared, measured = m.group(1).strip(), round(len(text) / 3.7)
    print(f"  pass {i}: declared={declared!r} measured={measured}")
    if declared == str(measured):
        print(f"  FIXED POINT {measured} ({len(text)} chars)")
        break
    p.write_text(text[:m.start(1)] + str(measured) + text[m.end(1):], encoding="utf-8")
else:
    sys.exit("no fixed point in 10 passes")
