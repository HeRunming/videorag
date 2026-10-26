# Untouched test group ledger v2 authoritative disposition

**Date:** 2026-10-14  
**Decision:** **PERMANENT NO-GO for v2; v3 required**  
**Decision token:** `UNTOUCHED_TEST_GROUP_LEDGER_V2_NO_GO_V3_REQUIRED`

## Binding decision

The independent v2 red-team is accepted as authoritative. It supersedes the
v2 `READY` decision, `UNTOUCHED_TEST_GROUP_LEDGER_V2_READY`, every
`CONDITIONAL_UNTOUCHED` row, every v2 group lock, and the v2 split lock for
all test-construction, authoring, evaluation, benchmark, H2, release, and
scientific uses.

All **12 of 12 selected v2 closures are contaminated**. V2 is a permanent
NO-GO, not a repair queue. It must never be used to unlock or construct a
test. It may not be patched, regenerated, rehashed, amended, partially
unlocked, grandfathered, or used as a roster or reserve list for v3.

No test groups are selected by this disposition.

No network request, playable-media access, transcript or caption opening,
semantic annotation access, model call, learned retrieval, or new source
probe was performed for this disposition. The decision is based only on
checked-in local text and structured artifacts and their SHA-256 hashes.

## Why all twelve fail

V2 applied an exposure policy that was too narrow for untouched-test
governance. The v1 exposure manifest allowed
`metadata_catalog_only`, `rights/access_preflight`, and
`failed_zero_byte_probe` to remain conditional, but it did not strictly
classify the semantics carried by:

- prior test-roster and replacement naming;
- candidate, reserve, primary, alternate, and replacement pool membership;
- ranks and deterministic participant or asset selection;
- title, course, series, domain, runtime, and producer aliases;
- target slots, likely modality routes, suitability and yield hypotheses;
- prospective source routing and audio-rich route membership;
- saved pages containing transcript text or transcript routes; and
- selection performed to fill a known roster shortfall.

V2 then selected nine v1 conditional survivors, selected the two named
lecture reserves returned by the manifest, and added `EPIC:P35` specifically
to complete the twelve-row target. This was selection from already named,
revealed, ranked, routed, or predesignated pools—not blind opaque selection
from a never-named universe.

The v1 disposition had explicitly warned that its nine conditional survivors
were not proof of untouched status and granted no authorization. V2
nonetheless recorded their selection origin as
`V1_CONDITIONAL_SURVIVOR_REVALIDATED`.

## Exact closure dispositions

Every disposition below applies to the complete closure: all participant,
person, environment, session, recording, rendition, mirror, view, encode,
excerpt, clip, frame, audio stem, caption, transcript, annotation, label,
semantic timestamp, feature, embedding, retrieval index, prompt, model
output, benchmark record, and present or future derivative.

| Slot | Closure | Exact representative | Exact exposure reason | Permanent disposition |
|---|---|---|---|---|
| `V2-TS-01` | `EPIC:P01` | `P01_101` | Previously named in the v1 test roster; inherited as a v1 survivor; also present in named EPIC candidate/reserve pools and prospective audio-rich/targeted routing pools. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-02` | `EPIC:P02` | `P02_108` | Previously named in the v1 test roster; inherited as a v1 survivor; also present in named EPIC candidate/reserve pools and prospective audio-rich/targeted routing pools. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-03` | `EPIC:P04` | `P04_123` | Previously named in the v1 test roster; inherited as a v1 survivor; also present in named EPIC candidate/reserve pools and prospective audio-rich/targeted routing pools. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-04` | `CC4D:P04` | `25_22` | Previously named in the v1 test roster and inherited as a survivor. The same person closure had already been traversed through selected person/environment aliases, including `cc4d_p04_e06` / `25_1` and replacement `cc4d_p04_e08`; changing environment aliases does not restore untouched status. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-05` | `CC4D:P06` | `16_18` | Previously named in the v1 test roster and inherited as a survivor. The same person closure had already been traversed through selected `cc4d_p06_e01` / `2_13`; changing environment aliases does not restore untouched status. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-06` | `CC4D:P07` | `16_23` | Previously named in the v1 test roster and inherited as a survivor. The exact recording was already selected in the CaptainCook4D primary technical pool, named in targeted prospecting, and used as an alternate in a prospective audio-rich route. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-07` | `ASSEMBLY101:9056` | `nusar-2021_action_both_9056-b08a_9056_user_id_2021-02-22_141934` | Previously named in the v1 test roster and inherited as a survivor. The participant and exact session were already revealed and ranked as a primary entry in the authenticated 8+2 Assembly101 candidate pool. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-08` | `ASSEMBLY101:9083` | `nusar-2021_action_both_9083-c03a_9083_user_id_2021-02-16_114344` | Previously named in the v1 test roster and inherited as a survivor. The participant and exact session were already revealed and ranked as a primary entry in the authenticated 8+2 Assembly101 candidate pool. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-09` | `ASSEMBLY101:9055` | `nusar-2021_action_both_9055-a07_9055_user_id_2021-02-09_092331` | Previously named in the v1 test roster and inherited as a survivor. The participant and exact session were already revealed and ranked as a primary entry in the authenticated 8+2 Assembly101 candidate pool. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-10` | `SG-MIT-2-003J-L01` | `repl-mit-2-003j-lecture-1` | Ranked fifth as a named reserve using producer, course, subject domain, title, and visual/speech suitability hypotheses; its dossier then recorded the exact lecture title and route state. V2 selected it directly from that named semantic reserve. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-11` | `SG-YALE-HIST202-L01` | `repl-yale-hist-202-lecture-1` | Ranked sixth as a named reserve using producer, course, subject domain, approximate runtime, title, and speech/visual hypotheses; its dossier recorded exact video/audio/transcript routes and that the saved lecture page contained transcript text. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |
| `V2-TS-12` | `EPIC:P35` | `P35_107` | Predeclared as an exact untouched replacement; present in named EPIC candidate/reserve and semantic-routing pools; then chosen specifically as the registry completion closure needed to reach twelve groups. | `CONTAMINATED_PERMANENTLY_INELIGIBLE_FOR_UNTOUCHED_TEST` |

