# Scale-1A Pilot-0 baseline freeze

**Task:** 93  
**Date:** 2026-09-11  
**Decision:** **`BASELINE_FROZEN`**

## Scope

This review freezes the exact NOAA-01 Pilot-0 state that Scale-1A must compare
against. It does not promote any annotation or result:

```text
stage = MACHINE_ADJUDICATED_PROVISIONAL_MVP
human_reviewed = false
gold_annotation = false
learned_model_evaluation = false
```

The machine-readable authority is:

```text
data/rehearsal_plan/scale1a_pilot0_trust_anchor.json
```

The anchor inventories 94 dependencies and outputs with exact path, byte size,
SHA-256, mode, access class, and semantic role. Its own file and the two Task
93 narrative companions are excluded to avoid a self-referential hash.

## Independent audit result

I independently read current files, streamed hashes from bytes, inspected
permissions, followed JSON cross-links, parsed the episode CSV, and recomputed
all aggregate rows. The existing producer was not used as the source of
expected metric values.

```text
checks:                         108
passed:                         108
failed:                           0

stale hash inconsistencies:       0
permission inconsistencies:       0
decision inconsistencies:         0
count inconsistencies:            0
metric aggregate mismatches:      0
```

The following independently matched:

- all five source-media byte sizes and SHA-256 digests;
- acquisition plan hash and acquisition/media manifests;
- all machine-review input/output identities recorded by its manifest;
- all 12 Whisper and 4 AST pinned snapshot file identities;
- frozen-index canonical self-hash and family links to index, validation, and
  intervention documents;
- all 11 current run-manifest artifact hashes;
- all 15 Task-90 authoritative artifact hashes;
- 72 episode rows reduced to 40 aggregate rows, with zero mismatch against
  both `summary.csv` and `report.json`.

## Frozen source identities

| Asset | Duration (s) | Bytes | SHA-256 |
|---|---:|---:|---|
| `cand-045` | 1772.440000 | 58,576,631 | `03da99e7a33a1ad18ad57376e6517639f950e39b4fe67f898c54a948e17f9ad6` |
| `cand-047` | 1983.781800 | 284,515,787 | `ddfb6c2ffa2794f20bb5d2d4330b89807dfaeed7156a3d7cab372e78bd184160` |
| `cand-049` | 2465.329542 | 491,943,858 | `1934c31cb0311a46daab367f840eb549d29bb1e9e1475a73287912bba03069e5` |
| `cand-051` | 3718.581542 | 558,522,234 | `279f6b3841188e805b153ab0c7f0c85cdc584dd6bce6090f9e2a0b2d06d951b2` |
| `cand-052` | 3781.144042 | 561,739,683 | `c4f5d8c6e60d6802bb60e26f811f5dcabc9698626a29c6cb8aabcc373db4eef1` |

Total source bytes:

```text
1,955,298,193
```

All five have at least one video and one audio stream and remain within the
20–90 minute acquisition range.

## Frozen counts and decisions

```text
machine-review records:       18
accepted / deferred / reject:  6 / 10 / 2
Whisper executions:           18
AST executions:               18
validated necessary V/S/A:     0 / 0 / 0

Pilot-0 source assets used:     3
Pilot-0 families:               6
bounded index windows:         18
bounded index records:         54
main trajectories:             72
valid trajectories:            72
no-trigger controls:           12
runtime evaluations:           72
aggregate rows:                40
```

The three decisions agree across the report, run manifest, and Task-90 audit:

