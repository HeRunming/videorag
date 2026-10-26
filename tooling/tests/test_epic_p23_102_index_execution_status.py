from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATUS_PATH = (
    ROOT
    / "data/rehearsal_plan/epic_p23_102_index_execution_status_v1.json"
)
PLAN_PATH = (
    ROOT / "data/rehearsal_plan/epic_p23_102_full_timeline_index_v1.json"
)
EXACT_MANIFEST_PATH = (
    ROOT
    / "data/restricted/epic_p23_102_source_v1/manifests/"
    "epic_p23_102_exact_manifest.json"
)
ADDENDUM_PATH = (
    ROOT
    / "docs/review/epic_p23_102_index_execution_status_addendum.md"
)

DECISION = "EPIC_P23_102_INDEX_EXECUTION_STATUS_ADDENDUM_READY"
CONFIG_HASH = (
    "sha256:4e8f231d41c9df1c707d68194f22d8d26146bb905de12ca13ef52b4dfb1541c4"
)
SOURCE_HASH = (
    "sha256:58f53a4ae0089bb3df4299d112d3e16740a36febd7da9aabea76bf17963da822"
)

STABLE_OBSERVATION: dict[str, Any] = {
    "observed_at_utc": "2026-10-14T04:21:26.412245Z",
    "observed_at_local": "2026-10-14T12:21:26.412245+08:00",
    "orchestrator_pid": 2729700,
    "orchestrator_ppid": 2729699,
    "build_pid": 2729701,
    "build_ppid": 2729700,
    "started_at_utc": "2026-10-14T03:54:58Z",
    "started_at_local": "2026-10-14T11:54:58+08:00",
    "acquisition_probe_at_utc": "2026-10-14T04:21:26.528538Z",
}


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def payload_hash(document: dict[str, Any]) -> str:
    body = {
        key: value
        for key, value in document.items()
        if key != "status_payload_sha256"
    }
    return "sha256:" + hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def generate_execution_snapshot(observation: dict[str, Any]) -> dict[str, Any]:
    """Generate the PID/time-varying section from explicit observation input."""
    return {
        "observation_mode": "explicit_stable_snapshot",
        "observed_at_utc": observation["observed_at_utc"],
        "observed_at_local": observation["observed_at_local"],
        "current_state": "BUILD_RUNNING",
        "orchestrator_process": {
            "pid": observation["orchestrator_pid"],
            "ppid": observation["orchestrator_ppid"],
            "started_at_utc": observation["started_at_utc"],
            "started_at_local": observation["started_at_local"],
            "stat": "S",
            "command_argv": [
                "python",
                "tools/p23_102_post_acquisition_orchestrator.py",
                "--run-all",
            ],
        },
        "build_process": {
            "pid": observation["build_pid"],
            "ppid": observation["build_ppid"],
            "started_at_utc": observation["started_at_utc"],
            "started_at_local": observation["started_at_local"],
            "stat": "Rl",
            "command_argv": [
                "/opt/conda/envs/torch-base/bin/python",
                (
                    "/path/to/av-trace"
                    "build_epic_p23_102_full_timeline.py"
                ),
                "--repo-root",
                "/path/to/av-trace",
                "--plan",
                (
                    "data/rehearsal_plan/"
                    "epic_p23_102_full_timeline_index_v1.json"
                ),
                "--mode",
                "full",
                "--resume",
                "--threads",
                "8",
            ],
        },
        "acquisition_activity_probe": {
            "observed_at_utc": observation["acquisition_probe_at_utc"],
            "active": False,
            "blockers": [],
            "canonical_lock_present": False,
            "parallel_lock_held": False,
            "matching_processes": [],
        },
        "checkpoint_progress": {
            "expected_layers": [
                "source_probe",
                "speech_asr",
                "siglip2_visual",
                "clap_audio",
            ],
            "observed_count": 2,
            "expected_count": 4,
            "observed": [
                {
                    "layer": "source_probe",
                    "path": (
                        "data/restricted/"
                        "epic_p23_102_full_timeline_index_v1/checkpoints/"
                        "P23_102/source_probe.json"
                    ),
                    "bytes": 2002,
                    "mode": "0600",
                    "mtime_utc": "2026-10-14T03:55:34.156535Z",
                    "sha256": (
                        "sha256:2bf8fad84cfe786887105d140edd620c00156de4b"
                        "91e5b414394ce321a57cc5e"
                    ),
                    "record_count": 1,
                    "config_hash": CONFIG_HASH,
                    "checkpoint_key": (
                        "sha256:0ad85e8a85796f2c02ffda1509611ded074b0a4e"
                        "ee80226af451c1d7ee6cd57d"
                    ),
                    "payload_hash": (
                        "sha256:a09a8b330b171efa0140312788c071c2a4ebe124"
                        "5cc35823e4b40f7c5105088e"
                    ),
                },
                {
                    "layer": "speech_asr",
                    "path": (
                        "data/restricted/"
                        "epic_p23_102_full_timeline_index_v1/checkpoints/"
                        "P23_102/speech_asr.json"
                    ),
                    "bytes": 69363,
                    "mode": "0600",
                    "mtime_utc": "2026-10-14T03:56:32.513117Z",
                    "sha256": (
                        "sha256:fca6702d2808e6656da7fedf4754c144acd052b"
                        "3f9fab6f92dd6825e8f95995e"
                    ),
                    "record_count": 119,
                    "config_hash": CONFIG_HASH,
                    "checkpoint_key": (
                        "sha256:9b404fb659c8a8ada10d8adad1c6390cb74acc37"
                        "25a6233c64e94df1bc06b344"
                    ),
                    "payload_hash": (
                        "sha256:afb40b1de3c190fda91d4538adfc3eb44d8b48"
                        "bd4d7b3c4fc4db21f1111bb9ca"
                    ),
                },
            ],
            "not_yet_observed": ["siglip2_visual", "clap_audio"],
        },
        "top_level_artifacts_at_observation": {
            "present": [],
            "not_yet_present": [
                "segment_manifest.json",
                "observation_manifest.json",
                "full_timeline_index.json",
                "resource_manifest.json",
                "checkpoint_manifest.json",
                "build_manifest.json",
            ],
        },
        "directory_modes_at_observation": [
            {
                "path": (
                    "data/restricted/"
                    "epic_p23_102_full_timeline_index_v1"
                ),
                "mode": "0700",
                "compliant": True,
            },
            {
                "path": (
                    "data/restricted/"
                    "epic_p23_102_full_timeline_index_v1/checkpoints"
                ),
                "mode": "0755",
                "compliant": False,
            },
            {
                "path": (
                    "data/restricted/"
                    "epic_p23_102_full_timeline_index_v1/checkpoints/P23_102"
                ),
                "mode": "0700",
                "compliant": True,
            },
        ],
    }


