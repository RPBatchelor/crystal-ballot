"""A blind backtest may only use what was public before polling day.

Each check names an input a backtest draws from history and asserts that, for every
election we backtest, it comes only from elections held before that one.
"""

import pytest

from prophecy import jurisdictions
from prophecy.model import swing_fit
from prophecy.model.hareclark import tas_flows
from prophecy.model.pipeline import PROCESSED, flow_source

# Every election with a processed result whose predecessor is also processed: the set
# `prophecy backtest` can be run on.
BACKTESTABLE = [
    e for e in jurisdictions.ELECTIONS.values()
    if (p := jurisdictions.previous(e)) is not None
    and (PROCESSED / e.election_id / "primary.csv").exists()
    and (PROCESSED / p.election_id / "primary.csv").exists()
]


def test_there_are_backtestable_elections():
    assert len(BACKTESTABLE) >= 20


@pytest.mark.parametrize("e", BACKTESTABLE, ids=lambda e: e.election_id)
def test_preference_source_precedes_election(e):
    src = flow_source(e)
    assert src is None or src.date < e.date


def test_victorian_flow_sources():
    # The VEC published full distributions first for 2022: earlier elections must fall
    # back to the federal divisions, never borrow 2022's.
    assert flow_source(jurisdictions.get("vic-2018")) is None
    assert flow_source(jurisdictions.get("vic-2022")) is None
    assert flow_source(jurisdictions.get("vic-2026")).election_id == "vic-2022"


@pytest.mark.parametrize("eid", ["vic-2018", "vic-2022", "tas-2024", "act-2024", "nt-2024"])
def test_federal_flows_precede_election(eid):
    e = jurisdictions.get(eid)
    logged = []
    tas_flows(e, log=logged.append)
    used = [jurisdictions.get(x) for x in logged[0].split("[")[1].split("]")[0].replace("'", "").split(", ")]
    assert used and all(f.date < e.date for f in used)


@pytest.mark.parametrize("eid", ["vic-2018", "nsw-2023", "qld-2024", "sa-2026", "fed-2025"])
def test_swing_pairs_precede_election(eid):
    e = jurisdictions.get(eid)
    assert all(later.date < e.date for later, _ in swing_fit.pairs(e.date))
