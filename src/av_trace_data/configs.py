"""Audited adapter configurations and orthogonal access semantics."""

from __future__ import annotations

from dataclasses import dataclass

ACCESS_GATES = {"public", "token", "terms_acceptance", "external_agreement", "unresolved"}
PAYLOAD_STATES = {
    "release_payload_available",
    "metadata_only",
    "annotations_only",
    "card_only_payload_unavailable",
    "manual_distribution",
    "unresolved",
}
ADAPTER_STATES = {"active", "protocol_only", "manual_resolution"}


@dataclass(frozen=True)
class AccessCrosswalk:
    """Lossless mapping of an audited inventory status to technical access.

    Media rights and episode publication class are intentionally absent.  They
    must be recorded independently and cannot be derived from accessibility.
    """

    technical_access_status: str
    access_gate: str
    payload_state: str


ACCESS_STATUS_CROSSWALK: dict[str, AccessCrosswalk] = {
    "public_ungated": AccessCrosswalk(
        "public_ungated", "public", "release_payload_available"
    ),
    "public_ungated_metadata": AccessCrosswalk(
        "public_ungated_metadata", "public", "metadata_only"
    ),
    "public_ungated_annotations": AccessCrosswalk(
        "public_ungated_annotations", "public", "annotations_only"
    ),
    "public_card_only_payload_unavailable": AccessCrosswalk(
        "public_card_only_payload_unavailable",
        "public",
        "card_only_payload_unavailable",
    ),
    "public_ungated_high_risk": AccessCrosswalk(
        "public_ungated_high_risk", "public", "release_payload_available"
    ),
    "public_academic_restricted": AccessCrosswalk(
        "public_academic_restricted", "public", "release_payload_available"
    ),
    "gated_acceptance": AccessCrosswalk(
        "gated_acceptance", "terms_acceptance", "release_payload_available"
    ),
    "request_only_licensed": AccessCrosswalk(
        "request_only_licensed", "external_agreement", "manual_distribution"
    ),
    "manual_protocol_only": AccessCrosswalk(
        "manual_protocol_only", "unresolved", "unresolved"
    ),
}


def access_crosswalk(status: str) -> AccessCrosswalk:
    try:
        return ACCESS_STATUS_CROSSWALK[status]
    except KeyError as exc:
        choices = ", ".join(sorted(ACCESS_STATUS_CROSSWALK))
        raise ValueError(
            f"unmapped technical access status {status!r}; choose one of: {choices}"
        ) from exc


@dataclass(frozen=True)
class AdapterConfig:
    adapter_id: str
    dataset_id: str
    provider: str
    repository_id: str
    source_family: str
    technical_access_status: str
    media_rights_status: str
    publisher: str
    repository_kind: str = "dataset"
    adapter_state: str = "active"
    code_repository_id: str | None = None
    code_repository_provider: str | None = None
    identity_policy: str = "direct"
    legacy_access_mode: str = "downloadable_annotation_only"

    def __post_init__(self) -> None:
        access_crosswalk(self.technical_access_status)
        if self.adapter_state not in ADAPTER_STATES:
            raise ValueError(f"invalid adapter_state: {self.adapter_state!r}")
        if self.repository_kind not in {"dataset", "code", "manifest", "manual"}:
            raise ValueError(f"invalid repository_kind: {self.repository_kind!r}")
        if bool(self.code_repository_id) != bool(self.code_repository_provider):
            raise ValueError(
                "code_repository_id and code_repository_provider must be paired"
            )

    @property
    def access_gate(self) -> str:
        return access_crosswalk(self.technical_access_status).access_gate

    @property
    def payload_state(self) -> str:
        return access_crosswalk(self.technical_access_status).payload_state

    @property
    def access_mode(self) -> str:
        """Deprecated adapter route; not a rights or publication decision."""

        return self.legacy_access_mode


def _hf(
    adapter_id: str,
    repository_id: str,
    *,
    access_status: str = "public_ungated",
    media_rights_status: str = "unknown_hold",
    publisher: str | None = None,
    adapter_state: str = "active",
    code_repository_id: str | None = None,
    identity_policy: str = "direct",
) -> AdapterConfig:
    return AdapterConfig(
        adapter_id=adapter_id,
        dataset_id=adapter_id,
        provider="huggingface",
        repository_id=repository_id,
        source_family="COMPATIBILITY_ONLY",
        technical_access_status=access_status,
        media_rights_status=media_rights_status,
        publisher=publisher or repository_id.split("/", 1)[0],
        adapter_state=adapter_state,
        code_repository_id=code_repository_id,
        code_repository_provider="github" if code_repository_id else None,
        identity_policy=identity_policy,
    )


def _github(
    adapter_id: str,
    repository_id: str,
    *,
    source_family: str = "COMPATIBILITY_ONLY",
    access_status: str = "public_ungated",
    media_rights_status: str = "unknown_hold",
    publisher: str | None = None,
    repository_kind: str = "manifest",
    adapter_state: str = "active",
    identity_policy: str = "direct",
    legacy_access_mode: str = "downloadable_annotation_only",
) -> AdapterConfig:
    return AdapterConfig(
        adapter_id=adapter_id,
        dataset_id=adapter_id,
        provider="github",
        repository_id=repository_id,
        source_family=source_family,
        technical_access_status=access_status,
        media_rights_status=media_rights_status,
        publisher=publisher or repository_id.split("/", 1)[0],
        repository_kind=repository_kind,
        adapter_state=adapter_state,
        identity_policy=identity_policy,
        legacy_access_mode=legacy_access_mode,
    )


