"""End-to-end media-backed v2 experiment orchestration."""

from __future__ import annotations

import csv
import json
import shutil
import statistics
import sys
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from av_trace import SchemaRegistry, validate_trajectory
from av_trace.util import load_json, sha256_json
from av_trace_agent_runtime import RuntimeConfig, run_subprocess_episode
from av_trace_mvp.index import GeneratedCorpus, load_generated
from av_trace_mvp.metrics import aggregate_metrics, dashboard_rows, score_episode
from av_trace_validation.metrics_adapter import adapt_episode_metrics

from .backend import MediaBackedBackend, MediaRegistration
from .certification import CertificationBinding, verify_certified_dataset
from .indexing import MediaIndexBuild, build_media_index


AGENTS = (
    "AlwaysAnswer",
    "SingleShotRAG",
    "ReActHeuristic",
    "EvidenceBeliefState",
)
STATES = ("CLEAN", "BLOCKED", "RESTORED")
MUTATIONS = (
    {
        "mutation_id": "blanked_visual_segment",
        "asset_id": "syn_source_01",
        "fixture": "syn_source_01_blank_24_30.mp4",
        "affected_family": "syn_f01_visual_order",
        "control_family": "syn_f02_speech_sequence",
    },
    {
        "mutation_id": "muted_ambient_segment",
        "asset_id": "syn_source_02",
        "fixture": "syn_source_02_mute_38_44.mp4",
        "affected_family": "syn_f03_bell_then_square",
        "control_family": "syn_f04_star_bin",
    },
    {
        "mutation_id": "altered_speech_codec_segment",
        "asset_id": "syn_source_01",
        "fixture": "syn_source_01_speech_72_78_to_659hz.mp4",
        "affected_family": "syn_f02_speech_sequence",
        "control_family": "syn_f01_visual_order",
    },
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, sort_keys=True, separators=(",", ":"))
                        if isinstance(value, (dict, list, tuple))
                        else value
                    )
                    for key, value in row.items()
                }
            )


def _registrations(generated_root: Path) -> dict[str, MediaRegistration]:
    corpus_index = load_json(generated_root / "corpus_index.json")
    return {
        item["source_id"]: MediaRegistration(
            asset_id=item["source_id"],
            path=generated_root / item["media_path"],
            media_hash=item["media_sha256"],
        )
        for item in corpus_index["sources"]
    }


def _baseline_command(agent: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "av_trace_agent_runtime.baseline_entrypoint",
        "--agent",
        agent,
    ]


def _run_one(
    *,
    corpus: GeneratedCorpus,
    family: Mapping[str, Any],
    state_role: str,
    agent: str,
    media_index: MediaIndexBuild,
    media: MediaRegistration,
    registry: SchemaRegistry,
    runtime_config: RuntimeConfig,
) -> dict[str, Any]:
    backend = MediaBackedBackend(
        deepcopy(dict(family)),
        state_role,
        corpus.index,
        corpus.manifest,
        media_index=media_index.index,
        media=media,
        registry=registry,
    )
    trajectory = run_subprocess_episode(
        backend=backend,
        family=family,
        state_role=state_role,
        agent_name=agent,
        command=_baseline_command(agent),
        config=runtime_config,
        registry=registry,
    )
    validation = validate_trajectory(trajectory, registry)
    if not validation.ok:
        first = validation.issues[0]
        raise ValueError(
            f"Subprocess trajectory failed validation: {first.code} "
            f"at {first.pointer}: {first.message}"
        )
    return trajectory


def _calibration(rows: Sequence[Mapping[str, Any]], bins: int = 5) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["agent"])].append(row)
    output: list[dict[str, Any]] = []
    for agent, values in sorted(grouped.items()):
        ordered = sorted(
            values,
            key=lambda item: (
                float(item["final_p_sufficient"]),
                item["family_id"],
                item["state_role"],
            ),
        )
        for index in range(bins):
            start = index * len(ordered) // bins
            end = (index + 1) * len(ordered) // bins
            selected = ordered[start:end]
            if not selected:
                continue
            output.append(
                {
                    "agent": agent,
                    "bin": index + 1,
                    "count": len(selected),
                    "mean_predicted_sufficiency": sum(
                        float(item["final_p_sufficient"]) for item in selected
                    )
                    / len(selected),
                    "observed_sufficiency_rate": sum(
                        float(item["observed_sufficient"]) for item in selected
                    )
                    / len(selected),
                    "mean_squared_error": sum(
                        (
                            float(item["final_p_sufficient"])
                            - float(item["observed_sufficient"])
                        )
                        ** 2
                        for item in selected
                    )
                    / len(selected),
                }
            )
    return output


