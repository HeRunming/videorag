from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from av_trace_media_pipeline.certification import verify_certified_dataset

from .conftest import ROOT


def test_checked_in_certificate_and_denominator_bind_live_corpus(corpus):
    binding = verify_certified_dataset(
        corpus, validator_root=ROOT / "mvp/validator/generated"
    )
    assert binding.certificate["status"] == "PASS"
    assert binding.denominator["system_independent"] is True
    assert binding.fixed_call_case["trigger_type"] == "fixed_call_index"


def test_certificate_mismatch_fails_before_experiment(corpus, tmp_path: Path):
    source = ROOT / "mvp/validator/generated"
    target = tmp_path / "validator"
    shutil.copytree(source, target)
    certificate_path = target / "dataset_certificate.json"
    certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    certificate["index_hash"] = "sha256:" + "0" * 64
    certificate_path.write_text(
        json.dumps(certificate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="self-hash mismatch"):
        verify_certified_dataset(corpus, validator_root=target)
