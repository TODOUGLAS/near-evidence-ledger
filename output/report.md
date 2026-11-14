# NEAR Evidence Ledger: report (data through week ending 2026-11-08)

NEAR is an infrastructure bet on settlement flow for agents and intents, not on raw layer-1 transaction counts. The thesis holds only if (a) real fee revenue exists on the chain, (b) liquidity and stablecoins stay on it, (c) validation stays decentralised, (d) dilution stays modest and (e) intent flow, the settlement volume of NEAR Intents, keeps growing and pays a fee. The risks are shrinking organic usage and a price that does not track usage. Each statement below is a claim with a numeric threshold that the data can refute.

## Claims

| # | Claim | Measured | 90% interval | Threshold | Verdict | Sources (fetched UTC) |
|---|---|---|---|---|---|---|
| C1 | Usage is not shrinking: median weekly transactions of the last 13 weeks are at least equal to the same 13 weeks one year earlier. | 0.15 | 0.14 to 0.19 | >= 1.00 | **REFUTED** | nb_charts (2026-11-13T23:53:07Z) |
| C2 | The user base is large: median of weekly-median daily active accounts over the last 13 weeks is at least 100,000. | 71,159 | 55,503 to 79,464 | >= 100,000 | **REFUTED** | nb_charts (2026-11-13T23:53:07Z) |
| C3 | Real revenue exists: fees paid on the NEAR chain (network + protocols, DefiLlama), annualised from the last 13 weeks, are at least 1% of current market capitalisation. | 1.86% | 1.57% to 2.29% | >= 1.00% | **SUPPORTED** | dl_fees (2026-11-13T23:53:15Z), nb_stats (2026-11-13T23:53:08Z) |
| C4 | DeFi liquidity holds: latest weekly TVL is at least its trailing 52-week median. | 1.54 | 1.42 to 1.75 | >= 1.00 | **SUPPORTED** | dl_tvl (2026-11-13T23:53:14Z) |
| C5 | Stablecoin float is growing: stablecoin supply on NEAR is at least 5% higher than 13 weeks earlier. | 1.6% | n/a | >= 5.0% | **REFUTED** | dl_stable (2026-11-13T23:53:15Z) |
| C6 | Price tracks usage: over the last 52 weeks the correlation between weekly log change of price and weekly log change of active accounts is at least 0.2. | -0.10 | -0.28 to 0.13 | >= 0.20 | **REFUTED** | nb_charts (2026-11-13T23:53:07Z) |
| C7 | Validation is decentralised: at least 10 validators are needed to control one third of the stake (the BFT safety threshold). | 10 | n/a | >= 10 | **INCONCLUSIVE** | rpc_validators (2026-11-13T23:53:14Z) |
| C8 | Dilution is modest: total supply grew by at most 5% over the last 52 weeks. | 2.5% | n/a | <= 5.0% | **SUPPORTED** | nb_charts (2026-11-13T23:53:07Z) |
| C9 | Intent flow keeps growing: median weekly NEAR Intents volume of the last 13 weeks is at least the median of the 13 weeks before them. | 1.93 | 1.68 to 2.18 | >= 1.00 | **SUPPORTED** | dl_intents_vol (2026-11-14T08:05:53Z) |
| C10 | Intent flow monetises: fees DefiLlama attributes to NEAR Intents are at least 0.10% of its volume over the last 13 weeks. | 0.154% | 0.141% to 0.166% | >= 0.100% | **SUPPORTED** | dl_intents_vol (2026-11-14T08:05:53Z), dl_intents_fees (2026-11-14T08:05:53Z) |

## Backtest coverage (rolling origin, last 156 weekly origins; 80% / 95% nominal)

