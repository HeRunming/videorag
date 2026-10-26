#!/usr/bin/env python3
"""Independent artifact-level audit for the Task-103 Wave-R run."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


TOP_KS = (1, 5, 10, 20)
ROOT = Path(".")
RESTRICTED = Path("data/restricted/scale1b/wave_r")
RESULTS = Path("mvp/results/scale1b_wave_r")


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode()


def jhash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def fhash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def self_hash(document: Mapping[str, Any], field: str) -> bool:
    expected = document.get(field)
    payload = dict(document)
    payload.pop(field, None)
    return expected == jhash(payload)


def metrics(
    ranking: Sequence[str], groups: Mapping[str, set[str]],
    contributions: Mapping[str, set[str]] | None,
) -> dict[str, Any]:
    ranks = {
        modality: next(
            (
                rank for rank, item in enumerate(ranking[:20], 1)
                if item in ids and (
                    contributions is None
                    or modality in contributions.get(item, set())
                )
            ),
            None,
        )
        for modality, ids in groups.items() if ids
    }
    present = [rank for rank in ranks.values() if rank is not None]
    output: dict[str, Any] = {
        "first_accepted_evidence_rank": min(present) if present else None,
        "MRR": (
            sum(1 / rank if rank else 0 for rank in ranks.values()) / len(ranks)
            if ranks else None
        ),
    }
    for k in TOP_KS:
        observed = [rank for rank in ranks.values() if rank and rank <= k]
        output[f"Recall@{k}"] = len(observed) / len(ranks) if ranks else None
        output[f"All-Evidence@{k}"] = (
            float(len(observed) == len(ranks)) if ranks else None
        )
        ideal = sum(
            1 / math.log2(i + 1) for i in range(1, min(len(ranks), k) + 1)
        )
        output[f"nDCG@{k}"] = (
            sum(1 / math.log2(rank + 1) for rank in observed) / ideal
            if ideal else None
        )
    return output


def equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return abs(float(left) - float(right)) <= 1e-10


def main() -> int:
    global ROOT
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    ROOT = Path(args.repo_root).resolve()
    failures: list[str] = []
    checks = 0

    contract = load(ROOT / "data/rehearsal_plan/scale1b_wave_r_trust_anchor.json")
    models = load(ROOT / "data/restricted/scale1b/manifests/wave_r_model_acquisition.json")
    segment = load(ROOT / "data/restricted/noaa01/scale1a/segment_manifest.json")
    acquisition = load(ROOT / "data/restricted/noaa01/manifests/noaa01_acquisition_manifest.json")
    observation = load(ROOT / RESTRICTED / "observation_manifest.json")
    index = load(ROOT / RESTRICTED / "learned_index.json")
    checkpoint = load(ROOT / RESTRICTED / "checkpoint_manifest.json")
    build = load(ROOT / RESTRICTED / "build_manifest.json")
    runs = load(ROOT / RESTRICTED / "retrieval_runs.json")
    evaluation = load(ROOT / RESTRICTED / "evaluation_manifest.json")
    report = load(ROOT / RESULTS / "report.json")
    run_manifest = load(ROOT / RESULTS / "run_manifest.json")

    def check(condition: bool, label: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    check(contract["decision"] == "WAVE_R_CONTRACT_FROZEN", "contract_gate")
    check(self_hash(contract, "anchor_sha256"), "contract_self_hash")
    check(models["siglip2_decision"] == "SIGLIP2_SNAPSHOT_READY", "siglip_gate")
    check(models["clap_decision"] == "CLAP_SNAPSHOT_READY", "clap_gate")
    check(models["wave_r_decision"] == "WAVE_R_MODELS_READY", "models_gate")
    check(models["technical_internal_use_authorized"] is True, "internal_use")
    check(
        segment["totals"]["base_cells"] == 3433
        and segment["totals"]["fine_windows"] == 3428
        and segment["totals"]["context_windows"] == 855,
        "timeline_counts",
    )
    source_expected = {x["candidate_id"]: x for x in acquisition["assets"]}
    for binding in build["source_bindings"]:
        source = source_expected[binding["source_ref"]]
        path = ROOT / "data/restricted/noaa01/raw" / source["basename"]
        check(
            path.stat().st_size == binding["size_bytes"]
            and fhash(path).removeprefix("sha256:") == binding["sha256"],
            f"source_identity:{binding['source_ref']}",
        )

    check(self_hash(observation, "observation_manifest_hash"), "observation_hash")
    check(self_hash(index, "index_hash"), "index_hash")
    check(self_hash(checkpoint, "checkpoint_manifest_hash"), "checkpoint_hash")
    check(self_hash(build, "build_manifest_hash"), "build_hash")
    check(self_hash(report, "report_hash"), "report_hash")
    check(self_hash(run_manifest, "run_manifest_hash"), "run_manifest_hash")
    check(len(checkpoint["checkpoints"]) == 10, "checkpoint_count")
    for row in checkpoint["checkpoints"]:
        path = ROOT / row["path"]
        check(
            path.is_file() and path.stat().st_size == row["size_bytes"]
            and fhash(path) == row["sha256"],
            f"checkpoint_file:{row['path']}",
        )
        document = load(path)
        check(
            document["payload_hash"] == row["payload_hash"]
            and document["payload_hash"] == jhash(document["payload"]),
            f"checkpoint_payload:{row['path']}",
        )
        check(
            document["payload"].get("actual_learned_model") is True,
            f"learned_proof:{row['path']}",
        )

    for layer, expected_count, expected_dimension in (
        ("siglip2_visual", 4283, 768), ("clap_audio", 4283, 512)
    ):
        documents = index["modalities"][layer]["documents"]
        check(len(documents) == expected_count, f"index_count:{layer}")
        invalid = 0
        for document in documents:
            vector = np.frombuffer(
                bytes.fromhex(document["vector_f16_hex"]), dtype="<f2"
            ).astype(np.float32)
            norm = float(np.linalg.norm(vector))
            invalid += (
                len(vector) != expected_dimension
                or not np.isfinite(vector).all()
                or abs(norm - 1.0) > 0.02
            )
        check(invalid == 0, f"index_vectors:{layer}:{invalid}")

    rows = evaluation["metric_rows"]
    expected_counts = {
        "V-CLIP": 8, "V-SIGLIP2": 8, "A-AST": 2, "A-CLAP": 2,
        "S-BM25": 4, "F-CTRL": 10, "F-V": 10, "F-A": 10, "F-VA": 10,
    }
    observed_counts = {
        ranker: sum(row["ranker"] == ranker for row in rows)
        for ranker in expected_counts
    }
    check(observed_counts == expected_counts, "comparison_matrix")
    check(
        all(row["family_disposition"] == "retained" for row in rows),
        "excluded_family_scored",
    )
    check(
        all(row["modality_necessity"] is None for row in rows),
        "modality_necessity_nonnull",
    )
    clean_runs = {
        (row["family_id"], row["scope"], row["ranker"]): row
        for row in runs["rows"] if row["probe"] == "clean"
    }
    metric_mismatches = 0
    for row in rows:
        stored = clean_runs[(row["family_id"], row["scope"], row["ranker"])]
        ranking = stored["evaluator_private_ranking_segment_ids"]
        groups = {
            key: set(value) for key, value in stored["support_groups"].items()
        }
        contributions = stored.get("evaluator_private_fused_contributions")
        if contributions is not None:
            contributions = {
                key: set(value) for key, value in contributions.items()
            }
        if row["metric_source"] == "task101_frozen_direct_control":
            frozen = next(
                x for x in contract["wave_r_direct_control_preflight"]["rows"]
                if x["family_id"] == row["family_id"]
                and x["scope"] == row["scope"] and x["row_id"] == row["ranker"]
            )
            route_ranks = frozen["support_route_ranks"]
            recalculated = {
                "first_accepted_evidence_rank": min(
                    [x for x in route_ranks.values() if x is not None],
                    default=None,
                ),
                "MRR": sum(1 / x if x else 0 for x in route_ranks.values())
                / len(route_ranks),
            }
            for k in TOP_KS:
                hits = sum(x is not None and x <= k for x in route_ranks.values())
                recalculated[f"Recall@{k}"] = hits / len(route_ranks)
                recalculated[f"All-Evidence@{k}"] = float(hits == len(route_ranks))
        else:
            recalculated = metrics(ranking, groups, contributions)
        for key in (
            "first_accepted_evidence_rank", "MRR",
            "Recall@1", "Recall@5", "Recall@10", "Recall@20",
            "All-Evidence@1", "All-Evidence@5",
            "All-Evidence@10", "All-Evidence@20",
        ):
            if not equal(row.get(key), recalculated.get(key)):
                metric_mismatches += 1
    check(metric_mismatches == 0, f"metric_recompute:{metric_mismatches}")

    paired_by = {
        (row["family_id"], row["scope"], row["ranker"]): row for row in rows
    }
    paired_mismatches = 0
    for row in evaluation["paired_rows"]:
        left = paired_by[(row["family_id"], row["scope"], row["learned_ranker"])]
        right = paired_by[(row["family_id"], row["scope"], row["control_ranker"])]
        for key in (
            "Recall@1", "Recall@5", "Recall@10", "Recall@20",
            "All-Evidence@1", "All-Evidence@5",
            "All-Evidence@10", "All-Evidence@20", "MRR",
            "nDCG@1", "nDCG@5", "nDCG@10", "nDCG@20",
        ):
            if not equal(row[f"delta_{key}"], left[key] - right[key]):
                paired_mismatches += 1
    check(paired_mismatches == 0, f"paired_recompute:{paired_mismatches}")

    for artifact in run_manifest["artifacts"]:
        path = ROOT / artifact["path"]
        check(
            path.is_file() and path.stat().st_size == artifact["size_bytes"]
            and fhash(path) == artifact["sha256"],
            f"run_manifest:{artifact['path']}",
        )
    media_suffixes = {".wav", ".flac", ".mp3", ".mp4", ".jpg", ".jpeg", ".png"}
    derivatives = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / RESTRICTED).rglob("*")
        if path.is_file() and path.suffix.lower() in media_suffixes
    ]
    check(not derivatives, "persisted_media_derivatives")
    public_text = "\n".join(
        (ROOT / RESULTS / name).read_text(errors="ignore")
        for name in ("report.json", "report.md", "retrieval_metrics.csv",
                     "paired_comparisons.csv", "summary.csv")
    )
    leakage = [
        token for token in (
            "/jizhicfs/", "http_proxy", "https_proxy", "vector_f16_hex",
            "transcript_excerpt",
        ) if token in public_text
    ]
    check(not leakage, "public_leakage")

    result = {
        "schema_version": "av-trace.scale1b.wave-r.audit/1.0",
        "task": 103, "date": "2026-09-12",
        "passed": not failures, "check_count": checks,
        "failures": failures,
        "counts": {
            "source_media": len(source_expected),
            "checkpoints": len(checkpoint["checkpoints"]),
            "metric_rows": len(rows),
            "paired_rows": len(evaluation["paired_rows"]),
            "retrieval_probe_rows": len(runs["rows"]),
            "run_manifest_artifacts": len(run_manifest["artifacts"]),
        },
        "decisions": report["decisions"],
        "boundary": {
            "human_reviewed": False, "gold_annotation": False,
            "modality_necessity": None,
            "final_benchmark": "FINAL_BENCHMARK_NOT_YET_VALIDATED",
        },
    }
    output = ROOT / RESTRICTED / "final_audit.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.chmod(output, 0o600)
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
