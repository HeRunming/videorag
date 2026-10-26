# P23_102 post-acquisition orchestrator

**Date:** 2026-10-14  
**Disposition:** `P23_102_POST_ACQUISITION_ORCHESTRATOR_READY`

## Purpose

`tools/p23_102_post_acquisition_orchestrator.py` is a fail-closed,
checkpointed wrapper around the already-defined P23_102 post-acquisition
chain. It does not download bytes and it does not launch the rehearsal.

The frozen order is:

1. prove the parallel segment manifest has complete, contiguous coverage from
   the current canonical staging prefix to exact EOF;
2. run `epic_p23_102_parallel_acquisition.py --assemble`, which also reuses the
   exact acquisition implementation to produce the
   `COMPLETE_VERIFIED_READY` exact manifest;
3. run the full (not smoke) P23_102 timeline build with resume enabled;
4. run the independent full-timeline verifier with source rehashing enabled;
5. run deterministic family mining to the development-only
   `candidate_registry.json`;
6. audit the prospective rehearsal prerequisites and write an honest
   ready/not-ready report without running the rehearsal.

## CLI

```text
python tools/p23_102_post_acquisition_orchestrator.py --status
python tools/p23_102_post_acquisition_orchestrator.py --run-next
python tools/p23_102_post_acquisition_orchestrator.py --run-all
```

Optional controls are `--repo-root`, `--state-dir`, and the positive
`--threads` value passed to the full-timeline builder.

`--status` is read-only. `--run-next` executes or adopts at most one stage.
`--run-all` advances through all remaining stages and stops at the first
failure.

## Acquisition and tmux interlock

Every mutating mode checks all of the following before it considers a stage:

- the canonical `.acquisition.lock` path must be absent;
- the `.parallel_acquisition.lock` advisory `flock` must not be held;
- `/proc/*/cmdline` must contain no active P23_102 parallel/exact acquisition
  process or known `avtrace_p23_acquire` / `tmux_parallel_acquire` supervisor.

This combines lock semantics with process inspection because the parallel
lock file is intentionally persistent: file existence alone does not prove
activity. Conversely, the exact downloader's canonical lock uses existence as
its exclusion protocol. Any active signal refuses `--run-next` and
`--run-all`; the orchestrator never waits, kills, attaches to, or modifies the
live acquisition.

As observed on 2026-10-14, the live acquisition can therefore continue while
`--status` reports `BLOCKED` without affecting it.

## Orchestrator exclusion

Mutating modes take a nonblocking exclusive `flock` on:

```text
data/restricted/epic_p23_102_source_v1/
  post_acquisition_orchestrator_v1/.orchestrator.lock
```

Only one orchestrator may adopt outputs, execute a delegated command, or
write receipts at a time. Status reports whether this lock is currently held
but does not acquire it.

## Stage gates

### `assemble_exact`

The precheck binds asset ID, expected bytes, official MD5, current prefix, and
contiguous complete segment records. It checks the corresponding segment
files and sizes but intentionally leaves full segment-content rehashing to the
existing assembly implementation, which validates every selected segment
before mutation.

The command is exactly:

```text
<python> tools/epic_p23_102_parallel_acquisition.py --assemble
```

Success requires the exact manifest and final media to bind:

- `status == COMPLETE_VERIFIED_READY`;
- `P23_102`, CC BY-NC 4.0, exact byte count and official MD5;
- a 64-hex SHA-256;
- successful ffprobe validation;
- no semantic-annotation use.

### `build_full_timeline`

The exact manifest is the prerequisite. The command selects `--mode full`,
`--resume`, and the configured thread count. Success requires all six
canonical timeline files, a full non-smoke build, valid self-hash, valid
artifact hashes and the existing index-only/nonclaim terminal boundary.

### `verify_full_timeline`

The verifier is a separate process and receives `--mode full` and
`--rehash-source`. Its stdout must be JSON with `verified: true` and the
P23_102 full-timeline decision token. Because this verification does not
create a dedicated canonical output, it is never silently adopted: a valid
receipt is required to mark it complete.

### `mine_machine_provisional_registry`

The command invokes the existing deterministic miner in `mine` mode without a
human prescreen. The resulting registry must:

- have the machine-provisional completion decision;
- be self-hash valid;
- remain development-only;
- report zero accepted families, accepted SESs, H tiers, and Gate A credit;
- report zero model inference and `models_loaded == false`;
- retain `future_test_eligible == false`.

### `validate_rehearsal_prerequisites`

This is an internal file/schema audit, not a rehearsal runner. It enumerates
both `existing_required` and
`future_required_for_development_rehearsal` from the committed rehearsal plan.
Missing files, mismatched required status/tokens/phrases, or bindings the
orchestrator cannot prove remain failures. The report may validly end as:

- `READY_FOR_DEVELOPMENT_REHEARSAL`, or
- `NOT_READY_FAIL_CLOSED`.

Both outcomes mean the validation stage completed honestly. Neither outcome
authorizes scientific execution.

## Receipts and attempts

The state root contains:

```text
receipts/<stage>.json
attempts/<stage>.<timestamp>.<pid>.json
rehearsal_readiness.json
```

Writes use a same-directory temporary file, file `fsync`, atomic `os.replace`,
and directory `fsync`. Each command attempt records:

- exact argv as a JSON array (never a shell command string);
- start and end UTC timestamps;
- return code;
- stdout/stderr byte counts, SHA-256 hashes, and bounded tails;
- prerequisite evidence;
- a deterministic attempt hash.

A successful stage receipt additionally records:

- tool/config/control snapshots;
- output snapshots and hashes;
- semantic output-validation evidence;
- the linked attempt hash;
- the nonclaim boundary;
- a deterministic receipt hash.

The large exact media snapshot reuses the SHA-256 from the exact manifest
while binding path, size, mode, mtime, and inode. The independent verifier
later performs the explicit source-content rehash. Timeline artifacts,
registries, plans, tools, and ordinary outputs are directly SHA-256 hashed.

## Resume, adoption, and stale state

A valid receipt is the only basis for skipping a completed stage. Validation
recomputes:

- receipt self-hash;
- exact command argv;
- control snapshots;
- output snapshots;
- stage-specific semantic validation.

If any binding changes, the receipt is stale and execution stops. The tool
does not automatically rerun an expensive stage over ambiguous state.
Repair requires explicit review and removal or relocation of the stale
receipt/output outside this tool.

If canonical outputs already exist before this orchestrator is introduced,
the tool may create an `adopted_existing_valid_outputs` receipt only after the
same output validation succeeds. It records the exact command that would
have produced the stage, `return_code: null`, and that no command was run.
Independent verification is excluded from adoption because its successful
process result is itself the evidence.

After a command failure, the attempt remains recorded but no success receipt
is written. A later invocation resumes from that stage; earlier valid stages
are not rerun. Repeated `--run-all` calls after completion are idempotent.

## Safety and claim boundary

The orchestrator:

- never uses `shell=True`;
- never runs acquisition mode;
- never runs the rehearsal runner;
- never runs an agent or grounded generator;
- does not load models itself (the existing full-timeline build is the sole
  predefined model-indexing stage);
- stops after a machine-provisional candidate registry and prerequisite audit;
- never claims human review, accepted SES, an H tier, Gate A, a scientific
  episode, a model result, or a causal effect.

The readiness token describes this implementation and checkpoint protocol:

`P23_102_POST_ACQUISITION_ORCHESTRATOR_READY`
