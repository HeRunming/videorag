from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from av_trace_captaincook4d_family_mining import (
    CaptainCook4DIndexInputs,
    HumanObservation,
    PrescreenBundle,
    PrescreenSourceGate,
    build_candidate_registry,
    mine_initial_machine_leads,
    validate_candidate_registry,
)
from av_trace_captaincook4d_family_mining.inspection import (
    direct_inspection_assistance,
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


def fixture_inputs(tmp_path: Path) -> CaptainCook4DIndexInputs:
    source_ids = ("15_29", "16_20", "26_22")
    groups = {
        "15_29": "cc4d_p02_e02",
        "16_20": "cc4d_p01_e08",
        "26_22": "cc4d_p03_e03",
    }
    vision = []
    ambient = []
    speech = []
    routing = []
    media = {}
    for source_index, source_id in enumerate(source_ids):
        path = tmp_path / f"{source_id}.mp4"
        path.write_bytes(b"fixture-not-decoded")
        media[source_id] = path
        for index, start_us in enumerate(
            (0, 24_000_000, 200_000_000, 240_000_000)
        ):
            segment_id = f"seg.{source_id}.fine.{index}"
            cells = [
                f"cell.{source_id}.{index}",
                f"cell.{source_id}.{index + 1}",
            ]
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
                        "vector_f16_hex": _hex(1.0, 0.1 + source_index),
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
                                "class_name": "Chopping (food)",
                                "weight": 0.75 - 0.05 * index,
                                "generic": False,
                            },
                            {
                                "class_name": "Speech",
                                "weight": 0.05,
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
                            "motion_or_change": 0.25 + 0.01 * cell_index,
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
                    "tokens": ["mix", "then", "cook", "carefully"],
                    "term_frequency": {},
                },
            }
        )
    return CaptainCook4DIndexInputs(
        index={
            "modalities": {
                "vision": {"documents": vision},
                "ambient": {"documents": ambient},
                "speech": {"documents": speech},
            }
        },
        segment_manifest={},
        observation_manifest={},
        routing_records=tuple(routing),
        source_hashes={
            source_id: str(index + 1) * 64
            for index, source_id in enumerate(source_ids)
        },
        source_groups=groups,
        source_media_paths=media,
        source_durations_s={source_id: 300.0 for source_id in source_ids},
        provenance={
            "fixture": True,
            "semantic_captaincook_annotations_accessed": False,
            "task_graphs_accessed": False,
            "error_labels_accessed": False,
        },
    )


def fixture_registry(tmp_path: Path, *, mode: str) -> dict[str, Any]:
    inputs = fixture_inputs(tmp_path)
    leads = mine_initial_machine_leads(
        inputs, visual_encoder=FixtureEncoder()
    )
    return build_candidate_registry(
        inputs,
        leads,
        mode=mode,
        prescreen=None,
        created_date="2026-10-10",
        run_direct_inspection=False,
    )


def test_mining_emits_exactly_two_per_source_with_label_firewall(tmp_path):
    leads = mine_initial_machine_leads(
        fixture_inputs(tmp_path), visual_encoder=FixtureEncoder()
    )
    assert {key: len(value) for key, value in leads.items()} == {
        "15_29": 2,
        "16_20": 2,
        "26_22": 2,
    }
    for source_leads in leads.values():
        for lead in source_leads:
            assert set(lead["observation_hypotheses"]) == {
                "dynamic_nontext_visual",
                "board_ocr_static_overlay",
                "speech",
                "non_speech",
            }
            firewall = lead["risk_flags"]["semantic_annotation_firewall"]
            assert not any(firewall.values())
            if lead["hop_structure"]["hop_stratum"] == "one_hop":
                assert lead["hop_structure"]["temporal_stratum"] == "near_local"


def test_development_registry_is_machine_expert_provisional_and_gate_a_barred(
    tmp_path,
):
    registry = fixture_registry(tmp_path, mode="development_only")
    validate_candidate_registry(registry)
    assert registry["artifact_classification"] == "MACHINE_EXPERT_PROVISIONAL"
    assert registry["summary"]["candidate_lead_count"] == 6
    assert registry["gate_a_boundary"]["eligible_to_enter_gate_a"] is False
    for source in registry["sources"]:
        for lead in source["candidate_leads"]:
            inspection = lead["authoring_assistance"][
                "bounded_direct_inspection"
            ]
            assert inspection["frame_inspection"]["status"] == "NOT_RUN"
            hypotheses = inspection["source_world_hypotheses"]
            assert hypotheses["question_hypothesis"].strip()
            assert hypotheses["answer_hypothesis"].strip()
            assert hypotheses["claim_hypotheses"]
            assert hypotheses["evidence_hypotheses"]
            assert (
                lead["task145_cbrn_template"]["active_intervention"] is False
            )


