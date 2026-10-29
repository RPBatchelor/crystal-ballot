"""Registry of jurisdictions and elections the platform knows about."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Election:
    election_id: str  # e.g. "vic-2026"
    jurisdiction: str  # e.g. "VIC"
    chamber: str  # "assembly" | "council" | "house" | "senate"
    date: date
    seats: int
    boundary_set: str  # boundaries in force, e.g. "vic-2021" (redivision year)
    polls_wiki_title: str | None = None


ELECTIONS: dict[str, Election] = {
    e.election_id: e
    for e in [
        Election("vic-2002", "VIC", "assembly", date(2002, 11, 30), 88, "vic-2001"),
        Election("vic-2006", "VIC", "assembly", date(2006, 11, 25), 88, "vic-2001",
                 polls_wiki_title="2006 Victorian state election"),
        Election("vic-2010", "VIC", "assembly", date(2010, 11, 27), 88, "vic-2001",
                 polls_wiki_title="2010 Victorian state election"),
        Election("vic-2014", "VIC", "assembly", date(2014, 11, 29), 88, "vic-2013",
                 polls_wiki_title="2014 Victorian state election"),
        Election("vic-2018", "VIC", "assembly", date(2018, 11, 24), 88, "vic-2013",
                 polls_wiki_title="2018 Victorian state election"),
        Election("vic-2022", "VIC", "assembly", date(2022, 11, 26), 88, "vic-2021",
                 polls_wiki_title="2022 Victorian state election"),
        Election(
            "vic-2026", "VIC", "assembly", date(2026, 11, 28), 88, "vic-2021",
            polls_wiki_title="Opinion polling for the 2026 Victorian state election",
        ),
        # Federal House of Representatives. Earlier cycles' poll pages are Wikipedia's
        # "Opinion polling for the <year> Australian federal election".
        Election("fed-2007", "FED", "house", date(2007, 11, 24), 150, "fed-2006"),
        # Next federal election: due by mid-2028; date is a placeholder until it is called.
        Election("fed-next", "FED", "house", date(2028, 5, 20), 150, "fed-2024",
                 polls_wiki_title="Opinion polling for the next Australian federal election"),
        *[
            Election(f"fed-{d.year}", "FED", "house", d, seats, boundary,
                     polls_wiki_title=f"Opinion polling for the {d.year} Australian federal election")
            for d, seats, boundary in [
                (date(2010, 8, 21), 150, "fed-2009"),
                (date(2013, 9, 7), 150, "fed-2010"),
                (date(2016, 7, 2), 150, "fed-2015"),
                (date(2019, 5, 18), 151, "fed-2018"),
                (date(2022, 5, 21), 151, "fed-2021"),
                (date(2025, 5, 3), 150, "fed-2024"),
            ]
        ],
    ]
}


def in_jurisdiction(jurisdiction: str) -> list[Election]:
    """Elections for a jurisdiction, oldest first."""
    return sorted((e for e in ELECTIONS.values() if e.jurisdiction == jurisdiction),
                  key=lambda e: e.date)


def previous(election: Election) -> Election | None:
    earlier = [e for e in in_jurisdiction(election.jurisdiction) if e.date < election.date]
    return earlier[-1] if earlier else None


def get(election_id: str) -> Election:
    try:
        return ELECTIONS[election_id]
    except KeyError:
        raise KeyError(f"Unknown election {election_id!r}; known: {sorted(ELECTIONS)}") from None


def site_code(jurisdiction: str) -> str:
    """URL/data-folder code on the website (e.g. FED -> federal, VIC -> vic)."""
    return {"FED": "federal"}.get(jurisdiction, jurisdiction.lower())
