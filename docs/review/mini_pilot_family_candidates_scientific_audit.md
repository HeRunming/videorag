# Mini-pilot family-candidate scientific audit

**Audit date:** 2026-09-23  
**Auditor role:** independent scientific audit  
**Registry:** `data/restricted/mini_pilot_family_candidates_v1/candidate_registry.json`  
**Registry status:** machine-provisional; 0 human-reviewed, 0 H1, 0 H2,
0 final accepted families  
**Decision token:** `CANDIDATE_SCIENCE_REPAIR`

## 1. Decision

`CANDIDATE_SCIENCE_REPAIR`

The registry is a useful deterministic mining artifact, but it is not a
scientifically ready 12-family pilot.

The decisive findings are:

1. **All 14 question and answer fields are placeholders.** Every question asks
   which observations support machine cues, and every answer says that a human
   must replace or reject it. Therefore no proposal is directly usable as a
   substantive QA family.
2. **Machine retrieval relevance is repeatedly mistaken for semantic
   evidence.** CLIP query similarity, BM25 term overlap, and AST class scores
   identify candidate intervals; they do not establish that an interval
   answers a human-meaningful question.
3. **The lecture-source ambient concern is confirmed.** All four
   ambient-bearing proposals from the Oxford/MIT/Yale lecture sources
   (`F02`, `F05`, `F06`, `F08`) fail as currently authored. Their ambient
   records are dominated by speech or generic classroom sounds, and the
   non-speech labels do not carry answer content.
4. **The lecture-source dynamic-visual concern is also confirmed.** The
   lecture visual proposals are chalkboard text/equations, static diagrams,
   title/end cards, or a talking head. None currently establishes a dynamic
   non-text visual route that is not recoverable from speech, transcript,
   captions, or OCR.
5. **The slot ontology contains a structural inconsistency.** Under the miner,
   `one_hop` means one distinct evidence interval and `far_separated` requires
   at least 120 seconds between evidence centers. A one-hop candidate therefore
   cannot be far/separated. The `F05` and `F09` target cells were impossible by
   construction and were correctly emitted as near/local.
6. **Machine “multi-hop” is not scientific multi-hop.** It currently means
   more than one distinct interval. Several such proposals join unrelated
   retrieval hits rather than claims that must be composed to answer one
   question.
7. **The current C/B/R templates are obsolete for future primary execution.**
   They use second-search or `get_channel_status` triggers. Any repaired family
   must be re-instantiated under
   `data/rehearsal_plan/exogenous_restoration_protocol_v2.json`, with the fixed
   exogenous checkpoint, matched `RESTORED`/`NO_TRIGGER` prefix, and
   mechanism-specific estimand.

No P tier is promoted by this audit. The reported registry tiers remain
machine-only metadata.

## 2. Evidence reviewed

The audit read:

- the complete 14-slot registry, including questions, answer hypotheses,
  atomic claims, evidence intervals, SES hypotheses, leave-one-out records,
  modality drops, sidecar challenges, route-closure registries, risk flags,
  strata, provenance, and inert intervention templates;
- Task 142's execution audit and result;
- Task 141's hostile red-team and source-composition requirements;
- the frozen CVPR pivot and Gate A/B rules;
- the current and replacement source dossiers;
- the canonical four-source full-timeline index, segment and observation
  manifests, and source-specific speech/ambient/vision checkpoints;
- the frozen NOAA Scale-1A index, migrated-family records, and source
  checkpoints;
- direct source-frame inspections at every selected and alternative visual
  interval; and
- the human construct-validity and saturation-auditor protocols.

The candidate registry, canonical data, source media, and miner code were not
modified.

## 3. Audit rubric

Each slot was assessed on:

- substantive question/answer meaningfulness;
- semantic specificity versus ranker or class-label artifacts;
- whether the route is genuinely visual, speech, or non-speech ambient rather
  than a transcript, caption, OCR, or neighboring-modality duplicate;
- preferred-SES sufficiency and minimality plausibility;
- alternative-route and official-sidecar risk;
- scientific one/multi-hop and near/far interpretation;
- intervention feasibility under the v2 causal contract;
- expected human labor and failure risk; and
- final disposition: `KEEP`, `REPAIR`, `REJECT`, or
  `DEMOTE_TO_CALIBRATION`.

