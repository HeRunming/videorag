# Pilot-0 execution plan

**Version:** 0.2.0 (2026-09-05)  
**Purpose:** construct validation and feasibility; not a leaderboard paper  
**Current operational state:** preflight only; media acquisition and content
annotation remain prohibited until their gates pass.

## 1. Frozen contract

### Target

- 20–30 rights-cleared, source-disjoint public-core videos;
- 60 base questions / episode families;
- exactly 3 episodes per family: `CLEAN`, `BLOCKED`, `RESTORED`;
- 180 core episodes per system;
- 4 systems initially;
- 720 core runs total.

The video count may vary within 20–30 because rights clearance and valid family
yield are uncertain. Sixty families and 180 episodes/system are fixed.

### Mechanisms

Each family uses exactly one:

1. `necessity_group_withholding`; or
2. `modality_channel_outage`.

Target at least 20 families per mechanism; freeze the final allocation before
model results. Families are analyzed in four preregistered requirement strata:
vision, speech, ambient, and cross-modal. These are reporting strata, not a
claim of complete factorial balance.

### Deferred

No Pilot-0 ASR corruption, distractor insertion, answer-flipping replacement,
broad budget stress, open-system evaluation, source-absence partition, or
ranking-inversion gate.

## 2. Rights-first source plan

Primary Pilot-0 conclusions use only
`PUBLIC_CORE_FIXED_BACKEND_TRIPLETS`.

Candidate source families are asset-cleared:

- NASA-authored official media;
- NARA records with an affirmative federal-work/public-domain basis;
- NOAA-authored official media;
- Wikimedia Commons files with pinned revision and verified source chain;
- direct creator/institution grants covering the intended use and release.

These are candidate families, not blanket clearance. Gated academic datasets and
existing web-derived benchmarks may appear only in
`EXTERNAL_COMPATIBILITY_UNPOOLED`.

No quota deficit authorizes crawling or generic platform downloading. Approved
methods are official direct download, official dataset tooling under recorded
terms, platform-authorized API/export, or rightsholder delivery.

### Pre-annotation asset gate

Every asset must:

1. validate against `acquisition_manifest_schema.json`;
2. record explicit acquisition, processing, derivative-release,
   annotation-release, transcript-release, and raw-media-release decisions;
3. have no applicable `unknown_hold`;
4. include exact authority and evidence snapshot hashes;
5. pass privacy/safety and embedded-component review; and
6. be 20–90 minutes with usable original audio.

Current cleared asset count remains **0** until real signed/reviewed records
exist. Planning documents do not clear media.

## 3. Annotation workflow

Roles must be independent:

- author;
- alternative-evidence finder;
- validator A;
- validator B;
- adjudicator.

Status transitions are:

`draft → independent_review → necessity_test → adjudication → accepted → frozen`

Any state may move to `quarantined`. A quarantined item can return only through a
reason-coded new version.

### Per-family steps

1. Blind full-source review.
2. Structured question and claim authoring.
3. Evidence units and controlled hops.
4. Independent full-source search for alternative support.
5. Enumerate every acceptable minimal SES.
6. Validate SES satisfiability and leave-one-out minimality.
7. Construct one necessity group that intersects every target SES.
8. Build `CLEAN`, `BLOCKED`, and exact `RESTORED`.
9. Run semantic validation and pair-diff isolation.
10. Two validators solve all three states.
11. Run question-only, metadata-only, transcript-only, silent-video,
    ambient-only, temporal-shuffle, snippet-only, duplicate-evidence,
    contamination, and intervention-artifact audits as applicable.
12. Adjudicate and freeze.

No content annotation begins before the synthetic conformance fixture and
semantic validator implementation pass.

## 4. Rehearsal and schedule

The old fixed seven-week/200-item schedule is retired. Before a production
schedule is approved, conduct a **12-family synthetic or fully cleared
rehearsal** and measure:

- rights review;
- source review and authoring;
- alternative search;
- two validations;
- necessity and modality ablations;
- adjudication;
- rejected-candidate cost;
- semantic lint and replay repair;
- preprocessing, storage, and run cost.

The observed distributions—not earlier per-item guesses—set the staffing,
schedule, storage, and contingency.

## 5. Systems and runs

Freeze four systems before execution. The intended diversity is:

1. strong direct/full-context configuration where feasible;
2. standardized retrieval agent;
3. transcript-first configuration without raw ambient-audio search;
4. audio-visual agent with separate V/S/A tools and explicit sufficiency state.

This list is provisional until model snapshots, prompts, decoding, seeds, retry
rules, and backend compatibility are recorded.

### Core run manifest

| Block | Count |
|---|---:|
| Families | 60 |
| States/family | 3 |
| Core episodes/system | 180 |
| Systems | 4 |
| **Core runs** | **720** |

Separately budget and report:

- synthetic canaries;
- invalid-run reserve;
- backend-fault reruns;
- any stochastic repeats;
- oracle-evidence diagnostics;
- mapper/judge audits;
- ablations.

None is silently included in the 720 count.

## 6. Outcomes

The primary output is the dashboard in `../spec/metrics_protocol.md`:

- grounded task success by state;
- insufficiency and access-failure calibration;
- premature stopping;
- search-policy response;
- paired restoration gain and recovery cost;
- Claim-Response Consistency;
- completion, replay, and resource cost.

No IDS, Intervention Utility, or weighted ranking score is used. Between-system
differences are descriptive. Video is the primary resampling cluster.

## 7. Construct-validation gates

Pilot-0 can support scale-up only if:

| Gate | Required evidence |
|---|---|
| Rights | Every selected public-core asset and released artifact has an affirmative applicable decision; no `unknown_hold`. |
| Schema | All family, action, response, final-output, trajectory, and rights objects validate. |
| Semantics | 100% of frozen families pass SES, necessity, provenance, family, intervention-isolation, and restoration rules. |
| Human validity | Both validators solve `CLEAN`, cannot support the blocked target in `BLOCKED`, and recover in `RESTORED`. |
| Pair isolation | At least 95% pass initially; all failures are repaired and revalidated before freeze. |
| Replay | At least 95% complete on first execution and 100% of retained runs replay exactly after approved reruns. |
| Construct signal | `CLEAN→BLOCKED` changes sufficiency/grounded behavior and `BLOCKED→RESTORED` produces usable restoration in enough families to estimate direction and uncertainty. No p-value or rank inversion is required. |
| Cost | Measured labor, compute, storage, and rerun reserve fit the approved scale-up scenario. |

A weak or imprecise effect leads to revise/expand, not a post-hoc claim. A
construct that validators cannot instantiate leads to no-go for that construct.

## 8. Statistics and future power

Family quantities are averaged within video; uncertainty bootstraps videos.
Pilot-0 estimates effect sizes, missingness, completion, and intraclass
correlation for simulation-based operating characteristics. A later
confirmatory study must predeclare:

- independent video count;
- effect sizes and ICC assumptions;
- missing-family and common-failure rates;
- one confirmatory endpoint and comparison set;
- practical tie/equivalence region;
- Holm correction for confirmatory pairwise tests.

Pilot-0 does not make a confirmatory model-ranking claim.

## 9. Change control

Changes to question, graph, SESs, necessity groups, intervention, backend,
rights decision, schema, prompt, model, or cost schedule create a new version.
Frozen objects are never silently patched. Public-core and compatibility results
remain separate in every report.

