# Event-centric long-A/V source discovery v1

**Date:** 2026-09-23  
**Decision token:** `REPAIR`  
**Scope:** rights-first discovery sidecar; no new completed network probe, no
media download, no acquisition authorization

## 1. Decision

`REPAIR`

The package records **14 candidate source groups across seven capture-format
labels** and ranks **six** for a later exact-acquisition preflight. It does not
support `EVENT_SOURCE_DISCOVERY_READY`, because **0/14** candidates are
currently exact-acquisition ready:

- only one candidate, NASA/JPL *The Pathfinders*, has an exact first-party
  media master already frozen;
- that object remains on a component-rights, processing, and annotation hold;
- the strongest procedural lead, USGS Shift Curves, lacks a successful saved
  item page and exact media object;
- most other candidates have only official landing/catalog identity and
  family-level policy evidence;
- semantic non-speech audio and dynamic non-text visual evidence remain
  hypotheses except for limited prior inspection of NOAA `cand-049`;
- no sports source and no clean wildlife-only source reached dossier quality
  before browsing was stopped.

This is still useful progress: it creates a fail-closed event-centric queue,
separates acquisition/processing/annotation/release decisions, and rejects
presentation-heavy or rights-ambiguous candidates instead of promoting them.

## 2. Boundary and evidence cutoff

The user stopped further browsing and probing and requested immediate
finalization. Accordingly:

- Task 143 completed **zero new successful network requests**;
- the two attempted proxy requests failed or were aborted before source
  evidence was collected;
- no HEAD, range, manifest, segment, or container request completed for this
  task;
- no media bytes were downloaded or retained;
- no existing canonical source/index root was modified;
- all findings below are derived from repository evidence dated principally
  **2026-09-05 through 2026-09-23**;
- no current-web freshness is claimed.

The machine-readable record is
`data/rehearsal_plan/event_centric_source_dossiers_v1.json`.

## 3. Why this wave is required

Task 122 froze AV-TRACE as a benchmark-and-diagnostic protocol and prioritized
rights-first source diversification. Task 141 then found that the acquired
Oxford/MIT/Yale sources and planned NOAA additions were too
lecture/webinar/presentation-heavy for broad audiovisual or ambient claims.
Its minimum six-source repair requires:

- at least three event-centric source groups;
- at least two sources with plausible semantically relevant non-speech
  evidence;
- at least two sources with dynamic non-text visual evidence;
- no ambient quota satisfied by generic applause, chalk, writing, room noise,
  or music.

Task 144 independently confirmed the failure mode. The lecture-source ambient
proposals were speech or generic classroom sounds, and the visual proposals
were largely board text, static diagrams, title cards, or talking heads. The
preferred future composition therefore calls for field procedure/maintenance,
environment or wildlife observation, industrial/lab process, and
assembly/repair/mission-operation sources.

This discovery wave applies those constraints at source intake rather than
after expensive annotation.

## 4. Evidence and decision standard

### 4.1 Discovery fields

Each candidate records:

1. exact canonical URL and stable ID available in the repository;
2. publisher/rightsholder status;
3. duration and stream evidence, including explicit unknowns;
4. dated item/license/permission evidence;
5. privacy, music, marks, component, and safety risks;
6. approved candidate acquisition method, without authorizing it;
7. expected `V`, `S`, and `A` routes;
8. transcript, caption, OCR, and narration shortcut risk;
9. separate acquisition, processing, annotation, and release decisions; and
10. exact-acquisition readiness.

### 4.2 Fail-closed interpretation

An institutional host is not item clearance. Federal custody is not always
public domain. General NASA, NARA, NOAA, or USGS policy does not clear
contractor, partner, music, marks, privacy, publicity, or archival components.
A Commons license badge does not cure uploader-authority or source-chain
problems.

Likewise, source titles and metadata cannot establish semantic modality:

- equipment noise is not answer evidence merely because it is audible;
- launch or surf sound is not necessary merely because it is salient;
- diagrams, slides, captions, and board writing are vulnerable to OCR;
- documentary narration may fully substitute for visible action;
- score and applause are not acceptable ambient evidence by default.

No candidate can proceed to family authoring until a later semantic pre-scan
verifies the proposed route.

## 5. Candidate portfolio

| Disposition | Count |
|---|---:|
| Rank for exact-acquisition preflight | 6 |
| Reserve / repair | 5 |
| Reject weak or ambiguous | 3 |
| **Total** | **14** |

The seven capture-format labels are:

1. field or instrument procedure training;
2. field safety demonstration;
3. observational environment or maritime operations;
4. mission training or operations documentary;
5. engineering failure/recovery documentary;
6. industrial or military process archival film; and
7. public performance or ceremony.

These are discovery labels, not validated scientific strata. Several sources
are edited documentaries or presentation-wrapped event footage and may fail
the later semantic screen.

