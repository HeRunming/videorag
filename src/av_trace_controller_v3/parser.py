"""Fail-closed parser for controller-v3 classification heads."""

from __future__ import annotations

import json
from typing import Any

MAX_OUTPUT_BYTES = 64
JSON_WHITESPACE = " \t\r\n"


class ControllerV3OutputError(ValueError):
    """Stable parser error for a constrained classification output."""

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


def parse_choice_output(
    raw: bytes,
    *,
    allowed_choice_indices: list[int] | tuple[int, ...],
) -> dict[str, int]:
    """Parse exactly ``{"choice_index": N}`` without repair or coercion."""

    if not isinstance(raw, bytes):
        raise TypeError("controller output must be UTF-8 bytes")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise ControllerV3OutputError("OUTPUT_TOO_LARGE")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ControllerV3OutputError("INVALID_UTF8") from exc
    start = 0
    while start < len(text) and text[start] in JSON_WHITESPACE:
        start += 1
    if start == len(text):
        raise ControllerV3OutputError("EMPTY_OUTPUT")
    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )
    try:
        value, end = decoder.raw_decode(text, start)
    except _DuplicateKey as exc:
        raise ControllerV3OutputError("DUPLICATE_KEY") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise ControllerV3OutputError("MALFORMED_JSON") from exc
    if any(character not in JSON_WHITESPACE for character in text[end:]):
        raise ControllerV3OutputError("TRAILING_CONTENT")
    if not isinstance(value, dict):
        raise ControllerV3OutputError("WRONG_TOP_LEVEL_TYPE")
    if set(value) != {"choice_index"}:
        raise ControllerV3OutputError("FIELD_SET_MISMATCH")
    choice_index = value["choice_index"]
    if isinstance(choice_index, bool) or not isinstance(choice_index, int):
        raise ControllerV3OutputError("TYPE_MISMATCH")
    if choice_index not in allowed_choice_indices:
        raise ControllerV3OutputError("DYNAMIC_ENUM_VIOLATION")
    return {"choice_index": choice_index}
