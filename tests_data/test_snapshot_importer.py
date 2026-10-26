from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from av_trace_data.errors import SnapshotImportError
from av_trace_data.snapshot_importer import SnapshotImporter, SnapshotInput

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests_data" / "fixtures"
SNAPSHOTS = ROOT / "data" / "hf_recon" / "snapshots"
PYTHON = sys.executable
REVISION = "0123456789abcdef0123456789abcdef01234567"


class SnapshotImporterTests(unittest.TestCase):
    def test_hf_api_and_generic_jsonl_preserve_source_bytes_and_unknowns(self) -> None:
        api = FIXTURES / "snapshot_import_hf_api.json"
        rows = FIXTURES / "snapshot_import_unknown_modality.jsonl"
        artifact = SnapshotImporter().build(
            [
                api,
                SnapshotInput(
                    rows,
                    provider="huggingface",
                    repository_id="example/metadata-release",
                    repository_revision=REVISION,
                    repository_path="records.jsonl",
                    source_family="generic_metadata",
                ),
            ]
        )
        source = next(
            item
            for item in artifact["source_files"]
            if item["local_name"] == rows.name
        )
        self.assertEqual(source["byte_size"], len(rows.read_bytes()))
        self.assertEqual(
            source["sha256"],
            "sha256:" + hashlib.sha256(rows.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            source["repository_revision"],
            {
                "scope": "repository",
                "kind": "git_commit",
                "value": REVISION,
                "immutable": True,
            },
        )
        self.assertEqual(source["blob_revision"]["scope"], "blob")
        self.assertEqual(
            source["blob_revision"]["value"],
            "89abcdef0123456789abcdef0123456789abcdef",
        )
        self.assertIsNone(source["file_revision"])
        record = next(
            item
            for item in artifact["records"]
            if item["record_type"] == "metadata_row"
        )
        self.assertEqual(record["media"]["declared_modalities"], ["sensor_fusion"])
        self.assertIsNone(record["media"]["video"])
        self.assertIsNone(record["media"]["audio"])
        self.assertEqual(record["license"]["state"], "unknown")
        self.assertEqual(record["identity"]["status"], "unknown")
        self.assertEqual(artifact["acquisition_authorization"], "none")
        self.assertFalse(artifact["contains_media"])
        self.assertFalse(artifact["network_access_performed"])
        self.assertNotIn("manifest", artifact)

        repository = artifact["repositories"][0]
        self.assertEqual(repository["license_state"], "observed")
        self.assertEqual(repository["media_rights_state"], "unknown")
        evidence = artifact["license_evidence"][0]
        self.assertFalse(evidence["rights_inference"])

    def test_real_hf_snapshot_and_longvidsearch_rows_join_to_parent(self) -> None:
        artifact = SnapshotImporter().build(
            [
                SNAPSHOTS / "hf_api_Fishiing_LongVidSearch.json",
                SNAPSHOTS / "hf_Fishiing_LongVidSearch_full-QA_3000.json",
            ]
        )
        self.assertEqual(artifact["summary"]["record_count"], 3001)
        self.assertEqual(artifact["summary"]["lineage_join_count"], 3000)
        source = next(
            item
            for item in artifact["source_files"]
            if item["local_name"].endswith("full-QA_3000.json")
        )
        self.assertEqual(
            source["repository_revision"]["value"],
            "96cdf541ad916fe3e401ad7d1e387f660dd3336f",
        )
        join = artifact["source_lineage_joins"][0]
        self.assertEqual(join["relation"], "annotates")
        self.assertEqual(join["to_identity"]["namespace"], "longvideobench")

    def test_real_github_commit_tree_and_qa_preserve_revision_scopes(self) -> None:
        artifact = SnapshotImporter().build(
            [
                SNAPSHOTS / "github_api_yrywill_LongVidSearch_commit_main.json",
                SNAPSHOTS / "github_api_yrywill_LongVidSearch_tree_4aa5620.json",
                SNAPSHOTS
                / "github_yrywill_LongVidSearch_-7wwfGJXEZg_qa_4aa5620.json",
            ]
        )
        qa_source = next(
            item
            for item in artifact["source_files"]
            if item["local_name"].startswith("github_yrywill")
        )
        self.assertEqual(
            qa_source["repository_revision"]["value"],
            "4aa5620e06ca1bc5cc7cfce2b3e3ed0a5ae82d4e",
        )
        self.assertEqual(
            qa_source["blob_revision"]["value"],
            "995e96f2dd5b9419de0d385ad998c7d4cd80262c",
        )
        self.assertEqual(qa_source["blob_revision"]["scope"], "blob")
        self.assertIsNone(qa_source["file_revision"])

    def test_traceav_source_lineage_join_is_materialized(self) -> None:
        artifact = SnapshotImporter().build(
            [
                SnapshotInput(
                    FIXTURES / "snapshot_import_trace_mapping.jsonl",
                    provider="huggingface",
                    repository_id="Heinz217/TraceAV-Bench",
                    repository_revision=REVISION,
                    repository_path="data/video_name_mapping.jsonl",
                    source_family="traceav",
                ),
                SnapshotInput(
                    FIXTURES / "snapshot_import_trace_task.jsonl",
                    provider="huggingface",
                    repository_id="Heinz217/TraceAV-Bench",
                    repository_revision=REVISION,
                    repository_path="data/a_background_music.jsonl",
                    source_family="traceav",
                ),
            ]
        )
        joined = [
            item
            for item in artifact["source_lineage_joins"]
            if item["relation"] == "annotates_mapped_source"
        ]
        self.assertEqual(len(joined), 1)
        self.assertEqual(
            joined[0]["to_identity"],
            {"namespace": "lvbench", "asset_id": "upstream-1"},
        )
        task = next(
            item
            for item in artifact["records"]
            if item["record_type"] == "task_annotation"
        )
        self.assertEqual(task["media"]["declared_modalities"], ["audio"])
        self.assertIsNone(task["media"]["audio"])

    def test_csv_is_supported_and_unknown_modality_is_not_promoted_to_fact(self) -> None:
        artifact = SnapshotImporter().build(
            [
                SnapshotInput(
                    FIXTURES / "snapshot_import_rows.csv",
                    provider="local",
                    repository_id="example/csv",
                    repository_revision=REVISION,
                    source_family="generic_metadata",
                )
            ]
        )
        record = artifact["records"][0]
        self.assertEqual(
            record["media"]["declared_modalities"], ["unknown_future_modality"]
        )
        self.assertIsNone(record["media"]["video"])
        self.assertIsNone(record["media"]["audio"])

    def test_parquet_is_supported_only_through_installed_pyarrow(self) -> None:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest("PyArrow is not installed")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "metadata.parquet"
            pq.write_table(
                pa.table({"id": ["pq-1"], "modality": ["not_known"]}),
                path,
            )
            artifact = SnapshotImporter().build(
                [
                    SnapshotInput(
                        path,
                        provider="local",
                        repository_id="example/parquet",
                        repository_revision=REVISION,
                        source_family="generic_metadata",
                    )
                ]
            )
            self.assertEqual(artifact["summary"]["record_count"], 1)
            self.assertEqual(artifact["source_files"][0]["format"], "parquet")

    def test_malformed_schema_duplicate_ids_and_embedded_media_fail_closed(self) -> None:
        cases = [
            (
                SnapshotInput(
                    FIXTURES / "snapshot_import_malformed_longvidsearch.json",
                    provider="local",
                    repository_id="example/longvidsearch",
                    repository_revision=REVISION,
                    source_family="longvidsearch",
                ),
                "missing required fields",
            ),
            (
                SnapshotInput(
                    FIXTURES / "snapshot_import_duplicate_ids.jsonl",
                    provider="local",
                    repository_id="example/generic",
                    repository_revision=REVISION,
                    source_family="generic_metadata",
                ),
                "duplicate metadata ID",
            ),
            (
                SnapshotInput(
                    FIXTURES / "snapshot_import_embedded_media.jsonl",
                    provider="local",
                    repository_id="example/generic",
                    repository_revision=REVISION,
                    source_family="generic_metadata",
                ),
                "embedded media data URI",
            ),
        ]
        for spec, message in cases:
            with self.subTest(path=Path(spec.path).name):
                with self.assertRaisesRegex(SnapshotImportError, message):
                    SnapshotImporter().build([spec])

    def test_oversized_and_payload_class_inputs_are_rejected_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * 33)
            with self.assertRaisesRegex(SnapshotImportError, "configured cap"):
                SnapshotImporter(max_file_bytes=32).build(
                    [
                        SnapshotInput(
                            oversized,
                            provider="local",
                            repository_id="example/oversized",
                            repository_revision=REVISION,
                        )
                    ]
                )
            media = root / "payload.mp4"
            media.write_bytes(b"\x00\x00\x00\x18ftypisom")
            with self.assertRaisesRegex(SnapshotImportError, "media payload"):
                SnapshotImporter().build([media])

    def test_binary_signature_and_base64_media_field_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            disguised = root / "disguised.json"
            disguised.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 16)
            with self.assertRaisesRegex(SnapshotImportError, "PNG image"):
                SnapshotImporter().build([disguised], promote=False)

            encoded = root / "encoded.jsonl"
            encoded.write_text(
                json.dumps(
                    {
                        "id": "encoded",
                        "image": (
                            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
                            + "A" * 480
                        ),
                    }
                )
                + "\n"
            )
            with self.assertRaisesRegex(SnapshotImportError, "base64-embedded"):
                SnapshotImporter().build(
                    [
                        SnapshotInput(
                            encoded,
                            provider="local",
                            repository_id="example/generic",
                            repository_revision=REVISION,
                            source_family="generic_metadata",
                        )
                    ]
                )

    def test_short_or_mutable_revision_is_rejected_for_promotion(self) -> None:
        for revision in ("main", "0123456"):
            with self.subTest(revision=revision):
                with self.assertRaisesRegex(SnapshotImportError, "cannot be promoted"):
                    SnapshotImporter().build(
                        [
                            SnapshotInput(
                                FIXTURES / "snapshot_import_rows.csv",
                                provider="local",
                                repository_id="example/csv",
                                repository_revision=revision,
                                source_family="generic_metadata",
                            )
                        ]
                    )
        artifact = SnapshotImporter().build(
            [
                SnapshotInput(
                    FIXTURES / "snapshot_import_rows.csv",
                    provider="local",
                    repository_id="example/csv",
                    repository_revision="main",
                    source_family="generic_metadata",
                )
            ],
            promote=False,
        )
        self.assertEqual(artifact["promotion_status"], "unpromoted")
        self.assertFalse(artifact["source_files"][0]["promotion"]["eligible"])

    def test_importer_never_calls_network_apis(self) -> None:
        with mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("network attempted")
        ), mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("network attempted")
        ):
            artifact = SnapshotImporter().build(
                [
                    SnapshotInput(
                        FIXTURES / "snapshot_import_rows.csv",
                        provider="local",
                        repository_id="example/csv",
                        repository_revision=REVISION,
                        source_family="generic_metadata",
                    )
                ]
            )
        self.assertFalse(artifact["network_access_performed"])

    def test_cli_writes_only_inspection_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "inspection.json"
            result = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts" / "import_metadata_snapshots.py"),
                    str(FIXTURES / "snapshot_import_rows.csv"),
                    "--output",
                    str(output),
                    "--provider",
                    "local",
                    "--repository-id",
                    "example/csv",
                    "--repository-revision",
                    REVISION,
                    "--source-family",
                    "generic_metadata",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            artifact = json.loads(output.read_text())
            self.assertEqual(
                artifact["artifact_class"], "metadata_reconnaissance_inspection"
            )
            self.assertEqual(artifact["acquisition_authorization"], "none")
            self.assertEqual(sorted(path.name for path in root.iterdir()), [output.name])

    def test_cli_rejects_url_inputs_without_opening_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "inspection.json"
            result = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts" / "import_metadata_snapshots.py"),
                    "https://example.invalid/data.json",
                    "--output",
                    str(output),
                    "--allow-unpromoted",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("URL rejected", result.stdout)
            self.assertFalse(output.exists())

    def test_selection_cli_requires_explicit_reviewed_candidate_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inspection = root / "reconnaissance.json"
            artifact = SnapshotImporter().build(
                [
                    SnapshotInput(
                        FIXTURES / "snapshot_import_rows.csv",
                        provider="local",
                        repository_id="example/csv",
                        repository_revision=REVISION,
                        source_family="generic_metadata",
                    )
                ]
            )
            # Even an injected candidates key must not make raw importer output
            # look like a reviewed NormalizedCandidate inspection.
            artifact["candidates"] = []
            inspection.write_text(json.dumps(artifact))
            selection = root / "selection.json"
            result = subprocess.run(
                [
                    PYTHON,
                    str(ROOT / "scripts" / "select_rehearsal_candidates.py"),
                    str(inspection),
                    "--output",
                    str(selection),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("explicit reviewed conversion", result.stdout)
            self.assertFalse(selection.exists())


if __name__ == "__main__":
    unittest.main()
