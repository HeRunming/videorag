# AV-TRACE final human-review handoff packet

**Evidence/snapshot execution date:** 2026-09-07  
**Handoff preparation date:** 2026-09-08  
**Current authority state:** `DEFAULT_DENY`  
**Gate A: closed**  
**Requests submitted / terms accepted / media acquired:** none

## 1. Purpose and audience

This packet hands the completed offline metadata, access, rights, and technical
planning work to four human owners:

- **Project lead:** decide whether each draft is still needed and whether its
  scope matches the rehearsal.
- **Institutional legal/rights reviewer:** review the live operative terms,
  source-owner authority, permitted uses, obligations, and institutional
  eligibility.
- **Data custodian:** approve an exact file allowlist, acquisition route,
  storage boundary, access controls, retention, deletion, and audit procedure.
- **Future annotation lead:** confirm that any later processing and annotation
  scope is sufficient for the planned evidence work without assuming release
  permission.

This document is an operational handoff, not legal advice and not an approval.
The machine-readable decision template is
`data/access_review/human_decision_form.json`. It is intentionally blank and
default-deny.

## 2. Authoritative five-source technical shortlist

The current final shortlist is the five LongVideoBench canonical source IDs
below. The older public-source list in
`data/rehearsal_review/shortlist.csv` remains a fail-closed substitution pool;
it is not the current five-source acquisition list.

| Rank | Candidate | Role | Canonical source ID | Verified metadata duration | Metadata basis | Current state |
|---:|---|---|---|---:|---|---|
| 1 | `ccp-008` | primary | `longvideobench:-PgbM2MhcYQ` | 2,987.08 s | LongVidSearch plus verified LongVideoBench parent row | `PRE_DOWNLOAD_TECHNICAL_CANDIDATE_NOT_APPROVED`; `unknown_hold` |
| 2 | `ccp-009` | primary | `longvideobench:-eRimFrm6kQ` | 1,540.88 s | LongVidSearch plus verified LongVideoBench parent row | `PRE_DOWNLOAD_TECHNICAL_CANDIDATE_NOT_APPROVED`; `unknown_hold` |
| 3 | `ccp-003` | primary | `longvideobench:-7wwfGJXEZg` | 1,515.20 s | LongVidSearch plus verified LongVideoBench parent row | `PRE_DOWNLOAD_TECHNICAL_CANDIDATE_NOT_APPROVED`; `unknown_hold` |
| 4 | `ccp-011` | primary | `longvideobench:H5vpBCLo74U` | 1,805.13 s | direct verified LongVideoBench-Meta rows | `PRE_DOWNLOAD_TECHNICAL_CANDIDATE_NOT_APPROVED`; `unknown_hold` |
| 5 | `ccp-012` | active reserve | `longvideobench:TMe7oXMJoSM` | 2,805.11 s | direct verified LongVideoBench-Meta rows | `PRE_DOWNLOAD_TECHNICAL_CANDIDATE_NOT_APPROVED`; `unknown_hold` |

The five canonical IDs are distinct in the current metadata pool. This does not
prove content-level source disjointness: alternate encodes, excerpts, and
re-uploads remain untested until authorized fingerprints can be compared.

## 3. Exact `LVB-01` request scope

The complete and only current `LVB-01` parent-ID scope, in order, is:

1. `-PgbM2MhcYQ` — primary;
2. `-eRimFrm6kQ` — primary;
3. `-7wwfGJXEZg` — primary;
4. `H5vpBCLo74U` — primary;
5. `TMe7oXMJoSM` — active reserve.

For each exact ID, the draft asks for:

- one **lowest-resolution complete synchronized audio-video rendition**;
- matching subtitle JSON if available;
- the matching metadata row containing split, `video_path`, `subtitle_path`,
  duration, subtitle offset, and source provenance;
- provider-reported byte size and SHA-256, if available.

The draft excludes every other video, the full multipart corpus, unrelated
subtitles, embeddings, and test answers. If item-level delivery is unavailable,
the scope must not silently expand. The correct action is
`REQUEST_CHANGES` or `REJECT`.

