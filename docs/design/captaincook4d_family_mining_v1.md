# CaptainCook4D event-centric family mining and authoring assistance v1

**Task:** 190  
**Date:** 2026-10-10  
**Implementation decision:** `CAPTAINCOOK4D_FAMILY_MINING_IMPLEMENTATION_READY`  
**Real mining execution:** not run; Task189 READY was absent during Task190
validation

## 1. Purpose and boundary

This package prepares event-centric substantive candidate mining and bounded
authoring assistance for the three CaptainCook4D Wave-0 sources:

| Source | Source group | Person | Environment | Target leads |
|---|---|---:|---:|---:|
| `16_20` | `cc4d_p01_e08` | 1 | 8 | exactly 2 |
| `15_29` | `cc4d_p02_e02` | 2 | 2 | exactly 2 |
| `26_22` | `cc4d_p03_e03` | 3 | 3 | exactly 2 |

The implementation emphasizes:

- dynamic non-text procedure actions;
- meaningful non-speech procedure audio;
- coherent compositional multi-hop candidates, including far/separated pairs
  only when a real source-world relation is hypothesized;
- direct bounded frame and audio inspection to assist source-world question,
  answer, claim, and evidence authoring.

Every result remains `MACHINE_EXPERT_PROVISIONAL`. The package does not assign
H1/H2, accept an SES, claim modality necessity or minimality, authorize Gate A,
or execute a scientific intervention.

## 2. Task189 execution interlock

No index or source observation can be read until both conditions hold:

1. `orchestration/results/189_captaincook4d_wave0_full_timeline.txt`
   contains the exact terminal token
   `CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY`;
2. the canonical full, non-smoke index under
   `data/restricted/captaincook4d_wave0_index_v1/` passes artifact, self-hash,
   source, plan, count, permission, checkpoint, stage, and terminal-boundary
   checks.

The loader requires:

- `segment_manifest.json`;
- `observation_manifest.json`;
- `full_timeline_index.json`;
- `resource_manifest.json`;
- `build_manifest.json`;
- mode `full`, `smoke_seconds=null`, status `COMPLETE`;
- exactly sources `16_20`, `15_29`, and `26_22`;
- twelve bound checkpoints;
- no semantic annotations, families, interventions, trajectories, evaluation,
  or persisted media derivatives in the index boundary.

Task190 does not modify the Task189 package, plan, result, checkpoint tree, or
canonical output root. During implementation, Task189 had not published its
READY result; therefore real candidate mining was not run.

## 3. Semantic annotation firewall

Initial mining accepts only canonical raw-derived observations:

- OpenCV visual change/routing records;
- frozen CLIP embeddings queried with generic procedure prompts;
- frozen Whisper ASR observations;
- frozen AST AudioSet observations.

The adapter and provenance prohibit:

- CaptainCook4D action annotations;
- step annotations;
- task or procedure graphs;
- error or mistake labels;
- recipe labels;
- benchmark semantic labels, splits, prior QA, outcomes, or label-derived
  features;
- existing annotation-vault paths;
- Task153 human forms during initial machine lead selection.

The initial miner has no semantic-annotation or prescreen parameter. Task153
data can be joined only after the six machine leads exist. AST, CLIP, ASR, and
OpenCV values remain routing observations rather than source-world evidence.

## 4. Event-centric scoring

Each searchable fine visual window is summarized using:

- a dynamic-procedure CLIP prompt bank;
- a static/text/package/display CLIP prompt bank;
- OpenCV motion/change and edge routing;
- overlapping AST observations with generic speech/music/environment classes
  separated from possible concrete non-speech events;
- overlapping Whisper lexical diversity without copying verbatim transcript
  into an answer.

The event score gives its largest weight to dynamic non-text vision, followed
by concrete non-speech audio. Speech has a small routing contribution and is
always accompanied by a substitution warning. Static/text-likeness reduces
the score. The score ranks inspection leads; it does not state which action,
ingredient, tool, sound, or procedural result occurs.

Every lead has separate observation classes:

1. `dynamic_nontext_visual`;
2. `board_ocr_static_overlay`;
3. `speech`;
4. `non_speech`.

Static packages, appliance displays, captions, signs, or printed instructions
may not be relabelled as dynamic procedure evidence merely because CLIP
retrieves them.

## 5. Exactly two leads per source

The registry contract is exactly three source records and two leads per source,
for six total.

- Lead 1 is the strongest distinct local event lead.
- Lead 2 attempts a coherent composition, with a distinct one-hop/local
  fallback if no compatible pair exists.

One-hop is always `near_local`.

Multi-hop requires:

- at least two nonoverlapping component intervals;
- an allowed procedure relation;
- a claim hypothesis for each component;
- one composed source-world claim hypothesis;
- a coherence basis such as the same object/material, tool/appliance,
  procedure-stage chain, result state, or audio/visual process-result;
- `arbitrary_interval_pairing_forbidden=true`;
- explicit status that human verification of component necessity has not
  occurred.

Pairs separated by at least 120 seconds may be labelled `far_separated`, but
only under that compositional structure. Two distant high-score windows alone
cannot create a far multi-hop candidate.

The allowed provisional relations are:

- setup or preparation, then execution;
- tool or ingredient selection, then transformation;
- visible action, then resulting state;
- audible process, then visible state change;
- earlier action, then later consequence.

Direct inspection must reject a proposed pair if the intervals do not concern
one coherent procedure or if either interval independently answers the
composed question.

## 6. Bounded direct frame/audio authoring assistance

After initial machine-only lead selection, the development and normal builders
can decode only each selected interval from the exact local source MP4.

