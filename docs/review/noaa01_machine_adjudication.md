# NOAA-01 machine adjudication

**Review date:** 2026-09-10  
**Stage:** `MACHINE_ADJUDICATED_PROVISIONAL_MVP`  
**Reviewer type:** `machine_codex`  
**Human-reviewed:** no  
**Gold annotation:** no  
**Decision:** **`GO_PROVISIONAL_EPISODE_CONSTRUCTION`**

## Executive finding

The exact 18 queued windows were decoded from the three original restricted
MP4 files. This is a provisional machine/Codex pass, not a substitute for
human-reviewed gold annotation. Exact pinned local Whisper Tiny English and
AST AudioSet snapshots were integrity-verified and executed on CPU for all 18
windows. Six windows are suitable for a first provisional episode-construction
set; the original three pilot assets remain stable.

## Counts

- Accepted: **6**
- Deferred: **10**
- Rejected: **2**
- Windows passing the ASR intelligibility proxy: **14**
- Windows with credible specific non-speech events: **1**
- Windows with meaningful visual content: **11**
- Likely-necessary modalities: **V=0, S=0, A=0**
- Candidate question/evidence seeds: **14**

## Model and decode posture

Every file listed by each local `SHA256SUMS` verified before model import.
Whisper `87c7102498dcde7456f24cfd30239ca606ed9063` and AST
`f826b80d28226b62986cc218e5cec390b1096902` loaded with `local_files_only=True` under
offline Transformers/Hugging Face settings. There are exactly two
`model.safetensors` weight files and zero `pytorch_model.bin` files. No HF
credential was read, recorded, or emitted. CPU inference used float32,
deterministic algorithms, seed 0, 4 threads, one interop thread, and
batches of 3. The host-only NumPy alias shim is recorded in
the restricted model manifest.

Restricted transcripts remain only in the restricted records. This public
report gives counts and methodological summaries, not transcript excerpts.
Generic speech, room/context, music, and noise labels are separated from
credible specific non-speech events.

## Scientific-layer separation

Every restricted record has four separate sections:

1. `observed_model_output`: decode facts, Whisper output, AST top-k output, and
   OpenCV observations;
2. `machine_inference`: thresholded speech/audio/vision assessments;
3. `codex_synthesis`: question seed, modality role, counterfactual rationale,
   disposition, and confidence;
4. `unresolved_uncertainty`: model-quality, localization, and disagreement
   limitations.

No modality is marked `likely_necessary` at this stage because no modality-drop
answerability intervention has been executed. Candidate roles identify which
channels support episode construction; they are not minimality claims. The
cross-modal hurricane-factor candidate is corroborative, and the audiovisual
surf candidate remains a routing hypothesis until its counterfactual is run.

## Cross-model and Task 80 consistency

Task 80/81 correctly treated their outputs as routing hypotheses. Task 84 now
finds usable ASR proxies in most content windows, finds one provisional
specific non-speech-event candidate, and confirms that several
Task 80 non-speech-priority routes were actually speech/music mixtures rather
than specific event evidence. Scenario counts were: lenient: intelligible-ASR 14, specific-audio 1, visual 18; default: intelligible-ASR 14, specific-audio 1, visual 16; strict: intelligible-ASR 14, specific-audio 1, visual 9.

Against Task 83 fallback, the main changes are real intelligibility judgments,
new machine-generated seeds, corrected modality-role hypotheses, and one
additional accepted window. One visually overclaimed window (`003`) is
deferred after red-team inspection. The Task 81 pilot trio remains unchanged.

Changed Task 83 fallback judgment fields by window (the unchanged window is
`noaa01-review-001`):

- `noaa01-review-002`: speech_intelligible, candidate_seed
- `noaa01-review-003`: speech_intelligible, non_speech_audio_present, candidate_seed, disposition
- `noaa01-review-004`: speech_intelligible, non_speech_audio_present, credible_specific_events, candidate_seed, candidate_modality_role
- `noaa01-review-005`: speech_intelligible, non_speech_audio_present
- `noaa01-review-006`: candidate_modality_role
- `noaa01-review-007`: speech_present, speech_intelligible
- `noaa01-review-008`: speech_intelligible
- `noaa01-review-009`: speech_intelligible, candidate_modality_role
- `noaa01-review-010`: speech_intelligible, non_speech_audio_present
- `noaa01-review-011`: speech_intelligible, non_speech_audio_present, candidate_seed
- `noaa01-review-012`: non_speech_audio_present
- `noaa01-review-013`: speech_present, speech_intelligible
- `noaa01-review-014`: speech_intelligible, non_speech_audio_present, candidate_seed
- `noaa01-review-015`: speech_intelligible, candidate_seed
- `noaa01-review-016`: speech_intelligible, non_speech_audio_present, candidate_seed, candidate_modality_role
- `noaa01-review-017`: speech_intelligible, candidate_seed, disposition
- `noaa01-review-018`: non_speech_audio_present

## Recommended first provisional episode set

Use the six accepted windows:

- `cand-049`: `noaa01-review-004`
- `cand-051`: `noaa01-review-007`, `noaa01-review-011`
- `cand-052`: `noaa01-review-014`, `noaa01-review-016`,
  `noaa01-review-017`

The selected set spans visual, speech, and audiovisual routing hypotheses.
None is yet modality-minimal. Branded/product imagery, low-value title cards,
weak webinar fragments, and credits remain deferred or rejected.

## Safety and persistence

Media was decoded directly from the exact originals. No repository frame,
clip, WAV, waveform, thumbnail, or contact sheet was created. Restricted JSON
is mode 0600. Temporary inspection media is not part of the tool output and
must be deleted before completion. Transcript text is not published outside
the restricted tree.

## Decision rationale

**`GO_PROVISIONAL_EPISODE_CONSTRUCTION`**: exact local models ran successfully,
all integrity and persistence controls passed, and six grounded candidates
now span visual, speech, and one specific non-speech audio use. Human review
remains necessary before gold release or definitive modality minimality.
