# AV-TRACE representative strong-agent baseline plan

**Plan date:** 2026-09-22  
**Decision:** `STRONG_AGENT_BASELINE_PLAN_READY`  
**Execution status:** `PLANNING_ONLY_NOT_AUTHORIZED`  
**Machine-readable companion:** `data/rehearsal_plan/strong_agent_baseline_registry.json`

## 1. Decision

AV-TRACE should add exactly two representative strong-agent sensitivity rows:

1. **Open-weight/local:** `openai/gpt-oss-20b`, pinned to Hugging Face
   revision `6cee5e81ee83917806bbde320786a8fb61efebee`.
2. **Closed/API:** OpenAI `gpt-5.4-2026-03-05` through
   `POST /v1/responses`, never the moving `gpt-5.4` alias in a scored run.

The plan is ready, but neither row is execution-ready. Acquisition, API use,
credentials, downloads, model inference, scientific-family access, and
evaluation remain separately gated and unauthorized by this document.

These rows are **baselines and capacity/provider sensitivities**, not the paper
contribution. AV-TRACE's proposed contribution remains the human-valid matched
evidence-access intervention and trace-grounded Acquire/Ground/Act diagnostic.
A stronger model succeeding does not make the model an AV-TRACE contribution;
a stronger model failing does not by itself validate AV-TRACE.

## 2. Evidence reviewed and motivation

This plan was derived from the frozen thesis/blueprint, R07/R12, the local
model inventory, and only safe aggregate controller results:

- `docs/paper/cvpr_thesis_and_evidence_gates.md`
- `docs/paper/cvpr_execution_blueprint.md`
- `docs/review/cvpr_pre_submission_risk_register.md`, especially R07 and R12
- `docs/design/scale1b_learned_baseline_inventory.md`
- `docs/review/controller_synthetic_competence.md`
- `docs/review/controller_capacity_sensitivity_qwen7b.md`
- `docs/review/controller_capacity_sensitivity_qwen7b_audit.md`
- `docs/review/controller_v2_holdout_evaluation.md`
- `data/restricted/scale1b/controller_v2_holdout_evaluation/safe_aggregate.json`
- `docs/design/controller_v3_factorized_state.md`
- `data/restricted/scale1b/controller_v3_dev/summary.json`
- `docs/review/strong_controller_model_acquisition.md`
- `data/restricted/scale1b/manifests/strong_controller_model_acquisition.json`

No scientific evaluation family or evaluator key is needed for this plan.

### 2.1 What v1-v3 establish

The existing controller sequence is valuable engineering evidence but does not
yet establish learned-agent competence:

| Version | Model/interface | Safe result | Consequence |
|---|---|---|---|
| v1 | Qwen2.5-1.5B, monolithic structured output | 10/16 valid outputs; 1/4 oracle-evidence supported answers; `NO_GO` | The original learned controller was below the R07 competence floor. |
| v1 capacity sensitivity | Qwen2.5-7B, same frozen interface | 11/16 valid outputs; 1/4 oracle-evidence supported answers; `NO_GO` | Replacing 1.5B with 7B did not resolve the competence concern. |
| v2 | Qwen2.5-7B, constrained action/state heads on sealed fictional holdout | 28/28 action and state syntax; 15/28 action correct; 0/28 exact state; 0/8 terminal correct; `NO_GO` | Grammar fixed serialization, not semantic state or finalization competence. |
| v3 | Qwen2.5-7B, six factorized state heads on consumed synthetic development data | 14/16 action correct; 0/16 exact joint state; 1/8 terminal correct; `NO_GO` | More calls and stronger factorization still left state estimation and terminal behavior far below gate. |

The strongest defensible next test is therefore not another small prompt edit.
It is a capacity/provider sensitivity using models selected for explicit
agentic tool use and structured output, while holding the AV-TRACE backend,
tools, observations, budget, finalizer schema, and failure semantics fixed.