Labor bands below are planning estimates, not measured annotation results:

- **moderate:** approximately 7–10 active reviewer-hours per family;
- **high:** approximately 10–15 hours;
- **very high:** approximately 14–20 hours.

They include two independent full-source searches, author/verifier work,
validators, adjudication, saturation audit, and route/intervention review.

## 4. Cross-cutting scientific findings

### 4.1 Question and answer validity

The registry records useful provenance but no finished scientific questions.
All 14 records fail the first construct requirement as written. A retained
record therefore means only that its underlying interval may support a newly
authored question after review.

### 4.2 Evidence and SES validity

The miner usually forms the preferred SES from the top result for each target
modality. It then treats overlapping or nearby top-ranked records as
alternative SES hypotheses. This creates three recurrent errors:

- overlapping windows from one continuous event are counted as distinct
  alternatives;
- unrelated high-scoring intervals are joined into one nominal multi-hop SES;
  and
- a ranker label is used as the claim itself, such as “the ambient model
  assigns Writing,” rather than evidence for a source-world fact.

Machine leave-one-out therefore does not establish minimality. In many cases it
only shows that another overlapping retrieval window exists.

### 4.3 Lecture/webinar ambient test

The red-team concern is **confirmed** for the acquired lecture sources:

| Slot | Source | Raw ambient finding | Scientific result |
|---|---|---|---|
| `F02` | Oxford QM | Selected interval is mostly speech; `Snort`, `Writing`, `Gasp`, `Animal`, and `Squish` have low scores and no demonstrated answer role. | Reject ambient route. |
| `F05` | MIT fluid dynamics | `Speech` is 0.835 and `Writing` is 0.764; the interval is a lecturer/slide section, not a semantically informative sound event. | Reject ambient-only family. |
| `F06` | MIT fluid dynamics | `Speech` is 0.926; `Writing` and several implausible low-score labels are attached to a narrated schematic. | Drop ambient; at most repair as V+S lecture navigation. |
| `F08` | Yale physics | `Writing` is strong, but it means chalk writing while the lecturer says “Newtonian mechanics.” The sound does not encode the requested physics content. | Reject ambient route and current family. |

The NOAA `cand-049` surf intervals are the only current source material with a
plausible real environmental sound. Even there, waves are simultaneously
visible and explicitly discussed in speech, and similar surf recurs elsewhere.
`F09` therefore remains a high-risk pre-screen candidate, not established
ambient necessity.

### 4.4 Lecture/webinar dynamic-visual test

The direct frame audit found:

- `F01`: evolving chalkboard text about quantum states;
- `F04`: Oxford title/presenter frames and the closing logo, not a literary
  quotation slide;
- `F06`: static Reynolds apparatus/result diagrams and later static slides;
- `F07`: a chalkboard projectile-motion derivation;
- `F08`: chalk writing and a later equation-filled board.

These may support narrowly scoped board/slide navigation, but they do not
support broad dynamic non-text visual claims. Their semantic content is mostly
the same content available through speech, transcript, captions, or OCR.

By contrast, `cand-049` contains real beach footage and a rescue animation.
That makes it the strongest current dynamic-visual source, although its
specific mined families still require reauthoring and route closure.

### 4.5 Stratum labels

The registry's observed labels are mechanically truthful but scientifically
insufficient:

- `F05` and `F09` are correctly relabeled from impossible one-hop/far targets
  to one-hop/near.
- `F10` is correctly relabeled to far because its ambient hit is about
  460 seconds from its speech/vision hits, but those pieces do not yet form a
  coherent answer.
- `F06` is called near at 115 seconds and `F02` far at 1,593 seconds because of
  the fixed 120-second threshold. This is a timing label, not proof of
  compositional reasoning.

Future selection should make one-hop imply near/local and reserve
far/separated for genuinely compositional multi-hop families.

### 4.6 Intervention feasibility

None of the registry's current C/B/R templates should be executed unchanged.
Every repaired candidate must:

1. freeze a human-accepted question, answer, claims, evidence graph, and all
   accepted SESs discovered under the frozen saturation protocol;
2. close ASR, official transcripts, captions, OCR, on-screen text, overlapping
   windows, repeated source passages, and cross-modal substitutes;
