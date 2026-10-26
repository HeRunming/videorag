from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/p23_102_post_acquisition_orchestrator.py"
SPEC = importlib.util.spec_from_file_location(
    "p23_102_post_acquisition_orchestrator", MODULE_PATH
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def inactive(_config: MODULE.Config) -> dict[str, Any]:
    return {
        "active": False,
        "blockers": [],
        "canonical_lock_present": False,
        "parallel_lock_held": False,
        "matching_processes": [],
    }


def copy_authoritative_readiness_fixture(tmp_path: Path) -> MODULE.Config:
    root = tmp_path / "repo"
    root.mkdir()
    config = MODULE.default_config(root)
    files = [
        ROOT
        / "data/rehearsal_plan/exogenous_restoration_protocol_v2.json",
        ROOT
        / "data/rehearsal_plan/p23_102_acquire_ground_act_rehearsal_v1.json",
        ROOT / MODULE.TECHNICAL_SMOKE_V2_FREEZE_PATH,
        ROOT / MODULE.TECHNICAL_SMOKE_V2_ATTESTATION_PATH,
        ROOT / MODULE.TECHNICAL_SMOKE_V2_RUNNER_PATH,
        ROOT / MODULE.ADAPTER_ATTESTATION_PATH,
        ROOT / MODULE.REHEARSAL_RUNNER_PATH,
        ROOT / MODULE.CONTROLLER_PATH,
        ROOT / MODULE.PROCESS_PATH,
        ROOT
        / "data/restricted/epic_p23_102_family_mining_v1_dev/"
        "candidate_registry.json",
        ROOT
        / "data/restricted/epic_p23_102_source_v1/manifests/"
        "epic_p23_102_exact_manifest.json",
        ROOT
        / "data/restricted/epic_p23_102_source_v1/"
        "post_acquisition_orchestrator_v1/receipts/"
        "verify_full_timeline.json",
    ]
    files.extend(
        ROOT / "data/restricted/epic_p23_102_full_timeline_index_v1" / name
        for name in MODULE.TIMELINE_FILES
    )
    files.extend(
        (
            ROOT
            / "data/restricted/epic_p23_102_full_timeline_index_v1/"
            "checkpoints/P23_102"
        ).glob("*.json")
    )
    files.extend(
        (
            ROOT
            / "data/restricted/"
            "epic_p23_102_machine_provisional_families_v1"
        ).glob("*.json")
    )
    for source in files:
        destination = root / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    config.final_media.parent.mkdir(parents=True, exist_ok=True)
    with config.final_media.open("wb") as handle:
        handle.truncate(MODULE.EXPECTED_BYTES)
    return config


class SyntheticRunner:
    def __init__(
        self,
        outputs: Mapping[str, Path],
        *,
        fail_once: set[str] | None = None,
    ) -> None:
        self.outputs = dict(outputs)
        self.fail_once = set(fail_once or set())
        self.calls: list[str] = []

    def __call__(
        self, argv: Sequence[str], cwd: Path
    ) -> subprocess.CompletedProcess[str]:
        assert cwd.is_dir()
        name = argv[-1]
        self.calls.append(name)
        if name in self.fail_once:
            self.fail_once.remove(name)
            return subprocess.CompletedProcess(
                argv,
                17,
                f"partial stdout for {name}\n",
                f"synthetic failure for {name}\n",
            )
        output = self.outputs[name]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"complete:{name}\n", encoding="utf-8")
        stdout = (
            json.dumps(
                {
                    "verified": True,
                    "decision": MODULE.TIMELINE_READY,
                }
            )
            if name == "verify_full_timeline"
            else json.dumps({"stage": name, "complete": True})
        )
        return subprocess.CompletedProcess(argv, 0, stdout, "")


