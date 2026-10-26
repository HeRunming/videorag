# Audio-rich V+S+A acquisition routes v1

**Date:** 2026-10-12  
**Decision:** `AUDIO_RICH_VSA_ACQUISITION_ROUTES_V1_READY`  
**Scope:** local-evidence acquisition routing only; no network use, media
download, semantic review, annotation, H-tier assignment, or Gate-A credit.

## 1. Decision

Pilot-v5 still has two empty target cells:

- `B08`: observation/environment/wildlife, `V+S+A`, multi-hop, far/separated;
- `B12`: assembly/repair/mission operation, `V+S+A`, multi-hop,
  far/separated.

No inspected route is currently acquisition-ready for either cell. The local
evidence supports a **repair queue**, not a GO:

1. **Primary B08 route:** `EC-NASA-MOONBOUND`, contingent on resolving its
   2,202-second API versus 1,646-second playlist mismatch, component rights,
   restricted processing/annotation authority, and a tiny audio-first
   semantic preflight.
2. **Primary B12 route:** Assembly101's frozen participant `9051` session,
   contingent on the existing account receiving the pinned repository gate,
   native synchronized audio and wall-clock duration being proven, and
   substantive speech plus answer-bearing non-speech sound surviving human
   review.
3. **Secondary B08 route:** EPIC reserve `P23_102`, capped at one
   Oxford/EPIC lineage in the production pair and never paired with HD-EPIC as
   an independent source.
4. **Secondary B12 route:** CaptainCook4D reserve
   `cc4d_p05_e07` / recording `25_109`, contingent on selected-file audio and
   substantive speech. This is an independent participant/environment group
   from the current three CaptainCook groups.

The recommended production pair, if both pass, is therefore **NASA+ Moonbound
+ Assembly101**. They are publisher-, participant-, environment-, and
continuous-recording-disjoint. The recommended fallback pair is **EPIC
`P23_102` + CaptainCook4D `25_109`**; these are different dataset lineages,
although both are egocentric procedural sources and therefore less diverse
than the primary pair.

Each admitted source group must yield a **second defensible candidate** under
the exact two-candidates-per-source rule. This document does not presume what
that second candidate's modality profile will be.

## 2. Evidence boundary and ranking method

The ranking uses only checked-in:

- pilot-v5 matrix and targeted prospecting artifacts;
- access and governance registries;
- bounded stream/container audits;
- exact downloaded-source facts;
- frozen source pools and local event-source dossiers.

The following are not evidence of V+S+A suitability: dataset descriptions,
sound labels, narrations, transcripts, captions, action labels, co-occurrence,
music, score, generic room/handling noise, or interval distance alone.

Routes are ranked for the **two new audio-rich far/multi groups**, not for
general dataset quality. Ranking favors:

1. exact source identity or a frozen exact pool;
2. source-lineage independence;
3. long continuous wall-clock media or a verifiable long first-party object;
4. technically evidenced synchronized A/V;
5. plausible substantive speech and concrete source-world non-speech sound;
6. usable native timestamps;
7. bounded preflight and acquisition cost;
8. low annotation leakage and benchmark contamination risk.

`GO` below means only **eligible to enter acquisition/authoring after the
listed evidence exists**. It does not mean accepted modality necessity.

## 3. Ranked route table

