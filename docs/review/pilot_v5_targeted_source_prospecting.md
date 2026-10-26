# Pilot-v5 targeted source prospecting

**Date:** 2026-10-12  
**Decision:** `PILOT_V5_TARGETED_PROSPECTING_READY`  
**Artifact class:** prospective source/asset routing plan only  
**Human semantic review performed by this task:** no  
**New media downloaded by this task:** no  
**Gate A GO asserted:** no

## 1. Executive decision

Pilot v4 honestly leaves these exact prospective shortages:

| Dimension | Target | Pilot-v4 hypothesis count | Shortage |
|---|---:|---:|---:|
| `V+S` | 2 | 0 | **2** |
| `V+S+A` | 2 | 0 | **2** |
| multi-hop | 6 | 5 | **1** |
| far/separated | 6 | 1 | **5** |

The shortages must be solved together, not as nine independent labels. Because
one-hop/far is prohibited, the five missing far families must all be coherent
multi-hop compositions. Four may replace current near/multi slots; one must
also replace a current one/near slot to close the one remaining multi-hop
shortage.

The recommended prospective order is:

1. **Prescreen already-local exact sources first**, with priority on NOAA
   `cand-049`, `cand-047`, and `cand-051`, followed by the current EPIC and
   CaptainCook4D exact timelines. This has the lowest acquisition cost and can
   test whether one `V+S` and several far compositions already exist, but it
   has high substitution and recurrence risk.
2. **Acquire distinct EPIC and CaptainCook4D source groups already enumerated
   by official metadata** if governance and acquisition are separately
   approved. These routes have exact IDs, long-duration evidence, synchronized
   A/V at dataset or selected-stream level, and dense timestamps, but their
   semantic labels must remain sealed during selection and initial authoring.
3. **Repair Assembly101 access** as the best independent procedural lineage
   once gate authorization, duration, native audio, and annotation authority
   close.
4. **Use HD-EPIC or MECCANO only as conditional fourth-lineage routes.** They
   are attractive for speech-plus-action or procedural audio, but current
   local evidence does not establish a usable exact asset pool.
5. **Do not spend primary effort on documentary/public-web or weak HF
   routes** until exact item rights, native synchronized audio, and timestamps
   are proved. They are reserves, not quota credit.

No route below is credited as a family. No machine score, transcript, dataset
label, action graph, sound label, or temporal distance is treated as human
semantic evidence. Candidate routes become usable only after the explicit
Go/Repair/No-Go requirements in the companion JSON are met.

## 2. Frozen evidence and non-claims

This plan is grounded in the frozen Pivot-v2 matrix and preregistration, the
pilot-v4 matrix and human-packet audits, the complete EPIC and CaptainCook4D
timeline indices, their development-only candidate registries, the complete
NOAA Scale-1A index, the licensed-dataset/access registries, and Task193
semantic-audio discovery.

The following boundaries remain unchanged:

- profile and structural cells are authoring targets, never labels to force;
- `V` means dynamic non-text visual evidence, not OCR, captions, slides, title
  cards, or a static diagram alone;
- `S` means substantive speech, not transcript text considered independently
  of its speech route;
- `A` means a concrete, temporally localizable source-world non-speech event
  that changes answerability, not score, applause, generic room noise, coarse
  AST/CLAP labels, or a visible/spoken duplicate;
- `V+S` and `V+S+A` require each named modality to carry a non-duplicative
  part of the authored answer after shortcut and substitute closure;
- far/separated requires a coherent composed claim over genuinely separated
  evidence, not unrelated intervals selected to satisfy a quota;
- a source group, including all participant/session/view/derivative lineage,
  stays in one split;
- existing development sources remain future-test-ineligible;
- no current Task153 source pass, Task194 human decision, accepted SES, H tier,
  or Gate-A GO is inferred here.

## 3. What the inspected artifacts establish

### 3.1 Current exact EPIC and CaptainCook4D sources

The exact local pool contains:

- EPIC `P27_101` and `P28_103`, totaling 3,185.36 seconds;
- CaptainCook4D `15_29`, `16_20`, and `26_22`, totaling 4,547.94 seconds.

Their full-timeline indices contain vision, speech, and ambient routing
records. Their candidate registries and Task193 agree on a hard limitation:
quality-passing substantive speech is essentially absent. Task193 retained two
provisional `A` and eight provisional `V+A` leads, but **zero `S+A`, zero
`V+S`, and zero `V+S+A` leads**. These five exact sources therefore remain
useful for far-state/procedure discovery and for confirming the current
audio-bearing candidates, but they are weak routes for the missing speech
profiles unless trained-human source-uniform review discovers speech that the
current ASR quality gates missed.

