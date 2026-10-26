from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from av_trace_strong_baselines_v2 import (
    AttemptKind,
    FactorStatus,
    RawFactorAttempt,
)
from tools import external_gateway_strong_agent as route


def registry() -> dict:
    return json.loads((ROOT / route.REGISTRY).read_text())


def _binding() -> dict:
    return {
        "model_slug": "gpt-6-astra",
        "catalog_record_sha256": None,
        "catalog_file_sha256": None,
        "catalog_archive_path": None,
        "tcodex_version": "0.0.16",
        "tcodex_commit": "0acab16d13a",
        "upstream_codex_version": "0.144.5",
        "tcodex_wrapper_sha256": "sha256:wrapper",
        "upstream_codex_binary_sha256": "sha256:binary",
        "observed_invocations": [],
    }


def test_public_smoke_is_exactly_two_development_cases() -> None:
    packets = route.public_smoke_packets()
    assert len(packets) == 2
    assert [packet["case_type"] for packet in packets] == [
        "controller",
        "finalizer",
    ]
    assert all(packet["public_fictional"] is True for packet in packets)
    assert all(packet["source_free"] is True for packet in packets)
    assert all(packet["development_only"] is True for packet in packets)
    assert "scoring_target" not in json.dumps(packets)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("H2_labels", ["private"]),
        ("SESs", ["private"]),
        ("evaluator_key", "private"),
        ("source_text", "private"),
        ("trigger", "private"),
        ("video_path", "clip.mp4"),
    ],
)
def test_privacy_guard_rejects_forbidden_uploads(
    key: str,
    value: object,
) -> None:
    packet = route.public_smoke_packets()[0]
    packet[key] = value
    with pytest.raises(route.ExternalGatewayError):
        route.validate_public_packet(packet)


def test_factor_prompts_contain_no_private_label_surface() -> None:
    for packet in route.public_smoke_packets():
        for factor in route.FACTOR_ORDER[packet["case_type"]]:
            prompt = route.factor_prompt(packet, factor)
            lowered = prompt.casefold()
            assert "scoring_target" not in lowered
            assert "private_labels" not in lowered
            assert "answer_key" not in lowered
            assert "evaluator_key" not in lowered
            assert "public_fictional_source_free_development_packet_only" in (
                lowered
            )


def test_noninteractive_command_binds_model_and_disables_tools(
    tmp_path: Path,
) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("public fictional packet", encoding="utf-8")
    output = tmp_path / "raw.txt"
    command = route.tcodex_exec_command(
        model_slug="gpt-6-astra",
        reasoning_effort="high",
        prompt_path=prompt,
        output_path=output,
        workspace=tmp_path,
    )
    expected = [
        "tcodex",
        "--",
        "-a",
        "never",
        "-s",
        "read-only",
        "-C",
        str(tmp_path),
        "exec",
        "--skip-git-repo-check",
        "--color",
        "never",
        "--model",
        "gpt-6-astra",
        "-c",
        'model_reasoning_effort="high"',
        "-c",
        'model_verbosity="low"',
        "-c",
        "check_for_update_on_startup=false",
        "-c",
        "analytics.enabled=false",
        "-o",
        str(output),
    ]
    for feature in route.DISABLED_FEATURES:
        expected.extend(("-c", f"features.{feature}=false"))
    expected.append("-")
    assert command == expected


