# Mini-pilot real family-candidate mining execution audit

**Date:** 2026-09-23  
**Scope:** machine-provisional family-candidate mining over the canonical
four-source full-timeline index plus frozen NOAA development inputs  
**Decision:** `REAL_FAMILY_CANDIDATES_REPAIR`

## 1. Decision

The real miner completed and wrote:

```text
data/restricted/mini_pilot_family_candidates_v1/candidate_registry.json
```

The registry is valid, self-hashed, restricted, deterministic, and limited to
machine-provisional P tiers. It contains all 12 reported candidate slots and
both excluded calibration slots. It contains **zero** H1/H2 assignments, human
gold records, accepted final families, active interventions, trajectories, or
evaluation results.

The decision is `REAL_FAMILY_CANDIDATES_REPAIR`, rather than READY, because two
narrow repairs to the owned family-mining implementation were required before
the canonical preflight and real execution could pass:

1. the canonical adapter still looked for the obsolete plan key
   `expected_totals`; the accepted plan stores its frozen lattice counts under
   `totals`;
2. the local Transformers 5.2.0 import path entered SciPy 1.14.1, which still
   references removed NumPy aliases under NumPy 1.26.4. The frozen CLIP query
   encoder now installs the same `np.long`/`np.ulong` compatibility aliases
   already used by the canonical index and Scale-1A runtimes.

Both changes are compatibility repairs only. They do not alter slot targets,
queries, source selection, retrieval scores, tier criteria, evidence, source
hashes, or governance boundaries. Post-repair tests and lint pass, the real
registry is byte-identical across repeated execution, and there is no
remaining blocker to using this registry as a machine-provisional input to a
separately authorized human workflow.

This decision does **not** declare Gate A, H1, H2, construct validity,
intervention isolation, route saturation, or evaluation readiness.

## 2. Canonical verifier, preflight, tests, and lint

### Canonical four-source verifier

Command:

```bash
PYTHONPATH=src python scripts/verify_mini_pilot_full_timeline.py --repo-root .
```

Final result:

```text
verified: true
decision: MINI_PILOT_INDEX_VERIFIED
verification_mode: full_build
smoke_seconds: null
check_count: 395
failures: []
sources: 4
checkpoints: 16
base_cells: 3208
temporal_segments: 4004
derived_bytes: 68099838
```

### Family canonical-input preflight

Command:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_family_candidates.py \
  --repo-root .
```

Final result:

```text
status: READY
mode: canonical_input_preflight
canonical_index_complete: true
candidate_generation_executed: false
```

The first pre-repair run failed closed with
`CANONICAL_INDEX_COUNT_MISMATCH:base_cells`, exposing the obsolete plan-key
lookup described above.

### Frozen NOAA development verifier

Command:

```bash
PYTHONPATH=src python scripts/verify_scale1a.py --repo-root .
```

Final result:

```text
passed: true
decision: SCALE1A_ENGINEERING_GO
failures: []
verified_inventory_count: 94
diagnostic_decision: SCALE1A_DIAGNOSTIC_INCONCLUSIVE
final_benchmark_status: FINAL_BENCHMARK_NOT_YET_VALIDATED
```

The last two statuses are preserved: the NOAA material is consumed
development input, not final benchmark evidence.

### Focused validation

Commands:

```bash
PYTHONPATH=src pytest -q tests_mini_pilot_families
python -m ruff check \
  scripts/build_mini_pilot_family_candidates.py \
  src/av_trace_mini_pilot_families \
  tests_mini_pilot_families
```

Final results:

```text
13 passed
All checks passed
```

## 3. Real execution and deterministic replay

Command:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_family_candidates.py \
  --repo-root . \
  --execute \
  --output \
  data/restricted/mini_pilot_family_candidates_v1/candidate_registry.json
```

Final result:

```text
status: MACHINE_PROVISIONAL_CANDIDATES_WRITTEN
proposed_candidate_count: 14
unfilled_slot_count: 0
human_reviewed_count: 0
human_gold_count: 0
final_accepted_family_count: 0
```

The first execution attempt after the count-key repair failed before writing
the registry because `CLIPModel` could not import through the local
NumPy/SciPy stack. After the narrowly scoped compatibility repair, execution
completed.

The exact execution was repeated. The registry SHA-256 was identical before
and after:

```text
e97a07def01a26a7d87f1ff5fef0e13e257a0876679ef17d8e7961136ae44ba9
```

The local CLIP load emitted environment warnings about unavailable CUDA,
the installed SciPy/NumPy version declaration, Requests dependency versions,
and two unexpected `position_ids` buffers. The model loaded on CPU, execution
completed, and the deterministic replay matched byte for byte.

## 4. Exact slot and source audit

### Denominators

