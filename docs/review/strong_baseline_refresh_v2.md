# AV-TRACE strong learned-baseline refresh v2

**Task:** 148  
**Date:** 2026-09-23, Asia/Shanghai  
**Decision:** `STRONG_BASELINE_REFRESH_REPAIR`  
**Machine-readable companion:** `data/rehearsal_plan/strong_baseline_registry_v2.json`  
**Execution status:** planning and lightweight reconnaissance only

## 1. Executive decision

AV-TRACE has a defensible **primary two-family baseline design**, but it is not
technically ready for scientific execution.

The exact recommended primary matrix is:

| Required role / row | Exact primary choice | Family | Status |
|---|---|---|---|
| `DIRECT_AV_MODEL`; `DLC-B` | `Qwen/Qwen2.5-Omni-7B` at `ae9e1690543ffd5c0221dc27f79834d0294cba00` | Qwen Omni | Official exact snapshot was metadata-reachable on 2026-09-23; native video plus in-video audio is documented; not acquired or load-tested |
| `TOOL_CONTROLLER_BACKBONE`; `RAG-A`, `REACT-A`, `SUFF-A` | `ibm-granite/granite-3.3-8b-instruct` at `51dd4bc2ade4059a6bd87649d68aa11e4fb2529b` | IBM Granite | Official exact snapshot was metadata-reachable on 2026-09-23; function-calling and long-context tasks are documented; not acquired or load-tested |
| `GROUNDED_FINALIZER`; `ORACLE-A`, `PARTIAL-A` | the same exact Granite snapshot and tokenizer as the controller | IBM Granite | Same-backbone finalizer is required to avoid a hidden capacity change; not acquired or competence-tested |
| Close published-style comparator | `TRACE_STYLE_CONVERGENCE_A`, an AV-TRACE-authored visual-subset adapter using the same Granite finalizer and frozen backend | TRACE-inspired, not an upstream model | Primary paper and official repository were reachable; upstream repository still said `Method Coming soon`, so this must not be called an official TRACE reproduction |
| Deterministic controls | existing `DET-REACT`, `DET-SUFF`, plus `NO-TRIGGER` | non-learned | Required controls; never substitutes for a learned output |

This satisfies the intended two-family design with **Qwen Omni** for native
audiovisual direct conditioning and **IBM Granite** for the shared learned RAG,
ReAct, sufficiency, and grounded-finalizer rows. It does not assume that either
model is competent before the sealed gates pass.

The exact fallback matrix is:

| Required role / row | Exact fallback choice | Limitation |
|---|---|---|
| Direct packed audiovisual row | `microsoft/Phi-4-multimodal-instruct` at `93f923e1a7727d1c4f446756212d9d3e8fcc5d81` | Accepts image and audio in one model and supports multi-frame/video-clip tasks, but the AV-TRACE adapter would supply deterministic sampled frames plus audio rather than a native continuous-video object. It is therefore a disclosed packed-AV fallback, not automatically a substitute for the strict native-video primary row. The official recipe uses `trust_remote_code=true`, which is prohibited until the exact code is archived and reviewed. |
| Shared RAG/ReAct/Suff/finalizer backbone | `Qwen/Qwen3-8B` at `b968826d9c46dd6066d109eabc6255188de91218` | Different from the failed Qwen2.5 snapshots, but still a Qwen-family controller and not acquired or tested. If paired with Phi-4, the fallback matrix retains two materially different families. |
| Published-style comparator fallback | `LONGVT_STYLE_CROP_A` on the eligible visual subset, using the frozen AV-TRACE crop action and the selected fallback finalizer | The official LongVT repository and released method are now reachable, but its released checkpoint/runtime is heavyweight and its exact behavior is not a drop-in match. Any AV-TRACE implementation is an adaptation, not an official reproduction. |

There is currently **no fully cleared strict native-video-plus-audio fallback**
if Qwen2.5-Omni fails. Phi-4 is the bounded repair route, not a claim that the
strict direct-row requirement is already met.

The decision is `REPAIR`, rather than `NO_GO`, because exact plausible routes
exist and the required architecture is implementable. It is not `READY`
because no selected new model is acquired, technically loadable, or competent;
no usable GPU is exposed to this process; and scientific evaluation remains
blocked by both model gates and the H2/causal-execution gates.

## 2. Non-result and authorization boundary