Frozen bounds:

- maximum frame window: 32 seconds per component;
- maximum audio window: 32 seconds per component;
- maximum sampled frames: 12 per component;
- no persisted frame, contact-sheet, clip, or audio derivative in the
  repository.

The helper records:

- exact sampled timestamps and decode deltas;
- nonsemantic frame luma/edge/change proxies;
- nonsemantic waveform RMS, peak, transient, and zero-crossing metrics;
- whether audio and video streams were available.

It deliberately does **not** use generated captions, OCR, semantic image
labels, AST labels as answers, or automated source-world action names. Its
authoring output is a structured hypothesis scaffold:

- nonempty source-world question hypothesis;
- nonempty source-world answer hypothesis;
- atomic component and composed claim hypotheses;
- exact evidence interval hypotheses;
- an explicit human-listening requirement for any audio-bearing route;
- `human_semantic_validation_status=NOT_PERFORMED`;
- `accepted_family=false`, `accepted_ses=false`,
  `necessity_claimed=false`, and `minimality_claimed=false`.

This is substantive authoring assistance, not human annotation. The resulting
artifact class remains `MACHINE_EXPERT_PROVISIONAL`.

## 7. Recurrence and shortcut flags

Every lead contains:

- a whole-source machine recurrence search and bounded list of suspected
  repetitions;
- a warning that recurrence heuristics are not adjudication;
- person-identity leakage and a required person-blocked split;
- environment/kitchen identity leakage and a required environment-blocked
  split;
- speech/ASR substitution risk;
- caption/OCR/package-label/appliance-display/text substitution risk;
- a semantic-firewall ledger for actions, steps, task graphs, recipes, and
  errors.

Human review must inspect the complete source for exact and near duplicates,
not merely the selected intervals.

## 8. Task153 Gate-A interlock and development mode

### Gate-A candidate mode

`gate_a_candidate_input` fails closed unless all three schema-valid Task153
artifacts are supplied:

- deterministic nonsemantic sample plan;
- completed trained-human form;
- READY import report.

All three sources must pass, have exposure recorded, retain
`necessity_assigned=false`, `h1_assigned=false`, and `h2_assigned=false`, and
bind exactly by plan/form/source/source-group identifiers and hashes.

Dynamic visual authoring requires at least one positive human source-level
dynamic event. Non-speech authoring requires at least one positive human
source-level concrete non-speech event. This permits review of a provisional
candidate; it does not establish sufficiency, minimality, necessity, or an H
tier.

### Development-only mode

Development mode still requires the complete Task189 index but does not
require completed Task153 forms. It may produce bounded direct-inspection
hypotheses. Its registry is structurally marked:

```text
mode = development_only
eligible_to_enter_gate_a = false
development_only_outputs_permanently_ineligible = true
artifact_classification = MACHINE_EXPERT_PROVISIONAL
```

Development output may not be renamed, copied, or promoted into Gate A. A
normal registry must be regenerated after the Task153 gate passes.

## 9. Task145 templates remain inert

Each lead carries a planning-only Task145 v2 template:

- states exactly `CLEAN`, `BLOCKED`, `RESTORED`, and `NO_TRIGGER`;
- fixed zero-based action index 4;
- one blocked prefix replayed into fresh R/N continuations;
- byte-identical public R/N checkpoint semantics;
- primary `RESTORED_minus_NO_TRIGGER` ITT contrast;
- mechanism-specific analysis only;
- `RESTORED_minus_BLOCKED` secondary;
- `get_channel_status` secondary/action-contingent only.

No mechanism is assigned and no intervention is active, executed, or
authorized.

## 10. Commands

Show the committed Task190 plan without reading Task189:

```bash
PYTHONPATH=src python scripts/build_captaincook4d_family_candidates.py \
  --show-plan
```

After Task189 READY, preflight availability without creating candidates:

```bash
PYTHONPATH=src python scripts/build_captaincook4d_family_candidates.py
```

After Task189 READY, emit development-only output with bounded direct
inspection:

```bash
PYTHONPATH=src python scripts/build_captaincook4d_family_candidates.py \
  --development-only \
  --output \
  data/restricted/captaincook4d_family_candidates_v1_dev/candidate_registry.json
```

After Task189 READY and completed human Task153 prescreen, emit normal
candidate input:

```bash
PYTHONPATH=src python scripts/build_captaincook4d_family_candidates.py \
  --execute \
  --prescreen-plan <task153-plan.json> \
  --prescreen-form <completed-task153-form.json> \
  --prescreen-report <ready-task153-import.json> \
  --output \
  data/restricted/captaincook4d_family_candidates_v1/candidate_registry.json
```

Verify an emitted registry without rerunning mining:

```bash
PYTHONPATH=src python scripts/verify_captaincook4d_family_candidates.py \
  --registry \
  data/restricted/captaincook4d_family_candidates_v1_dev/candidate_registry.json
```

## 11. Implementation-only validation

Task190 used synthetic in-memory observation fixtures only. The safe test suite
checks:

- exact six-lead accounting;
- one-hop/near enforcement;
- coherent multi-hop structure;
- annotation-firewall provenance;
- Task189 token-first failure before index reads;
- Gate-A failure without Task153;
- development permanent ineligibility;
- nonempty provisional Q/A/claim/evidence scaffolds;
- bounded direct-inspection contracts;
- recurrence, person/environment, speech, and OCR/text risk flags;
- inert Task145 templates;
- H-tier and affirmative human-status rejection;
- mode-specific restricted output roots.

No CaptainCook4D candidate registry was generated by Task190.