| Class | Count | Result |
|---|---:|---|
| Total registry slots | 14 | exact |
| Reported candidate slots | 12 | exact |
| New-source reported slots | 8 | exact |
| NOAA development reported slots | 4 | exact |
| Excluded calibration slots | 2 | exact |
| Unfilled slots | 0 | none |
| Missing target modalities | 0 | none |

Both calibration records have
`included_in_reported_denominator=false`:

- `CAL01`, NOAA `cand-051`, excluded low-risk visual anchor;
- `CAL02`, Oxford D.H. Lawrence, excluded wording/timing calibration.

### Reported source distribution

| Source | Role | Reported slots | Domain |
|---|---|---:|---|
| `SG-OXFORD-QM-001` | new source | 2 | quantum physics |
| `SG-OXFORD-DHL-CONSCIOUSNESS` | new source | 2 | literary studies |
| `SG-MIT-RES12-003-L01` | new source | 2 | fluid dynamics and sediment transport |
| `SG-YALE-PHYS200-L01` | new source | 2 | classical mechanics |
| `cand-049` | NOAA consumed development | 2 | instructional field safety |
| `cand-052` | NOAA consumed development | 2 | expert public information/weather |

Thus the 12 reported slots contain exactly six source groups with two slots
per source. The four new-source groups span four subject domains and three
collections; the two NOAA groups add two development domains. NOAA records are
marked `NOAA_CONSUMED_DEVELOPMENT_ONLY` and future-primary-test ineligible.

## 5. Target-versus-observed strata

No target was forced. The registry reports nine target-met slots and three
honest relabels:

| Slot | Target | Observed | Disposition |
|---|---|---|---|
| `F05` | far/separated | near/local | `PROPOSED_RELABEL_REQUIRED` |
| `F09` | far/separated | near/local | `PROPOSED_RELABEL_REQUIRED` |
| `F10` | near/local | far/separated | `PROPOSED_RELABEL_REQUIRED` |

All three mismatches are temporal. There are no modality or hop-stratum
mismatches.

### Reported target and observed distributions

| Axis | Target | Observed |
|---|---|---|
| Modality profile | `V=2`, `S=2`, `A=2`, `V+S=2`, `V+A/S+A=2`, `V+S+A=2` | exact match |
| Hop | one-hop `6`, multi-hop `6` | exact match |
| Temporal | near/local `6`, far/separated `6` | near/local `7`, far/separated `5` |
| Intervention template | necessity-group withholding `6`, modality-channel outage `6` | targets retained as templates; not executed |

The single observed temporal shortfall is therefore one far/separated slot,
with one extra near/local slot. The target intervention field is not an
observed causal result.

## 6. P tiers and machine diagnostics

### Tier counts

| Population | P0 | P1 | P2 |
|---|---:|---:|---:|
| 12 reported slots | 2 | 0 | 10 |
| 2 excluded calibrations | 1 | 0 | 1 |
| All 14 records | 3 | 0 | 11 |

P0 records are `F09`, `F11`, and excluded `CAL01`. Their tier remains P0
because the implementation did not count two independent machine methods for
them. No record was promoted to P1 merely to fill a tier.

P2 remains a machine-provisional diagnostic status. It does not establish
human sufficiency, minimality, necessity, pair isolation, or route saturation.

### Leave-one-out and modality-drop diagnostics

- machine leave-one-out records: **22**, one for every preferred machine
  evidence unit in the 14 proposed records;
- modality/shortcut drop records: **70**, exactly five per proposed record;
- each record includes, in order:
  `drop_vision`, `drop_speech`, `drop_ambient`, `question_only`,
  `metadata_only`;
- every leave-one-out and modality-drop record keeps the corresponding human
  assertion false.

### Alternative-route risk

Among the 12 reported slots:

```text
high: 10
not_detected_by_machine_search: 2
```

The latter label is not evidence that no alternative exists. It means the
bounded machine search did not detect one. Human blind full-source search and
saturation remain required.

### Official sidecar shortcut audit

Among the 12 reported slots:

```text
official transcript shortcut risk true: 8
official transcript shortcut risk false: 4
```

The four false records are the NOAA development slots, for which this miner
does not load official sidecars. All sidecar matches are explicitly:

- `alternative_or_derived_route_risk_only`;
- not searchable as primary family evidence;
- not citable.

The MIT PDF sidecar remains binary identity only; timed SRT/WebVTT and untimed
HTML routes are used only for shortcut/derived-route challenge.

### Derived-route closure and C/B/R templates

All 14 proposals contain:

- a derived-route closure registry with
  `all_entries_machine_complete=true`;
- all four template states:
  `CLEAN`, `BLOCKED`, `RESTORED`, and `NO_TRIGGER`;
- `template_only_not_executed=true` in every state;
- `human_pair_isolation_asserted=false`;
- no active intervention output.

