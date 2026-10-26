from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_mini_pilot_full_timeline.py"


def _module():
    spec = importlib.util.spec_from_file_location("mini_pilot_verifier", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_search_leakage_rejects_private_keys_but_allows_vocabulary_tokens():
    module = _module()
    safe = {
        "modalities": {
            "speech": {
                "documents": [
                    {
                        "segment_id": "s",
                        "tokens": ["question", "rights"],
                        "term_frequency": {"question": 1, "rights": 1},
                    }
                ]
            }
        }
    }
    assert module._check_search_leakage(safe) == []
    unsafe = {
        "modalities": {
            "speech": {"documents": [{"segment_id": "s", "family_id": "private"}]}
        }
    }
    assert module._check_search_leakage(unsafe) == [
        "index_leakage:speech[0].family_id"
    ]


def test_repo_relative_path_audit_rejects_absolute_and_parent_escape():
    module = _module()
    document = {
        "path": "/tmp/secret.json",
        "nested": [{"weights_path": "../escape.bin"}],
    }
    failures = module._check_repo_relative_paths(document, ROOT)
    assert len(failures) == 2
    assert all("path" in failure for failure in failures)


def test_smoke_expectations_follow_frozen_lattice():
    module = _module()

    class Source:
        def __init__(self, source_id: str, duration_seconds: float):
            self.source_id = source_id
            self.duration_seconds = duration_seconds

    class Plan:
        sources = (
            Source("one", 100.0),
            Source("two", 100.0),
            Source("three", 100.0),
            Source("four", 100.0),
        )

    per_source, segment, observation = module._smoke_expectations(Plan(), 8.0)
    assert per_source["one"] == {
        "duration_seconds": 8.0,
        "base_cells": 2,
        "fine_windows": 2,
        "context_windows": 0,
        "temporal_segments": 2,
        "whisper_chunks": 1,
    }
    assert segment == {
        "base_cells": 8,
        "fine_windows": 8,
        "context_windows": 0,
        "windows": 8,
        "maximum_modality_records": 24,
    }
    assert observation == {
        "routing_cells": 8,
        "clip_cells": 8,
        "vision_records": 8,
        "whisper_chunks": 4,
        "speech_records": 4,
        "ast_fine_calls": 8,
        "ambient_records": 8,
    }


def test_parser_exposes_explicit_smoke_verifier_mode():
    module = _module()
    args = module.build_parser().parse_args(["--smoke-seconds", "8"])
    assert args.smoke_seconds == 8.0


def test_missing_build_fails_closed(tmp_path: Path, monkeypatch):
    module = _module()

    class Plan:
        output_root = tmp_path / "output"

    monkeypatch.setattr(module, "load_source_plan", lambda *args, **kwargs: Plan())
    result = module.verify_index(tmp_path)
    assert result["verified"] is False
    assert result["decision"] == "MINI_PILOT_INDEX_NO_GO"
    assert any("missing" in failure for failure in result["failures"])


def test_downstream_and_media_artifact_names_are_detected(tmp_path: Path, monkeypatch):
    module = _module()
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    (output / "evaluation.json").write_text("{}")
    (output / "frame.png").write_bytes(b"not-a-real-image")

    class Plan:
        output_root = output

    monkeypatch.setattr(module, "load_source_plan", lambda *args, **kwargs: Plan())
    # Required files are absent, but the output-boundary helper itself must still
    # classify both prohibited artifact classes when used independently.
    media = []
    downstream = []
    for path in output.rglob("*"):
        if path.suffix.casefold() in module.MEDIA_SUFFIXES:
            media.append(path.name)
        if any(term in path.name.casefold() for term in module.DOWNSTREAM_TERMS):
            downstream.append(path.name)
    assert media == ["frame.png"]
    assert downstream == ["evaluation.json"]