def synthetic_orchestrator(
    tmp_path: Path,
    *,
    fail_once: set[str] | None = None,
) -> tuple[MODULE.Orchestrator, SyntheticRunner, dict[str, Path]]:
    root = tmp_path / "repo"
    root.mkdir()
    config = MODULE.default_config(root, state_dir="state")
    controls: dict[str, Path] = {}
    outputs: dict[str, Path] = {}
    stages: list[MODULE.Stage] = []

    for index, name in enumerate(MODULE.STAGE_NAMES):
        control = root / "controls" / f"{name}.txt"
        control.parent.mkdir(parents=True, exist_ok=True)
        control.write_text(f"control:{name}\n", encoding="utf-8")
        output = root / "outputs" / f"{name}.txt"
        controls[name] = control
        outputs[name] = output

        previous = (
            outputs[MODULE.STAGE_NAMES[index - 1]] if index else None
        )

        def make_prerequisite(
            prior: Path | None,
            stage_name: str,
        ) -> Callable[[MODULE.Config], dict[str, Any]]:
            def prerequisite(
                _config: MODULE.Config,
            ) -> dict[str, Any]:
                if prior is not None and not prior.is_file():
                    raise MODULE.PrerequisiteError(
                        f"SYNTHETIC_PREVIOUS_STAGE_MISSING:{stage_name}"
                    )
                return {
                    "passed": True,
                    "previous": str(prior) if prior else None,
                }

            return prerequisite

        def make_validator(
            path: Path,
            stage_name: str,
        ) -> Callable[[MODULE.Config], dict[str, Any]]:
            def validate(
                _config: MODULE.Config,
            ) -> dict[str, Any]:
                if not path.is_file():
                    raise MODULE.OutputValidationError(
                        f"SYNTHETIC_OUTPUT_MISSING:{stage_name}"
                    )
                payload = path.read_text(encoding="utf-8")
                if payload != f"complete:{stage_name}\n":
                    raise MODULE.OutputValidationError(
                        f"SYNTHETIC_OUTPUT_INVALID:{stage_name}"
                    )
                return {
                    "stage": stage_name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }

            return validate

        stages.append(
            MODULE.Stage(
                name=name,
                argv=lambda _config, stage_name=name: [
                    "synthetic",
                    "run",
                    stage_name,
                ],
                controls=lambda _config, path=control: [path],
                outputs=lambda _config, path=output: [path],
                validate_outputs=make_validator(output, name),
                prerequisite=make_prerequisite(previous, name),
                adopt_existing_outputs=name != "verify_full_timeline",
            )
        )

    runner = SyntheticRunner(outputs, fail_once=fail_once)
    orchestrator = MODULE.Orchestrator(
        config,
        stages=stages,
        runner=runner,
        activity_probe=inactive,
    )
    return orchestrator, runner, outputs


def test_incomplete_download_blocks_assembly(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    config = MODULE.default_config(root, state_dir="state")
    config = dataclasses.replace(config, expected_bytes=12)
    config.part_media.parent.mkdir(parents=True, exist_ok=True)
    config.part_media.write_bytes(b"abcd")
    config.segment_dir.mkdir(parents=True, exist_ok=True)
    first = config.segment_dir / "segment-4-7"
    first.write_bytes(b"efgh")
    manifest = {
        "asset_id": MODULE.ASSET_ID,
        "expected_bytes": 12,
        "official_md5": config.official_md5,
        "segments": {
            "4-7": {
                "start": 4,
                "end": 7,
                "status": "complete",
                "observed_bytes": 4,
                "sha256": hashlib.sha256(b"efgh").hexdigest(),
                "path": first.name,
            },
            "8-11": {
                "start": 8,
                "end": 11,
                "status": "pending",
                "observed_bytes": None,
                "sha256": None,
                "path": "segment-8-11",
            },
        },
    }
    config.segment_manifest.write_bytes(canonical(manifest))

    with pytest.raises(
        MODULE.PrerequisiteError,
        match="PARALLEL_SEGMENT_NOT_COMPLETE:8",
    ):
        MODULE.validate_parallel_segments_complete(config)


def test_active_acquisition_refuses_premature_execution(
    tmp_path: Path,
) -> None:
    orchestrator, runner, _ = synthetic_orchestrator(tmp_path)
    orchestrator.activity_probe = lambda _config: {
        "active": True,
        "blockers": ["PARALLEL_ACQUISITION_LOCK_HELD:fixture"],
        "canonical_lock_present": False,
        "parallel_lock_held": True,
        "matching_processes": [{"pid": 123}],
    }

    with pytest.raises(
        MODULE.ActiveAcquisitionError,
        match="PARALLEL_ACQUISITION_LOCK_HELD",
    ):
        orchestrator.run_next()
    assert runner.calls == []


def test_stale_receipt_fails_closed_without_rerun(tmp_path: Path) -> None:
    orchestrator, runner, outputs = synthetic_orchestrator(tmp_path)
    first = orchestrator.run_all()
    assert first["status"]["all_stages_complete"] is True
    original_calls = list(runner.calls)

    outputs["build_full_timeline"].write_text(
        "tampered\n", encoding="utf-8"
    )
    with pytest.raises(
        MODULE.StaleReceiptError,
        match="RECEIPT_BINDING_STALE|RECEIPT_OUTPUT_VALIDATION_STALE",
    ):
        orchestrator.run_all()
    assert runner.calls == original_calls


def test_command_failure_records_attempt_and_resume_skips_completed_stage(
    tmp_path: Path,
) -> None:
    orchestrator, runner, _ = synthetic_orchestrator(
        tmp_path, fail_once={"build_full_timeline"}
    )

    with pytest.raises(
        MODULE.CommandFailure,
        match="STAGE_COMMAND_FAILED:build_full_timeline:return_code=17",
    ):
        orchestrator.run_all()

    first_receipt = orchestrator.receipt_path(orchestrator.stages[0])
    second_receipt = orchestrator.receipt_path(orchestrator.stages[1])
    assert first_receipt.is_file()
    assert not second_receipt.exists()
    attempts = sorted(orchestrator.config.attempts_dir.glob("*.json"))
    failed = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in attempts
        if "build_full_timeline" in path.name
    ]
    assert len(failed) == 1
    assert failed[0]["return_code"] == 17
    assert failed[0]["command_argv"] == [
        "synthetic",
        "run",
        "build_full_timeline",
    ]
    assert failed[0]["stdout"]["sha256"] == hashlib.sha256(
        b"partial stdout for build_full_timeline\n"
    ).hexdigest()
    assert failed[0]["stderr"]["sha256"] == hashlib.sha256(
        b"synthetic failure for build_full_timeline\n"
    ).hexdigest()

    resumed = orchestrator.run_all()
    assert resumed["status"]["all_stages_complete"] is True
    assert runner.calls.count("assemble_exact") == 1
    assert runner.calls.count("build_full_timeline") == 2
    assert runner.calls[-1] == "validate_rehearsal_prerequisites"


