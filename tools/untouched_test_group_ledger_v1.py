"""Build and audit the prospective untouched-test source-group ledger v1.

This tool is intentionally metadata-only.  It reads the already-frozen
source-disjoint scale-up roster and current local access registries; it does
not open media, semantic annotations, candidate artifacts, transcripts, or
model outputs.  The resulting ledger freezes source-group identity and
closure before any controlled test construction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "av-trace.untouched-test-group-ledger/1.0"
LEDGER_ID = "UNTOUCHED_TEST_GROUP_LEDGER_V1"
FINAL_READY = "UNTOUCHED_TEST_GROUP_LEDGER_V1_READY"
FINAL_REPAIR = "UNTOUCHED_TEST_GROUP_LEDGER_V1_REPAIR"
CREATED_DATE = "2026-10-14"

LEDGER_REL = Path(
    "data/rehearsal_plan/untouched_test_group_ledger_v1.json"
)
MARKDOWN_REL = Path("docs/review/untouched_test_group_ledger_v1.md")
SOURCE_PLAN_REL = Path(
    "data/rehearsal_plan/source_disjoint_scaleup_wave_v1.json"
)
ACCESS_INPUTS = (
    Path("data/rehearsal_plan/assembly_epic_access_registry_v2.json"),
    Path("data/rehearsal_plan/captaincook4d_access_registry_v3.json"),
    Path("data/rehearsal_plan/third_lineage_access_registry_v1.json"),
)

EXPECTED_TEST_IDS = (
    "P01",
    "P02",
    "P04",
    "cc4d_p04_e05",
    "cc4d_p06_e02",
    "cc4d_p07_e02",
    "assembly101_p9056",
    "assembly101_p9083",
    "assembly101_p9055",
    "EC-USGS-SHIFT-CURVES",
    "EC-NASA-TO-THE-RESCUE",
    "EC-NARA-CITY-UNDER-ICE",
)

INPUT_ROLES = {
    SOURCE_PLAN_REL.as_posix(): (
        "Frozen exact 12-slot untouched-test roster, grouping blocks, and "
        "pre-semantic split policy"
    ),
    ACCESS_INPUTS[0].as_posix(): (
        "Current locally retained EPIC and Assembly101 access, authority, "
        "participant, and exact-session registry"
    ),
    ACCESS_INPUTS[1].as_posix(): (
        "Current CaptainCook4D route, acquisition-authority, and native-audio "
        "registry"
    ),
    ACCESS_INPUTS[2].as_posix(): (
        "Current independent-lineage access gap and fail-closed selection "
        "registry"
    ),
}

PERMITTED_TECHNICAL_PREFLIGHT = (
    "RIGHTS_AND_ACCESS_DOCUMENT_REVIEW",
    "BYTE_COUNT_AND_OBJECT_IDENTITY_CHECK",
    "CONTAINER_STREAM_INVENTORY_WITHOUT_CONTENT_INSPECTION",
    "WALL_CLOCK_DURATION_CHECK",
    "CRYPTOGRAPHIC_HASH_COMPUTATION_AND_COMPARISON",
)

FORBIDDEN_ACTIVITIES = (
    "CANDIDATE_MINING_OR_YIELD_ESTIMATION",
    "LEARNED_RETRIEVAL_OR_EMBEDDING_INDEX_INSPECTION",
    "ASR_OCR_AUDIO_TAGGING_OR_TRANSCRIPT_GENERATION",
    "CLAP_CLIP_SIGLIP_OR_OTHER_LEARNED_RANKING",
    "LLM_VLM_SUMMARIZATION_OR_MODEL_GUIDED_AUTHORING",
    "PROMPT_TUNING_PROMPT_SELECTION_OR_EVALUATION_DESIGN_USING_THE_GROUP",
    "HUMAN_SEMANTIC_PRESCREEN_WATCHING_OR_LISTENING",
    "OPENING_TRANSCRIPTS_CAPTIONS_NARRATIONS_LABELS_QA_OR_SEMANTIC_TIMESTAMPS",
    "QUESTION_ANSWER_CLAIM_EVIDENCE_SHORTCUT_MODALITY_HOP_OR_DISTANCE_AUTHORING",
    "DEVELOPMENT_OR_CALIBRATION_MODEL_RUNS_ON_ANY_GROUP_ARTIFACT",
)

EXPOSURE_STATES = (
    "RESERVED_UNTOUCHED_METADATA_ONLY",
    "RESERVED_UNTOUCHED_IDENTITY_ONLY",
    "TECHNICAL_PREFLIGHT_IN_PROGRESS_UNTOUCHED",
    "TECHNICALLY_PREFLIGHTED_UNTOUCHED",
    "CONTROLLED_TEST_CONSTRUCTION_UNLOCKED",
    "CONTAMINATED_INVALID_FOR_UNTOUCHED_TEST",
    "WITHDRAWN_OR_RIGHTS_FAILED",
)

EXCLUDED_EXACT_GROUPS = (
    {
        "source_group_id": "P27",
        "participant_block_id": "EPIC:P27",
        "reason": "TRAIN_DEVELOPMENT_AND_ALREADY_TOUCHED",
    },
    {
        "source_group_id": "P28",
        "participant_block_id": "EPIC:P28",
        "reason": "TRAIN_DEVELOPMENT_AND_ALREADY_TOUCHED",
    },
    {
        "source_group_id": "P23",
        "participant_block_id": "EPIC:P23",
        "reason": "DEVELOPMENT_ONLY_DIAGNOSTIC_AND_ALREADY_TOUCHED",
    },
    {
        "source_group_id": "cc4d_p01_e08",
        "participant_block_id": "CC4D:P01",
        "reason": "CAPTAINCOOK4D_WAVE0_DEVELOPMENT_GROUP",
    },
    {
        "source_group_id": "cc4d_p02_e02",
        "participant_block_id": "CC4D:P02",
        "reason": "CAPTAINCOOK4D_WAVE0_DEVELOPMENT_GROUP",
    },
    {
        "source_group_id": "cc4d_p03_e03",
        "participant_block_id": "CC4D:P03",
        "reason": "CAPTAINCOOK4D_WAVE0_DEVELOPMENT_GROUP",
    },
    {
        "source_group_id": "cc4d_p05_e07",
        "participant_block_id": "CC4D:P05",
        "reason": "DEV_CALIBRATION_ASSIGNMENT_AND_TECHNICAL_PREFLIGHT_HISTORY",
    },
    {
        "source_group_id": "P12",
        "participant_block_id": "EPIC:P12",
        "reason": "DEV_CALIBRATION_ASSIGNMENT",
    },
    {
        "source_group_id": "assembly101_p9051",
        "participant_block_id": "ASSEMBLY101:9051",
        "reason": "DEV_CALIBRATION_ASSIGNMENT",
    },
    {
        "source_group_id": "SG-OXFORD-QM-001",
        "participant_block_id": "OXFORD_QM:LECTURE01",
        "reason": "TRAIN_DEVELOPMENT_SOURCE",
    },
    {
        "source_group_id": "SG-OXFORD-DHL-CONSCIOUSNESS",
        "participant_block_id": "OXFORD_DHL:CONSCIOUSNESS",
        "reason": "TRAIN_DEVELOPMENT_SOURCE",
    },
    {
        "source_group_id": "SG-MIT-RES12-003-L01",
        "participant_block_id": "MIT_RES12:LECTURE01",
        "reason": "DEV_CALIBRATION_SOURCE",
    },
    {
        "source_group_id": "SG-YALE-PHYS200-L01",
        "participant_block_id": "YALE_PHYS200:LECTURE01",
        "reason": "DEV_CALIBRATION_SOURCE",
    },
)


class LedgerError(ValueError):
    """Raised when the ledger cannot be built or audited fail-closed."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LedgerError(f"JSON_OBJECT_REQUIRED:{path.as_posix()}")
    return value


