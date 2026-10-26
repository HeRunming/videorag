# AV-TRACE CVPR-main paper blueprint v2

**Packaging date:** 2026-09-23  
**Document role:** concrete paper/benchmark package; subordinate to the frozen
scientific decisions in `cvpr_pivot_decision_and_6week_plan.md` and
`cvpr_thesis_and_evidence_gates.md`  
**Companion matrix:** `data/rehearsal_plan/cvpr_main_evidence_matrix_v2.json`  
**Readiness token:** `CVPR_MAIN_BLUEPRINT_READY__PAPER_CLAIMS_BLOCKED`

## 0. Status firewall and immediate handoff

This blueprint separates three states in every section:

- **ACHIEVED/CURRENT:** supported by an existing artifact as of 2026-09-23.
- **ACTIVE NOW:** a process is running or a prerequisite has been implemented,
  but the terminal artifact or gate has not passed.
- **INTENDED/FUTURE:** a paper target, experiment, or claim that remains gated.

### 0.1 Current snapshot

| Area | Status on 2026-09-23 | What may be said |
|---|---|---|
| Audited real-A/V infrastructure | **ACHIEVED/CURRENT** | The repository executes and independently replays matched C/B/R episodes under fixed budgets on machine-provisional development material. |
| Full-timeline learned retrieval | **ACHIEVED/CURRENT** | Pinned visual/audio retrievers and fixed no-training fusion have reproducible low-N diagnostic results. |
| Four replacement source dossiers and exact acquisition | **ACHIEVED/CURRENT** | Four exact first-party renditions are available for restricted, noncommercial local processing under source-specific safeguards. This is not public-release clearance. |
| Four-source canonical full-timeline build | **ACTIVE NOW** | The unbounded build command is running against `data/restricted/mini_pilot_index_v1/`. At packaging time only `segment_manifest.json` and `resource_manifest.json` existed; the required terminal artifacts were not yet present. |
| Real family mining | **BLOCKED BEHIND ACTIVE BUILD** | The mining framework is ready and fail-closed, but no real family mining run has occurred and no real candidate family has been emitted. |
| Human validation | **NOT ACHIEVED** | Zero H1 and zero H2 families. No current SES, necessity, support, or modality label is human gold. |
| Learned generation/agents | **NOT READY** | Existing learned-controller runs are competence `NO_GO`; no H2 end-to-end learned result exists. |
| Final benchmark/public release | **NOT ACHIEVED** | No validated benchmark, scaled test set, population ranking, or release-ready public media core exists. |

The blueprint readiness token certifies that the **paper plan and artifact map**
are ready. It does not promote Gate A, Gate B, Gate C, Gate D, Gate F, Gate G,
`PAPER_CLAIM_READY`, or `FINAL_BENCHMARK_VALIDATED`.

### 0.2 Exact top blockers, in execution order

1. **`B01_CANONICAL_FOUR_SOURCE_FULL_TIMELINE_INDEX_INCOMPLETE`**  
   The active unbounded four-source build has not produced and frozen all five
   canonical artifacts, specifically
   `observation_manifest.json`, `full_timeline_index.json`, and
   `build_manifest.json` in addition to the two present manifests.
2. **`B02_REAL_MACHINE_PROVISIONAL_FAMILY_MINING_NOT_RUN`**  
   The fail-closed miner has emitted zero real candidates. The current
   `mini_pilot_family_mining_v1.json` is a 12+2 dry-run slot fixture, not mined
   families.
3. **`B03_GATE_A_MINI_PILOT_INPUT_READY_NOT_RUN`**  
   Exactly 12 eligible candidate families plus two excluded calibration
   families across exactly six source groups, frozen packets/forms/seed/roles,
   at least six trained reviewers, and a clean governance decision are not yet
   jointly established.
4. **`B04_HUMAN_CONSTRUCT_VALIDITY_ABSENT`**  
   There are zero H1 and zero H2 families. Alternative SES saturation,
   minimality, necessity groups, modality counterfactuals, pair isolation, and
   exact restoration have not been human adjudicated.
5. **`B05_LEARNED_CONTROLLER_GATE_IN_REPAIR`**  
   The frozen controller v1/v2/v3 evidence does not meet semantic, terminal,
   supported-answer, or abstention competence floors. Gate C remains `REPAIR`.
6. **`B06_END_TO_END_H2_DIAGNOSTIC_NOT_AUTHORIZED`**  
   Human-valid learned C/B/R and no-trigger runs do not exist; therefore the
   answer-versus-support, non-retrieval failure-stage, and recovery claims have
   not been tested.
7. **`B07_SCALE_SPLIT_AND_RELEASE_NOT_READY`**  
   The intended 60-H2, at-least-20-source corpus, source-disjoint split,
   reserve, rights decisions, release bill of materials, and public evaluator
   package do not exist.

## 1. Paper identity

### 1.1 Working title

**AV-TRACE: Diagnosing Evidence Acquisition, Grounding, and Recovery in
Long-Video Audiovisual Agents**

Backup, if the final corpus cannot support broad audiovisual wording:

**AV-TRACE: Matched Evidence-Access Interventions for Auditing Long-Video
Agents**

Neither title implies a novelty first, public release, human gold in the current
repository, or a controller-method contribution.

### 1.2 One-sentence thesis

