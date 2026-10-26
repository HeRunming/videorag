# Task195 pilot-v4 candidate integration audit

**Date:** 2026-10-10  
**Decision:** `PILOT_V4_CANDIDATE_MATRIX_REPAIR`  
**Artifact class:** prospective P-tier candidate planning only  
**Human review performed:** no  
**Gate A GO asserted:** no

## 1. Executive decision

Task195 creates a prospective v4 matrix by replacing exactly four Task192
visual slots with the four governed Task193/194 leads:

| Task194 code | Source | Slot replacement | Profile | Rationale |
|---|---|---|---|---|
| `C01` | `15_29` | `PV3-CC15-01` → `PV4-CC15-01` | A | Use the three-burst blender lead while preserving the sole CC15 far/multi tomato-state slot. |
| `C02` | `16_20` | `PV3-CC16-02` → `PV4-CC16-02` | A | Replace Task192's weakest newly-authored visual repair; the rejected arbitrary far parent remains rejected. |
| `C03` | `P27_101` | `PV3-P27-02` → `PV4-P27-02` | V+A | Upgrade the same wrapper action lineage with the Task193 crinkling/tearing hypothesis without changing source count. |
| `C04` | `P28_103` | `PV3-P28-01` → `PV4-P28-01` | V+A | Upgrade the same potato-peeling lineage with the corrected scraping lead after the earlier scissors false positive. |

The source and slot invariants remain exact: **6 sources, 12 slots, exactly 2
slots per source**. The replacement choice preserves the sole existing
far/multi hypothesis (`PV4-CC15-02`) and removes the weakest Task192 authored
repair (`PV3-CC16-02`) rather than displacing a stronger retained lineage.

The prospective profile hypotheses become **6 V, 2 S, 2 A, 2 V+A, 0 V+S, and
0 V+S+A**. C01-C04 are not currently credited human findings: all four
Task194 imports are blank `REPAIR`, no Task153 source has a completed READY
import, and fresh normal-mode regeneration has not occurred.

Gate A remains **REPAIR**, not GO and not yet NO_GO. A governed repair path
remains, but the exact current matrix cannot satisfy Pivot v2 because it still
lacks two V+S and two V+S+A families, one multi-hop family, and five
far/separated families.

## 2. Inputs and audit method

The audit read Tasks 145, 149, 153, and 192-194; the v3 matrix; the Task193
fact/source registries; all four Task194 packets/forms/imports and coordinator
ledgers; the EPIC, CaptainCook4D, and NOAA candidate registries; and the source
candidate/rights queues. It used only local frozen artifacts.

No media was decoded, no reviewer was assigned, no identity or human decision
was invented, and no parent development record was promoted.

Selection rules were:

1. replace, do not add, exactly four v3 visual slots;
2. keep exactly two slots per existing source;
3. map C03 and C04 onto their same-action v3 wrapper/peeling lineages;
4. map C02 onto the weakest newly authored CC16 visual repair;
5. map C01 onto the local CC15 visual slot so the sole far/multi CC15 slot is
   not lost;
6. count an audio pulse/cluster question as multi-hop only when the answer
   aggregates separate bounded event episodes;
7. never relabel a local span as far, a duplicate OCR route as V+S, or a
   speech-free interval as triple-modal.

## 3. Exact v4 matrix

| Slot | Source | Prospective profile | Hop / temporal | Task145 mechanism | Task194 |
|---|---|---:|---|---|---|
| `PV4-P27-01` | `P27_101` | V | one / near/local | silent | `—` |
| `PV4-P27-02` | `P27_101` | V+A | multi / near/local | explicit | `C03` |
| `PV4-P28-01` | `P28_103` | V+A | one / near/local | explicit | `C04` |
| `PV4-P28-02` | `P28_103` | V | multi / near/local | silent | `—` |
| `PV4-CC16-01` | `16_20` | V | one / near/local | silent | `—` |
| `PV4-CC16-02` | `16_20` | A | multi / near/local | explicit | `C02` |
| `PV4-CC15-01` | `15_29` | A | multi / near/local | explicit | `C01` |
| `PV4-CC15-02` | `15_29` | V | multi / far/separated | silent | `—` |
| `PV4-CC26-01` | `26_22` | V | one / near/local | explicit | `—` |
| `PV4-CC26-02` | `26_22` | V | one / near/local | silent | `—` |
| `PV4-NOAA52-01` | `cand-052` | S | one / near/local | explicit | `—` |
| `PV4-NOAA52-02` | `cand-052` | S | one / near/local | silent | `—` |

