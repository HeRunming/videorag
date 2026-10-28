#!/usr/bin/env python3
"""Build a strict, local-only PRIVATE derived restoration snapshot.

The builder reads ``data/migration/hf_asset_manifest.json`` to validate the
logical assets, then applies the narrower, explicit restoration allowlist in
``data/migration/private_derived_release_manifest.json``.  Dry-run is the
default.  ``--execute`` may create only a new, absent directory under
``/tmp``.  The tool performs no network, authentication, upload, or source
permission operations and never follows symlinks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence


AS_OF_DATE = "2026-10-28"
DEFAULT_ASSET_MANIFEST = "data/migration/hf_asset_manifest.json"
DEFAULT_RELEASE_MANIFEST = (
    "data/migration/private_derived_release_manifest.json"
)
OUTPUT_MANIFEST = "PRIVATE_DERIVED_MANIFEST.json"
OUTPUT_CHECKSUMS = "SHA256SUMS"
OUTPUT_RESTORE = "RESTORE.md"

FORBIDDEN_COMPONENTS = frozenset(
    {"models", "media", "raw", "staging", "acquisition_records"}
)
CACHE_COMPONENTS = frozenset(
    {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".cache"}
)
FORBIDDEN_SUFFIXES = frozenset(
    {
        ".mp4",
        ".m4v",
        ".safetensors",
        ".bin",
        ".headers",
        ".body",
        ".html",
        ".m3u8",
        ".curlmeta",
        ".pid",
        ".lock",
    }
)
CACHE_SUFFIXES = frozenset({".pyc", ".pyo"})
FORBIDDEN_NAME_PATTERNS = (
    ("authorization", re.compile(r"authori[sz]ation", re.IGNORECASE)),
    ("receipt", re.compile(r"receipt", re.IGNORECASE)),
    ("nonce", re.compile(r"nonce", re.IGNORECASE)),
    ("private_key", re.compile(r"private[-_. ]?key", re.IGNORECASE)),
    ("credential", re.compile(r"credential", re.IGNORECASE)),
    (
        "untouched_private_identity_or_ledger",
        re.compile(
            r"untouched.*(?:private.*identity|identity.*private|ledger)",
            re.IGNORECASE,
        ),
    ),
    ("source_dossier", re.compile(r"source[-_. ]?dossier", re.IGNORECASE)),
    (
        "source_provenance_log",
        re.compile(r"source[-_. ]?provenance.*log|provenance[-_. ]?log", re.IGNORECASE),
    ),
    (
        "http_body_or_headers",
        re.compile(r"(?:http[-_. ]?)?(?:body|headers?)$", re.IGNORECASE),
    ),
    (
        "runtime_auth_state",
        re.compile(r"runtime[-_. ]?auth|auth[-_. ]?state", re.IGNORECASE),
    ),
)

PRIVATE_KEY_PATTERN = re.compile(br"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
KNOWN_TOKEN_PATTERNS = (
    re.compile(br"\bhf_[A-Za-z0-9]{15,}\b"),
    re.compile(br"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(br"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(br"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(br"(?i)\bBearer[ \t]+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(
        br'''(?ix)
        ["']?
        (?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|
           client[_-]?secret|credential)
        ["']?
        \s*[:=]\s*
        ["']
        (?!PUBLIC_REDACTED|REDACTED|EXAMPLE|PLACEHOLDER|none\b|null\b)
        [^"'\r\n]{8,}
        ["']
        '''
    ),
)
INTERNAL_DOMAIN_PATTERNS = (
    re.compile(br"(?i)\b(?:[A-Za-z0-9-]+\.)+(?:woa|oa)\.com\b"),
    re.compile(br"(?i)\b(?:star|hy)[-_.]proxy\b"),
    re.compile(br"(?i)\b[A-Za-z0-9.-]+\.(?:internal|corp|localdomain)\b"),
)
OLD_ABSOLUTE_PATH = ("/" + "jizhicfs" + "/karonhe/AV-TRACE").encode()
SENSITIVE_JSON_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "auth_token",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "private_key",
        "credential",
        "credentials",
        "cookie",
    }
)
SAFE_SECRET_VALUES = frozenset(
    {"", "none", "null", "redacted", "public_redacted", "placeholder", "example"}
)


@dataclass(frozen=True)
class SelectedFile:
    source: Path
    path: str
    logical_asset: str
    reason: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class ExcludedFile:
    path: str
    bytes: int
    reason: str


@dataclass(frozen=True)
class BuildPlan:
    repository_root: Path
    asset_manifest_path: str
    release_manifest_path: str
    selected: tuple[SelectedFile, ...]
    excluded: tuple[ExcludedFile, ...]
    release_policy: Mapping[str, object]
    out_of_scope_private_assets: tuple[str, ...]

    @property
    def selected_bytes(self) -> int:
        return sum(item.bytes for item in self.selected)

    @property
    def excluded_bytes(self) -> int:
        return sum(item.bytes for item in self.excluded)


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
        raise ValueError(f"path must be normalized and repository-relative: {value!r}")
    return value


def _has_symlink_component(root: Path, relative: str) -> bool:
    current = root
    for component in PurePosixPath(relative).parts:
        current = current / component
        if current.is_symlink():
            return True
    return False


def _read_regular_file(root: Path, relative: str) -> bytes:
    relative = _normalized_relative_path(relative)
    if _has_symlink_component(root, relative):
        raise ValueError(f"refusing source symlink: {relative}")
    path = root.joinpath(*PurePosixPath(relative).parts)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as error:
        raise ValueError(f"required source is missing: {relative}") from error
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
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _load_json_file(root: Path, relative: str) -> object:
    content = _read_regular_file(root, relative)
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON: {relative}: {error}") from error


def _validate_sensitive_json_values(value: object, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in SENSITIVE_JSON_KEYS and child not in (None, False):
                credential_shaped = (
                    isinstance(child, str)
                    and child.strip().lower() not in SAFE_SECRET_VALUES
                ) or (isinstance(child, (dict, list)) and bool(child))
                if credential_shaped:
                    raise ValueError(
                        f"credential/secret value is forbidden in {path}: key {key!r}"
                    )
            _validate_sensitive_json_values(child, path)
    elif isinstance(value, list):
        for child in value:
            _validate_sensitive_json_values(child, path)


def _parse_structured_content(path: str, content: bytes) -> None:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".json":
        try:
            parsed = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid JSON: {path}: {error}") from error
        _validate_sensitive_json_values(parsed, path)
    elif suffix == ".jsonl":
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"invalid UTF-8 JSONL: {path}: {error}") from error
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid JSONL: {path}:{line_number}: {error}"
                ) from error
            _validate_sensitive_json_values(parsed, path)


def _scan_forbidden_content(path: str, content: bytes) -> str | None:
    if OLD_ABSOLUTE_PATH in content:
        return "old_absolute_machine_path"
    if PRIVATE_KEY_PATTERN.search(content):
        return "private_key_material"
    if any(pattern.search(content) for pattern in KNOWN_TOKEN_PATTERNS):
        return "known_credential_pattern"
    if any(pattern.search(content) for pattern in INTERNAL_DOMAIN_PATTERNS):
        return "internal_proxy_or_domain"
    return None


def _path_exclusion(relative: str) -> str | None:
    pure = PurePosixPath(relative)
    for component in pure.parts:
        normalized = component.lower().lstrip(".")
        if normalized in FORBIDDEN_COMPONENTS:
            return f"forbidden_component:{normalized}"
        if component.lower() in CACHE_COMPONENTS:
            return f"cache_component:{component.lower()}"
    suffix = pure.suffix.lower()
    if suffix in FORBIDDEN_SUFFIXES:
        return f"forbidden_suffix:{suffix}"
    if suffix in CACHE_SUFFIXES:
        return f"cache_suffix:{suffix}"
    stem_or_name = pure.name
    for label, pattern in FORBIDDEN_NAME_PATTERNS:
        if pattern.search(stem_or_name):
            return f"forbidden_name:{label}"
    return None


def _iter_root_files(repository_root: Path, relative_root: str) -> Iterable[str]:
    relative_root = _normalized_relative_path(relative_root)
    if not relative_root.startswith("data/restricted/"):
        raise ValueError(f"allowlist root must be under data/restricted/: {relative_root}")
    if _has_symlink_component(repository_root, relative_root):
        raise ValueError(f"refusing allowlist-root symlink: {relative_root}")
    absolute_root = repository_root.joinpath(*PurePosixPath(relative_root).parts)
    try:
        metadata = absolute_root.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"allowlist root is missing: {relative_root}") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"allowlist root is not a directory: {relative_root}")

    for current, directories, files in os.walk(absolute_root, followlinks=False):
        current_path = Path(current)
        for name in tuple(directories):
            child = current_path / name
            if child.is_symlink():
                relative = child.relative_to(repository_root).as_posix()
                raise ValueError(f"refusing source symlink: {relative}")
        for name in sorted(files):
            child = current_path / name
            relative = child.relative_to(repository_root).as_posix()
            if child.is_symlink():
                raise ValueError(f"refusing source symlink: {relative}")
            metadata = child.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"source is not a regular file: {relative}")
            yield relative


def _validate_control_manifests(
    asset_manifest: object, release_manifest: object
) -> tuple[dict[str, Mapping[str, object]], tuple[str, ...]]:
    if not isinstance(asset_manifest, dict) or not isinstance(
        asset_manifest.get("assets"), list
    ):
        raise ValueError("HF asset manifest must contain an assets list")
    if not isinstance(release_manifest, dict):
        raise ValueError("private release manifest must be a JSON object")
    if release_manifest.get("schema_version") != "av-trace.private-derived-release/1.0":
        raise ValueError("unsupported private release manifest schema")
    if release_manifest.get("generated_date") != AS_OF_DATE:
        raise ValueError(f"private release manifest date must be {AS_OF_DATE}")
    allowlist = release_manifest.get("allowlist")
    if not isinstance(allowlist, list) or not allowlist:
        raise ValueError("private release manifest allowlist must be non-empty")
    explicit_exclusions = release_manifest.get("explicit_exclusions", [])
    if not isinstance(explicit_exclusions, list):
        raise ValueError("explicit_exclusions must be a list")
    seen_explicit_exclusions: set[str] = set()
    for item in explicit_exclusions:
        if not isinstance(item, dict):
            raise ValueError("explicit_exclusions entries must be objects")
        path = _normalized_relative_path(str(item.get("path", "")))
        if path in seen_explicit_exclusions:
            raise ValueError(f"duplicate explicit exclusion: {path}")
        seen_explicit_exclusions.add(path)
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError(f"explicit exclusion reason is required: {path}")

    private_assets: dict[str, Mapping[str, object]] = {}
    for item in asset_manifest["assets"]:
        if not isinstance(item, dict):
            raise ValueError("HF asset manifest contains a non-object asset")
        if item.get("upload_policy") == "private_derived_index":
            logical_id = item.get("logical_id")
            if not isinstance(logical_id, str) or logical_id in private_assets:
                raise ValueError("invalid or duplicate private-derived logical_id")
            private_assets[logical_id] = item

    requested: set[str] = set()
    seen_roots: set[str] = set()
    for surface in allowlist:
        if not isinstance(surface, dict):
            raise ValueError("allowlist entries must be objects")
        logical_id = surface.get("logical_asset")
        roots = surface.get("roots")
        if logical_id not in private_assets:
            raise ValueError(
                f"allowlisted logical asset is not private_derived_index: {logical_id!r}"
            )
        if logical_id in requested:
            raise ValueError(f"duplicate allowlisted logical asset: {logical_id}")
        requested.add(logical_id)
        if not isinstance(roots, list) or not roots:
            raise ValueError(f"allowlisted logical asset has no roots: {logical_id}")
        for root in roots:
            if not isinstance(root, dict):
                raise ValueError(f"allowlist roots must be objects: {logical_id}")
            path = _normalized_relative_path(str(root.get("path", "")))
            if path in seen_roots:
                raise ValueError(f"duplicate allowlist root: {path}")
            seen_roots.add(path)
            if not isinstance(root.get("reason"), str) or not root["reason"].strip():
                raise ValueError(f"allowlist root reason is required: {path}")
            basenames = root.get("include_basenames")
            if basenames is not None and (
                not isinstance(basenames, list)
                or not basenames
                or not all(isinstance(name, str) and name for name in basenames)
            ):
                raise ValueError(f"invalid include_basenames: {path}")

    out_of_scope = tuple(sorted(set(private_assets) - requested))
    return private_assets, out_of_scope


def build_plan(
    repository_root: Path,
    *,
    asset_manifest_path: str = DEFAULT_ASSET_MANIFEST,
    release_manifest_path: str = DEFAULT_RELEASE_MANIFEST,
) -> BuildPlan:
    repository_root = repository_root.resolve()
    asset_manifest = _load_json_file(repository_root, asset_manifest_path)
    release_manifest = _load_json_file(repository_root, release_manifest_path)
    _, out_of_scope = _validate_control_manifests(asset_manifest, release_manifest)
    assert isinstance(release_manifest, dict)

    regenerable = release_manifest.get("regenerable_old_path_exclusions", [])
    if not isinstance(regenerable, list) or not all(
        isinstance(item, str) for item in regenerable
    ):
        raise ValueError("regenerable_old_path_exclusions must be a string list")
    regenerable_paths = {_normalized_relative_path(item) for item in regenerable}
    explicit_exclusions_value = release_manifest.get("explicit_exclusions", [])
    assert isinstance(explicit_exclusions_value, list)
    explicit_exclusions = {
        _normalized_relative_path(str(item["path"])): str(item["reason"])
        for item in explicit_exclusions_value
        if isinstance(item, dict)
    }

    selected: list[SelectedFile] = []
    excluded: list[ExcludedFile] = []
    seen_files: set[str] = set()
    allowlist = release_manifest["allowlist"]
    assert isinstance(allowlist, list)
    for surface in allowlist:
        assert isinstance(surface, dict)
        logical_asset = str(surface["logical_asset"])
        roots = surface["roots"]
        assert isinstance(roots, list)
        for root in roots:
            assert isinstance(root, dict)
            root_path = str(root["path"])
            reason = str(root["reason"])
            basenames_value = root.get("include_basenames")
            basenames = (
                frozenset(str(item) for item in basenames_value)
                if isinstance(basenames_value, list)
                else None
            )
            root_selected = 0
            for relative in _iter_root_files(repository_root, root_path):
                if relative in seen_files:
                    raise ValueError(f"file selected by overlapping roots: {relative}")
                seen_files.add(relative)
                source = repository_root.joinpath(*PurePosixPath(relative).parts)
                size = source.lstat().st_size
                if relative in explicit_exclusions:
                    excluded.append(
                        ExcludedFile(
                            relative,
                            size,
                            f"explicit_manifest_exclusion:{explicit_exclusions[relative]}",
                        )
                    )
                    continue
                if basenames is not None and PurePosixPath(relative).name not in basenames:
                    excluded.append(
                        ExcludedFile(relative, size, "not_in_root_filename_allowlist")
                    )
                    continue
                path_reason = _path_exclusion(relative)
                if path_reason is not None:
                    excluded.append(ExcludedFile(relative, size, path_reason))
                    continue
                content = _read_regular_file(repository_root, relative)
                if len(content) != size:
                    raise ValueError(f"source size changed while reading: {relative}")
                content_reason = _scan_forbidden_content(relative, content)
                if content_reason == "old_absolute_machine_path" and relative in regenerable_paths:
                    excluded.append(
                        ExcludedFile(
                            relative,
                            size,
                            "manifest_classified_regenerable_old_absolute_path",
                        )
                    )
                    continue
                if content_reason is not None:
                    raise ValueError(f"{content_reason} is forbidden in {relative}")
                _parse_structured_content(relative, content)
                selected.append(
                    SelectedFile(
                        source=source,
                        path=relative,
                        logical_asset=logical_asset,
                        reason=reason,
                        bytes=size,
                        sha256=hashlib.sha256(content).hexdigest(),
                    )
                )
                root_selected += 1
            if root_selected == 0:
                raise ValueError(f"allowlist root selected no files: {root_path}")

    selected.sort(key=lambda item: item.path)
    excluded.sort(key=lambda item: item.path)
    return BuildPlan(
        repository_root=repository_root,
        asset_manifest_path=asset_manifest_path,
        release_manifest_path=release_manifest_path,
        selected=tuple(selected),
        excluded=tuple(excluded),
        release_policy=release_manifest,
        out_of_scope_private_assets=out_of_scope,
    )


def _restore_instructions() -> bytes:
    return f"""# PRIVATE derived restoration snapshot

