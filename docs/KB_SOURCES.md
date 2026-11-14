# Knowledge-base sources (methodology)

Chunk ids are from the team's private book knowledge base (`kb` CLI); each id was opened and read on 2026-11-13.
They justify methods, not NEAR facts: every NEAR fact comes from the data sources in `FETCH_LOG.json`.

| KB id | Book | What we took from it |
|---|---|---|
| b174-00029, b174-00032 | K. Murphy, *Probabilistic Machine Learning: Advanced Topics* (2024), §14.3 Conformal prediction | prediction intervals from held-out residuals (our split-conformal quantiles of past h-step errors) |
| b174-00036, b174-00037 | Murphy (2024), quantile regression | the quantile gradient-boosting comparison model; the book notes regression quantiles give only *approximate* coverage, which our backtest measures |
| b132-00274, b132-00281 | S. Raschka, *Machine Learning Q and AI* (2024) | conformal predictions vs plain prediction intervals; why we report empirical coverage |
| x025-00367 | S. Kaabar, *Deep Learning for Finance* (2024), rolling window cross validation | rolling-origin evaluation |
| b070-00352, b070-00354 | L. Moroney, *AI and ML for Coders in PyTorch* (2025), naive forecast | the no-change baseline that every model is compared with (and that wins) |
| b193-00277 | P. Hall, J. Curtis, *Machine Learning for High-Risk Applications* (2025): "Do not use the future to predict the past" | no-leakage rule; enforced by `tests/test_ledger.py::test_no_leakage_*` |
| b104-00723, b083-00537 | J. M. Shea, *Foundations of Data Science with Python* (2024); T. Timbers et al., *Data Science* (2025) | bootstrap percentile confidence intervals (we use the moving-block variant for autocorrelated weekly data) |
| b114-01085 | A. Geron, *Hands-On Machine Learning with Scikit-Learn and PyTorch* (2026) | a weekly pattern in a daily series, the reason for weekly aggregation |
| b125-00160 | V. Smolyakov, *Machine Learning Algorithms in Depth* (2024), hierarchical Bayes | considered (shared prior across metrics) and **not used**, to keep the model auditable |
| b137-00331 | M. Ryan, L. Massaron, *Machine Learning for Tabular Data* (2025) | gradient boosting needs data; consistent with its weak showing on ~150-300 weekly points |
