#!/usr/bin/env python3
"""Development-only P23_102 Acquire/Ground/Act rehearsal runner.

Validation and planning never load model weights or decode media. Execution is
fail-closed and remains unauthorized while the frozen Qwen 1.5B agent
competence gate is incomplete or the machine-provisional bundle lacks accepted
SES / human-valid semantics.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from av_trace_scale1b_agent.backend import (
    FullTimelineBackend,
    LearnedFeatureModels,
)
from av_trace_scale1b_agent.checkpoint import canonical_bytes, semantic_hash
from av_trace_scale1b_agent.controller import (
    GenerationConfig,
    LearnedCallFailure,
    run_controller_decision,
    run_grounded_generator,
)
from av_trace_scale1b_agent.evaluation import mean_or_none
from av_trace_scale1b_agent.process import ModelProcessError
from av_trace_scale1b_agent.schema import PublicSchemaError

SCHEMA = "av-trace.p23-102-rehearsal-runner/2.0"
FROZEN_DATE = "2026-10-14"
CONFIG_REL = Path(
    "data/rehearsal_plan/p23_102_acquire_ground_act_rehearsal_v1.json"
)
ATTESTATION_REL = Path(
    "data/restricted/p23_102_acquire_ground_act_rehearsal_v1/"
    "adapter_attestation.json"
)
BUNDLE_REL = Path(
    "data/restricted/epic_p23_102_machine_provisional_families_v1"
)
INDEX_REL = Path("data/restricted/epic_p23_102_full_timeline_index_v1")
SOURCE_MANIFEST_REL = Path(
    "data/restricted/epic_p23_102_source_v1/manifests/"
    "epic_p23_102_exact_manifest.json"
)
MODEL_COMPETENCE_REL = Path(
    "data/restricted/scale1b/ga_pilot/task110_final_status.json"
)
MODEL_MANIFESTS = (
    Path("data/restricted/scale1b/manifests/ga_model_acquisition.json"),
    Path("data/restricted/scale1b/manifests/wave_r_model_acquisition.json"),
)
SYSTEMS = (
    "direct_long_context",
    "single_shot_rag",
    "learned_react",
    "learned_evidence_sufficiency",
)
MECHANISMS = (
    "SILENT_ROUTE_WITHHOLDING",
    "EXPLICIT_CHANNEL_OUTAGE",
)
ARMS = ("C", "B", "R", "N")
STAGED_SYSTEMS = SYSTEMS[1:]
CHECKPOINT_ACTION_INDEX = 4
CHECKPOINT_EVENT = {
    "event_type": "protocol_checkpoint",
    "event_version": "2.0.0",
    "message": "Scheduled protocol checkpoint completed.",
    "cost": 0.0,
}
FIXED_BUDGET = {
    "max_steps": 10,
    "cost_limit": 12.0,
    "tool_costs": {
        "search_visual": 1.0,
        "search_speech": 1.0,
        "search_ambient_audio": 1.0,
        "inspect_clip": 2.0,
        "read_transcript": 1.0,
        "get_channel_status": 0.25,
        "finalize": 0.0,
    },
    "generation": {
        "input_context_token_cap": 24576,
        "max_new_tokens": 512,
        "repair_attempts": 1,
        "repair_max_new_tokens": 512,
        "do_sample": False,
    },
}
REQUIRED_OUTPUTS = (
    "run_manifest.json",
    "assignments.jsonl",
    "raw_trajectories.jsonl",
    "raw_model_calls.jsonl",
    "factor_model_raw_outputs.jsonl",
    "citation_outputs.jsonl",
    "r_n_prefix_pairs.jsonl",
    "episode_metrics.jsonl",
    "metric_ready_records.jsonl",
    "failure_ledger.jsonl",
    "aggregate_metrics.json",
    "replay_manifest.json",
    "file_inventory.json",
)
TOKEN_RE = re.compile(r"[a-z0-9]+")


class RehearsalError(RuntimeError):
    """Typed fail-closed runner error."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class ModelLike(Protocol):
    def generate(
        self,
        *,
        system: str,
        payload: Mapping[str, Any],
        max_new_tokens: int,
    ) -> dict[str, Any]: ...


class BackendLike(Protocol):
    budget: Mapping[str, Any]
    costs: Mapping[str, float]
    events: list[dict[str, Any]]
    steps_used: int
    cost_used: float
    observation_private: Mapping[str, Mapping[str, Any]]
    evidence_by_observation: Mapping[str, Sequence[str]]

    def public_start(self) -> dict[str, Any]: ...

    def search(
        self, modality: str, query: str, top_k: int
    ) -> dict[str, Any]: ...

    def observe(self, pointer_id: str) -> dict[str, Any]: ...

    def status(self, modalities: Sequence[str]) -> dict[str, Any]: ...

    def snapshot(self) -> dict[str, Any]: ...

    def finalize(self, final: Mapping[str, Any]) -> dict[str, Any]: ...

    def apply_exogenous_restoration(self) -> None: ...

    def pack_accessible_observations(
        self, token_cap: int
    ) -> list[dict[str, Any]]: ...

    def clone(self) -> BackendLike: ...


