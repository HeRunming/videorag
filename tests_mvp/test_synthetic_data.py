from __future__ import annotations

import json
from pathlib import Path

from av_trace import GateProfile, SchemaRegistry, validate_family, validate_manifest_gate
from av_trace_mvp.synthetic_data import generate_corpus, probe_mp4

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "mvp/config/synthetic_scenarios.json"


def test_quick_generation_is_playable_valid_and_deterministic(tmp_path: Path) -> None:
    first = generate_corpus(
        config_path=CONFIG,
        output_dir=tmp_path / "first",
        mode="quick",
        seed=17,
        repository_root=ROOT,
    )
    second = generate_corpus(
        config_path=CONFIG,
        output_dir=tmp_path / "second",
        mode="quick",
        seed=17,
        repository_root=ROOT,
    )
    assert (first.source_count, first.family_count, first.episode_count) == (1, 2, 6)
    assert first.metadata_sha256 == second.metadata_sha256
    # Byte identity is expected under the same local codec build, but the public
    # contract intentionally does not promise it across PyAV/FFmpeg versions.
    assert first.mp4_hashes == second.mp4_hashes
    media = first.output_dir / "media/syn_source_01.mp4"
    probe = probe_mp4(media)
    assert probe["has_video"] and probe["has_audio"]
    assert 239.0 <= probe["duration_s"] <= 241.0

    registry = SchemaRegistry(ROOT)
    manifest = json.loads((first.output_dir / "manifests/syn_source_01.json").read_text())
    assert manifest["dataset_id"] == "synthetic_project_owned"
    assert validate_manifest_gate(manifest, GateProfile.PUBLIC_RELEASE, registry).ok
    for family_path in sorted((first.output_dir / "families").glob("*.json")):
        family = json.loads(family_path.read_text())
        report = validate_family(
            family, manifest, registry, media_mode="synthetic_testing"
        )
        assert report.ok, report.to_dict()


def test_full_config_covers_mvp_design() -> None:
    config = json.loads(CONFIG.read_text())
    sources = config["sources"]
    families = [family for source in sources for family in source["families"]]
    events = {
        event["event_id"]: event
        for source in sources
        for event in source["events"]
    }
    assert len(sources) == 4
    assert all(240 <= source["duration_s"] <= 480 for source in sources)
    assert len(families) == 8
    assert len(families) * 3 == 24
    assert {family["mechanism"] for family in families} == {
        "necessity_group_withholding",
        "modality_channel_outage",
    }
    modalities = {
        events[event_id]["modality"]
        for family in families
        for event_id in family["evidence_event_ids"]
    }
    assert modalities == {"vision", "speech", "ambient"}
    cross_modal = [
        family
        for family in families
        if len({events[event_id]["modality"] for event_id in family["evidence_event_ids"]}) > 1
    ]
    assert len(cross_modal) >= 4
    assert len(cross_modal) == 4
    assert any(len(family["accepted_ses"]) > 1 for family in families)
    assert any(
        max(events[event_id]["start_s"] for event_id in route)
        - min(events[event_id]["start_s"] for event_id in route)
        >= 120
        for family in families
        for route in family["accepted_ses"]
        if len(route) >= 2
    )
