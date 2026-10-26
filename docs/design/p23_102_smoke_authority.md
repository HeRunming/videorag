# P23_102 technical-smoke authority and receipt system

**Date:** 2026-10-14  
**Readiness token:** `P23_102_SMOKE_AUTHORITY_INDEPENDENT_CUSTODY_READY`

## Scope and authorization boundary

`tools/p23_102_smoke_authority.py` supplies a strict local Ed25519 authority
registry and signed-review-receipt verifier for the P23_102 technical smoke
v2. It does not alter the freeze, adapter, repaired runner, smoke runner, or
their existing unsigned overlay parser. It does not run a model or authorize
a smoke by itself.

This change initializes authority keys and records their public identities.
It intentionally creates **no review request, no GO receipt, and no approval
overlay**. The registry is an allowlist, not an approval.

## Independent roles and key custody

The exact role allowlist is:

1. `live_wiring_reviewer`
2. `red_team_reviewer`

Each role has a different Ed25519 public key, fingerprint, and authority ID.
The registry rejects additional, missing, reordered, duplicate, or
same-public-key authorities.

Public identities are stored in:

```text
data/restricted/p23_102_technical_smoke_v2/authority_registry.json
```

The checked public registry contains only public identity data. It has no
private-key bytes, private-key path, custody-root path, or secret reference.
Receipt and overlay verification load only this public registry.

The initialization command's compatibility/provisioning layout is:

```text
data/restricted/p23_102_technical_smoke_v2/
  authorities/live_wiring_reviewer/private_key.pem
  authorities/red_team_reviewer/private_key.pem
```

This layout is not a signing-time shared-custody requirement. Signing resolves
one selected role to one role-specific private root or one explicit key path.
It validates and reads only that private key. It does not enumerate, validate,
open, or require the other role's private root or key, and it does not require
the two custody roots to have a common parent.

For actual independent custody, distribute each existing role key to a
different filesystem view. Each view needs only:

```text
authority_registry.json                 mode 0644
PRIVATE_ROOT/                           mode 0700
  private_key.pem                       mode 0600
```

Alternatively, the key may have a role-local filename and be selected with
`--private-key`. The containing directory still must have mode `0700`, and the
key must be a regular, non-symlink file with mode `0600`. A key is accepted
only if its derived public-key fingerprint equals the selected role's existing
registry fingerprint. This preserves the current public identities when keys
are moved into separate custody roots.

The shared `authorities` directory is required only by the two-key
initialization/idempotence validation workflow. In that provisioning layout,
the directory and both role directories must have mode `0700`. Registry
loading requires mode `0644`. Permission drift, a symlink, a partial
registry/key state, a key-to-registry mismatch, or copied key material fails
closed.

The restricted data tree is repository-ignored. Only the public registry is
intended for publication or controlled transfer. Private keys must remain
under their role directories and must never be copied into a receipt,
overlay, log, or registry.

## Initialization

Run:

```text
python tools/p23_102_smoke_authority.py --init-authorities
```

Initialization is create-exclusive. With no authority state, it creates two
independent keys, writes the private files with mode `0600`, and writes the
public registry with mode `0644`. If a complete state already exists, the
command validates every registry identity, directory/file permission, and
private/public key relationship before returning
`AUTHORITIES_ALREADY_INITIALIZED`.

Initialization does not repair or overwrite a partial, malformed, copied-key,
or permission-drifted state. Such states require manual investigation.

Initialization is the only operation that intentionally handles both private
keys. It is an administrative provisioning check, not a reviewer signing
operation.

## Canonical signed receipt

The input to `--sign-receipt` is a receipt request, not an authorization
overlay. Its exact top-level fields are:

```text
schema_version
receipt_id
issued_at_utc
expires_at_utc
bound_execution
```

The tool adds the selected allowlisted role, authority ID, and key
fingerprint. It signs the resulting `signed_payload` using Ed25519 over:

```text
UTF-8 JSON
json.dumps(sort_keys=true,separators=(',',':'),
           ensure_ascii=false,allow_nan=false)
no trailing newline
```

The signed payload binds:

- role;
- authority ID;
- public-key fingerprint;
- receipt ID;
- UTC issue and expiry;
- one-run nonce;
- review decision exactly `GO`;
- all smoke-only/no-interpretation declarations; and
- the exact execution hashes listed below.

Required execution binding fields are:

```text
freeze_sha256
adapter_attestation_sha256
runner_sha256
repaired_runner_sha256
module_set_sha256
all_model_set_sha256
assignment_plan_sha256
checkpoint_contract_sha256
output_root_sha256
```

The one-run nonce is 32–128 URL-safe identifier characters. Every hash uses
lowercase `sha256:` plus 64 hexadecimal characters.

Required declarations are all exactly `true`:

```text
technical_smoke_only
no_scientific_interpretation
no_competence_or_performance_interpretation
single_run_only
immutable_freeze_remains_unauthorized
```

Receipt lifetime is positive and at most 900 seconds. UTC timestamps use a
terminal `Z`; expired and not-yet-valid requests or receipts fail closed.

Signing syntax:

```text
python tools/p23_102_smoke_authority.py \
  --sign-receipt live_wiring_reviewer \
  --registry /public-view/authority_registry.json \
  --private-root /custody/live-wiring \
  --payload REQUEST.json \
  --output LIVE_RECEIPT.json
```

The role-specific root form expects
`/custody/live-wiring/private_key.pem`. An explicit key filename is also
supported:

```text
python tools/p23_102_smoke_authority.py \
  --sign-receipt red_team_reviewer \
  --registry /public-view/authority_registry.json \
  --private-key /red-team-custody/red-review-key.pem \
  --payload REQUEST.json \
  --output RED_RECEIPT.json
```

`--private-root`, `--private-key`, and the compatibility
`--authorities-root` option are mutually exclusive. If none is supplied, the
selected role uses its own default role root under the provisioning layout.
The compatibility option resolves directly to
`AUTHORITIES_ROOT/SELECTED_ROLE/private_key.pem`; it does not validate or read
the other role.

The output path is create-exclusive and mode `0600`. The payload and output
paths must differ. A reviewer must sign only after independently completing
the review represented by its role.

## Receipt and overlay verification

Verify a receipt:

```text
python tools/p23_102_smoke_authority.py \
  --verify-receipt LIVE_RECEIPT.json
```

Verification requires:

- exact schemas with no unknown or missing fields;
- duplicate-JSON-key rejection;
- the exact role allowlist;
- exact registry authority ID and fingerprint;
- a currently valid time window;
- canonical Ed25519 signature validity; and
- the smoke-only declarations and `GO` decision.

No verification function or verification CLI accepts or loads a private-root,
private-key, or shared-authorities-root dependency. Deleting or withholding
all private custody roots does not prevent verification of an already signed
receipt.

The approval-overlay schema used by this authority tool has:

```text
schema_version
authorization_id
issued_at_utc
expires_at_utc
bound_execution
approvals
```

`approvals` must contain exactly one receipt under each exact role name.
Verification syntax:

```text
python tools/p23_102_smoke_authority.py \
  --verify-overlay-approvals OVERLAY.json
```

Overlay verification requires:

- both signatures to be valid against the registry;
- each receipt to occupy and sign its own role;
- distinct authority IDs and key fingerprints;
- both receipts to bind byte-equivalent canonical execution content;
- that content to equal the overlay's `bound_execution`;
- both receipt intervals to be fully contained in the overlay interval; and
- the overlay interval to be positive, current, and at most 900 seconds.

Changing any binding, nonce, declaration, decision, role, identity, issue
time, or expiry after signing invalidates the signature or overlay.

## Cryptographic backend and failure behavior

The primary backend is Python `cryptography`. If it is not importable, the
tool uses the local `openssl` executable for Ed25519 key generation,
public-key derivation, signing, and verification. If neither backend is
available, the operation fails closed. There is no non-cryptographic
fallback.

CLI failures emit one compact JSON object with status `FAIL_CLOSED`, a typed
error code, and a diagnostic message, then exit with status 2.

## Integration status

The existing smoke runner and its frozen/adapter artifacts were deliberately
not modified. Consequently, successful
`--verify-overlay-approvals` establishes that the two authority receipts are
cryptographically valid under this system, but it does not silently patch or
bypass the runner's current overlay parser. Runner integration requires a
separate owned change and must preserve all existing nonce and hash checks.

No GO receipt or signed approval overlay exists as part of this readiness
change.

## Independent-custody test evidence

`tooling/tests/test_p23_102_smoke_authority.py` proves that:

- each role signs in a filesystem view containing only the public registry
  and that role's private key;
- an audited signing call reads exactly the selected role's private-key file;
- neither role can sign with the other role's key because the
  key-to-registry fingerprint check fails closed;
- the two public fingerprints and signed identities remain distinct;
- an explicit role-specific key path has no shared-parent dependency;
- the registry is public-only; and
- receipt verification succeeds after the private authority tree is removed.

The public registry fingerprints remain:

```text
live_wiring_reviewer
sha256:d75604df8e6611f75043dbcebfce1f040752d4b764ec720c63cbae0607628a85

red_team_reviewer
sha256:44816a89532f9502810cc7807475102b92d6a375e6e599cc7d992a3ff503490f
```

No private-key bytes are included in this document, the registry, receipts,
or test diagnostics.

`P23_102_SMOKE_AUTHORITY_INDEPENDENT_CUSTODY_READY`
