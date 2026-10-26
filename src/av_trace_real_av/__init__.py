"""NOAA-01 bounded real-A/V protocol MVP.

This package is intentionally separate from the normative AV-TRACE episode
schema.  Its annotations are machine-adjudicated, provisional, and are not
human gold.
"""

from .core import build_mvp, run_mvp

__all__ = ["build_mvp", "run_mvp"]
