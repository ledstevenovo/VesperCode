# VesperCode 任务交接与规格收敛方法论

> 面向对象：一个完全不了解当前聊天记录的新 Codex 对话。
> 交接日期：2026-07-15（Asia/Taipei）。
> 权威分支：`origin/main`。
> 历史 Phase 2 现场：本文最初创建前，`main` 与 `origin/main` 曾均指向 `64de2a3846c05b81ad69909a6e59be976e87d2c1`；该 SHA 不代表本轮最终 HEAD。
> 本轮合同修正以 `cf720407af69aaac235b2bb0f7923fecd0544c68` 为基线，在 `codex/ch3-review-fixes` 分支实施。合并后开启新对话时必须先成功 fetch，并以当时最新 `origin/main` 为准，不得把本文中的历史或基线 SHA 当作最终提交。

## 1. 一分钟摘要

VesperCode 是课程项目 **Coding Agent Harness**。当前仓库仍处于规格阶段，没有进入实现阶段。

当前状态：

- `SPEC.md` 第 1、2 章和第 3 章 3.1—3.5 已有正文；
- 本轮针对 3.1—3.5 交叉审阅发现的 14 项问题，已经写入最小合同修正；
- `bd50d82` 闭合正式 3.3.7 启动终止，`a125dfe` 随后完成 Demo 同构修复；固定 `a125dfe` 后的规范审查通过，但文档质量审查与无背景冷审仍发现剩余缺口，当前分支已写入最小修正，状态仍为“等待新 SHA 复审”；
- 3.5 仍只有九个小节，3.5.9 仍是唯一且连续编号 1—21 的固定验收清单；
- 仓库仍处于规格阶段，没有权威课程 `PLAN.md` 或实现代码。

上述本轮修正尚未取得新的审查结论。本交接不提前记录通过；3.1—3.5 只有待本轮只读规范符合性审查、文档质量审查和无背景范围冷审实际通过后才可重新锁定。完整第三章仍须完成 3.6—3.12，并接受全章交叉审查。

当前 `SPEC.md` 在 **3.5.9** 结束，尚未形成 3.6—3.12 正文。下一项推荐任务是设计并审查：

```text
3.6 CandidateRevision、恢复修订和 FinalDiff
```

后续工作必须继续遵守一个核心边界：**v1 只定义课程周期内可实现、可演示、可由 mock/stub LLM 离线确定性验证的功能合同，不再把功能规约扩张成通用崩溃一致工作流引擎。**

## 2. 仓库与 Git 现场

### 2.1 权威状态与历史 Phase 2 现场

- 远端：`origin`，GitHub 仓库 `ledstevenovo/VesperCode`。
- 权威分支：`main`。
- 本轮交叉审阅修正基线：`cf720407af69aaac235b2bb0f7923fecd0544c68`。
- 本轮修正分支：`codex/ch3-review-fixes`；合并后仍以成功 fetch 得到的最新 `origin/main` 为唯一新任务起点。
- 以下只属于历史 Phase 2 现场：合并前置提交 `64de2a3846c05b81ad69909a6e59be976e87d2c1`，功能分支 `codex/spec-v1-stage35-reset`，以及最终冷审范围 `1759f0f..2ace4bc` 后的证据日志提交 `64de2a3`。
- 历史 Phase 1 检查点分支为 `spec-v1-scope-reset`，最终提交 `1759f0fcb96ee6f6e31fb2e2ee07beebaa832c67`；这些历史引用都不是当前或未来最终 HEAD。

以下命令假设本机已安装 Git、网络可访问 `origin`，并且调用方有权读取该仓库。新对话开始时使用明确的仓库路径执行：

```powershell
$repo = 'D:\code\VesperCode'
git -C $repo fetch origin
git -C $repo rev-parse origin/main
git -C $repo status --short --branch
git -C $repo worktree list --porcelain
```

不要假设本文中的前置 SHA 仍是最新 HEAD；以成功 fetch 后的 `origin/main` 和当前 Git 输出为准。如果 fetch 失败，不得基于未核实的旧 `origin/main` 继续。

### 2.2 本地 worktree 安全边界

当前机器曾存在以下 worktree：

