# Chapter 3 Follow-up Contract Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development whenever subagent capability is available; use superpowers:executing-plans only as the fallback when it is unavailable. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 关闭第三章 3.1—3.5 交叉审阅确认的全部合同缺口与计划错误，使生命周期、披露调度、轮次失败、用户故事和最低验收合同重新闭合。

**Architecture:** 只修订既有 `RunState`、`DisclosureRecord`、`AgentTurnOutcome`、完成处置和错误映射，不增加新的运行状态、等待类型、停止原因、持久 `DisclosureAttempt` 或跨进程恢复机制。把外部调用前可观察 checkpoint 与数据库实现方式分离，并以“串行单写入者”方式重新锁定 3.1—3.5：Task 2—5 依次由各自的 fresh implementation agent 编辑 `SPEC.md`，任一时刻只有一个写者，前一 Task 提交并通过规范符合性与文档质量两阶段只读审查后才交接下一 Task，所有 reviewer 均只读。该约束限定并发与角色权限，不要求跨 Task 复用同一 agent identity。

**Tech Stack:** Markdown specification documents, Git worktrees, PowerShell contract checks

**Execution Mode:** 本计划使用 `superpowers:subagent-driven-development` 作为唯一任务调度器：控制代理读取并跟踪本计划，按顺序为每个 Task 派发一个 fresh implementation agent，再依次做规范符合性和文档质量两阶段只读审查。Task 2—5 的 implementation agent 依次编辑 `SPEC.md`；任一时刻只能有一个写者，前一 Task 必须先提交并通过两阶段审查，控制代理才可交接下一 Task，所有 reviewer 均保持只读。“串行单写入者”是并发与角色约束，不要求跨 Task 复用同一 agent identity。该模式同时满足逐步执行、勾选状态和检查点要求；不得再把 `superpowers:executing-plans` 作为第二个并列调度器重复执行同一 Task。只有运行环境没有 subagent 能力时，才改用 `superpowers:executing-plans` 作为后备流程。

---

## 基线、范围与文件职责

- 计划基线：`main = origin/main = 53ddefd1676c2c72603dddaac33393ffb3627ef7`。
- 计划 worktree：`D:\code\VesperCode\.worktrees\ch3-followup-review-plan`。
- 计划分支：`codex/ch3-followup-review-plan`。
- 实施前必须使用 `superpowers:using-git-worktrees` 核验该 worktree；无需再创建第二个实施 worktree。
- `SPEC.md` 采用串行单写入者合同：Task 2—5 各由一个 fresh implementation agent 依次编辑，任一时刻只允许当前 Task 的一个写者；前一 Task 提交并通过两阶段只读审查后才交接，所有规范符合性、文档质量和无背景范围冷审 reviewer 均只读。该合同不要求跨 Task 复用同一 agent identity。
- 不修改根 worktree，不接触其中未跟踪的 `.gitignore`、`AGENTS.md`、`PLAN.md` 或 `REFLECTION.md`。
- 不创建课程权威 `PLAN.md`，不添加实现代码、测试代码或依赖。

**Files:**

- Create: `docs/superpowers/plans/2026-07-16-chapter-3-followup-contract-fixes.md` — 本实施计划，不是课程权威 `PLAN.md`。
- Modify: `SPEC.md` — 唯一规范合同，修正第 1、2 章及 3.1—3.5。
- Modify: `SPEC_PROCESS.md` — 只追加本轮六项审阅证据和采纳理由，不改写历史。
- Modify: `TASK_HANDOFF.md` — 同步当前合同、验收门禁和下一任务。
- Modify: `AGENT_LOG.md` — 三轮审查完成后追加真实技能、提交、人工决定和审查结果。

## 六项逐条判断

### 1. 正式运行重启没有进入 3.2 唯一转换矩阵

```text
classification: CONTRACT_CONTRADICTION
acceptance_dimension: 3.2 生命周期唯一来源、3.2.6 稳定错误映射、3.3.16 第 5 项
affected_contract: 3.2.7 声明其矩阵是生命周期转换唯一规范来源，但“正常转换矩阵”的标题与导语已经无法覆盖现有 Demo 失效路线，且矩阵仍缺少 3.3.7 的正式运行启动终止
counterexample: 新进程发现旧正式运行处于 RUNNING(AGENT_LOOP)。按 3.3.7 必须写入 PROCESS_RESTARTED_DURING_RUN 并停止为 INTERNAL_ERROR，但 3.2.7 的唯一矩阵中没有合法转换，3.2.6 也无法从该错误码得到 StopReason
minimal_fix: 在 3.2.6 增加 PROCESS_RESTARTED_DURING_RUN -> INTERNAL_ERROR；把 3.2.7 改名为权威生命周期转换矩阵，并以封闭源状态集合增加正式运行启动终止行，引用 3.3.7 的完整守卫而不复制第二套闭合算法
```

**判断：采纳。** 这是直接矛盾。新增的是矩阵事件 `PROCESS_RESTART_DETECTED` 和既有错误码映射，不新增 `RunStatus` 或 `StopReason`。

### 2. `DisclosureRecord`、披露预算和真实调用之间缺少持久提交点

```text
classification: PROVABLY_UNIMPLEMENTABLE
acceptance_dimension: 第 1 章披露承诺、US-05、3.1.3 外部副作用顺序、3.2.3、3.5.3 与 3.5.7
affected_contract: 当前要求每次实际发送都有 DisclosureRecord，同时禁止持久 DisclosureAttempt；checkpoint 在适配器调用前，但尚未要求它原子创建 DisclosureRecord 和消费披露预算
counterexample: 进程把请求交给真实适配器后立即崩溃，供应商可能已经收到请求，但进程尚未来得及创建 DisclosureRecord 或扣减累计字节预算；重启后无法证明是否真实发送，也不能安全补写或回退
minimal_fix: 把既有 DisclosureRecord 定义为真实适配器调用前 pre-dispatch commit 的持久事实；同一 dispatch checkpoint 原子重验 grant、消费规范外发载荷字节预算、创建记录并消费 feedback reservations，然后才允许尝试调用真实适配器
```

**判断：采纳并收敛。** `DisclosureRecord` 只证明请求已获授权并完成真实适配器调用前的 pre-dispatch commit；从该提交完成起，系统才被允许尝试调用适配器。它不证明适配器实际被调用，也不证明供应商收到、处理或返回。checkpoint 后崩溃时，适配器调用与交付事实都为 `UNKNOWN`，但记录、披露预算和 feedback 消费不得恢复。Mock 路线仍不创建 `DisclosureRecord`、不消费真实披露预算。

### 3. `LLMCallFailureRecord` 没有确定的后续生命周期路线

```text
classification: CONTRACT_CONTRADICTION
acceptance_dimension: 3.1.2 稳定错误与失败关闭、3.5.1 四值 outcome、3.5.4 完成处置、3.5.8 调用失败
affected_contract: LLM_CALL_FAILED 和 RUN_STOPPED 都已存在，但没有冻结两者的映射、稳定 error_code 或 StopReason
counterexample: dispatch checkpoint 后适配器返回终态调用失败。实现者可以选择创建下一 turn，也可以停止；两者都能引用现有枚举，却产生相反的供应商重发与预算行为，违反 3.1.2 要求的唯一稳定失败路线
minimal_fix: 固定 LLMCallFailureRecord -> LLM_CALL_FAILED + RUN_STOPPED，error_code = LLM_ADAPTER_CALL_FAILED，StopReason = EXECUTION_TERMINATED；不得自动创建下一 turn
```

**判断：采纳。** v1 不把适配器调用失败变成同一运行内的供应商请求重发。另增加 3.5 最小错误路由表，封闭当前已经出现的预算、输出、阶段、工具输入、完整性和响应处理失败。

### 4. US-08 的三种用户状态与 `RECOVERY_REQUIRED` 冲突

```text
classification: CONTRACT_CONTRADICTION
acceptance_dimension: US-08 结果级验收、2.7 INVEST、3.2.1 RunStatus、3.2.9 持久化恢复
affected_contract: US-08 只允许用户区分执行、等待和停止，并把需要恢复列为停止类别；3.2 把 RECOVERY_REQUIRED 定义为既非 WAITING_USER 也非 STOPPED 的独立非终态
counterexample: 运行处于 RECOVERY_REQUIRED 且 RecoveryDisposition = UNRESOLVED。按 US-08 UI 必须归入三类之一，但归入等待或停止都会错误表示其生命周期和取消能力
minimal_fix: 用户可见类别改为执行中、等待用户、恢复阻塞、已结束四类；从停止原因中移除需要恢复，并同步 INVEST 行
```