def _input_rows(root: Path) -> list[dict[str, str]]:
    rows = []
    for relative in (SOURCE_PLAN_REL, *ACCESS_INPUTS):
        path = root / relative
        if not path.is_file():
            raise LedgerError(f"AUTHORITATIVE_INPUT_MISSING:{relative}")
        rows.append(
            {
                "path": relative.as_posix(),
                "sha256": _sha256_file(path),
                "role": INPUT_ROLES[relative.as_posix()],
            }
        )
    return rows


def _access_summary(root: Path) -> dict[str, Any]:
    assembly_epic = _load_json(root / ACCESS_INPUTS[0])
    captain = _load_json(root / ACCESS_INPUTS[1])
    third = _load_json(root / ACCESS_INPUTS[2])
    return {
        "epic_kitchens_100": {
            "registry_decision_token": assembly_epic["decision_token"],
            "media_acquisition_decision": assembly_epic["epic"]["decisions"][
                "media_acquisition"
            ],
            "media_processing_authorized": assembly_epic[
                "authorizations_created"
            ]["media_processing"],
            "ledger_disposition": "CONDITIONAL_RESERVE",
        },
        "assembly101": {
            "registry_decision_token": assembly_epic["decision_token"],
            "current_host_media_access_proven": assembly_epic["assembly101"][
                "access"
            ]["current_host_media_access_proven"],
            "media_acquisition_decision": assembly_epic["assembly101"][
                "decisions"
            ]["media_acquisition"],
            "media_processing_authorized": assembly_epic[
                "authorizations_created"
            ]["media_processing"],
            "ledger_disposition": "CONDITIONAL_RESERVE",
        },
        "captaincook4d": {
            "registry_decision_token": captain["decision_token"],
            "route_readiness": captain["route_readiness"]["status"],
            "bulk_media_download": captain["authorization"][
                "bulk_media_download"
            ],
            "internal_media_processing": captain["authorization"][
                "internal_media_processing"
            ],
            "native_audio": captain["native_audio"][
                "native_audio_availability"
            ],
            "ledger_disposition": "CONDITIONAL_RESERVE",
        },
        "independent_lineage_access": {
            "registry_decision_token": third["decision_token"],
            "candidate_pool_status": third["candidate_pool"]["status"],
            "candidate_pool_freeze": third["separate_decisions"][
                "candidate_pool_freeze"
            ],
            "media_acquisition": third["separate_decisions"][
                "media_acquisition"
            ],
            "note": (
                "This registry does not clear any public-production test slot; "
                "the USGS, NASA/JPL, and NARA rows remain identity-only "
                "conditional reserves under their source-plan rights states."
            ),
        },
    }


def _closure_scope(row: Mapping[str, Any]) -> str:
    dataset = row["dataset_lineage_id"]
    if dataset == "EPIC_KITCHENS_100":
        prefix = (
            "The complete EPIC participant block, including every kitchen "
            "session and selected or unselected recording"
        )
    elif dataset == "CAPTAINCOOK4D":
        prefix = (
            "The complete CaptainCook4D person block across every environment, "
            "recipe, session, take, and recording"
        )
    elif dataset == "ASSEMBLY101":
        prefix = (
            "The complete Assembly101 participant block across every session "
            "and every synchronized ego or static camera view"
        )
    else:
        prefix = (
            "The complete named publisher production, including every "
            "rendition, mirror, excerpt, edit, embedded component, and archive "
            "copy"
        )
    return (
        f"{prefix}; all media, views, encodes, clips, frames, audio stems, "
        "captions, transcripts, ASR, annotations, labels, QA, semantic "
        "timestamps, features, embeddings, retrieval indexes, prompts, model "
        "outputs, benchmark records, and present or future derivatives inherit "
        "this group and split."
    )


