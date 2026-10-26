# EPIC development-only family-candidate execution audit

**Execution/audit date:** 2026-09-28  
**Decision:** `EPIC_DEV_CANDIDATES_REPAIR`  
**Registry:** `data/restricted/epic_family_candidates_v1_dev/candidate_registry.json`  
**Scope:** development-only machine proposals and independent internal audit;
not human semantic prescreen, not Gate A

## 1. Decision

`EPIC_DEV_CANDIDATES_REPAIR`

The real development-only run completed and produced exactly four machine
P-tier proposals, two per EPIC source. The output is structurally barred from
Gate A, contains no H1/H2 assignment, asserts no necessity, and authorizes no
intervention.

The source genre is **materially more promising than the lecture sources** for
event-centric dynamic vision and environmental audio: the inspected intervals
contain real egocentric manipulation, sink/cupboard activity, visible object
and scene changes, and machine ambient hypotheses that are at least physically
plausible. This directly improves on lecture candidates dominated by speech,
boards, equations, slides, and incidental classroom noise.

The emitted proposal set is nevertheless not ready. All eight route
blueprints intentionally have null question and answer placeholders because no
trained-human semantic prescreen exists. Two of the four selected leads are
redundant with another lead from the same source, all four have substantial
recurrence risk, there is no speech-bearing candidate, and the final output
contains no defensible compositional multi-hop lead. The machine P2 tier is not
a human quality or necessity judgment.

## 2. Inputs and semantic firewall

The execution used:

- Task 164's complete canonical index at
  `data/restricted/epic_wave1_index_v1/`;
- Task 165's EPIC-specific mining and authoring implementation;
- OpenCV routing/change observations and frozen CLIP embeddings;
- frozen Whisper ASR observations;
- frozen AST AudioSet observations; and
- direct internal frame-sequence inspection of the selected source intervals
  for this audit.

The run did **not** use EPIC action annotations, EPIC narrations or narration
times, EPIC-SOUNDS annotations, official semantic sound labels, benchmark
split labels, prior QA outcomes, or any existing annotation vault. Temporary
frame montages used for internal inspection were written only under `/tmp`;
no media derivative was persisted in the repository.

This internal review is not the trained-human Task-153 semantic prescreen.
`human_prescreen_complete` remains false.

## 3. Validation and narrow repairs

### 3.1 Final validation

```text
PYTHONPATH=src pytest -o addopts='' -q \
  tests_epic_family_mining tests_epic_wave1_index
34 passed

ruff check src/av_trace_epic_family_mining \
  scripts/build_epic_family_candidates.py \
  scripts/verify_epic_family_candidates.py \
  tests_epic_family_mining
All checks passed

python -m py_compile src/av_trace_epic_family_mining/*.py \
  scripts/build_epic_family_candidates.py \
  scripts/verify_epic_family_candidates.py
PASS

PYTHONPATH=src python scripts/verify_epic_wave1_full_timeline.py \
  --repo-root . \
  --output-root data/restricted/epic_wave1_index_v1 \
  --mode full
336 checks; 0 failures

PYTHONPATH=src python scripts/build_epic_family_candidates.py --show-plan
Committed-plan drift check and JSON parse: PASS
```

### 3.2 Narrow owned repairs

Two issues were repaired before the final run:

1. **Development output-root separation.** Task 165 admitted only
   `data/restricted/epic_family_candidates_v1/`, while this execution required
   `data/restricted/epic_family_candidates_v1_dev/`. The CLI and verifier now
   bind `development_only` registries to the development root and reject
   normal/development root-mode mismatches. The registry validator also
   requires the permanent Gate-A ineligibility marker and per-lead development
   blocker.
2. **False machine multi-hop construction.** The initial real run paired
   adjacent dynamic windows merely because the first also had an AST
   hypothesis, yielding two nominal
   `audible_event_then_visible_state_change` proposals without a distinct
   audible premise. Pair compatibility was narrowed to require at least four
   seconds of non-overlap and a directional observation pattern. The final
   registry correctly falls back to one-hop/local for all four leads.

No model, canonical index, source media, semantic threshold, H-tier rule, or
intervention behavior was changed.

## 4. Execution

Final command:

```text
PYTHONPATH=src python scripts/build_epic_family_candidates.py \
  --repo-root . \
  --development-only \
  --output \
  data/restricted/epic_family_candidates_v1_dev/candidate_registry.json
```

Result:

- status: `EPIC_MACHINE_P_TIER_PROPOSALS_WRITTEN`;
- mode: `development_only`;
- sources: 2;
- proposals: 4;
- exactly two proposals per source: yes;
- Gate-A eligible: no;
- H-tier count: 0;
- active interventions: 0.

The independent verifier passed with no failures. A second identical
development-only run was byte-identical.

