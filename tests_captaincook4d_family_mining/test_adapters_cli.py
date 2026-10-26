from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from av_trace_captaincook4d_family_mining import (
    CaptainCook4DFamilyInputError,
    load_canonical_captaincook4d_index,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_captaincook4d_family_candidates.py"
VERIFY_SCRIPT = ROOT / "scripts/verify_captaincook4d_family_candidates.py"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_show_plan_does_not_read_task189(monkeypatch, capsys):
    module = _module(SCRIPT, "cc4d_family_cli")

    def forbidden(*args, **kwargs):
        raise AssertionError("show-plan must not read Task189")

    monkeypatch.setattr(
        "av_trace_captaincook4d_family_mining."
        "load_canonical_captaincook4d_index",
        forbidden,
    )
    assert module.main(["--repo-root", str(ROOT), "--show-plan"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan_kind"] == "IMPLEMENTATION_REHEARSAL_NOT_EXECUTED"
    assert payload["execution_status"]["mining_executed_by_task190"] is False


def test_missing_task189_ready_result_fails_before_index_read(tmp_path):
    with pytest.raises(
        CaptainCook4DFamilyInputError, match="TASK189_READY_RESULT_MISSING"
    ):
        load_canonical_captaincook4d_index(tmp_path)


def test_ready_token_without_index_still_fails_closed(tmp_path):
    result = (
        tmp_path
        / "orchestration/results/"
        "189_captaincook4d_wave0_full_timeline.txt"
    )
    result.parent.mkdir(parents=True)
    result.write_text(
        "FINAL\nCAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY\n",
        encoding="utf-8",
    )
    with pytest.raises(
        CaptainCook4DFamilyInputError,
        match="CAPTAINCOOK4D_CANONICAL_INDEX_INCOMPLETE_MISSING",
    ):
        load_canonical_captaincook4d_index(tmp_path)


def test_verifier_accepts_valid_development_registry(tmp_path):
    from tests_captaincook4d_family_mining.test_mining_authoring import (
        fixture_registry,
    )

    module = _module(VERIFY_SCRIPT, "cc4d_family_verifier")
    path = (
        tmp_path
        / "data/restricted/captaincook4d_family_candidates_v1_dev/"
        "candidate_registry.json"
    )
    path.parent.mkdir(parents=True)
    path.parent.chmod(0o700)
    path.write_text(
        json.dumps(fixture_registry(tmp_path, mode="development_only")),
        encoding="utf-8",
    )
    path.chmod(0o600)
    result = module.verify_registry(
        tmp_path, path.relative_to(tmp_path).as_posix()
    )
    assert result["verified"] is True
    assert (
        result["decision"]
        == "CAPTAINCOOK4D_FAMILY_MINING_IMPLEMENTATION_READY"
    )