The scope matches:

- `data/access_review/request_scope.csv`;
- `data/access_review/approval_checklist.json`;
- `data/access_review/questions_for_maintainers.csv`;
- `docs/data/gated_access_dossier.md`; and
- the five shortlisted rows in the current candidate and gate matrices.

## 4. Other request/clarification packets

| Packet | Current purpose | Exact current scope | Present readiness |
|---|---|---|---|
| `LSHOT-01` | Metadata-only gated request | `postvalid_v2_test.jsonl` at revision `5a16213fadcbbbacd40b6feb6e5b048e5c180ddc`, 11,095,822 bytes, SHA-256 `f323f1f7244869c1220781970fb16099e885b86944a779d80499d634e6d47ad7`; README/schema/current terms only; no media | Draft complete, not submitted; human terms review required |
| `FLARE-01` | Written rights clarification only | `K759eXmaMTY`; `3uV8XZcIBbk`; `jWa2yrLGxCM`; no acquisition in this packet | Draft clarification complete, not submitted |
| `OMNI-01` | Conditional single-item request | `video_61` only; exclude byte-identical alias `video_60` and all other media | Do not send unless the project lead retains `ccp-007` after alias review |
| `EGO-01` | Blocker memo / metadata-crosswalk question only | No media IDs available; ask only for canonical Ego4D/EgoLife ID, split, evidence-interval, and release-version crosswalk | Too underspecified for a media request |

The authoritative row-by-row send posture is in
`data/access_review/final_request_ready.csv`.

The per-item 2 GiB media cap and 8 GiB retained-storage cap in the probe plan
are conservative **proposed planning ceilings**, not approved allocations.
They must be replaced or affirmatively adopted by the data custodian in the
signed exact-scope decision before any transfer.

## 5. What is verified

As of the 2026-09-07 evidence snapshot and the 2026-09-08 integration review:

- the five shortlist candidate IDs, canonical LongVideoBench parent IDs,
  rankings, and primary/reserve roles agree across the current structured
  artifacts;
- all five have exact metadata durations within the 1,200–5,400 second
  technical eligibility range;
- all five have verified metadata video paths and subtitle paths with a
  recorded `0.0` subtitle offset;
- the relevant LongVideoBench-Meta revision is
  `cdf3444602208c95f453e7683583a077ce38ddbf`;
- the relevant gated LongVideoBench release snapshot is
  `60d1c89c1919a198b73be39c2babb213b29d6a5c`;
- the three LongVidSearch-linked candidates have pinned downstream metadata and
  exact parent-row joins;
- the two direct candidates have three verified LongVideoBench metadata QA rows
  each, used only as inspection leads;
- the exact five-ID `LVB-01` scope is consistent across the access-review
  artifacts;
- the local software and metadata path fails closed: no concrete production
  transfer backend is shipped, and request drafting does not create executable
  authorization;
- no real media, subtitle payload, approval, terms acceptance, request
  submission, or authentication action was performed by this handoff task.

## 6. What remains unknown or unapproved

For every shortlisted source, the following remain unresolved:

- the live operative access terms and their exact archived hash at the time a
  human acts;
- source-owner authority and the artifact classes covered by the displayed
  dataset license;
- whether item-level delivery of the complete synchronized source is available;
- exact provider byte size, SHA-256, rendition identity, and immutable object
  locator;
- whether the object is complete, decodable, timestamp-stable, and contains
  usable original video and audio;
- actual speech, ambient/non-speech, and music content;
- subtitle contents, timing accuracy, completeness, and independence from
  generated or copied text;
- source-time mapping for LongVidSearch ordinal evidence slices and fresh
  source-time evidence for the direct candidates;
- content-level duplicate, excerpt, alternate-encode, and re-upload status;
- faces, voices, minors, private settings, precise locations, sensitive
  content, marks, copyrighted music, and other embedded components;
- permission for decoding, sampling, transcription, fingerprinting, temporary
  derivatives, annotation, retention, and every proposed release artifact;
