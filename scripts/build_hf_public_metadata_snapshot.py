#!/usr/bin/env python3
"""Build a strict metadata-only Hugging Face release staging directory.

The input must be an already-audited public snapshot whose
``PUBLIC_SNAPSHOT_MANIFEST.json`` says ``READY`` and whose complete payload
matches ``SHA256SUMS``.  The default operation is a non-mutating dry run;
``--execute`` is required to create a new empty directory under ``/tmp``.

This tool performs no network access, authentication, token handling, or
upload.  It copies only the explicit allowlist below, maps the dataset card to
``README.md``, sanitizes the Hugging Face asset manifest to public metadata,
and creates fresh release integrity indexes.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


DEFAULT_SOURCE = Path("/tmp/av-trace-public")
DEFAULT_DESTINATION = Path("/tmp/av-trace-hf-public-metadata")
SOURCE_INDEX_FILES = frozenset({"PUBLIC_SNAPSHOT_MANIFEST.json", "SHA256SUMS"})
RELEASE_INDEX_FILES = frozenset({"HF_RELEASE_MANIFEST.json", "SHA256SUMS"})
RELEASE_CHECKSUM_EXCLUDES = frozenset({"SHA256SUMS"})

ALLOWLIST = (
    ("docs/migration/HF_DATASET_CARD.md", "README.md", "dataset card"),
    ("LICENSE", "LICENSE", "project license"),
    (
        "docs/migration/THIRD_PARTY_DATA_NOTICE.md",
        "THIRD_PARTY_DATA_NOTICE.md",
        "third-party data notice",
    ),
    (
        "docs/overview/authoritative_cvpr_state_2026-10-23.md",
        "metadata/authoritative_cvpr_state_2026-10-23.md",
        "authoritative research status",
    ),
    (
        "data/rehearsal_plan/post_migration_cvpr_work_queue.json",
        "metadata/post_migration_cvpr_work_queue.json",
        "post-migration work queue",
    ),
)
HF_ASSET_MANIFEST_SOURCE = "data/migration/hf_asset_manifest.json"
HF_ASSET_MANIFEST_DESTINATION = "metadata/hf_asset_manifest.json"
PUBLIC_MANIFEST_DESTINATION = "metadata/PUBLIC_SNAPSHOT_MANIFEST.json"
PUBLIC_CHECKSUM_DESTINATION = "metadata/PUBLIC_SNAPSHOT_SHA256SUMS"

CACHE_COMPONENTS = frozenset(
    {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".cache"}
)
CACHE_SUFFIXES = frozenset({".pyc", ".pyo"})
RESTRICTED_COMPONENTS = frozenset({"restricted"})
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bhf_[A-Za-z0-9]{15,}\b"),
    re.compile(
        r"""(?ix)
        ["']?
        (?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)
        ["']?
        \s*[:=]\s*
        ["']
        (?!PUBLIC_REDACTED|REDACTED|EXAMPLE|PLACEHOLDER|none\b|null\b)
        [^"'\r\n]{8,}
        ["']
        """
    ),
)
_PRIVATE_MOUNT = "/" + "jizhicfs" + "/"
_HOME_ROOTS = "/" + "(?:home|Users)" + "/"
ABSOLUTE_OLD_MACHINE_PATTERNS = (
    re.compile(
        r"(?<![A-Za-z0-9_.-])"
        + re.escape(_PRIVATE_MOUNT)
        + r"""[^\s"'`<>]+"""
    ),
    re.compile(
        r"(?<![A-Za-z0-9_.-])" + _HOME_ROOTS + r"""[^\s"'`<>]+"""
    ),
)
INTERNAL_DOMAIN_PATTERNS = (
    re.compile(r"(?i)\b(?:[A-Za-z0-9-]+\.)+(?:woa|oa)\.com\b"),
    re.compile(r"(?i)\b(?:star|hy)[-_.]proxy\b"),
)
PATH_VALUE_KEYS = frozenset(
    {
        "local_path",
        "local_members",
        "repository_root",
        "reconstruction_command",
        "dependencies",
        "hash_basis",
    }
)
SAFE_PUBLIC_ASSET_POLICIES = frozenset(
    {"public_metadata_only", "redownload_upstream", "rebuild_from_code"}
)


@dataclass(frozen=True)
class StagedFile:
    path: str
    source: str | None
    reason: str
    content: bytes
    mode: int = 0o644

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def size_bytes(self) -> int:
        return len(self.content)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _normalized_relative_path(value: str) -> str:
    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or ".." in pure.parts
        or value != pure.as_posix()
    ):
        raise ValueError(
            f"path must be normalized and snapshot-relative: {value!r}"
        )
    return value


def _path_policy_check(relative: str) -> None:
    pure = PurePosixPath(_normalized_relative_path(relative))
    lowered = {part.lower() for part in pure.parts}
    if lowered & RESTRICTED_COMPONENTS:
        raise ValueError(f"restricted path is forbidden: {relative}")
    if lowered & CACHE_COMPONENTS or pure.suffix.lower() in CACHE_SUFFIXES:
        raise ValueError(f"cache/bytecode path is forbidden: {relative}")


def _path_has_symlink_component(root: Path, relative: str) -> bool:
    current = root
    for component in PurePosixPath(relative).parts:
        current = current / component
        if current.is_symlink():
            return True
    return False


def _read_regular_file(root: Path, relative: str) -> tuple[bytes, int]:
    _path_policy_check(relative)
    if _path_has_symlink_component(root, relative):
        raise ValueError(f"refusing source symlink: {relative}")
    path = root.joinpath(*PurePosixPath(relative).parts)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as error:
        raise ValueError(f"required source file is missing: {relative}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"source is not a regular file: {relative}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), stat.S_IMODE(metadata.st_mode)
    finally:
        os.close(descriptor)


def _decode_utf8(path: str, content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"metadata must be UTF-8 text: {path}: {error}") from error


def _scan_forbidden_text(path: str, content: bytes) -> None:
    text = _decode_utf8(path, content)
    for pattern in ABSOLUTE_OLD_MACHINE_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"absolute old-machine path is forbidden in {path}")
    for pattern in INTERNAL_DOMAIN_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"internal domain is forbidden in {path}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"credential/secret material is forbidden in {path}")


def _parse_content(path: str, content: bytes) -> object | None:
    text = _decode_utf8(path, content)
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".py":
        try:
            ast.parse(text, filename=path)
        except SyntaxError as error:
            raise ValueError(f"Python parse failed for {path}: {error}") from error
    if suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"JSON parse failed for {path}: {error}") from error
    return None


def _parse_checksum_index(content: bytes) -> dict[str, str]:
    text = _decode_utf8("SHA256SUMS", content)
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        digest, separator, relative = line.partition("  ")
        if (
            not separator
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"invalid SHA256SUMS line {line_number}: {line!r}")
        _path_policy_check(relative)
        if relative in SOURCE_INDEX_FILES:
            raise ValueError(
                f"source index must not self-hash {relative!r} in SHA256SUMS"
            )
        if relative in checksums:
            raise ValueError(f"duplicate SHA256SUMS path: {relative}")
        checksums[relative] = digest
    if not checksums:
        raise ValueError("SHA256SUMS must contain at least one payload entry")
    return checksums


def _manifest_file_map(manifest: Mapping[str, object]) -> dict[str, dict[str, object]]:
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("PUBLIC_SNAPSHOT_MANIFEST.json files must be an array")
    result: dict[str, dict[str, object]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"public snapshot manifest file row {index} is invalid")
        relative = row.get("path")
        digest = row.get("sha256")
        size = row.get("size_bytes")
        if not isinstance(relative, str):
            raise ValueError(f"public snapshot manifest row {index} lacks path")
        _path_policy_check(relative)
        if relative in SOURCE_INDEX_FILES or relative in result:
            raise ValueError(
                f"duplicate or self-indexed public manifest path: {relative}"
            )
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"invalid public manifest sha256 for {relative}")
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"invalid public manifest size for {relative}")
        result[relative] = row
    return result