| Rank | Route and exact local pool | Best target | Rights/gate state | Native synchronized audio | Speech / ambient-event likelihood | Duration and timestamp support | Lineage / contamination | Expected cost | Current |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | **NASA+ `EC-NASA-MOONBOUND`**; post `6979`, content `15230`, HLS asset `17905` | `B08` primary | First-party identity and HLS route established; acquisition, processing, annotation, and component rights remain `HOLD` | Muxed H.264/AAC and audio-only variants advertised, not decoded; synchronization plausible only | Speech **high**; concrete training/equipment/water/facility sound **medium but unverified** | API `2202 s`; playlist `1646 s`, a blocking mismatch; HLS `EXTINF` timeline only | NASA documentary production; component/score/archive contamination **high**; disjoint from Assembly/EPIC/CC4D | **High**; bounded mismatch repair, rights ledger, tiny decode, then full index | `REPAIR` |
| 2 | **Assembly101 frozen session** participant `9051`, session `nusar-2021_action_both_9051-c08a_9051_user_id_2021-02-22_115717`, representative `C10095_rgb.mp4`, SHA-256 `5d76...7415` | `B12` primary | Pinned HF revision `bfc15e...d967`; metadata ready; all 10 probes returned `403 GatedRepo`; processing/annotation not authorized | Unknown; zero media bytes read and no atom parse | Speech **unknown/medium-low**; assembly impacts/tool sounds **medium** | Wall-clock duration unresolved; 12 synchronized views, 5,107,229,101 aggregate bytes; dense labels exist but stay sealed | Independent dataset; participant block includes all sessions/views/derivatives; label contamination **high** | **High**; gate, bounded atom probes, minimum-view acquisition, index | `REPAIR` |
| 3 | **EPIC reserve `P23_102`** (`P23`, `3569.52 s`); same frozen pool also contains `P12_101`, `P06_101`, `P01_101`, `P22_114`, `P35_107`, `P03_103`, `P33_109`, `P04_123`, `P02_108` | `B08` secondary | Exact ID/duration/official metadata route known; media terms, acceptance, processing and annotation require separate closure | Dataset-level audio supported through EPIC-SOUNDS; selected file not technically verified | Narration/speech **medium-high**; kitchen events **high**, but both are label-blind hypotheses | `P23_102` is `59.492 min`; dense action/narration/sound timestamps exist but remain sealed | Complete `P23` participant/kitchen block; Oxford/EPIC contamination **critical**; correlated with HD-EPIC | **Medium**; selective file verification/acquisition and full index | `REPAIR` |
| 4 | **CaptainCook4D reserve `cc4d_p05_e07` / `25_109`** (`2126.96 s`); alternates `25_1`, `2_13`, `16_23`, `23_19`, replacements `23_24`, `16_17` | `B12` secondary | Exact official routes/durations known; governance hold remains; no annotation authority | Audio proven for acquired wave-0 GoPro files, not for reserve file `25_109` | Speech **low/unknown**; procedure sounds **high** | `35.449 min`; official duration and dense annotations exist, semantics sealed | Participant+environment block; disjoint from current `cc4d_p01_e08`, `p02_e02`, `p03_e03`; task-label contamination **high** | **Medium**; bounded route/audio probe, selective acquisition, index | `REPAIR` |
| 5 | **NASA+ `EC-NASA-TO-THE-RESCUE`**; post `4460`, content `13675`, HLS asset `15687` | `B12` alternate | Exact first-party HLS route; JPL/Caltech, archive/music components, processing and annotation remain held | Muxed A/V and audio-only advertised; not decoded | Speech **high**; mission-control/hardware signals **medium but authenticity unresolved** | API `3452 s`, playlist `3449 s`; strong long timeline, HLS timestamps only | Same NASA/JPL documentary family as other NASA routes; cannot pair with Moonbound as the preferred production-disjoint pair | **High**; component ledger and full manual chronology | `REPAIR` |
| 6 | **MECCANO official-release repair**; no exact IDs locally established | `B12` independent reserve | Exact release, terms, official route, IDs, and annotation authority unresolved | Unknown | Speech **unknown**; assembly events **plausible only** | Duration and timestamp support unresolved | Potentially independent and scientifically attractive; mirror/owner contamination risk **high until proven** | **High initially**, then medium if an exact official pool is found | `REPAIR` |
| 7 | **Ego-Exo4D V2 non-kitchen skilled-activity pool**; exact take/session IDs not locally enumerated | `B12` reserve | Agreement acceptance and official tooling absent; exact intended-use authority unresolved | Dataset-level yes, modality varies; selected assets unverified | Speech **medium**; skilled-activity events **medium-high** | 5,035 takes and 1,286.3 summed camera-hours are known, but wall-clock distribution is not | Meta/Ego super-lineage; all team/session/take/views/derivatives grouped; task/narration contamination **high** | **Very high**; agreement, tooling, metadata enumeration, multiview selection | `REPAIR` |
| 8 | **HD-EPIC exact-release repair**; exact source IDs not pinned | Either target, only as correlated fallback | Release, terms, registration, exact IDs, checksums and authority unresolved | Rich audio reported; selected files unverified | Corrected narrations **high**; about 51K audio events reported, but semantic use forbidden during selection | 156 videos / 41.3 h reported; mean `15.88 min` is below the preferred floor and item distribution is absent | Same Oxford/EPIC super-lineage; cannot be paired with EPIC as independent; leakage **critical** | **High** | `REPAIR` |
| 9 | **NASA+ `EC-NASA-PATHFINDERS`**; post `2391`, content `9199`, HLS asset `11211` | `B12` documentary reserve | Exact HLS route; JPL/Caltech/component authority and annotation approval unresolved | Muxed A/V and audio-only advertised; not decoded | Speech **high**; rover/landing/mechanical sound **medium-low and may be archival/score-covered** | API `3600 s`, playlist `3597 s`; HLS timestamps only | Same NASA/JPL documentary family as rank 5; archive/caption/graphics contamination **high** | **Very high**; shot/component ledger and manual timestamping | `REPAIR` |