> Answer accuracy alone cannot establish long-video agent reliability:
> AV-TRACE uses human-adjudicated, source-disjoint matched episode families that
> hold the question, evidence graph, backend, and budget fixed while changing
> validated evidence-route availability, enabling trace-level diagnosis of
> acquisition, grounding, citation, insufficiency judgment, stopping, and
> recovery across learned systems.

**Status:** intended main-paper thesis. The infrastructure clause is current;
the human-adjudicated corpus and learned empirical clause are future until their
gates pass.

### 1.3 Paper type and non-goals

The submission is a **benchmark-and-diagnostic-protocol paper**. It is not:

- a controller-method paper;
- a claim that v1/v2/v3 is a competent or novel proposed agent;
- a broad “first,” “unique,” or “only” long-video benchmark claim;
- a SOTA or universal-reliability claim;
- a claim that current NOAA or newly acquired source assets are public;
- a claim that machine-provisional evidence is human gold.

### 1.4 Related-work position

The paper must acknowledge overlap rather than win by component counting:

- necessary or multi-hop evidence: LongVidSearch and adjacent evidence-centric
  long-video work;
- audiovisual and modality-aware retrieval: FLARE and related retrieval
  benchmarks;
- retrieval/generation decomposition: V-RAGBench;
- long-form multimodal rubrics and agentic retrieval: LongShOTBench;
- iterative crop/search agents: LongVT/VideoSIAH, WorldMM, MOV-Bench, VideoGAIA;
- explicit sufficiency, re-retrieval, and stopping: REVEAL and TRACE/VES-Bench.

The narrow intended distinction is the **combination of human-validated matched
evidence-access interventions, common-endpoint restoration, no-trigger
controls, and trace-level Acquire/Ground/Act diagnosis on source-disjoint
long-video A/V families**. Phrase this as a design distinction, not a priority
claim. Refresh the primary-source audit immediately before submission.

## 2. Contribution contract with claim tiers

### Tier definitions

| Tier | Meaning | Paper placement |
|---|---|---|
| **T0 — achieved engineering** | Frozen artifact already supports bounded wording. | System/protocol section; optionally abstract only if clearly engineering-scoped. |
| **T1 — achieved low-N descriptive** | Reproducible result on machine-provisional development families. | Motivation or appendix; never the main scientific denominator. |
| **T2 — intended construct claim** | Requires human H2 evidence and isolation audits. | Abstract/conclusion only after human and corpus gates pass. |
| **T3 — intended empirical claim** | Requires frozen H2 learned evaluation, source-level inference, and independent audit. | Main results/abstract only after Gate D/G. |
| **TX — prohibited** | Not rescuable by wording without new evidence or a dated priority audit. | Must not appear. |

### Contribution list

1. **Matched intervention protocol — T0 now, T2 at benchmark scale.**  
   **Current allowed claim:** AV-TRACE implements auditable C/B/R and no-trigger
   execution with fixed budgets, common supported-answer restoration, complete
   traces, and final-point route certificates.  
   **Future paper claim:** H2 families causally alter the reachability of a
   human-validated necessary route while preserving the matched family
   contract.

2. **Human-adjudicated benchmark construct — T2, not achieved.**  
   Intended contribution: source-disjoint long-video A/V families with atomic
   claims, all accepted minimal SESs, necessity groups over all accepted SESs,
   alternative-route saturation, modality counterfactuals, isolated blocking,
   exact restoration, no-trigger controls, and rights/provenance records.

3. **Acquire/Ground/Act diagnostic — T0 operationalization, T3 empirical
   separation.**  
   **Current allowed claim:** the metrics separately score acquisition,
   claim-level support/citation, sufficiency/access diagnosis, stopping,
   recovery, invalidity, and cost.  
   **Future paper claim:** learned systems exhibit audited failure-stage
   separations not reducible to retrieval recall or answer accuracy.

4. **Strong learned benchmark study — T3, not achieved.**  
   Intended contribution: direct/long-context, single-shot RAG, learned ReAct,
   and learned evidence-sufficiency systems, with at least two model/backbone
   families, common tools/budgets/finalizer rules, and oracle/partial-evidence
   diagnostics.

5. **Reproducible retrieval and execution substrate — T0/T1.**  
   Pinned model snapshots, exact source/media identities, deterministic
   rankings, action-level replay, independent metric recomputation, and
   fail-closed verification are current. The observed full-timeline and
   learned-retrieval degradations remain low-N machine-provisional findings.

### Claims that remain secondary

- Generic learned encoders are not automatically better than task-aligned
  controls.
- Full-timeline search is harder than a shortlisted candidate universe.
- Explicit sufficiency control outperforms ordinary ReAct.
- Vision, speech, ambient audio, or a combination is necessary.

Each can be promoted only by its named evidence in the companion matrix.
Controller superiority is optional to the benchmark story and must be reported
as null or adverse if that is the outcome.

## 3. Proposed paper architecture

1. **Introduction:** answer correctness can conceal unsupported answers,
   missed evidence, wrong citations, false sufficiency, and premature stopping.
2. **Related work:** locate AV-TRACE among evidence-centric long-video
   benchmarks, audiovisual retrieval, tool-using video agents, and
   sufficiency/recovery agents; avoid firstness.
