"""Frozen download plans and fail-closed execution authorization.

This module deliberately separates metadata planning, human authorization, and
byte transport.  No concrete transport ships with AV-TRACE.
"""

from __future__ import annotations

import ipaddress
import hashlib
import os
import re
import stat
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

from .audit import verify_audit_log
from .errors import DownloadPlanError, DownloadRefused
from .io import load_json, sha256_json
from .models import NormalizedCandidate

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMMUTABLE_REVISION_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_RFC3339_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
}
_SENSITIVE_QUERY_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "awsaccesskeyid",
    "authorization",
    "auth",
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
_UNRESOLVED_RIGHTSHOLDER_VALUES = {
    "",
    "unknown",
    "unknown_hold",
    "unresolved",
    "tbd",
    "not_reviewed",
}
_DEFAULT_PROVIDER_HOSTS: dict[str, tuple[str, ...]] = {
    "huggingface": (
        "huggingface.co",
        "cdn-lfs.hf.co",
        "cdn-lfs-us-1.hf.co",
        "cas-bridge.xethub.hf.co",
    ),
    "github": (
        "github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
        "github-releases.githubusercontent.com",
    ),
}
_MAX_REDIRECTS = 5
_PLAN_MODES = {"executable", "metadata_preview"}
_FILELIKE_PATH_SEGMENT_RE = re.compile(r"^.+\.[A-Za-z0-9]{1,12}$")


