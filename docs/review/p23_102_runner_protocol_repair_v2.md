# P23_102 runner protocol repair v2

**Date:** 2026-10-14  
**Scope:** development-only, machine-provisional P23_102 rehearsal runner  
**Disposition:** `P23_102_RUNNER_PROTOCOL_REPAIR_V2_READY`

## Boundary

This repair changes only the rehearsal runner, its focused tests, and this
review note. It does not authorize execution, update the adapter attestation,
modify the frozen configuration, load a model, decode media, or create a
scientific result.

The P23_102 bundle remains:

- machine-provisional and not human validated;
- development-only and excluded from scientific evaluation;
- unable to establish accepted SES, answer validity, modality necessity,
  Gate A, H2, causal effects, or source-disjoint generalization; and
- blocked from execution by `execution_authorized=false`.

The repaired runner deliberately reports its new hash as
`REPAIR_NOT_ATTESTED`. Concurrent controller/process hash drift is likewise an
authorization blocker rather than a static planning failure. A future
attestation update is outside this task.

## Binding repairs

### 1. Real checkpoint delivery and independently checked R/N bytes

After exactly four completed action-response cycles, both fresh continuation
states now receive an actual public event row containing the frozen neutral
checkpoint. The event consumes no tool step or cost. Restoration is applied
privately only after both public rows have been appended.

The runner separately serializes the complete R and N public histories through
the event, records both lengths and SHA-256 hashes, and derives
`prefix_identical` from a byte comparison. It no longer reports equality by
construction while omitting the event from the delivered history.

Early terminal prefixes receive no checkpoint and remain copied into both
assigned R/N ITT outcomes.

### 2. Public-surface firewall

Model-visible history and budget records expose only public actions, sanitized
responses, public controller state, `remaining_steps`, and `remaining_cost`.
They never expose:

- trigger state;
- suppressed record identifiers;
- private pointer or observation inventories;
- arm, intervention, route, necessity, or support identifiers; or
- restoration status.

Blocked-state typed status is standardized before the checkpoint across B, R,
and N. In particular, retryability no longer encodes whether the hidden arm is
R.

### 3. C/B endpoint semantics

C and B are state-endpoint runs, not staged R/N prefixes. A valid
model-authored early `finalize` in C or B now invokes the grounded finalizer
and may complete normally. Only a staged R/N prefix that terminates before the
fixed checkpoint receives `EARLY_TERMINAL_BEFORE_CHECKPOINT`.

### 4. Baseline mechanics

Direct long-context now deterministically packs all state-accessible citable
observations without retrieval actions. Packing is chronological, with the
frozen vision/speech/ambient modality order resolving observations at the same
source interval, up to the 24,576-token cap.

Single-shot RAG issues one frozen question query to each modality, applies
equal-weight reciprocal-rank fusion with `rrf_k=60`, freezes deterministic
fused pointer selection, inspects the first selected pointer as cycle four,
and inspects only the remaining frozen selection after the checkpoint. It does
not reformulate or search again.

### 5. No-progress accounting

Controller payloads now carry the actual consecutive no-progress count.
Acquiring a new citable observation resets the count; search, status, failed
inspection, and other rounds without a new observation increment it. Two
consecutive no-progress rounds restrict the next public action menu to
`finalize`.

### 6. Raw failed attempts

`LearnedCallFailure` and compatible controller/process exceptions are inspected
for attached attempt records. Malformed and process-failure attempts, including
raw text when available, are retained in `raw_model_calls.jsonl` and linked
from factor-output failure records instead of being discarded at the runner
boundary.

### 7. Mechanical metric-ready records

Metric rows now derive fields from the frozen provisional evidence handles,
the acquired observation-to-evidence mapping, citations, final output, event
trajectory, and budget ledger. They include:

- evidence recall and all-evidence completeness;
- citation precision, recall, and F1;
- mechanically supported asserted-claim rate;
- a provisional supported-answer endpoint that can be one only when an
  answer has valid observed citations and intersects expected provisional
  evidence;
- premature stopping and post-checkpoint recovery fields; and
- steps and tool cost used.

These are mechanical development diagnostics over provisional bundle
relations. They are not human-valid answer or support scores.

### 8. Terminal ledger and run identity

Output writing now requires exactly one trajectory and metric terminal row per
assignment and rejects duplicates or omissions. `failure_ledger.jsonl` is a
complete assignment ledger: every assignment has one row, with a nested typed
failure only when applicable.

The run manifest records runner/config/bundle/plan identities, assignment and
terminal-row counts, the assignment-ID digest, output contract, systems,
mechanisms, arms, and the persistent non-scientific and unauthorized boundary.

### 9. Exact Williams balance

The 160 family/mechanism/system cells are deterministically hash-ordered from
the frozen assignment seed and assigned the four registered Williams
sequences cyclically. This produces exact `40/40/40/40` sequence allocation
before expanding each cell into four arm rows.

### 10. Provenance versus runtime leakage

The bundle provenance firewall and runtime leakage classifier are now separate
manifest objects:

- the frozen bundle gate may report `PASS` for construction-time provenance
  and claim-firewall checks;
- the runtime classifier remains `NOT_RUN_EXECUTION_UNAUTHORIZED` or
  `NOT_RUN_TEST_INJECTION`.

A bundle-gate pass is never represented as proof that runtime trajectory
leakage classification executed.

## Adversarial verification

Focused tests cover:

1. checkpoint delivery plus independent R/N byte and hash equality;
2. private snapshot-field removal and B/R/N pre-checkpoint equality;
3. valid C/B early finalization;
4. direct-context packing and frozen equal-weight RRF selection;
5. consecutive no-progress propagation and forced finalization;
6. malformed raw-attempt retention;
7. non-hardcoded metric fields and tool cost;
8. complete one-row-per-assignment terminal ledgers;
9. exact Williams `40/40/40/40` balance; and
10. explicit provenance/runtime leakage-status separation.

The focused test module and Ruff checks pass without live execution.

`P23_102_RUNNER_PROTOCOL_REPAIR_V2_READY`
