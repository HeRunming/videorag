# CVPR pivot review: data and construct validity

**Review date:** 2026-09-22  
**Decision:** `PIVOT_TO_BOUNDED_HUMAN_CONSTRUCT_WORK_NOW; DO_NOT_YET_COMMIT_TO_FULL_60-H2 PRODUCTION`

## 1. Scope and evidence boundary

This review uses the Task-108 protocol and plan, the frozen thesis/claim
ledger, the CVPR execution blueprint and pre-submission risk register, current
non-restricted real-A/V status documents, the rights register, and only the
safe aggregate Task-120/Task-121 reports. It does **not** inspect restricted
per-case labels, evaluator keys, or hidden evaluation content.

No human validation is claimed here. As of this review:

- human-reviewed families: **0**;
- H1 families: **0**;
- H2 families: **0**;
- current scored evidence: five machine-provisional retained families from
  three family-bearing NOAA videos;
- current real-A/V contribution: strong engineering infrastructure and a
  low-N learned-retrieval diagnostic, not a validated benchmark;
- controller-v2 sealed holdout: `NO_GO`;
- controller-v3 development: `NO_GO`, despite improved action syntax and
  action correctness, because joint state and terminal competence remain far
  below the frozen gates.

The numerical recommendations below are prospective design and labor-planning
targets, not completed observations.

## 2. Reviewer conclusion

### 2.1 Should AV-TRACE spend effort on human-valid SES, necessity, and source-disjoint data now?

**Yes, but as a staged scientific pivot rather than immediate bulk
annotation.**

Human construct validity is now the highest-value unresolved data question.
The central paper claims require reviewers to establish all accepted minimal
sufficient evidence sets (SESs), necessity groups, modality counterfactuals,
and isolated `CLEAN`/`BLOCKED`/`RESTORED` interventions. More machine
provisional families or more retrieval runs cannot substitute for this.

However, AV-TRACE should **not** immediately launch 60-H2 production:

1. The 8–12-family human protocol has never been executed, so candidate yield,
   alternative-SES discovery, reviewer agreement, rights throughput, and labor
   are unknown.
2. The current learned controller is not ready for the end-to-end thesis.
   Task 120 produced zero exact states and zero correct terminals on its sealed
   holdout; Task 121 remained at zero joint exact states and one correct
   terminal out of eight on consumed development data.
3. The current family-bearing sources are concentrated in NOAA and have
   already informed engineering and policy development. They are appropriate
   for construct debugging and development, but not for the final untouched
   test split.
4. Rights and public-release status remain item-specific. Government or public
   availability is not sufficient evidence of redistribution authority.

The correct near-term allocation is therefore:

- execute a **12-family / 6-source human mini-pilot** now;
- in parallel, resolve rights and technical feasibility for a broader
  source pool and continue learned-controller repair on synthetic/development
  data;
- authorize 60-H2 production only after the mini-pilot, learned competence,
  and H2 end-to-end mini-diagnostic gates pass.

This is not a recommendation to wait for a perfect controller before learning
whether the benchmark construct is viable. It is a recommendation to acquire
the minimum human evidence needed to decide whether further controller and
corpus investment is scientifically justified.

## 3. Scale options

| Option | Proposed scale | What it can establish | What it cannot establish | Planning labor |
|---|---|---|---|---:|
| **Immediate mini-pilot** | 12 completed families, 6 source groups, 5 required roles plus an independent alternative-search saturation audit | Whether questions, SESs, necessity groups, modality labels, pair isolation, forms, rights flow, and reviewer labor are workable | Population precision, model ranking, domain generalization, or a final benchmark claim | Approximately **100–220 person-hours** including training, source preparation, review, adjudication, and reporting |
| **Minimum CVPR-main corpus** | 60 H2 families, at least 20 rights-cleared source groups, source-disjoint 24/12/24 family split | A credible lower-bound main study with video-clustered inference and frozen held-out evaluation, if learned-system and diagnostic gates also pass | Broad domain representativeness or fine-grained per-modality claims with narrow uncertainty | Approximately **680–1,480 person-hours**, excluding counsel delays and model experiments |
| **Larger benchmark** | 120–180 H2 families, 40–60 source groups, at least 5 content domains | More stable source-level effects, credible leave-domain-out analyses, better modality/mechanism estimates, and reserves for withdrawal | Universal long-video generalization | Approximately **1,350–3,000 person-hours** for 120 H2; more for 180 |

