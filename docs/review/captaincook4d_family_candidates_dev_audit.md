# CaptainCook4D development-only family-candidate audit

**Task:** 191  
**Date:** 2026-10-10  
**Decision:** `CAPTAINCOOK4D_DEV_CANDIDATES_REPAIR`  
**Artifact class:** `MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY`

## 1. Scope and decision

Task191 executed the Task190 miner against the complete Task189 canonical
index and wrote:

`data/restricted/captaincook4d_family_candidates_v1_dev/candidate_registry.json`

The registry has exactly three sources and exactly two proposals per source,
for six proposals total. Bounded direct local frame and audio decoding was
performed only for selected components. Generic machine scaffolds were
replaced with substantive source-world question and answer hypotheses, atomic
claims, exact evidence intervals, provisional sufficient-evidence-set (SES)
hypotheses, and candidate-by-candidate independent audit records.

The final decision is **REPAIR**, not READY:

- three proposals are retained provisionally;
- two require repair before any later normal-mode regeneration;
- one machine-proposed far pair is rejected as an arbitrary composition;
- recurrence remains open for every source;
- audio identities remain machine hypotheses because trained-human semantic
  listening validation was not performed;
- no proposal, family, SES, modality necessity claim, H tier, or intervention
  is accepted.

## 2. Inputs and semantic firewall

Authoritative execution inputs were:

- Task188:
  `CAPTAINCOOK4D_WAVE0_ACQUISITION_READY`;
- Task189:
  `CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY`;
- Task190:
  `CAPTAINCOOK4D_FAMILY_MINING_IMPLEMENTATION_READY`;
- the canonical full index at
  `data/restricted/captaincook4d_wave0_index_v1/`;
- exact local MP4s for `15_29`, `16_20`, and `26_22`.

The run used canonical OpenCV routing/change observations, frozen CLIP
embeddings, frozen Whisper routing records, frozen AST AudioSet records, and
bounded direct decoding of selected raw-local frames and audio waveforms.

The run did **not** use:

- CaptainCook4D action or step annotations;
- task or procedure graphs;
- recipe labels;
- error or mistake labels;
- benchmark labels, prior QA, or label-derived features;
- Task153 human semantic forms during mining;
- repository-persisted frame, contact-sheet, audio, or clip derivatives.

Temporary internal review derivatives existed only under `/tmp` and are not
part of the repository output. No human semantic validation is claimed.

## 3. Validation and narrow repair

Before mining:

```text
PYTHONPATH=src pytest -o addopts='' -q \
  tests_captaincook4d_family_mining \
  tests_captaincook4d_wave0_index
26 passed

ruff check src/av_trace_captaincook4d_family_mining \
  scripts/build_captaincook4d_family_candidates.py \
  scripts/verify_captaincook4d_family_candidates.py \
  tests_captaincook4d_family_mining
All checks passed

python -m py_compile \
  src/av_trace_captaincook4d_family_mining/*.py \
  scripts/build_captaincook4d_family_candidates.py \
  scripts/verify_captaincook4d_family_candidates.py
PASS

PYTHONPATH=src python \
  scripts/verify_captaincook4d_wave0_full_timeline.py \
  --repo-root . \
  --output-root data/restricted/captaincook4d_wave0_index_v1 \
  --mode full
410 checks; 0 failures
```

Preflight exposed one Task190-owned defect: its default Task189 gate referenced
the nonexistent
`orchestration/results/189_captaincook4d_wave0_full_timeline_build.txt`
rather than the published
`orchestration/results/189_captaincook4d_wave0_full_timeline.txt`.

The path was narrowly repaired in the Task190 adapter, CLI, fixture plan,
focused test, and related Task190 documents. No Task188/189 code, canonical
index, source media, mining threshold, model, H-tier rule, or intervention
logic was changed. After repair, preflight reported Task189 ready and the
canonical index complete.

## 4. Execution and output properties

Execution command:

```text
PYTHONPATH=src python \
  scripts/build_captaincook4d_family_candidates.py \
  --repo-root . \
  --development-only \
  --output \
  data/restricted/captaincook4d_family_candidates_v1_dev/candidate_registry.json
```

Final registry properties:

- sources: 3;
- proposals: 6;
- exactly two per source: yes;
- substantive Q/A records: 6;
- atomic claim sets: 6;
- provisional SES hypotheses: 6;
- accepted SES: 0;
- file bytes: 161,617;
- file mode: `0600`;
- directory mode: `0700`;
- file SHA-256:
  `23ee9356b530fe9d7bace1948f55818a590736b6c264438bf9f13abcbfac62fa`;