**判断：采纳。** 这是展示合同和生命周期合同的直接矛盾。四类只是对现有六值 `RunStatus` 的展示分组，不增加状态。

### 5. 3.5.1 对事务拓扑的排除容易被解释为排除原子验收

```text
classification: NON_BLOCKING_ENHANCEMENT
acceptance_dimension: 3.5.1 范围、3.5.7 可观察原子性
affected_contract: 3.5.1 排除数据库字段、多对象事务拓扑、发布键和摘要 DAG；3.5.7 已明确全有或全无、无部分对象可见及调用前 checkpoint
counterexample: 审阅者可能把“不构成 v1 功能验收条件”扩大解释为全有或全无也不可验收，但现有文字仍可按“实现方式不冻结、可观察结果冻结”作一致解释
minimal_fix: 明说表结构、存储技术、内部引用拓扑和摘要 DAG 不属于验收；本章明确规定的全有或全无、单一胜出、无部分可见和调用前 checkpoint 仍是规范性可观察合同
```

**判断：不是阻断矛盾，但建议修改。** 现有 3.5.1 与 3.5.7 在严格解释下可以同时成立；本轮邻接修改时增加一句澄清，不引入任何新运行时义务。

### 6. 3.5.9 不应宣称是完整且唯一的验收合同

```text
classification: CONTRACT_CONTRADICTION
acceptance_dimension: 3.5.1—3.5.8 的规范性 MUST/MUST NOT 与 3.5.9 的验收范围声明
affected_contract: 3.5.9 声称 1—21 是完整且唯一的 v1 验收合同，但前文仍有未在清单重复的规范要求
counterexample: 实现持久化完整原始模型响应，违反 3.5.1；由于该禁令没有完整出现在 21 项中，按“完整且唯一”解释却可以不纳入验收
minimal_fix: 标题改为固定最低验收清单；声明 1—21 是最低必测集合，3.5.1—3.5.8 其他规范合同继续有效，清单不得被解释为排除未逐项重复的要求
```

**判断：采纳。** 保持固定编号 1—21，不尝试把前文所有 `必须／不得` 复制进清单。`TASK_HANDOFF.md` 中所有“唯一清单”和“细化门禁只来自清单”的当前状态描述必须同步修正；历史过程记录不回写。

## 补充审阅结论：3.5 局部锁定与 3.6 前置依赖

| 补充建议 | 判断 | 计划处理 |
| --- | --- | --- |
| 固定 `LLMCallFailureRecord` 的唯一后续路线 | 正确 | 已由 Task 4 冻结为 `LLM_ADAPTER_CALL_FAILED + LLM_CALL_FAILED + RUN_STOPPED + STOPPED(EXECUTION_TERMINATED)` |
| 区分数据库事务技术与可观察原子性 | 正确，但属于 `NON_BLOCKING_ENHANCEMENT` | 已由 Task 4 澄清；不增加新运行时对象 |
| 把 3.5.9 改为固定最低验收清单 | 正确 | 已由 Task 5 处理，编号继续严格保持 1—21 |
| 真实调用前已形成 `DisclosureRecord` 和披露预算事实 | 意图正确，但“在 dispatch checkpoint 前形成”不精确 | 已由 Task 3 改为“作为 dispatch checkpoint 的原子组成提交”；checkpoint 成功后、调用真实适配器前，记录与预算已经持久化 |

四项全部完成并通过本计划的顺序审查后，3.5 可以作为局部合同单独锁定。该结论只表示 3.5 的写作结构和自身规范已经闭合，不表示 `3.5 -> 3.6` 的首轮修复端到端链路已经可执行，也不表示完整第三章已锁定。不得新增 3.5.10，也不得借收口继续扩写 3.5 新机制。

初始候选建议成立，门禁记录为：

```text
classification: PROVABLY_UNIMPLEMENTABLE
acceptance_dimension: 3.5.2 RepairTurnSubject 与未来 3.6 CandidateRevision 的端到端绑定
affected_contract: 3.5.2 要求 RUNNING(AGENT_LOOP) 的 RepairTurnSubject 绑定当前 CandidateRevision、CandidateTree 和 repair base；现有进入 AGENT_LOOP 的转换只发布 Manifest／repair base／phase-entry，没有发布初始候选
counterexample: ExistingFailure 基线进入 AGENT_LOOP 后立即创建第一个 RepairTurnSubject。控制面既不能绑定不存在的 CandidateRevision，也不得使用空 candidate 或占位修订，因此第一轮无法合法开始
minimal_fix: 3.6 必须规定每次进入 AGENT_LOOP 时，在首个 RepairTurnSubject 可见前唯一发布初始 CandidateRevision 及 CandidateTree，并使其精确绑定当前 Manifest、phase-entry 和 repair base
```

这是 **3.6 的强制前置合同**，不是本计划要在 3.5 中实现的第七项修复。未来 3.6 至少必须冻结：

- ExistingFailure 的初始候选内容等于其 `SnapshotTree` repair base；
- NaturalLanguageDefect 的初始候选内容等于已确认的 `reproduction_candidate_tree` repair base；
- 进入 `AGENT_LOOP` 的权威结果在初始 `CandidateRevision`、`CandidateTree`、Manifest、repair base 与 phase-entry 未全有或全无绑定时不得可见；
- 初始候选是正式修订，不得用空值、`NO_CANDIDATE` 或占位修订代替；
- 同一进入结果最多发布一个初始候选；发布失败不得留下可启动首个 `RepairTurnSubject` 的阶段状态。

## 执行前方案审阅六项结论

| # | 判断 | 计划修正 |
| --- | --- | --- |
| 1 | 正确，是计划编号错误 | Task 2 的 `3.2.10` 全部改为 `3.2.11`；守卫失败时既不得终止旧运行，也不得创建新运行 |
| 2 | 正确，是矩阵名称与成员不一致 | 3.2.7 改为“权威生命周期转换矩阵”；正式重启源状态使用七项封闭集合，明确排除 `RUNNING(PERSISTENCE)` 与 `RECOVERY_REQUIRED` |
| 3 | 正确，是证明语义过强 | `DisclosureRecord` 只证明授权与 pre-dispatch commit 完成，不证明适配器实际调用或供应商送达 |
| 4 | 正确，是 `ErrorEnvelope` 必填字段遗漏 | 3.5 最小错误路由增加副作用判定对象和 `side_effect_status`，逐行冻结 `NONE | COMMITTED | UNKNOWN` |
| 5 | 正确，是跨章节权威冲突 | 3.10 只形成 `FormalValidationResult`；3.5 在下一 turn 创建时从该结果确定性生成反馈 |
| 6 | 正确，是用户故事承诺过宽 | US-06 收窄到 `ConfirmReproductionAction` 一次性批准和通用 `DENY` 拦截；最终持久化批准继续只由 US-07 覆盖 |

六项全部进入既有 Task，不增加新 Task、新审查轮次或 3.5.10。`TASK_HANDOFF.md` 还必须为未来章节冻结两条约束：3.9 是 grant、披露预算账本、`DisclosureRecord` 发布键／幂等与 pre-dispatch commit 的权威来源；3.12 只能展示“已完成调用前调度提交／适配器调用与交付未知”等准确状态，不得把记录无条件显示为“已发送”或“供应商已收到”。

## 修订后冻结的公共合同

### 生命周期与用户可见状态

```text
PROCESS_RESTART_DETECTED
  -> error_code = PROCESS_RESTARTED_DURING_RUN
  -> 3.3.7 同一 CAS／权威提交闭合旧正式运行及在途对象
  -> STOPPED(INTERNAL_ERROR)
```

用户可见分组固定为：

- 执行中：`CREATED | RUNNING`；
- 等待用户：`WAITING_USER`；
- 恢复阻塞：`RECOVERY_REQUIRED`；
- 已结束：`SUCCEEDED | STOPPED`。

`RECOVERY_REQUIRED` 不得显示为停止原因，用户取消或声明放弃也不得直接结束该状态。

### 真实披露 dispatch checkpoint

真实适配器调用前的单一持久 checkpoint 必须按同一权威提交完成：

1. 重新验证当前 turn、attempt、最终 `ContextProjection`、规范供应商请求和 `DisclosureGrant` 绑定；
2. 以确定性序列化后的最终规范外发载荷字节数校验并消费累计披露预算；
3. 创建既有 `DisclosureRecord`，绑定最终请求摘要、实际来源、数据类别、外发载荷体量、脱敏结果和所消费 grant；
4. 原子全量消费 `AgentFeedbackConsumptionManifest` 的 ACTIVE reservations；
5. 提交成功后才允许调用真实适配器。

