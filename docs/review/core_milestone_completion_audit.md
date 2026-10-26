# AV-TRACE 核心里程碑独立完成度审计

**Task:** 88  
**审计日期:** 2026-09-10  
**最终证据截止时间:** 2026-09-10 19:02:12（Asia/Shanghai）  
**总体状态:** **`CORE_MILESTONE_PROVEN`**

## 结论

本轮仅重新审计 Task 87/89 新增的 requirements 11–14；此前已经证明的
1–10 和 15 保持不变。

Task 87 已产出 11/11 必需 artifacts，并实际完成 bounded real-A/V
protocol MVP。Task 89 随后完成第一轮独立红队；Task 90 又修复了其指出的
五项 substantive limitations，完整重生成 72 条 trajectory 与全部结果，
并维持以下判断：

```text
ENGINEERING_GO
PROVISIONAL_SCIENTIFIC_INCONCLUSIVE
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

因此，用户定义的**当前核心里程碑**已经完成：3–5 个长视频资产的筛选、
精确下载、A/V 审计，以及对应 MVP 数据/协议验证和 Go/No-Go 记录均已有
可核验的实际产物。

`CORE_MILESTONE_PROVEN` 只表示这个 bounded engineering/protocol
milestone 已完成，**不表示科学 benchmark 已被验证**。Task 90 明确保留
`PROVISIONAL_SCIENTIFIC_INCONCLUSIVE`。

## 保持成立的 requirements 1–10 和 15

此前独立重算的证据没有被 Task 87/89 推翻：

- 公开 NOAA 来源的 5 个精确视频；
- 实测时长 29.54–63.02 分钟；
- 总下载量 1,955,298,193 bytes；
- 5/5 本地文件大小与 SHA-256 匹配；
- 5/5 真实可解码视频流和音频流；
- beginning/middle/near-end A/V decode 15/15；
- 120 个 recon 窗口、30 个 shortlist 窗口；
- 18/18 Whisper、18/18 AST；
- Task 85 保留 6 个窗口，覆盖 3 个 pilot asset；
- 所有标注继续是
  `MACHINE_ADJUDICATED_PROVISIONAL_MVP`,
  `human_reviewed=false`, `gold_annotation=false`。

五个资产仍为：

| Asset | PyAV 时长 | 本地 bytes | SHA-256 |
|---|---:|---:|---|
| `cand-045` | 29.540667 min | 58,576,631 | `03da99e7a33a1ad18ad57376e6517639f950e39b4fe67f898c54a948e17f9ad6` |
| `cand-047` | 33.063030 min | 284,515,787 | `ddfb6c2ffa2794f20bb5d2d4330b89807dfaeed7156a3d7cab372e78bd184160` |
| `cand-049` | 41.088826 min | 491,943,858 | `1934c31cb0311a46daab367f840eb549d29bb1e9e1475a73287912bba03069e5` |
| `cand-051` | 61.976359 min | 558,522,234 | `279f6b3841188e805b153ab0c7f0c85cdc584dd6bce6090f9e2a0b2d06d951b2` |
| `cand-052` | 63.019067 min | 561,739,683 | `c4f5d8c6e60d6802bb60e26f811f5dcabc9698626a29c6cb8aabcc373db4eef1` |

## Task 87/90 post-repair 重算结果

```text
provisional families:       6
source assets used by MVP:  3
reviewed windows:          18
frozen-index records:      54
main trajectories:         72
valid trajectories:        72
no-trigger controls:       12
intervention families:    6/6 passed

observations exercised:
  vision:                  178
  speech:                  109
  ambient:                 108

