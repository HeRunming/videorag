from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/noaa_targeted_family_mining_v5.py"
REGISTRY_PATH = (
    ROOT
    / "data/restricted/noaa_targeted_family_candidates_v5_dev/"
    "candidate_registry.json"
)


def load_tool():
    spec = importlib.util.spec_from_file_location("noaa_targeted_v5", TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_is_deterministic_and_matches_checked_in_registry() -> None:
    tool = load_tool()
    first = tool.build_registry()
    second = tool.build_registry()
    checked_in = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    assert tool.canonical_bytes(first) == tool.canonical_bytes(second)
    assert tool.canonical_bytes(first) == tool.canonical_bytes(checked_in)
    tool.validate_registry(checked_in)


def test_priority_order_statuses_and_honest_vsa_zero() -> None:
    tool = load_tool()
    registry = tool.build_registry()

    assert [item["source_id"] for item in registry["candidates"]] == [
        "cand-049",
        "cand-047",
        "cand-051",
        "cand-045",
        "cand-052",
    ]
    assert [item["provisional_status"] for item in registry["candidates"]] == [
        "REPAIR",
        "KEEP",
        "KEEP",
        "REJECT",
        "REJECT",
    ]
    assert registry["profile_accounting"]["V+S+A"] == {
        "keep": 0,
        "repair": 0,
        "validated_or_accepted": 0,
        "honest_zero": True,
        "reason": (
            "No local exact-source evidence establishes a concrete, temporally "
            "localizable, source-world non-speech event carrying a "
            "non-duplicative answer component."
        ),
        "recommendation": (
            "Use separately approved acquisition of audio-rich procedural "
            "sources, or prospectively narrow/remove V+S+A rather than forcing "
            "AST labels, music, surf, generic handling, or co-occurrence."
        ),
    }
    bound_paths = {item["path"] for item in registry["input_bindings"]}
    assert (
        "data/restricted/noaa01/scale1a/checkpoints/cand-047/speech.json"
        in bound_paths
    )
    assert (
        "data/restricted/noaa01/scale1a/checkpoints/cand-051/vision_clip.json"
        in bound_paths
    )
    assert (
        "data/restricted/noaa01/scale1a/checkpoints/cand-049/ambient.json"
        in bound_paths
    )
    assert (
        "data/restricted/noaa01/raw/05_archive_070620_sm.mp4.metadata.json"
        in bound_paths
    )


def test_far_candidates_are_multihop_coherent_and_above_threshold() -> None:
    tool = load_tool()
    registry = tool.build_registry()
    far = [
        item
        for item in registry["candidates"]
        if item["temporal_structure"]["temporal_hypothesis"] == "far_separated"
    ]

    assert len(far) == 3
    for item in far:
        temporal = item["temporal_structure"]
        assert temporal["hop_hypothesis"] == "multi_hop"
        assert temporal["evidence_center_separation_s"] >= 120.0
        assert temporal["threshold_passes"] is True
        assert temporal["coherence_hypothesis"]


def test_cand049_forbidden_surf_routes_are_explicitly_excluded() -> None:
    tool = load_tool()
    candidate = tool.build_registry()["candidates"][0]
    exclusions = {
        item["route_id"] for item in candidate["known_route_exclusions"]
    }

    assert "DEV-F09-SURF-AUDIO-PROPERTY" in exclusions
    assert "noaa01-r004-surf-av" in exclusions
    assert candidate["hypothesized_profile"]["modality_work"]["A"].startswith(
        "No answer-bearing"
    )


def test_validator_rejects_gate_a_or_vsa_invention() -> None:
    tool = load_tool()
    registry = tool.build_registry()

    bad_gate = copy.deepcopy(registry)
    bad_gate["candidates"][0]["gate_a_credit"] = True
    bad_gate["registry_payload_sha256"] = tool.object_hash(
        {
            key: value
            for key, value in bad_gate.items()
            if key != "registry_payload_sha256"
        }
    )
    with pytest.raises(tool.MiningError, match="Gate-A"):
        tool.validate_registry(bad_gate)

    bad_vsa = copy.deepcopy(registry)
    bad_vsa["profile_accounting"]["V+S+A"]["keep"] = 1
    bad_vsa["registry_payload_sha256"] = tool.object_hash(
        {
            key: value
            for key, value in bad_vsa.items()
            if key != "registry_payload_sha256"
        }
    )
    with pytest.raises(tool.MiningError, match="honest zero"):
        tool.validate_registry(bad_vsa)


def test_validator_rejects_unknown_exact_handle() -> None:
    tool = load_tool()
    registry = tool.build_registry()
    registry["candidates"][1]["evidence_handles"][0]["record_references"][0] = (
        "seg.unknown"
    )
    registry["candidates"][1]["candidate_payload_sha256"] = tool.object_hash(
        {
            key: value
            for key, value in registry["candidates"][1].items()
            if key != "candidate_payload_sha256"
        }
    )
    registry["registry_payload_sha256"] = tool.object_hash(
        {
            key: value
            for key, value in registry.items()
            if key != "registry_payload_sha256"
        }
    )

    with pytest.raises(tool.MiningError, match="unknown vision handle"):
        tool.validate_registry(registry)


def test_cli_check_mode_is_local_and_ready() -> None:
    completed = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "NOAA_TARGETED_FAMILY_MINING_V5_READY"
