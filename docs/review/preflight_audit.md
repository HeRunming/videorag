# AV-TRACE independent preflight audit

**Review date:** 2026-09-05  
**Scope:** `docs/research/`, `docs/data/`, `docs/spec/`, and `docs/pilot/`  
**Decision:** **NO-GO for media download, content annotation, or Pilot-0 model runs in the current state.** Metadata-only source discovery, rights-document collection, and synthetic protocol implementation may proceed.

This is a research, reproducibility, and risk review, not legal advice. Legal conclusions require institutional counsel. All factual checks below use primary-source paper/project/repository/dataset/policy pages; uncertain points are marked rather than inferred as fact.

## 1. Executive verdict

### What is viable

A narrow contribution survives:

> **AV-TRACE should test, within the same question and frozen claim–evidence graph, how an agent responds when a validated evidence route is blocked and then deterministically restored. The benchmark should separately measure insufficiency recognition, absence-versus-access diagnosis, policy change, grounded answer revision, and recovery cost.**

This is materially narrower than the current “factorial” framing. It is defensible as a **matched intervention protocol**, not yet as a verified first. Necessary evidence, audiovisual necessity, iterative retrieval, sufficiency checking, stopping, counterfactual video reasoning, evidence attribution, and tool-using video agents are all occupied by prior work.

### Why work must stop before acquisition/annotation

1. **No asset-level manifests exist.** The repository currently demonstrates zero assets with documented acquisition, processing, and release authority.
2. **The rights schema fails open.** Legally material fields may be null, and one status conflates copyright basis, access, processing, and redistribution.
3. **Pilot and normative specification disagree about the experimental unit.** The pilot assumes universal `C/I-/I+` triplets and individually necessary units; the spec defines many variants and necessity groups over multiple sufficient sets.
4. **The executable protocol is incomplete/internally invalid.** There is no action/final-output schema, the `finalize` example does not match the common envelope, an intervention example violates the episode schema, and JSON Schema cannot enforce core graph semantics.
5. **Primary metrics and leaderboard rules conflict.** Three different composite definitions coexist; recovery, modality diagnosis, budget curves, and clustering are not consistently estimable.
6. **The planned 60-question/15-video MFS is too small for the stated inferential gates.** It can debug constructs, not establish ranking inversions, interactions, or confirmatory lower-bound claims.
7. **The cost model omits required run blocks and substantial annotation labor.** The seven-week, 200-question plan is not credible until a measured rehearsal is complete.

The machine-readable conflict register contains 50 findings: [`cross_document_conflicts.csv`](cross_document_conflicts.csv).

## 2. Highest-impact factual verification

### 2.1 Core novelty comparators

