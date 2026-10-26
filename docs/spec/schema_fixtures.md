# Normative schema fixtures

**Version:** 0.2.0

Machine-readable fixtures live under `docs/spec/fixtures/` and
`docs/data/fixtures/`.

## Positive fixtures

| Fixture | Expected result |
|---|---|
| `fixtures/positive_final_answer.json` | Valid against `final_answer_schema.json`. |
| `fixtures/positive_agent_action.json` | Valid against `agent_action_schema.json`. |
| `fixtures/positive_tool_response.json` | Valid against `tool_response_schema.json`. |
| `fixtures/positive_trajectory.json` | Valid against `trajectory_schema.json`, including cross-schema references. |
| `fixtures/positive_episode_family.json` | Valid against `episode_schema.json`; intended to pass semantic family rules. |
| `../data/fixtures/positive_acquisition_manifest.json` | Valid against `acquisition_manifest_schema.json`; contains no `unknown_hold`. |

## Negative fixtures

| Fixture | Expected failure |
|---|---|
| `fixtures/negative_agent_action_unknown_tool.json` | Reject unknown alias `request_channel_status`. |
| `../data/fixtures/negative_manifest_unknown_release.json` | Reject `unknown_hold` at `public_release_approved`. |

Negative fixtures are syntactically valid JSON. They are intentionally invalid
instances of their target schemas.

## Semantic adversarial fixtures

`semantic_validator_spec.md` documents negative cases for:

- an alternative SES surviving the block;
- a non-minimal SES;
- restoration changing budget;
- mismatched manifest provenance;
- unresolved rights;
- model-dependent restoration.

Those fragments define semantic failure patterns; the implementation backlog
requires full executable versions before Gate B can pass.

