# Pre-download reproduction checklist

**Purpose:** inspect and freeze official upstream metadata without cloning large
repositories or transferring media/data shards. This checklist is a discovery
procedure, not an executable download allowlist and not a grant of network or
media authority. Stop at the marked gate.

No executable media allowlist exists in this package. A later allowlist, if
authorized, must be generated from asset-level manifests after Gate A.

## 0. Safety setup

```bash
set -euo pipefail
export AUDIT_DATE=2026-09-07
export OUT="${OUT:-/tmp/av_trace_upstream_recon}"
umask 077
mkdir -p "$OUT"/{github,hf,headers,notes}
```

Rules:

- Use only official URLs listed in `docs/research/upstream_reproduction_audit.md`.
- Do not place tokens or cookies on a command line, in shell history, or in the repository.
- Do not run `git clone`, `huggingface-cli download` without `--dry-run`, `wget`, `curl -O`, `yt-dlp`, `aria2c`, `git lfs pull`, archive extraction, or any upstream `download*.sh`.
- Do not open `.pkl`, `.pt`, `.npy`, `.bin`, archive, video, or audio files.

## 1. Verify required clients

```bash
python - <<'PY'
import importlib.util
for name in ("requests", "huggingface_hub"):
    print(name, "present" if importlib.util.find_spec(name) else "MISSING")
PY
command -v git
command -v sha256sum
```

Installation, if needed, should occur in an isolated environment and must be separately reviewed; do not let package installation trigger model/data downloads.

## 2. Resolve GitHub revisions and small trees

Set an optional token in the environment for rate limits:

```bash
# Read interactively if needed; do not echo or persist.
# read -rsp 'GitHub token: ' GITHUB_TOKEN; export GITHUB_TOKEN; echo
```

Create a metadata-only inspector:

```bash
cat > "$OUT/github_inspect.py" <<'PY'
import json, os, sys, urllib.request
repo, out = sys.argv[1:]
headers = {"Accept":"application/vnd.github+json", "User-Agent":"av-trace-recon"}
if os.getenv("GITHUB_TOKEN"):
    headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
def get(url):
    req=urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
meta=get(f"https://api.github.com/repos/{repo}")
branch=meta["default_branch"]
commit=get(f"https://api.github.com/repos/{repo}/commits/{branch}")
tree=get(f"https://api.github.com/repos/{repo}/git/trees/{commit['sha']}?recursive=1")
allowed=[]
for x in tree.get("tree", []):
    p=x.get("path", "").lower()
    if x.get("type")=="blob" and x.get("size", 0) <= 262144 and (
        p.endswith((".md",".txt",".json",".yaml",".yml",".toml",".py",".sh","license"))
        or p.rsplit("/",1)[-1] in {"license","notice"}
    ):
        allowed.append({k:x.get(k) for k in ("path","sha","size","url")})
result={
  "repository": repo,
  "html_url": meta["html_url"],
  "default_branch": branch,
  "commit_sha": commit["sha"],
  "commit_date": commit["commit"]["committer"]["date"],
  "license": meta.get("license"),
  "archived": meta.get("archived"),
  "tree_truncated": tree.get("truncated"),
  "small_text_candidates": allowed,
}
with open(out,"w") as f: json.dump(result,f,indent=2,sort_keys=True)
print(repo, result["commit_sha"], len(allowed), "small text candidates")
PY
```

Run against official repositories:

```bash
for repo in \
  TechNomad-ds/LoVR-benchmark \
  yrywill/LongVidSearch \
  YqjMartin/FLARE \
  MME-Benchmarks/Video-MME \
  longvideobench/LongVideoBench \
  mbzuai-oryx/LongShOT \
  Heinz217/TraceAV-Bench \
  buaa-colalab/TRACE
do
  python "$OUT/github_inspect.py" "$repo" "$OUT/github/${repo//\//__}.json"
done
sha256sum "$OUT"/github/*.json > "$OUT/github/SHA256SUMS"
```

Review file names and sizes. Fetch only selected README/LICENSE/config/source blobs smaller than 256 KiB through the GitHub contents API at the resolved SHA. Do not execute them.

```bash
python - <<'PY'
from pathlib import Path
import json, os
root=Path(os.environ["OUT"])/"github"
for p in sorted(root.glob('*.json')):
    d=json.loads(p.read_text())
    print("\n", d['repository'], d['commit_sha'], 'license=', d['license'])
    for x in d['small_text_candidates'][:80]: print(x['size'], x['path'])
PY
```

## 3. Inspect Hugging Face repositories without downloading files

Create a metadata-only inspector:

```bash
cat > "$OUT/hf_inspect.py" <<'PY'
import json, os, sys
from huggingface_hub import HfApi
repo, out = sys.argv[1:]
api=HfApi(token=os.getenv("HF_TOKEN"))
info=api.dataset_info(repo_id=repo, files_metadata=True, expand=["cardData"])
rows=[]
for s in info.siblings or []:
    lfs=getattr(s,"lfs",None)
    rows.append({
      "rfilename":s.rfilename,
      "size":getattr(s,"size",None),
      "blob_id":getattr(s,"blob_id",None),
      "lfs_oid":getattr(lfs,"oid",None) if lfs else None,
      "lfs_size":getattr(lfs,"size",None) if lfs else None,
    })
outobj={
  "repo_id":repo, "sha":info.sha, "private":info.private,
  "gated":info.gated, "disabled":info.disabled,
  "card_data":dict(info.card_data or {}), "siblings":rows,
}
with open(out,"w") as f: json.dump(outobj,f,indent=2,sort_keys=True,default=str)
print(repo, info.sha, "gated=", info.gated, "files=", len(rows))
PY
```

