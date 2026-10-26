# P23_102 R23-C exposed-development calibration canary

**Date:** 2026-10-23  
**Implementation status:** `R23_C_EXPOSED_CALIBRATION_IMPLEMENTATION_READY`

## Scope and non-claim

R23-C is a new isolated development-calibration pipeline for the R23-B v9
structured visual atoms and global-distinctiveness protocol. It does not alter
or reuse an R22 marker, authorization receipt, failure capsule, successful
output path, or pipeline identifier. It is not an R22 retry.

The input identities were exposed by the terminal R21/R22 development lineage:
`family-009` / `clip-003`, `family-005` / `clip-011` and `clip-019`, and
`family-003` / `clip-007` and `clip-010`. They are not fresh, untouched, or a
reserve. No unselected reserve identity is read into selection, disclosed, or
consumed. Consequently this experiment may diagnose implementation and
calibration behavior, but it can never establish a fresh scientific-evaluation
claim.

## Fixed budget and modalities

The future authorized run is exactly 13 primary model calls:

- 5 video-only visual calls;
- 5 audio-only ambient calls; and
- 3 text-only relation-kind calls.

There are no repair, semantic retry, redraw, replacement, retrieval, embedding,
or scoring calls.

Visual output is the R23-B v9 inherited finite visual-atom object. Its closed
registry gives more than 33 million valid canonical leaves, so R23-C uses the
allowed strict-JSON alternative rather than pretending that a materialized
token trie is a practical committed runtime object. A future runtime must stop
at the first complete top-level JSON object and then apply exact field-set,
enum, cardinality, uniqueness, state, specificity, and R23-B v9 validation.
Extra text, trailing objects, schema repair, semantic retry, and any
post-validation failure are terminal fail-closed outcomes. The current
implementation commits this boundary but deliberately does not tokenize or
load a model.

Ambient output reuses the parent R21 closed tuple and its 7,680-leaf canonical
token-prefix trie. Ambient description and query text are mechanical. Relation
output is one required closed kind per frozen family; relation natural language
is never model-authored. Visual, ambient, and family descriptions/queries are
mechanically generated and passed through the R23-B v9 build and verification
gates.

## Calibration decision

The estimand is query identifiability before learned retrieval. Any ABSTAIN,
identity duplication, content/signature duplication, normalized duplicate,
Jaccard threshold failure, ambient tuple duplication, generic/specificity
failure, row-regeneration failure, or review-interface construction failure is
fail-closed. Retrieval and embeddings are forbidden.

Only a bundle whose full inherited global gate set passes can receive
`MACHINE_CALIBRATION_PASS_HUMAN_PENDING`. Human packets are generated from all
five trusted component records and remain unfilled in this task. Unfilled
packets do not block the machine-calibration status, but they do block every
human-validated or scientific GO claim. The pipeline never emits scientific
GO.

## One-shot governance

A future real run requires an independently issued R23-C authorization binding
the exact plan, exposed selection, file hashes, tool hashes, model snapshot,
call budget, output path, and authorization-specific marker path. Exclusive
marker creation is the consumption boundary. Failure retains the marker and
the same receipt cannot run again.

Because the data are already exposed, a future code experiment is allowed only
under a new versioned pipeline ID, output path, plan, and authorization receipt.
It must be named exposed development calibration, not fresh evaluation.

## Current commands

`self-test`, `preflight0`, `preflight`, `plan`, and `write-artifacts` are
zero-model and zero-authorization operations. They use only the synthetic stage
runner plus exact exposed-selection verification. The `execute` command cannot
create authorization and has no built-in real model runner.
