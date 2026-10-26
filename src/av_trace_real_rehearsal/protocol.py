"""Deterministic real-media protocol execution for LVB-01.

This module measures protocol mechanics only. It does not implement learned
semantic visual retrieval, infer benchmark answers, or create annotations.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

from .adapter import (
    AccessBlockedError,
    FrameSample,
    RestrictedAssetAdapter,
    SubtitleProxyHit,
    _sha256_json,
)


State = Literal["CLEAN", "BLOCKED", "RESTORED"]
Route = Literal[
    "visual_only",
    "subtitle_proxy_only",
    "video_to_subtitle_proxy",
    "subtitle_proxy_to_video",
]
Baseline = Literal["direct_single_shot", "subtitle_first", "visual_first", "recovery_agent"]

ROUTES: tuple[Route, ...] = (
    "visual_only",
    "subtitle_proxy_only",
    "video_to_subtitle_proxy",
    "subtitle_proxy_to_video",
)
BASELINES: tuple[Baseline, ...] = (
    "direct_single_shot",
    "subtitle_first",
    "visual_first",
    "recovery_agent",
)
STATES: tuple[State, ...] = ("CLEAN", "BLOCKED", "RESTORED")


@dataclass(frozen=True)
class ProvisionalTask:
    task_id: str
    candidate_id: str
    asset_id: str
    route: Route
    target_cue_index: int
    target_time_s: float
    target_window_start_s: float
    target_window_end_s: float
    wrong_visual_time_s: float
    query_tokens: tuple[str, ...]
    cue_line_sha256: str
    status: str = "PROVISIONAL_REHEARSAL_ONLY"
    source_basis: str = "automatically_derived_from_audited_real_media"
    semantic_visual_retrieval: str = "UNAVAILABLE_NOT_FAKED"
    final_benchmark_annotation: bool = False

    def safe_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("query_tokens")
        value.pop("cue_line_sha256")
        return value


@dataclass(frozen=True)
class InterventionState:
    state: State
    block_route: str
    video_enabled: bool
    subtitle_proxy_enabled: bool
    blocked_video_window: tuple[float, float] | None
    restoration_after_failure: bool
    state_hash: str

    def safe_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if result["blocked_video_window"] is not None:
            result["blocked_video_window"] = [
                round(value, 6) for value in result["blocked_video_window"]
            ]
        return result


@dataclass
class _Episode:
    task: ProvisionalTask
    baseline: Baseline
    intervention: InterventionState
    tool_calls: int = 0
    video_seconds_inspected: float = 0.0
    route_history: list[str] = None  # type: ignore[assignment]
    observations: list[dict[str, Any]] = None  # type: ignore[assignment]
    failures: list[str] = None  # type: ignore[assignment]
    perturbation_applied: bool = False
    recovered_after_perturbation: bool = False
    restoration_triggered: bool = False
    stopped: bool = False
    final_verdict: str = "insufficient"

    def __post_init__(self) -> None:
        self.route_history = []
        self.observations = []
        self.failures = []


def derive_provisional_tasks(adapter: RestrictedAssetAdapter) -> tuple[ProvisionalTask, ...]:
    tasks: list[ProvisionalTask] = []
    for candidate_id in adapter.candidate_ids:
        binding = adapter.binding(candidate_id)
        probe = adapter.derive_probe(candidate_id)
        start = max(0.0, probe["cue_start_s"] - 6.0)
        end = min(binding.duration_s, probe["cue_start_s"] + 6.0)
        for route in ROUTES:
            tasks.append(
                ProvisionalTask(
                    task_id=f"{candidate_id}:{route}:r1",
                    candidate_id=candidate_id,
                    asset_id=binding.asset_id,
                    route=route,
                    target_cue_index=int(probe["cue_index"]),
                    target_time_s=float(probe["visual_time_s"]),
                    target_window_start_s=start,
                    target_window_end_s=end,
                    wrong_visual_time_s=float(probe["wrong_visual_time_s"]),
                    query_tokens=tuple(probe["query_tokens"]),
                    cue_line_sha256=str(probe["cue_line_sha256"]),
                )
            )
    return tuple(tasks)


def _intervention_for(task: ProvisionalTask, state: State) -> InterventionState:
    block_subtitle = task.route in {"subtitle_proxy_only", "video_to_subtitle_proxy"}
    block_route = "subtitle_proxy" if block_subtitle else "video_window"
    payload = {
        "task_id": task.task_id,
        "block_route": block_route,
        "blocked_video_window": (
            None
            if block_subtitle
            else [task.target_window_start_s, task.target_window_end_s]
        ),
        "blocked_subtitle_proxy": block_subtitle,
    }
    return InterventionState(
        state=state,
        block_route=block_route,
        video_enabled=True,
        subtitle_proxy_enabled=not (state in {"BLOCKED", "RESTORED"} and block_subtitle),
        blocked_video_window=(
            (task.target_window_start_s, task.target_window_end_s)
            if state in {"BLOCKED", "RESTORED"} and not block_subtitle
            else None
        ),
        restoration_after_failure=state == "RESTORED",
        state_hash=_sha256_json(payload),
    )


class RehearsalRunner:
    """Execute deterministic matched-state baselines on real asset bytes."""

    runner_version = "lvb01-rehearsal-runner/1.0.0"

    def __init__(self, adapter: RestrictedAssetAdapter) -> None:
        self.adapter = adapter

    def run_all(self) -> dict[str, Any]:
        tasks = derive_provisional_tasks(self.adapter)
        runs = [
            self.run_episode(task, state, baseline)
            for task in tasks
            for state in STATES
            for baseline in BASELINES
        ]
        return {
            "schema_version": "1.0",
            "rehearsal_id": "LVB-01-VISUAL-SUBTITLE-PROXY-REHEARSAL",
            "scope_label": "V + subtitle-proxy internal engineering rehearsal",
            "runner_version": self.runner_version,
            "adapter_version": self.adapter.adapter_version,
            "semantic_visual_retrieval": "UNAVAILABLE_NOT_FAKED",
            "visual_baseline": "deterministic source-time candidate inspection with real frame decoding",
            "subtitle_route": "ordered subtitle-proxy token search with start-time-centered windows",
            "audio_used": False,
            "raw_frames_persisted": False,
            "subtitle_text_persisted": False,
            "final_benchmark_annotations_created": False,
            "tasks": [task.safe_dict() for task in tasks],
            "runs": runs,
            "summary": self._summarize(tasks, runs),
        }

    def run_episode(
        self,
        task: ProvisionalTask,
        state: State,
        baseline: Baseline,
    ) -> dict[str, Any]:
        episode = _Episode(task, baseline, _intervention_for(task, state))
        if baseline == "direct_single_shot":
            self._direct_single_shot(episode)
        elif baseline == "subtitle_first":
            self._subtitle_first(episode)
        elif baseline == "visual_first":
            self._visual_first(episode)
        elif baseline == "recovery_agent":
            self._recovery_agent(episode)
        else:
            raise ValueError(f"unsupported baseline: {baseline}")

        required = self._required_evidence(task.route)
        observed = {item["kind"] for item in episode.observations if item["target_match"]}
        evidence_success = required <= observed
        timestamp_valid = self._citation_validity(episode.observations)
        diagnosed_terminal_block = (
            state == "BLOCKED"
            and baseline == "recovery_agent"
            and bool(episode.failures)
        )
        premature_stop = episode.stopped and not evidence_success and not diagnosed_terminal_block
        unsupported_claim_proxy = int(
            episode.final_verdict == "sufficient"
            and (not evidence_success or not timestamp_valid)
        )
        return {
            "run_id": f"{task.task_id}:{state}:{baseline}",
            "task_id": task.task_id,
            "candidate_id": task.candidate_id,
            "route": task.route,
            "state": state,
            "baseline": baseline,
            "provisional_rehearsal_only": True,
            "intervention": episode.intervention.safe_dict(),
            "matched_envelope": {
                "max_tool_calls": 5,
                "answer_surface": "protocol_evidence_sufficiency_only",
                "available_channels": ["video", "subtitle_proxy"],
            },
            "perturbation": {
                "applied": episode.perturbation_applied,
                "kind": "wrong_visual_window_or_partial_subtitle_result",
                "recovered": episode.recovered_after_perturbation,
            },
            "metrics": {
                "evidence_acquisition_success": int(evidence_success),
                "timestamp_citation_validity": int(timestamp_valid),
                "recovery_after_perturbation": int(episode.recovered_after_perturbation),
                "premature_stop": int(premature_stop),
                "tool_calls": episode.tool_calls,
                "video_seconds_inspected": round(episode.video_seconds_inspected, 6),
                "route_switches": sum(
                    left != right
                    for left, right in zip(episode.route_history, episode.route_history[1:])
                ),
                "unsupported_claim_proxy": unsupported_claim_proxy,
            },
            "final": {
                "verdict": episode.final_verdict,
                "claim_type": "protocol_evidence_sufficiency_only",
                "answer_text_created": False,
            },
            "route_history": episode.route_history,
            "observations": episode.observations,
            "failures": episode.failures,
        }

    @staticmethod
    def _required_evidence(route: Route) -> set[str]:
        if route == "visual_only":
            return {"video"}
        if route == "subtitle_proxy_only":
            return {"subtitle_proxy"}
        return {"video", "subtitle_proxy"}

    @staticmethod
    def _citation_validity(observations: Sequence[Mapping[str, Any]]) -> bool:
        if not observations:
            return True
        for item in observations:
            citation = item["citation"]
            if not (
                0 <= citation["start_s"] <= citation["evidence_time_s"] <= citation["end_s"]
            ):
                return False
        return True

    def _maybe_restore(self, episode: _Episode, failure_code: str) -> bool:
        episode.failures.append(failure_code)
        if episode.intervention.state != "RESTORED":
            return False
        episode.restoration_triggered = True
        return True

    def _video(self, episode: _Episode, *, target: bool) -> bool:
        episode.tool_calls += 1
        episode.route_history.append("video")
        episode.video_seconds_inspected += 1.0
        time_s = episode.task.target_time_s if target else episode.task.wrong_visual_time_s
        blocked_window = episode.intervention.blocked_video_window
        if episode.restoration_triggered:
            blocked_window = None
        try:
            sample = self.adapter.sample_frame(
                episode.task.candidate_id,
                time_s,
                video_enabled=episode.intervention.video_enabled,
                blocked_window=blocked_window,
            )
        except AccessBlockedError as exc:
            self._maybe_restore(episode, str(exc))
            return False
        target_match = (
            target
            and abs(sample.source_time_s - episode.task.target_time_s) <= 1.0
        )
        episode.observations.append(self._frame_observation(sample, target_match))
        return target_match

    @staticmethod
    def _frame_observation(sample: FrameSample, target_match: bool) -> dict[str, Any]:
        return {
            "kind": "video",
            "target_match": target_match,
            "citation": {
                "start_s": max(0.0, sample.source_time_s - 0.5),
                "end_s": sample.source_time_s + 0.5,
                "evidence_time_s": sample.source_time_s,
            },
            "diagnostic": sample.safe_dict(),
        }

    def _subtitle(self, episode: _Episode, *, partial: bool) -> bool:
        episode.tool_calls += 1
        episode.route_history.append("subtitle_proxy")
        excluded = {episode.task.target_cue_index} if partial else set()
        enabled = episode.intervention.subtitle_proxy_enabled or episode.restoration_triggered
        try:
            hits = self.adapter.search_subtitle_proxy(
                episode.task.candidate_id,
                episode.task.query_tokens,
                subtitle_proxy_enabled=enabled,
                excluded_cue_indexes=excluded,
            )
        except AccessBlockedError as exc:
            self._maybe_restore(episode, str(exc))
            return False
        match = next(
            (hit for hit in hits if hit.cue_index == episode.task.target_cue_index),
            None,
        )
        if match is not None:
            episode.observations.append(self._subtitle_observation(match, True))
            return True
        if hits:
            episode.observations.append(self._subtitle_observation(hits[0], False))
        else:
            episode.failures.append("SUBTITLE_PROXY_NO_RESULT")
        return False

    @staticmethod
    def _subtitle_observation(hit: SubtitleProxyHit, target_match: bool) -> dict[str, Any]:
        return {
            "kind": "subtitle_proxy",
            "proxy_label": "subtitle proxy; not audio",
            "target_match": target_match,
            "citation": {
                "start_s": hit.window_start_s,
                "end_s": hit.window_end_s,
                "evidence_time_s": hit.cue_start_s,
            },
            "diagnostic": hit.safe_dict(),
        }

    def _finish(self, episode: _Episode) -> None:
        required = self._required_evidence(episode.task.route)
        observed = {item["kind"] for item in episode.observations if item["target_match"]}
        episode.final_verdict = "sufficient" if required <= observed else "insufficient"
        episode.stopped = True

    def _direct_single_shot(self, episode: _Episode) -> None:
        if episode.task.route == "subtitle_proxy_only":
            self._subtitle(episode, partial=False)
        else:
            self._video(episode, target=True)
        self._finish(episode)

    def _subtitle_first(self, episode: _Episode) -> None:
        if episode.task.route == "visual_only":
            self._video(episode, target=True)
        else:
            first = self._subtitle(episode, partial=False)
            if episode.task.route in {"subtitle_proxy_to_video", "video_to_subtitle_proxy"} and first:
                self._video(episode, target=True)
        self._finish(episode)

    def _visual_first(self, episode: _Episode) -> None:
        if episode.task.route == "subtitle_proxy_only":
            self._subtitle(episode, partial=False)
        else:
            first = self._video(episode, target=True)
            if episode.task.route in {"video_to_subtitle_proxy", "subtitle_proxy_to_video"} and first:
                self._subtitle(episode, partial=False)
        self._finish(episode)

    def _recovery_agent(self, episode: _Episode) -> None:
        episode.perturbation_applied = True
        route = episode.task.route
        if route == "visual_only":
            self._video(episode, target=False)
            success = self._video(episode, target=True)
            if episode.restoration_triggered and not success:
                success = self._video(episode, target=True)
        elif route == "subtitle_proxy_only":
            self._subtitle(episode, partial=True)
            success = self._subtitle(episode, partial=False)
            if episode.restoration_triggered and not success:
                success = self._subtitle(episode, partial=False)
        elif route == "video_to_subtitle_proxy":
            self._video(episode, target=False)
            video_ok = self._video(episode, target=True)
            subtitle_ok = self._subtitle(episode, partial=False) if video_ok else False
            if not subtitle_ok and episode.restoration_triggered:
                subtitle_ok = self._subtitle(episode, partial=False)
            success = video_ok and subtitle_ok
        else:
            self._subtitle(episode, partial=True)
            subtitle_ok = self._subtitle(episode, partial=False)
            video_ok = self._video(episode, target=True) if subtitle_ok else False
            if not video_ok and episode.restoration_triggered:
                video_ok = self._video(episode, target=True)
            success = subtitle_ok and video_ok
        episode.recovered_after_perturbation = success
        self._finish(episode)

    @staticmethod
    def _summarize(
        tasks: Sequence[ProvisionalTask],
        runs: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        metric_names = (
            "evidence_acquisition_success",
            "timestamp_citation_validity",
            "recovery_after_perturbation",
            "premature_stop",
            "tool_calls",
            "video_seconds_inspected",
            "route_switches",
            "unsupported_claim_proxy",
        )

        def aggregate(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
            count = len(items)
            return {
                "run_count": count,
                **{
                    name: round(
                        sum(float(item["metrics"][name]) for item in items) / count,
                        6,
                    )
                    for name in metric_names
                },
            }

        by_baseline = {
            baseline: aggregate([item for item in runs if item["baseline"] == baseline])
            for baseline in BASELINES
        }
        by_state = {
            state: aggregate([item for item in runs if item["state"] == state])
            for state in STATES
        }
        recovery_runs = [
            item
            for item in runs
            if item["baseline"] == "recovery_agent"
        ]
        all_assets = sorted({task.candidate_id for task in tasks})
        asset_recovery = {
            candidate_id: all(
                item["metrics"]["recovery_after_perturbation"] == 1
                for item in recovery_runs
                if item["candidate_id"] == candidate_id
                and item["state"] in {"CLEAN", "RESTORED"}
            )
            for candidate_id in all_assets
        }
        matched = all(
            len(
                {
                    item["intervention"]["state_hash"]
                    for item in runs
                    if item["task_id"] == task.task_id
                }
            )
            == 1
            for task in tasks
        )
        expected_recovery = [
            item
            for item in recovery_runs
            if item["state"] in {"CLEAN", "RESTORED"}
        ]
        blocked_recovery = [
            item
            for item in recovery_runs
            if item["state"] == "BLOCKED"
        ]
        return {
            "asset_count": len(all_assets),
            "task_count": len(tasks),
            "run_count": len(runs),
            "all_assets_have_controlled_perturbation_and_recovery_attempt": all(asset_recovery.values()),
            "per_asset_recovery_check": asset_recovery,
            "matched_intervention_definition_across_states": matched,
            "by_baseline": by_baseline,
            "by_state": by_state,
            "recovery_agent_expected_success_states": aggregate(expected_recovery),
            "recovery_agent_blocked_state": aggregate(blocked_recovery),
            "strict_engineering_go": (
                len(all_assets) == 5
                and all(asset_recovery.values())
                and matched
                and all(
                    item["metrics"]["timestamp_citation_validity"] == 1
                    for item in runs
                )
                and all(
                    item["metrics"]["evidence_acquisition_success"] == 1
                    for item in recovery_runs
                    if item["state"] in {"CLEAN", "RESTORED"}
                )
                and all(
                    item["metrics"]["premature_stop"] == 0
                    for item in recovery_runs
                )
                and all(
                    item["metrics"]["unsupported_claim_proxy"] == 0
                    for item in recovery_runs
                )
            ),
            "scientific_scope": {
                "protocol_execution_on_real_bytes": "SHOWN",
                "learned_semantic_visual_retrieval": "UNTESTED",
                "answer_accuracy_or_final_annotation_quality": "UNTESTED",
                "raw_audio_speech_or_ambient": "UNTESTED_AND_UNAVAILABLE",
                "rights_or_public_release": "NOT_ESTABLISHED",
            },
        }


def write_rehearsal_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        path.chmod(0o600)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
