"""Fail-closed, read-only access to the restricted LVB-01 rehearsal assets.

The public return values deliberately contain no subtitle strings and no frame
pixels. Subtitle content is used only inside this process for deterministic
query matching and is represented outside the adapter by cue indexes, source
times, counts, and one-way query/content digests.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import av


PLAN_REL = Path("data/acquisition_plan/lvb01_exact_asset_plan.json")
MANIFEST_REL = Path("data/restricted/lvb01/manifests/lvb01_acquisition_manifest.json")
AUDIT_REL = Path("data/restricted/lvb01/manifests/lvb01_media_audit.json")
STATUS_REL = Path("data/rehearsal_plan/lvb01_verified_asset_status.csv")
RESTRICTED_REL = Path("data/restricted/lvb01")

_WORD_RE = re.compile(r"[a-z0-9']+")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RestrictedAssetError(RuntimeError):
    """Base class for safe restricted-asset access failures."""


class IntegrityBindingError(RestrictedAssetError):
    """Raised before media opens when acquisition/audit bindings have drifted."""


class AccessBlockedError(RestrictedAssetError):
    """Raised when a matched-state intervention blocks a requested route."""


def _sha256_file(path: Path, *, chunk_size: int = 4 * 1024 * 1024) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(chunk_size):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrityBindingError(f"INVALID_BOUND_JSON:{path.name}") from exc


def _parse_timestamp(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a timestamp")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        parts = value.strip().split(":")
        if len(parts) == 1:
            result = float(parts[0])
        elif len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
            if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
                raise ValueError("invalid clock timestamp")
            result = hours * 3600 + minutes * 60 + seconds
        else:
            raise ValueError("invalid timestamp")
    else:
        raise TypeError("invalid timestamp type")
    if not math.isfinite(result) or result < 0:
        raise ValueError("timestamp must be finite and non-negative")
    return result


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(_WORD_RE.findall(value.casefold()))


def _safe_regular_file(path: Path, restricted_root: Path) -> bool:
    try:
        resolved = path.resolve(strict=True)
        root = restricted_root.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    mode = path.lstat().st_mode
    return (
        stat.S_ISREG(mode)
        and not path.is_symlink()
        and stat.S_IMODE(mode) & 0o077 == 0
    )


@dataclass(frozen=True)
class AssetBinding:
    candidate_id: str
    asset_id: str
    duration_s: float
    video_path: Path
    subtitle_path: Path
    video_size: int
    subtitle_size: int
    video_sha256: str
    subtitle_sha256: str
    subtitle_entry_count: int

    def safe_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "asset_id": self.asset_id,
            "duration_s": round(self.duration_s, 6),
            "video_size": self.video_size,
            "subtitle_size": self.subtitle_size,
            "video_sha256_prefix": self.video_sha256[:12],
            "subtitle_sha256_prefix": self.subtitle_sha256[:12],
            "subtitle_entry_count": self.subtitle_entry_count,
        }


@dataclass(frozen=True)
class FrameSample:
    candidate_id: str
    requested_time_s: float
    source_time_s: float
    width: int
    height: int

    def safe_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "requested_time_s": round(self.requested_time_s, 6),
            "source_time_s": round(self.source_time_s, 6),
            "width": self.width,
            "height": self.height,
            "decode_status": "FRAME_DECODED_IN_MEMORY_NOT_PERSISTED",
        }


@dataclass(frozen=True)
class SubtitleProxyHit:
    candidate_id: str
    cue_index: int
    cue_start_s: float
    window_start_s: float
    window_end_s: float
    matched_token_count: int
    query_token_count: int
    cue_token_count: int

    def safe_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "cue_index": self.cue_index,
            "cue_start_s": round(self.cue_start_s, 6),
            "window_start_s": round(self.window_start_s, 6),
            "window_end_s": round(self.window_end_s, 6),
            "matched_token_count": self.matched_token_count,
            "query_token_count": self.query_token_count,
            "cue_token_count": self.cue_token_count,
            "text_disclosure": "subtitle-proxy text withheld",
        }


@dataclass(frozen=True)
class _Cue:
    index: int
    start_s: float
    tokens: frozenset[str]
    line_sha256: str


class RestrictedAssetAdapter:
    """Resolve and decode only the five audit-bound LVB-01 asset pairs."""

    adapter_version = "lvb01-restricted-v-subtitle-proxy/1.0.0"

    def __init__(
        self,
        repo_root: str | Path,
        *,
        expected_candidate_count: int = 5,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.restricted_root = (self.repo_root / RESTRICTED_REL).resolve()
        self.expected_candidate_count = expected_candidate_count
        self._bindings: dict[str, AssetBinding] = {}
        self._cues: dict[str, tuple[_Cue, ...]] = {}
        self._verified_payloads: set[tuple[str, str]] = set()
        self._verify_control_bindings()
        self._build_allowlist()
        self._verify_status_overlay()

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(self._bindings)

    def binding(self, candidate_id: str) -> AssetBinding:
        try:
            return self._bindings[candidate_id]
        except KeyError as exc:
            raise RestrictedAssetError(f"NOT_ALLOWLISTED_CANDIDATE:{candidate_id}") from exc

    def _verify_control_bindings(self) -> None:
        plan_path = self.repo_root / PLAN_REL
        manifest_path = self.repo_root / MANIFEST_REL
        audit_path = self.repo_root / AUDIT_REL
        for path in (plan_path, manifest_path, audit_path):
            if not path.is_file() or path.is_symlink():
                raise IntegrityBindingError(f"MISSING_OR_UNSAFE_CONTROL_FILE:{path.name}")
        plan_size, plan_sha = _sha256_file(plan_path)
        manifest_size, manifest_sha = _sha256_file(manifest_path)
        plan = _load_json(plan_path)
        manifest = _load_json(manifest_path)
        audit = _load_json(audit_path)

        frozen = audit.get("inputs", {}).get("frozen_plan", {})
        acquisition = audit.get("inputs", {}).get("acquisition_manifest", {})
        checks = [
            audit.get("decision") == "CONDITIONAL_GO",
            audit.get("scope", {}).get("restricted_root") == RESTRICTED_REL.as_posix(),
            audit.get("scope", {}).get("benchmark_annotations_created") is False,
            audit.get("scope", {}).get("derived_media_persisted") is False,
            audit.get("scope", {}).get("payloads_modified") is False,
            audit.get("integrity_and_provenance", {}).get("passed") is True,
            audit.get("integrity_and_provenance", {}).get("aggregate", {}).get("exact_match") is True,
            frozen.get("path") == PLAN_REL.as_posix(),
            frozen.get("size") == plan_size,
            frozen.get("sha256") == plan_sha,
            acquisition.get("path") == MANIFEST_REL.as_posix(),
            acquisition.get("size") == manifest_size,
            acquisition.get("sha256") == manifest_sha,
            manifest.get("plan_sha256") == plan_sha,
            manifest.get("plan_id") == plan.get("plan_id"),
            manifest.get("pinned_revision") == plan.get("pinned_revision"),
            len(plan.get("targets", ())) == len(manifest.get("targets", ())),
            len(plan.get("targets", ())) == self.expected_candidate_count * 2,
        ]
        if not all(checks):
            raise IntegrityBindingError("CONTROL_BINDING_DRIFT")
        self._plan = plan
        self._manifest = manifest
        self._audit = audit

    def _build_allowlist(self) -> None:
        plan_by_basename = {item["basename"]: item for item in self._plan["targets"]}
        manifest_by_basename = {item["basename"]: item for item in self._manifest["targets"]}
        audit_entries = {
            item["basename"]: item
            for item in self._audit["integrity_and_provenance"]["entries"]
        }
        video_audit = {item["candidate_id"]: item for item in self._audit["videos"]}
        subtitle_audit = {item["candidate_id"]: item for item in self._audit["subtitles"]}
        by_candidate: dict[str, dict[str, Mapping[str, Any]]] = {}

        if set(plan_by_basename) != set(manifest_by_basename) or set(plan_by_basename) != set(audit_entries):
            raise IntegrityBindingError("ALLOWLIST_SET_DRIFT")
        for basename, plan_item in plan_by_basename.items():
            manifest_item = manifest_by_basename[basename]
            audit_item = audit_entries[basename]
            if (
                manifest_item.get("status") != "downloaded"
                or audit_item.get("passed") is not True
                or manifest_item.get("kind") != plan_item.get("kind")
                or audit_item.get("kind") != plan_item.get("kind")
                or int(manifest_item.get("size", -1)) != int(plan_item.get("size", -2))
                or int(audit_item.get("actual_size", -3)) != int(plan_item.get("size", -4))
                or manifest_item.get("sha256") != audit_item.get("actual_sha256")
                or not _SHA256_RE.fullmatch(str(manifest_item.get("sha256", "")))
            ):
                raise IntegrityBindingError(f"PAYLOAD_BINDING_DRIFT:{basename}")
            candidate_id = str(plan_item.get("candidate_id", ""))
            by_candidate.setdefault(candidate_id, {})[str(plan_item["kind"])] = {
                "plan": plan_item,
                "manifest": manifest_item,
                "audit": audit_item,
            }

        expected_candidates = set(video_audit) & set(subtitle_audit)
        if (
            set(by_candidate) != expected_candidates
            or len(expected_candidates) != self.expected_candidate_count
        ):
            raise IntegrityBindingError("CANDIDATE_BINDING_DRIFT")
        for candidate_id in sorted(by_candidate):
            pair = by_candidate[candidate_id]
            if set(pair) != {"video", "subtitle"}:
                raise IntegrityBindingError(f"INCOMPLETE_ASSET_PAIR:{candidate_id}")
            video = pair["video"]
            subtitle = pair["subtitle"]
            video_path = self.repo_root / str(video["audit"]["path"])
            subtitle_path = self.repo_root / str(subtitle["audit"]["path"])
            if not _safe_regular_file(video_path, self.restricted_root):
                raise IntegrityBindingError(f"UNSAFE_VIDEO_PATH:{candidate_id}")
            if not _safe_regular_file(subtitle_path, self.restricted_root):
                raise IntegrityBindingError(f"UNSAFE_SUBTITLE_PATH:{candidate_id}")
            va = video_audit[candidate_id]
            sa = subtitle_audit[candidate_id]
            if (
                va.get("technically_usable") is not True
                or va.get("streams", {}).get("video_stream_count") != 1
                or va.get("streams", {}).get("audio_stream_count") != 0
                or sa.get("valid") is not True
                or sa.get("usable_speech_proxy") is not True
            ):
                raise IntegrityBindingError(f"UNSUPPORTED_AUDIT_STATUS:{candidate_id}")
            self._bindings[candidate_id] = AssetBinding(
                candidate_id=candidate_id,
                asset_id=str(video["plan"]["video_id"]),
                duration_s=float(va["duration"]["actual_seconds"]),
                video_path=video_path,
                subtitle_path=subtitle_path,
                video_size=int(video["manifest"]["size"]),
                subtitle_size=int(subtitle["manifest"]["size"]),
                video_sha256=str(video["manifest"]["sha256"]),
                subtitle_sha256=str(subtitle["manifest"]["sha256"]),
                subtitle_entry_count=int(sa["schema"]["entry_count"]),
            )

    def _verify_status_overlay(self) -> None:
        path = self.repo_root / STATUS_REL
        if not path.is_file() or path.is_symlink():
            raise IntegrityBindingError("MISSING_OR_UNSAFE_STATUS_OVERLAY")
        rows: dict[str, Mapping[str, str]] = {}
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    candidate_id = str(row.get("candidate_id", ""))
                    if candidate_id in rows:
                        raise IntegrityBindingError("DUPLICATE_STATUS_CANDIDATE")
                    rows[candidate_id] = row
        except (OSError, UnicodeError, csv.Error) as exc:
            raise IntegrityBindingError("INVALID_STATUS_OVERLAY") from exc
        if set(rows) != set(self._bindings):
            raise IntegrityBindingError("STATUS_CANDIDATE_DRIFT")
        for candidate_id, row in rows.items():
            if (
                row.get("download_integrity_status") != "DOWNLOADED_HASH_VERIFIED_INTERNAL"
                or row.get("video_stream_status") != "AVAILABLE_ONE_H264_STREAM"
                or row.get("audio_stream_status") != "ABSENT_ZERO_STREAMS"
                or row.get("internal_visual_subtitle_rehearsal_status")
                != "TECHNICALLY_READY_INTERNAL_ONLY"
                or not str(row.get("subtitle_proxy_status", "")).startswith(
                    "AVAILABLE_ORDERED_NONEMPTY"
                )
            ):
                raise IntegrityBindingError(f"STATUS_NOT_READY:{candidate_id}")

    def verify_asset(self, candidate_id: str) -> AssetBinding:
        # The non-restricted status overlay is authoritative and intentionally
        # rechecked before every open, alongside payload size/hash checks.
        self._verify_status_overlay()
        binding = self.binding(candidate_id)
        for kind, path, expected_size, expected_sha in (
            ("video", binding.video_path, binding.video_size, binding.video_sha256),
            ("subtitle_proxy", binding.subtitle_path, binding.subtitle_size, binding.subtitle_sha256),
        ):
            cache_key = (candidate_id, kind)
            stat_result = path.stat()
            if stat_result.st_size != expected_size:
                raise IntegrityBindingError(f"SIZE_DRIFT:{candidate_id}:{kind}")
            if cache_key not in self._verified_payloads:
                actual_size, actual_sha = _sha256_file(path)
                if actual_size != expected_size or actual_sha != expected_sha:
                    raise IntegrityBindingError(f"HASH_DRIFT:{candidate_id}:{kind}")
                self._verified_payloads.add(cache_key)
        return binding

    def _load_cues(self, candidate_id: str) -> tuple[_Cue, ...]:
        if candidate_id in self._cues:
            return self._cues[candidate_id]
        binding = self.verify_asset(candidate_id)
        value = _load_json(binding.subtitle_path)
        if not isinstance(value, list) or len(value) != binding.subtitle_entry_count:
            raise IntegrityBindingError(f"SUBTITLE_STRUCTURE_DRIFT:{candidate_id}")
        cues: list[_Cue] = []
        previous = -1.0
        for index, item in enumerate(value):
            if not isinstance(item, Mapping) or set(item) != {"start", "end", "line"}:
                raise IntegrityBindingError(f"SUBTITLE_SCHEMA_DRIFT:{candidate_id}")
            line = item["line"]
            if not isinstance(line, str) or not line.strip():
                raise IntegrityBindingError(f"EMPTY_SUBTITLE_PROXY:{candidate_id}")
            start = _parse_timestamp(item["start"])
            if start < previous:
                raise IntegrityBindingError(f"SUBTITLE_ORDER_DRIFT:{candidate_id}")
            previous = start
            cues.append(
                _Cue(
                    index=index,
                    start_s=start,
                    tokens=frozenset(_tokens(line)),
                    line_sha256=hashlib.sha256(line.encode("utf-8")).hexdigest(),
                )
            )
        result = tuple(cues)
        self._cues[candidate_id] = result
        return result

    def derive_probe(self, candidate_id: str) -> dict[str, Any]:
        """Derive safe rehearsal coordinates from real subtitle timing/content.

        A deterministic rare-token cue is selected. The query remains in
        memory and is never serialized by the runner.
        """

        binding = self.binding(candidate_id)
        cues = self._load_cues(candidate_id)
        frequencies: dict[str, int] = {}
        for cue in cues:
            for token in cue.tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
        candidates: list[tuple[int, float, int, _Cue, tuple[str, ...]]] = []
        for cue in cues:
            query_tokens = tuple(
                sorted(
                    token
                    for token in cue.tokens
                    if len(token) >= 6 and frequencies.get(token, 0) <= 2
                )
            )
            if not query_tokens:
                continue
            score = len(query_tokens) * 100 + len(cue.tokens)
            candidates.append((score, cue.start_s, -cue.index, cue, query_tokens[:4]))
        if not candidates:
            cue = cues[len(cues) // 2]
            query_tokens = tuple(sorted(cue.tokens))[:2]
        else:
            _, _, _, cue, query_tokens = max(candidates)
        if not query_tokens:
            raise RestrictedAssetError(f"NO_SAFE_PROBE_TOKENS:{candidate_id}")
        visual_time = min(max(0.25, cue.start_s), max(0.25, binding.duration_s - 0.25))
        wrong_time = min(max(0.25, binding.duration_s * 0.113), max(0.25, binding.duration_s - 0.25))
        if abs(wrong_time - visual_time) < 30.0:
            wrong_time = min(max(0.25, binding.duration_s * 0.887), max(0.25, binding.duration_s - 0.25))
        return {
            "cue_index": cue.index,
            "cue_start_s": cue.start_s,
            "visual_time_s": visual_time,
            "wrong_visual_time_s": wrong_time,
            "query_tokens": query_tokens,
            "cue_line_sha256": cue.line_sha256,
        }

    def sample_frame(
        self,
        candidate_id: str,
        source_time_s: float,
        *,
        video_enabled: bool = True,
        blocked_window: tuple[float, float] | None = None,
    ) -> FrameSample:
        if not video_enabled:
            raise AccessBlockedError("VIDEO_ROUTE_BLOCKED")
        binding = self.verify_asset(candidate_id)
        requested = float(source_time_s)
        if not math.isfinite(requested) or not 0 <= requested < binding.duration_s:
            raise RestrictedAssetError("INVALID_SOURCE_TIME")
        if blocked_window and blocked_window[0] <= requested <= blocked_window[1]:
            raise AccessBlockedError("VIDEO_WINDOW_BLOCKED")
        try:
            with av.open(str(binding.video_path), mode="r") as container:
                stream = next((item for item in container.streams if item.type == "video"), None)
                if stream is None:
                    raise IntegrityBindingError("AUDITED_VIDEO_STREAM_MISSING")
                target = max(0.0, requested - 1.0)
                container.seek(int(target / float(stream.time_base)), stream=stream, backward=True)
                chosen = None
                for frame in container.decode(stream):
                    if frame.pts is None:
                        continue
                    timestamp = float(frame.pts * frame.time_base)
                    chosen = frame
                    if timestamp + 1e-6 >= requested:
                        break
                if chosen is None or chosen.pts is None:
                    raise RestrictedAssetError("FRAME_NOT_DECODED")
                source_time = float(chosen.pts * chosen.time_base)
                rgb = chosen.to_ndarray(format="rgb24")
        except RestrictedAssetError:
            raise
        except Exception as exc:
            raise RestrictedAssetError(f"FRAME_DECODE_FAILED:{type(exc).__name__}") from exc
        return FrameSample(
            candidate_id=candidate_id,
            requested_time_s=requested,
            source_time_s=source_time,
            width=int(rgb.shape[1]),
            height=int(rgb.shape[0]),
        )

    def search_subtitle_proxy(
        self,
        candidate_id: str,
        query_tokens: Sequence[str],
        *,
        subtitle_proxy_enabled: bool = True,
        center_window_s: float = 6.0,
        limit: int = 3,
        excluded_cue_indexes: Iterable[int] = (),
    ) -> tuple[SubtitleProxyHit, ...]:
        """Search ordered subtitle proxy text, returning start-centered windows.

        Cue end times are intentionally ignored because the audited files often
        use point-like end timestamps.
        """

        if not subtitle_proxy_enabled:
            raise AccessBlockedError("SUBTITLE_PROXY_ROUTE_BLOCKED")
        binding = self.verify_asset(candidate_id)
        if not math.isfinite(center_window_s) or center_window_s <= 0:
            raise ValueError("center_window_s must be positive")
        normalized = frozenset(
            token
            for value in query_tokens
            for token in _tokens(str(value))
        )
        if not normalized:
            raise ValueError("query must contain at least one token")
        excluded = set(excluded_cue_indexes)
        ranked: list[tuple[int, float, int, _Cue]] = []
        for cue in self._load_cues(candidate_id):
            if cue.index in excluded:
                continue
            overlap = len(normalized & cue.tokens)
            if overlap:
                ranked.append((-overlap, cue.start_s, cue.index, cue))
        ranked.sort()
        hits = []
        for negative_overlap, _, _, cue in ranked[:limit]:
            hits.append(
                SubtitleProxyHit(
                    candidate_id=candidate_id,
                    cue_index=cue.index,
                    cue_start_s=cue.start_s,
                    window_start_s=max(0.0, cue.start_s - center_window_s),
                    window_end_s=min(binding.duration_s, cue.start_s + center_window_s),
                    matched_token_count=-negative_overlap,
                    query_token_count=len(normalized),
                    cue_token_count=len(cue.tokens),
                )
            )
        return tuple(hits)
