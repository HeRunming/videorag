# AV-TRACE migration handoff

**As of:** 2026-10-26  
**Package class:** code, metadata, plans, documentation, and model-free tooling  
**Default operation:** dry-run; no upload, token access, model execution, or
restricted-media copying

## Decision

The repository's public snapshot content gates are ready: every exported
Python file parses, internal infrastructure and machine paths are removed,
the snapshot manifest/checksum inventory is complete, generated caches are
absent, and the complete focused migration/public-release test set passes
inside both the standalone and bundle-embedded snapshots. The owner selected
Apache-2.0 for project-authored code and documentation on 2026-10-26.

The **small-file migration handoff bundle** is content-ready but is not an
authorization for credentialed upload, restricted-media transfer, or
scientific execution.

On 2026-10-26, the owner selected the public upload targets recorded in
`data/migration/publish_targets.json`. Credentials pasted into chat are treated
as exposed and are not used; GitHub publication still requires a freshly
rotated credential delivered through a protected channel.

The metadata-only Hugging Face release was published and verified in
`blackBOX25I47/videorag`. It contains no source media, model weights,
restricted indexes, credentials, or private evaluation artifacts. The exact
remote commit is recorded outside the public snapshot in
`/tmp/av-trace-publish-result.json` to avoid a self-referential release cycle.

Source-machine preparation is complete. No further research experiment should
be launched from this checkpoint. The next operation is owner-controlled
license selection, repository/repo-ID selection, credentialed upload, and
destination-machine restoration.

The bundle is built by:

```bash
cd "${AV_TRACE_ROOT:?set AV_TRACE_ROOT first}"
python scripts/build_migration_bundle.py \
  --as-of-date 2026-10-26 \
  --destination /tmp/av-trace-migration-bundle
```

The default command is a non-mutating dry run. To create the copy:

```bash
python scripts/build_migration_bundle.py \
  --as-of-date 2026-10-26 \
  --destination /tmp/av-trace-migration-bundle \
  --execute
```

`BUNDLE_SHA256SUMS` is the top-level integrity index. The reported bundle hash
is the SHA-256 of that index. The bundle also embeds the generated public
snapshot's `PUBLIC_SNAPSHOT_MANIFEST.json` and `SHA256SUMS`.

## What is included

- audited public GitHub snapshot content;
- public snapshot manifest and `SHA256SUMS`;
- HF logical asset manifest, without upload or asset bytes;
- path-rebinding policy;
- new-machine bootstrap and migration runbooks;
- research-state, R22 terminal, and R23-A/B/C status records;
- migration, HF, public-export, and readiness tooling;
- focused model-free tests;
- owner action and final migration checklists.

## What is excluded

- every path below `data/restricted/`;
- raw or copied media, model weights, caches, staging chunks, and large
  derived payloads;
- credentials, tokens, cookies, shell history, SSH private keys, `.env`
  files, and secret-manager output;
- old authorization receipts, attempt markers, nonces, and runnable runtime
  plans;
- any upload, network acquisition, model call, media decode, or GPU workload.

A private repository or private HF dataset is **not** a license override.
Original media remains excluded until the owner confirms an item-level
permission boundary that expressly permits the intended onward copy.

## Consolidated state

| Surface | State on 2026-10-26 |
|---|---|
| GitHub snapshot | `/tmp/av-trace-public`; content-ready under Apache-2.0 after automated gates |
| Migration bundle | `/tmp/av-trace-migration-bundle`; both checksum layers verified; no restricted files, symlinks, or caches |
| HF assets | Metadata-only public release verified; raw media and private-derived upload remain unauthorized |
| New-machine runbook | Ready for model-free bootstrap and path checks |
| Research state | Infrastructure mature; H1 = 0, H2 = 0, Gate A = REPAIR, scientific episodes = 0 |
| R22 | Permanent scientific NO-GO; one-shot consumed; rerun/receipt reuse prohibited |
| R23-A | Implementation repair and deterministic retained-evidence replay ready; R22 remains NO-GO |
| R23-B | v9 design/model-free preflight ready only; no authorization, execution, external signature, identity proof, or scientific GO |
| R23-C | Exposed calibration implementation ready; not run; never an untouched evaluation |

## Owner decisions still required

1. Resolve item-level third-party data rights before any media redistribution.
2. Provide GitHub organization, repository name, visibility, default branch,
   and a newly issued least-privilege credential through the environment or
   interactive `gh auth login`.
3. Decide whether a separate private-derived HF repository will be created and
   whether any private derived indexes are authorized to migrate.
4. Provide the new-machine root, OS, GPU model/count, driver/CUDA constraints,
   and protected restricted-data volume.
5. Confirm whether any private derived indexes may move.
6. Confirm the item-level boundary for media that cannot be uploaded. The
   current default is no original-media upload or bundle copy.

See:

- `docs/migration/credential_handoff.md`
- `docs/migration/final_migration_checklist.md`
- `docs/overview/authoritative_cvpr_state_2026-10-23.md`
- `data/rehearsal_plan/post_migration_cvpr_work_queue.json`
- `data/migration/migration_bundle_manifest.json`

Machine-readable build results are intentionally kept outside the public
snapshot, avoiding a self-referential hash:

- `/tmp/av-trace-public-result.json`
- `/tmp/av-trace-migration-bundle-result.json`
- `/tmp/final-public-snapshot-audit.json`

The exact final hashes should be taken from those generated files or from a
fresh `sha256sum` immediately before transfer.

## Non-reuse rule

Old authorization, approval, attempt, nonce, plan-hash, or receipt material is
historical evidence only. It cannot be copied into active runtime state or
reused on the new machine. New root paths and regenerated plans require new
hashes and fresh authorization.
