# Task 98 — Scale-1A post-repair independent audit

Date: 2026-09-11  
Auditor: Task 98  
Scope: read-only audit of Task 97 outputs plus Scale-1B plan review

## Final decision

```text
SCALE1A_NO_GO
SCALE1A_NO_GO
FINAL_BENCHMARK_NOT_YET_VALIDATED

SCALE1A_MILESTONE_INCOMPLETE
```

The first decision is the Scale-1A engineering decision and the second is the
diagnostic decision.

This result does **not** invalidate the expensive media/model/index work.
Task 97 closed the five concrete defects raised by Task 96 at their narrow
scope: speech is now represented once per truthful ASR chunk, speech lineage
and BLOCKED closure are complete, real action logs and strict claim/citation
outputs exist, and unvalidated visual negatives are no longer called
validated. However, independent comparison against the frozen Scale-1A
protocol found three remaining evaluation-layer defects. The current public
report therefore overstates `SCALE1A_ENGINEERING_GO`.

## 1. Work actually executed

Task 98 performed the following checks before the request to stop additional
long-running work:

```text
PYTHONPATH=src python scripts/verify_scale1a.py --repo-root . --strict
PASS: passed=true, failures=[]
```

```text
PYTHONPATH=src pytest -q \
  tests_scale1a tests/test_scale1a_model_acquisition.py
PASS: 33 tests
```

```text
PYTHONPATH=src pytest -q \
  tests tests_mvp tests_media tests_agent_runtime \
  tests_validation tests_media_pipeline tests_real_av tests_scale1a
PASS: exit code 0; 478 tests were independently collected
```

The full test command completed successfully. The terminal was run with quiet
output and did not print a final numeric summary, so this audit records the
independent collection count and successful process exit rather than repeating
Task 97's older `476 passed` string.

Checkpoint-derived replay was run through `replay_scale1a` with only its
post-replay build-manifest writer disabled, so the audit did not mutate
production/generated artifacts:

```text
all_match=true
checkpoint_count=20
```

All eight semantic replay hashes matched:

```text
segment
index
migration
negatives
interventions
rankings
trajectories
summary
```

Task 98 also independently recomputed segmentation, CLIP pooling, speech
lineage, intervention closure, persisted trajectory budgets, seven strict
episode metrics, retrieval-at-K metrics, aggregate rows, public leakage, and
the Scale-1B plan structure.

No Whisper, AST, CLIP, or other heavyweight inference was rerun.

## 2. Current-state integrity

### Pilot-0 trust anchor and source media

The Task-93 trust anchor verifies:

- inventory: `94/94`;
- source files: `5/5`;
- total source bytes: `1,955,298,193`;
- source size and SHA-256 bindings: `5/5`;
- each source has one decodable video stream and one decodable audio stream.

### CLIP gate

The Task-94b boundary remains correctly separated:

```text
technical_inference_decision: CLIP_SNAPSHOT_READY
redistribution_decision:      NOT_AUTHORIZED
overall decision:             CONDITIONAL_GO
```

The restricted CLIP snapshot contains 9 allowlisted files totaling
`608,871,522` bytes. Internal offline inference is authorized; redistribution
is not.

### Checkpoints

All 20 checkpoints passed path, mode, key, record count, byte count, raw
SHA-256, stored payload hash, and independently recomputed payload hash checks.
Their modification times all precede the Task-97 derived-artifact rebuild, and
their hashes match the immutable checkpoint references used by replay.

## 3. Full-timeline products

Independent segmentation arithmetic reproduced:

| Product | Count |
|---|---:|
| Four-second base cells | 3,433 |
| Eight-second fine windows | 3,428 |
| Thirty-two-second context windows | 855 |
| Total temporal windows | 4,283 |
| Unique speech-chunk records | 461 |
| Ambient records | 4,283 |
| Visual records | 4,283 |

For every source, base cells are contiguous from time zero to the exact source
duration. Fine and context terminal windows also end at the exact duration.

All 3,433 CLIP cell vectors:

- have dimension 512;
- are finite and nonzero;
- have post-float16 norms in
  `[0.9998109936714172, 1.0002050399780273]`.

Task 98 independently recomputed all 4,283 fine/context pooled CLIP vectors
from the stored cell vectors:

```text
4,283 checked
0 mismatches
```

No persisted image, audio, or video derivative was found under the Scale-1A
tree. Restricted directories and files use `0700` and `0600`, respectively.

## 4. Task-96 blocker closure

| Task-96 finding | Task-98 result |
|---|---|
| D96-01: BLOCKED speech leakage | **Closed.** r016 has 1 support chunk and 1 derived record; r017 has 2 support chunks and 2 derived records. Every derived record is suppressed and none remains reachable pre-restoration. |
| D96-02: metric rows instead of trajectories | **Closed.** 140 trajectories contain 606 ordered actions, responses/references, budgets, triggers, observations, final outputs, validation and route certificates. |
| D96-03: Ground/Act metrics copied from acquisition | **Closed at the named metric scope.** Independent recomputation of Evidence Recall, All-Evidence Success, Answer Score, Citation F1, Supported-Claim Rate, Success@Budget and Premature Stop found 0 mismatches. |
| D96-04: visual hard-negative overclaim | **Closed.** There are 0 admitted visual negatives and 36 explicitly provisional visual candidates; they are excluded from validated-hard-negative metrics. |
| D96-05: duplicated 30-second transcripts | **Closed.** The searchable speech index has 461 unique chunk records, 461 lineage keys, at most one record per chunk, and zero fine/context transcript projections. |

The action logs have:

```text
140 trajectories
606 actions
120 ordinary C/B/R trajectories
20 displacement/control trajectories
maximum 8/10 steps
maximum 9.25/12.0 cost
0 action-sequence or accumulated-cost mismatches
0 final-certificate hash/arithmetic mismatches
```

All persisted policy-blindness flags are false, and code inspection confirms
that the controller receives only the question, public claim-slot handles,
available tools, and budgets. Search responses expose opaque pointers,
modality, interval, generic preview, and score—not family/state/evidence IDs.

## 5. Independent metric checks

Task 98 found:

```text
strict episode metric mismatches: 0
Recall@K / All-Evidence@K mismatches: 0
aggregate-row mismatches: 0
public leakage findings: 0
```

The report's diagnostic outcomes are reproducible:

- all five retained families have at least one nonzero bounded-to-full
  acquisition degradation;
- answer/evidence/grounding separation occurs;
- deterministic policy aggregate signatures differ;
- `r007` does not survive the frozen Recall@5 criterion;
- no displaced trajectory recovers;
- validated hard-negative eligibility does not cover every retained family.

Therefore a diagnostic GO is not supported.

## 6. Remaining blockers

### T98-01 — Query reformulation gain is unimplemented

The frozen protocol defines:

> best evidence recall after searches 2..N minus recall after the first search

and says it is eligible whenever at least two content searches occur.

Independent action-log inspection found:

```text
eligible trajectories with >=2 content searches: 60
eligible trajectories with a persisted gain value: 0
```

All 140 rows contain `query_reformulation_gain=null`. The evaluator and
aggregate report therefore omit a required full-timeline diagnostic rather
than applying its declared eligibility rule.

### T98-02 — Cross-modal switch counting does not follow the frozen definition

The frozen protocol counts modality changes between consecutive content
**search and observation** actions. The implementation counts search actions
only and divides by the number of searches.

Independent recomputation from both searches and successful
`inspect_clip`/`read_transcript` actions disagreed with the persisted
`modality_switches` or `modality_switch_rate` in:

```text
36/140 trajectories
```

This affects a required full-timeline metric and its aggregates.

### T98-03 — Required controls and displacement semantics are incomplete

The frozen protocol requires a matched no-trigger control for RESTORED, but
the persisted 140 trajectories contain:

```text
RESTORED trajectories with restoration disabled: 0
```

There are ten `recovery_disabled=true` controls, but they belong only to the
separate CLEAN displacement condition. They do not establish that the same
RESTORED action sequence cannot recover when its restoration hook is disabled.

