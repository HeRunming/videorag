#!/usr/bin/env python3
"""Metadata-only reconnaissance for long, potentially audio-bearing videos.

The default ``offline`` mode normalizes the repository's pinned evidence.  The
optional ``live`` mode requests only official HTML/API metadata and HEAD
responses.  It has no media-download mode and rejects audio/video response
bodies.

This tool intentionally distinguishes:

* independently verified streams;
* item/container declarations;
* corpus-level claims and task labels; and
* unverified expectations.

Only the first class can establish that a selected rendition is audio-bearing.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

try:
    import httpx
except ImportError:  # pragma: no cover - exercised only by live CLI use
    httpx = None  # type: ignore[assignment]


AS_OF_DATE = "2026-09-09"
SCHEMA_VERSION = "1.1.0"
MIN_DURATION_S = 1_200.0
MAX_DURATION_S = 5_400.0
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 6

FLARE_DEMO_REPO = "AnonymousFLARE/FLARE_demo"
FLARE_DEMO_REVISION = "a7e85c038a16b86afe1109b33cd131ec80d67cb3"
FLARE_REPO = "AnonymousFLARE/FLARE"
FLARE_REVISION = "ed89d868647a3658fe6989ba06b7a7117c2624d9"
OMNI_REPO = "NJU-LINK/OmniVideoBench"
OMNI_REVISION = "1b1aa0899fca5aa92e4fe5dcd3b60be58efff6ca"
TRACEAV_REVISION = "cc96f31d1d30b56bd4be02bb660bee394896c288"
LVB_REVISION = "60d1c89c1919a198b73be39c2babb213b29d6a5c"

CANDIDATE_CSV = Path("data/rehearsal_plan/audio_asset_recon_candidates.csv")
ALLOWLIST_JSON = Path("data/rehearsal_plan/audio_asset_proposed_allowlist.json")
LIVE_EVIDENCE_JSON = Path(
    "data/rehearsal_plan/audio_asset_recon_live_evidence.json"
)
STREAM_PREFLIGHT_PROPOSAL_JSON = Path(
    "data/rehearsal_plan/audio_asset_stream_preflight_proposal.json"
)

ALLOWED_HOSTS = {
    "commons.wikimedia.org",
    "upload.wikimedia.org",
    "svs.gsfc.nasa.gov",
    "www.nasa.gov",
    "nasa.gov",
    "oceantoday.noaa.gov",
    "www.noaa.gov",
    "noaa.gov",
    "huggingface.co",
}
METADATA_CONTENT_TYPES = {
    "application/json",
    "application/ld+json",
    "text/html",
    "text/plain",
    "text/xml",
    "application/xml",
}
MEDIA_CONTENT_PREFIXES = ("audio/", "video/", "image/")
REDIRECT_CODES = {301, 302, 303, 307, 308}

CSV_FIELDS = [
    "candidate_id",
    "route_priority",
    "route_class",
    "shortlist_tier",
    "source_family",
    "title",
    "canonical_item_id",
    "official_item_url",
    "official_metadata_url",
    "release_id",
    "release_revision",
    "object_path",
    "object_blob_id",
    "object_size_bytes",
    "object_hash_algorithm",
    "object_hash",
    "declared_media_type",
    "declared_container",
    "exact_duration_s",
    "duration_evidence_class",
    "duration_gate",
    "audio_status",
    "audio_evidence_class",
    "audio_verified",
    "speech_status",
    "ambient_status",
    "subtitle_transcript_status",
    "duplicate_aliases",
    "official_download_url",
    "official_download_route_status",
    "access_status",
    "rights_status",
    "processing_rights_status",
    "annotation_rights_status",
    "publication_role",
    "likely_speech_score_0_5",
    "likely_ambient_score_0_5",
    "role_v_s_score_0_5",
    "role_v_a_score_0_5",
    "role_v_s_a_score_0_5",
    "item_selectivity_score_0_5",
    "access_clarity_score_0_5",
    "processing_rights_score_0_5",
    "annotation_rights_score_0_5",
    "public_core_fit_score_0_5",
    "compatibility_fit_score_0_5",
    "contamination_risk_score_0_5",
    "privacy_risk_score_0_5",
    "recon_priority_score_0_100",
    "evidence_sources",
    "metadata_conflicts",
    "unresolved_questions",
    "disposition",
    "notes",
]


class ReconError(RuntimeError):
    """Safe, credential-free reconnaissance error."""

    def __init__(self, code: str, **details: Any) -> None:
        super().__init__(code)
        self.code = code
        self.details = details

    def diagnostic(self) -> dict[str, Any]:
        return {"error": self.code, **self.details}


SENSITIVE_QUERY_KEYS = {
    "access_token",
    "auth",
    "authorization",
    "credential",
    "key",
    "signature",
    "token",
    "x-amz-credential",
    "x-amz-signature",
}
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def safe_endpoint(url: str) -> str:
    """Return a credential-free endpoint identity without query or fragment."""
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    netloc = hostname
    if parsed.port:
        netloc = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path or "/", "", ""))


def sanitize_exception_message(exc: BaseException) -> str:
    """Reduce a transport message without retaining tokens or signed URLs."""
    message = " ".join(str(exc).split())

    def replace_url(match: re.Match[str]) -> str:
        value = match.group(0).rstrip(".,);]")
        suffix = match.group(0)[len(value) :]
        try:
            return safe_endpoint(value) + suffix
        except (TypeError, ValueError):
            return "[REDACTED_URL]"

    message = URL_PATTERN.sub(replace_url, message)
    message = re.sub(
        r"(?i)\b(bearer|token|authorization|proxy-authorization)"
        r"\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        message,
    )
    for key in SENSITIVE_QUERY_KEYS:
        message = re.sub(
            rf"(?i)(\b{re.escape(key)}\b\s*[:=]\s*)[^\s,;&]+",
            r"\1[REDACTED]",
            message,
        )
    return message[:500] or exc.__class__.__name__


def exception_class(exc: BaseException) -> str:
    module = exc.__class__.__module__
    name = exc.__class__.__name__
    return f"{module}.{name}" if module not in {"builtins", "__main__"} else name


def _validate_proxy_url(proxy_url: str) -> None:
    parsed = urlsplit(proxy_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ReconError("INVALID_PROXY_CONFIGURATION")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ReconError("INVALID_PROXY_CONFIGURATION")


def proxy_label(proxy_url: str | None) -> str:
    if not proxy_url:
        return "environment-or-direct"
    parsed = urlsplit(proxy_url)
    label = parsed.hostname or "configured-proxy"
    if parsed.port:
        label = f"{label}:{parsed.port}"
    return label


def configured_proxy_urls(explicit: Sequence[str] | None = None) -> list[str]:
    """Resolve explicit or standard proxy settings without exposing userinfo."""
    values: list[str] = []
    if explicit:
        values.extend(explicit)
    else:
        for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            value = os.environ.get(name)
            if value:
                values.append(value)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        _validate_proxy_url(value)
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def load_hf_token() -> str | None:
    """Use an environment token or the existing HF login cache, in memory only."""
    token = os.environ.get("HF_TOKEN")
    if token:
        return token
    try:
        from huggingface_hub import get_token
    except ImportError:
        return None
    return get_token()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def semicolon(values: Iterable[str]) -> str:
    return ";".join(value for value in values if value)


def duration_gate(value: float | None) -> str:
    if value is None:
        return "UNRESOLVED"
    if MIN_DURATION_S <= value <= MAX_DURATION_S:
        return "PASS"
    return "FAIL"


@dataclass
class Candidate:
    candidate_id: str
    route_priority: int
    route_class: str
    shortlist_tier: str
    source_family: str
    title: str
    canonical_item_id: str
    official_item_url: str
    official_metadata_url: str = ""
    release_id: str = ""
    release_revision: str = ""
    object_path: str = ""
    object_blob_id: str = ""
    object_size_bytes: int | None = None
    object_hash_algorithm: str = ""
    object_hash: str = ""
    declared_media_type: str = ""
    declared_container: str = ""
    exact_duration_s: float | None = None
    duration_evidence_class: str = "unresolved"
    audio_status: str = "UNVERIFIED"
    audio_evidence_class: str = "none"
    audio_verified: bool = False
    speech_status: str = "UNVERIFIED"
    ambient_status: str = "UNVERIFIED"
    subtitle_transcript_status: str = "UNVERIFIED"
    duplicate_aliases: list[str] = field(default_factory=list)
    official_download_url: str = ""
    official_download_route_status: str = "UNRESOLVED"
    access_status: str = "UNRESOLVED"
    rights_status: str = "unknown_hold"
    processing_rights_status: str = "NOT_APPROVED"
    annotation_rights_status: str = "NOT_APPROVED"
    publication_role: str = "UNRESOLVED"
    likely_speech_score_0_5: int = 0
    likely_ambient_score_0_5: int = 0
    role_v_s_score_0_5: int = 0
    role_v_a_score_0_5: int = 0
    role_v_s_a_score_0_5: int = 0
    item_selectivity_score_0_5: int = 0
    access_clarity_score_0_5: int = 0
    processing_rights_score_0_5: int = 0
    annotation_rights_score_0_5: int = 0
    public_core_fit_score_0_5: int = 0
    compatibility_fit_score_0_5: int = 0
    contamination_risk_score_0_5: int = 0
    privacy_risk_score_0_5: int = 0
    evidence_sources: list[str] = field(default_factory=list)
    metadata_conflicts: list[dict[str, Any]] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    disposition: str = "DEFER"
    notes: str = ""

    def priority_score(self) -> int:
        """Triage score only; it never overrides hard gates."""
        positive = (
            3 * self.item_selectivity_score_0_5
            + 3 * self.access_clarity_score_0_5
            + 2 * self.processing_rights_score_0_5
            + 2 * self.annotation_rights_score_0_5
            + 2 * max(
                self.role_v_s_score_0_5,
                self.role_v_a_score_0_5,
                self.role_v_s_a_score_0_5,
            )
            + self.public_core_fit_score_0_5
            + self.compatibility_fit_score_0_5
        )
        if duration_gate(self.exact_duration_s) == "PASS":
            positive += 15
        if self.audio_verified:
            positive += 20
        negative = (
            2 * self.contamination_risk_score_0_5
            + self.privacy_risk_score_0_5
        )
        return max(0, min(100, positive - negative))

    def as_row(self) -> dict[str, Any]:
        row = {
            field_name: getattr(self, field_name)
            for field_name in CSV_FIELDS
            if hasattr(self, field_name)
        }
        row.update(
            {
                "duration_gate": duration_gate(self.exact_duration_s),
                "audio_verified": str(self.audio_verified).lower(),
                "duplicate_aliases": semicolon(self.duplicate_aliases),
                "recon_priority_score_0_100": self.priority_score(),
                "evidence_sources": semicolon(self.evidence_sources),
                "metadata_conflicts": json.dumps(
                    self.metadata_conflicts,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "unresolved_questions": semicolon(self.unresolved_questions),
            }
        )
        return {name: row.get(name, "") for name in CSV_FIELDS}


PUBLIC_SPECS: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "cand-061",
        "priority": 1,
        "tier": "PRIMARY",
        "speech": 5,
        "ambient": 1,
        "roles": (5, 1, 2),
        "access": 4,
        "public": 5,
        "privacy": 1,
        "contamination": 1,
        "publication": "PUBLIC_CORE_CANDIDATE",
    },
    {
        "candidate_id": "cand-023",
        "priority": 1,
        "tier": "HOLD",
        "speech": 5,
        "ambient": 2,
        "roles": (5, 2, 3),
        "access": 0,
        "public": 0,
        "privacy": 1,
        "contamination": 2,
        "publication": "IDENTITY_MAPPING_HOLD_NOT_ACTIVE",
    },
    {
        "candidate_id": "cand-048",
        "priority": 1,
        "tier": "PRIMARY",
        "speech": 4,
        "ambient": 4,
        "roles": (4, 4, 5),
        "access": 2,
        "public": 4,
        "privacy": 2,
        "contamination": 2,
        "publication": "PUBLIC_CORE_CANDIDATE",
    },
    {
        "candidate_id": "cand-056",
        "priority": 1,
        "tier": "RESERVE",
        "speech": 5,
        "ambient": 1,
        "roles": (5, 1, 2),
        "access": 4,
        "public": 3,
        "privacy": 1,
        "contamination": 2,
        "publication": "PUBLIC_CORE_RESERVE",
    },
    {
        "candidate_id": "cand-051",
        "priority": 1,
        "tier": "RESERVE",
        "speech": 4,
        "ambient": 3,
        "roles": (4, 3, 4),
        "access": 2,
        "public": 4,
        "privacy": 1,
        "contamination": 2,
        "publication": "PUBLIC_CORE_RESERVE",
    },
)

FLARE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "ccp-005",
        "item_id": "K759eXmaMTY",
        "tier": "COMPATIBILITY_PRIMARY",
        "sample": "sample_0",
        "speech": 4,
        "ambient": 4,
        "roles": (4, 4, 5),
    },
    {
        "candidate_id": "ccp-006",
        "item_id": "3uV8XZcIBbk",
        "tier": "COMPATIBILITY_PRIMARY",
        "sample": "sample_1",
        "speech": 4,
        "ambient": 4,
        "roles": (4, 4, 5),
    },
    {
        "candidate_id": "ccp-004",
        "item_id": "jWa2yrLGxCM",
        "tier": "COMPATIBILITY_RESERVE",
        "sample": "",
        "speech": 2,
        "ambient": 3,
        "roles": (2, 3, 3),
    },
)

OMNI_SPECS: tuple[dict[str, str], ...] = (
    {
        "candidate_id": "omni-video_284",
        "item_id": "video_284",
        "traceav_id": "video109",
        "tier": "GATED_COMPATIBILITY_PRIMARY",
    },
    {
        "candidate_id": "omni-video_617",
        "item_id": "video_617",
        "traceav_id": "video163",
        "tier": "GATED_COMPATIBILITY_PRIMARY",
    },
    {
        "candidate_id": "omni-video_611",
        "item_id": "video_611",
        "traceav_id": "video157",
        "tier": "GATED_COMPATIBILITY_RESERVE",
    },
)

LVB_IDS: tuple[tuple[str, str], ...] = (
    ("ccp-003", "-7wwfGJXEZg"),
    ("ccp-008", "-PgbM2MhcYQ"),
    ("ccp-009", "-eRimFrm6kQ"),
    ("ccp-011", "H5vpBCLo74U"),
    ("ccp-012", "TMe7oXMJoSM"),
)


def _public_candidates(root: Path) -> list[Candidate]:
    rows = {
        row["candidate_id"]: row
        for row in read_csv(root / "data/candidates/source_candidates.csv")
    }
    candidates: list[Candidate] = []
    for spec in PUBLIC_SPECS:
        candidate_id = spec["candidate_id"]
        source = rows[candidate_id]
        packet = read_json(
            root / "data/rehearsal_review/packets" / f"{candidate_id}.json"
        )
        packet_candidate = packet["candidate"]
        verification = packet["official_primary_source_verification"]
        duration = float(packet_candidate["duration_s_metadata"])
        acquisition = verification["acquisition_path"]
        source_family = source["source_family"]
        commons = source_family == "WIKIMEDIA_COMMONS"
        rights_score = 2 if commons else 1
        object_path = source["stable_source_id"].removeprefix("CommonsFile:") if commons else ""
        candidate = Candidate(
            candidate_id=candidate_id,
            route_priority=spec["priority"],
            route_class="PUBLIC_INSTITUTIONAL",
            shortlist_tier=spec["tier"],
            source_family=source_family,
            title=source["title"],
            canonical_item_id=source["stable_source_id"],
            official_item_url=source["canonical_landing_url"],
            official_metadata_url=source["canonical_landing_url"],
            object_path=object_path,
            declared_container="webm" if commons else "",
            exact_duration_s=duration,
            duration_evidence_class="official_item_page_metadata_not_stream_probe",
            audio_status="UNVERIFIED",
            audio_evidence_class="expected_modality_only_not_audio_evidence",
            speech_status="LIKELY_UNVERIFIED",
            ambient_status="LIKELY_UNVERIFIED",
            subtitle_transcript_status=source["transcript_caption_availability"],
            official_download_route_status=acquisition["status"],
            access_status=(
                "PUBLIC_OFFICIAL_ITEM_PAGE"
                if commons or candidate_id == "cand-023"
                else "PUBLIC_PAGE_NO_VERIFIED_TRANSFER_ROUTE"
            ),
            rights_status="unknown_hold",
            processing_rights_status="NOT_APPROVED",
            annotation_rights_status="NOT_APPROVED",
            publication_role=spec["publication"],
            likely_speech_score_0_5=spec["speech"],
            likely_ambient_score_0_5=spec["ambient"],
            role_v_s_score_0_5=spec["roles"][0],
            role_v_a_score_0_5=spec["roles"][1],
            role_v_s_a_score_0_5=spec["roles"][2],
            item_selectivity_score_0_5=5,
            access_clarity_score_0_5=spec["access"],
            processing_rights_score_0_5=rights_score,
            annotation_rights_score_0_5=rights_score,
            public_core_fit_score_0_5=spec["public"],
            compatibility_fit_score_0_5=2,
            contamination_risk_score_0_5=spec["contamination"],
            privacy_risk_score_0_5=spec["privacy"],
            evidence_sources=[
                "data/candidates/source_candidates.csv",
                f"data/rehearsal_review/packets/{candidate_id}.json",
            ],
            unresolved_questions=[
                *(
                    [
                        "Does any retained first-party evidence still bind this exact title and duration to NASA SVS ID 11205?",
                        "Was SVS ID 11205 repurposed, or was the candidate title-to-ID mapping originally wrong?",
                    ]
                    if candidate_id == "cand-023"
                    else []
                ),
                "Does the exact selected file independently expose and later decode a non-empty audio stream?",
                "What immutable file revision, byte size, and provider hash identify the selected rendition?",
                "Does item/component authority permit local decoding, audio extraction, ASR, indexing, and ML evaluation?",
                "May newly authored timestamp annotations be released, and under what attribution/takedown terms?",
                "Are music, slides, archival/partner footage, marks, speakers, and audience components cleared for the intended scope?",
            ],
            disposition=(
                "STALE_OR_MISMATCHED_ID_HOLD"
                if candidate_id == "cand-023"
                else (
                    "FAIL_CLOSED_PRIMARY_SHORTLIST"
                    if spec["tier"] == "PRIMARY"
                    else "FAIL_CLOSED_RESERVE_SHORTLIST"
                )
            ),
            notes=(
                (
                    "Parent live metadata fetched the official SVS 11205 page "
                    "on 2026-09-09, but the expected title was absent. The "
                    "captured response behavior cannot distinguish a stale, "
                    "repurposed, or originally incorrect mapping. Retain the "
                    "pinned duration only as disputed historical metadata; do "
                    "not treat this candidate as active and do not invent a "
                    "replacement URL. "
                )
                if candidate_id == "cand-023"
                else ""
            )
            + (
                "Likelihood and role scores are triage hypotheses, not audio or "
                "modality verification."
            ),
        )
        if candidate_id == "cand-023":
            candidate.duration_evidence_class = (
                "pinned_official_page_metadata_bound_to_disputed_identity"
            )
            candidate.evidence_sources.append(str(LIVE_EVIDENCE_JSON))
        candidates.append(candidate)
    return candidates


def _sibling_index(api: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        item["rfilename"]: item
        for item in api.get("siblings", [])
        if isinstance(item, Mapping) and isinstance(item.get("rfilename"), str)
    }


def _file_aliases(api: Mapping[str, Any], path: str) -> list[str]:
    siblings = _sibling_index(api)
    item = siblings.get(path)
    if not item:
        return []
    lfs = item.get("lfs") if isinstance(item.get("lfs"), Mapping) else {}
    digest = lfs.get("sha256") or item.get("blobId")
    if not digest:
        return []
    aliases = []
    for other_path, other in siblings.items():
        other_lfs = other.get("lfs") if isinstance(other.get("lfs"), Mapping) else {}
        other_digest = other_lfs.get("sha256") or other.get("blobId")
        if other_path != path and other_digest == digest:
            aliases.append(other_path)
    return sorted(aliases)


def _conflict_value(field_name: str, value: Any) -> Any:
    if field_name.endswith("_url") and isinstance(value, str) and value:
        return safe_endpoint(value)
    return value


def _merge_evidence_field(
    candidate: Candidate,
    field_name: str,
    evidence_value: Any,
    evidence_source: str,
    *,
    conflict_is_fatal: bool,
) -> bool:
    """Merge metadata without degrading or silently replacing stronger facts.

    Empty/absent fields are ignored. A non-empty value can fill an
    unresolved field or confirm an equal pinned value. Any different non-empty
    value is retained as an explicit conflict while the pinned value remains
    authoritative pending review.
    """
    if evidence_value is None or evidence_value == "":
        return False
    pinned_value = getattr(candidate, field_name)
    if pinned_value is None or pinned_value == "":
        setattr(candidate, field_name, evidence_value)
        return True
    if pinned_value == evidence_value:
        return False
    conflict = {
        "field": field_name,
        "pinned_value": _conflict_value(field_name, pinned_value),
        "live_value": _conflict_value(field_name, evidence_value),
        "evidence_source": evidence_source,
    }
    if conflict not in candidate.metadata_conflicts:
        candidate.metadata_conflicts.append(conflict)
    if candidate.disposition != "STALE_OR_MISMATCHED_ID_HOLD":
        candidate.disposition = "METADATA_CONFLICT_HOLD"
    if conflict_is_fatal:
        raise ReconError(
            "LIVE_METADATA_CONFLICT",
            candidate_id=candidate.candidate_id,
            field=field_name,
            pinned_value=conflict["pinned_value"],
            live_value=conflict["live_value"],
            evidence_source=evidence_source,
        )
    return False


def _apply_hf_object(
    candidate: Candidate,
    api: Mapping[str, Any],
    path: str,
    *,
    evidence_source: str = "pinned_hf_snapshot",
    conflict_is_fatal: bool = False,
) -> None:
    item = _sibling_index(api).get(path)
    if not item:
        return
    _merge_evidence_field(
        candidate,
        "object_path",
        path,
        evidence_source,
        conflict_is_fatal=conflict_is_fatal,
    )
    blob_id = item.get("blobId")
    if blob_id is not None:
        _merge_evidence_field(
            candidate,
            "object_blob_id",
            str(blob_id),
            evidence_source,
            conflict_is_fatal=conflict_is_fatal,
        )
    size = item.get("size")
    if isinstance(size, int):
        _merge_evidence_field(
            candidate,
            "object_size_bytes",
            int(size),
            evidence_source,
            conflict_is_fatal=conflict_is_fatal,
        )
    lfs = item.get("lfs") if isinstance(item.get("lfs"), Mapping) else {}
    if lfs.get("sha256"):
        _merge_evidence_field(
            candidate,
            "object_hash_algorithm",
            "sha256",
            evidence_source,
            conflict_is_fatal=conflict_is_fatal,
        )
        _merge_evidence_field(
            candidate,
            "object_hash",
            str(lfs["sha256"]),
            evidence_source,
            conflict_is_fatal=conflict_is_fatal,
        )
    aliases = _file_aliases(api, path)
    if aliases:
        if candidate.duplicate_aliases and candidate.duplicate_aliases != aliases:
            conflict = {
                "field": "duplicate_aliases",
                "pinned_value": candidate.duplicate_aliases,
                "live_value": aliases,
                "evidence_source": evidence_source,
            }
            candidate.metadata_conflicts.append(conflict)
            candidate.disposition = "METADATA_CONFLICT_HOLD"
            if conflict_is_fatal:
                raise ReconError(
                    "LIVE_METADATA_CONFLICT",
                    candidate_id=candidate.candidate_id,
                    **conflict,
                )
            return
        candidate.duplicate_aliases = aliases
    download_url = (
        "https://huggingface.co/datasets/"
        f"{candidate.release_id}/resolve/{candidate.release_revision}/"
        f"{quote(path, safe='/')}"
    )
    _merge_evidence_field(
        candidate,
        "official_download_url",
        download_url,
        evidence_source,
        conflict_is_fatal=conflict_is_fatal,
    )


def _flare_candidates(root: Path) -> list[Candidate]:
    pool = {
        row["candidate_id"]: row
        for row in read_csv(root / "data/rehearsal_plan/concrete_candidate_pool.csv")
    }
    demo_api = read_json(
        root / "data/hf_recon/snapshots/hf_api_AnonymousFLARE_FLARE_demo.json"
    )
    candidates: list[Candidate] = []
    for spec in FLARE_SPECS:
        row = pool[spec["candidate_id"]]
        item_id = spec["item_id"]
        demo = bool(spec["sample"])
        repo = FLARE_DEMO_REPO if demo else FLARE_REPO
        revision = FLARE_DEMO_REVISION if demo else FLARE_REVISION
        object_path = f"{spec['sample']}/{item_id}.mp4" if demo else ""
        candidate = Candidate(
            candidate_id=spec["candidate_id"],
            route_priority=3,
            route_class="FLARE_VIDEOMME",
            shortlist_tier=spec["tier"],
            source_family="FLARE / Video-MME",
            title=f"FLARE/Video-MME exact item {item_id}",
            canonical_item_id=f"videomme:{item_id}",
            official_item_url=(
                f"https://huggingface.co/datasets/{repo}/tree/{revision}/"
                f"{spec['sample']}".rstrip("/")
            ),
            official_metadata_url=f"https://huggingface.co/api/datasets/{repo}",
            release_id=repo,
            release_revision=revision,
            object_path=object_path,
            declared_media_type="video/mp4" if demo else "audio/wav-derived-only",
            declared_container="mp4" if demo else "unresolved_full_source",
            exact_duration_s=None,
            duration_evidence_class="videomme_categorical_medium_not_exact_seconds",
            audio_status=(
                "CORPUS_OR_GENERATED_CAPTION_CLAIM_UNVERIFIED"
                if demo
                else "DERIVED_WAV_LISTED_FULL_SOURCE_UNVERIFIED"
            ),
            audio_evidence_class=(
                "corpus_claim_and_generated_caption_not_item_stream_metadata"
                if demo
                else "derived_artifact_identity_not_full_source_stream_metadata"
            ),
            speech_status="LIKELY_FROM_GENERATED_TEXT_ONLY_NOT_VERIFIED",
            ambient_status="LIKELY_FROM_GENERATED_TEXT_ONLY_NOT_VERIFIED",
            subtitle_transcript_status="NO_HUMAN_SUBTITLE_OR_TRANSCRIPT_VERIFIED",
            official_download_route_status=(
                "OFFICIAL_HF_OBJECT_LISTED_NOT_AUTHORIZED"
                if demo
                else "NO_COMPLETE_SOURCE_OBJECT_IDENTIFIED"
            ),
            access_status=(
                "PUBLIC_HF_REPOSITORY" if demo else "PUBLIC_METADATA_ARCHIVES"
            ),
            rights_status="unknown_hold",
            processing_rights_status="NOT_APPROVED_FLARE_01_CLARIFICATION_ONLY",
            annotation_rights_status="NOT_APPROVED",
            publication_role="EXTERNAL_COMPATIBILITY_UNPOOLED_ONLY",
            likely_speech_score_0_5=spec["speech"],
            likely_ambient_score_0_5=spec["ambient"],
            role_v_s_score_0_5=spec["roles"][0],
            role_v_a_score_0_5=spec["roles"][1],
            role_v_s_a_score_0_5=spec["roles"][2],
            item_selectivity_score_0_5=5 if demo else 3,
            access_clarity_score_0_5=3 if demo else 1,
            processing_rights_score_0_5=0,
            annotation_rights_score_0_5=0,
            public_core_fit_score_0_5=0,
            compatibility_fit_score_0_5=5,
            contamination_risk_score_0_5=5,
            privacy_risk_score_0_5=2,
            evidence_sources=[
                "data/rehearsal_plan/concrete_candidate_pool.csv",
                (
                    "data/hf_recon/snapshots/"
                    "hf_api_AnonymousFLARE_FLARE_demo.json"
                    if demo
                    else "data/hf_recon/snapshots/hf_api_AnonymousFLARE_FLARE.json"
                ),
                "data/hf_recon/snapshots/"
                "videomme_parent_rows_ead1408f75b618502df9a1d8e0950166bf0a2a0b_targets.json",
                "data/access_review/request_scope.csv",
            ],
            unresolved_questions=[
                "What is the exact full-source duration in seconds, and is it within 1,200–5,400 seconds?",
                "Does the exact full MP4 independently expose and later decode a non-empty synchronized audio stream?",
                "Which artifact classes are covered by FLARE's displayed CC BY 4.0 field versus Video-MME/source-owner restrictions?",
                "Are decoding, audio sampling, ASR, feature extraction, and temporary derivatives authorized?",
                "May new non-media AV-TRACE annotations be released, and what deletion/takedown terms apply?",
            ],
            disposition="DEFER_PENDING_EXACT_DURATION_STREAM_AND_RIGHTS",
            notes=(
                "Generated audio/unified captions and corpus claims are selection "
                "aids only and never count as audio verification."
            ),
        )
        if demo:
            _apply_hf_object(candidate, demo_api, object_path)
        candidates.append(candidate)
    return candidates


def _omni_candidates(root: Path) -> list[Candidate]:
    api = read_json(
        root / "data/hf_recon/snapshots/hf_api_NJU-LINK_OmniVideoBench.json"
    )
    join = read_json(
        root
        / "data/hf_recon/snapshots/"
        "traceav_modality_lvb_join_"
        f"{TRACEAV_REVISION}_{'cdf3444602208c95f453e7683583a077ce38ddbf'}.json"
    )
    candidates: list[Candidate] = []
    for spec in OMNI_SPECS:
        item_id = spec["item_id"]
        rows = [
            row
            for row in join["row_join_audit"]
            if row.get("mapped_parent_id") == item_id
        ]
        classes = {str(row.get("modality_file_class")) for row in rows}
        speech = 4 if "speech" in classes else 1
        ambient = 4 if "environmental" in classes else 1
        cross = 5 if "crossmodal" in classes else 2
        candidate = Candidate(
            candidate_id=spec["candidate_id"],
            route_priority=4,
            route_class="TRACEAV_OMNIVIDEOBENCH",
            shortlist_tier=spec["tier"],
            source_family="TraceAV / OmniVideoBench",
            title=f"OmniVideoBench {item_id} mapped from TraceAV {spec['traceav_id']}",
            canonical_item_id=f"omnivideobench:{item_id}",
            official_item_url=(
                f"https://huggingface.co/datasets/{OMNI_REPO}/blob/"
                f"{OMNI_REVISION}/videos/{item_id}.mp4"
            ),
            official_metadata_url=f"https://huggingface.co/api/datasets/{OMNI_REPO}",
            release_id=OMNI_REPO,
            release_revision=OMNI_REVISION,
            object_path=f"videos/{item_id}.mp4",
            declared_media_type="video/mp4",
            declared_container="mp4",
            exact_duration_s=None,
            duration_evidence_class="traceav_evidence_extent_only_not_source_duration",
            audio_status="CORPUS_AND_TASK_LABEL_CLAIM_UNVERIFIED",
            audio_evidence_class="corpus_claim_and_task_labels_not_item_stream_metadata",
            speech_status=(
                "TASK_LABEL_SELECTION_LEAD_NOT_VERIFIED"
                if "speech" in classes
                else "UNVERIFIED"
            ),
            ambient_status=(
                "TASK_LABEL_SELECTION_LEAD_NOT_VERIFIED"
                if "environmental" in classes
                else "UNVERIFIED"
            ),
            subtitle_transcript_status="UNVERIFIED",
            official_download_route_status="GATED_OFFICIAL_HF_OBJECT_NOT_APPROVED",
            access_status="GATED_APPLICATION_REQUIRED",
            rights_status="unknown_hold",
            processing_rights_status="NOT_APPROVED_SCOPE_NOT_IN_OMNI_01",
            annotation_rights_status="NOT_APPROVED",
            publication_role="EXTERNAL_COMPATIBILITY_UNPOOLED_ONLY",
            likely_speech_score_0_5=speech,
            likely_ambient_score_0_5=ambient,
            role_v_s_score_0_5=speech,
            role_v_a_score_0_5=ambient,
            role_v_s_a_score_0_5=cross,
            item_selectivity_score_0_5=5,
            access_clarity_score_0_5=2,
            processing_rights_score_0_5=0,
            annotation_rights_score_0_5=0,
            public_core_fit_score_0_5=0,
            compatibility_fit_score_0_5=5,
            contamination_risk_score_0_5=5,
            privacy_risk_score_0_5=3,
            evidence_sources=[
                "data/hf_recon/snapshots/hf_api_NJU-LINK_OmniVideoBench.json",
                "data/hf_recon/snapshots/"
                "traceav_modality_lvb_join_"
                f"{TRACEAV_REVISION}_cdf3444602208c95f453e7683583a077ce38ddbf.json",
                "data/access_review/request_scope.csv",
            ],
            unresolved_questions=[
                "What is the exact source duration in seconds, and does it pass the 1,200–5,400-second gate?",
                "Does this exact MP4 independently expose and later decode a non-empty synchronized audio stream?",
                "Does the live gate authorize this exact item and internal transformations under the displayed CC BY-NC-ND 4.0 field?",
                "May newly authored timestamp annotations be released without redistributing source media?",
                "Does item-level provenance reveal source-owner restrictions, duplicate/re-upload aliases, or elevated privacy risk?",
            ],
            disposition="DEFER_PENDING_NEW_ITEM_SCOPE_DURATION_STREAM_AND_RIGHTS",
            notes=(
                "TraceAV task labels are selection aids only. They do not prove "
                "audio, speech, ambient usability, or cross-modal necessity."
            ),
        )
        _apply_hf_object(candidate, api, candidate.object_path)
        candidates.append(candidate)
    return candidates


def _lvb_alternate_candidates(root: Path) -> list[Candidate]:
    status_rows = {
        row["candidate_id"]: row
        for row in read_csv(
            root / "data/rehearsal_plan/lvb01_verified_asset_status.csv"
        )
    }
    pool = {
        row["candidate_id"]: row
        for row in read_csv(root / "data/rehearsal_plan/concrete_candidate_pool.csv")
    }
    candidates: list[Candidate] = []
    for ccp_id, item_id in LVB_IDS:
        status = status_rows[ccp_id]
        pool_row = pool[ccp_id]
        duration = float(status["duration_s"])
        candidate = Candidate(
            candidate_id=f"lvb-alt-{ccp_id}",
            route_priority=5,
            route_class="LVB_AUTHORIZED_SYNCHRONIZED_ALTERNATE",
            shortlist_tier="SALVAGE_ONLY",
            source_family="LongVideoBench / source-owner alternate",
            title=f"Authorized synchronized audio-bearing alternate for {item_id}",
            canonical_item_id=f"longvideobench:{item_id}",
            official_item_url=(
                f"https://huggingface.co/datasets/longvideobench/LongVideoBench/"
                f"tree/{LVB_REVISION}"
            ),
            official_metadata_url=(
                "https://huggingface.co/api/datasets/"
                "longvideobench/LongVideoBench"
            ),
            release_id="longvideobench/LongVideoBench",
            release_revision=LVB_REVISION,
            object_path=f"{item_id}.mp4 (current silent baseline only)",
            declared_media_type="video/mp4",
            declared_container="mp4",
            exact_duration_s=duration,
            duration_evidence_class="independent_local_probe_current_silent_rendition",
            audio_status="VERIFIED_ABSENT_CURRENT_RENDITION_ALTERNATE_NOT_LOCATED",
            audio_evidence_class="independent_stream_probe_current_rendition_only",
            audio_verified=False,
            speech_status="SUBTITLE_PROXY_ONLY_NOT_AUDIO",
            ambient_status="UNAVAILABLE_CURRENT_RENDITION",
            subtitle_transcript_status=pool_row["transcript_status"],
            official_download_route_status="NO_AUTHORIZED_ALTERNATE_LOCATED",
            access_status="MAINTAINER_OR_SOURCE_OWNER_DELIVERY_REQUIRED",
            rights_status="unknown_hold",
            processing_rights_status="NOT_APPROVED_FOR_ALTERNATE",
            annotation_rights_status="NOT_APPROVED",
            publication_role="SALVAGE_ROUTE_NOT_A_CURRENT_ASSET",
            likely_speech_score_0_5=1,
            likely_ambient_score_0_5=0,
            role_v_s_score_0_5=1,
            role_v_a_score_0_5=0,
            role_v_s_a_score_0_5=0,
            item_selectivity_score_0_5=5,
            access_clarity_score_0_5=0,
            processing_rights_score_0_5=0,
            annotation_rights_score_0_5=0,
            public_core_fit_score_0_5=0,
            compatibility_fit_score_0_5=1,
            contamination_risk_score_0_5=4,
            privacy_risk_score_0_5=2,
            evidence_sources=[
                "data/rehearsal_plan/lvb01_verified_asset_status.csv",
                "docs/review/lvb01_download_media_audit.md",
                "docs/review/lvb01_post_download_decision.md",
            ],
            unresolved_questions=[
                "Was audio intentionally stripped from the released processed MP4?",
                "Does a maintainer- or source-owner-authorized complete audio-bearing rendition exist for this exact source ID?",
                "What checksum, duration, edit history, and timeline relation prove synchronization with the audited silent rendition?",
                "What explicit transfer, processing, annotation, and deletion authority covers the alternate?",
            ],
            disposition="REJECT_CURRENT_RENDITION_DEFER_ALTERNATE_UNTIL_LOCATED",
            notes=(
                "The current exact MP4 is independently verified to have zero "
                "audio streams. Subtitles do not establish speech audio."
            ),
        )
        candidates.append(candidate)
    return candidates


def build_candidates(root: Path) -> list[Candidate]:
    candidates = (
        _public_candidates(root)
        + _flare_candidates(root)
        + _omni_candidates(root)
        + _lvb_alternate_candidates(root)
    )
    ids = [candidate.candidate_id for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise ReconError("DUPLICATE_NORMALIZED_CANDIDATE_ID")
    return candidates


def proposed_allowlist(
    candidates: Sequence[Candidate],
    mode: str,
    live_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    primary_ids = ["cand-061", "cand-048", "cand-051"]
    reserve_ids = ["cand-056"]

    def item(candidate_id: str, proposed_role: str) -> dict[str, Any]:
        candidate = by_id[candidate_id]
        return {
            "candidate_id": candidate.candidate_id,
            "canonical_item_id": candidate.canonical_item_id,
            "title": candidate.title,
            "source_family": candidate.source_family,
            "official_item_url": candidate.official_item_url,
            "exact_duration_s": candidate.exact_duration_s,
            "duration_gate": duration_gate(candidate.exact_duration_s),
            "proposed_role": proposed_role,
            "audio_status": candidate.audio_status,
            "audio_verified": candidate.audio_verified,
            "rights_status": candidate.rights_status,
            "processing_rights_status": candidate.processing_rights_status,
            "annotation_rights_status": candidate.annotation_rights_status,
                "official_download_route_status": candidate.official_download_route_status,
                "official_download_url": candidate.official_download_url,
                "metadata_conflicts": candidate.metadata_conflicts,
                "unresolved_questions": candidate.unresolved_questions,
            }

    excluded = []
    for candidate in candidates:
        if candidate.candidate_id in primary_ids + reserve_ids:
            continue
        excluded.append(
            {
                "candidate_id": candidate.candidate_id,
                "canonical_item_id": candidate.canonical_item_id,
                "reason": candidate.disposition,
                "audio_status": candidate.audio_status,
                "duration_gate": duration_gate(candidate.exact_duration_s),
            }
        )
    result = {
        "schema_version": SCHEMA_VERSION,
        "prepared_as_of": AS_OF_DATE,
        "generation_mode": mode,
        "decision": "FAIL_CLOSED_SHORTLIST_ONLY_NO_TRANSFER_ALLOWLIST_ISSUED",
        "decision_reason": (
            "No candidate has both independently verified audio on the exact "
            "proposed rendition and approved item-level processing rights. "
            "cand-023 is separately held because the live official SVS page did "
            "not contain its pinned title. The coherent entries below are "
            "ranking proposals only, not authorization to acquire media."
        ),
        "authorized_for_transfer": [],
        "audio_verified_count": sum(
            1 for candidate in candidates if candidate.audio_verified
        ),
        "proposed_primary_after_gate_resolution": [
            item("cand-061", "speech-heavy V+S anchor"),
            item("cand-048", "field/webinar candidate for V+A / V+S+A"),
            item("cand-051", "environmental-program V+S+A candidate"),
        ],
        "proposed_reserves_after_gate_resolution": [
            item("cand-056", "speech-heavy V+S reserve"),
        ],
        "activation_requirements": [
            "Freeze an immutable exact file identity, byte size, provider hash, and official item-level route.",
            "Confirm exact duration is 1,200–5,400 seconds.",
            "Obtain direct approval for local decoding, audio extraction/sampling, ASR, indexing, and ML evaluation.",
            "Keep annotation/publication approval separate from acquisition and processing approval.",
            "After authorized acquisition, independently verify at least one decodable, non-empty, synchronized audio stream.",
            "Inspect actual audio to establish speech and/or ambient content; captions, task labels, and corpus claims are insufficient.",
            "Complete duplicate, component-rights, contamination, privacy, attribution, retention, and takedown review.",
        ],
        "compatibility_candidates_not_in_transfer_scope": [
            "ccp-005",
            "ccp-006",
            "ccp-004",
            "omni-video_284",
            "omni-video_617",
            "omni-video_611",
        ],
        "rejected_or_deferred": excluded,
    }
    if live_evidence is not None:
        result["live_precheck_status"] = live_evidence["status"]
        result["live_precheck_complete"] = bool(
            live_evidence["status"] == "PASS"
        )
        result["live_evidence_path"] = str(LIVE_EVIDENCE_JSON)
    return result


def stream_preflight_proposal(
    candidates: Sequence[Candidate],
    live_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a fail-closed next-action proposal; never an acquisition grant."""
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    public_priority = [
        ("cand-061", "freeze Commons page/revision/original/hash/size and rights"),
        ("cand-056", "freeze Commons page/revision/original/hash/size and license"),
        ("cand-048", "obtain an official NOAA/rightsholder delivery object"),
        ("cand-051", "obtain an official NOAA/rightsholder delivery object"),
    ]

    def request_item(candidate_id: str, request: str) -> dict[str, Any]:
        candidate = by_id[candidate_id]
        return {
            "candidate_id": candidate_id,
            "canonical_item_id": candidate.canonical_item_id,
            "official_item_url": candidate.official_item_url,
            "current_object_path": candidate.object_path,
            "current_release_revision": candidate.release_revision,
            "current_object_size_bytes": candidate.object_size_bytes,
            "current_object_hash_algorithm": candidate.object_hash_algorithm,
            "current_object_hash": candidate.object_hash,
            "request": request,
            "required_before_stream_preflight": [
                "immutable exact object identity and official delivery route",
                "provider byte size and hash",
                "item-level authorization for the bounded header request",
            ],
            "required_before_full_acquisition": [
                "item-level acquisition and processing approval",
                "component-rights and privacy review",
                "retention, deletion, attribution, and takedown terms",
            ],
        }

    compatibility_ids = [
        "ccp-005",
        "ccp-006",
        "ccp-004",
        "omni-video_284",
        "omni-video_617",
        "omni-video_611",
    ]
    exact_compatibility = []
    for candidate_id in compatibility_ids:
        candidate = by_id[candidate_id]
        exact_compatibility.append(
            {
                "candidate_id": candidate_id,
                "release_id": candidate.release_id,
                "release_revision": candidate.release_revision,
                "object_path": candidate.object_path,
                "object_size_bytes": candidate.object_size_bytes,
                "object_hash_algorithm": candidate.object_hash_algorithm,
                "object_hash": candidate.object_hash,
                "duration_gate": duration_gate(candidate.exact_duration_s),
                "audio_verified": candidate.audio_verified,
                "processing_rights_status": candidate.processing_rights_status,
                "disposition": "DEFER_NO_PREFLIGHT_AUTHORITY",
                "reason": (
                    "Exact repository object metadata alone does not establish "
                    "duration, decoded audio, or item-level processing authority."
                    if candidate.object_hash
                    else "No complete exact source object is identified."
                ),
            }
        )

    return {
        "schema_version": "1.0.0",
        "prepared_as_of": AS_OF_DATE,
        "live_evidence_status": live_evidence["status"],
        "decision": "NO_GO_STREAM_PREFLIGHT_OR_ACQUISITION",
        "decision_reason": (
            "The parent live official-metadata pass was partial. No coherent "
            "public shortlist item combines an immutable exact byte object with "
            "item-level preflight/acquisition authority; cand-023 is excluded "
            "because its title-to-SVS-ID mapping failed live identity "
            "normalization. Existing exact compatibility objects also lack "
            "duration and processing approval."
        ),
        "authorized_for_stream_header_preflight": [],
        "authorized_for_full_acquisition": [],
        "authorized_for_transfer": [],
        "next_authorized_action": (
            "Rerun only the repaired metadata-only live precheck. For Commons, "
            "allow the official item-page HTML fallback if the API remains "
            "blocked. Submit the four coherent item-scoped identity and "
            "authority requests below; investigate cand-023 identity separately. "
            "Do not request media bytes."
        ),
        "item_scoped_identity_and_authority_requests": [
            request_item(candidate_id, request)
            for candidate_id, request in public_priority
        ],
        "conditional_preflight_priority_after_all_required_fields_are_met": [
            "cand-061",
            "cand-056",
            "cand-048",
            "cand-051",
        ],
        "conditional_preflight_limit": (
            "Choose 3–5 from the ordered list only after each chosen object has "
            "a frozen identity and explicit bounded-preflight authority."
        ),
        "identity_mapping_holds": [
            {
                "candidate_id": "cand-023",
                "title": by_id["cand-023"].title,
                "pinned_canonical_item_id": by_id["cand-023"].canonical_item_id,
                "pinned_official_item_url": by_id["cand-023"].official_item_url,
                "disposition": by_id["cand-023"].disposition,
                "reason": (
                    "The parent live HTTP 200 response for NASA SVS 11205 did "
                    "not contain the expected title. The retained evidence is "
                    "insufficient to determine whether the ID is stale, "
                    "repurposed, or was incorrectly mapped."
                ),
                "required_resolution": (
                    "Direct first-party evidence binding this exact title and "
                    "duration to a valid official ID/page; do not infer or "
                    "invent a replacement URL."
                ),
            }
        ],
        "exact_compatibility_objects_deferred": exact_compatibility,
        "safety_boundary": [
            "No media payload or media-object Range GET is authorized by this file.",
            "HEAD is metadata only and cannot establish a decoded audio stream.",
            "Container/MIME/audio-codec declarations do not set audio_verified=true.",
            "Processing, annotation, and release authority remain separate gates.",
        ],
    }


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    temp_path.replace(path)


