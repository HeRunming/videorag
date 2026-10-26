# LVB-01 post-download candidate decision

**Decision date:** 2026-09-09  
**Batch:** five downloaded LongVideoBench candidate bundles  
**Overall decision:** **CONDITIONAL GO — visual + subtitle-proxy internal
rehearsal only**

## 1. Status transition

Task 61 changes the five candidates from metadata-only leads to verified local
technical assets, but only for the modalities actually present.

| Status dimension | 2026-09-09 finding |
|---|---|
| Download and integrity | All five video/subtitle bundles were downloaded and hash-verified internally against the frozen acquisition records. |
| Video | Available. Each MP4 has one decodable H.264 video stream and passed bounded beginning/middle/end decode checks. |
| Audio | **Absent. Each downloaded MP4 has zero audio streams.** |
| Subtitle proxy | Available. Each JSON is ordered and non-empty. Four use predominantly point-like cues, so cue starts and broad timeline coverage are usable but cue ends are not reliable speech-span boundaries. |
| Duration | Verified against candidate metadata within the audit tolerance. |
| Internal rehearsal | Technically ready for visual and subtitle-proxy experiments only. |
| Audiovisual or ambient rehearsal | Blocked by the missing audio stream. |
| Scientific episode suitability | Not established. |
| Rights and public release | `unknown_hold`; acquisition integrity does not establish processing, annotation, derivative, or publication rights. |

The machine-readable, non-restricted status overlay is
`data/rehearsal_plan/lvb01_verified_asset_status.csv`. Historical shortlist and
candidate records retain their original dates and pre-download statements; the
new overlay is the authoritative post-download technical status as of
2026-09-09.

The factual basis is `docs/review/lvb01_download_media_audit.md`. Restricted
paths, payload digests, subtitle text, and restricted-manifest details are not
copied into the status overlay or this decision.

## 2. Precise Go / No-Go

### GO now: restricted internal technical experiments

The batch is a **GO** for the following bounded experiments:

1. **Visual evidence acquisition**
   - seek and decode source-time windows;
   - build or exercise a visual retrieval index;
   - test near/far visual evidence localization and multi-window retrieval;
   - measure retrieval latency, scan coverage, and source-time citation
     accuracy.
2. **Subtitle/speech-proxy search**
   - index ordered subtitle text as a source-level proxy for spoken content;
   - search by cue start time or conservative windows around cue starts;
   - test query-to-subtitle localization and subtitle-to-video follow-up;
   - do not interpret approximately 10 ms cue ends as real utterance spans.
3. **Visual-versus-transcript routing**
   - compare policies that begin with video search, subtitle search, or switch
     between them;
   - test whether a policy recognizes that a subtitle hit still requires visual
     confirmation for visual claims.
4. **CLEAN/BLOCKED/RESTORED intervention mechanics**
   - instantiate matched interventions over the **video** and
     **subtitle-proxy** channels;
   - block selected evidence windows or one of those two channels;
   - restore the exact blocked evidence without changing the answer surface,
     budget, or unrelated observations.
5. **Recovery, stopping, citation, and sufficiency mechanics**
   - test whether a policy changes route after an observable visual/subtitle
     failure;
   - test restoration-triggered recovery;
   - test evidence sufficiency, abstention, premature stopping, and timestamp
     citation validation using only the available channels.
6. **Engineering robustness**
   - test long-duration seeking, point-like subtitle handling, cache behavior,
     state transitions, replay, and failure logging on real media rather than
     synthetic fixtures.

These are engineering and limited method-rehearsal uses. They are not approval
to create final benchmark annotations or release media-derived artifacts.

### NO-GO now: claims requiring real audio or completed governance

The batch is a **NO-GO** for:

- raw speech waveform retrieval, ASR evaluation, speaker or prosody analysis;
- ambient or non-speech audio retrieval;
- music, acoustic-event, or audio-context evidence claims;
- true `V+A`, `S+A`, or `V+S+A` minimal-modality necessity;
- audio/video synchronization, drift, or cross-modal temporal alignment;
- audio-channel `BLOCKED`/`RESTORED` outage and recovery claims;
- treating subtitles as proof that an audio stream or intelligible speech was
  available;
- treating a missing audio stream as a controlled experimental intervention;
- claims that AV-TRACE has demonstrated audiovisual recovery, full-modality
  routing, or ambient-audio reasoning;
- public benchmark, rights-cleared, redistributable, privacy-cleared, or
  publication-ready status;
- final episode acceptance or final benchmark annotation.

The missing audio is a property of the acquired rendition, not a valid
experimental `BLOCKED` condition. There is no matched CLEAN rendition with
audio and no restoration action that can return the missing channel.

## 3. Scientific hypotheses supported by this batch

The five sources can provide **limited evidence** about:

