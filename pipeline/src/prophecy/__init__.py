"""Prophecy: Bayesian seat-level forecasting for Australian elections."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CURATED_DIR = DATA_DIR / "curated"
WAREHOUSE = DATA_DIR / "warehouse.duckdb"
WEB_DATA_DIR = REPO_ROOT / "web" / "static" / "data"
