"""Estimated seat-swing terms, pooled polling error, first-time independents, scoring."""

import numpy as np
from scipy.special import logit

from prophecy.model.backtest import crps, pendulum_accuracy
from prophecy.model.new_candidates import draw
from prophecy.model.simulate import SimConfig, statewide_shares
from prophecy.model.swing_fit import _key, _shift


def test_name_keys_agree_across_commission_formats():
    assert _key("FOLEY, Martin") == _key("FOLEY Martin") == "FOLEY M"
    assert _key("O'HANLON Cressida") == "OHANLON C"
    assert _key("WERNER-GIBBINGS Taimus") == "WERNERGIBBINGS T"
    assert _key(None) is None


def test_shift_recentres_to_target():
    rng = np.random.default_rng(0)
    l0 = logit(rng.uniform(0.2, 0.6, 50))
    w = np.full(50, 1 / 50)
    c = _shift(l0, w, 0.45)
    assert abs((1 / (1 + np.exp(-(l0 + c)))) @ w - 0.45) < 1e-9


def test_crps_matches_closed_form_for_normal():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, 200_000)
    # CRPS of N(0,1) at y = 0 is (sqrt(2) - 1) / sqrt(pi).
    assert abs(crps(x, 0.0) - (np.sqrt(2) - 1) / np.sqrt(np.pi)) < 0.005
    assert crps(np.full(10, 3.0), 3.0) == 0.0


def test_pendulum_baseline():
    base = {"A": 52.0, "B": 49.0, "C": 60.0}
    actual = {"A": "LIB", "B": "ALP", "C": "IND"}
    inc = {"A": "ALP", "B": "LIB", "C": "IND"}
    # A 3-point swing to Labor: A stays Labor (wrong), B goes Labor (right), C stays IND.
    assert pendulum_accuracy(base, 3.0, actual, inc) == round(2 / 3, 4)


def test_new_independents_draw_only_where_standing():
    pool = np.array([0.01, 0.02, 0.3])
    out = draw(np.array([0, 1, 2]), pool, 5000, np.random.default_rng(2))
    assert out.shape == (5000, 3)
    assert (out[:, 0] == 0).all()
    assert out[:, 2].mean() > out[:, 1].mean() > 0
    assert out.max() <= 0.6


def test_correlated_polling_error():
    cfg = SimConfig(n_per_draw=1, poll_error_df=200.0)
    cfg.poll_error_sd = {"ALP": 2.0, "COAL": 2.0, "GRN": 1.0}
    cfg.poll_error_corr = [[1, -0.8, 0], [-0.8, 1, 0], [0, 0, 1]]
    cfg.poll_error_corr_parties = ["ALP", "COAL", "GRN"]
    agg = np.tile([35.0, 35.0, 10.0, 20.0], (20_000, 1))
    out = statewide_shares(agg, ["ALP", "COAL", "GRN", "OTH"], cfg, np.random.default_rng(3))
    from prophecy.model.preferences import IDX

    r = np.corrcoef(out[:, IDX["ALP"]], out[:, IDX["COAL"]])[0, 1]
    assert r < -0.6


def test_party_blocs_for_labels_that_were_misread_during_development():
    from prophecy.schema.parties import bloc, party_code

    cases = {
        "Country Liberal Party": "COAL",
        "Liberal National Party of Queensland": "COAL",
        "The Nationals": "COAL",
        "Pauline Hanson's One Nation": "ONP",
        "The Greens (WA)": "GRN",
        "Australian Labor Party (ALP)": "ALP",
        "Independent": "IND",
        "Jacqui Lambie Network": "OTH",
        "Liberal Democrats": "OTH",  # not the Liberal Party
        "Liberals For Climate": "OTH",
    }
    for name, expected in cases.items():
        assert bloc(party_code(name)) == expected, name