| 路径 | 分支 | 处置 |
|---|---|---|
| `D:\code\VesperCode` | `codex/fix3.1-3.4` | 根目录含未跟踪用户文件，不得切分支、reset、清理或覆盖 |
| `D:\code\VesperCode\.worktrees\spec-v1-scope-reset` | `spec-v1-scope-reset` | Phase 1 历史 worktree，只读保留 |
| `D:\code\VesperCode\.worktrees\spec-v1-stage35-reset` | `codex/spec-v1-stage35-reset` | Phase 2 历史 worktree，只读保留；曾出现无内容 diff 的行尾/stat 标记，不要顺手归一化 |
| `D:\code\VesperCode\.worktrees\main-merge` | `main` | 用于合并和创建本文；下一独立任务仍建议创建新 worktree |

新任务推荐从最新 `origin/main` 创建新分支和新 worktree，例如：

```powershell
$repo = 'D:\code\VesperCode'
$next = 'D:\code\VesperCode\.worktrees\spec-v1-chapter36'
git -C $repo fetch origin
git -C $repo worktree add -b codex/spec-v1-chapter36 $next origin/main
git -C $next status --short --branch
```

如果目标目录或分支已经存在，先停止并检查，不要自动改名、复用或删除。

“不得修改根目录”是指不得改写、暂存、清理或切换 `D:\code\VesperCode` 根 worktree 的已跟踪/未跟踪内容；通过 `git worktree add` 在其 `.worktrees` 子目录创建隔离 worktree 是允许且推荐的操作。

### 2.3 不得误用的本地文件

根目录 worktree 中曾出现未跟踪的 `PLAN.md`、`REFLECTION.md`、`AGENT_LOG.md`、`AGENTS.md` 和 `.gitignore`。这些文件属于另一分支/用户现场，不在当前 `main` 的权威提交中。未经逐文件审阅和用户授权，不得把它们复制、暂存或删除。

当前 `main` 仍没有批准完成的 `PLAN.md`，也没有实现代码。课程实现阶段尚未获准启动。

## 3. 当前权威文档

| 文件 | 当前职责 |
|---|---|
| `AI4SE_Final_Project_通用要求.md` | 课程通用要求，最高层外部来源 |
| `AI4SE_Final_Project_A_Coding_Agent_Harness(1).md` | Coding Agent Harness 专项要求 |
| `SPEC.md` | 当前功能规约；正文已完成到 3.5.9 |
| `SPEC_PROCESS.md` | brainstorming、审查、采纳/拒绝建议和范围重置历史 |
| `AGENT_LOG.md` | 实施代理、审查代理、提交、人工决定和验证证据 |
| `README.md` | 当前项目入口说明；实现阶段后仍需扩充 |
| `TASK_HANDOFF.md` | 本交接文档，不替代 `SPEC.md` 的规范效力 |

发生冲突时，优先级为：课程源文档 → `SPEC.md` 当前合同 → `SPEC_PROCESS.md` 的当前审查规则 → 本交接文档。3.1—3.5 的本轮修正待只读审查通过后才可重新锁定；历史过程记录不能覆盖当前规范。

## 4. 当前规格正文与本轮修正范围

### 4.1 3.1：共同不变量

当前合同内容：

- 信任边界和模型无授权权力；
- 解析、绑定、治理、授权、执行、验证、记录的共同顺序；
- 外部副作用、生命周期转换、一次性批准/预算、唯一发布和工作区写入的幂等边界；
- 统一错误信封、脱敏、规范化和摘要绑定；
- 3.1.2 只冻结语义输入、权威输出、绑定、原子可观察边界和稳定错误；数据库字段、CAS、摘要 DAG 与事务拓扑下放到架构、数据模型和 `PLAN.md`；
- 状态空间强类型隔离；
- `RECONCILIATION_REQUIRED` 只服务 3.10 持久化恢复，不是通用错误路线；
- mock/stub 环境下的确定性验证约定。

已经删除或下放：通用 generation、worker claim、WAL/outbox、通用 reconciliation 算法。

### 4.2 3.2：生命周期与用户等待

保留三个 `WaitKind`：

```text
DISCLOSURE_AUTHORIZATION
CONFIRM_REPRODUCTION_APPROVAL
FINAL_PERSISTENCE_APPROVAL
```

本地动作策略只有规定的复现确认动作和最终持久化动作可以进入 `ASK`；披露授权属于独立状态空间。不要重新引入通用 `ACTION_APPROVAL`，除非第 2 章产品承诺被用户显式修改。