## 3. Selected open-weight baseline

### 3.1 Identity and dated verification

| Field | Frozen plan value |
|---|---|
| Baseline ID | `strong_open_gpt_oss_20b` |
| Repository | `openai/gpt-oss-20b` |
| Exact revision | `6cee5e81ee83917806bbde320786a8fb61efebee` |
| License | Apache-2.0, subject to archival and legal review of the exact snapshot |
| Format | OpenAI Harmony chat/tool format |
| Planned weights | Official MXFP4 safetensors allowlist only; do not acquire optional original/full-precision material |
| Official verification date | 2026-09-22 |
| Official sources | OpenAI-owned Hugging Face model card and exact-revision tree |

On 2026-09-22, the official model card described gpt-oss-20b as a 21B-total,
3.6B-active MoE intended for local/specialized use, with configurable
reasoning, function calling, agentic use, Structured Outputs, Apache-2.0
licensing, and an MXFP4 form intended to fit within about 16 GB of memory. The
exact-revision tree exposed three selected MXFP4 safetensors shards totaling
about 13.8 GB plus configuration/tokenizer files.

This is a **dated candidate verification**, not a claim that the current
AV-TRACE runtime can load it or that it will pass AV-TRACE competence.

### 3.2 Why this is materially stronger and locally realistic

- It is a different model family and post-training regime from the failed
  Qwen2.5-1.5B/7B rows.
- It has substantially larger total parameter capacity than the existing 7B
  controller and explicit official support for reasoning, native function
  calling, and structured outputs.
- The official MXFP4 artifact is small enough for the inventoried host's RAM.
  The repository already ran Qwen2.5-7B CPU BF16 with roughly 16 GB peak RSS;
  the host inventory reports about 2.2 TiB RAM and 192 physical CPU cores.
- It does not require sending family content outside the local environment.

“Materially stronger” here means a credible stronger-capacity, explicitly
agentic baseline candidate. It does **not** assert superior AV-TRACE results
before the competence gate.

### 3.3 Runtime plan

- Primary runtime: pinned Transformers plus the exact snapshot, using the
  snapshot's chat template/Harmony format.
- Alternative runtime, only if Transformers cannot provide strict tool
  constraints: pinned vLLM or SGLang in a local-only process. Changing runtime
  requires a new runtime ID, environment lock, and full competence rerun.
- Network: denied during load and inference; `local_files_only=true`;
  `trust_remote_code=false` unless a separate source review explicitly changes
  the plan.
- Precision: official MXFP4 weights as distributed; no unregistered
  requantization for the primary row.
- Shared context cap: 32,768 tokens, even if the model supports more.
- Reasoning effort: `medium`, frozen before the sealed competence set.
- Sampling: greedy/deterministic where the runtime permits. Persist runtime,
  kernel, CPU/GPU, thread count, seed, and tokenizer/template hashes.
- Hidden reasoning: never requested as an evaluator output, never scored, and
  not copied into public traces. Store only the model's tool/final answer plus
  bounded operational metadata; if a runtime exposes reasoning text, keep it
  out of release artifacts.

### 3.4 Local compute estimate and hard preflight

Planning estimate, to be replaced by measurement:

- selected download: about 13.8 GB weights plus tokenizer/config/license/card;
- disk reservation: 20 GB for staging, snapshot, manifests, and logs;
- RAM reservation: 32 GB minimum, 64 GB recommended for context/KV-cache and
  implementation overhead;
- current host route: CPU is realistic for smoke and bounded runs because RAM
  is ample, but throughput is unverified;
- target accelerator route: one compatible GPU with at least 24 GB usable VRAM
  is preferred, but no GPU availability is assumed;
- expected CPU wall time: provisionally 0.5-5 generated tokens/s and
  10-45 minutes per ten-step episode. This is a scheduling estimate, not a
  measured result.