There are **14/14** complete machine closure records and **14/14** structurally
complete C/B/R/no-trigger templates.

## 7. Hash and permission audit

### Candidate registry

```text
file SHA-256:
e97a07def01a26a7d87f1ff5fef0e13e257a0876679ef17d8e7961136ae44ba9

internal registry hash:
sha256:2287bb50d34ef2422ae63df89c81533d7eb7e982f6c6b65e5492f33faa107a85

file mode: 0600
parent directory mode: 0700
symlink: no
```

All 14 candidate self-hashes recompute exactly.

### Canonical new-source index

The canonical verifier passed all 395 checks. Direct recomputation also
confirmed all five internal self-hashes and these file hashes:

| Artifact | File SHA-256 |
|---|---|
| `segment_manifest.json` | `f73606374dfe2bf2904f634c124d27d9f4f002b60aec55e41b34c18847fb2114` |
| `observation_manifest.json` | `d60f930fd6909a0b8d57b82b31a4a82213c6209b6f06f135d35c3f3270cd52c5` |
| `full_timeline_index.json` | `6f8f7fb3e13a4a374901b79220f55b4e5b18d8923d2c78302b383793d3dd122a` |
| `resource_manifest.json` | `9b93576a8031683ca022e1b0fbc1b8976f610024970f2d824b9024e6303918c6` |
| `build_manifest.json` | `93aa3baf32f1edfbc68415f572616d510fd130a1db51f537838131f14fb60800` |

The four build-manifest inventory hashes, 16 checkpoint hashes, four source
manifest hashes, four primary-media hashes, and five official-sidecar hashes
were independently recomputed. All matched. Restricted files were `0600` and
restricted roots were `0700`.

### Frozen NOAA development inputs

The Scale-1A verifier passed and its 94-item trust-anchor inventory remained
valid. The family adapter's three top-level frozen artifacts also passed:

| Artifact | File SHA-256 |
|---|---|
| `full_timeline_index.json` | `4ae19541e0a4e77af72f59ab6ae0a11b3e4f35e8d3887e1c21467d6329a6f0af` |
| `migrated_families.json` | `26d1375df19106cc1d656e8cbc72927a1a9bdf46bceab5d972e2308fa6dab2ca` |
| `build_manifest.json` | `90c8a4f83fc8c3c4d284f8d6e6db6c049acbd07968d697d240d79311628f6dea` |

The NOAA index, migration, and build-manifest internal hashes recomputed
exactly. The exact `cand-049`, `cand-051`, and `cand-052` source-media hashes
and `0600` modes were independently verified.

### Frozen pivot inputs

All seven `authoritative_inputs` hashes recorded by
`data/rehearsal_plan/cvpr_pivot_gate_registry.json` recomputed exactly,
including the safe aggregate and controller-v3 development result. No
controller evaluator key, human-review restricted key, or evaluator-private
label was accessed by the miner.

## 8. Safety-boundary audit

The registry and execution satisfy the required boundary:

- H1 count: **0**;
- H2 count: **0**;
- human-reviewed count: **0**;
- human-gold count: **0**;
- final accepted family count: **0**;
- active intervention count: **0**;
- trajectory count: **0**;
- evaluation/metric result count: **0**.

Question and answer fields are explicitly machine hypotheses requiring human
replacement, repair, or rejection. The C/B/R structures are inert templates.
Sidecars are non-citable challenge routes. NOAA remains development-only.

## 9. Changed files and blockers

### Changed files

- `src/av_trace_mini_pilot_families/adapters.py`
- `src/av_trace_mini_pilot_families/mining.py`
- `tests_mini_pilot_families/test_adapters.py`
- `tests_mini_pilot_families/test_cli.py`
- `tests_mini_pilot_families/test_mining.py`
- `data/restricted/mini_pilot_family_candidates_v1/candidate_registry.json`
- `docs/review/mini_pilot_family_candidates_execution_audit.md`
- `orchestration/results/142_mini_pilot_family_candidates_execution.txt`

The mounted `.git` directory contains no repository metadata, so Git status
and diff-based attribution were unavailable. No concurrent edits were
reverted.

### Remaining blockers

There is no blocker to preserving or handing off this machine-provisional
candidate registry.

There are explicit blockers to every later scientific or human-validity
claim:

1. three reported candidates require temporal relabel/review;
2. ten of 12 reported candidates carry high machine-detected
   alternative-support risk;
3. eight of 12 reported candidates carry official-sidecar shortcut risk;
4. all minimality, necessity, sufficiency, route saturation, pair isolation,
   rights/privacy suitability, and question/answer correctness judgments
   remain human-unvalidated;
5. Gate A staffing, forms, role independence, full-source human search,
   source-specific governance, and calibration execution are outside this
   task and are not completed here.

## 10. Final token

```text
REAL_FAMILY_CANDIDATES_REPAIR
```
