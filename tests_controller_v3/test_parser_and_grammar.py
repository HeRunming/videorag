from __future__ import annotations

import pytest
import xgrammar

from av_trace_controller_v3.parser import (
    ControllerV3OutputError,
    parse_choice_output,
)
from av_trace_controller_v3.schemas import (
    action_grammar_schema,
    choice_grammar_schema,
)


def test_choice_parser_accepts_only_case_local_index() -> None:
    assert parse_choice_output(
        b'{"choice_index":2}', allowed_choice_indices=[0, 1, 2]
    ) == {"choice_index": 2}
    with pytest.raises(
        ControllerV3OutputError, match="DYNAMIC_ENUM_VIOLATION"
    ):
        parse_choice_output(
            b'{"choice_index":3}', allowed_choice_indices=[0, 1, 2]
        )


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b"", "EMPTY_OUTPUT"),
        (b"[]", "WRONG_TOP_LEVEL_TYPE"),
        (b'{"choice_index":true}', "TYPE_MISMATCH"),
        (b'{"choice_index":0,"extra":1}', "FIELD_SET_MISMATCH"),
        (b'{"choice_index":0} trailing', "TRAILING_CONTENT"),
        (b'{"choice_index":0,"choice_index":1}', "DUPLICATE_KEY"),
    ],
)
def test_choice_parser_is_fail_closed(raw: bytes, code: str) -> None:
    with pytest.raises(ControllerV3OutputError, match=code):
        parse_choice_output(raw, allowed_choice_indices=[0, 1])


def test_case_local_schemas_compile() -> None:
    xgrammar.Grammar.from_json_schema(
        action_grammar_schema(allowed_action_indices=[0, 1, 2]),
        strict_mode=True,
    )
    xgrammar.Grammar.from_json_schema(
        choice_grammar_schema(allowed_choice_indices=[0, 1, 2, 3]),
        strict_mode=True,
    )
