# Pilot-0 report outline

**Working title:**  
**AV-TRACE Pilot-0: Construct Validation for Matched Evidence Blocking and
Restoration in Long-Video Agents**

This is a pilot report outline, not a promised leaderboard paper.

## 1. Claim hierarchy

### Primary claim

AV-TRACE can instantiate matched, replayable long-video episode triplets that
separately measure insufficiency recognition, access-failure diagnosis,
search-policy response, and grounded recovery.

### Supporting claims

1. Necessity-group annotations and all accepted minimal SESs can be validated
   with acceptable human agreement.
2. `BLOCKED` states remove all accepted routes without changing the latent
   question or unrelated backend behavior.
3. `RESTORED` states reverse exactly the block and permit supported recovery.
4. The fixed protocol yields complete, replayable trajectories and interpretable
   cost measurements.
5. Descriptive system differences motivate or fail to motivate a larger powered
   study.

### Claims not approved

- “first,” “unique,” or priority equivalents;
- confirmatory model ranking or ranking inversion;
- broad factorial coverage;
- counterfactual answer replacement;
- general source-absence competence;
- public-core conclusions pooled with external compatibility results.

## 2. Paper/report structure

1. **Introduction:** static success does not reveal behavior under access
   failure and restoration.
2. **Related work:** directly compare LongVidSearch, FLARE, V-RAGBench,
   LongShOTBench, MOV-Bench, VideoGAIA, REVEAL, TRACE/VES-Bench, HERBench, and
   OmniHalluc-L. Describe REVEAL as a method and distinguish ordinary iterative
   retrieval from imposed-failure recovery. Complete a dated later-work audit
   before submission.
3. **Protocol:** one fixed graph and exactly `CLEAN`, `BLOCKED`, `RESTORED`;
   necessity groups; two mechanisms; deterministic restoration.
4. **Rights-cleared public core:** 20–30 videos, 60 families, rights and
   provenance controls. Put external compatibility in a separate section/table.
5. **Schemas and replay:** normative action, response, final, episode, manifest,
   and trajectory contracts plus semantic validation.
6. **Construct validation:** human agreement, alternative-SES discovery,
   necessity validity, pair isolation, restoration feasibility, shortcut tests.
7. **Descriptive system study:** four frozen systems and the primary metric
   dashboard, with video-cluster intervals.
8. **Cost and feasibility:** measured annotation labor, core/diagnostic runs,
   storage, completion, and replay.
9. **Decision:** scale, revise, or stop each construct independently.
10. **Limitations and ethics:** pilot size, rights scope, public-video
    contamination, modality coverage, and API volatility.

## 3. Required figures

1. One family with `CLEAN`/`BLOCKED`/`RESTORED` and the exact state diff.
2. Claim–hop–evidence graph with alternative SESs and a necessity group.
3. Rights/provenance and validation pipeline.
4. Construct-validity funnel: candidates, accepted SESs/groups, families, and
   rejection reasons.
5. Outcome dashboard with video-cluster intervals.
6. Restoration trajectories and cost from trigger to supported finalization.

## 4. Required tables

1. Conservative related-work capability matrix with dated verification.
2. Public-core composition and rights status.
3. Annotation agreement and semantic-validator failures.
4. Four-system dashboard; no weighted composite.
5. Core and non-core run manifest and measured cost.
6. Separate, unpooled compatibility results if executed.

## 5. Interpretation rule

Pilot-0 succeeds when the constructs are valid, interventions isolated,
restoration usable, traces replayable, and observed uncertainty/cost justify a
larger study. A ranking inversion is optional descriptive evidence and never a
success criterion.

