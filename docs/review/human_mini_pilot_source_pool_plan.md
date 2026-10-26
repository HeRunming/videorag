# AV-TRACE human mini-pilot source-pool plan

**Date:** 2026-09-22  
**Decision:** `SOURCE_POOL_PLAN_READY`  
**State:** plan only; no media downloaded; no human review performed

## 1. Decision boundary

AV-TRACE has a concrete next candidate pool for the Task-108 construct-validity
mini-pilot:

- **12 candidate families from exactly 6 source groups**;
- **2 families per source group**;
- **4 new source groups in 4 non-NOAA domains**;
- **2 current NOAA source groups, capped at 4 families, as development only**;
- balanced targets of 6 necessity-withholding / 6 modality-outage, 6 one-hop /
  6 multi-hop, and 6 near / 6 far families;
- explicit ambient and `V+S+A` stress slots that must be rejected or replaced if
  genuine non-speech necessity is absent.

`SOURCE_POOL_PLAN_READY` means the pool is sufficiently concrete for
rights/metadata reconciliation and bounded stream preflight. It **does not**
authorize media acquisition, decoding, annotation, redistribution, H1, H2, or
benchmark release. All modality and family assignments remain hypotheses.

No restricted controller evaluator labels or hidden evaluator keys were read.
The current NOAA families were identified from the public planning registry and
existing non-controller status artifacts. No human validation is claimed.

## 2. Inputs and constraints applied

The plan follows:

- Task 108's tiered, fail-closed construct-validation protocol and its
  8–12-family / 5–6-source target;
- the 2026-09-22 pivot recommendation to run 12 families over 6 source groups,
  with no more than 4 gate-defining families from 2 current NOAA groups and 8
  families from 4 new groups in at least 2 non-NOAA domains;
- the current source inventory, candidate queue, rights register, source audit,
  candidate funnel, concrete pool, family-slot matrix, and human boundary;
- the project's exact-route and bounded-range preflight pattern: first-party
  route reconciliation, closed object allowlist, immutable identity fields,
  bounded in-memory container parsing, no full-object response, and separate
  acquisition/processing/release gates.

The full machine-readable specification, exact evidence URLs, preflight lists,
and fallbacks are in
`data/rehearsal_plan/human_mini_pilot_source_pool_plan.json`.

## 3. Frozen six-source pool

| Source group | Role | Domain | Duration | Access method now | Likely coverage | Rights / redistribution boundary | Exact next preflight | Fallback |
|---|---|---|---:|---|---|---|---|---|
| `SG-NOAA-049` — *Beach and Bay Safe* | Existing development source | Instructional/field safety | 41:05 local decoded source | Reuse existing restricted object; **do not redownload** | V, ambient, V+A; near/far; one/multi-hop | `unknown_hold`; restricted development only; no raw/clip/frame/audio/transcript release | Rebind local hash/duration; full-source chronology; speech-vs-ambient segmentation; minors/bystanders/music/components; derived-route and fingerprint checks | `SG-NOAA-052` or `cand-047`, development only |
| `SG-NOAA-052` — *Climate Alive! Wild Weather* | Existing development source | Expert public information/weather | 44:53 local decoded rendition | Reuse existing restricted object; **do not redownload** | S, V+S, possible V+S+A; strong separated sections | `unknown_hold`; partner visualizations, slides, broadcaster clips, music and likenesses remain held | Reconcile local/page duration lineage; speech/graphics chronology; OCR/caption/ASR route inventory; component/music/privacy and fingerprint checks | `cand-045`, development only |
| `SG-USGS-SHIFT-CURVES` — *Developing and Applying Shift Curves using GRSAT* | New primary candidate | Instructional/procedural field demonstration | 1:17:31 official page | Official USGS `Download Video`/`Download Transcript` route; not used yet | V, S, V+S; possible V+S+A through procedural/field cues | Official item says Public Domain; still audit third-party software/screens, marks, personal data and inserts; release remains artifact-specific | Archive page and public-domain statement; freeze exact official object; HEAD identity; bounded container range parse; transcript identity; later approved bounded semantic samples; full privacy/component and dedup audit | USGS Public Lecture *Six Eruptions…* or equivalent USGS public-domain procedural item |
| `SG-USGS-SIX-ERUPTIONS` — *Six Eruptions at Two Volcanoes Over the Past Three Years* | New primary candidate | Expert public information/volcanology | 55:55 official page | Official USGS `Download Video`/`Download Transcript` route; not used yet | S, V, V+S; possible eruption/environmental V+S+A; strong far/multi-hop | Official item says Public Domain; audit photographs, observatory/partner footage, maps, music, credits and audience content | Archive page and rights evidence; freeze exact object; HEAD plus bounded container parse; later approved speech/ambient sample; full-source components/privacy; alternative-route and dedup scan | USGS *Volcano Watchers* or *Unrest at Long Valley Caldera* after the same checks |
| `SG-NASA-PATHFINDERS` — *JPL and the Space Age: The Pathfinders* | New primary candidate, rights hold | Observational engineering/mission history | 1:00:00 official metadata | NASA+ or official NASA/JPL downloadable rendition only; never extract an embedded platform | V, S, V+S; possible mission/mechanical V+A or V+S+A; strong long arc | `unknown_hold`; NASA guidance is not an item license; audit JPL/Caltech, contractor/archive footage, score, marks and likenesses; no raw redistribution approved | Snapshot NASA+/NASA/JPL policies; locate first-party downloadable rendition; exact identity and bounded container parse; later approved semantic probe; shot/component ledger; dedup against mirrors | `cand-005` *Planetary Defenders*, then `cand-008`, under identical gates |
| `SG-COMMONS-BLOCKCHAIN` — *Abuse on the blockchain…* | New primary candidate, rights hold | Expert public lecture/technology policy | 1:00:56 official file page | Official Commons original-file route only after pageid/oldid/source/license pinning | S and V+S; local and separated lecture routes; likely useful control | `unknown_hold`; pin exact license/version, attribution/share-alike, uploader authority and source chain; audit slide screenshots, websites, logos, audience and sensitive examples | MediaWiki API page/revision/license/file identity capture; reject unexplained reupload; bounded WebM parse; TimedText provenance; later approved semantic sample; full component/privacy/dedup audit | `cand-059` *Before Vermont…*; avoid ceremony/music-heavy Commons fallbacks |

