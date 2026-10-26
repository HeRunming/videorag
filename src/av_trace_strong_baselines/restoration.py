"""Task-145 staged exogenous RESTORED/NO_TRIGGER continuation support."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import BudgetLedger, canonical_json_bytes, sha256_json
from .errors import IsolationViolation, StrongBaselineError
from .security import (
    IsolationAttestation,
    assert_isolated,
    assert_public_surface,
)

TRIGGER_ACTION_INDEX = 4
CHECKPOINT_EVENT = {
    "event_type": "protocol_checkpoint",
    "event_version": "2.0.0",
    "message": "Scheduled protocol checkpoint completed.",
    "cost": 0.0,
}
CHECKPOINT_BYTES = canonical_json_bytes(CHECKPOINT_EVENT)


@dataclass(frozen=True)
class CompletedCycle:
    action: Mapping[str, Any]
    response: Mapping[str, Any]

    def public_dict(self) -> dict[str, Any]:
        value = {
            "action": copy.deepcopy(dict(self.action)),
            "response": copy.deepcopy(dict(self.response)),
        }
        assert_public_surface(value)
        return value


@dataclass(frozen=True)
class FrozenBlockedPrefix:
    cycles: tuple[CompletedCycle, ...]
    ledger_snapshot: Mapping[str, Any]
    public_transcript_hash: str

    @classmethod
    def freeze(
        cls,
        cycles: Sequence[CompletedCycle],
        *,
        ledger: BudgetLedger,
    ) -> FrozenBlockedPrefix:
        if len(cycles) != TRIGGER_ACTION_INDEX:
            raise StrongBaselineError(
                "RESTORATION_PREFIX_WRONG_ACTION_BOUNDARY",
                details={
                    "completed_cycles": len(cycles),
                    "required": TRIGGER_ACTION_INDEX,
                },
            )
        if ledger.actions_used != TRIGGER_ACTION_INDEX or ledger.finalized:
            raise StrongBaselineError("RESTORATION_LEDGER_BOUNDARY_INVALID")
        transcript = [item.public_dict() for item in cycles]
        return cls(
            cycles=tuple(cycles),
            ledger_snapshot=ledger.snapshot(),
            public_transcript_hash=sha256_json(transcript),
        )

    def public_transcript(self) -> list[dict[str, Any]]:
        return [item.public_dict() for item in self.cycles]


@dataclass(frozen=True)
class StagedContinuation:
    arm: str
    public_transcript: tuple[Mapping[str, Any], ...]
    public_transcript_hash_through_event: str
    ledger_snapshot: Mapping[str, Any]
    isolation: IsolationAttestation
    _route_available: bool

    @property
    def route_available_private(self) -> bool:
        return self._route_available

    def model_visible_payload(self) -> dict[str, Any]:
        value = {
            "public_transcript": [
                copy.deepcopy(dict(item)) for item in self.public_transcript
            ],
            "remaining_budget": copy.deepcopy(dict(self.ledger_snapshot)),
        }
        assert_public_surface(value)
        return value


@dataclass(frozen=True)
class EarlyTerminalAssignment:
    """Task-145 ITT record when the shared blocked prefix terminates early."""

    arm: str
    terminal_public_transcript: tuple[Mapping[str, Any], ...]
    terminal_public_transcript_hash: str
    trigger_opportunity_reached: bool = False
    checkpoint_delivered: bool = False


def copy_early_terminal_assignments(
    public_transcript: Sequence[Mapping[str, Any]],
) -> tuple[EarlyTerminalAssignment, EarlyTerminalAssignment]:
    """Copy one pre-trigger terminal prefix to both assigned arms."""

    if len(public_transcript) >= TRIGGER_ACTION_INDEX:
        raise StrongBaselineError("EARLY_TERMINAL_PREFIX_NOT_EARLY")
    normalized = tuple(copy.deepcopy(dict(item)) for item in public_transcript)
    assert_public_surface(normalized)
    digest = sha256_json(normalized)
    return (
        EarlyTerminalAssignment(
            arm="RESTORED",
            terminal_public_transcript=normalized,
            terminal_public_transcript_hash=digest,
        ),
        EarlyTerminalAssignment(
            arm="NO_TRIGGER",
            terminal_public_transcript=normalized,
            terminal_public_transcript_hash=digest,
        ),
    )


def fork_restored_no_trigger(
    prefix: FrozenBlockedPrefix,
    *,
    restored_isolation: IsolationAttestation,
    no_trigger_isolation: IsolationAttestation,
) -> tuple[StagedContinuation, StagedContinuation]:
    """Replay one blocked prefix into fresh isolated R/N continuations."""

    assert_isolated([restored_isolation, no_trigger_isolation])
    transcript = prefix.public_transcript()
    event = json_roundtrip_checkpoint()
    transcript_with_event = (*transcript, event)
    transcript_hash = sha256_json(transcript_with_event)
    restored = StagedContinuation(
        arm="RESTORED",
        public_transcript=transcript_with_event,
        public_transcript_hash_through_event=transcript_hash,
        ledger_snapshot=copy.deepcopy(dict(prefix.ledger_snapshot)),
        isolation=restored_isolation,
        _route_available=True,
    )
    no_trigger = StagedContinuation(
        arm="NO_TRIGGER",
        public_transcript=transcript_with_event,
        public_transcript_hash_through_event=transcript_hash,
        ledger_snapshot=copy.deepcopy(dict(prefix.ledger_snapshot)),
        isolation=no_trigger_isolation,
        _route_available=False,
    )
    if (
        restored.public_transcript_hash_through_event
        != no_trigger.public_transcript_hash_through_event
    ):
        raise IsolationViolation("R_N_PUBLIC_PREFIX_HASH_MISMATCH")
    if canonical_json_bytes(restored.public_transcript[-1]) != CHECKPOINT_BYTES:
        raise IsolationViolation("RESTORED_CHECKPOINT_BYTES_MISMATCH")
    if canonical_json_bytes(no_trigger.public_transcript[-1]) != CHECKPOINT_BYTES:
        raise IsolationViolation("NO_TRIGGER_CHECKPOINT_BYTES_MISMATCH")
    return restored, no_trigger


def json_roundtrip_checkpoint() -> dict[str, Any]:
    """Return a detached object with the exact frozen checkpoint bytes."""

    import json

    return json.loads(CHECKPOINT_BYTES)
