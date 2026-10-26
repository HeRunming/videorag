# AV-TRACE deferred human construct-validity protocol v1.1

**Status:** protocol ready; human execution deferred  
**As of:** 2026-09-23  
**Human-reviewed families recorded by this task:** **0**  
**Human-gold families recorded by this task:** **0**

This protocol lets AV-TRACE continue machine-provisional development without
silently turning machine judgments into gold. It is designed for later offline
execution after copying a portable packet from the server.

## 1. Construct being validated

The unit is an episode **family**, not an isolated answer:

1. the question is answerable and unambiguous enough;
2. its answer is decomposed into correct atomic claims;
3. cited source-time intervals support those claims;
4. accepted minimal sufficient evidence sets (SESs), including alternatives,
   have been searched over the full source;
5. necessity groups and modality counterfactuals are valid;
6. `CLEAN`, `BLOCKED`, and `RESTORED` differ only by the registered
   intervention;
7. no direct, derived, or alternative evidence route leaks through `BLOCKED`;
8. recovery is actually feasible under the common tool/cost budget.

Correct answers alone do not establish construct validity.

## 2. Annotation tiers

| Tier | Allowed use | Promotion evidence | Forbidden claims |
|---|---|---|---|
| `P0_MACHINE_CANDIDATE` | Mining, debugging, failure inspection | Versioned machine proposal, source identity/hash, successful decode | validated support, minimality, necessity, human review, gold |
| `P1_MACHINE_CROSS_VALIDATED` | Provisional experiments and human-sample registry | At least two independent machine methods, entailment and shortcut checks, attempted alternative search | human validated/gold, proven SES minimality or modality necessity |
| `P2_MACHINE_COUNTERFACTUAL_VALIDATED` | Machine-provisional C/B/R experiments and precision estimation | P1 plus machine leave-one-out, modality drops, route closure and restoration checks | human gold or final construct validity |
| `H1_HUMAN_VALIDATED` | Human-validated analysis and candidate benchmark inclusion | Four complete independent roles, full-source blind alternative search, validator agreement on all critical constructs | adjudicated gold, population validity from a mini-pilot |
| `H2_HUMAN_ADJUDICATED_GOLD` | Gold evaluation after separate split/release gates | Independent fifth-person adjudication plus a passing blind sixth-person post-adjudication saturation audit, zero unresolved critical disagreements, every critical adjudication check passes, and no newly discovered sufficient route | redistribution unless rights permit; domain representativeness without sampling evidence |

Every tier keeps source/version hashes, machine/model or human pseudonymous
identity, timestamps, decisions, disagreement history, and parent artifact
references. Promotion never overwrites the lower-tier record.

The importer derives H1/H2. A registry cannot directly declare an eligible
record H1/H2, blank assignments have `human_gold_at_assignment=false`, and the
schemas reject invented human completion.

## 3. Human roles and blinding

Six distinct identities are required per family:

1. **Question/claim author or verifier.** Checks answerability, ambiguity,
   atomic claims, shortcuts and rights/privacy/safety. They cannot validate or
   adjudicate that family.
2. **Blind alternative-evidence finder.** Receives the source and question,
   but no machine tier, preferred evidence, preferred SES, machine confidence,
   validator decisions or adjudication. They log contiguous full-source
   coverage and every plausible alternative route before unblinding.
3. **Validator A.** Independently reviews the proposed claims, evidence,
   SES/minimality, necessity groups, modality drops and C/B/R family.
4. **Validator B.** Performs the same work without seeing A's decisions.
5. **Adjudicator.** A fifth identity who acts only after all four forms are
   frozen. They resolve conflicts from source evidence rather than majority
   vote and document evidence considered.
6. **Blind post-adjudication saturation auditor.** A sixth identity who begins
   only after adjudication is complete and frozen. They receive only the full
   source, source provenance/duration, and frozen question. They must not see
   the accepted SES ledger, preferred SES, machine ranks/confidence/tier
   evidence, validator decisions, or adjudication decisions. They log
   chronological full-source coverage and every newly discovered plausible
   route. The coordinator records the frozen adjudication file's SHA-256 in
   the audit form before release; import verifies the hash and temporal order.
   A new sufficient route reopens the family and blocks H2 until the evidence
   graph, necessity groups, and C/B/R isolation are repaired, readjudicated,
   and independently re-audited.