The one existing far hypothesis, `15_29` whole-to-diced tomatoes, remains
machine-expert provisional. The rejected `16_20` far pair must not be revived:
its intervals did not establish a shared object, dish, or causal chain.

### 3.2 Current exact NOAA sources

Five exact NOAA sources are locally indexed with synchronized H.264/AAC
streams and durations from 1,772.44 to 3,781.14 seconds. Of these:

- `cand-049` has real beach footage, rescue animation, substantive speech, and
  a repaired `V+S` lead, but repeated animation, repeated speech, OCR/`911`,
  and speech-only substitutes remain open;
- `cand-047` contains long speech-rich deep-ocean/watch-party material with
  embedded expedition clips and hands-on demonstrations, but no human review
  has established whether any visual component is dynamic and non-duplicative
  or whether any source-world ambient sound survives narration and score;
- `cand-051` contains long speech-rich marine-debris material with field or
  embedded clips according to the source inventory, but current candidate
  work used it only as a visual-route calibration and did not establish a
  substantive multimodal family;
- `cand-045` is presentation/resource dominated and is a lower-priority
  `V+S` route because slides, websites, and OCR are likely substitutes;
- `cand-052` supplies speech candidates but its inspected visual route is
  duplicate text/graphic evidence and its ambient predictions are not
  semantically established.

These are technically cheap to prescreen because the exact media and complete
index already exist. They are scientifically expensive if full-source route
closure repeatedly finds narration, captions, OCR, repeated clips, or
editorial sound to be complete substitutes.

### 3.3 Additional exact metadata pools

The inspected access artifacts provide two especially useful nonsemantic
candidate pools:

- **EPIC reserve participants:** `P02_108`, `P35_107`, `P12_101`, `P01_101`,
  `P23_102`, `P33_109`, `P04_123`, and `P06_101`, plus replacements
  `P22_114` and `P03_103`. Durations are 21.53-59.49 minutes. The official
  EPIC route and checksums are known; dataset-level audio is established
  through EPIC-SOUNDS, but selected-file stream checks and governance approval
  remain prerequisites.
- **CaptainCook4D reserve groups:** `25_1`, `25_109`, `2_13`, `16_23`, and
  `23_19`, plus `23_24` and `16_17`. Durations are 21.51-35.45 minutes. Exact
  official GoPro/HoloLens routes and participant/environment groupings are
  enumerated. Native audio was later verified for the three acquired wave-0
  GoPro files, not for these reserve files; bounded technical verification and
  governance approval remain required.

Both datasets have dense timestamp annotations that could help a later
evaluator audit, but opening those semantics during source selection or
initial authoring would contaminate the route. Use only IDs, durations,
hashes, stream facts, and lineage fields until source freeze.

### 3.4 Independent or public/HF routes

- **Assembly101** has an exact pinned HF revision, 362 session IDs, 48
  participant lineages, exact file sizes/hashes, and a frozen 8+2 pool.
  Current account access to media returned `403 GatedRepo`; wall-clock
  duration and native audio remain unproved.
- **HD-EPIC** is promising because local dataset-level evidence reports
  corrected narrations and dense audio events, but no exact release,
  selected-file route, or operative terms are pinned.
- **MECCANO** remains the preferred independent lineage from the earlier
  access audit, but exact release, rights, route, IDs, duration, audio, and
  timestamps remain unresolved.
- **Ego4D/Ego-Exo4D** can provide long speech/action sessions, but access,
  agreement, selected-file audio, privacy, and Meta-lineage correlation make
  them higher-cost reserves rather than the first repair.
- **USGS Shift Curves** and selected NASA/NARA items may provide long
  procedures or mission sequences, but exact item/component rights, source
  objects, native audio, and timestamp annotation support remain unresolved.
- **VES-Bench, LongVideoBench silent renditions, and current
  OmniVideoBench/TraceAV routes are No-Go for primary prospecting** under the
  present evidence: duration is absent or audio is absent/access-blocked, and
  item-level rights remain unresolved.

## 4. Candidate classes

### A. Already in current exact sources: human semantic prescreen required

#### A1. NOAA `cand-049` rescue/safety reauthoring

**Potential contribution:** one `V+S`, one far, one multi.

Prescreen the full source without the old candidate labels. The candidate is
viable only if a trained author can define a two-part safety question in which:

1. an earlier dynamic demonstration carries one necessary claim;
2. a separated spoken instruction or later dynamic rescue sequence carries a
   second necessary claim; and
