from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import noaa_content_recon as recon


def measurement(
    candidate_id: str,
    start: float,
    *,
    speech: float,
    non_speech: float,
    visual: float,
    stage: str = "coarse",
) -> dict:
    speech_status = (
        "strong_speech_proxy"
        if speech >= recon.SPEECH_SCORE_STRONG
        else "speech_proxy_candidate"
        if speech >= recon.SPEECH_SCORE_THRESHOLD
        else "below_speech_proxy_threshold"
    )
    non_speech_status = (
        "non_speech_priority_candidate"
        if non_speech >= recon.NON_SPEECH_SCORE_THRESHOLD
        else "possible_mixture"
        if non_speech >= 0.35
        else "not_indicated"
    )
    visual_status = (
        "strong_change"
        if visual >= 0.70
        else "meaningful_change"
        if visual >= 0.42
        else "mostly_static_or_low_change"
    )
    item = {
        "measurement_id": f"{candidate_id}-{stage}-{start}",
        "candidate_id": candidate_id,
        "basename": f"{candidate_id}.mp4",
        "start_seconds": start,
        "end_seconds": start + recon.WINDOW_SECONDS,
        "sampling_stage": stage,
        "sampling_retrieval_rationale": "test",
        "audio": {
            "rms_full_scale": 0.02,
            "peak_absolute_full_scale": 0.2,
            "silence_ratio": 0.1,
            "active_frame_ratio": 0.9,
            "zero_crossing_rate": 0.08,
            "spectral_centroid_hz": 1000.0,
            "spectral_flatness": 0.2,
            "voiced_proxy_ratio": 0.6,
            "harmonicity_proxy": 0.5,
        },
        "visual": {
            "mean_frame_difference": 0.05,
            "max_frame_difference": 0.15,
            "scene_cut_count": 1,
            "mean_entropy_bits": 5.0,
            "mean_edge_density": 0.1,
            "mean_brightness_normalized": 0.5,
        },
        "inferences": {
            "speech_score": speech,
            "speech_status": speech_status,
            "non_speech_audio_score": non_speech,
            "non_speech_audio_status": non_speech_status,
            "visual_change_score": visual,
            "visual_content_status": visual_status,
        },
    }
    item["candidate_modality_families"] = recon.modality_families(item)
    return item


def test_regular_grid_is_deterministic_and_covers_edges() -> None:
    assert recon.regular_grid(108.0, count=6) == [0.0, 20.0, 40.0, 60.0, 80.0, 100.0]
    assert recon.regular_grid(8.0, count=5) == [0.0]


def test_infer_window_separates_measurements_from_status() -> None:
    audio = {
        "rms_full_scale": 0.02,
        "peak_absolute_full_scale": 0.2,
        "silence_ratio": 0.1,
        "active_frame_ratio": 0.9,
        "zero_crossing_rate": 0.09,
        "spectral_flatness": 0.15,
        "voiced_proxy_ratio": 0.8,
        "harmonicity_proxy": 0.7,
    }
    visual = {"mean_frame_difference": 0.07, "max_frame_difference": 0.16}
    result = recon.infer_window(audio, visual)
    assert result["speech_status"] == "strong_speech_proxy"
    assert result["visual_content_status"] == "strong_change"
    assert result["speech_basis"] == "deterministic_signal_proxy_no_asr_model"


def test_modality_families_are_combinations_not_necessity_claims() -> None:
    item = measurement("cand-045", 0, speech=0.8, non_speech=0.6, visual=0.8)
    assert recon.modality_families(item) == ["V", "S", "A", "V+S", "V+A", "V+S+A"]


def test_proxy_status_names_do_not_claim_speech_or_audio_event_identity() -> None:
    item = measurement("cand-045", 0, speech=0.8, non_speech=0.7, visual=0.8)
    assert item["inferences"]["speech_status"] == "strong_speech_proxy"
    assert (
        item["inferences"]["non_speech_audio_status"]
        == "non_speech_priority_candidate"
    )
    assert "credible" not in item["inferences"]["non_speech_audio_status"]