3. distinguish silent route withholding from explicit channel outage;
4. use the Task 145 exogenous fixed-action checkpoint for the primary
   `RESTORED` versus `NO_TRIGGER` contrast; and
5. prove that the remaining action budget permits reacquisition after
   restoration.

Whole-channel outages that suppress hundreds or thousands of records are
technically expressible but scientifically coarse. They should not substitute
for a defensible necessity group.

## 5. Candidate-by-candidate audit

### `F01` — Oxford quantum mechanics — **DEMOTE_TO_CALIBRATION**

- **Q/A:** not meaningful as written.
- **Raw evidence:** 1928–1936 seconds shows the lecturer writing on a board
  headed “Quantum States.” Alternatives at 1888–1920 are overlapping portions
  of the same board episode.
- **Route:** genuinely visual pixels, but the answer-bearing content is
  board text/formulas and is simultaneously explained in speech. It is an
  OCR/transcript-duplicate stress case, not broad visual understanding.
- **SES/minimality:** the one-window preferred SES is not minimal against the
  three overlapping visual alternatives; 20 sidecar routes and accessible
  speech further threaten necessity.
- **Labels:** one-hop/near is mechanically reasonable. `V` is not scientifically
  necessary on present evidence.
- **Intervention:** visual withholding alone would leave speech and likely OCR
  or transcript routes. Current pair isolation is implausible.
- **Labor/risk:** high, about 10–15 hours; many duplicate routes.
- **Disposition:** retain only as an OCR/board-duplication calibration reserve.

### `F02` — Oxford quantum mechanics — **REJECT**

- **Q/A:** not meaningful as written; no coherent joint fact is proposed.
- **Raw evidence:** speech at 1020–1050 discusses why quantum mechanics matters
  and probability distributions. The ambient interval at 2624–2632 is
  dominated by speech; low-score labels include snort, writing, gasp, animal,
  and squish.
- **Route:** speech plus a machine-label artifact, not a meaningful S+A family.
- **SES/minimality:** the three speech alternatives discuss other probability
  passages. They do not make the selected ambient event meaningful. The two
  preferred members are 1,593 seconds apart without a compositional relation.
- **Labels:** multi-hop/far is only a geometric label. Scientifically the pair
  is unrelated.
- **Intervention:** the template removes the full speech and ambient channels
  and 20 sidecar routes. That is a coarse outage, not a well-founded
  intervention on a meaningful family.
- **Labor/risk:** very high, about 14–20 hours, with little prospect of repair.
- **Disposition:** reject the proposal; author a different speech or
  board-navigation family if this source remains in a narrow development
  study.

### `F03` — Oxford D. H. Lawrence — **REPAIR**

- **Q/A:** placeholder, but the underlying speech is substantive.
- **Raw evidence:** 2370–2400 states that awakening children to consciousness
  is said to cripple their souls, then reports Birkin's challenge about whether
  one would rather know that the little red flowers are present.
- **Route:** genuine speech evidence. It has a direct official-transcript
  duplicate and must be checked against visible text/OCR.
- **SES/minimality:** one local speech interval is plausible, but the 30-second
  chunk should be tightened and the full lecture searched for repeated
  formulations.
- **Labels:** one-hop/near and speech-only are plausible after review.
- **Intervention:** feasible as an explicit speech outage only if official
  transcript, captions, and any visible text are also closed. Rebuild under the
  v2 exogenous trigger.
- **Proposed repair:** “What reason is given for opposing education, and what
  question does Birkin use to challenge that position?” Expected answer:
  consciousness is said to cripple children's souls; Birkin asks whether the
  speaker would rather know or not know that the little red flowers are there.
- **Labor/risk:** moderate to high, about 8–11 hours.
- **Disposition:** repair for the narrow current-source option; development
  only under the preferred event-centric option.

### `F04` — Oxford D. H. Lawrence — **REJECT**

- **Q/A:** not meaningful as written.
- **Raw evidence:** the selected visual interval is the closing Oxford card,
  while alternatives are the opening title/talking-head sequence. The speech
  evidence is the opening remark about Lawrence's popularity around 1970.