3. **Task and matched-family design:** formalize the family as the causal unit,
   all-SES semantics, necessity groups, C/B/R, common endpoint, and no-trigger.
4. **Data and human adjudication:** rights-first sourcing, full-timeline
   indexing, machine candidate mining, independent roles, saturation,
   intervention construction, split and release rules.
5. **Systems and evaluation:** shared backend/budgets, baselines, metrics,
   invalid-run policy, source-cluster inference.
6. **Results:** corpus validity, primary dashboard, matched interventions,
   failure taxonomy, ablations, qualitative traces.
7. **Limitations, rights, and responsible release.**

## 4. Benchmark composition target

### 4.1 Final target and stage boundary

The final paper target remains **60 H2 families from at least 20 source
groups**, with whole-source development/validation/test assignment. This is
**INTENDED/FUTURE**, not a description of the current dataset.

| Dimension | Minimum/frozen target | Preferred target | Rule |
|---|---:|---:|---|
| H2 families | 60 | 72 if schedule and unchanged criteria permit | Never fill quota by weakening SES, necessity, isolation, or rights rules. |
| Source groups | 20 | 24–30 | No source contributes more than 10% of scored families. |
| Split | 24 dev / 12 val / 24 test families from at least 8/4/8 source groups | 12/6/12 source groups if 30 sources | All derivatives inherit source split. |
| Content domains | at least 3 | 4–6 | Main finding may not be supported by one domain alone. |
| Intervention mechanisms | necessity-group withholding and modality-channel outage | approximately balanced | Report actual accepted balance; do not force invalid families. |
| Hop strata | one-hop and multi-hop | approximately balanced | Define from H2 claim-evidence graph, not slot intent. |
| Temporal span | near/local and far/separated | approximately balanced | Freeze threshold before test analysis. |
| Evidence routes | V, S, A, and valid combinations | broad coverage | Necessity labels only when every accepted SES supports the claim. |
| Alternative SES | all discovered accepted SESs recorded | saturation-audited | Preferred SES alone is never treated as exhaustive. |
| Controls | C/B/R plus no-trigger where eligible | all restoration families | No-trigger denominator reported separately. |
| Reserve | at least 25% source/family reserve | 30% | Used for rights withdrawal or construct defects, never outcome replacement. |

The current four new sources and NOAA development sources are **candidate and
development material**, not the final source-disjoint test. Current NOAA and
all sources touched during protocol, prompt, controller, retriever, metric, or
family development are excluded from the primary test split.

### 4.2 Table 1 shell — corpus and construct statistics

| Split | Source groups | H2 families | Total hours | Median source min | V | S | A | V+S | V+A/S+A | V+S+A | Necessity block | Modality outage | 1-hop | Multi-hop | Near | Far | Median accepted SES/family | Alt-SES discovery rate | Pair-isolation pass | Public/reconstructable/restricted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Development | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Validation | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Test | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Total | **target ≥20** | **target 60** | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

Footnote requirements: distinguish primary modality route from proven
necessity; state that modality combinations may overlap; report source-group,
not upload, counts; disclose restricted assets separately from releasable
artifacts.

### 4.3 Table 2 shell — construction funnel and labor

| Stage | Candidates entering | Accepted | Repaired | Rejected/quarantined | Main rejection reasons | Active review hours | Adjudication hours | Rights hours | Replay pass |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| Machine P0 | TBD | TBD | — | TBD | duplicate/weak evidence/unsafe | TBD | — | TBD | TBD |
| Machine P1/P2 | TBD | TBD | TBD | TBD | alternative route/modality mismatch | TBD | — | TBD | TBD |
| H1 | TBD | TBD | TBD | TBD | ambiguity/minimality/isolation | TBD | — | TBD | TBD |
| H2 | TBD | TBD | TBD | TBD | adjudicated construct/governance failures | TBD | TBD | TBD | TBD |
| Frozen corpus | TBD | **60 target** | — | reserve reported separately | rights/withdrawal/late audit | — | — | TBD | 100% target |

## 5. Figure concepts

### Figure 1 — Why answer accuracy is not a reliability metric

**Diagnostic concept.** A left-to-right visual with one question and one fixed
claim-evidence graph at the top, followed by three agents that all emit the same
answer:

1. **supported and cited:** acquired an accepted SES, grounded every atomic
   claim, valid citations, justified stop;
2. **correct but unsupported:** answer matches, but a required claim lacks
   observed support or has a wrong citation;
3. **premature or falsely sufficient:** a certified feasible route remains at
   finalization, or the agent declares sufficiency in BLOCKED.

Below, map the trace to the three diagnostic bands:

```text
Acquire: accepted evidence/SES coverage
Ground: answer, claim support, citation
Act: sufficiency, diagnosis, stop, recovery, cost
```

**Caption boundary:** the figure explains the intended construct and metrics.
Until H2 learned evidence exists, use a schematic or explicitly labeled
machine-provisional development trace, not a representative benchmark result.

### Figure 2 — Rights-first data and annotation pipeline

Show a gated funnel:

```text
source discovery
  -> exact route, identity, rights/privacy dossier
  -> restricted exact acquisition
  -> full-timeline 4/8/32-second indexing
  -> P0/P1/P2 machine proposal mining
  -> author/verifier
  -> blind full-source alternative-SES search
  -> validators A/B + counterfactuals
  -> adjudication + saturation
  -> H2 family
  -> intervention build and replay audit
  -> whole-source split + release decision
```