Stop before acquisition or evaluation if the exact selected files exceed
20 GiB, the staged total exceeds 24 GiB, the snapshot cannot be integrity
validated, Harmony/native tools cannot be reproduced, peak RAM exceeds the
declared allocation, or p95 episode wall time exceeds 60 minutes in the
synthetic preflight.

## 4. Selected closed/API baseline

### 4.1 Identity and dated verification

| Field | Frozen plan value |
|---|---|
| Baseline ID | `strong_api_openai_gpt54_20260305` |
| Provider | OpenAI API |
| Endpoint | `POST /v1/responses` |
| Exact model snapshot | `gpt-5.4-2026-03-05` |
| Moving alias policy | `gpt-5.4` may be used only for an availability probe, never for a scored call |
| Reasoning effort | `medium` |
| Service tier | default/standard, frozen in the run manifest |
| Storage request | `store=false` |
| Official verification date | 2026-09-22 |

On 2026-09-22, the official OpenAI model documentation listed
`gpt-5.4-2026-03-05` as a GPT-5.4 snapshot and reported function calling,
Structured Outputs, a 1.05M context window, and standard token pricing of
$2.50/M input tokens, $0.25/M cached input tokens, and $15/M output tokens.
AV-TRACE will cap context far below the model maximum and will use only local
AV-TRACE tools, not hosted web, computer-use, shell, file-search, or MCP tools.

The API row is conditional on a same-day, non-family preflight confirming that
the account/region can invoke the exact snapshot and that the returned model
identity is exactly the pinned value. A moving alias, silent substitution, or
provider retirement makes the row unavailable rather than eligible for a
fallback model.

### 4.2 API request contract

- Use native strict function calling with the seven AV-TRACE actions only.
- Set `parallel_tool_calls=false`; one model turn may select one action.
- Use strict JSON Schema for every function.
- Use the exact pinned model snapshot and a pinned OpenAI SDK version.
- Resend the explicit conversation/tool history needed for every turn so the
  archived request is self-contained. Do not depend on an unarchived provider
  conversation.
- If reasoning items or encrypted reasoning state are required by the Responses
  API, archive and resend the provider-returned item unchanged. Never synthesize
  or inspect hidden reasoning.
- No provider-hosted tools, browsing, code execution, file upload, vector
  store, or remote retrieval are allowed.
- No API response may be replaced with a local-model answer after failure.
  Provider error, timeout, refusal, malformed tool call, or identity mismatch
  is a typed invalid run.

### 4.3 Privacy and data-upload boundary

The provider request may contain only:

- the question and public claim-slot descriptions authorized for that run;
- the public action history;
- frozen tool schemas and budget state;
- pointer previews and citable textualized observations already returned by
  the common backend.

It may not contain raw video/audio, source files, evaluator-private claim
graphs, accepted SESs, necessity groups, intervention role, restoration
trigger, answer keys, reviewer forms, private route certificates, credentials,
or unrestricted source metadata.

API execution is prohibited until an item-level rights/privacy review
affirmatively allows off-host processing of the exact payload fields. OpenAI's
business/API documentation states that API data is not used to train models by
default, but that does not itself establish AV-TRACE upload authority or zero
retention. Before the first request, archive the account's then-current data
controls, retention terms, regional-processing setting, and any approved
Modified Abuse Monitoring or Zero Data Retention status. Use `store=false`,
but do not describe the run as zero-retention unless the organization is
actually approved and the selected endpoint/features are eligible.

### 4.4 Cost estimate and cap

The primary planning envelope per episode is:

- no more than 64,000 billed input tokens;
- no more than 6,000 billed output/reasoning tokens;
- no more than 12 model turns including one allowed schema repair;
- no provider-hosted tool charges.

At the 2026-09-22 standard rates, the uncached worst-case planning cost is
approximately:

```text
64,000 × $2.50/M + 6,000 × $15/M = $0.25 per episode
```

