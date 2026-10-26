#!/usr/bin/env python3
"""Run the fail-closed P23_102 technical smoke v2 wiring.

This is a 32-assignment, smoke-only integration check. It is not a benchmark,
competence evaluation, semantic validation, or authorization to run the full
P23 rehearsal matrix.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import stat
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Self

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from av_trace_scale1b_agent.checkpoint import canonical_bytes, semantic_hash
from av_trace_scale1b_agent.process import (
    FreshQwenProcessFactory,
    ProcessConfig,
    QwenProcess,
)

SCHEMA = "av-trace.p23-102-technical-smoke-v2-runner/1.0"
PLAN_SCHEMA = "av-trace.p23-102-technical-smoke-v2-plan/1.0"
FROZEN_DATE = "2026-10-14"

REPAIRED_RUNNER_REL = Path(
    "scripts/run_p23_102_acquire_ground_act_rehearsal.py"
)
CONFIG_REL = Path(
    "data/rehearsal_plan/p23_102_technical_smoke_v2.json"
)
ADAPTER_ATTESTATION_REL = Path(
    "data/restricted/p23_102_technical_smoke_v2/"
    "adapter_attestation.json"
)
OUTPUT_ROOT_REL = Path(
    "data/restricted/p23_102_technical_smoke_v2/runs"
)
BUNDLE_REL = Path(
    "data/restricted/epic_p23_102_machine_provisional_families_v1"
)
INDEX_REL = Path(
    "data/restricted/epic_p23_102_full_timeline_index_v1"
)
QWEN_MANIFEST_REL = Path(
    "data/restricted/scale1b/manifests/ga_model_acquisition.json"
)
RETRIEVAL_MODEL_MANIFEST_REL = Path(
    "data/restricted/scale1b/manifests/wave_r_model_acquisition.json"
)
WHISPER_SNAPSHOT_REL = Path(
    "data/restricted/noaa01/models/whisper-tiny.en-87c7102"
)
WHISPER_SHA256SUMS_REL = WHISPER_SNAPSHOT_REL / "SHA256SUMS"

EXPECTED_QWEN_REPO = "Qwen/Qwen2.5-1.5B-Instruct"
EXPECTED_QWEN_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
EXPECTED_SIGLIP2_REPO = "google/siglip2-base-patch16-224"
EXPECTED_SIGLIP2_REVISION = "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"
EXPECTED_CLAP_REPO = "laion/clap-htsat-unfused"
EXPECTED_CLAP_REVISION = "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a"
EXPECTED_WHISPER_REPO = "openai/whisper-tiny.en"
EXPECTED_WHISPER_REVISION = "87c7102498dcde7456f24cfd30239ca606ed9063"
ARMS = ("C", "B", "R", "N")

ABORT_THRESHOLDS = {
    "assignment_count": 32,
    "checkpoint_pair_count": 12,
    "max_model_generate_calls_per_assignment": 11,
    "max_total_model_generate_calls": 352,
    "max_provider_call_seconds": 120.0,
    "max_assignment_seconds": 900.0,
    "max_process_failures": 2,
    "max_malformed_after_repair": 3,
    "max_typed_tool_contract_violations": 2,
    "max_runtime_private_leakage_hits": 0,
    "max_isolation_collisions": 0,
    "required_completion_rows_per_assignment": 1,
}

AUTHORIZATION_SCHEMA = (
    "av-trace.p23-102-smoke-approval-overlay/1.0"
)
AUTHORITY_REGISTRY_REL = Path(
    "data/restricted/p23_102_technical_smoke_v2/authority_registry.json"
)
AUTHORITY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{7,127}$")
NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
SIGNATURE_RE = re.compile(r"^[A-Za-z0-9+/=_:-]{32,4096}$")
CHECKPOINT_SHA256 = (
    "sha256:c580c16af6401b4d12df1d39085bbddee6f63e6d81772f6b3186a0fcc84c996c"
)

OUTPUT_FILES = (
    "run_manifest.json",
    "plan.json",
    "model_inventory_pre_spawn.json",
    "assignments.jsonl",
    "provider_call_journal.jsonl",
    "raw_trajectories.jsonl",
    "raw_model_calls.jsonl",
    "factor_model_raw_outputs.jsonl",
    "public_trajectories.jsonl",
    "private_arm_evidence_mappings.jsonl",
    "r_n_prefix_pairs.jsonl",
    "checkpoint_delivery.json",
    "episode_metrics.jsonl",
    "metric_ready_records.jsonl",
    "metrics.jsonl",
    "citation_outputs.jsonl",
    "failure_ledger.jsonl",
    "completion_ledger.jsonl",
    "abort_ledger.jsonl",
    "unstarted_assignments.jsonl",
    "process_session_isolation.json",
    "runtime_leakage_surface.json",
    "b_r_n_prefix_identity.json",
    "aggregate_metrics.json",
    "replay_manifest.json",
    "raw_retention_manifest.json",
    "file_inventory.json",
    "artifact_manifest.json",
)

PRIVATE_KEY_FRAGMENTS = {
    "accepted_ses",
    "arm",
    "evidence_by_observation",
    "evidence_handle",
    "intervention",
    "necessity_group",
    "observation_private",
    "pointer_private",
    "restoration_applied",
    "route_group",
    "suppressed_segment_ids",
    "triggered",
}
PRIVATE_KEYS_EXACT = {
    "known_observation_ids",
    "known_pointer_ids",
}
SNAPSHOT_HARMLESS_ALLOWLIST = frozenset({"SHA256SUMS"})
_TEST_EXECUTION_CAPABILITY = object()


class TechnicalSmokeError(RuntimeError):
    """Typed fail-closed technical-smoke error."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class TechnicalSmokeHardAbort(BaseException):
    """Non-recoverable runtime abort that repaired-runner handlers cannot eat."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class ModelLike(Protocol):
    """Minimal model process surface consumed by the repaired runner."""

    def generate(
        self,
        *,
        system: str,
        payload: Mapping[str, Any],
        max_new_tokens: int,
    ) -> dict[str, Any]: ...


class BackendLike(Protocol):
    """Marker protocol for injected smoke backends."""


class AuthorityVerifier(Protocol):
    """Trusted pluggable verifier supplied by the authority integration."""

    def verify_overlay(
        self,
        *,
        overlay_path: Path,
        registry_path: Path,
        now: dt.datetime,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class RepositoryAuthorityVerifier:
    """Adapter over the separately owned strict Ed25519 authority module."""

    module_path: Path = REPO_ROOT / "tools/p23_102_smoke_authority.py"

    def verify_overlay(
        self,
        *,
        overlay_path: Path,
        registry_path: Path,
        now: dt.datetime,
    ) -> Mapping[str, Any]:
        if (
            not self.module_path.is_file()
            or self.module_path.is_symlink()
        ):
            raise TechnicalSmokeError("AUTHORITY_VERIFIER_UNAVAILABLE")
        spec = importlib.util.spec_from_file_location(
            "p23_102_smoke_authority_for_runner",
            self.module_path,
        )
        if spec is None or spec.loader is None:
            raise TechnicalSmokeError("AUTHORITY_VERIFIER_UNAVAILABLE")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.verify_overlay_file(
            overlay_path,
            registry_path=registry_path,
            now=now,
        )


@dataclass(frozen=True)
class SmokeInputs:
    """Current frozen P23 and pinned-model inputs."""

    families: dict[str, Any]
    evidence: dict[str, Any]
    interventions: dict[str, Any]
    leakage: dict[str, Any]
    index: dict[str, Any]
    build_manifest: dict[str, Any]
    segment_manifest: dict[str, Any]
    qwen_manifest: dict[str, Any]


@dataclass
class ProviderCallJournal:
    """Append-only durable request/result journal for every provider call."""

    path: Path
    sequence: int = 0
    requests: dict[str, dict[str, Any]] = field(default_factory=dict)
    terminal_rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    interrupt_after_raw: Callable[[Mapping[str, Any]], None] | None = None
    interrupt_after_terminal: Callable[[Mapping[str, Any]], None] | None = None

    def record_request(self, row: Mapping[str, Any]) -> None:
        call_id = str(row["call_id"])
        if call_id in self.requests:
            raise TechnicalSmokeError("PROVIDER_CALL_ID_COLLISION", call_id)
        request_row = copy.deepcopy(dict(row))
        self.requests[call_id] = request_row
        self._append("request", request_row)

    def record_terminal(self, row: Mapping[str, Any]) -> None:
        call_id = str(row["call_id"])
        if call_id not in self.requests:
            raise TechnicalSmokeError(
                "PROVIDER_TERMINAL_WITHOUT_REQUEST", call_id
            )
        if call_id in self.terminal_rows:
            raise TechnicalSmokeError(
                "PROVIDER_DUPLICATE_TERMINAL", call_id
            )
        terminal = copy.deepcopy(dict(row))
        _append_jsonl_durable(
            self.path.parent / "raw_model_calls.jsonl", terminal
        )
        _append_jsonl_durable(
            self.path.parent / "factor_model_raw_outputs.jsonl",
            self._factor_projection(terminal),
        )
        if self.interrupt_after_raw is not None:
            self.interrupt_after_raw(terminal)
        self._append("terminal", terminal)
        self.terminal_rows[call_id] = terminal
        if self.interrupt_after_terminal is not None:
            self.interrupt_after_terminal(terminal)

    def annotate_terminal(self, row: Mapping[str, Any]) -> None:
        """Durably replace a terminal projection after runner validation."""

        call_id = str(row["call_id"])
        previous = self.terminal_rows.get(call_id)
        if previous is None:
            raise TechnicalSmokeError(
                "PROVIDER_ANNOTATION_WITHOUT_TERMINAL", call_id
            )
        if (
            previous.get("trajectory_id") != row.get("trajectory_id")
            or previous.get("process_label") != row.get("process_label")
        ):
            return
        annotated = copy.deepcopy(dict(row))
        prospective = dict(self.terminal_rows)
        prospective[call_id] = annotated
        _atomic_write_jsonl(
            self.path.parent / "raw_model_calls.jsonl",
            list(prospective.values()),
        )
        _atomic_write_jsonl(
            self.path.parent / "factor_model_raw_outputs.jsonl",
            [
                self._factor_projection(terminal)
                for terminal in prospective.values()
            ],
        )
        self._append("terminal_annotation", annotated)
        self.terminal_rows[call_id] = annotated

    def close_open_requests(self, *, code: str, detail: str) -> None:
        """Write synthetic terminal failures for every durable open request."""

        raw_by_id = {
            str(row.get("call_id")): row
            for row in _read_jsonl_strict(
                self.path.parent / "raw_model_calls.jsonl"
            )
        }
        for call_id, raw in raw_by_id.items():
            if call_id not in self.requests:
                continue
            previous = self.terminal_rows.get(call_id)
            if previous is None:
                self._append("terminal", raw)
                self.terminal_rows[call_id] = copy.deepcopy(raw)
            elif previous != raw:
                self._append("terminal_annotation", raw)
                self.terminal_rows[call_id] = copy.deepcopy(raw)
        for call_id, request in list(self.requests.items()):
            if call_id in self.terminal_rows:
                continue
            failure = {
                "type": "InterruptedProviderCall",
                "code": code,
                "message": detail,
            }
            raw_bytes = canonical_bytes(failure)
            failure["raw_diagnostic_bytes_sha256"] = _bytes_sha256(raw_bytes)
            failure["raw_diagnostic_bytes_length"] = len(raw_bytes)
            terminal = {
                **copy.deepcopy(request),
                "response": None,
                "failure": failure,
                "latency_seconds_observed": None,
            }
            terminal["call_sha256"] = semantic_hash(terminal)
            self.record_terminal(terminal)

    def _append(self, event: str, payload: Mapping[str, Any]) -> None:
        self.sequence += 1
        _append_jsonl_durable(
            self.path,
            {
                "journal_sequence": self.sequence,
                "event": event,
                "persisted_at_utc": _utc_text(),
                "payload": copy.deepcopy(dict(payload)),
            },
        )

    @staticmethod
    def _factor_projection(terminal: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "call_id": terminal["call_id"],
            "trajectory_id": terminal["trajectory_id"],
            "process_label": terminal["process_label"],
            "call_index": terminal["call_index"],
            "repaired_runner_attempt": terminal.get(
                "repaired_runner_attempt"
            ),
            "failure": terminal.get("failure"),
        }


@dataclass
class RecordingModel:
    """Capture exact worker requests, responses, and process failures."""

    worker: ModelLike
    trajectory_id: str
    process_label: str
    calls: list[dict[str, Any]]
    call_guard: Callable[[str, float | None], None] | None = None
    journal: ProviderCallJournal | None = None
    failure_guard: Callable[[Mapping[str, Any]], None] | None = None

    def generate(
        self,
        *,
        system: str,
        payload: Mapping[str, Any],
        max_new_tokens: int,
    ) -> dict[str, Any]:
        if self.call_guard is not None:
            self.call_guard(self.process_label, None)
        request = {
            "system": system,
            "payload": copy.deepcopy(dict(payload)),
            "max_new_tokens": max_new_tokens,
        }
        call_id = (
            f"{self.process_label}:{len(self.calls)}:{uuid.uuid4().hex}"
        )
        row: dict[str, Any] = {
            "call_id": call_id,
            "trajectory_id": self.trajectory_id,
            "process_label": self.process_label,
            "call_index": len(self.calls),
            "request": request,
            "request_sha256": semantic_hash(request),
            "response": None,
            "failure": None,
        }
        if self.journal is not None:
            self.journal.record_request(
                {
                    "call_id": call_id,
                    "trajectory_id": self.trajectory_id,
                    "process_label": self.process_label,
                    "call_index": len(self.calls),
                    "request": request,
                    "request_sha256": row["request_sha256"],
                }
            )
        try:
            started = time.monotonic()
            response = self.worker.generate(
                system=system,
                payload=payload,
                max_new_tokens=max_new_tokens,
            )
        except BaseException as exc:
            elapsed = time.monotonic() - started
            failure: dict[str, Any] = {
                "type": type(exc).__name__,
                "code": str(getattr(exc, "code", type(exc).__name__)),
                "message": str(exc),
            }
            to_record = getattr(exc, "to_record", None)
            if callable(to_record):
                failure["record"] = to_record()
            details = getattr(exc, "details", None)
            if isinstance(details, Mapping):
                failure["details"] = copy.deepcopy(dict(details))
            raw_bytes = _canonical_failure_bytes(exc, failure)
            failure["raw_diagnostic_bytes_sha256"] = _bytes_sha256(raw_bytes)
            failure["raw_diagnostic_bytes_length"] = len(raw_bytes)
            row["latency_seconds_observed"] = elapsed
            row["failure"] = failure
            row["call_sha256"] = semantic_hash(row)
            self.calls.append(row)
            if self.journal is not None:
                self.journal.record_terminal(row)
            if self.failure_guard is not None:
                self.failure_guard(failure)
            if self.call_guard is not None:
                self.call_guard(self.process_label, elapsed)
            raise
        elapsed = time.monotonic() - started
        row["response"] = copy.deepcopy(dict(response))
        row["latency_seconds_observed"] = elapsed
        row["call_sha256"] = semantic_hash(row)
        self.calls.append(row)
        if self.journal is not None:
            self.journal.record_terminal(row)
        if self.call_guard is not None:
            self.call_guard(self.process_label, elapsed)
        return response


def _terminate_worker_process_group(worker: Any) -> dict[str, Any]:
    process = getattr(worker, "process", None)
    pid = getattr(process, "pid", None)
    pgid: int | None = None
    if isinstance(pid, int):
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            pgid = pid
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    closer = getattr(worker, "close", None)
    close_error: dict[str, str] | None = None
    if callable(closer):
        try:
            closer()
        except Exception as exc:  # noqa: BLE001 - cleanup must continue
            close_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
    return {
        "pid": pid,
        "process_group_id": pgid,
        "sigkill_sent": isinstance(pgid, int),
        "close_error": close_error,
    }


@dataclass
class AssignmentDeadline:
    """Active wall-clock deadline that kills registered worker groups."""

    seconds: float
    assignment_ids: tuple[str, ...]
    workers: list[Any] = field(default_factory=list)
    terminated_workers: list[dict[str, Any]] = field(default_factory=list)
    _previous_handler: Any = None

    def register(self, worker: Any) -> None:
        self.workers.append(worker)

    def register_pid(self, pid: int) -> None:
        """Register a startup process before a full worker exists."""

        process = type("_StartupProcess", (), {"pid": pid})()
        worker = type(
            "_StartupWorker",
            (),
            {"process": process, "close": lambda self: None},
        )()
        self.register(worker)

    def create_worker(self, factory: Any, label: str) -> Any:
        creator = getattr(factory, "create", None)
        return _create_worker_under_deadline(
            creator if callable(creator) else factory,
            label,
            deadline=self,
        )

    def _handle_timeout(self, _signum: int, _frame: Any) -> None:
        self.terminated_workers = [
            _terminate_worker_process_group(worker)
            for worker in list(self.workers)
        ]
        raise TechnicalSmokeHardAbort(
            "ASSIGNMENT_DEADLINE_EXCEEDED",
            ",".join(self.assignment_ids),
        )

    def __enter__(self) -> Self:
        if (
            self.seconds <= 0
            or not hasattr(signal, "SIGALRM")
            or not hasattr(signal, "setitimer")
        ):
            return self
        self._previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, self._handle_timeout)
        signal.setitimer(signal.ITIMER_REAL, self.seconds)
        return self

    def __exit__(self, *_: object) -> None:
        if (
            self._previous_handler is not None
            and hasattr(signal, "SIGALRM")
            and hasattr(signal, "setitimer")
        ):
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            signal.signal(signal.SIGALRM, self._previous_handler)


@dataclass
class ProcessRegistry:
    """Create one fresh worker per assignment or continuation arm."""

    factory: Any
    attestations: dict[str, dict[str, Any]]
    deadline: AssignmentDeadline | None = None

    @contextlib.contextmanager
    def worker(self, assignment: Mapping[str, Any]) -> Iterator[ModelLike]:
        label = str(assignment["assignment_id"])
        with _created_worker(
            self.factory, label, deadline=self.deadline
        ) as worker:
            attestation = _worker_attestation(worker, label)
            attestation["assignment_id"] = label
            attestation["arm"] = assignment["arm"]
            self.attestations[label] = attestation
            yield worker

    @contextlib.contextmanager
    def pair(
        self,
        r_assignment: Mapping[str, Any],
        n_assignment: Mapping[str, Any],
    ) -> Iterator[tuple[ModelLike, ModelLike]]:
        r_label = str(r_assignment["assignment_id"])
        n_label = str(n_assignment["assignment_id"])
        with contextlib.ExitStack() as stack:
            restored = stack.enter_context(
                _created_worker(
                    self.factory, r_label, deadline=self.deadline
                )
            )
            no_trigger = stack.enter_context(
                _created_worker(
                    self.factory, n_label, deadline=self.deadline
                )
            )
            for assignment, worker in (
                (r_assignment, restored),
                (n_assignment, no_trigger),
            ):
                label = str(assignment["assignment_id"])
                attestation = _worker_attestation(worker, label)
                attestation["assignment_id"] = label
                attestation["arm"] = assignment["arm"]
                self.attestations[label] = attestation
            yield restored, no_trigger

    @contextlib.contextmanager
    def prefix(self, pair_id: str) -> Iterator[ModelLike]:
        label = f"{pair_id}:prefix"
        with _created_worker(
            self.factory, label, deadline=self.deadline
        ) as worker:
            self.attestations[label] = _worker_attestation(worker, label)
            yield worker


_REPAIRED_RUNNER: Any | None = None


def _repaired_runner() -> Any:
    """Load the repaired runner without making the scripts directory a package."""

    global _REPAIRED_RUNNER
    if _REPAIRED_RUNNER is not None:
        return _REPAIRED_RUNNER
    path = REPO_ROOT / REPAIRED_RUNNER_REL
    spec = importlib.util.spec_from_file_location(
        "p23_102_repaired_rehearsal_runner_for_smoke_v2",
        path,
    )
    if spec is None or spec.loader is None:
        raise TechnicalSmokeError(
            "REPAIRED_RUNNER_IMPORT_FAILED", str(path)
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _REPAIRED_RUNNER = module
    return module


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TechnicalSmokeError("INVALID_JSON", f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TechnicalSmokeError("INVALID_SCHEMA", f"{path}: not an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _bytes_sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_failure_bytes(
    exc: BaseException, failure: Mapping[str, Any]
) -> bytes:
    for name in (
        "raw_bytes",
        "diagnostic_bytes",
        "stderr_bytes",
        "stdout_bytes",
    ):
        value = getattr(exc, name, None)
        if isinstance(value, bytes):
            return value
    for name in ("raw_text", "stderr", "stdout"):
        value = getattr(exc, name, None)
        if isinstance(value, str):
            return value.encode("utf-8", errors="surrogatepass")
    return canonical_bytes(dict(failure))


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(
                json.dumps(
                    value,
                    sort_keys=True,
                    indent=2,
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode()
                + b"\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_write_jsonl(
    path: Path, rows: Sequence[Mapping[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for row in rows:
                handle.write(canonical_bytes(dict(row)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _append_jsonl_durable(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        0o600,
    )
    try:
        payload = canonical_bytes(dict(row)) + b"\n"
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)
    _fsync_directory(path.parent)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _utc_text(value: dt.datetime | None = None) -> str:
    current = value or _utc_now()
    return current.astimezone(dt.UTC).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_utc(value: Any, field: str) -> dt.datetime:
    if not isinstance(value, str):
        raise TechnicalSmokeError(
            "AUTHORIZATION_SCHEMA_INVALID", f"{field}: not a string"
        )
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise TechnicalSmokeError(
            "AUTHORIZATION_SCHEMA_INVALID", f"{field}: invalid UTC"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise TechnicalSmokeError(
            "AUTHORIZATION_SCHEMA_INVALID", f"{field}: UTC required"
        )
    return parsed


def _exact_keys(
    value: Any, expected: set[str], location: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TechnicalSmokeError(
            "AUTHORIZATION_SCHEMA_INVALID",
            f"{location}: object required",
        )
    actual = {str(key) for key in value}
    if actual != expected:
        raise TechnicalSmokeError(
            "AUTHORIZATION_SCHEMA_INVALID",
            f"{location}: expected={sorted(expected)} actual={sorted(actual)}",
        )
    return value


def _authorization_expected_hashes(
    root: Path,
    *,
    output_root: Path,
    plan: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, str]:
    config = _load(root / CONFIG_REL)
    modules = [
        {
            "path": str(record["path"]),
            "sha256": _sha256(root / str(record["path"])),
        }
        for record in config.get("frozen_bindings", [])
    ]
    models = _model_binding_projection(validation["local_models"])
    assignments = [
        {
            "assignment_id": row["assignment_id"],
            "trajectory_id": row["trajectory_id"],
            "ordinal": row["ordinal"],
        }
        for row in plan["assignments"]
    ]
    checkpoint = {
        "event": config["checkpoint_contract"]["event"],
        "event_sha256": CHECKPOINT_SHA256,
        "action_index_zero_based": 4,
    }
    return {
        "freeze_sha256": _sha256(root / CONFIG_REL),
        "adapter_attestation_sha256": _sha256(
            root / ADAPTER_ATTESTATION_REL
        ),
        "runner_sha256": _sha256(
            root / "scripts/run_p23_102_technical_smoke_v2.py"
        ),
        "module_set_sha256": semantic_hash(modules),
        "all_model_set_sha256": semantic_hash(models),
        "assignment_plan_sha256": semantic_hash(assignments),
        "checkpoint_contract_sha256": semantic_hash(checkpoint),
        "output_root_sha256": semantic_hash(str(output_root)),
        "repaired_runner_sha256": validation["repaired_runner"]["sha256"],
    }


def _validate_authorization_overlay(
    path: Path,
    *,
    root: Path,
    output_root: Path,
    plan: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    return _validate_authorization_overlay_with_verifier(
        path,
        root=root,
        output_root=output_root,
        plan=plan,
        validation=validation,
        authority_verifier=RepositoryAuthorityVerifier(
            root / "tools/p23_102_smoke_authority.py"
        ),
    )


def _validate_authorization_overlay_for_test(
    path: Path,
    *,
    root: Path,
    output_root: Path,
    plan: Mapping[str, Any],
    validation: Mapping[str, Any],
    authority_verifier: AuthorityVerifier,
) -> dict[str, Any]:
    """Explicit test-only verifier injection, unavailable from the CLI."""

    return _validate_authorization_overlay_with_verifier(
        path,
        root=root,
        output_root=output_root,
        plan=plan,
        validation=validation,
        authority_verifier=authority_verifier,
    )


def _validate_authorization_overlay_with_verifier(
    path: Path,
    *,
    root: Path,
    output_root: Path,
    plan: Mapping[str, Any],
    validation: Mapping[str, Any],
    authority_verifier: AuthorityVerifier,
) -> dict[str, Any]:
    record = _load(path)
    if record["schema_version"] != AUTHORIZATION_SCHEMA:
        raise TechnicalSmokeError("AUTHORIZATION_SCHEMA_INVALID")
    expected_keys = {
        "schema_version",
        "authorization_id",
        "issued_at_utc",
        "expires_at_utc",
        "bound_execution",
        "approvals",
    }
    _exact_keys(record, expected_keys, "authorization_overlay")
    bound = _exact_keys(
        record["bound_execution"],
        {"bindings", "one_run_nonce", "declarations", "review_decision"},
        "bound_execution",
    )
    nonce = bound["one_run_nonce"]
    if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
        raise TechnicalSmokeError("AUTHORIZATION_NONCE_INVALID")
    expected = _authorization_expected_hashes(
        root,
        output_root=output_root,
        plan=plan,
        validation=validation,
    )
    if dict(bound["bindings"]) != expected:
        raise TechnicalSmokeError(
            "AUTHORIZATION_BINDING_MISMATCH",
            json.dumps(
                {"expected": expected, "actual": dict(bound["bindings"])},
                sort_keys=True,
            ),
        )
    declarations = _exact_keys(
        bound["declarations"],
        {
            "technical_smoke_only",
            "no_scientific_interpretation",
            "no_competence_or_performance_interpretation",
            "single_run_only",
            "immutable_freeze_remains_unauthorized",
        },
        "declarations",
    )
    if (
        bound["review_decision"] != "GO"
        or any(value is not True for value in declarations.values())
    ):
        raise TechnicalSmokeError(
            "AUTHORIZATION_ACKNOWLEDGEMENT_MISSING"
        )
    registry_path = root / AUTHORITY_REGISTRY_REL
    if not registry_path.is_file():
        raise TechnicalSmokeError("AUTHORITY_REGISTRY_REQUIRED")
    now = _utc_now()
    try:
        verification = authority_verifier.verify_overlay(
            overlay_path=path,
            registry_path=registry_path,
            now=now,
        )
    except BaseException as exc:
        raise TechnicalSmokeError(
            "AUTHORITY_SIGNATURE_VERIFICATION_FAILED", str(exc)
        ) from exc
    if (
        not isinstance(verification, Mapping)
        or verification.get("status") != "OVERLAY_APPROVALS_VALID"
        or verification.get("authorization_id")
        != record["authorization_id"]
    ):
        raise TechnicalSmokeError(
            "AUTHORITY_SIGNATURE_VERIFICATION_FAILED",
            "official verifier did not return the required authorization",
        )
    return {
        "authorization_id": record["authorization_id"],
        "issued_at_utc": record["issued_at_utc"],
        "expires_at_utc": record["expires_at_utc"],
        "one_run_nonce_sha256": semantic_hash(nonce),
        "overlay_sha256": _sha256(path),
        "authority_registry": {
            "path": str(AUTHORITY_REGISTRY_REL),
            "sha256": _sha256(registry_path),
        },
        "authority_verifier": {
            "implementation": type(authority_verifier).__name__,
            "module_path": str(
                getattr(authority_verifier, "module_path", "")
            ),
            "module_sha256": (
                _sha256(authority_verifier.module_path)
                if isinstance(
                    getattr(authority_verifier, "module_path", None),
                    Path,
                )
                else None
            ),
        },
        "authority_verification": copy.deepcopy(dict(verification)),
        "approvals": {
            role: {
                "role": role,
                "authority_id": approval["signed_payload"]["authority_id"],
                "key_fingerprint": approval["signed_payload"][
                    "key_fingerprint"
                ],
                "receipt_id": approval["signed_payload"]["receipt_id"],
                "issued_at_utc": approval["signed_payload"]["issued_at_utc"],
                "expires_at_utc": approval["signed_payload"][
                    "expires_at_utc"
                ],
                "signed_payload_sha256": semantic_hash(
                    approval["signed_payload"]
                ),
                "receipt_sha256": semantic_hash(approval),
            }
            for role, approval in record["approvals"].items()
        },
        "bindings": expected,
        "acknowledgements": copy.deepcopy(dict(declarations)),
    }


def _remove_reserved_output_root(output_root: Path) -> None:
    if output_root.is_dir() and not output_root.is_symlink():
        shutil.rmtree(output_root)
        _fsync_directory(output_root.parent)


def _reserve_output_root(
    output_root: Path,
    *,
    repo_root: Path,
    authorization: Mapping[str, Any] | None,
) -> None:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    if output_root.exists() or output_root.is_symlink():
        raise TechnicalSmokeError(
            "OUTPUT_ROOT_ALREADY_EXISTS", str(output_root)
        )
    try:
        output_root.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise TechnicalSmokeError(
            "OUTPUT_ROOT_ALREADY_EXISTS", str(output_root)
        ) from exc
    os.chmod(output_root, 0o700)
    try:
        marker = output_root / ".output_root_reservation.json"
        descriptor = os.open(
            marker,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            payload = canonical_bytes(
                {
                    "authorization_id": (
                        None
                        if authorization is None
                        else authorization["authorization_id"]
                    ),
                    "one_run_nonce_sha256": (
                        None
                        if authorization is None
                        else authorization["one_run_nonce_sha256"]
                    ),
                    "reserved_at_utc": _utc_text(),
                }
            ) + b"\n"
            written = 0
            while written < len(payload):
                written += os.write(descriptor, payload[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(output_root)
        _fsync_directory(output_root.parent)

        if authorization is None:
            return
        nonce_root = repo_root / OUTPUT_ROOT_REL / ".authorization_nonces"
        nonce_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(nonce_root, 0o700)
        nonce_hash = str(authorization["one_run_nonce_sha256"])
        nonce_reservation = nonce_root / f"{nonce_hash[7:]}.json"
        try:
            descriptor = os.open(
                nonce_reservation,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError as exc:
            raise TechnicalSmokeError(
                "AUTHORIZATION_NONCE_ALREADY_USED", nonce_hash
            ) from exc
        try:
            payload = canonical_bytes(
                {
                    "authorization_id": authorization["authorization_id"],
                    "one_run_nonce_sha256": nonce_hash,
                    "output_root": str(output_root),
                    "reserved_at_utc": _utc_text(),
                }
            ) + b"\n"
            written = 0
            while written < len(payload):
                written += os.write(descriptor, payload[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(nonce_root)
    except BaseException:
        _remove_reserved_output_root(output_root)
        raise


def _required_current_paths() -> tuple[Path, ...]:
    return (
        REPAIRED_RUNNER_REL,
        CONFIG_REL,
        BUNDLE_REL / "family_registry.json",
        BUNDLE_REL / "evidence_registry.json",
        BUNDLE_REL / "intervention_manifest.json",
        BUNDLE_REL / "leakage_gate.json",
        INDEX_REL / "build_manifest.json",
        INDEX_REL / "full_timeline_index.json",
        INDEX_REL / "segment_manifest.json",
        QWEN_MANIFEST_REL,
        RETRIEVAL_MODEL_MANIFEST_REL,
        WHISPER_SHA256SUMS_REL,
        ADAPTER_ATTESTATION_REL,
    )


def _load_inputs(root: Path) -> SmokeInputs:
    return SmokeInputs(
        families=_load(root / BUNDLE_REL / "family_registry.json"),
        evidence=_load(root / BUNDLE_REL / "evidence_registry.json"),
        interventions=_load(
            root / BUNDLE_REL / "intervention_manifest.json"
        ),
        leakage=_load(root / BUNDLE_REL / "leakage_gate.json"),
        index=_load(root / INDEX_REL / "full_timeline_index.json"),
        build_manifest=_load(root / INDEX_REL / "build_manifest.json"),
        segment_manifest=_load(root / INDEX_REL / "segment_manifest.json"),
        qwen_manifest=_load(root / QWEN_MANIFEST_REL),
    )


def _snapshot_file_inventory(
    snapshot: Path,
    *,
    error_prefix: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Hash every regular snapshot file and reject non-regular entries."""

    if not snapshot.is_dir() or snapshot.is_symlink():
        return [], []
    files: list[dict[str, Any]] = []
    errors: list[str] = []
    for current_root, directory_names, file_names in os.walk(
        snapshot,
        followlinks=False,
    ):
        current = Path(current_root)
        for name in sorted(directory_names):
            path = current / name
            relative = path.relative_to(snapshot).as_posix()
            if path.is_symlink():
                errors.append(
                    f"{error_prefix}_NONREGULAR_ENTRY:{relative}"
                )
        for name in sorted(file_names):
            path = current / name
            relative = path.relative_to(snapshot).as_posix()
            if path.is_symlink() or not path.is_file():
                errors.append(
                    f"{error_prefix}_NONREGULAR_ENTRY:{relative}"
                )
                continue
            files.append(
                {
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    files.sort(key=lambda row: str(row["path"]))
    return files, errors


def _validate_snapshot_sha256sums(
    sums_path: Path,
    *,
    required: Mapping[str, Mapping[str, Any]],
    error_prefix: str,
) -> list[str]:
    """Bind the harmless SHA256SUMS allowlist file to the exact manifest."""

    errors: list[str] = []
    entries: dict[str, str] = {}
    try:
        lines = sums_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [f"{error_prefix}_HARMLESS_ALLOWLIST_UNBOUND:SHA256SUMS"]
    for line in lines:
        digest, separator, relative = line.partition("  ")
        if (
            not separator
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not relative
            or relative in entries
        ):
            errors.append(
                f"{error_prefix}_HARMLESS_ALLOWLIST_INVALID:SHA256SUMS"
            )
            continue
        entries[relative] = f"sha256:{digest}"
    expected = {}
    for relative, record in required.items():
        digest = str(record.get("sha256", ""))
        expected[relative] = (
            digest if digest.startswith("sha256:") else f"sha256:{digest}"
        )
    if entries != expected:
        errors.append(
            f"{error_prefix}_HARMLESS_ALLOWLIST_UNBOUND:SHA256SUMS"
        )
    return errors


def _local_model_identity(
    root: Path,
    *,
    manifest_path: Path,
    model: Mapping[str, Any],
    expected_repo: str,
    expected_revision: str,
    error_prefix: str,
) -> dict[str, Any]:
    snapshot_value = str(model.get("snapshot_dir", ""))
    snapshot = Path(snapshot_value)
    if not snapshot.is_absolute():
        snapshot = root / snapshot
    files = model.get("files", [])
    required = {
        str(row.get("path")): {
            "bytes": row.get("bytes"),
            "sha256": str(row.get("sha256", "")),
        }
        for row in files
        if isinstance(row, Mapping)
    }
    errors: list[str] = []
    validated_files: list[dict[str, Any]] = []
    if model.get("repo_id") != expected_repo:
        errors.append(f"{error_prefix}_REPO_MISMATCH")
    if model.get("revision") != expected_revision:
        errors.append(f"{error_prefix}_REVISION_MISMATCH")
    if not snapshot.is_dir() or snapshot.is_symlink():
        errors.append(f"{error_prefix}_SNAPSHOT_MISSING")
    actual_files, inventory_errors = _snapshot_file_inventory(
        snapshot,
        error_prefix=error_prefix,
    )
    errors.extend(inventory_errors)
    actual_paths = {str(row["path"]) for row in actual_files}
    allowed_paths = set(required) | SNAPSHOT_HARMLESS_ALLOWLIST
    for relative in sorted(actual_paths - allowed_paths):
        errors.append(f"{error_prefix}_UNEXPECTED_FILE:{relative}")
    harmless_paths = actual_paths & SNAPSHOT_HARMLESS_ALLOWLIST
    sums_path = snapshot / "SHA256SUMS"
    if "SHA256SUMS" in harmless_paths:
        errors.extend(
            _validate_snapshot_sha256sums(
                sums_path,
                required=required,
                error_prefix=error_prefix,
            )
        )
    for relative in sorted(required):
        record = required.get(relative)
        path = snapshot / relative
        if record is None:
            errors.append(f"{error_prefix}_MANIFEST_FILE_MISSING:{relative}")
        elif not path.is_file() or path.is_symlink():
            errors.append(f"{error_prefix}_LOCAL_FILE_MISSING:{relative}")
        elif (
            isinstance(record["bytes"], int)
            and path.stat().st_size != record["bytes"]
        ):
            errors.append(f"{error_prefix}_LOCAL_FILE_SIZE:{relative}")
        else:
            expected_sha = str(record["sha256"])
            if not expected_sha.startswith("sha256:"):
                expected_sha = "sha256:" + expected_sha
            actual_sha = _sha256(path)
            if actual_sha != expected_sha:
                errors.append(f"{error_prefix}_LOCAL_FILE_HASH:{relative}")
            validated_files.append(
                {
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": actual_sha,
                    "expected_sha256": expected_sha,
                }
            )
    for record in actual_files:
        if record["path"] in harmless_paths:
            validated_files.append(
                {
                    **record,
                    "expected_sha256": record["sha256"],
                    "inventory_role": "frozen_harmless_allowlist",
                }
            )
    validated_files.sort(key=lambda row: str(row["path"]))
    return {
        "ready": not errors,
        "errors": errors,
        "repo_id": model.get("repo_id"),
        "revision": model.get("revision"),
        "snapshot_path": str(snapshot),
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256(root / manifest_path),
        "validated_files": validated_files,
        "validated_file_set_sha256": semantic_hash(validated_files),
        "local_files_only": True,
        "exact_snapshot_inventory": True,
        "harmless_allowlist": sorted(SNAPSHOT_HARMLESS_ALLOWLIST),
    }


def _qwen_identity(
    root: Path, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    return _local_model_identity(
        root,
        manifest_path=QWEN_MANIFEST_REL,
        model=manifest.get("model", {}),
        expected_repo=EXPECTED_QWEN_REPO,
        expected_revision=EXPECTED_QWEN_REVISION,
        error_prefix="QWEN",
    )


def _sha256sums_model_identity(
    root: Path,
    *,
    snapshot_rel: Path,
    sums_rel: Path,
    expected_repo: str,
    expected_revision: str,
    error_prefix: str,
) -> dict[str, Any]:
    snapshot = root / snapshot_rel
    sums_path = root / sums_rel
    errors: list[str] = []
    required: list[dict[str, Any]] = []
    try:
        lines = sums_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
        errors.append(f"{error_prefix}_MANIFEST_MISSING")
    prefix = snapshot_rel.as_posix() + "/"
    for line in lines:
        digest, separator, relative = line.partition("  ")
        if (
            not separator
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not relative.startswith(prefix)
        ):
            errors.append(f"{error_prefix}_MANIFEST_INVALID")
            continue
        local_relative = relative[len(prefix) :]
        required.append(
            {
                "path": local_relative,
                "sha256": f"sha256:{digest}",
            }
        )
    validated_files: list[dict[str, Any]] = []
    if not snapshot.is_dir() or snapshot.is_symlink():
        errors.append(f"{error_prefix}_SNAPSHOT_MISSING")
    actual_files, inventory_errors = _snapshot_file_inventory(
        snapshot,
        error_prefix=error_prefix,
    )
    errors.extend(inventory_errors)
    actual_paths = {str(row["path"]) for row in actual_files}
    required_paths = {str(row["path"]) for row in required}
    allowed_paths = required_paths | SNAPSHOT_HARMLESS_ALLOWLIST
    for relative in sorted(actual_paths - allowed_paths):
        errors.append(f"{error_prefix}_UNEXPECTED_FILE:{relative}")
    for record in sorted(required, key=lambda row: str(row["path"])):
        relative = str(record["path"])
        path = snapshot / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"{error_prefix}_LOCAL_FILE_MISSING:{relative}")
            continue
        actual_sha = _sha256(path)
        if actual_sha != record["sha256"]:
            errors.append(f"{error_prefix}_LOCAL_FILE_HASH:{relative}")
        validated_files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": actual_sha,
                "expected_sha256": record["sha256"],
            }
        )
    for record in actual_files:
        if record["path"] in SNAPSHOT_HARMLESS_ALLOWLIST:
            validated_files.append(
                {
                    **record,
                    "expected_sha256": record["sha256"],
                    "inventory_role": "frozen_harmless_allowlist",
                }
            )
    validated_files.sort(key=lambda row: str(row["path"]))
    if not required:
        errors.append(f"{error_prefix}_MANIFEST_EMPTY")
    return {
        "ready": not errors,
        "errors": errors,
        "repo_id": expected_repo,
        "revision": expected_revision,
        "snapshot_path": str(snapshot),
        "manifest_path": str(sums_rel),
        "manifest_sha256": (
            _sha256(sums_path) if sums_path.is_file() else None
        ),
        "validated_files": validated_files,
        "validated_file_set_sha256": semantic_hash(validated_files),
        "local_files_only": True,
        "inventory_only_control": True,
        "exact_snapshot_inventory": True,
        "harmless_allowlist": sorted(SNAPSHOT_HARMLESS_ALLOWLIST),
    }