- registry self-hash:
  `sha256:c7f9dbe160ce1e260051059bfc48f4183dab39e84960bb83ea07fc28f8c205c3`;
- independent structural verifier: PASS with zero failures.

## 5. Exact final counts

| Measure | Count |
|---|---:|
| Sources | 3 |
| Proposals | 6 |
| Proposals per source | exactly 2 |
| `P2_MACHINE_COUNTERFACTUAL_VALIDATED` labels | 6 |
| H1 / H2 | 0 / 0 |
| One-hop / near-local | 4 |
| Multi-hop / far-separated | 2 |
| Substantive non-null questions | 6 |
| Substantive non-null answers | 6 |
| Atomic claim sets | 6 |
| Provisional SES hypotheses | 6 |
| Accepted SES | 0 |
| Proposals with non-speech hypotheses | 6 |
| Proposals with speech hypotheses | 0 |
| Audit `KEEP` | 3 |
| Audit `REPAIR` | 2 |
| Audit `REJECT` | 1 |
| Gate-A eligible | 0 |
| Future-test eligible | 0 |
| Active interventions | 0 |

The machine P2 labels are inherited routing tiers. They do not mean human
validation, semantic counterfactual proof, acceptance, minimality, necessity,
or gold status.

## 6. Candidate-by-candidate independent audit

### 6.1 `15_29` lead 1 — `cc4d.lead.9f54485d9d61833c`

- **Interval:** 632.0–640.0 seconds.
- **Structure:** one-hop, near/local.
- **Question:** What prepared ingredient is on the cutting board as it is
  carried away from the stovetop?
- **Answer hypothesis:** A pile of diced tomatoes.
- **Audit disposition:** `KEEP`.

Direct frames show diced red tomatoes on a white cutting board beside the
stovetop, followed by movement toward the sink-side counter. This is a
specific dynamic ingredient-handling event rather than a generic “cooking”
label.

The provisional SES is visual: frames showing the diced tomatoes plus the
board movement. AST routes include stir, sizzle, and frying, but audio was not
semantically validated and is not claimed necessary.

Five machine recurrence candidates remain, including other pan/stir windows.
The event is retained because the loaded cutting board makes it locally
specific. No speech hypothesis exists. Laptop or package text is unnecessary
to identify the tomatoes, though kitchen-layout and repeated-event shortcuts
remain open.

### 6.2 `15_29` lead 2 — `cc4d.lead.96416b3c53aeb206`

- **Intervals:** 36.0–44.0 and 632.0–640.0 seconds.
- **Structure:** multi-hop, far-separated.
- **Question:** How do the tomatoes differ between the early sink/stove
  interval and the later cutting-board interval?
- **Answer hypothesis:** Whole tomatoes are handled early; diced tomatoes
  appear later.
- **Audit disposition:** `REPAIR`.

Direct early frames show whole tomatoes at the sink, then carried to and set
beside the stove. Later frames show diced tomatoes on a cutting board. The
generic machine pair was therefore repaired into a same-ingredient
whole-to-diced state-change hypothesis.

The composition is coherent enough for development review but not accepted:
the exact physical identity of the tomatoes across ten minutes is not proven,
and the late component duplicates lead 1. Water and pan-process audio routes
are plausible only as machine hypotheses.

Recurrence is extensive for sink/water and pan events. No speech route is
present. A visible laptop could provide instructions through OCR, but the
authored question is intentionally grounded only in the observed ingredient
states.

### 6.3 `16_20` lead 1 — `cc4d.lead.56a0afee3a48bd76`

- **Interval:** 1096.0–1104.0 seconds.
- **Structure:** one-hop, near/local.
- **Question:** What ingredient is being stirred in the small pan before the
  utensil is handled with a paper towel?
- **Answer hypothesis:** Chopped red onion.
- **Audit disposition:** `KEEP`.

Frames show chopped red onion in a small pan, active stirring with a dark
utensil, and immediate utensil handling near a paper towel. The proposal has a
clear object, action, and short temporal progression.

The provisional SES is visual. Cookware and cutlery audio routes may be
plausible, while AST alternatives such as hammer and wood are rejected as
routing noise. Sixteen recurrence entries require source-level closure, but
the visible onion-and-stir action is sufficiently specific for provisional
retention.

No speech hypothesis exists, and stove-display or other OCR routes are not
needed to answer.

### 6.4 `16_20` lead 2 — `cc4d.lead.ce01b450ca70e10a`

