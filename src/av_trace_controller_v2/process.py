"""Bounded parent-side client for the offline constrained Qwen worker."""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from av_trace_scale1b_agent.process import ModelProcessError


@dataclass(frozen=True)
class ProcessConfig:
    startup_timeout_s: float = 240.0
    generation_timeout_s: float = 180.0
    max_line_bytes: int = 1_000_000
    threads: int = 8
    max_context_tokens: int = 32768
    deny_network_namespace: bool = True


class ConstrainedQwenProcess:
    """Reusable local model process with optional per-call JSON constraints."""

    def __init__(
        self,
        snapshot: Path,
        *,
        config: ProcessConfig | None = None,
        command: list[str] | None = None,
    ) -> None:
        self.snapshot = snapshot.resolve()
        self.config = config or ProcessConfig()
        home = Path("/tmp/av-trace-controller-v2-worker-home")
        home.mkdir(mode=0o700, exist_ok=True)
        package_root = str(Path(__file__).resolve().parents[1])
        python_paths = [package_root, *(str(item) for item in sys.path if item)]
        worker_command = command or [
            sys.executable,
            "-m",
            "av_trace_controller_v2.model_worker",
            "--snapshot",
            str(self.snapshot),
            "--threads",
            str(self.config.threads),
            "--max-context-tokens",
            str(self.config.max_context_tokens),
        ]
        self.command = (
            ["unshare", "-n", "--", *worker_command]
            if self.config.deny_network_namespace and command is None
            else worker_command
        )
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.pathsep.join(dict.fromkeys(python_paths)),
            "HOME": str(home),
            "PYTHONHASHSEED": "0",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
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
                cwd="/tmp",
            )
        except OSError as exc:
            raise ModelProcessError("SPAWN_FAILED", str(exc)) from exc
        assert self.process.stdin and self.process.stdout and self.process.stderr
        os.set_blocking(self.process.stdout.fileno(), False)
        os.set_blocking(self.process.stderr.fileno(), False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
        self.selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")
        self.buffer = bytearray()
        self.stderr = bytearray()
        ready = self._receive(self.config.startup_timeout_s)
        if ready.get("type") != "ready":
            self.close()
            raise ModelProcessError("WORKER_NOT_READY", repr(ready))
        ready["network_namespace_denied"] = (
            self.config.deny_network_namespace and command is None
        )
        self.metadata = ready

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
                    raise ModelProcessError(
                        "MALFORMED_WORKER_JSON", str(exc)
                    ) from exc
                if not isinstance(value, dict):
                    raise ModelProcessError(
                        "MALFORMED_WORKER_JSON", "not an object"
                    )
                return value
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ModelProcessError("TIMEOUT", "worker response timeout")
            for key, _ in self.selector.select(remaining):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    if key.data == "stdout":
                        code = self.process.poll()
                        stderr = self.stderr[-500:].decode(errors="replace")
                        raise ModelProcessError(
                            "PROCESS_CRASH",
                            f"worker closed stdout rc={code}; stderr={stderr}",
                        )
                    self.selector.unregister(key.fileobj)
                elif key.data == "stdout":
                    self.buffer.extend(chunk)
                    if len(self.buffer) > self.config.max_line_bytes:
                        raise ModelProcessError(
                            "OUTPUT_LIMIT", "worker line too large"
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
        constraint_schema: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.process.poll() is not None:
            raise ModelProcessError("PROCESS_CRASH", "worker is not running")
        request = {
            "type": "generate",
            "system": system,
            "payload": dict(payload),
            "max_new_tokens": max_new_tokens,
            "constraint_schema": (
                dict(constraint_schema) if constraint_schema is not None else None
            ),
        }
        raw = (
            json.dumps(request, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode("utf-8")
        if len(raw) > self.config.max_line_bytes:
            raise ModelProcessError("INPUT_LIMIT", "worker request too large")
        try:
            assert self.process.stdin
            self.process.stdin.write(raw)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ModelProcessError("PROCESS_CRASH", str(exc)) from exc
        response = self._receive(self.config.generation_timeout_s)
        if response.get("type") == "error":
            raise ModelProcessError(
                str(response.get("code", "MODEL_ERROR")),
                str(response.get("message", "")),
            )
        if response.get("type") != "generation":
            raise ModelProcessError(
                "UNEXPECTED_WORKER_MESSAGE", repr(response)
            )
        return response

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                try:
                    assert self.process.stdin
                    self.process.stdin.write(b'{"type":"shutdown"}\n')
                    self.process.stdin.flush()
                    self.process.wait(timeout=5)
                except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self.process.wait(timeout=5)
        finally:
            self.selector.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
