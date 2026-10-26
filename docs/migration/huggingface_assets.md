# Hugging Face asset migration plan

**Inventory date:** 2026-10-23  
**Status:** dry-run migration package; no upload authorization and no upload
performed.

The machine-readable source of truth is
`data/migration/hf_asset_manifest.json`. The two scripts in this package do not
read Hugging Face tokens and do not perform network operations.

## Decisions

1. **Do not mirror third-party model weights.** Preserve repository IDs,
   immutable revisions, selected-file identities, and local manifest hashes;
   re-download models from their upstream model repositories.
2. **Do not upload current restricted media.** A private Hugging Face
   repository is access control, not permission to redistribute. EPIC,
   CaptainCook4D, LongVideoBench, mixed university media, and the current NOAA
   exact-five package remain blocked from rehosting.
3. **Use a public repository only for reviewed metadata.** It must contain
   redacted, non-substitutive metadata, upstream pointers, hashes, licenses, and
   reconstruction instructions—not source audio/video, dense derivatives,
   access receipts, cookies, headers, or private identities.
4. **Use a separate private repository for approved derived/index artifacts.**
   This does not make the artifacts publicly releasable and does not admit raw
   private governance or authorization records.
5. **Rebuild project-owned synthetic outputs from code** instead of spending
   storage and transfer budget on generated binaries and reports.

## Point-in-time inventory

The scan found **1,427 files / 111,971,384,441 bytes** under
`data/restricted/`. The manifest also covers the relevant generated MVP
outputs, `data/hf_recon/`, and `data/source_recon/`. Logical asset groups are
used to keep the plan reviewable; they are not a claim that every grouped file
has identical rights.

| Policy | Logical assets | Files | Bytes | Disposition |
|---|---:|---:|---:|---|
| `redownload_upstream` | 12 | 123 | 78,675,538,324 | Upload identity records only; re-download NOAA/model assets upstream |
| `never_upload` | 6 | 336 | 22,740,241,801 | Exclude media, private governance, authorization, and run artifacts |
| `delete_after_verified_migration` | 1 | 157 | 10,273,904,267 | EPIC P23 transfer chunks; never upload; deletion only after independent verification |
| `private_derived_index` | 11 | 811 | 281,700,049 | Candidate for the private derived repository after owner review |
| `rebuild_from_code` | 3 | 377 | 22,157,446 | Re-run project code |
| `public_metadata_only` | 2 | 411 | 18,985,349 | Candidate pool requiring redaction and item-level review |

These are logical policy totals. The practical transfer estimate is:

- **immediately command-eligible private-derived candidates: 135,628,713
  bytes / 174 files across 5 logical assets**, still using placeholder repo IDs
  and therefore not executable as-is;
- **pending narrower private allowlists: 146,071,336 bytes / 637 files across 6
  logical assets**;
- **current public upload: 0 bytes** because both metadata groups have
  `release_review_status=pending`;
- **maximum private-derived candidate set: 281,700,049 bytes** before
  exclusions/redaction;
- **maximum current public-metadata candidate pool: 18,985,349 bytes**, not all
  automatically publishable;
- **model/source re-download on the new machine: 78,675,538,324 bytes** if every
  currently inventoried upstream model and NOAA raw source is restored;
- **current media/governance exclusions: 22,740,241,801 bytes**;
- **duplicate EPIC range staging that should not migrate:
  10,273,904,267 bytes**.

## Proposed repositories

The manifest uses placeholders so no command can accidentally target a real
organization.

### `blackBOX25I47/videorag`

- Type: Hugging Face **dataset**
- Visibility: public
- Gated: no; metadata intended for public reproducibility should not depend on
  an access request
- Contents: redacted asset inventory, upstream URLs/repository IDs, revisions,
  verified checksums, licenses/attribution pointers, reconstruction commands,
  and non-sensitive summaries
- Explicit exclusions: payload snapshots, HTTP authorization evidence,
  internal infrastructure, private identities, media, features that substitute
  for media, and model weights

### `ORG/av-trace-restricted-media`

- Type: Hugging Face **dataset**
- Visibility: private; optionally gated later only if external access is ever
  authorized
- Current contents: **none**
- Reason: every current real-media family has an unresolved or explicit
  no-redistribution boundary. Creating the repository is not authorization to
  populate it.