`DisclosureRecord` 是“请求已获授权并完成真实适配器调用前 pre-dispatch commit”的持久事实，不是适配器调用、供应商送达或处理收据。checkpoint 失败时不得调用适配器，披露预算、记录和 feedback 消费必须全有或全无；checkpoint 成功后系统才允许尝试调用适配器。若进程随后失效，适配器调用与交付事实均为 `UNKNOWN`，但已提交的记录、披露预算和 feedback 消费不得回退。

### 3.5 最小错误路由

| 场景 | 稳定 `error_code` | 副作用判定对象 | `side_effect_status` | 轮次 outcome／完成处置 | `retry_disposition` | 运行路线 |
| --- | --- | --- | --- | --- | --- | --- |
| mandatory context 经规范压缩后仍超预算 | `CONTEXT_BUDGET_EXCEEDED` | 拟议 LLM 适配器调用 | `NONE` | 不创建 `AgentTurn`，不伪造完成类别 | `NEW_RUN_REQUIRED` | `STOPPED(BUDGET_EXHAUSTED)` |
| 模型输出 Schema 无效，未达到冻结阈值 | `MODEL_OUTPUT_INVALID` | 本次 LLM 适配器调用 | `COMMITTED` | `RejectedTurnOutputRecord + OUTPUT_INVALID + CREATE_NEXT_TURN` | `NEW_ATTEMPT_ALLOWED` | 当前运行保持非终态 |
| 模型输出 Schema 无效达到冻结阈值 | `MODEL_OUTPUT_INVALID_LIMIT_REACHED` | 本次 LLM 适配器调用 | `COMMITTED` | `RejectedTurnOutputRecord + OUTPUT_INVALID + RUN_STOPPED` | `NEW_RUN_REQUIRED` | `STOPPED(NO_PROGRESS)` |
| 阶段不允许已解析动作 | `ACTION_NOT_ALLOWED_IN_PHASE` | `AgentAction` 执行 | `NONE` | `AcceptedTurnOutputRecord + ACTION_REJECTED + CREATE_NEXT_TURN` | `NEW_ATTEMPT_ALLOWED` | 当前运行保持非终态 |
| 文件工具路径、范围、glob、查询或分页输入非法 | `TOOL_INPUT_INVALID` | `AgentAction` 执行 | `NONE` | `AcceptedTurnOutputRecord + ACTION_REJECTED + CREATE_NEXT_TURN` | `NEW_ATTEMPT_ALLOWED` | 当前运行保持非终态 |
| 活动 turn 的文件工具发现内容对象、树引用或摘要完整性失效 | `TOOL_RESULT_INTEGRITY_INVALID` | `AgentAction` 执行 | `NONE` | 保留已存在的 outcome；`TURN_ABORTED + RUN_STOPPED` | `NO_RETRY` | `STOPPED(INTERNAL_ERROR)` |
| 创建新 turn 前重读内容发现同一完整性失效 | `TOOL_RESULT_INTEGRITY_INVALID` | 拟议下一次 LLM 适配器调用 | `NONE` | 尚无 turn，不伪造 `TURN_ABORTED` | `NO_RETRY` | `STOPPED(INTERNAL_ERROR)` |
| dispatch checkpoint 后真实或 Mock LLM 适配器终态失败 | `LLM_ADAPTER_CALL_FAILED` | 本次 LLM 适配器调用 | `UNKNOWN` | `LLMCallFailureRecord + LLM_CALL_FAILED + RUN_STOPPED` | `NEW_RUN_REQUIRED` | `STOPPED(EXECUTION_TERMINATED)` |
| 已收到响应后的不可恢复控制面处理故障 | `TURN_PROCESSING_FAILED` | 本次 LLM 适配器调用 | `COMMITTED` | `TurnProcessingFailureRecord + TURN_ABORTED + RUN_STOPPED` | `NO_RETRY` | `STOPPED(INTERNAL_ERROR)` |

`side_effect_status` 必须相对于表中“副作用判定对象”解释。LLM 调用类错误描述供应商适配器调用是否发生；pre-dispatch commit 中已经提交的 `DisclosureRecord`、披露预算和 feedback 消费由各自权威事实表达，不得因为 `LLM_ADAPTER_CALL_FAILED` 的调用状态为 `UNKNOWN` 而回退。动作类错误只描述 `AgentAction` 执行，不把此前已完成的 LLM 调用混入该字段。`COMMITTED` 只证明被引用操作已发生，不表示输出有效或运行成功。

`MODEL_OUTPUT_INVALID`、`ACTION_NOT_ALLOWED_IN_PHASE` 和 `TOOL_INPUT_INVALID` 在未触发终态时不得伪造 `StopReason`。所有产生终态的表项必须同步进入 3.2.6 的稳定错误码—`StopReason` 映射。`CREATE_NEXT_TURN` 只允许控制面重新检查取消、预算、披露和绑定，不自动调用适配器。

## 实施任务

### Task 1: 固定实施现场与计划证据

**Files:**

- Create: `docs/superpowers/plans/2026-07-16-chapter-3-followup-contract-fixes.md`
- Inspect only: root worktree and `origin/main`

- [ ] **Step 1: 使用 worktree 技能核对隔离边界**

读取并执行 `superpowers:using-git-worktrees` 的核验步骤。确认当前路径和分支：

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status --short --branch
```

Expected:

```text
D:/code/VesperCode/.worktrees/ch3-followup-review-plan
codex/ch3-followup-review-plan
```

状态中只允许出现本计划文件；不得出现 `SPEC.md`、`PLAN.md` 或根 worktree 的未跟踪文件。

- [ ] **Step 2: 获取远端并核对计划基线**

```powershell
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
```

Expected at plan creation:

```text
53ddefd1676c2c72603dddaac33393ffb3627ef7
53ddefd1676c2c72603dddaac33393ffb3627ef7
```

如果 `origin/main` 已移动，先运行以下只读命令审查新增提交；只有确认其没有覆盖本计划合同后，才把实施基线更新到新的 `origin/main`：

```powershell
git log --oneline --decorate 53ddefd1676c2c72603dddaac33393ffb3627ef7..origin/main
git diff --stat 53ddefd1676c2c72603dddaac33393ffb3627ef7..origin/main
```

- [ ] **Step 3: 提交批准版实施计划**

```powershell
git add docs/superpowers/plans/2026-07-16-chapter-3-followup-contract-fixes.md
git commit -m "Add chapter three follow-up repair plan"
```

Expected: 一个只包含本计划文件的提交。

### Task 2: 补齐权威生命周期矩阵与用户故事边界

**Files:**

- Modify: `SPEC.md` — US-06、US-08、2.7 INVEST、3.2.6—3.2.7、3.2.11、3.3.7、3.3.16

- [ ] **Step 1: 运行变更前反例检查**

```powershell
$spec = Get-Content SPEC.md -Raw
$mapping = [regex]::Match($spec, '(?s)### 3\.2\.6.*?(?=### 3\.2\.7)').Value
$matrix = [regex]::Match($spec, '(?s)### 3\.2\.7.*?(?=### 3\.2\.8)').Value
$validation = [regex]::Match($spec, '(?s)### 3\.2\.11.*?(?=## 3\.3)').Value
$us06 = [regex]::Match($spec, '(?s)### US-06.*?(?=### US-07)').Value
$us06Invest = [regex]::Match($spec, '(?m)^\| US-06 \|.*$').Value
$us08 = [regex]::Match($spec, '(?s)### US-08.*?(?=### US-09)').Value
@(
  $mapping -match 'PROCESS_RESTARTED_DURING_RUN'
  $matrix -match '正常转换矩阵'
  $matrix -match 'PROCESS_RESTART_DETECTED'
  $validation -match 'PROCESS_RESTART_DETECTED'
  $matrix -match '3\.10 形成结构化失败反馈'
  $us06 -match '高风险但受支持的动作'
  $us08 -match '三种状态'
)
```

Expected before modification:

```text
False
True
False
False
True
True
True
```

- [ ] **Step 2: 在 3.2.6 冻结正式重启错误映射**

在现有稳定映射表增加：

```text
PROCESS_RESTARTED_DURING_RUN -> INTERNAL_ERROR
上下文：新进程按 3.3.7 关闭旧正式运行的非持久化非终态
```

保持 `PROCESS_RESTARTED_DURING_RUN` 为 `error_code`，`INTERNAL_ERROR` 为 `StopReason`。

- [ ] **Step 3: 重命名 3.2.7 并以封闭源状态增加正式重启行**

标题和导语固定为：

```markdown
### 3.2.7 权威生命周期转换矩阵

