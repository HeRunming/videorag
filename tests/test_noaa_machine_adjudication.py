from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import noaa_machine_adjudication as machine


ROOT = Path(__file__).resolve().parents[1]


def load_records() -> list[dict]:
    return json.loads((ROOT / machine.RECORDS_REL).read_text())["records"]


def test_delivered_records_are_complete_provisional_and_in_queue_order() -> None:
    queue = json.loads((ROOT / machine.QUEUE_REL).read_text())
    records = load_records()
    machine.validate_records(queue, records)
    assert len(records) == 18
    assert [item["review_id"] for item in records] == [
        item["review_id"] for item in queue["windows"]
    ]
    assert all(item["adjudication_stage"] == machine.STAGE for item in records)
    assert all(item["human_reviewed"] is False for item in records)
    assert all(item["gold_annotation"] is False for item in records)


def test_scientific_layers_are_separate() -> None:
    for record in load_records():
        assert set(
            (
                "observed_model_output",
                "machine_inference",
                "codex_synthesis",
                "unresolved_uncertainty",
            )
        ).issubset(record)
        raw = json.dumps(record["observed_model_output"], sort_keys=True)
        assert "likely_necessary" not in raw
        assert '"disposition"' not in raw


def test_real_local_asr_and_audioset_executed_for_every_window() -> None:
    seen_asr_review_ids = []
    for record in load_records():
        asr = record["observed_model_output"]["asr"]
        events = record["observed_model_output"]["audio_events"]
        assert asr["executed"] is True
        assert asr["local_files_only"] is True
        assert asr["backend"] == "transformers_whisper_local_cpu"
        assert asr["model_id"] == machine.PREFERRED_MODELS[0]["model_id"]
        assert asr["revision"] == machine.PREFERRED_MODELS[0]["revision"]
        assert asr["review_id"] == record["review_id"]
        seen_asr_review_ids.append(asr["review_id"])
        assert isinstance(asr["provisional_text"], str)
        assert len(asr["provisional_text"]) <= 240
        assert asr["token_count"] >= 0
        assert events["executed_audioset_model"] is True
        assert events["local_files_only"] is True
        assert events["backend"] == "transformers_ast_audioset_local_cpu"
        assert events["model_id"] == machine.PREFERRED_MODELS[1]["model_id"]
        assert events["revision"] == machine.PREFERRED_MODELS[1]["revision"]
        assert len(events["aggregate_predictions"]) == machine.AST_TOP_K
        assert events["probability_transform"] == "independent_sigmoid_over_527_labels"
    assert len(set(seen_asr_review_ids)) == 18


def test_likely_necessary_requires_counterfactual_fields() -> None:
    for record in load_records():
        for value in record["codex_synthesis"]["modality_necessity"].values():
            if value["assessment"] == "likely_necessary":
                assert value["lost_without_modality"]
                assert value["dependent_candidate_claim"]
                assert value["duplicated_by_other_modality"] == "no"


def test_manual_compatible_export_is_machine_labeled() -> None:
    export = json.loads((ROOT / machine.EXPORT_REL).read_text())
    assert export["reviewer_type"] == machine.REVIEWER_TYPE
    assert export["human_reviewed"] is False
    assert export["gold_annotation"] is False
    assert export["record_count"] == export["completed_count"] == 18
    for record in export["records"]:
        assert set(record["judgment"]) == {
            "media_loads_and_seeks_correctly",
            "speech_present",
            "speech_intelligible",
            "non_speech_audio_present",
            "non_speech_audio_type",
            "meaningful_visual_information",
            "visual_type",
            "plausible_question_evidence_seed",
            "candidate_modality_role",
            "modality_necessity",
            "evidence_interval_adjustment",
            "sensitive_distressing_private_content",
            "disposition",
            "reviewer_confidence",
            "reviewer_notes",
        }


