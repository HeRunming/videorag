#!/usr/bin/env python3
"""Fail-closed checkpoint orchestration for the P23_102 post-acquisition chain.

This tool never starts or resumes acquisition.  It waits for complete parallel
coverage, delegates assembly/exact validation to the existing acquisition
tool, builds and independently verifies the full timeline, mines only the
machine-provisional registry, and finally audits (but does not execute) the
development-rehearsal prerequisites.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Self

READY_TOKEN = "P23_102_POST_ACQUISITION_ORCHESTRATOR_READY"
SCHEMA_VERSION = "av-trace.p23-102-post-acquisition-orchestrator/1.0"
RECEIPT_SCHEMA_VERSION = (
    "av-trace.p23-102-post-acquisition-stage-receipt/1.0"
)
ATTEMPT_SCHEMA_VERSION = (
    "av-trace.p23-102-post-acquisition-stage-attempt/1.0"
)
READINESS_SCHEMA_VERSION = (
    "av-trace.p23-102-rehearsal-readiness-validation/3.0"
)
READINESS_REPAIR_TOKEN = (
    "P23_102_HISTORICAL_REHEARSAL_SUPERSEDED_READY"
)
HISTORICAL_SUPERSEDED_STATUS = "SUPERSEDED_CODE_DRIFT_FAIL_CLOSED"

ASSET_ID = "P23_102"
EXPECTED_BYTES = 10_814_161_307
OFFICIAL_MD5 = "4698fcbf13782f6396029761eb3bd5f2"
EXACT_READY = "COMPLETE_VERIFIED_READY"
TIMELINE_READY = "EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY"
TIMELINE_SCHEMA_VERSION = "av-trace.epic-p23-102-full-timeline/1.0"
TIMELINE_STAGE = "RESTRICTED_DEVELOPMENT_ONLY_SOURCE_DERIVED_INDEX"
FAMILY_READY = (
    "EPIC_P23_102_FAMILY_MINING_MACHINE_PROVISIONAL_COMPLETE"
)
MACHINE_BUNDLE_READY = "P23_102_MACHINE_PROVISIONAL_BUNDLE_READY"
MACHINE_BUNDLE_CLASSIFICATION = (
    "DEVELOPMENT_ONLY_MACHINE_PROVISIONAL_NOT_HUMAN_VALIDATED"
)
MACHINE_BUNDLE_ROOT = (
    "data/restricted/epic_p23_102_machine_provisional_families_v1"
)
ADAPTER_ATTESTATION_PATH = (
    "data/restricted/p23_102_acquire_ground_act_rehearsal_v1/"
    "adapter_attestation.json"
)
REHEARSAL_RUNNER_PATH = (
    "scripts/run_p23_102_acquire_ground_act_rehearsal.py"
)
CONTROLLER_PATH = "src/av_trace_scale1b_agent/controller.py"
PROCESS_PATH = "src/av_trace_scale1b_agent/process.py"
TECHNICAL_SMOKE_V2_FREEZE_PATH = (
    "data/rehearsal_plan/p23_102_technical_smoke_v2.json"
)
TECHNICAL_SMOKE_V2_ATTESTATION_PATH = (
    "data/restricted/p23_102_technical_smoke_v2/"
    "adapter_attestation.json"
)
TECHNICAL_SMOKE_V2_RUNNER_PATH = (
    "scripts/run_p23_102_technical_smoke_v2.py"
)
TECHNICAL_SMOKE_V2_FREEZE_ID = "P23_102_TECHNICAL_SMOKE_V2"
MACHINE_BUNDLE_SPECS = {
    "family_registry.json": (
        "av-trace.p23-102-machine-provisional-family-registry/1.0",
        "MACHINE_PROVISIONAL_FROZEN",
    ),
    "evidence_registry.json": (
        "av-trace.p23-102-machine-provisional-evidence-registry/1.0",
        "MACHINE_PROVISIONAL_EVIDENCE_FROZEN",
    ),
    "intervention_manifest.json": (
        "av-trace.p23-102-machine-provisional-interventions/1.0",
        "MECHANISM_SPECIFIC_FROZEN",
    ),
    "state_surface_manifest.json": (
        "av-trace.p23-102-machine-provisional-state-surfaces/1.0",
        "FROZEN",
    ),
    "source_split_manifest.json": (
        "av-trace.p23-102-machine-provisional-source-split/1.0",
        "P23_DEVELOPMENT_ONLY_SOURCE_DISJOINT_FROM_EVALUATION",
    ),
    "leakage_gate.json": (
        "av-trace.p23-102-machine-provisional-leakage-gate/1.0",
        "PASS",
    ),
}
TIMELINE_VERIFIER_RECEIPT = "verify_full_timeline.json"

STAGE_NAMES = (
    "assemble_exact",
    "build_full_timeline",
    "verify_full_timeline",
    "mine_machine_provisional_registry",
    "validate_rehearsal_prerequisites",
)

HASH_BLOCK_BYTES = 16 * 1024 * 1024
STDIO_TAIL_CHARS = 4000


class OrchestrationError(RuntimeError):
    """Base fail-closed orchestration error."""


class ActiveAcquisitionError(OrchestrationError):
    """Acquisition or its supervising tmux process is still active."""


class PrerequisiteError(OrchestrationError):
    """A stage prerequisite is absent, incomplete, or invalid."""


class OutputValidationError(OrchestrationError):
    """A stage output is absent, unsafe, or semantically invalid."""


class StaleReceiptError(OrchestrationError):
    """A receipt exists but no longer binds the command, inputs, or outputs."""


class CommandFailure(OrchestrationError):
    """A delegated command returned nonzero."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def object_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def seal(document: dict[str, Any], field: str) -> dict[str, Any]:
    document[field] = object_hash(document)
    return document


