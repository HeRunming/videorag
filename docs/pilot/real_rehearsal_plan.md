# Real-video rehearsal operations plan

**Version:** 1.1.0  
**Prepared:** 2026-09-07  
**Scope:** conditional selection and annotation-operations plan for 4–5 real videos
and 12 episode families  
**Authority:** `docs/project_charter.md`, `docs/decisions.md`,
`docs/spec/benchmark_v0.md`, `docs/spec/annotation_guideline_v0.md`, and
`docs/pilot/pilot_0_plan.md`

## 1. Operating posture

This package plans a real-media rehearsal but does not authorize media transfer,
content review, or annotation. Every row in
`data/rehearsal_plan/candidate_funnel.csv` is
`PROVISIONAL_NOT_APPROVED`.

The preferred inputs are existing official dataset releases, not ad hoc web
crawling:

- FLARE / Video-MME;
- LoVR / LongVidSearch;
- LongShOTBench / TraceAV-Bench / TRACE-VES-Bench where an official release,
  item identity, access route, and applicable rights can be pinned.

The Hugging Face reconciliation in `docs/data/hf_dataset_recon.md` and the
tables under `data/hf_recon/` were refreshed on 2026-09-07. The candidate
funnel now carries official release IDs and either observed item/revision
evidence or explicit `UNRESOLVED_*` codes. Short SHAs and file revisions remain
evidence leads, not freeze-grade revisions. No missing value may be inferred to
make a candidate appear complete.

Date convention for this package:

- 2026-09-05 is the normative design freeze;
- 2026-09-06 is the claims/evidence cutoff;
- 2026-09-07 is the live access-observation and planning date.

Later live observations reconcile metadata; they do not silently amend the
normative contract.

Existing NASA, NOAA, and Wikimedia candidates from
`data/rehearsal_review/shortlist.csv` are maintained only as fail-closed
substitutes. Their packets remain `unknown_hold`, with zero approved assets.

## 2. Rehearsal output

The rehearsal target is:

- **4–5 source-disjoint videos**;
- **exactly 12 candidate families** entering full authoring;
- **exactly three episode states per retained family:** `CLEAN`, `BLOCKED`,
  `RESTORED`;
- **both intervention mechanisms** represented;
- **vision, speech, ambient, and cross-modal** requirements planned;
- **one-hop and two-hop** requirements represented;
- **near and far temporal evidence** represented;
- **at least one accepted alternative SES** in the retained set.

This is a rehearsal-yield target, not an instruction to approve weak families.
If fewer than 12 families pass, the shortfall and rejection labor are reported;
rejected items are not relabeled as accepted to fill the matrix.

The slot plan is frozen in
`data/rehearsal_plan/family_slot_matrix.csv`. A selected video may carry at most
three slots. Therefore 12 retained families require at least four
source-disjoint videos; the allowed package size is four or five videos.
Modality coverage is a planned design target and is not achieved until
authorized stream inspection, human content classification, family authoring,
and acceptance all pass.

## 3. Candidate funnel

### Stage 0 — dataset reconciliation

**Input:** the 12 provisional rows in `candidate_funnel.csv`.

For each dataset-derived row, a data steward must record:

1. exact official dataset/repository locator;
2. immutable release revision, commit, or dataset revision;
3. release row/video/item ID;
4. upstream source dataset and source identifier;
5. metadata-backed duration;
6. declared media/audio availability;
7. observed official technical access route;
8. rights status, artifact-license scope, source-media rights, and intended
   episode publication class as separate values;
9. existing temporal or QA labels used only for triage;
10. parent asset and lineage relation;
11. complete-source availability and source-time join status;
12. duplicate checks, including the exact `checked_against_scope`.

Do not reuse a benchmark question or annotation as AV-TRACE ground truth. Existing
labels may identify likely evidence-rich videos, but AV-TRACE questions, claims,
evidence units, SESs, necessity groups, and trajectories require independent
authoring and validation.

**Exit:** 8–12 candidates with exact released identities or explicit
reason-coded unresolved fields. A candidate is freeze-ready only when its full
immutable provider revision is resolved. The target mix before
technical review is:

| Source family | Target candidates | Purpose |
|---|---:|---|
| FLARE / Video-MME | 2–3 | Audio-only, visual, and hard-bimodal retrieval candidates |
| LoVR / LongVidSearch | 2–3 | Temporally distant and multi-hop candidates |
| LongShOT / TraceAV / TRACE | 3–4 | Multimodal QA, reasoning-chain, and jointly necessary evidence candidates |
| Existing official public-source pool | 0–3 reserves | Rights-cleared substitution path if dataset assets fail |

No source family is guaranteed a final slot. No two selected videos may be the
same underlying asset, alternate encode, excerpt, or close re-upload.