### Why USGS leads the new pool

The official USGS pages checked on 2026-09-22 provide unusually useful
preflight evidence in one place: exact displayed lengths, first-party video and
transcript download controls, and item-level `Public Domain` markings. USGS's
copyright policy still requires separating USGS-authored material from
non-USGS material. Thus these are high-priority, rights-conscious candidates,
not automatically release-cleared objects.

NASA and Commons are retained because they improve producer and domain
diversity, but they remain explicit holds until exact item/component authority
is established. If either cannot pass without ambiguity, substitute a rights-
clean institutional fallback; do not weaken the gate.

## 4. Twelve-family assignment

Every row is `HYPOTHESIS_NOT_AUTHORED_NOT_VALIDATED`.

| Slot | Source | Primary stratum / route | Hop | Span | Intervention | Purpose and fail-closed condition |
|---|---|---|---:|---|---|---|
| F01 | NOAA-049 | vision / V | 1 | near | necessity withholding | Local visible safety condition; speech/captions cannot answer; low-risk control |
| F02 | NOAA-049 | ambient / V+A | 2 | far | modality outage | Visible water state plus genuine surf/environment event; narration/music is not ambient evidence |
| F03 | NOAA-052 | speech / S | 1 | near | modality outage | Spoken weather proposition absent from printed graphics; low-risk control |
| F04 | NOAA-052 | cross-modal / V+S | 2 | far | necessity withholding | Earlier graphic plus later explanation; enrich wrong-citation/minimality risk |
| F05 | USGS Shift Curves | vision / V | 2 | far | necessity withholding | Early setup to later visible result; transcript-only route must fail |
| F06 | USGS Shift Curves | cross-modal / V+S+A | 1 | near | modality outage | Spoken instruction + visible action/state + genuine non-speech cue; reject if no semantic ambient cue |
| F07 | USGS Six Eruptions | speech / S | 2 | far | necessity withholding | Combine statements about separated eruption episodes; enumerate repetitions |
| F08 | USGS Six Eruptions | cross-modal / V+S+A | 1 | near | modality outage | Narration + eruption/map visual + genuine non-speech event; reject if sound is only speech/score |
| F09 | NASA Pathfinders | vision / V | 1 | near | necessity withholding | Local engineering state/change; narration/title cards must not answer |
| F10 | NASA Pathfinders | ambient / V+A | 2 | far | modality outage | Test/setup to later operation using genuine mission/mechanical sound; score is forbidden evidence |
| F11 | Commons lecture | speech / S | 1 | near | modality outage | Locally stated claim absent from slide text/metadata; low-risk control |
| F12 | Commons lecture | cross-modal / V+S | 2 | far | necessity withholding | Visual example plus separated spoken interpretation; audit slide and repetition substitutes |