def verify_seal(
    document: Mapping[str, Any], field: str, *, label: str
) -> None:
    body = {key: value for key, value in document.items() if key != field}
    if document.get(field) != object_hash(body):
        raise OutputValidationError(f"{label}_{field.upper()}_MISMATCH")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(HASH_BLOCK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        mode,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_json(path: Path, value: Any) -> None:
    atomic_write(path, canonical_json_bytes(value))


def load_json(path: Path, *, label: str) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise OutputValidationError(f"{label}_UNREADABLE:{path}") from exc


def relative(root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError as exc:
        raise OrchestrationError(f"PATH_OUTSIDE_REPOSITORY:{path}") from exc


def safe_repo_path(root: Path, value: str | Path, *, label: str) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        path = raw
    else:
        pure = PurePosixPath(str(raw))
        if ".." in pure.parts:
            raise OrchestrationError(f"{label}_UNSAFE:{value}")
        path = root.joinpath(*pure.parts)
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise OrchestrationError(f"{label}_OUTSIDE_REPOSITORY:{value}") from exc
    if path.is_symlink():
        raise OrchestrationError(f"{label}_SYMLINK_FORBIDDEN:{value}")
    return path


@dataclass(frozen=True)
class Config:
    root: Path
    python: str
    threads: int
    expected_bytes: int
    official_md5: str
    source_base: Path
    staging_dir: Path
    segment_dir: Path
    segment_manifest: Path
    part_media: Path
    final_media: Path
    canonical_acquisition_lock: Path
    parallel_acquisition_lock: Path
    state_dir: Path
    receipts_dir: Path
    attempts_dir: Path
    orchestrator_lock: Path
    exact_manifest: Path
    timeline_root: Path
    candidate_registry: Path
    readiness_report: Path
    rehearsal_plan: Path
    parallel_tool: Path
    exact_tool: Path
    build_tool: Path
    verify_tool: Path
    family_tool: Path
    timeline_plan: Path
    family_plan: Path


def default_config(
    root: str | Path,
    *,
    state_dir: str | Path | None = None,
    threads: int = 8,
) -> Config:
    repository = Path(root).resolve()
    source_base = (
        repository / "data/restricted/epic_p23_102_source_v1"
    )
    staging = source_base / "staging"
    state = (
        safe_repo_path(repository, state_dir, label="STATE_DIR")
        if state_dir is not None
        else source_base / "post_acquisition_orchestrator_v1"
    )
    timeline = (
        repository
        / "data/restricted/epic_p23_102_full_timeline_index_v1"
    )
    return Config(
        root=repository,
        python=sys.executable,
        threads=threads,
        expected_bytes=EXPECTED_BYTES,
        official_md5=OFFICIAL_MD5,
        source_base=source_base,
        staging_dir=staging,
        segment_dir=staging / "parallel_segments",
        segment_manifest=staging / "parallel_segments/manifest.json",
        part_media=staging / "P23_102.MP4.part",
        final_media=source_base / "media/P23/P23_102.MP4",
        canonical_acquisition_lock=staging / ".acquisition.lock",
        parallel_acquisition_lock=staging / ".parallel_acquisition.lock",
        state_dir=state,
        receipts_dir=state / "receipts",
        attempts_dir=state / "attempts",
        orchestrator_lock=state / ".orchestrator.lock",
        exact_manifest=(
            source_base
            / "manifests/epic_p23_102_exact_manifest.json"
        ),
        timeline_root=timeline,
        candidate_registry=(
            repository
            / "data/restricted/epic_p23_102_family_mining_v1_dev"
            / "candidate_registry.json"
        ),
        readiness_report=state / "rehearsal_readiness.json",
        rehearsal_plan=(
            repository
            / "data/rehearsal_plan"
            / "p23_102_acquire_ground_act_rehearsal_v1.json"
        ),
        parallel_tool=(
            repository / "tools/epic_p23_102_parallel_acquisition.py"
        ),
        exact_tool=(
            repository / "tools/epic_p23_102_exact_acquisition.py"
        ),
        build_tool=(
            repository / "scripts/build_epic_p23_102_full_timeline.py"
        ),
        verify_tool=(
            repository / "scripts/verify_epic_p23_102_full_timeline.py"
        ),
        family_tool=(
            repository / "tools/epic_p23_102_family_mining_v1.py"
        ),
        timeline_plan=(
            repository
            / "data/rehearsal_plan"
            / "epic_p23_102_full_timeline_index_v1.json"
        ),
        family_plan=(
            repository
            / "data/rehearsal_plan/epic_p23_102_family_mining_v1.json"
        ),
    )


class ExclusiveLock:
    """Nonblocking advisory lock used only by mutating orchestration modes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.descriptor: int | None = None

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise OrchestrationError(
                f"ORCHESTRATOR_LOCKED:{self.path}"
            ) from exc
        payload = canonical_json_bytes(
            {"pid": os.getpid(), "locked_at_utc": utc_now()}
        )
        os.ftruncate(descriptor, 0)
        os.write(descriptor, payload)
        os.fsync(descriptor)
        self.descriptor = descriptor
        return self

    def __exit__(self, *_args: object) -> None:
        if self.descriptor is not None:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            os.close(self.descriptor)
            self.descriptor = None


def advisory_lock_is_held(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        descriptor = os.open(path, os.O_RDWR)
    except OSError:
        return True
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return False
    finally:
        os.close(descriptor)


def acquisition_processes() -> list[dict[str, Any]]:
    """Return matching live processes without invoking ps or tmux."""
    matches: list[dict[str, Any]] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return matches
    own_pid = os.getpid()
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == own_pid:
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        command = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
        if not command:
            continue
        parallel = "epic_p23_102_parallel_acquisition.py" in command
        exact = "epic_p23_102_exact_acquisition.py" in command
        tmux_supervisor = (
            "avtrace_p23_acquire" in command
            or "tmux_parallel_acquire" in command
        )
        active_mode = any(
            flag in command
            for flag in ("--acquire", "--assemble", "--execute")
        )
        if (parallel or exact) and (active_mode or tmux_supervisor):
            matches.append(
                {
                    "pid": int(entry.name),
                    "kind": (
                        "tmux_or_shell_supervisor"
                        if tmux_supervisor and not command.startswith("python")
                        else "acquisition_process"
                    ),
                    "command_sha256": hashlib.sha256(
                        command.encode("utf-8")
                    ).hexdigest(),
                    "command_tail": command[-500:],
                }
            )
    return sorted(matches, key=lambda item: item["pid"])


def acquisition_activity(config: Config) -> dict[str, Any]:
    blockers: list[str] = []
    canonical_present = config.canonical_acquisition_lock.exists()
    if canonical_present:
        blockers.append(
            "CANONICAL_ACQUISITION_LOCK_PRESENT:"
            + relative(config.root, config.canonical_acquisition_lock)
        )
    parallel_held = advisory_lock_is_held(
        config.parallel_acquisition_lock
    )
    if parallel_held:
        blockers.append(
            "PARALLEL_ACQUISITION_LOCK_HELD:"
            + relative(config.root, config.parallel_acquisition_lock)
        )
    processes = acquisition_processes()
    if processes:
        blockers.append(
            "ACTIVE_ACQUISITION_OR_TMUX_PROCESSES:"
            + ",".join(str(item["pid"]) for item in processes)
        )
    return {
        "active": bool(blockers),
        "blockers": blockers,
        "canonical_lock_present": canonical_present,
        "parallel_lock_held": parallel_held,
        "matching_processes": processes,
    }


def require_no_acquisition_activity(config: Config) -> dict[str, Any]:
    activity = acquisition_activity(config)
    if activity["active"]:
        raise ActiveAcquisitionError(";".join(activity["blockers"]))
    return activity


def orchestrator_lock_is_held(config: Config) -> bool:
    return advisory_lock_is_held(config.orchestrator_lock)


def validate_parallel_segments_complete(config: Config) -> dict[str, Any]:
    """Cheap completeness gate; assembly performs full segment hashing."""
    if not config.segment_manifest.is_file():
        raise PrerequisiteError("PARALLEL_SEGMENT_MANIFEST_MISSING")
    manifest = load_json(
        config.segment_manifest, label="PARALLEL_SEGMENT_MANIFEST"
    )
    if not isinstance(manifest, Mapping):
        raise PrerequisiteError("PARALLEL_SEGMENT_MANIFEST_NOT_OBJECT")
    if (
        manifest.get("asset_id") != ASSET_ID
        or manifest.get("expected_bytes") != config.expected_bytes
        or manifest.get("official_md5") != config.official_md5
    ):
        raise PrerequisiteError(
            "PARALLEL_SEGMENT_MANIFEST_IDENTITY_MISMATCH"
        )
    if config.final_media.exists():
        raise PrerequisiteError(
            "FINAL_MEDIA_EXISTS_WITHOUT_VALID_EXACT_OUTPUT_ADOPTION"
        )
    prefix = config.part_media.stat().st_size if config.part_media.exists() else 0
    if prefix < 0 or prefix > config.expected_bytes:
        raise PrerequisiteError(f"CANONICAL_PREFIX_INVALID:{prefix}")
    records = manifest.get("segments")
    if not isinstance(records, Mapping):
        raise PrerequisiteError("PARALLEL_SEGMENT_RECORDS_INVALID")
    by_start: dict[int, Mapping[str, Any]] = {}
    for value in records.values():
        if not isinstance(value, Mapping):
            raise PrerequisiteError("PARALLEL_SEGMENT_RECORD_INVALID")
        try:
            start = int(value["start"])
            end = int(value["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PrerequisiteError(
                "PARALLEL_SEGMENT_BOUNDS_INVALID"
            ) from exc
        if start in by_start:
            raise PrerequisiteError(
                f"PARALLEL_SEGMENT_AMBIGUOUS_START:{start}"
            )
        if end < start or end >= config.expected_bytes:
            raise PrerequisiteError(
                f"PARALLEL_SEGMENT_BOUNDS_INVALID:{start}-{end}"
            )
        by_start[start] = value

    current = prefix
    count = 0
    covered_bytes = 0
    while current < config.expected_bytes:
        record = by_start.get(current)
        if record is None:
            raise PrerequisiteError(
                f"PARALLEL_SEGMENTS_INCOMPLETE_GAP_AT:{current}"
            )
        if record.get("status") != "complete":
            raise PrerequisiteError(
                f"PARALLEL_SEGMENT_NOT_COMPLETE:{current}"
            )
        end = int(record["end"])
        expected_size = end - current + 1
        if record.get("observed_bytes") != expected_size:
            raise PrerequisiteError(
                f"PARALLEL_SEGMENT_RECORDED_SIZE_MISMATCH:{current}"
            )
        digest = str(record.get("sha256", ""))
        if len(digest) != 64:
            raise PrerequisiteError(
                f"PARALLEL_SEGMENT_HASH_MISSING:{current}"
            )
        stored = Path(str(record.get("path", "")))
        if (
            stored.is_absolute()
            or ".." in stored.parts
            or stored.name != str(record.get("path"))
        ):
            raise PrerequisiteError(
                f"PARALLEL_SEGMENT_PATH_UNSAFE:{current}"
            )
        path = config.segment_dir / stored
        if path.is_symlink() or not path.is_file():
            raise PrerequisiteError(
                f"PARALLEL_SEGMENT_FILE_MISSING:{current}"
            )
        if path.stat().st_size != expected_size:
            raise PrerequisiteError(
                f"PARALLEL_SEGMENT_FILE_SIZE_MISMATCH:{current}"
            )
        count += 1
        covered_bytes += expected_size
        current = end + 1
    if current != config.expected_bytes:
        raise PrerequisiteError("PARALLEL_SEGMENTS_DO_NOT_REACH_EOF")
    return {
        "manifest": relative(config.root, config.segment_manifest),
        "manifest_sha256": sha256_file(config.segment_manifest),
        "canonical_prefix_bytes": prefix,
        "complete_segment_count": count,
        "complete_segment_bytes": covered_bytes,
        "expected_bytes": config.expected_bytes,
        "full_segment_content_rehash_deferred_to_assembly": True,
    }


def validate_exact_outputs(config: Config) -> dict[str, Any]:
    if not config.exact_manifest.is_file():
        raise OutputValidationError("EXACT_MANIFEST_MISSING")
    manifest = load_json(config.exact_manifest, label="EXACT_MANIFEST")
    if not isinstance(manifest, Mapping):
        raise OutputValidationError("EXACT_MANIFEST_NOT_OBJECT")
    source = manifest.get("source", {})
    media = manifest.get("media", {})
    technical = manifest.get("technical_validation", {})
    scope = manifest.get("scope", {})
    expected_media_path = relative(config.root, config.final_media)
    if (
        manifest.get("status") != EXACT_READY
        or source.get("asset_id") != ASSET_ID
        or source.get("license") != "CC-BY-NC-4.0"
        or media.get("path") != expected_media_path
        or media.get("bytes") != config.expected_bytes
        or media.get("md5") != config.official_md5
        or media.get("official_md5_verified") is not True
        or len(str(media.get("sha256", ""))) != 64
        or technical.get("ffprobe_passed") is not True
        or scope.get("semantic_annotations_opened_or_used") is not False
    ):
        raise OutputValidationError("EXACT_MANIFEST_NOT_READY")
    if config.final_media.is_symlink() or not config.final_media.is_file():
        raise OutputValidationError("EXACT_MEDIA_MISSING_OR_SYMLINK")
    if config.final_media.stat().st_size != config.expected_bytes:
        raise OutputValidationError("EXACT_MEDIA_SIZE_MISMATCH")
    return {
        "status": EXACT_READY,
        "manifest": relative(config.root, config.exact_manifest),
        "manifest_sha256": sha256_file(config.exact_manifest),
        "media": expected_media_path,
        "media_bytes": config.expected_bytes,
        "media_sha256_from_exact_manifest": media["sha256"],
        "media_content_rehash_deferred_to_independent_verifier": True,
    }


TIMELINE_FILES = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "checkpoint_manifest.json",
    "build_manifest.json",
)


def timeline_paths(config: Config) -> list[Path]:
    return [config.timeline_root / name for name in TIMELINE_FILES]


def timeline_documents(config: Config) -> dict[str, Mapping[str, Any]]:
    documents: dict[str, Mapping[str, Any]] = {}
    for name in TIMELINE_FILES:
        document = load_json(
            config.timeline_root / name,
            label=f"TIMELINE_{name.upper().replace('.', '_')}",
        )
        if not isinstance(document, Mapping):
            raise OutputValidationError(
                f"TIMELINE_{name.upper().replace('.', '_')}_NOT_OBJECT"
            )
        documents[name] = document
    return documents


def verified_timeline_receipt(config: Config) -> dict[str, Any]:
    path = config.receipts_dir / TIMELINE_VERIFIER_RECEIPT
    if path.is_symlink() or not path.is_file():
        raise OutputValidationError("TIMELINE_VERIFIER_RECEIPT_MISSING")
    receipt = load_json(path, label="TIMELINE_VERIFIER_RECEIPT")
    if not isinstance(receipt, Mapping):
        raise OutputValidationError("TIMELINE_VERIFIER_RECEIPT_NOT_OBJECT")
    verify_seal(
        receipt, "receipt_sha256", label="TIMELINE_VERIFIER_RECEIPT"
    )
    execution = receipt.get("execution", {})
    validation = receipt.get("output_validation", {})
    stdout = execution.get("stdout", {})
    stdout_tail = str(stdout.get("tail", ""))
    stdout_bytes = stdout_tail.encode("utf-8")
    if (
        receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION
        or receipt.get("stage") != "verify_full_timeline"
        or execution.get("execution_kind") != "executed"
        or execution.get("return_code") != 0
        or not isinstance(stdout, Mapping)
        or stdout.get("bytes") != len(stdout_bytes)
        or stdout.get("sha256")
        != hashlib.sha256(stdout_bytes).hexdigest()
        or not recursively_contains(stdout_tail, '"verified": true')
        or not recursively_contains(stdout_tail, TIMELINE_READY)
        or validation.get("status") != "COMPLETE"
        or validation.get("decision") != TIMELINE_READY
    ):
        raise OutputValidationError(
            "TIMELINE_VERIFIER_RECEIPT_NOT_VERIFIED"
        )
    return dict(receipt)


def validate_timeline_bindings(
    config: Config,
    documents: Mapping[str, Mapping[str, Any]],
    *,
    require_verifier_receipt: bool,
) -> dict[str, Any]:
    build = documents["build_manifest.json"]
    segment = documents["segment_manifest.json"]
    observation = documents["observation_manifest.json"]
    index = documents["full_timeline_index.json"]
    resource = documents["resource_manifest.json"]
    checkpoint = documents["checkpoint_manifest.json"]

    for name, document in documents.items():
        if (
            document.get("schema_version") != TIMELINE_SCHEMA_VERSION
            or document.get("stage") != TIMELINE_STAGE
        ):
            raise OutputValidationError(
                f"TIMELINE_SCHEMA_OR_STAGE_INVALID:{name}"
            )
    for document, field, label in (
        (segment, "segment_manifest_hash", "TIMELINE_SEGMENT_MANIFEST"),
        (
            observation,
            "observation_manifest_hash",
            "TIMELINE_OBSERVATION_MANIFEST",
        ),
        (index, "index_hash", "TIMELINE_FULL_INDEX"),
        (resource, "resource_manifest_hash", "TIMELINE_RESOURCE_MANIFEST"),
        (
            checkpoint,
            "checkpoint_manifest_hash",
            "TIMELINE_CHECKPOINT_MANIFEST",
        ),
        (build, "build_manifest_hash", "TIMELINE_BUILD_MANIFEST"),
    ):
        verify_seal(document, field, label=label)

    expected_source = validate_exact_outputs(config)[
        "media_sha256_from_exact_manifest"
    ]
    source = resource.get("source", {})
    models = resource.get("models", {})
    if (
        segment.get("source_ref") != ASSET_ID
        or segment.get("source_sha256") != expected_source
        or index.get("source_ref") != ASSET_ID
        or build.get("source_ref") != ASSET_ID
        or build.get("source_sha256") != expected_source
        or checkpoint.get("source_sha256") != expected_source
        or not isinstance(source, Mapping)
        or source.get("media_sha256") != expected_source
        or source.get("media_path") != relative(config.root, config.final_media)
        or source.get("manifest_path")
        != relative(config.root, config.exact_manifest)
        or source.get("manifest_sha256") != sha256_file(config.exact_manifest)
        or not isinstance(models, Mapping)
        or set(models) != {"audio", "speech", "vision"}
    ):
        raise OutputValidationError("TIMELINE_SOURCE_OR_RESOURCE_BINDING_INVALID")
    for name, model in models.items():
        if (
            not isinstance(model, Mapping)
            or not str(model.get("model_id", ""))
            or len(str(model.get("revision", ""))) < 20
            or model.get("local_files_only") is not True
            or not str(model.get("snapshot_path", ""))
        ):
            raise OutputValidationError(
                f"TIMELINE_MODEL_BINDING_INVALID:{name}"
            )

    config_hash = observation.get("config_hash")
    if (
        not isinstance(config_hash, str)
        or not config_hash.startswith("sha256:")
        or observation.get("config", {}).get("source_sha256")
        != expected_source
        or observation.get("segment_manifest_hash")
        != segment.get("segment_manifest_hash")
        or index.get("segment_manifest_hash")
        != segment.get("segment_manifest_hash")
        or index.get("observation_manifest_hash")
        != observation.get("observation_manifest_hash")
        or checkpoint.get("config_hash") != config_hash
        or build.get("config_hash") != config_hash
    ):
        raise OutputValidationError("TIMELINE_INDEX_BINDING_INVALID")
    observation_models = observation.get("config", {}).get("models", {})
    if not isinstance(observation_models, Mapping):
        raise OutputValidationError("TIMELINE_OBSERVATION_MODELS_INVALID")
    for name, model in models.items():
        observed = observation_models.get(name, {})
        if (
            not isinstance(observed, Mapping)
            or observed.get("model_id") != model.get("model_id")
            or observed.get("revision") != model.get("revision")
        ):
            raise OutputValidationError(
                f"TIMELINE_OBSERVATION_MODEL_BINDING_INVALID:{name}"
            )

    checkpoint_rows = checkpoint.get("checkpoints")
    payload_hashes = observation.get("checkpoint_payload_hashes")
    if (
        not isinstance(checkpoint_rows, list)
        or not isinstance(payload_hashes, Mapping)
        or checkpoint.get("checkpoint_count") != len(checkpoint_rows)
        or build.get("checkpoint_count") != len(checkpoint_rows)
    ):
        raise OutputValidationError("TIMELINE_CHECKPOINT_ROWS_INVALID")
    checked_checkpoints: list[dict[str, Any]] = []
    for row in checkpoint_rows:
        if not isinstance(row, Mapping):
            raise OutputValidationError("TIMELINE_CHECKPOINT_ROW_INVALID")
        layer = str(row.get("layer", ""))
        path = safe_repo_path(
            config.root,
            str(row.get("path", "")),
            label="TIMELINE_CHECKPOINT",
        )
        payload_hash = str(row.get("payload_hash", ""))
        if (
            not layer
            or payload_hashes.get(layer) != payload_hash
            or path.is_symlink()
            or not path.is_file()
            or row.get("size_bytes") != path.stat().st_size
            or row.get("sha256") != "sha256:" + sha256_file(path)
        ):
            raise OutputValidationError(
                f"TIMELINE_CHECKPOINT_BINDING_INVALID:{layer or '?'}"
            )
        payload = load_json(path, label=f"TIMELINE_CHECKPOINT_{layer}")
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema_version") != TIMELINE_SCHEMA_VERSION
            or payload.get("layer") != layer
            or payload.get("source_sha256") != expected_source
            or payload.get("config_hash") != config_hash
            or payload.get("payload_hash") != payload_hash
            or payload.get("record_count") != row.get("record_count")
        ):
            raise OutputValidationError(
                f"TIMELINE_CHECKPOINT_PAYLOAD_INVALID:{layer}"
            )
        if payload_hash != object_hash(payload.get("payload")):
            raise OutputValidationError(
                f"TIMELINE_CHECKPOINT_PAYLOAD_HASH_MISMATCH:{layer}"
            )
        checked_checkpoints.append(
            {
                "layer": layer,
                "path": relative(config.root, path),
                "payload_hash": payload_hash,
            }
        )

    receipt_hash: str | None = None
    if require_verifier_receipt:
        receipt = verified_timeline_receipt(config)
        validation = receipt["output_validation"]
        if (
            validation.get("build_manifest_hash")
            != build.get("build_manifest_hash")
        ):
            raise OutputValidationError(
                "TIMELINE_VERIFIER_BUILD_BINDING_MISMATCH"
            )
        receipt_artifacts = {
            item.get("path"): item
            for item in validation.get("artifacts", [])
            if isinstance(item, Mapping)
        }
        for name in TIMELINE_FILES:
            if name == "build_manifest.json":
                continue
            path = config.timeline_root / name
            row = receipt_artifacts.get(relative(config.root, path), {})
            if (
                row.get("bytes") != path.stat().st_size
                or row.get("sha256") != sha256_file(path)
            ):
                raise OutputValidationError(
                    f"TIMELINE_VERIFIER_ARTIFACT_BINDING_MISMATCH:{name}"
                )
        receipt_hash = receipt["receipt_sha256"]
    return {
        "source_sha256": expected_source,
        "segment_manifest_hash": segment["segment_manifest_hash"],
        "observation_manifest_hash": observation[
            "observation_manifest_hash"
        ],
        "index_hash": index["index_hash"],
        "resource_manifest_hash": resource["resource_manifest_hash"],
        "checkpoint_manifest_hash": checkpoint[
            "checkpoint_manifest_hash"
        ],
        "build_manifest_hash": build["build_manifest_hash"],
        "config_hash": config_hash,
        "model_revisions": {
            name: model["revision"] for name, model in sorted(models.items())
        },
        "checkpoint_count": len(checked_checkpoints),
        "verifier_receipt_sha256": receipt_hash,
    }


def validate_timeline_outputs(config: Config) -> dict[str, Any]:
    missing = [
        relative(config.root, path)
        for path in timeline_paths(config)
        if not path.is_file() or path.is_symlink()
    ]
    if missing:
        raise OutputValidationError(
            "TIMELINE_OUTPUTS_MISSING:" + ",".join(missing)
        )
    documents = timeline_documents(config)
    build = documents["build_manifest.json"]
    terminal = build.get("terminal_boundary", {})
    if (
        build.get("status") != "COMPLETE"
        or build.get("decision") != TIMELINE_READY
        or build.get("smoke_seconds") is not None
        or terminal.get("index_only") is not True
        or terminal.get("families_generated") is not False
        or terminal.get(
            "human_or_ses_or_h_or_gate_claim_generated"
        )
        is not False
    ):
        raise OutputValidationError("TIMELINE_BUILD_NOT_FULL_AND_COMPLETE")
    validate_timeline_bindings(
        config, documents, require_verifier_receipt=False
    )
    artifact_rows = build.get("artifact_hashes")
    if not isinstance(artifact_rows, list):
        raise OutputValidationError("TIMELINE_ARTIFACT_HASHES_INVALID")
    checked: list[dict[str, Any]] = []
    expected_artifacts = {
        relative(config.root, config.timeline_root / name)
        for name in TIMELINE_FILES
        if name != "build_manifest.json"
    }
    observed_artifacts: set[str] = set()
    for row in artifact_rows:
        if not isinstance(row, Mapping):
            raise OutputValidationError("TIMELINE_ARTIFACT_ROW_INVALID")
        path = safe_repo_path(
            config.root, str(row.get("path", "")), label="TIMELINE_ARTIFACT"
        )
        if path.is_symlink() or not path.is_file():
            raise OutputValidationError(
                f"TIMELINE_ARTIFACT_MISSING:{path}"
            )
        observed = sha256_file(path)
        if (
            row.get("size_bytes") != path.stat().st_size
            or row.get("sha256") != "sha256:" + observed
        ):
            raise OutputValidationError(
                f"TIMELINE_ARTIFACT_BINDING_MISMATCH:{path}"
            )
        path_text = relative(config.root, path)
        if path_text in observed_artifacts:
            raise OutputValidationError(
                f"TIMELINE_ARTIFACT_DUPLICATE:{path_text}"
            )
        observed_artifacts.add(path_text)
        checked.append(
            {
                "path": path_text,
                "bytes": path.stat().st_size,
                "sha256": observed,
            }
        )
    if observed_artifacts != expected_artifacts:
        raise OutputValidationError("TIMELINE_ARTIFACT_SET_INVALID")
    return {
        "status": "COMPLETE",
        "decision": TIMELINE_READY,
        "build_manifest_hash": build["build_manifest_hash"],
        "artifact_count": len(checked),
        "artifacts": checked,
    }


def validate_family_registry(config: Config) -> dict[str, Any]:
    if (
        config.candidate_registry.is_symlink()
        or not config.candidate_registry.is_file()
    ):
        raise OutputValidationError("CANDIDATE_REGISTRY_MISSING")
    registry = load_json(
        config.candidate_registry, label="CANDIDATE_REGISTRY"
    )
    if not isinstance(registry, Mapping):
        raise OutputValidationError("CANDIDATE_REGISTRY_NOT_OBJECT")
    verify_seal(
        registry, "registry_payload_sha256", label="CANDIDATE_REGISTRY"
    )
    summary = registry.get("summary", {})
    boundary = registry.get("acceptance_boundary", {})
    resource = registry.get("resource_report", {})
    mining = registry.get("mining_boundary", {})
    if (
        registry.get("decision") != FAMILY_READY
        or registry.get("source_id") != ASSET_ID
        or registry.get("artifact_classification")
        != "DEVELOPMENT_ONLY_MACHINE_EXPERT_PROVISIONAL"
        or summary.get("accepted_family_count") != 0
        or summary.get("accepted_ses_count") != 0
        or summary.get("h_tier_count") != 0
        or summary.get("gate_a_credit_count") != 0
        or boundary.get("accepted_families") != []
        or boundary.get("accepted_ses") != []
        or boundary.get("h_tiers") != []
        or boundary.get("gate_a_asserted") is not False
        or boundary.get("future_test_eligible") is not False
        or resource.get("model_inference_runs") != 0
        or mining.get("models_loaded") is not False
    ):
        raise OutputValidationError(
            "CANDIDATE_REGISTRY_CLAIM_BOUNDARY_VIOLATION"
        )
    return {
        "decision": FAMILY_READY,
        "registry": relative(config.root, config.candidate_registry),
        "registry_sha256": sha256_file(config.candidate_registry),
        "registry_payload_sha256": registry["registry_payload_sha256"],
        "candidate_count": summary.get("candidate_count"),
        "accepted_family_count": 0,
        "accepted_ses_count": 0,
        "h_tier_count": 0,
        "gate_a_credit_count": 0,
    }


def recursively_contains(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return value == needle or needle in value
    if isinstance(value, Mapping):
        return any(recursively_contains(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(recursively_contains(item, needle) for item in value)
    return False


def machine_bundle_paths(config: Config) -> dict[str, Path]:
    root = safe_repo_path(
        config.root, MACHINE_BUNDLE_ROOT, label="MACHINE_BUNDLE_ROOT"
    )
    return {name: root / name for name in MACHINE_BUNDLE_SPECS}


def validate_machine_provisional_bundle(config: Config) -> dict[str, Any]:
    paths = machine_bundle_paths(config)
    documents: dict[str, Mapping[str, Any]] = {}
    for name, path in paths.items():
        if path.is_symlink() or not path.is_file():
            raise OutputValidationError(f"MACHINE_BUNDLE_MISSING:{name}")
        document = load_json(path, label=f"MACHINE_BUNDLE_{name.upper()}")
        if not isinstance(document, Mapping):
            raise OutputValidationError(
                f"MACHINE_BUNDLE_NOT_OBJECT:{name}"
            )
        schema, status = MACHINE_BUNDLE_SPECS[name]
        if (
            document.get("schema_version") != schema
            or document.get("status") != status
            or document.get("decision") != MACHINE_BUNDLE_READY
            or document.get("source_id") != ASSET_ID
            or document.get("source_group_id") != "P23"
            or document.get("artifact_classification")
            != MACHINE_BUNDLE_CLASSIFICATION
        ):
            raise OutputValidationError(
                f"MACHINE_BUNDLE_IDENTITY_INVALID:{name}"
            )
        verify_seal(document, "payload_sha256", label=name.upper())
        documents[name] = document

    timeline = validate_timeline_bindings(
        config, timeline_documents(config), require_verifier_receipt=True
    )
    expected_index_bindings = {
        "build_manifest_hash": timeline["build_manifest_hash"],
        "index_hash": timeline["index_hash"],
        "observation_manifest_hash": timeline[
            "observation_manifest_hash"
        ],
        "segment_manifest_hash": timeline["segment_manifest_hash"],
    }
    expected_inputs = {
        relative(config.root, path): "sha256:" + sha256_file(path)
        for path in [
            config.root
            / "data/rehearsal_plan/exogenous_restoration_protocol_v2.json",
            config.rehearsal_plan,
            config.candidate_registry,
            *timeline_paths(config),
        ]
    }
    payload_hashes = {
        name: document["payload_sha256"]
        for name, document in documents.items()
    }
    for name, document in documents.items():
        if (
            document.get("source_sha256") != timeline["source_sha256"]
            or document.get("index_bindings") != expected_index_bindings
        ):
            raise OutputValidationError(
                f"MACHINE_BUNDLE_TIMELINE_BINDING_INVALID:{name}"
            )
        input_rows = document.get("input_bindings")
        if not isinstance(input_rows, list):
            raise OutputValidationError(
                f"MACHINE_BUNDLE_INPUT_BINDINGS_INVALID:{name}"
            )
        actual_inputs: dict[str, str] = {}
        for row in input_rows:
            if (
                not isinstance(row, Mapping)
                or set(row) != {"path", "sha256"}
                or str(row.get("path", "")) in actual_inputs
            ):
                raise OutputValidationError(
                    f"MACHINE_BUNDLE_INPUT_BINDING_ROW_INVALID:{name}"
                )
            actual_inputs[str(row["path"])] = str(row["sha256"])
        if actual_inputs != expected_inputs:
            raise OutputValidationError(
                f"MACHINE_BUNDLE_INPUT_BINDING_MISMATCH:{name}"
            )

    families = documents["family_registry.json"]
    evidence = documents["evidence_registry.json"]
    interventions = documents["intervention_manifest.json"]
    surfaces = documents["state_surface_manifest.json"]
    split = documents["source_split_manifest.json"]
    leakage = documents["leakage_gate.json"]
    boundary = families.get("acceptance_boundary", {})
    coverage = evidence.get("coverage_phrase_compatibility", {})
    checks = leakage.get("checks", {})
    firewall = leakage.get("claim_firewall", {})
    if (
        boundary.get("accepted_family_count") != 0
        or boundary.get("accepted_ses_count") != 0
        or boundary.get("h_tier_count") != 0
        or boundary.get("gate_a_credit_count") != 0
        or boundary.get("future_test_eligible") is not False
        or coverage.get("asserted") is not False
        or not str(coverage.get("reason", ""))
        or split.get("source_assignments", [{}])[0].get("evaluation_eligible")
        is not False
        or checks.get("models_loaded") is not False
        or checks.get("network_used") is not False
        or any(
            firewall.get(key) != 0
            for key in (
                "accepted_families",
                "accepted_ses",
                "h_tiers",
                "gate_a_claims",
                "validated_answer_semantics",
                "validated_support_semantics",
                "validated_necessity_semantics",
            )
        )
    ):
        raise OutputValidationError("MACHINE_BUNDLE_CLAIM_BOUNDARY_INVALID")

    family_rows = families.get("families")
    evidence_rows = evidence.get("evidence")
    route_rows = evidence.get("route_groups")
    intervention_rows = interventions.get("interventions")
    surface_rows = surfaces.get("surfaces")
    if not all(
        isinstance(rows, list)
        for rows in (
            family_rows,
            evidence_rows,
            route_rows,
            intervention_rows,
            surface_rows,
        )
    ):
        raise OutputValidationError("MACHINE_BUNDLE_ROWS_INVALID")
    family_ids = {str(row.get("family_id")) for row in family_rows}
    evidence_ids = {
        str(row.get("evidence_handle_id")) for row in evidence_rows
    }
    route_ids = {str(row.get("route_group_id")) for row in route_rows}
    intervention_ids = {
        str(row.get("intervention_id")) for row in intervention_rows
    }
    if (
        len(family_ids) != families.get("family_count")
        or len(family_ids) != len(family_rows)
        or len(evidence_ids)
        != evidence.get("evidence_count")
        or len(evidence_ids) != len(evidence_rows)
        or len(route_ids) != evidence.get("route_group_count")
        or len(route_ids) != len(route_rows)
        or len(intervention_ids)
        != interventions.get("intervention_count")
        or len(intervention_ids) != len(intervention_rows)
        or surfaces.get("surface_count") != len(surface_rows)
    ):
        raise OutputValidationError("MACHINE_BUNDLE_COUNT_OR_ID_INVALID")
    index = timeline_documents(config)["full_timeline_index.json"]
    modalities = index.get("modalities", {})
    if not isinstance(modalities, Mapping):
        raise OutputValidationError("MACHINE_BUNDLE_INDEX_MODALITIES_INVALID")
    indexed: dict[str, dict[str, Mapping[str, Any]]] = {}
    for modality, index_name in (
        ("vision", "siglip2_visual"),
        ("ambient_audio", "clap_audio"),
    ):
        section = modalities.get(index_name, {})
        documents_in_section = (
            section.get("documents", {})
            if isinstance(section, Mapping)
            else {}
        )
        if not isinstance(documents_in_section, list):
            raise OutputValidationError(
                f"MACHINE_BUNDLE_INDEX_DOCUMENTS_INVALID:{modality}"
            )
        indexed[modality] = {
            str(row.get("segment_id")): row
            for row in documents_in_section
            if isinstance(row, Mapping)
        }
    family_by_id = {
        str(row["family_id"]): row
        for row in family_rows
        if isinstance(row, Mapping) and "family_id" in row
    }
    route_by_id = {
        str(row["route_group_id"]): row
        for row in route_rows
        if isinstance(row, Mapping) and "route_group_id" in row
    }
    intervention_by_id = {
        str(row["intervention_id"]): row
        for row in intervention_rows
        if isinstance(row, Mapping) and "intervention_id" in row
    }
    for row in evidence_rows:
        modality = str(row.get("modality", ""))
        indexed_row = indexed.get(modality, {}).get(
            str(row.get("record_id", ""))
        )
        if (
            row.get("family_id") not in family_ids
            or row.get("route_group_id") not in route_ids
            or row.get("exact_index_binding_verified") is not True
            or row.get("human_validated") is not False
            or row.get("semantic_content_asserted") is not False
            or indexed_row is None
            or indexed_row.get("start_us") != row.get("start_us")
            or indexed_row.get("end_us") != row.get("end_us")
            or row.get("source_sha256") != timeline["source_sha256"]
        ):
            raise OutputValidationError(
                "MACHINE_BUNDLE_EVIDENCE_REFERENCE_INVALID"
            )
    for row in route_rows:
        family = family_by_id.get(str(row.get("family_id", "")), {})
        if (
            row.get("family_id") not in family_ids
            or not set(row.get("evidence_handle_ids", [])) <= evidence_ids
            or row.get("route_group_id") != family.get("route_group_id")
            or set(row.get("evidence_handle_ids", []))
            != set(family.get("evidence_handle_ids", []))
            or row.get("human_validated") is not False
            or row.get("support_validated") is not False
            or row.get("necessity_validated") is not False
        ):
            raise OutputValidationError(
                "MACHINE_BUNDLE_ROUTE_REFERENCE_INVALID"
            )
    for row in intervention_rows:
        route = route_by_id.get(str(row.get("route_group_id", "")), {})
        if (
            row.get("family_id") not in family_ids
            or row.get("route_group_id") not in route_ids
            or not set(row.get("suppressed_evidence_handle_ids", []))
            <= evidence_ids
            or set(row.get("suppressed_evidence_handle_ids", []))
            != set(route.get("evidence_handle_ids", []))
            or row.get("human_validated") is not False
            or row.get("accepted_ses") is not False
        ):
            raise OutputValidationError(
                "MACHINE_BUNDLE_INTERVENTION_REFERENCE_INVALID"
            )
    for row in surface_rows:
        intervention = intervention_by_id.get(
            str(row.get("intervention_id", "")), {}
        )
        if (
            row.get("family_id") not in family_ids
            or row.get("route_group_id") not in route_ids
            or row.get("intervention_id") not in intervention_ids
            or row.get("human_validated") is not False
            or row.get("private_fields_model_visible") is not False
            or row.get("family_id") != intervention.get("family_id")
            or row.get("route_group_id")
            != intervention.get("route_group_id")
        ):
            raise OutputValidationError(
                "MACHINE_BUNDLE_SURFACE_REFERENCE_INVALID"
            )

    non_leakage = {
        name: payload_hash
        for name, payload_hash in sorted(payload_hashes.items())
        if name != "leakage_gate.json"
    }
    if (
        leakage.get("artifact_payload_hashes") != non_leakage
        or leakage.get("bundle_content_sha256") != object_hash(non_leakage)
        or interventions.get("family_registry_payload_sha256")
        != payload_hashes["family_registry.json"]
        or interventions.get("evidence_registry_payload_sha256")
        != payload_hashes["evidence_registry.json"]
        or surfaces.get("family_registry_payload_sha256")
        != payload_hashes["family_registry.json"]
        or surfaces.get("evidence_registry_payload_sha256")
        != payload_hashes["evidence_registry.json"]
        or surfaces.get("intervention_manifest_payload_sha256")
        != payload_hashes["intervention_manifest.json"]
    ):
        raise OutputValidationError(
            "MACHINE_BUNDLE_REFERENTIAL_HASH_BINDING_INVALID"
        )
    return {
        "decision": MACHINE_BUNDLE_READY,
        "bundle_root": MACHINE_BUNDLE_ROOT,
        "bundle_content_sha256": leakage["bundle_content_sha256"],
        "artifacts": {
            name: {
                "path": relative(config.root, paths[name]),
                "file_sha256": sha256_file(paths[name]),
                "payload_sha256": payload_hashes[name],
                "schema_version": document["schema_version"],
                "status": document["status"],
            }
            for name, document in sorted(documents.items())
        },
        "family_count": families["family_count"],
        "evidence_count": evidence["evidence_count"],
        "route_group_count": evidence["route_group_count"],
        "intervention_count": interventions["intervention_count"],
        "surface_count": surfaces["surface_count"],
        "accepted_family_count": 0,
        "accepted_ses_count": 0,
        "timeline_bindings": timeline,
        "evidence_coverage_claim_asserted": False,
    }


def compatibility_mapping(config: Config) -> list[dict[str, Any]]:
    paths = machine_bundle_paths(config)
    return [
        {
            "prospective_path": relative(
                config.root, config.timeline_root / "build_manifest.json"
            ),
            "prospective_requirement": {
                "required_status": EXACT_READY,
            },
            "current_authoritative_requirement": {
                "status": "COMPLETE",
                "decision": TIMELINE_READY,
                "full_hash_and_verifier_receipt_binding_required": True,
            },
            "resolution": "CURRENT_AUTHORITATIVE_OUTPUT",
        },
        {
            "prospective_path": relative(
                config.root,
                config.timeline_root / "full_timeline_index.json",
            ),
            "prospective_requirement": {
                "required_binding": (
                    "source_sha256_and_frozen_model_revisions"
                )
            },
            "current_authoritative_requirement": {
                "bound_via": [
                    "build_manifest.json",
                    "resource_manifest.json",
                    "checkpoint_manifest.json",
                    "observation_manifest.json",
                    TIMELINE_VERIFIER_RECEIPT,
                ]
            },
            "resolution": "CURRENT_AUTHORITATIVE_OUTPUT",
        },
        {
            "prospective_path": relative(
                config.root,
                config.timeline_root / "observation_manifest.json",
            ),
            "prospective_requirement": {"required_status": "COMPLETE"},
            "current_authoritative_requirement": {
                "self_hash_and_checkpoint_payload_bindings_required": True
            },
            "resolution": "CURRENT_AUTHORITATIVE_OUTPUT",
        },
        {
            "prospective_path": relative(
                config.root, paths["evidence_registry.json"]
            ),
            "prospective_requirement": {
                "required_phrase": (
                    "all accepted SESs discovered under the frozen "
                    "saturation protocol"
                )
            },
            "current_authoritative_requirement": {
                "status": "MACHINE_PROVISIONAL_EVIDENCE_FROZEN",
                "coverage_phrase_asserted": False,
                "accepted_ses_count": 0,
            },
            "resolution": "MACHINE_PROVISIONAL_NONCLAIM",
        },
        *[
            {
                "prospective_path": relative(config.root, path),
                "prospective_requirement": "PATH_STATUS_SCHEMA_FROM_FROZEN_PLAN",
                "current_authoritative_requirement": {
                    "schema_version": MACHINE_BUNDLE_SPECS[name][0],
                    "status": MACHINE_BUNDLE_SPECS[name][1],
                    "decision": MACHINE_BUNDLE_READY,
                    "payload_and_cross_artifact_hashes_required": True,
                },
                "resolution": "CURRENT_AUTHORITATIVE_OUTPUT",
            }
            for name, path in sorted(paths.items())
            if name != "evidence_registry.json"
        ],
        {
            "prospective_path": ADAPTER_ATTESTATION_PATH,
            "prospective_requirement": {
                "required_status": "EXOGENOUS_RESTORATION_V2_ADAPTER_READY"
            },
            "current_authoritative_requirement": {
                "historical_artifact_preserved": True,
                "current_hash_match_required_for_readiness": True,
                "drift_disposition": HISTORICAL_SUPERSEDED_STATUS,
                "stale_readiness_may_not_be_adopted": True,
            },
            "resolution": HISTORICAL_SUPERSEDED_STATUS,
        },
        {
            "prospective_path": REHEARSAL_RUNNER_PATH,
            "prospective_requirement": {
                "required_status": "IMPLEMENTED_AND_HASH_FROZEN"
            },
            "current_authoritative_requirement": {
                "old_freeze_execution_forbidden": True,
                "runner_not_executed_by_readiness_audit": True,
                "current_development_execution_route": (
                    TECHNICAL_SMOKE_V2_FREEZE_ID
                ),
            },
            "resolution": HISTORICAL_SUPERSEDED_STATUS,
        },
    ]


def load_historical_adapter_attestation(
    config: Config,
) -> tuple[Path, Mapping[str, Any]]:
    path = safe_repo_path(
        config.root,
        ADAPTER_ATTESTATION_PATH,
        label="ADAPTER_ATTESTATION",
    )
    if path.is_symlink() or not path.is_file():
        raise OutputValidationError("ADAPTER_ATTESTATION_MISSING")
    document = load_json(path, label="ADAPTER_ATTESTATION")
    if not isinstance(document, Mapping):
        raise OutputValidationError("ADAPTER_ATTESTATION_NOT_OBJECT")
    runner = document.get("runner", {})
    if (
        document.get("schema_version")
        != "av-trace.p23-102-rehearsal-adapter-attestation/1.0"
        or document.get("status")
        != "EXOGENOUS_RESTORATION_V2_ADAPTER_READY"
        or document.get("validation_status") != "READY"
        or document.get("development_only") is not True
        or document.get("execution_authorized") is not False
        or document.get("decision")
        != "VALIDATION_READY_EXECUTION_FAIL_CLOSED"
        or not isinstance(runner, Mapping)
        or runner.get("path") != REHEARSAL_RUNNER_PATH
    ):
        raise OutputValidationError("ADAPTER_ATTESTATION_BOUNDARY_INVALID")
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise OutputValidationError("ADAPTER_ATTESTATION_ARTIFACTS_INVALID")
    seen: set[str] = set()
    for row in [*artifacts, runner]:
        if (
            not isinstance(row, Mapping)
            or set(row) != {"path", "sha256", "bytes"}
        ):
            raise OutputValidationError(
                "ADAPTER_ATTESTATION_ARTIFACT_ROW_INVALID"
            )
        row_path = str(row["path"])
        if row_path in seen:
            raise OutputValidationError(
                "ADAPTER_ATTESTATION_ARTIFACT_DUPLICATE"
            )
        seen.add(row_path)
    return path, document


def historical_adapter_attestation_audit(
    config: Config,
) -> dict[str, Any]:
    path, document = load_historical_adapter_attestation(config)
    runner = document["runner"]
    assert isinstance(runner, Mapping)
    runner_path = safe_repo_path(
        config.root,
        REHEARSAL_RUNNER_PATH,
        label="HISTORICAL_REHEARSAL_RUNNER",
    )
    runner_actual_sha256 = (
        "sha256:" + sha256_file(runner_path)
        if not runner_path.is_symlink() and runner_path.is_file()
        else None
    )
    code_drift = historical_code_drift_rows(config)
    return {
        "path": ADAPTER_ATTESTATION_PATH,
        "sha256": sha256_file(path),
        "status": document["status"],
        "validation_status": document["validation_status"],
        "execution_authorized": False,
        "attested_artifact_count": len(document["artifacts"]),
        "historical_receipt_preserved": True,
        "current_code_bound": False,
        "code_drift_rows": code_drift,
        "historical_runner_binding": {
            "path": REHEARSAL_RUNNER_PATH,
            "expected_sha256": runner.get("sha256"),
            "actual_sha256": runner_actual_sha256,
            "current": runner_actual_sha256 == runner.get("sha256"),
        },
    }


def historical_code_drift_rows(config: Config) -> list[dict[str, Any]]:
    _path, document = load_historical_adapter_attestation(config)
    artifacts = document["artifacts"]
    assert isinstance(artifacts, list)
    by_path = {
        str(row["path"]): row
        for row in artifacts
        if isinstance(row, Mapping)
    }
    rows: list[dict[str, Any]] = []
    for path_text in (CONTROLLER_PATH, PROCESS_PATH):
        historical = by_path.get(path_text)
        current_path = safe_repo_path(
            config.root,
            path_text,
            label="HISTORICAL_EXECUTION_CRITICAL_CODE",
        )
        actual_bytes = (
            current_path.stat().st_size
            if not current_path.is_symlink() and current_path.is_file()
            else None
        )
        actual_sha256 = (
            "sha256:" + sha256_file(current_path)
            if actual_bytes is not None
            else None
        )
        expected_sha256 = (
            str(historical["sha256"]) if historical is not None else None
        )
        expected_bytes = (
            historical["bytes"] if historical is not None else None
        )
        binding_matches = (
            historical is not None
            and expected_sha256 == actual_sha256
            and expected_bytes == actual_bytes
        )
        if binding_matches:
            continue
        rows.append(
            {
                "path": path_text,
                "drift_kind": (
                    "HASH_OR_SIZE_MISMATCH"
                    if historical is not None
                    else "MISSING_HISTORICAL_BINDING"
                ),
                "historical_binding_present": historical is not None,
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
                "expected_bytes": expected_bytes,
                "actual_bytes": actual_bytes,
            }
        )
    return rows


def technical_smoke_v2_route(config: Config) -> dict[str, Any]:
    freeze_path = safe_repo_path(
        config.root,
        TECHNICAL_SMOKE_V2_FREEZE_PATH,
        label="TECHNICAL_SMOKE_V2_FREEZE",
    )
    attestation_path = safe_repo_path(
        config.root,
        TECHNICAL_SMOKE_V2_ATTESTATION_PATH,
        label="TECHNICAL_SMOKE_V2_ATTESTATION",
    )
    runner_path = safe_repo_path(
        config.root,
        TECHNICAL_SMOKE_V2_RUNNER_PATH,
        label="TECHNICAL_SMOKE_V2_RUNNER",
    )
    if any(
        path.is_symlink() or not path.is_file()
        for path in (freeze_path, attestation_path, runner_path)
    ):
        raise OutputValidationError("TECHNICAL_SMOKE_V2_ROUTE_MISSING")
    freeze = load_json(
        freeze_path, label="TECHNICAL_SMOKE_V2_FREEZE"
    )
    attestation = load_json(
        attestation_path, label="TECHNICAL_SMOKE_V2_ATTESTATION"
    )
    if (
        not isinstance(freeze, Mapping)
        or freeze.get("freeze_id") != TECHNICAL_SMOKE_V2_FREEZE_ID
        or freeze.get("execution_authorized") is True
        or freeze.get("scope", {}).get("execution_authorized") is not False
        or not isinstance(attestation, Mapping)
        or attestation.get("execution_authorized") is not False
    ):
        raise OutputValidationError(
            "TECHNICAL_SMOKE_V2_ROUTE_BOUNDARY_INVALID"
        )
    return {
        "route_id": TECHNICAL_SMOKE_V2_FREEZE_ID,
        "only_current_development_execution_route": True,
        "freeze": {
            "path": TECHNICAL_SMOKE_V2_FREEZE_PATH,
            "sha256": "sha256:" + sha256_file(freeze_path),
        },
        "adapter_attestation": {
            "path": TECHNICAL_SMOKE_V2_ATTESTATION_PATH,
            "sha256": "sha256:" + sha256_file(attestation_path),
        },
        "runner": {
            "path": TECHNICAL_SMOKE_V2_RUNNER_PATH,
            "sha256": "sha256:" + sha256_file(runner_path),
        },
        "execution_authorized_by_route_artifacts": False,
        "separate_authorization_overlay_required": True,
        "executed_by_readiness_audit": False,
    }


def audit_rehearsal_prerequisites(config: Config) -> dict[str, Any]:
    validate_family_registry(config)
    if not config.rehearsal_plan.is_file():
        raise PrerequisiteError("REHEARSAL_PLAN_MISSING")
    plan = load_json(config.rehearsal_plan, label="REHEARSAL_PLAN")
    if not isinstance(plan, Mapping):
        raise PrerequisiteError("REHEARSAL_PLAN_NOT_OBJECT")
    prerequisite_block = plan.get("prerequisites")
    if not isinstance(prerequisite_block, Mapping):
        raise PrerequisiteError("REHEARSAL_PREREQUISITES_INVALID")
    rows: list[dict[str, Any]] = []
    timeline_validation: dict[str, Any] | None = None
    bundle_validation: dict[str, Any] | None = None
    historical_attestation_audit: dict[str, Any] | None = None
    smoke_route: dict[str, Any] | None = None

    def audit_row(row: Mapping[str, Any], category: str) -> None:
        nonlocal bundle_validation, historical_attestation_audit
        nonlocal smoke_route, timeline_validation
        path_text = str(row.get("path", ""))
        result: dict[str, Any] = {
            "category": category,
            "path": path_text,
            "passed": False,
            "checks": [],
        }
        try:
            path = safe_repo_path(
                config.root, path_text, label="REHEARSAL_PREREQUISITE"
            )
        except OrchestrationError as exc:
            result["checks"].append(str(exc))
            rows.append(result)
            return
        if path.is_symlink() or not path.is_file():
            result["checks"].append("MISSING_OR_SYMLINK")
            rows.append(result)
            return
        result["bytes"] = path.stat().st_size
        if (
            path == config.final_media
            and row.get("required_binding")
            == "sha256_and_size_from_exact_manifest"
        ):
            exact = load_json(config.exact_manifest, label="EXACT_MANIFEST")
            result["sha256"] = exact.get("media", {}).get("sha256")
            result["sha256_source"] = relative(
                config.root, config.exact_manifest
            )
        else:
            result["sha256"] = sha256_file(path)
        document: Any = None
        if path.suffix == ".json":
            try:
                document = load_json(path, label="REHEARSAL_PREREQUISITE")
            except OutputValidationError as exc:
                result["checks"].append(str(exc))
                rows.append(result)
                return
        checks: list[bool] = []
        timeline_paths_by_name = {
            relative(config.root, config.timeline_root / name): name
            for name in TIMELINE_FILES
        }
        bundle_paths_by_name = {
            relative(config.root, path): name
            for name, path in machine_bundle_paths(config).items()
        }
        if path_text in timeline_paths_by_name:
            try:
                if timeline_validation is None:
                    timeline_validation = validate_timeline_bindings(
                        config,
                        timeline_documents(config),
                        require_verifier_receipt=True,
                    )
                passed = True
                result["compatibility_resolution"] = (
                    "CURRENT_AUTHORITATIVE_OUTPUT"
                )
                result["authoritative_validation"] = timeline_validation
                result["checks"].append(
                    "current_timeline_referential_and_verifier_binding:PASS"
                )
            except OrchestrationError as exc:
                passed = False
                result["checks"].append(
                    "current_timeline_referential_and_verifier_binding:"
                    f"FAIL:{exc}"
                )
            checks.append(passed)
            result["passed"] = all(checks)
            rows.append(result)
            return
        if path_text in bundle_paths_by_name:
            try:
                if bundle_validation is None:
                    bundle_validation = validate_machine_provisional_bundle(
                        config
                    )
                name = bundle_paths_by_name[path_text]
                passed = True
                result["compatibility_resolution"] = (
                    "CURRENT_AUTHORITATIVE_OUTPUT"
                )
                result["authoritative_validation"] = bundle_validation[
                    "artifacts"
                ][name]
                result["checks"].append(
                    "current_machine_provisional_bundle_full_validation:PASS"
                )
                if name == "evidence_registry.json":
                    result["checks"].append(
                        "accepted_ses_coverage_phrase_not_asserted:"
                        "MACHINE_PROVISIONAL_PASS"
                    )
            except OrchestrationError as exc:
                passed = False
                result["checks"].append(
                    "current_machine_provisional_bundle_full_validation:"
                    f"FAIL:{exc}"
                )
            checks.append(passed)
            result["passed"] = all(checks)
            rows.append(result)
            return
        if path_text == ADAPTER_ATTESTATION_PATH:
            try:
                if historical_attestation_audit is None:
                    historical_attestation_audit = (
                        historical_adapter_attestation_audit(config)
                    )
                passed = False
                result["compatibility_resolution"] = (
                    HISTORICAL_SUPERSEDED_STATUS
                )
                result["authoritative_validation"] = (
                    historical_attestation_audit
                )
                result["checks"].append(
                    "historical_adapter_attestation_preserved:"
                    f"{HISTORICAL_SUPERSEDED_STATUS}"
                )
                result["checks"].append(
                    "current_code_binding:FAIL_CLOSED"
                )
            except OrchestrationError as exc:
                passed = False
                result["checks"].append(
                    f"historical_adapter_attestation_audit:FAIL:{exc}"
                )
            checks.append(passed)
            result["passed"] = all(checks)
            rows.append(result)
            return
        if path_text == REHEARSAL_RUNNER_PATH:
            try:
                if smoke_route is None:
                    smoke_route = technical_smoke_v2_route(config)
                passed = False
                result["compatibility_resolution"] = (
                    HISTORICAL_SUPERSEDED_STATUS
                )
                result["authoritative_validation"] = {
                    "old_freeze_execution_allowed": False,
                    "old_freeze_executed_by_readiness_audit": False,
                    "current_development_execution_route": smoke_route,
                }
                result["checks"].append(
                    "historical_640_run_execution_route:"
                    "SUPERSEDED_FAIL_CLOSED"
                )
                result["checks"].append(
                    "old_freeze_execution:FORBIDDEN"
                )
            except (OSError, OrchestrationError) as exc:
                passed = False
                result["checks"].append(
                    "technical_smoke_v2_route_validation:"
                    f"FAIL:{exc}"
                )
            checks.append(passed)
            result["passed"] = all(checks)
            rows.append(result)
            return
        required_status = row.get("required_status")
        if required_status is not None:
            passed = (
                isinstance(document, Mapping)
                and document.get("status") == required_status
            )
            checks.append(passed)
            result["checks"].append(
                f"required_status:{required_status}:{'PASS' if passed else 'FAIL'}"
            )
        tokens: list[str] = []
        if row.get("required_token") is not None:
            tokens.append(str(row["required_token"]))
        if isinstance(row.get("required_tokens"), list):
            tokens.extend(str(item) for item in row["required_tokens"])
        for token in tokens:
            passed = recursively_contains(document, token)
            checks.append(passed)
            result["checks"].append(
                f"required_token:{token}:{'PASS' if passed else 'FAIL'}"
            )
        phrase = row.get("required_phrase")
        if phrase is not None:
            passed = str(phrase) in path.read_text(
                encoding="utf-8", errors="replace"
            )
            checks.append(passed)
            result["checks"].append(
                f"required_phrase:{'PASS' if passed else 'FAIL'}"
            )
        binding = row.get("required_binding")
        if binding == "sha256_and_size_from_exact_manifest":
            try:
                validate_exact_outputs(config)
                exact = load_json(
                    config.exact_manifest, label="EXACT_MANIFEST"
                )
                media = exact["media"]
                passed = (
                    path == config.final_media
                    and path.stat().st_size == media["bytes"]
                    and len(str(media["sha256"])) == 64
                )
            except (
                OutputValidationError,
                KeyError,
                TypeError,
            ):
                passed = False
            checks.append(passed)
            result["checks"].append(
                f"required_binding:{binding}:{'PASS' if passed else 'FAIL'}"
            )
        elif binding is not None:
            # These bindings need their dedicated future artifacts. Presence
            # alone is never promoted to a binding claim.
            checks.append(False)
            result["checks"].append(
                f"required_binding:{binding}:UNPROVEN_FAIL_CLOSED"
            )
        if not checks:
            checks.append(True)
            result["checks"].append("file_present:PASS")
        result["passed"] = all(checks)
        rows.append(result)

    for row in prerequisite_block.get("existing_required", []):
        if isinstance(row, Mapping):
            audit_row(row, "existing_required")
    for row in prerequisite_block.get(
        "future_required_for_development_rehearsal", []
    ):
        if isinstance(row, Mapping):
            audit_row(row, "future_required")

    if historical_attestation_audit is None:
        historical_attestation_audit = (
            historical_adapter_attestation_audit(config)
        )
    if smoke_route is None:
        smoke_route = technical_smoke_v2_route(config)
    code_drift_rows = historical_attestation_audit["code_drift_rows"]
    expected_drift_paths = [CONTROLLER_PATH, PROCESS_PATH]
    observed_drift_paths = [
        str(row["path"]) for row in code_drift_rows
    ]
    if observed_drift_paths != expected_drift_paths:
        raise OutputValidationError(
            "HISTORICAL_CODE_DRIFT_ROWS_INVALID:"
            + ",".join(observed_drift_paths)
        )
    ready = False
    report: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "decision": READINESS_REPAIR_TOKEN,
        "generated_at_utc": utc_now(),
        "source_id": ASSET_ID,
        "status": HISTORICAL_SUPERSEDED_STATUS,
        "ready_for_development_rehearsal": ready,
        "historical_rehearsal": {
            "rehearsal_id": (
                "P23_102_ACQUIRE_GROUND_ACT_REHEARSAL_V1"
            ),
            "planned_assignment_count": 640,
            "disposition": HISTORICAL_SUPERSEDED_STATUS,
            "configuration_preserved": True,
            "adapter_attestation_preserved": True,
            "previous_receipts_preserved_as_historical": True,
            "stale_readiness_adopted_as_current": False,
            "old_freeze_execution_allowed": False,
        },
        "code_drift_rows": code_drift_rows,
        "current_development_execution_route": smoke_route,
        "rehearsal_executed": False,
        "models_or_agents_executed_by_readiness_validation": False,
        "machine_provisional_registry_only": True,
        "human_review_claimed": False,
        "accepted_ses_claimed": False,
        "h_tier_claimed": False,
        "gate_a_claimed": False,
        "scientific_execution_authorized": False,
        "prerequisite_count": len(rows),
        "passed_count": sum(bool(row["passed"]) for row in rows),
        "failed_count": sum(not bool(row["passed"]) for row in rows),
        "current_vs_prospective_compatibility": compatibility_mapping(
            config
        ),
        "authoritative_timeline_validation": timeline_validation,
        "authoritative_machine_provisional_bundle_validation": (
            bundle_validation
        ),
        "remaining_blockers": [
            row["path"] for row in rows if not row["passed"]
        ],
        "prerequisites": rows,
    }
    return seal(report, "readiness_report_sha256")


def normalized_readiness_report(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key not in {"generated_at_utc", "readiness_report_sha256"}
    }


def validate_readiness_report(config: Config) -> dict[str, Any]:
    if (
        config.readiness_report.is_symlink()
        or not config.readiness_report.is_file()
    ):
        raise OutputValidationError("READINESS_REPORT_MISSING")
    report = load_json(
        config.readiness_report, label="READINESS_REPORT"
    )
    if not isinstance(report, Mapping):
        raise OutputValidationError("READINESS_REPORT_NOT_OBJECT")
    verify_seal(
        report, "readiness_report_sha256", label="READINESS_REPORT"
    )
    if (
        report.get("schema_version") != READINESS_SCHEMA_VERSION
        or report.get("decision") != READINESS_REPAIR_TOKEN
        or report.get("status") != HISTORICAL_SUPERSEDED_STATUS
        or report.get("ready_for_development_rehearsal") is not False
        or report.get("historical_rehearsal", {}).get("disposition")
        != HISTORICAL_SUPERSEDED_STATUS
        or report.get("historical_rehearsal", {}).get(
            "stale_readiness_adopted_as_current"
        )
        is not False
        or report.get("historical_rehearsal", {}).get(
            "old_freeze_execution_allowed"
        )
        is not False
        or [
            row.get("path")
            for row in report.get("code_drift_rows", [])
            if isinstance(row, Mapping)
        ]
        != [CONTROLLER_PATH, PROCESS_PATH]
        or report.get("current_development_execution_route", {}).get(
            "route_id"
        )
        != TECHNICAL_SMOKE_V2_FREEZE_ID
        or report.get("current_development_execution_route", {}).get(
            "only_current_development_execution_route"
        )
        is not True
        or report.get("rehearsal_executed") is not False
        or report.get(
            "models_or_agents_executed_by_readiness_validation"
        )
        is not False
        or report.get("machine_provisional_registry_only") is not True
        or report.get("human_review_claimed") is not False
        or report.get("accepted_ses_claimed") is not False
        or report.get("h_tier_claimed") is not False
        or report.get("gate_a_claimed") is not False
    ):
        raise OutputValidationError("READINESS_REPORT_BOUNDARY_VIOLATION")
    expected = audit_rehearsal_prerequisites(config)
    if normalized_readiness_report(report) != normalized_readiness_report(
        expected
    ):
        raise OutputValidationError("READINESS_REPORT_STALE")
    return {
        "status": report["status"],
        "ready_for_development_rehearsal": report[
            "ready_for_development_rehearsal"
        ],
        "passed_count": report["passed_count"],
        "failed_count": report["failed_count"],
        "remaining_blockers": report["remaining_blockers"],
        "readiness_report_sha256": report[
            "readiness_report_sha256"
        ],
    }


@dataclass(frozen=True)
class Stage:
    name: str
    argv: Callable[[Config], list[str]]
    controls: Callable[[Config], list[Path]]
    outputs: Callable[[Config], list[Path]]
    validate_outputs: Callable[[Config], dict[str, Any]]
    prerequisite: Callable[[Config], dict[str, Any]]
    internal: bool = False
    adopt_existing_outputs: bool = True


def no_prerequisite(_config: Config) -> dict[str, Any]:
    return {"passed": True}


def exact_prerequisite(config: Config) -> dict[str, Any]:
    return validate_parallel_segments_complete(config)


def timeline_prerequisite(config: Config) -> dict[str, Any]:
    return validate_exact_outputs(config)


def verify_prerequisite(config: Config) -> dict[str, Any]:
    return validate_timeline_outputs(config)


def family_prerequisite(config: Config) -> dict[str, Any]:
    return validate_timeline_outputs(config)


def readiness_prerequisite(config: Config) -> dict[str, Any]:
    return validate_family_registry(config)


def rehearsal_control_paths(config: Config) -> list[Path]:
    paths = [
        config.rehearsal_plan,
        config.candidate_registry,
        config.receipts_dir / TIMELINE_VERIFIER_RECEIPT,
        config.root / TECHNICAL_SMOKE_V2_FREEZE_PATH,
        config.root / TECHNICAL_SMOKE_V2_ATTESTATION_PATH,
        config.root / TECHNICAL_SMOKE_V2_RUNNER_PATH,
        *timeline_paths(config),
        *machine_bundle_paths(config).values(),
    ]
    if not config.rehearsal_plan.is_file():
        return paths
    plan = load_json(config.rehearsal_plan, label="REHEARSAL_PLAN")
    if not isinstance(plan, Mapping):
        return paths
    prerequisites = plan.get("prerequisites", {})
    if not isinstance(prerequisites, Mapping):
        return paths
    for key in (
        "existing_required",
        "future_required_for_development_rehearsal",
    ):
        rows = prerequisites.get(key, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping) or not row.get("path"):
                continue
            paths.append(
                safe_repo_path(
                    config.root,
                    str(row["path"]),
                    label="REHEARSAL_PREREQUISITE",
                )
            )
    return paths


def default_stages() -> tuple[Stage, ...]:
    return (
        Stage(
            name="assemble_exact",
            argv=lambda c: [
                c.python,
                str(c.parallel_tool),
                "--assemble",
            ],
            controls=lambda c: [c.parallel_tool, c.exact_tool],
            outputs=lambda c: [c.exact_manifest, c.final_media],
            validate_outputs=validate_exact_outputs,
            prerequisite=exact_prerequisite,
        ),
        Stage(
            name="build_full_timeline",
            argv=lambda c: [
                c.python,
                str(c.build_tool),
                "--repo-root",
                str(c.root),
                "--plan",
                relative(c.root, c.timeline_plan),
                "--mode",
                "full",
                "--resume",
                "--threads",
                str(c.threads),
            ],
            controls=lambda c: [
                c.build_tool,
                c.timeline_plan,
                c.exact_manifest,
            ],
            outputs=timeline_paths,
            validate_outputs=validate_timeline_outputs,
            prerequisite=timeline_prerequisite,
        ),
        Stage(
            name="verify_full_timeline",
            argv=lambda c: [
                c.python,
                str(c.verify_tool),
                "--repo-root",
                str(c.root),
                "--plan",
                relative(c.root, c.timeline_plan),
                "--output-root",
                relative(c.root, c.timeline_root),
                "--mode",
                "full",
                "--rehash-source",
            ],
            controls=lambda c: [
                c.verify_tool,
                c.timeline_plan,
                c.exact_manifest,
                *timeline_paths(c),
            ],
            outputs=lambda _c: [],
            validate_outputs=validate_timeline_outputs,
            prerequisite=verify_prerequisite,
            adopt_existing_outputs=False,
        ),
        Stage(
            name="mine_machine_provisional_registry",
            argv=lambda c: [
                c.python,
                str(c.family_tool),
                "--repo-root",
                str(c.root),
                "--plan",
                relative(c.root, c.family_plan),
                "--mode",
                "mine",
                "--index-root",
                relative(c.root, c.timeline_root),
                "--output",
                relative(c.root, c.candidate_registry),
            ],
            controls=lambda c: [
                c.family_tool,
                c.family_plan,
                *timeline_paths(c),
            ],
            outputs=lambda c: [c.candidate_registry],
            validate_outputs=validate_family_registry,
            prerequisite=family_prerequisite,
        ),
        Stage(
            name="validate_rehearsal_prerequisites",
            argv=lambda _c: [
                "internal:p23_102_post_acquisition_orchestrator",
                "validate_rehearsal_prerequisites",
            ],
            controls=lambda c: [
                c.root / "tools/p23_102_post_acquisition_orchestrator.py",
                *rehearsal_control_paths(c),
            ],
            outputs=lambda c: [c.readiness_report],
            validate_outputs=validate_readiness_report,
            prerequisite=readiness_prerequisite,
            internal=True,
            adopt_existing_outputs=False,
        ),
    )


Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


def subprocess_runner(
    argv: Sequence[str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


class Orchestrator:
    def __init__(
        self,
        config: Config,
        *,
        stages: Sequence[Stage] | None = None,
        runner: Runner = subprocess_runner,
        activity_probe: Callable[[Config], dict[str, Any]] = acquisition_activity,
    ) -> None:
        self.config = config
        self.stages = tuple(stages or default_stages())
        self.runner = runner
        self.activity_probe = activity_probe
        if tuple(stage.name for stage in self.stages) != STAGE_NAMES:
            raise ValueError("STAGE_ORDER_MISMATCH")

    def receipt_path(self, stage: Stage) -> Path:
        return self.config.receipts_dir / f"{stage.name}.json"

    def _path_snapshot(self, path: Path) -> dict[str, Any]:
        record: dict[str, Any] = {
            "path": relative(self.config.root, path),
            "exists": path.exists(),
        }
        if not path.exists():
            return record
        if path.is_symlink():
            record["kind"] = "symlink_forbidden"
            return record
        if not path.is_file():
            record["kind"] = "non_file"
            return record
        stat = path.stat()
        record.update(
            {
                "kind": "file",
                "bytes": stat.st_size,
                "mode": oct(stat.st_mode & 0o777),
                "mtime_ns": stat.st_mtime_ns,
                "inode": stat.st_ino,
            }
        )
        if path == self.config.final_media and self.config.exact_manifest.is_file():
            manifest = load_json(
                self.config.exact_manifest, label="EXACT_MANIFEST"
            )
            media = manifest.get("media", {}) if isinstance(manifest, Mapping) else {}
            if (
                isinstance(media, Mapping)
                and media.get("path") == relative(self.config.root, path)
                and media.get("bytes") == stat.st_size
                and len(str(media.get("sha256", ""))) == 64
            ):
                record["sha256"] = media["sha256"]
                record["sha256_source"] = relative(
                    self.config.root, self.config.exact_manifest
                )
                record["content_rehash"] = False
                return record
        record["sha256"] = sha256_file(path)
        record["sha256_source"] = "direct"
        record["content_rehash"] = True
        return record

    def _snapshot(self, paths: Sequence[Path]) -> list[dict[str, Any]]:
        return [
            self._path_snapshot(path)
            for path in sorted(
                set(paths), key=lambda item: relative(self.config.root, item)
            )
        ]

    def _attempt_path(self, stage: Stage, started: str) -> Path:
        stamp = (
            started.replace("-", "")
            .replace(":", "")
            .replace(".", "")
            .replace("Z", "Z")
        )
        return (
            self.config.attempts_dir
            / f"{stage.name}.{stamp}.{os.getpid()}.json"
        )

    def _write_attempt(
        self,
        *,
        stage: Stage,
        argv: Sequence[str],
        started: str,
        ended: str,
        return_code: int | None,
        stdout: str,
        stderr: str,
        execution_kind: str,
        prerequisite_evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        stdout_bytes = stdout.encode("utf-8")
        stderr_bytes = stderr.encode("utf-8")
        attempt: dict[str, Any] = {
            "schema_version": ATTEMPT_SCHEMA_VERSION,
            "stage": stage.name,
            "execution_kind": execution_kind,
            "command_argv": list(argv),
            "started_at_utc": started,
            "ended_at_utc": ended,
            "return_code": return_code,
            "stdout": {
                "bytes": len(stdout_bytes),
                "sha256": hashlib.sha256(stdout_bytes).hexdigest(),
                "tail": stdout[-STDIO_TAIL_CHARS:],
            },
            "stderr": {
                "bytes": len(stderr_bytes),
                "sha256": hashlib.sha256(stderr_bytes).hexdigest(),
                "tail": stderr[-STDIO_TAIL_CHARS:],
            },
            "prerequisite_evidence": dict(prerequisite_evidence),
        }
        seal(attempt, "attempt_sha256")
        atomic_json(self._attempt_path(stage, started), attempt)
        return attempt

    def _write_receipt(
        self,
        *,
        stage: Stage,
        attempt: Mapping[str, Any],
        output_validation: Mapping[str, Any],
    ) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "stage": stage.name,
            "recorded_at_utc": utc_now(),
            "execution": {
                "execution_kind": attempt["execution_kind"],
                "command_argv": attempt["command_argv"],
                "started_at_utc": attempt["started_at_utc"],
                "ended_at_utc": attempt["ended_at_utc"],
                "return_code": attempt["return_code"],
                "stdout": attempt["stdout"],
                "stderr": attempt["stderr"],
                "attempt_sha256": attempt["attempt_sha256"],
            },
            "control_snapshot": self._snapshot(stage.controls(self.config)),
            "output_snapshot": self._snapshot(stage.outputs(self.config)),
            "output_validation": dict(output_validation),
            "claim_boundary": {
                "machine_provisional_only": stage.name
                in {
                    "mine_machine_provisional_registry",
                    "validate_rehearsal_prerequisites",
                },
                "rehearsal_executed": False,
                "human_review_claimed": False,
                "accepted_ses_claimed": False,
                "h_tier_claimed": False,
                "gate_a_claimed": False,
            },
        }
        seal(receipt, "receipt_sha256")
        atomic_json(self.receipt_path(stage), receipt)
        return receipt

    def validate_receipt(self, stage: Stage) -> dict[str, Any]:
        path = self.receipt_path(stage)
        if not path.is_file() or path.is_symlink():
            raise StaleReceiptError(f"RECEIPT_MISSING:{stage.name}")
        receipt = load_json(path, label=f"RECEIPT_{stage.name}")
        if not isinstance(receipt, Mapping):
            raise StaleReceiptError(f"RECEIPT_NOT_OBJECT:{stage.name}")
        try:
            verify_seal(
                receipt, "receipt_sha256", label=f"RECEIPT_{stage.name}"
            )
        except OutputValidationError as exc:
            raise StaleReceiptError(str(exc)) from exc
        execution = receipt.get("execution", {})
        if (
            receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION
            or receipt.get("stage") != stage.name
            or execution.get("command_argv") != stage.argv(self.config)
            or execution.get("return_code") not in (0, None)
            or receipt.get("control_snapshot")
            != self._snapshot(stage.controls(self.config))
            or receipt.get("output_snapshot")
            != self._snapshot(stage.outputs(self.config))
        ):
            raise StaleReceiptError(
                f"RECEIPT_BINDING_STALE:{stage.name}"
            )
        if (
            execution.get("execution_kind") == "executed"
            and execution.get("return_code") != 0
        ):
            raise StaleReceiptError(
                f"RECEIPT_NONZERO_EXECUTION:{stage.name}"
            )
        validation = stage.validate_outputs(self.config)
        if receipt.get("output_validation") != validation:
            raise StaleReceiptError(
                f"RECEIPT_OUTPUT_VALIDATION_STALE:{stage.name}"
            )
        return dict(receipt)

    def _outputs_exist(self, stage: Stage) -> bool:
        outputs = stage.outputs(self.config)
        return bool(outputs) and any(path.exists() for path in outputs)

    def inspect_stage(self, stage: Stage) -> dict[str, Any]:
        receipt = self.receipt_path(stage)
        if receipt.exists():
            try:
                valid = self.validate_receipt(stage)
                return {
                    "stage": stage.name,
                    "state": "complete",
                    "receipt": relative(self.config.root, receipt),
                    "receipt_sha256": valid["receipt_sha256"],
                    "execution_kind": valid["execution"]["execution_kind"],
                }
            except (OrchestrationError, OSError) as exc:
                return {
                    "stage": stage.name,
                    "state": "stale_receipt",
                    "receipt": relative(self.config.root, receipt),
                    "error": str(exc),
                }
        if self._outputs_exist(stage):
            if not stage.adopt_existing_outputs:
                return {
                    "stage": stage.name,
                    "state": "ready_to_run",
                    "reason": "receipt_required_for_nonpersistent_verification",
                }
            try:
                validation = stage.validate_outputs(self.config)
                return {
                    "stage": stage.name,
                    "state": "adoptable",
                    "output_validation": validation,
                }
            except OrchestrationError as exc:
                return {
                    "stage": stage.name,
                    "state": "invalid_existing_outputs",
                    "error": str(exc),
                }
        try:
            evidence = stage.prerequisite(self.config)
            return {
                "stage": stage.name,
                "state": "ready_to_run",
                "prerequisite_evidence": evidence,
            }
        except OrchestrationError as exc:
            return {
                "stage": stage.name,
                "state": "blocked",
                "error": str(exc),
            }

    def status(self) -> dict[str, Any]:
        activity = self.activity_probe(self.config)
        rows: list[dict[str, Any]] = []
        prior_complete = True
        for stage in self.stages:
            row = self.inspect_stage(stage)
            if not prior_complete and row["state"] not in {
                "complete",
                "stale_receipt",
                "invalid_existing_outputs",
            }:
                row = {
                    "stage": stage.name,
                    "state": "waiting_for_previous_stage",
                }
            rows.append(row)
            prior_complete = row["state"] == "complete"
        all_complete = all(row["state"] == "complete" for row in rows)
        readiness: bool | None = None
        readiness_stage_complete = (
            rows[-1]["stage"] == "validate_rehearsal_prerequisites"
            and rows[-1]["state"] == "complete"
        )
        if readiness_stage_complete and self.config.readiness_report.is_file():
            report = load_json(
                self.config.readiness_report, label="READINESS_REPORT"
            )
            readiness = bool(
                report.get("ready_for_development_rehearsal")
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "decision": READY_TOKEN,
            "mode": "status",
            "generated_at_utc": utc_now(),
            "acquisition_activity": activity,
            "orchestrator_lock_held": orchestrator_lock_is_held(
                self.config
            ),
            "all_stages_complete": all_complete,
            "ready_for_development_rehearsal": readiness,
            "terminal_boundary": {
                "stops_after_machine_provisional_registry_and_readiness_audit": True,
                "rehearsal_executed": False,
                "human_review_claimed": False,
                "accepted_ses_claimed": False,
                "h_tier_claimed": False,
                "gate_a_claimed": False,
            },
            "stages": rows,
        }

    def _adopt(self, stage: Stage) -> dict[str, Any]:
        validation = stage.validate_outputs(self.config)
        now = utc_now()
        attempt = self._write_attempt(
            stage=stage,
            argv=stage.argv(self.config),
            started=now,
            ended=now,
            return_code=None,
            stdout="",
            stderr="",
            execution_kind="adopted_existing_valid_outputs",
            prerequisite_evidence={
                "adoption": True,
                "command_not_executed": True,
            },
        )
        return self._write_receipt(
            stage=stage,
            attempt=attempt,
            output_validation=validation,
        )

    def _execute(self, stage: Stage) -> dict[str, Any]:
        prerequisite_evidence = stage.prerequisite(self.config)
        argv = stage.argv(self.config)
        started = utc_now()
        if stage.internal:
            try:
                report = audit_rehearsal_prerequisites(self.config)
                atomic_json(self.config.readiness_report, report)
                completed = subprocess.CompletedProcess(
                    argv, 0, json.dumps(report, sort_keys=True) + "\n", ""
                )
            except (OSError, OrchestrationError) as exc:
                completed = subprocess.CompletedProcess(
                    argv, 2, "", f"{type(exc).__name__}:{exc}\n"
                )
        else:
            completed = self.runner(argv, self.config.root)
        ended = utc_now()
        attempt = self._write_attempt(
            stage=stage,
            argv=argv,
            started=started,
            ended=ended,
            return_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            execution_kind="executed",
            prerequisite_evidence=prerequisite_evidence,
        )
        if completed.returncode != 0:
            raise CommandFailure(
                f"STAGE_COMMAND_FAILED:{stage.name}:"
                f"return_code={completed.returncode}:"
                f"stderr_sha256={attempt['stderr']['sha256']}"
            )
        if stage.name == "verify_full_timeline":
            try:
                verifier = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise CommandFailure(
                    "INDEPENDENT_VERIFIER_STDOUT_NOT_JSON"
                ) from exc
            if (
                verifier.get("verified") is not True
                or verifier.get("decision") != TIMELINE_READY
            ):
                raise CommandFailure(
                    "INDEPENDENT_VERIFIER_DID_NOT_VERIFY"
                )
        validation = stage.validate_outputs(self.config)
        return self._write_receipt(
            stage=stage,
            attempt=attempt,
            output_validation=validation,
        )

    def run_stage(self, stage: Stage) -> dict[str, Any]:
        inspection = self.inspect_stage(stage)
        state = inspection["state"]
        if state == "complete":
            return {
                "stage": stage.name,
                "action": "skipped_valid_receipt",
                "receipt": inspection["receipt"],
            }
        if state == "stale_receipt":
            if (
                stage.name == "validate_rehearsal_prerequisites"
                and self.receipt_path(stage).is_file()
            ):
                self.receipt_path(stage).unlink()
                return self.run_stage(stage)
            raise StaleReceiptError(str(inspection["error"]))
        if state == "invalid_existing_outputs":
            raise OutputValidationError(str(inspection["error"]))
        if state == "blocked":
            raise PrerequisiteError(str(inspection["error"]))
        if state == "adoptable":
            receipt = self._adopt(stage)
            return {
                "stage": stage.name,
                "action": "adopted_existing_valid_outputs",
                "receipt_sha256": receipt["receipt_sha256"],
            }
        receipt = self._execute(stage)
        return {
            "stage": stage.name,
            "action": "executed",
            "receipt_sha256": receipt["receipt_sha256"],
        }

    def run_next_locked(self) -> dict[str, Any]:
        activity = self.activity_probe(self.config)
        if activity["active"]:
            raise ActiveAcquisitionError(
                ";".join(activity.get("blockers", []))
            )
        for stage in self.stages:
            inspection = self.inspect_stage(stage)
            if inspection["state"] == "complete":
                continue
            result = self.run_stage(stage)
            return {
                "schema_version": SCHEMA_VERSION,
                "decision": READY_TOKEN,
                "mode": "run-next",
                "result": result,
                "status": self.status(),
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "decision": READY_TOKEN,
            "mode": "run-next",
            "result": {"action": "already_complete"},
            "status": self.status(),
        }

    def run_next(self) -> dict[str, Any]:
        with ExclusiveLock(self.config.orchestrator_lock):
            return self.run_next_locked()

    def run_all(self) -> dict[str, Any]:
        with ExclusiveLock(self.config.orchestrator_lock):
            activity = self.activity_probe(self.config)
            if activity["active"]:
                raise ActiveAcquisitionError(
                    ";".join(activity.get("blockers", []))
                )
            actions: list[dict[str, Any]] = []
            for stage in self.stages:
                actions.append(self.run_stage(stage))
            return {
                "schema_version": SCHEMA_VERSION,
                "decision": READY_TOKEN,
                "mode": "run-all",
                "actions": actions,
                "status": self.status(),
            }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--run-next", action="store_true")
    mode.add_argument("--run-all", action="store_true")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    parser.add_argument("--state-dir")
    parser.add_argument("--threads", type=int, default=8)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.threads <= 0:
        raise SystemExit("--threads must be positive")
    config = default_config(
        args.repo_root,
        state_dir=args.state_dir,
        threads=args.threads,
    )
    orchestrator = Orchestrator(config)
    try:
        if args.status:
            result = orchestrator.status()
        elif args.run_next:
            result = orchestrator.run_next()
        else:
            result = orchestrator.run_all()
        print(json.dumps(result, indent=2, sort_keys=True))
        print(READY_TOKEN)
        return 0
    except ActiveAcquisitionError as exc:
        print(
            json.dumps(
                {
                    "decision": READY_TOKEN,
                    "status": "BLOCKED_ACTIVE_ACQUISITION",
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    except (
        CommandFailure,
        OrchestrationError,
        OSError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {
                    "decision": READY_TOKEN,
                    "status": "FAILED_CLOSED",
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