## 6. Ranked exact-acquisition preflight queue

“Ranked” means worth a separate exact dossier/preflight. It does **not** mean
eligible for download.

| Rank | Source group | Format/domain | Duration evidence | Current strongest evidence | Principal blockers |
|---:|---|---|---:|---|---|
| 1 | `EC-USGS-SHIFT-CURVES` — *Developing and Applying Shift Curves using GRSAT* | Field/instrument procedure | 01:17:31, prior official-page observation | Frozen plan recorded Public Domain, Download Video, and Download Transcript | Saved dossier has only WAF/403/405 responses; no exact object or streams; processing/annotation authority absent |
| 2 | `EC-NASA-MOONBOUND` — *Moonbound \| For All Humanity* | Astronaut training | 00:36:42 official NASA+ | Official title/runtime; action-rich training hypothesis | No exact object; contractor/partner, music, marks, and likeness scope unresolved |
| 3 | `EC-NASA-TO-THE-RESCUE` — *JPL and the Space Age: To the Rescue* | Engineering failure/recovery | 00:57:32 official NASA+ | Natural failure/workaround/restoration narrative | JPL/Caltech and component authority unresolved; no exact item route |
| 4 | `EC-NOAA-SHIPWRECKS` — *Shipwrecks and Sanctuaries* | Maritime observation/ROV | 00:50:00 official NOAA | Official title/runtime; possible underwater dynamic evidence | Webinar/presentation share unknown; partner clips, music, likenesses, exact object, and semantic audio unresolved |
| 5 | `EC-NASA-PATHFINDERS` — *JPL and the Space Age: The Pathfinders* | Engineering/mission documentary | 01:00:00 NASA+ metadata | Exact first-party HLS master and advertised H.264/AAC A/V variants | JPL/Caltech and documentary component authority unresolved; no segment/container parse or semantic screen |
| 6 | `EC-NASA-PLANETARY-DEFENDERS` — *Planetary Defenders* | Planetary-defense exercise/documentary | ~01:15:00 official government notice | Detection, modeling, exercise, and response structure | Runtime remains approximate; no exact object; partner, dramatized, music, and likeness scope unresolved |

### Preflight ordering rationale

1. **USGS Shift Curves** is the strongest match to the requested field
   procedure/maintenance axis and has the best prior item-level permission
   signal, but its current dossier is technically empty of successful source
   evidence.
2. **Moonbound** is action-rich and less presentation-like than the existing
   lecture pool. It needs exact NASA+ route and component-rights work.
3. **To the Rescue** is valuable for AV-TRACE because failure, workaround, and
   recovery are native to the source narrative, but JPL/Caltech authority is a
   hard prerequisite.
4. **Shipwrecks and Sanctuaries** could provide observation/ROV evidence, but
   must prove that meaningful action footage occupies enough of the native
   recording and that non-speech sound is not dubbed or incidental.
5. **Pathfinders** already has the strongest exact-route evidence, but the
   rights-first order still requires JPL/Caltech and component repair before
   any media-segment probe.
6. **Planetary Defenders** has a useful event sequence and target-length
   runtime, but its exact object and high-burden documentary components remain
   unresolved.

## 7. Reserve / repair candidates

| Source | Why retained | Why not top-six ready |
|---|---|---|
| `EC-NASA-EXPLORERS-LAUNCH` | Action-rich mission-operations sequence with verified official identity/runtime | 00:23:21 is below this wave's preferred 30-minute target; display-title collision, exact object, and component rights remain unresolved |
| `EC-NARA-CITY-UNDER-ICE` | Distinct archival machinery/logistics process hypothesis | Runtime, restriction record, exact object, streams, soundtrack provenance, and sensitive-content review are unresolved |
| `EC-NARA-MEMPHIS-BELLE` | Action-rich aviation process and authentic-event-audio potential | Approximate duration, item restrictions, music, combat imagery, privacy/publicity, and exact object unresolved |
| `EC-NARA-THUNDERBOLT` | Distinct aviation operations source | Candidate metadata was not re-reviewed; restrictions, streams, soundtrack provenance, and safety burden unresolved |
| `EC-NOAA-BEACH-BAY-SAFE` | Prior direct frame audit found real beach footage and rescue animation; surf is the strongest current environmental-audio lead | Existing development-touched webinar source; rights/privacy hold; repeated visible/spoken surf routes defeat any present ambient-necessity claim |

The ranked `EC-NASA-PATHFINDERS` illustrates why route readiness and use readiness must
stay separate. Its first-party master is known:

```text
https://nasaplus.akamaized.net/output/11211.m3u8
```

The saved master advertises H.264 video, AAC audio, an audio-only variant, and
English closed captions, but no segment was fetched or decoded. More
importantly, general NASA guidance does not clear JPL/Caltech production,
score, archive/partner footage, marks, or likenesses. It remains `HOLD`.