def test_aggregate_counts_are_recomputed_from_records() -> None:
    aggregate = machine.aggregate_records(load_records())
    assert aggregate["accepted_count"] == 6
    assert aggregate["deferred_count"] == 10
    assert aggregate["rejected_count"] == 2
    assert aggregate["intelligible_asr_window_count"] == 14
    assert aggregate["credible_non_speech_event_window_count"] == 1
    assert aggregate["meaningful_visual_window_count"] == 11
    assert aggregate["candidate_question_evidence_seed_count"] == 14
    assert aggregate["likely_necessary_modality_counts"] == {
        "V": 0,
        "S": 0,
        "A": 0,
    }


def test_accepted_records_have_grounded_seeds() -> None:
    accepted = [
        item for item in load_records() if item["codex_synthesis"]["disposition"] == "accept"
    ]
    assert len(accepted) == 6
    for record in accepted:
        synthesis = record["codex_synthesis"]
        assert synthesis["candidate_question_evidence_seed"]
        grounding = synthesis["seed_grounding"]
        assert (
            grounding["visual_observation_indices"]
            or grounding["asr_segment_ids"]
            or grounding["audio_event_labels"]
        )


def test_model_manifest_hashes_all_persisted_model_files() -> None:
    manifest = json.loads((ROOT / machine.MODEL_MANIFEST_REL).read_text())
    assert manifest["credential_controls"]["hf_credentials_read"] is False
    assert manifest["network_result"].startswith("NOT_USED")
    assert manifest["model_integrity"]["all_sha256sums_verified"] is True
    assert manifest["model_integrity"]["pytorch_model_bin_count"] == 0
    assert (
        manifest["model_integrity"]["duplicate_pytorch_model_bin_confirmed_absent"]
        is True
    )
    assert len(manifest["preferred_external_models"]) == 2
    for model in manifest["preferred_external_models"]:
        assert model["executed"] is True
        assert model["local_files_only"] is True
        assert model["status"] == "LOCAL_PINNED_SNAPSHOT_VERIFIED_AND_EXECUTED"
        assert str(model["local_path"]).startswith(machine.MODELS_ROOT_REL.as_posix())
        for item in model["files"]:
            path = ROOT / item["path"]
            size, digest = machine.sha256_file(path)
            assert size == item["size_bytes"]
            assert digest == item["sha256"]
            assert item["verified_against_sha256sums"] is True
    for fallback in manifest["executed_fallbacks"]:
        for item in fallback["files"]:
            assert str(item["path"]).startswith(machine.MODELS_ROOT_REL.as_posix())
    settings = manifest["inference_settings"]
    assert settings["device"] == "cpu"
    assert settings["dtype"] == "float32"
    assert settings["torch_deterministic_algorithms"] is True
    assert settings["whisper"]["do_sample"] is False
    assert settings["whisper"]["num_beams"] == 1
    assert settings["ast"]["top_k"] == machine.AST_TOP_K


def test_shared_model_root_accepts_registered_clip_weight() -> None:
    integrity = machine.verify_all_models(ROOT)
    assert set(integrity) == {"whisper", "ast"}
    assert all(item["verified"] for item in integrity.values())


def test_owned_snapshots_still_have_exactly_two_safetensors_weights() -> None:
    integrity = machine.verify_all_models(ROOT)
    owned_weights = [
        item
        for verified in integrity.values()
        for item in verified["files"]
        if Path(item["path"]).name in {"model.safetensors", "pytorch_model.bin"}
    ]
    assert len(owned_weights) == 2
    assert {Path(item["path"]).name for item in owned_weights} == {
        "model.safetensors"
    }


def test_owned_snapshot_rejects_unregistered_extra_weight(tmp_path: Path) -> None:
    snapshot = tmp_path / "owned"
    snapshot.mkdir()
    weight = snapshot / "model.safetensors"
    extra = snapshot / "pytorch_model.bin"
    weight.write_bytes(b"owned")
    extra.write_bytes(b"unregistered")
    (snapshot / "SHA256SUMS").write_text(
        f"{hashlib.sha256(b'owned').hexdigest()}  model.safetensors\n",
        encoding="utf-8",
    )
    with pytest.raises(machine.AdjudicationError, match="MODEL_FILE_SET_MISMATCH"):
        machine.verify_model_snapshot(
            tmp_path,
            Path("owned"),
            required_files=("model.safetensors",),
        )