The mini-pilot is a **governance and construct experiment**. The 60-H2 design
is the minimum credible CVPR-main target already implied by the blueprint, not
a statistically luxurious benchmark. A larger benchmark should be pursued
only if the 60-family study is feasible and the main empirical effect is
scientifically real.

For orientation, a simple binomial proportion at the worst-case value of 0.5
has an approximate Wilson 95% half-width of 25 percentage points at 12
families, 12 points at 60, and 9 points at 120. Model-effect uncertainty will
be wider because the correct independent unit is the source group: 6, 20, and
40 sources respectively. Therefore:

- 12 families are descriptive only;
- 60 families over 20 sources can support moderate or large paired effects but
  should not be advertised as broad representativeness;
- 120 or more families over at least 40 sources are preferable for stable
  stratum and domain analyses.

No power claim should be made before the mini-pilot supplies source-level
variance and intracluster-correlation estimates.

## 4. Immediate 12-family mini-pilot

### 4.1 Sampling unit and source rules

Use **12 completed families from exactly 6 source groups**, targeting two
families per source. A source group is the earliest verified underlying media
asset and includes mirrors, excerpts, alternate encodings, transcript
variants, and near-duplicate edits.

For a stronger source-diversity diagnostic than the bare Task-108 minimum:

- include at least **3 content domains**, with at least **2 source groups per
  domain**;
- include no more than **4 gate-defining families from 2 current NOAA source
  groups**;
- obtain the other **8 families from 4 new source groups in at least 2
  non-NOAA domains**;
- treat the remaining current NOAA families, if reviewed, as an additional
  development/stress subset rather than using them to satisfy domain balance;
- prohibit all current NOAA source groups from the future primary test split,
  because they have already influenced family construction, retrieval,
  controller, metric, and repair work.

Suitable domain categories should be declared before selection rather than
inferred after acceptance. A feasible first set is:

1. expert explanation or public-information presentation;
2. instructional, procedural, or field demonstration;
3. observational event, wildlife/environment, museum, or industrial process.

Prefer low-privacy institutional or owner-controlled material. Do not add
egocentric/home, minors, copyrighted music, or sensitive-event footage merely
to increase apparent diversity.

### 4.2 Candidate-stratum targets

These are **candidate hypotheses** until H2 adjudication. A failed necessity
test changes the label or rejects the family; it is never repaired by forcing
the intended stratum.

| Dimension | Twelve-family target |
|---|---|
| Modality/route | 2 vision-dominant; 2 speech-dominant; 2 ambient-dominant; 2 V+S; 2 V+A or S+A, including at least one ambient combination; 2 V+S+A |
| Intervention | 6 necessity-group withholding; 6 modality-channel outage |
| Reasoning | 6 one-hop; 6 multi-hop |
| Temporal structure | 6 near/local; 6 far/separated |
| Alternative-support risk | At least 6 high-risk cases: repeated statements, cross-modal substitutes, learned/control ranking disagreements, or uncertain minimality |
| Controls | At least 2 deterministically selected low-risk controls |
| Failure enrichment | Include available correct-answer/wrong-citation and machine-disagreement cases, without replacing the random controls |

The mini-pilot passes a modality stratum only when a family remains accepted
after full-source alternative search and the relevant modality-drop
counterfactual. If no ambient or V+S+A candidate survives, report that stratum
as failed or infeasible; do not impute coverage from routing behavior.

### 4.3 Human roles and independence

Retain the five Task-108 identities for every family:

1. question/claim author or independent verifier;
2. blind full-source alternative-evidence finder;
3. validator A;
4. validator B;
5. adjudicator.

Add a sixth role for this pilot:

6. **blind saturation auditor**, who receives the source and frozen question
   after initial adjudication but not the accepted SES ledger. The auditor
   attempts to find a new sufficient route. Any accepted new route reopens the
   family, recomputes necessity groups, and reruns pair isolation.

At least six trained reviewers are therefore needed, although roles may rotate
across families. No person may hold two roles on the same family. Use two
practice/calibration families that are excluded from every reported
denominator. Calibration may clarify instructions but must not expose
evaluation-family preferred evidence.

### 4.4 Alternative-SES search procedure

Alternative-support search is the most important construct-validity operation.
For every family:

1. **Blind chronological coverage.** The finder receives the full source and
   question, but no preferred evidence, machine tier, confidence, model rank,
   or proposed SES. The coverage log must span the complete source in source
   time, with no unlogged gap over the Task-108 one-second tolerance.
2. **Independent route construction.** Record every plausible answer route as
   atomic claims, exact intervals, modality, and derivation lineage. Repeated
   statements, captions, OCR, ASR, subtitles, summaries, descriptions, and
   co-timed cross-modal evidence must be marked as duplicate, derived, or
   genuinely distinct routes.
3. **Retrieval-assisted challenge.** After the blind pass, search with lexical
   and frozen learned retrieval over the complete timeline. Inspect apparent
   false positives and control-only/learned-only hits rather than assuming
   they are irrelevant.
4. **Unblind and reconcile.** Compare the independent routes with the proposed
   evidence graph. Register all sufficient alternatives, including those that
   invalidate the preferred route's claimed necessity.
5. **Leave-one-evidence-out tests.** Remove each SES member in turn. A set is
   minimal only when every removal breaks at least one target claim.
6. **Necessity recomputation.** A necessity group must intersect every accepted
   SES for its target claims. Individual evidence is not necessary merely
   because it appears in one preferred SES.
7. **Derived-route closure.** Apply the block to direct and derived
   representations, including transcript, captions, OCR, labels, cached
   descriptions, metadata, and temporally bound substitutes.
8. **Blind saturation audit.** A new reviewer searches for an unregistered
   sufficient route. Any discovery prevents freeze until the graph and all
   C/B/R states are rebuilt and revalidated.

Required outputs are inspected-time coverage, search queries, candidate
intervals, accepted/rejected route reasons, SES membership, leave-one-out
results, necessity hitting sets, modality drops, saturation outcome, and
active minutes. “No alternative found” is acceptable only with complete logs.

### 4.5 Mini-pilot statistics

Report the full funnel:

```text
sampled
  -> all independent forms complete
  -> H1
  -> adjudicated
  -> saturation-audited
  -> H2 / repair / reject / governance hold
```

Required statistics:

- H1 and H2 yield, overall and by starting P tier, with Wilson 95% intervals;
- validator A/B raw agreement and Cohen's kappa for critical categorical
  labels; use raw agreement and the disagreement table when kappa is unstable;
- temporal IoU and median/90th-percentile absolute boundary error;
- evidence- and SES-set Jaccard/F1;
- alternative-SES discovery by the first finder, by retrieval-assisted review,
  and by the final saturation auditor;
- leave-one-out minimality and necessity-group pass rates;
- modality-label survival after counterfactual review;
- pair-isolation, derived-leak, restoration-feasibility, and no-trigger failure
  rates;
- question-only and metadata-only shortcut rates;
- rights/privacy/safety hold rates;
- active time by role, source duration, modality, and outcome;
- reasons for every repair and rejection.

Do not run or report null-hypothesis significance tests for this pilot. Every
result must carry `LOW_N_MINI_PILOT_DESCRIPTIVE_ONLY`.

### 4.6 Mini-pilot decision

Apply the frozen Task-108 decision first:

- **GO:** 8–12 complete families from at least five source groups; every role
  complete; H1 yield at least 75%; H2 yield at least 60%; pair-isolation
  failure at most 10%; no unresolved critical governance hold; and no
  systematic minimality/modality failure above 25%.
- **REPAIR:** at least 40% reach H1 or failures are localized to repairable
  wording, interval, route, role, or form defects.
- **NO-GO:** fewer than 40% reach H1, at least half are rejected, or systematic
  alternative-support, necessity, isolation, or governance failures undermine
  the construct.

