# Task 89 — Independent red-team of the NOAA-01 real-A/V MVP

**Audit date:** 2026-09-10  
**Stage:** `MACHINE_ADJUDICATED_PROVISIONAL_MVP`  
**Human reviewed:** `false`  
**Gold annotation:** `false`

## Executive decision

- **`ENGINEERING_GO`**
- **`PROVISIONAL_SCIENTIFIC_INCONCLUSIVE`**
- **`FINAL_BENCHMARK_NOT_YET_VALIDATED`**

Task 87 is a valid bounded engineering/protocol MVP, not a validated scientific benchmark or a learned-model comparison. The audit independently verified source provenance, decoded all 18 exact review intervals from the original MP4 files with both audio and video enabled, recomputed all 72 metric rows, inspected all six intervention families, checked the 12 no-trigger controls, and checked all 10 Task 87 manifest hashes. Several metric and baseline-design limitations were found; they do not overturn the engineering result, but they prevent a provisional scientific GO.

## Scope independently observed

- 6 retained provisional families, exactly matching the Task 85 gate:
  - `noaa01-review-004`
  - `noaa01-review-007`
  - `noaa01-review-011`
  - `noaa01-review-014`
  - `noaa01-review-016`
  - `noaa01-review-017`
- 3 source assets: `cand-049`, `cand-051`, `cand-052`
- 18/18 reviewed windows represented in the frozen index
- 54 modality-specific frozen-index records
- 72 main trajectories: 6 families × 3 states × 4 policies
- 12 RESTORED no-trigger controls
- All outputs retain the required machine-only and non-gold boundary.

## 1. Data and provenance

### Passed

1. The family set exactly equals Task 85's six retained windows.
2. Family candidate IDs, review IDs, source-measurement IDs, and intervals agree across the Task 82 queue, Task 84 records, Task 85 gate, acquisition manifest, media audit, and Task 87 family/index files.
3. For all three used assets, local byte size and SHA-256 were independently recomputed and matched the acquisition manifest and Task 87 source bindings.
4. The source durations and A/V stream declarations match the media audit.
5. The frozen index contains all 18 reviewed windows and 54 records.
6. Searchable records contain machine observation text, but no question, answer hypothesis, claim graph, reviewer rationale, state role, or intervention ID fields.
7. Every family retains at least two same-source distractor windows after the implemented alias filter.

### Boundary

Distractor admission is only a bounded lexical/alias check plus machine synthesis. It is **not** an exhaustive human entailment determination. Therefore “non-answer-bearing” remains provisional.

### Permission repair

The four restricted JSON files were already mode `0600`, but their immediate directory was mode `0755`. Task 89 changed:

```text
data/restricted/noaa01/real_av_mvp  0755 -> 0700
```

`mvp/results/noaa01_real_av_mvp/run_manifest.json` disclosed restricted artifact paths/hashes while being mode `0644` and had no restricted marker. Task 89:

- changed it to mode `0600`;
- added `"restricted": true` to the current manifest;
- patched `src/av_trace_real_av/core.py` so future manifests are also emitted as restricted mode `0600` with that marker.

No Task 87 media/trajectory regeneration was needed for this permission-only repair.

## 2. Real-media execution

The implementation was traced rather than accepted from its report:

- `RealBackend.observe()` invokes `SourceVerifier.verify()` before each citable observation, and that verifier re-hashes the complete registered source file.
- It constructs the exact source-time `TimeInterval` and invokes `PyAVMediaReader.read()` at tool time.
- Vision observations require video decode coverage; speech and ambient observations require audio decode coverage.
- `direct_context()` also opens and decodes each accessible exact interval from the original source, though it hashes once for the single direct-context tool invocation.
- Frozen JSON supplies semantic observation text, but it is not accepted without touching and decoding the original media.

Task 89 independently decoded all 18 queue intervals from the three source MP4s with `include_video=true` and `include_audio=true`. Results:

```text
cand-049: 6/6 A/V intervals
cand-051: 6/6 A/V intervals
cand-052: 6/6 A/V intervals
Total:    18/18
```

Stored trajectory observations exercised all modalities:

```text
vision observations:  178
speech observations:  109
ambient observations: 108
```

No citable observation had missing required-channel coverage. No NOAA frame, audio, or clip derivative was found under the restricted NOAA tree. The previously existing `/tmp/avtrace_media_contact.jpg` is a synthetic contact sheet, not a Task 87 NOAA derivative.

## 3. Agent blindness and baseline honesty

### Passed

The capability-limited `BlindPolicySession` exposes only:

- question;
- video duration;
- tool list and costs;
- budget;
- opaque search pointers, modality, interval, generic preview, and score;
- citable observation payloads after decode.

It does not expose state role, family/intervention ID, answer hypothesis, support/evidence IDs, or evaluator-private route mapping through its public methods. Timestamp binding for `r004` and `r016` uses only intervals returned to the policy. The search still ranks with the public query and frozen content; the timestamp heuristic does not directly read the gold route.

Direct and single-shot policies receive `Recovery=null`. All four are labeled `deterministic-protocol-policy/1.0` and `learned_model=false`.

### Limitation

The harness is in-process, not an OS subprocess. The blindness result is therefore a capability/API-contract property, not a hard process-isolation guarantee. That is allowed by Task 87's “subprocess-compatible or equivalently isolated” wording for this bounded MVP, but should be strengthened before release.

## 4. Intervention validity

Task 89 recomputed each family against the frozen index and actual traces. All six passed the bounded protocol checks:

| Family | CLEAN route | BLOCKED suppression | Distractors ≥2 | Pre-trigger match | Trigger | Reacquired | No-trigger blocked | Budget fixed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `r004-surf-av` | pass | pass | pass | pass | pass | pass | pass | pass |
| `r007-opening-plastic-waste` | pass | pass | pass | pass | pass | pass | pass | pass |
| `r011-bag-by-fence` | pass | pass | pass | pass | pass | pass | pass | pass |
| `r014-aircraft-storm-view` | pass | pass | pass | pass | pass | pass | pass | pass |
| `r016-three-factors-vs` | pass | pass | pass | pass | pass | pass | pass | pass |
| `r017-north-atlantic-basin` | pass | pass | pass | pass | pass | pass | pass | pass |

For `r004` and `r016`, RESTORED runs first observe a policy-visible interval in the other modality, encounter the registered channel outage, call status, then select and decode the co-timed restored record. Their no-trigger controls do not reacquire the affected evidence.

The fixed-call triggers are deterministic and answer/model independent. The channel-status trigger is also deterministic, although the observable outage response is intentionally the intervention signal.

## 5. Independent metric recomputation

Task 89 independently reconstructed acquired evidence IDs from observation provenance and recomputed every published metric row using the implemented formulas.

```text
Rows recomputed: 72
Row-level mismatches versus episode_metrics.csv: 0
Aggregate mismatches versus report.json: 0
Modality Recall non-null rows: 0
Non-agentic Recovery non-null rows: 0
```

The published aggregate values are therefore arithmetically reproducible under Task 87's current definitions. In particular:

- Direct long-context Acquire metrics are `null`, while Answer Score remains non-null as allowed for a protocol-oracle grounding check.
- Modality Recall is universally `null`, correctly preserving the absence of human-validated modality necessity.
- ReAct and Evidence-Sufficiency have identical trajectories and aggregate vectors.
- The report explicitly calls the six-family pilot descriptive and low-N.

### Metric defects/limitations found

1. **Supported-Claim Rate is semantically weak.** The code computes the number of evaluator-required claims whose evidence was acquired, divided by the number of verbatim observation assertions. It does not actually map each asserted claim to a supported registered claim. This explains the direct baseline's very low aggregate `0.058642`. The value is reproducible but should be renamed as a proxy or replaced with claim-level mapping before scientific use.
2. **Success@Budget is a proxy.** It uses `answer_correct AND all_evidence_success` plus budget checks, rather than an explicit supported-finalization predicate with claim-level citation validation.
3. **Premature Stop feasibility is coarse.** Eligibility is inferred from CLEAN/RESTORED state rather than a certified feasible route under the exact remaining steps and cost at the final decision point. A concrete symptom is the RESTORED `r017` single-shot run: it ends `insufficient` without evidence but is scored premature-stop `0`, even though the route is available at the endpoint. The metric should be considered provisional.
4. **No distinct evidence-sufficiency policy exists yet.** `react-recovery` and `evidence-sufficiency` share the exact same code branch, traces, and aggregate vectors. This fails the Task 86 provisional-science criterion requiring Act separation between those policies.
5. **Low-N metadata is incomplete at aggregate level.** The per-metric warning threshold does not fire at exactly six families and three sources. Prose correctly warns that the whole pilot is descriptive, but machine consumers should also receive an unconditional pilot-scale warning.
6. Direct long-context concatenates all accessible frozen observations, so its Answer/Ground values are protocol-plumbing checks, not realistic long-context model behavior.