- **Intervals:** 224.0–232.0 and 1096.0–1104.0 seconds.
- **Structure:** multi-hop, far-separated.
- **Question:** Which two ingredient-handling actions occur in the early and
  later intervals?
- **Answer hypothesis:** A pink strip or pieces of food are pulled apart
  early; chopped red onion is stirred later.
- **Audit disposition:** `REJECT`.

Both intervals contain real dynamic actions. The early interval appears to
show a pink food strip or pieces being separated by hand; the later interval
is the onion-stirring event already used by lead 1.

Direct inspection does not establish a shared object, dish, result, or causal
procedure chain. Each interval independently answers its own one-hop action
question. The pair therefore fails the intended coherent multi-hop standard
and looks like two high-scoring windows joined by chronology alone.

The early object identity is also uncertain and could be food or packaging.
Crinkling/tearing and cookware/cutlery audio routes remain unvalidated.
Because the late component duplicates lead 1 and recurrence is high, the pair
is rejected rather than repaired into a false composition. It remains in the
development registry only for audit traceability.

### 6.5 `26_22` lead 1 — `cc4d.lead.e77b56c376c244a3`

- **Interval:** 920.0–928.0 seconds.
- **Structure:** one-hop, near/local.
- **Question:** What does the participant do immediately after opening the
  microwave?
- **Answer hypothesis:** They remove a mug and stir its contents.
- **Audit disposition:** `KEEP`.

Frames show the microwave door opening, a mug being removed, and the mug
contents being stirred with a spoon. This is the strongest complete local
action sequence in the final set.

Microwave and beep AST routes are plausible, but no audio identity is
validated or necessary for the visual answer. The contents of the mug are not
named. Sixteen recurrence entries include other appliance-like windows, yet
the complete open-retrieve-stir sequence is locally distinctive.

No speech route exists. Microwave-display and laptop OCR are not needed.

### 6.6 `26_22` lead 2 — `cc4d.lead.96b7ab9298d78633`

- **Interval:** 460.0–468.0 seconds.
- **Structure:** repaired to one-hop, near/local.
- **Question:** What small utensil is rinsed under the faucet and then carried
  away from the sink?
- **Answer hypothesis:** A small red measuring spoon.
- **Audit disposition:** `REPAIR`.

The original machine output paired this sink interval with the microwave
interval 460 seconds later. Direct inspection found no shared object or
causal chain, so the far pair was removed. The primary interval was retained
as a local utensil-rinsing proposal.

Frames show a small red spoon-like utensil at the faucet and then carried away
from the sink. “Measuring spoon” remains a provisional identification; “small
red spoon” is a viable conservative alternative.

Water/faucet audio is plausible but unvalidated. The source contains many
water/sink recurrences, so the event requires recurrence repair or
replacement in any future normal-mode regeneration. No speech or OCR
substitute is needed.

## 7. Cross-candidate findings

### Dynamic action and non-speech audio

All six records now describe concrete physical actions or state changes.
Non-speech audio routes are present for all six, but they remain AST and
waveform hypotheses. No semantic sound identity has trained-human validation,
and no modality necessity is asserted.

### Multi-hop quality

Two far-separated records remain in the registry:

- `15_29` whole-to-diced tomatoes: repaired and provisionally coherent;
- `16_20` food-separation then onion-stirring: audited `REJECT`.

The original `26_22` water-to-microwave pair was repaired into a one-hop sink
proposal because direct inspection found no coherent source-world relation.

### Recurrence

Every source has repeated sink, water, pan, utensil, or appliance activity.
Machine recurrence lists are challenge routes, not adjudication. They include
false or overly broad matches based on shared AST classes and kitchen visual
profiles. Full-source trained-human duplicate closure remains required before
normal-mode regeneration.

### Speech, OCR, and shortcut substitutes

No final proposal has a speech hypothesis. Laptop screens, microwave/stove
displays, packaging, persistent kitchen geometry, and participant identity
remain possible shortcuts, but none is used as the authored answer basis.
Questions were written around observed actions, objects, and state changes.

## 8. Boundary

- Classification:
  `MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY`.
- `eligible_to_enter_gate_a=false`.
- `future_test_eligible=false`.
- Development outputs must not be renamed, copied, or promoted into Gate A.
- Human Task153 semantic prescreen complete: no.
- Accepted family count: 0.
- Accepted SES count: 0.
- Necessity/minimality claims: 0.
- H1/H2: 0/0.
- Active interventions: 0.
- Task145 C/B/R/N v2 templates remain inert and unexecuted.

**Final: `CAPTAINCOOK4D_DEV_CANDIDATES_REPAIR`.**
