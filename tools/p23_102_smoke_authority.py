#!/usr/bin/env python3
"""Strict local Ed25519 authorities for the P23_102 technical smoke.

This tool creates keys and verifies cryptographic review receipts.  It does
not run the smoke, modify its frozen inputs, or infer authorization from a
successful test or hash check.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_ROOT = REPO_ROOT / "data/restricted/p23_102_technical_smoke_v2"
DEFAULT_REGISTRY = SMOKE_ROOT / "authority_registry.json"
DEFAULT_AUTHORITIES_ROOT = SMOKE_ROOT / "authorities"

ROLES = ("live_wiring_reviewer", "red_team_reviewer")
DEFAULT_ROLE_PRIVATE_ROOTS = {
    role: DEFAULT_AUTHORITIES_ROOT / role for role in ROLES
}
REGISTRY_SCHEMA = "av-trace.p23-102-smoke-authority-registry/1.0"
RECEIPT_REQUEST_SCHEMA = (
    "av-trace.p23-102-smoke-review-receipt-request/1.0"
)
SIGNED_PAYLOAD_SCHEMA = (
    "av-trace.p23-102-smoke-review-signed-payload/1.0"
)
RECEIPT_SCHEMA = "av-trace.p23-102-smoke-review-receipt/1.0"
OVERLAY_SCHEMA = "av-trace.p23-102-smoke-approval-overlay/1.0"
ALGORITHM = "Ed25519"
REGISTRY_ID = "P23_102_TECHNICAL_SMOKE_V2_AUTHORITY_REGISTRY"
MAX_RECEIPT_VALIDITY_SECONDS = 900
MAX_OVERLAY_VALIDITY_SECONDS = 900

HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{7,127}$")
NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?Z$"
)

BINDING_FIELDS = {
    "freeze_sha256",
    "adapter_attestation_sha256",
    "runner_sha256",
    "repaired_runner_sha256",
    "module_set_sha256",
    "all_model_set_sha256",
    "assignment_plan_sha256",
    "checkpoint_contract_sha256",
    "output_root_sha256",
}
DECLARATION_FIELDS = {
    "technical_smoke_only",
    "no_scientific_interpretation",
    "no_competence_or_performance_interpretation",
    "single_run_only",
    "immutable_freeze_remains_unauthorized",
}


class AuthorityError(RuntimeError):
    """A typed fail-closed authority error."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


