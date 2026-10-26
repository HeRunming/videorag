# P23_102 R23-B v7 red-team closure

**Decision token:** `R23_B_V7_DESIGN_READY`  
**Date:** 2026-10-23  
**Status:** isolated model-free tool, inherited v6 tests, new v7 regressions,
plan, and external commitment request ready  
**Scientific status:** not execution, not authorization, not externally
attested, and not scientific GO

## Isolation

V7 adds only:

- `tools/p23_102_global_distinctiveness_v7.py`;
- `tooling/tests/test_p23_102_global_distinctiveness_v7.py`;
- this design note;
- a v7 plan; and
- a v7 external commitment request.

It does not modify historical authoring, Canary, marker, capsule, or
authorization surfaces. It performs zero model, media decode, retrieval,
authorization, or real-family selection calls.

## 1. Duplicate and invalid typed public keys

Typed mapping lookup now returns exactly one of:

1. `UNIQUE`, with the unique typed value and, for public IDs, a canonical
   nonempty string;
2. `MISSING`; or
3. `DUPLICATE_OR_INVALID`.

The sealed identity records the complete extraction audit: every matching
pair's zero-based pair-list position, typed value envelope, validity status,
and string value when valid. Duplicate or invalid `sample_key` and
`component_key` fields are never downgraded to `unknown`; they enter
`hard_global_identity_failures` as `invalid_or_duplicate_public_keys`.
Therefore a normal input and a malformed duplicate-key input carrying the same
visible ID still yield `REJECT_SAMPLE_SET`.

## 2. Exact typed-audit validation

Every scalar tag has a strict contract:

- `null` has no value field;
- `bool` is an exact Boolean;
- `str` is an exact string;
- `int` is canonical decimal, forbidding plus signs, leading zeroes, and
  negative zero;
- finite `float` is exactly Python `float.hex()`;
- nonfinite float values use only `NaN`, `+Infinity`, or `-Infinity`; and
- `bytes` uses canonical validated RFC 4648 base64.

Containers, typed mappings, unsupported envelopes, type metadata, captured
state, hashes, and ordering are also validated before rendering. The
`_canonical_json_bytes_from_audit` boundary catches every unexpected native
failure and exposes only `ContractError`; malformed trees cannot leak
`ValueError`, `TypeError`, `KeyError`, or overflow errors.

## 3. Conflict-dependent adjudication

The receipt contract is now explicit:

- when two reviewers agree, adjudication has the canonical value `null`;
- if any adjudication is supplied on agreement, its field set, registry
  principal, adjudicator role, canonical ID, packet binding, and independence
  are validated first, then the receipt is rejected with
  `UNEXPECTED_ADJUDICATION_WITHOUT_CONFLICT`;
- when reviewers conflict, adjudication is mandatory and fully validated.

The builder seals only the validated packet, reviewer records, canonical
adjudication, and derived decision. It never copies an unvalidated submitted
mapping into a receipt.

## 4. Transitive dependency closure

The external commitment embeds a dependency manifest and manifest hash. It
binds and rechecks from disk:

- the v7 tool and tests;
- inherited v6 and v5 tools and the inherited v6 regression file;
- `p23_102_query_authoring_v2.py`, the parent ambient tool;
- the v7 design note;
- inherited schema, gate, visual registry, family registry, generator, and
  parent ambient schema manifests;
- v7 typed-audit and receipt schemas;
- reviewer principal registry schema and current synthetic registry;
- runtime constants; and
- the synthetic fixture used by self-test/preflight0.

Commitment verification recomputes this closure. Changing only the parent tool
hash or only the fixture invalidates the old commitment.

## Regression and validation commands

```bash
pytest -q tooling/tests/test_p23_102_global_distinctiveness_v6.py \
  tooling/tests/test_p23_102_global_distinctiveness_v7.py
ruff check tools/p23_102_global_distinctiveness_v7.py \
  tooling/tests/test_p23_102_global_distinctiveness_v7.py
python -m py_compile tools/p23_102_global_distinctiveness_v7.py \
  tooling/tests/test_p23_102_global_distinctiveness_v7.py
python tools/p23_102_global_distinctiveness_v7.py self-test
python tools/p23_102_global_distinctiveness_v7.py plan
python tools/p23_102_global_distinctiveness_v7.py commitment-request
python tools/p23_102_global_distinctiveness_v7.py preflight0
```

## Remaining prerequisites

Real R23-B execution still requires an independent signature/authorization
over the exact v7 commitment, externally sealed real slots and inputs, an
operationally identity-proofed principal registry, pinned model/runtime assets,
real-media calibration, complete review/adjudication receipts, a sealed output
audit passing all inherited gates, and a separate scientific GO.
