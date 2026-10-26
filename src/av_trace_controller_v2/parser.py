"""Fail-closed parsers for the two controller-v2 model output languages."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

ACTION_MAX_BYTES = 64
STATE_MAX_BYTES = 1024
JSON_WHITESPACE = " \t\r\n"
STATE_FIELDS = (
    "p_sufficient",
    "covered_claim_handles",
    "missing_modalities",
    "missing_hops",
    "missingness_cause",
    "recovery_intent",
)
SUFFICIENCY_BINS = (0.0, 0.25, 0.5, 0.75, 1.0)
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


class ControllerOutputError(ValueError):
    """A stable, fail-closed controller-v2 parser error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _DuplicateKey(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite JSON number")


def _parse_single_json(raw: bytes, *, maximum_bytes: int) -> Any:
    if not isinstance(raw, bytes):
        raise TypeError("controller output must be UTF-8 bytes")
    if len(raw) > maximum_bytes:
        raise ControllerOutputError("OUTPUT_TOO_LARGE")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ControllerOutputError("INVALID_UTF8") from exc
    start = 0
    while start < len(text) and text[start] in JSON_WHITESPACE:
        start += 1
    if start == len(text):
        raise ControllerOutputError("EMPTY_OUTPUT")
    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )
    try:
        value, end = decoder.raw_decode(text, start)
    except _DuplicateKey as exc:
        raise ControllerOutputError("DUPLICATE_KEY") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise ControllerOutputError("MALFORMED_JSON") from exc
    if any(character not in JSON_WHITESPACE for character in text[end:]):
        raise ControllerOutputError("TRAILING_CONTENT")
    return value


def _require_exact_fields(value: Any, required: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ControllerOutputError("WRONG_TOP_LEVEL_TYPE")
    if set(value) != set(required):
        raise ControllerOutputError("FIELD_SET_MISMATCH")
    return value


def _require_string_array(value: Any) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ControllerOutputError("TYPE_MISMATCH")
    if len(set(value)) != len(value):
        raise ControllerOutputError("DUPLICATE_ARRAY_ITEM")
    return value


def _validate_canonical_array(
    value: Any,
    *,
    allowed: tuple[str, ...],
    dynamic: bool = False,
) -> list[str]:
    items = _require_string_array(value)
    allowed_set = set(allowed)
    if any(item not in allowed_set for item in items):
        raise ControllerOutputError(
            "DYNAMIC_ENUM_VIOLATION" if dynamic else "ENUM_VIOLATION"
        )
    expected = [item for item in allowed if item in set(items)]
    if items != expected:
        raise ControllerOutputError("NONCANONICAL_ARRAY_ORDER")
    return items


def parse_action_output(
    raw: bytes,
    *,
    allowed_action_indices: list[int] | tuple[int, ...],
) -> dict[str, Any]:
    """Parse one action-head output without repair, coercion, or normalization."""

    value = _require_exact_fields(
        _parse_single_json(raw, maximum_bytes=ACTION_MAX_BYTES),
        ("action_index",),
    )
    action_index = value["action_index"]
    if isinstance(action_index, bool) or not isinstance(action_index, int):
        raise ControllerOutputError("TYPE_MISMATCH")
    if action_index not in allowed_action_indices:
        raise ControllerOutputError("DYNAMIC_ENUM_VIOLATION")
    return value


def parse_state_output(
    raw: bytes,
    *,
    allowed_claim_handles: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Parse one state-head output without semantic plausibility checks."""

    value = _require_exact_fields(
        _parse_single_json(raw, maximum_bytes=STATE_MAX_BYTES),
        STATE_FIELDS,
    )
    p_sufficient = value["p_sufficient"]
    if isinstance(p_sufficient, bool) or not isinstance(
        p_sufficient, (int, float)
    ):
        raise ControllerOutputError("TYPE_MISMATCH")
    if p_sufficient not in SUFFICIENCY_BINS:
        raise ControllerOutputError("ENUM_VIOLATION")

    _validate_canonical_array(
        value["covered_claim_handles"],
        allowed=tuple(allowed_claim_handles),
        dynamic=True,
    )
    _validate_canonical_array(
        value["missing_modalities"],
        allowed=MODALITIES,
    )
    _validate_canonical_array(value["missing_hops"], allowed=HOPS)

    for field, allowed in (
        ("missingness_cause", CAUSES),
        ("recovery_intent", RECOVERY_INTENTS),
    ):
        item = value[field]
        if not isinstance(item, str):
            raise ControllerOutputError("TYPE_MISMATCH")
        if item not in allowed:
            raise ControllerOutputError("ENUM_VIOLATION")
    return value


Parser = Callable[..., dict[str, Any]]
