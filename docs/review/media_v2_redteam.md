# AV-TRACE media-backed MVP v2 final red-team review

**Review date:** 2026-09-06  
**Scope:** normative design, media-backed implementation, subprocess runtime,
validator/certificate bundle, mutation fixtures, metrics, checked-in v2
results, and two fresh post-review reruns.  
**Post-review result directory:** `mvp/results/media_backed_v2_final/`  
**Review posture:** passing tests and internally consistent reports are
necessary but not sufficient.

## Executive finding

The reviewed implementation is a valid **synthetic media-backed engineering
canary after the corrections in this review**. Searchable content and citable
observations in the canonical experiment are derived from registered decoded
MP4 bytes. The matched intervention state machine, subprocess protocol,
trajectory reconstruction, fixed-call canary, certified premature-stop
adapter, and deterministic artifact production execute end to end.

This is not a production audiovisual benchmark and does not validate the
scientific thesis on natural media or independent models. The perception stack
is a procedural-fixture recognizer; the four agents share one deterministic
fixture-oriented answer engine; the validator identities are generated roles
rather than independently authored human judgments; the runtime is not an OS
sandbox; the validator certificate binds the metadata/control backend but does
not certify the separately built media-derived index; and the required Pilot-0
metric protocol remains incomplete.

Three material defects were confirmed and fixed:

1. Public opaque handles were deterministic hashes of low-entropy private IDs
   under a public seed, permitting offline dictionary recovery of
   family/state identity.
2. Mutation episodes decoded mutated bytes for observations but searched the
   canonical media index, so mutation-time searchable content did not depend on
   the mutated bytes.
3. Validator certification checked route `required_cost` against the sum of
   stored per-step costs but did not recompute each step cost from the frozen
   backend schedule; trajectory start/replay binding was also incomplete.

Regression tests now cover these defects. Mutation runs also persist a separate
media-derived index and build record for each mutated asset.

## Execution evidence

### Test suites

The explicitly enumerated suite passed before review and again after the final
changes:

```bash
PYTHONPATH=src pytest -q \
  tests tests_mvp tests_media tests_agent_runtime tests_validation \
  tests_media_pipeline
```

The final suite contains 165 collected tests and completed with no failures.
The added regressions cover:

- non-enumerable first public episode handles across known family/state IDs;
- mutation-specific media-index construction and affected-index change;
- recomputation of validator route step cost from the backend schedule.

### Two complete post-review reruns

Two complete runs, including all mutation pairs, were executed into temporary
directories and were byte-identical:

- semantic result hash:
  `sha256:9d84c9f9f34d2b34bbbce540cc674ec3e1ca6260bf0ef292acc289d48e9a3b19`
- `report.json` file hash:
  `sha256:3f58c37f310f206394776d583e753b0656ec8ccb67f6d3080b92da45829315e0`
- `run_manifest.json` file hash:
  `sha256:d833fcb094be11ff96e5296a1cf43b1ced8a77f325fdb7ca6b15cd30efe9de44`
- `artifact_hashes.json` file hash:
  `sha256:e6da5a8ca4eb17edc5576569f89ed7b45a8b8cddafd1c74266f82d3bd7768ae8`

The first of those identical runs was copied to
`mvp/results/media_backed_v2_final/`. The prior
`mvp/results/media_backed_v2/` directory was preserved.

An independent filesystem pass recomputed all 140 entries in
`artifact_hashes.json`; no missing, extra, or mismatched entry was found.

## Confirmed defects and corrections

### RT-01 — deterministic handle dictionary attack

**Severity before fix:** high for the claimed subprocess leakage boundary.

`SubprocessEpisodeRuntime` derived its handle-map seed from the public runtime
seed plus replay seed, agent name, and the real episode ID. `OpaqueHandleMap`
then hashed the private identifier into the public handle. The algorithm and
public seed were available to the child, while family IDs, state suffixes, and
agent names came from a small enumerable set. A hostile child could therefore
precompute candidate handles and recover state/family identity.