Add the following **scale authorization conditions**. A protocol-level GO does
not by itself authorize 60-H2 production:

- at least two accepted source groups are outside the current NOAA development
  lineage;
- at least one ambient and one V+S+A candidate reaches H2, otherwise those
  claims are removed or another pilot is run;
- the saturation auditor finds no new unblocked route, or all discoveries are
  repaired and re-audited;
- the observed labor and H2 yield imply a feasible route to 60 H2 without
  weakening acceptance criteria;
- no critical rights decision remains `unknown_hold`.

## 5. Minimum credible CVPR-main target: 60 H2

### 5.1 Production funnel

Sixty is the number of **accepted H2 families**, not the number sent to
review. At plausible H2 yields:

- 75% yield requires about 80 completed reviews;
- 70% yield requires about 86;
- 60% yield requires 100.

Accordingly, build **120–160 P-tier candidates from 30–40 source groups**,
conduct a frozen first-wave review of 40, and continue to approximately
80–100 completed human reviews only if the measured yield, rights throughput,
and labor remain acceptable. Preserve all rejected and repaired candidates.

After the first 40 reviews, require:

- observed H2 yield at least 60%, or a documented localized repair that is
  rerun under a new protocol version;
- no evidence that acceptance requires weakening SES, necessity, modality, or
  pair-isolation rules;
- no high-risk stratum represented by fewer than five completed reviews;
- a measured source-preparation and annotation budget that fits the remaining
  schedule;
- a credible rights-cleared reserve of at least 25% beyond the 20 sources
  required for freeze.

### 5.2 Frozen corpus composition

| Dimension | Minimum 60-H2 requirement |
|---|---|
| Source groups | At least 20; target 3 H2 families/source; hard operational cap 4/source |
| Content domains | At least 4, with at least 5 source groups and 12 H2 families per domain |
| Producers/collections | At least 5 independent producers or collections; no collection should supply more than 25% of H2 families |
| Primary modality strata | 15 vision; 15 speech; 15 ambient; 15 jointly cross-modal |
| Cross-modal subcoverage | Within the 15: at least 4 V+S, 4 V+A, 3 S+A, and 4 V+S+A |
| Intervention mechanisms | Target 30 withholding and 30 channel-outage; never fewer than 24 of either |
| Reasoning complexity | Target 30 one-hop and 30 multi-hop |
| Temporal structure | Target 30 near/local and 30 far/separated |
| Alternative-support stress | At least 20 reviewed high-risk candidates; at least 10 accepted multi-SES H2 families across 5 sources for a confirmatory alternative-SES sensitivity analysis |
| Random controls | At least 20% of each review wave selected as deterministic low-risk controls |

These are composition constraints, not permission to relabel failed families.
If a stratum cannot be filled under unchanged H2 rules, narrow the paper claim
or acquire more sources.

The minimum source-disjoint split remains:

| Split | Source groups | H2 families | Use |
|---|---:|---:|---|
| Development/train | 8 | 24 | Prompt and policy development; optional learned fusion training |
| Validation | 4 | 12 | Calibration and one-time design freeze |
| Test | 8 | 24 | Locked primary evaluation only |

Assign whole source groups. Current NOAA and every source used in controller,
retrieval, metric, or prompt development belong only in development or a
separate historical diagnostic set. Rejected candidates from test sources
remain test-private and cannot become training negatives. Every transcript,
clip, embedding, query paraphrase, alternative SES, and derivative inherits
the source split.

### 5.3 Statistical analysis at 60 H2

- The causal unit is the matched family; the resampling unit is the source
  group.
- Compute episode outcomes, then within-family state contrasts, then average
  families within source, then resample sources.
- Use at least 10,000 source-cluster bootstrap replicates for 95% intervals.
- Report paired absolute risk differences first and a source-level
  randomization/permutation analysis where feasible.
- Apply Holm correction only to frozen primary learned-controller contrasts;
  label BH-corrected secondary work exploratory.
- Report leave-one-source-out and leave-one-domain-out sensitivity.
- Do not claim a modality or domain effect unless at least five independent
  source groups contribute to that estimate.
