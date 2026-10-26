# Scale-1B agent failure retention and R/N isolation

Date: 2026-10-14  
Status: **SCALE1B_AGENT_FAILURE_RETENTION_AND_ISOLATION_READY**

## Scope

This repair closes two red-team defects in the Scale-1B learned-agent process
boundary:

1. learned-call failures now retain the complete available initial/repair
   generation evidence and typed worker-error metadata; and
2. matched `R`/`N` continuations can be injected with explicitly fresh,
   independently attestable model processes.

No runner was modified. The new process factory is deliberately runner-facing
so a later runner change can inject it without weakening this boundary.

## Failure-retention contract

`LearnedCallFailure` remains the controller-level typed exception and now
provides:

- `attempts`: ordered, detached attempt records; and
- `to_record()`: a persistence-ready typed failure record.

For malformed initial output followed by malformed repair output, both attempt
records retain:

- exact `raw_text`;
- `raw_sha256`;
- request and system-prompt hashes;
- token, latency, and RSS fields when supplied by the worker;
- validation error text and type; and
- whether the record was initial generation or repair.

For `ModelProcessError`, the failed attempt retains:

- typed process error code and message;
- stderr accumulated by the parent;
- worker return code when available;
- process PID and process-group ID;
- session ID, cache namespace, and runtime namespace;
- command and offline/network-denial state;
- request count and request hashes; and
- worker-provided typed error payload when the worker emitted one.

If a process failure occurs during repair, the validly captured initial raw
attempt remains in the same ordered failure record. There is no deterministic
answer or action substitution after failure.

## Fresh continuation primitive

`FreshQwenProcessFactory` is the injection primitive. It supports:

- `factory(label)` or `factory.create(label)` for one fresh process; and
- `factory.continuations()` as a context manager yielding independent
  `restored` and `no_trigger` `QwenProcess` instances.

Each created process receives a cryptographically random:

- session ID;
- model/cache namespace; and
- private runtime directory.

Each process also receives:

- its own OS process and process group (`start_new_session=True`);
- private `HOME`, `TMPDIR`, `XDG_CACHE_HOME`, `HF_HOME`,
  `HUGGINGFACE_HUB_CACHE`, and `TRANSFORMERS_CACHE`;
- no inherited request or conversation object;
- no shared model KV state because the model runtime is loaded in a distinct
  process; and
- environment-visible session/cache identifiers for worker attestation.

`ContinuationProcessPair.attestations()` reports, per arm:

- continuation label;
- session and cache IDs;
- PID and process-group ID;
- runtime namespace;
- network-namespace-denial setting;
- offline-environment status;
- fresh-process status; and
- explicit `shared_conversation_state=False` and `shared_kv_state=False`.

The pair context manager fails closed on any collision in session ID, cache
namespace, PID, process group, or runtime namespace.

## Offline and network-denial behavior

Every worker still runs with:

- `HF_HUB_OFFLINE=1`;
- `TRANSFORMERS_OFFLINE=1`;
- `HF_DATASETS_OFFLINE=1`;
- proxy and Hugging Face token variables removed; and
- local cache/home roots scoped to that process.

When `ProcessConfig.deny_network_namespace=True`, network namespace denial is
applied to both default and injected worker commands via `unshare -n`. This
means fake or alternate runner-injected commands cannot silently bypass the
configured denial policy.

## Bounded cleanup

Normal close requests worker shutdown and waits only
`shutdown_timeout_s` (default five seconds). Broken pipes, non-responsive
workers, or timeout cause a process-group `SIGKILL`, followed by another
bounded wait and direct child kill fallback. Selector resources and private
runtime/cache directories are removed in `finally`. `close()` is idempotent.

The paired continuation context uses `ExitStack`, so both workers are closed
on normal return, exception, or isolation-attestation failure.

## Tests

Focused tests use only fake Python JSONL workers; no Qwen inference is run.
They cover:

- malformed output after repair retains both exact raw attempts and hashes;
- a repair-stage process crash retains the initial attempt plus typed process
  metadata;
- a real fake-worker crash retains stderr, session/cache IDs, and request
  hashes;
- `R` and `N` use distinct processes, process groups, sessions, cache
  namespaces, and runtime roots;
- request counters demonstrate no shared request/conversation state; and
- paired cleanup reaps both workers and removes both private runtime roots.

Validation commands:

```text
ruff check src/av_trace_scale1b_agent/controller.py \
  src/av_trace_scale1b_agent/process.py \
  tooling/tests/test_scale1b_agent_controller.py \
  tooling/tests/test_scale1b_agent_process_isolation.py

PYTHONPATH=src pytest -q \
  tooling/tests/test_scale1b_agent_controller.py \
  tooling/tests/test_scale1b_agent_process_isolation.py
```

Final disposition:
**SCALE1B_AGENT_FAILURE_RETENTION_AND_ISOLATION_READY**