def _enumeration_basis(dataset_lineage_id: str) -> str:
    return {
        "EPIC_KITCHENS_100": (
            "EXACT_PARTICIPANT_AND_SESSION_LOCALLY_ENUMERATED_IN_FROZEN_"
            "NONSEMANTIC_OFFICIAL_METADATA"
        ),
        "CAPTAINCOOK4D": (
            "EXACT_PERSON_ENVIRONMENT_AND_RECORDING_LOCALLY_ENUMERATED_IN_"
            "SOURCE_GROUP_INVENTORY"
        ),
        "ASSEMBLY101": (
            "EXACT_PARTICIPANT_AND_SESSION_LOCALLY_ENUMERATED_IN_"
            "AUTHENTICATED_NONSEMANTIC_METADATA"
        ),
        "USGS_PUBLIC_MEDIA": "EXACT_PUBLISHER_ITEM_IDENTITY_ONLY",
        "NASA_JPL_DOCUMENTARY": "EXACT_PUBLISHER_ITEM_IDENTITY_ONLY",
        "NARA_ARCHIVAL_FILM": "EXACT_ARCHIVE_CATALOG_IDENTITY_ONLY",
    }[dataset_lineage_id]


def _group_lock_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "slot",
        "source_group_id",
        "exact_object_or_session_id",
        "participant_block_id",
        "dataset_lineage_id",
        "production_lineage_id",
        "group_closure",
        "reservation_class",
        "rights_access_state",
        "exposure_state",
        "split",
    )
    return {field: row[field] for field in fields}


def compute_group_lock_hash(row: Mapping[str, Any]) -> str:
    """Return the deterministic lock hash for one group row."""
    return _sha256_value(_group_lock_payload(row))


def _replacement_policy() -> dict[str, Any]:
    return {
        "outcome_conditioned_replacement_forbidden": True,
        "minimum_frozen_group_count": 12,
        "lineage_count_must_not_decrease": True,
        "automatic_replacement_rule": (
            "Replacement is allowed only before semantic/model exposure, only "
            "from the predeclared untouched reserve for that same "
            "dataset/production lineage, and only with a versioned addendum "
            "that preserves 12 occupied slots and the frozen lineage counts."
        ),
        "failure_rule": (
            "If no same-lineage untouched reserve survives, leave the slot "
            "vacant, mark the ledger REPAIR, and do not backfill from a more "
            "convenient or higher-yield lineage."
        ),
        "replacement_reasons_allowed": [
            "RIGHTS_OR_ACCESS_FAILURE",
            "BYTE_OR_HASH_IDENTITY_FAILURE",
            "STREAM_OR_DURATION_TECHNICAL_FAILURE",
            "PARTICIPANT_OR_PRODUCTION_LINEAGE_COLLISION",
            "CONTAMINATION_EVENT",
            "WITHDRAWAL_OR_DELETION_REQUIREMENT",
        ],
        "predeclared_same_lineage_reserves": {
            "EPIC_KITCHENS_100": [
                {
                    "rank": 1,
                    "source_group_id": "P35",
                    "exact_object_or_session_id": "P35_107",
                    "participant_block_id": "EPIC:P35",
                },
                {
                    "rank": 2,
                    "source_group_id": "P33",
                    "exact_object_or_session_id": "P33_109",
                    "participant_block_id": "EPIC:P33",
                },
                {
                    "rank": 3,
                    "source_group_id": "P22",
                    "exact_object_or_session_id": "P22_114",
                    "participant_block_id": "EPIC:P22",
                },
                {
                    "rank": 4,
                    "source_group_id": "P03",
                    "exact_object_or_session_id": "P03_103",
                    "participant_block_id": "EPIC:P03",
                },
            ],
            "CAPTAINCOOK4D": [
                {
                    "rank": 1,
                    "source_group_id": "cc4d_p08_e06",
                    "exact_object_or_session_id": "23_26",
                    "participant_block_id": "CC4D:P08",
                    "closure": "ALL_PERSON_8_ENVIRONMENTS_AND_DERIVATIVES",
                }
            ],
            "ASSEMBLY101": [
                {
                    "rank": rank,
                    "source_group_id": source_group_id,
                    "exact_object_or_session_id": session_id,
                    "participant_block_id": participant,
                }
                for rank, source_group_id, session_id, participant in (
                    (
                        1,
                        "assembly101_p9044",
                        (
                            "nusar-2021_action_both_9044-a08_9044_user_id_"
                            "2021-02-05_154403"
                        ),
                        "ASSEMBLY101:9044",
                    ),
                    (
                        2,
                        "assembly101_p9081",
                        (
                            "nusar-2021_action_both_9081-c13a_9081_user_id_"
                            "2021-02-12_162453"
                        ),
                        "ASSEMBLY101:9081",
                    ),
                    (
                        3,
                        "assembly101_p9043",
                        (
                            "nusar-2021_action_both_9043-b03b_9043_user_id_"
                            "2021-02-05_133926"
                        ),
                        "ASSEMBLY101:9043",
                    ),
                    (
                        4,
                        "assembly101_p9066",
                        (
                            "nusar-2021_action_both_9066-a09_9066_user_id_"
                            "2021-02-17_152039"
                        ),
                        "ASSEMBLY101:9066",
                    ),
                    (
                        5,
                        "assembly101_p9024",
                        (
                            "nusar-2021_action_both_9024-c12c_9024_user_id_"
                            "2021-02-23_153804"
                        ),
                        "ASSEMBLY101:9024",
                    ),
                )
            ],
            "USGS_PUBLIC_MEDIA": [],
            "NASA_JPL_DOCUMENTARY": [
                {
                    "rank": 1,
                    "source_group_id": "EC-NASA-MOONBOUND",
                    "condition": (
                        "Same NASA/JPL documentary lineage only; exact "
                        "identity, closure, and untouched state must be proven."
                    ),
                },
                {
                    "rank": 2,
                    "source_group_id": "EC-NASA-PLANETARY-DEFENDERS",
                    "condition": (
                        "Same NASA/JPL documentary lineage only; exact "
                        "identity, closure, and untouched state must be proven."
                    ),
                },
            ],
            "NARA_ARCHIVAL_FILM": [
                {
                    "rank": 1,
                    "source_group_id": "EC-NARA-MEMPHIS-BELLE",
                    "condition": (
                        "Same NARA archival-film lineage only; exact identity, "
                        "closure, and untouched state must be proven."
                    ),
                },
                {
                    "rank": 2,
                    "source_group_id": "EC-NARA-THUNDERBOLT",
                    "condition": (
                        "Same NARA archival-film lineage only; exact identity, "
                        "closure, and untouched state must be proven."
                    ),
                },
            ],
        },
        "not_automatic_replacements": [
            {
                "source_group_id": "MECCANO",
                "reason": (
                    "A different lineage cannot automatically replace a frozen "
                    "lineage slot; it requires a new prospective ledger version "
                    "before any semantic exposure."
                ),
            }
        ],
        "reserve_contamination_rule": (
            "Any reserve that has been mined, semantically prescreened, exposed "
            "to learned retrieval, or used for prompt/model tuning is removed "
            "from the reserve queue together with its full participant and "
            "production closure."
        ),
    }


