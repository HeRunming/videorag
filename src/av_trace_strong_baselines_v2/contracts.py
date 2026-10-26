"""Versioned contracts for the prospective Granite-native adapter v2.

The v2 package is deliberately separate from the frozen Task-158 adapter.
It contains no model loader and does not authorize a competence or scientific
run.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from av_trace_strong_baselines.contracts import canonical_json_bytes
from av_trace_strong_baselines.errors import StrongBaselineError

ADAPTER_SCHEMA_VERSION = "av-trace.granite-native-adapter/2.0"
MAX_ATTEMPTS_PER_FACTOR = 2
MAX_SCHEMA_ONLY_RETRIES_PER_FACTOR = 1


class FactorStatus(StrEnum):
    """Fail-closed status of one independently authored factor."""

    VALID = "VALID"
    INVALID_OUTPUT = "INVALID_OUTPUT"


class AttemptKind(StrEnum):
    """The only permitted attempt kinds for a factor."""

    INITIAL = "initial"
    SCHEMA_ONLY_RETRY = "schema_only_retry"


class ProjectionStatus(StrEnum):
    """Status of a non-generative cross-factor consistency projection."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True)
class RawFactorAttempt:
    """One exact model-authored response for one factor.

    ``raw_output`` is retained byte-for-byte. The adapter parses a copy but
    never rewrites the stored attempt.
    """

    attempt_index: int
    kind: AttemptKind
    raw_output: bytes

    def __post_init__(self) -> None:
        if self.attempt_index < 1:
            raise StrongBaselineError("FACTOR_ATTEMPT_INDEX_INVALID")
        if not isinstance(self.raw_output, bytes):
            raise StrongBaselineError("FACTOR_RAW_OUTPUT_NOT_BYTES")

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        attempt_index: int = 1,
        kind: AttemptKind = AttemptKind.INITIAL,
    ) -> RawFactorAttempt:
        return cls(
            attempt_index=attempt_index,
            kind=kind,
            raw_output=text.encode("utf-8"),
        )

    @property
    def sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self.raw_output).hexdigest()


@dataclass(frozen=True)
class FactorSpec:
    """Public constrained-output contract for one factor."""

    factor_id: str
    role: str
    output_schema: Mapping[str, Any]
    repairable_error_codes: frozenset[str]
    maximum_bytes: int

    def __post_init__(self) -> None:
        if not self.factor_id or not self.role:
            raise StrongBaselineError("FACTOR_SPEC_IDENTITY_INVALID")
        if self.maximum_bytes <= 0:
            raise StrongBaselineError("FACTOR_MAXIMUM_BYTES_INVALID")


@dataclass(frozen=True)
class FactorOutcome:
    """Parsed factor value plus the complete immutable attempt history."""

    factor_id: str
    status: FactorStatus
    value: Any | None
    error_code: str | None
    attempts: tuple[RawFactorAttempt, ...]

    @property
    def schema_retries_used(self) -> int:
        return sum(
            attempt.kind is AttemptKind.SCHEMA_ONLY_RETRY
            for attempt in self.attempts
        )


@dataclass(frozen=True)
class StateProjection:
    """Accepted state or a typed rejection; never a repaired state."""

    status: ProjectionStatus
    evidence_state: Mapping[str, Any] | None
    error_code: str | None


@dataclass(frozen=True)
class NativeActionChoice:
    """A Granite-native function choice mapped to one frozen menu entry."""

    function_name: str
    action_index: int
    action: Mapping[str, Any]


@dataclass(frozen=True)
class ControllerFactorResult:
    """Independent operational action and diagnostic-state products."""

    action_factor: FactorOutcome
    evidence_state_factor: FactorOutcome
    native_action: NativeActionChoice | None
    state_projection: StateProjection
    canonical_decision: Mapping[str, Any] | None


@dataclass(frozen=True)
class FinalizerFactorResult:
    """All finalizer factors and an optional mechanical canonical envelope."""

    factors: Mapping[str, FactorOutcome]
    projection_status: ProjectionStatus
    projection_error_code: str | None
    canonical_envelope: Mapping[str, Any] | None


FactorValidator = Callable[[Any], Any]


def require_attempt_sequence(
    attempts: Sequence[RawFactorAttempt],
) -> tuple[RawFactorAttempt, ...]:
    """Enforce one initial attempt and at most one schema-only retry."""

    normalized = tuple(attempts)
    if not normalized or len(normalized) > MAX_ATTEMPTS_PER_FACTOR:
        raise StrongBaselineError("FACTOR_ATTEMPT_COUNT_INVALID")
    if normalized[0].attempt_index != 1:
        raise StrongBaselineError("FACTOR_INITIAL_ATTEMPT_MISSING")
    if normalized[0].kind is not AttemptKind.INITIAL:
        raise StrongBaselineError("FACTOR_FIRST_ATTEMPT_NOT_INITIAL")
    if len(normalized) == 2 and (
        normalized[1].attempt_index != 2
        or normalized[1].kind is not AttemptKind.SCHEMA_ONLY_RETRY
    ):
        raise StrongBaselineError("FACTOR_RETRY_SEQUENCE_INVALID")
    return normalized


def fingerprint_public_contract(value: Mapping[str, Any]) -> str:
    """Hash a public adapter plan without relying on model output."""

    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()
