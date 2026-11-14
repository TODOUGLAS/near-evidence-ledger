# Clean-room run ("as a screener")

Run on 2026-11-14 02:14 CST (08:14 UTC) on the build box: the final repository was copied to an empty directory
**without** `.venv`, `data/raw`, `data/cache`, `site/`, `output/` and `contract/target`, then only the README commands were used:

1. `python3 -m venv .venv && . .venv/bin/activate`
2. `pip install -r requirements.txt` (six pinned libraries, Python 3.13.5)
3. `python -m ledger all --offline`: ten claims, backtest, robustness, dashboard (`site/index.html`, 5.2 MB, works offline), `output/report.md`
4. `python -m ledger test`: 34 tests, OK
5. `python -m ledger verify`: `RESULT: ALL MATCH` against run #0 on `evledger-1114.testnet` (spec, snapshot, results, code hashes, ten verdicts, 21 of 21 forecasts)

Whole sequence 62 s on 8 cores (cold backtest cache, network used only by `verify` for RPC reads).
The dashboard contains the sections "On-chain record" and "How fragile is each verdict?".
Contract tests (maintainer only, needs Rust 1.100 via `rust-toolchain.toml`): `cd contract && cargo test --lib` (19 tests including a 480-vector replay of the verdict rule shared with Python), `cargo clippy` clean.
Not verified: GitHub Actions (`.github/workflows/verify.yml`) has not been executed on GitHub because no repository exists yet.
