# Final independent audit: mini-pilot replacement dossiers

**Audit date:** 2026-09-23  
**Final decision:** `MINI_PILOT_REPLACEMENT_DOSSIERS_READY`  
**Audit mode:** offline, saved evidence only

## 1. Scope and independence

This audit independently reviewed:

- the Oxford Quantum Mechanics and D.H. Lawrence dossiers;
- the repaired MIT RES.12-003 dossier from Task 129;
- the repaired Yale PHYS 200 dossier from Task 130;
- all four embedded evidence manifests;
- the Task-128 saved-response audit;
- all Task-128/129/130 media-buffer deletion proofs;
- Task-128 status and preflight review;
- the pivot Gate A definition; and
- the human mini-pilot source-pool plan.

Task 131 used no network, downloaded no media, accessed no controller/evaluator
key or restricted label, and performed no annotation. It did not modify any
individual dossier.

## 2. Decision

All four dossiers pass the replacement-dossier gate:

`MINI_PILOT_REPLACEMENT_DOSSIERS_READY`

This is narrower than `MINI_PILOT_INPUT_READY`. Gate A remains `NOT_RUN`
because acquisition, complete-source screening, candidate-family preparation,
staffing, forms, seed, and other Gate A prerequisites are not completed by this
audit.

## 3. Per-source technical findings

### 3.1 Oxford Quantum Mechanics

- Source group: `SG-OXFORD-QM-001`
- Exact route:
  `https://media.podcasts.ox.ac.uk/physics/quantum_mechanics/binney01.mp4`
- Object: 302,443,579 bytes; `video/mp4`;
  ETag `"1206ec3b-4a1e2de791280"`; Last-Modified
  `Wed, 27 Apr 2011 09:14:34 GMT`.
- Ranges: two 1 MiB HTTP 206 responses, total 2,097,152 bytes.
- Duration arithmetic:
  - audio: `126,973,440 × 1/48,000 = 2,645.28 s`;
  - video: `6,613,200 × 1/2,500 = 2,645.28 s`.
- Streams: AAC stereo 48 kHz and H.264 640×360.
- Result: exact duration, A+V presence, range behavior, route, and object
  identity pass.

### 3.2 Oxford D.H. Lawrence

- Source group: `SG-OXFORD-DHL-CONSCIOUSNESS`
- Exact route:
  `https://media.podcasts.ox.ac.uk/engfac/dhlawrence/2012-01-18-01-great-writers-brown-lawrence.mp4`
- Object: 369,848,995 bytes; `video/mp4`;
  ETag `"160b72a3-4b7ea09a6cfc0"`; Last-Modified
  `Wed, 01 Feb 2012 17:01:59 GMT`.
- Ranges: two 1 MiB HTTP 206 responses, total 2,097,152 bytes.
- Duration arithmetic:
  - audio: `128,717,316 × 1/44,100 = 2,918.76 s`;
  - video: `7,296,900 × 1/2,500 = 2,918.76 s`.
- Streams: AAC stereo 44.1 kHz and H.264 640×360.
- Result: exact duration, A+V presence, range behavior, route, and object
  identity pass.

### 3.3 MIT RES.12-003 Lecture 1

- Source group: `SG-MIT-RES12-003-L01`
- Exact route:
  `https://ocw.mit.edu/courses/res-12-003-fluid-motions-sediment-transport-and-current-generated-sedimentary-structures-fall-2025/mitres_12-003f25_lec1_1080p_360p_16_9.mp4`
- Object: 84,051,067 bytes; `video/mp4`;
  ETag `"4606f46b3ea0b3327994bf9989b1840c-11"`; Last-Modified
  `Wed, 03 Jun 2026 21:11:01 GMT`.
- HEAD: HTTP 200, zero body. Six media reads: HTTP 206 with consistent URL,
  length, ETag, Last-Modified, MIME, and `Content-Range`.
- Ranges: 7,077,888 bytes total, independently summed from the six records.
- Duration arithmetic:
  - video: `85,798,000 × 1/30,000 = 2,859.933333... s`;
  - audio presentation: `137,273,792 × 1/48,000 =
    2,859.870667 s`.
- Streams: H.264 High 640×360 at 30 fps; AAC-LC stereo 48 kHz.
- A/V: common presentation start, 0.062667-second end delta, and both indexed
  stream payloads present in all three sparse ranges.
- Caption/transcript: exact official WebVTT and PDF routes are retained.
- Result: exact duration, A+V presence, range behavior, route, and object
  identity pass.

### 3.4 Yale PHYS 200 Lecture 1

- Source group: `SG-YALE-PHYS200-L01`
- Exact selected route:
  `https://openmedia.yale.edu/projects/courses/fall06/phys200/iphone/phys200_01_090606.m4v`
- Object: 377,169,329 bytes; `video/mp4`;
  ETag `"167b27c7-5cafc2b972763;377169329"`; Last-Modified
  `Thu, 02 Sep 2021 05:08:15 GMT`.