| Work | Correct high-impact record for this preflight | Audit implication | Primary source |
|---|---|---|---|
| **LongVidSearch** | Agentic multi-hop evidence retrieval; official paper/repository report 3,000 questions over 447 videos, with 2/3/4-hop necessary evidence. Exact benchmark-controlled matched distractor injection was not verified. | Blocks first necessary/multi-hop evidence claims. Passive irrelevant content must not be equated with AV-TRACE-style distractor intervention. | https://arxiv.org/abs/2603.14468 ; https://github.com/yrywill/LongVidSearch |
| **FLARE** | Full-modality long-video audiovisual retrieval over 399 Video-MME videos, 87,697 clips, 274,933 user-style queries, and 225.4 hours; includes visual, audio, and hard-bimodal retrieval. | Blocks first audiovisual long-video retrieval and both-modalities-necessary claims. It does not, on the reviewed record, supply failure/restoration trajectories. | https://arxiv.org/abs/2605.10228 ; https://flarebench.github.io/ |
| **V-RAGBench** | 2,100 query–evidence–answer triplets over 216 Ego4D/EgoLife videos; evidence is localized and retrieval/generation are evaluated separately. | Strong evidence-dependence precedent. Call it construction-filtered evidence dependence, not a matched causal intervention. | https://arxiv.org/abs/2606.13141 ; https://huggingface.co/datasets/DISLab/VRAG-Bench |
| **LongShOTBench** | Current v2/release reports 3,401 questions over 274 videos, about 188 hours and about 41 minutes average; version 1 had different counts. | Blocks broad omni-modal long-video reasoning, rubric, routing, and iterative verification claims. Raw-video acquisition remains source/platform dependent. | https://arxiv.org/abs/2512.16978 ; https://github.com/mbzuai-oryx/LongShOT ; https://huggingface.co/datasets/MBZUAI/longshot-bench |
| **MOV-Bench / AOP-Agent** | 519 curated audiovisual multi-hop MCQs with active omni-modal observe–reflect–replan behavior. Release status beyond the paper was not verified in the audited materials. | Blocks broad claims for multi-hop audiovisual evidence and active omni-modal reasoning. | https://arxiv.org/abs/2605.28192 |
| **VideoGAIA** | 271 human-verified agent tasks with iterative video inspection and web tools; official repository and dataset card are public. | Blocks first general video-agent/tool benchmark claims. Dedicated audio necessity and controlled failure/restoration were not verified. | https://arxiv.org/abs/2608.14718 ; https://github.com/zfkarl/VideoGAIA ; https://huggingface.co/datasets/Karl28/VideoGAIA |
| **REVEAL** | A method, not a new source benchmark: rubric-guided sufficiency verification, missing-clue identification, and targeted re-retrieval on existing long-video benchmarks. | Directly occupies sufficiency verification and premature-stopping prevention at method level. The current benchmark spec mislabels it as a benchmark/evidence-localization evaluation. | https://arxiv.org/abs/2608.08612 |
| **TRACE / VES-Bench** | 600 four-choice questions over 348 public long videos with jointly necessary evidence intervals and decoded-frame coverage auditing; TRACE uses evidence-growth/convergence stopping. | Closest benchmark precedent for necessary evidence, evidence seen by the model, and stopping. Blocks first evidence-coverage or stopping-aware benchmark claims. | https://arxiv.org/abs/2608.22516 ; https://github.com/buaa-colalab/TRACE ; https://huggingface.co/datasets/buaaplay/VES-Bench |
| **HERBench** | 26,806 five-way MCQs across 12 compositional tasks, with at least three non-overlapping cues from distinct segments. | Blocks first unavoidable multi-evidence integration claims. | https://arxiv.org/abs/2512.14870 |
| **OmniHalluc-L** | 3,600 paired supported/counterfactual claims from 638 videos, with audiovisual event binding, strict-pair evaluation, and audio-negative modality probes. | Blocks first counterfactual audiovisual benchmark and modality-perturbation calibration claims. | https://arxiv.org/abs/2606.03614 |

Other factual records in the research documents are generally careful, but all repository/card license statements must be pinned to exact revisions before reliance. The current BibTeX file also contains entries whose author metadata is explicitly unverified; those are acceptable as placeholders only, not camera-ready citations.

### 2.2 Later and omitted adjacent work

The literature search is not complete enough to support any “first” statement. At minimum, add and audit:

- **From Intent to Evidence: An Evidence-Grounded Framework for Long-Video Agents** — https://arxiv.org/abs/2608.31005
- **Omni-Decision: A Progressive Evidence-State Agent System for Context-Aware Reasoning** — https://arxiv.org/abs/2607.11433
- **VideoTreeSearch** — https://arxiv.org/abs/2607.16189
- **OmniAgent: Native Active Perception as Reasoning for Omni-Modal Understanding** — https://arxiv.org/abs/2606.19341
- **AVHBench / When No Answer Is Correct** — https://arxiv.org/abs/2606.08239
- **VideoAgent2** — https://arxiv.org/abs/2507.04471
- **VideoDR** — https://arxiv.org/abs/2601.00138
- **ViSAGE** — https://arxiv.org/abs/2607.28678
- **MetaVideoAgent** — https://arxiv.org/abs/2608.04587
- **VideoHarness-RSI** — https://arxiv.org/abs/2608.24302

