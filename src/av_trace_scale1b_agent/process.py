"""Bounded parent-side client for the offline Qwen worker."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self


class ModelProcessError(RuntimeError):
    """Typed worker failure with persistence-safe diagnostic metadata."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_record(self) -> dict[str, Any]:
        """Return all available failure evidence for durable result records."""

        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ProcessConfig:
    startup_timeout_s: float = 180.0
    generation_timeout_s: float = 120.0
    max_line_bytes: int = 1_000_000
    threads: int = 8
    max_context_tokens: int = 12288
    deny_network_namespace: bool = False
    shutdown_timeout_s: float = 5.0


@dataclass(frozen=True)
class ProcessIsolationAttestation:
    """Auditable proof fields for one fresh model-process namespace."""

    session_id: str
    cache_namespace: str
    continuation_label: str | None
    pid: int
    process_group_id: int
    runtime_namespace: str
    network_namespace_denied: bool
    offline_environment: bool = True
    fresh_process: bool = True
    shared_conversation_state: bool = False
    shared_kv_state: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "cache_namespace": self.cache_namespace,
            "continuation_label": self.continuation_label,
            "pid": self.pid,
            "process_group_id": self.process_group_id,
            "runtime_namespace": self.runtime_namespace,
            "network_namespace_denied": self.network_namespace_denied,
            "offline_environment": self.offline_environment,
            "fresh_process": self.fresh_process,
            "shared_conversation_state": self.shared_conversation_state,
            "shared_kv_state": self.shared_kv_state,
        }