This task performed no model inference, no paid API call, no large weight
download, no GPU reservation, and no scientific-family execution. It did not
inspect an evaluator-private key or create a human label.

The following states are separate and must never be collapsed:

1. **Model or route discovered:** an official model/paper/repository route was
   identified.
2. **Exact snapshot reachable:** exact immutable model metadata or the exact
   paper/repository surface was retrieved on the stated date.
3. **License/privacy acceptable:** the exact license and intended data path
   have completed the applicable legal, privacy, retention, and rights review.
4. **Acquisition authorized:** a named decision authorizes file transfer or
   paid API use.
5. **Technically loadable:** the exact bytes load offline in the frozen runtime
   with the declared dtype, processor, memory, and security settings.
6. **Competence passed:** the frozen sealed fictional suite passes every gate.
7. **Scientific evaluation authorized:** all H2, intervention-v2, leakage,
   split, and execution gates independently authorize evaluation.

For every selected learned row in this report, states 4--7 are currently
false. A reachable model is not an acquired model; an acquired model is not a
loadable model; and a loadable model is not a competent or scientifically
authorized model.

## 3. Evidence reviewed

The refresh is subordinate to:

- `docs/paper/cvpr_pivot_decision_and_6week_plan.md`;
- `docs/paper/av_trace_cvpr_evaluation_preregistration.md`;
- `docs/paper/av_trace_cvpr_main_blueprint_v2.md`;
- `docs/review/cvpr_main_blueprint_v2_redteam.md`;
- `docs/review/strong_agent_baseline_plan.md`;
- `docs/review/gpt_oss_20b_acquisition_preflight.md`;
- `docs/design/exogenous_restoration_protocol_v2.md`;
- `data/rehearsal_plan/exogenous_restoration_protocol_v2.json`;
- controller v1, capacity, v2, and v3 design/audit artifacts; and
- the existing learned generator/controller schemas and implementation under
  `src/av_trace_scale1b_agent`, `src/av_trace_controller_v2`, and
  `src/av_trace_controller_v3`.

The failed historical controller evidence remains:

| Controller | Safe result | Consequence |
|---|---|---|
| Qwen2.5-1.5B v1 | 10/16 valid; 1/4 oracle-evidence supported answers | `NO_GO` |
| Qwen2.5-7B capacity row | 11/16 valid; 1/4 oracle-evidence supported answers | `NO_GO`; not a strong fallback |
| Qwen2.5-7B v2 | 28/28 action syntax, 15/28 correct action, 0/28 exact state, 0/8 terminal | `NO_GO`; grammar did not solve semantics |
| Qwen2.5-7B v3 development | 14/16 action, 0/16 joint state, 1/8 terminal | `NO_GO`; consumed development data only |

Unsupported required claims were zero in these studies, but that safety
property does not establish action, state, answer, abstention, or restoration
competence.

## 4. Fresh non-invasive host inventory

Observed on 2026-09-23 at approximately 20:04 Asia/Shanghai:

| Resource | Observation | Baseline consequence |
|---|---|---|
| CPU | 2 sockets, 96 physical cores/socket, 384 logical CPUs; AMD EPYC 9K84 | Metadata work, preprocessing, indexing, and bounded CPU smoke tests are possible |
| RAM | 2.2 TiB total; about 1.5 TiB available; no swap | Capacity is ample, but every load must have an RSS limit because there is no swap |
| Workspace disk | about 22 PiB total, 5.3 PiB available | Disk capacity is not the bottleneck; authorization and exact allowlists remain mandatory |
| `/tmp` disk | about 24 TiB total, 17 TiB available | Suitable only for bounded temporary metadata/runtime work |
| Local CUDA | `torch.cuda.is_available() == false`, device count 0 | Treat this process as CPU-only |
| GPU visibility | `nvidia-smi` could not communicate with the driver | Per-device occupancy and free VRAM could not be verified |
| Unrelated jobs | a separate Ray process advertises `accelerator_type:H20` and seven GPUs | Treat every accelerator as unavailable; do not attach to, reserve, inspect through Ray, stop, or slow that job |

Relevant package/runtime observations:

- Python `3.13.11`;
- PyTorch `2.10.0`, torchvision `0.25.0+8ac84ee`,
  torchaudio `2.10.0+27b7ebd`;
- Transformers `5.2.0`, tokenizers `0.22.2`, Accelerate `1.9.0`,
  huggingface-hub `1.5.0`, safetensors `0.7.0`;
