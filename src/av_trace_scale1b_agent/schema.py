"""Strict public schemas for learned model decisions and finalization."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

PRIVATE_MARKERS = ("noaa01-", "claim.r", "e.r", "seg.", "cand-")
MODALITIES = ("vision", "speech", "ambient")
HOPS = (
    "entity_identity",
    "event_detection",
    "speech_content",
    "ambient_event",
    "temporal_order",
    "cross_modal_binding",
    "causal_link",
    "state_change",
    "comparison",
    "counting",
    "other",
)
CAUSES = (
    "source_evidence_absent",
    "evidence_in_source_but_inaccessible",
    "evidence_accessible_but_not_found",
    "not_missing",
    "uncertain",
)
VERDICTS = ("answer", "insufficient", "access_failure", "abstain")


class PublicSchemaError(ValueError):
    """Raised when model-authored public JSON fails closed."""


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicSchemaError(f"{name}_NOT_OBJECT")
    return value


def _exact_keys(
    value: Mapping[str, Any], required: set[str], name: str
) -> None:
    if set(value) != required:
        raise PublicSchemaError(
            f"{name}_FIELDS:{sorted(value)}!={sorted(required)}"
        )


def _probability(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PublicSchemaError(f"{name}_NOT_NUMBER")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise PublicSchemaError(f"{name}_OUT_OF_RANGE")
    return result


def _short_text(value: Any, name: str, limit: int, *, nonempty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (nonempty and not value.strip()):
        raise PublicSchemaError(f"{name}_INVALID")
    if any(marker in value for marker in PRIVATE_MARKERS):
        raise PublicSchemaError(f"{name}_PRIVATE_IDENTIFIER")
    return value


def _string_list(
    value: Any, name: str, allowed: set[str] | None = None
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PublicSchemaError(f"{name}_NOT_STRING_LIST")
    if len(set(value)) != len(value):
        raise PublicSchemaError(f"{name}_DUPLICATE")
    if allowed is not None and not set(value) <= allowed:
        raise PublicSchemaError(f"{name}_UNKNOWN_VALUE")
    return list(value)


def validate_finalization(
    value: Any,
    *,
    claim_handles: set[str],
    observation_ids: set[str],
) -> dict[str, Any]:
    """Validate and normalize a learned finalization.

    Evaluator-private IDs are never accepted. Mapping public slots to private
    claims happens only after this function succeeds.
    """

    obj = _object(value, "FINAL")
    required = {
        "verdict",
        "answer_text",
        "asserted_claims",
        "claim_to_citations",
        "missing_modalities",
        "missing_hops",
        "missingness_cause",
        "p_sufficient",
        "recovery_intent",
        "stop_rationale",
    }
    _exact_keys(obj, required, "FINAL")
    verdict = obj["verdict"]
    if verdict not in VERDICTS:
        raise PublicSchemaError("FINAL_VERDICT")
    answer = _short_text(obj["answer_text"], "ANSWER_TEXT", 1200)
    p_sufficient = _probability(obj["p_sufficient"], "P_SUFFICIENT")
    missing_modalities = _string_list(
        obj["missing_modalities"], "MISSING_MODALITIES", set(MODALITIES)
    )
    missing_hops = _string_list(obj["missing_hops"], "MISSING_HOPS", set(HOPS))
    if obj["missingness_cause"] not in CAUSES:
        raise PublicSchemaError("MISSINGNESS_CAUSE")
    recovery_intent = _short_text(
        obj["recovery_intent"], "RECOVERY_INTENT", 300
    )
    stop_rationale = _short_text(
        obj["stop_rationale"], "STOP_RATIONALE", 300, nonempty=True
    )
    assertions = obj["asserted_claims"]
    citation_map = _object(obj["claim_to_citations"], "CLAIM_TO_CITATIONS")
    if not isinstance(assertions, list) or len(assertions) > 32:
        raise PublicSchemaError("ASSERTED_CLAIMS_INVALID")
    normalized_assertions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(assertions):
        assertion = _object(raw, f"ASSERTION_{index}")
        _exact_keys(assertion, {"claim_handle", "text", "citations"}, f"ASSERTION_{index}")
        handle = assertion["claim_handle"]
        if handle not in claim_handles or handle in seen:
            raise PublicSchemaError(f"ASSERTION_{index}_UNKNOWN_OR_DUPLICATE_HANDLE")
        seen.add(handle)
        text = _short_text(assertion["text"], f"ASSERTION_{index}_TEXT", 600, nonempty=True)
        citations = _string_list(assertion["citations"], f"ASSERTION_{index}_CITATIONS")
        if not citations:
            raise PublicSchemaError(f"ASSERTION_{index}_CITATIONS_EMPTY")
        if any(item not in observation_ids for item in citations):
            raise PublicSchemaError(f"ASSERTION_{index}_UNKNOWN_CITATION")
        if list(citation_map.get(handle, [])) != citations:
            raise PublicSchemaError(f"ASSERTION_{index}_CITATION_MAP_MISMATCH")
        normalized_assertions.append(
            {"claim_handle": handle, "text": text, "citations": citations}
        )
    if set(citation_map) != seen:
        raise PublicSchemaError("CLAIM_TO_CITATIONS_HANDLE_SET_MISMATCH")
    if verdict == "answer":
        if not answer.strip() or not normalized_assertions:
            raise PublicSchemaError("ANSWER_WITHOUT_CONTENT")
        if seen != claim_handles:
            raise PublicSchemaError("ANSWER_WITHOUT_ALL_REQUIRED_CLAIMS")
        if missing_modalities or missing_hops:
            raise PublicSchemaError("ANSWER_WITH_MISSING_REQUIREMENTS")
        if obj["missingness_cause"] != "not_missing":
            raise PublicSchemaError("ANSWER_WITH_MISSINGNESS_CAUSE")
        if p_sufficient < 0.5:
            raise PublicSchemaError("ANSWER_WITH_LOW_SUFFICIENCY")
    else:
        if normalized_assertions:
            raise PublicSchemaError("NONANSWER_WITH_ASSERTIONS")
        if answer.strip():
            raise PublicSchemaError("NONANSWER_WITH_ANSWER_TEXT")
        if not missing_modalities and not missing_hops:
            raise PublicSchemaError("NONANSWER_WITHOUT_MISSING_REQUIREMENT")
        if obj["missingness_cause"] == "not_missing":
            raise PublicSchemaError("NONANSWER_WITH_NOT_MISSING")
        if p_sufficient > 0.5:
            raise PublicSchemaError("NONANSWER_WITH_HIGH_SUFFICIENCY")
    return {
        "verdict": verdict,
        "answer_text": answer,
        "asserted_claims": normalized_assertions,
        "claim_to_citations": {key: list(citation_map[key]) for key in sorted(citation_map)},
        "missing_modalities": missing_modalities,
        "missing_hops": missing_hops,
        "missingness_cause": obj["missingness_cause"],
        "p_sufficient": p_sufficient,
        "recovery_intent": recovery_intent,
        "stop_rationale": stop_rationale,
    }


def validate_controller_decision(
    value: Any,
    *,
    claim_handles: set[str],
    pointer_ids: set[str],
    observation_ids: set[str],
    available_tools: set[str],
    action_menu: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    obj = _object(value, "DECISION")
    _exact_keys(obj, {"public_state", "action_index"}, "DECISION")
    state = _object(obj["public_state"], "PUBLIC_STATE")
    _exact_keys(
        state,
        {
            "p_sufficient",
            "covered_claim_handles",
            "missing_modalities",
            "missing_hops",
            "missingness_cause",
            "recovery_intent",
        },
        "PUBLIC_STATE",
    )
    covered = _string_list(state["covered_claim_handles"], "COVERED_CLAIMS")
    if not set(covered) <= claim_handles:
        raise PublicSchemaError("COVERED_CLAIMS_UNKNOWN")
    if covered and not observation_ids:
        raise PublicSchemaError("COVERED_CLAIMS_WITHOUT_OBSERVATIONS")
    public_state = {
        "p_sufficient": _probability(state["p_sufficient"], "P_SUFFICIENT"),
        "covered_claim_handles": covered,
        "missing_modalities": _string_list(
            state["missing_modalities"], "MISSING_MODALITIES", set(MODALITIES)
        ),
        "missing_hops": _string_list(state["missing_hops"], "MISSING_HOPS", set(HOPS)),
        "missingness_cause": state["missingness_cause"],
        "recovery_intent": _short_text(
            state["recovery_intent"], "RECOVERY_INTENT", 300
        ),
    }
    if public_state["missingness_cause"] not in CAUSES:
        raise PublicSchemaError("MISSINGNESS_CAUSE")
    if set(covered) == claim_handles and claim_handles:
        if public_state["missing_modalities"] or public_state["missing_hops"]:
            raise PublicSchemaError("FULL_COVERAGE_WITH_MISSING_REQUIREMENTS")
        if public_state["missingness_cause"] != "not_missing":
            raise PublicSchemaError("FULL_COVERAGE_WITH_MISSINGNESS_CAUSE")
    if action_menu is None or not action_menu:
        raise PublicSchemaError("ACTION_MENU_MISSING")
    action_index = obj["action_index"]
    if (
        isinstance(action_index, bool)
        or not isinstance(action_index, int)
        or not 0 <= action_index < len(action_menu)
    ):
        raise PublicSchemaError("ACTION_INDEX_INVALID")
    action = _object(action_menu[action_index], "ACTION")
    if "type" not in action:
        raise PublicSchemaError("ACTION_TYPE_MISSING")
    kind = action["type"]
    if kind == "search":
        _exact_keys(action, {"type", "modality", "query", "top_k"}, "SEARCH")
        modality = action["modality"]
        tool = {
            "vision": "search_visual",
            "speech": "search_speech",
            "ambient": "search_ambient_audio",
        }.get(modality)
        if tool is None or tool not in available_tools:
            raise PublicSchemaError("SEARCH_MODALITY_UNAVAILABLE")
        query = _short_text(action["query"], "SEARCH_QUERY", 500, nonempty=True)
        top_k = action["top_k"]
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 20:
            raise PublicSchemaError("SEARCH_TOP_K")
        normalized_action = {
            "type": "search",
            "modality": modality,
            "query": query,
            "top_k": top_k,
        }
    elif kind == "observe":
        _exact_keys(action, {"type", "pointer_id"}, "OBSERVE")
        if action["pointer_id"] not in pointer_ids:
            raise PublicSchemaError("UNKNOWN_POINTER")
        normalized_action = dict(action)
    elif kind == "status":
        _exact_keys(action, {"type", "modalities"}, "STATUS")
        normalized_action = {
            "type": "status",
            "modalities": _string_list(
                action["modalities"], "STATUS_MODALITIES", set(MODALITIES)
            ),
        }
        if not normalized_action["modalities"]:
            raise PublicSchemaError("STATUS_MODALITIES_EMPTY")
    elif kind == "finalize":
        _exact_keys(action, {"type"}, "FINALIZE")
        normalized_action = {"type": "finalize"}
    else:
        raise PublicSchemaError("UNKNOWN_ACTION_TYPE")
    return {
        "public_state": public_state,
        "action_index": action_index,
        "action": normalized_action,
    }


def extract_json_object(text: str) -> Any:
    """Parse strict JSON, permitting only surrounding whitespace."""

    stripped = text.strip()
    if not stripped:
        raise PublicSchemaError("EMPTY_MODEL_OUTPUT")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise PublicSchemaError("MALFORMED_MODEL_JSON") from exc


def finalization_schema_prompt(
    *,
    claim_handles: list[str] | None = None,
    observation_ids: list[str] | None = None,
) -> dict[str, Any]:
    claims = list(claim_handles or [])
    observations = list(observation_ids or [])
    schema: dict[str, Any] = {
        "exact_keys": [
            "verdict",
            "answer_text",
            "asserted_claims",
            "claim_to_citations",
            "missing_modalities",
            "missing_hops",
            "missingness_cause",
            "p_sufficient",
            "recovery_intent",
            "stop_rationale",
        ],
        "nonanswer_example": {
            "verdict": "insufficient",
            "answer_text": "",
            "asserted_claims": [],
            "claim_to_citations": {},
            "missing_modalities": ["speech"],
            "missing_hops": ["speech_content"],
            "missingness_cause": "evidence_accessible_but_not_found",
            "p_sufficient": 0.1,
            "recovery_intent": "Search speech evidence.",
            "stop_rationale": "Visible evidence is insufficient.",
        },
        "answer_invariants": [
            "assert every allowed claim_handle exactly once",
            "copy one or more exact visible observation_id values for every claim",
            "make claim_to_citations exactly match asserted_claims",
            "use empty missing lists, not_missing, and empty recovery_intent",
        ],
        "nonanswer_invariants": [
            "answer_text is empty",
            "asserted_claims is empty and claim_to_citations is empty",
            "name at least one missing modality or missing hop",
            "missingness_cause is not not_missing and p_sufficient is at most 0.5",
        ],
        "allowed_claim_handles": claims,
        "allowed_observation_ids": observations,
    }
    if claims and observations:
        schema["answer_example_shape"] = {
            "verdict": "answer",
            "answer_text": "concise answer grounded in observations",
            "asserted_claims": [
                {
                    "claim_handle": claim,
                    "text": f"supported content for {claim}",
                    "citations": [observations[index % len(observations)]],
                }
                for index, claim in enumerate(claims)
            ],
            "claim_to_citations": {
                claim: [observations[index % len(observations)]]
                for index, claim in enumerate(claims)
            },
            "missing_modalities": [],
            "missing_hops": [],
            "missingness_cause": "not_missing",
            "p_sufficient": 0.9,
            "recovery_intent": "",
            "stop_rationale": "The cited evidence supports the answer.",
        }
    else:
        schema["answer_not_permitted_without_visible_observation"] = True
    return schema


def controller_schema_prompt(
    action_menu: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "exact_top_level_keys": ["public_state", "action_index"],
        "public_state_example": {
            "public_state": {
                "p_sufficient": 0.1,
                "covered_claim_handles": [],
                "missing_modalities": ["speech"],
                "missing_hops": ["speech_content"],
                "missingness_cause": "evidence_accessible_but_not_found",
                "recovery_intent": "Search speech evidence.",
            }
        }["public_state"],
        "public_state_exact_keys": [
            "p_sufficient",
            "covered_claim_handles",
            "missing_modalities",
            "missing_hops",
            "missingness_cause",
            "recovery_intent",
        ],
        "allowed_missing_modalities": ["vision", "speech", "ambient"],
        "allowed_missing_hops": list(HOPS),
        "allowed_missingness_causes": list(CAUSES),
        "action_menu": [
            {"action_index": index, "action": dict(action)}
            for index, action in enumerate(action_menu or [])
        ],
        "instruction": (
            "Choose exactly one action_index from action_menu. Do not copy the "
            "action object into the response."
        ),
        "state_invariants": [
            "covered_claim_handles must be supported by visible citable observations",
            "when every claim is covered, use empty missing lists and not_missing",
            "when evidence is incomplete, identify the still-missing modality or hop",
        ],
    }