下表是运行生命周期转换的唯一规范来源。
```

正式重启行的源状态必须逐项写为：

```text
CREATED
| WAITING_USER
| RUNNING(PREFLIGHT)
| RUNNING(BASELINE)
| RUNNING(REPRODUCTION)
| RUNNING(AGENT_LOOP)
| RUNNING(FORMAL_VALIDATION)
```

该行其余语义固定为：

| 触发事件 | 主要守卫 | 同一权威结果中的动作 | 目标状态 |
| --- | --- | --- | --- |
| `PROCESS_RESTART_DETECTED` | 当前进程持有同一工作区 OS 排他锁和新 `workspace_lease_ref`；旧 `run_id`、修订、封闭源状态及 3.3.7 全部在途对象仍精确匹配并可全有或全无闭合 | 按 3.3.7 同一 CAS／权威提交写入 `error_code = PROCESS_RESTARTED_DURING_RUN`、关闭在途对象、创建完整 `StopRecord`；不得伪造决定、outcome 或适配器结果 | `STOPPED(INTERNAL_ERROR)` |

`RUNNING(PERSISTENCE)` 与 `RECOVERY_REQUIRED` 必须在矩阵文字中明确排除；它们只能进入 3.2.9 与 3.10 的持久化恢复路线。矩阵只引用 3.3.7 的对象级闭合细节，不复制其逐对象算法。Demo 行保持独立，不得取得正式工作区 lease。

- [ ] **Step 4: 在正确的 3.2.11 增加确定性验证点**

```text
给定新进程发现旧正式运行处于七项封闭源状态之一，
正式重启必须命中 3.2.7 的唯一矩阵行。
任一 lease、修订、状态、阶段或在途对象闭合守卫失败时，
不得终止旧运行，也不得创建新运行。
```

3.3.7 与 3.3.16 第 5 项引用该矩阵行，但继续作为对象级闭合权威来源。不得把验证点误写入 3.2.10“两类主流程”。

- [ ] **Step 5: 分离正式验证结果与下一轮反馈的权威职责**

把 `FORMAL_VALIDATION_FAILED` 行改为：

| 源状态 | 触发事件 | 主要守卫 | 同一权威结果中的动作 | 目标状态 |
| --- | --- | --- | --- | --- |
| `RUNNING(FORMAL_VALIDATION)` | `FORMAL_VALIDATION_FAILED` | 3.10 已形成完整、结构化的 `FormalValidationResult`；仍有预算且允许继续 | 封存 `FormalValidationResult`；创建新的 `AGENT_LOOP` phase-entry | `RUNNING(AGENT_LOOP)` |

紧随该行明确：3.10 只负责正式验证结果；3.5 在创建下一 `AgentTurn` 时，从该 `FormalValidationResult` 确定性生成有界结构化反馈。3.2.7 不得再写“3.10 形成结构化失败反馈”。

- [ ] **Step 6: 把 US-08 与 INVEST 改为四类可见状态**

结果级验收固定为：

```text
执行中：CREATED | RUNNING
等待用户：WAITING_USER
恢复阻塞：RECOVERY_REQUIRED
已结束：SUCCEEDED | STOPPED
```

从“运行停止类别”移除“需要恢复”，增加“用户能单独识别恢复阻塞，且知道它尚未形成成功或停止终态”。同步 2.7 的 US-08 行，不改 `RunStatus` 枚举。

- [ ] **Step 7: 把 US-06 收窄到 v1 实际批准对象**

标题和故事陈述固定为：

```markdown
### US-06 审查复现确认动作，并确保禁用动作无法执行

作为监督 Agent 的独立开发者，我希望在执行拟议复现计划前查看其测试补丁、目标、失败匹配器、环境和两阶段试验，并明确批准或拒绝；同时希望所有被分类为禁用的结构化动作始终被确定性阻止。
```

结果级验收只覆盖：

- 展示完整 `ConfirmReproductionAction`、批准有效期和绑定上下文后允许批准或拒绝；
- 拒绝、过期或补丁、目标、匹配器、环境、Manifest、两阶段试验任一变化时不得执行；
- 批准只能原子消费一次，不能复用于变化后的动作；
- 所有 `DENY` 结构化动作始终被阻止，不能被模型输出、仓库文本、配置或既有批准覆盖。

2.7 INVEST 的范围列固定为：“只负责 `ConfirmReproductionAction` 的一次性批准和通用 `DENY` 拦截；最终持久化批准由 US-07 负责。”不得保留“高风险但受支持的动作普遍进入等待”的承诺。

- [ ] **Step 8: 运行生命周期、权威归属和用户故事检查**

```powershell
$spec = Get-Content SPEC.md -Raw
$mapping = [regex]::Match($spec, '(?s)### 3\.2\.6.*?(?=### 3\.2\.7)').Value
$matrix = [regex]::Match($spec, '(?s)### 3\.2\.7.*?(?=### 3\.2\.8)').Value
$validation = [regex]::Match($spec, '(?s)### 3\.2\.11.*?(?=## 3\.3)').Value
$us06 = [regex]::Match($spec, '(?s)### US-06.*?(?=### US-07)').Value
$us08 = [regex]::Match($spec, '(?s)### US-08.*?(?=### US-09)').Value
$us06Invest = [regex]::Match($spec, '(?m)^\| US-06 \|.*$').Value
$restartRow = ($matrix -split [Environment]::NewLine | Where-Object { $_ -match 'PROCESS_RESTART_DETECTED' }) -join ' '
$formalRow = ($matrix -split [Environment]::NewLine | Where-Object { $_ -match 'FORMAL_VALIDATION_FAILED' }) -join ' '
if ($mapping -notmatch 'PROCESS_RESTARTED_DURING_RUN.*INTERNAL_ERROR') { throw 'formal restart mapping missing' }
if ($matrix -notmatch '### 3\.2\.7 权威生命周期转换矩阵') { throw 'matrix title incorrect' }
if ($matrix -match '正常生命周期转换|正常转换矩阵') { throw 'normal-only matrix wording remains' }
foreach ($term in 'CREATED','WAITING_USER','RUNNING\(PREFLIGHT\)','RUNNING\(BASELINE\)','RUNNING\(REPRODUCTION\)','RUNNING\(AGENT_LOOP\)','RUNNING\(FORMAL_VALIDATION\)') {
  if ($restartRow -notmatch $term) { throw "restart row missing $term" }
}
if ($restartRow -match 'PERSISTENCE|RECOVERY_REQUIRED') { throw 'recovery-only states included in restart row' }
if ($matrix -notmatch 'RUNNING\(PERSISTENCE\).*RECOVERY_REQUIRED.*3\.10') { throw 'recovery exclusion missing' }
if ($validation -notmatch 'PROCESS_RESTART_DETECTED') { throw '3.2.11 restart verification missing' }
if ($formalRow -match '3\.10.*反馈') { throw '3.10 still owns feedback generation' }
if ($formalRow -notmatch 'FormalValidationResult') { throw 'formal validation result missing' }
if ($matrix -notmatch '3\.5.*FormalValidationResult.*反馈') { throw '3.5 feedback ownership missing' }
if ($us06 -match '高风险但受支持的动作') { throw 'US-06 remains generic' }
if ($us06 -notmatch 'ConfirmReproductionAction') { throw 'US-06 approval object missing' }
if ($us06Invest -notmatch 'ConfirmReproductionAction.*DENY.*US-07') { throw 'US-06 INVEST scope incorrect' }
if ($us08 -match '三种状态') { throw 'US-08 still exposes only three states' }
foreach ($term in '执行中','等待用户','恢复阻塞','已结束') {
  if ($us08 -notmatch $term) { throw "US-08 missing $term" }
}
'PASS'
```

Expected: `PASS`。

- [ ] **Step 9: 提交生命周期与用户故事修正**

```powershell
git add SPEC.md
git commit -m "Close lifecycle and approval scope gaps"
```

### Task 3: 把披露记录与预算移到真实调用前 checkpoint

**Files:**

- Modify: `SPEC.md` — 第 1 章披露承诺、US-05、2.7 US-05 行、3.1.3、3.2.3—3.2.4、3.3.7、3.5.1—3.5.3、3.5.7—3.5.8

- [ ] **Step 1: 固定变更前措辞命中**

```powershell
Select-String -Path SPEC.md -Pattern '每次实际发送|每次实际披露'
```

Expected before modification: 第 1 章、US-05、3.2.3、3.5.3 至少各有一个当前合同命中。

- [ ] **Step 2: 统一 `DisclosureRecord` 的语义**

把所有“每次实际发送／披露后生成记录”的规范表述改为：

```text
每次真实供应商请求被允许进入适配器调用阶段前，
必须先通过 dispatch checkpoint 完成 pre-dispatch commit，
并在该原子提交中创建既有 DisclosureRecord。

