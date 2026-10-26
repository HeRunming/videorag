#!/usr/bin/env python3
"""Verify Task-198 freeze/run/evaluation seals and replay the evaluator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from av_trace_strong_baselines.competence import (
    evaluate_competence_submission,
    load_submission,
    load_suite,
)
from tools.qwen25_omni_direct_competence import (
    OUTPUT_DIR,
    SUITE,
    _verify_freeze,
    _verify_run_seal,
    sha256_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    output_dir = root / args.output_dir
    _suite, _, _, _ = _verify_freeze(root, output_dir)
    seal = _verify_run_seal(output_dir)
    stored = json.loads(
        (output_dir / "evaluator_report.json").read_text(encoding="utf-8")
    )
    replay = evaluate_competence_submission(
        load_suite(root / SUITE),
        load_submission(output_dir / "submission.json"),
    )
    if replay != stored:
        raise SystemExit("EVALUATOR_REPLAY_MISMATCH")
    evaluation_seal = json.loads(
        (output_dir / "evaluation_seal.json").read_text(encoding="utf-8")
    )
    for name, record in evaluation_seal["files"].items():
        path = output_dir / name
        if (
            sha256_file(path) != record["sha256"]
            or path.stat().st_size != record["bytes"]
        ):
            raise SystemExit(f"EVALUATION_FILE_MISMATCH:{name}")
    print(
        json.dumps(
            {
                "status": "QWEN25_OMNI_DIRECT_AUDIT_PASS",
                "run_id": seal["run_id"],
                "decision": replay["decision"],
                "gate_checks": replay["gate_checks"],
                "sealed_input_verified": True,
                "evaluator_replay_identical": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
