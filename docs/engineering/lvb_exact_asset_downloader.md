# LongVideoBench exact five-asset downloader

## Scope

`tools/lvb_exact_asset_downloader.py` is a fail-closed downloader for exactly
five MP4 members and their five English subtitle JSON members at:

- repository: `longvideobench/LongVideoBench`
- revision: `60d1c89c1919a198b73be39c2babb213b29d6a5c`

It does not scan or extract a tar archive and has no interface for selecting
other members. Source objects, header ranges, payload intervals, object sizes,
and destination basenames are frozen in
`data/acquisition_plan/lvb01_exact_asset_plan.json`. That plan is derived only
from the two independently audited range CSVs. The downloader recomputes the
plan and rejects any drift before it reads credentials or uses the network.

## Frozen transfer budget

| Target | Bytes |
|---|---:|
| `-PgbM2MhcYQ.mp4` | 62,830,440 |
| `-eRimFrm6kQ.mp4` | 90,220,390 |
| `-7wwfGJXEZg.mp4` | 153,008,405 |
| `H5vpBCLo74U.mp4` | 36,357,778 |
| `TMe7oXMJoSM.mp4` | 238,302,656 |
| **Video subtotal** | **580,719,669** |
| `-PgbM2MhcYQ_en.json` | 142,437 |
| `-eRimFrm6kQ_en.json` | 96,086 |
| `-7wwfGJXEZg_en.json` | 57,351 |
| `H5vpBCLo74U_en.json` | 69,540 |
| `TMe7oXMJoSM_en.json` | 43,973 |
| **Subtitle subtotal** | **409,387** |
| **Exact payload total** | **581,129,056** |

There are also ten mandatory 512-byte tar-header revalidation responses, for a
maximum expected successful wire body total of 581,134,176 bytes when nothing
is resumed or already complete. Each response is at most 8 MiB. A Range equal
to a complete archive object or multipart part is rejected.

## Safety behavior

- The bearer token is obtained with `huggingface_hub.get_token()` only in
  execute mode.
- Authorization is attached only to the exact canonical
  `https://huggingface.co:443` origin. It is never forwarded to a CDN.
- Redirect URLs are held only in memory. No URL, cookie, token, request header,
  proxy credential, or request log is persisted.
- A single persistent HTTP client and per-object process-local effective URL
  cache are used.
- Every response must be HTTP 206 with an exact `Content-Length`,
  `Content-Range`, identity encoding, and bounded body.
- Immediately before a target's payload transfer, its exact 512-byte tar
  header is fetched and checked for checksum, full path, basename, regular-file
  type, declared size, and exact data offset.
- Files are written with mode `0600` to `.partial`, fsynced after every chunk,
  hashed, content-validated, fsynced again, and atomically renamed.
- Resume is allowed only when `.partial` and `.partial.json` agree on the
  frozen plan binding, byte count, prefix hash, and exact chunk boundary. The
  existing prefix is re-hashed.
- A completed file is skipped only when its sidecar binding, size, and
  independently recomputed SHA-256 all agree. Any disagreement is fatal.
- Existing unrelated files are never overwritten. Symlinks in staging are
  rejected.

The restricted output layout is:

```text
data/restricted/lvb01/raw/videos/
data/restricted/lvb01/raw/subtitles/
data/restricted/lvb01/manifests/
```

The whole `data/restricted/` tree is gitignored.

## Validation after transfer

MP4 files must start with a valid ISO-BMFF `ftyp` box. Size and SHA-256 are
always recorded. If `ffprobe` is installed, the sidecar also records format,
duration, stream codec type/name, dimensions, audio sample rate/channels, and
probe errors.

Subtitle files must decode as UTF-8 or UTF-8 with BOM and parse as JSON. A
small schema summary is recorded without creating benchmark annotations.

## Commands

Offline validation, which does not read a token, make network calls, or write
outputs:

```bash
python tools/lvb_exact_asset_downloader.py --dry-run
```

Authorized parent execution:

```bash
python tools/lvb_exact_asset_downloader.py --execute
```

Progress is printed to stderr using only allowlisted basenames and byte counts.
The command prints a final secret-free JSON summary to stdout. If execution is
interrupted, rerun the same command; valid chunk-boundary partial files resume.

## Operational notes

1. Run from the repository checkout containing the frozen plan and audited
   inputs.
2. Ensure the Hugging Face login/token is available to
   `huggingface_hub.get_token()`.
3. Ensure at least 582 MB plus filesystem overhead is available.
4. If a stale `.lvb_exact_asset_downloader.lock` remains after a hard crash,
   inspect that no downloader process is running, then remove only that lock.
5. Do not move completed files without their adjacent `.metadata.json`
   sidecars if skip verification is expected on a later run.
