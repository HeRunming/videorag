# PRIVATE derived restoration snapshot

Date: 2026-10-28

`scripts/build_private_derived_snapshot.py` builds a narrow development
restoration snapshot for approved `private_derived_index` logical assets. It is
not an export of the full `data/restricted/` tree and does not include source
media, model weights, acquisition records, credentials, runtime authorization
state, source dossiers, or private provenance logs.

The explicit restoration roots are defined in
`data/migration/private_derived_release_manifest.json`. The builder also reads
`data/migration/hf_asset_manifest.json` and refuses any allowlisted logical
asset whose upload policy is not `private_derived_index`.

## Build

Dry-run is the default and writes nothing:

```sh
python scripts/build_private_derived_snapshot.py
```

To build, choose a new absent directory below `/tmp`:

```sh
python scripts/build_private_derived_snapshot.py \
  --execute \
  --destination /tmp/av-trace-private-derived
```

The command performs no network access, token lookup, upload, source `chmod`,
or symlink traversal. Every selected file is required to be a regular file and
is checked for exact byte count, SHA-256, valid JSON/JSONL where applicable,
known credential patterns, private keys, internal proxy/domain strings, and
the obsolete source-machine project root recorded by the policy manifest.

The snapshot preserves paths beginning with `data/restricted/` and contains:

- `PRIVATE_DERIVED_MANIFEST.json`, with per-file logical asset, path, bytes,
  SHA-256, inclusion reason, and an exclusions summary;
- `SHA256SUMS`, covering every copied file, `RESTORE.md`, and the manifest;
- `RESTORE.md`, with private-handling and clone-restoration instructions.

Verify before restoration:

```sh
cd /tmp/av-trace-private-derived
sha256sum --check SHA256SUMS
```

Then copy the preserved paths into an intentionally prepared clone:

```sh
cp -a /tmp/av-trace-private-derived/data/restricted/. \
  /path/to/AV-TRACE/data/restricted/
```

This snapshot is PRIVATE and is not suitable for a public repository. Raw
media and models must be reacquired separately from approved upstream sources
under current terms. Historical authorization references retained in
scientific manifests are audit context only: they are non-executable and do
not grant current access, download, redistribution, or upload authority.
