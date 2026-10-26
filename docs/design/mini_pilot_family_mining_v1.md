# Mini-pilot machine-provisional family mining v1

**Date:** 2026-09-23  
**Status:** implementation ready; canonical new-source index incomplete  
**Output class:** P-tier candidate proposals only  
**Human or final families created by this workstream:** **0**

## 1. Scope and hard boundary

This workstream implements the mining layer between the frozen full-timeline
indexes and the later Task-108 human construct-validity workflow. It can
propose machine records at:

```text
P0_MACHINE_CANDIDATE
P1_MACHINE_CROSS_VALIDATED
P2_MACHINE_COUNTERFACTUAL_VALIDATED
```

It cannot emit `H1_HUMAN_VALIDATED`, `H2_HUMAN_ADJUDICATED_GOLD`, or a final
accepted family. Machine leave-one-out and modality-drop checks are diagnostics,
not human minimality or necessity judgments.

The implementation reads only:

- the canonical four-source mini-pilot full-timeline index after its full,
  non-smoke build is frozen;
- the frozen NOAA Scale-1A full-timeline index and five retained
  machine-provisional development families;
- source-plan official transcript sidecars for alternative/derived-route
  challenge only.

It does not read controller evaluator keys/labels or the human-review
restricted key. It does not modify Scale-1A, source media, current family
results, or human forms.

## 2. Inputs and fail-closed readiness

### New-source canonical adapter

`load_canonical_new_source_index` requires all five artifacts under
`data/restricted/mini_pilot_index_v1/`:

1. `segment_manifest.json`
2. `observation_manifest.json`
3. `full_timeline_index.json`
4. `resource_manifest.json`
5. `build_manifest.json`

The build must have `status=COMPLETE`, `smoke_seconds=null`, exactly four
complete sources, valid self-hashes, frozen artifact hashes, full planned
lattice counts, and a terminal boundary proving that the index builder itself
did not generate families, negatives, interventions, trajectories, or
evaluation.

The normal runner performs this check before mining. As of 2026-09-23 the
canonical directory has only `segment_manifest.json` and
`resource_manifest.json`, so the runner intentionally returns `NO_GO`. The
completed eight-second smoke index is also explicitly rejected.

### NOAA development adapter

`load_frozen_noaa_development` verifies the frozen Scale-1A index and migrated
family files against the Scale-1A build inventory. It requires exactly five
retained families, all still machine-provisional, with all human-review,
human-gold, human-minimality, and human-necessity flags false.

NOAA sources are assigned `NOAA_CONSUMED_DEVELOPMENT_ONLY` and are ineligible
for a future primary test split.

### Official transcript sidecars

SRT/WebVTT sidecars are parsed into time-bound lexical route records. Untimed
HTML is parsed as an untimed lexical route, and PDF is retained as binary
identity only. Sidecars are:

- not primary searchable index records;
- not citable evidence;
- not answer labels;
- used only to flag transcript/caption shortcuts and to close derived routes.

## 3. Frozen slot design

The committed deterministic registry contains **14 fixture slots**:

- **12 reported candidate slots**;
- **8 new-source slots**, exactly two per each of four new sources;
- **4 NOAA development slots**, exactly two per each of two NOAA sources;
- **2 calibration slots**, excluded from every reported denominator.

Across the 12 reported slots the target hypotheses are exactly:

- 2 `V`;
- 2 `S`;
- 2 `A`;
- 2 `V+S`;
- 2 `V+A/S+A`;
- 2 `V+S+A`;
- 6 necessity-group withholding and 6 modality-channel outage;
- 6 one-hop and 6 multi-hop;
- 6 near/local and 6 far/separated.

These are selection targets only. Mining records observed strata separately.
Missing modalities leave a slot unfilled; mismatches produce
`PROPOSED_RELABEL_REQUIRED`. No code relabels evidence to satisfy a quota.

## 4. Mining helpers

The package implements:

- **speech BM25:** compatible with both the mini-pilot nested search payload
  and the Scale-1A flat speech schema;
- **visual vector search:** frozen CLIP text embeddings against float16 stored
  vectors, with an explicit encoder dependency;
- **visual routing audit:** blank-frame, face-presence, and motion/change
  summaries; routing features are never semantic evidence;
- **ambient label search:** weighted sparse label overlap with generic-label
  tracking and explicit model-prediction status;
- **official sidecar challenge:** lexical matching for alternate and derived
  speech routes, never citation;
- **temporal selection:** deterministic near/far selection over candidate
  intervals;
- **duplicate and alternative-route risk:** overlap, shared binding cells,
  score ratios, and high-scoring separated alternatives.

The implementation deliberately creates machine observation claims rather than
asserting factual source claims. A human author must replace, repair, or reject
the generated question and answer hypotheses.

## 5. Candidate record contract

Each proposed candidate contains:

1. source/version provenance and construction split;
2. machine question and answer hypotheses;
3. atomic machine-observation claim hypotheses;
4. exact evidence intervals and source segment IDs;
5. preferred and alternative SES hypotheses;
6. machine leave-one-out checks;
7. five machine counterfactual records:
   `drop_vision`, `drop_speech`, `drop_ambient`, `question_only`,
   `metadata_only`;
8. a derived-route closure registry across direct, overlapping/context,
   shared-binding, speech-chunk-derived, and official-sidecar routes;
9. inert `CLEAN`, `BLOCKED`, `RESTORED`, and `NO_TRIGGER` templates;
10. duplicate, alternative support, sidecar shortcut, routing, governance,
    and unvalidated-minimality/necessity risk flags;
11. target and observed strata with explicit mismatch/relabel status.

Tier logic is conservative:

- P0 requires a versioned machine evidence proposal.
- P1 additionally requires at least two machine methods and attempted
  alternative-route challenge.
- P2 additionally requires machine leave-one-out, all five modality/shortcut
  counterfactuals, derived-route closure, and C/B/R restoration templates.

P2 still means machine-provisional. It is not a claim that support,
sufficiency, minimality, necessity, pair isolation, or route saturation is
human valid.

## 6. Deterministic dry-run fixture

`data/rehearsal_plan/mini_pilot_family_mining_v1.json` is generated by
`build_dry_run_fixture_registry()`. It reads no index, source media, transcript,
or current family payload. Its 14 records are slot fixtures, not mined or
accepted families.

Run:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_family_candidates.py --dry-run
```

The default command is a canonical-input preflight:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_family_candidates.py
```

It currently fails with `CANONICAL_INDEX_INCOMPLETE_MISSING` and generates no
candidate artifact. After the canonical index is complete, explicit execution
requires an output under:

```text
data/restricted/mini_pilot_family_candidates_v1/
```

Example future command:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_family_candidates.py \
  --execute \
  --output data/restricted/mini_pilot_family_candidates_v1/candidate_registry.json
```

No real execution is performed by this task.

## 7. Safety invariants

- All emitted candidate tiers are P0/P1/P2.
- Human review, human gold, final acceptance, human minimality, and human
  necessity are always false.
- The runner refuses smoke or incomplete canonical indexes.
- Calibration records are marked excluded from reported denominators.
- Source splits are by source group; NOAA is development-only.
- Official sidecars remain non-citable route-challenge material.
- C/B/R records are templates until a later authorized intervention build.
- No target stratum is forced when machine evidence does not support it.

