# P23_102 R23-B v9 surrogate and principal-registry closure

**Decision token:** `R23_B_V9_DESIGN_READY`  
**Date:** 2026-10-23  
**Status:** isolated model-free v9 tool, v5-v8 inherited regressions, v9
regressions, plan, and external commitment request ready  
**Scientific status:** not execution, not authorization, not externally
signed, not identity proof, and not scientific GO

## Isolation

V9 adds a new tool, test file, design note, rehearsal plan, and external
commitment request. It does not modify historical authoring, Canary, marker,
capsule, or authorization surfaces. It performs zero model and authorization
calls.

## 1. Canonical surrogate diagnostic grammar

`safe_normalized_escaped` has one ASCII grammar:

```text
escaped := token*
token   := printable-ASCII-except-backslash | "\\" | "\u{HHHHHH}"
```

`HHHHHH` is exactly six uppercase hexadecimal digits. Printable ASCII is
literal except that backslash is always doubled. Every other codepoint,
including each codepoint in `U+D800..U+DFFF`, uses `\u{HHHHHH}`.

The validator strictly parses this grammar, re-encodes it canonically, and
reconstructs the complete character sequence. It derives every surrogate
position and `U+XXXX` diagnostic from that decoded sequence and requires exact
list equality. It rejects false positions/codepoints, omissions, extras,
lowercase or short escapes, alternate escape spellings, malformed ASCII, and
an envelope whose decoded sequence contains no surrogate.

## 2. Current principal registry trust boundary

The current unsigned registry schema is synthetic-unverified only:

- `registry_id` is exactly
  `synthetic-unverified-r23b-v9-principals`;
- `provisioning_status` is exactly
  `SYNTHETIC_UNVERIFIED_PRINCIPALS_ONLY`;
- `real_human_identity_proven` is the exact boolean `false`;
- self-reported `true`, wrong types, authorized/proven status strings, and
  registry-id substitutions are rejected even when the payload is rehashed.

Real identity proof cannot be expressed by adding or changing fields in this
registry. A future capability must use an independent signed principal
registry schema and verifier.

Review receipts, plans, and commitment requests explicitly state
`identity_proven=false` and `external_signature_verified=false`. Synthetic
principals still exercise the existing review/adjudication workflow without
claiming real-human identity.

## 3. Dependency closure

The v9 commitment binds the v9 tool/tests/design, inherited v8-v5 tools and
tests, the parent ambient tool, semantic manifests, the strict surrogate
grammar, the unsigned-registry schema and exact synthetic registry, runtime
constants, and the synthetic fixture.

## Validation commands

```bash
pytest -q tooling/tests/test_p23_102_global_distinctiveness_v5.py \
  tooling/tests/test_p23_102_global_distinctiveness_v6.py \
  tooling/tests/test_p23_102_global_distinctiveness_v7.py \
  tooling/tests/test_p23_102_global_distinctiveness_v8.py \
  tooling/tests/test_p23_102_global_distinctiveness_v9.py
ruff check tools/p23_102_global_distinctiveness_v9.py \
  tooling/tests/test_p23_102_global_distinctiveness_v9.py
python -m py_compile tools/p23_102_global_distinctiveness_v9.py \
  tooling/tests/test_p23_102_global_distinctiveness_v9.py
python tools/p23_102_global_distinctiveness_v9.py self-test
python tools/p23_102_global_distinctiveness_v9.py plan
python tools/p23_102_global_distinctiveness_v9.py commitment-request
python tools/p23_102_global_distinctiveness_v9.py preflight0
```

## Remaining prerequisites

Real R23-B execution still requires an independent external signature and
authorization over the exact v9 commitment, a separate signed principal
registry verifier/schema with externally established identities, sealed real
slots and inputs, pinned model/runtime assets, real-media calibration,
complete review/adjudication receipts, a sealed output audit passing all
inherited gates, and a separate scientific GO.