**Correction:** public handles are now based on per-namespace first-seen
ordinals under the configured seed, not on private identifiers. Because each
process sees one episode, the first episode handle is identical for a fixed
seed regardless of the private family/state ID. Request, pointer, observation,
and backend handles remain episode-local bijections.

**Residual risk:** the fixed seed still permits stable handles and ordering
within an episode. This is acceptable for reproducibility, but it is not a
security token and must not be treated as one.

### RT-02 — mutation search used the canonical index

**Severity before fix:** high for the stated mutation contract.

The mutation experiment registered and decoded the mutated MP4 for
`inspect_clip`/`read_transcript`, but `_run_one` still received the canonical
media index. Search pointers, ranking, scores, result cardinality, and intervals
therefore came from the unmutated bytes. The tests could pass because the later
observation decode failed or changed, even though mutation-time search was
stale.

**Correction:** each mutation now rebuilds the full source-level media index
with the affected source overridden by the registered mutation bytes. The
mutation index and build record are stored under
`mutation_indexes/`. The run fails unless media-derived index records touching
the affected family change. Mutation observations then use that same
mutation-derived index.

**Result:** all three mutation contracts still pass. Blanking and muting reduce
the index from 17 to 16 records; the speech-code mutation keeps 17 records but
changes the affected speech content and index hash.

### RT-03 — validator route cost and replay fields were partly trusted

**Severity before fix:** high for the certificate claim.

The certifier verified that `required_cost` equaled the sum of stored step
costs, but did not verify that each stored cost matched the frozen backend
schedule. Thus a consistently falsified step cost and total could pass that
check. It also did not fully compare each linked trajectory's public episode
start and replay backend fields with the frozen family/backend.

**Correction:** certification now:

- recomputes every route-step cost from `backend.tool_costs`;
- validates route IDs, SES IDs, missing evidence, evidence-producing tool
  arguments, expected evidence, and required finalization;
- binds episode question, duration, available tools, budget, cost schedule,
  backend version/hash, and intervention manifest hash.

The existing checked-in certificate remains valid because its underlying
artifacts satisfy the stronger checks. The trust-anchor hash was not changed.

## Audit-question findings

### 1. Does searchable/citable content actually depend on decoded media bytes?

**Canonical run: yes, within the synthetic adapter scope.**

- `build_media_index` validates each registered source hash, scans decoded
  pixels/waveforms on a fixed grid, merges detections, and re-decodes final
  intervals.
- Search text, public previews, and observation payload content are projected
  from adapter outputs, not read from timeline, transcript, evidence, or
  family JSON.
- Runtime citable observations are decoded again from the registered media.
- Corrupt, truncated, or hash-mismatched inputs fail closed.

Evaluator-private route binding still uses annotated asset, modality, and exact
interval. It does not generate public content, but it determines whether a
decoded observation counts as registered evidence.

**Mutation run: yes after RT-02.** Search and observation decode now use the
same mutated bytes. The pre-review checked-in v2 mutation results did not meet
that stronger statement.

### 2. Does evaluator-private interval/route binding leak labels?

**No direct label field crosses the JSONL boundary after review, but the design
still has important structural leakage.**

Direct controls that pass:

- `_route_refs`, evidence IDs, real result IDs, real observation IDs, real
  episode IDs, family IDs, state roles, backend labels, intervention IDs, and
  oracle structures are absent or translated in policy-visible messages.
- Submitted registered claim IDs are discarded and remapped from exact text.
- Search previews are generic interval/modality descriptions.
- Public result scores are lexical scores over media-derived text, not route
  membership or correctness labels.
- RT-01 removed deterministic handle encoding of private IDs.

Residual channels:

- state is intentionally inferable through tool behavior: withheld results,
  typed channel errors, and restoration responses are part of the task;
- result cardinality and ordering can reveal which media records are currently
  accessible;
- intervals and content can identify the procedural source/family;
- all questions and media fixtures are public and tiny, so memorization is not
  excluded;
- `get_channel_status` restoration fires on any status request, not only a
  semantically relevant channel request;