- **Route:** the claimed “literary quotation” visual is a retrieval false
  positive. The selected visual and speech do not jointly answer a coherent
  question.
- **SES/minimality:** invalid preferred SES; alternatives are title/presenter
  duplicates, not alternative support.
- **Labels:** multi-hop/far reflects opposite ends of the file, not reasoning.
- **Intervention:** no meaningful route exists to isolate or restore.
- **Labor/risk:** high, about 10–15 hours if pursued; rejection is cheaper.
- **Disposition:** reject and author a new speech-based far/multi-hop family
  only if this lecture is retained.

### `F05` — MIT fluid dynamics — **REJECT**

- **Q/A:** not meaningful as written.
- **Raw evidence:** 1828–1836 is a narrated lecture/slide interval. AST assigns
  high `Writing`, but also `Speech=0.835` and implausible low-score labels such
  as zipper, shuffling cards, crunch, snort, and stomach rumble.
- **Route:** machine-label artifact. Chalk/writing noise does not carry the
  fluid-dynamics answer.
- **SES/minimality:** several distant “Writing” hits survive leave-one-out,
  showing generic class recurrence rather than semantic alternatives.
- **Labels:** one-hop/near is the only possible observed temporal class.
  The one-hop/far target is structurally impossible.
- **Intervention:** an ambient-channel outage across 892 records is not a
  meaningful causal test for this proposal.
- **Labor/risk:** very high relative to expected yield, about 12–18 hours.
- **Disposition:** reject.

### `F06` — MIT fluid dynamics — **REPAIR**

- **Q/A:** placeholder; the three-way claim is not acceptable.
- **Raw evidence:** 76–84 shows a static schematic of Reynolds's apparatus;
  180–210 contains speech about observing swirls/eddies; 92–100 has
  speech-dominated AST labels with a secondary `Writing` prediction.
- **Route:** the visual and speech can potentially support a narrow
  diagram-plus-explanation question. Ambient performs no demonstrated
  semantic work. The visual is static diagram/text, not a dynamic experiment.
- **SES/minimality:** current V+S+A SES is not plausible. Drop ambient, tighten
  the speech interval toward the schematic explanation, and rescan repeated
  diagrams and transcript routes.
- **Labels:** a repaired V+S family could be multi-hop/near. It must not retain
  the `V+S+A` label.
- **Intervention:** potentially feasible as route withholding over a
  human-accepted diagram/speech SES; not feasible as current triple-modal
  withholding. Rebuild under v2.
- **Proposed repair:** ask for the depicted parts of Reynolds's setup and the
  narrated change in the dye stream as flow increases, while explicitly
  auditing whether speech alone answers both claims.
- **Labor/risk:** high, about 10–15 hours.
- **Disposition:** repair for a narrow lecture-agent study; development only
  in the preferred event-centric pilot.

### `F07` — Yale physics — **DEMOTE_TO_CALIBRATION**

- **Q/A:** not meaningful as written.
- **Raw evidence:** 3760–3792 shows a projectile-motion derivation on the
  blackboard. Two alternatives are the same evolving board state; another is
  an unrelated derivative/tangent section around 2192.
- **Route:** board text/equations plus lecturer pointing. This is an OCR and
  speech-duplication case, not a standalone dynamic-visual family.
- **SES/minimality:** the preferred context window is not minimal; nearby
  windows preserve the board. The distant alternative is semantically
  different despite a similar CLIP score.
- **Labels:** one-hop/near is mechanically correct. `V` necessity is not
  plausible without closing speech and OCR.
- **Intervention:** visual-only withholding would leave the spoken derivation.
- **Labor/risk:** high, about 10–15 hours.
- **Disposition:** retain only as a board/OCR calibration reserve.

### `F08` — Yale physics — **REJECT**

- **Q/A:** not meaningful as written.
- **Raw evidence:** the visual hit at 3736–3744 is an equation-filled board and
  lecturer; the ambient hit at 1412–1420 is chalk writing while the lecturer
  says “Newtonian mechanics.”
- **Route:** neither a moving apparatus nor meaningful ambient evidence. The
  two intervals concern different lecture moments.
- **SES/minimality:** current two-item SES is semantically incoherent.
  Visual alternatives are repeated board states.
