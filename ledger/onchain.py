"""Sub-commands that touch the NEAR testnet registry. See ledger/chain.py for hashes and transport."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from . import chain as H
from . import claims as C
from . import data as D
from . import sources as S

TXS = H.ROOT / "docs" / "testnet_txs.tsv"


def _results() -> dict:
    p = S.OUT / "results.json"
    if not p.exists():
        raise SystemExit("no output/results.json: run `python -m ledger all --offline` first")
    return json.loads(p.read_text())


def _recompute_offline() -> dict:
    """Re-run the analysis on the frozen snapshots in a subprocess (quiet) and return results.json."""
    r = subprocess.run([sys.executable, "-m", "ledger", "all", "--offline"], capture_output=True, text=True, cwd=H.ROOT)
    if r.returncode != 0:
        raise SystemExit("offline re-run failed:\n" + r.stdout[-800:] + r.stderr[-800:])
    return _results()


def _log_tx(action: str, ident, tx: dict, note: str = "") -> None:
    TXS.parent.mkdir(exist_ok=True)
    new = not TXS.exists()
    with TXS.open("a", newline="") as f:
        wr = csv.writer(f, delimiter="\t", lineterminator="\n")
        if new:
            wr.writerow(["utc", "action", "id", "tx", "url", "note"])
        wr.writerow([datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), action, ident, tx["tx"], tx["url"], note])


def snapshot_onchain(run_id: int | None = None) -> dict:
    """Write docs/onchain.json: a static copy of the registry state that the dashboard embeds."""
    info = H.view("info")
    out: dict = {"contract": H.contract_id(), "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "info": info}
    rows = []
    if TXS.exists():
        rows = list(csv.DictReader(TXS.open(), delimiter="\t"))
    if info["runs"]:
        rid = run_id if run_id is not None else info["runs"] - 1
        out["run"] = H.view("get_run", {"run_id": rid})
        out["challenges"] = H.view("get_challenges", {"run_id": rid})
        pubs = [r for r in rows if r["action"] == "publish_run" and str(r["id"]) == str(rid)]
        out["run_tx"] = pubs[-1]["tx"] if pubs else ""
    preds = []
    for i in range(0, info["predictions"], 100):
        preds += H.view("list_predictions", {"from": i, "limit": 100})
    if preds:
        out["predictions"] = preds
        out["scoreboard"] = H.view("scoreboard", {"attester": preds[0]["attester"]})
        regs = [r for r in rows if r["action"] == "register_predictions"]
        out["predictions_registered_utc"] = regs[0]["utc"] if regs else ""
    (H.ROOT / "docs" / "onchain.json").write_text(json.dumps(out, indent=1))
    return out


def _fmt(v, pct=False):
    return f"{v / H.MICRO:,.4g}" if not pct else f"{v / H.MICRO:.1%}"


# ------------------------------------------------------------------------------------------ status
def status(a) -> int:
    info = H.view("info")
    if getattr(a, "write_onchain", False):
        snapshot_onchain(a.run)
        print("docs/onchain.json written (run `python -m ledger analyze` to rebuild the dashboard with it)")
    print(f"contract {H.contract_id()}  ({info['version']})  runs={info['runs']} challenges={info['challenges']} predictions={info['predictions']}")
    if info["runs"]:
        r = H.view("get_run", {"run_id": (a.run if a.run is not None else info["runs"] - 1)})
        print(f"\nrun {r['id']} by {r['attester']} at block {r['height']}  data through {r['meta']['data_through']}")
        for k in ("spec_hash", "snapshot_hash", "code_hash", "results_hash"):
            print(f"  {k:14} {r['meta'][k]}")
        print(f"  backtest coverage 80%={r['meta']['backtest_cov80_bp'] / 100:.0f}%  95%={r['meta']['backtest_cov95_bp'] / 100:.0f}%")
        for v in r["verdicts"]:
            ci = f"[{_fmt(v['ci_lo'])}, {_fmt(v['ci_hi'])}]" if v["ci_lo"] is not None else "n/a"
            print(f"  {v['claim_id']}  {v['verdict']:<12} value {_fmt(v['value']):>10}  90%CI {ci:<18} need {v['comparator']} {_fmt(v['threshold'])}")
        ch = H.view("get_challenges", {"run_id": r["id"]})
        for c in ch:
            print(f"  challenge #{c['id']} on {c['claim_id']} by {c['challenger']}: alt verdict {c['alt_verdict']} (flips: {c['flips']})")
    if info["predictions"]:
        ps = H.view("list_predictions", {"from": 0, "limit": 100})
        att = sorted({p["attester"] for p in ps})
        for who in att:
            s = H.view("scoreboard", {"attester": who})
            print(f"\nscoreboard {who}: {s['predictions']} registered, {s['resolved']} resolved, {s['hits']} hits "
                  f"({s['hits_strict']} strict; hit rate {s['hit_rate_bp'] / 100:.0f}% vs {s['mean_level_bp'] / 100:.0f}% nominal), {s['disputed']} disputed")
    return 0


# ------------------------------------------------------------------------------------------ verify
def verify(a) -> int:
    """Re-run offline on the frozen snapshot and compare every committed field with the on-chain run."""
    print("== re-running the pipeline offline on data/snapshots (no network, no keys) ==")
    res = _recompute_offline()
    import pandas as pd
    bt = pd.read_csv(S.OUT / "backtest.csv")
    cov = H.backtest_coverage(bt)
    meta, vers = H.build_run(res, cov[0], cov[1], "")
    rid = a.run if a.run is not None else H.view("run_count") - 1
    if rid < 0:
        raise SystemExit("no run on-chain yet")
    on = H.view("get_run", {"run_id": rid})
    print(f"== comparing with run {rid} on {H.contract_id()} (attester {on['attester']}, block {on['height']}) ==")
    bad, warn = 0, 0

    def row(name, a_, b_, soft=False):
        nonlocal bad, warn
        ok = a_ == b_
        tag = "MATCH" if ok else ("DIFFERS (warning)" if soft else "MISMATCH")
        if not ok:
            warn, bad = (warn + 1, bad) if soft else (warn, bad + 1)
        print(f"  {name:<16} {tag:<18} local {str(a_)[:20]}  chain {str(b_)[:20]}")

    row("spec_hash", meta["spec_hash"], on["meta"]["spec_hash"])
    row("snapshot_hash", meta["snapshot_hash"], on["meta"]["snapshot_hash"])
    row("results_hash", meta["results_hash"], on["meta"]["results_hash"], soft=True)
    row("code_hash", meta["code_hash"], on["meta"]["code_hash"], soft=True)
    row("backtest 80%/95%", cov, (on["meta"]["backtest_cov80_bp"], on["meta"]["backtest_cov95_bp"]), soft=True)
    chain_v = {v["claim_id"]: v for v in on["verdicts"]}
    for v in vers:
        o = chain_v.get(v["claim_id"])
        if o is None:
            row(v["claim_id"], v["verdict"], "(missing)")
            continue
        close = all(abs((v[k] or 0) - (o[k] or 0)) <= H.VALUE_TOLERANCE_MICRO for k in ("value", "ci_lo", "ci_hi", "threshold"))
        print(f"  {v['claim_id']:<16} {'MATCH' if v['verdict'] == o['verdict'] and close else 'MISMATCH':<18} "
              f"local {v['verdict']:<12} chain {o['verdict']:<12} value {_fmt(v['value'])} vs {_fmt(o['value'])}")
        if not (v["verdict"] == o["verdict"] and close):
            bad += 1
    npred = H.view("prediction_count")
    if npred:
        onp = []
        for i in range(0, npred, 100):
            onp += H.view("list_predictions", {"from": i, "limit": 100})
        mine = {(p["body"]["metric"], p["body"]["target_week"], p["body"]["level_bp"]): p for p in onp
                if p["attester"] == on["attester"]}
        local = H.build_predictions(D.weekly(S.load_log()))
        same = diff = 0
        for q in local:
            o = mine.get((q["metric"], q["target_week"], q["level_bp"]))
            if o is None:
                continue
            ok = all(abs(q[k] - o["body"][k]) <= max(H.VALUE_TOLERANCE_MICRO, abs(q[k]) // 10**6) for k in ("lo", "hi", "point")) \
                and q["snapshot_hash"] == o["body"]["snapshot_hash"]
            same, diff = same + ok, diff + (not ok)
        print(f"  forecasts        {'MATCH' if not diff else 'MISMATCH':<18} {same} of {same + diff} on-chain intervals reproduce from the frozen snapshot")
        bad += diff
    ch = H.view("get_challenges", {"run_id": rid})
    print(f"== {len(ch)} challenge(s) on this run; {sum(1 for c in ch if c['flips'])} flip a verdict ==")
    print("RESULT: " + ("ALL MATCH" if not bad and not warn else "VERDICTS+DATA MATCH (code/results hash differ: code was edited after publishing?)" if not bad else "MISMATCH"))
    return 1 if bad else 0


# ------------------------------------------------------------------------------------------ publish
def publish(a) -> int:
    res = _results()
    if not all(v["status"] == "snapshot" for v in res["sources"].values()):
        raise SystemExit("results.json was computed from fresh data; publish the frozen run: `python -m ledger all --offline`")
    bt = pd.read_csv(S.OUT / "backtest.csv")
    cov = H.backtest_coverage(bt)
    note = f"Evidence Ledger: {len(res['claims'])} NEAR claims, data through {res['as_of_week']}"
    meta, vers = H.build_run(res, cov[0], cov[1], note)
    args = {"run": meta, "verdicts": vers}
    if a.dry_run:
        print(json.dumps(args, indent=1))
        return 0
    if not a.signer:
        raise SystemExit("--signer <testnet account> required")
    tx = H.call("publish_run", args, a.signer, deposit="0.2 NEAR")
    rid = H.view("run_count") - 1  # the run just published (sequential ids)
    _log_tx("publish_run", rid, tx, f"results_hash={meta['results_hash'][:16]}")
    print(f"published run {rid}: {tx['url']}")
    snapshot_onchain()
    return 0


# ------------------------------------------------------------------------------------------ challenge
def challenge(a) -> int:
    if not a.claim:
        raise SystemExit("--claim C<n> required")
    rid = a.run if a.run is not None else H.view("run_count") - 1
    res = _results()
    snap_dir = a.snapshot_dir or str(S.RAW)
    recs = {v["claim_id"]: v for v in H.verdict_records(res)}
    if a.claim not in recs:
        raise SystemExit(f"{a.claim} not in local results")
    r = recs[a.claim]
    value = H.C.micro(a.value) if a.value is not None else r["value"]
    lo, hi = (H.C.micro(a.ci[0]), H.C.micro(a.ci[1])) if a.ci else (r["ci_lo"], r["ci_hi"])
    thr = H.C.micro(a.threshold) if a.threshold is not None else None
    alt_snap = H.snapshot_hash(snap_dir)
    ev = a.evidence or f"re-run {datetime.now(timezone.utc):%Y-%m-%d} code={H.code_hash()[:12]} data={snap_dir}"
    args = dict(run_id=rid, claim_id=a.claim, alt_snapshot_hash=alt_snap, alt_value=value, alt_ci_lo=lo,
                alt_ci_hi=hi, alt_threshold=thr, evidence=ev[:280])
    print(f"challenging run {rid} claim {a.claim}: alternative value {_fmt(value)} -> local rule says "
          f"{C.verdict_fp(value, r['comparator'], thr if thr is not None else r['threshold'], (lo, hi) if lo is not None else None)}")
    if a.dry_run:
        print(json.dumps(args, indent=1))
        return 0
    if not a.signer:
        raise SystemExit("--signer <testnet account> required")
    tx = H.call("challenge", args, a.signer, deposit="0.05 NEAR")
    _log_tx("challenge", f"run{rid}/{a.claim}", tx, ev[:60])
    print(f"challenge recorded: {tx['url']}")
    snapshot_onchain()
    return 0


# ------------------------------------------------------------------------------------------ predict
def predict(a) -> int:
    log = S.load_log()
    if not all(v["status"] == "snapshot" for v in log.values()):
        raise SystemExit("predict from the frozen snapshot: run `python -m ledger all --offline` first")
    w = D.weekly(log)
    items = H.build_predictions(w)
    key = lambda p: (p["metric"], p["target_week"], p["level_bp"])  # noqa: E731
    have = set()
    if not a.dry_run:
        n = H.view("prediction_count")
        for i in range(0, n, 100):
            for p in H.view("list_predictions", {"from": i, "limit": 100}):
                if p["attester"] == a.signer:
                    have.add((p["body"]["metric"], p["body"]["target_week"], p["body"]["level_bp"]))
    todo = [p for p in items if key(p) not in have]
    print(f"{len(items)} forecasts built from data through {w.index[-1]:%Y-%m-%d}; {len(todo)} to register")
    for p in todo:
        print(f"  {p['metric']:<18} {p['target_week']}  80% interval [{p['lo'] / 1e6:,.4g}, {p['hi'] / 1e6:,.4g}]  point {p['point'] / 1e6:,.4g}")
    if a.dry_run or not todo:
        return 0
    if not a.signer:
        raise SystemExit("--signer <testnet account> required")
    for i in range(0, len(todo), 12):
        chunk = todo[i:i + 12]
        tx = H.call("register_predictions", {"items": chunk}, a.signer, deposit="0.3 NEAR")
        _log_tx("register_predictions", f"{i}-{i + len(chunk) - 1}", tx, f"{len(chunk)} forecasts")
        print(f"registered {len(chunk)}: {tx['url']}")
    snapshot_onchain()
    return 0


# ------------------------------------------------------------------------------------------ resolve
def resolve(a) -> int:
    n = H.view("prediction_count")
    preds = []
    for i in range(0, n, 100):
        preds += H.view("list_predictions", {"from": i, "limit": 100})
    now_ms = int(time.time() * 1000)
    due = [p for p in preds if p["resolution"] is None and int(p["body"]["target_end_ms"]) <= now_ms]
    print(f"{n} predictions on-chain, {len(due)} past their target week and unresolved")
    if not due:
        return 0
    print("== fetching fresh data (observed values come from today's public sources) ==")
    log = S.fetch_all(force_offline=False)
    if not all(v["status"] == "fresh" for v in log.values()):
        raise SystemExit("some sources fell back to snapshots; refusing to resolve with stale data")
    w = D.weekly(log)
    src_hash = H.snapshot_hash(S.RAW)
    sent = 0
    for p in due:
        b = p["body"]
        obs = H.observed_value(w, b["metric"], b["target_week"])
        if obs is None:
            print(f"  #{p['id']} {b['metric']} {b['target_week']}: week not yet complete in the data, skipped")
            continue
        o = H.C.micro(obs)
        hit = b["lo"] <= o <= b["hi"]
        print(f"  #{p['id']} {b['metric']:<18} {b['target_week']}  observed {o / 1e6:,.4g}  interval [{b['lo'] / 1e6:,.4g}, {b['hi'] / 1e6:,.4g}]  -> {'HIT' if hit else 'MISS'}")
        if a.dry_run:
            continue
        if not a.signer:
            raise SystemExit("--signer <testnet account> required")
        tx = H.call("resolve", {"prediction_id": p["id"], "observed": o, "source_hash": src_hash}, a.signer, deposit="0.02 NEAR")
        _log_tx("resolve", p["id"], tx, f"{b['metric']} {b['target_week']} {'hit' if hit else 'miss'}")
        sent += 1
    print(f"{sent} resolution(s) sent")
    if sent:
        snapshot_onchain()
    return 0


# ------------------------------------------------------------------------------------------ claim (custom, local only)
def claim(a) -> int:
    """Evaluate a user-written claim spec on the frozen snapshot (no keys, no chain)."""
    from . import custom
    if not a.spec:
        raise SystemExit("usage: python -m ledger claim <spec.json>")
    log = S.load_log()
    w = D.weekly(log)
    r = custom.evaluate(custom.load(a.spec), w)
    ci = f"90%CI [{r['ci90'][0]:,.4g}, {r['ci90'][1]:,.4g}]" if r["ci90"] else "no interval (+-5% point rule)"
    print(f"{r['id']}  {r['verdict']}  value {r['value']:,.4g}  {ci}  need {r['comparator']} {r['threshold']:,.4g}")
    print(f"  {r['statement']}")
    print(f"  spec_hash {r['spec_hash']}  data through {r['as_of_week']}  snapshot_hash {r['snapshot_hash'][:16]}...")
    print(f"  integer record the contract would accept: value={C.micro(r['value'])} threshold={C.micro(r['threshold'])}")
    return 0
