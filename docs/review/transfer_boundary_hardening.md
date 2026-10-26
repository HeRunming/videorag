# Transfer-boundary hardening

**Date:** 2026-09-07  
**Scope:** residual findings `NEW-002` through `NEW-006`  
**Network/media activity:** none

## Result

The package still ships no concrete transport backend, and the CLI cannot
transfer data. The transfer boundary now fails closed on the residual
red-team probes.

## Controls

### Executable plan versus metadata preview (`NEW-005`)

`create_download_plan` has an explicit `plan_mode`:

- `executable` is the default and requires a verified selection plus at least
  one valid source snapshot binding;
- every selected `provider:repository@revision` must be covered by the binding
  map; and
- `metadata_preview` is explicitly non-executable and is the only mode for
  review when snapshot evidence is absent.

The CLI exposes the same distinction as `--mode executable` and
`--mode metadata-preview`.

### Approval authenticity (`NEW-002`)

Approval-field validation without a backend may be performed offline. If no
trusted detached-signature verifier is present, the result is
`validated_not_authorized`; it cannot be interpreted as execution approval.

Every call with a non-`None` backend requires both a trusted
`ApprovalSignatureVerifier` and a valid detached signature. A signer/role JSON
allowlist alone is insufficient.

### Backend effects and attestations (`NEW-004`)

Backend claims remain schema-checked, including a complete redirect count and
one public peer IP for every requested/redirected URL hop. Missing per-hop
evidence is rejected.

After a backend reports success, the executor independently:

1. requires the staging root to exist as a real directory;
2. rejects a missing destination;
3. rejects symlinks and non-regular files;
4. verifies the resolved destination remains inside the staging root;
5. opens the destination with no-follow semantics where supported;
6. checks the opened inode did not change during verification;
7. streams and counts the bytes; and
8. recomputes SHA-256 and compares it with both the frozen expected hash and
   backend claim.

Execution is limited to full-object plans with a frozen expected SHA-256.
Range-only plans remain useful for metadata review but cannot be executed until
an independently known range digest is represented.

### URL canonicalization (`NEW-006`)

Canonicalization rejects:

- literal C0/C1 control and NUL characters;
- percent-encoded controls;
- recursively or multiply encoded `/`, `\`, `.`, and `..`;
- direct dot segments and backslashes; and
- provider object paths with a file-looking segment followed by more path,
  including `file.mp4/extra`.

Tests include the exact final-red-team forms `%252e%252e`, `%252f`, `%00`, and
`file.mp4/extra`.

### Audit suffix completeness (`NEW-003`)

`verify_audit_log` can verify an externally supplied expected chain head and
record count. Both values are required together. A mismatch rejects the log,
including deletion of a complete valid suffix.

Every future backend execution requires a non-empty external checkpoint and
the corresponding audit log. The checkpoint must be held independently of the
log being checked. An unanchored append-only file alone cannot prove suffix
completeness or detect whole-log replacement.

## Preserved boundaries

- No concrete network backend is included.
- The CLI passes `backend=None` and cannot transfer.
- Existing revision, URL host/scheme, credential, size/cap, destination,
  manifest, rights, privacy, approval-content, and freshness checks remain in
  force.
