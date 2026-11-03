"""Publish simplified electoral boundaries (GeoJSON) for the website's seat maps."""

from __future__ import annotations

import json

import polars as pl
import shapely
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.polygon import orient

from prophecy import CURATED_DIR, RAW_DIR, WEB_DATA_DIR
from prophecy.ingest.boundaries import LAYERS, raw_path
from prophecy.ingest.vec import canonical_district
from prophecy.jurisdictions import site_code
from prophecy.publish.results import PROCESSED, slugify

TOLERANCE_DEG = 0.001  # ~100 m: keeps small inner-city seats recognisable
PRECISION_DEG = 0.0001
MIN_ISLAND_DEG2 = 2e-5  # ~0.2 km2: smaller islands are invisible at map scale


def _clockwise(geom):
    """d3-geo treats rings spherically: exteriors must be clockwise (RFC 7946 is the
    opposite), or a polygon renders as the whole globe minus the seat."""
    if isinstance(geom, Polygon):
        return orient(geom, sign=-1.0)
    if isinstance(geom, MultiPolygon):
        return MultiPolygon([orient(p, sign=-1.0) for p in geom.geoms])
    return geom


def _vic_features(boundaries: str) -> list[tuple[dict, dict]]:
    data = json.loads((RAW_DIR / "vicmap" / f"{boundaries}.json").read_text(encoding="utf-8"))
    out = []
    for f in data["features"]:
        p = f["properties"]
        name = canonical_district(p["district_label"].removesuffix(" District"))
        out.append(({"name": name, "slug": slugify(name),
                     "region": p["region_label"].removesuffix(" Region")}, f["geometry"]))
    return out


# An election held on each boundary set, for the commission's spelling of district names.
NAMES_FROM = {"nsw-2013": "nsw-2019", "nsw-2021": "nsw-2023", "qld-2008": "qld-2015", "qld-2017": "qld-2024",
              "sa-2012": "sa-2014", "sa-2016": "sa-2018", "sa-2020": "sa-2022", "sa-2024": "sa-2026"}
LORD_HOWE_LON = 155.0  # Lord Howe Island (in Port Macquarie) would stretch the map


def _mainland(geom):
    if isinstance(geom, MultiPolygon):
        parts = [p for p in geom.geoms if p.bounds[0] < LORD_HOWE_LON]
        return parts[0] if len(parts) == 1 else MultiPolygon(parts)
    return geom


def _land(boundaries: str):
    """The land area to clip a boundary set to (districts that extend out to sea)."""
    key = LAYERS[boundaries].land
    if key is None:
        return None
    data = json.loads(raw_path(key).read_text(encoding="utf-8"))
    land = shapely.union_all([shape(f["geometry"]) for f in data["features"]])
    shapely.prepare(land)
    return land


def _on_land(geom, land):
    geom = geom.intersection(land)
    parts = [p for p in getattr(geom, "geoms", [geom])
             if isinstance(p, Polygon) and p.area >= MIN_ISLAND_DEG2]
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)


def _state_features(boundaries: str) -> list[tuple[dict, dict]]:
    data = json.loads(raw_path(boundaries).read_text(encoding="utf-8"))
    land = _land(boundaries)
    names = {slugify(n): n for n in pl.read_csv(
        PROCESSED / NAMES_FROM[boundaries] / "districts.csv")["district"]}
    regions_path = CURATED_DIR / f"regions_{boundaries}.csv"
    regions = dict(pl.read_csv(regions_path).iter_rows()) if regions_path.exists() else {}
    out = []
    for f in data["features"]:
        props = {k.lower(): v for k, v in f["properties"].items()}  # field case varies by year
        label = props[LAYERS[boundaries].name_field.lower()]
        slug = slugify(label)
        if slug not in names:
            raise ValueError(f"No district in {NAMES_FROM[boundaries]} results for boundary {label!r}")
        geom = _mainland(shape(f["geometry"]))
        geom = mapping(_on_land(geom, land) if land is not None else geom)
        out.append(({"name": names[slug], "slug": slug, "region": regions.get(slug, "")}, geom))
    if len(out) != len(names):
        raise ValueError(f"{len(out)} boundaries for {len(names)} districts in {boundaries}")
    return out


def publish_boundaries(boundaries: str, jurisdiction: str = "VIC") -> str:
    source = _vic_features if jurisdiction == "VIC" else _state_features
    features = []
    for props, geometry in source(boundaries):
        geom = shape(geometry).simplify(TOLERANCE_DEG, preserve_topology=True)
        geom = _clockwise(shapely.set_precision(geom, PRECISION_DEG))
        features.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})
    out = WEB_DATA_DIR / site_code(jurisdiction) / "geo" / f"{boundaries}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                              separators=(",", ":")), encoding="utf-8")
    return str(out)
