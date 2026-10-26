"""Build the sealed untouched-test group ledger v3.

The builder consumes only the neutral-only candidate universe already frozen
in ``source_exposure_alias_manifest_v2.json``.  Selection is performed over
opaque candidate handles and nonsemantic technical metadata.  Identity-bearing
rows are written only to the private ledger; the public artifact and review
document contain commitments, counts, governance, and lock state only.

The first build must use ``--initialize`` to create private random material.
Later builds are deterministic because that material is frozen in the
mode-0600 private ledger.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION_PRIVATE = "av-trace.untouched-test-group-ledger-private/3.0"
SCHEMA_VERSION_PUBLIC = "av-trace.untouched-test-group-commitment/3.0"
LEDGER_ID = "UNTOUCHED_TEST_GROUP_LEDGER_V3"
COMMITMENT_ID = "UNTOUCHED_TEST_GROUP_LEDGER_V3_PUBLIC_COMMITMENT"
CREATED_DATE = "2026-10-14"

FINAL_READY = "UNTOUCHED_TEST_GROUP_LEDGER_V3_FROZEN_PRIVATE_READY"
FINAL_REPAIR = "UNTOUCHED_TEST_GROUP_LEDGER_V3_REPAIR"
MANIFEST_READY = "SOURCE_EXPOSURE_ALIAS_MANIFEST_V2_READY"

MANIFEST_REL = Path(
    "data/rehearsal_plan/source_exposure_alias_manifest_v2.json"
)
PRIVATE_REL = Path(
    "data/restricted/untouched_test_group_ledger_v3_private.json"
)
PUBLIC_REL = Path(
    "data/rehearsal_plan/"
    "untouched_test_group_ledger_v3_public_commitment.json"
)
REVIEW_REL = Path("docs/review/untouched_test_group_ledger_v3.md")

TARGET_GROUP_COUNT = 12
MINIMUM_DATASET_LINEAGES = 3
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
PUBLIC_FILE_MODE = 0o644

SELECTOR_ALLOWED_FIELDS = (
    "opaque_candidate_id",
    "opaque_dataset_lineage_id",
    "opaque_production_lineage_id",
    "rights_access_technical_state",
    "duration_seconds",
    "bytes_availability_state",
    "audio_availability_state",
)
FORBIDDEN_SELECTOR_FIELDS = (
    "closure_root",
    "exact_object_or_session_id",
    "aliases",
    "title",
    "description",
    "prompt",
    "target",
    "rank",
    "candidate_label",
    "route_narrative",
    "outcome",
)
GOVERNANCE_FIELDS = (
    "universe_definition",
    "prior_exclusions",
    "alias_and_exposure_policy",
    "role_separation",
    "seed_commitment",
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
    "source_boundaries",
    "contamination_policy",
    "eligibility_policy",
    "blind_selection",
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

_DURATION_RE = re.compile(r"\bduration_seconds=([0-9]+(?:\.[0-9]+)?)\b")


class LedgerError(ValueError):
    """Raised when v3 construction or validation must fail closed."""


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


def _hmac_hex(key_hex: str, domain: str, value: Any) -> str:
    try:
        key = bytes.fromhex(key_hex)
    except ValueError as exc:
        raise LedgerError("PRIVATE_SECRET_NOT_HEX") from exc
    message = domain.encode("utf-8") + b"\0" + canonical_bytes(value)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _opaque_id(
    seed_hex: str, prefix: str, domain: str, value: Any, length: int = 20
) -> str:
    return f"{prefix}-{_hmac_hex(seed_hex, domain, value)[:length]}"


def _parse_technical_metadata(candidate: dict[str, Any]) -> dict[str, Any]:
    detail = candidate["neutral_evidence"].get("detail", "")
    duration_match = _DURATION_RE.search(detail)
    return {
        "rights_access_technical_state": (
            "OFFICIAL_METADATA_ENUMERATED_RIGHTS_NOT_CLAIMED"
        ),
        "duration_seconds": (
            float(duration_match.group(1)) if duration_match else None
        ),
        "bytes_availability_state": (
            "NOT_AVAILABLE_IN_AUTHORITATIVE_CANDIDATE_ROW"
        ),
        "audio_availability_state": (
            "NOT_AVAILABLE_IN_AUTHORITATIVE_CANDIDATE_ROW"
        ),
    }


def _component_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for component in manifest["alias_graph"]["components"]:
        root = component["closure_root"]
        if root in rows:
            raise LedgerError(f"DUPLICATE_CLOSURE_ROOT:{root}")
        rows[root] = component
    return rows


def derive_eligible_universe(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Recompute the exact neutral-only universe from manifest v2."""
    if manifest.get("final_marker") != MANIFEST_READY:
        raise LedgerError("SOURCE_EXPOSURE_ALIAS_MANIFEST_V2_NOT_READY")
    candidates = manifest.get("candidate_universe", [])
    if not candidates:
        raise LedgerError("NEUTRAL_CANDIDATE_UNIVERSE_EMPTY")

    contaminated = {
        row["closure_root"] for row in manifest["contaminated_closures"]
    }
    components = _component_map(manifest)
    pinned = {
        row["path"]: row for row in manifest["scan_freeze"]["pinned_files"]
    }
    roots: set[str] = set()
    eligible: list[dict[str, Any]] = []
    for candidate in candidates:
        root = candidate["closure_root"]
        if root in roots:
            raise LedgerError(f"DUPLICATE_CANDIDATE_CLOSURE:{root}")
        roots.add(root)
        if root in contaminated:
            raise LedgerError(f"NEUTRAL_CANDIDATE_CONTAMINATED:{root}")
        if candidate.get("semantic_routing_event_count") != 0:
            raise LedgerError(f"NONZERO_ROUTING_EVENT_COUNT:{root}")
        component = components.get(root)
        if component is None:
            raise LedgerError(f"CANDIDATE_CLOSURE_COMPONENT_MISSING:{root}")
        exact_id = candidate["exact_object_or_session_id"]
        if exact_id not in component["aliases"]:
            raise LedgerError(f"EXACT_ID_OUTSIDE_CLOSURE:{root}")
        evidence = candidate["neutral_evidence"]
        pinned_row = pinned.get(evidence["path"])
        if pinned_row is None:
            raise LedgerError(f"NEUTRAL_EVIDENCE_NOT_PINNED:{root}")
        if pinned_row["sha256"] != evidence["sha256"]:
            raise LedgerError(f"NEUTRAL_EVIDENCE_HASH_MISMATCH:{root}")
        eligible.append(copy.deepcopy(candidate))
    return sorted(
        eligible,
        key=lambda row: (
            row["family"],
            row["closure_root"],
            row["exact_object_or_session_id"],
        ),
    )


