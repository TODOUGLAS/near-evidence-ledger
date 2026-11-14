"""Public data sources, fetching with snapshot fallback, and the fetch manifest.

Every number shown in the report/dashboard traces back to one of the source ids
defined here (URL + fetch time). `fetch_all()` never raises on network problems:
it falls back to the frozen snapshot in data/snapshots/ and records that fact.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SNAP = ROOT / "data" / "snapshots"
OUT = ROOT / "output"
CST = ZoneInfo("America/Chicago")

_RPC = {"jsonrpc": "2.0", "id": "ledger"}

SOURCES: dict[str, dict] = {
    "nb_charts": dict(
        name="NearBlocks daily charts (price, txns, accounts, fees, supply)",
        url="https://api.nearblocks.io/v1/charts", file="nb_charts.json",
        docs="https://api.nearblocks.io/api-docs/"),
    "nb_stats": dict(
        name="NearBlocks current network stats",
        url="https://api.nearblocks.io/v1/stats", file="nb_stats.json",
        docs="https://api.nearblocks.io/api-docs/"),
    "rpc_status": dict(
        name="NEAR RPC: status (mainnet)", url="https://rpc.mainnet.near.org",
        body={**_RPC, "method": "status", "params": []}, file="rpc_status.json",
        docs="https://docs.near.org/api/rpc/network#node-status"),
    "rpc_validators": dict(
        name="NEAR RPC: current validators and stake (mainnet)",
        url="https://rpc.mainnet.near.org",
        body={**_RPC, "method": "validators", "params": [None]},
        file="rpc_validators.json",
        docs="https://docs.near.org/api/rpc/network#validation-status"),
    "fastnear_rpc": dict(
        name="FastNEAR free RPC: status (cross-check of chain head)",
        url="https://free.rpc.fastnear.com",
        body={**_RPC, "method": "status", "params": []}, file="fastnear_rpc.json",
        docs="https://docs.fastnear.com/"),
    "dl_tvl": dict(
        name="DefiLlama: historical TVL of the NEAR chain",
        url="https://api.llama.fi/v2/historicalChainTvl/Near", file="dl_tvl.json",
        docs="https://defillama.com/chain/Near"),
    "dl_chains": dict(
        name="DefiLlama: chains list (current TVL, market cap context)",
        url="https://api.llama.fi/v2/chains", file="dl_chains.json",
        docs="https://defillama.com/chains"),
    "dl_stable": dict(
        name="DefiLlama: stablecoin supply on NEAR",
        url="https://stablecoins.llama.fi/stablecoincharts/Near", file="dl_stable.json",
        docs="https://defillama.com/stablecoins/Near"),
    "dl_fees": dict(
        name="DefiLlama: fees paid on the NEAR chain (network + protocols)",
        url="https://api.llama.fi/overview/fees/Near?dataType=dailyFees",
        file="dl_fees.json", docs="https://defillama.com/fees/chain/Near"),
    "dl_intents_vol": dict(
        name="DefiLlama: NEAR Intents daily volume",
        url="https://api.llama.fi/summary/dexs/near-intents", file="dl_intents_vol.json",
        docs="https://defillama.com/protocol/near-intents"),
    "dl_intents_fees": dict(
        name="DefiLlama: fees attributed to NEAR Intents",
        url="https://api.llama.fi/summary/fees/near-intents?dataType=dailyFees", file="dl_intents_fees.json",
        docs="https://defillama.com/fees/near-intents"),
    "dl_dex": dict(
        name="DefiLlama: DEX volume on NEAR",
        url="https://api.llama.fi/overview/dexs/Near", file="dl_dex.json",
        docs="https://defillama.com/dexs/chain/Near"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(dt: datetime) -> dict:
    return {"utc": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cst": dt.astimezone(CST).strftime("%Y-%m-%d %H:%M %Z")}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _get(src: dict, timeout: int, retries: int = 2) -> bytes:
    last: Exception | None = None
    for i in range(retries + 1):
        try:
            if "body" in src:
                r = requests.post(src["url"], json=src["body"], timeout=timeout,
                                  headers={"User-Agent": "near-evidence-ledger/0.1"})
            else:
                r = requests.get(src["url"], timeout=timeout,
                                 headers={"User-Agent": "near-evidence-ledger/0.1"})
            r.raise_for_status()
            json.loads(r.content)  # must be valid JSON
            if len(r.content) < 50:
                raise ValueError("response suspiciously small")
            return r.content
        except Exception as e:  # noqa: BLE001 - we fall back, whatever it was
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(str(last))


def fetch_all(force_offline: bool | None = None, timeout: int = 20, write_log: bool = True) -> dict:
    """Fetch every source into data/raw; fall back to data/snapshots on failure.

    Returns the manifest {source_id: {status, url, fetched_at_utc/cst, sha256, bytes,
    path, note}} and writes it to output/FETCH_LOG.json.
    """
    if force_offline is None:
        force_offline = os.environ.get("LEDGER_OFFLINE") == "1"
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    snap_manifest = {}
    if (SNAP / "MANIFEST.json").exists():
        snap_manifest = json.loads((SNAP / "MANIFEST.json").read_text())
    log: dict[str, dict] = {}
    for sid, src in SOURCES.items():
        entry = {"name": src["name"], "url": src["url"], "docs": src.get("docs"),
                 "file": src["file"]}
        if src.get("body"):
            entry["post_body"] = src["body"]["method"]
        content, err = None, None
        if not force_offline:
            try:
                content = _get(src, timeout)
            except Exception as e:  # noqa: BLE001
                err = str(e)[:200]
        if content is not None:
            if write_log:
                (RAW / src["file"]).write_bytes(content)
            t = _stamp(_now())
            entry.update(status="fresh", fetched_at_utc=t["utc"], fetched_at_cst=t["cst"],
                         sha256=_sha(content), bytes=len(content),
                         path=str((RAW / src["file"]).relative_to(ROOT)))
        else:
            sp = SNAP / src["file"]
            if not sp.exists():
                raise SystemExit(f"[{sid}] network failed ({err}) and no snapshot at {sp}")
            m = snap_manifest.get(sid, {})
            entry.update(status="snapshot", fetched_at_utc=m.get("fetched_at_utc", "unknown"),
                         fetched_at_cst=m.get("fetched_at_cst", "unknown"),
                         sha256=_sha(sp.read_bytes()), bytes=sp.stat().st_size,
                         path=str(sp.relative_to(ROOT)),
                         note=("offline mode" if force_offline else f"network error: {err}"))
        log[sid] = entry
        print(f"  [{entry['status']:8}] {sid:15} {entry['fetched_at_utc']}  {entry['bytes']:>8} B")
    if write_log:
        (OUT / "FETCH_LOG.json").write_text(json.dumps(log, indent=2, ensure_ascii=False))
    return log


def update_snapshots(log: dict | None = None, only: list[str] | None = None) -> None:
    """Freeze the fresh raw files as the committed offline snapshots (maintainer step).
    `only` freezes just those source ids and keeps the other snapshots and their manifest entries untouched."""
    log = log or json.loads((OUT / "FETCH_LOG.json").read_text())
    SNAP.mkdir(parents=True, exist_ok=True)
    man = json.loads((SNAP / "MANIFEST.json").read_text()) if only and (SNAP / "MANIFEST.json").exists() else {}
    for sid, e in log.items():
        if only and sid not in only:
            continue
        if e["status"] != "fresh":
            raise SystemExit(f"{sid} is not fresh; refusing to freeze a stale file as new")
        shutil.copyfile(ROOT / e["path"], SNAP / SOURCES[sid]["file"])
        man[sid] = {k: e[k] for k in ("url", "fetched_at_utc", "fetched_at_cst", "sha256", "bytes")}
    (SNAP / "MANIFEST.json").write_text(json.dumps(man, indent=2))
    print(f"snapshots updated: {len(man)} files")


def load_log() -> dict:
    p = OUT / "FETCH_LOG.json"
    if not p.exists():
        raise SystemExit("run `python -m ledger fetch` first (or `python -m ledger all`)")
    return json.loads(p.read_text())


def load_json(sid: str, log: dict | None = None):
    log = log or load_log()
    return json.loads((ROOT / log[sid]["path"]).read_text())
