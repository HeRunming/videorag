# Audio-gap recovery plan for the AV-TRACE MVP

**Plan date:** 2026-09-09  
**Target:** obtain **3–5 genuinely audio-bearing long-video assets** without
conflating transcript proxies with audio  
**Mode used for this plan:** existing repository evidence only; no browsing and
no media download

## 1. Recovery target and acceptance rule

The MVP should not count an asset as audio-bearing until an authorized exact
rendition passes all of the following:

1. duration is 1,200–5,400 seconds;
2. the complete source video decodes and has at least one decodable audio
   stream;
3. audio is non-empty and synchronized sufficiently for source-time evidence;
4. at least one intended role is directly verified:
   intelligible speech, identifiable non-speech/ambient events, or both;
5. the item has two or more useful, temporally separated evidence regions;
6. exact identity, provenance, duplicate status, and the authorized route are
   frozen;
7. internal processing is approved for the exact rendition;
8. annotation and release remain separately gated;
9. generated captions, dataset task labels, or a corpus-level paper statement
   are not treated as a substitute for probing the selected file.

Recommended minimum composition for the first 3–5:

- at least **one speech-bearing `V+S`** source;
- at least **one ambient/non-speech `V+A`** source;
- at least **one plausible `V+S+A`** source;
- at least two source families if governance permits;
- no more than two sources from one production family in the headline cohort.

Here `S` means speech information obtained from an actual audio stream or a
validated derivative of that stream. A supplied subtitle can assist retrieval,
but it does not prove `S` availability and is not `A`.

## 2. What the local inventory currently establishes

No alternative exact MP4 is already proven audio-bearing by the local
repository evidence. FLARE supplies package/object and derived-WAV evidence;
OmniVideoBench supplies gated MP4 listings plus a corpus-level audio claim;
EgoLife/Ego4D supply dataset-level audiovisual descriptions. Every selected
file still requires an authorized item-level stream probe.

| Release/source | Local evidence about media and audio | Current implication |
|---|---|---|
| LongVideoBench, exact LVB-01 rendition | Five MP4s are present and verified; all have zero audio streams. | Useful for `V+subtitle-proxy`; cannot fill any audio slot. |
| FLARE demo / Video-MME | Exact candidates `ccp-005` and `ccp-006` have released package metadata listing a full MP4 plus derived scenes; `ccp-004` has a derived scene WAV. Streams and exact source durations remain unverified. | Strong item-selective reconnaissance route; not yet proof of an audio-bearing long MP4. |
| OmniVideoBench via TraceAV | Gated MP4 objects are exposed; corpus-level evidence says the source videos have audio tracks. TraceAV supplies explicit speech, environmental-sound, and cross-modal task rows. | Strongest existing benchmark route for audio-task alignment, but each file, duration, license scope, and duplicate status must be checked. |
| TraceAV-Bench | Releases annotations and mappings, not source media. | Useful for selecting items and evidence patterns only. |
| Video-MME | Source IDs/URLs and audio/subtitle evaluation are documented, but the local candidate rows do not establish an authorized full-source download or file streams. | Do not use direct platform downloading without a separately authorized route. |
| LongShOTBench | Audio-oriented tasks are represented, but the inspected release hosts no raw media. | Annotation/selection aid only unless an authorized source route is established. |
| EgoLife / Ego4D | Centrally hosted controlled media are described as audiovisual; EgoLife includes environmental audio and transcripts, and Ego4D documents AAC in canonical encodings. Exact candidate files remain unverified. | Technically promising, but privacy, agreement, and source-ID blockers make this a later route. |
| TRACE / VES-Bench | A video package is documented, but audio presence and the media-license basis are unverified locally. | Do not prioritize ahead of routes with better audio evidence. |
| NASA, NOAA, NARA, Wikimedia Commons, direct grants | Existing project inventory identifies long, potentially redistributable assets with expected speech and/or ambient audio. Every item remains an item-level rights and technical hold. | Preferred foundation for a public-core or rights-clean supplemental cohort. |

## 3. Ranked acquisition routes

### Rank 1 — item-level clearance of public/institutional candidates

**Recommended priority:** **P0 — primary MVP recovery route**

