### EPIC audiovisual access preflight v1

**Task:** 157  
**Date:** 2026-09-24  
**Decision token:** `EPIC_AV_ACCESS_REPAIR`  
**Network status:** stopped at the user's instruction; no network request was
started after that instruction.  
**Media transferred:** 0 files, 0 bytes.

### Decision

EPIC-KITCHENS-100 plus EPIC-SOUNDS remains a technically promising restricted
research source, but it is not ready for acquisition, processing, restricted
annotation, or release.

The retained evidence pins EPIC-KITCHENS-100 to the `2020-100` release family
and records 700 videos, 100 hours, and 45 kitchens. It does not pin an
immutable annotation snapshot or the exact EPIC-SOUNDS release/revision.
EPIC-SOUNDS is recorded as 78,366 categorized and 39,187 uncategorized sound
events, 117,553 total. No official source listing, exact video/session IDs,
per-video duration table, selected-file stream metadata, accepted media
agreement, or usable downloader was established in Task 157.

The annotation repository's CC BY-NC 4.0 notice is evidence for the covered
annotation artifacts only. It is not treated as a license for participant
video or native audio. Operative raw-media terms remain unarchived.

### Evidence boundary

Task 157 began with bounded official-source probes only. The first proxy
request failed before HTTP because the proxy hostname could not be resolved.
An escalated retry was later aborted by the user; no successful response,
headers, body, listing, or media bytes were observed. The user then ordered
all network activity stopped and immediate finalization.

All findings below therefore come from:

- Tasks 149, 152, and 155;
- the official-source-derived local inventory dated 2026-09-05;
- earlier local rights and preflight reviews that point to the official EPIC
  project and official EPIC GitHub organization; and
- local environment checks that read no secret values.

No current-web freshness claim is made. The empty
`project_2026.headers.txt` file records that the failed request produced no
HTTP headers.

### Release and artifact separation

| Artifact class | Exact release or revision established | Terms evidence | Task 157 disposition |
|---|---|---|---|
| EPIC-KITCHENS participant video/audio | `EPIC-KITCHENS-100`, project route `2020-100`; package revision not pinned | Raw-media terms or agreement not archived | `UNKNOWN_HOLD` |
| EPIC-KITCHENS-100 annotations | Repository identity recorded locally; immutable commit not pinned | CC BY-NC 4.0 recorded for the annotation repository | Covered annotation reuse only after exact file/revision and attribution scope are archived |
| EPIC-SOUNDS annotations | Dataset identity and aggregate event counts recorded; exact release/revision not pinned | No separate exact license snapshot archived in Task 157 | `UNKNOWN_HOLD` pending artifact-level license capture |
| Downloader/scripts | Official downloader route recorded by prior official-source audit | No local script, package, revision, or credentials found | `NOT_READY` |
| New AV-TRACE records derived from media | No release | Depends on media terms, privacy review, and record class | `NOT_AUTHORIZED` |

The annotation notice cannot be propagated to raw media, extracted clips,
audio, frames, transcripts, embeddings, or newly authored records without an
artifact-specific review.

### Access and registration state

The strongest retained official-route description is: accept the official
EPIC terms and use the official downloader. Task 157 could not refresh the
portal or capture the current registration form, account workflow, agreement
text, package menu, or downloader documentation.

Local readiness is negative:

- no accepted EPIC media-terms record was found;
- no registered-account evidence was found;
- no EPIC credential environment variable was present;
- no downloader executable under the checked EPIC names was installed;
- no Python distribution with `epic` or `kitchen` in its package name was
  found;
- no local official EPIC repository/package was found; and
- no authenticated listing or media access was demonstrated.

The prior statement that the official portal and download tools were active
was observed on 2026-09-05. It is historical evidence, not a September 24
live check.

### Source IDs and duration distribution

No exact source video ID, session ID, participant ID, or kitchen ID was
enumerated in Task 157. Exact candidate count is therefore 0.

The only duration evidence retained at dataset level is:

- 700 videos;
- 100 total hours; and
- arithmetic mean `100 × 60 / 700 = 8.57` minutes per video.

The mean does not establish the distribution. Minimum, maximum, median,
quantiles, and counts in the 20–90 minute target interval are unavailable.
The local qualitative note that many recordings are tens of minutes cannot
replace an official duration table.

An 8–12 source-group metadata candidate pool could not be identified without
an official nonsemantic listing. Inventing participant, kitchen, video, or
session IDs would violate the source-freeze contract. The registry therefore
defines a 10-group future listing target but contains no fabricated
candidates.

### Native audio and EPIC-SOUNDS linkage

Dataset-level evidence supports the existence of source audio:

- the retained inventory describes native audio in EPIC-KITCHENS videos; and
- EPIC-SOUNDS provides timestamped non-speech event annotations aligned to
  EPIC-KITCHENS-100 source recordings.

This is not file-level stream verification. No official media manifest row,
container probe, codec, channel count, sample rate, duration agreement, or
audio/video synchronization field was captured for any selected file.

The EPIC-SOUNDS relationship is treated as a derivative annotation linkage to
the same underlying EPIC-KITCHENS-100 recording lineage. Exact join keys,
schema version, split coverage, event-to-video completeness, and revision
compatibility were not validated. All EPIC-SOUNDS rows inherit the source
group and split of the linked EPIC recording.

### Source-group definition

The conservative source group is the participant/kitchen lineage, not an
individual action clip or sound event:

`EPIC participant × kitchen lineage`

The group contains every available recording/session from that lineage and
all derivatives:

- source video and native audio;
- transcoded or clipped media;
- frame and audio extracts;
- narrations;
- action, verb, noun, and object labels;
- EPIC-SOUNDS categorized and uncategorized events;
- timestamps and temporal boundaries;
- features, embeddings, indexes, questions, and authored records; and
- any later corrections or alternate releases that map to the same lineage.

