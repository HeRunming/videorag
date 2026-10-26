from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_smoke_authority.py"
SPEC = importlib.util.spec_from_file_location(
    "p23_102_smoke_authority", TOOL_PATH
)
assert SPEC and SPEC.loader
AUTHORITY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUTHORITY
SPEC.loader.exec_module(AUTHORITY)

NOW = dt.datetime(2026, 10, 14, 8, 0, tzinfo=dt.UTC)
CHECKED_REGISTRY = (
    ROOT
    / "data/restricted/p23_102_technical_smoke_v2"
    / "authority_registry.json"
)
EXPECTED_FINGERPRINTS = {
    "live_wiring_reviewer": (
        "sha256:"
        "d75604df8e6611f75043dbcebfce1f040752d4b764ec720c63cbae0607628a85"
    ),
    "red_team_reviewer": (
        "sha256:"
        "44816a89532f9502810cc7807475102b92d6a375e6e599cc7d992a3ff503490f"
    ),
}


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _write_json(path: Path, value: Any, mode: int = 0o600) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(mode)


def _authority_layout(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, dict[str, Any]]]:
    root = tmp_path / "smoke"
    root.mkdir(parents=True)
    registry_path = root / "authority_registry.json"
    authorities_root = root / "authorities"
    result = AUTHORITY.initialize_authorities(
        registry_path=registry_path,
        authorities_root=authorities_root,
        now=NOW,
    )
    assert result["status"] == "AUTHORITIES_INITIALIZED"
    return (
        registry_path,
        authorities_root,
        AUTHORITY.load_registry(registry_path),
    )


def _bound_execution(seed: str = "a") -> dict[str, Any]:
    fields = {
        field: f"sha256:{seed * 64}"
        for field in AUTHORITY.BINDING_FIELDS
    }
    return {
        "bindings": fields,
        "one_run_nonce": seed * 32,
        "declarations": {
            field: True for field in AUTHORITY.DECLARATION_FIELDS
        },
        "review_decision": "GO",
    }


def _request(
    receipt_id: str,
    *,
    issued: dt.datetime | None = None,
    expires: dt.datetime | None = None,
    bound_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": AUTHORITY.RECEIPT_REQUEST_SCHEMA,
        "receipt_id": receipt_id,
        "issued_at_utc": AUTHORITY.utc_text(
            issued or NOW - dt.timedelta(minutes=1)
        ),
        "expires_at_utc": AUTHORITY.utc_text(
            expires or NOW + dt.timedelta(minutes=5)
        ),
        "bound_execution": bound_execution or _bound_execution(),
    }


def _signed_receipt(
    tmp_path: Path,
    role: str,
    request: dict[str, Any],
    *,
    registry_path: Path,
    authorities_root: Path,
    now: dt.datetime = NOW,
) -> dict[str, Any]:
    stem = f"{role}-{request['receipt_id']}".replace("/", "_")
    payload_path = tmp_path / f"{stem}-request.json"
    output_path = tmp_path / f"{stem}-receipt.json"
    _write_json(payload_path, request)
    return AUTHORITY.sign_receipt(
        role,
        payload_path=payload_path,
        output_path=output_path,
        registry_path=registry_path,
        authorities_root=authorities_root,
        now=now,
    )


def _separate_custody_views(
    tmp_path: Path,
    *,
    registry_path: Path,
    authorities_root: Path,
) -> dict[str, tuple[Path, Path]]:
    views: dict[str, tuple[Path, Path]] = {}
    for role in AUTHORITY.ROLES:
        view = tmp_path / f"{role}-custody"
        private_root = view / "private"
        private_root.mkdir(parents=True, mode=0o700)
        private_root.chmod(0o700)
        view_registry = view / "authority_registry.json"
        shutil.copyfile(registry_path, view_registry)
        view_registry.chmod(0o644)
        shutil.copyfile(
            authorities_root / role / "private_key.pem",
            private_root / "private_key.pem",
        )
        (private_root / "private_key.pem").chmod(0o600)
        views[role] = (view_registry, private_root)
    return views


