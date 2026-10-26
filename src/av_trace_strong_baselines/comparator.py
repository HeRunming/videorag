"""Published-style comparator adapter with mandatory adaptation disclosure."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .adapters import (
    AdapterContext,
    AdapterKind,
    PreparedInvocation,
    SharedGroundedFinalizer,
)
from .contracts import BudgetLedger, sha256_json
from .errors import StrongBaselineError

TRACE_STYLE_LABEL = (
    "AV-TRACE TRACE-style adaptation; not an official TRACE reproduction"
)


@dataclass
class TraceStyleAdaptation:
    """Visual-subset convergence loop; model answers remain model-authored."""

    finalizer: SharedGroundedFinalizer
    disclosure_label: str = TRACE_STYLE_LABEL
    required_consecutive_stable_answers: int = 2
    candidate_hashes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.disclosure_label != TRACE_STYLE_LABEL:
            raise StrongBaselineError("TRACE_ADAPTATION_LABEL_REQUIRED")
        if self.required_consecutive_stable_answers != 2:
            raise StrongBaselineError("TRACE_CONVERGENCE_RULE_MISMATCH")

    def prepare_iteration(
        self,
        context: AdapterContext,
        *,
        iteration: int,
        observations: Sequence[Mapping[str, Any]],
        ledger: BudgetLedger,
    ) -> PreparedInvocation:
        if iteration < 0 or iteration != len(self.candidate_hashes):
            raise StrongBaselineError("TRACE_ITERATION_SEQUENCE_INVALID")
        invocation = self.finalizer.prepare(
            context,
            observations=observations,
            condition="trace_style_adaptation_candidate",
            staged_event_capable=True,
        )
        payload = dict(invocation.public_payload)
        payload["comparator_disclosure"] = self.disclosure_label
        payload["convergence_rule"] = {
            "required_consecutive_stable_answers": 2,
            "final_verification_uses_same_evidence": True,
        }
        payload["remaining_budget"] = ledger.snapshot()
        return PreparedInvocation(
            adapter_kind=AdapterKind.TRACE_STYLE_ADAPTATION,
            model_binding=invocation.model_binding,
            task=invocation.task,
            public_payload=payload,
            max_new_tokens=invocation.max_new_tokens,
            context_cap_processor_tokens=(
                invocation.context_cap_processor_tokens
            ),
            staged_event_capable=True,
        )

    def record_model_candidate(self, final_envelope: Mapping[str, Any]) -> bool:
        """Record, but never synthesize, a candidate answer."""

        digest = sha256_json(final_envelope)
        self.candidate_hashes.append(digest)
        return (
            len(self.candidate_hashes)
            >= self.required_consecutive_stable_answers
            and len(set(self.candidate_hashes[-2:])) == 1
        )

    def prepare_final_verification(
        self,
        context: AdapterContext,
        *,
        observations: Sequence[Mapping[str, Any]],
    ) -> PreparedInvocation:
        if (
            len(self.candidate_hashes) < 2
            or self.candidate_hashes[-1] != self.candidate_hashes[-2]
        ):
            raise StrongBaselineError("TRACE_CONVERGENCE_NOT_REACHED")
        invocation = self.finalizer.prepare(
            context,
            observations=observations,
            condition="trace_style_same_evidence_final_verification",
            staged_event_capable=True,
        )
        payload = dict(invocation.public_payload)
        payload["comparator_disclosure"] = self.disclosure_label
        payload["candidate_answer_hash"] = self.candidate_hashes[-1]
        return PreparedInvocation(
            adapter_kind=AdapterKind.TRACE_STYLE_ADAPTATION,
            model_binding=invocation.model_binding,
            task=invocation.task,
            public_payload=payload,
            max_new_tokens=invocation.max_new_tokens,
            context_cap_processor_tokens=(
                invocation.context_cap_processor_tokens
            ),
            staged_event_capable=True,
        )
