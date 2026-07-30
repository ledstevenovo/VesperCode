# VesperCode v1 规格说明

> 状态：范围冻结候选稿。通过独立审查和课程冷启动试验前，不得进入实现。

## 0. 文档约定

本文与 AI4SE_Final_Project_通用要求.md、AI4SE_Final_Project_A_Coding_Agent_Harness(1).md 共同构成项目要求。冲突时课程原文优先。

规范词含义如下：

- **必须 / 不得**：v1 强制要求。
- **应当**：除非有记录在 AGENT_LOG.md 的明确理由，否则必须满足。
- **可以**：非强制实现选择。
- **未来工作**：不属于 v1，不得进入 v1 的实现任务或验收门禁。

每项规范合同只在一个章节定义。问题陈述和用户故事描述可观察结果，不重新定义内部协议。功能合同使用 FR-*，非功能要求使用 NFR-*，验收标准使用 AC-*。

# 1. 问题陈述与范围

## 1.1 用户问题

现有 Coding Agent 在本地仓库中工作时，用户通常难以确认：

1. Agent 是否只修改了允许的文件，还是越过工作区或接触了敏感路径；
2. 测试是否完整执行，还是通过删除测试、增加跳过或修改检查配置获得表面成功；
3. 一次批准是否只授权了用户实际看到的动作和 diff；
4. 本地允许读取的数据是否被自动发送给外部 LLM；
5. 最终写回的内容是否就是已验证、已批准的候选内容。

仅在提示词中要求模型谨慎不能确定性解决这些问题。模型输出、仓库文本和工具输出都可能不可靠，治理、检查、审批、成功判定和停止必须由 Harness 代码控制。

## 1.2 产品定位

**VesperCode 是一个面向 Windows 11 本地 Python 参考仓库的治理型 Coding Agent Harness 原型：它在隔离副本中修复已有失败测试，用 pytest、Ruff 和 Mypy 验证候选结果，并在用户批准精确 diff 后才写回原仓库。**

主要贡献是一条可离线测试的确定性治理管线：

    结构化动作
    → 路径与验收契约校验
    → ALLOW / ASK / DENY
    → 精确上下文的一次性批准
    → 不可变 ValidationManifestV1 下的正式验证
    → 用户批准精确 diff
    → 受控写回与写后核对

项目定位是课程型、安全研究型参考 Harness，不承诺兼容普通 Python 生态中的任意仓库，也不以生产级崩溃一致控制平面为目标。

## 1.3 目标用户

目标用户是希望观察和评估治理机制的课程评审者、安全研究者，以及愿意使用受支持参考画像的 Windows 本地 Python 开发者。

用户需要理解 Git、pytest 和 diff 的基本概念，但不需要理解内部状态表或数据库结构。

## 1.4 v1 支持矩阵

| 维度 | v1 支持 | v1 不支持 |
|---|---|---|
| 宿主 | Windows 11 x64，Docker Desktop Linux 容器模式 | macOS、Linux 宿主、Windows 容器 |
| Harness 运行时 | Python >=3.12,<3.13 | 其他 Python 主版本 |
| 目标项目 | 唯一 `python-reference-v1` 画像：Python >=3.12,<3.13、`pyproject.toml`、`uv.lock`、`src/`、`tests/`，依赖已在绑定镜像中准备 | 扁平包布局、其他依赖集合、自动安装依赖、运行时依赖 Git 历史或未跟踪文件 |
| 缺陷输入 | 已存在且可稳定复现的 pytest 失败测试 | 自然语言缺陷自动生成测试 |
| 检查 | pytest 8.x、Ruff、Mypy；命令由适配器生成 | 任意 shell 命令、动态下载工具 |
| 补丁 | UTF-8/UTF-8 BOM 普通文本文件的创建和修改 | 删除、重命名、二进制、符号链接、reparse point、文件模式变更 |
| Git | 有有效 HEAD 的干净普通仓库 | submodule、LFS、稀疏检出、filter、未合并 index、脏工作区 |
| 执行 | 预构建、无网络的 Docker profile | 宿主执行、运行中构建镜像或安装依赖 |
| LLM | 可注入 Mock LLM；一个 OpenAI 单轮适配器 | 高层 Agent 框架、供应商请求重发与跨崩溃恢复 |
| WebUI | 本地 WebUI；公网 Mock Demo | 公网读取本地仓库、上传任意仓库、公网真实凭据 |

发布时必须在 lock file 和 README 的兼容性表中记录通过 CI 的精确依赖版本、Docker 镜像摘要和 Windows/Docker Desktop 测试环境。超出画像的输入以明确的不支持结果停止，不得静默降级。

## 1.5 v1 目标

- 自行实现顺序 Agent 主循环和可注入 LLM 抽象。
- 提供受路径围栏约束的 list、read、search、apply patch、run check 和 propose completion 动作。
- 用确定性代码实现 ALLOW / ASK / DENY、一次性批准和硬拒绝。
- 用 ValidationManifestV1 保护测试、检查配置和正式验证条件。
- 将 pytest、Ruff、Mypy 结果转换为结构化反馈并驱动下一轮动作。
- 在用户审查精确 diff 后写回干净权威工作区，并核对写后结果。
- 提供安全凭据管理、本地 WebUI、离线 Mock 测试和可访问的公网 Mock Demo。

## 1.6 非目标

- 生产级通用 Coding Agent 或任意仓库兼容。
- 自然语言缺陷生成复现测试、ValidationManifestV2 或测试生成审批。
- 多 Agent、并行 turn、分布式任务、供应商调用对账或自动重发。
- 普通 Agent turn 的跨进程恢复。
- 永久 quarantine allocator、通用 reconciliation 或多层 cleanup 状态机。
- 自动 commit、push、PR、依赖安装、镜像构建或对外发布。
- 识别所有秘密格式、消除所有提示注入或对恶意宿主管理员提供隔离。

# 2. 用户故事

## 2.1 US-01 配置并安全启动运行

作为受支持仓库的开发者，我希望在运行前看到冻结的配置和兼容性检查，以便在任何模型调用、项目执行或持久修改前发现不支持或不安全的条件。

验收结果：

- 未知配置字段、无效值和试图放宽硬 DENY 的配置被拒绝。
- 用户能看到工作区、目标测试、执行 profile、模型模式和预算摘要。
- 脏仓库、不支持的 Git 策略、危险文件对象、缺失 Docker profile 或凭据会在首次模型调用前停止。
- 被拒绝的启动不安装依赖、不构建镜像、不修改仓库。

## 2.2 US-02 安全管理真实 LLM 凭据

作为使用真实 LLM 的开发者，我希望安全录入、查看状态、更新和清除 API Key，以便不把凭据写入仓库、命令历史、日志或公网 Demo。

验收结果：

- 首次真实调用前提供隐藏输入。
- 状态查询只返回已配置/未配置和供应商标识，不返回秘密。
- 更新和清除给出明确成功或失败结果。
- 清除后新的真实调用必须停止，直到重新配置。

## 2.3 US-03 修复已有稳定失败

作为已有失败测试的开发者，我希望 Agent 在隔离副本中根据客观检查反馈迭代修复，以便获得不削弱既有验收条件的候选 diff。

验收结果：

- 所有目标测试必须被收集；每个目标都必须连续两次产生相同稳定失败，并在最终正式验证中转为 PASS。
- 非目标测试、Ruff 和 Mypy 必须满足严格基线。
- 候选补丁不能修改受保护测试或检查配置。
- 检查失败形成结构化反馈，Mock LLM 可据此在下一轮改变动作。
- 只有完整正式验证通过的候选才能进入最终审查。

## 2.4 US-04 控制外部数据披露

作为使用真实 LLM 的开发者，我希望在每次项目数据外发前知道供应商、模型、来源类别和体量，以便本地读取权限不会被自动解释为外发权限。

验收结果：

- 未授权请求不得调用真实适配器。
- 授权精确绑定运行、供应商、模型、来源类别、请求摘要、字节数和有效期。
- 供应商、模型、来源、摘要、预算或有效期变化使授权失效。
- 审计只保存摘要和元数据，不保存完整请求或凭据。

## 2.5 US-05 依赖确定性护栏和一次性审批

作为监督 Agent 的用户，我希望硬拒绝动作始终被阻止，而可批准动作只执行一次，以便权限不能由模型、仓库文本或旧批准扩大。

验收结果：

- DENY 不可被模型输出、配置或任何批准覆盖。
- ASK 展示完整动作摘要、理由、绑定上下文和有效期。
- 拒绝、过期、上下文变化或重复消费均不执行动作。
- 批准只被精确绑定的动作原子消费一次。

## 2.6 US-06 审查并持久化已验证 diff

作为开发者，我希望在原仓库发生修改前查看精确 diff 和验证证据，以便写回内容与我批准的内容一致。

验收结果：

- 用户拒绝时权威工作区保持不变。
- 候选、Manifest、验证证据或工作区前映像变化使批准失效。
- 写回不自动执行 git add 或 commit。
- 写后核对失败不得报告成功。

