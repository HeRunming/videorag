"""Offline, provider-neutral metadata snapshot import.

This module turns already-captured repository/API and tabular metadata files
into deterministic reconnaissance artifacts.  It intentionally has no URL
loader, HTTP client, media decoder, acquisition manifest writer, or rights
approval path.
"""

from __future__ import annotations

import base64
import binascii
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from .errors import SnapshotImportError
from .io import canonical_json, write_json_atomic
from .models import immutable_revision

SNAPSHOT_INSPECTION_VERSION = "1.0"
DEFAULT_MAX_SOURCE_BYTES = 20 * 1024 * 1024

_TEXT_FORMATS = {".json", ".jsonl", ".csv"}
_SUPPORTED_FORMATS = _TEXT_FORMATS | {".parquet"}
_DISALLOWED_SUFFIXES = {
    # Media.
    ".aac",
    ".avi",
    ".flac",
    ".gif",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogg",
    ".opus",
    ".png",
    ".wav",
    ".webm",
    ".webp",
    # Archives.
    ".7z",
    ".bz2",
    ".gz",
    ".rar",
    ".tar",
    ".tgz",
    ".xz",
    ".zip",
    # Embeddings, checkpoints, and model payloads.
    ".bin",
    ".ckpt",
    ".h5",
    ".joblib",
    ".npy",
    ".npz",
    ".onnx",
    ".pickle",
    ".pkl",
    ".pt",
    ".pth",
    ".safetensors",
}
_BINARY_FIELD_TOKENS = {
    "array",
    "audio",
    "binary",
    "blob",
    "bytes",
    "content_bytes",
    "embedding",
    "frame",
    "image",
    "media",
    "model",
    "payload",
    "tensor",
    "thumbnail",
    "video",
    "waveform",
}
_DATA_URI_RE = re.compile(
    r"^data:(?:audio|video|image|application/(?:zip|octet-stream|x-tar|gzip))"
    r"[^,]*;base64,",
    re.IGNORECASE,
)
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
_GITHUB_REPOSITORY_URL_RE = re.compile(
    r"https?://api\.github\.com/repos/([^/]+/[^/]+)/"
)
_FULL_HEX_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")


@dataclass(frozen=True)
class SnapshotInput:
    """One local input and optional immutable provenance overrides."""

    path: str | Path
    provider: str | None = None
    repository_id: str | None = None
    repository_revision: str | None = None
    repository_revision_kind: str = "git_commit"
    repository_path: str | None = None
    file_revision: str | None = None
    file_revision_kind: str | None = None
    blob_revision: str | None = None
    source_family: str | None = None


@dataclass(frozen=True)
class _LoadedInput:
    spec: SnapshotInput
    path: Path
    local_name: str
    byte_size: int
    sha256: str
    suffix: str
    data: bytes
    parsed: Any