- PyAV `16.1.0`, NumPy `1.26.4`, SciPy `1.18.0`;
- OpenAI SDK `2.24.0`, vLLM `0.16.0.post1+a572baff5`,
  OpenAI Harmony installed, qwen-vl-utils installed;
- `ffmpeg`, `ffprobe`, `decord`, `soundfile`, `librosa`, `bitsandbytes`,
  SGLang, FAISS, and sentence-transformers are absent; and
- the NumPy/SciPy environment emits a compatibility warning. This is relevant
  to the prior GPT-OSS import failure and requires an isolated runtime rather
  than in-place mutation of the shared environment.

No package was installed or modified by this task.

### 4.1 Exact local model snapshots

The following exact local snapshots were found:

| Snapshot | Local size / role |
|---|---|
| `openai/whisper-tiny.en` local `87c7102` snapshot | 148 MiB; speech observation support |
| `MIT/ast-finetuned-audioset-10-10-0.4593` local `f826b80` snapshot | 331 MiB; event-label diagnostic, not audio-text retrieval |
| `openai/clip-vit-base-patch32` local `3d74acf` snapshot | 581 MiB; visual retrieval legacy |
| `google/siglip2-base-patch16-224` at `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2` | 1.5 GiB; learned visual retrieval |
| `laion/clap-htsat-unfused` at `8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a` | 590 MiB; learned audio-text retrieval |
| `Qwen/Qwen2.5-1.5B-Instruct` at `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` | 2.9 GiB; historical weak generator/controller |
| `Qwen/Qwen2.5-7B-Instruct` at `a09a35458c702b33eeacc393d103063234e8bc28` | 15 GiB; historical failed controller comparator |

None of the newly selected Qwen Omni, Granite, Phi-4, or Qwen3 snapshots is
present locally.

## 5. Candidate-stack evaluation

### 5.1 Native video plus audio

**Primary: Qwen2.5-Omni-7B.** The official exact-revision model card and
license were reachable. It describes one model that accepts text, images,
audio, and video, can use audio embedded in video, and aligns video and audio
time. The exact metadata listed five safetensors shards totaling
22,362,861,192 bytes. The official card's BF16 minimum-GPU table reported
31.11 GB for 15 seconds, 41.85 GB for 30 seconds, and 60.19 GB for 60 seconds,
while warning that practical use is usually at least 1.2 times higher.

Consequences:

- reserve about 32 GiB disk for the reviewed snapshot and manifests;
- reserve at least 64 GiB host RAM for a bounded load test;
- plan roughly 40/52/73 GB usable VRAM for 15/30/60-second BF16 canaries after
  applying the card's stated 1.2x practical factor;
- a dedicated 80 GB-class GPU is the conservative 60-second target, but none
  is available to this task;
- never feed a full long source naively; use the frozen question-independent,
  source-uniform chronological packer and report exactly how many source
  seconds, frames, and audio seconds were exposed.

The current environment is not technically ready: the dedicated Omni utility
package is not inventoried, `ffmpeg`/`decord` are absent, no GPU is usable, and
no processor/config/load smoke was run.

**Fallback: Phi-4-multimodal-instruct.** Its exact metadata listed
12,810,242,408 bytes of main and modality-adapter safetensors, MIT metadata,
image and audio inputs, multi-frame/video-clip use, a 128K context claim, and
function calling. It is smaller than Qwen Omni. However, its documented
AV-TRACE route is sampled frames plus audio, and its official loading example
uses remote code. It is therefore a conditional packed-AV fallback only.

### 5.2 Video plus text without native audio

`HuggingFaceTB/SmolVLM2-2.2B-Instruct` at
`482adb537c021c86670beed01cd58990d01e72e4` remains the previously verified
small video/text candidate. It may support a disclosed visual/video direct
ablation with transcript or event text, but it cannot satisfy the native
ambient-audio requirement and must not be labeled the primary audiovisual
direct row.

### 5.3 Text/tool controller over frozen audiovisual observations

**Primary: Granite-3.3-8B-Instruct.** Exact official metadata showed four
safetensors shards totaling 16,341,771,384 bytes. The official card describes
an 8B, 128K-context instruct model trained for reasoning, instruction
following, function-calling, and long-context tasks. It is materially
different from Qwen2.5 and from the Qwen Omni direct model.

Use the same exact Granite weights for:

- single-shot RAG generation;
- learned ReAct decisions;
- learned evidence-sufficiency decisions; and
- the grounded finalizer and oracle/partial diagnostics.

