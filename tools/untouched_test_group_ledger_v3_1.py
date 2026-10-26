#!/usr/bin/env python3
"""Build the sealed untouched-test group ledger v3.1.

This repair is intentionally narrow.  It retains nine commitment-selected
groups from the frozen v3 private ledger and adds three commitment-selected
HoloAssist groups.  Selection and replacement decisions use commitment hashes
only.  Identity-bearing records and exact technical timing evidence are copied
only into the mode-0600 private ledger.

The builder performs no network access, media access, semantic annotation
access, or learned ranking.  The public commitment and review document expose
only commitments, counts, dataset-lineage names, lock state, and governance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_PRIVATE = "av-trace.untouched-test-group-ledger-private/3.1"
SCHEMA_PUBLIC = "av-trace.untouched-test-group-commitment/3.1"
LEDGER_ID = "UNTOUCHED_TEST_GROUP_LEDGER_V3_1"
COMMITMENT_ID = "UNTOUCHED_TEST_GROUP_LEDGER_V3_1_PUBLIC_COMMITMENT"
CREATED_DATE = "2026-10-15"

FINAL_READY = "UNTOUCHED_TEST_GROUP_LEDGER_V3_1_FROZEN_PRIVATE_READY"
FINAL_REPAIR = "UNTOUCHED_TEST_GROUP_LEDGER_V3_1_REPAIR"
V3_REPAIR = "UNTOUCHED_TEST_GROUP_LEDGER_V3_REPAIR"
MANIFEST_READY = "SOURCE_EXPOSURE_ALIAS_MANIFEST_V2_READY"
HOLO_UNIVERSE_READY = "HOLOASSIST_OPAQUE_GROUP_UNIVERSE_READY"
HOLO_SUPPLEMENT_READY = "HOLOASSIST_EXPOSURE_SUPPLEMENT_V1_READY"

V3_PRIVATE_REL = Path(
    "data/restricted/untouched_test_group_ledger_v3_private.json"
)
MANIFEST_REL = Path(
    "data/rehearsal_plan/source_exposure_alias_manifest_v2.json"
)
HOLO_PRIVATE_REL = Path(
    "data/restricted/holoassist_opaque_group_universe_v1.json"
)
HOLO_PUBLIC_REL = Path(
    "data/rehearsal_plan/holoassist_opaque_group_commitment_v1.json"
)
HOLO_SUPPLEMENT_REL = Path(
    "data/rehearsal_plan/holoassist_exposure_supplement_v1.json"
)
PRIVATE_REL = Path(
    "data/restricted/untouched_test_group_ledger_v3_1_private.json"
)
PUBLIC_REL = Path(
    "data/rehearsal_plan/"
    "untouched_test_group_ledger_v3_1_public_commitment.json"
)
REVIEW_REL = Path("docs/review/untouched_test_group_ledger_v3_1.md")

EXPECTED_INPUT_HASHES = {
    V3_PRIVATE_REL.as_posix(): (
        "d0295fd3081b45054941144f3f15f2499efad3c7e081cad6724e25f2b11b1f68"
    ),
    MANIFEST_REL.as_posix(): (
        "2c631f070505f60a49862a05d879c83e856d7dd60bca99fb34bfa16e8c064618"
    ),
    HOLO_PRIVATE_REL.as_posix(): (
        "bfed01c6cf5d1fb6ac5befb2959dacedeba649aa0d33112338e7eb49ae4bf529"
    ),
    HOLO_PUBLIC_REL.as_posix(): (
        "2b2b39da033e1b9be27901bea2a52bae5163f897844236113baed5bb4871d7ac"
    ),
    HOLO_SUPPLEMENT_REL.as_posix(): (
        "47060b97dbf80e84c9ec4c5f7db07e2e2f841269293e402954321e825c85e890"
    ),
}

TARGET_GROUP_COUNT = 12
HOLOASSIST_SELECTION_COUNT = 3
MINIMUM_DATASET_LINEAGES = 3
MINIMUM_PRODUCTION_CLOSURES = 12
PRIVATE_FILE_MODE = 0o600
PUBLIC_FILE_MODE = 0o644
RESTRICTED_DIRECTORY_MODE = 0o700

DATASET_LINEAGES = ("ASSEMBLY101", "EPIC", "HOLOASSIST")
SELECTION_FIELDS = (
    "source_commitment_sha256",
    "source_pool",
)
FORBIDDEN_SELECTION_FIELDS = (
    "identity",
    "closure_root",
    "recording_root",
    "exact_object",
    "aliases",
    "title",
    "description",
    "prompt",
    "target",
    "task",
    "label",
    "transcript",
    "timing_path",
    "pose_path",
)
GOVERNANCE_FIELDS = (
    "universe_definition",
    "prior_exclusions",
    "alias_and_exposure_policy",
    "role_separation",
    "selection_commitment_rule",
    "count_and_lineage_constraints",
    "rights_and_custody_gates",
    "reveal_protocol",
    "replacement_protocol",
    "automatic_fail_closed_rules",
    "independent_audit",
)
SPLIT_LOCK_COVERED_FIELDS = (
    "schema_version",
    "commitment_id",
    "created_date",
    "artifact_classification",
    "authoritative_inputs",
    "historical_v3",
    "source_boundaries",
    "contamination_policy",
    "eligibility_policy",
    "selection",
    "roster_construction",
    "lineage_composition",
    "locks",
    "claims",
    "custodian_reveal_rules",
    "replacement_policy",
    "group_commitments",
    "sealed_private_roster_commitment_sha256",
    "governance",
    "decision",
    "final_marker",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LedgerError(ValueError):
    """Raised whenever the v3.1 repair must fail closed."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LedgerError(f"JSON_OBJECT_REQUIRED:{path.as_posix()}")
    return value


