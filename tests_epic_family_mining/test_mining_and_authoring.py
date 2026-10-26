from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pytest

from av_trace_epic_family_mining import (
    EpicIndexInputs,
    HashFixtureEncoder,
    HumanObservation,
    PrescreenBundle,
    PrescreenSourceGate,
    build_candidate_registry,
    mine_initial_machine_leads,
    validate_candidate_registry,
)


class FixtureEncoder:
    def encode(self, query: str, dimension: int) -> np.ndarray:
        del query
        vector = np.zeros(dimension, dtype=np.float32)
        vector[0] = 1.0
        return vector


def _hex(first: float, second: float = 0.0) -> str:
    vector = np.asarray([first, second, 0.0, 0.0], dtype=np.float32)
    vector /= np.linalg.norm(vector)
    return vector.astype("<f2").tobytes().hex()


def _inputs() -> EpicIndexInputs:
    source_ids = ("P27_101", "P28_103")
    vision = []
    ambient = []
    speech = []
    routing = []
    for source_index, source_id in enumerate(source_ids):
        for index, start_us in enumerate((0, 20_000_000, 50_000_000)):
            segment_id = f"seg.{source_id}.fine.{index}"
            cells = [f"cell.{source_id}.{index}", f"cell.{source_id}.{index + 1}"]
            vision.append(
                {
                    "segment_id": segment_id,
                    "source_ref": source_id,
                    "start_us": start_us,
                    "end_us": start_us + 8_000_000,
                    "binding_cell_ids": cells,
                    "modality": "vision",
                    "scale": "fine",
                    "searchable": True,
                    "search_payload": {
                        "dimension": 4,
                        "vector_f16_hex": _hex(1.0, 0.2 + source_index),
                    },
                }
            )
            ambient.append(
                {
                    "segment_id": segment_id,
                    "source_ref": source_id,
                    "start_us": start_us,
                    "end_us": start_us + 8_000_000,
                    "binding_cell_ids": cells,
                    "modality": "ambient",
                    "scale": "fine",
                    "searchable": True,
                    "search_payload": {
                        "features": [
                            {
                                "class_name": "Dishes, pots, and pans",
                                "weight": 0.7,
                                "generic": False,
                            },
                            {
                                "class_name": "Speech",
                                "weight": 0.1,
                                "generic": True,
                            },
                        ]
                    },
                }
            )
            for cell_index, cell_id in enumerate(cells):
                routing.append(
                    {
                        "cell_id": cell_id,
                        "source_ref": source_id,
                        "features": {
                            "motion_or_change": 0.25 + cell_index * 0.02,
                            "edge_density": 0.12,
                            "blank_frame": False,
                            "semantic_claim_allowed": False,
                        },
                    }
                )
        speech.append(
            {
                "segment_id": f"asr.{source_id}",
                "source_ref": source_id,
                "start_us": 0,
                "end_us": 30_000_000,
                "binding_cell_ids": [],
                "modality": "speech",
                "scale": "speech_chunk_30s",
                "searchable": True,
                "search_payload": {
                    "tokens": [
                        "open",
                        "container",
                        "then",
                        "pour",
                        "water",
                        "carefully",
                    ],
                    "term_frequency": {},
                    "derived_from_chunk_ids": [f"speech.{source_id}.0"],
                },
            }
        )
    index = {
        "modalities": {
            "vision": {"documents": vision},
            "ambient": {"documents": ambient},
            "speech": {
                "documents": speech,
                "document_count": len(speech),
                "average_document_length": 6,
                "document_frequency": {},
            },
        }
    }
    return EpicIndexInputs(
        index=index,
        segment_manifest={},
        observation_manifest={},
        routing_records=tuple(routing),
        source_hashes={"P27_101": "2" * 64, "P28_103": "1" * 64},
        source_groups={"P27_101": "P27", "P28_103": "P28"},
        provenance={
            "fixture": True,
            "semantic_epic_annotations_accessed": False,
            "existing_annotation_vault_accessed": False,
        },
    )


def fixture_registry(*, mode: str) -> dict[str, Any]:
    inputs = _inputs()
    leads = mine_initial_machine_leads(
        inputs, visual_encoder=FixtureEncoder()
    )
    return build_candidate_registry(
        inputs,
        leads,
        mode=mode,
        prescreen=None,
        created_date="2026-09-28",
    )


def test_initial_mining_emits_two_event_leads_per_source_without_labels():
    leads = mine_initial_machine_leads(
        _inputs(), visual_encoder=FixtureEncoder()
    )
    assert {source_id: len(items) for source_id, items in leads.items()} == {
        "P27_101": 2,
        "P28_103": 2,
    }
    for items in leads.values():
        for lead in items:
            assert set(lead["observation_hypotheses"]) == {
                "dynamic_nontext_visual",
                "board_ocr_static_overlay",
                "speech",
                "non_speech",
            }
            assert lead["current_tier"].startswith("P")
            assert lead["machine_observation_provenance"][
                "semantic_epic_annotations_accessed"
            ] is False
            if lead["hop_structure"]["hop_stratum"] == "one_hop":
                assert lead["hop_structure"]["temporal_stratum"] == "near_local"
            else:
                assert lead["hop_structure"]["composition"][
                    "component_claim_placeholders"
                ]