metric rows recomputed:     72
row-level mismatches:        0
aggregate mismatches:        0
aggregate rows:             40
route certificates:         72/72
run-manifest hashes:        11/11
stable replay hashes:       13/13
```

Task 90 记录的 15 项 authoritative artifact hashes 与当前文件全部匹配；
当前 Task 87 run manifest 引用的 11 个 artifact hashes 也全部匹配。

## 更新后的逐项证据矩阵

| # | 要求 | 观察结果 | 状态 | 剩余动作 |
|---:|---|---|---|---|
| 1 | 来源发现和公开/HF provenance | 5/5 视频来自官方 NOAA 页面和 CDN；HF 用于固定版本模型。 | `PROVEN` | 不得暗示视频来自 HF。 |
| 2 | 3–5 个资产 | 精确为 5 个资产。 | `PROVEN` | 无。 |
| 3 | 20–90 分钟 | 5/5 实测时长满足范围。 | `PROVEN` | 无。 |
| 4 | 真实视频和音频流 | 5/5 可解码；真实 ASR/AST 已运行。 | `PROVEN` | 无。 |
| 5 | 精确 URL/revision/bytes/hash | URL、ETag、Last-Modified、bytes、SHA-256 完整且一致。 | `PROVEN` | 无。 |
| 6 | 可执行下载及成功获取 | downloader 可执行，5 个完整 MP4 和 sidecar/manifest 存在。 | `PROVEN` | 无。 |
| 7 | B/M/E A/V decode | 15/15 A/V 解码通过。 | `PROVEN` | 可单独修复旧 media-audit 的 stage-aware allowlist。 |
| 8 | 内容窗口侦察 | 120 measurements，30 shortlist。 | `PROVEN` | routing label 不得当作 gold necessity。 |
| 9 | 真实 ASR/audio-event 裁决 | 18/18 Whisper、18/18 AST；Task 85 为 6/10/2。 | `PROVEN` | 仍非人工语义验证。 |
| 10 | provisional episode input gate | 6 个 accepted window，3 个 pilot asset，ambient/speech anchors 均存在。 | `PROVEN` | 已由 Task 87 builder 执行。 |
| 11 | CLEAN/BLOCKED/RESTORED 协议验证 | 6 个 family 均通过 CLEAN reachability、BLOCKED suppression、RESTORED trigger/reacquisition、no-trigger 和固定 budget 检查；72 条 trajectory 有最终点 validation。 | `PROVEN` | 人工语义/反事实验证留待 benchmark gold 阶段。 |
| 12 | fixed backend 和四类 baseline | 54-record fixed index；四类 policy 在 6×3 组合上运行，共 72 trajectories；Task 90 将 ReAct 和 sufficiency 分离为独立 controller，16/18 family-state action sequences 不同。 | `PROVEN` | 科学阶段应加入 learned baselines 和更强进程隔离。 |
| 13 | Acquire/Ground/Act metrics | 72 rows、40 aggregates、72 route certificates 全部独立复算且 0 mismatch/error；strict claim support、Success@Budget、final-point Premature Stop 和全局 low-N 均已实现。 | `PROVEN` | human-gold semantics 仍是后续科学验证条件。 |
| 14 | engineering / provisional scientific Go/No-Go | 当前 Task 87 和 Task 90 一致给出 `ENGINEERING_GO / PROVISIONAL_SCIENTIFIC_INCONCLUSIVE / FINAL_BENCHMARK_NOT_YET_VALIDATED`。 | `PROVEN` | INCONCLUSIVE 是已完成且诚实的科学 Go/No-Go 结果，不是缺失项。 |
| 15 | machine provisional 与 human gold 边界 | 所有关键产物保持 machine-only、non-gold；human-validated modality necessity 仍为 0。 | `PROVEN` | 后续人工验证前不升级 claim。 |

最终统计：

```text
PROVEN:       15/15
INCOMPLETE:    0/15
MISSING:       0/15
CONTRADICTED:  0/15
```

## Requirement 11：CLEAN / BLOCKED / RESTORED

Task 90 重生成并验证六个 family：

- CLEAN support route reachable；
- BLOCKED 抑制 direct/derived route；
- 每个 family 保留至少 4–5 个 admissible same-source distractors；
- RESTORED 在 trigger 前与 BLOCKED 一致；
- trigger 确定且不依赖答案或模型身份；
- trigger 后恢复 CLEAN route；
- agent 在恢复后重新获取 evidence；
- 12/12 no-trigger controls 无法 recovery；
- 三种状态预算一致。

`r004` 和 `r016` 使用 policy-visible exact timestamp 做跨模态绑定。Task 89
确认该规则没有读取 evaluator-private route ID。

## Requirement 12：fixed backend 和四类 baseline

实际产物包括：

```text
18 reviewed windows
54 modality-specific index records
6 families
3 states
4 named deterministic policies
72 trajectories
```

每个 citable observation 在 tool time：

1. 对原始 MP4 重新计算并核对 SHA-256；
2. 从原始 MP4 直接解码精确时间区间；
3. 验证请求模态的完整覆盖；
4. 不持久化帧、音频或 clip derivative。

Task 89 曾独立以 video+audio 模式解码 18/18 review intervals；Task 90
重生成后继续通过 tool-time decode、media invariance 和无 derivative 检查。

这里的四个系统仍是 **deterministic protocol probes**，不是 learned
VLM/LLM baseline。但 Task 90 已将两个 agentic controller 分离：

```text
reactive-query-reformulation/2.0
explicit-evidence-sufficiency/2.0
```

它们在 18 个 family-state cases 中有 **16 个不同 action sequences**。
该修复证明 controller 实现不同，但不构成 learned-model 优越性证据。

## Requirement 13：Acquire / Ground / Act

Task 90 独立重构 evaluator claim/evidence mapping，并重算：

```text
72/72 episode rows
40/40 aggregate rows
72/72 final-point route certificates
0 row mismatch
0 aggregate mismatch
0 certificate consistency error
```

正确的 eligibility 处理包括：

- direct-long-context 的 Evidence Recall 与 All-Evidence Success 为 `null`；
- 所有 Modality Recall 为 `null`，因为没有 human-validated modality necessity；
- direct 与 single-shot 的 Recovery 为 `null`；
- agentic RESTORED Recovery 的分母为 6；
- 每项均报告 numerator、denominator、eligible family/source count。

Task 90 已修复此前四项 metric limitations：

1. Supported-Claim Rate 现在按
   `supported asserted claims / all asserted claims`；
2. Success@Budget 要求 valid、in-budget、正确、完整 support set、逐 claim
   citation support，且无 forbidden/contradictory assertion；
3. Premature Stop 使用实际 final decision point 的 route-feasibility
   certificate；
4. 40/40 aggregate rows 均携带 `LOW_N_DESCRIPTIVE_PILOT`，并与
   metric-specific eligibility warning 分开。

## Requirement 14：Go/No-Go

Task 90 在完成修复和重生成后再次确认三层结论：

### `ENGINEERING_GO`

适用于当前 bounded MVP：

- 原始媒体绑定和 tool-time decode 成立；
- 6/6 intervention families 通过；
- 72/72 trajectory 有效；
- 12/12 no-trigger controls 通过；
- 指标按当前公式可复算；
- media bytes 不变，无持久化 NOAA media derivative。

### `PROVISIONAL_SCIENTIFIC_INCONCLUSIVE`

不能升级为 GO，原因包括：

- 只有 6 个 family、3 个来源和 18-window candidate pool；
- 没有 human gold、human modality necessity 或 semantic minimality；
- 没有 learned model baseline；
- 两个 validator 都是 deterministic rules；
- 当前 policy 仍是 deterministic protocol probes；
- descriptive separation 尚不能在如此小的 machine-adjudicated pilot 上
  支撑科学有效性结论。

### `FINAL_BENCHMARK_NOT_YET_VALIDATED`

Task 90 已补上 strict claim-level grounding 和 final-point stopping
feasibility；最终 benchmark 仍需人工 evidence/counterfactual review、
learned baselines、更广的 full-timeline 数据和 release/privacy review。

## Task 89 和 Task 90 修复

Task 89 修复了两个 restricted-output 问题：

1. `data/restricted/noaa01/real_av_mvp/`：`0755 → 0700`
2. `mvp/results/noaa01_real_av_mvp/run_manifest.json`：
   - 增加 `restricted=true`
   - `0644 → 0600`
   - 修补 future writer，后续生成也保持该边界

修复后：

```text
run manifest artifact hashes: 11/11 match
run_manifest.json mode:       0600
restricted MVP directory:     0700
```

Task 90 进一步完成：

- strict claim-slot / citation mapping；
- strict supported finalization；
- 72 个 actual-final-point route certificates；
- 独立 evidence-sufficiency controller；
- 40/40 aggregate global low-N warning；
- 完整 Task 87 输出重生成。

## 验证

Task 90 实际完成：

```text
72/72 metric rows independently recomputed
40/40 aggregate rows independently recomputed
72/72 route certificates checked
0 row-level mismatches
0 aggregate mismatches
0 certificate errors
15 focused tests passed
441 full-suite tests passed
11/11 run-manifest hashes matched
13/13 deterministic replay hashes stable
```

Task 88 在 Task 90 重生成后又执行：

```text
PYTHONPATH=src python -m py_compile \
  src/av_trace_real_av/core.py \
  scripts/build_noaa_real_av_mvp.py \
  scripts/run_noaa_real_av_mvp.py

PASS
```

```text
PYTHONPATH=src pytest -q tests_real_av
15 passed
```

并再次完成 Task 87 指定的完整 suite，**441 tests passed**。Task 88 还
独立重算了当前 strict claim metrics、Success@Budget、Premature Stop、
40 个 aggregate rows 和 72 个 route certificates，未发现差异。

## 最终判断

```text
CORE_MILESTONE_PROVEN
```

这是对“资产筛选、精确获取、真实 A/V 验证、bounded MVP 协议运行和
Go/No-Go 记录”这一核心里程碑的完成确认。它与
`PROVISIONAL_SCIENTIFIC_INCONCLUSIVE` 和
`FINAL_BENCHMARK_NOT_YET_VALIDATED` 完全兼容。