def _load_bound_inputs(root: Path) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for relative, expected_hash in EXPECTED_INPUT_HASHES.items():
        path = root / relative
        if not path.is_file():
            raise LedgerError(f"BOUND_INPUT_MISSING:{relative}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise LedgerError(f"BOUND_INPUT_HASH_MISMATCH:{relative}")
        values[relative] = load_json(path)
    return values


def _token_present(data: bytes, identity: str) -> bool:
    pattern = re.compile(
        rb"(?<![A-Za-z0-9])"
        + re.escape(identity.encode("ascii"))
        + rb"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    return pattern.search(data) is not None


def _validate_source_markers(inputs: dict[str, dict[str, Any]]) -> None:
    v3 = inputs[V3_PRIVATE_REL.as_posix()]
    manifest = inputs[MANIFEST_REL.as_posix()]
    holo_private = inputs[HOLO_PRIVATE_REL.as_posix()]
    holo_public = inputs[HOLO_PUBLIC_REL.as_posix()]
    supplement = inputs[HOLO_SUPPLEMENT_REL.as_posix()]
    if v3.get("final_marker") != V3_REPAIR:
        raise LedgerError("HISTORICAL_V3_MUST_REMAIN_REPAIR")
    if manifest.get("final_marker") != MANIFEST_READY:
        raise LedgerError("FROZEN_MANIFEST_V2_NOT_READY")
    if holo_private.get("final_marker") != HOLO_UNIVERSE_READY:
        raise LedgerError("HOLOASSIST_PRIVATE_UNIVERSE_NOT_READY")
    if holo_public.get("final_marker") != HOLO_UNIVERSE_READY:
        raise LedgerError("HOLOASSIST_PUBLIC_COMMITMENT_NOT_READY")
    if supplement.get("final_marker") != HOLO_SUPPLEMENT_READY:
        raise LedgerError("HOLOASSIST_EXPOSURE_SUPPLEMENT_NOT_READY")


def select_commitment_roster(
    source_commitments: list[str],
    holoassist_commitments: list[str],
) -> dict[str, list[str]]:
    """Select replacements using commitment hashes and pool tags only."""
    if len(source_commitments) < TARGET_GROUP_COUNT:
        raise LedgerError("V3_SELECTED_COMMITMENT_COUNT_TOO_SMALL")
    if len(holoassist_commitments) < HOLOASSIST_SELECTION_COUNT:
        raise LedgerError("HOLOASSIST_COMMITMENT_COUNT_TOO_SMALL")
    for value in source_commitments + holoassist_commitments:
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise LedgerError("INVALID_SELECTION_COMMITMENT")
    if len(set(source_commitments)) != len(source_commitments):
        raise LedgerError("DUPLICATE_V3_SELECTION_COMMITMENT")
    if len(set(holoassist_commitments)) != len(holoassist_commitments):
        raise LedgerError("DUPLICATE_HOLOASSIST_SELECTION_COMMITMENT")

    # Frozen rule: add the lowest HoloAssist commitments and remove the
    # highest v3 commitments.  No identity, metadata, timing, or semantics
    # participate in this choice.
    selected_holo = sorted(holoassist_commitments)[
        :HOLOASSIST_SELECTION_COUNT
    ]
    removed_source = sorted(
        source_commitments, reverse=True
    )[:HOLOASSIST_SELECTION_COUNT]
    removed = set(removed_source)
    retained_source = sorted(
        value for value in source_commitments if value not in removed
    )
    if len(retained_source) + len(selected_holo) != TARGET_GROUP_COUNT:
        raise LedgerError("FINAL_COMMITMENT_ROSTER_COUNT_MISMATCH")
    return {
        "retained_v3_commitments": retained_source,
        "removed_v3_commitments": removed_source,
        "selected_holoassist_commitments": selected_holo,
        "unselected_holoassist_commitments": sorted(
            set(holoassist_commitments) - set(selected_holo)
        ),
    }


def _supplement_groups(
    supplement: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    groups = supplement["exposure_classes"]["sealed_selected_groups"][
        "groups"
    ]
    result = {row["commitment"]: row for row in groups}
    if len(result) != len(groups):
        raise LedgerError("DUPLICATE_SUPPLEMENT_COMMITMENT")
    return result


def _validate_holoassist_sources(
    root: Path,
    *,
    manifest: dict[str, Any],
    holo_private: dict[str, Any],
    holo_public: dict[str, Any],
    supplement: dict[str, Any],
) -> None:
    private_groups = holo_private.get("selected_groups", [])
    private_by_commitment = {
        row["private_commitment"]: row for row in private_groups
    }
    public_commitments = set(holo_public.get("commitments", []))
    supplement_by_commitment = _supplement_groups(supplement)
    if len(private_by_commitment) != len(private_groups):
        raise LedgerError("DUPLICATE_HOLOASSIST_PRIVATE_COMMITMENT")
    if set(private_by_commitment) != public_commitments:
        raise LedgerError("HOLOASSIST_PUBLIC_PRIVATE_COMMITMENT_MISMATCH")
    if set(private_by_commitment) != set(supplement_by_commitment):
        raise LedgerError("HOLOASSIST_SUPPLEMENT_COMMITMENT_MISMATCH")

    readme_exposed = set(holo_private["policy"]["explicit_exclusions"])
    readme_exposed.update(
        holo_private["policy"]["semantic_text_exclusions"]
    )
    manifest_bytes = (root / MANIFEST_REL).read_bytes()
    for commitment, group in private_by_commitment.items():
        identity = group["recording_root"]
        if identity in readme_exposed:
            raise LedgerError("HOLOASSIST_SELECTED_README_EXPOSED")
        if _token_present(manifest_bytes, identity):
            raise LedgerError("HOLOASSIST_SELECTED_IN_FROZEN_MANIFEST_V2")
        if not group.get("timing_closed"):
            raise LedgerError("HOLOASSIST_GROUP_TIMING_NOT_CLOSED")
        for variant in group.get("variants", []):
            evidence = variant.get("timing_evidence", {})
            if (
                not variant.get("timing_present")
                or not evidence.get("fetched")
                or not evidence.get("format_recognized")
                or not evidence.get("sha256")
            ):
                raise LedgerError(
                    "HOLOASSIST_EXACT_TIMING_EVIDENCE_INCOMPLETE"
                )
        summary = supplement_by_commitment[commitment]
        conditions = summary["conditions"]
        if (
            summary["classification"] != "CONDITIONAL_METADATA_ONLY"
            or not conditions["timing_closed"]
            or not conditions["absent_from_official_readme_example_set"]
            or not conditions[
                "absent_from_frozen_repository_history_v2"
            ]
        ):
            raise LedgerError("HOLOASSIST_SUPPLEMENT_CONDITION_FAILED")
    boundary = supplement["claim_boundary"]
    if (
        boundary["video_content_access_claim"]
        or boundary["audio_content_access_claim"]
        or boundary["native_audio_presence_claim"]
        or boundary["playable_media_validation_claim"]
    ):
        raise LedgerError("HOLOASSIST_EXACT_AV_ACCESS_NOT_UNRESOLVED")
    if manifest["scan_freeze"]["supplemental_post_freeze_file_count"] != 0:
        raise LedgerError("FROZEN_MANIFEST_V2_NOT_EXACTLY_FROZEN")


def _group_commitment_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in row.items()
        if key not in {
            "v3_1_commitment_salt_hex",
            "v3_1_group_commitment_sha256",
        }
    }


def compute_group_commitment(row: dict[str, Any]) -> str:
    salt = row["v3_1_commitment_salt_hex"]
    if not _SHA256_RE.fullmatch(salt):
        raise LedgerError("INVALID_V3_1_GROUP_COMMITMENT_SALT")
    return hashlib.sha256(
        bytes.fromhex(salt)
        + b"\0"
        + canonical_bytes(_group_commitment_payload(row))
    ).hexdigest()


def _derived_salt(master_salt_hex: str, source_commitment: str) -> str:
    try:
        key = bytes.fromhex(master_salt_hex)
    except ValueError as exc:
        raise LedgerError("V3_COMMITMENT_MASTER_SALT_INVALID") from exc
    return hmac.new(
        key,
        b"untouched-test-group-ledger-v3.1\0"
        + source_commitment.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _source_group(
    *,
    slot: str,
    source: dict[str, Any],
    master_salt_hex: str,
) -> dict[str, Any]:
    source_commitment = source["group_commitment_sha256"]
    row = {
        "slot": slot,
        "dataset_lineage": source["dataset_lineage_id"],
        "source_pool": "FROZEN_V3_SELECTED_GROUP",
        "source_commitment_sha256": source_commitment,
        "conditional_status": "CONDITIONAL",
        "closure_kind": source["closure_kind"],
        "production_closure_complete": True,
        "timing_closed": None,
        "video_exact_access_resolved": False,
        "audio_exact_access_resolved": False,
        "semantic_routing_event_count": 0,
        "test_construction_locked": True,
        "distribution_locked": True,
        "identity_and_evidence": copy.deepcopy(source),
        "v3_1_commitment_salt_hex": _derived_salt(
            master_salt_hex, source_commitment
        ),
        "v3_1_group_commitment_sha256": "",
    }
    row["v3_1_group_commitment_sha256"] = compute_group_commitment(row)
    return row


def _holoassist_group(
    *,
    slot: str,
    source: dict[str, Any],
    summary: dict[str, Any],
    master_salt_hex: str,
) -> dict[str, Any]:
    source_commitment = source["private_commitment"]
    row = {
        "slot": slot,
        "dataset_lineage": "HOLOASSIST",
        "source_pool": "HOLOASSIST_SEALED_COMMITMENT",
        "source_commitment_sha256": source_commitment,
        "conditional_status": "CONDITIONAL",
        "closure_kind": "COMPLETE_RECORDING_PRODUCTION_CLOSURE",
        "production_closure_complete": True,
        "timing_closed": True,
        "video_exact_access_resolved": False,
        "audio_exact_access_resolved": False,
        "semantic_routing_event_count": 0,
        "test_construction_locked": True,
        "distribution_locked": True,
        "identity_and_evidence": {
            "opaque_universe_group": copy.deepcopy(source),
            "exposure_and_timing_summary": copy.deepcopy(summary),
        },
        "v3_1_commitment_salt_hex": _derived_salt(
            master_salt_hex, source_commitment
        ),
        "v3_1_group_commitment_sha256": "",
    }
    row["v3_1_group_commitment_sha256"] = compute_group_commitment(row)
    return row


def _authoritative_inputs(root: Path) -> list[dict[str, str]]:
    roles = {
        V3_PRIVATE_REL.as_posix(): (
            "Frozen v3 identity-bearing selected roster, locks, claims, "
            "custodian rules, and replacement policy"
        ),
        MANIFEST_REL.as_posix(): (
            "Frozen v2 exposure identities and Assembly101/EPIC closure "
            "authority"
        ),
        HOLO_PRIVATE_REL.as_posix(): (
            "Private HoloAssist closure identities and exact technical "
            "timing evidence"
        ),
        HOLO_PUBLIC_REL.as_posix(): (
            "Public HoloAssist sealed commitment universe"
        ),
        HOLO_SUPPLEMENT_REL.as_posix(): (
            "HoloAssist exposure exclusions, timing closure, and unresolved "
            "video/audio access boundary"
        ),
    }
    return [
        {
            "path": relative,
            "role": roles[relative],
            "sha256": sha256_file(root / relative),
        }
        for relative in EXPECTED_INPUT_HASHES
    ]


def _source_boundaries() -> dict[str, Any]:
    return {
        "network_used": False,
        "media_opened_or_inspected": False,
        "semantic_annotation_bodies_opened": False,
        "transcript_or_caption_bodies_opened": False,
        "model_or_learned_ranking_used": False,
        "candidate_mining_performed": False,
        "selection_input_boundary": (
            "Existing SHA-256 commitment hashes and source-pool tags only."
        ),
        "private_identity_use": (
            "Post-selection validation, private evidence binding, exact-token "
            "exposure exclusion, and commitment construction only."
        ),
    }


def _contamination_policy(
    v3: dict[str, Any], supplement: dict[str, Any]
) -> dict[str, Any]:
    return {
        "inherited_v3_policy": copy.deepcopy(v3["contamination_policy"]),
        "holoassist_policy": {
            "official_readme_examples_permanently_excluded": True,
            "frozen_manifest_v2_identity_absence_required": True,
            "timing_metadata_is_nonsemantic": True,
            "selected_commitment_conditions_sha256": sha256_value(
                supplement["exposure_classes"]["sealed_selected_groups"]
            ),
            "unknown_or_conflicting_identity_effect": "FAIL_CLOSED",
        },
    }


def _eligibility_policy() -> dict[str, Any]:
    return {
        "v3_group_must_be_frozen_selected_group": True,
        "holoassist_group_must_be_public_private_commitment_matched": True,
        "holoassist_group_must_be_timing_closed": True,
        "holoassist_group_must_be_absent_from_manifest_v2_identities": True,
        "holoassist_group_must_be_absent_from_readme_exposed_ids": True,
        "complete_production_closure_required": True,
        "semantic_selection_forbidden": True,
        "status_if_eligible": "CONDITIONAL",
        "video_exact_access_may_remain_unresolved": True,
        "audio_exact_access_may_remain_unresolved": True,
    }


def _governance(
    *,
    v3: dict[str, Any],
    selection_rule_commitment: str,
) -> dict[str, Any]:
    return {
        "universe_definition": (
            "The twelve frozen v3 selected commitments plus the six sealed "
            "HoloAssist commitments bound by the private universe, public "
            "commitment, and exposure supplement."
        ),
        "prior_exclusions": (
            "All v2 contaminated closures, all official README example "
            "identities, every HoloAssist identity present in frozen v2 "
            "history, and every unknown or conflicting closure."
        ),
        "alias_and_exposure_policy": (
            "Inherit v3 complete Assembly101/EPIC closures; for HoloAssist, "
            "merge every variant under its recording root and require the "
            "supplement's exact exposure exclusions."
        ),
        "role_separation": copy.deepcopy(
            v3["governance"]["role_separation"]
        ),
        "selection_commitment_rule": {
            "algorithm": (
                "Select the three lexicographically lowest HoloAssist "
                "commitments; remove the three lexicographically highest v3 "
                "selected commitments; assign final slots by ascending "
                "source commitment."
            ),
            "allowed_fields": list(SELECTION_FIELDS),
            "forbidden_fields": list(FORBIDDEN_SELECTION_FIELDS),
            "rule_sha256": selection_rule_commitment,
        },
        "count_and_lineage_constraints": {
            "minimum_exact_closure_count": TARGET_GROUP_COUNT,
            "minimum_independent_dataset_lineages": (
                MINIMUM_DATASET_LINEAGES
            ),
            "minimum_holoassist_commitments": (
                HOLOASSIST_SELECTION_COUNT
            ),
            "minimum_complete_production_closures": (
                MINIMUM_PRODUCTION_CLOSURES
            ),
            "distinct_complete_production_closure_per_group": True,
        },
        "rights_and_custody_gates": copy.deepcopy(
            v3["governance"]["rights_and_custody_gates"]
        ),
        "reveal_protocol": copy.deepcopy(v3["custodian_reveal_rules"]),
        "replacement_protocol": copy.deepcopy(v3["replacement_policy"]),
        "automatic_fail_closed_rules": [
            "fewer than twelve selected commitments",
            "fewer than three independent dataset lineages",
            "fewer than three selected HoloAssist commitments",
            "fewer than twelve complete production closures",
            "historical v3 no longer marked REPAIR",
            "bound input hash or marker mismatch",
            "selection input contains identity, timing, or semantic fields",
            "HoloAssist identity appears in frozen manifest v2 or README IDs",
            "HoloAssist technical timing closure is incomplete",
            "HoloAssist exact video or audio access is falsely claimed",
            "public identity disclosure",
            "commitment, roster, or split-lock mismatch",
            "permissions differ from private 0600 and public 0644",
        ],
        "independent_audit": {
            "required_before_non_custodian_reveal": True,
            "required_checks": [
                "bound input hashes and historical v3 REPAIR state",
                "commitment-only deterministic replacement transcript",
                "identity exclusion from manifest v2 and README examples",
                "HoloAssist exact technical timing closure",
                "count, lineage, and production-closure thresholds",
                "private/public commitment verification",
                "full-field governance split-lock",
                "permissions and public non-disclosure",
            ],
            "current_signed_go": False,
        },
    }


def compute_private_roster_commitment(private: dict[str, Any]) -> str:
    payload = {
        key: copy.deepcopy(value)
        for key, value in private.items()
        if key != "sealed_private_roster_commitment_sha256"
    }
    return sha256_value(payload)


def compute_split_lock_payload(public: dict[str, Any]) -> dict[str, Any]:
    return {
        field: copy.deepcopy(public[field])
        for field in SPLIT_LOCK_COVERED_FIELDS
    }


def compute_split_lock_hash(public: dict[str, Any]) -> str:
    return sha256_value(compute_split_lock_payload(public))


def _selection_rule_commitment() -> str:
    return sha256_value(
        {
            "source_selection": "highest_commitment_hashes_removed",
            "source_remove_count": HOLOASSIST_SELECTION_COUNT,
            "holoassist_selection": "lowest_commitment_hashes_added",
            "holoassist_add_count": HOLOASSIST_SELECTION_COUNT,
            "final_slot_order": "ascending_source_commitment_sha256",
            "allowed_fields": list(SELECTION_FIELDS),
        }
    )


def build_artifacts(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    inputs = _load_bound_inputs(root)
    _validate_source_markers(inputs)
    v3 = inputs[V3_PRIVATE_REL.as_posix()]
    manifest = inputs[MANIFEST_REL.as_posix()]
    holo_private = inputs[HOLO_PRIVATE_REL.as_posix()]
    holo_public = inputs[HOLO_PUBLIC_REL.as_posix()]
    supplement = inputs[HOLO_SUPPLEMENT_REL.as_posix()]
    _validate_holoassist_sources(
        root,
        manifest=manifest,
        holo_private=holo_private,
        holo_public=holo_public,
        supplement=supplement,
    )

    source_by_commitment = {
        row["group_commitment_sha256"]: row
        for row in v3["selected_groups"]
    }
    holo_by_commitment = {
        row["private_commitment"]: row
        for row in holo_private["selected_groups"]
    }
    summaries = _supplement_groups(supplement)
    selection = select_commitment_roster(
        list(source_by_commitment), list(holo_by_commitment)
    )

    final_descriptors = [
        {
            "source_commitment_sha256": value,
            "source_pool": "FROZEN_V3_SELECTED_GROUP",
        }
        for value in selection["retained_v3_commitments"]
    ] + [
        {
            "source_commitment_sha256": value,
            "source_pool": "HOLOASSIST_SEALED_COMMITMENT",
        }
        for value in selection["selected_holoassist_commitments"]
    ]
    final_descriptors.sort(
        key=lambda row: row["source_commitment_sha256"]
    )
    if any(set(row) != set(SELECTION_FIELDS) for row in final_descriptors):
        raise LedgerError("SELECTION_DESCRIPTOR_FIELD_MISMATCH")

    master_salt = v3["private_material"]["commitment_master_salt_hex"]
    groups: list[dict[str, Any]] = []
    for index, descriptor in enumerate(final_descriptors, 1):
        commitment = descriptor["source_commitment_sha256"]
        slot = f"V3.1-TS-{index:02d}"
        if descriptor["source_pool"] == "FROZEN_V3_SELECTED_GROUP":
            group = _source_group(
                slot=slot,
                source=source_by_commitment[commitment],
                master_salt_hex=master_salt,
            )
        else:
            group = _holoassist_group(
                slot=slot,
                source=holo_by_commitment[commitment],
                summary=summaries[commitment],
                master_salt_hex=master_salt,
            )
        groups.append(group)

    lineage_counts = Counter(row["dataset_lineage"] for row in groups)
    production_closure_count = sum(
        bool(row["production_closure_complete"]) for row in groups
    )
    holo_count = lineage_counts["HOLOASSIST"]
    count_ready = len(groups) >= TARGET_GROUP_COUNT
    lineage_ready = len(lineage_counts) >= MINIMUM_DATASET_LINEAGES
    production_ready = (
        production_closure_count >= MINIMUM_PRODUCTION_CLOSURES
    )
    holo_ready = holo_count >= HOLOASSIST_SELECTION_COUNT
    ready = count_ready and lineage_ready and production_ready and holo_ready
    marker = FINAL_READY if ready else FINAL_REPAIR
    decision_value = "FROZEN_PRIVATE_READY" if ready else "REPAIR"
    rule_commitment = _selection_rule_commitment()
    authoritative_inputs = _authoritative_inputs(root)

    selection_record = {
        "allowed_fields": list(SELECTION_FIELDS),
        "forbidden_fields": list(FORBIDDEN_SELECTION_FIELDS),
        "algorithm": (
            "Lowest HoloAssist commitment hashes replace highest v3 selected "
            "commitment hashes; final slots sorted by commitment hash."
        ),
        "selection_rule_commitment_sha256": rule_commitment,
        "v3_selected_commitment_count": len(source_by_commitment),
        "holoassist_commitment_count": len(holo_by_commitment),
        "retained_v3_commitments": selection[
            "retained_v3_commitments"
        ],
        "removed_v3_commitments": selection[
            "removed_v3_commitments"
        ],
        "selected_holoassist_commitments": selection[
            "selected_holoassist_commitments"
        ],
        "final_selection_transcript": copy.deepcopy(final_descriptors),
    }
    roster_construction = {
        "target_group_count": TARGET_GROUP_COUNT,
        "committed_group_count": len(groups),
        "replaced_v3_group_count": len(
            selection["removed_v3_commitments"]
        ),
        "selected_holoassist_group_count": holo_count,
        "complete_production_closure_count": production_closure_count,
        "all_groups_conditional": all(
            row["conditional_status"] == "CONDITIONAL" for row in groups
        ),
        "selection_used_commitment_hashes_only": True,
        "identities_withheld_publicly": True,
    }
    lineage_composition_private = {
        "selected_dataset_lineage_counts": dict(
            sorted(lineage_counts.items())
        ),
        "selected_dataset_lineage_count": len(lineage_counts),
        "required_dataset_lineage_count": MINIMUM_DATASET_LINEAGES,
        "selected_production_closure_count": production_closure_count,
        "required_production_closure_count": (
            MINIMUM_PRODUCTION_CLOSURES
        ),
        "lineage_constraint_satisfied": lineage_ready,
        "production_closure_constraint_satisfied": production_ready,
    }
    decision = {
        "decision": decision_value,
        "count_constraint_satisfied": count_ready,
        "lineage_constraint_satisfied": lineage_ready,
        "holoassist_constraint_satisfied": holo_ready,
        "production_closure_constraint_satisfied": production_ready,
        "repair_reason": (
            None
            if ready
            else "One or more frozen v3.1 count, lineage, HoloAssist, or "
            "production-closure constraints failed."
        ),
    }
    historical_v3 = {
        "path": V3_PRIVATE_REL.as_posix(),
        "sha256": EXPECTED_INPUT_HASHES[V3_PRIVATE_REL.as_posix()],
        "final_marker": V3_REPAIR,
        "status": "REPAIR_HISTORICAL_UNMODIFIED",
    }
    governance = _governance(
        v3=v3, selection_rule_commitment=rule_commitment
    )

    private = {
        "schema_version": SCHEMA_PRIVATE,
        "ledger_id": LEDGER_ID,
        "created_date": CREATED_DATE,
        "artifact_classification": (
            "RESTRICTED_IDENTITY_BEARING_CONDITIONAL_TEST_GROUP_LEDGER"
        ),
        "authoritative_inputs": authoritative_inputs,
        "historical_v3": historical_v3,
        "source_boundaries": _source_boundaries(),
        "contamination_policy": _contamination_policy(v3, supplement),
        "eligibility_policy": _eligibility_policy(),
        "selection": selection_record,
        "roster_construction": roster_construction,
        "lineage_composition": lineage_composition_private,
        "locks": copy.deepcopy(v3["locks"]),
        "claims": copy.deepcopy(v3["claims"]),
        "custodian_reveal_rules": copy.deepcopy(
            v3["custodian_reveal_rules"]
        ),
        "replacement_policy": copy.deepcopy(v3["replacement_policy"]),
        "selected_groups": groups,
        "replacement_reserve": {
            "inherited_v3_unselected_neutral_pool": copy.deepcopy(
                v3["unselected_neutral_replacement_pool"]
            ),
            "removed_v3_selected_groups": [
                copy.deepcopy(source_by_commitment[value])
                for value in selection["removed_v3_commitments"]
            ],
            "unselected_holoassist_commitments_not_eligible_under_"
            "preserved_policy": selection[
                "unselected_holoassist_commitments"
            ],
        },
        "governance": governance,
        "decision": decision,
        "final_marker": marker,
        "sealed_private_roster_commitment_sha256": "",
    }
    private["sealed_private_roster_commitment_sha256"] = (
        compute_private_roster_commitment(private)
    )

    public_groups = [
        {
            "slot": row["slot"],
            "dataset_lineage": row["dataset_lineage"],
            "source_pool": row["source_pool"],
            "source_commitment_sha256": row[
                "source_commitment_sha256"
            ],
            "v3_1_group_commitment_sha256": row[
                "v3_1_group_commitment_sha256"
            ],
            "commitment_algorithm": (
                "SHA-256(private deterministic salt || NUL || canonical "
                "private group JSON)"
            ),
            "conditional_status": "CONDITIONAL",
            "production_closure_complete": True,
            "timing_closed": row["timing_closed"],
            "video_exact_access_resolved": False,
            "audio_exact_access_resolved": False,
            "test_construction_locked": True,
            "distribution_locked": True,
        }
        for row in groups
    ]
    public = {
        "schema_version": SCHEMA_PUBLIC,
        "commitment_id": COMMITMENT_ID,
        "created_date": CREATED_DATE,
        "artifact_classification": (
            "PUBLIC_IDENTITY_FREE_GOVERNANCE_AND_ROSTER_COMMITMENT"
        ),
        "authoritative_inputs": authoritative_inputs,
        "historical_v3": historical_v3,
        "source_boundaries": _source_boundaries(),
        "contamination_policy": _contamination_policy(v3, supplement),
        "eligibility_policy": _eligibility_policy(),
        "selection": selection_record,
        "roster_construction": roster_construction,
        "lineage_composition": {
            "selected_dataset_lineage_counts": dict(
                sorted(lineage_counts.items())
            ),
            "selected_dataset_lineages": sorted(lineage_counts),
            "selected_dataset_lineage_count": len(lineage_counts),
            "required_dataset_lineage_count": MINIMUM_DATASET_LINEAGES,
            "selected_production_closure_count": (
                production_closure_count
            ),
            "required_production_closure_count": (
                MINIMUM_PRODUCTION_CLOSURES
            ),
            "lineage_constraint_satisfied": lineage_ready,
            "production_closure_constraint_satisfied": production_ready,
        },
        "locks": copy.deepcopy(v3["locks"]),
        "claims": copy.deepcopy(v3["claims"]),
        "custodian_reveal_rules": copy.deepcopy(
            v3["custodian_reveal_rules"]
        ),
        "replacement_policy": copy.deepcopy(v3["replacement_policy"]),
        "group_commitments": public_groups,
        "sealed_private_roster_commitment_sha256": private[
            "sealed_private_roster_commitment_sha256"
        ],
        "governance": governance,
        "decision": decision,
        "final_marker": marker,
        "split_lock": {
            "algorithm": "SHA-256",
            "canonicalization": (
                "UTF-8 canonical JSON; sorted keys; compact separators"
            ),
            "covered_top_level_fields": list(
                SPLIT_LOCK_COVERED_FIELDS
            ),
            "governance_fields": list(GOVERNANCE_FIELDS),
            "split_lock_sha256": "",
        },
    }
    public["split_lock"]["split_lock_sha256"] = compute_split_lock_hash(
        public
    )
    validate_artifacts(
        root, private=private, public=public, inputs=inputs
    )
    return private, public


def _private_identity_strings(private: dict[str, Any]) -> set[str]:
    identities: set[str] = set()
    for group in private["selected_groups"]:
        evidence = group["identity_and_evidence"]
        if group["dataset_lineage"] == "HOLOASSIST":
            identities.add(
                evidence["opaque_universe_group"]["recording_root"]
            )
            for variant in evidence["opaque_universe_group"]["variants"]:
                identities.add(variant["folder"])
                identities.add(variant["timing_path"])
                identities.add(variant["pose_path"])
        else:
            identities.add(evidence["closure_root"])
            identities.add(evidence["exact_object_or_session_id"])
            identities.update(evidence["closure_aliases"])
    return {value for value in identities if value}


def validate_public_non_disclosure(
    private: dict[str, Any],
    *,
    public_text: str,
    review_text: str,
) -> None:
    combined = public_text + "\n" + review_text
    for identity in sorted(
        _private_identity_strings(private), key=len, reverse=True
    ):
        if identity in combined:
            raise LedgerError(
                "SELECTED_IDENTITY_DISCLOSED_PUBLICLY:" + identity
            )
    forbidden_keys = {
        "identity_and_evidence",
        "closure_root",
        "recording_root",
        "exact_object_or_session_id",
        "closure_aliases",
        "timing_path",
        "pose_path",
        "v3_1_commitment_salt_hex",
    }
    public_value = json.loads(public_text)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if forbidden_keys & set(value):
                raise LedgerError("PRIVATE_KEY_DISCLOSED_PUBLICLY")
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(public_value)


def validate_artifacts(
    root: Path,
    *,
    private: dict[str, Any],
    public: dict[str, Any],
    inputs: dict[str, dict[str, Any]] | None = None,
) -> None:
    if inputs is None:
        inputs = _load_bound_inputs(root)
    _validate_source_markers(inputs)
    v3 = inputs[V3_PRIVATE_REL.as_posix()]
    manifest = inputs[MANIFEST_REL.as_posix()]
    holo_private = inputs[HOLO_PRIVATE_REL.as_posix()]
    holo_public = inputs[HOLO_PUBLIC_REL.as_posix()]
    supplement = inputs[HOLO_SUPPLEMENT_REL.as_posix()]
    _validate_holoassist_sources(
        root,
        manifest=manifest,
        holo_private=holo_private,
        holo_public=holo_public,
        supplement=supplement,
    )
    if private.get("schema_version") != SCHEMA_PRIVATE:
        raise LedgerError("PRIVATE_SCHEMA_MISMATCH")
    if public.get("schema_version") != SCHEMA_PUBLIC:
        raise LedgerError("PUBLIC_SCHEMA_MISMATCH")
    groups = private.get("selected_groups", [])
    if len(groups) != TARGET_GROUP_COUNT:
        raise LedgerError("SELECTED_GROUP_COUNT_MISMATCH")
    if len({row["slot"] for row in groups}) != len(groups):
        raise LedgerError("DUPLICATE_SELECTED_SLOT")
    if len(
        {row["source_commitment_sha256"] for row in groups}
    ) != len(groups):
        raise LedgerError("DUPLICATE_SELECTED_SOURCE_COMMITMENT")

    expected_selection = select_commitment_roster(
        [
            row["group_commitment_sha256"]
            for row in v3["selected_groups"]
        ],
        holo_public["commitments"],
    )
    if private["selection"]["retained_v3_commitments"] != (
        expected_selection["retained_v3_commitments"]
    ):
        raise LedgerError("V3_RETAINED_SELECTION_MISMATCH")
    if private["selection"]["removed_v3_commitments"] != (
        expected_selection["removed_v3_commitments"]
    ):
        raise LedgerError("V3_REMOVED_SELECTION_MISMATCH")
    if private["selection"]["selected_holoassist_commitments"] != (
        expected_selection["selected_holoassist_commitments"]
    ):
        raise LedgerError("HOLOASSIST_SELECTION_MISMATCH")

    public_by_slot = {
        row["slot"]: row for row in public["group_commitments"]
    }
    if len(public_by_slot) != len(groups):
        raise LedgerError("PUBLIC_GROUP_COUNT_MISMATCH")
    for row in groups:
        if row["conditional_status"] != "CONDITIONAL":
            raise LedgerError("SELECTED_GROUP_NOT_CONDITIONAL")
        if not row["production_closure_complete"]:
            raise LedgerError("PRODUCTION_CLOSURE_NOT_COMPLETE")
        if row["semantic_routing_event_count"] != 0:
            raise LedgerError("SELECTED_GROUP_SEMANTIC_EVENT_NONZERO")
        if not row["test_construction_locked"]:
            raise LedgerError("SELECTED_GROUP_CONSTRUCTION_UNLOCKED")
        if not row["distribution_locked"]:
            raise LedgerError("SELECTED_GROUP_DISTRIBUTION_UNLOCKED")
        expected_commitment = compute_group_commitment(row)
        if row["v3_1_group_commitment_sha256"] != expected_commitment:
            raise LedgerError("PRIVATE_GROUP_COMMITMENT_MISMATCH")
        public_row = public_by_slot.get(row["slot"])
        if public_row is None:
            raise LedgerError("PUBLIC_GROUP_COMMITMENT_MISSING")
        if (
            public_row["source_commitment_sha256"]
            != row["source_commitment_sha256"]
            or public_row["v3_1_group_commitment_sha256"]
            != expected_commitment
            or public_row["dataset_lineage"] != row["dataset_lineage"]
        ):
            raise LedgerError("PUBLIC_PRIVATE_GROUP_MISMATCH")
        if row["dataset_lineage"] == "HOLOASSIST":
            if (
                row["timing_closed"] is not True
                or row["video_exact_access_resolved"] is not False
                or row["audio_exact_access_resolved"] is not False
            ):
                raise LedgerError("HOLOASSIST_CONDITIONAL_STATE_MISMATCH")

    lineages = Counter(row["dataset_lineage"] for row in groups)
    closures = sum(
        bool(row["production_closure_complete"]) for row in groups
    )
    ready = (
        len(groups) >= TARGET_GROUP_COUNT
        and len(lineages) >= MINIMUM_DATASET_LINEAGES
        and lineages["HOLOASSIST"] >= HOLOASSIST_SELECTION_COUNT
        and closures >= MINIMUM_PRODUCTION_CLOSURES
    )
    expected_marker = FINAL_READY if ready else FINAL_REPAIR
    if private["final_marker"] != expected_marker:
        raise LedgerError("PRIVATE_FINAL_MARKER_MISMATCH")
    if public["final_marker"] != expected_marker:
        raise LedgerError("PUBLIC_FINAL_MARKER_MISMATCH")
    if private["historical_v3"]["final_marker"] != V3_REPAIR:
        raise LedgerError("PRIVATE_HISTORICAL_V3_STATUS_MISMATCH")
    if public["historical_v3"]["final_marker"] != V3_REPAIR:
        raise LedgerError("PUBLIC_HISTORICAL_V3_STATUS_MISMATCH")
    for field in (
        "locks",
        "claims",
        "custodian_reveal_rules",
        "replacement_policy",
    ):
        if private[field] != v3[field] or public[field] != v3[field]:
            raise LedgerError(f"INHERITED_POLICY_MISMATCH:{field}")

    private_commitment = compute_private_roster_commitment(private)
    if private["sealed_private_roster_commitment_sha256"] != (
        private_commitment
    ):
        raise LedgerError("PRIVATE_ROSTER_COMMITMENT_MISMATCH")
    if public["sealed_private_roster_commitment_sha256"] != (
        private_commitment
    ):
        raise LedgerError("PUBLIC_PRIVATE_ROSTER_COMMITMENT_MISMATCH")
    if set(public["governance"]) != set(GOVERNANCE_FIELDS):
        raise LedgerError("GOVERNANCE_FIELD_COVERAGE_MISMATCH")
    if public["split_lock"]["covered_top_level_fields"] != list(
        SPLIT_LOCK_COVERED_FIELDS
    ):
        raise LedgerError("SPLIT_LOCK_FIELD_LIST_MISMATCH")
    if set(public) - {"split_lock"} != set(
        SPLIT_LOCK_COVERED_FIELDS
    ):
        raise LedgerError("PUBLIC_FIELD_NOT_SPLIT_LOCKED")
    if public["split_lock"]["split_lock_sha256"] != (
        compute_split_lock_hash(public)
    ):
        raise LedgerError("SPLIT_LOCK_HASH_MISMATCH")


def render_markdown(public: dict[str, Any]) -> str:
    lineages = public["lineage_composition"]
    counts = lineages["selected_dataset_lineage_counts"]
    roster = public["roster_construction"]
    return "\n".join(
        [
            "# Untouched Test Group Ledger v3.1",
            "",
            f"- Final marker: `{public['final_marker']}`",
            (
                "- Identity-free committed conditional groups: "
                f"**{roster['committed_group_count']}**"
            ),
            (
                "- Dataset lineages: "
                f"**{lineages['selected_dataset_lineage_count']} / "
                f"{lineages['required_dataset_lineage_count']} required**"
            ),
            (
                "- Lineage composition: **"
                + ", ".join(
                    f"{name} {counts[name]}" for name in sorted(counts)
                )
                + "**"
            ),
            (
                "- Complete production closures: "
                f"**{lineages['selected_production_closure_count']} / "
                f"{lineages['required_production_closure_count']} required**"
            ),
            (
                "- Selected HoloAssist sealed commitments: "
                f"**{roster['selected_holoassist_group_count']}**"
            ),
            "- Test construction locked: **true**",
            "- Distribution locked: **true**",
            "- Public identities: **none**",
            "",
            "## Decision",
            "",
            f"**{public['decision']['decision']}**.",
            "",
            (
                "The v3.1 commitment roster contains twelve conditional "
                "production closures across Assembly101, EPIC, and "
                "HoloAssist. Three HoloAssist commitments replace three "
                "frozen v3 commitments by commitment-hash order only."
            ),
            "",
            (
                "Historical v3 remains unmodified and retains marker "
                f"`{public['historical_v3']['final_marker']}`."
            ),
            "",
            "## Commitment-only selection",
            "",
            (
                "The repair selected the three lexicographically lowest "
                "HoloAssist commitment hashes and removed the three "
                "lexicographically highest frozen-v3 group commitment "
                "hashes. No identity, title, task, label, transcript, media, "
                "timing path, annotation, or semantic field participated."
            ),
            "",
            "## HoloAssist conditional boundary",
            "",
            (
                "All selected HoloAssist commitments are timing-closed and "
                "absent from frozen manifest-v2 identities and the permanent "
                "official README example exclusions. Exact video access and "
                "exact audio access remain unresolved; every group therefore "
                "remains CONDITIONAL."
            ),
            "",
            "## Commitments",
            "",
            (
                "- Selection-rule commitment: "
                f"`{public['selection']['selection_rule_commitment_sha256']}`"
            ),
            (
                "- Sealed private-roster commitment: "
                f"`{public['sealed_private_roster_commitment_sha256']}`"
            ),
            (
                "- Full governance split-lock: "
                f"`{public['split_lock']['split_lock_sha256']}`"
            ),
            (
                "- Per-group private commitments: "
                f"**{len(public['group_commitments'])}**"
            ),
            "",
            "## Preserved governance",
            "",
            (
                "All v3 locks, claims, custodian reveal rules, and "
                "replacement policy are preserved exactly. Identities and "
                "exact technical timing evidence remain only in the "
                "restricted private ledger. The full public governance "
                "surface is covered by the recomputed split-lock."
            ),
            "",
            f"`{public['final_marker']}`",
            "",
        ]
    )


def _write_text(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.chmod(temporary, mode)
    temporary.replace(path)
    os.chmod(path, mode)


def write_outputs(
    root: Path,
    *,
    private: dict[str, Any],
    public: dict[str, Any],
) -> None:
    if (root / PRIVATE_REL).parent.stat().st_mode & 0o777 != (
        RESTRICTED_DIRECTORY_MODE
    ):
        raise LedgerError("RESTRICTED_DIRECTORY_MODE_NOT_0700")
    private_text = json.dumps(private, indent=2, sort_keys=True) + "\n"
    public_text = json.dumps(public, indent=2, sort_keys=True) + "\n"
    review_text = render_markdown(public)
    validate_public_non_disclosure(
        private, public_text=public_text, review_text=review_text
    )
    _write_text(root / PRIVATE_REL, private_text, PRIVATE_FILE_MODE)
    _write_text(root / PUBLIC_REL, public_text, PUBLIC_FILE_MODE)
    _write_text(root / REVIEW_REL, review_text, PUBLIC_FILE_MODE)


def check_permissions(root: Path) -> None:
    checks = (
        ((root / PRIVATE_REL).parent, RESTRICTED_DIRECTORY_MODE),
        (root / PRIVATE_REL, PRIVATE_FILE_MODE),
        (root / PUBLIC_REL, PUBLIC_FILE_MODE),
        (root / REVIEW_REL, PUBLIC_FILE_MODE),
    )
    for path, expected in checks:
        actual = path.stat().st_mode & 0o777
        if actual != expected:
            raise LedgerError(
                f"PERMISSION_MISMATCH:{path.as_posix()}:{oct(actual)}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    private, public = build_artifacts(args.root)
    expected_private = json.dumps(
        private, indent=2, sort_keys=True
    ) + "\n"
    expected_public = json.dumps(
        public, indent=2, sort_keys=True
    ) + "\n"
    expected_review = render_markdown(public)
    if args.check:
        committed_private = load_json(args.root / PRIVATE_REL)
        committed_public = load_json(args.root / PUBLIC_REL)
        validate_artifacts(
            args.root,
            private=committed_private,
            public=committed_public,
        )
        if (args.root / PRIVATE_REL).read_text(
            encoding="utf-8"
        ) != expected_private:
            raise LedgerError("COMMITTED_PRIVATE_LEDGER_NOT_CURRENT")
        if (args.root / PUBLIC_REL).read_text(
            encoding="utf-8"
        ) != expected_public:
            raise LedgerError("COMMITTED_PUBLIC_COMMITMENT_NOT_CURRENT")
        if (args.root / REVIEW_REL).read_text(
            encoding="utf-8"
        ) != expected_review:
            raise LedgerError("COMMITTED_REVIEW_NOT_CURRENT")
        validate_public_non_disclosure(
            committed_private,
            public_text=expected_public,
            review_text=expected_review,
        )
    else:
        write_outputs(args.root, private=private, public=public)
    check_permissions(args.root)
    print(public["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
