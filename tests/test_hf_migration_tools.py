from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prepare = load_script("prepare_hf_upload.py")
verify = load_script("verify_hf_mirror.py")


def minimal_manifest(root: Path) -> dict:
    return {
        "schema_version": "test",
        "repositories": {
            "dataset_public_metadata": {
                "repo_id_placeholder": "ORG/public",
                "repo_type": "dataset",
            },
            "dataset_private_derived": {
                "repo_id_placeholder": "ORG/private",
                "repo_type": "dataset",
            },
        },
        "assets": [
            {
                "logical_id": "public.one",
                "local_path": "public",
                "bytes": 5,
                "file_count": 1,
                "sha256_or_manifest_hash": "sha256:test",
                "license_source": "test",
                "sensitivity": "public",
                "target_repo_type": "dataset_public_metadata",
                "proposed_hf_path": "metadata/public/",
                "upload_policy": "public_metadata_only",
                "release_review_status": "approved",
                "reconstruction_command": "rebuild public",
                "dependencies": [],
            },
            {
                "logical_id": "restricted.one",
                "local_path": "restricted.bin",
                "bytes": 4,
                "file_count": 1,
                "sha256_or_manifest_hash": "sha256:test",
                "license_source": "test",
                "sensitivity": "restricted",
                "target_repo_type": "none",
                "proposed_hf_path": None,
                "upload_policy": "never_upload",
                "reconstruction_command": "reacquire",
                "dependencies": [],
            },
        ],
    }


def test_repository_manifest_has_required_fields_and_model_policy() -> None:
    manifest = prepare.load_manifest(
        ROOT / "data" / "migration" / "hf_asset_manifest.json"
    )
    assert len(manifest["assets"]) >= 30
    for asset in manifest["assets"]:
        assert prepare.REQUIRED_FIELDS <= asset.keys()
        if asset["logical_id"].startswith("model."):
            assert asset["upload_policy"] == "redownload_upstream"
            assert asset["target_repo_type"] == "upstream_model_reference_only"


def test_prepare_is_dry_run_and_never_stages_restricted(tmp_path: Path) -> None:
    (tmp_path / "public").mkdir()
    (tmp_path / "public" / "a.json").write_text("{}\n  ")
    (tmp_path / "restricted.bin").write_bytes(b"xxxx")
    manifest = minimal_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    plan = prepare.build_plan(
        manifest,
        manifest_path=manifest_path,
        root=tmp_path,
        hash_limit=1024,
    )

    assert plan["dry_run"] is True
    assert plan["safety"]["tokens_read"] is False
    assert plan["safety"]["uploads_performed"] is False
    public = next(item for item in plan["assets"] if item["logical_id"] == "public.one")
    restricted = next(
        item for item in plan["assets"] if item["logical_id"] == "restricted.one"
    )
    assert public["stageable"] is True
    assert public["file_checks"][0]["checksum"].startswith("sha256:")
    assert "hf upload " in public["proposed_commands"][0]
    assert restricted["stageable"] is False
    assert restricted["proposed_commands"] == []


def test_prepare_rejects_symlinks_without_following(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    source = tmp_path / "public"
    source.mkdir()
    (source / "safe.txt").write_text("safe")
    (source / "link.txt").symlink_to(outside)

    inspection = prepare.inspect_path(tmp_path, "public")

    assert inspection["status"] == "blocked"
    assert inspection["file_count"] == 1
    assert any("symlink file rejected" in item for item in inspection["blockers"])


def test_prepare_multi_member_file_path_matches_upload_destination(
    tmp_path: Path,
) -> None:
    first = tmp_path / "one.json"
    second = tmp_path / "folder"
    first.write_text("{}")
    second.mkdir()
    (second / "two.json").write_text("{}")
    manifest = minimal_manifest(tmp_path)
    asset = manifest["assets"][0]
    asset.update(
        {
            "logical_id": "private.multi",
            "local_path": "one.json and folder",
            "local_members": ["one.json", "folder"],
            "bytes": 4,
            "file_count": 2,
            "target_repo_type": "dataset_private_derived",
            "proposed_hf_path": "derived/multi/",
            "upload_policy": "private_derived_index",
        }
    )
    manifest["assets"] = [asset]

    plan = prepare.build_plan(
        manifest,
        manifest_path=tmp_path / "manifest.json",
        root=tmp_path,
        hash_limit=1024,
    )
    item = plan["assets"][0]
    paths = {file["hf_path"] for file in item["file_checks"]}

    assert paths == {"derived/multi/one.json", "derived/multi/folder/two.json"}
    assert any(command.endswith("derived/multi/one.json") for command in item["proposed_commands"])


def test_verify_plan_checks_hash_and_private_modes(tmp_path: Path) -> None:
    mirror = tmp_path / "mirror"
    target = mirror / "derived" / "asset"
    target.mkdir(parents=True)
    payload = target / "a.json"
    payload.write_text('{"ok": true}\n')
    target.chmod(0o700)
    (mirror / "derived").chmod(0o700)
    mirror.chmod(0o700)
    payload.chmod(0o600)
    checksum = "sha256:" + prepare.sha256_file(payload)
    plan = {
        "assets": [
            {
                "logical_id": "derived.one",
                "upload_policy": "private_derived_index",
                "stageable": True,
                "proposed_hf_path": "derived/asset/",
                "inspection": {"local_path": "source"},
                "file_checks": [
                    {
                        "path": "source/a.json",
                        "bytes": payload.stat().st_size,
                        "checksum": checksum,
                    }
                ],
            }
        ]
    }
    manifest = {"assets": []}

    report = verify.verify(
        mirror,
        manifest=manifest,
        plan=plan,
        policies={"private_derived_index"},
        require_private_modes=True,
        allow_extra=False,
    )

    assert report["status"] == "pass"
    assert report["verified_file_count"] == 1

    payload.write_text('{"ok": false}\n')
    failed = verify.verify(
        mirror,
        manifest=manifest,
        plan=plan,
        policies={"private_derived_index"},
        require_private_modes=True,
        allow_extra=False,
    )
    assert failed["status"] == "fail"
    assert any(item["check"] == "size_mismatch" for item in failed["findings"])


def test_verify_rejects_symlinks_and_open_permissions(tmp_path: Path) -> None:
    mirror = tmp_path / "mirror"
    mirror.mkdir(mode=0o700)
    payload = mirror / "payload.json"
    payload.write_text("{}")
    payload.chmod(0o644)
    (mirror / "link.json").symlink_to(payload)

    report = verify.verify(
        mirror,
        manifest={"assets": []},
        plan={"assets": []},
        policies={"private_derived_index"},
        require_private_modes=True,
        allow_extra=True,
    )

    checks = {item["check"] for item in report["findings"]}
    assert report["status"] == "fail"
    assert "tree_safety" in checks
    assert "permission_too_open" in checks
