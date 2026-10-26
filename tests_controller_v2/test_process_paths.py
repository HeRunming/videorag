from __future__ import annotations

import sys
from pathlib import Path

import pytest

from av_trace_controller_v2 import process as process_module
from av_trace_controller_v2.process import (
    ConstrainedQwenProcess,
    ProcessConfig,
)


def _write_fixture_worker(path: Path) -> Path:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

snapshot = None
if "--snapshot" in sys.argv:
    snapshot = sys.argv[sys.argv.index("--snapshot") + 1]
print(
    json.dumps(
        {
            "type": "ready",
            "argv": sys.argv[1:],
            "cwd": os.getcwd(),
            "snapshot_is_absolute": (
                os.path.isabs(snapshot) if snapshot is not None else None
            ),
            "snapshot_exists": (
                os.path.isdir(snapshot) if snapshot is not None else None
            ),
        }
    ),
    flush=True,
)
for line in sys.stdin:
    if json.loads(line).get("type") == "shutdown":
        break
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _config() -> ProcessConfig:
    return ProcessConfig(
        startup_timeout_s=5,
        generation_timeout_s=5,
        deny_network_namespace=False,
    )


@pytest.mark.parametrize("use_relative_path", [True, False])
def test_default_worker_receives_absolute_snapshot_before_tmp_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    use_relative_path: bool,
) -> None:
    fixture_worker = _write_fixture_worker(tmp_path / "fixture_worker.py")
    snapshot = tmp_path / "snapshots" / "model"
    snapshot.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    supplied_snapshot = (
        snapshot.relative_to(tmp_path) if use_relative_path else snapshot
    )
    monkeypatch.setattr(
        process_module.sys, "executable", str(fixture_worker)
    )

    with ConstrainedQwenProcess(
        supplied_snapshot,
        config=_config(),
    ) as process:
        snapshot_index = process.command.index("--snapshot") + 1
        command_snapshot = Path(process.command[snapshot_index])

        assert process.snapshot == snapshot
        assert command_snapshot == snapshot
        assert command_snapshot.is_absolute()
        assert process.metadata["cwd"] == "/tmp"
        assert process.metadata["snapshot_is_absolute"] is True
        assert process.metadata["snapshot_exists"] is True


def test_custom_fixture_command_is_not_rewritten_or_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_worker = _write_fixture_worker(tmp_path / "fixture_worker.py")
    snapshot = tmp_path / "snapshots" / "model"
    snapshot.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    command = [
        sys.executable,
        str(fixture_worker),
        "custom-fixture",
        "--snapshot",
        "fixture-owned-relative-value",
    ]

    with ConstrainedQwenProcess(
        snapshot.relative_to(tmp_path),
        config=ProcessConfig(
            startup_timeout_s=5,
            generation_timeout_s=5,
            deny_network_namespace=True,
        ),
        command=command,
    ) as process:
        assert process.snapshot == snapshot
        assert process.command == command
        assert process.metadata["argv"] == command[2:]
        assert process.metadata["cwd"] == "/tmp"
        assert process.metadata["snapshot_is_absolute"] is False
        assert process.metadata["network_namespace_denied"] is False
