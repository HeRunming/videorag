# Assembly101 access preflight v1

**Task:** 156  
**Date:** 2026-09-23  
**Decision:** `ASSEMBLY101_ACCESS_REPAIR`  
**Authority created:** none for acquisition, processing, restricted annotation, evaluation, or release

## 1. Immediate result

Assembly101 is **not ready for source acquisition**. The only fresh successful
official response completed before the stop was a HEAD response from the
official project landing page. It returned HTTP 200, `server: GitHub.com`,
`content-type: text/html; charset=utf-8`, a reported page length of 15,546
bytes, ETag `"6a0804ea-3cba"`, and Last-Modified
`Sat, 16 May 2026 05:47:22 GMT`.

Those values identify the landing page response only. They do not establish a
dataset release, a data package version, an official repository commit, a
download manifest, a storage object, or permission to use the data.

The user then ordered all network activity stopped. Network activity after
that instruction was zero. No full media, segment, thumbnail, sample, archive,
or media byte range was requested or retained.

## 2. Evidence boundary

Task 156 completed two request attempts:

1. an environment-proxy HEAD attempt that failed before HTTP because the proxy
   hostname did not resolve; and
2. an explicit-proxy HEAD request to the official project page that returned
   HTTP 200 headers and no body.

A later homepage GET command was interrupted. No successful GET response or
saved body from that command was observed. There were:

- 0 successful page-body fetches;
- 0 successful GitHub/API/tree listings;
- 0 successful download/storage listings;
- 0 paper fetches;
- 0 metadata archives or tool installations;
- 0 media requests; and
- 0 media bytes.

After the stop, a local process audit found no active Task 156 or
Assembly101-targeted network client. Unrelated work by other processes was not
altered. Finalization used only the saved HEAD evidence and retained repository
records from Tasks 149, 152, and 155.

## 3. Exact release and primary paper

The exact Assembly101 dataset release or version is **unresolved**. No release
name, tag, date, immutable manifest, package revision, or checksum was
captured.

The exact primary-paper version is also unresolved because no official paper
page or PDF was fetched before the stop. Task 156 therefore does not repeat
paper statistics as current release facts.

The earlier combined values of 4,321 videos, 513 hours, and 15 views remain
withdrawn from acquisition, duration, and storage planning. They mix units or
versions that were not reproducibly bound to one pinned official release.

## 4. License and terms

No operative Assembly101 data license, data-use agreement, package terms, or
acceptance record was archived. A project page or code-repository license
cannot be propagated to participant recordings or annotation packages.

Current use states are:

| Decision surface | Status |
|---|---|
| Research use | `UNKNOWN_HOLD` |
| Internal processing | `UNKNOWN_HOLD` |
| New restricted annotation | `UNKNOWN_HOLD` |
| Derived-output publication | `UNKNOWN_HOLD_BY_ARTIFACT_CLASS` |
| Identifier or metadata release | `UNKNOWN_HOLD` |
| Annotation release | `UNKNOWN_HOLD` |
| Raw-media release | `NOT_AUTHORIZED` |

The next rights review must map the exact package clauses separately for
acquisition, internal processing, restricted annotation, retention/deletion,
aggregate publication, identifiers, annotations, clips, frames, audio,
features, and raw media.

## 5. Official acquisition route and current credentials

The only confirmed entry point is the official project landing page:
`https://assembly-101.github.io/`.

The exact maintained download script, script revision, provider repository,
storage prefix, package names, gate form, and acceptance procedure were not
captured. Consequently the official acquisition route remains unresolved.

Task 155 recorded that a generic Hugging Face login existed on this host. It
also found zero proven exact official Assembly101 Hugging Face repository IDs
and zero successful target listings. Task 156 did not improve that result.

The correct credential finding is:

`CURRENT_HOST_CAN_LIST_ASSEMBLY101_ASSETS = NOT_PROVEN`

This is not a provider denial. The exact official provider target was not
established, so a generic platform login cannot be treated as Assembly101
asset authority.

## 6. IDs, durations, and candidate source groups

No official item-ID schema, session-ID schema, participant mapping, view
mapping, file tree, or asset manifest was listed. Exact collected counts are:

| Measure | Count |
|---|---:|
| Exact item IDs | 0 |
| Exact session IDs | 0 |
| Exact candidate source-group IDs | 0 |
| Candidate source groups with wall-clock duration | 0 |
| Candidate source groups with verified native audio | 0 |

The required 8–12 candidate source groups therefore cannot be selected.
Placeholder IDs are not created.

A later metadata-only listing must compute **wall-clock duration per coherent
assembly session**. It must not sum synchronized camera-hours and must not join
unrelated takes to meet the desired duration window. The listing should freeze
8–12 real participant/session groups plus replacements using only non-label
metadata.