This avoids giving the sufficiency controller or RAG row a hidden stronger
generator. Plan 24 GiB restricted disk and 24--32 GiB RAM for the first BF16
CPU load canary. Throughput is unknown and must be measured.

**Fallback: Qwen3-8B.** Exact official metadata showed five safetensors shards
totaling 16,381,516,776 bytes, Apache-2.0 metadata, native 32,768-token context,
and documented agent/tool integration. It is not the failed Qwen2.5 snapshot,
but its family relation must be disclosed and it must independently pass the
same gates.

**Do not require GPT-OSS-20B.** The exact official HF metadata was reachable
again and identified revision
`6cee5e81ee83917806bbde320786a8fb61efebee`, but
`GPT_OSS_20B_ACQUISITION_NO_GO` remains controlling. The fresh metadata check
does not repair its Python import, CPU BF16 fallback, unavailable accelerator,
kernel, load, or competence blockers. GPT-OSS is a reserve candidate only.

### 5.4 API route

The prior 2026-09-22 plan records OpenAI
`gpt-5.4-2026-03-05` through `POST /v1/responses` as a possible exact-snapshot
tool controller. Fresh official developer-document checks returned HTTP 403
on 2026-09-23 before the user stopped probes. Therefore freshness was **not**
re-established and the prior price, retention, media, and feature observations
are dated evidence only.

No paid call is authorized. Before reconsideration, the exact snapshot,
account availability, returned model identity, price, `store=false`
semantics, abuse-monitoring retention, Zero Data Retention eligibility,
regional processing, media-upload policy, strict structured outputs, and
function-call behavior must all be archived on the actual execution date.
Raw media, evaluator-private data, accepted SESs, triggers, answer keys, and
route certificates may never be uploaded. The required paper matrix does not
depend on an API.

## 6. Frozen experiment matrix

### 6.1 Primary matrix

| ID | Model and route | Frozen contract |
|---|---|---|
| `DLC-B-QWEN25OMNI7B` | Qwen2.5-Omni-7B native video plus audio | One non-agent generation over state-accessible, question-independent chronological packing; same strict final schema |
| `RAG-A-GRANITE33-8B` | Granite single-shot RAG | One visual, speech, and ambient query at `top_k=5`; F-CTRL fusion; inspect/read under cost 12; one finalizer call |
| `REACT-A-GRANITE33-8B` | Granite ordinary ReAct | Shared backend/action/finalizer/budget contract |
| `SUFF-A-GRANITE33-8B` | Granite explicit six-field sufficiency control | Differs from ReAct only in frozen controller prompt/interface |
| `ORACLE-A-GRANITE33-8B` | Granite with canonical complete H2 SES | Diagnostic only |
| `PARTIAL-A-GRANITE33-8B` | Granite with preregistered insufficient proper subset | Diagnostic only |
| `TRACE-STYLE-A-GRANITE33-8B` | AV-TRACE-authored visual-subset convergence comparator | Iterative visual retrieval, growing evidence bundle, two consecutive stable answers, then a final pass over the same evidence; not an official reproduction |
| `DET-REACT`, `DET-SUFF` | deterministic policies | Controls only |
| `NO-TRIGGER` | restoration-disabled sham continuation | Required for recovery claims |

The primary learned agent budget remains:

- maximum 10 canonical actions including `finalize`;
- cost limit 12.0;
- `top_k=5`;
- 32,768 processor-token context cap;
- 512 new tokens per decision/finalization;
- maximum 12 model calls including one schema-only repair;
- no semantic repair, voting, best-of-N, answer substitution, or
  model-specific retry.

The direct and oracle/partial rows receive one generation plus at most one
schema-only repair. Structural ineligibility is null with a reason code, never
scored as zero.

### 6.2 Fallback matrix

| ID | Model and route | Frozen contract |
|---|---|---|
| `DLC-B-PHI4MM` | Phi-4 deterministic sampled-frame plus audio packing | Provisional packed-AV row; strict native-video equivalence not claimed |
| `RAG-A-QWEN3-8B` | Qwen3 single-shot RAG | Same F-CTRL and final schema |
| `REACT-A-QWEN3-8B` | Qwen3 ordinary ReAct | Same common action contract |
| `SUFF-A-QWEN3-8B` | Qwen3 sufficiency controller | Same Qwen3 backbone/finalizer |
| `ORACLE/PARTIAL-A-QWEN3-8B` | Qwen3 diagnostics | Same exact finalizer |
| `LONGVT-STYLE-A-QWEN3-8B` | adapted visual crop loop | Eligible visual subset only; no official-reproduction claim |

