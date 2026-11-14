"""How fragile is each verdict? Two checks no static dashboard shows.

1. **Flip distance**: how far the pre-declared threshold would have to move (relative, signed) before the verdict
   changes, found by scanning the on-chain integer rule (`verdict_fp`) over +-200% in 0.5% steps.
2. **Variants**: the same claim recomputed with other windows, another statistic, or another data source
   (e.g. C3 with gas-only fees instead of DefiLlama's protocol-inclusive fees). A verdict that flips under a
   reasonable variant is reported as FRAGILE, not hidden.

Variant thresholds are scaled to the window where the claim is a rate (C5, C8). The 'base' variant of each claim is
the shipped definition (its bootstrap seed differs from claims.py, so its interval can differ in the 3rd digit; the
test suite asserts that the base verdict equals the shipped verdict).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import claims as C
from . import sources as S
from .stats import boot_ci, boot_ci_pair


def _fp(value, cmp_, thr, ci):
    return C.verdict_fp(C.micro(value), cmp_, C.micro(thr),
                        (C.micro(ci[0]), C.micro(ci[1])) if ci else None)


def flip_change(rec: dict) -> float | None:
    """Smallest signed relative threshold change (|.|<=200%) that changes the verdict; None if none or thr==0."""
    thr = rec["threshold"]
    if thr == 0:
        return None
    ci = (rec["ci_lo"], rec["ci_hi"]) if rec.get("ci_lo") is not None else None
    base = C.verdict_fp(rec["value"], rec["comparator"], thr, ci)
    best = None
    for k in range(1, 401):
        for sign in (1, -1):
            t = int(round(thr * (1 + sign * k * 0.005)))
            if C.verdict_fp(rec["value"], rec["comparator"], t, ci) != base:
                cand = sign * k * 0.005
                if best is None or abs(cand) < abs(best):
                    best = cand
        if best is not None:
            return best
    return None


def _ratio_yoy(w, n, stat):
    cur = w["txns"].iloc[-n:].to_numpy()
    prev = w["txns"].iloc[-n - 52:-52].to_numpy()
    f = np.median if stat == "median" else np.mean
    val = float(f(cur) / f(prev))
    g = np.random.default_rng(11)
    from .stats import block_bootstrap_idx
    vs = [f(cur[block_bootstrap_idx(n, 3, g)]) / f(prev[block_bootstrap_idx(n, 3, g)]) for _ in range(2000)]
    return val, (float(np.percentile(vs, 5)), float(np.percentile(vs, 95)))


def variants(w: pd.DataFrame, log: dict) -> dict[str, list[dict]]:
    """{claim_id: [{label, value, ci, verdict, thr, note}]}; first item is the shipped definition."""
    out: dict[str, list[dict]] = {}
    spec = {c["id"]: c for c in C.CLAIMS}

    def add(cid, label, val, ci, thr=None, note=""):
        c = spec[cid]
        thr = c["threshold"] if thr is None else thr
        out.setdefault(cid, []).append(dict(label=label, value=float(val), ci=ci, thr=float(thr),
                                            verdict=_fp(val, c["comparator"], thr, ci), note=note))

    for n, st in [(13, "median"), (8, "median"), (26, "median"), (13, "mean")]:
        v, ci = _ratio_yoy(w, n, st)
        add("C1", f"{st} of last {n} weeks vs same weeks a year earlier", v, ci)

    for n, f, nm in [(13, np.median, "median"), (8, np.median, "median"), (26, np.median, "median"), (13, np.mean, "mean")]:
        x = w["active_accounts"].iloc[-n:].to_numpy()
        add("C2", f"{nm} of weekly-median daily active accounts, last {n} weeks", float(f(x)), boot_ci(x, f, block=3, seed=2))

    mcap = float(S.load_json("nb_stats", log)["stats"][0]["market_cap"])
    for n in (13, 8, 26):
        x = w["dl_fees_usd"].dropna().iloc[-n:].to_numpy()
        f = 52 / n
        add("C3", f"DefiLlama fees (network + protocols), last {n} weeks annualised", float(x.sum() * f / mcap),
            boot_ci(x, lambda a, f=f: float(a.sum() * f / mcap), block=3, seed=3))
    x = w["net_fees_usd"].iloc[-13:].to_numpy()
    add("C3", "DATA SOURCE: gas-only fees (NearBlocks), last 13 weeks annualised", float(x.sum() * 4 / mcap),
        boot_ci(x, lambda a: float(a.sum() * 4 / mcap), block=3, seed=3),
        note="drops protocol fees that DefiLlama attributes to NEAR")

    tvl = w["tvl"].dropna()
    for n in (52, 26, 104):
        ref = tvl.iloc[-n - 1:-1].to_numpy()
        g = np.random.default_rng(4)
        from .stats import block_bootstrap_idx
        now = float(tvl.iloc[-1])
        vs = [now / np.median(ref[block_bootstrap_idx(len(ref), 4, g)]) for _ in range(2000)]
        add("C4", f"latest TVL vs trailing {n}-week median", now / float(np.median(ref)),
            (float(np.percentile(vs, 5)), float(np.percentile(vs, 95))))

    st = w["stable_usd"].dropna()
    for n in (13, 8, 26):
        thr = 1.05 ** (n / 13) - 1
        add("C5", f"stablecoin growth over {n} weeks (threshold scaled to {thr:.1%})", float(st.iloc[-1] / st.iloc[-n - 1] - 1),
            None, thr)

    cor = lambda a, b: float(np.corrcoef(a, b)[0, 1])  # noqa: E731
    for n in (52, 26, 104):
        lp = np.log(w["price"]).diff().iloc[-n:].to_numpy()
        la = np.log(w["active_accounts"]).diff().iloc[-n:].to_numpy()
        add("C6", f"price vs active-account log-change correlation, last {n} weeks", cor(lp, la),
            boot_ci_pair(lp, la, cor, block=4, seed=6))

    cv = S.load_json("rpc_validators", log)["result"]["current_validators"]
    stakes = np.array([float(v["stake"]) for v in cv])
    for fr, lab in [(1 / 3, "1/3 of stake (BFT safety)"), (0.30, "30% of stake"), (0.36, "36% of stake")]:
        add("C7", f"validators needed to control {lab}", float(C.nakamoto(stakes, fr)), None)

    iv = w["intents_vol_usd"].dropna()
    from .stats import block_bootstrap_idx
    for n, f, nm in [(13, np.median, "median"), (8, np.median, "median"), (26, np.median, "median"), (13, np.mean, "mean")]:
        cur, prev = iv.iloc[-n:].to_numpy(), iv.iloc[-2 * n:-n].to_numpy()
        g = np.random.default_rng(9)
        vs = [f(cur[block_bootstrap_idx(n, 3, g)]) / f(prev[block_bootstrap_idx(n, 3, g)]) for _ in range(2000)]
        add("C9", f"{nm} weekly Intents volume, last {n} weeks vs the {n} before", float(f(cur) / f(prev)),
            (float(np.percentile(vs, 5)), float(np.percentile(vs, 95))))

    both = w[["intents_vol_usd", "intents_fees_usd"]].dropna()
    rate = lambda a, b: float(np.sum(b) / np.sum(a))  # noqa: E731
    for n in (13, 8, 26):
        vv, ff = both["intents_vol_usd"].iloc[-n:].to_numpy(), both["intents_fees_usd"].iloc[-n:].to_numpy()
        add("C10", f"fees / volume, last {n} weeks", rate(vv, ff), boot_ci_pair(vv, ff, rate, block=3, seed=10))
    vv, ff = both["intents_vol_usd"].iloc[-4:].to_numpy(), both["intents_fees_usd"].iloc[-4:].to_numpy()
    add("C10", "fees / volume, last 4 weeks (the fee switch is recent)", rate(vv, ff), boot_ci_pair(vv, ff, rate, block=2, seed=10))

    ts = w["total_supply"]
    for n in (52, 26, 104):
        thr = 0.05 * n / 52
        add("C8", f"supply growth over {n} weeks (threshold scaled to {thr:.1%})", float(ts.iloc[-1] / ts.iloc[-n - 1] - 1),
            None, thr)
    return out


def analyze(w: pd.DataFrame, log: dict, rows: list[dict]) -> list[dict]:
    """One record per claim: shipped verdict, flip distance, variants, stability label."""
    var = variants(w, log)
    res = []
    for r in rows:
        rec = dict(claim_id=r["id"], comparator=r["comparator"], threshold=C.micro(r["threshold"]),
                   value=C.micro(r["value"]), ci_lo=C.micro(r["ci"][0]) if r["ci"] else None,
                   ci_hi=C.micro(r["ci"][1]) if r["ci"] else None)
        vs = var[r["id"]]
        same = sum(1 for v in vs if v["verdict"] == r["verdict"])
        frac = same / len(vs)
        label = "ROBUST" if frac == 1 else ("MOSTLY STABLE" if frac >= 0.75 else "FRAGILE")
        res.append(dict(id=r["id"], verdict=r["verdict"], flip_change=flip_change(rec), variants=vs,
                        stable_share=frac, label=label, base_same=vs[0]["verdict"] == r["verdict"]))
    return res
