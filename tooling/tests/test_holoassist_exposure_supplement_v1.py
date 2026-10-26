from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/holoassist_exposure_supplement_v1.py"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "holoassist_exposure_supplement_v1", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_outputs_have_no_private_identity_or_path_leak() -> None:
    tool = load_tool()
    private = json.loads(tool.PRIVATE_UNIVERSE.read_text(encoding="utf-8"))
    public_bytes = tool.OUTPUT.read_bytes()
    review_bytes = tool.REVIEW.read_bytes()
    identities = {
        group["recording_root"] for group in private["selected_groups"]
    }
    identities.update(private["policy"]["explicit_exclusions"])
    identities.update(private["policy"]["semantic_text_exclusions"])
    for identity in identities:
        pattern = re.compile(
            rb"(?<![A-Za-z0-9])"
            + re.escape(identity.encode("ascii"))
            + rb"(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        assert pattern.search(public_bytes) is None
        assert pattern.search(review_bytes) is None
    for token in (
        b"extracted_videos/",
        b"VideoMp4Timing.txt",
        b"Pose_sync.txt",
        b"recording_root",
        b"timing_path",
    ):
        assert token not in public_bytes
        assert token not in review_bytes


def test_all_six_commitments_are_conditional_and_timing_closed() -> None:
    tool = load_tool()
    report = json.loads(tool.OUTPUT.read_text(encoding="utf-8"))
    commitment = json.loads(tool.PUBLIC_COMMITMENT.read_text(encoding="utf-8"))
    groups = report["exposure_classes"]["sealed_selected_groups"]["groups"]
    assert len(groups) == 6
    assert {group["commitment"] for group in groups} == set(
        commitment["commitments"]
    )
    assert all(
        group["classification"] == "CONDITIONAL_METADATA_ONLY"
        for group in groups
    )
    assert all(group["conditions"]["timing_closed"] for group in groups)
    assert all(
        group["conditions"]["absent_from_official_readme_example_set"]
        for group in groups
    )
    assert all(
        group["conditions"]["absent_from_frozen_repository_history_v2"]
        for group in groups
    )
    assert report["timing_evidence_totals"]["timing_closed_group_count"] == 6
    assert report["timing_evidence_totals"]["timing_text_file_count"] == 41


def test_official_examples_are_permanent_exclusions() -> None:
    tool = load_tool()
    report = json.loads(tool.OUTPUT.read_text(encoding="utf-8"))
    private = json.loads(tool.PRIVATE_UNIVERSE.read_text(encoding="utf-8"))
    examples = set(private["policy"]["explicit_exclusions"])
    examples.update(private["policy"]["semantic_text_exclusions"])
    selected = {
        group["recording_root"] for group in private["selected_groups"]
    }
    exposure = report["exposure_classes"]["official_readme_semantic_examples"]
    assert len(examples) == 4
    assert not (examples & selected)
    assert exposure["classification"] == "PERMANENTLY_CONTAMINATED"
    assert exposure["identity_count"] == 4
    assert exposure["selected_intersection_count"] == 0
    assert exposure["identity_set_sha256"] == hashlib.sha256(
        tool.canonical_json(sorted(examples))
    ).hexdigest()


def test_frozen_repository_history_and_bound_hashes() -> None:
    tool = load_tool()
    report = json.loads(tool.OUTPUT.read_text(encoding="utf-8"))
    history = report["repository_history_check"]
    assert history["selected_identity_exact_token_hits"] == 0
    assert history["result"] == "ALL_SIX_ABSENT"
    assert history["pinned_file_count"] == 2143
    for value in report["source_bindings"].values():
        path = ROOT / value["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == value["sha256"]
    assert report["hugging_face_metadata_evidence"]["revision"] == tool.HF_REVISION
    assert report["license_discrepancy"]["mirror_declared_license"] == "Apache-2.0"
    assert (
        report["license_discrepancy"]["official_declared_license"]
        == "CDLA-Permissive-2.0"
    )


def test_no_semantic_or_media_access_contract() -> None:
    tool = load_tool()
    report = json.loads(tool.OUTPUT.read_text(encoding="utf-8"))
    scope = report["scope"]
    assert scope["network_used"] is False
    assert scope["media_opened"] is False
    assert scope["video_opened"] is False
    assert scope["audio_opened"] is False
    assert scope["annotations_opened"] is False
    assert scope["labels_opened"] is False
    assert scope["semantic_dataset_fields_opened"] is False
    boundary = report["claim_boundary"]
    assert boundary["video_content_access_claim"] is False
    assert boundary["audio_content_access_claim"] is False
    assert boundary["native_audio_presence_claim"] is False

    source = TOOL_PATH.read_text(encoding="utf-8")
    for forbidden_lookup in (
        'get("task',
        'get("title',
        'get("description',
        'get("transcript',
        'get("label',
        '["task',
        '["title',
        '["description',
        '["transcript',
        '["label',
    ):
        assert forbidden_lookup not in source


def test_integrity_and_generation_are_deterministic(tmp_path: Path) -> None:
    tool = load_tool()
    first = tool.build_supplement()
    second = tool.build_supplement()
    assert tool.canonical_json(first) == tool.canonical_json(second)
    integrity = dict(first["integrity"])
    payload = dict(first)
    del payload["integrity"]
    assert integrity["canonical_payload_sha256"] == hashlib.sha256(
        tool.canonical_json(payload)
    ).hexdigest()
    assert tool.canonical_json(first) == tool.OUTPUT.read_bytes()
    assert tool.render_review(first) == tool.REVIEW.read_text(encoding="utf-8")

    out = tmp_path / "supplement.json"
    review = tmp_path / "supplement.md"
    run = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--skip-retained-evidence-verification",
            "--output",
            str(out),
            "--review",
            str(review),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.strip() == tool.FINAL_MARKER
    assert out.read_bytes() == tool.OUTPUT.read_bytes()
    assert review.read_bytes() == tool.REVIEW.read_bytes()
