from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_machine_provisional_bundle.py"
OUTPUT_ROOT = (
    ROOT
    / "data/restricted/epic_p23_102_machine_provisional_families_v1"
)
OUTPUT_NAMES = (
    "family_registry.json",
    "evidence_registry.json",
    "intervention_manifest.json",
    "state_surface_manifest.json",
    "source_split_manifest.json",
    "leakage_gate.json",
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "p23_102_machine_provisional_bundle", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_committed() -> dict[str, dict]:
    return {
        name: json.loads((OUTPUT_ROOT / name).read_text(encoding="utf-8"))
        for name in OUTPUT_NAMES
    }


def reseal(tool, artifact: dict) -> None:
    artifact["payload_sha256"] = tool.object_hash(
        {
            key: value
            for key, value in artifact.items()
            if key != "payload_sha256"
        }
    )


def refresh_leakage_bundle_hash(tool, artifacts: dict[str, dict]) -> None:
    payload_hashes = {
        name: artifact["payload_sha256"]
        for name, artifact in sorted(artifacts.items())
        if name != "leakage_gate.json"
    }
    leakage = artifacts["leakage_gate.json"]
    leakage["artifact_payload_hashes"] = payload_hashes
    leakage["bundle_content_sha256"] = tool.object_hash(payload_hashes)
    reseal(tool, leakage)


def test_build_is_deterministic_and_matches_committed_bundle() -> None:
    tool = load_tool()
    inputs = tool.load_inputs(ROOT)
    first = tool.build_bundle(inputs)
    second = tool.build_bundle(inputs)
    committed = load_committed()

    assert tool.canonical_bytes(first) == tool.canonical_bytes(second)
    assert tool.canonical_bytes(first) == tool.canonical_bytes(committed)
    tool.validate_bundle(committed, inputs=inputs)
    assert committed["family_registry.json"]["status"] == (
        "MACHINE_PROVISIONAL_FROZEN"
    )
    assert committed["intervention_manifest.json"]["status"] == (
        "MECHANISM_SPECIFIC_FROZEN"
    )
    assert committed["state_surface_manifest.json"]["status"] == "FROZEN"
    assert committed["source_split_manifest.json"]["status"] == (
        "P23_DEVELOPMENT_ONLY_SOURCE_DISJOINT_FROM_EVALUATION"
    )
    assert committed["leakage_gate.json"]["status"] == "PASS"


def test_only_repair_va_leads_are_converted_with_templates_and_risks() -> None:
    artifacts = load_committed()
    source = json.loads(
        (
            ROOT
            / "data/restricted/epic_p23_102_family_mining_v1_dev/"
            "candidate_registry.json"
        ).read_text(encoding="utf-8")
    )
    families = artifacts["family_registry.json"]

    assert families["family_count"] == len(source["candidates"]) == 20
    assert [row["source_candidate_id"] for row in families["families"]] == [
        row["candidate_id"] for row in source["candidates"]
    ]
    assert all(
        row["machine_provisional_status"] == "REPAIR"
        and row["profile_hypothesis"] == "V+A"
        and row["profile_status"] == "HYPOTHESIS_NOT_MODALITY_NECESSITY"
        and row["human_prescreen"] == "NOT_PERFORMED"
        and row["source_uniform_human_prescreen_required"] is True
        and row["accepted_family"] is False
        and row["accepted_ses"] is False
        and row["h_tier"] is None
        and row["gate_a_credit"] is False
        and row["substitution_risks"]
        and row["recurrence_checks"][
            "human_full_source_recurrence_review_required"
        ]
        is True
        and row["question_template"]
        and row["answer_template"]
        and row["atomic_claim_templates"]
        for row in families["families"]
    )
    assert {
        row["temporal_structure"]["temporal_hypothesis"]
        for row in families["families"]
    } == {"near_local", "far_separated"}
    assert {
        row["temporal_structure"]["hop_hypothesis"]
        for row in families["families"]
    } == {"one_hop", "multi_hop"}


def test_exact_index_handles_and_temporal_ranges_are_preserved() -> None:
    artifacts = load_committed()
    evidence = artifacts["evidence_registry.json"]
    index = json.loads(
        (
            ROOT
            / "data/restricted/epic_p23_102_full_timeline_index_v1/"
            "full_timeline_index.json"
        ).read_text(encoding="utf-8")
    )
    segment_manifest = json.loads(
        (
            ROOT
            / "data/restricted/epic_p23_102_full_timeline_index_v1/"
            "segment_manifest.json"
        ).read_text(encoding="utf-8")
    )
    documents = {
        "vision": {
            row["segment_id"]: row
            for row in index["modalities"]["siglip2_visual"]["documents"]
        },
        "ambient_audio": {
            row["segment_id"]: row
            for row in index["modalities"]["clap_audio"]["documents"]
        },
    }

    assert evidence["evidence_count"] == 56
    for row in evidence["evidence"]:
        indexed = documents[row["modality"]][row["record_id"]]
        assert row["start_us"] == indexed["start_us"]
        assert row["end_us"] == indexed["end_us"]
        assert 0 <= row["start_us"] < row["end_us"]
        assert row["end_us"] <= segment_manifest["duration_us"]
        assert row["start_seconds"] == row["start_us"] / 1_000_000
        assert row["end_seconds"] == row["end_us"] / 1_000_000
        assert row["exact_index_binding_verified"] is True
        assert row["human_semantic_validation"] == "NOT_PERFORMED"
        assert row["semantic_content_asserted"] is False


def test_provisional_answer_support_and_necessity_semantics_are_explicit() -> None:
    artifacts = load_committed()
    families = artifacts["family_registry.json"]
    evidence = artifacts["evidence_registry.json"]
    interventions = artifacts["intervention_manifest.json"]

    for family in families["families"]:
        boundary = family["answer_support_and_necessity_boundary"]
        assert boundary == {
            "answer_is_provisional_template_only": True,
            "support_is_machine_route_hypothesis_only": True,
            "necessity_is_not_established": True,
            "human_validated": False,
            "accepted_ses": False,
        }
        for claim in family["atomic_claim_templates"]:
            assert claim["status"] == "MACHINE_TEMPLATE_UNFILLED"
            assert "NOT_HUMAN_VALIDATED" in claim["answer_semantics"]
            assert "NOT_ACCEPTED_SES" in claim["support_semantics"]
            assert "NOT_ESTABLISHED" in claim["necessity_semantics"]
    assert all(
        row["support_validated"] is False
        and row["necessity_validated"] is False
        and row["human_validated"] is False
        for row in evidence["route_groups"]
    )
    assert interventions["semantics_boundary"][
        "answer_semantics"
    ] == "PROVISIONAL_NOT_HUMAN_VALIDATED"
    assert interventions["semantics_boundary"][
        "support_semantics"
    ] == "PROVISIONAL_NOT_HUMAN_VALIDATED"
    assert interventions["semantics_boundary"][
        "necessity_semantics"
    ] == "PROVISIONAL_NOT_HUMAN_VALIDATED"


def test_interventions_and_cbrn_exposure_constraints_are_exact() -> None:
    artifacts = load_committed()
    interventions = artifacts["intervention_manifest.json"]
    surfaces = artifacts["state_surface_manifest.json"]

    assert interventions["intervention_count"] == 40
    assert surfaces["surface_count"] == 160
    by_intervention: dict[str, dict[str, dict]] = {}
    for row in surfaces["surfaces"]:
        by_intervention.setdefault(row["intervention_id"], {})[
            row["arm"]
        ] = row
    intervention_by_id = {
        row["intervention_id"]: row
        for row in interventions["interventions"]
    }
    for intervention_id, rows in by_intervention.items():
        assert set(rows) == {"C", "B", "R", "N"}
        handles = intervention_by_id[intervention_id][
            "suppressed_evidence_handle_ids"
        ]
        assert rows["C"]["available_evidence_handle_ids_initial"] == handles
        assert rows["C"]["available_evidence_handle_ids_after_checkpoint"] == (
            handles
        )
        assert rows["B"]["available_evidence_handle_ids_initial"] == []
        assert rows["B"]["available_evidence_handle_ids_after_checkpoint"] == []
        assert rows["R"]["available_evidence_handle_ids_initial"] == []
        assert rows["R"]["available_evidence_handle_ids_after_checkpoint"] == (
            handles
        )
        assert rows["N"]["available_evidence_handle_ids_initial"] == []
        assert rows["N"]["available_evidence_handle_ids_after_checkpoint"] == []
        assert rows["R"]["checkpoint"] == rows["N"]["checkpoint"]
        assert rows["R"]["checkpoint"]["action_index"] == 4
        assert rows["R"]["checkpoint"]["index_base"] == "zero"
        assert rows["R"]["checkpoint"]["public_bytes_identical_r_n"] is True
        assert rows["R"]["checkpoint"]["reveals_restoration"] is False
        assert rows["R"]["restoration_applied"] is True
        assert rows["N"]["restoration_applied"] is False
        assert rows["R"]["question_template"] == rows["N"][
            "question_template"
        ]
        assert rows["R"]["public_claim_handles"] == rows["N"][
            "public_claim_handles"
        ]


def test_source_split_leakage_gate_and_honest_zero_boundaries() -> None:
    artifacts = load_committed()
    families = artifacts["family_registry.json"]
    evidence = artifacts["evidence_registry.json"]
    split = artifacts["source_split_manifest.json"]
    leakage = artifacts["leakage_gate.json"]

    assert split["split_boundary"]["P23_102_development_only"] is True
    assert split["split_boundary"]["P23_102_future_test_ineligible"] is True
    assert split["source_assignments"][0]["future_test_eligible"] is False
    assert split["source_assignments"][0]["evaluation_eligible"] is False
    assert leakage["checks"]["semantic_annotations_entered"] is False
    assert leakage["checks"]["private_human_labels_entered"] is False
    assert leakage["checks"]["human_prescreen_entered"] is False
    assert leakage["checks"]["raw_media_opened"] is False
    assert leakage["checks"]["models_loaded"] is False
    assert leakage["checks"]["network_used"] is False
    assert all(value == 0 for value in leakage["claim_firewall"].values())
    assert families["acceptance_boundary"]["accepted_family_count"] == 0
    assert families["acceptance_boundary"]["accepted_ses_count"] == 0
    assert families["acceptance_boundary"]["h_tier_count"] == 0
    assert families["acceptance_boundary"]["gate_a_credit_count"] == 0
    assert evidence["honest_zero_profiles"]["V+S"]["honest_zero"] is True
    assert evidence["honest_zero_profiles"]["V+S"][
        "machine_lead_count"
    ] == 0
    assert evidence["honest_zero_profiles"]["V+S+A"]["honest_zero"] is True
    assert evidence["honest_zero_profiles"]["V+S+A"][
        "machine_lead_count"
    ] == 0


def test_validator_fails_closed_on_handle_exposure_and_claim_tampering() -> None:
    tool = load_tool()
    inputs = tool.load_inputs(ROOT)
    artifacts = tool.build_bundle(inputs)

    unknown = copy.deepcopy(artifacts)
    unknown["evidence_registry.json"]["evidence"][0][
        "record_id"
    ] = "P23_102.fine.unknown"
    reseal(tool, unknown["evidence_registry.json"])
    refresh_leakage_bundle_hash(tool, unknown)
    with pytest.raises(tool.BundleError, match="OUTPUT_INDEX_HANDLE_UNKNOWN"):
        tool.validate_bundle(unknown, inputs=inputs)

    exposure = copy.deepcopy(artifacts)
    surface = next(
        row
        for row in exposure["state_surface_manifest.json"]["surfaces"]
        if row["arm"] == "N"
    )
    surface["available_evidence_handle_ids_after_checkpoint"] = list(
        surface["suppressed_evidence_handle_ids_initial"]
    )
    reseal(tool, exposure["state_surface_manifest.json"])
    refresh_leakage_bundle_hash(tool, exposure)
    with pytest.raises(tool.BundleError, match="N_EXPOSURE_INVALID"):
        tool.validate_bundle(exposure, inputs=inputs)

    accepted = copy.deepcopy(artifacts)
    accepted["family_registry.json"]["acceptance_boundary"][
        "accepted_family_count"
    ] = 1
    reseal(tool, accepted["family_registry.json"])
    refresh_leakage_bundle_hash(tool, accepted)
    with pytest.raises(
        tool.BundleError, match="FAMILY_ACCEPTANCE_BOUNDARY_VIOLATION"
    ):
        tool.validate_bundle(accepted, inputs=inputs)


def test_cli_check_and_failure_token() -> None:
    completed = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--mode", "check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["decision"] == (
        "P23_102_MACHINE_PROVISIONAL_BUNDLE_READY"
    )

    failed = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--repo-root",
            str(ROOT / "does-not-exist"),
            "--mode",
            "build",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert failed.returncode == 2
    assert json.loads(failed.stdout)["decision"] == (
        "P23_102_MACHINE_PROVISIONAL_BUNDLE_REPAIR"
    )
