"""Bear/base/bull scenarios (p10/p50/p90 of the conformal forecast) and a sensitivity analysis.

Network fees obey an exact identity:  fees_usd = txns x fee_per_txn_near x price.
The tornado moves each factor to its own +/-1 sigma (sigma taken from the 80% interval of that
factor's forecast) while the other two stay at their medians.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import forecast as F
from .provenance import Registry

H = 12
Z80 = 1.2815515655446004
SCEN_METRICS = {"txns": ("Weekly transactions", "nb_charts"),
                "active_accounts": ("Weekly-median daily active accounts", "nb_charts"),
                "net_fees_usd": ("Weekly network fees (USD)", "nb_charts"),
                "price": ("NEAR price (USD)", "nb_charts"),
                "tvl": ("TVL (USD)", "dl_tvl"),
                "stable_usd": ("Stablecoins on NEAR (USD)", "dl_stable")}


def scenarios(w: pd.DataFrame, reg: Registry) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    fans = {m: F.fan(w, m, H) for m in list(SCEN_METRICS) + ["fee_per_txn_near"]}
    rows = []
    for m, (label, src) in SCEN_METRICS.items():
        f = fans[m]
        last = w[m].dropna().iloc[-1]
        target = f.index[H - 1].strftime("%Y-%m-%d")
        r = dict(metric=m, label=label, now=float(last), target_week=target)
        for k, col in (("bear", "p100"), ("base", "p500"), ("bull", "p900")):
            r[k] = float(f.iloc[H - 1][col])
            reg.add(f"scn.{m}.{k}", r[k], ",.2f" if m == "price" else ",.0f", src,
                    f"{k} scenario for {label}, week ending {target} (conformal "
                    f"{'p10' if k == 'bear' else 'p50' if k == 'base' else 'p90'}, h={H})",
                    "ledger.forecast.fan")
        reg.add(f"scn.{m}.now", float(last), ",.2f" if m == "price" else ",.0f", src,
                f"latest complete week of {label}")
        rows.append(r)
    sc = pd.DataFrame(rows).set_index("metric")
    return sc, fans


def tornado(w: pd.DataFrame, fans: dict[str, pd.DataFrame], reg: Registry) -> pd.DataFrame:
    factors = {"txns": "Transactions", "fee_per_txn_near": "Fee per txn (NEAR)", "price": "NEAR price"}
    med = {k: float(fans[k].iloc[H - 1]["p500"]) for k in factors}
    sig = {k: float((np.log(fans[k].iloc[H - 1]["p900"]) - np.log(fans[k].iloc[H - 1]["p100"]))
                    / (2 * Z80)) for k in factors}
    base = med["txns"] * med["fee_per_txn_near"] * med["price"]
    rows = []
    for k, label in factors.items():
        lo = base * np.exp(-sig[k])
        hi = base * np.exp(sig[k])
        rows.append(dict(factor=k, label=label, sigma_log=sig[k], low=lo, high=hi, base=base,
                         swing=hi - lo))
        src = ["nb_charts"]
        reg.add(f"tor.{k}.sigma", sig[k], ".3f", src,
                f"1-sigma of log {label} at h={H} (from the 80% conformal interval / 2.563)")
        reg.add(f"tor.{k}.low", lo, ",.0f", src, f"network fees (USD/week) if {label} is -1 sigma")
        reg.add(f"tor.{k}.high", hi, ",.0f", src, f"network fees (USD/week) if {label} is +1 sigma")
    reg.add("tor.base", base, ",.0f", "nb_charts",
            "weekly network fees (USD) at the product of the three factor medians")
    direct = float(fans["net_fees_usd"].iloc[H - 1]["p500"]) if "net_fees_usd" in fans else float("nan")
    reg.add("tor.direct_median", direct, ",.0f", "nb_charts",
            "median of the directly forecast weekly network fees (cross-check of the identity)")
    return pd.DataFrame(rows).sort_values("swing", ascending=False).reset_index(drop=True)


def implied_yield(w: pd.DataFrame, sc: pd.DataFrame, reg: Registry) -> dict[str, float]:
    """Ecosystem fee yield (C3) under scenario prices, fees held at the 13-week run-rate."""
    circ = float(w["circ_supply"].iloc[-1])
    ann = reg.v("c3.fees_ann")
    out = {}
    for k in ("bear", "base", "bull"):
        mcap = float(sc.loc["price", k]) * circ
        y = ann / mcap
        out[k] = y
        reg.add(f"scn.yield.{k}", y, ".2%", ["dl_fees", "nb_charts"],
                f"C3 fee yield if price is the {k} scenario price and ecosystem fees stay at the "
                f"13-week run-rate", "c3.fees_ann / (scenario price x circulating supply)")
    return out
