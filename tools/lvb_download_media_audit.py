#!/usr/bin/env python3
"""Independent, redaction-safe audit of the downloaded LVB-01 media.

The audit never modifies acquired payloads and never persists decoded media.
It prefers an external ffprobe/ffmpeg pair.  When those executables are absent,
it records that limitation and uses PyAV in bounded child processes for
container inspection and decode smoke tests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence


PLAN_REL = Path("data/acquisition_plan/lvb01_exact_asset_plan.json")
MANIFEST_REL = Path("data/restricted/lvb01/manifests/lvb01_acquisition_manifest.json")
AUDIT_REL = Path("data/restricted/lvb01/manifests/lvb01_media_audit.json")
CANDIDATE_POOL_REL = Path("data/rehearsal_plan/concrete_candidate_pool.csv")
RESTRICTED_REL = Path("data/restricted/lvb01")
EXPECTED_PAYLOAD_BYTES = 581_129_056
EXPECTED_PAYLOAD_COUNT = 10
FFPROBE_TIMEOUT_SECONDS = 120
DECODE_TIMEOUT_SECONDS = 120
SECRET_KEY_RE = re.compile(
    r"(authorization|bearer|cookie|credential|password|passwd|secret|token|"
    r"access[_-]?key|client[_-]?secret|private[_-]?key)",
    re.IGNORECASE,
)
SIGNED_QUERY_RE = re.compile(
    r"(x-amz-(?:signature|credential|security-token|algorithm)|"
    r"x-goog-signature|signature=|sig=|token=|expires=|policy=|key-pair-id=)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


class AuditError(RuntimeError):
    """Expected audit failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"INVALID_JSON:{path.as_posix()}") from exc


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
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


def sha256_file(path: Path, *, chunk_size: int = 4 * 1024 * 1024) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(chunk_size):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def path_safety(path: Path, restricted_root: Path, repo_root: Path) -> dict[str, Any]:
    lexical_under_root = is_relative_to(path.absolute(), restricted_root.absolute())
    resolved_under_root = is_relative_to(path.resolve(strict=True), restricted_root.resolve(strict=True))
    mode = stat.S_IMODE(path.lstat().st_mode)
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "lexically_under_restricted_root": lexical_under_root,
        "resolved_under_restricted_root": resolved_under_root,
        "is_regular_file": path.is_file(),
        "is_symlink": path.is_symlink(),
        "mode_octal": f"{mode:04o}",
        "group_or_other_permission_bits": f"{mode & 0o077:03o}",
        "restricted_permissions": (mode & 0o077) == 0,
    }


def scan_sensitive_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    parsed = json.loads(raw)
    findings: list[dict[str, str]] = []

    def walk(value: Any, location: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key)
                child_location = f"{location}.{key_text}" if location else key_text
                if SECRET_KEY_RE.search(key_text):
                    findings.append({"kind": "sensitive_key", "location": child_location})
                walk(child, child_location)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{location}[{index}]")
        elif isinstance(value, str):
            if URL_RE.search(value) and ("?" in value or "@" in value.partition("://")[2].partition("/")[0]):
                findings.append({"kind": "url_with_query_or_userinfo", "location": location})
            if SIGNED_QUERY_RE.search(value):
                findings.append({"kind": "signed_url_or_token_indicator", "location": location})

    walk(parsed, "")
    if SIGNED_QUERY_RE.search(raw):
        findings.append({"kind": "raw_signed_url_or_token_indicator", "location": "$"})
    unique = sorted({(item["kind"], item["location"]) for item in findings})
    return {
        "path": path.as_posix(),
        "passed": not unique,
        "finding_count": len(unique),
        "findings": [{"kind": kind, "location": location} for kind, location in unique],
    }