def test_gate_a_mode_fails_closed_without_task153(tmp_path):
    inputs = fixture_inputs(tmp_path)
    leads = mine_initial_machine_leads(
        inputs, visual_encoder=FixtureEncoder()
    )
    with pytest.raises(
        ValueError, match="TASK153_HUMAN_PRESCREEN_REQUIRED_FOR_GATE_A"
    ):
        build_candidate_registry(
            inputs,
            leads,
            mode="gate_a_candidate_input",
            prescreen=None,
            created_date="2026-10-10",
            run_direct_inspection=False,
        )


def test_completed_task153_can_unlock_gate_a_review_without_h_tier(tmp_path):
    inputs = fixture_inputs(tmp_path)
    leads = mine_initial_machine_leads(
        inputs, visual_encoder=FixtureEncoder()
    )
    gates = {}
    for source_id, group_id in inputs.source_groups.items():
        gates[source_id] = PrescreenSourceGate(
            source_id=source_id,
            source_group_id=group_id,
            observations=(
                HumanObservation(
                    observation_id=f"{source_id}.visual",
                    modality="dynamic_nontext_visual",
                    start_us=0,
                    end_us=300_000_000,
                    candidate_fact_ids=(f"{source_id}.fact",),
                ),
                HumanObservation(
                    observation_id=f"{source_id}.audio",
                    modality="non_speech",
                    start_us=0,
                    end_us=300_000_000,
                    candidate_fact_ids=(f"{source_id}.fact",),
                ),
            ),
            candidate_facts=(
                {
                    "fact_id": f"{source_id}.fact",
                    "fact_statement": "Human-prescreened source fact.",
                },
            ),
            recurrence_groups=(),
            authoring_constraints=("Close text and recurrence routes.",),
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
                "necessity_assigned": False,
            },
        ),
        created_date="2026-10-10",
        run_direct_inspection=False,
    )
    validate_candidate_registry(registry)
    assert registry["gate_a_boundary"]["eligible_to_enter_gate_a"] is True
    assert registry["summary"]["h_tier_count"] == 0


def test_registry_rejects_affirmative_human_status(tmp_path):
    registry = fixture_registry(tmp_path, mode="development_only")
    broken = copy.deepcopy(registry)
    lead = broken["sources"][0]["candidate_leads"][0]
    lead["h1_assigned"] = True
    from av_trace_captaincook4d_family_mining.contracts import json_hash

    lead.pop("candidate_hash")
    lead["candidate_hash"] = json_hash(lead)
    broken.pop("registry_hash")
    broken["registry_hash"] = json_hash(broken)
    with pytest.raises(ValueError, match="FORBIDDEN_AFFIRMATIVE_STATUS"):
        validate_candidate_registry(broken)


def test_direct_inspection_is_bounded_and_persists_no_derivatives(tmp_path):
    import av

    path = tmp_path / "bounded-fixture.mkv"
    with av.open(str(path), "w") as container:
        video = container.add_stream("mpeg4", rate=10)
        video.width = 64
        video.height = 48
        video.pix_fmt = "yuv420p"
        audio = container.add_stream("pcm_s16le", rate=16_000)
        audio.layout = "mono"
        for index in range(30):
            image = np.zeros((48, 64, 3), dtype=np.uint8)
            image[:, :, 0] = (index * 8) % 256
            image[:, index % 64, :] = 255
            frame = av.VideoFrame.from_ndarray(image, format="rgb24")
            frame.pts = index
            for packet in video.encode(frame):
                container.mux(packet)
        for packet in video.encode():
            container.mux(packet)
        samples = (
            0.2
            * np.sin(2 * np.pi * 440 * np.arange(48_000) / 16_000)
            * 32_767
        ).astype(np.int16)[None, :]
        audio_frame = av.AudioFrame.from_ndarray(
            samples, format="s16", layout="mono"
        )
        audio_frame.sample_rate = 16_000
        audio_frame.pts = 0
        for packet in audio.encode(audio_frame):
            container.mux(packet)
        for packet in audio.encode():
            container.mux(packet)
    lead = {
        "candidate_lead_id": "cc4d.fixture.direct",
        "primary_interval": {"start_s": 0.2, "end_s": 2.5},
        "hop_structure": {"hop_stratum": "one_hop", "composition": None},
        "observation_hypotheses": {
            "dynamic_nontext_visual": {"status": "MACHINE_HYPOTHESIS"},
            "non_speech": {"status": "MACHINE_AST_HYPOTHESIS"},
        },
    }
    before = {item.name for item in tmp_path.iterdir()}
    result = direct_inspection_assistance(path, lead)
    after = {item.name for item in tmp_path.iterdir()}
    assert before == after
    assert 1 <= result["frame_inspection"]["frame_sample_count"] <= 12
    assert result["audio_inspection"]["human_listening_performed"] is False
    assert result["repository_media_derivatives_persisted"] is False
    assert (
        result["source_world_hypotheses"]["artifact_classification"]
        == "MACHINE_EXPERT_PROVISIONAL"
    )