@dataclass
class _RepositoryContext:
    provider: str
    repository_id: str
    repository_revision: str
    repository_revision_kind: str
    source_file_ids: list[str]
    file_inventory: list[dict[str, Any]]
    metadata: dict[str, Any]
    license_evidence: list[dict[str, Any]]


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotImportError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_loads(text: str, *, label: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_json_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                SnapshotImportError(f"non-finite JSON number in {label}: {value}")
            ),
        )
    except SnapshotImportError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise SnapshotImportError(f"invalid JSON in {label}: {exc}") from exc


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotImportError(f"{label} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_scalar(value: Any, label: str) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise SnapshotImportError(f"{label} contains a non-finite number")
    return value


def _source_file_id(sha256: str) -> str:
    return f"source-file:{sha256.removeprefix('sha256:')}"


def _normalize_filename(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _revision_object(
    value: str | None, *, kind: str | None, scope: str
) -> dict[str, Any] | None:
    if value is None:
        return None
    normalized = _promotable_revision(value)
    return {
        "scope": scope,
        "kind": kind or "unknown",
        "value": normalized or value,
        "immutable": normalized is not None,
    }


def _classify_payload_name(name: str) -> str:
    lowered = name.lower()
    suffixes = Path(lowered).suffixes
    suffix = suffixes[-1] if suffixes else ""
    if suffix in {
        ".aac",
        ".avi",
        ".flac",
        ".gif",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".ogg",
        ".opus",
        ".png",
        ".wav",
        ".webm",
        ".webp",
    }:
        return "media"
    if suffix in {
        ".7z",
        ".bz2",
        ".gz",
        ".rar",
        ".tar",
        ".tgz",
        ".xz",
        ".zip",
    }:
        return "archive"
    if suffix in {".npy", ".npz"} or "embedding" in lowered:
        return "embedding"
    if suffix in {
        ".bin",
        ".ckpt",
        ".h5",
        ".joblib",
        ".onnx",
        ".pickle",
        ".pkl",
        ".pt",
        ".pth",
        ".safetensors",
    }:
        return "model"
    if suffix in _SUPPORTED_FORMATS:
        return "metadata"
    return "other"


def _binary_signature(data: bytes) -> str | None:
    signatures = (
        (b"\x89PNG\r\n\x1a\n", "PNG image"),
        (b"\xff\xd8\xff", "JPEG image"),
        (b"GIF87a", "GIF image"),
        (b"GIF89a", "GIF image"),
        (b"RIFF", "RIFF media"),
        (b"OggS", "Ogg media"),
        (b"fLaC", "FLAC audio"),
        (b"ID3", "MP3 audio"),
        (b"\x1aE\xdf\xa3", "Matroska/WebM media"),
        (b"PK\x03\x04", "ZIP/archive"),
        (b"\x1f\x8b", "gzip archive"),
        (b"7z\xbc\xaf'\x1c", "7z archive"),
        (b"\x93NUMPY", "NumPy embedding"),
    )
    for signature, label in signatures:
        if data.startswith(signature):
            return label
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "ISO base media"
    if data.startswith(b"PAR1"):
        return None
    return None


def _field_suggests_binary(field_name: str | None) -> bool:
    if not field_name:
        return False
    tokens = set(re.split(r"[^a-z0-9]+", field_name.lower()))
    return bool(tokens & _BINARY_FIELD_TOKENS)


def _decode_base64_prefix(text: str) -> bytes | None:
    compact = "".join(text.split())
    if len(compact) < 16 or len(compact) % 4 != 0 or not _BASE64_RE.fullmatch(compact):
        return None
    try:
        return base64.b64decode(compact[: min(len(compact), 256)], validate=True)
    except (ValueError, binascii.Error):
        return None


def _detect_embedded_payload(
    value: Any, *, field_name: str | None = None, location: str = "$"
) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _detect_embedded_payload(
                item, field_name=str(key), location=f"{location}.{key}"
            )
        return
    if isinstance(value, (list, tuple)):
        if (
            len(value) >= 8
            and all(isinstance(item, int) and 0 <= item <= 255 for item in value[:32])
        ):
            prefix = bytes(value[:32])
            signature = _binary_signature(prefix)
            if signature or (_field_suggests_binary(field_name) and len(value) >= 256):
                raise SnapshotImportError(
                    f"likely embedded media/binary bytes at {location}"
                )
        for index, item in enumerate(value):
            _detect_embedded_payload(
                item, field_name=field_name, location=f"{location}[{index}]"
            )
        return
    if isinstance(value, (bytes, bytearray, memoryview)):
        payload = bytes(value)
        if payload:
            raise SnapshotImportError(
                f"likely embedded media/binary bytes at {location}"
            )
        return
    if not isinstance(value, str):
        _safe_scalar(value, location)
        return
    stripped = value.strip()
    if _DATA_URI_RE.match(stripped):
        raise SnapshotImportError(f"embedded media data URI at {location}")
    decoded = _decode_base64_prefix(stripped)
    if decoded is not None and (
        _binary_signature(decoded)
        or (_field_suggests_binary(field_name) and len(stripped) >= 512)
    ):
        raise SnapshotImportError(
            f"likely base64-embedded media/binary bytes at {location}"
        )


def _parse_csv(data: bytes, label: str) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SnapshotImportError(f"{label} is not UTF-8 CSV") from exc
    try:
        reader = csv.reader(io.StringIO(text), strict=True)
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise SnapshotImportError(f"{label} has no valid CSV header") from exc
    if not header or any(not item.strip() for item in header):
        raise SnapshotImportError(f"{label} contains an empty CSV header")
    if len(set(header)) != len(header):
        raise SnapshotImportError(f"{label} contains duplicate CSV headers")
    rows: list[dict[str, Any]] = []
    try:
        for line_number, values in enumerate(reader, start=2):
            if len(values) != len(header):
                raise SnapshotImportError(
                    f"{label}:{line_number} has {len(values)} columns; "
                    f"expected {len(header)}"
                )
            row = dict(zip(header, values, strict=True))
            row["__source_line__"] = line_number
            rows.append(row)
    except csv.Error as exc:
        raise SnapshotImportError(f"invalid CSV in {label}: {exc}") from exc
    return rows


def _parse_parquet(data: bytes, label: str) -> list[dict[str, Any]]:
    try:
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.parquet as pq  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SnapshotImportError(
            "Parquet input requires an already-installed PyArrow; "
            "the importer will not install or fetch it"
        ) from exc
    try:
        table = pq.read_table(pa.BufferReader(data))
    except Exception as exc:
        raise SnapshotImportError(f"invalid Parquet metadata file {label}: {exc}") from exc
    rows = table.to_pylist()
    if not all(isinstance(row, dict) for row in rows):
        raise SnapshotImportError(f"Parquet rows in {label} must be objects")
    for index, row in enumerate(rows, start=1):
        row["__source_line__"] = index
    return rows


def _load_input(spec: SnapshotInput, max_file_bytes: int) -> _LoadedInput:
    raw_path = str(spec.path)
    parsed_url = urlparse(raw_path)
    if parsed_url.scheme or raw_path.startswith("//"):
        raise SnapshotImportError(
            f"only local filesystem paths are accepted; URL rejected: {raw_path!r}"
        )
    path = Path(raw_path)
    if path.is_symlink():
        raise SnapshotImportError(f"symbolic-link inputs are not accepted: {path}")
    if not path.is_file():
        raise SnapshotImportError(f"input is not a regular local file: {path}")
    suffix = path.suffix.lower()
    payload_class = _classify_payload_name(path.name)
    if suffix in _DISALLOWED_SUFFIXES or payload_class in {
        "media",
        "archive",
        "embedding",
        "model",
    }:
        raise SnapshotImportError(
            f"refusing {payload_class} payload input: {path.name}"
        )
    if suffix not in _SUPPORTED_FORMATS:
        raise SnapshotImportError(
            f"unsupported metadata input extension {suffix or '<none>'}: {path.name}"
        )
    size = path.stat().st_size
    if size > max_file_bytes:
        raise SnapshotImportError(
            f"input exceeds configured cap of {max_file_bytes} bytes: "
            f"{path.name} ({size} bytes)"
        )
    data = path.read_bytes()
    if len(data) != size:
        raise SnapshotImportError(f"input changed while being read: {path}")
    if len(data) > max_file_bytes:
        raise SnapshotImportError(
            f"input exceeds configured cap of {max_file_bytes} bytes after read: "
            f"{path.name} ({len(data)} bytes)"
        )
    signature = _binary_signature(data[:64])
    if signature is not None:
        raise SnapshotImportError(
            f"refusing non-metadata payload in {path.name}: {signature}"
        )
    sha256 = "sha256:" + hashlib.sha256(data).hexdigest()
    if suffix == ".json":
        try:
            parsed = _json_loads(data.decode("utf-8-sig"), label=path.name)
        except UnicodeDecodeError as exc:
            raise SnapshotImportError(f"{path.name} is not UTF-8 JSON") from exc
    elif suffix == ".jsonl":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SnapshotImportError(f"{path.name} is not UTF-8 JSONL") from exc
        parsed = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            row = _json_loads(line, label=f"{path.name}:{line_number}")
            if not isinstance(row, dict):
                raise SnapshotImportError(
                    f"{path.name}:{line_number} JSONL row must be an object"
                )
            row["__source_line__"] = line_number
            parsed.append(row)
    elif suffix == ".csv":
        parsed = _parse_csv(data, path.name)
    else:
        parsed = _parse_parquet(data, path.name)
    _detect_embedded_payload(parsed)
    return _LoadedInput(
        spec=spec,
        path=path,
        local_name=path.name,
        byte_size=size,
        sha256=sha256,
        suffix=suffix,
        data=data,
        parsed=parsed,
    )


def _github_repository_id(value: Mapping[str, Any]) -> str | None:
    for candidate in (
        value.get("url"),
        value.get("html_url"),
        (value.get("commit") or {}).get("url")
        if isinstance(value.get("commit"), Mapping)
        else None,
    ):
        if isinstance(candidate, str):
            match = _GITHUB_REPOSITORY_URL_RE.search(candidate)
            if match:
                return match.group(1)
    return None


def _hf_license_evidence(payload: Mapping[str, Any], revision: str) -> list[dict[str, Any]]:
    card = payload.get("cardData")
    if not isinstance(card, Mapping):
        return []
    license_value = card.get("license")
    if license_value is None:
        return []
    values = license_value if isinstance(license_value, list) else [license_value]
    return [
        {
            "evidence_type": "repository_metadata",
            "artifact_scope": "dataset_release",
            "value": str(value),
            "observed_revision": revision,
            "rights_inference": False,
        }
        for value in values
        if value is not None and str(value).strip()
    ]


def _hf_context(loaded: _LoadedInput) -> _RepositoryContext | None:
    value = loaded.parsed
    if not isinstance(value, Mapping):
        return None
    repository_id = value.get("id")
    revision = value.get("sha")
    siblings = value.get("siblings")
    if not (
        isinstance(repository_id, str)
        and isinstance(revision, str)
        and isinstance(siblings, list)
    ):
        return None
    inventory: list[dict[str, Any]] = []
    for index, item in enumerate(siblings):
        if not isinstance(item, Mapping):
            raise SnapshotImportError(
                f"{loaded.local_name}: siblings[{index}] must be an object"
            )
        repository_path = _text(item.get("rfilename"), "HF sibling rfilename")
        size = item.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise SnapshotImportError(
                f"{loaded.local_name}: invalid size for {repository_path}"
            )
        lfs = item.get("lfs") if isinstance(item.get("lfs"), Mapping) else {}
        file_revision = _optional_text(lfs.get("sha256"))
        if file_revision and not file_revision.startswith("sha256:"):
            file_revision = "sha256:" + file_revision.lower()
        inventory.append(
            {
                "repository_path": repository_path,
                "byte_size": size,
                "payload_class": _classify_payload_name(repository_path),
                "blob_revision": _optional_text(item.get("blobId")),
                "file_revision": file_revision,
                "file_revision_kind": "sha256" if file_revision else None,
            }
        )
    return _RepositoryContext(
        provider="huggingface",
        repository_id=repository_id,
        repository_revision=revision,
        repository_revision_kind="git_commit",
        source_file_ids=[_source_file_id(loaded.sha256)],
        file_inventory=inventory,
        metadata={
            "private": value.get("private"),
            "gated": value.get("gated"),
            "disabled": value.get("disabled"),
            "tags": list(value.get("tags") or []),
            "card_data": dict(value.get("cardData") or {}),
        },
        license_evidence=_hf_license_evidence(value, revision),
    )


def _github_context(loaded: _LoadedInput) -> _RepositoryContext | None:
    value = loaded.parsed
    if not isinstance(value, Mapping):
        return None
    repository_id = _github_repository_id(value)
    revision = value.get("sha")
    if not repository_id or not isinstance(revision, str):
        return None
    inventory: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    if isinstance(value.get("tree"), list):
        metadata["api_object"] = "tree"
        metadata["truncated"] = value.get("truncated")
        for index, item in enumerate(value["tree"]):
            if not isinstance(item, Mapping):
                raise SnapshotImportError(
                    f"{loaded.local_name}: tree[{index}] must be an object"
                )
            repository_path = _text(item.get("path"), "GitHub tree path")
            size = item.get("size")
            if size is not None and (
                isinstance(size, bool) or not isinstance(size, int) or size < 0
            ):
                raise SnapshotImportError(
                    f"{loaded.local_name}: invalid size for {repository_path}"
                )
            inventory.append(
                {
                    "repository_path": repository_path,
                    "byte_size": size,
                    "payload_class": _classify_payload_name(repository_path),
                    "blob_revision": (
                        _optional_text(item.get("sha"))
                        if item.get("type") == "blob"
                        else None
                    ),
                    "object_revision": _optional_text(item.get("sha")),
                    "object_type": _optional_text(item.get("type")),
                    "file_revision": None,
                    "file_revision_kind": None,
                }
            )
    elif isinstance(value.get("commit"), Mapping):
        metadata["api_object"] = "commit"
        tree = value["commit"].get("tree")
        if isinstance(tree, Mapping):
            metadata["tree_revision"] = tree.get("sha")
        for item in value.get("files") or []:
            if not isinstance(item, Mapping):
                continue
            repository_path = _text(item.get("filename"), "GitHub commit filename")
            inventory.append(
                {
                    "repository_path": repository_path,
                    "byte_size": None,
                    "payload_class": _classify_payload_name(repository_path),
                    "blob_revision": _optional_text(item.get("sha")),
                    "file_revision": None,
                    "file_revision_kind": None,
                }
            )
    else:
        return None
    return _RepositoryContext(
        provider="github",
        repository_id=repository_id,
        repository_revision=revision,
        repository_revision_kind="git_commit",
        source_file_ids=[_source_file_id(loaded.sha256)],
        file_inventory=inventory,
        metadata=metadata,
        license_evidence=[],
    )


def _merge_contexts(contexts: Iterable[_RepositoryContext]) -> list[_RepositoryContext]:
    merged: dict[tuple[str, str, str], _RepositoryContext] = {}
    for context in contexts:
        key = (
            context.provider,
            context.repository_id,
            context.repository_revision,
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = context
            continue
        existing.source_file_ids.extend(context.source_file_ids)
        known = {
            (
                item.get("repository_path"),
                item.get("blob_revision"),
                item.get("file_revision"),
            )
            for item in existing.file_inventory
        }
        for item in context.file_inventory:
            identity = (
                item.get("repository_path"),
                item.get("blob_revision"),
                item.get("file_revision"),
            )
            if identity not in known:
                existing.file_inventory.append(item)
                known.add(identity)
        existing.metadata.update(context.metadata)
        for evidence in context.license_evidence:
            if evidence not in existing.license_evidence:
                existing.license_evidence.append(evidence)
    return sorted(
        merged.values(),
        key=lambda item: (
            item.provider,
            item.repository_id,
            item.repository_revision,
        ),
    )


def _context_for_input(
    loaded: _LoadedInput, contexts: Sequence[_RepositoryContext]
) -> tuple[_RepositoryContext | None, dict[str, Any] | None]:
    spec = loaded.spec
    if spec.repository_id:
        matches = [
            item
            for item in contexts
            if item.repository_id == spec.repository_id
            and (not spec.provider or item.provider == spec.provider)
        ]
        if spec.repository_revision:
            matches = [
                item
                for item in matches
                if item.repository_revision == spec.repository_revision
            ]
        if len(matches) > 1:
            raise SnapshotImportError(
                f"ambiguous repository context for {loaded.local_name}"
            )
        context = matches[0] if matches else None
    else:
        inventory_matches: list[tuple[_RepositoryContext, dict[str, Any]]] = []
        normalized_name = _normalize_filename(loaded.local_name)
        for context in contexts:
            for item in context.file_inventory:
                size = item.get("byte_size")
                if size is not None and size != loaded.byte_size:
                    continue
                repository_path = str(item.get("repository_path") or "")
                normalized_path = _normalize_filename(repository_path)
                normalized_base = _normalize_filename(Path(repository_path).name)
                if (
                    (normalized_base and normalized_base in normalized_name)
                    or (normalized_path and normalized_path in normalized_name)
                ):
                    inventory_matches.append((context, item))
        if not inventory_matches:
            # Captured filenames commonly inject provider/repository/revision
            # labels before the suffix, so exact basenames do not survive.
            # An exact byte-size match is accepted only when globally unique.
            for context in contexts:
                for item in context.file_inventory:
                    if (
                        item.get("byte_size") == loaded.byte_size
                        and item.get("payload_class") == "metadata"
                    ):
                        inventory_matches.append((context, item))
        unique = {
            (
                item[0].provider,
                item[0].repository_id,
                item[0].repository_revision,
                item[1].get("repository_path"),
            ): item
            for item in inventory_matches
        }
        if len(unique) == 1:
            context, inventory_item = next(iter(unique.values()))
            return context, inventory_item

        prefix_matches = []
        for context in contexts:
            normalized_repository = _normalize_filename(context.repository_id)
            if normalized_repository and normalized_repository in normalized_name:
                prefix_matches.append(context)
        if len(prefix_matches) == 1:
            context = prefix_matches[0]
        else:
            context = None

    if context is None:
        return None, None
    if spec.repository_path:
        matches = [
            item
            for item in context.file_inventory
            if item.get("repository_path") == spec.repository_path
        ]
        if len(matches) > 1:
            raise SnapshotImportError(
                f"duplicate inventory path {spec.repository_path!r}"
            )
        return context, matches[0] if matches else None
    matches = [
        item
        for item in context.file_inventory
        if item.get("byte_size") in (None, loaded.byte_size)
        and _normalize_filename(Path(str(item.get("repository_path"))).name)
        in _normalize_filename(loaded.local_name)
    ]
    return context, matches[0] if len(matches) == 1 else None


def _records_from_hf_api(
    loaded: _LoadedInput, source_file_id: str
) -> list[dict[str, Any]]:
    payload = loaded.parsed
    assert isinstance(payload, Mapping)
    repository_id = _text(payload.get("id"), "HF repository id")
    records: list[dict[str, Any]] = [
        {
            "record_id": f"huggingface:{repository_id}:repository",
            "source_family": "huggingface_dataset_api",
            "record_type": "repository_snapshot",
            "source": {"source_file_id": source_file_id, "row": None},
            "identity": {
                "status": "resolved",
                "namespace": "huggingface_dataset",
                "asset_id": repository_id,
                "local_id": repository_id,
            },
            "media": _unknown_media(),
            "license": _unknown_license(),
            "fields": {
                "private": payload.get("private"),
                "gated": payload.get("gated"),
                "disabled": payload.get("disabled"),
                "tags": list(payload.get("tags") or []),
                "used_storage": payload.get("usedStorage"),
            },
        }
    ]
    card = payload.get("cardData")
    if isinstance(card, Mapping):
        dataset_info = card.get("dataset_info")
        infos = dataset_info if isinstance(dataset_info, list) else [dataset_info]
        for info_index, info in enumerate(infos):
            if not isinstance(info, Mapping):
                continue
            features = info.get("features") or []
            splits = info.get("splits") or []
            records.append(
                {
                    "record_id": (
                        f"huggingface:{repository_id}:schema:"
                        f"{info.get('config_name') or info_index}"
                    ),
                    "source_family": _repository_family(repository_id),
                    "record_type": "dataset_schema",
                    "source": {"source_file_id": source_file_id, "row": None},
                    "identity": _unknown_identity(
                        str(info.get("config_name") or "default")
                    ),
                    "media": _unknown_media(
                        declared_modalities=[
                            tag.split(":", 1)[1]
                            for tag in payload.get("tags") or []
                            if isinstance(tag, str) and tag.startswith("modality:")
                        ]
                    ),
                    "license": _unknown_license(),
                    "fields": {
                        "config_name": info.get("config_name"),
                        "features": features,
                        "splits": splits,
                        "download_size": info.get("download_size"),
                        "dataset_size": info.get("dataset_size"),
                    },
                }
            )
    return records


def _records_from_github_api(
    loaded: _LoadedInput, source_file_id: str
) -> list[dict[str, Any]]:
    payload = loaded.parsed
    assert isinstance(payload, Mapping)
    repository_id = _github_repository_id(payload)
    if not repository_id:
        raise SnapshotImportError(
            f"{loaded.local_name}: cannot recover GitHub repository identity"
        )
    if isinstance(payload.get("tree"), list):
        return [
            {
                "record_id": f"github:{repository_id}:tree:{payload.get('sha')}",
                "source_family": "github_tree_api",
                "record_type": "repository_tree",
                "source": {"source_file_id": source_file_id, "row": None},
                "identity": {
                    "status": "resolved",
                    "namespace": "github_repository",
                    "asset_id": repository_id,
                    "local_id": str(payload.get("sha")),
                },
                "media": _unknown_media(),
                "license": _unknown_license(),
                "fields": {
                    "tree_revision": payload.get("sha"),
                    "entry_count": len(payload["tree"]),
                    "truncated": payload.get("truncated"),
                },
            }
        ]
    return [
        {
            "record_id": f"github:{repository_id}:commit:{payload.get('sha')}",
            "source_family": "github_commit_api",
            "record_type": "repository_commit",
            "source": {"source_file_id": source_file_id, "row": None},
            "identity": {
                "status": "resolved",
                "namespace": "github_repository",
                "asset_id": repository_id,
                "local_id": str(payload.get("sha")),
            },
            "media": _unknown_media(),
            "license": _unknown_license(),
            "fields": {
                "commit_revision": payload.get("sha"),
                "tree_revision": (
                    payload.get("commit", {}).get("tree", {}).get("sha")
                    if isinstance(payload.get("commit"), Mapping)
                    else None
                ),
                "parent_revisions": [
                    item.get("sha")
                    for item in payload.get("parents") or []
                    if isinstance(item, Mapping)
                ],
            },
        }
    ]


def _unknown_identity(local_id: str | None) -> dict[str, Any]:
    return {
        "status": "unknown",
        "namespace": None,
        "asset_id": None,
        "local_id": local_id,
    }


def _unknown_media(
    *, declared_modalities: Sequence[str] | None = None
) -> dict[str, Any]:
    return {
        "video": None,
        "audio": None,
        "speech": None,
        "ambient_audio": None,
        "declared_modalities": list(declared_modalities or []),
    }


def _unknown_license() -> dict[str, Any]:
    return {
        "state": "unknown",
        "evidence_ids": [],
        "rights_inferred": False,
    }


def _repository_family(repository_id: str | None) -> str:
    normalized = (repository_id or "").lower()
    if "longvideobench-meta" in normalized:
        return "longvideobench_meta"
    if "video-mme" in normalized:
        return "video_mme"
    if "longvidsearch" in normalized:
        return "longvidsearch"
    if "traceav" in normalized:
        return "traceav"
    if "flare_demo" in normalized:
        return "flare_demo"
    if "flare" in normalized:
        return "flare"
    if "longshot" in normalized:
        return "longshot"
    return "generic_metadata"


def _detect_family(
    loaded: _LoadedInput, repository_id: str | None, rows: Sequence[Mapping[str, Any]]
) -> str:
    if loaded.spec.source_family and loaded.spec.source_family != "auto":
        aliases = {
            "longvideobench-meta": "longvideobench_meta",
            "longvideobench": "longvideobench_meta",
            "video-mme": "video_mme",
            "videomme": "video_mme",
            "longvidsearch_qa": "longvidsearch",
            "traceav_mapping": "traceav",
            "traceav_task": "traceav",
            "flare_demo_query": "flare_demo",
            "flare_demo_caption": "flare_demo",
            "longshot_annotation": "longshot",
        }
        return aliases.get(loaded.spec.source_family, loaded.spec.source_family)
    family = _repository_family(repository_id)
    if family != "generic_metadata":
        if family == "flare" and "demo" in loaded.local_name.lower():
            return "flare_demo"
        return family
    keys = set(rows[0]) if rows else set()
    if {"video_path", "unified_caption"} <= keys or {
        "video_id",
        "video_level_caption",
    } <= keys:
        return "flare_demo"
    if {"video_id", "source", "id"} <= keys or {
        "task_type",
        "question_id",
        "video_id",
        "trajectory_with_timestamps",
    } <= keys:
        return "traceav"
    if {"question", "answer", "evidence_slices"} <= keys:
        return "longvidsearch"
    if {"sample_id", "sample_type", "conversations"} <= keys:
        return "longshot"
    if {"video_id", "video_path", "subtitle_path", "question"} <= keys:
        return "longvideobench_meta"
    if {"video_id", "question_id", "task_type", "options"} <= keys:
        return "video_mme"
    return "generic_metadata"


def _row_list(parsed: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, Mapping):
        if isinstance(parsed.get("rows"), list):
            rows = parsed["rows"]
        elif isinstance(parsed.get("data"), list):
            rows = parsed["data"]
        else:
            rows = [parsed]
    else:
        raise SnapshotImportError(f"{label} metadata root must be an object or array")
    if not all(isinstance(row, dict) for row in rows):
        raise SnapshotImportError(f"{label} metadata rows must be objects")
    return [dict(row) for row in rows]


def _require_keys(row: Mapping[str, Any], keys: Sequence[str], label: str) -> None:
    missing = [key for key in keys if key not in row or row[key] is None]
    if missing:
        raise SnapshotImportError(f"{label} missing required fields: {', '.join(missing)}")


def _line(row: Mapping[str, Any], index: int) -> int:
    value = row.get("__source_line__", index + 1)
    return value if isinstance(value, int) else index + 1


def _clean_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "__source_line__"}


def _stable_fragment(value: Any, length: int = 16) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()[:length]


def _base_record(
    *,
    record_id: str,
    family: str,
    record_type: str,
    source_file_id: str,
    line: int,
    local_id: str | None,
    identity: dict[str, Any] | None = None,
    declared_modalities: Sequence[str] | None = None,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "source_family": family,
        "record_type": record_type,
        "source": {"source_file_id": source_file_id, "row": line},
        "identity": identity or _unknown_identity(local_id),
        "media": _unknown_media(declared_modalities=declared_modalities),
        "license": _unknown_license(),
        "fields": dict(fields),
    }


def _parse_longvidsearch(
    rows: Sequence[Mapping[str, Any]], source_file_id: str, loaded: _LoadedInput
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    filename_video = re.search(r"LongVidSearch_(.+?)_qa_", loaded.local_name)
    fallback_video = filename_video.group(1) if filename_video else None
    seen_explicit: set[str] = set()
    for index, row in enumerate(rows):
        _require_keys(
            row,
            ("question", "answer", "category", "hop_level", "evidence_slices"),
            f"{loaded.local_name}:{_line(row, index)} LongVidSearch row",
        )
        if not isinstance(row["evidence_slices"], list) or not all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in row["evidence_slices"]
        ):
            raise SnapshotImportError(
                f"{loaded.local_name}:{_line(row, index)} evidence_slices "
                "must be an array of integers"
            )
        video_id = _optional_text(row.get("vid")) or fallback_video
        if not video_id:
            raise SnapshotImportError(
                f"{loaded.local_name}:{_line(row, index)} LongVidSearch video ID "
                "is absent from both row and pinned filename"
            )
        explicit_id = _optional_text(row.get("question_id") or row.get("id"))
        if explicit_id:
            scoped = f"{video_id}:{explicit_id}"
            if scoped in seen_explicit:
                raise SnapshotImportError(f"duplicate ID in LongVidSearch rows: {scoped}")
            seen_explicit.add(scoped)
            qa_id = explicit_id
        else:
            qa_id = f"row-{index + 1}-{_stable_fragment(_clean_fields(row))}"
        record_id = f"longvidsearch:qa:{video_id}:{qa_id}"
        records.append(
            _base_record(
                record_id=record_id,
                family="longvidsearch",
                record_type="qa_annotation",
                source_file_id=source_file_id,
                line=_line(row, index),
                local_id=qa_id,
                identity={
                    "status": "resolved",
                    "namespace": "longvidsearch_qa",
                    "asset_id": f"{video_id}:{qa_id}",
                    "local_id": qa_id,
                },
                declared_modalities=[],
                fields=_clean_fields(row),
            )
        )
        joins.append(
            {
                "from_record_id": record_id,
                "relation": "annotates",
                "to_identity": {
                    "namespace": "longvideobench",
                    "asset_id": video_id,
                },
                "resolution_status": "resolved",
                "basis": "explicit LongVidSearch video identifier",
            }
        )
    return records, joins


def _parse_traceav(
    rows: Sequence[Mapping[str, Any]], source_file_id: str, loaded: _LoadedInput
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        line = _line(row, index)
        if {"video_id", "source", "id"} <= set(row):
            _require_keys(row, ("video_id", "source", "id"), f"{loaded.local_name}:{line}")
            video_id = _text(row["video_id"], "TraceAV video_id")
            if video_id in seen:
                raise SnapshotImportError(f"duplicate TraceAV mapping ID: {video_id}")
            seen.add(video_id)
            upstream_source = _text(row["source"], "TraceAV source")
            upstream_id = _text(row["id"], "TraceAV upstream id")
            record_id = f"traceav:mapping:{video_id}"
            records.append(
                _base_record(
                    record_id=record_id,
                    family="traceav",
                    record_type="source_mapping",
                    source_file_id=source_file_id,
                    line=line,
                    local_id=video_id,
                    identity={
                        "status": "resolved",
                        "namespace": "traceav",
                        "asset_id": video_id,
                        "local_id": video_id,
                    },
                    fields=_clean_fields(row),
                )
            )
            joins.append(
                {
                    "from_record_id": record_id,
                    "relation": "mapped_from",
                    "to_identity": {
                        "namespace": upstream_source,
                        "asset_id": upstream_id,
                    },
                    "resolution_status": "resolved",
                    "basis": "explicit TraceAV mapping row",
                }
            )
            continue
        _require_keys(
            row,
            ("task_type", "question_id", "video_id", "question"),
            f"{loaded.local_name}:{line} TraceAV task row",
        )
        task_type = _text(row["task_type"], "TraceAV task_type")
        video_id = _text(row["video_id"], "TraceAV video_id")
        question_id = _text(str(row["question_id"]), "TraceAV question_id")
        identity = f"{task_type}:{question_id}"
        if identity in seen:
            raise SnapshotImportError(f"duplicate TraceAV task ID: {identity}")
        seen.add(identity)
        for encoded_field in ("options", "correct_options", "trajectory_with_timestamps"):
            value = row.get(encoded_field)
            if isinstance(value, str):
                decoded = _json_loads(
                    value, label=f"{loaded.local_name}:{line}:{encoded_field}"
                )
                if encoded_field == "trajectory_with_timestamps" and not isinstance(
                    decoded, list
                ):
                    raise SnapshotImportError(
                        f"{loaded.local_name}:{line} {encoded_field} must encode an array"
                    )
        record_id = f"traceav:task:{task_type}:{question_id}"
        task_modalities: list[str] = []
        lowered = task_type.lower()
        if lowered.startswith("a_"):
            task_modalities.append("audio")
        elif lowered.startswith("v_"):
            task_modalities.append("video")
        elif lowered.startswith("av_") or lowered.startswith("mh_"):
            task_modalities.extend(("audio", "video"))
        records.append(
            _base_record(
                record_id=record_id,
                family="traceav",
                record_type="task_annotation",
                source_file_id=source_file_id,
                line=line,
                local_id=question_id,
                identity={
                    "status": "resolved",
                    "namespace": "traceav_task",
                    "asset_id": identity,
                    "local_id": question_id,
                },
                declared_modalities=task_modalities,
                fields=_clean_fields(row),
            )
        )
        joins.append(
            {
                "from_record_id": record_id,
                "relation": "annotates",
                "to_identity": {"namespace": "traceav", "asset_id": video_id},
                "resolution_status": "resolved",
                "basis": "explicit TraceAV task video_id",
            }
        )
    return records, joins


def _parse_flare(
    rows: Sequence[Mapping[str, Any]], source_file_id: str, loaded: _LoadedInput
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        line = _line(row, index)
        if "video_path" in row:
            _require_keys(row, ("video_path",), f"{loaded.local_name}:{line}")
            path = _text(row["video_path"], "FLARE video_path")
            caption_keys = [
                key
                for key in ("unified_caption", "audio_caption", "vision_caption")
                if row.get(key) is not None
            ]
            if not caption_keys:
                raise SnapshotImportError(
                    f"{loaded.local_name}:{line} FLARE clip row has no caption"
                )
            clip_id = Path(path).stem
            parent_id = path.split("/", 1)[0] if "/" in path else clip_id.split("-Scene-")[0]
            if clip_id in seen:
                raise SnapshotImportError(f"duplicate FLARE clip ID: {clip_id}")
            seen.add(clip_id)
            modalities = sorted(
                {
                    modality
                    for key in caption_keys
                    for modality in (
                        ("audio", "video") if key == "unified_caption" else
                        ("audio",) if key == "audio_caption" else ("video",)
                    )
                }
            )
            record_id = f"flare:clip:{clip_id}"
            records.append(
                _base_record(
                    record_id=record_id,
                    family="flare_demo",
                    record_type="clip_caption_or_query",
                    source_file_id=source_file_id,
                    line=line,
                    local_id=clip_id,
                    identity={
                        "status": "resolved",
                        "namespace": "flare_demo_clip",
                        "asset_id": clip_id,
                        "local_id": clip_id,
                    },
                    declared_modalities=modalities,
                    fields=_clean_fields(row),
                )
            )
            joins.append(
                {
                    "from_record_id": record_id,
                    "relation": "segment_of",
                    "to_identity": {
                        "namespace": "flare_demo_video",
                        "asset_id": parent_id,
                    },
                    "resolution_status": "resolved",
                    "basis": "explicit FLARE relative video_path",
                }
            )
            continue
        caption_key = next(
            (
                key
                for key in (
                    "video_level_caption",
                    "unified_caption",
                    "audio_caption",
                    "vision_caption",
                )
                if key in row
            ),
            None,
        )
        if "video_id" not in row or caption_key is None:
            raise SnapshotImportError(
                f"{loaded.local_name}:{line} malformed FLARE caption/query row"
            )
        video_id = _text(row["video_id"], "FLARE video_id")
        if video_id in seen:
            raise SnapshotImportError(f"duplicate FLARE video ID: {video_id}")
        seen.add(video_id)
        modalities = (
            ["audio", "video"]
            if "unified" in caption_key or caption_key == "video_level_caption"
            else ["audio"]
            if "audio" in caption_key
            else ["video"]
        )
        record_id = f"flare:video:{video_id}"
        records.append(
            _base_record(
                record_id=record_id,
                family="flare_demo",
                record_type="video_caption_or_query",
                source_file_id=source_file_id,
                line=line,
                local_id=video_id,
                identity={
                    "status": "resolved",
                    "namespace": "flare_demo_video",
                    "asset_id": video_id,
                    "local_id": video_id,
                },
                declared_modalities=modalities,
                fields=_clean_fields(row),
            )
        )
        joins.append(
            {
                "from_record_id": record_id,
                "relation": "references_source",
                "to_identity": {"namespace": "videomme", "asset_id": video_id},
                "resolution_status": "unresolved",
                "basis": (
                    "FLARE source identifier; object/rendition equivalence is not inferred"
                ),
            }
        )
    return records, joins


def _parse_longvideobench(
    rows: Sequence[Mapping[str, Any]], source_file_id: str, loaded: _LoadedInput
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        line = _line(row, index)
        _require_keys(
            row,
            ("video_id", "id", "video_path", "subtitle_path", "question", "duration"),
            f"{loaded.local_name}:{line} LongVideoBench-Meta row",
        )
        qa_id = _text(str(row["id"]), "LongVideoBench question id")
        if qa_id in seen:
            raise SnapshotImportError(f"duplicate LongVideoBench ID: {qa_id}")
        seen.add(qa_id)
        video_id = _text(row["video_id"], "LongVideoBench video_id")
        duration = row["duration"]
        if isinstance(duration, bool):
            raise SnapshotImportError("LongVideoBench duration must be numeric")
        try:
            numeric_duration = float(duration)
        except (TypeError, ValueError) as exc:
            raise SnapshotImportError("LongVideoBench duration must be numeric") from exc
        if not math.isfinite(numeric_duration) or numeric_duration <= 0:
            raise SnapshotImportError("LongVideoBench duration must be positive")
        record_id = f"longvideobench:qa:{qa_id}"
        records.append(
            _base_record(
                record_id=record_id,
                family="longvideobench_meta",
                record_type="qa_metadata",
                source_file_id=source_file_id,
                line=line,
                local_id=qa_id,
                identity={
                    "status": "resolved",
                    "namespace": "longvideobench_qa",
                    "asset_id": qa_id,
                    "local_id": qa_id,
                },
                fields=_clean_fields(row),
            )
        )
        joins.append(
            {
                "from_record_id": record_id,
                "relation": "annotates",
                "to_identity": {
                    "namespace": "longvideobench",
                    "asset_id": video_id,
                },
                "resolution_status": "resolved",
                "basis": "explicit LongVideoBench-Meta video_id",
            }
        )
    return records, joins


def _parse_videomme(
    rows: Sequence[Mapping[str, Any]], source_file_id: str, loaded: _LoadedInput
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        line = _line(row, index)
        _require_keys(
            row,
            ("video_id", "question_id", "question", "options", "answer"),
            f"{loaded.local_name}:{line} Video-MME row",
        )
        question_id = _text(str(row["question_id"]), "Video-MME question_id")
        if question_id in seen:
            raise SnapshotImportError(f"duplicate Video-MME question ID: {question_id}")
        seen.add(question_id)
        video_id = _text(row["video_id"], "Video-MME video_id")
        record_id = f"videomme:qa:{question_id}"
        records.append(
            _base_record(
                record_id=record_id,
                family="video_mme",
                record_type="qa_metadata",
                source_file_id=source_file_id,
                line=line,
                local_id=question_id,
                identity={
                    "status": "resolved",
                    "namespace": "videomme_qa",
                    "asset_id": question_id,
                    "local_id": question_id,
                },
                fields=_clean_fields(row),
            )
        )
        joins.append(
            {
                "from_record_id": record_id,
                "relation": "annotates",
                "to_identity": {"namespace": "videomme", "asset_id": video_id},
                "resolution_status": "resolved",
                "basis": "explicit Video-MME video_id",
            }
        )
    return records, joins


def _parse_longshot(
    rows: Sequence[Mapping[str, Any]], source_file_id: str, loaded: _LoadedInput
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        line = _line(row, index)
        _require_keys(
            row,
            ("video_id", "sample_id", "sample_type", "conversations"),
            f"{loaded.local_name}:{line} LongShOT row",
        )
        sample_id = _text(str(row["sample_id"]), "LongShOT sample_id")
        if sample_id in seen:
            raise SnapshotImportError(f"duplicate LongShOT sample ID: {sample_id}")
        seen.add(sample_id)
        conversations = row["conversations"]
        if not isinstance(conversations, list) or not all(
            isinstance(item, Mapping) for item in conversations
        ):
            raise SnapshotImportError(
                f"{loaded.local_name}:{line} conversations must be an array of objects"
            )
        modalities: list[str] = []
        for turn in conversations:
            values = turn.get("modalities")
            if isinstance(values, list):
                modalities.extend(str(item) for item in values)
        video_id = _text(row["video_id"], "LongShOT video_id")
        record_id = f"longshot:sample:{sample_id}"
        records.append(
            _base_record(
                record_id=record_id,
                family="longshot",
                record_type="annotation",
                source_file_id=source_file_id,
                line=line,
                local_id=sample_id,
                identity={
                    "status": "resolved",
                    "namespace": "longshot_sample",
                    "asset_id": sample_id,
                    "local_id": sample_id,
                },
                declared_modalities=sorted(set(modalities)),
                fields=_clean_fields(row),
            )
        )
        joins.append(
            {
                "from_record_id": record_id,
                "relation": "annotates",
                "to_identity": {"namespace": "longshot_video", "asset_id": video_id},
                "resolution_status": "resolved",
                "basis": "explicit LongShOT video_id",
            }
        )
    return records, joins


def _parse_generic(
    rows: Sequence[Mapping[str, Any]], source_file_id: str, loaded: _LoadedInput
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        line = _line(row, index)
        explicit = _optional_text(
            row.get("record_id")
            or row.get("sample_id")
            or row.get("question_id")
            or row.get("id")
        )
        if explicit:
            if explicit in seen_ids:
                raise SnapshotImportError(f"duplicate metadata ID: {explicit}")
            seen_ids.add(explicit)
            local_id = explicit
        else:
            local_id = f"row-{index + 1}-{_stable_fragment(_clean_fields(row))}"
        declared = row.get("modalities") or row.get("modality") or []
        if isinstance(declared, str):
            declared_modalities = [declared]
        elif isinstance(declared, list):
            declared_modalities = [str(item) for item in declared]
        else:
            declared_modalities = [str(declared)] if declared else []
        records.append(
            _base_record(
                record_id=f"generic:{source_file_id}:{local_id}",
                family="generic_metadata",
                record_type="metadata_row",
                source_file_id=source_file_id,
                line=line,
                local_id=local_id,
                declared_modalities=declared_modalities,
                fields=_clean_fields(row),
            )
        )
    return records, []


_ROW_PARSERS = {
    "longvidsearch": _parse_longvidsearch,
    "traceav": _parse_traceav,
    "flare": _parse_flare,
    "flare_demo": _parse_flare,
    "longvideobench_meta": _parse_longvideobench,
    "video_mme": _parse_videomme,
    "longshot": _parse_longshot,
    "generic_metadata": _parse_generic,
}


def _promotable_revision(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith("sha256:"):
        digest = value.removeprefix("sha256:")
        return digest.lower() if len(digest) == 64 and _FULL_HEX_RE.fullmatch(digest) else None
    return immutable_revision(value)


class SnapshotImporter:
    """Build deterministic inspection JSON from bounded local metadata files."""

    def __init__(self, *, max_file_bytes: int = DEFAULT_MAX_SOURCE_BYTES):
        if isinstance(max_file_bytes, bool) or max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be a positive integer")
        self.max_file_bytes = int(max_file_bytes)

    def build(
        self,
        inputs: Iterable[SnapshotInput | str | Path],
        *,
        promote: bool = True,
    ) -> dict[str, Any]:
        specs = [
            item if isinstance(item, SnapshotInput) else SnapshotInput(path=item)
            for item in inputs
        ]
        if not specs:
            raise SnapshotImportError("at least one local input is required")
        loaded_inputs = [_load_input(spec, self.max_file_bytes) for spec in specs]
        duplicate_hashes: dict[str, str] = {}
        for item in loaded_inputs:
            previous = duplicate_hashes.get(item.sha256)
            if previous is not None:
                raise SnapshotImportError(
                    f"duplicate source file content: {previous} and {item.local_name}"
                )
            duplicate_hashes[item.sha256] = item.local_name

        raw_contexts = [
            context
            for loaded in loaded_inputs
            for context in (_hf_context(loaded), _github_context(loaded))
            if context is not None
        ]
        contexts = _merge_contexts(raw_contexts)

        source_files: list[dict[str, Any]] = []
        records: list[dict[str, Any]] = []
        joins: list[dict[str, Any]] = []
        record_ids: set[str] = set()
        for loaded in loaded_inputs:
            source_file_id = _source_file_id(loaded.sha256)
            own_hf = _hf_context(loaded)
            own_github = _github_context(loaded)
            if own_hf is not None:
                context, inventory_item = own_hf, None
            elif own_github is not None:
                context, inventory_item = own_github, None
            else:
                context, inventory_item = _context_for_input(loaded, contexts)
            provider = (
                loaded.spec.provider
                or (context.provider if context else None)
                or ("huggingface" if own_hf else "github" if own_github else "unknown")
            )
            repository_id = (
                loaded.spec.repository_id
                or (context.repository_id if context else None)
            )
            repository_revision = (
                loaded.spec.repository_revision
                or (context.repository_revision if context else None)
            )
            repository_revision_kind = (
                loaded.spec.repository_revision_kind
                if loaded.spec.repository_revision
                else context.repository_revision_kind
                if context
                else loaded.spec.repository_revision_kind
            )
            repository_path = loaded.spec.repository_path or (
                inventory_item.get("repository_path") if inventory_item else None
            )
            file_revision = loaded.spec.file_revision or (
                inventory_item.get("file_revision") if inventory_item else None
            )
            file_revision_kind = loaded.spec.file_revision_kind or (
                inventory_item.get("file_revision_kind") if inventory_item else None
            )
            blob_revision = loaded.spec.blob_revision or (
                inventory_item.get("blob_revision") if inventory_item else None
            )
            if own_hf or own_github:
                detected_context = own_hf or own_github
                assert detected_context is not None
                if (
                    loaded.spec.provider
                    and loaded.spec.provider != detected_context.provider
                ):
                    raise SnapshotImportError(
                        f"{loaded.local_name}: provider override conflicts with "
                        "the API snapshot"
                    )
                if (
                    loaded.spec.repository_id
                    and loaded.spec.repository_id != detected_context.repository_id
                ):
                    raise SnapshotImportError(
                        f"{loaded.local_name}: repository override conflicts with "
                        "the API snapshot"
                    )
                if (
                    loaded.spec.repository_revision
                    and loaded.spec.repository_revision
                    != detected_context.repository_revision
                ):
                    raise SnapshotImportError(
                        f"{loaded.local_name}: repository revision override conflicts "
                        "with the API snapshot"
                    )
            if inventory_item is not None:
                expected_size = inventory_item.get("byte_size")
                if expected_size is not None and expected_size != loaded.byte_size:
                    raise SnapshotImportError(
                        f"{loaded.local_name}: local byte size {loaded.byte_size} "
                        f"does not match repository metadata {expected_size}"
                    )
                expected_file_revision = inventory_item.get("file_revision")
                if (
                    isinstance(expected_file_revision, str)
                    and expected_file_revision.startswith("sha256:")
                    and expected_file_revision.lower() != loaded.sha256.lower()
                ):
                    raise SnapshotImportError(
                        f"{loaded.local_name}: local SHA-256 does not match "
                        "repository file revision"
                    )
            promotion_errors: list[str] = []
            if repository_revision is None:
                promotion_errors.append("repository revision is unknown")
            elif _promotable_revision(repository_revision) is None:
                promotion_errors.append(
                    f"repository revision is mutable, short, or unsupported: "
                    f"{repository_revision!r}"
                )
            for label, revision in (
                ("file", file_revision),
                ("blob", blob_revision),
            ):
                if revision is not None and _promotable_revision(revision) is None:
                    promotion_errors.append(
                        f"{label} revision is mutable, short, or unsupported: "
                        f"{revision!r}"
                    )
            if promote and promotion_errors:
                raise SnapshotImportError(
                    f"{loaded.local_name} cannot be promoted: "
                    + "; ".join(promotion_errors)
                )

            source_files.append(
                {
                    "source_file_id": source_file_id,
                    "local_name": loaded.local_name,
                    "format": loaded.suffix.removeprefix("."),
                    "byte_size": loaded.byte_size,
                    "sha256": loaded.sha256,
                    "payload_class": "metadata",
                    "repository": {
                        "provider": provider,
                        "repository_id": repository_id,
                    },
                    "repository_path": repository_path,
                    "repository_revision": _revision_object(
                        repository_revision,
                        kind=repository_revision_kind,
                        scope="repository",
                    ),
                    "file_revision": _revision_object(
                        file_revision,
                        kind=file_revision_kind,
                        scope="file",
                    ),
                    "blob_revision": _revision_object(
                        blob_revision,
                        kind="git_blob",
                        scope="blob",
                    ),
                    "promotion": {
                        "eligible": not promotion_errors,
                        "errors": promotion_errors,
                    },
                }
            )

            if own_hf:
                new_records = _records_from_hf_api(loaded, source_file_id)
                new_joins: list[dict[str, Any]] = []
            elif own_github:
                new_records = _records_from_github_api(loaded, source_file_id)
                new_joins = []
            elif (
                isinstance(loaded.parsed, Mapping)
                and {"dataset_info", "pending", "failed", "partial"}
                <= set(loaded.parsed)
            ):
                family = _repository_family(repository_id)
                new_records = [
                    _base_record(
                        record_id=f"dataset-info:{source_file_id}",
                        family=family,
                        record_type="dataset_info",
                        source_file_id=source_file_id,
                        line=1,
                        local_id="dataset_info",
                        fields=dict(loaded.parsed),
                    )
                ]
                new_joins = []
            else:
                rows = _row_list(loaded.parsed, loaded.local_name)
                family = _detect_family(loaded, repository_id, rows)
                parser = _ROW_PARSERS.get(family)
                if parser is None:
                    raise SnapshotImportError(
                        f"unsupported source family {family!r} for {loaded.local_name}"
                    )
                new_records, new_joins = parser(rows, source_file_id, loaded)
            for record in new_records:
                record_id = record["record_id"]
                if record_id in record_ids:
                    raise SnapshotImportError(
                        f"duplicate normalized record ID: {record_id}"
                    )
                record_ids.add(record_id)
                records.append(record)
            joins.extend(new_joins)

        mapping_targets: dict[str, dict[str, Any]] = {}
        for join in joins:
            if (
                join["relation"] == "mapped_from"
                and join["from_record_id"].startswith("traceav:mapping:")
            ):
                trace_id = join["from_record_id"].removeprefix("traceav:mapping:")
                mapping_targets[trace_id] = join["to_identity"]
        for join in list(joins):
            target = join.get("to_identity") or {}
            if (
                join["relation"] == "annotates"
                and target.get("namespace") == "traceav"
                and target.get("asset_id") in mapping_targets
            ):
                joins.append(
                    {
                        "from_record_id": join["from_record_id"],
                        "relation": "annotates_mapped_source",
                        "to_identity": mapping_targets[target["asset_id"]],
                        "resolution_status": "resolved",
                        "basis": "joined through imported TraceAV mapping",
                    }
                )

        repositories = []
        evidence: list[dict[str, Any]] = []
        for context in contexts:
            evidence_ids = []
            for item in context.license_evidence:
                evidence_id = (
                    "license-evidence:"
                    + hashlib.sha256(canonical_json(item)).hexdigest()
                )
                evidence.append({"evidence_id": evidence_id, **item})
                evidence_ids.append(evidence_id)
            repositories.append(
                {
                    "provider": context.provider,
                    "repository_id": context.repository_id,
                    "repository_revision": _revision_object(
                        context.repository_revision,
                        kind=context.repository_revision_kind,
                        scope="repository",
                    ),
                    "source_file_ids": sorted(set(context.source_file_ids)),
                    "license_state": "observed" if evidence_ids else "unknown",
                    "license_evidence_ids": evidence_ids,
                    "media_rights_state": "unknown",
                    "identity_state": "resolved",
                    "file_inventory": sorted(
                        context.file_inventory,
                        key=lambda item: str(item.get("repository_path")),
                    ),
                    "metadata": context.metadata,
                }
            )

        source_files.sort(key=lambda item: (item["local_name"], item["sha256"]))
        records.sort(key=lambda item: item["record_id"])
        joins.sort(
            key=lambda item: (
                item["from_record_id"],
                item["relation"],
                str(item["to_identity"].get("namespace")),
                str(item["to_identity"].get("asset_id")),
            )
        )
        evidence.sort(key=lambda item: item["evidence_id"])
        artifact: dict[str, Any] = {
            "inspection_version": SNAPSHOT_INSPECTION_VERSION,
            "artifact_class": "metadata_reconnaissance_inspection",
            "promotion_status": "promoted" if promote else "unpromoted",
            "network_access_performed": False,
            "contains_media": False,
            "acquisition_authorization": "none",
            "rights_policy": (
                "License metadata is evidence only. No media or acquisition "
                "rights are inferred."
            ),
            "limits": {"max_source_file_bytes": self.max_file_bytes},
            "source_files": source_files,
            "repositories": repositories,
            "license_evidence": evidence,
            "records": records,
            "source_lineage_joins": joins,
            "summary": {
                "source_file_count": len(source_files),
                "repository_count": len(repositories),
                "record_count": len(records),
                "lineage_join_count": len(joins),
            },
        }
        artifact["inspection_sha256"] = (
            "sha256:" + hashlib.sha256(canonical_json(artifact)).hexdigest()
        )
        return artifact

    def build_to_path(
        self,
        inputs: Iterable[SnapshotInput | str | Path],
        output: str | Path,
        *,
        promote: bool = True,
    ) -> dict[str, Any]:
        artifact = self.build(inputs, promote=promote)
        write_json_atomic(output, artifact)
        return artifact


def build_snapshot_inspection(
    inputs: Iterable[SnapshotInput | str | Path],
    *,
    max_file_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
    promote: bool = True,
) -> dict[str, Any]:
    """Convenience wrapper for one deterministic offline import."""

    return SnapshotImporter(max_file_bytes=max_file_bytes).build(
        inputs, promote=promote
    )


__all__ = [
    "DEFAULT_MAX_SOURCE_BYTES",
    "SNAPSHOT_INSPECTION_VERSION",
    "SnapshotImporter",
    "SnapshotInput",
    "build_snapshot_inspection",
]
