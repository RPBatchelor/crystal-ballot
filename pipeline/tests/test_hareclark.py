"""Hare-Clark count at party/independent level, and the TEC results fragment parser."""

import numpy as np

from prophecy.ingest.tec import parse_count
from prophecy.model.hareclark import hare_clark
from prophecy.model.preferences import BLOCS, IDX


def flat_flows(n: int = 1) -> np.ndarray:
    w = np.full((n, len(BLOCS), len(BLOCS)), 1.0)
    w[:, np.arange(len(BLOCS)), np.arange(len(BLOCS))] = 0.0
    return w / w.sum(axis=2, keepdims=True)


def test_full_quotas_then_remainders():
    # Quota 1/6: Liberal 3 quotas, Labor 1 quota and a remainder, Greens 1.2 quotas.
    v = np.array([[0.50, 0.30, 0.20]])
    blocs = np.array([IDX["COAL"], IDX["ALP"], IDX["GRN"]])
    won = hare_clark(v, blocs, np.array([5, 5, 5]), 5, flat_flows())
    assert won.tolist() == [[3, 1, 1]]


def test_independent_wins_one_seat_and_passes_on_surplus():
    # An independent with two quotas can only take one seat; the surplus elects Labor.
    v = np.array([[0.40, 0.30, 0.30]])
    blocs = np.array([IDX["IND"], IDX["ALP"], IDX["COAL"]])
    won = hare_clark(v, blocs, np.array([1, 3, 3]), 3, flat_flows())
    assert won[0, 0] == 1 and won.sum() == 3


def test_exclusion_transfers_decide_last_seat():
    # Last seat between Labor's remainder and an independent: the Greens' preferences
    # (all to Labor) put Labor ahead.
    v = np.array([[0.30, 0.38, 0.17, 0.15]])  # ALP, COAL, IND, GRN; 2 seats, quota 1/3
    blocs = np.array([IDX["ALP"], IDX["COAL"], IDX["IND"], IDX["GRN"]])
    flows = flat_flows()
    flows[0, IDX["GRN"]] = 0.0
    flows[0, IDX["GRN"], IDX["ALP"]] = 1.0
    won = hare_clark(v, blocs, np.array([2, 2, 1, 2]), 2, flows, exhaust=0.0)
    assert won.tolist() == [[1, 1, 0, 0]]


FRAGMENT = """
<p>Quota:&nbsp; 8,432</p>
<h3>Liberal Party</h3>
<table><tr><td>&nbsp;</td><td>ARCHER, Bridget</td><td>8,432</td><td><strong>Elected 1</strong></td></tr>
<tr><td>&bull;</td><td>FERGUSON, Michael</td><td>8,432</td><td><strong>Elected 3</strong></td></tr>
<tr><td>&nbsp;</td><td>WOOD, Simon</td><td>0</td><td>Excluded</td></tr></table>
<h3>Group E</h3>
<table><tr><td>&nbsp;</td><td>RAZAY, George</td><td>6,968</td><td><strong>Elected 6</strong></td></tr></table>
<h3>Ungrouped</h3>
<table><tr><td>&bull;</td><td>McLENNAN, Charlene</td><td>0</td><td>Excluded</td></tr></table>
"""


def test_parse_count():
    rows = parse_count(FRAGMENT)
    assert [(r["group"], r["name"], r["votes"], r["elected_order"], r["sitting"]) for r in rows] == [
        ("Liberal Party", "ARCHER Bridget", 8432, 1, False),
        ("Liberal Party", "FERGUSON Michael", 8432, 3, True),
        ("Liberal Party", "WOOD Simon", 0, None, False),
        ("Group E", "RAZAY George", 6968, 6, False),
        ("Ungrouped", "McLENNAN Charlene", 0, None, True),
    ]
