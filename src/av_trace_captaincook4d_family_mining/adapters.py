"""Fail-closed adapters for Task189 and Task153 CaptainCook4D inputs."""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .contracts import EXPECTED_SOURCE_GROUPS, EXPECTED_SOURCE_IDS, json_hash

CANONICAL_INDEX_ROOT = Path("data/restricted/captaincook4d_wave0_index_v1")
CANONICAL_INDEX_PLAN = Path(
    "data/rehearsal_plan/captaincook4d_wave0_full_timeline_index_v1.json"
)
TASK189_RESULT = Path(
    "orchestration/results/189_captaincook4d_wave0_full_timeline.txt"
)
REQUIRED_TASK189_TOKEN = "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY"
CANONICAL_ARTIFACTS = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "build_manifest.json",
)
EXPECTED_INDEX_SCHEMA = "av-trace.captaincook4d-wave0-index/1.0"
EXPECTED_INDEX_VERSION = "captaincook4d-wave0-full-timeline-index/1.0"
EXPECTED_STAGE = "RESTRICTED_CAPTAINCOOK4D_WAVE0_SOURCE_DERIVED_INDEX"
PRESCREEN_READY = "SEMANTIC_AV_SOURCE_PRESCREEN_READY"

_FORBIDDEN_SEMANTIC_KEYS = {
    "action",
    "actions",
    "action_annotation",
    "action_annotations",
    "action_class",
    "action_label",
    "step",
    "steps",
    "step_annotation",
    "step_annotations",
    "task_graph",
    "task_graphs",
    "procedure_graph",
    "recipe",
    "recipe_id",
    "recipe_label",
    "error",
    "errors",
    "error_annotation",
    "error_annotations",
    "mistake",
    "mistakes",
    "benchmark_label",
    "benchmark_split",
}
_FORBIDDEN_PATH_FRAGMENTS = (
    "annotation_vault",
    "annotations",
    "task_graph",
    "task-graph",
    "error_labels",
    "recipe_labels",
)


class CaptainCook4DFamilyInputError(RuntimeError):
    """A prerequisite cannot safely support CaptainCook4D mining."""


@dataclass(frozen=True)
class CaptainCook4DIndexInputs:
    """Normalized canonical Task189 observations."""

    index: Mapping[str, Any]
    segment_manifest: Mapping[str, Any]
    observation_manifest: Mapping[str, Any]
    routing_records: tuple[Mapping[str, Any], ...]
    source_hashes: Mapping[str, str]
    source_groups: Mapping[str, str]
    source_media_paths: Mapping[str, Path]
    source_durations_s: Mapping[str, float]
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class HumanObservation:
    """One completed Task153 visual or non-speech source observation."""

    observation_id: str
    modality: str
    start_us: int
    end_us: int
    candidate_fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class PrescreenSourceGate:
    """One completed human source-authoring gate."""

    source_id: str
    source_group_id: str
    observations: tuple[HumanObservation, ...]
    candidate_facts: tuple[Mapping[str, Any], ...]
    recurrence_groups: tuple[Mapping[str, Any], ...]
    authoring_constraints: tuple[str, ...]


@dataclass(frozen=True)
class PrescreenBundle:
    """Completed Task153 artifacts for all three sources."""

    sources: Mapping[str, PrescreenSourceGate]
    provenance: Mapping[str, Any]


def _fail(code: str, detail: str = "") -> None:
    raise CaptainCook4DFamilyInputError(
        f"{code}:{detail}" if detail else code
    )