## 2.7 US-07 检查和清除仓库记忆

作为重复维护同一参考仓库的用户，我希望查看、使用和清除仓库级记忆，以便获得有限连续性而不让旧信息成为权限来源。

验收结果：

- 记忆按规范化工作区身份隔离。
- 用户能查看来源、摘要和更新时间，并能清除。
- 记忆不保存完整源码、完整工具输出、凭据或权限。
- 当前仓库和检查证据始终优先于记忆。

## 2.8 US-08 理解状态和审计证据

作为监督运行的用户，我希望看到准备中、运行中、等待决定、恢复阻塞和已结束状态，以便区分模型建议、检查结果和正式成功。

验收结果：

- CREATED 显示为准备中，RUNNING 显示为运行中。
- 测试失败、错误、超时和未运行不得显示为通过。
- LLM 的 completion 建议不能直接触发 SUCCEEDED。
- 停止和成功均显示对应的结构化证据。

## 2.9 US-09 运行公网 Mock Demo

作为评审者，我希望无需仓库或真实凭据即可运行固定 Demo，以便重复观察危险动作拦截、失败反馈修正和 Manifest 防篡改。

验收结果：

- Demo 只使用内置场景、Mock LLM 和模拟执行器。
- 页面持续显示模拟运行，不得展示为正式修复成功。
- 相同场景版本、输入和用户选择产生相同关键状态与动作序列。
- Demo 不注册本地文件、真实凭据、Docker 或真实 LLM 能力。

## 2.10 INVEST 检查

| 故事 | I / N / V / E / S / T 结论 |
|---|---|
| US-01 | 独立验证准入；交互可协商；价值、边界和拒绝样例明确 |
| US-02 | 独立验证凭据生命周期；存储方案固定，界面细节可协商 |
| US-03 | 以预置失败 fixture 独立验收；实现任务在 PLAN 中继续拆分 |
| US-04 | 独立验证单次披露；真实网络以 stub adapter 测试 |
| US-05 | 直接构造动作即可离线验证决策、批准和拒绝 |
| US-06 | 以固定候选和工作区前映像独立验证持久化结果 |
| US-07 | 以临时数据库独立验证隔离、读取和清除 |
| US-08 | 以预置运行记录独立验证状态和证据展示 |
| US-09 | 以内置脚本独立、确定性、可重复验收 |

# 3. 领域与机制设计

## 3.1 Coding 领域的四类机制

| 类别 | v1 设计 | 确定性代码机制 |
|---|---|---|
| 动作/工具 | list、read、search、apply patch、run check、propose completion | 严格动作 Schema、工具注册表、路径解析器、受控适配器 |
| 客观反馈 | pytest、Ruff、Mypy、Schema/策略拒绝、正式验证 | 结果解析器、失败分类器、FeedbackRecord 和下一轮投影 |
| 危险动作 | 越界路径、敏感路径、验收篡改、任意命令、外发、权威写回 | PolicyEngine、ALLOW/ASK/DENY、一次性审批和披露授权 |
| 记忆 | 项目约定、用户确认的决策、上次运行摘要 | 仓库隔离存储、有限检索、来源标注、用户清除 |

## 3.2 六个 Harness 维度

| 维度 | v1 最低实现 | 深度 |
|---|---|---|
| 决策 | 顺序主循环、上下文装配、一次 LLM 调用、动作解析、停止谓词 | 最低闭环 |
| 工具 | 六种结构化动作和统一分发 | 最低闭环 |
| 记忆 | SQLite 仓库级摘要存取、检查和清除 | 最低闭环 |
| 治理 | 路径围栏、Manifest、ALLOW/ASK/DENY、一次性批准、受控写回 | **主要贡献** |
| 反馈 | 三类检查结果、拒绝原因和下一轮结构化反馈 | 最低闭环 |
| 配置 | 严格 Schema、冻结快照、预算和不可放宽硬规则 | 最低闭环 |

## 3.3 主贡献的评价问题

1. 构造任意模型动作时，模型能否越过工作区、敏感路径或受保护工件？
2. 用户批准的动作或 diff 是否就是最终执行对象，且批准能否复用？
3. 模型能否通过修改测试、配置或成功条件获得表面成功？

三项都必须在替换真实 LLM 为 Mock 后由离线单元测试回答。

## 3.4 信任边界

- **可信控制面：** 主循环、配置解析、路径解析、策略、审批、Manifest、检查解析、成功和停止判定。
- **不可信输入：** 用户仓库、代码注释、测试数据、工具输出、模型输出、记忆正文和 WebUI 客户端请求。
- **受限执行面：** 无网络 Docker 容器，只挂载一次性执行副本。
- **外部边界：** 真实 LLM 供应商；本地读取授权不等于披露授权。
- **权威工作区：** 只允许持久化模块在最终审批后写入。

# 4. 功能规约

## 4.1 FR-ADM：配置、创建与准入

**接口与输入：**

    RunRequest {
      workspace_path
      target_test_ids[]
      llm_mode: MOCK | OPENAI
      docker_profile_id
      configurable_limits
    }

    ValidateRunRequest(RunRequest)
      -> ValidatedRunRequest | CONFIG_INVALID

    CreateRun(ValidatedRunRequest)
      -> Run(status=CREATED, config_snapshot_id)

    StartRun(run_id)
      -> AdmissionResult

**行为：**

1. `ValidateRunRequest` 使用拒绝未知字段的版本化 Schema，只校验字段类型、必填值、目标测试 ID 语法和可配置上限；失败时不分配 `run_id`、不创建审计事件。
2. `CreateRun` 将用户值与内建硬上限合并；用户只能收紧，不能放宽硬规则。随后冻结不含秘密的 `RunConfigSnapshot`，创建 `CREATED` Run 和首个状态审计事件。
3. `StartRun` 原子地把 `CREATED` 转为 `RUNNING(PREFLIGHT)`；其他状态调用返回 `RUN_NOT_STARTABLE`，不得重复准入。
4. PREFLIGHT 规范化工作区身份并取得 §4.6 定义的跨进程排他锁。
5. PREFLIGHT 验证有效 HEAD、干净 index/工作区、受支持 Git 策略、文件对象和 `PythonProjectProfileV1`。
6. PREFLIGHT 验证 Docker profile 已预构建且镜像摘要匹配；真实模式只检查凭据状态，不读取或记录秘密。
7. 全部通过时进入 `RUNNING(BASELINE)`；任一拒绝形成带稳定原因和审计证据的 `STOPPED`，释放不再需要的锁。

**输出：**

- `ValidateRunRequest` 失败：`CONFIG_INVALID`，不存在 Run。
- `CreateRun` 成功：`CREATED(run_id, config_snapshot_id)`。
- `StartRun` 成功：`ACCEPTED(run_id, BASELINE)`；准入拒绝：`STOPPED(run_id, error)`。

**边界和错误：**

- 输入无效：CONFIG_INVALID。
- 工作区不干净：WORKTREE_DIRTY。
- 仓库或项目画像不支持：UNSUPPORTED_REPOSITORY / UNSUPPORTED_PROJECT。
- Docker profile 不可用：EXECUTION_PROFILE_UNAVAILABLE。
- 真实模式缺少凭据：CREDENTIAL_MISSING。
- 同一工作区存在未解决持久化事务：WORKSPACE_RECOVERY_REQUIRED；新 Run 进入 STOPPED，原事务保持 RECOVERY_REQUIRED。
- 任一拒绝发生在 LLM 调用、项目执行和工作区修改前。

**确定性测试：** 覆盖无效请求不创建 Run、有效请求产生可见 `CREATED`、重复 Start 被拒绝，以及每种 PREFLIGHT 拒绝均进入可审计 `STOPPED`；断言 LLM 和执行器调用次数均为零。

## 4.2 FR-LOOP：主循环、动作和停止

**接口：**

    LLMAdapter.generate(ContextProjection) -> ModelResponse
    ActionParser.parse(ModelResponse) -> AgentAction | ParseError
    ToolDispatcher.dispatch(AgentAction, RunContext) -> ActionResult
    StopEvaluator.evaluate(RunState, Evidence)
      -> Continue | Validate | Stop(stop_reason)

AgentAction 是封闭联合：

    ListFilesAction
    | ReadFileAction
    | SearchTextAction
    | ApplyCandidatePatchAction
    | RunCheckAction
    | ProposeCompletionAction

所有动作都是拒绝未知字段的版本化 JSON 对象，共同字段为 `schema_version: 1` 和下表中的固定 `type`；字符串使用 UTF-8，路径使用 §4.3 的规范相对路径。

