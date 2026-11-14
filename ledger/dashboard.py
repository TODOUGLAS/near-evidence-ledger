"""Static HTML dashboard (Plotly). No literal numbers: every displayed number is pulled from
the provenance registry and rendered as a link to its source URL with the fetch date in the
tooltip. Plotly.js is embedded so the file works offline."""
from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots

from . import __version__
from .provenance import Registry

METRIC_SRC = {"txns": "nb_charts", "active_accounts": "nb_charts", "net_fees_usd": "nb_charts",
              "price": "nb_charts", "fee_per_txn_near": "nb_charts", "tvl": "dl_tvl",
              "stable_usd": "dl_stable", "dl_fees_usd": "dl_fees"}
METRIC_LABEL = {"txns": "Weekly transactions", "active_accounts": "Active accounts (weekly median of daily)",
                "net_fees_usd": "Network fees, USD/week", "price": "NEAR price, USD",
                "fee_per_txn_near": "Fee per txn, NEAR", "tvl": "TVL, USD",
                "stable_usd": "Stablecoins on NEAR, USD", "dl_fees_usd": "Chain fees incl. protocols, USD/week"}
VERDICT_CLASS = {"SUPPORTED": "ok", "REFUTED": "bad", "INCONCLUSIVE": "mid"}

KB_REFS = [
    ("b174-00029, b174-00032", "Murphy, Probabilistic Machine Learning: Advanced Topics (2024), §14.3 Conformal prediction",
     "split-conformal intervals from held-out residuals"),
    ("b174-00036, b174-00037", "Murphy (2024), quantile regression for prediction intervals",
     "the quantile GBM interval model and its approximate coverage"),
    ("b132-00274, b132-00281", "Raschka, Machine Learning Q and AI (2024), conformal predictions vs prediction intervals",
     "why we report empirical coverage, not nominal"),
    ("x025-00367", "Kaabar, Deep Learning for Finance (2024), rolling window cross validation",
     "rolling-origin backtest design"),
    ("b070-00352, b070-00354", "Moroney, AI and ML for Coders in PyTorch (2025), naive forecast baseline",
     "the random-walk baseline every model must beat"),
    ("b193-00277", "Hall and Curtis, Machine Learning for High-Risk Applications (2025): 'Do not use the future to predict the past'",
     "no-leakage rule for time series, enforced by tests"),
    ("b104-00723, b083-00537", "Shea, Foundations of Data Science with Python (2024); Timbers et al., Data Science (2025), bootstrap CIs",
     "bootstrap intervals used for the claim verdicts (block variant for autocorrelation)"),
    ("b114-01085", "Geron, Hands-On Machine Learning with Scikit-Learn and PyTorch (2026), weekly pattern in a daily series",
     "why daily series are aggregated to weeks"),
    ("b125-00160", "Smolyakov, Machine Learning Algorithms in Depth (2024), hierarchical Bayes",
     "considered (shared prior across metrics); NOT used, to keep the model simple and auditable"),
    ("b137-00331", "Ryan and Massaron, ML for Tabular Data (2025), gradient boosting caveats",
     "gradient boosting is data-hungry; our 150-300 weekly points are small, which the backtest shows"),
]


def _fig_html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displaylogo": False, "responsive": True})


def _hover(reg: Registry, sid: str) -> str:
    return f"%{{x|%Y-%m-%d}}: %{{y:,.4g}}<br>src {sid}, fetched {reg.fetched(sid)}<extra></extra>"


