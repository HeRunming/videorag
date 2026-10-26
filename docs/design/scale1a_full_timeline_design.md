# Scale-1A full-timeline multimodal indexing design

**Task:** 91  
**Design version:** `scale1a-full-timeline/1.0`  
**Date:** 2026-09-11  
**Decision:** `READY_TO_IMPLEMENT`

## 1. Scope, evidence status, and non-claims

Scale-1A replaces Pilot-0's 18-window retrieval universe with deterministic
full-timeline indices over all five exact NOAA assets. It keeps the six
machine-adjudicated provisional families as migration probes; it does not
promote their answers, evidence, modality roles, or minimality to human gold.

Normative labels for this stage are:

```text
MACHINE_ADJUDICATED_PROVISIONAL_SCALE1A
human_reviewed=false
gold_annotation=false
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

The implementation may establish engineering feasibility and provisional
diagnostic effects. It must not claim learned-model performance unless a
separately identified learned policy is actually run, and it must not report
modality necessity from the six families because no modality-drop
counterfactual has been human validated.

Authoritative source durations come from
`data/restricted/noaa01/manifests/noaa01_media_audit.json`, rather than the
earlier range-probe estimates:

| Asset | Duration (s) | Duration (min) | Bytes | SHA-256 |
|---|---:|---:|---:|---|
| `cand-045` | 1772.440000 | 29.5407 | 58,576,631 | `03da99e7...f9ad6` |
| `cand-047` | 1983.781800 | 33.0630 | 284,515,787 | `ddfb6c2f...84160` |
| `cand-049` | 2465.329542 | 41.0888 | 491,943,858 | `1934c31c...69e5` |
| `cand-051` | 3718.581542 | 61.9764 | 558,522,234 | `279f6b38...951b2` |
| `cand-052` | 3781.144042 | 63.0191 | 561,739,683 | `c4f5d8c6...4eef1` |
| **Total** | **13721.276926** | **228.6879** | **1,955,298,193** | — |

The five original MP4s remain restricted, immutable inputs. No extracted
frame, audio, or clip derivative may be retained after its consuming shard is
committed.

## 2. Deterministic temporal lattice and segmentation

### 2.1 Shared lattice

Each source has a source-local clock starting at zero. All persisted interval
boundaries are decimal seconds rounded to six places. The base lattice is
four seconds:

```text
cell(i) = [4i, min(4(i+1), D))
```

The last cell is retained even when shorter than four seconds. It is used for
coverage and frame sampling, but a sub-four-second terminal cell never becomes
a standalone fine/context search segment.

Segment IDs are derived only from the immutable source hash, scale, and
integer lattice index:

```text
seg.<first12(source_sha256)>.<scale>.<index:06d>
```

They must not include a question, answer, family, review ID, evidence ID,
state role, or intervention identifier.

### 2.2 Fine windows

Fine windows are suitable for localized evidence:

```text
nominal length = 8 s
stride         = 4 s
start(i)       = 4i
admission      = D - start(i) >= 4 s
end(i)         = min(start(i) + 8 s, D)
```

Thus the terminal fine window is in `[4, 8]` seconds and ends exactly at the
container duration. Counts are fixed by the audited durations:

| Asset | Fine windows |
|---|---:|
| `cand-045` | 443 |
| `cand-047` | 495 |
| `cand-049` | 616 |
| `cand-051` | 929 |
| `cand-052` | 945 |
| **Total** | **3428** |

### 2.3 Context windows

Context windows allow nearby utterances and scene context to be recovered
without re-decoding long arbitrary ranges:

```text
nominal length = 32 s
stride         = 16 s
start(i)       = 16i
admission      = D - start(i) >= 16 s
end(i)         = min(start(i) + 32 s, D)
```

The terminal context window is in `[16, 32]` seconds and ends at `D`.

| Asset | Context windows |
|---|---:|
| `cand-045` | 110 |
| `cand-047` | 123 |
| `cand-049` | 154 |
| `cand-051` | 232 |
| `cand-052` | 236 |
| **Total** | **855** |

There are **4283 temporal search segments** and at most **12,849
modality-segment records** (`4283 × 3`). Empty or low-information records
remain in the inventory with an exclusion reason but are omitted from the
search postings.

### 2.4 One-pass media sampling

Implementation must decode each source sequentially once per build attempt
and feed bounded in-memory ring buffers:

- one representative vision frame per four-second cell, at
  `min(cell_start + 2 s, D - one_video_timebase_tick)`;
- audio samples to contiguous Whisper chunks;
- audio samples to overlapping AST fine windows.

This produces **3433 sampled frames**. Fine visual embeddings are the
L2-normalized mean of their one or two cell embeddings; context embeddings
are pooled from child cells. Context aggregation never triggers another model
forward pass.

Whisper chunks are contiguous 30-second chunks:

```text
[30i, min(30(i+1), D))
```

including the final short chunk. There are exactly **461 Whisper calls**.
Final chunks shorter than five seconds are retained in provenance but become
searchable only if the ASR quality gate passes.

AST is evaluated once for each fine window: **3428 AST calls** representing
27,413.276926 seconds of overlapped model input. Audio is not decoded afresh
per call; windows are emitted from the shared sequential audio buffer.

## 3. Versioned observation layers

Every layer has a frozen configuration, input-source hashes, code hash,
runtime manifest, and output hash.

### 3.1 Speech layer

- Model: `openai/whisper-tiny.en`
- Revision: `87c7102498dcde7456f24cfd30239ca606ed9063`
- Weight SHA-256:
  `db59695928ded6043adaef491a53ef4e12da9611184d77c53baa691a60b958ad`
- Local-only inference, 16 kHz mono, greedy decoding, no sampling.
- Generation settings inherit the Task-84 manifest except that timestamped
  chunks/segments must be persisted. Word timestamps are optional; segment
  timestamps are mandatory.
- Timestamped ASR pieces are intersected with fine/context windows to create
  searchable text. The complete text for an inspected interval is citable
  only after source-hash verification and `read_transcript`.
- Empty text, non-finite scores, known one-token tail hallucinations, or
  failed decoding are inventory records but not searchable.

### 3.2 Ambient layer

- Model: `MIT/ast-finetuned-audioset-10-10-0.4593`
- Revision: `f826b80d28226b62986cc218e5cec390b1096902`
- Weight SHA-256:
  `ae0c1e2ad4e1381d851fa9bf298ba13ebc9c5a914cdee2dbe427a6583869924d`
- 16 kHz audio; sigmoid probabilities; persist top 15 class IDs, canonical
  labels, and scores for each fine window.
- Context observations are deterministic max/mean aggregates from child fine
  windows and require no additional AST inference.
- Generic classes (`Speech`, `Music`, `Inside`, `Outside`) receive the same
  frozen discount policy across all sources. A record with only discounted
  generic classes below threshold is low-information and not searchable.
- AST output is explicitly a **provisional event-model observation**, not
  proof that a human would hear the event.

### 3.3 Vision layers

Two layers must remain distinguishable:

1. `opencv-routing/1.0`: deterministic luminance, color histogram, edge,
   motion/change, blank-frame, and optional pinned Haar face-presence
   features. These are suitable for quality/routing filters, not semantic
   descriptions.
2. `clip-visual/1.0`: sampled-frame and text embeddings from
   `openai/clip-vit-base-patch32` at revision
   `3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268`. This model is not present in
   the current repository; implementation must acquire it into restricted
   storage, freeze every file hash, run local-only, and fail closed if the
   exact revision cannot be verified.

No generated image caption is part of Scale-1A v1. Existing Codex visual
descriptions are used only as evaluator-private migration hypotheses; they
must not be copied into the full-timeline searchable index.

### 3.4 Joint temporal binding

Binding is purely temporal and label-free. Records sharing a source and
overlapping four-second cells carry a `binding_group_id` derived from source
hash and cell index. Context records list child binding groups. The binding
layer may support rank fusion or a follow-up search near an already found
interval. It may not consume question, answer, claim, evidence, family,
review, or intervention fields.

### 3.5 Visibility classes

| Object | Searchable | Citable | Evaluator-private |
|---|---|---|---|
| CLIP vectors and generic pointer preview | Yes | No | No |
| Timestamped Whisper text in search postings | Yes | No | No |
| AST class labels/scores above frozen gate | Yes | No | No |
| `inspect_clip` exact decoded observation | No | Yes | No |
| `read_transcript` exact interval text | No | Yes | No |
| Machine answer/support hypotheses | No | No | Yes |
| Alternative-support and negative labels | No | No | Yes |
| C/B/R state, hooks, family IDs, evidence IDs | No | No | Yes |
| Filename, title, URL, review ID, raw metadata | No | No | Yes |

Search pointers expose only an opaque result ID, modality, interval, score,
scale, and a generic preview such as `"vision candidate 1012.000-1020.000s"`.
They never expose a transcript excerpt, AST labels, generated caption,
filename, title, evidence role, or answer-related field. Content becomes
citable only through an observation tool and after exact source verification.

## 4. Frozen indices and APIs

### 4.1 Per-modality indices

- **Speech:** Unicode NFKC, case-folded `[a-z0-9]+` tokenizer,
  `bm25-okapi/1.0`, `k1=1.2`, `b=0.75`; document length and IDF computed only
  from searchable full-timeline speech records.
- **Ambient:** canonical AudioSet label tokens and frozen synonym expansion,
  weighted sparse cosine over discounted AST probabilities. Query expansion
  is versioned and cannot contain family answer aliases.
- **Vision:** CLIP text-to-image cosine similarity over L2-normalized pooled
  float16 vectors; similarity accumulation/ranking in float32.
- **Fused:** weighted reciprocal-rank fusion,
  `RRF(k=60)`, equal modality weights, deduplicated by source and overlapping
  binding group. A modality absent from a query contributes no rank.

Every ordering uses:

```text
descending score
ascending source_id
ascending start_us
ascending end_us
ascending segment_id
ascending modality
```

Rounded display times never participate in ranking; integer microseconds do.

### 4.2 Search modes

- `source_scoped`: restrict to the episode's registered source. This is the
  primary paired comparison against Pilot-0.
- `cross_source`: search all five sources, exposing only an opaque source
  handle. This is a secondary stress test and must not be pooled with the
  primary result.

Scale-1A backend protocol `0.3.0` retains:

```text
search_visual
search_speech
search_ambient_audio
inspect_clip
read_transcript
get_channel_status
finalize
```

and adds `search_fused` for a query carrying a non-empty set of requested
modalities. Existing `0.2.0` clients remain valid when they do not call it.

All search calls accept `query`, `top_k` (1–20), `time_range`,
`exclude_result_ids`, and `search_scope`. A search result contains:

```json
{
  "result_type": "search_pointer",
  "result_id": "opaque deterministic ID",
  "source_ref": "opaque source handle",
  "interval": {"start_s": 0.0, "end_s": 8.0},
  "modality": "vision",
  "scale": "fine",
  "score": 0.0,
  "preview": "vision candidate 0.000-8.000s"
}
```

At `inspect_clip`/`read_transcript` time, the backend:

1. resolves the pointer inside the restricted process;
2. verifies path confinement, file size, and full SHA-256 against the
   acquisition manifest (cached only after inode/size/mtime agreement);
3. seeks and decodes the registered interval with PyAV;
4. verifies requested streams, finite samples/frames, and interval coverage;
5. returns a content-bearing citable observation and payload hash;
6. deletes all temporary media buffers.

### 4.3 Freeze and replay

The frozen manifest includes source and model hashes, code revision/tree hash,
runtime package versions, segmentation parameters, all observation-layer
hashes, searchable/excluded record counts with reasons, tokenizer/ranker
configuration, synonym tables, vector dtype/dimension, tie breaker, and
Merkle-style hashes for each source/modality/scale shard and the root index.

A deterministic replay rebuild must reproduce:

- every segment boundary and ID;
- every non-neural feature;
- every model observation within exact serialized outputs;
- every vector file byte-for-byte or, if the device kernel is not bitwise
  deterministic, a separately frozen canonical CPU serialization whose
  cosine scores agree within `1e-6` and whose complete ranking is identical;
- the root index hash and a fixed query-suite ranking hash.

## 5. Hard negatives and leakage controls

Negative labels are attached only after the content index is frozen. They are
evaluator-private and cannot affect searchable text or embeddings.

### 5.1 Negative classes

1. **Same-video near-temporal:** same source and within 120 seconds of a
   provisional support interval, but not overlapping its 32-second exclusion
   neighborhood.
2. **Same-topic lexical:** high speech BM25 overlap with the question while
   lacking accepted support.
3. **Same-modality semantic:** high CLIP or AST similarity within the same
   modality while lacking accepted support.
4. **Cross-modal mismatch:** a strong result in one modality whose temporal
   partner does not support the required provisional claim.
5. **Repeated/duplicate content:** intros, webinar layouts, recurring slides,
   repeated montage shots, or repeated utterances.
6. **Title/credit/metadata shortcut:** opening/closing cards, filenames,
   program title, speaker labels, and other source-identity cues.

### 5.2 Admission and exclusion

A candidate negative is admitted only when all checks pass:

- source bytes and segment provenance verify;
- it does not overlap any provisional or discovered alternative support
  interval expanded by 16 seconds on each side;
- for near-temporal negatives, center distance is at least 32 seconds and at
  most 120 seconds;
- normalized answer aliases are absent from visible ASR/OCR/event text;
- two independent machine checks find no answer support in the exact decoded
  interval; disagreement makes it `unsafe_negative`, not a negative;
- duplicate clusters are not split between provisional support and negative
  without explicit alternative-support adjudication;
- title/credit/metadata records are tagged and cannot count as ordinary hard
  negatives or accepted evidence.

OCR is not a searchable layer in v1. If an implementation adds OCR, it must be
versioned separately and the answer-alias and title-card contamination audits
must be rerun.

### 5.3 Contamination tests

Fail the build or affected family if:

- any searchable/index payload contains a family, evidence, claim, review,
  state, or intervention ID;
- any visual/ambient pointer exposes transcript or answer-bearing labels;
- retrieval ranking changes when evaluator annotations are removed;
- a classifier can predict state role from response shape, IDs, errors,
  counts, latency bucket, or filenames above chance on the complete frozen
  corpus;
- an answer-only/title-only/filename-only query retrieves provisional support
  through metadata rather than media-derived observations;
- BLOCKED leaves a direct, context, fused, duplicate, or alternative route to
  the withheld support.

## 6. Migration of the six provisional families

Legacy evidence is mapped to every same-modality fine/context segment with
positive temporal overlap. The primary matched segment is the fine segment
with maximum IoU, with deterministic tie-breaking. Current best fine matches
are:

| Family | Legacy interval | Primary fine interval | Coverage of legacy |
|---|---|---|---:|
| `r004` | 1011.842–1019.842 | 1012–1020 | 0.98025 |
| `r007` | 0–8 | 0–8 | 1.00000 |
| `r011` | 3055.773–3063.773 | 3056–3064 | 0.97163 |
| `r014` | 443.899–451.899 | 444–452 | 0.98738 |
| `r016` | 1331.698–1339.698 | 1332–1340 | 0.96225 |
| `r017` | 2663.396–2671.396 | 2664–2672 | 0.92450 |

These mappings are routing hypotheses, not proof of exact support.

### 6.1 `noaa01-r004-surf-av` — retain, high-risk ambient candidate

- **Expected route:** visual search for a person and water conditions;
  inspect the visual interval; use its time range for ambient search; inspect
  audio in the bound interval.
- **Distractor pressure:** repeated surf/coastal footage and speech-dominated
  AST labels elsewhere in `cand-049`; nearby safety narration is a strong
  lexical mismatch trap.
- **Question-derived queries:** `"person water conditions near shore"`,
  `"environmental sounds same interval water"`, and temporal-bound ambient
  follow-up. Do not seed `"surf"`, `"ocean"`, `"waves"`, or `"wind"` as hidden
  answer aliases.
- **CLEAN:** both provisional routes must be reachable in top 20 and within
  the unchanged budget.
- **BLOCKED:** disable the entire ambient channel, including fine, context,
  fused, and derived observations.
- **RESTORED:** `get_channel_status(["ambient"])` restores before response;
  ambient evidence must then be searched and inspected anew.
- **No-trigger:** identical action budget with restoration hook disabled.
- **Failure:** no visual anchor, no specific AST event at the exact interval,
  an unblocked ambient alternative, or answer support only from speech.
- **Disposition:** retain only as a machine-provisional ambient stress case;
  exclude from modality-necessity scoring.

### 6.2 `noaa01-r007-opening-plastic-waste` — rewrite

- **Rewrite:** `"Which discarded material appears in the introductory
  montage?"` The prior phrasing and start position are vulnerable to an
  `"opening"` shortcut; report a separate result with temporal terms masked.