| 动作与 type | 必填字段 | 封闭语义与输出上限 |
|---|---|---|
| ListFilesAction / `list_files` | `path`、`recursive` | 最多 200 项、32 KiB；按规范路径字节序排序，超限返回截断标志而非静默遗漏 |
| ReadFileAction / `read_file` | `path`、`start_line`、`end_line` | 1-based 闭区间；最多 400 行、64 KiB；范围无效或超过上限时拒绝，不自动改写范围 |
| SearchTextAction / `search_text` | `path`、`query`、`case_sensitive` | v1 仅支持非空字面量；最多 100 个匹配、32 KiB；按 path、line、column 排序 |
| ApplyCandidatePatchAction / `apply_candidate_patch` | `base_candidate_digest`、`unified_diff` | 只对精确匹配的当前候选应用 §4.3 严格补丁；陈旧摘要返回 `CANDIDATE_STALE` |
| RunCheckAction / `run_check` | `check_plan_id` | 只能引用控制面已发布的封闭 ID；Agent loop 中唯一允许值为 `TARGET_TESTS`，不得包含 executable、argv 或命令文本 |
| ProposeCompletionAction / `propose_completion` | `candidate_digest` | 摘要必须等于当前候选；只请求进入正式验证，不携带成功声明 |

Schema 类型错误、未知字段、缺失字段、非法枚举和超限输入统一在策略与工具执行前返回 `ACTION_SCHEMA_INVALID`。

RunStatus 是封闭联合：

    CREATED | RUNNING | WAITING_USER | RECOVERY_REQUIRED | SUCCEEDED | STOPPED

RUNNING 的 phase 只允许 PREFLIGHT、BASELINE、AGENT_LOOP、FORMAL_VALIDATION、PERSISTENCE。SUCCEEDED 和 STOPPED 是终态；RECOVERY_REQUIRED 只属于持久化不确定状态。

**行为：**

1. 同一运行任一时刻最多一个活动 AgentTurn。
2. 每轮从当前候选、有限记忆、未消费反馈和预算生成有界 ContextProjection。
3. 每轮恰好调用一次 LLM，随后严格解析一个动作。
4. 动作先经 Schema、路径、阶段和策略校验，再分发。
5. 结果发布为结构化 ActionResult；需要继续时，下一 turn 原子绑定并消费本轮选中的 feedback_refs。
6. ProposeCompletionAction 只请求进入正式验证，不能声明成功。
7. StopEvaluator 只可以因轮次/调用/时长预算、连续无效输出上限或不可恢复错误产生普通 `STOPPED`，或请求进入正式验证；它不能发布 `SUCCEEDED`。

**ContextProjection：**

最终投影使用 UTF-8 canonical JSON（对象键按字节序、无无意义空白、整数十进制、数组保持规范顺序），总上限 64 KiB。来源和类别上限固定为：

1. 系统合同、动作 Schema、冻结配置和 Manifest 绑定：16 KiB；属于强制块，超限时以 `CONTEXT_BUDGET_EXCEEDED` 停止，不得裁掉安全合同。
2. 当前候选摘要、规范化净 diff 和目标测试：16 KiB；路径按字节序，diff 按 §4.3 规范顺序。
3. 未消费反馈：16 KiB；先按严重度，再按产生序号，最近失败必须保留。
4. 记忆：8 KiB；使用 FR-MEM 的确定性选择顺序。
5. 有界工具观察：8 KiB；按 turn、动作和结果序号排序。

需要裁剪时依次删除最旧工具观察、最低优先级记忆、最旧非当前反馈、候选正文片段；run/config/Manifest 摘要、当前候选摘要、当前错误和动作 Schema 永不裁剪。`context_digest` 和真实 LLM 的 `request_digest` 都基于裁剪后的最终规范对象计算。

**生命周期：**

- CREATED 只能进入 RUNNING(PREFLIGHT) 或 STOPPED。
- RUNNING 可以推进到下一 phase、进入 WAITING_USER 或 STOPPED。
- WAITING_USER 在决定被精确消费后回到来源 phase 的新执行入口，拒绝或超时进入 STOPPED。
- RUNNING(PERSISTENCE) 可以进入 SUCCEEDED、STOPPED 或 RECOVERY_REQUIRED。
- RECOVERY_REQUIRED 只能由 FR-PERSIST 的恢复结果进入 SUCCEEDED、STOPPED 或保持不变。
- 非持久化阶段进程重启进入 STOPPED；v1 不提供用户取消接口或普通 Agent turn 恢复。

**状态发布权威：**

| 结果 | 唯一发布者 |
|---|---|
| Continue、进入 FORMAL_VALIDATION、普通 STOPPED | StopEvaluator / 当前 phase 协调器 |
| WAITING_USER 及其返回/拒绝/过期 | FR-GOV |
| RECOVERY_REQUIRED | PersistenceCoordinator |
| SUCCEEDED | PersistenceCoordinator 在正式验证、批准消费、精确写回和写后核对全部完成后发布 |

模型动作、LLM 文字、检查退出码、WebUI 和 StopEvaluator 均不得直接发布 `SUCCEEDED`。

**输出：** 每轮形成一个 AgentTurn outcome 和 ActionResult；运行最终形成 SUCCEEDED 或带稳定原因的 STOPPED，持久化证据不确定时形成 RECOVERY_REQUIRED。

**错误与继续策略：**

- 模型输出无效：生成结构化反馈；连续两次无效则 MODEL_OUTPUT_INVALID_LIMIT 停止。
- 动作被拒绝：生成策略反馈；硬 DENY 不进入审批。
- LLM 调用失败：LLM_CALL_FAILED 并停止；v1 不自动重试。
- 响应后控制面失败：INTERNAL_ERROR 并停止。
- 非持久化阶段进程重启：旧运行停止为 PROCESS_RESTARTED_DURING_RUN，不得恢复或重发。

**确定性测试：** 脚本化 Mock LLM 依次返回失败动作、修正动作和 completion；断言顺序、反馈和停止完全可重复。

## 4.3 FR-WS：快照、路径和候选补丁

**输入：** 已通过准入的 Git 工作区和 ApplyCandidatePatchAction。

**行为：**

1. 从冻结 HEAD 和已验证工作区字节建立不可变 SnapshotTree。
2. 每个检查使用由 SnapshotTree + CandidateDiff 物化的全新 UUID 执行副本；副本不含 .git。
3. 所有 Agent 路径必须是使用 / 的相对路径；拒绝绝对路径、..、盘符、UNC、ADS、设备名、符号链接和 reparse point。
4. 文件访问在解析前后都验证最终目标仍位于授权根。
5. CandidateDiff 只允许创建或修改 UTF-8/UTF-8 BOM 普通文本文件，并保持既有 BOM 与换行风格。
6. 新候选从不可变父候选派生；不得原地修改权威快照。
7. 补丁格式固定为 UTF-8 严格 unified diff：既有文件使用 `--- a/path`、`+++ b/path`，新文件使用 `--- /dev/null`、`+++ b/path`；禁止时间戳、rename/mode/delete header、二进制块和同一文件重复 header。
8. hunk 的路径、旧行号、上下文和删除行必须与 `base_candidate_digest` 指向的字节精确匹配；禁止 fuzzy apply、自动 offset 和上下文猜测。
9. 每次派生后重新计算当前 CandidateTree 相对 SnapshotTree 的规范化净差异；历史补丁抵消后不进入最终差异。
10. 新文件若命中准入时冻结的 Git ignore 规则，返回 `IGNORED_PATH`。

**输出：** 不可变 SnapshotTree、CandidateRevision 和 CandidateDiff，或一个无候选副作用的稳定错误。`FinalDiff` 是 SnapshotTree 到最终 CandidateTree 的规范化净差异：文件按规范路径排序，header/hunk 使用 LF，文件正文仍保持原 BOM 和换行；摘要对该规范 UTF-8 表示计算，而不是拼接历史 patch。

**硬限制：**

- 当前候选累计净差异最多 3 个修改文件。
- 当前候选规范化净 diff 不超过 256 KiB。
- 单文件不超过 128 KiB。
- 不支持删除、重命名、二进制修改或模式变化。

**错误：** PATH_INVALID、PATH_OUTSIDE_WORKSPACE、SENSITIVE_PATH、IGNORED_PATH、CANDIDATE_STALE、UNSUPPORTED_PATCH_OPERATION、PATCH_CONTEXT_MISMATCH、PATCH_LIMIT_EXCEEDED、TREE_INTEGRITY_FAILED。

**清理：** 执行副本删除前验证 UUID 根身份且不跟随链接。删除失败时记录精确残留路径并永不复用该名称；当前运行停止。v1 不实现永久 allocator 或跨进程清理状态机。

**确定性测试：** 使用临时目录构造绝对路径、父目录、ADS、设备名、symlink/reparse、敏感路径和超限补丁；断言全部在文件访问或副本修改前被稳定拒绝。

## 4.4 FR-GOV：策略、审批和披露

**输入：** 规范化 AgentAction、当前运行/候选/Manifest/配置绑定、可选用户决定，以及真实请求的供应商、模型、来源和规范摘要。

### 4.4.1 动作策略

PolicyEngine.evaluate(action, context) -> ALLOW | ASK | DENY。