Output properties:

- registry bytes: 58,629;
- file mode: `0600`;
- containing directory mode: `0700`;
- file SHA-256:
  `7009f862c0797dec565a625a5de56c88c17da977b4092cb55a6b492c42efcd3c`;
- registry self-hash:
  `sha256:f09192bca47792b7f2f4745552940581349a002bb969f920e01ad00928df249a`.

## 5. Exact counts

| Measure | Count |
|---|---:|
| Sources | 2 |
| Proposals | 4 |
| `P0_MACHINE_CANDIDATE` | 0 |
| `P1_MACHINE_CROSS_VALIDATED` | 0 |
| `P2_MACHINE_COUNTERFACTUAL_VALIDATED` | 4 |
| H1 | 0 |
| H2 | 0 |
| One-hop | 4 |
| Multi-hop | 0 |
| Near/local | 4 |
| Far/separated | 0 |
| Dynamic non-text visual machine hypotheses | 4 |
| Non-speech AST machine hypotheses | 4 |
| Speech machine hypotheses | 0 |
| Primary static/OCR/overlay classifications | 0 |
| Question blueprints | 8 |
| Non-null question placeholders | 0 |
| Non-null answer placeholders | 0 |
| Proposals flagged for recurrence | 4 |
| Listed possible-recurrence entries | 39 |
| Leads eligible for Gate-A input review | 0 |
| Leads for which human authoring may begin | 0 |
| Active interventions | 0 |

Independent audit dispositions:

| Disposition | Count |
|---|---:|
| `REPAIR` | 2 |
| `REJECT_REPLACE` | 2 |
| `READY` / retain unchanged | 0 |

## 6. Candidate-by-candidate audit

### 6.1 `P27_101` lead 1 — `epic.lead.4c60d048f41a9e26`

- **Interval:** 1204.0–1212.0 seconds.
- **Machine tier:** `P2_MACHINE_COUNTERFACTUAL_VALIDATED`.
- **Final structure:** one-hop, near/local.
- **Machine scores:** dynamic visual 0.84343007; non-speech 1.0; speech 0.
- **Ambient observations:** `Door`, `Slam`, `Sliding door`,
  `Cupboard open or close`, plus a low-weight `Vehicle` false-positive route.
- **Recurrence list:** 3 entries.
- **Audit disposition:** `REPAIR`.

Direct frame inspection shows genuine egocentric physical activity around the
stove, sink, and lower cupboard, including opening/reaching and handling a
cleaning item. This is substantially more plausible dynamic non-text visual
material than a lecture board or slide. A cupboard/door sound is also
physically plausible.

The record still has no actual question. The AST list is broad and includes a
clearly irrelevant low-weight class, audio has not received human listening
confirmation, and nearby same-kitchen actions may answer many possible
questions through vision alone. A human author must select one precise event,
listen to the interval, and challenge product-label, kitchen-layout, and
repeat-event shortcuts.

### 6.2 `P27_101` lead 2 — `epic.lead.b8cb83fc059ba74e`

- **Interval:** 1260.0–1268.0 seconds.
- **Machine tier:** `P2_MACHINE_COUNTERFACTUAL_VALIDATED`.
- **Final structure:** one-hop, near/local.
- **Machine scores:** dynamic visual 0.81311441; non-speech 0.9589282;
  speech 0.
- **Ambient observations:** `Door`, `Cupboard open or close`, `Slam`,
  `Drawer open or close`, `Sliding door`.
- **Recurrence list:** 12 entries.
- **Audit disposition:** `REJECT_REPLACE`.

The interval contains plausible manipulation near the sink/lower cupboard, so
it is not a blank or static-text failure. It is, however, part of the same
cupboard/sink cleaning cluster as lead 1 only 56 seconds later. The machine
recurrence list is saturated and also includes unrelated same-AST hits,
showing that the current recurrence heuristic is low precision.

With no authored question or distinct event relation, this lead does not add a
second defensible family for `P27_101`. Replace it with a semantically distinct
event after human prescreen rather than spending review budget on a likely
duplicate.

### 6.3 `P28_103` lead 1 — `epic.lead.d8480ee4d0ed5d4d`

- **Interval:** 32.0–40.0 seconds.
- **Machine tier:** `P2_MACHINE_COUNTERFACTUAL_VALIDATED`.
- **Final structure:** one-hop, near/local.
- **Machine scores:** dynamic visual 0.86073757; non-speech 1.0; speech 0.
- **Ambient observations:** `Water`, `Water tap, faucet`,
  `Sink (filling or washing)`, `Toilet flush`, `Dishes, pots, and pans`.
- **Recurrence list:** 12 entries.
- **Audit disposition:** `REPAIR`.