These are adjacent rather than automatically novelty-destroying. Their exact overlap must be entered into the same capability matrix using primary texts. In particular, AVHBench narrows abstention/absent-answer claims, while progressive evidence-state and active-perception agents narrow broad recovery/routing claims.

### 2.3 Dataset and source facts requiring correction or stronger evidence

- **LoVR, LongVidSearch, LongShOTBench, and TRACE/VES-Bench licenses:** the inventory makes specific code/data-license statements without storing exact repository commits, Hugging Face revisions, license-file URLs, card hashes, or artifact scope. Until those are captured, mark the relevant license fields **unverified/hold**, not cleared.
- **LongShOTBench:** a documented cookie-based YouTube workflow is not evidence that this project is authorized to download source videos. Treat it as metadata/annotation compatibility only unless an expressly authorized route or rightsholder grant exists. Official sources: https://github.com/mbzuai-oryx/LongShOT and https://www.youtube.com/static?template=terms
- **NASA:** revise the inventory wording. NASA-authored works are generally not copyrighted in the United States; that status is not conditional on noncommercial use. NASA-hosted third-party material, logos/insignia, endorsement, identifiable-person uses, music, and non-US rights still need asset-level review. Source: https://www.nasa.gov/nasa-brand-center/images-and-media/
- **NARA:** a catalog record is evidence, not a warranty of title. Accept only an affirmative federal-work/public-domain basis or documented permission; absent or ambiguous restrictions remain `unknown_hold`. Sources: https://www.archives.gov/research/motion-pictures and https://www.archives.gov/research/still-pictures/permissions
- **EPIC-KITCHENS:** the CC BY-NC annotation license does not establish rights in downloaded participant footage/audio. Keep raw media on hold until its exact package terms/agreement are archived. Source: https://github.com/epic-kitchens/epic-kitchens-100-annotations/blob/master/license.txt
- **Assembly101:** the inventory's “4,321 videos; 513 hours; 15 views across 101 participants” combines quantities whose exact meaning and release version were not reproducibly established in this audit. Mark the row uncertain and re-verify every quantity and term from a pinned official project/paper release before using it for acquisition or storage planning. Source: https://assembly-101.github.io/

## 3. Legal and rights analysis

### 3.1 Required separation

Every source and every released artifact needs four independent determinations:

| Dimension | Question | Insufficient evidence |
|---|---|---|
| **Software/annotation license** | May code, labels, rubrics, metadata, or generated annotations be copied and redistributed? | A repository LICENSE badge without artifact scope. |
| **Source-media copyright** | Who owns the video, audio, music, subtitles, graphics, and inserted third-party material? | Public availability, dataset hosting, or a paper's CC license. |
| **Access permission** | May this team obtain and process the bytes by this route, account, entity, and purpose? | A URL resolving or a third-party downloader working. |
| **Redistribution authority** | May this project give raw media, clips, transcripts, frames, audio, or features to others? | Permission to access internally or conduct research. |

The documents state this distinction in prose, but `acquisition_manifest_schema.json` does not enforce it. `rights_status: permission_or_agreement` can validate while the scope of permission and onward sharing remain unknown; multiple required fields accept `null`; annotation redistribution is optional; derived-artifact records lack sufficient rights evidence.

### 3.2 Unsupported or overconfident legal conclusions

- **`downloadable_redistributable_raw` is not a source-family property.** It is an asset-and-purpose decision after verifying all embedded components.
- **“Catalog record controls” is too absolute for NARA.** Catalog metadata must be retained, but ambiguity is not affirmative clearance.
- **“Official project distributes videos” does not prove sublicensing authority.** This applies to LoVR, LongShOTBench, TRACE/VES-Bench, FLARE, and similar web-derived releases.
- **Research purpose does not cure platform or copyright restrictions.** Remove the quota-driven crawl exception.
- **Generated derivatives are not automatically free of upstream rights.** Dense transcripts, clips, recognizable audio, frame packs, and invertible features need their own release decision.

