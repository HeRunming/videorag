from __future__ import annotations

import ast
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Self

import pytest

from av_trace_controller_v2 import execution
from av_trace_controller_v2.packet import verify_execution_seal

from .fixtures import fictional_case

ROOT = Path(__file__).resolve().parents[1]


def _packet() -> dict[str, Any]:
    first = fictional_case()
    second = deepcopy(first)
    second["case_id"] = "fixture-clockwork-orchard-two"
    second["question"] = "Which mark is painted on the second fictional leaf?"
    return {
        "packet_id": "fictional-paired-packet",
        "cases": [first, second],
    }


def _contract_check() -> dict[str, Any]:
    return {
        "contract": {
            "model_and_runtime": {
                "context_limit_tokens": 32768,
                "action_max_new_tokens": 32,
                "state_max_new_tokens": 256,
                "finalizer_max_new_tokens": 512,
            }
        },
        "contract_hash": "sha256:contract",
        "contract_file_sha256": "sha256:contract-file",
        "checked_artifacts": {"public_execution_packet": "sha256:packet"},
        "task111_protected_hashes_from_contract": {
            "task111": "sha256:unchanged"
        },
    }


def _attestation() -> dict[str, Any]:
    return {
        "implementation_worker": "fictional-test-worker",
        "attested_at": "2026-09-21T00:00:00Z",
    }


def _model_identity() -> dict[str, Any]:
    return {
        "repo_id": "fictional/model",
        "revision": "frozen-revision",
        "snapshot_path": "/fictional/snapshot",
        "files": {},
    }


def _result(case_id: str, arm: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "arm": arm,
        "public_payload_hash": f"sha256:{case_id}",
        "action_syntax_valid": True,
        "state_syntax_valid": True,
        "selected_action_index": 0,
        "dispatched_action": {"type": "search"},
        "public_state": {},
        "finalizer_called": False,
        "final": None,
        "finalization_error": None,
        "model_calls": [
            {
                "phase": f"{arm}_phase",
                "status": "valid",
                "request_hash": f"sha256:{case_id}:{arm}",
                "system_prompt_sha256": "sha256:prompt",
                "raw_output_utf8": "{}",
                "raw_sha256": "sha256:raw",
            }
        ],
    }


class FakeProcess:
    instances = 0

    def __init__(self, *_: Any, **__: Any) -> None:
        type(self).instances += 1
        self.metadata = {
            "pid": 4242,
            "offline": True,
            "local_files_only": True,
            "network_namespace_denied": True,
            "device": "cpu",
            "dtype": "torch.bfloat16",
            "constraint_engine": "xgrammar",
        }

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _patch_prerequisites(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[tuple[str, str]],
) -> None:
    FakeProcess.instances = 0
    monkeypatch.setattr(execution, "ConstrainedQwenProcess", FakeProcess)
    monkeypatch.setattr(execution, "load_public_packet", lambda _: _packet())
    monkeypatch.setattr(
        execution, "load_implementation_attestation", lambda _: _attestation()
    )
    monkeypatch.setattr(
        execution, "verify_contract_inputs", lambda **_: _contract_check()
    )
    monkeypatch.setattr(
        execution, "verify_model_snapshot", lambda **_: _model_identity()
    )
    monkeypatch.setattr(
        execution,
        "_verify_task111_hashes",
        lambda **_: {"task111": "sha256:unchanged"},
    )
    monkeypatch.setattr(
        execution, "sha256_file", lambda _: "sha256:fictional-input"
    )
    monkeypatch.setattr(
        execution,
        "execute_v1_case",
        lambda _model, case, **_: (
            events.append((case["case_id"], "v1"))
            or _result(case["case_id"], "v1")
        ),
    )
    monkeypatch.setattr(
        execution,
        "execute_v2_case",
        lambda _model, case, **_: (
            events.append((case["case_id"], "v2"))
            or _result(case["case_id"], "v2")
        ),
    )


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_paired_mode_interleaves_arms_in_one_model_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, str]] = []
    _patch_prerequisites(monkeypatch, events=events)
    report = execution.run_public_packet(
        repo_root=tmp_path,
        arm="paired",
        public_packet_path=tmp_path / "public.json",
        model_snapshot=tmp_path / "snapshot",
        output_dir=tmp_path / "out",
        implementation_attestation_path=tmp_path / "attestation.json",
    )
    assert events == [
        ("fixture-clockwork-orchard", "v1"),
        ("fixture-clockwork-orchard", "v2"),
        ("fixture-clockwork-orchard-two", "v1"),
        ("fixture-clockwork-orchard-two", "v2"),
    ]
    assert FakeProcess.instances == 1
    assert report["manifest"]["confirmatory"] is True
    assert report["manifest"]["paired_protocol"]["model_process_count"] == 1
    trace = _jsonl(tmp_path / "out/order_trace.jsonl")
    assert [(item["case_id"], item["arm"]) for item in trace] == events


