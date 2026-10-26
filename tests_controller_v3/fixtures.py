from __future__ import annotations

from typing import Any


def fictional_case() -> dict[str, Any]:
    handles = ["fixture.slot.mark"]
    return {
        "case_id": "fixture-v3-clockwork-leaf",
        "policy": "evidence_sufficiency",
        "question": "Which mark is painted on the fictional copper leaf?",
        "public_claim_slots": [
            {
                "claim_handle": handles[0],
                "description": "The fictional painted mark.",
            }
        ],
        "known_pointers": [],
        "citable_observations": [
            {
                "observation_id": "fixture.obs.leaf",
                "modality": "vision",
                "content": "The fictional copper leaf has a blue spiral.",
                "citable": True,
            }
        ],
        "recent_public_events": [],
        "no_progress_rounds": 0,
        "remaining_budget": {"steps": 1, "cost": 0.0},
        "action_menu": [{"type": "finalize"}],
        "state_choice_enums": {
            "p_sufficient": [0.0, 1.0],
            "covered_claim_handles": [[], handles],
            "missing_modalities": [[], ["vision"]],
            "missing_hops": [[], ["entity_identity"]],
            "missingness_cause": ["not_missing", "uncertain"],
            "recovery_intent": ["finalize_answer", "finalize_abstain"],
        },
    }