Generated {AS_OF_DATE}. This snapshot is **PRIVATE** and is not suitable for a public repository,
public dataset, or unrestricted artifact store. It contains private-derived
indexes, candidates, labels, evaluation outputs, and timing metadata. It does
not grant redistribution rights to underlying source media.

Verify integrity from the snapshot root before restoration:

```sh
sha256sum --check SHA256SUMS
```

Restore the preserved repository-relative paths into a clone:

```sh
cp -a /tmp/av-trace-private-derived/data/restricted/. /path/to/AV-TRACE/data/restricted/
```

Use a new or intentionally prepared clone; review conflicts before replacing
existing files. Raw media and model weights are intentionally absent and must
be reacquired separately from their approved upstream sources under current
terms and authorization.

Any references to old authorizations inside retained scientific manifests are
historical audit context only. They are non-executable, do not carry forward,
and do not authorize network access, downloads, model access, or redistribution.
""".encode("utf-8")


def _exclusions_summary(plan: BuildPlan) -> dict[str, object]:
    by_reason = Counter(item.reason for item in plan.excluded)
    policy = plan.release_policy.get("global_exclusions", {})
    return {
        "global_policy": policy,
        "out_of_scope_private_derived_logical_assets": list(
            plan.out_of_scope_private_assets
        ),
        "within_allowlisted_roots": {
            "file_count": len(plan.excluded),
            "bytes": plan.excluded_bytes,
            "by_reason": dict(sorted(by_reason.items())),
            "files": [
                {"path": item.path, "bytes": item.bytes, "reason": item.reason}
                for item in plan.excluded
            ],
        },
    }


def _output_manifest(plan: BuildPlan, restore_content: bytes) -> dict[str, object]:
    return {
        "schema_version": "av-trace.private-derived-snapshot/1.0",
        "generated_date": AS_OF_DATE,
        "classification": "PRIVATE",
        "public_release_suitable": False,
        "source_asset_manifest": plan.asset_manifest_path,
        "source_release_manifest": plan.release_manifest_path,
        "path_contract": (
            "Selected files preserve repository-relative data/restricted/ paths "
            "for direct restoration into a clone."
        ),
        "network_access": False,
        "token_access": False,
        "upload_performed": False,
        "snapshot_summary": {
            "selected_file_count": len(plan.selected),
            "selected_bytes": plan.selected_bytes,
        },
        "exclusions_summary": _exclusions_summary(plan),
        "files": [
            {
                "source_logical_asset": item.logical_asset,
                "path": item.path,
                "bytes": item.bytes,
                "sha256": item.sha256,
                "reason": item.reason,
            }
            for item in plan.selected
        ],
        "generated_files": [
            {
                "path": OUTPUT_RESTORE,
                "bytes": len(restore_content),
                "sha256": hashlib.sha256(restore_content).hexdigest(),
                "reason": "private restoration and handling instructions",
            },
            {
                "path": OUTPUT_MANIFEST,
                "reason": "self-describing snapshot manifest; not self-hashed here",
            },
            {
                "path": OUTPUT_CHECKSUMS,
                "reason": "complete checksum index; intentionally not self-hashed",
            },
        ],
        "checksum_contract": {
            "index": OUTPUT_CHECKSUMS,
            "covers": (
                "every selected payload file, RESTORE.md, and "
                "PRIVATE_DERIVED_MANIFEST.json"
            ),
            "excludes": [OUTPUT_CHECKSUMS],
        },
    }


def _destination_guard(destination: Path) -> Path:
    destination = destination.absolute()
    tmp_root = Path("/tmp")
    try:
        destination.relative_to(tmp_root)
    except ValueError as error:
        raise ValueError("destination must be under /tmp") from error
    if destination == tmp_root:
        raise ValueError("destination must be a child directory under /tmp")
    if destination.exists() or destination.is_symlink():
        raise ValueError("destination must be new and absent")
    parent = destination.parent
    if not parent.exists() or not parent.is_dir():
        raise ValueError("destination parent must already exist")
    resolved_parent = parent.resolve()
    try:
        resolved_parent.relative_to(tmp_root)
    except ValueError as error:
        raise ValueError("destination parent must resolve under /tmp") from error
    current = tmp_root
    for component in destination.relative_to(tmp_root).parts[:-1]:
        current = current / component
        if current.is_symlink():
            raise ValueError("destination parent path must not contain symlinks")
    return destination


def _write_new_file(destination: Path, relative: str, content: bytes) -> None:
    relative = _normalized_relative_path(relative)
    target = destination.joinpath(*PurePosixPath(relative).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(content)


def execute_plan(plan: BuildPlan, destination: Path) -> dict[str, object]:
    destination = _destination_guard(destination)
    restore_content = _restore_instructions()
    manifest = _output_manifest(plan, restore_content)
    manifest_content = _json_bytes(manifest)
    checksums: list[tuple[str, str]] = []

    destination.mkdir()
    try:
        for item in plan.selected:
            content = _read_regular_file(plan.repository_root, item.path)
            digest = hashlib.sha256(content).hexdigest()
            if len(content) != item.bytes or digest != item.sha256:
                raise ValueError(f"source changed after dry-run validation: {item.path}")
            _write_new_file(destination, item.path, content)
            checksums.append((item.path, digest))
        _write_new_file(destination, OUTPUT_RESTORE, restore_content)
        checksums.append(
            (OUTPUT_RESTORE, hashlib.sha256(restore_content).hexdigest())
        )
        _write_new_file(destination, OUTPUT_MANIFEST, manifest_content)
        checksums.append(
            (OUTPUT_MANIFEST, hashlib.sha256(manifest_content).hexdigest())
        )
        checksum_content = "".join(
            f"{digest}  {path}\n" for path, digest in sorted(checksums)
        ).encode("utf-8")
        _write_new_file(destination, OUTPUT_CHECKSUMS, checksum_content)
        audit_snapshot(destination)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return manifest


def _parse_checksums(content: bytes) -> dict[str, str]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"invalid UTF-8 {OUTPUT_CHECKSUMS}: {error}") from error
    result: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError(f"invalid {OUTPUT_CHECKSUMS} line {line_number}")
        digest, relative = match.groups()
        relative = _normalized_relative_path(relative)
        if relative in result:
            raise ValueError(f"duplicate checksum path: {relative}")
        if relative == OUTPUT_CHECKSUMS:
            raise ValueError(f"{OUTPUT_CHECKSUMS} must not self-hash")
        result[relative] = digest
    return result


def audit_snapshot(destination: Path) -> None:
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("snapshot destination must be a real directory")
    manifest_content = _read_regular_file(destination, OUTPUT_MANIFEST)
    try:
        manifest = json.loads(manifest_content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {OUTPUT_MANIFEST}: {error}") from error
    if manifest.get("schema_version") != "av-trace.private-derived-snapshot/1.0":
        raise ValueError("unsupported private snapshot manifest schema")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("private snapshot manifest files must be a list")
    expected_payload: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("private snapshot manifest contains a non-object file")
        relative = _normalized_relative_path(str(row.get("path", "")))
        if not relative.startswith("data/restricted/"):
            raise ValueError(f"payload path is outside data/restricted/: {relative}")
        if relative in expected_payload:
            raise ValueError(f"duplicate manifest payload path: {relative}")
        expected_payload[relative] = row

    expected_files = set(expected_payload) | {
        OUTPUT_RESTORE,
        OUTPUT_MANIFEST,
        OUTPUT_CHECKSUMS,
    }
    actual_files: set[str] = set()
    for path in destination.rglob("*"):
        relative = path.relative_to(destination).as_posix()
        if path.is_symlink():
            raise ValueError(f"snapshot contains a symlink: {relative}")
        if path.is_dir():
            if _path_exclusion(relative + "/placeholder") is not None:
                raise ValueError(f"snapshot contains a forbidden directory: {relative}")
            continue
        if not path.is_file():
            raise ValueError(f"snapshot contains a non-regular file: {relative}")
        actual_files.add(relative)
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        extra = sorted(actual_files - expected_files)
        raise ValueError(
            f"snapshot manifest completeness failure: missing={missing}, extra={extra}"
        )

    for relative, row in expected_payload.items():
        content = _read_regular_file(destination, relative)
        digest = hashlib.sha256(content).hexdigest()
        if len(content) != row.get("bytes"):
            raise ValueError(f"snapshot manifest byte-count mismatch: {relative}")
        if digest != row.get("sha256"):
            raise ValueError(f"snapshot manifest checksum mismatch: {relative}")
        path_reason = _path_exclusion(relative)
        if path_reason is not None:
            raise ValueError(f"snapshot contains forbidden payload: {relative}")
        content_reason = _scan_forbidden_content(relative, content)
        if content_reason is not None:
            raise ValueError(f"snapshot contains forbidden content: {relative}")
        _parse_structured_content(relative, content)

    generated = manifest.get("generated_files")
    if not isinstance(generated, list):
        raise ValueError("private snapshot generated_files must be a list")
    restore_row = next(
        (
            row
            for row in generated
            if isinstance(row, dict) and row.get("path") == OUTPUT_RESTORE
        ),
        None,
    )
    if restore_row is None:
        raise ValueError("RESTORE.md is missing from generated_files")
    restore_content = _read_regular_file(destination, OUTPUT_RESTORE)
    if len(restore_content) != restore_row.get("bytes") or hashlib.sha256(
        restore_content
    ).hexdigest() != restore_row.get("sha256"):
        raise ValueError("generated RESTORE.md integrity mismatch")

    checksum_content = _read_regular_file(destination, OUTPUT_CHECKSUMS)
    checksums = _parse_checksums(checksum_content)
    expected_checksum_paths = expected_files - {OUTPUT_CHECKSUMS}
    if set(checksums) != expected_checksum_paths:
        raise ValueError("SHA256SUMS completeness failure")
    for relative, expected_digest in checksums.items():
        content = _read_regular_file(destination, relative)
        if hashlib.sha256(content).hexdigest() != expected_digest:
            raise ValueError(f"SHA256SUMS mismatch: {relative}")

    summary = manifest.get("snapshot_summary")
    if not isinstance(summary, dict):
        raise ValueError("private snapshot summary is missing")
    if summary.get("selected_file_count") != len(expected_payload):
        raise ValueError("snapshot summary file count mismatch")
    if summary.get("selected_bytes") != sum(
        int(row["bytes"]) for row in expected_payload.values()
    ):
        raise ValueError("snapshot summary byte count mismatch")


def _summary(plan: BuildPlan, mode: str, destination: Path) -> dict[str, object]:
    return {
        "mode": mode,
        "classification": "PRIVATE",
        "as_of_date": AS_OF_DATE,
        "destination": str(destination),
        "selected_file_count": len(plan.selected),
        "selected_bytes": plan.selected_bytes,
        "excluded_file_count_within_allowlisted_roots": len(plan.excluded),
        "excluded_bytes_within_allowlisted_roots": plan.excluded_bytes,
        "out_of_scope_private_derived_logical_assets": list(
            plan.out_of_scope_private_assets
        ),
        "network_access": False,
        "token_access": False,
        "upload_performed": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root containing data/migration and data/restricted",
    )
    parser.add_argument(
        "--asset-manifest",
        default=DEFAULT_ASSET_MANIFEST,
        help="repository-relative HF logical asset manifest",
    )
    parser.add_argument(
        "--release-manifest",
        default=DEFAULT_RELEASE_MANIFEST,
        help="repository-relative strict restoration allowlist",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("/tmp/av-trace-private-derived"),
        help="new absent destination under /tmp",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="create the snapshot; without this flag only validate and report",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        plan = build_plan(
            arguments.repository_root,
            asset_manifest_path=arguments.asset_manifest,
            release_manifest_path=arguments.release_manifest,
        )
        if arguments.execute:
            execute_plan(plan, arguments.destination)
            result = _summary(plan, "execute", arguments.destination)
        else:
            result = _summary(plan, "dry-run", arguments.destination)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