## Nominal hashes and split lock cannot authorize construction

The rejected v2 split lock is:

`79ebe564bb499dc4a2723355c9f2f0201a26d970a9992e97ea5a7bc917c06122`

It is permanently revoked for authorization. The twelve v2 group-lock hashes
are likewise revoked.

A matching SHA-256 proves only that bytes match the payload used to compute
the hash. It does **not** prove:

- untouched eligibility;
- complete alias or exposure coverage;
- correct semantic-routing classification;
- independence from prior named pools;
- governance compliance; or
- authority to construct a test.

The hashes and split lock bind an internally reproducible roster generated
under an insufficient policy. Cryptographic consistency cannot convert
contaminated selections into an authorized untouched split. Successful
execution of the historical v2 validator or tests has the same limitation.

## Hash-bound evidence

The machine-readable disposition binds the complete evidence manifest.
Principal bindings include:

| Path | SHA-256 | Role |
|---|---|---|
| `data/rehearsal_plan/untouched_test_group_ledger_v2.json` | `9f9d12628f6e928c458db89d9a76cf46d8d602198efe90cc104e6b6bc2bc9c63` | Rejected v2 roster, origins, group locks, and split lock |
| `docs/review/untouched_test_group_ledger_v2.md` | `0140892a1a322e4b938aa3dff9750d953d89e3cb678c3c5c348c279f19a42fc0` | Rejected v2 READY report |
| `tools/untouched_test_group_ledger_v2.py` | `4fc92264c6dd6921524864b2258310ac79c2d17d8c7e62fbb2559d74b6e75aed` | Historical v2 generator/validator |
| `tooling/tests/test_untouched_test_group_ledger_v2.py` | `45b771195415cb1b0cfc3b7095b1ea202ae2884f69dbdd1c34ec6aadb33d7f9d` | Historical internal-consistency tests |
| `data/rehearsal_plan/source_exposure_alias_manifest_v1.json` | `7b67011380d877b7670e4694b2f876c8811b84a4c42ee263661ec449c89c2cbc` | Insufficient v1 exposure classification and replacement discovery |
| `docs/review/source_exposure_alias_manifest_v1.md` | `bd3c6b3e5eb5a578d981c79dec3904d52ada8c14839b9d2f8c423ff54728fe88` | Human-readable v1 policy and discovered replacements |
| `tools/source_exposure_alias_manifest_v1.py` | `12d3ac9e3ea3c7538e96fa64edfe27f0898aa1cac65d183e159ebce063e47a91` | Historical v1 manifest generator |
| `data/rehearsal_plan/untouched_test_group_ledger_v1_disposition.json` | `1995cd46ac4e01061e1b236938d46d7f3132e92d8e8f167b6f06817b7f51c5ef` | Binding warning that v1 survivors were not authorization |
| `data/rehearsal_plan/source_disjoint_scaleup_wave_v1.json` | `85546014be95a495ed2d33431e2fa29c79649b6c63640358c727fea40744e330` | Prior test roster, reserve pools, and P35 replacement naming |
| `data/rehearsal_plan/assembly_epic_access_registry_v2.json` | `22f1c3a5a59f60e94e5b8d61b3ded4f71558805502f25ac9295e8007204ef9b1` | Named and ranked EPIC candidate pool |
| `data/rehearsal_plan/captaincook4d_access_registry_v1.json` | `1a8bcf4748ec2088272a9ff5e71108a189d93de77927c8a34c7003a0e2153b06` | CaptainCook4D selected groups and person-closure aliases |
| `data/rehearsal_plan/assembly101_authenticated_registry_v1.json` | `72d2a22ed041fe86da49a0b837c1056dd3a16ff94151de83c9ec6da8d003dc71` | Ranked Assembly101 8+2 candidate pool |
| `data/rehearsal_plan/mini_pilot_replacement_candidates.json` | `37be0a9935b06f2697c7ce9b1b4934fa7327fac6041c2ef6ac521ee253fbe410` | MIT/Yale titles, courses, ranks, roles, and suitability hypotheses |
| `data/restricted/source_dossiers/mini_pilot_replacements_v1/SG-MIT-2-003J-L01.json` | `2764aca1f85e08ab9f66b41059294a26f44fb09dd1ee876f9e2c2e216aba1ede` | MIT exact title and route-dossier exposure |
| `data/restricted/source_dossiers/mini_pilot_replacements_v1/SG-YALE-HIST202-L01.json` | `e9d31aeea3625ae9e31989de686b75657cbb4648efe47e7effa521e2a4cd40c3` | Yale exact title and video/audio/transcript route exposure |
| `data/rehearsal_plan/audio_rich_vsa_acquisition_routes_v1.json` | `775af4ee30c607cb4059f5a5e35a78a327d9993c464c11c2315ea4b085246c55` | Prospective semantic-route pools naming selected representatives |
| `data/rehearsal_plan/pilot_v5_targeted_source_prospecting.json` | `da102c5bc9833e0d3dd4213848997f7155d129cbfdd0c704702149443c893778` | Targeted prospecting and named pool membership |

