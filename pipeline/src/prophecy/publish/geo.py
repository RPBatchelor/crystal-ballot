"""Publish simplified electoral boundaries (GeoJSON) for the website's seat maps."""

from __future__ import annotations

import json

import shapely
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.polygon import orient

from prophecy import RAW_DIR, WEB_DATA_DIR
from prophecy.ingest.vec import canonical_district
from prophecy.publish.results import slugify

TOLERANCE_DEG = 0.001  # ~100 m: keeps small inner-city seats recognisable
PRECISION_DEG = 0.0001


def _clockwise(geom):
    """d3-geo treats rings spherically: exteriors must be clockwise (RFC 7946 is the
    opposite), or a polygon renders as the whole globe minus the seat."""
    if isinstance(geom, Polygon):
        return orient(geom, sign=-1.0)
    if isinstance(geom, MultiPolygon):
        return MultiPolygon([orient(p, sign=-1.0) for p in geom.geoms])
    return geom


def publish_boundaries(boundaries: str, jurisdiction: str = "VIC") -> str:
    data = json.loads((RAW_DIR / "vicmap" / f"{boundaries}.json").read_text(encoding="utf-8"))
    features = []
    for f in data["features"]:
        p = f["properties"]
        name = canonical_district(p["district_label"].removesuffix(" District"))
        geom = shape(f["geometry"]).simplify(TOLERANCE_DEG, preserve_topology=True)
        geom = _clockwise(shapely.set_precision(geom, PRECISION_DEG))
        features.append({
            "type": "Feature",
            "properties": {"name": name, "slug": slugify(name),
                           "region": p["region_label"].removesuffix(" Region")},
            "geometry": mapping(geom),
        })
    out = WEB_DATA_DIR / jurisdiction.lower() / "geo" / f"{boundaries}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                              separators=(",", ":")), encoding="utf-8")
    return str(out)
