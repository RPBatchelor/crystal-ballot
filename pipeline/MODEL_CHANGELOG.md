# Model changelog

The model was frozen at **1.0.0** (git tag `model-v1.0.0`) for the launch of the
Victorian 2026 forecast. Its blind tests were scored with the structure and settings
already visible to the people building it, so they are probably a little flattering
(model review, finding V1).

From 1.0.0 on, record every change to model code or settings here: what changed, why,
whether it was made after looking at a blind test's results, and which tests were rerun.
Bug fixes and data corrections count. Bump `MODEL_VERSION` in
`src/prophecy/publish/forecast.py` for any change that alters a published forecast.

## 1.0.0 (11 Nov 2026)

Launch version. Blind tests of 20 elections, all from clean commits
(`data/processed/backtest_summary.csv`). Victoria: 2018 favourite right in 87.5% of
seats (status quo 86.4%), Brier 0.170; 2022 88.6% (status quo 88.6%), Brier 0.180.
