"""Matched full-timeline backend with a policy-visible, evaluator-blind view."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from av_trace_scale1a import core as s1
from av_trace_scale1b_retrieval import core as wr


def _opaque(namespace: str, value: str) -> str:
    return f"{namespace}." + hashlib.sha256(
        f"ga-public-v1:{namespace}:{value}".encode()
    ).hexdigest()[:24]


def public_claim_slots(family: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "claim_handle": f"slot.c{ordinal:02d}",
            "description": (
                "Required answer component; infer its content and supporting "
                "modality from the question and acquired evidence."
            ),
        }
        for ordinal, _claim in enumerate(family.get("claims", ()), 1)
    ]


class LearnedFeatureModels:
    """Lazy text encoders; model files are only loaded if their ranker is used."""

    def __init__(self, root: Path, *, threads: int = 8) -> None:
        gate = wr.verify_gates(root)
        models = gate["models"]["models"]
        self.paths = {
            "siglip2": root / str(models["siglip2"]["snapshot_dir"]),
            "clap": root / str(models["clap"]["snapshot_dir"]),
        }
        self.threads = threads
        self.runtime: Any | None = None

    def _load(self) -> Any:
        if self.runtime is None:
            self.runtime = wr._WaveRModels(
                self.paths["siglip2"], self.paths["clap"], threads=self.threads
            )
        return self.runtime

    def visual(self, query: str) -> np.ndarray:
        return self._load().siglip_text([query])[0]

    def ambient(self, query: str) -> np.ndarray:
        return self._load().clap_text([query])[0]


class FullTimelineBackend:
    """Fixed backend supporting F-CTRL or F-VA search under C/B/R states."""

    def __init__(
        self,
        root: Path,
        *,
        family: Mapping[str, Any],
        intervention: Mapping[str, Any],
        retrieval_variant: str,
        state: str,
        scope: str = "source_scoped",
        restoration_enabled: bool = True,
        fault_injection: Mapping[str, Any] | None = None,
        feature_models: LearnedFeatureModels | None = None,
    ) -> None:
        if retrieval_variant not in {"F-CTRL", "F-VA"}:
            raise ValueError("retrieval_variant must be F-CTRL or F-VA")
        if state not in {"CLEAN", "BLOCKED", "RESTORED"}:
            raise ValueError("unknown state")
        self.root = root
        self.family = dict(family)
        self.intervention = dict(intervention)
        self.retrieval_variant = retrieval_variant
        self.state = state
        self.scope = scope
        self.restoration_enabled = restoration_enabled
        self.fault_injection = dict(fault_injection or {})
        self.scale_index = s1._load(root / s1.RESTRICTED_REL / "full_timeline_index.json")
        self.learned_index = wr._load(root / wr.RESTRICTED_REL / "learned_index.json")
        machine_review = s1._load(
            root
            / "data/restricted/noaa01/machine_review/"
            "noaa01_machine_review_records.json"
        )
        self.visual_catalog = [
            {
                "source_ref": row["candidate_id"],
                "start_s": float(row["review_interval"]["start_seconds"]),
                "end_s": float(row["review_interval"]["end_seconds"]),
                "description": str(
                    row.get("codex_synthesis", {}).get("visual_description", "")
                ),
                "review_id": row["review_id"],
            }
            for row in machine_review["records"]
            if row.get("codex_synthesis", {}).get("visual_description")
        ]
        segment_manifest = s1._load(root / s1.RESTRICTED_REL / "segment_manifest.json")
        source = next(
            row for row in segment_manifest["sources"]
            if row["source_ref"] == self.family["asset_id"]
        )
        self.video_duration_s = float(source["duration_us"]) / 1_000_000
        self.feature_models = feature_models
        self.budget = {"max_steps": 10, "cost_limit": 12.0}
        self.costs = {
            "search_visual": 1.0,
            "search_speech": 1.0,
            "search_ambient_audio": 1.0,
            "inspect_clip": 2.0,
            "read_transcript": 1.0,
            "get_channel_status": 0.25,
            "search_fused": 1.25,
            "finalize": 0.0,
        }
        self.steps_used = 0
        self.cost_used = 0.0
        self.triggered = False
        self.search_count: defaultdict[str, int] = defaultdict(int)
        self.search_queries: defaultdict[str, list[str]] = defaultdict(list)
        self.pointer_private: dict[str, dict[str, Any]] = {}
        self.observation_private: dict[str, dict[str, Any]] = {}
        self.evidence_by_observation: dict[str, list[str]] = {}
        self.events: list[dict[str, Any]] = []
        self.final_decision_snapshot: dict[str, Any] | None = None
        self.suppressed = (
            set(intervention["blocked"]["suppressed_segment_ids"])
            if state in {"BLOCKED", "RESTORED"}
            else set()
        )
        self.support_by_modality = {
            key: set(values)
            for key, values in family["support_segment_ids"].items()
        }

    def public_start(self) -> dict[str, Any]:
        return {
            "question": self.family["question"],
            "claim_slots": public_claim_slots(self.family),
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
        cost = self.costs[tool]
        if self.cost_used + cost > self.budget["cost_limit"] + 1e-9:
            raise RuntimeError("OVER_BUDGET_COST")
        self.steps_used += 1
        self.cost_used += cost

    def _maybe_fault(self, tool: str) -> dict[str, Any] | None:
        spec = self.fault_injection.get(tool)
        if spec is None:
            return None
        if isinstance(spec, list):
            index = sum(event["tool"] == tool for event in self.events)
            spec = spec[index] if index < len(spec) else None
        if not spec:
            return None
        status = str(spec)
        if status not in {
            "timeout",
            "malformed",
            "oom",
            "rate_limited",
            "access_failure",
        }:
            return None
        return {"status": status, "error": {"code": status.upper(), "retryable": status != "malformed"}}

    def _maybe_trigger(
        self,
        tool: str,
        modalities: Sequence[str] = (),
        *,
        query: str | None = None,
    ) -> None:
        if self.state != "RESTORED" or self.triggered or not self.restoration_enabled:
            return
        trigger = str(self.intervention["trigger"])
        channel = self.intervention.get("channel")
        fires = (
            tool == "get_channel_status"
            and trigger.startswith("get_channel_status")
            and (channel is None or channel in modalities)
        ) or (
            tool == "search_visual"
            and trigger.startswith("second distinct visual query")
            and query is not None
            and bool(self.search_queries["vision"])
            and query.strip().casefold()
            not in {item.strip().casefold() for item in self.search_queries["vision"]}
        )
        if fires:
            self.suppressed.clear()
            self.triggered = True

    def _control(self, modality: str, query: str, source_ref: str | None) -> list[dict[str, Any]]:
        if modality == "speech":
            return s1.search_speech(
                self.scale_index,
                query,
                top_k=20,
                source_ref=source_ref,
                exclude_ids=self.suppressed,
            )
        if modality == "ambient":
            return s1.search_ambient(
                self.scale_index,
                query,
                top_k=20,
                source_ref=source_ref,
                exclude_ids=self.suppressed,
            )
        vector = s1._cached_clip_text(self.root, [query], threads=8)[0]
        return s1.search_visual(
            self.root,
            self.scale_index,
            query,
            top_k=20,
            source_ref=source_ref,
            exclude_ids=self.suppressed,
            text_vector=vector,
        )

    def _learned(self, modality: str, query: str, source_ref: str | None) -> list[dict[str, Any]]:
        if modality == "speech":
            return self._control(modality, query, source_ref)
        if self.feature_models is None:
            self.feature_models = LearnedFeatureModels(self.root)
        if modality == "vision":
            documents = self.learned_index["modalities"]["siglip2_visual"]["documents"]
            vector = self.feature_models.visual(query)
        else:
            documents = self.learned_index["modalities"]["clap_audio"]["documents"]
            vector = self.feature_models.ambient(query)
        return wr._rank_vectors(
            documents, vector, source_ref=source_ref, suppressed=self.suppressed
        )[:20]

    def search(self, modality: str, query: str, top_k: int) -> dict[str, Any]:
        tool = {
            "vision": "search_visual",
            "speech": "search_speech",
            "ambient": "search_ambient_audio",
        }[modality]
        self._charge(tool)
        self._maybe_trigger(tool, query=query)
        self.search_count[modality] += 1
        self.search_queries[modality].append(query)
        fault = self._maybe_fault(tool)
        if fault is not None:
            self.events.append({"tool": tool, "request": {"query": query, "top_k": top_k}, "response": fault})
            return fault
        source_ref = self.family["asset_id"] if self.scope == "source_scoped" else None
        ranking = (
            self._control(modality, query, source_ref)
            if self.retrieval_variant == "F-CTRL"
            else self._learned(modality, query, source_ref)
        )
        results = []
        for rank, row in enumerate(ranking[:top_k], 1):
            segment = str(row["segment_id"])
            pointer_id = _opaque("ptr", f"{modality}:{segment}")
            normalized = {
                **row,
                "modality": modality,
                "rank": rank,
                "interval": {
                    "start_s": round(int(row["start_us"]) / 1e6, 6),
                    "end_s": round(int(row["end_us"]) / 1e6, 6),
                },
            }
            self.pointer_private[pointer_id] = normalized
            results.append(
                {
                    "pointer_id": pointer_id,
                    "modality": modality,
                    "interval": normalized["interval"],
                    "preview": f"{modality} evidence candidate",
                    "score": round(float(row["score"]), 8),
                }
            )
        response = {"status": "ok" if results else "not_found", "results": results}
        self.events.append({"tool": tool, "request": {"query": query, "top_k": top_k}, "response": response})
        return response

    def status(self, modalities: Sequence[str]) -> dict[str, Any]:
        self._charge("get_channel_status")
        self._maybe_trigger("get_channel_status", modalities)
        channels = {
            modality: {
                "status": (
                    "unavailable"
                    if self.suppressed
                    & self.support_by_modality.get(modality, set())
                    else "available"
                ),
                "retryable": self.state == "RESTORED" and self.restoration_enabled,
            }
            for modality in modalities
        }
        response = {"status": "ok", "channels": channels}
        self.events.append({"tool": "get_channel_status", "request": {"modalities": list(modalities)}, "response": response})
        return response

    def observe(self, pointer_id: str) -> dict[str, Any]:
        pointer = self.pointer_private.get(pointer_id)
        if pointer is None:
            return {"status": "not_found", "error": {"code": "UNKNOWN_POINTER", "retryable": False}}
        modality = pointer["modality"]
        tool = "read_transcript" if modality == "speech" else "inspect_clip"
        self._charge(tool)
        fault = self._maybe_fault(tool)
        if fault is not None:
            self.events.append({"tool": tool, "request": {"pointer_id": pointer_id}, "response": fault})
            return fault
        if pointer["segment_id"] in self.suppressed:
            response = {"status": "access_failure", "error": {"code": "ROUTE_INACCESSIBLE", "retryable": self.state == "RESTORED"}}
            self.events.append({"tool": tool, "request": {"pointer_id": pointer_id}, "response": response})
            return response
        decoded = s1.tool_time_decode(
            self.root,
            self.family["asset_id"],
            (
                float(pointer["interval"]["start_s"]),
                float(pointer["interval"]["end_s"]),
            ),
            include_video=modality == "vision",
            include_audio=modality in {"speech", "ambient"},
        )
        document = s1._find_document(self.scale_index, pointer["segment_id"], modality)
        matched: list[str] = []
        for evidence in self.family["evidence_units"]:
            if evidence["modality"] != modality:
                continue
            if pointer["segment_id"] in self.support_by_modality.get(modality, set()):
                matched.append(evidence["evidence_id"])
        if modality == "speech":
            content = " ".join(document["tokens"])
        elif modality == "ambient":
            content = ", ".join(item["label"] for item in document["features"][:8])
        else:
            overlaps = [
                row
                for row in self.visual_catalog
                if row["source_ref"] == pointer["source_ref"]
                and row["start_s"] < pointer["interval"]["end_s"]
                and row["end_s"] > pointer["interval"]["start_s"]
            ]
            # The catalog is constructed independently for all 18 reviewed
            # windows. It is never selected based on evaluator support labels.
            content = (
                " ".join(row["description"] for row in overlaps)
                if overlaps
                else "Visual clip decoded successfully; no textual description is available."
            )
        observation_id = _opaque("obs", f"{modality}:{pointer['segment_id']}")
        observation = {
            "observation_id": observation_id,
            "modality": modality,
            "interval": dict(pointer["interval"]),
            "content": content,
            "citable": True,
            "perception_source": (
                "machine_review_window_catalog"
                if modality == "vision" and overlaps
                else "source_derived"
            ),
        }
        self.observation_private[observation_id] = {
            **observation,
            "segment_id": pointer["segment_id"],
            "pointer_id": pointer_id,
            "tool_time_decode": decoded,
        }
        self.evidence_by_observation[observation_id] = sorted(set(matched))
        response = {"status": "ok", "observation": observation}
        self.events.append({"tool": tool, "request": {"pointer_id": pointer_id}, "response": response})
        return response

    def _query_by_modality(self) -> dict[str, str]:
        return {
            modality: self.family["query_families"][
                min(
                    len(self.family["query_families"]) - 1,
                    1 if modality == "ambient" else 0,
                )
            ]
            for modality in self.family["provisional_modalities"]
        }

    def fused_search(self, top_k: int = 5) -> dict[str, Any]:
        """Internal single-shot RAG retrieval under the frozen RRF contract."""

        self._charge("search_fused")
        source_ref = self.family["asset_id"] if self.scope == "source_scoped" else None
        query_by_modality = self._query_by_modality()
        rankings: dict[str, list[dict[str, Any]]] = {}
        for modality, query in query_by_modality.items():
            rows = (
                self._control(modality, query, source_ref)
                if self.retrieval_variant == "F-CTRL"
                else self._learned(modality, query, source_ref)
            )
            rankings[modality] = [{**row, "modality": modality} for row in rows]
        if "vision" in rankings and len(rankings) > 1:
            visual_docs = (
                self.scale_index["modalities"]["vision"]["documents"]
                if self.retrieval_variant == "F-CTRL"
                else self.learned_index["modalities"]["siglip2_visual"]["documents"]
            )
            rankings["vision"] = wr._temporal_bind_visual(
                rankings["vision"],
                {key: value for key, value in rankings.items() if key != "vision"},
                visual_docs,
                source_ref=source_ref,
            )
            rankings["vision"] = [
                {**row, "modality": "vision"} for row in rankings["vision"]
            ]
        fused, contributions = wr._rrf_record_details(
            rankings,
            rrf_k=60,
            weights={"vision": 1.0, "ambient": 1.0, "speech": 1.0},
        )
        results: list[dict[str, Any]] = []
        for rank, segment_id in enumerate(fused[:top_k], 1):
            representative: Mapping[str, Any] | None = None
            modality = None
            for candidate_modality in sorted(contributions.get(segment_id, set())):
                row = next(
                    (
                        item
                        for item in rankings[candidate_modality]
                        if item["segment_id"] == segment_id
                    ),
                    None,
                )
                if row is not None:
                    representative = row
                    modality = candidate_modality
                    break
            if representative is None:
                # RRF may choose a temporally-bound representative from one
                # modality while contribution metadata names another.
                for candidate_modality, rows in rankings.items():
                    row = next(
                        (item for item in rows if item["segment_id"] == segment_id),
                        None,
                    )
                    if row is not None:
                        representative = row
                        modality = candidate_modality
                        break
            if representative is None or modality is None:
                continue
            temporal_key = wr._temporal_group(representative)
            modality_pointers: dict[str, str] = {}
            for candidate_modality in sorted(
                contributions.get(segment_id, set())
            ):
                candidate = next(
                    (
                        item
                        for item in rankings.get(candidate_modality, ())
                        if wr._temporal_group(item) == temporal_key
                    ),
                    None,
                )
                if candidate is None:
                    continue
                pointer_id = _opaque(
                    "ptr",
                    (
                        f"fused:{self.retrieval_variant}:"
                        f"{candidate_modality}:{candidate['segment_id']}"
                    ),
                )
                normalized = {
                    **candidate,
                    "modality": candidate_modality,
                    "rank": rank,
                    "interval": {
                        "start_s": round(int(candidate["start_us"]) / 1e6, 6),
                        "end_s": round(int(candidate["end_us"]) / 1e6, 6),
                    },
                }
                self.pointer_private[pointer_id] = normalized
                modality_pointers[candidate_modality] = pointer_id
            results.append(
                {
                    "fused_result_id": _opaque(
                        "ptr",
                        f"fused-result:{self.retrieval_variant}:{segment_id}",
                    ),
                    "modality_pointers": modality_pointers,
                    "interval": {
                        "start_s": round(int(representative["start_us"]) / 1e6, 6),
                        "end_s": round(int(representative["end_us"]) / 1e6, 6),
                    },
                    "preview": "fused evidence candidate",
                    "contributing_modalities": sorted(
                        contributions.get(segment_id, set())
                    ),
                }
            )
        response = {"status": "ok" if results else "not_found", "results": results}
        self.events.append(
            {
                "tool": "search_fused_internal",
                "request": {"top_k": top_k, "queries": query_by_modality},
                "response": response,
            }
        )
        return response

    def public_route_certificate(self) -> dict[str, Any]:
        snapshot = self.final_decision_snapshot or self.snapshot()
        missing_modalities = sorted(
            {
                evidence["modality"]
                for evidence in self.family["evidence_units"]
                if evidence["evidence_id"]
                not in {
                    eid
                    for values in self.evidence_by_observation.values()
                    for eid in values
                }
            }
        )
        return {
            "final_action_index": self.steps_used,
            "remaining_steps": snapshot["remaining_steps"],
            "remaining_cost": snapshot["remaining_cost"],
            "acquired_evidence_count": len(
                {
                    eid
                    for values in self.evidence_by_observation.values()
                    for eid in values
                }
            ),
            "missing_modalities": missing_modalities,
            "triggered": snapshot["triggered"],
            "channel_state": (
                "restricted" if snapshot["suppressed_segment_ids"] else "open"
            ),
        }

    def provisional_evidence_pack(self, *, omit_one: bool = False) -> list[dict[str, Any]]:
        selected: list[tuple[str, str]] = []
        for modality in self.family["provisional_modalities"]:
            segment_ids = sorted(
                self.support_by_modality.get(modality, set()),
                key=lambda item: (
                    s1._find_document(self.scale_index, item, modality)["scale"] != "fine",
                    item,
                ),
            )
            if segment_ids:
                selected.append((modality, segment_ids[0]))
        if omit_one and selected:
            selected = selected[:-1]
        observations: list[dict[str, Any]] = []
        for modality, segment_id in selected:
            document = s1._find_document(self.scale_index, segment_id, modality)
            pointer_id = _opaque("ptr", f"provisional:{modality}:{segment_id}")
            self.pointer_private[pointer_id] = {
                **document,
                "modality": modality,
                "interval": {
                    "start_s": round(int(document["start_us"]) / 1e6, 6),
                    "end_s": round(int(document["end_us"]) / 1e6, 6),
                },
            }
            response = self.observe(pointer_id)
            if response.get("status") == "ok":
                observations.append(response["observation"])
        return observations

    def snapshot(self) -> dict[str, Any]:
        return {
            "remaining_steps": self.budget["max_steps"] - self.steps_used,
            "remaining_cost": round(self.budget["cost_limit"] - self.cost_used, 6),
            "triggered": self.triggered,
            "suppressed_segment_ids": sorted(self.suppressed),
            "known_pointer_ids": sorted(self.pointer_private),
            "known_observation_ids": sorted(self.observation_private),
        }

    def finalize(self, final: Mapping[str, Any]) -> dict[str, Any]:
        self.final_decision_snapshot = self.snapshot()
        self._charge("finalize")
        response = {
            "status": "finalized",
            "verdict": final.get("verdict"),
        }
        self.events.append(
            {"tool": "finalize", "request": {}, "response": response}
        )
        return response