def audit_public_snapshot(source: Path) -> tuple[dict[str, object], dict[str, bytes]]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"source must be a non-symlink directory: {source}")

    manifest_bytes, _ = _read_regular_file(
        source, "PUBLIC_SNAPSHOT_MANIFEST.json"
    )
    checksum_bytes, _ = _read_regular_file(source, "SHA256SUMS")
    manifest_value = _parse_content(
        "PUBLIC_SNAPSHOT_MANIFEST.json", manifest_bytes
    )
    assert isinstance(manifest_value, dict)
    manifest = manifest_value
    if manifest.get("release_status") != "READY":
        raise ValueError("public snapshot release_status must be READY")
    if manifest.get("snapshot_content_ready") is not True:
        raise ValueError("public snapshot snapshot_content_ready must be true")

    manifest_files = _manifest_file_map(manifest)
    checksums = _parse_checksum_index(checksum_bytes)
    if set(manifest_files) != set(checksums):
        raise ValueError(
            "public snapshot manifest/checksum file sets differ: "
            f"manifest_only={sorted(set(manifest_files) - set(checksums))}, "
            f"checksum_only={sorted(set(checksums) - set(manifest_files))}"
        )

    actual_files: set[str] = set()
    for current, directory_names, file_names in os.walk(
        source, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        safe_directories: list[str] = []
        for name in sorted(directory_names):
            child = current_path / name
            relative = child.relative_to(source).as_posix()
            _path_policy_check(relative)
            if child.is_symlink():
                raise ValueError(f"refusing source symlink: {relative}")
            safe_directories.append(name)
        directory_names[:] = safe_directories
        for name in sorted(file_names):
            child = current_path / name
            relative = child.relative_to(source).as_posix()
            _path_policy_check(relative)
            if child.is_symlink():
                raise ValueError(f"refusing source symlink: {relative}")
            if not stat.S_ISREG(child.lstat().st_mode):
                raise ValueError(f"source is not a regular file: {relative}")
            actual_files.add(relative)
    expected_files = set(checksums) | SOURCE_INDEX_FILES
    if actual_files != expected_files:
        raise ValueError(
            "public snapshot contains unindexed or missing files: "
            f"unindexed={sorted(actual_files - expected_files)}, "
            f"missing={sorted(expected_files - actual_files)}"
        )

    contents: dict[str, bytes] = {}
    for relative in sorted(checksums):
        content, _ = _read_regular_file(source, relative)
        actual_digest = hashlib.sha256(content).hexdigest()
        if actual_digest != checksums[relative]:
            raise ValueError(f"SHA256SUMS digest mismatch: {relative}")
        row = manifest_files[relative]
        if row["sha256"] != actual_digest:
            raise ValueError(f"public manifest digest mismatch: {relative}")
        if row["size_bytes"] != len(content):
            raise ValueError(f"public manifest size mismatch: {relative}")
        _parse_content(relative, content)
        contents[relative] = content

    return manifest, contents


def _contains_restricted_reference(value: object) -> bool:
    if isinstance(value, str):
        return bool(re.search(r"(?i)(?:^|[\\/])data[\\/]restricted(?:[\\/]|$)", value))
    if isinstance(value, list):
        return any(_contains_restricted_reference(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_restricted_reference(key)
            or _contains_restricted_reference(item)
            for key, item in value.items()
        )
    return False


def sanitize_hf_asset_manifest(content: bytes) -> bytes:
    value = _parse_content(HF_ASSET_MANIFEST_SOURCE, content)
    if not isinstance(value, dict) or not isinstance(value.get("assets"), list):
        raise ValueError("hf_asset_manifest must be an object with an assets array")

    safe_assets: list[dict[str, object]] = []
    excluded_policy_counts: dict[str, int] = {}
    for index, asset in enumerate(value["assets"]):
        if not isinstance(asset, dict):
            raise ValueError(f"hf_asset_manifest asset {index} is not an object")
        policy = asset.get("upload_policy")
        if not isinstance(policy, str):
            raise ValueError(f"hf_asset_manifest asset {index} lacks upload_policy")
        if policy not in SAFE_PUBLIC_ASSET_POLICIES:
            excluded_policy_counts[policy] = excluded_policy_counts.get(policy, 0) + 1
            continue
        sanitized = {
            str(key): item
            for key, item in asset.items()
            if key not in PATH_VALUE_KEYS
        }
        if _contains_restricted_reference(sanitized):
            raise ValueError(
                "sanitized hf_asset_manifest retains a data/restricted reference: "
                f"asset {asset.get('logical_id', index)!r}"
            )
        safe_assets.append(sanitized)

    sanitized_manifest = {
        "schema_version": "av-trace.hf-public-asset-manifest/1.0",
        "source_schema_version": value.get("schema_version"),
        "source_generated_date": value.get("generated_date"),
        "metadata_only": True,
        "sanitization": {
            "included_upload_policies": sorted(SAFE_PUBLIC_ASSET_POLICIES),
            "removed_fields": sorted(PATH_VALUE_KEYS),
            "excluded_policy_counts": dict(sorted(excluded_policy_counts.items())),
            "source_asset_count": len(value["assets"]),
            "published_asset_count": len(safe_assets),
            "note": (
                "Local paths, reconstruction commands, dependencies, hash-basis "
                "text, private-derived entries, and never-upload entries are omitted."
            ),
        },
        "repositories": {
            key: repository
            for key, repository in value.get("repositories", {}).items()
            if isinstance(repository, dict)
            and repository.get("visibility") == "public"
        },
        "assets": safe_assets,
    }
    result = _json_bytes(sanitized_manifest)
    _parse_content(HF_ASSET_MANIFEST_DESTINATION, result)
    _scan_forbidden_text(HF_ASSET_MANIFEST_DESTINATION, result)
    if b"data/restricted" in result.lower():
        raise ValueError("sanitized hf_asset_manifest contains data/restricted")
    return result


def _source_manifest_public_copy(manifest: Mapping[str, object]) -> bytes:
    public_copy = {
        key: value
        for key, value in manifest.items()
        if key
        not in {
            "files",
            "policy_decisions",
        }
    }
    public_copy["metadata_release_note"] = (
        "Payload file inventory and policy-decision details are omitted from the "
        "Hugging Face metadata release; source integrity is independently pinned "
        f"by {PUBLIC_CHECKSUM_DESTINATION}."
    )
    result = _json_bytes(public_copy)
    _parse_content(PUBLIC_MANIFEST_DESTINATION, result)
    _scan_forbidden_text(PUBLIC_MANIFEST_DESTINATION, result)
    return result


def build_payload(
    source: Path,
    manifest: Mapping[str, object],
    source_contents: Mapping[str, bytes],
) -> dict[str, StagedFile]:
    payload: dict[str, StagedFile] = {}
    for source_path, destination, reason in ALLOWLIST:
        content = source_contents.get(source_path)
        if content is None:
            raise ValueError(
                f"allowlisted file is absent from audited snapshot: {source_path}"
            )
        _path_policy_check(destination)
        _parse_content(destination, content)
        _scan_forbidden_text(destination, content)
        payload[destination] = StagedFile(
            path=destination,
            source=source_path,
            reason=reason,
            content=content,
        )

    asset_content = source_contents.get(HF_ASSET_MANIFEST_SOURCE)
    if asset_content is None:
        raise ValueError(
            "allowlisted file is absent from audited snapshot: "
            f"{HF_ASSET_MANIFEST_SOURCE}"
        )
    payload[HF_ASSET_MANIFEST_DESTINATION] = StagedFile(
        path=HF_ASSET_MANIFEST_DESTINATION,
        source=HF_ASSET_MANIFEST_SOURCE,
        reason="sanitized public asset identity/policy metadata",
        content=sanitize_hf_asset_manifest(asset_content),
    )
    payload[PUBLIC_MANIFEST_DESTINATION] = StagedFile(
        path=PUBLIC_MANIFEST_DESTINATION,
        source="PUBLIC_SNAPSHOT_MANIFEST.json",
        reason="public snapshot READY status and audit summary",
        content=_source_manifest_public_copy(manifest),
    )
    source_checksum_bytes, _ = _read_regular_file(source, "SHA256SUMS")
    _scan_forbidden_text(PUBLIC_CHECKSUM_DESTINATION, source_checksum_bytes)
    payload[PUBLIC_CHECKSUM_DESTINATION] = StagedFile(
        path=PUBLIC_CHECKSUM_DESTINATION,
        source="SHA256SUMS",
        reason="complete audited public snapshot payload hash index",
        content=source_checksum_bytes,
    )

    for relative, item in payload.items():
        _path_policy_check(relative)
        _parse_content(relative, item.content)
        _scan_forbidden_text(relative, item.content)
    return payload


def assemble_release(
    payload: Mapping[str, StagedFile],
    source: Path,
    source_manifest: Mapping[str, object],
) -> dict[str, StagedFile]:
    source_manifest_bytes, _ = _read_regular_file(
        source, "PUBLIC_SNAPSHOT_MANIFEST.json"
    )
    source_checksum_bytes, _ = _read_regular_file(source, "SHA256SUMS")
    file_rows = [
        {
            "path": item.path,
            "source": item.source,
            "reason": item.reason,
            "size_bytes": item.size_bytes,
            "sha256": item.sha256,
            "mode": f"{item.mode:04o}",
        }
        for item in sorted(payload.values(), key=lambda item: item.path)
    ]
    manifest = {
        "schema_version": "av-trace.hf-public-metadata-release/1.0",
        "builder": "scripts/build_hf_public_metadata_snapshot.py",
        "metadata_only": True,
        "network_access": False,
        "token_access": False,
        "upload_performed": False,
        "source_public_snapshot": {
            "release_status": source_manifest.get("release_status"),
            "snapshot_content_ready": source_manifest.get(
                "snapshot_content_ready"
            ),
            "as_of_date": source_manifest.get("as_of_date"),
            "manifest_sha256": hashlib.sha256(source_manifest_bytes).hexdigest(),
            "checksum_index_sha256": hashlib.sha256(
                source_checksum_bytes
            ).hexdigest(),
            "payload_file_count": len(source_manifest.get("files", [])),
        },
        "integrity": {
            "algorithm": "sha256",
            "index": "SHA256SUMS",
            "index_excludes": sorted(RELEASE_CHECKSUM_EXCLUDES),
            "reason": "SHA256SUMS is intentionally not self-hashed",
            "manifest_inventory_excludes": sorted(RELEASE_INDEX_FILES),
        },
        "files": file_rows,
    }
    manifest_item = StagedFile(
        path="HF_RELEASE_MANIFEST.json",
        source=None,
        reason="generated Hugging Face release provenance and file inventory",
        content=_json_bytes(manifest),
    )
    release = dict(payload)
    release[manifest_item.path] = manifest_item
    checksum_members = dict(release)
    checksums = "".join(
        f"{item.sha256}  {item.path}\n"
        for item in sorted(checksum_members.values(), key=lambda item: item.path)
    ).encode("utf-8")
    release["SHA256SUMS"] = StagedFile(
        path="SHA256SUMS",
        source=None,
        reason="generated SHA-256 index for all non-index release files",
        content=checksums,
    )
    audit_release_files(release)
    return release


def audit_release_files(files: Mapping[str, StagedFile | bytes]) -> None:
    if set(files) < RELEASE_INDEX_FILES:
        raise ValueError("HF release index files are incomplete")

    def content_for(value: StagedFile | bytes) -> bytes:
        return value.content if isinstance(value, StagedFile) else value

    manifest_value = _parse_content(
        "HF_RELEASE_MANIFEST.json",
        content_for(files["HF_RELEASE_MANIFEST.json"]),
    )
    assert isinstance(manifest_value, dict)
    rows = manifest_value.get("files")
    if not isinstance(rows, list):
        raise ValueError("HF_RELEASE_MANIFEST.json files must be an array")
    expected = set(files) - RELEASE_INDEX_FILES
    manifest_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("HF_RELEASE_MANIFEST.json contains an invalid file row")
        relative = row["path"]
        if relative in manifest_paths:
            raise ValueError(f"duplicate HF release manifest path: {relative}")
        manifest_paths.add(relative)
        item = files.get(relative)
        if item is None:
            continue
        content = content_for(item)
        if row.get("sha256") != hashlib.sha256(content).hexdigest():
            raise ValueError(f"HF release manifest checksum mismatch: {relative}")
        if row.get("size_bytes") != len(content):
            raise ValueError(f"HF release manifest size mismatch: {relative}")
    if manifest_paths != expected:
        raise ValueError("HF release manifest file set is incomplete")

    checksums = _parse_checksum_index(content_for(files["SHA256SUMS"]))
    checksum_expected = set(files) - RELEASE_CHECKSUM_EXCLUDES
    if set(checksums) != checksum_expected:
        raise ValueError("HF release SHA256SUMS file set is incomplete")
    for relative, digest in checksums.items():
        if hashlib.sha256(content_for(files[relative])).hexdigest() != digest:
            raise ValueError(f"HF release SHA256SUMS mismatch: {relative}")

    for relative, item in files.items():
        _path_policy_check(relative)
        content = content_for(item)
        _parse_content(relative, content)
        _scan_forbidden_text(relative, content)
        if relative == HF_ASSET_MANIFEST_DESTINATION and b"data/restricted" in content.lower():
            raise ValueError("sanitized hf_asset_manifest contains data/restricted")


def _absolute_without_resolving(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _validate_destination(destination: Path, source: Path) -> Path:
    absolute = _absolute_without_resolving(destination)
    try:
        relative = absolute.relative_to("/tmp")
    except ValueError as error:
        raise ValueError("destination must be under /tmp") from error
    if not relative.parts:
        raise ValueError("destination must be a directory below /tmp, not /tmp")

    current = Path("/tmp")
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"destination must not traverse a symlink: {current}")
        if not current.exists():
            break
    resolved = absolute.resolve(strict=False)
    if resolved == source or source in resolved.parents:
        raise ValueError("destination must be outside the source snapshot")
    return absolute


def _prepare_destination(destination: Path) -> None:
    if destination.exists():
        raise ValueError(
            f"destination must be new and absent; refusing overwrite: {destination}"
        )
    destination.mkdir(parents=True, mode=0o755)


def _ensure_parent(destination: Path, parent: PurePosixPath) -> None:
    current = destination
    for component in parent.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"refusing destination symlink: {current}")
        if current.exists():
            if not current.is_dir():
                raise ValueError(f"destination parent is not a directory: {current}")
        else:
            current.mkdir(mode=0o755)


def write_release(destination: Path, files: Mapping[str, StagedFile]) -> None:
    _prepare_destination(destination)
    for relative, item in sorted(files.items()):
        pure = PurePosixPath(_normalized_relative_path(relative))
        _ensure_parent(destination, pure.parent)
        output = destination.joinpath(*pure.parts)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(output, flags, item.mode)
        try:
            view = memoryview(item.content)
            while view:
                view = view[os.write(descriptor, view) :]
            os.fchmod(descriptor, item.mode)
        finally:
            os.close(descriptor)


def audit_release_directory(destination: Path) -> None:
    contents: dict[str, bytes] = {}
    for current, directory_names, file_names in os.walk(
        destination, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        safe_directories: list[str] = []
        for name in sorted(directory_names):
            child = current_path / name
            relative = child.relative_to(destination).as_posix()
            if child.is_symlink():
                raise ValueError(f"release directory symlink is forbidden: {relative}")
            safe_directories.append(name)
        directory_names[:] = safe_directories
        for name in sorted(file_names):
            child = current_path / name
            relative = child.relative_to(destination).as_posix()
            if child.is_symlink():
                raise ValueError(f"release file symlink is forbidden: {relative}")
            metadata = child.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"release entry is not a regular file: {relative}")
            contents[relative] = child.read_bytes()
    audit_release_files(contents)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"audited READY public snapshot (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=DEFAULT_DESTINATION,
        help=f"new empty staging directory under /tmp (default: {DEFAULT_DESTINATION})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="write the staging directory; default is dry-run",
    )
    parser.add_argument(
        "--json-output",
        help="write result JSON to PATH or '-'",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        source = args.source.resolve()
        destination = _validate_destination(args.destination, source)
        source_manifest, source_contents = audit_public_snapshot(source)
        payload = build_payload(source, source_manifest, source_contents)
        release = assemble_release(payload, source, source_manifest)
        if args.execute:
            write_release(destination, release)
            audit_release_directory(destination)
        result = {
            "schema_version": 1,
            "mode": "execute" if args.execute else "dry-run",
            "metadata_only": True,
            "source": str(source),
            "source_release_status": source_manifest["release_status"],
            "source_payload_file_count": len(source_manifest["files"]),
            "destination": str(destination),
            "release_file_count": len(release),
            "release_bytes": sum(item.size_bytes for item in release.values()),
            "network_access": False,
            "token_access": False,
            "upload_performed": False,
        }
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))

    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_output == "-":
        sys.stdout.write(serialized)
    elif args.json_output:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
        print(serialized, end="")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
