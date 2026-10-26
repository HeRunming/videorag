"""Case-local JSON grammars for controller-v3 classification heads."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def choice_grammar_schema(
    *, allowed_choice_indices: list[int]
) -> dict[str, Any]:
    """Return the complete language for one state classification head."""

    return {
        "type": "object",
        "properties": {
            "choice_index": {
                "type": "integer",
                "enum": list(allowed_choice_indices),
            }
        },
        "required": ["choice_index"],
        "additionalProperties": False,
    }


def action_grammar_schema(
    *, allowed_action_indices: list[int]
) -> dict[str, Any]:
    """Return the native action-index language retained from controller v2."""

    return {
        "type": "object",
        "properties": {
            "action_index": {
                "type": "integer",
                "enum": list(allowed_action_indices),
            }
        },
        "required": ["action_index"],
        "additionalProperties": False,
    }


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()