def test_paired_mode_writes_separate_artifacts_and_one_complete_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, str]] = []
    _patch_prerequisites(monkeypatch, events=events)
    output_dir = tmp_path / "out"
    report = execution.run_public_packet(
        repo_root=tmp_path,
        arm="paired",
        public_packet_path=tmp_path / "public.json",
        model_snapshot=tmp_path / "snapshot",
        output_dir=output_dir,
        implementation_attestation_path=tmp_path / "attestation.json",
    )
    expected = {
        "v1_results.jsonl",
        "v1_calls.jsonl",
        "v2_results.jsonl",
        "v2_calls.jsonl",
        "order_trace.jsonl",
        "execution_manifest.json",
    }
    assert set(report["seal"]["files"]) == expected
    assert not (output_dir / "results.jsonl").exists()
    assert not (output_dir / "calls.jsonl").exists()
    assert {item["arm"] for item in _jsonl(output_dir / "v1_calls.jsonl")} == {
        "v1"
    }
    assert {item["arm"] for item in _jsonl(output_dir / "v2_calls.jsonl")} == {
        "v2"
    }
    assert verify_execution_seal(output_dir)
    (output_dir / "v2_results.jsonl").chmod(0o644)
    with (output_dir / "v2_results.jsonl").open("ab") as handle:
        handle.write(b"tamper\n")
    assert not verify_execution_seal(output_dir)


def test_runner_never_imports_or_accesses_evaluator_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, str]] = []
    _patch_prerequisites(monkeypatch, events=events)
    original_stat = Path.stat
    original_open = Path.open
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    def _guard(path: Path) -> None:
        if path.name == "restricted_evaluator_key.json":
            raise AssertionError("forbidden evaluator key accessed")

    def guarded_stat(path: Path, *args: Any, **kwargs: Any):
        _guard(path)
        return original_stat(path, *args, **kwargs)

    def guarded_open(path: Path, *args: Any, **kwargs: Any):
        _guard(path)
        return original_open(path, *args, **kwargs)

    def guarded_read_bytes(path: Path, *args: Any, **kwargs: Any):
        _guard(path)
        return original_read_bytes(path, *args, **kwargs)

    def guarded_read_text(path: Path, *args: Any, **kwargs: Any):
        _guard(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", guarded_stat)
    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    execution.run_public_packet(
        repo_root=tmp_path,
        arm="paired",
        public_packet_path=tmp_path / "public.json",
        model_snapshot=tmp_path / "snapshot",
        output_dir=tmp_path / "out",
        implementation_attestation_path=tmp_path / "attestation.json",
    )
    tree = ast.parse(Path(execution.__file__).read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert all("evaluator" not in name for name in imported_modules)
    assert all("scor" not in name for name in imported_modules)


def test_persisted_paired_calls_exclude_prompts_and_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, str]] = []
    _patch_prerequisites(monkeypatch, events=events)
    output_dir = tmp_path / "out"
    execution.run_public_packet(
        repo_root=tmp_path,
        arm="paired",
        public_packet_path=tmp_path / "public.json",
        model_snapshot=tmp_path / "snapshot",
        output_dir=output_dir,
        implementation_attestation_path=tmp_path / "attestation.json",
    )
    forbidden = {
        "system",
        "system_prompt",
        "payload",
        "request_payload",
        "messages",
    }
    for name in ("v1_calls.jsonl", "v2_calls.jsonl"):
        for call in _jsonl(output_dir / name):
            assert forbidden.isdisjoint(call)


def test_single_arm_mode_is_explicitly_non_confirmatory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, str]] = []
    _patch_prerequisites(monkeypatch, events=events)
    report = execution.run_public_packet(
        repo_root=tmp_path,
        arm="v1",
        public_packet_path=tmp_path / "public.json",
        model_snapshot=tmp_path / "snapshot",
        output_dir=tmp_path / "out",
        implementation_attestation_path=tmp_path / "attestation.json",
    )
    assert report["manifest"]["confirmatory"] is False
    assert report["manifest"]["execution_mode"] == (
        "non_confirmatory_single_arm"
    )


def test_task111_protected_hashes_are_unchanged() -> None:
    expected = {
        "data/restricted/scale1b/controller_dev/suite_contract.json": (
            "b4aa831e77e6b8f744387f5a02e1516082bf0b990c010dca2a7d8e83d33f3ef7"
        ),
        "data/restricted/scale1b/controller_dev/results.json": (
            "02f10aa9c781f132e81679d221b696453cbf1d04d146f37eb730f44a6aab1c1d"
        ),
        "data/restricted/scale1b/controller_dev/summary.json": (
            "131643b79fc4addb866c1f07e79f503f00f9e659e3f5618f196f61fc6775af96"
        ),
        "data/restricted/scale1b/controller_dev/calls.jsonl": (
            "1c8e433668d10c242179b7393f67791d0a3127af13210bd4010580d668353654"
        ),
        "docs/review/controller_synthetic_competence.md": (
            "4663c65a633a1fcd0df3c3e6434d3c926e4541c3d9f0335b5db266f24d0fb769"
        ),
        "orchestration/results/111_controller_synthetic_competence.txt": (
            "fa641ddbfd31ed19b315f8c88e73c394e8ebebd3c7452ab52465554779b40698"
        ),
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
