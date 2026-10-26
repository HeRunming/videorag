# Semantic A/V source-prescreen protocol

**Version:** `semantic-av-source-prescreen-v1`  
**Date:** 2026-09-23  
**Purpose:** fail-closed, pre-authoring human screen for future event-centric
or licensed A/V sources

## 1. Scope and non-claims

This protocol runs **after source rights, access, integrity, duration, and
native-stream checks** and **before question/family authoring**. It answers a
narrow question:

> Do source-uniform sampled intervals contain plausible semantic material
> that makes this source eligible for careful authoring, repair, or rejection?

It does not establish:

- a benchmark question or answer;
- sufficiency or minimality;
- necessity of an interval, route, channel, or modality;
- full-source absence of alternatives;
- H1 or H2;
- saturation;
- rights, release permission, or privacy clearance beyond the sampled human
  screen; or
- source-wide prevalence from sampled intervals.

The permitted terminal tokens are:

- `SEMANTIC_AV_SOURCE_PRESCREEN_READY`;
- `SEMANTIC_AV_SOURCE_PRESCREEN_REPAIR`; and
- `SEMANTIC_AV_SOURCE_PRESCREEN_NO_GO`.

`READY` means eligible to begin constrained authoring. It is not a construct
tier and confers no annotation, acquisition, evaluation, or release authority.

## 2. Inputs and prohibited leakage

The planner consumes a nonsemantic inventory containing only:

- source ID and source-group ID;
- source duration;
- source-content hash;
- an adapter reference; and
- explicit declarations that neither media nor semantic metadata is embedded.

Do not expose the planner to transcripts, OCR, captions, narrations, action or
sound labels, QA, evidence timestamps, family candidates, retrieval ranks, or
model-generated semantic labels. The generated sample plan contains only
source identity, hashes, time bounds, and adapter requests with
`extract_media=false`.

Media extraction remains adapter-only. The tools in this protocol neither
download nor decode media.

## 3. Deterministic source-uniform sampling

Use `tools/semantic_av_source_prescreen_plan.py`.

The frozen algorithm is
`source-uniform-temporal-bin-sha256-jitter-v1`:

1. sort sources by `source_id`;
2. allocate the requested total count as evenly as possible, so per-source
   counts differ by at most one;
3. choose which sources receive a remainder interval by SHA-256 ordering of
   `seed|quota|source_id`;
4. divide each source timeline into equal-width bins;
5. place one fixed-duration interval inside each bin using SHA-256 jitter from
   `seed|source_id|bin_index`; and
6. reject a source if the requested duration cannot fit without overlapping
   neighboring bins.

The same inventory bytes, IDs, seed, timestamp, sample count, and interval
duration produce the same plan and `plan_sha256`. The timestamp is an explicit
input rather than wall-clock state.

Example:

```bash
python tools/semantic_av_source_prescreen_plan.py \
  --inventory source_inventory.json \
  --plan-out prescreen_plan.json \
  --form-out prescreen_form.json \
  --plan-id semantic-prescreen-wave-01 \
  --form-id semantic-prescreen-wave-01-form \
  --created-at 2026-09-23T00:00:00+00:00 \
  --seed AVTRACE-SEMANTIC-PRESCREEN-WAVE-01 \
  --sample-count 36 \
  --interval-duration-s 20
```

## 4. Prescreener qualification and packet boundary

The prescreener must:

- be trained on this protocol and attest training in the form;
- inspect synchronized A/V for every assigned interval;
- use a stable pseudonymous reviewer ID;
- record start and completion timestamps; and
- understand that exposure to semantic source content permanently removes
  them from the two blind source-search roles for that source group.

The prescreener may later serve a nonblind role only if the governing
construct-validity assignment policy permits it. The prescreener cannot be
assigned as either:

- `blind_alternative_evidence_finder`; or
- `blind_post_adjudication_saturation_auditor`

for any family in the reviewed source group.

## 5. Required interval observations

For every sampled interval, record all of the following even when the answer
is “none”:

### 5.1 Dynamic non-text visual events

Record concrete visible state changes, object interactions, movements,
procedures, spatial relations, or outcomes that unfold over time. A valid
entry must be both:

- dynamic; and
- non-text.

Static slides, equations, title cards, subtitles, written labels, talking
heads without a relevant changing visual state, and OCR-only facts do not
qualify.

### 5.2 Concrete non-speech audio events

Record identifiable environmental, operational, mechanical, animal, impact,
alarm, or other concrete sound events. Generic room tone, music used only as
background, broad machine tags, and unspecified “noise” are insufficient.
Speech content belongs under speech presence, not this field.

### 5.3 Speech presence

Record `absent`, `possible`, or `present`. `unknown` is allowed only in a blank
or incomplete form and blocks import readiness.