def _overlay(
    live: dict[str, Any],
    red: dict[str, Any],
    *,
    bound_execution: dict[str, Any] | None = None,
    issued: dt.datetime | None = None,
    expires: dt.datetime | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": AUTHORITY.OVERLAY_SCHEMA,
        "authorization_id": "authorization.p23_102.smoke.test",
        "issued_at_utc": AUTHORITY.utc_text(
            issued or NOW - dt.timedelta(minutes=2)
        ),
        "expires_at_utc": AUTHORITY.utc_text(
            expires or NOW + dt.timedelta(minutes=6)
        ),
        "bound_execution": bound_execution or _bound_execution(),
        "approvals": {
            "live_wiring_reviewer": live,
            "red_team_reviewer": red,
        },
    }


def test_initialization_is_idempotent_and_private_material_is_separate(
    tmp_path: Path,
) -> None:
    registry_path, authorities_root, registry = _authority_layout(tmp_path)
    second = AUTHORITY.initialize_authorities(
        registry_path=registry_path,
        authorities_root=authorities_root,
        now=NOW + dt.timedelta(minutes=1),
    )
    assert second["status"] == "AUTHORITIES_ALREADY_INITIALIZED"
    assert set(registry) == set(AUTHORITY.ROLES)
    assert _mode(registry_path) == 0o644
    assert _mode(authorities_root) == 0o700

    registry_text = registry_path.read_text(encoding="utf-8")
    fingerprints: set[str] = set()
    public_keys: set[str] = set()
    for role in AUTHORITY.ROLES:
        role_root = authorities_root / role
        private_key = role_root / "private_key.pem"
        assert _mode(role_root) == 0o700
        assert _mode(private_key) == 0o600
        private_text = private_key.read_text(encoding="ascii")
        assert "PRIVATE KEY" in private_text
        assert private_text not in registry_text
        assert "PRIVATE KEY" not in registry_text
        fingerprints.add(registry[role]["key_fingerprint"])
        public_keys.add(registry[role]["public_key_pem"])
    assert len(fingerprints) == len(public_keys) == 2


def test_each_signer_operates_with_only_registry_and_own_custody_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path, authorities_root, registry = _authority_layout(tmp_path)
    views = _separate_custody_views(
        tmp_path / "views",
        registry_path=registry_path,
        authorities_root=authorities_root,
    )
    private_reads: list[Path] = []
    original_read_bytes = Path.read_bytes

    def audited_read_bytes(path: Path) -> bytes:
        if path.name == "private_key.pem":
            private_reads.append(path)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", audited_read_bytes)
    receipts: dict[str, dict[str, Any]] = {}
    for role in AUTHORITY.ROLES:
        view_registry, private_root = views[role]
        operation_root = tmp_path / f"{role}-operation"
        operation_root.mkdir()
        payload_path = operation_root / "request.json"
        output_path = operation_root / "receipt.json"
        _write_json(payload_path, _request(f"receipt.{role}.isolated"))
        before = len(private_reads)
        receipts[role] = AUTHORITY.sign_receipt(
            role,
            payload_path=payload_path,
            output_path=output_path,
            registry_path=view_registry,
            private_root=private_root,
            now=NOW,
        )
        assert private_reads[before:] == [
            private_root / "private_key.pem"
        ]
        assert set(private_root.parent.iterdir()) == {
            private_root,
            view_registry,
        }
        assert set(private_root.iterdir()) == {
            private_root / "private_key.pem"
        }
        AUTHORITY.verify_receipt(
            receipts[role],
            registry=registry,
            now=NOW,
            expected_role=role,
        )

    assert (
        receipts["live_wiring_reviewer"]["signed_payload"]["key_fingerprint"]
        != receipts["red_team_reviewer"]["signed_payload"][
            "key_fingerprint"
        ]
    )


@pytest.mark.parametrize(
    ("signing_role", "custody_role"),
    [
        ("live_wiring_reviewer", "red_team_reviewer"),
        ("red_team_reviewer", "live_wiring_reviewer"),
    ],
)
def test_signer_cannot_use_other_roles_private_key(
    tmp_path: Path,
    signing_role: str,
    custody_role: str,
) -> None:
    registry_path, authorities_root, _ = _authority_layout(tmp_path)
    views = _separate_custody_views(
        tmp_path / "views",
        registry_path=registry_path,
        authorities_root=authorities_root,
    )
    custody_registry, custody_private_root = views[custody_role]
    payload_path = tmp_path / "request.json"
    output_path = tmp_path / "receipt.json"
    _write_json(
        payload_path,
        _request(f"receipt.{signing_role}.wrong-custody"),
    )

    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.sign_receipt(
            signing_role,
            payload_path=payload_path,
            output_path=output_path,
            registry_path=custody_registry,
            private_root=custody_private_root,
            now=NOW,
        )
    assert caught.value.code == "PRIVATE_KEY_REGISTRY_MISMATCH"
    assert not output_path.exists()