def _exclusion_policy() -> dict[str, Any]:
    return {
        "exact_exclusions": [dict(row) for row in EXCLUDED_EXACT_GROUPS],
        "pattern_exclusions": [
            {
                "pattern": "source_group_id starts with cand-",
                "reason": (
                    "All NOAA cand-* and similarly named mined candidate-pool "
                    "groups are development-contaminated and test-ineligible."
                ),
            },
            {
                "pattern": (
                    "Any CaptainCook4D wave0 or reserve participant block after "
                    "candidate mining or semantic/model exposure"
                ),
                "reason": (
                    "Mining contaminates the complete person-level closure, not "
                    "only the viewed recording."
                ),
            },
            {
                "pattern": (
                    "Any source assigned to train-development or "
                    "dev-calibration in the frozen scale-up plan"
                ),
                "reason": "Split assignment is irreversible for primary test.",
            },
        ],
        "irreversible_rule": (
            "Excluded development/calibration groups and their participant or "
            "production closures can never be promoted into this untouched "
            "test ledger."
        ),
    }


def _governance_policy() -> dict[str, Any]:
    return {
        "group_closure_definition": (
            "A frozen group includes the complete participant/session/"
            "production lineage and all media, synchronized or alternate "
            "views, annotations, labels, transcripts, clips, features, model "
            "artifacts, benchmark artifacts, and future derivatives."
        ),
        "permitted_before_controlled_test_construction": list(
            PERMITTED_TECHNICAL_PREFLIGHT
        ),
        "permitted_scope_is_exhaustive": True,
        "forbidden_before_controlled_test_construction": list(
            FORBIDDEN_ACTIVITIES
        ),
        "forbidden_applies_to_humans_and_automated_systems": True,
        "semantic_review_performed_by_this_ledger": False,
        "candidate_mining_performed_by_this_ledger": False,
        "model_guided_selection_performed_by_this_ledger": False,
    }


def _custody_policy() -> dict[str, Any]:
    return {
        "publicly_frozen_fields": [
            "slot",
            "source_group_id",
            "exact_object_or_session_id",
            "participant_block_id",
            "dataset_lineage_id",
            "production_lineage_id",
            "rights_access_state",
            "exposure_state",
            "group_lock_hash",
        ],
        "custodian_only_before_unlock": [
            "media bytes or playable media",
            "authenticated routes, credentials, signed URLs, and storage paths",
            "stream manifests beyond the minimum technical audit record",
            "transcripts, captions, labels, annotations, and semantic metadata",
            "derived features, embeddings, retrieval indexes, and model outputs",
        ],
        "technical_preflight_reveal": (
            "The custodian may reveal only the minimum rights, byte-count, "
            "stream, duration, and hash facts needed for a logged technical "
            "preflight. No playable content or semantic field may be revealed."
        ),
        "controlled_reveal_requires": [
            "train-development and dev-calibration protocol frozen",
            "test construction authorization recorded separately",
            "test-only personnel roster frozen",
            "all exposure logs reconciled with no contamination event",
            "split-lock hash verified",
            "rights/access and custody gates passed for the revealed group",
        ],
        "development_team_reveal_before_unlock": False,
        "unlogged_reveal_is_contamination": True,
    }


