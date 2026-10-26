#!/usr/bin/env python3
"""Independent replay/component audit for the sealed Qwen3 holdout run."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts import audit_granite_adapter_v2_holdout_run as _base
from tools import qwen3_adapter_v2_holdout as runner

AUDIT_SCHEMA = "av-trace.qwen3-adapter-v2-independent-audit/1.0"
DEFAULT_RUN_DIR = Path(
    "data/restricted/strong_baselines/qwen3_v2_holdout_run"
)
AuditError = _base.AuditError
_load = _base._load
_sha256 = _base._sha256
_atomic_json = _base._atomic_json


def build_audit(root: Path, run_dir: Path) -> dict[str, Any]:
    """Replay the private evaluator once and independently audit components."""

    _base.runner = runner
    _base.AUDIT_SCHEMA = AUDIT_SCHEMA
    return _base.build_audit(root, run_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    audit = build_audit(root, run_dir)
    _atomic_json(run_dir / "component_audit.json", audit)
    pending = _load(run_dir / "evaluation_pending_audit.json")
    report = _load(run_dir / "evaluator_report.json")
    final_seal = {
        "schema_version": runner.EVALUATION_SEAL_SCHEMA,
        "task_id": runner.TASK_ID,
        "run_id": pending["run_id"],
        "evaluated_at": pending["evaluated_at"],
        "independently_audited_at": audit["audited_at"],
        "state": "EVALUATED_AND_INDEPENDENTLY_AUDITED",
        "sealed_input_verified": True,
        "input_seal_sha256": pending["input_seal_sha256"],
        "files": {
            name: {
                "sha256": _sha256(run_dir / name),
                "bytes": (run_dir / name).stat().st_size,
            }
            for name in ("evaluator_report.json", "component_audit.json")
        },
        "decision": report["decision"],
        "deterministic_replay_count_completed": 1,
        "independent_audit_status": audit["status"],
        "auditor_source": str(Path(__file__).relative_to(root)),
        "auditor_source_sha256": _sha256(Path(__file__)),
    }
    _atomic_json(run_dir / "evaluation_seal.json", final_seal)
    os.chmod(run_dir / "evaluator_report.json", 0o400)
    os.chmod(run_dir / "component_audit.json", 0o400)
    (run_dir / "evaluation_pending_audit.json").unlink()
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