def test_explicit_private_key_path_has_no_shared_parent_dependency(
    tmp_path: Path,
) -> None:
    registry_path, authorities_root, registry = _authority_layout(tmp_path)
    role = "red_team_reviewer"
    detached_root = tmp_path / "detached-red-custody"
    detached_root.mkdir(mode=0o700)
    detached_key = detached_root / "red-review-key.pem"
    shutil.copyfile(
        authorities_root / role / "private_key.pem", detached_key
    )
    detached_key.chmod(0o600)
    payload_path = tmp_path / "request.json"
    output_path = tmp_path / "receipt.json"
    _write_json(payload_path, _request("receipt.red-team.detached"))

    receipt = AUTHORITY.sign_receipt(
        role,
        payload_path=payload_path,
        output_path=output_path,
        registry_path=registry_path,
        private_key=detached_key,
        now=NOW,
    )
    verified = AUTHORITY.verify_receipt(
        receipt,
        registry=registry,
        now=NOW,
        expected_role=role,
    )
    assert verified["key_fingerprint"] == registry[role]["key_fingerprint"]


def test_registry_is_public_only_and_verification_needs_no_private_root(
    tmp_path: Path,
) -> None:
    registry_path, authorities_root, registry = _authority_layout(tmp_path)
    receipts = {
        role: _signed_receipt(
            tmp_path,
            role,
            _request(f"receipt.{role}.public-verification"),
            registry_path=registry_path,
            authorities_root=authorities_root,
        )
        for role in AUTHORITY.ROLES
    }
    overlay_path = tmp_path / "overlay.json"
    _write_json(
        overlay_path,
        _overlay(
            receipts["live_wiring_reviewer"],
            receipts["red_team_reviewer"],
        ),
    )
    registry_document = json.loads(registry_path.read_text(encoding="utf-8"))
    serialized = json.dumps(registry_document, sort_keys=True)
    assert "PRIVATE KEY" not in serialized
    assert "private_key" not in serialized.lower()

    shutil.rmtree(authorities_root)
    verified = AUTHORITY.verify_receipt_file(
        tmp_path
        / "live_wiring_reviewer-"
        "receipt.live_wiring_reviewer.public-verification-receipt.json",
        registry_path=registry_path,
        now=NOW,
    )
    assert verified == receipts["live_wiring_reviewer"]["signed_payload"]
    assert verified["authority_id"] == registry[
        "live_wiring_reviewer"
    ]["authority_id"]
    overlay_result = AUTHORITY.verify_overlay_file(
        overlay_path,
        registry_path=registry_path,
        now=NOW,
    )
    assert overlay_result["status"] == "OVERLAY_APPROVALS_VALID"


def test_checked_registry_is_public_only_and_fingerprints_are_retained(
) -> None:
    registry = AUTHORITY.load_registry(CHECKED_REGISTRY)
    registry_text = CHECKED_REGISTRY.read_text(encoding="utf-8")
    assert "PRIVATE KEY" not in registry_text
    assert "private_key" not in registry_text.lower()
    assert {
        role: registry[role]["key_fingerprint"]
        for role in AUTHORITY.ROLES
    } == EXPECTED_FINGERPRINTS
    assert len(
        {registry[role]["public_key_pem"] for role in AUTHORITY.ROLES}
    ) == len(AUTHORITY.ROLES)


