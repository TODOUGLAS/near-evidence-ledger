import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from ledger import claims as C
from ledger import data as D
from ledger import forecast as F
from ledger import sources as S
from ledger.provenance import Registry
from ledger.stats import wilson

ROOT = Path(__file__).resolve().parent.parent


def snap_log():
    """A fetch log pointing at the frozen snapshots (no network)."""
    man = json.loads((S.SNAP / "MANIFEST.json").read_text())
    log = {}
    for sid, src in S.SOURCES.items():
        m = man[sid]
        log[sid] = {"name": src["name"], "url": src["url"], "file": src["file"], "status": "snapshot",
                    "fetched_at_utc": m["fetched_at_utc"], "fetched_at_cst": m["fetched_at_cst"],
                    "sha256": m["sha256"], "bytes": m["bytes"], "path": f"data/snapshots/{src['file']}"}
    return log


class TestData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = snap_log()
        cls.w = D.weekly(cls.log)

    def test_snapshot_hashes_match_manifest(self):
        for sid, e in self.log.items():
            raw = (ROOT / e["path"]).read_bytes()
            import hashlib
            self.assertEqual(hashlib.sha256(raw).hexdigest(), e["sha256"], sid)

    def test_incomplete_day_dropped(self):
        nb = D.nb_daily(self.log)
        fetch_day = pd.Timestamp(self.log["nb_charts"]["fetched_at_utc"][:10])
        self.assertTrue((nb.index < fetch_day).all())

    def test_only_complete_weeks(self):
        self.assertTrue(((self.w.index.dayofweek) == 6).all())  # weeks end on Sunday
        nb = D.nb_daily(self.log)
        self.assertLessEqual(self.w.index[-1], nb.index[-1])

    def test_weekly_txns_equal_daily_sum(self):
        nb = D.nb_daily(self.log)
        wk = self.w.index[-5]
        s = nb.loc[wk - pd.Timedelta(days=6):wk, "txns"].sum()
        self.assertAlmostEqual(s, self.w.loc[wk, "txns"])


class TestClaims(unittest.TestCase):
    def test_verdict_rules(self):
        self.assertEqual(C.verdict(2.0, ">=", 1.0, (1.5, 2.5)), "SUPPORTED")
        self.assertEqual(C.verdict(0.5, ">=", 1.0, (0.4, 0.6)), "REFUTED")
        self.assertEqual(C.verdict(1.0, ">=", 1.0, (0.8, 1.2)), "INCONCLUSIVE")
        self.assertEqual(C.verdict(0.025, "<=", 0.05, None), "SUPPORTED")
        self.assertEqual(C.verdict(10, ">=", 10, None), "INCONCLUSIVE")  # inside the 5% band
        self.assertEqual(C.verdict(0.06, "<=", 0.05, None), "REFUTED")

    def test_nakamoto(self):
        self.assertEqual(C.nakamoto(np.array([50, 20, 10, 10, 10])), 1)   # 50% > 1/3
        self.assertEqual(C.nakamoto(np.ones(9)), 4)                       # 3/9 not > 1/3, 4/9 is
        self.assertEqual(C.nakamoto(np.ones(100)), 34)

    def test_claims_have_thresholds_and_ids(self):
        ids = [c["id"] for c in C.CLAIMS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(6 <= len(ids) <= 12)
        for c in C.CLAIMS:
            self.assertIn(c["comparator"], (">=", "<="))
            self.assertIsInstance(c["threshold"], (int, float))

    def test_every_claim_gets_a_verdict_and_provenance(self):
        log = snap_log()
        w = D.weekly(log)
        reg = Registry(log)
        rows = C.evaluate(w, log, reg)
        self.assertEqual(len(rows), len(C.CLAIMS))
        for r in rows:
            self.assertIn(r["verdict"], ("SUPPORTED", "REFUTED", "INCONCLUSIVE"))
            self.assertIn(f"{r['id']}.value", reg.items)
            self.assertIn("fetched", reg.tooltip(f"{r['id']}.value"))


class TestForecast(unittest.TestCase):
    def synthetic(self, n=200, seed=1):
        g = np.random.default_rng(seed)
        y = np.cumsum(g.normal(0.0, 0.1, n)) + 10
        return y, np.r_[np.nan, np.diff(y)]

    def test_no_leakage_future_changes_do_not_move_forecast(self):
        y, d = self.synthetic()
        t, h = 150, 4
        q0 = F.conformal_q(y, d, t, h, [0.1, 0.5, 0.9])
        y2 = y.copy()
        y2[t + 1:] += 100.0  # corrupt everything after the origin
        d2 = np.r_[np.nan, np.diff(y2)]
        q1 = F.conformal_q(y2, d2, t, h, [0.1, 0.5, 0.9])
        self.assertEqual(q0, q1)
        g0 = F.gauss_q(y, d, t, h, [0.1, 0.9])
        g1 = F.gauss_q(y2, d2, t, h, [0.1, 0.9])
        self.assertEqual(g0, g1)
        b0 = F.qgbm_q(y, d, t, h, [0.1, 0.9])
        b1 = F.qgbm_q(y2, d2, t, h, [0.1, 0.9])
        self.assertEqual(b0, b1)

    def test_calibration_errors_only_use_resolved_origins(self):
        y, d = self.synthetic()
        t, h = 100, 12
        e = F.cal_errors(y, d, t, h)
        # last origin allowed is t-h; recompute it by hand
        s = t - h
        manual = y[s + h] - y[s] - F.drift_path(d, s, h)
        self.assertAlmostEqual(e[-1], manual)

    def test_conformal_coverage_on_iid_noise_is_near_nominal(self):
        y, d = self.synthetic(n=600, seed=3)
        h = 4
        hits = []
        for t in range(300, 590):
            q = F.conformal_q(y, d, t, h, [0.1, 0.9])
            hits.append(q[0.1] <= y[t + h] <= q[0.9])
        self.assertGreater(np.mean(hits), 0.7)
        self.assertLess(np.mean(hits), 0.92)

    def test_fan_is_monotone_and_widens(self):
        log = snap_log()
        w = D.weekly(log)
        f = F.fan(w, "txns", 12)
        self.assertTrue((f["p100"] <= f["p500"]).all() and (f["p500"] <= f["p900"]).all())
        self.assertGreater(f["p900"].iloc[-1] / f["p100"].iloc[-1], f["p900"].iloc[0] / f["p100"].iloc[0])

    def test_wilson(self):
        lo, hi = wilson(80, 100)
        self.assertTrue(lo < 0.8 < hi)


class TestFetchFallback(unittest.TestCase):
    def test_network_failure_falls_back_to_snapshot(self):
        orig = S._get
        S._get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated outage"))
        try:
            log = S.fetch_all(force_offline=False, write_log=False)
        finally:
            S._get = orig
        self.assertEqual({e["status"] for e in log.values()}, {"snapshot"})
        self.assertTrue(all("simulated outage" in e["note"] for e in log.values()))


class TestRegistry(unittest.TestCase):
    def test_link_contains_source_and_date(self):
        log = snap_log()
        reg = Registry(log)
        reg.add("x", 1234.5, ",.1f", "dl_tvl", "demo")
        h = reg.link("x")
        self.assertIn("api.llama.fi", h)
        self.assertIn("fetched", h)
        with self.assertRaises(KeyError):
            reg.add("y", 1, "d", "no_such_source", "bad")


if __name__ == "__main__":
    unittest.main()
