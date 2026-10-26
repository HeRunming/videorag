from __future__ import annotations

import sys
from dataclasses import replace
from types import ModuleType, SimpleNamespace

import numpy as np

from av_trace_mini_pilot_families import (
    FrozenClipQueryEncoder,
    HashFixtureEncoder,
    MiningInputs,
    build_candidate_registry,
    search_ambient_labels,
    search_speech_bm25,
    search_visual_vectors,
    slot_specs,
)


def _visual_hex(vector):
    values = np.asarray(vector, dtype=np.float32)
    values /= np.linalg.norm(values)
    return values.astype("<f2").tobytes().hex()


def _index(source_ids):
    speech_documents = []
    ambient_documents = []
    vision_documents = []
    for source_index, source_id in enumerate(source_ids):
        for item_index, start_us in enumerate((0, 300_000_000)):
            speech_documents.append(
                {
                    "segment_id": f"s.{source_id}.{item_index}",
                    "source_ref": source_id,
                    "start_us": start_us,
                    "end_us": start_us + 30_000_000,
                    "modality": "speech",
                    "scale": "speech_chunk_30s",
                    "searchable": True,
                    "search_payload": {
                        "tokens": ["lecture", "physics", "explanation", "basin"],
                        "term_frequency": {
                            "lecture": 1,
                            "physics": 1,
                            "explanation": 1,
                            "basin": 1,
                        },
                        "derived_from_chunk_ids": [
                            f"chunk.{source_id}.{item_index}"
                        ],
                    },
                }
            )
            ambient_documents.append(
                {
                    "segment_id": f"a.{source_id}.{item_index}",
                    "source_ref": source_id,
                    "start_us": start_us,
                    "end_us": start_us + 8_000_000,
                    "modality": "ambient",
                    "scale": "fine",
                    "searchable": True,
                    "search_payload": {
                        "features": [
                            {
                                "class_name": "Writing",
                                "tokens": ["writing", "chalk"],
                                "generic": False,
                                "weight": 0.9,
                            },
                            {
                                "class_name": "Ocean",
                                "tokens": ["ocean", "waves", "surf"],
                                "generic": False,
                                "weight": 0.8,
                            },
                        ]
                    },
                }
            )
            vision_documents.append(
                {
                    "segment_id": f"v.{source_id}.{item_index}",
                    "source_ref": source_id,
                    "start_us": start_us,
                    "end_us": start_us + 8_000_000,
                    "modality": "vision",
                    "scale": "fine",
                    "searchable": True,
                    "search_payload": {
                        "dimension": 4,
                        "vector_f16_hex": _visual_hex(
                            [
                                1 + source_index,
                                2 + item_index,
                                0.5,
                                0.25,
                            ]
                        ),
                    },
                }
            )
    return {
        "modalities": {
            "speech": {
                "documents": speech_documents,
                "document_count": len(speech_documents),
                "average_document_length": 4.0,
                "document_frequency": {
                    "lecture": len(speech_documents),
                    "physics": len(speech_documents),
                    "explanation": len(speech_documents),
                    "basin": len(speech_documents),
                },
            },
            "ambient": {"documents": ambient_documents},
            "vision": {"documents": vision_documents},
        }
    }


def _inputs():
    new_ids = [
        "SG-OXFORD-QM-001",
        "SG-OXFORD-DHL-CONSCIOUSNESS",
        "SG-MIT-RES12-003-L01",
        "SG-YALE-PHYS200-L01",
    ]
    noaa_ids = ["cand-049", "cand-051", "cand-052"]
    return MiningInputs(
        new_index=_index(new_ids),
        noaa_index=_index(noaa_ids),
        new_source_hashes={item: "n" * 64 for item in new_ids},
        noaa_source_hashes={item: "a" * 64 for item in noaa_ids},
        new_routing_records=(),
        official_transcript_routes=(),
        noaa_families=(),
        provenance={
            "new_source": {"fixture": True},
            "noaa_development": {"fixture": True},
        },
    )