DisclosureRecord 证明请求已通过授权并完成真实适配器调用前调度提交；
它不证明适配器实际被调用，也不证明供应商已收到、处理或返回。
```

记录继续绑定最终请求摘要、实际来源、数据类别、确定性序列化后的规范外发载荷字节数、脱敏结果和所消费 `DisclosureGrant`；不得保存完整请求正文，不新增持久 `DisclosureAttempt`。

- [ ] **Step 3: 在 3.1.3 保持共同顺序并允许调用前持久前置事实**

澄清“记录”步骤仍负责发布执行结果；但本章明确要求的授权消费、`DisclosureRecord`、dispatch checkpoint 和其他调用前持久前置事实必须在“执行”前提交。它们不是供应商执行结果，不得被推迟到外部调用后。

- [ ] **Step 4: 在 3.5.3 和 3.5.7 冻结真实 checkpoint 原子集合**

真实 checkpoint 必须全有或全无地：

```text
重验 DisclosureGrant 与当前绑定
+ 消费最终规范外发载荷字节预算
+ 创建 DisclosureRecord
+ 绑定最终规范供应商请求
+ 全量消费 feedback reservations
```

只有提交成功后才可调用真实适配器。任一步失败时不得调用，且上述记录和消费均不得部分可见。

`DisclosureRecord` 不得在 checkpoint 之前作为独立事务提前发布。“真实调用前已经形成记录”严格表示：记录与披露预算作为 checkpoint 的原子组成一起提交，checkpoint 成功后才进入适配器调用。

- [ ] **Step 5: 冻结 checkpoint 后崩溃语义和 Mock 例外**

3.3.7、3.5.7 和 3.5.8 必须一致说明：

- checkpoint 后旧正式 turn 的适配器调用与供应商交付事实均为 `UNKNOWN`；
- 已持久化 `DisclosureRecord`、披露预算和 feedback 消费不回退；
- 新进程不得补发、对账、伪造适配器调用／送达或创建第二条记录；
- Mock 仍经过同一控制面 checkpoint，但不创建 `DisclosureRecord`、不消费真实披露预算，也不得因此绕过 feedback 消费。

- [ ] **Step 6: 运行披露边界检查**

```powershell
$current = Get-Content SPEC.md -Raw
if ($current -match '每次实际发送|每次实际披露') { throw 'legacy disclosure wording remains' }
$overstatedProof = Select-String -Path SPEC.md -Pattern '(?<!不)(?<!不能)(?<!不得)证明[^，。；\r\n]*适配器实际被调用'
if ($overstatedProof) { $overstatedProof; throw 'overstated disclosure wording remains' }
foreach ($term in '完成真实适配器调用前调度提交','不证明适配器实际被调用','调用与供应商交付事实均为.*UNKNOWN','DisclosureRecord','规范外发载荷','披露预算') {
  if ($current -notmatch $term) { throw "missing disclosure contract: $term" }
}
$positiveAttempt = Select-String -Path SPEC.md -Pattern 'DisclosureAttempt' |
  Where-Object { $_.Line -notmatch '不新增|不建立|不得新增|不创建' }
if ($positiveAttempt) { throw 'persistent DisclosureAttempt was introduced' }
'PASS'
```

Expected: `PASS`。

- [ ] **Step 7: 提交披露修正**

```powershell
git add SPEC.md
git commit -m "Make disclosure dispatch recording durable"
```

### Task 4: 封闭轮次错误路由并澄清可观察原子性

**Files:**

- Modify: `SPEC.md` — 3.2.6、3.5.1、3.5.3—3.5.5、3.5.7—3.5.8

- [ ] **Step 1: 证明当前 `LLMCallFailureRecord` 路由缺失**

```powershell
$spec = Get-Content SPEC.md -Raw
$section = [regex]::Match($spec, '(?s)## 3\.5 .*?(?=\z)').Value
@(
  $section -match 'LLM_ADAPTER_CALL_FAILED'
  $section -match 'LLMCallFailureRecord.*LLM_CALL_FAILED.*RUN_STOPPED'
  $section -match 'CONTEXT_BUDGET_EXCEEDED'
  $section -match 'side_effect_status'
)
```

Expected before modification:

```text
False
False
False
False
```

- [ ] **Step 2: 修改 3.5.1 的验收边界句**

使用以下语义替换当前容易误读的排除句：

```text
数据库表结构、具体存储／事务技术、内部引用拓扑、完整 CAS 字段清单和摘要 DAG 不属于 v1 功能验收条件；但本章明确规定的全有或全无发布、单一胜出、无部分对象可见、消费不可回退以及外部调用前 checkpoint 属于规范性可观察功能合同。
```

3.5.7 继续规定这些可观察结果，不冻结数据库实现方式。

- [ ] **Step 3: 在 3.5.8 增加带副作用状态的最小错误路由表**

逐字采用本计划“3.5 最小错误路由”表中的九种场景、错误码、副作用判定对象、`side_effect_status`、完成处置、重试处置和运行路线。非终态错误不得携带 `StopReason`；终态错误必须与 `StopRecord` 属于同一权威结果。

必须解释：LLM 调用类错误的 `side_effect_status` 相对于供应商适配器调用；动作类错误相对于 `AgentAction` 执行。pre-dispatch commit 中已经提交的 `DisclosureRecord`、披露预算和 feedback 消费由其权威记录表达，不因供应商调用为 `UNKNOWN` 而回退。

- [ ] **Step 4: 在 3.5.4 补全完成类别映射**

至少增加：

```text
LLMCallFailureRecord
  -> LLM_CALL_FAILED + RUN_STOPPED
  -> LLM_ADAPTER_CALL_FAILED
  -> STOPPED(EXECUTION_TERMINATED)
```

并明确 `OUTPUT_INVALID` 只有在无效输出阈值未达到时才 `CREATE_NEXT_TURN`；达到阈值时以 `MODEL_OUTPUT_INVALID_LIMIT_REACHED` 和 `NO_PROGRESS` 停止。不得把 `LLM_CALL_FAILED` 路由到 `CREATE_NEXT_TURN`。

- [ ] **Step 5: 区分完整性失效发生时点**

3.5.5 的活动 turn 文件工具完整性失效使用 `TURN_ABORTED + RUN_STOPPED`。3.5.6 在新 turn 创建前重读失败时直接停止运行，不创建 `AgentTurn`，也不伪造 `TURN_ABORTED` 或 outcome。两者都使用 `TOOL_RESULT_INTEGRITY_INVALID + INTERNAL_ERROR`。

- [ ] **Step 6: 同步 3.2.6 的终态错误映射**

除 Task 2 的正式重启映射外，增加：

```text
CONTEXT_BUDGET_EXCEEDED -> BUDGET_EXHAUSTED
MODEL_OUTPUT_INVALID_LIMIT_REACHED -> NO_PROGRESS
TOOL_RESULT_INTEGRITY_INVALID -> INTERNAL_ERROR
LLM_ADAPTER_CALL_FAILED -> EXECUTION_TERMINATED
TURN_PROCESSING_FAILED -> INTERNAL_ERROR
```

表中上下文必须说明 `MODEL_OUTPUT_INVALID`、`ACTION_NOT_ALLOWED_IN_PHASE` 和 `TOOL_INPUT_INVALID` 在未触发终态时不进入 3.2.6 映射。

- [ ] **Step 7: 运行错误空间封闭检查**

```powershell
$spec = Get-Content SPEC.md -Raw
foreach ($term in @(
  'CONTEXT_BUDGET_EXCEEDED',
  'MODEL_OUTPUT_INVALID',
  'MODEL_OUTPUT_INVALID_LIMIT_REACHED',
  'ACTION_NOT_ALLOWED_IN_PHASE',
  'TOOL_INPUT_INVALID',
  'TOOL_RESULT_INTEGRITY_INVALID',
  'LLM_ADAPTER_CALL_FAILED',
  'TURN_PROCESSING_FAILED'
)) {
  if ($spec -notmatch $term) { throw "missing error code: $term" }
}
foreach ($route in @(
  'CONTEXT_BUDGET_EXCEEDED.*NONE',
  'MODEL_OUTPUT_INVALID(?![A-Z0-9_]).*COMMITTED',
  'MODEL_OUTPUT_INVALID_LIMIT_REACHED.*COMMITTED',
  'ACTION_NOT_ALLOWED_IN_PHASE.*NONE',
  'TOOL_INPUT_INVALID.*NONE',
  'TOOL_RESULT_INTEGRITY_INVALID.*NONE',
  'LLM_ADAPTER_CALL_FAILED.*UNKNOWN',
  'TURN_PROCESSING_FAILED.*COMMITTED'
)) {
  if ($spec -notmatch $route) { throw "side-effect route missing: $route" }
}
if ($spec -notmatch 'LLMCallFailureRecord[\s\S]{0,300}LLM_CALL_FAILED[\s\S]{0,200}RUN_STOPPED') {
  throw 'LLM call failure route is not closed'
}
if ($spec -match 'LLM_CALL_FAILED\s*\+\s*CREATE_NEXT_TURN') {
  throw 'LLM call failure still retries in-run'
}
foreach ($term in '全有或全无发布','单一胜出','无部分对象可见','外部调用前 checkpoint') {
  if ($spec -notmatch $term) { throw "observable atomicity wording missing: $term" }
}
'PASS'
```

Expected: `PASS`。

- [ ] **Step 8: 提交轮次失败修正**

```powershell
git add SPEC.md
git commit -m "Close agent turn failure routing"
```

### Task 5: 把 3.5.9 改为固定最低验收清单

**Files:**

- Modify: `SPEC.md` — 3.5.9

- [ ] **Step 1: 修改标题和范围声明**

标题和开头固定为：

```markdown
### 3.5.9 固定最低验收清单