Every slot retains an inert Task145 v2 template. Mechanism balance remains
**6 silent-route-withholding / 6 explicit-channel-outage**. The fixed trigger
is zero-based action index 4; RESTORED and NO_TRIGGER require the matched
blocked prefix and byte-identical public checkpoint; the primary contrast
remains mechanism-specific RESTORED minus NO_TRIGGER under ITT. No template is
executable.

## 4. Why the four replacements are prospective only

Task193 used a frozen CLAP snapshot over complete local timelines and retained
the four leads after bounded machine review, but it performed **no human
listening**. Task194 then built reviewer-blind packets that intentionally hide
machine labels, ranks, scores, proposed questions, answers, profiles, and
expected counts.

The required Task194 order is audio-only focal review, synchronized A/V reveal,
then three bounded audio-only recurrence probes. A valid READY import requires
a concrete source-world non-speech event, an audio answerability signal,
resolved substitution/privacy/safety fields, and constraints for high/full
substitution. READY would confer authoring eligibility only.

Current Task194 state:

- candidate packets: 4;
- human identities: 0;
- human decisions: 0;
- exposure events: 0;
- distribution authorized: false;
- blank import token for C01-C04:
  `AUDIO_CANDIDATE_PRESCREEN_PACKETS_REPAIR`.

Any completed prescreener exposure must be bridged into the Task146-compatible
source ledger before construct assignments freeze. The exposed reviewer is
barred source-wide from blind alternative-evidence finding and blind
post-adjudication saturation auditing.

## 5. Honest quota recalculation

### Profiles

| Profile | Pivot-v2 target | v3 | v4 prospective hypothesis | Exact shortage |
|---|---:|---:|---:|---:|
| V | 2 | 10 | 6 | 0 (over by 4) |
| S | 2 | 2 | 2 | 0 |
| A | 2 | 0 | 2, both pending C01/C02 review | 0 nominal; 2 not human-confirmed |
| V+S | 2 | 0 | 0 | **2** |
| V+A or S+A | 2 | 0 | 2 V+A, both pending C03/C04 review | 0 nominal; 2 not human-confirmed |
| V+S+A | 2 | 0 | 0 | **2** |

There are no S+A hypotheses. Task193 found no quality-passing substantive
speech overlapping an independently answer-bearing non-speech event.

### Hop and temporal structure

| Dimension | Target | v3 | v4 | Exact shortage |
|---|---:|---:|---:|---:|
| one-hop | 6 | 9 | 7 | over by 1 |
| multi-hop | 6 | 3 | 5 | **1** |
| near/local | 6 | 11 | 11 | over by 5 |
| far/separated | 6 | 1 | 1 | **5** |

C01 and C02 are multi-hop count hypotheses because their answers aggregate
three separated event episodes. They remain near/local because their complete
spans are only 44 and 72 seconds. C03 remains a near multi-component
retrieval/wrapper chain. C04 is one local synchronized action.

To hit both 6/6 structural targets honestly, five current near slots must be
replaced by defensible far compositions: one current one/near slot must become
multi/far, and four current multi/near slots must become multi/far. One-hop/far
is prohibited.

### Fail-closed current credit

For Gate A, current human-confirmed credit is zero: 0 Task153-ready sources, 0
Task194-ready candidates, 0 normal-mode records, 0 accepted question/answer/
claim/evidence sets, 0 accepted SESs, and 0 H tiers.

## 6. Per-slot substantive and contingency audit

### `PV4-P27-01` — V