**Exact current candidates**

1. `cand-061` — *Grace Hopper - Future Possibilities - Data, Hardware,
   Software, and People*; Wikimedia Commons/federal archival provenance;
   5,375 seconds metadata duration.
2. `cand-023` — *The World Avoided: Successful Stratospheric Ozone
   Protection*; NASA SVS; 2,243 seconds.
3. `cand-048` — *Shipwrecks and Sanctuaries*; NOAA Ocean Today; 3,000 seconds.
4. Reserve `cand-056` — *Blockchain solutionism* lecture; Wikimedia Commons;
   3,067 seconds.
5. Reserve `cand-051` — *Trash Talk*; NOAA Ocean Today; 3,720 seconds.

**Expected role**

- `cand-061`: speech-heavy `V+S`, transcript/routing control, room or recording
  noise only as a secondary possibility.
- `cand-023`: `V+S` and possible `V+S+A` through narration, visualization, and
  non-speech program audio.
- `cand-048`: `V+S` with a targeted search for field, underwater, or expedition
  audio that could support `V+A` or `V+S+A`.
- `cand-056`: speech/slide `V+S` reserve with a documented direct file route.
- `cand-051`: lower-sensitivity environmental reserve; ambient utility must be
  confirmed rather than inferred from topic.

**Access, licensing, and redistribution caveats**

- Every row remains `unknown_hold`.
- General NASA/NOAA policy or a Commons file page is evidence, not blanket
  asset/component clearance.
- Freeze exact page/file revision, author/source chain, credit line, license or
  federal-work basis, and all music/slide/archive/partner components.
- Confirm acquisition, local processing, transcript/ASR, annotation,
  derivative, and raw redistribution decisions separately.
- For Commons, validate against license laundering and automate required
  attribution/share-alike notices.

**Item-level selectivity:** excellent. The project already has exact candidate
IDs, durations, roles, review packets, and reserves.

**Expected engineering effort:** medium. Official file resolution, immutable
metadata capture, bounded acquisition, stream probing, ASR/subtitle alignment,
and indexing are required.

**Scientific risk:** medium. The pool is speech-heavy, and purported ambient
content may be narration-correlated or unnecessary. The three-source set must
pass silent-video, transcript-only, ambient-only, and visual-only shortcut
checks before modality claims.

**Recommended action:** in the parent network environment, revalidate these
five exact records and attempt to clear/select three. Prefer
`cand-061 + cand-023 + cand-048` if all pass; substitute `cand-056` or
`cand-051` only for a failed role, not merely for easier access.

### Rank 2 — rights-controllable directly granted or self-recorded AV

**Recommended priority:** **P0 reserve — use to guarantee missing modality
coverage**

**Exact source:** a new, versioned `AV-TRACE-Controlled-AV-01` supplemental set
recorded by the project or delivered under a written creator/institution grant.
Create one to two complete 20–45 minute recordings, not synthetic remixes.

Suggested recordings:

- `controlled-av-01`: narrated demonstration with recurring off-screen
  machine/tool sounds and visually similar distractor phases;
- `controlled-av-02`: indoor/outdoor procedure with temporally separated
  speech instructions, visual state changes, and natural ambient events.

**Expected role:** deliberately cover one `V+A` and one `V+S+A` source while
retaining natural recorded audio. A speech-only `V+S` source is optional if
Rank 1 fails.

**Access, licensing, and redistribution caveats**

- Obtain written participant, location, music, object/brand, and bystander
  releases as applicable.
- Use no uncleared background music, screens, broadcasts, artwork, or private
  conversations.
- The grant/consent must cover acquisition, ML processing, transcription,
  annotation, derivatives, worldwide redistribution, and takedown handling.
- Privacy review remains mandatory even for project-created media.

**Item-level selectivity:** maximal; content and recording design are under
project control.

**Expected engineering effort:** medium-high. Recording, release forms,
quality control, long-take synchronization, backup, captioning, and
documentation are required.

**Scientific risk:** medium-high if over-scripted. Such assets can look staged,
have artificial distractors, or favor the benchmark designers. Limit them to
one or two of the 3–5 assets, label the source class, and report results
separately from natural external media.

