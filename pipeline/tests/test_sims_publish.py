import json

import numpy as np

from prophecy.publish.sims import (
    decode_sims,
    encode_sims,
    history_entry,
    local_date,
    publish_sims,
    upsert_history,
)


def arrays(S=50, D=7, seed=0):
    rng = np.random.default_rng(seed)
    return {
        "winners": rng.integers(0, 4, size=(S, D)).astype(np.uint8),
        "parties": np.array(["ALP", "LIB", "NAT", "GRN"]),
        "districts": np.array([f"D{i}" for i in range(D)]),
        "blocs": np.array(["ALP", "COAL", "GRN"]),
        "statewide": rng.uniform(5, 45, size=(S, 3)).astype(np.float32),
        "tpp": rng.uniform(40, 60, size=S).astype(np.float32),
    }


def test_round_trip_and_alignment():
    a = arrays(D=7)  # odd S*D: the int16 block needs padding
    buf, header = encode_sims(a)
    assert len(buf) == header["byte_length"]
    assert all(f["offset"] % (1 if f["dtype"] == "uint8" else 2) == 0 for f in header["layout"])
    back = decode_sims(buf, header)
    assert np.array_equal(back["winners"], a["winners"])
    assert np.allclose(back["statewide"], a["statewide"], atol=0.05)
    assert np.allclose(back["tpp"], a["tpp"], atol=0.05)
    # Seat totals recomputed from the file are exact.
    alp = (back["winners"] == header["parties"].index("ALP")).sum(axis=1)
    assert np.array_equal(alp, (a["winners"] == 0).sum(axis=1))


def test_publish_sims_skips_stale_simulations(tmp_path):
    npz = tmp_path / "s.npz"
    np.savez_compressed(npz, simulated_at=np.array("2026-11-09T05:00:00+00:00"), **arrays())
    assert "not from the published forecast" in publish_sims(npz, tmp_path / "out", 2026, "other")
    assert not (tmp_path / "out").exists()
    assert publish_sims(npz, tmp_path / "out", 2026, "2026-11-09T05:00:00+00:00")
    header = json.loads((tmp_path / "out" / "2026-sims.json").read_text())
    assert header["n_sims"] == 50 and header["simulated_at"] == "2026-11-09T05:00:00+00:00"


def test_history_one_entry_per_local_day(tmp_path):
    summary = {"outcome": {"hung": 0.3}, "seats": {"ALP": [1, 2, 3, 4, 5]}, "tpp_alp": [40, 45, 50],
               "districts": [{"district": "A", "probs": {"ALP": 1.0}}]}
    # 23:00 UTC on 8 Nov is the morning of 9 Nov in Melbourne.
    assert local_date("2026-11-08T23:00:35+00:00", "VIC") == "2026-11-09"
    path = tmp_path / "h.json"
    upsert_history(path, history_entry(summary, "2026-11-09"))
    upsert_history(path, history_entry({**summary, "outcome": {"hung": 0.4}}, "2026-11-09"))
    h = upsert_history(path, history_entry(summary, "2026-11-08"))
    assert [e["date"] for e in h] == ["2026-11-08", "2026-11-09"]
    assert h[1]["outcome"]["hung"] == 0.4 and h[0]["seats"]["ALP"] == [1, 3, 5]
