#!/usr/bin/env python3
"""Build a reproducible, audited public-repository snapshot outside the repo.

The source tree is never modified.  The default operation is a dry run.
``--execute`` creates a new empty staging directory using exclusive file
creation and never follows source symlinks.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import tokenize
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath

DEFAULT_DESTINATION = Path("/tmp/av-trace-public")
DEFAULT_LARGE_FILE_BYTES = 10 * 1024 * 1024
INDEX_FILES = {"PUBLIC_SNAPSHOT_MANIFEST.json", "SHA256SUMS"}
REWRITEABLE_CHECKS = {
    "absolute_machine_path",
    "internal_domain",
    "private_governance_id",
}
PYTHON_SANITIZED_TOKEN_TYPES = {
    tokenize.STRING,
    tokenize.COMMENT,
    getattr(tokenize, "FSTRING_MIDDLE", -1),
}
CACHE_DIRECTORY_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}
CACHE_FILE_SUFFIXES = {".pyc", ".pyo"}
PUBLIC_PROXY_EXAMPLE = "https://proxy.example.invalid:3128"
INTERNAL_PROXY_LABEL_PATTERNS = (
    (re.compile(r"(?i)(?<![A-Za-z0-9])star[-_. ]proxy"), "primary_proxy"),
    (re.compile(r"(?i)(?<![A-Za-z0-9])hy[-_. ]proxy"), "fallback_proxy"),
)


def _load_public_audit():
    path = Path(__file__).with_name("audit_public_release.py")
    spec = importlib.util.spec_from_file_location("_av_trace_public_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load public audit module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit_public_release = _load_public_audit()


@dataclass(frozen=True)
class PlannedFile:
    destination: str
    action: str
    source: str | None
    mode: int
    content: bytes
    reason: str

    @property
    def size_bytes(self) -> int:
        return len(self.content)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class PolicyDecision:
    path: str
    checks: tuple[str, ...]
    strategy: str
    reason: str
    destination: str | None = None


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _safe_relative_path(value: str) -> str:
    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or ".." in pure.parts
        or value != pure.as_posix()
    ):
        raise ValueError(
            "path must be a normalized repository-relative path: "
            f"{value!r}"
        )
    return value


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _source_components_are_not_symlinks(root: Path, relative: str) -> None:
    current = root
    for component in PurePosixPath(relative).parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"refusing to follow source symlink: {relative}")


def _read_regular_file(root: Path, relative: str) -> tuple[bytes, int]:
    relative = _safe_relative_path(relative)
    _source_components_are_not_symlinks(root, relative)
    path = root / relative
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
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


def _rewrite_text(text: str, checks: Iterable[str]) -> str:
    enabled = set(checks)
    if "internal_domain" in enabled:
        endpoint_pattern = audit_public_release.INTERNAL_DOMAIN_PATTERNS[0]
        text = endpoint_pattern.sub(PUBLIC_PROXY_EXAMPLE, text)
        for pattern, replacement in INTERNAL_PROXY_LABEL_PATTERNS:
            text = pattern.sub(replacement, text)
    if "absolute_machine_path" in enabled:
        for pattern in audit_public_release.ABSOLUTE_MACHINE_PATH_PATTERNS:
            text = pattern.sub("/path/to/av-trace", text)
    if "private_governance_id" in enabled:
        for pattern in audit_public_release.PRIVATE_GOVERNANCE_PATTERNS:
            text = pattern.sub("PUBLIC_REDACTED_IDENTIFIER", text)
    return text


def _rewrite_python_identifier(value: str) -> str:
    # Assemble the private identifier spellings so sanitizing this sanitizer
    # does not rewrite its own replacement table and become non-idempotent.
    private_primary_upper = "STAR" + "_PROXY"
    private_fallback_upper = "HY" + "_PROXY"
    private_primary_lower = "star" + "_proxy"
    private_fallback_lower = "hy" + "_proxy"
    rewritten = value.replace(private_primary_upper, "PRIMARY_PROXY")
    rewritten = rewritten.replace(private_fallback_upper, "FALLBACK_PROXY")
    rewritten = rewritten.replace(private_primary_lower, "primary_proxy")
    rewritten = rewritten.replace(private_fallback_lower, "fallback_proxy")
    return rewritten


def _sanitize_python(path: str, text: str, checks: Iterable[str]) -> str:
    try:
        ast.parse(text, filename=path)
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (SyntaxError, tokenize.TokenError) as error:
        raise ValueError(f"cannot safely sanitize invalid Python: {path}: {error}") from error
    enabled = set(checks)
    rewritten = []
    lines = text.splitlines(keepends=True)
    for token_info in tokens:
        token_text = token_info.string
        if "internal_domain" in enabled and token_info.type == tokenize.NAME:
            token_text = _rewrite_python_identifier(token_text)
        elif token_info.type in PYTHON_SANITIZED_TOKEN_TYPES:
            token_text = _rewrite_text(token_text, enabled)
        if (
            "private_governance_id" in enabled
            and token_info.type == tokenize.STRING
            and token_info.start[0] == token_info.end[0]
        ):
            line = lines[token_info.start[0] - 1]
            contextual = line[: token_info.start[1]] + token_info.string
            if any(
                pattern.search(contextual)
                for pattern in audit_public_release.PRIVATE_GOVERNANCE_PATTERNS
            ):
                prefix_length = len(token_info.string) - len(
                    token_info.string.lstrip("rRuUbBfF")
                )
                prefix = token_info.string[:prefix_length]
                token_text = prefix + repr("PUBLIC_REDACTED_IDENTIFIER")
        rewritten.append(token_info._replace(string=token_text))
    result = tokenize.untokenize(rewritten)
    try:
        ast.parse(result, filename=path)
    except SyntaxError as error:
        raise ValueError(
            f"Python sanitizer produced invalid syntax for {path}: {error}"
        ) from error
    return result


def _transform_json_strings(value: object, checks: Iterable[str]) -> object:
    if isinstance(value, str):
        return _rewrite_text(value, checks)
    if isinstance(value, list):
        return [_transform_json_strings(item, checks) for item in value]
    if isinstance(value, dict):
        transformed: dict[str, object] = {}
        for key, item in value.items():
            rewritten_key = _rewrite_text(str(key), checks)
            if rewritten_key in transformed:
                raise ValueError(
                    "JSON sanitization produced a duplicate object key: "
                    f"{rewritten_key!r}"
                )
            transformed[rewritten_key] = _transform_json_strings(item, checks)
        return transformed
    return value


def _sanitize_copy(path: str, content: bytes, checks: Iterable[str]) -> bytes:
    unsupported = set(checks) - REWRITEABLE_CHECKS
    if unsupported:
        raise ValueError(
            f"rewrite-copy cannot resolve {sorted(unsupported)} in {path}; "
            "use exclude or require-owner"
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"rewrite-copy requires UTF-8 text: {path}") from error

    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".py":
        rewritten = _sanitize_python(path, text, checks)
    elif suffix == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"cannot safely sanitize invalid JSON: {path}: {error}") from error
        rewritten = json.dumps(
            _transform_json_strings(parsed, checks),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ) + "\n"
        try:
            json.loads(rewritten)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"JSON sanitizer produced invalid JSON for {path}: {error}"
            ) from error
    else:
        rewritten = _rewrite_text(text, checks)
    return rewritten.encode("utf-8")


def sanitize_public_content(path: str, content: bytes) -> bytes:
    """Sanitize detected public-release blockers using the format-safe path."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    checks = {
        finding.check
        for finding in audit_public_release.scan_text(path, text)
        if finding.check in REWRITEABLE_CHECKS
    }
    return _sanitize_copy(path, content, checks) if checks else content