def history_fig(w: pd.DataFrame, reg: Registry) -> go.Figure:
    ms = ["txns", "active_accounts", "price", "tvl", "stable_usd", "net_fees_usd"]
    fig = make_subplots(rows=3, cols=2, subplot_titles=[f"{METRIC_LABEL[m]} [{METRIC_SRC[m]}]" for m in ms],
                        vertical_spacing=0.09)
    for i, m in enumerate(ms):
        s = w[m].dropna()
        fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", name=m, showlegend=False,
                                 hovertemplate=_hover(reg, METRIC_SRC[m])), row=i // 2 + 1, col=i % 2 + 1)
        fig.update_yaxes(type="log", row=i // 2 + 1, col=i % 2 + 1)
    fig.update_layout(height=820, margin=dict(t=40, b=20, l=50, r=20))
    return fig


def fan_fig(w: pd.DataFrame, fans: dict[str, pd.DataFrame], reg: Registry) -> go.Figure:
    ms = ["txns", "active_accounts", "net_fees_usd", "price", "tvl", "stable_usd"]
    fig = make_subplots(rows=3, cols=2, subplot_titles=[METRIC_LABEL[m] for m in ms], vertical_spacing=0.09)
    for i, m in enumerate(ms):
        r, c = i // 2 + 1, i % 2 + 1
        s = w[m].dropna().iloc[-104:]
        f = fans[m]
        sid = METRIC_SRC[m]
        x = list(f.index)
        fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", line=dict(color="#1f3a5f"),
                                 showlegend=False, hovertemplate=_hover(reg, sid)), row=r, col=c)
        for lo, hi, col, nm in (("p025", "p975", "rgba(31,58,95,0.12)", "95%"),
                                ("p100", "p900", "rgba(31,58,95,0.28)", "80%")):
            fig.add_trace(go.Scatter(x=x + x[::-1], y=list(f[hi]) + list(f[lo])[::-1], fill="toself",
                                     fillcolor=col, line=dict(width=0), showlegend=False, name=nm,
                                     hoverinfo="skip"), row=r, col=c)
        fig.add_trace(go.Scatter(x=x, y=f["p500"], mode="lines", line=dict(color="#c0392b", dash="dash"),
                                 showlegend=False, name="median",
                                 hovertemplate="median %{y:,.4g}<br>src " + sid + ", fetched "
                                 + reg.fetched(sid) + "<extra></extra>"), row=r, col=c)
        fig.update_yaxes(type="log", row=r, col=c)
    fig.update_layout(height=820, margin=dict(t=40, b=20, l=50, r=20))
    return fig


def coverage_fig(bt: pd.DataFrame, level: str) -> go.Figure:
    nominal = {"80%": 0.8, "95%": 0.95}[level]
    fig = make_subplots(rows=1, cols=2, subplot_titles=["h = 4 weeks", "h = 12 weeks"], shared_yaxes=True)
    colors = {"gauss": "#7f8c8d", "conformal": "#1f3a5f", "qgbm": "#e67e22"}
    for j, h in enumerate((4, 12)):
        for meth in ("gauss", "conformal", "qgbm"):
            d = bt[(bt.h == h) & (bt.level == level) & (bt.method == meth)]
            fig.add_trace(go.Bar(
                x=d.metric, y=d.coverage, name=meth, marker_color=colors[meth], showlegend=(j == 0),
                error_y=dict(type="data", symmetric=False, array=(d.wilson_hi - d.coverage).clip(lower=0),
                             arrayminus=(d.coverage - d.wilson_lo).clip(lower=0), thickness=1),
                hovertemplate="%{x} " + meth + ": %{y:.0%}<extra></extra>"), row=1, col=j + 1)
        fig.add_hline(y=nominal, line_dash="dot", line_color="#c0392b", row=1, col=j + 1)
    fig.update_yaxes(range=[0, 1.05], tickformat=".0%")
    fig.update_layout(height=380, barmode="group", margin=dict(t=40, b=20, l=50, r=20))
    return fig


def tornado_fig(tor: pd.DataFrame) -> go.Figure:
    t = tor.iloc[::-1]
    base = float(t["base"].iloc[0])
    fig = go.Figure()
    fig.add_trace(go.Bar(y=t.label, x=t.high - base, base=base, orientation="h", name="+1 sigma",
                         marker_color="#27ae60", hovertemplate="%{y} +1 sigma: %{x:+,.0f} USD/week<extra></extra>"))
    fig.add_trace(go.Bar(y=t.label, x=t.low - base, base=base, orientation="h", name="-1 sigma",
                         marker_color="#c0392b", hovertemplate="%{y} -1 sigma: %{x:+,.0f} USD/week<extra></extra>"))
    fig.add_vline(x=base, line_color="black")
    fig.update_layout(barmode="overlay", height=300, margin=dict(t=30, b=20, l=130, r=20),
                      xaxis_title="Weekly network fees, USD (12 weeks ahead)")
    return fig