- **Expected route:** question-derived visual search, inspect the 0–8 second
  montage.
- **Distractor pressure:** repeated debris/plastic imagery throughout
  `cand-051`, opening title frames, and lexical references in speech.
- **Queries:** `"discarded material introductory montage"` and `"waste
  material shown in montage"`; no answer alias.
- **CLEAN:** accepted visual segment appears by top 20 in both ordinary and
  temporal-term-masked diagnostics.
- **BLOCKED:** withhold all overlapping fine/context/fused routes and all
  duplicate shots supporting the answer.
- **RESTORED:** second distinct visual query triggers restoration before
  dispatch; returned evidence must be inspected.
- **No-trigger:** the same two searches cannot reach the withheld/duplicate
  support group.
- **Failure:** only timestamp/order retrieves it, alternative plastic footage
  is not catalogued, or withholding leaves a duplicate answer route.
- **Disposition:** rewrite and retain only if the anti-shortcut and
  alternative-support audit passes; otherwise exclude.

### 6.3 `noaa01-r011-bag-by-fence` — retain

- **Expected route:** visual search for a walking person beside a fence,
  followed by inspection.
- **Distractor pressure:** many people/webinar panes, other waste objects, and
  speech mentioning a plastic bottle in the same interval.
- **Queries:** `"person carrying object beside fence"` and `"walking beside
  fence carrying something"`; do not seed `"bag"`.
