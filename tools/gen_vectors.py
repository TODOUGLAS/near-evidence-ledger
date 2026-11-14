"""Regenerate contract/tests/verdict_vectors.json from the Python integer rule (the contract test replays it)."""
import json
import random
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from ledger.claims import verdict_fp  # noqa: E402

random.seed(7)
cases = []
for thr in [0, 1_000_000, -2_000_000, 100_000_000_000, 50_000, 10_000_000]:
    for c in (">=", "<="):
        for _ in range(40):
            v = random.choice([thr, thr + thr // 20, thr - thr // 20, thr + thr // 20 + 1, thr - thr // 20 - 1,
                               random.randint(-3 * abs(thr) - 5, 3 * abs(thr) + 5)])
            ci = None
            if random.random() < 0.6:
                a = v + random.randint(-abs(thr) // 3 - 3, abs(thr) // 3 + 3)
                b = v + random.randint(-abs(thr) // 3 - 3, abs(thr) // 3 + 3)
                ci = (min(a, b), max(a, b))
            cases.append(dict(value=v, comparator=c, threshold=thr, ci=ci, verdict=verdict_fp(v, c, thr, ci)))
(root / "contract" / "tests" / "verdict_vectors.json").write_text(json.dumps(cases))
print(len(cases), "vectors written")