**Recommended action:** prepare this route in parallel. It is scientifically
preferable to synthetic audio and may be preferable to ambiguous web media for
the public core, but it should complement rather than replace naturalistic
sources.

### Rank 3 — FLARE demo / Video-MME exact items

**Recommended priority:** **P1 — high-value external compatibility route**

**Exact candidates**

- `ccp-005` / Video-MME `K759eXmaMTY`: FLARE demo metadata lists a full MP4
  and scenes 067–069; generated captions describe speech/narration and
  music/tones.
- `ccp-006` / Video-MME `3uV8XZcIBbk`: FLARE demo metadata lists a full MP4
  and scenes 040–042; generated captions describe speech/narration and
  music/tones.
- `ccp-004` / Video-MME `jWa2yrLGxCM`: FLARE metadata exposes a derived scene
  WAV; a complete long source and exact duration remain unresolved.

**Expected role:** audio-only retrieval, speech, ambient/music, `V+A`, and
hard-bimodal `V+S+A` compatibility. The first two are preferred because local
metadata identifies complete MP4 package objects; the third is a reserve until
the full-source counterpart is established.

**Access, licensing, and redistribution caveats**

- `FLARE-01` is a written-rights clarification packet only and is not
  acquisition permission.
- Reconcile FLARE's displayed CC BY 4.0 with Video-MME academic/source-owner,
  prior-approval, and modification restrictions.
- Establish which exact MP4, clip, WAV, caption, query, and metadata classes
  are covered.
- A source URL is not an authorized acquisition route, and direct
  source-platform extraction is prohibited unless expressly authorized.
- Treat resulting media as external compatibility, not public-core media,
  unless item-level rights support more.

**Item-level selectivity:** high. Three exact IDs and package relationships are
already recorded.

**Expected engineering effort:** medium. Resolve object inventory and duration,
then acquire at most two complete sources and one reserve; join scene ordinals
to source seconds and probe streams.

**Scientific risk:** medium. Generated captions can leak target semantics and
must not serve as proof of audio content or as gold evidence. Upstream
benchmark contamination and Video-MME source heterogeneity require separate
reporting.

**Recommended action:** send the already drafted `FLARE-01` clarification
after human review. If answers are favorable, freeze exact full-MP4 objects for
`ccp-005` and `ccp-006`, verify exact durations and audio streams, and acquire
one or two for an unpooled compatibility cohort.

### Rank 4 — TraceAV-selected OmniVideoBench MP4s

**Recommended priority:** **P2 — strong modality fit, heavier gate**

**Exact candidates from the local TraceAV join audit**

- OmniVideoBench `video_284`, mapped from TraceAV `video109`: represented in
  environmental-sound, speech-context, and cross-modal task rows, with a
  released evidence span up to 12 minutes.
- OmniVideoBench `video_617`, mapped from TraceAV `video163`: represented in
  environmental-sound and speech-context rows, with a released evidence span
  up to 16 minutes.
- OmniVideoBench `video_611`, mapped from TraceAV `video157`: represented in
  environmental-sound and cross-modal rows, with a released evidence span up
  to 14 minutes.

Use only one or two after exact-duration and duplicate screening. These IDs
are better aligned to the current audio gap than the existing conditional
`OMNI-01` item `video_61`, whose `video_60`/`video_61` package alias remains a
known blocker.

**Expected role:** verified speech, environmental sound, `V+A`, and
cross-modal `V+S+A` compatibility if the selected files substantiate the task
labels.

**Access, licensing, and redistribution caveats**

- OmniVideoBench is gated; TraceAV's annotation license does not license the
  MP4s.
- Resolve the live gate, per-video media scope, source-owner restrictions,
  no-derivatives implications, internal transformations, and annotation
  release.
- Corpus-level statements about audio tracks do not verify an individual
  object.

**Item-level selectivity:** high after parent reconnaissance; local mappings
and task rows provide a narrow exact-ID set.

**Expected engineering effort:** medium-high. A new item-level packet is
needed, followed by metadata/object reconnaissance, duration filtering,
duplicate checks, exact acquisition, and source-time joins.