- Report intention-to-evaluate results with invalid runs counted as endpoint
  failures, plus a valid-run-only sensitivity.
- Do not choose the final sample size from observed favorable model effects.
  Use mini-pilot variance and an effect-size grid to simulate source-cluster
  precision before corpus freeze.

Twenty source groups are a lower bound. If the principal result changes sign
when one source is removed, is supported by one domain, or has intervals too
wide to distinguish the frozen practical margins, acquire more sources before
submission.

## 6. Rights, privacy, and release plan

Rights work must precede expensive annotation and remain separate from
scientific acceptance.

### 6.1 Per-source gates

For every exact asset and rendition, record:

1. canonical source and source-group lineage;
2. acquisition authority and approved route;
3. processing authority for decoding, transcription, feature extraction, and
   temporary derivatives;
4. separate decisions for raw media, clips, transcripts, annotations,
   embeddings/features, and evaluator release;
5. license/grant version, dated evidence snapshot, rightsholder or licensor,
   attribution, share-alike, and commercial-use conditions;
6. faces, voices, minors, bystanders, private spaces, precise locations,
   sensitive content, music, marks, and third-party components;
7. retention, access control, takedown, withdrawal, deletion, quarantine, and
   replacement policy;
8. content hash, duration, streams, time base, and source-edit checks.

An accessible URL, public agency provenance, repository license, or benchmark
card is not sufficient. Any applicable `unknown_hold` blocks H2 freeze for the
intended use.

### 6.2 Release tracks

- **Public/reconstructable core:** prioritize item-level verified NASA, NOAA,
  NARA, Wikimedia, or direct owner-granted sources with lawful stable access
  and releaseable annotations/evaluator artifacts. Prefer all 20 primary
  sources in this track.
- **Restricted compatibility track:** gated datasets may be used only under
  their agreements, with separate storage and unpooled reporting. They cannot
  satisfy a public-core claim.
- **ID-only track:** use only when source access, annotation release, and
  reproducibility are affirmatively permitted; provide hashes, versioned
  source IDs, integrity checks, and replacement policy.
- **Reject:** unknown rights, prohibited acquisition, unverifiable source
  lineage, unmitigated sensitive personal data, or embedded third-party media
  that cannot be separated.

All 60 primary families must permit release of the benchmark annotations,
schemas, split metadata, evaluation code, and required attribution. If raw
media cannot be redistributed, the paper and release must say so explicitly.
If a substantial fraction of the primary test set is restricted or
non-reconstructable, describe the contribution as a restricted evaluation
corpus, not a release-ready public benchmark.

Before submission, produce an asset-level rights manifest, release bill of
materials, attribution file, privacy review, and tested takedown/replacement
procedure. Public and restricted build pipelines must be physically and
logically separate.

## 7. Labor and staffing assumptions

Use the mini-pilot to replace these planning ranges with observed medians and
90th percentiles.

### 7.1 Per reviewed family

| Work item | Planning range |
|---|---:|
| Question/claim verification | 0.75–1.25 h |
| Blind full-source alternative search | 1.5–3.0 h |
| Validator A | 1.0–1.5 h |
| Validator B | 1.0–1.5 h |
| Adjudication | 0.75–1.25 h |
| Blind saturation audit | 0.75–1.5 h |
| Coordinator/import/QA | 0.3–0.5 h |
| **Total** | **6.0–10.5 h/family** |

Longer, repetitive, ambient-heavy, or multi-SES sources may exceed this range.
Record active and elapsed time separately.

### 7.2 Program totals

- **12-family mini-pilot:** 72–126 direct family-review hours, 15–25 hours of
  training/calibration, 24–60 hours of source rights/technical preparation,
  and 10–20 hours of coordination/reporting: approximately **100–220
  person-hours**.
- **60 accepted H2:** assuming 80–100 completed reviews, approximately
  **480–1,050 direct annotation hours**, plus 100–240 hours of source
  rights/technical work and 15% coordination/rework: approximately
  **680–1,480 person-hours** or roughly **4–9 full-time person-months** at 160
  hours/month.
