# Mini-pilot replacement dossier preflight

**Date:** 2026-09-23  
**Decision:** `MINI_PILOT_REPLACEMENT_DOSSIERS_READY`  
**Scope:** four replacement-source dossiers only; this is **not** Gate A GO  
**Mode:** independent offline audit of saved evidence; no network, media download, human annotation, or evaluator-key/label access

## Outcome

All four repaired replacement dossiers pass the dossier-level gate:

1. `SG-OXFORD-QM-001`
2. `SG-OXFORD-DHL-CONSCIOUSNESS`
3. `SG-MIT-RES12-003-L01`
4. `SG-YALE-PHYS200-L01`

They are four distinct underlying lecture assets across **3 collections**
(Oxford Podcasts, MIT OpenCourseWare, Open Yale Courses), **4 subject
domains**, and **3 selected media hosts**. Every exact duration is within the
frozen **1,200–5,400 second** window.

`READY` means that a separate controlled task may acquire the exact first-party
renditions into restricted storage for noncommercial processing and candidate
work. It does not authorize public release, commercial use, human-gold claims,
or execution of the human mini-pilot.

## Source decisions

| Source group | Collection / domain | Exact duration | Technical A/V | Dossier decision |
|---|---|---:|---|---|
| `SG-OXFORD-QM-001` | Oxford / quantum physics | 2,645.28 s | H.264 640×360 + AAC stereo 48 kHz | `GO_TO_BOUNDED_ACQUISITION` |
| `SG-OXFORD-DHL-CONSCIOUSNESS` | Oxford / literary studies | 2,918.76 s | H.264 640×360 + AAC stereo 44.1 kHz | `GO_TO_BOUNDED_ACQUISITION` |
| `SG-MIT-RES12-003-L01` | MIT / fluid dynamics and sediment transport | 2,859.933333 s | H.264 High 640×360 + AAC-LC stereo 48 kHz | `GO_TO_BOUNDED_ACQUISITION` |
| `SG-YALE-PHYS200-L01` | Yale / classical mechanics | 4,400.900901 s | H.264 Baseline 320×180 + AAC-LC stereo 44.1 kHz | `GO_TO_BOUNDED_ACQUISITION` |

For each source, the saved official page binds the lecture to its exact
first-party media route. Saved response headers/manifests establish final host,
object length, MIME, ETag, Last-Modified value, byte-range behavior, and range
consistency.

The A/V finding is a **technical container finding**: both tracks are declared
on co-timed presentation timelines and the MIT/Yale sparse checks show
interleaved video/audio payload locations. It is not a claim that Task 131
decoded the full lecture or established perceptual/semantic lip sync.

## Independent hash and arithmetic audit

- Rehashed **104 retained evidence files / 1,307,971 bytes** listed by the four
  dossier manifests.
- File existence, byte length, and SHA-256 mismatches: **0**.
- Aggregate digest over the sorted `path<TAB>bytes<TAB>sha256` records:
  `609d9bbd2a3d06d985c5f88067d7f1bee8f65403379334eb4cddbede7e06fdbc`.
- Per-dossier aggregate digests:
  - Oxford QM: `beb5a3c685fa943cd9214efdff12c8dd41c116effb79bb9df2c486b7c56d8d99`
  - Oxford DHL: `c656d5122cee8f7b58d1d382cb68b239fb37ed89b0083e2d3d931a962c6309eb`
  - MIT RES12: `15b936e6b98ceb9fee698a1eb5b59f82c34b9ba05ed8e92dc6758d42fc2a42d6`
  - Yale PHYS200: `74d4c4c60e28c381418d9aae0a3973cb52b5a006a9acff78ac94a879308d324e`

Duration arithmetic was independently recomputed from saved time bases and
duration ticks:

- Oxford QM: `126,973,440 / 48,000 = 2,645.28` seconds and
  `6,613,200 / 2,500 = 2,645.28` seconds.
- Oxford DHL: `128,717,316 / 44,100 = 2,918.76` seconds and
  `7,296,900 / 2,500 = 2,918.76` seconds.
- MIT: `85,798,000 / 30,000 = 2,859.933333...` seconds; audio presentation is
  2,859.870667 seconds after its edit-list offset, a 0.062667-second tail
  difference.
- Yale: `13,189,500 / 2,997 = 4,400.900900...` seconds; audio and video have
  the same presentation duration, while raw audio media duration differs by
  about 0.000324 seconds.