- **CLEAN:** visual support is reachable by top 20.
- **BLOCKED:** suppress all fine/context/fused records overlapping the support
  group and any duplicate shot.
- **RESTORED:** a second distinct visual formulation triggers restoration;
  evidence must be reacquired and inspected.
- **No-trigger:** same sequence cannot recover support.
- **Failure:** speech alone leaks the answer, duplicate shots remain, or the
  object is not resolvable in tool-time decoded frames.
- **Disposition:** retain, subject to exact-frame visibility check.

### 6.4 `noaa01-r014-aircraft-storm-view` — rewrite

- **Rewrite:** `"What view is shown during the segment about collecting
  observations inside a hurricane?"` This removes the unsupported implication
  that a separately indexed caption is authoritative.
- **Expected route:** speech search may localize the hurricane-observation
  segment; temporal binding then routes to visual inspection. A direct visual
  route is also recorded.
- **Distractor pressure:** many storm/cloud graphics, aircraft references,
  title montage, and other weather footage in `cand-052`.
- **Queries:** `"view shown collecting observations inside hurricane"` and
  `"hurricane observation segment visual scene"`.
- **CLEAN:** at least one direct visual route and one speech-to-visual bound
  route must be measured, without requiring both as necessary.
- **BLOCKED:** suppress every visual support route, its contexts, fused
  records, and duplicate aircraft/cloud shots; speech localization may remain
  but cannot become citable visual support.
