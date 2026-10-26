"""Deterministic Scale-1A full-timeline indexing and evaluation."""

from .core import (
    Scale1AError,
    build_scale1a,
    run_scale1a,
    verify_scale1a,
)

__all__ = ["Scale1AError", "build_scale1a", "run_scale1a", "verify_scale1a"]
