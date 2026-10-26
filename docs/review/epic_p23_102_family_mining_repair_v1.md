# EPIC P23_102 family-mining repair review v1

**Date:** 2026-10-14  
**Binding input:** `data/rehearsal_plan/epic_p23_102_zero_candidate_audit_v1.json`  
**Decision:** `REPAIR_SUCCEEDED_MACHINE_PROVISIONAL_ONLY`  
**Completion token:** `EPIC_P23_102_FAMILY_MINING_REPAIR_READY`

## 1. Scope and safety boundary

This review covers the prospective repair and rerun of the P23_102 structural
family miner. Work was limited to the owned miner, focused test, committed plan,
design document, and this review document. The existing development candidate
registry was rerun as explicitly requested.

The repair did not inspect EPIC semantic annotations, manually inspect source
content, decode media, load models, access the network, or use human labels.
It did not accept a family or SES, assign an H tier, grant Gate-A credit, or
assert modality necessity. All emitted leads remain machine-provisional and
require the unchanged source-uniform human prescreen before any separate
acceptance process.

## 2. Repairs implemented

### 2.1 Source-calibrated visual transition

The unreachable fixed transition floor `0.18` was removed. The frozen rule is
now computed from all searchable fine-window transition values, without labels:

`max(0.02, p95_linear, median + 2 * MAD)`

The completed-index calibration was:

| Component | Value |
|---|---:|
| Minimum absolute effect | `0.02` |
| Median | `0.03620279` |
| MAD | `0.01675260` |
| Median + 2 MAD | `0.06970799` |
| p95 | `0.08093195` |
| Selected threshold | **`0.08093195`** |
| Passing fine windows | **45 / 892** |

The registry records the distribution, quantile interpolation, robust term,
absolute floor, selected threshold, and pass count. These values are structural
routing diagnostics, not semantic labels.

### 2.2 All-fine far-pair search

Far generation is no longer derived from local rows. The miner evaluated all
eligible unordered fine-window pairs at least 120 seconds apart, then applied
visual continuity and independent speech or audio structural bridges.

| Far filter stage | Count |
|---|---:|
| Pairs at minimum separation | `371,952` |
| Visual continuity `>= 0.88` | `61,084` |
| Quality-gated speech at both components | `0` |
| Speech lexical/strong-visual bridge | `0` |
| Audio structural floor at both components | `20,347` |
| Audio continuity `>= 0.80` | `1,129` |
| Raw far rows | `1,129` |
| Retained after deterministic diversity and cap | **8** |

Thus the sparse speech join is reported honestly, while speech-free V+A far
structural leads remain possible. Distance alone is not credited; every far
lead carries visual and audio continuity metrics, an unfilled coherence
hypothesis, recurrence checks, and substitution risks.

### 2.3 Audio novelty, RMS, and silence accounting

Audio novelty is computed against immediate neighbors in the independently
ordered fine-audio sequence, using a deterministic segment-position map. The
completed index reports:

| Audio diagnostic | Count |
|---|---:|
| Fine windows | `892` |
| Novelty `>= 0.16` | `459` |
| RMS `>= 1e-5` | `892` |
| Not `NEAR_SILENCE` | `892` |
| Joint novelty/RMS/silence pass | `459` |
| Joint structural plus sparse searchable-speech pass | `459` |

Final candidate emptiness is no longer used to claim that no audio window
cleared structural floors. Structural audio routing is explicitly separated
from any claim that audio is meaningful or answer-bearing.

### 2.4 Sparse-speech handling

The index contains 119 ASR chunks, one quality-gated searchable chunk, and 118
inventory-only chunks. The rerun records
`inventory_only_promoted_to_searchable: 0`.

No emitted lead has a speech handle because the sole searchable chunk does not
survive the repaired local or far joins. Consequently:

- `V+S`: zero, with no source-level absence inference;
- `V+S+A`: zero, with no source-level absence inference;
- `V+A`: permitted from qualifying visual/audio structure;
- inventory-only text never contributes terms, handles, or ranking evidence.

### 2.5 Deterministic caps and diversity

Local rows are center-deduplicated, limited to two per 300-second time bin, and
capped at 12. Far rows allow one retained use per endpoint, at most two leads
per frozen separation bucket, at most two per 600-second first-component bin,
and eight total.

The completed rerun records 10 local center-dedup rejections, six local time-bin
rejections, 104 far endpoint-reuse rejections, 632 far separation-bucket
rejections, and nine far first-component-bin rejections. These are deterministic
review bounds and do not force a quota.

## 3. Completed-index rerun result

The existing registry was regenerated at:

`data/restricted/epic_p23_102_family_mining_v1_dev/candidate_registry.json`

Result:

| Measure | Count |
|---|---:|
| Total machine leads | **20** |
| Near-local V+A | `12` |
| Far/multi-hop V+A | `8` |
| V+S | `0` |
| V+S+A | `0` |
| KEEP | `0` |
| REPAIR | **20** |
| REJECT | `0` |
| Accepted families / SES / H tiers / Gate-A | **all 0** |

The count of 20 is an honest output of the frozen structural rules and caps,
not a target. All leads are `REPAIR` because no semantic review, listening,
source-world coherence validation, recurrence adjudication, or modality-
necessity determination has occurred.

Registry bindings after the final rerun:

- plan payload: `sha256:a798a999b361a5c05f07d164886ad633a1922677ac4a18a1924f3ce0cb8ae1df`;
- registry payload: `sha256:6c2aa00b0e73f632c9a5f999d39bf9a16b1ec9eb7fa5812f4a85dd218d1fdba3`;
- registry file: `sha256:981ae0b7eac8206d62826a881321dda5a17a3f8a77e0342c14e1d2bc2404ba90`.

## 4. Validation and tests

Commands completed successfully on 2026-10-14:

```text
pytest -q tooling/tests/test_epic_p23_102_family_mining_v1.py
.........                                                                [100%]

python tools/epic_p23_102_family_mining_v1.py --mode mine \
  --output data/restricted/epic_p23_102_family_mining_v1_dev/candidate_registry.json
EPIC_P23_102_FAMILY_MINING_MACHINE_PROVISIONAL_COMPLETE

python tools/epic_p23_102_family_mining_v1.py --mode check \
  --registry data/restricted/epic_p23_102_family_mining_v1_dev/candidate_registry.json
EPIC_P23_102_FAMILY_MINING_REPAIR_READY
```

Focused tests now cover deterministic plan/hash agreement, the frozen
source-calibration rule, exact evidence binding, all-fine far generation even
when local transition passage is forced to zero, sparse-speech V+A behavior,
non-promotion of inventory-only ASR, corrected audio accounting, deterministic
diversity caps, recurrence/substitution fields, source-uniform prescreening,
and rejection of acceptance/hash/handle tampering.

## 5. Remaining risks and required next step

The repair makes the mining result structurally auditable; it does not validate
the 20 leads. Principal risks remain:

- visual recurrence or camera motion may mimic a state change;
- cross-window similarity may be recurrent context rather than one chain;
- CLAP novelty or continuity may be speech leakage, background ambience, or
  incidental handling;
- an intervening or repeated route may substitute for the proposed evidence;
- the lack of speech leads reflects the current quality-gated join, not proven
  source-level absence.

Every machine lead must receive the same source-uniform human prescreen and
full-source recurrence exposure before any separately authorized acceptance
protocol. This repair intentionally leaves all candidates unaccepted and
untiered.

**EPIC_P23_102_FAMILY_MINING_REPAIR_READY**
