# AV-TRACE 项目现状：从最初想法到当前进度

**状态截至：2026-09-16**  
**证据口径：以当前 repository 中 post-red-team / post-repair artifact 为准。**

> **最短结论：**AV-TRACE 已经从一个宽泛的“长音视频 Agentic RAG
> benchmark”设想，收敛为一个更有辨识度的**配对干预诊断协议**：在问题、
> claim–evidence graph 和预算不变时，控制关键证据路径的可用性，观察系统能否
> 发现证据不足、判断是“源中没有证据”还是“访问路径失效”、改变检索行为，并在
> 路径恢复后重新取得证据和作答。工程链路已经相当扎实；科学证据仍是低样本、
> machine-provisional，尚未达到 CVPR main paper 所需的人类有效性、规模和
> learned-agent 证据。

---

## 0. 一页结论

### 项目现在处于什么阶段

可以把当前进度分成三个完全不同的层级：

| 层级 | 当前状态 | 它实际说明什么 |
|---|---|---|
| **Engineering readiness** | **已证明** | 五个真实 NOAA 长视频可被精确获取、校验、完整建索引；CLEAN/BLOCKED/RESTORED、轨迹、指标、重放和 learned retrieval 都已运行并经多轮独立审计。 |
| **Diagnostic / scientific evidence** | **有限且阶段不一** | Pilot-0 与 Scale-1A 是 `INCONCLUSIVE`；Wave-R 达到预注册的 `DIAGNOSTIC_GO`，但该 GO 只表示 learned retriever 确实产生了可复现的排序差异，且多数方向是变差。 |
| **Final benchmark validation** | **尚未建立** | 没有人类 gold，未验证 minimality / modality necessity，只有 5 个计分 family、3 个 family-bearing 视频，也没有 learned generator 或 learned agent 的端到端比较。 |

### 已完成的三个主要里程碑

1. **Pilot-0 bounded real-A/V MVP**
   - 3 个长视频、6 个 provisional family、18 个候选窗口；
   - 4 个 deterministic policy × 6 family × 3 state = **72 条主轨迹**；
   - **12 条 no-trigger control**；
   - 72/72 轨迹有效，6/6 intervention family、12/12 no-trigger control
     通过；
   - 结论：`ENGINEERING_GO`，但
     `PROVISIONAL_SCIENTIFIC_INCONCLUSIVE`。

2. **Scale-1A full-timeline**
   - 将检索空间从 18 个预选窗口扩展到五个视频的完整时间线；
   - 3,433 个四秒 cell、3,428 个 fine window、855 个 context window，
     共 **4,283 个 temporal segment**；
   - 迁移后保留 5 个 family，`r014` 因 visual support 不进 top-20 被排除；
   - 最终 **138 条 action-level trajectory、654 个 action**；
   - 结论：`SCALE1A_ENGINEERING_GO`，
     `SCALE1A_DIAGNOSTIC_INCONCLUSIVE`。

3. **Scale-1B Wave-R learned retrieval**
   - 在同一 frozen timeline 上加入真实的 **SigLIP2 visual retrieval**
     和 **CLAP audio retrieval**；
   - 与 CLIP、AST、BM25 及固定 equal-weight RRF control 做严格配对；
   - 64 个 metric row、40 个 paired row、132 个 retrieval/probe row；
   - 结论：`LEARNED_RETRIEVAL_READY`、`WAVE_R_DIAGNOSTIC_GO`；
   - 但结果不是“新模型更好”：在当前五个 provisional family 上，
     SigLIP2/CLAP 和全 learned 替换的 fusion 多数**弱于**原 control。

### 当前最重要的科学认识

AV-TRACE 已经证明一件有价值但较窄的事情：

> **“模型更先进”不等于“在长视频中更容易定位任务所需证据”；而且只看最终答案，
> 会掩盖 acquisition、grounding、stopping 和 recovery 的不同失败。**

当前还没有证明：

- 这些题目的答案和证据是人类认可的 gold；
- 被阻断的证据在语义上确实是 minimal / necessary；
- 某一题客观上必须使用 vision、speech 或 ambient；
- learned agent 比普通 RAG 或其他 controller 更会诊断和恢复；
- 结果可推广到 NOAA 以外，或推广到总体长视频任务。

### 对 CVPR main 的直白判断

**现在不是一篇完整的 CVPR main paper。**  
它已经超过“空概念”或“只有脚手架”的阶段，是一个经过认真审计的
**research infrastructure + real-data MVP + learned-retrieval diagnostic**。
但论文最关键的主张——受控干预能否揭示真实 learned agents 的可靠性差异——尚未
由 human-valid、跨视频、端到端实验支持。

### 下一步的一句话建议

**先做“小而严”的人工 construct-validation milestone，不要立刻大规模扩视频，
也不要先花时间写主论文。** 建议先把当前 5 个 retained family 和新增的一小批
候选做独立人工复核，验证答案、alternative SES、necessity group、modality
counterfactual 和 intervention isolation；只有该关通过，再接入 learned
generator / learned controllers 做端到端 CLEAN/BLOCKED/RESTORED。

---

## 1. 最初想做什么

### 1.1 原始构想：一个长音视频 Agentic RAG benchmark

项目最初希望覆盖一个完整的 long audio-video RAG 链：

```text
Long video
  -> multimodal retrieval
  -> grounded generation
  -> agentic tool use / replanning
  -> answer + evidence
```

从早期任务定义看，计划同时研究：

- vision、speech、ambient audio 检索；
- sparse / multi-hop evidence；
- grounded answer 与 citations；
- hard distractors、missing evidence、retrieval miss；
- modality/tool failure、ASR corruption；
- sufficiency calibration、abstention、premature stopping；
- restoration/recovery；
- counterfactual evidence utilization；
- fixed-backend、gold-evidence、open-system 等多个评测 tracks。

“retrieval / grounded generation / agentic”本质上是三类系统能力：

| 原始能力块 | 想回答的问题 |
|---|---|
| Retrieval | 能否从很长的视频中定位视觉、语音、环境声证据？ |
| Grounded generation | 能否只基于真正取得的证据生成正确 claim，并给出有效 citation？ |
| Agentic | 能否主动改写 query、切换 modality、调用工具、判断充分性并决定何时停止？ |

这条主线今天仍然存在，但它不再被当作三个松散的排行榜赛道。当前设计把它们重构成
一条可诊断的行为链：

```text
Acquire evidence
  -> Utilize / Ground evidence
  -> Decide whether to continue, stop, abstain, or recover
```

### 1.2 原始科学直觉

最初真正有价值的直觉是：

> 长视频系统“最后答对了多少题”不足以说明它是否可靠。

一个系统可能：

- 碰巧猜对，但没有取得足够证据；
- 找到相关片段，却漏掉决定性线索；
- 看到工具报错后，把“访问失败”误判为“视频里没有”；
- 在仍有可行检索路径时过早停止；
- 路径恢复后仍不重新检索，靠旧印象回答；
- 引用了片段，但 citation 并不能支持对应 claim。

因此原始 gap 并不只是“提高 QA accuracy”，而是希望观察 agent 在证据不完整、
工具受限和证据恢复时的行为。