3. neither speech alone, animation alone, visible `911`/captions, nor the
   repeated rescue sequence answers the whole question.

The old ambient surf interval is excluded. It may not be appended to make the
family triple-modal.

#### A2. NOAA `cand-047` deep-ocean clips and hands-on demonstration

**Potential contribution:** one `V+S`; possibly one far/multi.

This is a source-level prospect, not a candidate fact. Prescreen:

- embedded expedition footage for dynamic animal/ROV interactions that
  narration does not completely describe;
- separated hands-on model construction and later expert explanation for a
  coherent composed claim;
- all visible labels, polls, title cards, subtitles, and replayed clips.

Do not claim underwater ambient audio unless listening establishes that it is
native or source-world sound and answer-bearing rather than score or
voice-over mix.

#### A3. NOAA `cand-051` marine-debris field/embedded clips

**Potential contribution:** one `V+S`; possibly one `V+S+A`; one far/multi.

The long duration and speech density make it worth a source-uniform human
prescreen. A triple-modal candidate requires a dynamic field action or object
state, a non-duplicative spoken claim, and a concrete source-world sound such
as handling, collection, sorting, or water interaction. Music, generic
animal-like AST labels, and narration bed do not count.

#### A4. Current EPIC/CaptainCook complete timelines

**Potential contribution:** far/multi only; speech-profile yield expected low.

Run a blinded far-composition prescreen over all five sources, prioritizing
same-object state transitions, setup-to-result chains, and tool/material
transformations separated by at least the frozen far threshold. Existing
near-local Task193 leads may seed time neighborhoods only after prescreen
assignments are frozen; they may not be relabeled far. Any speech-bearing
candidate is Repair until direct listening confirms substantive speech and
independent visual work.

#### A5. NOAA `cand-045` and `cand-052` presentation sources

**Potential contribution:** at most `V+S` or speech far/multi; low priority.

Use only if higher-ranked exact sources fail. Dynamic non-text vision must be
demonstrated; website navigation, slides, diagrams, captions, and text panels
remain OCR/derived routes. `cand-052`'s three-factor graphic stays a duplicate
speech/text route, not `V+S`.

### B. Additional datasets or exact assets worth acquiring

#### B1. Distinct EPIC participant groups

**Priority:** highest acquisition route.

Select from the frozen reserve pool before opening action, narration, or
EPIC-SOUNDS labels. Favor 30-60 minute representatives and distinct
participant/kitchen groups. Search prospectively for:

- a dynamic action/state plus non-duplicative narration for `V+S`;
- a dynamic action/state, substantive speech, and a concrete non-speech event
  for `V+S+A`;
- setup/result or error/recovery compositions with separated timestamp
  support.

Because this remains the Oxford/EPIC lineage, use it to fill at most one
source group if source diversity would otherwise collapse.

#### B2. Distinct CaptainCook4D participant/environment groups

**Priority:** highest procedure/far route; medium speech route.

Acquire only after bounded stream/audio verification and governance closure.
The reserve groups are source-disjoint by participant and environment from
the current three. They are strong candidates for long procedure state
changes and source-world sound, but `V+S`/`V+S+A` credit requires actual
substantive speech rather than presumed kitchen narration.

#### B3. Assembly101 after gate repair

**Priority:** best independent procedural lineage.

Obtain dataset gate authorization, then verify wall-clock duration and native
audio for the frozen 8+2 participant-blocked sessions before acquisition.
Assembly/mistake/recovery structure is attractive for far/multi and
`V+S`/`V+S+A`, but speech is not guaranteed. Fine/coarse action and mistake
labels remain sealed through independent authoring.

#### B4. HD-EPIC

**Priority:** conditional high-value speech/audio route.

Worth acquiring only after pinning the exact release, operative agreement,
selected source IDs, durations, checksums, and native synchronized audio.
Corrected narrations plus reported audio events make it a strong
`V+S+A` prospect, but it is correlated with EPIC and must not be counted as an
independent publisher lineage. All semantic labels and timestamps remain
sealed until post-authoring audit.

#### B5. MECCANO

**Priority:** conditional independent-lineage route.

Proceed only if official metadata establishes an immutable release, rights,
20-90 minute source groups, synchronized audio, and timestamp annotations or
raw continuous media. If speech is absent, use it for far/multi and `V+A`,
not forced `V+S+A`.

#### B6. Rights-first public long assets

**Priority:** reserve.

USGS Shift Curves is the strongest field-procedure lead. NASA Moonbound,
Pathfinders, To the Rescue, and selected NARA process films are useful only
after exact item/component rights, official object identity, audio streams,
duration, and annotation authority are established. Edited documentaries have
high narration-substitution, score, archive-component, and timestamp-cost
risk; they should not outrank exact research-dataset routes.

