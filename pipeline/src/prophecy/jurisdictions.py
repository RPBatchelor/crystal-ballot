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
    # Pinned page revision, for polls since removed from the current article.
    polls_wiki_oldid: int | None = None


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
        # New South Wales Legislative Assembly. The 2015 and 2019 poll tables were removed
        # from Wikipedia's election articles; they are read from late-2022 revisions.
        Election("nsw-2007", "NSW", "assembly", date(2007, 3, 24), 93, "nsw-2004"),
        Election("nsw-2011", "NSW", "assembly", date(2011, 3, 26), 93, "nsw-2004",
                 polls_wiki_title="2011 New South Wales state election"),
        Election("nsw-2015", "NSW", "assembly", date(2015, 3, 28), 93, "nsw-2013",
                 polls_wiki_title="2015 New South Wales state election",
                 polls_wiki_oldid=1130479877),
        Election("nsw-2019", "NSW", "assembly", date(2019, 3, 23), 93, "nsw-2013",
                 polls_wiki_title="2019 New South Wales state election",
                 polls_wiki_oldid=1130479641),
        Election("nsw-2023", "NSW", "assembly", date(2023, 3, 25), 93, "nsw-2021",
                 polls_wiki_title="2023 New South Wales state election"),
        Election(
            "nsw-2027", "NSW", "assembly", date(2027, 3, 27), 93, "nsw-2021",
            polls_wiki_title="Opinion polling for the 2027 New South Wales state election",
        ),
        # Queensland Legislative Assembly (optional preferential voting until 2015, full
        # preferential since 2017; 89 seats until the 2017 redistribution, 93 since).
        Election("qld-2009", "QLD", "assembly", date(2009, 3, 21), 89, "qld-2008"),
        *[
            Election(f"qld-{d.year}", "QLD", "assembly", d, seats, boundary,
                     polls_wiki_title=f"{d.year} Queensland state election")
            for d, seats, boundary in [
                (date(2012, 3, 24), 89, "qld-2008"),
                (date(2015, 1, 31), 89, "qld-2008"),
                (date(2017, 11, 25), 93, "qld-2017"),
                (date(2020, 10, 31), 93, "qld-2017"),
                (date(2024, 10, 26), 93, "qld-2017"),
            ]
        ],
        Election(
            "qld-2028", "QLD", "assembly", date(2028, 10, 28), 93, "qld-2017",
            polls_wiki_title="Opinion polling for the 2028 Queensland state election",
        ),
        # South Australian House of Assembly (47 seats; full preferential). Boundaries are
        # redrawn before every election, so each has its own boundary set.
        *[
            Election(f"sa-{d.year}", "SA", "assembly", d, 47, boundary,
                     polls_wiki_title=f"{d.year} South Australian state election")
            for d, boundary in [
                (date(2010, 3, 20), "sa-2007"),
                (date(2014, 3, 15), "sa-2012"),
                (date(2018, 3, 17), "sa-2016"),
                (date(2022, 3, 19), "sa-2020"),
            ]
        ],
        Election("sa-2026", "SA", "assembly", date(2026, 3, 21), 47, "sa-2024",
                 polls_wiki_title="Opinion polling for the 2026 South Australian state election"),
        # Next election: fixed for the third Saturday in March 2030; boundaries not yet redrawn.
        Election("sa-2030", "SA", "assembly", date(2030, 3, 16), 47, "sa-2024"),
        # Western Australian Legislative Assembly (59 seats since 2008; full preferential).
        # Boundaries are redrawn after every election, named by redistribution year.
        Election("wa-2005", "WA", "assembly", date(2005, 2, 26), 57, "wa-2003"),
        *[
            Election(f"wa-{d.year}", "WA", "assembly", d, 59, boundary,
                     polls_wiki_title=f"{d.year} Western Australian state election")
            for d, boundary in [
                (date(2008, 9, 6), "wa-2007"),
                (date(2013, 3, 9), "wa-2011"),
                (date(2017, 3, 11), "wa-2015"),
                (date(2021, 3, 13), "wa-2019"),
                (date(2025, 3, 8), "wa-2023"),
            ]
        ],
        # Next election: fixed for the second Saturday in March 2029.
        Election("wa-2029", "WA", "assembly", date(2029, 3, 10), 59, "wa-2023"),
        # Tasmanian House of Assembly: Hare-Clark, five multi-member divisions on the federal
        # boundaries (Denison renamed Clark in 2017); 25 members until 2021, 35 since 2024.
        Election("tas-2010", "TAS", "assembly", date(2010, 3, 20), 25, "tas-2009"),
        *[
            Election(f"tas-{d.year}", "TAS", "assembly", d, seats, boundary,
                     polls_wiki_title=f"{d.year} Tasmanian state election")
            for d, seats, boundary in [
                (date(2014, 3, 15), 25, "tas-2009"),
                (date(2018, 3, 3), 25, "tas-2017"),
                (date(2021, 5, 1), 25, "tas-2017"),
                (date(2024, 3, 23), 35, "tas-2017"),
            ]
        ],
        Election("tas-2025", "TAS", "assembly", date(2025, 7, 19), 35, "tas-2017",
                 polls_wiki_title="Opinion polling for the 2025 Tasmanian state election"),
        # ACT Legislative Assembly: Hare-Clark, 17 members in three electorates to 2012, 25
        # in five electorates (Brindabella, Ginninderra, Kurrajong, Murrumbidgee, Yerrabi)
        # since 2016. Fixed four-year terms, polling in October.
        Election("act-2012", "ACT", "assembly", date(2012, 10, 20), 17, "act-2012",
                 polls_wiki_title="2012 Australian Capital Territory election"),
        *[
            Election(f"act-{d.year}", "ACT", "assembly", d, 25, boundary,
                     polls_wiki_title=f"{d.year} Australian Capital Territory election")
            for d, boundary in [
                (date(2016, 10, 15), "act-2015"),
                (date(2020, 10, 17), "act-2019"),
                (date(2024, 10, 19), "act-2023"),
            ]
        ],
        Election("act-2028", "ACT", "assembly", date(2028, 10, 21), 25, "act-2023"),
        # Northern Territory Legislative Assembly: 25 single-member divisions, full
        # preferential; the Country Liberal Party is the Coalition. Fixed four-year terms.
        Election("nt-2012", "NT", "assembly", date(2012, 8, 25), 25, "nt-2011"),
        Election("nt-2016", "NT", "assembly", date(2016, 8, 27), 25, "nt-2015",
                 polls_wiki_title="2016 Northern Territory general election"),
        Election("nt-2020", "NT", "assembly", date(2020, 8, 22), 25, "nt-2019",
                 polls_wiki_title="Opinion polling for the 2020 Northern Territory general election"),
        Election("nt-2024", "NT", "assembly", date(2024, 8, 24), 25, "nt-2023",
                 polls_wiki_title="2024 Northern Territory general election"),
        Election("nt-2028", "NT", "assembly", date(2028, 8, 26), 25, "nt-2023"),
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
