from __future__ import annotations

import pytest

from av_trace_controller_v2.parser import (
    ControllerOutputError,
    parse_action_output,
    parse_state_output,
)

from .fixtures import VALID_STATE


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'{"action_index":1,"action_index":0}', "DUPLICATE_KEY"),
        (b'{"action_index":1} trailing', "TRAILING_CONTENT"),
        (b'```json\\n{"action_index":1}\\n```', "MALFORMED_JSON"),
        (b'{"action_index":true}', "TYPE_MISMATCH"),
        (b'{"action_index":3}', "DYNAMIC_ENUM_VIOLATION"),
    ],
)
def test_action_parser_fails_closed(raw: bytes, code: str) -> None:
    with pytest.raises(ControllerOutputError, match=code) as caught:
        parse_action_output(raw, allowed_action_indices=[0, 1, 2])
    assert caught.value.code == code


def test_action_parser_returns_exact_model_value() -> None:
    value = parse_action_output(
        b' \n{"action_index":2}\t', allowed_action_indices=[0, 1, 2]
    )
    assert value == {"action_index": 2}


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (
            VALID_STATE.replace(
                b'"v2slot.fictional_mark"',
                b'"v2slot.not_public"',
            ),
            "DYNAMIC_ENUM_VIOLATION",
        ),
        (
            VALID_STATE.replace(
                b'["speech"]', b'["speech","speech"]'
            ),
            "DUPLICATE_ARRAY_ITEM",
        ),
        (
            VALID_STATE.replace(
                b'["speech"]', b'["ambient","vision"]'
            ),
            "NONCANONICAL_ARRAY_ORDER",
        ),
        (
            VALID_STATE.replace(
                b'["v2slot.fictional_mark"]',
                b'["v2slot.fictional_color","v2slot.fictional_mark"]',
            ),
            "NONCANONICAL_ARRAY_ORDER",
        ),
        (
            VALID_STATE.replace(b'"p_sufficient":0.5', b'"p_sufficient":0.6'),
            "ENUM_VIOLATION",
        ),
    ],
)
def test_state_parser_enforces_enums_and_canonical_arrays(
    raw: bytes, code: str
) -> None:
    with pytest.raises(ControllerOutputError, match=code):
        parse_state_output(
            raw,
            allowed_claim_handles=[
                "v2slot.fictional_mark",
                "v2slot.fictional_color",
            ],
        )


def test_state_parser_does_not_normalize_or_repair() -> None:
    parsed = parse_state_output(
        VALID_STATE,
        allowed_claim_handles=[
            "v2slot.fictional_mark",
            "v2slot.fictional_color",
        ],
    )
    assert parsed["p_sufficient"] == 0.5
    assert parsed["covered_claim_handles"] == ["v2slot.fictional_mark"]