def test_adaptive_starts_are_bounded_unique_and_deterministic() -> None:
    coarse = [
        measurement("cand-045", 0, speech=0.1, non_speech=0.2, visual=0.1),
        measurement("cand-045", 20, speech=0.9, non_speech=0.2, visual=0.8),
        measurement("cand-045", 40, speech=0.2, non_speech=0.8, visual=0.2),
    ]
    result = recon.build_adaptive_starts(coarse, 60, max_windows=3)
    assert result == sorted(result, key=lambda item: item["start_seconds"])
    assert len({item["start_seconds"] for item in result}) == len(result)
    assert all(0 <= item["start_seconds"] <= 52 for item in result)


def test_candidate_selection_is_compact_balanced_and_human_reviewed() -> None:
    values = []
    for candidate_id in recon.EXPECTED_CANDIDATES:
        for index in range(8):
            values.append(
                measurement(
                    candidate_id,
                    index * 20.0,
                    speech=0.8 if index % 3 == 0 else 0.3,
                    non_speech=0.7 if index % 3 == 1 else 0.2,
                    visual=0.8 if index % 3 == 2 else 0.2,
                )
            )
    candidates = recon.select_candidates(values)
    assert len(candidates) == 30
    assert {item["video_id"] for item in candidates} == set(recon.EXPECTED_CANDIDATES)
    assert all(item["human_review_required"] is True for item in candidates)
    assert all("gold" in item["not_gold_label_reason"] for item in candidates)
    assert all(
        "review-routing hypotheses" in item["candidate_modality_family_semantics"]
        for item in candidates
    )


def test_feasibility_go_requires_broad_speech_visual_and_combined_candidates() -> None:
    values = []
    for candidate_id in recon.EXPECTED_CANDIDATES:
        values.extend(
            [
                measurement(candidate_id, 0, speech=0.8, non_speech=0.2, visual=0.8),
                measurement(candidate_id, 180, speech=0.4, non_speech=0.8, visual=0.8),
            ]
        )
    candidates = recon.select_candidates(values, target_count=10, max_per_asset=2)
    result = recon.assess_feasibility(values, candidates, asr_model_available=True)
    assert result["decision"] == "GO_REAL_AV_MVP_CONSTRUCTION"
    assert result["all_five_assets_contain_intelligible_speech_candidates"] is True
    assert result["non_speech_priority_candidate_asset_count"] == 5


def test_validate_authoritative_inputs_fails_on_missing_audit(tmp_path: Path) -> None:
    with pytest.raises(recon.ReconError, match="MISSING_OR_UNSAFE_PLAN"):
        recon.validate_authoritative_inputs(tmp_path)


def test_authorization_has_required_prohibitions() -> None:
    root = Path(__file__).resolve().parents[1]
    authorization = json.loads((root / recon.AUTHORIZATION_REL).read_text())
    assert authorization["authorization_status"] == (
        "ACTIVE_FOR_RESTRICTED_CONTENT_RECONNAISSANCE_ONLY"
    )
    assert all(authorization["continuing_prohibitions"].values())
    assert authorization["authorized_scope"]["persistent_media_derivatives_allowed"] is False


def test_pyav_child_declares_no_persistent_output() -> None:
    assert "persistent_outputs_created" in recon.PYAV_RECON_CHILD
    assert "cv2.imwrite" not in recon.PYAV_RECON_CHILD
    assert "open(" not in recon.PYAV_RECON_CHILD.replace("av.open(", "")


def test_capability_audit_does_not_claim_unimplemented_asr_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / recon.ASR_LOCAL_REL
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}")
    (model_dir / "model.safetensors").write_bytes(b"placeholder")
    result = recon.capability_audit(tmp_path)
    assert result["asr_model"]["locally_ready"] is True
    assert result["asr_model"]["executed"] is False
    assert result["selected_reconnaissance_backend"] == "deterministic_signal_proxy"