- approved storage location, named custodians, access list, deletion deadline,
  takedown procedure, and audit checkpoint.

Metadata descriptions are not proof of modality coverage or annotation yield.
No AV-TRACE evidence graph, sufficient evidence set, necessity group, or
accepted family has been authored for these sources.

## 7. Why nothing currently authorizes a download

No current artifact authorizes transfer because:

1. every request is `DRAFT_NOT_SUBMITTED`;
2. live terms review is pending or blocked;
3. terms have not been accepted by an institutionally authorized human;
4. acquisition, processing, annotation, and release decisions are all
   `NOT_APPROVED`;
5. source-media rights remain `unknown_hold`;
6. no signed human decision form binds an exact asset/rendition allowlist;
7. no approved provider route, positive expected object size, checksum,
   destination, custodian, or retention record exists for the five media files;
8. the repository ships no concrete production transfer backend; and
9. the post-authorization probe CSV is explicitly
   `NOT_EXECUTABLE_UNTIL_APPROVED`.

Access approval, terms acceptance, acquisition, processing, annotation, and
release are separate decisions. Approval of a request draft means only that an
authorized human may send that exact draft. It does not approve any later
stage.

## 8. Required human actions

### Project lead

1. Name the institution, requester, accountable project owner, and intended
   non-commercial use/funding context.
2. Confirm the five-source shortlist and decide whether each non-LVB packet is
   still needed.
3. For `OMNI-01`, explicitly retain or drop `ccp-007`; do not send the packet
   while this is undecided.
4. Select `APPROVE_REQUEST_DRAFT`, `REQUEST_CHANGES`, or `REJECT` for each
   packet.

### Institutional legal/rights reviewer

1. Open the live official terms immediately before the decision.
2. Record the exact terms URL, retrieval timestamp, SHA-256, archived-copy
   reference, and controlling agreement/version.
3. Determine institutional eligibility, non-commercial compatibility,
   source-owner authority, permitted acquisition and processing, derivative
   restrictions, attribution/share-alike duties, deletion/takedown duties, and
   whether separate permission is required.
4. Record terms acceptance separately. Do not infer acceptance from request
   approval or account access.

### Data custodian

1. Approve or reject the exact item/rendition allowlist and official acquisition
   route.
2. Require a positive provider size and SHA-256 for each object before transfer.
3. Approve a controlled staging root, named access list, encryption/logging,
   byte caps, retained-storage caps, retention deadline, deletion evidence, and
   quarantine procedure.
4. Do not allow cookies, browser-session extraction, generic downloaders,
   unofficial mirrors, full-corpus substitution, or credentials in plans/logs.

### Privacy/safety reviewer

1. Review expected handling of identifiable faces and voices, minors,
   bystanders, private spaces, precise locations, sensitive/harmful content,
   music, marks, and third-party components.
2. Specify review, minimization, access, exclusion, and withdrawal controls.
3. Reject or hold any source whose risk cannot be assessed before the proposed
   processing.

### Future annotation lead

1. Confirm that processing permission covers complete-source review,
   transcription where applicable, source-time alignment, fingerprints, and
   temporary working derivatives.
2. Keep released benchmark QA text as a triage lead only; author new AV-TRACE
   questions and evidence independently.
3. Do not begin annotation until acquisition, processing, privacy/safety, and
   annotation decisions are separately approved and the technical probe passes.
4. Obtain a separate artifact-specific release decision before publishing any
   annotation, transcript, feature, fingerprint, output, or excerpt.

All named humans must complete a copy of
`data/access_review/human_decision_form.json`; blank identities, missing
evidence, or unsigned decisions have no effect.

## 9. Request-draft decision tree

### `APPROVE_REQUEST_DRAFT`

Choose only when the live terms evidence has been captured, the requester and
institution are eligible, the exact scope is correct, and the proposed wording
does not overstate authority.

Effect:

- an institutionally authorized human may send the exact reviewed draft;
- `LVB-01` remains limited to its five IDs;
- `LSHOT-01` remains metadata-only;
- `FLARE-01` remains clarification-only;
- `OMNI-01` remains conditional on explicit project-lead retention;
- `EGO-01` may at most become a metadata-crosswalk question, never a media
  request.

