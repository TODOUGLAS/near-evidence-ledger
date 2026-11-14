# Why these thresholds

Thresholds live in `ledger/claims.py` (`CLAIMS`). They are **round numbers with a stated reason**, fixed in
code before the verdicts were computed. Full disclosure: the author had seen coarse history charts of the series
(for example that activity fell from its 2024-25 peak) while writing them, so they are not blind. They were not
changed after the verdicts appeared. If you disagree with a threshold, change one line and re-run `make offline`.

| id | threshold | reason |
|---|---|---|
| C1 | ratio >= 1.0 | "not shrinking" means no decline against the same weeks a year earlier; a ratio is scale-free. |
| C2 | >= 100,000 daily active accounts | a round figure for "a user base of six figures"; the weekly median is used because single-day bot bursts make the daily series spiky. |
| C3 | >= 1% of market cap, annualised | a 1% fee yield is a common order-of-magnitude bar for "revenue exists" for a network asset; gas-only yield is shown next to it. |
| C4 | latest >= trailing 52-week median | "liquidity holds" = not below its own one-year norm. |
| C5 | >= +5% in 13 weeks | roughly 20% a year; below this the stablecoin float is flat for practical purposes. |
| C6 | correlation >= 0.2 | the smallest value usually read as a weak-but-real positive relation; below it, price is not tracking usage. |
| C7 | Nakamoto coefficient >= 10 at 1/3 stake | a round figure; one third is the BFT safety threshold. A value inside +-5% of the threshold is reported INCONCLUSIVE by rule. |
| C8 | <= 5% supply growth in 52 weeks | a round cap for "modest dilution". |
| C9 | ratio >= 1.0 (13 weeks vs the 13 before) | "keeps growing" = no quarter-on-quarter decline of median weekly NEAR Intents volume. |
| C10 | fees >= 0.10% of volume (10 bps) | a round figure for "intent flow monetises"; the take rate of intent/bridge aggregators is usually quoted in basis points. |

**C9 and C10 were added later (14.11, v2)**, because the NEAR thesis is about intent flow and the first eight claims did not measure it. Disclosure: before fixing their thresholds the author had seen DefiLlama's 30-day aggregates for NEAR Intents (about 3.8 B USD volume and 5.8 M USD fees, i.e. a take rate near 0.15%), but no weekly value of either claim. 10 bps is a round number below that rate, so C10 is not a hard test; C9 (ratio >= 1) is the neutral momentum bar. Both are reported with the same rule, and the robustness table shows how C9 behaves for other windows.

Verdict rule (see `ledger/claims.py`): with a 90% moving-block bootstrap interval, SUPPORTED if the whole interval
passes, REFUTED if the whole interval fails, otherwise INCONCLUSIVE. Point-in-time statistics without a sampling model
(C5, C7, C8) are INCONCLUSIVE inside +-5% (relative) of the threshold and decided by the point value otherwise.