- **Question hypothesis:** After opening the lower cupboard beside the sink, what item does the wearer bring back toward the stove?
- **Answer hypothesis:** A pink-and-blue spray bottle of cleaner.
- **Claim hypotheses:** - The wearer opens the lower cupboard beside the sink. - The wearer retrieves a pink-and-blue spray-cleaner bottle and returns it toward the stove.
- **Evidence hypotheses:** - `e.p27.cleaner.v1` (vision, 1205.5-1212.0 s): The wearer opens the lower cupboard, reaches inside, takes a pink-and-blue spray bottle, and returns toward the hob.
- **Lineage:** prospective successor to `PV3-P27-01`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `PLANNED_BLANK_NOT_REVIEWED`; Task194 not applicable.
- **Prescreen contingency:** Source-level authoring may begin, but this candidate still requires fresh direct interval authoring, full-source alternative search, and normal-mode regeneration. Failure follows `REJECT_SLOT_AND_REMINE_SOURCE`.
- **Alternative-route risks:** - Distinctive bottle color/shape or package text may answer from a single frame. - Other cupboard and cleaning episodes recur in the source. - Door/cupboard sounds route the event but do not identify the object.
- **Rejection fallback:** Do not reactivate the rejected long-handled-cleaning-tool lead. Generate a fresh independent P27 candidate or replace the source.

### `PV4-P27-02` — V+A

- **Question hypothesis:** After taking the small item from the freezer, what happens to its wrapper, and what repeated non-speech sound accompanies that action?
- **Answer hypothesis:** The wrapper is torn or opened and removed while repeated crinkling/tearing sounds occur.
- **Claim hypotheses:** - A small wrapped item is taken from the freezer. - The wrapper is actively torn or opened and removed. - A repeated flexible-package crinkling/tearing sound accompanies the wrapper action.
- **Evidence hypotheses:** - `pv4.c03.vision.retrieve` (vision, 1284.0-1290.0 s): Vision binds the handled package to the just-retrieved freezer item. - `pv4.c03.vision.wrapper` (vision, 1288.0-1301.0 s): Two-handed package manipulation visually supports active opening/removal. - `pv4.c03.audio.wrapper` (audio, 1288.0-1301.0 s): A dense irregular broadband crinkle/tear cluster accompanies the action.
- **Lineage:** prospective successor to `PV3-P27-02`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `PLANNED_BLANK_NOT_REVIEWED`; Task194 `C03`: `data/rehearsal_plan/audio_candidate_prescreen_packets_v1/candidates/C03/candidate_packet.json`.
- **Prescreen contingency:** Treat C03 as eligible for fresh constrained V+A authoring only if the reviewer identifies a concrete local non-speech wrapper event, resolves the count/description, and records substitution constraints. Failure follows `FALL_BACK_TO_FRESH_V_ONLY_WRAPPER_SLOT`.
- **Alternative-route risks:** - Vision clearly shows wrapper manipulation and may be a complete substitute for the action. - Wrapper-like sounds recur near 960-976 seconds and at isolated earlier hits. - Package appearance or readable text may identify the item without the intended chain. - No human has listened; CLAP and spectrum review can confuse rustling with other flexible-material handling.
- **Rejection fallback:** If C03 audio fails but the visual chain survives, regenerate the Task192 wrapper family as V/multi/near after Task153. If the visual chain also fails, re-mine P27.

### `PV4-P28-01` — V+A