生命周期仍采用六状态、六阶段、唯一转换矩阵、取消安全点、唯一停止原因和 3.10 专用持久化恢复。

稳定细分 `error_code` 只表达诊断，`StopReason` 只表达生命周期停止原因；3.2.6 的带上下文映射是两者之间的权威转换，不得把同一名称在两个状态空间混用。

### 4.3 3.3：准入与重启

当前合同内容：

- 进程持有的 OS 排他锁；
- 唯一、不可转授、无 TTL 的 `workspace_lease_ref`；
- 进程重启创建新 lease ref；
- 获取锁后的旧运行失败关闭/持久化恢复门；
- 正式 `PROCESS_RESTARTED_DURING_RUN` 启动终止必须以同一 CAS／权威提交全有或全无地闭合旧运行：已开始且无结果的 `AdmissionCheckAttempt → UNKNOWN`，未开始或无法安全启动的 attempt → `NOT_RUN(CONTROL_PLANE_ABORTED)`，未完成 `AgentTurn → TURN_ABORTED + RUN_STOPPED`；已有 outcome 和已终局对象不得改写；
- 正式旧 turn 在 checkpoint 前必须闭合 `AgentFeedbackConsumptionManifest` 并全量关闭 reservations 且不消费；checkpoint 后无 outcome 时必须闭合 `AgentFeedbackConsumptionManifest`、保持 reservations 已消费并保留披露／预算事实与真实适配器可能已调用的不确定边界，不得创建 outcome、调用、恢复或重发适配器；
- `REPOSITORY_STATE` 只验证 HEAD/index 可解析性、支持的仓库结构与策略机制，并发布 `RepositoryPolicySnapshotRef`；
- `SNAPSHOT_TREE` 唯一判定实际工作区的 HEAD/index 清洁性、非忽略未跟踪状态、tracked 原始字节与 mode，以及双观察之间是否发生变化；
- `CONFIG_SNAPSHOT` 只能读取目标仓库外的控制面配置；仓库内 pytest、Ruff、Mypy 等项目配置必须在 Snapshot 发布后由 `PROJECT_PROFILE` 从不可变快照读取；
- 旧进程遗留的非终态 Demo 运行必须以旧 `run_id`、旧 `process_instance_ref`、session、进程内配额 reservation、`lifecycle_revision` 和适用阶段绑定执行启动 CAS；不得取得、要求或伪造正式 `WorkspaceIdentityRef`、工作区 OS 锁或 `workspace_lease_ref`；
- `DEMO_SESSION_INVALIDATED` 必须在同一 CAS／权威提交中全有或全无地形成 `StopReason = INTERNAL_ERROR`、完整 `StopRecord`，并按正式路线的同一规则闭合无结果 `AdmissionCheckAttempt`、未完成 turn、`AgentFeedbackConsumptionManifest` 与 feedback reservations：已开始 Admission attempt → `UNKNOWN`，未开始或无法安全启动的 attempt → `NOT_RUN(CONTROL_PLANE_ABORTED)`，未完成 turn → `TURN_ABORTED + RUN_STOPPED`；checkpoint 前关闭且不消费，checkpoint 后无 outcome 保持已消费、只保留已持久化预算事实与 Mock adapter 可能已调用的不确定边界，且不创建 outcome、调用、恢复或重发 Mock adapter；已有 outcome 和已终局对象不得改写，旧绑定迟到结果必须拒绝；
- 敏感路径、Docker-only 和 Demo 隔离保持有效。

v1 不定义 takeover、fencing generation、TTL 转授、人工强制清除或 admission block。

### 4.4 3.4：快照、执行副本、基线与 Manifest

当前权威链：

```text
RepositoryPolicySnapshot
→ SnapshotTree
→ ExecutionWorkspaceEvidence
→ BaselineEvidenceSet
→ BaselineDecision
→ ValidationManifestV1
→ ReproductionEvaluation(CONFIRMED)
→ ValidationManifestV2
```

重要合同：

