# Untouched Test Group Ledger v3.1 independent audit addendum

**Date:** 2026-10-15  
**Aggregate verdict:** **GO — CONDITIONAL**  
**Decision token:** `UNTOUCHED_TEST_GROUP_LEDGER_V3_1_AUDIT_GO_CONDITIONAL`

## Binding decision

The independent aggregate audit confirms that the hash-bound v3.1 frozen
private roster is valid as a sealed, identity-withheld roster:

- **12 / 12** production closures are closed and remain `CONDITIONAL`;
- **0** selected closures are contaminated;
- **3** independent dataset lineages are represented;
- the sealed private-roster commitment is valid;
- the public/private per-group commitments are consistent;
- the commitment-only selection rule remains valid;
- the full-governance split-lock is valid; and
- the supplemental selected commitment/closure exposure hit count is **0**.

This is not an unlock. `distribution_locked` and
`test_construction_locked` remain **true**, and `unlock_authorized` remains
**false**. All twelve groups remain conditional pending rights clearance,
exact source access, and audio preflight. No test construction, evaluation
execution, distribution, release, or scientific validity claim is authorized
by this addendum.

## Hash-bound evidence

| Evidence | SHA-256 | Audit result |
|---|---|---|
| Restricted v3.1 private ledger | `11f87b1d3d39c5ca12859b7cb5385eaae923add03075a0bd0984155cf403a149` | Frozen private roster valid; mode `0600` |
| Public v3.1 commitment | `0e5b98ef6ec19d8ac5124cce53035eccab3f75955f38e7fe0999ab850ef40f15` | Identity-free public commitment valid; mode `0644` |
| Frozen source exposure alias manifest v2 | `2c631f070505f60a49862a05d879c83e856d7dd60bca99fb34bfa16e8c064618` | Pinned manifest valid and unchanged |
| HoloAssist exposure supplement v1 | `47060b97dbf80e84c9ec4c5f7db07e2e2f841269293e402954321e825c85e890` | READY; technical timing closure only; rights/access/audio claims remain unresolved |
| Manifest-v2 supplemental audit | `148e234651b60c44a8ae23853669547fdfc14045a19662a15797b5ac5d5b2958` | PASS; strict contamination events `0`; selected hits `0` |

The sealed private-roster commitment is
`8d36f0c70233c0d3893f2b7b48bf8b1ba1dbb0de005ddded91b68a9b6b12e087`.
The full-governance split-lock is
`53135211c4a6903078cdea7bef7380fbd37bd6fbeed851f623a75709d8ad8ac2`.
The commitment-only selection-rule commitment is
`af7f101137b91949507e8e3e3e29dbbc96f16527d4259df902f6a70d7d9e7bc6`.

## Independent red-team aggregate

The audit used checked-in local governance and structured artifacts only. It
did not use network access, playable media, transcripts, captions, semantic
annotation bodies, labels, model calls, learned retrieval, or new source
probing. No selected identity, alias, private path, salt, or
commitment-to-identity mapping is published here.

The aggregate result is:

| Check | Result |
|---|---|
| Complete production closures | `12 / 12` |
| Conditional groups | `12 / 12` |
| Contaminated selected closures | `0` |
| Independent dataset lineages | `3` |
| Supplemental selected hits | `0` |
| Private/public commitment consistency | `PASS` |
| Sealed roster commitment | `PASS` |
| Commitment-only selection | `PASS` |
| Full-governance split-lock | `PASS` |
| Public non-disclosure | `PASS` |
| Required permissions | `PASS` |

## Tests and permissions

On 2026-10-15, both deterministic check commands returned their expected
markers:

- `UNTOUCHED_TEST_GROUP_LEDGER_V3_1_FROZEN_PRIVATE_READY`
- `SOURCE_EXPOSURE_ALIAS_MANIFEST_V2_SUPPLEMENTAL_AUDIT_PASS`

The three targeted local suites completed with **22 passed**:

- v3.1 ledger tests: `11`;
- HoloAssist supplement tests: `6`; and
- manifest-v2 supplemental-audit tests: `5`.

Permission checks confirmed the restricted directory at `0700`, the private
v3.1 ledger at `0600`, and the public v3.1 commitment and review at `0644`.

## Conditional boundary

The audit confirms roster integrity and exposure cleanliness only. It does
not assert that rights are cleared, media or exact source objects are
acquired, audio is available, audio preflight has passed, evaluation may run,
distribution may occur, or release is authorized. Those gates remain
fail-closed for every group.

`UNTOUCHED_TEST_GROUP_LEDGER_V3_1_AUDIT_GO_CONDITIONAL`