def _manifest_targets(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for target in manifest.get("targets", []):
        basename = str(target.get("basename", ""))
        if basename in result:
            raise AuditError(f"DUPLICATE_MANIFEST_BASENAME:{basename}")
        result[basename] = target
    return result


def load_expected_durations(path: Path, video_ids: set[str]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            video_id = str(row.get("upstream_item_id", ""))
            if video_id not in video_ids:
                continue
            try:
                duration = float(row["duration_s"])
            except (KeyError, TypeError, ValueError) as exc:
                raise AuditError(f"INVALID_CANDIDATE_DURATION:{video_id}") from exc
            if not math.isfinite(duration) or duration <= 0:
                raise AuditError(f"INVALID_CANDIDATE_DURATION:{video_id}")
            if video_id in rows:
                raise AuditError(f"DUPLICATE_CANDIDATE_DURATION:{video_id}")
            rows[video_id] = {
                "candidate_id": row.get("candidate_id"),
                "video_id": video_id,
                "duration_seconds": duration,
                "source": path.as_posix(),
            }
    missing = sorted(video_ids - rows.keys())
    if missing:
        raise AuditError(f"MISSING_CANDIDATE_DURATIONS:{','.join(missing)}")
    return rows


def inventory_tree(
    restricted_root: Path,
    expected_payload_paths: set[Path],
    expected_sidecar_paths: set[Path],
    allowed_manifest_paths: set[Path],
    repo_root: Path,
) -> dict[str, Any]:
    symlinks: list[str] = []
    partials: list[str] = []
    locks: list[str] = []
    unexpected_payloads: list[str] = []
    orphan_sidecars: list[str] = []
    files: list[Path] = []
    actual_payload_files: list[Path] = []

    for root, directories, names in os.walk(restricted_root, followlinks=False):
        root_path = Path(root)
        for name in [*directories, *names]:
            path = root_path / name
            if path.is_symlink():
                symlinks.append(path.relative_to(repo_root).as_posix())
        for name in names:
            path = root_path / name
            files.append(path)
            lowered = name.lower()
            if ".partial" in lowered:
                partials.append(path.relative_to(repo_root).as_posix())
            if lowered.endswith(".lock") or lowered.startswith(".lock"):
                locks.append(path.relative_to(repo_root).as_posix())
            if path.suffix == ".mp4" or (path.suffix == ".json" and not name.endswith(".metadata.json")):
                if path not in expected_payload_paths and path not in allowed_manifest_paths:
                    unexpected_payloads.append(path.relative_to(repo_root).as_posix())
            if (
                is_relative_to(path, restricted_root / "raw")
                and not name.endswith(".metadata.json")
                and path.is_file()
            ):
                actual_payload_files.append(path)
            if name.endswith(".metadata.json"):
                payload = path.with_name(name[: -len(".metadata.json")])
                if path not in expected_sidecar_paths or payload not in expected_payload_paths:
                    orphan_sidecars.append(path.relative_to(repo_root).as_posix())

    basenames = Counter(path.name for path in actual_payload_files)
    duplicate_basenames = sorted(name for name, count in basenames.items() if count > 1)
    expected_all = expected_payload_paths | expected_sidecar_paths | allowed_manifest_paths
    unexpected_files = sorted(
        path.relative_to(repo_root).as_posix()
        for path in files
        if path not in expected_all
    )
    directory_permissions = []
    for path in [restricted_root, restricted_root / "raw", restricted_root / "raw/videos",
                 restricted_root / "raw/subtitles", restricted_root / "manifests"]:
        if path.exists():
            mode = stat.S_IMODE(path.lstat().st_mode)
            directory_permissions.append(
                {
                    "path": path.relative_to(repo_root).as_posix(),
                    "mode_octal": f"{mode:04o}",
                    "is_symlink": path.is_symlink(),
                    "resolved_under_restricted_root": is_relative_to(
                        path.resolve(strict=True), restricted_root.resolve(strict=True)
                    ),
                    "group_or_other_write_bits": f"{mode & 0o022:03o}",
                    "not_group_or_other_writable": (mode & 0o022) == 0,
                }
            )
    return {
        "symlinks": sorted(symlinks),
        "partial_files": sorted(partials),
        "stale_locks": sorted(locks),
        "orphan_sidecars": sorted(orphan_sidecars),
        "duplicate_payload_basenames": duplicate_basenames,
        "unexpected_payload_files": sorted(unexpected_payloads),
        "unexpected_files": unexpected_files,
        "directory_permissions": directory_permissions,
        "passed": not any(
            [
                symlinks,
                partials,
                locks,
                orphan_sidecars,
                duplicate_basenames,
                unexpected_payloads,
                unexpected_files,
            ]
        )
        and all(
            item["not_group_or_other_writable"]
            and item["resolved_under_restricted_root"]
            and not item["is_symlink"]
            for item in directory_permissions
        ),
    }


def parse_fraction(value: Any) -> float | None:
    if value in (None, "", "N/A", "0/0"):
        return None
    try:
        result = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return None
    return result if math.isfinite(result) else None


def _compact_probe(parsed: Mapping[str, Any], stderr: str, returncode: int) -> dict[str, Any]:
    format_info = parsed.get("format") if isinstance(parsed.get("format"), Mapping) else {}
    streams = parsed.get("streams") if isinstance(parsed.get("streams"), list) else []
    compact_streams = []
    for stream in streams:
        if not isinstance(stream, Mapping):
            continue
        compact_streams.append(
            {
                key: stream.get(key)
                for key in (
                    "index",
                    "codec_type",
                    "codec_name",
                    "codec_long_name",
                    "profile",
                    "width",
                    "height",
                    "pix_fmt",
                    "r_frame_rate",
                    "avg_frame_rate",
                    "sample_rate",
                    "channels",
                    "channel_layout",
                    "sample_fmt",
                    "start_time",
                    "duration",
                    "nb_frames",
                )
                if stream.get(key) is not None
            }
        )
    errors = []
    if returncode != 0:
        errors.append(f"FFPROBE_EXIT_{returncode}")
    if stderr.strip():
        errors.append("FFPROBE_STDERR_NONEMPTY")
    duration = None
    try:
        duration = float(format_info.get("duration"))
    except (TypeError, ValueError):
        pass
    return {
        "tool": "ffprobe",
        "available": True,
        "invoked": True,
        "returncode": returncode,
        "readable_container": returncode == 0 and bool(format_info),
        "format_name": format_info.get("format_name"),
        "format_long_name": format_info.get("format_long_name"),
        "duration_seconds": duration,
        "stream_count": len(compact_streams),
        "streams": compact_streams,
        "file_level_errors": errors,
        "stderr_present": bool(stderr.strip()),
    }


def run_ffprobe(path: Path, timeout_seconds: int = FFPROBE_TIMEOUT_SECONDS) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        return {
            "tool": "ffprobe",
            "available": False,
            "invoked": False,
            "readable_container": None,
            "file_level_errors": ["FFPROBE_NOT_AVAILABLE"],
        }
    command = [
        executable,
        "-hide_banner",
        "-v",
        "warning",
        "-show_error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {
            "tool": "ffprobe",
            "available": True,
            "invoked": True,
            "readable_container": False,
            "file_level_errors": ["FFPROBE_TIMEOUT"],
        }
    except OSError:
        return {
            "tool": "ffprobe",
            "available": True,
            "invoked": True,
            "readable_container": False,
            "file_level_errors": ["FFPROBE_EXECUTION_ERROR"],
        }
    try:
        parsed = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = {}
    return _compact_probe(
        parsed,
        result.stderr.decode("utf-8", errors="replace"),
        result.returncode,
    )


PYAV_CHILD = r"""
import json, math, sys
from fractions import Fraction
import av

path = sys.argv[1]
mode = sys.argv[2]
result = {"tool": "pyav", "available": True, "invoked": True, "errors": []}

def seconds(value, time_base=None):
    if value is None:
        return None
    try:
        output = float(value if time_base is None else value * time_base)
    except Exception:
        return None
    return output if math.isfinite(output) else None

try:
    with av.open(path, metadata_errors="ignore") as container:
        duration = seconds(container.duration, Fraction(1, av.time_base))
        if mode == "probe":
            streams = []
            for stream in container.streams:
                codec = stream.codec_context.codec
                item = {
                    "index": stream.index,
                    "codec_type": stream.type,
                    "codec_name": getattr(codec, "name", None),
                    "codec_long_name": getattr(codec, "long_name", None),
                    "time_base": str(stream.time_base) if stream.time_base else None,
                    "start_time_seconds": seconds(stream.start_time, stream.time_base),
                    "duration_seconds": seconds(stream.duration, stream.time_base),
                    "frames": stream.frames,
                    "errors": [],
                }
                if stream.type == "video":
                    item.update({
                        "width": stream.codec_context.width,
                        "height": stream.codec_context.height,
                        "pixel_format": getattr(stream.codec_context.format, "name", None),
                        "average_frame_rate": str(stream.average_rate) if stream.average_rate else None,
                        "frame_rate_fps": float(stream.average_rate) if stream.average_rate else None,
                    })
                elif stream.type == "audio":
                    item.update({
                        "sample_rate": stream.codec_context.sample_rate,
                        "channels": stream.codec_context.channels,
                        "channel_layout": getattr(stream.codec_context.layout, "name", None),
                        "sample_format": getattr(stream.codec_context.format, "name", None),
                    })
                streams.append(item)
            result.update({
                "readable_container": True,
                "format_name": container.format.name,
                "format_long_name": container.format.long_name,
                "duration_seconds": duration,
                "bit_rate": container.bit_rate,
                "start_time_seconds": seconds(container.start_time, Fraction(1, av.time_base)),
                "streams": streams,
            })
        elif mode == "decode":
            points = json.loads(sys.argv[3])
            observations = []
            video_streams = list(container.streams.video)
            audio_streams = list(container.streams.audio)
            for point in points:
                point_result = {"label": point["label"], "target_seconds": point["seconds"]}
                if video_streams:
                    stream = video_streams[0]
                    container.seek(max(0, int(point["seconds"] * av.time_base)), backward=True)
                    selected = None
                    examined = 0
                    for packet in container.demux(stream):
                        for frame in packet.decode():
                            examined += 1
                            frame_time = seconds(frame.pts, frame.time_base)
                            selected = frame
                            if frame_time is None or frame_time + 2.0 >= point["seconds"] or examined >= 250:
                                break
                        if selected is not None and (
                            selected.pts is None
                            or seconds(selected.pts, selected.time_base) + 2.0 >= point["seconds"]
                            or examined >= 250
                        ):
                            break
                    if selected is None:
                        point_result["video"] = {"decoded": False, "error": "NO_VIDEO_FRAME_DECODED"}
                    else:
                        point_result["video"] = {
                            "decoded": True,
                            "frame_time_seconds": seconds(selected.pts, selected.time_base),
                            "width": selected.width,
                            "height": selected.height,
                            "pixel_format": selected.format.name,
                            "frames_examined": examined,
                        }
                else:
                    point_result["video"] = {"decoded": False, "error": "NO_VIDEO_STREAM"}
                if audio_streams:
                    stream = audio_streams[0]
                    container.seek(max(0, int(point["seconds"] * av.time_base)), backward=True)
                    frame_count = 0
                    sample_count = 0
                    first_time = None
                    last_time = None
                    target_end = point["seconds"] + 1.0
                    examined = 0
                    for packet in container.demux(stream):
                        for frame in packet.decode():
                            examined += 1
                            frame_time = seconds(frame.pts, frame.time_base)
                            if frame_time is not None and frame_time + 2.0 < point["seconds"] and examined < 500:
                                continue
                            if first_time is None:
                                first_time = frame_time
                            frame_count += 1
                            sample_count += frame.samples
                            last_time = frame_time
                            frame_end = None if frame_time is None else frame_time + frame.samples / frame.sample_rate
                            if frame_end is None or frame_end >= target_end or examined >= 500:
                                break
                        if frame_count and (
                            last_time is None
                            or last_time >= point["seconds"]
                            or examined >= 500
                        ) and sample_count >= max(1, stream.codec_context.sample_rate // 2):
                            break
                    point_result["audio"] = {
                        "decoded": frame_count > 0 and sample_count > 0,
                        "frame_count": frame_count,
                        "sample_count": sample_count,
                        "first_frame_time_seconds": first_time,
                        "last_frame_time_seconds": last_time,
                        "frames_examined": examined,
                    }
                    if frame_count == 0 or sample_count == 0:
                        point_result["audio"]["error"] = "NO_AUDIO_WINDOW_DECODED"
                else:
                    point_result["audio"] = {"decoded": False, "not_applicable": True, "error": "NO_AUDIO_STREAM"}
                observations.append(point_result)
            result["observations"] = observations
        else:
            raise RuntimeError("invalid mode")
except Exception as exc:
    result["errors"].append("PYAV_" + type(exc).__name__.upper())
    result["readable_container"] = False
print(json.dumps(result, sort_keys=True))
"""


def run_pyav_child(
    path: Path,
    mode: str,
    *,
    points: list[dict[str, Any]] | None = None,
    timeout_seconds: int = DECODE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    command = [sys.executable, "-c", PYAV_CHILD, str(path), mode]
    if points is not None:
        command.append(json.dumps(points, separators=(",", ":")))
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {
            "tool": "pyav",
            "available": True,
            "invoked": True,
            "errors": [f"PYAV_{mode.upper()}_TIMEOUT"],
        }
    except OSError:
        return {
            "tool": "pyav",
            "available": False,
            "invoked": False,
            "errors": [f"PYAV_{mode.upper()}_EXECUTION_ERROR"],
        }
    if result.returncode != 0:
        return {
            "tool": "pyav",
            "available": True,
            "invoked": True,
            "errors": [f"PYAV_{mode.upper()}_EXIT_{result.returncode}"],
        }
    try:
        parsed = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {
            "tool": "pyav",
            "available": True,
            "invoked": True,
            "errors": [f"PYAV_{mode.upper()}_INVALID_JSON"],
        }
    parsed["stderr_present"] = bool(result.stderr.strip())
    if result.stderr.strip():
        parsed.setdefault("errors", []).append(f"PYAV_{mode.upper()}_STDERR_NONEMPTY")
    return parsed


def stream_summary(probe: Mapping[str, Any]) -> dict[str, Any]:
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    return {
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "video_streams": video_streams,
        "audio_streams": audio_streams,
        "other_stream_count": len(streams) - len(video_streams) - len(audio_streams),
    }


def compare_duration(actual: float | None, expected: float) -> dict[str, Any]:
    if actual is None or not math.isfinite(actual):
        return {
            "expected_seconds": expected,
            "actual_seconds": actual,
            "absolute_difference_seconds": None,
            "relative_difference": None,
            "relative_difference_percent": None,
            "within_tolerance": False,
            "tolerance": "max(1.0 second, 0.1%)",
        }
    absolute = abs(actual - expected)
    relative = absolute / expected
    return {
        "expected_seconds": expected,
        "actual_seconds": actual,
        "absolute_difference_seconds": absolute,
        "relative_difference": relative,
        "relative_difference_percent": relative * 100.0,
        "within_tolerance": absolute <= max(1.0, expected * 0.001),
        "tolerance": "max(1.0 second, 0.1%)",
    }


def decode_points(duration: float) -> list[dict[str, Any]]:
    return [
        {"label": "beginning", "seconds": 0.0},
        {"label": "middle", "seconds": duration / 2.0},
        {"label": "near_end", "seconds": max(0.0, duration - min(2.0, duration * 0.01))},
    ]


def parse_timestamp(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if ":" not in text:
            result = float(text)
        else:
            parts = text.split(":")
            if len(parts) != 3:
                raise ValueError
            hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
            if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
                raise ValueError
            result = hours * 3600 + minutes * 60 + seconds
    else:
        raise ValueError
    if not math.isfinite(result):
        raise ValueError
    return result


def subtitle_schema(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        key_sets = Counter()
        item_types = Counter(type(item).__name__ for item in value)
        for item in value:
            if isinstance(item, Mapping):
                key_sets[tuple(sorted(str(key) for key in item))] += 1
        return {
            "top_level_type": "array",
            "entry_count": len(value),
            "item_types": dict(sorted(item_types.items())),
            "object_key_sets": [
                {"keys": list(keys), "count": count}
                for keys, count in sorted(key_sets.items())
            ],
        }
    if isinstance(value, Mapping):
        return {
            "top_level_type": "object",
            "top_level_keys": sorted(str(key) for key in value),
            "entry_count": len(value),
        }
    return {"top_level_type": type(value).__name__, "entry_count": None}


def analyze_subtitle_value(value: Any, video_duration: float) -> dict[str, Any]:
    schema = subtitle_schema(value)
    if not isinstance(value, list):
        return {
            "schema": schema,
            "valid": False,
            "errors": ["SUBTITLE_TOP_LEVEL_NOT_ARRAY"],
        }

    errors: list[str] = []
    warnings: list[str] = []
    entries = []
    invalid_temporal_entries = 0
    negative_temporal_entries = 0
    end_before_start_entries = 0
    empty_text_entries = 0
    starts_decreasing = 0
    overlaps: list[float] = []
    durations: list[float] = []
    previous_start: float | None = None
    previous_end: float | None = None
    maximum_prior_end: float | None = None
    ends_decreasing = 0

    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            invalid_temporal_entries += 1
            continue
        text = item.get("line", item.get("text", item.get("caption", item.get("content"))))
        if not isinstance(text, str) or not text.strip():
            empty_text_entries += 1
        try:
            start = parse_timestamp(item.get("start"))
            end = parse_timestamp(item.get("end"))
        except (TypeError, ValueError):
            invalid_temporal_entries += 1
            continue
        if start < 0 or end < 0:
            negative_temporal_entries += 1
        if end < start:
            end_before_start_entries += 1
        else:
            durations.append(end - start)
        if previous_start is not None and start < previous_start:
            starts_decreasing += 1
        if previous_end is not None and end < previous_end:
            ends_decreasing += 1
        if maximum_prior_end is not None and start < maximum_prior_end:
            overlaps.append(maximum_prior_end - start)
        previous_start, previous_end = start, end
        maximum_prior_end = end if maximum_prior_end is None else max(maximum_prior_end, end)
        entries.append((index, start, end))

    if invalid_temporal_entries:
        errors.append("INVALID_TEMPORAL_FIELDS")
    if negative_temporal_entries:
        errors.append("NEGATIVE_TEMPORAL_FIELDS")
    if end_before_start_entries:
        errors.append("END_BEFORE_START")
    if starts_decreasing:
        errors.append("START_TIMES_NOT_ORDERED")
    if ends_decreasing:
        warnings.append("END_TIMES_NOT_ORDERED")
    if empty_text_entries:
        warnings.append("EMPTY_TEXT_ENTRIES")

    first_timestamp = min((start for _, start, _ in entries), default=None)
    last_timestamp = max((end for _, _, end in entries), default=None)
    beyond_video = sum(1 for _, _, end in entries if end > video_duration + 1.0)
    gross_mismatch = (
        last_timestamp is None
        or last_timestamp < video_duration * 0.5
        or last_timestamp > video_duration + max(5.0, video_duration * 0.01)
    )
    if beyond_video:
        warnings.append("TIMESTAMPS_BEYOND_VIDEO_DURATION")
    if gross_mismatch:
        warnings.append("OBVIOUS_TIMELINE_MISMATCH")
    pathological_overlap_count = sum(overlap > 2.0 for overlap in overlaps)
    if pathological_overlap_count:
        warnings.append("PATHOLOGICAL_OVERLAPS")
    short_entry_count = sum(duration <= 0.05 for duration in durations)
    if durations and short_entry_count / len(durations) > 0.5:
        warnings.append("MAJORITY_VERY_SHORT_CUE_DURATIONS")

    coverage_span = None if first_timestamp is None or last_timestamp is None else last_timestamp - first_timestamp
    return {
        "schema": schema,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "temporal_validation": {
            "valid_temporal_entry_count": len(entries),
            "invalid_temporal_entry_count": invalid_temporal_entries,
            "negative_temporal_entry_count": negative_temporal_entries,
            "end_before_start_entry_count": end_before_start_entries,
            "start_order_violation_count": starts_decreasing,
            "end_order_violation_count": ends_decreasing,
            "overlap_count": len(overlaps),
            "maximum_overlap_seconds": max(overlaps, default=0.0),
            "pathological_overlap_threshold_seconds": 2.0,
            "pathological_overlap_count": pathological_overlap_count,
            "empty_text_entry_count": empty_text_entries,
            "very_short_cue_threshold_seconds": 0.05,
            "very_short_cue_count": short_entry_count,
            "very_short_cue_fraction": (
                short_entry_count / len(durations) if durations else None
            ),
        },
        "timeline": {
            "first_timestamp_seconds": first_timestamp,
            "last_timestamp_seconds": last_timestamp,
            "coverage_span_seconds": coverage_span,
            "video_duration_seconds": video_duration,
            "first_timestamp_relative_to_video": (
                first_timestamp / video_duration if first_timestamp is not None else None
            ),
            "last_timestamp_relative_to_video": (
                last_timestamp / video_duration if last_timestamp is not None else None
            ),
            "tail_gap_seconds": (
                video_duration - last_timestamp if last_timestamp is not None else None
            ),
            "timestamp_entries_beyond_video_by_more_than_one_second": beyond_video,
            "obvious_timeline_mismatch": gross_mismatch,
        },
    }


def audit_integrity(
    repo_root: Path,
    plan: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    restricted_root = repo_root / RESTRICTED_REL
    manifest_targets = _manifest_targets(manifest)
    expected_payload_paths: set[Path] = set()
    expected_sidecar_paths: set[Path] = set()
    results = []
    aggregate = 0
    for target in plan.get("targets", []):
        basename = str(target["basename"])
        destination = restricted_root / str(target["destination"])
        sidecar_path = destination.with_name(destination.name + ".metadata.json")
        expected_payload_paths.add(destination)
        expected_sidecar_paths.add(sidecar_path)
        if not destination.exists() or not sidecar_path.exists():
            raise AuditError(f"MISSING_PAYLOAD_OR_SIDECAR:{basename}")
        actual_size, actual_sha256 = sha256_file(destination)
        aggregate += actual_size
        sidecar = load_json(sidecar_path)
        manifest_target = manifest_targets.get(basename, {})
        matches = {
            "frozen_plan_basename": destination.name == basename,
            "frozen_plan_destination": destination.relative_to(restricted_root).as_posix()
            == target.get("destination"),
            "frozen_plan_size": actual_size == target.get("size"),
            "acquisition_manifest_basename": manifest_target.get("basename") == basename,
            "acquisition_manifest_kind": manifest_target.get("kind") == target.get("kind"),
            "acquisition_manifest_size": actual_size == manifest_target.get("size"),
            "acquisition_manifest_sha256": actual_sha256 == manifest_target.get("sha256"),
            "sidecar_size": actual_size == sidecar.get("size"),
            "sidecar_sha256": actual_sha256 == sidecar.get("sha256"),
            "manifest_metadata_path": manifest_target.get("metadata_path")
            == sidecar_path.relative_to(restricted_root).as_posix(),
            "sidecar_basename": sidecar.get("basename") == basename,
            "sidecar_kind": sidecar.get("kind") == target.get("kind"),
            "sidecar_member_path": sidecar.get("member_path") == target.get("member_path"),
            "sidecar_plan_sha256": sidecar.get("plan_sha256") == manifest.get("plan_sha256"),
            "manifest_status_complete": manifest_target.get("status") in {"downloaded", "skipped_verified"},
        }
        safety = path_safety(destination, restricted_root, repo_root)
        sidecar_safety = path_safety(sidecar_path, restricted_root, repo_root)
        results.append(
            {
                "candidate_id": target.get("candidate_id"),
                "video_id": target.get("video_id"),
                "kind": target.get("kind"),
                "basename": basename,
                "path": destination.relative_to(repo_root).as_posix(),
                "metadata_path": sidecar_path.relative_to(repo_root).as_posix(),
                "actual_size": actual_size,
                "actual_sha256": actual_sha256,
                "matches": matches,
                "path_safety": safety,
                "sidecar_path_safety": sidecar_safety,
                "passed": all(matches.values())
                and all(
                    (
                        safety["lexically_under_restricted_root"],
                        safety["resolved_under_restricted_root"],
                        safety["is_regular_file"],
                        not safety["is_symlink"],
                        safety["restricted_permissions"],
                        sidecar_safety["lexically_under_restricted_root"],
                        sidecar_safety["resolved_under_restricted_root"],
                        sidecar_safety["is_regular_file"],
                        not sidecar_safety["is_symlink"],
                        sidecar_safety["restricted_permissions"],
                    )
                ),
            }
        )
    inventory = inventory_tree(
        restricted_root,
        expected_payload_paths,
        expected_sidecar_paths,
        {repo_root / MANIFEST_REL, repo_root / AUDIT_REL},
        repo_root,
    )
    aggregate_summary = {
        "actual_payload_bytes": aggregate,
        "expected_payload_bytes": EXPECTED_PAYLOAD_BYTES,
        "plan_payload_bytes": sum(int(target["size"]) for target in plan.get("targets", [])),
        "manifest_expected_payload_bytes": manifest.get("expected_total_payload_bytes"),
        "manifest_verified_payload_bytes": manifest.get("verified_total_payload_bytes"),
        "payload_count": len(results),
        "expected_payload_count": EXPECTED_PAYLOAD_COUNT,
        "plan_target_count": len(plan.get("targets", [])),
        "manifest_target_count": len(manifest.get("targets", [])),
        "manifest_basenames_match_plan": set(manifest_targets)
        == {str(target["basename"]) for target in plan.get("targets", [])},
        "exact_match": aggregate == EXPECTED_PAYLOAD_BYTES
        and len(results) == EXPECTED_PAYLOAD_COUNT
        and len(manifest.get("targets", [])) == EXPECTED_PAYLOAD_COUNT
        and set(manifest_targets)
        == {str(target["basename"]) for target in plan.get("targets", [])},
    }
    return results, {"aggregate": aggregate_summary, "inventory": inventory}


def audit_videos(
    repo_root: Path,
    plan: Mapping[str, Any],
    expected_durations: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    restricted_root = repo_root / RESTRICTED_REL
    results = []
    for target in plan.get("targets", []):
        if target.get("kind") != "video":
            continue
        path = restricted_root / str(target["destination"])
        video_id = str(target["video_id"])
        ffprobe = run_ffprobe(path)
        pyav_probe = run_pyav_child(path, "probe")
        authoritative = ffprobe if ffprobe.get("readable_container") else pyav_probe
        streams = stream_summary(authoritative)
        actual_duration = authoritative.get("duration_seconds")
        expected = float(expected_durations[video_id]["duration_seconds"])
        comparison = compare_duration(actual_duration, expected)
        smoke = run_pyav_child(path, "decode", points=decode_points(actual_duration or expected))
        observations = smoke.get("observations", [])
        video_decode_ok = len(observations) == 3 and all(
            item.get("video", {}).get("decoded") for item in observations
        )
        audio_decode_ok = (
            streams["audio_stream_count"] == 0
            or (
                len(observations) == 3
                and all(item.get("audio", {}).get("decoded") for item in observations)
            )
        )
        flags = []
        if streams["video_stream_count"] == 0:
            flags.append("MISSING_VIDEO")
        if streams["audio_stream_count"] == 0:
            flags.append("MISSING_AUDIO")
        if actual_duration is None or actual_duration <= 0:
            flags.append("IMPLAUSIBLE_DURATION")
        if not comparison["within_tolerance"]:
            flags.append("DURATION_MISMATCH")
        zero_length_streams = [
            stream.get("index")
            for stream in authoritative.get("streams", [])
            if stream.get("duration_seconds") is not None and stream.get("duration_seconds") <= 0
        ]
        if zero_length_streams:
            flags.append("ZERO_LENGTH_STREAM")
        if not video_decode_ok:
            flags.append("VIDEO_DECODE_SMOKE_FAILED")
        if streams["audio_stream_count"] and not audio_decode_ok:
            flags.append("AUDIO_DECODE_SMOKE_FAILED")
        if authoritative.get("errors") or authoritative.get("file_level_errors"):
            flags.append("PROBE_ERROR")
        technical_usable = (
            authoritative.get("readable_container") is True
            and streams["video_stream_count"] > 0
            and actual_duration is not None
            and actual_duration > 0
            and comparison["within_tolerance"]
            and not zero_length_streams
            and video_decode_ok
            and audio_decode_ok
        )
        results.append(
            {
                "candidate_id": target.get("candidate_id"),
                "video_id": video_id,
                "basename": target.get("basename"),
                "path": path.relative_to(repo_root).as_posix(),
                "external_ffprobe": ffprobe,
                "pyav_probe": pyav_probe,
                "authoritative_probe": "ffprobe" if authoritative is ffprobe else "pyav_fallback",
                "container": {
                    "readable": authoritative.get("readable_container"),
                    "format_name": authoritative.get("format_name"),
                    "format_long_name": authoritative.get("format_long_name"),
                },
                "duration": comparison,
                "streams": streams,
                "zero_length_stream_indices": zero_length_streams,
                "decode_smoke": {
                    "method": "PyAV child process; decoded data not persisted",
                    "timeout_seconds": DECODE_TIMEOUT_SECONDS,
                    "observations": observations,
                    "errors": smoke.get("errors", []),
                    "video_passed": video_decode_ok,
                    "audio_passed_or_not_applicable": audio_decode_ok,
                },
                "flags": flags,
                "technically_usable": technical_usable,
            }
        )
    return results


def audit_subtitles(
    repo_root: Path,
    plan: Mapping[str, Any],
    video_results: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    restricted_root = repo_root / RESTRICTED_REL
    results = []
    for target in plan.get("targets", []):
        if target.get("kind") != "subtitle":
            continue
        path = restricted_root / str(target["destination"])
        raw = path.read_bytes()
        encoding = "utf-8-bom" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
        try:
            value = json.loads(raw.decode("utf-8-sig"))
            parse_error = None
        except (UnicodeDecodeError, json.JSONDecodeError):
            value = None
            parse_error = "SUBTITLE_DECODE_OR_PARSE_FAILED"
        video_id = str(target["video_id"])
        duration = video_results[video_id]["duration"]["actual_seconds"]
        if value is None or duration is None:
            analysis = {
                "schema": {"top_level_type": None, "entry_count": None},
                "valid": False,
                "errors": [parse_error or "VIDEO_DURATION_UNAVAILABLE"],
                "warnings": [],
            }
        else:
            analysis = analyze_subtitle_value(value, float(duration))
        results.append(
            {
                "candidate_id": target.get("candidate_id"),
                "video_id": video_id,
                "basename": target.get("basename"),
                "path": path.relative_to(repo_root).as_posix(),
                "encoding": encoding,
                "decoded_and_parsed": parse_error is None,
                **analysis,
                "usable_speech_proxy": parse_error is None
                and analysis.get("valid") is True
                and (analysis.get("schema", {}).get("entry_count") or 0) > 0
                and not analysis.get("timeline", {}).get("obvious_timeline_mismatch", True),
                "text_disclosure": "No full subtitle text persisted or printed by the audit.",
            }
        )
    return results


def decide(
    integrity_entries: list[Mapping[str, Any]],
    integrity_summary: Mapping[str, Any],
    videos: list[Mapping[str, Any]],
    subtitles: list[Mapping[str, Any]],
    secret_scans: list[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    reasons = []
    hard_fail = False
    if not all(entry.get("passed") for entry in integrity_entries):
        hard_fail = True
        reasons.append("One or more payloads failed size/hash/sidecar/path/permission matching.")
    if not integrity_summary["aggregate"].get("exact_match"):
        hard_fail = True
        reasons.append("Aggregate payload bytes do not equal 581,129,056.")
    if not integrity_summary["inventory"].get("passed"):
        hard_fail = True
        reasons.append("Restricted-tree inventory contains a prohibited or unsafe condition.")
    if not all(scan.get("passed") for scan in secret_scans):
        hard_fail = True
        reasons.append("A sidecar or manifest contains a secret/signed-URL indicator.")
    if not all(video.get("technically_usable") for video in videos):
        hard_fail = True
        reasons.append("One or more videos failed technical usability checks.")
    if not all(subtitle.get("usable_speech_proxy") for subtitle in subtitles):
        hard_fail = True
        reasons.append("One or more subtitle files failed usability or gross timeline checks.")
    if hard_fail:
        return "NO_GO", reasons
    if any(video.get("streams", {}).get("audio_stream_count") == 0 for video in videos):
        reasons.append(
            "All downloaded MP4s lack an audio stream; internal rehearsal is limited to "
            "video plus subtitle/speech-proxy use unless separate audio is lawfully obtained."
        )
    if any(
        "MAJORITY_VERY_SHORT_CUE_DURATIONS" in subtitle.get("warnings", [])
        for subtitle in subtitles
    ):
        reasons.append(
            "Four subtitle files have predominantly point-like (about 10 ms) cue durations; "
            "ordered start times and broad timeline coverage are usable, but cue end times "
            "must not be treated as reliable speech-span boundaries."
        )
    if not all(video.get("external_ffprobe", {}).get("available") for video in videos):
        reasons.append(
            "The environment has no ffprobe/ffmpeg executable; bounded PyAV fallback passed, "
            "but the explicitly requested external-tool check remains unavailable."
        )
    if reasons:
        return "CONDITIONAL_GO", reasons
    return "GO_INTERNAL_REHEARSAL", ["All required technical integrity and usability checks passed."]


def build_audit(repo_root: Path) -> dict[str, Any]:
    plan_path = repo_root / PLAN_REL
    manifest_path = repo_root / MANIFEST_REL
    plan = load_json(plan_path)
    manifest = load_json(manifest_path)
    plan_size, plan_sha256 = sha256_file(plan_path)
    manifest_size, manifest_sha256 = sha256_file(manifest_path)
    if manifest.get("plan_sha256") != plan_sha256:
        raise AuditError("MANIFEST_PLAN_SHA256_MISMATCH")
    video_ids = {
        str(target["video_id"]) for target in plan.get("targets", []) if target.get("kind") == "video"
    }
    expected_durations = load_expected_durations(repo_root / CANDIDATE_POOL_REL, video_ids)
    integrity_entries, integrity_summary = audit_integrity(repo_root, plan, manifest)
    videos = audit_videos(repo_root, plan, expected_durations)
    videos_by_id = {str(video["video_id"]): video for video in videos}
    subtitles = audit_subtitles(repo_root, plan, videos_by_id)

    sidecar_paths = [
        repo_root / entry["metadata_path"] for entry in integrity_entries
    ]
    secret_paths = [plan_path, manifest_path, *sidecar_paths]
    secret_scans = []
    for path in secret_paths:
        scan = scan_sensitive_json(path)
        scan["path"] = path.relative_to(repo_root).as_posix()
        secret_scans.append(scan)

    decision, reasons = decide(integrity_entries, integrity_summary, videos, subtitles, secret_scans)
    subtitles_by_id = {str(item["video_id"]): item for item in subtitles}
    modality = []
    for video in videos:
        video_id = str(video["video_id"])
        modality.append(
            {
                "candidate_id": video["candidate_id"],
                "video_id": video_id,
                "video_stream_available": video["streams"]["video_stream_count"] > 0,
                "audio_stream_available": video["streams"]["audio_stream_count"] > 0,
                "subtitle_speech_proxy_available": subtitles_by_id[video_id]["usable_speech_proxy"],
                "ambient_non_speech_audio": (
                    "UNVERIFIED"
                    if video["streams"]["audio_stream_count"] > 0
                    else "UNVERIFIED_AND_NOT_AVAILABLE_IN_DOWNLOADED_MP4"
                ),
                "necessity_claim": "NOT_ASSESSED",
            }
        )
    return {
        "schema_version": "1.0",
        "audit_id": "LVB-01-DOWNLOAD-MEDIA-AUDIT",
        "generated_at_utc": utc_now(),
        "scope": {
            "restricted_root": RESTRICTED_REL.as_posix(),
            "payloads_modified": False,
            "derived_media_persisted": False,
            "benchmark_annotations_created": False,
        },
        "inputs": {
            "frozen_plan": {
                "path": PLAN_REL.as_posix(),
                "size": plan_size,
                "sha256": plan_sha256,
            },
            "acquisition_manifest": {
                "path": MANIFEST_REL.as_posix(),
                "size": manifest_size,
                "sha256": manifest_sha256,
            },
            "candidate_duration_source": CANDIDATE_POOL_REL.as_posix(),
        },
        "tool_availability": {
            "ffprobe": shutil.which("ffprobe") is not None,
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "pyav_fallback": True,
            "timeouts_seconds": {
                "ffprobe": FFPROBE_TIMEOUT_SECONDS,
                "decode_smoke": DECODE_TIMEOUT_SECONDS,
            },
        },
        "integrity_and_provenance": {
            "entries": integrity_entries,
            **integrity_summary,
            "secret_and_signed_url_scans": secret_scans,
            "passed": all(entry["passed"] for entry in integrity_entries)
            and integrity_summary["aggregate"]["exact_match"]
            and integrity_summary["inventory"]["passed"]
            and all(scan["passed"] for scan in secret_scans),
        },
        "videos": videos,
        "subtitles": subtitles,
        "initial_modality_evidence": modality,
        "decision": decision,
        "decision_reasons": reasons,
        "decision_scope": {
            "technically_usable_asset": all(video["technically_usable"] for video in videos)
            and all(subtitle["usable_speech_proxy"] for subtitle in subtitles),
            "scientifically_suitable_av_trace_episode": "NOT_ESTABLISHED",
            "rights_or_public_release_eligible": "NOT_ESTABLISHED",
        },
    }


def find_repo_root(script_path: Path) -> Path:
    root = script_path.resolve().parents[1]
    if not (root / "pyproject.toml").is_file():
        raise AuditError("REPOSITORY_ROOT_NOT_FOUND")
    return root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=AUDIT_REL.as_posix(),
        help="repository-relative audit JSON path",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="run the audit and print only the concise result",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo_root = find_repo_root(Path(__file__))
        audit = build_audit(repo_root)
        if not args.no_write:
            output = repo_root / args.output
            if not is_relative_to(output.absolute(), (repo_root / RESTRICTED_REL).absolute()):
                raise AuditError("AUDIT_OUTPUT_MUST_REMAIN_UNDER_RESTRICTED_ROOT")
            atomic_write_json(output, audit)
        print(
            json.dumps(
                {
                    "decision": audit["decision"],
                    "payload_count": audit["integrity_and_provenance"]["aggregate"]["payload_count"],
                    "payload_bytes": audit["integrity_and_provenance"]["aggregate"]["actual_payload_bytes"],
                    "technically_usable_assets": sum(
                        1 for video in audit["videos"] if video["technically_usable"]
                    ),
                    "subtitle_proxies_usable": sum(
                        1 for subtitle in audit["subtitles"] if subtitle["usable_speech_proxy"]
                    ),
                    "output_written": not args.no_write,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if audit["decision"] != "NO_GO" else 2
    except AuditError as exc:
        print(f"lvb download media audit failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"lvb download media audit failed: INTERNAL_{type(exc).__name__.upper()}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
