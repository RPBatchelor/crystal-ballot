import polars as pl

from prophecy.ingest.vec_nominations import _keep_curated, district_slug, parse_nominations
from prophecy.model import new_candidates

PAGE = """
<tbody>
        <tr class="candidate-row">
            <td>
                PANOPOULOS, Angelica
                    <p>The Greens</p>
                            </td>
            <td><span>Jess Wheelock</span></td>
        </tr>
        <tr class="candidate-row">
            <td>
                O&#39;NEILL, Daniel
                            </td>
            <td></td>
        </tr>
</tbody>
"""


def test_parse_nominations_reads_names_and_parties():
    assert parse_nominations(PAGE) == [("PANOPOULOS, Angelica", "The Greens"),
                                       ("O'NEILL, Daniel", "Independent")]


def test_district_slug():
    assert district_slug("South-West Coast") == "south-west-coast"
    assert district_slug("Narre Warren North") == "narre-warren-north"


def test_reingest_keeps_curated_columns(tmp_path):
    path = tmp_path / "c.csv"
    pl.DataFrame({"district": ["A", "A"], "name": ["X, a", "Y, b"], "party": ["IND", "ALP"],
                  "ballot_position": [None, None], "prior_share": [12.5, None],
                  "note": ["teal", None]}).write_csv(path)
    new = pl.DataFrame({"district": ["A", "A"], "name": ["X, a", "Z, c"], "party": ["IND", "IND"],
                        "ballot_position": [2, 1], "note": [None, None]},
                       schema_overrides={"ballot_position": pl.Int64, "note": pl.String})
    out = _keep_curated(new, path)
    assert out.columns == ["district", "name", "party", "ballot_position", "prior_share", "note"]
    assert out.row(0, named=True)["prior_share"] == 12.5 and out.row(0, named=True)["note"] == "teal"
    assert out.row(1, named=True)["prior_share"] is None


def test_count_new_on_ballot_skips_candidates_who_stood_before(tmp_path, monkeypatch):
    (tmp_path / "prev").mkdir()
    pl.DataFrame({"district": ["A"], "candidate": ["DRAGWIDGE, Georgie"]}).write_csv(
        tmp_path / "prev" / "primary.csv")
    monkeypatch.setattr(new_candidates, "PROCESSED", tmp_path)

    class Prev:
        election_id = "prev"

    ballot = pl.DataFrame({"district": ["A", "A", "A", "B"],
                           "name": ["DRAGWIDGE, Georgie", "KING, Adrian", "TAYLOR, Nina", "NEW, Person"],
                           "party": ["IND", "IND", "ALP", "IND"]})
    assert new_candidates.count_new_on_ballot(ballot, Prev(), ["A", "B", "C"]).tolist() == [1, 1, 0]