```text
ENGINEERING_GO
PROVISIONAL_SCIENTIFIC_INCONCLUSIVE
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

## Frozen paired migration cohort

| Family | Review window | Asset | Exact interval (s) | Candidate modalities |
|---|---|---|---:|---|
| `noaa01-r004-surf-av` | `noaa01-review-004` | `cand-049` | `[1011.842, 1019.842)` | vision + ambient |
| `noaa01-r007-opening-plastic-waste` | `noaa01-review-007` | `cand-051` | `[0.000, 8.000)` | vision |
| `noaa01-r011-bag-by-fence` | `noaa01-review-011` | `cand-051` | `[3055.773, 3063.773)` | vision |
| `noaa01-r014-aircraft-storm-view` | `noaa01-review-014` | `cand-052` | `[443.899, 451.899)` | vision |
| `noaa01-r016-three-factors-vs` | `noaa01-review-016` | `cand-052` | `[1331.698, 1339.698)` | vision + speech |
| `noaa01-r017-north-atlantic-basin` | `noaa01-review-017` | `cand-052` | `[2663.396, 2671.396)` | speech |

“Candidate modalities” are routing/support hypotheses. They are not
human-validated necessity labels.

## Frozen headline aggregates

| Policy | Evidence Recall | All-Evidence | Answer | Citation F1 | Supported Claims | Success@Budget | Premature Stop | Recovery |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Direct long context | N/A | N/A | 0.666667 | 0.740741 | 0.823529 | 0.666667 | 0.000000 | N/A |
| Single-shot RAG | 0.388889 | 0.222222 | 0.222222 | 0.444445 | 0.625000 | 0.222222 | 0.388889 | N/A |
| ReAct recovery | 0.722222 | 0.666667 | 0.666667 | 0.740741 | 0.823529 | 0.666667 | 0.000000 | 1.000000 |
| Evidence sufficiency | 0.722222 | 0.666667 | 0.666667 | 0.666667 | 1.000000 | 0.666667 | 0.000000 | 1.000000 |

The anchor stores all 40 rows with their numerators and denominators. All
Modality Recall rows remain `null`; direct acquisition metrics and non-agentic
Recovery remain ineligible where defined by the frozen protocol. Every row
retains `LOW_N_DESCRIPTIVE_PILOT`.

## Permissions

All 58 restricted files in the inventory are mode `0600`; the
`data/restricted/noaa01` parent is `0700`. The `machine_review`, `recon`, and
`review` child directories are `0755`, but group/other cannot traverse the
`0700` parent. This is not a current disclosure inconsistency. Tightening
those child modes in Scale-1A is permitted hardening, provided it is reported
and not confused with semantic baseline drift.

## Scale-1A invariants

Scale-1A must preserve:

1. the five source MP4 byte identities;
2. the complete Pilot-0 inventory as an immutable comparison snapshot;
3. the six family/review/asset/interval tuples as the paired migration cohort;
4. paired CLEAN/BLOCKED/RESTORED budgets, triggers, restoration, reacquisition,
   and no-trigger semantics;
5. the policy-visible versus evaluator-private information boundary;
6. hash-verified, exact-interval access to original media without persistent
   media derivatives;
7. machine-only, provisional, non-gold annotation status;
8. Task-90 metric definitions and null eligibility semantics;
9. Pilot-0 aggregate values and decisions as immutable reference values;
10. restricted/public permission and leakage boundaries;
11. legacy replay or an explicit baseline-break report after shared-code
    changes;
12. the distinction between five acquisition assets and three Pilot-0 MVP
    assets.

## Explicitly allowed migration differences

Scale-1A may create, in separate versioned paths:

- a full-timeline multi-scale index with more windows and records;
- more same-video distractors and provisional alternative evidence;
- new or learned modality-specific and multimodal retrievers;
- new rankings, costs, trajectories, and metric values attributable to the
  full-timeline condition;
- a versioned backend adapter that preserves visibility and intervention
  semantics;
- later families or assets as additions, not replacements;
- later human promotion through a separate validation gate.

None of these differences authorizes overwriting Pilot-0 artifacts.

## Verifier specification

Task 93 was prohibited from adding production code, so the verifier is
specified but not created:

```bash
python tools/verify_scale1a_pilot0_anchor.py \
  --repo-root . \
  --anchor data/rehearsal_plan/scale1a_pilot0_trust_anchor.json \
  --strict
```

It must:

1. reject missing paths and symlinks;
2. recompute all inventory sizes, hashes, and modes;
3. cross-check source media against acquisition and media-audit manifests;
4. recompute review dispositions and real-model execution counts;
5. verify the canonical frozen-index self-hash and all family document links;
6. recompute families, trajectory cross-products, controls, evaluations, and
   decisions;
7. independently aggregate the 72 episode rows into the 40 stored metric rows;
8. verify run-manifest and Task-90 hashes and permission boundaries;
9. exit nonzero with a machine-readable mismatch list on any drift.

## Final decision

No stale hash, permission, decision, count, or aggregate inconsistency was
found in the frozen scope.

```text
BASELINE_FROZEN
```
