# Credential handoff

**As of:** 2026-10-26  
**Rule:** credentials are newly issued on the destination machine, never
stored in the repository or migration bundle, and never pasted into handoff
documents or chat.

The migration tooling does not read GitHub or Hugging Face token variables.
Authentication and upload are separate owner-controlled operations.

## General controls

1. Use a new, least-privilege credential for the destination operator or
   workload.
2. Prefer hidden interactive login or a secret manager.
3. Do not place a token in a command-line argument, checked-in file, `.env`,
   shell history, JSON manifest, issue, pull request, chat, or terminal
   transcript.
4. Run authentication only after repository/repository-ID decisions are
   approved.
5. Never copy the old machine's credential stores, browser cookies, SSH
   private keys, or CLI auth directories.

## 2026-10-26 exposure event

GitHub and Hugging Face access tokens were pasted into a chat message. They
must be considered exposed even if no unauthorized use is observed.

- Revoke both tokens in their provider settings.
- Do not store them in this repository, shell history, a command argument, or
  an upload plan.
- The exposed values are not approved for AV-TRACE upload.
- The machine's pre-existing Hugging Face CLI login is a separate credential
  and was observed to identify as `blackBOX25I47`; it may be used only while
  it remains valid and owner-approved.
- GitHub upload requires a newly rotated credential or a separately verified
  interactive/SSH login.

## GitHub CLI

Preferred interactive flow:

```bash
gh auth login
gh auth status
```

For ephemeral automation, let the secret manager set the environment without
printing it:

```bash
set +x
export GH_TOKEN='${INJECT_FROM_SECRET_MANAGER}'
gh auth status
```

Do not use `echo "$GH_TOKEN"`, `env`, `printenv`, `set -x`, or a process
argument containing the value.

After the operation:

```bash
unset GH_TOKEN
gh auth logout --hostname github.com
```

If the token may have been exposed, revoke it immediately in the GitHub owner
account or organization, review its audit/activity record, issue a replacement
with narrower scope, and update only the secret manager.

## Hugging Face CLI

Preferred interactive flow:

```bash
install -d -m 0700 "${HF_HOME:?set HF_HOME first}"
hf auth login
hf auth whoami
```

The interactive prompt must be hidden; do not put the token after a CLI flag.

For ephemeral automation:

```bash
set +x
export HF_TOKEN='${INJECT_FROM_SECRET_MANAGER}'
hf auth whoami
```

If the local stack is standardized on `HUGGINGFACE_HUB_TOKEN`, use that name
instead of duplicating the same secret in two variables:

```bash
set +x
export HUGGINGFACE_HUB_TOKEN='${INJECT_FROM_SECRET_MANAGER}'
hf auth whoami
```

After the operation:

```bash
unset HF_TOKEN HUGGINGFACE_HUB_TOKEN
hf auth logout
```

If exposure is suspected, revoke the token in the HF account settings, remove
the destination credential cache, rotate the secret-manager entry, and rerun
`hf auth login` with the replacement.

## Storage boundary

- Credential caches belong to the destination user's protected home/cache,
  not `$AV_TRACE_ROOT`.
- Do not copy `~/.config/gh`, `~/.cache/huggingface/token`, `HF_HOME`, `.netrc`,
  keyrings, browser profiles, or SSH private keys into the bundle.
- Repository documents may contain only placeholders such as
  `${INJECT_FROM_SECRET_MANAGER}`.
- A token must never be recorded in
  `data/migration/migration_bundle_manifest.json`,
  `BUNDLE_MANIFEST.json`, `BUNDLE_SHA256SUMS`, or test output.

## Rotation checklist

- [ ] Old machine credentials inventoried without copying their values.
- [ ] Old credentials revoked or scheduled for revocation after cutover.
- [ ] New credentials scoped to the approved GitHub/HF repositories only.
- [ ] Destination authentication verified without token output.
- [ ] Secret variables unset after use.
- [ ] No credential appears in shell history, logs, repository files, bundle,
      issue trackers, or chat.