## 7. Native audio and synchronization

Retained local records describe Assembly101 source videos as audio-bearing,
but Task 156 collected no fresh package metadata and verified no selected
stream. Native synchronized audio is therefore `UNKNOWN_HOLD`.

A later technical preflight must record, for every selected native video:

- audio stream presence, codec, channels, sample rate, and duration;
- video duration and time base;
- audio/video presentation alignment;
- alignment across the selected synchronized views; and
- whether the audio is native capture rather than an annotation-only or
  post-produced track.

No container parse or media range probe occurred in Task 156.

## 8. Multi-view lineage and source grouping

The official metadata schema was not verified. Until it is, use this
fail-closed grouping rule:

> One source group is one participant by one coherent assembly-session
> lineage, including every synchronized ego and static view, native audio,
> clips, encodes, poses or calibration artifacts, annotations, and all project
> derivatives.

If a participant appears in multiple sessions, keep that participant in one
split until official participant/session relationships support a stricter
grouping. Count elapsed session time once, not once per camera. Even if later
acquisition is limited to a minimum approved view set, all omitted views must
remain in the lineage ledger because they are correlated alternatives.

This is a conservative project grouping policy, not a claim that the
unfetched official schema uses these exact identifiers.

## 9. Privacy and sealed annotations

No official privacy, consent, withdrawal, retention, or participant-release
terms were archived. Controlled capture does not eliminate risks from faces,
voices, participant identity, background identity cues, repeated
participation, or multi-view reidentification.

Before acquisition, the project needs restricted storage, least-privilege
access, a minimum-file and minimum-view allowlist, a participant/session
lineage ledger, a retention/deletion plan, and component/personality-rights
review.

During metadata selection, only the following may be visible:

- release and package identity;
- non-label participant, session, item, and view identifiers;
- file names, sizes, hashes, and provider revisions;
- wall-clock duration;
- technical stream-presence fields; and
- non-label lineage and privacy flags.

The following labels and derived artifacts must remain sealed during source
selection, candidate authoring, assignment, and model-facing execution:

- fine-grained and coarse action label IDs and names;
- action-segment start/end timestamps;
- mistake, error, or correction labels;
- procedure-step, ordering, and task labels;
- verb, noun, object, or state labels if present;
- benchmark split labels, scores, and outcomes;
- label-derived clips or preselected windows;
- captions, narrations, transcripts, or ASR if present; and
- question-answer or evidence-timestamp artifacts if present.

They may be opened only in a logged, separately approved post-authoring audit.
Existing dataset annotations do not create AV-TRACE labels or validate new
project decisions.

## 10. Separate decisions

### Acquisition

`NOT_AUTHORIZED`

The release, package, route, terms, approval, asset IDs, duration distribution,
and target-specific access are unresolved.

### Processing

`NOT_AUTHORIZED`

The operative data terms and selected-file custody boundary are not archived.

### Restricted annotation

`NOT_AUTHORIZED`

No annotation clause has been established and no eligible source group is
frozen.

### Release

`NOT_AUTHORIZED`

There is no artifact-specific redistribution authority or completed privacy
review for raw media, clips, frames, audio, identifiers, annotations, or
derived outputs.

### Metadata-only repair

`SEPARATE_TASK_REQUIRED`

Task 156 is stopped. A future task may resume only official project, official
GitHub, official download/storage, and primary-paper metadata work. It should
use HEAD, API/tree listing, metadata manifests, and tiny bounded technical
probes only. Media acquisition remains a separate decision.

## 11. Repair checklist

1. Archive the official project body and follow only project-linked paper,
   GitHub, and download/storage routes.
2. Pin the exact data release/package and immutable official code or manifest
   revision.
3. Archive the operative data terms and any approval or acceptance evidence.
4. Map acquisition, processing, restricted annotation, retention, derivative
   publication, and redistribution separately.
5. Prove a target-specific credential can list the exact official asset tree
   without media transfer.
6. Capture item, session, participant, view, and file relationship fields.
7. Compute wall-clock session durations and freeze 8–12 real candidate source
   groups plus replacements.
8. Verify native synchronized audio for every selected view using metadata
   first and only separately approved tiny probes if needed.
9. Freeze participant/session lineage and keep restricted labels sealed.
10. Obtain separate written decisions before acquisition, processing,
    restricted annotation, or release.

## 12. Decision

This is `REPAIR`, not `READY`, because every acquisition-critical field beyond
the project landing-page identity is unresolved. It is not `NO_GO` because the
official project page remains reachable and retained records describe a
plausible project-maintained access path. That path has not been verified and
confers no authority.

`ASSEMBLY101_ACCESS_REPAIR`
