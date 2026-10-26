from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import ClassVar

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_mini_pilot_full_timeline.py"


def _module():
    spec = importlib.util.spec_from_file_location("mini_pilot_build_cli", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_exposes_required_controls():
    module = _module()
    args = module.build_parser().parse_args(
        [
            "--plan", "plan.json", "--output-root", "out", "--no-resume",
            "--threads", "3", "--device", "cpu", "--smoke-seconds", "12.5",
        ]
    )
    assert args.plan == "plan.json"
    assert args.output_root == "out"
    assert args.resume is False
    assert args.threads == 3
    assert args.device == "cpu"
    assert args.smoke_seconds == 12.5


def test_default_command_runs_offline_preflight_only(monkeypatch, capsys):
    module = _module()
    called = False

    def forbidden_build(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("build must not run without --execute")

    monkeypatch.setattr(module, "_invoke_build", forbidden_build)
    assert module.main(["--repo-root", str(ROOT)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "offline_technical_preflight"
    assert payload["network_access"] == "disabled"
    assert payload["models_loaded"] is False
    assert payload["media_decoded"] is False
    assert payload["source_count"] == 4
    assert payload["expected_checkpoint_count"] == 16
    assert called is False


def test_smoke_refuses_to_fall_through_to_full_build(monkeypatch, tmp_path: Path):
    module = _module()

    class Plan:
        model_snapshots: ClassVar = {
            "vision_semantic": {"snapshot_path": "clip"},
            "speech": {"snapshot_path": "whisper"},
            "ambient": {"snapshot_path": "ast"},
            "vision_routing": {"haar_snapshot_path": "haar"},
        }
        sources: ClassVar = [object()] * 4
        repo_root = tmp_path
        raw: ClassVar = {
            "storage_caps": {"derived_artifacts_hard_fail_cap_mib": 512}
        }

    monkeypatch.setattr(module, "_config_for", lambda *args: object())

    def build_without_smoke(repo_root, config, *, resume=True):
        raise AssertionError("must not be called")

    monkeypatch.setattr(
        "av_trace_mini_pilot_index.core.build_mini_pilot_index",
        build_without_smoke,
    )
    original_signature = module.inspect.signature
    monkeypatch.setattr(
        module.inspect,
        "signature",
        lambda value: original_signature(build_without_smoke),
    )
    with pytest.raises(RuntimeError, match="SMOKE_NOT_SUPPORTED_BY_CORE"):
        module._invoke_build(
            tmp_path,
            plan=Plan(),
            output_root=tmp_path / "out",
            resume=True,
            threads=1,
            device="cpu",
            smoke_seconds=5.0,
        )


def test_execute_forwards_supported_runtime_controls(monkeypatch, tmp_path: Path):
    module = _module()
    received = {}

    class Plan:
        model_snapshots: ClassVar = {
            "vision_semantic": {"snapshot_path": "clip"},
            "speech": {"snapshot_path": "whisper"},
            "ambient": {"snapshot_path": "ast"},
            "vision_routing": {"haar_snapshot_path": "haar"},
        }
        sources: ClassVar = [object()] * 4
        repo_root = tmp_path
        raw: ClassVar = {
            "storage_caps": {"derived_artifacts_hard_fail_cap_mib": 512}
        }

    monkeypatch.setattr(module, "_config_for", lambda *args: "config")

    def fake_build(
        repo_root,
        config,
        *,
        resume=True,
        threads=8,
        device="cpu",
        smoke_seconds=None,
        media_backend=None,
    ):
        received.update(
            repo_root=repo_root,
            config=config,
            resume=resume,
            threads=threads,
            device=device,
            smoke_seconds=smoke_seconds,
            media_backend=media_backend,
        )
        return {}

    monkeypatch.setattr("av_trace_mini_pilot_index.core.build_mini_pilot_index", fake_build)
    module._invoke_build(
        tmp_path,
        plan=Plan(),
        output_root=tmp_path / "out",
        resume=False,
        threads=2,
        device="cpu",
        smoke_seconds=7.0,
    )
    assert received["repo_root"] == tmp_path
    assert received["config"] == "config"
    assert received["resume"] is False
    assert received["threads"] == 2
    assert received["device"] == "cpu"
    assert received["smoke_seconds"] == 7.0
    assert received["media_backend"]._smoke_seconds == 7.0