### `ORG/av-trace-private-derived`

- Type: Hugging Face **dataset**
- Visibility: private
- Contents: separately approved indexes, features, machine-provisional
  artifacts, and non-model experiment outputs
- Exclusions: source media, model weights, evaluator keys, authorization
  receipts, raw gateway attempts, untouched-test identities, and records whose
  scientific-integrity or privacy risk exceeds their portability value

No new model repository is proposed. Model inventory records point to exact
upstream revisions. The private-derived and restricted-media repository names
remain placeholders because the owner has not authorized targets for them.

## License and release blockers

### EPIC-KITCHENS / EPIC-SOUNDS

Project records use **CC BY-NC 4.0 / source-specific terms** for relevant
components. That shorthand is not a file-level release approval. The exact
P23 and wave-1 acquisition manifests explicitly state that public release or
redistribution is not authorized. The recordings contain identifiable homes,
routines, voices, and participants. Therefore:

- do not upload the three EPIC videos, including to a private HF repository;
- do not publish dense speech/visual/audio indexes;
- keep derivatives private and noncommercial unless a separate rights/privacy
  decision clears a narrower set.

### CaptainCook4D

The local record verifies an Apache-2.0 dataset statement and reports
consent/IRB statements, but the operative linked consent/IRB documents are not
archived. Task188 authorizes restricted internal research and expressly says no
public release or redistribution. An Apache license on downloader code—or even
a dataset-level statement—does not by itself establish that identifiable
participant video may be rehosted. Therefore raw media remains `never_upload`;
derived indexes remain private.

### HoloAssist

The official project declaration captured locally is
`CDLA-Permissive-2.0`, while a third-party HF mirror reports `Apache-2.0`.
Those are not treated as equivalent. The official declaration controls pending
reconciliation, and the exact operative dataset license/media route is not
closed. No HoloAssist media was inventoried locally. The 41 tiny technical
timing files and sealed opaque universe may be considered only for the private
derived repository; selected identities must remain sealed.

### NOAA and other public sources

The five NOAA files came from official public CDN URLs, but the recorded
authorization holds public redistribution. Government provenance is not a
blanket clearance for item-level third-party content, logos/trademarks,
endorsement, faces/voices, or privacy/publicity. Prefer exact upstream
re-download. A later reviewer may clear individual NOAA-produced assets, but
this package does not.

The same item-level rule applies to the Oxford, MIT, and Yale mini-pilot
sources. Their folder mixes licenses and attribution/share-alike obligations;
it must not be assigned one blanket license.

### LongVideoBench

The exact-five acquisition authorization excludes release and redistribution.
The benchmark's repository access does not establish rehosting rights for the
underlying videos or subtitles. Reacquire from the pinned upstream only under
renewed authorization.

### Models

Model acquisition records mark local redistribution as unauthorized or pending
release review. Even where an upstream model declares Apache-2.0 or another
permissive license, the preferred migration is an immutable-revision
re-download. The archived exact-revision metadata for
`openai/clip-vit-base-patch32` did not declare a license; verify current
upstream terms before restoring it.

## Dry-run preparation

`scripts/prepare_hf_upload.py`:

- loads and validates the migration manifest;
- does not inspect environment variables, HF cache credentials, token files, or
  account identity;
- uses no network;
- does not copy, chmod, delete, or upload files;
- refuses absolute paths, `..`, special files, and any symlink component;
- computes SHA-256 only for files below a configurable threshold;
- defers large-file identity to existing verified hashes/manifests;
- emits inert `hf upload` command text only for stageable policies. The current
  candidates need explicit destination subpaths, which the locally installed
  resumable `upload-large-folder` CLI does not expose.

Examples:

```bash
# Summary of every policy.
python scripts/prepare_hf_upload.py

# Generate a per-file plan for the approved private-derived candidates.
python scripts/prepare_hf_upload.py \
  --policy private_derived_index \
  --json-output /tmp/av-trace-private-derived-plan.json

# Inspect only the public metadata candidate pool.
python scripts/prepare_hf_upload.py \
  --policy public_metadata_only \
  --format json
```

The script does not create a staging copy. This is intentional: copying
restricted payloads into a second tree would increase exposure and storage
without upload authorization.