def test_shared_model_root_rejects_unregistered_pytorch_weight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models = tmp_path / machine.MODELS_ROOT_REL / "foreign"
    models.mkdir(parents=True)
    (models / "pytorch_model.bin").write_bytes(b"unregistered")

    def owned_snapshot_stub(*args, **kwargs):
        return {
            "files": [
                {
                    "path": "owned/model.safetensors",
                    "size_bytes": 1,
                    "sha256": "0" * 64,
                }
            ],
            "verified": True,
        }

    monkeypatch.setattr(machine, "verify_model_snapshot", owned_snapshot_stub)
    with pytest.raises(machine.AdjudicationError, match="UNEXPECTED_PYTORCH_MODEL_BIN"):
        machine.verify_all_models(tmp_path)


def test_authorization_preserves_non_gold_boundary() -> None:
    authorization = json.loads((ROOT / machine.AUTHORIZATION_REL).read_text())
    assert authorization["adjudication_stage"] == machine.STAGE
    assert authorization["authorized_scope"]["window_count"] == 18
    assert authorization["scientific_boundary"]["human_reviewed"] is False
    assert authorization["scientific_boundary"]["gold_annotation"] is False
    assert all(authorization["continuing_prohibitions"].values())


def test_generic_audio_labels_never_become_credible_events() -> None:
    features = {
        "event_routing_proxy": [
            {"label": "Music", "score": 0.99, "generic_discounted": True}
        ]
    }
    result = machine.audio_event_observation(features)
    assert result["qualifying_specific_event_predictions"] == []


def test_delivered_specific_events_are_non_generic_and_above_threshold() -> None:
    credible_windows = []
    for record in load_records():
        predictions = record["machine_inference"]["non_speech_audio"][
            "credible_specific_events"
        ]
        if predictions:
            credible_windows.append(record["review_id"])
        for prediction in predictions:
            assert not machine.is_generic_audio_label(prediction["label"])
            assert (
                prediction["probability"]
                >= machine.AST_SPECIFIC_EVENT_MIN_PROBABILITY
            )
    assert credible_windows == ["noaa01-review-004"]


def test_semantically_incoherent_asr_is_not_counted_as_intelligible() -> None:
    by_id = {record["review_id"]: record for record in load_records()}
    record = by_id["noaa01-review-006"]
    asr = record["observed_model_output"]["asr"]
    assert "SEMANTIC_COHERENCE_REVIEW_FAILED" in asr["quality_flags"]
    assert record["machine_inference"]["speech_presence"]["value"] == "yes"
    assert record["machine_inference"]["speech_intelligibility"]["value"] == "uncertain"


def test_invalid_necessity_fails_closed() -> None:
    queue = json.loads((ROOT / machine.QUEUE_REL).read_text())
    records = load_records()
    necessity = records[0]["codex_synthesis"]["modality_necessity"]["V"]
    necessity["assessment"] = "likely_necessary"
    necessity["dependent_candidate_claim"] = ""
    necessity["lost_without_modality"] = "A visual fact would be unavailable."
    necessity["duplicated_by_other_modality"] = "no"
    with pytest.raises(machine.AdjudicationError, match="UNSUPPORTED_NECESSITY"):
        machine.validate_records(queue, records)


def test_necessity_requires_executed_passing_counterfactual() -> None:
    queue = json.loads((ROOT / machine.QUEUE_REL).read_text())
    records = load_records()
    synthesis = records[0]["codex_synthesis"]
    synthesis["modality_necessity"]["V"] = machine.strict_necessity(
        True,
        True,
        lost="The visual answer-bearing evidence would be unavailable.",
        claim=synthesis["candidate_question_evidence_seed"],
        duplicated="no",
    )
    with pytest.raises(
        machine.AdjudicationError, match="NECESSITY_WITHOUT_COUNTERFACTUAL"
    ):
        machine.validate_records(queue, records)