The portable packet gives each role a separate directory. Coordinator-only
registry/sample files must not be distributed to either blind role.

### Source-group independence and assignment freeze

Independence is enforced across the complete underlying source group, not just
within one family. Before any role packet is distributed, the coordinator
must:

1. resolve every selected family to one `source_group_id`;
2. record all known prior source-group exposures in the pre-distribution
   snapshot of `coordinator/source_exposure_ledger.json`;
3. assign all six roles for every family in
   `coordinator/reviewer_assignments.json`;
4. validate that each family has six distinct identities and that:
   - anyone exposed to preferred evidence, machine ranks/confidence,
     validator decisions, adjudication decisions, or accepted SES for any
     other family in source group \(g\) is excluded from both blind roles in
     \(g\); and
   - an adjudicator for a family in \(g\) is not the author/verifier of another
     family in \(g\);
5. freeze and hash the complete assignment ledger before distribution.

The generated blank packet is `DRAFT_NOT_DISTRIBUTABLE`; it contains no
reviewer identities. A coordinator may freeze a populated packet with:

```bash
python tools/construct_validity_packet.py \
  --output-dir /path/to/portable_packet \
  --freeze-existing-packet \
  --frozen-at 2026-09-23T23:30:00+00:00
```

After distribution, every actual access is appended to the exposure ledger
with reviewer, source group, family, role, exposure categories, timestamps,
artifact references, and a hash-chain link. Import rejects completed forms
when assignments were not frozen first, form identities differ from frozen
assignments, required exposure events are absent, the ledger/hash chain is
invalid, or a source-group role conflict is found.

## 4. Required validation work

### Question, answer and claims

- Judge answerability from the source and intended tools.
- Mark minor/major ambiguity.
- Verify every required atomic claim and detect missing or contradictory claims.
- Run question-only and metadata-only checks; the pass condition is that these
  shortcuts are **absent**.

### Evidence and alternatives

- Inspect precise intervals in source time and correct too broad/narrow bounds.
- Label `vision`, `speech`, or non-speech `ambient`; ASR/subtitles remain
  speech-derived.
- Blind-search the full source. The coverage log must start near zero, contain
  no uncovered gap over one second, and reach the source duration.
- Record duplicate/derived routes and every alternative SES. Any unresolved
  source region blocks H1.
- After adjudication is frozen, repeat full-source chronological coverage with
  the blind saturation auditor. Record search methods, queries, exact candidate
  intervals, modality and route lineage. Any new sufficient route or unresolved
  source region blocks H2 and requires reopening.

### Sufficiency, minimality and necessity

- Demonstrate that each SES supports its listed claims.
- Remove every evidence member one at a time. A minimal SES passes only when
  at least one target claim becomes unsupported for every removal.
- Reject strict supersets of another sufficient set.
- A necessity group must intersect every accepted SES for its target claims,
  and removing the complete group must break all targeted support.
- Do not infer individual necessity merely from membership in one preferred SES.

### Modality counterfactuals

Record exactly one result for each:

```text
drop_vision
drop_speech
drop_ambient
question_only
metadata_only
```

`not_applicable` or an unchanged answer is valid data, not a reason to force a
modality-necessity claim. A modality is called necessary only after accepted
alternative SESs and the relevant drop agree.

### C/B/R isolation and recovery

- `CLEAN`: at least one accepted SES is reachable.
- `BLOCKED`: the source remains sufficient, but every direct, derived and
  alternative route through the selected necessity group/channel is
  inaccessible.
- `RESTORED`: begins exactly as `BLOCKED`; a predeclared model-independent
  trigger reverses only the block.
- Tools, costs, budget, question, claims, source and unaffected outputs remain
  identical across states.
- Validate a feasible recovery route under the common remaining budget.

### Governance

Every role records rights/release, privacy and safety outcomes. A critical hold
prevents H2 and benchmark release even if the semantic construct passes.

## 5. Deferred sampling

### Immediate mini-pilot