def test_idempotence_reuses_valid_receipts_and_outputs(
    tmp_path: Path,
) -> None:
    orchestrator, runner, _ = synthetic_orchestrator(tmp_path)
    first = orchestrator.run_all()
    calls_after_first = list(runner.calls)
    receipt_bytes = {
        stage.name: orchestrator.receipt_path(stage).read_bytes()
        for stage in orchestrator.stages
    }

    second = orchestrator.run_all()
    assert first["status"]["all_stages_complete"] is True
    assert second["status"]["all_stages_complete"] is True
    assert runner.calls == calls_after_first
    assert all(
        action["action"] == "skipped_valid_receipt"
        for action in second["actions"]
    )
    assert receipt_bytes == {
        stage.name: orchestrator.receipt_path(stage).read_bytes()
        for stage in orchestrator.stages
    }


def test_existing_valid_output_is_adopted_without_command_execution(
    tmp_path: Path,
) -> None:
    orchestrator, runner, outputs = synthetic_orchestrator(tmp_path)
    first = orchestrator.stages[0]
    outputs[first.name].parent.mkdir(parents=True, exist_ok=True)
    outputs[first.name].write_text(
        f"complete:{first.name}\n", encoding="utf-8"
    )

    result = orchestrator.run_next()
    assert result["result"]["action"] == "adopted_existing_valid_outputs"
    assert runner.calls == []
    receipt = json.loads(
        orchestrator.receipt_path(first).read_text(encoding="utf-8")
    )
    assert receipt["execution"]["execution_kind"] == (
        "adopted_existing_valid_outputs"
    )
    assert receipt["execution"]["return_code"] is None
    assert receipt["execution"]["command_argv"] == [
        "synthetic",
        "run",
        "assemble_exact",
    ]


def test_current_authoritative_bundle_and_timeline_are_accepted() -> None:
    config = MODULE.default_config(ROOT)

    timeline = MODULE.validate_timeline_outputs(config)
    bundle = MODULE.validate_machine_provisional_bundle(config)

    assert timeline["status"] == "COMPLETE"
    assert timeline["decision"] == MODULE.TIMELINE_READY
    assert bundle["decision"] == MODULE.MACHINE_BUNDLE_READY
    assert bundle["accepted_family_count"] == 0
    assert bundle["accepted_ses_count"] == 0
    assert bundle["evidence_coverage_claim_asserted"] is False
    assert bundle["timeline_bindings"]["verifier_receipt_sha256"].startswith(
        "sha256:"
    )