### Stage 1 — metadata-only technical/audio feasibility review

Before any rights decision or transfer request, triage the pinned official
dataset metadata and permitted annotation artifacts for:

- duration eligibility;
- declared audio or subtitle availability;
- likely speech, non-speech audio, visual, and cross-modal utility;
- existing temporal labels or evidence spans;
- likely near/far and one-/two-hop slot fit;
- duplicate, excerpt, and upstream-source relationships.

This stage does not play, probe, fetch, or inspect media. It records only a
feasibility hypothesis. Audio, speech, ambient, and cross-modal status stay
`unverified` unless an official text record states a limited source claim; such
claims are not technical verification.

**Exit:** 8–12 candidates recommended for rights/access review.

### Stage 2 — fail-closed rights/access review

Before transfer, the rights/access team determines whether the exact asset has:

- an authorized official acquisition method;
- an asset-level manifest that validates against
  `docs/data/acquisition_manifest_schema.json`;
- explicit acquisition, processing, derivative-release, annotation-release,
  transcript-release, and raw-media-release decisions;
- no applicable `unknown_hold`;
- an immutable authority/evidence snapshot;
- passed privacy, safety, likeness, music, marks, and embedded-component review.

Primary public-core rehearsal use requires all six named decisions to be
`allowed`. A dataset asset whose terms permit controlled research use but not
raw-media redistribution may be retained only as
`EXTERNAL_COMPATIBILITY_UNPOOLED`, with no implication that it can satisfy the
public-core quota.

**Exit:** an asset is `transfer_authorized`, `compatibility_only`, or rejected.
A merely accessible file is not authorized.

### Stage 3 — authorized technical and audio verification

Only after **Stage 2 / Gate A** records `transfer_authorized` for the exact
asset and rendition may the technical reviewer acquire or inspect bytes. The
reviewer records:

- exact probed duration;
- decodable video and audio streams;
- usable original audio;
- intelligible speech where required;
- non-speech acoustic content where required;
- timestamp stability and stream hashes;
- gross corruption, drift, missing sections, or duplicated segments;
- presence of at least two plausible evidence clusters;
- evidence-cluster separation needed by the assigned slot;
- obvious transcript-, title-, metadata-, or burned-in-text shortcuts.

The duration gate is **1,200–5,400 seconds inclusive**. For the selected 4–5
videos, prefer a median of at least 2,400 seconds; the Pilot-0 median target is
not waived, but a 4–5-video rehearsal may report a miss rather than distort
selection.

**Exit:** `technical_pass`, `technical_hold`, or rejection.

### Stage 4 — slot-fit review and provisional selection

The operations lead maps technically eligible videos to the 12 frozen family
slots. A slot assignment is a hypothesis until the blind source review and
necessity test pass.

Selection rules:

1. select 4–5 source-disjoint videos;
2. assign no more than three family slots per video;
3. select at least one video from each available preferred dataset family,
   unless rights/access or technical review blocks it;
4. avoid selecting more than two videos from the same upstream source family;
5. reserve at least one video with plausible non-speech audio;
6. reserve at least one source with evidence clusters at least 600 seconds apart;
7. do not count generated captions as proof of speech or ambient audio;
8. do not count a benchmark clip as a long-video source;
9. do not approve a candidate based on expected modality metadata alone.

**Exit:** 4–5 provisionally selected videos plus at least two slot-compatible
reserve candidates. Provisional selection does not equal family acceptance.

### Stage 5 — family authoring and validation

Each slot follows the normative lifecycle:

`draft → independent_review → necessity_test → adjudication → accepted → frozen`

Any state may move to `quarantined`. A return from quarantine requires a new
version and reason-coded audit entry.

For each slot:

1. the author performs a blind full-source review;
2. the author creates a structured question and atomic claims;
3. the author records source-time evidence units and controlled hops;
4. an alternative-evidence finder, blinded to the preferred SES before the first
   full-source pass, logs all plausible routes;
5. candidate SESs undergo satisfiability and leave-one-out minimality tests;
6. one necessity group is constructed over all accepted SESs;
7. `CLEAN`, `BLOCKED`, and exact `RESTORED` are built using one mechanism;
8. schema, semantic, pair-diff, and replay checks run;
9. validator A and validator B independently traverse all three states;
10. applicable shortcut audits run;
11. an adjudicator accepts, repairs under a new version, quarantines, or rejects.

Templates are:

- `data/rehearsal_plan/annotation_template.json`;
- `data/rehearsal_plan/reviewer_form.json`.

These are blank operations records, not substitute schemas. Frozen family and
trajectory objects still must validate against the normative JSON Schemas.

## 4. Assignment logic for the 12 slots