Under the user's instruction to stop long reruns, Task 89 did not redefine these metrics and regenerate all 72 trajectories. The flaws are recorded rather than hidden, and the scientific decision remains `INCONCLUSIVE`.

## 6. Reproducibility and tests actually completed

Task 89 actually completed:

```text
PYTHONPATH=src python /tmp/task89_audit.py
PASS
- exact retained-set/provenance checks
- 18/18 independent exact-interval A/V decodes
- 72/72 independent metric-row recomputations
- 0 metric mismatches
```

```text
PYTHONPATH=src pytest -q tests_real_av
11 passed
```

```text
PYTHONPATH=src python -m py_compile \
  src/av_trace_real_av/core.py \
  scripts/build_noaa_real_av_mvp.py \
  scripts/run_noaa_real_av_mvp.py
PASS
```

```text
Independent Task 87 run-manifest hash recomputation
10/10 hashes matched before the permission/marker-only manifest repair
```

Not performed by Task 89, per the request to stop further long-running reruns:

- no complete build-and-run replay of all media trajectories;
- no rerun of the full Task 87 multi-suite test command.

Task 87 previously reported `437 passed`, but this audit does **not** represent that prior result as independently rerun.

## 7. Leakage and persistence

A public-artifact scan found no raw media basename, `.mp4` path, transcript payload field, AST prediction field, model weight name, proxy credential, or raw NOAA transcript excerpt in the public report/CSV/review files. The run manifest intentionally contains restricted artifact inventory paths and is now marked and permissioned as restricted.

## Defects and repairs summary

| ID | Severity | Finding | Task 89 action |
|---|---|---|---|
| D89-01 | Medium | Restricted MVP directory mode was `0755`. | Changed to `0700`. |
| D89-02 | Medium | Run manifest exposed restricted paths/hashes at mode `0644` without marker. | Added restricted marker, changed to `0600`, patched future writer. |
| D89-03 | Medium | Supported-Claim Rate is not true assertion-level support. | Recorded; no metric regeneration. |
| D89-04 | Medium | Success@Budget and Premature Stop are proxy implementations. | Recorded; no metric regeneration. |
| D89-05 | Medium | ReAct and Evidence-Sufficiency are behaviorally identical. | Recorded; blocks scientific GO. |
| D89-06 | Low | Pilot-wide low-N warning is prose-only for some aggregate rows. | Recorded. |
| D89-07 | Low | Direct baseline is an oracle-style concatenation probe. | Existing honest labeling retained. |

## Final judgment

### `ENGINEERING_GO`

The bounded pipeline genuinely binds three long source videos, checks original bytes, decodes exact A/V intervals at citable access, executes deterministic C/B/R behavior, produces 72 valid trajectories, and reproduces its current metrics and intervention outcomes.

### `PROVISIONAL_SCIENTIFIC_INCONCLUSIVE`

The current run demonstrates that the intervention and measurement machinery can create different acquisition/grounding/action outcomes, but it does not establish benchmark validity. The evidence-sufficiency baseline is not behaviorally distinct, key Ground/Act metrics are provisional proxies, annotations are machine-generated, and N is extremely small.

### `FINAL_BENCHMARK_NOT_YET_VALIDATED`

Human validation of answers/evidence/counterfactuals, a real claim-level grounding evaluator, certified final-step route feasibility, behaviorally distinct learned baselines, broader sources, and release review remain required.