| Hypothesis | Testable interpretation |
|---|---|
| Real long-video visual retrieval is operational | The backend and agent can seek, retrieve, and cite visual evidence from 25–50 minute decoded sources. |
| Subtitle-proxy search can guide source navigation | Ordered subtitle cues can localize candidate source regions despite unreliable cue-end semantics. |
| Routing policy matters across available channels | Video-first, subtitle-first, and switch-after-failure policies can be compared for visual/subtitle tasks. |
| Matched intervention mechanics work on real inputs | Video- or subtitle-evidence can be hidden and exactly restored while preserving matched episode envelopes. |
| Recovery behavior can be measured for non-audio failures | A policy can diagnose a failed visual/subtitle route, choose another available route, and exploit restoration. |
| Stopping and evidence sufficiency can be audited | The system can be checked for unsupported finalization, abstention, citation accuracy, and stopping after adequate evidence. |
| Real-media engineering differs from the synthetic simulator | Seeking cost, long-source latency, subtitle sparsity, and evidence-window handling can be measured on actual files. |

Any test must be labeled **visual + subtitle-proxy**, not audiovisual. Existing
upstream questions may be used as inspection leads, but this task does not
authorize copying answers or producing final AV-TRACE annotations.

## 4. Scientific hypotheses not supported by this batch

This batch cannot test:

1. whether an agent retrieves semantic information from raw speech;
2. whether non-speech sound is necessary or sufficient for an answer;
3. whether vision and audio are jointly necessary;
4. whether vision, subtitle/speech, and ambient audio are jointly necessary;
5. whether a policy detects, diagnoses, or recovers from an audio-channel
   outage;
6. whether ASR/subtitles faithfully represent the source audio;
7. whether the system aligns acoustic and visual events in source time;
8. whether full-modality retrieval improves answer quality or efficiency;
9. whether audiovisual modality effects generalize across source families;
10. whether any candidate is rights-cleared, privacy-cleared, scientifically
    suitable as a final episode, or releasable.

## 5. Guardrails against silent benchmark collapse

Until at least three genuinely audio-bearing long videos pass item-level
technical and governance review:

- report this batch as `V+subtitle-proxy`, never `AV`;
- keep audio, ambient, `V+A`, and `V+S+A` cells explicitly missing rather than
  filling them with subtitle results;
- exclude this batch from audio-outage denominators;
- do not relabel subtitle search as speech/audio retrieval;
- do not count an audio-free rendition as an audio intervention;
- keep visual/subtitle results separate from any later audio-bearing cohort;
- make any cross-cohort comparison source-stratified and disclose the source
  imbalance;
- retain `unknown_hold` for rights/public release until an independent
  artifact-level decision changes it.

## 6. Next executable tasks

| Proposed task | Can start now? | Independent objective | Principal outputs |
|---|---|---|---|
| **Task 63 — LVB visual/subtitle restricted rehearsal** | **Yes** | Exercise source-time visual retrieval, conservative subtitle-start windowing, video-vs-subtitle routing, and matched video/subtitle CLEAN/BLOCKED/RESTORED mechanics on all five assets. Persist only approved internal metrics and non-content diagnostics; create no final annotations. | Rehearsal runner, tests, restricted run manifest, non-sensitive engineering report. |
| **Task 64 — Audio-bearing item reconnaissance and exact allowlist** | Parent-network work required | Revalidate the ranked routes in `docs/pilot/audio_gap_recovery_plan.md`; resolve exact files, durations, audio claims, rights scope, and source-time artifacts; select a 3–5 item primary/reserve allowlist. Download nothing. | Dated reconnaissance report, item-level rights questions, exact proposed allowlist and rejection reasons. |
| **Task 65 — Authorized audio-bearing acquisition and stream audit** | After Task 64 and explicit approval | Acquire only approved exact objects through official routes, then verify hashes, duration, video/audio streams, channel usability, A/V timing, speech, ambient events, privacy, and duplicate status. | Restricted acquisition manifest, `ffprobe`/decoder audit, safe status overlay, Go/No-Go. |
| **Task 66 — Cross-modal rehearsal gate** | After at least three assets pass Task 65 | Determine whether the approved audio-bearing cohort can instantiate speech, ambient, `V+A`, and `V+S+A` necessity and matched audio outage/restoration without unimodal shortcuts. This remains pre-final annotation design. | Modality-coverage matrix, rejected-family reasons, rehearsal-only episode specifications. |

## 7. Final decision

**GO:** continue immediately with a restricted **visual + subtitle-proxy**
engineering rehearsal and the associated intervention/recovery mechanics.

**NO-GO:** make any claim about raw audio, ambient sound, true audiovisual
minimality, audio outage/recovery, final episode validity, or public release.

The next data milestone is not “more silent LongVideoBench items.” It is an
item-selective, authorized set of **3–5 independently verified audio-bearing
long videos**.
