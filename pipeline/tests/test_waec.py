"""WAEC results API parser, on a trimmed copy of Warren-Blackwood 2013 (two candidates
named Redman, one of them unaligned and listed by surname only)."""

from prophecy.ingest.waec import parse_district


def dist(level, kind, name, votes):
    return {"PREFERENCE_LEVEL": level, "DISTRIBUTION_LEVEL": f"{kind} {level}" if level else kind,
            "BALLOT_PAPER_NAME": name, "FORMAL_LAST_PUBLISHED_NUMBER_ENTERED": votes}


RESULTS = {
    "currentElectorate": {"ElectorateName": "Warren-Blackwood"},
    "toptotals": {"NUMBER_ELECTORS": 25730, "INFORMAL_LAST_PUBLISHED_NUMBER_ENTERED": 1322},
    "resultsCandidates": [
        {"BALLOT_PAPER_NAME": "COLYER", "PARTY_AFFILIATION": "LIB", "Votes_Counted": 6699},
        {"BALLOT_PAPER_NAME": "REDMAN", "PARTY_AFFILIATION": "NAT", "Votes_Counted": 7439},
        {"BALLOT_PAPER_NAME": "REDMAN", "PARTY_AFFILIATION": "", "Votes_Counted": 273},
    ],
    "results2CP": [
        {"Ballot_Paper_Name": "COLYER - LIB", "Votes_Counted": 6800},
        {"Ballot_Paper_Name": "REDMAN - NAT", "Votes_Counted": 7611},
    ],
    "resultsFullDistribution": [
        dist(1, "Distribution", "COLYER - LIB", 101),
        dist(1, "Distribution", "REDMAN - NAT", 172),
        dist(1, "Distribution", "REDMAN", -273),
    ],
    "resultsPollingPlace": [
        {"BREAKDOWN_NAME": "Bridgetown", "BREAKDOWN_GROUP": "Polling Places",
         "COLYER - LIB": "300", "REDMAN - NAT": "400", "REDMAN": "20", "Informal": "9", "Total Votes": "729"},
        {"BREAKDOWN_NAME": "Postal Votes", "BREAKDOWN_GROUP": "Count Centre",
         "COLYER - LIB": "6399", "REDMAN - NAT": "7039", "REDMAN": "253", "Informal": "1313", "Total Votes": "15004"},
    ],
}
CANDIDATES = [
    {"BALLOT_PAPER_NAME": "COLYER, Ray", "PARTY_AFFILIATION": "Liberal Party"},
    {"BALLOT_PAPER_NAME": "REDMAN, K.", "PARTY_AFFILIATION": "(No Party Designation)"},
    {"BALLOT_PAPER_NAME": "REDMAN, Terry", "PARTY_AFFILIATION": "THE NATIONALS"},
]


def test_same_surname_told_apart_by_affiliation():
    out = parse_district(RESULTS, CANDIDATES)
    primary = {r["candidate"]: (r["party"], r["votes"]) for r in out["primary"]}
    assert primary == {"COLYER Ray": ("LIB", 6699), "REDMAN Terry": ("NAT", 7439),
                       "REDMAN K.": ("IND", 273)}
    assert out["districts"][0]["elected"] == "REDMAN Terry"
    assert out["districts"][0]["elected_party"] == "NAT"


def test_distribution_and_polling_places():
    out = parse_district(RESULTS, CANDIDATES)
    moves = {(r["from_candidate"], r["to_candidate"]): r["votes"] for r in out["dop_transfers"]}
    assert moves == {("REDMAN K.", "COLYER Ray"): 101, ("REDMAN K.", "REDMAN Terry"): 172}
    assert all(r["count"] == 2 for r in out["dop_transfers"])
    sections = {(r["venue"], r["section"]) for r in out["booths"]}
    assert sections == {("Bridgetown", "Polling Places"), ("Postal Votes", "Declaration")}
    assert sum(r["votes"] for r in out["booths"]) == 6699 + 7439 + 273