- Eight bounded media responses, all HTTP 206. The selected M4V identity is
  consistent across its probe, head, sparse, and tail responses.
- Ranges: 6,029,315 bytes total, including one-byte M4V/MP3/MOV identity
  probes, a 4 MiB M4V head, three 256 KiB sparse ranges, and a 1 MiB tail.
- Duration arithmetic:
  `13,189,500 × 1/2,997 = 4,400.900900... s`.
- Streams: H.264 Baseline 320×180 at 29.97 fps and AAC-LC stereo 44.1 kHz.
- A/V: equal edit-list presentation durations; raw media tail difference
  about 0.000324 seconds; both tracks have chunk starts in every sampled
  middle/tail region.
- Result: exact duration, A+V presence, range behavior, route, and object
  identity pass.

## 4. Duration and diversity gate

| Requirement | Recomputed result | Decision |
|---|---|---|
| Four distinct source groups | 4 | pass |
| At least three collections | Oxford, MIT, Yale = 3 | pass |
| At least three subject domains | quantum physics, literary studies, fluid dynamics/sediment transport, classical mechanics = 4 | pass |
| At least three selected media hosts | Oxford media, MIT OCW, Yale Open Media = 3 | pass |
| Duration 1,200–5,400 seconds | 2,645.28; 2,918.76; 2,859.933333; 4,400.900901 | pass |
| Exact first-party route | present for all four | pass |
| Synchronized technical A+V | present for all four | pass |

Distinctness is established at the dossier level by canonical lecture
identity, official route, collection, title, duration, and object metadata.
Full-content cryptographic/perceptual duplicate screening remains a
post-acquisition Gate A activity because complete media is intentionally not
present.

## 5. Hash audit

Task 131 recomputed SHA-256 and byte length for every retained file listed by
the four dossier manifests:

| Dossier | Files | Bytes | Mismatches | Aggregate manifest digest |
|---|---:|---:|---:|---|
| Oxford QM | 15 | 88,623 | 0 | `beb5a3c685fa943cd9214efdff12c8dd41c116effb79bb9df2c486b7c56d8d99` |
| Oxford DHL | 13 | 88,442 | 0 | `c656d5122cee8f7b58d1d382cb68b239fb37ed89b0083e2d3d931a962c6309eb` |
| MIT RES12 | 52 | 884,290 | 0 | `15b936e6b98ceb9fee698a1eb5b59f82c34b9ba05ed8e92dc6758d42fc2a42d6` |
| Yale PHYS200 | 24 | 246,616 | 0 | `74d4c4c60e28c381418d9aae0a3973cb52b5a006a9acff78ac94a879308d324e` |
| **Total** | **104** | **1,307,971** | **0** | `609d9bbd2a3d06d985c5f88067d7f1bee8f65403379334eb4cddbede7e06fdbc` |

The Task-128 response audit also retains its expected SHA-256:
`f15535be32d656da6f1e0d96d07c816fa52ad4f211d571acd38ee48f1e032b7d`.

### Deleted-payload limitation

The original range bodies were deleted as required. Their payload hashes
cannot be freshly recomputed from absent bytes. The audit instead:

1. rehashed every retained manifest/deletion-proof file;
2. matched each recorded range length to its inclusive `Content-Range`;
3. matched each range hash and length between the range manifest and deletion
   proof; and
4. verified all listed temporary media paths are absent.

This supports integrity and cleanup consistency, but it is not equivalent to
retaining and independently rehashing the original range payloads. No report
should claim otherwise.

## 6. Response accounting

### Per-source results

| Source | Non-media bytes in applicable task | Largest non-media response | Media-range bytes | Result |
|---|---:|---:|---:|---|
| Oxford QM | 82,226 | 31,470 | 2,097,152 | pass |
| Oxford DHL | 82,130 | 31,470 | 2,097,152 | pass |
| MIT Task 129 | 255,345 | 469,635 | 7,077,888 | pass |
| Yale Task 130 | 195,137 | 85,267 | 6,029,315 | pass |

- Non-media limit: 2,097,152 bytes per response.
- Task-129/130 media-range limit: 16,777,216 bytes per repaired candidate.
- Task-128 total unique response limit: 83,886,080 bytes.
- Task-128 actual: 6,553,144 bytes.
- Task-129 new actual: 7,333,233 bytes.
- Task-130 new actual: 6,224,452 bytes.
- Informational Tasks-128–130 aggregate: 20,110,829 bytes.

No applicable limit was exceeded. The Yale accounting correctly counts the
four non-media requests again as Task-130 transfer while avoiding duplicate
repository bodies because their hashes matched Task 128.

## 7. Deletion and no-full-media finding

The three deletion-proof files rehash correctly:

- Task 128:
  `0340736ffce25b6db79a6f8a3d690ce58bf3191cd969e5d5345859317f0475b2`
- Task 129:
  `f943624cb7d7f22744e4e58f1e13d62e257f03ec502758d3931e4c17e51c4890`