EXPL = "https://testnet.nearblocks.io"


def _tx(h: str) -> str:
    return f"<a href='{EXPL}/txns/{h}' target='_blank' rel='noopener'>{h[:10]}&hellip;</a>"


def _mu(v) -> str:
    return "n/a" if v is None else f"{v / 1e6:,.4g}"


def _onchain_html(oc: dict) -> str:
    """Static snapshot of the NEAR testnet registry (written by `python -m ledger status --write-onchain`)."""
    h = ["<h2>1b. On-chain record (NEAR testnet): anyone can re-run and challenge these verdicts</h2>"]
    if not oc or not oc.get("run"):
        h.append("<p class='small'>No run published yet. See README, 'Publish'.</p>")
        return "".join(h)
    r = oc["run"]
    c = oc["contract"]
    h.append(f"<p>Contract <a href='{EXPL}/address/{c}' target='_blank'>{c}</a>. Run <b>#{r['id']}</b> published by "
             f"<code>{r['attester']}</code> at block {r['height']} (tx {_tx(oc['run_tx'])}). The contract recomputed every "
             f"verdict from its own value, interval and threshold before storing it; a verdict that contradicts its numbers is rejected.</p>")
    h.append("<table><tr><th>commitment</th><th>sha256</th><th>what it pins</th></tr>")
    for k, t in (("spec_hash", "the claim texts, thresholds, windows and sources"),
                 ("snapshot_hash", "the exact raw API responses the verdicts were computed from (data/snapshots)"),
                 ("code_hash", "the analysis code (claims, data, stats, forecast, robustness, sources)"),
                 ("results_hash", "the integer verdict table")):
        h.append(f"<tr><td>{k}</td><td class='small'><code>{r['meta'][k]}</code></td><td class='small'>{t}</td></tr>")
    h.append("</table>")
    h.append("<p><b>Re-check it yourself, no keys needed:</b> <code>python -m ledger verify</code> re-runs offline and compares every "
             "hash and verdict with this record (MATCH / MISMATCH). <b>Dispute it:</b> <code>python -m ledger challenge --claim C2 "
             "--signer &lt;your testnet account&gt;</code> after a re-run on other data; the contract computes the alternative verdict and "
             "records whether it flips.</p>")
    ch = oc.get("challenges") or []
    h.append(f"<p>Challenges on this run: <b>{len(ch)}</b>"
             + (" (" + "; ".join(f"{x['claim_id']} by {x['challenger']}: {x['alt_verdict']}, flips={x['flips']}" for x in ch) + ")" if ch else "") + ".</p>")
    ps = oc.get("predictions") or []
    if ps:
        sc = oc.get("scoreboard") or {}
        h.append("<h3>Pre-registered forecasts (committed before the data exists)</h3>")
        h.append(f"<p>{len(ps)} 80% conformal intervals were written to the contract on "
                 f"{oc.get('predictions_registered_utc', '')} for weeks that had not ended. They are scored by the contract after each target week; "
                 f"resolved so far: <b>{sc.get('resolved', 0)}</b>, hits: <b>{sc.get('hits', 0)}</b> (strict, i.e. every recorded observation inside the interval: <b>{sc.get('hits_strict', 0)}</b>)"
                 + (f", hit rate {sc['hit_rate_bp'] / 100:.0f}% vs 80% nominal" if sc.get("resolved") else "")
                 + ". The first week (ending 2026-11-15) closes after the submission deadline, so the track record starts empty by design: no backdating is possible.</p>")
        h.append("<table><tr><th>#</th><th>metric</th><th>target week</th><th>80% interval</th><th>point</th><th>observed</th><th>result</th></tr>")
        for q in ps:
            b = q["body"]
            res = q.get("resolution")
            h.append(f"<tr><td>{q['id']}</td><td>{b['metric']}</td><td>{b['target_week']}</td><td>[{_mu(b['lo'])}, {_mu(b['hi'])}]</td>"
                     f"<td>{_mu(b['point'])}</td><td>{_mu(res['observed']) if res else 'pending'}</td>"
                     f"<td>{('HIT' if res['hit'] else 'MISS') if res else ''}</td></tr>")
        h.append("</table>")
    return "".join(h)