---

## 2. 为什么原始 formulation 不够强

### 2.1 单个组件都不是足够的新颖点

项目自己的 related-work 和 preflight audit 得出的结论很严厉：

- necessary / multi-hop evidence 已有工作覆盖；
- audiovisual retrieval 和 bimodal necessity 已有工作覆盖；
- sufficiency verification、targeted re-retrieval、stopping 已有工作覆盖；
- tool-using long-video agent 已有工作覆盖；
- evidence attribution、counterfactual video evaluation 也已有工作覆盖。

所以如下论文故事都不够稳：

- “第一个 long-video Agentic RAG benchmark”；
- “第一个需要 audio + vision 的 benchmark”；
- “第一个研究 evidence sufficiency / stopping / recovery”；
- “第一个 evidence-grounded video QA benchmark”。

如果 AV-TRACE 只是把 retrieval、generation、agent 三类结果放在一起，容易被评价为
已有 benchmark 和方法的拼装。

### 2.2 原始设计过宽，难以形成可验证主张

早期设计试图同时包含 evidence deletion、distractor insertion、modality failure、
tool failure、ASR corruption、counterfactual replacement、budget sweep 等多种因素。
问题是：

1. 每种 intervention 都需要独立的有效性证明；
2. rights、annotation 和运行成本迅速膨胀；
3. 多个版本的 episode、metric 和 leaderboard 定义曾互相冲突；
4. 小规模 pilot 无法支撑 factorial interaction、ranking inversion 或显著性结论；
5. “删掉作者找到的一个 clip”不代表证据真的被移除了，因为可能存在 alternative
   evidence。

因此 2026-09-05 的 preflight 将 broad factorial framing 判为不可直接推进，并把
论文核心收窄为 **matched blocking and restoration**。

### 2.3 从“相关证据”升级到“充分且必要的证据”

这是 formulation 变化中最重要的一步。

#### Minimal sufficient evidence set（SES）

一个 SES 是一组能够支持全部目标 claims 的 evidence units，并且移除其中任何一个
成员后，至少一个目标 claim 不再被支持。它回答的是：

> agent 当前看到的证据是否真的足够，而不仅是“看起来相关”？

#### Necessity group

若同一事实在不同时间或 modality 中有替代证据，则任何单个 clip 都未必 necessary。
因此定义 necessity group：它必须与该 claim 的**每一个 accepted minimal SES**
相交。只有将该 group 的所有成员和 derived leaks 一起阻断，才能声称没有完整
accepted route 可达。

这使 AV-TRACE 的科学对象从“检索到某个标注 clip 没有”变成：

> 在枚举了替代支持路径后，系统是否真正取得了足以支持答案的证据集合？

### 2.4 Modality routing 不等于 modality necessity

两者在早期很容易混淆：

- **Modality routing** 是系统行为：它先搜 speech 还是 vision，失败后是否转向
  ambient，是否进行 cross-modal binding。
- **Modality necessity** 是题目属性：关闭某 modality 后，是否所有可接受 SES 都
  被破坏。

当前项目已经可以测 routing，但还不能声称 necessity。当前 NOAA 标签均是
machine-adjudicated hypotheses，没有人类完成 leave-one-modality counterfactual
和 exhaustive alternative search，因此 `Modality Recall` 被正确保留为 `null`。

### 2.5 哪些原始内容被保留，哪些被推迟

| 保留并强化 | Pilot-0 暂缓 |
|---|---|
| long A/V、V/S/A 三种 observation | ASR corruption |
| retrieval、grounded claims、citations | distractor insertion 作为核心 state |
| agentic search、query reformulation、routing | answer-flipping counterfactual replacement |
| sufficiency、abstention、stopping | generic retrieval-miss state |
| access failure 与 restoration | broad budget factorial |
| action-level trace 和 cost | open-system leaderboard |
| matched paired comparison | source-absence partition |

Counterfactual 的思想没有被否定，而是因为当时缺少可执行且 rights-aware 的媒体替换
操作，被移出 Pilot-0。当前用较窄的 **Claim-Response Consistency** 检查：
BLOCKED 时受影响 claim 应消失，RESTORED 后只有在重新 grounded 时才应回来。

---

## 3. 当前核心科学命题

当前 canonical thesis 可以概括为：

> **静态 clean-video accuracy 不能刻画长视频 agent 的可靠性。应在固定问题、
> 固定 claim–evidence graph、固定 backend 和预算下，对关键证据路径进行配对阻断
> 与恢复，测量系统能否识别证据不足、诊断访问失败、改变搜索策略并进行 grounded
> recovery。**

项目现在关注四个连续问题：

1. **Evidence acquisition：**系统有没有真正 search + inspect/read 到足够证据？
2. **Evidence utilization / grounding：**最终 claims 是否正确，且每个 claim 的
   citation 是否真的支持它？
3. **Sufficiency and stopping：**证据不足时，系统是否知道不足；若预算内还有可行
   route，是否过早停止？
4. **Recovery：**证据路径恢复后，系统是否改变策略、重新获取证据，并在同一预算内
   完成 supported answer？

一个有用的全局视图是：

```text
Long video
  -> full-timeline multimodal indexing
       vision | speech | ambient
  -> evidence acquisition
  -> evidence sufficiency / access diagnosis
  -> search reformulation / modality switch / stopping
  -> grounded answer + claim-level citations
  -> matched recovery and diagnostic metrics
```

这里的创新重点不是某个新 encoder 或 controller，而是把**干预本身设为实验单位**，
从 trace 中定位失败发生在 Acquire、Ground 还是 Act/Stop。

---

## 4. 整体 benchmark/protocol 是怎么工作的

### 4.1 一个 family，而不是三个无关问题

每个 family 固定：

- 一个 source video；
- 一个 question；
- 一组 atomic claims；
- 一个 claim–hop–evidence graph；
- 全部 accepted SES；
- 一个 necessity group 或 necessary channel；
- 同一套工具、预算和后端。

然后复制为三个状态：

```text
                  ┌─ CLEAN：至少一个 accepted SES 可达
同一个 family ────┼─ BLOCKED：关键路径不可达，且无 accepted SES 残留
                  └─ RESTORED：从 BLOCKED 起步，固定触发后仅恢复该路径
```

### 4.2 CLEAN / BLOCKED / RESTORED 的含义

**CLEAN**

- 正常证据路径可达；
- 用来建立在相同 backend 和预算下的正常能力基线。

**BLOCKED**

- 通过 `necessity_group_withholding` 隐藏所有必要 group 成员及其派生泄漏，或
  `modality_channel_outage` 关闭必要 channel；
- source video 本身仍有证据，但 agent 当前无法访问；
- 理想行为不是猜答案，而是降低 sufficiency、避免 unsupported claims，并识别
  `evidence_in_source_but_inaccessible`。

**RESTORED**

- 初始状态与 BLOCKED 相同；
- 预先声明的固定调用或 `get_channel_status` 触发恢复；
- 预算、问题、其他工具结果不变；
- 旧 pointer 不会自动变成证据，agent 必须重新 search 和 inspect/read。

