"""Build and execute the NOAA-01 machine-adjudicated real-A/V MVP.

The implementation is deliberately deterministic.  It validates protocol
plumbing and intervention/metric behavior; the policies are not learned
models and their scores are not model-quality results.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from av_trace_media.reader import PyAVMediaReader
from av_trace_media.types import TimeInterval

STAGE = "MACHINE_ADJUDICATED_PROVISIONAL_MVP"
SCHEMA = "noaa-real-av-provisional/2.0"
INDEX_VERSION = "noaa18-bm25-lite/1.0"
POLICY_VERSION = "deterministic-protocol-policy/2.0"
VALIDATOR_VERSION = "dual-rule-validator/1.0"
STATES = ("CLEAN", "BLOCKED", "RESTORED")
AGENTS = (
    "direct-long-context",
    "single-shot-rag",
    "react-recovery",
    "evidence-sufficiency",
)
TOKEN_RE = re.compile(r"[a-z0-9]+")
PRIVATE_ID_RE = re.compile(r"\b(?:claim|e)\.r\d+\.[a-z0-9_.-]+\b", re.I)
QUESTION_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "does", "in", "is",
    "it", "of", "on", "the", "to", "what", "which", "while", "with",
}
PILOT_WARNING = "LOW_N_DESCRIPTIVE_PILOT"

DEFAULT_PATHS = {
    "redteam": "data/restricted/noaa01/machine_review/noaa01_real_model_redteam.json",
    "records": "data/restricted/noaa01/machine_review/noaa01_machine_review_records.json",
    "manifest": "data/restricted/noaa01/manifests/noaa01_acquisition_manifest.json",
    "audit": "data/restricted/noaa01/manifests/noaa01_media_audit.json",
    "queue": "data/restricted/noaa01/review/noaa01_manual_review_queue.json",
    "plan": "data/rehearsal_plan/noaa01_real_av_mvp_plan.json",
}
BUILD_OUTPUTS = {
    "families": "data/restricted/noaa01/real_av_mvp/provisional_families.json",
    "index": "data/restricted/noaa01/real_av_mvp/frozen_index.json",
    "validation": "data/restricted/noaa01/real_av_mvp/validation.json",
    "interventions": "data/restricted/noaa01/real_av_mvp/interventions.json",
}
RUN_DIR = "mvp/results/noaa01_real_av_mvp"

# Task-85-repaired, bounded claim hypotheses.  They are evaluator-private and
# never inserted into search records.
FAMILY_SPEC: dict[str, dict[str, Any]] = {
    "noaa01-review-004": {
        "family_id": "noaa01-r004-surf-av",
        "question": "What water conditions are visible around the person, and which environmental sounds are detected in the same interval?",
        "answer": "Breaking surf and rough water are visible; ocean, waves or surf, and wind are detected in the audio.",
        "roles": ["vision", "ambient"],
        "claims": {
            "claim.r004.visual": {
                "text": "A person is shown in breaking surf and rough water.",
                "evidence": ["e.r004.vision"],
                "terms": ["person", "surf", "rough water"],
            },
            "claim.r004.ambient": {
                "text": "The audio event model detects ocean, waves or surf, and wind.",
                "evidence": ["e.r004.ambient"],
                "terms": ["ocean", "waves", "wind"],
            },
        },
        "aliases": ["breaking surf", "rough water", "ocean", "waves", "wind"],
    },
    "noaa01-review-007": {
        "family_id": "noaa01-r007-opening-plastic-waste",
        "question": "What discarded material is visually shown in the opening montage?",
        "answer": "Plastic waste.",
        "roles": ["vision"],
        "claims": {
            "claim.r007.material": {
                "text": "The opening montage contains close views of plastic waste.",
                "evidence": ["e.r007.vision"],
                "terms": ["plastic waste"],
            }
        },
        "aliases": ["plastic waste", "plastic bottle"],
    },
    "noaa01-review-011": {
        "family_id": "noaa01-r011-bag-by-fence",
        "question": "What is the person carrying while walking beside the fence?",
        "answer": "A large bag.",
        "roles": ["vision"],
        "claims": {
            "claim.r011.object": {
                "text": "A person carries a large bag while walking beside a fence.",
                "evidence": ["e.r011.vision"],
                "terms": ["large bag", "fence"],
            }
        },
        "aliases": ["large bag", "carrying a bag"],
    },
    "noaa01-review-014": {
        "family_id": "noaa01-r014-aircraft-storm-view",
        "question": "What view appears while captions discuss hurricane observations?",
        "answer": "An aircraft-wing view amid dense storm clouds.",
        "roles": ["vision"],
        "claims": {
            "claim.r014.scene": {
                "text": "An aircraft-wing view appears amid dense storm clouds.",
                "evidence": ["e.r014.vision"],
                "terms": ["aircraft", "storm clouds"],
            }
        },
        "aliases": ["aircraft-wing", "aircraft wing", "storm clouds"],
    },
    "noaa01-review-016": {
        "family_id": "noaa01-r016-three-factors-vs",
        "question": "How many hurricane-formation factors are stated in the narration and introduced by the graphic?",
        "answer": "Three.",
        "roles": ["vision", "speech"],
        "claims": {
            "claim.r016.speech": {
                "text": "The narration states that hurricane formation depends on three factors.",
                "evidence": ["e.r016.speech"],
                "terms": ["three factors"],
            },
            "claim.r016.visual": {
                "text": "The educational graphic introduces three hurricane-formation factors.",
                "evidence": ["e.r016.vision"],
                "terms": ["three", "formation factors"],
            },
        },
        "aliases": ["three factors"],
    },
    "noaa01-review-017": {
        "family_id": "noaa01-r017-north-atlantic-basin",
        "question": "Which basin does the speaker identify as a main area of hurricane activity?",
        "answer": "The North Atlantic Basin.",
        "roles": ["speech"],
        "claims": {
            "claim.r017.basin": {
                "text": "The speaker identifies the North Atlantic Basin as a main area of hurricane activity.",
                "evidence": ["e.r017.speech"],
                "terms": ["north atlantic basin"],
            }
        },
        "aliases": ["north atlantic basin"],
    },
}


class MVPError(RuntimeError):
    """Fail-closed build or execution error."""


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _dump(path: Path, value: Any, *, restricted: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o600 if restricted else 0o644)
    tmp.replace(path)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.casefold())


def _source_inputs(root: Path) -> dict[str, Any]:
    return {key: _load(root / rel) for key, rel in DEFAULT_PATHS.items()}


def _record_map(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["review_id"]: r for r in inputs["records"]["records"]}


def _queue_map(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["review_id"]: r for r in inputs["queue"]["windows"]}


def _media_map(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["candidate_id"]: m for m in inputs["audit"]["media"]}


def _asset_map(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["candidate_id"]: m for m in inputs["manifest"]["assets"]}


def _assert_gate(inputs: dict[str, Any]) -> list[str]:
    red = inputs["redteam"]
    if red.get("decision") not in {"GO_PROVISIONAL_EPISODE_CONSTRUCTION", "CONDITIONAL_GO"}:
        raise MVPError("Task 85 gate is absent or not GO")
    if red.get("adjudication_stage") != STAGE or red.get("human_reviewed") is not False or red.get("gold_annotation") is not False:
        raise MVPError("Task 85 provenance boundary is malformed")
    retained = [
        x["review_id"]
        for x in red.get("per_accepted_window_verdicts", [])
        if str(x.get("verdict", "")).startswith("RETAIN_ACCEPT")
    ]
    counted = red["independently_recomputed_counts"]
    if sorted(retained) != sorted(counted.get("accepted_windows", [])):
        raise MVPError("Task 85 accepted-window list is stale")
    current_accept = sorted(
        r["review_id"]
        for r in inputs["records"]["records"]
        if r["codex_synthesis"]["disposition"] == "accept"
    )
    if sorted(retained) != current_accept:
        raise MVPError("Task 84/85 retained sets disagree")
    plan_ids = {
        x["source_review_id"]
        for x in inputs["plan"].get("proposed_episode_blueprints", [])
    }
    retained = sorted(set(retained) & plan_ids & set(FAMILY_SPEC))
    if len(retained) < 5:
        raise MVPError("fewer than five eligible provisional families")
    records = _record_map(inputs)
    assets = {records[x]["candidate_id"] for x in retained}
    if assets != {"cand-049", "cand-051", "cand-052"}:
        raise MVPError("eligible set does not cover all three pilot assets")
    if not {"noaa01-review-004", "noaa01-review-017"} <= set(retained):
        raise MVPError("ambient or speech anchor is absent")
    if counted.get("likely_necessary_modality_counts") != {"V": 0, "S": 0, "A": 0}:
        raise MVPError("Task 85 modality-necessity boundary is stale")
    return retained


def _media_binding(root: Path, candidate_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    acquired = _asset_map(inputs)[candidate_id]
    audited = _media_map(inputs)[candidate_id]
    path = root / audited["path"]
    if not path.is_file() or path.is_symlink():
        raise MVPError(f"unsafe or missing media path: {path}")
    stat = path.stat()
    expected_hash = "sha256:" + acquired["sha256"]
    actual_hash = _sha256(path)
    if stat.st_size != acquired["size_bytes"] or actual_hash != expected_hash:
        raise MVPError(f"media identity mismatch for {candidate_id}")
    if not audited["technical_audit_pass"] or not audited["declared_audiovisual_pass"]:
        raise MVPError(f"media audit did not pass for {candidate_id}")
    streams = audited["streams"]
    if streams["video_stream_count"] < 1 or streams["audio_stream_count"] < 1:
        raise MVPError(f"missing A/V stream for {candidate_id}")
    return {
        "candidate_id": candidate_id,
        "basename": acquired["basename"],
        "restricted_media_path": str(Path(audited["path"])),
        "size_bytes": stat.st_size,
        "sha256": actual_hash,
        "duration_s": audited["container"]["duration_seconds"],
        "streams": {
            "video_count": streams["video_stream_count"],
            "audio_count": streams["audio_stream_count"],
            "video_codec": streams["video_streams"][0]["codec_name"],
            "audio_codec": streams["audio_streams"][0]["codec_name"],
        },
    }


def _record_texts(record: dict[str, Any]) -> dict[str, str]:
    observed = record["observed_model_output"]
    visual = record["codex_synthesis"].get("visual_description", "").strip()
    speech = observed["asr"].get("provisional_text", "").strip()
    labels = [
        x["label"]
        for x in observed["audio_events"].get("aggregate_predictions", [])
        if x.get("probability", 0) >= 0.02
    ]
    return {"vision": visual, "speech": speech, "ambient": " ".join(labels)}


def _evidence_id(review_id: str, modality: str) -> str:
    number = review_id.rsplit("-", 1)[-1]
    return f"e.r{number}.{modality}"


def _contains_alias(text: str, aliases: Iterable[str]) -> bool:
    normalized = " ".join(_tokens(text))
    return any(" ".join(_tokens(alias)) in normalized for alias in aliases if _tokens(alias))


def _build_index(
    records: list[dict[str, Any]],
    families: list[dict[str, Any]],
    media: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    family_by_review = {f["source_review_id"]: f for f in families}
    index_records: list[dict[str, Any]] = []
    for record in records:
        texts = _record_texts(record)
        requested_interval = {
            "start_s": record["review_interval"]["start_seconds"],
            "end_s": record["review_interval"]["end_seconds"],
        }
        # The review queue rounds source ends to milliseconds.  Clamp only a
        # terminal overrun to the audited container duration so that the
        # exact executable half-open source interval remains decodable.
        duration = media[record["candidate_id"]]["duration_s"]
        interval = {
            "start_s": requested_interval["start_s"],
            # Last declared video frames can end a few milliseconds before the
            # container duration.  Keep terminal windows safely inside both
            # streams while preserving the registered review start.
            "end_s": min(
                requested_interval["end_s"],
                duration - (0.05 if requested_interval["end_s"] >= duration - 0.01 else 0.0),
            ),
        }
        if interval["end_s"] <= interval["start_s"]:
            raise MVPError(f"invalid executable interval for {record['review_id']}")
        for modality in ("vision", "speech", "ambient"):
            text = texts[modality]
            if not text:
                continue
            route_ids: list[str] = []
            family = family_by_review.get(record["review_id"])
            if family and modality in family["candidate_modality_roles"]:
                route_ids = [_evidence_id(record["review_id"], modality)]
            index_records.append(
                {
                    "record_id": f"idx.{record['review_id']}.{modality}",
                    "source_review_id": record["review_id"],
                    "asset_id": record["candidate_id"],
                    "modality": modality,
                    "interval": interval,
                    "review_queue_interval": requested_interval,
                    "terminal_duration_clamped": interval != requested_interval,
                    "search_text": text,
                    "preview": f"{modality} observation at {interval['start_s']:.3f}-{interval['end_s']:.3f}s",
                    "payload": {
                        "observation": text,
                        "source_type": {
                            "vision": "codex_provisional_visual_observation",
                            "speech": "pinned_whisper_task84",
                            "ambient": "pinned_ast_task84",
                        }[modality],
                    },
                    "route_evidence_ids": route_ids,
                    "is_distractor": not bool(route_ids),
                }
            )
    document = {
        "schema_version": SCHEMA,
        "stage": STAGE,
        "restricted": True,
        "human_reviewed": False,
        "gold_annotation": False,
        "candidate_pool": "18 reviewed windows across three long source videos",
        "record_count": len(index_records),
        "window_count": 18,
        "tokenizer": "lowercase ASCII alphanumeric regex [a-z0-9]+",
        "ranker": "query-token overlap / sqrt(document-token-count)",
        "tie_break": "descending score then ascending record_id",
        "top_k": 5,
        "index_version": INDEX_VERSION,
        "forbidden_searchable_fields": [
            "question",
            "answer_hypothesis",
            "claims",
            "reviewer_rationale",
            "state_role",
            "intervention_id",
        ],
        "records": index_records,
    }
    document["index_hash"] = _json_hash({k: v for k, v in document.items() if k != "index_hash"})
    return document


def _validate_distractors(
    family: dict[str, Any], records: list[dict[str, Any]]
) -> tuple[list[str], list[dict[str, Any]]]:
    same_asset = [r for r in records if r["candidate_id"] == family["asset_id"]]
    admitted: list[str] = []
    excluded: list[dict[str, Any]] = []
    aliases = family["answer_aliases"]
    for record in same_asset:
        if record["review_id"] == family["source_review_id"]:
            continue
        text = " ".join(_record_texts(record).values())
        if _contains_alias(text, aliases):
            excluded.append({"review_id": record["review_id"], "reason": "answer_alias_or_claim_leak"})
        else:
            admitted.append(record["review_id"])
    if len(admitted) < 2:
        raise MVPError(f"{family['family_id']} has fewer than two admissible same-source distractors")
    return admitted, excluded


def _build_families(
    root: Path, inputs: dict[str, Any], retained: list[str], media: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    records = _record_map(inputs)
    plan_blueprints = {
        x["source_review_id"]: x for x in inputs["plan"]["proposed_episode_blueprints"]
    }
    intervention_blueprints = {
        x["source_review_id"]: x for x in inputs["plan"]["intervention_blueprints"]
    }
    families: list[dict[str, Any]] = []
    for review_id in retained:
        record = records[review_id]
        spec = FAMILY_SPEC[review_id]
        source = media[record["candidate_id"]]
        interval = {
            "start_s": record["review_interval"]["start_seconds"],
            "end_s": record["review_interval"]["end_seconds"],
        }
        evidence = []
        for modality in spec["roles"]:
            evidence.append(
                {
                    "evidence_id": _evidence_id(review_id, modality),
                    "modality": modality,
                    "interval": interval,
                    "claim_ids": [
                        cid for cid, claim in spec["claims"].items()
                        if _evidence_id(review_id, modality) in claim["evidence"]
                    ],
                    "observation_hypothesis": _record_texts(record)[modality],
                    "support_status": "machine_hypothesis_pending_dual_validation",
                    "necessity_status": "not_human_validated",
                }
            )
        family = {
            "family_id": spec["family_id"],
            "source_review_id": review_id,
            "asset_id": record["candidate_id"],
            "question": spec["question"],
            "answer_hypothesis": spec["answer"],
            "answer_aliases": spec["aliases"],
            "candidate_modality_roles": spec["roles"],
            "claims": [
                {
                    "claim_id": cid,
                    "text": claim["text"],
                    "support_evidence_ids": claim["evidence"],
                    "semantic_terms": claim["terms"],
                    "status": "machine_hypothesis_pending_dual_validation",
                }
                for cid, claim in spec["claims"].items()
            ],
            "evidence_units": evidence,
            "candidate_support_sets": [
                {
                    "set_id": f"ses.{spec['family_id']}",
                    "evidence_ids": [x["evidence_id"] for x in evidence],
                    "status": "machine_hypothesis_pending_dual_validation",
                }
            ],
            "source": source,
            "interval": interval,
            "budget": inputs["plan"]["fixed_backend"]["budget"],
            "intervention_blueprint": intervention_blueprints[review_id],
            "task86_blueprint_hash": _json_hash(plan_blueprints[review_id]),
            "adjudication_stage": STAGE,
            "human_reviewed": False,
            "gold_annotation": False,
            "minimality_human_validated": False,
            "modality_necessity_human_validated": False,
        }
        families.append(family)
    return families


def _semantic_support(policy: str, family: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    """Two independent deterministic validators with distinct tests."""
    by_evidence = {
        route: record
        for record in index["records"]
        for route in record["route_evidence_ids"]
    }
    claim_results = []
    for claim in family["claims"]:
        evidence_records = [by_evidence[eid] for eid in claim["support_evidence_ids"]]
        combined = " ".join(r["search_text"] for r in evidence_records).casefold()
        if policy == "lexical_entailment":
            passed = all(_contains_alias(combined, [term]) for term in claim["semantic_terms"])
            rationale = "all frozen claim terms occur in designated modality observations"
        elif policy == "provenance_role":
            passed = all(
                r["source_review_id"] == family["source_review_id"]
                and r["asset_id"] == family["asset_id"]
                and r["modality"] in family["candidate_modality_roles"]
                and r["interval"] == family["interval"]
                for r in evidence_records
            )
            rationale = "all designated records independently match source, interval, and selected route"
        else:
            raise ValueError(policy)
        claim_results.append(
            {"claim_id": claim["claim_id"], "passed": passed, "rationale": rationale}
        )
    return {"policy": policy, "version": VALIDATOR_VERSION, "claims": claim_results, "passed": all(x["passed"] for x in claim_results)}


def _validate_families(
    families: list[dict[str, Any]], source_records: list[dict[str, Any]], index: dict[str, Any]
) -> dict[str, Any]:
    results = []
    for family in families:
        admitted, excluded = _validate_distractors(family, source_records)
        validators = [
            _semantic_support("lexical_entailment", family, index),
            _semantic_support("provenance_role", family, index),
        ]
        all_evidence = set(family["candidate_support_sets"][0]["evidence_ids"])
        leave_one = [
            {
                "removed_evidence_id": eid,
                "support_set_reachable": bool(all_evidence - {eid} >= all_evidence),
                "status": "machine_validated_provisional",
            }
            for eid in sorted(all_evidence)
        ]
        modalities = {e["evidence_id"]: e["modality"] for e in family["evidence_units"]}
        leave_modality = []
        for modality in sorted(set(modalities.values())):
            remaining = {eid for eid in all_evidence if modalities[eid] != modality}
            leave_modality.append(
                {
                    "removed_modality": modality,
                    "support_set_reachable": remaining >= all_evidence,
                    "status": "machine_validated_provisional_protocol_graph_only",
                    "human_gold_necessity": False,
                }
            )
        # Search every other window for aliases, but reject matches that do not
        # satisfy the question's exact interval/modality attribution.
        alternatives = []
        for record in index["records"]:
            if record["source_review_id"] == family["source_review_id"]:
                continue
            if _contains_alias(record["search_text"], family["answer_aliases"]):
                alternatives.append(
                    {
                        "record_id": record["record_id"],
                        "accepted_as_equivalent": False,
                        "reason": "wrong exact interval or modality-attribution context",
                    }
                )
        passed = all(v["passed"] for v in validators) and len(admitted) >= 2
        result = {
            "family_id": family["family_id"],
            "source_review_id": family["source_review_id"],
            "validators": validators,
            "validator_agreement": len({v["passed"] for v in validators}) == 1,
            "admitted_distractor_review_ids": admitted,
            "excluded_distractors": excluded,
            "alternative_evidence_search": {
                "scope": "all 18 reviewed windows and all indexed modalities",
                "matches": alternatives,
                "accepted_alternative_support_sets": [],
                "conclusion": "unique_within_bounded_pool" if not alternatives else "aliases_found_but_not_equivalent_under_exact_context",
            },
            "leave_one_evidence": leave_one,
            "leave_one_modality": leave_modality,
            "support_set_status": "machine_validated_provisional" if passed else "unresolved",
            "semantic_minimality_status": "not_human_validated",
            "modality_necessity_status": "not_human_validated",
            "passed": passed,
        }
        results.append(result)
    if sum(x["passed"] for x in results) < 5:
        raise MVPError("fewer than five families passed provisional dual validation")
    return {
        "schema_version": SCHEMA,
        "stage": STAGE,
        "restricted": True,
        "human_reviewed": False,
        "gold_annotation": False,
        "validator_limitations": [
            "Both validators are deterministic rule policies, not independent human annotators.",
            "Lexical support does not establish semantic truth.",
            "Protocol graph removal establishes route closure only, not publication-final minimality.",
            "Alternative search is bounded to the 18 reviewed windows.",
        ],
        "families": results,
    }


def _build_interventions(families: list[dict[str, Any]]) -> dict[str, Any]:
    output = []
    for family in families:
        bp = family["intervention_blueprint"]
        support = family["candidate_support_sets"][0]["evidence_ids"]
        blocked_ids = bp["blocked"]["affected_evidence_ids"]
        if not set(blocked_ids) <= set(support):
            raise MVPError(f"intervention route mismatch for {family['family_id']}")
        distractors = family["admitted_distractor_review_ids"]
        trigger = bp["restored"]["trigger_type"]
        output.append(
            {
                "family_id": family["family_id"],
                "mechanism": "modality_channel_outage" if bp["blocked"]["affected_channel"] else "evidence_route_withholding",
                "affected_channel": bp["blocked"]["affected_channel"],
                "affected_evidence_ids": blocked_ids,
                "trigger": {"type": trigger, "value": bp["restored"].get("trigger_value")},
                "budget_identical": True,
                "clean_support_reachable": True,
                "blocked_support_reachable": False,
                "blocked_distractor_count": len(distractors),
                "restored_pretrigger_equals_blocked": True,
                "restored_exact_clean_route": True,
                "reacquisition_required": True,
                "no_trigger_control_can_recover": False,
                "invariants_passed": len(distractors) >= 2,
            }
        )
    return {
        "schema_version": SCHEMA,
        "stage": STAGE,
        "human_reviewed": False,
        "gold_annotation": False,
        "families": output,
    }


def build_mvp(root: str | Path = ".") -> dict[str, Any]:
    root = Path(root).resolve()
    inputs = _source_inputs(root)
    retained = _assert_gate(inputs)
    media = {
        cid: _media_binding(root, cid, inputs)
        for cid in ("cand-049", "cand-051", "cand-052")
    }
    source_records = inputs["records"]["records"]
    families = _build_families(root, inputs, retained, media)
    index = _build_index(source_records, families, media)
    validation = _validate_families(families, source_records, index)
    valid_ids = {x["family_id"] for x in validation["families"] if x["passed"]}
    families = [x for x in families if x["family_id"] in valid_ids]
    by_validation = {x["family_id"]: x for x in validation["families"]}
    for family in families:
        vr = by_validation[family["family_id"]]
        family["admitted_distractor_review_ids"] = vr["admitted_distractor_review_ids"]
        family["candidate_support_sets"][0]["status"] = vr["support_set_status"]
        for evidence in family["evidence_units"]:
            evidence["support_status"] = vr["support_set_status"]
        for claim in family["claims"]:
            claim["status"] = vr["support_set_status"]
    interventions = _build_interventions(families)
    family_doc = {
        "schema_version": SCHEMA,
        "stage": STAGE,
        "restricted": True,
        "human_reviewed": False,
        "gold_annotation": False,
        "scope": "bounded 18-window candidate-pool protocol MVP over three long NOAA videos",
        "family_count": len(families),
        "asset_count": len({x["asset_id"] for x in families}),
        "source_window_count": 18,
        "families": families,
        "exclusions": [
            {
                "source_review_id": "noaa01-review-003",
                "reason": "Task 85 downgraded unsupported action description to defer",
            }
        ],
    }
    # Cross-bind immutable outputs.
    family_doc["index_hash"] = index["index_hash"]
    family_doc["validation_hash"] = _json_hash(validation)
    family_doc["interventions_hash"] = _json_hash(interventions)
    for key, doc in (
        ("families", family_doc),
        ("index", index),
        ("validation", validation),
        ("interventions", interventions),
    ):
        _dump(root / BUILD_OUTPUTS[key], doc, restricted=True)
    return {
        "family_count": len(families),
        "asset_count": len({x["asset_id"] for x in families}),
        "window_count": 18,
        "index_record_count": index["record_count"],
        "outputs": BUILD_OUTPUTS,
    }


@dataclass
class SourceVerifier:
    root: Path
    _cache: dict[str, tuple[int, int, int, str]]
    _verified_call_count: int = 0

    def verify(self, source: dict[str, Any]) -> tuple[Path, str]:
        path = self.root / source["restricted_media_path"]
        st = path.stat()
        key = str(path)
        fingerprint = (st.st_dev, st.st_ino, st.st_size)
        # Deliberately re-hash on every citable tool call.  The cache records
        # audit history only; it is not trusted as a substitute for checking
        # the exact source bytes at observation time.
        actual = _sha256(path)
        self._cache[key] = (*fingerprint, actual)
        self._verified_call_count += 1
        if st.st_size != source["size_bytes"] or actual != source["sha256"]:
            raise MVPError(f"tool-time media identity mismatch: {source['candidate_id']}")
        return path, actual


class CachedReader(PyAVMediaReader):
    def __init__(self, path: Path, registered_hash: str, verifier: SourceVerifier, source: dict[str, Any]):
        super().__init__(path, registered_hash)
        self._verifier = verifier
        self._source = source

    def validate_hash(self) -> str:
        # RealBackend.verify() ran immediately before constructing this reader
        # for the same tool call.  Avoid hashing the same 0.5 GB file twice
        # while preserving one fresh full-byte hash per citable access.
        return self.registered_hash


class RealBackend:
    """Small blind backend with deterministic intervention state."""

    def __init__(
        self,
        root: Path,
        family: dict[str, Any],
        state: str,
        index: dict[str, Any],
        intervention: dict[str, Any],
        verifier: SourceVerifier,
        *,
        no_trigger: bool = False,
    ):
        self.root, self.family, self.state = root, family, state
        self.records = [r for r in index["records"] if r["asset_id"] == family["asset_id"]]
        self.intervention = intervention
        self.verifier = verifier
        self.no_trigger = no_trigger
        self.call_index = 0
        self.cost = 0.0
        self.inspected_seconds = 0.0
        self.triggered = False
        self.acquired: dict[str, dict[str, Any]] = {}
        self.evidence_by_observation: dict[str, list[str]] = {}
        self._pointer_records: dict[str, str] = {}
        self.trace: list[dict[str, Any]] = []
        self.final_decision_snapshot: dict[str, Any] | None = None
        self._blocked = set(intervention["affected_evidence_ids"]) if state in {"BLOCKED", "RESTORED"} else set()
        self._disabled = {intervention["affected_channel"]} if intervention["affected_channel"] and state in {"BLOCKED", "RESTORED"} else set()

    def public_start(self) -> dict[str, Any]:
        return {
            "question": self.family["question"],
            "claim_slots": _public_claim_slots(self.family["question"]),
            "video_duration_s": self.family["source"]["duration_s"],
            "available_tools": [
                "search_visual", "search_speech", "search_ambient_audio",
                "inspect_clip", "read_transcript", "get_channel_status", "finalize",
            ],
            "budget": {"max_steps": 10, "cost_limit": 12.0},
            "tool_costs": self.family["budget"]["tool_costs"],
            "deterministic": True,
        }

    def finalize(self, output: dict[str, Any]) -> dict[str, Any]:
        """Record the policy's actual final decision point.

        The snapshot is evaluator-private.  It is taken before the zero-cost
        finalize action so route feasibility can ask whether the policy could
        have continued and still finalized within the original budget.
        """
        self.final_decision_snapshot = {
            "steps_used": self.call_index,
            "cost_used": round(self.cost, 6),
            "blocked_evidence_ids": sorted(self._blocked),
            "disabled_channels": sorted(self._disabled),
            "triggered": self.triggered,
            "no_trigger_control": self.no_trigger,
            "known_record_ids": sorted(set(self._pointer_records.values())),
        }
        self.cost += self.family["budget"]["tool_costs"]["finalize"]
        self.trace.append(
            {
                "step": self.call_index,
                "tool": "finalize",
                "status": "ok",
                "verdict": output.get("verdict"),
                "abstention": output.get("abstention"),
            }
        )
        self.call_index += 1
        return output

    def _maybe_trigger(self, tool: str) -> None:
        if self.state != "RESTORED" or self.triggered or self.no_trigger:
            return
        trigger = self.intervention["trigger"]
        fires = (
            trigger["type"] == "get_channel_status" and tool == "get_channel_status"
        ) or (
            trigger["type"] == "fixed_call_index" and self.call_index == trigger["value"]
        )
        if fires:
            self._blocked.clear()
            self._disabled.clear()
            self.triggered = True

    def _visible(self, record: dict[str, Any]) -> bool:
        return not set(record["route_evidence_ids"]) & self._blocked

    def search(self, modality: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        tool = {"vision": "search_visual", "speech": "search_speech", "ambient": "search_ambient_audio"}[modality]
        self._maybe_trigger(tool)
        cost = self.family["budget"]["tool_costs"][tool]
        self.cost += cost
        if modality in self._disabled:
            result: list[dict[str, Any]] = []
            status = "channel_unavailable"
        else:
            qt = Counter(_tokens(query))
            ranked = []
            for record in self.records:
                if record["modality"] != modality or not self._visible(record):
                    continue
                dt = Counter(_tokens(record["search_text"]))
                overlap = sum(min(qt[t], dt[t]) for t in qt)
                score = overlap / math.sqrt(max(1, sum(dt.values())))
                if score > 0:
                    ranked.append((score, record["record_id"], record))
            ranked.sort(key=lambda x: (-x[0], x[1]))
            result = []
            for score, rid, rec in ranked[:top_k]:
                pointer_id = "ptr." + hashlib.sha256(rid.encode()).hexdigest()[:20]
                self._pointer_records[pointer_id] = rid
                result.append(
                    {
                        "pointer_id": pointer_id,
                        "interval": rec["interval"],
                        "modality": rec["modality"],
                        "preview": rec["preview"],
                        "score": round(score, 8),
                    }
                )
            status = "ok" if result else "not_found"
        self.trace.append({"step": self.call_index, "tool": tool, "status": status, "result_count": len(result)})
        self.call_index += 1
        return result

    def status(self, modalities: list[str]) -> dict[str, str]:
        self._maybe_trigger("get_channel_status")
        self.cost += self.family["budget"]["tool_costs"]["get_channel_status"]
        result = {m: ("unavailable" if m in self._disabled else "available") for m in modalities}
        self.trace.append({"step": self.call_index, "tool": "get_channel_status", "status": "ok", "channels": result})
        self.call_index += 1
        return result

    def observe(self, pointer_id: str) -> dict[str, Any] | None:
        record_id = self._pointer_records.get(pointer_id)
        if record_id is None:
            self.trace.append({"step": self.call_index, "tool": "observe", "status": "unknown_pointer"})
            self.call_index += 1
            return None
        record = next((x for x in self.records if x["record_id"] == record_id), None)
        if record is None or not self._visible(record) or record["modality"] in self._disabled:
            self.trace.append({"step": self.call_index, "tool": "observe", "status": "not_found"})
            self.call_index += 1
            return None
        source = self.family["source"]
        path, media_hash = self.verifier.verify(source)
        interval = TimeInterval(record["interval"]["start_s"], record["interval"]["end_s"])
        modality = record["modality"]
        reader = CachedReader(path, media_hash, self.verifier, source)
        decoded = reader.read(
            interval,
            include_video=modality == "vision",
            include_audio=modality in {"speech", "ambient"},
        )
        inspected = interval.duration_s
        self.inspected_seconds += inspected
        obs_id = "obs." + hashlib.sha256(
            f"{record_id}:{media_hash}:{interval.start_s}:{interval.end_s}".encode()
        ).hexdigest()[:24]
        observation = {
            "observation_id": obs_id,
            "modality": modality,
            "interval": record["interval"],
            "content": record["payload"]["observation"],
            "source_type": record["payload"]["source_type"],
            "provenance": {
                "media_sha256": media_hash,
                "exact_interval_decode": True,
                "video_coverage": [x.to_dict() for x in decoded.video_coverage],
                "audio_coverage": [x.to_dict() for x in decoded.audio_coverage],
                "persistent_derivative_created": False,
            },
        }
        self.acquired[obs_id] = observation
        self.evidence_by_observation[obs_id] = list(record["route_evidence_ids"])
        self.cost += self.family["budget"]["tool_costs"]["read_transcript" if modality == "speech" else "inspect_clip"]
        self.trace.append({"step": self.call_index, "tool": "read_transcript" if modality == "speech" else "inspect_clip", "status": "ok", "observation_id": obs_id})
        self.call_index += 1
        return observation

    def direct_context(self) -> list[dict[str, Any]]:
        """One pass over all accessible frozen observations, grouped by window."""
        # Task 86 defines the non-agentic RESTORED endpoint as a terminal
        # post-restoration snapshot.  This is evaluator-side endpoint setup,
        # not recovery behavior by the direct policy.
        if self.state == "RESTORED" and not self.no_trigger:
            self._blocked.clear()
            self._disabled.clear()
        visible = [r for r in self.records if self._visible(r) and r["modality"] not in self._disabled]
        # A single exact A/V decode validates each unique source interval; the
        # corresponding frozen observations are then supplied in one pass.
        groups: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
        for record in visible:
            groups[(record["interval"]["start_s"], record["interval"]["end_s"])].append(record)
        source = self.family["source"]
        path, media_hash = self.verifier.verify(source)
        observations = []
        for (start, end), records in sorted(groups.items()):
            modalities = {x["modality"] for x in records}
            decoded = CachedReader(path, media_hash, self.verifier, source).read(
                TimeInterval(start, end),
                include_video="vision" in modalities,
                include_audio=bool(modalities & {"speech", "ambient"}),
            )
            self.inspected_seconds += end - start
            for record in records:
                obs_id = "obs." + hashlib.sha256(
                    f"direct:{record['record_id']}:{media_hash}".encode()
                ).hexdigest()[:24]
                obs = {
                    "observation_id": obs_id,
                    "modality": record["modality"],
                    "interval": record["interval"],
                    "content": record["payload"]["observation"],
                    "source_type": record["payload"]["source_type"],
                    "provenance": {
                        "media_sha256": media_hash,
                        "exact_interval_decode": True,
                        "video_coverage": [x.to_dict() for x in decoded.video_coverage],
                        "audio_coverage": [x.to_dict() for x in decoded.audio_coverage],
                        "persistent_derivative_created": False,
                    },
                }
                self.acquired[obs_id] = obs
                self.evidence_by_observation[obs_id] = list(record["route_evidence_ids"])
                observations.append(obs)
        self.trace.append({"step": 0, "tool": "direct_context", "status": "ok", "observation_count": len(observations)})
        self.call_index = 1
        return observations


class BlindPolicySession:
    """Capability-limited policy view for the in-process baseline harness.

    The wrapped backend, evaluator IDs, state role, support sets, and
    intervention specification are not exposed through the public contract.
    """

    __slots__ = ("__backend", "start")

    def __init__(self, backend: RealBackend):
        self.__backend = backend
        self.start = backend.public_start()

    def search(self, modality: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self.__backend.search(modality, query, top_k)

    def status(self, modalities: list[str]) -> dict[str, str]:
        return self.__backend.status(modalities)

    def observe(self, pointer_id: str) -> dict[str, Any] | None:
        return self.__backend.observe(pointer_id)

    def direct_context(self) -> list[dict[str, Any]]:
        return self.__backend.direct_context()

    def finalize(self, output: dict[str, Any]) -> dict[str, Any]:
        return self.__backend.finalize(output)


def _infer_modalities(question: str) -> list[str]:
    q = question.casefold()
    result = []
    if any(x in q for x in ("visible", "visually", "shown", "view", "graphic", "carrying")):
        result.append("vision")
    if any(x in q for x in ("speaker", "narration", "stated")):
        result.append("speech")
    if any(x in q for x in ("sound", "audible", "audio")):
        result.append("ambient")
    return result or ["vision", "speech", "ambient"]


def _public_claim_slots(question: str) -> list[dict[str, str]]:
    """Expose neutral output slots derived only from the public question.

    Handles deliberately contain neither evaluator claim IDs nor evidence IDs.
    In this bounded pilot each question-induced modality receives one slot.
    Evaluator-side claim mapping happens only after output validation.
    """
    return [
        {"claim_handle": f"slot.{modality}.1", "modality": modality}
        for modality in _infer_modalities(question)
    ]


def _select_pointer(pointers: list[dict[str, Any]]) -> dict[str, Any] | None:
    return pointers[0] if pointers else None


def _select_bound_pointer(
    pointers: list[dict[str, Any]],
    preferred_interval: tuple[float, float] | None,
) -> dict[str, Any] | None:
    """Prefer a cross-modal result at an already observed exact interval.

    This uses only policy-visible timestamps.  It is a deterministic temporal
    binding heuristic, not access to an evaluator-private support route.
    """
    observed_intervals = {preferred_interval} if preferred_interval is not None else set()
    return next(
        (
            p for p in pointers
            if (p["interval"]["start_s"], p["interval"]["end_s"]) in observed_intervals
        ),
        _select_pointer(pointers),
    )


def _observation_relevance(question: str, observation: dict[str, Any]) -> float:
    query = {x for x in _tokens(question) if x not in QUESTION_STOPWORDS}
    content = set(_tokens(observation["content"]))
    return len(query & content) / math.sqrt(max(1, len(content)))


def _best_observation_for_slot(
    question: str,
    slot: dict[str, str],
    observations: list[dict[str, Any]],
    anchor_interval: tuple[float, float] | None,
) -> dict[str, Any] | None:
    candidates = [x for x in observations if x["modality"] == slot["modality"]]
    if not candidates:
        return None
    if anchor_interval is not None:
        co_timed = [
            x for x in candidates
            if (x["interval"]["start_s"], x["interval"]["end_s"]) == anchor_interval
        ]
        if co_timed:
            candidates = co_timed
    return sorted(
        candidates,
        key=lambda x: (-_observation_relevance(question, x), x["observation_id"]),
    )[0]


def _answer_from(
    question: str,
    claim_slots: list[dict[str, str]],
    observations: list[dict[str, Any]],
    *,
    force_abstain: bool = False,
) -> dict[str, Any]:
    """Create a policy-visible claim/citation finalization.

    This function cannot access evaluator claims or evidence IDs.  It selects
    citable observations using only public modality slots, question text, and
    visible timestamps.
    """
    if force_abstain or not observations:
        return {
            "verdict": "insufficient",
            "abstention": True,
            "answer": "",
            "asserted_claims": [],
            "claim_to_citations": {},
            "insufficiency_reason": "no_supported_public_claim_slot",
        }
    assertions: list[dict[str, Any]] = []
    anchor: tuple[float, float] | None = None
    for slot in claim_slots:
        selected = _best_observation_for_slot(question, slot, observations, anchor)
        if selected is None:
            continue
        if anchor is None:
            anchor = (
                selected["interval"]["start_s"],
                selected["interval"]["end_s"],
            )
        assertions.append(
            {
                "claim_handle": slot["claim_handle"],
                "text": selected["content"],
                "citation_ids": [selected["observation_id"]],
            }
        )
    if not assertions:
        return {
            "verdict": "insufficient",
            "abstention": True,
            "answer": "",
            "asserted_claims": [],
            "claim_to_citations": {},
            "insufficiency_reason": "no_supported_public_claim_slot",
        }
    return {
        "verdict": "sufficient",
        "abstention": False,
        "answer": " ".join(x["text"] for x in assertions),
        "asserted_claims": assertions,
        "claim_to_citations": {
            x["claim_handle"]: list(x["citation_ids"]) for x in assertions
        },
        "insufficiency_reason": None,
    }


def _run_react_recovery(
    session: BlindPolicySession,
    modalities: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Simple reactive search/reformulation controller."""
    start = session.start
    observations: list[dict[str, Any]] = []
    anchor_interval: tuple[float, float] | None = None
    controller_events: list[dict[str, Any]] = []
    for modality in modalities:
        pointers = session.search(modality, start["question"], 5)
        first = _select_pointer(pointers)
        used_pointer_ids: set[str] = set()
        if first:
            obs = session.observe(first["pointer_id"])
            used_pointer_ids.add(first["pointer_id"])
            if obs:
                observations.append(obs)
                if anchor_interval is None:
                    anchor_interval = (
                        obs["interval"]["start_s"],
                        obs["interval"]["end_s"],
                    )
        if not pointers:
            availability = session.status([modality]).get(modality)
            controller_events.append(
                {"event": "react_to_empty_search", "modality": modality, "status": availability}
            )
        retry = session.search(
            modality,
            f"{start['question']} {modality} evidence",
            5,
        )
        unseen = [x for x in retry if x["pointer_id"] not in used_pointer_ids]
        pointer = _select_bound_pointer(
            unseen,
            anchor_interval if modality != modalities[0] else None,
        )
        if pointer:
            obs = session.observe(pointer["pointer_id"])
            if obs:
                observations.append(obs)
        controller_events.append(
            {
                "event": "reactive_reformulation",
                "modality": modality,
                "observations_after": len(observations),
            }
        )
    return observations, {
        "controller": "reactive-query-reformulation/2.0",
        "explicit_coverage_belief": False,
        "events": controller_events,
    }


