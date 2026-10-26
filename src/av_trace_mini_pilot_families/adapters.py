"""Fail-closed adapters for canonical and frozen development inputs."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import json_hash

CANONICAL_ARTIFACTS = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "build_manifest.json",
)
NOAA_ARTIFACTS = (
    "full_timeline_index.json",
    "migrated_families.json",
    "build_manifest.json",
)
_TIMESTAMP = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})"
)
_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[a-z0-9]+")


class FamilyInputError(RuntimeError):
    """An input cannot safely support candidate mining."""


@dataclass(frozen=True)
class TranscriptRoute:
    """Official sidecar route used only for shortcut/alternative challenge."""

    route_id: str
    source_ref: str
    format: str
    timing: str
    start_us: int | None
    end_us: int | None
    tokens: tuple[str, ...]
    content_sha256: str
    use: str = "derived_route_challenge_only"


@dataclass(frozen=True)
class MiningInputs:
    """Normalized source material for the machine-provisional miner."""

    new_index: Mapping[str, Any]
    noaa_index: Mapping[str, Any]
    new_source_hashes: Mapping[str, str]
    noaa_source_hashes: Mapping[str, str]
    new_routing_records: tuple[Mapping[str, Any], ...]
    official_transcript_routes: tuple[TranscriptRoute, ...]
    noaa_families: tuple[Mapping[str, Any], ...]
    provenance: Mapping[str, Any]

    def index_for(self, source_kind: str) -> Mapping[str, Any]:
        if source_kind == "new_source":
            return self.new_index
        if source_kind == "noaa_development":
            return self.noaa_index
        raise FamilyInputError(f"UNKNOWN_SOURCE_KIND:{source_kind}")

    def source_hash(self, source_kind: str, source_id: str) -> str:
        values = (
            self.new_source_hashes
            if source_kind == "new_source"
            else self.noaa_source_hashes
        )
        try:
            return str(values[source_id])
        except KeyError as exc:
            raise FamilyInputError(f"SOURCE_NOT_IN_INDEX:{source_id}") from exc


def _load(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise FamilyInputError(f"JSON_LOAD_FAILED:{path}:{exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _repo_path(repo_root: Path, value: str | Path) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        candidate = raw
    else:
        pure = PurePosixPath(str(value))
        if ".." in pure.parts:
            raise FamilyInputError(f"UNSAFE_REPOSITORY_PATH:{value}")
        candidate = repo_root.joinpath(*pure.parts)
    try:
        candidate.resolve(strict=False).relative_to(repo_root)
    except ValueError as exc:
        raise FamilyInputError(f"PATH_OUTSIDE_REPOSITORY:{value}") from exc
    if candidate.is_symlink():
        raise FamilyInputError(f"SYMLINK_INPUT_FORBIDDEN:{value}")
    return candidate


def _self_hash(document: Mapping[str, Any], key: str) -> bool:
    copy = dict(document)
    stored = copy.pop(key, None)
    return stored == json_hash(copy)


def _inventory_map(
    repo_root: Path, build_manifest: Mapping[str, Any]
) -> dict[str, Mapping[str, Any]]:
    records = build_manifest.get("artifacts") or build_manifest.get(
        "artifact_inventory", ()
    )
    output: dict[str, Mapping[str, Any]] = {}
    for item in records:
        path = _repo_path(repo_root, str(item["path"]))
        output[path.resolve().as_posix()] = item
    return output


def _verify_inventory_artifact(
    repo_root: Path,
    build_manifest: Mapping[str, Any],
    path: Path,
) -> None:
    inventory = _inventory_map(repo_root, build_manifest)
    item = inventory.get(path.resolve().as_posix())
    if item is None:
        raise FamilyInputError(f"ARTIFACT_NOT_FROZEN_IN_BUILD_MANIFEST:{path.name}")
    expected = str(item["sha256"])
    actual = _sha256(path)
    if expected != actual:
        raise FamilyInputError(
            f"FROZEN_ARTIFACT_HASH_MISMATCH:{path.name}:{expected}:{actual}"
        )


def _timestamp_us(value: str) -> int:
    match = _TIMESTAMP.search(value)
    if match is None:
        raise ValueError(value)
    return (
        (
            int(match.group("h")) * 3600
            + int(match.group("m")) * 60
            + int(match.group("s"))
        )
        * 1_000_000
        + int(match.group("ms")) * 1000
    )


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(html.unescape(text).casefold()))


def parse_official_sidecar(
    *,
    source_ref: str,
    path: Path,
    format_name: str,
    timing: str,
    expected_sha256: str,
) -> tuple[TranscriptRoute, ...]:
    """Parse sidecars for derived-route challenge, never as citable evidence."""
    actual = _sha256(path)
    expected = (
        expected_sha256
        if expected_sha256.startswith("sha256:")
        else f"sha256:{expected_sha256}"
    )
    if actual != expected:
        raise FamilyInputError(f"SIDECAR_HASH_MISMATCH:{source_ref}:{path.name}")
    format_name = format_name.casefold()
    if format_name == "pdf":
        return (
            TranscriptRoute(
                route_id=f"sidecar.{source_ref}.pdf",
                source_ref=source_ref,
                format="pdf",
                timing="untimed",
                start_us=None,
                end_us=None,
                tokens=(),
                content_sha256=actual,
                use="binary_sidecar_identity_only",
            ),
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    if format_name in {"srt", "webvtt", "vtt"} and timing == "timed":
        routes: list[TranscriptRoute] = []
        blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
        for index, block in enumerate(blocks):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            timing_line = next((line for line in lines if "-->" in line), None)
            if timing_line is None:
                continue
            left, right = timing_line.split("-->", 1)
            try:
                start_us = _timestamp_us(left)
                end_us = _timestamp_us(right)
            except ValueError:
                continue
            body = " ".join(
                line
                for line in lines
                if line != timing_line and not line.isdigit()
            )
            route_tokens = _tokens(_TAG.sub(" ", body))
            if not route_tokens or end_us <= start_us:
                continue
            routes.append(
                TranscriptRoute(
                    route_id=f"sidecar.{source_ref}.{index:06d}",
                    source_ref=source_ref,
                    format=format_name,
                    timing="timed",
                    start_us=start_us,
                    end_us=end_us,
                    tokens=route_tokens,
                    content_sha256=actual,
                )
            )
        return tuple(routes)
    cleaned = _TAG.sub(" ", text)
    return (
        TranscriptRoute(
            route_id=f"sidecar.{source_ref}.untimed",
            source_ref=source_ref,
            format=format_name,
            timing="untimed",
            start_us=None,
            end_us=None,
            tokens=_tokens(cleaned),
            content_sha256=actual,
        ),
    )


def _load_routing_records(
    repo_root: Path, observation: Mapping[str, Any]
) -> tuple[Mapping[str, Any], ...]:
    output: list[Mapping[str, Any]] = []
    for item in observation.get("checkpoints", ()):
        if not str(item.get("path", "")).endswith("/vision_routing.json"):
            continue
        path = _repo_path(repo_root, str(item["path"]))
        if _sha256(path) != item.get("sha256"):
            raise FamilyInputError(f"ROUTING_CHECKPOINT_HASH_MISMATCH:{path}")
        checkpoint = _load(path)
        output.extend(dict(record) for record in checkpoint.get("records", ()))
    return tuple(output)


def load_canonical_new_source_index(
    repo_root: str | Path,
    *,
    index_root: str | Path = "data/restricted/mini_pilot_index_v1",
    plan_path: str | Path = (
        "data/rehearsal_plan/mini_pilot_full_timeline_v1.json"
    ),
) -> tuple[
    Mapping[str, Any],
    Mapping[str, str],
    tuple[Mapping[str, Any], ...],
    tuple[TranscriptRoute, ...],
    Mapping[str, Any],
]:
    """Load only a complete, non-smoke canonical four-source index."""
    root = Path(repo_root).resolve()
    output = _repo_path(root, index_root)
    missing = [name for name in CANONICAL_ARTIFACTS if not (output / name).is_file()]
    if missing:
        raise FamilyInputError(
            "CANONICAL_INDEX_INCOMPLETE_MISSING:" + ",".join(sorted(missing))
        )
    build = _load(output / "build_manifest.json")
    if build.get("status") != "COMPLETE":
        raise FamilyInputError("CANONICAL_INDEX_BUILD_NOT_COMPLETE")
    if build.get("smoke_seconds") is not None:
        raise FamilyInputError("SMOKE_INDEX_FORBIDDEN_FOR_FAMILY_MINING")
    if build.get("source_count") != 4 or build.get("expected_source_count") != 4:
        raise FamilyInputError("CANONICAL_INDEX_SOURCE_COUNT_MUST_BE_FOUR")
    boundary = build.get("terminal_boundary", {})
    forbidden_outputs = (
        "families_generated",
        "negatives_generated",
        "interventions_generated",
        "trajectories_generated",
        "evaluation_generated",
    )
    if any(boundary.get(key) is not False for key in forbidden_outputs):
        raise FamilyInputError("CANONICAL_INDEX_TERMINAL_BOUNDARY_INVALID")
    for name in CANONICAL_ARTIFACTS[:-1]:
        _verify_inventory_artifact(root, build, output / name)

    segment = _load(output / "segment_manifest.json")
    observation = _load(output / "observation_manifest.json")
    index = _load(output / "full_timeline_index.json")
    resource = _load(output / "resource_manifest.json")
    if not observation.get("all_sources_complete"):
        raise FamilyInputError("CANONICAL_OBSERVATIONS_INCOMPLETE")
    if set(observation.get("complete_source_refs", ())) != set(
        index.get("source_hashes", {})
    ):
        raise FamilyInputError("CANONICAL_COMPLETE_SOURCE_SET_MISMATCH")
    if not _self_hash(segment, "segment_manifest_hash"):
        raise FamilyInputError("CANONICAL_SEGMENT_SELF_HASH_INVALID")
    if not _self_hash(observation, "observation_manifest_hash"):
        raise FamilyInputError("CANONICAL_OBSERVATION_SELF_HASH_INVALID")
    if not _self_hash(index, "index_hash"):
        raise FamilyInputError("CANONICAL_INDEX_SELF_HASH_INVALID")
    if not _self_hash(resource, "resource_manifest_hash"):
        raise FamilyInputError("CANONICAL_RESOURCE_SELF_HASH_INVALID")

    plan = _load(_repo_path(root, plan_path))
    expected = plan.get("totals") or plan.get("expected_totals", {})
    counts = segment.get("totals", {})
    for key in ("base_cells", "fine_windows", "context_windows"):
        if int(counts.get(key, -1)) != int(expected.get(key, -2)):
            raise FamilyInputError(f"CANONICAL_INDEX_COUNT_MISMATCH:{key}")

    routes: list[TranscriptRoute] = []
    for source in plan.get("sources", ()):
        source_ref = str(source["source_id"])
        for sidecar in source.get("official_transcript_sidecars", ()):
            if sidecar.get("index_use") != "verification_only":
                raise FamilyInputError(
                    f"OFFICIAL_SIDECAR_USE_CHANGED:{source_ref}"
                )
            routes.extend(
                parse_official_sidecar(
                    source_ref=source_ref,
                    path=_repo_path(root, str(sidecar["path"])),
                    format_name=str(sidecar["format"]),
                    timing=str(sidecar["timing"]),
                    expected_sha256=str(sidecar["sha256"]),
                )
            )
    provenance = {
        "adapter": "canonical_new_source_full_timeline_v1",
        "index_root": output.relative_to(root).as_posix(),
        "build_manifest_hash": build.get("build_manifest_hash"),
        "index_hash": index["index_hash"],
        "observation_manifest_hash": observation["observation_manifest_hash"],
        "segment_manifest_hash": segment["segment_manifest_hash"],
        "resource_manifest_hash": resource["resource_manifest_hash"],
        "complete_non_smoke_index_required": True,
    }
    return (
        index,
        dict(index["source_hashes"]),
        _load_routing_records(root, observation),
        tuple(routes),
        provenance,
    )


def load_frozen_noaa_development(
    repo_root: str | Path,
    *,
    index_root: str | Path = "data/restricted/noaa01/scale1a",
) -> tuple[
    Mapping[str, Any],
    Mapping[str, str],
    tuple[Mapping[str, Any], ...],
    Mapping[str, Any],
]:
    """Load frozen NOAA development inputs without treating them as gold."""
    root = Path(repo_root).resolve()
    output = _repo_path(root, index_root)
    missing = [name for name in NOAA_ARTIFACTS if not (output / name).is_file()]
    if missing:
        raise FamilyInputError(
            "NOAA_DEVELOPMENT_INPUT_INCOMPLETE:" + ",".join(sorted(missing))
        )
    build = _load(output / "build_manifest.json")
    index_path = output / "full_timeline_index.json"
    families_path = output / "migrated_families.json"
    _verify_inventory_artifact(root, build, index_path)
    _verify_inventory_artifact(root, build, families_path)
    index = _load(index_path)
    families = _load(families_path)
    if not _self_hash(index, "index_hash"):
        raise FamilyInputError("NOAA_INDEX_SELF_HASH_INVALID")
    if not _self_hash(families, "migration_hash"):
        raise FamilyInputError("NOAA_FAMILY_SELF_HASH_INVALID")
    if any(
        document.get("human_reviewed") is not False
        or document.get("gold_annotation") is not False
        for document in (index, families, build)
    ):
        raise FamilyInputError("NOAA_INPUT_MUST_REMAIN_MACHINE_PROVISIONAL")
    retained = tuple(
        dict(item)
        for item in families.get("families", ())
        if item.get("migration_disposition") == "retained"
    )
    if len(retained) != 5 or families.get("retained_family_count") != 5:
        raise FamilyInputError("NOAA_RETAINED_FAMILY_FREEZE_CHANGED")
    for family in retained:
        if family.get("human_reviewed") is not False:
            raise FamilyInputError("NOAA_RETAINED_FAMILY_HUMAN_STATUS_CHANGED")
        if family.get("gold_annotation") is not False:
            raise FamilyInputError("NOAA_RETAINED_FAMILY_GOLD_STATUS_CHANGED")
        if family.get("minimality_human_validated") is not False:
            raise FamilyInputError("NOAA_HUMAN_MINIMALITY_STATUS_CHANGED")
        if family.get("modality_necessity_human_validated") is not False:
            raise FamilyInputError("NOAA_HUMAN_NECESSITY_STATUS_CHANGED")
    provenance = {
        "adapter": "frozen_noaa_scale1a_development",
        "index_root": output.relative_to(root).as_posix(),
        "build_manifest_hash": build.get("build_manifest_hash"),
        "index_hash": index["index_hash"],
        "migration_hash": families["migration_hash"],
        "retained_family_count": 5,
        "development_only": True,
        "future_primary_test_excluded": True,
    }
    return index, dict(index["source_hashes"]), retained, provenance


def load_mining_inputs(
    repo_root: str | Path,
    *,
    new_index_root: str | Path = "data/restricted/mini_pilot_index_v1",
    noaa_index_root: str | Path = "data/restricted/noaa01/scale1a",
) -> MiningInputs:
    """Load both inputs, failing before mining when either freeze is invalid."""
    (
        new_index,
        new_hashes,
        routing,
        transcript_routes,
        new_provenance,
    ) = load_canonical_new_source_index(repo_root, index_root=new_index_root)
    (
        noaa_index,
        noaa_hashes,
        noaa_families,
        noaa_provenance,
    ) = load_frozen_noaa_development(repo_root, index_root=noaa_index_root)
    return MiningInputs(
        new_index=new_index,
        noaa_index=noaa_index,
        new_source_hashes=new_hashes,
        noaa_source_hashes=noaa_hashes,
        new_routing_records=routing,
        official_transcript_routes=transcript_routes,
        noaa_families=noaa_families,
        provenance={
            "new_source": new_provenance,
            "noaa_development": noaa_provenance,
        },
    )


def sidecar_query(
    routes: Iterable[TranscriptRoute],
    *,
    source_ref: str,
    query: str,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Return lexical sidecar matches as non-citable route-risk records."""
    query_tokens = set(_tokens(query))
    scored = []
    for route in routes:
        if route.source_ref != source_ref or not route.tokens:
            continue
        overlap = query_tokens.intersection(route.tokens)
        if not overlap:
            continue
        score = len(overlap) / max(1, len(query_tokens))
        scored.append(
            {
                "route_id": route.route_id,
                "source_ref": route.source_ref,
                "format": route.format,
                "timing": route.timing,
                "start_us": route.start_us,
                "end_us": route.end_us,
                "matched_terms": sorted(overlap),
                "score": round(score, 8),
                "citable": False,
                "use": route.use,
            }
        )
    scored.sort(
        key=lambda item: (
            -item["score"],
            item["start_us"] if item["start_us"] is not None else -1,
            item["route_id"],
        )
    )
    return scored[:top_k]
