# Independent decision on the rehearsal shortlist

**Decision date:** 2026-09-08  
**Scope:** metadata-only review of proposed rehearsal sources  
**Authority effect:** none — no access, acquisition, processing, annotation, or release approval

## Operative Task 50 decision

The strict pre-download technical shortlist is expanded from three to **five**
source-ID-disjoint LongVideoBench canonical IDs. Task 50 allows direct source
selection from the verified LongVideoBench-Meta rows because AV-TRACE will
create new questions and evidence graphs; an upstream TraceAV or LongVidSearch
annotation is not required.

| Rank | Candidate | Role | Canonical source | Duration | Split | Topic / QA category |
|---:|---|---|---|---:|---|---|
| 1 | `ccp-008` | primary | `longvideobench:-PgbM2MhcYQ` | 2,987.08 s | test | `NP-News-Programs`; `E3E` ×3 |
| 2 | `ccp-009` | primary | `longvideobench:-eRimFrm6kQ` | 1,540.88 s | validation | `KG-Knowledge-Geography`; `O3O` ×3 |
| 3 | `ccp-003` | primary | `longvideobench:-7wwfGJXEZg` | 1,515.20 s | test | `KH-Knowledge-History`; `E3E` ×3 |
| 4 | `ccp-011` | primary | `longvideobench:H5vpBCLo74U` | 1,805.13 s | test | `KC-Knowledge-Computer-Science`; `T2E` ×3 |
| 5 | `ccp-012` | active reserve | `longvideobench:TMe7oXMJoSM` | 2,805.11 s | validation | `KA-Knowledge-Art`; `TAA` ×3 |

All five remain `PRE_DOWNLOAD_TECHNICAL_CANDIDATE_NOT_APPROVED`, with candidate
approval `PROVISIONAL_NOT_APPROVED` and source-media rights `unknown_hold`.

## Basis for the two additions

- `ccp-011` occupies test rows 2976–2978. Its three released QA prompts align
  subtitle phrases with changes on instructional slides. This makes it a
  plausible speech/cross-modal inspection lead only.
- `ccp-012` occupies validation rows 602–604. Its three prompts describe
  performance/scene changes and two mention singing or lyrics. This makes it a
  plausible ambient/visual-temporal inspection lead only.
- Both have verified relative video paths, subtitle metadata paths, 0.0 subtitle
  offsets, exact in-range durations, and topics/categories not represented by
  the earlier three.
- No exact canonical-ID, path, duration, or exact-question collision was found.
  Content/re-upload dedup remains unresolved.

The complete ranking method, row-level facts, and hash/schema verification are
recorded in `docs/review/direct_lvb_candidate_expansion.md`.

## Coverage is still hypothesis-only

| Requirement | Current evidence | Decision boundary |
|---|---|---|
| Vision | Released QA descriptions refer to visual states and changes. | Media decode and human evidence review required. |
| Speech | `ccp-011` metadata repeatedly references subtitle phrases. | Speech stream/content and subtitle independence unverified. |
| Ambient/non-speech | `ccp-012` metadata mentions singing/lyrics and performance changes. | Original audio and a necessary non-speech event unverified. |
| Cross-modal | QA wording links text/audio-related cues to screen states. | Must prove every unimodal shortcut fails; not established by metadata. |
| Temporal/hops | Categories and multiple QA rows provide inspection variety. | No source timestamps or AV-TRACE evidence graph have been authored. |
| Alternative SES | None identified. | Requires authorized full-source search and leave-one-out validation. |

## Access scope

`LVB-01` is now limited to the final strict shortlist only:

1. `-PgbM2MhcYQ` — primary;
2. `-eRimFrm6kQ` — primary;
3. `-7wwfGJXEZg` — primary;
4. `H5vpBCLo74U` — primary;
5. `TMe7oXMJoSM` — active reserve.

The request remains `DRAFT_NOT_SUBMITTED`. The prior six-ID scope containing
non-shortlisted `-WnyRMZqV1U`, `20lTg3yUrO4`, and `-hgJVx12Qk4` is superseded.
No full archive or non-shortlisted LongVideoBench item belongs in the packet.

## Required gates before any transfer or use

1. Human/legal review of the live LongVideoBench gate and operative terms.
2. Confirmation of item-level delivery and a complete synchronized rendition.
3. Exact provider size/hash allowlist for only the five scoped IDs.
4. Separate acquisition and processing approvals.
5. Post-authorization container/stream, duration, subtitle, completeness,
   privacy/component, and duplicate/re-upload checks.
6. Human verification of speech, ambient sound, and any proposed cross-modal or
   temporal necessity.
7. Separate annotation and release approvals before either activity.

## Stop and substitution rule

Use the four primaries for the initial technical sequence and keep `ccp-012` as
the active reserve. Substitute or reduce the pilot if any primary fails rights,
completeness, stream, duration, dedup, or authoring-yield checks. Do not convert
metadata wording into modality coverage, and do not add another asset to the
request without a new documented shortlist decision.

## Historical reconciliation

Task 48 established the original three-row exact-duration shortlist. Task 49
found no qualifying TraceAV-derived addition. Those findings remain valid but
are superseded as the final-size decision by Task 50's direct LongVideoBench
selection. Earlier four-primary/five-planning-queue text is historical only and
must not be used as an acquisition list.

## Final gate calls

| Decision | Result | Basis |
|---|---|---|
| Strict shortlist size | **5** | Three existing candidates plus two direct LongVideoBench additions satisfying all metadata hard requirements. |
| Candidate freeze | **NO-GO** | Complete-source, streams, source-time evidence, modality necessity, rights, and content dedup remain unresolved. |
| Download/acquisition | **NO-GO** | `LVB-01` is draft only; no transfer approval exists. |
| Processing | **NO-GO** | No decode, sampling, transcription, fingerprinting, or transformation approval exists. |
| Annotation | **NO-GO** | No candidate is annotation-approved and no AV-TRACE evidence graph has been created. |
| Release | **NO-GO** | No artifact-specific release review exists. |
| Human review of narrowed request | **GO** | Review may proceed for the exact five-ID draft scope only. |

**Bottom line:** the technical shortlist reaches five source-ID-disjoint
LongVideoBench candidates, but all remain provisional metadata leads. No media,
subtitle payload, approval, or authorization was created.
