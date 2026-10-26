#!/usr/bin/env python3
"""Rebind verified Wave-R checkpoints after a non-semantic gate-manifest rewrite.

This tool never runs learned inference. It accepts only the current ten
checkpoints whose payload hashes, source hashes, model revisions and prior
config hash all match the authoritative observation/checkpoint manifests. It
updates only the config-hash envelope so ``build_scale1b_wave_r.py`` can reuse
the checkpoints against the current, independently verified model manifest.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from av_trace_scale1b_retrieval.core import (
    RESTRICTED_REL,
    SCALE1A_ROOT_REL,
    _dump,
    _json_hash,
    _load,
    verify_gates,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    restricted = root / RESTRICTED_REL
    gates = verify_gates(root)
    observation = _load(restricted / "observation_manifest.json")
    checkpoint_manifest = _load(restricted / "checkpoint_manifest.json")
    segment = _load(root / SCALE1A_ROOT_REL / "segment_manifest.json")

    old_config = observation["config"]
    old_hash = observation["config_hash"]
    if _json_hash(old_config) != old_hash:
        raise RuntimeError("OBSERVATION_CONFIG_SELF_HASH_MISMATCH")
    new_config = json.loads(json.dumps(old_config))
    new_config["gate_hashes"] = {
        key: gates[key]
        for key in (
            "contract_sha256",
            "model_manifest_sha256",
            "scale1a_audit_sha256",
        )
    }
    new_hash = _json_hash(new_config)
    expected_sources = {
        row["source_ref"]: row["sha256"] for row in segment["sources"]
    }
    expected_revisions = {
        "siglip2_visual": gates["models"]["models"]["siglip2"]["revision"],
        "clap_audio": gates["models"]["models"]["clap"]["revision"],
    }
    records = checkpoint_manifest["checkpoints"]
    if len(records) != 10:
        raise RuntimeError("CHECKPOINT_COUNT_NOT_TEN")

    documents: list[tuple[Path, dict]] = []
    for record in records:
        path = root / record["path"]
        document = _load(path)
        payload = document.get("payload")
        if (
            document.get("config_hash") != old_hash
            or document.get("payload_hash") != _json_hash(payload)
            or document.get("payload_hash") != record.get("payload_hash")
            or document.get("source_sha256")
            != expected_sources.get(record["source_ref"])
            or payload.get("actual_learned_model") is not True
            or payload.get("model_revision")
            != expected_revisions.get(record["layer"])
        ):
            raise RuntimeError(f"CHECKPOINT_NOT_SAFE_TO_REBIND:{record['path']}")
        documents.append((path, document))

    result = {
        "old_config_hash": old_hash,
        "new_config_hash": new_hash,
        "checkpoint_count": len(documents),
        "payloads_unchanged": True,
        "learned_inference_executed": False,
        "changed": old_hash != new_hash,
    }
    if args.execute and old_hash != new_hash:
        for path, document in documents:
            updated = dict(document)
            updated["config_hash"] = new_hash
            _dump(path, updated)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