Use red lock icons at rights, H2, split, and release gates. Mark the current
repository position precisely: **four-source full-timeline build active;
real mining and human review not yet run**.

### Figure 3 — Matched intervention and common-endpoint recovery

For one H2 family, draw the same question, evidence graph, backend, budget, and
initial public observations in three columns:

- **CLEAN:** at least one accepted SES route reachable.
- **BLOCKED:** every route through one validated necessity group or necessary
  channel inaccessible.
- **RESTORED:** begins identically to BLOCKED; a deterministic policy-blind
  trigger restores exactly the registered route.

At the bottom use the same endpoint for CLEAN and RESTORED:
`supported_answer_success`. Report BLOCKED insufficiency/access diagnosis as a
separate endpoint. Add a fourth narrow column for **NO_TRIGGER**, which stays
blocked and estimates trigger leakage/false recovery.

**Prohibited arithmetic:** never label
`RESTORED supported answer - BLOCKED diagnostic success` as recovery gain.

## 6. Full experiment and table plan

### 6.1 Systems

| Row | System class | Required role | Current/future |
|---|---|---|---|
| D-ReAct | Deterministic ReAct protocol probe | Metric/intervention positive control | Current engineering; never a learned baseline |
| D-Suff | Deterministic evidence-sufficiency probe | Protocol sensitivity control | Current engineering; never a learned baseline |
| Direct-LC-A/V | Pinned direct or long-context learned A/V model | Tests retrieval/agent necessity | Future; must be genuinely A/V-capable or narrowly labeled |
| RAG-FCTRL | Single-shot learned RAG with frozen control retrieval | Non-agent learned grounding baseline | Future |
| RAG-FVA | Single-shot learned RAG with learned modality retrieval/fixed RRF | Retrieval sensitivity | Future |
| ReAct-FCTRL | Learned ordinary ReAct | Agent comparator | Future; same backbone/contract as Suff-FCTRL where practical |
| Suff-FCTRL | Learned evidence-sufficiency agent | Controller hypothesis | Future |
| Strong-open | Pinned materially stronger open-weight agent | Capacity/model-family sensitivity | Planned, not execution-ready |
| Strong-API | Exact dated API snapshot if rights/privacy permit | Provider/model-family sensitivity | Optional; no claim may depend solely on it |
| Oracle-H2 | Generator given accepted H2 evidence | Ground upper-bound diagnostic | Future |
| Partial-H2 | Generator given preregistered incomplete evidence | Hallucination/refusal diagnostic | Future |
| No-trigger | RESTORED-shaped run with restoration disabled | Trigger leakage/false recovery | Future |

At least four learned system classes and two model/backbone families are needed
for `PAPER_CLAIM_READY`. Every learned comparison must disclose model identity,
snapshot/date, input representation, prompt/config hash, tools, budget, repair
policy, completion, invalid count, and cost.

### 6.2 Main Table 3 shell — system contract

| System | Model/revision | Native A/V or proxy | Direct/RAG/agent | Retrieval | Tools | Max steps/cost | Context policy | Prompt/config hash | Dev sources used | Valid/total | Cost/episode |
|---|---|---|---|---|---|---|---|---|---|---:|---:|
| Direct-LC-A/V | TBD | TBD | Direct | — | none | TBD | TBD | TBD | dev only | TBD | TBD |
| RAG-FCTRL | TBD | proxy/native disclosed | RAG | F-CTRL | inspect/read only | TBD | TBD | TBD | dev only | TBD | TBD |
| ReAct-FCTRL | TBD | proxy/native disclosed | Agent | F-CTRL | full common menu | 10/12 primary | frozen | TBD | dev only | TBD | TBD |
| Suff-FCTRL | same comparison backbone | same | Agent | F-CTRL | same menu | same | same | TBD | dev only | TBD | TBD |
| Strong sensitivity | TBD | disclosed | Agent | F-CTRL | same menu | same | same | TBD | dev only | TBD | TBD |

### 6.3 Main Table 4 shell — primary Acquire/Ground/Act dashboard

Each cell is source-cluster mean with 95% source bootstrap interval. Never pool
states as independent rows.

| System | State | All-SES coverage | Evidence Recall@K | Supported answer | Answer score | Citation F1 | Supported-claim rate | False sufficient | Diagnosis accuracy | Premature stop | Recovery success | No-trigger false recovery | Cost/supported answer | Invalid/total |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TBD | CLEAN | TBD | TBD | TBD | TBD | TBD | TBD | — | — | TBD | — | — | TBD | TBD |
| TBD | BLOCKED | TBD | TBD | — | TBD | TBD | TBD | TBD | TBD | TBD | — | — | TBD | TBD |
| TBD | RESTORED | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | — | TBD | TBD |
| TBD | NO_TRIGGER | TBD | TBD | — | TBD | TBD | TBD | TBD | TBD | TBD | — | TBD | TBD | TBD |

### 6.4 Main Table 5 shell — matched effects

