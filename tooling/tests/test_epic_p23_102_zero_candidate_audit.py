from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = (
    ROOT
    / "data/rehearsal_plan/epic_p23_102_zero_candidate_audit_v1.json"
)
REPORT_PATH = ROOT / "docs/review/epic_p23_102_zero_candidate_audit.md"
INDEX_ROOT = (
    ROOT / "data/restricted/epic_p23_102_full_timeline_index_v1"
)
REGISTRY_PATH = (
    ROOT
    / "data/restricted/epic_p23_102_family_mining_v1_dev"
    / "candidate_registry.json"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def vector(document: dict) -> np.ndarray:
    value = np.frombuffer(
        bytes.fromhex(document["vector_f16_hex"]), dtype="<f2"
    ).astype(np.float32)
    value /= np.linalg.norm(value)
    return value


def center(document: dict) -> float:
    return (int(document["start_us"]) + int(document["end_us"])) / 2.0


def overlap_us(first: dict, second: dict) -> int:
    return max(
        0,
        min(int(first["end_us"]), int(second["end_us"]))
        - max(int(first["start_us"]), int(second["start_us"])),
    )


def neighbor_distances(documents: list[dict]) -> list[float]:
    values = [vector(document) for document in documents]
    result = []
    for index, value in enumerate(values):
        distances = []
        if index:
            distances.append(1.0 - float(np.dot(value, values[index - 1])))
        if index + 1 < len(values):
            distances.append(
                1.0 - float(np.dot(value, values[index + 1]))
            )
        result.append(max(distances, default=0.0))
    return result


def test_audit_decision_scope_and_completion_token() -> None:
    audit = load_json(AUDIT_PATH)
    report = REPORT_PATH.read_text(encoding="utf-8")

    assert audit["audit_date"] == "2026-10-14"
    assert audit["decision"] == "MINER_REPAIR"
    assert audit["recommendation"]["keep_zero_until_repaired"] is True
    assert audit["scope"] == {
        "source_id": "P23_102",
        "method": "LIGHTWEIGHT_STRUCTURAL_JSON_ONLY",
        "models_run": False,
        "media_opened_or_decoded": False,
        "semantic_annotations_inspected": False,
        "candidates_fabricated": False,
    }
    assert audit["completion_token"] in report
    assert report.rstrip().endswith(
        "**EPIC_P23_102_ZERO_CANDIDATE_AUDIT_READY**"
    )


def test_audit_input_hashes_are_exact() -> None:
    audit = load_json(AUDIT_PATH)

    for binding in audit["inputs"]:
        path = ROOT / binding["path"]
        payload = path.read_bytes()
        assert len(payload) == binding["size_bytes"]
        assert (
            "sha256:" + hashlib.sha256(payload).hexdigest()
            == binding["sha256"]
        )


def test_manifest_checkpoint_and_modality_ids_are_consistent() -> None:
    audit = load_json(AUDIT_PATH)
    checkpoint_manifest = load_json(INDEX_ROOT / "checkpoint_manifest.json")
    segment_manifest = load_json(INDEX_ROOT / "segment_manifest.json")
    index = load_json(INDEX_ROOT / "full_timeline_index.json")

    assert checkpoint_manifest["checkpoint_count"] == 4
    for row in checkpoint_manifest["checkpoints"]:
        path = ROOT / row["path"]
        document = load_json(path)
        payload_bytes = (
            json.dumps(
                document["payload"],
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        assert row["record_count"] == document["record_count"]
        assert row["size_bytes"] == path.stat().st_size
        assert row["sha256"] == (
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        )
        assert document["payload_hash"] == (
            "sha256:" + hashlib.sha256(payload_bytes).hexdigest()
        )

    fine_ids = {
        row["segment_id"]
        for row in segment_manifest["segments"]
        if row["scale"] == "fine"
    }
    all_ids = {
        row["segment_id"] for row in segment_manifest["segments"]
    }
    visual = index["modalities"]["siglip2_visual"]["documents"]
    audio = index["modalities"]["clap_audio"]["documents"]
    assert fine_ids == {
        row["segment_id"] for row in visual if row["scale"] == "fine"
    }
    assert fine_ids == {
        row["segment_id"] for row in audio if row["scale"] == "fine"
    }
    assert all_ids == {row["segment_id"] for row in visual}
    assert all_ids == {row["segment_id"] for row in audio}
    assert audit["integrity"]["path_or_schema_mismatch_found"] is False


def test_speech_quality_bottleneck_matches_index() -> None:
    audit = load_json(AUDIT_PATH)
    index = load_json(INDEX_ROOT / "full_timeline_index.json")
    speech = index["modalities"]["speech"]["documents"]

    assert len(speech) == 119
    assert sum(bool(row["text"].strip()) for row in speech) == 119
    assert sum(bool(row["quality_gate_pass"]) for row in speech) == 1
    assert sum(bool(row["searchable"]) for row in speech) == 1
    assert sum(
        "LOW_GENERATED_TOKEN_LOGPROB" in row["quality_flags"]
        for row in speech
    ) == 116
    assert sum(
        "TOO_FEW_LEXICAL_TOKENS" in row["quality_flags"]
        for row in speech
    ) == 31
    assert sum(int(row["token_count"]) >= 5 for row in speech) == 88
    assert sum(
        row["mean_generated_token_log_probability"] >= -0.85
        for row in speech
    ) == 3
    assert audit["speech_quality"]["searchable_chunks"] == 1
    assert audit["speech_quality"]["quality_gate_pass"] == 1


def test_visual_gate_is_unreachable_and_local_funnel_is_zero() -> None:
    audit = load_json(AUDIT_PATH)
    index = load_json(INDEX_ROOT / "full_timeline_index.json")
    visual = sorted(
        [
            row
            for row in index["modalities"]["siglip2_visual"]["documents"]
            if row["scale"] == "fine" and row["searchable"]
        ],
        key=lambda row: (
            row["start_us"],
            row["end_us"],
            row["segment_id"],
        ),
    )
    transitions = neighbor_distances(visual)

    assert len(visual) == 892
    assert abs(max(transitions) - 0.0962067246) < 1e-10
    assert sum(value >= 0.18 for value in transitions) == 0
    assert sum(value >= 0.10 for value in transitions) == 0
    assert sum(value >= 0.05 for value in transitions) == 273
    assert audit["candidate_generation_funnel"]["local"] == [
        {"gate": "searchable_fine_visual", "count": 892},
        {"gate": "visual_transition_at_least_0_18", "count": 0},
        {"gate": "overlapping_searchable_speech", "count": 0},
        {"gate": "speech_quality_at_least_0_2", "count": 0},
        {"gate": "raw_local_rows", "count": 0},
        {
            "gate": "after_12_second_center_deduplication",
            "count": 0,
        },
    ]


def test_audio_floors_have_structural_passes_but_no_candidate_attachment() -> None:
    audit = load_json(AUDIT_PATH)
    index = load_json(INDEX_ROOT / "full_timeline_index.json")
    visual = sorted(
        [
            row
            for row in index["modalities"]["siglip2_visual"]["documents"]
            if row["scale"] == "fine" and row["searchable"]
        ],
        key=lambda row: (
            row["start_us"],
            row["end_us"],
            row["segment_id"],
        ),
    )
    audio = sorted(
        [
            row
            for row in index["modalities"]["clap_audio"]["documents"]
            if row["scale"] == "fine" and row["searchable"]
        ],
        key=lambda row: (
            row["start_us"],
            row["end_us"],
            row["segment_id"],
        ),
    )
    searchable_speech = [
        row
        for row in index["modalities"]["speech"]["documents"]
        if row["searchable"]
    ]
    novelty = neighbor_distances(audio)

    assert len(searchable_speech) == 1
    assert sum(value >= 0.16 for value in novelty) == 459
    assert all(row["audio_rms_full_scale"] >= 1e-5 for row in audio)
    assert all("NEAR_SILENCE" not in row["quality_flags"] for row in audio)

    complete_audio_floor_passes = 0
    for visual_row, audio_row, novelty_value in zip(
        visual, audio, novelty, strict=True
    ):
        overlaps = [
            row
            for row in searchable_speech
            if overlap_us(visual_row, row) > 0
        ]
        if not overlaps:
            continue
        overlaps.sort(
            key=lambda row: (
                -overlap_us(visual_row, row),
                -row["document_length"],
                row["chunk_id"],
            )
        )
        if (
            novelty_value >= 0.16
            and audio_row["audio_rms_full_scale"] >= 1e-5
            and "NEAR_SILENCE" not in audio_row["quality_flags"]
            and overlaps[0]["document_length"] <= 8
        ):
            complete_audio_floor_passes += 1

    assert complete_audio_floor_passes == 5
    assert audit["audio_structural_diagnostics"][
        "fine_windows_passing_novelty_rms_silence_and_sparse_searchable_speech"
    ] == 5
    assert load_json(REGISTRY_PATH)["candidates"] == []


def test_far_and_recurrence_structural_counts_are_deterministic() -> None:
    audit = load_json(AUDIT_PATH)
    index = load_json(INDEX_ROOT / "full_timeline_index.json")
    visual = sorted(
        [
            row
            for row in index["modalities"]["siglip2_visual"]["documents"]
            if row["scale"] == "fine" and row["searchable"]
        ],
        key=lambda row: (
            row["start_us"],
            row["end_us"],
            row["segment_id"],
        ),
    )
    vectors = np.stack([vector(row) for row in visual])
    centers = np.asarray([center(row) for row in visual])

    far_separated = 0
    far_continuity = 0
    far_strong = 0
    recurrence = 0
    for index_value in range(len(visual)):
        similarities = vectors[index_value + 1 :] @ vectors[index_value]
        separations = np.abs(
            centers[index_value + 1 :] - centers[index_value]
        )
        far_mask = separations >= 120_000_000
        far_separated += int(far_mask.sum())
        far_continuity += int((far_mask & (similarities >= 0.88)).sum())
        far_strong += int((far_mask & (similarities >= 0.96)).sum())
        recurrence += int(
            (
                (separations >= 16_000_000)
                & (similarities >= 0.985)
            ).sum()
        )

    counterfactual = audit["candidate_generation_funnel"][
        "far_all_fine_counterfactual_structural_counts"
    ]
    assert far_separated == counterfactual[
        "pairs_at_least_120_seconds_apart"
    ] == 371952
    assert far_continuity == counterfactual[
        "pairs_also_visual_continuity_at_least_0_88"
    ] == 61084
    assert far_strong == counterfactual[
        "pairs_also_visual_continuity_at_least_0_96"
    ] == 289
    assert recurrence == audit["candidate_generation_funnel"][
        "recurrence"
    ][
        "pairs_at_least_16_seconds_apart_and_visual_similarity_at_least_0_985"
    ] == 3
    assert audit["candidate_generation_funnel"]["far_exact_miner"] == [
        {
            "gate": "anchor_pool_derived_only_from_raw_local_rows",
            "count": 0,
        },
        {"gate": "anchor_pairs", "count": 0},
        {"gate": "far_rows", "count": 0},
    ]
