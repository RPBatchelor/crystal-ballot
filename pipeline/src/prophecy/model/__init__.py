"""Forecast models (Stan) and simulation."""

from __future__ import annotations

import sys
from functools import cache
from pathlib import Path

STAN_DIR = Path(__file__).parent / "stan"


@cache
def stan_model(name: str):
    """Compile (or load the cached build of) ``stan/<name>.stan``."""
    import cmdstanpy

    if sys.platform == "win32":
        # Puts the RTools C++ toolchain installed by cmdstanpy on PATH.
        cmdstanpy.utils.cxx_toolchain_path()
    return cmdstanpy.CmdStanModel(stan_file=STAN_DIR / f"{name}.stan")