The original media-range bodies were intentionally deleted. Therefore Task 131
could not freshly hash those deleted payload bytes. It instead verified that
every persisted range hash and byte length agrees between the range manifests
and deletion proofs, and that all listed temporary media paths are now absent.
This is internally consistent evidence, but it must not be described as a new
byte-level rehash of the deleted payloads.

## Response-byte limits

All applicable limits pass:

| Source/task | Largest non-media response | Media-range bytes | Applicable result |
|---|---:|---:|---|
| Oxford QM / Task 128 | 31,470 | 2,097,152 | pass |
| Oxford DHL / Task 128 | 31,470 | 2,097,152 | pass |
| MIT / Task 129 | 469,635 | 7,077,888 | pass |
| Yale / Task 130 | 85,267 | 6,029,315 | pass |

The per-response non-media ceiling was 2 MiB and the per-candidate repair range
ceiling was 16 MiB. Task 128 used 6,553,144 unique response bytes against its
80 MiB task ceiling. Tasks 128–130 together transferred 20,110,829 response
bytes; this aggregate is informational because Tasks 129 and 130 had their own
separate limits. Yale's four repeated non-media bodies count as Task-130
network transfer even though their identical Task-128 copies were not retained
again.

## Temporary-buffer deletion and repository retention

- Task-128 deletion proof:
  `0340736ffce25b6db79a6f8a3d690ce58bf3191cd969e5d5345859317f0475b2`
- Task-129 deletion proof:
  `f943624cb7d7f22744e4e58f1e13d62e257f03ec502758d3931e4c17e51c4890`
- Task-130 deletion proof:
  `cd59425d95bdbe571763919ce06f3da0b6738dfc8acd380993349df62b4099c0`

Every listed temporary media response or derived concatenation is absent.
No selected full-media filename, exact-size full object, or media-payload file
was found in the replacement dossier tree or the recorded task temporary
locations. Retained media payload is **0 bytes**.

## Rights decision and overclaim boundary

The saved evidence supports a **qualified operational authorization** for all
four sources:

- exact first-party acquisition into restricted storage;
- genuinely noncommercial internal use;
- local ML processing and candidate-family mining;
- restricted human annotation;
- preservation of source, attribution, license, and object-identity metadata;
- access controls, data minimization, and component/privacy flagging.

MIT's saved terms expressly address compliant noncommercial AI/ML training.
Oxford and Yale support internal work through their item/course CC BY-NC-SA
grants and noncommercial-use terms; neither contains an annotation-specific
grant. This is a conservative project decision, not legal advice or a warranty
that every embedded component is cleared.

The following would be overclaims:

1. **“Fully rights-cleared.”** Third-party material and privacy, publicity,
   moral-right, and trademark interests may remain.
2. **“CC BY-NC-SA prohibits public release.”** The licenses can permit some
   noncommercial sharing if all conditions and underlying rights are satisfied.
   Public release is blocked here by project governance because component-level
   scope, privacy/personality, attribution/share-alike packaging, and artifact
   compatibility are not complete.
3. **“Full-file hash verified.”** No complete media object was downloaded, so
   identity is URL + length + ETag + Last-Modified + MIME + consistent ranges,
   not a whole-file SHA-256.
4. **“Decoded semantic synchronization verified.”** Only technical A/V
   presence/timing was established.

## Exact authorization

**Authorized next:** a separate task may acquire exactly the four frozen
first-party renditions into restricted project storage and use them for
noncommercial local processing, candidate mining, and restricted annotation,
subject to attribution, access control, minimization, and mandatory exclusion
flags.

**Still prohibited/not authorized:** commercial use; alternate or third-party
download routes; public release or redistribution of raw media, clips, frames,
audio, transcripts, annotations, embeddings, or derived features; public use
of uncleared third-party or identifiable-person material; human-gold claims;
and starting the scientific pilot without Gate A GO.

## Gate A

The pivot registry's Gate A remains `NOT_RUN`. This audit satisfies the
replacement-dossier prerequisite for these four groups only. Gate A still
requires restricted full acquisition and custody hashes, decoded full-source
semantic/component/privacy checks, twelve eligible family candidates plus two
excluded calibrations across exactly six source groups, frozen forms/protocol/
seed/registry, at least six trained reviewers with valid role assignments, and
no unresolved critical governance hold.

No individual dossier was modified by Task 131; no demonstrable dossier
inconsistency required correction.