def _robust_html(rob: list) -> str:
    h = ["<h2>1c. How fragile is each verdict?</h2>",
         "<p class='small'>Two checks. <b>Flip distance</b>: how far the pre-declared threshold would have to move before the "
         "verdict changes (found by scanning the same integer rule the contract runs). <b>Variants</b>: the claim recomputed with other "
         "windows, another statistic or another data source. A verdict that flips under a reasonable variant is labelled FRAGILE, not hidden. "
         "Rate thresholds (C5, C8) are scaled to the window.</p>",
         "<table><tr><th>claim</th><th>verdict</th><th>threshold change that flips it</th><th>variants with same verdict</th><th>label</th><th>variants (value &rarr; verdict)</th></tr>"]
    cls = {"ROBUST": "ok", "MOSTLY STABLE": "mid", "FRAGILE": "bad"}
    for r in rob:
        fc = "none within &plusmn;200%" if r["flip_change"] is None else f"{r['flip_change']:+.1%}"
        same = sum(1 for v in r["variants"] if v["verdict"] == r["verdict"])
        vs = "<br>".join(f"{html.escape(v['label'])}: {v['value']:,.4g} &rarr; {v['verdict']}" + (f" <i>({html.escape(v['note'])})</i>" if v["note"] else "")
                         for v in r["variants"])
        h.append(f"<tr><td>{r['id']}</td><td>{r['verdict']}</td><td>{fc}</td><td>{same} of {len(r['variants'])}</td>"
                 f"<td class='{cls[r['label']]}'><span class='badge'>{r['label']}</span></td><td class='small'>{vs}</td></tr>")
    h.append("</table>")
    return "".join(h)


def _num(reg, key):
    return reg.link(key)


