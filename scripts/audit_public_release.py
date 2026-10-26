#!/usr/bin/env python3
"""Build and audit a conservative, model-free public-release file manifest.

The audit is deliberately independent of Git state.  It never modifies the
repository unless ``--json-output`` explicitly requests a report file.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


DEFAULT_LARGE_FILE_BYTES = 10 * 1024 * 1024
TEXT_SCAN_LIMIT_BYTES = 10 * 1024 * 1024
SAMPLE_BYTES = 8192

PUBLIC_TOP_LEVEL_DIRECTORIES = {
    "docs",
    "mvp",
    "scripts",
    "src",
    "tests",
    "tests_agent_runtime",
    "tests_captaincook4d_family_mining",
    "tests_captaincook4d_wave0_index",
    "tests_controller_v2",
    "tests_controller_v3",
    "tests_data",
    "tests_epic_family_mining",
    "tests_epic_wave1_index",
    "tests_media",
    "tests_media_pipeline",
    "tests_mini_pilot_families",
    "tests_mini_pilot_index",
    "tests_mvp",
    "tests_real_av",
    "tests_scale1a",
    "tests_scale1b",
    "tests_scale1b_agent",
    "tests_validation",
    "tooling",
    "tools",
}

PUBLIC_DATA_DIRECTORIES = {
    "data/acquisition_plan",
    "data/candidates",
    "data/rehearsal_plan",
}

EXCLUDED_DIRECTORY_NAMES = {
    "__pycache__": "generated Python bytecode cache",
    ".pytest_cache": "test cache",
    ".ruff_cache": "lint cache",
    ".mypy_cache": "type-check cache",
    ".tox": "test environment",
    ".nox": "test environment",
    ".venv": "local virtual environment",
    "venv": "local virtual environment",
    "build": "build artifact",
    "dist": "distribution artifact",
    "logs": "runtime logs",
    "log": "runtime logs",
    "output": "runtime output",
    "outputs": "runtime output",
    "results": "runtime results",
    "media": "media payload",
    "models": "model payload",
    "restricted": "restricted material",
}

EXCLUDED_DIRECTORY_PREFIXES = {
    ".git": "version-control internals",
    ".agents": "local agent configuration",
    ".codex": "local agent configuration",
    "data/access_review": "private access and authorization records",
    "data/acquisition_preflight": "live acquisition/preflight records",
    "data/hf_recon": "third-party service reconnaissance snapshots",
    "data/rehearsal_review": "internal review packets",
    "data/restricted": "restricted data, media, models, and run evidence",
    "data/source_recon": "third-party source snapshots pending release review",
    "mvp/generated": "generated output",
    "mvp/results": "runtime results",
    "mvp/media_backed/fixtures": "media fixtures",
    "orchestration/logs": "internal orchestration logs",
    "orchestration/prompts": "internal orchestration prompts",
    "orchestration/results": "internal orchestration results",
    "data/rehearsal_plan/external_gateway_strong_agent_smoke_run_v1": (
        "internal model/gateway run attempts and outputs"
    ),
}

MEDIA_AND_MODEL_SUFFIXES = {
    ".avi",
    ".bin",
    ".ckpt",
    ".flac",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
    ".wav",
    ".webm",
    ".weights",
}

GENERATED_SUFFIXES = {
    ".egg-info",
    ".log",
    ".partial",
    ".pyc",
    ".pyo",
    ".swp",
    ".tmp",
}

SENSITIVE_ARTIFACT_SUFFIXES = {
    ".csv",
    ".json",
    ".jsonl",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

# Exact-path/check allowlisting only.  Entries must state a reviewable reason.
# This list is intentionally empty: repository-local exceptions should be
# supplied in a reviewed JSON file via --allowlist and are copied into reports.
BUILTIN_ALLOWLIST: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class Finding:
    check: str
    path: str
    message: str
    severity: str = "blocker"
    line: int | None = None
    column: int | None = None
    excerpt: str | None = None
    allowlisted: bool = False
    allowlist_reason: str | None = None


@dataclass(frozen=True)
class Exclusion:
    path: str
    kind: str
    reason: str


@dataclass(frozen=True)
class AllowlistEntry:
    path: str
    check: str
    reason: str

    @classmethod
    def from_mapping(cls, value: object) -> "AllowlistEntry":
        if not isinstance(value, dict):
            raise ValueError("each allowlist entry must be an object")
        path = value.get("path")
        check = value.get("check")
        reason = value.get("reason")
        if not all(isinstance(item, str) and item.strip() for item in (path, check, reason)):
            raise ValueError("allowlist entries require non-empty path, check, and reason")
        return cls(path=path, check=check, reason=reason)


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{20,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    (
        "assigned credential",
        re.compile(
            r"""(?ix)
            \b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|
            password|passwd|secret[_-]?key)\b
            \s*[:=]\s*
            ["']?([A-Za-z0-9+/_.:@-]{8,})["']?
            """
        ),
    ),
)

INTERNAL_DOMAIN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"""(?ix)
        (?<![A-Za-z0-9_])
        (?:
            https?://
            (?:[^/\s:@]+(?::[^/\s@]+)?@)?
        )?
        (?:
            (?:hy|star)-proxy(?:\.[A-Za-z0-9.-]+)?
            |
            (?:[A-Za-z0-9-]+\.)+(?:woa|oa)\.com
            |
            (?:proxy|gateway)\.internal
        )
        (?::\d{1,5})?
        (?![A-Za-z0-9_])
        """
    ),
    re.compile(r"(?i)(?<![A-Za-z0-9])(?:hy|star)_proxy"),
)

ABSOLUTE_MACHINE_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![A-Za-z0-9_.-])/(?:jizhicfs|root|home|Users|mnt|private/tmp)/[^\s\"'`,;)}\]]+"),
    re.compile(r"(?i)\b[A-Z]:\\(?:Users|Documents and Settings)\\[^\s\"']+"),
)

PRIVATE_GOVERNANCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bexternal-gateway-dev-(?:controller|finalizer)-\d+\b"),
    re.compile(r"\bP23QAV2-[A-Z0-9-]*AUTH[A-Z0-9-]*\b"),
    re.compile(
        r"""(?ix)
        \b(?:private[_ -]?(?:governance|roster|ledger)[_ -]?(?:id|key)|
        authorization[_ -]?(?:id|claim)|approval[_ -]?id)\b
        \s*[:=]\s*(?P<quote>["'])
        (?P<governance_value>[A-Za-z0-9_.:-]{4,})
        (?P=quote)
        """
    ),
)

SAFE_ASSIGNED_VALUES = {
    "changeme",
    "example",
    "placeholder",
    "redacted",
    "replace_me",
    "required",
    "secret",
    "test-only",
    "test_only",
    "your_token",
}


def _posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _path_is_or_is_below(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def directory_exclusion_reason(path: str) -> str | None:
    for prefix, reason in EXCLUDED_DIRECTORY_PREFIXES.items():
        if _path_is_or_is_below(path, prefix):
            return reason
    for component in PurePosixPath(path).parts:
        if component in EXCLUDED_DIRECTORY_NAMES:
            return EXCLUDED_DIRECTORY_NAMES[component]
        if component.endswith(".egg-info"):
            return "generated package metadata"
    return None


def is_public_surface(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if len(parts) == 1:
        return (
            parts[0] in PUBLIC_TOP_LEVEL_DIRECTORIES
            or any(prefix.startswith(path + "/") for prefix in PUBLIC_DATA_DIRECTORIES)
        )
    top = parts[0]
    if top in PUBLIC_TOP_LEVEL_DIRECTORIES:
        return True
    return any(
        _path_is_or_is_below(path, prefix) or prefix.startswith(path + "/")
        for prefix in PUBLIC_DATA_DIRECTORIES
    )


def file_exclusion_reason(path: str) -> str | None:
    pure = PurePosixPath(path)
    name = pure.name
    lower_name = name.lower()
    suffix = pure.suffix.lower()
    parts_lower = tuple(part.lower() for part in pure.parts)

    if len(pure.parts) != 1 and not is_public_surface(path):
        return "outside the conservative public include surface"
    if directory_exclusion_reason(path):
        return directory_exclusion_reason(path)
    if suffix in MEDIA_AND_MODEL_SUFFIXES:
        return "media or model payload"
    if suffix in GENERATED_SUFFIXES or any(lower_name.endswith(item) for item in GENERATED_SUFFIXES):
        return "generated/cache/log artifact"
    if name == ".coverage" or lower_name.startswith("coverage."):
        return "coverage output"
    if lower_name.startswith(".env"):
        return "credential-bearing environment file"
    if suffix in {".pem", ".key", ".p12", ".pfx"}:
        return "credential or private-key artifact"
    if "raw_attempt" in lower_name or "attempt_marker" in lower_name:
        return "private attempt record"
    if "failure_capsule" in lower_name or ".failure-" in lower_name:
        return "private failure capsule"
    if suffix in SENSITIVE_ARTIFACT_SUFFIXES:
        if any(word in lower_name for word in ("credential", "secret", "token")):
            return "credential/token artifact"
        if "authorization" in lower_name or "authorisation" in lower_name:
            return "authorization artifact"
        if "private" in lower_name:
            return "private artifact"
    if (
        len(parts_lower) >= 3
        and parts_lower[0:2] == ("data", "rehearsal_plan")
        and lower_name.startswith("untouched_test_group_ledger_")
        and "public_commitment" not in lower_name
    ):
        return "private untouched-test ledger"
    return None


def looks_binary(sample: bytes) -> bool:
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    text_controls = {7, 8, 9, 10, 12, 13, 27}
    suspicious = sum(byte < 32 and byte not in text_controls for byte in sample)
    return suspicious / len(sample) > 0.05


def _line_column(text: str, start: int) -> tuple[int, int]:
    line = text.count("\n", 0, start) + 1
    previous_newline = text.rfind("\n", 0, start)
    column = start + 1 if previous_newline < 0 else start - previous_newline
    return line, column


def _redacted_excerpt(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    before = text[line_start:start][-80:]
    after = text[end:line_end][:80]
    return (before + "[REDACTED]" + after).strip()


def _finding_for_match(
    *,
    check: str,
    path: str,
    message: str,
    text: str,
    match: re.Match[str],
) -> Finding:
    line, column = _line_column(text, match.start())
    return Finding(
        check=check,
        path=path,
        message=message,
        line=line,
        column=column,
        excerpt=_redacted_excerpt(text, match.start(), match.end()),
    )


def scan_text(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for label, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if label == "assigned credential":
                value = match.group(1).lower()
                if (
                    value in SAFE_ASSIGNED_VALUES
                    or value.startswith(("example", "fake", "mock", "test"))
                    or value.endswith(("_env", "_file", "_path"))
                ):
                    continue
            findings.append(
                _finding_for_match(
                    check="secret_pattern",
                    path=path,
                    message=f"possible {label}",
                    text=text,
                    match=match,
                )
            )
    for pattern in INTERNAL_DOMAIN_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                _finding_for_match(
                    check="internal_domain",
                    path=path,
                    message="internal proxy or domain reference",
                    text=text,
                    match=match,
                )
            )
    for pattern in ABSOLUTE_MACHINE_PATH_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                _finding_for_match(
                    check="absolute_machine_path",
                    path=path,
                    message="absolute machine-specific path",
                    text=text,
                    match=match,
                )
            )
    for pattern in PRIVATE_GOVERNANCE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.groupdict().get("governance_value")
            if value and value.lower() in {
                "example",
                "placeholder",
                "public_redacted_identifier",
                "redacted",
                "test-only",
                "test_only",
            }:
                continue
            findings.append(
                _finding_for_match(
                    check="private_governance_id",
                    path=path,
                    message="possible private governance or run identifier",
                    text=text,
                    match=match,
                )
            )
    return findings


def load_allowlist(path: Path | None) -> list[AllowlistEntry]:
    entries = [AllowlistEntry.from_mapping(item) for item in BUILTIN_ALLOWLIST]
    if path is None:
        return entries
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("allowlist JSON must be an array")
    entries.extend(AllowlistEntry.from_mapping(item) for item in value)
    return entries


def apply_allowlist(finding: Finding, entries: Sequence[AllowlistEntry]) -> Finding:
    for entry in entries:
        if entry.check not in {"*", finding.check}:
            continue
        if fnmatch.fnmatchcase(finding.path, entry.path):
            value = asdict(finding)
            value["allowlisted"] = True
            value["allowlist_reason"] = entry.reason
            return Finding(**value)
    return finding


def _license_findings(root: Path, candidate_paths: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    license_names = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
    if not any((root / name).is_file() for name in license_names):
        findings.append(
            Finding(
                check="license_boundary",
                path=".",
                message=(
                    "no repository-level code license is present; public release requires "
                    "an explicit owner-approved code-license decision"
                ),
            )
        )
    required_notices = {
        "docs/migration/LICENSE_DECISION_REQUIRED.md",
        "docs/migration/THIRD_PARTY_DATA_NOTICE.md",
    }
    for path in sorted(required_notices - candidate_paths):
        findings.append(
            Finding(
                check="license_boundary",
                path=path,
                message="required public-release license boundary notice is missing",
            )
        )
    return findings


def audit_repository(
    root: Path,
    *,
    large_file_bytes: int = DEFAULT_LARGE_FILE_BYTES,
    allowlist: Sequence[AllowlistEntry] = (),
) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {root}")

    candidate_files: list[dict[str, object]] = []
    exclusions: list[Exclusion] = []
    findings: list[Finding] = []
    symlinks: list[str] = []

    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_directories: list[str] = []
        for directory_name in sorted(directory_names):
            full_path = current_path / directory_name
            relative = _posix(full_path, root)
            if full_path.is_symlink():
                symlinks.append(relative)
                exclusions.append(Exclusion(relative, "symlink", "symlinks are not released"))
                continue
            reason = directory_exclusion_reason(relative)
            if reason is not None or not is_public_surface(relative):
                exclusions.append(
                    Exclusion(
                        relative,
                        "directory",
                        reason or "outside the conservative public include surface",
                    )
                )
                continue
            kept_directories.append(directory_name)
        directory_names[:] = kept_directories

        for file_name in sorted(file_names):
            full_path = current_path / file_name
            relative = _posix(full_path, root)
            if full_path.is_symlink():
                symlinks.append(relative)
                exclusions.append(Exclusion(relative, "symlink", "symlinks are not released"))
                continue
            reason = file_exclusion_reason(relative)
            if reason is not None:
                exclusions.append(Exclusion(relative, "file", reason))
                continue
            try:
                size = full_path.stat().st_size
            except OSError as error:
                findings.append(
                    Finding(
                        check="read_error",
                        path=relative,
                        message=f"could not stat candidate file: {error}",
                    )
                )
                continue

            entry: dict[str, object] = {"path": relative, "size_bytes": size}
            candidate_files.append(entry)
            if size > large_file_bytes:
                findings.append(
                    Finding(
                        check="large_file",
                        path=relative,
                        message=(
                            f"candidate file is {size} bytes, above the configured "
                            f"{large_file_bytes}-byte review threshold"
                        ),
                    )
                )

            try:
                with full_path.open("rb") as handle:
                    sample = handle.read(SAMPLE_BYTES)
            except OSError as error:
                findings.append(
                    Finding(
                        check="read_error",
                        path=relative,
                        message=f"could not read candidate file: {error}",
                    )
                )
                continue

            if looks_binary(sample):
                entry["content_type"] = "binary"
                findings.append(
                    Finding(
                        check="binary_file",
                        path=relative,
                        message="binary content is not allowed on the default public surface",
                    )
                )
                continue
            entry["content_type"] = "text"
            if size > TEXT_SCAN_LIMIT_BYTES:
                findings.append(
                    Finding(
                        check="content_scan_limit",
                        path=relative,
                        message=(
                            f"text content was not scanned because it exceeds "
                            f"{TEXT_SCAN_LIMIT_BYTES} bytes"
                        ),
                    )
                )
                continue
            try:
                text = full_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                findings.append(
                    Finding(
                        check="binary_file",
                        path=relative,
                        message="candidate is not valid UTF-8 text",
                    )
                )
                continue
            except OSError as error:
                findings.append(
                    Finding(
                        check="read_error",
                        path=relative,
                        message=f"could not scan candidate text: {error}",
                    )
                )
                continue
            findings.extend(scan_text(relative, text))

    candidate_files.sort(key=lambda item: str(item["path"]))
    exclusions.sort(key=lambda item: item.path)
    candidate_path_set = {str(item["path"]) for item in candidate_files}
    findings.extend(_license_findings(root, candidate_path_set))
    findings = [apply_allowlist(item, allowlist) for item in findings]
    findings.sort(
        key=lambda item: (
            item.allowlisted,
            item.path,
            item.check,
            item.line or 0,
            item.column or 0,
        )
    )

    blocker_findings = [item for item in findings if not item.allowlisted]
    blocked_paths = {item.path for item in blocker_findings if item.path != "."}
    release_ready_files = [
        item for item in candidate_files if str(item["path"]) not in blocked_paths
    ]
    check_counts = Counter(item.check for item in blocker_findings)
    exclusion_counts = Counter(item.reason for item in exclusions)
    candidate_bytes = sum(int(item["size_bytes"]) for item in candidate_files)
    release_ready_bytes = sum(int(item["size_bytes"]) for item in release_ready_files)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(root),
        "policy": {
            "git_independent": True,
            "default_mutation": "none",
            "large_file_threshold_bytes": large_file_bytes,
            "text_scan_limit_bytes": TEXT_SCAN_LIMIT_BYTES,
            "public_top_level_directories": sorted(PUBLIC_TOP_LEVEL_DIRECTORIES),
            "public_data_directories": sorted(PUBLIC_DATA_DIRECTORIES),
        },
        "summary": {
            "status": "blocked" if blocker_findings else "pass",
            "candidate_file_count": len(candidate_files),
            "candidate_bytes": candidate_bytes,
            "release_ready_file_count": len(release_ready_files),
            "release_ready_bytes": release_ready_bytes,
            "excluded_entry_count": len(exclusions),
            "symlink_count": len(symlinks),
            "blocker_count": len(blocker_findings),
            "blocked_candidate_path_count": len(blocked_paths & candidate_path_set),
            "allowlisted_finding_count": len(findings) - len(blocker_findings),
            "blockers_by_check": dict(sorted(check_counts.items())),
            "exclusions_by_reason": dict(sorted(exclusion_counts.items())),
        },
        "candidate_public_files": candidate_files,
        "release_ready_files": release_ready_files,
        "excluded_entries": [asdict(item) for item in exclusions],
        "symlinks": sorted(symlinks),
        "blockers": [asdict(item) for item in blocker_findings],
        "allowlisted_findings": [
            asdict(item) for item in findings if item.allowlisted
        ],
        "allowlist": [asdict(item) for item in allowlist],
    }


def _write_json(report: dict[str, object], destination: str) -> None:
    serialized = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if destination == "-":
        sys.stdout.write(serialized)
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized, encoding="utf-8")


def _print_summary(report: dict[str, object]) -> None:
    summary = report["summary"]
    assert isinstance(summary, dict)
    print(f"public-release audit: {summary['status']}")
    print(f"candidate files:       {summary['candidate_file_count']}")
    print(f"candidate bytes:       {summary['candidate_bytes']}")
    print(f"release-ready files:   {summary['release_ready_file_count']}")
    print(f"release-ready bytes:   {summary['release_ready_bytes']}")
    print(f"excluded entries:      {summary['excluded_entry_count']}")
    print(f"blockers:              {summary['blocker_count']}")
    blockers_by_check = summary["blockers_by_check"]
    if isinstance(blockers_by_check, dict) and blockers_by_check:
        print("blockers by check:")
        for check, count in blockers_by_check.items():
            print(f"  {check}: {count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: parent of this script)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="return exit status 1 when non-allowlisted blockers are found",
    )
    parser.add_argument(
        "--json-output",
        metavar="PATH",
        help="write the full report to PATH, or '-' for stdout",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        help=(
            "optional JSON array of exact/glob path, check, and reason entries; "
            "all applied entries are copied into the report"
        ),
    )
    parser.add_argument(
        "--large-file-bytes",
        type=int,
        default=DEFAULT_LARGE_FILE_BYTES,
        help=f"large-file review threshold (default: {DEFAULT_LARGE_FILE_BYTES})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.large_file_bytes <= 0:
        parser.error("--large-file-bytes must be positive")
    try:
        allowlist = load_allowlist(args.allowlist)
        report = audit_repository(
            args.root,
            large_file_bytes=args.large_file_bytes,
            allowlist=allowlist,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))

    if args.json_output:
        _write_json(report, args.json_output)
        if args.json_output != "-":
            _print_summary(report)
    else:
        _print_summary(report)

    summary = report["summary"]
    assert isinstance(summary, dict)
    if args.check and summary["status"] != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
