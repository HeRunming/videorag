"""Strict parsing and semantic validation for public adapter outputs."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .errors import SchemaViolation
from .security import (
    ObservedEvidenceLock,
    OutputProvenance,
    assert_public_surface,
)

EVIDENCE_STATE_FIELDS = (
    "p_sufficient",
    "covered_claim_handles",
    "missing_modalities",
    "missing_hops",
    "missingness_cause",
    "recovery_intent",
)
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
RECOVERY_INTENTS = (
    "none",
    "search_vision",
    "search_speech",
    "search_ambient",
    "observe_pointer",
    "check_channel_status",
    "retry_restored_route",
    "finalize_answer",
    "finalize_abstain",
)


class _DuplicateKey(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise _DuplicateKey(key)
        value[key] = child
    return value


def _reject_nonfinite(_: str) -> None:
    raise ValueError("non-finite JSON number")


def parse_strict_json(raw: bytes | str, *, maximum_bytes: int) -> Any:
    """Parse exactly one UTF-8 JSON value with no coercion or duplicate keys."""

    if isinstance(raw, str):
        encoded = raw.encode("utf-8")
    elif isinstance(raw, bytes):
        encoded = raw
    else:
        raise TypeError("model output must be UTF-8 bytes or text")
    if len(encoded) > maximum_bytes:
        raise SchemaViolation("MODEL_OUTPUT_TOO_LARGE")
    try:
        text = encoded.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SchemaViolation("MODEL_OUTPUT_INVALID_UTF8") from exc
    stripped = text.strip(" \t\r\n")
    if not stripped:
        raise SchemaViolation("MODEL_OUTPUT_EMPTY")
    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )
    try:
        value, end = decoder.raw_decode(text, len(text) - len(text.lstrip()))
    except _DuplicateKey as exc:
        raise SchemaViolation("MODEL_OUTPUT_DUPLICATE_KEY") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise SchemaViolation("MODEL_OUTPUT_MALFORMED_JSON") from exc
    if text[end:].strip(" \t\r\n"):
        raise SchemaViolation("MODEL_OUTPUT_TRAILING_CONTENT")
    assert_public_surface(value)
    return value


def _require_exact_keys(
    value: Mapping[str, Any], required: set[str], *, name: str
) -> None:
    if set(value) != required:
        raise SchemaViolation(
            f"{name}_FIELD_SET_MISMATCH",
            details={"actual": sorted(value), "required": sorted(required)},
        )


def _canonical_subset(
    value: Any, allowed: Sequence[str], *, name: str
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise SchemaViolation(f"{name}_TYPE")
    if len(set(value)) != len(value):
        raise SchemaViolation(f"{name}_DUPLICATE")
    if any(item not in allowed for item in value):
        raise SchemaViolation(f"{name}_ENUM")
    expected = [item for item in allowed if item in set(value)]
    if value != expected:
        raise SchemaViolation(f"{name}_NONCANONICAL_ORDER")
    return list(value)


def validate_evidence_state(
    value: Any, *, allowed_claim_handles: Sequence[str]
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaViolation("EVIDENCE_STATE_NOT_OBJECT")
    _require_exact_keys(value, set(EVIDENCE_STATE_FIELDS), name="EVIDENCE_STATE")
    p_sufficient = value["p_sufficient"]
    if isinstance(p_sufficient, bool) or not isinstance(
        p_sufficient, (int, float)
    ):
        raise SchemaViolation("P_SUFFICIENT_TYPE")
    if float(p_sufficient) not in {0.0, 0.25, 0.5, 0.75, 1.0}:
        raise SchemaViolation("P_SUFFICIENT_ENUM")
    covered = _canonical_subset(
        value["covered_claim_handles"],
        allowed_claim_handles,
        name="COVERED_CLAIMS",
    )
    missing_modalities = _canonical_subset(
        value["missing_modalities"], MODALITIES, name="MISSING_MODALITIES"
    )
    missing_hops = _canonical_subset(
        value["missing_hops"], HOPS, name="MISSING_HOPS"
    )
    missingness_cause = value["missingness_cause"]
    recovery_intent = value["recovery_intent"]
    if missingness_cause not in CAUSES:
        raise SchemaViolation("MISSINGNESS_CAUSE_ENUM")
    if recovery_intent not in RECOVERY_INTENTS:
        raise SchemaViolation("RECOVERY_INTENT_ENUM")
    if set(covered) == set(allowed_claim_handles) and allowed_claim_handles:
        if missing_modalities or missing_hops:
            raise SchemaViolation("FULL_COVERAGE_WITH_MISSING_REQUIREMENT")
        if missingness_cause != "not_missing":
            raise SchemaViolation("FULL_COVERAGE_WITH_MISSINGNESS")
    return {
        "p_sufficient": float(p_sufficient),
        "covered_claim_handles": covered,
        "missing_modalities": missing_modalities,
        "missing_hops": missing_hops,
        "missingness_cause": missingness_cause,
        "recovery_intent": recovery_intent,
    }


def _schema_root(repo_root: str | Path | None = None) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()
    return Path(__file__).resolve().parents[2]


def _load_schema(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SchemaViolation("CANONICAL_SCHEMA_NOT_OBJECT")
    return value


def _raise_schema_errors(
    validator: Draft202012Validator, value: Any, *, code: str
) -> None:
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        first = errors[0]
        raise SchemaViolation(
            code,
            details={
                "path": ".".join(str(part) for part in first.absolute_path),
                "message": first.message,
            },
        )


def validate_agent_action(
    value: Any, *, repo_root: str | Path | None = None
) -> dict[str, Any]:
    """Validate the full canonical agent-action envelope."""

    assert_public_surface(value)
    root = _schema_root(repo_root)
    action_schema = _load_schema(root / "docs/spec/agent_action_schema.json")
    final_schema = _load_schema(root / "docs/spec/final_answer_schema.json")
    registry = Registry().with_resource(
        final_schema["$id"], Resource.from_contents(final_schema)
    )
    validator = Draft202012Validator(action_schema, registry=registry)
    _raise_schema_errors(validator, value, code="AGENT_ACTION_SCHEMA_INVALID")
    action = value["action"]
    if action["tool"].startswith("search_") and action["arguments"]["top_k"] != 5:
        raise SchemaViolation("SEARCH_TOP_K_NOT_FROZEN")
    interval = action.get("arguments", {}).get("interval")
    if isinstance(interval, Mapping) and interval["end_s"] <= interval["start_s"]:
        raise SchemaViolation("ACTION_INTERVAL_INVALID")
    return copy.deepcopy(dict(value))


def validate_tool_action(value: Any) -> dict[str, Any]:
    """Validate one model-visible tool call.

    Non-final calls are exactly the action objects embedded in
    ``agent_action_schema.json``.  ``finalize`` is represented by an empty
    marker here because its model-authored arguments are produced by the
    separate canonical final-answer call.
    """

    assert_public_surface(value)
    if not isinstance(value, Mapping):
        raise SchemaViolation("TOOL_ACTION_NOT_OBJECT")
    _require_exact_keys(value, {"tool", "arguments"}, name="TOOL_ACTION")
    tool = value["tool"]
    arguments = value["arguments"]
    if not isinstance(arguments, Mapping):
        raise SchemaViolation("TOOL_ARGUMENTS_NOT_OBJECT")
    if tool in {"search_visual", "search_ambient_audio", "search_speech"}:
        required = {
            "query",
            "top_k",
            "time_range",
            "exclude_result_ids",
        }
        if tool == "search_speech":
            required.add("speaker_hint")
        _require_exact_keys(arguments, required, name="SEARCH_ARGUMENTS")
        if (
            not isinstance(arguments["query"], str)
            or not arguments["query"].strip()
            or len(arguments["query"]) > 500
        ):
            raise SchemaViolation("SEARCH_QUERY_INVALID")
        if arguments["top_k"] != 5:
            raise SchemaViolation("SEARCH_TOP_K_NOT_FROZEN")
        _validate_interval(arguments["time_range"], name="SEARCH_TIME_RANGE")
        excluded = arguments["exclude_result_ids"]
        if (
            not isinstance(excluded, list)
            or any(not isinstance(item, str) for item in excluded)
            or len(set(excluded)) != len(excluded)
        ):
            raise SchemaViolation("SEARCH_EXCLUSIONS_INVALID")
        if tool == "search_speech":
            hint = arguments["speaker_hint"]
            if hint is not None and (
                not isinstance(hint, str) or len(hint) > 100
            ):
                raise SchemaViolation("SPEAKER_HINT_INVALID")
    elif tool == "inspect_clip":
        _require_exact_keys(
            arguments,
            {"interval", "include_video", "include_audio"},
            name="INSPECT_ARGUMENTS",
        )
        _validate_interval(arguments["interval"], name="INSPECT_INTERVAL")
        if not isinstance(arguments["include_video"], bool) or not isinstance(
            arguments["include_audio"], bool
        ):
            raise SchemaViolation("INSPECT_FLAGS_INVALID")
        if not arguments["include_video"] and not arguments["include_audio"]:
            raise SchemaViolation("INSPECT_EMPTY_MODALITY")
    elif tool == "read_transcript":
        _require_exact_keys(
            arguments,
            {"interval", "source", "include_word_timestamps"},
            name="TRANSCRIPT_ARGUMENTS",
        )
        _validate_interval(arguments["interval"], name="TRANSCRIPT_INTERVAL")
        if arguments["source"] not in {"asr", "subtitle"}:
            raise SchemaViolation("TRANSCRIPT_SOURCE_INVALID")
        if not isinstance(arguments["include_word_timestamps"], bool):
            raise SchemaViolation("TRANSCRIPT_TIMESTAMP_FLAG_INVALID")
    elif tool == "get_channel_status":
        _require_exact_keys(arguments, {"channels"}, name="STATUS_ARGUMENTS")
        channels = arguments["channels"]
        allowed = {"visual", "speech", "ambient", "clip", "transcript"}
        if (
            not isinstance(channels, list)
            or not channels
            or any(item not in allowed for item in channels)
            or len(set(channels)) != len(channels)
        ):
            raise SchemaViolation("STATUS_CHANNELS_INVALID")
    elif tool == "finalize":
        if arguments:
            raise SchemaViolation("FINALIZE_MARKER_ARGUMENTS_NOT_EMPTY")
    else:
        raise SchemaViolation("UNKNOWN_CANONICAL_TOOL")
    return copy.deepcopy(dict(value))


def _validate_interval(value: Any, *, name: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise SchemaViolation(f"{name}_NOT_OBJECT")
    _require_exact_keys(value, {"start_s", "end_s"}, name=name)
    start = value["start_s"]
    end = value["end_s"]
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, (int, float))
        or not isinstance(end, (int, float))
        or float(start) < 0
        or float(end) <= float(start)
    ):
        raise SchemaViolation(f"{name}_INVALID")
    return {"start_s": float(start), "end_s": float(end)}


def validate_final_answer_envelope(
    value: Any,
    *,
    claim_handles: Sequence[str],
    evidence_lock: ObservedEvidenceLock,
    provenance: OutputProvenance,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate canonical final answer plus its redundant citation map."""

    assert_public_surface(value)
    if not isinstance(value, Mapping):
        raise SchemaViolation("FINAL_ENVELOPE_NOT_OBJECT")
    _require_exact_keys(
        value,
        {"final_answer", "claim_to_citations"},
        name="FINAL_ENVELOPE",
    )
    final = value["final_answer"]
    citation_map = value["claim_to_citations"]
    root = _schema_root(repo_root)
    final_schema = _load_schema(root / "docs/spec/final_answer_schema.json")
    _raise_schema_errors(
        Draft202012Validator(final_schema),
        final,
        code="FINAL_ANSWER_SCHEMA_INVALID",
    )
    if not isinstance(citation_map, Mapping):
        raise SchemaViolation("CLAIM_TO_CITATIONS_NOT_OBJECT")
    provenance.require_model_authored_answer()
    allowed = set(claim_handles)
    seen: set[str] = set()
    derived_map: dict[str, list[str]] = {}
    for claim in final["claims"]:
        handle = claim["registered_claim_id"]
        if handle not in allowed or handle in seen:
            raise SchemaViolation("CLAIM_HANDLE_UNKNOWN_OR_DUPLICATE")
        seen.add(handle)
        citations = claim["citations"]
        if not citations:
            raise SchemaViolation("ANSWER_CLAIM_WITHOUT_CITATION")
        ids: list[str] = []
        for citation in citations:
            evidence_lock.validate_citation(citation)
            ids.append(citation["observation_id"])
        if len(set(ids)) != len(ids):
            raise SchemaViolation("CLAIM_CITATION_DUPLICATE")
        derived_map[str(handle)] = ids
    if dict(citation_map) != derived_map:
        raise SchemaViolation("CLAIM_TO_CITATIONS_MISMATCH")
    mode = final["answer_mode"]
    if mode == "answer":
        if seen != allowed:
            raise SchemaViolation("ANSWER_MISSING_REQUIRED_CLAIMS")
        if final["verdict"] != "sufficient" or final["p_sufficient"] < 0.5:
            raise SchemaViolation("ANSWER_SUFFICIENCY_INCONSISTENT")
        if not final["natural_language_answer"].strip():
            raise SchemaViolation("ANSWER_TEXT_EMPTY")
    elif mode == "abstain":
        if final["claims"] or final["natural_language_answer"].strip():
            raise SchemaViolation("ABSTAIN_WITH_ANSWER_CONTENT")
        if final["verdict"] == "sufficient" or final["p_sufficient"] > 0.5:
            raise SchemaViolation("ABSTAIN_SUFFICIENCY_INCONSISTENT")
    else:
        if not final["claims"]:
            raise SchemaViolation("PARTIAL_ANSWER_WITHOUT_CLAIMS")
        if seen == allowed:
            raise SchemaViolation("PARTIAL_ANSWER_HAS_FULL_COVERAGE")
    return copy.deepcopy(dict(value))