class QwenProcess:
    """One reusable model process; requests and responses are single JSONL lines."""

    def __init__(
        self,
        snapshot: Path,
        *,
        config: ProcessConfig | None = None,
        command: list[str] | None = None,
        session_id: str | None = None,
        cache_namespace: str | None = None,
        continuation_label: str | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.config = config or ProcessConfig()
        self.session_id = session_id or f"qwen-{uuid.uuid4().hex}"
        self.cache_namespace = cache_namespace or f"cache-{uuid.uuid4().hex}"
        self.continuation_label = continuation_label
        self._closed = False
        self._request_count = 0
        self._request_hashes: list[str] = []
        self.runtime_dir = Path(
            tempfile.mkdtemp(prefix="av-trace-qwen-", dir="/tmp")
        )
        os.chmod(self.runtime_dir, 0o700)
        home = self.runtime_dir / "home"
        cache_root = self.runtime_dir / "cache" / self.cache_namespace
        tmp_root = self.runtime_dir / "tmp"
        for path in (home, cache_root, tmp_root):
            path.mkdir(parents=True, mode=0o700)
        package_root = str(Path(__file__).resolve().parents[1])
        python_paths = [package_root, *(str(item) for item in sys.path if item)]
        worker_command = command or [
            sys.executable,
            "-m",
            "av_trace_scale1b_agent.model_worker",
            "--snapshot",
            str(snapshot),
            "--threads",
            str(self.config.threads),
            "--max-context-tokens",
            str(self.config.max_context_tokens),
        ]
        self.command = (
            ["unshare", "-n", "--", *worker_command]
            if self.config.deny_network_namespace
            else worker_command
        )
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.pathsep.join(dict.fromkeys(python_paths)),
            "HOME": str(home),
            "TMPDIR": str(tmp_root),
            "XDG_CACHE_HOME": str(cache_root),
            "HF_HOME": str(cache_root / "huggingface"),
            "HUGGINGFACE_HUB_CACHE": str(cache_root / "huggingface" / "hub"),
            "TRANSFORMERS_CACHE": str(cache_root / "transformers"),
            "PYTHONHASHSEED": "0",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "AV_TRACE_SESSION_ID": self.session_id,
            "AV_TRACE_CACHE_NAMESPACE": self.cache_namespace,
            "AV_TRACE_CONTINUATION_LABEL": continuation_label or "",
        }
        for key in (
            "HF_TOKEN",
            "HUGGING_FACE_HUB_TOKEN",
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "all_proxy",
            "NO_PROXY",
            "no_proxy",
        ):
            env.pop(key, None)
        self.process: subprocess.Popen[bytes] | None = None
        self.selector = selectors.DefaultSelector()
        self.buffer = bytearray()
        self.stderr = bytearray()
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                close_fds=True,
                start_new_session=True,
                env=env,
                cwd=str(self.runtime_dir),
            )
        except OSError as exc:
            self.selector.close()
            shutil.rmtree(self.runtime_dir, ignore_errors=True)
            raise ModelProcessError(
                "SPAWN_FAILED",
                str(exc),
                details=self._diagnostic_details(),
            ) from exc
        assert self.process.stdin and self.process.stdout and self.process.stderr
        os.set_blocking(self.process.stdout.fileno(), False)
        os.set_blocking(self.process.stderr.fileno(), False)
        self.selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
        self.selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")
        try:
            ready = self._receive(self.config.startup_timeout_s)
        except ModelProcessError:
            self.close()
            raise
        if ready.get("type") != "ready":
            details = self._diagnostic_details(worker_message=ready)
            self.close()
            raise ModelProcessError(
                "WORKER_NOT_READY",
                repr(ready),
                details=details,
            )
        ready["network_namespace_denied"] = self.config.deny_network_namespace
        ready.update(self.isolation_attestation().to_dict())
        self.metadata = ready

    def _stderr_text(self) -> str:
        return self.stderr[-100_000:].decode(errors="replace")

    def _drain_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        while True:
            try:
                chunk = os.read(process.stderr.fileno(), 65536)
            except BlockingIOError:
                return
            if not chunk:
                return
            self.stderr.extend(chunk)
            del self.stderr[: max(0, len(self.stderr) - 100_000)]

    def _process_group_id(self) -> int | None:
        process = self.process
        if process is None:
            return None
        try:
            return os.getpgid(process.pid)
        except ProcessLookupError:
            return process.pid

    def _diagnostic_details(self, **extra: Any) -> dict[str, Any]:
        process = self.process
        details: dict[str, Any] = {
            "session_id": self.session_id,
            "cache_namespace": self.cache_namespace,
            "continuation_label": self.continuation_label,
            "runtime_namespace": str(self.runtime_dir),
            "command": list(self.command),
            "pid": process.pid if process is not None else None,
            "process_group_id": self._process_group_id(),
            "returncode": process.poll() if process is not None else None,
            "stderr_text": self._stderr_text(),
            "request_count": self._request_count,
            "request_hashes": list(self._request_hashes),
            "offline_environment": True,
            "network_namespace_denied": self.config.deny_network_namespace,
        }
        details.update(extra)
        return details

    def _failure(
        self, code: str, message: str, **details: Any
    ) -> ModelProcessError:
        return ModelProcessError(
            code,
            message,
            details=self._diagnostic_details(**details),
        )

    def isolation_attestation(self) -> ProcessIsolationAttestation:
        process = self.process
        if process is None:
            raise RuntimeError("process has not been spawned")
        return ProcessIsolationAttestation(
            session_id=self.session_id,
            cache_namespace=self.cache_namespace,
            continuation_label=self.continuation_label,
            pid=process.pid,
            process_group_id=self._process_group_id() or process.pid,
            runtime_namespace=str(self.runtime_dir),
            network_namespace_denied=self.config.deny_network_namespace,
        )

    def _receive(self, timeout_s: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while True:
            newline = self.buffer.find(b"\n")
            if newline >= 0:
                raw = bytes(self.buffer[:newline])
                del self.buffer[: newline + 1]
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise self._failure(
                        "MALFORMED_WORKER_JSON",
                        str(exc),
                        raw_stdout=raw.decode(errors="replace"),
                    ) from exc
                if not isinstance(value, dict):
                    raise self._failure(
                        "MALFORMED_WORKER_JSON",
                        "not an object",
                        raw_stdout=raw.decode(errors="replace"),
                    )
                return value
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise self._failure("TIMEOUT", "worker response timeout")
            events = self.selector.select(remaining)
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    if key.data == "stdout":
                        assert self.process is not None
                        code = self.process.poll()
                        self._drain_stderr()
                        raise self._failure(
                            "PROCESS_CRASH",
                            f"worker closed stdout rc={code}",
                        )
                    self.selector.unregister(key.fileobj)
                elif key.data == "stdout":
                    self.buffer.extend(chunk)
                    if len(self.buffer) > self.config.max_line_bytes:
                        raise self._failure(
                            "OUTPUT_LIMIT",
                            "worker line too large",
                            buffered_stdout_bytes=len(self.buffer),
                        )
                else:
                    self.stderr.extend(chunk)
                    del self.stderr[: max(0, len(self.stderr) - 100_000)]

    def generate(
        self,
        *,
        system: str,
        payload: Mapping[str, Any],
        max_new_tokens: int,
    ) -> dict[str, Any]:
        assert self.process is not None
        if self.process.poll() is not None:
            raise self._failure("PROCESS_CRASH", "worker is not running")
        request_id = f"{self.session_id}:{self._request_count}"
        request = {
            "type": "generate",
            "session_id": self.session_id,
            "cache_namespace": self.cache_namespace,
            "request_id": request_id,
            "system": system,
            "payload": dict(payload),
            "max_new_tokens": max_new_tokens,
        }
        raw = (
            json.dumps(request, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode()
        request_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
        if len(raw) > self.config.max_line_bytes:
            raise self._failure(
                "INPUT_LIMIT",
                "worker request too large",
                request_id=request_id,
                request_hash=request_hash,
                request_bytes=len(raw),
            )
        self._request_count += 1
        self._request_hashes.append(request_hash)
        try:
            assert self.process.stdin
            self.process.stdin.write(raw)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise self._failure(
                "PROCESS_CRASH",
                str(exc),
                request_id=request_id,
                request_hash=request_hash,
            ) from exc
        response = self._receive(self.config.generation_timeout_s)
        if response.get("type") == "error":
            raise self._failure(
                str(response.get("code", "MODEL_ERROR")),
                str(response.get("message", "")),
                worker_error=dict(response),
                request_id=request_id,
                request_hash=request_hash,
            )
        if response.get("type") != "generation":
            raise self._failure(
                "UNEXPECTED_WORKER_MESSAGE",
                repr(response),
                worker_message=dict(response),
                request_id=request_id,
                request_hash=request_hash,
            )
        return response

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            process = self.process
            if process is not None and process.poll() is None:
                try:
                    assert process.stdin
                    process.stdin.write(b'{"type":"shutdown"}\n')
                    process.stdin.flush()
                    process.wait(timeout=self.config.shutdown_timeout_s)
                except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=self.config.shutdown_timeout_s)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=self.config.shutdown_timeout_s)
        finally:
            self.selector.close()
            shutil.rmtree(self.runtime_dir, ignore_errors=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@dataclass
class ContinuationProcessPair:
    """Fresh, non-sharing process pair for matched R/N continuations."""

    restored: QwenProcess
    no_trigger: QwenProcess
    labels: tuple[str, str] = field(default=("R", "N"))

    def attestations(self) -> dict[str, dict[str, Any]]:
        return {
            self.labels[0]: self.restored.isolation_attestation().to_dict(),
            self.labels[1]: self.no_trigger.isolation_attestation().to_dict(),
        }


CommandFactory = Callable[[str], list[str]]


class FreshQwenProcessFactory:
    """Create per-continuation workers with no shared process or cache state."""

    def __init__(
        self,
        snapshot: Path,
        *,
        config: ProcessConfig | None = None,
        command: list[str] | None = None,
        command_factory: CommandFactory | None = None,
    ) -> None:
        if command is not None and command_factory is not None:
            raise ValueError("provide command or command_factory, not both")
        self.snapshot = snapshot
        self.config = config or ProcessConfig()
        self.command = list(command) if command is not None else None
        self.command_factory = command_factory

    def create(self, continuation_label: str) -> QwenProcess:
        command = (
            self.command_factory(continuation_label)
            if self.command_factory is not None
            else (list(self.command) if self.command is not None else None)
        )
        nonce = uuid.uuid4().hex
        return QwenProcess(
            self.snapshot,
            config=self.config,
            command=command,
            session_id=f"session-{nonce}",
            cache_namespace=f"cache-{nonce}",
            continuation_label=continuation_label,
        )

    def __call__(self, continuation_label: str) -> QwenProcess:
        """Allow direct runner injection as a one-argument process factory."""

        return self.create(continuation_label)

    @contextlib.contextmanager
    def continuations(
        self,
        *,
        restored_label: str = "R",
        no_trigger_label: str = "N",
    ) -> Iterator[ContinuationProcessPair]:
        """Yield two live fresh workers and bound cleanup on every exit path."""

        with contextlib.ExitStack() as stack:
            restored = stack.enter_context(self.create(restored_label))
            no_trigger = stack.enter_context(self.create(no_trigger_label))
            restored_attestation = restored.isolation_attestation()
            no_trigger_attestation = no_trigger.isolation_attestation()
            for field_name in (
                "session_id",
                "cache_namespace",
                "pid",
                "process_group_id",
                "runtime_namespace",
            ):
                if getattr(restored_attestation, field_name) == getattr(
                    no_trigger_attestation, field_name
                ):
                    raise ModelProcessError(
                        "ISOLATION_COLLISION",
                        f"R/N collision in {field_name}",
                        details={
                            "restored": restored_attestation.to_dict(),
                            "no_trigger": no_trigger_attestation.to_dict(),
                        },
                    )
            yield ContinuationProcessPair(
                restored=restored,
                no_trigger=no_trigger,
                labels=(restored_label, no_trigger_label),
            )
