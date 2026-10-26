"""Restricted real-media visual + subtitle-proxy rehearsal machinery."""

from .adapter import (
    AssetBinding,
    FrameSample,
    IntegrityBindingError,
    RestrictedAssetAdapter,
    RestrictedAssetError,
    SubtitleProxyHit,
)
from .protocol import RehearsalRunner, derive_provisional_tasks

__all__ = [
    "AssetBinding",
    "FrameSample",
    "IntegrityBindingError",
    "RehearsalRunner",
    "RestrictedAssetAdapter",
    "RestrictedAssetError",
    "SubtitleProxyHit",
    "derive_provisional_tasks",
]