- 正式 consumer 使用不同的全新执行副本；
- workspace instance/root identity 不复用；
- 清理只有 `CLEANED | QUARANTINED | BOUNDARY_UNSAFE`；
- quarantine 由不可变记录跨重启永久禁止复用；物理删除失败时不承诺以后再次删除；
- 3.4 的无恢复安全失败关闭只覆盖 Snapshot、执行副本和普通 consumer；3.10 权威持久化恢复是唯一例外，未解决恢复继续阻断工作区，用户取消或声明放弃不能清除恢复工件；
- v1 文本画像固定为 `TextContentProfile = UTF8 | UTF8_BOM`；BOM 计入原始字节摘要、从逻辑文本投影移除，补丁序列化必须恢复原画像；
- `BaselineDecision = ACCEPTED | REJECTED`，证据不完整不伪装成 REJECTED；
- ExistingFailure 和 NaturalLanguageDefect 的完整 collection、目标、非目标节点及 mandatory 检查语义已封闭；
- 3.8 形成 `ReproductionEvaluation`，3.4 只消费 `CONFIRMED` 并发布 v2。

不要把已删除的 MaterializationJob、workspace lifecycle、cleanup attempt、resource gate 或通用 reconciliation 引回 3.4。

### 4.5 3.5：Agent 主循环、文件工具与反馈

3.5 最终只有九个小节：

1. 范围与 v1 不变量；
2. 轮次主体与顺序主循环；
3. `ContextProjection`、预算与披露；
4. 单动作输出、绑定、阶段允许与完成处置；
5. 不可变树上的只读文件工具；
6. 有界的下一轮结构化反馈；
7. reservation 与轮次终态；
8. 内部故障关闭与明确非目标；
9. 唯一的 21 项固定验收清单。

核心行为：

- 同一运行最多一个活动 Agent turn；
- 每个逻辑 turn 恰好关联一个 LLM call attempt，并恰好形成一个 `AgentTurnCompletionKind` 与一个 `TurnContinuationDisposition`；
- `AgentTurnOutcome` 是 owning process 内 checkpoint 后正常或失败完成的 `AcceptedTurnOutputRecord | RejectedTurnOutputRecord | LLMCallFailureRecord | TurnProcessingFailureRecord` 四值联合；
- 3.3.7 正式启动终止或 3.3.14 Demo 启动失效是既有崩溃关闭例外：它们以 `TURN_ABORTED + RUN_STOPPED` 闭合未完成 turn，不创建或伪造 `AgentTurnOutcome`；
- `AgentAction` 是 `ListFilesAction | ReadFileAction | SearchTextAction | ApplyCandidatePatchAction | RunCheckAction | ProposeReproductionAction | ProposeCompletionAction` 七值联合，并遵守现有阶段矩阵；
- 停止只由控制面稳定谓词触发，模型动作不能触发或宣告停止；
- Mock 与真实适配器经过同一解析、绑定、策略、分发、反馈和停止路径；
- `REPRODUCTION` 读取 `SnapshotTree`，`AGENT_LOOP` 读取 `CandidateTree`；
- list/read/search 直接读取不可变内容对象，不创建 `ExecutionWorkspace`；
- 路径、受限 glob、字面量搜索、稳定排序、分页和硬上限由确定性代码执行；
- 正文缺失或摘要错误时不发布、不披露、不调用 LLM；
- `DisclosureGrant` 只绑定运行级供应商、端点、模型、允许来源与数据类别、脱敏规则、累计预算和有效期；每次实际发送由既有 `DisclosureRecord` 绑定最终请求摘要、实际来源、体量、脱敏结果和所消费 grant；
- 披露等待前只能构建非权威 `ContextProjectionDraft`；授权不足只创建 `WaitContext`，不得创建 turn、attempt、feedback、`AgentFeedbackConsumptionManifest` 或 reservations；授权满足并在新 phase-entry 全量重算后，才原子创建 `AgentTurn`、最终 `ContextProjection`、attempt、适用 feedback、`AgentFeedbackConsumptionManifest` 和 reservations；
- feedback 只支持 `NEXT_TURN_ONLY` 有界摘要，不跨候选或 phase 迁移；
- 每条选中反馈恰好一个 reservation，一个 `AgentFeedbackConsumptionManifest` 聚合完整集合；确定性 dispatch checkpoint 在适配器调用前提交并立即全量消费 reservations；
- owning process 内 Accepted、Rejected、`LLMCallFailureRecord` 和 `TurnProcessingFailureRecord` 都保持 checkpoint 后的消费；
- owning process 内 checkpoint 前取消或内部中止全量关闭 reservations 且不消费；3.3.7 正式启动终止或 3.3.14 Demo 启动失效在 checkpoint 前执行相同关闭，在 checkpoint 后无 outcome 时保持已消费；
- `SAME_ATTEMPT_REPLAY` 只能为相同标识和相同规范输入返回首次已形成的同一 outcome，并复用原最终投影、`AgentFeedbackConsumptionManifest` 和 reservations；尚无 outcome 时不得重发适配器调用；
- 两种启动关闭都不得调用、恢复或重发适用适配器；正式路线保留披露／预算事实与真实适配器可能已调用的不确定边界，Demo 路线只保留已持久化预算事实与 Mock adapter 可能已调用的不确定边界；旧 process、适用的正式 lease 或 Demo session、turn 或 attempt 绑定的迟到结果不得重开或改写终态；
- 响应后的不可恢复处理故障形成 `TurnProcessingFailureRecord + TURN_ABORTED + STOPPED(INTERNAL_ERROR)`，保持 reservations 已消费，不产生动作且不重新请求供应商。