def test_every_record_declares_counterfactual_status() -> None:
    for record in load_records():
        validation = record["codex_synthesis"]["counterfactual_validation"]
        assert validation["performed"] is False
        assert validation["status"] == "not_run"
        assert validation["validated_likely_necessary_modalities"] == []
        assert all(
            value["assessment"] != "likely_necessary"
            for value in record["codex_synthesis"]["modality_necessity"].values()
        )


def test_sha256sums_parser_rejects_duplicate_paths_and_invalid_digests(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "SHA256SUMS").write_text(
        f"{'0' * 64}  file.bin\n{'1' * 64}  file.bin\n"
    )
    with pytest.raises(machine.AdjudicationError, match="DUPLICATE_SHA256SUMS_PATH"):
        machine._parse_sha256sums(snapshot)
    (snapshot / "SHA256SUMS").write_text("not-a-digest  file.bin\n")
    with pytest.raises(machine.AdjudicationError, match="INVALID_SHA256SUMS_DIGEST"):
        machine._parse_sha256sums(snapshot)


def test_record_queue_identity_checks_fail_closed() -> None:
    queue = json.loads((ROOT / machine.QUEUE_REL).read_text())
    for field, bad_value, error_field in (
        ("queue_position", 999, "queue_position"),
        ("source_task80_candidate_window_id", "wrong", "source_task80"),
        (
            "review_interval",
            {"start_seconds": 1.0, "end_seconds": 2.0},
            "review_interval",
        ),
    ):
        records = load_records()
        records[0][field] = bad_value
        with pytest.raises(machine.AdjudicationError, match=error_field):
            machine.validate_records(queue, records)


def test_record_decode_evidence_checks_fail_closed() -> None:
    queue = json.loads((ROOT / machine.QUEUE_REL).read_text())
    records = load_records()
    records[0]["observed_model_output"]["decode"]["audio_sample_count"] -= 1
    with pytest.raises(machine.AdjudicationError, match="INVALID_DECODE_EVIDENCE"):
        machine.validate_records(queue, records)


def test_validate_existing_and_public_report_have_no_transcript_text() -> None:
    result = machine.validate_existing(ROOT)
    assert result["status"] == "VALID"
    public_paths = (
        ROOT / machine.REPORT_REL,
        ROOT / machine.RESULT_REL,
        ROOT / machine.TASK84_RESULT_REL,
        ROOT / machine.AUTHORIZATION_REL,
    )
    public_text = "\n".join(path.read_text() for path in public_paths)
    assert "provisional_text" not in public_text
    assert machine.STAGE in public_text
    for record in load_records():
        text = record["observed_model_output"]["asr"]["provisional_text"]
        if len(text.strip()) >= 4:
            assert text not in public_text


def test_restricted_tree_contains_no_persistent_media_derivatives() -> None:
    forbidden_suffixes = {".wav", ".flac", ".png", ".jpg", ".jpeg", ".webp", ".npy", ".npz"}
    found = [
        path
        for path in (ROOT / machine.RESTRICTED_ROOT_REL).rglob("*")
        if path.is_file() and path.suffix.lower() in forbidden_suffixes
    ]
    assert found == []


def test_task83_fallback_is_preserved_and_superseded() -> None:
    assert (ROOT / machine.FALLBACK_RECORDS_REL).is_file()
    manifest = json.loads((ROOT / machine.MANIFEST_REL).read_text())
    comparison = manifest["task83_fallback_comparison"]
    assert comparison["superseded"] is True
    assert comparison["changed_window_count"] == 17
    assert "noaa01-review-017" in comparison["changed_windows"]


def test_authoritative_result_is_real_model_go() -> None:
    for rel in (machine.RESULT_REL, machine.TASK84_RESULT_REL):
        result = (ROOT / rel).read_text()
        assert "GO_PROVISIONAL_EPISODE_CONSTRUCTION" in result
        assert "local_files_only=True" in result