def _load_or_create_private_material(
    root: Path, *, initialize: bool
) -> dict[str, str]:
    path = root / PRIVATE_REL
    if path.is_file():
        material = load_json(path).get("private_material", {})
        required = {
            "frozen_selection_seed_hex",
            "commitment_master_salt_hex",
        }
        if set(material) != required:
            raise LedgerError("FROZEN_PRIVATE_MATERIAL_INVALID")
        for value in material.values():
            if not isinstance(value, str) or len(value) != 64:
                raise LedgerError("FROZEN_PRIVATE_MATERIAL_INVALID")
            try:
                bytes.fromhex(value)
            except ValueError as exc:
                raise LedgerError("FROZEN_PRIVATE_MATERIAL_INVALID") from exc
        return dict(material)
    if not initialize:
        raise LedgerError("PRIVATE_LEDGER_MISSING_USE_INITIALIZE")
    return {
        "frozen_selection_seed_hex": secrets.token_hex(32),
        "commitment_master_salt_hex": secrets.token_hex(32),
    }


def build_opaque_universe(
    manifest: dict[str, Any],
    private_material: dict[str, str],
) -> list[dict[str, Any]]:
    seed = private_material["frozen_selection_seed_hex"]
    eligible = derive_eligible_universe(manifest)
    rows = []
    seen_opaque: set[str] = set()
    for candidate in eligible:
        root = candidate["closure_root"]
        family = candidate["family"]
        exact_id = candidate["exact_object_or_session_id"]
        opaque_candidate = _opaque_id(
            seed,
            "oc",
            "candidate",
            {"closure_root": root, "exact_id": exact_id},
        )
        if opaque_candidate in seen_opaque:
            raise LedgerError("OPAQUE_CANDIDATE_COLLISION")
        seen_opaque.add(opaque_candidate)
        technical = _parse_technical_metadata(candidate)
        selector_view = {
            "opaque_candidate_id": opaque_candidate,
            "opaque_dataset_lineage_id": _opaque_id(
                seed, "dl", "dataset-lineage", family, 16
            ),
            "opaque_production_lineage_id": _opaque_id(
                seed, "pl", "production-lineage", root, 16
            ),
            **technical,
        }
        if tuple(selector_view) != SELECTOR_ALLOWED_FIELDS:
            raise LedgerError("SELECTOR_VIEW_FIELD_MISMATCH")
        score = _hmac_hex(seed, "blind-selection-score", selector_view)
        rows.append(
            {
                "identity": copy.deepcopy(candidate),
                "selector_view": selector_view,
                "selection_score_sha256": score,
            }
        )
    return rows