def _manual(
    adapter_id: str,
    repository_id: str,
    *,
    access_status: str,
    publisher: str,
    adapter_state: str,
    identity_policy: str,
) -> AdapterConfig:
    return AdapterConfig(
        adapter_id=adapter_id,
        dataset_id=adapter_id,
        provider="manual",
        repository_id=repository_id,
        source_family="COMPATIBILITY_ONLY",
        technical_access_status=access_status,
        media_rights_status="restricted",
        publisher=publisher,
        repository_kind="manual",
        adapter_state=adapter_state,
        identity_policy=identity_policy,
        legacy_access_mode="gated_agreement",
    )


PRIORITY_ADAPTERS: dict[str, AdapterConfig] = {
    # Audited dataset releases.  Code repository provenance is separate.
    "lovr": _hf(
        "lovr",
        "debugger123/LoVR-benchmark",
        code_repository_id="TechNomad-ds/LoVR-benchmark",
        identity_policy="longvideobench_lineage",
    ),
    "longvidsearch": _hf(
        "longvidsearch",
        "Fishiing/LongVidSearch",
        code_repository_id="yrywill/LongVidSearch",
        identity_policy="longvideobench_lineage",
    ),
    "flare": _hf(
        "flare",
        "AnonymousFLARE/FLARE",
        code_repository_id="YqjMartin/FLARE",
        identity_policy="video_mme_lineage",
    ),
    "longshotbench": _hf(
        "longshotbench",
        "MBZUAI/longshot-bench",
        code_repository_id="mbzuai-oryx/LongShOT",
        identity_policy="mapped_upstream",
    ),
    "videogaia": _hf("videogaia", "zfkarl/VideoGAIA"),
    "trace_vesbench": _hf(
        "trace_vesbench",
        "buaaplay/VES-Bench",
        code_repository_id="buaa-colalab/TRACE",
        identity_policy="mapped_upstream",
    ),
    "traceav_bench": _hf(
        "traceav_bench",
        "Heinz217/TraceAV-Bench",
        access_status="public_ungated_annotations",
        code_repository_id="Heinz217/TraceAV-Bench",
        identity_policy="mapped_upstream",
    ),
    "lvbench": _hf("lvbench", "zai-org/LVBench"),
    "video_mme": _hf(
        "video_mme",
        "lmms-lab/Video-MME",
        access_status="public_academic_restricted",
        media_rights_status="restricted",
        identity_policy="video_mme_lineage",
    ),
    "longvideobench": _hf(
        "longvideobench",
        "longvideobench/LongVideoBench",
        access_status="gated_acceptance",
        media_rights_status="restricted",
        code_repository_id="longvideobench/LongVideoBench",
        identity_policy="longvideobench_lineage",
    ),
    "longvideobench_meta": _hf(
        "longvideobench_meta",
        "longvideobench/LongVideoBench-Meta",
        access_status="public_ungated_metadata",
        identity_policy="longvideobench_lineage",
    ),
    # Code-only surface: not represented as a dataset release.
    "mlvu": _github(
        "mlvu",
        "JUNJIE99/MLVU",
        repository_kind="code",
        adapter_state="manual_resolution",
        identity_policy="mapped_upstream",
    ),
    # Explicitly non-executable sources required by the audited plan.
    "vragbench": _hf(
        "vragbench",
        "DISLab/VRAG-Bench",
        access_status="public_card_only_payload_unavailable",
        media_rights_status="restricted",
        adapter_state="protocol_only",
        identity_policy="mapped_upstream",
    ),
    "egolife": _hf(
        "egolife",
        "lmms-lab/EgoLife",
        access_status="public_ungated_high_risk",
        media_rights_status="restricted",
        code_repository_id="EvolvingLMMs-Lab/EgoLife",
        adapter_state="manual_resolution",
        identity_policy="direct",
    ),
    "ego4d": _manual(
        "ego4d",
        "Ego4D",
        access_status="request_only_licensed",
        publisher="Ego4D Consortium",
        adapter_state="manual_resolution",
        identity_policy="direct",
    ),
    "omnivideobench": _hf(
        "omnivideobench",
        "NJU-LINK/OmniVideoBench",
        access_status="gated_acceptance",
        media_rights_status="restricted",
        adapter_state="manual_resolution",
        identity_policy="direct",
    ),
    "nasa_media": _github(
        "nasa_media",
        "official/NASA-media-manifest",
        source_family="NASA",
        publisher="NASA",
        legacy_access_mode="downloadable_redistributable_raw",
    ),
    "nara_video": _github(
        "nara_video",
        "official/NARA-catalog-export",
        source_family="NARA",
        publisher="US National Archives",
        legacy_access_mode="downloadable_redistributable_raw",
    ),
    "noaa_media": _github(
        "noaa_media",
        "official/NOAA-media-manifest",
        source_family="NOAA",
        publisher="NOAA",
        legacy_access_mode="downloadable_redistributable_raw",
    ),
    "wikimedia_commons_video": _github(
        "wikimedia_commons_video",
        "official/Wikimedia-Commons-export",
        source_family="WIKIMEDIA_COMMONS",
        publisher="Wikimedia Commons",
        legacy_access_mode="downloadable_redistributable_raw",
    ),
}


def get_adapter_config(adapter_id: str) -> AdapterConfig:
    try:
        return PRIORITY_ADAPTERS[adapter_id]
    except KeyError as exc:
        choices = ", ".join(sorted(PRIORITY_ADAPTERS))
        raise KeyError(f"unknown adapter {adapter_id!r}; choose one of: {choices}") from exc
