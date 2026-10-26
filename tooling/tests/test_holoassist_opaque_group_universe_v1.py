#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/holoassist_opaque_group_universe_v1.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("holoassist_opaque_v1", TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_commitment_has_no_recording_identity_or_path() -> None:
    tool = load_tool()
    public = json.loads(tool.PUBLIC_OUTPUT.read_text())
    raw = json.dumps(public, sort_keys=True)
    assert not re.search(
        r"(?<![A-Za-z0-9])R\d{3,}(?!\d)", raw, re.IGNORECASE
    )
    assert "extracted_videos/" not in raw
    assert "VideoMp4Timing" not in raw
    assert "Pose_sync" not in raw
    tool.validate_public_identity_absence(public)


def test_exclusions_and_group_closure_are_permanent() -> None:
    tool = load_tool()
    private = json.loads(tool.PRIVATE_OUTPUT.read_text())
    excluded = set(private["policy"]["explicit_exclusions"])
    excluded.update(private["policy"]["semantic_text_exclusions"])
    assert {"R007", "R012", "R013", "R014"} <= excluded
    assert not ({group["recording_root"] for group in private["selected_groups"]} & excluded)
    for group in private["selected_groups"]:
        assert all(v["timing_present"] and v["pose_present"] for v in group["variants"])


def test_commitments_are_deterministic() -> None:
    tool = load_tool()
    private1, public1 = tool.build_universe()
    private2, public2 = tool.build_universe()
    assert tool.canonical_json(private1) == tool.canonical_json(private2)
    assert tool.canonical_json(public1) == tool.canonical_json(public2)


def test_no_semantic_field_access_contract() -> None:
    tool = load_tool()
    private = json.loads(tool.PRIVATE_OUTPUT.read_text())
    assert private["policy"]["semantic_fields_accessed"] == []
    source = TOOL_PATH.read_text()
    assert "get(\"task" not in source
    assert "get(\"title" not in source
    assert "get(\"description" not in source
    assert "get(\"transcript" not in source
    assert "get(\"label" not in source


def test_timing_closure_matches_current_committed_state() -> None:
    tool = load_tool()
    private = json.loads(tool.PRIVATE_OUTPUT.read_text())
    public = json.loads(tool.PUBLIC_OUTPUT.read_text())
    assert public["counts"]["sealed_group_count"] >= 6
    assert public["counts"]["timing_closed_group_count"] == 6
    assert private["final_marker"] == tool.READY
    assert public["final_marker"] == tool.READY


def test_permissions_are_private() -> None:
    tool = load_tool()
    assert tool.PRIVATE_OUTPUT.stat().st_mode & 0o777 == 0o600
    assert tool.PUBLIC_OUTPUT.stat().st_mode & 0o777 == 0o600
