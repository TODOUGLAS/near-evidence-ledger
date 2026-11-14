"""On-chain side of the Evidence Ledger (NEAR testnet only).

Hashes, the canonical payloads, RPC view calls, and near-cli wrappers for publish / challenge / predict / resolve.
The contract (contract/src/lib.rs) stores the hashes and verdicts; this module builds them from the local run so that
anyone can recompute the same bytes and compare (`python -m ledger verify`).

Keys never live in this repository: signing is delegated to near-cli-rs (`sign-with-keychain`, ~/.near-credentials).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import requests

from . import claims as C
from . import sources as S

ROOT = S.ROOT
DEPLOY = ROOT / "docs" / "deployment.json"
RPCS = ["https://rpc.testnet.near.org", "https://test.rpc.fastnear.com"]
EXPLORER = "https://testnet.nearblocks.io"
MICRO = C.MICRO
# the files whose content decides verdicts and forecasts (not the CLI, dashboard or chain glue)
CODE_FILES = ["claims.py", "data.py", "forecast.py", "robustness.py", "sources.py", "stats.py"]
VALUE_TOLERANCE_MICRO = 5  # cross-platform float noise allowed when comparing re-computed values


# --------------------------------------------------------------------------- hashes
def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# the ten sources of the first frozen snapshot (13.11 23:53 UTC). The 21 forecasts registered on 14.11 ~02:00 CST pin
# THIS subset (all they use); the two NEAR Intents sources were frozen later (14.11 08:05 UTC) for claims C9/C10.
CORE_IDS = ["nb_charts", "nb_stats", "rpc_status", "rpc_validators", "fastnear_rpc", "dl_tvl", "dl_chains",
            "dl_stable", "dl_fees", "dl_dex"]


def snapshot_hash(snap_dir: Path | None = None, ids: list[str] | None = None) -> str:
    """sha256 over sorted 'file sha256(content)' lines of the frozen raw responses (MANIFEST.json excluded).
    Default: all sources; `ids=CORE_IDS` gives the commitment used by the pre-registered forecasts."""
    d = Path(snap_dir) if snap_dir else S.SNAP
    srcs = [S.SOURCES[i] for i in (ids or S.SOURCES)]
    lines = sorted(f"{src['file']} {sha((d / src['file']).read_bytes())}" for src in srcs)
    return sha("\n".join(lines).encode())


def code_hash() -> str:
    h = hashlib.sha256()
    for name in sorted(CODE_FILES):
        h.update(name.encode() + b"\0" + (ROOT / "ledger" / name).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def spec_of(claims=None) -> list[dict]:
    out = []
    for c in claims or C.CLAIMS:
        out.append(dict(id=c["id"], statement=c["statement"], metric=c["metric"], comparator=c["comparator"],
                        threshold_micro=C.micro(c["threshold"]), window=c["window"], sources=sorted(c["src"])))
    return out


def spec_hash(claims=None) -> str:
    return sha(canon(spec_of(claims)))


def verdict_records(results: dict) -> list[dict]:
    """Contract-ready verdict entries from output/results.json (integers, 6 decimals)."""
    out = []
    for r in results["claims"]:
        ci = r.get("ci90")
        rec = dict(claim_id=r["id"], comparator=r["comparator"], threshold=C.micro(r["threshold"]),
                   value=C.micro(r["value"]),
                   ci_lo=C.micro(ci[0]) if ci else None, ci_hi=C.micro(ci[1]) if ci else None)
        want = C.verdict_fp(rec["value"], rec["comparator"], rec["threshold"],
                            (rec["ci_lo"], rec["ci_hi"]) if ci else None)
        rec["verdict"] = want
        out.append(rec)
    return out


def results_hash(results: dict, snap: str) -> str:
    core = dict(as_of_week=results["as_of_week"], snapshot_hash=snap, verdicts=verdict_records(results))
    return sha(canon(core))


def backtest_coverage(bt) -> tuple[int, int]:
    c = bt[bt.method == "conformal"]
    a = c[c.level == "80%"].coverage.mean()
    b = c[c.level == "95%"].coverage.mean()
    return int(round(a * 10_000)), int(round(b * 10_000))


def build_run(results: dict, cov80_bp: int, cov95_bp: int, note: str, snap_dir: Path | None = None) -> tuple[dict, list]:
    snap = snapshot_hash(snap_dir)
    meta = dict(spec_hash=spec_hash(), snapshot_hash=snap, code_hash=code_hash(),
                results_hash=results_hash(results, snap), data_through=results["as_of_week"],
                backtest_cov80_bp=cov80_bp, backtest_cov95_bp=cov95_bp, note=note[:280])
    return meta, verdict_records(results)


# --------------------------------------------------------------------------- deployment info
def deployment() -> dict:
    if DEPLOY.exists():
        return json.loads(DEPLOY.read_text())
    return {}


def contract_id() -> str:
    c = os.environ.get("LEDGER_CONTRACT") or deployment().get("contract")
    if not c:
        raise SystemExit("no contract: set LEDGER_CONTRACT or create docs/deployment.json (see README, 'Deploy')")
    if not c.endswith(".testnet"):
        raise SystemExit(f"refusing to use {c!r}: this project is testnet-only")
    return c


# --------------------------------------------------------------------------- RPC views
def view(method: str, args: dict | None = None, contract: str | None = None):
    contract = contract or contract_id()
    payload = {"jsonrpc": "2.0", "id": "ledger", "method": "query", "params": {
        "request_type": "call_function", "finality": "final", "account_id": contract, "method_name": method,
        "args_base64": base64.b64encode(json.dumps(args or {}).encode()).decode()}}
    last = None
    for url in RPCS:
        try:
            r = requests.post(url, json=payload, timeout=25).json()
            if "error" in r:
                raise RuntimeError(json.dumps(r["error"])[:300])
            res = r["result"]
            if "error" in res:
                raise RuntimeError(res["error"])
            return json.loads(bytes(res["result"]).decode())
        except Exception as e:  # noqa: BLE001
            last = e
    raise SystemExit(f"RPC view {method} failed on all providers: {last}")


# --------------------------------------------------------------------------- near-cli transactions
def _near() -> str:
    exe = shutil.which("near") or str(Path.home() / ".cargo/bin/near")
    if not Path(exe).exists():
        raise SystemExit("near-cli-rs not found: https://github.com/near/near-cli-rs (cargo install near-cli-rs)")
    return exe


def call(method: str, args: dict, signer: str, deposit: str = "0.05 NEAR", gas: str = "100 Tgas") -> dict:
    """Signed testnet transaction through near-cli-rs. Returns {tx, url, output}."""
    cid = contract_id()
    cmd = [_near(), "contract", "call-function", "as-transaction", cid, method, "json-args", json.dumps(args),
           "prepaid-gas", gas, "attached-deposit", deposit, "sign-as", signer,
           "network-config", "testnet", "sign-with-keychain", "send"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    out = re.sub(r"\x1b\[[0-9;]*m", "", p.stdout + p.stderr)
    m = re.search(r"Transaction ID:\s*([A-Za-z0-9]{40,50})", out)
    if p.returncode != 0 or not m:
        raise SystemExit(f"transaction failed ({method}):\n{out[-1500:]}")
    return {"tx": m.group(1), "url": f"{EXPLORER}/txns/{m.group(1)}", "output": out}


# --------------------------------------------------------------------------- predictions
WEEK_MS = 7 * 24 * 3600 * 1000


def week_end_ms(week_end_label: str) -> int:
    """Unix ms of the END of the UTC day that closes an ISO week (the Sunday label) = next Monday 00:00 UTC."""
    import pandas as pd
    return int((pd.Timestamp(week_end_label, tz="UTC") + pd.Timedelta(days=1)).timestamp() * 1000)


def build_predictions(w, horizons=(1, 2, 4), metrics=None, snap: str | None = None) -> list[dict]:
    """80% conformal intervals (p10..p90) from the frozen data for the next weeks, in natural units * 1e6."""
    from . import forecast as F
    snap = snap or snapshot_hash(ids=CORE_IDS)
    out = []
    last = w.index[-1].strftime("%Y-%m-%d")
    for metric in metrics or [m for m in F.METRICS if m != "fee_per_txn_near"]:  # 6-decimal fixed point is too coarse for NEAR/txn
        fan = F.fan(w, metric, H=max(horizons))
        if fan.empty:
            continue
        for h in horizons:
            r = fan[fan.h == h].iloc[0]
            target = fan[fan.h == h].index[0].strftime("%Y-%m-%d")
            out.append(dict(metric=metric, origin_week=last, target_week=target,
                            target_end_ms=str(week_end_ms(target)), level_bp=8000,
                            point=C.micro(r["p500"]), lo=C.micro(r["p100"]), hi=C.micro(r["p900"]),
                            snapshot_hash=snap, method=f"conformal-h{h}"))
    return out


def observed_value(w, metric: str, target_week: str):
    import pandas as pd
    ts = pd.Timestamp(target_week)
    if ts not in w.index or metric not in w.columns:
        return None
    v = w.loc[ts, metric]
    return None if v != v else float(v)