class P23FullTimelineBackendAdapter(FullTimelineBackend):
    """Mechanical P23 adapter for the existing FullTimelineBackend contract.

    The P23 index contains learned visual/audio vectors and inventory-only ASR,
    but no human-valid semantic visual/audio descriptions. This adapter can
    therefore validate routing, suppression, restoration, budgets, pointers,
    observations, and citation plumbing. It cannot establish semantic answer
    competence; the attestation consequently keeps live execution disabled.
    """

    def __init__(
        self,
        root: Path,
        *,
        family: Mapping[str, Any],
        evidence_rows: Sequence[Mapping[str, Any]],
        intervention: Mapping[str, Any],
        mechanism: str,
        arm: str,
        feature_models: LearnedFeatureModels | None = None,
    ) -> None:
        self.root = root
        self.family = dict(family)
        self.intervention = dict(intervention)
        self.mechanism = mechanism
        self.arm = arm
        self.state = {
            "C": "CLEAN",
            "B": "BLOCKED",
            "R": "RESTORED",
            "N": "NO_TRIGGER",
        }[arm]
        self.scale_index = _load(root / INDEX_REL / "full_timeline_index.json")
        self.segment_manifest = _load(
            root / INDEX_REL / "segment_manifest.json"
        )
        self.evidence_rows = [dict(row) for row in evidence_rows]
        self.feature_models = feature_models
        self.budget = {
            "max_steps": FIXED_BUDGET["max_steps"],
            "cost_limit": FIXED_BUDGET["cost_limit"],
        }
        self.costs = dict(FIXED_BUDGET["tool_costs"])
        self.steps_used = 0
        self.cost_used = 0.0
        self.triggered = False
        self.events: list[dict[str, Any]] = []
        self.pointer_private: dict[str, dict[str, Any]] = {}
        self.observation_private: dict[str, dict[str, Any]] = {}
        self.evidence_by_observation: dict[str, list[str]] = {}
        self.final_decision_snapshot: dict[str, Any] | None = None
        self.support_by_modality: dict[str, set[str]] = defaultdict(set)
        self.evidence_handles_by_record: dict[str, list[str]] = defaultdict(
            list
        )
        for row in self.evidence_rows:
            modality = self._public_modality(str(row["modality"]))
            record_id = str(row["record_id"])
            self.support_by_modality[modality].add(record_id)
            self.evidence_handles_by_record[record_id].append(
                str(row["evidence_handle_id"])
            )
        self.suppressed = (
            {
                str(item)
                for item in intervention["suppressed_segment_ids"]
            }
            if arm in {"B", "R", "N"}
            else set()
        )
        self.explicit_outage = mechanism == "EXPLICIT_CHANNEL_OUTAGE"
        self.video_duration_s = (
            float(self.segment_manifest["duration_us"]) / 1_000_000
        )

    @staticmethod
    def _public_modality(value: str) -> str:
        return {
            "ambient_audio": "ambient",
            "audio": "ambient",
            "siglip2_visual": "vision",
            "clap_audio": "ambient",
        }.get(value, value)

    @staticmethod
    def _index_modality(value: str) -> str:
        return {
            "vision": "siglip2_visual",
            "ambient": "clap_audio",
            "speech": "speech",
        }[value]

    def clone(self) -> P23FullTimelineBackendAdapter:
        return copy.deepcopy(self)

    def apply_exogenous_restoration(self) -> None:
        """Apply evaluator-private restoration only when called by the runner."""

        self.suppressed.clear()
        self.triggered = True

    def pack_accessible_observations(
        self, token_cap: int
    ) -> list[dict[str, Any]]:
        """Pack all route-accessible evidence without exposing private state.

        This is the deterministic direct-long-context adapter. It performs no
        learned retrieval and charges no tool action. Evidence is ordered by
        source chronology and then by a frozen modality round-robin tie-break.
        """

        modality_rank = {"vision": 0, "speech": 1, "ambient": 2}
        rows = sorted(
            self.evidence_rows,
            key=lambda row: (
                int(row["start_us"]),
                int(row["end_us"]),
                modality_rank[
                    self._public_modality(str(row["modality"]))
                ],
                str(row["evidence_handle_id"]),
            ),
        )
        documents: dict[tuple[str, str], Mapping[str, Any]] = {}
        for public_modality in ("vision", "speech", "ambient"):
            index_modality = self._index_modality(public_modality)
            for document in self.scale_index["modalities"][
                index_modality
            ]["documents"]:
                record_id = str(
                    document.get("chunk_id")
                    or document.get("segment_id")
                )
                documents[(public_modality, record_id)] = document
        packed: list[dict[str, Any]] = []
        used_tokens = 0
        by_observation: dict[str, dict[str, Any]] = {}
        for row in rows:
            record_id = str(row["record_id"])
            if record_id in self.suppressed:
                continue
            modality = self._public_modality(str(row["modality"]))
            document = documents.get((modality, record_id), {})
            content = (
                str(document.get("text", ""))
                if modality == "speech"
                else (
                    "Source-derived interval acquired. The current frozen "
                    "P23 index has no human-valid semantic text for this "
                    f"{modality} observation."
                )
            )
            observation_id = (
                "p23obs."
                + hashlib.sha256(
                    f"{modality}:{record_id}".encode()
                ).hexdigest()[:24]
            )
            estimated_tokens = max(1, len(TOKEN_RE.findall(content.casefold())))
            if observation_id not in by_observation:
                if used_tokens + estimated_tokens > token_cap:
                    continue
                observation = {
                    "observation_id": observation_id,
                    "modality": modality,
                    "interval": {
                        "start_s": round(int(row["start_us"]) / 1e6, 6),
                        "end_s": round(int(row["end_us"]) / 1e6, 6),
                    },
                    "content": content,
                    "citable": True,
                    "perception_source": (
                        "inventory_only_asr"
                        if modality == "speech"
                        else (
                            "source_derived_interval_without_"
                            "semantic_caption"
                        )
                    ),
                    "payload_sha256": semantic_hash(
                        {
                            "record_id": record_id,
                            "content": content,
                        }
                    ),
                }
                used_tokens += estimated_tokens
                by_observation[observation_id] = observation
                packed.append(observation)
                self.observation_private[observation_id] = {
                    **observation,
                    "record_id": record_id,
                    "pointer_id": None,
                }
            self.evidence_by_observation.setdefault(
                observation_id, []
            ).append(str(row["evidence_handle_id"]))
        for observation_id in self.evidence_by_observation:
            self.evidence_by_observation[observation_id] = sorted(
                set(self.evidence_by_observation[observation_id])
            )
        return packed

    def public_start(self) -> dict[str, Any]:
        claim_slots = [
            {
                "claim_handle": str(row["public_claim_handle"]),
                "description": str(row["template"]),
            }
            for row in self.family["atomic_claim_templates"]
        ]
        return {
            "question": str(self.family["question_template"]),
            "claim_slots": claim_slots,
            "available_tools": [
                "search_visual",
                "search_speech",
                "search_ambient_audio",
                "inspect_clip",
                "read_transcript",
                "get_channel_status",
                "finalize",
            ],
            "budget": dict(self.budget),
            "tool_costs": dict(self.costs),
            "remaining_steps": self.budget["max_steps"],
            "remaining_cost": self.budget["cost_limit"],
            "video_duration_s": self.video_duration_s,
        }

    def _charge(self, tool: str) -> None:
        if self.steps_used + 1 > self.budget["max_steps"]:
            raise RuntimeError("OVER_BUDGET_STEPS")
        cost = float(self.costs[tool])
        if self.cost_used + cost > self.budget["cost_limit"] + 1e-9:
            raise RuntimeError("OVER_BUDGET_COST")
        self.steps_used += 1
        self.cost_used += cost

    def _typed_outage(self, modality: str) -> dict[str, Any] | None:
        affected = {
            self._public_modality(str(item))
            for item in self.intervention.get("affected_modalities", [])
        }
        if (
            self.explicit_outage
            and self.suppressed
            and modality in affected
        ):
            response = dict(self.intervention["typed_error_response"])
            return {
                "status": response["status"],
                "error": {
                    "code": response["error_code"],
                    "message": response["message"],
                    "retryable": response["retryable"],
                },
            }
        return None

    def _rank_speech(
        self, query: str, top_k: int
    ) -> list[dict[str, Any]]:
        modality = self.scale_index["modalities"]["speech"]
        documents = modality["documents"]
        count = len(documents)
        average = float(modality["average_document_length"]) or 1.0
        query_tokens = set(TOKEN_RE.findall(query.casefold()))
        output: list[dict[str, Any]] = []
        for document in documents:
            if not document.get("searchable"):
                continue
            score = 0.0
            for token in query_tokens:
                frequency = int(
                    document["term_frequency"].get(token, 0)
                )
                if not frequency:
                    continue
                document_frequency = int(
                    modality["document_frequency"].get(token, 0)
                )
                inverse = math.log(
                    1
                    + (
                        count
                        - document_frequency
                        + 0.5
                    )
                    / (document_frequency + 0.5)
                )
                denominator = frequency + 1.2 * (
                    0.25
                    + 0.75
                    * int(document["document_length"])
                    / average
                )
                score += inverse * frequency * 2.2 / denominator
            if score:
                output.append(
                    {
                        "record_id": str(document["chunk_id"]),
                        "start_us": int(document["start_us"]),
                        "end_us": int(document["end_us"]),
                        "score": score,
                        "document": document,
                    }
                )
        output.sort(
            key=lambda row: (-float(row["score"]), row["record_id"])
        )
        return output[:top_k]

    def _rank_vector(
        self, modality: str, query: str, top_k: int
    ) -> list[dict[str, Any]]:
        if self.feature_models is None:
            self.feature_models = LearnedFeatureModels(self.root)
        if modality == "vision":
            query_vector = self.feature_models.visual(query)
        else:
            query_vector = self.feature_models.ambient(query)
        documents = self.scale_index["modalities"][
            self._index_modality(modality)
        ]["documents"]
        rows = []
        for document in documents:
            record_id = str(document["segment_id"])
            if (
                record_id in self.suppressed
                or not document.get("searchable", True)
            ):
                continue
            vector = np.frombuffer(
                bytes.fromhex(document["vector_f16_hex"]),
                dtype="<f2",
            ).astype(np.float32)
            score = float(
                np.dot(vector, query_vector.astype(np.float32))
            )
            rows.append(
                {
                    "record_id": record_id,
                    "start_us": int(document["start_us"]),
                    "end_us": int(document["end_us"]),
                    "score": score,
                    "document": document,
                }
            )
        rows.sort(
            key=lambda row: (-float(row["score"]), row["record_id"])
        )
        return rows[:top_k]

    def search(
        self, modality: str, query: str, top_k: int
    ) -> dict[str, Any]:
        tool = {
            "vision": "search_visual",
            "speech": "search_speech",
            "ambient": "search_ambient_audio",
        }[modality]
        self._charge(tool)
        outage = self._typed_outage(modality)
        if outage is not None:
            response = outage
        else:
            ranking = (
                self._rank_speech(query, top_k)
                if modality == "speech"
                else self._rank_vector(modality, query, top_k)
            )
            results = []
            for rank, row in enumerate(ranking, 1):
                record_id = str(row["record_id"])
                pointer_id = (
                    "p23ptr."
                    + hashlib.sha256(
                        f"{modality}:{record_id}".encode()
                    ).hexdigest()[:24]
                )
                private = {
                    **row,
                    "modality": modality,
                    "rank": rank,
                    "interval": {
                        "start_s": round(
                            int(row["start_us"]) / 1e6, 6
                        ),
                        "end_s": round(
                            int(row["end_us"]) / 1e6, 6
                        ),
                    },
                }
                self.pointer_private[pointer_id] = private
                results.append(
                    {
                        "pointer_id": pointer_id,
                        "modality": modality,
                        "interval": private["interval"],
                        "preview": (
                            f"{modality} evidence candidate"
                        ),
                        "score": round(float(row["score"]), 8),
                    }
                )
            response = {
                "status": "ok" if results else "not_found",
                "results": results,
            }
        self.events.append(
            {
                "tool": tool,
                "request": {"query": query, "top_k": top_k},
                "response": response,
            }
        )
        return response

    def status(
        self, modalities: Sequence[str]
    ) -> dict[str, Any]:
        self._charge("get_channel_status")
        channels = {}
        for modality in modalities:
            affected = bool(
                self.suppressed
                & self.support_by_modality.get(modality, set())
            )
            channels[modality] = {
                "status": (
                    "unavailable" if affected else "available"
                ),
                # Retryability is a public property of the registered outage,
                # not an arm label. B/R/N must be indistinguishable before the
                # checkpoint.
                "retryable": affected,
            }
        response = {"status": "ok", "channels": channels}
        self.events.append(
            {
                "tool": "get_channel_status",
                "request": {"modalities": list(modalities)},
                "response": response,
            }
        )
        return response

    def observe(self, pointer_id: str) -> dict[str, Any]:
        pointer = self.pointer_private.get(pointer_id)
        if pointer is None:
            return {
                "status": "not_found",
                "error": {
                    "code": "UNKNOWN_POINTER",
                    "retryable": False,
                },
            }
        modality = str(pointer["modality"])
        tool = (
            "read_transcript"
            if modality == "speech"
            else "inspect_clip"
        )
        self._charge(tool)
        record_id = str(pointer["record_id"])
        if record_id in self.suppressed:
            response = (
                self._typed_outage(modality)
                or {
                    "status": "access_failure",
                    "error": {
                        "code": "ROUTE_INACCESSIBLE",
                        "retryable": True,
                    },
                }
            )
            self.events.append(
                {
                    "tool": tool,
                    "request": {"pointer_id": pointer_id},
                    "response": response,
                }
            )
            return response
        document = pointer["document"]
        content = (
            str(document.get("text", ""))
            if modality == "speech"
            else (
                "Source-derived interval acquired. The current frozen "
                "P23 index has no human-valid semantic text for this "
                f"{modality} observation."
            )
        )
        observation_id = (
            "p23obs."
            + hashlib.sha256(
                f"{modality}:{record_id}".encode()
            ).hexdigest()[:24]
        )
        observation = {
            "observation_id": observation_id,
            "modality": modality,
            "interval": dict(pointer["interval"]),
            "content": content,
            "citable": True,
            "perception_source": (
                "inventory_only_asr"
                if modality == "speech"
                else "source_derived_interval_without_semantic_caption"
            ),
            "payload_sha256": semantic_hash(
                {
                    "record_id": record_id,
                    "interval": pointer["interval"],
                    "content": content,
                }
            ),
        }
        self.observation_private[observation_id] = {
            **observation,
            "record_id": record_id,
            "pointer_id": pointer_id,
        }
        self.evidence_by_observation[observation_id] = sorted(
            self.evidence_handles_by_record.get(record_id, [])
        )
        response = {
            "status": "ok",
            "observation": observation,
        }
        self.events.append(
            {
                "tool": tool,
                "request": {"pointer_id": pointer_id},
                "response": response,
            }
        )
        return response

    def snapshot(self) -> dict[str, Any]:
        return {
            "remaining_steps": (
                self.budget["max_steps"] - self.steps_used
            ),
            "remaining_cost": round(
                self.budget["cost_limit"] - self.cost_used, 6
            ),
            "triggered": self.triggered,
            "suppressed_segment_ids": sorted(self.suppressed),
            "known_pointer_ids": sorted(self.pointer_private),
            "known_observation_ids": sorted(
                self.observation_private
            ),
        }

    def finalize(
        self, final: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.final_decision_snapshot = self.snapshot()
        self._charge("finalize")
        response = {
            "status": "finalized",
            "verdict": final.get("verdict"),
        }
        self.events.append(
            {
                "tool": "finalize",
                "request": {},
                "response": response,
            }
        )
        return response


@dataclass(frozen=True)
class FrozenInputs:
    config: dict[str, Any]
    attestation: dict[str, Any]
    families: dict[str, Any]
    evidence: dict[str, Any]
    interventions: dict[str, Any]
    surfaces: dict[str, Any]
    source_split: dict[str, Any]
    leakage: dict[str, Any]
    index: dict[str, Any]
    segment_manifest: dict[str, Any]


@dataclass
class PrefixState:
    backend: BackendLike
    start: dict[str, Any]
    pointers: dict[str, dict[str, Any]]
    observations: dict[str, dict[str, Any]]
    events: list[dict[str, Any]]
    model_calls: list[dict[str, Any]]
    factor_outputs: list[dict[str, Any]]
    no_progress_rounds: int = 0
    rag_selected_pointer_ids: list[str] | None = None
    terminal: bool = False
    final: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RehearsalError("INVALID_SCHEMA", f"{path} is not an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _atomic_write(path: Path, value: Any, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    payload = json.dumps(
        value,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    ).encode() + b"\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_jsonl(
    path: Path, rows: Sequence[Mapping[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for row in rows:
                handle.write(canonical_bytes(dict(row)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _require(
    condition: bool, code: str, errors: list[str]
) -> None:
    if not condition:
        errors.append(code)


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _load_inputs(root: Path) -> FrozenInputs:
    return FrozenInputs(
        config=_load(root / CONFIG_REL),
        attestation=_load(root / ATTESTATION_REL),
        families=_load(root / BUNDLE_REL / "family_registry.json"),
        evidence=_load(root / BUNDLE_REL / "evidence_registry.json"),
        interventions=_load(root / BUNDLE_REL / "intervention_manifest.json"),
        surfaces=_load(root / BUNDLE_REL / "state_surface_manifest.json"),
        source_split=_load(root / BUNDLE_REL / "source_split_manifest.json"),
        leakage=_load(root / BUNDLE_REL / "leakage_gate.json"),
        index=_load(root / INDEX_REL / "full_timeline_index.json"),
        segment_manifest=_load(root / INDEX_REL / "segment_manifest.json"),
    )


def _attested_hash(
    root: Path,
    attestation: Mapping[str, Any],
    relative: str,
    errors: list[str],
) -> None:
    path = root / relative
    record = next(
        (
            row
            for row in attestation.get("artifacts", [])
            if row.get("path") == relative
        ),
        None,
    )
    _require(record is not None, f"ATTESTATION_ENTRY_MISSING:{relative}", errors)
    if record is not None:
        _require(path.is_file(), f"ATTESTED_FILE_MISSING:{relative}", errors)
        if path.is_file():
            _require(
                _sha256(path) == record.get("sha256"),
                f"ATTESTED_HASH_MISMATCH:{relative}",
                errors,
            )


def validate_repository(
    repo_root: str | Path = ".",
) -> dict[str, Any]:
    """Validate frozen artifacts without model loading or media decoding."""

    root = Path(repo_root).resolve()
    required = [
        CONFIG_REL,
        ATTESTATION_REL,
        SOURCE_MANIFEST_REL,
        MODEL_COMPETENCE_REL,
        *MODEL_MANIFESTS,
        *(
            BUNDLE_REL / name
            for name in (
                "family_registry.json",
                "evidence_registry.json",
                "intervention_manifest.json",
                "state_surface_manifest.json",
                "source_split_manifest.json",
                "leakage_gate.json",
            )
        ),
        *(
            INDEX_REL / name
            for name in (
                "build_manifest.json",
                "full_timeline_index.json",
                "observation_manifest.json",
                "resource_manifest.json",
                "segment_manifest.json",
            )
        ),
    ]
    errors: list[str] = []
    missing = [str(path) for path in required if not (root / path).is_file()]
    if missing:
        return {
            "schema_version": SCHEMA,
            "mode": "validate-only",
            "validation_status": "NOT_READY",
            "execution_authorized": False,
            "errors": ["PREREQUISITE_MISSING"],
            "missing": missing,
            "model_or_media_execution_performed": False,
        }
    inputs = _load_inputs(root)
    config = inputs.config
    _require(
        [row["system_id"] for row in config["matrix"]["system_rows"]]
        == list(SYSTEMS),
        "INVALID_SYSTEM_ROWS",
        errors,
    )
    _require(
        [row["arm"] for row in config["arms"]] == list(ARMS),
        "INVALID_ARM_ROWS",
        errors,
    )
    _require(
        [row["mechanism"] for row in config["mechanisms"]]
        == list(MECHANISMS),
        "INVALID_MECHANISM_ROWS",
        errors,
    )
    restoration = config["restoration_v2"]
    _require(
        restoration["fixed_action_index"] == CHECKPOINT_ACTION_INDEX,
        "INVALID_RESTORATION_SCHEDULE",
        errors,
    )
    _require(
        restoration["checkpoint_event"] == CHECKPOINT_EVENT,
        "INVALID_CHECKPOINT_EVENT_MISMATCH",
        errors,
    )
    _require(
        config["budgets"]["agentic_and_rag"]["max_steps"]
        == FIXED_BUDGET["max_steps"]
        and config["budgets"]["agentic_and_rag"]["cost_limit"]
        == FIXED_BUDGET["cost_limit"]
        and config["budgets"]["agentic_and_rag"]["tool_costs"]
        == FIXED_BUDGET["tool_costs"]
        and config["budgets"]["generation"]
        == FIXED_BUDGET["generation"],
        "INVALID_BUDGET",
        errors,
    )
    _require(
        inputs.families.get("status") == "MACHINE_PROVISIONAL_FROZEN",
        "FAMILY_REGISTRY_NOT_READY",
        errors,
    )
    _require(
        inputs.interventions.get("status") == "MECHANISM_SPECIFIC_FROZEN",
        "INTERVENTION_NOT_READY",
        errors,
    )
    _require(
        inputs.surfaces.get("status") == "FROZEN",
        "STATE_SURFACE_NOT_READY",
        errors,
    )
    _require(
        inputs.source_split.get("status")
        == "P23_DEVELOPMENT_ONLY_SOURCE_DISJOINT_FROM_EVALUATION",
        "SOURCE_DISJOINTNESS_VIOLATION",
        errors,
    )
    _require(
        inputs.leakage.get("status") == "PASS",
        "LEAKAGE_GATE_NOT_RUN",
        errors,
    )
    _require(
        inputs.index.get("source_ref") == "P23_102",
        "INDEX_NOT_READY",
        errors,
    )
    _require(
        inputs.segment_manifest.get("source_sha256")
        == inputs.families.get("source_sha256"),
        "SOURCE_BINDING_MISMATCH",
        errors,
    )
    family_ids = {
        str(row["family_id"]) for row in inputs.families["families"]
    }
    intervention_pairs = {
        (str(row["family_id"]), str(row["mechanism"]))
        for row in inputs.interventions["interventions"]
    }
    surface_slots = {
        (
            str(row["family_id"]),
            str(row["mechanism"]),
            str(row["arm"]),
        )
        for row in inputs.surfaces["surfaces"]
    }
    _require(
        intervention_pairs
        == {
            (family, mechanism)
            for family in family_ids
            for mechanism in MECHANISMS
        },
        "INTERVENTION_MATRIX_MISMATCH",
        errors,
    )
    _require(
        surface_slots
        == {
            (family, mechanism, arm)
            for family in family_ids
            for mechanism in MECHANISMS
            for arm in ARMS
        },
        "STATE_SURFACE_MATRIX_MISMATCH",
        errors,
    )
    attestation = inputs.attestation
    attestation_drift: list[dict[str, str]] = []
    _require(
        attestation.get("status")
        == "EXOGENOUS_RESTORATION_V2_ADAPTER_READY",
        "ADAPTER_ATTESTATION_NOT_READY",
        errors,
    )
    for record in attestation.get("artifacts", []):
        relative = str(record["path"])
        path = root / relative
        _require(
            path.is_file(), f"ATTESTED_FILE_MISSING:{relative}", errors
        )
        if path.is_file():
            actual = _sha256(path)
            if actual != record["sha256"]:
                # Concurrent controller/process repairs and this runner repair
                # intentionally invalidate the old execution attestation.
                # Static protocol validation/planning remains available, but
                # execution authorization cannot inherit stale hashes.
                attestation_drift.append(
                    {
                        "path": relative,
                        "expected_sha256": str(record["sha256"]),
                        "actual_sha256": actual,
                    }
                )
    runner_path = root / (
        "scripts/run_p23_102_acquire_ground_act_rehearsal.py"
    )
    runner_expected = attestation.get("runner", {}).get("sha256")
    runner_actual = _sha256(runner_path)
    runner_attested = (
        runner_expected is None or runner_actual == runner_expected
    )
    competence = _load(root / MODEL_COMPETENCE_REL)
    agent_decision = competence.get("decisions", {}).get("agent")
    all_accepted = bool(inputs.families["families"]) and all(
        row.get("accepted_family") is True
        and row.get("accepted_ses") is True
        for row in inputs.families["families"]
    )
    execute_reasons: list[str] = []
    if agent_decision != "LEARNED_AGENT_READY":
        execute_reasons.append("QWEN15_AGENT_COMPETENCE_NOT_READY")
    if not all_accepted:
        execute_reasons.append(
            "BUNDLE_SEMANTICS_MACHINE_PROVISIONAL_NOT_ACCEPTED_SES"
        )
    if any(
        row.get("gate_a_credit") is not True
        for row in inputs.families["families"]
    ):
        execute_reasons.append("GATE_A_NOT_ESTABLISHED")
    if any(
        row.get("human_prescreen") != "PASS"
        for row in inputs.families["families"]
    ):
        execute_reasons.append("HUMAN_FAMILY_VALIDITY_NOT_ESTABLISHED")
    if not runner_attested:
        execute_reasons.append("RUNNER_REPAIR_NOT_ATTESTED")
    if attestation_drift:
        execute_reasons.append("ADAPTER_COMPONENT_REPAIR_NOT_ATTESTED")
    execute_authorized = not errors and not execute_reasons
    return {
        "schema_version": SCHEMA,
        "mode": "validate-only",
        "validation_status": "READY" if not errors else "NOT_READY",
        "execution_authorized": execute_authorized,
        "execution_authorization_reasons": execute_reasons,
        "errors": errors,
        "family_count": len(family_ids),
        "planned_assignment_count": (
            len(family_ids) * len(MECHANISMS) * len(SYSTEMS) * len(ARMS)
        ),
        "adapter_competence": attestation.get("competence"),
        "qwen_agent_competence": agent_decision,
        "bundle_semantics": (
            "MACHINE_PROVISIONAL_NOT_HUMAN_VALIDATED"
        ),
        "bundle_provenance_firewall": {
            "status": inputs.leakage.get("status"),
            "scope": "bundle_construction_inputs_and_claim_firewall",
            "runtime_classifier_executed": False,
        },
        "runtime_leakage_classifier": {
            "status": "NOT_RUN_EXECUTION_UNAUTHORIZED",
            "distinct_from_bundle_provenance_firewall": True,
        },
        "runner_attestation": {
            "status": (
                "MATCHED" if runner_attested else "REPAIR_NOT_ATTESTED"
            ),
            "expected_sha256": runner_expected,
            "actual_sha256": runner_actual,
        },
        "adapter_attestation_drift": attestation_drift,
        "claims": {
            "strong_competence": False,
            "h2": False,
            "human_family_validity": False,
            "causal_result": False,
            "gate_a": False,
        },
        "model_or_media_execution_performed": False,
        "validated_artifacts": [
            _artifact(root / path, root) for path in required
        ],
    }


def _balanced_sequence_map(
    keys: Sequence[str], config: Mapping[str, Any]
) -> dict[str, list[str]]:
    """Allocate Williams sequences exactly evenly over the 160 cells."""

    sequences = [
        str(value).split("-")
        for value in config["matrix"]["counterbalanced_order_sequences"]
    ]
    seed = int(config["matrix"]["assignment_seed"])
    ordered = sorted(
        keys,
        key=lambda key: (
            hashlib.sha256(f"{seed}:{key}".encode()).hexdigest(),
            key,
        ),
    )
    if len(ordered) % len(sequences):
        raise RehearsalError(
            "UNBALANCED_WILLIAMS_CELL_COUNT", str(len(ordered))
        )
    return {
        key: sequences[index % len(sequences)]
        for index, key in enumerate(ordered)
    }


def build_plan(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    validation = validate_repository(root)
    if validation["validation_status"] != "READY":
        raise RehearsalError(
            "VALIDATION_NOT_READY", ",".join(validation["errors"])
        )
    inputs = _load_inputs(root)
    assignments: list[dict[str, Any]] = []
    ordinal = 0
    families = sorted(
        inputs.families["families"],
        key=lambda row: (row["rank"], row["family_id"]),
    )
    cell_keys = [
        f"P23:{family['family_id']}:{mechanism}:{system}"
        for family in families
        for mechanism in MECHANISMS
        for system in SYSTEMS
    ]
    sequence_by_key = _balanced_sequence_map(
        cell_keys, inputs.config
    )
    for family in families:
        for mechanism in MECHANISMS:
            for system in SYSTEMS:
                key = (
                    f"P23:{family['family_id']}:{mechanism}:{system}"
                )
                sequence = sequence_by_key[key]
                for order_index, arm in enumerate(sequence):
                    ordinal += 1
                    structural = (
                        system == "direct_long_context"
                        and arm in {"R", "N"}
                    )
                    assignment_id = (
                        "p23a."
                        + hashlib.sha256(
                            f"{key}:{arm}".encode()
                        ).hexdigest()[:24]
                    )
                    assignments.append(
                        {
                            "assignment_id": assignment_id,
                            "ordinal": ordinal,
                            "source_group_id": "P23",
                            "source_id": "P23_102",
                            "family_id": family["family_id"],
                            "family_rank": family["rank"],
                            "mechanism": mechanism,
                            "system_id": system,
                            "arm": arm,
                            "order_sequence": sequence,
                            "order_sequence_id": (
                                "-".join(sequence)
                            ),
                            "order_index": order_index,
                            "fixed_budget": FIXED_BUDGET,
                            "checkpoint_action_index_zero_based": (
                                CHECKPOINT_ACTION_INDEX
                            ),
                            "assignment_status": (
                                "STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT"
                                if structural
                                else "ASSIGNED_ITT"
                            ),
                            "itt_retained": not structural,
                            "synthetic_outcome_created": False,
                            "expected_evidence_handle_ids": sorted(
                                str(value)
                                for value in family[
                                    "evidence_handle_ids"
                                ]
                            ),
                        }
                    )
    return {
        "schema_version": SCHEMA,
        "mode": "plan",
        "status": "PLAN_READY",
        "development_only": True,
        "execution_authorized": validation["execution_authorized"],
        "execution_authorization_reasons": validation[
            "execution_authorization_reasons"
        ],
        "assignment_count": len(assignments),
        "assignments": assignments,
        "plan_hash": semantic_hash(assignments),
        "model_or_media_execution_performed": False,
    }


def _typed_failure(
    code: str,
    *,
    phase: str,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "phase": phase,
        "detail": detail,
        "positive_endpoint": 0.0,
    }


def _execute_action(
    backend: BackendLike, action: Mapping[str, Any]
) -> dict[str, Any]:
    kind = action["type"]
    if kind == "search":
        return backend.search(
            str(action["modality"]),
            str(action["query"]),
            int(action.get("top_k", 5)),
        )
    if kind == "observe":
        return backend.observe(str(action["pointer_id"]))
    if kind == "status":
        return backend.status(
            [str(item) for item in action["modalities"]]
        )
    raise RehearsalError(
        "INVALID_SCHEMA", f"unsupported action {kind}"
    )


def _pack_direct_long_context(state: PrefixState) -> None:
    packer = getattr(
        state.backend, "pack_accessible_observations", None
    )
    if not callable(packer):
        state.failure = _typed_failure(
            "DIRECT_CONTEXT_ADAPTER_NOT_CONFIGURED",
            phase="direct_long_context",
        )
        return
    try:
        observations = packer(
            int(
                FIXED_BUDGET["generation"][
                    "input_context_token_cap"
                ]
            )
        )
        for observation in observations:
            public = _sanitize_public_response(
                {"observation": observation}
            )["observation"]
            state.observations[
                str(public["observation_id"])
            ] = dict(public)
        state.factor_outputs.append(
            {
                "phase": "direct_long_context_packing",
                "packing_order": (
                    "chronological_then_modality_round_robin"
                ),
                "input_context_token_cap": FIXED_BUDGET[
                    "generation"
                ]["input_context_token_cap"],
                "packed_observation_ids": list(
                    state.observations
                ),
            }
        )
    except (
        RehearsalError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
    ) as exc:
        state.failure = _typed_failure(
            str(
                getattr(
                    exc,
                    "code",
                    "DIRECT_CONTEXT_PACKING_FAILURE",
                )
            ),
            phase="direct_long_context",
            detail=str(exc),
        )


def _public_budget_snapshot(
    backend: BackendLike,
) -> dict[str, Any]:
    """Return only the model-visible budget ledger."""

    snapshot = backend.snapshot()
    return {
        "remaining_steps": int(snapshot["remaining_steps"]),
        "remaining_cost": float(snapshot["remaining_cost"]),
    }


def _sanitize_public_response(
    response: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove evaluator-private state and normalize blocked-state status."""

    public = copy.deepcopy(dict(response))
    public.pop("triggered", None)
    public.pop("suppressed_segment_ids", None)
    public.pop("known_pointer_ids", None)
    public.pop("known_observation_ids", None)
    error = public.get("error")
    if isinstance(error, dict) and public.get("status") in {
        "unavailable",
        "access_failure",
    }:
        error["retryable"] = True
    channels = public.get("channels")
    if isinstance(channels, dict):
        for channel in channels.values():
            if (
                isinstance(channel, dict)
                and channel.get("status") == "unavailable"
            ):
                channel["retryable"] = True
    return public


def _record_event(
    state: PrefixState,
    action: Mapping[str, Any],
    response: Mapping[str, Any],
    *,
    public_state: Mapping[str, Any] | None = None,
) -> None:
    public_response = _sanitize_public_response(response)
    event = {
        "action_index": _completed_action_count(state.events),
        "action": dict(action),
        "response": public_response,
        "public_state": dict(public_state or {}),
        "remaining_budget": _public_budget_snapshot(state.backend),
    }
    state.events.append(event)
    for item in public_response.get("results", []):
        if "pointer_id" in item:
            state.pointers[str(item["pointer_id"])] = dict(item)
        for modality, pointer_id in item.get(
            "modality_pointers", {}
        ).items():
            state.pointers[str(pointer_id)] = {
                "pointer_id": str(pointer_id),
                "modality": str(modality),
                "preview": "fused evidence candidate",
            }
    observation = public_response.get("observation")
    if isinstance(observation, Mapping):
        public = dict(observation)
        public["source_pointer_id"] = action.get("pointer_id")
        state.observations[str(public["observation_id"])] = public


def _completed_action_count(
    events: Sequence[Mapping[str, Any]],
) -> int:
    return sum(
        1
        for event in events
        if isinstance(event.get("action"), Mapping)
    )


def _retain_exception_attempts(
    state: PrefixState,
    exc: BaseException,
    *,
    phase: str,
) -> None:
    """Retain malformed/process raw attempts carried by controller errors."""

    details = getattr(exc, "details", None)
    attempts: list[dict[str, Any]] = []
    if isinstance(details, Mapping):
        attempts.extend(
            dict(row)
            for row in details.get("attempts", [])
            if isinstance(row, Mapping)
        )
    attached = getattr(exc, "attempts", None)
    if isinstance(attached, Sequence) and not isinstance(
        attached, (str, bytes)
    ):
        attempts.extend(
            dict(row) for row in attached if isinstance(row, Mapping)
        )
    deduplicated: list[dict[str, Any]] = []
    seen_attempts: set[bytes] = set()
    for attempt in attempts:
        encoded = canonical_bytes(attempt)
        if encoded in seen_attempts:
            continue
        seen_attempts.add(encoded)
        deduplicated.append(attempt)
    attempts = deduplicated
    raw_text = getattr(exc, "raw_text", None)
    if raw_text is not None and not attempts:
        raw = str(raw_text)
        attempts.append(
            {
                "status": "exception_raw_attempt",
                "raw_text": raw,
                "raw_sha256": (
                    "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
                ),
                "error_code": str(
                    getattr(exc, "code", type(exc).__name__)
                ),
            }
        )
    if not attempts:
        return
    state.model_calls.extend(attempts)
    state.factor_outputs.append(
        {
            "phase": phase,
            "action_index": _completed_action_count(state.events),
            "status": "typed_failure",
            "error_code": str(
                getattr(exc, "code", type(exc).__name__)
            ),
            "raw_model_calls": attempts,
        }
    )


def _rrf_selected_pointer_ids(
    events: Sequence[Mapping[str, Any]],
    *,
    rrf_k: int = 60,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Freeze equal-weight RRF over the three single-shot rankings."""

    rankings: dict[str, list[Mapping[str, Any]]] = {
        "vision": [],
        "speech": [],
        "ambient": [],
    }
    for event in events:
        action = event.get("action", {})
        if action.get("type") != "search":
            continue
        modality = str(action.get("modality"))
        if modality in rankings:
            rankings[modality] = list(
                event.get("response", {}).get("results", [])
            )
    fused: dict[str, dict[str, Any]] = {}
    for modality in ("vision", "speech", "ambient"):
        for rank, pointer in enumerate(rankings[modality], 1):
            interval = pointer.get("interval")
            group_key = canonical_bytes(
                interval
                if isinstance(interval, Mapping)
                else {"pointer_id": pointer.get("pointer_id")}
            ).decode()
            row = fused.setdefault(
                group_key,
                {
                    "group_key": group_key,
                    "rrf_score": 0.0,
                    "best_rank": rank,
                    "pointers": [],
                },
            )
            row["rrf_score"] += 1.0 / (rrf_k + rank)
            row["best_rank"] = min(int(row["best_rank"]), rank)
            row["pointers"].append(
                {
                    "pointer_id": str(pointer["pointer_id"]),
                    "modality": modality,
                    "rank": rank,
                }
            )
    ordered = sorted(
        fused.values(),
        key=lambda row: (
            -float(row["rrf_score"]),
            int(row["best_rank"]),
            str(row["group_key"]),
        ),
    )
    selected: list[str] = []
    public_fusion: list[dict[str, Any]] = []
    for fused_rank, row in enumerate(ordered[:5], 1):
        constituents = sorted(
            row["pointers"],
            key=lambda item: (
                int(item["rank"]),
                ("vision", "speech", "ambient").index(
                    str(item["modality"])
                ),
                str(item["pointer_id"]),
            ),
        )
        selected.extend(
            str(item["pointer_id"]) for item in constituents
        )
        public_fusion.append(
            {
                "fused_rank": fused_rank,
                "rrf_score": round(float(row["rrf_score"]), 12),
                "constituent_pointer_ids": [
                    str(item["pointer_id"]) for item in constituents
                ],
                "modalities": sorted(
                    {str(item["modality"]) for item in constituents}
                ),
            }
        )
    return selected, public_fusion


def _safe_action(
    state: PrefixState,
    model: ModelLike | None,
    policy: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    if model is None:
        raise RehearsalError(
            "MODEL_PROCESS_CRASH", "no model supplied"
        )
    snapshot = _public_budget_snapshot(state.backend)
    observed_pointer_ids = {
        str(row.get("source_pointer_id"))
        for row in state.observations.values()
    }
    unobserved = [
        pointer_id
        for pointer_id in state.pointers
        if pointer_id not in observed_pointer_ids
    ]
    menu: list[dict[str, Any]] = []
    if state.no_progress_rounds >= 2:
        menu = [{"type": "finalize"}]
    elif unobserved:
        menu.extend(
            {"type": "observe", "pointer_id": pointer_id}
            for pointer_id in unobserved[:3]
        )
    else:
        question = state.start["question"]
        for modality in ("vision", "speech", "ambient"):
            menu.append(
                {
                    "type": "search",
                    "modality": modality,
                    "query": question,
                    "top_k": 5,
                }
            )
        menu.append(
            {
                "type": "status",
                "modalities": ["vision", "speech", "ambient"],
            }
        )
    if not menu or menu[-1].get("type") != "finalize":
        menu.append({"type": "finalize"})
    generated = run_controller_decision(
        model,
        policy=policy,
        turn=_completed_action_count(state.events),
        question=state.start["question"],
        claim_slots=state.start["claim_slots"],
        available_tools=state.start["available_tools"],
        remaining_budget={
            "steps": snapshot["remaining_steps"],
            "cost": snapshot["remaining_cost"],
            "tool_costs": state.start["tool_costs"],
        },
        known_pointers=list(state.pointers.values()),
        citable_observations=list(state.observations.values()),
        recent_public_events=state.events[-12:],
        action_menu=menu,
        no_progress_rounds=state.no_progress_rounds,
        config=GenerationConfig(),
    )
    return (
        generated["decision"]["action"],
        generated["decision"]["public_state"],
        generated["model_calls"],
    )


def run_blocked_prefix(
    backend: BackendLike,
    *,
    system_id: str,
    model: ModelLike | None = None,
    checkpoint_required: bool = True,
) -> PrefixState:
    """Run four completed cycles before the zero-based action-4 event."""

    state = PrefixState(
        backend=backend,
        start=backend.public_start(),
        pointers={},
        observations={},
        events=[],
        model_calls=[],
        factor_outputs=[],
    )
    question = state.start["question"]
    try:
        if system_id == "single_shot_rag":
            actions = [
                {
                    "type": "search",
                    "modality": "vision",
                    "query": question,
                    "top_k": 5,
                },
                {
                    "type": "search",
                    "modality": "speech",
                    "query": question,
                    "top_k": 5,
                },
                {
                    "type": "search",
                    "modality": "ambient",
                    "query": question,
                    "top_k": 5,
                },
            ]
            for action in actions:
                _record_event(
                    state,
                    action,
                    _execute_action(backend, action),
                )
            selected, fusion = _rrf_selected_pointer_ids(state.events)
            state.rag_selected_pointer_ids = selected
            state.factor_outputs.append(
                {
                    "phase": "single_shot_rag_fusion",
                    "rrf_k": 60,
                    "modality_weights": {
                        "vision": 1.0,
                        "speech": 1.0,
                        "ambient": 1.0,
                    },
                    "fused_selection": fusion,
                }
            )
            pointer = selected[0] if selected else None
            action = (
                {"type": "observe", "pointer_id": pointer}
                if pointer
                else {
                    "type": "status",
                    "modalities": ["vision", "speech", "ambient"],
                }
            )
            _record_event(
                state,
                action,
                _execute_action(backend, action),
            )
        else:
            policy = (
                "react"
                if system_id == "learned_react"
                else "evidence_sufficiency"
            )
            while (
                _completed_action_count(state.events)
                < CHECKPOINT_ACTION_INDEX
            ):
                action, public_state, calls = _safe_action(
                    state, model, policy
                )
                state.model_calls.extend(calls)
                state.factor_outputs.append(
                    {
                        "phase": "controller",
                        "action_index": _completed_action_count(
                            state.events
                        ),
                        "policy": policy,
                        "public_state": public_state,
                        "raw_model_calls": calls,
                    }
                )
                if action["type"] == "finalize":
                    if checkpoint_required:
                        state.terminal = True
                        state.failure = _typed_failure(
                            "EARLY_TERMINAL_BEFORE_CHECKPOINT",
                            phase="blocked_prefix",
                        )
                    else:
                        _finalize_state(
                            state,
                            model,
                            "state_endpoint_early_finalize",
                        )
                        state.terminal = state.final is not None
                    break
                observations_before = len(state.observations)
                _record_event(
                    state,
                    action,
                    _execute_action(backend, action),
                    public_state=public_state,
                )
                state.no_progress_rounds = (
                    0
                    if len(state.observations) > observations_before
                    else state.no_progress_rounds + 1
                )
    except LearnedCallFailure as exc:
        _retain_exception_attempts(
            state, exc, phase="blocked_prefix"
        )
        state.failure = _typed_failure(
            exc.code,
            phase="blocked_prefix",
            detail=str(exc),
        )
    except RehearsalError as exc:
        state.failure = _typed_failure(
            exc.code,
            phase="blocked_prefix",
            detail=str(exc),
        )
    except RuntimeError as exc:
        code = (
            str(exc)
            if str(exc).startswith("OVER_BUDGET")
            else "TOOL_ACCESS_FAILURE"
        )
        state.failure = _typed_failure(
            code,
            phase="blocked_prefix",
            detail=str(exc),
        )
    return state


def fork_restoration_pair(
    prefix: PrefixState,
) -> tuple[PrefixState, PrefixState, dict[str, Any]]:
    """Fork R/N after a byte-identical public action-index-4 event."""

    r_state = PrefixState(
        backend=prefix.backend.clone(),
        start=copy.deepcopy(prefix.start),
        pointers=copy.deepcopy(prefix.pointers),
        observations=copy.deepcopy(prefix.observations),
        events=copy.deepcopy(prefix.events),
        model_calls=copy.deepcopy(prefix.model_calls),
        factor_outputs=copy.deepcopy(prefix.factor_outputs),
        no_progress_rounds=prefix.no_progress_rounds,
        rag_selected_pointer_ids=copy.deepcopy(
            prefix.rag_selected_pointer_ids
        ),
        terminal=prefix.terminal,
        final=copy.deepcopy(prefix.final),
        failure=copy.deepcopy(prefix.failure),
    )
    n_state = PrefixState(
        backend=prefix.backend.clone(),
        start=copy.deepcopy(prefix.start),
        pointers=copy.deepcopy(prefix.pointers),
        observations=copy.deepcopy(prefix.observations),
        events=copy.deepcopy(prefix.events),
        model_calls=copy.deepcopy(prefix.model_calls),
        factor_outputs=copy.deepcopy(prefix.factor_outputs),
        no_progress_rounds=prefix.no_progress_rounds,
        rag_selected_pointer_ids=copy.deepcopy(
            prefix.rag_selected_pointer_ids
        ),
        terminal=prefix.terminal,
        final=copy.deepcopy(prefix.final),
        failure=copy.deepcopy(prefix.failure),
    )
    restoration_applied = False
    event_opportunity_reached = (
        _completed_action_count(prefix.events)
        == CHECKPOINT_ACTION_INDEX
        and not prefix.terminal
        and prefix.failure is None
    )
    if event_opportunity_reached:
        for state in (r_state, n_state):
            state.events.append(
                {
                    "action_index": CHECKPOINT_ACTION_INDEX,
                    "event": copy.deepcopy(CHECKPOINT_EVENT),
                    "remaining_budget": _public_budget_snapshot(
                        state.backend
                    ),
                }
            )
        r_state.backend.apply_exogenous_restoration()
        restoration_applied = True
    r_prefix_bytes = canonical_bytes(
        {
            "start": r_state.start,
            "pointers": r_state.pointers,
            "observations": r_state.observations,
            "events": r_state.events,
            "no_progress_rounds": r_state.no_progress_rounds,
        }
    )
    n_prefix_bytes = canonical_bytes(
        {
            "start": n_state.start,
            "pointers": n_state.pointers,
            "observations": n_state.observations,
            "events": n_state.events,
            "no_progress_rounds": n_state.no_progress_rounds,
        }
    )
    prefix_hash_r = (
        "sha256:" + hashlib.sha256(r_prefix_bytes).hexdigest()
    )
    prefix_hash_n = (
        "sha256:" + hashlib.sha256(n_prefix_bytes).hexdigest()
    )
    pair = {
        "prefix_hash_r": prefix_hash_r,
        "prefix_hash_n": prefix_hash_n,
        "prefix_byte_length_r": len(r_prefix_bytes),
        "prefix_byte_length_n": len(n_prefix_bytes),
        "checkpoint_event_hash": semantic_hash(CHECKPOINT_EVENT),
        "prefix_identical": r_prefix_bytes == n_prefix_bytes,
        "checkpoint_identical": (
            event_opportunity_reached
            and r_state.events[-1] == n_state.events[-1]
        ),
        "checkpoint_delivered_r": event_opportunity_reached,
        "checkpoint_delivered_n": event_opportunity_reached,
        "event_opportunity_reached": event_opportunity_reached,
        "restoration_applied_r": restoration_applied,
        "restoration_applied_n": False,
        "early_terminal_copied_to_both": prefix.terminal,
        "itt_retained_r": True,
        "itt_retained_n": True,
    }
    return r_state, n_state, pair


def _finalize_state(
    state: PrefixState,
    model: ModelLike | None,
    condition: str,
) -> None:
    if state.final is not None or state.failure is not None:
        return
    if model is None:
        state.failure = _typed_failure(
            "MODEL_PROCESS_CRASH",
            phase="grounded_finalization",
        )
        return
    try:
        generated = run_grounded_generator(
            model,
            question=state.start["question"],
            claim_slots=state.start["claim_slots"],
            observations=list(state.observations.values()),
            condition=condition,
            config=GenerationConfig(),
        )
        state.model_calls.extend(generated["model_calls"])
        state.factor_outputs.append(
            {
                "phase": "grounded_finalization",
                "condition": condition,
                "raw_model_calls": generated["model_calls"],
                "validated_output": generated["final"],
            }
        )
        state.final = generated["final"]
        state.backend.finalize(state.final)
    except (
        LearnedCallFailure,
        ModelProcessError,
        PublicSchemaError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
    ) as exc:
        _retain_exception_attempts(
            state, exc, phase="grounded_finalization"
        )
        code = getattr(exc, "code", "MALFORMED_AFTER_REPAIR")
        state.failure = _typed_failure(
            str(code),
            phase="grounded_finalization",
            detail=str(exc),
        )


def _continue_state(
    state: PrefixState,
    *,
    system_id: str,
    arm: str,
    model: ModelLike | None,
) -> None:
    if state.failure or state.terminal:
        return
    if system_id == "single_shot_rag":
        observed = {
            str(row.get("source_pointer_id"))
            for row in state.observations.values()
        }
        pointer_order = (
            state.rag_selected_pointer_ids
            if state.rag_selected_pointer_ids is not None
            else list(state.pointers)
        )
        for pointer_id in pointer_order:
            if pointer_id in observed:
                continue
            try:
                action = {
                    "type": "observe",
                    "pointer_id": pointer_id,
                }
                _record_event(
                    state,
                    action,
                    _execute_action(state.backend, action),
                )
            except RuntimeError as exc:
                state.failure = _typed_failure(
                    str(exc), phase="post_checkpoint"
                )
                return
            if (
                _public_budget_snapshot(state.backend)[
                    "remaining_steps"
                ]
                <= 1
            ):
                break
        _finalize_state(
            state, model, f"{arm}:single_shot_rag"
        )
        return
    policy = (
        "react"
        if system_id == "learned_react"
        else "evidence_sufficiency"
    )
    while (
        _public_budget_snapshot(state.backend)["remaining_steps"] > 0
        and state.final is None
        and state.failure is None
    ):
        try:
            action, public_state, calls = _safe_action(
                state, model, policy
            )
            state.model_calls.extend(calls)
            state.factor_outputs.append(
                {
                    "phase": "controller",
                    "action_index": _completed_action_count(
                        state.events
                    ),
                    "policy": policy,
                    "public_state": public_state,
                    "raw_model_calls": calls,
                }
            )
            if action["type"] == "finalize":
                _finalize_state(
                    state, model, f"{arm}:{policy}"
                )
                break
            observations_before = len(state.observations)
            _record_event(
                state,
                action,
                _execute_action(state.backend, action),
                public_state=public_state,
            )
            state.no_progress_rounds = (
                0
                if len(state.observations) > observations_before
                else state.no_progress_rounds + 1
            )
        except (
            LearnedCallFailure,
            ModelProcessError,
            PublicSchemaError,
            RehearsalError,
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            _retain_exception_attempts(
                state, exc, phase="post_checkpoint"
            )
            state.failure = _typed_failure(
                str(
                    getattr(
                        exc,
                        "code",
                        "TOOL_ACCESS_FAILURE",
                    )
                ),
                phase="post_checkpoint",
                detail=str(exc),
            )
    if state.final is None and state.failure is None:
        state.failure = _typed_failure(
            "NO_FINALIZATION_WITHIN_STEP_LIMIT",
            phase="post_checkpoint",
        )


def validate_citations(
    final: Mapping[str, Any] | None,
    observations: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    known = set(observations)
    cited: list[str] = []
    if final:
        for assertion in final.get("asserted_claims", []):
            cited.extend(
                str(item)
                for item in assertion.get("citations", [])
            )
        for values in final.get(
            "claim_to_citations", {}
        ).values():
            cited.extend(str(item) for item in values)
    unknown = sorted(set(cited) - known)
    return {
        "valid": not unknown,
        "unknown_observation_ids": unknown,
        "cited_observation_ids": sorted(set(cited)),
        "search_pointer_citations_forbidden": True,
    }


def _provisional_support_metrics(
    assignment: Mapping[str, Any],
    state: PrefixState,
    citation: Mapping[str, Any],
) -> dict[str, Any]:
    expected = {
        str(value)
        for value in assignment.get(
            "expected_evidence_handle_ids", []
        )
    }
    acquired: set[str] = set()
    for observation_id in state.observations:
        acquired.update(
            str(value)
            for value in state.backend.evidence_by_observation.get(
                observation_id, []
            )
        )
    cited = set(citation["cited_observation_ids"])
    cited_evidence: set[str] = set()
    for observation_id in cited:
        cited_evidence.update(
            str(value)
            for value in state.backend.evidence_by_observation.get(
                observation_id, []
            )
        )
    asserted = (
        list(state.final.get("asserted_claims", []))
        if state.final
        else []
    )
    supported_claims = 0
    for claim in asserted:
        claim_citations = {
            str(value) for value in claim.get("citations", [])
        }
        claim_evidence: set[str] = set()
        for observation_id in claim_citations:
            claim_evidence.update(
                str(value)
                for value in state.backend.evidence_by_observation.get(
                    observation_id, []
                )
            )
        if (
            claim_citations
            and claim_citations <= set(state.observations)
            and (not expected or bool(claim_evidence & expected))
        ):
            supported_claims += 1
    evidence_recall = (
        len(acquired & expected) / len(expected)
        if expected
        else None
    )
    all_evidence_success = (
        float(expected <= acquired) if expected else None
    )
    citation_precision = (
        len(cited_evidence & expected) / len(cited_evidence)
        if cited_evidence
        else (1.0 if not asserted else 0.0)
    )
    citation_recall = (
        len(cited_evidence & expected) / len(expected)
        if expected
        else None
    )
    citation_f1 = (
        None
        if citation_recall is None
        else (
            0.0
            if citation_precision + citation_recall == 0
            else (
                2
                * citation_precision
                * citation_recall
                / (citation_precision + citation_recall)
            )
        )
    )
    supported_claim_rate = (
        supported_claims / len(asserted) if asserted else 1.0
    )
    verdict = (state.final or {}).get("verdict")
    supported_answer = float(
        verdict == "answer"
        and citation["valid"]
        and bool(asserted)
        and supported_claim_rate == 1.0
        and bool(cited_evidence & expected)
    )
    checkpoint_delivered = any(
        event.get("event") == CHECKPOINT_EVENT
        for event in state.events
    )
    post_checkpoint_observations = 0
    post_checkpoint_evidence: set[str] = set()
    if checkpoint_delivered:
        checkpoint_index = next(
            index
            for index, event in enumerate(state.events)
            if event.get("event") == CHECKPOINT_EVENT
        )
        for event in state.events[checkpoint_index + 1 :]:
            observation = event.get("response", {}).get(
                "observation"
            )
            if (
                event.get("response", {}).get("status") == "ok"
                and isinstance(observation, Mapping)
            ):
                post_checkpoint_observations += 1
                post_checkpoint_evidence.update(
                    str(value)
                    for value in state.backend.evidence_by_observation.get(
                        str(observation.get("observation_id")), []
                    )
                )
    failure_code = (state.failure or {}).get("code")
    premature_stop = bool(
        failure_code == "EARLY_TERMINAL_BEFORE_CHECKPOINT"
        or (
            state.final is not None
            and verdict in {"answer", "insufficient"}
            and expected
            and acquired < expected
        )
    )
    return {
        "expected_evidence_handle_ids": sorted(expected),
        "acquired_evidence_handle_ids": sorted(acquired),
        "cited_evidence_handle_ids": sorted(cited_evidence),
        "evidence_recall": evidence_recall,
        "all_evidence_success": all_evidence_success,
        "citation_precision": citation_precision,
        "citation_recall": citation_recall,
        "citation_f1": citation_f1,
        "supported_claim_rate": supported_claim_rate,
        "supported_answer_endpoint": supported_answer,
        "premature_stop": premature_stop,
        "checkpoint_delivered": checkpoint_delivered,
        "post_checkpoint_observations": post_checkpoint_observations,
        "post_checkpoint_evidence_handle_ids": sorted(
            post_checkpoint_evidence
        ),
        "recovery": (
            float(
                bool(
                    post_checkpoint_evidence
                    & expected
                )
            )
            if assignment["arm"] in {"R", "N"}
            else None
        ),
    }


def _metric_record(
    assignment: Mapping[str, Any],
    state: PrefixState,
) -> dict[str, Any]:
    citation = validate_citations(
        state.final, state.observations
    )
    completed = (
        state.final is not None
        and state.failure is None
        and citation["valid"]
    )
    mechanical = _provisional_support_metrics(
        assignment, state, citation
    )
    budget = _public_budget_snapshot(state.backend)
    tool_cost = round(
        float(state.backend.budget["cost_limit"])
        - float(budget["remaining_cost"]),
        6,
    )
    return {
        "assignment_id": assignment["assignment_id"],
        "family_id": assignment["family_id"],
        "mechanism": assignment["mechanism"],
        "system_id": assignment["system_id"],
        "arm": assignment["arm"],
        "itt_retained": assignment["itt_retained"],
        "structurally_ineligible": (
            assignment["assignment_status"]
            == "STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT"
        ),
        "completion_status": (
            "COMPLETED_VALID"
            if completed
            else (state.failure or {}).get(
                "code", "INVALID_SCHEMA"
            )
        ),
        "supported_answer_endpoint": mechanical[
            "supported_answer_endpoint"
        ],
        "acquire": (
            None
            if assignment["system_id"] == "direct_long_context"
            else {
                "evidence_recall": mechanical["evidence_recall"],
                "all_evidence_success": mechanical[
                    "all_evidence_success"
                ],
                "expected_evidence_handle_ids": mechanical[
                    "expected_evidence_handle_ids"
                ],
                "acquired_evidence_handle_ids": mechanical[
                    "acquired_evidence_handle_ids"
                ],
            }
        ),
        "ground": {
            "answer_score": mechanical[
                "supported_answer_endpoint"
            ],
            "citation_f1": mechanical["citation_f1"],
            "supported_claim_rate": mechanical[
                "supported_claim_rate"
            ],
            "citation_precision": mechanical[
                "citation_precision"
            ],
            "citation_recall": mechanical["citation_recall"],
            "citation_output_valid": citation["valid"],
        },
        "act": (
            None
            if assignment["system_id"] == "direct_long_context"
            else {
                "success_at_budget": mechanical[
                    "supported_answer_endpoint"
                ],
                "premature_stop": mechanical["premature_stop"],
                "recovery": mechanical["recovery"],
                "checkpoint_delivered": mechanical[
                    "checkpoint_delivered"
                ],
                "post_checkpoint_observations": mechanical[
                    "post_checkpoint_observations"
                ],
            }
        ),
        "tool_cost": {
            "steps_used": (
                int(state.backend.budget["max_steps"])
                - int(budget["remaining_steps"])
            ),
            "cost_used": tool_cost,
            "remaining_steps": budget["remaining_steps"],
            "remaining_cost": budget["remaining_cost"],
        },
        "failure_scored_zero": not completed,
        "no_deterministic_answer_substitution": True,
    }


def _trajectory(
    assignment: Mapping[str, Any],
    state: PrefixState,
    pair: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    citation = validate_citations(
        state.final, state.observations
    )
    completion = (
        "COMPLETED_VALID"
        if state.final and not state.failure and citation["valid"]
        else (state.failure or {}).get("code", "INVALID_SCHEMA")
    )
    return {
        "assignment_id": assignment["assignment_id"],
        "family_id": assignment["family_id"],
        "mechanism": assignment["mechanism"],
        "system_id": assignment["system_id"],
        "arm": assignment["arm"],
        "episode_start": state.start,
        "events": state.events,
        "checkpoint": pair,
        "final_output": state.final,
        "completion": {
            "status": completion,
            "failure": state.failure,
            "itt_retained": assignment["itt_retained"],
        },
        "observations": list(state.observations.values()),
        "public_no_progress_rounds": state.no_progress_rounds,
        "citation_validation": citation,
        "replay": {
            "public_trajectory_hash": semantic_hash(
                {
                    "events": state.events,
                    "final": state.final,
                }
            ),
            "deterministic_answer_substitution": False,
        },
    }


def _aggregate(
    metric_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_mechanism: dict[
        str, dict[str, list[float]]
    ] = defaultdict(lambda: defaultdict(list))
    denominators: dict[
        str, dict[str, int]
    ] = defaultdict(lambda: defaultdict(int))
    for row in metric_rows:
        mechanism = str(row["mechanism"])
        denominators[mechanism]["assigned"] += int(
            bool(row["itt_retained"])
        )
        denominators[mechanism][
            "structurally_ineligible"
        ] += int(bool(row["structurally_ineligible"]))
        denominators[mechanism]["invalid"] += int(
            row["completion_status"] != "COMPLETED_VALID"
        )
        denominators[mechanism]["valid"] += int(
            row["completion_status"] == "COMPLETED_VALID"
        )
        if row["arm"] in {"R", "N"} and row["itt_retained"]:
            by_mechanism[mechanism][str(row["arm"])].append(
                float(row["supported_answer_endpoint"])
            )
    tables = {}
    for mechanism in MECHANISMS:
        r_mean = mean_or_none(
            by_mechanism[mechanism]["R"]
        )
        n_mean = mean_or_none(
            by_mechanism[mechanism]["N"]
        )
        tables[mechanism] = {
            "estimand": "R_minus_N_ITT",
            "r_mean": r_mean,
            "n_mean": n_mean,
            "difference": (
                None
                if r_mean is None or n_mean is None
                else r_mean - n_mean
            ),
            "denominators": dict(denominators[mechanism]),
            "interpretation": (
                "development_rehearsal_only_no_causal_claim"
            ),
        }
    return {
        "mechanisms_pooled": False,
        "itt": tables,
        "no_trigger": {
            "conditioning_on_trigger_allowed": False,
            "missing_pairs_dropped": False,
        },
        "claims": {
            "causal_result": False,
            "h2": False,
            "gate_a": False,
        },
    }


def write_run_outputs(
    output_dir: Path,
    *,
    plan: Mapping[str, Any],
    trajectories: Sequence[Mapping[str, Any]],
    model_calls: Sequence[Mapping[str, Any]],
    factor_outputs: Sequence[Mapping[str, Any]],
    prefix_pairs: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
    run_manifest: Mapping[str, Any],
) -> None:
    if (
        output_dir.exists()
        and (output_dir / "run_manifest.json").is_file()
    ):
        existing = _load(output_dir / "run_manifest.json")
        if existing.get("completion_status") == "COMPLETE":
            raise RehearsalError(
                "OUTPUT_EXISTS", str(output_dir)
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    assignments = list(plan["assignments"])
    assignment_ids = [
        str(row["assignment_id"]) for row in assignments
    ]
    trajectory_ids = [
        str(row["assignment_id"]) for row in trajectories
    ]
    metric_ids = [
        str(row["assignment_id"]) for row in metric_rows
    ]
    for label, values in (
        ("assignments", assignment_ids),
        ("trajectories", trajectory_ids),
        ("metric_rows", metric_ids),
    ):
        if len(values) != len(set(values)):
            raise RehearsalError(
                "DUPLICATE_ASSIGNMENT_TERMINAL_ROW", label
            )
    if set(assignment_ids) != set(trajectory_ids) or set(
        assignment_ids
    ) != set(metric_ids):
        raise RehearsalError(
            "INCOMPLETE_ASSIGNMENT_TERMINAL_LEDGER"
        )
    failures_by_assignment = {
        str(row["assignment_id"]): dict(row)
        for row in failures
    }
    if len(failures_by_assignment) != len(failures):
        raise RehearsalError("DUPLICATE_FAILURE_LEDGER_ROW")
    completion_ledger = [
        {
            "assignment_id": row["assignment_id"],
            "completion_status": row["completion_status"],
            "itt_retained": row["itt_retained"],
            "structurally_ineligible": row[
                "structurally_ineligible"
            ],
            "failure": failures_by_assignment.get(
                str(row["assignment_id"])
            ),
        }
        for row in metric_rows
    ]
    citations = [
        {
            "assignment_id": row["assignment_id"],
            "verdict": (
                row.get("final_output") or {}
            ).get("verdict"),
            "answer_text": (
                row.get("final_output") or {}
            ).get("answer_text", ""),
            "asserted_claims": (
                row.get("final_output") or {}
            ).get("asserted_claims", []),
            "claim_to_citations": (
                row.get("final_output") or {}
            ).get("claim_to_citations", {}),
            "observation_catalog": row.get(
                "observations", []
            ),
            "citation_validation": row[
                "citation_validation"
            ],
            "output_schema_valid": (
                row["completion"]["status"]
                == "COMPLETED_VALID"
            ),
        }
        for row in trajectories
    ]
    _write_jsonl(
        output_dir / "assignments.jsonl", assignments
    )
    _write_jsonl(
        output_dir / "raw_trajectories.jsonl",
        trajectories,
    )
    _write_jsonl(
        output_dir / "raw_model_calls.jsonl",
        model_calls,
    )
    _write_jsonl(
        output_dir / "factor_model_raw_outputs.jsonl",
        factor_outputs,
    )
    _write_jsonl(
        output_dir / "citation_outputs.jsonl", citations
    )
    _write_jsonl(
        output_dir / "r_n_prefix_pairs.jsonl",
        prefix_pairs,
    )
    _write_jsonl(
        output_dir / "episode_metrics.jsonl",
        metric_rows,
    )
    _write_jsonl(
        output_dir / "metric_ready_records.jsonl",
        metric_rows,
    )
    _write_jsonl(
        output_dir / "failure_ledger.jsonl",
        completion_ledger,
    )
    _atomic_write(
        output_dir / "aggregate_metrics.json",
        _aggregate(metric_rows),
    )
    _atomic_write(
        output_dir / "replay_manifest.json",
        {
            "schema_version": SCHEMA,
            "trajectory_hashes": [
                row["replay"]["public_trajectory_hash"]
                for row in trajectories
            ],
            "r_n_prefix_integrity": all(
                row["prefix_identical"]
                for row in prefix_pairs
            ),
            "no_deterministic_answer_substitution": True,
        },
    )
    _atomic_write(
        output_dir / "run_manifest.json",
        {
            **run_manifest,
            "assignment_count": len(assignments),
            "trajectory_count": len(trajectories),
            "metric_row_count": len(metric_rows),
            "completion_ledger_row_count": len(
                completion_ledger
            ),
            "assignment_ids_sha256": semantic_hash(
                sorted(assignment_ids)
            ),
            "output_contract": list(REQUIRED_OUTPUTS),
            "execution_authorized": False,
            "machine_provisional_non_scientific": True,
            "bundle_provenance_firewall": {
                "status": run_manifest.get(
                    "bundle_provenance_firewall", {}
                ).get("status", "UNKNOWN_NOT_REPORTED"),
                "scope": (
                    "frozen_bundle_construction_and_claim_firewall"
                ),
            },
            "runtime_leakage_classifier": {
                "status": (
                    "NOT_RUN_TEST_INJECTION"
                    if run_manifest.get("testing_injection")
                    else "NOT_RUN_EXECUTION_UNAUTHORIZED"
                ),
                "distinct_from_bundle_provenance_firewall": True,
            },
            "completion_status": "COMPLETE",
        },
    )
    inventory = []
    for path in sorted(output_dir.iterdir()):
        if (
            path.name == "file_inventory.json"
            or not path.is_file()
        ):
            continue
        inventory.append(
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "mode": oct(
                    stat.S_IMODE(path.stat().st_mode)
                ),
                "sha256": _sha256(path),
            }
        )
    _atomic_write(
        output_dir / "file_inventory.json",
        {"files": inventory},
    )
    absent = [
        name
        for name in REQUIRED_OUTPUTS
        if not (output_dir / name).is_file()
    ]
    if absent:
        raise RehearsalError(
            "MISSING_OUTPUTS", ",".join(absent)
        )


def execute_rehearsal(
    repo_root: str | Path = ".",
    *,
    output_dir: str | Path | None = None,
    backend_factory: (
        Callable[[Mapping[str, Any]], BackendLike] | None
    ) = None,
    model: ModelLike | None = None,
) -> dict[str, Any]:
    """Execute only after authorization, except injected test adapters."""

    root = Path(repo_root).resolve()
    validation = validate_repository(root)
    testing_injection = (
        backend_factory is not None and model is not None
    )
    if (
        not validation["execution_authorized"]
        and not testing_injection
    ):
        raise RehearsalError(
            "EXECUTION_NOT_AUTHORIZED",
            ",".join(
                validation[
                    "execution_authorization_reasons"
                ]
            ),
        )
    plan = build_plan(root)
    frozen_inputs = _load_inputs(root)
    if backend_factory is None or model is None:
        raise RehearsalError(
            "EXECUTION_ADAPTER_NOT_CONFIGURED",
            "live execution is intentionally unavailable "
            "while authorization is false",
        )
    trajectories: list[dict[str, Any]] = []
    model_calls: list[dict[str, Any]] = []
    factor_outputs: list[dict[str, Any]] = []
    prefix_pairs: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    grouped: dict[
        tuple[str, str, str],
        dict[str, dict[str, Any]],
    ] = defaultdict(dict)
    for assignment in plan["assignments"]:
        key = (
            assignment["family_id"],
            assignment["mechanism"],
            assignment["system_id"],
        )
        grouped[key][assignment["arm"]] = assignment
    for (
        _family,
        _mechanism,
        system_id,
    ), arms in grouped.items():
        if system_id == "direct_long_context":
            for arm, assignment in arms.items():
                backend = backend_factory(assignment)
                if arm in {"R", "N"}:
                    state = PrefixState(
                        backend=backend,
                        start=backend.public_start(),
                        pointers={},
                        observations={},
                        events=[],
                        model_calls=[],
                        factor_outputs=[],
                        failure=_typed_failure(
                            "STRUCTURALLY_INELIGIBLE_"
                            "BEFORE_ASSIGNMENT",
                            phase="preassignment",
                        ),
                    )
                else:
                    state = PrefixState(
                        backend=backend,
                        start=backend.public_start(),
                        pointers={},
                        observations={},
                        events=[],
                        model_calls=[],
                        factor_outputs=[],
                    )
                    _pack_direct_long_context(state)
                    _finalize_state(
                        state,
                        model,
                        f"{arm}:direct_long_context",
                    )
                trajectories.append(
                    _trajectory(assignment, state)
                )
                metric_rows.append(
                    _metric_record(assignment, state)
                )
                if state.failure:
                    failures.append(
                        {
                            "assignment_id": assignment[
                                "assignment_id"
                            ],
                            **state.failure,
                            "itt_retained": assignment[
                                "itt_retained"
                            ],
                        }
                    )
                model_calls.extend(
                    {
                        "assignment_id": assignment[
                            "assignment_id"
                        ],
                        **row,
                    }
                    for row in state.model_calls
                )
                factor_outputs.extend(
                    {
                        "assignment_id": assignment[
                            "assignment_id"
                        ],
                        **row,
                    }
                    for row in state.factor_outputs
                )
            continue
        for arm in ("C", "B"):
            assignment = arms[arm]
            state = run_blocked_prefix(
                backend_factory(assignment),
                system_id=system_id,
                model=model,
                checkpoint_required=False,
            )
            _continue_state(
                state,
                system_id=system_id,
                arm=arm,
                model=model,
            )
            trajectories.append(
                _trajectory(assignment, state)
            )
            metric_rows.append(
                _metric_record(assignment, state)
            )
            if state.failure:
                failures.append(
                    {
                        "assignment_id": assignment[
                            "assignment_id"
                        ],
                        **state.failure,
                        "itt_retained": True,
                    }
                )
            model_calls.extend(
                {
                    "assignment_id": assignment[
                        "assignment_id"
                    ],
                    **row,
                }
                for row in state.model_calls
            )
            factor_outputs.extend(
                {
                    "assignment_id": assignment[
                        "assignment_id"
                    ],
                    **row,
                }
                for row in state.factor_outputs
            )
        prefix = run_blocked_prefix(
            backend_factory(arms["R"]),
            system_id=system_id,
            model=model,
        )
        r_state, n_state, pair = fork_restoration_pair(
            prefix
        )
        pair.update(
            {
                "r_assignment_id": arms["R"][
                    "assignment_id"
                ],
                "n_assignment_id": arms["N"][
                    "assignment_id"
                ],
                "family_id": arms["R"]["family_id"],
                "mechanism": arms["R"]["mechanism"],
                "system_id": system_id,
            }
        )
        prefix_pairs.append(pair)
        for arm, state in (
            ("R", r_state),
            ("N", n_state),
        ):
            assignment = arms[arm]
            _continue_state(
                state,
                system_id=system_id,
                arm=arm,
                model=model,
            )
            trajectories.append(
                _trajectory(assignment, state, pair)
            )
            metric_rows.append(
                _metric_record(assignment, state)
            )
            if state.failure:
                failures.append(
                    {
                        "assignment_id": assignment[
                            "assignment_id"
                        ],
                        **state.failure,
                        "itt_retained": True,
                    }
                )
            model_calls.extend(
                {
                    "assignment_id": assignment[
                        "assignment_id"
                    ],
                    **row,
                }
                for row in state.model_calls
            )
            factor_outputs.extend(
                {
                    "assignment_id": assignment[
                        "assignment_id"
                    ],
                    **row,
                }
                for row in state.factor_outputs
            )
    run_id = (
        "synthetic-test"
        if testing_injection
        else hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    )
    target = (
        Path(output_dir)
        if output_dir
        else root
        / (
            "data/restricted/"
            "p23_102_acquire_ground_act_rehearsal_v1/"
            "runs"
        )
        / run_id
    )
    write_run_outputs(
        target,
        plan=plan,
        trajectories=trajectories,
        model_calls=model_calls,
        factor_outputs=factor_outputs,
        prefix_pairs=prefix_pairs,
        metric_rows=metric_rows,
        failures=failures,
        run_manifest={
            "schema_version": SCHEMA,
            "run_id": run_id,
            "created_date": FROZEN_DATE,
            "runner_identity": {
                "path": (
                    "scripts/"
                    "run_p23_102_acquire_ground_act_rehearsal.py"
                ),
                "sha256": _sha256(
                    root
                    / "scripts/"
                    "run_p23_102_acquire_ground_act_rehearsal.py"
                ),
                "protocol_schema": SCHEMA,
            },
            "rehearsal_identity": {
                "source_group_id": "P23",
                "source_id": "P23_102",
                "config_path": str(CONFIG_REL),
                "config_sha256": _sha256(root / CONFIG_REL),
                "bundle_path": str(BUNDLE_REL),
                "bundle_content_sha256": frozen_inputs.leakage.get(
                    "bundle_content_sha256"
                ),
                "plan_hash": plan["plan_hash"],
                "assignment_count": plan["assignment_count"],
                "systems": list(SYSTEMS),
                "mechanisms": list(MECHANISMS),
                "arms": list(ARMS),
            },
            "development_only": True,
            "scientific_execution_authorized": False,
            "validation": validation,
            "bundle_provenance_firewall": validation[
                "bundle_provenance_firewall"
            ],
            "runtime_leakage_classifier": validation[
                "runtime_leakage_classifier"
            ],
            "plan_hash": plan["plan_hash"],
            "testing_injection": testing_injection,
            "no_deterministic_answer_substitution": True,
            "claims": {
                "strong_competence": False,
                "h2": False,
                "human_family_validity": False,
                "causal_result": False,
                "gate_a": False,
            },
        },
    )
    return {
        "status": "COMPLETE",
        "output_dir": str(target),
        "trajectory_count": len(trajectories),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    modes = parser.add_mutually_exclusive_group(
        required=True
    )
    modes.add_argument("--validate-only", action="store_true")
    modes.add_argument("--plan", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.validate_only:
            report = validate_repository(args.repo_root)
        elif args.plan:
            report = build_plan(args.repo_root)
        else:
            report = execute_rehearsal(
                args.repo_root,
                output_dir=args.output_dir,
            )
    except RehearsalError as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL_CLOSED",
                    "code": exc.code,
                    "message": str(exc),
                },
                indent=2,
            )
        )
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