### C. Strata to narrow if support remains absent

Narrowing is prospective claim control, not retrospective relabeling.

1. **Remove `V+S+A` from the pilot denominator and paper claims** if two
   source-disjoint triple-modal candidates do not survive:
   - at least 12 rights-eligible, audio-verified, long-video source prescreens;
   - at least four capture/production lineages;
   - at least six initially plausible triple-modal intervals;
   - full human audio-first/A-V prescreen; and
   - duplicate-route and full-source recurrence challenge.
2. **Narrow the exact 6/6 far balance to “far/multi feasibility reported
   descriptively”** if five defensible far replacements do not emerge after:
   - complete far-composition review of the five current exact EPIC/CC
     timelines and `cand-049`, `cand-047`, `cand-051`;
   - acquisition/prescreen of at least four new source-disjoint long groups;
   - at least 20 far-composition attempts; and
   - rejection of arbitrary or distance-only pairings.
3. **Narrow `V+S` to corroborative audiovisual routing, not modality
   necessity**, if two candidates cannot survive speech-only, vision-only,
   OCR/caption/transcript, repeat-clip, and question-prior challenges.
4. If any required stratum can be filled only by weakening rights,
   source-disjointness, semantic-prescreen, minimality, or temporal-coherence
   rules, Gate A becomes **No-Go for the broad matrix**. The correct outcome
   is a narrower preregistered pilot, not quota-preserving relabeling.

## 5. Cross-route acquisition and evaluation criteria

### 5.1 Source disjointness

Required before semantic inspection:

- group by participant/household, environment/kitchen, continuous recording
  lineage, synchronized session/take, publisher production family, and every
  derivative;
- keep EPIC and HD-EPIC overlap in one super-group if identity/kitchen overlap
  cannot be ruled out;
- keep all Assembly101 synchronized views and repeated participant sessions
  together;
- keep all CaptainCook4D views/streams for one participant-environment group
  together;
- keep NOAA embedded/replayed clips linked to their production/source family
  when traceable;
- reject mirrors, excerpts, alternate encodes, or benchmark derivatives as
  independent sources.

### 5.2 Rights and access

Before media acquisition or human annotation, require:

- immutable release/object identity and checksum or provider-bound object
  hash;
- operative media terms, not only code or annotation licenses;
- affirmative internal-processing and restricted-annotation authority;
- privacy/consent, withdrawal, retention, deletion, and least-privilege
  handling;
- separate decisions for raw media, clips/frames/audio, transcripts,
  annotations/evaluator records, identifiers, and features;
- no inference of release authority from public hosting or successful login.

### 5.3 Long-video and stream criteria

Preferred wall-clock duration is **1,200-5,400 seconds**, counted once per
coherent session rather than summed across camera views. A route must prove:

- at least one decodable video stream;
- at least one native synchronized audio stream;
- audio codec, channels, sample rate, and nonempty decoded samples;
- audio/video start and end alignment within the frozen technical tolerance;
- a stable timestamp/time-base map usable for source-time evidence bounds.

Subtitles, captions, narration annotations, or benchmark text do not prove an
audio stream.

### 5.4 Speech and ambient criteria

For a source to remain in `V+S+A` prospecting:

- substantive speech and a concrete non-speech event must overlap the
  authored answer without either being a complete substitute;
- the non-speech event must be audible in audio-first review and identifiable
  without revealing machine labels or expected answers;
- music, applause, room tone, wind bed, score, and generic handling noise are
  excluded unless a concrete source-world property is independently shown to
  change answerability;
- speech ASR, captions, and official transcripts are route-discovery tools and
  derived duplicates, not independent modalities.

### 5.5 Timestamp and annotation criteria

Preferred sources expose native source-time, stable time bases, and dense
human timestamps. Existing semantics remain sealed during selection and
initial authoring. After an independent question/evidence draft is frozen,
annotations may be opened only for:

- recurrence and missed-route auditing;
- exact temporal-boundary challenge;
- participant/session lineage verification; and
- contamination/near-duplicate checks.

Existing labels never establish AV-TRACE minimality, necessity, accepted SES,
or H tier.

### 5.6 Acquisition-cost bands