For the blueprint's 720 core episode-calls, this is a $180 upper-envelope
estimate; an additional 15% invalid/replay reserve gives $207. Actual cost must
come from provider usage records and may be lower with cached input. Provider
prompt caching is a billing/latency optimization only; it is not the AV-TRACE
reproducibility cache.

Stop API execution if the snapshot identity differs, price/terms are not
reverified on the run date, cumulative spend reaches the approved hard cap,
p95 cost exceeds $0.35/episode in competence testing, or the account cannot
satisfy the approved data-handling boundary.

## 5. Fair shared experiment contract

The strong rows must differ only in model/provider/runtime. They must not get a
better backend or larger search budget.

### 5.1 Common backend and observations

- Primary retrieval/backend: the same frozen F-CTRL backend used by all agent
  rows; F-VA is a separately labeled retrieval sensitivity.
- Same immutable indexes, candidate universe, ASR/decoder derivatives, result
  order, intervention manifest, restoration trigger, and error vocabulary.
- Search results are non-citable pointers. Only `inspect_clip` and
  `read_transcript` outputs are citable.
- Models receive textualized public observations, not raw source media. This
  makes the controller sensitivity comparable and prevents the API row from
  receiving privileged audiovisual input.
- Same canonical observation serializer, truncation policy, and context
  compaction. If the 32,768-token cap would be exceeded, apply a frozen
  model-agnostic oldest-event compaction that preserves all citable
  observations and budget/status events; otherwise mark the episode invalid.

### 5.2 Common actions and budget

Use the existing AV-TRACE tool contract:

| Action | Cost |
|---|---:|
| `search_visual` | 1.0 |
| `search_speech` | 1.0 |
| `search_ambient_audio` | 1.0 |
| `inspect_clip` | 2.0 |
| `read_transcript` | 1.0 |
| `get_channel_status` | 0.25 |
| `finalize` | 0.0 |

Primary budget: `max_steps=10`, `cost_limit=12.0`. A separately preregistered,
unpooled budget sensitivity may use `max_steps=20`, `cost_limit=24.0`.
`top_k`, time-range limits, clip duration, transcript span, result shape, and
repair allowance are frozen per experiment and identical across rows.

One model call selects one action. At most one schema-only repair is allowed
after a malformed action/finalization; it counts as a model call and token/API
cost but not as an additional backend action. No semantic correction prompt,
majority vote, best-of-N selection, or model-specific retry is allowed.

### 5.3 Native tools and canonical action mapping

Expose one strict native function for each available AV-TRACE action. Each
function schema contains:

- `protocol_version`, `episode_id`, `request_id`, and `step_index`;
- the existing public `belief_state`;
- only the arguments legal for that tool.

The adapter performs a mechanical, lossless mapping from the native function
call into `docs/spec/agent_action_schema.json`. It may validate and reject; it
may not infer a missing action, rewrite a query, alter belief values, create a
citation, or substitute an answer.

For the local row, the native call is parsed from Harmony tool output. For the
API row, it is parsed from Responses API function-call items. Both then enter
the identical backend dispatcher and trajectory validator.

### 5.4 Evidence citation and finalizer interface

`finalize` is a strict native function whose arguments are exactly
`docs/spec/final_answer_schema.json`:

- every claim is model-authored;
- citations may name only observation IDs actually returned to that model;
- intervals and modalities must equal the cited observation metadata;
- `registered_claim_id` may use only public claim handles;
- answer, partial answer, and abstention obey the existing verdict and
  diagnosis semantics;
- final belief-state probabilities must agree with final-answer probabilities;
- invalid or unsupported output fails closed.

The evaluator-private mapping from public handles/observations to accepted
support derivations remains post hoc and inaccessible to both models. The
final-point route-feasibility certificate also remains evaluator-private.

## 6. Competence preflight before any scientific family

Create a new source-free fictional suite. Do not reuse the consumed Task-111
development cases as an unseen gate, do not reopen r017, and do not expose any
scientific family or evaluator key.