- wall-clock timing was not equalized or measured.

These residuals do not invalidate the synthetic engineering canary, but they
prevent a claim of a side-channel-secure evaluation boundary.

### 3. Are mutation tests fair, localized, and capable of failing?

**Conditionally yes after RT-02.**

Strengths:

- fixtures are produced by localized decoded video/audio transformations;
- each fixture has its own registered media hash;
- each affected family must start with supported success and end with failure;
- a same-source control family must preserve semantic observations, answer, and
  support;
- mutation-specific search indexes are now rebuilt and persisted;
- affected media-index records must change.

Limits:

- whole-container re-encoding changes bytes outside the target interval;
- the control checks semantic outputs, not exact decoded samples or exact
  unmodified-frame hashes;
- there is one affected and one control family per mutation;
- the tests target three known procedural detectors and do not measure false
  positive rates on unseen corruptions;
- the speech mutation changes one codeword to another valid codeword, not
  natural ASR behavior.

The tests are capable of catching a disconnected media path and the stale-index
defect, but are not a general robustness or localization proof.

### 4. Are the validators independent, and are claims recomputed?

**Mechanical certificate validity: conditional pass. Human/epistemic
independence: no.**

The bundle contains two distinct generated plans:

- validator A searches and then observes chronologically;
- validator B directly observes in reverse chronological order.

The certifier recomputes schema validity, semantic family validity, trajectory
hashes, SES reachability, leave-one-out minimality, blocked insufficiency,
restoration exactness, route evidence, route step counts and costs, budget
arithmetic, denominator equality, and fixed-call behavior.

However, both validators are produced by the same generator, use the same
private graph and deterministic backend, share the same code and organization
label, and have self-declared conflict attestations. That is useful redundancy
for engineering, not independent human validation and not independent
implementation diversity.

The certificate also certifies the control-plane index
`sha256:98a040...`, not the media-derived index
`sha256:2de4b0...`. The media index is independently rebuilt and reported, but
is outside the signed validator certificate.

### 5. Is premature-stop system-independent and correctly applied?

**System-independent route source: yes. Full proof for arbitrary tested
trajectories: limited.**

- Route templates come from the certified validator denominator, not from the
  tested system's unused actions.
- The adapter recomputes observed evidence, remaining steps, and remaining
  cost from each tested trajectory.
- Infeasible zero-step BLOCKED records are excluded.
- Valid `budget_guard` handling is present.

Limitations:

- the adapter uses the consensus route templates from validator
  `decision_index == 0`, then subtracts already observed evidence and an
  already-fired status trigger. It does not match the tested trajectory to a
  certified route record at the same decision index;
- route feasibility assumes direct oracle intervals remain callable and does
  not independently execute the route from the tested backend state;
- non-trigger past actions are ignored except through remaining budget and
  observed evidence;
- the exact fixed-call variant has no matching denominator and is correctly
  excluded from canonical premature-stop metrics.

For the current monotone synthetic backend and direct-route templates, the
reported final-stop denominators are internally coherent. Generalization to
stateful tools, expiring handles, search prerequisites, or non-monotone
backends is unsupported.

### 6. Does certificate verification bind the exact live corpus and control backend?

**Yes for the generated control bundle; no for the media-derived index.**

The live loader verifies every artifact in
`mvp/generated/full/backend_manifest.json`, including source MP4 byte hashes.
The v2 verifier checks the stored certificate self-hash against a pinned trust
anchor, re-runs certification, and binds the live backend manifest hash,
control-index hash, family hashes, denominator hash, source manifests, and
fixed-call family.

The separately generated media index is clearly reported with its own hash and
build record, but the validator certificate does not bind that index. The
report correctly carries both hashes, yet downstream users must not describe
the certificate as certification of media perception or media-index semantics.

### 7. Is fixed-call restoration separated from canonical metrics?

**Yes.**

Four fixed-call RESTORED trajectories are stored separately. All trigger at
call index 0 and reach grounded success. They are not added to the 96 canonical
episode rows, state aggregates, paired family rows, dashboard, or canonical
premature-stop denominator.