- **Labels:** multi-hop/far describes distance only.
- **Intervention:** no answer-bearing ambient route exists to withhold.
- **Labor/risk:** very high, about 14–20 hours.
- **Disposition:** reject and replace with a newly authored lecture-navigation
  family only in Option A.

### `F09` — NOAA `cand-049` — **REPAIR**

- **Q/A:** placeholder; the raw source can support an interpretable
  environmental-audio question.
- **Raw evidence:** 1008–1016 contains visible breaking surf and AST evidence
  for ocean, waves/surf, and wind. Speech is also present and explicitly
  discusses wave-safety behavior. Adjacent and later surf segments are strong
  alternatives.
- **Route:** this is a real environmental scene, unlike the lecture ambient
  cases, but visual and narration can reveal the same condition. Human
  listening must identify a non-speech property that is not inferable from
  frames or words.
- **SES/minimality:** one short ambient interval may suffice for an auditory
  question, but repeated surf makes interval necessity unlikely. The accepted
  SES may need to be an event class rather than one exact 8-second window.
- **Labels:** one-hop/near; the target one-hop/far cell is impossible.
- **Intervention:** conditionally feasible as an ambient-channel outage or
  route withholding only after speech/visual substitutes are closed.
- **Proposed repair:** conduct a blind semantic-audio pre-screen and author a
  human-audible question. If no auditory property survives visual and speech
  challenge, remove the ambient stratum rather than force it.
- **Labor/risk:** high, about 10–15 hours.
- **Disposition:** repair with a hard fail-closed ambient pre-screen.

### `F10` — NOAA `cand-049` — **REPAIR**

- **Q/A:** placeholder.
- **Raw evidence:** 2096–2128 contains a dynamic rescue animation and nearby
  speech about alerting lifeguards/911 and using a floating or reaching aid.
  The selected ambient surf interval is around 1648–1656, about 460 seconds
  earlier.
- **Route:** the rescue visual and speech are meaningful. The distant ambient
  interval is real surf but is not shown to be necessary for the rescue
  answer.
- **SES/minimality:** current V+S+A SES is not coherent. Drop ambient and
  reauthor either a local V+S sequence or a defensible far two-part safety
  question using separate dynamic demonstrations.
- **Labels:** the current far label is mechanically correct only because of
  the unrelated ambient hit. Recompute labels after repair.
- **Intervention:** feasible after a new accepted SES and complete duplicate
  route inventory. Do not outage all three channels for the current family.
- **Proposed repair:** a two-part far question can connect an earlier
  demonstrated response to breaking waves with the later rescue sequence,
  requiring one visual action/state and one spoken instruction.
- **Labor/risk:** high, about 10–15 hours.
- **Disposition:** repair; strongest current dynamic-visual source.

### `F11` — NOAA `cand-052` — **REPAIR**

- **Q/A:** placeholder, but the underlying speech supports the original
  migrated-family question.
- **Raw evidence:** 2640–2670 states that El Niño and La Niña affect hurricane
  activity and identifies the North Atlantic Basin as a main area of interest.
- **Route:** genuine speech. The webinar interface contains substantial
  on-screen text, so an OCR/visible-text shortcut audit remains necessary even
  though no official sidecar was loaded by this miner.
- **SES/minimality:** one local speech interval is plausible; tighten to the
  exact answer span and search repeated basin mentions.
- **Labels:** one-hop/near and speech-only are plausible.
- **Intervention:** feasible as explicit speech outage only after visible text,
  captions, chat, and duplicate speech routes are closed; use v2 restoration.
- **Proposed repair:** restore the original question: “Which basin does the
  speaker identify as a main area of hurricane activity?” Expected answer:
  “The North Atlantic Basin.”
- **Labor/risk:** moderate to high, about 8–11 hours.
- **Disposition:** repair.

### `F12` — NOAA `cand-052` — **REPAIR**

- **Q/A:** placeholder.
- **Raw evidence:** the selected visual at 3448–3456 is a SLOSH storm-surge
  animation, while selected speech at 300–330 discusses the 2020 hurricane
  season. They do not support the “three formation factors” seed. A retrieved
  alternative at 1332–1336 does show the correct “3 Factors Hurricane
  Formation” graphic, with matching narration in 1320–1350.
