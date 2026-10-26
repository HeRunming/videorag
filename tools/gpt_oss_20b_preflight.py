#!/usr/bin/env python3
"""Offline, fail-closed validator for the GPT-OSS-20B acquisition preflight."""
from __future__ import annotations

import importlib.metadata
import json
import re
from pathlib import Path
from typing import Any

MANIFEST = Path("data/restricted/scale1b/manifests/gpt_oss_20b_preflight.json")
REPO_ID = "openai/gpt-oss-20b"
REVISION = "6cee5e81ee83917806bbde320786a8fb61efebee"
SELECTED_CAP_BYTES = 25 << 30
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class PreflightError(RuntimeError):
    pass


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def validate_manifest(value: dict[str, Any]) -> None:
    model = value.get("model", {})
    if model.get("repo_id") != REPO_ID:
        raise PreflightError("REPO_ID_MISMATCH")
    if model.get("revision") != REVISION or not HEX40.fullmatch(REVISION):
        raise PreflightError("REVISION_MISMATCH")
    if value.get("decision") != "GPT_OSS_20B_ACQUISITION_NO_GO":
        raise PreflightError("FAIL_CLOSED_DECISION_REQUIRED")
    if value.get("network_stopped") is not True:
        raise PreflightError("NETWORK_STOP_NOT_RECORDED")
    if value.get("full_model_downloaded") is not False:
        raise PreflightError("FULL_DOWNLOAD_MUST_BE_FALSE")
    if value.get("model_inference_run") is not False:
        raise PreflightError("INFERENCE_MUST_BE_FALSE")
    if value.get("api_calls_made") is not False:
        raise PreflightError("API_CALLS_MUST_BE_FALSE")
    if value.get("evaluation_families_or_keys_touched") is not False:
        raise PreflightError("PROTECTED_SCOPE_VIOLATION")
    acquisition = value.get("acquisition", {})
    if acquisition.get("selected_payload_cap_bytes") != SELECTED_CAP_BYTES:
        raise PreflightError("CAP_MISMATCH")
    gaps = value.get("blocking_gaps")
    required = {
        "exact_tree_not_archived",
        "exact_file_sizes_not_archived",
        "exact_hash_identities_not_archived",
        "exact_config_and_tokenizer_not_archived",
        "official_license_text_not_archived",
        "runtime_load_not_proven",
    }
    if not isinstance(gaps, list) or not required.issubset(set(gaps)):
        raise PreflightError("BLOCKING_GAPS_INCOMPLETE")
    runtime = value.get("runtime_compatibility", {})
    if runtime.get("current_environment_proven_compatible") is not False:
        raise PreflightError("RUNTIME_MUST_REMAIN_UNPROVEN")
    if runtime.get("gpt_oss_config_registered") is not True:
        raise PreflightError("CONFIG_SUPPORT_NOT_RECORDED")
    if runtime.get("gpt_oss_causal_lm_registered") is not True:
        raise PreflightError("MODEL_SUPPORT_NOT_RECORDED")
    if runtime.get("mxfp4_quantizer_registered") is not True:
        raise PreflightError("MXFP4_SUPPORT_NOT_RECORDED")
    if runtime.get("gpt_oss_model_import_succeeded") is not False:
        raise PreflightError("IMPORT_FAILURE_NOT_RECORDED")
    security = value.get("security", {})
    if security.get("trust_remote_code_planned") is not False:
        raise PreflightError("REMOTE_CODE_MUST_BE_DISABLED")
    if security.get("pickle_weights_allowed") is not False:
        raise PreflightError("PICKLE_MUST_BE_REJECTED")


def main() -> int:
    value = load_manifest()
    validate_manifest(value)
    print(value["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