In addition, the displacement design says to demote the first accepted result
below top-K and substitute an admitted negative. The implementation inserts
the first available negative at rank one but does not identify and demote an
accepted result below K. In the independently checked cases where support was
already in the first-query top five, support remained in the top five:

```text
r007: rank 3 -> rank 3
r011: rank 2 -> rank 3
r017: rank 1 -> rank 2
```

For r004 and r016 the first-query route did not contain accepted support in the
top five. Thus the 20 rows are auditable perturbation attempts, but they do not
instantiate the frozen hard-negative-displacement intervention as specified.

This explains the honest zero recovery result, but it also means the required
control experiment has not yet been executed.

## 7. Why the strict verifier and tests still pass

The strict verifier correctly covers the repaired Task-96 conditions, hashes,
permissions, lineage and existence of action-level fields. It does not
currently:

- enforce non-null Query Reformulation Gain for eligible traces;
- independently recompute modality switches from search plus observation
  actions;
- require matched RESTORED no-trigger trajectories;
- prove that a displacement moved accepted support below the declared K.

Consequently, green verifier/tests are valid evidence for what they cover, but
not proof of the complete frozen Scale-1A protocol.

## 8. Scale-1B plan audit

The Scale-1B plan is **complete enough for bounded download and smoke-test
execution**, but no learned readiness gate is open.

It includes:

- exact model IDs and 40-character revisions for SigLIP2, CLAP, Qwen 1.5B,
  optional SmolVLM2, and optional Qwen 7B;
- per-model snapshot/weight estimates;
- Wave R (`2,157,360,092` bytes), Wave G/A (`3,098,973,447` bytes), and
  optional Wave D (`8,992,155,310` bytes);
- restricted staging, allowlists, size/SHA-256 checks, offline
  `local_files_only` load, safetensors checks and atomic promotion;
- retrieval, generator, output-validator and agent-runtime integration
  surfaces;
- L0–L4 validation, failure injection and API provenance requirements;
- explicit fail-closed gates.

Current state:

```text
plan decision:             READY_FOR_BOUNDED_DOWNLOADS
LEARNED_RETRIEVAL_READY:   false
LEARNED_GENERATION_READY:  false
LEARNED_AGENT_READY:       false
SCALE1B_READY:             false
```

Before Scale-1B L2/L3 execution, its “all six” language must be reconciled with
Scale-1A's current five retained families and one excluded r014 family. Learned
fusion also remains gated on a leakage-safe, non-evaluation training split.
Neither issue prevents bounded Wave-R acquisition and L0/L1 smoke tests.

## 9. Requirement/evidence conclusion

| Requirement | Status |
|---|---|
| Trust anchor, five sources and exact identity | PROVEN |
| CLIP internal-use gate and redistribution boundary | PROVEN |
| Twenty immutable checkpoints | PROVEN |
| Full timeline and modality index counts | PROVEN |
| Genuine CLIP vectors and deterministic pooling | PROVEN |
| Truthful chunk-level speech and lineage | PROVEN |
| r016/r017 BLOCKED closure | PROVEN |
| Action-level trajectories and strict Task-90 core metrics | PROVEN |
| Visual-negative provisional labeling | PROVEN |
| Query reformulation gain | MISSING |
| Cross-modal switch semantics | CONTRADICTED |
| RESTORED no-trigger control | MISSING |
| Frozen displacement intervention | CONTRADICTED |
| Deterministic replay and artifact hashes | PROVEN |
| Scale-1B bounded next-step plan | PROVEN_WITH_PRE_EXECUTION_GATES |

Because required evaluation components are missing or contradicted while the
current report claims engineering GO, the honest overall result is:

```text
SCALE1A_MILESTONE_INCOMPLETE
```

The repair should be narrow: preserve all expensive checkpoints, implement the
two metric definitions, add actual RESTORED trigger-disabled controls, correct
the displacement operator, regenerate only derived trajectories/reports, and
repeat this audit.