- **Route:** current preferred evidence is wrong. The original local
  visual-plus-speech pair is meaningful but largely duplicate/corroborative:
  both say there are three factors.
- **SES/minimality:** re-anchor to approximately 1332–1340 and model the visual
  and speech as alternative SESs unless a revised question makes both
  necessary.
- **Labels:** after re-anchoring, one-hop/near is more defensible than the
  current multi-hop/far label.
- **Intervention:** feasible as a route-closure stress family that withholds
  both duplicate routes, not as proof that both modalities are necessary.
- **Proposed repair:** re-anchor the family to approximately 1332–1340. For
  Option B, narrow it to the speech-only question “How many
  hurricane-formation factors does the narration state?” with answer “Three.”
  If the original narration-plus-graphic wording is retained for development,
  treat the two modalities as duplicate/corroborative routes rather than
  claiming dual-modality necessity.
- **Labor/risk:** high, about 10–14 hours because visible captions and repeated
  hurricane graphics require closure.
- **Disposition:** repair.

### `CAL01` — NOAA `cand-051` — **REPAIR**, calibration only

- **Q/A:** placeholder and incorrectly calls the selected interval an
  “introductory montage.”
- **Raw evidence:** 1328–1360 shows a large pile of plastic trash while the
  narration discusses preventing marine debris. Alternatives show
  microplastics, opening presenters, and another outdoor trash scene.
- **Route:** meaningful visual content, but on-screen captions and narration
  duplicate the material category, and repeated plastic imagery is extensive.
- **SES/minimality:** intentionally difficult alternative-route case; not a
  low-risk anchor.
- **Labels:** one-hop/near is plausible after wording repair.
- **Intervention:** useful for testing route-closure forms, not for a reported
  visual-necessity result.
- **Proposed repair:** ask what discarded material is visibly piled up in the
  selected scene, with “plastic trash/waste” as the provisional answer.
- **Labor/risk:** high, about 9–13 hours.
- **Disposition:** keep only as one of the two excluded, repaired calibration
  families.

### `CAL02` — Oxford D. H. Lawrence — **REPAIR**, calibration only

- **Q/A:** placeholder.
- **Raw evidence:** 210–240 contains a clear spoken list including Germany and
  Italy and a preview of later lecture topics.
- **Route:** genuine speech with a direct official-transcript duplicate.
- **SES/minimality:** one interval is plausible after tightening; sidecar and
  repeated lecture-outline references must be checked.
- **Labels:** one-hop/near and speech-only are plausible.
- **Intervention:** suitable for testing speech-outage forms after v2
  conversion and transcript/OCR closure.
- **Proposed repair:** use a simple wording/timing question, such as which two
  countries are described as having meant a lot to Lawrence.
- **Labor/risk:** moderate, about 7–10 hours.
- **Disposition:** keep only as the second excluded, repaired calibration
  family.

## 6. Disposition summary

| Disposition | Slots | Count |
|---|---|---:|
| `KEEP` as written | none | 0 |
| `REPAIR` | `F03`, `F06`, `F09`, `F10`, `F11`, `F12`, `CAL01`, `CAL02` | 8 |
| `DEMOTE_TO_CALIBRATION` | `F01`, `F07` | 2 |
| `REJECT` | `F02`, `F04`, `F05`, `F08` | 4 |

The two formal excluded calibration families should remain repaired `CAL01`
and repaired `CAL02`. `F01` and `F07` are additional development/calibration
reserves, not extra reported families.

## 7. Pilot composition option A: current six sources, narrow scope

### Scientific scope

Option A is acceptable only as a **developmental lecture/webinar evidence-
navigation pilot**. It must not support claims about broad audiovisual
reasoning, semantic ambient evidence, or dynamic visual understanding.

Remove reported ambient and `V+S+A` strata. Allow speech, board/slide
inspection, diagram grounding, local dynamic instructional clips, and
duplicate-route closure. Label board and slide tasks explicitly as
text/diagram navigation rather than native dynamic vision.

### Proposed 12 reported families

This is a new, explicitly narrower slot matrix. It retains the 6/6 hop,
6/6 temporal, and 6/6 intervention balance, but intentionally collapses the
modality profile to 6 speech, 2 visual, and 4 V+S families. It contains no
reported ambient or V+S+A family.