The fallback matrix may replace the primary only after a versioned registry
amendment made before sealed competence outputs. Rows may not be mixed after
seeing outcomes to manufacture a passing matrix.

## 7. Adapter boundaries

### 7.1 Structured tool actions

Expose only:

`search_visual`, `search_speech`, `search_ambient_audio`, `inspect_clip`,
`read_transcript`, `get_channel_status`, and `finalize`.

The model emits one native function call or one schema-constrained action per
turn. The adapter:

- validates exact keys/types/enums and case-local action legality;
- maps losslessly into `docs/spec/agent_action_schema.json`;
- records model bytes, parse result, action fingerprint, tokens, latency, and
  hashes; and
- may reject but may not infer a missing action, rewrite a query, create a
  citation, fill a state field, or answer.

### 7.2 Six-field evidence state

The learned state is exactly:

1. `p_sufficient`;
2. `covered_claim_handles`;
3. `missing_modalities`;
4. `missing_hops`;
5. `missingness_cause`; and
6. `recovery_intent`.

Use one canonical object if the model proves reliable serialization. A
factorized native-tool form is allowed only if frozen before the sealed suite
and recombined mechanically without semantic filling. The state is diagnostic
and may never become answer text or citations.

### 7.3 Claim/citation finalization

Use the existing strict final-answer schema:

- all assertions and answer text are model-authored;
- citations are exact observed `observation_id` values;
- the redundant claim-to-citation map must exactly match assertions;
- only public claim handles may be named;
- evaluator mapping to accepted support remains post hoc and private; and
- malformed or unsupported output after one schema-only repair is invalid.

The same grounded finalizer snapshot, prompt, schema, decoding, and failure
policy is shared by RAG, ReAct, and sufficiency rows.

### 7.4 Staged exogenous restoration v2

Every recovery-eligible learned row must:

- pause after four completed canonical action/response cycles;
- fork one frozen blocked prefix into fresh `R` and `N` continuation sessions;
- receive the byte-identical neutral protocol checkpoint in both arms;
- restore the evaluator-private route only in `R`;
- continue under unchanged remaining budget; and
- preserve identical public transcript hashes through the checkpoint.

No restoration may depend on action identity, `get_channel_status`, answer
content, model state, or outcome. A non-staged direct system is declared
`STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT` for the primary R-minus-N
estimand and may appear only in state-endpoint tables.

### 7.5 Observed-evidence lock

At each model call, derive an immutable allowlist from the current trajectory.
The model receives only:

- public question and public claim slots;
- public action/budget history;
- currently observed citable records; and
- non-citable search pointers explicitly marked as non-citable.

Final validation rejects unknown observation IDs, unobserved content,
out-of-interval citations, pointer citations, private handles, future
restoration knowledge, and any claim unsupported by acquired observations.
Oracle and partial diagnostics use separate frozen observation bundles and
never expose why a member was selected or removed.

### 7.6 Deterministic fallback behavior

A learned-run failure may produce only a typed invalid result:

- malformed after one schema repair: no dispatch or answer;
- illegal action: no inferred action;
- timeout/provider/process/OOM: terminate invalid;
- context overflow after frozen compaction: terminate invalid;
- invalid finalizer: retain no substituted answer; and
- model/snapshot mismatch: stop before the call.

`DET-REACT` and `DET-SUFF` are independent control systems. Their outputs may
never replace a failed learned output.

## 8. Competence suite and exact gates

No scientific family, evaluation source, or evaluator-private key may be read.
Create new fictional, source-free cases and freeze case, media, prompt, schema,
runtime, thresholds, and evaluator hashes before a selected model sees them.

### 8.1 Controller/finalizer suite

Use at least 48 sealed cases covering:

- visual, speech, and ambient initial routing;
- inspect/read selection;
- one- and two-claim complete evidence;
- exact observation-ID citation;
- partial and blocked evidence;
- inaccessible/not-found/absent distinction;
- repeated-action/no-progress guard;
- exogenous restoration and reacquisition;
- no-trigger;
- adversarial menu ordering and distractors/conflicts; and
- malformed tool output, timeout, budget exhaustion, model identity failure,
  and provider/process failure.