- **RESTORED:** second distinct visual search restores before dispatch, then
  inspection reacquires support.
- **No-trigger:** speech localization alone must not satisfy the visual claim.
- **Failure:** only title/metadata/OCR provides the answer, no clean route by
  top 20, or alternative aircraft footage remains.
- **Disposition:** rewrite and retain if decoded-frame and duplicate audits
  pass; otherwise exclude.

### 6.5 `noaa01-r016-three-factors-vs` — retain as corroboration, not necessity

- **Expected route:** speech search for stated formation factors; transcript
  read; temporal-bound visual search/inspection of the graphic.
- **Distractor pressure:** repeated hurricane explanations, other numbered
  lists, and `r017` hurricane speech in the same source.
- **Queries:** `"how many hurricane formation factors stated"`,
  `"formation factors educational graphic"`.
- **CLEAN:** speech and vision candidate support are both reachable by top 20.
- **BLOCKED:** disable speech/transcript globally, including speech
  contributions to fused records; the visual route remains visible.
- **RESTORED:** `get_channel_status(["speech","transcript"])` restores before
  response; transcript evidence must be searched/read again.
- **No-trigger:** speech cannot return.
- **Failure:** number is unavailable in decoded frames/transcript, a remaining
  modality independently answers through an uncatalogued route, or temporal
  binding uses evaluator-private IDs.