### 5.4 Substitution risk

Independently assess whether a fact available in the interval may be
substituted by:

- transcript;
- OCR;
- caption; or
- narration.

Use `none`, `low`, or `high` and explain the assessment. `unknown` blocks a
completed import. A source may still pass with high risk only when explicit
authoring constraints prevent the risky route from defining the claimed
modality.

## 6. Candidate facts and modality carriers

Record candidate facts only after interval observation. For each fact:

- state the fact concretely;
- link the sampled intervals;
- state whether vision, non-speech audio, or speech carries it;
- link visual and non-speech carriers to observation IDs;
- link speech carriers to sample IDs;
- state whether the fact appears resistant to transcript/OCR/caption/narration
  substitution; and
- add an authoring caution.

These are **candidate facts**, not benchmark claims and not evidence of
necessity. A modality carrying a fact does not imply that another modality is
insufficient or unnecessary.

## 7. Temporal recurrence and duplicates

Across sampled intervals, record:

- recurring events;
- exact duplicates;
- near duplicates; and
- cross-modal recurrence.

State the authoring implication, such as duplicate-route risk, repeated
narration, visually repeated steps, or the need for a later full-source
alternative-evidence search. A sampled screen cannot certify that no duplicate
exists elsewhere in the source.

## 8. Privacy and safety

Assess privacy and safety separately. Record concerns, severity, and whether
each is unresolved, mitigated, or not applicable.

A source cannot pass while a high or critical sampled privacy/safety concern
is unresolved. This screen does not replace the project’s rights, privacy,
security, or release reviews.

## 9. Source decision

Choose exactly one source-level authoring decision:

### `pass`

Use only when:

- all intervals were reviewed;
- speech and substitution fields are resolved;
- recurrence, privacy, and safety were assessed;
- at least one concrete candidate fact is documented;
- no unresolved high/critical privacy or safety concern remains; and
- any high substitution risk has an explicit authoring constraint.

Import emits `SEMANTIC_AV_SOURCE_PRESCREEN_READY`.

### `repair`

Use when a plausible authoring path exists but a concrete repair is required.
At least one repair action is mandatory. Examples include selecting a
different continuous source asset, increasing sample coverage, resolving
caption substitution, or excluding a privacy-sensitive region.

Import emits `SEMANTIC_AV_SOURCE_PRESCREEN_REPAIR`.

### `no_go`

Use when the source should not enter authoring, for example because sampled
material is semantically unsuitable, dominated by substitutions, unsafe,
privacy-incompatible, or otherwise not repairable within the protocol.

Import emits `SEMANTIC_AV_SOURCE_PRESCREEN_NO_GO`.

If sources have mixed terminal decisions, the aggregate token is `REPAIR`.
The aggregate token is `NO_GO` only when every reviewed source is `no_go`.

## 10. Import, exposure ledger, and construct-ledger bridge

Run:

```bash
python tools/semantic_av_source_prescreen_import.py \
  --plan prescreen_plan.json \
  --form completed_prescreen_form.json \
  --report-out prescreen_import.json \
  --exposure-ledger-out prescreen_exposure_ledger.json
```

The importer validates plan binding, exact source/sample coverage, trained
reviewer identity, timestamps, all required semantic fields, candidate-fact
links, recurrence, privacy, safety, and decision-specific requirements. It
always reports:

```text
necessity_assigned=false
h1_assigned=false
h2_assigned=false
```

A completed valid form creates one exposure event per source group. The event
records source-content and candidate-semantic-fact exposure and permanently
declares both blind-role exclusions.

Before construct reviewer assignments are frozen, bridge the prescreen
exposure into:

- `coordinator/source_exposure_ledger.json`; and
- `coordinator/reviewer_assignments.json`.

Use the four optional construct-ledger arguments to the importer. The bridge:

1. refuses a frozen assignment ledger;
2. refuses a construct ledger with review events already present;
3. requires every reviewed source group in the construct packet;
4. appends a hash-chained `external_prior_work` event with
   `source_content` and conservative `preferred_evidence` exposure;
5. recomputes the pre-distribution snapshot hash; and
6. binds the draft assignment ledger to the new snapshot.

The existing construct-validity assignment freeze then rejects the
prescreener as a blind finder or saturation auditor for that source group.

## 11. Portable blank example

The checked-in example consists of:

- `data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_inventory.json`;
- `data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_plan.json`;
- `data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_form.json`;
- `data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_import.json`;
  and
- `data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_exposure_ledger.json`.

It contains no media, no semantic observations, no reviewer identity, no
authoring approval, no exposure events, and no H tier. Its expected import
token is `SEMANTIC_AV_SOURCE_PRESCREEN_REPAIR`.
