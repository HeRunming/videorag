# P23_102 R23-B v8 total typed-audit boundary

**Decision token:** `R23_B_V8_DESIGN_READY`  
**Date:** 2026-10-23  
**Status:** isolated model-free v8 tool, v5-v7 inherited regressions, new v8
regressions, plan, and external commitment request ready  
**Scientific status:** not execution, not authorization, not externally
attested, and not scientific GO

## Isolation

V8 adds only:

- `tools/p23_102_global_distinctiveness_v8.py`;
- `tooling/tests/test_p23_102_global_distinctiveness_v8.py`;
- this design note;
- a v8 rehearsal plan; and
- a v8 external commitment request.

It does not modify historical authoring, Canary, marker, capsule, or
authorization surfaces. It performs zero model, media decode, retrieval,
authorization, or real-family selection calls.

## 1. Total encoding and verification boundary

The v8 `_capture_raw` path treats canonical JSON encoding, typed encoding,
typed-tree validation, canonical rendering, fallback encoding, and hashing as
one fail-closed boundary. Expected noncanonical input produces a stable
`CANONICALIZATION_FAILED` typed envelope. Any failure that prevents even that
safe envelope is converted to `ContractError`; native `UnicodeEncodeError`,
`ValueError`, `TypeError`, `KeyError`, overflow, or hostile-object exceptions
do not escape.

The persisted verifier applies the same rule to base64 decoding, typed-tree
validation, payload hashing, fallback-byte reconstruction, semantic decoding,
and identity rederivation. A malformed persisted audit tree is always a
`ContractError`.

## 2. Unpaired UTF-16 surrogate policy

A typed `str` is valid only when it contains no codepoint in
`U+D800..U+DFFF`. An invalid string is never copied into the typed tree.
Instead, v8 records a UTF-8-safe `INVALID_UNICODE_SURROGATE` envelope with:

- the failure code;
- every zero-based position;
- each `U+XXXX` codepoint; and
- an ASCII-only backslash-escaped normalized form.

This applies recursively to a top-level string, mapping key, mapping value,
list member, captured `__dict__`, and captured slots state. The resulting
fallback envelope and bundle are strictly UTF-8 encodable and deterministic.

## 3. Persistence, reload, and tamper

Bundles containing surrogate failures remain auditable `ABSTAIN` outputs.
Writing with strict UTF-8 JSON, loading in a fresh process, and verifying
against the separately trusted slot manifest reproduces the same sealed
identity and bundle hash. Any resealed mutation of the audit envelope, raw
bytes, diagnostic position/codepoint, or hash is rejected.

## 4. Dependency closure

The v8 commitment binds:

- the v8 tool, tests, and design document;
- inherited v7, v6, and v5 tools;
- inherited v7, v6, and v5 regression files;
- the parent ambient tool;
- inherited semantic schema/gate/registry/generator manifests;
- v8 typed-audit and receipt manifests;
- runtime constants, principal registry material, and the synthetic fixture.

Commitment verification recomputes the complete closure from current files and
semantic manifests.

## Validation commands

```bash
pytest -q tooling/tests/test_p23_102_global_distinctiveness_v5.py \
  tooling/tests/test_p23_102_global_distinctiveness_v6.py \
  tooling/tests/test_p23_102_global_distinctiveness_v7.py \
  tooling/tests/test_p23_102_global_distinctiveness_v8.py
ruff check tools/p23_102_global_distinctiveness_v8.py \
  tooling/tests/test_p23_102_global_distinctiveness_v8.py
python -m py_compile tools/p23_102_global_distinctiveness_v8.py \
  tooling/tests/test_p23_102_global_distinctiveness_v8.py
python tools/p23_102_global_distinctiveness_v8.py self-test
python tools/p23_102_global_distinctiveness_v8.py plan
python tools/p23_102_global_distinctiveness_v8.py commitment-request
python tools/p23_102_global_distinctiveness_v8.py preflight0
```

## Remaining prerequisites

Real R23-B execution still requires an independent signature/authorization
over the exact v8 commitment, externally sealed real slots and inputs, an
operationally identity-proofed principal registry, pinned model/runtime assets,
real-media calibration, complete review/adjudication receipts, a sealed output
audit passing every inherited gate, and a separate scientific GO.