def test_search_helpers_cover_speech_ambient_and_visual():
    index = _index(["source-a"])
    assert search_speech_bm25(
        index, "physics explanation", source_ref="source-a"
    )
    assert search_ambient_labels(
        index, "writing chalk", source_ref="source-a"
    )
    assert search_visual_vectors(
        index,
        "physics apparatus",
        source_ref="source-a",
        encoder=HashFixtureEncoder(),
    )


def test_candidate_registry_never_promotes_or_forces_strata():
    registry = build_candidate_registry(
        _inputs(),
        slot_specs(),
        visual_encoder=HashFixtureEncoder(),
        top_k=5,
    )
    assert len(registry["slots"]) == 14
    assert registry["summary"]["human_reviewed_count"] == 0
    assert registry["summary"]["human_gold_count"] == 0
    assert registry["summary"]["final_accepted_family_count"] == 0
    for slot in registry["slots"]:
        candidate = slot["candidate"]
        if candidate is None:
            assert slot["slot_status"] == "UNFILLED_NO_MACHINE_EVIDENCE"
            continue
        assert candidate["current_tier"].startswith("P")
        assert candidate["human_reviewed"] is False
        assert candidate["human_minimality_asserted"] is False
        assert candidate["human_necessity_asserted"] is False
        assert candidate["strata"]["quota_forcing_forbidden"] is True


def test_missing_target_modality_relabels_instead_of_fabricating():
    inputs = _inputs()
    index = dict(inputs.new_index)
    modalities = dict(index["modalities"])
    modalities["ambient"] = {"documents": []}
    index["modalities"] = modalities
    inputs = replace(inputs, new_index=index)
    registry = build_candidate_registry(
        inputs,
        slot_specs(),
        visual_encoder=HashFixtureEncoder(),
        top_k=5,
    )
    slot = next(item for item in registry["slots"] if item["slot_id"] == "F05")
    assert slot["slot_status"] == "UNFILLED_NO_MACHINE_EVIDENCE"
    assert slot["candidate"] is None
    assert slot["missing_target_modalities"] == ["ambient"]


def test_frozen_clip_encoder_restores_numpy_compatibility_aliases(
    monkeypatch,
    tmp_path,
):
    model_path = tmp_path / "data/restricted/noaa01/models/clip"
    model_path.mkdir(parents=True)

    class FakeTensor:
        def __init__(self, values):
            self.values = np.asarray(values, dtype=np.float32)

        def float(self):
            return self

        def norm(self, dim=-1, keepdim=True):
            return FakeTensor(
                np.linalg.norm(self.values, axis=dim, keepdims=keepdim)
            )

        def clamp_min(self, minimum):
            return FakeTensor(np.maximum(self.values, minimum))

        def __truediv__(self, other):
            return FakeTensor(self.values / other.values)

        def __getitem__(self, index):
            return FakeTensor(self.values[index])

        def cpu(self):
            return self

        def numpy(self):
            return self.values

    class FakeProcessor:
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            assert path == model_path
            return cls()

        def __call__(self, **kwargs):
            return SimpleNamespace(
                input_ids=FakeTensor([[1]]),
                attention_mask=FakeTensor([[1]]),
            )

    class FakeModel:
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            assert path == model_path
            return cls()

        def to(self, device):
            assert device == "cpu"
            return self

        def eval(self):
            return self

        def parameters(self):
            return ()

        def text_model(self, **kwargs):
            return SimpleNamespace(pooler_output=FakeTensor([[1.0, 2.0]]))

        def text_projection(self, values):
            return values

    fake_torch = ModuleType("torch")
    fake_torch.inference_mode = lambda: __import__("contextlib").nullcontext()
    fake_transformers = ModuleType("transformers")
    fake_transformers.CLIPModel = FakeModel
    fake_transformers.CLIPProcessor = FakeProcessor
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.delitem(np.__dict__, "long", raising=False)
    monkeypatch.delitem(np.__dict__, "ulong", raising=False)

    vector = FrozenClipQueryEncoder(
        tmp_path,
        model_path="data/restricted/noaa01/models/clip",
    ).encode("test query", 2)

    assert np.long is np.int64
    assert np.ulong is np.uint64
    np.testing.assert_allclose(
        vector,
        np.asarray([1.0, 2.0], dtype=np.float32) / np.sqrt(5.0),
    )