| 动作 | 默认决定 |
|---|---|
| 受限 list/read/search | ALLOW |
| 候选副本内受支持补丁 | ALLOW |
| 适配器生成的检查动作 | ALLOW |
| 最终权威写回 | ASK |
| 越界、敏感路径、任意命令、验收篡改、控制面修改 | DENY |

硬 DENY 列表由代码定义。配置、提示、仓库文本和用户批准都不能改变 DENY。

### 4.4.2 本地一次性 WritebackApproval

WritebackApproval 只授权最终权威写回，必须绑定：

- run_id、动作类型和规范动作摘要；
- 当前候选摘要、Manifest 摘要和适用验证证据；
- 工作区前映像摘要；
- 配置、策略和执行 profile 摘要；
- 创建时间、到期时间和状态。

状态为 PENDING | REJECTED | EXPIRED | CONSUMED。用户拒绝或超时分别使 PENDING 进入 REJECTED 或 EXPIRED；只有当前 PENDING 且全部绑定仍匹配的批准请求可以在动作执行前通过一次原子更新变为 CONSUMED。消费失败不得执行动作。

### 4.4.3 外部披露

发送每一个真实 LLM 请求前，控制面先生成裁剪完成的最终规范请求和 `DisclosureRequest`，随后把 Run 从来源 phase 转为 `WAITING_USER`。UI 必须展示并检查：

- 当前运行和供应商/模型；
- 来源文件及数据类别；
- 确定性序列化后的请求摘要和字节数；
- 当前累计披露预算和有效期。

用户拒绝或超时使 Run 进入带稳定原因的 `STOPPED`，不得调用适配器。用户确认后创建只绑定该请求的 `DisclosureAuthorizationRecord(status=AUTHORIZED)`；记录包含 run、来源 phase、provider、model、source categories、最终 request_digest、精确字节数、累计预算、创建/到期时间，不保存正文或凭据。

控制面必须在真实适配器调用前把当前 AUTHORIZED 记录原子消费为 CONSUMED，并绑定唯一 `llm_call_attempt_id`；消费失败不得调用。调用结束后由独立 `LLMCallResult` 表示成功或失败，授权记录不证明供应商已收到请求。v1 不重试真实调用，因此同一记录永不授权第二次尝试。调用结果提交后，Run 回到来源 phase 的新执行入口。

每个不同 `request_digest` 都需要新的用户确认；v1 不提供覆盖多个请求的运行级范围授权。DisclosureAuthorizationRecord 与 WritebackApproval 是不同类型：本地写回批准不能授权外发，披露确认不能授权本地 ASK 动作，二者都不能覆盖 DENY。FR-GOV 是两类授权状态转换的唯一所有者；FR-PERSIST 只能提交待批准的写回对象并消费已验证的 WritebackApproval。

Mock 路线经过相同上下文裁剪、Schema、策略和预算逻辑，但不创建真实披露授权、不读取凭据、不联网。

**输出：** PolicyDecision、WritebackApproval 状态变化、DisclosureRequest、DisclosureAuthorizationRecord、LLMCallResult 或稳定拒绝。

**错误：** ACTION_SCHEMA_INVALID、ACTION_DENIED、WRITEBACK_APPROVAL_REJECTED、WRITEBACK_APPROVAL_EXPIRED、WRITEBACK_APPROVAL_STALE、WRITEBACK_APPROVAL_ALREADY_CONSUMED、DISCLOSURE_NOT_AUTHORIZED、DISCLOSURE_BUDGET_EXCEEDED。

**确定性测试：** 直接构造 ALLOW、ASK、DENY 动作及批准竞态；断言硬拒绝不可覆盖，只有一个精确批准消费胜出，未授权披露时真实适配器调用次数为零。

## 4.5 FR-VAL：Python 适配器、基线、Manifest 和反馈

**唯一支持画像 `PythonProjectProfileV1`：**

| 维度 | 冻结规则 |
|---|---|
| profile | `profile_id = python-reference-v1`；发布注册表只允许一个 profile，并绑定适配器版本、镜像摘要、工具版本和一个允许的 `uv.lock` 摘要 |
| 布局 | 仓库根必须有 `pyproject.toml`、`uv.lock`、`src/`、`tests/`；源码根固定为 `src/`，测试根固定为 `tests/` |
| 配置 | `pyproject.toml` 必须含 `[project]`、`[tool.ruff]` 和 `[tool.mypy]`；不得同时存在会产生第二权威来源的 `pytest.ini`、`setup.cfg`、`tox.ini`、`mypy.ini`、`ruff.toml` 或 `.ruff.toml` |
| pytest | 设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`；除 pytest 内建插件、受保护的仓库 `conftest.py` 和 Harness 自有 `vespercode.pytest_reporter` 外不允许其他插件。reporter 输出 `/tmp/vesper-pytest-events.jsonl` 作为权威机器证据；JUnit XML 只可作为展示工件 |
| 环境 | 项目可见白名单固定为 `PYTHONHASHSEED=0`、`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`TZ=UTC`、`LC_ALL=C.UTF-8`；容器内部 PATH/HOME/TMP 由 profile 固定并纳入环境摘要 |
| 依赖 | 运行时不得联网或安装；`uv.lock` 摘要、预装依赖集合和镜像摘要必须与发布注册表完全匹配 |

`vespercode.pytest_reporter` 是控制面随 wheel 交付并通过 `-p vespercode.pytest_reporter` 显式加载的可信插件，不从目标仓库导入。profile 和 Manifest 必须绑定 reporter 的 schema_version、包版本和源码摘要。它按单调 sequence 写 canonical JSON Lines，封闭事件至少包括：

- `collection_complete`：有序完整 node ID 集合；
- `deselected`：被取消选择的完整 node ID；
- `test_phase`：node ID、setup/call/teardown、outcome、`wasxfail` 和有界错误摘要；
- `collection_error`、`session_error`、`environment_error`；
- `session_end`：pytest exit code、事件数量和前序事件摘要。

缺少结束事件、sequence 断裂、重复/未知事件、reporter 版本或摘要不匹配、node 集合与计划不符时统一返回 `REPORTER_INVALID`。成功、基线和反馈分类只能读取该事件流及控制面已知的 Ruff/Mypy 结构化结果，不得用终端文本补足 XPASS、deselect、NOT_RUN 或错误状态。

**保护工件表：** `tests/**`、任意层级 `conftest.py`、`pyproject.toml`、`uv.lock`、`.gitignore`、`.gitattributes`、`sitecustomize.py` 和 `usercustomize.py`。候选创建或修改任一保护工件均硬 DENY。

**敏感路径表：** `.env`、`.env.*`、`.pypirc`、`.npmrc`、`*.pem`、`*.key`、`id_rsa`、`id_rsa.*`。任一模式命中 tracked 文件时 PREFLIGHT 直接返回 `SENSITIVE_PATH`，不得把该文件放入 SnapshotTree 或容器。任一 tracked 普通文件的 link count 大于 1 时返回 `UNSUPPORTED_HARD_LINK`。

**画像资源上限：** tracked 文件最多 1000 个、tracked 原始字节合计最多 32 MiB、单个物化执行副本最多 64 MiB。每个容器限制为 1 CPU、1 GiB 内存、128 PID、256 MiB tmpfs；每项检查的 stdout/stderr 合计最多 1 MiB，超限为 `CHECK_OUTPUT_LIMIT_EXCEEDED`。

**适配器边界：**

    ProjectAdapter {
      detect(snapshot) -> ProjectProfile
      build_baseline_plan(profile, target_test_ids) -> CheckPlan
      build_validation_plan(manifest, candidate) -> CheckPlan
      parse_check_result(raw_result) -> CheckResult
      protected_artifacts(profile) -> ProtectedArtifactSet
    }

核心只理解 CheckAction、CheckResult、TestIdentity、ProtectedArtifact 和 ValidationManifestV1。pytest、Ruff、Mypy 的命令和解析属于 PythonProjectAdapterV1。

**输入：** SnapshotTree、目标测试 ID、当前候选、受支持项目画像和冻结执行环境。

**基线：**

1. 在两个独立只读副本中各执行一次 `pytest --collect-only`；完整 node ID 集合必须相同。
2. 在第一个全新副本执行一次完整 pytest，记录全部逐测试结果和目标的第一次失败分类/指纹。
3. 在第二个全新副本只运行目标集合，记录第二次结果；每个目标都必须存在，并在两次运行中产生相同失败分类和失败指纹。任一目标 PASS、未运行、不稳定或缺失都拒绝整个 baseline。
4. 完整 pytest 中的非目标测试必须全部 PASS；不得出现 skip、xfail、xpass、deselect、NOT_RUN、收集错误或环境错误。
5. 在各自全新副本运行 Ruff 和 Mypy，两者必须 PASS。
6. 每次运行后验证 SnapshotTree、保护工件和环境摘要未变化；全部成立后创建不可变 ValidationManifestV1。

Manifest 至少绑定：

