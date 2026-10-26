"""Public-surface, evidence-lock, authorship, and cache-isolation guards."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import sha256_json
from .errors import IsolationViolation, SchemaViolation

FORBIDDEN_PRIVATE_KEYS = frozenset(
    {
        "state_role",
        "assignment_arm",
        "intervention_id",
        "necessity_group_id",
        "trigger_enabled",
        "hidden_route_availability",
        "accepted_ses_labels",
        "answer_keys",
        "order_sequence_id",
        "oracle_support",
        "required_terms",
        "evaluator_key",
        "evaluator_private",
        "private_support_map",
        "expected_answer",
        "scoring_target",
        "expected_action_index",
        "expected_evidence_state",
        "accepted_support",
        "required_terms_by_claim",
    }
)

PRIVATE_IDENTIFIER_PATTERNS = (
    re.compile(r"\bnoaa01-", re.IGNORECASE),
    re.compile(r"\bclaim\.r[0-9a-z._-]*", re.IGNORECASE),
    re.compile(r"\be\.r[0-9a-z._-]*", re.IGNORECASE),
    re.compile(r"\bseg\.[0-9a-z._-]*", re.IGNORECASE),
    re.compile(r"\bcand-[0-9a-z._-]*", re.IGNORECASE),
)

ANSWER_BEARING_PATH_PREFIXES = (
    "final_answer.answer_mode",
    "final_answer.verdict",
    "final_answer.claims",
    "final_answer.natural_language_answer",
    "final_answer.diagnosis",
)


def _walk(value: Any, path: str = "$") -> Iterable[tuple[str, str, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key), child
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def assert_public_surface(value: Any) -> None:
    """Reject evaluator-private fields and known private identifier forms."""

    for path, key, child in _walk(value):
        if key.casefold() in FORBIDDEN_PRIVATE_KEYS:
            raise SchemaViolation(
                "EVALUATOR_PRIVATE_FIELD_EXPOSED",
                details={"path": path},
            )
        if isinstance(child, str):
            for pattern in PRIVATE_IDENTIFIER_PATTERNS:
                if pattern.search(child):
                    raise SchemaViolation(
                        "PRIVATE_IDENTIFIER_EXPOSED",
                        details={"path": path},
                    )


@dataclass(frozen=True)
class PublicObservation:
    observation_id: str
    interval: Mapping[str, float]
    modalities: tuple[str, ...]
    payload: Mapping[str, Any]

    def to_public_dict(self) -> dict[str, Any]:
        value = {
            "observation_id": self.observation_id,
            "interval": dict(self.interval),
            "modalities": list(self.modalities),
            "payload": dict(self.payload),
        }
        assert_public_surface(value)
        return value


class ObservedEvidenceLock:
    """Immutable citation allowlist derived only from the current trajectory."""

    def __init__(self, observations: Sequence[Mapping[str, Any]]) -> None:
        normalized: dict[str, PublicObservation] = {}
        for raw in observations:
            assert_public_surface(raw)
            observation_id = raw.get("observation_id")
            interval = raw.get("interval")
            modalities = raw.get("modalities")
            payload = raw.get("payload", {})
            if not isinstance(observation_id, str) or not observation_id:
                raise SchemaViolation("OBSERVATION_ID_INVALID")
            if observation_id in normalized:
                raise SchemaViolation("OBSERVATION_ID_DUPLICATE")
            if (
                not isinstance(interval, Mapping)
                or not isinstance(interval.get("start_s"), (int, float))
                or not isinstance(interval.get("end_s"), (int, float))
                or isinstance(interval.get("start_s"), bool)
                or isinstance(interval.get("end_s"), bool)
                or float(interval["start_s"]) < 0
                or float(interval["end_s"]) <= float(interval["start_s"])
            ):
                raise SchemaViolation("OBSERVATION_INTERVAL_INVALID")
            if (
                not isinstance(modalities, list)
                or not modalities
                or any(
                    item not in {"vision", "speech", "ambient"}
                    for item in modalities
                )
                or len(set(modalities)) != len(modalities)
            ):
                raise SchemaViolation("OBSERVATION_MODALITIES_INVALID")
            if not isinstance(payload, Mapping):
                raise SchemaViolation("OBSERVATION_PAYLOAD_INVALID")
            normalized[observation_id] = PublicObservation(
                observation_id=observation_id,
                interval={
                    "start_s": float(interval["start_s"]),
                    "end_s": float(interval["end_s"]),
                },
                modalities=tuple(modalities),
                payload=dict(payload),
            )
        self._observations = normalized
        self.fingerprint = sha256_json(
            [
                item.to_public_dict()
                for item in sorted(
                    normalized.values(), key=lambda row: row.observation_id
                )
            ]
        )

    @property
    def observation_ids(self) -> frozenset[str]:
        return frozenset(self._observations)

    def public_observations(self) -> list[dict[str, Any]]:
        return [
            item.to_public_dict()
            for item in sorted(
                self._observations.values(), key=lambda row: row.observation_id
            )
        ]

    def validate_citation(self, citation: Mapping[str, Any]) -> None:
        observation_id = citation.get("observation_id")
        if observation_id not in self._observations:
            raise SchemaViolation(
                "CITATION_NOT_OBSERVED",
                details={"observation_id": observation_id},
            )
        observation = self._observations[str(observation_id)]
        if dict(citation.get("interval", {})) != dict(observation.interval):
            raise SchemaViolation(
                "CITATION_INTERVAL_MISMATCH",
                details={"observation_id": observation_id},
            )
        if list(citation.get("modalities", [])) != list(
            observation.modalities
        ):
            raise SchemaViolation(
                "CITATION_MODALITY_MISMATCH",
                details={"observation_id": observation_id},
            )


@dataclass(frozen=True)
class OutputProvenance:
    """Runner-side authorship attestation; never included in model prompts."""

    model_authored_paths: frozenset[str]
    deterministic_paths: frozenset[str] = frozenset()
    copied_paths: frozenset[str] = frozenset()

    def require_model_authored_answer(self) -> None:
        def covers(path: str, prefix: str) -> bool:
            return (
                path == prefix
                or path.startswith(prefix + ".")
                or prefix.startswith(path + ".")
            )

        for prefix in ANSWER_BEARING_PATH_PREFIXES:
            if any(
                covers(path, prefix) for path in self.deterministic_paths
            ):
                raise SchemaViolation(
                    "DETERMINISTIC_ANSWER_SUBSTITUTION",
                    details={"path": prefix},
                )
            if not any(
                covers(path, prefix) for path in self.model_authored_paths
            ):
                raise SchemaViolation(
                    "ANSWER_AUTHORSHIP_NOT_MODEL",
                    details={"path": prefix},
                )


@dataclass(frozen=True)
class IsolationAttestation:
    """Mutable runtime namespaces that must not cross states or R/N arms."""

    provider_session_id: str
    model_cache_namespace: str
    retrieval_cache_namespace: str
    tool_cache_namespace: str
    artifact_namespace: str
    generated_memory_namespace: str

    def __post_init__(self) -> None:
        values = tuple(self.to_dict().values())
        if any(not value for value in values):
            raise IsolationViolation("ISOLATION_NAMESPACE_EMPTY")

    def to_dict(self) -> dict[str, str]:
        return {
            "provider_session_id": self.provider_session_id,
            "model_cache_namespace": self.model_cache_namespace,
            "retrieval_cache_namespace": self.retrieval_cache_namespace,
            "tool_cache_namespace": self.tool_cache_namespace,
            "artifact_namespace": self.artifact_namespace,
            "generated_memory_namespace": self.generated_memory_namespace,
        }


def assert_isolated(attestations: Sequence[IsolationAttestation]) -> None:
    """Require every mutable namespace to be unique across compared states."""

    if len(attestations) < 2:
        return
    fields = tuple(attestations[0].to_dict())
    for field in fields:
        values = [item.to_dict()[field] for item in attestations]
        if len(set(values)) != len(values):
            raise IsolationViolation(
                "INVALID_CROSS_STATE_CONTAMINATION",
                details={"namespace_field": field},
            )