def _assert_no_serialized_secrets(value: Any, path: str = "value") -> None:
    """Reject credential-shaped fields before data enters a frozen plan."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in {
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
            }:
                raise DownloadPlanError(
                    f"sensitive field cannot be serialized into plan: {path}.{key}"
                )
            _assert_no_serialized_secrets(nested, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_no_serialized_secrets(nested, f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return
    lowered = value.strip().lower()
    if lowered.startswith(("bearer ", "basic ")):
        raise DownloadPlanError(
            f"authorization material cannot be serialized into plan: {path}"
        )
    if not lowered.startswith(("http://", "https://")):
        return
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise DownloadPlanError(f"malformed URL in plan input: {path}") from exc
    if parsed.username is not None or parsed.password is not None:
        raise DownloadPlanError(f"URL credentials cannot be serialized into plan: {path}")
    for field in parsed.query.split("&") if parsed.query else ():
        name = unquote(field.split("=", 1)[0]).strip().lower()
        if name in _SENSITIVE_QUERY_NAMES:
            raise DownloadPlanError(
                f"credential-like query cannot be serialized into plan: {path}"
            )


@dataclass(frozen=True)
class ResolvedDownload:
    """Public, non-secret metadata returned by a resolver.

    ``headers`` remains for source compatibility, but planning rejects any
    supplied header. Authentication belongs in a separately reviewed transport
    and must never be serialized into a plan.
    """

    url: str
    headers: dict[str, str]
    provider_revision: str
    expected_size: int | None = None
    expected_sha256: str | None = None
    etag: str | None = None


class DownloadURLResolver(ABC):
    """Boundary for future official API/HF-client URL resolution."""

    @abstractmethod
    def resolve(self, candidate: NormalizedCandidate) -> ResolvedDownload:
        """Resolve one pinned candidate without transferring bytes."""


class MetadataURLResolver(DownloadURLResolver):
    """Use an exact URL already present in a frozen local metadata snapshot."""

    def resolve(self, candidate: NormalizedCandidate) -> ResolvedDownload:
        if not candidate.media_url:
            raise DownloadPlanError(
                f"{candidate.dataset_id}:{candidate.source_id} has no frozen media URL"
            )
        return ResolvedDownload(
            url=candidate.media_url,
            headers={},
            provider_revision=candidate.revision,
            expected_size=candidate.byte_size,
            expected_sha256=candidate.checksum,
            etag=(
                str(candidate.retrieval["etag"])
                if candidate.retrieval.get("etag") is not None
                else None
            ),
        )


class ApprovalSignatureVerifier(ABC):
    """Optional detached-signature verifier supplied by trusted application code."""

    @abstractmethod
    def verify(
        self, signed_payload: Mapping[str, Any], detached_signature: str
    ) -> bool:
        """Return true only for a valid signature over ``signed_payload``."""


class ByteTransferBackend(ABC):
    """Future byte-transfer boundary. No network backend ships in this package."""

    @abstractmethod
    def transfer(self, item: Mapping[str, Any]) -> Mapping[str, Any]:
        """Transfer one item and return the strict attestation documented below.

        The result is not trusted merely because the backend returned it.
        ``execute_download_plan`` validates the requested/effective URLs,
        redirect chain, peer IP, destination, byte range/count, immutable
        revision, ETag, and checksum before reporting success.
        """


def _require_sha256(value: Any, label: str, error_type: type[Exception]) -> str:
    text = str(value or "").lower()
    if not _SHA256_RE.fullmatch(text):
        raise error_type(f"{label} must be a lowercase sha256 digest")
    return text


def _require_immutable_revision(
    value: Any, label: str, error_type: type[Exception]
) -> str:
    revision = str(value or "")
    if not _IMMUTABLE_REVISION_RE.fullmatch(revision):
        raise error_type(
            f"{label} must be one full immutable 40- or 64-hex revision"
        )
    return revision.lower()


def _provider_hosts(
    provider: str,
    overrides: Mapping[str, Sequence[str]] | None,
    *,
    error_type: type[Exception],
) -> tuple[str, ...]:
    source = overrides if overrides is not None else _DEFAULT_PROVIDER_HOSTS
    raw_hosts = source.get(provider)
    if not raw_hosts:
        raise error_type(f"no explicit URL host allowlist for provider {provider!r}")
    hosts: list[str] = []
    for raw_host in raw_hosts:
        host = str(raw_host).strip().rstrip(".").lower()
        if not host or "/" in host or ":" in host:
            raise error_type(f"invalid allowed host for provider {provider!r}")
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise error_type(f"invalid allowed host for provider {provider!r}") from exc
        hosts.append(host)
    return tuple(sorted(set(hosts)))


def _is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(address.is_global)


def _canonicalize_url(
    value: Any,
    *,
    allowed_hosts: Sequence[str],
    label: str,
    error_type: type[Exception],
) -> str:
    text = str(value or "")
    if (
        not text
        or any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in text)
        or text != text.strip()
        or "\\" in text
    ):
        raise error_type(f"{label} is malformed")
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as exc:
        raise error_type(f"{label} is malformed") from exc
    if parsed.scheme.lower() != "https":
        raise error_type(f"{label} must use HTTPS")
    if not parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise error_type(f"{label} must not contain credentials")
    if parsed.fragment:
        raise error_type(f"{label} must not contain a fragment")
    if port not in (None, 443):
        raise error_type(f"{label} must use the default HTTPS port")
    hostname = (parsed.hostname or "").rstrip(".").lower()
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise error_type(f"{label} has an invalid hostname") from exc
    if not hostname or hostname not in set(allowed_hosts):
        raise error_type(f"{label} host is not allowed for this provider")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise error_type(f"{label} resolves to a local name")
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and not literal_ip.is_global:
        raise error_type(f"{label} must not target a private or local address")
    decoded_path = parsed.path
    for _ in range(8):
        lowered = decoded_path.lower()
        if re.search(r"%(?![0-9a-f]{2})", lowered):
            raise error_type(f"{label} contains malformed percent encoding")
        if re.search(r"%(?:0[0-9a-f]|1[0-9a-f]|7f|8[0-9a-f]|9[0-9a-f])", lowered):
            raise error_type(f"{label} contains an encoded control character")
        if "%2f" in lowered or "%5c" in lowered:
            raise error_type(f"{label} contains an ambiguous encoded path separator")
        for segment in decoded_path.split("/"):
            if segment in {".", ".."}:
                raise error_type(f"{label} contains path traversal")
        next_path = unquote(decoded_path)
        if next_path == decoded_path:
            break
        decoded_path = next_path
    else:
        raise error_type(f"{label} is recursively encoded")
    if any(
        ord(character) < 32 or 127 <= ord(character) <= 159
        for character in decoded_path
    ):
        raise error_type(f"{label} contains a control character")
    if "\\" in decoded_path:
        raise error_type(f"{label} contains an ambiguous path separator")
    if any(segment in {".", ".."} for segment in decoded_path.split("/")):
        raise error_type(f"{label} contains path traversal")
    if parsed.query:
        # A generic planner cannot prove that arbitrary query material is
        # non-secret. Provider transports may resolve ephemeral credentials
        # out of band, but they must not freeze them into plans.
        raise error_type(f"{label} contains credential-like query material")
    netloc = hostname if port is None else f"{hostname}:443"
    return urlunsplit(
        SplitResult("https", netloc, parsed.path or "/", parsed.query, "")
    )


def _validate_revision_url(
    *,
    provider: str,
    repository_id: str,
    revision: str,
    canonical_url: str,
    error_type: type[Exception],
) -> None:
    parsed = urlsplit(canonical_url)
    decoded_segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
    repository_segments = repository_id.split("/")
    if len(repository_segments) != 2 or not all(repository_segments):
        raise error_type("repository_id must be an owner/name pair")
    if provider == "huggingface":
        expected = ["datasets", *repository_segments, "resolve", revision]
        if decoded_segments[: len(expected)] != expected:
            raise error_type(
                "Hugging Face URL is not bound to the repository and immutable revision"
            )
        object_segments = decoded_segments[len(expected) :]
        if not object_segments:
            raise error_type("Hugging Face URL has no provider object path")
        if any(_FILELIKE_PATH_SEGMENT_RE.fullmatch(part) for part in object_segments[:-1]):
            raise error_type("Hugging Face URL has an ambiguous provider object path")
        return
    if provider == "github":
        host = parsed.hostname
        if host == "raw.githubusercontent.com":
            expected = [*repository_segments, revision]
            if decoded_segments[: len(expected)] != expected:
                raise error_type(
                    "GitHub raw URL is not bound to the repository and immutable revision"
                )
            object_segments = decoded_segments[len(expected) :]
            if not object_segments:
                raise error_type("GitHub raw URL has no provider object path")
            if any(
                _FILELIKE_PATH_SEGMENT_RE.fullmatch(part)
                for part in object_segments[:-1]
            ):
                raise error_type("GitHub raw URL has an ambiguous provider object path")
            return
        if host == "github.com":
            prefix = decoded_segments[:4]
            if (
                len(prefix) < 4
                or prefix[:2] != repository_segments
                or prefix[2] not in {"blob", "raw"}
                or prefix[3] != revision
            ):
                raise error_type(
                    "GitHub URL is not bound to the repository and immutable revision"
                )
            object_segments = decoded_segments[4:]
            if not object_segments:
                raise error_type("GitHub URL has no provider object path")
            if any(
                _FILELIKE_PATH_SEGMENT_RE.fullmatch(part)
                for part in object_segments[:-1]
            ):
                raise error_type("GitHub URL has an ambiguous provider object path")
            return
        raise error_type("GitHub planning URLs must be github.com or raw.githubusercontent.com")
    raise error_type(f"provider {provider!r} has no immutable URL binding rule")


def _safe_filename(candidate: NormalizedCandidate, canonical_url: str) -> str:
    suffix = Path(urlsplit(canonical_url).path).suffix
    if (
        not suffix
        or len(suffix) > 12
        or not re.fullmatch(r"\.[A-Za-z0-9]+", suffix)
    ):
        suffix = ".bin"
    base = "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in f"{candidate.dataset_id}-{candidate.source_id}"
    ).strip(".")
    if not base:
        raise DownloadPlanError("candidate identity does not produce a safe filename")
    return base[:180] + suffix.lower()


def _normalized_staging_root(output_root: str) -> Path:
    raw = Path(output_root).expanduser()
    if not raw.is_absolute():
        raise DownloadPlanError("output_root must be an absolute approved staging path")
    root = raw.resolve(strict=False)
    if root == Path(root.anchor):
        raise DownloadPlanError("filesystem root cannot be used as the staging root")
    return root


def _contained_destination(root: Path, filename: str) -> Path:
    destination = (root / filename).resolve(strict=False)
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise DownloadPlanError("destination escapes the approved staging root") from exc
    return destination


def _selection_body_and_candidates(
    candidates_or_selection: Sequence[NormalizedCandidate] | Mapping[str, Any],
    selection_artifact: Mapping[str, Any] | None,
) -> tuple[list[NormalizedCandidate], dict[str, Any], bool]:
    if isinstance(candidates_or_selection, Mapping):
        if selection_artifact is not None:
            raise DownloadPlanError("selection artifact was supplied twice")
        selection_artifact = candidates_or_selection
        raw_selected = selection_artifact.get("selected")
        if not isinstance(raw_selected, list):
            raise DownloadPlanError("selection artifact must contain a selected array")
        candidates = [NormalizedCandidate.from_dict(dict(item)) for item in raw_selected]
    else:
        candidates = list(candidates_or_selection)

    if not candidates:
        raise DownloadPlanError("cannot create an empty download plan")
    exact_records = [candidate.to_dict() for candidate in candidates]
    _assert_no_serialized_secrets(exact_records, "selected")
    if selection_artifact is None:
        # Legacy direct callers may still create a review-only plan, but it
        # cannot cross the authorization boundary.
        body = {
            "selection_version": "direct-input-unverified",
            "selected": exact_records,
        }
        return candidates, body, False

    artifact = dict(selection_artifact)
    supplied_hash = _require_sha256(
        artifact.get("selection_sha256"),
        "selection_sha256",
        DownloadPlanError,
    )
    body = dict(artifact)
    body.pop("selection_sha256", None)
    if sha256_json(body) != supplied_hash:
        raise DownloadPlanError("selection hash does not match its complete artifact")
    if artifact.get("selection_version") not in {"1.0", "2.0"}:
        raise DownloadPlanError("unsupported selection_version")
    if not isinstance(artifact.get("policy"), Mapping):
        raise DownloadPlanError("selection artifact has no policy object")
    if not isinstance(artifact.get("summary"), Mapping):
        raise DownloadPlanError("selection artifact has no summary object")
    if not isinstance(artifact.get("rejected"), list):
        raise DownloadPlanError("selection artifact has no rejected array")
    if artifact.get("selected") != exact_records:
        raise DownloadPlanError("selected normalized records do not match the selection")
    if artifact["summary"].get("selected_count") != len(exact_records):
        raise DownloadPlanError("selection summary selected_count is inconsistent")
    return candidates, artifact, True


def _snapshot_bindings(selection: Mapping[str, Any]) -> dict[str, str]:
    source_snapshots = selection.get("source_snapshots")
    if source_snapshots is None:
        return {}
    if not isinstance(source_snapshots, Mapping):
        raise DownloadPlanError("source_snapshots must be an object of source bindings")
    bindings: dict[str, str] = {}
    for raw_key, value in source_snapshots.items():
        key = str(raw_key).strip()
        source, separator, raw_revision = key.rpartition("@")
        provider, provider_separator, repository_id = source.partition(":")
        repository_parts = repository_id.split("/")
        if (
            not key
            or separator != "@"
            or provider_separator != ":"
            or not provider
            or len(repository_parts) != 2
            or not all(repository_parts)
        ):
            raise DownloadPlanError(
                "source snapshot keys must be provider:repository@revision bindings"
            )
        revision = _require_immutable_revision(
            raw_revision,
            f"source snapshot revision for {key}",
            DownloadPlanError,
        )
        normalized_key = f"{provider}:{repository_id}@{revision}"
        digest = _require_sha256(
            value, f"source snapshot hash for {key}", DownloadPlanError
        )
        if normalized_key in bindings and bindings[normalized_key] != digest:
            raise DownloadPlanError(
                f"conflicting source snapshot hashes for {normalized_key}"
            )
        bindings[normalized_key] = digest
    return dict(sorted(bindings.items()))


def _snapshot_hashes(selection: Mapping[str, Any]) -> list[str]:
    found: set[str] = set()
    for key in (
        "inspection_snapshot_sha256",
        "source_snapshot_sha256",
        "snapshot_sha256",
    ):
        if selection.get(key) is not None:
            found.add(_require_sha256(selection[key], key, DownloadPlanError))
    for value in _snapshot_bindings(selection).values():
        found.add(value)
    selected = selection.get("selected")
    if isinstance(selected, list):
        for record in selected:
            if not isinstance(record, Mapping):
                continue
            metadata = record.get("source_metadata")
            if not isinstance(metadata, Mapping):
                continue
            for key in (
                "inspection_snapshot_sha256",
                "source_snapshot_sha256",
                "snapshot_sha256",
            ):
                if metadata.get(key) is not None:
                    found.add(
                        _require_sha256(metadata[key], key, DownloadPlanError)
                    )
    return sorted(found)


def _manifest_binding(
    candidate: NormalizedCandidate,
    manifest: Mapping[str, Any],
    manifest_key: str,
    *,
    require_integrity_values: bool = False,
) -> None:
    source = manifest.get("source")
    integrity = manifest.get("integrity")
    acquisition = manifest.get("acquisition")
    if not isinstance(source, Mapping):
        raise DownloadPlanError(f"manifest for {manifest_key} has no source object")
    if not isinstance(integrity, Mapping):
        raise DownloadPlanError(f"manifest for {manifest_key} has no integrity object")
    if not isinstance(acquisition, Mapping):
        raise DownloadPlanError(f"manifest for {manifest_key} has no acquisition object")
    comparisons = (
        ("dataset_id", manifest.get("dataset_id"), candidate.dataset_id),
        ("source_revision", source.get("source_revision"), candidate.revision),
        ("source_identifier", source.get("source_identifier"), candidate.upstream_id),
        ("canonical_url", source.get("canonical_url"), candidate.canonical_url),
        ("publisher", source.get("publisher"), candidate.publisher),
        ("source_family", source.get("source_family"), candidate.source_family),
    )
    for label, actual, expected in comparisons:
        if actual != expected:
            raise DownloadPlanError(f"manifest {label} mismatch for {manifest_key}")
    for label, actual, expected in (
        ("byte_size", integrity.get("byte_size"), candidate.byte_size),
        ("content_sha256", integrity.get("content_sha256"), candidate.checksum),
    ):
        if actual is None and not require_integrity_values:
            continue
        if actual != expected:
            raise DownloadPlanError(f"manifest {label} mismatch for {manifest_key}")
    if not str(acquisition.get("method") or "").strip():
        raise DownloadPlanError(f"manifest acquisition method is missing for {manifest_key}")


def create_download_plan(
    candidates: Sequence[NormalizedCandidate] | Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    *,
    output_root: str,
    resolver: DownloadURLResolver | None = None,
    max_item_bytes: int | None = None,
    max_total_bytes: int | None = None,
    range_start: int | None = None,
    range_end: int | None = None,
    selection_artifact: Mapping[str, Any] | None = None,
    provider_host_allowlist: Mapping[str, Sequence[str]] | None = None,
    plan_mode: str = "executable",
) -> dict[str, Any]:
    """Create a frozen transfer plan without opening a network connection.

    Passing the complete selection artifact (either as the first argument or
    through ``selection_artifact``) is required for executable mode. Direct
    candidate sequences are accepted only in explicit ``metadata_preview``
    mode, which produces a non-executable plan.
    """

    if plan_mode not in _PLAN_MODES:
        raise DownloadPlanError(
            "plan_mode must be 'executable' or 'metadata_preview'"
        )
    candidates_list, selection, selection_verified = _selection_body_and_candidates(
        candidates, selection_artifact
    )
    snapshot_bindings = _snapshot_bindings(selection)
    executable = plan_mode == "executable"
    if executable and not selection_verified:
        raise DownloadPlanError(
            "executable plans require a verified complete selection artifact"
        )
    if executable:
        if not snapshot_bindings:
            raise DownloadPlanError(
                "executable plans require at least one source snapshot binding"
            )
        missing_sources = sorted(
            {
                f"{candidate.provider}:{candidate.repository_id}@"
                f"{candidate.revision.lower()}"
                for candidate in candidates_list
            }
            - set(snapshot_bindings)
        )
        if missing_sources:
            raise DownloadPlanError(
                "executable plan source snapshot coverage is missing: "
                + ", ".join(missing_sources)
            )
    if range_start is not None and range_start < 0:
        raise DownloadPlanError("range_start must be non-negative")
    if range_end is not None and range_end < 0:
        raise DownloadPlanError("range_end must be non-negative")
    if range_start is not None and range_end is not None and range_end < range_start:
        raise DownloadPlanError("range_end must be greater than or equal to range_start")
    if max_item_bytes is not None and max_item_bytes <= 0:
        raise DownloadPlanError("max_item_bytes must be positive")
    if max_total_bytes is not None and max_total_bytes <= 0:
        raise DownloadPlanError("max_total_bytes must be positive")
    if executable:
        policy = selection.get("policy")
        if isinstance(policy, Mapping):
            if max_item_bytes is None:
                max_item_bytes = policy.get("max_item_bytes")
            if max_total_bytes is None:
                max_total_bytes = policy.get("max_total_bytes")
        if (
            isinstance(max_item_bytes, bool)
            or not isinstance(max_item_bytes, int)
            or max_item_bytes <= 0
            or isinstance(max_total_bytes, bool)
            or not isinstance(max_total_bytes, int)
            or max_total_bytes <= 0
        ):
            raise DownloadPlanError(
                "executable plans require explicit positive item and total byte caps"
            )

    resolver = resolver or MetadataURLResolver()
    staging_root = _normalized_staging_root(output_root)
    items: list[dict[str, Any]] = []
    known_total = 0
    seen_assets: set[str] = set()
    seen_paths: set[str] = set()
    for candidate in candidates_list:
        manifest_key = f"{candidate.dataset_id}:{candidate.source_id}"
        if not candidate.upstream_id:
            raise DownloadPlanError(
                f"candidate identity is unresolved for {manifest_key}"
            )
        manifest = manifests.get(manifest_key)
        if not isinstance(manifest, Mapping):
            raise DownloadPlanError(f"missing manifest for {manifest_key}")
        asset_id = str(manifest.get("asset_id") or "")
        if not asset_id:
            raise DownloadPlanError(f"manifest for {manifest_key} has no asset_id")
        if asset_id in seen_assets:
            raise DownloadPlanError(f"duplicate asset_id in plan: {asset_id}")
        seen_assets.add(asset_id)
        _manifest_binding(candidate, manifest, manifest_key)

        revision = _require_immutable_revision(
            candidate.revision,
            f"revision for {manifest_key}",
            DownloadPlanError,
        )
        resolved = resolver.resolve(candidate)
        if resolved.headers:
            names = {str(name).strip().lower() for name in resolved.headers}
            if names & _SENSITIVE_HEADER_NAMES:
                raise DownloadPlanError(
                    f"resolver returned credential headers for {manifest_key}"
                )
            raise DownloadPlanError(
                f"resolver headers cannot be serialized into a plan for {manifest_key}"
            )
        provider_revision = _require_immutable_revision(
            resolved.provider_revision,
            f"resolver revision for {manifest_key}",
            DownloadPlanError,
        )
        if provider_revision != revision:
            raise DownloadPlanError(
                f"resolver returned a different immutable revision for {manifest_key}"
            )
        allowed_hosts = _provider_hosts(
            candidate.provider,
            provider_host_allowlist,
            error_type=DownloadPlanError,
        )
        canonical_url = _canonicalize_url(
            resolved.url,
            allowed_hosts=allowed_hosts,
            label=f"download URL for {manifest_key}",
            error_type=DownloadPlanError,
        )
        _validate_revision_url(
            provider=candidate.provider,
            repository_id=candidate.repository_id,
            revision=revision,
            canonical_url=canonical_url,
            error_type=DownloadPlanError,
        )

        size = resolved.expected_size
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise DownloadPlanError(
                f"transfer size is unknown or invalid for {manifest_key}"
            )
        if candidate.byte_size != size:
            raise DownloadPlanError(f"resolver size mismatch for {manifest_key}")
        expected_sha256 = resolved.expected_sha256
        if expected_sha256 is not None:
            expected_sha256 = _require_sha256(
                expected_sha256,
                f"expected checksum for {manifest_key}",
                DownloadPlanError,
            )
        if expected_sha256 != candidate.checksum:
            raise DownloadPlanError(f"resolver checksum mismatch for {manifest_key}")

        start = 0 if range_start is None else range_start
        if start >= size:
            raise DownloadPlanError(f"range starts beyond item size for {manifest_key}")
        effective_end = size - 1 if range_end is None else min(range_end, size - 1)
        requested_size = effective_end - start + 1
        if requested_size <= 0:
            raise DownloadPlanError(f"empty byte range for {manifest_key}")
        if max_item_bytes is not None and requested_size > max_item_bytes:
            raise DownloadPlanError(f"item size cap exceeded for {manifest_key}")
        known_total += requested_size
        if max_total_bytes is not None and known_total > max_total_bytes:
            raise DownloadPlanError("known total byte size exceeds plan cap")

        destination_path = _contained_destination(
            staging_root, _safe_filename(candidate, canonical_url)
        )
        destination = str(destination_path)
        related_paths = {
            destination,
            destination + ".partial",
            destination + ".resume.json",
        }
        if seen_paths & related_paths:
            raise DownloadPlanError("destination collision detected in download plan")
        seen_paths.update(related_paths)
        full_object = start == 0 and effective_end == size - 1
        item = {
            "asset_id": asset_id,
            "manifest_key": manifest_key,
            "manifest_sha256": sha256_json(manifest),
            "normalized_candidate": candidate.to_dict(),
            "normalized_candidate_sha256": sha256_json(candidate.to_dict()),
            "provider": candidate.provider,
            "repository_id": candidate.repository_id,
            "source_revision": revision,
            "source_identifier": candidate.upstream_id,
            "acquisition_method": manifest["acquisition"]["method"],
            "url": canonical_url,
            "allowed_redirect_hosts": list(allowed_hosts),
            "redirect_policy": {
                "https_only": True,
                "max_redirects": _MAX_REDIRECTS,
                "require_each_hop_allowed": True,
                "require_public_peer_ip": True,
                "require_dns_rebinding_protection": True,
            },
            "destination": destination,
            "staging_root": str(staging_root),
            "overwrite_allowed": False,
            "expected_size": size,
            "planned_transfer_bytes": requested_size,
            "expected_sha256": expected_sha256,
            "checksum_scope": (
                "exact_full_object" if full_object else "full_object_not_range"
            ),
            "byte_range": {
                "start": start,
                "end_inclusive": effective_end,
            },
            "resume": {
                "strategy": "exact_http_range_with_endpoint_attestation",
                "partial_path": destination + ".partial",
                "metadata_path": destination + ".resume.json",
                "initial_offset": start,
                "etag": resolved.etag,
                "verify_revision_before_resume": True,
                "verify_final_sha256": expected_sha256 is not None and full_object,
            },
        }
        items.append(item)

    items.sort(key=lambda item: (item["asset_id"], item["source_identifier"]))
    if max_item_bytes is None:
        max_item_bytes = max(int(item["planned_transfer_bytes"]) for item in items)
    if max_total_bytes is None:
        max_total_bytes = known_total
    selection_hash = (
        selection["selection_sha256"]
        if selection_verified
        else sha256_json(selection)
    )
    plan_body = {
        "download_plan_version": "2.0",
        "state": "planned_not_authorized",
        "plan_mode": plan_mode,
        "executable": executable,
        "network_access_performed": False,
        "selection_binding": {
            "verified_complete_artifact": selection_verified,
            "selection_sha256": selection_hash,
            "selection_artifact_sha256": sha256_json(selection),
            "policy_sha256": (
                sha256_json(selection["policy"])
                if isinstance(selection.get("policy"), Mapping)
                else None
            ),
            "policy": (
                dict(selection["policy"])
                if isinstance(selection.get("policy"), Mapping)
                else None
            ),
            "summary_sha256": (
                sha256_json(selection["summary"])
                if isinstance(selection.get("summary"), Mapping)
                else None
            ),
            "summary": (
                dict(selection["summary"])
                if isinstance(selection.get("summary"), Mapping)
                else None
            ),
            "source_snapshot_sha256s": _snapshot_hashes(selection),
            "source_snapshot_bindings": snapshot_bindings,
            "selected_normalized_records": [
                candidate.to_dict() for candidate in candidates_list
            ],
        },
        "staging_root": str(staging_root),
        "limits": {
            "max_item_bytes": max_item_bytes,
            "max_total_bytes": max_total_bytes,
            "known_total_bytes": known_total,
            "unknown_size_count": 0,
        },
        "items": items,
    }
    plan_hash = sha256_json(plan_body)
    return {
        **plan_body,
        "plan_id": plan_hash,
        "plan_sha256": plan_hash,
    }


def _validate_plan_integrity(plan: Mapping[str, Any]) -> str:
    if plan.get("download_plan_version") != "2.0":
        raise DownloadRefused("unsupported download_plan_version")
    expected_hash = plan.get("plan_sha256")
    body = dict(plan)
    body.pop("plan_id", None)
    body.pop("plan_sha256", None)
    actual_hash = sha256_json(body)
    if expected_hash != actual_hash or plan.get("plan_id") != actual_hash:
        raise DownloadRefused("download plan hash does not match its frozen contents")
    if plan.get("executable") is not True:
        raise DownloadRefused("plan is not bound to a verified complete selection artifact")
    if plan.get("plan_mode") != "executable":
        raise DownloadRefused("plan is metadata-preview only and cannot be executed")
    selection_binding = plan.get("selection_binding")
    if not isinstance(selection_binding, Mapping):
        raise DownloadRefused("plan selection binding is missing")
    if selection_binding.get("verified_complete_artifact") is not True:
        raise DownloadRefused("plan selection artifact was not verified")
    selected = selection_binding.get("selected_normalized_records")
    items = plan.get("items")
    if not isinstance(selected, list) or not isinstance(items, list) or not items:
        raise DownloadRefused("plan items or selected records are malformed")
    item_records = [
        item.get("normalized_candidate") for item in items if isinstance(item, Mapping)
    ]
    if sorted(item_records, key=sha256_json) != sorted(selected, key=sha256_json):
        raise DownloadRefused("plan items do not match the exact selected records")
    snapshot_bindings = selection_binding.get("source_snapshot_bindings")
    if not isinstance(snapshot_bindings, Mapping) or not snapshot_bindings:
        raise DownloadRefused("executable plan has no source snapshot binding")
    expected_sources = {
        f"{item.get('provider')}:{item.get('repository_id')}@{item.get('source_revision')}"
        for item in items
        if isinstance(item, Mapping)
    }
    if not expected_sources.issubset(set(snapshot_bindings)):
        raise DownloadRefused("executable plan source snapshot coverage is incomplete")
    for source_key, snapshot_hash in snapshot_bindings.items():
        _require_sha256(
            snapshot_hash,
            f"source snapshot hash for {source_key}",
            DownloadRefused,
        )
    snapshot_hashes = selection_binding.get("source_snapshot_sha256s")
    if (
        not isinstance(snapshot_hashes, list)
        or not snapshot_hashes
        or not all(isinstance(value, str) for value in snapshot_hashes)
        or not set(snapshot_bindings.values()).issubset(set(snapshot_hashes))
    ):
        raise DownloadRefused("executable plan snapshot hashes are inconsistent")
    limits = plan.get("limits")
    if not isinstance(limits, Mapping):
        raise DownloadRefused("plan byte limits are missing")
    for name in ("max_item_bytes", "max_total_bytes"):
        value = limits.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise DownloadRefused("executable plans require positive byte limits")
    if limits.get("unknown_size_count") != 0:
        raise DownloadRefused("executable plans cannot contain unknown transfer sizes")
    return actual_hash


def _validate_plan_items_and_manifests(
    plan: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    *,
    approved_staging_roots: Sequence[str] | None,
) -> list[str]:
    raw_root = str(plan.get("staging_root") or "")
    try:
        plan_root = _normalized_staging_root(raw_root)
    except DownloadPlanError as exc:
        raise DownloadRefused(str(exc)) from exc
    if str(plan_root) != raw_root:
        raise DownloadRefused("plan staging root is not normalized")
    if not approved_staging_roots:
        raise DownloadRefused(
            "an independent approved staging-root allowlist is required"
        )
    approved_roots = {
        str(_normalized_staging_root(root)) for root in approved_staging_roots
    }
    if str(plan_root) not in approved_roots:
        raise DownloadRefused("plan staging root is not independently approved")

    limits = plan["limits"]
    total = 0
    paths: set[str] = set()
    approved_assets: list[str] = []
    for item in plan["items"]:
        if not isinstance(item, Mapping):
            raise DownloadRefused("plan item is malformed")
        manifest_key = str(item.get("manifest_key") or "")
        manifest = manifests.get(manifest_key)
        if not isinstance(manifest, Mapping):
            raise DownloadRefused(f"manifest missing at execution: {manifest_key}")
        if sha256_json(manifest) != item.get("manifest_sha256"):
            raise DownloadRefused(f"manifest changed after planning: {manifest_key}")
        audit = manifest.get("audit")
        if (
            not isinstance(audit, Mapping)
            or audit.get("gate_status") != "acquisition_approved"
        ):
            raise DownloadRefused(
                f"manifest is not exactly acquisition_approved: {manifest_key}"
            )
        try:
            candidate = NormalizedCandidate.from_dict(
                dict(item.get("normalized_candidate") or {})
            )
            if sha256_json(candidate.to_dict()) != item.get(
                "normalized_candidate_sha256"
            ):
                raise DownloadRefused(
                    f"normalized candidate hash mismatch: {manifest_key}"
                )
            _manifest_binding(
                candidate,
                manifest,
                manifest_key,
                require_integrity_values=True,
            )
        except (DownloadPlanError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, DownloadRefused):
                raise
            raise DownloadRefused(str(exc)) from exc

        size = item.get("expected_size")
        planned_bytes = item.get("planned_transfer_bytes")
        byte_range = item.get("byte_range")
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or isinstance(planned_bytes, bool)
            or not isinstance(planned_bytes, int)
            or planned_bytes <= 0
            or not isinstance(byte_range, Mapping)
        ):
            raise DownloadRefused(f"invalid size or range for {manifest_key}")
        start = byte_range.get("start")
        end = byte_range.get("end_inclusive")
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or start < 0
            or end < start
            or end >= size
            or end - start + 1 != planned_bytes
        ):
            raise DownloadRefused(f"stored byte range does not match cap accounting: {manifest_key}")
        if planned_bytes > limits["max_item_bytes"]:
            raise DownloadRefused(f"item size cap exceeded at execution: {manifest_key}")
        total += planned_bytes

        destination = str(item.get("destination") or "")
        try:
            destination_path = Path(destination)
            if not destination_path.is_absolute():
                raise ValueError
            destination_path.resolve(strict=False).relative_to(plan_root)
        except ValueError as exc:
            raise DownloadRefused(
                f"destination escapes approved staging root: {manifest_key}"
            ) from exc
        if str(destination_path.resolve(strict=False)) != destination:
            raise DownloadRefused(f"destination is not normalized: {manifest_key}")
        related = {
            destination,
            str(item.get("resume", {}).get("partial_path") or ""),
            str(item.get("resume", {}).get("metadata_path") or ""),
        }
        if "" in related or paths & related:
            raise DownloadRefused("destination collision detected at execution")
        if related != {
            destination,
            destination + ".partial",
            destination + ".resume.json",
        }:
            raise DownloadRefused(f"resume paths are not bound to destination: {manifest_key}")
        paths.update(related)

        revision = _require_immutable_revision(
            item.get("source_revision"),
            f"revision for {manifest_key}",
            DownloadRefused,
        )
        if revision != candidate.revision.lower():
            raise DownloadRefused(f"candidate revision mismatch: {manifest_key}")
        allowed_hosts = item.get("allowed_redirect_hosts")
        if (
            not isinstance(allowed_hosts, list)
            or not allowed_hosts
            or not all(isinstance(host, str) for host in allowed_hosts)
        ):
            raise DownloadRefused(f"URL host allowlist missing: {manifest_key}")
        canonical_url = _canonicalize_url(
            item.get("url"),
            allowed_hosts=allowed_hosts,
            label=f"download URL for {manifest_key}",
            error_type=DownloadRefused,
        )
        if canonical_url != item.get("url"):
            raise DownloadRefused(f"download URL is not canonical: {manifest_key}")
        _validate_revision_url(
            provider=str(item.get("provider") or ""),
            repository_id=str(item.get("repository_id") or ""),
            revision=revision,
            canonical_url=canonical_url,
            error_type=DownloadRefused,
        )

        acquisition = manifest.get("acquisition")
        rights = manifest.get("rights")
        privacy = manifest.get("privacy_safety")
        source = manifest.get("source")
        if not isinstance(acquisition, Mapping) or acquisition.get("status") not in {
            "planned",
            "completed",
        }:
            raise DownloadRefused(f"manifest acquisition status is not approved: {manifest_key}")
        acquisition_method = str(acquisition.get("method") or "").strip()
        if acquisition_method.lower() in {"", "none", "unknown", "unknown_hold"}:
            raise DownloadRefused(
                f"manifest acquisition method is not approved: {manifest_key}"
            )
        if acquisition_method != item.get("acquisition_method"):
            raise DownloadRefused(
                f"manifest acquisition method changed after planning: {manifest_key}"
            )
        if not isinstance(rights, Mapping):
            raise DownloadRefused(f"manifest rights object missing: {manifest_key}")
        decisions = rights.get("decisions")
        if (
            rights.get("acquisition_authority") != "allowed"
            or rights.get("local_processing_authority") != "allowed"
            or not isinstance(decisions, Mapping)
            or decisions.get("acquisition") != "allowed"
            or decisions.get("processing") != "allowed"
        ):
            raise DownloadRefused(f"manifest rights gate does not pass: {manifest_key}")
        rightsholder = (
            str(source.get("rightsholder_or_status") or "").strip().lower()
            if isinstance(source, Mapping)
            else ""
        )
        if rightsholder in _UNRESOLVED_RIGHTSHOLDER_VALUES:
            raise DownloadRefused(
                f"manifest has unresolved asset-level rightsholder status: {manifest_key}"
            )
        if candidate.media_rights_status != "asset_reviewed":
            raise DownloadRefused(
                f"candidate lacks asset-level media-rights review: {manifest_key}"
            )
        authority_basis = str(acquisition.get("authority_basis") or "").strip().lower()
        if not authority_basis or "metadata discovery only" in authority_basis:
            raise DownloadRefused(
                f"manifest lacks asset-level acquisition authority: {manifest_key}"
            )
        authority_hash = acquisition.get("authority_evidence_hash")
        try:
            _require_sha256(
                authority_hash,
                f"authority evidence hash for {manifest_key}",
                DownloadRefused,
            )
        except DownloadRefused:
            raise
        if not isinstance(privacy, Mapping) or privacy.get("review_status") != "approved":
            raise DownloadRefused(f"manifest privacy/safety gate does not pass: {manifest_key}")
        try:
            from av_trace.manifest import GateProfile, validate_manifest_gate
        except ImportError as exc:
            raise DownloadRefused(
                "normative acquisition-manifest validator is unavailable"
            ) from exc
        gate_report = validate_manifest_gate(dict(manifest), GateProfile.ACQUISITION)
        if not gate_report.ok:
            codes = ",".join(sorted({issue.code for issue in gate_report.issues}))
            raise DownloadRefused(
                f"manifest fails normative acquisition validation: {manifest_key} ({codes})"
            )
        approved_assets.append(str(item.get("asset_id") or ""))
    if total != limits.get("known_total_bytes") or total > limits["max_total_bytes"]:
        raise DownloadRefused("total byte accounting does not match the plan limits")
    return approved_assets


def _parse_approval_time(value: Any, label: str) -> datetime:
    text = str(value or "")
    if not _RFC3339_UTC_RE.fullmatch(text):
        raise DownloadRefused(f"{label} must be strict RFC3339 UTC with a Z suffix")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise DownloadRefused(f"{label} is not a valid timestamp") from exc
    return parsed


def _normalize_authorized_signers(
    authorized_signers: Mapping[str, Sequence[str] | str] | None,
) -> dict[str, set[str]]:
    if not authorized_signers:
        raise DownloadRefused("an independent authorized signer/role allowlist is required")
    normalized: dict[str, set[str]] = {}
    for signer, roles in authorized_signers.items():
        signer_name = str(signer).strip()
        if not signer_name:
            raise DownloadRefused("authorized signer identity cannot be empty")
        if isinstance(roles, str):
            values = [roles]
        elif isinstance(roles, Sequence):
            values = list(roles)
        else:
            raise DownloadRefused(
                f"roles for authorized signer {signer_name!r} are malformed"
            )
        role_set = {str(role).strip() for role in values if str(role).strip()}
        if not role_set:
            raise DownloadRefused(f"authorized signer {signer_name!r} has no roles")
        normalized[signer_name] = role_set
    return normalized


def validate_execution_approval(
    plan: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    approval: Mapping[str, Any],
    *,
    authorized_signers: Mapping[str, Sequence[str] | str] | None = None,
    authorization_time: datetime | None = None,
    max_approval_age: timedelta = timedelta(hours=24),
    max_clock_skew: timedelta = timedelta(minutes=5),
    signature_verifier: ApprovalSignatureVerifier | None = None,
    approved_staging_roots: Sequence[str] | None = None,
    require_signature: bool = False,
) -> dict[str, Any]:
    """Authorize a frozen plan only when every independent control passes."""

    actual_hash = _validate_plan_integrity(plan)
    # Validate the acquisition evidence before identity fields. This keeps a
    # draft/unknown-rights manifest categorically blocked regardless of what an
    # approval file claims.
    approved_assets = _validate_plan_items_and_manifests(
        plan, manifests, approved_staging_roots=approved_staging_roots
    )

    required_approval_fields = {
        "approval_version",
        "action",
        "plan_sha256",
        "approved_by",
        "approved_role",
        "approved_at",
        "approved_asset_ids",
        "attestation",
    }
    missing = sorted(required_approval_fields - set(approval))
    if missing:
        raise DownloadRefused(f"approval file is missing fields: {', '.join(missing)}")
    if approval.get("approval_version") != "1.0":
        raise DownloadRefused("unsupported approval_version")
    if approval.get("action") != "approve_download_execution":
        raise DownloadRefused("approval action is not approve_download_execution")
    if approval.get("plan_sha256") != actual_hash:
        raise DownloadRefused("approval file does not bind this exact plan")
    signer = str(approval.get("approved_by") or "").strip()
    role = str(approval.get("approved_role") or "").strip()
    allowed = _normalize_authorized_signers(authorized_signers)
    if signer not in allowed or role not in allowed[signer]:
        raise DownloadRefused("approval signer or role is not independently authorized")
    if approval.get("attestation") != (
        "I approve acquisition of the exact assets in this frozen plan."
    ):
        raise DownloadRefused("approval file does not contain the required attestation")
    if approval.get("approved_asset_ids") != approved_assets:
        raise DownloadRefused(
            "approval file does not enumerate the exact ordered planned assets"
        )

    approved_at = _parse_approval_time(approval.get("approved_at"), "approved_at")
    now = authorization_time or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise DownloadRefused("authorization_time must be timezone-aware")
    now = now.astimezone(timezone.utc)
    if max_approval_age <= timedelta(0) or max_clock_skew < timedelta(0):
        raise DownloadRefused("approval validity bounds are invalid")
    if approved_at > now + max_clock_skew:
        raise DownloadRefused("approval timestamp is too far in the future")
    if now - approved_at > max_approval_age:
        raise DownloadRefused("approval is stale")

    signature = approval.get("detached_signature")
    signature_verified = False
    if signature_verifier is not None:
        if not isinstance(signature, str) or not signature.strip():
            raise DownloadRefused("detached signature is required by the verifier")
        signed_payload = dict(approval)
        signed_payload.pop("detached_signature", None)
        if not signature_verifier.verify(signed_payload, signature):
            raise DownloadRefused("detached approval signature is invalid")
        signature_verified = True
    elif signature is not None:
        raise DownloadRefused("detached signature was supplied without a trusted verifier")
    elif require_signature:
        raise DownloadRefused(
            "transfer execution requires a trusted detached signature verifier"
        )

    return {
        "execution_authorization_version": "2.0",
        "status": (
            "authorized_not_executed"
            if signature_verified
            else "validated_not_authorized"
        ),
        "plan_sha256": actual_hash,
        "approved_by": signer,
        "approved_role": role,
        "approved_at": approval["approved_at"],
        "asset_ids": approved_assets,
        "approval_signature_verified": signature_verified,
        "network_access_performed": False,
        "note": (
            (
                "Authorization checks and detached-signature verification passed. "
                if signature_verified
                else "Plan and approval fields validated, but no trusted detached "
                "signature was verified; this result is not execution authorization. "
            )
            + "This package ships no network transfer backend."
        ),
    }


def _validate_backend_result(
    item: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any]:
    manifest_key = str(item["manifest_key"])
    required = {
        "requested_url",
        "effective_url",
        "destination",
        "bytes_written",
        "byte_range",
        "provider_revision",
        "etag",
        "sha256",
        "endpoint_attestation",
        "filesystem_attestation",
        "destination_preexisted",
    }
    missing = sorted(required - set(result))
    if missing:
        raise DownloadRefused(
            f"backend result for {manifest_key} is missing: {', '.join(missing)}"
        )
    if result.get("requested_url") != item.get("url"):
        raise DownloadRefused(f"backend requested URL mismatch: {manifest_key}")
    if result.get("destination") != item.get("destination"):
        raise DownloadRefused(f"backend destination mismatch: {manifest_key}")
    if result.get("destination_preexisted") is not False:
        raise DownloadRefused(f"backend overwrote or reused a destination: {manifest_key}")
    filesystem = result.get("filesystem_attestation")
    if (
        not isinstance(filesystem, Mapping)
        or filesystem.get("attestation_version") != "1.0"
        or filesystem.get("exclusive_create") is not True
        or filesystem.get("symlink_safe") is not True
        or filesystem.get("destination_contained") is not True
        or filesystem.get("staging_root") != item.get("staging_root")
    ):
        raise DownloadRefused(
            f"backend filesystem safety attestation failed: {manifest_key}"
        )
    if result.get("bytes_written") != item.get("planned_transfer_bytes"):
        raise DownloadRefused(f"backend byte count mismatch: {manifest_key}")
    if result.get("byte_range") != item.get("byte_range"):
        raise DownloadRefused(f"backend byte range mismatch: {manifest_key}")
    if str(result.get("provider_revision") or "").lower() != item.get("source_revision"):
        raise DownloadRefused(f"backend revision mismatch: {manifest_key}")
    planned_etag = item.get("resume", {}).get("etag")
    if planned_etag is not None and result.get("etag") != planned_etag:
        raise DownloadRefused(f"backend ETag mismatch: {manifest_key}")
    result_sha256 = _require_sha256(
        result.get("sha256"),
        f"backend checksum for {manifest_key}",
        DownloadRefused,
    )
    if (
        item.get("checksum_scope") == "exact_full_object"
        and item.get("expected_sha256") is not None
        and result_sha256 != item.get("expected_sha256")
    ):
        raise DownloadRefused(f"backend checksum mismatch: {manifest_key}")

    allowed_hosts = item["allowed_redirect_hosts"]
    effective_url = _canonicalize_url(
        result.get("effective_url"),
        allowed_hosts=allowed_hosts,
        label=f"effective URL for {manifest_key}",
        error_type=DownloadRefused,
    )
    if effective_url != result.get("effective_url"):
        raise DownloadRefused(f"effective URL is not canonical: {manifest_key}")
    attestation = result.get("endpoint_attestation")
    if not isinstance(attestation, Mapping):
        raise DownloadRefused(f"endpoint attestation is malformed: {manifest_key}")
    if attestation.get("attestation_version") != "1.0":
        raise DownloadRefused(f"unsupported endpoint attestation: {manifest_key}")
    if attestation.get("dns_rebinding_protected") is not True:
        raise DownloadRefused(f"DNS rebinding protection was not attested: {manifest_key}")
    peer_ip = str(attestation.get("peer_ip") or "")
    if not _is_public_ip(peer_ip):
        raise DownloadRefused(f"backend peer IP is not public: {manifest_key}")
    redirect_chain = attestation.get("redirect_chain")
    if (
        not isinstance(redirect_chain, list)
        or not redirect_chain
        or len(redirect_chain) > _MAX_REDIRECTS + 1
        or redirect_chain[0] != item.get("url")
        or redirect_chain[-1] != effective_url
    ):
        raise DownloadRefused(f"backend redirect chain is invalid: {manifest_key}")
    if attestation.get("redirect_count") != len(redirect_chain) - 1:
        raise DownloadRefused(
            f"backend redirect count attestation is incomplete: {manifest_key}"
        )
    peer_ips = attestation.get("peer_ips")
    if (
        not isinstance(peer_ips, list)
        or len(peer_ips) != len(redirect_chain)
        or not all(isinstance(value, str) and _is_public_ip(value) for value in peer_ips)
        or peer_ips[-1] != peer_ip
    ):
        raise DownloadRefused(
            f"backend per-hop peer attestation is incomplete: {manifest_key}"
        )
    for index, hop in enumerate(redirect_chain):
        canonical_hop = _canonicalize_url(
            hop,
            allowed_hosts=allowed_hosts,
            label=f"redirect hop {index} for {manifest_key}",
            error_type=DownloadRefused,
        )
        if canonical_hop != hop:
            raise DownloadRefused(f"redirect hop is not canonical: {manifest_key}")
    if attestation.get("requested_url") != item.get("url"):
        raise DownloadRefused(f"endpoint attestation requested URL mismatch: {manifest_key}")
    if attestation.get("effective_url") != effective_url:
        raise DownloadRefused(f"endpoint attestation effective URL mismatch: {manifest_key}")
    return dict(result)


def _verify_backend_filesystem_effect(
    item: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any]:
    manifest_key = str(item["manifest_key"])
    if (
        item.get("checksum_scope") != "exact_full_object"
        or item.get("expected_sha256") is None
    ):
        raise DownloadRefused(
            f"execution requires an exact expected hash for transferred bytes: {manifest_key}"
        )
    destination = Path(str(item["destination"]))
    staging_root = Path(str(item["staging_root"]))
    try:
        root_real = staging_root.resolve(strict=True)
    except OSError as exc:
        raise DownloadRefused(
            f"staging root does not exist after backend success: {manifest_key}"
        ) from exc
    if root_real.is_symlink() or not root_real.is_dir():
        raise DownloadRefused(f"staging root is not a regular directory: {manifest_key}")
    try:
        destination_lstat = destination.lstat()
    except OSError as exc:
        raise DownloadRefused(
            f"backend reported success but destination does not exist: {manifest_key}"
        ) from exc
    if stat.S_ISLNK(destination_lstat.st_mode) or not stat.S_ISREG(
        destination_lstat.st_mode
    ):
        raise DownloadRefused(
            f"backend destination is not a regular non-symlink file: {manifest_key}"
        )
    try:
        destination.resolve(strict=True).relative_to(root_real)
    except (OSError, ValueError) as exc:
        raise DownloadRefused(
            f"backend destination is outside the staging root: {manifest_key}"
        ) from exc

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(destination, flags)
    except OSError as exc:
        raise DownloadRefused(
            f"backend destination cannot be opened safely: {manifest_key}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise DownloadRefused(
                f"backend destination is not a regular file: {manifest_key}"
            )
        if (
            opened.st_dev != destination_lstat.st_dev
            or opened.st_ino != destination_lstat.st_ino
        ):
            raise DownloadRefused(
                f"backend destination changed during verification: {manifest_key}"
            )
        digest = hashlib.sha256()
        byte_count = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            byte_count += len(chunk)
            digest.update(chunk)
    finally:
        os.close(descriptor)
    actual_sha256 = "sha256:" + digest.hexdigest()
    if byte_count != item.get("planned_transfer_bytes"):
        raise DownloadRefused(
            f"destination byte count does not match the plan: {manifest_key}"
        )
    if actual_sha256 != item.get("expected_sha256"):
        raise DownloadRefused(
            f"destination checksum does not match expected bytes: {manifest_key}"
        )
    if actual_sha256 != result.get("sha256"):
        raise DownloadRefused(
            f"backend checksum attestation does not match destination: {manifest_key}"
        )
    return {
        "verification_version": "1.0",
        "destination": str(destination),
        "regular_file": True,
        "symlink": False,
        "contained_in_staging_root": True,
        "bytes_verified": byte_count,
        "sha256": actual_sha256,
    }


def _validate_backend_execution_preconditions(item: Mapping[str, Any]) -> None:
    manifest_key = str(item["manifest_key"])
    if (
        item.get("checksum_scope") != "exact_full_object"
        or item.get("expected_sha256") is None
    ):
        raise DownloadRefused(
            f"execution requires an exact expected hash for transferred bytes: {manifest_key}"
        )
    destination = Path(str(item["destination"]))
    if destination.exists() or destination.is_symlink():
        raise DownloadRefused(
            f"destination already exists before backend transfer: {manifest_key}"
        )


def _verify_execution_audit_checkpoint(
    audit_log_path: str | Path | None,
    audit_checkpoint: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if audit_log_path is None or not isinstance(audit_checkpoint, Mapping):
        raise DownloadRefused(
            "transfer execution requires an external audit checkpoint and audit log"
        )
    if audit_checkpoint.get("checkpoint_version") != "1.0":
        raise DownloadRefused("unsupported audit checkpoint version")
    count = audit_checkpoint.get("record_count")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise DownloadRefused(
            "transfer execution requires a non-empty external audit checkpoint"
        )
    try:
        return verify_audit_log(
            audit_log_path,
            expected_head_sha256=audit_checkpoint.get("head_sha256"),
            expected_record_count=count,
        )
    except (OSError, ValueError) as exc:
        raise DownloadRefused(f"audit checkpoint verification failed: {exc}") from exc


def execute_download_plan(
    plan: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    approval: Mapping[str, Any],
    *,
    backend: ByteTransferBackend | None = None,
    authorized_signers: Mapping[str, Sequence[str] | str] | None = None,
    authorization_time: datetime | None = None,
    max_approval_age: timedelta = timedelta(hours=24),
    max_clock_skew: timedelta = timedelta(minutes=5),
    signature_verifier: ApprovalSignatureVerifier | None = None,
    approved_staging_roots: Sequence[str] | None = None,
    audit_log_path: str | Path | None = None,
    audit_checkpoint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate authorization, then require an explicitly supplied backend."""

    authorization = validate_execution_approval(
        plan,
        manifests,
        approval,
        authorized_signers=authorized_signers,
        authorization_time=authorization_time,
        max_approval_age=max_approval_age,
        max_clock_skew=max_clock_skew,
        signature_verifier=signature_verifier,
        approved_staging_roots=approved_staging_roots,
        require_signature=backend is not None,
    )
    if backend is None:
        return authorization
    checkpoint_report = _verify_execution_audit_checkpoint(
        audit_log_path, audit_checkpoint
    )
    results: list[dict[str, Any]] = []
    for item in plan["items"]:
        _validate_backend_execution_preconditions(item)
        raw_result = backend.transfer(dict(item))
        if not isinstance(raw_result, Mapping):
            raise DownloadRefused("backend result must be an object")
        validated_result = _validate_backend_result(item, raw_result)
        results.append(
            {
                **validated_result,
                "independent_filesystem_verification": (
                    _verify_backend_filesystem_effect(item, validated_result)
                ),
            }
        )
    return {
        **authorization,
        "status": "executed",
        "network_access_performed": True,
        "audit_checkpoint": checkpoint_report,
        "results": results,
    }


def load_approval(path: str | Path) -> dict[str, Any]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise DownloadRefused("approval file root must be an object")
    return value
