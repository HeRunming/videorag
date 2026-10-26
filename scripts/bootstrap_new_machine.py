#!/usr/bin/env python3
"""Dry-run/check tooling for an AV-TRACE new-machine bootstrap.

The default action is read-only.  The script does not install packages, clone,
download, authenticate, read tokens, run models, move files, or rewrite
historical artifacts.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


DEFAULT_REBIND_MANIFEST = Path("data/migration/path_rebinding_manifest.json")
PACKAGE_GROUPS = {
    "pyproject_core": ("av", "jsonschema", "numpy", "Pillow"),
    "migration_and_acquisition": (
        "huggingface-hub",
        "httpx",
        "requests",
        "cryptography",
        "pytest",
    ),
    "media_optional": ("opencv-python", "pyarrow"),
    "model_runtime_optional": (
        "torch",
        "torchvision",
        "torchaudio",
        "transformers",
        "safetensors",
        "xgrammar",
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def run_probe(argv: list[str], timeout: int = 8) -> dict[str, Any]:
    executable = shutil.which(argv[0])
    if executable is None:
        return {"available": False, "path": None, "returncode": None, "first_line": None}
    try:
        result = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "available": False,
            "path": executable,
            "returncode": None,
            "first_line": f"{type(exc).__name__}: {exc}",
        }
    output = result.stdout or result.stderr
    return {
        "available": result.returncode == 0,
        "path": executable,
        "returncode": result.returncode,
        "first_line": output.splitlines()[0] if output else "",
    }


def package_inventory() -> dict[str, list[dict[str, Any]]]:
    inventory: dict[str, list[dict[str, Any]]] = {}
    for group, names in PACKAGE_GROUPS.items():
        items = []
        for name in names:
            try:
                version = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                version = None
            items.append({"distribution": name, "installed": version is not None, "version": version})
        inventory[group] = items
    return inventory


def pyproject_inventory(root: Path) -> dict[str, Any]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return {"present": False, "path": "pyproject.toml"}
    data = tomllib.loads(path.read_text())
    project = data.get("project", {})
    return {
        "present": True,
        "path": "pyproject.toml",
        "name": project.get("name"),
        "requires_python": project.get("requires-python"),
        "dependencies": project.get("dependencies", []),
        "build_requires": data.get("build-system", {}).get("requires", []),
    }


def system_inventory() -> dict[str, Any]:
    probes = {
        "git": run_probe(["git", "--version"]),
        "git_lfs": run_probe(["git", "lfs", "version"]),
        "ffmpeg": run_probe(["ffmpeg", "-version"]),
        "ffprobe": run_probe(["ffprobe", "-version"]),
        "nvidia_smi": run_probe(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ]
        ),
        "hf_cli": run_probe(["hf", "--version"]),
    }
    return {
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "supported_by_pyproject": sys.version_info >= (3, 11),
            "recommendation": "Prefer Python 3.11 or 3.12 for the broadest model-stack compatibility; pyproject requires >=3.11.",
        },
        "platform": platform.platform(),
        "executables": probes,
        "packages": package_inventory(),
    }


def _matches(path: str, pattern: str) -> bool:
    # fnmatch treats ** like *, so "/**/" would otherwise require at least one
    # intermediate component.  Also test the zero-component expansion.
    variants = {pattern}
    while "/**/" in pattern:
        pattern = pattern.replace("/**/", "/", 1)
        variants.add(pattern)
    return any(fnmatch.fnmatchcase(path, candidate) for candidate in variants)


def classify_path(path: str, manifest: dict[str, Any]) -> dict[str, Any] | None:
    for rule in manifest.get("rules", []):
        if any(_matches(path, pattern) for pattern in rule.get("patterns", [])):
            return rule
    return None


def scan_path_references(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    source_root = manifest["source_root"].encode()
    scan = manifest["scan"]
    suffixes = set(scan["text_suffixes"])
    skipped = set(scan["skip_directories"])
    max_bytes = int(scan["max_text_file_bytes"])
    findings: list[dict[str, Any]] = []
    skipped_large: list[str] = []

    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in skipped and not (directory_path / name).is_symlink()
        )
        for name in sorted(filenames):
            path = directory_path / name
            if path.suffix.lower() not in suffixes or path.is_symlink():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            relative = path.relative_to(root).as_posix()
            if size > max_bytes:
                skipped_large.append(relative)
                continue
            try:
                count = path.read_bytes().count(source_root)
            except OSError:
                continue
            if not count:
                continue
            rule = classify_path(relative, manifest)
            findings.append(
                {
                    "path": relative,
                    "occurrences": count,
                    "classification": rule["classification"] if rule else "unclassified",
                    "rule_id": rule["id"] if rule else None,
                    "rewrite_policy": rule.get("rewrite_policy") if rule else None,
                }
            )

    blocking = [
        item
        for item in findings
        if item["classification"] in {"public_code_blocker", "unclassified"}
    ]
    return {
        "source_root": manifest["source_root"],
        "finding_count": len(findings),
        "findings": findings,
        "blocking_findings": blocking,
        "skipped_large_text_candidates": skipped_large,
        "status": "BLOCKED" if blocking else "PASS",
        "mutations_performed": False,
    }


def command_plan(new_root: str, repo_url: str, python_command: str) -> dict[str, Any]:
    quoted_root = "'${AV_TRACE_ROOT}'"
    return {
        "dry_run": True,
        "network_performed": False,
        "tokens_read": False,
        "commands_executed": False,
        "environment_template": [
            f"export AV_TRACE_ROOT={json.dumps(new_root)}",
            f"export AV_TRACE_REPO_URL={json.dumps(repo_url)}",
            "export HF_HOME=\"$AV_TRACE_ROOT/data/restricted/_hf_home\"",
            "export HF_HUB_CACHE=\"$HF_HOME/hub\"",
            "export TRANSFORMERS_CACHE=\"$HF_HOME/transformers\"",
            "export HUGGINGFACE_HUB_TOKEN='${INJECT_FROM_SECRET_MANAGER}'",
            "# Optional site-specific proxy variables, intentionally blank:",
            "export HTTPS_PROXY=''",
            "export HTTP_PROXY=''",
            "export NO_PROXY=''",
        ],
        "phases": [
            {
                "name": "clone_without_lfs_payloads",
                "commands": [
                    "umask 077",
                    "GIT_LFS_SKIP_SMUDGE=1 git clone --filter=blob:none \"$AV_TRACE_REPO_URL\" \"$AV_TRACE_ROOT\"",
                    f"cd {quoted_root}",
                ],
            },
            {
                "name": "create_environment",
                "commands": [
                    f"{python_command} -m venv \"$AV_TRACE_ROOT/.venv\"",
                    "source \"$AV_TRACE_ROOT/.venv/bin/activate\"",
                    "python -m pip install --upgrade pip setuptools wheel",
                    "python -m pip install -e \"$AV_TRACE_ROOT\"",
                    "python -m pip install pytest huggingface-hub httpx requests cryptography",
                    "# Install torch/torchvision/torchaudio from the CUDA/CPU index selected for the new driver; do not copy this host's wheel cache blindly.",
                    "# Then install project-needed optional packages, e.g. transformers safetensors opencv-python pyarrow xgrammar.",
                ],
            },
            {
                "name": "secure_local_state",
                "commands": [
                    "install -d -m 0700 \"$AV_TRACE_ROOT/data/restricted\" \"$HF_HOME\" \"$HF_HUB_CACHE\" \"$TRANSFORMERS_CACHE\"",
                    "find \"$AV_TRACE_ROOT/data/restricted\" -type d -exec chmod 0700 {} +",
                    "find \"$AV_TRACE_ROOT/data/restricted\" -type f -exec chmod 0600 {} +",
                ],
            },
            {
                "name": "authenticate_after_secret_delivery",
                "commands": [
                    "gh auth login  # interactive; required only for a private GitHub origin",
                    "hf auth login  # paste through the hidden prompt; never put a token in shell history",
                    "hf auth whoami",
                ],
            },
            {
                "name": "read_only_checks",
                "commands": [
                    "python scripts/bootstrap_new_machine.py --mode check --repo-root \"$AV_TRACE_ROOT\" --format json",
                    "python scripts/verify_migration_readiness.py --repo-root \"$AV_TRACE_ROOT\" --hf-authenticated --json-output /tmp/av-trace-migration-readiness.json",
                ],
            },
        ],
        "operator_warning": "This is command text only. Review and run phases manually in order. Do not execute model/download commands until access and authorization are renewed.",
    }


def build_report(
    root: Path,
    manifest: dict[str, Any],
    *,
    mode: str,
    new_root: str,
    repo_url: str,
    python_command: str,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "av-trace.new-machine-bootstrap/1.0",
        "mode": mode,
        "dry_run": True,
        "repo_root": str(root),
        "safety": {
            "pip_install_performed": False,
            "network_performed": False,
            "token_read": False,
            "model_loaded": False,
            "files_moved": False,
            "paths_rewritten": False,
        },
        "pyproject": pyproject_inventory(root),
        "path_rebinding": scan_path_references(root, manifest),
        "command_plan": command_plan(new_root, repo_url, python_command),
    }
    if mode == "check":
        report["environment"] = system_inventory()
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_REBIND_MANIFEST)
    parser.add_argument("--mode", choices=("plan", "check"), default="plan")
    parser.add_argument("--new-root", default="${HOME}/src/AV-TRACE")
    parser.add_argument("--repo-url", default="git@github.com:ORG/AV-TRACE.git")
    parser.add_argument("--python-command", default="python3.11")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args(argv)


def print_text(report: dict[str, Any]) -> None:
    print("AV-TRACE new-machine bootstrap: DRY RUN")
    print("No install, network, token, model, move, or rewrite action was performed.")
    print(f"repo root: {report['repo_root']}")
    print(f"path rebinding: {report['path_rebinding']['status']}")
    print(f"absolute-root findings: {report['path_rebinding']['finding_count']}")
    if "environment" in report:
        py = report["environment"]["python"]
        print(f"python: {py['version']} ({'supported' if py['supported_by_pyproject'] else 'unsupported'})")
        for name, probe in report["environment"]["executables"].items():
            state = "OK" if probe["available"] else "MISSING/BLOCKED"
            print(f"{name}: {state} {probe['first_line'] or ''}".rstrip())
    print("\nSuggested commands (not executed):")
    for phase in report["command_plan"]["phases"]:
        print(f"\n# {phase['name']}")
        for command in phase["commands"]:
            print(command)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repo_root.resolve()
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    manifest = load_json(manifest_path)
    report = build_report(
        root,
        manifest,
        mode=args.mode,
        new_root=args.new_root,
        repo_url=args.repo_url,
        python_command=args.python_command,
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2) + "\n")
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print_text(report)
    return 1 if report["path_rebinding"]["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