def _read_json(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        _fail(code, path.as_posix())
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptainCook4DFamilyInputError(
            f"{code}:{path.as_posix()}"
        ) from exc
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
    allow_task153_annotation: bool = False,
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
    forbidden = tuple(
        fragment
        for fragment in _FORBIDDEN_PATH_FRAGMENTS
        if not allow_task153_annotation or fragment != "annotations"
    )
    if any(fragment in lowered for fragment in forbidden):
        _fail("SEMANTIC_ANNOTATION_PATH_FORBIDDEN", raw.as_posix())
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


def _verify_mode(path: Path, expected: int, code: str) -> None:
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != expected:
        _fail(code, path.as_posix())


def _scan_forbidden_semantic_keys(
    value: Any,
    location: str = "index",
    *,
    parent_key: str | None = None,
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            folded = str(key).casefold()
            if (
                parent_key not in {"term_frequency", "document_frequency"}
                and folded in _FORBIDDEN_SEMANTIC_KEYS
            ):
                _fail(
                    "SEALED_CAPTAINCOOK4D_SEMANTIC_FIELD_PRESENT",
                    f"{location}.{key}",
                )
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


def _require_task189_ready(root: Path, result_path: str | Path) -> Path:
    path = _repo_path(root, result_path)
    if not path.is_file():
        _fail("TASK189_READY_RESULT_MISSING", path.relative_to(root).as_posix())
    text = path.read_text(encoding="utf-8")
    final_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() == REQUIRED_TASK189_TOKEN
        or line.strip() == f"FINAL {REQUIRED_TASK189_TOKEN}"
        or line.strip() == f"FINAL: {REQUIRED_TASK189_TOKEN}"
    ]
    if not final_lines:
        _fail("TASK189_READY_TOKEN_MISSING")
    return path


def load_canonical_captaincook4d_index(
    repo_root: str | Path,
    *,
    index_root: str | Path = CANONICAL_INDEX_ROOT,
    plan_path: str | Path = CANONICAL_INDEX_PLAN,
    task189_result_path: str | Path = TASK189_RESULT,
) -> CaptainCook4DIndexInputs:
    """Load only the complete canonical index after Task189 READY."""
    root = Path(repo_root).resolve()
    ready_path = _require_task189_ready(root, task189_result_path)
    output = _repo_path(root, index_root)
    missing = [name for name in CANONICAL_ARTIFACTS if not (output / name).is_file()]
    if missing:
        _fail(
            "CAPTAINCOOK4D_CANONICAL_INDEX_INCOMPLETE_MISSING",
            ",".join(sorted(missing)),
        )
    _verify_mode(output, 0o700, "CAPTAINCOOK4D_INDEX_ROOT_MODE_INVALID")
    documents = {
        name: _read_json(
            output / name, f"CAPTAINCOOK4D_INDEX_ARTIFACT_INVALID:{name}"
        )
        for name in CANONICAL_ARTIFACTS
    }
    build = documents["build_manifest.json"]
    if build.get("status") != "COMPLETE":
        _fail("CAPTAINCOOK4D_CANONICAL_INDEX_BUILD_NOT_COMPLETE")
    if build.get("mode") != "full" or build.get("smoke_seconds") is not None:
        _fail("CAPTAINCOOK4D_SMOKE_INDEX_FORBIDDEN")
    if build.get("source_count") != 3 or build.get("expected_source_count") != 3:
        _fail("CAPTAINCOOK4D_SOURCE_COUNT_MUST_BE_THREE")
    if build.get("output_dir") != output.relative_to(root).as_posix():
        _fail("CAPTAINCOOK4D_OUTPUT_BINDING_MISMATCH")
    boundary = build.get("terminal_boundary", {})
    for key in (
        "semantic_annotations_generated",
        "families_generated",
        "interventions_generated",
        "trajectories_generated",
        "evaluation_generated",
        "media_derivatives_generated",
    ):
        if boundary.get(key) is not False:
            _fail("CAPTAINCOOK4D_TERMINAL_BOUNDARY_INVALID", key)
    if not _self_hash(build, "build_manifest_hash"):
        _fail("CAPTAINCOOK4D_BUILD_MANIFEST_SELF_HASH_INVALID")
    inventory = _inventory(build)
    for name in CANONICAL_ARTIFACTS[:-1]:
        path = output / name
        _verify_mode(path, 0o600, "CAPTAINCOOK4D_INDEX_ARTIFACT_MODE_INVALID")
        relative = path.relative_to(root).as_posix()
        record = inventory.get(relative)
        if record is None:
            _fail("CAPTAINCOOK4D_ARTIFACT_NOT_FROZEN", name)
        if record.get("sha256") != _sha256(path):
            _fail("CAPTAINCOOK4D_ARTIFACT_HASH_MISMATCH", name)
        if record.get("size_bytes") != path.stat().st_size:
            _fail("CAPTAINCOOK4D_ARTIFACT_SIZE_MISMATCH", name)
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
            _fail("CAPTAINCOOK4D_INDEX_SCHEMA_MISMATCH", key)
        if document.get("stage") != EXPECTED_STAGE:
            _fail("CAPTAINCOOK4D_INDEX_STAGE_MISMATCH", key)
        if not _self_hash(document, key):
            _fail("CAPTAINCOOK4D_INDEX_SELF_HASH_INVALID", key)
    if index.get("index_version") != EXPECTED_INDEX_VERSION:
        _fail("CAPTAINCOOK4D_INDEX_VERSION_MISMATCH")
    if observation.get("all_sources_complete") is not True:
        _fail("CAPTAINCOOK4D_OBSERVATIONS_INCOMPLETE")
    complete = tuple(sorted(observation.get("complete_source_refs", ())))
    if complete != EXPECTED_SOURCE_IDS:
        _fail("CAPTAINCOOK4D_COMPLETE_SOURCE_SET_MISMATCH")
    source_hashes = dict(index.get("source_hashes", {}))
    if tuple(sorted(source_hashes)) != EXPECTED_SOURCE_IDS:
        _fail("CAPTAINCOOK4D_INDEX_SOURCE_SET_MISMATCH")
    if build.get("source_sha256") != source_hashes:
        _fail("CAPTAINCOOK4D_BUILD_SOURCE_HASH_BINDING_MISMATCH")
    if index.get("segment_manifest_hash") != segment.get("segment_manifest_hash"):
        _fail("CAPTAINCOOK4D_INDEX_SEGMENT_BINDING_MISMATCH")
    if index.get("observation_manifest_hash") != observation.get(
        "observation_manifest_hash"
    ):
        _fail("CAPTAINCOOK4D_INDEX_OBSERVATION_BINDING_MISMATCH")
    plan_file = _repo_path(root, plan_path)
    plan = _read_json(plan_file, "CAPTAINCOOK4D_INDEX_PLAN_INVALID")
    if build.get("plan_path") != plan_file.relative_to(root).as_posix():
        _fail("CAPTAINCOOK4D_INDEX_PLAN_PATH_BINDING_MISMATCH")
    if build.get("plan_sha256") != _sha256(plan_file, prefixed=False):
        _fail("CAPTAINCOOK4D_INDEX_PLAN_HASH_BINDING_MISMATCH")
    source_groups = {
        str(item["source_id"]): str(item["source_group_id"])
        for item in plan.get("sources", ())
    }
    if source_groups != EXPECTED_SOURCE_GROUPS:
        _fail("CAPTAINCOOK4D_SOURCE_GROUP_BINDING_MISMATCH")
    media_paths = {
        str(item["source_id"]): _repo_path(root, str(item["media_path"]))
        for item in plan.get("sources", ())
    }
    durations = {
        str(item["source_id"]): float(item["official_duration_seconds"])
        for item in plan.get("sources", ())
    }
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
            _fail("CAPTAINCOOK4D_INDEX_COUNT_MISMATCH", key)
    if int(expected_totals.get("whisper_chunks", -1)) != int(
        observation.get("counts", {}).get("whisper_chunks", -2)
    ):
        _fail("CAPTAINCOOK4D_INDEX_COUNT_MISMATCH", "whisper_chunks")
    checkpoints = list(observation.get("checkpoints", ()))
    if len(checkpoints) != int(expected_totals.get("checkpoint_count", -1)):
        _fail("CAPTAINCOOK4D_INDEX_COUNT_MISMATCH", "checkpoint_count")
    routing_records: list[Mapping[str, Any]] = []
    for checkpoint in checkpoints:
        checkpoint_path = _repo_path(root, str(checkpoint.get("path", "")))
        _verify_mode(
            checkpoint_path,
            0o600,
            "CAPTAINCOOK4D_CHECKPOINT_MODE_INVALID",
        )
        if checkpoint.get("sha256") != _sha256(checkpoint_path):
            _fail("CAPTAINCOOK4D_CHECKPOINT_HASH_MISMATCH")
        if checkpoint.get("size_bytes") != checkpoint_path.stat().st_size:
            _fail("CAPTAINCOOK4D_CHECKPOINT_SIZE_MISMATCH")
        if checkpoint_path.name == "vision_routing.json":
            payload = _read_json(
                checkpoint_path, "CAPTAINCOOK4D_ROUTING_CHECKPOINT_INVALID"
            )
            if payload.get("semantic_claim_allowed") is not False:
                _fail("CAPTAINCOOK4D_ROUTING_SEMANTIC_FLAG_INVALID")
            routing_records.extend(
                dict(item) for item in payload.get("records", ())
            )
    _scan_forbidden_semantic_keys(index)
    policy = index.get("searchable_field_policy", {})
    if policy.get("evaluator_annotations_excluded") is not True:
        _fail("CAPTAINCOOK4D_EVALUATOR_EXCLUSION_MISSING")
    if policy.get("rights_metadata_excluded") is not True:
        _fail("CAPTAINCOOK4D_RIGHTS_EXCLUSION_MISSING")
    return CaptainCook4DIndexInputs(
        index=index,
        segment_manifest=segment,
        observation_manifest=observation,
        routing_records=tuple(routing_records),
        source_hashes=source_hashes,
        source_groups=source_groups,
        source_media_paths=media_paths,
        source_durations_s=durations,
        provenance={
            "adapter": "canonical_captaincook4d_wave0_full_timeline_v1",
            "task189_result_path": ready_path.relative_to(root).as_posix(),
            "task189_result_sha256": _sha256(ready_path),
            "task189_ready_token": REQUIRED_TASK189_TOKEN,
            "index_root": output.relative_to(root).as_posix(),
            "build_manifest_hash": build["build_manifest_hash"],
            "index_hash": index["index_hash"],
            "semantic_captaincook_annotations_accessed": False,
            "task_graphs_accessed": False,
            "error_labels_accessed": False,
            "complete_non_smoke_index_required": True,
        },
    )


def _validate_schema(root: Path, value: Mapping[str, Any], schema_path: str) -> None:
    schema_file = _repo_path(root, schema_path, allow_task153_annotation=True)
    schema = _read_json(schema_file, "PRESCREEN_SCHEMA_INVALID")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if errors:
        _fail("PRESCREEN_SCHEMA_VALIDATION_FAILED", errors[0].message)


def load_human_complete_prescreen(
    repo_root: str | Path,
    *,
    plan_path: str | Path,
    form_path: str | Path,
    report_path: str | Path,
    source_groups: Mapping[str, str],
) -> PrescreenBundle:
    """Load completed Task153 artifacts and require all sources to pass."""
    root = Path(repo_root).resolve()
    paths = {
        "plan": _repo_path(root, plan_path, allow_task153_annotation=True),
        "form": _repo_path(root, form_path, allow_task153_annotation=True),
        "report": _repo_path(root, report_path, allow_task153_annotation=True),
    }
    plan = _read_json(paths["plan"], "PRESCREEN_PLAN_INVALID")
    form = _read_json(paths["form"], "PRESCREEN_FORM_INVALID")
    report = _read_json(paths["report"], "PRESCREEN_REPORT_INVALID")
    _validate_schema(
        root, plan, "docs/spec/semantic_av_source_prescreen_plan_schema.json"
    )
    _validate_schema(
        root, form, "docs/spec/semantic_av_source_prescreen_annotation_schema.json"
    )
    _validate_schema(
        root, report, "docs/spec/semantic_av_source_prescreen_import_schema.json"
    )
    if plan.get("semantic_labels_present") is not False:
        _fail("PRESCREEN_PLAN_MUST_BE_NONSEMANTIC")
    if form.get("plan_id") != plan.get("plan_id"):
        _fail("PRESCREEN_FORM_PLAN_ID_MISMATCH")
    if form.get("plan_sha256") != _sha256(paths["plan"]):
        _fail("PRESCREEN_FORM_PLAN_HASH_MISMATCH")
    if report.get("plan_id") != plan.get("plan_id"):
        _fail("PRESCREEN_REPORT_PLAN_ID_MISMATCH")
    if report.get("form_id") != form.get("form_id"):
        _fail("PRESCREEN_REPORT_FORM_ID_MISMATCH")
    if report.get("readiness_token") != PRESCREEN_READY:
        _fail("PRESCREEN_REPORT_NOT_READY")
    if report.get("necessity_assigned") is not False:
        _fail("PRESCREEN_NECESSITY_FORBIDDEN")
    if report.get("h1_assigned") is not False or report.get("h2_assigned") is not False:
        _fail("PRESCREEN_H_TIER_FORBIDDEN")
    if form.get("completion_status") != "complete":
        _fail("PRESCREEN_FORM_NOT_COMPLETE")
    reviewer = form.get("reviewer", {})
    if reviewer.get("training_attested") is not True:
        _fail("PRESCREEN_REVIEWER_NOT_TRAINED")
    samples = {
        str(item["sample_id"]): item for item in plan.get("samples", ())
    }
    reviews = {
        str(item.get("source_id")): item
        for item in form.get("source_reviews", ())
        if isinstance(item, Mapping)
    }
    results = {
        str(item.get("source_id")): item
        for item in report.get("source_results", ())
        if isinstance(item, Mapping)
    }
    if set(reviews) != set(EXPECTED_SOURCE_IDS) or set(results) != set(
        EXPECTED_SOURCE_IDS
    ):
        _fail("PRESCREEN_SOURCE_SET_MISMATCH")
    source_gates: dict[str, PrescreenSourceGate] = {}
    for source_id in EXPECTED_SOURCE_IDS:
        group_id = source_groups[source_id]
        review = reviews[source_id]
        result = results[source_id]
        if review.get("source_group_id") != group_id:
            _fail("PRESCREEN_FORM_SOURCE_GROUP_MISMATCH", source_id)
        if result.get("source_group_id") != group_id:
            _fail("PRESCREEN_REPORT_SOURCE_GROUP_MISMATCH", source_id)
        if (
            review.get("authoring_eligibility") != "pass"
            or result.get("authoring_eligibility") != "pass"
            or result.get("readiness_token") != PRESCREEN_READY
            or result.get("exposure_recorded") is not True
            or result.get("errors")
        ):
            _fail("PRESCREEN_SOURCE_NOT_HUMAN_COMPLETE_PASS", source_id)
        sample_reviews = list(review.get("sample_reviews", ()))
        expected_sample_ids = [
            str(item["sample_id"])
            for item in plan.get("samples", ())
            if item.get("source_id") == source_id
        ]
        if [str(item.get("sample_id")) for item in sample_reviews] != (
            expected_sample_ids
        ):
            _fail("PRESCREEN_SAMPLE_SET_OR_ORDER_MISMATCH", source_id)
        candidate_facts = list(review.get("candidate_facts", ()))
        if not candidate_facts:
            _fail("PRESCREEN_PASS_REQUIRES_CANDIDATE_FACT", source_id)
        observations: list[HumanObservation] = []
        for sample_review in sample_reviews:
            if sample_review.get("review_status") != "reviewed":
                _fail("PRESCREEN_INTERVAL_NOT_REVIEWED", source_id)
            sample = samples.get(str(sample_review.get("sample_id")))
            if sample is None:
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
            source_group_id=group_id,
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
            "necessity_assigned": False,
        },
    )


__all__ = [
    "CANONICAL_ARTIFACTS",
    "CANONICAL_INDEX_PLAN",
    "CANONICAL_INDEX_ROOT",
    "REQUIRED_TASK189_TOKEN",
    "TASK189_RESULT",
    "CaptainCook4DFamilyInputError",
    "CaptainCook4DIndexInputs",
    "HumanObservation",
    "PrescreenBundle",
    "PrescreenSourceGate",
    "load_canonical_captaincook4d_index",
    "load_human_complete_prescreen",
]