| Comparison | Primary endpoint | Effect | 95% source-cluster CI | Holm-adjusted p if confirmatory | Sources/families | Practical threshold | Decision |
|---|---|---:|---|---:|---:|---:|---|
| CLEAN → BLOCKED | supported-answer degradation | TBD | TBD | TBD | TBD | preregistered | TBD |
| BLOCKED → RESTORED | common-endpoint supported-answer recovery | TBD | TBD | TBD | TBD | preregistered | TBD |
| RESTORED → NO_TRIGGER | trigger-dependent recovery | TBD | TBD | TBD | TBD | preregistered | TBD |
| Suff vs ReAct in CLEAN | supported-answer non-inferiority | TBD | TBD | TBD | TBD | margin 0.10 | TBD |
| Suff vs ReAct in BLOCKED | false-sufficient reduction | TBD | TBD | TBD | TBD | improvement ≥0.15 for directional claim | TBD |
| Suff vs ReAct | premature-stop or recovery improvement | TBD | TBD | TBD | TBD | improvement ≥0.15 for directional claim | TBD |

### 6.5 Main Table 6 shell — answer versus support and failure stages

| System/state | Answer correct & supported | Answer correct but unsupported | Answer correct, citation invalid | Acquired complete evidence but failed use | Correctly diagnosed insufficiency | Feasible route but stopped | Restored route acquired but no supported answer | Sources represented |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

This table carries MC2/MC3 only if divergence and at least two non-retrieval
categories satisfy the frozen multi-source rules. Otherwise it becomes a
descriptive taxonomy table with no broad claim.

### 6.6 Main Table 7 shell — ablations

| Ablation | Controlled comparison | Acquire Δ | Ground Δ | Act Δ | Cost Δ | Sources/families | Interpretation |
|---|---|---:|---:|---:|---:|---:|---|
| F-CTRL → F-VA | same system, learned retrieval sensitivity | TBD | TBD | TBD | TBD | TBD | bounded to tested retrievers |
| Retrieved → Oracle H2 evidence | same generator | — | TBD | — | TBD | TBD | acquisition vs utilization |
| Complete → Partial evidence | same generator | — | TBD | false sufficiency/refusal | TBD | TBD | hallucination calibration |
| Observed-evidence lock | same observations, policy/finalizer variants | fixed | TBD | TBD | TBD | TBD | non-retrieval separation |
| Remove claim coverage | same sufficiency agent | TBD | TBD | TBD | TBD | TBD | component effect |
| Remove missingness state | same sufficiency agent | TBD | TBD | TBD | TBD | TBD | component effect |
| Remove calibrated sufficiency | same sufficiency agent | TBD | TBD | TBD | TBD | TBD | component effect |
| Remove status tool | same agent/backend | TBD | TBD | TBD | TBD | TBD | diagnosis vs leakage |
| Disable trigger | RESTORED vs no-trigger | TBD | TBD | TBD | TBD | TBD | trigger isolation |
| Budget 10/12 → 20/24 | preregistered sensitivity | TBD | TBD | TBD | TBD | TBD | budget robustness |
| Preferred SES → all accepted SESs | scoring sensitivity | TBD | TBD | TBD | — | TBD | registry completeness |
| Final-point certificate semantics | normative vs typed-exception sensitivity | — | — | TBD | — | TBD | stopping construct |

### 6.7 Appendix tables

- per-source composition, influence, and leave-one-source-out estimates;
- per-domain and per-intervention-mechanism strata;
- per-family accepted SESs, necessity groups, and saturation outcomes with
  private gold withheld as needed;
- invalid-run, timeout, OOM, malformed-output, and retry accounting;
- learned retrieval ranks and end-to-end propagation;
- prompt/action-menu order sensitivity;
- native-modality versus textualized-observation sensitivity;
- model-capacity sensitivity;
- complete null, negative, rejected, excluded, and low-count strata.

## 7. Failure taxonomy

Failures are assigned from complete traces and can be multi-label unless a
frozen precedence rule is used for a mutually exclusive summary.

| Code | Stage | Operational definition | Required evidence |
|---|---|---|---|
| `F-AQ-LOC` | Acquire | Accepted evidence/SES exists and is reachable, but the system never retrieves a usable pointer. | H2 support graph + retrieval trace |
| `F-AQ-OBS` | Acquire | A usable pointer is retrieved but never inspected/read into a citable observation. | Pointer and action trace |
| `F-AQ-ROUTE` | Acquire | Wrong modality/query/temporal route persists despite budget and feasible route. | Final-point route certificate |
| `F-GR-USE` | Ground | Complete accepted evidence is observed, but a required claim is omitted or wrong. | Observation lock + claim scoring |
| `F-GR-CITE` | Ground | Answer/claim may be correct, but citations do not support the asserted claim. | Human-audited citation labels |
| `F-GR-HALL` | Ground | Required unsupported claim is asserted from partial/blocked evidence. | Atomic claim/support map |
| `F-ACT-FS` | Act | Agent declares sufficient/answers in BLOCKED without accepted support. | Sufficiency output + H2 graph |
| `F-ACT-DIAG` | Act | Agent confuses inaccessible, not found, absent, or unknown. | Frozen state target |
| `F-ACT-STOP` | Act | Agent finalizes while a certified legal route remains feasible. | Final-point executable certificate |
| `F-ACT-OVER` | Act | Agent continues after supported finalization is justified or repeats no-progress actions. | Trace and stopping policy |
| `F-REC-MISS` | Recovery | Restoration occurs, but agent does not check/reacquire the restored route. | Trigger-aligned trace |
| `F-REC-GROUND` | Recovery | Restored evidence is observed but no supported answer follows. | Common endpoint |
| `F-REC-FALSE` | Recovery | No-trigger run appears to recover. | No-trigger control |
| `F-PERCEPT` | Perception | Retrieved raw segment is correct but derived observation is wrong/inadequate. | Human observation audit |
| `F-PROTOCOL` | Execution | Invalid schema, timeout, OOM, backend error, over-budget, or replay mismatch. | Typed failure artifact |

