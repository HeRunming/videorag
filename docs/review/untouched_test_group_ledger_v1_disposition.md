# Untouched test group ledger v1 authoritative disposition

**Date:** 2026-10-14  
**Decision:** **PERMANENT NO-GO for v1 test construction; v2 required**  
**Decision token:** `UNTOUCHED_TEST_GROUP_LEDGER_V1_NO_GO_V2_REQUIRED`

## Binding decision

The independent audit is accepted as authoritative and supersedes the
`READY`, `PASS`, and empty-contamination conclusions recorded by the v1
ledger. The v1 ledger, generator, Markdown report, group-lock hashes, and
split-lock hash remain historical evidence only. They may not be used to
unlock, construct, author, review, evaluate, release, or support any
untouched-test, H2, benchmark, scientific, or model-capability claim.

This is a **permanent v1 NO-GO**, not a temporary rights or acquisition hold.
V1 may not be patched, re-generated, re-hashed, amended, grandfathered, or
partially unlocked. Repository presence and successful execution of the v1
validator do not confer authorization.

The audit found pre-freeze semantic/test-design exposure for `TS-10`,
`TS-11`, and `TS-12` under aliases not reconciled by the v1 contamination
check. Their complete production closures are permanently contaminated for
untouched-test use. `TS-01` through `TS-09` are only **conditional
survivors**: the audit did not establish a dispositive closure-specific
contamination event for those nine rows, but that is not proof that they are
untouched and does not authorize use under v1.

No network request, playable-media access, transcript opening, semantic media
review, model call, or new source probe was performed for this disposition.
The decision is based only on checked-in local artifacts and their hashes.

## Why v1 fails closed

V1 froze twelve rows on 2026-10-14 and recorded zero known contamination
events. That conclusion was incomplete because the audit did not crosswalk
source-group IDs against earlier candidate IDs, stable item IDs, route IDs,
titles, catalog IDs, and production aliases.

The three public-production rows had already been used in semantic source
assessment or prospective test/family design. These are activities explicitly
forbidden by v1 itself, including candidate mining or yield assessment,
semantic prescreening, modality-route assessment, and question/evaluation
design using the group. A later freeze cannot restore untouched status.

## Contaminated rows and exact alias crosswalk

### `TS-10` — USGS Shift Curves

**V1 identity**

- source group: `EC-USGS-SHIFT-CURVES`
- exact object/session ID:
  `USGS-media-video-developing-and-applying-shift-curves-using-grsat`
- participant block: `USGS:SHIFT_CURVES_COMPLETE_PRODUCTION`
- production closure:
  `USGS:SHIFT_CURVES:ALL_RENDITIONS_AND_DERIVATIVES`

**Resolved aliases**

- `SG-USGS-SHIFT-CURVES`
- `new-usgs-shift-curves`
- `USGS-media-video-developing-and-applying-shift-curves-using-grsat`
- `USGS media slug developing-and-applying-shift-curves-using-grsat`
- *Developing and Applying Shift Curves using GRSAT*

**Exact contamination reason**

Before the v1 freeze, the same production was assigned likely family strata,
planned family slots `F05` and `F06`, route candidates, question patterns,
modality suitability, event-centric hypotheses, expected evidence routes, and
shortcut risks. It was also ranked for source acquisition/preflight on the
basis of those semantic/test-design judgments. This is pre-freeze candidate
selection and prospective family/evaluation design. It contaminates the
complete production closure even though no media payload was acquired.

**Disposition:** `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST`

### `TS-11` — NASA/JPL To the Rescue

**V1 identity**

- source group: `EC-NASA-TO-THE-RESCUE`
- exact object/session ID: `NASA+-jpl-to-the-rescue`
- participant block: `NASA_JPL:TO_THE_RESCUE_COMPLETE_PRODUCTION`
- production closure: `NASA_JPL:TO_THE_RESCUE_AND_ALL_COMPONENTS`

**Resolved aliases**

- `cand-014`
- `NASA+-jpl-to-the-rescue`
- `NASA+ post 4460 / content-id 13675 / HLS asset 15687`
- `ARVSA-R05-NASA-TO-THE-RESCUE`
- *JPL and the Space Age: To the Rescue*

**Exact contamination reason**

Before the v1 freeze, the production was semantically characterized as a
failure/workaround/recovery source, assigned expected modality routes and
likely profiles, ranked for acquisition, assessed for shortcut and event
audio risk, and assigned a prospective `B12` alternate role with explicit
GO/REPAIR/NO-GO semantic conditions. The earlier candidate registry also
recorded target-domain and modality judgments. These are pre-freeze candidate
mining, semantic route assessment, and test-design exposure.

**Disposition:** `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST`

### `TS-12` — NARA City Under the Ice

**V1 identity**

- source group: `EC-NARA-CITY-UNDER-ICE`
- exact object/session ID: `NAID:2569752`
- participant block: `NARA:CITY_UNDER_ICE_COMPLETE_PRODUCTION`
- production closure: `NARA:CITY_UNDER_ICE_AND_ALL_RENDITIONS`

**Resolved aliases**

