# 第三章交叉审阅修订计划

> **For agentic workers:** 实施时先使用 `superpowers:using-git-worktrees`，再使用 `superpowers:executing-plans` 顺序修改；`SPEC.md` 只允许一个实施者编辑，审查代理保持只读。

**目标：** 关闭第三章审阅发现的合同矛盾和实现缺口，使 3.1—3.5 重新达到可锁定状态，同时保持课程 v1 范围。

**架构原则：** 优先修改既有联合、记录和失败关闭路线；不引入 generation、takeover、通用 reconciliation 或新的恢复状态机。

**基线：** 实施前重新获取并核验最新 `origin/main`。本轮隔离分支从 `cf720407af69aaac235b2bb0f7923fecd0544c68` 创建。

## 逐条判断

| # | 门禁分类 | 判断与处理 |
|---|---|---|
| 1 | `CONTRACT_CONTRADICTION` | 采纳。`SAME_ATTEMPT_REPLAY` 只能返回既有权威结果，绝不重新发出外部调用。 |
| 2 | `CONTRACT_CONTRADICTION` | 采纳但收敛。`DisclosureGrant` 只绑定运行级范围；最终请求摘要进入既有 `DisclosureRecord`，v1 不新增 `DisclosureAttempt` 持久类型。 |
| 3 | `PROVABLY_UNIMPLEMENTABLE` | 采纳。披露批准发生在正式创建 `AgentTurn` 前，等待路线不得留下孤立 turn。 |
| 4 | `CONTRACT_CONTRADICTION` | 采纳。增加 `TurnProcessingFailureRecord`，形成四值 `AgentTurnOutcome`。 |
| 5 | `CONTRACT_CONTRADICTION` | 采纳。以确定性 dispatch checkpoint 为消费边界；一旦越过，所有结果都消费 feedback reservations。 |
| 6 | `CONTRACT_CONTRADICTION` | 采纳方案二。终态保证撤销可达性和复用资格；删除失败允许永久 quarantine，不再承诺必然物理删除。 |
| 7 | `CONTRACT_CONTRADICTION` | 采纳。`REPOSITORY_STATE` 负责结构与策略；`SNAPSHOT_TREE` 唯一判定实际工作区字节、mode 和观察期间变化。 |
| 8 | `PROVABLY_UNIMPLEMENTABLE` | 采纳推荐方案。启动时将旧进程的非终态 Demo 原子终止为 `STOPPED(INTERNAL_ERROR)`。 |
| 9 | `CONTRACT_CONTRADICTION` | 采纳。增加稳定错误码—`StopReason` 映射，并修正第 1、2 章类型混用。 |
| 10 | `PROVABLY_UNIMPLEMENTABLE` | 采纳推荐方案。v1 删除 `ProposeStopAction`，动作联合缩为七值，停止只由控制面谓词触发。 |
| 11 | `NON_BLOCKING_ENHANCEMENT` | 采纳澄清。3.1.2 只要求语义输入输出、绑定和错误边界，不要求数据库字段或事务拓扑。 |
| 12 | `NON_BLOCKING_ENHANCEMENT` | 采纳范围冻结。v1 只支持严格 UTF-8 与 UTF-8 BOM。 |
| 13 | `CONCRETE_SECURITY_PATH` | 采纳。`CONFIG_SNAPSHOT` 只能读取目标仓库外的控制面配置；仓内配置只能从已发布快照读取。 |
| 14 | `CONTRACT_CONTRADICTION` | 采纳。限定 3.4 的无恢复范围，并删除“用户放弃恢复后直接清除”的不合法路线。 |

v1 实施边界表属于过程性范围收敛，不新增运行时义务，但一并采纳。

## 公共合同调整

- `AgentAction` 改为七值联合，删除 `ProposeStopAction`。
- `AgentTurnOutcome` 固定为：

```text
AcceptedTurnOutputRecord
| RejectedTurnOutputRecord
| LLMCallFailureRecord
| TurnProcessingFailureRecord
```

