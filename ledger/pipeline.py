"""End-to-end analysis: weekly frame -> claims -> backtest -> scenarios -> dashboard + report."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from . import claims as C
from . import dashboard as DB
from . import data as D
from . import forecast as F
from . import robustness as RB
from . import scenarios as SC
from . import sources as S
from .provenance import Registry

CACHE = S.ROOT / "data" / "cache"
SITE = S.ROOT / "site"


def _key(w: pd.DataFrame) -> str:
    h = hashlib.sha256()
    h.update(w.to_csv().encode())
    h.update((Path(F.__file__)).read_bytes())
    return h.hexdigest()[:12]


def _cached(name: str, key: str, fn):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{name}_{key}.csv"
    if p.exists():
        print(f"  cache hit: {p.name}")
        return pd.read_csv(p)
    df = fn()
    df.to_csv(p, index=False)
    print(f"  computed and cached: {p.name}")
    return df


def register_backtest(bt: pd.DataFrame, reg: Registry) -> None:
    for (metric, h, meth), g in bt.groupby(["metric", "h", "method"], sort=False):
        src = DB.METRIC_SRC[metric]
        k = f"bt.{metric}.{h}.{meth}"
        calc = (f"rolling-origin backtest, origins {g['first_origin'].iloc[0]}..{g['last_origin'].iloc[0]}, "
                f"n={int(g['n_origins'].iloc[0])}, h={h}, method={meth}")
        for lvl in ("80%", "95%"):
            r = g[g.level == lvl].iloc[0]
            reg.add(f"{k}.{lvl}", float(r.coverage), ".0%", src, f"empirical {lvl} coverage of {metric}", calc)
            if lvl == "80%":
                reg.add(f"{k}.width", float(r.width_ratio), ".1f", src, f"mean p90/p10 ratio of {metric}", calc)
                reg.add(f"{k}.h1", float(r.cov_first_half), ".0%", src, "80% coverage in first half of origins", calc)
                reg.add(f"{k}.h2", float(r.cov_second_half), ".0%", src, "80% coverage in second half of origins", calc)


def register_grid(g: pd.DataFrame, reg: Registry) -> None:
    for _, r in g.iterrows():
        k = f"grid.{int(r.cal)}.{int(r.dw)}.{r.phi}"
        reg.add(f"{k}.{r.level}", float(r.coverage), ".0%", "nb_charts",
                f"grid coverage {r.level} (cal={int(r.cal)}, drift={int(r.dw)}, phi={r.phi})", "ledger.forecast.grid")
        if r.level == "80%":
            reg.add(f"{k}.width", float(r.width_ratio_gm), ".1f", "nb_charts", "grid geometric-mean width p90/p10")


def summary_table(rows) -> str:
    out = ["", "CLAIMS", "-" * 96]
    for r in rows:
        ci = f"[{format(r['ci'][0], r['fmt'])}, {format(r['ci'][1], r['fmt'])}]" if r["ci"] else "n/a"
        out.append(f"{r['id']}  {r['verdict']:<12} value {format(r['value'], r['fmt']):>10}  90%CI {ci:<24} "
                   f"need {r['comparator']} {format(r['threshold'], r['fmt'] if r['unit'] != 'accounts' else ',.0f')}  | {r['statement'][:60]}")
    return "\n".join(out)


def run_analysis(skip_cache: bool = False, n_jobs: int = -1) -> dict:
    log = S.load_log()
    w = D.weekly(log)
    reg = Registry(log)
    asof = w.index[-1].strftime("%Y-%m-%d")
    print(f"weekly frame: {len(w)} weeks, last complete week ending {asof}")

    rows = C.evaluate(w, log, reg)
    head = {}
    try:
        a = S.load_json("rpc_status", log)["result"]["sync_info"]["latest_block_height"]
        b = S.load_json("fastnear_rpc", log)["result"]["sync_info"]["latest_block_height"]
        reg.add("chk.head_near", int(a), ",d", "rpc_status", "chain head height from rpc.mainnet.near.org")
        reg.add("chk.head_fast", int(b), ",d", "fastnear_rpc", "chain head height from free.rpc.fastnear.com")
        reg.add("chk.head_diff", abs(int(a) - int(b)), ",d", ["rpc_status", "fastnear_rpc"],
                "absolute block-height difference between the two providers (they are queried seconds apart)")
        head = {"near_rpc": int(a), "fastnear": int(b), "diff": abs(int(a) - int(b))}
        print(f"chain head check: rpc.mainnet.near.org {a} vs FastNEAR {b} (diff {abs(int(a) - int(b))} blocks)")
    except Exception as e:  # noqa: BLE001 - a cross-check must never break the analysis
        print(f"chain head check skipped: {e}")
    key = _key(w)
    bt = _cached("backtest", key, lambda: F.backtest(w, n_jobs=n_jobs))
    gr = _cached("grid", key, lambda: F.grid(w, n_jobs=n_jobs))
    sk = _cached("skill", key, lambda: F.skill(w))
    for _, r in sk.iterrows():
        for kk, nm in (("trend", "damped-trend candidate (phi 0.9)"), ("final", "shipped model")):
            reg.add(f"sk.{r.metric}.{int(r.h)}.{kk}", float(r[f"skill_{kk}"]), ".0%", DB.METRIC_SRC[r.metric],
                    f"point-forecast skill of the {nm} for {r.metric} at h={int(r.h)} vs no-change random walk "
                    f"(1 - MAE_model/MAE_rw, n={int(r.n_origins)} origins)", "ledger.forecast.skill")
    register_backtest(bt, reg)
    register_grid(gr, reg)
    sc, fans = SC.scenarios(w, reg)
    tor = SC.tornado(w, fans, reg)
    SC.implied_yield(w, sc, reg)

    rob = RB.analyze(w, log, rows)
    onchain = {}
    oc = S.ROOT / "docs" / "onchain.json"
    if oc.exists():
        onchain = json.loads(oc.read_text())
    SITE.mkdir(exist_ok=True)
    DB.build(w, log, reg, rows, bt, gr, sc, fans, tor, SITE / "index.html", C.THESIS, asof, sk,
             robust=rob, onchain=onchain)
    S.OUT.mkdir(exist_ok=True)
    w.to_csv(S.OUT / "weekly.csv")
    bt.to_csv(S.OUT / "backtest.csv", index=False)
    sk.to_csv(S.OUT / "skill.csv", index=False)
    gr.to_csv(S.OUT / "grid.csv", index=False)
    res = {"as_of_week": asof, "chain_head_check": head, "claims": [
        {"id": r["id"], "statement": r["statement"], "metric": r["metric"], "threshold": r["threshold"],
         "comparator": r["comparator"], "value": r["value"], "ci90": r["ci"], "verdict": r["verdict"],
         "sources": r["src"], "kb": r["kb"]} for r in rows],
        "sources": {k: {kk: v[kk] for kk in ("url", "status", "fetched_at_utc", "fetched_at_cst", "sha256")}
                    for k, v in log.items()}}
    (S.OUT / "results.json").write_text(json.dumps(res, indent=2))
    (S.OUT / "robustness.json").write_text(json.dumps(rob, indent=2))
    write_report(rows, bt, sc, tor, reg, log, asof, sk, rob)
    print(summary_table(rows))
    c = bt[(bt.method == "conformal") & (bt.level == "80%")]
    c95 = bt[(bt.method == "conformal") & (bt.level == "95%")]
    print("\nBACKTEST (conformal, mean over metrics): 80% interval covers "
          f"{c.coverage.mean():.0%} (h=4: {c[c.h == 4].coverage.mean():.0%}, h=12: {c[c.h == 12].coverage.mean():.0%}); "
          f"95% interval covers {c95.coverage.mean():.0%}")
    print(f"\nOpen site/index.html  |  report: output/report.md  |  fetch log: output/FETCH_LOG.json")
    return res


def write_report(rows, bt, sc, tor, reg: Registry, log, asof, sk, rob=None) -> None:
    L = [f"# NEAR Evidence Ledger: report (data through week ending {asof})", "",
         C.THESIS, "", "## Claims", "",
         "| # | Claim | Measured | 90% interval | Threshold | Verdict | Sources (fetched UTC) |",
         "|---|---|---|---|---|---|---|"]
    for r in rows:
        ci = f"{format(r['ci'][0], r['fmt'])} to {format(r['ci'][1], r['fmt'])}" if r["ci"] else "n/a"
        s = ", ".join(f"{x} ({log[x]['fetched_at_utc']})" for x in r["src"])
        thr = format(r["threshold"], r["fmt"] if r["unit"] != "accounts" else ",.0f")
        L.append(f"| {r['id']} | {r['statement']} | {format(r['value'], r['fmt'])} | {ci} | {r['comparator']} {thr} | "
                 f"**{r['verdict']}** | {s} |")
    L += ["", "## Backtest coverage (rolling origin, last 156 weekly origins; 80% / 95% nominal)", "",
          "| metric | h | method | 80% | 95% | origins | n_eff |", "|---|---|---|---|---|---|---|"]
    for (m, h, meth), g in bt.groupby(["metric", "h", "method"], sort=False):
        a = g[g.level == "80%"].iloc[0]
        b = g[g.level == "95%"].iloc[0]
        L.append(f"| {m} | {h} | {meth} | {a.coverage:.0%} | {b.coverage:.0%} | {int(a.n_origins)} | {int(a.n_eff)} |")
    L += ["", "## Point-forecast skill of the base case vs a no-change random walk (positive = better)", "",
          "| metric | h | damped-trend candidate (phi 0.9) | shipped model |", "|---|---|---|---|"]
    for _, r in sk.iterrows():
        L.append(f"| {r.metric} | {int(r.h)} | {r.skill_trend:+.0%} | {r.skill_final:+.0%} |")
    L += ["", "## Scenarios, 12 weeks ahead (bear=p10, base=p50, bull=p90)", "",
          "| metric | latest | bear | base | bull | target week |", "|---|---|---|---|---|---|"]
    for m, r in sc.iterrows():
        f = ",.2f" if m == "price" else ",.0f"
        L.append(f"| {r['label']} | {format(r['now'], f)} | {format(r['bear'], f)} | {format(r['base'], f)} | "
                 f"{format(r['bull'], f)} | {r['target_week']} |")
    L += ["", "## Sensitivity of weekly network fees (1 sigma per factor)", "", "| factor | sigma (log) | -1 sigma | +1 sigma |", "|---|---|---|---|"]
    for _, r in tor.iterrows():
        L.append(f"| {r['label']} | {r['sigma_log']:.3f} | {r['low']:,.0f} | {r['high']:,.0f} |")
    if rob:
        L += ["", "## How fragile is each verdict? (flip distance and variants)", "",
              "| claim | verdict | threshold change that flips it | variants with the same verdict | label |", "|---|---|---|---|---|"]
        for r in rob:
            fc = "none within +-200%" if r["flip_change"] is None else f"{r['flip_change']:+.1%}"
            n_same = sum(1 for v in r["variants"] if v["verdict"] == r["verdict"])
            L.append(f"| {r['id']} | {r['verdict']} | {fc} | {n_same} of {len(r['variants'])} | {r['label']} |")
    L += ["", "Source ids and URLs: see output/FETCH_LOG.json. Every number on the dashboard (site/index.html) is a link to its source."]
    (S.OUT / "report.md").write_text("\n".join(L) + "\n")
