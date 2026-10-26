# EPIC machine-provisional substantive authoring audit

**Task:** 167  
**Date:** 2026-10-02  
**Decision:** `EPIC_SUBSTANTIVE_DEV_READY`  
**Registry:** `data/restricted/epic_family_candidates_v2_dev/candidate_registry.json`  
**Artifact class:** `MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY`

## 1. Decision

`EPIC_SUBSTANTIVE_DEV_READY`

The four Task 166 interval leads now have nonempty source-world questions,
answers, atomic claims, exact evidence intervals, provisional sufficient
evidence set (SES) hypotheses, and alternative-route ledgers. Two are retained
as development proposals and two are explicitly rejected after substantive
inspection.

A complete search of both local indexed timelines also produced three
additional proposals:

1. removing a small item from a freezer and opening its wrapper;
2. peeling a potato with a handheld peeler; and
3. adding vegetables to a saucepan, adjusting a burner control, and resuming
   stirring.

All three are retained for development review. The first and third are
near-local compositional proposals with nonoverlapping component intervals.
The cooking sequence also has a strong, temporally aligned
frying/sizzle/stir machine-audio hypothesis. No substantive speech proposal
was promoted: the only canonical Whisper chunk passing its quality gate, and
the only such output reproduced by a bounded rerun, was the short
acknowledgment `Mm-hmm.` in `P28_103` at 630–660 seconds.

This decision means the requested development authoring artifact is complete.
It does **not** mean that any candidate is human accepted, minimal, necessary,
H1, H2, Gate-A eligible, or scientifically executable.

## 2. Inputs read and semantic firewall

The work used:

- Tasks 153, 159, and 164–166;
- the Task 166 registry;
- the complete canonical EPIC Wave-1 index;
- local raw source media for `P27_101` and `P28_103`;
- canonical local Whisper, AST AudioSet, CLIP, and OpenCV observations;
- local CLIP text-query retrieval over all searchable visual windows;
- bounded PyAV frame decoding;
- bounded PyAV audio decoding, waveform/spectral measurements, and frozen
  local Whisper reruns.

The work did **not** open or use:

- EPIC action segment annotations or verb/noun labels;
- EPIC narration text or narration timestamps;
- EPIC-SOUNDS annotations, labels, or timestamps;
- benchmark semantic labels, prior QA outcomes, or an annotation vault.

Temporary contact sheets were written only under `/tmp/task167`. No frame,
audio, or clip derivative was persisted in the repository.

### Important audio boundary

Audio was directly decoded from bounded intervals and examined through the
existing AST observations, local Whisper reruns, and waveform/spectral
measurements. No human listening session was performed. Therefore every
semantic non-speech interpretation remains a machine-expert hypothesis and is
explicitly marked as requiring human listening.

## 3. Complete-timeline search

The canonical index covers both complete recordings:

| Source | Duration |
|---|---:|
| `P27_101` | 1360.20 s |
| `P28_103` | 1825.16 s |

The search covered:

| Observation inventory | Count |
|---|---:|
| Fine AST calls/windows | 796 |
| CLIP cells | 798 |
| OpenCV routing cells | 798 |
| Whisper chunks | 107 |

Fifteen local CLIP text queries were evaluated against every searchable fine
visual window in both sources. They covered cutting, chopping, peeling/opening
packaging, stirring, frying, pouring, cracking, sink washing, scrubbing,
cupboard/drawer operation, plating, appliance use, visible state change, and
cookware handling.

The full AST timeline was also ranked by concrete non-generic event classes.
High-value regions selected for bounded inspection included:

- `P27_101` 1084–1100: `Rub`/`Sanding`/`Wood`;
- `P27_101` 1188–1196: `Coin (dropping)`;
- `P27_101` 1288–1304: `Crumpling, crinkling`;
- `P28_103` 196–212: `Scissors`;
- `P28_103` 940–960: `Frying (food)`/`Sizzle`/`Stir`;
- `P28_103` 1112–1124: `Chopping (food)`;
- `P28_103` 1428–1444: `Rain`/`Raindrop`/`Rain on surface`.

Bounded frame review showed two important machine-label corrections:

- the `P28_103` 196–212 `Scissors` route is visually a potato being peeled
  with a handheld peeler;
