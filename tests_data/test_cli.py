from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class CLITests(unittest.TestCase):
    def run_cli(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, str(ROOT / "scripts" / script), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_inspect_and_select_create_no_media(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inspection = root / "inspection.json"
            selection = root / "selection.json"
            manifests = root / "manifests"
            audit = root / "audit.jsonl"
            result = self.run_cli(
                "inspect_dataset_release.py",
                "--adapter",
                "video_mme",
                "--fixture",
                str(ROOT / "tests_data/fixtures/hf_synthetic_av_snapshot.json"),
                "--output",
                str(inspection),
                "--audit-log",
                str(audit),
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            result = self.run_cli(
                "select_rehearsal_candidates.py",
                str(inspection),
                "--output",
                str(selection),
                "--manifest-dir",
                str(manifests),
                "--created-by",
                "cli_fixture",
                "--audit-log",
                str(audit),
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            inspection_data = json.loads(inspection.read_text())
            selection_data = json.loads(selection.read_text())
            self.assertEqual(
                list(selection_data["source_snapshots"].values()),
                [inspection_data["snapshot_sha256"]],
            )
            manifest_files = sorted(manifests.glob("*.json"))
            self.assertEqual(len(manifest_files), 1)
            manifest = json.loads(manifest_files[0].read_text())
            self.assertEqual(manifest["audit"]["gate_status"], "metadata_only")
            self.assertFalse(any(path.suffix in {".mp4", ".webm"} for path in root.rglob("*")))

    def test_execute_refuses_draft_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inspection = root / "inspection.json"
            selection = root / "selection.json"
            manifests = root / "manifests"
            plan = root / "plan.json"
            inspect_result = self.run_cli(
                "inspect_dataset_release.py",
                "--adapter",
                "video_mme",
                "--fixture",
                str(ROOT / "tests_data/fixtures/hf_synthetic_av_snapshot.json"),
                "--output",
                str(inspection),
            )
            self.assertEqual(inspect_result.returncode, 0)
            select_result = self.run_cli(
                "select_rehearsal_candidates.py",
                str(inspection),
                "--output",
                str(selection),
                "--manifest-dir",
                str(manifests),
            )
            self.assertEqual(select_result.returncode, 0)
            plan_result = self.run_cli(
                "plan_dataset_download.py",
                "plan",
                "--selection",
                str(selection),
                "--manifest-dir",
                str(manifests),
                "--output",
                str(plan),
                "--output-root",
                str(root / "media"),
                "--max-item-bytes",
                "10000",
                "--max-total-bytes",
                "10000",
            )
            self.assertEqual(plan_result.returncode, 0, plan_result.stdout)
            plan_data = json.loads(plan.read_text())
            approval = root / "approval.json"
            approval.write_text(
                json.dumps(
                    {
                        "approval_version": "1.0",
                        "action": "approve_download_execution",
                        "plan_sha256": plan_data["plan_sha256"],
                        "approved_by": "reviewer",
                        "approved_role": "acquisition_reviewer",
                        "approved_at": "2026-09-07T00:00:00Z",
                        "approved_asset_ids": [
                            item["asset_id"] for item in plan_data["items"]
                        ],
                        "attestation": (
                            "I approve acquisition of the exact assets in this frozen plan."
                        ),
                    }
                )
            )
            signers = root / "authorized-signers.json"
            signers.write_text(
                json.dumps({"reviewer": ["acquisition_reviewer"]})
            )
            execute_result = self.run_cli(
                "plan_dataset_download.py",
                "execute",
                "--selection",
                str(selection),
                "--manifest-dir",
                str(manifests),
                "--plan",
                str(plan),
                "--approval-file",
                str(approval),
                "--authorized-signers",
                str(signers),
                "--approved-staging-root",
                str(root / "media"),
            )
            self.assertEqual(execute_result.returncode, 1)
            self.assertIn("not exactly acquisition_approved", execute_result.stdout)
            self.assertFalse((root / "media").exists())


if __name__ == "__main__":
    unittest.main()
