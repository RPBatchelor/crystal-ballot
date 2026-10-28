from datetime import date

import polars as pl
import pytest

from prophecy.model.backtest import error_bias, error_sd, poll_error_table


def test_poll_error_table_uses_final_window_only():
    polls = pl.DataFrame({
        "pollster": ["A", "B", "C"],
        "field_end": [date(2018, 11, 20), date(2018, 11, 10), date(2018, 9, 1)],
        "ALP": [40.0, 42.0, 30.0],  # the September poll is outside the 28-day window
        "COAL": [38.0, 36.0, 50.0],
        "GRN": [12.0, 10.0, 10.0],
        "tpp_alp_vs_coal": [54.0, 56.0, 40.0],
    })
    results = pl.DataFrame({
        "year": [2018], "date": [date(2018, 11, 24)],
        "ALP": [42.9], "COAL": [35.2], "GRN": [10.7], "tpp_alp_vs_coal": [57.3],
    })
    t = poll_error_table(polls, results)
    row = t.row(0, named=True)
    assert row["n_polls"] == 2
    assert row["ALP_error"] == pytest.approx(41.0 - 42.9)
    assert row["tpp_error"] == pytest.approx(55.0 - 57.3)


def test_error_sd_respects_floor_and_bias_is_shrunk():
    table = pl.DataFrame({
        "ALP_error": [0.5, -0.5], "COAL_error": [3.0, -3.0], "GRN_error": [2.0, 2.0],
    })
    sd = error_sd(table, floor={"ALP": 2.0})
    assert sd["ALP"] == 2.0  # RMS 0.5 floored
    assert sd["COAL"] == pytest.approx(3.0)
    assert error_bias(table)["GRN"] == pytest.approx(1.0)  # half of mean +2
