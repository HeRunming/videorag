"""Media-backed AV-TRACE MVP v2 integration."""

from .backend import MediaBackedBackend, MediaRegistration
from .certification import CertificationBinding, verify_certified_dataset
from .experiment import run_media_backed_experiment
from .indexing import MediaIndexBuild, build_media_index

__all__ = [
    "CertificationBinding",
    "MediaBackedBackend",
    "MediaIndexBuild",
    "MediaRegistration",
    "build_media_index",
    "run_media_backed_experiment",
    "verify_certified_dataset",
]