- **120 accepted H2:** assuming 160–200 completed reviews, approximately
  **1,350–3,000 person-hours**, or roughly **8.5–19 person-months**.

These totals exclude institutional counsel delays, model inference, storage,
and engineering. A practical 60-H2 team is 8–12 trained annotators with role
rotation, at least two adjudicators, one annotation lead, one rights/privacy
lead, and data/QA support.

## 8. Gates and recommended execution order

### Gate A — `MINI_PILOT_INPUT_READY`

Require 12 eligible candidate families, 6 source groups, source hashes and
lineage, approved processing/annotation rights, complete media, frozen forms
and sampling seed, named independent reviewers, and two excluded calibration
families.

### Gate B — `CONSTRUCT_VALIDITY_MINI_PILOT_GO`

Apply the Task-108 thresholds plus the diversity and saturation conditions in
Section 4.6. Failure yields `REPAIR` or `NO_GO`, not a smaller gold claim.

### Gate C — `LEARNED_CONTROLLER_READY`

The current status is `NO_GO`. Before using H2 data for the end-to-end thesis,
an unseen, non-evaluation-family competence suite must meet the frozen
requirements, including:

- 100% syntax on required state heads;
- at least 75% on every semantic state head;
- at least 50% joint exact state;
- at least 75% terminal correctness;
- at least 90% valid structured learned outputs after the one permitted repair;
- at least 80% supported-answer success on human-valid oracle-evidence cases;
- zero unsupported required claims.

Do not tune on the Task-120 holdout, restricted labels, future H2 test sources,
or adjudication rationales.

### Gate D — `END_TO_END_DIAGNOSTIC_GO`

Run learned single-shot, learned ReAct, and learned sufficiency control on the
accepted H2 mini-pilot families. Require a diagnostic separation across at
least three source groups, a nonzero answer-versus-supported-answer or citation
divergence, and at least one non-retrieval failure category not explained by
retrieval recall. Maintain no-trigger controls and common-endpoint restoration.

### Gate E — `DATA_SCALE_UP_GO`

Authorize full production only if Gates B–D pass and the first 40 scaled
reviews show acceptable H2 yield, rights throughput, labor, reviewer
agreement, and stratum coverage under unchanged rules.

### Gate F — `60_H2_CORPUS_FREEZE`

Require 60 H2 families, at least 20 source groups, the 8/4/8 source split,
complete rights decisions, no weakened construct criteria, private untouched
test sources, and a 25% source/family reserve for failed rights, withdrawal, or
late construct defects.

### Gate G — `PAPER_CLAIM_READY`

In addition to the data gate, require the full learned-system matrix, two
backbone families, source-cluster uncertainty, all preregistered ablations,
invalid-run accounting, independent metric/replay/leakage audits, and a
sentence-level claim ledger.

## 9. Final recommendation

1. **Fund and execute the 12-family / 6-source human mini-pilot immediately.**
   This is now more informative than another machine-provisional data expansion.
2. **Spend source-acquisition effort now only on rights-first diversification
   and reserves**, not on mass family annotation.
3. **Keep the current NOAA families in development/construct diagnosis.** Do
   not use their source groups as primary held-out test evidence.
4. **Repair learned-controller competence in parallel.** The Task-120 and
   Task-121 safe aggregates do not justify running the 60-family main
   experiment.
5. **Commit to the 60-H2 / 20-source corpus only after the construct and
   end-to-end mini gates pass.** This is the minimum credible CVPR-main data
   target, not evidence of broad representativeness.
6. **Prefer 120 H2 / 40 sources if the intended paper emphasizes benchmark
   generality, modality-specific findings, or domain robustness.** Otherwise,
   a carefully audited 60-H2 study with a compelling non-retrieval separation
   is the rational first submission target.

The project should therefore pivot toward human-valid data now, but the pivot
must be **quality-first, rights-first, and gate-limited**. Scaling before
alternative-SES saturation, human necessity validation, source quarantine, and
controller competence would convert the current scientific uncertainty into a
larger and more expensive uncertainty rather than a credible CVPR main result.