def _observed_route_ids(family: Mapping[str, Any], trajectory: Mapping[str, Any]) -> list[str]:
    hashes = {
        sha256_json({"evidence_id": item["evidence_id"]}): item["evidence_id"]
        for item in family["claim_evidence_graph"]["evidence_units"]
    }
    return sorted(
        {
            hashes[route]
            for event in trajectory["events"]
            for result in event.get("response", {}).get("results", ())
            if result.get("result_type") == "observation"
            for route in result.get("payload", {}).get("_route_refs", ())
            if route in hashes
        }
    )


def _observation_signatures(trajectory: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return semantic media outputs without hash/provenance-only differences."""

    signatures = []
    for event in trajectory["events"]:
        for result in event.get("response", {}).get("results", ()):
            if result.get("result_type") != "observation":
                continue
            payload = deepcopy(result["payload"])
            payload.pop("_route_refs", None)
            payload.pop("media_provenance", None)
            payload.pop("inspection", None)
            detection = payload.get("visual_detection")
            if isinstance(detection, dict):
                detection.pop("numeric_tokens", None)
            signatures.append(
                {
                    "interval": result["interval"],
                    "modalities": result["modalities"],
                    "payload": payload,
                }
            )
    return sorted(
        signatures,
        key=lambda item: (
            item["interval"]["start_s"],
            item["interval"]["end_s"],
            item["modalities"],
            sha256_json(item["payload"]),
        ),
    )


def _mutation_comparison(
    *,
    mutation: Mapping[str, Any],
    original: Mapping[tuple[str, str], dict[str, Any]],
    mutated: Mapping[tuple[str, str], dict[str, Any]],
    families: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    affected_checks = []
    control_checks = []
    for agent in AGENTS:
        affected_family = families[mutation["affected_family"]]
        before = original[(agent, mutation["affected_family"])]
        after = mutated[(agent, mutation["affected_family"])]
        before_routes = _observed_route_ids(affected_family, before)
        after_routes = _observed_route_ids(affected_family, after)
        before_signatures = _observation_signatures(before)
        after_signatures = _observation_signatures(after)
        before_row = adapt_episode_metrics(
            agent, affected_family, "CLEAN", before, mutation["_denominator"]
        )
        after_row = adapt_episode_metrics(
            agent, affected_family, "CLEAN", after, mutation["_denominator"]
        )
        affected_checks.append(
            {
                "agent": agent,
                "original_answer": before["final_output"]["natural_language_answer"],
                "mutated_answer": after["final_output"]["natural_language_answer"],
                "original_evidence_ids": before_routes,
                "mutated_evidence_ids": after_routes,
                "original_observation_signatures": before_signatures,
                "mutated_observation_signatures": after_signatures,
                "original_supported_answer_success": before_row["supported_answer_success"],
                "mutated_supported_answer_success": after_row["supported_answer_success"],
                "evidence_changed": before_signatures != after_signatures,
                "answer_changed_or_failed": (
                    before["final_output"]["natural_language_answer"]
                    != after["final_output"]["natural_language_answer"]
                    or after_row["supported_answer_success"] == 0
                ),
            }
        )
        control_family = families[mutation["control_family"]]
        control_before = original[(agent, mutation["control_family"])]
        control_after = mutated[(agent, mutation["control_family"])]
        before_control_row = adapt_episode_metrics(
            agent, control_family, "CLEAN", control_before, mutation["_denominator"]
        )
        after_control_row = adapt_episode_metrics(
            agent, control_family, "CLEAN", control_after, mutation["_denominator"]
        )
        control_checks.append(
            {
                "agent": agent,
                "answer_stable": (
                    control_before["final_output"]["natural_language_answer"]
                    == control_after["final_output"]["natural_language_answer"]
                ),
                "evidence_stable": (
                    _observation_signatures(control_before)
                    == _observation_signatures(control_after)
                ),
                "supported_answer_stable": (
                    before_control_row["supported_answer_success"]
                    == after_control_row["supported_answer_success"]
                ),
            }
        )
    passed = all(
        item["evidence_changed"]
        and item["answer_changed_or_failed"]
        and item["original_supported_answer_success"] == 1
        and item["mutated_supported_answer_success"] == 0
        for item in affected_checks
    ) and all(
        item["answer_stable"]
        and item["evidence_stable"]
        and item["supported_answer_stable"]
        for item in control_checks
    )
    return {
        "mutation_id": mutation["mutation_id"],
        "asset_id": mutation["asset_id"],
        "fixture": mutation["fixture"],
        "affected_family": mutation["affected_family"],
        "control_family": mutation["control_family"],
        "affected_checks": affected_checks,
        "control_checks": control_checks,
        "passed": passed,
    }


def _artifact_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): "sha256:" + __import__("hashlib").sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "artifact_hashes.json"
    }


def _certified_premature_stop_summary(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["agent"]), str(row["state_role"]))].append(row)
    output = []
    for (agent, state_role), values in sorted(grouped.items()):
        eligible = [item for item in values if item["premature_stop_eligible"] == 1]
        numerator = sum(int(item["premature_stop"]) for item in eligible)
        output.append(
            {
                "agent": agent,
                "state_role": state_role,
                "eligible_episodes": len(eligible),
                "premature_stops": numerator,
                "rate": numerator / len(eligible) if eligible else None,
                "denominator_source": (
                    values[0]["premature_stop_denominator_source"] if values else None
                ),
            }
        )
    return output


def run_media_backed_experiment(
    *,
    repository_root: str | Path,
    output_root: str | Path,
    run_mutations: bool = True,
) -> dict[str, Any]:
    """Run the complete certified media-backed experiment and write v2 outputs."""

    repository_root = Path(repository_root).resolve()
    generated_root = repository_root / "mvp/generated/full"
    validator_root = repository_root / "mvp/validator/generated"
    output_root = Path(output_root).resolve()
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    registry = SchemaRegistry(repository_root)
    corpus = load_generated(generated_root)
    certification = verify_certified_dataset(
        corpus, validator_root=validator_root
    )
    media_index = build_media_index(
        generated_root=generated_root,
        families=corpus.families,
    )
    _write_json(output_root / "media_index.json", media_index.index.to_document())
    _write_json(output_root / "media_index_build.json", media_index.build_record)
    registrations = _registrations(generated_root)
    runtime_config = RuntimeConfig(timeout_s=20.0, seed=20260906)

    trajectories: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    original_clean: dict[tuple[str, str], dict[str, Any]] = {}
    for agent in AGENTS:
        for family in sorted(corpus.families, key=lambda item: item["family_id"]):
            for state_role in STATES:
                trajectory = _run_one(
                    corpus=corpus,
                    family=family,
                    state_role=state_role,
                    agent=agent,
                    media_index=media_index,
                    media=registrations[family["source"]["asset_id"]],
                    registry=registry,
                    runtime_config=runtime_config,
                )
                path = (
                    output_root
                    / "trajectories/main"
                    / agent
                    / f"{family['family_id']}.{state_role.lower()}.json"
                )
                _write_json(path, trajectory)
                trajectories.append(trajectory)
                validation_rows.append(
                    {
                        "agent": agent,
                        "family_id": family["family_id"],
                        "state_role": state_role,
                        "trajectory_hash": trajectory["replay"]["trajectory_hash"],
                        "valid": True,
                    }
                )
                episode_rows.append(
                    adapt_episode_metrics(
                        agent,
                        family,
                        state_role,
                        trajectory,
                        certification.denominator,
                    )
                )
                if state_role == "CLEAN":
                    original_clean[(agent, family["family_id"])] = trajectory

    aggregates = aggregate_metrics(episode_rows)
    dashboard = dashboard_rows(episode_rows, aggregates)
    calibration = _calibration(episode_rows)

    fixed_runs: list[dict[str, Any]] = []
    fixed_family = certification.fixed_call_family
    for agent in AGENTS:
        trajectory = _run_one(
            corpus=corpus,
            family=fixed_family,
            state_role="RESTORED",
            agent=agent,
            media_index=media_index,
            media=registrations[fixed_family["source"]["asset_id"]],
            registry=registry,
            runtime_config=runtime_config,
        )
        _write_json(
            output_root / "trajectories/fixed_call" / f"{agent}.restored.json",
            trajectory,
        )
        trigger_indexes = [
            index
            for index, event in enumerate(trajectory["events"])
            if event.get("active_hook_ids")
        ]
        fixed_runs.append(
            {
                "agent": agent,
                "trajectory_hash": trajectory["replay"]["trajectory_hash"],
                "trigger_indexes": trigger_indexes,
                "triggered_at_certified_index": (
                    trigger_indexes == [certification.fixed_call_case["trigger_value"]]
                ),
                # The fixed-call variant intentionally shares a family ID with
                # the canonical status-trigger case but has no separate
                # denominator artifact.  Score its state endpoint without
                # applying the canonical premature-stop denominator.
                "grounded_task_success": score_episode(
                    agent, fixed_family, "RESTORED", trajectory
                )["grounded_task_success"],
            }
        )

    mutation_reports: list[dict[str, Any]] = []
    if run_mutations:
        fixture_hashes = load_json(
            repository_root / "mvp/media_backed/fixtures/fixture_hashes.json"
        )
        hashes = {item["path"]: item["sha256"] for item in fixture_hashes["fixtures"]}
        families = {item["family_id"]: item for item in corpus.families}
        for spec in MUTATIONS:
            registration = MediaRegistration(
                asset_id=spec["asset_id"],
                path=repository_root / "mvp/media_backed/fixtures" / spec["fixture"],
                media_hash=hashes[spec["fixture"]],
            )
            # Rebuild search over the exact mutated bytes.  Reusing the
            # canonical media index here would make mutation-time search stale
            # even though citable observations were decoded from the fixture.
            mutated_media_index = build_media_index(
                generated_root=generated_root,
                families=corpus.families,
                media_overrides={
                    spec["asset_id"]: (registration.path, registration.media_hash)
                },
                require_full_coverage=False,
            )
            _write_json(
                output_root / "mutation_indexes" / f"{spec['mutation_id']}.json",
                mutated_media_index.index.to_document(),
            )
            _write_json(
                output_root
                / "mutation_indexes"
                / f"{spec['mutation_id']}.build.json",
                mutated_media_index.build_record,
            )
            affected_evidence_ids = {
                evidence["evidence_id"]
                for family in corpus.families
                if family["family_id"] == spec["affected_family"]
                for evidence in family["claim_evidence_graph"]["evidence_units"]
            }
            canonical_relevant = sorted(
                sha256_json(
                    {
                        "interval": record.interval,
                        "modality": record.modality,
                        "search_text": record.search_text,
                        "payload": record.payload,
                    }
                )
                for record in media_index.index.records
                if affected_evidence_ids.intersection(record.route_evidence_ids)
            )
            mutated_relevant = sorted(
                sha256_json(
                    {
                        "interval": record.interval,
                        "modality": record.modality,
                        "search_text": record.search_text,
                        "payload": record.payload,
                    }
                )
                for record in mutated_media_index.index.records
                if affected_evidence_ids.intersection(record.route_evidence_ids)
            )
            if canonical_relevant == mutated_relevant:
                raise ValueError(
                    f"Mutation {spec['mutation_id']} did not alter its affected media-derived index records."
                )
            mutated: dict[tuple[str, str], dict[str, Any]] = {}
            for agent in AGENTS:
                for family_id in (spec["affected_family"], spec["control_family"]):
                    family = families[family_id]
                    trajectory = _run_one(
                        corpus=corpus,
                        family=family,
                        state_role="CLEAN",
                        agent=agent,
                        media_index=mutated_media_index,
                        media=registration,
                        registry=registry,
                        runtime_config=runtime_config,
                    )
                    mutated[(agent, family_id)] = trajectory
                    _write_json(
                        output_root
                        / "trajectories/mutations"
                        / spec["mutation_id"]
                        / agent
                        / f"{family_id}.clean.json",
                        trajectory,
                    )
            enriched = dict(spec)
            enriched["_denominator"] = certification.denominator
            comparison = _mutation_comparison(
                mutation=enriched,
                original=original_clean,
                mutated=mutated,
                families=families,
            )
            comparison["mutation_media_index_hash"] = mutated_media_index.index.index_hash
            comparison["mutation_media_index_build_hash"] = mutated_media_index.build_record[
                "build_hash"
            ]
            comparison["affected_index_records_changed"] = True
            mutation_reports.append(comparison)

    media_consistency = {
        "original_registered_evidence_count": sum(
            len(family["claim_evidence_graph"]["evidence_units"])
            for family in corpus.families
        ),
        "media_index_bound_evidence_count": len(
            {
                evidence_id
                for record in media_index.index.records
                for evidence_id in record.route_evidence_ids
            }
        ),
        "all_original_evidence_media_detected": True,
        "mutation_count": len(mutation_reports),
        "mutation_pass_count": sum(item["passed"] for item in mutation_reports),
        "tamper_sensitivity_rate": (
            sum(item["passed"] for item in mutation_reports) / len(mutation_reports)
            if mutation_reports
            else None
        ),
    }
    report = {
        "schema_version": "2.0.0",
        "experiment_id": "av-trace-media-backed-mvp-v2",
        "created_at": "2026-09-06T00:00:00Z",
        "scope": "synthetic_media_backed_construct_validation",
        "certification": {
            "certificate_id": certification.certificate["certificate_id"],
            "certificate_hash": certification.certificate["certificate_hash"],
            "status": certification.certificate["status"],
            "backend_manifest_hash": certification.certificate["backend_manifest_hash"],
            "certified_index_hash": certification.certificate["index_hash"],
            "denominator_hash": certification.artifact_index["denominator_hash"],
        },
        "media_index": media_index.build_record,
        "counts": {
            "main_trajectories": len(trajectories),
            "fixed_call_trajectories": len(fixed_runs),
            "mutation_trajectories": len(MUTATIONS) * 2 * len(AGENTS) if run_mutations else 0,
            "valid_main_trajectories": sum(item["valid"] for item in validation_rows),
        },
        "aggregates": aggregates,
        "dashboard": dashboard,
        "sufficiency_calibration": calibration,
        "certified_premature_stop": _certified_premature_stop_summary(
            episode_rows
        ),
        "fixed_call_fixture": {
            "label": "separate_fixed_call_integration_fixture",
            "family_id": fixed_family["family_id"],
            "case_hash": certification.fixed_call_case["family_hash"],
            "runs": fixed_runs,
            "all_triggered_at_certified_index": all(
                item["triggered_at_certified_index"] for item in fixed_runs
            ),
        },
        "mutation_sensitivity": mutation_reports,
        "media_consistency": media_consistency,
        "synthetic_specific_perception_outputs": [
            "fixed-layout central-object shape/color detection",
            "closed-vocabulary burned-in caption and counter OCR",
            "procedural tonal speech decoded by a six-symbol codebook (not ASR)",
            "procedural waveform classes for bell/click pulses, motor hum, and confirmation chime",
            "synthetic role wording added as a deterministic display projection of decoded codec symbols",
        ],
    }
    report["result_hash"] = sha256_json(report)
    _write_json(output_root / "report.json", report)
    _write_json(output_root / "validation.json", validation_rows)
    _write_json(output_root / "calibration.json", calibration)
    _write_json(output_root / "mutation_report.json", mutation_reports)
    _write_csv(output_root / "episode_metrics.csv", episode_rows)
    _write_csv(output_root / "summary.csv", aggregates["state"] + aggregates["paired"])
    _write_csv(output_root / "dashboard.csv", dashboard)
    _write_json(
        output_root / "run_manifest.json",
        {
            "schema_version": "2.0.0",
            "created_at": "2026-09-06T00:00:00Z",
            "agents": list(AGENTS),
            "states": list(STATES),
            "runtime": asdict(runtime_config),
            "result_hash": report["result_hash"],
            "trajectory_hashes": sorted(
                item["replay"]["trajectory_hash"] for item in trajectories
            ),
        },
    )
    _write_json(output_root / "artifact_hashes.json", _artifact_hashes(output_root))
    return report
