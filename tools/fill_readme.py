"""Run the offline pipeline and paste (1) its console output into README.md between the EXAMPLE markers and
(2) the on-chain facts (docs/onchain.json, docs/deployment.json) between the ONCHAIN markers.
Run from the repo root:  python tools/fill_readme.py"""
import json
import re
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
out = subprocess.run([sys.executable, "-m", "ledger", "all", "--offline"], cwd=root,
                     capture_output=True, text=True, check=True).stdout
lines = [l for l in out.splitlines() if "cache hit" not in l and "computed and cached" not in l]
res = json.loads((root / "output" / "results.json").read_text())
txt = "\n".join(lines)
block = ("### Example output (frozen snapshot, `python -m ledger all --offline`)\n\n"
         f"Data through the week ending {res['as_of_week']}; the first ten snapshots were fetched "
         f"{res['sources']['nb_charts']['fetched_at_utc']} (UTC), the two NEAR Intents ones "
         f"{res['sources']['dl_intents_vol']['fetched_at_utc']}. A fresh `python -m ledger all` uses newer data, so its numbers differ.\n\n"
         "```text\n" + txt + "\n```\n")
p = root / "README.md"
s = p.read_text(encoding="utf-8")
s = re.sub(r"<!-- EXAMPLE:BEGIN -->.*?<!-- EXAMPLE:END -->",
           lambda m: "<!-- EXAMPLE:BEGIN -->\n" + block + "<!-- EXAMPLE:END -->", s, flags=re.S)

dep = json.loads((root / "docs" / "deployment.json").read_text())
oc_path = root / "docs" / "onchain.json"
oc = json.loads(oc_path.read_text()) if oc_path.exists() else {}
E = "https://testnet.nearblocks.io"
L = ["## On-chain record (NEAR testnet)", "",
     f"* Contract: [`{dep['contract']}`]({E}/address/{dep['contract']}) (wasm sha256 `{dep['contract_wasm_sha256'][:16]}...`). Publisher `{dep['publisher']}`, challenger `{dep['challenger']}`.",
     "* Every transaction (account creation, deploys, run, challenge, forecasts) with its explorer link: [`docs/testnet_txs.tsv`](docs/testnet_txs.tsv)."]
if oc.get("run"):
    r = oc["run"]
    L += [f"* **Run #{r['id']}** by `{r['attester']}` at block {r['height']}, data through {r['meta']['data_through']}: [transaction]({E}/txns/{oc['run_tx']}).",
          f"  * `spec_hash` `{r['meta']['spec_hash']}`", f"  * `snapshot_hash` `{r['meta']['snapshot_hash']}`",
          f"  * `code_hash` `{r['meta']['code_hash']}`", f"  * `results_hash` `{r['meta']['results_hash']}`"]
    ch = oc.get("challenges") or []
    for c in ch:
        L.append(f"* **Challenge #{c['id']}** on {c['claim_id']} by `{c['challenger']}`: alternative verdict {c['alt_verdict']}, flips the published one: **{c['flips']}**. "
                 f"This one is the project's own robustness variant (gas-only fees, same snapshot), filed from a separate account to show the mechanism; it is not an independent third-party dispute.")
if oc.get("predictions"):
    sc = oc.get("scoreboard", {})
    L.append(f"* **{len(oc['predictions'])} pre-registered 80% forecast intervals** (7 metrics x horizons 1, 2, 4 weeks), committed {oc.get('predictions_registered_utc', '')} for weeks that had not ended. "
             f"Scoreboard at {oc.get('fetched_utc', '')}: {sc.get('resolved', 0)} resolved, {sc.get('hits', 0)} hits. First resolution possible Mon 2026-11-16 00:00 UTC.")
new = "<!-- ONCHAIN:BEGIN -->\n" + "\n".join(L) + "\n<!-- ONCHAIN:END -->"
s = re.sub(r"<!-- ONCHAIN:BEGIN -->.*?<!-- ONCHAIN:END -->", lambda m: new, s, flags=re.S)
p.write_text(s, encoding="utf-8")
print("README example + on-chain blocks updated")