def validate_status(document: dict[str, Any]) -> list[str]:
    failures: list[str] = []

    def check(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    check(
        document.get("schema_version")
        == "av-trace.epic-p23-102-index-execution-status/1.0",
        "schema",
    )
    check(document.get("decision") == DECISION, "decision")
    check(
        document.get("status_payload_sha256") == payload_hash(document),
        "payload_hash",
    )
    scope = document.get("scope", {})
    check(scope.get("live_files_modified") is False, "non_destructive")
    check(scope.get("frozen_plan_modified") is False, "plan_immutable")
    check(scope.get("running_build_modified") is False, "build_immutable")

    bindings = document.get("immutable_bindings", {})
    plan = bindings.get("frozen_plan", {})
    exact = bindings.get("exact_acquisition_ready", {})
    check(
        plan.get("frozen_current_execution_status")
        == "ACQUISITION_PENDING_DO_NOT_RUN_FULL_MEDIA",
        "stale_field_bound",
    )
    check(
        exact.get("required_and_observed_status")
        == "COMPLETE_VERIFIED_READY",
        "exact_ready",
    )
    check(exact.get("media_sha256") == SOURCE_HASH, "source_hash")

    supersession = document.get("operational_supersession", {})
    check(
        supersession.get("superseded_for_operations") is True,
        "supersession",
    )
    check(
        supersession.get("frozen_plan_hash_preserved") is True,
        "plan_hash_preserved",
    )
    check(
        supersession.get("observed_checkpoint_config_hash") == CONFIG_HASH,
        "config_hash",
    )

    snapshot = document.get("execution_snapshot", {})
    check(snapshot.get("current_state") == "BUILD_RUNNING", "snapshot_state")
    progress = snapshot.get("checkpoint_progress", {})
    check(progress.get("observed_count") == 2, "observed_checkpoint_count")
    check(progress.get("expected_count") == 4, "expected_checkpoint_count")
    check(
        {row.get("config_hash") for row in progress.get("observed", [])}
        == {CONFIG_HASH},
        "checkpoint_config_uniform",
    )

    machine = document.get("state_machine", {})
    transitions = {
        (row.get("from"), row.get("to"))
        for row in machine.get("allowed_forward_transitions", [])
    }
    check(
        transitions
        == {
            ("BUILD_RUNNING", "BUILD_COMPLETE_PENDING_VERIFY"),
            ("BUILD_COMPLETE_PENDING_VERIFY", "VERIFIED_READY"),
        },
        "state_transitions",
    )
    check(
        machine.get("shortcut_transition_forbidden")
        == {"from": "BUILD_RUNNING", "to": "VERIFIED_READY"},
        "shortcut_forbidden",
    )

    artifacts = document.get("canonical_artifact_requirements", {})
    check(artifacts.get("required_checkpoint_count") == 4, "checkpoint_count")
    check(
        artifacts.get("required_top_level_artifact_count") == 6,
        "artifact_count",
    )
    check(artifacts.get("required_directory_mode") == "0700", "dir_mode")
    check(artifacts.get("required_file_mode") == "0600", "file_mode")
    check(artifacts.get("required_source_sha256") == SOURCE_HASH, "source")
    check(artifacts.get("required_config_hash") == CONFIG_HASH, "config")

    repairs = document.get("post_build_custody_repairs", {})
    actions = repairs.get("ordered_actions", [])
    check(
        repairs.get("execution_status")
        == "QUEUED_NOT_EXECUTED_BY_THIS_ADDENDUM",
        "repair_not_executed",
    )
    check(
        [row.get("order") for row in actions] == [1, 2, 3, 4, 5],
        "repair_order",
    )
    cleanup = next(
        (
            row
            for row in actions
            if row.get("action") == "REMOVE_OBSOLETE_NONCANONICAL_RANGE_PART"
        ),
        {},
    )
    check(
        cleanup.get("path", "").endswith(".P23_102.MP4.range.part"),
        "cleanup_path",
    )
    check(
        "No active acquisition or acquisition lock exists."
        in cleanup.get("preconditions", []),
        "cleanup_idle_gate",
    )

    dates = document.get("date_semantics", {})
    check(dates.get("task_start_date") == "2026-10-13", "task_start")
    check(
        dates.get("exact_acquisition_finalization_date") == "2026-10-14",
        "acquisition_finalization",
    )
    governance = document.get("governance_boundary", {})
    check(governance.get("development_only") is True, "development_only")
    check(governance.get("future_test_eligible") is False, "test_ineligible")
    check(
        governance.get("scientific_evaluation_claimed") is False,
        "no_evaluation_claim",
    )
    return failures


def test_status_record_is_valid_and_deterministically_sealed() -> None:
    document = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    assert validate_status(document) == []
    assert STATUS_PATH.read_bytes().endswith(b"\n")
    assert b"TO_BE_" not in STATUS_PATH.read_bytes()
    assert payload_hash(document) == document["status_payload_sha256"]


def test_explicit_observation_generator_matches_stable_snapshot() -> None:
    document = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    assert document["execution_snapshot"] == generate_execution_snapshot(
        STABLE_OBSERVATION
    )


def test_generator_tolerates_pid_and_time_changes_via_input() -> None:
    changed = copy.deepcopy(STABLE_OBSERVATION)
    changed["observed_at_utc"] = "2030-01-02T03:04:05.000000Z"
    changed["observed_at_local"] = "2030-01-02T11:04:05.000000+08:00"
    changed["orchestrator_pid"] = 101
    changed["build_pid"] = 102
    generated = generate_execution_snapshot(changed)
    assert generated["observed_at_utc"] == changed["observed_at_utc"]
    assert generated["orchestrator_process"]["pid"] == 101
    assert generated["build_process"]["pid"] == 102
    assert generated["checkpoint_progress"]["expected_count"] == 4
    assert generated["checkpoint_progress"]["observed_count"] == 2


def test_validator_fails_closed_on_tampered_state_or_seal() -> None:
    document = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    state_tamper = copy.deepcopy(document)
    state_tamper["execution_snapshot"]["current_state"] = "VERIFIED_READY"
    assert "snapshot_state" in validate_status(state_tamper)
    assert "payload_hash" in validate_status(state_tamper)

    seal_tamper = copy.deepcopy(document)
    seal_tamper["status_payload_sha256"] = "sha256:" + "0" * 64
    assert validate_status(seal_tamper) == ["payload_hash"]


def test_frozen_plan_and_exact_ready_manifest_bindings() -> None:
    document = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    bindings = document["immutable_bindings"]
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    exact = json.loads(EXACT_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert sha256(PLAN_PATH) == bindings["frozen_plan"]["raw_file_sha256"]
    assert (
        "sha256:" + hashlib.sha256(canonical_json_bytes(plan)).hexdigest()
        == bindings["frozen_plan"]["canonical_json_sha256"]
    )
    assert plan["current_execution_status"] == (
        "ACQUISITION_PENDING_DO_NOT_RUN_FULL_MEDIA"
    )
    assert sha256(EXACT_MANIFEST_PATH) == (
        bindings["exact_acquisition_ready"]["manifest_sha256"]
    )
    assert exact["status"] == "COMPLETE_VERIFIED_READY"
    assert "sha256:" + exact["media"]["sha256"] == SOURCE_HASH


def test_addendum_states_custody_and_governance_boundaries() -> None:
    text = ADDENDUM_PATH.read_text(encoding="utf-8")
    for required in (
        "BUILD_RUNNING",
        "BUILD_COMPLETE_PENDING_VERIFY",
        "VERIFIED_READY",
        "ACQUISITION_PENDING_DO_NOT_RUN_FULL_MEDIA",
        "COMPLETE_VERIFIED_READY",
        ".P23_102.MP4.range.part",
        "mode `0700`",
        "mode `0600`",
        "`future_test_eligible: false`",
        DECISION,
    ):
        assert required in text
    assert "This addendum records repairs; it does not execute them." in text