This is the strongest emitted lead. Direct frames show real sink-side object
handling/rinsing and subsequent movement away from the sink. Water/faucet/sink
audio hypotheses are physically plausible, unlike the incidental
speech/writing ambient routes found in lecture footage.

It still lacks a question, and the visible sink/faucet action may reveal any
sound answer without audio. `Toilet flush` is an implausible competing AST
class. The source contains many other water/sink events, so recurrence and
visual-to-audio substitution must be closed before any modality-necessity
claim.

### 6.4 `P28_103` lead 2 — `epic.lead.8f2a283d462000e4`

- **Interval:** 496.0–504.0 seconds.
- **Machine tier:** `P2_MACHINE_COUNTERFACTUAL_VALIDATED`.
- **Final structure:** one-hop, near/local.
- **Machine scores:** dynamic visual 0.82954104; non-speech 1.0; speech 0.
- **Ambient observations:** `Water tap, faucet`,
  `Sink (filling or washing)`, `Water`, `Bathtub (filling or washing)`,
  `Fill (with liquid)`.
- **Recurrence list:** 12 entries.
- **Audit disposition:** `REJECT_REPLACE`.

The interval is dynamically plausible and the water-related machine audio
route broadly agrees with the visible sink activity. It is nevertheless a
second sink/water proposal from the same source and is explicitly linked by
the recurrence list to lead 1 and many other water events. It therefore adds
little source-level diversity and has high vision-to-audio shortcut risk.

The canonical index contains other high-scoring event types, including
frying/sizzle and object-handling regions. Human prescreen should replace this
lead with a distinct event rather than retain two recurrent sink families.

## 7. Cross-proposal findings

### Question-placeholder quality

The development interlock behaves correctly: dynamic and ambient authoring is
blocked without human prescreen. Consequently, all eight question/answer
placeholders are null. This is safe but means the registry contains interval
leads, not usable questions. No proposal can be assessed for answer
specificity, ambiguity, or minimal sufficient evidence until a human author
drafts a concrete question.

### Dynamic non-text visual plausibility

All four intervals show real physical activity rather than boards, slides,
title cards, or talking heads. Two are reasonably strong repair candidates.
The weakness is selection diversity, not absence of motion.

### Speech and ambient specificity

No selected interval has a speech hypothesis. Ambient hypotheses are more
plausible than the lecture-source ambient routes, but remain machine routing
labels. `P28_103` water/sink classes align better with visible context than
`P27_101`'s broad door/slam group. In every case, the visual scene may itself
predict the ambient class, so no audio necessity is established.

### Compositional multi-hop

The first execution exposed two false nominal multi-hop pairs built from
adjacent dynamic windows. The narrow repair removed them. The final count is
zero multi-hop proposals. This is scientifically preferable to keeping
arbitrary interval pairs, but it also means the run provides no compositional
multi-hop candidate.

### Recurrence and duplicates

Every proposal is recurrence-flagged; the registry lists 39 possible
repetitions. The two selected proposals within each source are semantically
close:

- `P27_101`: lower-cupboard/sink cleaning activity;
- `P28_103`: sink/water activity.

The recurrence heuristic also groups visibly unrelated events when AST labels
match, so its entries are challenge routes rather than duplicate judgments.

### Shortcut risk

Major open routes are:

- visible faucet/sink/cupboard geometry predicting ambient labels;
- persistent kitchen identity and participant lineage;
- product/package/bin labels and other OCR-able text;
- repeated performance of the same household action;
- question wording that names the event or modality;
- treating AST class names as answers; and
- treating the machine P2 tier as semantic counterfactual validation.

No necessity, minimality, or accepted-family claim is justified.

## 8. Comparison with lecture sources

**Yes: these EPIC sources look materially more promising than lecture sources
for the intended event-centric A/V program.**

The advantage is substantive: the raw footage contains changing physical
states, manipulation, recurring environmental sounds, and many possible
event boundaries. Lecture sources mainly supported speech, transcript/OCR,
board/static-diagram, and duplicate-route calibration.

The advantage is not yet realized by the four-proposal output. The current
miner over-concentrates on sink/cupboard events, emits no speech route, emits
no final multi-hop route, and cannot author questions before human prescreen.
The appropriate next step is a trained-human semantic prescreen followed by
regeneration in normal mode—not promotion or reuse of this development
registry.

## 9. Boundary

- Development-only and permanently ineligible for Gate A.
- Do not rename or copy this registry into the normal candidate-input root.
- Human semantic prescreen complete: no.
- H1/H2: 0/0.
- Human minimality or necessity: not asserted.
- Gate A decision: not asserted.
- Active interventions: 0.
- Scientific execution authorization: none.

**Final: `EPIC_DEV_CANDIDATES_REPAIR`.**