Frozen totals:

- primary modality: **3 vision, 3 speech, 2 ambient, 4 cross-modal**;
- routes: **3 V, 3 S, 2 V+A, 2 V+S, 2 V+S+A**;
- interventions: **6 necessity-group withholding, 6 modality-channel outage**;
- reasoning: **6 one-hop, 6 multi-hop**;
- temporal: **6 near/local, 6 far/separated**;
- controls/risk: **3 low-risk controls, 9 risk-enriched**, including 2 ambient
  and 2 triple-modal stress candidates.

These quotas are selection targets, not permission to relabel a failed family.
A missing ambient cue or surviving unimodal route causes rejection/replacement.

## 5. Source-disjointness and split policy

A source group is the earliest verified underlying media asset. Mirrors,
excerpts, alternate encodings, subtitle/transcript variants, and near-duplicate
edits are one source group.

Before assignment, compare canonical IDs/URLs/titles/durations, exact hashes
when authorized, perceptual video/audio fingerprints, transcript overlap,
opening/closing slates, edit history, and cross-collection mirrors. Any
plausible collision collapses groups and replaces the lower-rights or
lower-modality candidate.

**Current NOAA is development-only.** The future primary test must exclude:

1. `SG-NOAA-049` and `SG-NOAA-052`;
2. every other current NOAA source group;
3. every source used for retrieval, controller, metric, prompt or protocol
   development; and
4. every derivative of those sources, including clips, transcripts,
   embeddings, questions, alternate SESs and repaired versions.

Future split assignment must occur by whole source group, before human H2
freeze. Rejected candidates from test sources remain test-private.

## 6. Exact preflight sequence — no download now

1. **Metadata/rights evidence:** archive first-party pages, policies, item IDs,
   displayed duration, source chain and exact date/hash.
2. **Route reconciliation:** identify only an official first-party or verified
   Commons-owner-controlled media route. Freeze HTTPS host, path, size, ETag or
   immutable revision/hash, Last-Modified where available, MIME and range
   capability. Do not fetch a media body.
3. **Bounded stream preflight:** use a closed allowlist and bounded in-memory
   range reader. Reject full-object `200`, complete-object ranges, redirects
   outside the allowlist, identity drift, missing synchronized video/audio, or
   duration outside **1,200–5,400 seconds**. Persist metadata only.
4. **Human authority gate:** named legal/rights, privacy/safety, custodian and
   annotation leads separately approve exact acquisition and exact processing.
5. **Later restricted acquisition:** a separate task may download only the
   approved exact rendition into restricted storage.
6. **Semantic A/V audit:** verify intelligible speech, genuine non-speech sound,
   synchronization, complete source, component boundaries and privacy.
7. **Family authoring:** author provisional P-tier families only after the
   source passes. Then run full-source alternative search, minimality,
   necessity, counterfactual and pair-isolation checks.
8. **Task-108 human pilot:** apply independent roles plus saturation audit;
   nothing is H1/H2 before import passes.

Immediate stop conditions include an unfrozen source route, out-of-range
runtime, absent synchronized A/V, absent required semantic modality, minors or
sensitive content that cannot be excluded, inseparable music/third-party
content, an unresolved acquisition-rights hold, duplicate/development leakage,
or inability to author two families without relaxing construct rules.

## 7. Go/no-go interpretation

**Decision: `SOURCE_POOL_PLAN_READY`.**

Rationale:

- exact six-source/twelve-family structure is specified;
- four new groups cover four non-NOAA domains and three producer/control
  lineages;
- the two USGS candidates have strong first-party, long-duration,
  public-domain-marked discovery evidence;
- NASA and Commons add diversity while remaining transparently held, with
  concrete fallbacks;
- each source has an access method, duration, modality hypothesis, family
  strata, rights/release boundary, exact preflight, and fallback;
- source-disjointness and future NOAA exclusion are explicit;
- no media acquisition or evaluator-label inspection occurred.

The next action is metadata/rights capture and bounded stream preflight—not
media download. Acquisition remains `NO_GO` until at least four new source
groups across at least two non-NOAA domains individually pass technical,
semantic, rights, privacy, custody and source-disjointness gates.
