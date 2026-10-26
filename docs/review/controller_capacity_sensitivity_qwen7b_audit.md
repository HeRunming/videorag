# Independent audit: Qwen2.5-7B controller capacity sensitivity

**Audit date:** 2026-09-21  
**Scope:** Task 114 frozen synthetic/development competence run  
**Audit constraint:** no model rerun and no implementation change

## Audit decision

```text
TASK114_AUDIT_PASS
QWEN7B_CONTROLLER_SYNTHETIC_COMPETENCE_NO_GO_VALID
R017_REOPEN_NOT_PERMITTED
```

The Task-114 artifacts support the reported `NO_GO`. Two preregistered gates
failed by large margins:

| Frozen gate | Recomputed result | Decision |
|---|---:|---|
| Valid structured outputs after at most one repair | 11/16 = 68.75% | **FAIL**; floor 90% |
| Supported-answer success on oracle-evidence cases | 1/4 = 25.00% | **FAIL**; floor 80% |
| Unsupported required claims | 0 | **PASS**; required 0 |

Because all three gates were required, the 7B synthetic competence decision
must remain:

```text
QWEN7B_CONTROLLER_SYNTHETIC_COMPETENCE_NO_GO
```

The excluded `r017` competence gate may **not** be reopened on the basis of
Task 114. Its permanent scientific exclusion is unaffected. A future run could
only use it again as the already-excluded development competence gate after a
new synthetic interface gate is preregistered and passed; it cannot become
scientifically eligible.

## Verification matrix

| Audit item | Result | Evidence and qualification |
|---|---|---|
| Exact model and revision | **PASS** | `Qwen/Qwen2.5-7B-Instruct`, revision `a09a35458c702b33eeacc393d103063234e8bc28`, snapshot `data/restricted/scale1b/models/Qwen--Qwen2.5-7B-Instruct--a09a35458c70`. All nine selected snapshot files were independently rehashed and matched the acquisition manifest, including all four safetensors shards. |
| Frozen Task-111 contract equality | **PASS** | Task-111 and Task-114 `suite_contract.json` files are byte-identical. Their file SHA-256 is `b4aa831e77e6b8f744387f5a02e1516082bf0b990c010dca2a7d8e83d33f3ef7`. The contract's canonical self-hash independently recomputes to `sha256:b0f280487b936d82e14b118c16eb07ab1f4e189a74efe1000177487221002091`. |
| Task-111 protected hashes unchanged | **PASS** | All six Task-114B frozen SHA-256 values still match: contract, results, summary, calls, review, and orchestration result. Exact values are listed below. |
| Prompt hashes | **PASS** | All four prompt-file hashes match the frozen contract. The aggregate prompt/config hash independently recomputes to `sha256:7bfb36b8ad01105ea83e14e82676e036a70f70e8da46901169b4c2e304c46252`. |
| Exact request hashes | **PASS** | All 22 request hashes were independently reconstructed from the frozen cases, current frozen prompts, schemas, initial raw outputs, and validation errors. All 22 matched. The 16 initial request hashes are exactly equal to their Task-111 counterparts. |
| No full prompt/payload persistence | **PASS** | Recursive inspection of all five Task-114 JSON/JSONL artifacts found no `system_prompt` or `request_payload` fields. Call records retain hashes and raw model output, as required. |
| Actual calls and repair maximum | **PASS** | 22 model calls are recorded: 16 initial calls and 6 repairs. No case has more than attempts `[0, 1]`; there are no substituted answers or process-error records. Embedded result calls exactly equal `calls.jsonl`. |
| Raw-call integrity | **PASS** | Every persisted `raw_sha256` matches its `raw_text`. Token counts, latency, validation status, and peak RSS are present for every Task-114 call. |
| Metric recomputation | **PASS** | Independent parsing, strict validation, semantic rescoring, aggregation, and gate evaluation reproduce the stored results exactly. |
| Oracle denominator | **PASS** | Exactly four frozen generator cases have `oracle_evidence=true`: `dev-finalize-visual`, `dev-finalize-speech`, `dev-finalize-two-claims`, and `dev-finalize-shared-observation`. Only `dev-finalize-visual` succeeds. |
| Unsupported required claims | **PASS** | Recomputed count is 0. This means no accepted structured result asserted a required claim with an empty or out-of-oracle citation set. It does **not** imply broad grounding competence: malformed outputs fail closed, missing required claims are separately scored, and two valid oracle outputs abstained instead of answering. |
| CPU/bfloat16/local-only | **PASS** | Runtime metadata records CPU and `torch.bfloat16`; model/tokenizer loading uses `local_files_only=True` and `trust_remote_code=False`; offline environment variables are set. |
| Network denied | **PASS WITH EVIDENCE LIMIT** | The recorded Task-114 process configuration enables `unshare -n`; current source and its timestamp-matched bytecode construct that command, and the model process successfully started. Proxy/token variables are removed. Task 114 did not persist an independent socket-attempt counter or command stderr log, so the audit supports namespace denial but does not independently claim “zero attempted connections.” |
| No evaluation-family content | **PASS** | The frozen suite and Task-114 calls/results contain fictional `dev-*` cases only. Searches for NOAA/family IDs and evaluator-style identifiers found none. The sole `evaluation_family` occurrence is the contract's negative scope flag. No evaluation-family run was performed by Task 114. |
| Paired case/capability comparison | **PASS** | Every per-case semantic flag/error list/delta and every capability count/rate/delta independently recomputes from the unchanged Task-111 results and Task-114 results. |
| Focused validation | **PASS** | Audit-time non-model checks completed: `24 passed, 1 skipped`; Ruff passed on the Task-114 implementation/test paths. |