Residual limitation: only one derived family and one trigger index are tested.

### 8. Can subprocess agents infer state through side channels?

**Direct identifier leakage found and fixed; complete non-inference is not
established.**

After RT-01, the first episode handle no longer depends on private
family/state identity. Result, observation, request, and backend identifiers
are ordinal-derived opaque values in a fresh per-episode process. Protected
route metadata is removed and public hashes are recomputed.

Agents can still infer operational state from intended observations and errors.
They may also exploit ordering/cardinality, public question/duration/budget,
deterministic content, and timing. Most importantly, the child is not
OS-sandboxed and inherits repository paths through `PYTHONPATH`; a malicious
submission can read dataset and evaluator files directly. Therefore this
boundary is valid only for cooperative/bundled agents, not untrusted
submissions.

### 9. Are all requested metrics present with correct denominators and missingness?

**No.**

Present:

- state grounded success;
- supported-answer success;
- stepwise and final sufficiency Brier;
- equal-count calibration data;
- BLOCKED false-sufficient and high-confidence false-sufficient rates;
- cause accuracy/Brier and modality F1/Brier;
- aggregate hop F1;
- certified premature-stop fields and explicit null rates for zero eligible
  denominators;
- triggered recovery and common-endpoint restoration gain;
- trigger-to-SES/finalize action and cost fields;
- tool calls, tool cost, inspected duration, completion, and protocol validity;
- video-cluster bootstrap summaries.

Missing or incomplete relative to `docs/spec/metrics_protocol.md`:

- Claim-Response Consistency;
- per-hop-type F1;
- first useful call rank;
- query reformulation and repeat/fallback indicators;
- evaluator-validated recovery-route allocation (the present route fraction is
  only a broad tool-category fraction);
- retained-error and correction-without-grounding rates;
- common-failure and own-failure recovery tables;
- decoded audio seconds separate from video seconds;
- input/output tokens;
- wall time/latency;
- cost per grounded success;
- source-family sensitivity;
- mechanism/modality aggregate tables with explicit denominators;
- explicit missing-pair accounting.

The dashboard's `blocked_premature_stop` is null for every system because
BLOCKED has zero eligible episodes. The separate certified table correctly
reports RESTORED denominators, but the required dashboard does not expose them.

There is also an unresolved normative conflict: D-012 and section 7 define the
primary paired quantity using state-specific grounded success, while the
implementation reports a more interpretable common supported-answer endpoint
as `paired_restoration_gain` and retains the literal normative contrast under
another name.

### 10. What remains synthetic-specific or not production-ready?

Synthetic-specific:

- fixed-layout central shape/color recognition;
- closed vocabulary burned-in text/counter recognition;
- six-symbol tonal speech codec, not ASR;
- handcrafted pulse, click, hum, and chime detectors;
- deterministic role phrases projected from decoded codewords;
- exact interval/modality annotation binding;
- exact-text claim mapping;
- one composite required claim per family;
- four sources, eight families, and a largely answer-bearing 17-record index;
- four scripted agents sharing extraction and answer logic;
- trigger-policy alignment that largely constructs the reported separation.

Not production-ready:

- no natural-speech or unconstrained-video perception;
- no learned or independently implemented agent comparison;
- no OS/container sandbox for untrusted code;
- no timing normalization or side-channel budget;
- no production validator independence;
- no media-index certificate binding;
- incomplete required metrics;
- no real-video annotation/rejection/yield evidence;
- no measured human labor, privacy review, or operational cost;
- no dependency lock or demonstrated cross-environment byte reproducibility.

## Final interpretation

The post-review system supports this narrow claim:

> A deterministic synthetic corpus can drive search and citations from decoded
> registered media bytes, exercise matched blocking/restoration through fresh
> subprocess agents, and produce reproducible validator-linked metrics.

It does not support claims about natural audiovisual reasoning, model ranking,
real-asset annotation readiness, side-channel resistance against hostile
submissions, or production-scale benchmark operation.
