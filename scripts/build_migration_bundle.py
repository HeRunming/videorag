#!/usr/bin/env python3
"""Build a model-free AV-TRACE migration handoff bundle under /tmp.

The default is a non-mutating dry run.  ``--execute`` writes only regular,
small files into a new empty destination under ``/tmp``.  The builder refuses
restricted source paths, source or destination symlinks, hash drift, likely
credential material, and files larger than the manifest limit.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath


DEFAULT_DESTINATION = Path("/tmp/av-trace-migration-bundle")
DEFAULT_MANIFEST = Path("data/migration/migration_bundle_manifest.json")
BUNDLE_INDEX = "BUNDLE_SHA256SUMS"
BUNDLE_MANIFEST = "BUNDLE_MANIFEST.json"
TEXT_SUFFIXES = {
    ".cfg",
    ".csv",
    ".ini",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
FORBIDDEN_SECRET_PATH_NAMES = {
    ".env",
    ".netrc",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
SECRET_PATTERNS = (
    (
        "private_key",
        re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    ),
    (
        "github_token",
        re.compile(r"\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "hugging_face_token",
        re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    ),
    (
        "aws_access_key",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "assigned_secret",
        re.compile(
            r"""(?ix)
            \b(?:GH_TOKEN|HF_TOKEN|HUGGINGFACE_HUB_TOKEN|API_KEY|
                SECRET_KEY|PASSWORD)\b
            \s*=\s*
            (?P<quote>["'])
            (?!\$\{|<|PLACEHOLDER|REDACTED|INJECT_FROM_SECRET_MANAGER)
            [^"'\r\n]{8,}
            (?P=quote)
            """
        ),
    ),
)


@dataclass(frozen=True)
class PlannedFile:
    destination: str
    content: bytes
    mode: int
    source: str
    role: str

    @property
    def bytes(self) -> int:
        return len(self.content)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def safe_relative_path(value: str) -> str:
    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or ".." in pure.parts
        or value != pure.as_posix()
    ):
        raise ValueError(
            f"path must be normalized and repository-relative: {value!r}"
        )
    return value


def is_forbidden_source_path(relative: str) -> bool:
    pure = PurePosixPath(relative)
    parts = pure.parts
    return (
        len(parts) >= 2
        and parts[0] == "data"
        and parts[1] == "restricted"
    )


def source_components_are_not_symlinks(root: Path, relative: str) -> None:
    current = root
    for component in PurePosixPath(relative).parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"refusing source symlink: {relative}")


def read_regular_file(root: Path, relative: str) -> tuple[bytes, int]:
    relative = safe_relative_path(relative)
    if is_forbidden_source_path(relative):
        raise ValueError(f"restricted source path is forbidden: {relative}")
    source_components_are_not_symlinks(root, relative)
    path = root / relative
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"source is not a regular file: {relative}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), stat.S_IMODE(info.st_mode)
    finally:
        os.close(descriptor)


def likely_text(path: str, content: bytes) -> bool:
    if PurePosixPath(path).suffix.lower() in TEXT_SUFFIXES:
        return True
    return b"\x00" not in content[:4096]


def secret_findings(path: str, content: bytes) -> list[str]:
    findings: list[str] = []
    pure = PurePosixPath(path)
    if pure.name.lower() in FORBIDDEN_SECRET_PATH_NAMES:
        findings.append("secret-bearing filename")
    if not likely_text(path, content):
        return findings
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return findings
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(label)
    return findings


def load_manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("migration bundle manifest must be a JSON object")
    if value.get("schema_version") != "av-trace.migration-bundle-manifest/1.0":
        raise ValueError("unsupported migration bundle manifest schema")
    files = value.get("source_files")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest requires a non-empty source_files array")
    return value


def load_public_snapshot_builder(root: Path, relative: str):
    relative = safe_relative_path(relative)
    path = root / relative
    spec = importlib.util.spec_from_file_location(
        "_av_trace_public_snapshot_builder", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load public snapshot builder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_binding(
    *,
    relative: str,
    content: bytes,
    declared_bytes: object,
    declared_sha256: object,
) -> None:
    if declared_bytes != len(content):
        raise ValueError(
            f"byte-count drift for {relative}: "
            f"expected {declared_bytes}, got {len(content)}"
        )
    actual = "sha256:" + sha256_bytes(content)
    if declared_sha256 != actual:
        raise ValueError(
            f"SHA-256 drift for {relative}: "
            f"expected {declared_sha256}, got {actual}"
        )


def add_planned_file(
    files: dict[str, PlannedFile],
    item: PlannedFile,
    *,
    max_file_bytes: int,
) -> None:
    destination = safe_relative_path(item.destination)
    if destination in files:
        raise ValueError(f"duplicate bundle destination: {destination}")
    if item.bytes > max_file_bytes:
        raise ValueError(
            f"file exceeds small-file limit ({max_file_bytes} bytes): "
            f"{destination} ({item.bytes} bytes)"
        )
    findings = secret_findings(destination, item.content)
    if findings:
        raise ValueError(
            f"possible secret material in {destination}: "
            + ", ".join(sorted(set(findings)))
        )
    files[destination] = item


def build_source_files(
    root: Path,
    manifest: Mapping[str, object],
    *,
    max_file_bytes: int,
    public_builder: object | None = None,
) -> dict[str, PlannedFile]:
    planned: dict[str, PlannedFile] = {}
    rows = manifest["source_files"]
    assert isinstance(rows, list)
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise TypeError(f"source_files[{index}] must be an object")
        relative = safe_relative_path(str(row["path"]))
        destination = safe_relative_path(
            str(row.get("destination", relative))
        )
        content, mode = read_regular_file(root, relative)
        validate_binding(
            relative=relative,
            content=content,
            declared_bytes=row.get("bytes"),
            declared_sha256=row.get("sha256"),
        )
        if public_builder is not None and hasattr(
            public_builder, "sanitize_public_content"
        ):
            content = public_builder.sanitize_public_content(relative, content)
        add_planned_file(
            planned,
            PlannedFile(
                destination=destination,
                content=content,
                mode=mode,
                source=relative,
                role=str(row.get("role", "handoff")),
            ),
            max_file_bytes=max_file_bytes,
        )
    return planned


def build_public_snapshot_files(
    root: Path,
    manifest: Mapping[str, object],
    *,
    as_of_date: str,
    max_file_bytes: int,
) -> dict[str, PlannedFile]:
    config = manifest["public_snapshot"]
    if not isinstance(config, dict):
        raise TypeError("public_snapshot must be an object")
    builder_relative = safe_relative_path(str(config["builder"]))
    policy_relative = safe_relative_path(str(config["policy"]))
    prefix = safe_relative_path(str(config["bundle_prefix"])).rstrip("/")

    builder_content, _ = read_regular_file(root, builder_relative)
    policy_content, _ = read_regular_file(root, policy_relative)
    bindings = config["bindings"]
    if not isinstance(bindings, dict):
        raise TypeError("public_snapshot.bindings must be an object")
    validate_binding(
        relative=builder_relative,
        content=builder_content,
        declared_bytes=bindings["builder"]["bytes"],
        declared_sha256=bindings["builder"]["sha256"],
    )
    validate_binding(
        relative=policy_relative,
        content=policy_content,
        declared_bytes=bindings["policy"]["bytes"],
        declared_sha256=bindings["policy"]["sha256"],
    )

    builder = load_public_snapshot_builder(root, builder_relative)
    license_choice_value = config.get("license_choice")
    license_file_value = config.get("license_file")
    if (license_choice_value is None) != (license_file_value is None):
        raise ValueError(
            "public_snapshot license_choice and license_file must be supplied together"
        )
    public_plan = builder.build_plan(
        root,
        root / policy_relative,
        as_of_date=as_of_date,
        large_file_bytes=int(config["large_file_bytes"]),
        license_choice=(
            str(license_choice_value)
            if license_choice_value is not None
            else None
        ),
        license_file=(
            root / safe_relative_path(str(license_file_value))
            if license_file_value is not None
            else None
        ),
    )
    public_files = builder._assemble_snapshot_files(public_plan)
    public_manifest = json.loads(
        public_files["PUBLIC_SNAPSHOT_MANIFEST.json"].content
    )
    expected_status = config["expected_release_status"]
    if public_manifest["release_status"] != expected_status:
        raise ValueError(
            "public snapshot release status drift: "
            f"expected {expected_status}, "
            f"got {public_manifest['release_status']}"
        )
    if not public_manifest["snapshot_content_ready"]:
        raise ValueError("public snapshot content is not ready")

    planned: dict[str, PlannedFile] = {}
    for relative, public_item in sorted(public_files.items()):
        destination = f"{prefix}/{relative}"
        add_planned_file(
            planned,
            PlannedFile(
                destination=destination,
                content=public_item.content,
                mode=public_item.mode,
                source=f"generated:{builder_relative}:{relative}",
                role="public_snapshot",
            ),
            max_file_bytes=max_file_bytes,
        )
    return planned


def generated_bundle_manifest(
    source_manifest_path: str,
    source_manifest_content: bytes,
    files: Mapping[str, PlannedFile],
    *,
    as_of_date: str,
) -> bytes:
    public_manifest_path = "public_snapshot/PUBLIC_SNAPSHOT_MANIFEST.json"
    public_sums_path = "public_snapshot/SHA256SUMS"
    if public_manifest_path not in files or public_sums_path not in files:
        raise ValueError("public snapshot index files are missing")
    role_counts = Counter(item.role for item in files.values())
    payload = {
        "schema_version": "av-trace.migration-bundle/1.0",
        "as_of_date": as_of_date,
        "classification": "CODE_METADATA_PLANS_NO_RESTRICTED_MEDIA",
        "source_manifest": {
            "path": source_manifest_path,
            "bytes": len(source_manifest_content),
            "sha256": "sha256:" + sha256_bytes(source_manifest_content),
        },
        "safety": {
            "model_calls": 0,
            "network_requests": 0,
            "uploads": 0,
            "tokens_read": False,
            "restricted_source_files": 0,
            "symlinks_allowed": False,
            "secret_material_allowed": False,
        },
        "public_snapshot_binding": {
            "manifest_path": public_manifest_path,
            "manifest_sha256": "sha256:" + files[public_manifest_path].sha256,
            "sha256sums_path": public_sums_path,
            "sha256sums_sha256": "sha256:" + files[public_sums_path].sha256,
        },
        "payload_summary": {
            "file_count": len(files),
            "bytes": sum(item.bytes for item in files.values()),
            "files_by_role": dict(sorted(role_counts.items())),
        },
        "files": [
            {
                "path": path,
                "bytes": item.bytes,
                "sha256": "sha256:" + item.sha256,
                "mode": f"{item.mode:04o}",
                "source": item.source,
                "role": item.role,
            }
            for path, item in sorted(files.items())
        ],
    }
    return json_bytes(payload)


def assemble_bundle(
    root: Path,
    manifest_path: Path,
    *,
    as_of_date: str,
) -> dict[str, PlannedFile]:
    manifest_content = manifest_path.read_bytes()
    manifest = load_manifest(manifest_path)
    max_file_bytes = int(manifest["safety"]["max_file_bytes"])
    public_config = manifest["public_snapshot"]
    if not isinstance(public_config, dict):
        raise TypeError("public_snapshot must be an object")
    public_builder = load_public_snapshot_builder(
        root, safe_relative_path(str(public_config["builder"]))
    )
    files = build_source_files(
        root,
        manifest,
        max_file_bytes=max_file_bytes,
        public_builder=public_builder,
    )
    manifest_relative = manifest_path.relative_to(root).as_posix()
    add_planned_file(
        files,
        PlannedFile(
            destination=manifest_relative,
            content=manifest_content,
            mode=stat.S_IMODE(manifest_path.stat().st_mode),
            source=manifest_relative,
            role="bundle_definition",
        ),
        max_file_bytes=max_file_bytes,
    )
    public_files = build_public_snapshot_files(
        root,
        manifest,
        as_of_date=as_of_date,
        max_file_bytes=max_file_bytes,
    )
    for item in public_files.values():
        add_planned_file(files, item, max_file_bytes=max_file_bytes)

    bundle_manifest_content = generated_bundle_manifest(
        manifest_relative,
        manifest_content,
        files,
        as_of_date=as_of_date,
    )
    add_planned_file(
        files,
        PlannedFile(
            destination=BUNDLE_MANIFEST,
            content=bundle_manifest_content,
            mode=0o644,
            source="generated",
            role="bundle_index",
        ),
        max_file_bytes=max_file_bytes,
    )
    sums = "".join(
        f"{item.sha256}  {path}\n"
        for path, item in sorted(files.items())
    ).encode("utf-8")
    add_planned_file(
        files,
        PlannedFile(
            destination=BUNDLE_INDEX,
            content=sums,
            mode=0o644,
            source="generated",
            role="bundle_index",
        ),
        max_file_bytes=max_file_bytes,
    )
    validate_bundle_files(files, public_builder, max_file_bytes=max_file_bytes)
    return files


def validate_bundle_files(
    files: Mapping[str, PlannedFile],
    public_builder: object,
    *,
    max_file_bytes: int,
) -> None:
    required = {
        BUNDLE_MANIFEST,
        BUNDLE_INDEX,
        "data/migration/hf_asset_manifest.json",
        "data/migration/path_rebinding_manifest.json",
        "public_snapshot/PUBLIC_SNAPSHOT_MANIFEST.json",
        "public_snapshot/SHA256SUMS",
        "public_snapshot/data/migration/hf_asset_manifest.json",
        "public_snapshot/data/migration/path_rebinding_manifest.json",
    }
    missing = sorted(required - set(files))
    if missing:
        raise ValueError(f"migration bundle required files are missing: {missing}")
    cache_paths = [
        path
        for path in files
        if any(
            part in {"__pycache__", ".pytest_cache"}
            for part in PurePosixPath(path).parts
        )
        or PurePosixPath(path).suffix.lower() in {".pyc", ".pyo"}
    ]
    if cache_paths:
        raise ValueError(
            f"migration bundle contains generated cache artifacts: {cache_paths}"
        )
    contents = {path: item.content for path, item in files.items()}
    if hasattr(public_builder, "audit_contents"):
        findings = public_builder.audit_contents(
            contents, large_file_bytes=max_file_bytes
        )
        if findings:
            raise ValueError(
                "migration bundle public-content audit failed: "
                + json.dumps(findings[:10], sort_keys=True)
            )
    if hasattr(public_builder, "_python_ast_findings"):
        ast_findings = public_builder._python_ast_findings(contents)
        if ast_findings:
            raise ValueError(
                "migration bundle Python AST audit failed: "
                + json.dumps(ast_findings[:10], sort_keys=True)
            )
    if hasattr(public_builder, "audit_snapshot_manifest_files"):
        public_prefix = "public_snapshot/"
        public_files = {
            path[len(public_prefix) :]: item.content
            for path, item in files.items()
            if path.startswith(public_prefix)
        }
        public_findings = public_builder.audit_snapshot_manifest_files(
            public_files
        )
        if public_findings:
            raise ValueError(
                "embedded public snapshot completeness audit failed: "
                + json.dumps(public_findings[:10], sort_keys=True)
            )
    bundle_manifest = json.loads(files[BUNDLE_MANIFEST].content)
    rows = bundle_manifest.get("files")
    if not isinstance(rows, list):
        raise ValueError("BUNDLE_MANIFEST.json files field must be an array")
    expected_manifest_paths = set(files) - {BUNDLE_MANIFEST, BUNDLE_INDEX}
    manifest_paths = {
        str(row.get("path"))
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    if manifest_paths != expected_manifest_paths:
        raise ValueError(
            "bundle manifest file set mismatch: "
            f"missing={sorted(expected_manifest_paths - manifest_paths)}, "
            f"extra={sorted(manifest_paths - expected_manifest_paths)}"
        )
    sums_paths: set[str] = set()
    for line in files[BUNDLE_INDEX].content.decode("utf-8").splitlines():
        digest, separator, path = line.partition("  ")
        if (
            not separator
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or path in sums_paths
        ):
            raise ValueError(f"invalid or duplicate bundle checksum line: {line!r}")
        sums_paths.add(path)
        if path not in files or files[path].sha256 != digest:
            raise ValueError(f"bundle checksum mismatch: {path}")
    expected_sums_paths = set(files) - {BUNDLE_INDEX}
    if sums_paths != expected_sums_paths:
        raise ValueError(
            "bundle checksum file set mismatch: "
            f"missing={sorted(expected_sums_paths - sums_paths)}, "
            f"extra={sorted(sums_paths - expected_sums_paths)}"
        )


def validate_destination(root: Path, destination: Path) -> Path:
    absolute = Path(os.path.abspath(destination))
    resolved = absolute.resolve(strict=False)
    try:
        resolved.relative_to(Path("/tmp"))
    except ValueError as error:
        raise ValueError("destination must be under /tmp") from error
    try:
        resolved.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("destination must be outside the source repository")

    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current = current / component
        if current.is_symlink():
            raise ValueError(
                f"destination path must not traverse a symlink: {current}"
            )
        if not current.exists():
            break
    return absolute


def prepare_destination(destination: Path) -> None:
    if destination.is_symlink():
        raise ValueError(f"destination must not be a symlink: {destination}")
    if destination.exists():
        if not destination.is_dir():
            raise ValueError(
                f"destination is not a directory: {destination}"
            )
        if any(destination.iterdir()):
            raise ValueError(
                f"destination must be empty; refusing overwrite: {destination}"
            )
    else:
        destination.mkdir(parents=True, mode=0o755)


def ensure_parent(destination: Path, relative: str) -> None:
    current = destination
    for component in PurePosixPath(relative).parent.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"refusing destination symlink: {current}")
        if current.exists():
            if not current.is_dir():
                raise ValueError(
                    f"destination parent is not a directory: {current}"
                )
        else:
            current.mkdir(mode=0o755)


def write_bundle(
    destination: Path, files: Mapping[str, PlannedFile]
) -> None:
    prepare_destination(destination)
    for relative, item in sorted(files.items()):
        ensure_parent(destination, relative)
        target = destination / relative
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            item.mode,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(item.content)
                handle.flush()
                os.fsync(handle.fileno())
            os.fchmod(descriptor, item.mode)
        finally:
            os.close(descriptor)


def verify_written_bundle(
    destination: Path, files: Mapping[str, PlannedFile]
) -> None:
    observed: set[str] = set()
    for path in destination.rglob("*"):
        relative = path.relative_to(destination).as_posix()
        if path.is_symlink():
            raise ValueError(f"written bundle contains symlink: {relative}")
        if path.is_file():
            observed.add(relative)
    expected = set(files)
    if observed != expected:
        raise ValueError(
            "written bundle file set mismatch: "
            f"missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )
    for relative, item in files.items():
        target = destination / relative
        if target.stat().st_size != item.bytes:
            raise ValueError(f"written byte-count mismatch: {relative}")
        if sha256_file(target) != item.sha256:
            raise ValueError(f"written SHA-256 mismatch: {relative}")
    forbidden = [
        relative
        for relative in observed
        if any(
            part in {"__pycache__", ".pytest_cache"}
            for part in PurePosixPath(relative).parts
        )
        or PurePosixPath(relative).suffix.lower() in {".pyc", ".pyo"}
    ]
    if forbidden:
        raise ValueError(
            f"written bundle contains generated cache artifacts: {sorted(forbidden)}"
        )


def result_for(
    destination: Path,
    files: Mapping[str, PlannedFile],
    *,
    executed: bool,
) -> dict[str, object]:
    index = files[BUNDLE_INDEX]
    public_manifest = files[
        "public_snapshot/PUBLIC_SNAPSHOT_MANIFEST.json"
    ]
    public_sums = files["public_snapshot/SHA256SUMS"]
    role_counts = Counter(item.role for item in files.values())
    return {
        "schema_version": "av-trace.migration-bundle-result/1.0",
        "mode": "execute" if executed else "dry-run",
        "destination": str(destination),
        "bundle_file_count": len(files),
        "bundle_bytes": sum(item.bytes for item in files.values()),
        "bundle_sha256": "sha256:" + index.sha256,
        "bundle_hash_basis": "SHA-256 of BUNDLE_SHA256SUMS",
        "public_snapshot_manifest_sha256": (
            "sha256:" + public_manifest.sha256
        ),
        "public_snapshot_sha256sums_sha256": (
            "sha256:" + public_sums.sha256
        ),
        "files_by_role": dict(sorted(role_counts.items())),
        "safety": {
            "model_calls": 0,
            "network_requests": 0,
            "uploads": 0,
            "tokens_read": False,
            "restricted_files_copied": 0,
        },
    }


def print_result(result: Mapping[str, object]) -> None:
    print(f"migration bundle:      {result['mode']}")
    print(f"destination:           {result['destination']}")
    print(f"bundle files:          {result['bundle_file_count']}")
    print(f"bundle bytes:          {result['bundle_bytes']}")
    print(f"bundle hash:           {result['bundle_sha256']}")
    print(
        "public manifest hash: "
        f"{result['public_snapshot_manifest_sha256']}"
    )
    print(
        "public sums hash:     "
        f"{result['public_snapshot_sha256sums_sha256']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--destination",
        type=Path,
        default=DEFAULT_DESTINATION,
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="write the bundle; default is a non-mutating dry run",
    )
    parser.add_argument(
        "--as-of-date",
        default=datetime.now().astimezone().date().isoformat(),
    )
    parser.add_argument(
        "--json-output",
        help="write the result JSON to PATH or '-'",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        date.fromisoformat(args.as_of_date)
    except ValueError:
        parser.error("--as-of-date must be YYYY-MM-DD")

    root = args.root.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest
        else root / DEFAULT_MANIFEST
    )
    try:
        files = assemble_bundle(
            root, manifest_path, as_of_date=args.as_of_date
        )
        destination = validate_destination(root, args.destination)
        if args.execute:
            write_bundle(destination, files)
            verify_written_bundle(destination, files)
        result = result_for(
            destination, files, executed=args.execute
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))

    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_output == "-":
        sys.stdout.write(serialized)
    elif args.json_output:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
        print_result(result)
    else:
        print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