- 完整 pytest node ID 集合和目标集合；
- 基线逐测试状态及目标失败指纹；
- 受保护测试、pytest/Ruff/Mypy 配置和依赖锁文件摘要；
- 检查计划、Python/工具版本、容器镜像摘要和环境白名单；
- `vespercode.pytest_reporter` 的 schema_version、包版本、源码摘要和权威事件流摘要；
- 仓库快照摘要和适配器版本。

**候选检查与反馈：**

- 快速反馈可以只运行受影响目标，但不能产生成功。
- CheckResult.status = PASS | FAIL | ERROR | TIMEOUT | NOT_RUN。
- 反馈只从结构化结果和稳定错误码生成，不直接把任意 stdout/stderr 当作权威结论。
- 下一 turn 最多接收 10 条反馈、32 KiB，总是包含最近失败的分类、位置和有界摘要。
- 修改 Manifest 保护工件的候选直接 DENY，不运行检查。
- 每项检查从 SnapshotTree + 当前累计净 diff 重新物化 CandidateTree，并以只读方式挂载到全新无网络、非 root 容器；容器根文件系统同样只读，不挂载 Docker socket。
- `/tmp`、pytest 临时目录和 Mypy cache 使用有界 tmpfs；设置 `PYTHONDONTWRITEBYTECODE=1`，pytest 禁用 cacheprovider，Ruff 使用 `--no-cache`。要求在项目树写运行时文件的项目不属于 v1 画像。
- 检查结束后重新计算物化树、保护工件和环境摘要；任何非允许变化均使结果失败关闭。

**输出：** BaselineResult、不可变 ValidationManifestV1、CheckResult 和有界 FeedbackRecord。

**错误：** TARGET_NOT_FOUND、TARGET_NOT_REPRODUCED、TARGET_UNSTABLE、BASELINE_BLOCKED、UNSUPPORTED_HARD_LINK、RESOURCE_LIMIT_EXCEEDED、REPORTER_INVALID、CHECK_ERROR、CHECK_TIMEOUT、CHECK_OUTPUT_LIMIT_EXCEEDED、PROTECTED_ARTIFACT_CHANGED、VALIDATION_ENVIRONMENT_CHANGED。

**确定性测试：** 使用 Harness reporter 固定事件夹具分别覆盖 PASS、FAIL、skip、xfail、xpass、deselect、NOT_RUN、collection/session/environment error、sequence/结束事件损坏、稳定失败、节点漂移、保护工件变化和正式全通过；解析测试不读取终端文本、不访问网络或真实 Docker。

## 4.6 FR-PERSIST：正式验证、持久化和最小恢复

**输入：** FinalDiff、CandidateRevision、ValidationManifestV1、完整检查计划、工作区前映像和最终持久化 WritebackApproval。

**正式验证：**

1. 从原始 SnapshotTree 和准备持久化的精确 FinalDiff 物化 CandidateTree；验证 tree digest 后以只读方式挂载。
2. 完整 pytest、Ruff 和 Mypy 分别使用全新容器与全新物化副本，执行约束与 §4.5 相同。
3. 最终 pytest 收集集合必须与 Manifest 完全相同；每个 node ID 必须实际执行且为 PASS，不得有 skip、xfail、xpass、deselect、NOT_RUN、收集错误或环境错误。
4. 每个目标必须从 Manifest 记录的允许稳定失败状态变为最终 PASS；所有非目标测试继续 PASS；Ruff 和 Mypy 均为 PASS。
5. 每项检查后 CandidateTree、保护工件、检查计划、镜像、工具版本和环境摘要必须与 Manifest 绑定一致，且项目树没有任何非允许变化。
6. 上述谓词全部成立才创建 VerifiedCandidate；pytest 退出码 0 本身不构成成功证据。

**持久化：**

1. WebUI 展示精确 diff、Manifest 摘要和正式验证证据。
2. 用户批准生成绑定完整上下文的一次性 WritebackApproval。
3. 消费前重新验证权威工作区仍等于原始前映像。
4. 创建本地事务日志和需要的前映像备份。
5. 使用同目录临时文件、flush 和原子替换逐文件写入。
6. 写后逐文件比较期望摘要，并重验未涉及的 tracked 文件未变化。
7. 全部匹配后标记提交完成并进入 SUCCEEDED。

**跨进程锁：**

- 锁键是规范化 `workspace_identity` 的 SHA-256；锁文件固定为 `%LOCALAPPDATA%\VesperCode\locks\<workspace_sha256>.lock`。
- 本地实现保持文件句柄，并用 Python `msvcrt.locking` 对第一个字节执行非阻塞跨进程排他锁；同一进程内数据库状态不能替代该锁。
- 正式 Run 从 PREFLIGHT 到确定终态或持久化证据落盘一直持锁。进入 RECOVERY_REQUIRED 前必须先持久化事务门，然后释放旧进程的 OS 锁；事务门阻止新 Run，只有 recovery 命令可以为该工作区重新取得锁。

**最小恢复接口：**

    vespercode recover --workspace <path>
    vespercode recover --workspace <path> --apply

不带 `--apply` 时只读取事务日志、备份和当前字节，展示逐文件前映像/后映像匹配状态、将执行的确定性动作及预计结果，不修改工作区。`--apply` 在取得同一跨进程锁后只允许：

- `COMMITTED`：全部后映像匹配，完成写后核对和提交标记，生命周期进入 SUCCEEDED。
- `ROLLED_BACK`：每个已写文件都匹配已知前/后映像且备份完整，原子恢复全部前映像并核对，生命周期进入 STOPPED。
- `UNRESOLVED`：存在未知字节、缺失备份或矛盾证据；不写任何文件，保持 RECOVERY_REQUIRED。

不存在 `--ignore` 或强制成功选项。只有 COMMITTED 可以删除前映像备份，只有 COMMITTED/ROLLED_BACK 且最终核对完成后可以归档事务日志并释放阻断；UNRESOLVED 保留全部证据。事务日志存在但尚无工作区写入时按 ROLLED_BACK 处理并删除已核对的临时文件。只有持久化阶段支持上述恢复；普通重启不能把不确定事务改写为成功。

**输出：** VerifiedCandidate、PersistenceTransaction、RecoveryInspection、COMMITTED / ROLLED_BACK / UNRESOLVED，以及对应 SUCCEEDED / STOPPED / RECOVERY_REQUIRED 生命周期结果。

**错误：** FORMAL_VALIDATION_FAILED、APPROVAL_STALE、WORKSPACE_CHANGED、PERSISTENCE_FAILED、PERSISTENCE_UNCERTAIN、WRITEBACK_MISMATCH。

**确定性测试：** 使用临时目录与故障注入点覆盖写入前失败、部分替换、完整提交、前映像变化、可回滚和未知字节；启动两个进程竞争同一 workspace lock，断言只有一个成功。未知证据只能进入 RECOVERY_REQUIRED，且 preview、apply、备份清理和锁释放结果可重复。

## 4.7 FR-CRED：真实 LLM 凭据

**接口：**

    SetCredential(provider, secret) -> CredentialMutationResult
    GetCredentialStatus(provider) -> CredentialStatus
    ClearCredential(provider) -> CredentialMutationResult

`provider` 的 v1 唯一值为 OPENAI。`secret` 只存在于隐藏 WebUI 表单到 CredentialStore 适配器的调用内存中，不得进入 URL、命令行参数、SQLite、日志、审计或异常正文。

**行为：**

1. 应用启动和每次写操作前验证实际 keyring backend 是 `keyring.backends.Windows.WinVaultKeyring`；未知、明文、不可用或非 Windows 后端统一失败关闭，不得静默降级。
2. SetCredential 使用固定服务名和当前 Windows 用户作用域写入；已有条目时原子覆盖。成功结果不含 secret、长度、前后值或可推断 secret 的摘要。
3. GetCredentialStatus 只返回 `configured`、provider 和最近成功更新时间；不得读取后回显 secret。
4. ClearCredential 删除条目；不存在时返回稳定的未配置结果，后端删除失败必须显式失败。
5. 公网 Demo 不注册 CredentialStore、FR-CRED 路由或真实 LLM 能力。

**输出与错误：** CredentialStatus、CredentialMutationResult；稳定错误为 `CREDENTIAL_BACKEND_UNAVAILABLE`、`CREDENTIAL_WRITE_FAILED`、`CREDENTIAL_READ_FAILED`、`CREDENTIAL_DELETE_FAILED`。任何错误都不得包含 secret。

**确定性测试：** 使用 FakeCredentialStore 覆盖首次写入、更新、非回显状态、清除、不存在和后端故障；Windows release smoke 必须证明实际 backend 为 Windows Credential Manager，并以测试秘密检查日志、审计和 HTTP 响应均无泄露。

## 4.8 FR-MEM：记忆与审计

**输入：** 规范化工作区身份、当前运行主体、用户记忆操作和控制面事件。

**记忆：**