### 4.3 Recovery 与 premature stopping

二者是同一决策问题的两面：

- **Premature stop：**最终 evidence 仍不足，但在剩余 budget 内存在 validator
  证明的可行 continuation route，系统却停止或无依据作答。
- **Recovery：**恢复触发后，系统沿可行 route 继续行动，重新取得 accepted
  evidence，并以 citations 支持最终 claims。

因此，“RESTORED 最后答对”还不够。系统还要证明：

1. trigger 真发生；
2. 路径确实恢复；
3. 证据在 trigger 后被重新取得；
4. 最终 claim–citation linkage 有效；
5. 整个过程未超预算。

### 4.4 工具和输出

固定工具面包括：

- `search_visual`
- `search_speech`
- `search_ambient_audio`
- `inspect_clip`
- `read_transcript`
- `get_channel_status`
- `finalize`

每个 action 都进入完整 trajectory。最终输出不是只写一句自然语言，而是包含：

- sufficiency verdict / probability；
- missingness cause；
- asserted claim slots；
- 每个 claim 对应的 citation IDs；
- abstention 与 recovery 信息。

### 4.5 Acquire / Ground / Act 三层指标

| 层 | 主要指标 | 解释 |
|---|---|---|
| **Acquire** | Evidence Recall、All-Evidence、Recall@K、first rank | 有没有找到并实际观察到完整 evidence set |
| **Ground** | Answer Score、Citation F1、Supported-Claim Rate | 答案是否正确，以及每个 claim 是否真的被所引证据支持 |
| **Act** | Success@Budget、Premature Stop、Recovery、query reformulation、modality switches | 是否在正确时机继续、切换、检查、停止或恢复 |

这一拆分很重要。例如，一个系统可以 Answer Score 较高，却 Citation F1 低；也可以
top-20 已含完整证据，但 agent 没有 inspect 到它；还可以证据不足却过早 finalize。

---

## 5. 项目演进时间线

### 阶段 A：宽 formulation 与 preflight 收敛（2026-09-05）

最初按综合 Agentic RAG benchmark 设计，并考虑多种 intervention 和 tracks。
related-work / preflight 发现：

- 广泛“首创”主张站不住；
- rights、schema、metric 和统计计划存在冲突；
- 小 pilot 无法支持 leaderboard 或 ranking inversion。

于是冻结新的 charter：

- 每个 family 只有 CLEAN/BLOCKED/RESTORED；
- 每个 family 只使用一种 intervention mechanism；
- Pilot-0 是 construct validation，而非 model ranking；
- 目标仍是未来 20–30 videos、60 families、4 systems、720 core runs。

### 阶段 B：synthetic protocol simulator

项目先建立 schema、semantic validator、固定工具 API、intervention runtime、
trajectory validation 和 deterministic replay。独立 red-team 证明其价值仅限于
协议管线，不能代表真实 A/V：

- 早期检索主要基于 metadata；
- agent 行为和结果有 fixture-oriented 成分；
- 一些 metric 定义和 denominator 不够严格。

这一步的意义是把 protocol 做成可执行对象，而不是得到科学结果。

### 阶段 C：真实 NOAA 媒体和 bounded Pilot-0（2026-09-09 至 09-10）

- 从官方 NOAA 资源中冻结并精确下载 5 个 29.54–63.02 分钟的视频；
- 总计约 3.81 小时、1,955,298,193 bytes；
- 5/5 hash、stream、beginning/middle/end A/V decode 通过；
- 初步扫描 120 个窗口，shortlist 30 个；
- 为控制成本，先在内容更合适的 `cand-049/051/052` 上审查 18 个窗口；
- Whisper/AST 跑满 18/18，机器裁决接受 6 个 family seed；
- 建成 18-window bounded real-A/V MVP。

### 阶段 D：Pilot-0 red-team 与语义指标修复（2026-09-10）

Task 89 发现五类 substantive limitation，包括：

- claim/citation 映射不够严格；
- Success@Budget 语义偏松；
- Premature Stop 没有 exact-final-point feasibility；
- ReAct 与 sufficiency controller 行为过于相似；
- low-N 标识不完整。

Task 90 重新生成 72 条轨迹并修复：

- public claim slots 与逐 claim citations；
- strict supported finalization；
- 72/72 final-point route certificates；
- 独立 evidence-sufficiency controller；
- 40/40 aggregate 全部标记 `LOW_N_DESCRIPTIVE_PILOT`。

决策保持：工程通过，科学仍不确定。

### 阶段 E：Scale-1A 全时间线（2026-09-11）

项目不再只在 18 个“已知有趣窗口”中检索，而是给五个完整视频建立固定时间网格和
多模态索引。初版曾被独立审计降为 `NO_GO`，原因包括：

- speech chunk 被投影到重叠窗口，造成 temporal leakage；
- “trajectory”缺少真实 action-level execution；
- strict Ground/Act 指标实际上没有执行；
- visual hard negatives 只是候选，不是 validated negatives。

修复后又发现：

- query reformulation gain 未实现；
- modality switch 定义不一致；
- 缺少 matched RESTORED no-trigger control；
- displacement 没有真正把 evidence 推出 top-5。

Task 99 完成第二轮修复；Task 100 最终确认 engineering GO，但 diagnostic 仍为
inconclusive。

### 阶段 F：Scale-1B Wave-R learned retrieval（2026-09-12 至 09-14）

Wave-R 冻结五个 retained family，只做 learned retrieval：

- CLIP vs SigLIP2；
- AST vs CLAP；
- BM25 speech 保持不变；
- fixed equal-weight RRF 比较不同 encoder 组合。

Task 104 red-team 又修复了：

- learned checkpoint 绑定了旧 model-manifest hash；
- fusion 未按 contract 应用 temporal binding；
-一个 control metric 与 persisted ranking 不一致；
- route suppression 被误表述成 full-universe rerank；
- CLAP spot-check 使用了与 production 不同的 decode path。

Task 105 最终审计通过，形成当前权威 Wave-R 结果。

---

## 6. 当前已经具备的资产和实现

### 6.1 五个 NOAA 长视频

| Asset | 主题角色 | 时长 |
|---|---|---:|
| `cand-045` | 教育 webinar | 29.54 min |
| `cand-047` | deep-ocean watch party | 33.06 min |
| `cand-049` | beach / bay safety | 41.09 min |
| `cand-051` | marine debris / conservation | 61.98 min |
| `cand-052` | weather / climate | 63.02 min |

五个视频都进入 Scale-1A/Wave-R 的**索引 candidate universe**。但 family 的形成经过
了更窄的 funnel：

```text
5 个视频
  -> 120 个 reconnaissance measurements
  -> 30 个 shortlist windows
  -> 先在 cand-049 / 051 / 052 上深审 18 个 windows
  -> 6 个 machine-provisional families
  -> full-timeline migration 后 5 个 retained families
```

`cand-045` 和 `cand-047` 没有进入当前 family evaluation，不是因为媒体失败，而是
因为 bounded review 优先选了后三个视频，尚未从前两个视频中产出 accepted
provisional family。它们仍作为 full-timeline distractor/cross-source candidate
参与索引。

