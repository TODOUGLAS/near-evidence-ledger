"""Load the raw JSON sources into tidy weekly frames.

Rules (applied identically to every series):
* the current, still-incomplete UTC day (and anything later) is dropped;
* weeks are ISO weeks ending Sunday; only complete weeks are kept;
* flows are summed (txns, fees, volume); stocks take the end-of-week value
  (price, TVL, stablecoins, supply); active accounts take the weekly MEDIAN of the
  daily values because the daily series is spiky (single-day bot bursts).
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import sources as S

YOCTO = 1e24


def _cutoff(log: dict, sid: str) -> pd.Timestamp:
    """First UTC day that is NOT complete when the source was fetched."""
    ts = log[sid]["fetched_at_utc"]
    if ts == "unknown":
        return pd.Timestamp(datetime.now(timezone.utc).date())
    return pd.Timestamp(ts[:10])


def _daily_from_pairs(pairs, col: str, cutoff: pd.Timestamp) -> pd.Series:
    s = pd.Series({pd.Timestamp(int(t), unit="s").normalize(): float(v) for t, v in pairs},
                  name=col).sort_index()
    return s[s.index < cutoff]


def nb_daily(log: dict) -> pd.DataFrame:
    rows = S.load_json("nb_charts", log)["charts"]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    num = ["near_price", "market_cap", "total_supply", "circulating_supply", "txns", "txn_fee",
           "txn_fee_usd", "new_accounts", "active_accounts", "txn_volume_usd", "active_contracts",
           "new_contracts"]
    for c in num:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["total_supply"] /= YOCTO
    df["circulating_supply"] /= YOCTO
    df["txn_fee"] /= YOCTO  # NEAR
    df = df.set_index("date").sort_index()
    df = df[df.index < _cutoff(log, "nb_charts")]
    df = df[df["near_price"] > 0]
    return df


def dl_daily(log: dict) -> dict[str, pd.Series]:
    out = {}
    c = _cutoff(log, "dl_tvl")
    out["tvl"] = _daily_from_pairs([(r["date"], r["tvl"]) for r in S.load_json("dl_tvl", log)],
                                   "tvl", c)
    st = S.load_json("dl_stable", log)
    out["stable_usd"] = _daily_from_pairs(
        [(r["date"], r["totalCirculatingUSD"]["peggedUSD"]) for r in st
         if r.get("totalCirculatingUSD")], "stable_usd", _cutoff(log, "dl_stable"))
    out["dl_fees_usd"] = _daily_from_pairs(S.load_json("dl_fees", log)["totalDataChart"],
                                           "dl_fees_usd", _cutoff(log, "dl_fees"))
    out["intents_vol_usd"] = _daily_from_pairs(S.load_json("dl_intents_vol", log)["totalDataChart"],
                                               "intents_vol_usd", _cutoff(log, "dl_intents_vol"))
    out["intents_fees_usd"] = _daily_from_pairs(S.load_json("dl_intents_fees", log)["totalDataChart"],
                                                "intents_fees_usd", _cutoff(log, "dl_intents_fees"))
    out["dex_vol_usd"] = _daily_from_pairs(S.load_json("dl_dex", log)["totalDataChart"],
                                           "dex_vol_usd", _cutoff(log, "dl_dex"))
    return out


def weekly(log: dict) -> pd.DataFrame:
    nb = nb_daily(log)
    dl = dl_daily(log)
    wk = lambda s: s.index.to_period("W-SUN")  # noqa: E731
    agg = pd.DataFrame({
        "txns": nb["txns"].groupby(wk(nb)).sum(),
        "active_accounts": nb["active_accounts"].groupby(wk(nb)).median(),
        "new_accounts": nb["new_accounts"].groupby(wk(nb)).sum(),
        "net_fees_usd": nb["txn_fee_usd"].groupby(wk(nb)).sum(),
        "net_fees_near": nb["txn_fee"].groupby(wk(nb)).sum(),
        "price": nb["near_price"].groupby(wk(nb)).last(),
        "circ_supply": nb["circulating_supply"].groupby(wk(nb)).last(),
        "total_supply": nb["total_supply"].groupby(wk(nb)).last(),
        "days": nb["txns"].groupby(wk(nb)).count(),
    })
    for k in ("tvl", "stable_usd"):
        s = dl[k]
        agg[k] = s.groupby(wk(s)).last()
        agg[k + "_days"] = s.groupby(wk(s)).count()
    for k in ("dl_fees_usd", "dex_vol_usd", "intents_vol_usd", "intents_fees_usd"):
        s = dl[k]
        agg[k] = s.groupby(wk(s)).sum(min_count=7)
    # keep complete weeks only (7 daily observations in the NearBlocks base series)
    agg = agg[agg["days"] == 7].drop(columns=["days"])
    for k in ("tvl", "stable_usd"):
        agg.loc[agg[k + "_days"] < 7, k] = np.nan
        agg = agg.drop(columns=[k + "_days"])
    agg["mcap_usd"] = agg["price"] * agg["circ_supply"]
    agg["fee_per_txn_near"] = agg["net_fees_near"] / agg["txns"]
    agg.index = agg.index.to_timestamp(how="end").normalize()  # week-ending Sunday
    agg.index.name = "week_end"
    return agg


def week_label(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%d")