- MemoryEntry 只保存仓库身份、类型、用户可见摘要、来源、创建/更新时间和状态。
- 类型限于 PROJECT_CONVENTION | USER_DECISION | RUN_SUMMARY | KNOWN_FAILURE。
- 创建权固定为：RUN_SUMMARY 和 KNOWN_FAILURE 只能由控制面根据已提交的运行/检查事实确定性创建；PROJECT_CONVENTION 只能由用户显式创建或确认；USER_DECISION 只能由已验证的真实用户决定派生。
- AgentAction 联合不包含通用 `remember(text)`；模型、仓库文本、工具输出和 LLM 摘要都不能直接写 MemoryEntry。自动生成摘要必须标记事实来源，并在投影中继续按不可信上下文处理。
- 每次上下文最多选择 20 条、16 KiB；确定性按当前仓库、类型优先级和时间排序。
- 记忆不能修改策略、Manifest、审批、配置或成功条件。
- 用户清除后，后续 turn 和运行不得再选择该条目。

**审计：**

- 记录运行状态变化、动作摘要、策略决定、审批生命周期、披露授权元数据、检查结果、停止和成功证据。
- 不记录凭据、完整 LLM 请求/响应、完整文件正文或未截断工具输出。
- 审计事件不可由 Agent 修改；默认保留 30 天，用户可以显式清除已结束运行的本地审计。

**输出：** 有界 MemorySelection、记忆查看/清除结果和按序 AuditEvent。

**边界和错误：** 跨仓库检索、秘密或完整正文写入、Agent 修改和无来源条目均拒绝；存储失败必须返回 MEMORY_STORE_FAILED 或 AUDIT_STORE_FAILED，不得假装成功。

**确定性测试：** 使用两个临时工作区身份、固定时钟和内存 SQLite，验证四种类型的合法/非法创建者、模型无法直接写入、来源缺失拒绝、选择顺序、跨仓库隔离、清除效果、秘密字段拒绝和审计序号单调。

## 4.9 FR-UI：本地 WebUI 与公网 Demo

**输入：** 已认证本地会话请求，或受限公网 Demo 场景和用户选择。

**本地模式：**

- CLI 启动绑定 127.0.0.1 的 WebUI。
- 使用随机本地会话令牌、严格 Host/Origin 校验和 CSRF 防护。
- 提供运行创建、状态、diff、审批、凭据状态、记忆和审计页面。
- 不可信文本以纯文本或安全转义方式渲染，不执行仓库 HTML。

**公网 Demo：**

- 独立进程只注册 Mock LLM、内置场景和 DemoExecutor。
- 不注册本地文件、Keyring、Docker 或真实供应商适配器。
- 固定场景必须展示：硬 DENY 拦截；一次检查失败使下一动作改变；受保护验收工件修改被拒绝。
- DemoSession 与正式 Run 是不同实体；`DemoSessionStatus = ACTIVE | DEMO_COMPLETED | DEMO_FAILED`，任何值都不能映射为正式 SUCCEEDED。
- 会话有独立 UUID 状态，最长 5 分钟；结束后丢弃。重置失败只使该会话停止，不创建跨进程恢复协议。

**输出：** 安全渲染的状态、diff、审批、检查、记忆和审计页面，以及 DEMO_COMPLETED 或 DEMO_FAILED。

**边界和错误：** 本地 Host/Origin/CSRF 校验失败、无效会话、Demo 非法场景或能力请求必须拒绝；公网进程不得以错误恢复为由注册本地或真实能力。

**确定性测试：** 使用测试客户端验证 Host/Origin/CSRF、HTML 转义和状态映射；固定 Demo 场景重复两次，断言关键动作、状态和终态一致且真实适配器调用次数为零。

# 5. 非功能需求与安全

## 5.1 NFR-PERF：性能与预算

- 正式运行最大 20 个 Agent turn、20 次 LLM 调用、15 分钟。
- 单工具动作默认 60 秒，正式完整验证默认 10 分钟。
- 单次 LLM 规范请求不超过 64 KiB，单次工具反馈不超过 32 KiB。
- 公网 Demo 每会话最多 20 个动作、5 分钟；进程级并发上限 10。
- 达到上限必须在动作或调用前停止，不得把截断后的无效结果视为成功。
- 仓库、执行副本、Docker 和检查输出的硬上限由 `PythonProjectProfileV1` 冻结；用户配置只能进一步收紧。

## 5.2 NFR-REL：可靠性

- 相同 Mock 脚本、快照、配置和用户决定必须产生相同关键动作、状态和终态。
- 所有核心机制使用离线、无网络的 Mock/Stub 单元测试。
- 未知或不完整证据默认失败关闭。
- 只有持久化阶段允许恢复；其他重启统一停止。

## 5.3 NFR-USE：可用性

- 所有拒绝和停止结果必须包含稳定代码、用户可理解原因和下一步建议。
- WebUI 不直接暴露内部引用图或数据库字段。
- 用户必须能区分准备中、运行中、等待决定、恢复阻塞、成功和停止。
- diff、审批对象和验证证据必须在同一页面关联展示。

## 5.4 NFR-OBS：可观测性

- 每个运行有唯一 run_id 和按顺序递增的审计序号。
- 日志使用结构化事件，并对路径、输出和错误文本执行长度限制与脱敏。
- 测试模式允许注入时钟和 ID 生成器，以获得稳定快照。
- GitHub Actions 的 `unit-test` job 必须在每次 push/PR 运行；`.gitlab-ci.yml` 也必须包含调用相同唯一测试命令的 `unit-test` job。两套最终记录都必须通过。

## 5.5 NFR-SEC：凭据威胁模型

| 资产/风险 | 攻击者或来源 | 对策 | 残余风险 |
|---|---|---|---|
| OpenAI API Key | 仓库文本、日志、命令历史、Demo 用户 | Windows Credential Manager；隐藏录入；禁止 CLI 参数和明文配置；日志字段白名单 | 同一 Windows 用户或管理员仍可能访问凭据 |
| 用户源码 | 恶意模型、提示注入、错误披露范围 | 本地读取与外发分离；逐请求摘要授权；敏感路径硬拒绝 | 不能识别所有源码中的秘密 |
| 权威工作区 | 越界路径、symlink/reparse、陈旧批准 | 双重路径校验、无链接文件画像、前映像绑定、写后核对 | 最后检查与替换间仍有短暂本机竞争窗口 |
| 验收契约 | 模型修改测试或配置 | 控制面不可变 Manifest、保护工件集合、正式重验 | Manifest 只能覆盖支持画像中已识别的检查 |
| 控制面数据 | 项目代码或容器读取宿主数据 | 无网络容器、只挂载执行副本、控制面目录不挂载 | Docker Desktop/宿主管理员不在威胁模型内 |
| WebUI | CSRF、恶意仓库 HTML、远程访问 | loopback、会话令牌、Host/Origin、CSRF、安全转义 | 本机恶意进程可能与用户权限相同 |
| 公网 Demo | 越权到真实能力、跨会话数据 | 独立能力注册表、固定场景、无凭据、会话隔离 | 部署平台管理员仍可访问服务运行环境 |

安全属性必须表述为在上述前提下可测试的机制，不使用绝对安全或保证识别所有攻击的承诺。

## 5.6 NFR-PRIV：数据保留

- 凭据只存于 Windows Credential Manager。
- 运行数据库、记忆和审计默认位于用户本地应用数据目录，不进入目标仓库。
- 审计默认保留 30 天；执行副本在运行终止后立即尝试删除。
- 公网 Demo 不接收用户仓库、真实凭据或任意文件上传。

# 6. 系统架构

## 6.1 组件图

    Local WebUI / Demo UI
              |
      Application Service
              |
          Agent Loop
       /      |       \
    Context  LLM    Tool Dispatcher
      |       |       /     |      \
    SQLite   Mock/  Policy  Workspace  Project Adapter
             OpenAI    |       |          |
             WritebackApproval  Persistence  DockerExecutor
                                |
                       Authoritative Workspace

依赖方向从应用服务指向核心端口，再指向适配器。LLM、Docker、Keyring、数据库和文件系统必须可替换为测试 double。WebUI 不直接访问仓库或数据库。

## 6.2 正式修复数据流

    RunRequest
    → 配置与准入
    → SnapshotTree
    → 两次稳定基线
    → ValidationManifestV1
    → Agent turn / 治理 / 候选补丁 / 检查反馈循环
    → 全新副本正式验证
    → VerifiedCandidate
    → 用户批准精确 FinalDiff
    → 持久化事务与写后核对
    → SUCCEEDED、RECOVERY_REQUIRED 或结构化 STOPPED

## 6.3 公网 Demo 数据流

    固定 Scenario
    → Mock LLM 脚本
    → 相同动作解析、策略、反馈和停止核心
    → DemoExecutor 模拟结果
    → 模拟审计和 DEMO_COMPLETED

Demo 不经过 Keyring、真实 LLM、Docker 或权威持久化。

## 6.4 外部依赖

