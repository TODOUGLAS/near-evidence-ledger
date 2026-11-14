"""Probabilistic forecasts of weekly log metrics and a rolling-origin coverage backtest.

Three interval methods are compared on every metric and horizon:
  gauss    : log random walk, sigma from the last 52 weekly changes (naive baseline)
  conformal: no-change point forecast (PHI=0; a damped drift is available via PHI>0) + empirical
             (split-conformal style) quantiles of its own past h-step errors, using only errors
             already observed at the origin
  qgbm     : direct quantile gradient boosting on lag features (one model per h and quantile)
No method sees data after its forecast origin (see tests/test_no_leakage.py).
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import GradientBoostingRegressor

from .stats import wilson

PHI = 0.0            # drift damping; 0 = no-change (random-walk) centre. 0.9 was the first candidate
                     # and lost to the random walk in 16/16 metric-horizon cells (see skill())
DRIFT_W = 8          # weeks used for the drift
CAL_N = 104          # most recent h-step errors used as calibration set
MIN_CAL = 30
MIN_T = 26           # features need 26 weeks of history
LEVELS = {"80%": (0.10, 0.90), "95%": (0.025, 0.975)}
QS = [0.025, 0.10, 0.50, 0.90, 0.975]
EVAL_WEEKS = 156     # held-out evaluation origins: the last 3 years of origins
METRICS = ["txns", "active_accounts", "net_fees_usd", "price", "tvl", "stable_usd",
           "dl_fees_usd", "fee_per_txn_near"]


def _d(y: np.ndarray) -> np.ndarray:
    return np.r_[np.nan, np.diff(y)]


def drift_path(d: np.ndarray, t: int, h: int) -> float:
    dr = float(np.mean(d[t - DRIFT_W + 1:t + 1]))
    return float(dr * sum(PHI ** i for i in range(1, h + 1)))


def cal_errors(y: np.ndarray, d: np.ndarray, t: int, h: int) -> np.ndarray:
    """h-step errors of the damped-drift forecast for origins t' with t'+h <= t."""
    lo = DRIFT_W
    hi = t - h
    if hi < lo:
        return np.array([])
    e = [y[s + h] - y[s] - drift_path(d, s, h) for s in range(lo, hi + 1)]
    return np.asarray(e)[-CAL_N:]


def conformal_q(y, d, t, h, probs):
    e = cal_errors(y, d, t, h)
    if len(e) < MIN_CAL:
        return None
    m = drift_path(d, t, h)
    return {p: float(y[t] + m + np.quantile(e, p)) for p in probs}


def gauss_q(y, d, t, h, probs):
    s = float(np.std(d[max(1, t - 51):t + 1], ddof=1))
    return {p: float(y[t] + norm.ppf(p) * s * np.sqrt(h)) for p in probs}


def _feat(y, d, t):
    return [d[t], d[t - 1], d[t - 2], d[t - 3], np.mean(d[t - 7:t + 1]),
            np.std(d[t - 25:t + 1], ddof=1), y[t] - np.mean(y[t - 25:t + 1])]


def qgbm_q(y, d, t, h, probs):
    lo = MIN_T
    hi = t - h
    if hi - lo + 1 < MIN_CAL:
        return None
    X = np.array([_feat(y, d, s) for s in range(lo, hi + 1)])
    Y = np.array([y[s + h] - y[s] for s in range(lo, hi + 1)])
    x = np.array([_feat(y, d, t)])
    out = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for p in probs:
            m = GradientBoostingRegressor(loss="quantile", alpha=p, n_estimators=60, max_depth=2,
                                          learning_rate=0.05, subsample=0.8, min_samples_leaf=5,
                                          random_state=0)
            m.fit(X, Y)
            out[p] = float(y[t] + m.predict(x)[0])
    vals = np.sort(np.array([out[p] for p in probs]))
    return {p: float(v) for p, v in zip(sorted(probs), vals)}  # enforce monotone quantiles


METHODS = {"gauss": gauss_q, "conformal": conformal_q, "qgbm": qgbm_q}


def log_series(w: pd.DataFrame, metric: str) -> pd.Series:
    s = w[metric].dropna()
    s = s[s > 0]
    return np.log(s)


def _bt_task(metric: str, idx: list[str], y: np.ndarray, h: int, gbm_step: int,
             methods: tuple[str, ...] | None = None, cfg: dict | None = None) -> list[dict]:
    global CAL_N, DRIFT_W, PHI
    if cfg:  # used by the hyper-parameter grid (each task sets all three)
        CAL_N, DRIFT_W, PHI = cfg["cal"], cfg["dw"], cfg["phi"]
    d = _d(y)
    n = len(y)
    rows = []
    first = max(MIN_T, DRIFT_W + MIN_CAL + h - 1)  # conformal needs MIN_CAL past errors
    origins = list(range(max(first, n - h - EVAL_WEEKS), n - h))
    for name, fn in METHODS.items():
        if methods and name not in methods:
            continue
        ts = origins if name != "qgbm" else origins[::gbm_step]
        probs = sorted({p for lv in LEVELS.values() for p in lv})
        recs = []
        for t in ts:
            q = fn(y, d, t, h, probs)
            if q is not None:
                recs.append((t, y[t + h], q))
        if not recs:
            continue
        half = len(recs) // 2
        for lvl, (pl, ph) in LEVELS.items():
            cov = np.array([q[pl] <= yy <= q[ph] for _, yy, q in recs])
            wid = np.array([q[ph] - q[pl] for _, _, q in recs])
            n_eff = max(1, int(round(len(cov) / h)))  # overlapping h-step windows
            k_eff = int(round(cov.mean() * n_eff))
            wl, wh = wilson(k_eff, n_eff)
            rows.append(dict(
                metric=metric, h=h, method=name, level=lvl, n_origins=len(cov), n_eff=n_eff,
                coverage=float(cov.mean()), wilson_lo=wl, wilson_hi=wh,
                width_ratio=float(np.exp(wid.mean())),
                cov_first_half=float(cov[:half].mean()) if half else np.nan,
                cov_second_half=float(cov[half:].mean()),
                first_origin=idx[recs[0][0]], last_origin=idx[recs[-1][0]]))
    return rows


def backtest(w: pd.DataFrame, horizons=(4, 12), gbm_step=4, metrics=METRICS,
             n_jobs: int = 1) -> pd.DataFrame:
    """Rolling-origin backtest over the last EVAL_WEEKS origins (each uses only past data)."""
    from joblib import Parallel, delayed
    tasks = []
    for metric in metrics:
        ls = log_series(w, metric)
        idx = [t.strftime("%Y-%m-%d") for t in ls.index]
        for h in horizons:
            tasks.append((metric, idx, ls.to_numpy(), h, gbm_step))
    out = Parallel(n_jobs=n_jobs)(delayed(_bt_task)(*t) for t in tasks)
    return pd.DataFrame([r for rows in out for r in rows])


def fan(w: pd.DataFrame, metric: str, H: int = 12) -> pd.DataFrame:
    """Conformal fan at the last observed week: quantiles for h = 1..H (original units)."""
    ls = log_series(w, metric)
    y = ls.to_numpy()
    d = _d(y)
    t = len(y) - 1
    probs = [0.025, 0.10, 0.50, 0.90, 0.975]
    rows = []
    for h in range(1, H + 1):
        q = conformal_q(y, d, t, h, probs)
        if q is None:
            return pd.DataFrame()
        idx = ls.index[-1] + pd.Timedelta(weeks=h)
        rows.append({"week_end": idx, "h": h, **{f"p{int(p*1000):03d}": float(np.exp(v)) for p, v in q.items()}})
    return pd.DataFrame(rows).set_index("week_end")


GRID = [dict(cal=c, dw=dw, phi=p) for c in (52, 104) for dw in (4, 8, 13) for p in (0.0, 0.9)]
GRID_METRICS = ["txns", "active_accounts", "net_fees_usd", "price", "tvl", "stable_usd"]


def grid(w: pd.DataFrame, n_jobs: int = 1) -> pd.DataFrame:
    """Robustness table: conformal coverage/width across 12 hyper-parameter settings."""
    from joblib import Parallel, delayed
    tasks = []
    for cfg in GRID:
        for metric in GRID_METRICS:
            ls = log_series(w, metric)
            idx = [t.strftime("%Y-%m-%d") for t in ls.index]
            for h in (4, 12):
                tasks.append((metric, idx, ls.to_numpy(), h, 4, ("conformal",), cfg))
    out = Parallel(n_jobs=n_jobs)(delayed(_bt_task)(*t) for t in tasks)
    rows = []
    for t, rr in zip(tasks, out):
        for r in rr:
            rows.append({**r, **t[-1]})
    df = pd.DataFrame(rows)
    g = df.groupby(["cal", "dw", "phi", "level"]).agg(
        coverage=("coverage", "mean"),
        width_ratio_gm=("width_ratio", lambda x: float(np.exp(np.log(x).mean())))).reset_index()
    return g


def skill(w: pd.DataFrame, horizons=(4, 12), metrics=METRICS) -> pd.DataFrame:
    """Point-forecast accuracy (MAE in log units) of two 'base' candidates against the no-change
    random walk, on the same origins as the backtest. skill = 1 - MAE_model / MAE_rw.
    `trend` = damped drift (phi 0.9) + median error; `final` = the shipped model (PHI default)."""
    global PHI
    keep = PHI
    rows = []
    try:
        for metric in metrics:
            ls = log_series(w, metric)
            y = ls.to_numpy()
            d = _d(y)
            n = len(y)
            for h in horizons:
                first = max(MIN_T, DRIFT_W + MIN_CAL + h - 1)
                errs = {"rw": [], "trend": [], "final": []}
                for t in range(max(first, n - h - EVAL_WEEKS), n - h):
                    PHI = 0.9
                    qt = conformal_q(y, d, t, h, [0.5])
                    PHI = keep
                    qf = conformal_q(y, d, t, h, [0.5])
                    if qt is None or qf is None:
                        continue
                    errs["trend"].append(abs(y[t + h] - qt[0.5]))
                    errs["final"].append(abs(y[t + h] - qf[0.5]))
                    errs["rw"].append(abs(y[t + h] - y[t]))
                if errs["rw"]:
                    r = {k: float(np.mean(v)) for k, v in errs.items()}
                    rows.append(dict(metric=metric, h=h, n_origins=len(errs["rw"]), mae_rw=r["rw"],
                                     skill_trend=1 - r["trend"] / r["rw"], skill_final=1 - r["final"] / r["rw"]))
    finally:
        PHI = keep
    return pd.DataFrame(rows)