def _local_model_identities(
    root: Path,
    qwen_manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    retrieval_manifest = _load(root / RETRIEVAL_MODEL_MANIFEST_REL)
    retrieval_models = retrieval_manifest.get("models", {})
    if not isinstance(retrieval_models, Mapping):
        retrieval_models = {}
    return {
        "qwen": _qwen_identity(root, qwen_manifest),
        "siglip2": _local_model_identity(
            root,
            manifest_path=RETRIEVAL_MODEL_MANIFEST_REL,
            model=(
                retrieval_models.get("siglip2", {})
                if isinstance(retrieval_models.get("siglip2", {}), Mapping)
                else {}
            ),
            expected_repo=EXPECTED_SIGLIP2_REPO,
            expected_revision=EXPECTED_SIGLIP2_REVISION,
            error_prefix="SIGLIP2",
        ),
        "clap": _local_model_identity(
            root,
            manifest_path=RETRIEVAL_MODEL_MANIFEST_REL,
            model=(
                retrieval_models.get("clap", {})
                if isinstance(retrieval_models.get("clap", {}), Mapping)
                else {}
            ),
            expected_repo=EXPECTED_CLAP_REPO,
            expected_revision=EXPECTED_CLAP_REVISION,
            error_prefix="CLAP",
        ),
        "whisper": _sha256sums_model_identity(
            root,
            snapshot_rel=WHISPER_SNAPSHOT_REL,
            sums_rel=WHISPER_SHA256SUMS_REL,
            expected_repo=EXPECTED_WHISPER_REPO,
            expected_revision=EXPECTED_WHISPER_REVISION,
            error_prefix="WHISPER",
        ),
    }


def _model_binding_projection(
    identities: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "manifest_sha256": identity["manifest_sha256"],
            "validated_file_set_sha256": identity[
                "validated_file_set_sha256"
            ],
        }
        for name, identity in sorted(identities.items())
    }