- **Question hypothesis:** What does the wearer do to the potato, and what repeated non-speech sound accompanies the action?
- **Answer hypothesis:** They peel the potato with a handheld peeler while repeated scraping sounds occur.
- **Claim hypotheses:** - The wearer works on a potato with a handheld peeler. - Repeated peeler strokes remove the potato skin. - Repeated quiet broadband scraping accompanies the peeling action.
- **Evidence hypotheses:** - `pv4.c04.vision.peel` (vision, 196.0-224.0 s): Vision identifies the potato, handheld peeler, and repeated peeling strokes. - `pv4.c04.audio.scrape` (audio, 196.0-224.0 s): Repeated quiet scraping/grating-like transients accompany the visible strokes.
- **Lineage:** prospective successor to `PV3-P28-01`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `PLANNED_BLANK_NOT_REVIEWED`; Task194 `C04`: `data/rehearsal_plan/audio_candidate_prescreen_packets_v1/candidates/C04/candidate_packet.json`.
- **Prescreen contingency:** Treat C04 as eligible for fresh constrained V+A authoring only if human review confirms a concrete repeated scrape correlated with the peeling action and records the full visual-substitution risk. Failure follows `FALL_BACK_TO_FRESH_V_ONLY_PEEL_SLOT`.
- **Alternative-route risks:** - Vision independently identifies the potato and peeling action. - Scraping-like sounds recur and CLAP confuses peeling with grating. - The paired action-plus-sound wording may be artificial if the sound is incidental or not concrete. - No human has listened and the exact audible onset/offset is unresolved.
- **Rejection fallback:** If C04 audio fails but vision survives, regenerate the original P28 peel family as V/one/near after Task153. If visual authoring also fails, use a fresh normal-mode P28 alternate.

### `PV4-P28-02` — V

- **Question hypothesis:** What sequence links the bowl of chopped vegetables to the next round of stirring?
- **Answer hypothesis:** The wearer tips the vegetables into the saucepan, adjusts a stove burner control knob, and then resumes stirring.
- **Claim hypotheses:** - Chopped vegetables are tipped into the saucepan. - The wearer turns a stove burner control knob. - The wearer resumes stirring after the adjustment.
- **Evidence hypotheses:** - `e.p28.cook.v1` (vision, 938.0-944.5 s): Chopped vegetables are tipped from a bowl into the saucepan. - `e.p28.cook.v2` (vision, 949.5-954.5 s): The wearer's hand turns a stove control knob. - `e.p28.cook.v3` (vision, 955.0-959.5 s): The wearer returns to stirring the saucepan. - `e.p28.cook.a1` (audio, 940.0-960.0 s): AST routes frying, sizzle, and stir, but human listening has not established semantic support.
- **Lineage:** prospective successor to `PV3-P28-02`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `PLANNED_BLANK_NOT_REVIEWED`; Task194 not applicable.
- **Prescreen contingency:** Source-level authoring may begin, but this candidate still requires fresh direct interval authoring, full-source alternative search, and normal-mode regeneration. Failure follows `FRESH_NORMAL_MODE_ALTERNATE`.
- **Alternative-route risks:** - Any one visible step may let a reviewer infer the routine without the full sequence. - Stirring/frying-like sounds recur and are not human-validated. - The three-step question may be overcompound if one component is nonessential.
- **Rejection fallback:** Use the Task167 P28 dry-hands-with-white-towel KEEP lead only after fresh Task153-compatible authoring and independent verification.

### `PV4-CC16-01` — V

- **Question hypothesis:** What ingredient is being stirred in the small pan before the utensil is handled with a paper towel?
- **Answer hypothesis:** Chopped red onion is being stirred.
- **Claim hypotheses:** - Chopped red onion is visible in the small pan. - The participant stirs the onion with a dark utensil. - The utensil is then moved toward or handled with a paper towel.
- **Evidence hypotheses:** - `cc4d.lead.56a0afee3a48bd76.vision.stir` (vision, 1096.0-1101.0 s): Decoded frames show chopped red onion being stirred in a small pan. - `cc4d.lead.56a0afee3a48bd76.vision.after` (vision, 1101.0-1104.0 s): Decoded frames show the utensil moved away from the pan toward a paper towel. - `cc4d.lead.56a0afee3a48bd76.audio.utensil` (audio, 1096.0-1104.0 s): AST routes dishes, pots, cutlery, and transients; no semantic listening validation was performed.
- **Lineage:** prospective successor to `PV3-CC16-01`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `NONSEMANTIC_PLAN_ONLY_FORM_AND_IMPORT_AUTHORING_NEEDED`; Task194 not applicable.
- **Prescreen contingency:** Source-level authoring may begin, but this candidate still requires fresh direct interval authoring, full-source alternative search, and normal-mode regeneration. Failure follows `REJECT_SLOT_AND_REMINE_SOURCE`.
- **Alternative-route risks:** - Ingredient appearance may be answerable from a single static frame. - Chopping/stirring/utensil sounds recur and do not uniquely bind the onion. - Person/environment cues may become source shortcuts.
- **Rejection fallback:** Re-mine 16_20 prospectively; Task193 chopping/stirring leads are unpacketized alternatives and cannot be substituted automatically.