| Band | Definition | Examples |
|---|---|---|
| Low | Exact local media/index already present; no transfer; only authorized human prescreen and route closure needed | NOAA exact five, current EPIC/CC five |
| Medium | Exact IDs, durations, hashes/routes known; selective acquisition and one full index required | EPIC reserve, CaptainCook4D reserve |
| High | Gate/agreement, duration/audio verification, privacy review, or multiview selection unresolved | Assembly101, HD-EPIC, MECCANO |
| Very high | Item/component rights, exact object, audio, timestamps, and editing provenance unresolved | NASA/NARA/USGS documentary/public assets |

Stop a route when expected profile yield no longer justifies full-timeline
indexing and six-role review. In particular, do not acquire a high-cost source
solely because its metadata mentions sound, narration, or an event.

## 6. Execution sequence and stop rules

### Wave 0 — no acquisition

1. Obtain annotation authority for the exact local sources.
2. Run source-uniform Task153-style visual/audio prescreens for `cand-049`,
   `cand-047`, `cand-051`, then the current EPIC/CC sources.
3. Produce candidate facts without old labels, proposed profiles, expected
   answers, or machine ranks visible to prescreeners.
4. Run a dedicated far-composition pass requiring same object/material,
   setup-result, instruction-execution, error-recovery, or observation-
   interpretation coherence.

**Wave-0 Go:** at least two defensible `V+S` prospects or one `V+S` plus two
far prospects survive prescreen.  
**Wave-0 Repair:** useful candidates exist but rights, recurrence, or
substitution fields remain open.  
**Wave-0 No-Go:** all speech/vision pairs are duplicate routes and all far
pairs are arbitrary or distance-only.

### Wave 1 — selective exact research-dataset acquisition

Acquire at most:

- two distinct EPIC participant groups;
- two distinct CaptainCook4D participant/environment groups; and
- two Assembly101 groups only if its gate, duration, and audio repairs close.

Do not open semantic annotations before the source/group list and checksums
are frozen.

**Wave-1 Go:** the combined current/new pool contains at least two
source-disjoint `V+S`, two source-disjoint `V+S+A`, and six far/multi
prospects before author/verifier acceptance.  
**Wave-1 Repair:** one triple-modal or two far cells remain open but a distinct
rights-ready route is identified.  
**Wave-1 No-Go:** required cells remain empty across three or more lineages,
or only correlated EPIC-family sources can fill them.

### Wave 2 — high-cost independent lineage

Use HD-EPIC, MECCANO, or one rights-clean public field/mission asset only if
Wave 1 fails and the exact route-specific evidence requirements are met.

Stop broad prospecting and invoke the narrowing rules if:

- 12 long source groups across four lineages have completed semantic
  prescreen without two triple-modal survivors;
- 20 far-composition attempts across at least ten source groups yield fewer
  than five coherent far families;
- estimated acquisition/index/prescreen labor exceeds 40 hours per surviving
  candidate in a route; or
- any route requires weakening source grouping, rights, modality, temporal,
  or blindness rules.

## 7. Ranked route summary

| Rank | Route | Class | Primary shortage role | Current disposition |
|---:|---|---|---|---|
| 1 | NOAA `cand-049` rescue/safety | Existing exact | `V+S`, multi, far | `REPAIR` |
| 2 | NOAA `cand-047` deep-ocean/demonstration | Existing exact | `V+S`, multi, far | `REPAIR` |
| 3 | NOAA `cand-051` field/debris | Existing exact | `V+S`, possible `V+S+A`, multi, far | `REPAIR` |
| 4 | Distinct EPIC reserve participants | Acquire exact | `V+S`, `V+S+A`, multi, far | `REPAIR` |
| 5 | Distinct CaptainCook4D reserve groups | Acquire exact | far/multi; possible `V+S+A` | `REPAIR` |
| 6 | Current EPIC/CC far-composition pass | Existing exact | multi, far | `REPAIR` |
| 7 | Assembly101 gate repair | Acquire gated HF | independent far/multi; possible `V+S+A` | `REPAIR` |
| 8 | HD-EPIC exact-release repair | Acquire licensed | `V+S+A`, far/multi | `REPAIR` |
| 9 | MECCANO exact-release repair | Acquire licensed | independent procedural far/multi | `REPAIR` |
| 10 | Rights-first public field/mission assets | Public exact asset | far/multi reserve | `REPAIR`; weak HF/LVB/VES routes `NO_GO` |

The machine-readable companion ranks these routes and gives explicit evidence
conditions for `GO`, `REPAIR`, and `NO_GO`.

## 8. Final boundary

This task performed local artifact inspection and prospective planning only.
It did not listen to media, perform human semantic validation, obtain new
access, verify new rights, download media, accept an SES, assign H1/H2, or
authorize pilot execution or release.

`PILOT_V5_TARGETED_PROSPECTING_READY`
