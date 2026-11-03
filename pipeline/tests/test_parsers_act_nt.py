"""ACT name handling and the NT Wikipedia election-box parser."""

from prophecy.ingest.elections_act import _is_elected, _name
from prophecy.ingest.wiki_nt import divisions

BOX = """
=== [[Electoral division of Araluen|Araluen]] ===
{{Election box begin | title=2024 Northern Territory general election: Araluen}}
{{Election box candidate AU party
 |party = CLP
 |candidate = [[Marie-Clare Boothby]]
 |votes = 2,031
 |percentage = 46.2
 |change = +10.1
}}
{{Election box candidate AU party
 |party = Independent
 |candidate = [[Robyn Lambley]]
 |votes = 1,512
 |percentage = 34.4
 |change = -5.0
}}
{{Election box candidate AU party
 |party = Labor NT
 |candidate = Ana Piza
 |votes = 851
 |percentage = 19.4
 |change = -1.2
}}
{{Election box formal| votes = 4,394 }}
{{Election box informal| votes = 120 }}
{{Election box 2cp}}
{{Election box candidate AU party
 |party = Independent
 |candidate = [[Robyn Lambley]]
 |votes = 2,250
 |percentage = 51.2
 |change = +1.0
}}
{{Election box candidate AU party
 |party = CLP
 |candidate = [[Marie-Clare Boothby]]
 |votes = 2,144
 |percentage = 48.8
 |change = -1.0
}}
{{Election box gain AU party
 |winner = Independent
 |loser = CLP
}}
{{Election box end}}
"""


def test_nt_box_count_and_holder():
    (d,) = divisions(BOX)
    assert d["district"] == "Araluen"
    assert [c["party"] for c in d["primary"]] == ["CLP", "IND", "ALP"]
    assert d["primary"][0]["candidate"] == "BOOTHBY Marie-Clare"
    assert d["formal"] == 4394 and d["informal"] == 120
    # The two-candidate count, not the primary lead, decides the seat.
    assert d["elected"]["candidate"] == "LAMBLEY Robyn"
    assert d["held"] is False and d["previous_holder"] == "CLP"


def test_act_names_and_elected_matching():
    assert _name("Taimus WERNER-GIBBINGS") == "WERNER-GIBBINGS Taimus"
    assert _name("Mark PARTON") == "PARTON Mark"
    cell = "Mark Parton - Canberra Liberals, Taimus Werner-Gibbings - ACT Labor"
    assert _is_elected("Mark PARTON", cell)
    assert _is_elected("Taimus WERNER-GIBBINGS", cell)
    assert not _is_elected("Mark JONES", cell)