def _revalidate_model_inventory_before_spawn(
    root: Path,
    *,
    validation: Mapping[str, Any],
    authorization: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Re-hash exact model inventories at the last pre-spawn boundary."""

    inputs = _load_inputs(root)
    identities = _local_model_identities(root, inputs.qwen_manifest)
    errors = [
        str(error)
        for identity in identities.values()
        for error in identity["errors"]
    ]
    if errors:
        raise TechnicalSmokeError(
            "PRE_SPAWN_MODEL_INVENTORY_INVALID", ",".join(errors)
        )
    model_bindings = _model_binding_projection(identities)
    all_model_set_sha256 = semantic_hash(model_bindings)
    initial_bindings = _model_binding_projection(
        validation["local_models"]
    )
    initial_all_model_set_sha256 = semantic_hash(initial_bindings)
    if model_bindings != initial_bindings:
        raise TechnicalSmokeError(
            "PRE_SPAWN_MODEL_INVENTORY_DRIFT"
        )
    signed_all_model_set_sha256 = None
    if authorization is not None:
        signed_all_model_set_sha256 = authorization["bindings"][
            "all_model_set_sha256"
        ]
        if all_model_set_sha256 != signed_all_model_set_sha256:
            raise TechnicalSmokeError(
                "PRE_SPAWN_MODEL_INVENTORY_AUTHORIZATION_MISMATCH"
            )
    return {
        "schema_version": SCHEMA,
        "checked_at_utc": _utc_text(),
        "models": copy.deepcopy(identities),
        "model_bindings": model_bindings,
        "all_model_set_sha256": all_model_set_sha256,
        "initial_all_model_set_sha256": initial_all_model_set_sha256,
        "signed_overlay_all_model_set_sha256": (
            signed_all_model_set_sha256
        ),
        "equals_initial_validation": (
            all_model_set_sha256 == initial_all_model_set_sha256
        ),
        "equals_signed_overlay": (
            None
            if signed_all_model_set_sha256 is None
            else all_model_set_sha256 == signed_all_model_set_sha256
        ),
        "worker_spawned_before_check": False,
    }


def validate_repository(
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    """Validate planning inputs without loading models or decoding media."""

    root = Path(repo_root).resolve()
    missing = [
        str(path)
        for path in _required_current_paths()
        if not (root / path).is_file()
    ]
    if missing:
        return {
            "schema_version": SCHEMA,
            "mode": "validate-only",
            "validation_status": "NOT_READY",
            "execution_authorized": False,
            "execution_authorization_reasons": ["PREREQUISITE_MISSING"],
            "missing": missing,
            "model_or_media_execution_performed": False,
        }
    inputs = _load_inputs(root)
    config = _load(root / CONFIG_REL)
    errors: list[str] = []
    if inputs.build_manifest.get("status") != "COMPLETE":
        errors.append("P23_INDEX_NOT_COMPLETE")
    if (
        inputs.build_manifest.get("decision")
        != "EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY"
    ):
        errors.append("P23_INDEX_DECISION_NOT_READY")
    if inputs.index.get("source_ref") != "P23_102":
        errors.append("P23_INDEX_SOURCE_MISMATCH")
    if inputs.families.get("status") != "MACHINE_PROVISIONAL_FROZEN":
        errors.append("P23_FAMILY_BUNDLE_NOT_FROZEN")
    if (
        inputs.interventions.get("status")
        != "MECHANISM_SPECIFIC_FROZEN"
    ):
        errors.append("P23_INTERVENTIONS_NOT_FROZEN")
    if inputs.leakage.get("status") != "PASS":
        errors.append("P23_BUNDLE_PROVENANCE_FIREWALL_NOT_PASS")
    if (
        inputs.segment_manifest.get("source_sha256")
        != inputs.families.get("source_sha256")
    ):
        errors.append("P23_SOURCE_BINDING_MISMATCH")
    local_models = _local_model_identities(root, inputs.qwen_manifest)
    for identity in local_models.values():
        errors.extend(identity["errors"])
    qwen = local_models["qwen"]
    local_model_file_set_sha256 = semantic_hash(
        {
            name: {
                "repo_id": identity["repo_id"],
                "revision": identity["revision"],
                **binding,
            }
            for name, binding in _model_binding_projection(
                local_models
            ).items()
            for identity in (local_models[name],)
        }
    )
    repaired = _repaired_runner()
    repaired_validation = repaired.validate_repository(root)
    if repaired_validation.get("validation_status") != "READY":
        errors.append("REPAIRED_RUNNER_VALIDATION_NOT_READY")
    repaired_sha256 = _sha256(root / REPAIRED_RUNNER_REL)
    binding_drift = []
    for record in config.get("frozen_bindings", []):
        relative = Path(str(record.get("path", "")))
        path = root / relative
        if not path.is_file():
            binding_drift.append(
                {"path": str(relative), "error": "MISSING"}
            )
            continue
        actual = _sha256(path)
        if actual != record.get("sha256"):
            binding_drift.append(
                {
                    "path": str(relative),
                    "error": "HASH_MISMATCH",
                    "expected_sha256": record.get("sha256"),
                    "actual_sha256": actual,
                }
            )
    if binding_drift:
        errors.append("V2_FROZEN_BINDING_DRIFT")
    adapter = _load(root / ADAPTER_ATTESTATION_REL)
    if config.get("authorization", {}).get("execution_authorized") is not False:
        errors.append("IMMUTABLE_FREEZE_AUTHORIZATION_CHANGED")
    if adapter.get("execution_authorized") is not False:
        errors.append("IMMUTABLE_ADAPTER_AUTHORIZATION_CHANGED")
    reasons = ["STRICT_AUTHORIZATION_OVERLAY_REQUIRED"]
    if errors:
        reasons.append("TECHNICAL_SMOKE_PREREQUISITES_NOT_READY")
    return {
        "schema_version": SCHEMA,
        "mode": "validate-only",
        "validation_status": "READY" if not errors else "NOT_READY",
        "planning_authorized": not errors,
        "execution_authorized": False,
        "execution_authorization_reasons": reasons,
        "errors": errors,
        "current_p23_inputs": {
            "family_count": inputs.families.get("family_count"),
            "evidence_count": inputs.evidence.get("evidence_count"),
            "intervention_count": inputs.interventions.get(
                "intervention_count"
            ),
            "index_source_ref": inputs.index.get("source_ref"),
            "index_build_status": inputs.build_manifest.get("status"),
        },
        "qwen": qwen,
        "local_models": local_models,
        "local_model_file_set_sha256": local_model_file_set_sha256,
        "offline_runtime_required": True,
        "network_namespace_denial_required": True,
        "repaired_runner": {
            "path": str(REPAIRED_RUNNER_REL),
            "sha256": repaired_sha256,
            "validation_status": repaired_validation.get(
                "validation_status"
            ),
            "full_rehearsal_execution_authorized": repaired_validation.get(
                "execution_authorized"
            ),
        },
        "v2_authorization": {
            "config_path": str(CONFIG_REL),
            "adapter_attestation_path": str(ADAPTER_ATTESTATION_REL),
            "strict_overlay_required": True,
            "overlay_present": False,
            "immutable_freeze_execution_authorized": False,
            "immutable_adapter_execution_authorized": False,
        },
        "v2_config": {
            "schema_version": config.get("schema_version"),
            "status": config.get("status"),
            "decision_token": config.get("decision_token"),
            "assignment_count": config.get("assignment_plan", {}).get(
                "assignment_count"
            ),
            "frozen_binding_drift": binding_drift,
        },
        "claims": {
            "semantic_validity": False,
            "model_competence": False,
            "performance": False,
            "causal_effect": False,
            "gate_a": False,
            "h2": False,
        },
        "model_or_media_execution_performed": False,
    }


def build_plan(repo_root: str | Path = ".") -> dict[str, Any]:
    """Build the exact deterministic 32-assignment frozen smoke plan."""

    root = Path(repo_root).resolve()
    validation = validate_repository(root)
    if validation["validation_status"] != "READY":
        raise TechnicalSmokeError(
            "VALIDATION_NOT_READY", ",".join(validation["errors"])
        )
    inputs = _load_inputs(root)
    config = _load(root / CONFIG_REL)
    families = {
        str(row["family_id"]): dict(row)
        for row in inputs.families["families"]
    }
    frozen_assignments = config["assignment_plan"]["assignments"]
    assignments = []
    for frozen in frozen_assignments:
        family_id = str(frozen["family_id"])
        family = families.get(family_id)
        if family is None:
            raise TechnicalSmokeError(
                "CONFIGURED_FAMILY_NOT_FOUND", family_id
            )
        assignment_id = str(frozen["assignment_id"])
        assignments.append(
            {
                **copy.deepcopy(dict(frozen)),
                "trajectory_id": (
                    "p23trajv2."
                    + hashlib.sha256(
                        assignment_id.encode()
                    ).hexdigest()[:24]
                ),
                "source_id": "P23_102",
                "checkpoint_action_index_zero_based": 4,
                "expected_evidence_handle_ids": sorted(
                    str(item)
                    for item in family["evidence_handle_ids"]
                ),
                "smoke_only": True,
            }
        )
    if [row["ordinal"] for row in assignments] != list(
        range(1, len(assignments) + 1)
    ):
        raise TechnicalSmokeError("ASSIGNMENT_ORDER_MISMATCH")
    configured_ids_hash = config["assignment_plan"].get(
        "assignment_ids_sha256"
    )
    actual_ids_hash = semantic_hash(
        [row["assignment_id"] for row in assignments]
    )
    if configured_ids_hash != actual_ids_hash:
        raise TechnicalSmokeError(
            "ASSIGNMENT_ID_HASH_MISMATCH",
            f"{configured_ids_hash}!={actual_ids_hash}",
        )
    plan_identity = {
        "config_plan_sha256": config.get("deterministic_hashes", {}).get(
            "plan_sha256_excluding_this_field"
        ),
        "assignment_ids_sha256": actual_ids_hash,
        "qwen_revision": EXPECTED_QWEN_REVISION,
    }
    return {
        "schema_version": PLAN_SCHEMA,
        "mode": "plan",
        "status": "PLAN_READY",
        "created_date": FROZEN_DATE,
        "smoke_only": True,
        "development_only": True,
        "assignment_count": len(assignments),
        "assignments": assignments,
        "abort_thresholds": copy.deepcopy(config["abort_thresholds"]),
        "plan_hash": semantic_hash(
            {"identity": plan_identity, "assignments": assignments}
        ),
        "execution_authorized": validation["execution_authorized"],
        "execution_authorization_reasons": validation[
            "execution_authorization_reasons"
        ],
        "model_or_media_execution_performed": False,
        "claims": validation["claims"],
    }


def _rows_for_assignment(
    inputs: SmokeInputs, assignment: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    family_id = str(assignment["family_id"])
    mechanism = str(assignment["mechanism"])
    family = next(
        (
            dict(row)
            for row in inputs.families["families"]
            if row["family_id"] == family_id
        ),
        None,
    )
    if family is None:
        raise TechnicalSmokeError("ASSIGNMENT_FAMILY_NOT_FOUND", family_id)
    evidence = [
        dict(row)
        for row in inputs.evidence["evidence"]
        if row["family_id"] == family_id
    ]
    intervention = next(
        (
            dict(row)
            for row in inputs.interventions["interventions"]
            if row["family_id"] == family_id
            and row["mechanism"] == mechanism
        ),
        None,
    )
    if intervention is None:
        raise TechnicalSmokeError(
            "ASSIGNMENT_INTERVENTION_NOT_FOUND",
            f"{family_id}:{mechanism}",
        )
    return family, evidence, intervention


def _default_backend_factory(
    root: Path, inputs: SmokeInputs
) -> Callable[[Mapping[str, Any]], BackendLike]:
    repaired = _repaired_runner()

    def create(assignment: Mapping[str, Any]) -> BackendLike:
        family, evidence, intervention = _rows_for_assignment(
            inputs, assignment
        )
        return repaired.P23FullTimelineBackendAdapter(
            root,
            family=family,
            evidence_rows=evidence,
            intervention=intervention,
            mechanism=str(assignment["mechanism"]),
            arm=str(assignment["arm"]),
        )

    return create


def _default_process_factory(
    qwen: Mapping[str, Any],
) -> FreshQwenProcessFactory:
    snapshot = Path(str(qwen["snapshot_path"]))
    return FreshQwenProcessFactory(
        snapshot,
        config=ProcessConfig(
            threads=4,
            max_context_tokens=24576,
            deny_network_namespace=True,
        ),
    )


def _create_worker_under_deadline(
    creator: Callable[[str], Any],
    label: str,
    *,
    deadline: AssignmentDeadline,
) -> Any:
    """Create a worker while retaining a killable startup-process handle."""

    owner = getattr(creator, "__self__", None)
    startup_creator = getattr(owner, "create_under_deadline", None)
    if callable(startup_creator):
        worker = startup_creator(label, deadline)
        if not any(worker is registered for registered in deadline.workers):
            deadline.register(worker)
        return worker
    if (
        owner is not None
        and isinstance(owner, FreshQwenProcessFactory)
        and getattr(creator, "__func__", None)
        is FreshQwenProcessFactory.create
    ):
        factory = owner
        command = (
            factory.command_factory(label)
            if factory.command_factory is not None
            else (
                list(factory.command)
                if factory.command is not None
                else None
            )
        )
        nonce = uuid.uuid4().hex
        worker = QwenProcess.__new__(QwenProcess)
        deadline.register(worker)
        QwenProcess.__init__(
            worker,
            factory.snapshot,
            config=factory.config,
            command=command,
            session_id=f"session-{nonce}",
            cache_namespace=f"cache-{nonce}",
            continuation_label=label,
        )
        return worker
    worker = creator(label)
    if not any(worker is registered for registered in deadline.workers):
        deadline.register(worker)
    return worker


@contextlib.contextmanager
def _created_worker(
    factory: Any,
    label: str,
    *,
    deadline: AssignmentDeadline | None = None,
) -> Iterator[ModelLike]:
    creator = getattr(factory, "create", None)
    creator = creator if callable(creator) else factory
    worker = (
        _create_worker_under_deadline(creator, label, deadline=deadline)
        if deadline is not None
        else creator(label)
    )
    try:
        yield worker
    finally:
        closer = getattr(worker, "close", None)
        if callable(closer):
            closer()


def _worker_attestation(worker: Any, label: str) -> dict[str, Any]:
    method = getattr(worker, "isolation_attestation", None)
    if callable(method):
        value = method()
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            record = dict(to_dict())
        elif isinstance(value, Mapping):
            record = dict(value)
        else:
            raise TechnicalSmokeError(
                "INVALID_PROCESS_ATTESTATION", label
            )
    else:
        metadata = getattr(worker, "metadata", {})
        record = dict(metadata) if isinstance(metadata, Mapping) else {}
        for key in (
            "session_id",
            "cache_namespace",
            "pid",
            "process_group_id",
            "runtime_namespace",
            "network_namespace_denied",
            "offline_environment",
        ):
            if key not in record and hasattr(worker, key):
                record[key] = getattr(worker, key)
    record["process_label"] = label
    return record


def _isolation_report(
    attestations: Sequence[Mapping[str, Any]],
    *,
    expected_assignment_labels: set[str],
    extra_attestations: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    all_attestations = [*attestations, *extra_attestations]
    collision_fields = (
        "session_id",
        "cache_namespace",
        "pid",
        "process_group_id",
        "runtime_namespace",
    )
    collisions = []
    for collision_field in collision_fields:
        values: dict[str, list[str]] = {}
        for row in all_attestations:
            value = str(row.get(collision_field))
            values.setdefault(value, []).append(str(row["process_label"]))
        for value, labels in values.items():
            if value in {"", "None"} or len(labels) > 1:
                collisions.append(
                    {
                        "field": collision_field,
                        "value": value,
                        "labels": labels,
                    }
                )
    offline = all(
        row.get("offline_environment") is True for row in all_attestations
    )
    network_denied = all(
        row.get("network_namespace_denied") is True
        for row in all_attestations
    )
    return {
        "status": (
            "PASS"
            if not collisions and offline and network_denied
            else "FAIL"
        ),
        "attestations": [dict(row) for row in all_attestations],
        "collisions": collisions,
        "offline_environment_all_processes": offline,
        "network_namespace_denied_all_processes": network_denied,
        "fresh_process_per_assignment": expected_assignment_labels
        <= {
            str(row["process_label"])
            for row in all_attestations
        },
        "dedicated_prefix_process_count": sum(
            str(row["process_label"]).endswith(":prefix")
            for row in all_attestations
        ),
        "shared_conversation_state": False,
        "shared_kv_state": False,
    }


def _state_private_mapping(
    assignment: Mapping[str, Any],
    state: Any,
    process: Mapping[str, Any],
    intervention: Mapping[str, Any],
) -> dict[str, Any]:
    backend = state.backend
    snapshot = backend.snapshot()
    return {
        "trajectory_id": assignment["trajectory_id"],
        "assignment_id": assignment["assignment_id"],
        "family_id": assignment["family_id"],
        "mechanism": assignment["mechanism"],
        "arm": assignment["arm"],
        "intervention_id": intervention.get("intervention_id"),
        "route_group_id": intervention.get("route_group_id"),
        "suppressed_segment_ids_registered": sorted(
            str(item)
            for item in intervention.get("suppressed_segment_ids", [])
        ),
        "expected_evidence_handle_ids": assignment[
            "expected_evidence_handle_ids"
        ],
        "backend_private_snapshot": copy.deepcopy(snapshot),
        "observation_private": copy.deepcopy(
            dict(getattr(backend, "observation_private", {}))
        ),
        "evidence_by_observation": copy.deepcopy(
            dict(getattr(backend, "evidence_by_observation", {}))
        ),
        "process": dict(process),
    }


def _public_trajectory(
    assignment: Mapping[str, Any], state: Any
) -> dict[str, Any]:
    repaired = _repaired_runner()
    citation = repaired.validate_citations(
        state.final, state.observations
    )
    completion = (
        "COMPLETED_VALID"
        if state.final is not None
        and state.failure is None
        and citation["valid"]
        else (state.failure or {}).get("code", "INVALID_SCHEMA")
    )
    return {
        "trajectory_id": assignment["trajectory_id"],
        "system_id": assignment["system_id"],
        "episode_start": copy.deepcopy(state.start),
        "events": copy.deepcopy(state.events),
        "final_output": copy.deepcopy(state.final),
        "observations": list(copy.deepcopy(state.observations).values()),
        "completion_status": completion,
        "citation_schema_validation": citation,
        "public_no_progress_rounds": state.no_progress_rounds,
        "public_trajectory_sha256": semantic_hash(
            {
                "start": state.start,
                "events": state.events,
                "final": state.final,
                "observations": state.observations,
            }
        ),
    }


def _metric_row(
    assignment: Mapping[str, Any],
    state: Any,
    *,
    checkpoint_delivered: bool,
    raw_calls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    remaining = state.backend.snapshot()
    malformed = sum(
        1
        for row in state.model_calls
        if row.get("status") in {"invalid", "process_error"}
    )
    return {
        "trajectory_id": assignment["trajectory_id"],
        "assignment_id": assignment["assignment_id"],
        "arm": assignment["arm"],
        "completion_status": _public_trajectory(
            assignment, state
        )["completion_status"],
        "typed_failure_code": (
            None if state.failure is None else state.failure.get("code")
        ),
        "checkpoint_delivered": checkpoint_delivered,
        "public_action_count": sum(
            1 for event in state.events if "action" in event
        ),
        "public_event_count": sum(
            1 for event in state.events if "event" in event
        ),
        "observation_count": len(state.observations),
        "exact_model_generate_call_count": len(raw_calls),
        "invalid_or_process_attempt_count": malformed,
        "steps_used": int(state.backend.budget["max_steps"])
        - int(remaining["remaining_steps"]),
        "cost_used": round(
            float(state.backend.budget["cost_limit"])
            - float(remaining["remaining_cost"]),
            6,
        ),
        "technical_wiring_only": True,
        "semantic_score_reported": False,
        "performance_claim_reported": False,
    }


def _failure_row(
    assignment: Mapping[str, Any], state: Any
) -> dict[str, Any]:
    return {
        "assignment_id": assignment["assignment_id"],
        "trajectory_id": assignment["trajectory_id"],
        "completion_status": _public_trajectory(
            assignment, state
        )["completion_status"],
        "failure": copy.deepcopy(state.failure),
        "one_terminal_row": True,
    }


def _private_values(
    private_rows: Sequence[Mapping[str, Any]],
) -> set[str]:
    values: set[str] = set()
    value_keys = {
        "family_id",
        "intervention_id",
        "route_group_id",
        "record_id",
        "evidence_handle",
        "expected_evidence_handle_ids",
        "suppressed_segment_ids",
        "suppressed_segment_ids_registered",
        "evidence_by_observation",
    }

    def collect(value: Any, *, sensitive: bool = False) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                normalized = str(key).casefold()
                child_sensitive = normalized in value_keys
                collect(child, sensitive=child_sensitive)
        elif isinstance(value, (list, tuple, set)):
            for child in value:
                collect(child, sensitive=sensitive)
        elif (
            sensitive
            and isinstance(value, str)
            and len(value) >= 6
            and (
                "." in value
                or value.startswith(("P23", "record"))
            )
        ):
            values.add(value)

    for row in private_rows:
        for key in (
            "family_id",
            "intervention_id",
            "route_group_id",
        ):
            value = row.get(key)
            if isinstance(value, str) and value:
                values.add(value)
        for key in (
            "suppressed_segment_ids_registered",
            "expected_evidence_handle_ids",
        ):
            values.update(str(item) for item in row.get(key, []))
        collect(row)
    return values


def _walk_leakage(
    value: Any,
    *,
    location: str,
    private_values: set[str],
    hits: list[dict[str, Any]],
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold()
            if normalized in PRIVATE_KEYS_EXACT or any(
                fragment in normalized
                for fragment in PRIVATE_KEY_FRAGMENTS
            ):
                hits.append(
                    {
                        "location": f"{location}.{key}",
                        "kind": "private_key",
                        "value": str(key),
                    }
                )
            _walk_leakage(
                child,
                location=f"{location}.{key}",
                private_values=private_values,
                hits=hits,
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_leakage(
                child,
                location=f"{location}[{index}]",
                private_values=private_values,
                hits=hits,
            )
    elif isinstance(value, str):
        normalized = value.casefold()
        for fragment in PRIVATE_KEY_FRAGMENTS | PRIVATE_KEYS_EXACT:
            if fragment in normalized:
                hits.append(
                    {
                        "location": location,
                        "kind": "embedded_private_key",
                        "value_sha256": semantic_hash(value),
                    }
                )
                break
        for private in private_values:
            if private in value:
                hits.append(
                    {
                        "location": location,
                        "kind": (
                            "private_value"
                            if private == value
                            else "embedded_private_value"
                        ),
                        "private_value_sha256": semantic_hash(private),
                        "value_sha256": semantic_hash(value),
                    }
                )


def _runtime_leakage_report(
    raw_calls: Sequence[Mapping[str, Any]],
    public_trajectories: Sequence[Mapping[str, Any]],
    private_rows: Sequence[Mapping[str, Any]],
    public_outputs: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    private_values = _private_values(private_rows)
    for index, row in enumerate(raw_calls):
        for surface_field in (
            "request",
            "response",
            "failure",
            "repaired_runner_attempt",
        ):
            _walk_leakage(
                row.get(surface_field),
                location=f"raw_model_calls[{index}].{surface_field}",
                private_values=private_values,
                hits=hits,
            )
    for index, row in enumerate(public_trajectories):
        _walk_leakage(
            row,
            location=f"public_trajectories[{index}]",
            private_values=private_values,
            hits=hits,
        )
    for index, row in enumerate(public_outputs):
        _walk_leakage(
            row,
            location=f"public_outputs[{index}]",
            private_values=private_values,
            hits=hits,
        )
    scan = {
        "status": "PASS" if not hits else "FAIL",
        "scanner": "recursive_exact_and_embedded_private_surface_scan_v2",
        "model_call_count": len(raw_calls),
        "public_trajectory_count": len(public_trajectories),
        "public_output_count": len(public_outputs),
        "private_value_count": len(private_values),
        "leakage_hit_count": len(hits),
        "hits": hits,
    }
    return {
        "status": "NOT_ESTIMABLE_SINGLE_SOURCE",
        "mechanical_private_surface_scan": scan,
        "runtime_leakage_classifier": {
            "status": "NOT_ESTIMABLE_SINGLE_SOURCE",
            "pass_allowed": False,
            "reason": (
                "P23_102 has one source group; the recursive mechanical "
                "private-surface scan is not a runtime leakage classifier."
            ),
        },
        "bundle_provenance_firewall_is_distinct": True,
    }


def _attach_attempt_validation(
    exact_calls: list[dict[str, Any]],
    state: Any,
    *,
    journal: ProviderCallJournal | None = None,
) -> None:
    attempts = list(state.model_calls)
    for index, call in enumerate(exact_calls):
        call["repaired_runner_attempt"] = (
            copy.deepcopy(attempts[index])
            if index < len(attempts)
            else None
        )
        call["call_sha256"] = semantic_hash(
            {key: value for key, value in call.items() if key != "call_sha256"}
        )
        if journal is not None:
            journal.annotate_terminal(call)


def _run_state_with_worker(
    assignment: Mapping[str, Any],
    state: Any,
    worker: ModelLike,
    *,
    arm: str,
) -> tuple[Any, list[dict[str, Any]]]:
    repaired = _repaired_runner()
    exact_calls: list[dict[str, Any]] = []
    model = RecordingModel(
        worker=worker,
        trajectory_id=str(assignment["trajectory_id"]),
        process_label=arm,
        calls=exact_calls,
    )
    repaired._continue_state(
        state,
        system_id=str(assignment["system_id"]),
        arm=arm,
        model=model,
    )
    _attach_attempt_validation(exact_calls, state)
    return state, exact_calls


def _run_endpoint(
    assignment: Mapping[str, Any],
    *,
    backend_factory: Callable[[Mapping[str, Any]], BackendLike],
    registry: ProcessRegistry,
    call_guard: Callable[[str, float | None], None] | None = None,
    journal: ProviderCallJournal | None = None,
    failure_guard: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    repaired = _repaired_runner()
    backend = backend_factory(assignment)
    system_id = str(assignment["system_id"])
    arm = str(assignment["arm"])
    if system_id == "direct_long_context":
        state = repaired.PrefixState(
            backend=backend,
            start=backend.public_start(),
            pointers={},
            observations={},
            events=[],
            model_calls=[],
            factor_outputs=[],
        )
        repaired._pack_direct_long_context(state)
        with registry.worker(assignment) as worker:
            exact_calls: list[dict[str, Any]] = []
            model = RecordingModel(
                worker=worker,
                trajectory_id=str(assignment["trajectory_id"]),
                process_label=str(assignment["assignment_id"]),
                calls=exact_calls,
                call_guard=call_guard,
                journal=journal,
                failure_guard=failure_guard,
            )
            repaired._finalize_state(
                state, model, f"{arm}:direct_long_context"
            )
            _attach_attempt_validation(
                exact_calls, state, journal=journal
            )
            calls = exact_calls
    else:
        with registry.worker(assignment) as worker:
            exact_calls = []
            model = RecordingModel(
                worker=worker,
                trajectory_id=str(assignment["trajectory_id"]),
                process_label=str(assignment["assignment_id"]),
                calls=exact_calls,
                call_guard=call_guard,
                journal=journal,
                failure_guard=failure_guard,
            )
            state = repaired.run_blocked_prefix(
                backend,
                system_id=system_id,
                model=model,
                checkpoint_required=False,
            )
            repaired._continue_state(
                state,
                system_id=system_id,
                arm=arm,
                model=model,
            )
            _attach_attempt_validation(
                exact_calls, state, journal=journal
            )
            calls = exact_calls
    process = registry.attestations[str(assignment["assignment_id"])]
    return state, calls, process


def _continuation_context(
    process_factory: Any,
    *,
    restored_label: str,
    no_trigger_label: str,
) -> Any:
    method = getattr(process_factory, "continuations", None)
    if not callable(method):
        raise TechnicalSmokeError(
            "FRESH_CONTINUATION_FACTORY_REQUIRED"
        )
    return method(
        restored_label=restored_label,
        no_trigger_label=no_trigger_label,
    )


def _checkpoint_validation(
    row: Mapping[str, Any],
    *,
    r_state: Any,
    n_state: Any,
) -> list[str]:
    repaired = _repaired_runner()
    reasons: list[str] = []
    expected_event = copy.deepcopy(repaired.CHECKPOINT_EVENT)
    if expected_event != {
        "event_type": "protocol_checkpoint",
        "event_version": "2.0.0",
        "message": "Scheduled protocol checkpoint completed.",
        "cost": 0.0,
    }:
        reasons.append("CHECKPOINT_IMPLEMENTATION_OBJECT_MISMATCH")
    if semantic_hash(expected_event) != CHECKPOINT_SHA256:
        reasons.append("CHECKPOINT_IMPLEMENTATION_HASH_MISMATCH")
    if row.get("checkpoint_event") != expected_event:
        reasons.append("CHECKPOINT_EVENT_OBJECT_MISMATCH")
    if row.get("checkpoint_event_hash") != CHECKPOINT_SHA256:
        reasons.append("CHECKPOINT_EVENT_HASH_MISMATCH")
    if row.get("checkpoint_action_index_zero_based") != 4:
        reasons.append("CHECKPOINT_INDEX_MISMATCH")
    for arm, state in (("R", r_state), ("N", n_state)):
        matches = [
            event
            for event in state.events
            if event.get("event") == expected_event
        ]
        if len(matches) != 1:
            reasons.append(f"CHECKPOINT_{arm}_DELIVERY_CARDINALITY")
        elif matches[0].get("action_index") != 4:
            reasons.append(f"CHECKPOINT_{arm}_DELIVERY_INDEX")
    if not row.get("checkpoint_delivered_r"):
        reasons.append("CHECKPOINT_R_NOT_DELIVERED")
    if not row.get("checkpoint_delivered_n"):
        reasons.append("CHECKPOINT_N_NOT_DELIVERED")
    return reasons


def _brn_pre_prefix_identity_probe(
    assignment: Mapping[str, Any],
    *,
    backend_factory: Callable[[Mapping[str, Any]], BackendLike],
) -> dict[str, Any]:
    surfaces = {}
    for arm in ("B", "R", "N"):
        probe_assignment = {**dict(assignment), "arm": arm}
        surfaces[arm] = backend_factory(probe_assignment).public_start()
    hashes = {
        arm: _bytes_sha256(canonical_bytes(surface))
        for arm, surface in surfaces.items()
    }
    return {
        "pair_id": assignment["pair_id"],
        "scope": "PUBLIC_START_BEFORE_FIRST_ACTION",
        "applicable_cells_only": True,
        "canonical_surface_hashes": hashes,
        "b_r_n_identical": len(set(hashes.values())) == 1,
    }


def _online_abort_reasons(
    *,
    total_calls: int,
    effective_assignment_calls: Mapping[str, int],
    process_failures: int,
    malformed_after_repair: int,
    tool_contract_violations: int,
    provider_latencies: Sequence[float],
    assignment_elapsed: float,
    mechanical_scan_hits: int,
    isolation_collisions: int,
) -> list[str]:
    reasons: list[str] = []
    if total_calls >= ABORT_THRESHOLDS["max_total_model_generate_calls"]:
        reasons.append("GLOBAL_MODEL_CALL_THRESHOLD_REACHED")
    if any(
        count >= ABORT_THRESHOLDS[
            "max_model_generate_calls_per_assignment"
        ]
        for count in effective_assignment_calls.values()
    ):
        reasons.append("ASSIGNMENT_MODEL_CALL_THRESHOLD_REACHED")
    if process_failures >= ABORT_THRESHOLDS["max_process_failures"]:
        reasons.append("PROCESS_FAILURE_THRESHOLD_REACHED")
    if malformed_after_repair >= ABORT_THRESHOLDS[
        "max_malformed_after_repair"
    ]:
        reasons.append("MALFORMED_THRESHOLD_REACHED")
    if tool_contract_violations >= ABORT_THRESHOLDS[
        "max_typed_tool_contract_violations"
    ]:
        reasons.append("TOOL_CONTRACT_THRESHOLD_REACHED")
    if any(
        latency >= ABORT_THRESHOLDS["max_provider_call_seconds"]
        for latency in provider_latencies
    ):
        reasons.append("PROVIDER_TIMEOUT_THRESHOLD_REACHED")
    if assignment_elapsed >= ABORT_THRESHOLDS["max_assignment_seconds"]:
        reasons.append("ASSIGNMENT_TIMEOUT_THRESHOLD_REACHED")
    if mechanical_scan_hits >= 1:
        reasons.append("PRIVATE_SURFACE_SCAN_FAILURE")
    if isolation_collisions >= 1:
        reasons.append("PROCESS_ISOLATION_COLLISION")
    return reasons


def _check_abort_thresholds(
    *,
    plan: Mapping[str, Any],
    checkpoints: Sequence[Mapping[str, Any]],
    raw_calls: Sequence[Mapping[str, Any]],
    failure_rows: Sequence[Mapping[str, Any]],
    completion_rows: Sequence[Mapping[str, Any]],
    isolation: Mapping[str, Any],
    leakage: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if plan["assignment_count"] != ABORT_THRESHOLDS["assignment_count"]:
        reasons.append("ASSIGNMENT_COUNT")
    if (
        len(checkpoints)
        != ABORT_THRESHOLDS["checkpoint_pair_count"]
    ):
        reasons.append("CHECKPOINT_PAIR_COUNT")
    if any(not row.get("prefix_identical") for row in checkpoints):
        reasons.append("R_N_PREFIX_NOT_IDENTICAL")
    if any(not row.get("checkpoint_identical") for row in checkpoints):
        reasons.append("R_N_CHECKPOINT_NOT_IDENTICAL")
    if any(
        not (
            row.get("checkpoint_delivered_r")
            and row.get("checkpoint_delivered_n")
        )
        for row in checkpoints
    ):
        reasons.append("CHECKPOINT_NOT_DELIVERED_TO_BOTH")
    if len(raw_calls) >= ABORT_THRESHOLDS[
        "max_total_model_generate_calls"
    ]:
        reasons.append("MODEL_CALL_LIMIT")
    assignment_call_counts: dict[str, int] = {}
    for row in raw_calls:
        process_label = str(row.get("process_label", ""))
        if process_label.endswith(":prefix"):
            continue
        assignment_call_counts[process_label] = (
            assignment_call_counts.get(process_label, 0) + 1
        )
    if any(
        count >= ABORT_THRESHOLDS[
            "max_model_generate_calls_per_assignment"
        ]
        for count in assignment_call_counts.values()
    ):
        reasons.append("ASSIGNMENT_MODEL_CALL_LIMIT")
    process_failures = sum(
        1
        for row in raw_calls
        if isinstance(row.get("failure"), Mapping)
    )
    if process_failures >= ABORT_THRESHOLDS["max_process_failures"]:
        reasons.append("PROCESS_FAILURE_LIMIT")
    malformed_after_repair = sum(
        row.get("completion_status") == "MALFORMED_AFTER_REPAIR"
        for row in failure_rows
    )
    if malformed_after_repair >= ABORT_THRESHOLDS[
        "max_malformed_after_repair"
    ]:
        reasons.append("MALFORMED_LIMIT")
    typed_tool_contract_violations = sum(
        row.get("completion_status") == "TOOL_CONTRACT_VIOLATION"
        for row in failure_rows
    )
    if typed_tool_contract_violations >= ABORT_THRESHOLDS[
        "max_typed_tool_contract_violations"
    ]:
        reasons.append("TOOL_CONTRACT_LIMIT")
    if isolation.get("status") != "PASS":
        reasons.append("PROCESS_ISOLATION")
    if (
        leakage.get("mechanical_private_surface_scan", {}).get(
            "leakage_hit_count", 0
        )
        >= ABORT_THRESHOLDS["max_runtime_private_leakage_hits"] + 1
    ):
        reasons.append("RUNTIME_PRIVATE_LEAKAGE")
    expected_ids = {
        str(row["assignment_id"]) for row in plan["assignments"]
    }
    completion_ids = [
        str(row["assignment_id"]) for row in completion_rows
    ]
    failure_ids = [str(row["assignment_id"]) for row in failure_rows]
    if (
        set(completion_ids) != expected_ids
        or len(completion_ids) != len(set(completion_ids))
    ):
        reasons.append("COMPLETION_LEDGER_CARDINALITY")
    if (
        set(failure_ids) != expected_ids
        or len(failure_ids) != len(set(failure_ids))
    ):
        reasons.append("FAILURE_LEDGER_CARDINALITY")
    return reasons


def _read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TechnicalSmokeError(
            "DURABLE_ARTIFACT_READ_FAILED", f"{path}:{exc}"
        ) from exc
    for line_number, line in enumerate(lines, 1):
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TechnicalSmokeError(
                "DURABLE_ARTIFACT_INVALID_JSON",
                f"{path}:{line_number}:{exc}",
            ) from exc
        if not isinstance(value, dict):
            raise TechnicalSmokeError(
                "DURABLE_ARTIFACT_INVALID_SCHEMA",
                f"{path}:{line_number}",
            )
        rows.append(value)
    return rows


def _manifest_identity_core(
    *,
    output_dir: Path,
    run_id: str,
    plan: Mapping[str, Any],
    validation: Mapping[str, Any],
    authorization: Mapping[str, Any] | None,
    testing_injection: bool,
    started_at_utc: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "run_id": run_id,
        "created_date": FROZEN_DATE,
        "started_at_utc": started_at_utc,
        "output_root": str(output_dir.resolve()),
        "smoke_only": True,
        "development_only": True,
        "testing_injection": testing_injection,
        "scientific_execution": False,
        "plan_hash": plan["plan_hash"],
        "assignment_count": plan["assignment_count"],
        "runner": {
            "path": "scripts/run_p23_102_technical_smoke_v2.py",
            "sha256": _sha256(
                REPO_ROOT / "scripts/run_p23_102_technical_smoke_v2.py"
            ),
        },
        "repaired_runner": copy.deepcopy(validation["repaired_runner"]),
        "current_p23_inputs": copy.deepcopy(
            validation["current_p23_inputs"]
        ),
        "local_models": copy.deepcopy(validation["local_models"]),
        "local_model_file_set_sha256": validation[
            "local_model_file_set_sha256"
        ],
        "authorization": {
            "immutable_freeze_execution_authorized": False,
            "strict_overlay": copy.deepcopy(authorization),
            "testing_injection": testing_injection,
        },
        "provenance": {
            "freeze_sha256": _sha256(REPO_ROOT / CONFIG_REL),
            "adapter_attestation_sha256": _sha256(
                REPO_ROOT / ADAPTER_ATTESTATION_REL
            ),
            "runner_sha256": _sha256(
                REPO_ROOT
                / "scripts/run_p23_102_technical_smoke_v2.py"
            ),
            "repaired_runner_sha256": validation["repaired_runner"][
                "sha256"
            ],
            "plan_sha256": plan["plan_hash"],
            "local_model_file_set_sha256": validation[
                "local_model_file_set_sha256"
            ],
            "local_model_manifests": {
                name: identity["manifest_sha256"]
                for name, identity in validation["local_models"].items()
            },
            "local_model_validated_file_sets": {
                name: identity["validated_file_set_sha256"]
                for name, identity in validation["local_models"].items()
            },
        },
        "abort_thresholds": dict(ABORT_THRESHOLDS),
        "claims": {
            "semantic_validity": False,
            "model_competence": False,
            "performance": False,
            "causal_effect": False,
            "gate_a": False,
            "h2": False,
        },
        "claim_boundary": (
            "Technical wiring evidence only. No semantic, competence, "
            "performance, causal, or benchmark claim is permitted."
        ),
        "output_contract": list(OUTPUT_FILES),
    }


def _write_and_validate_replay_manifest(
    output_dir: Path,
    *,
    plan: Mapping[str, Any],
    checkpoints: Sequence[Mapping[str, Any]],
    write: bool = True,
) -> dict[str, Any]:
    source_path = output_dir / "public_trajectories.jsonl"
    source_sha256 = _sha256(source_path)
    public_rows = _read_jsonl_strict(output_dir / "public_trajectories.jsonl")
    manifest = {
        "schema_version": SCHEMA,
        "plan_hash": plan["plan_hash"],
        "public_trajectories_jsonl_sha256": source_sha256,
        "public_trajectories": [
            {
                "trajectory_id": row.get("trajectory_id"),
                "public_trajectory_sha256": row.get(
                    "public_trajectory_sha256"
                ),
            }
            for row in public_rows
        ],
        "all_r_n_prefixes_identical": all(
            row.get("prefix_identical") is True for row in checkpoints
        ),
        "deterministic_answer_substitution": False,
    }
    expected_ids = [
        str(row["trajectory_id"]) for row in plan["assignments"]
    ]
    actual_ids = [
        str(row.get("trajectory_id")) for row in public_rows
    ]
    if actual_ids != expected_ids:
        raise TechnicalSmokeError("REPLAY_TRAJECTORY_ORDER_MISMATCH")
    for row in public_rows:
        recalculated = semantic_hash(
            {
                "start": row.get("episode_start"),
                "events": row.get("events"),
                "final": row.get("final_output"),
                "observations": {
                    str(item.get("observation_id")): item
                    for item in row.get("observations", [])
                    if isinstance(item, Mapping)
                },
            }
        )
        if row.get("public_trajectory_sha256") != recalculated:
            raise TechnicalSmokeError("REPLAY_TRAJECTORY_HASH_MISMATCH")
    persisted_rows = _read_jsonl_strict(
        output_dir / "public_trajectories.jsonl"
    )
    if persisted_rows != public_rows or _sha256(source_path) != source_sha256:
        raise TechnicalSmokeError("REPLAY_SOURCE_MUTATED_DURING_VALIDATION")
    if write:
        _atomic_write_json(output_dir / "replay_manifest.json", manifest)
        if _sha256(source_path) != source_sha256:
            raise TechnicalSmokeError(
                "REPLAY_SOURCE_MUTATED_DURING_PUBLICATION"
            )
        persisted = _load(output_dir / "replay_manifest.json")
        if persisted != manifest:
            raise TechnicalSmokeError(
                "REPLAY_MANIFEST_PERSISTENCE_MISMATCH"
            )
    return manifest


def _write_and_validate_raw_retention_manifest(
    output_dir: Path, *, write: bool = True
) -> dict[str, Any]:
    journal_path = output_dir / "provider_call_journal.jsonl"
    raw_path = output_dir / "raw_model_calls.jsonl"
    journal_sha256 = _sha256(journal_path)
    raw_sha256 = _sha256(raw_path)
    journal = _read_jsonl_strict(journal_path)
    raw_rows = _read_jsonl_strict(raw_path)
    requests: dict[str, dict[str, Any]] = {}
    terminals: dict[str, dict[str, Any]] = {}
    for expected_sequence, entry in enumerate(journal, 1):
        if entry.get("journal_sequence") != expected_sequence:
            raise TechnicalSmokeError("PROVIDER_JOURNAL_SEQUENCE_INVALID")
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            raise TechnicalSmokeError("PROVIDER_JOURNAL_PAYLOAD_INVALID")
        call_id = str(payload.get("call_id", ""))
        event = entry.get("event")
        if event == "request":
            target = requests
        elif event in {"terminal", "terminal_annotation"}:
            target = terminals
        else:
            raise TechnicalSmokeError("PROVIDER_JOURNAL_EVENT_INVALID")
        if not call_id or (event != "terminal_annotation" and call_id in target):
            raise TechnicalSmokeError("PROVIDER_JOURNAL_EVENT_INVALID")
        if event == "terminal_annotation" and call_id not in terminals:
            raise TechnicalSmokeError("PROVIDER_JOURNAL_EVENT_INVALID")
        target[call_id] = dict(payload)
    raw_by_id: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        call_id = str(row.get("call_id", ""))
        if not call_id or call_id in raw_by_id:
            raise TechnicalSmokeError("RAW_RETENTION_DUPLICATE_CALL")
        raw_by_id[call_id] = row
    if set(requests) != set(terminals) or set(terminals) != set(raw_by_id):
        raise TechnicalSmokeError("RAW_RETENTION_CLOSURE_MISMATCH")
    mismatches = [
        call_id
        for call_id, terminal in terminals.items()
        if terminal != raw_by_id[call_id]
    ]
    if mismatches:
        raise TechnicalSmokeError(
            "RAW_RETENTION_CONTENT_MISMATCH", ",".join(sorted(mismatches))
        )
    manifest = {
        "schema_version": SCHEMA,
        "request_count": len(requests),
        "terminal_count": len(terminals),
        "raw_row_count": len(raw_rows),
        "call_ids_sha256": semantic_hash(sorted(requests)),
        "journal_sha256": journal_sha256,
        "raw_model_calls_sha256": raw_sha256,
        "closure_status": "PASS",
    }
    if (
        _sha256(journal_path) != journal_sha256
        or _sha256(raw_path) != raw_sha256
    ):
        raise TechnicalSmokeError(
            "RAW_RETENTION_SOURCE_MUTATED_DURING_VALIDATION"
        )
    if write:
        _atomic_write_json(output_dir / "raw_retention_manifest.json", manifest)
        if (
            _sha256(journal_path) != journal_sha256
            or _sha256(raw_path) != raw_sha256
        ):
            raise TechnicalSmokeError(
                "RAW_RETENTION_SOURCE_MUTATED_DURING_PUBLICATION"
            )
    if (
        write
        and _load(output_dir / "raw_retention_manifest.json") != manifest
    ):
        raise TechnicalSmokeError("RAW_RETENTION_MANIFEST_MISMATCH")
    return manifest


def _validate_final_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    staged_run_manifest: Path | None = None,
) -> None:
    missing = [
        name
        for name in OUTPUT_FILES
        if not (output_dir / name).is_file()
    ]
    if missing:
        raise TechnicalSmokeError(
            "OUTPUT_CONTRACT_INCOMPLETE", ",".join(missing)
        )
    inventory = _load(output_dir / "file_inventory.json")
    artifact = _load(output_dir / "artifact_manifest.json")
    if (
        inventory.get("run_id") != run_id
        or artifact.get("run_id") != run_id
        or inventory.get("files") != artifact.get("files")
        or artifact.get("manifest_payload_sha256")
        != semantic_hash(inventory.get("files"))
    ):
        raise TechnicalSmokeError("FINAL_ARTIFACT_MANIFEST_MISMATCH")
    expected = {
        str(row.get("path")): row
        for row in inventory.get("files", [])
        if isinstance(row, Mapping)
    }
    for name, record in expected.items():
        path = (
            staged_run_manifest
            if name == "run_manifest.json"
            and staged_run_manifest is not None
            else output_dir / name
        )
        if (
            not path.is_file()
            or path.stat().st_size != record.get("bytes")
            or _sha256(path) != record.get("sha256")
        ):
            raise TechnicalSmokeError(
                "FINAL_ARTIFACT_INVENTORY_MISMATCH", name
            )


def _write_outputs(
    output_dir: Path,
    *,
    plan: Mapping[str, Any],
    validation: Mapping[str, Any],
    public_trajectories: Sequence[Mapping[str, Any]],
    private_rows: Sequence[Mapping[str, Any]],
    metrics: Sequence[Mapping[str, Any]],
    failure_rows: Sequence[Mapping[str, Any]],
    completion_rows: Sequence[Mapping[str, Any]],
    checkpoints: Sequence[Mapping[str, Any]],
    isolation: Mapping[str, Any],
    leakage: Mapping[str, Any],
    run_id: str,
    testing_injection: bool,
    abort_reasons: Sequence[str],
    authorization: Mapping[str, Any] | None = None,
    started_at_utc: str | None = None,
    brn_identity: Sequence[Mapping[str, Any]] = (),
    pre_completion_hook: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    _atomic_write_json(output_dir / "plan.json", plan)
    durable_jsonl = {
        "assignments.jsonl": plan["assignments"],
        "public_trajectories.jsonl": public_trajectories,
        "raw_trajectories.jsonl": public_trajectories,
        "private_arm_evidence_mappings.jsonl": private_rows,
        "r_n_prefix_pairs.jsonl": checkpoints,
        "metrics.jsonl": metrics,
        "episode_metrics.jsonl": metrics,
        "metric_ready_records.jsonl": metrics,
        "failure_ledger.jsonl": failure_rows,
        "completion_ledger.jsonl": completion_rows,
    }
    for name, rows in durable_jsonl.items():
        path = output_dir / name
        if not path.exists():
            _atomic_write_jsonl(path, rows)
    _atomic_write_json(
        output_dir / "checkpoint_delivery.json",
        {
            "pair_count": len(checkpoints),
            "pairs": list(checkpoints),
            "all_prefixes_identical": all(
                row["prefix_identical"] for row in checkpoints
            ),
            "all_checkpoints_identical": all(
                row["checkpoint_identical"] for row in checkpoints
            ),
        },
    )
    citation_path = output_dir / "citation_outputs.jsonl"
    if not citation_path.exists():
        _atomic_write_jsonl(
            citation_path,
            [
                {
                    "trajectory_id": row["trajectory_id"],
                    "completion_status": row["completion_status"],
                    "citation_schema_validation": row[
                        "citation_schema_validation"
                    ],
                    "final_output": row["final_output"],
                }
                for row in public_trajectories
            ],
        )
    if not (output_dir / "abort_ledger.jsonl").exists():
        _atomic_write_jsonl(output_dir / "abort_ledger.jsonl", [])
    if not (output_dir / "unstarted_assignments.jsonl").exists():
        _atomic_write_jsonl(output_dir / "unstarted_assignments.jsonl", [])
    _atomic_write_json(
        output_dir / "process_session_isolation.json", isolation
    )
    _atomic_write_json(
        output_dir / "runtime_leakage_surface.json", leakage
    )
    _atomic_write_json(
        output_dir / "b_r_n_prefix_identity.json",
        {
            "scope": "PUBLIC_START_BEFORE_FIRST_ACTION",
            "probe_count": len(brn_identity),
            "all_identical": all(
                row["b_r_n_identical"] for row in brn_identity
            ),
            "probes": list(brn_identity),
        },
    )
    _atomic_write_json(
        output_dir / "aggregate_metrics.json",
        {
            "assignment_count": len(metrics),
            "completion_status_counts": {
                status: sum(
                    row["completion_status"] == status
                    for row in metrics
                )
                for status in sorted(
                    {
                        str(row["completion_status"])
                        for row in metrics
                    }
                )
            },
            "technical_wiring_only": True,
            "semantic_or_performance_aggregation": False,
        },
    )
    if pre_completion_hook is not None:
        pre_completion_hook(output_dir)
    replay_manifest = _write_and_validate_replay_manifest(
        output_dir,
        plan=plan,
        checkpoints=checkpoints,
        write=False,
    )
    raw_retention_manifest = _write_and_validate_raw_retention_manifest(
        output_dir, write=False
    )
    _atomic_write_json(output_dir / "replay_manifest.json", replay_manifest)
    _atomic_write_json(
        output_dir / "raw_retention_manifest.json",
        raw_retention_manifest,
    )
    _write_and_validate_replay_manifest(
        output_dir, plan=plan, checkpoints=checkpoints
    )
    _write_and_validate_raw_retention_manifest(output_dir)
    identity_core = _manifest_identity_core(
        output_dir=output_dir,
        run_id=run_id,
        plan=plan,
        validation=validation,
        authorization=authorization,
        testing_injection=testing_injection,
        started_at_utc=started_at_utc or _utc_text(),
    )
    completed_at = _utc_text()
    preparing_manifest = {
        **identity_core,
        "completed_at_utc": completed_at,
        "completion_status": "FINALIZING",
        "abort_reasons": list(abort_reasons),
        "public_trajectory_count": len(public_trajectories),
        "completion_ledger_count": len(completion_rows),
        "raw_model_call_count": raw_retention_manifest["raw_row_count"],
        "runtime_leakage_status": leakage["status"],
        "mechanical_private_surface_scan_status": leakage[
            "mechanical_private_surface_scan"
        ]["status"],
        "process_isolation_status": isolation["status"],
    }
    _atomic_write_json(output_dir / "run_manifest.json", preparing_manifest)
    if abort_reasons:
        raise TechnicalSmokeError(
            "ABORT_THRESHOLD_EXCEEDED", ",".join(abort_reasons)
        )
    final_manifest = {
        **preparing_manifest,
        "completion_status": "TECHNICAL_SMOKE_COMPLETE",
        "final_commit_marker": "TECHNICAL_SMOKE_COMPLETE",
        "final_commit_at_utc": completed_at,
    }
    staged_run_manifest = output_dir / ".run_manifest.final"
    _atomic_write_json(staged_run_manifest, final_manifest)
    inventory = []
    for path in sorted(output_dir.iterdir()):
        if path.name in {
            "artifact_manifest.json",
            "file_inventory.json",
            "run_manifest.json",
            staged_run_manifest.name,
        } or not path.is_file():
            continue
        inventory.append(
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "mode": oct(stat.S_IMODE(path.stat().st_mode)),
                "sha256": _sha256(path),
            }
        )
    inventory.append(
        {
            "path": "run_manifest.json",
            "bytes": staged_run_manifest.stat().st_size,
            "mode": oct(stat.S_IMODE(staged_run_manifest.stat().st_mode)),
            "sha256": _sha256(staged_run_manifest),
        }
    )
    inventory.sort(key=lambda row: str(row["path"]))
    _atomic_write_json(
        output_dir / "file_inventory.json",
        {
            "schema_version": SCHEMA,
            "run_id": run_id,
            "files": inventory,
        },
    )
    _atomic_write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": SCHEMA,
            "run_id": run_id,
            "files": inventory,
            "manifest_payload_sha256": semantic_hash(inventory),
        },
    )
    _validate_final_artifacts(
        output_dir,
        run_id=run_id,
        staged_run_manifest=staged_run_manifest,
    )
    os.replace(staged_run_manifest, output_dir / "run_manifest.json")
    _fsync_directory(output_dir)
    _validate_final_artifacts(output_dir, run_id=run_id)
    return {
        "raw_model_call_count": raw_retention_manifest["raw_row_count"],
        "run_manifest": final_manifest,
    }


def execute_technical_smoke(
    repo_root: str | Path = ".",
    *,
    output_dir: str | Path | None = None,
    authorization_overlay: str | Path | None = None,
) -> dict[str, Any]:
    """Execute the production smoke path with no injectable collaborators."""

    return _execute_technical_smoke_core(
        repo_root,
        output_dir=output_dir,
        authorization_overlay=authorization_overlay,
        capability=None,
    )


def _execute_technical_smoke_for_test(
    repo_root: str | Path = ".",
    *,
    output_dir: str | Path,
    backend_factory: Callable[[Mapping[str, Any]], BackendLike],
    process_factory: Any,
    assignment_deadline_seconds: float | None = None,
    provider_terminal_hook: (
        Callable[[Mapping[str, Any]], None] | None
    ) = None,
    pre_completion_hook: Callable[[Path], None] | None = None,
    pre_spawn_hook: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Private synthetic harness enabled only by a module capability."""

    return _execute_technical_smoke_core(
        repo_root,
        output_dir=output_dir,
        authorization_overlay=None,
        backend_factory=backend_factory,
        process_factory=process_factory,
        assignment_deadline_seconds=assignment_deadline_seconds,
        provider_terminal_hook=provider_terminal_hook,
        pre_completion_hook=pre_completion_hook,
        pre_spawn_hook=pre_spawn_hook,
        capability=_TEST_EXECUTION_CAPABILITY,
    )


def _execute_technical_smoke_core(
    repo_root: str | Path,
    *,
    output_dir: str | Path | None,
    authorization_overlay: str | Path | None,
    backend_factory: (
        Callable[[Mapping[str, Any]], BackendLike] | None
    ) = None,
    process_factory: Any | None = None,
    assignment_deadline_seconds: float | None = None,
    provider_terminal_hook: (
        Callable[[Mapping[str, Any]], None] | None
    ) = None,
    pre_completion_hook: Callable[[Path], None] | None = None,
    pre_spawn_hook: Callable[[], None] | None = None,
    capability: object | None = None,
) -> dict[str, Any]:
    """Shared implementation; injected execution needs the private capability."""

    root = Path(repo_root).resolve()
    testing_injection = capability is _TEST_EXECUTION_CAPABILITY
    injected_values = (
        backend_factory,
        process_factory,
        provider_terminal_hook,
        pre_completion_hook,
        pre_spawn_hook,
    )
    if not testing_injection and any(
        value is not None for value in injected_values
    ):
        raise TechnicalSmokeError("PRODUCTION_INJECTION_REJECTED")
    if testing_injection and (
        backend_factory is None or process_factory is None
    ):
        raise TechnicalSmokeError("TEST_EXECUTION_INJECTION_INCOMPLETE")
    validation = validate_repository(root)
    if validation["validation_status"] != "READY":
        raise TechnicalSmokeError(
            "VALIDATION_NOT_READY", ",".join(validation["errors"])
        )
    plan = build_plan(root)
    run_id = (
        "synthetic-test"
        if testing_injection
        else f"{_utc_now():%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"
    )
    target = (
        Path(output_dir).resolve()
        if output_dir is not None
        else (root / OUTPUT_ROOT_REL / run_id).resolve()
    )
    authorization: dict[str, Any] | None = None
    if not testing_injection:
        if authorization_overlay is None:
            raise TechnicalSmokeError(
                "EXECUTION_NOT_AUTHORIZED",
                "STRICT_AUTHORIZATION_OVERLAY_REQUIRED",
            )
        overlay_path = Path(authorization_overlay).resolve()
        authorization = _validate_authorization_overlay(
            overlay_path,
            root=root,
            output_root=target,
            plan=plan,
            validation=validation,
        )
    _reserve_output_root(
        target,
        repo_root=root,
        authorization=authorization,
    )
    started_at = _utc_text()
    identity_core = _manifest_identity_core(
        output_dir=target,
        run_id=run_id,
        plan=plan,
        validation=validation,
        authorization=authorization,
        testing_injection=testing_injection,
        started_at_utc=started_at,
    )
    initial_manifest = {
        **identity_core,
        "completion_status": "RUNNING",
        "immutable_freeze_execution_authorized": False,
    }
    _atomic_write_json(target / "run_manifest.json", initial_manifest)
    _atomic_write_json(target / "plan.json", plan)
    _atomic_write_jsonl(target / "assignments.jsonl", plan["assignments"])
    for name in (
        "raw_model_calls.jsonl",
        "provider_call_journal.jsonl",
        "public_trajectories.jsonl",
        "raw_trajectories.jsonl",
        "factor_model_raw_outputs.jsonl",
        "private_arm_evidence_mappings.jsonl",
        "r_n_prefix_pairs.jsonl",
        "metrics.jsonl",
        "episode_metrics.jsonl",
        "metric_ready_records.jsonl",
        "citation_outputs.jsonl",
        "failure_ledger.jsonl",
        "completion_ledger.jsonl",
        "abort_ledger.jsonl",
        "unstarted_assignments.jsonl",
    ):
        _atomic_write_jsonl(target / name, [])
    provider_journal = ProviderCallJournal(
        target / "provider_call_journal.jsonl",
        interrupt_after_terminal=provider_terminal_hook,
    )

    inputs = _load_inputs(root)
    if pre_spawn_hook is not None:
        pre_spawn_hook()
    pre_spawn_inventory = _revalidate_model_inventory_before_spawn(
        root,
        validation=validation,
        authorization=authorization,
    )
    _atomic_write_json(
        target / "model_inventory_pre_spawn.json",
        pre_spawn_inventory,
    )
    initial_manifest = {
        **initial_manifest,
        "pre_spawn_model_inventory": {
            "path": "model_inventory_pre_spawn.json",
            "all_model_set_sha256": pre_spawn_inventory[
                "all_model_set_sha256"
            ],
            "equals_initial_validation": True,
            "equals_signed_overlay": pre_spawn_inventory[
                "equals_signed_overlay"
            ],
        },
    }
    _atomic_write_json(target / "run_manifest.json", initial_manifest)
    if backend_factory is None:
        backend_factory = _default_backend_factory(root, inputs)
    if process_factory is None:
        process_factory = _default_process_factory(validation["qwen"])
    assignments = [dict(row) for row in plan["assignments"]]
    states: dict[str, Any] = {}
    calls_by_id: dict[str, list[dict[str, Any]]] = {}
    process_by_id: dict[str, dict[str, Any]] = {}
    registry = ProcessRegistry(process_factory, process_by_id)
    repaired = _repaired_runner()
    checkpoints: list[dict[str, Any]] = []
    brn_identity: list[dict[str, Any]] = []
    prefix_attestations: list[dict[str, Any]] = []
    processed: set[str] = set()
    public_trajectories: list[dict[str, Any]] = []
    private_rows: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    completion_rows: list[dict[str, Any]] = []
    abort_reasons: list[str] = []
    total_calls = 0
    process_failures_seen = 0
    current_effective_ids: tuple[str, ...] = ()
    current_call_count = 0
    provider_latencies: list[float] = []
    active_deadline: AssignmentDeadline | None = None
    configured_assignment_deadline = (
        ABORT_THRESHOLDS["max_assignment_seconds"]
        if assignment_deadline_seconds is None
        else float(assignment_deadline_seconds)
    )

    def failure_guard(_failure: Mapping[str, Any]) -> None:
        nonlocal process_failures_seen
        process_failures_seen += 1
        if process_failures_seen >= ABORT_THRESHOLDS[
            "max_process_failures"
        ]:
            raise TechnicalSmokeHardAbort(
                "PROCESS_FAILURE_THRESHOLD_REACHED"
            )

    def call_guard(_label: str, elapsed: float | None) -> None:
        nonlocal total_calls, current_call_count
        if elapsed is None:
            if total_calls >= ABORT_THRESHOLDS[
                "max_total_model_generate_calls"
            ]:
                raise TechnicalSmokeError(
                    "GLOBAL_MODEL_CALL_THRESHOLD_REACHED"
                )
            if current_call_count >= ABORT_THRESHOLDS[
                "max_model_generate_calls_per_assignment"
            ]:
                raise TechnicalSmokeError(
                    "ASSIGNMENT_MODEL_CALL_THRESHOLD_REACHED",
                    ",".join(current_effective_ids),
                )
            total_calls += 1
            current_call_count += 1
        else:
            provider_latencies.append(elapsed)
            if elapsed >= ABORT_THRESHOLDS["max_provider_call_seconds"]:
                raise TechnicalSmokeError(
                    "PROVIDER_TIMEOUT_THRESHOLD_REACHED"
                )

    pairs: dict[str, dict[str, dict[str, Any]]] = {}
    for assignment in assignments:
        pair_id = assignment.get("pair_id")
        if pair_id:
            pairs.setdefault(str(pair_id), {})[
                str(assignment["arm"])
            ] = assignment

    def persist_assignment(assignment: Mapping[str, Any]) -> None:
        assignment_id = str(assignment["assignment_id"])
        state = states[assignment_id]
        public = _public_trajectory(assignment, state)
        _, _, intervention = _rows_for_assignment(inputs, assignment)
        private = _state_private_mapping(
            assignment,
            state,
            process_by_id[assignment_id],
            intervention,
        )
        calls = calls_by_id.get(assignment_id, [])
        metric = _metric_row(
            assignment,
            state,
            checkpoint_delivered=bool(assignment.get("pair_id")),
            raw_calls=calls,
        )
        failure = _failure_row(assignment, state)
        completion = {
            "assignment_id": assignment["assignment_id"],
            "trajectory_id": assignment["trajectory_id"],
            "completion_status": failure["completion_status"],
            "terminal_row_count": 1,
            "failure_present": failure["failure"] is not None,
        }
        citation = {
            "trajectory_id": public["trajectory_id"],
            "completion_status": public["completion_status"],
            "citation_schema_validation": public[
                "citation_schema_validation"
            ],
            "final_output": public["final_output"],
        }
        public_trajectories.append(public)
        private_rows.append(private)
        raw_calls.extend(calls)
        metrics.append(metric)
        failure_rows.append(failure)
        completion_rows.append(completion)
        for name, row in (
            ("public_trajectories.jsonl", public),
            ("raw_trajectories.jsonl", public),
            ("private_arm_evidence_mappings.jsonl", private),
            ("metrics.jsonl", metric),
            ("episode_metrics.jsonl", metric),
            ("metric_ready_records.jsonl", metric),
            ("citation_outputs.jsonl", citation),
            ("failure_ledger.jsonl", failure),
            ("completion_ledger.jsonl", completion),
        ):
            _append_jsonl_durable(target / name, row)

    try:
        for assignment in assignments:
            assignment_id = str(assignment["assignment_id"])
            if assignment_id in processed:
                continue
            boundary_started = time.monotonic()
            pair_id = assignment.get("pair_id")
            deadline_ids = (
                (assignment_id,)
                if not pair_id
                else tuple(
                    str(pairs[str(pair_id)][arm]["assignment_id"])
                    for arm in ("R", "N")
                )
            )
            active_deadline = AssignmentDeadline(
                configured_assignment_deadline,
                deadline_ids,
            )
            registry.deadline = active_deadline
            active_deadline.__enter__()
            if not pair_id:
                current_effective_ids = (assignment_id,)
                current_call_count = 0
                state, calls, process = _run_endpoint(
                    assignment,
                    backend_factory=backend_factory,
                    registry=registry,
                    call_guard=call_guard,
                    journal=provider_journal,
                    failure_guard=failure_guard,
                )
                states[assignment_id] = state
                calls_by_id[assignment_id] = calls
                process_by_id[assignment_id] = process
                processed.add(assignment_id)
                persist_assignment(assignment)
            else:
                arms = pairs[str(pair_id)]
                if set(arms) != {"R", "N"}:
                    raise TechnicalSmokeError(
                        "INVALID_R_N_PAIR", str(pair_id)
                    )
                r_assignment = arms["R"]
                n_assignment = arms["N"]
                r_id = str(r_assignment["assignment_id"])
                n_id = str(n_assignment["assignment_id"])
                current_effective_ids = (r_id, n_id)
                current_call_count = 0
                brn = _brn_pre_prefix_identity_probe(
                    r_assignment, backend_factory=backend_factory
                )
                brn_identity.append(brn)
                if not brn["b_r_n_identical"]:
                    raise TechnicalSmokeError(
                        "B_R_N_PRE_PREFIX_IDENTITY_MISMATCH"
                    )
                prefix_calls: list[dict[str, Any]] = []
                prefix_model: RecordingModel | None = None
                system_id = str(r_assignment["system_id"])
                prefix_attestation: dict[str, Any] | None = None
                if system_id == "single_shot_rag":
                    prefix = repaired.run_blocked_prefix(
                        backend_factory(r_assignment),
                        system_id=system_id,
                        model=None,
                    )
                else:
                    with registry.prefix(str(pair_id)) as prefix_worker:
                        prefix_attestation = registry.attestations[
                            f"{pair_id}:prefix"
                        ]
                        prefix_attestations.append(prefix_attestation)
                        prefix_model = RecordingModel(
                            worker=prefix_worker,
                            trajectory_id=f"{pair_id}:prefix",
                            process_label=f"{pair_id}:prefix",
                            calls=prefix_calls,
                            call_guard=call_guard,
                            journal=provider_journal,
                            failure_guard=failure_guard,
                        )
                        prefix = repaired.run_blocked_prefix(
                            backend_factory(r_assignment),
                            system_id=system_id,
                            model=prefix_model,
                        )
                    if getattr(prefix_worker, "closed", True) is not True:
                        raise TechnicalSmokeError(
                            "PREFIX_WORKER_NOT_CLOSED"
                        )
                r_state, n_state, checkpoint = (
                    repaired.fork_restoration_pair(prefix)
                )
                with registry.pair(
                    r_assignment, n_assignment
                ) as (r_worker, n_worker):
                    r_calls = copy.deepcopy(prefix_calls)
                    r_model = RecordingModel(
                        worker=r_worker,
                        trajectory_id=str(r_assignment["trajectory_id"]),
                        process_label=r_id,
                        calls=r_calls,
                        call_guard=call_guard,
                        journal=provider_journal,
                        failure_guard=failure_guard,
                    )
                    repaired._continue_state(
                        r_state,
                        system_id=system_id,
                        arm="R",
                        model=r_model,
                    )
                    _attach_attempt_validation(
                        r_calls, r_state, journal=provider_journal
                    )
                    n_calls = copy.deepcopy(prefix_calls)
                    for row in n_calls:
                        row["trajectory_id"] = str(
                            n_assignment["trajectory_id"]
                        )
                        row["process_label"] = f"{pair_id}:prefix"
                        row["call_sha256"] = semantic_hash(
                            {
                                key: value
                                for key, value in row.items()
                                if key != "call_sha256"
                            }
                        )
                    n_model = RecordingModel(
                        worker=n_worker,
                        trajectory_id=str(n_assignment["trajectory_id"]),
                        process_label=n_id,
                        calls=n_calls,
                        call_guard=call_guard,
                        journal=provider_journal,
                        failure_guard=failure_guard,
                    )
                    repaired._continue_state(
                        n_state,
                        system_id=system_id,
                        arm="N",
                        model=n_model,
                    )
                    _attach_attempt_validation(
                        n_calls, n_state, journal=provider_journal
                    )
                checkpoint_row = {
                    **checkpoint,
                    "pair_id": pair_id,
                    "checkpoint_action_index_zero_based": 4,
                    "checkpoint_event": copy.deepcopy(
                        repaired.CHECKPOINT_EVENT
                    ),
                    "r_assignment_id": r_id,
                    "n_assignment_id": n_id,
                    "r_trajectory_id": r_assignment["trajectory_id"],
                    "n_trajectory_id": n_assignment["trajectory_id"],
                    "prefix_process": prefix_attestation,
                    "technical_smoke_only": True,
                }
                checkpoint_errors = _checkpoint_validation(
                    checkpoint_row,
                    r_state=r_state,
                    n_state=n_state,
                )
                if checkpoint_errors:
                    raise TechnicalSmokeError(
                        "CHECKPOINT_VALIDATION_FAILED",
                        ",".join(checkpoint_errors),
                    )
                checkpoints.append(checkpoint_row)
                _append_jsonl_durable(
                    target / "r_n_prefix_pairs.jsonl", checkpoint_row
                )
                states[r_id] = r_state
                states[n_id] = n_state
                calls_by_id[r_id] = r_calls
                calls_by_id[n_id] = n_calls
                processed.update({r_id, n_id})
                persist_assignment(r_assignment)
                persist_assignment(n_assignment)
            assignment_elapsed = time.monotonic() - boundary_started
            attestations = [
                row
                for label, row in process_by_id.items()
                if not label.endswith(":prefix")
            ]
            isolation = _isolation_report(
                attestations,
                expected_assignment_labels={
                    str(row["assignment_id"])
                    for row in assignments
                    if str(row["assignment_id"]) in processed
                },
                extra_attestations=prefix_attestations,
            )
            leakage = _runtime_leakage_report(
                raw_calls,
                public_trajectories,
                private_rows,
            )
            process_failures = sum(
                isinstance(row.get("failure"), Mapping)
                for row in raw_calls
            )
            malformed = sum(
                row.get("completion_status")
                == "MALFORMED_AFTER_REPAIR"
                for row in failure_rows
            )
            tool_failures = sum(
                row.get("completion_status")
                == "TOOL_CONTRACT_VIOLATION"
                for row in failure_rows
            )
            abort_reasons = _online_abort_reasons(
                total_calls=total_calls,
                effective_assignment_calls={
                    assignment_id: current_call_count
                },
                process_failures=process_failures,
                malformed_after_repair=malformed,
                tool_contract_violations=tool_failures,
                provider_latencies=provider_latencies,
                assignment_elapsed=assignment_elapsed,
                mechanical_scan_hits=leakage[
                    "mechanical_private_surface_scan"
                ]["leakage_hit_count"],
                isolation_collisions=len(isolation["collisions"]),
            )
            if abort_reasons:
                raise TechnicalSmokeError(
                    "ABORT_THRESHOLD_REACHED",
                    ",".join(abort_reasons),
                )
            active_deadline.__exit__(None, None, None)
            active_deadline = None
            registry.deadline = None
    except BaseException as exc:
        abort_deadline = active_deadline
        if active_deadline is not None:
            active_deadline.__exit__(None, None, None)
            registry.deadline = None
        code = (
            exc.code
            if isinstance(
                exc, (TechnicalSmokeError, TechnicalSmokeHardAbort)
            )
            else type(exc).__name__
        )
        provider_journal.close_open_requests(
            code=code,
            detail=str(exc),
        )
        if isinstance(exc, (TechnicalSmokeError, TechnicalSmokeHardAbort)):
            abort_reasons = abort_reasons or [exc.code]
        else:
            abort_reasons = abort_reasons or [type(exc).__name__]
        unstarted = [
            row for row in assignments
            if str(row["assignment_id"]) not in processed
        ]
        aborted_at = _utc_text()
        abort_row = {
            "run_id": run_id,
            "output_root": str(target),
            "started_at_utc": started_at,
            "aborted_at_utc": aborted_at,
            "authorization": copy.deepcopy(
                initial_manifest["authorization"]
            ),
            "provenance": copy.deepcopy(initial_manifest["provenance"]),
            "code": code,
            "detail": str(exc),
            "completed_assignment_count": len(processed),
            "unstarted_assignment_count": len(unstarted),
            "abort_reasons": abort_reasons,
            "deadline_terminated_workers": (
                []
                if abort_deadline is None
                else abort_deadline.terminated_workers
            ),
            "raw_journal_request_count": len(provider_journal.requests),
            "raw_journal_terminal_count": len(
                provider_journal.terminal_rows
            ),
        }
        _append_jsonl_durable(
            target / "abort_ledger.jsonl", abort_row
        )
        for row in unstarted:
            _append_jsonl_durable(
                target / "unstarted_assignments.jsonl",
                {
                    "assignment_id": row["assignment_id"],
                    "ordinal": row["ordinal"],
                    "reason": "RUN_ABORTED_BEFORE_START",
                },
            )
        _atomic_write_json(
            target / "run_manifest.json",
            {
                **initial_manifest,
                "completion_status": "ABORTED",
                "aborted_at_utc": aborted_at,
                "abort_reasons": abort_reasons,
                "completed_assignment_count": len(processed),
                "unstarted_assignment_count": len(unstarted),
                "raw_journal_request_count": len(
                    provider_journal.requests
                ),
                "raw_journal_terminal_count": len(
                    provider_journal.terminal_rows
                ),
            },
        )
        raise

    attestations = [
        row
        for label, row in process_by_id.items()
        if not label.endswith(":prefix")
    ]
    isolation = _isolation_report(
        attestations,
        expected_assignment_labels={
            str(row["assignment_id"]) for row in assignments
        },
        extra_attestations=prefix_attestations,
    )
    leakage = _runtime_leakage_report(
        raw_calls,
        public_trajectories,
        private_rows,
    )
    abort_reasons = _check_abort_thresholds(
        plan=plan,
        checkpoints=checkpoints,
        raw_calls=raw_calls,
        failure_rows=failure_rows,
        completion_rows=completion_rows,
        isolation=isolation,
        leakage=leakage,
    )
    if len(brn_identity) != 12 or not all(
        row["b_r_n_identical"] for row in brn_identity
    ):
        abort_reasons.append("B_R_N_PRE_PREFIX_IDENTITY")
    _write_outputs(
        target,
        plan=plan,
        validation=validation,
        public_trajectories=public_trajectories,
        private_rows=private_rows,
        metrics=metrics,
        failure_rows=failure_rows,
        completion_rows=completion_rows,
        checkpoints=checkpoints,
        isolation=isolation,
        leakage=leakage,
        run_id=run_id,
        testing_injection=testing_injection,
        abort_reasons=abort_reasons,
        authorization=authorization,
        started_at_utc=started_at,
        brn_identity=brn_identity,
        pre_completion_hook=pre_completion_hook,
    )
    if abort_reasons:
        raise TechnicalSmokeError(
            "ABORT_THRESHOLD_EXCEEDED", ",".join(abort_reasons)
        )
    return {
        "status": "TECHNICAL_SMOKE_COMPLETE",
        "run_id": run_id,
        "output_dir": str(target),
        "assignment_count": len(plan["assignments"]),
        "completion_row_count": len(completion_rows),
        "raw_model_call_count": len(raw_calls),
        "checkpoint_pair_count": len(checkpoints),
        "process_isolation_status": isolation["status"],
        "mechanical_private_surface_scan_status": leakage[
            "mechanical_private_surface_scan"
        ]["status"],
        "runtime_leakage_status": leakage["status"],
        "claims": {
            "semantic_validity": False,
            "model_competence": False,
            "performance": False,
            "causal_effect": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--validate-only", action="store_true")
    modes.add_argument("--plan", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir")
    parser.add_argument("--authorization-overlay")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.validate_only:
            report = validate_repository(args.repo_root)
        elif args.plan:
            report = build_plan(args.repo_root)
        else:
            report = execute_technical_smoke(
                args.repo_root,
                output_dir=args.output_dir,
                authorization_overlay=args.authorization_overlay,
            )
    except TechnicalSmokeError as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL_CLOSED",
                    "code": exc.code,
                    "message": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
