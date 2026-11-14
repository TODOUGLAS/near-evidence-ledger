"""Add your own falsifiable claim without touching Python: a JSON spec + `python -m ledger claim <spec.json>`.

Spec fields (all required unless marked):
  id, statement         free text
  series                a column of the weekly frame (see SERIES)
  kind                  "level"        stat of the last `window` weeks
                        "ratio_prior"  stat of the last `window` weeks / same stat `lag` weeks earlier (optional lag, default 52)
                        "growth"       last value / value `window` weeks earlier - 1
  stat                  "median" | "mean" | "last"   (level, ratio_prior)
  window                int, weeks (2..156)
  comparator, threshold ">=" | "<=", number
The verdict is the same rule as the eight core claims (claims.py): 90% moving-block bootstrap interval where there is
a sampling model (level, ratio_prior), else a +-5% point rule. The spec is hashed (`spec_hash`) so a claim can be
pre-registered before its data moves. Evaluated on the frozen snapshot by default.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import chain as H
from . import claims as C
from .stats import block_bootstrap_idx

SERIES = ["txns", "active_accounts", "new_accounts", "net_fees_usd", "net_fees_near", "price", "circ_supply",
          "total_supply", "tvl", "stable_usd", "dl_fees_usd", "dex_vol_usd", "mcap_usd", "fee_per_txn_near"]
STATS = {"median": np.median, "mean": np.mean, "last": lambda a: a[-1]}


def validate(spec: dict) -> dict:
    need = ["id", "statement", "series", "kind", "window", "comparator", "threshold"]
    miss = [k for k in need if k not in spec]
    if miss:
        raise ValueError(f"missing fields: {miss}")
    if spec["series"] not in SERIES:
        raise ValueError(f"series must be one of {SERIES}")
    if spec["kind"] not in ("level", "ratio_prior", "growth"):
        raise ValueError("kind must be level | ratio_prior | growth")
    if spec["comparator"] not in (">=", "<="):
        raise ValueError("comparator must be >= or <=")
    if not isinstance(spec["window"], int) or not 2 <= spec["window"] <= 156:
        raise ValueError("window must be an integer 2..156")
    if not isinstance(spec["threshold"], (int, float)):
        raise ValueError("threshold must be a number")
    if spec["kind"] != "growth" and spec.get("stat", "median") not in STATS:
        raise ValueError("stat must be median | mean | last")
    return spec


def evaluate(spec: dict, w: pd.DataFrame) -> dict:
    spec = validate(spec)
    s = w[spec["series"]].dropna()
    n, kind = spec["window"], spec["kind"]
    stat = STATS[spec.get("stat", "median")]
    lag = int(spec.get("lag", 52))
    g = np.random.default_rng(int(H.sha(H.canon(spec))[:8], 16))
    ci = None
    if kind == "growth":
        if len(s) < n + 1:
            raise ValueError("series too short for this window")
        value = float(s.iloc[-1] / s.iloc[-n - 1] - 1)
    elif kind == "level":
        if len(s) < n:
            raise ValueError("series too short for this window")
        x = s.iloc[-n:].to_numpy()
        value = float(stat(x))
        vs = [stat(x[block_bootstrap_idx(n, 3, g)]) for _ in range(2000)]
        ci = (float(np.percentile(vs, 5)), float(np.percentile(vs, 95)))
    else:
        if len(s) < n + lag:
            raise ValueError("series too short for this window and lag")
        cur = s.iloc[-n:].to_numpy()
        prev = s.iloc[-n - lag:-lag].to_numpy()
        value = float(stat(cur) / stat(prev))
        vs = [stat(cur[block_bootstrap_idx(n, 3, g)]) / stat(prev[block_bootstrap_idx(n, 3, g)]) for _ in range(2000)]
        ci = (float(np.percentile(vs, 5)), float(np.percentile(vs, 95)))
    thr = float(spec["threshold"])
    verdict = C.verdict_fp(C.micro(value), spec["comparator"], C.micro(thr),
                           (C.micro(ci[0]), C.micro(ci[1])) if ci else None)
    return dict(id=spec["id"], statement=spec["statement"], value=value, ci90=ci, threshold=thr,
                comparator=spec["comparator"], verdict=verdict, spec_hash=H.sha(H.canon(spec)),
                as_of_week=w.index[-1].strftime("%Y-%m-%d"), snapshot_hash=H.snapshot_hash())


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())