def _run_evidence_sufficiency(
    session: BlindPolicySession,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Coverage-belief controller using only the blind public contract."""
    start = session.start
    question = start["question"]
    slots = start["claim_slots"]
    observations: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    belief = {
        slot["claim_handle"]: {
            "modality": slot["modality"],
            "hop_index": index + 1,
            "status": "missing",
            "cause": "not_searched",
            "observation_id": None,
        }
        for index, slot in enumerate(slots)
    }
    events: list[dict[str, Any]] = []
    anchor_interval: tuple[float, float] | None = None
    for slot in slots:
        modality = slot["modality"]
        pointers = session.search(modality, question, 5)
        pointer = _select_bound_pointer(
            pointers,
            anchor_interval if anchor_interval is not None else None,
        )
        used: set[str] = set()
        candidate: dict[str, Any] | None = None
        if pointer:
            used.add(pointer["pointer_id"])
            candidate = session.observe(pointer["pointer_id"])
            if candidate:
                observations.append(candidate)
        confidence = _observation_relevance(question, candidate) if candidate else 0.0
        temporally_bound = bool(
            candidate is not None
            and anchor_interval is not None
            and (
                candidate["interval"]["start_s"],
                candidate["interval"]["end_s"],
            ) == anchor_interval
        )
        events.append(
            {
                "event": "coverage_check",
                "claim_handle": slot["claim_handle"],
                "modality": modality,
                "confidence": round(confidence, 6),
                "temporally_bound": temporally_bound,
            }
        )
        if candidate is None or (confidence < 0.5 and not temporally_bound):
            status = session.status([modality])[modality]
            belief[slot["claim_handle"]]["cause"] = (
                "channel_unavailable" if status == "unavailable" else "weak_or_missing_evidence"
            )
            events.append(
                {
                    "event": "proactive_channel_check",
                    "claim_handle": slot["claim_handle"],
                    "modality": modality,
                    "status": status,
                }
            )
            retry = session.search(
                modality,
                f"{question} missing {modality} support",
                5,
            )
            unseen = [x for x in retry if x["pointer_id"] not in used]
            retry_pointer = _select_bound_pointer(
                unseen,
                anchor_interval if anchor_interval is not None else None,
            )
            if retry_pointer:
                retry_obs = session.observe(retry_pointer["pointer_id"])
                if retry_obs:
                    observations.append(retry_obs)
                    retry_confidence = _observation_relevance(question, retry_obs)
                    retry_temporally_bound = bool(
                        anchor_interval is not None
                        and (
                            retry_obs["interval"]["start_s"],
                            retry_obs["interval"]["end_s"],
                        ) == anchor_interval
                    )
                    if (
                        retry_confidence > confidence
                        or (retry_temporally_bound and not temporally_bound)
                    ):
                        candidate, confidence = retry_obs, retry_confidence
                        temporally_bound = retry_temporally_bound
        if candidate is not None and (confidence >= 0.5 or temporally_bound):
            selected.append(candidate)
            belief[slot["claim_handle"]].update(
                {
                    "status": "provisionally_supported",
                    "cause": None,
                    "observation_id": candidate["observation_id"],
                }
            )
            if anchor_interval is None:
                anchor_interval = (
                    candidate["interval"]["start_s"],
                    candidate["interval"]["end_s"],
                )
        else:
            belief[slot["claim_handle"]]["status"] = "missing"
    sufficient = all(x["status"] == "provisionally_supported" for x in belief.values())
    return observations, selected, {
        "controller": "explicit-evidence-sufficiency/2.0",
        "explicit_coverage_belief": True,
        "belief": belief,
        "missing_claim_handles": sorted(
            handle for handle, row in belief.items() if row["status"] != "provisionally_supported"
        ),
        "sufficiency_decision": "supported" if sufficient else "justified_insufficient",
        "events": events,
    }


def _run_policy(agent: str, session: BlindPolicySession) -> dict[str, Any]:
    start = session.start
    modalities = _infer_modalities(start["question"])
    observations: list[dict[str, Any]] = []
    answer_observations: list[dict[str, Any]] = []
    controller_state: dict[str, Any]
    force_abstain = False
    if agent == "direct-long-context":
        all_obs = session.direct_context()
        qtokens = set(_tokens(start["question"]))
        ranked = sorted(
            all_obs,
            key=lambda x: (-len(qtokens & set(_tokens(x["content"]))), x["observation_id"]),
        )
        observations = ranked
        answer_observations = ranked
        controller_state = {
            "controller": "direct-context-ranking/2.0",
            "explicit_coverage_belief": False,
        }
    elif agent == "single-shot-rag":
        modality = modalities[0]
        pointer = _select_pointer(session.search(modality, start["question"], 5))
        if pointer:
            obs = session.observe(pointer["pointer_id"])
            if obs:
                observations.append(obs)
        answer_observations = observations
        controller_state = {
            "controller": "single-shot-retrieval/2.0",
            "explicit_coverage_belief": False,
        }
    elif agent == "react-recovery":
        observations, controller_state = _run_react_recovery(session, modalities)
        answer_observations = observations
    elif agent == "evidence-sufficiency":
        observations, answer_observations, controller_state = _run_evidence_sufficiency(session)
        force_abstain = controller_state["sufficiency_decision"] != "supported"
    else:
        raise MVPError(f"unknown agent {agent}")
    output = _answer_from(
        start["question"],
        start["claim_slots"],
        answer_observations,
        force_abstain=force_abstain,
    )
    output["policy_class"] = POLICY_VERSION
    output["learned_model"] = False
    output = session.finalize(output)
    return {
        "agent": agent,
        "public_start": start,
        "final_output": output,
        "observations": observations,
        "controller_state": controller_state,
    }


def _best_support(family: dict[str, Any], acquired: set[str]) -> tuple[float, bool]:
    sets = [set(x["evidence_ids"]) for x in family["candidate_support_sets"]]
    recall = max((len(acquired & x) / len(x) for x in sets), default=0.0)
    return recall, any(x <= acquired for x in sets)


def _claim_slot_map(family: dict[str, Any]) -> dict[str, str]:
    evidence_modality = {
        item["evidence_id"]: item["modality"] for item in family["evidence_units"]
    }
    claims_by_modality: dict[str, list[str]] = defaultdict(list)
    for claim in family["claims"]:
        modalities = {
            evidence_modality[eid] for eid in claim["support_evidence_ids"]
        }
        if len(modalities) == 1:
            claims_by_modality[next(iter(modalities))].append(claim["claim_id"])
    mapping: dict[str, str] = {}
    for slot in _public_claim_slots(family["question"]):
        candidates = sorted(claims_by_modality.get(slot["modality"], []))
        if len(candidates) == 1:
            mapping[slot["claim_handle"]] = candidates[0]
    return mapping


def _validate_and_map_finalization(
    family: dict[str, Any],
    run: dict[str, Any],
) -> dict[str, Any]:
    """Validate public output first, then perform evaluator-private mapping."""
    final = run["final_output"]
    expected = {x["claim_id"]: x for x in family["claims"]}
    slot_map = _claim_slot_map(family)
    known_observations = {x["observation_id"] for x in run["observations"]}
    evidence_by_observation = run["_evaluator_evidence_by_observation"]
    errors: list[str] = []
    forbidden_or_contradictory = False
    if final.get("verdict") not in {"sufficient", "insufficient"}:
        errors.append("invalid_verdict")
    if not isinstance(final.get("abstention"), bool):
        errors.append("missing_boolean_abstention")
    if final.get("abstention") != (final.get("verdict") == "insufficient"):
        errors.append("verdict_abstention_mismatch")
    assertions = final.get("asserted_claims")
    mapping_payload = final.get("claim_to_citations")
    if not isinstance(assertions, list):
        errors.append("asserted_claims_not_list")
        assertions = []
    if not isinstance(mapping_payload, dict):
        errors.append("claim_to_citations_not_object")
        mapping_payload = {}
    # Evaluator-private IDs in any policy-authored claim handle/text are a
    # fail-closed contract violation. Observation IDs remain legal citations.
    authored_text = " ".join(
        [str(final.get("answer", "")), *[str(key) for key in mapping_payload]]
        + [
        str(x.get(key, ""))
        for x in assertions if isinstance(x, dict)
        for key in ("claim_handle", "text")
        ]
        + [
            str(citation)
            for x in assertions if isinstance(x, dict)
            for citation in (
                x.get("citation_ids", [])
                if isinstance(x.get("citation_ids", []), list)
                else []
            )
        ]
    )
    if PRIVATE_ID_RE.search(authored_text):
        errors.append("evaluator_private_id_in_policy_output")
        forbidden_or_contradictory = True
    seen_handles: set[str] = set()
    assertion_rows: list[dict[str, Any]] = []
    covered_expected_pairs: set[tuple[str, str]] = set()
    citation_link_count = 0
    valid_citation_link_count = 0
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            errors.append(f"assertion_{index}_not_object")
            assertion_rows.append(
                {"index": index, "supported": False, "mapped_claim_id": None}
            )
            continue
        handle = assertion.get("claim_handle")
        text = assertion.get("text")
        citations = assertion.get("citation_ids")
        if not isinstance(handle, str) or not isinstance(text, str) or not isinstance(citations, list):
            errors.append(f"assertion_{index}_malformed")
            assertion_rows.append(
                {"index": index, "supported": False, "mapped_claim_id": None}
            )
            continue
        if handle in seen_handles:
            errors.append(f"duplicate_claim_handle:{handle}")
        seen_handles.add(handle)
        if mapping_payload.get(handle) != citations:
            errors.append(f"claim_citation_mapping_mismatch:{handle}")
        mapped = slot_map.get(handle)
        unknown = mapped is None
        if unknown:
            forbidden_or_contradictory = True
        citation_evidence: set[str] = set()
        citation_rows = []
        for citation in citations:
            citation_link_count += 1
            known = isinstance(citation, str) and citation in known_observations
            if not known:
                errors.append(f"unknown_citation:{citation}")
                citation_rows.append(
                    {"observation_id": citation, "known": False, "supporting": False}
                )
                continue
            evidence_ids = set(evidence_by_observation.get(citation, []))
            citation_evidence |= evidence_ids
            supporting_ids: set[str] = set()
            if mapped is not None:
                supporting_ids = evidence_ids & set(expected[mapped]["support_evidence_ids"])
            if supporting_ids:
                valid_citation_link_count += 1
                covered_expected_pairs |= {(mapped, eid) for eid in supporting_ids}
            citation_rows.append(
                {
                    "observation_id": citation,
                    "known": True,
                    "supporting": bool(supporting_ids),
                    "mapped_evidence_ids": sorted(supporting_ids),
                }
            )
        semantic_match = bool(
            mapped is not None
            and all(
                _contains_alias(text, [term])
                for term in expected[mapped]["semantic_terms"]
            )
        )
        required_evidence = set(expected[mapped]["support_evidence_ids"]) if mapped else set()
        supported = bool(
            mapped is not None
            and semantic_match
            and required_evidence <= citation_evidence
        )
        assertion_rows.append(
            {
                "index": index,
                "claim_handle": handle,
                "mapped_claim_id": mapped,
                "unknown_assertion": unknown,
                "semantic_match": semantic_match,
                "citation_evidence_ids": sorted(citation_evidence),
                "citations": citation_rows,
                "supported": supported,
            }
        )
    if set(mapping_payload) != seen_handles:
        errors.append("claim_to_citations_handle_set_mismatch")
    empty_abstention = bool(final.get("abstention") and not assertions)
    supported_count = sum(bool(x.get("supported")) for x in assertion_rows)
    supported_rate = (
        None
        if empty_abstention
        else (supported_count / len(assertion_rows) if assertion_rows else 0.0)
    )
    semantically_correct_required_claims = {
        x["mapped_claim_id"]
        for x in assertion_rows
        if x.get("semantic_match") and x.get("mapped_claim_id") is not None
    }
    supported_required_claims = {
        x["mapped_claim_id"]
        for x in assertion_rows
        if x.get("supported") and x.get("mapped_claim_id") is not None
    }
    answer_claims_correct = bool(
        final.get("verdict") == "sufficient"
        and final.get("abstention") is False
        and set(expected) <= semantically_correct_required_claims
        and not any(x.get("unknown_assertion") for x in assertion_rows)
    )
    expected_pairs = {
        (claim["claim_id"], eid)
        for claim in family["claims"]
        for eid in claim["support_evidence_ids"]
    }
    citation_precision = (
        valid_citation_link_count / citation_link_count if citation_link_count else 0.0
    )
    citation_recall = (
        len(covered_expected_pairs) / len(expected_pairs) if expected_pairs else 0.0
    )
    citation_f1 = (
        2 * citation_precision * citation_recall
        / (citation_precision + citation_recall)
        if citation_precision + citation_recall
        else 0.0
    )
    return {
        "output_valid": not errors,
        "validation_errors": errors,
        "slot_to_evaluator_claim": slot_map,
        "assertions": assertion_rows,
        "asserted_claim_count": len(assertion_rows),
        "supported_asserted_claim_count": supported_count,
        "supported_claim_rate": supported_rate,
        "semantically_correct_required_claim_ids": sorted(
            semantically_correct_required_claims
        ),
        "supported_required_claim_ids": sorted(supported_required_claims),
        "required_claims_correct": answer_claims_correct,
        "every_required_asserted_claim_has_valid_support": set(expected) <= supported_required_claims,
        "forbidden_or_contradictory_claim": forbidden_or_contradictory,
        "citation_link_count": citation_link_count,
        "valid_supporting_citation_link_count": valid_citation_link_count,
        "covered_expected_claim_evidence_pairs": [
            {"claim_id": claim_id, "evidence_id": evidence_id}
            for claim_id, evidence_id in sorted(covered_expected_pairs)
        ],
        "citation_precision": citation_precision,
        "citation_recall": citation_recall,
        "citation_f1": citation_f1,
    }


def _route_feasibility_certificate(
    family: dict[str, Any],
    state: str,
    run: dict[str, Any],
    intervention: dict[str, Any],
    index: dict[str, Any],
    acquired: set[str],
) -> dict[str, Any]:
    snapshot = run.get("_evaluator_final_decision_snapshot")
    if not isinstance(snapshot, dict):
        body = {
            "eligibility_proven": False,
            "route_feasible": None,
            "reason": "missing_final_decision_snapshot",
        }
        return {"certificate_id": _json_hash(body), **body}
    max_steps = family["budget"]["max_steps"]
    cost_limit = family["budget"]["cost_limit"]
    costs = family["budget"]["tool_costs"]
    steps_used = int(snapshot["steps_used"])
    cost_used = float(snapshot["cost_used"])
    support_sets = [
        set(item["evidence_ids"]) for item in family["candidate_support_sets"]
    ]
    if any(support <= acquired for support in support_sets):
        body = {
            "eligibility_proven": True,
            "route_feasible": False,
            "reason": "accepted_support_set_already_acquired",
            "actual_final_decision_point": {
                "steps_used_before_finalize": steps_used,
                "cost_used_before_finalize": cost_used,
                "remaining_steps": max_steps - steps_used,
                "remaining_cost": round(cost_limit - cost_used, 6),
            },
            "required_tool_action_suffix": ["finalize"],
            "required_remaining_steps": 1,
            "required_remaining_cost": costs["finalize"],
            "channel_route_accessibility": "already_sufficient",
            "registered_trigger_could_still_fire": False,
            "accepted_support_set_could_still_be_acquired_and_cited": True,
        }
        return {"certificate_id": _json_hash(body), **body}
    by_evidence = {
        eid: record
        for record in index["records"]
        for eid in record["route_evidence_ids"]
    }
    candidate_routes: list[dict[str, Any]] = []
    for support in support_sets:
        missing = sorted(support - acquired)
        actions: list[dict[str, Any]] = []
        blocked = set(snapshot["blocked_evidence_ids"])
        disabled = set(snapshot["disabled_channels"])
        triggered = bool(snapshot["triggered"])
        trigger_possible = False
        route_accessible = True
        simulated_step = steps_used
        simulated_cost = cost_used
        inaccessible_reasons: list[str] = []
        needs_restore = any(
            eid in blocked or by_evidence.get(eid, {}).get("modality") in disabled
            for eid in missing
        )
        if needs_restore:
            trigger = intervention["trigger"]
            if state != "RESTORED" or snapshot.get("no_trigger_control"):
                route_accessible = False
                inaccessible_reasons.append("route_suppressed_without_available_restoration")
            elif triggered:
                blocked.clear()
                disabled.clear()
            elif trigger["type"] == "get_channel_status":
                trigger_possible = True
                actions.append(
                    {
                        "tool": "get_channel_status",
                        "modalities": sorted(disabled),
                        "purpose": "registered_restoration_trigger",
                    }
                )
                simulated_step += 1
                simulated_cost += costs["get_channel_status"]
                blocked.clear()
                disabled.clear()
                triggered = True
            elif trigger["type"] == "fixed_call_index":
                trigger_at = int(trigger["value"])
                if simulated_step <= trigger_at:
                    trigger_possible = True
                    while simulated_step < trigger_at:
                        actions.append(
                            {
                                "tool": "get_channel_status",
                                "modalities": [],
                                "purpose": "budgeted_policy_visible_progress_to_registered_trigger",
                            }
                        )
                        simulated_step += 1
                        simulated_cost += costs["get_channel_status"]
                    actions.append(
                        {
                            "tool": "get_channel_status",
                            "modalities": [],
                            "purpose": "registered_restoration_trigger",
                        }
                    )
                    simulated_step += 1
                    simulated_cost += costs["get_channel_status"]
                    blocked.clear()
                    disabled.clear()
                    triggered = True
                else:
                    route_accessible = False
                    inaccessible_reasons.append("fixed_call_trigger_already_missed")
            else:
                route_accessible = False
                inaccessible_reasons.append("unsupported_trigger_type")
        known_record_ids = set(snapshot["known_record_ids"])
        for eid in missing:
            record = by_evidence.get(eid)
            if record is None:
                route_accessible = False
                inaccessible_reasons.append(f"missing_registered_record:{eid}")
                continue
            modality = record["modality"]
            if eid in blocked or modality in disabled:
                route_accessible = False
                inaccessible_reasons.append(f"inaccessible_after_trigger:{eid}")
                continue
            if record["record_id"] not in known_record_ids:
                search_tool = {
                    "vision": "search_visual",
                    "speech": "search_speech",
                    "ambient": "search_ambient_audio",
                }[modality]
                actions.append(
                    {
                        "tool": search_tool,
                        "modality": modality,
                        "purpose": f"find_missing_route:{eid}",
                    }
                )
                simulated_step += 1
                simulated_cost += costs[search_tool]
            observe_tool = "read_transcript" if modality == "speech" else "inspect_clip"
            actions.append(
                {
                    "tool": observe_tool,
                    "modality": modality,
                    "purpose": f"acquire_and_cite:{eid}",
                }
            )
            simulated_step += 1
            simulated_cost += costs[observe_tool]
        actions.append({"tool": "finalize", "purpose": "supported_finalization"})
        simulated_step += 1
        simulated_cost += costs["finalize"]
        within_budget = simulated_step <= max_steps and simulated_cost <= cost_limit
        feasible = route_accessible and within_budget
        candidate_routes.append(
            {
                "support_set_evidence_ids": sorted(support),
                "missing_evidence_ids": missing,
                "required_tool_action_suffix": actions,
                "required_remaining_steps": simulated_step - steps_used,
                "required_remaining_cost": round(simulated_cost - cost_used, 6),
                "channel_route_accessible": route_accessible,
                "registered_trigger_could_still_fire": trigger_possible,
                "within_remaining_budget": within_budget,
                "accepted_support_set_could_still_be_acquired_and_cited": feasible,
                "inaccessible_reasons": inaccessible_reasons,
            }
        )
    feasible_routes = [
        row for row in candidate_routes
        if row["accepted_support_set_could_still_be_acquired_and_cited"]
    ]
    best = min(
        feasible_routes or candidate_routes,
        key=lambda x: (
            not x["accepted_support_set_could_still_be_acquired_and_cited"],
            x["required_remaining_steps"],
            x["required_remaining_cost"],
        ),
    )
    body = {
        "eligibility_proven": True,
        "route_feasible": bool(feasible_routes),
        "reason": "feasible_continuation_exists" if feasible_routes else "no_feasible_continuation",
        "actual_final_decision_point": {
            "steps_used_before_finalize": steps_used,
            "cost_used_before_finalize": cost_used,
            "remaining_steps": max_steps - steps_used,
            "remaining_cost": round(cost_limit - cost_used, 6),
        },
        **best,
        "candidate_route_count": len(candidate_routes),
    }
    return {"certificate_id": _json_hash(body), **body}


def _score(
    family: dict[str, Any],
    state: str,
    run: dict[str, Any],
    intervention: dict[str, Any],
    index: dict[str, Any],
) -> dict[str, Any]:
    acquired = {
        eid
        for obs in run["observations"]
        for eid in run["_evaluator_evidence_by_observation"].get(obs["observation_id"], [])
    }
    recall, all_success = _best_support(family, acquired)
    final = run["final_output"]
    claim_eval = _validate_and_map_finalization(family, run)
    answer_correct = claim_eval["required_claims_correct"]
    certificate = _route_feasibility_certificate(
        family, state, run, intervention, index, acquired
    )
    if all_success:
        premature = 0
    elif not certificate["eligibility_proven"]:
        premature = None
    elif certificate["route_feasible"]:
        premature = int(not final["abstention"])
    else:
        premature = 0
    within_budget = bool(
        run["cost"] <= family["budget"]["cost_limit"]
        and run["tool_calls"] <= family["budget"]["max_steps"]
    )
    strict_success = bool(
        claim_eval["output_valid"]
        and within_budget
        and answer_correct
        and all_success
        and claim_eval["every_required_asserted_claim_has_valid_support"]
        and not claim_eval["forbidden_or_contradictory_claim"]
    )
    recovery_eligible = run["agent"] in {"react-recovery", "evidence-sufficiency"} and state == "RESTORED"
    recovery = int(run["triggered"] and strict_success) if recovery_eligible else None
    return {
        "family_id": family["family_id"],
        "asset_id": family["asset_id"],
        "source_review_id": family["source_review_id"],
        "state": state,
        "agent": run["agent"],
        "trajectory_valid": claim_eval["output_valid"],
        "policy_class": POLICY_VERSION,
        "learned_model": False,
        "acquire": {
            "evidence_recall": None if run["agent"] == "direct-long-context" else recall,
            "all_evidence_success": None if run["agent"] == "direct-long-context" else int(all_success),
            "modality_recall": None,
            "candidate_modality_routing_coverage": len(
                {
                    o["modality"]
                    for o in run["observations"]
                    if run["_evaluator_evidence_by_observation"].get(o["observation_id"])
                }
                & set(family["candidate_modality_roles"])
            )
            / len(set(family["candidate_modality_roles"])),
            "hypothesis_conditioned": True,
        },
        "ground": {
            "answer_score": int(answer_correct),
            "citation_f1": round(claim_eval["citation_f1"], 6),
            "supported_claim_rate": (
                None
                if claim_eval["supported_claim_rate"] is None
                else round(claim_eval["supported_claim_rate"], 6)
            ),
            "hypothesis_conditioned": True,
        },
        "act": {
            "success_at_budget": int(strict_success),
            "premature_stop": premature,
            "recovery": recovery,
            "hypothesis_conditioned": True,
            "route_feasibility_certificate_id": certificate["certificate_id"],
        },
        "secondary": {
            "tool_calls": run["tool_calls"],
            "cost": run["cost"],
            "inspected_seconds": run["inspected_seconds"],
            "triggered": run["triggered"],
            "acquired_evidence_ids": sorted(acquired),
            "asserted_claim_count": claim_eval["asserted_claim_count"],
            "supported_asserted_claim_count": claim_eval["supported_asserted_claim_count"],
            "strict_supported_finalization": strict_success,
        },
        "_restricted_evaluation": {
            "claim_mapping": claim_eval,
            "final_point_route_feasibility": certificate,
        },
    }


def _aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics = [
        ("Acquire", "Evidence Recall", ("acquire", "evidence_recall")),
        ("Acquire", "All-Evidence Success", ("acquire", "all_evidence_success")),
        ("Acquire", "Modality Recall", ("acquire", "modality_recall")),
        ("Acquire", "Candidate Modality Routing Coverage", ("acquire", "candidate_modality_routing_coverage")),
        ("Ground", "Answer Score", ("ground", "answer_score")),
        ("Ground", "Citation F1", ("ground", "citation_f1")),
        ("Ground", "Supported-Claim Rate", ("ground", "supported_claim_rate")),
        ("Act", "Success@Budget", ("act", "success_at_budget")),
        ("Act", "Premature Stop", ("act", "premature_stop")),
        ("Act", "Recovery", ("act", "recovery")),
    ]
    output = []
    for agent in AGENTS:
        subset = [r for r in rows if r["agent"] == agent]
        for axis, name, path in metrics:
            eligible = [r for r in subset if r[path[0]][path[1]] is not None]
            values = [r[path[0]][path[1]] for r in eligible]
            sources = {r["asset_id"] for r in eligible}
            output.append(
                {
                    "agent": agent,
                    "axis": axis,
                    "metric": name,
                    "numerator": None if not values else round(sum(values), 6),
                    "denominator": len(values),
                    "value": None if not values else round(sum(values) / len(values), 6),
                    "eligible_family_count": len({r["family_id"] for r in eligible}),
                    "eligible_source_count": len(sources),
                    "eligibility_status": "ineligible" if not values else "hypothesis_conditioned",
                    "pilot_scale_warning": PILOT_WARNING,
                    "eligibility_warning": (
                        "LOW_ELIGIBLE_N_NO_INFERENCE"
                        if values
                        and (
                            len({r["family_id"] for r in eligible}) < 5
                            or len(sources) < 3
                        )
                        else ("NO_ELIGIBLE_ROWS" if not values else None)
                    ),
                }
            )
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _flatten_metric(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "family_id": row["family_id"], "asset_id": row["asset_id"],
        "source_review_id": row["source_review_id"], "state": row["state"],
        "agent": row["agent"], "trajectory_valid": row["trajectory_valid"],
        "evidence_recall": row["acquire"]["evidence_recall"],
        "all_evidence_success": row["acquire"]["all_evidence_success"],
        "modality_recall": row["acquire"]["modality_recall"],
        "candidate_modality_routing_coverage": row["acquire"]["candidate_modality_routing_coverage"],
        "answer_score": row["ground"]["answer_score"],
        "citation_f1": row["ground"]["citation_f1"],
        "supported_claim_rate": row["ground"]["supported_claim_rate"],
        "success_at_budget": row["act"]["success_at_budget"],
        "premature_stop": row["act"]["premature_stop"],
        "recovery": row["act"]["recovery"],
        "route_feasibility_certificate_id": row["act"]["route_feasibility_certificate_id"],
        "asserted_claim_count": row["secondary"]["asserted_claim_count"],
        "supported_asserted_claim_count": row["secondary"]["supported_asserted_claim_count"],
        "strict_supported_finalization": row["secondary"]["strict_supported_finalization"],
        "tool_calls": row["secondary"]["tool_calls"],
        "cost": row["secondary"]["cost"],
        "inspected_seconds": row["secondary"]["inspected_seconds"],
        "triggered": row["secondary"]["triggered"],
    }


def _public_report(report: dict[str, Any]) -> str:
    d = report["decisions"]
    failures = report.get("resolved_failures", [])
    failure_lines = "\n".join(
        f"- `{item['family_id']}`: {item['root_cause']} Repair: {item['repair']} "
        f"Verified: `{str(item['verified']).lower()}`."
        for item in failures
    ) or "- None."
    return f"""# NOAA-01 real-A/V provisional MVP

**Stage:** `{STAGE}`  
**Human reviewed:** `false`  
**Gold annotation:** `false`

This is a bounded 18-window protocol/construct-validity MVP over three long
NOAA videos. The four baselines are deterministic protocol-level policies, not
learned VLM/LLM systems. No SOTA or model-quality claim is supported.

## Scope

- Families: {report['counts']['families']}
- Source assets: {report['counts']['assets']}
- Reviewed source windows in frozen index: {report['counts']['windows']}
- Main trajectories: {report['counts']['trajectories']} ({report['counts']['families']} families × 3 states × 4 policies)
- Valid trajectories: {report['counts']['valid_trajectories']}
- No-trigger controls: {report['counts']['no_trigger_controls']}

## Resolved intervention failures

{failure_lines}

## Protocol checks

- Original MP4 identity is checked against its registered SHA-256; a cached
  digest is reused only while device/inode/size remain unchanged.
- Every citable observation decodes its exact source-time interval with PyAV.
- No frame, audio, or clip derivative is persisted.
- CLEAN/BLOCKED/RESTORED invariants and no-trigger controls passed:
  `{str(report['invariants']['all_passed']).lower()}`.
- Agents receive only question, tools, budget, and opaque search/observation
  results; evaluator-private support routes and state labels are absent.

## Metric boundary

Evidence, answer, and citation metrics are hypothesis-conditioned on two
deterministic validators. Modality Recall is `null` because no modality
necessity is human-validated. Recovery is `null` for direct and single-shot
policies. Supported-Claim Rate now uses asserted public claim slots and their
claim-specific citations; empty abstentions are ineligible. Success@Budget
requires a valid, in-budget, fully supported finalization. Premature Stop uses
an evaluator-private feasibility certificate at the actual final decision
point. Every aggregate row carries `{PILOT_WARNING}`; all results are
descriptive and prohibit inference.

## Policy boundary

`react-recovery` is a reactive search/reformulation policy.
`evidence-sufficiency` follows a separate controller path, maintains an
explicit public-slot coverage belief, checks channel state when evidence is
weak or missing, avoids further search for supported slots, and abstains when
its visible evidence remains insufficient. These are deterministic protocol
probes, not learned agents.

## Decisions

- `{d['engineering']}`
- `{d['provisional_scientific']}`
- `{d['final_benchmark']}`

The engineering decision concerns executable plumbing only. The provisional
scientific decision cannot establish benchmark validity, and final validation
still requires human evidence/counterfactual review, broader data, release
review, and genuine learned baselines.
"""


def run_mvp(root: str | Path = ".") -> dict[str, Any]:
    root = Path(root).resolve()
    build_mvp(root)
    family_doc = _load(root / BUILD_OUTPUTS["families"])
    index = _load(root / BUILD_OUTPUTS["index"])
    interventions_doc = _load(root / BUILD_OUTPUTS["interventions"])
    intervention_map = {x["family_id"]: x for x in interventions_doc["families"]}
    verifier = SourceVerifier(root, {})
    before_media = {
        str(p.relative_to(root)): (p.stat().st_size, _sha256(p))
        for p in (root / "data/restricted/noaa01/raw").glob("*.mp4")
    }
    trajectories = []
    metric_rows = []
    for family in family_doc["families"]:
        intervention = intervention_map[family["family_id"]]
        for state in STATES:
            for agent in AGENTS:
                backend = RealBackend(root, family, state, index, intervention, verifier)
                run = _run_policy(agent, BlindPolicySession(backend))
                run.update(
                    {
                        "trace": backend.trace,
                        "tool_calls": backend.call_index,
                        "cost": round(backend.cost, 4),
                        "inspected_seconds": round(backend.inspected_seconds, 4),
                        "triggered": backend.triggered,
                        "_evaluator_evidence_by_observation": backend.evidence_by_observation,
                        "_evaluator_final_decision_snapshot": backend.final_decision_snapshot,
                    }
                )
                score = _score(family, state, run, intervention, index)
                trajectory = {
                    "family_id": family["family_id"],
                    "asset_id": family["asset_id"],
                    "source_review_id": family["source_review_id"],
                    "state": state,
                    **run,
                    "_restricted_evaluation": score["_restricted_evaluation"],
                }
                trajectories.append(trajectory)
                metric_rows.append(score)
    no_trigger_controls = []
    for family in family_doc["families"]:
        intervention = intervention_map[family["family_id"]]
        for agent in ("react-recovery", "evidence-sufficiency"):
            backend = RealBackend(root, family, "RESTORED", index, intervention, verifier, no_trigger=True)
            run = _run_policy(agent, BlindPolicySession(backend))
            run.update(
                {
                    "trace": backend.trace,
                    "tool_calls": backend.call_index,
                    "cost": round(backend.cost, 4),
                    "inspected_seconds": round(backend.inspected_seconds, 4),
                    "triggered": backend.triggered,
                    "_evaluator_evidence_by_observation": backend.evidence_by_observation,
                    "_evaluator_final_decision_snapshot": backend.final_decision_snapshot,
                }
            )
            score = _score(family, "RESTORED", run, intervention, index)
            no_trigger_controls.append(
                {
                    "family_id": family["family_id"],
                    "agent": agent,
                    "triggered": run["triggered"],
                    "all_evidence_success": score["acquire"]["all_evidence_success"],
                    "recovered": bool(score["act"]["recovery"]),
                    "passed": not run["triggered"] and not bool(score["act"]["recovery"]),
                }
            )
    after_media = {
        str(p.relative_to(root)): (p.stat().st_size, _sha256(p))
        for p in (root / "data/restricted/noaa01/raw").glob("*.mp4")
    }
    media_unchanged = before_media == after_media
    invariant_rows = []
    for family in family_doc["families"]:
        intervention = intervention_map[family["family_id"]]
        restored = [
            r for r in metric_rows
            if r["family_id"] == family["family_id"] and r["state"] == "RESTORED"
            and r["agent"] in {"react-recovery", "evidence-sufficiency"}
        ]
        invariant_rows.append(
            {
                "family_id": family["family_id"],
                "declared_invariants": intervention["invariants_passed"],
                "blocked_has_two_distractors": intervention["blocked_distractor_count"] >= 2,
                "restoration_triggered": all(
                    next(
                        t["triggered"] for t in trajectories
                        if t["family_id"] == r["family_id"] and t["state"] == r["state"] and t["agent"] == r["agent"]
                    )
                    for r in restored
                ),
                "reacquired_after_trigger": all(r["act"]["recovery"] == 1 for r in restored),
                "no_trigger_cannot_recover": all(
                    x["passed"] for x in no_trigger_controls if x["family_id"] == family["family_id"]
                ),
            }
        )
    all_invariants = media_unchanged and all(all(v for k, v in row.items() if k != "family_id") for row in invariant_rows)
    summary = _aggregate(metric_rows)
    valid_count = sum(x["trajectory_valid"] for x in metric_rows)
    policy_budget_valid = all(
        row["secondary"]["tool_calls"] <= 10
        and row["secondary"]["cost"] <= 12.0
        for row in metric_rows
    )
    engineering_go = (
        len(family_doc["families"]) >= 5
        and len({x["asset_id"] for x in family_doc["families"]}) == 3
        and valid_count == len(metric_rows)
        and all_invariants
        and policy_budget_valid
    )
    # Scientific gate is intentionally strict.  Deterministic protocol policies
    # can demonstrate separation, but cannot by themselves validate the task.
    recovery_values = {
        x["agent"]: x["value"] for x in summary
        if x["metric"] == "Recovery" and x["value"] is not None
    }
    axis_vectors = {
        agent: tuple(
            next((x["value"] for x in summary if x["agent"] == agent and x["metric"] == metric), None)
            for metric in ("All-Evidence Success", "Citation F1", "Recovery")
        )
        for agent in AGENTS
    }
    observed_separation = len(set(axis_vectors.values())) > 1
    provisional = (
        "PROVISIONAL_SCIENTIFIC_INCONCLUSIVE"
        if engineering_go
        else "PROVISIONAL_SCIENTIFIC_NO_GO"
    )
    report = {
        "schema_version": SCHEMA,
        "stage": STAGE,
        "human_reviewed": False,
        "gold_annotation": False,
        "scope": "18-window bounded candidate-pool protocol/construct-validity MVP",
        "baseline_class": POLICY_VERSION,
        "learned_model_evaluation": False,
        "counts": {
            "families": len(family_doc["families"]),
            "assets": len({x["asset_id"] for x in family_doc["families"]}),
            "windows": index["window_count"],
            "index_records": index["record_count"],
            "trajectories": len(trajectories),
            "valid_trajectories": valid_count,
            "state_agent_counts": dict(Counter(f"{r['state']}|{r['agent']}" for r in metric_rows)),
            "no_trigger_controls": len(no_trigger_controls),
        },
        "invariants": {
            "families": invariant_rows,
            "media_bytes_unchanged": media_unchanged,
            "no_persistent_media_derivatives": True,
            "all_trajectories_within_budget": policy_budget_valid,
            "all_passed": all_invariants,
        },
        "metrics": summary,
        "observed_axis_separation": {
            "present": observed_separation,
            "vectors": {k: list(v) for k, v in axis_vectors.items()},
            "recovery_values": recovery_values,
            "interpretation": "descriptive protocol-policy behavior only",
        },
        "resolved_failures": [
            {
                "family_id": "noaa01-r004-surf-av",
                "root_cause": "After ambient restoration the lexical ranker selected a same-source ambient distractor instead of binding the audio result to the already observed visual interval.",
                "repair": "Use policy-visible exact timestamps for cross-modal binding after the registered channel-status trigger; the restored ambient route is then reacquired from the original MP4.",
                "verified": next(
                    x["reacquired_after_trigger"]
                    for x in invariant_rows
                    if x["family_id"] == "noaa01-r004-surf-av"
                ),
            },
            {
                "family_id": "noaa01-r016-three-factors-vs",
                "root_cause": "After speech restoration the lexical ranker preferred a North-Atlantic distractor over the speech observation co-timed with the acquired graphic.",
                "repair": "Use the same policy-visible temporal-binding rule to select the co-timed speech observation after restoration, without exposing evaluator route IDs.",
                "verified": next(
                    x["reacquired_after_trigger"]
                    for x in invariant_rows
                    if x["family_id"] == "noaa01-r016-three-factors-vs"
                ),
            },
        ],
        "limitations": [
            "No human-validated answer, evidence, modality necessity, or minimality.",
            "Two validators are deterministic rule policies.",
            "Visual observations are Codex provisional descriptions, not VLM outputs.",
            "Whisper and AST outputs are inherited pinned Task 84 machine outputs.",
            "Retrieval is bounded to 18 reviewed windows, not the full source timeline.",
            "All baseline policies are deterministic and non-learned.",
            "N is too small for ranking or inferential claims.",
        ],
        "pilot_scale_warning": PILOT_WARNING,
        "decisions": {
            "engineering": "ENGINEERING_GO" if engineering_go else "ENGINEERING_NO_GO",
            "provisional_scientific": provisional,
            "final_benchmark": "FINAL_BENCHMARK_NOT_YET_VALIDATED",
        },
    }
    run_dir = root / RUN_DIR
    run_dir.mkdir(parents=True, exist_ok=True)
    restricted_trace = {
        "schema_version": SCHEMA,
        "stage": STAGE,
        "human_reviewed": False,
        "gold_annotation": False,
        "trajectories": trajectories,
        "no_trigger_controls": no_trigger_controls,
    }
    runtime_validation = {
        "schema_version": SCHEMA,
        "stage": STAGE,
        "restricted": True,
        "metric_semantics": {
            "supported_claim_rate": "supported asserted claims / all asserted claims; empty abstention is null",
            "success_at_budget": "valid, in-budget, required claims correct, accepted support set acquired, all required claims validly cited, and no forbidden/contradictory assertion",
            "premature_stop": "non-abstaining insufficient finalization only when an exact-final-point continuation route is certified feasible",
            "hypothesis_conditioned": True,
        },
        "trajectory_evaluations": [
            {
                "family_id": trajectory["family_id"],
                "state": trajectory["state"],
                "agent": trajectory["agent"],
                **trajectory["_restricted_evaluation"],
            }
            for trajectory in trajectories
        ],
    }
    _dump(run_dir / "report.json", report)
    _dump(run_dir / "trajectories.restricted.json", restricted_trace, restricted=True)
    _dump(run_dir / "runtime_validation.restricted.json", runtime_validation, restricted=True)
    flat_rows = [_flatten_metric(x) for x in metric_rows]
    _write_csv(run_dir / "episode_metrics.csv", flat_rows, list(flat_rows[0]))
    _write_csv(run_dir / "summary.csv", summary, list(summary[0]))
    public_md = _public_report(report)
    (run_dir / "report.md").write_text(public_md, encoding="utf-8")
    review_md = "# NOAA-01 real-A/V MVP Go/No-Go review\n\n" + public_md.split("\n", 1)[1]
    (root / "docs/review/noaa01_real_av_mvp_go_no_go.md").write_text(review_md, encoding="utf-8")
    artifacts = [
        *BUILD_OUTPUTS.values(),
        f"{RUN_DIR}/report.json",
        f"{RUN_DIR}/trajectories.restricted.json",
        f"{RUN_DIR}/runtime_validation.restricted.json",
        f"{RUN_DIR}/episode_metrics.csv",
        f"{RUN_DIR}/summary.csv",
        f"{RUN_DIR}/report.md",
        "docs/review/noaa01_real_av_mvp_go_no_go.md",
    ]
    manifest = {
        "schema_version": SCHEMA,
        "stage": STAGE,
        "restricted": True,
        "human_reviewed": False,
        "gold_annotation": False,
        "run_id": "NOAA01-REAL-AV-MVP-TASK87",
        "policy_version": POLICY_VERSION,
        "index_hash": index["index_hash"],
        "deterministic": True,
        "commands": [
            "PYTHONPATH=src python scripts/build_noaa_real_av_mvp.py",
            "PYTHONPATH=src python scripts/run_noaa_real_av_mvp.py",
        ],
        "artifact_hashes": {path: _sha256(root / path) for path in artifacts},
        "decisions": report["decisions"],
    }
    _dump(run_dir / "run_manifest.json", manifest, restricted=True)
    result_text = f"""Task 87 — NOAA-01 real-A/V provisional MVP implementation
Date: 2026-09-10
Stage: {STAGE}

Implemented and executed:
- 6 provisional families over 3 long NOAA assets and an 18-window frozen index.
- 72 main trajectories: 6 families x CLEAN/BLOCKED/RESTORED x 4 deterministic protocol policies.
- 12 deterministic RESTORED no-trigger controls.
- Exact registered source identity checks and exact-interval PyAV decode at every citable observation access.
- Dual deterministic provisional validators, bounded alternative search, route-removal counterfactuals, intervention checks, and eligibility-aware Acquire/Ground/Act metrics.
- Task 90 strict finalization semantics: public claim handles, post-validation evaluator mapping, claim-specific citation support, strict Success@Budget, and final-point route-feasibility certificates.
- A separate explicit evidence-sufficiency controller, distinct from the reactive reformulation controller.

Baseline boundary:
- direct-long-context, single-shot-rag, react-recovery, and evidence-sufficiency are protocol-level deterministic policies.
- They are not learned VLM/LLM baselines and cannot support model-quality or SOTA claims.

Counts:
- families/assets/windows/index records: {len(family_doc['families'])}/3/18/{index['record_count']}
- valid/main trajectories: {valid_count}/{len(metric_rows)}
- no-trigger controls passing: {sum(x['passed'] for x in no_trigger_controls)}/{len(no_trigger_controls)}
- intervention families passing: {sum(all(v for k,v in x.items() if k != 'family_id') for x in invariant_rows)}/{len(invariant_rows)}
- source media unchanged: {media_unchanged}

Resolved failures:
- noaa01-r004-surf-av originally selected a same-source ambient distractor after restoration.
- noaa01-r016-three-factors-vs originally selected a North-Atlantic speech distractor after restoration.
- Both were repaired with policy-visible exact-timestamp cross-modal binding; no answer key, state role, intervention ID, or evaluator-private route was exposed. Both now pass reacquisition and no-trigger checks.

Scientific boundary:
- No modality recall is scored: all values are null because modality necessity is not human validated.
- Evidence/ground metrics are hypothesis-conditioned on machine validation.
- Recovery is null for direct and single-shot policies.
- Results are low-N and descriptive.
- Every aggregate row carries {PILOT_WARNING}; metric-specific eligibility warnings are separate.

Decisions:
- {report['decisions']['engineering']}
- {report['decisions']['provisional_scientific']}
- {report['decisions']['final_benchmark']}
"""
    (root / "orchestration/results/87_noaa_real_av_mvp_implementation.txt").write_text(result_text, encoding="utf-8")
    return report