def test_partial_or_permission_drift_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "smoke"
    root.mkdir()
    registry_path = root / "authority_registry.json"
    authorities_root = root / "authorities"
    registry_path.write_text("{}", encoding="utf-8")
    registry_path.chmod(0o644)
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.initialize_authorities(
            registry_path=registry_path,
            authorities_root=authorities_root,
            now=NOW,
        )
    assert caught.value.code == "PARTIAL_AUTHORITY_STATE"

    registry_path.unlink()
    registry_path, authorities_root, _ = _authority_layout(tmp_path / "full")
    private_key = (
        authorities_root / "live_wiring_reviewer/private_key.pem"
    )
    private_key.chmod(0o644)
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.initialize_authorities(
            registry_path=registry_path,
            authorities_root=authorities_root,
            now=NOW,
        )
    assert caught.value.code == "PRIVATE_KEY_FILE_INVALID"


def test_registry_rejects_forged_ids_and_copied_same_key(
    tmp_path: Path,
) -> None:
    registry_path, _, _ = _authority_layout(tmp_path)
    document = json.loads(registry_path.read_text(encoding="utf-8"))

    forged = copy.deepcopy(document)
    forged["authorities"][0]["authority_id"] = (
        "p23_102.live_wiring_reviewer.forged00"
    )
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.validate_registry(forged)
    assert caught.value.code == "REGISTRY_INVALID"

    copied = copy.deepcopy(document)
    copied["authorities"][1]["public_key_pem"] = copied["authorities"][0][
        "public_key_pem"
    ]
    copied["authorities"][1]["key_fingerprint"] = copied["authorities"][0][
        "key_fingerprint"
    ]
    copied["authorities"][1]["authority_id"] = (
        "p23_102.red_team_reviewer."
        + copied["authorities"][0]["key_fingerprint"][7:23]
    )
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.validate_registry(copied)
    assert caught.value.code == "REGISTRY_INDEPENDENCE_INVALID"


def test_receipt_rejects_signature_tamper_forged_id_and_role_swap(
    tmp_path: Path,
) -> None:
    registry_path, authorities_root, registry = _authority_layout(tmp_path)
    live = _signed_receipt(
        tmp_path,
        "live_wiring_reviewer",
        _request("receipt.live-wiring.test"),
        registry_path=registry_path,
        authorities_root=authorities_root,
    )
    verified = AUTHORITY.verify_receipt(
        live,
        registry=registry,
        now=NOW,
        expected_role="live_wiring_reviewer",
    )
    assert verified["bound_execution"]["review_decision"] == "GO"

    tampered_signature = copy.deepcopy(live)
    replacement = (
        "A"
        if tampered_signature["signature_base64"][0] != "A"
        else "B"
    )
    tampered_signature["signature_base64"] = (
        replacement + tampered_signature["signature_base64"][1:]
    )
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.verify_receipt(
            tampered_signature, registry=registry, now=NOW
        )
    assert caught.value.code == "SIGNATURE_INVALID"

    forged_id = copy.deepcopy(live)
    forged_id["signed_payload"]["authority_id"] = (
        "p23_102.live_wiring_reviewer.forged00"
    )
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.verify_receipt(forged_id, registry=registry, now=NOW)
    assert caught.value.code == "AUTHORITY_NOT_ALLOWLISTED"

    role_swap = copy.deepcopy(live)
    role_swap["signed_payload"]["role"] = "red_team_reviewer"
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.verify_receipt(role_swap, registry=registry, now=NOW)
    assert caught.value.code == "AUTHORITY_NOT_ALLOWLISTED"