### Routes deliberately not promoted

- **Ego4D v2.1:** useful long naturalistic reserve, but exact UIDs, accepted
  agreement, temporary AWS credentials, CLI, selected-file duration/audio,
  and annotation authority are absent. It also shares a Meta/Ego lineage with
  Ego-Exo4D.
- **USGS Shift Curves:** locally attractive for field procedure, but the later
  live preflight is `PREFLIGHT_NO_GO`: no exact object, no successful saved
  item-level rights evidence, and no stream/audio proof. It can re-enter only
  after a new exact-object implementation, not by relying on the old page
  description.
- **NASA Planetary Defenders:** exact long HLS route exists, but the local
  dossier rates concrete non-speech sound as weak and unverified.
- **Current NOAA `cand-051`:** cheap and worth human repair for a possible
  triple-modal family, but it is presentation-wrapped, development-touched,
  component rights are unresolved, and admitting it would worsen the frozen
  presentation-source and two-candidates-per-group constraints. It is not a
  preferred new production group.
- **Current EPIC/CaptainCook files:** local audio discovery found zero
  `S+A`, zero `V+S`, and zero `V+S+A` leads. They remain far-composition
  controls, not acquisition routes for the two missing cells.

## 4. Exact preflight decisions

### 4.1 Rank 1 — NASA+ Moonbound

**GO evidence**

1. API runtime and the selected first-party media timeline agree within the
   frozen tolerance, with an immutable asset/playlist identity.
2. A source/component ledger affirmatively permits internal ML processing and
   restricted human annotation for the retained intervals.
3. A bounded, separately authorized decode proves synchronized speech and
   source-world non-speech audio.
4. Audio-first review identifies a localizable training/equipment/water/
   facility event that contributes an answer fact rather than mood.
5. Blind A/V review identifies dynamic non-text vision and substantive speech,
   each with a distinct necessary role.
6. Two separated intervals form one coherent observation/training state chain,
   and captions, narration, OCR, score, archive inserts, and repeated clips do
   not answer the whole question.
7. A second defensible candidate survives from the same complete source group.

**REPAIR evidence**

- Runtime mismatch persists but a unique first-party full-length rendition is
  identifiable.
- V+S far/multi survives while the sound event is incidental or reconstructed.
- Semantic suitability is plausible but one component-rights class remains
  held.

**NO-GO evidence**

- No stable full-length object resolves the 556-second mismatch.
- All plausible A is score, Foley, reconstruction, or generic ambience.
- Narration/captions fully substitute for vision and sound.
- Component authority cannot cover restricted annotation.

### 4.2 Rank 2 — Assembly101 participant 9051

**GO evidence**

1. The current account receives gate access to revision
   `bfc15ea5e3f0bc8f8c232af6c1b45aa137a9d967` without changing the frozen
   selection.
2. Bounded head/tail atom probes establish wall-clock duration in
   `1200-5400 s`, video, native audio, channels/rate, and A/V synchronization
   for the representative file and the minimum selected view set.
3. Processing, restricted annotation, privacy, retention, and custody
   approvals close.
4. Action/mistake/task annotations remain sealed.
5. Raw-media review finds substantive speech, dynamic assembly or recovery,
   and a concrete event such as a tool engagement, snap, impact, or mechanism
   state that carries a non-duplicative answer fact.
6. A coherent setup/error/recovery/result chain supplies far/multi evidence.
7. A second defensible candidate survives inside the same participant block.

**REPAIR evidence**

- Gate opens but duration/audio is incomplete on some views.
- The session supports far visual procedure reasoning or V+A, but no
  substantive speech.