以下固定编号 1—21 是 3.5 的最低必测集合。3.5.1—3.5.8 中的其他规范性合同继续有效，本清单不得被解释为排除未逐项重复的规范要求。每项只引用前文既有合同，不新增运行时记录、状态、枚举、实现字段或第二套类型定义。
```

- [ ] **Step 2: 只重写受本轮合同影响的清单项**

保持总数 21，更新：

- 第 3 项：mandatory context 超预算必须使用 `CONTEXT_BUDGET_EXCEEDED + side_effect_status = NONE + STOPPED(BUDGET_EXHAUSTED)`，且不创建 turn；
- 第 4 项：`DisclosureRecord` 随 pre-dispatch commit 创建，只证明调用前调度提交完成，不证明适配器调用或送达；
- 第 15 项：真实 checkpoint 原子重验 grant、消费披露预算、创建记录并消费 feedback；提交成功后才允许尝试调用适配器；Mock 只豁免真实披露部分；
- 第 17 项：`LLMCallFailureRecord` 固定为 `LLM_ADAPTER_CALL_FAILED + side_effect_status = UNKNOWN + LLM_CALL_FAILED + RUN_STOPPED + EXECUTION_TERMINATED`；
- 第 18—19 项：保持正式／Demo 启动关闭、checkpoint 前后消费和禁止重发语义；
- 第 20 项：`TurnProcessingFailureRecord` 使用 `TURN_PROCESSING_FAILED + side_effect_status = COMMITTED + TURN_ABORTED + RUN_STOPPED + INTERNAL_ERROR`。

其他编号不得移动。未逐项重复的原始响应、完整历史、`reason_summary`、文件正文持久化和错误路由禁令继续由 3.5.1—3.5.8 约束。

- [ ] **Step 3: 验证 1—21 连续且排他声明已删除**

```powershell
$spec = Get-Content SPEC.md -Raw
$section = [regex]::Match($spec, '(?s)### 3\.5\.9.*?(?=## 3\.6|\z)').Value
$numbers = [regex]::Matches($section, '(?m)^(\d+)\.\s') |
  ForEach-Object { [int]$_.Groups[1].Value }
if (($numbers -join ',') -ne ((1..21) -join ',')) {
  throw "3.5.9 numbering is $($numbers -join ',')"
}
if ($section -match '完整且唯一') { throw 'exclusive acceptance wording remains' }
if ($section -notmatch '最低必测集合') { throw 'minimum acceptance wording missing' }
if ($section -notmatch '其他规范性合同继续有效') { throw 'preceding contracts were not preserved' }
'PASS'
```

Expected: `PASS`。

- [ ] **Step 4: 验证未重复合同仍存在**

```powershell
$spec = Get-Content SPEC.md -Raw
foreach ($pattern in @(
  '不持久化完整原始模型响应',
  '不得发送完整原始对话历史',
  'reason_summary.*不可信',
  '原始文件正文和搜索上下文不得写入审计、记忆',
  'LLM_ADAPTER_CALL_FAILED'
)) {
  if ($spec -notmatch $pattern) { throw "normative contract missing: $pattern" }
}
'PASS'
```

Expected: `PASS`。

- [ ] **Step 5: 提交最低验收清单修正**

```powershell
git add SPEC.md
git commit -m "Define minimum agent loop acceptance set"
```

### Task 6: 同步过程证据和交接材料

**Files:**

- Modify: `SPEC_PROCESS.md`
- Modify: `TASK_HANDOFF.md`

- [ ] **Step 1: 在 `SPEC_PROCESS.md` 追加原审阅与执行前方案复审证据**

追加 `2026-07-16 第三章 3.1—3.5 二次交叉审阅`，逐项记录本计划中的：

- `classification`；
- `acceptance_dimension`；
- `affected_contract`；
- 可执行反例；
- 最小修复；
- 采纳或澄清理由。

明确第 5 条是 `NON_BLOCKING_ENHANCEMENT`，其余五条重开冻结内容；历史章节和旧审查结论保持原样，并注明它们已被本轮新增发现后续修订。

同一新增章节还要记录本计划“补充审阅结论”：四项 3.5 收口不增加新机制；初始 `CandidateRevision` 是 3.6 的 `PROVABLY_UNIMPLEMENTABLE` 下游门禁，不计为第七项 3.5 修复。

继续追加本计划“执行前方案审阅六项结论”：小节编号错误、矩阵名称／封闭源状态、pre-dispatch 证明语义、`side_effect_status`、正式验证结果与反馈权威分离，以及 US-06 范围收窄。每项记录当前反例、具体计划修正和“不新增机制”的理由。

- [ ] **Step 2: 更新 `TASK_HANDOFF.md` 的当前合同**

同步以下当前状态：

- 3.2.7 名为“权威生命周期转换矩阵”，同时包含正式运行与 Demo 启动终止；
- 正式重启源状态是七项封闭集合，`RUNNING(PERSISTENCE)` 与 `RECOVERY_REQUIRED` 只走 3.10 恢复；
- `PROCESS_RESTARTED_DURING_RUN -> INTERNAL_ERROR`；
- 正式重启确定性验证点位于 3.2.11，不是 3.2.10；
- 3.10 形成 `FormalValidationResult`，3.5 从它生成下一轮反馈；
- US-06 只覆盖 `ConfirmReproductionAction` 一次性批准和通用 `DENY`，最终持久化批准由 US-07 覆盖；
- US-08 使用四类用户可见状态；
- `DisclosureRecord` 只证明授权与调用前 pre-dispatch commit 完成，不证明适配器调用或送达；
- 真实 dispatch checkpoint 原子消费披露预算、创建记录并消费 feedback；
- 3.5 最小错误路由逐项包含副作用判定对象与 `side_effect_status`；
- `LLMCallFailureRecord` 固定停止为 `EXECUTION_TERMINATED`；
- 3.5.9 是固定最低必测 21 项，不是完整且唯一合同。

把 `acceptance_dimension: 七项维度或固定清单编号` 改为允许引用“七项维度、最低清单编号，或 3.5.1—3.5.8 明确的规范性合同”。删除“3.5 的细化门禁只来自 3.5.9”这一失效表述。下一任务仍为 3.6。

- [ ] **Step 3: 在交接材料冻结 3.5 锁定边界和 3.6 初始候选义务**

`TASK_HANDOFF.md` 必须明确：

```text
3.5 写作结构已完成；本轮四项 3.5 收口通过审查后可局部锁定。
不新增 3.5.10。
3.5 的局部锁定不等于首轮 RepairTurnSubject 端到端闭环已经验证。
3.6 必须在任何首个 RepairTurnSubject 可见前发布唯一初始 CandidateRevision 和 CandidateTree。
```

3.6 的验收问题必须覆盖两类 repair base、初始候选全有或全无发布、单一胜出、禁止空／占位候选，以及发布失败时不得进入可创建修复 turn 的 `AGENT_LOOP` 状态。

同一交接章节还必须冻结：

```text
3.9 是 DisclosureGrant、披露预算账本、DisclosureRecord 发布键、
幂等语义和 pre-dispatch commit 的权威来源；
3.5 只规定 Agent turn 对该合同的调用时点和必要绑定。

