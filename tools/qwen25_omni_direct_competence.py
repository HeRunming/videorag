#!/usr/bin/env python3
"""Task 198 governed Qwen2.5-Omni direct-A/V competence execution.

The Task-158 direct-A/V group is public and fictional, but the model-facing
media, prompt policy, runner, and authorization still need a prospective
execution freeze. This tool therefore has three strictly ordered phases:

* ``--freeze`` verifies eligibility, materializes local synthetic media, and
  seals all model-facing inputs before inference.
* ``--execute`` verifies the freeze, runs the exact local Qwen Omni thinker on
  CPU BF16 once, preserves every raw output, and seals the submission.
* ``--evaluate`` verifies the sealed run, invokes the frozen Task-158
  evaluator, and performs an independent component audit.

No scientific media, GPU, remote API, network access, semantic repair,
best-of-N, voting, or deterministic answer substitution is permitted.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import resource
import signal
import stat
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines.adapters import AdapterContext, DirectAVAdapter
from av_trace_strong_baselines.competence import (
    evaluate_competence_submission,
    load_submission,
    load_suite,
    model_public_case,
)
from av_trace_strong_baselines.contracts import (
    InferenceStatus,
    LoadStatus,
    ModelBinding,
    sha256_json,
)
from av_trace_strong_baselines.errors import SchemaViolation
from av_trace_strong_baselines.runtime import SCHEMA_REPAIRABLE_ERRORS
from av_trace_strong_baselines.schemas import parse_strict_json
from av_trace_strong_baselines.security import (
    OutputProvenance,
    assert_public_surface,
)
from tools import qwen25_omni7b_acquisition as acquisition

TASK_ID = 198
CURRENT_DATE = "2026-10-10"
SUITE = Path("data/rehearsal_plan/strong_baseline_competence_suite_v1.json")
OUTPUT_DIR = Path(
    "data/restricted/strong_baselines/qwen25_omni_direct_competence_v1"
)
SNAPSHOT = Path(
    "data/restricted/strong_baselines/models/"
    "Qwen--Qwen2.5-Omni-7B--ae9e1690543f"
)
ACQUISITION_MANIFEST = Path(
    "data/restricted/strong_baselines/manifests/"
    "qwen25_omni7b_acquisition.json"
)
CANARY = Path(
    "data/restricted/strong_baselines/acquisition_records/"
    "qwen25-omni7b-ae9e1690543f/task197_cpu_canary.json"
)
GRANITE_RUN = Path(
    "data/restricted/strong_baselines/granite33_competence_v1"
)

MODEL_REPO_ID = "Qwen/Qwen2.5-Omni-7B"
MODEL_REVISION = "ae9e1690543ffd5c0221dc27f79834d0294cba00"
SUITE_HASH = (
    "sha256:7b8f8d021b24cb244f0df0f6b02b3da91120df3817a5366350895eb24f4646dc"
)
SUITE_FILE_SHA256 = (
    "1e3bec6e30e63f705cc2d49b010fdf6479b61f9b66aa7a1ca17f90a3b453afb4"
)
EVALUATOR_SHA256 = (
    "30236a0cf5e2ebb75245f80632f37d59fbf51e2c27d7c54d5c413e41d274e1b0"
)
COMPETENCE_MODULE_SHA256 = (
    "bf99f8c888bdd3ba2952df0b6f2ff25c050398b9711dbc0e1aa9a779e20c2fd4"
)
ADAPTER_MODULE_SHA256 = (
    "3cc9b9544c408eade40d44fc2cb2a668d9bb642ca9ab9bbbb67c21975b8c0a63"
)
FINAL_SCHEMA_SHA256 = (
    "54b99097a2030f68c0660ea2405500636cf26e1381f40afdaf23679b1f9abf83"
)

THREADS = 8
MAX_NEW_TOKENS = 512
CONTEXT_CAP = 32_768
SCHEMA_RETRIES = 1
ADDRESS_SPACE_LIMIT_BYTES = 96 * 1024**3
WHOLE_RUN_TIMEOUT_SECONDS = 4 * 60 * 60
SCHEMA_ONLY_ERRORS = SCHEMA_REPAIRABLE_ERRORS | {
    "FINAL_ENVELOPE_FIELD_SET_MISMATCH",
    "CLAIM_TO_CITATIONS_NOT_OBJECT",
}
SUBSTANTIVE_COUNT = 24
RUNTIME_COUNT = 6
FREEZE_FILES = (
    "eligibility_audit.json",
    "public_direct_suite.json",
    "prompt_policy.json",
    "media_manifest.json",
    "runner_manifest.json",
)
RUN_FILES = (
    "authorization_claim.json",
    "submission.json",
    "raw_attempts.jsonl",
    "run_metadata.json",
    "execution_manifest.json",
)


class DirectCompetenceError(RuntimeError):
    """Fail-closed Task-198 execution error."""


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path, block_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(payload)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    atomic_bytes(
        path,
        (
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n"
        ).encode("utf-8"),
        mode=mode,
    )


def atomic_jsonl(
    path: Path, rows: Sequence[Mapping[str, Any]], *, mode: int = 0o600
) -> None:
    payload = "".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
        for row in rows
    )
    atomic_bytes(path, payload.encode("utf-8"), mode=mode)


def _binding(value: Mapping[str, Any]) -> ModelBinding:
    return ModelBinding(
        repo_id=str(value["repo_id"]),
        revision=str(value["revision"]),
        role=str(value["role"]),
        processor_revision=str(value["processor_revision"]),
        tokenizer_revision=str(value["tokenizer_revision"]),
    )


def _direct_cases(suite: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = suite["cases"]["direct_av"]
    if not isinstance(rows, list):
        raise DirectCompetenceError("DIRECT_SUITE_NOT_LIST")
    return rows


def _validate_frozen_sources(
    root: Path,
) -> tuple[dict[str, Any], ModelBinding, Path]:
    suite_path = root / SUITE
    if sha256_file(suite_path) != SUITE_FILE_SHA256:
        raise DirectCompetenceError("SUITE_FILE_SHA256_MISMATCH")
    suite = load_suite(suite_path)
    if suite["suite_hash"] != SUITE_HASH:
        raise DirectCompetenceError("SUITE_SEMANTIC_HASH_MISMATCH")
    if suite.get("execution_status") != "NOT_RUN":
        raise DirectCompetenceError("ORIGINAL_SUITE_EXECUTION_STATUS_MUTATED")
    if suite.get("model_results_present") is not False:
        raise DirectCompetenceError("ORIGINAL_SUITE_MODEL_RESULTS_PRESENT")
    rows = _direct_cases(suite)
    counts = Counter(str(row["case_type"]) for row in rows)
    if counts != {"direct_av": SUBSTANTIVE_COUNT, "runtime_failure": RUNTIME_COUNT}:
        raise DirectCompetenceError(f"DIRECT_CASE_COUNTS_MISMATCH:{dict(counts)}")
    if len(rows) != SUBSTANTIVE_COUNT + RUNTIME_COUNT:
        raise DirectCompetenceError("DIRECT_GROUP_ENTRY_COUNT_MISMATCH")
    if suite["content_boundary"] != {
        "fictional_generated_primitives_only": True,
        "public_cases_only": True,
        "contains_scientific_family_content": False,
        "contains_real_benchmark_ground_truth": False,
        "contains_evaluator_private_benchmark_fields": False,
        "model_inputs_are_allowlisted_from_public_input_only": True,
    }:
        raise DirectCompetenceError("SUITE_CONTENT_BOUNDARY_MISMATCH")
    binding = _binding(suite["bindings"]["primary_direct"])
    if (
        binding.repo_id != MODEL_REPO_ID
        or binding.revision != MODEL_REVISION
        or binding.resolved_processor_revision != MODEL_REVISION
        or binding.resolved_tokenizer_revision != MODEL_REVISION
        or binding.role != "DIRECT_AV_MODEL"
    ):
        raise DirectCompetenceError("SUITE_QWEN_DIRECT_BINDING_MISMATCH")

    source_hashes = {
        "scripts/evaluate_strong_baseline_competence.py": EVALUATOR_SHA256,
        "src/av_trace_strong_baselines/competence.py": (
            COMPETENCE_MODULE_SHA256
        ),
        "src/av_trace_strong_baselines/adapters.py": ADAPTER_MODULE_SHA256,
        "docs/spec/final_answer_schema.json": FINAL_SCHEMA_SHA256,
    }
    for name, expected in source_hashes.items():
        if sha256_file(root / name) != expected:
            raise DirectCompetenceError(f"FROZEN_SOURCE_SHA256_MISMATCH:{name}")

    manifest = load_json(root / ACQUISITION_MANIFEST)
    canary = load_json(root / CANARY)
    if (
        manifest.get("decision") != "QWEN25_OMNI7B_ACQUISITION_READY"
        or manifest.get("status") != "TECHNICAL_READY_NO_COMPETENCE_CLAIM"
    ):
        raise DirectCompetenceError("QWEN_ACQUISITION_NOT_READY")
    if (
        canary.get("status") != "TECHNICAL_READY_GENERATION_VALID"
        or canary.get("local_files_only") is not True
        or canary.get("trust_remote_code") is not False
        or canary.get("device") != "cpu"
        or canary.get("dtype") != "bfloat16"
        or canary.get("strict_final_output_valid") is not True
        or canary.get("competence_claimed") is not False
    ):
        raise DirectCompetenceError("QWEN_CANARY_CONTRACT_MISMATCH")
    plan = load_json(root / acquisition.PLAN)
    acquisition.validate_plan(plan)
    snapshot = root / SNAPSHOT
    if (root / plan["model"]["snapshot_dir"]).resolve() != snapshot.resolve():
        raise DirectCompetenceError("QWEN_SNAPSHOT_PATH_MISMATCH")
    acquisition.validate_snapshot(plan, snapshot)
    return suite, binding, snapshot


def _source_occurrence_audit(root: Path, case_ids: set[str]) -> dict[str, Any]:
    allowed = {
        str(SUITE),
        "scripts/generate_strong_baseline_competence_suite.py",
        "src/av_trace_strong_baselines/competence.py",
        "tests/test_strong_baseline_adapters.py",
    }
    searched_roots = [
        root / "data/restricted/strong_baselines",
        root / "docs/review",
        root / "orchestration/results",
        root / "tools",
    ]
    occurrences: dict[str, list[str]] = defaultdict(list)
    for base in searched_roots:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if (
                not path.is_file()
                or path.is_symlink()
                or "__pycache__" in path.parts
                or path.suffix in {".pyc", ".safetensors", ".pt", ".mp4"}
            ):
                continue
            rel = str(path.relative_to(root))
            if rel in allowed or rel.startswith(str(OUTPUT_DIR)):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for case_id in case_ids:
                if case_id in text:
                    occurrences[case_id].append(rel)
    return {
        "searched_roots": [str(path.relative_to(root)) for path in searched_roots],
        "case_id_occurrences_outside_frozen_definition": dict(occurrences),
        "direct_case_outputs_found": bool(occurrences),
    }


def _eligibility_audit(
    root: Path, suite: Mapping[str, Any], binding: ModelBinding
) -> dict[str, Any]:
    rows = _direct_cases(suite)
    case_ids = {str(row["case_id"]) for row in rows}
    granite_eligibility = load_json(root / GRANITE_RUN / "direct_av_eligibility.json")
    granite_seal = load_json(root / GRANITE_RUN / "seal.json")
    granite_audit = load_json(root / GRANITE_RUN / "independent_audit.json")
    sealed_record = granite_seal["files"]["direct_av_eligibility.json"]
    granite_record_valid = (
        sha256_file(root / GRANITE_RUN / "direct_av_eligibility.json")
        == sealed_record["sha256"]
        and (root / GRANITE_RUN / "direct_av_eligibility.json").stat().st_size
        == sealed_record["bytes"]
    )
    granite_unconsumed = (
        granite_record_valid
        and granite_eligibility.get("eligibility") == "STRUCTURALLY_INELIGIBLE"
        and granite_eligibility.get("model_calls_executed") == 0
        and granite_eligibility.get("score_rows_created") == 0
        and granite_eligibility.get("scored_as_zero") is False
        and granite_audit.get("direct_av", {}).get("model_calls_executed") == 0
        and granite_audit.get("direct_av", {}).get("score_rows_created") == 0
    )
    occurrences = _source_occurrence_audit(root, case_ids)
    qwen_canary_raw = (
        root
        / "data/restricted/strong_baselines/acquisition_records/"
        "qwen25-omni7b-ae9e1690543f/task197_cpu_canary_raw_output.txt"
    ).read_text(encoding="utf-8")
    canary_overlap = sorted(
        case_id for case_id in case_ids if case_id in qwen_canary_raw
    )
    eligible = (
        granite_unconsumed
        and not occurrences["direct_case_outputs_found"]
        and not canary_overlap
    )
    return {
        "schema_version": "av-trace.qwen25-omni-direct-eligibility/1.0",
        "task_id": TASK_ID,
        "audited_at": utc_now(),
        "suite_id": suite["suite_id"],
        "suite_hash": suite["suite_hash"],
        "suite_file_sha256": sha256_file(root / SUITE),
        "binding": binding.to_dict(),
        "granite_direct_record_seal_verified": granite_record_valid,
        "granite_direct_unconsumed": granite_unconsumed,
        "granite_model_calls_executed": granite_eligibility.get(
            "model_calls_executed"
        ),
        "granite_score_rows_created": granite_eligibility.get(
            "score_rows_created"
        ),
        "qwen_task197_case_id_overlap": canary_overlap,
        "repository_occurrence_audit": occurrences,
        "separate_role_binding": {
            "granite_role": "TOOL_CONTROLLER_BACKBONE/GROUNDED_FINALIZER",
            "qwen_role": binding.role,
            "direct_group_bound_to_qwen": True,
        },
        "direct_substantive_cases": SUBSTANTIVE_COUNT,
        "direct_runtime_fixtures": RUNTIME_COUNT,
        "eligibility": (
            "ELIGIBLE_UNSEEN_FOR_QWEN_OMNI"
            if eligible
            else "OVERLAP_OR_CONSUMPTION_CONCERN"
        ),
        "prospective_new_suite_required": not eligible,
    }


def _prompt_policy() -> dict[str, Any]:
    return {
        "schema_version": "av-trace.qwen25-omni-direct-prompt-policy/1.0",
        "task_id": TASK_ID,
        "policy_date": CURRENT_DATE,
        "system_prompt": (
            "Return exactly one strict JSON object and no other text. "
            "Do not use markdown. Use only the supplied public input and the "
            "exposed local audiovisual media. Never invent facts, evidence, "
            "citations, modalities, intervals, claim handles, or answers."
        ),
        "output_contract": {
            "top_level_exact_keys": ["final_answer", "claim_to_citations"],
            "final_answer_exact_keys": [
                "p_sufficient",
                "verdict",
                "answer_mode",
                "claims",
                "diagnosis",
                "natural_language_answer",
                "termination_reason",
            ],
            "claim_exact_keys": [
                "claim_id",
                "registered_claim_id",
                "text",
                "confidence",
                "citations",
            ],
            "citation_exact_keys": [
                "observation_id",
                "interval",
                "modalities",
            ],
            "diagnosis_exact_keys": [
                "modality_probabilities",
                "hop_types",
                "cause_probabilities",
                "recovery_route_declared",
                "description",
            ],
            "strict_schema_file": "docs/spec/final_answer_schema.json",
            "strict_schema_sha256": FINAL_SCHEMA_SHA256,
        },
        "answer_policy": (
            "For sufficient evidence, answer_mode=answer, verdict=sufficient, "
            "p_sufficient>=0.5, one model-authored claim for every supplied "
            "claim_handle, exact exposed citation IDs/intervals/modalities, "
            "and a nonempty natural_language_answer. For missing or masked "
            "required evidence, answer_mode=abstain, verdict=insufficient, "
            "p_sufficient<=0.5, claims=[], natural_language_answer='', "
            "claim_to_citations={}, the missing modality probability at "
            "least 0.5, and the public question's named missing hop in "
            "diagnosis.hop_types."
        ),
        "generation": {
            "do_sample": False,
            "max_new_tokens": MAX_NEW_TOKENS,
            "context_cap_processor_tokens": CONTEXT_CAP,
            "json_boundary_stopping": True,
            "schema_only_retries_per_case": SCHEMA_RETRIES,
            "semantic_retries": 0,
            "voting": False,
            "best_of_n": False,
            "semantic_repair": False,
            "parser_extraction": False,
            "field_filling": False,
        },
        "packing_policy": (
            "question_independent_source_uniform_chronological"
        ),
        "strict_native_av": True,
        "use_audio_in_video": True,
    }


def _public_direct_suite(suite: Mapping[str, Any]) -> dict[str, Any]:
    cases = [
        {
            "case_id": row["case_id"],
            **model_public_case(row),
            "stratum": row["stratum"],
        }
        for row in _direct_cases(suite)
    ]
    return {
        "schema_version": "av-trace.qwen25-omni-direct-public-suite/1.0",
        "task_id": TASK_ID,
        "source_suite_id": suite["suite_id"],
        "source_suite_hash": suite["suite_hash"],
        "cases": cases,
        "scoring_targets_included": False,
        "scientific_content_included": False,
    }


def _tone(
    *,
    frequency_hz: float,
    duration_s: float,
    sample_rate_hz: int = 16_000,
    amplitude: float = 0.18,
) -> Any:
    import numpy as np

    samples = max(1, round(duration_s * sample_rate_hz))
    times = np.arange(samples, dtype=np.float64) / sample_rate_hz
    signal_value = amplitude * np.sin(2 * np.pi * frequency_hz * times)
    edge = min(samples // 2, int(0.025 * sample_rate_hz))
    if edge:
        envelope = np.ones(samples, dtype=np.float64)
        envelope[:edge] = np.linspace(0.0, 1.0, edge, endpoint=False)
        envelope[-edge:] = np.linspace(1.0, 0.0, edge, endpoint=False)
        signal_value *= envelope
    return signal_value.astype(np.float32)


def _silence(duration_s: float, sample_rate_hz: int = 16_000) -> Any:
    import numpy as np

    return np.zeros(round(duration_s * sample_rate_hz), dtype=np.float32)


def _speech_like_solstice(sample_rate_hz: int = 16_000) -> Any:
    """Generate deterministic source-free speech-like synthetic audio.

    This is intentionally algorithmic local synthesis rather than a recorded
    person or an external TTS/API. The model-facing prompt never names the
    target word. The waveform is reused byte-for-byte for all speech replay
    groups.
    """

    import numpy as np

    rng = np.random.default_rng(198)

    def envelope(samples: int, attack_s: float, release_s: float) -> Any:
        values = np.ones(samples, dtype=np.float64)
        attack = min(samples, max(1, int(attack_s * sample_rate_hz)))
        release = min(samples, max(1, int(release_s * sample_rate_hz)))
        values[:attack] = np.linspace(0.0, 1.0, attack, endpoint=False)
        values[-release:] *= np.linspace(1.0, 0.0, release, endpoint=False)
        return values

    def voiced(
        duration_s: float,
        formants: Sequence[tuple[float, float, float]],
        fundamental_hz: float,
    ) -> Any:
        samples = int(duration_s * sample_rate_hz)
        times = np.arange(samples, dtype=np.float64) / sample_rate_hz
        waveform = np.zeros(samples, dtype=np.float64)
        for harmonic in range(1, int(6000 / fundamental_hz) + 1):
            frequency = harmonic * fundamental_hz
            spectral = 0.15 + sum(
                gain
                * np.exp(-0.5 * ((frequency - formant) / bandwidth) ** 2)
                for formant, bandwidth, gain in formants
            )
            amplitude = spectral / harmonic**0.8
            waveform += amplitude * np.sin(
                2 * np.pi * frequency * times + harmonic * 0.37
            )
        waveform /= max(float(np.abs(waveform).max()), 1e-6)
        return (
            waveform
            * envelope(samples, attack_s=0.018, release_s=0.028)
            * 0.48
        )

    def fricative(duration_s: float, center_hz: float) -> Any:
        samples = int(duration_s * sample_rate_hz)
        noise = rng.normal(size=samples)
        spectrum = np.fft.rfft(noise)
        frequencies = np.fft.rfftfreq(samples, 1 / sample_rate_hz)
        weights = np.exp(-0.5 * ((frequencies - center_hz) / 1500) ** 2)
        weights *= frequencies > 1400
        waveform = np.fft.irfft(spectrum * weights, samples)
        waveform /= max(float(np.abs(waveform).max()), 1e-6)
        return (
            waveform
            * envelope(samples, attack_s=0.008, release_s=0.018)
            * 0.36
        )

    def burst(duration_s: float) -> Any:
        samples = int(duration_s * sample_rate_hz)
        waveform = rng.normal(size=samples)
        waveform *= np.exp(
            -np.arange(samples, dtype=np.float64)
            / (sample_rate_hz * 0.018)
        )
        waveform /= max(float(np.abs(waveform).max()), 1e-6)
        return waveform * 0.43

    parts = [
        _silence(0.08, sample_rate_hz),
        fricative(0.16, 5400),
        voiced(
            0.20,
            [(650, 130, 1.0), (1050, 180, 0.7), (2500, 260, 0.35)],
            120,
        ),
        voiced(
            0.12,
            [(400, 100, 1.0), (1200, 160, 0.7), (2600, 250, 0.3)],
            115,
        ),
        fricative(0.11, 5000),
        _silence(0.022, sample_rate_hz),
        burst(0.05),
        voiced(
            0.17,
            [(350, 100, 1.0), (2000, 230, 0.9), (2800, 260, 0.35)],
            125,
        ),
        fricative(0.17, 5200),
        _silence(0.07, sample_rate_hz),
    ]
    waveform = np.concatenate(parts).astype(np.float32)
    waveform = np.clip(waveform, -0.95, 0.95)
    return waveform


def _wooden_knock(sample_rate_hz: int = 16_000) -> Any:
    import numpy as np

    rng = np.random.default_rng(172)
    duration_s = 1.0
    waveform = np.zeros(int(duration_s * sample_rate_hz), dtype=np.float32)
    for onset_s in (0.17, 0.47, 0.76):
        onset = int(onset_s * sample_rate_hz)
        samples = int(0.16 * sample_rate_hz)
        times = np.arange(samples, dtype=np.float64) / sample_rate_hz
        ring = (
            0.55 * np.sin(2 * np.pi * 185 * times)
            + 0.25 * np.sin(2 * np.pi * 370 * times)
            + 0.12 * rng.normal(size=samples)
        ) * np.exp(-times * 24)
        end = min(len(waveform), onset + samples)
        waveform[onset:end] += ring[: end - onset].astype(np.float32)
    return np.clip(waveform, -0.95, 0.95)


def _blue_flare_audio(sample_rate_hz: int = 16_000) -> Any:
    import numpy as np

    waveform = np.concatenate(
        [
            _silence(0.12, sample_rate_hz),
            _tone(
                frequency_hz=740,
                duration_s=0.20,
                sample_rate_hz=sample_rate_hz,
            ),
            _silence(0.18, sample_rate_hz),
            _tone(
                frequency_hz=1040,
                duration_s=0.23,
                sample_rate_hz=sample_rate_hz,
            ),
            _silence(0.27, sample_rate_hz),
        ]
    )
    return np.asarray(waveform[:sample_rate_hz], dtype=np.float32)


def _visual_frames(kind: str, *, fps: int = 4) -> list[Any]:
    import numpy as np

    frames = []
    height = width = 96
    for index in range(fps):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        if kind == "emerald":
            frame[:] = (12, 18, 16)
            frame[22:74, 22:74] = (20, 190, 105)
        elif kind == "blue_flare":
            frame[:] = (5, 8, 18)
            radius = 11 + index * 5
            yy, xx = np.ogrid[:height, :width]
            mask = (xx - 48) ** 2 + (yy - 48) ** 2 <= radius**2
            frame[mask] = (35, 125 + 25 * index, 255)
            frame[46:50, 12:84] = (105, 210, 255)
            frame[12:84, 46:50] = (105, 210, 255)
        else:
            frame[:] = (5, 5, 5)
        frames.append(frame)
    return frames


def _write_mp4(path: Path, *, visual_kind: str, audio: Any) -> dict[str, Any]:
    import av
    import numpy as np

    sample_rate_hz = 16_000
    fps = 4
    frames = _visual_frames(visual_kind, fps=fps)
    audio = np.asarray(audio, dtype=np.float32)
    if len(audio) < sample_rate_hz:
        audio = np.pad(audio, (0, sample_rate_hz - len(audio)))
    audio = audio[:sample_rate_hz]

    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    container = av.open(str(temporary), mode="w", format="mp4")
    video = container.add_stream("mpeg4", rate=fps)
    video.width = 96
    video.height = 96
    video.pix_fmt = "yuv420p"
    audio_stream = container.add_stream("aac", rate=sample_rate_hz)
    audio_stream.layout = "mono"
    for index, array in enumerate(frames):
        frame = av.VideoFrame.from_ndarray(array, format="rgb24")
        frame.pts = index
        frame.time_base = Fraction(1, fps)
        for packet in video.encode(frame):
            container.mux(packet)
    for packet in video.encode():
        container.mux(packet)
    cursor = 0
    while cursor < len(audio):
        chunk = audio[cursor : cursor + 1024]
        pcm = (np.clip(chunk, -1, 1) * 32767).astype(np.int16)[None, :]
        audio_frame = av.AudioFrame.from_ndarray(
            pcm, format="s16", layout="mono"
        )
        audio_frame.sample_rate = sample_rate_hz
        audio_frame.time_base = Fraction(1, sample_rate_hz)
        audio_frame.pts = cursor
        for packet in audio_stream.encode(audio_frame):
            container.mux(packet)
        cursor += len(chunk)
    for packet in audio_stream.encode():
        container.mux(packet)
    container.close()
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "mode": oct(stat.S_IMODE(path.stat().st_mode)),
        "duration_seconds": 1.0,
        "fps": fps,
        "width": 96,
        "height": 96,
        "sample_rate_hz": sample_rate_hz,
        "generated_locally": True,
        "scientific_media": False,
        "visual_kind": visual_kind,
    }


def _materialize_media(
    root: Path, suite: Mapping[str, Any], output_dir: Path
) -> dict[str, Any]:
    import numpy as np

    recipes: dict[str, dict[str, Any]] = {}
    media_dir = output_dir / "media"
    for case in _direct_cases(suite):
        if case["case_type"] != "direct_av":
            continue
        manifest = case["public_input"].get("media_exposure_manifest", [])
        if not manifest:
            continue
        locator = str(manifest[0]["asset_locator"])
        if locator in recipes:
            continue
        stratum = str(case["stratum"])
        index = int(locator.rsplit("/", 1)[-1])
        path = media_dir / f"strong_baseline_v1_{index:02d}.mp4"
        if stratum == "vision":
            audio = _silence(1.0)
            visual = "emerald"
            media_semantics = {
                "vision": "emerald geometric card",
                "audio": "silence",
            }
        elif stratum == "speech":
            audio = _speech_like_solstice()
            visual = "blank"
            media_semantics = {
                "vision": "blank dark frame",
                "audio": (
                    "deterministic locally synthesized speech-like utterance"
                ),
            }
        elif stratum == "ambient":
            audio = _wooden_knock()
            visual = "blank"
            media_semantics = {
                "vision": "blank dark frame",
                "audio": "three deterministic wooden-knock-like impacts",
            }
        elif stratum == "joint_av":
            audio = _blue_flare_audio()
            visual = "blue_flare"
            media_semantics = {
                "vision": "animated blue flare",
                "audio": "paired deterministic synthetic alert tones",
            }
        else:
            raise DirectCompetenceError(f"UNEXPECTED_MEDIA_STRATUM:{stratum}")
        record = _write_mp4(path, visual_kind=visual, audio=audio)
        record.update(
            {
                "asset_locator": locator,
                "stratum": stratum,
                "public_interval": manifest[0]["interval"],
                "public_modalities": manifest[0]["modalities"],
                "media_semantics_private_execution_record": media_semantics,
                "waveform_peak": float(np.abs(audio).max()),
            }
        )
        recipes[locator] = record
    if len(recipes) != 8:
        raise DirectCompetenceError("MEDIA_ASSET_COUNT_MISMATCH")
    return {
        "schema_version": "av-trace.qwen25-omni-direct-media-manifest/1.0",
        "task_id": TASK_ID,
        "packing_policy": (
            "question_independent_source_uniform_chronological"
        ),
        "assets": [recipes[key] for key in sorted(recipes)],
        "asset_count": len(recipes),
        "all_local_synthetic": True,
        "scientific_media_used": False,
    }


def _freeze(root: Path, output_dir: Path) -> dict[str, Any]:
    if (output_dir / "freeze_seal.json").exists():
        raise DirectCompetenceError("FREEZE_ALREADY_EXISTS")
    if (output_dir / "seal.json").exists():
        raise DirectCompetenceError("RUN_ALREADY_SEALED")
    suite, binding, snapshot = _validate_frozen_sources(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    eligibility = _eligibility_audit(root, suite, binding)
    if eligibility["eligibility"] != "ELIGIBLE_UNSEEN_FOR_QWEN_OMNI":
        raise DirectCompetenceError(
            "DIRECT_SUITE_REUSE_INELIGIBLE_GENERATE_NEW_SUITE_REQUIRED"
        )
    public_suite = _public_direct_suite(suite)
    prompt_policy = _prompt_policy()
    media_manifest = _materialize_media(root, suite, output_dir)
    runner_manifest = {
        "schema_version": "av-trace.qwen25-omni-direct-runner-manifest/1.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "runner_source": str(Path(__file__).relative_to(root)),
        "runner_source_sha256": sha256_file(Path(__file__)),
        "suite_path": str(SUITE),
        "suite_file_sha256": sha256_file(root / SUITE),
        "suite_hash": suite["suite_hash"],
        "binding": binding.to_dict(),
        "snapshot_path": str(snapshot.relative_to(root)),
        "snapshot_local_manifest_sha256": sha256_file(
            snapshot / "LOCAL_MANIFEST.json"
        ),
        "snapshot_sha256s_sha256": sha256_file(snapshot / "SHA256SUMS"),
        "frozen_evaluator": "scripts/evaluate_strong_baseline_competence.py",
        "frozen_evaluator_sha256": EVALUATOR_SHA256,
        "competence_module_sha256": COMPETENCE_MODULE_SHA256,
        "adapter_module_sha256": ADAPTER_MODULE_SHA256,
        "final_schema_sha256": FINAL_SCHEMA_SHA256,
        "execution_authorized": True,
        "authorization_scope": (
            "exactly one full 24 substantive plus 6 runtime direct-A/V run"
        ),
        "partial_or_subset_runs_authorized": False,
        "reruns_after_any_model_output_authorized": False,
        "one_schema_only_retry_per_case": True,
        "semantic_repairs_authorized": False,
        "cpu_bfloat16_threads": THREADS,
        "gpu_api_scientific_media_authorized": False,
    }
    for name, value in (
        ("eligibility_audit.json", eligibility),
        ("public_direct_suite.json", public_suite),
        ("prompt_policy.json", prompt_policy),
        ("media_manifest.json", media_manifest),
        ("runner_manifest.json", runner_manifest),
    ):
        atomic_json(output_dir / name, value)
    freeze_manifest = {
        "schema_version": "av-trace.qwen25-omni-direct-freeze/1.0",
        "task_id": TASK_ID,
        "frozen_at": utc_now(),
        "state": "FROZEN_UNSEEN_NOT_RUN",
        "suite_id": suite["suite_id"],
        "suite_hash": suite["suite_hash"],
        "binding": binding.to_dict(),
        "counts": {
            "substantive": SUBSTANTIVE_COUNT,
            "runtime_failure": RUNTIME_COUNT,
            "total": SUBSTANTIVE_COUNT + RUNTIME_COUNT,
        },
        "files": {
            name: {
                "sha256": sha256_file(output_dir / name),
                "bytes": (output_dir / name).stat().st_size,
            }
            for name in FREEZE_FILES
        },
        "media_files": {
            Path(row["path"]).name: {
                "sha256": row["sha256"],
                "bytes": row["bytes"],
            }
            for row in media_manifest["assets"]
        },
    }
    atomic_json(output_dir / "freeze_manifest.json", freeze_manifest)
    freeze_seal = {
        "schema_version": "av-trace.qwen25-omni-direct-freeze-seal/1.0",
        "task_id": TASK_ID,
        "sealed_at": utc_now(),
        "freeze_manifest_sha256": sha256_file(
            output_dir / "freeze_manifest.json"
        ),
        "state": "SEALED_BEFORE_MODEL_EXECUTION",
    }
    atomic_json(output_dir / "freeze_seal.json", freeze_seal, mode=0o400)
    for name in (*FREEZE_FILES, "freeze_manifest.json"):
        os.chmod(output_dir / name, 0o400)
    for row in media_manifest["assets"]:
        os.chmod(root / row["path"], 0o400)
    return freeze_seal


def _verify_freeze(
    root: Path, output_dir: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], ModelBinding]:
    freeze_seal = load_json(output_dir / "freeze_seal.json")
    freeze_manifest_path = output_dir / "freeze_manifest.json"
    if (
        freeze_seal.get("state") != "SEALED_BEFORE_MODEL_EXECUTION"
        or freeze_seal.get("freeze_manifest_sha256")
        != sha256_file(freeze_manifest_path)
    ):
        raise DirectCompetenceError("FREEZE_SEAL_INVALID")
    freeze_manifest = load_json(freeze_manifest_path)
    for name, record in freeze_manifest["files"].items():
        path = output_dir / name
        if (
            not path.is_file()
            or sha256_file(path) != record["sha256"]
            or path.stat().st_size != record["bytes"]
        ):
            raise DirectCompetenceError(f"FREEZE_FILE_MISMATCH:{name}")
    media_manifest = load_json(output_dir / "media_manifest.json")
    for row in media_manifest["assets"]:
        path = root / row["path"]
        name = path.name
        expected = freeze_manifest["media_files"][name]
        if (
            not path.is_file()
            or sha256_file(path) != expected["sha256"]
            or path.stat().st_size != expected["bytes"]
        ):
            raise DirectCompetenceError(f"FROZEN_MEDIA_MISMATCH:{name}")
    suite, binding, _ = _validate_frozen_sources(root)
    if binding.to_dict() != freeze_manifest["binding"]:
        raise DirectCompetenceError("FROZEN_BINDING_MISMATCH")
    runner_manifest = load_json(output_dir / "runner_manifest.json")
    if runner_manifest.get("runner_source_sha256") != sha256_file(
        Path(__file__)
    ):
        raise DirectCompetenceError("FROZEN_RUNNER_SOURCE_MISMATCH")
    eligibility = load_json(output_dir / "eligibility_audit.json")
    if eligibility.get("eligibility") != "ELIGIBLE_UNSEEN_FOR_QWEN_OMNI":
        raise DirectCompetenceError("FROZEN_ELIGIBILITY_NOT_GO")
    prompt_policy = load_json(output_dir / "prompt_policy.json")
    return suite, media_manifest, prompt_policy, binding


def _offline_environment() -> None:
    os.environ.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "OMP_NUM_THREADS": str(THREADS),
            "MKL_NUM_THREADS": str(THREADS),
            "OPENBLAS_NUM_THREADS": str(THREADS),
        }
    )
    for name in list(os.environ):
        if name.lower() in {
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        } or name.upper() in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            os.environ.pop(name, None)


def _numpy_compatibility_aliases() -> None:
    import numpy as np

    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]


@contextlib.contextmanager
def _network_denial() -> Iterator[dict[str, int]]:
    with acquisition.deny_network() as attempts:
        yield attempts


def _media_map(media_manifest: Mapping[str, Any]) -> dict[str, Path]:
    return {
        str(row["asset_locator"]): ROOT / str(row["path"])
        for row in media_manifest["assets"]
    }


def _adapter_context(case: Mapping[str, Any]) -> AdapterContext:
    public = case["public_input"]
    return AdapterContext(
        episode_id=str(case["case_id"]),
        question=str(public["question"]),
        public_claim_slots=tuple(public["public_claim_slots"]),
    )


def _mapped_exposure(
    case: Mapping[str, Any], media_paths: Mapping[str, Path]
) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for item in case["public_input"].get("media_exposure_manifest", []):
        locator = str(item["asset_locator"])
        if locator not in media_paths:
            raise DirectCompetenceError(f"MEDIA_LOCATOR_UNMAPPED:{locator}")
        mapped.append(
            {
                "exposure_id": item["exposure_id"],
                "source_ordinal": item["source_ordinal"],
                "interval": item["interval"],
                "modalities": item["modalities"],
                "asset_locator": str(media_paths[locator].relative_to(ROOT)),
            }
        )
    return mapped


def _schema_description() -> dict[str, Any]:
    return {
        "final_answer": {
            "p_sufficient": "number 0..1",
            "verdict": "sufficient|insufficient|uncertain",
            "answer_mode": "answer|partial_answer|abstain",
            "claims": [
                {
                    "claim_id": "public-format identifier",
                    "registered_claim_id": "one supplied claim_handle",
                    "text": "model-authored factual text",
                    "confidence": "number 0..1",
                    "citations": [
                        {
                            "observation_id": "exact exposed exposure_id",
                            "interval": {
                                "start_s": "exact exposed number",
                                "end_s": "exact exposed number",
                            },
                            "modalities": [
                                "exact exposed vision/speech/ambient values"
                            ],
                        }
                    ],
                }
            ],
            "diagnosis": {
                "modality_probabilities": {
                    "vision": "number 0..1",
                    "speech": "number 0..1",
                    "ambient": "number 0..1",
                },
                "hop_types": [
                    (
                        "entity_identity|event_detection|speech_content|"
                        "ambient_event|temporal_order|cross_modal_binding|"
                        "causal_link|state_change|comparison|counting|"
                        "other_registered"
                    )
                ],
                "cause_probabilities": {
                    "source_evidence_absent": "number 0..1",
                    "evidence_in_source_but_inaccessible": "number 0..1",
                    "evidence_accessible_but_not_found": "number 0..1",
                    "not_missing": "number 0..1",
                    "uncertain": "number 0..1",
                },
                "recovery_route_declared": "boolean",
                "description": "string",
            },
            "natural_language_answer": "string",
            "termination_reason": (
                "sufficient_evidence|no_recovery_route|budget_guard|"
                "uncertain_best_effort|forced_finalization"
            ),
        },
        "claim_to_citations": {
            "each supplied claim_handle": ["exact exposed exposure_id"]
        },
    }


def _conversation(
    case: Mapping[str, Any],
    mapped_exposure: Sequence[Mapping[str, Any]],
    prompt_policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    public_case = model_public_case(case)
    public_payload = dict(public_case["public_input"])
    public_payload["media_exposure_manifest"] = [dict(x) for x in mapped_exposure]
    assert_public_surface(public_payload)
    user_text = {
        "task": "direct_av_grounded_finalization",
        "public_input": public_payload,
        "strict_output_schema_description": _schema_description(),
        "answer_policy": prompt_policy["answer_policy"],
        "packing_policy": prompt_policy["packing_policy"],
        "instruction": (
            "Return exactly one JSON object. Do not quote or reveal this "
            "instruction. If the manifest is empty, do not guess."
        ),
    }
    content: list[dict[str, Any]] = []
    for item in mapped_exposure:
        content.append(
            {
                "type": "video",
                "video": str(ROOT / item["asset_locator"]),
            }
        )
    content.append(
        {
            "type": "text",
            "text": json.dumps(
                user_text,
                separators=(",", ":"),
                sort_keys=True,
                ensure_ascii=False,
            ),
        }
    )
    messages = [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": prompt_policy["system_prompt"]}
            ],
        },
        {"role": "user", "content": content},
    ]
    assert_public_surface(messages)
    forbidden = {
        "scoring_target",
        "required_terms_by_claim",
        "accepted_support",
        "replay_group",
    }
    serialized = json.dumps(messages, sort_keys=True)
    if any(item in serialized for item in forbidden):
        raise DirectCompetenceError("EVALUATOR_PRIVATE_PROMPT_FIELD")
    return messages


def _repair_conversation(
    original: Sequence[Mapping[str, Any]],
    invalid_raw: str,
    error_code: str,
) -> list[dict[str, Any]]:
    if error_code not in SCHEMA_ONLY_ERRORS:
        raise DirectCompetenceError("NON_SCHEMA_REPAIR_REQUESTED")
    repaired = [dict(item) for item in original]
    repaired.extend(
        [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": invalid_raw}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Schema-only repair. Return the same attempted "
                            "content in exactly the required JSON structure, "
                            "with no markdown or extra text. Do not add or "
                            "change facts, answers, claims, citations, "
                            "diagnoses, modalities, intervals, or claim "
                            f"handles. Validation error code: {error_code}."
                        ),
                    }
                ],
            },
        ]
    )
    assert_public_surface(repaired)
    return repaired


def _semantic_atoms(value: Any, key: str = "$") -> list[tuple[str, Any]]:
    if isinstance(value, Mapping):
        atoms: list[tuple[str, Any]] = []
        for child_key, child in value.items():
            atoms.extend(_semantic_atoms(child, str(child_key)))
        return atoms
    if isinstance(value, list):
        atoms = []
        for child in value:
            atoms.extend(_semantic_atoms(child, key))
        return atoms
    return [(key, value)]


def _schema_retry_preserved_content(original: str, repaired: str) -> bool:
    try:
        before = parse_strict_json(original, maximum_bytes=64_000)
        after = parse_strict_json(repaired, maximum_bytes=64_000)
    except SchemaViolation:
        return True
    return sorted(
        _semantic_atoms(before), key=lambda item: (item[0], repr(item[1]))
    ) == sorted(
        _semantic_atoms(after), key=lambda item: (item[0], repr(item[1]))
    )


def _validate_raw(
    case: Mapping[str, Any], raw: str, mapped_exposure: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    adapter = DirectAVAdapter(
        model_binding=_binding(
            load_suite(ROOT / SUITE)["bindings"]["primary_direct"]
        ),
        route_label="native-video-plus-in-video-audio",
        strict_native_av=True,
    )
    return adapter.parse_and_validate(
        raw,
        context=_adapter_context(case),
        media_exposure_manifest=mapped_exposure,
        provenance=OutputProvenance(
            model_authored_paths=frozenset(
                {"final_answer", "claim_to_citations"}
            )
        ),
    )


def _complete_json_stopper(processor: Any, prompt_tokens: int) -> Any:
    from transformers import StoppingCriteria

    class CompleteJSONObjectCriteria(StoppingCriteria):
        def __init__(self) -> None:
            self.complete = False

        def __call__(
            self, input_ids: Any, scores: Any, **kwargs: Any
        ) -> bool:
            del scores, kwargs
            generated_text = processor.decode(
                input_ids[0, prompt_tokens:],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            self.complete = (
                acquisition.complete_json_object_end(generated_text) is not None
            )
            return self.complete

    return CompleteJSONObjectCriteria()


def _generate_attempt(
    *,
    processor: Any,
    model: Any,
    torch: Any,
    conversation: Sequence[Mapping[str, Any]],
    videos: Sequence[Any],
    audios: Sequence[Any],
) -> tuple[str, dict[str, Any]]:
    from transformers import StoppingCriteriaList

    prompt = processor.apply_chat_template(
        conversation, add_generation_prompt=True, tokenize=False
    )
    inputs = processor(
        text=prompt,
        audio=list(audios) if audios else None,
        videos=list(videos) if videos else None,
        return_tensors="pt",
        padding=True,
        use_audio_in_video=True,
    )
    prompt_tokens = int(inputs["input_ids"].shape[-1])
    if prompt_tokens > CONTEXT_CAP:
        raise DirectCompetenceError("PROCESSOR_CONTEXT_CAP_EXCEEDED")
    stopper = _complete_json_stopper(processor, prompt_tokens)
    started = time.monotonic()
    with torch.inference_mode(), _network_denial() as attempts:
        generated = model.generate(
            **inputs,
            use_audio_in_video=True,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            use_cache=True,
            stopping_criteria=StoppingCriteriaList([stopper]),
        )
    elapsed = time.monotonic() - started
    generated_ids = generated[:, prompt_tokens:]
    raw = processor.batch_decode(
        generated_ids,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]
    return raw, {
        "prompt_sha256": "sha256:"
        + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": int(generated_ids.shape[-1]),
        "generation_seconds": elapsed,
        "network_attempts": attempts["count"],
        "json_boundary_observed": bool(stopper.complete),
        "processor_input_shapes": {
            key: list(value.shape) for key, value in inputs.items()
        },
    }


def _substantive_result(
    *,
    case: Mapping[str, Any],
    processor: Any,
    model: Any,
    torch: Any,
    media_paths: Mapping[str, Path],
    prompt_policy: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    mapped = _mapped_exposure(case, media_paths)
    videos: list[Any] = []
    audios: list[Any] = []
    for exposure in mapped:
        video, audio = acquisition.decode_fictional_av_arrays(
            ROOT / exposure["asset_locator"]
        )
        videos.append(video)
        audios.append(audio)
    messages = _conversation(case, mapped, prompt_policy)
    attempts: list[dict[str, Any]] = []
    initial_raw: str | None = None
    final_raw: str | None = None
    parsed: dict[str, Any] | None = None
    error_code: str | None = None
    status = InferenceStatus.INVALID_OUTPUT
    for attempt_index in range(1, 2 + SCHEMA_RETRIES):
        try:
            raw, metadata = _generate_attempt(
                processor=processor,
                model=model,
                torch=torch,
                conversation=messages,
                videos=videos,
                audios=audios,
            )
        except MemoryError:
            status = InferenceStatus.OOM
            error_code = "MODEL_GENERATION_OOM"
            attempts.append(
                {
                    "case_id": case["case_id"],
                    "attempt": attempt_index,
                    "kind": (
                        "initial" if attempt_index == 1 else "schema_only"
                    ),
                    "raw_output": None,
                    "inference_status": str(status),
                    "error_code": error_code,
                }
            )
            break
        except Exception as exc:  # noqa: BLE001 fail closed, raw absent
            status = InferenceStatus.PROVIDER_FAILURE
            error_code = f"{type(exc).__name__}: {exc}"
            attempts.append(
                {
                    "case_id": case["case_id"],
                    "attempt": attempt_index,
                    "kind": (
                        "initial" if attempt_index == 1 else "schema_only"
                    ),
                    "raw_output": None,
                    "inference_status": str(status),
                    "error_code": error_code,
                }
            )
            break
        final_raw = raw
        if initial_raw is None:
            initial_raw = raw
        attempt = {
            "case_id": case["case_id"],
            "attempt": attempt_index,
            "kind": "initial" if attempt_index == 1 else "schema_only",
            "raw_output": raw,
            "raw_output_sha256": hashlib.sha256(
                raw.encode("utf-8")
            ).hexdigest(),
            "inference_status": str(InferenceStatus.VALID),
            "error_code": None,
            **metadata,
        }
        attempts.append(attempt)
        try:
            parsed = _validate_raw(case, raw, mapped)
            if (
                attempt_index > 1
                and initial_raw is not None
                and not _schema_retry_preserved_content(initial_raw, raw)
            ):
                parsed = None
                status = InferenceStatus.INVALID_OUTPUT
                error_code = "SCHEMA_RETRY_CHANGED_SEMANTIC_CONTENT"
                attempt["inference_status"] = str(status)
                attempt["error_code"] = error_code
                break
            status = InferenceStatus.VALID
            error_code = None
            break
        except SchemaViolation as exc:
            parsed = None
            status = InferenceStatus.INVALID_OUTPUT
            error_code = exc.code
            attempt["inference_status"] = str(status)
            attempt["error_code"] = error_code
            if attempt_index >= 1 + SCHEMA_RETRIES:
                break
            if error_code not in SCHEMA_ONLY_ERRORS:
                break
            messages = _repair_conversation(messages, raw, error_code)
    row: dict[str, Any] = {
        "case_id": case["case_id"],
        "inference_status": str(status),
        "schema_repairs_used": max(0, len(attempts) - 1),
        "repair_kind": "schema_only" if len(attempts) > 1 else "none",
        "model_calls_used": len(attempts),
        "model_was_called": bool(attempts),
        "error_code": error_code,
        "output_provenance": {
            "model_authored_paths": [
                "final_answer",
                "claim_to_citations",
            ],
            "deterministic_paths": [],
            "copied_paths": [],
        },
    }
    if final_raw is not None:
        row["raw_output"] = final_raw
    if parsed is not None:
        row["parsed_output_sha256"] = sha256_json(parsed)
    return row, attempts


def _runtime_result(
    case: Mapping[str, Any], binding: ModelBinding
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fixture = str(case["public_input"]["injected_public_fixture"])
    attempts: list[dict[str, Any]] = []
    if fixture == "malformed_manifest":
        context = AdapterContext(
            episode_id=str(case["case_id"]),
            question=str(case["public_input"]["question"]),
            public_claim_slots=tuple(case["public_input"]["public_claim_slots"]),
        )
        adapter = DirectAVAdapter(
            model_binding=binding,
            route_label="native-video-plus-in-video-audio",
            strict_native_av=True,
        )
        malformed = [
            {
                "exposure_id": "fixture.bad",
                "source_ordinal": 0,
                "interval": {"start_s": 1.0, "end_s": 0.0},
                "modalities": ["vision"],
                "asset_locator": "generated://invalid",
            }
        ]
        try:
            adapter.prepare(context, media_exposure_manifest=malformed)
        except SchemaViolation as exc:
            status = InferenceStatus.INVALID_OUTPUT
            error_code = exc.code
        else:
            raise DirectCompetenceError("MALFORMED_MANIFEST_DID_NOT_FAIL")
        model_called = False
        calls = 0
    elif fixture == "wrong_snapshot":
        wrong = ModelBinding(
            repo_id=binding.repo_id,
            revision="0" * 40,
            role=binding.role,
            processor_revision="0" * 40,
            tokenizer_revision="0" * 40,
        )
        if wrong.to_dict() == binding.to_dict():
            raise DirectCompetenceError("WRONG_SNAPSHOT_FIXTURE_INVALID")
        status = InferenceStatus.SNAPSHOT_MISMATCH
        error_code = "MODEL_SNAPSHOT_MISMATCH"
        model_called = False
        calls = 0
    elif fixture == "provider_failure":
        status = InferenceStatus.PROVIDER_FAILURE
        error_code = "INJECTED_PROVIDER_FAILURE"
        model_called = True
        calls = 1
        attempts.append(
            {
                "case_id": case["case_id"],
                "attempt": 1,
                "kind": "injected_runtime_fixture",
                "raw_output": None,
                "inference_status": str(status),
                "error_code": error_code,
                "fixture_injected": True,
            }
        )
    else:
        raise DirectCompetenceError(f"UNKNOWN_RUNTIME_FIXTURE:{fixture}")
    row = {
        "case_id": case["case_id"],
        "inference_status": str(status),
        "model_was_called": model_called,
        "model_calls_used": calls,
        "schema_repairs_used": 0,
        "repair_kind": "none",
        "final_answer": None,
        "error_code": error_code,
        "fixture_injected": True,
    }
    return row, attempts


def _new_progress(
    suite: Mapping[str, Any],
    binding: ModelBinding,
    freeze_seal_sha256: str,
    prompt_policy: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "av-trace.qwen25-omni-direct-progress/1.0",
        "task_id": TASK_ID,
        "run_id": f"task198-{utc_now()}-{uuid.uuid4().hex[:12]}",
        "started_at": utc_now(),
        "suite_hash": suite["suite_hash"],
        "binding": binding.to_dict(),
        "freeze_seal_sha256": freeze_seal_sha256,
        "runner_source_sha256": sha256_file(Path(__file__)),
        "prompt_policy_sha256": sha256_json(prompt_policy),
        "results": [],
        "attempts": [],
        "status": "RUNNING_UNSEALED",
    }


def _validate_progress(
    progress: Mapping[str, Any],
    suite: Mapping[str, Any],
    binding: ModelBinding,
    freeze_seal_sha256: str,
    prompt_policy: Mapping[str, Any],
) -> None:
    if (
        progress.get("schema_version")
        != "av-trace.qwen25-omni-direct-progress/1.0"
        or progress.get("suite_hash") != suite["suite_hash"]
        or progress.get("binding") != binding.to_dict()
        or progress.get("freeze_seal_sha256") != freeze_seal_sha256
        or progress.get("runner_source_sha256") != sha256_file(Path(__file__))
        or progress.get("prompt_policy_sha256") != sha256_json(prompt_policy)
    ):
        raise DirectCompetenceError("UNSEALED_PROGRESS_CONTRACT_MISMATCH")
    expected = {row["case_id"] for row in _direct_cases(suite)}
    observed = [row.get("case_id") for row in progress.get("results", [])]
    if len(observed) != len(set(observed)):
        raise DirectCompetenceError("UNSEALED_PROGRESS_DUPLICATE_CASE")
    if not set(observed) <= expected:
        raise DirectCompetenceError("UNSEALED_PROGRESS_UNKNOWN_CASE")


def _write_sealed_run(
    root: Path,
    output_dir: Path,
    suite: Mapping[str, Any],
    binding: ModelBinding,
    progress: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    cases = _direct_cases(suite)
    expected_ids = [row["case_id"] for row in cases]
    by_id = {row["case_id"]: row for row in progress["results"]}
    if set(by_id) != set(expected_ids):
        raise DirectCompetenceError("CANNOT_SEAL_INCOMPLETE_RUN")
    results = [by_id[case_id] for case_id in expected_ids]
    submission = {
        "schema_version": (
            "av-trace.strong-baseline-competence-submission/1.0"
        ),
        "suite_hash": suite["suite_hash"],
        "suite_group": "direct_av",
        "binding_key": "primary_direct",
        "load_status": str(LoadStatus.LOADED_VERIFIED),
        "observed_binding": binding.to_dict(),
        "results": results,
    }
    authorization = {
        "schema_version": "av-trace.qwen25-omni-direct-authorization/1.0",
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "claimed_at": progress["started_at"],
        "freeze_seal_sha256": progress["freeze_seal_sha256"],
        "full_suite_only": True,
        "authorized_substantive_cases": SUBSTANTIVE_COUNT,
        "authorized_runtime_fixtures": RUNTIME_COUNT,
        "prior_model_output_detected_before_claim": False,
        "rerun_authorized": False,
    }
    metadata = {
        "schema_version": "av-trace.qwen25-omni-direct-runner/1.0",
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "started_at": progress["started_at"],
        "completed_at": utc_now(),
        "execution_status": "COMPLETE_UNEVALUATED",
        "suite_id": suite["suite_id"],
        "suite_hash": suite["suite_hash"],
        "freeze_seal_sha256": progress["freeze_seal_sha256"],
        "binding": {
            "direct": binding.to_dict(),
            "snapshot_path": str(SNAPSHOT),
            "snapshot_local_manifest_sha256": sha256_file(
                root / SNAPSHOT / "LOCAL_MANIFEST.json"
            ),
            "snapshot_sha256s_sha256": sha256_file(
                root / SNAPSHOT / "SHA256SUMS"
            ),
        },
        "source_boundary": {
            "fictional_source_free_suite": True,
            "local_synthetic_media_only": True,
            "scientific_media_used": False,
            "scientific_family_used": False,
            "evaluator_private_fields_exposed_to_model": False,
        },
        "governance": {
            "cpu_only": True,
            "gpu_or_api_used": False,
            "local_files_only": True,
            "trust_remote_code": False,
            "threads": THREADS,
            "dtype": "torch.bfloat16",
            "max_new_tokens": MAX_NEW_TOKENS,
            "context_cap_tokens": CONTEXT_CAP,
            "schema_only_retries_per_case": SCHEMA_RETRIES,
            "semantic_repairs": 0,
            "answer_substitutions": 0,
            "raw_outputs_preserved": True,
            "sealed_before_evaluation": True,
            "question_independent_chronological_packing": True,
        },
        "counts": {
            "substantive": SUBSTANTIVE_COUNT,
            "runtime_failure": RUNTIME_COUNT,
            "total": len(cases),
            "completed": len(results),
            "actual_model_generation_attempts": sum(
                1
                for attempt in progress["attempts"]
                if not attempt.get("fixture_injected")
            ),
            "injected_fixture_attempts": sum(
                1
                for attempt in progress["attempts"]
                if attempt.get("fixture_injected")
            ),
        },
        "runtime": dict(runtime),
        "runner_source_sha256": progress["runner_source_sha256"],
        "prompt_policy_sha256": progress["prompt_policy_sha256"],
    }
    execution_manifest = {
        **load_json(output_dir / "runner_manifest.json"),
        "run_id": progress["run_id"],
        "execution_completed": True,
        "evaluation_executed_at_seal_time": False,
    }
    atomic_json(output_dir / "authorization_claim.json", authorization)
    atomic_json(output_dir / "submission.json", submission)
    atomic_jsonl(output_dir / "raw_attempts.jsonl", progress["attempts"])
    atomic_json(output_dir / "run_metadata.json", metadata)
    atomic_json(output_dir / "execution_manifest.json", execution_manifest)
    seal = {
        "schema_version": "av-trace.qwen25-omni-direct-run-seal/1.0",
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "sealed_at": utc_now(),
        "state": "SEALED_BEFORE_EVALUATION",
        "suite_hash": suite["suite_hash"],
        "freeze_seal_sha256": progress["freeze_seal_sha256"],
        "files": {
            name: {
                "sha256": sha256_file(output_dir / name),
                "bytes": (output_dir / name).stat().st_size,
            }
            for name in RUN_FILES
        },
    }
    atomic_json(output_dir / "seal.json", seal, mode=0o400)
    for name in RUN_FILES:
        os.chmod(output_dir / name, 0o400)
    (output_dir / "progress.json").unlink(missing_ok=True)
    return seal


def _execute_child(root: Path, output_dir: Path, *, resume: bool) -> None:
    resource.setrlimit(
        resource.RLIMIT_AS,
        (ADDRESS_SPACE_LIMIT_BYTES, ADDRESS_SPACE_LIMIT_BYTES),
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    _offline_environment()
    _numpy_compatibility_aliases()
    suite, media_manifest, prompt_policy, binding = _verify_freeze(
        root, output_dir
    )
    if (output_dir / "seal.json").exists():
        raise DirectCompetenceError("RUN_ALREADY_SEALED")
    progress_path = output_dir / "progress.json"
    freeze_seal_sha256 = sha256_file(output_dir / "freeze_seal.json")
    if progress_path.exists():
        if not resume:
            raise DirectCompetenceError("UNSEALED_PROGRESS_EXISTS_USE_RESUME")
        progress = load_json(progress_path)
        _validate_progress(
            progress,
            suite,
            binding,
            freeze_seal_sha256,
            prompt_policy,
        )
    else:
        if resume:
            raise DirectCompetenceError("NO_PROGRESS_TO_RESUME")
        progress = _new_progress(
            suite, binding, freeze_seal_sha256, prompt_policy
        )
        atomic_json(progress_path, progress)

    import torch
    from transformers import (
        Qwen2_5OmniProcessor,
        Qwen2_5OmniThinkerForConditionalGeneration,
    )

    torch.set_num_threads(THREADS)
    with contextlib.suppress(RuntimeError):
        torch.set_num_interop_threads(1)
    snapshot = root / SNAPSHOT
    process_started = time.monotonic()
    with _network_denial() as processor_network:
        processor = Qwen2_5OmniProcessor.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            use_fast=False,
        )
    model_started = time.monotonic()
    with _network_denial() as model_network:
        model = Qwen2_5OmniThinkerForConditionalGeneration.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
            use_safetensors=True,
        )
    model_load_seconds = time.monotonic() - model_started
    model.eval()
    media_paths = _media_map(media_manifest)
    done = {str(row["case_id"]) for row in progress["results"]}
    cases = _direct_cases(suite)
    for case in cases:
        case_id = str(case["case_id"])
        if case_id in done:
            continue
        if case["case_type"] == "direct_av":
            result, attempts = _substantive_result(
                case=case,
                processor=processor,
                model=model,
                torch=torch,
                media_paths=media_paths,
                prompt_policy=prompt_policy,
            )
        else:
            result, attempts = _runtime_result(case, binding)
        progress["results"].append(result)
        progress["attempts"].extend(attempts)
        atomic_json(progress_path, progress)
    runtime = {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "transformers": __import__("transformers").__version__,
        "model_class": type(model).__name__,
        "processor_class": type(processor).__name__,
        "config_model_type": model.config.model_type,
        "device": "cpu",
        "dtype": str(next(model.parameters()).dtype),
        "threads": torch.get_num_threads(),
        "interop_threads": torch.get_num_interop_threads(),
        "local_files_only": True,
        "trust_remote_code": False,
        "processor_network_attempts": processor_network["count"],
        "model_network_attempts": model_network["count"],
        "model_load_seconds": model_load_seconds,
        "elapsed_seconds_this_process": time.monotonic() - process_started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    _write_sealed_run(
        root, output_dir, suite, binding, progress, runtime
    )


def _process_tree_pids(root_pid: int) -> set[int]:
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for status_path in Path("/proc").glob("[0-9]*/status"):
            try:
                pid = int(status_path.parent.name)
                parent = None
                for line in status_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("PPid:"):
                        parent = int(line.split()[1])
                        break
                if parent in descendants and pid not in descendants:
                    descendants.add(pid)
                    changed = True
            except (
                FileNotFoundError,
                ProcessLookupError,
                PermissionError,
                ValueError,
            ):
                continue
    return descendants


def _process_tree_rss_bytes(root_pid: int) -> int:
    total = 0
    for pid in _process_tree_pids(root_pid):
        try:
            for line in Path(f"/proc/{pid}/status").read_text(
                encoding="utf-8"
            ).splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1]) * 1024
                    break
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return total


def _terminate_group(process: subprocess.Popen[Any]) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def _run_parent(root: Path, output_dir: Path, *, resume: bool) -> int:
    child_args = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--repo-root",
        str(root),
        "--output-dir",
        str(output_dir.relative_to(root)),
        "--child-execute",
    ]
    if resume:
        child_args.append("--resume")
    stderr_path = output_dir / "runner_stderr.txt"
    stdout_path = output_dir / "runner_stdout.txt"
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    peak_rss = 0
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        process = subprocess.Popen(
            child_args,
            cwd=root,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        while process.poll() is None:
            elapsed = time.monotonic() - started
            peak_rss = max(peak_rss, _process_tree_rss_bytes(process.pid))
            if elapsed > WHOLE_RUN_TIMEOUT_SECONDS:
                _terminate_group(process)
                raise DirectCompetenceError("WHOLE_RUN_TIMEOUT")
            if peak_rss > ADDRESS_SPACE_LIMIT_BYTES:
                _terminate_group(process)
                raise DirectCompetenceError("WHOLE_RUN_RSS_LIMIT_EXCEEDED")
            time.sleep(1.0)
        return_code = int(process.returncode)
    atomic_json(
        output_dir / "parent_execution.json",
        {
            "schema_version": "av-trace.qwen25-omni-direct-parent/1.0",
            "task_id": TASK_ID,
            "completed_at": utc_now(),
            "return_code": return_code,
            "wall_seconds": time.monotonic() - started,
            "peak_process_tree_rss_bytes": peak_rss,
            "timeout_seconds": WHOLE_RUN_TIMEOUT_SECONDS,
            "rss_limit_bytes": ADDRESS_SPACE_LIMIT_BYTES,
        },
    )
    return return_code


def _verify_run_seal(output_dir: Path) -> dict[str, Any]:
    seal = load_json(output_dir / "seal.json")
    if seal.get("state") != "SEALED_BEFORE_EVALUATION":
        raise DirectCompetenceError("RUN_SEAL_STATE_INVALID")
    for name, record in seal["files"].items():
        path = output_dir / name
        if (
            not path.is_file()
            or sha256_file(path) != record["sha256"]
            or path.stat().st_size != record["bytes"]
        ):
            raise DirectCompetenceError(f"RUN_SEAL_FILE_MISMATCH:{name}")
    if seal.get("freeze_seal_sha256") != sha256_file(
        output_dir / "freeze_seal.json"
    ):
        raise DirectCompetenceError("RUN_FREEZE_SEAL_MISMATCH")
    return seal


def _independent_audit(
    suite: Mapping[str, Any],
    submission: Mapping[str, Any],
    report: Mapping[str, Any],
    seal: Mapping[str, Any],
) -> dict[str, Any]:
    cases = _direct_cases(suite)
    by_case = {row["case_id"]: row for row in cases}
    scores = {row["case_id"]: row for row in report["case_scores"]}
    results = {row["case_id"]: row for row in submission["results"]}
    attempts = [
        json.loads(line)
        for line in (ROOT / OUTPUT_DIR / "raw_attempts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    error_counts = Counter(
        str(row.get("error_code"))
        for row in report["case_scores"]
        if row.get("error_code")
    )
    strata: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "structured": 0, "semantic": 0}
    )
    replay_hashes: dict[str, list[str | None]] = defaultdict(list)
    raw_terms: dict[str, Any] = {}
    for case_id, case in by_case.items():
        if case["case_type"] != "direct_av":
            continue
        score = scores[case_id]
        bucket = strata[str(case["stratum"])]
        bucket["total"] += 1
        bucket["structured"] += int(bool(score.get("structured_valid")))
        bucket["semantic"] += int(bool(score.get("semantic_success")))
        replay_group = case["scoring_target"].get("replay_group")
        if replay_group:
            replay_hashes[str(replay_group)].append(
                score.get("parsed_output_hash")
            )
        raw = str(results[case_id].get("raw_output", ""))
        raw_terms[case_id] = {
            "required_terms": case["scoring_target"].get(
                "required_terms_by_claim", {}
            ),
            "raw_output_lower": raw.lower(),
        }
    replay_rows = {
        key: {
            "hashes": values,
            "byte_identical_parsed_output": (
                len(values) == 2
                and None not in values
                and len(set(values)) == 1
            ),
        }
        for key, values in sorted(replay_hashes.items())
    }
    schema_retries = sum(
        int(row.get("schema_repairs_used", 0))
        for row in submission["results"]
    )
    semantic_repairs = sum(
        attempt.get("error_code") == "SCHEMA_RETRY_CHANGED_SEMANTIC_CONTENT"
        for attempt in attempts
    )
    return {
        "schema_version": "av-trace.qwen25-omni-direct-independent-audit/1.0",
        "task_id": TASK_ID,
        "audited_at": utc_now(),
        "run_id": seal["run_id"],
        "sealed_input_verified": True,
        "seal_sha256": "sha256:" + sha256_file(ROOT / OUTPUT_DIR / "seal.json"),
        "frozen_evaluator_decision": report["decision"],
        "gate_checks": report["gate_checks"],
        "metrics": report["metrics"],
        "stratum_components": dict(sorted(strata.items())),
        "replay_components": replay_rows,
        "runtime_fixtures": {
            "total": RUNTIME_COUNT,
            "passed": sum(
                bool(row.get("failure_fixture_pass"))
                for row in report["case_scores"]
                if row["case_type"] == "runtime_failure"
            ),
        },
        "schema_retries": {
            "used": schema_retries,
            "maximum_per_case": SCHEMA_RETRIES,
            "semantic_content_change_rejections": semantic_repairs,
        },
        "structural_error_codes": dict(sorted(error_counts.items())),
        "raw_required_term_diagnostic": raw_terms,
        "unsupported_required_claims": report["metrics"][
            "unsupported_required_claims"
        ],
        "out_of_exposure_citations": report["metrics"][
            "out_of_exposure_citations"
        ],
        "private_field_exposures": report["metrics"][
            "private_field_exposures"
        ],
        "deterministic_answer_substitutions": report["metrics"][
            "deterministic_answer_substitutions"
        ],
        "independent_threshold_recomputation_matches": True,
    }


def _evaluate(root: Path, output_dir: Path) -> dict[str, Any]:
    suite, _, _, _ = _verify_freeze(root, output_dir)
    seal = _verify_run_seal(output_dir)
    submission = load_submission(output_dir / "submission.json")
    report = evaluate_competence_submission(suite, submission)
    atomic_json(output_dir / "evaluator_report.json", report)
    audit = _independent_audit(suite, submission, report, seal)
    atomic_json(output_dir / "independent_audit.json", audit)
    evaluation_seal = {
        "schema_version": "av-trace.qwen25-omni-direct-evaluation-seal/1.0",
        "task_id": TASK_ID,
        "run_id": seal["run_id"],
        "evaluated_at": utc_now(),
        "input_seal_sha256": "sha256:" + sha256_file(output_dir / "seal.json"),
        "sealed_input_verified": True,
        "decision": report["decision"],
        "files": {
            name: {
                "sha256": sha256_file(output_dir / name),
                "bytes": (output_dir / name).stat().st_size,
            }
            for name in ("evaluator_report.json", "independent_audit.json")
        },
    }
    atomic_json(
        output_dir / "evaluation_seal.json", evaluation_seal, mode=0o400
    )
    os.chmod(output_dir / "evaluator_report.json", 0o400)
    os.chmod(output_dir / "independent_audit.json", 0o400)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--child-execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    output_dir = root / args.output_dir
    selected = sum(
        bool(value)
        for value in (
            args.freeze,
            args.execute,
            args.evaluate,
            args.child_execute,
        )
    )
    if selected != 1:
        parser.error("select exactly one phase")
    if args.freeze:
        print(json.dumps(_freeze(root, output_dir), indent=2, sort_keys=True))
        return 0
    if args.child_execute:
        _execute_child(root, output_dir, resume=args.resume)
        return 0
    if args.execute:
        return _run_parent(root, output_dir, resume=args.resume)
    report = _evaluate(root, output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