def test_adjacent_dynamic_windows_do_not_create_machine_multihop():
    leads = mine_initial_machine_leads(
        _inputs(), visual_encoder=FixtureEncoder()
    )
    assert all(
        lead["hop_structure"]["hop_stratum"] == "one_hop"
        for source_leads in leads.values()
        for lead in source_leads
    )


def test_development_only_proposals_are_barred_from_gate_a():
    registry = fixture_registry(mode="development_only")
    validate_candidate_registry(registry)
    assert registry["summary"]["candidate_lead_count"] == 4
    assert registry["gate_a_boundary"]["eligible_to_enter_gate_a"] is False
    assert registry["gate_a_boundary"][
        "development_only_outputs_permanently_ineligible"
    ] is True
    for source in registry["sources"]:
        for lead in source["candidate_leads"]:
            assert lead["task145_cbrn_template"]["active_intervention"] is False
            assert lead["task145_cbrn_template"]["primary_schedule"][
                "action_index"
            ] == 4
            assert (
                lead["authoring_assistance"]["authoring_gate"][
                    "human_authoring_may_begin"
                ]
                is False
            )
            for blueprint in lead["authoring_assistance"]["question_blueprints"]:
                if blueprint["route"] in {
                    "dynamic_nontext_visual",
                    "non_speech",
                }:
                    assert blueprint["question_placeholder"] is None
                    assert blueprint["answer_placeholder"] is None


def test_development_registry_requires_permanent_gate_a_barrier():
    registry = fixture_registry(mode="development_only")
    changed = copy.deepcopy(registry)
    changed["gate_a_boundary"][
        "development_only_outputs_permanently_ineligible"
    ] = False
    changed.pop("registry_hash")
    from av_trace_epic_family_mining.contracts import json_hash

    changed["registry_hash"] = json_hash(changed)
    with pytest.raises(
        ValueError,
        match="DEVELOPMENT_OUTPUT_PERMANENT_INELIGIBILITY_REQUIRED",
    ):
        validate_candidate_registry(changed)


def test_normal_mode_fails_closed_without_human_complete_prescreen():
    inputs = _inputs()
    leads = mine_initial_machine_leads(
        inputs, visual_encoder=HashFixtureEncoder()
    )
    with pytest.raises(ValueError, match="HUMAN_COMPLETE_PRESCREEN_REQUIRED"):
        build_candidate_registry(
            inputs,
            leads,
            mode="gate_a_candidate_input",
            prescreen=None,
            created_date="2026-09-28",
        )


def test_registry_rejects_h_tier():
    registry = fixture_registry(mode="development_only")
    changed = copy.deepcopy(registry)
    changed["sources"][0]["candidate_leads"][0][
        "current_tier"
    ] = "H1_HUMAN_VALIDATED"
    with pytest.raises(ValueError, match="INVALID_P_TIER"):
        validate_candidate_registry(changed)


def test_human_complete_overlapping_prescreen_unlocks_authoring_not_h_tier():
    inputs = _inputs()
    leads = mine_initial_machine_leads(
        inputs, visual_encoder=FixtureEncoder()
    )
    gates = {}
    for source_id, group_id in inputs.source_groups.items():
        gates[source_id] = PrescreenSourceGate(
            source_id=source_id,
            source_group_id=group_id,
            authoring_eligibility="pass",
            observations=(
                HumanObservation(
                    observation_id=f"{source_id}.visual",
                    modality="dynamic_nontext_visual",
                    start_us=0,
                    end_us=80_000_000,
                    candidate_fact_ids=(f"{source_id}.fact",),
                ),
                HumanObservation(
                    observation_id=f"{source_id}.audio",
                    modality="non_speech",
                    start_us=0,
                    end_us=80_000_000,
                    candidate_fact_ids=(f"{source_id}.fact",),
                ),
            ),
            candidate_facts=(
                {
                    "fact_id": f"{source_id}.fact",
                    "fact_statement": "Human-prescreened candidate fact.",
                },
            ),
            recurrence_groups=(),
            authoring_constraints=("Close all text and narration routes.",),
        )
    registry = build_candidate_registry(
        inputs,
        leads,
        mode="gate_a_candidate_input",
        prescreen=PrescreenBundle(
            sources=gates,
            provenance={
                "human_complete": True,
                "h1_assigned": False,
                "h2_assigned": False,
            },
        ),
        created_date="2026-09-28",
    )
    validate_candidate_registry(registry)
    assert registry["gate_a_boundary"]["eligible_to_enter_gate_a"] is True
    assert registry["gate_a_boundary"]["gate_a_decision_asserted"] is False
    assert registry["summary"]["h_tier_count"] == 0