### 6.1 Required strata

At minimum:

1. visual, speech, and ambient initial routing;
2. pointer inspection and transcript reading;
3. exact observation-ID citation;
4. one- and two-claim complete-evidence finalization;
5. partial evidence with calibrated non-answer;
6. inaccessible versus not-found versus absent diagnosis;
7. no-progress/repeated-action guard;
8. restoration status check and reacquisition;
9. no-trigger control;
10. adversarial menu/tool ordering;
11. distractor and conflicting observation handling;
12. malformed tool output, timeout, budget exhaustion, and provider failure.

Use at least 48 sealed cases, balanced across the main capabilities, plus
unscored public parser fixtures. Freeze case, prompt, tool-schema, runtime,
threshold, and evaluator hashes before either model sees a sealed case.

### 6.2 Frozen minimum gates

Each selected strong baseline must independently pass:

- 100% deterministic parser/schema/failure-injection fixtures;
- at least 90% valid structured model calls after at most one repair;
- at least 85% correct first actions overall and at least 75% in every
  preregistered action stratum;
- at least 75% exact public state and at least 80% per state component, using
  either one canonical state object or a frozen equivalent native-tool schema;
- at least 80% supported-answer success on complete/oracle-evidence cases;
- at least 80% correct abstention/typed insufficiency on blocked or partial
  cases;
- at least 80% restoration/reacquisition success on eligible cases;
- zero unsupported required claims;
- zero private-field exposure and zero deterministic answer substitution;
- 100% fail-closed behavior under snapshot/API mismatch and injected provider
  failure.

For the API row, repeat every canary three times and repeat a frozen stratified
20% of the sealed competence cases. Report exact-match action/finalization
variance. If endpoint success differs by more than 5 percentage points or any
case changes between supported answer and unsupported answer, the row is
`NONDETERMINISTIC_NOT_READY` until a preregistered repeat/aggregation policy is
approved.

Passing authorizes only a separately frozen, human-valid evaluation plan. It
does not itself establish `LEARNED_AGENT_READY`.

## 7. API caching, replay, and drift control

### 7.1 Content-addressed cache

Before any API request, canonicalize and hash:

- provider and exact model snapshot;
- endpoint and pinned SDK/API version;
- reasoning effort, service tier, output limits, and storage flag;
- system/developer prompt bytes;
- full ordered input/tool history;
- strict tool definitions and schema hashes;
- backend, episode-public-packet, and observation-serializer versions.

The SHA-256 digest is the cache key. A cache hit returns the immutable archived
provider response without network access. A cache miss is the only condition
that may issue an API request.

Store under a restricted future run root with `0700` directories and `0600`
files:

- canonical request JSON;
- raw response JSON;
- request/response SHA-256;
- response model identity;
- provider request ID and relevant headers;
- usage tokens, cached-token count, latency, retries, error body, and cost;
- parsed action/finalization and validator result.

Credentials and authorization headers are never persisted. Public release
contains hashes, configuration, aggregate usage/cost, and redacted traces only.

### 7.2 Replay modes

1. **Offline exact replay:** no network; feed archived raw responses through
   the current parser/dispatcher and require byte-identical parsed actions.
2. **Backend replay:** rerun the same archived actions against the frozen local
   backend and require identical tool responses/hashes.
3. **Provider variance replay:** issue a new request only under a separately
   authorized audit, store it as a new sample, and never overwrite the
   original.

### 7.3 Drift and retirement

- Verify official model documentation, snapshot listing, pricing, endpoint,
  data controls, and account availability on every execution date.
- Require response `model` identity to equal `gpt-5.4-2026-03-05`.
- Any changed prompt, tool schema, SDK, API parameter, provider model, region,
  serializer, or backend creates a new run configuration and invalidates cache
  interchangeability.
- Never silently fall back from the snapshot to an alias, mini model, newer
  model, local model, or cached answer from a different configuration.
