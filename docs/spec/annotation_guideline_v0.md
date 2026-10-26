# Annotation and adjudication guideline v0.2

## 1. Purpose

Produce construct-valid `CLEAN`/`BLOCKED`/`RESTORED` families for Pilot-0.
No real content annotation starts until the asset has passed the fail-closed
manifest gate and the synthetic schema/semantic conformance suite passes.

## 2. Roles

Each family has independent:

- author;
- alternative-evidence finder;
- validator A;
- validator B;
- adjudicator.

No person may validate or adjudicate a family they authored. The
alternative-evidence finder must not see the author's preferred SES before the
first full-source search.

## 3. Status lifecycle

`draft → independent_review → necessity_test → adjudication → accepted → frozen`

`quarantined` is reachable from any state. Return from quarantine creates a new
version and a reason-coded audit entry.

## 4. Prerequisites

Before source review:

1. acquisition manifest validates;
2. gate is `annotation_approved`;
3. all six named rights decisions are explicit and none is `unknown_hold`;
4. privacy/safety and embedded-content review pass;
5. asset duration is 20–90 minutes with usable original audio;
6. source and stream hashes are frozen.

## 5. Authoring

Write a question whose primary answer is represented as atomic registered
claims. Natural language is display-only. Reject questions answerable from
title, metadata, common knowledge, or a prohibited modality.

Annotate evidence units in source time:

- `vision`: visual scene, action, object, or readable on-screen text;
- `speech`: spoken content represented by audio/ASR/subtitles;
- `ambient`: non-speech acoustic event.

Burned-in text is visual. ASR/subtitles are speech-derived, not independent
visual evidence.

## 6. Hops and support

Use only the controlled hop ontology in the episode schema. Every required claim
must have a complete support derivation. The support graph must be acyclic.

## 7. Exhaustive alternative search

The alternative-evidence finder reviews the full source and records every
plausible alternate route. Candidate SESs are accepted only when both validators
can use them to support their listed claims.

For each accepted SES:

1. demonstrate satisfiability;
2. remove each evidence member in turn;
3. confirm at least one listed required claim becomes unsupported;
4. reject strict supersets of another SES for the same claims.

If acceptable alternatives cannot be credibly enumerated, reject the item.

## 8. Necessity groups

Construct one to three groups. A valid group:

- targets required claims;
- contains substitutable evidence units;
- intersects every accepted SES for those claims;
- breaks all targeted support when every member is removed.

Do not call a unit individually necessary merely because it belongs to the first
SES found.

## 9. Family construction

### `CLEAN`

At least one accepted SES is reachable under the frozen backend and common
budget.

### `BLOCKED`

Use exactly one mechanism:

- withhold every member and derived leak of one necessity group; or
- disable one necessary modality/channel route.

No accepted SES may remain reachable. The source remains sufficient.

### `RESTORED`

Copy the `BLOCKED` start state exactly. Use a predeclared fixed-call or
`get_channel_status` trigger to reverse only the blocking operation. The budget,
tools, graph, question, costs, and unaffected outputs remain unchanged.

## 10. Validation

Both validators independently:

1. answer `CLEAN` with supported registered claims;
2. fail to support the blocked target in `BLOCKED`;
3. diagnose source evidence as present but inaccessible;
4. recover a supported answer in `RESTORED` within budget.

At least two validator trajectories must demonstrate restoration feasibility.

## 11. Anti-shortcut audits

Run, where applicable:

- question-only;
- metadata-only;
- transcript-only;
- silent-video;
- ambient-only;
- temporal shuffle;
- snippet-only;
- duplicate-evidence;
- contamination;
- intervention-artifact classification.

A failed critical audit sends the family to adjudication or quarantine.

## 12. Semantic and pair-diff validation

Run every rule in `semantic_validator_spec.md`. The validator must establish:

- temporal bounds and provenance;
- reference and DAG validity;
- SES satisfiability/minimality;
- necessity-group validity;
- intervention isolation;
- exact restoration;
- family consistency.

Schema validity alone never freezes a family.

## 13. Deferred annotation

Do not author Pilot-0 distractor insertion, ASR corruption, answer-flipping
replacement, broad budget stress, or source-absence states. Existing notes about
these concepts are research backlog only.

## 14. Rehearsal and quality reporting

Before production, complete a 12-family rehearsal and measure every role,
rejection, ablation, adjudication, and repair step. Freeze field-specific
agreement statistics and minimum denominators from that rehearsal.

Report:

- acceptance and rejection counts;
- SES and necessity-group agreement;
- temporal overlap;
- modality and hop agreement;
- family-state outcome agreement;
- adjudication reason codes;
- blind-audit errors;
- labor distributions.