### 6.2 Machine-adjudicated provisional labels

当前 family 不等于 benchmark gold。18 个 review window 经：

- 从原 MP4 精确区间解码；
- pinned Whisper Tiny English；
- pinned AST AudioSet；
- OpenCV / machine visual inspection；
- machine/Codex synthesis 和 red-team；

得到 6 accepted、10 deferred、2 rejected。所有关键 artifact 明确记录：

```text
MACHINE_ADJUDICATED_PROVISIONAL_MVP
human_reviewed=false
gold_annotation=false
```

并且当时的 `likely-necessary modalities` 是 **V=0, S=0, A=0**：这不是说没有
多模态线索，而是说没有一项通过人类 counterfactual 被证明为 necessary。

### 6.3 Pilot-0：bounded retrieval

Pilot-0 的冻结 index 只有：

- 18 个 reviewed window；
- 每个 window 的 vision / speech / ambient 三条 observation record；
- 共 54 records。

优点是能快速验证 intervention、tool-time decode、trajectory 和 metric semantics；
缺点是搜索空间已被人工预筛，不代表真正的长视频 localization 难度。

四类 baseline 是：

1. direct-long-context；
2. single-shot RAG；
3. ReAct recovery；
4. explicit evidence-sufficiency。

它们都是 deterministic protocol probes，不是 learned VLM/LLM。

### 6.4 Scale-1A：full-timeline multimodal indexing

Scale-1A 把五个视频铺在统一时间格上：

- 4 秒 base cell；
- 8 秒、stride 4 秒的 fine window；
- 32 秒、stride 16 秒的 context window。

三个 observation layers：

| Layer | 当前表示与用途 |
|---|---|
| **Vision** | OpenCV routing feature + pinned CLIP frame embedding；segment vector 由 cell pooling 得到 |
| **Speech** | pinned Whisper 的 30 秒 timestamped chunk；后经修复保持 chunk-unique search/citation lineage |
| **Ambient** | pinned AST AudioSet top labels，对 fine window 推理并聚合到 context |

索引支持 source-scoped primary 和 cross-source stress，使用固定 tie-break 和
label-independent temporal binding。搜索 pointer 本身不算证据，必须
`inspect_clip` / `read_transcript` 后才是 citable observation。

### 6.5 Action-level trajectories 与 strict metrics

当前轨迹记录：

- action / response 顺序；
- step 和 cost；
- search query、modality 和 observation；
- restoration trigger；
- final structured output；
- asserted claim 和逐 claim citation；
- actual finalization point；
- evaluator-private route-feasibility certificate。

这使项目可以区分：

- top-K 中有证据，但 agent 没有观察；
- 观察了证据，但没形成正确 claim；
- claim 正确，但 citation 不支持；
- 尚有 route，却过早停止；
- trigger 后路径恢复，但 agent 没有重新获取；
- 真正 grounded recovery。

### 6.6 Scale-1B Wave-R：SigLIP2、CLAP 与 controls

Wave-R 使用：

- **V-CLIP**：Scale-1A visual control；
- **V-SIGLIP2**：learned visual-text retriever；
- **A-AST**：AudioSet sparse/control；
- **A-CLAP**：learned audio-text retriever；
- **S-BM25**：speech lexical control；
- **F-CTRL / F-V / F-A / F-VA**：四种固定 fusion 组合。

Fusion 不是 learned：

```text
equal-weight RRF
rrf_k = 60
input depth = 20
V / A / S weights = 1 / 1 / 1
logistic fusion = disabled
```

原因是没有 disjoint training split，不能在五个 evaluation family 上训练或调参。
SigLIP2/CLAP 作为 frozen timeline 的 sidecar，不改变 segment identity。

### 6.7 独立审计为何重要

多个关键结论都经历了“先报 GO，再被红队推翻或收窄，再修复”的过程：

- Pilot-0：指标和 controller 语义被修复，但 scientific decision 没被强行提升；
- Scale-1A：Task 95 的 engineering GO 被 Task 96 降为 NO_GO；修复后 Task 98
  又发现三项 evaluation-layer blocker；直到 Task 99/100 才恢复 engineering GO；
- Wave-R：Task 103 的结果经 Task 104 修复 stale hash、temporal binding、
  metric/ranking mismatch 和 probe scope 后，Task 105 才确认。

这说明当前可信度主要来自：

1. artifact hash / trust anchor；
2. independent metric recomputation；
3. deterministic replay；
4. red-team 能实际改变 gate，而不是只做形式审查。

---

## 7. 三个阶段的实验与结论

## 7.1 Pilot-0：协议能否在真实 A/V 上跑通？

### 规模和当前权威决策

| 项目 | 数量 |
|---|---:|
| family-bearing videos | 3 |
| provisional families | 6 |
| reviewed windows | 18 |
| frozen index records | 54 |
| main trajectories | 72 |
| valid trajectories | 72/72 |
| no-trigger controls | 12/12 passed |
| intervention families | 6/6 passed |