| metric | h | method | 80% | 95% | origins | n_eff |
|---|---|---|---|---|---|---|
| txns | 4 | gauss | 95% | 96% | 156 | 39 |
| txns | 4 | conformal | 80% | 94% | 156 | 39 |
| txns | 4 | qgbm | 90% | 95% | 39 | 10 |
| txns | 12 | gauss | 87% | 91% | 156 | 13 |
| txns | 12 | conformal | 74% | 85% | 156 | 13 |
| txns | 12 | qgbm | 69% | 87% | 39 | 3 |
| active_accounts | 4 | gauss | 91% | 94% | 156 | 39 |
| active_accounts | 4 | conformal | 87% | 96% | 156 | 39 |
| active_accounts | 4 | qgbm | 85% | 92% | 39 | 10 |
| active_accounts | 12 | gauss | 82% | 99% | 156 | 13 |
| active_accounts | 12 | conformal | 87% | 97% | 156 | 13 |
| active_accounts | 12 | qgbm | 69% | 87% | 39 | 3 |
| net_fees_usd | 4 | gauss | 79% | 88% | 156 | 39 |
| net_fees_usd | 4 | conformal | 78% | 92% | 156 | 39 |
| net_fees_usd | 4 | qgbm | 74% | 95% | 39 | 10 |
| net_fees_usd | 12 | gauss | 72% | 87% | 156 | 13 |
| net_fees_usd | 12 | conformal | 72% | 88% | 156 | 13 |
| net_fees_usd | 12 | qgbm | 82% | 97% | 39 | 3 |
| price | 4 | gauss | 75% | 92% | 156 | 39 |
| price | 4 | conformal | 72% | 92% | 156 | 39 |
| price | 4 | qgbm | 72% | 90% | 39 | 10 |
| price | 12 | gauss | 67% | 92% | 156 | 13 |
| price | 12 | conformal | 65% | 85% | 156 | 13 |
| price | 12 | qgbm | 56% | 87% | 39 | 3 |
| tvl | 4 | gauss | 75% | 90% | 156 | 39 |
| tvl | 4 | conformal | 74% | 92% | 156 | 39 |
| tvl | 4 | qgbm | 77% | 95% | 39 | 10 |
| tvl | 12 | gauss | 75% | 85% | 156 | 13 |
| tvl | 12 | conformal | 78% | 92% | 156 | 13 |
| tvl | 12 | qgbm | 79% | 82% | 39 | 3 |
| stable_usd | 4 | gauss | 80% | 88% | 156 | 39 |
| stable_usd | 4 | conformal | 71% | 89% | 156 | 39 |
| stable_usd | 4 | qgbm | 59% | 82% | 39 | 10 |
| stable_usd | 12 | gauss | 72% | 84% | 156 | 13 |
| stable_usd | 12 | conformal | 70% | 86% | 156 | 13 |
| stable_usd | 12 | qgbm | 47% | 67% | 36 | 3 |
| dl_fees_usd | 4 | gauss | 93% | 100% | 67 | 17 |
| dl_fees_usd | 4 | conformal | 87% | 99% | 67 | 17 |
| dl_fees_usd | 4 | qgbm | 58% | 83% | 12 | 3 |
| dl_fees_usd | 12 | gauss | 98% | 100% | 51 | 4 |
| dl_fees_usd | 12 | conformal | 96% | 100% | 51 | 4 |
| dl_fees_usd | 12 | qgbm | 62% | 88% | 8 | 1 |
| fee_per_txn_near | 4 | gauss | 88% | 93% | 156 | 39 |
| fee_per_txn_near | 4 | conformal | 78% | 91% | 156 | 39 |
| fee_per_txn_near | 4 | qgbm | 90% | 92% | 39 | 10 |
| fee_per_txn_near | 12 | gauss | 87% | 90% | 156 | 13 |
| fee_per_txn_near | 12 | conformal | 74% | 88% | 156 | 13 |
| fee_per_txn_near | 12 | qgbm | 82% | 95% | 39 | 3 |

## Point-forecast skill of the base case vs a no-change random walk (positive = better)

| metric | h | damped-trend candidate (phi 0.9) | shipped model |
|---|---|---|---|
| txns | 4 | -21% | -1% |
| txns | 12 | -13% | -7% |
| active_accounts | 4 | -8% | +5% |
| active_accounts | 12 | -6% | -0% |
| net_fees_usd | 4 | -20% | -2% |
| net_fees_usd | 12 | -14% | -6% |
| price | 4 | -13% | -4% |
| price | 12 | -21% | -13% |
| tvl | 4 | -11% | -4% |
| tvl | 12 | -22% | -7% |
| stable_usd | 4 | -6% | -4% |
| stable_usd | 12 | -25% | -11% |
| dl_fees_usd | 4 | -24% | -1% |
| dl_fees_usd | 12 | -48% | -44% |
| fee_per_txn_near | 4 | -24% | -1% |
| fee_per_txn_near | 12 | -24% | +1% |

## Scenarios, 12 weeks ahead (bear=p10, base=p50, bull=p90)

| metric | latest | bear | base | bull | target week |
|---|---|---|---|---|---|
| Weekly transactions | 4,684,451 | 1,417,864 | 4,067,041 | 5,090,023 | 2027-01-31 |
| Weekly-median daily active accounts | 78,560 | 43,150 | 57,930 | 72,497 | 2027-01-31 |
| Weekly network fees (USD) | 21,935 | 8,910 | 17,054 | 37,679 | 2027-01-31 |
| NEAR price (USD) | 3.73 | 1.97 | 3.63 | 6.97 | 2027-01-31 |
| TVL (USD) | 175,085,497 | 102,827,042 | 167,312,316 | 304,466,125 | 2027-01-31 |
| Stablecoins on NEAR (USD) | 130,477,212 | 61,587,661 | 123,885,656 | 157,089,213 | 2027-01-31 |

## Sensitivity of weekly network fees (1 sigma per factor)

| factor | sigma (log) | -1 sigma | +1 sigma |
|---|---|---|---|
| Transactions | 0.499 | 11,683 | 31,672 |
| NEAR price | 0.493 | 11,750 | 31,492 |
| Fee per txn (NEAR) | 0.126 | 16,952 | 21,827 |

## How fragile is each verdict? (flip distance and variants)

| claim | verdict | threshold change that flips it | variants with the same verdict | label |
|---|---|---|---|---|
| C1 | REFUTED | -81.5% | 4 of 4 | ROBUST |
| C2 | REFUTED | -21.0% | 3 of 4 | MOSTLY STABLE |
| C3 | SUPPORTED | +57.5% | 3 of 4 | MOSTLY STABLE |
| C4 | SUPPORTED | +42.0% | 3 of 3 | ROBUST |
| C5 | REFUTED | -66.5% | 2 of 3 | FRAGILE |
| C6 | REFUTED | -37.5% | 2 of 3 | FRAGILE |
| C7 | INCONCLUSIVE | -5.0% | 1 of 3 | FRAGILE |
| C8 | SUPPORTED | -48.0% | 3 of 3 | ROBUST |
| C9 | SUPPORTED | +68.0% | 3 of 4 | MOSTLY STABLE |
| C10 | SUPPORTED | +42.0% | 4 of 4 | ROBUST |

Source ids and URLs: see output/FETCH_LOG.json. Every number on the dashboard (site/index.html) is a link to its source.