## Mandatory v3 requirements

V3 must be a new trust boundary and must satisfy every requirement below
before any source identity is revealed or any test construction begins.

1. **Retire v1 and v2 as selection authorities.** Their ledgers, generators,
   tests, markers, hashes, split locks, survivors, candidates, reserves, and
   selected closures are historical contamination evidence only.
2. **Use strict semantic-routing classification.** Candidate/reserve naming,
   ranking, pool membership, target-slot assignment, suitability or yield
   hypotheses, modality expectations, title/course semantics, route
   assessment, transcript-bearing page access, prospective family/question
   design, and outcome-aware completion are contaminating events for the
   complete closure.
3. **Cover pool-membership and title/course aliases.** The alias graph must
   include candidate, primary, alternate, reserve, replacement, and test-pool
   roles; titles; courses and series; producer/collection identifiers; route
   IDs; participant/person/environment/session/recording IDs; URLs, catalog
   IDs, mirrors, encodes, and derivatives. Unknown or conflicting identity is
   `NO-GO`.
4. **Create a complete governance split-lock before reveal.** It must bind
   the universe definition, all prior named exclusions, alias and exposure
   policy versions, role separation, seed or randomization commitments,
   count/lineage constraints, rights and custody gates, reveal protocol, and
   automatic fail-closed rules.
5. **Select blindly from a never-named universe.** The selector may receive
   only opaque handles and precommitted nonsemantic technical fields. It may
   not receive titles, courses, participant/person IDs, candidate labels,
   prior ranks, pool membership, route narratives, semantic suitability, or
   outcomes. Every previously named v1/v2 closure is outside the v3 universe.
6. **Seal mappings and separate roles.** Universe custody, opaque selection,
   rights/access review, alias/exposure audit, and final adjudication must be
   independent under the governance lock. The selector cannot resolve opaque
   handles.
7. **Require independent audit before reveal.** The auditor must verify the
   universe, never-named status, alias closures, semantic-routing
   classifications, exposure history, exclusions, selection transcript,
   counts, lineages, and governance lock while selected identities remain
   sealed from construction and authoring roles.
8. **Reveal only after an independent signed GO.** If any selected opaque
   handle resolves to a previously named, ranked, pooled, routed, inspected,
   or semantically characterized closure, revoke the complete proposed split
   and restart from a freshly committed universe. Do not substitute from a
   revealed reserve list.
9. **Create fresh v3 locks only after audit.** Fresh group locks and a fresh
   governance split lock must bind the complete alias graph, exposure audit,
   governance commitments, selection transcript, exclusion registry, and
   signed adjudication. Hashes themselves are never authorization.
10. **Keep gates separate and fail closed.** Eligibility, rights,
    acquisition, processing, annotation, evaluation, release, and scientific
    claims are independent gates. Untouched eligibility alone authorizes none
    of the others.
11. **Select no groups here.** This disposition is not a v3 roster and no
    v2 closure, replacement, hash, or evidence review may be treated as one.

Until all requirements are met and an independent pre-reveal audit issues a
signed GO, controlled test construction remains forbidden.

`UNTOUCHED_TEST_GROUP_LEDGER_V2_NO_GO_V3_REQUIRED`