def write_outputs(
    root: Path,
    candidates: Sequence[Candidate],
    allowlist: Mapping[str, Any],
    preflight_proposal: Mapping[str, Any] | None = None,
) -> None:
    csv_path = root / CANDIDATE_CSV
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(candidate.as_row())
    json_path = root / ALLOWLIST_JSON
    _atomic_json_write(json_path, allowlist)
    if preflight_proposal is not None:
        proposal_path = root / STREAM_PREFLIGHT_PROPOSAL_JSON
        _atomic_json_write(proposal_path, preflight_proposal)


class MetadataClient:
    """Bounded client that cannot fetch a media response body."""

    def __init__(
        self,
        token: str | None = None,
        *,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
        client: Any = None,
        proxies: Sequence[str] | None = None,
    ) -> None:
        if httpx is None and client is None:
            raise ReconError("LIVE_MODE_REQUIRES_HTTPX")
        self.token = token
        self.max_response_bytes = max_response_bytes
        self.max_total_bytes = max_total_bytes
        self.total_bytes = 0
        self.records: list[dict[str, Any]] = []
        if client is not None and proxies:
            raise ReconError("CLIENT_AND_PROXY_CONFIGURATION_CONFLICT")
        if client is not None:
            self._clients = [("injected-client", client)]
        else:
            proxy_urls = configured_proxy_urls(proxies)
            if proxy_urls:
                self._clients = [
                    (
                        proxy_label(proxy_url),
                        httpx.Client(
                            proxy=proxy_url,
                            trust_env=False,
                            follow_redirects=False,
                            timeout=httpx.Timeout(30.0, connect=15.0),
                            headers={
                                "User-Agent": "AV-TRACE-audio-asset-recon/1.1"
                            },
                        ),
                    )
                    for proxy_url in proxy_urls
                ]
            else:
                self._clients = [
                    (
                        "environment-or-direct",
                        httpx.Client(
                            trust_env=True,
                            follow_redirects=False,
                            timeout=httpx.Timeout(30.0, connect=15.0),
                            headers={
                                "User-Agent": "AV-TRACE-audio-asset-recon/1.1"
                            },
                        ),
                    )
                ]
        self.proxy_routes = [label for label, _ in self._clients]

    def close(self) -> None:
        for _, client in self._clients:
            client.close()

    def __enter__(self) -> "MetadataClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ReconError("UNSAFE_METADATA_URL")
        if not parsed.hostname or parsed.hostname.lower() not in ALLOWED_HOSTS:
            raise ReconError("OFFICIAL_HOST_NOT_ALLOWLISTED")

    def _headers(self, url: str) -> dict[str, str]:
        headers = {"Accept": "application/json,text/html,text/plain;q=0.8"}
        if self.token and urlsplit(url).hostname == "huggingface.co":
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request_stream(self, method: str, url: str, purpose: str) -> tuple[Any, str]:
        self._validate_url(url)
        attempt_diagnostics: list[dict[str, Any]] = []
        for route, raw_client in self._clients:
            current = url
            try:
                for _ in range(MAX_REDIRECTS + 1):
                    request = raw_client.build_request(
                        method, current, headers=self._headers(current)
                    )
                    response = raw_client.send(request, stream=True)
                    if response.status_code not in REDIRECT_CODES:
                        return response, route
                    location = response.headers.get("location")
                    if not location:
                        response.close()
                        raise ReconError(
                            "REDIRECT_WITHOUT_LOCATION",
                            purpose=purpose,
                            method=method,
                            endpoint=safe_endpoint(current),
                            proxy_route=route,
                        )
                    next_url = urljoin(current, location)
                    response.close()
                    self._validate_url(next_url)
                    current = next_url
                raise ReconError(
                    "TOO_MANY_REDIRECTS",
                    purpose=purpose,
                    method=method,
                    endpoint=safe_endpoint(url),
                    proxy_route=route,
                )
            except ReconError:
                raise
            except Exception as exc:
                if httpx is None or not isinstance(exc, httpx.HTTPError):
                    raise
                diagnostic = {
                    "purpose": purpose,
                    "method": method,
                    "endpoint": safe_endpoint(current),
                    "host": urlsplit(current).hostname,
                    "proxy_route": route,
                    "status": "ERROR",
                    "error": "LIVE_METADATA_REQUEST_FAILED",
                    "exception_class": exception_class(exc),
                    "exception_message": sanitize_exception_message(exc),
                    "body_bytes": 0,
                }
                self.records.append(diagnostic)
                attempt_diagnostics.append(diagnostic)
        final = attempt_diagnostics[-1]
        raise ReconError(
            "LIVE_METADATA_REQUEST_FAILED",
            purpose=purpose,
            method=method,
            endpoint=final["endpoint"],
            exception_class=final["exception_class"],
            exception_message=final["exception_message"],
            proxy_attempts=[
                item["proxy_route"] for item in attempt_diagnostics
            ],
        ) from None

    def head(self, url: str, purpose: str) -> dict[str, Any]:
        response, route = self._request_stream("HEAD", url, purpose)
        try:
            record = {
                "purpose": purpose,
                "method": "HEAD",
                "endpoint": safe_endpoint(url),
                "host": urlsplit(url).hostname,
                "proxy_route": route,
                "status": "OK" if 200 <= response.status_code < 300 else "ERROR",
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", "").split(";")[0],
                "content_length": response.headers.get("content-length"),
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
                "body_bytes": 0,
            }
        finally:
            response.close()
        self.records.append(record)
        if record["status"] != "OK":
            raise ReconError(
                f"METADATA_HEAD_HTTP_STATUS_{record['status_code']}",
                purpose=purpose,
                method="HEAD",
                endpoint=safe_endpoint(url),
                status_code=record["status_code"],
            )
        return record

    def get_bytes(self, url: str, purpose: str) -> bytes:
        response, route = self._request_stream("GET", url, purpose)
        content_type = (
            response.headers.get("content-type", "").split(";")[0].lower()
        )
        base_record = {
            "purpose": purpose,
            "method": "GET",
            "endpoint": safe_endpoint(url),
            "host": urlsplit(url).hostname,
            "proxy_route": route,
            "status_code": response.status_code,
            "content_type": content_type,
            "content_length": response.headers.get("content-length"),
        }
        try:
            if not 200 <= response.status_code < 300:
                self.records.append(
                    {**base_record, "status": "ERROR", "body_bytes": 0}
                )
                raise ReconError(
                    f"METADATA_HTTP_STATUS_{response.status_code}",
                    purpose=purpose,
                    method="GET",
                    endpoint=safe_endpoint(url),
                    status_code=response.status_code,
                )
            if any(
                content_type.startswith(prefix) for prefix in MEDIA_CONTENT_PREFIXES
            ):
                self.records.append(
                    {**base_record, "status": "REJECTED", "body_bytes": 0}
                )
                raise ReconError("MEDIA_RESPONSE_BODY_PROHIBITED")
            if content_type and content_type not in METADATA_CONTENT_TYPES:
                self.records.append(
                    {**base_record, "status": "REJECTED", "body_bytes": 0}
                )
                raise ReconError("NON_METADATA_RESPONSE_BODY_PROHIBITED")
            declared_length = response.headers.get("content-length")
            if declared_length:
                try:
                    declared_count = int(declared_length)
                except ValueError:
                    raise ReconError("INVALID_METADATA_CONTENT_LENGTH") from None
                if declared_count > self.max_response_bytes:
                    raise ReconError("METADATA_RESPONSE_BODY_LIMIT_EXCEEDED")
                if self.total_bytes + declared_count > self.max_total_bytes:
                    raise ReconError("METADATA_TOTAL_BODY_LIMIT_EXCEEDED")
            chunks: list[bytes] = []
            count = 0
            for chunk in response.iter_bytes():
                count += len(chunk)
                if count > self.max_response_bytes:
                    raise ReconError("METADATA_RESPONSE_BODY_LIMIT_EXCEEDED")
                if self.total_bytes + count > self.max_total_bytes:
                    raise ReconError("METADATA_TOTAL_BODY_LIMIT_EXCEEDED")
                chunks.append(chunk)
            body = b"".join(chunks)
        finally:
            response.close()
        self.total_bytes += len(body)
        self.records.append(
            {
                **base_record,
                "status": "OK",
                "body_bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
        return body

    def get_json(self, url: str, purpose: str) -> Any:
        body = self.get_bytes(url, purpose)
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ReconError("INVALID_METADATA_JSON") from exc


def commons_api_url(file_title: str) -> str:
    title = file_title
    if not title.startswith("File:"):
        title = f"File:{title}"
    params = (
        "action=query&format=json&formatversion=2"
        "&prop=info%7Cimageinfo%7Cvideoinfo"
        "&iiprop=timestamp%7Curl%7Csize%7Csha1%7Cmime%7Cmediatype"
        "%7Cmetadata%7Ccommonmetadata%7Cextmetadata"
        "&viprop=derivatives%7Ctimedtext%7Cmetadata"
        f"&titles={quote(title, safe='')}"
    )
    return f"https://commons.wikimedia.org/w/api.php?{params}"


def _metadata_value(items: Any, name: str) -> Any:
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, Mapping) and item.get("name") == name:
            return item.get("value")
    return None


def apply_commons_live(candidate: Candidate, payload: Mapping[str, Any]) -> None:
    pages = payload.get("query", {}).get("pages", [])
    if not isinstance(pages, list) or len(pages) != 1:
        raise ReconError("COMMONS_EXACT_PAGE_NOT_RESOLVED")
    page = pages[0]
    if page.get("missing"):
        raise ReconError("COMMONS_FILE_MISSING")
    source = "live_commons_api"
    page_id = page.get("pageid")
    revision = page.get("lastrevid")
    if revision is not None:
        _merge_evidence_field(
            candidate,
            "release_revision",
            str(revision),
            source,
            conflict_is_fatal=True,
        )
    infos = page.get("imageinfo", [])
    if not isinstance(infos, list) or not infos:
        raise ReconError("COMMONS_IMAGEINFO_MISSING")
    info = infos[0]
    if isinstance(info.get("size"), int):
        _merge_evidence_field(
            candidate,
            "object_size_bytes",
            int(info["size"]),
            source,
            conflict_is_fatal=True,
        )
    if info.get("sha1"):
        _merge_evidence_field(
            candidate,
            "object_hash_algorithm",
            "sha1",
            source,
            conflict_is_fatal=True,
        )
        _merge_evidence_field(
            candidate,
            "object_hash",
            str(info["sha1"]),
            source,
            conflict_is_fatal=True,
        )
    if info.get("mime"):
        _merge_evidence_field(
            candidate,
            "declared_media_type",
            str(info["mime"]),
            source,
            conflict_is_fatal=True,
        )
    if info.get("url"):
        _merge_evidence_field(
            candidate,
            "official_download_url",
            str(info["url"]),
            source,
            conflict_is_fatal=True,
        )
        if not candidate.official_download_route_status:
            candidate.official_download_route_status = (
                "OFFICIAL_COMMONS_ORIGINAL_URL_EXPOSED"
            )
    metadata = info.get("metadata", [])
    duration = _metadata_value(metadata, "length")
    if duration is not None:
        _merge_evidence_field(
            candidate,
            "exact_duration_s",
            float(duration),
            source,
            conflict_is_fatal=True,
        )
        candidate.duration_evidence_class = "official_commons_file_metadata"
    audio_codec = _metadata_value(metadata, "audiocodec")
    audio_channels = _metadata_value(metadata, "audiochannels")
    if audio_codec or audio_channels:
        candidate.audio_status = "ITEM_METADATA_DECLARES_AUDIO_NOT_INDEPENDENTLY_PROBED"
        candidate.audio_evidence_class = "official_item_container_metadata"
    candidate.notes += (
        f" Live Commons pageid={page_id!r}/revision captured; "
        f"audio codec={audio_codec!r}, "
        f"channels={audio_channels!r}. Declaration remains unverified until acquisition."
    )


def apply_commons_item_page_live(candidate: Candidate, body: bytes) -> None:
    """Confirm only item-page identity when the Commons API is inaccessible."""
    text = _plain_page_text(body)
    normalized_text = text.casefold()
    title_markers = {
        candidate.title.casefold(),
        candidate.object_path.casefold(),
        candidate.object_path.removesuffix(".webm").casefold(),
    }
    if not any(marker and marker in normalized_text for marker in title_markers):
        raise ReconError(
            "COMMONS_ITEM_PAGE_TITLE_MARKER_NOT_FOUND",
            candidate_id=candidate.candidate_id,
            endpoint=safe_endpoint(candidate.official_item_url),
        )
    if str(LIVE_EVIDENCE_JSON) not in candidate.evidence_sources:
        candidate.evidence_sources.append(str(LIVE_EVIDENCE_JSON))
    candidate.notes += (
        " Live official Commons item-page HTML matched the pinned filename after "
        "the API endpoint failed. This fallback confirms page identity only; it "
        "does not freeze revision, hash, size, original URL, license, duration, "
        "or audio."
    )


def _plain_page_text(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace")
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())


def _duration_markers(seconds: float) -> list[str]:
    rounded = int(round(seconds))
    hours, remainder = divmod(rounded, 3600)
    minutes, secs = divmod(remainder, 60)
    markers = [
        f"{hours:02d}:{minutes:02d}:{secs:02d}",
        f"{hours}:{minutes:02d}:{secs:02d}",
        f"{rounded // 60}:{secs:02d}",
    ]
    if hours:
        markers.extend(
            [
                f"{hours} hour {minutes} minutes",
                f"{hours} hour {minutes} minute",
                f"{hours} hr {minutes} min",
            ]
        )
    else:
        markers.extend(
            [
                f"{minutes} minutes",
                f"{minutes} minute",
                f"{minutes} min",
            ]
        )
    return markers


def apply_official_page_live(candidate: Candidate, body: bytes) -> None:
    """Validate only title/duration declarations present in an official page."""
    text = _plain_page_text(body)
    normalized_text = text.casefold()
    title_present = candidate.title.casefold() in normalized_text
    duration_present = bool(
        candidate.exact_duration_s is not None
        and any(
            marker.casefold() in normalized_text
            for marker in _duration_markers(candidate.exact_duration_s)
        )
    )
    if not title_present:
        if candidate.candidate_id == "cand-023":
            candidate.disposition = "STALE_OR_MISMATCHED_ID_HOLD"
            candidate.shortlist_tier = "HOLD"
            candidate.publication_role = "IDENTITY_MAPPING_HOLD_NOT_ACTIVE"
            candidate.duration_evidence_class = (
                "pinned_official_page_metadata_bound_to_disputed_identity"
            )
            if str(LIVE_EVIDENCE_JSON) not in candidate.evidence_sources:
                candidate.evidence_sources.append(str(LIVE_EVIDENCE_JSON))
            candidate.notes += (
                " Live official-page response did not contain the expected "
                "title. Identity mapping is held; no replacement URL inferred."
            )
        raise ReconError(
            "OFFICIAL_PAGE_TITLE_MARKER_NOT_FOUND",
            candidate_id=candidate.candidate_id,
            endpoint=safe_endpoint(candidate.official_item_url),
        )
    candidate.evidence_sources.append(str(LIVE_EVIDENCE_JSON))
    if duration_present:
        candidate.duration_evidence_class = (
            "live_official_item_page_duration_declaration_not_stream_probe"
        )
    candidate.notes += (
        " Live official-page metadata response matched the exact title; "
        f"duration marker present={str(duration_present).lower()}. "
        "This does not establish an exact media object or audio stream."
    )


def run_live_metadata(
    candidates: Sequence[Candidate],
    client: MetadataClient,
    *,
    hf_token_available: bool = False,
) -> dict[str, Any]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    checks: list[dict[str, Any]] = []

    def attempt(
        purpose: str,
        candidate_ids: Sequence[str],
        operation: Any,
    ) -> Any:
        try:
            result = operation()
        except ReconError as exc:
            checks.append(
                {
                    "purpose": purpose,
                    "candidate_ids": list(candidate_ids),
                    "status": "FAIL",
                    **exc.diagnostic(),
                }
            )
            return None
        checks.append(
            {
                "purpose": purpose,
                "candidate_ids": list(candidate_ids),
                "status": "PASS",
            }
        )
        return result

    for candidate_id in ("cand-061", "cand-056"):
        candidate = by_id[candidate_id]
        purpose = f"{candidate_id}:commons-file-metadata"
        payload = attempt(
            purpose,
            [candidate_id],
            lambda candidate=candidate, purpose=purpose: client.get_json(
                commons_api_url(candidate.object_path), purpose
            ),
        )
        if isinstance(payload, Mapping):
            attempt(
                f"{candidate_id}:commons-metadata-normalization",
                [candidate_id],
                lambda candidate=candidate, payload=payload: apply_commons_live(
                    candidate, payload
                ),
            )
            if checks[-1]["status"] == "PASS" and candidate.official_download_url:
                attempt(
                    f"{candidate_id}:commons-original-head",
                    [candidate_id],
                    lambda candidate=candidate: client.head(
                        candidate.official_download_url,
                        f"{candidate.candidate_id}:commons-original-head",
                    ),
                )
        else:
            fallback_purpose = f"{candidate_id}:commons-item-page-metadata"
            body = attempt(
                fallback_purpose,
                [candidate_id],
                lambda candidate=candidate, purpose=fallback_purpose: client.get_bytes(
                    candidate.official_item_url, purpose
                ),
            )
            if isinstance(body, bytes):
                attempt(
                    f"{candidate_id}:commons-item-page-normalization",
                    [candidate_id],
                    lambda candidate=candidate, body=body: apply_commons_item_page_live(
                        candidate, body
                    ),
                )

    for candidate_id in ("cand-023", "cand-048", "cand-051"):
        candidate = by_id[candidate_id]
        purpose = f"{candidate_id}:official-page-metadata"
        body = attempt(
            purpose,
            [candidate_id],
            lambda candidate=candidate, purpose=purpose: client.get_bytes(
                candidate.official_item_url, purpose
            ),
        )
        if isinstance(body, bytes):
            attempt(
                f"{candidate_id}:official-page-normalization",
                [candidate_id],
                lambda candidate=candidate, body=body: apply_official_page_live(
                    candidate, body
                ),
            )

    live_hf: dict[str, Mapping[str, Any]] = {}
    for repo, purpose in (
        (FLARE_DEMO_REPO, "flare-demo-repository-metadata"),
        (FLARE_REPO, "flare-repository-metadata"),
        (OMNI_REPO, "omni-repository-metadata"),
        ("longvideobench/LongVideoBench", "lvb-repository-metadata"),
    ):
        candidate_ids = [
            candidate.candidate_id
            for candidate in candidates
            if candidate.release_id == repo
        ]
        payload = attempt(
            purpose,
            candidate_ids,
            lambda repo=repo, purpose=purpose: client.get_json(
                f"https://huggingface.co/api/datasets/{repo}", purpose
            ),
        )
        if payload is not None:
            if not isinstance(payload, Mapping):
                checks.append(
                    {
                        "purpose": f"{purpose}:normalization",
                        "candidate_ids": candidate_ids,
                        "status": "FAIL",
                        "error": "HF_REPOSITORY_METADATA_NOT_AN_OBJECT",
                    }
                )
            else:
                live_hf[repo] = payload

    for spec in FLARE_SPECS:
        candidate = by_id[spec["candidate_id"]]
        repo = FLARE_DEMO_REPO if spec["sample"] else FLARE_REPO
        payload = live_hf.get(repo)
        if payload is None:
            continue
        def apply_flare_live(
            candidate: Candidate = candidate,
            payload: Mapping[str, Any] = payload,
            repo: str = repo,
            spec: Mapping[str, Any] = spec,
        ) -> None:
            current_revision = payload.get("sha")
            if current_revision is not None:
                _merge_evidence_field(
                    candidate,
                    "release_revision",
                    str(current_revision),
                    f"live_hf_api:{repo}",
                    conflict_is_fatal=True,
                )
            if spec["sample"]:
                _apply_hf_object(
                    candidate,
                    payload,
                    candidate.object_path,
                    evidence_source=f"live_hf_api:{repo}",
                    conflict_is_fatal=True,
                )
            else:
                exact_video_paths = sorted(
                    path
                    for path in _sibling_index(payload)
                    if path.endswith(f"/{spec['item_id']}.mp4")
                    or path == f"{spec['item_id']}.mp4"
                )
                if len(exact_video_paths) == 1:
                    _apply_hf_object(
                        candidate,
                        payload,
                        exact_video_paths[0],
                        evidence_source=f"live_hf_api:{repo}",
                        conflict_is_fatal=True,
                    )
                    candidate.declared_media_type = "video/mp4"
                    candidate.declared_container = "mp4"
                    candidate.official_download_route_status = (
                        "OFFICIAL_HF_FULL_SOURCE_OBJECT_LISTED_NOT_AUTHORIZED"
                    )
                    candidate.notes += (
                        " Live metadata located one exact full-source MP4."
                    )
                elif len(exact_video_paths) > 1:
                    candidate.notes += (
                        " Live metadata located multiple exact-name full-source "
                        "MP4 paths; canonical object remains unresolved."
                    )

        attempt(
            f"{candidate.candidate_id}:hf-metadata-merge",
            [candidate.candidate_id],
            apply_flare_live,
        )

    omni_payload = live_hf.get(OMNI_REPO)
    if omni_payload is not None:
        for spec in OMNI_SPECS:
            candidate = by_id[spec["candidate_id"]]
            def apply_omni_live(candidate: Candidate = candidate) -> None:
                current_revision = omni_payload.get("sha")
                if current_revision is not None:
                    _merge_evidence_field(
                        candidate,
                        "release_revision",
                        str(current_revision),
                        f"live_hf_api:{OMNI_REPO}",
                        conflict_is_fatal=True,
                    )
                _apply_hf_object(
                    candidate,
                    omni_payload,
                    candidate.object_path,
                    evidence_source=f"live_hf_api:{OMNI_REPO}",
                    conflict_is_fatal=True,
                )

            attempt(
                f"{candidate.candidate_id}:hf-metadata-merge",
                [candidate.candidate_id],
                apply_omni_live,
            )

    lvb_payload = live_hf.get("longvideobench/LongVideoBench")
    if lvb_payload is not None:
        current_lvb_revision = lvb_payload.get("sha")
        if current_lvb_revision is not None:
            for ccp_id, _ in LVB_IDS:
                candidate = by_id[f"lvb-alt-{ccp_id}"]
                attempt(
                    f"{candidate.candidate_id}:hf-revision-merge",
                    [candidate.candidate_id],
                    lambda candidate=candidate: _merge_evidence_field(
                        candidate,
                        "release_revision",
                        str(current_lvb_revision),
                        "live_hf_api:longvideobench/LongVideoBench",
                        conflict_is_fatal=True,
                    ),
                )

    request_records = client.records
    successful_requests = sum(
        1 for record in request_records if record.get("status") == "OK"
    )
    failed_checks = [check for check in checks if check["status"] == "FAIL"]
    if successful_requests == 0:
        status = "FAIL"
    elif failed_checks:
        status = "PARTIAL"
    else:
        status = "PASS"
    return {
        "schema_version": "1.1",
        "created_at": utc_now(),
        "status": status,
        "classification": "METADATA_ONLY_NO_MEDIA_BODY_REQUESTS",
        "network": {
            "proxy_routes": client.proxy_routes,
            "huggingface_token_available": hf_token_available,
            "credentials_persisted": False,
        },
        "request_count": len(request_records),
        "successful_request_count": successful_requests,
        "response_body_bytes": client.total_bytes,
        "logical_checks": checks,
        "records": request_records,
        "candidate_evidence_summary": [
            {
                "candidate_id": candidate.candidate_id,
                "canonical_item_id": candidate.canonical_item_id,
                "release_id": candidate.release_id,
                "release_revision": candidate.release_revision,
                "object_path": candidate.object_path,
                "object_blob_id": candidate.object_blob_id,
                "object_size_bytes": candidate.object_size_bytes,
                "object_hash_algorithm": candidate.object_hash_algorithm,
                "object_hash": candidate.object_hash,
                "exact_duration_s": candidate.exact_duration_s,
                "duration_evidence_class": candidate.duration_evidence_class,
                "declared_media_type": candidate.declared_media_type,
                "declared_container": candidate.declared_container,
                "audio_status": candidate.audio_status,
                "audio_evidence_class": candidate.audio_evidence_class,
                "audio_verified": candidate.audio_verified,
                "processing_rights_status": candidate.processing_rights_status,
                "annotation_rights_status": candidate.annotation_rights_status,
                "rights_status": candidate.rights_status,
                "disposition": candidate.disposition,
                "metadata_conflicts": candidate.metadata_conflicts,
            }
            for candidate in candidates
        ],
    }


def validate_outputs(candidates: Sequence[Candidate], allowlist: Mapping[str, Any]) -> None:
    if len(candidates) != 16:
        raise ReconError("EXPECTED_EXACTLY_16_RECON_CANDIDATES")
    if any(candidate.audio_verified for candidate in candidates):
        raise ReconError("LOCAL_EVIDENCE_MUST_NOT_MARK_AUDIO_VERIFIED")
    primary = allowlist["proposed_primary_after_gate_resolution"]
    reserve = allowlist["proposed_reserves_after_gate_resolution"]
    if [item["candidate_id"] for item in primary] != [
        "cand-061",
        "cand-048",
        "cand-051",
    ]:
        raise ReconError("UNEXPECTED_PRIMARY_SHORTLIST")
    if [item["candidate_id"] for item in reserve] != ["cand-056"]:
        raise ReconError("UNEXPECTED_RESERVE_SHORTLIST")
    cand_023 = next(
        candidate
        for candidate in candidates
        if candidate.candidate_id == "cand-023"
    )
    if cand_023.disposition != "STALE_OR_MISMATCHED_ID_HOLD":
        raise ReconError("CAND_023_IDENTITY_HOLD_REQUIRED")
    if allowlist["authorized_for_transfer"]:
        raise ReconError("FAIL_CLOSED_OUTPUT_CANNOT_AUTHORIZE_TRANSFER")


def validate_preflight_proposal(proposal: Mapping[str, Any]) -> None:
    for field in (
        "authorized_for_stream_header_preflight",
        "authorized_for_full_acquisition",
        "authorized_for_transfer",
    ):
        if proposal[field]:
            raise ReconError("PRECHECK_CANNOT_AUTHORIZE_MEDIA_ACTION")
    requested = [
        item["candidate_id"]
        for item in proposal["item_scoped_identity_and_authority_requests"]
    ]
    if requested != [
        "cand-061",
        "cand-056",
        "cand-048",
        "cand-051",
    ]:
        raise ReconError("UNEXPECTED_PREFLIGHT_REQUEST_SCOPE")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--mode",
        choices=("offline", "live"),
        default="offline",
        help="Live mode still performs metadata-only requests.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the normalized CSV and fail-closed shortlist JSON.",
    )
    parser.add_argument(
        "--evidence-out",
        type=Path,
        help="Optional path for a credential-free live request audit.",
    )
    parser.add_argument(
        "--proxy",
        action="append",
        default=[],
        help=(
            "Explicit HTTP(S) proxy. May be repeated for transport-error "
            "failover. Values are never written to outputs."
        ),
    )
    parser.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
    )
    parser.add_argument(
        "--max-total-body-bytes",
        type=int,
        default=DEFAULT_MAX_TOTAL_BYTES,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repo_root.resolve()
    candidates = build_candidates(root)
    live_evidence = None
    if args.mode == "live":
        token = load_hf_token()
        with MetadataClient(
            token,
            max_response_bytes=args.max_response_bytes,
            max_total_bytes=args.max_total_body_bytes,
            proxies=args.proxy or None,
        ) as client:
            live_evidence = run_live_metadata(
                candidates,
                client,
                hf_token_available=bool(token),
            )
    allowlist = proposed_allowlist(candidates, args.mode, live_evidence)
    preflight_proposal = (
        stream_preflight_proposal(candidates, live_evidence)
        if live_evidence is not None
        else None
    )
    validate_outputs(candidates, allowlist)
    if preflight_proposal is not None:
        validate_preflight_proposal(preflight_proposal)
    if args.write:
        write_outputs(root, candidates, allowlist, preflight_proposal)
    if args.evidence_out:
        if live_evidence is None:
            raise ReconError("EVIDENCE_OUT_REQUIRES_LIVE_MODE")
        evidence_path = args.evidence_out
        if not evidence_path.is_absolute():
            evidence_path = root / evidence_path
        _atomic_json_write(evidence_path, live_evidence)
    execution_status = (
        live_evidence["status"] if live_evidence is not None else "PASS"
    )
    summary = {
        "status": execution_status,
        "mode": args.mode,
        "candidate_count": len(candidates),
        "audio_verified_count": sum(
            1 for candidate in candidates if candidate.audio_verified
        ),
        "decision": allowlist["decision"],
        "wrote_outputs": bool(args.write),
        "live_response_body_bytes": (
            live_evidence["response_body_bytes"] if live_evidence else 0
        ),
    }
    print(json.dumps(summary, sort_keys=True))
    if execution_status != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReconError as exc:
        print(
            json.dumps({"status": "FAIL", **exc.diagnostic()}, sort_keys=True),
            file=sys.stderr,
        )
        raise SystemExit(2)
