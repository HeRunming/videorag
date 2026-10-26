# LVB-01 authorized request-draft review guide

**Packet:** `LVB-01`  
**Request decision:** `APPROVE_REQUEST_DRAFT`  
**External submission:** `NOT_SUBMITTED_BY_SYSTEM`  
**Next action:** authorized user may submit through the official gated page

## Authorization now on record

The user explicitly stated in the current conversation:

> 不用这么麻烦,我有权限授权这些,直接按你建议的权限范围来做就行

That instruction authorizes only the final request draft in
`docs/pilot/lvb01_final_request_text.md`. The authorization record is
`data/access_review/lvb01_user_authorization.json`.

The exact ordered scope is:

1. `-PgbM2MhcYQ`
2. `-eRimFrm6kQ`
3. `-7wwfGJXEZg`
4. `H5vpBCLo74U`
5. `TMe7oXMJoSM`

The purpose is a non-commercial internal AV-TRACE rehearsal. The request is
limited to minimum item-level access, excludes the full corpus and multipart
archives, and promises no redistribution.

## Current official gate evidence

The current official Hugging Face dataset API evidence supplied on
2026-09-08 is archived at:

`data/access_review/evidence/lvb_LongVideoBench_api_2026-09-08_rev-60d1c89c1919a198b73be39c2babb213b29d6a5c.json`

- dataset: `longvideobench/LongVideoBench`
- revision: `60d1c89c1919a198b73be39c2babb213b29d6a5c`
- gate: `auto`
- license field: `cc-by-nc-sa-4.0`
- bytes: `10561`
- SHA-256:
  `747c167c73908d018134c08869ac74d3e15f100af7cf40a2b8d962d598f6147d`

The gate states that LongVideoBench does not own or create the linked videos,
rights remain with source/channel owners, content may be changed or deleted,
use is non-commercial only, and access acknowledges CC-BY-NC-SA 4.0.

## What is authorized

- Use the exact final request text.
- Ask for only the five IDs.
- Ask for the lowest-resolution complete synchronized rendition plus matching
  subtitle and metadata for each item.
- Ask for item-level delivery or authorization rather than full archives.
- Ask whether internal decoding, sampling, transcription, feature extraction,
  fingerprinting, temporary technical derivatives, and newly authored
  non-media annotations are permitted.
- Ask for expected file sizes, SHA-256 hashes, and immutable identifiers where
  possible.
- Submit only through the official gated page, by the authorized user.

## What remains prohibited or unapproved

The system did not and must not:

- sign in to Hugging Face;
- tick official checkboxes;
- accept external terms;
- submit the external request;
- download or acquire media;
- decode, sample, transcribe, fingerprint, or otherwise process media;
- annotate media; or
- release any artifact.

The following statuses remain:

```text
exact_asset_scope = NOT_APPROVED
terms_acceptance = NOT_APPROVED
acquisition = NOT_APPROVED
processing = NOT_APPROVED
annotation = NOT_APPROVED
release = NOT_APPROVED
external_submission = NOT_SUBMITTED_BY_SYSTEM
```

An access grant does not change those statuses.

## Identity boundary

No full legal name, institution, email, or handwritten signature was supplied,
and none has been fabricated. If the official page requires identity or
account details, the authorized user must supply them directly.

## Submission

Follow `docs/pilot/lvb01_submission_instructions.md`. Before submitting, the
authorized user must personally read the live official gate and decide whether
to tick its checkboxes. Request-draft authorization is not terms acceptance.