def test_overlay_requires_two_valid_receipts_over_identical_payload(
    tmp_path: Path,
) -> None:
    registry_path, authorities_root, registry = _authority_layout(tmp_path)
    bound = _bound_execution()
    live = _signed_receipt(
        tmp_path,
        "live_wiring_reviewer",
        _request("receipt.live-wiring.test", bound_execution=bound),
        registry_path=registry_path,
        authorities_root=authorities_root,
    )
    red = _signed_receipt(
        tmp_path,
        "red_team_reviewer",
        _request("receipt.red-team.test", bound_execution=bound),
        registry_path=registry_path,
        authorities_root=authorities_root,
    )
    overlay = _overlay(live, red, bound_execution=bound)
    result = AUTHORITY.verify_overlay_approvals(
        overlay, registry=registry, now=NOW
    )
    assert result["status"] == "OVERLAY_APPROVALS_VALID"
    assert set(result["authority_ids"]) == set(AUTHORITY.ROLES)

    swapped = copy.deepcopy(overlay)
    swapped["approvals"]["live_wiring_reviewer"] = red
    swapped["approvals"]["red_team_reviewer"] = live
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.verify_overlay_approvals(
            swapped, registry=registry, now=NOW
        )
    assert caught.value.code == "ROLE_MISMATCH"

    duplicate_red = _signed_receipt(
        tmp_path,
        "red_team_reviewer",
        _request("receipt.live-wiring.test", bound_execution=bound),
        registry_path=registry_path,
        authorities_root=authorities_root,
    )
    duplicate_receipt_id = _overlay(
        live, duplicate_red, bound_execution=bound
    )
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.verify_overlay_approvals(
            duplicate_receipt_id, registry=registry, now=NOW
        )
    assert caught.value.code == "APPROVAL_INDEPENDENCE_INVALID"

    drifted_bound = _bound_execution("b")
    drifted = copy.deepcopy(overlay)
    drifted["bound_execution"] = drifted_bound
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.verify_overlay_approvals(
            drifted, registry=registry, now=NOW
        )
    assert caught.value.code == "BOUND_EXECUTION_MISMATCH"

    tampered_receipt = copy.deepcopy(overlay)
    tampered_receipt["approvals"]["red_team_reviewer"][
        "signed_payload"
    ]["bound_execution"]["bindings"]["runner_sha256"] = "sha256:" + "c" * 64
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.verify_overlay_approvals(
            tampered_receipt, registry=registry, now=NOW
        )
    assert caught.value.code == "SIGNATURE_INVALID"


def test_expired_and_out_of_window_approvals_fail_closed(
    tmp_path: Path,
) -> None:
    registry_path, authorities_root, registry = _authority_layout(tmp_path)
    bound = _bound_execution()
    expired = _signed_receipt(
        tmp_path,
        "live_wiring_reviewer",
        _request(
            "receipt.live-wiring.expired",
            issued=NOW - dt.timedelta(minutes=10),
            expires=NOW - dt.timedelta(minutes=1),
            bound_execution=bound,
        ),
        registry_path=registry_path,
        authorities_root=authorities_root,
        now=NOW - dt.timedelta(minutes=5),
    )
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.verify_receipt(
            expired,
            registry=registry,
            now=NOW + dt.timedelta(minutes=1),
        )
    assert caught.value.code == "EXPIRED"

    live = _signed_receipt(
        tmp_path,
        "live_wiring_reviewer",
        _request("receipt.live-wiring.window", bound_execution=bound),
        registry_path=registry_path,
        authorities_root=authorities_root,
    )
    red = _signed_receipt(
        tmp_path,
        "red_team_reviewer",
        _request("receipt.red-team.window", bound_execution=bound),
        registry_path=registry_path,
        authorities_root=authorities_root,
    )
    overlay = _overlay(
        live,
        red,
        bound_execution=bound,
        issued=NOW - dt.timedelta(seconds=30),
        expires=NOW + dt.timedelta(minutes=4),
    )
    with pytest.raises(AUTHORITY.AuthorityError) as caught:
        AUTHORITY.verify_overlay_approvals(
            overlay, registry=registry, now=NOW
        )
    assert caught.value.code == "APPROVAL_OUTSIDE_OVERLAY_WINDOW"


def test_receipt_and_overlay_never_contain_private_key_material(
    tmp_path: Path,
) -> None:
    registry_path, authorities_root, registry = _authority_layout(tmp_path)
    bound = _bound_execution()
    receipts = [
        _signed_receipt(
            tmp_path,
            role,
            _request(f"receipt.{role}.no-leak", bound_execution=bound),
            registry_path=registry_path,
            authorities_root=authorities_root,
        )
        for role in AUTHORITY.ROLES
    ]
    overlay = _overlay(receipts[0], receipts[1], bound_execution=bound)
    serialized = json.dumps(
        {"registry": registry, "receipts": receipts, "overlay": overlay},
        sort_keys=True,
    )
    assert "PRIVATE KEY" not in serialized
    for role in AUTHORITY.ROLES:
        private_text = (
            authorities_root / role / "private_key.pem"
        ).read_text(encoding="ascii")
        assert private_text not in serialized