Every selected controller/finalizer must independently pass:

- 100% deterministic parser/schema/failure-injection fixtures;
- at least 90% valid structured model calls after at most one repair;
- at least 85% correct first actions overall and at least 75% in every frozen
  action stratum;
- at least 75% exact six-field state and at least 80% for every component;
- at least 80% supported-answer success on complete/oracle-evidence cases;
- at least 80% correct abstention and typed insufficiency on blocked/partial
  cases;
- at least 80% restoration/reacquisition success on eligible cases;
- zero unsupported required claims;
- zero private-field exposure;
- zero deterministic answer substitution; and
- 100% fail-closed behavior under identity mismatch and injected failure.

These are the existing frozen floors and are not weakened to accommodate an
8B model.

### 8.2 Native/packed AV direct suite

Use at least 24 sealed synthetic audiovisual cases, balanced across
vision-required, speech-required, ambient-required, jointly audiovisual, and
masked/partial conditions. Media must be generated from fictional primitives
and must not contain evaluation content.

The direct model must pass:

- 100% processor/input-manifest and injected-failure fixtures;
- at least 90% valid strict final outputs after at most one repair;
- at least 80% supported-answer success on complete-evidence cases;
- at least 75% supported-answer success in each preregistered modality
  stratum;
- at least 80% correct abstention/typed insufficiency on partial or masked
  cases;
- zero unsupported required claims and zero citations outside the direct
  exposure manifest;
- 100% observed-evidence-lock checks;
- all audio-required cases must fail or abstain appropriately under the frozen
  audio-drop counterfactual, and all vision-required cases under visual drop;
  and
- byte-identical parsed final outputs on deterministic local replay.

Passing a packed-frame Phi-4 suite does not by itself satisfy the strict
native-video Qwen Omni row.

## 9. Resource, runtime, and cost envelope

| Candidate | Exact known payload | Conservative preflight envelope | Current-host decision |
|---|---:|---|---|
| Qwen2.5-Omni-7B | 22.36 GB weights | 32 GiB disk; 64--96 GiB CPU RAM; dedicated 80 GB-class GPU preferred for 60-second BF16 canary | Metadata only; no usable GPU; do not acquire yet |
| Granite-3.3-8B | 16.34 GB weights | 24 GiB disk; 24--32 GiB CPU RAM; first canary CPU-only with strict RSS/time limits | Plausible CPU load route, unmeasured |
| Phi-4 multimodal | 12.81 GB known weight/adapters | 20 GiB disk; 32--48 GiB RAM/VRAM planning reserve; reviewed code required | Blocked by remote-code/security and unmeasured runtime |
| Qwen3-8B | 16.38 GB weights | 24 GiB disk; 24--32 GiB CPU RAM | Plausible CPU load route, unmeasured |
| GPT-OSS-20B | exact repo metadata reachable; selected MXFP4 about 13.8 GB, whole repo about 41.3 GB | Prior 64--96 GiB CPU BF16 preflight; accelerator path unresolved | Existing acquisition `NO_GO`; reserve only |

No throughput claim is made for an unmeasured candidate. Stop any future CPU
smoke if peak RSS exceeds its approved allocation, the host's available RAM
falls below the safety floor, or p95 synthetic episode wall time exceeds 60
minutes. A dedicated accelerator allocation must be explicit and must not use
the unrelated Ray/H20 job.

API cost is `UNVERIFIED_CURRENT`. The prior 2026-09-22 planning rates and
episode estimate are not operative after the failed fresh check. No budget may
be approved from stale pricing.

## 10. Stepwise acquisition and smoke-test plan

Every stage requires an explicit decision; success at one stage does not imply
authorization for the next.

1. **Metadata freeze, no weights.** Archive the exact official API response,
   card, license, config/tokenizer/processor file list, sizes, Git/LFS
   identities, required custom code, and security allowlist.
2. **Small-file runtime probe.** In a new isolated environment, load only
   config/tokenizer/processor from reviewed small files with network disabled.
   Reject unresolved remote code, pickle, dynamic kernel fetches, or version
   conflicts.
3. **License/privacy/compute decision.** Obtain named approval for the exact
   snapshot, intended internal use, retention, and dedicated resource
   allocation. This task grants none.
4. **Bounded acquisition.** Under `umask 077`, download only allowlisted files
   sequentially, verify upstream identities and local SHA-256, validate
   safetensors/index consistency, and atomically promote.