### `PV4-CC16-02` — A

- **Question hypothesis:** How many distinct clusters of short electronic alert tones occur during the bounded preparation span?
- **Answer hypothesis:** Three distinct alert-tone clusters.
- **Claim hypotheses:** - A first cluster of short stable tones occurs near 676-692 seconds. - A second separated tone cluster occurs near 708-720 seconds. - A third separated tone cluster occurs near 736-748 seconds. - The bounded span therefore contains three distinct alert-tone clusters.
- **Evidence hypotheses:** - `pv4.c02.audio.cluster1` (audio, 676.0-692.0 s): The first repeated stable tonal stack forms one alert cluster. - `pv4.c02.audio.cluster2` (audio, 708.0-720.0 s): A temporally separated second tonal stack forms another alert cluster. - `pv4.c02.audio.cluster3` (audio, 736.0-748.0 s): A third separated tonal stack forms the final bounded alert cluster.
- **Lineage:** prospective successor to `PV3-CC16-02`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `NONSEMANTIC_PLAN_ONLY_FORM_AND_IMPORT_AUTHORING_NEEDED`; Task194 `C02`: `data/rehearsal_plan/audio_candidate_prescreen_packets_v1/candidates/C02/candidate_packet.json`.
- **Prescreen contingency:** Treat C02 as eligible for fresh A-only count authoring only if audio-first review independently finds three concrete non-speech clusters and A/V review does not reveal a complete visual/text route. Failure follows `CONDITIONAL_VISUAL_FALLBACK_OR_SOURCE_REMINE`.
- **Alternative-route risks:** - The emitting appliance is not visible in bounded frames. - Weaker beep-like detections recur elsewhere in the source. - Tonal utensil/electronic sounds may be mistaken for separate clusters. - Speech/music dominance and exact cluster boundaries remain human-unknown. - Question wording itself may expose that the expected answer is a small count.
- **Rejection fallback:** Use Task192's local hand-separation visual hypothesis only if a fresh human author can safely identify the object/action and normal-mode regeneration succeeds; otherwise re-mine or replace 16_20.

### `PV4-CC15-01` — A

- **Question hypothesis:** How many separate motor bursts does the countertop blender or food processor make during the bounded span before the participant returns to the pan?
- **Answer hypothesis:** Three separate motor bursts.
- **Claim hypotheses:** - A first sustained motor-sound burst occurs near 836-844 seconds. - A second separated motor-sound burst occurs near 848-860 seconds. - A third separated motor-sound burst occurs near 868-876 seconds. - The bounded operation therefore contains three separate motor bursts.
- **Evidence hypotheses:** - `pv4.c01.audio.burst1` (audio, 836.0-844.0 s): A sustained low-frequency motor block forms the first operation burst. - `pv4.c01.audio.burst2` (audio, 848.0-860.0 s): A separated second sustained motor block forms the second burst. - `pv4.c01.audio.burst3` (audio, 868.0-876.0 s): A separated third sustained motor block forms the final burst.
- **Lineage:** prospective successor to `PV3-CC15-01`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `NONSEMANTIC_PLAN_ONLY_FORM_AND_IMPORT_AUTHORING_NEEDED`; Task194 `C01`: `data/rehearsal_plan/audio_candidate_prescreen_packets_v1/candidates/C01/candidate_packet.json`.
- **Prescreen contingency:** Treat C01 as eligible for fresh A-only count authoring only if audio-first review independently confirms three motor bursts and A/V review does not expose a complete visual/text count substitute. Failure follows `FALL_BACK_TO_FRESH_V_ONLY_DICED_TOMATO_SLOT`.
- **Alternative-route risks:** - Vision identifies the appliance and may expose some operation periods. - Sparse machine-reviewed frames did not establish the full count, but a human A/V review might. - Weak blender-like detections at 676-708 and 1056-1064 seconds create recurrence/substitute risk. - Motor sounds may come from another appliance or continuous operation segmented by noise. - No human has listened; exact three-burst boundaries remain provisional.
- **Rejection fallback:** If C01 fails, regenerate the Task192 diced-tomato-board family as V/one/near only after Task153 and explicit duplicate accounting against the retained far tomato-state slot.

