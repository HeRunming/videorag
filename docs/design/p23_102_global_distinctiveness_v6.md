# P23_102 R23-B v6 fail-closed integrity closure

**Decision token:** `R23_B_V6_DESIGN_READY`  
**Date:** 2026-10-23  
**Status:** isolated model-free tool, P0/P1 regressions, plan, and commitment
request ready  
**Scientific status:** not execution, not authorization, not externally
attested, and not scientific GO

## Isolation and trust boundary

V6 is a new surface:

- `tools/p23_102_global_distinctiveness_v6.py`;
- `tooling/tests/test_p23_102_global_distinctiveness_v6.py`;
- this design document;
- a v6 plan; and
- a v6 external commitment request.

It does not modify the historical authoring, Canary, marker, authorization, or
capsule surfaces. It performs zero model, ASR, embedding, retrieval,
authorization, media-decode, or real-selection calls.

All verifiers make only the claim
`CURRENT_IMPLEMENTATION_RECOMPUTED_INTEGRITY_NOT_EXTERNAL_AUTHORIZATION`.
Without an independent signature or authorization over the exact commitment,
coordinated code and artifact replacement remains outside this tool's trust
boundary.

## Closure 1: sealed identities are rederived, never self-reported

`verify_bundle(bundle, trusted_slot_manifest)` requires an external sealed slot
manifest. Immutable position is the combination of:

1. bundle input order;
2. manifest `slot_index`;
3. manifest `external_slot_id`; and
4. manifest payload hash.

For every input, verification:

1. validates the exact base64 bytes and `raw_bytes_sha256`;
2. requires `exact_input_sha256 == raw_bytes_sha256`;
3. validates the complete typed audit envelope;
4. checks canonical JSON bytes, or exact fallback typed-envelope bytes when
   canonicalization failed;
5. extracts `sample_key` and `component_key` only from an unambiguous typed
   mapping pair-list string key/string value;
6. otherwise records the public key as literal `unknown`;
7. recomputes content, sample, component, and slot identities; and
8. rejects any difference from the sealed fields.

There is no replay object carrying a trusted `sealed_identity`. A
`CANONICALIZATION_FAILED` input therefore cannot choose its own identity.

Sample/component identities are derived from both the audited content and the
external slot binding. Separate sample/component content hashes remove
renameable public keys and remain slot-independent. Consequently, two
identical audit envelopes in two slots have different slot, sample, and
component identities but identical content hashes. The bundle records those
content duplicates and the global duplicate policy still rejects the set;
position cannot launder duplicate content.

## Closure 2: review packets derive from trusted successful records

Successful semantic authoring emits a sealed component/source record containing
the sample/component identities, exact input hash, family role, visual and
ambient atoms, content hash, media binding, evidence interval, and source
binding hash.

The only packet constructor is:

```python
build_review_packet(component_record, media_evidence_binding, stratum)
```

It verifies the record, requires the supplied media/evidence binding to equal
the sealed source binding, requires the mechanical family-role stratum, and
derives all packet fields:

- sample/component/slot identities;
- exact input and component-record hashes;
- content, media, and evidence hashes;
- blinded action/object atoms; and
- fixed review questions.

Verification is:

```python
verify_review_packet(packet, trusted_component_record)
```

It rebuilds the entire packet from the separately trusted record. Recomputing
the packet payload hash, packet key, reviewer bindings, receipt decision, and
outer receipt hash after changing packet content is still rejected if the
trusted component record is unchanged.

Receipts bind the trusted component-record hash and principal-registry hash.
`external_signature_verified` is explicitly false, so a successful receipt is
current integrity only.

## Closure 3: hostile type labels, mappings, and state

Every access to type/module/qualname, metaclass MRO/dictionary, mapping items,
`__dict__`, and slots is contained by `try/except`. Native hostile exceptions
do not cross the contract boundary.

A typed mapping envelope contains:

- a safe type label, module, and qualname;
- a canonically sorted key/value pair-list;
- state status and state-capture failures; and
- safely encodable `__dict__`/slots state plus a state hash when available.

Unknown objects use the same safe type metadata and state representation.
Different safely encodable state produces different audit/raw hashes. Mapping
iteration/type/state failures become an `UNSUPPORTED_TYPE` envelope or a
`ContractError`; they do not escape as `RuntimeError`, `TypeError`, or another
native exception.

Verification validates pair lists directly. It does not reconstruct a Python
dictionary from hostile or unhashable audited keys.

## Closure 4: externally provisioned principal registry

Review submissions and adjudications contain only `principal_id`; there are no
free-form reviewer/adjudicator identity fields.

The future external principal registry has:

- schema/version and registry identity;
- canonical principal IDs;
- one role per principal: `reviewer` or `adjudicator`;
- a unique opaque subject commitment per principal; and
- a registry payload hash.

Principal IDs are normalized by trim, Unicode case-fold, and internal
whitespace collapse. Registry IDs must already be in normalized form, and
submissions must exactly equal the canonical registered ID. Case aliases,
leading/trailing spaces, and whitespace aliases are rejected rather than
silently accepted. Reviewer/adjudicator roles are mutually exclusive.
Duplicate subject commitments are rejected, preventing aliases from claiming
independence.

The current synthetic registry manifest contains opaque principals only. The
tool verifies registry consistency; it does **not** prove that a principal is a
real human. The commitment request binds the registry schema/hash and the
current synthetic registry manifest/hash. A future externally provisioned
registry replaces that synthetic manifest under a new external commitment.

## P0/P1 regression coverage

The v6 tests reproduce:

- sealed identity tamper and exact/raw byte mismatch;
- duplicate malformed public identities;
- same content in different slots and global duplicate rejection;
- coordinated packet plus receipt resealing against an unchanged trusted
  component record;
- hostile metaclass, mapping, and state behavior;
- canonical pair-list public-key extraction without dictionary rebuilding;
- same-actor case and whitespace aliases;
- reviewer/adjudicator role reuse; and
- duplicate subject commitments.

## Artifacts and commands

```bash
pytest -q tooling/tests/test_p23_102_global_distinctiveness_v6.py
ruff check tools/p23_102_global_distinctiveness_v6.py \
  tooling/tests/test_p23_102_global_distinctiveness_v6.py
python -m py_compile tools/p23_102_global_distinctiveness_v6.py \
  tooling/tests/test_p23_102_global_distinctiveness_v6.py
python tools/p23_102_global_distinctiveness_v6.py self-test
python tools/p23_102_global_distinctiveness_v6.py plan
python tools/p23_102_global_distinctiveness_v6.py commitment-request
python tools/p23_102_global_distinctiveness_v6.py preflight
```

`preflight` is the requested preflight0-equivalent synthetic path. It runs no
model and consumes no authorization.

## Remaining prerequisites

Real R23-B execution still requires:

1. independent authorization/signature over the exact v6 commitment request;
2. an externally sealed slot manifest and authorized nonempty real input set;
3. an externally provisioned principal registry with operational identity
   proofing outside this tool;
4. pinned structured-call model/runtime assets;
5. preregistered replacement order, pointer, and exhaustion behavior;
6. real-media calibration and operating thresholds;
7. complete review receipts from two independent reviewers and, on conflict,
   an independent adjudicator;
8. a sealed real-output audit passing the full inherited semantic and global
   gates; and
9. a separate scientific GO decision.