def blind_select(
    opaque_universe: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(opaque_universe) < TARGET_GROUP_COUNT:
        raise LedgerError("INSUFFICIENT_NEUTRAL_CANDIDATE_COUNT")
    by_lineage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in opaque_universe:
        lineage = row["selector_view"]["opaque_dataset_lineage_id"]
        by_lineage[lineage].append(row)
    for rows in by_lineage.values():
        rows.sort(
            key=lambda row: (
                row["selection_score_sha256"],
                row["selector_view"]["opaque_candidate_id"],
            )
        )

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    # First maximize independent dataset-lineage representation.
    for lineage in sorted(by_lineage):
        row = by_lineage[lineage][0]
        selected.append(row)
        selected_ids.add(row["selector_view"]["opaque_candidate_id"])
    # Then fill the target by the frozen blind score.
    remaining = sorted(
        (
            row
            for row in opaque_universe
            if row["selector_view"]["opaque_candidate_id"] not in selected_ids
        ),
        key=lambda row: (
            row["selection_score_sha256"],
            row["selector_view"]["opaque_candidate_id"],
        ),
    )
    selected.extend(remaining[: TARGET_GROUP_COUNT - len(selected)])
    selected_ids = {
        row["selector_view"]["opaque_candidate_id"] for row in selected
    }
    unselected = [
        row
        for row in sorted(
            opaque_universe,
            key=lambda item: (
                item["selector_view"]["opaque_dataset_lineage_id"],
                item["selection_score_sha256"],
                item["selector_view"]["opaque_candidate_id"],
            ),
        )
        if row["selector_view"]["opaque_candidate_id"] not in selected_ids
    ]
    selected.sort(
        key=lambda row: (
            row["selection_score_sha256"],
            row["selector_view"]["opaque_candidate_id"],
        )
    )
    return selected, unselected


def _closure_evidence(
    component: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in component["supporting_edges"]:
        for evidence in edge["evidence"]:
            key = (
                evidence["path"],
                evidence["locator"],
                evidence["sha256"],
            )
            rows[key] = {
                "path": evidence["path"],
                "locator": evidence["locator"],
                "sha256": evidence["sha256"],
            }
    return [rows[key] for key in sorted(rows)]


def _group_commitment_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in row.items()
        if key not in {"commitment_salt_hex", "group_commitment_sha256"}
    }


def compute_group_commitment(row: dict[str, Any]) -> str:
    salt = row["commitment_salt_hex"]
    return hashlib.sha256(
        bytes.fromhex(salt) + b"\0" + canonical_bytes(
            _group_commitment_payload(row)
        )
    ).hexdigest()


def _build_private_group(
    *,
    slot: str,
    opaque_row: dict[str, Any],
    component: dict[str, Any],
    private_material: dict[str, str],
) -> dict[str, Any]:
    identity = opaque_row["identity"]
    view = opaque_row["selector_view"]
    salt = _hmac_hex(
        private_material["commitment_master_salt_hex"],
        "group-commitment-salt",
        view["opaque_candidate_id"],
    )
    row = {
        "slot": slot,
        "opaque_candidate_id": view["opaque_candidate_id"],
        "opaque_dataset_lineage_id": view["opaque_dataset_lineage_id"],
        "opaque_production_lineage_id": view[
            "opaque_production_lineage_id"
        ],
        "closure_root": identity["closure_root"],
        "exact_object_or_session_id": identity[
            "exact_object_or_session_id"
        ],
        "dataset_lineage_id": identity["family"],
        "production_lineage_id": identity["closure_root"],
        "closure_kind": "COMPLETE_SOURCE_PARTICIPANT_OR_PRODUCTION_CLOSURE",
        "closure_aliases": copy.deepcopy(component["aliases"]),
        "closure_member_count": len(component["aliases"]),
        "closure_evidence": _closure_evidence(component),
        "neutral_candidate_evidence": copy.deepcopy(
            identity["neutral_evidence"]
        ),
        "semantic_routing_event_count": identity[
            "semantic_routing_event_count"
        ],
        "technical_metadata": {
            key: view[key]
            for key in SELECTOR_ALLOWED_FIELDS
            if key
            not in {
                "opaque_candidate_id",
                "opaque_dataset_lineage_id",
                "opaque_production_lineage_id",
            }
        },
        "selection_score_sha256": opaque_row["selection_score_sha256"],
        "conditional_status": "CONDITIONAL",
        "test_construction_locked": True,
        "distribution_locked": True,
        "commitment_salt_hex": salt,
        "group_commitment_sha256": "",
    }
    row["group_commitment_sha256"] = compute_group_commitment(row)
    return row


def _build_replacement_row(
    opaque_row: dict[str, Any],
    component: dict[str, Any],
) -> dict[str, Any]:
    identity = opaque_row["identity"]
    view = opaque_row["selector_view"]
    return {
        "opaque_candidate_id": view["opaque_candidate_id"],
        "opaque_dataset_lineage_id": view["opaque_dataset_lineage_id"],
        "opaque_production_lineage_id": view[
            "opaque_production_lineage_id"
        ],
        "closure_root": identity["closure_root"],
        "exact_object_or_session_id": identity[
            "exact_object_or_session_id"
        ],
        "dataset_lineage_id": identity["family"],
        "production_lineage_id": identity["closure_root"],
        "closure_aliases": copy.deepcopy(component["aliases"]),
        "neutral_candidate_evidence": copy.deepcopy(
            identity["neutral_evidence"]
        ),
        "technical_metadata": {
            key: view[key]
            for key in SELECTOR_ALLOWED_FIELDS
            if key
            not in {
                "opaque_candidate_id",
                "opaque_dataset_lineage_id",
                "opaque_production_lineage_id",
            }
        },
        "selection_score_sha256": opaque_row["selection_score_sha256"],
        "replacement_eligibility": "UNSELECTED_NEUTRAL_POOL_ONLY",
    }


def _authoritative_inputs(root: Path) -> list[dict[str, str]]:
    path = root / MANIFEST_REL
    if not path.is_file():
        raise LedgerError("AUTHORITATIVE_MANIFEST_MISSING")
    return [
        {
            "path": MANIFEST_REL.as_posix(),
            "role": (
                "Frozen alias closures, contamination exclusions, and "
                "neutral-only candidate universe"
            ),
            "sha256": sha256_file(path),
        }
    ]


def _source_boundaries() -> dict[str, Any]:
    return {
        "network_used": False,
        "media_opened_or_inspected": False,
        "semantic_annotation_bodies_opened": False,
        "transcript_or_caption_bodies_opened": False,
        "model_or_learned_ranking_used": False,
        "candidate_mining_performed": False,
        "authoritative_candidate_source": (
            MANIFEST_REL.as_posix() + "#/candidate_universe"
        ),
        "selection_input_boundary": (
            "Opaque IDs plus dataset/production lineage and nonsemantic "
            "rights/access, duration, byte, and audio-availability "
            "technical state only."
        ),
    }


def _contamination_policy(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_policy_sha256": sha256_value(
            manifest["contamination_policy"]
        ),
        "contaminating_event_types": copy.deepcopy(
            manifest["contamination_policy"]["contaminating_event_types"]
        ),
        "full_alias_closure_invalidation": True,
        "selected_closure_event_requirement": (
            "semantic_routing_event_count must equal zero and closure must be "
            "absent from contaminated_closures"
        ),
        "unknown_or_conflicting_identity_effect": "FAIL_CLOSED",
    }