### `PV4-CC15-02` — V

- **Question hypothesis:** How do the tomatoes differ between the early sink/stove interval and the later cutting-board interval?
- **Answer hypothesis:** They appear as whole tomatoes being rinsed and set near the stove early, and as diced tomatoes on a cutting board later.
- **Claim hypotheses:** - Whole tomatoes are handled at the sink and moved toward the stove early in the source. - Diced tomatoes are visible on a cutting board beside the stovetop later in the source. - The two intervals support a same-ingredient-type whole-to-diced state-change hypothesis, not yet same-physical-object identity.
- **Evidence hypotheses:** - `cc4d.lead.96416b3c53aeb206.vision.early_sink` (vision, 36.0-38.0 s): Decoded frames show whole tomatoes held at the sink under the faucet area. - `cc4d.lead.96416b3c53aeb206.vision.early_move` (vision, 38.0-44.0 s): Decoded frames show the whole tomatoes carried to and placed beside the stove. - `cc4d.lead.96416b3c53aeb206.vision.late_diced` (vision, 632.0-640.0 s): Decoded frames show diced tomatoes on a cutting board beside the stove.
- **Lineage:** prospective successor to `PV3-CC15-02`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `NONSEMANTIC_PLAN_ONLY_FORM_AND_IMPORT_AUTHORING_NEEDED`; Task194 not applicable.
- **Prescreen contingency:** Source-level authoring may begin, but this candidate still requires fresh direct interval authoring, full-source alternative search, and normal-mode regeneration. Failure follows `REJECT_FAR_HYPOTHESIS_AND_REOPEN_POOL`.
- **Alternative-route risks:** - The early and late tomatoes may be the same ingredient type but not the same physical objects. - The late diced-tomato evidence was also used by the replaced v3 local slot. - Water and pan sounds recur and do not establish the state transition.
- **Rejection fallback:** No known same-source far composition survives. Reopen source/slot selection rather than pairing unrelated intervals.

### `PV4-CC26-01` — V

- **Question hypothesis:** What does the participant do immediately after opening the microwave?
- **Answer hypothesis:** They remove a mug and stir the mug's contents with a spoon.
- **Claim hypotheses:** - The participant opens the microwave door. - The participant removes a mug from the microwave. - The participant stirs the mug contents with a spoon after retrieval.
- **Evidence hypotheses:** - `cc4d.lead.e77b56c376c244a3.vision.open_retrieve` (vision, 921.0-925.0 s): Decoded frames show the microwave door opening and a mug being removed. - `cc4d.lead.e77b56c376c244a3.vision.stir` (vision, 925.0-928.0 s): Decoded frames show the mug contents being stirred with a spoon. - `cc4d.lead.e77b56c376c244a3.audio.microwave` (audio, 920.0-925.0 s): AST routes microwave oven and beep/bleep; semantic listening validation was not performed.
- **Lineage:** prospective successor to `PV3-CC26-01`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `NONSEMANTIC_PLAN_ONLY_FORM_AND_IMPORT_AUTHORING_NEEDED`; Task194 not applicable.
- **Prescreen contingency:** Source-level authoring may begin, but this candidate still requires fresh direct interval authoring, full-source alternative search, and normal-mode regeneration. Failure follows `REPAIR_OR_REGENERATE_LOCAL_SLOT`.
- **Alternative-route risks:** - Vision may completely answer the open-remove-stir sequence. - Microwave-like hum and beep events recur elsewhere. - The local sequence may collapse to a single action rather than a composition.
- **Rejection fallback:** A Task193 microwave-stop V+A hypothesis may be separately packetized and reviewed, but it is not an automatic replacement.