明确移出 v1：Stage2 generation、响应正文跨崩溃恢复、persistent processing block、successor reconciliation、handoff DAG、恢复工件、完整迟到兼容矩阵、跨候选 feedback continuation、`UNTIL_SUPERSEDED`、summary/detail 双模式和持久 detail。

## 5. 冻结与审查门禁

### 5.1 七项封闭验收维度

后续审查只能使用以下七项高层维度：

1. 最小 Coding Agent Harness 功能闭环可运行；
2. 权威输入、结果与持久化边界可判定；
3. 模型不参与授权或安全事实判定；
4. feedback reservation 不部分消费或部分关闭；
5. 内部故障安全停止且不伪造成功；
6. 核心机制可用 Mock LLM 离线确定性测试；
7. 方案在单人课程周期内可实现、演示和验证。

3.5 的细化门禁只来自 3.5.9 现有的 21 项清单；其本轮修正待只读审查通过后才可重新锁定。

### 5.2 阻断意见的准入格式

任何阻断意见必须同时提供：

```text
classification: CONTRACT_CONTRADICTION | PROVABLY_UNIMPLEMENTABLE | CONCRETE_SECURITY_PATH
acceptance_dimension: 七项维度或固定清单编号
affected_contract: 当前冻结合同
counterexample: 可复现的具体反例
minimal_fix: 不扩大范围的最小修复
```

缺少任一项时，该意见不得阻断。无法映射的意见统一标为过程标签：

```text
NON_BLOCKING_ENHANCEMENT
```

该标签不是运行时枚举，不产生实现或冻结义务。

### 5.3 允许重开冻结内容的条件

只有以下三类问题可以重开：

- 当前合同直接自相矛盾；
- 可以证明无法实现；
- 存在具体攻击路径的严重安全漏洞。

“可以更可靠”“生产环境通常这样做”“新对象也需要恢复协议”都不足以重开冻结内容。新增验收维度必须由用户显式批准。

## 6. 下一任务建议：3.6

### 6.1 3.6 的权威职责

3.1 的权威索引已经指定：

```text
3.6：CandidateRevision、恢复修订和 FinalDiff
```

新对话应先从课程要求、第 1/2 章承诺、3.4 的 `SnapshotTree/ValidationManifest` 和 3.5 的 `ApplyCandidatePatchAction` 边界提取 3.6 所需行为，不应直接从实现技术倒推类型。

### 6.2 推荐的 3.6 v1 范围

先固定以下功能问题，再写对象字段：

1. 候选修订从哪个不可变来源树派生；
2. 补丁输入如何绑定当前 turn、candidate、Manifest 和 phase-entry；
3. 补丁成功、确定性拒绝和内部失败分别形成什么权威结果；
4. 如何保证旧候选不被原地修改；
5. 新候选如何成为当前候选，失败时旧候选如何保持有效；
6. 恢复修订在 v1 中具体解决哪个用户可见问题；
7. `FinalDiff` 何时形成、绑定哪些树和验证事实；
8. 哪些错误必须失败关闭，哪些可以生成下一轮反馈；
9. 哪些行为必须在 Mock LLM 和故障注入下确定性验证。

建议 3.6 只深入候选树不可变派生、补丁边界与 `FinalDiff` 的权威来源。不要预先加入多 worker generation、跨进程补丁接管、通用 WAL/outbox、持久 resource block 或自动 reconciliation。