**Scientific risk:** low-to-medium for task alignment, high for governance and
contamination. Existing TraceAV questions should be selection aids or
compatibility labels, not copied into new headline episodes.

**Recommended action:** parent reconnaissance should first check exact
duration, object availability, stream metadata if exposed, aliasing, and
rights for these three IDs. Draft a new packet only for the one or two best
survivors; do not broaden `OMNI-01` silently.

### Rank 5 — alternate synchronized LongVideoBench rendition or authorized
source-owner delivery

**Recommended priority:** **P2 — salvage route, not assumed available**

**Exact candidates:** the five current LVB-01 IDs represented by `ccp-003`,
`ccp-008`, `ccp-009`, `ccp-011`, and `ccp-012`.

**Expected role:** preserve the exact video/subtitle timeline while adding raw
speech and possible ambient sound, potentially enabling `V+S`, `V+A`, and
`V+S+A`.

**Access, licensing, and redistribution caveats**

- Ask LongVideoBench maintainers whether audio was intentionally stripped and
  whether an official complete synchronized rendition exists for these exact
  items.
- Prefer maintainer-provided or source-owner-provided exact files with
  authorization, checksums, duration, and timeline identity.
- Do not scrape or download from the apparent source platform merely because
  the identifier resembles a public video ID.
- A different platform rendition may have edits, ads, silence insertion,
  changed duration, or rights terms and therefore may not be equivalent to the
  audited MP4/subtitle timeline.

**Item-level selectivity:** excellent; exact identities and expected durations
already exist.

**Expected engineering effort:** low if maintainers provide synchronized
alternates; high if source-owner authorization and timeline reconciliation are
required.

**Scientific risk:** medium-high. Reacquired audio may not synchronize with
the processed video and may introduce source-selection bias. If equivalence
cannot be proven, treat it as a new asset rather than an audio restoration of
LVB-01.

**Recommended action:** send a narrow maintainer question before any platform
work. Stop if no authorized synchronized rendition is available.

### Rank 6 — Ego4D/EgoLife through an exact V-RAGBench crosswalk

**Recommended priority:** **P3 — later controlled research route**

**Exact source:** V-RAGBench metadata crosswalk to selected Ego4D `video_uid`
or EgoLife canonical paths. Exact asset IDs do not yet exist locally, so this
route cannot currently name a safe media allowlist.

**Expected role:** naturalistic speech, environmental audio, `V+A`, `V+S+A`,
and long-horizon retrieval.

**Access, licensing, and redistribution caveats**

- `EGO-01` is correctly blocked at metadata-crosswalk-only.
- Resolve V-RAGBench source allocation, EgoLife's observed MIT-versus-S-Lab
  conflict, the Ego4D agreement, participant/privacy obligations, and
  source-specific retention.
- Raw redistribution is unlikely to be appropriate for the public core.

**Item-level selectivity:** currently poor; exact upstream IDs and evidence
intervals are absent.

**Expected engineering effort:** very high.

**Scientific risk:** high governance and privacy risk despite excellent
scientific content.

**Recommended action:** request only the versioned metadata crosswalk. Do not
request or acquire media until exact IDs and source-specific review exist.

### Rank 7 — synthetic audio

**Recommended priority:** **engineering-only; never headline benchmark data**

**Exact source:** existing synthetic MVP fixtures or new clearly labeled test
signals attached to synthetic/controlled test videos.

**Expected role:** deterministic tests of audio indexing APIs, channel masking,
restoration state transitions, budget accounting, corruption handling, and
validator plumbing.

**Access, licensing, and redistribution caveats:** use project-created signals
or assets with explicit rights. Do not combine synthetic audio with a
third-party video unless the video and derivative combination are authorized.

**Item-level selectivity:** maximal.

**Expected engineering effort:** low.

**Scientific risk:** critical if presented as empirical audiovisual evidence.
Synthetic tones, TTS, or scripted effects do not establish natural speech,
ambient retrieval, audiovisual necessity, or recovery in real media.

**Recommended action:** retain for unit/integration testing only. Exclude from
headline denominators, modality-yield claims, and the 3–5 real
audio-bearing-asset target.

