"""Command-line interface for AV-TRACE validation and synthetic replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from .manifest import GateProfile, validate_manifest_gate
from .schemas import SchemaRegistry
from .semantic import validate_family
from .trajectory import validate_action, validate_response, validate_trajectory
from .util import load_json


def _print(report: Any) -> int:
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="av-trace", description="Validate AV-TRACE Pilot-0 synthetic artifacts.")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository root containing docs/spec.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("schemas", help="Check all normative JSON schemas.")

    schema = sub.add_parser("schema", help="Validate one JSON instance against a named schema.")
    schema.add_argument("schema_name", choices=sorted({"episode-family", "agent-action", "tool-response", "final-answer", "trajectory", "acquisition-manifest"}))
    schema.add_argument("path", type=Path)

    manifest = sub.add_parser("manifest", help="Validate a manifest and a fail-closed gate.")
    manifest.add_argument("path", type=Path)
    manifest.add_argument("--gate", choices=[item.value for item in GateProfile], required=True)

    family = sub.add_parser("family", help="Validate an episode family structurally and semantically.")
    family.add_argument("path", type=Path)
    family.add_argument("--manifest", type=Path, required=True)

    for command in ("action", "response", "trajectory"):
        item = sub.add_parser(command, help=f"Validate one {command} JSON artifact.")
        item.add_argument("path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        registry = SchemaRegistry(args.repo_root)
        def input_path(path: Path) -> Path:
            if path.is_absolute() or args.repo_root is None:
                return path
            return args.repo_root / path
        if args.command == "schemas":
            return _print(registry.check_schemas())
        if args.command == "schema":
            return _print(registry.validate(args.schema_name, load_json(input_path(args.path))))
        if args.command == "manifest":
            return _print(validate_manifest_gate(load_json(input_path(args.path)), args.gate, registry))
        if args.command == "family":
            return _print(validate_family(load_json(input_path(args.path)), load_json(input_path(args.manifest)), registry))
        validators: dict[str, Callable[..., Any]] = {
            "action": validate_action,
            "response": validate_response,
            "trajectory": validate_trajectory,
        }
        return _print(validators[args.command](load_json(input_path(args.path)), registry))
    except (OSError, json.JSONDecodeError, KeyError, ValueError, RecursionError) as exc:
        print(json.dumps({"status": "FAIL", "issues": [{"code": "CLI-INPUT", "pointer": "", "message": str(exc), "severity": "error"}]}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