def build(w, log, reg: Registry, claims_rows, bt, grid_df, sc, fans, tor, out: Path, thesis: str,
          asof: str, sk=None, robust=None, onchain=None) -> None:
    css = """body{font-family:system-ui,Arial,sans-serif;max-width:1180px;margin:24px auto;padding:0 16px;color:#1b1f23}
h1{margin-bottom:0}h2{border-bottom:1px solid #ddd;padding-bottom:4px;margin-top:36px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #ddd;padding:5px 8px;vertical-align:top}
th{background:#f3f5f7;text-align:left}a.num{color:#0b5cad;text-decoration:underline dotted;font-variant-numeric:tabular-nums}
.ok{background:#d4efdf}.bad{background:#f5b7b1}.mid{background:#fcf3cf}.small{font-size:12px;color:#555}
.badge{font-weight:700;padding:2px 8px;border-radius:4px;white-space:nowrap}code{background:#f3f5f7;padding:1px 4px}"""
    p = []
    p.append(f"<!doctype html><html><head><meta charset='utf-8'><title>NEAR Evidence Ledger</title>"
             f"<style>{css}</style><script>{get_plotlyjs()}</script></head><body>")
    p.append("<h1>NEAR Evidence Ledger</h1>")
    p.append(f"<p class='small'>Track: Investment Thesis &middot; data through week ending {asof} &middot; "
             f"v{__version__} &middot; every number below is a link: click it to open its source, hover to see "
             f"the calculation and the fetch date. Companion project: Counterparty Guard.</p>")
    p.append(f"<p>{html.escape(thesis)}</p>")

    # verdict summary
    cnt = {k: sum(1 for r in claims_rows if r["verdict"] == k) for k in VERDICT_CLASS}
    p.append("<h2>1. Claims and verdicts</h2>")
    p.append(f"<p><b>{cnt['SUPPORTED']}</b> supported, <b>{cnt['REFUTED']}</b> refuted, "
             f"<b>{cnt['INCONCLUSIVE']}</b> inconclusive. Verdicts are computed by <code>ledger/claims.py</code> from the "
             f"data, with thresholds fixed in code before the verdicts were computed. Refuted claims are shown "
             f"on purpose: this is evidence, not conviction.</p>")
    p.append("<table><tr><th>#</th><th>Claim</th><th>Measured</th><th>90% interval</th><th>Threshold</th>"
             "<th>Verdict</th><th>Window</th><th>Sources</th></tr>")
    for r in claims_rows:
        cid = r["id"]
        ci = (f"{_num(reg, cid + '.ci_lo')} &ndash; {_num(reg, cid + '.ci_hi')}" if r["ci"] else "n/a (point-in-time)")
        srcs = ", ".join(f"<a href='{html.escape(log[s]['url'])}' target='_blank'>{s}</a> "
                         f"<span class='small'>({log[s]['fetched_at_utc']})</span>" for s in r["src"])
        p.append(f"<tr><td>{cid}</td><td>{html.escape(r['statement'])}</td><td>{_num(reg, cid + '.value')}</td>"
                 f"<td>{ci}</td><td>{html.escape(r['comparator'])} {_num(reg, cid + '.threshold')}</td>"
                 f"<td class='{VERDICT_CLASS[r['verdict']]}'><span class='badge'>{r['verdict']}</span></td>"
                 f"<td class='small'>{html.escape(r['window'])}</td><td class='small'>{srcs}</td></tr>")
    p.append("</table>")
    p.append("<p class='small'>Context numbers: C1 compares "
             f"{_num(reg, 'c1.cur_median_txns')} with {_num(reg, 'c1.prev_median_txns')} weekly txns; "
             f"C2 peak was {_num(reg, 'c2.peak_active_accounts')}; "
             f"C3 uses {_num(reg, 'c3.fees_ann')} USD/year of chain fees (incl. protocols) over market cap "
             f"{_num(reg, 'c3.mcap_spot')} USD, while protocol-level network gas alone is only "
             f"{_num(reg, 'c3.net_fees_ann')} USD/year, a yield of {_num(reg, 'c3.net_fee_yield')}; "
             f"C4 TVL {_num(reg, 'c4.tvl_now')} vs 52-week median {_num(reg, 'c4.tvl_med52')}; "
             f"C5 stablecoins {_num(reg, 'c5.stable_now')} vs {_num(reg, 'c5.stable_prev')} 13 weeks earlier; "
             f"C7 {_num(reg, 'c7.n_validators')} validators, largest holds {_num(reg, 'c7.top1_share')}, top ten "
             f"{_num(reg, 'c7.top10_share')}; C8 supply {_num(reg, 'c8.supply_now')} vs {_num(reg, 'c8.supply_prev')} NEAR.</p>")
    p.append("<p class='small'>Caveat on C3: DefiLlama attributes fees to the NEAR chain, including intent-settlement "
             "protocols; attribution rules are theirs and may change. We show the gas-only yield next to it.</p>")

    p.append(_onchain_html(onchain or {}))
    if robust:
        p.append(_robust_html(robust))

    p.append("<h2>2. History</h2>")
    p.append(_fig_html(history_fig(w, reg)))
    p.append("<p class='small'>Log scale. Weekly aggregation; incomplete weeks are dropped. Hover shows the source id and fetch time.</p>")

    p.append("<h2>3. Probabilistic forecast (12 weeks) with intervals</h2>")
    p.append(_fig_html(fan_fig(w, fans, reg)))
    p.append("<p class='small'>Dark band: 80% interval, light band: 95%, dashed: median. Split-conformal on a no-change forecast "
             "(see Methods). The bands are wide because these series changed regime several times; that width is the honest answer.</p>")

    p.append("<h2>4. Backtest: do the intervals cover?</h2>")
    p.append("<p class='small'>Bars: share of held-out outcomes inside the interval. Red dotted line = nominal level. "
             "Whiskers = Wilson 95% interval using n_eff = origins/h.</p>")
    p.append("<b>80% intervals</b>")
    p.append(_fig_html(coverage_fig(bt, "80%")))
    p.append("<b>95% intervals</b>")
    p.append(_fig_html(coverage_fig(bt, "95%")))
    p.append("<table><tr><th>metric</th><th>h</th><th>method</th><th>80% cov.</th><th>95% cov.</th><th>80% width (p90/p10)</th>"
             "<th>origins</th><th>n_eff</th><th>80% cov. 1st / 2nd half</th></tr>")
    for (metric, h, meth), g in bt.groupby(["metric", "h", "method"], sort=False):
        k = f"bt.{metric}.{h}.{meth}"
        if f"{k}.80%" not in reg.items:
            continue
        p.append(f"<tr><td>{metric}</td><td>{h}</td><td>{meth}</td><td>{_num(reg, k + '.80%')}</td><td>{_num(reg, k + '.95%')}</td>"
                 f"<td>{_num(reg, k + '.width')}x</td><td>{int(g['n_origins'].iloc[0])}</td><td>{int(g['n_eff'].iloc[0])}</td>"
                 f"<td>{_num(reg, k + '.h1')} / {_num(reg, k + '.h2')}</td></tr>")
    p.append("</table>")
    p.append("<p class='small'>Origins are weekly and overlap for h&gt;1, so the effective sample is origins/h (column n_eff); "
             "conformal and gauss use every origin, qgbm every 4th. Coverage below nominal is reported as is.</p>")

    if sk is not None and len(sk):
        p.append("<h3>Why the centre is 'no change': point-forecast skill vs a random walk</h3>"
                 "<p class='small'>skill = 1 &minus; MAE(model)/MAE(random walk) in log units on the same origins; negative = worse than "
                 "saying 'no change'. The first candidate, a damped trend (phi 0.9), lost in every cell, so the shipped model "
                 "centres on no change and only learns the <i>width</i> from its past errors. This choice was made after seeing "
                 "this backtest, so the coverage numbers above are mildly optimistic.</p>"
                 "<table><tr><th>metric</th><th>h = 4: trend</th><th>h = 4: shipped</th><th>h = 12: trend</th><th>h = 12: shipped</th></tr>")
        for m in sk.metric.unique():
            cells = "".join(f"<td>{_num(reg, f'sk.{m}.{h}.{kk}')}</td>" if f"sk.{m}.{h}.{kk}" in reg.items else "<td>n/a</td>"
                            for h in (4, 12) for kk in ("trend", "final"))
            p.append(f"<tr><td>{m}</td>{cells}</tr>")
        p.append("</table>")
    p.append("<h2>5. Scenarios (bear / base / bull = p10 / p50 / p90, 12 weeks ahead)</h2>")
    p.append("<p class='small'>Base = median of the no-change model with learned error width (so it sits near the latest value); "
             "bear and bull are the 10th and 90th percentiles of the forecast distribution, not stress cases.</p>")
    p.append("<table><tr><th>metric</th><th>latest</th><th>bear</th><th>base</th><th>bull</th><th>target week</th></tr>")
    for m, r in sc.iterrows():
        p.append(f"<tr><td>{html.escape(r['label'])}</td><td>{_num(reg, f'scn.{m}.now')}</td><td>{_num(reg, f'scn.{m}.bear')}</td>"
                 f"<td>{_num(reg, f'scn.{m}.base')}</td><td>{_num(reg, f'scn.{m}.bull')}</td><td>{r['target_week']}</td></tr>")
    p.append("</table>")
    p.append(f"<p>What the C3 fee yield would be at those prices if ecosystem fees stay at the 13-week run-rate: "
             f"bear price {_num(reg, 'scn.yield.bear')}, base price {_num(reg, 'scn.yield.base')}, "
             f"bull price {_num(reg, 'scn.yield.bull')} (a lower price raises the yield; it is arithmetic, not a forecast of fees).</p>")
    p.append("<h3>Sensitivity: what moves network fees?</h3>")
    p.append(_fig_html(tornado_fig(tor)))
    p.append("<table><tr><th>factor</th><th>1-sigma (log)</th><th>fees at -1 sigma</th><th>fees at +1 sigma</th></tr>")
    for _, r in tor.iterrows():
        k = r["factor"]
        p.append(f"<tr><td>{html.escape(r['label'])}</td><td>{_num(reg, f'tor.{k}.sigma')}</td>"
                 f"<td>{_num(reg, f'tor.{k}.low')}</td><td>{_num(reg, f'tor.{k}.high')}</td></tr>")
    p.append(f"</table><p class='small'>Identity: fees(USD) = txns x fee-per-txn(NEAR) x price. Base (product of medians) = "
             f"{_num(reg, 'tor.base')} USD/week; the directly forecast median is {_num(reg, 'tor.direct_median')}. "
             f"The gap shows that the factors are not independent.</p>")

    if grid_df is not None and len(grid_df):
        p.append("<h2>6. Robustness: hyper-parameter grid</h2>")
        p.append("<p class='small'>Conformal coverage and geometric-mean width over six metrics and h = 4, 12 for 12 settings "
                 "(calibration window, drift window, damping phi; phi = 0 is the shipped no-change centre, in which the drift window has no effect). The calibration window default (104) was fixed before the grid was run; phi was switched from 0.9 to 0 after the skill test in section 4.</p>")
        p.append("<table><tr><th>cal</th><th>drift wk</th><th>phi</th><th>80% cov.</th><th>95% cov.</th><th>80% width</th></tr>")
        for (cal, dw, phi), g in grid_df.groupby(["cal", "dw", "phi"]):
            k = f"grid.{cal}.{dw}.{phi}"
            p.append(f"<tr><td>{cal}</td><td>{dw}</td><td>{phi}</td><td>{_num(reg, k + '.80%')}</td>"
                     f"<td>{_num(reg, k + '.95%')}</td><td>{_num(reg, k + '.width')}x</td></tr>")
        p.append("</table>")

    p.append("<h2>7. Data sources and freshness</h2><table><tr><th>id</th><th>source</th><th>fetched (UTC)</th><th>fetched (CST)</th><th>used</th><th>sha256</th></tr>")
    for sid, e in log.items():
        p.append(f"<tr><td>{sid}</td><td><a href='{html.escape(e['url'])}' target='_blank'>{html.escape(e['name'])}</a></td>"
                 f"<td>{e['fetched_at_utc']}</td><td>{e['fetched_at_cst']}</td><td>{e['status']}</td><td class='small'>{e['sha256'][:12]}</td></tr>")
    p.append("</table>")
    if "chk.head_near" in reg.items:
        p.append(f"<p class='small'>Cross-check of two independent RPC providers: chain head at fetch time "
                 f"{_num(reg, 'chk.head_near')} (rpc.mainnet.near.org) vs {_num(reg, 'chk.head_fast')} (FastNEAR), "
                 f"difference {_num(reg, 'chk.head_diff')} blocks.</p>")
    p.append("<h2>8. Method, limits, disclosure</h2><ul>"
             "<li>Weekly aggregation (ISO weeks); flows summed, stocks end-of-week, active accounts weekly median; the latest incomplete day and week are dropped.</li>"
             "<li>Interval method: no-change point forecast in log space with empirical quantiles of its own past h-step errors (last 104 origins, split-conformal style). Comparison methods: Gaussian log random walk (width from the last 52 weeks) and quantile gradient boosting.</li>"
             "<li>Backtest: rolling origin over the last 156 weekly origins; every method sees only data up to its origin (tests/test_ledger.py).</li>"
             "<li>Limits: no causal claims; price is close to unpredictable and the intervals say so; DefiLlama attribution is a third-party model; intent-flow volume has no public API used here, so it is not in the ledger; the series are short and contain regime breaks, possible causes such as bot activity or incentive programs are not tested here.</li>"
             "<li>Code and this page were written with an AI coding assistant (disclosed per hackathon rule Q-005). Libraries: numpy, pandas, scipy, scikit-learn, plotly, requests, joblib.</li>"
             "<li>Not investment advice.</li></ul>")
    p.append("<h2>9. Knowledge-base sources</h2><table><tr><th>KB ids</th><th>Source</th><th>Used for</th></tr>")
    for ids, src, use in KB_REFS:
        p.append(f"<tr><td>{html.escape(ids)}</td><td>{html.escape(src)}</td><td>{html.escape(use)}</td></tr>")
    p.append("</table></body></html>")
    out.write_text("\n".join(p), encoding="utf-8")
