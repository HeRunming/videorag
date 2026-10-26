# Download security fix review

**Date:** 2026-09-07  
**Scope:** Task 31; acquisition planning and the transfer authorization boundary  
**Network/data transfer:** none performed

## Outcome

The download plan and authorization path now fail closed against the attacks in
RT-036 through RT-048 while retaining the shipped no-download behavior. The
CLI still passes `backend=None`; successful authorization returns
`authorized_not_executed` and `network_access_performed: false`.

## Implemented controls

| Finding/control | Resolution |
|---|---|
| RT-036 immutable revisions | Planning requires one full 40- or 64-hex revision. Branches, tags, short hashes, ref expressions, dates, and composite revisions are rejected. The check is repeated at authorization. |
| RT-037 revision/URL binding | URLs are canonicalized and provider-specific path rules bind Hugging Face and GitHub URLs to the exact repository and immutable revision. |
| RT-038 rights scope | Authorization rejects unresolved rightsholder state, candidates without `asset_reviewed` media rights, metadata-only authority language, absent authority-evidence hashes, and acquisition method `none`/unknown. Existing normative acquisition-gate validation remains mandatory. Repository license evidence alone cannot cross this boundary. |
| RT-039 manifest/candidate binding | The plan freezes the exact normalized candidate and its hash, plus manifest hash. Dataset, canonical URL, source identity, revision, publisher, source family, acquisition method, byte size, and content checksum are compared. Manifest changes are rejected. |
| RT-040 URL/host attacks | HTTPS is mandatory; userinfo, non-default ports, fragments, path traversal, ambiguous encoded separators, credential-like query fields, local names, and private/local literal IPs are rejected. Providers require an explicit host allowlist. Redirect policy is frozen into each item. |
| RT-041 backend mismatch | A future backend must return a strict result and endpoint/filesystem attestations. Trusted code validates requested/effective URL, every redirect, public peer IP, DNS-rebinding protection, destination, exclusive/symlink-safe creation, bytes, range, revision, ETag, and checksum where applicable. Any mismatch raises `DownloadRefused`. |
| RT-042 range accounting | Stored ranges use the same clamped inclusive end used for cap accounting. Authorization recomputes `end - start + 1`, checks object bounds, and verifies item and total caps. |
| RT-043 selection integrity | The CLI passes the complete selection object, not only `selected`. Planning recomputes `selection_sha256`, validates structural fields, freezes the selection hash, policy and summary hashes, available inspection/source snapshot hashes, and exact selected normalized records. Direct candidate-list plans are marked non-executable. |
| RT-044 approval authentication | Execution requires an independently supplied signer-to-role allowlist, exact ordered asset list, exact plan hash, strict UTC RFC3339 timestamp, bounded age/future skew, and the exact attestation text. An optional detached-signature verifier interface is available; signatures are rejected if no trusted verifier is supplied. No key or secret storage was added. |
| RT-045 destinations | The staging root must be absolute, normalized, non-root, and independently allowlisted at authorization. Destinations and resume paths are normalized, containment-checked, and collision-checked. A future backend must attest exclusive, symlink-safe creation and containment. |
| RT-046 resolver secrets | Resolver headers are never serialized: credential headers are explicitly rejected and all other resolver headers also fail planning. Credential-like URL query parameters are rejected. Audit events reject sensitive key names recursively. |
| RT-047 audit tampering | JSONL records now form a SHA-256 chain with sequence number, previous-entry hash, and canonical entry hash. Existing chains are verified while holding an exclusive file lock before append. `verify_audit_log` detects modified, removed/reordered, unsupported, or truncated records (except undetectable truncation of a valid suffix without an externally retained head; see follow-up). |
| RT-048 absent transport | No concrete transport was added. The backend seam is stricter but remains future-only. CLI execution cannot transfer bytes. |

## Plan and transport contract

Executable plan version `2.0` requires:

- a verified complete selection artifact;
- exact selected records and available source snapshot hashes;
- positive item and total byte caps;
- known positive object size for every item;
- immutable revisions and provider-bound HTTPS URLs;
- an approved absolute staging root;
- exact manifest and candidate bindings.

A future transport must not place credentials in the plan or result. It must
receive credentials through an out-of-band secret facility and return only
non-secret attestations. Its endpoint attestation must include the requested
URL, effective URL, complete redirect chain, connected public peer IP, and a
claim that DNS-rebinding protections were active. Its filesystem attestation
must confirm exclusive creation, symlink-safe handling, root containment, and
the exact staging root.

The current checks validate the attestation but do not make an untrusted
backend trustworthy. Enabling a concrete transport therefore still requires a
separate implementation review and integration tests around actual DNS,
redirect, socket-peer, filesystem, resume, and cleanup behavior.

## CLI behavior

`plan_dataset_download.py plan` now requires explicit `--max-item-bytes` and
`--max-total-bytes` and verifies the complete selection artifact.

`plan_dataset_download.py execute` requires:

- `--authorized-signers` containing an independently maintained signer/role map;
- one or more `--approved-staging-root` values;
- the same selection artifact whose hash is frozen in the plan.

The command still supplies no backend and therefore cannot download data.

## Tests

The adversarial suite covers:

- plan and selection tampering;
- unverified direct-input plans;
- mutable, short, ref-style, and composite revisions;
- HTTP, credentials, disallowed hosts, private targets, and query secrets;
- resolver header leakage;
- unknown sizes, mandatory caps, and range clamping/accounting;
- destination traversal and collision;
- incomplete manifest binding and unresolved rights;
- unauthorized/stale/malformed approvals and detached signature verification;
- backend URL, endpoint, destination, range, byte, revision, ETag/checksum, and filesystem-attestation mismatches;
- audit-chain verification and tamper detection;
- preservation of `authorized_not_executed` with no backend.

Acceptance command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
python -m pytest tests_data/test_download.py tests_data/test_download_security.py \
  -q -o addopts=''
```

Result on 2026-09-07: **23 passed, 13 subtests passed**.

## Follow-ups owned elsewhere

The following changes were intentionally not made because Task 31 forbids
editing adapters, models, selection, inspection output, normative schemas, or
`docs/engineering/data_adapter.md`:

1. Extend the selection/inspection contract so source snapshot hashes are
   emitted natively and required, rather than merely preserved and validated
   when available. Until then, a selection with no snapshot hashes is visibly
   recorded with an empty list but can still be executable if its complete
   artifact hash is valid.
2. Document plan version `2.0`, signer/role files, staging-root allowlists, and
   the backend attestation schema in `docs/engineering/data_adapter.md`.
3. Add a normative schema for download plans, approvals, backend attestations,
   and audit-chain checkpoints if those artifacts become interoperable inputs.
4. Persist audit chain heads in an independently protected store or sign/checkpoint
   them. A self-contained hash chain detects content edits and interior removal,
   but a valid suffix truncation cannot be detected without an external head.
5. Implement provider-specific transport adapters only after separate security
   review. They must pin DNS results through connection, validate every redirect,
   verify the socket peer, use exclusive/symlink-safe filesystem operations,
   enforce response-length/range semantics while streaming, and remove partial
   output on any failed attestation.
6. Reconcile provider aliases and canonical repository IDs in the adapter-owned
   configuration before real acquisition; the download layer intentionally does
   not guess aliases.