The matrix contains three slots per modality stratum:

| Stratum | Slots | One-hop | Two-hop |
|---|---:|---:|---:|
| Vision | 3 | 1 | 2 |
| Speech | 3 | 1 | 2 |
| Ambient | 3 | 2 | 1 |
| Cross-modal | 3 | 1 | 2 |
| **Total** | **12** | **5** | **7** |

It also contains:

- six `necessity_group_withholding` slots;
- six `modality_channel_outage` slots;
- six near slots with minimum evidence-cluster separation of 30 seconds;
- six far slots with minimum evidence-cluster separation of 600 seconds;
- eight slots that require at least one accepted alternative SES.

“Alternative SES required” means at least two accepted minimal SESs cover the
target claim set through genuinely distinct evidence routes. Duplicate
encodings, ASR plus transcript copies, alternate clips of the same observation,
or deterministic derivatives are not independent alternatives.

If an alternative-SES slot cannot support an exhaustively enumerated alternative
route, it is rejected or substituted; it may not be silently converted into a
no-alternative slot.

## 5. Roles and separation of duties

| Role | Responsibility | Independence rule |
|---|---|---|
| Operations lead | Owns schedule, slot balance, freeze decisions, and issue log | May not be sole adjudicator for a family authored by the lead |
| Dataset/recon steward | Pins release revisions, item IDs, upstream provenance, and duplicate relationships | Does not approve rights |
| Rights/access reviewer | Owns asset manifest, authority evidence, and six named decisions | Must be named and authorized by the institution |
| Privacy/safety reviewer | Reviews people, speech, sensitive content, and mitigations | Independent sign-off for elevated risk |
| Technical/audio reviewer | Probes only authorized bytes and records stream/audio/timestamp findings | Does not author the first question on the same source |
| Author | Writes question, claims, evidence units, and initial graph | Cannot validate or adjudicate the family |
| Alternative-evidence finder | Performs blind full-source search for other routes | Must not see the preferred SES before first pass |
| Validator A | Independently tests SESs and the three trajectories | Cannot be author or adjudicator |
| Validator B | Independently repeats validation | Cannot be author or adjudicator |
| Adjudicator | Resolves disagreement and owns accept/reject decision | Cannot be an author or validator of that family |
| Schema/replay operator | Runs structural, semantic, pair-diff, and replay checks | Reports failures without silent repair |
| Measurement coordinator | Aggregates labor, rejection, agreement, and yield metrics | Uses immutable submitted forms |

One person may hold multiple operational roles across different families, but
the per-family independence constraints are mandatory.

## 6. Two-week execution schedule

The schedule assumes all preconditions are met by the morning of Day 1:
institutionally approved reviewers are assigned; synthetic semantic validation
passes; and at least 8 candidate identities are pinned. Dates below are local
project dates in Asia/Shanghai.

| Day | Date | Main work | Owners | Required output / decision |
|---:|---|---|---|---|
| 1 | Mon 2026-09-14 | Kickoff; freeze forms, slot matrix, reason codes, role assignments; reconcile releases and run metadata-only technical/audio triage | Operations lead, recon steward, technical reviewer, schema operator | 8–12 pinned dataset candidate rows; no approvals inferred |
| 2 | Tue 2026-09-15 | Rights/access precheck and duplicate/upstream-source review | Rights reviewer, privacy reviewer, recon steward | Fail-closed manifest status for every row; rejected access paths logged |
| 3 | Wed 2026-09-16 | Complete Gate A decisions; authorize only eligible transfers through official routes | Rights reviewer, Gate A owner | Transfer-authorized set or no-go; compatibility labels fixed |
| 4 | Thu 2026-09-17 | Technical/video/audio probe of authorized assets | Technical reviewer, schema/replay operator | Duration, streams, audio, hashes, corruption and timestamp report |
| 5 | Fri 2026-09-18 | Slot-fit triage; choose 4–5 videos and reserves; source review begins | Operations lead, technical reviewer, authors | Provisional selected set and slot assignment |
| 6 | Mon 2026-09-21 | Question/claim/evidence drafting for FS-01–FS-06 | Authors | Six draft family records |
| 7 | Tue 2026-09-22 | Question/claim/evidence drafting for FS-07–FS-12; independent-review handoff | Authors, operations lead | Twelve drafts or reason-coded slot shortfall |
| 8 | Wed 2026-09-23 | Blind full-source alternative search; candidate SES enumeration | Alternative finders | Route logs, unresolved regions, candidate SESs |
| 9 | Thu 2026-09-24 | Leave-one-out SES tests; necessity groups; intervention construction | Authors, alternative finders, schema operator | Necessity-test package for each surviving slot |
| 10 | Fri 2026-09-25 | Validator A trajectories for `CLEAN`, `BLOCKED`, `RESTORED` | Validator A, trajectory operator | First independent trajectory set and failure log |
| 11 | Mon 2026-09-28 | Validator B trajectories; shortcut audits | Validator B, audit operator | Second trajectory set and audit results |
| 12 | Tue 2026-09-29 | Adjudication, repairs, substitutions for early hard failures | Adjudicator, operations lead, affected roles | Accepted/rejected/quarantined decisions; versioned repairs |
| 13 | Wed 2026-09-30 | Schema/semantic lint, pair-diff isolation, deterministic replay | Schema/replay operator | Machine-validation report and repair queue |
| 14 | Thu 2026-10-01 | Final adjudication; freeze rehearsal measurements; retrospective | Adjudicator, measurement coordinator, operations lead | Final 12-slot outcome, timing distributions, rejection/yield report, scale-up recommendation |