def _eligibility_policy() -> dict[str, Any]:
    return {
        "required_manifest_marker": MANIFEST_READY,
        "candidate_universe_member_required": True,
        "neutral_only_required": True,
        "zero_semantic_routing_events_required": True,
        "complete_alias_closure_required": True,
        "pinned_neutral_evidence_required": True,
        "previously_contaminated_closure_forbidden": True,
        "status_if_eligible": "CONDITIONAL",
    }


def _locks() -> dict[str, Any]:
    return {
        "test_construction_locked": True,
        "distribution_locked": True,
        "identity_publication_locked": True,
        "evaluation_execution_locked": True,
        "unlock_authorized": False,
    }


def _claims() -> dict[str, Any]:
    return {
        "rights_cleared_claimed": False,
        "media_acquired_claimed": False,
        "audio_available_claimed": False,
        "test_validity_claimed": False,
        "scientific_execution_authorized": False,
        "release_authorized": False,
    }


def _custodian_reveal_rules() -> dict[str, Any]:
    return {
        "identity_mapping_custodian_only": True,
        "allowed_identity_recipients": [
            "DESIGNATED_UNIVERSE_CUSTODIAN",
            "INDEPENDENT_ALIAS_EXPOSURE_AUDITOR_UNDER_LEAST_PRIVILEGE",
        ],
        "forbidden_identity_recipients": [
            "OPAQUE_SELECTOR",
            "TEST_CONSTRUCTION_ROLE",
            "QUESTION_OR_CLAIM_AUTHORING_ROLE",
            "MODEL_DEVELOPMENT_ROLE",
            "DISTRIBUTION_ROLE",
            "PUBLIC_REVIEW_DOCUMENT",
        ],
        "preconditions": [
            "independent audit verifies the committed mapping and closures",
            "signed adjudication explicitly authorizes the named recipient",
            "recipient accepts no-copy and no-semantic-inspection controls",
            "all applicable construction and distribution locks remain enforced",
        ],
        "repair_state_rule": (
            "REPAIR forbids reveal to construction, authoring, development, "
            "evaluation, distribution, or public roles."
        ),
        "post_reveal_failure_rule": (
            "Any eligibility failure after a selected identity has been "
            "revealed revokes the entire proposed split and requires a fresh "
            "seed, universe commitment, and versioned ledger."
        ),
    }


def _replacement_policy() -> dict[str, Any]:
    return {
        "source": "PRIVATE_UNSELECTED_NEUTRAL_POOL_ONLY",
        "order": (
            "same opaque dataset lineage first, then frozen selection score, "
            "then opaque candidate ID"
        ),
        "allowed_before_identity_reveal_only": True,
        "replacement_must_revalidate_full_closure": True,
        "replacement_must_preserve_or_improve_constraints": True,
        "diversity_deficit_rule": (
            "A missing independent dataset lineage cannot be repaired by "
            "substitution when that lineage is absent from the authoritative "
            "neutral pool; expand and recommit the universe instead."
        ),
        "revealed_reserve_list_forbidden": True,
    }


def _governance(seed_commitment: str) -> dict[str, Any]:
    return {
        "universe_definition": (
            "Exactly the manifest-v2 neutral-only candidate universe after "
            "mechanical closure, contamination, zero-event, and pinned-"
            "evidence validation."
        ),
        "prior_exclusions": (
            "Every manifest-v2 contaminated closure and any closure with "
            "unknown, conflicting, incomplete, or nonzero event state."
        ),
        "alias_and_exposure_policy": (
            "Manifest-v2 complete source/participant/production closure and "
            "strict semantic-routing contamination policy."
        ),
        "role_separation": {
            "universe_custodian": "IDENTITY_MAPPING_AND_PRIVATE_EVIDENCE_ONLY",
            "opaque_selector": "OPAQUE_TECHNICAL_VIEW_ONLY",
            "rights_access_reviewer": "TECHNICAL_AND_RIGHTS_GATE_ONLY",
            "alias_exposure_auditor": "INDEPENDENT_PRE_REVEAL_AUDIT",
            "final_adjudicator": "SIGNED_GO_OR_REPAIR_ONLY",
            "construction_and_authoring": "NO_IDENTITY_ACCESS_WHILE_LOCKED",
        },
        "seed_commitment": {
            "algorithm": "SHA-256",
            "frozen_selection_seed_sha256": seed_commitment,
            "raw_seed_location": "PRIVATE_LEDGER_CUSTODIAN_ONLY",
        },
        "count_and_lineage_constraints": {
            "minimum_exact_closure_count": TARGET_GROUP_COUNT,
            "minimum_independent_dataset_lineages": MINIMUM_DATASET_LINEAGES,
            "distinct_complete_production_closure_per_group": True,
        },
        "rights_and_custody_gates": (
            "Eligibility, rights, acquisition, processing, annotation, "
            "evaluation, release, and scientific claims remain separate "
            "fail-closed gates."
        ),
        "reveal_protocol": _custodian_reveal_rules(),
        "replacement_protocol": _replacement_policy(),
        "automatic_fail_closed_rules": [
            "insufficient selected closure count",
            "insufficient independent dataset lineages",
            "selected closure absent from neutral universe",
            "selected closure present in contaminated closures",
            "nonzero semantic-routing event count",
            "incomplete source/participant/production closure",
            "identity visible in public commitment or review",
            "commitment, seed, roster, or split-lock mismatch",
            "private permissions not exactly directory 0700 and file 0600",
        ],
        "independent_audit": {
            "required_before_non_custodian_reveal": True,
            "required_checks": [
                "universe completeness",
                "never-routed neutral status",
                "alias closure completeness",
                "selection transcript determinism",
                "count and lineage composition",
                "commitment verification",
                "permissions and public non-disclosure",
            ],
            "current_signed_go": False,
        },
    }