def test_machine_bundle_schema_drift_fails_closed(
    tmp_path: Path,
) -> None:
    config = copy_authoritative_readiness_fixture(tmp_path)
    path = MODULE.machine_bundle_paths(config)["family_registry.json"]
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = (
        "av-trace.p23-102-machine-provisional-family-registry/2.0"
    )
    MODULE.seal(document, "payload_sha256")
    path.write_bytes(MODULE.canonical_json_bytes(document))

    with pytest.raises(
        MODULE.OutputValidationError,
        match="MACHINE_BUNDLE_IDENTITY_INVALID:family_registry.json",
    ):
        MODULE.validate_machine_provisional_bundle(config)


def test_malicious_status_only_spoof_fails_closed(
    tmp_path: Path,
) -> None:
    config = copy_authoritative_readiness_fixture(tmp_path)
    path = MODULE.machine_bundle_paths(config)["family_registry.json"]
    document = json.loads(path.read_text(encoding="utf-8"))
    document["families"] = []
    document["family_count"] = 0
    document["status"] = "MACHINE_PROVISIONAL_FROZEN"
    document["decision"] = MODULE.MACHINE_BUNDLE_READY
    document.pop("payload_sha256")
    MODULE.seal(document, "payload_sha256")
    path.write_bytes(MODULE.canonical_json_bytes(document))

    with pytest.raises(
        MODULE.OutputValidationError,
            match=(
                "MACHINE_BUNDLE_COUNT_OR_ID_INVALID|"
                "MACHINE_BUNDLE_EVIDENCE_REFERENCE_INVALID|"
                "MACHINE_BUNDLE_REFERENTIAL_HASH_BINDING_INVALID"
            ),
    ):
        MODULE.validate_machine_provisional_bundle(config)


def test_missing_input_hash_binding_fails_closed(
    tmp_path: Path,
) -> None:
    config = copy_authoritative_readiness_fixture(tmp_path)
    path = MODULE.machine_bundle_paths(config)["evidence_registry.json"]
    document = json.loads(path.read_text(encoding="utf-8"))
    document["input_bindings"] = [
        row
        for row in document["input_bindings"]
        if not row["path"].endswith("resource_manifest.json")
    ]
    document.pop("payload_sha256")
    MODULE.seal(document, "payload_sha256")
    path.write_bytes(MODULE.canonical_json_bytes(document))

    with pytest.raises(
        MODULE.OutputValidationError,
        match="MACHINE_BUNDLE_INPUT_BINDING_MISMATCH:evidence_registry.json",
    ):
        MODULE.validate_machine_provisional_bundle(config)


def test_readiness_audit_preserves_frozen_config_and_maps_current_outputs(
) -> None:
    config = MODULE.default_config(ROOT)
    before = hashlib.sha256(config.rehearsal_plan.read_bytes()).hexdigest()
    attestation = ROOT / MODULE.ADAPTER_ATTESTATION_PATH
    attestation_before = hashlib.sha256(attestation.read_bytes()).hexdigest()

    report = MODULE.audit_rehearsal_prerequisites(config)

    after = hashlib.sha256(config.rehearsal_plan.read_bytes()).hexdigest()
    assert before == after
    assert hashlib.sha256(attestation.read_bytes()).hexdigest() == (
        attestation_before
    )
    assert report["decision"] == MODULE.READINESS_REPAIR_TOKEN
    assert report["status"] == MODULE.HISTORICAL_SUPERSEDED_STATUS
    assert report["ready_for_development_rehearsal"] is False
    assert report["failed_count"] == 2
    assert report["remaining_blockers"] == [
        MODULE.ADAPTER_ATTESTATION_PATH,
        MODULE.REHEARSAL_RUNNER_PATH,
    ]
    assert report["historical_rehearsal"] == {
        "rehearsal_id": "P23_102_ACQUIRE_GROUND_ACT_REHEARSAL_V1",
        "planned_assignment_count": 640,
        "disposition": MODULE.HISTORICAL_SUPERSEDED_STATUS,
        "configuration_preserved": True,
        "adapter_attestation_preserved": True,
        "previous_receipts_preserved_as_historical": True,
        "stale_readiness_adopted_as_current": False,
        "old_freeze_execution_allowed": False,
    }
    assert report["current_development_execution_route"]["route_id"] == (
        MODULE.TECHNICAL_SMOKE_V2_FREEZE_ID
    )
    assert report["current_development_execution_route"][
        "only_current_development_execution_route"
    ] is True
    assert report["current_vs_prospective_compatibility"]
    build_rows = [
        row
        for row in report["current_vs_prospective_compatibility"]
        if row["prospective_path"].endswith("build_manifest.json")
    ]
    assert build_rows[0]["current_authoritative_requirement"] == {
        "status": "COMPLETE",
        "decision": MODULE.TIMELINE_READY,
        "full_hash_and_verifier_receipt_binding_required": True,
    }