5. **Offline load canary.** Use `local_files_only=true`, network denial,
   reviewed code only, fixed dtype/runtime, one process, and strict RSS/time
   caps. No generation yet.
6. **One fictional generation/action smoke.** Run one tiny synthetic input,
   record latency/RSS/parser behavior, and stop on any mismatch.
7. **Unscored public fixtures.** Validate adapters, citations,
   observed-evidence lock, restoration fork, and deterministic invalid
   behavior.
8. **Sealed competence.** Freeze and run the suites in Section 8. No tuning on
   sealed cases.
9. **Technical gate review.** Only all-pass candidates may be proposed for
   `STRONG_BASELINE_TECHNICAL_READY`.
10. **Scientific gate review.** Separately require H2 eligibility, frozen
    source-disjoint split, intervention-v2 manifests, R/N replay, fresh-session
    attestations, passing metadata-only leakage gate, and explicit evaluation
    authorization.

Hard stop rules include:

- exact revision, file identity, license, or required code cannot be archived;
- payload exceeds its approved cap;
- runtime silently changes dtype/model/processor;
- remote code or dynamic binary/kernel material is unreviewed;
- no dedicated usable compute route exists;
- model identity or returned API identity differs;
- raw media or private evaluator fields would leave the approved boundary;
- any competence floor fails;
- unsupported required claims are nonzero;
- deterministic output substitution occurs;
- staged R/N transcript equality or cache isolation fails;
- leakage gate is not passed; or
- scientific execution has not been separately authorized.

## 11. Exact current blockers

1. `B148-01_SELECTED_SNAPSHOTS_NOT_ACQUIRED` — Qwen Omni, Granite, Phi-4, and
   Qwen3 are absent locally.
2. `B148-02_NO_USABLE_DEDICATED_GPU` — local CUDA is unavailable and the
   unrelated H20/Ray allocation is off limits.
3. `B148-03_RUNTIME_ENVIRONMENT_NOT_FROZEN` — required media dependencies are
   missing, the shared Python environment has a NumPy/SciPy warning, and
   model-specific import/config/processor loads are untested.
4. `B148-04_EXACT_LICENSE_SECURITY_ARCHIVE_INCOMPLETE` — metadata/card evidence
   exists, but exact per-snapshot legal/security review and allowlists are not
   complete for the selected matrix.
5. `B148-05_STRICT_NATIVE_AV_FALLBACK_NOT_CLEARED` — Phi-4 is only a packed-AV
   fallback and requires reviewed remote code.
6. `B148-06_COMPETENCE_NOT_RUN` — no selected direct model, controller, or
   finalizer has passed the frozen fictional suites.
7. `B148-07_TRACE_NOT_OFFICIAL_REPRODUCTION` — the official TRACE repository
   still has no method implementation; only an attributed AV-TRACE adaptation
   is currently possible.
8. `B148-08_API_FRESHNESS_AND_GOVERNANCE_UNRESOLVED` — fresh official OpenAI
   docs returned 403 and no privacy, retention, price, account, or paid-use
   approval exists.
9. `B148-09_H2_AND_CAUSAL_GATES_BLOCK_EXECUTION` — zero H2 families, the
   intervention-v2 metadata leakage gate is not run, and scientific evaluation
   is not authorized.

## 12. Official primary-source checks

All successful online checks were lightweight metadata/card/paper/repository
retrievals on 2026-09-23. Exact URLs, HTTP outcomes, immutable IDs, and
supported claims are recorded in the JSON companion. No freshness claim is
made for an inaccessible page.

Key checked surfaces included:

- exact Hugging Face model APIs/cards for Qwen2.5-Omni-7B, Granite-3.3-8B,
  Phi-4-multimodal-instruct, Qwen3-8B, Qwen3-Omni-30B-A3B-Instruct,
  Mistral-Small-3.2-24B-Instruct-2506, and GPT-OSS-20B;
- the official LongVT repository;
- the official TRACE repository; and
- the primary REVEAL and TRACE arXiv abstract pages.

The OpenAI developer model/data/function-calling pages were attempted but
returned HTTP 403 in the fresh check. Their prior 2026-09-22 observations are
retained as prior dated evidence only.

## 13. Final disposition

The baseline architecture and acquisition sequence are ready for bounded
repair work. The learned systems themselves are not ready.

```text
STRONG_BASELINE_REFRESH_REPAIR
```