- **Disposition:** retain as a cross-modal corroboration/routing family.
  Report all-evidence metrics as hypothesis-conditioned and modality recall as
  null.

### 6.6 `noaa01-r017-north-atlantic-basin` — retain

- **Expected route:** speech search and transcript read.
- **Distractor pressure:** repeated hurricane/basin discussion, `r016`, and
  generic webinar speech.
- **Queries:** `"speaker main area hurricane activity basin"` and `"which
  basin main hurricane activity"`; do not seed `"North Atlantic"`.
- **CLEAN:** transcript support reachable by top 20.
- **BLOCKED:** disable speech/transcript and every speech contribution to
  context/fused records.
- **RESTORED:** status call restores speech/transcript; a new search/read must
  reacquire evidence.
- **No-trigger:** no speech result or citation can be produced.
- **Failure:** title/metadata supplies the basin, no full-index route by top
  20, or an uncatalogued alternate utterance remains accessible in BLOCKED.
- **Disposition:** retain, subject to full-source alternative-utterance scan.

### 6.7 Common intervention invariants

For every retained family:

1. CLEAN, BLOCKED, and RESTORED use identical immutable indices, ranking,
   budgets, tool costs, result shapes, and deterministic seeds.
2. CLEAN has at least one reachable provisional support set.
3. BLOCKED suppresses direct, context, fused, duplicate, and accepted
   alternative routes, but retains at least five admitted hard negatives.
