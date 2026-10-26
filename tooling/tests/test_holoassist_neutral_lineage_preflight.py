from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/holoassist_neutral_lineage_preflight.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "holoassist_neutral_lineage_preflight", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _closed_group(index: int) -> dict[str, object]:
    return {
        "group_id": f"opaque-group-{index:02d}",
        "participant_id": f"p-{index:02d}",
        "pair_id": f"pair-{index:02d}",
        "session_id": f"s-{index:02d}",
        "recording_id": f"r-{index:02d}",
        "file_id": f"f-{index:02d}",
        "rendition_id": f"rendition-{index:02d}",
        "bytes": 1000 + index,
        "hash_algorithm": "sha256",
        "hash": f"{index:064x}",
        "duration_seconds": 1200.0 + index,
        "audio_stream_count": 1,
        "audio_codec": "aac",
    }


def test_plan_is_fail_closed_and_has_zero_groups() -> None:
    tool = load_tool()
    report = tool.build_report(mode="plan-only")

    assert report["final_marker"] == tool.REPAIR
    assert report["eligible_universe"]["exact_group_count"] == 0
    assert report["eligible_universe"]["exact_session_count"] == 0
    assert report["eligible_universe"]["group_ids"] == []
    assert report["eligible_universe"]["semantic_yield"] is None
    assert report["scope"]["test_groups_selected"] == 0


def test_ready_requires_six_fully_closed_opaque_groups() -> None:
    tool = load_tool()
    groups = [_closed_group(index) for index in range(6)]
    marker, blockers = tool.classify(
        identity_established=True,
        license_established=True,
        access_mechanism_exact=True,
        groups=groups,
    )

    assert marker == tool.READY
    assert blockers == []

    groups[0]["audio_stream_count"] = 0
    marker, blockers = tool.classify(
        identity_established=True,
        license_established=True,
        access_mechanism_exact=True,
        groups=groups,
    )
    assert marker == tool.REPAIR
    assert any("Fewer than six" in blocker for blocker in blockers)


def test_semantic_group_fields_are_rejected() -> None:
    tool = load_tool()
    group = _closed_group(1)
    group["task_title"] = "must never be opened"

    with pytest.raises(
        tool.PreflightError, match="SEMANTIC_GROUP_FIELD_BLOCKED"
    ):
        tool.eligible_universe([group])


def test_nonofficial_and_semantic_urls_are_blocked() -> None:
    tool = load_tool()

    with pytest.raises(tool.PreflightError, match="NON_OFFICIAL_URL_BLOCKED"):
        tool.validate_official_url("https://example.com/manifest.json")
    with pytest.raises(tool.PreflightError, match="SEMANTIC_ENDPOINT_BLOCKED"):
        tool.validate_official_url(
            "https://holoassist.github.io/annotations.json"
        )


def test_github_parser_accepts_only_exact_official_repository() -> None:
    tool = load_tool()
    data = json.dumps(
        {
            "full_name": "holoAssist/holoassist.github.io",
            "default_branch": "main",
            "archived": False,
            "license": {"spdx_id": "CDLA-Permissive-2.0"},
        }
    ).encode()
    parsed = tool.parse_github_repository(data)
    assert parsed["full_name"] == "holoAssist/holoassist.github.io"
    assert parsed["license_spdx_id"] == "CDLA-Permissive-2.0"

    bad = data.replace(b"holoAssist", b"unofficial")
    with pytest.raises(tool.PreflightError, match="IDENTITY_MISMATCH"):
        tool.parse_github_repository(bad)


def test_stopped_ledger_is_zero_byte_and_records_user_stop() -> None:
    tool = load_tool()
    evidence = tool.stopped_live_evidence()

    assert evidence["user_stop_observed"] is True
    assert evidence["requests_after_stop"] == 0
    assert evidence["response_body_bytes_read"] == 0
    assert evidence["response_body_bytes_persisted"] == 0
    assert len(evidence["requests"]) == 8
    assert all(
        item["response_body_bytes"] == 0
        for item in evidence["requests"]
    )


def test_cli_stopped_finalization_is_deterministic_and_offline(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    command = [
        sys.executable,
        str(TOOL_PATH),
        "--live",
        "--stop-network",
    ]
    run1 = subprocess.run(
        [*command, "--output", str(first)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    run2 = subprocess.run(
        [*command, "--output", str(second)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert run1.returncode == 0, run1.stdout + run1.stderr
    assert run2.returncode == 0, run2.stdout + run2.stderr
    assert run1.stdout.strip() == load_tool().REPAIR
    assert first.read_bytes() == second.read_bytes()

    report = json.loads(first.read_text(encoding="utf-8"))
    assert report["mode"] == "live-stopped-finalization"
    assert report["technical_inventory"]["session_ids_obtained"] == 0
    assert report["technical_inventory"][
        "sessions_with_native_synchronized_audio_evidence"
    ] == 0
    assert report["technical_inventory"][
        "sessions_with_duration_evidence"
    ] == 0