- the `P28_103` 1428–1444 rain route remains indoors over a saucepan and is
  treated as cooking-noise confusion, not rain.

The latter was not promoted.

## 4. Direct media audit

The direct audit decoded:

| Audit operation | Exact count |
|---|---:|
| Broad bounded frame inspections | 17 |
| Detail bounded frame inspections | 7 |
| Sampled frame observations inspected | 419 |
| Bounded audio decodes | 24 |
| Frozen local Whisper reruns | 10 |
| Bounded waveform/spectral metric intervals | 14 |
| Repository-persisted media derivatives | 0 |

### 4.1 Task 166 intervals

| Source / interval | Direct bounded frame observation | Audio/index observation | Disposition |
|---|---|---|---|
| `P27_101` 1204–1212 | At 1205.5–1209 the wearer opens the lower cupboard beside the sink; at 1210–1212 a pink-and-blue spray bottle is carried back toward the hob. | AST peaks include `Door` 0.44723, `Slam` 0.32633, `Sliding door` 0.23615, and `Cupboard open or close` 0.12532. Bounded audio has strong transients, but no human listening validation. | `KEEP` |
| `P27_101` 1260–1268 | The wearer opens the same lower-cupboard area and removes a green-and-pink long-handled cleaning item before walking away. | AST again favors door/cupboard/slam classes. The event is in the same cleaning cluster as the retained P27 lead. | `REJECT` |
| `P28_103` 32–40 | The wearer finishes at the sink, moves away, and at 36.5–39.5 wipes/dries both hands with a white towel. | Water/faucet/sink AST evidence belongs mostly to the preceding sink action and does not identify the towel. | `KEEP` |
| `P28_103` 496–504 | The wearer approaches the sink, performs a rinsing motion, and then lifts a yellow food packet. | AST strongly repeats the source's water/faucet/sink cluster. Package appearance and possible text create an additional shortcut. | `REJECT` |

### 4.2 Additional promoted intervals

| Source / interval | Direct bounded frame observation | Audio/index observation | Disposition |
|---|---|---|---|
| `P27_101` 1284–1301 | At 1284–1290 the wearer removes a small wrapped item from the freezer; at 1292–1299.5 the wrapper is peeled/opened before the wearer walks away. | AST `Crumpling, crinkling` peaks at 0.40372 in 1292–1300. This is plausible corroboration only until a human listens. | `KEEP` |
| `P28_103` 196–212 | Repeated strokes of a handheld peeler remove skin from a potato while other vegetables remain on a blue board. | AST `Scissors` peaks at 0.84856, but bounded frames contradict the class. The AST route is explicitly rejected as semantic support. | `KEEP` |
| `P28_103` 938–960 | At 938–944.5 chopped vegetables are tipped into a saucepan; at 949.5–954.5 a burner control is adjusted; at 955–959.5 stirring resumes. | Across overlapping windows, AST peaks are `Frying (food)` 0.89492, `Sizzle` 0.78190, and `Stir` 0.92433. The sound route plausibly establishes active cooking but cannot identify the knob without vision. | `KEEP` |

### 4.3 Speech search

All 107 canonical Whisper chunks were inspected as a complete timeline. The
canonical quality gates yielded:

- `P27_101`: 0 passing chunks;
- `P28_103`: 1 passing chunk, 630–660 seconds, `Mm-hmm.`.

Ten bounded frozen-Whisper reruns targeted the strongest speech-like AST
regions and the canonical passing region. Only the 630–660 second rerun passed
the same lexical/log-probability gate, again producing `Mm-hmm.`. This is
genuine speech-like content but not sufficiently substantive for a coherent
source-world QA. It is recorded as a searched and unpromoted route rather than
inflated into a speech candidate.

## 5. Authored candidate audit

### 5.1 `EPIC-DEV-P27-CLEANER-FROM-CUPBOARD`

- **Question:** After opening the lower cupboard beside the sink, what item
  does the wearer bring back toward the stove?
- **Answer:** A pink-and-blue spray bottle of cleaner.
- **Evidence:** visual 1205.5–1212.0.
- **Provisional SES:** the bounded visual sequence alone.
- **Open alternatives:** later cleaning/cupboard recurrence, distinctive
  product appearance, single-frame answerability, and product-label/OCR risk.
