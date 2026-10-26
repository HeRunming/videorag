# P23_102 R23-B v4 fail-closed global distinctiveness

**Decision token:** `R23_B_V4_DESIGN_READY`  
**Date:** 2026-10-23  
**Status:** model-free implementation, regressions, plan, and external commitment request ready  
**Scientific status:** not execution, not authorization, not externally attested, and not scientific GO

## Isolation and trust boundary

R23-B v4 is implemented as a new surface. It does not modify the historical
P23_102 authoring, Canary, marker, authorization, or capsule files. It reads no
private selection and performs zero model, ASR, embedding, retrieval, media
 decode, or authorization calls.

`verify_bundle` and `verify_plan` provide only
`CURRENT_IMPLEMENTATION_RECOMPUTED_INTEGRITY_NOT_EXTERNAL_AUTHORIZATION`.
Independent authorization of the exact commitment request remains mandatory.

## Red-team closure 1: stable raw audit encoding

Canonical JSON inputs retain their exact canonical JSON bytes. If canonical
JSON fails, `_capture_raw_bytes` uses
`av-trace.p23-102-r23b-canonical-typed-raw-audit/1.0`; it never uses `repr`.
The fallback is a recursively typed tree with:

- mapping entries sorted by canonical encoded key (and value as a deterministic tie-break);
- ordered list and tuple items;
- sorted set/frozenset items;
- explicit `NaN`, `+Infinity`, and `-Infinity` float tags;
- finite floats represented by exact hexadecimal strings;
- bytes represented as base64;
- integers represented as decimal strings; and
- unknown objects represented only by module-qualified type and a stable,
  irreversible domain-separated digest. Object addresses and representations
  are excluded.

Each envelope binds encoding schema, version, payload hash, raw bytes, raw
bytes hash, raw type, and audit tree. JSON persistence and fresh-process reload
must recapture exactly. Noncanonical input remains audited `ABSTAIN`.

## Red-team closure 2: immutable identity uniqueness and review deduplication

The global identity gate checks and reports complete locations for duplicate:

- `sample_key`;
- `component_key`;
- `query_key`;
- `sample_identity_sha256`; and
- `component_identity_sha256`.

Any duplicate immutable identity in the input set is a scientific input-set
failure and therefore globally yields `REJECT_SAMPLE_SET`; review deduplication
is not a substitute for this gate.

Every human-review candidate pool and final selection is deduplicated by
`component_identity_sha256`. The review count is computed from the unique
component-identity population, so identical component content appearing under
different samples can consume at most one review slot.

## Red-team closure 3: review packet binding and receipt sealing

Every reviewer submission and adjudication record must include and exactly
match the selected packet's:

- `review_packet_key`;
- `content_sha256`;
- `media_binding_sha256`; and
- `evidence_binding_sha256`.

Both reviewer submissions and any adjudication must bind the same packet.
Cross-packet replay fails closed. Reviewer identities must differ; a conflict
adjudicator must differ from both reviewers.

`build_review_receipt` seals the exact review packet, both submissions,
optional adjudication, derived decision, schema version, and
`receipt_payload_sha256`. `verify_review_receipt` recomputes the hash and
 decision; packet/submission/decision tampering fails.

## Mechanical global contract

The retained v3 protections remain active: closed family roles; ordered
multi-component far roles; visual kind in atoms/signatures/text; exact query
regeneration and query-to-atoms; non-vacuous cardinality; exact, near, content,
ambient, and family collision gates; atom specificity; no adaptive rewrite;
and complete per-slot/per-sample audit accounting.

The synthetic preflight remains fixed at 3 samples, 6 components, and 15
primary queries. All commands report zero model and authorization calls.

## New artifacts

- Tool: `tools/p23_102_global_distinctiveness_v4.py`
- Tests: `tooling/tests/test_p23_102_global_distinctiveness_v4.py`
- Design: `docs/design/p23_102_global_distinctiveness_v4.md`
- Plan: `data/rehearsal_plan/p23_102_global_distinctiveness_v4_plan.json`
- Commitment request: `data/rehearsal_plan/p23_102_global_distinctiveness_v4_external_commitment_request.json`

## Verification commands

```bash
pytest -q tooling/tests/test_p23_102_global_distinctiveness_v4.py
ruff check tools/p23_102_global_distinctiveness_v4.py \
  tooling/tests/test_p23_102_global_distinctiveness_v4.py
python -m py_compile tools/p23_102_global_distinctiveness_v4.py \
  tooling/tests/test_p23_102_global_distinctiveness_v4.py
python tools/p23_102_global_distinctiveness_v4.py self-test
python tools/p23_102_global_distinctiveness_v4.py plan
python tools/p23_102_global_distinctiveness_v4.py commitment-request
python tools/p23_102_global_distinctiveness_v4.py preflight
```

## Remaining prerequisites

Before any real R23-B execution, governance must still provide:

1. independent authorization binding the exact v4 commitment-request hashes;
2. a sealed, authorized, nonempty real input set and expected query count;
3. preregistered replacement order, pointer, and exhaustion state;
4. pinned structured-call model/runtime assets;
5. real-media calibration and operating thresholds;
6. two independent reviewers and an independent conflict adjudicator;
7. verified sealed review receipts for required packets;
8. a sealed real-output audit passing all fixed gates; and
9. a separate scientific GO decision.