- OpenAI：仅单轮生成接口；不使用 Agent runner。
- Docker Desktop：运行目标代码和正式检查。
- Windows Credential Manager：真实 API Key 存储。
- Git：只读准入、快照身份和工作区一致性检查。
- pytest、Ruff、Mypy：由 Python 项目适配器调用并解析。

# 7. 数据模型

| 实体 | 关键字段 | 关系与约束 |
|---|---|---|
| Run | id、workspace_identity、status、phase、config_snapshot_id | 一个运行有多个 turn；终态不可重开 |
| RunConfigSnapshot | schema_version、normalized_config、digest | 创建后不可变；不能包含秘密 |
| SnapshotTree | root_digest、entries、repository_policy_digest | 一个运行一个权威基线快照 |
| ValidationManifestV1 | target IDs、test collection、protected digests、check plan、environment digest | 由基线创建后不可变 |
| CandidateRevision | id、parent_id、diff_digest、tree_digest | 单父链；正文存本地工件，不进审计 |
| AgentTurn | id、run_id、candidate_id、context_digest、consumed_feedback_refs、outcome | 同一运行最多一个活动 turn |
| ActionRecord | action_type、canonical_digest、policy_decision、result_ref | 动作输入与结果不可被 Agent 改写 |
| FeedbackRecord | source_ref、kind、bounded_payload、consumed_by_turn | 最多被一个下一 turn 消费 |
| WritebackApproval | subject_digest、bindings、expires_at、status | 只授权最终权威写回；PENDING 只能一次转入一个终局状态 |
| DisclosureRequest | run_id、source_phase、provider、model、request_digest、source categories、bytes、expires_at | 每个真实请求一个待决定对象；拒绝或超时停止运行 |
| DisclosureAuthorizationRecord | disclosure_request_id、llm_call_attempt_id、provider、model、request_digest、source categories、bytes、expires_at、status | AUTHORIZED 只能原子消费为 CONSUMED；只授权一次调用尝试，不含正文 |
| CheckResult | check_kind、status、structured_findings、raw_digest | 原始输出作为有界本地工件 |
| VerifiedCandidate | candidate_id、manifest_id、formal_result_digest | 只有完整正式验证通过时创建 |
| PersistenceTransaction | final_diff_digest、preimages、postimages、state | 未解决时阻止同工作区新运行 |
| MemoryEntry | workspace_identity、kind、summary、source、timestamps | 不保存秘密、权限或完整源码 |
| AuditEvent | run_id、sequence、event_type、redacted_payload | 每个运行序号唯一且单调 |
| DemoSession | id、scenario_version、status、expires_at | 与 Run 隔离；状态只允许 ACTIVE、DEMO_COMPLETED、DEMO_FAILED |

控制存储使用 SQLite 事务保证单进程内的状态比较与更新。大文件、执行副本、补丁正文和原始检查输出存为本地受限工件，只在数据库保存摘要与精确路径；凭据从不进入 SQLite。

# 8. 凭据、分发与部署

## 8.1 凭据流程

1. 首次选择真实 LLM 时，WebUI 通过 password 输入控件调用 FR-CRED 的 SetCredential。
2. 后端在确认实际 backend 为 Windows Credential Manager 后直接写入；不经过命令行参数、URL、SQLite、日志或审计。
3. GetCredentialStatus 只返回配置状态、供应商和最近成功更新时间。
4. 更新再次调用 SetCredential，以新秘密覆盖旧条目并返回不含秘密的明确结果。
5. ClearCredential 删除凭据条目；删除失败必须报告稳定错误，不能假装成功。
6. 公网 Demo 构建不包含 FR-CRED 路由、CredentialStore 或真实 LLM 适配器注册。

## 8.2 本地分发

- v1 版本固定为 0.1.0，交付本地 wheel，不承诺发布 PyPI。构建产物固定命名为 `dist/vespercode-0.1.0-py3-none-any.whl`，安装命令为 `pipx install .\dist\vespercode-0.1.0-py3-none-any.whl`。
- vespercode serve 启动本地 WebUI；首次运行执行非秘密环境检查和凭据引导。
- 目标机器前提：Windows 11 x64、Python 3.12、Git、Docker Desktop Linux 容器模式，以及预构建的受支持执行镜像。
- README 必须给出获取、安装、启动、凭据配置、Docker profile 准备、目录结构和已知限制。

## 8.3 公网 Demo 分发

- 使用独立 Docker 镜像启动 Mock Demo。
- 镜像不包含本地模式能力注册、真实凭据入口或 Docker socket。
- 唯一部署平台为 Render Web Service，使用仓库中的 Demo Dockerfile 从 main 分支构建。
- 容器读取 Render 注入的 PORT 并绑定 0.0.0.0，健康检查固定为 GET /healthz。
- 服务不挂载持久磁盘；会话状态只存在进程内，进程重启后全部丢弃。
- Render 环境不得配置真实 LLM Key、Docker socket 或目标仓库访问凭据。
- README 记录公开 URL、Render 服务配置、健康检查和免费实例可能冷启动的限制。
- GitHub Actions 的 `demo-image` job 构建 Demo 镜像，但不得在测试中访问真实 LLM。
- 仓库同时交付最小 `.gitlab-ci.yml`；它只需提供名为 `unit-test` 的 job，并调用与 GitHub Actions 相同的 `python -m pytest -q`，不复制 Windows、Docker、wheel 或 Demo jobs。

# 9. 技术选型

| 项目 | 选择 | 理由 |
|---|---|---|
| 语言 | Python 3.12 | 与目标项目和测试生态一致，适合快速实现可注入端口 |
| API/Web | FastAPI + Pydantic v2 | 严格请求 Schema、类型校验和本地/公网复用 |
| UI | 服务端 HTML + HTMX；Open Design 作为设计系统，实施时使用 ui-ux-pro-max skill 做交互与可访问性检查 | 降低前端状态复杂度，满足 WebUI 交付 |
| 控制存储 | SQLite | 支持本地原子状态更新、无需额外服务 |
| 凭据 | keyring 的 `keyring.backends.Windows.WinVaultKeyring`；启动时验证实际后端 | 满足系统钥匙串存储要求并禁止静默降级 |
| LLM | 自定义 LLMAdapter；Mock + OpenAI 单轮适配器 | 不依赖高层 Agent 框架，真实与离线路线共享核心 |
| 执行 | Docker SDK for Python；命令以 argv 传入，禁用网络，容器根文件系统和 CandidateTree 均只读，仅有界 tmpfs 可写 | 消除 API/CLI 实现分歧，阻止检查期间瞬时篡改并形成结构化执行证据 |
| 检查 | pytest、Ruff、Mypy | 提供测试、lint 和类型反馈 |
| 测试 | pytest；单一命令 python -m pytest -q | 离线、可注入、适合 TDD |
| CI | GitHub Actions `.github/workflows/ci.yml` 提供完整 `unit-test`、`windows-integration`、`docker-integration`、`package-smoke`、`demo-image`；最小 `.gitlab-ci.yml` 提供同命令 `unit-test` | 同时满足课程 §4.8 的 GitHub Actions 和最终清单的 GitLab CI 强制条款 |
| 包分发 | 本地 wheel 0.1.0 + pipx 路径安装 | 适合 Windows 本地 CLI/WebUI，且不额外承诺 PyPI 发布流程 |
| Demo | OCI 容器 | 与本地能力隔离，便于公网部署 |
| 公网部署 | Render Web Service；Docker runtime、/healthz、无持久磁盘 | 冻结公开 WebUI 的端口、健康检查和无状态边界 |

依赖必须锁定。不得引入 LangChain AgentExecutor、AutoGen、CrewAI、LlamaIndex Agent 或宿主编码智能体 runner。

# 10. 验收标准与追踪

## 10.1 项目级验收

