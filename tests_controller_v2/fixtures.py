from __future__ import annotations

from typing import Any


def fictional_case(*, finalize_index: int | None = None) -> dict[str, Any]:
    menu = [
        {
            "type": "search",
            "modality": "vision",
            "query": "clockwork orchard copper leaf",
            "top_k": 2,
        },
        {"type": "observe", "pointer_id": "fixture.ptr.copper_leaf"},
        {"type": "finalize"},
    ]
    if finalize_index is not None:
        final = menu.pop(2)
        menu.insert(finalize_index, final)
    return {
        "case_id": "fixture-clockwork-orchard",
        "policy": "evidence_sufficiency",
        "question": "Which mark is painted on the fictional copper leaf?",
        "public_claim_slots": [
            {
                "claim_handle": "v2slot.fictional_mark",
                "description": "The fictional painted mark.",
            },
            {
                "claim_handle": "v2slot.fictional_color",
                "description": "The fictional paint color.",
            },
        ],
        "known_pointers": [
            {
                "pointer_id": "fixture.ptr.copper_leaf",
                "modality": "vision",
                "preview": "A fabricated close view of a copper leaf.",
            }
        ],
        "citable_observations": [
            {
                "observation_id": "fixture.obs.copper_leaf",
                "modality": "vision",
                "content": "A wholly fictional leaf carries a blue spiral.",
                "citable": True,
            }
        ],
        "recent_public_events": [],
        "no_progress_rounds": 0,
        "remaining_budget": {"steps": 3, "cost": 2.0},
        "action_menu": menu,
        "action_output_contract": {
            "schema_id": (
                "urn:av-trace:schema:controller-v2-action:2.0.0"
            ),
            "allowed_action_indices": list(range(len(menu))),
        },
        "state_output_contract": {
            "schema_id": (
                "urn:av-trace:schema:controller-v2-state:2.0.0"
            ),
            "allowed_claim_handles": [
                "v2slot.fictional_mark",
                "v2slot.fictional_color",
            ],
        },
    }


VALID_STATE = (
    b'{"p_sufficient":0.5,"covered_claim_handles":'
    b'["v2slot.fictional_mark"],"missing_modalities":["speech"],'
    b'"missing_hops":["speech_content"],'
    b'"missingness_cause":"evidence_accessible_but_not_found",'
    b'"recovery_intent":"search_speech"}'
)