Headline “failure-stage separation” requires at least two non-retrieval
categories, each on at least two source groups, and must not be an artifact of
metric implementation or registry incompleteness.

## 8. Ablation and causal decomposition plan

1. **Answer-only scoring:** quantify how conclusions change when support and
   citations are ignored.
2. **Observed-evidence lock:** hold acquired observations fixed to isolate
   generation, sufficiency, and stopping.
3. **Oracle-H2 versus retrieved evidence:** estimate the acquisition bottleneck.
4. **Partial evidence:** test unsupported completion and calibrated refusal.
5. **Retrieval replacement:** F-CTRL versus F-VA, with human-revalidated
   support and identical downstream components.
6. **Single modality and modality-drop:** only for H2-eligible families; report
   routing when necessity fails.
7. **Sufficiency-state components:** remove claim coverage, missing modality,
   missing hop/cause, recovery intent, and calibrated probability separately.
8. **Status tool:** remove or blind `get_channel_status`; test benefit versus
   restoration leakage.
9. **Trigger/no-trigger:** verify exact restoration and false-recovery rate.
10. **Route-certificate semantics:** audit terminal exceptions and certificate
    executability.
11. **Budget:** preregister primary and expanded caps; do not retrospectively
    truncate.
12. **Alternative SES:** preferred-route scoring versus all accepted H2 SESs.
13. **Backbone/capacity:** ensure the principal diagnostic conclusion is not
    reversed by one weak controller family.
14. **Source/domain leave-out:** no headline effect may depend on one source or
    one domain.
15. **Native A/V versus proxy observations:** either confirm the finding with a
    raw-modality-capable path or explicitly scope the paper to agents over
    audited retrieval observations.
16. **Prompt/menu order:** counterbalance action order and report context/token
    differences.

## 9. Qualitative examples

Select examples by frozen rules after metric computation; do not hand-pick
favorable traces.

### Required main-paper panels

1. **Same answer, different reliability.** One supported/cited trace and one
   correct-but-unsupported or wrong-citation trace for the same endpoint.
2. **Acquire succeeds, Ground fails.** All accepted evidence is observed, but
   the answer or citation fails.
3. **Premature stop.** A final-point certificate shows a feasible route left
   unused.
4. **Successful common-endpoint recovery.** BLOCKED prefix, policy-blind
   trigger, route reacquisition, supported finalization.
5. **No-trigger negative control.** Similar prefix without restoration; no
   false recovery.
6. **Alternative-SES discovery.** A machine-preferred route is not exhaustive;
   human search finds another valid route and changes the necessity group.

### Required appendix cases

- one rejected family for each major construct failure;
- one modality-hypothesis relabeled to routing/corroboration;
- one perception-proxy error;
- one invalid learned run;
- one source or domain that weakens/reverses the aggregate;
- one null/adverse sufficiency-controller example if applicable.

For every shown case disclose selection rule, source split, family/state,
system, observed evidence IDs, endpoint values, and whether media can be shown.
If source-derived media cannot be released, use abstracted timelines, approved
thumbnails, or text-redacted trace diagrams.

## 10. Reproducibility, release, and rights wording

### 10.1 Wording allowed now

> The current repository contains restricted research assets, exact provenance
> and integrity records, pinned model snapshots, deterministic build and replay
> machinery, and machine-provisional development annotations. Public
> redistribution of source media, transcripts, clips, frames, audio,
> embeddings, annotations, or model weights is not implied and remains
> artifact-specific.

> Four newly acquired first-party source renditions are authorized for
> qualified noncommercial internal processing under attribution, component,
> privacy, and source-specific safeguards. Their availability does not by
> itself authorize public release.

### 10.2 Intended final-paper wording, only after rights audit

> We release the evaluator, schemas, metric implementation, source/split
> manifests, checksums, baseline recipes, and all annotations or reconstruction
> metadata for which affirmative release authority exists. Restricted or
> non-redistributable source-derived artifacts are excluded from the public
> package and are identified in the release bill of materials. Raw media and
> third-party model weights are redistributed only when separately authorized.

If the final evaluation remains restricted, write:

> AV-TRACE reports a restricted internal evaluation with a public protocol and
> evaluator package; it is not presented as a fully redistributable media
> benchmark.

### 10.3 Reproducibility checklist

- exact source/page/object identity, hashes, duration, lineage, and split;
- exact model repository/revision or dated API snapshot;
- prompt, tool schema, metric, threshold, budget, and environment hashes;
- full action/response trajectories and typed invalid-run records;
- deterministic ranking tie-breaks and replay seeds;
- source-cluster analysis code and resampling seeds;
- independent metric/replay/leakage audit;
- release bill of materials, attribution, privacy, takedown, and replacement
  policy;