### 3.3 Rights-safe source recommendation

For a 50-video eventual public core, use this target only after per-asset clearance:

| Source | Target | Mandatory condition |
|---|---:|---|
| NASA-authored official media | 16 | Official direct file; NASA production confirmed; no uncleared third-party footage/music; marks, endorsement, and likeness reviewed |
| NARA federal-government works | 12 | Affirmative federal-work/public-domain basis, not merely no displayed restriction |
| NOAA-authored official media | 8 | NOAA production/credit verified; partner/contractor components excluded unless separately licensed |
| Wikimedia Commons | 8 | Prefer CC0, verified public domain, or CC BY 4.0; pin revision and source chain; initially avoid uncertain and share-alike-complex assets |
| Direct creator/institution grants | 6 | Written worldwide grant for acquisition, editing, ML evaluation, raw redistribution, derived artifacts, and all included audio/music |

Gated academic datasets and existing benchmarks should be separate compatibility evaluations and must not count toward a public-redistributable-core quota.

## 4. Cross-document audit by required category

Detailed row-level conflicts are in the CSV. The principal contradictions are:

- **Terminology:** individually necessary units versus necessity groups; hop IDs versus hop types; probability “distribution” versus independent multilabel probabilities; `STOP`/`INSUFFICIENT` actions versus one `finalize` action; `request_channel_status` versus `get_channel_status`.
- **Novelty thesis:** full factorial family versus one intervention pair per item; broad counterfactual claim versus no counterfactual operation in schema; ranking inversion versus paired behavioral response.
- **Modalities:** V/S/A is mostly consistent, but alternative SESs can use different modalities, making the current single gold missing-modality target ill-defined.
- **Evidence necessity:** pilot uses single-unit deletion; spec and annotation guide correctly require exhaustive alternative search and necessity-group removal.
- **Episode variants:** nine canonical variants, five pilot families, universal C/I-/I+ roles, and optional counterfactuals are not reconciled.
- **Tracks:** public core and gated/compatibility sources are separated in data prose but not clearly separated in leaderboard eligibility.
- **Metrics:** benchmark overview, metrics protocol, and pilot define different headline aggregates; recovery and premature-stop prose/formulas disagree; budget curves cannot be derived from a single terminating prediction.
- **Output schema:** no normative action/response/final schema; final modality probabilities needed by metrics are absent.
- **Sample sizes:** 15 video clusters in the MFS cannot sustain stated confirmatory inference; 200 items cannot reliably fill the promised interaction structure.
- **Episode counts/costs:** the 600-episode basis excludes counterfactual, oracle-reveal, ablation, repeat, canary, retry, and robustness runs.
- **Gates:** rights, pair isolation, and reproducibility gates are conceptually sound but cannot yet be machine-enforced.
- **Source mix:** the five-domain quota is not backed by a rights-cleared candidate manifest and could force prohibited/risky media acquisition.

## 5. Three hostile reviewer reports

### 5.1 Benchmark novelty reviewer — **weak reject unless narrowed**

**Attack:** “This is LongVidSearch/TRACE necessary evidence plus FLARE audiovisual retrieval plus REVEAL sufficiency checking plus standard agent failure injection.”

**Assessment:** That attack succeeds against the current broad framing. The research documents correctly identify most occupied territory, but the pilot does not implement the full factorial white space it claims, and the paper outline omits the closest 2026 works.

**Required rebuttal:** show that, for the same latent item and frozen backend, clean performance does not predict (i) correct insufficiency recognition under a blocked necessity group, (ii) correct attribution to access failure rather than source absence, and (iii) grounded answer revision after deterministic restoration. Directly compare with a REVEAL-style verifier and TRACE-style convergence policy. Do not rely on a “first” claim.