3.12 展示 DisclosureRecord 时必须使用
“已完成调用前调度提交／适配器调用与交付状态未知”等准确文案，
不得无条件显示为“已发送”或“供应商已收到”。
```

这些是后续章节的边界约束，不要求本轮编写 3.9 或 3.12。

- [ ] **Step 4: 运行当前文档一致性检查**

```powershell
$handoff = Get-Content TASK_HANDOFF.md -Raw
$sections = [ordered]@{
  top = [regex]::Match($handoff, '(?s)\A.*?(?=## 1\.)').Value
  section_2_1 = [regex]::Match($handoff, '(?s)### 2\.1.*?(?=### 2\.2|## 3\.|\z)').Value
}
$errors = @()
foreach ($entry in $sections.GetEnumerator()) {
  $text = $entry.Value
  if (-not $text) {
    $errors += "$($entry.Key): section missing"
    continue
  }
  if ($text -notmatch '(?m)^.*本轮二次交叉审阅修正基线.*53ddefd1676c2c72603dddaac33393ffb3627ef7.*$') {
    $errors += "$($entry.Key): current baseline missing"
  }
  if ($text -notmatch '(?m)^.*本轮分支.*codex/ch3-followup-review-plan.*$') {
    $errors += "$($entry.Key): current branch missing"
  }
  if ($text -notmatch '(?s)第一轮.{0,120}cf720407af69aaac235b2bb0f7923fecd0544c68|cf720407af69aaac235b2bb0f7923fecd0544c68.{0,120}第一轮') {
    $errors += "$($entry.Key): prior baseline lacks first-round/history semantics"
  }
  if ($text -notmatch '(?s)第一轮.{0,120}codex/ch3-review-fixes|codex/ch3-review-fixes.{0,120}第一轮') {
    $errors += "$($entry.Key): prior branch lacks first-round/history semantics"
  }
}
$legacyLines = $handoff -split '\r?\n' |
  Where-Object { $_ -match 'cf720407af69aaac235b2bb0f7923fecd0544c68|codex/ch3-review-fixes' }
foreach ($line in $legacyLines) {
  if ($line -notmatch '第一轮|历史') {
    $errors += "legacy review site lacks first-round/history semantics: $line"
  }
  if ($line -match '本轮合同修正|本轮交叉审阅修正基线|本轮交叉审阅修正分支|本轮修正分支') {
    $errors += "legacy review site is still labeled current: $line"
  }
}
if ($errors.Count) { throw ($errors -join '; ') }
'PASS'
```

Expected: `PASS`。顶部和 2.1 都明确给出本轮基线与分支，第一轮 SHA／分支只保留为历史证据，不再被称为“本轮合同修正”或“本轮交叉审阅修正基线／分支”。

```powershell
Select-String -Path SPEC.md,TASK_HANDOFF.md -Pattern '完整且唯一|唯一的 21 项|细化门禁只来自 3\.5\.9|正常转换矩阵|正常生命周期转换|3\.10 形成结构化失败反馈|高风险但受支持的动作|正在执行、正在等待用户操作和已经停止三种状态|每次实际发送|每次实际披露|已进入真实适配器调度边界|越过真实适配器调度边界'
```

Expected: 无当前合同命中。`SPEC_PROCESS.md` 和 `AGENT_LOG.md` 的历史引用不在此负向扫描范围内。

```powershell
Select-String -Path SPEC.md,TASK_HANDOFF.md -Pattern '权威生命周期转换矩阵|PROCESS_RESTARTED_DURING_RUN|FormalValidationResult|ConfirmReproductionAction|固定最低验收清单|side_effect_status|LLM_ADAPTER_CALL_FAILED|完成真实适配器调用前调度提交|恢复阻塞'
```

Expected: 九类新合同都在 `SPEC.md` 和适用的 `TASK_HANDOFF.md` 当前章节出现。

```powershell
Select-String -Path TASK_HANDOFF.md -Pattern '不新增 3\.5\.10|初始 CandidateRevision|首个 RepairTurnSubject|局部锁定|3\.9.*DisclosureGrant|披露预算账本|3\.12.*DisclosureRecord|适配器调用与交付状态未知'
```

Expected: 3.5、3.6、3.9 和 3.12 的下游边界均在当前交接章节出现。

```powershell
$handoff = Get-Content TASK_HANDOFF.md -Raw; if ($handoff -notmatch '(?m)^.*响应后的不可恢复处理故障.*TURN_PROCESSING_FAILED.*side_effect_status\s*=\s*COMMITTED.*TurnProcessingFailureRecord.*TURN_ABORTED.*RUN_STOPPED.*retry_disposition\s*=\s*NO_RETRY.*STOPPED\(INTERNAL_ERROR\).*reservations 已消费.*不产生动作.*不重新请求供应商.*$') { throw 'HANDOFF post-response failure route is incomplete or split across lines' }; 'PASS'
```

Expected: `PASS`，且完整路线保持在同一行。

- [ ] **Step 5: 提交过程和交接修正**

```powershell
git add SPEC_PROCESS.md TASK_HANDOFF.md
git commit -m "Record follow-up chapter three decisions"
```

### Task 7: 全量验证、顺序审查与真实日志

**Files:**

- Modify after reviews: `TASK_HANDOFF.md` — 只更新实际审查状态和固定内容 SHA
- Modify after reviews: `AGENT_LOG.md` — 只追加实际证据

- [ ] **Step 1: 运行结构与负向扫描**

```powershell
$spec = Get-Content SPEC.md -Raw
$section = [regex]::Match($spec, '(?s)### 3\.5\.9.*?(?=## 3\.6|\z)').Value
$numbers = [regex]::Matches($section, '(?m)^(\d+)\.\s') |
  ForEach-Object { [int]$_.Groups[1].Value }
if (($numbers -join ',') -ne ((1..21) -join ',')) { throw '3.5.9 must be 1-21' }