- Privacy/minimum-view authority remains incomplete.

**NO-GO evidence**

- Gate remains closed for the pinned revision.
- The selected session is below 20 minutes, lacks native audio, or has no
  usable synchronized time base.
- Human review finds no substantive speech or only incidental/recurrent
  assembly sound.
- Existing labels are needed to find the proposed evidence.

### 4.3 Rank 3 — EPIC P23_102

**GO evidence**

1. Freeze `P23_102`, exact checksum, route, and selected-file stream facts
   before semantic inspection.
2. Prove native synchronized audio on the selected object.
3. Close media terms, acceptance, processing, restricted annotation, privacy,
   and deletion controls.
4. Keep action, narration, and EPIC-SOUNDS labels/timestamps sealed through
   initial authoring.
5. Human review finds substantive speech, dynamic action/state, a concrete
   non-speech event, and a coherent far chain; each modality is necessary.
6. `P23` has no participant/kitchen overlap with current EPIC or any admitted
   HD-EPIC block.
7. A second defensible candidate survives in the `P23` block.

**REPAIR evidence**

- Technical/governance gates close but only V+A or far visual candidates
  survive.
- Speech is commentary or a complete duplicate of visible action.

**NO-GO evidence**

- Selected audio is absent or unusable.
- Source selection depends on action/narration/sound labels.
- Only EPIC and HD-EPIC can fill both missing groups.

### 4.4 Rank 4 — CaptainCook4D 25_109

**GO evidence**

1. The exact official GoPro route resolves and a bounded probe proves native
   synchronized audio and the expected `2126.96 s` time base.
2. Governance explicitly permits internal processing and restricted
   annotation.
3. The complete `cc4d_p05_e07` group remains disjoint from current groups and
   from any other selected CaptainCook group.
4. Human audio-first review finds a concrete procedure event and substantive
   speech.
5. A same-object/material setup-to-result or error-to-recovery chain supports
   far/multi, with no recipe/task-label use.
6. A second defensible candidate survives in the same group.

**REPAIR evidence**

- Strong far V or V+A candidates exist but speech is absent.
- Audio is present but only recurrent kitchen noise survives.
- Consent/annotation authority remains held.

**NO-GO evidence**

- Reserve file lacks native audio or a stable time base.
- All far pairs are unrelated stages joined only by distance.
- V+S+A requires presumed kitchen talk or generic handling noise.

### 4.5 Ranks 5-9

For `EC-NASA-TO-THE-RESCUE`, MECCANO, Ego-Exo4D, HD-EPIC, and
`EC-NASA-PATHFINDERS`, GO requires the same invariant evidence:

- immutable exact objects and source groups;
- affirmative media terms and restricted processing/annotation authority;
- selected-file duration and synchronized audio;
- independent, label-blind raw-media authoring;
- concrete answer-bearing A, substantive S, dynamic non-text V;
- coherent far/multi composition;
- a second defensible candidate;
- complete lineage and derivative blocking.

They remain `REPAIR` if exactly one bounded rights, route, duration, audio, or
lineage field is open. They are `NO_GO` if speech/audio is only presumed,
labels are required to locate evidence, the only sound is editorial, or the
route cannot provide an independent source group.

## 5. Exact next commands and implementation

No command below should be run in network mode until the corresponding
governance approval exists.

### 5.1 Local-only validation now

```bash
python -m json.tool data/rehearsal_plan/audio_rich_vsa_acquisition_routes_v1.json >/dev/null
python tools/hf_audio_stream_preflight.py --validate-plan-only
```

The second command validates the existing closed HF plan only; it does not yet
cover Assembly101's 10-session frozen pool.

### 5.2 Missing implementation: one generic bounded A/V preflight

Add a future tool, without executing downloads:

```text
tools/audio_rich_vsa_route_preflight.py
```

Required modes:

- `--mode validate-local`: verify IDs, hashes, durations, source grouping,
  rights decisions, route allowlists, and no semantic-label selection.
- `--mode bounded-http`: HEAD plus bounded head/tail ranges for MP4, or
  manifest plus at most one tiny non-retained HLS sample after authorization.
- `--mode emit-prescreen-inventory`: output a nonsemantic inventory consumable
  by `tools/semantic_av_source_prescreen_plan.py`.

Required fail-closed fields:

```text
route_id, target_slot, exact_source_group_id, exact_asset_id,
release_revision, expected_duration_s, object_hash_or_validator,
rights_processing, rights_restricted_annotation, lineage_block,
audio_codec, channels, sample_rate_hz, av_duration_delta_s,
timestamp_time_base, bytes_requested, bytes_retained,
semantic_labels_opened=false
```

### 5.3 Route-specific future commands

After approval, the intended invocations are:

```bash
# Assembly101: extend the existing bounded HF tool to accept this registry.
python tools/hf_audio_stream_preflight.py \
  --plan data/rehearsal_plan/assembly101_authenticated_registry_v1.json \
  --validate-plan-only

# CaptainCook4D: first generate a reserve-only inventory containing 25_109
# (and one frozen replacement), then run the existing bounded route probe.
python tools/captaincook4d_route_probe_v3.py \
  --inventory data/acquisition_preflight/captaincook4d_vsa_reserve_inventory_v1.json \
  --output data/acquisition_preflight/captaincook4d_vsa_reserve_probe_v1.json

# Human prescreen planning only after local exact-source inventories exist.
python tools/semantic_av_source_prescreen_plan.py \
  --inventory data/acquisition_preflight/audio_rich_vsa_exact_inventory_v1.json \
  --plan-out data/rehearsal_plan/audio_rich_vsa_prescreen_plan_v1.json \
  --form-out data/rehearsal_plan/audio_rich_vsa_prescreen_form_v1.json \
  --plan-id audio-rich-vsa-prescreen-v1 \
  --form-id audio-rich-vsa-prescreen-form-v1 \
  --created-at 2026-10-12T00:00:00+08:00 \
  --seed AVTRACE-AUDIO-RICH-VSA-V1 \
  --sample-count 24 \
  --interval-duration-s 12
```

For NASA HLS sources, no suitable generic local tool currently exists. The new
preflight must reuse the checked-in manifest identity, compare API and playlist
durations, reject a mismatched Moonbound rendition, and prohibit full segment
or full-media acquisition.

For MECCANO, first implement an **official-primary-source metadata registry**
that can remain empty/NO-GO; do not accept the locally observed unverified HF
mirrors. For Ego-Exo4D, implement a metadata-only official-tool export before
any media request. For HD-EPIC, implement an EPIC/HD-EPIC participant and
kitchen overlap audit before source freezing.

## 6. Production selection and stopping rule

### Preferred production pair

| Cell | Primary | Required second candidate in group | Production-disjoint from |
|---|---|---|---|
| `B08` | NASA+ `EC-NASA-MOONBOUND` | another independently defensible family from the same full documentary source, not a replay/encode | Assembly101, EPIC, CaptainCook4D |
| `B12` | Assembly101 participant `9051` session | another family in the same participant block, authored without task/mistake labels | NASA+, EPIC, CaptainCook4D |

Do **not** substitute `EC-NASA-TO-THE-RESCUE` or Pathfinders for Assembly101
while retaining Moonbound and then claim two independent production lineages.
Do **not** pair EPIC and HD-EPIC as independent.

### Fallback pair

If either primary route reaches documented NO-GO:

- `B08` fallback: EPIC `P23_102`;
- `B12` fallback: CaptainCook4D `25_109`.

If only one fallback passes, try the highest-ranked non-correlated route:
MECCANO before Ego-Exo4D, and one NASA/JPL source only if no other NASA source
is already admitted.

### Honest narrowing fallback

Freeze a prospective addendum removing or reducing the two `V+S+A` targets
when either condition holds:

1. no two production/source-disjoint groups survive unchanged rights,
   duration, synchronized-audio, speech, ambient-event, far-composition, and
   second-candidate gates; or
2. the only surviving pair is correlated (`EPIC` + `HD-EPIC`, two NASA/JPL
   documentaries, or `Ego4D` + `Ego-Exo4D`).

The replacement must be prospective. Permissible reporting is:

- V+S+A feasibility was tested and failed under frozen necessity criteria;
- retain passing V+S, V+A, A, or far/multi families under their actual
  profiles;
- report the empty stratum and route-specific failure evidence.

Never relabel surf, score, narration bed, generic handling noise, an audio
classifier label, or simple co-occurrence as the missing A component.

`AUDIO_RICH_VSA_ACQUISITION_ROUTES_V1_READY`
