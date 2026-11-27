"""Tests for the P0/P1 statistical uplift fixes (E1-E5, G1-G2)."""

from datetime import date

import numpy as np
import polars as pl
import pytest

from prophecy.jurisdictions import Election
from prophecy.model.aggregate import inits, prepare
from prophecy.model.preferences import BLOCS, IDX, count, draw_seat_weights, draw_weights
from prophecy.model.simulate import SeatInputs, SimConfig, _recentre, simulate, statewide_shares


def _simple_inputs(n_seats: int = 20, contest_onp_half: bool = False) -> SeatInputs:
    rng = np.random.default_rng(42)
    base = np.zeros((n_seats, len(BLOCS)))
    base[:, IDX["ALP"]] = rng.uniform(0.28, 0.44, n_seats)
    base[:, IDX["COAL"]] = rng.uniform(0.28, 0.44, n_seats)
    base[:, IDX["GRN"]] = rng.uniform(0.06, 0.16, n_seats)
    base[:, IDX["IND"]] = 0.02
    base[:, IDX["OTH"]] = np.maximum(1.0 - base.sum(axis=1), 0.04)
    base /= base.sum(axis=1, keepdims=True)
    contest = np.ones((n_seats, len(BLOCS)), dtype=bool)
    if contest_onp_half:
        contest[n_seats // 2 :, IDX["ONP"]] = False
    return SeatInputs(
        districts=[f"Seat_{i}" for i in range(n_seats)],
        regions=[f"Reg_{i % 4}" for i in range(n_seats)],
        weight=np.full(n_seats, 40_000.0),
        base=base,
        onp_index=np.linspace(0.4, 2.5, n_seats),
        coal_party=["LIB"] * n_seats,
        incumbent=["COAL" if i % 2 == 0 else "ALP" for i in range(n_seats)],
        contest=contest,
    )


def _uniform_flows() -> np.ndarray:
    w = np.full((len(BLOCS), len(BLOCS)), 0.2)
    np.fill_diagonal(w, 0.0)
    return w / w.sum(axis=1, keepdims=True)


def test_e1_prepare_and_inits_multivariate_zero_sum():
    prev = Election("test-2022", "VIC", "assembly", date(2022, 11, 26), 10, "b1")
    elec = Election("test-2026", "VIC", "assembly", date(2026, 11, 28), 10, "b1")
    polls = pl.DataFrame({
        "pollster": ["A", "B", "A"],
        "field_start": [date(2023, 1, 1), date(2023, 2, 1), date(2023, 3, 1)],
        "field_end": [date(2023, 1, 5), date(2023, 2, 5), date(2023, 3, 5)],
        "sample_size": [1000, 1200, 1000],
        "ALP": [38.0, 36.0, 37.0],
        "COAL": [35.0, 37.0, 36.0],
        "GRN": [12.0, 11.0, 12.0],
        "ONP": [5.0, None, 6.0],  # Only pollster A reports ONP (J_k = 1 -> 0 free params)
    })
    start = {"ALP": 37.0, "COAL": 35.0, "GRN": 11.0, "ONP": 3.0, "OTH": 14.0}
    data, pollsters, _ = prepare(polls, prev, elec, start, ["ALP", "COAL", "GRN", "ONP", "OTH"])
    assert data["M"] == 3
    assert data["poll_m"] == [4, 3, 4]
    assert data["J_k"] == [2, 2, 2, 1]
    # H_free = (2-1) + (2-1) + (2-1) + 0 = 3
    init_list = inits(data, "poll_aggregator", chains=2, seed=1)
    assert len(init_list[0]["house_free"]) == 3


def test_e2_alr_polling_error_preserves_simplex_and_onp_correlation():
    cfg = SimConfig(n_per_draw=1, poll_error_df=200.0, poll_error_alr=True)
    cfg.poll_error_sd = {"ALP": 2.0, "COAL": 2.0, "GRN": 1.0, "ONP": 2.5}
    cfg.poll_error_corr = [[1.0, -0.5, -0.2], [-0.5, 1.0, -0.2], [-0.2, -0.2, 1.0]]
    cfg.poll_error_corr_parties = ["ALP", "COAL", "GRN"]
    agg = np.tile([22.0, 32.0, 13.0, 21.0, 12.0], (20_000, 1))
    out = statewide_shares(agg, ["ALP", "COAL", "GRN", "ONP", "OTH"], cfg, np.random.default_rng(7))
    # Exact simplex sum without clipping distortion
    assert np.allclose(out.sum(axis=1), 100.0, atol=1e-9)
    assert (out[:, [IDX[p] for p in ("ALP", "COAL", "GRN", "ONP", "OTH")]] > 0).all()
    # ONP polling error negatively correlated with COAL
    r_onp_coal = np.corrcoef(out[:, IDX["ONP"]], out[:, IDX["COAL"]])[0, 1]
    assert r_onp_coal < -0.25


def test_e3_partial_contestation_conserves_statewide_vote_and_raking():
    inputs = _simple_inputs(n_seats=20, contest_onp_half=True)
    cfg = SimConfig(
        n_per_draw=1,
        poll_error_sd={},
        poll_bias={},
        seat_corr=[[1.0, -0.7, -0.1], [-0.7, 1.0, -0.1], [-0.1, -0.1, 1.0]],
        seat_corr_blocs=["ALP", "COAL", "GRN"],
        region_corr=[[1.0, -0.7, -0.1], [-0.7, 1.0, -0.1], [-0.1, -0.1, 1.0]],
        region_corr_blocs=["ALP", "COAL", "GRN"],
    )
    agg = np.tile([34.0, 36.0, 11.0, 8.0, 11.0], (400, 1))
    res = simulate(inputs, agg, ["ALP", "COAL", "GRN", "ONP", "OTH"], _uniform_flows(), cfg)
    # Non-contesting seats must remain strictly 0 for ONP, without inflating contested seats 2x
    assert np.all(res.seat_primary[:, 10:, IDX["ONP"]] == 0.0)
    assert res.seat_primary[:, :10, IDX["ONP"]].mean() * 100 < 12.0
    # Every seat sums to 1.0
    assert np.allclose(res.seat_primary.sum(axis=2), 1.0, atol=1e-9)
    # Full-contestation ONP (88/88 like vic-2026) conserves statewide ALP and ONP shares via raking
    w = inputs.weight / inputs.weight.sum()
    full_inputs = _simple_inputs(n_seats=20, contest_onp_half=False)
    res_full = simulate(full_inputs, agg, ["ALP", "COAL", "GRN", "ONP", "OTH"], _uniform_flows(), cfg)
    assert (res_full.seat_primary[:, :, IDX["ALP"]] @ w).mean() * 100 == pytest.approx(34.0, abs=0.4)
    assert (res_full.seat_primary[:, :, IDX["ONP"]] @ w).mean() * 100 == pytest.approx(8.0, abs=0.4)
    # Correlated seat shocks induce negative ALP-COAL swing correlation within seats
    alp_s = res_full.seat_primary[:, 0, IDX["ALP"]]
    coal_s = res_full.seat_primary[:, 0, IDX["COAL"]]
    assert np.corrcoef(alp_s, coal_s)[0, 1] < -0.4


def test_e5_logit_onp_saturates_smoothly_under_large_surge():
    inputs = _simple_inputs(n_seats=20, contest_onp_half=False)
    cfg = SimConfig(n_per_draw=1, poll_error_sd={}, poll_bias={})
    # Large 21.4% statewide ONP surge (like vic-2026)
    agg = np.tile([22.0, 32.0, 13.0, 21.4, 11.6], (500, 1))
    res = simulate(inputs, agg, ["ALP", "COAL", "GRN", "ONP", "OTH"], _uniform_flows(), cfg)
    max_onp_med = np.median(res.seat_primary[:, :, IDX["ONP"]], axis=0).max()
    # Highest-index seat should saturate well below 0.70 (not explode to 0.90 clip)
    assert 0.25 < max_onp_med < 0.65


def test_g1_g2_seat_heterogeneous_flows_and_ind_cannibalization():
    rng = np.random.default_rng(123)
    w = _uniform_flows()
    draws = draw_weights(w, 200, rng)
    # Rows remain normalized to 1 after ONP column jitter (preserves OPV exhaust scale)
    assert np.allclose(draws.sum(axis=2), 1.0, atol=1e-9)

    seat_w = draw_seat_weights(draws, ["COAL", "ALP", "IND"], rng, seat_sd=0.1, ind_sd=0.3,
                               ind_anti_incumbent_tilt=0.4)
    assert seat_w.shape == (200, 3, len(BLOCS), len(BLOCS))
    assert np.allclose(seat_w.sum(axis=3), 1.0, atol=1e-9)
    # In COAL-held seat 0, IND flows more to ALP than in ALP-held seat 1
    assert seat_w[:, 0, IDX["IND"], IDX["ALP"]].mean() > seat_w[:, 1, IDX["IND"], IDX["ALP"]].mean()
    # 4D weights work in count()
    shares = np.full((200, 3, len(BLOCS)), 1.0 / len(BLOCS))
    winner, final = count(shares, seat_w)
    assert winner.shape == (200, 3) and final.shape == (200, 3, len(BLOCS))

    # Incumbent-targeted cannibalization: a surging IND in COAL-held seat 0 hits COAL harder
    inputs = _simple_inputs(n_seats=10)
    inputs.ind_prior = np.full(10, np.nan)
    inputs.ind_prior[0] = 0.25  # seat 0 is COAL-held
    agg = np.tile([35.0, 35.0, 10.0, 20.0], (300, 1))
    cfg_on = SimConfig(n_per_draw=1, poll_error_sd={}, poll_bias={}, ind_incumbent_cannibal=0.7)
    cfg_off = SimConfig(n_per_draw=1, poll_error_sd={}, poll_bias={}, ind_incumbent_cannibal=0.0)
    r_on = simulate(inputs, agg, ["ALP", "COAL", "GRN", "OTH"], w, cfg_on)
    r_off = simulate(inputs, agg, ["ALP", "COAL", "GRN", "OTH"], w, cfg_off)
    assert r_on.seat_primary[:, 0, IDX["COAL"]].mean() < r_off.seat_primary[:, 0, IDX["COAL"]].mean() - 0.03


def test_e4_swing_fit_returns_correlated_residuals():
    from prophecy.model import swing_fit

    p = swing_fit.fit(date(2026, 11, 28), "VIC", log=lambda _: None)
    assert p is not None
    assert p.seat_corr is not None and p.region_corr is not None
    for mat in (np.asarray(p.seat_corr), np.asarray(p.region_corr)):
        assert mat.shape == (3, 3)
        assert np.allclose(mat, mat.T)
        assert np.allclose(np.diag(mat), 1.0)
        assert np.all(np.linalg.eigvalsh(mat) > 0)
    assert p.df["ALP"] < 10.0 and p.df["COAL"] < 10.0
    cfg = swing_fit.apply(SimConfig(), p)
    assert cfg.seat_corr is not None and cfg.region_corr is not None


def test_g3_multiweek_mrp_weighting_and_joint_tpp_prepare():
    prev = Election("test-2022", "VIC", "assembly", date(2022, 11, 26), 10, "b1")
    elec = Election("test-2026", "VIC", "assembly", date(2026, 11, 28), 10, "b1")
    polls = pl.DataFrame({
        "pollster": ["Resolve", "YouGov MRP"],
        # First poll spans 3 weeks; second is a huge 10,000-sample MRP
        "field_start": [date(2023, 1, 1), date(2023, 2, 1)],
        "field_end": [date(2023, 1, 22), date(2023, 2, 5)],
        "sample_size": [1500, 10000],
        "ALP": [38.0, 36.0],
        "COAL": [35.0, 37.0],
        "GRN": [12.0, 11.0],
        "tpp_alp_vs_coal": [53.5, None],
    })
    start = {"ALP": 37.0, "COAL": 35.0, "GRN": 11.0, "OTH": 17.0}
    data, _, _ = prepare(polls, prev, elec, start, ["ALP", "COAL", "GRN", "OTH"])
    assert data["poll_w_end"][0] > data["poll_w_start"][0]
    # MRP capped at MAX_N_EFF (2000) and uses MRP_DESIGN_EFFECT
    assert data["poll_n_eff"][1] == pytest.approx(2000.0)
    assert data["poll_n_eff"][0] == pytest.approx(1000.0)
    assert data["M_tpp"] == 1
    assert data["tpp_poll"] == [1]
    assert data["tpp_y"] == [53.5]
    assert len(data["tpp_flow_prior"]) == 2  # GRN, OTH
    init_list = inits(data, "poll_aggregator", chains=2, seed=2)
    assert len(init_list[0]["flow_alp"]) == 2
    assert init_list[0]["tau_tpp"] > 0


def test_g4_swing_prior_correlated_alr_and_opp_routing(tmp_path):
    from prophecy import jurisdictions
    from prophecy.model.pipeline import swing_prior

    e = jurisdictions.get("nt-2024")
    prev = jurisdictions.previous(e)
    out_dir, run_dir = tmp_path / "out", tmp_path / "run"
    swing_prior(e, prev, out_dir, run_dir, polls=None, n_draws=2000, seed=11, log=lambda _: None)
    draws = np.load(run_dir / "aggregate_draws.npz")["shares"][:, 0, :]
    # Exact simplex sum and strictly positive shares
    assert np.allclose(draws.sum(axis=1), 100.0, atol=1e-4)
    assert (draws > 0).all()
    # Shrunk ALR covariance prevents NT COAL SD from exploding to 13+ pts
    assert float(np.std(draws[:, 1])) < 10.0


def test_g5_hareclark_calibrated_sd_surplus_leakage_and_stochastic_exhaust():
    from prophecy.model.hareclark import hare_clark, hareclark_swing_sd

    sds = hareclark_swing_sd(date(2025, 7, 19))
    assert set(sds) == {"ALP", "COAL", "GRN", "OTH"}
    assert all(0.05 < v < 0.5 for v in sds.values())

    # Surplus leakage transfers a fraction of a dominant party's surplus to other units
    votes = np.array([[0.55, 0.25, 0.20]])  # 3 units, 5 seats (quota = 1/6 = 0.1667)
    unit_bloc = np.array([IDX["ALP"], IDX["COAL"], IDX["GRN"]])
    cap = np.array([5, 5, 5])
    flows = _uniform_flows()[None]
    ex = np.array([0.12])
    won_leak = hare_clark(votes, unit_bloc, cap, seats=5, flows=flows, exhaust=ex, surplus_leakage=0.15)
    assert won_leak.sum() == 5
    won_zero = hare_clark(votes, unit_bloc, cap, seats=5, flows=flows, exhaust=ex, surplus_leakage=0.0)
    assert won_zero.sum() == 5


def test_e6_notional_strict_zero_leakage_guard():
    from prophecy import jurisdictions
    from prophecy.model.states import notional_baseline

    # When booths.csv has no lat/lon coordinates and strict mode is enabled, must raise ValueError
    e = jurisdictions.get("nsw-2023")
    prev = jurisdictions.previous(e)
    with pytest.raises(ValueError, match="pre-election GIS"):
        notional_baseline(prev, e, log=lambda _: None, allow_post_election_venues=False)
