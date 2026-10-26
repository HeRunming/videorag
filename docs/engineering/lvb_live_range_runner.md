# LongVideoBench live bounded Range preflight runner

## Purpose and boundary

`tools/lvb_live_range_preflight.py` performs an authenticated, header-only preflight for the five approved LongVideoBench identifiers. It indexes exact MP4 and subtitle JSON tar members without downloading a target MP4 payload, a complete multipart part, or the complete subtitle archive.

The runner is pinned to:

- repository: `longvideobench/LongVideoBench`
- revision: `60d1c89c1919a198b73be39c2babb213b29d6a5c`
- target IDs: `-PgbM2MhcYQ`, `-eRimFrm6kQ`, `-7wwfGJXEZg`, `H5vpBCLo74U`, `TMe7oXMJoSM`

It has no target-media download flag. Finding a member records offsets and future HTTP ranges only.

## Prerequisites

1. Run from the repository checkout (the script derives the root from its own path).
2. `httpx` and `huggingface_hub` must be installed.
3. `huggingface_hub.get_token()` must return the locally stored credential; do not put a token on the command line.
4. The logged-in account must have passed the `longvideobench/LongVideoBench` gate.
5. Configure a proxy only through standard environment variables if required, for example:

```bash
export http_proxy=https://proxy.example.invalid:3128
export https_proxy=https://proxy.example.invalid:3128
```

or:

```bash
export http_proxy=https://proxy.example.invalid:3128
export https_proxy=https://proxy.example.invalid:3128
```

The runner uses `httpx` with `trust_env=True`; it does not hard-code or report proxy URLs.

## Commands

Validate pinned local inputs without reading credentials, accessing the network, or writing outputs:

```bash
python tools/lvb_live_range_preflight.py --dry-run
```

Execute the live bounded preflight:

```bash
python tools/lvb_live_range_preflight.py --execute
```

Progress is written to stderr every 1,000 parsed tar headers by default. Change
the interval with `--progress-every N`, or disable it with
`--progress-every 0`. Progress contains only the archive label, header count,
logical offset, cumulative response-body bytes, and target count.

Relevant offline tests:

```bash
pytest -q tests/test_lvb_live_range_preflight.py
```

## Live operation

The execute mode:

1. Loads the official pinned repository evidence and validates `lvb_tar_parts.csv` against it.
2. Reads the local token using `huggingface_hub.get_token()`.
3. Sends `HEAD` and `Range: bytes=0-511` for `videos.tar.part.aa` and `subtitles.tar`.
4. Reuses one persistent `httpx.Client`, including its proxy configuration and
   connection pools, for all requests.
5. After a validated redirect, caches the full signed effective URL only in
   process memory per pinned repository object and reuses it for later HEAD or
   Range requests. A `400`, `401`, or `403` from a cached route discards it and
   performs exactly one fresh canonical resolution.
6. Treats all 31 `videos.tar.part.*` objects as one logical byte stream using the pinned sizes.
7. Reads one 512-byte tar header at a time and jumps over ordinary payloads using declared sizes.
8. Reads only bodies required for GNU long name/link and PAX local/global metadata records.
9. Validates each nonzero tar header checksum and handles USTAR prefix/name, GNU `L`/`K`, PAX `x`/`g`, regular types, and two-block end-of-archive markers.
10. Scans through a validated end marker even after locating all five targets,
    so a later duplicate target basename still fails closed. Matching is never
    substring/suffix based and full stored paths are reported.
11. Computes exact global payload intervals and inclusive per-object HTTP ranges.
12. Stages all result files and atomically replaces them only after both scans finish coherently. The manifest is replaced last.

`tar_end_global_offset` and `tar_end_offset` in CSV output are exclusive payload endpoints. HTTP ranges are inclusive.

## Safety behavior

The runner aborts on:

- a non-HTTPS request or redirect;
- a redirect outside the allowlisted Hugging Face delivery host families;
- too many redirects;
- a Range request answered with `200`;
- any status other than expected `200` for HEAD or `206` for Range;
- missing, malformed, or mismatched `Content-Range`;
- missing or unexpected `Content-Length`;
- non-identity Range content encoding;
- a truncated or excess response body;
- a response body over 8 MiB;
- aggregate response-body bytes over 256 MiB;
- any request outside pinned object sizes or a full-object Range;
- an invalid tar checksum, malformed GNU/PAX structure, duplicate target, or target name on a non-regular member.

Redirect query strings are not persisted. Signed effective URLs never leave
process memory. The bearer token is sent only while following the canonical
`huggingface.co` same-origin resolution chain; it is never sent to an
effective/CDN host, including `us.aws.cdn.hf.co`. Reports include hostnames but
no headers, cookies, credentials, signed URL queries, or proxy details.
Unexpected transport exceptions are reduced to exception-class error codes
before reporting.

## Outputs

A coherent execute run updates:

- `data/acquisition_preflight/lvb_tar_parts.csv`
- `data/acquisition_preflight/lvb_five_member_ranges.csv`
- `data/acquisition_preflight/lvb_subtitle_ranges.csv`
- `data/acquisition_preflight/lvb_range_probe_manifest.json`
- `docs/review/lvb_tar_range_preflight.md`

Dry-run never modifies these files, so it cannot overwrite a successful live manifest.

## Interpreting completion

- `GO_HEADER_INDEX_COMPLETE`: all five MP4 and all five subtitle members were found from checksum-valid headers. This approves no payload acquisition; it only establishes exact bounded ranges.
- `NO_GO_TARGETS_NOT_FOUND`: a coherent scan reached an end marker but one or more exact names were absent. The result files preserve that live finding.
- Safety/configuration/transport abort: exit status 2; existing result files are not replaced.

Full-corpus acquisition remains prohibited. Actual target media payload acquisition, processing, annotation, and release require separate later-stage decisions.