If Day 3 produces fewer than four authorized, slot-compatible videos, stop the
annotation schedule and execute source substitution. Do not compress rights or
technical review to preserve dates.

## 7. Source substitution policy

Substitution preserves the **slot contract**, not the source identity.

### Trigger conditions

Substitute when a candidate is:

- unavailable through an authorized official route;
- silent or missing a required audio stream;
- shorter than 1,200 seconds or longer than 5,400 seconds;
- technically corrupt, incomplete, or timestamp-unstable;
- legally restricted for the intended track;
- under an applicable `unknown_hold`;
- privacy/safety rejected;
- a duplicate, excerpt, or close re-upload of another selected source;
- unable to instantiate the assigned modality, hop, or temporal requirement;
- defeated by shortcut audit;
- unable to support credible exhaustive alternative search;
- unable to produce a valid necessity group;
- still sufficient in `BLOCKED`;
- not recoverable by two validator trajectories in `RESTORED`.

### Replacement order

1. another item from the same official dataset family, with a distinct underlying
   source video;
2. another preferred dataset family named for that slot;
3. a fail-closed official public-pool reserve with matching slot properties;
4. an additional asset-level-cleared official dataset candidate added through a
   versioned funnel amendment.

No fallback inherits approval. It starts at Stage 0 and passes every applicable
gate. A replacement must preserve:

- modality stratum;
- one- or two-hop requirement;
- near/far temporal class;
- intervention mechanism;
- alternative-SES requirement;
- track label;
- source-disjointness constraints.

Changing any of those fields requires a versioned matrix amendment approved by
the operations lead before annotation, not a convenience edit after validation.

The current public-pool review order is `cand-061`, `cand-056`, `cand-023`,
`cand-048`, then `cand-003`, using the existing review packets. Each remains
`unknown_hold`; this ordering is not clearance. If none passes, add a newly
identified official-dataset item through a versioned funnel amendment rather
than crawling the open web.

### Family-level substitution

If a specific question fails necessity validation but the source remains usable:

1. reject and retain the failed family record;
2. record all labor through rejection;
3. allow one fresh question attempt for the same slot on that source;
4. use a new `family_id` and version lineage;
5. assign a new alternative finder or preserve the original blinding protocol;
6. after a second construct failure on the same source/slot, substitute the
   source rather than iterating indefinitely.

## 8. Metrics collected

Each form records active minutes and waiting time. Aggregate:

- candidates entering each funnel stage;
- rejection count and reason by stage and source family;
- selected videos and accepted families per video;
- family yield per authorized video;
- source intake, rights, technical, authoring, graph, evidence, alternative
  search, necessity, intervention, validation, adjudication, lint, replay repair,
  and rejection labor;
- calendar latency and blocked-wait hours;
- number of candidate and accepted SESs per family;
- fraction with at least one alternative SES;
- necessity-group agreement;
- modality, hop-count, and temporal-span agreement;
- evidence-interval overlap between reviewers;
- validator agreement for each episode state;
- first-pass pair-isolation, schema, semantic, and replay rates;
- repair iterations and final disposition.

Report medians, interquartile ranges, minima, maxima, and denominators. With only
12 families, do not present unstable agreement estimates without their counts.

## 9. Stop conditions

Stop and escalate if:

- media is requested before Gate A;
- an official release cannot be pinned without guessing;
- a dataset access path requires generic scraping, cookie extraction, or an
  unapproved downloader;
- a reviewer is asked to approve their own family;
- the slot matrix can be filled only by weakening necessity or modality rules;
- the selected set has no credible ambient-audio source;
- semantic validation is unavailable;
- two independent validator trajectories cannot be recorded;
- any accepted family retains an `unknown_hold`.

The correct output in these cases is a measured no-go or partial-yield report,
not fabricated annotation or an implicitly approved candidate.