- If the snapshot is retired, keep archived results as a dated
  non-rerunnable API sensitivity, exclude it from any decisive claim that
  cannot be reproduced without it, and rely on offline/open rows for primary
  reproducibility as required by R12.

## 8. License, redistribution, and security

### Open-weight row

- Archive the exact model card, Apache-2.0 license, usage policy, repository
  metadata, selected file allowlist, expected sizes, and upstream identities
  before download.
- Stage into a restricted directory; hash every file; validate safetensors and
  the index; reject symlinks, pickle weights, executable code, and unexpected
  files; promote atomically.
- The plan does not grant redistribution rights. Public artifacts should
  contain acquisition instructions, revision and hashes, not model weights,
  unless a later release review explicitly approves redistribution.
- Archive required notices and attribution in the release bill of materials.

### API row

- Use a project-scoped key supplied at runtime through the approved secret
  mechanism; never write it to the repository, shell history, cache, or logs.
- Approve spend, organization/project, region, retention controls, and upload
  fields before the first request.
- Treat provider raw responses and family-bearing prompts as restricted data.
- A provider's general privacy statement does not supersede source rights,
  participant privacy, or AV-TRACE release decisions.

## 9. Stop rules

Stop the affected row and do not substitute another model if any of the
following occurs:

1. exact snapshot/revision cannot be verified;
2. license, usage policy, rights, privacy, retention, or data residency is
   unresolved;
3. requested/returned model identity differs;
4. runtime or provider silently falls back or uses an undeclared tool;
5. strict native tool calls cannot map losslessly to the canonical action
   schema;
6. evaluator-private data, hidden state role, SESs, necessity groups, answer
   keys, or route certificates reach the model;
7. raw media would need to leave the local environment;
8. any competence floor fails;
9. unsupported required claims are nonzero;
10. open-row p95 synthetic episode time exceeds 60 minutes or resources exceed
    the approved allocation;
11. API p95 cost exceeds $0.35/episode, cumulative spend reaches the hard cap,
    or repeated-run instability exceeds the frozen tolerance;
12. an after-freeze prompt/schema/runtime change would be needed;
13. the principal paper claim would depend on the API row alone.

Failure yields a reported `NO_GO` or omitted row, not prompt tuning on the
sealed set.

## 10. Alternatives and fallbacks

### Open-weight alternative

`Qwen/Qwen3-30B-A3B-Instruct-2507` at official revision
`13b91ea9539e6cc1c464d15a6e053e40f3ca1845` is the first alternative. Official
metadata checked on 2026-09-22 described an Apache-2.0, 30.5B-total/3.3B-active
MoE with tool-calling guidance and a roughly 61.2 GB repository snapshot. It
is not primary because its acquisition/storage and likely CPU working-set cost
are materially higher. It requires its own amended registry, acquisition
manifest, runtime preflight, and new sealed competence run.

The existing Qwen2.5-7B snapshot remains a historical/weak-controller
comparator, not the strong fallback, because it already failed v1-v3 competence
gates.

### API alternative

There is no automatic API fallback. If `gpt-5.4-2026-03-05` is unavailable,
the API row is `UNAVAILABLE_PINNED_SNAPSHOT`. A newer or different closed model
may be proposed only through a new dated official-document check, exact
snapshot pin, registry version, cost/privacy review, and fresh competence
preflight. Historical cache entries cannot be relabeled as another model.

### Resource/privacy fallback

- If local inference is slow but correct, reduce parallelism or run fewer
  systems; do not reduce the shared episode budget for only one row.
- If the API upload boundary is not approved, omit the API row. The open row
  and other pinned offline systems must carry all primary claims.
- If native tool calling is unreliable, the affected model fails. Do not
  convert free text into actions with a model-specific heuristic parser.

## 11. Exact future acquisition and integration tasks

These are task specifications, not authorization:

1. **Freeze baseline registry v1.0.** Hash this plan, registry, canonical tool
   and final-answer schemas, shared prompt templates, context policy, budgets,
   and competence thresholds.
2. **Open snapshot metadata preflight.** Re-query only official upstream
   metadata for exact revision `6cee...`, archive card/license/usage policy,
   enumerate the minimal MXFP4 allowlist and byte cap, and produce a
   no-download authorization decision.
3. **Open snapshot acquisition.** After approval, download only allowlisted
   files into restricted staging, record upstream identities and local
   SHA-256, validate safetensors/index/template, and atomically promote.
4. **Open runtime preflight.** In a network-denied process, test Harmony
   rendering, one strict tool call, one strict finalization, deterministic
   replay, peak RAM, latency, and runtime compatibility.
5. **Canonical native-tool adapter.** Implement provider-neutral tool
   definitions and a lossless mapper to `agent_action_schema.json`; prohibit
   semantic filling and answer substitution.
6. **Shared observation/finalizer adapter.** Freeze the public state serializer,
   32,768-token compaction rule, citation allowlist, and exact
   `final_answer_schema.json` validator.
7. **API governance preflight.** Obtain explicit approval for provider,
   project, spend cap, region, uploaded fields, retention/data controls, raw
   response storage, and secret handling.
8. **API snapshot preflight.** Using a synthetic non-family request only,
   verify account availability of `gpt-5.4-2026-03-05`, returned model
   identity, endpoint parameters, strict function calling, `store=false`,
   usage accounting, and injected-failure behavior.
9. **API cache/replay implementation.** Add canonical hashing, immutable
   restricted cache, offline exact replay, backend replay, variance samples,
   and mismatch rejection.
10. **New fictional competence suite.** Author and seal at least 48 cases
    without using existing scientific families, r017, Task-111 as an unseen
    set, or any current evaluator key.
11. **Independent competence execution/audit.** Run each model under the same
    public packet and score only after outputs are sealed. Publish safe
    aggregates, structured failures, resources, latency, and cost.
12. **Scientific-run amendment.** Only after competence, construct validity,
    rights/privacy, split, and learned-agent gates pass, create a separate
    preregistered run manifest. Do not let this planning decision authorize a
    family run.

## 12. Interpretation in the paper

Allowed labels:

- “representative stronger open-weight controller sensitivity”;
- “pinned closed-API frontier-model sensitivity”;
- “capacity/provider sensitivity under the same AV-TRACE backend and budget.”

Forbidden interpretations:

- the selected model is part of the AV-TRACE method;
- AV-TRACE improves, trains, or contributes the foundation model;
- the API row is reproducible merely because requests were cached;
- a strong model's failure proves the benchmark is valid;
- a strong model's success disproves the need for the protocol;
- any primary conclusion that exists only for the API row;
- general frontier-model ranking or SOTA claims.

The scientifically relevant question is whether the matched intervention and
trace metrics reveal acquisition, grounding, diagnosis, recovery, or stopping
behavior that answer accuracy alone misses. The strong rows test whether that
finding survives increased controller capacity and a provider/runtime change.

## 13. Official online evidence used

Only current official primary pages were used for the new model selections:

- OpenAI-owned gpt-oss-20b model card:
  `https://huggingface.co/openai/gpt-oss-20b`
- Exact gpt-oss-20b revision tree:
  `https://huggingface.co/openai/gpt-oss-20b/tree/6cee5e81ee83917806bbde320786a8fb61efebee`
- OpenAI GPT-5.4 model documentation:
  `https://developers.openai.com/api/docs/models/gpt-5.4`
- OpenAI latest-model guidance:
  `https://developers.openai.com/api/docs/guides/latest-model`
- OpenAI API data/privacy guidance:
  `https://developers.openai.com/api/docs/guides/your-data`
- Official Qwen alternative model card:
  `https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507`

All availability, price, capability, license, and policy facts must be checked
again on the actual acquisition/execution date.

