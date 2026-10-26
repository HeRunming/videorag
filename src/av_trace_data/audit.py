"""Hash-chained JSON Lines audit logging."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from urllib.parse import unquote, urlsplit
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .io import canonical_json

_GENESIS_HASH = "sha256:" + "0" * 64
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "headers",
    "password",
    "proxy_authorization",
    "secret",
    "token",
    "x_api_key",
    "x_auth_token",
}
_SENSITIVE_QUERY_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "awsaccesskeyid",
    "credential",
    "key",
    "password",
    "secret",
    "signature",
    "sig",
    "token",
    "x-amz-credential",
    "x-amz-security-token",
    "x-amz-signature",
    "x-goog-credential",
    "x-goog-signature",
}


def _assert_no_sensitive_fields(value: Any, path: str = "event") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _SENSITIVE_KEYS:
                raise ValueError(f"sensitive field cannot be written to audit log: {path}.{key}")
            _assert_no_sensitive_fields(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_no_sensitive_fields(nested, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.strip().lower()
        if lowered.startswith(("bearer ", "basic ")):
            raise ValueError(
                f"authorization material cannot be written to audit log: {path}"
            )
        if lowered.startswith(("http://", "https://")):
            try:
                parsed = urlsplit(value)
            except ValueError as exc:
                raise ValueError(f"malformed URL cannot be written to audit log: {path}") from exc
            if parsed.username is not None or parsed.password is not None:
                raise ValueError(
                    f"URL credentials cannot be written to audit log: {path}"
                )
            for field in parsed.query.split("&") if parsed.query else ():
                name = unquote(field.split("=", 1)[0]).strip().lower()
                if name in _SENSITIVE_QUERY_NAMES:
                    raise ValueError(
                        f"credential-like URL cannot be written to audit log: {path}"
                    )


def _entry_hash(body: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(body)).hexdigest()


def audit_event(event: str, **fields: Any) -> dict[str, Any]:
    value = {
        "audit_version": "2.0",
        "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
        **fields,
    }
    _assert_no_sensitive_fields(value)
    return value


def _parse_lines(payload: bytes) -> list[dict[str, Any]]:
    if not payload:
        return []
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("audit log is not valid UTF-8") from exc
    if not text.endswith("\n"):
        raise ValueError("audit log has a truncated final record")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"audit log line {line_number} is invalid JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f"audit log line {line_number} is not an object")
        records.append(record)
    return records


def _validate_checkpoint_value(
    expected_head_sha256: str | None,
    expected_record_count: int | None,
) -> tuple[str, int] | None:
    if expected_head_sha256 is None and expected_record_count is None:
        return None
    if expected_head_sha256 is None or expected_record_count is None:
        raise ValueError(
            "audit checkpoint requires both expected head and record count"
        )
    if (
        not isinstance(expected_record_count, int)
        or isinstance(expected_record_count, bool)
        or expected_record_count < 0
    ):
        raise ValueError("audit checkpoint record count must be a non-negative integer")
    head = str(expected_head_sha256).lower()
    if (
        len(head) != len(_GENESIS_HASH)
        or not head.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in head[7:])
    ):
        raise ValueError("audit checkpoint head must be a lowercase sha256 digest")
    return head, expected_record_count


def verify_audit_log(
    path: str | Path,
    *,
    expected_head_sha256: str | None = None,
    expected_record_count: int | None = None,
) -> dict[str, Any]:
    """Verify every chain link and, when supplied, an external checkpoint.

    A self-contained append-only file can detect edits to retained records, but
    cannot by itself prove that a valid suffix was not removed. Callers that
    need suffix completeness must supply an independently stored expected head
    and record count.
    """

    source = Path(path)
    checkpoint = _validate_checkpoint_value(
        expected_head_sha256, expected_record_count
    )
    if not source.exists():
        report = {
            "valid": True,
            "record_count": 0,
            "head_sha256": _GENESIS_HASH,
        }
    else:
        records = _parse_lines(source.read_bytes())
        previous = _GENESIS_HASH
        for index, record in enumerate(records):
            if record.get("audit_chain_version") != "1.0":
                raise ValueError(
                    f"audit record {index + 1} has an unsupported chain version"
                )
            if record.get("sequence") != index + 1:
                raise ValueError(f"audit record {index + 1} has an invalid sequence")
            if record.get("previous_entry_sha256") != previous:
                raise ValueError(f"audit record {index + 1} has a broken previous hash")
            expected = record.get("entry_sha256")
            body = dict(record)
            body.pop("entry_sha256", None)
            actual = _entry_hash(body)
            if expected != actual:
                raise ValueError(
                    f"audit record {index + 1} hash does not match its contents"
                )
            _assert_no_sensitive_fields(body)
            previous = actual
        report = {
            "valid": True,
            "record_count": len(records),
            "head_sha256": previous,
        }
    if checkpoint is not None:
        expected_head, expected_count = checkpoint
        if report["record_count"] != expected_count:
            raise ValueError("audit log record count does not match external checkpoint")
        if report["head_sha256"] != expected_head:
            raise ValueError("audit log chain head does not match external checkpoint")
        report["checkpoint_verified"] = True
    else:
        report["checkpoint_verified"] = False
    return report


def append_audit_log(path: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    """Append one fsync'd record after verifying the complete existing chain."""

    _assert_no_sensitive_fields(event)
    if {"entry_sha256", "previous_entry_sha256", "sequence"} & set(event):
        raise ValueError("caller must not supply audit-chain fields")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_APPEND | os.O_CREAT | os.O_RDWR
    descriptor = os.open(destination, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        os.lseek(descriptor, 0, os.SEEK_SET)
        records = _parse_lines(os.read(descriptor, os.fstat(descriptor).st_size))
        previous = _GENESIS_HASH
        for index, record in enumerate(records):
            if record.get("audit_chain_version") != "1.0":
                raise ValueError(
                    f"audit record {index + 1} has an unsupported chain version"
                )
            if record.get("sequence") != index + 1:
                raise ValueError(f"audit record {index + 1} has an invalid sequence")
            if record.get("previous_entry_sha256") != previous:
                raise ValueError(f"audit record {index + 1} has a broken previous hash")
            expected = record.get("entry_sha256")
            body = dict(record)
            body.pop("entry_sha256", None)
            actual = _entry_hash(body)
            if expected != actual:
                raise ValueError(
                    f"audit record {index + 1} hash does not match its contents"
                )
            _assert_no_sensitive_fields(body)
            previous = actual

        body = {
            **event,
            "audit_chain_version": "1.0",
            "sequence": len(records) + 1,
            "previous_entry_sha256": previous,
        }
        record = {**body, "entry_sha256": _entry_hash(body)}
        line = json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        os.write(descriptor, (line + "\n").encode("utf-8"))
        os.fsync(descriptor)
        return record
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
