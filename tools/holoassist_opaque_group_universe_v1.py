#!/usr/bin/env python3
"""Build a sealed HoloAssist opaque recording-group universe.

Only Hugging Face technical metadata, recording folder paths, and the presence
of ``VideoMp4Timing.txt``/``Pose_sync.txt`` are consumed.  README bodies are
used solely by a narrow recording-ID regex to form a permanent exclusion set.
No annotation, label, title, description, transcript, or media file is opened.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_OUTPUT = ROOT / "data/restricted/holoassist_opaque_group_universe_v1.json"
PUBLIC_OUTPUT = ROOT / "data/rehearsal_plan/holoassist_opaque_group_commitment_v1.json"
INFO = Path("/tmp/holo_hf_info.json")
TREE = Path("/tmp/holo_hf_tree.json")
README_CANDIDATES = (Path("/tmp/holoassist_README.md"), Path("/tmp/holoassist_README.html"))

SCHEMA_PRIVATE = "av-trace.holoassist-opaque-group-universe/1.0"
SCHEMA_PUBLIC = "av-trace.holoassist-opaque-group-commitment/1.0"
READY = "HOLOASSIST_OPAQUE_GROUP_UNIVERSE_READY"
REPAIR = "HOLOASSIST_OPAQUE_GROUP_UNIVERSE_REPAIR"
FROZEN_SALT = "av-trace:holoassist:opaque-group:v1:2026-10-15"
MIN_GROUPS = 6
SELECT_COUNT = 6
EXPLICIT_EXCLUSIONS = frozenset({"R007", "R012", "R013", "R014"})
RID_RE = re.compile(r"(?<![A-Za-z0-9])R(\d{3,})(?!\d)", re.IGNORECASE)
ROOT_RE = re.compile(r"^extracted_videos/([^/]+)")
TIMING_SUFFIX = "/Export_py/Video/VideoMp4Timing.txt"
POSE_SUFFIX = "/Export_py/Video/Pose_sync.txt"
FORBIDDEN_SEMANTIC_KEYS = frozenset(
    {
        "action",
        "annotation",
        "caption",
        "description",
        "instruction",
        "label",
        "narration",
        "prompt",
        "task",
        "task_description",
        "task_title",
        "title",
        "transcript",
    }
)


class UniverseError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_rid(value: str) -> str:
    match = re.fullmatch(r"R(\d+)", value, re.IGNORECASE)
    if not match:
        raise UniverseError("INVALID_RECORDING_ID")
    return f"R{int(match.group(1)):03d}"


def semantic_text_exclusions(paths: tuple[Path, ...] = README_CANDIDATES) -> set[str]:
    """Extract only recording IDs; no semantic structure or field is parsed."""
    excluded: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        for match in RID_RE.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            excluded.add(normalized_rid("R" + match.group(1)))
    return excluded


def _technical_entries(info: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in info.get("siblings", []):
        if not isinstance(item, dict):
            continue
        name = item.get("rfilename")
        if (
            isinstance(name, str)
            and name.startswith("extracted_videos/")
            and name.endswith((TIMING_SUFFIX, POSE_SUFFIX))
        ):
            result.append(name)
    return sorted(set(result))


def _tree_metadata(tree: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for item in tree:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        metadata[item["path"]] = {
            key: item[key] for key in ("oid", "size", "type") if key in item
        }
    return metadata


def _base_identity(path: str) -> str:
    match = ROOT_RE.match(path)
    if not match:
        raise UniverseError("TECHNICAL_PATH_WITHOUT_RECORDING_ROOT")
    folder = match.group(1)
    identity = folder.split("-", 1)[0].upper()
    if not re.fullmatch(r"[A-Z]\d+", identity):
        raise UniverseError("INVALID_BASE_RECORDING_IDENTITY")
    if identity.startswith("R"):
        return normalized_rid(identity)
    return identity


def _folder(path: str) -> str:
    suffix = TIMING_SUFFIX if path.endswith(TIMING_SUFFIX) else POSE_SUFFIX
    return path[: -len(suffix)]


def _rank_material(group: dict[str, Any]) -> bytes:
    technical = []
    for variant in group["variants"]:
        technical.append(
            {
                "folder": variant["folder"],
                "pose_present": variant["pose_present"],
                "timing_present": variant["timing_present"],
                "folder_metadata": variant["folder_metadata"],
            }
        )
    return canonical_json({"salt": FROZEN_SALT, "technical": technical})


def _parse_timing_text(data: bytes) -> dict[str, Any]:
    """Best-effort parser for numeric timing text, used only if locally present."""
    if len(data) > 2 * 1024 * 1024:
        raise UniverseError("TIMING_TEXT_BOUND_EXCEEDED")
    text = data.decode("utf-8", errors="strict")
    rows: list[list[float]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        numbers = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", stripped)
        if numbers:
            rows.append([float(number) for number in numbers])
    if len(rows) < 2:
        return {"format_recognized": False, "frame_count": None, "duration_seconds": None}
    last_column = [row[-1] for row in rows]
    if any(b < a for a, b in itertools.pairwise(last_column)):
        return {"format_recognized": False, "frame_count": None, "duration_seconds": None}
    scale = 1.0
    span = last_column[-1] - last_column[0]
    if span > 100_000:
        scale = 1_000_000.0
    elif span > 10_000:
        scale = 1_000.0
    return {
        "format_recognized": True,
        "frame_count": len(rows),
        "duration_seconds": round(span / scale, 9),
    }


def build_universe(
    info_path: Path = INFO,
    tree_path: Path = TREE,
    readme_paths: tuple[Path, ...] = README_CANDIDATES,
    timing_cache: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    info_bytes = info_path.read_bytes()
    tree_bytes = tree_path.read_bytes()
    info = json.loads(info_bytes)
    tree = json.loads(tree_bytes)
    if not isinstance(info, dict) or not isinstance(tree, list):
        raise UniverseError("INVALID_HF_METADATA_SHAPE")

    excluded = EXPLICIT_EXCLUSIONS | semantic_text_exclusions(readme_paths)
    technical = _technical_entries(info)
    by_root: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for path in technical:
        root = _base_identity(path)
        folder = _folder(path)
        by_root[root][folder].add("timing" if path.endswith(TIMING_SUFFIX) else "pose")

    tree_meta = _tree_metadata(tree)
    candidates: list[dict[str, Any]] = []
    for root, folders in sorted(by_root.items()):
        if root in excluded:
            continue
        variants = []
        for folder, presence in sorted(folders.items()):
            variants.append(
                {
                    "folder": folder,
                    "timing_path": folder + TIMING_SUFFIX,
                    "pose_path": folder + POSE_SUFFIX,
                    "timing_present": "timing" in presence,
                    "pose_present": "pose" in presence,
                    "folder_metadata": tree_meta.get(folder, {}),
                    "timing_metadata": tree_meta.get(folder + TIMING_SUFFIX, {}),
                    "pose_metadata": tree_meta.get(folder + POSE_SUFFIX, {}),
                }
            )
        if variants and all(v["timing_present"] and v["pose_present"] for v in variants):
            group = {"recording_root": root, "variants": variants}
            group["selection_hash"] = sha256_bytes(_rank_material(group))
            candidates.append(group)

    selected = sorted(candidates, key=lambda group: group["selection_hash"])[:SELECT_COUNT]
    timing_closed = 0
    for group in selected:
        parsed_variants = 0
        for variant in group["variants"]:
            evidence = {
                "fetched": False,
                "bytes": 0,
                "sha256": None,
                "format_recognized": False,
                "frame_count": None,
                "duration_seconds": None,
            }
            if timing_cache is not None:
                cached = timing_cache / variant["timing_path"]
                if cached.is_file():
                    data = cached.read_bytes()
                    evidence.update(_parse_timing_text(data))
                    evidence.update({"fetched": True, "bytes": len(data), "sha256": sha256_bytes(data)})
            variant["timing_evidence"] = evidence
            if evidence["format_recognized"]:
                parsed_variants += 1
        group["timing_closed"] = parsed_variants == len(group["variants"])
        if group["timing_closed"]:
            timing_closed += 1
        group["private_commitment"] = sha256_bytes(
            canonical_json(
                {
                    "selection_hash": group["selection_hash"],
                    "recording_root": group["recording_root"],
                    "variants": group["variants"],
                }
            )
        )

    marker = READY if len(selected) >= MIN_GROUPS and timing_closed == len(selected) else REPAIR
    private = {
        "schema_version": SCHEMA_PRIVATE,
        "generated_date": "2026-10-15",
        "final_marker": marker,
        "source": {
            "hf_revision": info.get("sha"),
            "hf_info_sha256": sha256_bytes(info_bytes),
            "hf_tree_sha256": sha256_bytes(tree_bytes),
            "hf_gated": info.get("gated"),
            "hf_mirror_license": (info.get("cardData") or {}).get("license"),
            "official_declared_license": "CDLA-Permissive-2.0",
            "license_discrepancy": True,
            "tree_entries": len(tree),
            "technical_paths": len(technical),
        },
        "policy": {
            "frozen_salt_sha256": sha256_bytes(FROZEN_SALT.encode()),
            "grouping": "leading recording identity; all task/date/device suffix variants share one closure root",
            "collision_policy": "merge every extracted_videos folder with the same normalized leading recording identity",
            "explicit_exclusions": sorted(EXPLICIT_EXCLUSIONS),
            "semantic_text_exclusions": sorted(semantic_text_exclusions(readme_paths)),
            "semantic_fields_accessed": [],
            "media_or_annotation_downloads": 0,
        },
        "inventory": {
            "candidate_group_count": len(candidates),
            "selected_group_count": len(selected),
            "timing_closed_group_count": timing_closed,
            "minimum_required": MIN_GROUPS,
        },
        "selected_groups": selected,
    }
    public = {
        "schema_version": SCHEMA_PUBLIC,
        "generated_date": "2026-10-15",
        "final_marker": marker,
        "lineage": {
            "hf_revision": info.get("sha"),
            "hf_info_sha256": sha256_bytes(info_bytes),
            "hf_tree_sha256": sha256_bytes(tree_bytes),
            "mirror_gated": info.get("gated"),
            "mirror_declared_license": (info.get("cardData") or {}).get("license"),
            "official_declared_license": "CDLA-Permissive-2.0",
            "license_discrepancy_recorded": True,
        },
        "counts": {
            "sealed_group_count": len(selected),
            "timing_closed_group_count": timing_closed,
            "minimum_required": MIN_GROUPS,
        },
        "commitments": sorted(group["private_commitment"] for group in selected),
        "selection_rule_commitment": sha256_bytes(
            canonical_json(
                {
                    "salt": FROZEN_SALT,
                    "grouping": private["policy"]["grouping"],
                    "collision_policy": private["policy"]["collision_policy"],
                    "minimum": MIN_GROUPS,
                    "select": SELECT_COUNT,
                }
            )
        ),
        "private_universe_sha256": sha256_bytes(canonical_json(private)),
    }
    return private, public


def validate_public_identity_absence(public: dict[str, Any]) -> None:
    raw = canonical_json(public).decode()
    if RID_RE.search(raw) or "extracted_videos/" in raw or "VideoMp4Timing" in raw or "Pose_sync" in raw:
        raise UniverseError("PUBLIC_IDENTITY_LEAK")


def write_private(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(canonical_json(value))
    os.chmod(path, 0o600)


def write_public(path: Path, value: dict[str, Any]) -> None:
    validate_public_identity_absence(value)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(canonical_json(value))
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-output", type=Path, default=PRIVATE_OUTPUT)
    parser.add_argument("--public-output", type=Path, default=PUBLIC_OUTPUT)
    parser.add_argument("--timing-cache", type=Path)
    args = parser.parse_args()
    private, public = build_universe(timing_cache=args.timing_cache)
    write_private(args.private_output, private)
    write_public(args.public_output, public)
    print(public["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
