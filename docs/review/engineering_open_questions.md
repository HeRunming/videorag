# Engineering open questions for Pilot-0

**Recorded:** 2026-09-05  
**Implementation:** reference package `0.1.0`, schema contract `0.2.0`

The implementation fails closed where a normative rule needs information that
is not serialized by the current schemas.

1. **Backend/intervention manifest format.** The semantic-validator inputs name
   an immutable backend/intervention manifest, but no schema or lineage format
   exists for it. Consequently, derived-leak closure (`INT-002`), unaffected
   index/ranking comparison (`INT-003`), artifact-marker audits (`INT-005`), and
   byte-equivalence of observations (`REST-005`) cannot be proven from an
   episode-family file alone. The reference validator enforces every check that
   is derivable from the family and manifest; dataset-freeze tooling must reject
   a request to certify these external-artifact rules until that format exists.

2. **Validator trajectory linkage.** `SES-006` and `REST-004` require at least
   two validator trajectories, but the episode-family schema stores validator
   IDs and accepted final-set IDs rather than trajectory IDs/hashes. The package
   verifies the declared two-validator minimum and role independence. It
   validates trajectory files separately, but cannot link those files to a
   family. A family whose annotation status is `frozen` therefore receives
   `CERT-001` rather than a dataset-freeze `PASS`.

3. **Derived artifact lineage.** `PROV-002` permits a registered derivative
   lineage, but the episode schema stores transformation IDs without a
   cross-reference to acquisition-manifest `derived_artifacts`. The package
   verifies original content identity and stream hashes but cannot certify a
   transformation chain until a mapping format is frozen.

4. **Necessity-group modality target representation.** The schema stores one
   flat `required_modalities` array, while the metrics protocol describes a set
   of valid minimal missing-modality sets over alternative SESs. The validator
   interprets the existing field conservatively as the exact union of modalities
   represented by all group members. A future version should serialize the full
   set-valued target explicitly if alternatives can induce different modality
   sets.

5. **Replay hash envelope.** Tool responses contain a `response_hash`, but the
   normative text does not state whether that field participates in its own
   hash. The reference backend and validator hash the response content before
   adding `response_hash`, avoiding an impossible self-referential fixed point.
   The analogous trajectory convention omits `replay.trajectory_hash`. This
   convention should be made explicit in the next schema commentary.

6. **Fixture-versus-semantic status.** Schema-positive fixtures prove shape, not
   necessarily semantic conformance. Tests must not silently rewrite fixture
   fields before calling semantic validators. The current positive trajectory
   fixture now contains actual canonical payload, response, and trajectory
   hashes so it can be used unchanged at both layers.

7. **Validation profile boundary.** `validate_family` is a pre-annotation
   family/manifest validator. It rejects `annotation.status == "frozen"` with
   `CERT-001`, because the API has no backend/intervention-manifest or linked
   validator-trajectory inputs. A future dataset-freeze entry point must accept
   and hash those artifacts rather than treating a pre-annotation PASS as full
   certification.
