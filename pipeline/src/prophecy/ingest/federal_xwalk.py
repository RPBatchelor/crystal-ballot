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
