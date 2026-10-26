# GitHub public-release boundary

**As of:** 2026-10-26  
**Status:** migration policy and release checklist; the code-license decision
is resolved as Apache-2.0, while third-party and credential checks remain
separate publication gates.

## Principle

The public repository is assembled from an explicit, model-free candidate
manifest. Git tracking state is not treated as evidence that a file is safe.
Every candidate must pass path, content, size, binary, symlink, and license
boundary checks.

The public package should contain the smallest useful research and engineering
surface: source code, tests, schemas, public documentation, and reviewed public
plans. It must not contain the local execution environment or evidence whose
access, identity, license, privacy, or governance status is restricted.

## Default include surface

Subject to content scanning and file-level review:

- root project metadata and public policy documents;
- `src/`, `scripts/`, and `tools/`;
- `tests*/` and `tooling/`;
- `docs/`;
- code, schemas, and README material under `mvp/`;
- `data/acquisition_plan/` when it contains only generic plans and no
  authorization receipt or credential;
- `data/candidates/` when records are public-safe and rights-reviewed;
- `data/rehearsal_plan/` for public design plans, schemas, blank forms,
  registries, and explicit public commitments.

Inclusion is not automatic. A candidate is blocked when it contains a secret,
internal domain, machine path, private governance identifier, binary payload,
unreviewed large file, or unresolved license boundary.

## Default exclude surface

| Surface | Default disposition | Reason |
|---|---|---|
| `.git/`, `.agents/`, `.codex/` | Exclude | VCS and local-agent internals |
| caches, bytecode, coverage, `build/`, `dist/`, egg-info | Exclude | Reproducible generated state |
| `data/restricted/` | Exclude | Real media, models, private labels, attempts, authorizations, hashes, and controlled evidence |
| `data/access_review/` | Exclude | Approval, authorization, and access records |
| `data/acquisition_preflight/` | Exclude | Live route/probe results and transfer metadata |
| `data/hf_recon/`, `data/source_recon/` | Exclude pending item-level review | Third-party snapshots, licenses, metadata, and possible upstream payload fragments |
| `data/rehearsal_review/` | Exclude | Internal review packets |
| `mvp/generated/`, `mvp/results/` | Exclude | Generated outputs and run reports |
| `mvp/media_backed/fixtures/` | Exclude by default | Binary media, even when synthetic, requires explicit release and size review |
| `orchestration/logs/`, `prompts/`, `results/` | Exclude | Internal prompts, transcripts, paths, infrastructure details, and execution results |
| model/gateway smoke-run trees | Exclude | Raw attempts, model output, runtime provenance, and internal identifiers |
| credentials, tokens, private keys, environment files | Exclude and rotate if live | Security boundary |
| authorization/approval receipts and claims | Exclude | Private governance boundary |
| raw attempts, attempt markers, failure capsules | Exclude | Internal execution and incident evidence |
| private ledgers and untouched-test identities | Exclude | Scientific integrity and governance boundary |
| real audio/video and model/checkpoint formats | Exclude | Rights, privacy, size, and security boundary |

The word `rehearsal_plan` is intentionally **not** globally ignored. That
directory contains valuable public protocol plans. Private subtrees and
execution artifacts inside it are excluded narrowly.

## Current repository audit observations

The 2026-10-23 working tree contains:

- approximately 555 GB under `data/restricted/`, including multi-gigabyte
  acquired video and model weight files;
- build wheels, package metadata, Python/test/lint caches, coverage output, and
  many runtime logs;
- generated MVP media and reports;
- internal orchestration prompts, logs, and result transcripts;
- public plans mixed with private attempts and run provenance under
  `data/rehearsal_plan/`;
- numerous machine-specific absolute paths and internal proxy/domain references
  that require exclusion or redaction before their containing files can be
  public;
- an owner-approved Apache-2.0 repository license.

These observations make a direct "push the current tree" migration unsafe.

The initial model-free scan on this date produced 1,458 candidate files
(42,417,434 bytes). After removing candidate paths with detected blockers, the
provisional release-ready subset contained 1,370 files (19,943,420 bytes).
These figures are a point-in-time inventory, not a release approval; concurrent
workspace changes can alter them.

## Audit tool

`scripts/audit_public_release.py` walks the filesystem without consulting Git.
It:

- applies a conservative public include/exclude policy;
- emits a candidate public file manifest and a release-ready subset;
- detects likely secrets, internal proxy/domains, absolute machine paths, and
  private governance IDs;
- blocks symlinks, binary candidates, and files over the configured review
  threshold;
- checks the repository-level code-license decision and required notices;
- supports a transparent, report-embedded allowlist;
- modifies nothing by default.

Examples:

```bash
# Human-readable summary; exit status does not enforce blockers.
python scripts/audit_public_release.py

# CI/release gate. Exit 1 when non-allowlisted blockers remain.
python scripts/audit_public_release.py --check

# Full candidate manifest, exclusions, and blockers.
python scripts/audit_public_release.py --check \
  --json-output /tmp/av-trace-public-release-audit.json
```

An optional allowlist is a JSON array:

```json
[
  {
    "path": "docs/example.md",
    "check": "absolute_machine_path",
    "reason": "Reviewed historical example; no user or infrastructure identity"
  }
]
```

Allowlisting does not make content safe. It records an explicit reviewer
decision and should be narrow by path and check. Never allowlist a live secret,
credential, private key, restricted identity, or unlicensed payload.

## Release procedure

1. Verify that the owner-approved Apache-2.0 `LICENSE` is present and that
   third-party content remains outside its scope.
2. Review `THIRD_PARTY_DATA_NOTICE.md` and generate artifact-specific notices
   for anything actually included.
3. Run the audit with `--check --json-output`.
4. Remove, redact, or narrow the include surface for every blocker. Use an
   allowlist only after explicit human review.
5. Review all large files and binaries independently, even if a future policy
   elects to include them.
6. Scan the assembled release and repository history with the hosting
   provider's secret scanning and an approved history scanner.
7. Build the public repository in a clean staging directory from the manifest;
   do not publish the working tree in place.
8. Re-run tests and the audit against that staging directory.
9. Have code-license, third-party-rights, security, privacy, and scientific
   governance owners sign off before publishing.

## Stop conditions

Do not publish while any of the following remains:

- missing or altered owner-approved repository license;
- actual or suspected live secret;
- restricted media, model, private label, authorization, or identity;
- unexplained internal infrastructure detail or absolute machine path;
- unreviewed binary/symlink/large candidate;
- unclear third-party redistribution or attribution requirement;
- public package depending on files that are excluded or inaccessible.