4. RESTORED is byte-for-byte BLOCKED before the registered trigger.
5. The trigger is independent of model identity and answer content.
6. Post-trigger availability equals CLEAN, but prior pointers do not silently
   become citable: the route must be searched and observed again.
7. A matched no-trigger control cannot recover.
8. Budgets remain Pilot-0's `10 steps / 12 cost`, with a secondary
   `20 steps / 24 cost` sensitivity run reported separately.

A hard-negative-displacement shadow condition deterministically demotes the
first accepted result below top K on the first eligible query and substitutes
an admitted negative. It does not alter later rankings. It measures recovery
from a plausible retrieval miss and is not pooled with C/B/R.

## 7. Evaluation

Task-90 definitions of Evidence Recall, All-Evidence Success, Answer Score,
Citation F1, Supported-Claim Rate, Success@Budget, Premature Stop, and Recovery
remain normative. `Modality Recall` remains null until modality necessity is
validated.

Additional full-timeline metrics:

- **Recall@K:** for `K ∈ {1,5,10,20}`, the fraction of evaluator-registered
  provisional evidence units covered by a same-modality retrieved segment.
  Coverage requires temporal IoU at least 0.5 or coverage of the registered
  interval at least 0.8. Accepted alternative support counts.
- **Rank of first accepted evidence:** minimum rank of any accepted support
  route; `null` when no accepted support exists in the indexed corpus and
  `no_hit` when support exists but is not retrieved within the evaluated
  depth. Report hit rate and conditional median rank separately.
