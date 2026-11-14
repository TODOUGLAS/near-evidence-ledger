"""Falsifiable claims. Thresholds are fixed in CLAIMS below (written before the
verdicts were computed; see docs/THRESHOLDS_RATIONALE.md). Verdicts are computed, never typed.

Verdict rule
  * statistic has a bootstrap interval (90%): SUPPORTED if the whole interval passes the
    threshold, REFUTED if the whole interval fails it, otherwise INCONCLUSIVE;
  * point-in-time statistic without a sampling model: INCONCLUSIVE if within +/-5% (relative)
    of the threshold, otherwise decided by the point value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import sources as S
from .provenance import Registry
from .stats import boot_ci, boot_ci_pair

THESIS = (
    "NEAR is an infrastructure bet on settlement flow for agents and intents, not on raw "
    "layer-1 transaction counts. The thesis holds only if (a) real fee revenue exists on the "
    "chain, (b) liquidity and stablecoins stay on it, (c) validation stays decentralised, "
    "(d) dilution stays modest and (e) intent flow, the settlement volume of NEAR Intents, keeps growing and "
    "pays a fee. The risks are shrinking organic usage and a price that does not track usage. Each statement below is a claim with a numeric threshold that the data "
    "can refute.")

# id, statement, metric, window, comparator, threshold, sources, KB refs
CLAIMS = [
    dict(id="C1", metric="txns_yoy_ratio", comparator=">=", threshold=1.0, unit="x",
         statement="Usage is not shrinking: median weekly transactions of the last 13 "
                   "weeks are at least equal to the same 13 weeks one year earlier.",
         window="last 13 complete weeks vs the same 13 weeks 52 weeks earlier",
         src=["nb_charts"], kb=["b132-00274", "b104-00723"]),
    dict(id="C2", metric="active_accounts_median", comparator=">=", threshold=100_000, unit="accounts",
         statement="The user base is large: median of weekly-median daily active accounts over "
                   "the last 13 weeks is at least 100,000.",
         window="last 13 complete weeks", src=["nb_charts"], kb=["b104-00723"]),
    dict(id="C3", metric="fee_yield_ecosystem", comparator=">=", threshold=0.01, unit="of mcap",
         statement="Real revenue exists: fees paid on the NEAR chain (network + protocols, "
                   "DefiLlama), annualised from the last 13 weeks, are at least 1% of current "
                   "market capitalisation.",
         window="last 13 complete weeks x4, over spot market cap at fetch time",
         src=["dl_fees", "nb_stats"], kb=["b168-00630"]),
    dict(id="C4", metric="tvl_vs_median", comparator=">=", threshold=1.0, unit="x",
         statement="DeFi liquidity holds: latest weekly TVL is at least its trailing 52-week "
                   "median.", window="latest complete week vs trailing 52 weeks",
         src=["dl_tvl"], kb=["b104-00723"]),
    dict(id="C5", metric="stable_growth_13w", comparator=">=", threshold=0.05, unit="change",
         statement="Stablecoin float is growing: stablecoin supply on NEAR is at least 5% "
                   "higher than 13 weeks earlier.", window="latest vs 13 weeks earlier",
         src=["dl_stable"], kb=["b114-01085"]),
    dict(id="C6", metric="price_usage_corr", comparator=">=", threshold=0.2, unit="corr",
         statement="Price tracks usage: over the last 52 weeks the correlation between weekly "
                   "log change of price and weekly log change of active accounts is at least 0.2.",
         window="last 52 weekly changes", src=["nb_charts"], kb=["b193-00277"]),
    dict(id="C7", metric="nakamoto", comparator=">=", threshold=10, unit="validators",
         statement="Validation is decentralised: at least 10 validators are needed to control "
                   "one third of the stake (the BFT safety threshold).",
         window="current epoch", src=["rpc_validators"], kb=[]),
    dict(id="C8", metric="supply_growth_52w", comparator="<=", threshold=0.05, unit="change",
         statement="Dilution is modest: total supply grew by at most 5% over the last 52 weeks.",
         window="latest vs 52 weeks earlier", src=["nb_charts"], kb=[]),
    # added 2026-11-14 (v2) after the author had seen DefiLlama's 30-day aggregate for NEAR Intents (volume ~3.8B USD,
    # fees ~5.8M USD) but BEFORE any weekly value of these two claims was computed; thresholds are round numbers
    # (momentum: ratio >= 1; monetisation: 10 bps) and are not tuned to a verdict. See docs/THRESHOLDS_RATIONALE.md.
    dict(id="C9", metric="intents_qoq_ratio", comparator=">=", threshold=1.0, unit="x",
         statement="Intent flow keeps growing: median weekly NEAR Intents volume of the last 13 weeks is at least "
                   "the median of the 13 weeks before them.",
         window="last 13 complete weeks vs the 13 weeks before", src=["dl_intents_vol"], kb=[]),
    dict(id="C10", metric="intents_take_rate", comparator=">=", threshold=0.001, unit="of volume",
         statement="Intent flow monetises: fees DefiLlama attributes to NEAR Intents are at least 0.10% of its "
                   "volume over the last 13 weeks.",
         window="last 13 complete weeks", src=["dl_intents_vol", "dl_intents_fees"], kb=[]),
]


def _passes(v: float, cmp_: str, thr: float) -> bool:
    return v >= thr if cmp_ == ">=" else v <= thr


def verdict(v: float, cmp_: str, thr: float, ci: tuple[float, float] | None) -> str:
    if ci is not None:
        lo, hi = ci
        if _passes(lo, cmp_, thr) and _passes(hi, cmp_, thr):
            return "SUPPORTED"
        if not _passes(lo, cmp_, thr) and not _passes(hi, cmp_, thr):
            return "REFUTED"
        return "INCONCLUSIVE"
    if abs(v - thr) <= 0.05 * abs(thr):
        return "INCONCLUSIVE"
    return "SUPPORTED" if _passes(v, cmp_, thr) else "REFUTED"


MICRO = 1_000_000


def micro(x: float) -> int:
    """Fixed-point (6 decimals) used on-chain. Python round() is half-to-even; fine, it is only the encoding."""
    return int(round(float(x) * MICRO))


def verdict_fp(v: int, cmp_: str, thr: int, ci: tuple[int, int] | None) -> str:
    """Integer twin of `verdict`; this exact rule is also executed by the NEAR contract
    (contract/src/rule.rs). conformance: contract/tests/verdict_vectors.json."""
    ok = (lambda x: x >= thr) if cmp_ == ">=" else (lambda x: x <= thr)
    if ci is not None:
        a, b = ok(ci[0]), ok(ci[1])
        return "SUPPORTED" if (a and b) else "REFUTED" if (not a and not b) else "INCONCLUSIVE"
    if abs(v - thr) * 100 <= 5 * abs(thr):
        return "INCONCLUSIVE"
    return "SUPPORTED" if ok(v) else "REFUTED"


def nakamoto(stakes: np.ndarray, frac: float = 1 / 3) -> int:
    s = np.sort(np.asarray(stakes, float))[::-1]
    c = np.cumsum(s) / s.sum()
    return int(np.searchsorted(c, frac, side="right") + 1)


def compute_metrics(w: pd.DataFrame, log: dict, reg: Registry) -> dict[str, dict]:
    """Return {metric: {value, ci, extra}} and register every displayed number."""
    out: dict[str, dict] = {}
    last = w.index[-1]
    asof = last.strftime("%Y-%m-%d")

    # C1 -------------------------------------------------------------------
    cur = w["txns"].iloc[-13:].to_numpy()
    prev = w["txns"].iloc[-65:-52].to_numpy()
    ratio = float(np.median(cur) / np.median(prev))
    g_c = np.random.default_rng(11)
    lo_hi = []
    from .stats import block_bootstrap_idx
    for _ in range(2000):
        a = cur[block_bootstrap_idx(13, 3, g_c)]
        b = prev[block_bootstrap_idx(13, 3, g_c)]
        lo_hi.append(np.median(a) / np.median(b))
    ci1 = (float(np.percentile(lo_hi, 5)), float(np.percentile(lo_hi, 95)))
    out["txns_yoy_ratio"] = dict(value=ratio, ci=ci1)
    reg.add("c1.cur_median_txns", float(np.median(cur)), ",.0f", "nb_charts",
            f"median weekly txns, 13 weeks ending {asof}", "median(txns[-13:])")
    reg.add("c1.prev_median_txns", float(np.median(prev)), ",.0f", "nb_charts",
            "median weekly txns, same 13 weeks one year earlier", "median(txns[-65:-52])")

    # C2 -------------------------------------------------------------------
    aa = w["active_accounts"].iloc[-13:].to_numpy()
    out["active_accounts_median"] = dict(
        value=float(np.median(aa)), ci=boot_ci(aa, np.median, block=3, seed=2))
    reg.add("c2.peak_active_accounts", float(w["active_accounts"].max()), ",.0f", "nb_charts",
            "highest weekly-median daily active accounts in history",
            f"max over weeks to {asof}")

    # C3 -------------------------------------------------------------------
    f13 = w["dl_fees_usd"].dropna().iloc[-13:].to_numpy()
    mcap = float(S.load_json("nb_stats", log)["stats"][0]["market_cap"])
    ann = lambda x: float(np.sum(x) * 4)  # noqa: E731
    est = ann(f13) / mcap
    g = np.random.default_rng(3)
    vals = [np.sum(f13[block_bootstrap_idx(13, 3, g)]) * 4 / mcap for _ in range(2000)]
    out["fee_yield_ecosystem"] = dict(
        value=est, ci=(float(np.percentile(vals, 5)), float(np.percentile(vals, 95))))
    reg.add("c3.mcap_spot", mcap, ",.0f", "nb_stats", "spot market capitalisation (USD) at fetch")
    reg.add("c3.fees_ann", ann(f13), ",.0f", "dl_fees",
            "13-week DefiLlama chain fees x4 (USD, annualised)", "sum(dl_fees_usd[-13:])*4")
    net13 = float(w["net_fees_usd"].iloc[-13:].sum() * 4)
    reg.add("c3.net_fees_ann", net13, ",.0f", "nb_charts",
            "13-week protocol-level network fees x4 (USD): gas actually paid to the chain",
            "sum(net_fees_usd[-13:])*4")
    reg.add("c3.net_fee_yield", net13 / mcap, ".4%", ["nb_charts", "nb_stats"],
            "network-only fee yield on market cap (gas only, no app fees)")

    # C4 -------------------------------------------------------------------
    tvl = w["tvl"].dropna()
    t_now = float(tvl.iloc[-1])
    tmed = tvl.iloc[-53:-1].to_numpy()
    g = np.random.default_rng(4)
    vals = [t_now / np.median(tmed[block_bootstrap_idx(len(tmed), 4, g)]) for _ in range(2000)]
    out["tvl_vs_median"] = dict(value=t_now / float(np.median(tmed)),
                                ci=(float(np.percentile(vals, 5)), float(np.percentile(vals, 95))))
    reg.add("c4.tvl_now", t_now, ",.0f", "dl_tvl", f"NEAR TVL (USD), week ending {tvl.index[-1]:%Y-%m-%d}")
    reg.add("c4.tvl_med52", float(np.median(tmed)), ",.0f", "dl_tvl", "trailing 52-week median TVL (USD)")

    # C5 -------------------------------------------------------------------
    st = w["stable_usd"].dropna()
    g13 = float(st.iloc[-1] / st.iloc[-14] - 1)
    out["stable_growth_13w"] = dict(value=g13, ci=None)
    reg.add("c5.stable_now", float(st.iloc[-1]), ",.0f", "dl_stable", "stablecoins on NEAR (USD), latest week")
    reg.add("c5.stable_prev", float(st.iloc[-14]), ",.0f", "dl_stable", "stablecoins on NEAR (USD), 13 weeks earlier")

    # C6 -------------------------------------------------------------------
    lp = np.log(w["price"]).diff().iloc[-52:].to_numpy()
    la = np.log(w["active_accounts"]).diff().iloc[-52:].to_numpy()
    cor = lambda x, y: float(np.corrcoef(x, y)[0, 1])  # noqa: E731
    out["price_usage_corr"] = dict(value=cor(lp, la), ci=boot_ci_pair(lp, la, cor, block=4, seed=6))

    # C7 -------------------------------------------------------------------
    cv = S.load_json("rpc_validators", log)["result"]["current_validators"]
    stakes = np.array([float(v["stake"]) for v in cv])
    nk = nakamoto(stakes)
    out["nakamoto"] = dict(value=float(nk), ci=None)
    reg.add("c7.n_validators", len(cv), ",d", "rpc_validators", "validators in the current epoch")
    reg.add("c7.top1_share", float(stakes.max() / stakes.sum()), ".2%", "rpc_validators",
            "stake share of the largest validator")
    reg.add("c7.top10_share", float(np.sort(stakes)[::-1][:10].sum() / stakes.sum()), ".1%",
            "rpc_validators", "stake share of the ten largest validators")

    # C8 -------------------------------------------------------------------
    ts = w["total_supply"]
    sg = float(ts.iloc[-1] / ts.iloc[-53] - 1)
    out["supply_growth_52w"] = dict(value=sg, ci=None)
    reg.add("c8.supply_now", float(ts.iloc[-1]), ",.0f", "nb_charts", "total supply (NEAR), latest week")
    reg.add("c8.supply_prev", float(ts.iloc[-53]), ",.0f", "nb_charts", "total supply (NEAR), 52 weeks earlier")

    # C9 / C10 --------------------------------------------------------------
    iv = w["intents_vol_usd"].dropna()
    cur, prev = iv.iloc[-13:].to_numpy(), iv.iloc[-26:-13].to_numpy()
    g = np.random.default_rng(9)
    from .stats import block_bootstrap_idx
    vals = [np.median(cur[block_bootstrap_idx(13, 3, g)]) / np.median(prev[block_bootstrap_idx(13, 3, g)])
            for _ in range(2000)]
    out["intents_qoq_ratio"] = dict(value=float(np.median(cur) / np.median(prev)),
                                    ci=(float(np.percentile(vals, 5)), float(np.percentile(vals, 95))))
    reg.add("c9.cur_median_vol", float(np.median(cur)), ",.0f", "dl_intents_vol",
            f"median weekly NEAR Intents volume (USD), 13 weeks ending {asof}", "median(intents_vol_usd[-13:])")
    reg.add("c9.prev_median_vol", float(np.median(prev)), ",.0f", "dl_intents_vol",
            "median weekly NEAR Intents volume (USD), the 13 weeks before", "median(intents_vol_usd[-26:-13])")
    both = w[["intents_vol_usd", "intents_fees_usd"]].dropna().iloc[-13:]
    vv, ff = both["intents_vol_usd"].to_numpy(), both["intents_fees_usd"].to_numpy()
    rate = lambda a, b: float(np.sum(b) / np.sum(a))  # noqa: E731
    out["intents_take_rate"] = dict(value=rate(vv, ff), ci=boot_ci_pair(vv, ff, rate, block=3, seed=10))
    reg.add("c10.vol_13w", float(vv.sum()), ",.0f", "dl_intents_vol", "13-week NEAR Intents volume (USD)")
    reg.add("c10.fees_13w", float(ff.sum()), ",.0f", "dl_intents_fees", "13-week fees attributed to NEAR Intents (USD)")
    return out


def evaluate(w: pd.DataFrame, log: dict, reg: Registry) -> list[dict]:
    m = compute_metrics(w, log, reg)
    rows = []
    for c in CLAIMS:
        r = m[c["metric"]]
        v, ci = r["value"], r["ci"]
        verd = verdict(v, c["comparator"], c["threshold"], ci)
        fm = {"x": ".2f", "accounts": ",.0f", "of mcap": ".2%", "change": ".1%", "corr": ".2f",
              "validators": ".0f", "of volume": ".3%"}[c["unit"]]
        reg.add(f"{c['id']}.value", v, fm, c["src"], f"{c['id']} measured value", c["metric"])
        reg.add(f"{c['id']}.threshold", c["threshold"], fm if c["unit"] != "accounts" else ",.0f",
                c["src"], f"{c['id']} pre-declared threshold ({c['comparator']})")
        if ci:
            reg.add(f"{c['id']}.ci_lo", ci[0], fm, c["src"], f"{c['id']} 90% bootstrap lower bound")
            reg.add(f"{c['id']}.ci_hi", ci[1], fm, c["src"], f"{c['id']} 90% bootstrap upper bound")
        rows.append({**c, "value": v, "ci": ci, "verdict": verd, "fmt": fm})
    return rows