### 6.3 3.6 开始前的固定流程

1. 只读检查课程源文档和 3.1/3.4/3.5 的权威引用；
2. 写出 3.6 的范围、非目标和 5—10 个封闭验收问题；
3. 由用户显式批准验收维度；
4. 再写 3.6 正文；
5. 实施代理完成后依次做规范审查、文档质量审查；
6. 所有阻断项关闭后做无背景范围冷审；
7. 真实记录 `SPEC_PROCESS.md` 和 `AGENT_LOG.md`，不得提前声称审查通过。

### 6.4 3.6 完成标准

- 只定义 v1 功能合同，不定义生产级调度引擎；
- 与 3.4/3.5 无悬空引用或双重所有权；
- 候选修订不可变，旧候选不会被补丁原地改写；
- PatchEngine 的成功/拒绝/内部错误可机械区分；
- `FinalDiff` 的来源、形成条件和失败关闭可判定；
- 固定验收清单可由 deterministic code、mock LLM 和故障注入验证；
- 没有开放式“至少满足”或审查者可持续追加的验收措辞。

## 7. 3.6 之后的路线

按 3.1 权威索引，剩余 SPEC 顺序为：

| 章节 | 权威职责 |
|---|---|
| 3.6 | `CandidateRevision`、恢复修订、`FinalDiff` |
| 3.7 | 检查能力、`CheckResult`、失败指纹 |
| 3.8 | 两类修复场景、复现确认状态 |
| 3.9 | 策略决定、审批、披露授权、披露记录 |
| 3.10 | 正式验证、持久化事务、持久化恢复 |
| 3.11 | 记忆、配置、凭据 |
| 3.12 | 可见性事件、审计记录、演示状态 |

SPEC 全部完成和批准后，才能创建权威 `PLAN.md`。计划还必须通过不同代理类型的无背景冷启动试验，之后才能进入实现。不要从本地未跟踪的旧 `PLAN.md` 直接恢复工作。

## 8. 新对话启动提示词

可把下面内容作为新对话的第一条任务说明：

```text
不要先读取 D:\code\VesperCode 根 worktree 中的 SPEC、PLAN 或其他项目文件；
该路径当前属于另一分支并含用户未跟踪内容。

先运行 git -C D:\code\VesperCode fetch origin，确认成功后，从最新 origin/main
创建独立分支和 worktree D:\code\VesperCode\.worktrees\spec-v1-chapter36。
不得改写、暂存、清理或切换根 worktree 的内容；允许通过 git worktree add
在指定 .worktrees 目录创建隔离 worktree。

随后只从新建 worktree 根目录完整阅读 TASK_HANDOFF.md、
AGENTS.md（若该分支存在）、AI4SE_Final_Project_通用要求.md、
AI4SE_Final_Project_A_Coding_Agent_Harness(1).md、SPEC.md 的 3.0—3.5，
以及 SPEC_PROCESS.md 的 10.7、第 11 节和第 12 节。

当前任务只制定并审查 SPEC 3.6 的 v1 范围和封闭验收问题；
在用户批准验收维度前，不写生产级状态机，不引入 generation、takeover、
通用 reconciliation、persistent block 或多层 cleanup 协议，也不实现代码。

每条阻断建议必须映射到既有封闭维度、冻结合同、具体反例和最小修复；
无法映射者标记为 NON_BLOCKING_ENHANCEMENT。
```

## 9. 新对话的基础验证命令

进入新建 worktree 后，PowerShell 环境建议逐条运行，避免把多个长命令塞进同一进程。以下文本扫描优先使用 `rg`（ripgrep）；如果环境没有安装 `rg`，使用 PowerShell `Select-String -Path <文件> -Pattern <模式>` 执行等价只读扫描，不要因此跳过验证：

```powershell
git status --short --branch
git log --oneline -8
git diff --check origin/main...HEAD
rg -n "^### 3\." SPEC.md
rg -n "^### 3\.5\." SPEC.md
rg -n "NON_BLOCKING_ENHANCEMENT|新增验收维度|具体反例" SPEC_PROCESS.md
rg -n "TBD|TODO|待定|占位" SPEC.md SPEC_PROCESS.md AGENT_LOG.md
```

占位词命中必须分类：旧过程记录中的“扫描结果为 0”或规范中“禁止占位值”的文字不是未完成项，不应为追求全文件零命中而改写历史。