### `PV4-CC26-02` — V

- **Question hypothesis:** What small red utensil is rinsed under the faucet and then carried away from the sink?
- **Answer hypothesis:** A small red spoon, possibly a measuring spoon, is rinsed and carried away.
- **Claim hypotheses:** - A small red spoon is held at the faucet in the sink. - The participant carries the red spoon away from the sink. - The more specific measuring-spoon identity remains a human-review question.
- **Evidence hypotheses:** - `cc4d.lead.96b7ab9298d78633.vision.rinse` (vision, 460.0-464.0 s): Decoded frames show a small red spoon held at the faucet in the sink. - `cc4d.lead.96b7ab9298d78633.vision.move` (vision, 464.0-468.0 s): Decoded frames show the red spoon carried away from the sink. - `cc4d.lead.96b7ab9298d78633.audio.water` (audio, 460.0-464.0 s): AST routes water, faucet, and sink; semantic listening validation was not performed.
- **Lineage:** prospective successor to `PV3-CC26-02`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `NONSEMANTIC_PLAN_ONLY_FORM_AND_IMPORT_AUTHORING_NEEDED`; Task194 not applicable.
- **Prescreen contingency:** Source-level authoring may begin, but this candidate still requires fresh direct interval authoring, full-source alternative search, and normal-mode regeneration. Failure follows `REPAIR_OBJECT_WORDING_OR_REMINE`.
- **Alternative-route risks:** - Running water recurs and the visible faucet can substitute for sound. - Spoon versus measuring-spoon identity is unresolved. - A single object frame may bypass the rinse-and-carry sequence.
- **Rejection fallback:** A Task193 red-utensil rinse V+A hypothesis may be separately packetized; otherwise re-mine 26_22.

### `PV4-NOAA52-01` — S

- **Question hypothesis:** Which basin does the speaker identify as one of the main areas of hurricane activity?
- **Answer hypothesis:** The North Atlantic Basin.
- **Claim hypotheses:** - The speaker identifies a main area of hurricane activity. - The named area is the North Atlantic Basin.
- **Evidence hypotheses:** - `e.r017.speech` (speech, 2663.396-2671.396 s): The speaker identifies the North Atlantic Basin as a main area of hurricane activity.
- **Lineage:** prospective successor to `PV3-NOAA52-01`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `NOT_PLANNED`; Task194 not applicable.
- **Prescreen contingency:** Source-level authoring may begin, but this candidate still requires fresh direct interval authoring, full-source alternative search, and normal-mode regeneration. Failure follows `REJECT_SLOT_AND_REOPEN_NOAA_SOURCE_CHOICE`.
- **Alternative-route risks:** - Chat, slides, captions, transcripts, lower-thirds, or repeated speech may expose the basin. - Question-only geography priors may yield a plausible guess. - Webinar source and speaker identity may create metadata shortcuts.
- **Rejection fallback:** Search cand-052 for a different substantive speech proposition or reconsider cand-049 only after its independent rights and semantic repairs.

### `PV4-NOAA52-02` — S

- **Question hypothesis:** How many hurricane-formation factors does the narration state?
- **Answer hypothesis:** Three.
- **Claim hypotheses:** - The narration states that hurricane formation depends on a fixed number of factors. - The stated number is three.
- **Evidence hypotheses:** - `e.r016.speech` (speech, 1331.698-1339.698 s): The narration states that hurricane formation depends on three factors and begins listing them. - `e.r016.visual_duplicate` (vision, 1331.698-1339.698 s): The educational graphic introduces three hurricane-formation factors and may independently expose the count through OCR.
- **Lineage:** prospective successor to `PV3-NOAA52-02`; full registry and hash bindings are serialized in the matrix.
- **Reviewer packets:** Task153 status `NOT_PLANNED`; Task194 not applicable.
- **Prescreen contingency:** Source-level authoring may begin, but this candidate still requires fresh direct interval authoring, full-source alternative search, and normal-mode regeneration. Failure follows `REJECT_DUPLICATE_ROUTE_SLOT`.
- **Alternative-route risks:** - The on-screen graphic/OCR route completely duplicates the count. - Captions/transcript and repeated narration may expose the same answer. - The generic count question has a strong question-only shortcut risk.
- **Rejection fallback:** Do not restore the original three-factor list as V+S. Author a new cand-052 family or reopen the source pool.