- `DisclosureGrant` 绑定供应商、端点、模型、允许来源/类别、脱敏规则、累计预算和有效期；`DisclosureRecord` 绑定本次最终请求摘要、实际来源、体量、脱敏结果和所消费 grant。
- `ContextProjectionDraft` 只是不持久化、不授权的纯计算；授权通过后才原子创建最终投影、turn、attempt、Manifest 和 reservations。
- 增加 `TextContentProfile = UTF8 | UTF8_BOM`。BOM 计入原始字节摘要，但不计入逻辑文本行列；补丁序列化必须原样恢复。
- 不增加 `RunStatus`、`WaitKind` 或 `StopReason`。`DEMO_SESSION_INVALIDATED` 是错误码，映射 `INTERNAL_ERROR`。

## 实施任务

### 1. 建立隔离现场

- 从最新 `origin/main` 创建分支 `codex/ch3-review-fixes` 和 worktree `D:\code\VesperCode\.worktrees\ch3-review-fixes`。
- 若 fetch 后 `origin/main` 不再是计划基线，先审查新增提交再继续。
- 不改根 worktree，不接触其未跟踪 `PLAN.md`、`AGENTS.md`、`.gitignore` 或 `REFLECTION.md`。
- 本文件不是课程权威 `PLAN.md`。

### 2. 统一重放语义

修改 `SPEC.md` 的 3.1.4、3.3.9、3.5.1、3.5.7、3.5.9：

- 把 `SAME_ATTEMPT_REPLAY` 冻结为“仅返回首次权威结果”。
- 删除“传输恢复、传输重放、重新请求供应商”等含义。
- 尚无权威结果时不得重发；准入检查走既有 `UNKNOWN/CONTROL_PLANE_ABORTED`，LLM 调用走既有失败或启动终止路线。
- 改写 3.5.9 第 18—19 项，但保持清单总数为 21。

提交：`Clarify same-attempt replay semantics`

### 3. 闭合披露、turn、outcome 与 feedback

修改 `SPEC.md` 第 1 章披露承诺、US-05、3.1.3、3.2.3—3.2.4、3.5.1—3.5.3、3.5.6—3.5.9：

```text
读取当前状态与 subject
→ 构建非权威 ContextProjectionDraft
→ 校验取消、预算和 DisclosureGrant 范围
→ 授权不足：创建 WaitContext，不创建 AgentTurn
→ 授权后在新 phase-entry 重新计算
→ 原子创建 AgentTurn、最终 ContextProjection、attempt、
  feedback records、Manifest 和 reservations
→ 提交 dispatch checkpoint
→ 调用适配器
```

- dispatch checkpoint 一旦提交即全量消费 reservations；Accepted、Rejected、调用失败和响应后处理失败都不退回。
- 只有 checkpoint 前取消或内部中止关闭但不消费。
- 响应后内部故障形成 `TurnProcessingFailureRecord + TURN_ABORTED + STOPPED(INTERNAL_ERROR)`。
- 3.5.9 保持 21 项，重写第 1、3、4、14—20 项。

提交：`Close disclosure and turn outcome contracts`

### 4. 修正工作区、配置、Demo、编码和恢复边界

修改 `SPEC.md` 第 1 章、3.2.7—3.2.9、3.3.5、3.3.10、3.3.14、3.3.16、3.4 导语、3.4.2—3.4.4、3.4.7、3.5.5：

