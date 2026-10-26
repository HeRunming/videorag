# EPIC family mining and authoring assistance v1

**Date:** 2026-09-28  
**Implementation status:** ready; real-source mining intentionally not run  
**Current execution blocker:** the active canonical EPIC index is incomplete  
**Output class:** machine-provisional P-tier event-centric leads only

## 1. Scope

This layer is isolated from the generic `av_trace_mini_pilot_families`
implementation but reuses its frozen local CLIP text encoder. It is specific to
the two EPIC-KITCHENS-100 Wave-1 recordings:

- `P27_101`, source/participant group `P27`;
- `P28_103`, source/participant group `P28`.

The implementation owns only:

- complete-index intake and verification;
- initial machine candidate mining from nonsemantic source-derived signals;
- human-prescreen-gated authoring assistance;
- inert Task-145 `CLEAN/BLOCKED/RESTORED/NO_TRIGGER` templates;
- proposal validation and a restricted-output verifier.

It does not own or modify the active index build, its checkpoints, source
media, Task-153 forms, existing EPIC annotations, human construct review,
intervention execution, or Gate A.

## 2. Execution interlock

The normal and development paths both call
`load_canonical_epic_index(...)` before mining. The adapter requires all five
canonical artifacts under `data/restricted/epic_wave1_index_v1/`:

1. `segment_manifest.json`;
2. `observation_manifest.json`;
3. `full_timeline_index.json`;
4. `resource_manifest.json`;
5. `build_manifest.json`.

The build must be `status=COMPLETE`, `mode=full`, have
`smoke_seconds=null`, contain exactly the two frozen source IDs, bind the
committed index plan and source hashes, pass all self-hash and artifact-hash
checks, expose exactly eight complete checkpoints, match the frozen full
lattice counts, and retain the index terminal boundary stating that no
families, interventions, trajectories, or evaluation were generated.

Smoke output is never accepted. Missing files fail with
`EPIC_CANONICAL_INDEX_INCOMPLETE_MISSING` before any checkpoint is opened.

As of this implementation task, the active canonical root contains only the
segment and resource manifests plus a partially populated checkpoint tree.
Task 164 has no completed result artifact. Consequently, Task 165 did not run
mining and did not read or alter active checkpoint payloads.

## 3. Initial mining inputs and annotation firewall

Initial mining consumes only the completed canonical index:

- OpenCV `motion_or_change`, edge density, blank-frame, and related
  nonsemantic routing observations;
- frozen CLIP image embeddings queried with generic event and
  static/text/overlay prompts;
- frozen Whisper ASR observations;
- frozen AST AudioSet observations.

The initial miner has no argument for a semantic prescreen, EPIC action data,
EPIC narrations, or EPIC-SOUNDS records. Human prescreen information is joined
only after `mine_initial_machine_leads(...)` returns.

The adapter recursively rejects semantic EPIC field names outside lexical
vocabulary maps. Input path resolution rejects `.staging`, symlinks, path
escape, `annotation_vault`, `epic_sounds`, and `epic-sounds`. The source
provenance records:

```text
semantic_epic_annotations_accessed = false
existing_annotation_vault_accessed = false
```

This is an implementation guard, not evidence that every external process is
clean. Operational role separation and audit logs remain required.

## 4. Event-centric mining

The miner scores every searchable eight-second fine visual window. It combines:

- dynamic visual change from OpenCV;
- CLIP similarity to generic physical-action/state-change prompts;
- a penalty signal from CLIP similarity to text, caption, package, board,
  static-sign, and overlay prompts;
- overlapping non-generic AST observations;
- overlapping searchable ASR lexical diversity.

The score ranks inspection leads. It does **not** state what event happened,
what was said, or what sound occurred.

Each selected lead carries a four-way observation classification:

1. `dynamic_nontext_visual`;
2. `board_ocr_static_overlay`;
3. `speech`;
4. `non_speech`.

The first two are deliberately separate. A static package, sign, screen,
caption, overlay, or OCR-like route cannot be promoted to dynamic visual
evidence merely because CLIP retrieves it. AST class names and ASR terms are
also machine observations, never semantic answer evidence.

## 5. Exactly two leads per source

The output contract is exactly:

- two source records;
- two candidate leads per source;
- four candidate leads total.

Lead 1 is the highest-ranked local event window and is always represented as
`one_hop` plus `near_local`.

Lead 2 first attempts to find an ordered event pair within 120 seconds under
one of three explicit composition placeholders:

- instruction or intent, then visible execution;
- audible event, then visible state change;
- visible action, then resulting state.

If no such machine-compatible pair exists, Lead 2 falls back to a distinct
one-hop/local interval. It does not receive a multi-hop label merely because
two intervals differ. Every multi-hop proposal contains:

- two component claim placeholders;
- one composed claim placeholder;
- an allowed composition operator;
- `arbitrary_distinct_interval_counting_forbidden=true`;
- `semantic_relation_human_validated=false`.

Thus, one-hop implies near/local, while a multi-hop lead may be near or far
only when it carries a real compositional claim structure for later human
verification.