def _contamination_policy() -> dict[str, Any]:
    return {
        "events": [],
        "event_schema": {
            "required_fields": [
                "event_id",
                "timestamp_utc",
                "actor_or_system_id",
                "slot",
                "source_group_id",
                "participant_block_id",
                "production_lineage_id",
                "exposure_class",
                "artifact_or_tool",
                "semantic_fields_visible",
                "description",
                "detected_by",
                "disposition",
                "replacement_addendum_id",
            ],
            "exposure_classes": [
                "HUMAN_SEMANTIC_PRESCREEN",
                "CANDIDATE_MINING",
                "LEARNED_RETRIEVAL_INSPECTION",
                "ASR_OR_AUDIO_TAGGING",
                "CLAP_CLIP_SIGLIP_OR_EMBEDDING_RANKING",
                "PROMPT_TUNING_OR_MODEL_GUIDED_AUTHORING",
                "MODEL_EVALUATION_OR_DEVELOPMENT_RUN",
                "SEMANTIC_ANNOTATION_OR_TRANSCRIPT_OPENED",
                "CROSS_SPLIT_LINEAGE_COLLISION",
                "UNLOGGED_OR_UNAUTHORIZED_REVEAL",
            ],
        },
        "automatic_effect": (
            "Invalidate the complete group closure and every member of the same "
            "participant and production-lineage block; never salvage an "
            "unviewed clip, view, encode, or derivative from that closure."
        ),
        "required_response": [
            "seal access and preserve the nonsemantic audit trail",
            "append one immutable contamination event",
            "mark the slot CONTAMINATED_INVALID_FOR_UNTOUCHED_TEST",
            "apply only the frozen same-lineage replacement policy",
            "recompute group and split-lock hashes in a versioned addendum",
        ],
        "no_event_claim": (
            "An empty event list records no known contamination event in this "
            "ledger; it is not proof that acquisition, rights, or H2 exists."
        ),
    }