- `NARA-BIG-PICTURE-CITY-UNDER-ICE`
- `cand-042`
- `NAID:2569752`
- *The Big Picture: City Under the Ice*

**Exact contamination reason**

Before the v1 freeze, the production was retained and ranked using semantic
domain, modality, event-centricity, dynamic-visual, machinery/environmental
audio, temporal-structure, and shortcut-risk hypotheses. The candidate and
NARA dossiers used alternate IDs for the same catalog object and recorded
prospective suitability and screening criteria. These are pre-freeze
candidate mining and semantic/test-design exposure.

**Disposition:** `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST`

For all three rows, contamination applies to every rendition, mirror, edit,
excerpt, synchronized or alternate view, audio stem, caption, transcript,
annotation, feature, embedding, prompt, model output, benchmark record, and
present or future derivative in the closure. A new alias, encode, route, or
copy does not create an untouched source.

## Nine conditional survivors

The following rows survive only as quarantined inputs to a future independent
v2 audit. They are not a usable split, may not be unlocked through v1, and may
not inherit v1 group-lock validity.

| Slot | Source group | Exact object/session | Closure key | Disposition |
|---|---|---|---|---|
| `TS-01` | `P01` | `P01_101` | `EPIC:P01:KITCHEN_AND_ALL_DERIVATIVES` | `CONDITIONAL_SURVIVOR_REQUIRES_V2_REVALIDATION` |
| `TS-02` | `P02` | `P02_108` | `EPIC:P02:KITCHEN_AND_ALL_DERIVATIVES` | `CONDITIONAL_SURVIVOR_REQUIRES_V2_REVALIDATION` |
| `TS-03` | `P04` | `P04_123` | `EPIC:P04:KITCHEN_AND_ALL_DERIVATIVES` | `CONDITIONAL_SURVIVOR_REQUIRES_V2_REVALIDATION` |
| `TS-04` | `cc4d_p04_e05` | `25_22` | `CC4D:P04:ALL_ENVIRONMENTS_AND_DERIVATIVES` | `CONDITIONAL_SURVIVOR_REQUIRES_V2_REVALIDATION` |
| `TS-05` | `cc4d_p06_e02` | `16_18` | `CC4D:P06:ALL_ENVIRONMENTS_AND_DERIVATIVES` | `CONDITIONAL_SURVIVOR_REQUIRES_V2_REVALIDATION` |
| `TS-06` | `cc4d_p07_e02` | `16_23` | `CC4D:P07:ALL_ENVIRONMENTS_AND_DERIVATIVES` | `CONDITIONAL_SURVIVOR_REQUIRES_V2_REVALIDATION` |
| `TS-07` | `assembly101_p9056` | `nusar-2021_action_both_9056-b08a_9056_user_id_2021-02-22_141934` | `ASSEMBLY101:9056:ALL_SESSIONS_VIEWS_AND_DERIVATIVES` | `CONDITIONAL_SURVIVOR_REQUIRES_V2_REVALIDATION` |
| `TS-08` | `assembly101_p9083` | `nusar-2021_action_both_9083-c03a_9083_user_id_2021-02-16_114344` | `ASSEMBLY101:9083:ALL_SESSIONS_VIEWS_AND_DERIVATIVES` | `CONDITIONAL_SURVIVOR_REQUIRES_V2_REVALIDATION` |
| `TS-09` | `assembly101_p9055` | `nusar-2021_action_both_9055-a07_9055_user_id_2021-02-09_092331` | `ASSEMBLY101:9055:ALL_SESSIONS_VIEWS_AND_DERIVATIVES` | `CONDITIONAL_SURVIVOR_REQUIRES_V2_REVALIDATION` |

The only accepted survivor finding is that the independent audit did not
establish a dispositive, alias-resolved, closure-specific contamination event
for these nine rows from the bounded local evidence. Dataset-level mentions,
pool planning, unknown human exposure, missing logs, or unresolved aliases
must still fail closed during v2 construction. Any unresolved conflict
withdraws the complete closure.

## V1 split-lock revocation

The v1 split-lock SHA-256 is:

`abec2314728f48cc9a4bf7a91145fc1610e197f06ff02d5a32852c310d74f4f4`

It is permanently **revoked for authorization and test construction**. The
hash can still verify the bytes and policy payload generated by v1, but it
cannot verify untouched eligibility because it binds three contaminated rows
and an incomplete zero-event conclusion. No downstream tool or reviewer may
treat a match to this hash, its ordered group hashes, or
`UNTOUCHED_TEST_GROUP_LEDGER_V1_READY` as a GO signal.

## Hash-bound audit evidence

The machine-readable disposition binds the complete evidence manifest. The
principal bindings are:

| Path | SHA-256 | Role |
|---|---|---|
| `data/rehearsal_plan/untouched_test_group_ledger_v1.json` | `c3082a56eff6c33b0ad8b5eec2742f7e0fe2c08c705410b5359ee84f3fc8286d` | Rejected v1 ledger and row identities |
| `docs/review/untouched_test_group_ledger_v1.md` | `0b31fa3e769cf1303fd0a71e46ebaba7e57961a5dcfe6a9bd1a3d2b97e21abbe` | Rejected v1 human report |
| `data/rehearsal_plan/source_disjoint_scaleup_wave_v1.json` | `85546014be95a495ed2d33431e2fa29c79649b6c63640358c727fea40744e330` | Frozen twelve-slot source roster |
| `data/rehearsal_plan/human_mini_pilot_source_pool_plan.json` | `75a0e83caafd9af99e6b6ecf4558d25380f37a586ae9f65e94de0bff6ff48a8e` | TS-10 alias and pre-freeze family/question design |
| `data/restricted/source_dossiers/mini_pilot_v1/SG-USGS-SHIFT-CURVES.json` | `3be888bffc21b34749428098711e55f1fcbdf086f43ad9b69212ee956f9156e8` | TS-10 alias and semantic/source dossier |
| `data/rehearsal_plan/event_centric_source_dossiers_v1.json` | `59fb92f51a44fd8619e99e418b4ae28eaa3cfb98b23757d3e9be5d9eaf5da06a` | TS-10/11/12 semantic route and shortcut assessments |
| `data/rehearsal_plan/event_centric_live_preflight_v1.json` | `bca0f36fb9b7c0f111cca50e80f6855ee53d0f70af4dfcd12dfb15759873edab` | TS-10/11 exact alias and semantic-preflight findings |
| `data/rehearsal_plan/audio_rich_vsa_acquisition_routes_v1.json` | `775af4ee30c607cb4059f5a5e35a78a327d9993c464c11c2315ea4b085246c55` | TS-11 route ID, target role, and semantic gates |
| `data/rehearsal_plan/nara_event_source_dossiers_v1.json` | `b5f060839f2b82c8cfa0db8e22207a68643e9814336cf07492cc93f210677417` | TS-12 alternate source-group and candidate IDs |
| `data/candidates/source_candidates.csv` | `b00f3a2045aafea8517f232080c87433292fe9d84430739a4c7a89b7d833923b` | `cand-014` and `cand-042` semantic candidate records |
| `data/candidates/top30_review_queue.csv` | `27f34bea47c228473a0fa214b16f7a4b4b0219c3b629644679e57e458a8bc376` | TS-11/12 review and suitability criteria |

## Mandatory v2 requirements

V2 must be a new artifact and trust boundary, not an in-place v1 repair.
Before any `READY`, unlock, or semantic access:

1. **Retire v1 as an input authority.** V1 files may be cited only as
   historical evidence. No v1 group hash, split-lock hash, readiness marker,
   or zero-event assertion may be inherited.
2. **Permanently exclude the three contaminated closures.** `TS-10`,
   `TS-11`, and `TS-12`, every alias listed above, and all mirrors,
   renditions, components, and derivatives must appear in v2's irreversible
   exclusion registry.
3. **Re-audit the nine survivors.** Each survivor must receive a fresh,
   closure-wide exposure audit covering repository artifacts, source plans,
   candidate registries, prompts, packets, logs, reviewer assignments,
   model/tool outputs, transcripts, labels, embeddings, and human access.
   Absence of evidence is not clearance.
4. **Freeze a complete alias graph first.** Before roster selection, v2 must
   bind source-group IDs, candidate IDs, participant/session IDs, stable item
   IDs, titles, URLs, catalog IDs, route IDs, mirrors, encodes, and known
   derivatives. Unknown or conflicting identity must be `NO-GO`.
5. **Construct a complete prospective roster.** Conditional survivors may be
   reselected only after passing v2. The final roster must independently
   satisfy the declared group-count and lineage-composition target; the
   nine survivors alone are insufficient. Replacements may not be selected
   using prior semantic yield, target fit, model behavior, or outcome.
6. **Use independent construction and audit roles.** The v2 roster builder
   may not self-certify untouched status. A separate auditor must verify
   aliases, exposure history, closures, exclusions, counts, and hashes before
   a readiness marker can exist.
7. **Record historical contamination.** V2 must start with nonempty,
   immutable events for the three rejected closures, including dates,
   aliases, evidence paths/hashes, exposure classes, automatic closure
   effects, and permanent dispositions.
8. **Create fresh hashes and a fresh split lock.** Every retained or new row
   requires a newly computed v2 group lock over its alias graph, exposure
   audit, closure, and evidence manifest. The v2 split lock must bind this
   disposition and must be cryptographically distinct from v1.
9. **Keep semantic access locked.** Before an independently signed v2 unlock,
   only the exhaustively enumerated nonsemantic technical checks may occur.
   Any semantic metadata, transcript, label, playable-media, embedding,
   learned-retrieval, prompt-design, or model exposure invalidates the full
   closure.
10. **Separate eligibility from rights and acquisition.** Untouched status
    does not grant acquisition, processing, annotation, evaluation, or
    release authority. Each gate must remain independently fail-closed.
11. **Require a final independent NO-GO/GO disposition.** V2 is not
    authorized merely by being generated. Its evidence hashes, alias
    coverage, event ledger, roster composition, and split lock require a
    separate independent adjudication.

Until every requirement is met, controlled test construction remains
forbidden.

`UNTOUCHED_TEST_GROUP_LEDGER_V1_NO_GO_V2_REQUIRED`
