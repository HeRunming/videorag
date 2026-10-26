# AV-TRACE agent subprocess boundary report

**Review date:** 2026-09-06  
**Scope:** subprocess serialization boundary, baseline adapters, adversarial
tests, and normative trajectory reconstruction.

## Result

Implemented a one-process-per-episode JSONL runtime under the requested owned
paths. No normative document or existing MVP agent/backend/experiment source
was modified.

The runtime closes the specific in-process introspection weakness identified by
the scientific red-team: policy code no longer receives an object that holds
references to the evaluator session, family, backend, index, intervention
runtime, or oracle structures.

## Architecture

Evaluator-side code:

- launches one child for one episode;
- creates a seed-scoped opaque ID namespace;
- sends a reduced episode-start payload;
- validates public agent actions;
- privately translates IDs and validates the translated normative action;
- executes the existing fixed backend;
- validates the private response;
- strips evaluator-private route references;
- translates all policy-visible IDs and recomputes public payload/response
  hashes;
- sends a schema-valid public tool response;
- ignores submitted registered claim IDs and applies the evaluator-private
  exact-text claim mapper;
- reconstructs real action/response IDs, hook IDs, replay metadata, and episode
  metadata into a normative trajectory;
- validates the reconstructed trajectory before returning it.

Agent-side baseline adapter:

- receives only the reduced start JSON;
- exposes the existing `AgentSession` methods over JSONL;
- imports and runs one of the four existing deterministic policies;
- exits after the final acknowledgement.

## Leakage controls

The child start message contains:

- question;
- tool names;
- duration;
- public budget/cost schedule;
- deterministic seed and wire configuration;
- one opaque episode handle.

It does not contain:

- real episode ID;
- family ID;
- state role;
- intervention identifiers or definitions;
- oracle labels;
- evidence IDs;
- accepted sufficient sets or necessity groups;
- backend/index/intervention hashes;
- replay seed;
- active restoration-hook identifiers.

Real backend result IDs and observation IDs are replaced before delivery.
Backend-version strings are also replaced because arbitrary backend labels are
not required policy inputs and may otherwise become a condition side channel.
Observation payload `_route_refs` remain only in the evaluator trajectory.

Opaque handles are deterministic for a configured seed and episode, but have no
semantic components. They are not cryptographic authorization tokens; their
purpose is non-semantic identity and reversible evaluator bookkeeping.

## Protocol enforcement

Implemented controls:

1. total wall-clock deadline covering process startup, interaction, and exit;
2. cumulative stdout/stderr output-byte limit;
3. per-message byte limit;
4. UTF-8, newline termination, JSON-object, and envelope checks;
5. schema and semantic action validation;
6. schema and semantic response validation;
7. opaque episode-ID equality;
8. contiguous steps and unique request IDs;
9. backend enforcement of budget, action order, and no action after finalize;
10. explicit runtime rejection of any message emitted after finalization;
11. deterministic environment values and runtime configuration;
12. one process per episode.

The child environment is intentionally small, but this is hygiene rather than
security isolation.

## Adversarial tests

`tests_agent_runtime/adversarial_agent.py` includes modes that:

- inspect episode start and opaque IDs for state/family markers;
- submit a known-looking gold claim ID;
- inspect returned payloads for `_route_refs` or evidence identifiers;
- emit invalid JSON;
- exceed output limits;
- stall past timeout;
- send another action after finalize.

Expected behavior:

- state/family and private route probes see no protected identifiers;
- submitted registered claim IDs are overwritten by evaluator mapping;
- malformed, oversized, timed-out, and post-finalize agents fail closed with
  stable runtime error codes.

The test suite also executes all four current baselines in fresh subprocesses
and validates the reconstructed trajectory.

## Validation evidence

Commands run:

```bash
PYTHONPATH=src pytest -q tests_agent_runtime
PYTHONPATH=src pytest -q tests tests_mvp tests_agent_runtime
```

Both completed successfully. The focused runtime suite contains 13 tests. The
combined existing and runtime suites completed with no failures.

A direct CLI smoke test also produced a trajectory for
`syn_f01_visual_order/CLEAN` with `SingleShotRAG`; the current
`validate_trajectory` implementation returned `PASS`.

## Security statement

This implementation is a **serialization/process boundary, not an OS sandbox**.

It guarantees that evaluator Python objects are not handed directly to child
policy code and that protocol-visible content is filtered, translated, bounded,
and validated. It does not guarantee confidentiality against host filesystem
access, network access, `/proc` inspection, environment compromise, debugger or
ptrace access, side channels, inherited credentials, kernel vulnerabilities, or
other capabilities granted by the operating system.

For genuinely untrusted submissions, run the child command inside a separately
configured sandbox or container with:

- no network namespace access;
- a minimal read-only filesystem without dataset/evaluator artifacts;
- no evaluator secrets in environment variables;
- process, memory, CPU, file-descriptor, and syscall limits;
- separate user/namespace credentials;
- controlled executable and dependency provenance.

Those controls are outside this repository deliverable and are not claimed
here.