- **Human work:** confirm object identity, inspect the full cleaning sequence,
  search all cupboard/product repeats, and test whether a single frame answers.
- **Disposition:** `KEEP`.

### 5.2 `EPIC-DEV-P27-LONG-HANDLED-CLEANING-TOOL`

- **Question:** What long-handled item does the wearer remove from the lower
  cupboard before leaving the sink area?
- **Answer:** A green-and-pink long-handled cleaning tool.
- **Evidence:** visual 1261.0–1267.0.
- **Provisional SES:** the bounded visual sequence.
- **Open alternatives:** the retained P27 cleaning lead, broader same-task
  context, and single-frame color/shape recognition.
- **Human work if reconsidered:** identify the tool precisely and prove that
  the proposal adds a distinct family rather than another cleaning variant.
- **Disposition:** `REJECT`.

### 5.3 `EPIC-DEV-P28-DRY-HANDS-WITH-TOWEL`

- **Question:** After moving away from the sink, what does the wearer use on
  both hands?
- **Answer:** A white towel.
- **Evidence:** visual 36.5–39.5.
- **Provisional SES:** the narrowed towel-use interval.
- **Open alternatives:** a still-frame route and other possible hand-drying
  events in the source.
- **Human work:** verify the action as drying rather than generic wiping and
  perform full-source recurrence closure.
- **Disposition:** `KEEP`.

### 5.4 `EPIC-DEV-P28-YELLOW-PACKET-AFTER-RINSE`

- **Question:** Immediately after the rinsing motion at the sink, what does the
  wearer lift from the counter?
- **Answer:** A yellow food packet.
- **Evidence:** visual 496.5–504.0.
- **Provisional SES:** the bounded visual sequence.
- **Open alternatives:** recurrent sink/water actions and package/OCR identity.
- **Human work if reconsidered:** identify the packet, mask or close readable
  text, and justify retaining another sink-cluster item.
- **Disposition:** `REJECT`.

### 5.5 `EPIC-DEV-P27-UNWRAP-FROZEN-ITEM`

- **Question:** Where does the wearer get the small item, and what do they do
  to it before walking back toward the sink?
- **Answer:** They take it from the freezer and peel off or open its wrapper.
- **Evidence components:** visual 1284.0–1290.0; visual
  1292.0–1299.5; machine-audio hypothesis 1292.0–1300.0.
- **Composition:** freezer retrieval, then wrapper opening, with nonoverlapping
  components.
- **Provisional SES hypotheses:** both visual components; or freezer retrieval
  plus a future human-confirmed wrapper sound.
- **Open alternatives:** visual-only wrapper opening, audio-only crinkling,
  wrapper text/appearance, and other package-opening events.
- **Human work:** verify that both question parts are jointly required, listen
  to the wrapper sound, close package/OCR leakage, and search all packaging
  events.
- **Disposition:** `KEEP`.

### 5.6 `EPIC-DEV-P28-PEEL-POTATO`

- **Question:** What preparation does the wearer apply to the potato while the
  other vegetables remain on the blue board?
- **Answer:** Peels it with a handheld peeler.
- **Evidence:** visual 196.0–211.5.
- **Provisional SES:** the bounded visual action.
- **Open alternatives:** a single-frame peeler-contact shortcut and repeated
  vegetable preparation elsewhere.
- **Machine correction:** the strong AST `Scissors` label is rejected as a
  false semantic route.
- **Human work:** verify vegetable and tool identity, tighten the minimal
  interval, and search other peeling/cutting sequences.
- **Disposition:** `KEEP`.

### 5.7 `EPIC-DEV-P28-ADD-ADJUST-STIR`

- **Question:** What sequence links the bowl of chopped vegetables to the next
  round of stirring?
- **Answer:** The wearer tips the vegetables into the saucepan, adjusts a stove
  burner control knob, and then resumes stirring.
- **Evidence components:** visual 938.0–944.5, visual 949.5–954.5, visual
  955.0–959.5; machine-audio hypothesis 940.0–960.0.
- **Composition:** add vegetables, adjust burner control, resume stirring.
- **Provisional SES:** all three visual components jointly.
- **Open alternatives:** middle-component-only shortcut, question wording that
  leaks order, repeated frying/stirring elsewhere, and non-speech cooking audio
  that establishes cooking but not the adjusted control.
