# Model changelog

The model was frozen at **1.0.0** (git tag `model-v1.0.0`) for the launch of the
Victorian 2026 forecast. Its blind tests were scored with the structure and settings
already visible to the people building it, so they are probably a little flattering
(model review, finding V1).

From 1.0.0 on, record every change to model code or settings here: what changed, why,
whether it was made after looking at a blind test's results, and which tests were rerun.
Bug fixes and data corrections count. Bump `MODEL_VERSION` in
`src/prophecy/publish/forecast.py` for any change that alters a published forecast.

## 2.0.0 (27 Nov 2026)

Statistical and UI overhaul on branch `statistical_uplift`, motivated by an independent
statistical review of 1.0.0 and its 20 blind tests:

- **Multivariate Stan poll aggregator (`poll_aggregator.stan`, `poll_aggregator_corr.stan`, `aggregate.py`):**
  Replaced independent univariate normal poll likelihoods with a per-poll `multi_normal_cholesky`
  likelihood carrying the within-poll multinomial sampling covariance; moved pollster house
  effects onto the ALR scale with exact zero-sum isometric Helmert contrasts over reporting
  pollsters (`J_k >= 2`); integrated multi-week polls across their full fieldwork window; added
  MRP design-effect weighting (`4.0`, effective sample cap `2000`); added a joint 2PP likelihood
  with latent preference-flow parameters `flow_alp`; and added an automatic warmup retry when
  `max_rhat > 1.01` or divergences occur (`vic-2026`: `max_rhat 1.012 -> 1.007`, bulk ESS `552 -> 991`).
- **Polling-error calibration & sparse-poll prior (`backtest.py`, `simulate.py`, `pipeline.py`):**
  Switched `pooled_poll_error` to bias-centred residual variance net of Stage 1 raw-poll sampling
  variance; applied systematic errors and bias corrections on the ALR scale via the exact
  delta-method inverse Jacobian (including correlated One Nation error); and replaced independent
  Gaussian swings in `swing_prior` with shrunk correlated ALR Student-t swings routing 60% of
  anti-government swing to the major opposition.
- **Seat-level swing & spatial model (`swing_fit.py`, `simulate.py`):**
  Replaced unweighted OLS with heteroscedastic Student-t IRLS (bloc-specific intercepts,
  unbalanced random-effects ANOVA for regional variance, within-region de-meaning for pure
  seat-shock tails); added empirical cross-party correlations for regional and seat shocks;
  switched One Nation geography from multiplicative scaling to logit-scale swings; and replaced
  naive row-normalization with Sinkhorn-Knopp raking preserving contest masks and statewide
  vote conservation.
- **Preference flows, independents, Hare-Clark & GIS notionals (`preferences.py`, `new_candidates.py`, `hareclark.py`, `states.py`):**
  Added seat-heterogeneous preference flows with a mild anti-incumbent tilt for independents
  and OPV row normalization after ONP jitter; added thresholded incumbent-targeted cannibalization
  for major independent surges (`>8` pts) and `1/sqrt(k)` dampening for multiple first-time
  independents; added empirical Hare-Clark division swing SDs, stochastic exhaustion, and
  intra-ticket surplus leakage (`8%`); and added a pre-election GIS point-in-polygon notional
  baseline path.
- **Website & uncertainty UX (`web/src/`):**
  Added in-browser 20,000-simulation conditioning (`ScenarioExplorer` + Bellwether seats from
  `*-sims.bin`), Hypothetical Outcome Plots ("Simulate 1 election night"), Seat Forecast Drawer,
  multi-mode forecast maps, minor-party seat histograms, house-effect forest plots, hoverable
  poll details + pollster highlight syncing, 90% binomial calibration intervals, homepage live
  odds, and a dark/light theme toggle.

## 1.0.0 (11 Nov 2026)

Launch version. Blind tests of 20 elections, all from clean commits
(`data/processed/backtest_summary.csv`). Victoria: 2018 favourite right in 87.5% of
seats (status quo 86.4%), Brier 0.170; 2022 88.6% (status quo 88.6%), Brier 0.180.
