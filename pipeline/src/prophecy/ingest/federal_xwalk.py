"""Re-aggregate federal booth results onto state electoral districts.

Each federal polling place (with AEC coordinates) is assigned to the state district
whose boundary contains it, and first-preference votes are summed by bloc. Pre-poll
centres are assigned by location too: they draw voters from a wider area, so the
result is a geographic *pattern* (relative strength by district), not an exact count.

This is how the seat model learns where One Nation's vote sits: the party barely
contested the 2022 state election, but ran in every Victorian seat federally in 2025.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
from shapely import STRtree, points
from shapely.geometry import shape

from prophecy import RAW_DIR

AEC_PARTY_BLOC = {
    "ALP": "ALP",
    "LP": "COAL",
    "NP": "COAL",
    "LNP": "COAL",
    "GRN": "GRN",
    "GVIC": "GRN",
    "ON": "ONP",
    "IND": "IND",
}


def load_districts(path: Path) -> tuple[list[str], list[str], list]:
    """District names, Council regions and shapely geometries from Vicmap GeoJSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    names, regions, geoms = [], [], []
    for f in data["features"]:
        p = f["properties"]
        names.append(p["district_label"].removesuffix(" District"))
        regions.append(p["region_label"].removesuffix(" Region"))
        geoms.append(shape(f["geometry"]))
    return names, regions, geoms


def assign_polling_places(places: pl.DataFrame, names: list[str], geoms: list) -> pl.DataFrame:
    tree = STRtree(geoms)
    located = places.filter(pl.col("Latitude").is_not_null())
    pts = points(located["Longitude"].to_numpy(), located["Latitude"].to_numpy())
    pt_idx, geom_idx = tree.query(pts, predicate="within")
    district = np.full(len(pts), None, dtype=object)
    district[pt_idx] = np.array(names, dtype=object)[geom_idx]
    return located.with_columns(pl.Series("district", district, dtype=pl.String))


def federal_by_state_district(event: str = "31496", boundaries: str = "assembly2022") -> pl.DataFrame:
    raw = RAW_DIR / "aec" / "2025"
    booths = pl.read_csv(raw / f"HouseStateFirstPrefsByPollingPlaceDownload-{event}-VIC.csv", skip_rows=1)
    places = pl.read_csv(raw / f"GeneralPollingPlacesDownload-{event}.csv", skip_rows=1).filter(
        pl.col("State") == "VIC"
    )
    names, _, geoms = load_districts(RAW_DIR / "vicmap" / f"{boundaries}.json")
    places = assign_polling_places(places, names, geoms)

    votes = (
        booths.join(places.select("PollingPlaceID", "district"), on="PollingPlaceID", how="inner")
        .filter(pl.col("district").is_not_null())
        .with_columns(
            pl.col("PartyAb").replace_strict(AEC_PARTY_BLOC, default="OTH").alias("bloc")
        )
        .group_by("district", "bloc")
        .agg(pl.col("OrdinaryVotes").sum().alias("votes"))
    )
    return votes.with_columns(
        (100 * pl.col("votes") / pl.col("votes").sum().over("district")).round(3).alias("pct")
    ).sort("district", "bloc")


def district_regions(boundaries: str = "assembly2022") -> pl.DataFrame:
    names, regions, _ = load_districts(RAW_DIR / "vicmap" / f"{boundaries}.json")
    return pl.DataFrame({"district": names, "region": regions})


BOOTH_FILES = ("HouseStateFirstPrefsByPollingPlaceDownload-{event}-{state}.csv",
               "GeneralPollingPlacesDownload-{event}.csv")


def _fetch_booth_files(event: str, state: str) -> Path:
    """Cached AEC polling-place files (first preferences for ``state``; locations)."""
    import time

    import httpx

    from prophecy.ingest.aec import USER_AGENT

    out = RAW_DIR / "aec" / event
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True) as c:
        for pattern in BOOTH_FILES:
            name = pattern.format(event=event, state=state)
            dest = out / name
            if dest.exists() and dest.stat().st_size > 0:
                continue
            r = c.get(f"https://results.aec.gov.au/{event}/Website/Downloads/{name}")
            r.raise_for_status()
            dest.write_bytes(r.content)
            time.sleep(1)
    return out


def _lenient_csv(path: Path) -> pl.DataFrame:
    """AEC polling-place list (after its title line), read with Python's csv module: some
    addresses carry stray quotes (2019: '"Cnr" Rupert Ct') that strict parsers reject."""
    import csv

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))[1:]
    header, body = rows[0], [r for r in rows[1:] if len(r) == len(rows[0])]
    df = pl.DataFrame(body, schema=header, orient="row")
    return df.with_columns(pl.col("PollingPlaceID").cast(pl.Int64),
                           pl.col("Latitude").cast(pl.Float64, strict=False),
                           pl.col("Longitude").cast(pl.Float64, strict=False))


def federal_geography(year: int, state: str, boundary_set: str, districts: list[str]) -> pl.DataFrame:
    """Federal ``year`` first preferences by bloc on a state's ``boundary_set`` districts
    (district, bloc, votes, pct), from AEC polling places located in each district.

    ``districts`` are the state election's own district names; boundary files label
    them differently (capitals), so names are matched on their slug."""
    from prophecy.ingest.aec import EVENTS
    from prophecy.ingest.boundaries import LAYERS, raw_path
    from prophecy.publish.results import slugify

    event = EVENTS[year]
    raw = _fetch_booth_files(event, state)
    booths = pl.read_csv(raw / BOOTH_FILES[0].format(event=event, state=state), skip_rows=1,
                         infer_schema_length=None)
    places = _lenient_csv(raw / BOOTH_FILES[1].format(event=event)).filter(pl.col("State") == state)
    by_slug = {slugify(d): d for d in districts}
    data = json.loads(raw_path(boundary_set).read_text(encoding="utf-8"))
    field = LAYERS[boundary_set].name_field.lower()
    names, geoms = [], []
    for f in data["features"]:
        props = {k.lower(): v for k, v in f["properties"].items()}
        name = by_slug.get(slugify(str(props[field])))
        if name is None:
            raise ValueError(f"{boundary_set}: boundary {props[field]!r} matches no district")
        names.append(name)
        geoms.append(shape(f["geometry"]))
    places = assign_polling_places(places, names, geoms)
    votes = (
        booths.join(places.select("PollingPlaceID", "district"), on="PollingPlaceID", how="inner")
        .filter(pl.col("district").is_not_null())
        .with_columns(pl.col("PartyAb").replace_strict(AEC_PARTY_BLOC, default="OTH").alias("bloc"))
        .group_by("district", "bloc")
        .agg(pl.col("OrdinaryVotes").sum().alias("votes"))
    )
    return votes.with_columns(
        (100 * pl.col("votes") / pl.col("votes").sum().over("district")).round(3).alias("pct")
    ).sort("district", "bloc")