- **Human work:** verify all three temporal claims, listen to the cooking
  interval, test each component's removal, and search repeated cooking
  sequences near 1080–1104, 1296–1336, and 1472–1500 seconds.
- **Disposition:** `KEEP`.

## 6. Exact accounting

| Measure | Count |
|---|---:|
| Total authored proposals | 7 |
| Task 166 leads authored | 4 |
| Additional full-timeline leads | 3 |
| `KEEP` | 5 |
| `REPAIR` | 0 |
| `REJECT` | 2 |
| Nonempty questions | 7 |
| Nonempty answers | 7 |
| Atomic claims | 11 |
| Evidence units | 13 |
| Provisional, unaccepted SES hypotheses | 8 |
| Alternative-route entries | 18 |
| Multi-hop proposals | 2 |
| Promoted substantive speech proposals | 0 |
| H1 | 0 |
| H2 | 0 |
| Necessity claims | 0 |
| Minimality claims | 0 |
| Active interventions | 0 |

The exact dispositions are development authoring decisions, not human
acceptance outcomes.

## 7. Human semantic prescreen and full-source validation requirements

Every proposal, including every `KEEP`, still requires:

1. trained-human Task-153 source-level semantic prescreen;
2. frame-accurate review of each cited interval;
3. human listening for every audio-bearing hypothesis;
4. full-source recurrence and near-duplicate search;
5. OCR, package-label, transcript, ASR, and narration-substitute challenge;
6. participant-lineage and kitchen-identity leakage review;
7. independent SES sufficiency and leave-one-out minimality demonstrations;
8. blind alternative-route search and post-adjudication saturation audit.

The two rejected proposals remain in the registry as explicit development
rejections and may not be counted as retained candidates.

## 8. Validation

The new deterministic builder, verifier, and tests are:

- `scripts/build_epic_substantive_authoring_dev.py`;
- `scripts/verify_epic_substantive_authoring_dev.py`;
- `tests_epic_family_mining/test_substantive_authoring_dev.py`.

Validation results:

```text
python scripts/build_epic_substantive_authoring_dev.py \
  --repo-root . --execute
EPIC_SUBSTANTIVE_DEV_READY

python scripts/verify_epic_substantive_authoring_dev.py --repo-root .
EPIC_SUBSTANTIVE_AUTHORING_DEV_VERIFIED
exact dispositions: KEEP=5 REPAIR=0 REJECT=2

PYTHONPATH=src pytest -o addopts='' -q \
  tests_epic_family_mining/test_substantive_authoring_dev.py
5 passed

PYTHONPATH=src pytest -o addopts='' -q \
  tests_epic_family_mining tests_epic_wave1_index
39 passed

ruff check scripts/build_epic_substantive_authoring_dev.py \
  scripts/verify_epic_substantive_authoring_dev.py \
  tests_epic_family_mining/test_substantive_authoring_dev.py
All checks passed

python -m py_compile scripts/build_epic_substantive_authoring_dev.py \
  scripts/verify_epic_substantive_authoring_dev.py
PASS

PYTHONPATH=src python scripts/verify_epic_wave1_full_timeline.py \
  --repo-root . \
  --output-root data/restricted/epic_wave1_index_v1 \
  --mode full
336 checks; 0 failures
```

Registry properties after deterministic rebuild:

- file mode: `0600`;
- directory mode: `0700`;
- bytes: 62,156;
- file SHA-256:
  `ab0d4e70d912b9fe7bf7f84c48d717ba1809b1ac6ca4ed67464644e5d26bca5d`;
- internal payload SHA-256:
  `sha256:3113e902d75a85ec01ce54ecbd2688887beda059a35b7369721e7debe6a94f94`.

## 9. Boundary

- Every output remains
  `MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY`.
- Development artifacts are permanently future-test-ineligible and Gate-A
  ineligible.
- No human semantic review is claimed.
- No SES is accepted.
- No necessity or minimality is claimed.
- No H1 or H2 is assigned.
- No intervention is active or authorized.
- Full-source validation is not complete.

**Final: `EPIC_SUBSTANTIVE_DEV_READY`.**