- no silent fallback, model substitution, retry selection, or evaluator-private
  answer mapping.

## 11. Limitations text for the paper

1. **Construct cost and scale.** Exhaustive alternative-evidence search and
   human adjudication are expensive; 60 families cannot represent all
   long-video tasks.
2. **Source/domain coverage.** Findings are bounded to the frozen sources,
   domains, languages, durations, and intervention strata.
3. **Public-source contamination.** Foundation models may have encountered
   source material during pretraining; support/citation endpoints and
   question/metadata controls mitigate but cannot prove absence of memorization.
4. **Perception versus policy.** Textualized A/V observations may introduce
   perception errors and do not equal native audiovisual understanding.
5. **Intervention idealization.** C/B/R manipulates registered evidence access,
   not every real-world sensor, network, or tool failure.
6. **Non-unique evidence.** Alternative SES discovery can change necessity and
   intervention eligibility; saturation is empirical, not a proof of universal
   absence.
7. **Statistical power.** Source groups are the independent units; low-source
   strata are descriptive even when they contain many episodes.
8. **Model coverage and drift.** Results are bounded to pinned local models and
   dated API snapshots; API systems may not remain exactly reproducible.
9. **Rights and privacy.** Some scientifically usable assets may remain
   restricted or reconstructable rather than redistributable.
10. **No universal ranking.** The benchmark diagnoses behavior under its
    protocol and does not establish global model quality or safety.

## 12. Reviewer objections and required evidence

| Objection | Evidence required before submission | If absent |
|---|---|---|
| “This is incremental over evidence-centric long-video and sufficiency-agent work.” | Updated dated primary-source matrix; two-reader novelty-language audit; every novelty sentence names the matched intervention/common endpoint/no-trigger/trace distinction. | Remove priority language and narrow contribution. |
| “The evidence labels are generated by the authors/models, not valid gold.” | Independent role-complete H2 records, alternative-SES saturation, adjudication, disagreement and rejection reports. | No benchmark-valid or human-gold claim. |
| “Deleting one preferred clip does not remove all sufficient evidence.” | All accepted SES ledger, blind full-source search, leave-one-out, necessity hitting sets, derived-route closure, final saturation audit. | Quarantine family or report route incompleteness. |
| “Modality use is not modality necessity.” | Human modality-drop answerability over every accepted SES and derived representation. | Use routing/corroboration wording only. |
| “BLOCKED/RESTORED is detectable from artifacts.” | Visibility diff, taint scan, non-semantic state classifier, exact replay, no-trigger matrix. | Remove causal recovery claims. |
| “Prompt tuning leaked the evaluation.” | Chronological source/family development ledger, source quarantine, pre-run prompt/config hashes, untouched test split. | Exclude touched sources or invalidate claim. |
| “The controller is too weak; this measures JSON failure.” | New unseen competence suite meeting Gate C; stronger model-family sensitivity; typed invalid accounting. | No learned-agent scientific run or narrow to tested models. |
| “The result is just retrieval recall.” | Oracle/partial evidence, observed-evidence lock, acquisition-conditioned analysis, at least two non-retrieval failures across multiple sources. | Reframe as retrieval benchmark/negative result. |
| “One source or template drives the result.” | At least 20 source groups, source-cluster intervals, leave-one-source/domain-out and influence analysis. | No broad headline; acquire sources or remain descriptive. |
| “Episodes are pseudo-replicates.” | Family pairing, within-source aggregation, source bootstrap/permutation, exact denominators. | No inferential comparison. |
| “Metrics are self-confirming.” | Independent implementation, row-level diff, human support/citation audit, executable route certificates. | Block all metric-dependent claims. |
| “The agent sees textual proxies, not A/V.” | Perception provenance, human observation audit, native-modality baseline or explicitly narrow scope. | Remove broad audiovisual capability language. |
| “Release claims exceed rights.” | Asset-level rights decisions, public/restricted bill of materials, attribution, privacy and takedown policy. | Call it restricted and release only authorized artifacts. |
| “Too many endpoints invite cherry-picking.” | Timestamped analysis plan, primary contrasts and margins, Holm/BH families, all null/negative/invalid strata. | No directional headline. |
| “API baselines drift.” | Exact snapshot/date/parameters, request/response hashes, repeated variance, no silent fallback; primary claim reproducible without API-only row. | API row sensitivity-only or remove it. |

## 13. Six-week critical path from the active build

This schedule begins from the repository state observed on **2026-09-23**:
the four exact source acquisitions are complete, the canonical four-source
unbounded full-timeline build is actively running, and the real family-mining
framework is ready but blocked on that build. A missed gate enters
`REPAIR/HOLD`; it never compresses review, reuses held-out data, or weakens a
criterion.