```text
ENGINEERING_GO
PROVISIONAL_SCIENTIFIC_INCONCLUSIVE
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

### 汇总结果

以下数字跨 CLEAN/BLOCKED/RESTORED 聚合，必须视为 hypothesis-conditioned：

| Policy | All-Evidence | Answer | Citation F1 | Supported Claims | Success@Budget | Premature Stop | Recovery |
|---|---:|---:|---:|---:|---:|---:|---:|
| Direct long context | N/A | 0.6667 | 0.7407 | 0.8235 | 0.6667 | 0.0000 | N/A |
| Single-shot RAG | 0.2222 | 0.2222 | 0.4444 | 0.6250 | 0.2222 | 0.3889 | N/A |
| ReAct recovery | 0.6667 | 0.6667 | 0.7407 | 0.8235 | 0.6667 | 0.0000 | 1.0000 |
| Evidence sufficiency | 0.6667 | 0.6667 | 0.6667 | 1.0000 | 0.6667 | 0.0000 | 1.0000 |

按状态看，更直观：

- CLEAN：两个 agentic probe 在 6/6 family 上取得完整支持；
- BLOCKED：evidence-sufficiency 在 6/6 上 abstain，不输出 unsupported claim；
- RESTORED：两个 agentic probe 都在 6/6 上恢复；
- single-shot 在 RESTORED 的 6 个 family 中没有恢复，并有 5/6 premature stop。

### 它说明什么

它证明：

- matched state machine、阻断和恢复逻辑可运行；
- 系统级 trace 可以产生 Acquire/Ground/Act 的描述性差异；
- strict claim/citation、budget 和 final-point stopping 可实现。

它不证明：

- evidence-sufficiency 是更好的 learned agent；
- 1.0 recovery 会在真实模型或更大数据上出现；
- family 的语义、minimality 和 modality necessity 是正确的。

这些结果高度受 deterministic controller 和 18-window bounded universe 影响。

## 7.2 Scale-1A：进入完整时间线后，故事是否仍成立？

### 规模和决策

| 项目 | 数量 |
|---|---:|
| indexed videos | 5 |
| retained evaluation families | 5 |
| ordinary C/B/R trajectories | 120 |
| matched RESTORED no-trigger controls | 10 |
| displacement/control trajectories | 8 |
| total trajectories / actions | 138 / 654 |
| eligible query-reformulation rows | 76/76 non-null；12 positive |
| trajectories with modality-bearing sequence | 118 |
| trajectories with at least one switch | 36 |

```text
SCALE1A_ENGINEERING_GO
SCALE1A_DIAGNOSTIC_INCONCLUSIVE
FINAL_BENCHMARK_NOT_YET_VALIDATED
SCALE1A_MILESTONE_PROVEN
```

### 迁移结果

六个 provisional family 中：

- 保留：`r004`, `r007`, `r011`, `r016`, `r017`；
- 排除：`r014-aircraft-storm-view`，原因是
  `VISION_SUPPORT_NOT_TOP20`。

source-scoped CLEAN 的共同 retrieval 边界是：

- Recall@5 = **0.50**
- Recall@20 = **0.90**
- All-Evidence@20 = **0.80**

这意味着完整时间线里，5 个 family 中只有 4 个能在 top-20 收齐 provisional
evidence；而且 `r007` 仍未通过冻结的 Recall@5 shortcut criterion。

在 RESTORED 中，两个 agentic deterministic policy 能把上述 retrieval 边界恢复到
Recall@20 0.90 / All-Evidence@20 0.80，但 strict supported-answer recovery 只有
**0.20（1/5）**。No-trigger control 10/10 均没有完整 support。

validated-negative displacement 只对 speech families `r016/r017` 合格：

- 8/8 displacement proof 成立；
- recovery enabled 时 evidence reacquisition 4/4；
- supported answer recovery 2/4；
- disabled control evidence reacquisition 0/4。

### 它说明什么

Scale-1A 给出了比 Pilot-0 更诚实的结果：

- bounded 18-window 的成功不能直接外推到 full timeline；
- evidence 可以在 top-20，却未必被 agent 正确利用；
- agentic search 的“路径恢复”不等于最终 grounded answer recovery；
- hard-negative recovery 可以做，但当前只在两个 speech family 上有合格负例；
- 完整长视频检索确实暴露了 shortcut、distractor、temporal attribution 和 stopping
  问题。

为什么仍是 `DIAGNOSTIC_INCONCLUSIVE`：

- 只有 5 family、3 个 family-bearing source；
- `r007` shortcut criterion 失败；
- visual hard negatives 仍未被验证；
- deterministic policy，不是 learned agent；
- 没有人类 gold。

## 7.3 Wave-R：learned retriever 是否优于 controls？

### 规模和决策

| 项目 | 数量 |
|---|---:|
| retained / excluded families | 5 / 1 |
| systems | 9 |
| metric / paired rows | 64 / 40 |
| retrieval/probe rows | 132 |
| SigLIP source-frame / segment vectors | 3,433 / 4,283 |
| CLAP fine / context vectors | 3,428 / 855 |

```text
LEARNED_VISUAL_RETRIEVAL_READY
LEARNED_AUDIO_RETRIEVAL_READY
LEARNED_RETRIEVAL_READY
WAVE_R_DIAGNOSTIC_GO
FINAL_BENCHMARK_NOT_YET_VALIDATED
WAVE_R_MILESTONE_PROVEN
```

### 当前权威 source-scoped 结果

| Ranker | n | Recall@5 | Recall@20 | All-Evidence@20 | MRR |
|---|---:|---:|---:|---:|---:|
| V-CLIP | 4 | 0.25 | 0.50 | 0.50 | 0.1607 |
| V-SIGLIP2 | 4 | 0.25 | 0.25 | 0.25 | 0.0833 |
| A-AST | 1 | 0.00 | 1.00 | 1.00 | 0.1000 |
| A-CLAP | 1 | 0.00 | 0.00 | 0.00 | 0.0000 |
| S-BM25 | 2 | 1.00 | 1.00 | 1.00 | 1.0000 |
| F-CTRL | 5 | 0.50 | 0.90 | 0.80 | 0.3986 |
| F-V | 5 | 0.50 | 0.70 | 0.60 | 0.3367 |
| F-A | 5 | 0.50 | 0.70 | 0.60 | 0.3786 |
| F-VA | 5 | 0.50 | 0.50 | 0.40 | 0.3167 |

### 结果的正确解释

1. **Wave-R 的 GO 不是 superiority GO。**  
   预注册条件只要求出现可复现、跨 family 的非平凡 paired difference，并在
   cross-source 或 fusion boundary 中仍可见；改善不是必要条件。

2. **当前 learned retriever 多数更差。**
   - SigLIP2 的 visual Recall@20 为 0.25，低于 CLIP 的 0.50；
   - 唯一 ambient family 上，CLAP top-20 miss，而 AST hit；
   - 全替换 fusion F-VA 的 All-Evidence@20 为 0.40，低于 F-CTRL 的 0.80。

3. **这不是“SigLIP2/CLAP 普遍更差”。**  
   更合理的解释是：在当前 frozen query、segment pooling、NOAA domain 和
   machine-provisional support route 下，通用 learned encoder 不会自动优于
   domain/task-aligned control。

4. **样本太小，尤其 audio 只有 n=1。**  
   任何 population-level、显著性、SOTA 或架构优劣结论都不成立。

5. **Wave-R 只测 retrieval。**  
   route-suppression probes 是 clean top-20 的 suppression projection，
   `fresh_full_universe_rerank=false`；它们不等于 learned-agent recovery。

---

## 8. 当前最重要的发现

### 发现 1：工程问题已不再是主要未知数

项目已经具备从 source bytes 到结果表的完整、可审计链路：

```text
exact source identity
  -> deterministic segmentation
  -> V/S/A model observations
  -> frozen indices
  -> intervention runtime
  -> action trajectories
  -> claim/citation evaluation
  -> independent recomputation and replay
