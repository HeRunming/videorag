# Release snapshot importer review

Date: 2026-09-07

## Decision

The metadata snapshot importer is accepted as an offline reconnaissance
component. It is intentionally outside the acquisition authorization path and
does not modify candidate/rehearsal CSVs, research conclusions, rights
decisions, the download backend, or normative schemas.

## Implemented boundary

- Inputs are existing local regular files only.
- Accepted formats are JSON, JSONL, CSV, and metadata-only Parquet when
  PyArrow is already installed.
- Each source file retains exact SHA-256 and byte size.
- Repository, file, and blob revisions are distinct.
- Promotion rejects missing, mutable, short, or unsupported revisions.
- Source file size is capped before and after reading.
- Media, archive, embedding, and model payload extensions/signatures are
  rejected.
- Likely embedded binary/media values in tabular fields fail closed.
- License statements remain evidence and never become rights decisions.
- Media/audio/speech/ambient-audio and unresolved identities remain unknown.
- Output is versioned reconnaissance JSON with source/lineage joins and an
  explicit `acquisition_authorization: none`.
- The selection CLI explicitly rejects this raw artifact class, including a
  raw artifact with an injected `candidates` key. A human-reviewed conversion
  to complete `NormalizedCandidate` records is required before selection.

## Local schemas covered

- Hugging Face dataset API responses, including repository inventory and card
  metadata;
- GitHub commit and recursive tree API responses;
- LongVideoBench-Meta rows;
- Video-MME metadata rows;
- LongVidSearch QA JSON;
- TraceAV mapping/task JSONL;
- FLARE demo query/caption JSONL;
- LongShOT annotation JSONL if captured later;
- conservative generic JSON/JSONL/CSV/Parquet metadata rows.

## Security and non-goals

There is no HTTP library, URL opener, media decoder, download implementation,
manifest drafting, or gate transition in the importer or its CLI. URLs inside
metadata are preserved as strings only. URL-shaped input arguments are
rejected. Symbolic-link inputs are rejected to keep local file selection
explicit.

The output does not state that media exists merely because a schema, task, or
caption declares a modality. It also does not assert that a FLARE object is the
same rendition as a Video-MME object; that relationship is recorded as
unresolved unless stronger identity evidence is supplied.

## Verification

`tests_data/test_snapshot_importer.py` covers:

- exact source hashes and sizes;
- revision-scope preservation;
- real captured HF and GitHub API snapshots;
- source-lineage joins;
- malformed schemas;
- oversized inputs;
- rejected media payloads and embedded media signatures;
- unknown modality preservation;
- duplicate IDs;
- optional PyArrow Parquet ingestion;
- a socket-blocked import run;
- CLI output being inspection-only.

The complete `tests_data` suite is the release gate for this change.
