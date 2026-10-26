"""AV-TRACE Pilot-0 synthetic validation reference implementation."""

from .errors import ValidationIssue, ValidationReport
from .diffing import structural_differences, validate_family_diff
from .manifest import GateProfile, validate_manifest_gate
from .replay import SyntheticReplayBackend
from .schemas import SchemaRegistry
from .semantic import validate_family
from .trajectory import validate_action, validate_response, validate_trajectory

__all__ = [
    "GateProfile",
    "SchemaRegistry",
    "SyntheticReplayBackend",
    "ValidationIssue",
    "ValidationReport",
    "structural_differences",
    "validate_action",
    "validate_family",
    "validate_family_diff",
    "validate_manifest_gate",
    "validate_response",
    "validate_trajectory",
]

__version__ = "0.1.0"