def canonical_bytes(value: Any) -> bytes:
    """Return the sole signed JSON representation."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AuthorityError("NON_CANONICAL_JSON", str(exc)) from exc


def semantic_hash(value: Any) -> str:
    """Hash a value using the canonical signed JSON representation."""

    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _reject_duplicate_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthorityError("DUPLICATE_JSON_KEY", key)
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise AuthorityError("NON_CANONICAL_JSON", value)


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object while rejecting duplicates and non-finite values."""

    if path.is_symlink():
        raise AuthorityError("SYMLINK_REJECTED", str(path))
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(
                handle,
                object_pairs_hook=_reject_duplicate_pairs,
                parse_constant=_reject_constant,
            )
    except AuthorityError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuthorityError("INVALID_JSON", f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuthorityError("INVALID_SCHEMA", f"{path}: object required")
    return value


def _exact_keys(
    value: Any,
    expected: set[str],
    location: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AuthorityError(
            "INVALID_SCHEMA", f"{location}: object required"
        )
    actual = set(value)
    if actual != expected:
        raise AuthorityError(
            "INVALID_SCHEMA",
            f"{location}: expected={sorted(expected)} "
            f"actual={sorted(str(item) for item in actual)}",
        )
    if any(not isinstance(key, str) for key in value):
        raise AuthorityError(
            "INVALID_SCHEMA", f"{location}: string keys required"
        )
    return value


def _require_id(value: Any, location: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise AuthorityError("INVALID_SCHEMA", location)
    return value


def _require_hash(value: Any, location: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise AuthorityError("INVALID_SCHEMA", location)
    return value


def _parse_utc(value: Any, location: str) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise AuthorityError("INVALID_TIME", location)
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise AuthorityError("INVALID_TIME", location) from exc
    if parsed.utcoffset() != dt.timedelta(0):
        raise AuthorityError("INVALID_TIME", location)
    return parsed


def utc_text(value: dt.datetime | None = None) -> str:
    """Serialize a UTC time in the accepted canonical form."""

    current = value or dt.datetime.now(dt.UTC)
    if current.tzinfo is None or current.utcoffset() != dt.timedelta(0):
        raise AuthorityError("INVALID_TIME", "UTC required")
    return current.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _require_regular_file(path: Path, mode: int, code: str) -> None:
    try:
        status = path.lstat()
    except OSError as exc:
        raise AuthorityError(code, f"{path}: {exc}") from exc
    if not stat.S_ISREG(status.st_mode) or path.is_symlink():
        raise AuthorityError(code, f"{path}: regular non-symlink required")
    actual = stat.S_IMODE(status.st_mode)
    if actual != mode:
        raise AuthorityError(
            code, f"{path}: mode {actual:04o}, expected {mode:04o}"
        )


def _require_directory(path: Path, mode: int, code: str) -> None:
    try:
        status = path.lstat()
    except OSError as exc:
        raise AuthorityError(code, f"{path}: {exc}") from exc
    if not stat.S_ISDIR(status.st_mode) or path.is_symlink():
        raise AuthorityError(code, f"{path}: non-symlink directory required")
    actual = stat.S_IMODE(status.st_mode)
    if actual != mode:
        raise AuthorityError(
            code, f"{path}: mode {actual:04o}, expected {mode:04o}"
        )


def _cryptography_api() -> tuple[Any, Any, Any] | None:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError:
        return None
    return serialization, ed25519, InvalidSignature


def _run_openssl(
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
    failure_code: str,
) -> bytes:
    executable = shutil.which("openssl")
    if executable is None:
        raise AuthorityError(
            "CRYPTO_BACKEND_UNAVAILABLE",
            "cryptography and openssl are unavailable",
        )
    try:
        completed = subprocess.run(
            [executable, *arguments],
            input=input_bytes,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise AuthorityError(failure_code, str(exc)) from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise AuthorityError(failure_code, detail)
    return completed.stdout


def _generate_keypair() -> tuple[bytes, bytes]:
    api = _cryptography_api()
    if api is not None:
        serialization, ed25519, _ = api
        private = ed25519.Ed25519PrivateKey.generate()
        private_pem = private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return private_pem, public_pem
    private_pem = _run_openssl(
        ["genpkey", "-algorithm", "ED25519"],
        failure_code="KEY_GENERATION_FAILED",
    )
    public_pem = _run_openssl(
        ["pkey", "-pubout"],
        input_bytes=private_pem,
        failure_code="KEY_GENERATION_FAILED",
    )
    return private_pem, public_pem


def _public_from_private(private_pem: bytes) -> bytes:
    api = _cryptography_api()
    if api is not None:
        serialization, ed25519, _ = api
        try:
            private = serialization.load_pem_private_key(
                private_pem, password=None
            )
        except (TypeError, ValueError) as exc:
            raise AuthorityError("INVALID_PRIVATE_KEY", str(exc)) from exc
        if not isinstance(private, ed25519.Ed25519PrivateKey):
            raise AuthorityError("INVALID_PRIVATE_KEY", "Ed25519 required")
        return private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    return _run_openssl(
        ["pkey", "-pubout"],
        input_bytes=private_pem,
        failure_code="INVALID_PRIVATE_KEY",
    )


def _public_der(public_pem: bytes) -> bytes:
    api = _cryptography_api()
    if api is not None:
        serialization, ed25519, _ = api
        try:
            public = serialization.load_pem_public_key(public_pem)
        except (TypeError, ValueError) as exc:
            raise AuthorityError("INVALID_PUBLIC_KEY", str(exc)) from exc
        if not isinstance(public, ed25519.Ed25519PublicKey):
            raise AuthorityError("INVALID_PUBLIC_KEY", "Ed25519 required")
        return public.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    return _run_openssl(
        ["pkey", "-pubin", "-outform", "DER"],
        input_bytes=public_pem,
        failure_code="INVALID_PUBLIC_KEY",
    )


def key_fingerprint(public_pem: bytes) -> str:
    """Fingerprint the DER SubjectPublicKeyInfo representation."""

    return "sha256:" + hashlib.sha256(_public_der(public_pem)).hexdigest()


def _sign(private_pem: bytes, message: bytes) -> bytes:
    api = _cryptography_api()
    if api is not None:
        serialization, ed25519, _ = api
        try:
            private = serialization.load_pem_private_key(
                private_pem, password=None
            )
        except (TypeError, ValueError) as exc:
            raise AuthorityError("INVALID_PRIVATE_KEY", str(exc)) from exc
        if not isinstance(private, ed25519.Ed25519PrivateKey):
            raise AuthorityError("INVALID_PRIVATE_KEY", "Ed25519 required")
        return private.sign(message)

    with tempfile.TemporaryDirectory(prefix="p23-auth-sign-") as directory:
        private_path = Path(directory) / "private.pem"
        private_path.write_bytes(private_pem)
        os.chmod(private_path, 0o600)
        return _run_openssl(
            [
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(private_path),
            ],
            input_bytes=message,
            failure_code="SIGNATURE_CREATION_FAILED",
        )


def _verify(public_pem: bytes, message: bytes, signature: bytes) -> bool:
    api = _cryptography_api()
    if api is not None:
        serialization, ed25519, invalid_signature = api
        try:
            public = serialization.load_pem_public_key(public_pem)
        except (TypeError, ValueError) as exc:
            raise AuthorityError("INVALID_PUBLIC_KEY", str(exc)) from exc
        if not isinstance(public, ed25519.Ed25519PublicKey):
            raise AuthorityError("INVALID_PUBLIC_KEY", "Ed25519 required")
        try:
            public.verify(signature, message)
        except invalid_signature:
            return False
        return True

    with tempfile.TemporaryDirectory(prefix="p23-auth-verify-") as directory:
        root = Path(directory)
        public_path = root / "public.pem"
        signature_path = root / "signature.bin"
        public_path.write_bytes(public_pem)
        signature_path.write_bytes(signature)
        os.chmod(public_path, 0o600)
        os.chmod(signature_path, 0o600)
        executable = shutil.which("openssl")
        if executable is None:
            raise AuthorityError(
                "CRYPTO_BACKEND_UNAVAILABLE",
                "cryptography and openssl are unavailable",
            )
        completed = subprocess.run(
            [
                executable,
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(public_path),
                "-rawin",
                "-sigfile",
                str(signature_path),
            ],
            input=message,
            capture_output=True,
            check=False,
        )
        return completed.returncode == 0


def _normalize_public_pem(public_pem: bytes) -> str:
    der = _public_der(public_pem)
    api = _cryptography_api()
    if api is not None:
        serialization, _, _ = api
        public = serialization.load_der_public_key(der)
        normalized = public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    else:
        normalized = _run_openssl(
            ["pkey", "-pubin", "-pubout"],
            input_bytes=public_pem,
            failure_code="INVALID_PUBLIC_KEY",
        )
    return normalized.decode("ascii")


def _authority_record(role: str, public_pem: bytes) -> dict[str, Any]:
    fingerprint = key_fingerprint(public_pem)
    return {
        "role": role,
        "authority_id": f"p23_102.{role}.{fingerprint[7:23]}",
        "key_fingerprint": fingerprint,
        "algorithm": ALGORITHM,
        "public_key_pem": _normalize_public_pem(public_pem),
    }


def _registry_document(
    records: list[dict[str, Any]],
    *,
    generated_at: dt.datetime,
) -> dict[str, Any]:
    return {
        "schema_version": REGISTRY_SCHEMA,
        "registry_id": REGISTRY_ID,
        "generated_at_utc": utc_text(generated_at),
        "algorithm": ALGORITHM,
        "roles": list(ROLES),
        "authorities": records,
        "policy": {
            "exact_role_allowlist": True,
            "distinct_authority_ids_required": True,
            "distinct_public_keys_required": True,
            "receipt_max_validity_seconds": MAX_RECEIPT_VALIDITY_SECONDS,
            "overlay_max_validity_seconds": MAX_OVERLAY_VALIDITY_SECONDS,
            "review_decision": "GO",
            "technical_smoke_only": True,
        },
    }


def validate_registry(value: Any) -> dict[str, dict[str, Any]]:
    """Validate and index the exact two-authority public registry."""

    record = _exact_keys(
        value,
        {
            "schema_version",
            "registry_id",
            "generated_at_utc",
            "algorithm",
            "roles",
            "authorities",
            "policy",
        },
        "registry",
    )
    if record["schema_version"] != REGISTRY_SCHEMA:
        raise AuthorityError("REGISTRY_INVALID", "schema_version")
    if record["registry_id"] != REGISTRY_ID:
        raise AuthorityError("REGISTRY_INVALID", "registry_id")
    _parse_utc(record["generated_at_utc"], "registry.generated_at_utc")
    if record["algorithm"] != ALGORITHM:
        raise AuthorityError("REGISTRY_INVALID", "algorithm")
    if record["roles"] != list(ROLES):
        raise AuthorityError("REGISTRY_INVALID", "roles")
    policy = _exact_keys(
        record["policy"],
        {
            "exact_role_allowlist",
            "distinct_authority_ids_required",
            "distinct_public_keys_required",
            "receipt_max_validity_seconds",
            "overlay_max_validity_seconds",
            "review_decision",
            "technical_smoke_only",
        },
        "registry.policy",
    )
    expected_policy = {
        "exact_role_allowlist": True,
        "distinct_authority_ids_required": True,
        "distinct_public_keys_required": True,
        "receipt_max_validity_seconds": MAX_RECEIPT_VALIDITY_SECONDS,
        "overlay_max_validity_seconds": MAX_OVERLAY_VALIDITY_SECONDS,
        "review_decision": "GO",
        "technical_smoke_only": True,
    }
    if dict(policy) != expected_policy:
        raise AuthorityError("REGISTRY_INVALID", "policy")
    authorities = record["authorities"]
    if not isinstance(authorities, list) or len(authorities) != len(ROLES):
        raise AuthorityError("REGISTRY_INVALID", "authorities")
    by_role: dict[str, dict[str, Any]] = {}
    authority_ids: set[str] = set()
    fingerprints: set[str] = set()
    public_ders: set[bytes] = set()
    for index, raw_authority in enumerate(authorities):
        authority = _exact_keys(
            raw_authority,
            {
                "role",
                "authority_id",
                "key_fingerprint",
                "algorithm",
                "public_key_pem",
            },
            f"registry.authorities[{index}]",
        )
        role = authority["role"]
        if role not in ROLES or role in by_role:
            raise AuthorityError("REGISTRY_INVALID", f"role:{role}")
        authority_id = _require_id(
            authority["authority_id"], f"{role}.authority_id"
        )
        fingerprint = _require_hash(
            authority["key_fingerprint"], f"{role}.key_fingerprint"
        )
        if authority["algorithm"] != ALGORITHM:
            raise AuthorityError("REGISTRY_INVALID", f"{role}.algorithm")
        public_text = authority["public_key_pem"]
        if not isinstance(public_text, str):
            raise AuthorityError("REGISTRY_INVALID", f"{role}.public_key_pem")
        try:
            public_pem = public_text.encode("ascii")
        except UnicodeEncodeError as exc:
            raise AuthorityError(
                "REGISTRY_INVALID", f"{role}.public_key_pem"
            ) from exc
        normalized = _normalize_public_pem(public_pem)
        if normalized != public_text:
            raise AuthorityError(
                "REGISTRY_INVALID", f"{role}.public_key_pem not normalized"
            )
        actual_fingerprint = key_fingerprint(public_pem)
        if fingerprint != actual_fingerprint:
            raise AuthorityError(
                "REGISTRY_INVALID", f"{role}.key_fingerprint mismatch"
            )
        expected_id = f"p23_102.{role}.{fingerprint[7:23]}"
        if authority_id != expected_id:
            raise AuthorityError(
                "REGISTRY_INVALID", f"{role}.authority_id mismatch"
            )
        public_der = _public_der(public_pem)
        if (
            authority_id in authority_ids
            or fingerprint in fingerprints
            or public_der in public_ders
        ):
            raise AuthorityError("REGISTRY_INDEPENDENCE_INVALID")
        authority_ids.add(authority_id)
        fingerprints.add(fingerprint)
        public_ders.add(public_der)
        copied = dict(authority)
        by_role[role] = copied
    if tuple(by_role) != ROLES:
        raise AuthorityError("REGISTRY_INVALID", "authority order")
    return by_role


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, dict[str, Any]]:
    _require_regular_file(path, 0o644, "REGISTRY_FILE_INVALID")
    return validate_registry(load_json(path))


def _write_exclusive(path: Path, payload: bytes, mode: int) -> None:
    if path.is_symlink():
        raise AuthorityError("SYMLINK_REJECTED", str(path))
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            mode,
        )
    except OSError as exc:
        raise AuthorityError("EXCLUSIVE_WRITE_FAILED", f"{path}: {exc}") from exc
    try:
        written = 0
        while written < len(payload):
            amount = os.write(descriptor, payload[written:])
            if amount <= 0:
                raise AuthorityError("EXCLUSIVE_WRITE_FAILED", str(path))
            written += amount
        os.fsync(descriptor)
        os.fchmod(descriptor, mode)
    except BaseException:
        os.close(descriptor)
        path.unlink(missing_ok=True)
        raise
    else:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def private_key_path(authorities_root: Path, role: str) -> Path:
    """Return a key path in the legacy shared provisioning layout."""

    if role not in ROLES:
        raise AuthorityError("ROLE_NOT_ALLOWED", role)
    return authorities_root / role / "private_key.pem"


def default_role_private_root(role: str) -> Path:
    """Return the selected role's default independent custody root."""

    if role not in ROLES:
        raise AuthorityError("ROLE_NOT_ALLOWED", role)
    return DEFAULT_ROLE_PRIVATE_ROOTS[role]


def _resolve_role_private_key(
    role: str,
    *,
    authorities_root: Path | None,
    private_root: Path | None,
    private_key: Path | None,
) -> tuple[Path, Path]:
    locations = [
        authorities_root is not None,
        private_root is not None,
        private_key is not None,
    ]
    if sum(locations) > 1:
        raise AuthorityError(
            "PRIVATE_KEY_LOCATION_INVALID",
            "choose only one of authorities_root, private_root, or "
            "private_key",
        )
    if private_key is not None:
        return private_key.parent, private_key
    if private_root is not None:
        return private_root, private_root / "private_key.pem"
    if authorities_root is not None:
        root = authorities_root / role
        return root, root / "private_key.pem"
    root = default_role_private_root(role)
    return root, root / "private_key.pem"


def _load_role_private_key(
    registry: Mapping[str, Mapping[str, Any]],
    role: str,
    *,
    private_root: Path,
    private_key: Path,
) -> bytes:
    """Load and validate exactly one role's private key."""

    _require_directory(
        private_root, 0o700, "PRIVATE_DIRECTORY_INVALID"
    )
    _require_regular_file(
        private_key, 0o600, "PRIVATE_KEY_FILE_INVALID"
    )
    try:
        private_pem = private_key.read_bytes()
    except OSError as exc:
        raise AuthorityError("PRIVATE_KEY_FILE_INVALID", str(exc)) from exc
    public_pem = _public_from_private(private_pem)
    fingerprint = key_fingerprint(public_pem)
    if fingerprint != registry[role]["key_fingerprint"]:
        raise AuthorityError("PRIVATE_KEY_REGISTRY_MISMATCH", role)
    return private_pem


def _validate_existing_private_keys(
    registry: dict[str, dict[str, Any]],
    authorities_root: Path,
) -> None:
    _require_directory(
        authorities_root, 0o700, "PRIVATE_DIRECTORY_INVALID"
    )
    derived: set[str] = set()
    for role in ROLES:
        role_root = authorities_root / role
        path = private_key_path(authorities_root, role)
        private_pem = _load_role_private_key(
            registry,
            role,
            private_root=role_root,
            private_key=path,
        )
        public_pem = _public_from_private(private_pem)
        derived.add(key_fingerprint(public_pem))
    if len(derived) != len(ROLES):
        raise AuthorityError("REGISTRY_INDEPENDENCE_INVALID")


def initialize_authorities(
    *,
    registry_path: Path = DEFAULT_REGISTRY,
    authorities_root: Path = DEFAULT_AUTHORITIES_ROOT,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Create both authorities once, or validate an exact complete state."""

    registry_exists = registry_path.exists() or registry_path.is_symlink()
    root_exists = authorities_root.exists() or authorities_root.is_symlink()
    if registry_exists or root_exists:
        if not (registry_exists and root_exists):
            raise AuthorityError(
                "PARTIAL_AUTHORITY_STATE",
                "registry and private authority root must both exist",
            )
        registry = load_registry(registry_path)
        _validate_existing_private_keys(registry, authorities_root)
        return {
            "status": "AUTHORITIES_ALREADY_INITIALIZED",
            "registry": str(registry_path),
            "roles": list(ROLES),
        }

    parent = registry_path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise AuthorityError(
            "AUTHORITY_PARENT_INVALID",
            f"{parent}: existing non-symlink directory required",
        )
    if authorities_root.parent.resolve() != parent.resolve():
        raise AuthorityError(
            "AUTHORITY_LAYOUT_INVALID",
            "registry and authorities must share a parent",
        )

    generated: dict[str, tuple[bytes, dict[str, Any]]] = {}
    for role in ROLES:
        private_pem, public_pem = _generate_keypair()
        generated[role] = (
            private_pem,
            _authority_record(role, public_pem),
        )
    if len(
        {
            item[1]["key_fingerprint"]
            for item in generated.values()
        }
    ) != len(ROLES):
        raise AuthorityError("KEY_GENERATION_NOT_INDEPENDENT")

    created_paths: list[Path] = []
    old_umask = os.umask(0o077)
    try:
        os.mkdir(authorities_root, 0o700)
        created_paths.append(authorities_root)
        for role in ROLES:
            role_root = authorities_root / role
            os.mkdir(role_root, 0o700)
            created_paths.append(role_root)
            key_path = private_key_path(authorities_root, role)
            _write_exclusive(key_path, generated[role][0], 0o600)
            created_paths.append(key_path)
            _fsync_directory(role_root)
        registry_document = _registry_document(
            [generated[role][1] for role in ROLES],
            generated_at=now or _now_utc(),
        )
        validate_registry(registry_document)
        registry_payload = (
            json.dumps(
                registry_document,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
        _write_exclusive(registry_path, registry_payload, 0o644)
        created_paths.append(registry_path)
        _fsync_directory(authorities_root)
        _fsync_directory(parent)
        registry = load_registry(registry_path)
        _validate_existing_private_keys(registry, authorities_root)
    except BaseException:
        for path in reversed(created_paths):
            try:
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        os.umask(old_umask)
    return {
        "status": "AUTHORITIES_INITIALIZED",
        "registry": str(registry_path),
        "roles": list(ROLES),
    }


def _validate_bindings(value: Any) -> dict[str, str]:
    record = _exact_keys(value, BINDING_FIELDS, "bound_execution.bindings")
    return {
        field: _require_hash(record[field], f"bindings.{field}")
        for field in sorted(BINDING_FIELDS)
    }


def _validate_declarations(value: Any) -> dict[str, bool]:
    record = _exact_keys(
        value, DECLARATION_FIELDS, "bound_execution.declarations"
    )
    if any(record[field] is not True for field in DECLARATION_FIELDS):
        raise AuthorityError("DECLARATION_MISSING")
    return {field: True for field in sorted(DECLARATION_FIELDS)}


def validate_bound_execution(value: Any) -> dict[str, Any]:
    """Validate the exact execution subject shared by both reviewers."""

    record = _exact_keys(
        value,
        {
            "bindings",
            "one_run_nonce",
            "declarations",
            "review_decision",
        },
        "bound_execution",
    )
    nonce = record["one_run_nonce"]
    if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
        raise AuthorityError("NONCE_INVALID")
    if record["review_decision"] != "GO":
        raise AuthorityError("REVIEW_DECISION_NOT_GO")
    bindings = _validate_bindings(record["bindings"])
    declarations = _validate_declarations(record["declarations"])
    return {
        "bindings": {
            field: bindings[field]
            for field in sorted(BINDING_FIELDS)
        },
        "one_run_nonce": nonce,
        "declarations": {
            field: declarations[field]
            for field in sorted(DECLARATION_FIELDS)
        },
        "review_decision": "GO",
    }


def _validate_time_window(
    issued_text: Any,
    expires_text: Any,
    *,
    now: dt.datetime,
    max_seconds: int,
    location: str,
) -> tuple[dt.datetime, dt.datetime]:
    issued = _parse_utc(issued_text, f"{location}.issued_at_utc")
    expires = _parse_utc(expires_text, f"{location}.expires_at_utc")
    if issued > now:
        raise AuthorityError("NOT_YET_VALID", location)
    if expires <= now:
        raise AuthorityError("EXPIRED", location)
    lifetime = (expires - issued).total_seconds()
    if lifetime <= 0 or lifetime > max_seconds:
        raise AuthorityError("TIME_WINDOW_INVALID", location)
    return issued, expires


def _validate_receipt_request(
    value: Any,
    *,
    now: dt.datetime,
) -> dict[str, Any]:
    record = _exact_keys(
        value,
        {
            "schema_version",
            "receipt_id",
            "issued_at_utc",
            "expires_at_utc",
            "bound_execution",
        },
        "receipt_request",
    )
    if record["schema_version"] != RECEIPT_REQUEST_SCHEMA:
        raise AuthorityError("INVALID_SCHEMA", "receipt_request.schema_version")
    _require_id(record["receipt_id"], "receipt_request.receipt_id")
    _validate_time_window(
        record["issued_at_utc"],
        record["expires_at_utc"],
        now=now,
        max_seconds=MAX_RECEIPT_VALIDITY_SECONDS,
        location="receipt_request",
    )
    return {
        "schema_version": RECEIPT_REQUEST_SCHEMA,
        "receipt_id": record["receipt_id"],
        "issued_at_utc": record["issued_at_utc"],
        "expires_at_utc": record["expires_at_utc"],
        "bound_execution": validate_bound_execution(
            record["bound_execution"]
        ),
    }


def _validate_signed_payload(
    value: Any,
    *,
    now: dt.datetime,
    check_time: bool,
) -> dict[str, Any]:
    record = _exact_keys(
        value,
        {
            "schema_version",
            "receipt_id",
            "role",
            "authority_id",
            "key_fingerprint",
            "issued_at_utc",
            "expires_at_utc",
            "bound_execution",
        },
        "signed_payload",
    )
    if record["schema_version"] != SIGNED_PAYLOAD_SCHEMA:
        raise AuthorityError("INVALID_SCHEMA", "signed_payload.schema_version")
    _require_id(record["receipt_id"], "signed_payload.receipt_id")
    if record["role"] not in ROLES:
        raise AuthorityError("ROLE_NOT_ALLOWED", str(record["role"]))
    _require_id(record["authority_id"], "signed_payload.authority_id")
    _require_hash(
        record["key_fingerprint"], "signed_payload.key_fingerprint"
    )
    if check_time:
        _validate_time_window(
            record["issued_at_utc"],
            record["expires_at_utc"],
            now=now,
            max_seconds=MAX_RECEIPT_VALIDITY_SECONDS,
            location="signed_payload",
        )
    else:
        issued = _parse_utc(
            record["issued_at_utc"], "signed_payload.issued_at_utc"
        )
        expires = _parse_utc(
            record["expires_at_utc"], "signed_payload.expires_at_utc"
        )
        lifetime = (expires - issued).total_seconds()
        if lifetime <= 0 or lifetime > MAX_RECEIPT_VALIDITY_SECONDS:
            raise AuthorityError("TIME_WINDOW_INVALID", "signed_payload")
    return {
        "schema_version": SIGNED_PAYLOAD_SCHEMA,
        "receipt_id": record["receipt_id"],
        "role": record["role"],
        "authority_id": record["authority_id"],
        "key_fingerprint": record["key_fingerprint"],
        "issued_at_utc": record["issued_at_utc"],
        "expires_at_utc": record["expires_at_utc"],
        "bound_execution": validate_bound_execution(
            record["bound_execution"]
        ),
    }


def sign_receipt(
    role: str,
    *,
    payload_path: Path,
    output_path: Path,
    registry_path: Path = DEFAULT_REGISTRY,
    authorities_root: Path | None = None,
    private_root: Path | None = None,
    private_key: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Sign using only the public registry and the selected role's key."""

    if role not in ROLES:
        raise AuthorityError("ROLE_NOT_ALLOWED", role)
    if payload_path.resolve() == output_path.resolve():
        raise AuthorityError(
            "OUTPUT_PATH_INVALID", "payload and output must differ"
    )
    current = now or _now_utc()
    registry = load_registry(registry_path)
    resolved_root, resolved_key = _resolve_role_private_key(
        role,
        authorities_root=authorities_root,
        private_root=private_root,
        private_key=private_key,
    )
    private_pem = _load_role_private_key(
        registry,
        role,
        private_root=resolved_root,
        private_key=resolved_key,
    )
    request = _validate_receipt_request(load_json(payload_path), now=current)
    authority = registry[role]
    signed_payload = {
        "schema_version": SIGNED_PAYLOAD_SCHEMA,
        "receipt_id": request["receipt_id"],
        "role": role,
        "authority_id": authority["authority_id"],
        "key_fingerprint": authority["key_fingerprint"],
        "issued_at_utc": request["issued_at_utc"],
        "expires_at_utc": request["expires_at_utc"],
        "bound_execution": request["bound_execution"],
    }
    signature = _sign(private_pem, canonical_bytes(signed_payload))
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "algorithm": ALGORITHM,
        "signed_payload": signed_payload,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }
    payload = (
        json.dumps(
            receipt,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _write_exclusive(output_path, payload, 0o600)
    return receipt


def verify_receipt(
    value: Any,
    *,
    registry: Mapping[str, Mapping[str, Any]],
    now: dt.datetime | None = None,
    expected_role: str | None = None,
) -> dict[str, Any]:
    """Verify the schema, allowlist identity, validity, and signature."""

    record = _exact_keys(
        value,
        {
            "schema_version",
            "algorithm",
            "signed_payload",
            "signature_base64",
        },
        "receipt",
    )
    if record["schema_version"] != RECEIPT_SCHEMA:
        raise AuthorityError("INVALID_SCHEMA", "receipt.schema_version")
    if record["algorithm"] != ALGORITHM:
        raise AuthorityError("INVALID_SCHEMA", "receipt.algorithm")
    payload = _validate_signed_payload(
        record["signed_payload"],
        now=now or _now_utc(),
        check_time=True,
    )
    role = payload["role"]
    if expected_role is not None and role != expected_role:
        raise AuthorityError("ROLE_MISMATCH")
    if role not in registry:
        raise AuthorityError("ROLE_NOT_ALLOWED", role)
    authority = registry[role]
    if (
        payload["authority_id"] != authority["authority_id"]
        or payload["key_fingerprint"] != authority["key_fingerprint"]
    ):
        raise AuthorityError("AUTHORITY_NOT_ALLOWLISTED", role)
    signature_text = record["signature_base64"]
    if not isinstance(signature_text, str):
        raise AuthorityError("SIGNATURE_ENCODING_INVALID")
    try:
        signature = base64.b64decode(signature_text, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AuthorityError("SIGNATURE_ENCODING_INVALID") from exc
    if len(signature) != 64:
        raise AuthorityError("SIGNATURE_ENCODING_INVALID")
    public_pem = str(authority["public_key_pem"]).encode("ascii")
    if not _verify(public_pem, canonical_bytes(payload), signature):
        raise AuthorityError("SIGNATURE_INVALID")
    return payload


def verify_receipt_file(
    receipt_path: Path,
    *,
    registry_path: Path = DEFAULT_REGISTRY,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    return verify_receipt(
        load_json(receipt_path), registry=registry, now=now
    )


def verify_overlay_approvals(
    value: Any,
    *,
    registry: Mapping[str, Mapping[str, Any]],
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Require two independent valid receipts over one exact execution."""

    record = _exact_keys(
        value,
        {
            "schema_version",
            "authorization_id",
            "issued_at_utc",
            "expires_at_utc",
            "bound_execution",
            "approvals",
        },
        "overlay",
    )
    if record["schema_version"] != OVERLAY_SCHEMA:
        raise AuthorityError("INVALID_SCHEMA", "overlay.schema_version")
    authorization_id = _require_id(
        record["authorization_id"], "overlay.authorization_id"
    )
    current = now or _now_utc()
    overlay_issued, overlay_expires = _validate_time_window(
        record["issued_at_utc"],
        record["expires_at_utc"],
        now=current,
        max_seconds=MAX_OVERLAY_VALIDITY_SECONDS,
        location="overlay",
    )
    bound_execution = validate_bound_execution(record["bound_execution"])
    approvals = _exact_keys(
        record["approvals"], set(ROLES), "overlay.approvals"
    )
    verified: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        payload = verify_receipt(
            approvals[role],
            registry=registry,
            now=current,
            expected_role=role,
        )
        if payload["bound_execution"] != bound_execution:
            raise AuthorityError("BOUND_EXECUTION_MISMATCH", role)
        issued = _parse_utc(
            payload["issued_at_utc"], f"{role}.issued_at_utc"
        )
        expires = _parse_utc(
            payload["expires_at_utc"], f"{role}.expires_at_utc"
        )
        if issued < overlay_issued or expires > overlay_expires:
            raise AuthorityError("APPROVAL_OUTSIDE_OVERLAY_WINDOW", role)
        verified[role] = payload

    live = verified["live_wiring_reviewer"]
    red = verified["red_team_reviewer"]
    if (
        live["authority_id"] == red["authority_id"]
        or live["key_fingerprint"] == red["key_fingerprint"]
        or live["receipt_id"] == red["receipt_id"]
    ):
        raise AuthorityError("APPROVAL_INDEPENDENCE_INVALID")
    if live["bound_execution"] != red["bound_execution"]:
        raise AuthorityError("BOUND_EXECUTION_MISMATCH")
    return {
        "status": "OVERLAY_APPROVALS_VALID",
        "authorization_id": authorization_id,
        "overlay_sha256": semantic_hash(dict(record)),
        "bound_execution_sha256": semantic_hash(bound_execution),
        "authority_ids": {
            role: verified[role]["authority_id"] for role in ROLES
        },
        "receipt_ids": {
            role: verified[role]["receipt_id"] for role in ROLES
        },
    }


def verify_overlay_file(
    overlay_path: Path,
    *,
    registry_path: Path = DEFAULT_REGISTRY,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    return verify_overlay_approvals(
        load_json(overlay_path), registry=registry, now=now
    )


def _emit(value: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--init-authorities", action="store_true")
    action.add_argument("--sign-receipt", metavar="ROLE", choices=ROLES)
    action.add_argument("--verify-receipt", metavar="FILE", type=Path)
    action.add_argument(
        "--verify-overlay-approvals", metavar="FILE", type=Path
    )
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--authorities-root", type=Path)
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--private-key", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.init_authorities:
            if any(
                item is not None
                for item in (
                    args.payload,
                    args.output,
                    args.private_root,
                    args.private_key,
                )
            ):
                parser.error(
                    "--payload/--output/--private-root/--private-key "
                    "apply only to --sign-receipt"
                )
            result = initialize_authorities(
                registry_path=args.registry,
                authorities_root=(
                    args.authorities_root or DEFAULT_AUTHORITIES_ROOT
                ),
            )
        elif args.sign_receipt is not None:
            if args.payload is None or args.output is None:
                parser.error(
                    "--sign-receipt requires --payload FILE --output FILE"
                )
            receipt = sign_receipt(
                args.sign_receipt,
                payload_path=args.payload,
                output_path=args.output,
                registry_path=args.registry,
                authorities_root=args.authorities_root,
                private_root=args.private_root,
                private_key=args.private_key,
            )
            result = {
                "status": "RECEIPT_SIGNED",
                "role": args.sign_receipt,
                "receipt_id": receipt["signed_payload"]["receipt_id"],
                "output": str(args.output),
            }
        elif args.verify_receipt is not None:
            if any(
                item is not None
                for item in (
                    args.payload,
                    args.output,
                    args.authorities_root,
                    args.private_root,
                    args.private_key,
                )
            ):
                parser.error(
                    "private-key and payload options apply only to "
                    "--sign-receipt"
                )
            payload = verify_receipt_file(
                args.verify_receipt, registry_path=args.registry
            )
            result = {
                "status": "RECEIPT_VALID",
                "role": payload["role"],
                "receipt_id": payload["receipt_id"],
                "bound_execution_sha256": semantic_hash(
                    payload["bound_execution"]
                ),
            }
        else:
            if any(
                item is not None
                for item in (
                    args.payload,
                    args.output,
                    args.authorities_root,
                    args.private_root,
                    args.private_key,
                )
            ):
                parser.error(
                    "private-key and payload options apply only to "
                    "--sign-receipt"
                )
            result = verify_overlay_file(
                args.verify_overlay_approvals,
                registry_path=args.registry,
            )
    except AuthorityError as exc:
        _emit(
            {
                "status": "FAIL_CLOSED",
                "error_code": exc.code,
                "message": str(exc),
            }
        )
        return 2
    _emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