Machine pair compatibility is intentionally conservative: adjacent
dynamic-plus-ambient windows are not enough. A pair must have at least four
seconds of non-overlap and a directional observation pattern (a non-dynamic
speech/ambient interval followed by a dynamic interval, or a dynamic interval
followed by a materially lower-motion non-text visual-state check). Otherwise
Lead 2 remains one-hop/local.

## 6. Human semantic prescreen interlock

Normal `gate_a_candidate_input` mode requires all three Task-153 artifacts:

- deterministic nonsemantic sample plan;
- completed trained-human annotation form;
- valid READY import report.

They are schema-validated and must bind by plan ID, plan hash, form ID, source
ID, and participant/source-group ID. Every source must be `pass`, READY,
error-free, and have `exposure_recorded=true`. Prescreen necessity, H1, and H2
must remain false.

For each lead, the authoring layer first checks source-level human observations
and separately links any interval-overlapping facts:

- a dynamic visual blueprint remains blocked unless the completed source
  prescreen contains at least one human `dynamic_non_text_visual_event`;
- a non-speech blueprint remains blocked unless the completed source
  prescreen contains at least one human `concrete_non_speech_audio_event`;
- speech blueprints remain provisional and require transcript/narration route
  closure.

A source-level pass without the relevant positive event category does not
unlock that modality. An interval-overlapping prescreen fact may be exposed as
additional authoring scaffolding, but it is not candidate validation and the
author must inspect the candidate interval directly.

## 7. Development-only mode

`--development-only` is explicit and still requires the full canonical index.
It may emit machine proposals without a human-complete prescreen, but the
registry is structurally marked:

```text
mode = development_only
eligible_to_enter_gate_a = false
development_only_outputs_permanently_ineligible = true
```

All ambient and dynamic visual question blueprints stay blocked pending a
completed positive human source prescreen. Development output may not later be
renamed or copied into Gate A input; it must be regenerated in normal mode
against a completed prescreen.

## 8. Required risks

Every lead explicitly flags:

- repeated-event and near-duplicate risk from whole-source machine search;
- participant-lineage leakage and the required participant-blocked split;
- kitchen-identity leakage;
- transcript/ASR substitution;
- OCR, static, caption, or overlay substitution;
- narration substitution;
- the prohibition on consulting the existing annotation vault.

Repeated events are not accepted alternative SESs. The records are only a
bounded list of machine-suspected recurrences for human route closure.

## 9. Task-145 C/B/R/N templates

Every lead carries the Task-145 exogenous restoration v2 structure:

- states exactly `CLEAN`, `BLOCKED`, `RESTORED`, `NO_TRIGGER`;
- fixed zero-based action index `4`;
- one frozen blocked prefix replayed into fresh R/N continuations;
- byte-identical public checkpoint events for R and N;
- primary contrast `RESTORED_minus_NO_TRIGGER`;
- mechanism-specific ITT analysis;
- no pooling of silent withholding and explicit outage;
- `RESTORED_minus_BLOCKED` secondary only;
- `get_channel_status` secondary/action-contingent only.

The mechanism is deliberately unassigned until later human construct review.
These objects are templates only:

```text
active_intervention = false
intervention_executed = false
scientific_execution_authorized = false
```

## 10. Commands

Show the committed plan without reading the index:

```bash
PYTHONPATH=src python scripts/build_epic_family_candidates.py --show-plan
```

Preflight normal mode after the full index and human prescreen are complete:

```bash
PYTHONPATH=src python scripts/build_epic_family_candidates.py \
  --prescreen-plan <task153-plan.json> \
  --prescreen-form <completed-human-form.json> \
  --prescreen-report <ready-import-report.json>
```

Emit normal proposals:

```bash
PYTHONPATH=src python scripts/build_epic_family_candidates.py \
  --execute \
  --prescreen-plan <task153-plan.json> \
  --prescreen-form <completed-human-form.json> \
  --prescreen-report <ready-import-report.json> \
  --output data/restricted/epic_family_candidates_v1/candidate_registry.json
```

Emit explicitly non-Gate-A development proposals:

```bash
PYTHONPATH=src python scripts/build_epic_family_candidates.py \
  --development-only \
  --output data/restricted/epic_family_candidates_v1_dev/candidate_registry.json
```

The CLI and verifier bind `development_only` registries to the separate
`data/restricted/epic_family_candidates_v1_dev/` root. They reject a
development registry placed under the normal Gate-A candidate-input root, and
reject a normal registry placed under the development root.

Verify an emitted registry without mining:

```bash
PYTHONPATH=src python scripts/verify_epic_family_candidates.py \
  --registry data/restricted/epic_family_candidates_v1/candidate_registry.json
```

## 11. Output and claim boundary

The registry permits only:

```text
P0_MACHINE_CANDIDATE
P1_MACHINE_CROSS_VALIDATED
P2_MACHINE_COUNTERFACTUAL_VALIDATED
```

It cannot assert H1, H2, accepted family, human minimality, human necessity,
Gate A GO, or an intervention outcome. P2 indicates machine diagnostics and
structured counterfactual placeholders, not construct validity.

No real-source candidate registry was generated by Task 165 because the
canonical index was not complete. Synthetic in-memory unit fixtures exercised
the mining and validation logic only.