## 8. Explicit rejections

### `EC-USGS-SIX-ERUPTIONS`

Reject for this event-centric wave unless later used as a presentation
control. It is a public lecture with possible eruption inserts, a high
transcript/OCR shortcut risk, uncertain semantic eruption audio, no successful
saved item page, and no exact object.

### `EC-COMMONS-BLOCKCHAIN`

Reject for this wave. Exact metadata is unusually strong—pageid
`126021487`, oldid `1032015587`, 82,285,120-byte WebM, VP9/Opus, and
2,354.101-second duration—but the file is a YouTube import, the saved API
exposes `License review needed (video)`, recording-owner authority is not
affirmatively established, and the content is lecture/slide/screenshot
dominant.

### `EC-COMMONS-WIKIMANIA-2024-OPENING`

Reject for this wave. It is a genuine event recording, but likely evidence is
stage speech, text screens, music, and applause. Music, audience likenesses,
slides, venue/marks, page revision, license, and uploader source chain remain
unresolved. Generic applause cannot satisfy AV-TRACE ambient quotas.

## 9. Capture-format and domain gaps

The 14 recorded groups meet the numerical discovery request, but the useful
portfolio is not yet balanced:

- **field procedure:** one strong but technically blocked USGS lead;
- **maintenance/assembly:** no clean item-level candidate;
- **wildlife-only observation:** no dossier-quality candidate;
- **industrial/lab process:** one archival engineering lead with weak current
  metadata;
- **sports:** no dossier-quality candidate;
- **performance/event:** Commons ceremony lead exists but is rejected for
  music/privacy/semantic-audio reasons;
- **mission operations:** several NASA documentary leads, but they are one
  correlated production family and carry music/archival/component risk;
- **environment observation:** NOAA leads are presentation-wrapped and
  development-touched.

Therefore the package must not be described as a finished source pool.

## 10. Exact next preflight contract

If browsing/probing is later reauthorized, process only the ranked six, in
order, and stop each candidate as soon as a hard gate fails.

1. **Dated rights snapshot**
   - archive exact item page and controlling policy/permission page;
   - store response date, bytes, SHA-256, canonical ID, and source revision;
   - identify publisher, claimed rightsholder, federal-work/PD/CC basis, and
     every explicit exception.
2. **Exact route**
   - freeze only an official first-party direct object, API-provided original,
     HLS master, or NARA catalog-described digital object;
   - reject embedded-platform extraction, mirrors, guessed URLs, cookies, or
     user-upload chains without authority.
3. **Bounded technical probe**
   - HEAD or small metadata response first;
   - closed host/path allowlist;
   - reject full-object `200`, oversized responses, or redirects outside the
     allowlist;
   - obtain duration, video/audio streams, codecs, time base, range behavior,
     and synchronized A/V evidence without retaining media payloads.
4. **Semantic pre-screen**
   - inspect enough source content, under separate authorization, to classify
     visual route as dynamic non-text, diagram/OCR, overlay, talking head, or
     archive montage;
   - identify a concrete non-speech event and state what answer fact it could
     carry;
   - reject score, generic room noise, applause, chalk, writing, or repeated
     visible/spoken environmental sound as ambient necessity.
5. **Separate governance decisions**
   - acquisition;
   - internal processing;
   - restricted human annotation;
   - raw media release;
   - clip/frame/audio release;
   - transcript release;
   - annotation/evaluator release;
   - derived-feature release.

No decision inherits from another. In particular, a public-domain or CC basis
does not automatically authorize public release of every component or
source-derived artifact.

## 11. Current decisions

Across all 14 candidates:

- **acquisition:** 0 `GO`, all `HOLD` or `NO_GO` for this wave;
- **processing:** 0 affirmative new decisions;
- **annotation:** 0 affirmative new decisions;
- **release:** 0 authorized raw, clip/frame/audio, transcript, annotation, or
  derived-feature decisions;
- **human necessity:** not assessed and not claimed;
- **public release:** not assessed as ready and not claimed.

## 12. Required follow-up

1. Repair and preflight the top six only after explicit network/probe
   authorization.
2. Continue rights-first discovery for:
   - wildlife/environment observation without webinar framing;
   - assembly/repair or maintenance;
   - industrial/lab process;
   - sports/performance with rights-clean audio.
3. Cap NASA/JPL documentary-family concentration; multiple episodes do not
   equal capture-format independence.
4. Require the Task-141/144 semantic pre-screen before any candidate counts
   toward ambient, `V+A`, `S+A`, or `V+S+A`.
5. Keep every source in discovery status until exact acquisition,
   processing, annotation, and release are decided independently.

## 13. Final token

```text
REPAIR
```