```

五视频完整索引、learned sidecar、hash binding、权限和 no-derivative policy 均已
多次验证。下一阶段不应继续把主要精力放在“再证明一次管线能跑”。

### 发现 2：bounded retrieval 会显著高估问题的容易程度

Pilot-0 在 18 个 reviewed window 中，agentic probe 的 All-Evidence 和 recovery 都
达到 0.6667/1.0；进入 full timeline 后，strict supported-answer recovery 只有
1/5。这个落差本身就是项目需要研究的现象：长视频系统失败不只因为答案生成，还因为
evidence localization、distractor burden 和 action policy。

### 发现 3：取得 evidence 与利用 evidence 是两回事

Scale-1A 中 top-20 acquisition boundary 可以达到 Recall 0.90 /
All-Evidence 0.80，但最终 Answer Score / Success@Budget 仅 0.20。说明：

- retriever 覆盖到证据，不代表 controller 会观察正确候选；
- 观察到部分证据，不代表会形成完整 supported claim；
- recovery route 开放，不代表 agent 会真正恢复。

这正是 Acquire / Ground / Act 分解的价值。

### 发现 4：显式 sufficiency controller 的主要价值目前是“少乱说”

在 bounded Pilot-0 中，evidence-sufficiency 的 Supported-Claim Rate 是 1.0；
在 Scale-1A 中它的 Premature Stop 为 0，而其他策略可能较高。这是有启发性的行为
信号。但 controller 是 deterministic，不能写成 learned reasoning 能力结论。

### 发现 5：更强通用 encoder 可能破坏既有检索边界

Wave-R 的负向结果值得保留。它提醒后续论文不要默认“换一个更强 backbone”就会改善
长视频 evidence localization。可能原因包括：

- query 与视觉/音频语义不匹配；
- 单帧/窗口 pooling 不适合目标 evidence；
- NOAA 内容与通用预训练分布差异；
- provisional support route 太窄或不完整；
- control 的标签空间恰好更贴近任务。

当前数据不能区分这些原因，因此下一步应先做 failure analysis 和人工复核，而不是
立即堆更多 retriever。

### 发现 6：独立审计是项目现有最强资产之一

Scale-1A 的两次 NO_GO 和 Wave-R 的 post-repair 变化说明：项目不是把绿色 test
等同于科学正确性。审计实际抓出了 lineage leak、伪 action trace、metric
substitution、缺失 control、stale hash、fusion binding 和 scope overclaim。这种
“可被推翻、可追溯修复”的过程会是未来 artifact/reproducibility 叙事的优势。

---

## 9. 哪些结论现在还不能说

### 9.1 不能说“benchmark 已验证”

所有当前结果都带有：

```text
human_reviewed=false
gold_annotation=false
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

这是最重要的边界，不是措辞细节。

### 9.2 不能说存在 human-valid minimal sufficient evidence

当前 support set 是 machine-adjudicated provisional route。尚未完成规范要求的：

- 独立 full-source alternative search；
- 人类 leave-one-out minimality；
- necessity-group hitting-set 验证；
- 两名独立 validator 的完整 C/B/R 判断；
- adjudication 和 freeze。

因此当前的 “All-Evidence” 应理解为“覆盖了登记的 provisional support set”，
不是覆盖了最终 gold SES。

### 9.3 不能说某 modality 是必要的

当前可以说：

- 某个 family 被设计为 vision/speech/ambient routing case；
- 某 channel 被关闭后，登记的 provisional route 消失。

不能说：

- 该问题客观上必须用这个 modality；
- 其他 modality 或其他时间段不存在替代支持；
- `Modality Recall` 已被测量。它目前是 `null`。

### 9.4 不能完整声称“区分 source absence 与 access failure”

Pilot-0 没有 source-absence partition。当前能测的是：

- CLEAN/RESTORED 终态应为 `not_missing`；
- BLOCKED 应识别为 `evidence_in_source_but_inaccessible`。

由于没有真正“源中不存在证据”的正样本，双向区分能力尚未被完整识别。

### 9.5 不能说 learned agent 会 recovery

- Pilot-0/Scale-1A 的 controller 是 deterministic protocol probe；
- Wave-R 只运行 learned retrieval；
- 没有 learned evidence-conditioned generator；
- 没有 learned ReAct / learned sufficiency controller 的端到端 trajectory。

因此 learned retrieval 的 route-suppression 结果不能升级为 learned-agent recovery。

### 9.6 不能说 learned retriever 更强或更弱

Wave-R 只能说：

> 在五个 frozen provisional family 上，特定 pinned SigLIP2/CLAP 配置与 controls
> 产生了可复现的排序差异，并且当前方向主要是 degradation。

它不能支持：

- 通用模型排名；
- architecture superiority；
- statistical significance；
- NOAA 以外的 generalization。

### 9.7 不能把当前视频称为可公开发布的 public core

视频的 restricted acquisition、技术处理和内部实验已经有严格记录；但 raw media、
clips、transcripts、annotations、features 及模型 snapshot 的对外再分发仍需独立
release review。当前 NOAA MVP 设计也将这些资产放在
`EXTERNAL_COMPATIBILITY_UNPOOLED` 边界，而非已批准的 public core。

### 9.8 仍有两处值得正式收口的规范不一致

1. **Restoration gain endpoint：**规范文字曾把 BLOCKED 的“正确不足诊断”和
   RESTORED 的“正确 grounded answer”直接相减；早期 red-team 已指出这是异质
   outcome。后续实现倾向使用共同的 supported-answer endpoint，但 decision log /
   metrics protocol 应正式版本化修订。
2. **Premature Stop 与 abstention：**规范允许“仍有可行 route、却未声明 recovery
   route 的 abstention”被视为 premature；Task 90 实现说明则写成 abstention 不计。
   在正式人类 pilot 前必须统一。

另有一个较小的命名演进：早期 Scale-1B inventory 将 learned fusion 视为
`LEARNED_RETRIEVAL_READY` 的条件；Wave-R 后来把该 gate 收窄为 learned modality
retriever readiness，并明确使用 fixed RRF。这是可解释的 scope change，但最好在
decision log 中补一条 superseding decision。

还应注意两处历史 artifact 差异：

- 早期 `scale1b_wave_r_go_no_go.md` 把 source-scoped F-CTRL MRR 写为
  **0.3886**；post-repair `report.json` 与 Task 105 final audit 的当前权威值是
  **0.3986**。变化来自 Task 104 对 temporal binding 和“从 persisted ranking
  重算 metric”的修复。
- Scale-1A 设计阶段使用过
  `MACHINE_ADJUDICATED_PROVISIONAL_SCALE1A`，当前结果 artifact 使用
  `MACHINE_ADJUDICATED_PROVISIONAL_MVP`。两者都表达 non-human-gold 边界，但
  正式 release 前应统一 stage vocabulary。

---

## 10. 与 CVPR main 的距离

### 10.1 当前强项

1. **科学问题经过主动收窄。**  
   不再依赖“first Agentic RAG”之类脆弱主张，而是聚焦 matched causal
   intervention 和 trace-level failure diagnosis。

2. **protocol 设计严谨。**  
   SES、necessity group、C/B/R、deterministic restoration、no-trigger control、
   claim-level citation、final-point feasibility 都比一般 QA benchmark 更细。

3. **工程和 reproducibility 较强。**  
   精确 source/model revision、hash、restricted artifact、deterministic replay、
   independent recomputation、fail-closed verifier 都已落地。

4. **已经有真实数据和真实 learned retrieval。**  
   不再只是 synthetic toy；完整五视频 timeline、CLIP/Whisper/AST、SigLIP2/CLAP
   都实际运行过。

5. **有非平凡负结果。**  
   learned encoders 在当前任务上反而退化，且不是因为工程失败。这种结果若经
   human-valid 扩展，可能形成有价值的 benchmark finding。

### 10.2 当前 paper-level 弱点

1. **核心 construct 没有人类验证。**  
   对 benchmark paper 来说，这是最致命的问题。没有 gold SES 和 necessity，
   C/B/R 的科学含义仍是 provisional。

2. **样本极小且来源集中。**  
   5 个 scored family、3 个 family-bearing NOAA 视频，audio comparison n=1；
   无法做 video-cluster uncertainty 或领域泛化。

3. **只有 Acquire 的 learned evidence。**  
   Ground 和 Act 尚由 scripted controllers 承担，论文核心却是 agent reliability。

