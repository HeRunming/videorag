# Human boundary status

**Status date:** 2026-09-08  
**Evidence snapshot date:** 2026-09-07  
**Overall state:** `DEFAULT_DENY`  
**Gate A:** closed

## Current machine-completed state

The offline system has completed the work that does not require human
authority:

- imported and hash-bound local metadata snapshots;
- converted candidates only through signed, role-checked, time-bounded,
  snapshot-bound reviewer decisions;
- inspected and deterministically selected local candidates;
- ingested verified parent-row metadata;
- fixed the final shortlist to four primaries and one active reserve;
- narrowed `LVB-01` to exactly those five parent IDs;
- prepared a blank default-deny human decision form; and
- prepared a non-executable post-authorization probe plan.

The final shortlist is:

```text
ccp-008 -> -PgbM2MhcYQ -> 2987.08 s -> primary
ccp-009 -> -eRimFrm6kQ -> 1540.88 s -> primary
ccp-003 -> -7wwfGJXEZg -> 1515.20 s -> primary
ccp-011 -> H5vpBCLo74U -> 1805.13 s -> primary
ccp-012 -> TMe7oXMJoSM -> 2805.11 s -> active reserve
```

Each remains `PROVISIONAL_NOT_APPROVED`, has source-media rights
`unknown_hold`, has unverified streams/modalities, and is not
acquisition-approved.

## Safe to automate further

Automation may continue only for non-authorizing, local metadata operations:

1. parse and validate local JSON, JSONL, CSV, and metadata-only Parquet;
2. recompute hashes, sizes, row counts, and immutable revision bindings;
3. verify importer self-hashes and reviewed-decision signatures;
4. enforce reviewer registry role and UTC validity windows;
5. reject raw-importer selection bypass;
6. reproduce deterministic candidate inspection and selection;
7. compare the five-ID shortlist and `LVB-01` scope across artifacts;
8. validate that proposed plans contain no credentials and stay within a
   human-approved allowlist and caps; and
9. generate reports or blank templates that explicitly have no authority
   effect.

These actions must stay offline and must not fetch terms, authenticate, submit
forms, download source files, decode media, or create annotations from source
media.

## Named human action now required

### Project lead

- Provide legal name, role, institution, department, institutional email, and
  authority reference.
- Confirm that the exact five-source `LVB-01` scope is still required.
- Decide `APPROVE_REQUEST_DRAFT`, `REQUEST_CHANGES`, or `REJECT`.
- Decide separately whether the non-LVB packets remain necessary.

### Institutional legal/rights reviewer

- Open and archive the live official LongVideoBench gate and operative terms.
- Record URL, title/version, retrieval time, SHA-256, archived-copy reference,
  account/gate context, and reviewer identity.
- Determine institutional eligibility, source-owner/sublicensing authority,
  non-commercial compatibility, permitted acquisition and processing,
  derivative restrictions, attribution/share-alike, deletion/takedown, and
  potential annotation/release scope.
- Accept terms only through a separate affirmative decision by a person with
  institutional authority.

### Data custodian/security reviewer

- Approve or reject the exact item and rendition allowlist.
- Confirm an official item-level route; a full-corpus substitution is not
  permitted.
- Require positive expected byte size and SHA-256 for every object before
  transfer.
- Name the custodian, controlled staging root, access list, byte/storage caps,
  retention deadline, deletion evidence, quarantine process, and audit
  checkpoint.

### Privacy/safety reviewer

- Set controls for faces, voices, minors, bystanders, private spaces, precise
  locations, sensitive content, music, marks, and third-party components.
- Record exclusions, minimization, access controls, and withdrawal/takedown
  handling.

### Annotation lead

- Confirm whether any later approved processing scope is sufficient for
  complete-source inspection, source-time alignment, transcription,
  fingerprinting, and temporary derivatives.
- Preserve upstream QA text as a triage lead only and require independent
  AV-TRACE authoring.
- Approve annotation only after rights, acquisition, processing,
  privacy/safety, and technical probes pass.

All required humans must be named in a completed copy of
`data/access_review/human_decision_form.json`. Blank fields, missing live-terms
evidence, false attestations, scope mismatch, or a missing signature/reference
leave the decision ineffective.

## Separate decision gates

| Stage | Current state | What could change it |
|---|---|---|
| Request submission | `NOT_APPROVED` | A named authorized human approves the exact reviewed draft after live-terms review. |
| Terms acceptance | `NOT_ACCEPTED` | A separately authorized human affirmatively accepts the exact archived terms. |
| Media acquisition | `NOT_APPROVED` | Legal/rights review plus a signed exact allowlist, official route, hashes/sizes, custodian, storage, retention, and audit controls. |
| Processing/probing | `NOT_APPROVED` | Separate approval defining permitted decoding, sampling, transcription, fingerprinting, and derivative handling. |
| Annotation | `NOT_APPROVED` | Separate approval after successful technical, modality, source-time, dedup, rights, and privacy gates. |
| Release | `NOT_APPROVED` | Separate artifact-specific approval defining exactly what may be published and under what obligations. |

Approval at one stage does not approve a later stage. In particular,
`APPROVE_REQUEST_DRAFT` authorizes only an authorized human to send that exact
draft. A maintainer response, account access, or accessible URL does not
authorize acquisition or processing.

## Probe-plan boundary

`data/rehearsal_plan/post_authorization_probe_plan.csv` is a plan only. Every
row is `NOT_EXECUTABLE_UNTIL_APPROVED`. It has route placeholders rather than
URLs or credentials and requires expected size/hash before transfer.

Even after acquisition approval, execution requires the separately authorized
processing boundary and must stop on rights holds, route/allowlist gaps,
size/hash mismatches, incomplete or corrupt media, absent usable streams,
invalid subtitles, unresolved source-time joins, duplicate/re-upload findings,
privacy/component failure, or lack of intended annotation yield.

The repository currently ships no concrete production byte-transfer backend.
The validation CLI uses `backend=None`; therefore it cannot perform a source
media transfer.

## Final answer

- **Safe to automate further:** local parsing, integrity checks, signature and
  binding verification, deterministic selection, consistency checks, and
  default-deny document generation.
- **Requires named human action:** live terms capture and review, legal/rights
  determinations, request-submission decision, terms acceptance, exact
  acquisition allowlist and custody approval, privacy/safety review, and
  separate processing, annotation, and release decisions.
- **Request submission authorized:** no.
- **Terms acceptance authorized:** no.
- **Media acquisition authorized:** no.
- **Annotation authorized:** no.
- **Release authorized:** no.

