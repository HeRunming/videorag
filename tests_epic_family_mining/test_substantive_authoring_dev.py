from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = ROOT / "scripts/build_epic_substantive_authoring_dev.py"
VERIFY_PATH = ROOT / "scripts/verify_epic_substantive_authoring_dev.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_module(BUILD_PATH, "epic_substantive_builder")
verifier = load_module(VERIFY_PATH, "epic_substantive_verifier")


@pytest.fixture(scope="module")
def registry():
    return builder.build_registry(ROOT)


def test_build_registry_exact_development_accounting(registry):
    assert registry["decision"] == "EPIC_SUBSTANTIVE_DEV_READY"
    assert registry["artifact_classification"] == (
        "MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY"
    )
    assert registry["candidate_accounting"] == {
        "proposal_count": 7,
        "task166_lead_count": 4,
        "additional_lead_count": 3,
        "keep_count": 5,
        "repair_count": 0,
        "reject_count": 2,
        "nonempty_question_count": 7,
        "nonempty_answer_count": 7,
        "atomic_claim_count": 11,
        "evidence_unit_count": 13,
        "provisional_ses_count": 8,
        "alternative_route_count": 18,
        "multi_hop_count": 2,
        "substantive_speech_lead_count": 0,
        "counts_are_development_dispositions_not_human_acceptance": True,
    }


def test_build_registry_replaces_all_task166_placeholders(registry):
    prior_ids = {
        "epic.lead.4c60d048f41a9e26",
        "epic.lead.b8cb83fc059ba74e",
        "epic.lead.d8480ee4d0ed5d4d",
        "epic.lead.8f2a283d462000e4",
    }
    proposals = [
        item
        for item in registry["proposals"]
        if item["origin"]["kind"] == "TASK166_LEAD"
    ]
    assert {item["origin"]["candidate_lead_id"] for item in proposals} == prior_ids
    assert all(item["question"].strip() for item in proposals)
    assert all(item["answer"].strip() for item in proposals)
    assert all(item["atomic_claims"] for item in proposals)
    assert all(item["provisional_ses_ledger"] for item in proposals)
    assert all(item["alternative_route_ledger"] for item in proposals)


def test_build_registry_preserves_annotation_firewall_and_human_boundary(registry):
    firewall = registry["annotation_firewall"]
    assert firewall["epic_action_annotations_opened"] is False
    assert firewall["epic_narration_annotations_opened"] is False
    assert firewall["epic_sounds_annotations_opened"] is False
    assert firewall["existing_annotation_vault_opened"] is False
    assert registry["scope"]["human_semantic_prescreen_complete"] is False
    assert registry["scope"]["h1_assigned"] is False
    assert registry["scope"]["h2_assigned"] is False
    assert registry["scope"]["necessity_claimed"] is False
    assert registry["scope"]["minimality_claimed"] is False


def test_verifier_accepts_emitted_registry():
    path = (
        ROOT
        / "data/restricted/epic_family_candidates_v2_dev/candidate_registry.json"
    )
    assert verifier.verify(ROOT, path) == []


def test_verifier_rejects_affirmative_human_status(tmp_path, registry):
    broken = json.loads(json.dumps(registry))
    broken["proposals"][0]["h1_assigned"] = True
    proposal = dict(broken["proposals"][0])
    proposal.pop("proposal_payload_sha256")
    broken["proposals"][0]["proposal_payload_sha256"] = builder.json_hash(proposal)
    copied = dict(broken)
    copied.pop("registry_payload_sha256")
    broken["registry_payload_sha256"] = builder.json_hash(copied)
    path = tmp_path / "candidate_registry.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    path.chmod(0o600)
    tmp_path.chmod(0o700)
    failures = verifier.verify(ROOT, path)
    assert any(item.startswith("FORBIDDEN_TRUE:") for item in failures)