4. **intervention 类型覆盖不足。**  
   当前主要是 route withholding / channel outage；source absence 未覆盖，
   counterfactual utilization 被 deferred；validated negatives 只覆盖两个 speech
   family。

5. **当前结果可能受 provisional route 错误影响。**  
   learned retriever 找到但未被登记的新 evidence 会被记为 miss；因此负结果必须在
   人工 alternative-support 审查后再解释。

6. **没有具有说服力的 comparative finding。**  
   目前最强结果是“协议可运行”和“retriever 排名不同”；还没有展示 static clean
   accuracy 无法预测 intervention robustness 的跨模型证据。

### 10.3 当前应被称为什么

最准确的标签是：

> **一个成熟的 research infrastructure、经过红队的 real-A/V MVP，以及一个
> low-N learned-retrieval diagnostic。**

它还不是最终 benchmark，也不是完整 paper；但也不只是普通工程脚手架，因为：

- 核心干预语义已经可执行；
- action-level measurement 已经存在；
- full-timeline 与真实 learned retrieval 已经给出非平凡结果。

### 10.4 什么结果会让论文故事变得 compelling

至少需要出现以下组合：

1. 人类验证表明大多数候选能可靠形成 SES、necessity group 和 isolated C/B/R；
2. 多个独立视频上，模型在 CLEAN accuracy 接近，但在 BLOCKED 的
   false-sufficient / access diagnosis、RESTORED recovery、premature stop 上明显
   分离；
3. 这种分离不能由 retrieval recall 一项解释：需要展示
   “检索到了但没利用”“知道不足但不会恢复”“会恢复但 citation 不 grounded”等
   不同 failure modes；
4. learned sufficiency-aware controller 相比 learned ReAct 或 single-shot baseline
   有可复现行为差异，而不是由硬编码 trigger 造成；
5. 负向 learned-retrieval 结果经人工重新判定后仍成立，并能归因到具体问题，如
   query mismatch、temporal pooling 或 domain-label alignment；
6. 有足够多 source-disjoint video cluster 来给出不依赖个别视频的 uncertainty。

### 10.5 大规模扩数据前的最低里程碑

**不要把“新增很多视频”作为下一步第一优先级。**  
大规模扩张前最低应完成一个 **human-validated mini-pilot**：

- 约 8–12 个 family；
- 覆盖至少 5–6 个 source-disjoint 视频；
- 每个 family 有独立 author、alternative finder、validator A/B、adjudicator；
- 完成答案、evidence、alternative SES、minimality、necessity、modality
  counterfactual、pair isolation；
- 至少有 vision、speech、ambient、cross-modal；
- 在 learned retrieval 下重新搜索未登记的 alternative support；
- 至少跑一个 learned generator 和两个 learned controller；
- 给出接受率、排除原因、人工一致性、annotation labor 和 failure taxonomy。

如果这一小关无法稳定通过，就不应投入 20–30 视频 / 60 family 的生产规模。

---

## 11. 下一阶段建议

### Priority 0：先冻结科学语义和指标口径

在新实验前完成三个小但关键的版本化修订：

1. 将 restoration gain 明确定义为共同 supported-answer endpoint；
2. 统一 premature-stop 对 abstention / recovery-route declaration 的处理；
3. 在 decision log 中说明 Wave-R 的 `LEARNED_RETRIEVAL_READY` 不要求 learned
   fusion，fixed RRF 是无独立训练集时的正式 baseline。

**原因：**如果 metric semantics 继续漂移，增加数据只会放大后续返工。

### Priority 1：人工验证当前 family，并做 learned-retrieval failure analysis

先复核当前 5 个 retained family 和 `r014`：

- 从完整 source blind search alternative evidence；
- 审查 SigLIP2/CLAP top-ranked “false positives”和 control-only hits；
- 判定 learned model 是否发现了未登记但真实有效的 alternative；
- 重做 answer、claim、time interval、SES、necessity group；
- 做 silent-video、transcript-only、ambient-only 等 counterfactual；
- 对 `r004` ambient、`r016` corroboration 特别谨慎。

**为什么第一优先级不是更多视频或更强 retriever？**  
因为当前最大风险是 label/construct error，而不是 model capacity。若 support
registry 不完整，更多模型只会更快地产生不可解释的 miss。

### Priority 2：做一个 human-validated mini-pilot

从当前三视频中保留通过者，再从 `cand-045/047` 或少量新视频补齐到 8–12 family、
5–6 个 source cluster。报告：

- candidate → accepted funnel；
- inter-annotator agreement；
- alternative SES discovery rate；
- necessity / modality ablation pass rate；
- pair-isolation failure rate；
- 每个 family 的 annotation labor。

这是决定是否扩到 60 family 的真正 go/no-go。

### Priority 3：接入 learned grounded generation 和 learned agents

在 human-valid family 上实现 Scale-1B 后续 Wave G/A：

- evidence-conditioned structured generator；
- learned ReAct controller；
- learned explicit-sufficiency controller；
- 相同 backend、相同预算、相同 output schema；
- timeout、malformed JSON、OOM、over-budget fail closed。

最关键的实验不是谁总分最高，而是：

```text
clean accuracy 相近
但
BLOCKED FSR / access diagnosis / premature stop / RESTORED recovery 不同
```

这才直接支持论文 thesis。

### Priority 4：修 retriever，但以失败类型驱动

在完成 failure analysis 后，针对性选择：

- temporal video encoder 或 multi-frame representation；
- speech-aware / OCR-aware visual retrieval；
- domain-adapted audio labels或 query expansion；
- query decomposition；
- learned fusion——但必须有 disjoint training split。

不要先无目的替换更大的通用 encoder。Wave-R 已表明这不保证提升。

### Priority 5：达到 construct gate 后再扩视频和问题

若 mini-pilot 的 human acceptance、intervention isolation 和 learned-agent
separation 令人信服，再扩到 charter 目标：

- 20–30 source-disjoint videos；
- 60 families；
- 180 episodes/system；
- 4 systems、720 core runs；
- video-cluster uncertainty；
- modality/mechanism strata。

扩张时优先增加：

1. source diversity，而不是同一视频堆题；
2. ambient 和 cross-modal 的有效 family；
3. 多个 alternative SES 的 item；
4. learned retrieval 易失败但人类可清楚判定的 case；
5. public-core rights/release 可闭环的资产。

### Priority 6：最后才是论文主写作

现在可以维护：

- one-page thesis；
- figure skeleton；
- related-work matrix；
- limitation ledger。

但不应先写完整主论文。论文叙事应由 human mini-pilot 和 learned-agent 结果决定：

- 若 clean 相近而 recovery 显著分离，主线是 **causal resilience**；
- 若大量 family 无法通过 necessity 验证，主线可能转为 benchmark construction
  difficulty / negative result；
- 若 retriever degradation 经 human audit 仍普遍，主线可以强调
  representation-dependent evidence localization。

---

## 12. 关键文件阅读导航

### 想先理解“项目是什么”

1. `docs/project_charter.md`  
   当前 canonical mission、Pilot-0 边界和三层结论。