Run metadata inspection; failures for gated datasets are expected until terms are accepted:

```bash
for ds in \
  debugger123/LoVR-benchmark \
  Fishiing/LongVidSearch \
  AnonymousFLARE/FLARE \
  AnonymousFLARE/FLARE_demo \
  lmms-lab/Video-MME \
  longvideobench/LongVideoBench-Meta \
  longvideobench/LongVideoBench \
  MBZUAI/longshot-bench \
  Heinz217/TraceAV-Bench \
  buaaplay/VES-Bench \
  DISLab/VRAG-Bench \
  lmms-lab/EgoLife \
  NJU-LINK/OmniVideoBench
do
  python "$OUT/hf_inspect.py" "$ds" "$OUT/hf/${ds//\//__}.json" \
    || printf '%s\n' "$ds: gated, unavailable, renamed, or authentication required" \
       >> "$OUT/notes/hf_failures.txt"
done
sha256sum "$OUT"/hf/*.json > "$OUT/hf/SHA256SUMS" 2>/dev/null || true
```

Optional dry-run only, after inspecting repository size:

```bash
# Example; prints planned files and sizes but must not transfer content.
# huggingface-cli download longvideobench/LongVideoBench \
#   --repo-type dataset --dry-run
```

If the installed CLI lacks `--dry-run`, **do not substitute a real download**. Use `HfApi.dataset_info(..., files_metadata=True)` only.

## 4. Schema-only discovery

For small public JSON/README files, fetch by immutable revision into `$OUT`, hash, and inspect as text. For parquet, prefer server-exposed schema/statistics. Do not download a large shard merely to discover columns.

- [ ] LoVR: identify exact caption/clip table names and fields; record parent LongVideoBench IDs.
- [ ] LongVidSearch: enumerate `*_qa.json`; inspect one small example; record `full-QA(3000).json`, caption parquet, embedding files, and pickle as **do not load**.
- [ ] FLARE: enumerate release files and capture query/caption/modality field names.
- [ ] Video-MME: inspect the output template and evaluation script; record post-2024-06-15 revision.
- [ ] LongVideoBench: inspect `lvb_val.json` schema and subtitle JSON variants without fetching `videos.tar.part.*` or `subtitles.tar`.
- [ ] LongShOTBench: record gated status, terms URL, v1/v2 namespace, rubric and conversation fields.
- [ ] TraceAV-Bench: inspect one metadata example and staged source/config files; record model/prompt placeholders.
- [ ] VES-Bench: obtain parquet schema only and confirm evidence interval columns; do not fetch `videos/`.
- [ ] V-RAGBench: inspect the public card/file listing only; wait for an
  immutable payload with source IDs before schema work, and do not request
  Ego4D/EgoLife video.

## 5. Credential and service inventory

Record presence, never values:

```bash
python - <<'PY'
import os
for key in [
 "GITHUB_TOKEN", "HF_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
 "GOOGLE_API_KEY", "GEMINI_API_KEY", "DASHSCOPE_API_KEY"
]:
    print(f"{key}={'SET' if os.getenv(key) else 'unset'}")
PY
```

- [ ] No secret appears in captured stdout/stderr.
- [ ] No `cookies.txt` exists under the project or `$OUT`.
- [ ] Every API-dependent script has provider/model/base URL/prompt/temperature documented.
- [ ] Every local-model dependency has model repository, revision, license, weight hash, CUDA and inference-engine version documented.

## 6. License and rights split

For every release, complete four independent fields:

- [ ] repository/code license at pinned revision;
- [ ] annotation/dataset license and scope;
- [ ] model/weight license for generated artifacts;
- [ ] source-media acquisition/processing/redistribution rights per asset.
- [ ] observed official technical access route;
- [ ] intended episode publication class.

A missing field is `unknown_hold`, not permission. Public URL, dataset hosting, repository license, or successful authentication is insufficient.

## 7. Freeze the reconnaissance packet

```bash
find "$OUT" -type f -print0 | sort -z | xargs -0 sha256sum > "$OUT/MANIFEST.sha256"
python - <<'PY'
from pathlib import Path
import json, datetime, os
out=Path(os.environ["OUT"])
summary={
 "created_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "media_transfer_performed":False,
 "large_data_downloaded":False,
 "cookie_downloader_executed":False,
 "next_gate":"human review of revisions, schemas, licenses, rights, sizes, and services",
}
(out/'RECON_STATUS.json').write_text(
    json.dumps(summary,indent=2,sort_keys=True) + "\n"
)
PY
```

## Mandatory stop gate

**STOP HERE. Do not run any command that transfers media, subtitles, large parquet files, archives, embeddings, model weights, or platform-hosted video.**

Before a later materialization phase, require all of the following:

- immutable repository and dataset revisions;
- reviewed file allowlist, expected sizes, hashes/OIDs, and storage budget;
- explicit authorization for acquisition and local processing;
- accepted gated terms and external agreements where applicable;
- source-media rights and privacy review;
- a generated AV-TRACE download plan bound to approved asset IDs;
- a separate execution approval, as required by `docs/engineering/data_adapter.md`.
