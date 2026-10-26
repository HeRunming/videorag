# Final migration checklist

**As of:** 2026-10-26  
**Statuses:** `CURRENT` can be completed on the source machine; `OWNER`
requires an authorized owner decision; `NEW-MACHINE` requires the destination
host.

## Current/source-machine actions

- [x] **CURRENT** Run focused model-free tests in the source repository:

  ```bash
  python -m pytest -q \
    tests/test_audit_public_release.py \
    tests/test_build_migration_bundle.py \
    tests/test_build_public_repo_snapshot.py \
    tests/test_migration_bootstrap.py \
    tests/test_hf_migration_tools.py
  ```

- [x] **CURRENT** Run the bundle dry-run and record file count, bytes, and the
      SHA-256 of `BUNDLE_SHA256SUMS`.
- [x] **CURRENT** Execute only to a new empty
      `/tmp/av-trace-migration-bundle`.
- [x] **CURRENT** Verify:

  ```bash
  cd /tmp/av-trace-migration-bundle
  sha256sum --check BUNDLE_SHA256SUMS
  cd public_snapshot
  sha256sum --check SHA256SUMS
  ```

- [x] **CURRENT** Run the same focused tests inside both
      `/tmp/av-trace-public` and the bundle-embedded `public_snapshot`.
- [x] **CURRENT** Confirm the bundle contains no `data/restricted/`, symlink,
      secret file, original media, model weight, cache, or staging chunk.
- [x] **CURRENT** Confirm every exported Python file parses and that the
      standalone snapshot exactly matches the bundle-embedded snapshot.
- [x] **CURRENT** Preserve R22 as a permanent terminal NO-GO. Do not rerun,
      redraw, substitute a reserve, or install retained outputs as success.

Source-machine work is now stopped. All unchecked items below require an
owner decision or the destination machine.

## Owner actions

- [x] **OWNER** Select the code license and provide the actual approved license
      text to the public snapshot builder: Apache-2.0.
- [ ] **OWNER** Provide GitHub organization, repository name, visibility, and
      default branch.
- [ ] **OWNER** Issue a new least-privilege GitHub credential through hidden
      interactive login or environment injection; never write it to disk in
      this repository.
- [ ] **OWNER** Provide HF organization and exact repo IDs for public metadata,
      optional private derived artifacts, and any future restricted
      architecture.
- [x] **OWNER** Public metadata target selected and initial metadata-only
      release verified at `blackBOX25I47/videorag`; the exact commit receipt is
      stored outside the public snapshot in
      `/tmp/av-trace-publish-result.json`.
- [ ] **OWNER** Decide each HF repo's public/private/gated setting. Private or
      gated status does not grant redistribution rights.
- [ ] **OWNER** Decide whether private derived indexes will migrate. Default:
      do not migrate.
- [ ] **OWNER** Confirm in writing which original media, if any, may be copied
      onward. Default: none may be uploaded or bundled.
- [ ] **OWNER** Provide destination root, OS/version, filesystem/volume policy,
      GPU model/count, driver/CUDA constraints, and required system package
      channel.
- [ ] **OWNER** Approve retention/deletion timing for old-machine staging only
      after independent destination and backup verification.

## New-machine actions

- [ ] **NEW-MACHINE** Clone the approved code snapshot into the owner-selected
      root without automatically materializing unreviewed LFS content.
- [ ] **NEW-MACHINE** Establish fresh GitHub/HF authentication following
      `docs/migration/credential_handoff.md`.
- [ ] **NEW-MACHINE** Create protected restricted storage (`0700` directories,
      `0600` files), with no symlinks.
- [ ] **NEW-MACHINE** Run `scripts/bootstrap_new_machine.py --mode check`.
- [ ] **NEW-MACHINE** Rebind paths via `--repo-root`, `AV_TRACE_ROOT`, or
      script-relative resolution. Do not string-rewrite historical records.
- [ ] **NEW-MACHINE** Re-download upstream model/assets only at pinned
      revisions and only after current access/rights approval.
- [ ] **NEW-MACHINE** Rebuild deterministic/project-owned indexes only after
      their source dependencies verify.
- [ ] **NEW-MACHINE** Run `scripts/verify_migration_readiness.py` and focused
      model-free tests before any media/model execution.
- [ ] **NEW-MACHINE** Generate new runtime plans and plan hashes for the new
      root.
- [ ] **NEW-MACHINE** Obtain fresh authorization bound to those new hashes.

## Non-reusable historical authority

The following from the old machine is never active authority on the new
machine:

- authorization JSON, approval receipts, attempt markers, nonce directories,
  one-shot receipts, or old plan hashes;
- old runtime plans or results with source-machine absolute paths;
- R21/R22 retained outputs, capsules, logs, or failure evidence;
- credentials or authentication caches.

These may be retained only as immutable, read-only audit evidence when
explicitly approved. **Old authorization/attempt state cannot be reused.**

## Final GO criteria

Migration is complete only when:

1. both bundle checksum layers pass;
2. the owner decisions above are recorded without secret values;
3. destination credentials are new and scoped;
4. path checks report no current public-code blocker;
5. restricted permissions and no-symlink checks pass;
6. required upstream revisions/assets verify;
7. no old authority is active;
8. rights/privacy/redistribution boundaries are approved;
9. model-free tests pass; and
10. any future execution receives separate, fresh authorization.