### 5.2 Dataset/licensing/reproducibility reviewer — **reject / ethics-and-release blocker**

**Attack:** “The benchmark cannot establish that evaluators may obtain or redistribute its media; a research DUA, repository license, or hosted file is being used as a proxy for source rights.”

**Assessment:** The prose is cautious, but the operational schema permits precisely this failure. No item-level evidence exists yet. A public benchmark cannot depend on unreviewed web-derived packages or institution-specific access.

**Required rebuttal:** release a self-contained A1 public core with immutable rights evidence and an artifact-by-artifact release matrix. Publish gated compatibility results separately. Provide a takedown/versioning process and demonstrate clean-room reconstruction.

### 5.3 Evaluation/statistics reviewer — **reject as underspecified and underpowered**

**Attack:** “The metric can be changed by selecting one of three documents, recovery can be earned without recovery, the budget curve is not observable, and 15 video clusters cannot support the claimed rank and interaction conclusions.”

**Assessment:** Correct. The current statistical plan confuses construct validation with confirmatory benchmarking.

**Required rebuttal:** simplify Pilot-0, define one estimand per phenomenon, use video-cluster inference, remove weighted composites, publish power/operating-characteristic simulations, and expand independent video clusters before any leaderboard or paper-level ranking claim.

## 6. Severity-indexed issues

Every issue below includes the required location, current design, evidence/inconsistency, consequence, exact correction, and confidence. See the CSV for additional detail.

### P0_BLOCKER — fix before downloading or annotating media

#### P0-1. No asset has passed the proposed rights gate
- **Document/location:** repository state; `docs/data/data_source_audit.md:60-73`; `docs/pilot/pilot_0_plan.md:76-81,310-312`.
- **Current design:** proceed after source-family screening and later reach 100% source records.
- **Evidence/inconsistency:** only a schema and family inventory exist; there are no asset manifest instances or signed decisions.
- **Consequence:** acquisition and annotation authority are unproven; current cleared count is **0/50**.
- **Exact correction:** permit only metadata discovery until each asset has a validated manifest, rights snapshot, acquisition route, publisher/rightsholder, content hash plan, and separate release decisions.
- **Confidence:** High.

#### P0-2. Rights schema permits unresolved clearance
- **Document/location:** `docs/data/acquisition_manifest_schema.json:462-611,810-916`.
- **Current design:** required fields can be null; `rights_status` combines multiple legal dimensions; artifact rights evidence is incomplete.
- **Evidence/inconsistency:** conflicts with the fail-closed release checklist at `docs/data/license_risk_register.md:64-76`.
- **Consequence:** an unresolved or internal-only agreement can pass validation and be treated as public-release authority.
- **Exact correction:** split and conditionally require non-null copyright basis, acquisition authority, processing scope, authorized users, raw/derivative/transcript/annotation/feature redistribution, commercial use, exact license/agreement, licensor, snapshot hash, and reviewer decision.
- **Confidence:** High.

#### P0-3. Pilot evidence semantics invalidate interventions
- **Document/location:** `docs/pilot/pilot_0_plan.md:30-37`; `docs/spec/benchmark_v0.md:59-66,239-249`; `docs/spec/annotation_guideline_v0.md:137-175`.
- **Current design:** Pilot-0 requires one to three individually necessary units.
- **Evidence/inconsistency:** the normative design correctly allows several minimal SESs and defines necessity groups.
- **Consequence:** removing one unit may leave a valid alternative, falsely labeling the state insufficient.
- **Exact correction:** require enumerated minimal SESs and validated necessity groups; block every member of one group in `BLOCKED`.
- **Confidence:** High.