| Week | Critical-path work | Frozen deliverables | Exit/stop rule |
|---|---|---|---|
| **1 — finish index and run real mining** | Let the active build finish; verify all five terminal artifacts, complete/non-smoke status, four-source counts, self-hashes, checkpoints, no family leakage, and independent replay. Then execute real P-tier mining, preserving official sidecars as non-citable challenge routes. Add two NOAA development-source slots and two excluded calibrations without touching future test eligibility. | Frozen four-source index; independent index audit; real P0/P1/P2 candidate registry; 12 reported candidate slots + 2 excluded calibrations or explicit shortfall report. | If the index fails, repair and rerun. If mining cannot fill honest strata, relabel/reject; never quota-force. Gate A is still not GO merely because 12 records exist. |
| **2 — Gate A mobilization** | Human technical screening of complete sources; exact family packet construction; source/lineage/rights/privacy review; freeze six source groups, sampling seed, forms, protocol version, role assignments, calibration outcomes; train at least six reviewers. | Gate-A dossier and immutable candidate registry; reviewer roster; packets; governance decision. | Decide `MINI_PILOT_INPUT_READY` GO/REPAIR/NO-GO. No scientific family run before GO. |
| **3 — independent human passes** | Author/verifier, blind full-source alternative search, validators A/B, retrieval-assisted challenge, leave-one-out, modality drops, shortcut and derived-route audit, pair-isolation and recovery-route checks. | Complete independent forms and search logs; repair/quarantine queue; labor ledger. | No adjudicated claim yet. Systematic route or modality failure triggers repair/no-go, not relabeling. |
| **4 — adjudication, saturation, Gate B** | Adjudicate all 12; run new-reviewer saturation; reopen every discovered route; freeze H1/H2/rejected registry, funnel, agreement, labor, rights and replay reports. | At least 9/12 H1 and 8/12 H2 for GO; pair-isolation failures ≤1/12; required source/stratum and governance conditions. | Decide Gate B GO/REPAIR/NO-GO. No scale-up if NO-GO. |
| **5 — strong learned competence in parallel with paper scaffolding** | Repair controller/finalizer only on consumed synthetic/development data; freeze a new unseen fictional suite; run and independently audit learned generator, ReAct, sufficiency agent, and selected stronger baseline readiness. Freeze main table scripts and statistical plan without viewing H2 test outcomes. | Gate-C evidence, exact model/prompt/config hashes, competence and failure report, preregistered margins/endpoints. | Gate C GO/REPAIR/NO-GO. Current v1/v2/v3 results do not satisfy this exit. |
| **6 — H2 mini diagnostic and scale decision** | Only if Gates B and C are GO: execute all accepted mini-pilot H2 C/B/R/no-trigger episodes for single-shot RAG, learned ReAct, learned sufficiency, oracle and partial-evidence diagnostics; independently replay and fill mini versions of Tables 4–7. | Gate-D report: answer/support divergence, multi-source failure categories, matched recovery, source denominators, invalids and costs; first-40 authorization dossier. | Decide `END_TO_END_DIAGNOSTIC_GO/REPAIR/NO_GO`; authorize only the first 40 scaled reviews if Gate E1 also passes. The final 60-H2 corpus and paper claim freeze remain post-six-week work. |

## 14. Claim-to-artifact matrix summary

The machine-readable matrix is authoritative for packaging. Human-readable
summary:

| Claim | Tier/status now | Current anchor | Promotion artifact |
|---|---|---|---|
| Audited matched execution exists | T0 supported | Task-100/105 audits and frozen metrics | None for engineering wording |
| Common-endpoint restoration and route certificates are implemented | T0 supported | thesis/metrics/audits | H2 learned run for empirical claim |
| Full-timeline/learned retrieval differences exist on provisional data | T1 descriptive | Scale-1A and Wave-R audits | H2 source-disjoint replication |
| Benchmark families are human-valid and interventions isolate necessity | T2 blocked | none; zero H1/H2 | Gate B, then corpus freeze |
| Answer correctness diverges from supported correctness | T3 hypothesis | metrics only | H2 learned held-out result |
| At least two non-retrieval failure stages occur | T3 hypothesis | operational definitions only | audited multi-source traces |
| Recovery is measurable and learned systems recover | T0 mechanics/T3 empirical blocked | deterministic mechanics | H2 C/B/R + no-trigger learned runs |
| Sufficiency control improves ReAct | T3 optional hypothesis | controller competence NO_GO | same-backbone passed systems + thresholds |
| Public benchmark core exists | TX/currently prohibited | release not authorized | complete release audit and evaluator package |
| AV-TRACE is first/unique/SOTA | TX prohibited | substantial related-work overlap | no planned promotion; only narrow dated wording if independently supported |

## 15. Final packaging decision

```text
READINESS_TOKEN = CVPR_MAIN_BLUEPRINT_READY__PAPER_CLAIMS_BLOCKED
BLUEPRINT_PACKAGE = READY
CURRENT_SCIENTIFIC_PAPER_CLAIMS = NOT_READY
CURRENT_ACTIVE_STEP = FOUR_SOURCE_CANONICAL_FULL_TIMELINE_BUILD
NEXT_STEP_AFTER_BUILD = REAL_MACHINE_PROVISIONAL_FAMILY_MINING
HUMAN_GOLD_CLAIM = PROHIBITED_CURRENTLY
NOVELTY_FIRST_CLAIM = PROHIBITED
PUBLIC_BENCHMARK_CLAIM = PROHIBITED_CURRENTLY
```

The shortest credible path is not more prose or immediate bulk annotation. It
is: finish and audit the active four-source full-timeline build, run honest real
family mining, pass Gate A, obtain H2 construct evidence, pass learned
competence, and only then run the matched H2 end-to-end diagnostic.
