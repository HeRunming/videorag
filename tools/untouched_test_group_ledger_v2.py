"""Build and audit the alias-resolved untouched-test group ledger v2.

This builder is metadata-only.  It consumes the frozen exposure/alias
manifest, the binding v1 disposition, and exact local access registries.  It
does not scan the repository, mine candidates, open annotations, or inspect
media.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "av-trace.untouched-test-group-ledger/2.0"
LEDGER_ID = "UNTOUCHED_TEST_GROUP_LEDGER_V2"
FINAL_READY = "UNTOUCHED_TEST_GROUP_LEDGER_V2_READY"
FINAL_REPAIR = "UNTOUCHED_TEST_GROUP_LEDGER_V2_REPAIR"
CREATED_DATE = "2026-10-14"

OUTPUT_REL = Path("data/rehearsal_plan/untouched_test_group_ledger_v2.json")
REVIEW_REL = Path("docs/review/untouched_test_group_ledger_v2.md")
MANIFEST_REL = Path(
    "data/rehearsal_plan/source_exposure_alias_manifest_v1.json"
)
DISPOSITION_REL = Path(
    "data/rehearsal_plan/untouched_test_group_ledger_v1_disposition.json"
)
ASSEMBLY_REGISTRY_REL = Path(
    "data/rehearsal_plan/assembly101_authenticated_registry_v1.json"
)
EPIC_REGISTRY_REL = Path(
    "data/rehearsal_plan/assembly_epic_access_registry_v2.json"
)
CC4D_REGISTRY_REL = Path(
    "data/rehearsal_plan/captaincook4d_access_registry_v1.json"
)
AUTHORITATIVE_INPUTS = (
    MANIFEST_REL,
    DISPOSITION_REL,
    ASSEMBLY_REGISTRY_REL,
    EPIC_REGISTRY_REL,
    CC4D_REGISTRY_REL,
)

CONDITIONAL_EVENT_TYPES = {
    "metadata_catalog_only",
    "rights/access_preflight",
    "failed_zero_byte_probe",
}
CONTAMINATING_EVENT_TYPES = {
    "media_acquired",
    "media_indexed",
    "learned_model_ranked",
    "candidate_mined",
    "semantic_prompt_exposed",
    "human_prescreened",
    "annotation_opened",
}
PERMITTED_TECHNICAL_ONLY_ACTIONS = (
    "METADATA_CATALOG_ONLY",
    "RIGHTS_ACCESS_PREFLIGHT_ONLY",
    "FAILED_ZERO_BYTE_PROBE_ONLY",
)
FORBIDDEN_SEMANTICS = (
    "CANDIDATE_MINING",
    "SEMANTIC_PROMPT_EXPOSURE",
    "LEARNED_MODEL_RANKING_OR_RETRIEVAL",
    "MEDIA_INDEXING_ACQUISITION_OR_CONTENT_INSPECTION",
    "HUMAN_SEMANTIC_PRESCREEN",
    "ANNOTATION_TRANSCRIPT_CAPTION_LABEL_OR_SEMANTIC_TIMESTAMP_OPENING",
    "ASR_OCR_AUDIO_TAGGING_EMBEDDING_OR_FEATURE_EXTRACTION",
    "QUESTION_CLAIM_EVIDENCE_PROMPT_OR_EVALUATION_AUTHORING",
)

COMPLETION_ROOT = "EPIC:P35"
COMPLETION_SOURCE_GROUP_ID = "P35"
COMPLETION_EXACT_ID = "P35_107"


class LedgerError(ValueError):
    """Raised when a fail-closed v2 ledger cannot be built or verified."""


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


def input_bindings(root: Path) -> list[dict[str, str]]:
    roles = {
        MANIFEST_REL: "Frozen alias graph, exposure events, eligibility policy, and eleven exact replacement candidates",
        DISPOSITION_REL: "Binding v1 NO-GO disposition, nine conditional survivors, and permanent exclusions",
        ASSEMBLY_REGISTRY_REL: "Exact authenticated Assembly101 participant/session/file metadata",
        EPIC_REGISTRY_REL: "Exact EPIC participant/video metadata and technical candidate identifiers",
        CC4D_REGISTRY_REL: "Exact CaptainCook4D person/environment/recording inventory",
    }
    rows = []
    for relative in AUTHORITATIVE_INPUTS:
        path = root / relative
        if not path.is_file():
            raise LedgerError(f"AUTHORITATIVE_INPUT_MISSING:{relative}")
        rows.append(
            {
                "path": relative.as_posix(),
                "role": roles[relative],
                "sha256": sha256_file(path),
            }
        )
    return rows


def component_maps(
    manifest: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_root: dict[str, dict[str, Any]] = {}
    by_alias: dict[str, dict[str, Any]] = {}
    for component in manifest["alias_graph"]["components"]:
        root = component["closure_root"]
        if root in by_root:
            raise LedgerError(f"DUPLICATE_ALIAS_CLOSURE:{root}")
        by_root[root] = component
        for alias in component["aliases"]:
            if alias in by_alias and by_alias[alias]["closure_root"] != root:
                raise LedgerError(f"ALIAS_IN_MULTIPLE_CLOSURES:{alias}")
            by_alias[alias] = component
    return by_root, by_alias


def indexed_events(
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    rows: list[dict[str, Any]] = []
    by_root: dict[str, list[dict[str, Any]]] = {}
    for index, raw in enumerate(manifest["exposure_events"], 1):
        row = copy.deepcopy(raw)
        row["event_id"] = f"MXE-{index:04d}"
        rows.append(row)
        by_root.setdefault(row["closure_root"], []).append(row)
    return rows, by_root


def eligibility_for_root(
    root: str,
    manifest: dict[str, Any],
    by_root: dict[str, dict[str, Any]],
    events_by_root: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    component = by_root.get(root)
    if component is None:
        raise LedgerError(f"CLOSURE_ROOT_ABSENT_FROM_MANIFEST:{root}")
    events = events_by_root.get(root, [])
    contaminating = [
        event
        for event in events
        if event["event_type"] in CONTAMINATING_EVENT_TYPES
    ]
    unknown = [
        event["event_type"]
        for event in events
        if event["event_type"]
        not in CONDITIONAL_EVENT_TYPES | CONTAMINATING_EVENT_TYPES
    ]
    touched = {
        row["closure_root"]: row
        for row in manifest["current_touched_groups"]
    }
    if unknown:
        raise LedgerError(f"UNKNOWN_EXPOSURE_EVENT_TYPE:{root}:{unknown}")
    if bool(contaminating) != (root in touched):
        raise LedgerError(f"TOUCHED_SUMMARY_EVENT_DISAGREEMENT:{root}")
    return {
        "aliases": list(component["aliases"]),
        "conditional_events": [
            event for event in events if event["event_type"] in CONDITIONAL_EVENT_TYPES
        ],
        "contaminating_events": contaminating,
        "eligible": bool(events) and not contaminating,
    }


def _event_binding(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "evidence": event["evidence"],
    }


def _alias_evidence(component: dict[str, Any]) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in component["supporting_edges"]:
        for evidence in edge["evidence"]:
            key = (
                evidence["path"],
                evidence["locator"],
                evidence["sha256"],
            )
            rows[key] = {
                "aliases": edge["aliases"],
                "path": evidence["path"],
                "locator": evidence["locator"],
                "sha256": evidence["sha256"],
            }
    return [rows[key] for key in sorted(rows)]


def _epic_asset(
    registry: dict[str, Any], source_group_id: str, exact_id: str
) -> dict[str, Any]:
    candidates = registry["epic"]["provisional_candidate_pool"]["candidates"]
    row = next(
        (
            item
            for item in candidates
            if item["source_group_id"] == source_group_id
            and item["video_id"] == exact_id
        ),
        None,
    )
    if row is None:
        raise LedgerError(f"EPIC_EXACT_REGISTRY_BINDING_MISSING:{source_group_id}")
    return {
        "registry_path": EPIC_REGISTRY_REL.as_posix(),
        "registry_locator": (
            "/epic/provisional_candidate_pool/candidates/"
            f"{candidates.index(row)}"
        ),
        "representative_ids_or_assets": [
            {"kind": "video_id", "value": row["video_id"]},
            {"kind": "asset_hash", "value": row["asset_hash"]},
            {
                "kind": "media_manifest_version",
                "value": row["media_manifest_version"],
            },
        ],
    }


def _assembly_asset(
    registry: dict[str, Any], participant: str, exact_id: str
) -> dict[str, Any]:
    rows = registry["deterministic_selection"]["selected_groups"]
    row = next(
        (
            item
            for item in rows
            if item["participant_block_id"] == participant
            and item["session_id"] == exact_id
        ),
        None,
    )
    if row is None:
        raise LedgerError(f"ASSEMBLY_EXACT_REGISTRY_BINDING_MISSING:{participant}")
    return {
        "registry_path": ASSEMBLY_REGISTRY_REL.as_posix(),
        "registry_locator": (
            f"/deterministic_selection/selected_groups/{rows.index(row)}"
        ),
        "representative_ids_or_assets": [
            {"kind": "session_id", "value": row["session_id"]},
            {
                "kind": "representative_mp4_path",
                "value": row["representative_mp4_path"],
            },
            {
                "kind": "representative_mp4_lfs_sha256",
                "value": row["representative_mp4_lfs_sha256"],
            },
        ],
    }


def _cc4d_asset(
    registry: dict[str, Any], source_group_id: str, exact_id: str
) -> dict[str, Any]:
    rows = registry["source_group_policy"]["source_groups"]
    row = next(
        (
            item
            for item in rows
            if item["source_group_id"] == source_group_id
            and exact_id in item["recording_ids"]
        ),
        None,
    )
    if row is None:
        raise LedgerError(f"CC4D_EXACT_REGISTRY_BINDING_MISSING:{source_group_id}")
    return {
        "registry_path": CC4D_REGISTRY_REL.as_posix(),
        "registry_locator": (
            f"/source_group_policy/source_groups/{rows.index(row)}"
        ),
        "representative_ids_or_assets": [
            {"kind": "recording_id", "value": exact_id},
            {"kind": "source_group_id", "value": source_group_id},
            {
                "kind": "person_level_supergroup_id",
                "value": row["person_level_supergroup_id"],
            },
        ],
    }


def _lecture_asset(replacement: dict[str, Any]) -> dict[str, Any]:
    return {
        "registry_path": replacement["evidence"]["path"],
        "registry_locator": replacement["evidence"]["locator"],
        "representative_ids_or_assets": [
            {
                "kind": "exact_local_metadata_candidate_id",
                "value": replacement["exact_locally_enumerated_id"],
            },
            {"kind": "production_closure_root", "value": replacement["closure_root"]},
        ],
    }


def _dataset_lineage(root: str) -> str:
    if root.startswith("EPIC:"):
        return "EPIC_KITCHENS_100"
    if root.startswith("CC4D:"):
        return "CAPTAINCOOK4D"
    if root.startswith("ASSEMBLY101:"):
        return "ASSEMBLY101"
    if root == "SG-MIT-2-003J-L01":
        return "MIT_OPENCOURSEWARE_2_003J"
    if root == "SG-YALE-HIST202-L01":
        return "YALE_OPEN_COURSES_HIST202"
    raise LedgerError(f"UNKNOWN_DATASET_LINEAGE:{root}")


def _production_lineage(root: str) -> str:
    if root.startswith("EPIC:"):
        return f"{root}:PARTICIPANT_KITCHEN_ALL_RECORDINGS_AND_DERIVATIVES"
    if root.startswith("CC4D:"):
        return f"{root}:PERSON_ALL_ENVIRONMENTS_RECORDINGS_AND_DERIVATIVES"
    if root.startswith("ASSEMBLY101:"):
        return f"{root}:PARTICIPANT_ALL_SESSIONS_VIEWS_AND_DERIVATIVES"
    return f"{root}:COMPLETE_LECTURE_PRODUCTION_AND_ALL_DERIVATIVES"


def _closure_text(root: str) -> str:
    if root.startswith("EPIC:"):
        unit = "participant and kitchen lineage across every recording"
    elif root.startswith("CC4D:"):
        unit = "person lineage across every environment, session, take, and recording"
    elif root.startswith("ASSEMBLY101:"):
        unit = "participant lineage across every session and synchronized camera view"
    else:
        unit = "complete named lecture production"
    return (
        f"The {unit}; every media rendition, mirror, view, encode, excerpt, "
        "clip, frame, audio stem, transcript, caption, annotation, label, "
        "semantic timestamp, feature, embedding, retrieval index, prompt, "
        "model output, benchmark record, and present or future derivative "
        "inherits this closure and split."
    )


def _source_group_id(root: str, exact_id: str, disposition_row: dict[str, Any] | None) -> str:
    if disposition_row is not None:
        return disposition_row["source_group_id"]
    if root.startswith("EPIC:"):
        return root.split(":", 1)[1]
    return root


def _registry_binding(
    root: str,
    source_group_id: str,
    exact_id: str,
    replacement: dict[str, Any] | None,
    assembly: dict[str, Any],
    epic: dict[str, Any],
    cc4d: dict[str, Any],
) -> dict[str, Any]:
    if root.startswith("EPIC:"):
        return _epic_asset(epic, source_group_id, exact_id)
    if root.startswith("CC4D:"):
        return _cc4d_asset(cc4d, source_group_id, exact_id)
    if root.startswith("ASSEMBLY101:"):
        return _assembly_asset(assembly, root.split(":", 1)[1], exact_id)
    if replacement is None:
        raise LedgerError(f"LECTURE_REPLACEMENT_BINDING_MISSING:{root}")
    return _lecture_asset(replacement)


def compute_group_lock_hash(row: dict[str, Any]) -> str:
    locked = {key: value for key, value in row.items() if key != "group_lock_hash"}
    return sha256_value(locked)


def compute_split_lock_payload(ledger: dict[str, Any]) -> dict[str, Any]:
    return {
        "ledger_id": ledger["ledger_id"],
        "authoritative_input_hashes": [
            row["sha256"] for row in ledger["authoritative_inputs"]
        ],
        "ordered_slots": [row["slot"] for row in ledger["test_groups"]],
        "ordered_closure_roots": [
            row["closure_root"] for row in ledger["test_groups"]
        ],
        "ordered_group_lock_hashes": [
            row["group_lock_hash"] for row in ledger["test_groups"]
        ],
        "distribution_locked": ledger["locks"]["distribution_locked"],
        "test_construction_locked": ledger["locks"][
            "test_construction_locked"
        ],
        "permitted_technical_only_actions": ledger["policy"][
            "permitted_technical_only_actions"
        ],
        "forbidden_semantics": ledger["policy"]["forbidden_semantics"],
        "contamination_log_hash": sha256_value(ledger["contamination_log"]),
        "decision": ledger["decision"],
    }


def compute_split_lock_hash(ledger: dict[str, Any]) -> str:
    return sha256_value(compute_split_lock_payload(ledger))


def _build_row(
    *,
    slot: str,
    root: str,
    exact_id: str,
    disposition_row: dict[str, Any] | None,
    replacement: dict[str, Any] | None,
    origin: str,
    manifest: dict[str, Any],
    by_root: dict[str, dict[str, Any]],
    events_by_root: dict[str, list[dict[str, Any]]],
    assembly: dict[str, Any],
    epic: dict[str, Any],
    cc4d: dict[str, Any],
) -> dict[str, Any]:
    eligibility = eligibility_for_root(
        root, manifest, by_root, events_by_root
    )
    if not eligibility["eligible"]:
        kinds = sorted(
            {event["event_type"] for event in eligibility["contaminating_events"]}
        )
        raise LedgerError(f"SELECTED_CLOSURE_CONTAMINATED:{root}:{kinds}")
    if "cand-042" in eligibility["aliases"]:
        raise LedgerError("CAND_042_ALIAS_FORBIDDEN")
    source_group_id = _source_group_id(root, exact_id, disposition_row)
    binding = _registry_binding(
        root,
        source_group_id,
        exact_id,
        replacement,
        assembly,
        epic,
        cc4d,
    )
    component = by_root[root]
    row = {
        "slot": slot,
        "split": "test_untouched_v2",
        "selection_origin": origin,
        "closure_root": root,
        "source_group_id": source_group_id,
        "exact_object_or_session_id": exact_id,
        "dataset_lineage_id": _dataset_lineage(root),
        "production_lineage_id": _production_lineage(root),
        "group_closure": _closure_text(root),
        "resolved_aliases": eligibility["aliases"],
        "alias_evidence": _alias_evidence(component),
        "exposure_event_bindings": [
            _event_binding(event)
            for event in eligibility["conditional_events"]
        ],
        "contaminating_event_ids": [],
        "permitted_technical_only_actions": list(
            PERMITTED_TECHNICAL_ONLY_ACTIONS
        ),
        "forbidden_semantics": list(FORBIDDEN_SEMANTICS),
        "conditional_status": "CONDITIONAL_UNTOUCHED",
        "distribution_locked": True,
        "test_construction_locked": True,
        "acquired_claimed": False,
        "rights_cleared_claimed": False,
        "h2_claimed": False,
        **binding,
    }
    row["group_lock_hash"] = compute_group_lock_hash(row)
    return row


def _contamination_log(
    manifest: dict[str, Any],
    disposition: dict[str, Any],
    events_by_root: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    disposition_map = {
        row["participant_block_id"]: row
        for row in disposition["contaminated_groups"]
    }
    rows = []
    for touched in manifest["current_touched_groups"]:
        root = touched["closure_root"]
        events = [
            event
            for event in events_by_root.get(root, [])
            if event["event_type"] in CONTAMINATING_EVENT_TYPES
        ]
        if not events:
            raise LedgerError(f"TOUCHED_GROUP_WITHOUT_CONTAMINATING_EVENT:{root}")
        disposition_row = disposition_map.get(root)
        rows.append(
            {
                "closure_root": root,
                "resolved_aliases": touched["aliases"],
                "contaminating_event_ids": [
                    event["event_id"] for event in events
                ],
                "contaminating_event_types": sorted(
                    {event["event_type"] for event in events}
                ),
                "disposition": (
                    disposition_row["disposition"]
                    if disposition_row
                    else "INELIGIBLE_CONTAMINATED_BY_EXPOSURE_MANIFEST"
                ),
                "v1_disposition_evidence_binding_ids": (
                    disposition_row["evidence_binding_ids"]
                    if disposition_row
                    else []
                ),
            }
        )
    return sorted(rows, key=lambda row: row["closure_root"])


def build_ledger(root: Path) -> dict[str, Any]:
    manifest = load_json(root / MANIFEST_REL)
    disposition = load_json(root / DISPOSITION_REL)
    assembly = load_json(root / ASSEMBLY_REGISTRY_REL)
    epic = load_json(root / EPIC_REGISTRY_REL)
    cc4d = load_json(root / CC4D_REGISTRY_REL)

    if manifest.get("final_marker") != "SOURCE_EXPOSURE_ALIAS_MANIFEST_V1_READY":
        raise LedgerError("EXPOSURE_MANIFEST_NOT_READY")
    if disposition.get("final_marker") != "UNTOUCHED_TEST_GROUP_LEDGER_V1_NO_GO_V2_REQUIRED":
        raise LedgerError("V1_DISPOSITION_NOT_BINDING")
    policy = manifest["untouched_eligibility_policy"]
    if set(policy["conditional_event_types"]) != CONDITIONAL_EVENT_TYPES:
        raise LedgerError("CONDITIONAL_EVENT_POLICY_MISMATCH")
    if set(policy["contaminating_event_types"]) != CONTAMINATING_EVENT_TYPES:
        raise LedgerError("CONTAMINATING_EVENT_POLICY_MISMATCH")

    by_root, _ = component_maps(manifest)
    _, events_by_root = indexed_events(manifest)
    replacements = {
        row["closure_root"]: row
        for row in manifest["candidate_replacement_discovery"]
    }
    survivors = disposition["conditional_survivors"]
    if len(survivors) != 9:
        raise LedgerError("NINE_V1_SURVIVORS_REQUIRED")

    selections: list[tuple[str, str, dict[str, Any] | None, str]] = []
    for survivor in survivors:
        closure_root = survivor["participant_block_id"]
        if closure_root not in replacements:
            raise LedgerError(
                f"SURVIVOR_NOT_IN_MANIFEST_CANDIDATES:{closure_root}"
            )
        selections.append(
            (
                closure_root,
                survivor["exact_object_or_session_id"],
                survivor,
                "V1_CONDITIONAL_SURVIVOR_REVALIDATED",
            )
        )

    survivor_roots = {item[0] for item in selections}
    novel_replacements = [
        row
        for row in manifest["candidate_replacement_discovery"]
        if row["closure_root"] not in survivor_roots
    ]
    for replacement in novel_replacements:
        selections.append(
            (
                replacement["closure_root"],
                replacement["exact_locally_enumerated_id"],
                None,
                "MANIFEST_EXACT_REPLACEMENT_CANDIDATE",
            )
        )

    # The manifest has eleven replacement candidates, but nine are the same
    # survivor closures and therefore yields only two novel groups.  Complete
    # the >=12 freeze with an exact registry-enumerated conditional closure.
    selections.append(
        (
            COMPLETION_ROOT,
            COMPLETION_EXACT_ID,
            None,
            "EXACT_ACCESS_REGISTRY_COMPLETION_GROUP",
        )
    )

    rows = []
    for index, (closure_root, exact_id, survivor, origin) in enumerate(
        selections, 1
    ):
        rows.append(
            _build_row(
                slot=f"V2-TS-{index:02d}",
                root=closure_root,
                exact_id=exact_id,
                disposition_row=survivor,
                replacement=replacements.get(closure_root),
                origin=origin,
                manifest=manifest,
                by_root=by_root,
                events_by_root=events_by_root,
                assembly=assembly,
                epic=epic,
                cc4d=cc4d,
            )
        )

    counts = Counter(row["dataset_lineage_id"] for row in rows)
    contamination = _contamination_log(
        manifest, disposition, events_by_root
    )
    ready = len(rows) >= 12 and len(counts) >= 3
    ledger = {
        "schema_version": SCHEMA_VERSION,
        "ledger_id": LEDGER_ID,
        "created_date": CREATED_DATE,
        "artifact_classification": "METADATA_ONLY_CONDITIONAL_UNTOUCHED_GROUP_FREEZE",
        "authoritative_inputs": input_bindings(root),
        "source_boundaries": {
            "candidate_mining_performed": False,
            "network_used": False,
            "media_opened_or_inspected": False,
            "semantic_annotations_opened": False,
            "model_or_learned_ranking_used": False,
            "inputs_exhaustive": [
                path.as_posix() for path in AUTHORITATIVE_INPUTS
            ],
        },
        "roster_construction": {
            "v1_conditional_survivors_revalidated": len(survivors),
            "manifest_replacement_candidate_count": len(replacements),
            "manifest_replacement_candidates_selected": len(
                {row["closure_root"] for row in rows} & set(replacements)
            ),
            "novel_manifest_replacements_beyond_survivors": len(
                novel_replacements
            ),
            "novel_replacement_shortfall_note": (
                "The manifest's eleven candidates contain the same nine v1 "
                "survivor closures plus only two novel lecture closures. All "
                "eleven were selected; EPIC:P35 was added from the exact "
                "access registry to freeze twelve distinct closures."
            ),
            "registry_completion_closure": COMPLETION_ROOT,
            "selection_not_outcome_or_semantics_based": True,
        },
        "policy": {
            "conditional_event_types": sorted(CONDITIONAL_EVENT_TYPES),
            "contaminating_event_types": sorted(CONTAMINATING_EVENT_TYPES),
            "permitted_technical_only_actions": list(
                PERMITTED_TECHNICAL_ONLY_ACTIONS
            ),
            "forbidden_semantics": list(FORBIDDEN_SEMANTICS),
            "any_contaminating_event_invalidates_full_alias_closure": True,
        },
        "locks": {
            "distribution_locked": True,
            "test_construction_locked": True,
            "unlock_authorized": False,
        },
        "claims": {
            "groups_claimed_acquired": 0,
            "rights_clearance_claimed": False,
            "h2_claimed": False,
            "scientific_execution_authorized": False,
            "release_authorized": False,
        },
        "lineage_composition": {
            "counts": dict(sorted(counts.items())),
            "distinct_count": len(counts),
            "production_lineage_count": len(
                {row["production_lineage_id"] for row in rows}
            ),
        },
        "contamination_log": contamination,
        "test_groups": rows,
        "decision": {
            "minimum_group_count": 12,
            "frozen_group_count": len(rows),
            "minimum_lineage_count": 3,
            "decision": "READY" if ready else "REPAIR",
            "controlled_test_construction": "LOCKED",
        },
        "split_lock": {
            "algorithm": "SHA-256",
            "canonicalization": "UTF-8 canonical JSON; sorted keys; compact separators",
            "split_lock_sha256": "",
        },
        "final_marker": FINAL_READY if ready else FINAL_REPAIR,
    }
    ledger["split_lock"]["split_lock_sha256"] = compute_split_lock_hash(
        ledger
    )
    validate_ledger(ledger, manifest=manifest)
    return ledger


def validate_ledger(
    ledger: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
) -> None:
    if ledger.get("schema_version") != SCHEMA_VERSION:
        raise LedgerError("SCHEMA_VERSION_MISMATCH")
    groups = ledger.get("test_groups", [])
    if len(groups) < 12:
        raise LedgerError("FEWER_THAN_12_GROUPS")
    if not ledger["locks"]["distribution_locked"]:
        raise LedgerError("DISTRIBUTION_NOT_LOCKED")
    if not ledger["locks"]["test_construction_locked"]:
        raise LedgerError("TEST_CONSTRUCTION_NOT_LOCKED")
    if ledger["claims"] != {
        "groups_claimed_acquired": 0,
        "rights_clearance_claimed": False,
        "h2_claimed": False,
        "scientific_execution_authorized": False,
        "release_authorized": False,
    }:
        raise LedgerError("PROHIBITED_CLAIM_PRESENT")
    if not ledger["contamination_log"]:
        raise LedgerError("DERIVED_CONTAMINATION_LOG_EMPTY")

    roots = [row["closure_root"] for row in groups]
    if len(roots) != len(set(roots)):
        raise LedgerError("DUPLICATE_CLOSURE_ROOT")
    if len({row["dataset_lineage_id"] for row in groups}) < 3:
        raise LedgerError("FEWER_THAN_3_LINEAGES")
    for row in groups:
        if "cand-042" in row["resolved_aliases"]:
            raise LedgerError("CAND_042_ALIAS_FORBIDDEN")
        if row["conditional_status"] != "CONDITIONAL_UNTOUCHED":
            raise LedgerError(f"NONCONDITIONAL_SELECTED_ROW:{row['closure_root']}")
        if row["contaminating_event_ids"]:
            raise LedgerError(f"ROW_HAS_CONTAMINATION:{row['closure_root']}")
        if row["group_lock_hash"] != compute_group_lock_hash(row):
            raise LedgerError(f"GROUP_LOCK_MISMATCH:{row['closure_root']}")

    if manifest is not None:
        by_root, by_alias = component_maps(manifest)
        _, events_by_root = indexed_events(manifest)
        touched = {
            row["closure_root"]
            for row in manifest["current_touched_groups"]
        }
        for row in groups:
            root = row["closure_root"]
            component = by_root.get(root) or by_alias.get(root)
            if component is None:
                raise LedgerError(f"SELECTED_ROOT_NOT_ALIAS_RESOLVED:{root}")
            resolved_root = component["closure_root"]
            if resolved_root in touched:
                raise LedgerError(f"TOUCHED_GROUP_SELECTED:{resolved_root}")
            eligibility = eligibility_for_root(
                resolved_root, manifest, by_root, events_by_root
            )
            if not eligibility["eligible"]:
                raise LedgerError(
                    f"SELECTED_CLOSURE_CONTAMINATED:{resolved_root}"
                )
            if row["resolved_aliases"] != eligibility["aliases"]:
                raise LedgerError(f"ALIAS_SET_MISMATCH:{resolved_root}")
            observed_ids = {
                event["event_id"]
                for event in eligibility["conditional_events"]
            }
            bound_ids = {
                event["event_id"]
                for event in row["exposure_event_bindings"]
            }
            if observed_ids != bound_ids:
                raise LedgerError(
                    f"EXPOSURE_EVENT_BINDING_MISMATCH:{resolved_root}"
                )

    observed_split = ledger["split_lock"]["split_lock_sha256"]
    candidate = copy.deepcopy(ledger)
    candidate["split_lock"]["split_lock_sha256"] = ""
    expected_split = compute_split_lock_hash(candidate)
    if observed_split != expected_split:
        raise LedgerError("SPLIT_LOCK_MISMATCH")
    if ledger["final_marker"] != FINAL_READY:
        raise LedgerError("FINAL_MARKER_NOT_READY")


def render_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "# Untouched Test Group Ledger v2",
        "",
        f"- Final marker: `{ledger['final_marker']}`",
        f"- Frozen conditional groups: **{len(ledger['test_groups'])}**",
        (
            "- Dataset/production lineages: "
            f"**{ledger['lineage_composition']['distinct_count']} / "
            f"{ledger['lineage_composition']['production_lineage_count']}**"
        ),
        "- Distribution locked: **true**",
        "- Test construction locked: **true**",
        "- Acquired, rights-cleared, or H2 claim: **none**",
        "",
        "## Construction boundary",
        "",
        (
            "This ledger was built only from the frozen source exposure/alias "
            "manifest, the binding v1 disposition, and exact local access "
            "registries. It did not use network access, media inspection, "
            "semantic annotations, candidate mining, or learned ranking."
        ),
        "",
        (
            "The manifest exposes eleven replacement candidates, but nine are "
            "the same conditional survivor closures. Therefore all eleven "
            "manifest candidates are retained (nine survivors plus two novel "
            "lecture closures), and exact registry closure `EPIC:P35` "
            "completes the twelve-group freeze."
        ),
        "",
        "## Frozen groups",
        "",
        "| Slot | Closure root | Exact representative | Lineage | Status |",
        "|---|---|---|---|---|",
    ]
    for row in ledger["test_groups"]:
        lines.append(
            f"| {row['slot']} | `{row['closure_root']}` | "
            f"`{row['exact_object_or_session_id']}` | "
            f"`{row['dataset_lineage_id']}` | "
            f"`{row['conditional_status']}` |"
        )
    lines.extend(
        [
            "",
            "## Exposure rule",
            "",
            (
                "Only metadata catalog inspection, rights/access preflight, "
                "and a failed zero-byte probe may remain conditional. "
                "Candidate mining, semantic prompt exposure, learned ranking, "
                "media indexing/acquisition/content inspection, human "
                "prescreen, or opened annotations contaminates the complete "
                "alias closure."
            ),
            "",
            "## Historical contamination",
            "",
            (
                f"The derived contamination log contains "
                f"**{len(ledger['contamination_log'])}** alias-resolved "
                "touched closures. It includes the permanent v1 exclusions "
                "and their manifest event bindings; it is not an empty "
                "default."
            ),
            "",
            "## Split lock",
            "",
            f"`{ledger['split_lock']['split_lock_sha256']}`",
            "",
            f"`{ledger['final_marker']}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(root: Path, ledger: dict[str, Any]) -> None:
    output = root / OUTPUT_REL
    review = root / REVIEW_REL
    output.parent.mkdir(parents=True, exist_ok=True)
    review.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review.write_text(render_markdown(ledger), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    ledger = build_ledger(args.root)
    if args.check:
        committed = load_json(args.root / OUTPUT_REL)
        manifest = load_json(args.root / MANIFEST_REL)
        validate_ledger(committed, manifest=manifest)
        expected = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
        if (args.root / OUTPUT_REL).read_text(encoding="utf-8") != expected:
            raise LedgerError("COMMITTED_LEDGER_NOT_CURRENT")
        if (args.root / REVIEW_REL).read_text(
            encoding="utf-8"
        ) != render_markdown(ledger):
            raise LedgerError("COMMITTED_REVIEW_NOT_CURRENT")
    else:
        write_outputs(args.root, ledger)
    print(ledger["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