## 7. Rights, annotation, and release boundary

### EPIC P27/P28

CC BY-NC evidence supports governed noncommercial processing, but the exact
source manifests do not grant human annotation or public
release/redistribution. C03/C04 packet readiness does not cure this hold.

### CaptainCook4D 16_20/15_29/26_22

The dataset statement records Apache-2.0 and verified consent/IRB statements,
but the operative linked consent and IRB documents are not archived. Current
authority remains restricted internal research; human annotation and public
release are unauthorized. The Task153 artifact is a nonsemantic plan only,
without a completed form/import.

### NOAA cand-052

Exact restricted acquisition and narrow machine-provisional processing exist,
but ownership/license/release and human-annotation authority are unestablished.
Public transcripts, media derivatives, redistribution, and release remain
prohibited. The source-candidate registry still records item/component rights
as unresolved.

No Task195 choice weakens these boundaries.

## 8. Gate A decision under Pivot v2

**Decision: REPAIR.**

GO fails because:

1. no completed Task153 source pass exists;
2. no Task194 human decision exists;
3. C01-C04 remain machine-expert provisional;
4. no fresh normal-mode twelve-slot registry exists;
5. V+S is short by 2 and V+S+A is short by 2;
6. multi-hop is short by 1 and far/separated is short by 5;
7. source-specific annotation/privacy/custody/release holds remain;
8. two calibrations, at least eight trained reviewers, six-role assignments,
   exposure ledgers, and assignment freeze are absent; and
9. Task145 state-surface, R/N fork, session/cache, Williams assignment, ITT,
   and metadata-only leakage interlocks remain incomplete.

NO_GO is not yet asserted because C01-C04 have a valid fail-closed human review
route and Pivot v2 still permits prospective source/slot repair. If the exact
current six sources are frozen against replacement, or reopened-source work
cannot supply V+S, V+S+A, and far/multi families under unchanged rules, the
broad matrix must become NO_GO rather than be force-labelled.

## 9. Required next actions

1. Resolve source-specific annotation, privacy, custody, and release authority.
2. Complete Task153 for all six sources.
3. Under separate authorization, complete Task194 C01-C04 and bridge exposures.
4. Apply the serialized READY/REPAIR/NO_GO and rejection fallbacks.
5. Regenerate every surviving slot in fresh normal mode with human-authored
   question, answer, claims, and evidence bounds.
6. Reopen the pool for two V+S, two V+S+A, one additional multi, and five
   additional far hypotheses.
7. Complete calibrations, train at least eight reviewers, and freeze source-
   blind assignments and ledgers.
8. Instantiate and audit Task145 only after the construct prerequisites exist.
9. Re-audit Gate A before any pilot construct-packet distribution.

## 10. Validation and boundary

The generated matrix validates:

- JSON parse: pass;
- sources: 6;
- slots: 12;
- exactly 2 slots/source: pass;
- Task193 replacements: exactly C01-C04: pass;
- prospective profiles: 6 V / 2 S / 2 A / 2 V+A: pass;
- honest hop count: 7 one / 5 multi: pass;
- honest temporal count: 11 near / 1 far: pass;
- inert mechanism templates: 6 silent / 6 explicit: pass;
- human results, H tiers, accepted SESs, and necessity assignments: zero.

This is planning integration only. It does not authorize packet distribution,
human annotation without source authority, H promotion, scientific episodes,
or public release.

## Final

`PILOT_V4_CANDIDATE_MATRIX_REPAIR`