def _load_policy(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("public repository manifest must be a JSON object")
    if value.get("schema_version") != 1:
        raise ValueError("unsupported public repository manifest schema_version")
    rules = value.get("strategy_rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("manifest requires a non-empty strategy_rules array")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise TypeError(f"strategy_rules[{index}] must be an object")
        if rule.get("strategy") not in {
            "exclude",
            "redact-generated",
            "rewrite-copy",
            "require-owner",
        }:
            raise ValueError(f"strategy_rules[{index}] has an invalid strategy")
        for key in ("path", "reason"):
            if not isinstance(rule.get(key), str) or not str(rule[key]).strip():
                raise ValueError(f"strategy_rules[{index}] requires {key}")
    return value


def _matching_rule(
    rules: Sequence[Mapping[str, object]], path: str, checks: set[str]
) -> Mapping[str, object] | None:
    for rule in rules:
        pattern = str(rule["path"])
        if not fnmatch.fnmatchcase(path, pattern):
            continue
        configured_checks = rule.get("checks", ["*"])
        if not isinstance(configured_checks, list):
            raise TypeError(f"checks must be an array in rule for {pattern}")
        allowed = {str(item) for item in configured_checks}
        if "*" not in allowed and not checks <= allowed:
            continue
        return rule
    return None


def _source_summary(
    *, source_path: str, content: bytes, as_of_date: str
) -> bytes:
    return _json_bytes(
        {
            "schema_version": 1,
            "as_of_date": as_of_date,
            "artifact": "source exposure alias manifest v2 public commitment",
            "source_path": source_path,
            "source_size_bytes": len(content),
            "source_sha256": _sha256_bytes(content),
            "release_disposition": "SOURCE_FILE_EXCLUDED",
            "reason": (
                "The full source artifact is intentionally omitted from the public "
                "repository snapshot because it exceeds the default review threshold "
                "and contains detailed source-exposure governance records."
            ),
            "commitment": (
                "The hash commits to the reviewed local source artifact without "
                "redistributing its records. Publication requires a separate owner "
                "and governance decision."
            ),
        }
    )


def _license_marker(as_of_date: str) -> bytes:
    return (
        "LICENSE DECISION REQUIRED\n"
        f"As of: {as_of_date}\n\n"
        "This snapshot does not contain a repository-level software license and "
        "does not grant permission to copy, modify, or redistribute the code.\n"
        "Authorized owners must choose and supply the actual license text, then "
        "rebuild with --license-choice and --license-file.\n"
    ).encode()


def _planned_file_entry(item: PlannedFile) -> dict[str, object]:
    return {
        "path": item.destination,
        "source": item.source,
        "action": item.action,
        "reason": item.reason,
        "mode": f"{item.mode:04o}",
        "size_bytes": item.size_bytes,
        "sha256": item.sha256,
    }


def build_plan(
    root: Path,
    policy_path: Path,
    *,
    as_of_date: str,
    large_file_bytes: int,
    license_choice: str | None = None,
    license_file: Path | None = None,
) -> dict[str, object]:
    root = root.resolve()
    policy_path = policy_path.resolve()
    policy = _load_policy(policy_path)
    report = audit_public_release.audit_repository(
        root, large_file_bytes=large_file_bytes
    )
    rules = policy["strategy_rules"]
    assert isinstance(rules, list)

    planned: dict[str, PlannedFile] = {}
    decisions: list[PolicyDecision] = []
    owner_blockers: list[dict[str, str]] = []

    def add(item: PlannedFile) -> None:
        _safe_relative_path(item.destination)
        if item.destination in INDEX_FILES:
            raise ValueError(f"reserved snapshot index path: {item.destination}")
        if item.destination in planned:
            raise ValueError(f"duplicate snapshot destination: {item.destination}")
        planned[item.destination] = item

    for entry in report["release_ready_files"]:
        source = str(entry["path"])
        content, mode = _read_regular_file(root, source)
        add(
            PlannedFile(
                destination=source,
                action="copy",
                source=source,
                mode=mode,
                content=content,
                reason="provisional release-ready file from audit_public_release",
            )
        )

    blocked_by_path: dict[str, list[dict[str, object]]] = defaultdict(list)
    for finding in report["blockers"]:
        blocked_by_path[str(finding["path"])].append(finding)

    for path in sorted(blocked_by_path):
        checks = {str(item["check"]) for item in blocked_by_path[path]}
        rule = _matching_rule(rules, path, checks)
        if rule is None:
            owner_blockers.append(
                {
                    "kind": "unmapped_policy",
                    "path": path,
                    "detail": f"no strategy rule covers checks {sorted(checks)}",
                }
            )
            decisions.append(
                PolicyDecision(
                    path=path,
                    checks=tuple(sorted(checks)),
                    strategy="require-owner",
                    reason="No explicit strategy rule matched this blocked path.",
                )
            )
            continue

        strategy = str(rule["strategy"])
        reason = str(rule["reason"])
        destination_value = rule.get("replacement_path")
        destination = str(destination_value) if destination_value else None
        decisions.append(
            PolicyDecision(
                path=path,
                checks=tuple(sorted(checks)),
                strategy=strategy,
                reason=reason,
                destination=destination,
            )
        )

        if strategy == "exclude":
            continue
        if strategy == "require-owner":
            # The repository-global license finding is represented once below
            # as the code_license owner blocker and can be resolved through the
            # explicit --license-choice/--license-file interface.
            if not (path == "." and checks == {"license_boundary"}):
                owner_blockers.append(
                    {
                        "kind": "path_owner_review",
                        "path": path,
                        "detail": reason,
                    }
                )
            continue
        if path == ".":
            raise ValueError(f"{strategy} is not valid for repository-global blocker")

        content, mode = _read_regular_file(root, path)
        if strategy == "rewrite-copy":
            rewritten = _sanitize_copy(path, content, checks)
            add(
                PlannedFile(
                    destination=destination or path,
                    action=strategy,
                    source=path,
                    mode=mode,
                    content=rewritten,
                    reason=reason,
                )
            )
        elif strategy == "redact-generated":
            if not destination:
                raise ValueError(
                    "redact-generated rule requires replacement_path: "
                    f"{path}"
                )
            if path != "data/rehearsal_plan/source_exposure_alias_manifest_v2.json":
                raise ValueError(f"no redact-generated renderer is defined for {path}")
            add(
                PlannedFile(
                    destination=destination,
                    action=strategy,
                    source=path,
                    mode=0o644,
                    content=_source_summary(
                        source_path=path,
                        content=content,
                        as_of_date=as_of_date,
                    ),
                    reason=reason,
                )
            )

    required_copy_paths = policy.get("required_copy_paths", [])
    if not isinstance(required_copy_paths, list):
        raise TypeError("required_copy_paths must be an array")
    policy_relative: str | None = None
    try:
        policy_relative = policy_path.relative_to(root).as_posix()
    except ValueError:
        pass
    for value in required_copy_paths:
        source = _safe_relative_path(str(value))
        if source in planned:
            continue
        content, mode = _read_regular_file(root, source)
        content = sanitize_public_content(source, content)
        add(
            PlannedFile(
                destination=source,
                action="policy-required-copy",
                source=source,
                mode=mode,
                content=content,
                reason="required public migration metadata",
            )
        )
    if policy_relative and policy_relative not in planned:
        content, mode = _read_regular_file(root, policy_relative)
        add(
            PlannedFile(
                destination=policy_relative,
                action="policy-required-copy",
                source=policy_relative,
                mode=mode,
                content=content,
                reason="snapshot policy and explicit blocked-path strategy table",
            )
        )

    if (license_choice is None) != (license_file is None):
        raise ValueError(
            "--license-choice and --license-file must be supplied together"
        )
    if license_file is None:
        planned.pop("LICENSE", None)
        add(
            PlannedFile(
                destination="LICENSE_DECISION_REQUIRED",
                action="generated-license-blocker",
                source=None,
                mode=0o644,
                content=_license_marker(as_of_date),
                reason="repository-level code license has not been selected by owners",
            )
        )
        owner_blockers.append(
            {
                "kind": "code_license",
                "path": "LICENSE",
                "detail": (
                    "Authorized owners must choose a code license and rebuild with "
                    "--license-choice and --license-file."
                ),
            }
        )
    else:
        license_file = license_file.resolve()
        if license_file.is_symlink() or not license_file.is_file():
            raise ValueError("--license-file must be a non-symlink regular file")
        license_content = license_file.read_bytes()
        if not license_content.strip():
            raise ValueError("--license-file must not be empty")
        planned.pop("LICENSE_DECISION_REQUIRED", None)
        planned["LICENSE"] = PlannedFile(
            destination="LICENSE",
            action="owner-supplied-license",
            source=None,
            mode=stat.S_IMODE(license_file.stat().st_mode),
            content=license_content,
            reason=f"owner-supplied code license choice: {license_choice}",
        )
        owner_blockers = [
            item for item in owner_blockers if item["kind"] != "code_license"
        ]

    source_summary = report["summary"]
    assert isinstance(source_summary, dict)
    return {
        "policy": policy,
        "source_audit": report,
        "source_audit_summary": source_summary,
        "files": [planned[path] for path in sorted(planned)],
        "policy_decisions": decisions,
        "owner_blockers": owner_blockers,
        "license_choice": license_choice,
        "as_of_date": as_of_date,
        "large_file_bytes": large_file_bytes,
    }


def audit_contents(
    files: Mapping[str, bytes], *, large_file_bytes: int
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in sorted(files):
        content = files[path]
        if len(content) > large_file_bytes:
            findings.append(
                {
                    "check": "large_file",
                    "path": path,
                    "message": f"file exceeds {large_file_bytes}-byte threshold",
                }
            )
        sample = content[: audit_public_release.SAMPLE_BYTES]
        if audit_public_release.looks_binary(sample):
            findings.append(
                {
                    "check": "binary_file",
                    "path": path,
                    "message": "binary content is not allowed",
                }
            )
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(
                {
                    "check": "binary_file",
                    "path": path,
                    "message": "file is not valid UTF-8 text",
                }
            )
            continue
        findings.extend(
            asdict(item) for item in audit_public_release.scan_text(path, text)
        )
    return findings


def _python_ast_findings(files: Mapping[str, bytes]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path, content in sorted(files.items()):
        if not path.endswith(".py"):
            continue
        try:
            text = content.decode("utf-8")
            ast.parse(text, filename=path)
        except (UnicodeDecodeError, SyntaxError) as error:
            findings.append(
                {
                    "check": "python_ast",
                    "path": path,
                    "message": f"Python parse failed: {error}",
                }
            )
    return findings


def _cache_path_findings(paths: Iterable[str]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in sorted(paths):
        pure = PurePosixPath(path)
        if any(part in CACHE_DIRECTORY_NAMES for part in pure.parts) or (
            pure.suffix.lower() in CACHE_FILE_SUFFIXES
        ):
            findings.append(
                {
                    "check": "generated_cache",
                    "path": path,
                    "message": "generated cache/bytecode artifacts are forbidden",
                }
            )
    return findings


def _required_file_findings(
    files: Mapping[str, bytes], required_paths: Sequence[str]
) -> list[dict[str, object]]:
    return [
        {
            "check": "required_snapshot_file",
            "path": path,
            "message": "required snapshot file is missing",
        }
        for path in required_paths
        if path not in files
    ]


def _write_staging_tree(
    destination: Path, files: Mapping[str, PlannedFile]
) -> None:
    for relative, item in sorted(files.items()):
        pure = PurePosixPath(_safe_relative_path(relative))
        output = destination.joinpath(*pure.parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(item.content)
        output.chmod(item.mode)


def _run_focused_snapshot_tests(
    files: Mapping[str, PlannedFile], tests: Sequence[str]
) -> dict[str, object]:
    normalized = [_safe_relative_path(str(item)) for item in tests]
    if not normalized:
        return {
            "status": "PASS",
            "tests": [],
            "returncode": 0,
            "model_free": True,
        }
    missing = [path for path in normalized if path not in files]
    if missing:
        return {
            "status": "BLOCKED",
            "tests": normalized,
            "returncode": None,
            "model_free": True,
            "reason": f"focused snapshot tests are missing: {missing}",
        }
    with tempfile.TemporaryDirectory(prefix="av-trace-public-test-") as temporary:
        root = Path(temporary)
        _write_staging_tree(root, files)
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPYCACHEPREFIX"] = str(root / ".disabled-pycache")
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *normalized,
        ]
        completed = subprocess.run(
            command,
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        result: dict[str, object] = {
            "status": "PASS" if completed.returncode == 0 else "BLOCKED",
            "tests": normalized,
            "returncode": completed.returncode,
            "model_free": True,
        }
        if completed.returncode:
            result["tail"] = "\n".join(
                (completed.stdout + "\n" + completed.stderr).splitlines()[-80:]
            )
        return result


def _payload_quality_gates(
    plan: Mapping[str, object], payload_files: Mapping[str, PlannedFile]
) -> tuple[dict[str, object], list[dict[str, object]]]:
    contents = {path: item.content for path, item in payload_files.items()}
    policy = plan["policy"]
    assert isinstance(policy, dict)
    required_values = policy.get("required_snapshot_paths", [])
    if not isinstance(required_values, list):
        raise TypeError("required_snapshot_paths must be an array")
    required_paths = [_safe_relative_path(str(item)) for item in required_values]
    content_findings = audit_contents(
        contents, large_file_bytes=int(plan["large_file_bytes"])
    )
    ast_findings = _python_ast_findings(contents)
    cache_findings = _cache_path_findings(contents)
    required_findings = _required_file_findings(contents, required_paths)
    prerequisites_pass = not (
        content_findings + ast_findings + cache_findings + required_findings
    )
    configured_tests = policy.get("focused_snapshot_tests", [])
    if not isinstance(configured_tests, list):
        raise TypeError("focused_snapshot_tests must be an array")
    if prerequisites_pass:
        test_report = _run_focused_snapshot_tests(
            payload_files, [str(item) for item in configured_tests]
        )
    else:
        test_report = {
            "status": "BLOCKED",
            "tests": [str(item) for item in configured_tests],
            "returncode": None,
            "model_free": True,
            "reason": "focused tests were not run because prerequisite gates failed",
        }
    test_findings: list[dict[str, object]] = []
    if test_report["status"] != "PASS":
        test_findings.append(
            {
                "check": "focused_snapshot_tests",
                "path": ".",
                "message": str(
                    test_report.get("reason", "focused snapshot tests failed")
                ),
            }
        )
    findings = (
        content_findings
        + ast_findings
        + cache_findings
        + required_findings
        + test_findings
    )
    gates = {
        "content_audit": {
            "status": "PASS" if not content_findings else "BLOCKED",
            "finding_count": len(content_findings),
        },
        "python_ast": {
            "status": "PASS" if not ast_findings else "BLOCKED",
            "python_file_count": sum(path.endswith(".py") for path in contents),
            "finding_count": len(ast_findings),
        },
        "generated_artifacts": {
            "status": "PASS" if not cache_findings else "BLOCKED",
            "finding_count": len(cache_findings),
        },
        "required_snapshot_files": {
            "status": "PASS" if not required_findings else "BLOCKED",
            "required": required_paths,
            "finding_count": len(required_findings),
        },
        "focused_snapshot_tests": test_report,
    }
    return gates, findings


def _snapshot_manifest(
    plan: Mapping[str, object],
    payload: Sequence[PlannedFile],
    *,
    content_findings: Sequence[Mapping[str, object]],
    quality_gates: Mapping[str, object],
) -> dict[str, object]:
    owner_blockers = plan["owner_blockers"]
    assert isinstance(owner_blockers, list)
    content_ready = not content_findings
    has_license_blocker = any(
        item.get("kind") == "code_license" for item in owner_blockers
    )
    other_owner_blockers = any(
        item.get("kind") != "code_license" for item in owner_blockers
    )
    if not content_ready:
        release_status = "BLOCKED_CONTENT"
    elif other_owner_blockers:
        release_status = "BLOCKED_OWNER_REVIEW"
    elif has_license_blocker:
        release_status = "BLOCKED_LICENSE"
    else:
        release_status = "READY"

    decisions = plan["policy_decisions"]
    assert isinstance(decisions, list)
    source_summary = plan["source_audit_summary"]
    assert isinstance(source_summary, dict)
    return {
        "schema_version": 1,
        "as_of_date": plan["as_of_date"],
        "builder": "scripts/build_public_repo_snapshot.py",
        "git_independent": True,
        "release_status": release_status,
        "snapshot_content_ready": content_ready,
        "license_choice": plan["license_choice"],
        "source_audit_summary": {
            key: source_summary[key]
            for key in (
                "candidate_file_count",
                "candidate_bytes",
                "release_ready_file_count",
                "release_ready_bytes",
                "blocker_count",
                "blocked_candidate_path_count",
                "blockers_by_check",
            )
        },
        "snapshot_summary": {
            "payload_file_count": len(payload),
            "payload_bytes": sum(item.size_bytes for item in payload),
            "content_blocker_count": len(content_findings),
            "owner_blocker_count": len(owner_blockers),
        },
        "quality_gates": dict(quality_gates),
        "integrity": {
            "algorithm": "sha256",
            "index": "SHA256SUMS",
            "index_excludes": sorted(INDEX_FILES),
            "reason": "self-referential index files are intentionally not self-hashed",
        },
        "files": [_planned_file_entry(item) for item in payload],
        "policy_decisions": [asdict(item) for item in decisions],
        "content_blockers": list(content_findings),
        "owner_blockers": owner_blockers,
    }


def _assemble_snapshot_files(plan: Mapping[str, object]) -> dict[str, PlannedFile]:
    payload = plan["files"]
    assert isinstance(payload, list)
    payload_files = {item.destination: item for item in payload}
    quality_gates, preliminary_findings = _payload_quality_gates(
        plan, payload_files
    )
    manifest = _snapshot_manifest(
        plan,
        payload,
        content_findings=preliminary_findings,
        quality_gates=quality_gates,
    )
    manifest_bytes = _json_bytes(manifest)
    sums = "".join(
        f"{item.sha256}  {item.destination}\n" for item in payload
    ).encode("utf-8")
    assembled = dict(payload_files)
    assembled["SHA256SUMS"] = PlannedFile(
        destination="SHA256SUMS",
        action="generated-index",
        source=None,
        mode=0o644,
        content=sums,
        reason="SHA-256 index for all non-index snapshot files",
    )
    assembled["PUBLIC_SNAPSHOT_MANIFEST.json"] = PlannedFile(
        destination="PUBLIC_SNAPSHOT_MANIFEST.json",
        action="generated-index",
        source=None,
        mode=0o644,
        content=manifest_bytes,
        reason="snapshot provenance, policy decisions, hashes, and release status",
    )
    final_findings = audit_contents(
        {path: item.content for path, item in assembled.items()},
        large_file_bytes=int(plan["large_file_bytes"]),
    )
    final_findings.extend(
        _python_ast_findings(
            {path: item.content for path, item in assembled.items()}
        )
    )
    final_findings.extend(_cache_path_findings(assembled))
    if final_findings:
        merged = list(preliminary_findings)
        for finding in final_findings:
            if finding not in merged:
                merged.append(finding)
        quality_gates = dict(quality_gates)
        quality_gates["generated_index_audit"] = {
            "status": "BLOCKED",
            "finding_count": len(final_findings),
        }
        manifest = _snapshot_manifest(
            plan,
            payload,
            content_findings=merged,
            quality_gates=quality_gates,
        )
        assembled["PUBLIC_SNAPSHOT_MANIFEST.json"] = PlannedFile(
            destination="PUBLIC_SNAPSHOT_MANIFEST.json",
            action="generated-index",
            source=None,
            mode=0o644,
            content=_json_bytes(manifest),
            reason="snapshot provenance, policy decisions, hashes, and release status",
        )
    else:
        quality_gates = dict(quality_gates)
        quality_gates["generated_index_audit"] = {
            "status": "PASS",
            "finding_count": 0,
        }
        quality_gates["manifest_completeness"] = {
            "status": "PASS",
            "finding_count": 0,
            "definition": (
                "PUBLIC_SNAPSHOT_MANIFEST.json and SHA256SUMS are excluded "
                "from their own payload inventories"
            ),
        }
        manifest = _snapshot_manifest(
            plan,
            payload,
            content_findings=preliminary_findings,
            quality_gates=quality_gates,
        )
        assembled["PUBLIC_SNAPSHOT_MANIFEST.json"] = PlannedFile(
            destination="PUBLIC_SNAPSHOT_MANIFEST.json",
            action="generated-index",
            source=None,
            mode=0o644,
            content=_json_bytes(manifest),
            reason="snapshot provenance, policy decisions, hashes, and release status",
        )
    completeness = audit_snapshot_manifest_files(assembled)
    if completeness:
        raise ValueError(
            "generated snapshot manifest/index is incomplete: "
            + "; ".join(str(item["message"]) for item in completeness)
        )
    return assembled


def audit_snapshot_manifest_files(
    files: Mapping[str, PlannedFile | bytes],
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    try:
        manifest_item = files["PUBLIC_SNAPSHOT_MANIFEST.json"]
        sums_item = files["SHA256SUMS"]
    except KeyError as error:
        return [
            {
                "check": "manifest_completeness",
                "path": str(error.args[0]),
                "message": "required snapshot index file is missing",
            }
        ]
    content_for = (
        lambda value: value.content if isinstance(value, PlannedFile) else value
    )
    try:
        manifest = json.loads(content_for(manifest_item))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        return [
            {
                "check": "manifest_completeness",
                "path": "PUBLIC_SNAPSHOT_MANIFEST.json",
                "message": f"invalid snapshot manifest: {error}",
            }
        ]
    expected_payload = set(files) - INDEX_FILES
    rows = manifest.get("files")
    if not isinstance(rows, list):
        rows = []
        findings.append(
            {
                "check": "manifest_completeness",
                "path": "PUBLIC_SNAPSHOT_MANIFEST.json",
                "message": "manifest files field is not an array",
            }
        )
    manifest_paths = {
        str(row.get("path"))
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    if manifest_paths != expected_payload:
        findings.append(
            {
                "check": "manifest_completeness",
                "path": "PUBLIC_SNAPSHOT_MANIFEST.json",
                "message": (
                    f"manifest file set mismatch: missing="
                    f"{sorted(expected_payload - manifest_paths)}, extra="
                    f"{sorted(manifest_paths - expected_payload)}"
                ),
            }
        )
    sums_paths: set[str] = set()
    try:
        lines = content_for(sums_item).decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        lines = []
        findings.append(
            {
                "check": "manifest_completeness",
                "path": "SHA256SUMS",
                "message": f"invalid UTF-8 checksum index: {error}",
            }
        )
    for line in lines:
        digest, separator, path = line.partition("  ")
        if (
            not separator
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or path in sums_paths
        ):
            findings.append(
                {
                    "check": "manifest_completeness",
                    "path": "SHA256SUMS",
                    "message": f"invalid or duplicate checksum line: {line!r}",
                }
            )
            continue
        sums_paths.add(path)
        item = files.get(path)
        if item is None:
            continue
        if _sha256_bytes(content_for(item)) != digest:
            findings.append(
                {
                    "check": "manifest_completeness",
                    "path": path,
                    "message": "SHA256SUMS digest mismatch",
                }
            )
    if sums_paths != expected_payload:
        findings.append(
            {
                "check": "manifest_completeness",
                "path": "SHA256SUMS",
                "message": (
                    f"checksum file set mismatch: missing="
                    f"{sorted(expected_payload - sums_paths)}, extra="
                    f"{sorted(sums_paths - expected_payload)}"
                ),
            }
        )
    return findings


def _prepare_destination(destination: Path) -> None:
    if destination.is_symlink():
        raise ValueError(f"destination must not be a symlink: {destination}")
    if destination.exists():
        if not destination.is_dir():
            raise ValueError(
                f"destination exists and is not a directory: {destination}"
            )
        if any(destination.iterdir()):
            raise ValueError(
                "destination must be empty; refusing overwrite: "
                f"{destination}"
            )
    else:
        destination.mkdir(parents=True, mode=0o755)


def _validate_destination(root: Path, destination: Path) -> Path:
    absolute = Path(os.path.abspath(destination))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current = current / component
        if current.is_symlink():
            raise ValueError(
                f"destination path must not traverse a symlink: {current}"
            )
        if not current.exists():
            break

    resolved = absolute.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        return absolute
    raise ValueError(
        f"destination must be outside the source repository: {absolute}"
    )


def _ensure_destination_directory(
    destination: Path, relative_parent: PurePosixPath
) -> None:
    current = destination
    for component in relative_parent.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"refusing destination symlink: {current}")
        if current.exists():
            if not current.is_dir():
                raise ValueError(f"destination parent is not a directory: {current}")
        else:
            current.mkdir(mode=0o755)


def write_snapshot(destination: Path, files: Mapping[str, PlannedFile]) -> None:
    _prepare_destination(destination)
    for relative, item in sorted(files.items()):
        pure = PurePosixPath(_safe_relative_path(relative))
        _ensure_destination_directory(destination, pure.parent)
        output = destination.joinpath(*pure.parts)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(output, flags, item.mode)
        try:
            view = memoryview(item.content)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fchmod(descriptor, item.mode)
        finally:
            os.close(descriptor)


def audit_snapshot_directory(
    destination: Path, *, large_file_bytes: int
) -> list[dict[str, object]]:
    contents: dict[str, bytes] = {}
    findings: list[dict[str, object]] = []
    for current, directory_names, file_names in os.walk(
        destination, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(directory_names):
            path = current_path / name
            relative = path.relative_to(destination).as_posix()
            if path.is_symlink():
                findings.append(
                    {
                        "check": "symlink",
                        "path": relative,
                        "message": "snapshot directory symlink is not allowed",
                    }
                )
            else:
                kept.append(name)
        directory_names[:] = kept
        for name in sorted(file_names):
            path = current_path / name
            relative = path.relative_to(destination).as_posix()
            if path.is_symlink():
                findings.append(
                    {
                        "check": "symlink",
                        "path": relative,
                        "message": "snapshot file symlink is not allowed",
                    }
                )
                continue
            if not path.is_file():
                findings.append(
                    {
                        "check": "non_regular_file",
                        "path": relative,
                        "message": "snapshot entry is not a regular file",
                    }
                )
                continue
            contents[relative] = path.read_bytes()
    findings.extend(audit_contents(contents, large_file_bytes=large_file_bytes))
    findings.extend(_python_ast_findings(contents))
    findings.extend(_cache_path_findings(contents))
    findings.extend(audit_snapshot_manifest_files(contents))
    return findings


def _result(
    plan: Mapping[str, object],
    files: Mapping[str, PlannedFile],
    *,
    destination: Path,
    executed: bool,
) -> dict[str, object]:
    manifest = json.loads(files["PUBLIC_SNAPSHOT_MANIFEST.json"].content)
    action_counts = Counter(item.action for item in files.values())
    return {
        "schema_version": 1,
        "mode": "execute" if executed else "dry-run",
        "destination": str(destination),
        "release_status": manifest["release_status"],
        "snapshot_content_ready": manifest["snapshot_content_ready"],
        "snapshot_file_count": len(files),
        "snapshot_bytes": sum(item.size_bytes for item in files.values()),
        "actions": dict(sorted(action_counts.items())),
        "content_blocker_count": len(manifest["content_blockers"]),
        "owner_blockers": manifest["owner_blockers"],
        "policy_decision_count": len(manifest["policy_decisions"]),
    }


def _print_result(result: Mapping[str, object]) -> None:
    print(f"public snapshot:       {result['mode']}")
    print(f"destination:           {result['destination']}")
    print(f"release status:        {result['release_status']}")
    print(f"content ready:         {str(result['snapshot_content_ready']).lower()}")
    print(f"snapshot files:        {result['snapshot_file_count']}")
    print(f"snapshot bytes:        {result['snapshot_bytes']}")
    print(f"content blockers:      {result['content_blocker_count']}")
    owner_blockers = result["owner_blockers"]
    assert isinstance(owner_blockers, list)
    print(f"owner blockers:        {len(owner_blockers)}")
    for blocker in owner_blockers:
        print(f"  - {blocker['kind']}: {blocker['path']} — {blocker['detail']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="mixed source working tree (default: repository containing this script)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help=(
            "strategy manifest "
            "(default: ROOT/data/migration/public_repo_manifest.json)"
        ),
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=DEFAULT_DESTINATION,
        help=f"clean staging directory (default: {DEFAULT_DESTINATION})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="create the snapshot; default is a non-mutating dry run",
    )
    parser.add_argument(
        "--as-of-date",
        default=datetime.now().astimezone().date().isoformat(),
        help="date embedded in generated notices (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--large-file-bytes",
        type=int,
        default=DEFAULT_LARGE_FILE_BYTES,
        help=f"file review threshold (default: {DEFAULT_LARGE_FILE_BYTES})",
    )
    parser.add_argument(
        "--license-choice",
        help="owner-approved license identifier or decision label",
    )
    parser.add_argument(
        "--license-file",
        type=Path,
        help="owner-supplied actual license text; requires --license-choice",
    )
    parser.add_argument(
        "--json-output",
        help="write command result JSON to PATH or '-'",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        date.fromisoformat(args.as_of_date)
    except ValueError:
        parser.error("--as-of-date must be YYYY-MM-DD")
    if args.large_file_bytes <= 0:
        parser.error("--large-file-bytes must be positive")

    root = args.root.resolve()
    policy_path = (
        args.manifest.resolve()
        if args.manifest
        else root / "data" / "migration" / "public_repo_manifest.json"
    )
    try:
        plan = build_plan(
            root,
            policy_path,
            as_of_date=args.as_of_date,
            large_file_bytes=args.large_file_bytes,
            license_choice=args.license_choice,
            license_file=args.license_file,
        )
        files = _assemble_snapshot_files(plan)
        destination = _validate_destination(root, args.destination)
        if args.execute:
            write_snapshot(destination, files)
            disk_findings = audit_snapshot_directory(
                destination, large_file_bytes=args.large_file_bytes
            )
            expected_manifest = json.loads(
                files["PUBLIC_SNAPSHOT_MANIFEST.json"].content
            )
            if disk_findings != expected_manifest["content_blockers"]:
                raise ValueError(
                    "post-copy snapshot audit differs from the planned content audit"
                )
        result = _result(
            plan,
            files,
            destination=destination,
            executed=args.execute,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))

    if args.json_output:
        serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.json_output == "-":
            sys.stdout.write(serialized)
        else:
            output = Path(args.json_output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized, encoding="utf-8")
            _print_result(result)
    else:
        _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