def test_global_codex_flags_precede_exec_subcommand(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("public fictional packet", encoding="utf-8")
    command = route.tcodex_exec_command(
        model_slug="gpt-6-astra",
        reasoning_effort="high",
        prompt_path=prompt,
        output_path=tmp_path / "raw.txt",
        workspace=tmp_path / "empty_workspace",
    )
    exec_index = command.index("exec")
    assert command[2:exec_index] == [
        "-a",
        "never",
        "-s",
        "read-only",
        "-C",
        str(tmp_path / "empty_workspace"),
    ]
    assert "-a" not in command[exec_index + 1 :]
    assert "-s" not in command[exec_index + 1 :]
    assert "-C" not in command[exec_index + 1 :]
    assert "--ephemeral" not in command
    assert "--ignore-user-config" not in command
    assert "--ignore-rules" not in command


def test_schema_retry_cannot_change_action_semantics() -> None:
    packet = route.public_smoke_packets()[0]
    attempts = (
        RawFactorAttempt.from_text(
            '{"function_name":"select_action_99","arguments":[]}'
        ),
        RawFactorAttempt.from_text(
            '{"function_name":"select_action_00","arguments":{}}',
            attempt_index=2,
            kind=AttemptKind.SCHEMA_ONLY_RETRY,
        ),
    )
    outcome = route.parse_factor_outcome(
        packet,
        "action_choice",
        attempts,
    )
    assert outcome.status is FactorStatus.INVALID_OUTPUT
    assert outcome.error_code == "SEMANTIC_RETRY_FORBIDDEN"


def test_raw_attempt_record_preserves_bytes_and_hash() -> None:
    raw = b'{"text":"The fictional badge is octagonal."}\n'
    record = route._attempt_record(
        packet=route.public_smoke_packets()[1],
        factor_name="answer_text",
        attempt_index=1,
        command=["tcodex", "--", "exec"],
        prompt=b"public prompt",
        raw_output=raw,
        stdout=b"",
        stderr=b"",
        returncode=0,
        elapsed_seconds=0.5,
        binding={
            "model_slug": "gpt-6-astra",
            "catalog_record_sha256": "sha256:record",
            "catalog_file_sha256": "sha256:catalog",
            "catalog_archive_path": str(
                ROOT / "data/rehearsal_plan/catalog.json"
            ),
            "tcodex_version": "0.0.16",
            "tcodex_commit": "0acab16d13a",
            "upstream_codex_version": "0.144.5",
            "tcodex_wrapper_sha256": "sha256:wrapper",
            "upstream_codex_binary_sha256": "sha256:binary",
        },
    )
    assert record["raw_output"].encode() == raw
    assert record["raw_output_sha256"] == (
        "sha256:" + hashlib.sha256(raw).hexdigest()
    )
    assert record["gateway_success"] is True


def test_registry_selects_materially_different_backup() -> None:
    value = registry()
    route.validate_registry(value)
    assert value["models"]["primary"]["slug"] == "gpt-6-astra"
    assert value["models"]["primary"]["family"] == "OpenAI GPT"
    assert value["models"]["backup"]["slug"] == "deepseek-v4-pro-ioa"
    assert value["models"]["backup"]["family"] == "DeepSeek"
    assert value["models"]["automatic_fallback"] is False


def test_runtime_binding_does_not_reuse_registry_catalog_or_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    value = registry()
    value["catalog"]["path"] = "/path/to/av-trace"
    monkeypatch.setattr(
        route,
        "tcodex_version",
        lambda: {
            "tcodex_version": "0.0.16",
            "tcodex_commit": "0acab16d13a",
            "tcodex_built": "2026-07-17 17:08:19",
            "upstream_codex_version": "0.144.5",
        },
    )
    wrapper = tmp_path / "tcodex.js"
    native = tmp_path / "codex"
    wrapper.write_bytes(b"wrapper")
    native.write_bytes(b"native")
    monkeypatch.setattr(
        route,
        "_tcodex_package_paths",
        lambda: (wrapper, native),
    )
    monkeypatch.setattr(route.shutil, "which", lambda _: "/usr/bin/tcodex")
    value["runtime_binding"]["tcodex_wrapper_sha256"] = route.sha256_file(
        wrapper
    )
    value["runtime_binding"]["upstream_codex_binary_sha256"] = (
        route.sha256_file(native)
    )
    binding = route.runtime_binding(value, "gpt-6-astra")
    assert binding["catalog_record_sha256"] is None
    assert binding["catalog_file_sha256"] is None
    assert binding["catalog_archive_path"] is None
    assert binding["catalog_selected_model_evidenced"] is False
    assert binding["wrapper_binding_observed"] is False
    assert "catalog_path" not in binding
    assert "base_url" not in binding


def _wrapper_child_argv(catalog_path: Path, model_slug: str) -> list[str]:
    return [
        "/package/@openai/codex/bin/codex.js",
        "-c",
        (
            "model_providers.tencent={ name = "
            '"Tencent Internal Gateway", '
            'base_url = "http://127.0.0.1:43210", '
            'wire_api = "responses" }'
        ),
        "-c",
        'model_provider="tencent"',
        "-c",
        f'model_catalog_json="{catalog_path}"',
        "exec",
        "--model",
        model_slug,
        "-",
    ]


def test_capture_wrapper_binding_archives_exact_selected_catalog(
    tmp_path: Path,
) -> None:
    row = {
        "slug": "gpt-6-astra",
        "display_name": "GPT-6-Astra",
        "supported_reasoning_levels": [{"effort": "high"}],
    }
    catalog_path = tmp_path / "instances" / "43210" / "models.json"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(
        json.dumps({"models": [row]}, indent=2) + "\n",
        encoding="utf-8",
    )
    archive_path = tmp_path / "run" / "provenance" / "model_catalog.json"
    binding = route.capture_wrapper_binding(
        child_argv=_wrapper_child_argv(catalog_path, "gpt-6-astra"),
        expected_slug="gpt-6-astra",
        catalog_archive_path=archive_path,
    )
    assert archive_path.read_bytes() == catalog_path.read_bytes()
    assert binding["catalog_file_sha256"] == route.sha256_file(catalog_path)
    assert binding["catalog_record_sha256"] == route.sha256_bytes(
        route.canonical_json_bytes(row)
    )
    assert binding["catalog_archive_path"] == str(archive_path)
    assert binding["catalog_selected_model_evidenced"] is True
    assert binding["wrapper_selected_model"] == "gpt-6-astra"
    assert binding["wrapper_dynamic_port_observed"] is True
    assert "43210" not in json.dumps(binding)
    assert "/path/to/av-trace" not in json.dumps(binding)


def test_capture_wrapper_binding_fails_closed_without_selected_slug(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "instances" / "43210" / "models.json"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(
        json.dumps({"models": [{"slug": "gpt-6-astra"}]}),
        encoding="utf-8",
    )
    child_argv = _wrapper_child_argv(catalog_path, "gpt-6-astra")
    model_index = child_argv.index("--model")
    del child_argv[model_index : model_index + 2]
    with pytest.raises(
        route.ExternalGatewayError,
        match="TCODEX_SELECTED_MODEL_NOT_EVIDENCED",
    ):
        route.capture_wrapper_binding(
            child_argv=child_argv,
            expected_slug="gpt-6-astra",
            catalog_archive_path=tmp_path / "archive.json",
        )


def test_capture_wrapper_binding_rejects_mismatched_slug(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "instances" / "43210" / "models.json"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(
        json.dumps({"models": [{"slug": "deepseek-v4-pro-ioa"}]}),
        encoding="utf-8",
    )
    with pytest.raises(
        route.ExternalGatewayError,
        match="TCODEX_SELECTED_MODEL_MISMATCH",
    ):
        route.capture_wrapper_binding(
            child_argv=_wrapper_child_argv(
                catalog_path,
                "deepseek-v4-pro-ioa",
            ),
            expected_slug="gpt-6-astra",
            catalog_archive_path=tmp_path / "archive.json",
        )


def test_process_group_cleanup_kills_descendant_retaining_pipes() -> None:
    script = (
        "import os, signal, time\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    print('descendant-ready', flush=True)\n"
        "    time.sleep(60)\n"
        "time.sleep(60)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    time.sleep(0.2)
    started = time.monotonic()
    stdout, stderr, cleanup = route._terminate_process_group(
        process,
        terminate_wait_seconds=1.0,
        kill_wait_seconds=1.0,
        drain_wait_seconds=1.0,
    )
    assert time.monotonic() - started < 4.0
    assert b"descendant-ready" in stdout
    assert stderr == b""
    assert cleanup["terminate_group_sent"] is True
    assert cleanup["kill_group_sent"] is True
    assert cleanup["pipe_drain_timed_out"] is False
    assert process.poll() is not None


def test_process_group_cleanup_bounds_every_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Pipe:
        closed = False

        def close(self) -> None:
            self.closed = True

    class Process:
        pid = 43210
        returncode = None
        stdin = Pipe()
        stdout = Pipe()
        stderr = Pipe()

        def wait(self, timeout: float) -> None:
            raise subprocess.TimeoutExpired("wait", timeout)

        def communicate(
            self,
            timeout: float,
        ) -> tuple[bytes, bytes]:
            raise subprocess.TimeoutExpired(
                "communicate",
                timeout,
                output=b"late-out",
                stderr=b"late-err",
            )

    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(
        route.os,
        "killpg",
        lambda pgid, sig: signals.append((pgid, sig)),
    )
    process = Process()
    stdout, stderr, cleanup = route._terminate_process_group(
        process,  # type: ignore[arg-type]
        initial_stdout=b"early-out",
        initial_stderr=b"early-err",
        terminate_wait_seconds=0.01,
        kill_wait_seconds=0.01,
        drain_wait_seconds=0.01,
    )
    assert signals == [
        (43210, route.signal.SIGTERM),
        (43210, route.signal.SIGKILL),
    ]
    assert stdout == b"early-outlate-out"
    assert stderr == b"early-errlate-err"
    assert cleanup["terminate_wait_timed_out"] is True
    assert cleanup["kill_wait_timed_out"] is True
    assert cleanup["pipe_drain_timed_out"] is True
    assert cleanup["pipes_forcibly_closed"] is True
    assert process.stdout.closed is True
    assert process.stderr.closed is True


def test_invoke_records_provenance_capture_failure_and_session_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class Pipe:
        def close(self) -> None:
            return None

    class Process:
        pid = 54321
        returncode = None
        stdin = Pipe()
        stdout = Pipe()
        stderr = Pipe()

        def wait(self, timeout: float) -> int:
            self.returncode = -15
            return self.returncode

        def communicate(
            self,
            timeout: float,
        ) -> tuple[bytes, bytes]:
            return b"partial-stdout", b"partial-stderr"

        def poll(self) -> int | None:
            return self.returncode

    popen_kwargs: dict[str, object] = {}

    def fake_popen(
        command: list[str],
        **kwargs: object,
    ) -> Process:
        popen_kwargs.update(kwargs)
        return Process()

    monkeypatch.setattr(route.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(route.os, "killpg", lambda _pgid, _sig: None)
    monkeypatch.setattr(
        route,
        "observe_tcodex_binding",
        lambda **_kwargs: (_ for _ in ()).throw(
            route.ExternalGatewayError("TCODEX_CHILD_ARGV_NOT_OBSERVED")
        ),
    )
    value = registry()
    record = route.invoke_tcodex(
        packet=route.public_smoke_packets()[0],
        factor_name="action_choice",
        attempt_index=1,
        prompt="public fictional prompt",
        binding=_binding(),
        registry=value,
        run_dir=tmp_path / "run",
        timeout_seconds=1,
    )
    assert popen_kwargs["start_new_session"] is True
    assert record["gateway_success"] is False
    assert record["model_output_accepted"] is False
    assert record["transport_failure"] is True
    assert record["transport_error_code"] == (
        "TCODEX_CHILD_ARGV_NOT_OBSERVED"
    )
    assert record["stdout"] == "partial-stdout"
    assert "partial-stderr" in record["stderr"]
    assert record["provenance_artifacts"]["catalog"]["exists"] is False
    assert record["provenance_artifacts"]["child_argv"]["exists"] is False


def test_run_smoke_emits_repair_report_and_manifest_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binding = _binding()
    monkeypatch.setattr(route, "runtime_binding", lambda *_args: binding)

    def timeout_attempt(**kwargs: object) -> dict:
        packet = kwargs["packet"]
        assert isinstance(packet, dict)
        prompt = str(kwargs["prompt"]).encode()
        return route._attempt_record(
            packet=packet,
            factor_name=str(kwargs["factor_name"]),
            attempt_index=int(kwargs["attempt_index"]),
            command=["tcodex", "--", "exec"],
            prompt=prompt,
            raw_output=b"",
            stdout=b"partial stdout",
            stderr=b"partial stderr\nTCODEX_TIMEOUT\n",
            returncode=124,
            elapsed_seconds=600.0,
            binding=binding,
            transport_error_code="TCODEX_TIMEOUT",
            cleanup={
                "terminate_group_sent": True,
                "kill_group_sent": True,
                "pipe_drain_timed_out": True,
            },
        )

    monkeypatch.setattr(route, "invoke_tcodex", timeout_attempt)
    report = route.run_smoke(
        root=ROOT,
        registry=registry(),
        model_slug="gpt-6-astra",
        output_dir=tmp_path,
        timeout_seconds=1,
    )
    run_dir = tmp_path / report["run_id"]
    assert report["decision_token"] == route.REPAIR
    assert report["competence_claimed"] is False
    assert report["summary"]["transport_failures"] == 1
    assert report["summary"]["initial_attempts"] == 1
    assert report["summary"]["canonical_outputs"] == 0
    assert report["execution"]["transport_failures_are_model_outputs"] is False
    first_factor = report["cases"][0]["factors"]["action_choice"]
    assert first_factor["status"] == "TRANSPORT_FAILURE"
    assert first_factor["error_code"] == "TCODEX_TIMEOUT"
    assert report["cases"][1]["projection_status"] == "NOT_COMPUTED"
    assert (run_dir / "run_report.json").is_file()
    assert (run_dir / "raw_attempts.json").is_file()
    assert (run_dir / "manifest.json").is_file()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["decision_token"] == route.REPAIR
    attempts = json.loads((run_dir / "raw_attempts.json").read_text())
    assert attempts["attempts"][0]["transport_error_code"] == "TCODEX_TIMEOUT"
    assert attempts["attempts"][0]["model_output_accepted"] is False


def test_delivered_smoke_is_two_case_noncompetence_run() -> None:
    value = registry()
    report = route.validate_delivered_smoke(ROOT, value)
    assert report["decision_token"] in {route.READY, route.REPAIR}
    assert report["case_count"] == 2
    assert report["competence_claimed"] is False
    assert report["sealed_holdout_accessed"] is False
    assert report["execution"]["semantic_retries"] == 0
    assert report["execution"]["model_fallback_or_substitution"] is False
