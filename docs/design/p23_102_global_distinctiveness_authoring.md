# P23_102 R23-B v3 fail-closed global distinctiveness

**Decision token:** `R23_B_V3_DESIGN_READY`  
**Date:** 2026-10-23  
**Status:** model-free tool, regressions, review-packet interface, exact current-implementation plan, and external commitment request ready  
**Scientific status:** not execution, not externally attested, not a real-run authorization, and not scientific GO

## Scope and trust boundary

R23-B v3 is an isolated prospective contract. It does not modify the older
authoring, Canary, marker, authorization, or capsule code and does not read
private family selection. Its commands perform zero model, ASR, embedding,
retrieval, media-decode, or authorization calls.

`verify_bundle` and `verify_plan` provide only:

`CURRENT_IMPLEMENTATION_RECOMPUTED_INTEGRITY_NOT_EXTERNAL_AUTHORIZATION`

They recompute an artifact against the currently loaded implementation and its
current constants. They cannot prevent a coordinated tool edit followed by
newly generated plan/bundle hashes. Consequently every public verifier result
sets `execution=false` and `external_attested=false`. No self-produced hash is
described as a cryptographic trust root or independent authorization.

The estimand remains query identifiability before learned retrieval. A
collision or insufficient anchor is an authoring failure, not retrieval-model
evidence.

## External commitment request

The additional artifact
`data/rehearsal_plan/p23_102_global_distinctiveness_external_commitment_request.json`
uses the fixed schema
`av-trace.p23-102-r23b-external-commitment-request/1.0`. It requests a future
independent authorization binding and includes:

- current tool source hash;
- exact plan payload hash and expected canonical plan-file hash;
- gate-manifest hash;
- complete schema-manifest hash and commitment-request-schema hash;
- exact runtime constants plus their hash; and
- inherited parent ambient-tool source hash.

The request is not itself authorization or attestation. A future independent
party must bind and sign/record those values outside this implementation.

## Complete pre-validation audit chain

Every position receives an immutable slot envelope before structured
validation. Canonical inputs retain canonical raw bytes and SHA-256. Inputs
that cannot be canonicalized, including non-finite floats, retain a safe typed
audit encoding, safe representation/type digest, raw audit bytes/hash, and the
reason `CANONICALIZATION_FAILED`; bundle construction does not throw.

Non-hashable or malformed atom values are caught as per-sample validation
failures rather than escaping bundle construction. The bundle retains:

- every raw slot envelope and audit input;
- sample/component identity records where available;
- every per-sample disposition, failure stage, reasons, and query keys;
- successful rows even when another sample abstains;
- global-gate, cardinality, budget, review, and replacement state; and
- an explicit decision derivation from sample results, recomputed global
  gates, and cardinality checks.

There is no adaptive rewrite or output-conditioned retry. `ABSTAIN` and
`REJECT_SAMPLE_SET` require future preregistered replacement governance.

## Closed semantic and identity contracts

`family_role` is a closed enum. Far roles require at least two ordered
components and a registered ordered relation. Every component requires exact
media/evidence hashes, a positive interval, an ambient event plus acoustic
property, and at least two independent discriminative visual dimensions.

Visual `kind` is authoritative content. `kind:event` versus `kind:state` is
present in visual and family content atoms, content signatures, and mechanical
query/description text. Therefore changing only kind changes the observable
query and signature. `query_to_content_atoms` accepts only the exact mechanical
query projection and exact atom list.

`sample_key` is globally unique. `component_key` is globally unique across all
samples. `query_key` is mechanically derived from immutable sample/component
identities, component ordinal, and query kind, then exactly revalidated.
Duplicate supplied IDs and duplicate derived query keys fail closed while the
complete slot and per-sample audit chain remains present.

## Non-vacuous cardinality

A real or preflight bundle requires at least one input sample, at least one
visible component, and at least one expected primary query. Empty input yields
an audited `ABSTAIN`, failed nonempty-query/global analysis, and failed
cardinality report; it cannot pass vacuously.

The synthetic preflight is explicitly fixed at 3 samples, 6 components, and
15 expected primary queries.

## Mechanical rows and global gates

Descriptions and queries are regenerated from structured inputs. Fixed gates
cover:

1. nonempty primary-query set;
2. row integrity, query-key derivation, exact regeneration, and query-to-atoms;
3. global sample/component/query-key uniqueness;
4. normalized exact query uniqueness;
5. pairwise token-set Jaccard strictly below `0.92`;
6. ordered content-atom signature uniqueness;
7. global exact ambient-tuple uniqueness;
8. family-query pair near-collision rejection; and
9. authoritative atom specificity plus phrase-blacklist defense.

The global decision is not trusted from serialized input; it is derived and
then reproduced by current-implementation bundle verification.

## Human-review packet interface

No human result is filled in this task. Candidate selection uses immutable
content identity plus exact media/evidence binding, never renameable IDs.

- count: `ceil(0.2 * N)`;
- every selected component is removed from every later selection pool;
- when review count is at least the number of available family-role strata,
  every available role stratum is covered;
- no component can be selected twice;
- packet content is blinded action/object claims plus exact evidence binding;
- two distinct reviewer identities are mandatory;
- reviewer conflict requires adjudication;
- the adjudicator identity must differ from both reviewer identities;
- missing/non-independent required identities fail closed; and
- failed review rejects the sample with no text editing.

## Artifacts and model-free commands

- Tool: `tools/p23_102_global_distinctiveness_authoring.py`
- Tests: `tooling/tests/test_p23_102_global_distinctiveness_authoring.py`
- Plan: `data/rehearsal_plan/p23_102_global_distinctiveness_authoring_plan.json`
- External commitment request: `data/rehearsal_plan/p23_102_global_distinctiveness_external_commitment_request.json`

```bash
pytest -q tooling/tests/test_p23_102_global_distinctiveness_authoring.py
ruff check tools/p23_102_global_distinctiveness_authoring.py \
  tooling/tests/test_p23_102_global_distinctiveness_authoring.py
python -m py_compile tools/p23_102_global_distinctiveness_authoring.py \
  tooling/tests/test_p23_102_global_distinctiveness_authoring.py
python tools/p23_102_global_distinctiveness_authoring.py self-test
python tools/p23_102_global_distinctiveness_authoring.py plan
python tools/p23_102_global_distinctiveness_authoring.py commitment-request
python tools/p23_102_global_distinctiveness_authoring.py preflight
```

## Remaining prerequisites

Before any real R23-B execution, a separate governance action must provide:

1. independent external authorization binding the exact commitment-request
   tool/plan/gate/schema/runtime hashes;
2. a sealed authorized exact nonempty real input set and expected query count;
3. preregistered sampling, replacement order, pointer, and exhaustion state;
4. pinned structured-call model/runtime assets;
5. real-media calibration establishing thresholds and operating behavior;
6. two independent human reviewers plus an independent adjudicator;
7. completed review results validated by this interface;
8. a sealed real-output audit passing all fixed gates; and
9. a separate scientific GO decision.
