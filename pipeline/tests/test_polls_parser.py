from datetime import date

from prophecy.ingest.polls import parse_date_range, parse_poll_page

# Trimmed copy of the Wikipedia table layout: merged IND+Others cell, a rowspan
# continuation row carrying an ALP-v-One Nation 2PP, and an event row.
PAGE = """
==Voting intention==
===Legislative Assembly===
====2026====
{| class="wikitable sortable"
|-
! rowspan="3" | Date
! rowspan="3" | Polling firm
! rowspan="3" | Client
! rowspan="3" | Sample<br/>size
! colspan="6" | Primary vote
! colspan="3" | 2PP vote
|-
! ALP !! L/NP !! GRN !! ONP !! IND !! Others !! ALP !! L/NP !! ONP
|-
! data-sort-type="number" style="background:{{Australian politics/party colours|Labor}};"|
! data-sort-type="number" style="background:{{Australian politics/party colours|Coalition}};"|
! data-sort-type="number" style="background:{{Australian politics/party colours|Greens}};"|
! data-sort-type="number" style="background:{{Australian politics/party colours|One Nation}};"|
! data-sort-type="number" style="background:{{Australian politics/party colours|Independent}};"|
! data-sort-type="number" style="background:lightgray;"|
! data-sort-type="number" style="background:{{Australian politics/party colours|Labor}};"|
! data-sort-type="number" style="background:{{Australian politics/party colours|Coalition}};"|
! data-sort-type="number" style="background:{{Australian politics/party colours|One Nation}};"|
|-
| rowspan="2" |2–8 Oct
| rowspan="2" align="left" |RedBridge/Accent<ref name="x">{{cite web|title=t}}</ref>
| rowspan="2" |''[https://example.org AFR]''
| rowspan="2" |1,008
| rowspan="2" |24%
| rowspan="2" style="background:#B6CDFB;" |'''30%'''
| rowspan="2" |16%
| rowspan="2" |24%
| colspan="2" rowspan="2" |6%
|44%
! style="background:#B6CDFB" |56%
|{{n/a}}
|-
! style="background:#FFB6B6" |55%
|{{n/a}}
|45%
|-style=background:#DADADA
| 28 July
| colspan="11" | Ben Carroll becomes premier
|-
| 6-10 Oct
| [[Resolve (poll)|Resolve]]
| The Age
|1,000
|25%
|'''28%'''
|15%
|23%
|4%
|5%| 5%
| {{n/a}}
| {{n/a}}
| {{n/a}}
|}
"""


def test_parse_poll_page():
    polls, events = parse_poll_page(PAGE, "VIC")
    assert len(polls) == 2
    rb, resolve = polls
    assert rb.pollster == "RedBridge/Accent"
    assert rb.sample_size == 1008
    assert (rb.ALP, rb.COAL, rb.GRN, rb.ONP) == (24, 30, 16, 24)
    assert rb.IND is None and rb.OTH == 6  # merged IND+Others cell
    assert rb.tpp_alp_vs_coal == 44
    assert rb.tpp_alp_vs_onp == 55  # from the rowspan continuation row
    assert (resolve.IND, resolve.OTH) == (4, 5)
    assert resolve.field_start == date(2026, 10, 6)
    assert len(events) == 1 and "Carroll" in events[0].description


def test_parse_date_range_variants():
    assert parse_date_range("15–22 Oct", 2026) == (date(2026, 10, 15), date(2026, 10, 22))
    assert parse_date_range("24 Nov – 8 Dec 2025", 2026) == (date(2025, 11, 24), date(2025, 12, 8))
    assert parse_date_range("Dec 2024 – Jan 2025", 2025) == (date(2024, 12, 1), date(2025, 1, 31))
    assert parse_date_range("Sep–Oct 2023", 2023) == (date(2023, 9, 1), date(2023, 10, 31))
    assert parse_date_range("1–14 Sept", 2026) == (date(2026, 9, 1), date(2026, 9, 14))