| Slot | Source | Lineage/purpose | Profile | Hop | Span | Primary mechanism |
|---|---|---|---|---|---|---|
| A01 | `SG-OXFORD-QM-001` | New local spoken concept | S | one | near | explicit channel outage |
| A02 | `SG-OXFORD-QM-001` | New separated board-to-spoken-explanation navigation | V+S | multi | far | silent route withholding |
| A03 | `SG-OXFORD-DHL-CONSCIOUSNESS` | Repaired `F03` | S | one | near | explicit channel outage |
| A04 | `SG-OXFORD-DHL-CONSCIOUSNESS` | New separated spoken-claim synthesis replacing `F04` | S | multi | far | silent route withholding |
| A05 | `SG-MIT-RES12-003-L01` | Repaired `F06`, re-anchored to one local schematic/explanation episode | V+S | one | near | silent route withholding |
| A06 | `SG-MIT-RES12-003-L01` | New separated spoken fluid-dynamics synthesis replacing `F05` | S | multi | far | explicit channel outage |
| A07 | `SG-YALE-PHYS200-L01` | New local board-state navigation question replacing `F07` | V | one | near | silent route withholding |
| A08 | `SG-YALE-PHYS200-L01` | New separated board-plus-speech synthesis replacing `F08` | V+S | multi | far | explicit channel outage |
| A09 | `cand-049` | New local dynamic safety visual replacing ambient `F09` | V | one | near | silent route withholding |
| A10 | `cand-049` | Repaired `F10` without ambient | V+S | multi | far | explicit channel outage |
| A11 | `cand-052` | Repaired `F11` | S | one | near | explicit channel outage |
| A12 | `cand-052` | New separated spoken-weather synthesis replacing `F12` | S | multi | far | silent route withholding |

Formal excluded calibrations:

- repaired `CAL01`: repeated visual/onscreen-text alternative-route stress;
- repaired `CAL02`: speech/official-transcript wording and timing stress.

Current `F01`, `F02`, `F04`, `F05`, `F07`, `F08`, `F09`, and `F12` are
development-only examples under Option A. Repaired `F03`, `F06`, `F10`, and
`F11` are the only current reported-slot lineages retained in its proposed
denominator.

### Option-A judgment

This option can debug the six-role workflow and intervention machinery after
the listed repairs. It does **not** satisfy the Task 141 source-composition
repair and should not be used to preserve ambient or broad audiovisual paper
claims.

## 8. Pilot composition option B: preferred event-centric replacement wave

### Source composition

Use exactly six pilot source groups:

1. retain NOAA `cand-049`, conditional on rights/privacy review and semantic
   audio pre-screen;
2. retain NOAA `cand-052`, conditional on rights/privacy and visible-text
   route review;
3. add `NEW-EVENT-01`, a field procedure or maintenance source;
4. add `NEW-EVENT-02`, an observational environment or wildlife source;
5. add `NEW-EVENT-03`, an industrial or laboratory process source; and
6. add `NEW-EVENT-04`, an assembly, repair, mission-operation, or comparable
   action-rich source.

Each new source must pass the existing exact-route, duration, synchronized-A/V,
rights, privacy, source-disjointness, and restricted-custody gates. Before
family authoring, a human semantic pre-scan must affirm:

- at least one non-speech event whose audible property can change
  answerability;
- dynamic visual evidence not recoverable from transcript, captions, OCR, or
  metadata;
- no use of score/music as semantic ambient evidence; and
- two candidate families without weakened sufficiency or necessity rules.

No current held USGS/NASA/Commons lead is selected merely because it appears
event-centric; it must first pass a fresh complete dossier and semantic scan.

### Exact 12-slot target

This composition preserves the frozen profile, hop, temporal, and intervention
totals without the impossible one-hop/far cells:

