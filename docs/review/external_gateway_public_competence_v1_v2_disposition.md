# External-gateway public competence v1/v2 disposition

**Date:** 2026-10-12  
**Decision token:** `EXTERNAL_GATEWAY_COMPETENCE_V1_V2_PERMANENT_NO_GO_V3_REQUIRED`

## Binding decision

The independent red-team findings are accepted as authoritative. External-
gateway competence suites v1 and v2 are permanent **NO-GO** for execution.
Neither version, nor any result derived from either version, may be used for a
competence, Gate-C, H2, scientific, benchmark, or model-capability claim.
Their files remain historical evidence only; repository presence is not
authorization. V1/v2 may not be patched, re-armed, privately executed, or
grandfathered into eligibility. Any future attempt must be a separately
constructed v3 satisfying every requirement below.

V1 exposed evaluator material and target-signaling structure and admitted
public-only recovery, substring/contradiction, overinclusive-diagnosis,
forged-declaration, replay, leakage, schema-mismatch, and missing-claim
attacks. V2 improved local separation and scoring, but its deterministic
public construction, publicly reproducible labels/canary, self-produced
manifests, locally trusted runner path, incomplete retry-specific prompt
binding, repository-local comparator scope, and locally armable one-shot
state do not create an independently sealed competence evaluation. These are
freeze-boundary defects, not operational exceptions.

## Prospective v3 minimum requirements

V3 is a new design, not a repair authorization. Before any suite execution:

1. **Independent construction and entropy.** An evaluator independent of the
   model, runner, suite authors, and public repository must construct the
   suite using independently held, nonpublic entropy. Labels, target mappings,
   and the private canary must not be derivable or reproducible from public
   code, seeds, artifacts, commit history, or deterministic regeneration.
2. **Authenticated private manifest.** The evaluator must authenticate a
   private manifest binding the exact public packets, private labels/canary,
   case inventory, scoring policy, comparator inventory, runner trust anchor,
   ledger namespace, and all hashes. Authentication keys and verification
   authority must be outside the runner/repository trust domain.
3. **Independent runner trust anchor.** An independently built or attested
   runner artifact must be hash-pinned by the private manifest. The runner,
   prompt renderer, evaluator, and result verifier must fail closed on any
   identity, code, dependency, configuration, provider, model, or runtime
   drift.
4. **Fixed runner and prompt provenance.** Freeze at least 48 substantive
   cases and their complete factor order. Bind every initial attempt and every
   permitted schema-only retry to its own precommitted rendered-prompt hash
   and byte count; retry hashes must be distinct and retry-index-specific.
   No semantic retry, repair, substitution, fallback, voting, or best-of-N is
   allowed.
5. **Strict semantics.** Unsupported or missing required claims, wrong
   citations (including observed-but-wrong citations), unobserved citations,
   contradictory answers, extra claims, malformed projections, nonempty
   abstention answers, and incoherent/overinclusive diagnoses must be
   separately counted and must fail the run. Substring inclusion is never
   sufficient for correctness.
6. **Pinned comparator inventory.** The authenticated manifest must pin a
   complete comparator inventory and its hashes before execution, including
   public suites, development packets, rendered prompts, fixtures, examples,
   tests, reports, commit history, and known prior outputs. Exact, canonical,
   rendered-prompt, and near-overlap audits are mandatory. Supplemental
   independent leakage/memorization audits are required and may invalidate
   the run; they may not relax the pinned audit.
7. **Authenticated one-shot ledger.** Use a fixed, authenticated ledger
   namespace chosen before execution, with evaluator-controlled ownership and
   least-privilege permissions. Creation, arming, run start, retry use,
   submission, evaluation, consumption, and receipts must be atomic,
   append-only/tamper-evident, namespace-bound, and unavailable to suite
   authors, the model, gateway, and runner for reset or replay.
8. **Transport gate first.** A separate external-gateway transport smoke for
   the exact pinned model/provider/runtime route must be completed and
   independently adjudicated `READY` before the competence ledger is armed or
   any suite packet is rendered or submitted. `REPAIR`, timeout, empty output,
   partial provenance, or model substitution blocks execution.
9. **Claim boundary.** V3 remains a public-fictional technical competence
   evaluation only. Even a valid v3 pass makes no scientific, audiovisual,
   H2, or standalone Gate-C claim and cannot authorize scientific execution.

The machine-readable requirements are frozen in
`data/rehearsal_plan/external_gateway_competence_v3_requirements.json`.

## Observed transport facts; no competence evidence

No gateway or model call was made for this disposition.

- **GPT-6-Astra:** the completed public-development smoke report at
  `data/rehearsal_plan/external_gateway_strong_agent_smoke_run_v1/task202-gpt6-astra-final/task201-20261012T025000Z/run_report.json`
  has SHA-256
  `d304ef9a746be0f948dd519a048f3a52b7364de786dad18323584de12229fafd`
  and decision `EXTERNAL_GATEWAY_STRONG_AGENT_SMOKE_REPAIR`. Seven factor
  attempts produced zero valid factors, zero canonical outputs, and no raw
  model output.
- **DeepSeek V4 Pro (`deepseek-v4-pro-ioa`):** the independent
  public-development smoke report at
  `data/rehearsal_plan/external_gateway_strong_agent_smoke_run_v1/task205-deepseek-v4-pro-independent/task201-20261012T071411Z/run_report.json`
  has SHA-256
  `1bf001112bed2c37a801d9c68c332043b97aec48e0299d314f5c7f19ee199b2a`
  and decision `EXTERNAL_GATEWAY_STRONG_AGENT_SMOKE_REPAIR`. The first factor
  timed out, the remaining factors were not invoked, and there were zero
  valid factors, zero canonical outputs, and no raw model output.

Both reports are transport/process evidence only. They contain no model
outputs, no computed competence metric, and no competence evidence for or
against either model. Neither smoke is `READY`; therefore v3 suite execution
is presently blocked independently of the permanent v1/v2 prohibition.