If official metadata shows that one participant recorded in multiple kitchens
or that multiple identifiers refer to the same household, the broader linked
lineage controls. No derivative from a group may cross development,
validation, and test partitions.

EPIC-KITCHENS and HD-EPIC require a cross-dataset participant/kitchen overlap
audit before either dataset contributes separate groups.

### Privacy restrictions

The source material can expose:

- participant identity through hands, voice, clothing, reflections, and
  routines;
- private homes and kitchens;
- household possessions and location/context clues;
- incidental speech and third-party voices;
- possible bystanders or household members;
- daily routines, dietary practices, and safety-sensitive activity; and
- stable cross-recording identity cues that enable re-identification.

Until exact media terms and institutional privacy controls are approved:

- raw media stays in a restricted location;
- no public clips, frames, audio, waveforms, transcripts, thumbnails, or
  reversible features are released;
- no face, voice, household, or identity inference is added;
- no attempt is made to identify participants or locations;
- access is least-privilege and logged; and
- withdrawal, deletion, retention, and incident procedures remain unresolved
  gates rather than assumed permissions.

### Leakage controls for selection and authoring

EPIC is critical leakage risk because narrations, action intervals, and sound
event classes directly reveal candidate events and timestamps. The following
two-zone design is the operative control:

**Selection-safe zone**

- release identifier;
- opaque participant, kitchen, video, and session identifiers;
- duration and nonsemantic temporal coverage;
- file/container size and checksum;
- video/audio stream-presence flags;
- capture and rights status;
- privacy flags that do not expose semantic content; and
- source-group and overlap keys.

**Restricted annotation vault**

- narration text and timestamps;
- action, verb, noun, object, recipe, and benchmark labels;
- EPIC-SOUNDS category names, free text, onset/offset, confidence, and event
  identifiers;
- transcripts, captions, search indexes, label-derived features, and
  annotation-derived summaries; and
- benchmark outcomes or prior question/evidence records.

Controls:

1. A data custodian creates the selection-safe manifest and strips semantic
   columns before selectors see it.
2. Candidate filtering uses rights, duration, stream presence, capture,
   privacy, overlap, and source-group fields only.
3. Selection uses a precommitted hash over release plus opaque source-group
   ID after eligibility filtering.
4. Selectors and initial authors have no vault access. Search over narration,
   action, object, or sound labels is disabled.
5. Initial authoring, if separately authorized, uses only the selected raw
   audiovisual recording and a blank protocol packet.
6. Filenames, paths, thumbnails, cached metadata, logs, and model prompts are
   checked so they do not reveal label names or annotated timestamps.
7. Existing labels may be joined only after source selection and initial
   authoring are frozen, by a different logged role, for contamination and
   coverage audit.
8. Any author exposure to sealed labels is recorded and makes that source
   ineligible for untouched evaluation.
9. All derivatives inherit the participant/kitchen group and exposure status.
10. Existing EPIC annotations do not establish AV-TRACE scientific tiers or
    support claims.

### Future metadata-only candidate pool protocol

The next permitted network phase, only after renewed authorization, should
request an official listing without media payload and produce exactly 10
provisional groups where possible:

1. pin EPIC-KITCHENS-100 package/version, annotation commit, EPIC-SOUNDS
   version, downloader revision, and all operative terms;
2. obtain opaque participant, kitchen, video/session IDs, durations, file
   sizes, checksums, and stream-presence metadata only;
3. exclude groups outside the approved duration interval, lacking declared
   audio, with unresolved terms, or overlapping HD-EPIC;
4. avoid narration/action/audio-event files during filtering;
5. rank eligible groups by
   `SHA256("AVTRACE-EPIC-V1|" + release + "|" + source_group_id)`;
6. retain the lowest 10 hashes as the provisional pool and the next two as
   replacements, without opening semantic annotations; and
7. mark every listed or inspected group as development-touched.

This protocol is specified but not executed.

### Separate decisions

| Decision surface | Status | Basis |
|---|---|---|
| Metadata listing | `REPAIR` | Official listing and immutable revisions were not obtained; future bounded metadata-only work can close the gap. |
| Media acquisition | `NOT_AUTHORIZED` | No accepted current media terms, account route, exact allowlist, or working official downloader. |
| Media processing | `NOT_AUTHORIZED` | No acquired authorized files and no artifact-specific processing decision. |
| Restricted annotation | `NOT_AUTHORIZED` | No media-processing approval, privacy controls, source pool, or sealed authoring packet. |
| Scientific execution | `NOT_AUTHORIZED` | No frozen source groups or authorized records. |
| Derived-record release | `NOT_AUTHORIZED` | Media-dependent terms and privacy review are unresolved. |
| Raw-media release | `NOT_AUTHORIZED` | No affirmative redistribution authority is archived. |

### Repair closure conditions

A ready status can be considered only after all of the following are recorded:

- current official registration and access workflow;
- accepted media agreement evidence for the responsible user/institution;
- exact raw video/audio package terms;
- exact annotation terms for both EPIC-KITCHENS-100 and EPIC-SOUNDS;
- immutable release/repository/downloader revisions;
- working metadata-only official listing;
- exact participant/kitchen/video/session IDs and duration distribution;
- metadata-level audio stream declarations for selected files;
- validated EPIC-SOUNDS join keys and version compatibility;
- 8–12 nonsemantic source-group candidates, with overlap and privacy checks;
- approved restricted storage, retention, deletion, and incident controls;
- implemented annotation-vault separation and exposure logging; and
- written decisions issued separately for acquisition, processing,
  restricted annotation, and each release class.

Current token: `EPIC_AV_ACCESS_REPAIR`.
