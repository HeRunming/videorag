#!/usr/bin/env python3
"""Fail-closed verifier for Task 167's development authoring registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "av-trace.epic-substantive-authoring-dev/1.0"
ARTIFACT_CLASS = "MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY"
DECISION = "EPIC_SUBSTANTIVE_DEV_READY"
EXPECTED_TASK166_IDS = {
    "epic.lead.4c60d048f41a9e26",
    "epic.lead.b8cb83fc059ba74e",
    "epic.lead.d8480ee4d0ed5d4d",
    "epic.lead.8f2a283d462000e4",
}
FORBIDDEN_TRUE = {
    "future_test_eligible",
    "gate_a_authority_conferred",
    "scientific_execution_authorized",
    "human_semantic_prescreen_complete",
    "human_review_performed",
    "human_reviewed",
    "human_gold",
    "human_minimality_asserted",
    "human_necessity_asserted",
    "h1_assigned",
    "h2_assigned",
    "final_accepted",
    "necessity_claimed",
    "minimality_claimed",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def json_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def walk(value: Any, location: str = "root"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            yield key, child, child_location
            yield from walk(child, child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{location}[{index}]")


def verify(root: Path, path: Path) -> list[str]:
    failures: list[str] = []

    def check(condition: bool, code: str) -> None:
        if not condition:
            failures.append(code)

    check(path.is_file() and not path.is_symlink(), "REGISTRY_FILE_INVALID")
    if failures:
        return failures
    check(stat.S_IMODE(path.stat().st_mode) == 0o600, "REGISTRY_MODE_NOT_0600")
    check(
        stat.S_IMODE(path.parent.stat().st_mode) == 0o700,
        "REGISTRY_PARENT_MODE_NOT_0700",
    )
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return failures + ["REGISTRY_JSON_INVALID"]
    check(isinstance(registry, dict), "REGISTRY_OBJECT_REQUIRED")
    if not isinstance(registry, dict):
        return failures
    check(registry.get("schema_version") == SCHEMA_VERSION, "SCHEMA_INVALID")
    check(registry.get("decision") == DECISION, "DECISION_INVALID")
    check(
        registry.get("artifact_classification") == ARTIFACT_CLASS,
        "ARTIFACT_CLASS_INVALID",
    )
    copied = dict(registry)
    stored_hash = copied.pop("registry_payload_sha256", None)
    check(stored_hash == json_hash(copied), "REGISTRY_PAYLOAD_HASH_INVALID")

    proposals = registry.get("proposals")
    check(isinstance(proposals, list), "PROPOSALS_LIST_REQUIRED")
    if not isinstance(proposals, list):
        return failures
    check(len(proposals) == 7, "PROPOSAL_COUNT_NOT_SEVEN")
    ids = [item.get("proposal_id") for item in proposals]
    check(len(ids) == len(set(ids)), "DUPLICATE_PROPOSAL_ID")
    task166_ids = {
        item.get("origin", {}).get("candidate_lead_id")
        for item in proposals
        if item.get("origin", {}).get("kind") == "TASK166_LEAD"
    }
    check(task166_ids == EXPECTED_TASK166_IDS, "TASK166_LEAD_SET_INVALID")
    additional = [
        item
        for item in proposals
        if item.get("origin", {}).get("kind")
        == "TASK167_FULL_TIMELINE_ADDITIONAL_LEAD"
    ]
    check(len(additional) >= 2, "FEWER_THAN_TWO_ADDITIONAL_LEADS")

    dispositions = {"KEEP": 0, "REPAIR": 0, "REJECT": 0}
    source_durations = {
        source_id: float(binding["duration_s"])
        for source_id, binding in registry.get("input_bindings", {})
        .get("raw_sources", {})
        .items()
    }
    for proposal in proposals:
        disposition = proposal.get("disposition")
        check(disposition in dispositions, f"DISPOSITION_INVALID:{ids}")
        if disposition in dispositions:
            dispositions[disposition] += 1
        check(
            proposal.get("artifact_classification") == ARTIFACT_CLASS,
            f"PROPOSAL_CLASS_INVALID:{proposal.get('proposal_id')}",
        )
        check(
            bool(str(proposal.get("question", "")).strip()),
            f"QUESTION_EMPTY:{proposal.get('proposal_id')}",
        )
        check(
            bool(str(proposal.get("answer", "")).strip()),
            f"ANSWER_EMPTY:{proposal.get('proposal_id')}",
        )
        check(
            proposal.get("required_human_actions"),
            f"HUMAN_ACTIONS_EMPTY:{proposal.get('proposal_id')}",
        )
        check(
            proposal.get("provisional_ses_ledger"),
            f"SES_LEDGER_EMPTY:{proposal.get('proposal_id')}",
        )
        check(
            proposal.get("alternative_route_ledger"),
            f"ALTERNATIVE_LEDGER_EMPTY:{proposal.get('proposal_id')}",
        )
        copied_proposal = dict(proposal)
        proposal_hash = copied_proposal.pop("proposal_payload_sha256", None)
        check(
            proposal_hash == json_hash(copied_proposal),
            f"PROPOSAL_HASH_INVALID:{proposal.get('proposal_id')}",
        )
        source_id = str(proposal.get("source_id"))
        check(source_id in source_durations, f"SOURCE_INVALID:{source_id}")
        duration = source_durations.get(source_id, 0.0)
        evidence_ids: set[str] = set()
        claim_ids = {
            str(item.get("claim_id"))
            for item in proposal.get("atomic_claims", [])
        }
        check(
            bool(claim_ids),
            f"ATOMIC_CLAIMS_EMPTY:{proposal.get('proposal_id')}",
        )
        for unit in proposal.get("evidence_graph", {}).get(
            "evidence_units", []
        ):
            evidence_id = str(unit.get("evidence_id"))
            check(
                evidence_id not in evidence_ids,
                f"DUPLICATE_EVIDENCE_ID:{proposal.get('proposal_id')}",
            )
            evidence_ids.add(evidence_id)
            evidence_interval = unit.get("interval", {})
            start = evidence_interval.get("start_s")
            end = evidence_interval.get("end_s")
            check(
                isinstance(start, (int, float))
                and isinstance(end, (int, float))
                and 0 <= start < end <= duration,
                f"EVIDENCE_INTERVAL_INVALID:{proposal.get('proposal_id')}:{evidence_id}",
            )
            check(
                bool(unit.get("record_references")),
                f"EVIDENCE_REFERENCES_EMPTY:{proposal.get('proposal_id')}:{evidence_id}",
            )
        for hypothesis in proposal.get("provisional_ses_ledger", []):
            check(
                hypothesis.get("accepted") is False,
                f"SES_ACCEPTED_FORBIDDEN:{proposal.get('proposal_id')}",
            )
            check(
                hypothesis.get("human_validator_count") == 0,
                f"SES_HUMAN_VALIDATOR_FORBIDDEN:{proposal.get('proposal_id')}",
            )
            check(
                set(hypothesis.get("evidence_ids", ())) <= evidence_ids,
                f"SES_EVIDENCE_UNRESOLVED:{proposal.get('proposal_id')}",
            )
            check(
                set(hypothesis.get("claim_ids", ())) <= claim_ids,
                f"SES_CLAIMS_UNRESOLVED:{proposal.get('proposal_id')}",
            )

    accounting = registry.get("candidate_accounting", {})
    check(accounting.get("proposal_count") == len(proposals), "COUNT_PROPOSALS")
    check(accounting.get("keep_count") == dispositions["KEEP"], "COUNT_KEEP")
    check(accounting.get("repair_count") == dispositions["REPAIR"], "COUNT_REPAIR")
    check(accounting.get("reject_count") == dispositions["REJECT"], "COUNT_REJECT")
    check(dispositions == {"KEEP": 5, "REPAIR": 0, "REJECT": 2}, "EXACT_COUNTS")
    check(
        accounting.get("nonempty_question_count") == len(proposals),
        "COUNT_QUESTIONS",
    )
    check(
        accounting.get("nonempty_answer_count") == len(proposals),
        "COUNT_ANSWERS",
    )
    check(
        accounting.get("atomic_claim_count")
        == sum(len(item.get("atomic_claims", ())) for item in proposals),
        "COUNT_ATOMIC_CLAIMS",
    )
    check(
        accounting.get("evidence_unit_count")
        == sum(
            len(item.get("evidence_graph", {}).get("evidence_units", ()))
            for item in proposals
        ),
        "COUNT_EVIDENCE_UNITS",
    )
    check(
        accounting.get("substantive_speech_lead_count") == 0,
        "SPEECH_COUNT_INVALID",
    )

    firewall = registry.get("annotation_firewall", {})
    for key in (
        "epic_action_annotations_opened",
        "epic_narration_annotations_opened",
        "epic_sounds_annotations_opened",
        "existing_annotation_vault_opened",
        "official_semantic_labels_used",
    ):
        check(firewall.get(key) is False, f"ANNOTATION_FIREWALL_INVALID:{key}")
    for key, child, location in walk(registry):
        if key in FORBIDDEN_TRUE:
            check(child is False, f"FORBIDDEN_TRUE:{location}")
        if isinstance(child, str):
            check(
                "H1_HUMAN" not in child and "H2_HUMAN" not in child,
                f"H_TIER_STRING_FORBIDDEN:{location}",
            )

    for binding_name in (
        "task166_registry",
        "canonical_index",
        "raw_sources",
    ):
        check(
            binding_name in registry.get("input_bindings", {}),
            f"INPUT_BINDING_MISSING:{binding_name}",
        )
    task166 = registry["input_bindings"]["task166_registry"]
    task166_path = root / task166["path"]
    check(task166_path.is_file(), "TASK166_PATH_MISSING")
    if task166_path.is_file():
        check(
            file_hash(task166_path) == task166["sha256"],
            "TASK166_FILE_HASH_MISMATCH",
        )
    for source_id, binding in registry["input_bindings"]["raw_sources"].items():
        source_path = root / binding["path"]
        check(source_path.is_file(), f"RAW_SOURCE_MISSING:{source_id}")
        check(not source_path.is_symlink(), f"RAW_SOURCE_SYMLINK:{source_id}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--registry",
        default=(
            "data/restricted/epic_family_candidates_v2_dev/"
            "candidate_registry.json"
        ),
    )
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    path = Path(args.registry)
    if not path.is_absolute():
        path = root / path
    path.resolve(strict=False).relative_to(root)
    failures = verify(root, path)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"{len(failures)} failures")
        return 1
    print("EPIC_SUBSTANTIVE_AUTHORING_DEV_VERIFIED")
    print("checks: registry/hash/boundary/counts/evidence/SES/routes/firewall")
    print("exact dispositions: KEEP=5 REPAIR=0 REJECT=2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
