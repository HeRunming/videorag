from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_epic_family_candidates.py"
VERIFY_SCRIPT = ROOT / "scripts/verify_epic_family_candidates.py"


def _module():
    spec = importlib.util.spec_from_file_location("epic_family_cli", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_show_plan_does_not_read_active_index(monkeypatch, capsys):
    module = _module()

    def forbidden(*args, **kwargs):
        raise AssertionError("show-plan must not read the active index")

    monkeypatch.setattr(
        "av_trace_epic_family_mining.load_canonical_epic_index", forbidden
    )
    assert module.main(["--repo-root", str(ROOT), "--show-plan"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan_kind"] == "IMPLEMENTATION_REHEARSAL_NOT_EXECUTED"
    assert payload["execution_status"]["mining_executed_by_task165"] is False


def test_incomplete_index_fails_closed_without_output(tmp_path, capsys):
    module = _module()
    plan = tmp_path / "data/rehearsal_plan/epic_family_mining_v1.json"
    plan.parent.mkdir(parents=True)
    from av_trace_epic_family_mining import build_rehearsal_plan

    plan.write_text(json.dumps(build_rehearsal_plan()))
    code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--plan",
            plan.relative_to(tmp_path).as_posix(),
            "--development-only",
            "--output",
            "data/restricted/epic_family_candidates_v1/candidates.json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["candidate_generation_executed"] is False
    assert "EPIC_CANONICAL_INDEX_INCOMPLETE_MISSING" in payload["error"]
    assert not (
        tmp_path
        / "data/restricted/epic_family_candidates_v1/candidates.json"
    ).exists()


def test_verifier_rejects_missing_registry(tmp_path):
    module = _module_for(VERIFY_SCRIPT, "epic_family_verifier")
    result = module.verify_registry(
        tmp_path,
        "data/restricted/epic_family_candidates_v1/missing.json",
    )
    assert result["verified"] is False
    assert result["decision"] == "EPIC_FAMILY_MINING_REPAIR"


def test_verifier_accepts_valid_restricted_registry(tmp_path):
    module = _module_for(VERIFY_SCRIPT, "epic_family_verifier_valid")
    from tests_epic_family_mining.test_mining_and_authoring import (
        fixture_registry,
    )

    path = (
        tmp_path
        / "data/restricted/epic_family_candidates_v1_dev/candidate_registry.json"
    )
    path.parent.mkdir(parents=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(fixture_registry(mode="development_only")))
    path.chmod(0o600)
    result = module.verify_registry(
        tmp_path,
        path.relative_to(tmp_path).as_posix(),
    )
    assert result["verified"] is True
    assert result["decision"] == "EPIC_FAMILY_MINING_IMPLEMENTATION_READY"


def test_verifier_rejects_development_registry_under_normal_root(tmp_path):
    module = _module_for(VERIFY_SCRIPT, "epic_family_verifier_root_mismatch")
    from tests_epic_family_mining.test_mining_and_authoring import (
        fixture_registry,
    )

    path = (
        tmp_path
        / "data/restricted/epic_family_candidates_v1/candidate_registry.json"
    )
    path.parent.mkdir(parents=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(fixture_registry(mode="development_only")))
    path.chmod(0o600)
    result = module.verify_registry(
        tmp_path,
        path.relative_to(tmp_path).as_posix(),
    )
    assert result["verified"] is False
    assert result["decision"] == "EPIC_FAMILY_MINING_REPAIR"
    assert result["failures"] == [
        (
            "REGISTRY_MODE_OUTPUT_ROOT_MISMATCH:"
            "development_only:data/restricted/epic_family_candidates_v1"
        )
    ]


def test_output_validation_is_mode_specific(tmp_path):
    module = _module()
    dev = (
        tmp_path
        / "data/restricted/epic_family_candidates_v1_dev/candidate_registry.json"
    )
    normal = (
        tmp_path
        / "data/restricted/epic_family_candidates_v1/candidate_registry.json"
    )
    module._validate_output(tmp_path, dev, mode="development_only")
    module._validate_output(tmp_path, normal, mode="gate_a_candidate_input")
    for output, mode in (
        (normal, "development_only"),
        (dev, "gate_a_candidate_input"),
    ):
        try:
            module._validate_output(tmp_path, output, mode=mode)
        except ValueError as exc:
            assert (
                "OUTPUT_MUST_BE_UNDER_MODE_SPECIFIC_RESTRICTED_"
                "EPIC_CANDIDATE_ROOT"
            ) in str(exc)
        else:
            raise AssertionError("mode/output-root mismatch must fail")


def _module_for(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