#### P0-4. Pilot episode contract is not implementable consistently
- **Document/location:** `docs/pilot/pilot_0_plan.md:14-22,244-250`; `docs/spec/benchmark_v0.md:120-189`; `docs/spec/episode_schema.json:940-1092`.
- **Current design:** universal C/I-/I+ triplets coexist with nine variants, five merged families, and an extra counterfactual subset.
- **Evidence/inconsistency:** schema has no clean/blocked/restored role or triplet linkage beyond generic `pair_id`.
- **Consequence:** episode totals, pair membership, recovery eligibility, and cost are ambiguous.
- **Exact correction:** add `state_role`, `anchor_episode_id`, and `intervention_family_id`; for Pilot-0 permit exactly CLEAN/BLOCKED/RESTORED.
- **Confidence:** High.

#### P0-5. Counterfactual replacement is claimed but cannot be represented
- **Document/location:** `docs/research/novelty_boundary.md:73-86,180-200`; `docs/spec/episode_schema.json:682-938,940-1092`; `docs/spec/metrics_protocol.md:206-241`.
- **Current design:** counterfactual substitution is central, and claims can have `replace` response.
- **Evidence/inconsistency:** there is no replacement-media operation or variant; metrics say replacement may be later.
- **Consequence:** a flagship construct has no deterministic or rights-aware implementation.
- **Exact correction:** remove replacement from Pilot-0 and rename core CGC to Claim-Response Consistency; add replacement only in a future schema with licensed provenance and matched controls.
- **Confidence:** High.

#### P0-6. Web-crawl exception contradicts the rights policy
- **Document/location:** `docs/pilot/pilot_0_plan.md:23,312`; `docs/data/license_risk_register.md:19`.
- **Current design:** permits a crawl if licensed/public candidates fail a quota.
- **Evidence:** YouTube terms and developer policies do not make quota pressure an authorized download basis: https://www.youtube.com/static?template=terms and https://developers.google.com/youtube/terms/developer-policies
- **Consequence:** acquisition may violate platform terms or source rights.
- **Exact correction:** prohibit web-media acquisition unless an approved platform function or rightsholder grant authorizes the exact acquisition and processing; otherwise use metadata/IDs only.
- **Confidence:** High.

#### P0-7. Normative machine protocol is incomplete
- **Document/location:** `docs/spec/tool_api.md:18-151,363-448`; `docs/spec/episode_schema.json`.
- **Current design:** machine-validated actions, responses, final outputs, and intervention manifests.
- **Evidence/inconsistency:** no action/output schema; finalize does not use the common envelope; the `expected_graph_effect` example is forbidden by the hook schema; example hashes violate the declared pattern.
- **Consequence:** independent implementations cannot agree on valid traces.
- **Exact correction:** before any real annotation, publish schemas and executable synthetic fixtures for clean, blocked, restored, malformed, exhausted, and replayed episodes; validate every example.
- **Confidence:** High.

#### P0-8. JSON Schema cannot enforce the scientific graph invariants
- **Document/location:** `docs/spec/episode_schema.json:146-159,371-587`; `docs/pilot/backlog.md:P0-10`.
- **Current design:** schema validation is a release gate.
- **Evidence/inconsistency:** interval order, source bounds, ID references, uniqueness, DAG validity, complete claim support, SES minimality, and necessity-group intersection are not enforceable by the present schema.
- **Consequence:** schema-valid but scientifically invalid episodes can enter annotation.
- **Exact correction:** implement the semantic linter and unit-test it on positive and adversarial fixtures before the first real item.
- **Confidence:** High.

### P1_MAJOR — fix before Pilot-0 model runs