| Slot | Source | Profile | Hop | Span | Primary mechanism | Status |
|---|---|---|---|---|---|---|
| B01 | `cand-049` | A | one | near | silent route withholding | repaired `F09`, conditional on semantic-audio pass |
| B02 | `cand-049` | V+S | multi | far | explicit channel outage | repaired `F10`, two coherent safety episodes, no ambient claim |
| B03 | `cand-052` | S | one | near | explicit channel outage | repaired `F11` |
| B04 | `cand-052` | S | one | near | silent route withholding | repaired/re-anchored `F12`, narrowed to speech |
| B05 | `NEW-EVENT-01` | V | one | near | silent route withholding | new |
| B06 | `NEW-EVENT-01` | V+A | multi | far | explicit channel outage | new |
| B07 | `NEW-EVENT-02` | V | one | near | explicit channel outage | new |
| B08 | `NEW-EVENT-02` | V+S+A | multi | far | silent route withholding | new |
| B09 | `NEW-EVENT-03` | A | one | near | explicit channel outage | new |
| B10 | `NEW-EVENT-03` | S+A | multi | far | silent route withholding | new |
| B11 | `NEW-EVENT-04` | V+S | multi | far | silent route withholding | new |
| B12 | `NEW-EVENT-04` | V+S+A | multi | far | explicit channel outage | new |

Target totals are:

- profiles: exactly 2 each for `V`, `S`, `A`, `V+S`, `V+A/S+A`, and
  `V+S+A`;
- hop: 6 one-hop and 6 multi-hop;
- temporal: 6 near/local and 6 far/separated;
- intervention: 6 silent necessity-group withholding and 6 explicit
  modality-channel outage.

These remain authoring targets, never labels to force.

### Current sources and slots retained only for development/calibration

Under Option B, the four lecture sources are removed from the gate-defining
pilot:

| Current source | Current slots | Option-B role |
|---|---|---|
| `SG-OXFORD-QM-001` | `F01`, `F02` | development/calibration only |
| `SG-OXFORD-DHL-CONSCIOUSNESS` | `F03`, `F04`, `CAL02` | development/calibration only |
| `SG-MIT-RES12-003-L01` | `F05`, `F06` | development/calibration only |
| `SG-YALE-PHYS200-L01` | `F07`, `F08` | development/calibration only |
| `cand-051` | `CAL01` | excluded calibration only |

Only repaired `F09`–`F12` are conditionally carried into the Option-B
gate-defining candidate set. Current NOAA material remains development-touched
and is ineligible for any future primary test split.

Formal calibrations remain repaired `CAL01` and repaired `CAL02`; the remaining
lecture candidates may be used for author training, negative examples, and
route-closure rehearsal but not counted in the 12-family denominator.

### Option-B judgment

Option B is scientifically preferred. It directly addresses the red-team
failure mode by making at least four of six source groups event-centric and
limiting presentation/webinar-style sources. It is still only a plan:
replacement sources, repaired questions, semantic modality scans, governance,
v2 intervention manifests, staffing, and all six human roles remain
unfinished.

## 9. Required repairs before `MINI_PILOT_INPUT_READY`

1. Freeze a revised source registry with capture-format fields and the Option-A
   or Option-B claim scope.
2. Remove the impossible one-hop/far target cells and re-freeze the slot
   matrix.
3. Replace every placeholder question, answer, and claim with human-authored
   substantive content before reviewer assignment.
4. Run a pre-authoring semantic modality screen for every A, V+A, S+A, and
   V+S+A proposal.
5. Record visual-route class as dynamic non-text, diagram, board/OCR,
   title/overlay, or talking head.
6. Rebuild accepted-SES hypotheses from semantic claims, not top-ranked
   modality records.
7. Close official transcripts, ASR, captions, OCR, visible webinar text,
   repeated source statements, overlapping windows, and cross-modal
   substitutes.
8. Convert every intervention to the Task 145 exogenous-restoration v2
   contract and run the state-surface/leakage preflight.
9. Resolve the current NOAA rights/privacy `unknown_hold` or replace those
   sources.
10. Freeze exactly two calibration families, source-level blindness rules,
    reviewer roster, forms, packet hashes, and sampling seed.

Only after these repairs should a separate Gate A audit decide
`MINI_PILOT_INPUT_READY`.

## 10. Boundary

- No P0/P1/P2 tier was promoted.
- No H1 or H2 status is assigned or implied.
- No human validation was performed.
- No intervention was executed.
- No model or scientific evaluation result is claimed.
- The canonical registry and source/index artifacts remain unchanged.

## 11. Final token

```text
CANDIDATE_SCIENCE_REPAIR
```
