from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = (
    ROOT / "scripts/build_captaincook4d_wave0_full_timeline.py"
)
VERIFY_SCRIPT = (
    ROOT / "scripts/verify_captaincook4d_wave0_full_timeline.py"
)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_exposes_dry_smoke_full_and_resume_controls():
    build_cli = _module(BUILD_SCRIPT, "captaincook4d_build_cli_parser")
    args = build_cli.build_parser().parse_args([])
    assert args.execute is False
    assert args.mode == "smoke"
    assert args.resume is True
    assert args.smoke_seconds == 32.0
    assert args.device == "cpu"


def test_dry_preflight_reports_ready_without_decoding(capsys):
    build_cli = _module(BUILD_SCRIPT, "captaincook4d_build_cli_preflight")
    code = build_cli.main(["--repo-root", str(ROOT)])
    payload = capsys.readouterr().out
    assert code == 0
    assert "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY" in payload
    assert '"media_decoded": false' in payload
    assert '"passed": true' in payload


def test_verifier_fails_closed_when_requested_output_is_missing():
    verifier = _module(VERIFY_SCRIPT, "captaincook4d_verifier_gate")
    result = verifier.verify_index(
        ROOT,
        output_root=(
            "data/restricted/"
            "captaincook4d_wave0_index_v1_missing_fixture"
        ),
    )
    assert result["verified"] is False
    assert (
        result["decision"]
        == "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_REPAIR"
    )
    assert "output_root_mode_or_missing" in result["failures"]


def test_search_leakage_rejects_semantic_and_private_keys():
    verifier = _module(VERIFY_SCRIPT, "captaincook4d_verifier_leakage")
    index = {
        "modalities": {
            "speech": {
                "documents": [
                    {
                        "search_payload": {
                            "tokens": ["safe"],
                            "answer": "not allowed",
                        }
                    }
                ]
            }
        }
    }
    assert verifier._search_leakage(index)


def test_checkpoint_payload_rejects_internal_payload_tamper(tmp_path: Path):
    verifier = _module(VERIFY_SCRIPT, "captaincook4d_verifier_checkpoint")
    payload = {
        "layer_version": "opencv-routing/1.0",
        "records": [{"source_ref": "16_20"}],
    }
    checkpoint = {
        "key": "source/opencv-routing/1.0/base/0/config",
        "record_count": 1,
        "payload_hash": verifier._json_hash(payload),
    }
    path = tmp_path / "vision_routing.json"
    path.write_text(
        json.dumps(
            {
                **payload,
                "checkpoint_key": checkpoint["key"],
                "record_count": 1,
                "payload_hash": checkpoint["payload_hash"],
            }
        ),
        encoding="utf-8",
    )
    verifier._checkpoint_payload(path, checkpoint)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["records"][0]["source_ref"] = "15_29"
    path.write_text(json.dumps(body), encoding="utf-8")
    try:
        verifier._checkpoint_payload(path, checkpoint)
    except ValueError as exc:
        assert str(exc) == "CHECKPOINT_PAYLOAD_HASH_MISMATCH"
    else:
        raise AssertionError("tampered checkpoint payload was accepted")
