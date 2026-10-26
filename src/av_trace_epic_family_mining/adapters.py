"""Fail-closed adapters for the canonical EPIC index and human prescreen."""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .contracts import json_hash

CANONICAL_ARTIFACTS = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "build_manifest.json",
)
EXPECTED_INDEX_SCHEMA = "av-trace.epic-wave1-index/1.0"
EXPECTED_INDEX_VERSION = "epic-wave1-full-timeline-index/1.0"
EXPECTED_STAGE = "RESTRICTED_EPIC_WAVE1_SOURCE_DERIVED_INDEX"
EXPECTED_SOURCE_IDS = ("P27_101", "P28_103")
EXPECTED_SOURCE_GROUPS = {"P27_101": "P27", "P28_103": "P28"}
PRESCREEN_READY = "SEMANTIC_AV_SOURCE_PRESCREEN_READY"

_FORBIDDEN_EPIC_SEMANTIC_KEYS = {
    "action",
    "actions",
    "action_class",
    "action_classes",
    "action_label",
    "action_labels",
    "action_segment",
    "action_segments",
    "verb",
    "verb_class",
    "noun",
    "noun_class",
    "narration",
    "narrations",
    "narration_id",
    "narration_text",
    "narration_timestamp",
    "narration_timestamps",
    "epic_sounds",
    "epic_sounds_labels",
    "epic_sounds_events",
    "sound_class",
    "sound_classes",
    "sound_event_id",
    "sound_event_ids",
    "benchmark_split",
    "benchmark_label",
}
_FORBIDDEN_VAULT_FRAGMENTS = (
    "annotations",
    "annotation_vault",
    "epic_sounds",
    "epic-sounds",
)


class EpicFamilyInputError(RuntimeError):
    """An input cannot safely support EPIC candidate mining."""


@dataclass(frozen=True)
class EpicIndexInputs:
    """Normalized complete canonical index inputs."""

    index: Mapping[str, Any]
    segment_manifest: Mapping[str, Any]
    observation_manifest: Mapping[str, Any]
    routing_records: tuple[Mapping[str, Any], ...]
    source_hashes: Mapping[str, str]
    source_groups: Mapping[str, str]
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class HumanObservation:
    """One human-prescreened dynamic-visual or non-speech observation."""

    observation_id: str
    modality: str
    start_us: int
    end_us: int
    candidate_fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class PrescreenSourceGate:
    """Completed human source-level authoring gate."""

    source_id: str
    source_group_id: str
    authoring_eligibility: str
    observations: tuple[HumanObservation, ...]
    candidate_facts: tuple[Mapping[str, Any], ...]
    recurrence_groups: tuple[Mapping[str, Any], ...]
    authoring_constraints: tuple[str, ...]


@dataclass(frozen=True)
class PrescreenBundle:
    """Human-complete Task-153 artifacts."""

    sources: Mapping[str, PrescreenSourceGate]
    provenance: Mapping[str, Any]


def _fail(code: str, detail: str = "") -> None:
    raise EpicFamilyInputError(f"{code}:{detail}" if detail else code)