- **All-Evidence@K:** one if at least one complete accepted support set is
  covered by the union of top-K results across its required provisional
  routes; zero otherwise. It is hypothesis-conditioned, not minimality.
- **Inspected-video fraction:** duration of the union of unique inspected/read
  intervals divided by source duration. Repeated/overlapping inspection is
  counted once; no inspection gives zero.
- **Distractor burden:** inspected observations that support no registered or
  accepted alternative claim divided by all inspected observations; null when
  there are no inspections.
- **Query reformulation gain:** best evidence recall after searches 2..N minus
  recall after the first search, eligible only for traces with at least two
  content searches.
- **Cross-modal routing switches:** count of changes in modality between
  consecutive content-search/observation actions; also report per content
  action. Status/finalize actions are ignored.
- **Bounded-to-full degradation:** paired full-timeline value minus frozen
  Pilot-0 value for the same family, state, policy, budget, and metric. Missing
  pairs are null and never imputed.
- **Recovery after hard-negative displacement:** successful supported
  finalizations after the registered first-query displacement divided by
  eligible displaced trajectories. Also report evidence reacquisition and
  answer recovery separately.

Alternative support sets are evaluator-private, immutable after evaluation
freeze, and are credited symmetrically in bounded/full runs. Discovering a new
credible alternative invalidates the affected comparison until both indices
and interventions are regenerated.

Every result row records numerator, denominator, eligible family/source
counts, scope, state, policy, K/budget, and eligibility reason. With only six
families and three family-bearing sources, every aggregate carries
`LOW_N_DESCRIPTIVE_SCALE1A`. Cross-source and source-scoped results, nominal
and sensitivity budgets, and rewritten/original questions are never pooled.

## 8. Compute, storage, and execution stages

### 8.1 Deterministic workload

| Item | Count / amount |
|---|---:|
| Source media | 5 files, 1,955,298,193 bytes |
| Source duration | 13,721.276926 s (3.8115 h) |
| Four-second cells / vision frames | 3433 |
| Fine windows / AST calls | 3428 |
| Context windows | 855 |
| Whisper chunks/calls | 461 |
| Maximum modality-segment records | 12,849 |
| AST overlapped inference audio | 27,413.276926 s (7.6148 h) |
| Whisper inference audio | 13,721.276926 s (3.8115 h) |
| New CLIP frame forwards | 3433 |

Estimated persisted derived storage, excluding source media and model
snapshots:

- float16 512-D CLIP frame vectors: about 3.52 MB;
- float16 512-D pooled visual vectors for 4283 segments: about 4.39 MB;
- sparse AST top-15 labels/scores: under 8 MB target;
- ASR text/timestamps and BM25 postings: under 40 MB target;
- segment manifests, fusion maps, hashes, diagnostics: under 80 MB target;
- checkpoints, query suite, migration and evaluation results: under 120 MB
  target.

The planned total is **under 256 MiB**, with a hard fail at **512 MiB** of new
derived artifacts unless an explicit revised storage plan is recorded. The
CLIP snapshot has a separate **1 GiB acquisition cap**; its exact downloaded
bytes and every file hash must be recorded before inference.

Resource reservation:

- CPU: 8–16 cores, 16–32 GiB RAM, sequential PyAV decode;
- GPU: one CUDA device with at least 8 GiB, models loaded one at a time;
- initial reservation: 12 GPU-hours and 24 CPU-hours for all-five indexing,
  with no claim that these are measured runtimes;
- CPU-only fallback: allowed for smoke tests, not for an unbounded all-five
  run; reserve at most 72 wall-hours and stop for re-estimation if exceeded.

The smoke test must measure calls/second, peak RAM/VRAM, bytes/record, and
decode overhead. The all-five projection is recomputed from those
measurements; execution pauses if projected GPU-hours exceed 12, CPU-hours
exceed 24, peak RAM exceeds 32 GiB, VRAM exceeds 8 GiB, or derived storage
exceeds 512 MiB.