1. **One leaderboard rule:** delete the conflicting IDS/Intervention Utility definitions; sort only by stratified `Success@Budget`, with diagnostics shown separately. (`benchmark_v0.md:316-326`; `metrics_protocol.md:334-350`; `pilot_0_plan.md:185-193`) — **High**.
2. **Finalize probabilities:** either add final `missing_evidence.modality_probabilities` or remove Modality Brier. (`metrics_protocol.md:168-180`; `tool_api.md:397-405`) — **High**.
3. **Recovery:** define paired restoration gain as primary; separate route recovery, common-failure correction recovery, and own-failure descriptive rates. (`metrics_protocol.md:127-164`; `pilot_0_plan.md:164-181,304`) — **High**.
4. **Premature stop:** make the formula match prose, including answer mode, route declaration, and budget-guard exception. (`metrics_protocol.md:90-109`) — **High**.
5. **Budget curves:** add checkpoint predictions or run separate budget-capped episodes. (`metrics_protocol.md:151`; `tool_api.md:363-414`) — **High**.
6. **Clustering:** bootstrap videos, not families; source-level sensitivity where relevant. (`metrics_protocol.md:363-372`; `pilot_0_plan.md:39-40,301`) — **High**.
7. **Power:** MFS is construct-validation only. Use at least 30 source-disjoint videos and simulate operating characteristics before confirmatory thresholds. (`pilot_0_plan.md:138-204`) — **High**.
8. **Design:** retain only modality × intervention as a primary interaction; publish exact cell/alias diagnostics. (`pilot_0_plan.md:252-273`) — **High**.
9. **Cost:** count all mandatory states, systems, repeats, oracle reveals, ablations, judges, retries, and invalid-run reserve. (`cost_model.csv:7-8`; `pilot_0_plan.md:21,154-171,82`) — **High**.
10. **Labor:** re-estimate after rehearsal using the full workflow, rejected candidates, alternative search, two validators, and modality-ablation trials. (`cost_model.csv:3-5`; `pilot_0_plan.md:98-134`) — **High**.
11. **Public source mix:** gated datasets cannot satisfy a public-core threshold. (`pilot_0_plan.md:89-96`; `data_source_audit.md:9-14`) — **High**.
12. **Output/status vocabulary:** reconcile hop IDs/types, workflow statuses, and tool names. (`episode_schema.json:1161-1187,1220-1235`; `tool_api.md:133-151`; `benchmark_v0.md:167`) — **High**.
13. **Required-modality label:** use set-valued minimal missing requirements or restrict alternatives to modality-consistent SESs. (`metrics_protocol.md:168-180`; `benchmark_v0.md:241-249`) — **High**.
14. **LongShOT and similar packaged web media:** annotation/metadata compatibility only unless the acquisition route and source rights are expressly documented. — **High**.

### P2_PAPER — fix before paper freeze

1. Add all closest 2026 work to the main comparison, not merely the bibliography. — **High**.
2. Correct REVEAL's identity as a method evaluated on existing benchmarks. — **High**.
3. Change related-work “recovery D” labels to partial where work only iterates/retrieves without imposed failure and restoration. — **High**.
4. Change LongVidSearch hard-distractor overlap to partial unless matched injection is verified. — **Medium**.
5. Replace “causal dependence” for V-RAGBench with construction-filtered evidence dependence. — **High**.
6. Use “matched paired interventions,” not “factorial,” for the current Pilot-0. — **High**.
7. Treat rank inversion as optional evidence, not the main scientific success criterion. — **High**.
8. Resolve 10–20 minute versus ≥20-minute/45–90-minute source definitions. — **Medium**.
9. Use structured claim output as primary; natural-language answer quality is secondary/display-only. — **High**.
10. Remove the source-insufficient FSR requirement unless a distinct absence partition is constructed. — **High**.
11. Report public-core and compatibility-suite results separately. — **High**.
12. Correct NASA/NARA phrasing and pin all license/card revisions. — **High**.
13. Re-verify Assembly101 counts/version before using it in resource planning. — **Medium**.

### P3_POLISH

- Replace `example.org` schema IDs with project-controlled immutable URIs.
- Replace illustrative invalid hashes with valid dummy hashes.
- Explicitly list the five normative specification files in the freeze gate.

## 7. Canonical recommendation

### Canonical thesis

> **Static clean-video accuracy does not characterize long-video-agent reliability. AV-TRACE uses matched, deterministic blocking and restoration of validated necessity groups on a fixed claim–evidence graph to measure whether agents recognize insufficiency, distinguish access failure from evidence absence, adapt their search policy, and revise answers with grounded evidence.**

