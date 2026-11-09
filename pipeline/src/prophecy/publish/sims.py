"""Forecast simulations and history for the website.

``{year}-sims.bin`` holds every simulation, so the site can condition on scenarios
("if the Coalition wins Hawthorn...") in the browser. Little-endian, laid out as
described by ``{year}-sims.json``:

* ``winners``   uint8  S x D  index into ``parties`` (seat order ``districts``)
* ``statewide`` int16  S x B  first preferences by bloc, in tenths of a percent
* ``tpp``       int16  S      ALP v Coalition 2PP, in tenths of a percent

``{year}-history.json`` keeps one headline entry per day the forecast was run.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

SCALE = 10  # int16 fields store tenths of a percent
LOCAL_TZ = {"VIC": "Australia/Melbourne", "NSW": "Australia/Sydney", "QLD": "Australia/Brisbane",
            "SA": "Australia/Adelaide", "WA": "Australia/Perth", "TAS": "Australia/Hobart",
            "ACT": "Australia/Sydney", "NT": "Australia/Darwin", "FED": "Australia/Sydney"}


def encode_sims(arrays: dict[str, np.ndarray]) -> tuple[bytes, dict]:
    """Pack ``sim_arrays`` output into one buffer, plus the header describing it."""
    winners = np.ascontiguousarray(arrays["winners"], dtype="<u1")
    S, D = winners.shape
    statewide = np.round(arrays["statewide"] * SCALE).astype("<i2")
    tpp = np.round(arrays["tpp"] * SCALE).astype("<i2")
    parts, layout, offset = [], [], 0
    for name, a, dtype in (("winners", winners, "uint8"), ("statewide", statewide, "int16"),
                           ("tpp", tpp, "int16")):
        if offset % a.itemsize:  # typed-array views need aligned offsets
            pad = a.itemsize - offset % a.itemsize
            parts.append(b"\0" * pad)
            offset += pad
        layout.append({"name": name, "dtype": dtype, "shape": list(a.shape), "offset": offset,
                       "scale": 1 if dtype == "uint8" else SCALE})
        parts.append(a.tobytes())
        offset += a.nbytes
    header = {
        "n_sims": int(S),
        "districts": [str(d) for d in arrays["districts"]],
        "parties": [str(p) for p in arrays["parties"]],
        "blocs": [str(b) for b in arrays["blocs"]],
        "byte_length": offset,
        "layout": layout,
    }
    return b"".join(parts), header


def decode_sims(buf: bytes, header: dict) -> dict[str, np.ndarray]:
    """Inverse of ``encode_sims`` (what the site does with typed arrays)."""
    out = {}
    for f in header["layout"]:
        dtype = {"uint8": "<u1", "int16": "<i2"}[f["dtype"]]
        n = int(np.prod(f["shape"]))
        a = np.frombuffer(buf, dtype=dtype, count=n, offset=f["offset"]).reshape(f["shape"])
        out[f["name"]] = a if f["scale"] == 1 else a / f["scale"]
    return out


def publish_sims(npz_path: Path, out_dir: Path, year: int, simulated_at: str | None) -> str | None:
    """Write the site's simulation file when the saved simulations match the summary."""
    if not npz_path.exists():
        return None
    with np.load(npz_path) as z:
        if simulated_at is None or str(z["simulated_at"]) != simulated_at:
            return f"simulations in {npz_path} are not from the published forecast: kept the old file"
        buf, header = encode_sims({k: z[k] for k in z.files})
    header["simulated_at"] = simulated_at
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{year}-sims.bin").write_bytes(buf)
    (out_dir / f"{year}-sims.json").write_text(json.dumps(header, indent=1), encoding="utf-8")
    return str(out_dir / f"{year}-sims.bin")


def history_entry(summary: dict, date: str) -> dict:
    """Headline numbers of one forecast run."""
    return {
        "date": date,
        "simulated_at": summary.get("simulated_at"),
        "outcome": summary["outcome"],
        "seats": {p: [q[0], q[2], q[4]] for p, q in summary["seats"].items()},
        "tpp_alp": summary["tpp_alp"],
        "statewide_primary": summary.get("statewide_primary", {}),
        "probs": {d["district"]: d["probs"] for d in summary["districts"]},
    }


def local_date(timestamp: str, jurisdiction: str) -> str:
    tz = ZoneInfo(LOCAL_TZ.get(jurisdiction, "Australia/Sydney"))
    return datetime.fromisoformat(timestamp).astimezone(tz).date().isoformat()


def upsert_history(path: Path, entry: dict) -> list[dict]:
    """Add ``entry`` to the history file, replacing an earlier run on the same day."""
    history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    history = [h for h in history if h["date"] != entry["date"]] + [entry]
    history.sort(key=lambda h: h["date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, separators=(",", ":")), encoding="utf-8")
    return history