- Task 130:
  `cd59425d95bdbe571763919ce06f3da0b6738dfc8acd380993349df62b4099c0`

All recorded range-body and derived-concatenation paths are absent. No selected
full-media filename or exact-size complete object was found in the repository
or recorded task temporary locations. No media-payload file remains under the
replacement dossier tree. Retained media payload: **0 bytes**.

The retained MIT `chunk_offsets.json` and parser/build scripts in `/tmp` are
metadata/code, not media payload.

## 8. Rights analysis

### Oxford

Each selected episode page applies CC BY-NC-SA 2.0 UK to the episode and
publishes exact video/audio/transcript download routes. The Oxford general
copyright page distinguishes CC-licensed episodes from default personal-use
material. For these specifically licensed episodes, restricted copying,
noncommercial analysis/adaptation, and internal annotation are supportable
with attribution and noncommercial controls.

This is not complete component clearance. Quantum-mechanics slides/figures,
lecturer/audience likeness and voice, and D.H. Lawrence quotations/images
remain release-screening issues.

### MIT

The exact item/course carries CC BY-NC-SA 4.0. The saved MIT terms expressly
permit compliant noncommercial AI/ML training, development, and improvement,
while preserving attribution, share-alike, trademark, privacy, publicity, and
moral-right limits. Restricted acquisition, local processing, candidate
mining, and internal annotation are well supported for the stated
noncommercial purpose.

No item-specific Credits inventory was found. Slides, diagrams, marks,
lecturer/audience likeness and voice, and other components still block a
blanket public-release decision.

### Yale

The lecture page repeats Yale's statement that most lectures/course materials
are CC BY-NC-SA 3.0. Yale's terms permit noncommercial use but expressly
exclude third-party content unless covered by the applicable Credits section.
No Lecture-1-specific Credits inventory is present.

Restricted acquisition, local processing, and restricted annotation are a
defensible operational decision because Yale officially supplies the lecture
and the project will use it noncommercially under access controls while
flagging/excluding potentially affected content. This is the least categorical
of the four rights findings: it is not an affirmative clearance of unknown
third-party components or student/lecturer personality and privacy interests.
Those uncertainties remain release blockers.

### Correct interpretation

The four dossiers support **internal noncommercial use**, but only as a
qualified, source-specific project authorization. They do not establish that
all components are owned by the institutional publisher.

Public release is blocked by this project pending separate review. It would be
an overclaim to say that CC BY-NC-SA categorically forbids public release; the
licenses can allow some noncommercial sharing when attribution, share-alike,
component ownership, privacy/personality, and other requirements are met.

## 9. Exact authorization and prohibitions

### Authorized

A separately controlled task may:

1. acquire exactly one frozen first-party rendition for each of the four
   source groups;
2. store it only in restricted project storage;
3. perform genuinely noncommercial local ML processing and candidate-family
   mining;
4. permit restricted human annotation under access controls;
5. retain attribution, license/version, route, object-identity, custody, and
   deletion metadata; and
6. flag, exclude, quarantine, or separately clear third-party and
   privacy-sensitive intervals.

### Prohibited or not yet authorized

- commercial or profit-directed use;
- YouTube, Vimeo, Internet Archive, mirror, guessed, or non-frozen acquisition
  routes;
- public redistribution/release of raw media, clips, frames, audio,
  transcripts, annotations, embeddings, or derived features;
- release of identifiable student/audience material, third-party figures,
  readings, images, marks, music, or literary quotations without separate
  clearance;
- external-service upload not separately approved by the custody plan;
- human-gold, H1, H2, benchmark-readiness, or public-release claims; and
- human mini-pilot execution before Gate A GO.

## 10. Gate A and source-pool reconciliation

The source-pool plan defines `GO_TO_BOUNDED_ACQUISITION` as a precursor to
restricted acquisition, decoded semantic A/V review, family authoring, and
human validation. The pivot Gate A additionally requires six total source
groups, twelve eligible family candidates, two excluded calibration families,
complete media and lineage records, frozen forms/protocol/seed/registry, six
trained reviewers with valid role assignment, and no critical governance hold.

Accordingly:

- the **four replacement dossiers are READY**;
- the four sources may fill the four new non-NOAA source-group positions
  subject to later full-source checks;
- the two existing development sources and all remaining Gate A inputs must
  still be separately verified; and
- Gate A itself remains `NOT_RUN`, not GO.

## 11. Dossier-change log

No individual dossier was changed. The audit found no demonstrable internal
inconsistency requiring correction. The principal cautions are interpretation
boundaries, not dossier data errors:

- deleted range payloads cannot be freshly rehashed;
- object identity is not a complete-file SHA-256;
- A/V synchronization is technical, not semantic;
- internal noncommercial authority is qualified, not blanket rights
  clearance; and
- public release remains a project hold rather than a statement that the CC
  licenses inherently prohibit every form of public sharing.
