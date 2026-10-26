# P23_102 technical smoke v2 runner authorization repair

**Date:** 2026-10-14  
**Disposition:** `P23_102_TECHNICAL_SMOKE_V2_AUTHORIZATION_REPAIR_READY`

## Scope and immutable boundary

`scripts/run_p23_102_technical_smoke_v2.py` remains a smoke-only integration
runner. This repair changes only the runner, its focused tests, and owned
documentation. It does not modify the frozen configuration, adapter
attestation, old rehearsal runner, model/process modules, source modules, or
any restricted input. No live model inference was run.

The frozen configuration and adapter attestation remain explicitly
unauthorized. Their `execution_authorized=false` values are immutable inputs,
not switches. Normal execution is possible only when the operator supplies a
separate, strict, one-run authorization overlay. This repository does not
contain and this repair does not generate such an overlay.

## Strict authorization overlay

`--execute` without `--authorization-overlay` fails closed. The overlay has an
exact allowlisted schema; unknown or missing fields are rejected. It requires:

- overlay schema and authorization ID;
- UTC issue and expiry times;
- a one-run nonce reserved with create-exclusive durable storage;
- distinct live-wiring and red-team authority IDs, roles, approval IDs, and
  approval timestamps;
- exact hashes for the immutable freeze, adapter attestation, repaired smoke
  runner, execution module set, model set, assignment plan, checkpoint
  contract, and canonical absolute output root; and
- affirmative smoke-only, no-scientific-interpretation,
  no-competence/performance-interpretation, single-run, and immutable-freeze
  acknowledgements.

Authorization is not inferred from a test pass, hash match, model presence, or
a changed boolean in the frozen files.

## Worker and prefix isolation

For learned R/N cells, the blocked prefix runs in a dedicated prefix worker.
That worker is closed before two fresh continuation workers are created. The R
and N continuation workers have independent session, cache, process-group, and
runtime namespaces. Single-shot RAG has no learned prefix worker. Isolation
artifacts separately identify the 32 assignment workers and the 8 learned
prefix workers.

## Checkpoint and pre-prefix identity

Every R/N pair validates the complete canonical checkpoint contract, not only
R=N equality:

- exact checkpoint object;
- canonical SHA-256
  `sha256:c580c16af6401b4d12df1d39085bbddee6f63e6d81772f6b3186a0fcc84c996c`;
- zero-based action index 4;
- exactly one delivered event in each R and N public history; and
- byte-identical public prefixes through delivery.

The runner also executes and persists a scoped B/R/N public-start identity
probe for every applicable paired cell before the first action.

## Mechanical scan versus leakage classifier

`mechanical_private_surface_scan` recursively scans nested request, response,
failure, repaired-attempt, public-trajectory, and explicitly supplied public
output values. It detects private keys plus exact or embedded private values.
This mechanical scan may be `PASS` or `FAIL`.

The independent runtime leakage classifier remains
`NOT_ESTIMABLE_SINGLE_SOURCE`; it can never be reported as `PASS` for P23_102.
The construction-time bundle provenance firewall is also a separate object.

## Online abort and durability

Before another provider call and before the next assignment boundary, the
runner enforces hard limits with exact `>=` semantics:

- 11 provider calls per effective assignment boundary;
- 352 calls globally;
- two process failures, three malformed-after-repair terminals, or two typed
  tool-contract violations;
- 120 seconds per provider call and 900 seconds per assignment boundary;
- any checkpoint, replay, privacy, raw-retention, output, or process-isolation
  failure.

The output directory and an initial `RUNNING` manifest are durable before
assignment 1. Raw calls and each assignment's terminal trajectory, citation,
metric, failure, and completion rows are append-safe and fsynced. An abort
writes a durable abort row and one durable unstarted-assignment row for every
remaining assignment. Final inventory/artifact manifests are atomic.

## Raw failures, model validation, and provenance

Every process exception receives a canonical raw/diagnostic byte hash and byte
length, even when the exception exposes no native raw byte field. The complete
local Qwen snapshot is validated file-by-file against manifest sizes and
SHA-256 values, preventing same-size tampering.

Final provenance records actual UTC start/completion times, canonical output
root, authorization identity (when present), freeze/adapter/runner/module/model
and plan identities, and validated Qwen file-set identity. Scientific,
semantic, competence, performance, causal, H2, Gate A, and human-validity
interpretations remain prohibited.

`P23_102_TECHNICAL_SMOKE_V2_AUTHORIZATION_REPAIR_READY`
