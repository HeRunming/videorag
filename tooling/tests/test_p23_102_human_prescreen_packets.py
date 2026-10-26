from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_human_prescreen_packets.py"
OUTPUT_ROOT = (
    ROOT / "data/rehearsal_plan/p23_102_human_prescreen_packets_v1"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "p23_102_human_prescreen_packets",
        TOOL_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_committed() -> dict[str, bytes]:
    return {
        path.relative_to(OUTPUT_ROOT).as_posix(): path.read_bytes()
        for path in sorted(OUTPUT_ROOT.rglob("*"))
        if path.is_file()
    }


def json_values(rendered: dict[str, bytes]) -> dict[str, dict]:
    return {
        path: json.loads(content)
        for path, content in rendered.items()
        if path.endswith(".json")
    }


def completed_import(tool, rendered: dict[str, bytes]) -> dict:
    values = json_values(rendered)
    forms = [
        value
        for path, value in sorted(values.items())
        if path.startswith("lead_forms/")
    ]
    ledger = {
        "format_version": "1.0.0",
        "record_type": "p23_source_exposure_ledger",
        "ledger_id": tool.LEDGER_ID,
        "source_group_id": tool.SOURCE_GROUP_ID,
        "distribution_authorized": False,
        "derivative_group_rule": (
            "All derivatives originating from a P23 source use source group P23."
        ),
        "events": [
            {
                "event_id": "P23-EXPOSURE-0001",
                "occurred_at": "2026-10-14T09:30:00+08:00",
                "source_group_id": "P23",
                "source_reference": "P23_102",
                "derivative_reference": "P23_102.prescreen",
                "exposure_kind": "SOURCE_REVIEW",
            }
        ],
    }
    tool._seal(ledger, "ledger_sha256")
    return {
        "format_version": "1.0.0",
        "record_type": "p23_102_human_prescreen_import",
        "packet_id": tool.PACKET_ID,
        "source_group_id": tool.SOURCE_GROUP_ID,
        "distribution_authorized": False,
        "responses": [
            {
                "lead_id": form["lead_id"],
                "form_sha256": form["form_sha256"],
                "review_checks": {
                    name: {
                        "selection": "UNCERTAIN",
                        "notes": "Review note.",
                    }
                    for name in tool.CHECK_NAMES
                },
                "prescreen_choice": "REPAIR_AND_RECHECK",
                "free_rationale": "Additional source review is required.",
            }
            for form in forms
        ],
        "source_exposure_ledger": ledger,
    }


def test_build_is_deterministic_and_matches_committed_packet() -> None:
    tool = load_tool()
    inputs = tool.load_inputs(ROOT)
    first = tool.build_artifacts(inputs)
    second = tool.build_artifacts(inputs)
    committed = read_committed()

    assert first == second == committed
    assert len(committed) == 25
    tool.validate_artifacts(committed, inputs=inputs)

    manifest = json.loads(committed["artifact_manifest.json"])
    assert manifest["completion_token"] == tool.READY
    assert manifest["distribution_authorized"] is False
    assert manifest["package_content_sha256"].startswith("sha256:")


def test_twenty_leads_are_represented_exactly_once_with_exact_timestamps() -> None:
    tool = load_tool()
    inputs = tool.load_inputs(ROOT)
    rendered = read_committed()
    values = json_values(rendered)
    forms = [
        value
        for path, value in values.items()
        if path.startswith("lead_forms/")
    ]

    assert len(forms) == 20
    assert len({form["lead_id"] for form in forms}) == 20
    assert len({form["form_id"] for form in forms}) == 20

    expected = {}
    for candidate in inputs["registry"]["candidates"]:
        intervals = {
            (handle["start_us"], handle["end_us"])
            for handle in candidate["evidence_handles"]
        }
        expected[tool._public_lead_id(candidate["candidate_id"])] = intervals
    actual = {
        form["lead_id"]: {
            (handle["start_us"], handle["end_us"])
            for handle in form["timestamp_handles"]
        }
        for form in forms
    }
    assert actual == expected

    for form in forms:
        assert set(form["review_checks"]) == set(tool.CHECK_NAMES)
        assert form["prescreen_choice"]["options"] == list(
            tool.PRESCREEN_CHOICES
        )
        assert form["prescreen_choice"]["selection"] is None
        assert form["free_rationale"] == ""
        assert {
            row["modality"]
            for row in form["neutral_modality_hypotheses"]
        } == {"visual", "ambient_audio"}


def test_distribution_ledger_calibration_and_blank_boundaries() -> None:
    tool = load_tool()
    rendered = read_committed()
    values = json_values(rendered)

    for value in values.values():
        tool._validate_distribution_flags(value, "DISTRIBUTION_FLAG")

    ledger = values["source_exposure_ledger.json"]
    assert ledger["events"] == []
    assert ledger["source_group_id"] == "P23"
    assert ledger["covered_source_ids"] == ["P23_102"]
    assert "source group P23" in ledger["derivative_group_rule"]

    calibration = values["synthetic_calibration_examples.json"]
    assert calibration["synthetic_only"] is True
    assert len(calibration["examples"]) == 3
    assert all(
        example["fictional_source"].startswith("SYNTHETIC-")
        for example in calibration["examples"]
    )

    forms = [
        value
        for path, value in values.items()
        if path.startswith("lead_forms/")
    ]
    assert all(
        check["selection"] is None and check["notes"] == ""
        for form in forms
        for check in form["review_checks"].values()
    )


def test_no_prohibited_surfaces_private_ids_identities_or_decisions() -> None:
    tool = load_tool()
    inputs = tool.load_inputs(ROOT)
    rendered = read_committed()
    candidate_ids = [
        row["candidate_id"] for row in inputs["registry"]["candidates"]
    ]

    combined = "\n".join(
        content.decode("utf-8") for content in rendered.values()
    )
    tool._audit_text(
        combined,
        candidate_ids=candidate_ids,
        code_prefix="TEST",
    )
    lowered = combined.lower()
    for phrase in (
        "machine_provisional_status",
        "structural_scores",
        '"rank"',
        '"score"',
        "answer_template",
        "intervention_manifest",
        "private_label",
        "accepted_ses",
        "h_tier",
        "gate_a",
    ):
        assert phrase not in lowered

    values = json_values(rendered)
    keys = {
        key.lower()
        for value in values.values()
        for key in tool._walk_keys(value)
    }
    assert keys.isdisjoint(tool.IDENTITY_KEYS)
    assert tool.CONTACT_PATTERN.search(combined) is None

    forms = [
        value
        for path, value in values.items()
        if path.startswith("lead_forms/")
    ]
    assert all(
        form["prescreen_choice"]["selection"] is None
        and form["free_rationale"] == ""
        for form in forms
    )


def test_import_validator_accepts_complete_identity_free_import() -> None:
    tool = load_tool()
    inputs = tool.load_inputs(ROOT)
    rendered = read_committed()
    imported = completed_import(tool, rendered)

    tool.validate_import(imported, rendered=rendered, inputs=inputs)


def test_import_validator_rejects_missing_lead_identity_and_bad_group() -> None:
    tool = load_tool()
    inputs = tool.load_inputs(ROOT)
    rendered = read_committed()
    imported = completed_import(tool, rendered)

    missing = copy.deepcopy(imported)
    missing["responses"].pop()
    with pytest.raises(
        tool.PrescreenPacketError,
        match="IMPORT_RESPONSE_COUNT_INVALID",
    ):
        tool.validate_import(missing, rendered=rendered, inputs=inputs)

    identity = copy.deepcopy(imported)
    identity["reviewer_id"] = "person-1"
    with pytest.raises(
        tool.PrescreenPacketError,
        match="IMPORT_IDENTITY_FIELD",
    ):
        tool.validate_import(identity, rendered=rendered, inputs=inputs)

    wrong_group = copy.deepcopy(imported)
    wrong_group["source_exposure_ledger"]["events"][0][
        "source_group_id"
    ] = "P24"
    wrong_group["source_exposure_ledger"].pop("ledger_sha256")
    tool._seal(
        wrong_group["source_exposure_ledger"],
        "ledger_sha256",
    )
    with pytest.raises(
        tool.PrescreenPacketError,
        match="IMPORT_EVENT_GROUP_INVALID",
    ):
        tool.validate_import(wrong_group, rendered=rendered, inputs=inputs)


def test_cli_check_and_failure_token() -> None:
    completed = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--mode", "check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["completion_token"] == (
        "P23_102_HUMAN_PRESCREEN_PACKETS_READY"
    )

    failed = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--repo-root",
            str(ROOT / "does-not-exist"),
            "--mode",
            "check",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert failed.returncode == 1
    assert json.loads(failed.stdout)["completion_token"] == (
        "P23_102_HUMAN_PRESCREEN_PACKETS_REPAIR"
    )
