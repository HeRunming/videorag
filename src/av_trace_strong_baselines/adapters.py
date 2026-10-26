"""Model-agnostic strong-baseline adapter interfaces and dry plans."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .contracts import (
    CANONICAL_TOOLS,
    BudgetLedger,
    CommonBudget,
    ModelBinding,
    sha256_json,
)
from .errors import SchemaViolation, StrongBaselineError
from .schemas import (
    parse_strict_json,
    validate_agent_action,
    validate_evidence_state,
    validate_final_answer_envelope,
    validate_tool_action,
)
from .security import (
    ObservedEvidenceLock,
    OutputProvenance,
    assert_public_surface,
)


class AdapterKind(StrEnum):
    DIRECT_AV = "DIRECT_AV"
    SINGLE_SHOT_RAG = "SINGLE_SHOT_RAG"
    SAME_BACKBONE_REACT = "SAME_BACKBONE_REACT"
    SAME_BACKBONE_SUFFICIENCY = "SAME_BACKBONE_SUFFICIENCY"
    ORACLE_EVIDENCE = "ORACLE_EVIDENCE"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"
    TRACE_STYLE_ADAPTATION = "TRACE_STYLE_ADAPTATION"
    DETERMINISTIC_CONTROL = "DETERMINISTIC_CONTROL"
    SHARED_GROUNDED_FINALIZER = "SHARED_GROUNDED_FINALIZER"


@dataclass(frozen=True)
class AdapterContext:
    episode_id: str
    question: str
    public_claim_slots: tuple[Mapping[str, str], ...]
    available_tools: tuple[str, ...] = CANONICAL_TOOLS
    budget: CommonBudget = field(default_factory=CommonBudget)

    def __post_init__(self) -> None:
        if not self.episode_id or not self.question.strip():
            raise StrongBaselineError("ADAPTER_CONTEXT_INVALID")
        handles = [
            item.get("claim_handle") for item in self.public_claim_slots
        ]
        if (
            not handles
            or any(not isinstance(item, str) or not item for item in handles)
            or len(set(handles)) != len(handles)
        ):
            raise StrongBaselineError("PUBLIC_CLAIM_SLOTS_INVALID")
        if tuple(self.available_tools) != CANONICAL_TOOLS:
            raise StrongBaselineError("COMMON_TOOL_MENU_MISMATCH")
        assert_public_surface(self.public_payload())

    @property
    def claim_handles(self) -> tuple[str, ...]:
        return tuple(
            str(item["claim_handle"]) for item in self.public_claim_slots
        )

    def public_payload(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "question": self.question,
            "public_claim_slots": [dict(item) for item in self.public_claim_slots],
            "available_tools": list(self.available_tools),
            "budget": self.budget.to_dict(),
        }


@dataclass(frozen=True)
class PreparedInvocation:
    adapter_kind: AdapterKind
    model_binding: ModelBinding
    task: str
    public_payload: Mapping[str, Any]
    max_new_tokens: int
    context_cap_processor_tokens: int
    staged_event_capable: bool

    def __post_init__(self) -> None:
        assert_public_surface(self.public_payload)
        if self.max_new_tokens != 512:
            raise StrongBaselineError("INVOCATION_OUTPUT_CAP_MISMATCH")
        if self.context_cap_processor_tokens != 32_768:
            raise StrongBaselineError("INVOCATION_CONTEXT_CAP_MISMATCH")

    @property
    def fingerprint(self) -> str:
        return sha256_json(
            {
                "adapter_kind": self.adapter_kind,
                "model_binding": self.model_binding.to_dict(),
                "task": self.task,
                "public_payload": self.public_payload,
                "max_new_tokens": self.max_new_tokens,
                "context_cap_processor_tokens": (
                    self.context_cap_processor_tokens
                ),
                "staged_event_capable": self.staged_event_capable,
            }
        )


@dataclass(frozen=True)
class AdapterFailure:
    status: str
    error_code: str
    final_answer: None = None
    deterministic_substitution_used: bool = False


def fail_closed(error_code: str, *, status: str = "INVALID") -> AdapterFailure:
    return AdapterFailure(status=status, error_code=error_code)


def _interval(raw: Mapping[str, Any]) -> dict[str, float]:
    start = raw.get("start_s")
    end = raw.get("end_s")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, (int, float))
        or not isinstance(end, (int, float))
        or float(start) < 0
        or float(end) <= float(start)
    ):
        raise SchemaViolation("MEDIA_INTERVAL_INVALID")
    return {"start_s": float(start), "end_s": float(end)}


class DirectAVAdapter:
    """One-shot native or packed A/V generation over frozen exposure order."""

    def __init__(
        self,
        *,
        model_binding: ModelBinding,
        route_label: str,
        strict_native_av: bool,
    ) -> None:
        self.model_binding = model_binding
        self.route_label = route_label
        self.strict_native_av = strict_native_av

    def prepare(
        self,
        context: AdapterContext,
        *,
        media_exposure_manifest: Sequence[Mapping[str, Any]],
    ) -> PreparedInvocation:
        normalized: list[dict[str, Any]] = []
        for item in media_exposure_manifest:
            _keys = {
                "exposure_id",
                "source_ordinal",
                "interval",
                "modalities",
                "asset_locator",
            }
            if set(item) != _keys:
                raise SchemaViolation("DIRECT_EXPOSURE_FIELD_SET")
            modalities = item["modalities"]
            if (
                not isinstance(modalities, list)
                or not modalities
                or any(
                    value not in {"vision", "speech", "ambient"}
                    for value in modalities
                )
            ):
                raise SchemaViolation("DIRECT_EXPOSURE_MODALITIES")
            normalized.append(
                {
                    "exposure_id": str(item["exposure_id"]),
                    "source_ordinal": int(item["source_ordinal"]),
                    "interval": _interval(item["interval"]),
                    "modalities": list(modalities),
                    "asset_locator": str(item["asset_locator"]),
                }
            )
        expected = sorted(
            normalized,
            key=lambda row: (
                row["source_ordinal"],
                row["interval"]["start_s"],
                row["interval"]["end_s"],
                row["exposure_id"],
            ),
        )
        if normalized != expected:
            raise SchemaViolation(
                "DIRECT_PACKING_NOT_QUESTION_INDEPENDENT_CHRONOLOGICAL"
            )
        payload = {
            **context.public_payload(),
            "task": "direct_av_grounded_finalization",
            "route_label": self.route_label,
            "strict_native_av": self.strict_native_av,
            "packing_policy": (
                "question_independent_source_uniform_chronological"
            ),
            "media_exposure_manifest": normalized,
        }
        return PreparedInvocation(
            adapter_kind=AdapterKind.DIRECT_AV,
            model_binding=self.model_binding,
            task="direct_av_grounded_finalization",
            public_payload=payload,
            max_new_tokens=context.budget.max_new_tokens_per_call,
            context_cap_processor_tokens=(
                context.budget.context_cap_processor_tokens
            ),
            staged_event_capable=False,
        )

    def parse_and_validate(
        self,
        raw: bytes | str,
        *,
        context: AdapterContext,
        media_exposure_manifest: Sequence[Mapping[str, Any]],
        provenance: OutputProvenance,
    ) -> dict[str, Any]:
        self.prepare(
            context, media_exposure_manifest=media_exposure_manifest
        )
        observations = [
            {
                "observation_id": str(item["exposure_id"]),
                "interval": _interval(item["interval"]),
                "modalities": list(item["modalities"]),
                "payload": {"exposure": "direct_av"},
            }
            for item in media_exposure_manifest
        ]
        value = parse_strict_json(raw, maximum_bytes=64_000)
        return validate_final_answer_envelope(
            value,
            claim_handles=context.claim_handles,
            evidence_lock=ObservedEvidenceLock(observations),
            provenance=provenance,
        )


class SingleShotRAGAdapter:
    """One frozen search per modality followed by one shared finalizer."""

    SEARCH_TOOLS = (
        "search_visual",
        "search_speech",
        "search_ambient_audio",
    )

    def __init__(
        self,
        *,
        controller_binding: ModelBinding,
        finalizer: SharedGroundedFinalizer,
    ) -> None:
        _require_same_snapshot(controller_binding, finalizer.model_binding)
        self.controller_binding = controller_binding
        self.finalizer = finalizer

    def frozen_search_actions(
        self, context: AdapterContext
    ) -> list[dict[str, Any]]:
        actions = []
        for tool in self.SEARCH_TOOLS:
            actions.append(
                {
                    "tool": tool,
                    "arguments": {
                        "query": context.question,
                        "top_k": context.budget.search_top_k,
                        "time_range": {
                            "start_s": 0.0,
                            "end_s": 1_000_000_000.0,
                        },
                        "exclude_result_ids": [],
                        **(
                            {"speaker_hint": None}
                            if tool == "search_speech"
                            else {}
                        ),
                    },
                }
            )
        return actions

    def prepare_retrieval(self, context: AdapterContext) -> tuple[
        list[dict[str, Any]], BudgetLedger
    ]:
        ledger = BudgetLedger(context.budget)
        actions = self.frozen_search_actions(context)
        for action in actions:
            validate_tool_action(action)
            ledger.charge_action(action)
        return actions, ledger

    @staticmethod
    def fuse_pointers(
        rankings: Mapping[str, Sequence[Mapping[str, Any]]],
        *,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """Apply fixed equal-weight reciprocal-rank fusion without semantics."""

        if set(rankings) != {"vision", "speech", "ambient"}:
            raise SchemaViolation("RAG_MODALITY_RANKINGS_INCOMPLETE")
        if rrf_k != 60:
            raise SchemaViolation("RAG_FUSION_PARAMETER_MISMATCH")
        fused: dict[str, dict[str, Any]] = {}
        for modality in ("vision", "speech", "ambient"):
            seen: set[str] = set()
            for rank, pointer in enumerate(rankings[modality], 1):
                pointer_id = pointer.get("pointer_id")
                if not isinstance(pointer_id, str) or not pointer_id:
                    raise SchemaViolation("RAG_POINTER_ID_INVALID")
                if pointer_id in seen:
                    raise SchemaViolation("RAG_POINTER_DUPLICATE_WITHIN_RANKING")
                seen.add(pointer_id)
                row = fused.setdefault(
                    pointer_id,
                    {
                        "pointer_id": pointer_id,
                        "modalities": set(),
                        "rrf_score": 0.0,
                        "best_rank": rank,
                    },
                )
                row["modalities"].add(modality)
                row["rrf_score"] += 1.0 / (rrf_k + rank)
                row["best_rank"] = min(row["best_rank"], rank)
        ordered = sorted(
            fused.values(),
            key=lambda row: (
                -row["rrf_score"],
                row["best_rank"],
                row["pointer_id"],
            ),
        )
        return [
            {
                "pointer_id": row["pointer_id"],
                "modalities": sorted(row["modalities"]),
                "rrf_score": round(row["rrf_score"], 12),
            }
            for row in ordered
        ]

    def prepare_finalization(
        self,
        context: AdapterContext,
        *,
        observations: Sequence[Mapping[str, Any]],
    ) -> PreparedInvocation:
        return self.finalizer.prepare(
            context,
            observations=observations,
            condition="single_shot_rag",
            staged_event_capable=True,
        )

    def prepare_acquisition(
        self,
        *,
        pointers: Sequence[Mapping[str, Any]],
        selected_pointer_ids: Sequence[str],
        ledger: BudgetLedger,
    ) -> list[dict[str, Any]]:
        """Materialize a frozen fused pointer list without adaptive searching."""

        pointer_map: dict[str, Mapping[str, Any]] = {}
        for pointer in pointers:
            if set(pointer) != {
                "pointer_id",
                "interval",
                "modalities",
                "citable",
            }:
                raise SchemaViolation("RAG_POINTER_FIELD_SET")
            if pointer["citable"] is not False:
                raise SchemaViolation("SEARCH_POINTER_MUST_BE_NONCITABLE")
            pointer_id = pointer["pointer_id"]
            if not isinstance(pointer_id, str) or pointer_id in pointer_map:
                raise SchemaViolation("RAG_POINTER_ID_INVALID")
            _interval(pointer["interval"])
            modalities = pointer["modalities"]
            if (
                not isinstance(modalities, list)
                or not modalities
                or any(
                    value not in {"vision", "speech", "ambient"}
                    for value in modalities
                )
            ):
                raise SchemaViolation("RAG_POINTER_MODALITIES_INVALID")
            pointer_map[pointer_id] = pointer
        if len(set(selected_pointer_ids)) != len(selected_pointer_ids):
            raise SchemaViolation("RAG_SELECTED_POINTER_DUPLICATE")
        actions: list[dict[str, Any]] = []
        for pointer_id in selected_pointer_ids:
            if pointer_id not in pointer_map:
                raise SchemaViolation("RAG_SELECTED_POINTER_UNKNOWN")
            pointer = pointer_map[pointer_id]
            modalities = set(pointer["modalities"])
            if modalities == {"speech"}:
                action = {
                    "tool": "read_transcript",
                    "arguments": {
                        "interval": dict(pointer["interval"]),
                        "source": "asr",
                        "include_word_timestamps": True,
                    },
                }
            else:
                action = {
                    "tool": "inspect_clip",
                    "arguments": {
                        "interval": dict(pointer["interval"]),
                        "include_video": "vision" in modalities,
                        "include_audio": bool(
                            modalities & {"speech", "ambient"}
                        ),
                    },
                }
            validate_tool_action(action)
            if (
                ledger.actions_used + 1
                >= ledger.budget.max_canonical_actions_including_finalize
            ):
                raise StrongBaselineError("RAG_ACQUISITION_LEAVES_NO_FINALIZE")
            ledger.charge_action(action)
            actions.append(action)
        return actions


class _SameBackboneToolAdapter:
    policy: str
    adapter_kind: AdapterKind

    def __init__(
        self,
        *,
        controller_binding: ModelBinding,
        finalizer: SharedGroundedFinalizer,
    ) -> None:
        _require_same_snapshot(controller_binding, finalizer.model_binding)
        self.controller_binding = controller_binding
        self.finalizer = finalizer

    def prepare_turn(
        self,
        context: AdapterContext,
        *,
        turn: int,
        action_menu: Sequence[Mapping[str, Any]],
        observed_evidence: Sequence[Mapping[str, Any]],
        public_history: Sequence[Mapping[str, Any]],
        ledger: BudgetLedger,
    ) -> PreparedInvocation:
        if turn != ledger.actions_used:
            raise StrongBaselineError("TURN_LEDGER_MISMATCH")
        if not action_menu:
            raise SchemaViolation("ACTION_MENU_EMPTY")
        for action in action_menu:
            validate_tool_action(action)
        lock = ObservedEvidenceLock(observed_evidence)
        payload = {
            **context.public_payload(),
            "task": "choose_next_action",
            "policy": self.policy,
            "turn": turn,
            "action_menu": [copy.deepcopy(dict(item)) for item in action_menu],
            "observed_evidence": lock.public_observations(),
            "observed_evidence_lock": lock.fingerprint,
            "recent_public_history": [
                copy.deepcopy(dict(item)) for item in public_history
            ],
            "remaining_budget": ledger.snapshot(),
            "evidence_state_schema": [
                "p_sufficient",
                "covered_claim_handles",
                "missing_modalities",
                "missing_hops",
                "missingness_cause",
                "recovery_intent",
            ],
        }
        return PreparedInvocation(
            adapter_kind=self.adapter_kind,
            model_binding=self.controller_binding,
            task="choose_next_action",
            public_payload=payload,
            max_new_tokens=context.budget.max_new_tokens_per_call,
            context_cap_processor_tokens=(
                context.budget.context_cap_processor_tokens
            ),
            staged_event_capable=True,
        )

    def parse_decision(
        self,
        raw: bytes | str,
        *,
        context: AdapterContext,
        action_menu: Sequence[Mapping[str, Any]],
        observed_evidence: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        value = parse_strict_json(raw, maximum_bytes=8_192)
        if not isinstance(value, Mapping):
            raise SchemaViolation("CONTROLLER_DECISION_NOT_OBJECT")
        if set(value) != {"evidence_state", "action_index"}:
            raise SchemaViolation("CONTROLLER_DECISION_FIELD_SET")
        action_index = value["action_index"]
        if (
            isinstance(action_index, bool)
            or not isinstance(action_index, int)
            or not 0 <= action_index < len(action_menu)
        ):
            raise SchemaViolation("CONTROLLER_ACTION_INDEX_INVALID")
        state = validate_evidence_state(
            value["evidence_state"],
            allowed_claim_handles=context.claim_handles,
        )
        lock = ObservedEvidenceLock(observed_evidence)
        if state["covered_claim_handles"] and not lock.observation_ids:
            raise SchemaViolation("COVERED_CLAIMS_WITHOUT_OBSERVED_EVIDENCE")
        action = validate_tool_action(action_menu[action_index])
        return {
            "evidence_state": state,
            "action_index": action_index,
            "action": action,
        }


class SameBackboneReActAdapter(_SameBackboneToolAdapter):
    policy = "react"
    adapter_kind = AdapterKind.SAME_BACKBONE_REACT


class SameBackboneEvidenceSufficiencyAdapter(_SameBackboneToolAdapter):
    policy = "evidence_sufficiency"
    adapter_kind = AdapterKind.SAME_BACKBONE_SUFFICIENCY


class SharedGroundedFinalizer:
    """One finalizer contract shared by RAG, ReAct, sufficiency, and diagnostics."""

    def __init__(self, *, model_binding: ModelBinding) -> None:
        self.model_binding = model_binding

    def prepare(
        self,
        context: AdapterContext,
        *,
        observations: Sequence[Mapping[str, Any]],
        condition: str,
        staged_event_capable: bool,
    ) -> PreparedInvocation:
        lock = ObservedEvidenceLock(observations)
        payload = {
            **context.public_payload(),
            "task": "grounded_finalization",
            "condition": condition,
            "observed_evidence": lock.public_observations(),
            "observed_evidence_lock": lock.fingerprint,
            "output_contract": {
                "schema": "docs/spec/final_answer_schema.json",
                "envelope_addition": "claim_to_citations",
                "observed_citations_only": True,
                "model_authored_answer_required": True,
            },
        }
        return PreparedInvocation(
            adapter_kind=AdapterKind.SHARED_GROUNDED_FINALIZER,
            model_binding=self.model_binding,
            task="grounded_finalization",
            public_payload=payload,
            max_new_tokens=context.budget.max_new_tokens_per_call,
            context_cap_processor_tokens=(
                context.budget.context_cap_processor_tokens
            ),
            staged_event_capable=staged_event_capable,
        )

    def parse_and_validate(
        self,
        raw: bytes | str,
        *,
        context: AdapterContext,
        observations: Sequence[Mapping[str, Any]],
        provenance: OutputProvenance,
    ) -> dict[str, Any]:
        value = parse_strict_json(raw, maximum_bytes=64_000)
        return validate_final_answer_envelope(
            value,
            claim_handles=context.claim_handles,
            evidence_lock=ObservedEvidenceLock(observations),
            provenance=provenance,
        )


class EvidenceBundleAdapter:
    """Oracle-complete and partial-evidence generator diagnostic interface."""

    def __init__(
        self,
        *,
        finalizer: SharedGroundedFinalizer,
        bundle_kind: AdapterKind,
    ) -> None:
        if bundle_kind not in {
            AdapterKind.ORACLE_EVIDENCE,
            AdapterKind.PARTIAL_EVIDENCE,
        }:
            raise ValueError("bundle kind must be oracle or partial")
        self.finalizer = finalizer
        self.bundle_kind = bundle_kind

    def prepare(
        self,
        context: AdapterContext,
        *,
        observations: Sequence[Mapping[str, Any]],
        complete_claim_handles: Sequence[str],
    ) -> PreparedInvocation:
        supplied = set(complete_claim_handles)
        required = set(context.claim_handles)
        if self.bundle_kind is AdapterKind.ORACLE_EVIDENCE:
            if supplied != required:
                raise SchemaViolation("ORACLE_BUNDLE_NOT_COMPLETE")
            condition = "oracle_complete_evidence"
        else:
            if not supplied < required:
                raise SchemaViolation("PARTIAL_BUNDLE_NOT_PROPER_SUBSET")
            condition = "partial_evidence"
        invocation = self.finalizer.prepare(
            context,
            observations=observations,
            condition=condition,
            staged_event_capable=False,
        )
        payload = dict(invocation.public_payload)
        payload["diagnostic_bundle_kind"] = self.bundle_kind
        return PreparedInvocation(
            adapter_kind=self.bundle_kind,
            model_binding=invocation.model_binding,
            task=invocation.task,
            public_payload=payload,
            max_new_tokens=invocation.max_new_tokens,
            context_cap_processor_tokens=(
                invocation.context_cap_processor_tokens
            ),
            staged_event_capable=False,
        )


def default_public_belief_state() -> dict[str, Any]:
    """Neutral structural state; never used to generate or replace an answer."""

    return {
        "p_sufficient": 0.0,
        "verdict": "uncertain",
        "missing_modality_probabilities": {
            "vision": 0.0,
            "speech": 0.0,
            "ambient": 0.0,
        },
        "missing_hop_types": [],
        "missingness_cause_probabilities": {
            "source_evidence_absent": 0.0,
            "evidence_in_source_but_inaccessible": 0.0,
            "evidence_accessible_but_not_found": 0.0,
            "not_missing": 0.0,
            "uncertain": 1.0,
        },
        "next_action_rationale": "",
    }


def build_canonical_agent_action(
    context: AdapterContext,
    *,
    request_id: str,
    step_index: int,
    canonical_belief_state: Mapping[str, Any],
    selected_action: Mapping[str, Any],
    belief_state_model_authored: bool,
    final_answer: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Losslessly wrap model-authored state/action in the canonical schema.

    The function refuses to derive the canonical belief state from the
    six-field diagnostic state.  If ``finalize`` is selected, the caller must
    supply the separately validated, model-authored canonical final answer.
    """

    if not belief_state_model_authored:
        raise SchemaViolation("CANONICAL_BELIEF_STATE_NOT_MODEL_AUTHORED")
    action = validate_tool_action(selected_action)
    if action["tool"] == "finalize":
        if final_answer is None:
            raise SchemaViolation("FINALIZE_WITHOUT_MODEL_AUTHORED_FINAL")
        action = {"tool": "finalize", "arguments": copy.deepcopy(final_answer)}
    elif final_answer is not None:
        raise SchemaViolation("NONFINAL_ACTION_WITH_FINAL_ANSWER")
    envelope = {
        "protocol_version": "0.2.0",
        "episode_id": context.episode_id,
        "request_id": request_id,
        "step_index": step_index,
        "belief_state": copy.deepcopy(dict(canonical_belief_state)),
        "action": action,
    }
    return validate_agent_action(envelope)


def _require_same_snapshot(
    controller: ModelBinding, finalizer: ModelBinding
) -> None:
    controller_identity = (
        controller.repo_id,
        controller.revision,
        controller.resolved_processor_revision,
        controller.resolved_tokenizer_revision,
    )
    finalizer_identity = (
        finalizer.repo_id,
        finalizer.revision,
        finalizer.resolved_processor_revision,
        finalizer.resolved_tokenizer_revision,
    )
    if controller_identity != finalizer_identity:
        raise StrongBaselineError("SAME_BACKBONE_SNAPSHOT_REQUIRED")
