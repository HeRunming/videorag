from __future__ import annotations

import copy

import pytest

from tools import gpt_oss_20b_preflight as pf


def test_manifest_is_exact_and_fail_closed() -> None:
    value = pf.load_manifest()
    pf.validate_manifest(value)
    assert value["model"]["revision"] == pf.REVISION
    assert value["decision"] == "GPT_OSS_20B_ACQUISITION_NO_GO"


def test_rejects_revision_drift() -> None:
    value = copy.deepcopy(pf.load_manifest())
    value["model"]["revision"] = "0" * 40
    with pytest.raises(pf.PreflightError, match="REVISION"):
        pf.validate_manifest(value)


def test_rejects_ready_without_proof() -> None:
    value = copy.deepcopy(pf.load_manifest())
    value["decision"] = "GPT_OSS_20B_ACQUISITION_READY"
    with pytest.raises(pf.PreflightError, match="FAIL_CLOSED"):
        pf.validate_manifest(value)


def test_caps_and_protected_scope() -> None:
    value = pf.load_manifest()
    assert value["acquisition"]["selected_payload_cap_bytes"] == 25 << 30
    assert value["full_model_downloaded"] is False
    assert value["model_inference_run"] is False
    assert value["api_calls_made"] is False
    assert value["evaluation_families_or_keys_touched"] is False
