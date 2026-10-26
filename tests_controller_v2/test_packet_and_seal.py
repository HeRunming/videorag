from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from av_trace_controller_v2.packet import (
    ATTESTATION_VERSION,
    PUBLIC_PACKET_VERSION,
    PacketValidationError,
    assert_path_is_not_forbidden,
    load_implementation_attestation,
    seal_output_files,
    validate_public_packet,
    verify_execution_seal,
    write_json,
    write_jsonl,
)

from .fixtures import fictional_case


def fictional_packet() -> dict:
    return {
        "schema_version": PUBLIC_PACKET_VERSION,
        "packet_id": "fictional-unit-packet",
        "visibility": "PUBLIC_TO_IMPLEMENTATION_WORKER",
        "synthetic_only": True,
        "contains_source_media": False,
        "contains_expected_outputs": False,
        "model_inputs_only": True,
        "case_order_frozen": True,
        "cases": [fictional_case()],
    }


def test_public_packet_rejects_evaluator_fields() -> None:
    packet = fictional_packet()
    packet["cases"][0]["expected_action"] = {"type": "finalize"}
    with pytest.raises(
        PacketValidationError, match="PACKET_PRIVATE_LABEL_KEY"
    ):
        validate_public_packet(packet)


def test_forbidden_key_path_is_rejected_before_use(tmp_path: Path) -> None:
    forbidden = (
        tmp_path
        / "data/rehearsal_plan/controller_v2_holdout/"
        "restricted_evaluator_key.json"
    )
    with pytest.raises(
        PacketValidationError, match="FORBIDDEN_EVALUATOR_KEY_PATH"
    ):
        assert_path_is_not_forbidden(repo_root=tmp_path, path=forbidden)


def test_implementation_attestation_must_be_affirmative(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attestation.json"
    value = {
        "schema_version": ATTESTATION_VERSION,
        "implementation_worker": "fictional-test-worker",
        "attested_at": "2026-09-21T00:00:00Z",
        "forbidden_evaluator_key_not_accessed": True,
        "holdout_not_executed_during_implementation": True,
        "no_expected_outputs_or_labels_inspected": False,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(
        PacketValidationError, match="IMPLEMENTATION_ATTESTATION_FALSE"
    ):
        load_implementation_attestation(path)


def test_execution_manifest_seal_detects_tampering(tmp_path: Path) -> None:
    write_jsonl(tmp_path / "results.jsonl", [{"case_id": "fictional"}])
    write_jsonl(
        tmp_path / "calls.jsonl",
        [{"raw_output_utf8": '{"action_index":0}'}],
    )
    write_json(
        tmp_path / "execution_manifest.json",
        {
            "correctness_scored": False,
            "evaluator_labels_loaded": False,
        },
    )
    seal_output_files(
        tmp_path,
        names=["results.jsonl", "calls.jsonl", "execution_manifest.json"],
        input_commitments={"public_packet_sha256": "sha256:fictional"},
    )
    assert verify_execution_seal(tmp_path)
    os.chmod(tmp_path / "calls.jsonl", 0o644)
    with (tmp_path / "calls.jsonl").open("ab") as handle:
        handle.write(b"tamper\\n")
    assert not verify_execution_seal(tmp_path)


def test_persisted_call_records_exclude_prompts_and_request_payloads(
    tmp_path: Path,
) -> None:
    calls = [
        {
            "case_id": "fictional",
            "phase": "action_head",
            "request_hash": "sha256:abc",
            "system_prompt_sha256": "sha256:def",
            "grammar_hash": "sha256:ghi",
            "raw_output_utf8": '{"action_index":0}',
            "raw_sha256": "sha256:jkl",
            "prompt_tokens": 12,
            "generated_tokens": 4,
            "latency_seconds": 0.1,
            "peak_rss_kib": 100,
            "peak_rss_bytes": 102400,
        }
    ]
    write_jsonl(tmp_path / "calls.jsonl", calls)
    persisted = [
        json.loads(line)
        for line in (tmp_path / "calls.jsonl").read_text().splitlines()
    ]
    forbidden = {
        "system",
        "system_prompt",
        "payload",
        "request_payload",
        "messages",
    }
    assert forbidden.isdisjoint(persisted[0])
    assert persisted[0]["raw_output_utf8"] == '{"action_index":0}'