def _build_group_rows(
    source_plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    source_rows = source_plan["split_pools"]["test_untouched"]
    if [row["source_group_id"] for row in source_rows] != list(
        EXPECTED_TEST_IDS
    ):
        raise LedgerError("FROZEN_TEST_ROSTER_CHANGED")

    result = []
    for source in source_rows:
        row = {
            "slot": source["slot"],
            "source_group_id": source["source_group_id"],
            "exact_object_or_session_id": source[
                "exact_object_or_session_id"
            ],
            "participant_block_id": source["participant_block_id"],
            "dataset_lineage_id": source["dataset_lineage_id"],
            "production_lineage_id": source["production_lineage_id"],
            "split": "test_untouched",
            "enumeration_basis": _enumeration_basis(
                source["dataset_lineage_id"]
            ),
            "group_closure": _closure_scope(source),
            "reservation_class": "CONDITIONAL_RESERVE",
            "rights_access_state": source["rights_state"],
            "exposure_state": source["current_state"],
            "semantic_exposure_allowed_now": False,
            "technical_preflight_allowed_now": True,
            "acquired_claimed": False,
            "rights_cleared_claimed": False,
            "h2_claimed": False,
        }
        row["group_lock_hash"] = compute_group_lock_hash(row)
        result.append(row)
    return result


def _split_lock(
    groups: Sequence[Mapping[str, Any]],
    governance: Mapping[str, Any],
    custody: Mapping[str, Any],
    replacement: Mapping[str, Any],
    exclusions: Mapping[str, Any],
    contamination: Mapping[str, Any],
) -> dict[str, Any]:
    policy_hashes = {
        "governance_policy_sha256": _sha256_value(governance),
        "custody_policy_sha256": _sha256_value(custody),
        "replacement_policy_sha256": _sha256_value(replacement),
        "exclusion_policy_sha256": _sha256_value(exclusions),
        "contamination_policy_sha256": _sha256_value(contamination),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ledger_id": LEDGER_ID,
        "split": "test_untouched",
        "ordered_group_lock_hashes": [
            row["group_lock_hash"] for row in groups
        ],
        "policy_hashes": policy_hashes,
    }
    return {
        "algorithm": "SHA-256",
        "canonicalization": (
            "UTF-8 JSON, sort_keys=true, separators=(',', ':'), "
            "ensure_ascii=false"
        ),
        "ordered_slots": [row["slot"] for row in groups],
        "ordered_group_lock_hashes": payload["ordered_group_lock_hashes"],
        "policy_hashes": policy_hashes,
        "split_lock_sha256": _sha256_value(payload),
        "mutation_rule": (
            "Any identity, closure, state, policy, exclusion, reserve, or "
            "contamination change requires a versioned addendum and a new "
            "split-lock hash before further access."
        ),
    }


def build_ledger(root: Path) -> dict[str, Any]:
    """Build the deterministic ledger from local nonsemantic governance data."""
    source_plan = _load_json(root / SOURCE_PLAN_REL)
    governance = _governance_policy()
    custody = _custody_policy()
    replacement = _replacement_policy()
    exclusions = _exclusion_policy()
    contamination = _contamination_policy()
    groups = _build_group_rows(source_plan)
    lineage_counts = Counter(row["dataset_lineage_id"] for row in groups)
    honest = len(groups) >= 12 and len(lineage_counts) >= 3
    final_marker = FINAL_READY if honest else FINAL_REPAIR

    ledger = {
        "schema_version": SCHEMA_VERSION,
        "ledger_id": LEDGER_ID,
        "created_date": CREATED_DATE,
        "local_timezone": "Asia/Shanghai",
        "artifact_classification": (
            "PROSPECTIVE_UNTOUCHED_TEST_GROUP_FREEZE_AND_CONTAMINATION_"
            "CONTROL_ONLY"
        ),
        "decision": {
            "freeze_decision": "READY" if honest else "REPAIR",
            "controlled_test_construction": "LOCKED",
            "acquisition_readiness": "REPAIR",
            "rights_and_processing_readiness": "REPAIR",
            "basis": (
                "Exactly 12 locally enumerated or identity-frozen prospective "
                "groups are sealed across at least three dataset/production "
                "lineages. Every group remains a conditional reserve; this "
                "ledger grants no acquisition, processing, semantic-review, "
                "model-run, or release authority."
            ),
        },
        "scope": {
            "prospective_untouched_test_groups_frozen": len(groups),
            "distinct_dataset_or_production_lineages": len(lineage_counts),
            "minimum_groups_required": 12,
            "minimum_lineages_required": 3,
            "all_groups_are_conditional_reserves": True,
            "media_acquired_by_this_ledger": False,
            "groups_claimed_acquired": 0,
            "semantic_annotations_opened_by_this_ledger": False,
            "candidate_mining_performed_by_this_ledger": False,
            "model_guided_authoring_performed_by_this_ledger": False,
            "h2_families_created_or_claimed": 0,
            "scientific_test_execution_authorized": False,
            "public_release_authorized": False,
        },
        "authoritative_inputs": _input_rows(root),
        "source_plan_binding": {
            "plan_id": source_plan["plan_id"],
            "plan_created_date": source_plan["created_date"],
            "plan_current_decision": source_plan["current_decision"],
            "selection_rule": (
                "Copy the exact test_untouched roster already frozen in "
                "source_disjoint_scaleup_wave_v1; do not rank, mine, inspect, "
                "or substitute based on semantic content or expected yield."
            ),
        },
        "current_access_registry_summary": _access_summary(root),
        "lineage_composition": {
            "counts": dict(sorted(lineage_counts.items())),
            "distinct_count": len(lineage_counts),
            "independence_claim": (
                "Distinct dataset/publisher production strata for split "
                "composition only; not a claim of acquisition readiness, legal "
                "clearance, statistical independence, or H2 evidence."
            ),
        },
        "governance_policy": governance,
        "exposure_state_machine": {
            "states": list(EXPOSURE_STATES),
            "initial_states_allowed": [
                "RESERVED_UNTOUCHED_METADATA_ONLY",
                "RESERVED_UNTOUCHED_IDENTITY_ONLY",
            ],
            "technical_preflight_transitions": [
                (
                    "RESERVED_UNTOUCHED_METADATA_ONLY -> "
                    "TECHNICAL_PREFLIGHT_IN_PROGRESS_UNTOUCHED"
                ),
                (
                    "RESERVED_UNTOUCHED_IDENTITY_ONLY -> "
                    "TECHNICAL_PREFLIGHT_IN_PROGRESS_UNTOUCHED"
                ),
                (
                    "TECHNICAL_PREFLIGHT_IN_PROGRESS_UNTOUCHED -> "
                    "TECHNICALLY_PREFLIGHTED_UNTOUCHED"
                ),
            ],
            "unlock_transition_requires_separate_authority": (
                "TECHNICALLY_PREFLIGHTED_UNTOUCHED -> "
                "CONTROLLED_TEST_CONSTRUCTION_UNLOCKED"
            ),
            "semantic_or_model_exposure_before_unlock_transition": (
                "CONTAMINATED_INVALID_FOR_UNTOUCHED_TEST"
            ),
            "rights_or_technical_failure_transition": (
                "WITHDRAWN_OR_RIGHTS_FAILED"
            ),
            "state_changes_require_logged_event_and_recomputed_lock": True,
        },
        "custody_and_reveal_policy": custody,
        "test_groups": groups,
        "excluded_development_and_calibration_groups": exclusions,
        "replacement_policy": replacement,
        "contamination_ledger": contamination,
    }
    ledger["split_lock"] = _split_lock(
        groups,
        governance,
        custody,
        replacement,
        exclusions,
        contamination,
    )
    ledger["audit"] = {
        "group_count": len(groups),
        "lineage_count": len(lineage_counts),
        "unique_source_group_ids": len(
            {row["source_group_id"] for row in groups}
        ),
        "unique_participant_blocks": len(
            {row["participant_block_id"] for row in groups}
        ),
        "unique_production_lineage_ids": len(
            {row["production_lineage_id"] for row in groups}
        ),
        "known_contamination_event_count": len(contamination["events"]),
        "all_group_hashes_verified": True,
        "split_lock_verified": True,
        "result": "PASS" if honest else "REPAIR",
    }
    ledger["final_marker"] = final_marker
    validate_ledger(ledger)
    return ledger


def validate_ledger(ledger: Mapping[str, Any]) -> None:
    """Audit count, closure, exposure, exclusions, and split-lock integrity."""
    if ledger.get("schema_version") != SCHEMA_VERSION:
        raise LedgerError("SCHEMA_VERSION_MISMATCH")
    groups = ledger.get("test_groups")
    if not isinstance(groups, list) or len(groups) < 12:
        raise LedgerError("FEWER_THAN_12_FROZEN_GROUPS")
    if [row.get("source_group_id") for row in groups] != list(
        EXPECTED_TEST_IDS
    ):
        raise LedgerError("TEST_GROUP_ORDER_OR_ID_MISMATCH")

    required_group_fields = {
        "slot",
        "source_group_id",
        "exact_object_or_session_id",
        "participant_block_id",
        "dataset_lineage_id",
        "production_lineage_id",
        "group_closure",
        "reservation_class",
        "rights_access_state",
        "exposure_state",
        "split",
        "group_lock_hash",
    }
    for row in groups:
        missing = required_group_fields - set(row)
        if missing:
            raise LedgerError(f"GROUP_FIELDS_MISSING:{sorted(missing)}")
        closure = str(row["group_closure"]).lower()
        for token in ("media", "views", "annotations", "derivatives"):
            if token not in closure:
                raise LedgerError(f"GROUP_CLOSURE_INCOMPLETE:{token}")
        if row["reservation_class"] != "CONDITIONAL_RESERVE":
            raise LedgerError("NONCONDITIONAL_GROUP_PRESENT")
        if row["semantic_exposure_allowed_now"] is not False:
            raise LedgerError("SEMANTIC_EXPOSURE_ENABLED")
        if row["acquired_claimed"] is not False or row["h2_claimed"] is not False:
            raise LedgerError("ACQUISITION_OR_H2_OVERCLAIM")
        if row["group_lock_hash"] != compute_group_lock_hash(row):
            raise LedgerError(f"GROUP_LOCK_MISMATCH:{row['source_group_id']}")

    for field in (
        "source_group_id",
        "participant_block_id",
        "production_lineage_id",
    ):
        values = [row[field] for row in groups]
        if len(values) != len(set(values)):
            raise LedgerError(f"NONUNIQUE_GROUP_FIELD:{field}")

    lineages = Counter(row["dataset_lineage_id"] for row in groups)
    if len(lineages) < 3:
        raise LedgerError("FEWER_THAN_3_LINEAGES")
    if ledger["lineage_composition"]["counts"] != dict(sorted(lineages.items())):
        raise LedgerError("LINEAGE_COUNT_MISMATCH")

    governance = ledger["governance_policy"]
    if governance["permitted_before_controlled_test_construction"] != list(
        PERMITTED_TECHNICAL_PREFLIGHT
    ):
        raise LedgerError("PERMITTED_PREFLIGHT_SCOPE_CHANGED")
    forbidden_text = " ".join(
        governance["forbidden_before_controlled_test_construction"]
    )
    for token in (
        "CANDIDATE_MINING",
        "LEARNED_RETRIEVAL",
        "ASR",
        "CLAP",
        "SIGLIP",
        "PROMPT_TUNING",
        "HUMAN_SEMANTIC_PRESCREEN",
    ):
        if token not in forbidden_text:
            raise LedgerError(f"FORBIDDEN_ACTIVITY_MISSING:{token}")

    contamination = ledger["contamination_ledger"]
    if not isinstance(contamination["events"], list):
        raise LedgerError("CONTAMINATION_EVENTS_NOT_LIST")
    if contamination["events"]:
        raise LedgerError("COMMITTED_V1_HAS_CONTAMINATION_EVENTS")

    split_lock = ledger["split_lock"]
    expected = _split_lock(
        groups,
        governance,
        ledger["custody_and_reveal_policy"],
        ledger["replacement_policy"],
        ledger["excluded_development_and_calibration_groups"],
        contamination,
    )
    if split_lock != expected:
        raise LedgerError("SPLIT_LOCK_MISMATCH")

    expected_marker = (
        FINAL_READY if len(groups) >= 12 and len(lineages) >= 3 else FINAL_REPAIR
    )
    if ledger.get("final_marker") != expected_marker:
        raise LedgerError("FINAL_MARKER_MISMATCH")


def render_markdown(ledger: Mapping[str, Any]) -> str:
    """Render the committed human audit without adding new facts."""
    groups = ledger["test_groups"]
    lineage_counts = ledger["lineage_composition"]["counts"]
    lines = [
        "# Untouched test group ledger v1",
        "",
        f"**Date:** {ledger['created_date']}  ",
        f"**Freeze decision:** `{ledger['decision']['freeze_decision']}`  ",
        f"**Final marker:** `{ledger['final_marker']}`  ",
        "**Controlled test construction:** `LOCKED`  ",
        "**Acquisition / rights readiness:** `REPAIR`",
        "",
        "## Decision",
        "",
        (
            "This ledger prospectively freezes **12** untouched-test source "
            "groups before semantic review or model-guided authoring. They span "
            f"**{len(lineage_counts)}** dataset/publisher production strata. "
            "Every row is a **conditional reserve**: the ledger does not claim "
            "that media was acquired, rights were cleared, semantic review was "
            "performed, or any H2 family exists."
        ),
        "",
        (
            "The freeze is `READY` because exact participant/session/production "
            "identities and full closures can be sealed honestly. Execution "
            "remains `REPAIR` and locked because current access registries do "
            "not authorize the required acquisition and processing."
        ),
        "",
        "## Frozen groups",
        "",
        "| Slot | Source group | Exact object/session | Dataset or production lineage | Exposure state | Rights/access |",
        "|---|---|---|---|---|---|",
    ]
    for row in groups:
        lines.append(
            "| {slot} | `{source_group_id}` | `{exact_object_or_session_id}` "
            "| `{dataset_lineage_id}` | `{exposure_state}` | "
            "`{rights_access_state}` |".format(**row)
        )
    lines.extend(
        [
            "",
            "Lineage composition:",
            "",
        ]
    )
    for lineage, count in lineage_counts.items():
        lines.append(f"- `{lineage}`: {count} group(s)")
    lines.extend(
        [
            "",
            "## Group closure",
            "",
            ledger["governance_policy"]["group_closure_definition"],
            "",
            (
                "Participant blocks are split-level closures. An unviewed clip, "
                "alternate camera, encode, transcript, label file, embedding, "
                "or future derivative cannot be separated from a contaminated "
                "participant or production lineage."
            ),
            "",
            "## Before controlled test construction",
            "",
            "Only these technical preflights are permitted:",
            "",
        ]
    )
    for item in ledger["governance_policy"][
        "permitted_before_controlled_test_construction"
    ]:
        lines.append(f"- `{item}`")
    lines.extend(["", "The exhaustive forbidden set includes:"])
    for item in ledger["governance_policy"][
        "forbidden_before_controlled_test_construction"
    ]:
        lines.append(f"- `{item}`")
    lines.extend(
        [
            "",
            (
                "This explicitly forbids candidate mining, learned-retrieval "
                "inspection, ASR, CLAP/CLIP/SigLIP ranking, prompt tuning, and "
                "human semantic prescreening."
            ),
            "",
            "## Exposure states and custodian-only reveal",
            "",
            (
                "The initial states are metadata-only or identity-only untouched "
                "reservation. Technical preflight may advance a row only to "
                "`TECHNICALLY_PREFLIGHTED_UNTOUCHED`. Any semantic/model "
                "exposure before a separately authorized unlock moves the full "
                "closure to `CONTAMINATED_INVALID_FOR_UNTOUCHED_TEST`."
            ),
            "",
            (
                "Playable media, authenticated routes, semantic metadata, "
                "annotations, transcripts, features, retrieval indexes, and "
                "model outputs remain custodian-only. A technical reviewer may "
                "receive only the minimum rights, byte, stream, duration, and "
                "hash facts. Development staff receive no pre-unlock reveal."
            ),
            "",
            "## Split lock",
            "",
            f"- Algorithm: `{ledger['split_lock']['algorithm']}`",
            (
                "- Split-lock SHA-256: "
                f"`{ledger['split_lock']['split_lock_sha256']}`"
            ),
            (
                "- The hash binds the ordered 12 group hashes plus governance, "
                "custody, replacement, exclusion, and contamination policies."
            ),
            (
                "- Any mutation requires a versioned addendum and recomputed "
                "group and split hashes before further access."
            ),
            "",
            "## Replacement policy",
            "",
            (
                "Replacement is allowed only before semantic/model exposure and "
                "only from the predeclared untouched queue for the same "
                "dataset/production lineage. It must preserve 12 occupied slots "
                "and the frozen lineage counts. Candidate yield, perceived "
                "difficulty, model behavior, or H2 outcome can never trigger a "
                "replacement."
            ),
            "",
            (
                "If no same-lineage untouched reserve survives, the slot remains "
                "vacant and the ledger becomes `REPAIR`; another convenient "
                "lineage cannot silently backfill it."
            ),
            "",
            "## Explicit exclusions",
            "",
            (
                "P23/P27/P28, CaptainCook4D wave0 development groups, assigned "
                "development/calibration groups, all NOAA `cand-*` groups, and "
                "any reserve after mining or semantic/model exposure are "
                "test-ineligible with their complete closures."
            ),
            "",
        ]
    )
    for row in ledger["excluded_development_and_calibration_groups"][
        "exact_exclusions"
    ]:
        lines.append(
            f"- `{row['source_group_id']}` / `{row['participant_block_id']}`: "
            f"`{row['reason']}`"
        )
    lines.extend(
        [
            "",
            "## Contamination events",
            "",
            (
                "The committed event list is empty: no known contamination event "
                "is recorded by this ledger. This is not proof of acquisition, "
                "rights, or H2. Every future event must identify the actor/tool, "
                "group and closure, exposure class, visible semantic fields, "
                "disposition, and replacement addendum."
            ),
            "",
            (
                "A contamination event invalidates the complete participant and "
                "production closure. The custodian must seal access, append the "
                "event, apply only the same-lineage replacement rule, and "
                "recompute the split lock."
            ),
            "",
            "## Audit result",
            "",
            f"- Frozen groups: **{ledger['audit']['group_count']}**",
            f"- Distinct lineages: **{ledger['audit']['lineage_count']}**",
            (
                "- Known contamination events: "
                f"**{ledger['audit']['known_contamination_event_count']}**"
            ),
            f"- Audit: **{ledger['audit']['result']}**",
            "",
            f"`{ledger['final_marker']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _json_text(ledger: Mapping[str, Any]) -> str:
    return json.dumps(ledger, indent=2, sort_keys=True) + "\n"


def _check_committed(root: Path, ledger: Mapping[str, Any]) -> None:
    ledger_path = root / LEDGER_REL
    markdown_path = root / MARKDOWN_REL
    expected_json = _json_text(ledger)
    expected_markdown = render_markdown(ledger)
    if not ledger_path.is_file():
        raise LedgerError(f"COMMITTED_LEDGER_MISSING:{LEDGER_REL}")
    if not markdown_path.is_file():
        raise LedgerError(f"COMMITTED_MARKDOWN_MISSING:{MARKDOWN_REL}")
    if ledger_path.read_text(encoding="utf-8") != expected_json:
        raise LedgerError("COMMITTED_LEDGER_NOT_CURRENT")
    if markdown_path.read_text(encoding="utf-8") != expected_markdown:
        raise LedgerError("COMMITTED_MARKDOWN_NOT_CURRENT")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help="Write the deterministic JSON ledger and Markdown audit",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Audit committed outputs against current authoritative inputs",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    ledger = build_ledger(root)

    if args.write:
        ledger_path = root / LEDGER_REL
        markdown_path = root / MARKDOWN_REL
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(_json_text(ledger), encoding="utf-8")
        markdown_path.write_text(render_markdown(ledger), encoding="utf-8")
    else:
        _check_committed(root, ledger)

    print(ledger["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