## Frozen Task-111 hash recheck

| Protected artifact | Required and observed SHA-256 |
|---|---|
| `data/restricted/scale1b/controller_dev/suite_contract.json` | `b4aa831e77e6b8f744387f5a02e1516082bf0b990c010dca2a7d8e83d33f3ef7` |
| `data/restricted/scale1b/controller_dev/results.json` | `02f10aa9c781f132e81679d221b696453cbf1d04d146f37eb730f44a6aab1c1d` |
| `data/restricted/scale1b/controller_dev/summary.json` | `131643b79fc4addb866c1f07e79f503f00f9e659e3f5618f196f61fc6775af96` |
| `data/restricted/scale1b/controller_dev/calls.jsonl` | `1c8e433668d10c242179b7393f67791d0a3127af13210bd4010580d668353654` |
| `docs/review/controller_synthetic_competence.md` | `4663c65a633a1fcd0df3c3e6434d3c926e4541c3d9f0335b5db266f24d0fb769` |
| `orchestration/results/111_controller_synthetic_competence.txt` | `fa641ddbfd31ed19b315f8c88e73c394e8ebebd3c7452ab52465554779b40698` |

## Calls, repairs, and failure decomposition

- Calls: **22**
- Initial calls: **16**
- Repair calls: **6**
- Cases repaired: **6**
- Repairs that recovered strict validity: **1** (`dev-finalize-visual`)
- Terminal malformed-after-repair cases: **5**
- Maximum repairs for any output: **1**
- Call statuses: **11 valid, 11 invalid**
- Peak RSS: **16,403,644,416 bytes**

The five terminal structured failures are:

1. `dev-route-vision`
2. `dev-inspect-visual-pointer`
3. `dev-no-progress-repeat-guard`
4. `dev-missing-hop-diagnosis`
5. `dev-finalize-speech`

Invalid-attempt validation errors comprise seven
`COVERED_CLAIMS_WITHOUT_OBSERVATIONS`, three `MALFORMED_MODEL_JSON`, and one
`ASSERTION_0_CITATION_MAP_MISMATCH`.

Seven additional cases produced valid schemas but failed semantic scoring:

- `dev-route-ambient`
- `dev-read-speech-pointer`
- `dev-claim-coverage-finalize`
- `dev-blocked-route-status`
- `dev-finalize-two-claims`
- `dev-finalize-shared-observation`
- `dev-abstain-missing-speech`

This is not a syntax-only failure. The raw controller outputs show a mixed
failure mode: for two malformed controller cases the emitted action index was
the expected action but the public state was invalid; for two others the
action index itself was wrong. Several fully valid outputs also selected the
wrong action or refused oracle-supported answers.

## Paired comparison audit

The stored paired comparison is accurate:

- Structured validity: **10/16 -> 11/16** (`+1`)
- Oracle supported-answer success: **1/4 -> 1/4** (`0`)
- Unsupported required claims: **0 -> 0**
- Total semantic successes across all 16 probes: **6 -> 4**

Capability deltas independently reproduce as:

| Capability | 1.5B | 7B | Delta |
|---|---:|---:|---:|
| claim-slot coverage | 0/3 | 0/3 | 0 |
| exact observation-ID citation copy | 1/3 | 1/3 | 0 |
| finalization | 1/4 | 1/4 | 0 |
| initial modality routing | 1/3 | 1/3 | 0 |
| inspect/read | 2/2 | 0/2 | -2 |
| justified abstention | 0/3 | 1/3 | +1 |
| missing-hop diagnosis | 0/4 | 1/4 | +1 |
| no-progress/repeated-action handling | 1/1 | 0/1 | -1 |
| recovery after route restoration | 1/2 | 1/2 | 0 |

These are descriptive low-N synthetic results. They do not establish that the
7B backbone is generally worse; they establish that this exact 7B snapshot and
frozen interface did not satisfy the preregistered competence contract.

## Prompt-hash clarification

The contract stores SHA-256 hashes of the prompt files including their final
newline. Runtime `system_prompt_sha256` values hash `prompt_text(...).strip()`,
so those values are intentionally different. They match the stripped runtime
texts for all calls. The stronger check is the request reconstruction: all 22
full request hashes match, including repairs.

The label “prompt/config hash” is accurate but broad: it binds prompt-file
hashes, generation limits, process timeouts, thread count, context limit,
offline/network settings, seed, and repair budget. It is not a prompt-only
hash.

## Implementation-confound assessment

At the benchmark-content and model-request level, the capacity comparison is
clean:

- contract and cases are byte-identical;
- prompts and schemas are frozen;
- all 16 initial request hashes equal Task 111;
- thresholds and scoring are unchanged;
- the repair budget remains one;
- no post-outcome tuning or deterministic substitution is present.

The Task-114-specific current source also contains model-selection/output
plumbing, process timeout/thread configuration, network-namespace isolation,
offline metadata, peak-RSS instrumentation, logging redaction, and paired
report generation. These are operational changes rather than benchmark
semantic changes. Completed calls were not affected by the larger timeouts;
RSS/logging/report code is observational; and network isolation narrows rather
than expands model access.

Two provenance qualifications remain:

1. the workspace has no usable Git metadata or immutable pre-Task-114 source
   snapshot, so a historical source diff cannot be independently reconstructed;
2. the frozen Task-111 summary did not record its process configuration, so
   exact equality of thread/timeout/network settings cannot be proven solely
   from the baseline artifact. Task 114 records eight CPU threads. Initial
   token counts and request hashes are identical, but thread scheduling can in
   principle affect bit-level CPU reproducibility.

Accordingly, the report statement that “only the backbone” changed is a
**qualified pass**: true for cases, prompts, schemas, requests, scoring, and
decision gates, but not literally true for process isolation/instrumentation
code. This qualification does not rescue either failed gate and does not make
the `NO_GO` invalid.

## Narrowest controller-interface v2 experiment

Use a **synthetic-only, preregistered two-head diagnostic on the same ten
controller cases**, with the exact 7B snapshot, inputs, action menus, greedy
decoding, and one-repair ceiling. Do not change the six generator cases,
benchmark thesis, semantic labels, or frozen Task-114 result.

### Head A: constrained action choice

Return only:

```json
{"action_index": 0}
```

Constrain `action_index` at decoding time to the integer enum present in that
case's action menu. Score it against the existing expected action. This removes
free-form JSON/state serialization as an explanation for action-choice
failure.

### Head B: constrained public state

In a separate diagnostic call, provide the selected action index and request
only the existing six-field `public_state`, under a JSON grammar enforcing
keys, types, and closed enums but not semantic correctness. Score the same
coverage, missing-modality, missing-hop, cause, and sufficiency semantics.

Interpretation is then unambiguous:

- Head A wrong: **semantic action-selection failure**.
- Head A correct, Head B syntactically invalid: **schema/interface failure**.
- Head A correct, Head B valid but wrongly covered/missing: **semantic state
  estimation failure**.
- Both correct while v1 failed: **monolithic-interface interference**.

This is the narrowest useful diagnostic because it changes only output
factorization and syntax enforcement. It must not introduce new cases, reveal
oracle evidence, alter the action menu, tune prompts after outputs, or replace
the original competence gate. Passing it alone would **not** reopen `r017`;
the project should first preregister how v2 maps back to the same end-to-end
controller semantics and require a full synthetic gate before any excluded
`r017` rerun.

## Final disposition

- Task-114 artifact integrity and reported arithmetic: **PASS**
- Frozen 7B competence gate: **FAIL**
- Reported 7B `NO_GO`: **VALID**
- Reopen excluded `r017` now: **NO**
- Scientific-evaluation eligibility of `r017`: **remains permanently false**