def test_historical_controller_and_process_hash_drift_is_exact() -> None:
    report = MODULE.audit_rehearsal_prerequisites(
        MODULE.default_config(ROOT)
    )

    assert report["code_drift_rows"] == [
        {
            "path": MODULE.CONTROLLER_PATH,
            "drift_kind": "HASH_OR_SIZE_MISMATCH",
            "historical_binding_present": True,
            "expected_sha256": (
                "sha256:"
                "18b5a4e78e3a88253ff8f8f6568418bccbabb1e22a99f2ee95727a9a044f1b6f"
            ),
            "actual_sha256": (
                "sha256:"
                "e4f1acd34ce3af160e0e827eddeb3afd401d6a31ee141b811d28b1eac2feb773"
            ),
            "expected_bytes": 20465,
            "actual_bytes": 21403,
        },
        {
            "path": MODULE.PROCESS_PATH,
            "drift_kind": "MISSING_HISTORICAL_BINDING",
            "historical_binding_present": False,
            "expected_sha256": None,
            "actual_sha256": (
                "sha256:"
                "f011ee6a24aaabd4c13f534f7d64c5363abf42e06e4839e6bcead0152cb7892c"
            ),
            "expected_bytes": None,
            "actual_bytes": 19278,
        },
    ]


def test_hash_drift_is_recomputed_and_stale_ready_report_rejected(
    tmp_path: Path,
) -> None:
    config = copy_authoritative_readiness_fixture(tmp_path)
    report = MODULE.audit_rehearsal_prerequisites(config)
    MODULE.atomic_json(config.readiness_report, report)
    controller = config.root / MODULE.CONTROLLER_PATH
    controller.write_bytes(controller.read_bytes() + b"\n# drift\n")

    with pytest.raises(
        MODULE.OutputValidationError,
        match="READINESS_REPORT_STALE",
    ):
        MODULE.validate_readiness_report(config)


def test_readiness_audit_never_executes_old_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("old freeze execution attempted")

    monkeypatch.setattr(MODULE.subprocess, "run", forbidden)

    report = MODULE.audit_rehearsal_prerequisites(
        MODULE.default_config(ROOT)
    )

    assert report["rehearsal_executed"] is False
    assert report["historical_rehearsal"][
        "old_freeze_execution_allowed"
    ] is False
    runner_rows = [
        row
        for row in report["prerequisites"]
        if row["path"] == MODULE.REHEARSAL_RUNNER_PATH
    ]
    assert runner_rows[0]["passed"] is False
    assert "old_freeze_execution:FORBIDDEN" in runner_rows[0]["checks"]


def test_status_reports_valid_readiness_despite_unrelated_stale_stage(
    tmp_path: Path,
) -> None:
    orchestrator, _, _ = synthetic_orchestrator(tmp_path)
    readiness_stage = orchestrator.stages[-1]
    readiness_path = orchestrator.config.readiness_report
    readiness_path.parent.mkdir(parents=True, exist_ok=True)
    readiness_path.write_bytes(
        canonical({"ready_for_development_rehearsal": True})
    )
    orchestrator.stages = (
        *orchestrator.stages[:-1],
        dataclasses.replace(
            readiness_stage,
            validate_outputs=lambda _config: {"valid": True},
            outputs=lambda _config: [readiness_path],
        ),
    )
    for stage in orchestrator.stages:
        if stage is orchestrator.stages[-2]:
            continue
        output = stage.outputs(orchestrator.config)[0]
        output.parent.mkdir(parents=True, exist_ok=True)
        if output == readiness_path:
            orchestrator._adopt(stage)
            continue
        output.write_text(f"complete:{stage.name}\n", encoding="utf-8")
        orchestrator._adopt(stage)

    status = orchestrator.status()

    assert status["all_stages_complete"] is False
    assert status["stages"][-2]["state"] != "complete"
    assert status["stages"][-1]["state"] == "complete"
    assert status["ready_for_development_rehearsal"] is True