Target **8–12 families from 5–6 source-disjoint videos**. The preferred target
is 10. The five current retained NOAA families may be included, but occupy only
three videos and are not presumed valid. Add 2–3 new sources before execution.

Priority is deterministic and preregistered:

1. ambient and `V+S+A`;
2. machine/validator disagreement;
3. learned/control ranking disagreement;
4. correct answer with wrong citation;
5. uncertain minimality;
6. multiple alternative supports;
7. pair-isolation and rights/privacy risks;
8. uncovered source/domain/modality strata;
9. at least one random low-risk control.

The sampler accepts only P-tier eligible records. Immediate mode enforces
8–12 families, 5–6 sources and at least one low-risk control.

### Scale sample

After the registry reaches **100–200 provisional families**, review 30–50
(preferred 40). Scale mode rejects registries outside that pool range and
reserves at least 20% for low-risk controls. Use the quota guidance in
`construct_validity_mini_pilot_plan.json`, and never tune selection from human
outcomes.

## 6. Statistics

Report the complete funnel:

```text
sampled → four pre-adjudication roles complete → H1 → adjudicated
        → saturation-audited → H2 / repair / reject
```

For validator A/B:

- categorical critical labels and outcome: raw agreement and Cohen's kappa;
- confidence, if analyzed: quadratic-weighted kappa;
- evidence intervals: temporal IoU and boundary error;
- set-valued evidence/SES: Jaccard/F1 plus adjudicated new-alternative count.

Estimate P0/P1/P2 human acceptance separately, with Wilson 95% intervals.
Also report:

- alternative-SES discovery per completed family;
- post-adjudication new-route discovery and saturation-pass counts;
- leave-one-out minimality pass rate;
- necessity-group pass rate;
- pair-isolation failure rate;
- rights/privacy/safety hold rate;
- active minutes by role/family and adjudication/repair cost.

The 8–12 family mini-pilot always carries
`LOW_N_MINI_PILOT_DESCRIPTIVE_ONLY`. Do not perform significance testing or
generalize tier precision. Source-clustered bootstrap intervals begin only
after at least 20 source videos.

## 7. Decision rules

### `CONSTRUCT_VALIDITY_MINI_PILOT_GO`

- 8–12 families and at least five source-disjoint videos complete;
- all six roles complete for every family;
- at least 75% reach H1 and at least 60% reach H2;
- pair-isolation failure is at most 10%;
- no unresolved critical rights/privacy/safety hold;
- no systematic minimality/modality failure over 25%.

This permits expanding the protocol, not claiming final benchmark validity.

### `CONSTRUCT_VALIDITY_REPAIR`

At least 40% reach H1, or failures are localized to repairable wording,
interval, route-closure, role, or form defects. Freeze a revised protocol
version and rerun affected families before expansion.

### `CONSTRUCT_VALIDITY_NO_GO`

Fewer than 40% reach H1 after complete review, at least half are rejected, or
systematic alternative-support/minimality/necessity/pair-isolation or
rights/privacy failures undermine the intended construct.

## 8. Portable execution

```bash
# Select a future real registry.
python tools/construct_validity_sampler.py \
  --registry REGISTRY.json \
  --output SAMPLE.json \
  --mode immediate \
  --target-size 10 \
  --source-target 5 \
  --source-max 6 \
  --seed av-trace-construct-validity-v1

# Build role-separated offline files. Use --media-mode copy only when rights
# and storage policy permit the referenced local files to be copied.
python tools/construct_validity_packet.py \
  --registry REGISTRY.json \
  --sample SAMPLE.json \
  --output-dir PORTABLE_PACKET \
  --media-mode none

# After genuine human completion:
python tools/construct_validity_import.py \
  --packet-dir COMPLETED_PACKET \
  --output RESTRICTED_IMPORT_REPORT.json
```

Import verifies immutable packet artifacts, assignment hashes, schemas,
six-person identity separation, both blind searches' chronological coverage,
validator agreement, adjudication-before-audit ordering, and saturation. An
untouched packet returns:

```text
INCOMPLETE_NO_HUMAN_DECISION
human_review_occurred=false
```

That behavior is an intentional fail-closed safeguard.
