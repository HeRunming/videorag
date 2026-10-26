# P23_102 real retrieval diagnostic v1

**Date:** 2026-10-15  
**Decision:** `P23_102_REAL_RETRIEVAL_DIAGNOSTIC_READY`

## Scope and boundary

This is a deterministic, development-only, descriptive
machine-provisional retrieval diagnostic over the verified P23_102 full
timeline index and the repaired 20 V+A leads.

The run:

- read stored SigLIP visual and CLAP audio vectors from the verified index;
- loaded the exact frozen local SigLIP and CLAP text encoders;
- embedded only exact machine-generated question, answer, and atomic-claim
  template fields already present in the provisional family registry;
- used no semantic annotations, human labels, answer keys, accepted SES
  labels, evaluation outcomes, raw media, generation model, or agent;
- preserved the exact source-disjoint boundary: P23_102 remains
  development-only, evaluation-ineligible, and future-test-ineligible.

The results are **not** human-validated semantic evidence, modality
necessity, accepted SES, H-tier, Gate-A evidence, or evidence of
source-level generalization.

## Executed configuration

- Families: 20
- Evidence handles: 56
- Queries: 76
  - 20 family queries
  - 56 evidence-handle claim queries
- Unique query texts: 7
- Index records: 1,115 visual and 1,115 audio
- Frozen rankers:
  - SigLIP text-image cosine
  - CLAP text-audio cosine
  - equal-weight RRF joint, `k=60`
  - evaluation-only oracle target-modality routing
- Baselines:
  - deterministic SHA-256 random ranking
  - query-independent temporal-midpoint ranking
  - BM25 marked not applicable because no provisional target is speech

## Main descriptive result

For the 20 family queries, all-evidence success was zero at R@1, R@5,
and R@10 for every method.

At family-query R@10:

- visual-only evidence recall: 0.0000
- audio-only evidence recall: 0.0125
- equal-weight RRF joint evidence recall: 0.0000
- oracle modality-routing evidence recall: 0.0125
- random baseline evidence recall: 0.0000
- temporal baseline evidence recall: 0.0000
- joint minus best unimodal: -0.0125

The mean first-target ranks for family queries were:

- oracle modality routing: 238.25
- equal-weight RRF joint: 377.90
- visual-only: 406.20
- random: 411.05
- audio-only: 438.50
- temporal midpoint: 513.90

These values are descriptive only. In particular, oracle routing uses the
target handle's provisional modality during evaluation and is not an
available inference-time method.

## Leakage and identifiability audit

No direct query-to-index shortcut was detected:

- no target record ID appeared in query text;
- no source ID appeared in query text;
- no timestamp appeared in query text;
- no query exactly matched stored ASR text.

However, the 76 queries contain only seven unique texts. All seven text
groups are duplicated, producing a
`HIGH_NON_IDENTIFIABILITY` identical-template risk. Families sharing a
template necessarily receive identical learned rankings. This is the
dominant interpretation constraint and prevents treating the result as a
semantic family-identification benchmark.

## Reproducibility and audit

- Runtime: CPU, one thread, deterministic PyTorch algorithms
- Measured elapsed time on the final persisted run: see
  `resource_runtime.json` (runtime measurements are intentionally excluded
  from the deterministic hash)
- Peak RSS: see `resource_runtime.json`
- Ranking records: 380
- Ranked items persisted: 423,700
- Per-query metric rows: 456
- Deterministic rerun hash:
  `sha256:1e2cffceb6a4670cc5bcea53699b8405c75c8e9b1b30f23cee1a07a7b1f6c595`
- A second full execution reproduced the same deterministic rerun hash.
- Synthetic tests, real-output validation, and Ruff passed.

## Artifacts

- Public summary:
  `data/rehearsal_plan/p23_102_real_retrieval_diagnostic_v1.json`
- Restricted output root:
  `data/restricted/p23_102_real_retrieval_diagnostic_v1/`
- Implementation:
  `tools/p23_102_real_retrieval_diagnostic_v1.py`
- Tests:
  `tooling/tests/test_p23_102_real_retrieval_diagnostic_v1.py`

The restricted output includes exact configuration/model/index/bundle
hashes, queries, full per-query rankings and scores, per-query metrics,
aggregate metric tables, leakage audit, runtime/resource measurements,
deterministic payload, and final audit.
