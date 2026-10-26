# P23_102 R23-B v5 fail-closed global distinctiveness

**Decision token:** `R23_B_V5_DESIGN_READY`  
**Date:** 2026-10-23  
**Status:** model-free implementation, red-team regressions, plan, and external commitment request ready  
**Scientific status:** not execution, not authorization, not externally attested, and not scientific GO

## Isolation and trust boundary

R23-B v5 is a new isolated surface. It does not modify historical P23_102
authoring, Canary, marker, authorization, or capsule artifacts. It reads no
private selection and performs zero model, ASR, embedding, retrieval, media
decode, or authorization calls.

`verify_bundle`, `verify_plan`, review receipt verification, and commitment
verification provide only
`CURRENT_IMPLEMENTATION_RECOMPUTED_INTEGRITY_NOT_EXTERNAL_AUTHORIZATION`.
Independent authorization of the exact v5 commitment request remains required.

## Closure 1: complete review-packet commitment

Every selected review packet has a fixed `packet_payload` containing every
review-visible or review-binding field other than `review_packet_key`:

- sample key, sample identity, exact input hash;
- component key, component identity, and ordinal;
- role class and exact review stratum;
- blinded action/object atoms and exact questions;
- content hash, complete media binding plus hash, and evidence binding hash.

The tool first computes `packet_payload_sha256`, then derives
`review_packet_key` from the review-packet schema/version and that payload hash.
Reviewer and adjudication submissions bind all of:

- `review_packet_key`;
- `packet_payload_sha256`;
- `content_sha256`;
- `media_binding_sha256`; and
- `evidence_binding_sha256`.

Receipt verification recomputes the packet payload hash and packet key before
review decisions. Changing blinded atoms, questions, sample/component identity,
stratum, media, content, or evidence is rejected even if an attacker recomputes
the outer receipt hash. Packet-only tamper regressions cover the same fields.

## Closure 2: unconditional global public/immutable identity rejection

The global identity gate records complete locations for duplicate:

- `sample_key`;
- `component_key`;
- `query_key`;
- `sample_identity_sha256`; and
- `component_identity_sha256`.

Any such duplicate is copied into `hard_global_identity_failures` and yields
`REJECT_SAMPLE_SET` unconditionally. This precedence is below only a contract
error and above all per-sample `ABSTAIN`, malformed-input, cardinality, and
other global-gate outcomes. Therefore an all-malformed/all-ABSTAIN set with
duplicate public IDs is still rejected. `verify_bundle` reconstructs the bundle
and decision, so a resealed precedence downgrade is rejected.

## Closure 3: closed typed-audit fallback

Canonical JSON remains exact canonical UTF-8. When canonical JSON fails, v5
emits `av-trace.p23-102-r23b-canonical-typed-raw-audit/2.0` and marks the sample
`CANONICALIZATION_FAILED` / `ABSTAIN` unless the hard global identity rule
requires whole-set rejection.

Unknown objects are never represented by module-qualified type alone. They use
an explicit `UNSUPPORTED_TYPE` envelope with type/module/qualname and:

- safely typed canonical `__dict__` state plus `state_sha256`, when available;
- or an explicit `state_status` showing that content distinction is unavailable.

Thus same-type objects with different safely encodable state have different
audit hashes. Stateless/uninspectable unsupported objects make no content-
distinction claim; their sample/component audit identity is bound to the raw
position and the failure envelope, while the disposition remains fail-closed.
No process-dependent nonce or object address is used.

For `CANONICALIZATION_FAILED`, verification validates the sealed typed tree and
its exact fallback bytes/hashes but never attempts to recover the original
unknown object. Mapping audit encoding is a canonical sorted key/value pair
list. Unhashable list/dict keys are never rebuilt as a Python `dict`; fresh-
process verification compares the sealed pair-list envelope. Hostile Mapping
exceptions are converted to the explicit unsupported envelope or a contract-
level rejection; native exceptions do not escape.

## Mechanical contract retained

The v4/v3 protections remain active: closed family roles; ordered far-role
composition; visual kind in atoms/signatures/text; exact query regeneration and
query-to-atoms checks; non-vacuous cardinality; exact, near, content, ambient,
and family collision gates; atom specificity; no adaptive rewrite; complete
per-slot/per-sample accounting; content-identity review deduplication; two
independent reviewers; and an independent conflict adjudicator.

The synthetic preflight remains fixed at 3 samples, 6 components, and 15
primary queries. All commands report zero model and authorization calls.

## Artifacts

- Tool: `tools/p23_102_global_distinctiveness_v5.py`
- Tests: `tooling/tests/test_p23_102_global_distinctiveness_v5.py`
- Design: `docs/design/p23_102_global_distinctiveness_v5.md`
- Plan: `data/rehearsal_plan/p23_102_global_distinctiveness_v5_plan.json`
- Commitment request: `data/rehearsal_plan/p23_102_global_distinctiveness_v5_external_commitment_request.json`

## Verification commands

```bash
pytest -q tooling/tests/test_p23_102_global_distinctiveness_v5.py
ruff check tools/p23_102_global_distinctiveness_v5.py \
  tooling/tests/test_p23_102_global_distinctiveness_v5.py
python -m py_compile tools/p23_102_global_distinctiveness_v5.py \
  tooling/tests/test_p23_102_global_distinctiveness_v5.py
python tools/p23_102_global_distinctiveness_v5.py self-test
python tools/p23_102_global_distinctiveness_v5.py plan
python tools/p23_102_global_distinctiveness_v5.py commitment-request
python tools/p23_102_global_distinctiveness_v5.py preflight
```

`preflight` is the requested preflight0-equivalent synthetic, zero-model path.
It does not consume authorization or execute a real R23-B run.

## Remaining prerequisites

Before any real R23-B execution, governance must still provide:

1. independent authorization binding the exact v5 commitment-request hashes;
2. a sealed, authorized, nonempty real input set and expected query count;
3. preregistered replacement order, pointer, and exhaustion state;
4. pinned structured-call model/runtime assets;
5. real-media calibration and operating thresholds;
6. two independent reviewers and an independent conflict adjudicator;
7. verified sealed review receipts for all required packets;
8. a sealed real-output audit passing all fixed gates; and
9. a separate scientific GO decision.
