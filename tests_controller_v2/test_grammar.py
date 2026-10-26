from __future__ import annotations

from pathlib import Path

import xgrammar

from av_trace_controller_v2.schemas import (
    action_grammar_schema,
    state_grammar_schema,
)

ROOT = Path(__file__).resolve().parents[1]


def test_fictional_dynamic_schemas_compile_with_installed_xgrammar() -> None:
    action = action_grammar_schema(
        ROOT / "docs/spec/controller_v2_action_schema.json",
        allowed_action_indices=[0, 1, 2],
    )
    state = state_grammar_schema(
        ROOT / "docs/spec/controller_v2_state_schema.json",
        allowed_claim_handles=[
            "v2slot.fictional_alpha",
            "v2slot.fictional_beta",
        ],
    )
    xgrammar.Grammar.from_json_schema(action, strict_mode=True)
    xgrammar.Grammar.from_json_schema(state, strict_mode=True)
