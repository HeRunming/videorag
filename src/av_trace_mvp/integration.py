"""Top-level deterministic MVP generation, validation, execution, and audit."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any, Iterable

from av_trace import GateProfile, SchemaRegistry, validate_family, validate_manifest_gate
from av_trace.trajectory import validate_trajectory
from av_trace.util import load_json, sha256_json

from .agents import DEFAULT_AGENTS
from .backend import FixedBackend
from .experiment import run_experiment
from .index import GeneratedCorpus, build_generated_backend, load_generated
from .synthetic_data import GenerationResult, generate_corpus, probe_mp4


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def artifact_inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in _files(root)
        if path.name != "artifacts.json"
    ]


def generate(
    *,
    repository_root: Path,
    generated_root: Path,
    seed: int,
    probe: bool,
) -> tuple[GenerationResult, GeneratedCorpus, list[dict[str, Any]]]:
    result = generate_corpus(
        config_path=repository_root / "mvp/config/synthetic_scenarios.json",
        output_dir=generated_root,
        mode="full",
        seed=seed,
        clean=True,
        repository_root=repository_root,
    )
    corpus = build_generated_backend(generated_root)
    probes = []
    if probe:
        for source_id in sorted(result.mp4_hashes):
            probes.append(probe_mp4(generated_root / "media" / f"{source_id}.mp4"))
    return result, corpus, probes


def validate(
    *,
    repository_root: Path,
    generated_root: Path,
    results_root: Path | None = None,
) -> dict[str, Any]:
    registry = SchemaRegistry(repository_root)
    schema_report = registry.check_schemas()
    corpus = load_generated(generated_root)
    corpus_index = load_json(generated_root / "corpus_index.json")
    manifests: list[dict[str, Any]] = []
    families: list[dict[str, Any]] = []
    for source in corpus_index["sources"]:
        path = generated_root / source["manifest_path"]
        report = validate_manifest_gate(load_json(path), GateProfile.PUBLIC_RELEASE, registry)
        manifests.append({"path": path.relative_to(generated_root).as_posix(), **report.to_dict()})
    for family in corpus.families:
        source = next(
            item for item in corpus_index["sources"] if item["source_id"] == family["source"]["asset_id"]
        )
        manifest = load_json(generated_root / source["manifest_path"])
        report = validate_family(family, manifest, registry)
        families.append({"family_id": family["family_id"], **report.to_dict()})
    trajectories: list[dict[str, Any]] = []
    if results_root is not None and (results_root / "report.json").is_file():
        report = load_json(results_root / "report.json")
        for item in report.get("trajectories", []):
            validation = validate_trajectory(item["trajectory"], registry)
            trajectories.append(
                {
                    "agent": item["agent"],
                    "family_id": item["family_id"],
                    "state_role": item["state_role"],
                    **validation.to_dict(),
                }
            )
    failures = (
        ([] if schema_report.ok else [{"kind": "schemas"}])
        + [{"kind": "manifest", "id": item["path"]} for item in manifests if item["status"] != "PASS"]
        + [{"kind": "family", "id": item["family_id"]} for item in families if item["status"] != "PASS"]
        + [
            {
                "kind": "trajectory",
                "id": f"{item['agent']}:{item['family_id']}:{item['state_role']}",
            }
            for item in trajectories
            if item["status"] != "PASS"
        ]
    )
    result = {
        "status": "PASS" if not failures else "FAIL",
        "schemas": schema_report.to_dict(),
        "backend": {
            "manifest_sha256": corpus.manifest.manifest_hash,
            "index_sha256": corpus.index.index_hash,
            "record_count": len(corpus.index.records),
            "family_count": len(corpus.families),
        },
        "manifests": manifests,
        "families": families,
        "trajectories": trajectories,
        "counts": {
            "manifests": len(manifests),
            "families": len(families),
            "trajectories": len(trajectories),
            "failures": len(failures),
        },
        "failures": failures,
    }
    result["validation_hash"] = sha256_json(result)
    return result


def run(
    *,
    generated_root: Path,
    results_root: Path,
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    if not (generated_root / "backend_manifest.json").is_file():
        raise FileNotFoundError(
            f"{generated_root / 'backend_manifest.json'} is required; run generate first"
        )
    corpus = load_generated(generated_root)

    def backend_factory(family: dict[str, Any], state_role: str) -> FixedBackend:
        return FixedBackend(family, state_role, corpus.index, corpus.manifest)

    return run_experiment(
        corpus.families,
        DEFAULT_AGENTS,
        backend_factory,
        output_dir=results_root,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
    )


def _metric(
    report: dict[str, Any],
    agent: str,
    state: str,
    metric: str,
    *,
    eligible_field: str | None = None,
) -> float | None:
    values = [
        row[metric]
        for row in report["episode_metrics"]
        if row["agent"] == agent
        and row["state_role"] == state
        and row[metric] is not None
        and (eligible_field is None or row.get(eligible_field) == 1)
    ]
    return sum(values) / len(values) if values else None


def interpretation(report: dict[str, Any]) -> dict[str, Any]:
    agents = report["agents"]
    clean = {agent: _metric(report, agent, "CLEAN", "grounded_task_success") for agent in agents}
    blocked_fsr = {agent: _metric(report, agent, "BLOCKED", "false_sufficient") for agent in agents}
    blocked_premature = {
        agent: _metric(
            report,
            agent,
            "BLOCKED",
            "premature_stop",
            eligible_field="premature_stop_eligible",
        )
        for agent in agents
    }
    restored = {agent: _metric(report, agent, "RESTORED", "grounded_task_success") for agent in agents}
    recovery = {
        agent: _metric(report, agent, "RESTORED", "triggered_supported_recovery")
        for agent in agents
    }
    failures = [
        {
            "agent": row["agent"],
            "family_id": row["family_id"],
            "state_role": row["state_role"],
            "grounded_task_success": row["grounded_task_success"],
        }
        for row in report["episode_metrics"]
        if row["grounded_task_success"] != 1
    ]
    return {
        "clean_correctness_equal": len(set(clean.values())) == 1,
        "clean_grounded_success": clean,
        "diagnostic_metrics_differ": len(set(blocked_fsr.values())) > 1
        or len(set(blocked_premature.values())) > 1,
        "blocked_false_sufficient_rate": blocked_fsr,
        "blocked_premature_stop_rate": blocked_premature,
        "restored_grounded_success": restored,
        "triggered_supported_recovery": recovery,
        "restoration_separates_behavior": len(set(restored.values())) > 1
        or len(set(recovery.values())) > 1,
        "failed_grounded_runs": failures,
    }


def run_all(
    *,
    repository_root: Path,
    generated_root: Path,
    results_root: Path,
    seed: int,
    bootstrap_samples: int,
    bootstrap_seed: int,
    probe: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    generation, corpus, probes = generate(
        repository_root=repository_root,
        generated_root=generated_root,
        seed=seed,
        probe=probe,
    )
    pre_validation = validate(
        repository_root=repository_root,
        generated_root=generated_root,
    )
    if pre_validation["status"] != "PASS":
        raise RuntimeError("Generated corpus validation failed.")
    report = run(
        generated_root=generated_root,
        results_root=results_root,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
    )
    post_validation = validate(
        repository_root=repository_root,
        generated_root=generated_root,
        results_root=results_root,
    )
    if post_validation["status"] != "PASS":
        raise RuntimeError("Trajectory validation failed.")
    deterministic = {
        "generation_metadata_sha256": generation.metadata_sha256,
        "backend_manifest_sha256": corpus.manifest.manifest_hash,
        "backend_index_sha256": corpus.index.index_hash,
        "experiment_result_sha256": report["result_hash"],
        "validation_sha256": post_validation["validation_hash"],
    }
    summary = {
        "status": "PASS",
        "command": (
            "python scripts/run_mvp.py all "
            f"--generated-root {generated_root} --results-root {results_root}"
        ),
        "runtime_s": round(time.perf_counter() - started, 3),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "packages": {
                name: version(name)
                for name in ("av", "jsonschema", "numpy", "Pillow")
            },
            "ffmpeg_libraries": {
                name: ".".join(str(part) for part in parts)
                for name, parts in __import__("av").library_versions.items()
            },
        },
        "counts": {
            "sources": generation.source_count,
            "families": generation.family_count,
            "states_per_family": 3,
            "agents": len(DEFAULT_AGENTS),
            "agent_episodes": len(report["episode_metrics"]),
            "valid_trajectories": post_validation["counts"]["trajectories"],
        },
        "hashes": deterministic,
        "generation": {
            "bytes": generation.total_bytes,
            "mp4_sha256": generation.mp4_hashes,
            "probes": probes,
        },
        "interpretation": interpretation(report),
        "limitations": [
            "Synthetic 4–8 minute compatibility fixtures are not the 20–90 minute public core.",
            "Agents are deterministic symbolic baselines, not learned models.",
            "The frozen exact-text mapper attaches registered claim IDs at evaluation time.",
            "MP4 byte identity across different codec builds is not guaranteed.",
            "Agent execution is metadata-backed; MP4/audio bytes are generated and probed but are not decoded by retrieval tools.",
            "Bundled agents are fixture-specific scripted protocol probes, not independent or leakage-resistant model baselines.",
        ],
    }
    _write_json(results_root / "validation.json", post_validation)
    _write_json(results_root / "run_manifest.json", summary)
    inventory = artifact_inventory(results_root)
    _write_json(
        results_root / "artifacts.json",
        {
            "root": str(results_root),
            "files": inventory,
            "total_bytes": sum(item["bytes"] for item in inventory),
        },
    )
    return summary