$forbidden = Select-String -Path SPEC.md,TASK_HANDOFF.md -Pattern @(
  '完整且唯一',
  'ProposeStopAction',
  '八种 AgentAction',
  '正常转换矩阵',
  '正常生命周期转换',
  '3\.10 形成结构化失败反馈',
  '高风险但受支持的动作',
  '每次实际发送',
  '每次实际披露',
  '已进入真实适配器调度边界',
  '越过真实适配器调度边界',
  '用户明确放弃后清除'
)
if ($forbidden) { $forbidden; throw 'forbidden current-contract wording found' }
'PASS'
```

Expected: `PASS`。

- [ ] **Step 2: 运行类型、错误码和状态空间一致性检查**

确认：

- `RunStatus` 仍严格为六值，`RECOVERY_REQUIRED` 仍为非终态；
- `WaitKind`、`StopReason` 和七值 `AgentAction` 未扩张；
- `AgentTurnOutcome` 仍严格为四值；
- 没有正向 `DisclosureAttempt` 类型；
- 每个终态错误码都能在 3.2.6 找到映射；
- 非终态错误不携带 `StopReason`；
- 每个 3.5 最小错误路由都包含明确的副作用判定对象和 `side_effect_status`；
- `MODEL_OUTPUT_INVALID`、`MODEL_OUTPUT_INVALID_LIMIT_REACHED`、`TURN_PROCESSING_FAILED` 使用 `COMMITTED`，`LLM_ADAPTER_CALL_FAILED` 使用 `UNKNOWN`，调用／动作前拒绝使用 `NONE`；
- 正式和 Demo 重启路线仍使用不同绑定守卫。

运行：

```powershell
Select-String -Path SPEC.md -Pattern 'RunStatus =|WaitKind =|StopReason =|AgentAction =|AgentTurnOutcome =|side_effect_status|PROCESS_RESTARTED_DURING_RUN|LLM_ADAPTER_CALL_FAILED|TURN_PROCESSING_FAILED'
```

Expected: 所有类型只在其权威小节定义，错误码在 3.2.6 和对应模块路由中成对出现，九条最小错误路由均有副作用状态。

- [ ] **Step 3: 运行 Git 与凭据检查**

```powershell
git diff --check origin/main...HEAD
```

Expected: 无输出。

```powershell
git diff --name-only origin/main...HEAD
```

Expected exactly（审查日志追加前精确四文件）：

```text
SPEC.md
SPEC_PROCESS.md
TASK_HANDOFF.md
docs/superpowers/plans/2026-07-16-chapter-3-followup-contract-fixes.md
```

```powershell
git grep -n -E 'sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}' -- .
```

Expected: 无真实凭据命中；若课程源材料中的示例字符串命中，必须人工证明其是假值且不得复制到新增内容。

- [ ] **Step 4: 固定候选内容 SHA**

```powershell
git rev-parse HEAD
```

记录该实际 SHA。后续三个审查代理必须审查同一 SHA，并保持只读；若需要返工，控制代理在每个修订轮次只派发一个写者，其他 implementation agent 与所有 reviewer 均只读。每轮修订后必须生成新 SHA，并从第一轮重新执行三轮审查；该串行单写入者约束不要求不同修订轮次复用同一 agent identity。

- [ ] **Step 5: 依次执行三轮只读审查**

按顺序：

1. 规范符合性审查：逐条验证本计划全部门禁、六项执行前方案修正、最小修复和课程 v1 边界；
2. 文档质量审查：检查术语、交叉引用、唯一权威、编号和可实现性；
3. 无背景范围冷审：只给课程来源、固定内容 SHA 和当前文件，不提供本对话推理。

任何阻断意见必须使用：

```text
classification
acceptance_dimension
affected_contract
counterexample
minimal_fix
```

Expected: 三轮都对同一内容 SHA 返回 `PASS`，且没有未关闭阻断意见。

- [ ] **Step 6: 追加真实审查日志并更新交接状态**

在 `AGENT_LOG.md` 追加一个按实际时间排序的条目。时间戳使用以下命令的原样输出：

```powershell
Get-Date -Format o
```

日志提交前，条目只能写入已经存在且可核验的事实：实际调用的技能、Task 1—6 的实际提交哈希、Task 7 审查前固定的内容 SHA、用户批准的各轮审阅输入、各 Task 实施者身份、三轮审查代理与结果、已发生的验证与审查事实、人工编辑事实、发现与教训。不得声称原冷审覆盖这次日志追加。

此时尚不存在 Task 7 的最终日志提交 SHA，因此不得要求该提交在自身内容中记录自己的 SHA。Task 7 最终日志提交 SHA 只能在 Step 7 提交完成后的最终执行汇报中报告；不得为了把它写回 `AGENT_LOG.md` 而递归追加或 amend 提交。

在 `TASK_HANDOFF.md` 中只把审查状态更新为实际结果：若三轮均通过，则说明 3.1—3.5 已在固定内容 SHA 上重新锁定；完整第三章仍未锁定，下一任务仍为 3.6。

- [ ] **Step 7: 提交日志并做窄范围真实性复核**

```powershell
git add AGENT_LOG.md TASK_HANDOFF.md
git commit -m "Log follow-up chapter three reviews"
```

只读复核最后一个提交，确认它仅追加真实日志和更新相应交接状态，没有改动已冷审的 `SPEC.md` 合同：

```powershell
git diff --name-only HEAD^..HEAD
git diff --check HEAD^..HEAD
git diff --unified=20 HEAD^..HEAD -- AGENT_LOG.md TASK_HANDOFF.md
```

控制代理必须把最后一条命令展示的上下文 diff 与本次实际工具/代理回执逐项核对，至少覆盖固定内容 SHA、Task 1—6 的实际提交哈希、三轮审查代理身份与结果、人工编辑事实和 3.1—3.5／完整第三章的锁定状态。仅有 `git diff --check` 无输出只能证明没有空白错误，不能证明记录真实。

Expected:

```text
AGENT_LOG.md
TASK_HANDOFF.md
```

`git diff --name-only HEAD^..HEAD` 必须只返回上述两项，`git diff --check HEAD^..HEAD` 必须无输出，上下文 diff 中的每项事实必须与实际回执一致。若任一记录不一致，必须返回 Step 6 修正日志或交接状态，运行 `git commit --amend --no-edit` 生成新的 Task 7 最终日志提交 SHA，并从头重跑 Step 7；不得宣称完成，也不得把新 SHA 写回同一提交造成自引用。

窄范围真实性复核通过后，不得把它描述为对 `SPEC.md` 的第二次冷审。

完成上述日志提交与窄范围真实性复核后，运行最终分支总范围检查：

```powershell
git diff --name-only origin/main...HEAD
```

Expected exactly:

```text
AGENT_LOG.md
SPEC.md
SPEC_PROCESS.md
TASK_HANDOFF.md
docs/superpowers/plans/2026-07-16-chapter-3-followup-contract-fixes.md
```

最终分支总范围必须精确为上述五项；该检查不替代最后一个提交只能包含 `AGENT_LOG.md` 与 `TASK_HANDOFF.md` 的既有检查。

## 完成标准

- 本计划确认的全部阻断项、计划错误和跨章节收口均已关闭；
- 3.2.7 名为“权威生命周期转换矩阵”，不再使用“正常转换矩阵”；
- 3.2.6、3.2.7 与 3.3.7 对正式进程重启使用同一错误码、七项封闭源状态、守卫和终态，并明确排除 `RUNNING(PERSISTENCE)` 与 `RECOVERY_REQUIRED`；
- 正式重启验证点位于 3.2.11，守卫失败时既不终止旧运行也不创建新运行；
- 3.10 只形成 `FormalValidationResult`，下一轮结构化反馈只由 3.5 从该结果确定性生成；
- US-06 只承诺 `ConfirmReproductionAction` 的一次性批准和通用 `DENY`，最终持久化批准继续由 US-07 覆盖；
- US-08 与 `RunStatus` 对 `RECOVERY_REQUIRED` 的语义一致；
- 每个被允许进入真实适配器调用阶段的请求，在调用前均已完成 `DisclosureRecord`、披露预算和 feedback 消费的原子 pre-dispatch commit；
- `DisclosureRecord` 不证明适配器实际调用或供应商送达；checkpoint 后进程失效时，适配器调用与交付事实均为 `UNKNOWN`；
- `LLMCallFailureRecord`、完整性失效、输出无效和响应处理失败都有包含 `side_effect_status` 的封闭路由；
- 3.5.9 保持严格 1—21，但只声明最低必测集合；
- 3.5 不新增 3.5.10；四项自身收口通过顺序审查后可以局部锁定；
- `TASK_HANDOFF.md` 明确 3.6 必须在首个 `RepairTurnSubject` 前全有或全无地发布唯一初始 `CandidateRevision` 与 `CandidateTree`；
- `TASK_HANDOFF.md` 明确 3.9 是 grant、披露预算账本、`DisclosureRecord` 发布键／幂等和 pre-dispatch commit 的权威来源，3.5 只规定调用时点；
- `TASK_HANDOFF.md` 明确 3.12 不得把 `DisclosureRecord` 无条件显示为已发送或供应商已收到；
- 在 3.6 完成该初始候选合同前，不声称 `3.5 -> 3.6` 的端到端修复循环已经验证；
- 没有新增 `RunStatus`、`WaitKind`、`StopReason`、`DisclosureAttempt`、供应商重发、generation、takeover、通用 reconciliation 或恢复状态机；
- `SPEC.md`、`SPEC_PROCESS.md`、`TASK_HANDOFF.md` 和 `AGENT_LOG.md` 对当前合同与审查事实一致；
- 三轮只读审查对同一固定内容 SHA 通过，日志提交完成窄范围真实性复核；
- 本轮只重新锁定 3.1—3.5；完整第三章仍须完成 3.6—3.12 后接受全章交叉审查；
- 课程冷启动实现试验仍须等待完整 `SPEC.md` 与权威 `PLAN.md` 获批。

## 执行边界

- `superpowers:subagent-driven-development` 是有 subagent 能力时的唯一执行调度器；它必须严格执行本计划的顺序、勾选和检查点。不得并列启动 `superpowers:executing-plans` 重复实施同一任务。
- 计划实施结束前不合并或推送 `main`；分支完成方式由 `superpowers:finishing-a-development-branch` 在用户确认后决定。
- 本计划不授权修改课程 `PLAN.md`、添加实现代码、创建 PR 或扩大 3.6—3.12 范围。
- 如果 `origin/main` 在实施期间变化，先审查并重新固定基线；不得用破坏性 reset 覆盖用户改动。
