from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_mini_pilot_family_candidates.py"


def _module():
    spec = importlib.util.spec_from_file_location("family_candidate_cli", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dry_run_does_not_load_real_indexes(monkeypatch, capsys):
    module = _module()

    def forbidden(*args, **kwargs):
        raise AssertionError("dry run must not read canonical indexes")

    monkeypatch.setattr(
        "av_trace_mini_pilot_families.load_mining_inputs", forbidden
    )
    assert module.main(["--repo-root", str(ROOT), "--dry-run"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["registry_kind"] == "DETERMINISTIC_DRY_RUN_FIXTURE"
    assert payload["summary"]["real_index_access_count"] == 0


def test_default_runner_preflights_current_complete_canonical_index(capsys):
    module = _module()
    assert module.main(["--repo-root", str(ROOT)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "READY"
    assert payload["canonical_index_complete"] is True
    assert payload["candidate_generation_executed"] is False