It does **not** accept terms or approve access, acquisition, processing,
annotation, or release.

### `REQUEST_CHANGES`

Choose if scope, wording, addressee, purpose, retention, requested artifact
class, institutional status, or legal assumptions require correction. Record
every required change and keep all later decisions `NOT_APPROVED`. Re-review
the revised exact text and live terms before sending.

### `REJECT`

Choose if the request is unnecessary, overbroad, institutionally ineligible,
legally incompatible, unsafe, technically incapable of item-level delivery, or
cannot be made precise. Do not submit it. Close or replace the candidate through
the documented substitution process; no fallback inherits approval.

Any maintainer response, gate grant, or accessible URL returns the workflow to
human review. It does not automatically advance acquisition or processing.

## 10. Exact stop conditions

### Stop before sending a request

- required named human identity, role, institution, authority, timestamp, or
  signature/reference is blank;
- the live terms URL, archived snapshot, or SHA-256 is missing;
- the requested scope differs from the exact packet scope;
- `LVB-01` would include any non-shortlisted item or full multipart archive;
- `LSHOT-01` would include media or media-acquisition tooling;
- `FLARE-01` would be treated as an acquisition request;
- `OMNI-01` is considered without resolving the `video_60`/`video_61` alias and
  retaining `ccp-007`;
- `EGO-01` is converted into a broad Ego4D/EgoLife media request without exact
  UIDs;
- the human decision is `NOT_DECIDED`, `REQUEST_CHANGES`, or `REJECT`.

### Stop before transfer

- terms acceptance, when required, is not affirmatively recorded by an
  authorized human;
- acquisition decision is not `APPROVED`;
- any applicable right remains `unknown_hold`;
- source-owner, no-derivatives, privacy, music, component, or takedown scope is
  unresolved;
- exact file/rendition, official route, immutable revision, expected byte size,
  SHA-256, destination, custodian, retention, or deletion controls are absent;
- the provider object exceeds the approved item or total byte cap;
- the route requires scraping, cookies, private browser state, an unofficial
  mirror, a generic media downloader, or an unreviewed backend;
- item-level delivery is unavailable and the only alternative is a broader
  corpus.

### Stop during post-authorization probe

- size or SHA-256 mismatch;
- duration is below 1,200 seconds or above 5,400 seconds;
- missing video, missing/empty audio, corruption, incomplete source, unstable
  timestamps, severe A/V drift, or an unscannable region;
- subtitle/transcript identity or timing cannot be validated;
- source-time joins remain unresolved;
- duplicate, excerpt, or re-upload status defeats source disjointness;
- privacy/safety or embedded-component review fails;
- the intended modality or temporal slot has no defensible yield.

Use the exact reason codes in
`data/rehearsal_plan/post_authorization_probe_plan.csv` and
`docs/pilot/rehearsal_acceptance_criteria.md`.

### Stop before annotation or release

- processing or annotation decision is not `APPROVED`;
- the technical, audio, source-time, dedup, or privacy gate has not passed;
- a complete-source blind alternative search cannot be performed;
- annotation would copy upstream benchmark answers instead of independently
  authoring evidence;
- release decision for the exact artifact class is not `APPROVED`;
- release would include restricted media, subtitles, transcript-like text,
  recognizable audio features, credentials, or provider-only metadata.

## 11. Files to use next

- Human decision record:
  `data/access_review/human_decision_form.json`
- Packet-by-packet send posture:
  `data/access_review/final_request_ready.csv`
- Technical work plan after all required approvals:
  `data/rehearsal_plan/post_authorization_probe_plan.csv`
- Source dossier and detailed maintainer questions:
  `docs/data/gated_access_dossier.md` and
  `data/access_review/questions_for_maintainers.csv`

**Final handoff state:** human review may begin. No request may be sent, no
terms may be accepted, and no media may be acquired on the authority of this
packet alone.
