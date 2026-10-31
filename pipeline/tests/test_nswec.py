"""NSWEC page parsers, on trimmed copies of the 2023 page layouts."""

from prophecy.ingest.nswec import parse_dop, parse_fp, parse_tcp_fragment, parse_tcp_venues

FP = """<h3>State Electoral District of Campbelltown</h3>
<table><tr><th>Candidate</th><th>Representation</th><th>Formal Votes</th><th>% Total Formal Votes</th></tr>
<tr><td>SICARI Rosa (Rosetta)</td><td>Liberal Democratic Party</td><td>2,339</td><td>4.9%</td></tr>
<tr><td>WARREN Greg</td><td>Australian Labor Party (NSW Branch)</td><td>25,629</td><td>53.7%</td></tr>
<tr><td>PAUDEL Gypshouna</td><td>The Liberal Party of Australia, New South Wales Division</td><td>8,104</td><td>17.0%</td></tr>
<tr><td>TOTAL FORMAL VOTES</td><td></td><td>36,072</td><td>100.00%</td></tr></table>
<table><tr><th>Venue and Vote Types</th><th>SICARI (LDP)</th><th>WARREN (ALP)</th><th>PAUDEL (LIB)</th>
<th>Total Formal</th><th>Informal</th><th>Total Votes/ Ballot Papers</th><th>Count Status</th></tr>
<tr><td>Voting Centres</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>Ambarvale Public</td><td>20</td><td>500</td><td>180</td><td>700</td><td>30</td><td>730</td><td>Complete</td></tr>
<tr><td>Total Voting Centre Ordinary Votes</td><td>20</td><td>500</td><td>180</td><td>700</td><td>30</td><td>730</td><td></td></tr>
<tr><td>Declaration Votes</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>Postal</td><td>40</td><td>300</td><td>200</td><td>540</td><td>5</td><td>545</td><td></td></tr>
<tr><td>Total Votes / Ballot Papers</td><td>2,339</td><td>25,629</td><td>8,104</td><td>36,072</td><td>2,358</td><td>38,430</td><td></td></tr>
<tr><td>% of Formal Votes / Ballot Papers</td><td>6%</td><td>71%</td><td>23%</td><td>100%</td><td></td><td></td><td></td></tr>
</table>"""

DOP = """<table>
<tr><th>Counts</th><th>Count 1</th><th colspan="2">Count 2</th><th>% of Vote</th></tr>
<tr><td></td><td></td><td>SICARI Rosa (Rosetta) (LDP)Excluded Candidate</td><td></td></tr>
<tr><td>Candidates</td><td>FirstPreferenceVotes</td><td>VotesDistributed</td><td>ProgressiveTotals</td></tr>
<tr><td>SICARI Rosa (Rosetta)LDP</td><td>2,339</td><td>EXCLUDED</td></tr>
<tr><td>WARREN GregALP</td><td>ELECTED25,629</td><td>400</td><td>ELECTED26,029</td><td>74.2%</td></tr>
<tr><td>PAUDEL GypshounaLIB</td><td>8,104</td><td>950</td><td>9,054</td><td>25.8%</td></tr>
<tr><td>Total Votes in Count</td><td>36,072</td><td>1,350</td><td>35,083</td></tr>
<tr><td>Exhausted Votes</td><td>0</td><td>989</td><td>989</td></tr>
</table>"""


def test_parse_fp_candidates_venues_and_totals():
    cands, booths, totals = parse_fp(FP)
    assert [c["candidate"] for c in cands] == ["SICARI Rosa (Rosetta)", "WARREN Greg", "PAUDEL Gypshouna"]
    assert totals == {"formal": 36072, "informal": 2358}
    postal = {b["candidate"]: b["votes"] for b in booths if b["venue"] == "Postal"}
    assert postal == {"SICARI Rosa (Rosetta)": 40, "WARREN Greg": 300, "PAUDEL Gypshouna": 200, "": 5}
    assert {b["section"] for b in booths} == {"Voting Centres", "Declaration Votes"}
    assert {b["venue"] for b in booths} == {"Ambarvale Public", "Postal"}  # no subtotals


def test_parse_dop_handles_bracketed_names_and_exhaustion():
    cands, _, _ = parse_fp(FP)
    transfers, final, elected = parse_dop(DOP, cands)
    assert elected == "WARREN Greg"
    assert final == {"WARREN Greg": 26029, "PAUDEL Gypshouna": 9054}
    moved = {t["to_candidate"]: t["votes"] for t in transfers}
    assert moved == {"WARREN Greg": 400, "PAUDEL Gypshouna": 950, "Exhausted": 989}
    assert all(t["from_candidate"] == "SICARI Rosa (Rosetta)" for t in transfers)


def test_parse_tcp_fragment_and_venues():
    frag = parse_tcp_fragment("""<!--
        $notionalA=ROWLAND Marcus
        $notionalB=CLANCY Justin
        $formalA=14626
        $formalB=28811
        $exhausted=6351
    -->""")
    assert frag == {"a": "ROWLAND Marcus", "b": "CLANCY Justin", "a_votes": 14626,
                    "b_votes": 28811, "exhausted": 6351}
    venues = parse_tcp_venues("""<table>
        <tr><th>Venues and Vote Types</th><th>CLANCY (LIB)</th><th>MUIRHEAD (CLP)</th><th>Exhausted</th><th>Formal</th></tr>
        <tr><td>Voting Centres</td></tr>
        <tr><td>Albury High</td><td>585</td><td>393</td><td>121</td><td>1,099</td></tr>
        <tr><td>Total Votes</td><td>28,258</td><td>14,572</td><td>4,802</td><td>47,632</td></tr></table>""")
    assert venues == [{"section": "Voting Centres", "venue": "Albury High", "a": 585, "b": 393, "exhausted": 121}]
