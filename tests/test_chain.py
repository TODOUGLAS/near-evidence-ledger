"""On-chain glue, integer verdict rule, hashes, robustness. No network, no keys."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from ledger import chain as H  # noqa: E402
from ledger import claims as C  # noqa: E402
from ledger import data as D  # noqa: E402
from ledger import robustness as RB  # noqa: E402
from ledger import sources as S  # noqa: E402


def _results():
    p = ROOT / "output" / "results.json"
    if not p.exists():
        raise unittest.SkipTest("run `python -m ledger all --offline` first")
    return json.loads(p.read_text())


class TestIntegerRule(unittest.TestCase):
    def test_vectors_file_matches_python_rule(self):
        cases = json.loads((ROOT / "contract" / "tests" / "verdict_vectors.json").read_text())
        self.assertGreaterEqual(len(cases), 400)
        for c in cases:
            ci = tuple(c["ci"]) if c["ci"] else None
            self.assertEqual(C.verdict_fp(c["value"], c["comparator"], c["threshold"], ci), c["verdict"])
        self.assertEqual({c["verdict"] for c in cases}, {"SUPPORTED", "REFUTED", "INCONCLUSIVE"})

    def test_shipped_claims_same_verdict_in_float_and_integer_rule(self):
        for r in _results()["claims"]:
            ci = r["ci90"]
            fp = C.verdict_fp(C.micro(r["value"]), r["comparator"], C.micro(r["threshold"]),
                              (C.micro(ci[0]), C.micro(ci[1])) if ci else None)
            self.assertEqual(fp, r["verdict"], r["id"])

    def test_point_rule_boundaries(self):
        m = C.micro
        self.assertEqual(C.verdict_fp(m(10.5), ">=", m(10), None), "INCONCLUSIVE")  # exactly +5%
        self.assertEqual(C.verdict_fp(m(10.51), ">=", m(10), None), "SUPPORTED")
        self.assertEqual(C.verdict_fp(m(9.49), ">=", m(10), None), "REFUTED")


class TestHashes(unittest.TestCase):
    def test_snapshot_hash_is_stable_and_sensitive(self):
        a = H.snapshot_hash()
        self.assertEqual(a, H.snapshot_hash())
        self.assertEqual(len(a), 64)
        with tempfile.TemporaryDirectory() as t:
            for src in S.SOURCES.values():
                shutil.copy(S.SNAP / src["file"], Path(t) / src["file"])
            self.assertEqual(H.snapshot_hash(Path(t)), a)
            f = Path(t) / "dl_tvl.json"
            f.write_bytes(f.read_bytes() + b" ")
            self.assertNotEqual(H.snapshot_hash(Path(t)), a)

    def test_spec_hash_depends_on_threshold(self):
        base = H.spec_hash()
        changed = [dict(c) for c in C.CLAIMS]
        changed[0]["threshold"] = 1.01
        self.assertNotEqual(H.spec_hash(changed), base)
        self.assertEqual(H.spec_hash(), base)

    def test_results_hash_ignores_fetch_status_but_not_verdicts(self):
        res = _results()
        snap = H.snapshot_hash()
        h0 = H.results_hash(res, snap)
        res2 = json.loads(json.dumps(res))
        for v in res2["sources"].values():
            v["status"] = "fresh"
        self.assertEqual(H.results_hash(res2, snap), h0)
        res2["claims"][0]["value"] += 0.01
        self.assertNotEqual(H.results_hash(res2, snap), h0)

    def test_code_hash_is_hex(self):
        self.assertRegex(H.code_hash(), r"^[0-9a-f]{64}$")

    def test_contract_refuses_non_testnet(self):
        import os
        old = os.environ.get("LEDGER_CONTRACT")
        os.environ["LEDGER_CONTRACT"] = "someone.near"
        try:
            with self.assertRaises(SystemExit):
                H.contract_id()
        finally:
            if old is None:
                os.environ.pop("LEDGER_CONTRACT")
            else:
                os.environ["LEDGER_CONTRACT"] = old


class TestPayloads(unittest.TestCase):
    def test_verdict_records_are_integers_and_consistent(self):
        recs = H.verdict_records(_results())
        self.assertEqual(len(recs), len(C.CLAIMS))
        for r in recs:
            for k in ("threshold", "value"):
                self.assertIsInstance(r[k], int)
            self.assertIn(r["verdict"], ("SUPPORTED", "REFUTED", "INCONCLUSIVE"))
            self.assertEqual((r["ci_lo"] is None), (r["ci_hi"] is None))

    def test_build_run_fields_match_contract_schema(self):
        meta, vers = H.build_run(_results(), 7764, 9157, "x" * 400)
        self.assertEqual(set(meta), {"spec_hash", "snapshot_hash", "code_hash", "results_hash", "data_through",
                                     "backtest_cov80_bp", "backtest_cov95_bp", "note"})
        self.assertLessEqual(len(meta["note"]), 280)
        self.assertEqual(set(vers[0]), {"claim_id", "comparator", "threshold", "value", "ci_lo", "ci_hi", "verdict"})

    def test_week_end_ms(self):
        self.assertEqual(H.week_end_ms("2026-11-15"), int(pd.Timestamp("2026-11-16", tz="UTC").timestamp() * 1000))

    def test_predictions_are_ordered_and_in_the_future(self):
        w = D.weekly(S.load_log())
        items = H.build_predictions(w, horizons=(1, 2, 4))
        self.assertGreater(len(items), 15)
        last_end = H.week_end_ms(w.index[-1].strftime("%Y-%m-%d"))
        by = {}
        for p in items:
            self.assertLessEqual(p["lo"], p["point"])
            self.assertLessEqual(p["point"], p["hi"])
            self.assertGreater(int(p["target_end_ms"]), last_end)
            self.assertEqual(len(p["snapshot_hash"]), 64)
            by.setdefault(p["metric"], []).append(p["hi"] - p["lo"])
        for m, widths in by.items():  # intervals widen with the horizon
            self.assertEqual(widths, sorted(widths), m)

    def test_observed_value_requires_complete_week(self):
        w = D.weekly(S.load_log())
        last = w.index[-1].strftime("%Y-%m-%d")
        self.assertIsNotNone(H.observed_value(w, "txns", last))
        self.assertIsNone(H.observed_value(w, "txns", "2099-01-03"))


class TestRobustness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = S.load_log()
        cls.w = D.weekly(cls.log)
        from ledger.provenance import Registry
        cls.rows = C.evaluate(cls.w, cls.log, Registry(cls.log))
        cls.rob = RB.analyze(cls.w, cls.log, cls.rows)

    def test_base_variant_reproduces_shipped_verdict(self):
        for r in self.rob:
            self.assertTrue(r["base_same"], r["id"])
            self.assertEqual(len(r["variants"]) >= 3, True)

    def test_flip_change_really_flips(self):
        for rr, rb in zip(self.rows, self.rob):
            if rb["flip_change"] is None:
                continue
            rec = dict(comparator=rr["comparator"], threshold=C.micro(rr["threshold"]), value=C.micro(rr["value"]),
                       ci_lo=C.micro(rr["ci"][0]) if rr["ci"] else None, ci_hi=C.micro(rr["ci"][1]) if rr["ci"] else None)
            thr2 = int(round(rec["threshold"] * (1 + rb["flip_change"])))
            ci = (rec["ci_lo"], rec["ci_hi"]) if rec["ci_lo"] is not None else None
            self.assertNotEqual(C.verdict_fp(rec["value"], rec["comparator"], thr2, ci), rr["verdict"], rr["id"])

    def test_c3_gas_only_variant_is_reported(self):
        c3 = next(r for r in self.rob if r["id"] == "C3")
        gas = [v for v in c3["variants"] if v["label"].startswith("DATA SOURCE")]
        self.assertEqual(len(gas), 1)
        self.assertEqual(gas[0]["verdict"], "REFUTED")  # honest finding: SUPPORTED relies on DefiLlama's attribution


if __name__ == "__main__":
    unittest.main()


class TestCustomClaims(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = D.weekly(S.load_log())

    def test_examples_evaluate_and_hash_is_deterministic(self):
        from ledger import custom
        for f in sorted((ROOT / "claims" / "examples").glob("*.json")):
            a = custom.evaluate(custom.load(f), self.w)
            b = custom.evaluate(custom.load(f), self.w)
            self.assertEqual(a, b)
            self.assertIn(a["verdict"], ("SUPPORTED", "REFUTED", "INCONCLUSIVE"))
            self.assertEqual(len(a["spec_hash"]), 64)

    def test_validation_rejects_bad_specs(self):
        from ledger import custom
        good = custom.load(next((ROOT / "claims" / "examples").glob("*.json")))
        for bad in ({"series": "nope"}, {"kind": "x"}, {"comparator": "=="}, {"window": 1}, {"threshold": "a"}):
            with self.assertRaises(ValueError):
                custom.evaluate({**good, **bad}, self.w)
        with self.assertRaises(ValueError):
            custom.evaluate({k: v for k, v in good.items() if k != "id"}, self.w)

    def test_threshold_change_changes_spec_hash_and_can_flip_verdict(self):
        from ledger import custom
        spec = {"id": "T", "statement": "t", "series": "txns", "kind": "level", "stat": "median", "window": 13,
                "comparator": ">=", "threshold": 1.0}
        hi = custom.evaluate({**spec, "threshold": 1e12}, self.w)
        lo = custom.evaluate({**spec, "threshold": 1.0}, self.w)
        self.assertEqual((lo["verdict"], hi["verdict"]), ("SUPPORTED", "REFUTED"))
        self.assertNotEqual(lo["spec_hash"], hi["spec_hash"])
