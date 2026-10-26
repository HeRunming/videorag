# Qwen2.5-Omni-7B fictional native direct-A/V competence

**Task:** 198  
**Date:** 2026-10-10 (Asia/Shanghai)  
**Decision:** `QWEN25_OMNI_DIRECT_COMPETENCE_NO_GO`  
**Frozen evaluator result:** `STRONG_BASELINE_COMPETENCE_REPAIR`  
**Scientific evaluation:** not authorized and not performed

## Executive decision

The exact local Qwen2.5-Omni-7B thinker snapshot completed the full Task-158
direct-A/V competence group once:

- 24 substantive direct-A/V cases;
- 6 processor/identity/provider runtime fixtures; and
- 30/30 recorded result rows.

The run does **not** pass the frozen direct competence thresholds. The
controlling Task-198 disposition is therefore
`QWEN25_OMNI_DIRECT_COMPETENCE_NO_GO`.

This is a decision for the exact frozen model, prompt, media, schema, runtime,
and suite configuration. The consumed suite may not be tuned and rerun. Any
future attempt requires a prospective versioned adapter/prompt/media policy,
a newly generated fictional suite, a new pre-execution seal, and separate
authorization.

## Eligibility and reuse decision

Task 198 reused the original Task-158 direct-A/V group rather than generating
a new suite because its separate eligibility audit established all of the
following before inference:

1. The public Task-158 suite file and semantic hash were unchanged:
   - file SHA-256:
     `1e3bec6e30e63f705cc2d49b010fdf6479b61f9b66aa7a1ca17f90a3b453afb4`;
   - semantic hash:
     `sha256:7b8f8d021b24cb244f0df0f6b02b3da91120df3817a5366350895eb24f4646dc`.
2. The direct group is explicitly bound to
   `Qwen/Qwen2.5-Omni-7B` in the `DIRECT_AV_MODEL` role, not to Granite.
3. Granite's sealed Task-172 `direct_av_eligibility.json` was authenticated
   against its run seal and records:
   - `model_calls_executed: 0`;
   - `score_rows_created: 0`;
   - `scored_as_zero: false`; and
   - `STRUCTURALLY_INELIGIBLE`.
4. No Task-158 direct case identifier occurred in searched prior
   strong-baseline output/review/result/tool artifacts outside frozen suite
   definitions.
5. The Task-197 acquisition canary did not contain any Task-158 direct case
   identifier.

The eligibility record is:

`data/restricted/strong_baselines/qwen25_omni_direct_competence_v1/eligibility_audit.json`

It records `ELIGIBLE_UNSEEN_FOR_QWEN_OMNI` and
`prospective_new_suite_required: false`.

## Prospective freeze before inference

Even though the public Task-158 direct group was eligible, Task 198 sealed the
complete execution configuration before model inference:

- exact 24+6 public direct projection;
- exact Task-158 thresholds;
- exact local Qwen model/processor/tokenizer binding;
- prompt policy and strict final schema;
- question-independent chronological packing policy;
- eight local synthetic media files;
- runner and frozen evaluator identities; and
- one-run authorization.

Freeze time:

`2026-10-10T07:36:06Z`

Freeze seal SHA-256:

`3b77a3f055f8208a40c1a4106232cd39c63582b5d4248d5562bf6efb22bb521b`

The eight generated asset locators contain four byte-distinct source-free
media patterns reused for the frozen replay pairs:

- vision: emerald geometric card plus silence;
- speech: blank video plus a deterministic locally synthesized,
  speech-like utterance;
- ambient: blank video plus three deterministic wooden-knock-like impacts;
- joint A/V: animated blue flare plus paired synthetic alert tones.

No recorded person, scientific source, external TTS/API, benchmark media, or
scientific family was used.

## Exact model and runtime

- Repository: `Qwen/Qwen2.5-Omni-7B`
- Revision: `ae9e1690543ffd5c0221dc27f79834d0294cba00`
- Processor revision: same exact revision
- Tokenizer revision: same exact revision
- Snapshot:
  `data/restricted/strong_baselines/models/Qwen--Qwen2.5-Omni-7B--ae9e1690543f`
- Model class: `Qwen2_5OmniThinkerForConditionalGeneration`
- Processor class: `Qwen2_5OmniProcessor`
- Device/dtype: CPU / `torch.bfloat16`
- Threads: 8 intra-op, 1 inter-op
- `local_files_only=true`
- `trust_remote_code=false`
- Greedy single output
- Maximum new tokens: 512
- Processor context cap: 32,768
- `use_audio_in_video=true`
- Talker/token-to-wave execution: none
- GPU/API use: none
- Scientific media/source access: none