在 Windows 沙箱中，如果短命令出现 `CreateProcessAsUserW failed: 5`，先改为单条命令和绝对路径；这属于执行环境问题，不是规范失败。若 Git ownership 阻断单次只读诊断，可在明确授权后仅对该命令使用 `git -c safe.directory=<绝对路径> ...`，不要修改全局 Git 配置。若 ownership 阻断 `fetch`、`worktree add`、提交或推送等写操作，应切换到仓库实际所有者环境，或停止并请求授权；不得绕过检查，也不得使用未核实的旧远端引用继续。

## 10. 本轮暴露的结构性问题

### 10.1 对象增殖会产生“复杂度税”

本轮最明显的问题不是某个字段写错，而是每增加一个持久对象都会自动派生一整套问题：

```text
唯一键
→ 幂等
→ 并发
→ 崩溃恢复
→ 迟到结果
→ 清理
→ 清理状态未知
→ 对账
→ 阻断与接管
```

当 `Stage2ProcessingClaim`、generation、revocation gate、response artifact、persistent block、successor case 等对象叠加时，反馈协议被扩张成了通用可靠工作流引擎。

可复用规则：**新增持久对象前先计算对象税。** 如果它不能直接兑现现有用户故事、安全边界或固定验收项，就不进入 v1。

### 10.2 功能规约和实现规约混层

功能规约需要回答：输入是什么、权威输出是什么、失败如何关闭、哪些行为可验证。它不需要在每节展开数据库 CAS 字段、WAL/outbox、lease takeover、物理对象存储生命周期和所有 crash interleaving。

可复用规则：

- `SPEC.md` 写可观察合同和安全不变量；
- 架构章写组件、存储与并发策略；
- `PLAN.md` 写实现步骤和测试；
- 故障一致性附录才写生产级恢复算法。

如果一段内容只有数据库/调度器实现者才能理解，而用户故事和测试无法直接引用，它通常不应留在功能规约正文。

### 10.3 验收门槛后移

此前出现过以下循环：

```text
附条件批准
→ 引入新对象
→ 从新对象发现新边界
→ 把边界升级为新冻结条件
→ 再次附条件批准
```

该流程没有自然终点。

可复用规则：在开始审查前先冻结验收维度；“附条件批准”只能修复这些维度中的现存问题，不能自动创造新维度。条件全部关闭后必须 PASS。

### 10.4 横切问题被重复设计

幂等、状态未知、权威事实与临时资源分离，曾在快照、物化、清理、文件工具、LLM 调用和反馈 reservation 中重复展开。

可复用规则：同一横切问题第三次出现时，停止在局部新增类型，把共同合同上移到 3.1；各模块只引用共同合同并说明自己的失败关闭路线。

### 10.5 “恢复一切”并不等于安全

课程 v1 不要求任意崩溃点都自动恢复。过度追求 exactly-once 和跨进程恢复反而增加无法实现和无法验证的状态空间。

可复用规则：优先选择简单、可证明的安全失败关闭：

```text
权威状态不确定
→ 不伪造成功
→ 不重复外部副作用
→ 保留已发生事实
→ STOPPED(INTERNAL_ERROR)
```

只有明确的课程需求或用户故事要求恢复时，才增加恢复协议。

### 10.6 删除复杂机制后容易留下悬空引用

范围收敛时，旧类型可能继续出现在后续小节、验收清单或过程文档中。例如未定义的 `ResponseReceived` 和过时章节号 `3.5.38` 都是在最终静态检查中发现的。

可复用规则：删除前生成引用清单；每个命中只能归入：

```text
删除
替换为简化对象
仅保留为历史或未来增强说明
```

然后分别扫描规范正文和过程历史，不能用全文件关键词归零误删历史证据。

### 10.7 审查建议本身也可能过宽

本轮曾把“删除类型不得悬空”修成“所有章节引用必须已有当前定义”，结果把合法的 3.6—3.11 前向引用全部判为失败。

可复用规则：接受审查建议前，再问一次：

1. 它是否精确对应原验收项；
2. 它是否扩大了量词或作用域；
3. 它是否让当前规范在设计上必然失败；
4. 是否存在更小的等价修复。

审查意见不是新的权威需求，仍需技术判断。

### 10.8 规范历史和当前合同必须分离

