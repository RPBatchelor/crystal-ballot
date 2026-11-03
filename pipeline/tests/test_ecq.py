"""ECQ XML results feed parser, on a trimmed copy of the 2024 layout."""

import xml.etree.ElementTree as ET

from prophecy.ingest.ecq import _legacy_candidate, parse_district


def cand(name, n, party=None, code=None):
    attrs = f'ballotName="{name}" ballotOrderNumber="{n}"'
    if party:
        attrs += f' party="{party}" partyCode="{code}"'
    return attrs


DISTRICT = f"""<district districtName="Algester" enrolment="40236">
  <declaredCandidate {cand("ENOCH, Leeanne", 4)}/>
  <candidates count="3">
    <candidate {cand("BOSLEY, Rhys", 1, "Independent", "IND")}/>
    <candidate {cand("PRASAD, Jitendra", 3, "Liberal National Party of Queensland", "LNP")}/>
    <candidate {cand("ENOCH, Leeanne", 4, "Australian Labor Party (State of Queensland)", "ALP")}/>
  </candidates>
  <countRound countName="Unofficial Preliminary Count"/>
  <countRound countName="Official First Preference Count">
    <totalInformalVotes><count>1600</count></totalInformalVotes>
    <primaryVoteResults>
      <candidate {cand("BOSLEY, Rhys", 1)}><count>1500</count></candidate>
      <candidate {cand("PRASAD, Jitendra", 3)}><count>12000</count></candidate>
      <candidate {cand("ENOCH, Leeanne", 4)}><count>16500</count></candidate>
    </primaryVoteResults>
    <booths count="1">
      <booth name="Algester" typeDescription="Polling Booth">
        <primaryVoteResults>
          <candidate {cand("BOSLEY, Rhys", 1)}><count>100</count></candidate>
          <candidate {cand("PRASAD, Jitendra", 3)}><count>800</count></candidate>
          <candidate {cand("ENOCH, Leeanne", 4)}><count>1100</count></candidate>
        </primaryVoteResults>
      </booth>
    </booths>
  </countRound>
  <countRound countName="Official Distribution of Preferences Count">
    <twoCandidateVotes>
      <candidate {cand("PRASAD, Jitendra", 3)}><count>12900</count></candidate>
      <candidate {cand("ENOCH, Leeanne", 4)}><count>17100</count></candidate>
    </twoCandidateVotes>
    <preferenceDistributionSummary>
      <preferenceDistribution distribution="1" excludedBallotName="BOSLEY, Rhys" excludedBallotOrder="1">
        <candidatePreferences {cand("PRASAD, Jitendra", 3)}><count>900</count></candidatePreferences>
        <candidatePreferences {cand("ENOCH, Leeanne", 4)}><count>600</count></candidatePreferences>
        <exhausted><count>0</count></exhausted>
      </preferenceDistribution>
    </preferenceDistributionSummary>
  </countRound>
</district>"""


def test_parse_district():
    out = parse_district(ET.fromstring(DISTRICT))
    d = out["districts"][0]
    assert (d["elected"], d["elected_party"], d["formal"], d["informal"]) == ("ENOCH Leeanne", "ALP", 30000, 1600)
    assert {r["candidate"]: (r["party"], r["votes"]) for r in out["primary"]} == {
        "BOSLEY Rhys": ("IND", 1500), "PRASAD Jitendra": ("LNP", 12000), "ENOCH Leeanne": ("ALP", 16500)}
    assert sum(r["votes"] for r in out["booths"]) == 2000
    assert {r["candidate"]: r["pct"] for r in out["tcp"]} == {"PRASAD Jitendra": 43.0, "ENOCH Leeanne": 57.0}
    # The first count is the first preferences; zero exhausted ballots are not recorded.
    assert [(t["count"], t["from_party"], t["to_party"], t["votes"]) for t in out["dop_transfers"]] == [
        (2, "IND", "LNP", 900.0), (2, "IND", "ALP", 600.0)]


def test_legacy_candidate_headers():
    assert _legacy_candidate("BOOTHMAN, Mark LNP") == ("BOOTHMAN Mark", "LNP")
    # Independents carry no abbreviation, even when the given name is initials.
    assert _legacy_candidate("BOLTON, Sandy") == ("BOLTON Sandy", "IND")
    assert _legacy_candidate("DAVISON, BJ") == ("DAVISON BJ", "IND")