The processor instantiated one socket object inside the deny-network guard,
matching the Task-197 behavior. The guard blocked it; no connection or bytes
were sent. Model loading and every recorded generation report zero network
attempts.

Runtime:

- child elapsed: 6,127.53 seconds;
- parent wall time: 6,184.51 seconds;
- peak child RSS: 18,001,260 KiB;
- model load: 1.47 seconds;
- substantive model generation attempts: 32;
- schema-only retries: 8;
- semantic repairs: 0.

## Governed output handling

Every raw model-authored attempt is retained byte-for-byte in
`raw_attempts.jsonl`. The adapter allowed at most one retry and only for
schema-repairable failures. It performed no:

- semantic retry or prompt tuning;
- JSON extraction/completion;
- field filling;
- citation, interval, modality, diagnosis, or answer correction;
- deterministic answer substitution;
- voting or best-of-N; or
- outcome-conditioned rerun.

The run submission and raw attempts were sealed at
`2026-10-10T09:19:22Z`, before evaluation.

Run ID:

`task198-2026-10-10T07:37:12Z-9a1fbcff2c1b`

Run seal SHA-256:

`fafc568e4e72ad62f6aed5d12b6899b7e880306775c03c9447682dfe72ff2320`

## Frozen evaluator result

| Gate | Threshold | Result | Pass |
|---|---:|---:|:---:|
| Substantive cases | >=24 | 24 | yes |
| Runtime/manifest fixtures | 100% | 6/6 = 100% | yes |
| Valid strict final outputs | >=90% | 0/24 = 0% | **no** |
| Complete-evidence supported answers | >=80% | 0/16 = 0% | **no** |
| Vision stratum | >=75% | 0/4 = 0% | **no** |
| Speech stratum | >=75% | 0/4 = 0% | **no** |
| Ambient stratum | >=75% | 0/4 = 0% | **no** |
| Joint-A/V stratum | >=75% | 0/4 = 0% | **no** |
| Partial/masked correct abstention | >=80% | 0/8 = 0% | **no** |
| Unsupported required claims | 0 | 0 | yes |
| Out-of-exposure citations | 0 | 12 | **no** |
| Observed-evidence lock | 100% | 0/24 = 0% | **no** |
| Required-modality-drop behavior | 100% | 0/8 = 0% | **no** |
| Deterministic replay parsed output | 100% | 0/8 pairs | **no** |
| Deterministic answer substitutions | 0 | 0 | yes |
| Private-field exposures | 0 | 0 | yes |

Frozen evaluator decision:

`STRONG_BASELINE_COMPETENCE_REPAIR`

Structural invalid-output counts:

- `CLAIM_TO_CITATIONS_MISMATCH`: 4;
- `CITATION_INTERVAL_MISMATCH`: 8;
- `CITATION_MODALITY_MISMATCH`: 4; and
- `FINAL_ANSWER_SCHEMA_INVALID`: 8.

The model produced no evaluator-valid substantive envelope. For complete
cases, common failures included using full citation objects instead of
observation-ID strings in the redundant citation map, copying media-local
zero-based intervals instead of the frozen manifest intervals, and changing
the frozen modality set. For masked cases, all eight outputs remained schema
invalid after the permitted schema-only retry.

An additional raw-text diagnostic is not used for score but confirms that the
failure is not merely the redundant citation map:

- neither vision output pair used the required word `emerald`;
- neither speech output pair used `solstice`;
- neither ambient output pair used both `wooden` and `knock`;
- joint-A/V outputs used `blue` but not `flare`; and
- no masked output produced a valid abstention envelope.

## Independent audit

The independent audit:

- reverified the pre-execution freeze;
- reverified the run seal;
- replayed the frozen evaluator byte-identically;
- reproduced every metric and gate decision;
- checked all 6 runtime fixtures;
- recomputed per-stratum and replay-pair components; and
- confirmed zero semantic-content-change acceptance, private exposure, or
  deterministic substitution.

Evaluation seal SHA-256:

`e48b280a30755d8bb4ee532bc626ffacc382efa310850becace6c678d5a6e8e0`

## Boundary and disposition

- Fictional direct competence established: **no**
- Direct suite consumed by this run: **yes**
- Rerun of this exact suite/configuration allowed: **no**
- Scientific evaluation authorized: **no**
- No scientific media, GPU, or API used: **confirmed**

The correct final token is:

`QWEN25_OMNI_DIRECT_COMPETENCE_NO_GO`