`SPEC_PROCESS.md` 可以保留已经废弃的类型和讨论，用于证明迭代过程；这些历史术语不能被解释为当前实现义务。

可复用规则：规范正文回答“现在必须实现什么”，过程文档回答“为什么做出这个决定”。扫描和审查必须分别进行。

### 10.9 证据记录存在自引用问题

一个提交无法在自身内容中准确写入自己的最终 SHA；一次冷审也无法覆盖记录该冷审结果的后续日志提交。

可复用规则：使用时间点证据和追加式补证：

1. 先提交被审查内容；
2. 审查该确定 SHA；
3. 追加审查结果日志；
4. 对日志只做窄范围真实性复核；
5. 不声称原审查覆盖后续日志提交。

不要通过反复 amend 试图让提交自引用。

### 10.10 环境故障不能冒充设计故障

Windows 沙箱的进程启动拒绝、权限审批延迟、Git ownership 提示和行尾 stat 标记曾拖慢审查，但它们不构成规范反例。

可复用规则：把失败分成三类：

- 文档/代码失败；
- 验证工具失败；
- 执行环境失败。

只有第一类可以直接判定任务失败；后两类应换用最小只读命令、绝对路径和替代验证方式，并如实记录未验证范围。

## 11. 可复用的规格收敛流程

### 11.1 章节开始模板

每个新章节先写以下七项，不先写 Record 字段：

```text
目标与章节所有权
权威输入
权威输出
共同不变量
失败关闭路线
明确非目标
固定验收清单
```

### 11.2 新对象准入测试

提出新持久对象时逐题回答：

1. 它是否表达新的、用户可观察的权威事实；
2. 现有对象或结果联合为什么不能表达；
3. 它是否真的需要跨重启持久化；
4. 谁拥有它，谁负责释放或关闭；
5. 它是否会连带要求 generation、takeover、reconciliation 或 block；
6. 不加入它时，v1 能否通过安全失败关闭满足当前验收；
7. 它能否在 mock/stub LLM 和故障注入下确定性测试。

第 1、2、3 项不能明确回答时，默认不进入 v1。

### 11.3 原子性表达规则

功能规约只固定业务原子性：

```text
哪些权威结果必须全有或全无
哪个终态最多一个获胜
失败时哪些事实必须保持不变
```

除非存储机制本身是课程重点，不在功能规约列完整 CAS 字段、revision、摘要 DAG 和多对象提交拓扑。

### 11.4 审查工作流

对每项独立任务采用：

```text
新实施代理
→ 规范符合性审查
→ 原实施代理最小返修
→ 规范复审
→ 文档质量审查
→ 原实施代理最小返修
→ 质量复审
→ 无背景冷审
```

同一文件不要由多个实施代理并行编辑。审查代理只读；返修必须回到原实施代理，避免上下文和所有权漂移。

### 11.5 停止规则

满足以下条件后章节必须冻结：

- 固定验收项全部有正文证据；
- 没有合同矛盾、可证明不可实现或具体严重安全漏洞；
- 所有阻断意见已按最小修复关闭；
- 剩余建议均无法映射到冻结维度，已归类为 `NON_BLOCKING_ENHANCEMENT`；
- 无背景读者可以说明输入、输出、失败路线、下一任务和非目标。

冻结后，不得因为“还能更完善”继续追加状态机。

## 12. 最终交接检查表

新对话在开始设计前应能准确回答：

- 当前权威分支和远端是什么；
- 哪个本地 worktree 不能触碰；
- `SPEC.md` 已经完成到哪一节；
- 为什么本轮只能在只读审查实际通过后重新锁定 3.1—3.5，且不能声称完整第三章已锁定；
- 下一任务为什么是 3.6；
- 3.5 的九个小节、七值动作、四值 outcome、dispatch checkpoint 消费和只返回既有结果的 replay 决策是什么；
- 哪些生产级机制已经明确移出 v1；
- 阻断审查意见必须提供哪五项信息（分类及四类证据）；
- `NON_BLOCKING_ENHANCEMENT` 的含义；
- SPEC 完成前为什么不能进入实现或直接采用本地旧 `PLAN.md`；
- 如何验证新章节没有重新引入范围膨胀。

如果上述任一问题仍需要依赖旧聊天记录才能回答，先修订本文，不要继续下一章节。