## 4. Recommended portfolio

The preferred recovery sequence is:

1. clear and probe the five **Rank 1** public/institutional candidates;
2. in parallel, prepare up to two **Rank 2** controlled recordings as a
   guaranteed rights-clean reserve;
3. pursue **Rank 3** FLARE/Video-MME for one or two external compatibility
   assets;
4. use **Rank 4** OmniVideoBench only if FLARE fails or a particularly strong
   environmental/cross-modal item clears;
5. attempt **Rank 5** only through maintainer/source-owner authorized delivery;
6. defer **Rank 6** until the crosswalk and governance burden are resolved.

An acceptable first cohort would be:

- two or three naturally occurring, item-cleared public/institutional assets;
- zero or one controlled/self-recorded ambient-rich asset;
- zero or one FLARE/Omni compatibility asset;
- total 3–5, with all files independently probed.

If no natural source supports defensible ambient necessity, report an ambient
shortfall. Do not force the quota with synthetic sound or generated captions.

## 5. Parent-network reconnaissance required

No network work was performed for this plan. A parent/network-enabled task must
collect only metadata and rights evidence first.

### Public/institutional route

- revalidate exact landing/file pages for `cand-061`, `cand-023`, `cand-048`,
  `cand-056`, and `cand-051`;
- capture immutable revision/page IDs, exact file identity, duration, size,
  provider checksum if available, MIME/container, and official download route;
- archive the exact license/federal-work/rights statement and source/credit
  chain;
- enumerate music, slides, archival inserts, partner footage, logos, speakers,
  audience, and privacy concerns;
- obtain explicit decisions for acquisition, processing, transcript/ASR,
  annotation, derivatives, raw redistribution, attribution, and takedown.

### FLARE/Video-MME route

- confirm the current pinned release and exact full-MP4 object identity for
  `K759eXmaMTY` and `3uV8XZcIBbk`;
- determine whether a complete source counterpart exists for
  `jWa2yrLGxCM`;
- obtain exact duration, size/hash, scene-to-source timing, subtitle presence,
  and any exposed stream metadata;
- obtain written answers to `FLARE-Q01` through `FLARE-Q03`;
- identify whether separate Video-MME or source-owner approval is required.

### OmniVideoBench route

- query only `video_284`, `video_617`, and `video_611`;
- verify exact duration, object size/hash, row metadata, audio declaration,
  subtitle/transcript availability, and duplicate aliases;
- confirm the live gate and artifact-class license for MP4s, metadata,
  transformations, and new timestamp annotations;
- rank one or two survivors without changing the existing `OMNI-01` scope.

### LongVideoBench alternate-rendition route

- ask whether audio was stripped in the released processed MP4s;
- ask whether an official synchronized audio-bearing rendition exists for each
  exact ID;
- require rendition identity, duration, checksum, timeline relationship, and
  explicit transfer/processing authority;
- identify any source-owner or platform route that is expressly authorized;
  otherwise stop.

### Ego route

- request the V-RAGBench item-to-source crosswalk only;
- do not request media until exact Ego4D/EgoLife IDs, evidence intervals,
  release versions, license terms, and privacy review are available.

## 6. Fail-closed decision rules

Reject or defer an asset if:

- it has no decodable audio stream or has only silence/placeholder audio;
- its exact duration is outside 20–90 minutes;
- speech or ambient content is merely inferred from generated text;
- the only available object is a short clip rather than the complete source;
- source-time joins or A/V synchronization cannot be established;
- the official route or permission applies only to annotations/features;
- rights remain `unknown_hold` at the gate relevant to the intended use;
- a source-platform download would require an unapproved generic downloader,
  cookie extraction, or circumvention;
- duplicate/re-upload status defeats source independence;
- privacy or sensitive-content risk is unacceptable;
- modality necessity survives only because of annotation leakage or
  benchmark-derived wording.

## 7. Bottom line

The shortest scientifically defensible recovery is a mixed portfolio:
item-cleared public/institutional media for the primary cohort, at most one
controlled recording to guarantee an ambient-rich role, and one optional
FLARE/Omni item for external compatibility. Synthetic audio remains useful
plumbing, not evidence.