## Large files, LFS/Xet, and resumability

For an approved upload:

- use the current Hugging Face CLI and repository storage backend for large
  files rather than normal Git blobs;
- prefer `hf upload-large-folder` for a separately approved large directory
  only when that directory is intended to map to the repository root; its local
  task cache supports resuming/retrying, but the locally installed command does
  not accept a destination subpath;
- use `hf upload` for the current small, explicitly mapped derived directories;
- keep original logical files when possible; do not create ad hoc archive
  shards merely to bypass hosting limits;
- if an external archive format actually requires parts, the dry-run plan
  suggests **5 GiB** parts, records a part manifest, and requires verification
  after reassembly;
- keep commits reviewable and avoid a single enormous repository-wide commit;
- treat every multi-gigabyte file as a preflight item for quota, storage,
  repository limits, and transfer-window review;
- do not put tokens on a command line or in generated plans.

The dry-run commands deliberately use placeholder repository IDs and must be
reviewed against current official Hugging Face documentation immediately before
execution. Platform behavior and limits can change.

## Upload order

1. Create repository shells with the correct type and visibility. Confirm the
   restricted-media repository is empty.
2. Upload the migration manifest and reviewed README/license notices to the
   public-metadata repository.
3. Upload the smallest reviewed public metadata first; verify that no private
   path, internal host, credential evidence, or source payload is visible.
4. Upload private derived manifests and small JSON/CSV indexes.
5. Upload any approved larger private feature/index files last, with resumable
   folder upload and post-download SHA-256 verification.
6. Re-download third-party models directly from exact upstream revisions on the
   new machine.
7. Re-download NOAA or other source media only from upstream and only when the
   destination operator has the required authorization.
8. Rebuild synthetic/generated outputs from code.
9. Verify the restored machine before removing any old copy.

## Verification and permissions

Generate a dry-run plan on the source machine, transfer or download approved
content through a separate authorized process, then run:

```bash
python scripts/verify_hf_mirror.py /path/to/downloaded/repo \
  --manifest data/migration/hf_asset_manifest.json \
  --plan /tmp/av-trace-private-derived-plan.json \
  --policy private_derived_index \
  --require-private-modes \
  --json-output /tmp/av-trace-private-derived-verification.json
```

With a plan, verification is per-file: path, byte count, available SHA-256,
symlink rejection, and optional private permission checks. Without a plan,
verification is limited to asset totals under proposed HF paths.

Recommended local permissions after download:

- private repository root/directories: `0700`;
- private files: `0600`;
- public metadata working copy: no broader than `0755` directories and `0644`
  files, subject to local policy;
- caches containing private repository data: keep on encrypted/restricted
  storage and do not share between users.

The verifier reports permissions but never changes them.

## Deletion and rollback

- Never use a force-push or history rewrite as the primary response to an
  accidentally uploaded restricted file. Immediately disable access, notify
  the repository/security owners, revoke exposed credentials if any, and follow
  the hosting provider's purge process.
- Delete remote files only from an explicit deletion manifest containing path,
  prior commit, reason, and owner approval. A normal delete commit may not
  remove historical accessibility.
- Keep source copies until: remote download completes, `verify_hf_mirror.py`
  passes, permissions are checked, the reconstruction test succeeds, and an
  independent backup exists.
- The EPIC P23 range segments are the only current
  `delete_after_verified_migration` group. They are duplicate transfer staging,
  not upload material. Delete them only after the final 10,814,161,307-byte MP4
  and at least one independent backup match the recorded SHA-256.
- Do not delete local model manifests after replacing weights with upstream
  re-download; they are the provenance and pinning record.

## Stop conditions

Stop before upload if any of the following is true:

- a repository ID is still a placeholder;
- visibility or gating is not independently confirmed;
- any path traverses a symlink or escapes the repository root;
- an asset is marked `never_upload`, `redownload_upstream`,
  `rebuild_from_code`, or `delete_after_verified_migration`;
- a public candidate includes raw HTTP bodies/headers, internal infrastructure,
  authorization evidence, identities, or source-substitutive data;
- manifest bytes differ from observed bytes;
- a large file lacks an existing verified identity;
- rights, privacy, attribution, deletion, or incident-response ownership is
  unresolved.