Do not claim first. Do not include counterfactual replacement, generic audiovisual coverage, necessary evidence, sufficiency methods, stopping, or tool use as independent novelty claims.

### Canonical Pilot-0 scope

**Purpose:** construct validation and feasibility, not a paper-scale leaderboard.

- **30 source-disjoint, asset-cleared videos**; two questions per video.
- **60 families**, each with exactly:
  1. `CLEAN` — one validated SES reachable;
  2. `BLOCKED` — every member of one necessity group inaccessible, no alternative SES reachable;
  3. `RESTORED` — same blocked initial state, deterministic restoration within budget.
- **180 episodes/system; four fixed-backend systems = 720 core runs.**
- Four preregistered modality strata: V, S, A, cross-modal; 15 families each.
- Two intervention mechanisms only: necessity-group removal and channel outage. At least 20 families per mechanism; overlap/cross-modal balance declared before authoring.
- No distractor injection, ASR corruption, answer-flipping replacement, budget factorial, open-system track, broad five-domain quotas, or ranking-inversion gate.
- Primary Pilot-0 outputs: clean-to-blocked change, blocked FSR, restored-minus-blocked grounded success, sufficiency Brier, completion/replay rate, agreement, labor, and cost.
- Use video-cluster intervals. Pilot-0 passes if constructs are valid, interventions are isolated, restoration is usable, and uncertainty supports a larger powered study—not because a p-value or rank inversion is obtained.

### Primary leaderboard

**One primary track:** `Perturbed Fixed-Backend Triplets` on the public-redistributable core.

**Sorting key:** family-level `Success@Budget`, equal-weighted across CLEAN/BLOCKED/RESTORED and macro-averaged over preregistered modality/mechanism strata, with 95% video-cluster confidence intervals and a predeclared practical tie region.

Mandatory visible columns:

- CLEAN `Success@Budget`;
- BLOCKED `Success@Budget` and FSR;
- RESTORED `Success@Budget`;
- paired restoration gain;
- sufficiency Brier;
- Claim-Response Consistency;
- median tool cost and decoded seconds.

No IDS or Intervention Utility sorting. Gold-evidence, open-system, and restricted compatibility evaluations remain separate, unpooled tables.

## 8. Implementation blockers versus deferrable work

### Must be completed before any download/annotation

- asset-level rights manifest instances and fail-closed rights schema;
- approved public-core source list and acquisition methods;
- removal of the crawl exception;
- canonical CLEAN/BLOCKED/RESTORED episode model;
- necessity-group semantics;
- action/response/final schemas;
- semantic graph/intervention linter;
- one end-to-end synthetic replay fixture.

### Must be completed before any model run

- one primary metric/leaderboard rule;
- computable final outputs;
- corrected recovery, stopping, budget, and clustering definitions;
- measured run/cost manifest;
- prompt/model/tool/backend freeze;
- power/operating-characteristic study;
- completed annotation reliability and pair-isolation checks.

### Can wait until after Pilot-0 construct validation

- distractor injection;
- ASR corruption;
- answer-flipping counterfactual replacement;
- broad budget factorials;
- open-system leaderboard;
- multilingual extension;
- five-domain balance;
- public leaderboard infrastructure;
- large-scale compatibility suites.

## 9. Preflight disposition

**Current status: `P0_BLOCKED`.**  
Do not download source media or begin content annotation. The only approved next work is:

1. collect and adjudicate asset-level rights evidence without transferring media unless the route is already authorized;
2. reconcile the three-state Pilot-0 contract;
3. complete the executable schemas/linter/synthetic fixture;
4. rerun the novelty audit including the omitted work; and
5. price the exact run and annotation manifest.

Proceed to real media only after every item in the **Pre-acquisition freeze** section of [`freeze_checklist.md`](freeze_checklist.md) is signed off.
