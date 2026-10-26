# Reproducible public repository export

**As of:** 2026-10-23  
**Default release status:** `BLOCKED_LICENSE`

The mixed working tree must not be pushed directly. Build a separate snapshot
from the provisional release-ready file manifest produced by
`scripts/audit_public_release.py` and the explicit strategy table in
`data/migration/public_repo_manifest.json`.

## Safety properties

The snapshot builder:

- is independent of Git tracking state and does not modify source files;
- defaults to a dry run;
- copies only regular files and refuses to follow source or destination
  symlinks;
- requires a new or empty staging directory and uses exclusive file creation,
  so it will not overwrite an existing snapshot;
- preserves repository-relative paths and file permission modes;
- applies an explicit `exclude`, `redact-generated`, `rewrite-copy`, or
  `require-owner` decision to every audit-blocked path;
- excludes old blocked review/run material while retaining the public-ready
  README, current documentation, source, tools, scripts, and tests;
- replaces the large source-exposure alias artifact with a small public hash
  commitment and disposition summary;
- audits every staged file again for secrets, internal infrastructure,
  workstation paths, private run/governance identifiers, binary content,
  size, and links;
- writes `SHA256SUMS` and `PUBLIC_SNAPSHOT_MANIFEST.json`.

`rewrite-copy` changes only the staged UTF-8 copy. Historical files in the
working tree are never edited.

## Dry run and build

```bash
cd "$REPO_ROOT"

# Non-mutating plan. This is the default.
python scripts/build_public_repo_snapshot.py \
  --as-of-date 2026-10-23 \
  --json-output /tmp/av-trace-public-dry-run.json

# Build into the default clean staging location.
python scripts/build_public_repo_snapshot.py \
  --as-of-date 2026-10-23 \
  --execute
```

The default destination is `/tmp/av-trace-public`. Remove or archive an old
staging directory deliberately before rebuilding; the builder will not merge
or overwrite it.

## License owner interface

The default snapshot contains `LICENSE_DECISION_REQUIRED`, not a fabricated
`LICENSE`, and reports `release_status=BLOCKED_LICENSE`. After authorized
owners select a code license and provide its actual text:

```bash
python scripts/build_public_repo_snapshot.py \
  --execute \
  --destination /tmp/av-trace-public-licensed \
  --license-choice '<owner-approved identifier>' \
  --license-file /path/to/owner-approved-license.txt
```

Both options are required together. The builder copies the supplied text as
`LICENSE`; it does not download, infer, or generate license terms. Data, media,
model, annotation, and third-party notices remain separate rights decisions.

## Verification

```bash
cd /tmp/av-trace-public
sha256sum --check SHA256SUMS
python scripts/audit_public_release.py
pytest -q tests/test_build_public_repo_snapshot.py
```

`PUBLIC_SNAPSHOT_MANIFEST.json` records:

- source audit counts;
- every blocked-path policy decision;
- every payload path, mode, byte count, and SHA-256;
- file-level content blockers;
- remaining owner blockers;
- `snapshot_content_ready` and `release_status`.

The two index files do not hash themselves; this exclusion is declared in the
manifest. A snapshot is content-ready only when its file-level blocker count is
zero. A content-ready snapshot can still be globally blocked on the code
license.

## GitHub command templates — do not run from the mixed tree

Suggested branch and tag:

- branch: `public/main`
- first tag after owner approval: `public-v0.1.0`

Using Git:

```bash
cd /tmp/av-trace-public-licensed
git init -b main
git add --all
git commit -m "Initial public AV-TRACE snapshot"
git remote add origin 'git@github.com:<owner>/<public-repo>.git'
git push -u origin main
git tag -a public-v0.1.0 -m "Public snapshot v0.1.0"
git push origin public-v0.1.0
```

Using GitHub CLI:

```bash
cd /tmp/av-trace-public-licensed
gh repo create '<owner>/<public-repo>' --public --source=. --remote=origin
git push -u origin main
git push origin public-v0.1.0
```

These are templates only. Do not upload until license, third-party rights,
security, privacy, and scientific-governance owners approve the exact snapshot.
