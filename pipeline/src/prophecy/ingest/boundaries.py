"""State electoral district boundaries from the states' spatial data services.

* New South Wales (NSW Spatial Services, maintained with the NSW Electoral Commission): a
  snapshot of the 2013 redistribution (used at the 2015 and 2019 elections) and the current
  Administrative Boundaries Theme layer (the 2021 redistribution, first used in 2023).
* Queensland (Queensland Spatial, Administrative Boundaries Framework): the 2008
  redistribution (used at the 2009, 2012 and 2015 elections) and the 2017 one (2017, 2020
  and 2024). Queensland's districts run
  out to sea (Cook covers the Torres Strait, Traeger and Gregory the Gulf), so for maps
  they are clipped to the state's land area: the ABS state outline (ASGS 2021), which
  follows the coast and keeps the islands.

* South Australia (Location SA, "State Electorates" on data.sa.gov.au): one zipped GeoJSON
  per election, as determined by the Electoral Districts Boundaries Commission before it.

A "current" layer moves to the next redistribution's boundaries when they take effect,
so each download is cached once under ``data/raw/boundaries``.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from prophecy import RAW_DIR
from prophecy.ingest.vec import USER_AGENT, _cached_get


@dataclass(frozen=True)
class Layer:
    url: str  # ArcGIS feature/map service layer
    name_field: str  # attribute holding the district name
    where: str = "1%3D1"  # query filter (URL-encoded)
    land: str | None = None  # layer to clip the districts to, for districts extending to sea
    zip_member: str | None = None  # ``url`` is a zip download: its GeoJSON ending in this, if several


LAYERS = {
    "nsw-2013": Layer("https://portal.spatial.nsw.gov.au/server/rest/services/"
                      "Hosted/2013_NSW_Electoral_Boundaries/FeatureServer/0", "districtname"),
    "nsw-2021": Layer("https://portal.spatial.nsw.gov.au/server/rest/services/"
                      "NSW_Administrative_Boundaries_Theme/FeatureServer/4", "districtname"),
    "qld-2008": Layer("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
                      "Boundaries/AdminBoundariesFramework/MapServer/12", "adminareaname", land="qld-land"),
    "qld-2017": Layer("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
                      "Boundaries/AdminBoundariesFramework/MapServer/139", "name", land="qld-land"),
    "qld-land": Layer("https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/STE/MapServer/0",
                      "state_name_2021", where="state_code_2021%3D%273%27"),
    # South Australia: boundary set (redistribution year) -> the election it was drawn for.
    **{f"sa-{drawn}": Layer(f"https://www.dptiapps.com.au/dataportal/StateElectorates{used}_geojson.zip",
                            "electorate", zip_member="GDA2020.geojson")
       for drawn, used in [(2012, 2014), (2016, 2018), (2020, 2022), (2024, 2026)]},
}


def raw_path(boundary_set: str) -> Path:
    return RAW_DIR / "boundaries" / f"{boundary_set}.json"


def fetch_boundaries(boundary_set: str) -> Path:
    """Full-resolution GeoJSON (WGS84) of one boundary set (10-50 MB), and of the land
    area it is clipped to, if any."""
    layer = LAYERS[boundary_set]
    if layer.land:
        fetch_boundaries(layer.land)
    dest = raw_path(boundary_set)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=300) as client:
        if layer.zip_member is None:
            query = f"query?where={layer.where}&outFields={layer.name_field}&outSR=4326&f=geojson"
            return _cached_get(client, f"{layer.url}/{query}", dest)
        if not dest.exists():
            z = _cached_get(client, layer.url, dest.with_suffix(".zip"), binary=True)
            with zipfile.ZipFile(io.BytesIO(z.read_bytes())) as zf:
                names = [n for n in zf.namelist() if n.endswith(".geojson")]
                member = next((n for n in names if n.endswith(layer.zip_member)), names[0])
                dest.write_bytes(zf.read(member))
        return dest
