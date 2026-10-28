import numpy as np
import pytest

from prophecy.model.preferences import BLOCS, IDX, count, two_party


def flows(rows: dict[str, dict[str, float]]) -> np.ndarray:
    w = np.full((len(BLOCS), len(BLOCS)), 1.0)
    np.fill_diagonal(w, 0.0)
    for frm, to in rows.items():
        w[IDX[frm]] = [to.get(b, 0.0) for b in BLOCS]
    return w


def shares(**kw: float) -> np.ndarray:
    s = np.zeros(len(BLOCS))
    for k, v in kw.items():
        s[IDX[k]] = v
    return s / s.sum()


def test_greens_preferences_elect_labor():
    # ALP 40, COAL 45, GRN 15: Greens excluded, 80% to ALP -> ALP 52, COAL 48.
    w = flows({"GRN": {"ALP": 0.8, "COAL": 0.2}})
    winner, final = count(shares(ALP=40, COAL=45, GRN=15)[None, None], w[None])
    assert BLOCS[winner[0, 0]] == "ALP"
    assert final[0, 0, IDX["ALP"]] == pytest.approx(0.52)


def test_flows_only_go_to_remaining_candidates():
    # ONP excluded with GRN already gone: its GRN weight must be renormalised away.
    w = flows({
        "GRN": {"ALP": 1.0},
        "ONP": {"ALP": 0.1, "COAL": 0.3, "GRN": 0.6},
    })
    winner, final = count(shares(ALP=40, COAL=38, GRN=10, ONP=12)[None, None], w[None])
    # GRN out first (10): ALP 50, COAL 38, ONP 12 -> ONP out: 25% ALP, 75% COAL.
    assert final[0, 0, IDX["ALP"]] == pytest.approx(0.53)
    assert BLOCS[winner[0, 0]] == "ALP"


def test_others_bloc_is_excluded_first_even_when_large():
    # "Others" is several small candidates; it must not survive on its combined total.
    w = flows({"OTH": {"ALP": 0.5, "COAL": 0.5}})
    winner, final = count(shares(ALP=35, COAL=36, GRN=9, OTH=20)[None, None], w[None])
    assert final[0, 0, IDX["OTH"]] == 0.0
    assert BLOCS[winner[0, 0]] in ("ALP", "COAL")


def test_two_party_matches_count_for_three_candidates():
    w = flows({"GRN": {"ALP": 0.8, "COAL": 0.2}})
    primary = shares(ALP=40, COAL=45, GRN=15)[None]
    assert two_party(primary, w[None], "ALP", "COAL")[0] == pytest.approx(52.0)


def test_flows_reproduce_2022_statewide_tpp():
    """Calibrated flows + sequential count must recover the actual 2022 2PP (55.0)."""
    import polars as pl

    from prophecy import DATA_DIR
    from prophecy.model.preferences import calibrate_to_results, estimate_weights
    from prophecy.schema.parties import bloc

    src = DATA_DIR / "processed" / "vic-2022"
    if not (src / "dop_transfers.csv").exists():
        pytest.skip("VEC 2022 data not ingested")
    transfers = pl.read_csv(src / "dop_transfers.csv").filter(pl.col("count") > 0).with_columns(
        pl.col("from_party").map_elements(bloc, return_dtype=pl.String).alias("from_bloc"),
        pl.col("to_party").map_elements(bloc, return_dtype=pl.String).alias("to_bloc"),
    )
    primary = pl.read_csv(src / "primary.csv")
    tcp = pl.read_csv(src / "tcp.csv")
    names = sorted(primary["district"].unique().to_list())
    base = np.zeros((len(names), len(BLOCS)))
    for d, b, v in primary.group_by("district", "bloc").agg(pl.col("votes").sum()).iter_rows():
        base[names.index(d), IDX[b]] += v
    votes = base.sum(axis=1)
    base /= votes[:, None]
    alp = np.full(len(names), np.nan)
    for i, n in enumerate(names):
        t = tcp.filter(pl.col("district") == n)
        if set(t["bloc"]) == {"ALP", "COAL"}:
            alp[i] = t.filter(pl.col("bloc") == "ALP")["pct"][0]
    w, info = calibrate_to_results(estimate_weights(transfers), base, alp)
    assert abs(info["bias"]) < 0.5 and info["sd"] < 2.5
    state = (base * votes[:, None]).sum(axis=0) / votes.sum()
    assert two_party(state[None], w[None], "ALP", "COAL")[0] == pytest.approx(55.0, abs=1.0)