def _private_roster_projection(private: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_sha256": private["authoritative_inputs"][0]["sha256"],
        "frozen_selection_seed_sha256": private["blind_selection"][
            "frozen_selection_seed_sha256"
        ],
        "selected_groups": copy.deepcopy(private["selected_groups"]),
        "unselected_neutral_replacement_pool": copy.deepcopy(
            private["unselected_neutral_replacement_pool"]
        ),
        "selection_transcript": copy.deepcopy(
            private["blind_selection"]["selection_transcript"]
        ),
        "decision": copy.deepcopy(private["decision"]),
        "final_marker": private["final_marker"],
    }


def compute_private_roster_commitment(private: dict[str, Any]) -> str:
    return sha256_value(_private_roster_projection(private))


def compute_split_lock_payload(public: dict[str, Any]) -> dict[str, Any]:
    return {
        field: copy.deepcopy(public[field])
        for field in SPLIT_LOCK_COVERED_FIELDS
    }


def compute_split_lock_hash(public: dict[str, Any]) -> str:
    return sha256_value(compute_split_lock_payload(public))


def build_artifacts(
    root: Path, *, initialize: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load_json(root / MANIFEST_REL)
    private_material = _load_or_create_private_material(
        root, initialize=initialize
    )
    opaque_universe = build_opaque_universe(manifest, private_material)
    selected, unselected = blind_select(opaque_universe)
    components = _component_map(manifest)

    private_groups = [
        _build_private_group(
            slot=f"V3-TS-{index:02d}",
            opaque_row=row,
            component=components[row["identity"]["closure_root"]],
            private_material=private_material,
        )
        for index, row in enumerate(selected, 1)
    ]
    replacement_pool = [
        _build_replacement_row(
            row, components[row["identity"]["closure_root"]]
        )
        for row in unselected
    ]
    lineage_counts = Counter(
        row["dataset_lineage_id"] for row in private_groups
    )
    opaque_lineage_counts = Counter(
        row["opaque_dataset_lineage_id"] for row in private_groups
    )
    universe_lineage_counts = Counter(
        row["identity"]["family"] for row in opaque_universe
    )
    lineage_ready = len(lineage_counts) >= MINIMUM_DATASET_LINEAGES
    count_ready = len(private_groups) >= TARGET_GROUP_COUNT
    ready = count_ready and lineage_ready
    final_marker = FINAL_READY if ready else FINAL_REPAIR
    decision_value = "FROZEN_PRIVATE_READY" if ready else "REPAIR"
    seed_commitment = hashlib.sha256(
        bytes.fromhex(private_material["frozen_selection_seed_hex"])
    ).hexdigest()

    selection_transcript = [
        {
            "slot": row["slot"],
            "opaque_candidate_id": row["opaque_candidate_id"],
            "opaque_dataset_lineage_id": row[
                "opaque_dataset_lineage_id"
            ],
            "selection_score_sha256": row["selection_score_sha256"],
        }
        for row in private_groups
    ]
    authoritative_inputs = _authoritative_inputs(root)
    private = {
        "schema_version": SCHEMA_VERSION_PRIVATE,
        "ledger_id": LEDGER_ID,
        "created_date": CREATED_DATE,
        "artifact_classification": (
            "RESTRICTED_IDENTITY_BEARING_CONDITIONAL_TEST_GROUP_LEDGER"
        ),
        "private_material": private_material,
        "authoritative_inputs": authoritative_inputs,
        "source_boundaries": _source_boundaries(),
        "contamination_policy": _contamination_policy(manifest),
        "eligibility_policy": _eligibility_policy(),
        "blind_selection": {
            "selector_allowed_fields": list(SELECTOR_ALLOWED_FIELDS),
            "selector_forbidden_fields": list(FORBIDDEN_SELECTOR_FIELDS),
            "frozen_selection_seed_sha256": seed_commitment,
            "algorithm": (
                "HMAC-SHA-256 opaque handles and scores; maximize dataset "
                "lineage representation, then ascending frozen blind score"
            ),
            "universe_count": len(opaque_universe),
            "selection_transcript": selection_transcript,
        },
        "roster_construction": {
            "target_group_count": TARGET_GROUP_COUNT,
            "selected_exact_closure_count": len(private_groups),
            "unselected_neutral_pool_count": len(replacement_pool),
            "selection_used_only_opaque_nonsemantic_technical_fields": True,
            "all_selected_groups_conditional": True,
            "source_participant_production_closure_required": True,
        },
        "lineage_composition": {
            "selected_dataset_lineage_counts": dict(
                sorted(lineage_counts.items())
            ),
            "selected_dataset_lineage_count": len(lineage_counts),
            "required_dataset_lineage_count": MINIMUM_DATASET_LINEAGES,
            "neutral_universe_dataset_lineage_counts": dict(
                sorted(universe_lineage_counts.items())
            ),
            "selected_production_lineage_count": len(
                {row["production_lineage_id"] for row in private_groups}
            ),
            "lineage_constraint_satisfied": lineage_ready,
        },
        "locks": _locks(),
        "claims": _claims(),
        "custodian_reveal_rules": _custodian_reveal_rules(),
        "replacement_policy": _replacement_policy(),
        "selected_groups": private_groups,
        "unselected_neutral_replacement_pool": replacement_pool,
        "governance": _governance(seed_commitment),
        "decision": {
            "decision": decision_value,
            "count_constraint_satisfied": count_ready,
            "lineage_constraint_satisfied": lineage_ready,
            "repair_reason": (
                None
                if ready
                else (
                    "The authoritative neutral-only universe contains "
                    f"{len(universe_lineage_counts)} independent dataset "
                    "lineages, below the required minimum of "
                    f"{MINIMUM_DATASET_LINEAGES}. The sealed twelve-group "
                    "proposal remains locked and must not be revealed for "
                    "construction or distribution."
                )
            ),
        },
        "final_marker": final_marker,
    }
    private["sealed_private_roster_commitment_sha256"] = (
        compute_private_roster_commitment(private)
    )

    public_group_commitments = [
        {
            "slot": row["slot"],
            "opaque_candidate_id": row["opaque_candidate_id"],
            "opaque_dataset_lineage_id": row[
                "opaque_dataset_lineage_id"
            ],
            "conditional_status": row["conditional_status"],
            "test_construction_locked": True,
            "distribution_locked": True,
            "commitment_algorithm": (
                "SHA-256(private per-group salt || NUL || canonical group JSON)"
            ),
            "group_commitment_sha256": row["group_commitment_sha256"],
        }
        for row in private_groups
    ]
    public = {
        "schema_version": SCHEMA_VERSION_PUBLIC,
        "commitment_id": COMMITMENT_ID,
        "created_date": CREATED_DATE,
        "artifact_classification": (
            "PUBLIC_IDENTITY_FREE_GOVERNANCE_AND_ROSTER_COMMITMENT"
        ),
        "authoritative_inputs": authoritative_inputs,
        "source_boundaries": _source_boundaries(),
        "contamination_policy": _contamination_policy(manifest),
        "eligibility_policy": _eligibility_policy(),
        "blind_selection": {
            "selector_allowed_fields": list(SELECTOR_ALLOWED_FIELDS),
            "selector_forbidden_fields": list(FORBIDDEN_SELECTOR_FIELDS),
            "frozen_selection_seed_sha256": seed_commitment,
            "raw_seed_public": False,
            "algorithm": private["blind_selection"]["algorithm"],
            "neutral_universe_count": len(opaque_universe),
            "selection_transcript_sha256": sha256_value(
                selection_transcript
            ),
        },
        "roster_construction": {
            "target_group_count": TARGET_GROUP_COUNT,
            "committed_group_count": len(private_groups),
            "unselected_neutral_pool_count": len(replacement_pool),
            "all_groups_exact_complete_closures": True,
            "all_groups_conditional": True,
            "identities_withheld": True,
        },
        "lineage_composition": {
            "selected_opaque_dataset_lineage_counts": dict(
                sorted(opaque_lineage_counts.items())
            ),
            "selected_dataset_lineage_count": len(lineage_counts),
            "required_dataset_lineage_count": MINIMUM_DATASET_LINEAGES,
            "selected_production_lineage_count": len(private_groups),
            "lineage_constraint_satisfied": lineage_ready,
        },
        "locks": _locks(),
        "claims": _claims(),
        "custodian_reveal_rules": _custodian_reveal_rules(),
        "replacement_policy": _replacement_policy(),
        "group_commitments": public_group_commitments,
        "sealed_private_roster_commitment_sha256": private[
            "sealed_private_roster_commitment_sha256"
        ],
        "governance": _governance(seed_commitment),
        "decision": copy.deepcopy(private["decision"]),
        "final_marker": final_marker,
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
    validate_artifacts(private, public, manifest=manifest)
    return private, public


def _contains_forbidden_selector_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            lower = key.lower()
            if any(token in lower for token in FORBIDDEN_SELECTOR_FIELDS):
                return True
            if _contains_forbidden_selector_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_selector_key(item) for item in value)
    return False


def validate_artifacts(
    private: dict[str, Any],
    public: dict[str, Any],
    *,
    manifest: dict[str, Any],
) -> None:
    if private.get("schema_version") != SCHEMA_VERSION_PRIVATE:
        raise LedgerError("PRIVATE_SCHEMA_VERSION_MISMATCH")
    if public.get("schema_version") != SCHEMA_VERSION_PUBLIC:
        raise LedgerError("PUBLIC_SCHEMA_VERSION_MISMATCH")
    eligible = derive_eligible_universe(manifest)
    eligible_by_root = {row["closure_root"]: row for row in eligible}
    contaminated = {
        row["closure_root"] for row in manifest["contaminated_closures"]
    }
    groups = private.get("selected_groups", [])
    if len(groups) != TARGET_GROUP_COUNT:
        raise LedgerError("SELECTED_GROUP_COUNT_MISMATCH")
    if len({row["closure_root"] for row in groups}) != len(groups):
        raise LedgerError("SELECTED_CLOSURE_NOT_UNIQUE")
    public_commitments = {
        row["slot"]: row for row in public.get("group_commitments", [])
    }
    if len(public_commitments) != len(groups):
        raise LedgerError("PUBLIC_GROUP_COMMITMENT_COUNT_MISMATCH")
    for row in groups:
        root = row["closure_root"]
        candidate = eligible_by_root.get(root)
        if candidate is None:
            raise LedgerError(f"SELECTED_ROOT_NOT_ELIGIBLE:{root}")
        if root in contaminated:
            raise LedgerError(f"SELECTED_ROOT_CONTAMINATED:{root}")
        if row["exact_object_or_session_id"] != candidate[
            "exact_object_or_session_id"
        ]:
            raise LedgerError(f"SELECTED_EXACT_ID_MISMATCH:{root}")
        if row["semantic_routing_event_count"] != 0:
            raise LedgerError(f"SELECTED_EVENT_COUNT_NONZERO:{root}")
        if row["conditional_status"] != "CONDITIONAL":
            raise LedgerError(f"SELECTED_STATUS_NOT_CONDITIONAL:{root}")
        if not row["test_construction_locked"]:
            raise LedgerError(f"SELECTED_CONSTRUCTION_NOT_LOCKED:{root}")
        if not row["distribution_locked"]:
            raise LedgerError(f"SELECTED_DISTRIBUTION_NOT_LOCKED:{root}")
        expected_group = compute_group_commitment(row)
        if row["group_commitment_sha256"] != expected_group:
            raise LedgerError(f"GROUP_COMMITMENT_MISMATCH:{root}")
        public_row = public_commitments.get(row["slot"])
        if public_row is None:
            raise LedgerError(f"PUBLIC_GROUP_COMMITMENT_MISSING:{root}")
        if public_row["group_commitment_sha256"] != expected_group:
            raise LedgerError(f"PUBLIC_GROUP_COMMITMENT_MISMATCH:{root}")
        if public_row["opaque_candidate_id"] != row[
            "opaque_candidate_id"
        ]:
            raise LedgerError(f"PUBLIC_OPAQUE_ID_MISMATCH:{root}")

    if private["blind_selection"]["selector_allowed_fields"] != list(
        SELECTOR_ALLOWED_FIELDS
    ):
        raise LedgerError("SELECTOR_ALLOWED_FIELDS_MISMATCH")
    transcript = private["blind_selection"]["selection_transcript"]
    if _contains_forbidden_selector_key(transcript):
        raise LedgerError("SEMANTIC_OR_IDENTITY_FIELD_IN_SELECTION_TRANSCRIPT")
    seed_hash = hashlib.sha256(
        bytes.fromhex(
            private["private_material"]["frozen_selection_seed_hex"]
        )
    ).hexdigest()
    if seed_hash != private["blind_selection"][
        "frozen_selection_seed_sha256"
    ]:
        raise LedgerError("SEED_COMMITMENT_MISMATCH")
    if seed_hash != public["blind_selection"][
        "frozen_selection_seed_sha256"
    ]:
        raise LedgerError("PUBLIC_SEED_COMMITMENT_MISMATCH")
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
        raise LedgerError("SPLIT_LOCK_FIELD_COVERAGE_MISMATCH")
    public_fields = set(public) - {"split_lock"}
    if public_fields != set(SPLIT_LOCK_COVERED_FIELDS):
        raise LedgerError("PUBLIC_FIELD_NOT_COVERED_BY_SPLIT_LOCK")
    if public["split_lock"]["split_lock_sha256"] != (
        compute_split_lock_hash(public)
    ):
        raise LedgerError("SPLIT_LOCK_MISMATCH")

    selected_lineages = {
        row["dataset_lineage_id"] for row in groups
    }
    expected_ready = (
        len(groups) >= TARGET_GROUP_COUNT
        and len(selected_lineages) >= MINIMUM_DATASET_LINEAGES
    )
    expected_marker = FINAL_READY if expected_ready else FINAL_REPAIR
    if private["final_marker"] != expected_marker:
        raise LedgerError("PRIVATE_FINAL_MARKER_MISMATCH")
    if public["final_marker"] != expected_marker:
        raise LedgerError("PUBLIC_FINAL_MARKER_MISMATCH")
    if private["locks"] != _locks() or public["locks"] != _locks():
        raise LedgerError("LOCK_STATE_MISMATCH")
    if private["claims"] != _claims() or public["claims"] != _claims():
        raise LedgerError("CLAIM_STATE_MISMATCH")


def _identity_strings(private: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for row in private["selected_groups"]:
        values.add(row["closure_root"])
        values.add(row["exact_object_or_session_id"])
        values.update(row["closure_aliases"])
    return {value for value in values if value}


def validate_public_non_disclosure(
    private: dict[str, Any],
    public_text: str,
    review_text: str,
) -> None:
    combined = public_text + "\n" + review_text
    leaked = sorted(
        identity for identity in _identity_strings(private)
        if identity in combined
    )
    if leaked:
        raise LedgerError(
            "SELECTED_IDENTITY_DISCLOSED_PUBLICLY:" + leaked[0]
        )


def render_markdown(public: dict[str, Any]) -> str:
    lineage = public["lineage_composition"]
    decision = public["decision"]
    lines = [
        "# Untouched Test Group Ledger v3",
        "",
        f"- Final marker: `{public['final_marker']}`",
        (
            "- Identity-free committed conditional groups: "
            f"**{public['roster_construction']['committed_group_count']}**"
        ),
        (
            "- Independent dataset lineages: "
            f"**{lineage['selected_dataset_lineage_count']} / "
            f"{lineage['required_dataset_lineage_count']} required**"
        ),
        (
            "- Complete production closures: "
            f"**{lineage['selected_production_lineage_count']}**"
        ),
        "- Test construction locked: **true**",
        "- Distribution locked: **true**",
        "- Public identities: **none**",
        "",
        "## Decision",
        "",
        f"**{decision['decision']}**.",
        "",
    ]
    if decision["repair_reason"]:
        lines.extend([decision["repair_reason"], ""])
    lines.extend(
        [
            "The authoritative neutral-only universe supports the required "
            "group count but does not currently support the required number "
            "of independent dataset lineages. The committed roster therefore "
            "remains sealed, conditional, construction-locked, and "
            "distribution-locked.",
            "",
            "## Blind construction boundary",
            "",
            (
                "Selection used only opaque handles, opaque dataset and "
                "production lineage handles, rights/access technical state, "
                "duration, byte availability, and audio "
                "availability. It did not use titles, descriptions, prompts, "
                "semantic targets, candidate labels, prior ranks, route "
                "narratives, outcomes, media, or annotation bodies."
            ),
            "",
            "## Commitments",
            "",
            (
                "- Frozen seed commitment: "
                f"`{public['blind_selection']['frozen_selection_seed_sha256']}`"
            ),
            (
                "- Sealed private-roster commitment: "
                f"`{public['sealed_private_roster_commitment_sha256']}`"
            ),
            (
                "- Governance split-lock: "
                f"`{public['split_lock']['split_lock_sha256']}`"
            ),
            (
                "- Per-group salted commitments: "
                f"**{len(public['group_commitments'])}**"
            ),
            "",
            "## Custodian-only reveal",
            "",
            (
                "Identity mappings and evidence remain in the restricted "
                "private ledger. Only the designated universe custodian and "
                "an independent alias/exposure auditor operating under "
                "least-privilege controls may inspect them. No identity may "
                "be revealed to construction, question/claim authoring, model "
                "development, evaluation, distribution, or public roles "
                "while this artifact is in REPAIR."
            ),
            "",
            "## Replacement rule",
            "",
            (
                "A pre-reveal technical failure may be replaced only from the "
                "sealed unselected neutral pool in frozen order, with complete "
                "closure revalidation and without weakening any constraint. "
                "The current lineage deficit cannot be repaired by a "
                "same-universe substitution because the missing independent "
                "lineage is absent from the authoritative neutral pool. A "
                "future repair must expand and recommit the universe."
            ),
            "",
            f"`{public['final_marker']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _write_text(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.chmod(temporary, mode)
    temporary.replace(path)
    os.chmod(path, mode)


def write_outputs(
    root: Path,
    private: dict[str, Any],
    public: dict[str, Any],
) -> None:
    private_dir = (root / PRIVATE_REL).parent
    private_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(private_dir, PRIVATE_DIR_MODE)
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
    directory_mode = (root / PRIVATE_REL).parent.stat().st_mode & 0o777
    private_mode = (root / PRIVATE_REL).stat().st_mode & 0o777
    public_mode = (root / PUBLIC_REL).stat().st_mode & 0o777
    review_mode = (root / REVIEW_REL).stat().st_mode & 0o777
    if directory_mode != PRIVATE_DIR_MODE:
        raise LedgerError(
            f"RESTRICTED_DIRECTORY_MODE_MISMATCH:{oct(directory_mode)}"
        )
    if private_mode != PRIVATE_FILE_MODE:
        raise LedgerError(
            f"PRIVATE_LEDGER_MODE_MISMATCH:{oct(private_mode)}"
        )
    if public_mode != PUBLIC_FILE_MODE:
        raise LedgerError(
            f"PUBLIC_COMMITMENT_MODE_MISMATCH:{oct(public_mode)}"
        )
    if review_mode != PUBLIC_FILE_MODE:
        raise LedgerError(
            f"REVIEW_MODE_MISMATCH:{oct(review_mode)}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    private, public = build_artifacts(
        args.root, initialize=args.initialize
    )
    if args.check:
        committed_private = load_json(args.root / PRIVATE_REL)
        committed_public = load_json(args.root / PUBLIC_REL)
        manifest = load_json(args.root / MANIFEST_REL)
        validate_artifacts(
            committed_private, committed_public, manifest=manifest
        )
        expected_private = (
            json.dumps(private, indent=2, sort_keys=True) + "\n"
        )
        expected_public = (
            json.dumps(public, indent=2, sort_keys=True) + "\n"
        )
        expected_review = render_markdown(public)
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
        check_permissions(args.root)
    else:
        write_outputs(args.root, private, public)
        check_permissions(args.root)
    print(public["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