- AC-01：路径逃逸、绝对路径、ADS、symlink/reparse、hard link、敏感 tracked 路径和命中冻结 ignore 规则的新文件全部确定性拒绝。
- AC-02：硬 DENY 无法被配置、模型输出或批准覆盖。
- AC-03：一次性批准在过期、绑定变化和重复消费时均不执行。
- AC-04：修改测试、检查配置或 Manifest 保护工件的补丁不能进入检查或正式验证；检查期间尝试写 CandidateTree 失败且不能产生 VerifiedCandidate。
- AC-05：注入固定检查失败后，Mock LLM 下一轮动作按脚本发生变化。
- AC-06：LLM completion 建议不能绕过完整正式验证和最终批准。
- AC-07：写回内容精确等于已批准 FinalDiff；外部工作区变化阻止写入。
- AC-08：FR-CRED 的录入、状态、更新、清除和故障结果均不暴露测试秘密；非 Windows Credential Manager backend 稳定拒绝。
- AC-09：同一 Demo 输入产生相同关键状态和动作序列。
- AC-10：`python -m pytest -q` 离线通过；GitHub Actions `unit-test` 在每次 push/PR 运行，`.gitlab-ci.yml` 的同名 job 调用同一命令，两套最终记录均通过。
- AC-11：`pipx install .\dist\vespercode-0.1.0-py3-none-any.whl` 可在全新受支持 Windows 环境安装；README 步骤可启动 WebUI 并访问 `/healthz`。
- AC-12：公网 Mock Demo URL 可访问且无法使用本地/真实能力。
- AC-13：未授权披露时真实适配器调用次数为零；每个不同 request_digest 需要独立确认；WritebackApproval 与披露授权不能互用，供应商、模型、来源、字节预算或有效期变化使旧授权失效。
- AC-14：两个工作区的记忆相互隔离；四种 MemoryEntry 只有规定主体可创建；模型不能直接 remember；用户清除后后续 turn 不再选择该条目。
- AC-15：无效 RunRequest 不创建 Run；有效请求先形成可见 CREATED；仓库、画像、Docker profile 或凭据准入拒绝形成带 run_id 的审计 STOPPED，且发生在 LLM 和执行器调用前、不修改权威工作区。
- AC-16：CREATED、RUNNING、WAITING_USER、RECOVERY_REQUIRED、SUCCEEDED、STOPPED 分别显示为正确用户状态，失败、超时和未运行不显示为通过。
- AC-17：只有 `python-reference-v1` fixture 能通过画像识别；布局、配置、依赖摘要、敏感文件、hard link 或资源任一不匹配均在 LLM/执行前返回稳定拒绝。
- AC-18：Harness reporter 的版本/摘要/事件流有效，正式验证的收集集合、逐 node PASS、每个目标从稳定失败转绿、Ruff/Mypy、环境、保护工件和只读树谓词全部满足时才创建 VerifiedCandidate；任一 skip/xfail/xpass/deselect/NOT_RUN/错误均失败关闭。
- AC-19：两个进程竞争同一 workspace 时只有一个取得锁；崩溃事务只能得到 COMMITTED、ROLLED_BACK 或 UNRESOLVED，未知字节不能被忽略或报告成功。
- AC-20：DemoSession 只显示 ACTIVE、DEMO_COMPLETED 或 DEMO_FAILED，任何页面和审计都不得映射为正式 SUCCEEDED。

## 10.2 用户故事—合同—验收追踪

| 用户故事 | 权威功能合同 | 适用 NFR | 主要验收 |
|---|---|---|---|
| US-01 | FR-ADM | NFR-PERF、NFR-USE、NFR-SEC | AC-10、AC-11、AC-15、AC-17 |
| US-02 | FR-CRED、§8.1 | NFR-SEC、NFR-PRIV | AC-08 |
| US-03 | FR-LOOP、FR-WS、FR-VAL | NFR-PERF、NFR-REL | AC-04、AC-05、AC-06、AC-17、AC-18 |
| US-04 | FR-GOV | NFR-SEC、NFR-PRIV | AC-13、AC-16 |
| US-05 | FR-GOV | NFR-REL、NFR-SEC | AC-01、AC-02、AC-03 |
| US-06 | FR-PERSIST | NFR-REL、NFR-SEC | AC-06、AC-07、AC-18、AC-19 |
| US-07 | FR-MEM | NFR-OBS、NFR-PRIV | AC-14 |
| US-08 | FR-LOOP、FR-MEM、FR-UI | NFR-USE、NFR-OBS | AC-06、AC-16 |
| US-09 | FR-UI | NFR-PERF、NFR-REL、NFR-SEC | AC-09、AC-12、AC-20 |

## 10.3 机制演示

离线脚本或测试必须在同一场景中展示：

1. Mock LLM 提出读取工作区外路径，治理护栏返回 DENY；
2. Mock LLM 提出合法但失败的候选补丁，pytest 失败被结构化回灌，下一轮动作改变；
3. Mock LLM 尝试修改受保护测试或 Ruff/Mypy 配置，Manifest 保护机制拒绝；
4. 修正后的候选通过正式验证，但在没有最终批准时不会写入权威工作区。

## 10.4 验证环境与证据矩阵

| 层次 | 执行环境与内容 | 主要 AC | 门禁与保存证据 |
|---|---|---|---|
| 离线单元测试 | GitHub Actions 与 `.gitlab-ci.yml` 的 `unit-test` 调用同一命令，使用 Mock/Stub LLM、FakeCredentialStore、reporter 事件夹具和内存/临时存储；不得访问网络、真实 LLM 或真实 Docker | AC-02、AC-03、AC-05、AC-06、AC-08、AC-09、AC-10、AC-13、AC-14、AC-15、AC-16、AC-20 | GitHub 每次 push/PR 与 GitLab 最终记录必须通过；保存测试报告和 job URL |
| Windows 集成 | `windows-integration` 使用 windows-latest 验证 ADS、reparse、hard link、设备名、`msvcrt.locking` 和测试秘密非泄露；真实 Credential Manager 另在受支持 Windows 11 release smoke 验证 | AC-01、AC-08、AC-17、AC-19 | CI 报告加 release checklist；失败阻止发布 |
| Docker 集成 | `docker-integration` 在 Linux Docker runner 验证无网络、非 root、只读 root/CandidateTree、无 Docker socket、tmpfs 和资源限制；Windows 11 + Docker Desktop 重复关键 smoke | AC-04、AC-17、AC-18 | CI 夹具报告加 Windows Docker Desktop 证据；失败阻止发布 |
| 端到端 reference fixture | 固定 `python-reference-v1`：稳定失败 → 首次错误补丁 → 反馈回灌 → 修正 → 正式验证 → 最终批准 → 精确写回；另跑未批准不写回路径 | AC-05、AC-06、AC-07、AC-11、AC-15、AC-18、AC-19 | release smoke 保存动作/状态序列、最终 diff、Manifest/验证摘要和工作区摘要 |
| 分发与 Demo | `package-smoke` 构建 wheel 并用 pipx 安装；`demo-image` 构建镜像；部署后检查 `/healthz` 和能力注册表 | AC-10、AC-11、AC-12、AC-20 | wheel、镜像构建日志、公开 URL 和能力拒绝证据 |

每个 AC 必须至少映射到上表一层；涉及 Windows 或 Docker 专属安全属性时，离线单测不能作为唯一完成证据。

# 11. 风险、残余风险与未来工作

## 11.1 v1 风险

| 风险 | 概率/影响 | 触发信号 | 缓解或降级 |
|---|---|---|---|
| Python fixture 与真实项目差异过大 | 中/中 | 外部试用频繁命中不支持 | 保持参考画像定位；公开兼容矩阵，不临时扩张 |
| Docker Desktop 行为或性能不稳定 | 中/高 | 检查超时、挂载异常 | 固定 profile 和镜像摘要；准入失败关闭 |
| pytest/Ruff/Mypy 输出解析漂移 | 中/中 | 未知结果或解析错误 | 固定版本；使用机器可读输出；未知状态不通过 |
| 多文件持久化中断 | 低/高 | 事务日志未完成 | 前后映像、备份和最小恢复；矛盾时阻塞人工处理 |
| 真实 LLM 泄露未识别秘密 | 中/高 | 请求包含未分类敏感值 | 路径硬拒绝、逐请求确认、体量限制；明确残余风险 |
| SPEC 再次扩张 | 中/高 | 新增恢复/分布式状态或大量类型 | 所有新增必须先修改 §1.5/1.6 并经用户和独立审查批准 |
| 公网 Demo 被误认为正式验证 | 低/中 | UI 或审计缺少模拟标识 | 独立终态、持续标识、能力注册表隔离 |

## 11.2 进入 PLAN 的关闭门禁

本稿在独立复验给出 FINAL PASS 前仍是范围冻结候选，不声明“无架构级未决项”。进入 PLAN 前必须同时关闭并提供行号证据：

1. Validate/Create/START/PREFLIGHT 和成功发布权威唯一；
2. 六种动作、严格 patch、累计净差异和 ContextProjection 已冻结；
3. 逐请求披露、WritebackApproval 与 WAITING_USER 生命周期闭合；
4. `python-reference-v1`、只读检查和正式成功谓词闭合；
5. recover、跨进程锁、FR-CRED 和记忆创建权闭合；
6. pytest reporter 权威事件协议、所有 US→FR→AC 和 AC→验证环境映射完整；
7. 独立严格审查 P0/P1/P2 全部为零，且十项核心不变量未改变。

依赖的精确 patch 版本、实际 Docker 镜像摘要和部署 URL 属于实现/发布证据，必须由 lock file、CI 和 README 记录，不改变本 SPEC 的行为边界。

## 11.3 未来工作

- NaturalLanguageDefect、测试提案审批和 ValidationManifestV2。
- 更宽松但仍确定性的 skip/xfail 基线比较。
- 多语言 ProjectAdapter。
- 供应商请求重试、跨进程调用对账和普通 turn 恢复。
- 删除、重命名、二进制补丁和更广 Git 策略。
- 多用户部署、分布式配额和生产级工件清理。

这些项目不得出现在 v1 的 PLAN.md、代码路径或验收门禁中。
