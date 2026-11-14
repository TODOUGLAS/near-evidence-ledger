"""CLI:  python -m ledger <cmd>

Analysis : fetch | analyze | all | freeze | test
On-chain : verify | publish | challenge | predict | resolve | status        (NEAR testnet only)
Your claim: claim <spec.json>   (local, frozen snapshot; see claims/examples/)
"""
from __future__ import annotations

import argparse
import subprocess
import sys

from . import pipeline, sources


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ledger", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["fetch", "analyze", "all", "freeze", "test",
                                    "verify", "publish", "challenge", "predict", "resolve", "status", "claim"])
    ap.add_argument("spec", nargs="?", help="claim: path to a claim spec JSON (see claims/examples/)")
    ap.add_argument("--only", nargs="*", help="freeze: only these source ids")
    ap.add_argument("--offline", action="store_true", help="skip the network, use data/snapshots")
    ap.add_argument("--jobs", type=int, default=-1)
    ap.add_argument("--run", type=int, default=None, help="on-chain run id (default: latest)")
    ap.add_argument("--claim", help="claim id, e.g. C2 (challenge)")
    ap.add_argument("--signer", help="testnet account that signs (key in ~/.near-credentials via near-cli)")
    ap.add_argument("--snapshot-dir", help="challenge: directory holding the alternative raw data (default data/raw)")
    ap.add_argument("--value", type=float, help="challenge: override the alternative value")
    ap.add_argument("--ci", nargs=2, type=float, metavar=("LO", "HI"), help="challenge: override the alternative interval")
    ap.add_argument("--threshold", type=float, help="challenge: alternative threshold")
    ap.add_argument("--evidence", default="", help="challenge: short text (<=280 bytes)")
    ap.add_argument("--write-onchain", action="store_true", help="status: also write docs/onchain.json for the dashboard")
    ap.add_argument("--dry-run", action="store_true", help="publish/challenge/predict/resolve: print the call, send nothing")
    a = ap.parse_args(argv)
    if a.cmd in ("fetch", "all"):
        print("== fetching public data (falls back to data/snapshots on any error) ==")
        sources.fetch_all(force_offline=True if a.offline else None)
    if a.cmd in ("analyze", "all"):
        print("== analysis ==")
        pipeline.run_analysis(n_jobs=a.jobs)
    if a.cmd == "freeze":
        sources.update_snapshots(only=a.only)
    if a.cmd == "test":
        return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    if a.cmd in ("verify", "publish", "challenge", "predict", "resolve", "status", "claim"):
        from . import onchain
        return getattr(onchain, a.cmd)(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