def _read_json(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        _fail(code, path.as_posix())
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EpicFamilyInputError(f"{code}:{path.as_posix()}") from exc
    if not isinstance(value, dict):
        _fail(code, path.as_posix())
    return value


def _sha256(path: Path, *, prefixed: bool = True) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    value = digest.hexdigest()
    return f"sha256:{value}" if prefixed else value


def _repo_path(
    root: Path,
    value: str | Path,
    *,
    allow_prescreen_annotation: bool = False,
) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        try:
            relative = raw.resolve(strict=False).relative_to(root)
        except ValueError:
            _fail("PATH_OUTSIDE_REPOSITORY", raw.as_posix())
        pure = PurePosixPath(relative.as_posix())
    else:
        pure = PurePosixPath(raw.as_posix())
    if ".." in pure.parts or ".staging" in pure.parts:
        _fail("UNSAFE_REPOSITORY_PATH", raw.as_posix())
    lowered = pure.as_posix().casefold()
    forbidden = (
        _FORBIDDEN_VAULT_FRAGMENTS
        if not allow_prescreen_annotation
        else tuple(
            fragment
            for fragment in _FORBIDDEN_VAULT_FRAGMENTS
            if fragment != "annotations"
        )
    )
    if any(fragment in lowered for fragment in forbidden):
        _fail("EXISTING_ANNOTATION_VAULT_PATH_FORBIDDEN", raw.as_posix())
    path = root.joinpath(*pure.parts)
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError:
        _fail("PATH_OUTSIDE_REPOSITORY", raw.as_posix())
    if path.is_symlink():
        _fail("SYMLINK_INPUT_FORBIDDEN", raw.as_posix())
    return path


def _self_hash(document: Mapping[str, Any], key: str) -> bool:
    copy = dict(document)
    stored = copy.pop(key, None)
    return stored == json_hash(copy)


def _scan_forbidden_semantic_keys(
    value: Any,
    location: str = "index",
    *,
    parent_key: str | None = None,
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if (
                parent_key not in {"term_frequency", "document_frequency"}
                and str(key).casefold() in _FORBIDDEN_EPIC_SEMANTIC_KEYS
            ):
                _fail("SEALED_EPIC_SEMANTIC_FIELD_PRESENT", f"{location}.{key}")
            _scan_forbidden_semantic_keys(
                child,
                f"{location}.{key}",
                parent_key=str(key),
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden_semantic_keys(
                child,
                f"{location}[{index}]",
                parent_key=parent_key,
            )


def _inventory(build: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("path")): item
        for item in build.get("artifacts", ())
        if isinstance(item, Mapping)
    }


def _verify_mode(path: Path, expected: int, code: str) -> None:
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != expected:
        _fail(code, path.as_posix())


def load_canonical_epic_index(
    repo_root: str | Path,
    *,
    index_root: str | Path = "data/restricted/epic_wave1_index_v1",
    plan_path: str | Path = (
        "data/rehearsal_plan/epic_wave1_full_timeline_index_v1.json"
    ),
) -> EpicIndexInputs:
    """Load only the complete, canonical, non-smoke EPIC Wave-1 index."""
    root = Path(repo_root).resolve()
    output = _repo_path(root, index_root)
    missing = [name for name in CANONICAL_ARTIFACTS if not (output / name).is_file()]
    if missing:
        _fail("EPIC_CANONICAL_INDEX_INCOMPLETE_MISSING", ",".join(sorted(missing)))
    _verify_mode(output, 0o700, "EPIC_INDEX_ROOT_MODE_INVALID")
    documents = {
        name: _read_json(output / name, f"EPIC_INDEX_ARTIFACT_INVALID:{name}")
        for name in CANONICAL_ARTIFACTS
    }
    build = documents["build_manifest.json"]
    _verify_mode(
        output / "build_manifest.json",
        0o600,
        "EPIC_INDEX_ARTIFACT_MODE_INVALID",
    )
    if build.get("status") != "COMPLETE":
        _fail("EPIC_CANONICAL_INDEX_BUILD_NOT_COMPLETE")
    if build.get("mode") != "full" or build.get("smoke_seconds") is not None:
        _fail("EPIC_SMOKE_INDEX_FORBIDDEN")
    if build.get("source_count") != 2 or build.get("expected_source_count") != 2:
        _fail("EPIC_CANONICAL_SOURCE_COUNT_MUST_BE_TWO")
    if build.get("output_dir") != output.relative_to(root).as_posix():
        _fail("EPIC_CANONICAL_OUTPUT_BINDING_MISMATCH")
    boundary = build.get("terminal_boundary", {})
    if any(
        boundary.get(key) is not False
        for key in (
            "families_generated",
            "interventions_generated",
            "trajectories_generated",
            "evaluation_generated",
        )
    ):
        _fail("EPIC_CANONICAL_TERMINAL_BOUNDARY_INVALID")
    if not _self_hash(build, "build_manifest_hash"):
        _fail("EPIC_BUILD_MANIFEST_SELF_HASH_INVALID")

    artifact_inventory = _inventory(build)
    for name in CANONICAL_ARTIFACTS[:-1]:
        path = output / name
        _verify_mode(path, 0o600, "EPIC_INDEX_ARTIFACT_MODE_INVALID")
        relative = path.relative_to(root).as_posix()
        record = artifact_inventory.get(relative)
        if record is None:
            _fail("EPIC_ARTIFACT_NOT_FROZEN", name)
        if record.get("sha256") != _sha256(path):
            _fail("EPIC_ARTIFACT_HASH_MISMATCH", name)
        if record.get("size_bytes") != path.stat().st_size:
            _fail("EPIC_ARTIFACT_SIZE_MISMATCH", name)

    segment = documents["segment_manifest.json"]
    observation = documents["observation_manifest.json"]
    index = documents["full_timeline_index.json"]
    resource = documents["resource_manifest.json"]
    for document, key in (
        (segment, "segment_manifest_hash"),
        (observation, "observation_manifest_hash"),
        (index, "index_hash"),
        (resource, "resource_manifest_hash"),
    ):
        if document.get("schema_version") != EXPECTED_INDEX_SCHEMA:
            _fail("EPIC_INDEX_SCHEMA_VERSION_MISMATCH", key)
        if document.get("stage") != EXPECTED_STAGE:
            _fail("EPIC_INDEX_STAGE_MISMATCH", key)
        if not _self_hash(document, key):
            _fail("EPIC_INDEX_SELF_HASH_INVALID", key)
    if index.get("index_version") != EXPECTED_INDEX_VERSION:
        _fail("EPIC_INDEX_VERSION_MISMATCH")
    if not observation.get("all_sources_complete"):
        _fail("EPIC_OBSERVATIONS_INCOMPLETE")
    if observation.get("checkpoint_count") not in {None, 8}:
        _fail("EPIC_CHECKPOINT_COUNT_INVALID")
    complete_sources = tuple(sorted(observation.get("complete_source_refs", ())))
    if complete_sources != EXPECTED_SOURCE_IDS:
        _fail("EPIC_COMPLETE_SOURCE_SET_MISMATCH")
    source_hashes = dict(index.get("source_hashes", {}))
    if tuple(sorted(source_hashes)) != EXPECTED_SOURCE_IDS:
        _fail("EPIC_INDEX_SOURCE_SET_MISMATCH")
    if build.get("source_sha256") != source_hashes:
        _fail("EPIC_BUILD_SOURCE_HASH_BINDING_MISMATCH")
    if index.get("segment_manifest_hash") != segment.get("segment_manifest_hash"):
        _fail("EPIC_INDEX_SEGMENT_BINDING_MISMATCH")
    if index.get("observation_manifest_hash") != observation.get(
        "observation_manifest_hash"
    ):
        _fail("EPIC_INDEX_OBSERVATION_BINDING_MISMATCH")

    plan_file = _repo_path(root, plan_path)
    plan = _read_json(plan_file, "EPIC_INDEX_PLAN_INVALID")
    if build.get("plan_path") != plan_file.relative_to(root).as_posix():
        _fail("EPIC_INDEX_PLAN_PATH_BINDING_MISMATCH")
    if build.get("plan_sha256") != _sha256(plan_file, prefixed=False):
        _fail("EPIC_INDEX_PLAN_HASH_BINDING_MISMATCH")
    expected_totals = plan.get("totals", {})
    observed_totals = segment.get("totals", {})
    for key, segment_key in (
        ("base_cells", "base_cells"),
        ("fine_windows", "fine_windows"),
        ("context_windows", "context_windows"),
        ("temporal_segments", "windows"),
    ):
        if int(expected_totals.get(key, -1)) != int(
            observed_totals.get(segment_key, -2)
        ):
            _fail("EPIC_INDEX_COUNT_MISMATCH", key)
    if int(expected_totals.get("whisper_chunks", -1)) != int(
        observation.get("counts", {}).get("whisper_chunks", -2)
    ):
        _fail("EPIC_INDEX_COUNT_MISMATCH", "whisper_chunks")
    if int(expected_totals.get("checkpoint_count", -1)) != len(
        observation.get("checkpoints", ())
    ):
        _fail("EPIC_INDEX_COUNT_MISMATCH", "checkpoint_count")

    routing_records: list[Mapping[str, Any]] = []
    for checkpoint in observation.get("checkpoints", ()):
        checkpoint_path = _repo_path(root, str(checkpoint.get("path", "")))
        if checkpoint_path.name not in {
            "speech.json",
            "ambient.json",
            "vision_routing.json",
            "vision_clip.json",
        }:
            _fail("EPIC_CHECKPOINT_NAME_INVALID", checkpoint_path.name)
        _verify_mode(checkpoint_path, 0o600, "EPIC_CHECKPOINT_MODE_INVALID")
        if checkpoint.get("sha256") != _sha256(checkpoint_path):
            _fail("EPIC_CHECKPOINT_HASH_MISMATCH", checkpoint_path.as_posix())
        if checkpoint.get("size_bytes") != checkpoint_path.stat().st_size:
            _fail("EPIC_CHECKPOINT_SIZE_MISMATCH", checkpoint_path.as_posix())
        if checkpoint_path.name == "vision_routing.json":
            payload = _read_json(
                checkpoint_path, "EPIC_ROUTING_CHECKPOINT_INVALID"
            )
            if payload.get("semantic_claim_allowed") is not False:
                _fail("EPIC_ROUTING_SEMANTIC_CLAIM_FLAG_INVALID")
            routing_records.extend(
                dict(item) for item in payload.get("records", ())
            )

    _scan_forbidden_semantic_keys(index)
    policy = index.get("searchable_field_policy", {})
    if policy.get("evaluator_annotations_excluded") is not True:
        _fail("EPIC_EVALUATOR_ANNOTATION_EXCLUSION_MISSING")
    if policy.get("rights_metadata_excluded") is not True:
        _fail("EPIC_RIGHTS_METADATA_EXCLUSION_MISSING")
    if resource.get("acquisition_gate", {}).get("passed") is not True:
        _fail("EPIC_ACQUISITION_GATE_NOT_BOUND")
    source_groups = {
        str(item["source_id"]): str(item["source_group_id"])
        for item in plan.get("sources", ())
    }
    if source_groups != EXPECTED_SOURCE_GROUPS:
        _fail("EPIC_SOURCE_GROUP_BINDING_MISMATCH")
    return EpicIndexInputs(
        index=index,
        segment_manifest=segment,
        observation_manifest=observation,
        routing_records=tuple(routing_records),
        source_hashes=source_hashes,
        source_groups=source_groups,
        provenance={
            "adapter": "canonical_epic_wave1_full_timeline_v1",
            "index_root": output.relative_to(root).as_posix(),
            "build_manifest_hash": build["build_manifest_hash"],
            "index_hash": index["index_hash"],
            "observation_manifest_hash": observation[
                "observation_manifest_hash"
            ],
            "segment_manifest_hash": segment["segment_manifest_hash"],
            "resource_manifest_hash": resource["resource_manifest_hash"],
            "semantic_epic_annotations_accessed": False,
            "existing_annotation_vault_accessed": False,
            "complete_non_smoke_index_required": True,
        },
    )


def _required_completed_prescreen(
    plan: Mapping[str, Any],
    form: Mapping[str, Any],
    report: Mapping[str, Any],
) -> None:
    if plan.get("record_type") != "semantic_av_source_prescreen_plan":
        _fail("PRESCREEN_PLAN_TYPE_INVALID")
    if plan.get("semantic_labels_present") is not False:
        _fail("PRESCREEN_PLAN_MUST_BE_NONSEMANTIC")
    plan_copy = dict(plan)
    stored_hash = plan_copy.pop("plan_sha256", None)
    expected_hash = "sha256:" + hashlib.sha256(
        (
            json.dumps(
                plan_copy,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    if stored_hash != expected_hash:
        _fail("PRESCREEN_PLAN_HASH_INVALID")
    if form.get("record_type") != "semantic_av_source_prescreen_annotation":
        _fail("PRESCREEN_FORM_TYPE_INVALID")
    if form.get("completion_status") != "completed":
        _fail("PRESCREEN_NOT_HUMAN_COMPLETE")
    if form.get("human_semantic_prescreen_only") is not True:
        _fail("PRESCREEN_HUMAN_SEMANTIC_FLAG_MISSING")
    reviewer = form.get("reviewer", {})
    if (
        not reviewer.get("reviewer_id")
        or reviewer.get("training_attested") is not True
        or not reviewer.get("started_at")
        or not reviewer.get("completed_at")
    ):
        _fail("PRESCREEN_TRAINED_HUMAN_COMPLETION_INVALID")
    try:
        started = datetime.fromisoformat(str(reviewer["started_at"]))
        completed = datetime.fromisoformat(str(reviewer["completed_at"]))
    except ValueError:
        _fail("PRESCREEN_REVIEW_TIMESTAMP_INVALID")
    if completed < started:
        _fail("PRESCREEN_REVIEW_TIME_ORDER_INVALID")
    if form.get("plan_id") != plan.get("plan_id"):
        _fail("PRESCREEN_FORM_PLAN_ID_MISMATCH")
    if form.get("plan_sha256") != plan.get("plan_sha256"):
        _fail("PRESCREEN_FORM_PLAN_HASH_MISMATCH")
    prohibited = form.get("prohibited_assignments", {})
    if any(
        prohibited.get(key) is not False
        for key in ("necessity_assigned", "h1_assigned", "h2_assigned")
    ):
        _fail("PRESCREEN_FORBIDDEN_ASSIGNMENT_PRESENT")
    if report.get("record_type") != "semantic_av_source_prescreen_import":
        _fail("PRESCREEN_REPORT_TYPE_INVALID")
    if report.get("completion_status") != "valid":
        _fail("PRESCREEN_IMPORT_NOT_VALID")
    if report.get("readiness_token") != PRESCREEN_READY:
        _fail("PRESCREEN_IMPORT_NOT_READY")
    if report.get("plan_id") != plan.get("plan_id"):
        _fail("PRESCREEN_REPORT_PLAN_ID_MISMATCH")
    if report.get("form_id") != form.get("form_id"):
        _fail("PRESCREEN_REPORT_FORM_ID_MISMATCH")
    if report.get("errors"):
        _fail("PRESCREEN_REPORT_HAS_ERRORS")
    if any(
        report.get(key) is not False
        for key in ("necessity_assigned", "h1_assigned", "h2_assigned")
    ):
        _fail("PRESCREEN_REPORT_FORBIDDEN_ASSIGNMENT_PRESENT")


def _validate_schema(
    root: Path, value: Mapping[str, Any], schema_name: str, label: str
) -> None:
    schema_path = root / "docs/spec" / schema_name
    schema = _read_json(schema_path, f"{label}_SCHEMA_INVALID")
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        location = ".".join(str(item) for item in errors[0].absolute_path) or "$"
        _fail(f"{label}_SCHEMA_VALIDATION_FAILED", f"{location}:{errors[0].message}")


def load_human_complete_prescreen(
    repo_root: str | Path,
    *,
    plan_path: str | Path,
    form_path: str | Path,
    report_path: str | Path,
    source_groups: Mapping[str, str],
) -> PrescreenBundle:
    """Load a completed Task-153 prescreen without treating it as H-tier."""
    root = Path(repo_root).resolve()
    paths = {
        "plan": _repo_path(root, plan_path, allow_prescreen_annotation=True),
        "form": _repo_path(root, form_path, allow_prescreen_annotation=True),
        "report": _repo_path(root, report_path, allow_prescreen_annotation=True),
    }
    plan = _read_json(paths["plan"], "PRESCREEN_PLAN_INVALID")
    form = _read_json(paths["form"], "PRESCREEN_FORM_INVALID")
    report = _read_json(paths["report"], "PRESCREEN_REPORT_INVALID")
    _validate_schema(
        root,
        plan,
        "semantic_av_source_prescreen_plan_schema.json",
        "PRESCREEN_PLAN",
    )
    _validate_schema(
        root,
        form,
        "semantic_av_source_prescreen_annotation_schema.json",
        "PRESCREEN_FORM",
    )
    _validate_schema(
        root,
        report,
        "semantic_av_source_prescreen_import_schema.json",
        "PRESCREEN_REPORT",
    )
    _required_completed_prescreen(plan, form, report)

    samples = {
        str(item["sample_id"]): item for item in plan.get("samples", ())
    }
    report_results = {
        str(item["source_id"]): item for item in report.get("source_results", ())
    }
    reviews = {
        str(item["source_id"]): item for item in form.get("source_reviews", ())
    }
    if {samples_item["source_id"] for samples_item in samples.values()} != set(
        source_groups
    ):
        _fail("PRESCREEN_PLAN_SOURCE_SET_MISMATCH")
    if set(report_results) != set(source_groups) or set(reviews) != set(source_groups):
        _fail("PRESCREEN_SOURCE_SET_MISMATCH")

    source_gates: dict[str, PrescreenSourceGate] = {}
    for source_id, source_group_id in source_groups.items():
        result = report_results[source_id]
        review = reviews[source_id]
        if result.get("source_group_id") != source_group_id:
            _fail("PRESCREEN_REPORT_SOURCE_GROUP_MISMATCH", source_id)
        if review.get("source_group_id") != source_group_id:
            _fail("PRESCREEN_FORM_SOURCE_GROUP_MISMATCH", source_id)
        if (
            result.get("authoring_eligibility") != "pass"
            or result.get("readiness_token") != PRESCREEN_READY
            or result.get("exposure_recorded") is not True
            or result.get("errors")
        ):
            _fail("PRESCREEN_SOURCE_NOT_HUMAN_COMPLETE_PASS", source_id)
        sample_reviews = list(review.get("sample_reviews", ()))
        candidate_facts = list(review.get("candidate_facts", ()))
        expected_sample_ids = [
            str(item["sample_id"])
            for item in plan.get("samples", ())
            if item.get("source_id") == source_id
        ]
        actual_sample_ids = [
            str(item.get("sample_id")) for item in sample_reviews
        ]
        if actual_sample_ids != expected_sample_ids:
            _fail("PRESCREEN_SAMPLE_SET_OR_ORDER_MISMATCH", source_id)
        if review.get("authoring_eligibility") != "pass":
            _fail("PRESCREEN_FORM_SOURCE_NOT_PASS", source_id)
        if not candidate_facts:
            _fail("PRESCREEN_PASS_REQUIRES_CANDIDATE_FACT", source_id)
        if any(
            item.get("review_status") != "reviewed" for item in sample_reviews
        ):
            _fail("PRESCREEN_INTERVAL_NOT_REVIEWED", source_id)
        if any(
            item.get("speech_presence") == "unknown"
            or any(
                risk.get("level") == "unknown"
                for risk in item.get("substitution_risk", {}).values()
            )
            for item in sample_reviews
        ):
            _fail("PRESCREEN_SEMANTIC_FIELD_UNRESOLVED", source_id)
        if review.get("temporal_recurrence", {}).get("assessment_status") != (
            "complete"
        ):
            _fail("PRESCREEN_RECURRENCE_NOT_COMPLETE", source_id)
        if any(
            review.get(field, {}).get("assessment_status") == "not_assessed"
            for field in ("privacy_review", "safety_review")
        ):
            _fail("PRESCREEN_PRIVACY_OR_SAFETY_NOT_ASSESSED", source_id)
        expected_counts = {
            "sample_count": len(sample_reviews),
            "candidate_fact_count": len(candidate_facts),
            "dynamic_visual_event_count": sum(
                len(item.get("dynamic_non_text_visual_events", ()))
                for item in sample_reviews
            ),
            "concrete_non_speech_audio_event_count": sum(
                len(item.get("concrete_non_speech_audio_events", ()))
                for item in sample_reviews
            ),
            "speech_present_sample_count": sum(
                item.get("speech_presence") == "present"
                for item in sample_reviews
            ),
        }
        if any(result.get(key) != value for key, value in expected_counts.items()):
            _fail("PRESCREEN_REPORT_COUNT_MISMATCH", source_id)
        observations: list[HumanObservation] = []
        for sample_review in sample_reviews:
            sample = samples.get(str(sample_review.get("sample_id")))
            if sample is None or sample.get("source_id") != source_id:
                _fail("PRESCREEN_SAMPLE_BINDING_INVALID", source_id)
            sample_start_us = round(float(sample["start_s"]) * 1_000_000)
            for field, modality in (
                ("dynamic_non_text_visual_events", "dynamic_nontext_visual"),
                ("concrete_non_speech_audio_events", "non_speech"),
            ):
                for event in sample_review.get(field, ()):
                    start_us = sample_start_us + round(
                        float(event["start_offset_s"]) * 1_000_000
                    )
                    end_us = sample_start_us + round(
                        float(event["end_offset_s"]) * 1_000_000
                    )
                    if end_us <= start_us:
                        _fail("PRESCREEN_EVENT_INTERVAL_INVALID", source_id)
                    observations.append(
                        HumanObservation(
                            observation_id=str(event["observation_id"]),
                            modality=modality,
                            start_us=start_us,
                            end_us=end_us,
                            candidate_fact_ids=tuple(
                                str(item)
                                for item in event.get("candidate_fact_ids", ())
                            ),
                        )
                    )
        source_gates[source_id] = PrescreenSourceGate(
            source_id=source_id,
            source_group_id=source_group_id,
            authoring_eligibility="pass",
            observations=tuple(observations),
            candidate_facts=tuple(dict(item) for item in candidate_facts),
            recurrence_groups=tuple(
                dict(item)
                for item in review.get("temporal_recurrence", {}).get(
                    "groups", ()
                )
            ),
            authoring_constraints=tuple(
                str(item) for item in review.get("authoring_constraints", ())
            ),
        )
    return PrescreenBundle(
        sources=source_gates,
        provenance={
            "plan_path": paths["plan"].relative_to(root).as_posix(),
            "plan_sha256": _sha256(paths["plan"]),
            "form_path": paths["form"].relative_to(root).as_posix(),
            "form_sha256": _sha256(paths["form"]),
            "report_path": paths["report"].relative_to(root).as_posix(),
            "report_sha256": _sha256(paths["report"]),
            "human_complete": True,
            "h1_assigned": False,
            "h2_assigned": False,
        },
    )


__all__ = [
    "CANONICAL_ARTIFACTS",
    "EXPECTED_SOURCE_GROUPS",
    "EXPECTED_SOURCE_IDS",
    "EpicFamilyInputError",
    "EpicIndexInputs",
    "HumanObservation",
    "PrescreenBundle",
    "PrescreenSourceGate",
    "load_canonical_epic_index",
    "load_human_complete_prescreen",
]
