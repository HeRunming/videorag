from __future__ import annotations

import unittest
from pathlib import Path

from av_trace_data.adapters import adapter_for_config
from av_trace_data.configs import (
    PRIORITY_ADAPTERS,
    access_crosswalk,
    get_adapter_config,
)
from av_trace_data.errors import FixtureError

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests_data" / "fixtures"


class AdapterTests(unittest.TestCase):
    def test_lovr_schema_faithful_fixture_preserves_unknown_and_conflict(self) -> None:
        adapter = adapter_for_config(get_adapter_config("lovr"))
        result = adapter.inspect_fixture(FIXTURES / "hf_lovr_snapshot.json")
        self.assertEqual(result.inspection_version, "2.0")
        self.assertEqual(result.repository_id, "debugger123/LoVR-benchmark")
        self.assertEqual(len(result.configs), 1)
        self.assertEqual(len(result.files), 2)
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertIsNone(candidate.has_video)
        self.assertIsNone(candidate.has_audio)
        self.assertIsNone(candidate.has_speech)
        self.assertIsNone(candidate.has_ambient_audio)
        self.assertIsNone(candidate.media_url)
        self.assertFalse(candidate.transcript_available)
        self.assertEqual(candidate.identity_resolution_status, "unresolved")
        self.assertIsNone(candidate.upstream_id)
        self.assertEqual(candidate.license_resolution_status, "conflicting")
        self.assertEqual(len(candidate.license_evidence), 2)
        self.assertIsNone(candidate.license)
        self.assertTrue(
            candidate.source_metadata["license_evidence_is_not_rights_approval"]
        )
        self.assertIn("informational only", result.warnings[0])

    def test_traceav_fixture_normalizes_mapped_upstream_identity(self) -> None:
        adapter = adapter_for_config(get_adapter_config("traceav_bench"))
        result = adapter.inspect_fixture(FIXTURES / "hf_synthetic_traceav_snapshot.json")
        candidate = result.candidates[0]
        self.assertEqual(candidate.provider, "huggingface")
        self.assertEqual(candidate.source_id, "synthetic-traceav-001")
        self.assertEqual(candidate.upstream_namespace, "traceav")
        self.assertEqual(candidate.upstream_asset_id, "synthetic-traceav-video-77")
        self.assertEqual(
            candidate.upstream_id, "traceav:synthetic-traceav-video-77"
        )
        self.assertIn(
            "omnivideobench:synthetic-omni-77", candidate.identity_keys()
        )
        self.assertEqual(candidate.lineage_relation, "mapped_from")
        self.assertEqual(candidate.duration_s, 3300.0)
        self.assertEqual(candidate.license_evidence[0].name, "CC-BY-4.0")
        self.assertTrue(candidate.has_ambient_audio)

    def test_mutable_revision_fails_closed(self) -> None:
        adapter = adapter_for_config(get_adapter_config("lovr"))
        with self.assertRaisesRegex(FixtureError, "not pinned"):
            adapter.inspect_fixture(FIXTURES / "hf_missing_revision.json")

    def test_missing_license_is_valid_unresolved_reconnaissance(self) -> None:
        adapter = adapter_for_config(get_adapter_config("lovr"))
        result = adapter.inspect_fixture(FIXTURES / "hf_missing_license.json")
        self.assertEqual(result.candidates, ())
        self.assertIn("License evidence is unresolved", result.warnings[1])

    def test_official_release_ids_are_distinct_from_code_repositories(self) -> None:
        expected = {
            "lovr": ("debugger123/LoVR-benchmark", "TechNomad-ds/LoVR-benchmark"),
            "flare": ("AnonymousFLARE/FLARE", "YqjMartin/FLARE"),
            "longshotbench": ("MBZUAI/longshot-bench", "mbzuai-oryx/LongShOT"),
            "trace_vesbench": ("buaaplay/VES-Bench", "buaa-colalab/TRACE"),
        }
        for adapter_id, (dataset_repo, code_repo) in expected.items():
            config = get_adapter_config(adapter_id)
            self.assertEqual(config.repository_id, dataset_repo)
            self.assertEqual(config.repository_kind, "dataset")
            self.assertEqual(config.code_repository_id, code_repo)
            self.assertEqual(config.code_repository_provider, "github")

    def test_every_corrected_release_id_accepts_its_schema_fixture(self) -> None:
        fixtures = {
            "lovr": "hf_lovr_snapshot.json",
            "flare": "hf_flare_release_snapshot.json",
            "longshotbench": "hf_longshot_release_snapshot.json",
            "trace_vesbench": "hf_vesbench_release_snapshot.json",
        }
        for adapter_id, fixture in fixtures.items():
            with self.subTest(adapter=adapter_id):
                result = adapter_for_config(
                    get_adapter_config(adapter_id)
                ).inspect_fixture(FIXTURES / fixture)
                self.assertEqual(
                    result.repository_id,
                    get_adapter_config(adapter_id).repository_id,
                )

    def test_github_manifest_provider_remains_supported(self) -> None:
        result = adapter_for_config(get_adapter_config("nasa_media")).inspect_fixture(
            FIXTURES / "github_synthetic_manifest_snapshot.json"
        )
        self.assertEqual(result.provider, "github")
        self.assertEqual(result.repository_id, "official/NASA-media-manifest")

    def test_protocol_and_manual_sources_are_explicit_and_not_executable(self) -> None:
        expected = {
            "vragbench": "protocol_only",
            "egolife": "manual_resolution",
            "ego4d": "manual_resolution",
            "omnivideobench": "manual_resolution",
        }
        for adapter_id, state in expected.items():
            config = get_adapter_config(adapter_id)
            self.assertEqual(config.adapter_state, state)
            with self.assertRaisesRegex(ValueError, state):
                adapter_for_config(config)

    def test_access_crosswalk_is_lossless_and_fail_closed(self) -> None:
        status = access_crosswalk("public_card_only_payload_unavailable")
        self.assertEqual(status.access_gate, "public")
        self.assertEqual(status.payload_state, "card_only_payload_unavailable")
        with self.assertRaisesRegex(ValueError, "unmapped technical access status"):
            access_crosswalk("downloadable-ish")

    def test_priority_targets_have_adapter_configuration(self) -> None:
        expected = {
            "lovr",
            "longvidsearch",
            "flare",
            "longshotbench",
            "videogaia",
            "trace_vesbench",
            "traceav_bench",
            "lvbench",
            "video_mme",
            "longvideobench",
            "longvideobench_meta",
            "mlvu",
            "vragbench",
            "egolife",
            "ego4d",
            "omnivideobench",
            "nasa_media",
            "nara_video",
            "noaa_media",
            "wikimedia_commons_video",
        }
        self.assertTrue(expected.issubset(PRIORITY_ADAPTERS))


if __name__ == "__main__":
    unittest.main()