- `REPOSITORY_STATE` 只验证 HEAD/index 可解析性、支持的结构和机制，并发布 `RepositoryPolicySnapshotRef`。
- `SNAPSHOT_TREE` 负责 index/HEAD 清洁性、非忽略未跟踪状态、tracked 字节/mode、双观察和时间性变化。
- 初始稳定不一致映射 `WORKTREE_DIRTY`；观察间变化映射 `WORKSPACE_MUTATED_DURING_ADMISSION`。
- Demo 启动失效产生 `error_code = DEMO_SESSION_INVALIDATED`、`StopReason = INTERNAL_ERROR` 和完整 `StopRecord`。
- `CONFIG_SNAPSHOT` 禁止打开目标仓库；`pyproject.toml`、pytest、Ruff、Mypy 等配置在 Snapshot 发布后由 `PROJECT_PROFILE` 读取。
- 明确永久 quarantine 语义；启动时不得重新使用隔离根。
- 3.4 的安全失败关闭只适用于 Snapshot、执行副本和普通 consumer；3.10 的权威持久化恢复保持唯一例外。
- 删除“用户明确放弃恢复后清除”，未解决恢复必须继续阻断工作区。
- 冻结 UTF-8/UTF-8 BOM 规则。

提交：`Separate admission and artifact boundaries`

### 5. 收紧停止权力、错误映射与 v1 范围

修改 `SPEC.md` 第 1、2 章、第三章导语、3.1.2、3.2.6、3.5.4、3.5.9：

- 删除全部 `ProposeStopAction` 和“LLM 提出停止建议”的规范性表述；动作矩阵改为七种。
- 在 3.2.6 增加带上下文的稳定错误码—`StopReason` 映射表，覆盖第 1、2 章全部终止错误名。
- 将 `WORKSPACE_CHANGED`、`BUDGET_EXHAUSTED`、`NO_PROGRESS` 等明确标为 `StopReason`，不再写成错误码。
- 在第三章导语后增加 `3.0 v1 实施边界`：深入实现治理；其余 Harness 维度保持最低可运行实现；明确推迟普通 turn 跨进程恢复、供应商重发、反馈迁移、清理对账、分布式 Demo 配额和通用接管。

提交：`Freeze v1 scope and stop mappings`

### 6. 同步过程证据和交接材料

- 在 `SPEC_PROCESS.md` 追加本轮 14 项分类、反例、最小修复和采纳理由；历史章节保持原样。
- 更新 `TASK_HANDOFF.md` 中已经失效的八值动作、重放、feedback 消费和三值 outcome 描述；下一任务仍为 3.6。
- 在实际审查完成后追加 `AGENT_LOG.md`，记录技能、提交、人工决定、审查结果和未完成事项。
- 不创建或填写课程 `PLAN.md`，不添加实现代码。

提交：`Record chapter three contract corrections`

## 验证与审查

- 当前合同不得再出现“传输恢复”“安全传输重放”“ProposeStopAction”或“八种 AgentAction”。
- `AgentTurnOutcome`、`TurnProcessingFailureRecord`、`UTF8_BOM`、`DEMO_SESSION_INVALIDATED` 和 `3.0 v1 实施边界` 必须出现在对应权威小节。
- 不得保留“用户明确放弃后清除”或把最终请求摘要绑定到 `DisclosureGrant` 的表述。
- 3.5.9 必须严格保持编号 1—21，第 6 项使用七种动作。
- `git diff --check origin/main...HEAD` 必须通过。
- 改动文件只允许为本计划文件、`SPEC.md`、`SPEC_PROCESS.md`、`TASK_HANDOFF.md` 和 `AGENT_LOG.md`。
- 凭据模式扫描不得发现真实凭据。
- 规范审查、文档质量审查和无背景范围冷审均须通过；日志提交只做窄范围真实性复核。

## 完成标准

- 10 个必须修改项全部关闭，11—14 项和 v1 边界已明确处理。
- 3.1—3.5 无直接矛盾、悬空生命周期或双重权威。
- 没有新增生产级状态机或超出课程周期的恢复机制。
- `SPEC.md`、`SPEC_PROCESS.md` 与 `TASK_HANDOFF.md` 对当前合同描述一致。
- 本轮只重新锁定 3.1—3.5；完整第三章仍需在 3.6—3.12 完成后全章交叉审查。
- 课程最终冷启动实现试验仍须等待完整 `SPEC.md` 与权威 `PLAN.md` 获批。