### 8.2 Stages

1. **Dry-run inventory:** verify all five byte sizes/hashes/streams/durations;
   materialize segment tables only; assert the exact counts above.
2. **Small-shard smoke:** first 120 seconds of `cand-049`; 30 fine, 7 context,
   30 frames, 4 Whisper chunks, and 30 AST calls. Exercise every layer,
   checkpoint, API, empty-record path, and cleanup.
3. **One-video pilot:** all of `cand-049`; expected 616 fine, 154 context,
   617 frames, 83 Whisper calls, and 616 AST calls. Run `r004` C/B/R and
   displacement control.
4. **All-five build:** process one source and one model layer at a time;
   atomically commit source/modality shards.
5. **Migration run:** execute all retained families in source-scoped mode,
   then the separate cross-source stress run.
6. **Deterministic replay:** rebuild into a fresh restricted directory and
   compare segment IDs, outputs, index hashes, fixed query rankings, and
   family trajectories.
7. **Independent red-team:** recompute counts/hashes/metrics, inspect leakage
   and negative admission, verify no derivatives, and challenge every
   migration/disposition and C/B/R proof.

Checkpoint keys are
`source_sha256/layer_version/scale/shard_index/config_hash`. Writes use a
temporary file, fsync, hash verification, and atomic rename. A restart reuses
only a shard whose complete key, record count, byte count, and hash match;
partial shards are deleted. No checkpoint contains decoded media.

## 9. Go/No-Go

### `SCALE1A_ENGINEERING_GO`

All are required:

- exact source verification and exact planned segment counts for all five;
- all observation layers and all frozen indices build within caps;
- no persisted media derivatives or restricted-data leakage;
- deterministic API, tie-breaking, hashes, restart, and replay pass;
- at least four of six families remain executable, including at least one
  speech family and one cross-modal/ambient candidate;
- each retained family passes CLEAN/BLOCKED/RESTORED and no-trigger
  invariants with at least five admitted hard negatives;
- Task-90 and full-timeline metrics recompute without mismatch.

### `SCALE1A_DIAGNOSTIC_GO`

Requires `SCALE1A_ENGINEERING_GO` and all of:

- full-timeline retrieval yields a measurable paired effect, not merely a
  larger index: at least two retained families show non-zero
  bounded-to-full degradation in Recall@5, All-Evidence@5, inspected-video
  fraction, or distractor burden;
- at least one eligible family recovers after deterministic hard-negative
  displacement, while its matched no-recovery control does not;
- at least two policies differ on at least two of Acquire, Ground, and Act,
  across at least two retained families;
- at least one correct-answer trajectory has incomplete evidence/citation or
  one complete-evidence trajectory fails answer/grounding, demonstrating
  diagnostic separation;
- effects survive the temporal-shortcut-masked `r007` diagnostic and are not
  explained solely by source identity, title cards, metadata, or one family;
- all claims are descriptive, paired, machine-provisional, and low-N.

### `SCALE1A_DIAGNOSTIC_INCONCLUSIVE`

Use when engineering passes but diagnostic criteria do not—for example all
systems degrade identically, no policy separation appears, too many families
fail migration, or effects are limited to cost/index size.

### `SCALE1A_NO_GO`

Use when engineering invariants fail, source/index replay is not
deterministic, leakage is found, BLOCKED retains support, RESTORED cannot
reacquire it, resource caps are exceeded without an approved revision, or
fewer than four families remain.

Regardless of the Scale-1A outcome, report:

```text
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

until answers, support/alternatives, counterfactual minimality, rights/release,
and the final test set receive the required human validation.

## 10. Design decision

`READY_TO_IMPLEMENT`

The plan has exact source-derived counts, bounded resource gates, a
label-independent full-timeline index, explicit migration rules for all six
families, strict intervention semantics, paired diagnostics, and fail-closed
scientific claims. Implementation must not reinterpret the prose; the
machine-readable plan is normative where values are duplicated.