2. `docs/spec/benchmark_v0.md`  
   family、SES、necessity group、CLEAN/BLOCKED/RESTORED。
3. `docs/spec/metrics_protocol.md`  
   sufficiency、premature stop、recovery 和 dashboard。
4. `docs/research/novelty_boundary.md`  
   为什么不能再用宽泛的 Agentic RAG novelty。

### 想理解真实媒体如何进入系统

1. `docs/review/noaa_final_selection.md`
2. `docs/review/noaa01_content_recon.md`
3. `docs/review/noaa01_machine_adjudication.md`
4. `docs/design/noaa01_real_av_mvp_design.md`

### 想看 Pilot-0 当前权威结果

1. `docs/review/noaa01_real_av_semantic_metrics_repair.md`
2. `docs/review/core_milestone_completion_audit.md`
3. `mvp/results/noaa01_real_av_mvp/report.json`
4. `orchestration/results/90_real_av_semantic_metrics_repair.txt`

### 想看 full-timeline 的设计和最终结果

1. `docs/design/scale1a_full_timeline_design.md`
2. `data/rehearsal_plan/scale1a_full_timeline_plan.json`
3. `docs/review/scale1a_full_timeline_redteam.md`：首次 NO_GO 的原因
4. `docs/review/scale1a_post_repair_audit.md`：第二轮 blocker
5. `docs/review/scale1a_final_audit.md`：当前权威审计
6. `mvp/results/scale1a_full_timeline/report.json`

### 想看 learned retrieval

1. `docs/design/scale1b_learned_baseline_inventory.md`
2. `data/rehearsal_plan/scale1b_learned_baseline_plan.json`
3. `docs/design/scale1b_wave_r_experiment_contract.md`
4. `data/rehearsal_plan/scale1b_wave_r_trust_anchor.json`
5. `docs/review/scale1b_wave_r_redteam.md`
6. `docs/review/scale1b_wave_r_final_audit.md`
7. `mvp/results/scale1b_wave_r/report.json`

### 如何处理互相冲突的历史文件

- charter / accepted decisions 决定当前 scientific contract；
- 当前结果解释以 Task 90、Task 100、Task 105 的 post-repair audit 为准；
- Task 96、98、104 等 red-team 文件用于解释为什么结论曾改变；
- pre-repair report 中与当前 ranking、fusion 或 probe scope 不一致的数字，只保留为
  历史 provenance，不应作为当前结论。

---

## 13. 术语表

| 术语 | 简明解释 |
|---|---|
| **Family** | 同一问题和同一 evidence graph 的 CLEAN/BLOCKED/RESTORED 三联体。 |
| **Evidence unit** | 带 source-time 和 modality provenance 的原子观察。 |
| **Claim** | 最终答案中可独立判断和引用的原子命题。 |
| **SES** | Minimal sufficient evidence set；足以支持目标 claims，且删除任何成员都会失去部分支持的证据集合。 |
| **Necessity group** | 与所有 accepted SES 相交的一组可替代 evidence；整体阻断才使目标支持不可达。 |
| **CLEAN** | 至少一个 accepted SES 可达。 |
| **BLOCKED** | 源中仍有证据，但登记的必要 route/channel 不可访问，且无 accepted SES 可达。 |
| **RESTORED** | 从 BLOCKED 的同一初态开始，固定 trigger 后只恢复原阻断路径。 |
| **Acquire** | 检索并实际 inspect/read 到证据。 |
| **Ground / Utilize** | 用取得的证据支持正确 claim 和 citation。 |
| **Act / Stop** | query reformulation、modality switching、channel check、继续、停止、abstain 或恢复。 |
| **Modality routing** | 系统选择或切换 vision/speech/ambient 的行为。 |
| **Modality necessity** | 题目是否在所有有效支持路径上都必须依赖某 modality；当前尚无人类验证。 |
| **Premature stop** | 证据仍不足且预算内仍有可行 route，却过早终止。 |
| **Recovery** | restoration 后重新取得 accepted evidence 并完成 supported finalization。 |
| **No-trigger control** | 执行相同前缀但禁用 restoration，用来证明恢复不是自然发生或由泄漏造成。 |
| **Source-scoped** | 只在该 family 所属视频内检索；当前 primary retrieval scope。 |
| **Cross-source** | 在五个视频全部候选中检索；单独报告的 stress test。 |
| **RRF** | Reciprocal Rank Fusion；当前使用固定、等权、非 learned 的 rank fusion。 |
| **Machine-provisional** | 机器/model/Codex 裁决的暂定标签，不是人类 gold。 |
| **Engineering GO** | 管线、contract、replay、hash、metric 可执行；不等于科学命题成立。 |
| **Diagnostic GO** | 达到预先定义的描述性差异条件；不等于模型更优或 benchmark 已验证。 |

---

## 最终定位

### 2026-10-23 Canary2 R22 终局状态

R22 的 one-shot 已实际消费并永久关闭，终局 token 为
`R22_SCIENTIFIC_NO_GO_PERMANENT_R23_REQUIRED`。不得重跑 R22、换 reserve、重抽
reserve、复用 receipt，或把保留输出的离线回放安装成 R22 success。后续若继续，
必须是独立预注册、独立选择、独立授权的 **R23 新实验**，不是 R22 retry。

R22 顶层 exception
`COMPOSITION_COMPONENT_LOCAL_BINDING_INVALID:1` 是 component-local validator
实现缺陷：它把句内已有明确先行词的 `it` 误判为 unresolved continuity。
确定性重建证明 exact binding/provenance 本身为 PASS（13 accepted factors、
26 bound final rows、无 cross-factor substitution）。

但该实现缺陷不改变科学结论。即使假设修复 validator 并仅回放保留输出，仍有
3 对 exact duplicate 及对应 near collision，且一对 family-compositional
query 以两个方向记录 `0.92592593 > 0.92`，另有 1 个跨 family ambient tuple
duplicate。因此 R22 的 SCIENTIFIC NO-GO 独立成立。真实执行账本为 13 calls、
5 decodes、0 repair、0 retrieval/scoring；marker 与真实 failure capsule
完整。R21 的历史 NO-GO 单独保留，R22 不覆盖 R21。

权威终局记录：

- `docs/review/p23_102_canary2_r22_terminal_audit.md`
- `data/rehearsal_plan/p23_102_canary2_r22_terminal_public.json`
- `data/restricted/p23_102_canary2_r22_terminal_detailed_audit.json`

AV-TRACE 目前最值得保留的不是某个单独 baseline 的分数，而是一条已经被工程化的
研究主线：

```text
不是只问“答对了吗？”

而是问：
  找到足够证据了吗？
  真的使用了这些证据吗？
  证据不足时知道吗？
  知道是访问失败而不是源中不存在吗？
  会改变策略吗？
  路径恢复后会重新取证并修正答案吗？
  还是在可恢复时过早停止？
```

这条主线有成为强 benchmark paper 的潜力。当前仓库已经把最难的工程和审计底座
搭得很完整；下一步能否跨过论文门槛，主要取决于**人类 construct validity** 和
**真实 learned-agent behavioral separation**，而不是再增加一轮工程证明。
