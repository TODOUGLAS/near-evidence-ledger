# Competitive scan: who solves "is this investment thesis true?" and what is still missing

Scope and method: a time-boxed scan on 2026-11-14 (web search plus reading each product's own docs or GitHub repository). Every
row links to the page it is based on. We could only see public material, so "they do not do X" means "we found no public
evidence that they do X", not proof. Corrections are welcome.

## 1. What exists

### 1a. Crypto research and analytics (the thesis side)

| Product | What it does | How it handles evidence | Gap for a *testable* thesis |
|---|---|---|---|
| [Messari](https://docs.messari.io/user-guides/messari-features/research) | Analyst-written protocol reports plus quantitative data (exchange, on-chain, CoinMetrics, GitHub dev activity: [metric definitions](https://docs.messari.io/glossary/data-metrics/asset-metrics-definitions)) | Curated by analysts; data definitions are documented | Conclusions are prose. No pre-declared thresholds, no computed verdict, no way to re-run a report |
| [Token Terminal](https://tokenterminal.com/docs/data-approach) | Standardised protocol financials; keeps raw transaction-level data in an ELT pipeline so numbers can be traced and reprocessed ([methodologies](https://tokenterminal.com/resources/articles/launching-methodologies)) | Auditable pipeline, documented definitions | Shows metrics, not claims. Results are not committed anywhere a third party can compare |
| [Artemis](https://research.artemis.ai/p/announcing-artemis-source-availability) | Comparable chain economics; publishes the queries behind its metrics so anyone can reproduce them | Source availability of the metric queries | Strong on reproducing a *metric*. Nothing about thresholds, verdicts, intervals or forecasts |
| [DefiLlama](https://github.com/DefiLlama/DefiLlama-Adapters) (open adapters, [how to write one](https://docs.llama.fi/list-your-project/how-to-write-an-sdk-adapter)) and its [NEAR thesis page](https://investors.defillama.com/near) | Open-source TVL/fees adapters, reviewed by PR; the NEAR page states a thesis (fee run-rate, P/S) | Methodology text in the PR; adapter code is public | The thesis page states conclusions as text; nothing tests them against a bar fixed in advance |
| [Dune](https://github.com/duneanalytics/docsV2) ([version history](https://docs.dune.com/web-app/query-editor/version-history), [query lineage](https://docs.dune.com/web-app/query-editor/query-lineage)) incl. the official [NEAR Intents](https://dune.com/near/near-intents) and [Revenue](https://dune.com/near/revenue-dashboard) dashboards | Public, forkable SQL dashboards with versioned queries | Re-runnable by design | A dashboard is mutable: the number you saw yesterday is not committed or hashed. No verdicts |
| [Nansen](https://nansen.ai/post/what-is-smart-money-in-crypto-a-detailed-look-into-our-methodology) | Wallet labels ("smart money") from manual and automated rules | Methodology post; labels are proprietary | Closed labels, no re-run, no claims |
| [Electric Capital Open Dev Data](https://opendevdata.org/) ([repo](https://github.com/electric-capital/developer-reports)) | Replaced the annual PDF with continuously updated open datasets (MIT code, CC BY 4.0 data) | Open data and taxonomy, community-curated | Datasets, not claims or verdicts |
| [L2BEAT](https://github.com/l2beat/l2beat) ([Risk Rosette](https://forum.l2beat.com/t/the-risk-rosette-framework/292), [Stages](https://medium.com/l2beat/introducing-stages-a-framework-to-evaluate-rollups-maturity-d290bb22befe)) | Open-source site that grades L2s green/yellow/red against written criteria | Closest in spirit: criteria fixed in public, categorical verdicts | Criteria are applied by humans; no statistical intervals, no input-data hash, no on-chain record, no challenge mechanism |
| NEAR's own hub: [near.org/research-analytics](https://www.near.org/research-analytics) and [revenue.near.org](https://revenue.near.org/) | Lists Artemis, Dune, Flipside, Messari, Nansen, The Tie dashboards; revenue and fee-capture tracker | Live metrics | All of them display metrics; none states falsifiable claims with a threshold and a verdict |

### 1b. On-chain attestation, oracles, disputes (the commitment side)

| Product | What it does | Why it is not the same thing |
|---|---|---|
| [Ethereum Attestation Service](https://easscan.org/docs) ([contracts](https://github.com/ethereum-attestation-service/eas-contracts)) | Generic schema + attestation registry; resolver contracts can add checks | A general primitive on EVM. It would store our hashes, but a resolver would have to be written to enforce a *verdict rule*; there is no equivalent on NEAR. We ship a purpose-built registry whose rule runs in the contract |
| [UMA Optimistic Oracle](https://docs.uma.xyz/protocol-overview/how-does-umas-oracle-work) ([OOv3 source](https://github.com/UMAprotocol/protocol/blob/master/packages/core/contracts/optimistic-oracle-v3/implementation/OptimisticOracleV3.sol)) | Anyone asserts a fact with a bond; if undisputed during liveness it is true; if disputed, token holders vote | Resolves *subjective or real-world* questions by economic voting. Disputes are decided by stake, not by recomputation, and that has failed in public: a large UMA holder swung a $7M Polymarket market ([CoinDesk, 2025-03-26](https://www.coindesk.com/markets/2025/03/26/polymarket-suffers-uma-governance-attack-after-rouge-actor-becomes-top-5-token-staker)) |
| [Reality.eth](https://docs.kleros.io/products/reality) and [Kleros](https://docs.kleros.io/court/how-it-works) | Crowd-sourced oracle with escalating bonds; Kleros jurors vote on appeal | Same family: human voting resolves disputes. Nothing computes or re-runs anything |
| [Chainlink Proof of Reserve](https://chain.link/proof-of-reserve) ([how it works](https://matrixed.link/blog/chainlink-proof-of-reserve)) | A DON of nodes observes a reserve and publishes a signed aggregate on-chain; contracts can refuse to mint if coverage drops | Excellent for a *feed* that contracts consume. It is a trusted-network attestation of one number, not an open, recomputable, challengeable verdict |
| [Space and Time Proof of SQL](https://docs.spaceandtime.io/docs/zk-proven-sql-queries-technical) ([repo](https://github.com/spaceandtimefdn/sxt-proof-of-sql)) | Zero-knowledge proof that a SQL result was computed correctly over committed data | Stronger *computation* integrity than ours, but it proves a query, not a claim: no thresholds, verdict semantics, intervals or forecasts, and it needs their network |
| [TLSNotary](https://tlsnotary.org/) | Proves that data came from a given web API (TLS transcript) | Complementary: it would prove our API responses are authentic (see "Next steps"); it does not define or judge claims |
| [OpenTimestamps](https://github.com/opentimestamps/opentimestamps-client/) and git-based pre-registration | Anchors a hash in Bitcoin ("existed by time T") | Complementary. The standard open-science idea (pre-register, then test) that we implement with NEAR block time |

### 1c. Claim verification and forecast scoring (the method side)

| Product | Relevant idea | Limit for our use |
|---|---|---|
| [FEVER](https://fever.ai/dataset/fever.html) ([paper](https://aclanthology.org/N18-1074/)) | Three-way label SUPPORTED / REFUTED / NOT ENOUGH INFO with evidence | Text claims and Wikipedia evidence. We reuse the label scheme with *numeric* evidence and a computable rule |
| [Community Notes](https://github.com/twitter/communitynotes) ([ranking](https://github.com/twitter/communitynotes/blob/main/documentation/under-the-hood/ranking-notes.md)) | Fully open-source ranking, so anyone can check why a note is shown | Crowd consensus on posts, not data-backed numeric claims |
| [Metaculus](https://www.metaculus.com/questions/track-record/) | Public track records, calibration curves, scored forecasts | Human forecasters and subjective questions, off-chain. We copy the idea (a scored, public record), with machine-made intervals and on-chain scoring |
| Polymarket (resolved through UMA, above) | Prices thesis-like questions with real money | Needs a liquid market per question, resolves by vote; cannot grade an arbitrary data claim cheaply |

## 2. The gap

Each *piece* below exists somewhere. We found no public product or repository that puts all of them together for an
investment thesis:

1. claims with **numeric thresholds written before the verdict**, in a machine-readable spec (L2BEAT has public criteria, not code-evaluated claims);
2. **computed three-way verdicts with statistical intervals** (FEVER's labels, but numeric and with bootstrap intervals);
3. the **exact input data and the code, hashed and committed on a public chain** (EAS can store a hash; nobody commits a *data snapshot + code + verdict table*);
4. an **on-chain rule that refuses a verdict that contradicts its own numbers** (UMA/Kleros/Reality.eth accept whatever the stake says);
5. a **permissionless challenge by recomputation**: a challenger posts another snapshot hash or number and the contract computes whether the verdict flips (UMA/Kleros settle by vote);
6. **pre-registered interval forecasts scored on-chain** (Metaculus scores human forecasts off-chain; nobody scores calibrated machine intervals on a public chain);
7. a **robustness report per verdict**: how far the threshold must move, and how the verdict behaves under other windows and another data source (no dashboard in 1a does this);
8. **one command that re-checks the chain record** (`python -m ledger verify`) and a CI workflow that runs it daily.

For NEAR specifically, the official hub ([near.org/research-analytics](https://www.near.org/research-analytics)) points to six
dashboard products; none of them states a claim that could be refuted. The Evidence Ledger is that missing layer: it sits on top
of the same public data they use.

## 3. What we borrowed

* Pre-registration and a public record (open science, [OpenTimestamps](https://github.com/opentimestamps/opentimestamps-client/), [Metaculus](https://www.metaculus.com/questions/track-record/)).
* Open, re-runnable methodology (Artemis, Token Terminal, DefiLlama adapters, Dune lineage).
* A three-way verdict vocabulary (FEVER).
* "Permissionless dispute, with the dispute stored next to the claim" (UMA, Kleros), but resolved by *recomputation*, not a vote.

## 4. What we do NOT claim

* **Not an oracle and not cryptoeconomically secure.** There are no bonds, no jurors, no slashing. A dispute is a public, machine-checked record, not a ruling. A malicious publisher can commit a fabricated snapshot; the defence is that anyone can re-fetch the same public APIs and compare (`verify`, `challenge`).
* **Data authenticity is trusted, not proven**: the snapshot hash proves *which bytes* were used, not that the API really sent them. TLSNotary-style proofs are the natural next step.
* **Testnet only**, one publisher account, no mainnet transaction.
* **Computation integrity is by re-execution**, not by a zero-knowledge proof (Space and Time is stronger there).
* Absence of evidence in a web scan is not proof of absence: private tools may do parts of this.
