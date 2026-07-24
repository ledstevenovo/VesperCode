# VesperCode v1 规格说明

> 版本：SPEC v3  
> 状态：范围冻结候选稿。完成独立审查、冷启动试验和本文 §10 的验证证据前，不得宣称实现完成。

## 0. 文档约定

本文与 `AI4SE_Final_Project_通用要求.md`、`AI4SE_Final_Project_A_Coding_Agent_Harness(1).md` 共同构成项目要求；冲突时课程原文优先。

规范词含义如下：

- **必须 / 不得**：v1 强制要求。
- **应当**：除非在 `AGENT_LOG.md` 中记录明确理由，否则必须满足。
- **可以**：非强制实现选择。
- **未来工作**：不属于 v1，不得进入 v1 的实现任务或验收门禁。

每项规范合同只在一个章节定义。问题陈述和用户故事只描述可观察结果，不重新定义内部协议。功能合同使用 `FR-*`，非功能要求使用 `NFR-*`，验收标准使用 `AC-*`。

精确依赖 patch 版本、OpenAI model、profile manifest 摘要、Docker 镜像摘要、发布 URL 和 CI 执行编号属于实现与发布证据，必须记录在 lock file、manifest、CI 和 README 中，并由运行快照绑定，但不改变本文冻结的行为边界。

## 0.1 `CanonicalizationV1`

所有用于身份、重放、策略、批准、披露、验证和持久化绑定的摘要统一使用 SHA-256，并以对象类型和 schema 版本作域分隔。不同对象即使正文相同，也不得产生可互换的绑定摘要。

规范 JSON 使用无 BOM UTF-8：对象键按 Unicode code point 升序排列；不保留无意义空白；整数使用十进制；禁止浮点数、`NaN` 和无穷值；数组保持各合同规定的规范顺序。时间统一为 UTC RFC3339。未被具体合同声明为绑定字段的进程 ID、随机 ID、时间、审计序号和显示文本不得进入语义重放摘要。

仓库内路径统一为使用 `/` 的规范相对路径。路径解析必须拒绝 `.`/`..` 段、空段、绝对路径、盘符、UNC、ADS、设备路径、尾随点/空格、保留设备名、Unicode 或 Windows 大小写折叠后碰撞，以及多个输入解析到同一最终对象的别名。工作区身份绑定规范绝对路径、卷标识和最终目录对象身份；仅对路径字符串做大小写转换不构成身份验证。

下列对象的摘要输入必须唯一：

- `AgentAction`：拒绝未知字段后的完整规范动作对象；
- `ContextProjection`：裁剪完成、来源和裁剪决定已固定的最终投影；
- `ReferenceProfileManifestV1` 和 `LLMProfileManifestV1`：除自身 `digest` 外的全部规范字段；
- `ValidationManifestV1`：全部规范字段，不含显示文本；
- `FailureFingerprintV1`：规范测试身份、调用阶段失败事实、异常类型、规范消息、断言差异和项目栈帧；
- `FinalDiff`：§4.3 定义的规范树差异字节；
- 工作区前/后映像：规范路径、`ABSENT` 或原始文件字节摘要、文本元数据和最终对象身份；
- 语义检查结果：检查类型、输入树、环境、逐测试/诊断事实和稳定错误；排除执行时间、容器 ID 与审计序号。

# 1. 问题陈述与范围

## 1.1 用户问题

现有 Coding Agent 在本地仓库中工作时，用户通常难以确认：

1. Agent 是否只访问和修改了允许的文件，还是越过工作区或接触了敏感路径；
2. 测试是否完整执行，还是通过删除测试、增加跳过或修改检查配置获得表面成功；
3. 一次批准是否只授权了用户实际看到的动作和 diff；
4. 本地允许读取的数据是否被自动发送给外部 LLM；
5. 最终写回的内容是否就是已验证、已批准的候选内容；
6. 写回中断后，工作区是否仍处于可证明的状态。

仅在提示词中要求模型谨慎不能确定性解决这些问题。模型输出、仓库文本、工具输出和记忆均可能不可靠；治理、检查、审批、成功判定、停止和恢复必须由 Harness 代码控制。

## 1.2 产品定位

**VesperCode 是一个面向 Windows 11 本地 Python 参考仓库的治理型 Coding Agent Harness 原型：它在隔离候选树中修复已有失败测试，用 pytest、Ruff 和 Mypy 验证候选结果，并在用户批准精确 diff 后才写回原仓库。**

主要贡献是一条可离线测试的确定性治理管线：

    结构化动作
    → 路径、项目画像与验收契约校验
    → ALLOW / ASK / DENY
    → 精确动作的一次性批准
    → 运行级披露 Grant + 逐请求授权记录
    → 不可变 ValidationManifestV1 下的正式验证
    → 用户批准精确 FinalDiff
    → 受控写回、写后核对与最小恢复

项目定位是课程型、安全研究型参考 Harness，不承诺兼容普通 Python 生态中的任意仓库，也不以生产级分布式控制平面为目标。

## 1.3 目标用户

目标用户是希望观察和评估治理机制的课程评审者、安全研究者，以及愿意使用受支持参考画像的 Windows 本地 Python 开发者。

用户需要理解 Git、pytest 和 diff 的基本概念，但不需要理解内部数据库结构或事务实现。

## 1.4 v1 支持矩阵

| 维度 | v1 支持 | v1 不支持 |
|---|---|---|
| 宿主 | Windows 11 x64，Docker Desktop Linux 容器模式 | macOS、Linux 宿主、Windows 容器 |
| Harness 运行时 | Python `>=3.12,<3.13` | 其他 Python 主版本 |
| 目标项目 | §1.4.1 的 `PythonProjectProfileV1` | 任意 Python 项目、自动猜测项目布局 |
| 缺陷输入 | 已存在且可稳定复现的 pytest 失败测试 | 自然语言缺陷自动生成测试 |
| 检查 | pytest 8.x、Ruff、Mypy；命令由适配器生成 | 任意 Shell、任意 argv、动态下载工具 |
| 补丁 | 严格 `UNIFIED_DIFF_V1`；UTF-8/UTF-8 BOM 普通文本的创建和修改 | 删除、重命名、二进制、链接、模式变更、模糊应用 |
| Git | 有有效 HEAD、满足 §1.4.1 干净谓词且字节与 HEAD blob 一致的普通仓库 | submodule、LFS、稀疏检出、filter、工作树编码转换、特殊 index 状态、脏工作区 |
| 执行 | 预构建、无网络、候选树只读挂载的 Docker profile | 宿主执行、运行中构建镜像或安装依赖 |
| LLM | 可注入 Mock LLM；一个 OpenAI 单轮适配器 | 高层 Agent 框架、自动重试与跨崩溃调用恢复 |
| WebUI | 本地 WebUI；公网 Mock Demo | 公网读取本地仓库、上传任意仓库、公网真实凭据 |

发布时必须在 lock file 和 README 的兼容性表中记录通过验证的精确依赖版本、Docker 镜像摘要和 Windows/Docker Desktop 环境。超出画像的输入以明确的不支持结果停止，不得静默降级。

### 1.4.1 `PythonProjectProfileV1`

v1 只支持 profile id 为 `python-src-py312-v1` 的参考画像：

#### `ReferenceProfileManifestV1`

参考画像不是仅靠字符串约定的规则集合。发布包必须内置且只读地提供：

    ReferenceProfileManifestV1 {
      schema_version: 1
      profile_id: "python-src-py312-v1"
      requirements_lock_digest
      docker_image_digest
      python_version
      pytest_version
      report_plugin_version
      ruff_version
      mypy_version
      check_plan_version
      digest
    }

`digest` 按 §0.1 对除自身外的全部字段计算。目标仓库的 `requirements.lock` 必须精确匹配该 manifest 的 `requirements_lock_digest`；仅提供相同 profile id 不构成匹配。预检、基线、正式验证和发布证据必须使用同一个 manifest digest 和 Docker image digest。

交付仓库必须提供一个与该 manifest 匹配、能走完基线、错误补丁反馈、修正、正式验证和写回流程的 reference fixture。该 fixture 是实现和端到端验收工件，不扩大正式输入范围。

#### `StaticProjectProfileCheckV1`

静态预检不运行项目代码，只验证可由仓库快照、Git 元数据、内置 manifest 和 Docker 配置证明的事实：

| 项目 | 静态冻结要求 |
|---|---|
| 根目录文件 | 必须存在 `pyproject.toml` 和 `requirements.lock` |
| 源码布局 | 业务源码位于 `src/`；测试位于 `tests/` |
| Python 与工具 | 宿主适配器、容器和工具版本精确匹配 `ReferenceProfileManifestV1` |
| pytest | 配置只来自 `pyproject.toml`；允许内建插件及执行镜像内固定的机器可读报告插件 |
| Ruff / Mypy | 均必须在 `pyproject.toml` 中显式配置；未配置视为不支持，而不是跳过 |
| 依赖 | `requirements.lock` 摘要精确匹配 manifest；运行中不得安装或更新 |
| 文本 | 可编辑文件必须为 UTF-8 或 UTF-8 BOM、统一 LF/CRLF、具有末尾换行；混合换行文件不可编辑 |
| pytest 扩展 | 不支持自定义收集插件、动态下载插件或入口点自动加载 |
| Git 干净谓词 | index tree 必须等于 HEAD；不存在 unmerged、非 stage-0、intent-to-add、skip-worktree、assume-unchanged、tracked 字节漂移或不允许的 untracked 文件 |

    StaticProjectProfileResult =
      SUPPORTED {
        profile_id
        reference_profile_digest
        repository_policy_digest
      }
      | UNSUPPORTED_PROJECT {
        reasons[]
      }

`ProjectAdapter.detect_static` 必须逐项验证静态画像。任何一项无法证明时返回上述 `UNSUPPORTED_PROJECT`，不得猜测、运行项目代码或跳过检查。

未跟踪文件只有在冻结 ignore 规则下被忽略且不命中 §1.4.2—1.4.3 时才允许存在；它们不得进入 `SnapshotTree`、容器、披露来源或最终差异。Git index、工作树和 HEAD 的比较必须禁用宿主 system/global 配置、外部 attributes/ignore 和可改变内容的 filter。任意规范路径在 Windows 大小写或 Unicode 折叠后发生碰撞时返回 `UNSUPPORTED_REPOSITORY`。

有效 Git 配置必须满足 `core.autocrlf=false`，且不得通过 repository config 或 `.gitattributes` 为任一 tracked 路径启用 `core.eol`、`eol`、`working-tree-encoding` 或内容 filter 转换。CRLF 文件只有在 HEAD blob 本身使用一致 CRLF、工作区原始字节与 blob 完全相同且补丁保持该换行风格时受支持；不能依赖 checkout 转换制造 CRLF 工作树。

#### `RuntimeCompatibilityCheckV1`

以下行为只能在 `RUNNING(BASELINE)` 的固定无网络、无宿主服务、候选树只读容器中验证，不能由 `PREFLIGHT` 假装静态证明：

- 两次 pytest collect-only 的完整 node ID 集合稳定；
- 完整基线和独立目标复跑可在没有网络、宿主服务、数据库守护进程或未声明本地服务时完成；
- 项目不依赖 `.git`、提交历史、标签或 VCS 动态版本才能启动检查；
- pytest、Ruff 和 Mypy 不要求写入项目树，临时文件和缓存只进入 tmpfs；
- pytest 报告以及 Ruff/Mypy 输出满足 §4.5 的完整解析合同。

    RuntimeProfileViolationKind =
      EXTERNAL_SERVICE_REQUIRED
      | VCS_RUNTIME_DEPENDENCY
      | PROJECT_TREE_WRITE
      | COLLECTION_UNSTABLE
      | REPORT_INCOMPLETE
      | CHECK_ENVIRONMENT_ERROR

    RuntimeCompatibilityResult =
      COMPATIBLE {
        reference_profile_digest
        evidence_digest
      }
      | BASELINE_BLOCKED {
        reason: RUNTIME_PROFILE_VIOLATION
        violation_kind
        evidence_refs[]
      }

动态不兼容返回上述 `BASELINE_BLOCKED`，不得改写为静态 `UNSUPPORTED_PROJECT`。该结果只证明固定测试与检查在本次 reference profile 下的可观察兼容性，不宣称发现未执行代码中的潜在依赖。

### 1.4.2 受保护验收与仓库策略工件

下列路径或类别在基线建立后不得由候选创建、修改、删除或重命名：

- `tests/**`；
- 根目录 `pyproject.toml`、`requirements.lock`；
- 任意 `conftest.py`、`sitecustomize.py`、`usercustomize.py`；
- `pytest.ini`、`tox.ini`、`setup.cfg`、`mypy.ini`、`.ruff.toml`、`ruff.toml`；
- `poetry.lock`、`uv.lock`、`pdm.lock`、`requirements*.txt`；
- `.gitignore`、`.gitattributes`、`.gitmodules`；
- 适配器识别出的其他会改变 pytest 收集、解释器启动、依赖解析、Ruff 或 Mypy 行为的入口。

Profile 正常形态只使用 `pyproject.toml` 和 `requirements.lock`；出现其他 pytest、Ruff、Mypy、解释器启动或依赖解析配置入口时，适配器必须返回 `UNSUPPORTED_PROJECT`。保护集合必须由代码中的单一版本化表生成，不能由仓库文本放宽。

### 1.4.3 敏感路径与文件系统对象

以下 tracked 路径命中时，准入阶段直接拒绝整个运行；它们不能仅通过“禁止读取”留在快照或容器中：

- 任一路径段为 `.git`、`.ssh`、`.aws`、`.azure`、`.gnupg`、`.kube`；
- 文件名为 `.env` 或匹配 `.env.*`；
- 常见私钥或凭据文件，如 `id_rsa`、`id_ed25519`、`*.pem`、`*.key`、`*.p12`、`*.pfx`、`credentials.json`、`secrets.*`；
- 内建 `SensitivePathPolicyV1` 追加的保留路径。

所有 tracked 对象必须是单链接普通文件或目录。符号链接、junction/reparse point、Alternate Data Stream、设备路径、UNC、盘符相对路径、保留设备名、Windows 大小写或 Unicode 折叠后路径碰撞，以及 link count 大于 1 的普通文件均以 `UNSUPPORTED_FILESYSTEM_OBJECT` 拒绝。

### 1.4.4 仓库和候选硬上限

- tracked 文件最多 5,000 个；tracked 原始字节总量最多 128 MiB；单 tracked 文件最多 4 MiB。
- 可编辑单文件最多 128 KiB。
- 当前候选相对 `SnapshotTree` 的**累计净差异**最多涉及 3 个文件，其中最多 1 个新文件。
- 当前候选规范 `FinalDiff` 的新增与替换文本总量最多 128 KiB。
- 规范相对路径最多 240 个字符，单路径段最多 100 个字符。
- 执行副本与容器临时数据合计不得超过 512 MiB。
- 新文件在冻结的 Git ignore 规则下必须为非忽略文件。

限制作用于当前候选的累计净差异，而不是单次 `ApplyCandidatePatchAction`，因此不能通过多个小动作绕过。

### 1.4.5 `DockerExecutionProfileV1`

正式检查和 Agent 请求的检查都使用 `ReferenceProfileManifestV1.docker_image_digest` 指定的同一个锁定镜像，并满足：

- `--network none`；非 root 用户；只读容器根文件系统；`cap-drop=ALL`；不挂载 Docker socket；
- 候选项目树挂载到 `/workspace` 且为只读；权威工作区、控制面数据库、凭据和事务备份不得挂载；
- `/tmp` 与工具缓存目录使用有界 tmpfs；Python bytecode、pytest cache、Ruff cache 和 Mypy cache 不写入项目树；
- 上限为 2 CPU、2 GiB 内存、256 PIDs、256 MiB tmpfs；单检查输出最多 4 MiB；
- 环境白名单至少固定 `PYTHONHASHSEED=0`、`TZ=UTC`、`LANG=C.UTF-8`、`LC_ALL=C.UTF-8`、`PYTHONDONTWRITEBYTECODE=1`，并禁用 pytest 插件自动加载；
- 每项检查使用全新容器和全新物化候选树，不共享 cache、字节码或运行时文件。

若参考项目无法在只读项目树下运行，它不属于 v1 支持画像；不得为兼容该项目把候选挂载改为可写。

## 1.5 v1 目标

- 自行实现顺序 Agent 主循环和可注入 LLM 抽象。
- 提供受路径围栏约束的 list、read、literal search、apply patch、run check 和 propose completion 动作。
- 用确定性代码实现 `ALLOW / ASK / DENY`、一次性动作批准和硬拒绝。
- 用运行级 `DisclosureGrant` 与逐请求 `DisclosureAuthorizationRecord` 控制真实 LLM 外发。
- 用 `ValidationManifestV1` 保护测试、检查配置、执行环境和正式验证条件。
- 将 pytest、Ruff、Mypy 结果转换为结构化反馈并驱动下一轮动作。
- 在用户审查精确 diff 后写回干净权威工作区，完成写后核对并提供最小恢复入口。
- 提供安全凭据管理、有限仓库记忆、本地 WebUI、离线 Mock 测试和可访问的公网 Mock Demo。

## 1.6 非目标

- 生产级通用 Coding Agent 或任意仓库兼容。
- 自然语言缺陷生成复现测试、`ValidationManifestV2` 或测试生成审批。
- 多 Agent、并行 turn、分布式任务、供应商调用对账或自动重发。
- 普通 Agent turn 的跨进程恢复。
- 通用 quarantine allocator、分布式 reconciliation 或多层 cleanup 状态机。
- 自动 commit、push、PR、依赖安装、镜像构建或对外发布。
- 识别所有秘密格式、消除所有提示注入或对恶意宿主管理员提供隔离。
- 删除、重命名、二进制修改、文件模式变更或超过 3 文件的持久化事务。

# 2. 用户故事

## 2.1 US-01 配置并安全启动运行

作为受支持仓库的开发者，我希望先创建一个可见的准备中运行，再由系统执行静态预检和隔离的运行时兼容性验证，以便在任何模型调用或持久修改前发现不支持、不兼容或不安全的条件。

验收结果：

- 无效请求 Schema 在创建运行前被拒绝，不产生 `run_id`。
- 有效请求创建 `CREATED` 运行并冻结配置；用户能看到工作区、规范目标集合、reference/Docker/LLM profile digest 和 `RunLimitsV1` 摘要。
- 启动后进入 `RUNNING(PREFLIGHT)`；脏仓库、不支持的 Git/项目画像、危险文件对象、未解决恢复、缺失 Docker profile 或凭据会使该运行进入 `STOPPED`。
- 被拒绝的预检不调用 LLM、不运行项目代码、不安装依赖、不构建镜像、不修改仓库。
- 预检只验证静态事实；项目代码仅在无网络、候选树只读的 `BASELINE` 中运行，动态不兼容以结构化 `BASELINE_BLOCKED` 停止。

## 2.2 US-02 安全管理真实 LLM 凭据

作为使用真实 LLM 的开发者，我希望安全录入、查看状态、更新和清除 API Key，以便不把凭据写入仓库、命令历史、日志或公网 Demo。

验收结果：

- 首次真实调用前提供隐藏输入。
- 状态查询只返回已配置/未配置、供应商和更新时间，不返回秘密。
- 更新和清除给出明确成功或失败结果。
- 存储后端必须被验证为 Windows Credential Manager；不允许静默退化到明文或文件后端。
- 清除后新的真实调用必须停止，直到重新配置。

## 2.3 US-03 修复已有稳定失败

作为已有失败测试的开发者，我希望 Agent 在隔离候选树中根据客观检查反馈迭代修复，以便获得不削弱既有验收条件的候选 diff。

验收结果：

- 两次 collect-only 得到相同完整 node ID 集合；所有目标存在。
- 每个目标都在全量基线和独立目标复跑中稳定产生相同 `CALL/FAIL` 和 `FailureFingerprintV1.digest`。
- 非目标测试全部通过，Ruff 和 Mypy 通过，不存在 skip、xfail、xpass、deselect、未运行或环境错误。
- 候选补丁不能修改受保护测试或检查配置。
- 检查失败形成结构化反馈，Mock LLM 可据此在下一轮改变动作。
- 只有满足正式成功谓词的候选才能进入最终审查。

## 2.4 US-04 控制外部数据披露

作为使用真实 LLM 的开发者，我希望为当前运行创建一个明确范围的披露授权，并逐请求查看实际外发记录，以便本地读取权限不会被自动解释为外发权限，同时避免每轮都重复点击相同授权。

验收结果：

- 首次真实请求前，用户看到冻结 LLM profile、供应商、模型、允许的来源路径/类别、`NO_CONTENT_REDACTION_V1` 的明确含义、累计字节预算和有效期，并可批准或拒绝 `DisclosureGrant`。
- 用户拒绝或没有有效 Grant 时不得调用真实适配器。
- Grant 只对当前运行有效；LLM profile、来源范围、数据类别、redaction profile、累计预算或有效期变化时，在总墙钟仍有正等待区间时重新进入精确绑定的 `WAITING_USER`。
- 在有效 Grant 范围内，每个请求由控制面自动创建绑定精确请求摘要、实际来源和字节数的 `DisclosureAuthorizationRecord`，不要求用户逐请求点击。
- 请求摘要变化本身不会使 Grant 失效，但每个精确请求都必须有独立授权记录。
- 审计只保存摘要和元数据，不保存完整请求、完整响应或凭据。

## 2.5 US-05 依赖确定性护栏和一次性动作审批

作为监督 Agent 的用户，我希望硬拒绝动作始终被阻止，而最终写回批准只执行一次，以便权限不能由模型、仓库文本、披露 Grant 或旧批准扩大。

验收结果：

- `DENY` 不可被模型输出、配置、`DisclosureGrant` 或任何批准覆盖。
- `ASK` 展示完整动作摘要、理由、绑定上下文和有效期。
- 拒绝、过期、上下文变化或重复消费均不执行动作。
- `FinalWritebackApproval` 只被精确绑定的最终写回原子消费一次。
- `FinalWritebackApproval` 与 `DisclosureGrant` 是独立类型，不能互相授权。

## 2.6 US-06 审查、持久化并恢复已验证 diff

作为开发者，我希望在原仓库发生修改前查看精确 diff 和验证证据，并在写回中断后使用明确恢复入口，以便写回内容与我批准的内容一致，且不确定状态不会被伪装成成功。

验收结果：

- 用户拒绝时权威工作区保持不变。
- 候选、Manifest、验证证据、策略或工作区前映像变化使批准失效。
- 写回不自动执行 `git add` 或 commit。
- 写后核对失败不得报告成功。
- 每个路径以 `PersistencePathRecord` 记录 `PRESENT/ABSENT` 前映像和可滞后的持久进度；恢复必须以实际字节和对象身份为准。
- 未解决事务阻止同一工作区新运行；用户不能通过“忽略”绕过。
- `vespercode recover --workspace <path>` 或等价 WebUI 恢复页只产生 `COMMITTED`、`ROLLED_BACK` 或 `UNRESOLVED` 三种结果。

## 2.7 US-07 检查和清除仓库记忆

作为重复维护同一参考仓库的用户，我希望查看、使用和清除仓库级记忆，以便获得有限连续性而不让模型随意写入记忆或让旧信息成为权限来源。

验收结果：

- 记忆按规范化工作区身份隔离。
- 用户能查看类型、来源、摘要和更新时间，并能清除。
- `PROJECT_CONVENTION` 与 `USER_DECISION` 只由用户创建或确认；`RUN_SUMMARY` 与 `KNOWN_FAILURE` 只由控制面从结构化事实生成。
- 模型没有通用 `remember(text)` 工具。
- 记忆不保存完整源码、完整工具输出、凭据或权限；当前仓库和检查证据始终优先。

## 2.8 US-08 理解状态和审计证据

作为监督运行的用户，我希望看到准备中、预检、运行中、等待决定、恢复阻塞和已结束状态，以便区分模型建议、检查结果和正式成功。

验收结果：

- `CREATED` 显示为准备中，`RUNNING(PREFLIGHT)` 显示为预检，其他 `RUNNING` phase 显示为运行中。
- 测试失败、错误、超时、skip、xfail、xpass、deselect 和未运行不得显示为通过。
- LLM 的 completion 建议只能请求正式验证，不能直接触发 `SUCCEEDED`。
- 只有持久化协调器在正式验证、最终批准、写回和写后核对全部完成后才能发布 `SUCCEEDED`。
- 停止、恢复阻塞和成功均显示对应的结构化证据。

## 2.9 US-09 运行公网 Mock Demo

作为评审者，我希望无需仓库或真实凭据即可运行固定 Demo，以便重复观察危险动作拦截、失败反馈修正和 Manifest 防篡改。

验收结果：

- Demo 只使用内置场景、Mock LLM 和模拟执行器。
- 页面持续显示模拟运行，不得展示为正式修复成功。
- 相同场景版本、输入和用户选择产生相同关键状态与动作序列。
- Demo 使用独立 `DemoRunStatus`，不进入正式 `RunStatus.SUCCEEDED`。
- Demo 不注册本地文件、真实凭据、Docker 或真实 LLM 能力；模拟用户选择只形成 `DemoDecision`，不得形成正式批准或披露授权。

## 2.10 INVEST 检查

| 故事 | I / N / V / E / S / T 结论 |
|---|---|
| US-01 | 独立验证请求创建与预检；边界和拒绝时点明确 |
| US-02 | 独立验证凭据生命周期与后端校验；界面细节可协商 |
| US-03 | 以预置失败 fixture 独立验收；实现任务在 PLAN 中继续拆分 |
| US-04 | 独立验证运行级 Grant 与逐请求记录；真实网络以 stub adapter 测试 |
| US-05 | 直接构造动作即可离线验证决策、批准和类型隔离 |
| US-06 | 以固定候选、故障注入和工作区前映像独立验证持久化与恢复 |
| US-07 | 以临时数据库独立验证来源权限、隔离、读取和清除 |
| US-08 | 以预置运行记录独立验证状态和证据展示 |
| US-09 | 以内置脚本独立、确定性、可重复验收 |

# 3. 领域与机制设计

## 3.1 Coding 领域的四类机制

| 类别 | v1 设计 | 确定性代码机制 |
|---|---|---|
| 动作/工具 | list、分段 read、literal search、严格 patch、封闭 check、propose completion | 严格动作 Schema、工具注册表、路径解析器、补丁引擎、受控适配器 |
| 客观反馈 | pytest、Ruff、Mypy、Schema/策略拒绝、正式验证 | 机器可读结果解析器、失败分类器、`FeedbackRecord` 和下一轮投影 |
| 危险动作 | 越界路径、敏感路径、验收篡改、任意命令、外发、权威写回 | `PolicyEngine`、`ALLOW/ASK/DENY`、`FinalWritebackApproval`、`DisclosureGrant` |
| 记忆 | 项目约定、用户决定、运行摘要、已知失败 | 仓库隔离存储、写入权限、有限检索、来源标注、用户清除 |

## 3.2 六个 Harness 维度

| 维度 | v1 最低实现 | 深度 |
|---|---|---|
| 决策 | 顺序主循环、确定性上下文装配、一次 LLM 调用、动作解析、停止谓词 | 最低闭环 |
| 工具 | 六种结构化动作和统一分发 | 最低闭环 |
| 记忆 | SQLite 仓库级摘要存取、来源权限、检查和清除 | 最低闭环 |
| 治理 | 路径围栏、Manifest、披露门、一次性批准、受控写回与恢复阻断 | **主要贡献** |
| 反馈 | 三类检查结果、拒绝原因和下一轮结构化反馈 | 最低闭环 |
| 配置 | 严格 Schema、冻结快照、预算和不可放宽硬规则 | 最低闭环 |

## 3.3 主贡献的评价问题

1. 构造任意模型动作时，模型能否越过工作区、敏感路径或受保护工件？
2. 用户批准的动作或 diff 是否就是最终执行对象，且批准能否复用？
3. 模型能否通过修改测试、配置、执行命令或成功条件获得表面成功？
4. 本地可读数据能否在没有有效 Grant 和逐请求记录时进入真实适配器？

四项都必须在替换真实 LLM 为 Mock/Stub 后由离线单元测试回答。

## 3.4 信任边界

- **可信控制面：** 主循环、配置解析、路径解析、策略、审批、披露授权、Manifest、检查解析、成功/停止判定、持久化和恢复判定。
- **不可信输入：** 用户仓库、代码注释、测试数据、工具输出、模型输出、记忆正文和 WebUI 客户端请求。
- **受限执行面：** 无网络 Docker 容器；候选树只读挂载，临时写入仅进入 tmpfs。
- **外部边界：** 真实 LLM 供应商；本地读取授权不等于披露授权。
- **权威工作区：** 只允许持久化模块在正式验证和最终批准后写入。
- **恢复边界：** 只有持久化事务可以进入 `RECOVERY_REQUIRED`；普通 LLM、工具和检查失败不得升级为通用恢复状态机。

# 4. 功能规约

## 4.1 FR-ADM：请求校验、运行创建与预检

### 输入与接口

    ValidateRunRequestV1 {
      schema_version: 1
      workspace_path
      target_test_ids: 1..20 unique exact pytest node IDs
      llm_profile_id
      docker_profile_id: "python-src-py312-v1"
      limits: RunLimitsV1
    }

    RunLimitsV1 {
      max_turns: 1..20
      max_llm_calls: 1..20
      max_run_wall_clock_seconds: 1..900
      user_wait_timeout_seconds: 1..300
      tool_timeout_seconds: 1..60
      target_check_timeout_seconds: 1..120
      formal_validation_timeout_seconds: 1..600
    }

    LLMProfileManifestV1 =
      MockLLMProfileV1 {
        schema_version: 1
        profile_id: "mock-deterministic-v1"
        mode: MOCK
        adapter_version
        script_id
        script_digest
        digest
      }
      | OpenAILLMProfileV1 {
        schema_version: 1
        profile_id: "openai-single-turn-v1"
        mode: OPENAI
        provider: "openai"
        model
        adapter_version
        request_serializer_version
        fixed_parameters
        redaction_profile_id: "NO_CONTENT_REDACTION_V1"
        digest
      }

    validate_request(request) -> ValidatedRunRequest | CONFIG_INVALID
    create_run(validated_request) -> Run(CREATED, frozen_config)
    start_run(run_id) -> RUNNING(PREFLIGHT) | STOPPED

### 行为

1. `validate_request` 使用拒绝未知字段的版本化 Schema，只做语法、类型、枚举和基础值域校验；全部字段必填，解析器不得静默补默认值。单个 target node ID 必须为非空且不超过 1024 个 UTF-8 字节；重复值返回 `CONFIG_INVALID`，规范请求按 §0.1 排序后绑定。
2. `llm_profile_id` 和 `docker_profile_id` 必须解析到发布包内置的只读 manifest。精确模型、适配器、请求序列化器、固定参数、Mock 脚本、工具版本和镜像摘要由 manifest 决定，不能由请求自由覆盖。
3. `RunLimitsV1` 每个值只能等于或低于内建硬上限；WebUI 可以预填上述最大值，但 API 请求仍必须显式提交。子超时始终受剩余总墙钟约束。
4. `create_run` 冻结规范 target 集合、`RunLimitsV1`、LLM profile digest、`ReferenceProfileManifestV1` digest 和 Docker profile digest，形成不含秘密的 `RunConfigSnapshot` 并创建 `CREATED`。
5. `start_run` 以原子状态转换进入 `RUNNING(PREFLIGHT)`，同时冻结 `started_at` 和 `run_deadline = started_at + max_run_wall_clock_seconds`，然后执行工作区、Git、静态项目画像、Docker、凭据和恢复阻断检查；不得在预检运行项目代码。
6. 规范化工作区身份后，使用以该身份摘要为键的 Windows named mutex 或等价 Win32 跨进程锁；仅“当前进程内锁”不合格。
7. 若存在未解决 `PersistenceTransaction`，拒绝新运行并指向恢复入口。
8. 验证有效 HEAD、工作区字节与 HEAD blob 一致、受支持仓库策略、单链接普通文件、敏感路径规则和 `StaticProjectProfileCheckV1`。
9. 验证 `ReferenceProfileManifestV1`、Docker profile、镜像摘要和能力参数满足 §1.4.1 与 §1.4.5。
10. 只有选中的 LLM profile 为 `OpenAILLMProfileV1` 时才检查凭据状态和安全后端；检查不读取或记录秘密。
11. 预检通过后进入 `RUNNING(BASELINE)`，由 §4.5 执行 `RuntimeCompatibilityCheckV1`；静态预检失败和动态基线阻断必须使用不同证据与错误语义。

### 输出

- 请求无效：`CONFIG_INVALID`，无 `run_id`。
- 请求有效：`RunCreated(run_id, config_snapshot_id, status=CREATED)`；快照绑定 LLM、reference 和 Docker profile digest。
- 预检：`AdmissionResult = ACCEPTED | REJECTED(error)`，并形成相应生命周期结果。

### 错误

`CONFIG_INVALID`、`WORKTREE_DIRTY`、`UNSUPPORTED_REPOSITORY`、`UNSUPPORTED_PROJECT`、`UNSUPPORTED_FILESYSTEM_OBJECT`、`SENSITIVE_TRACKED_FILE`、`EXECUTION_PROFILE_UNAVAILABLE`、`CREDENTIAL_MISSING`、`CREDENTIAL_BACKEND_UNSAFE`、`RECOVERY_BLOCKS_NEW_RUN`、`WORKSPACE_LOCKED`。

所有预检拒绝发生在 LLM 调用、项目执行和权威工作区修改前。

### 确定性测试

- 无效 Schema 不产生 Run。
- 有效请求先产生 `CREATED`，再进入 `PREFLIGHT`。
- 重复、超过 20 个、超长 target ID，未知 profile、遗漏限制字段和放宽硬上限均为 `CONFIG_INVALID`；target 输入排列不同但集合相同时形成相同规范摘要。
- 为每种预检拒绝使用固定仓库或 stub；断言 LLM、Docker 和持久化调用次数均为零。
- 预检不得调用 pytest、Ruff、Mypy 或导入目标项目；运行时兼容性只在 `BASELINE` 检查。
- 两个进程竞争同一规范工作区时最多一个获得 lease。

## 4.2 FR-LOOP：主循环、动作协议、上下文和停止

### 4.2.1 核心接口与状态

    LLMAdapter.generate(PreparedModelRequest) -> ModelResponse
    ActionParser.parse(ModelResponse) -> AgentAction | ParseError
    ToolDispatcher.dispatch(AgentAction, RunContext) -> ActionResult
    StopEvaluator.evaluate(RunState, Evidence) -> Continue | Validate | Stop

正式运行状态：

    RunStatus = CREATED | RUNNING | WAITING_USER | RECOVERY_REQUIRED | SUCCEEDED | STOPPED
    RunPhase  = PREFLIGHT | BASELINE | AGENT_LOOP | FORMAL_VALIDATION | PERSISTENCE

公网 Demo 使用独立状态：

    DemoRunStatus = DEMO_CREATED | DEMO_RUNNING | DEMO_WAITING_USER | DEMO_COMPLETED | DEMO_FAILED

`DEMO_COMPLETED` 不是正式 `RunStatus`，不能生成 `VerifiedCandidate`、`FinalWritebackApproval`、`DisclosureGrant` 或权威工作区写入。

### 4.2.2 封闭动作 Schema

所有模型响应必须是一个 JSON 对象，且只包含一个动作；动作外自由文本、未知字段和多个动作均为无效输出。公共字段和具体动作字段位于同一个拒绝未知字段的对象中，所有下列字段均为必填字段，不应用解析器默认值补齐。

公共信封：

    ActionEnvelope {
      schema_version: 1
      action_id: non-empty UTF-8 string, <=128 bytes
      action_type: closed literal
    }

封闭联合及字段：

    ListFilesAction = ActionEnvelope & {
      action_type: "list_files"
      root: relative_path
      recursive: bool
      max_entries: 1..500
    }

    ReadFileAction = ActionEnvelope & {
      action_type: "read_file"
      path: relative_path
      start_line: >=1
      line_count: 1..400
      max_bytes: 1..32768
    }

    SearchTextAction = ActionEnvelope & {
      action_type: "search_text"
      query: literal UTF-8 string, 1..256 bytes
      roots[]: 1..8 relative paths
      case_sensitive: bool
      context_lines: 0..2
      max_results: 1..100
    }

    ApplyCandidatePatchAction = ActionEnvelope & {
      action_type: "apply_candidate_patch"
      base_candidate_digest
      patch_format: "UNIFIED_DIFF_V1"
      patch_text: UTF-8, <=128 KiB
    }

    RunCheckAction = ActionEnvelope & {
      action_type: "run_check"
      check_plan_id: TARGET_TESTS | FULL_PYTEST | RUFF | MYPY
    }

    ProposeCompletionAction = ActionEnvelope & {
      action_type: "propose_completion"
      candidate_digest
      rationale_summary: UTF-8, <=2048 bytes
    }

`RunCheckAction` 不含 executable、argv、工作目录、环境变量或命令文本；这些全部由可信 `PythonProjectAdapterV1` 根据冻结 profile 生成。模型没有任意 Shell 或任意命令能力。

`ListFilesAction`、`ReadFileAction` 和 `SearchTextAction` 的结果按规范相对路径、行号稳定排序。Search v1 只支持字面量，不支持正则表达式。路径数组不得为空、重复或在 Windows 折叠规则下形成别名。

动作结果使用公共信封：

    ActionResult {
      action_id
      status: SUCCEEDED | REJECTED | FAILED
      result_type
      payload_ref?
      error?
    }

各动作的规范结果为：

- `ListFilesResult`：`entries[{path, kind, size_bytes?, text_profile?}]` 与 `truncated`；目录优先、随后按路径排序。
- `ReadFileResult`：`path`、`file_digest`、实际 `start_line/end_line`、`eof` 和有界正文。`start_line` 超过文件末行返回 `READ_RANGE_OUT_OF_BOUNDS`；请求范围越过 EOF 时返回已有内容并令 `eof=true`。
- `SearchTextResult`：`matches[{path, line, column, excerpt}]`、`truncated` 和 `skipped_non_text_count`；只搜索受支持文本文件。
- `ApplyCandidatePatchResult`：新 `candidate_digest`、规范 `final_diff_digest`、累计文件数和累计字节数。
- `RunCheckResult`：对应 `CheckResult` 引用；原始输出不直接内嵌进模型上下文。
- `ProposeCompletionResult`：`VALIDATION_REQUESTED` 或结构化拒绝；它不是成功记录。

面向模型的单个结果正文统一不超过 32 KiB。允许截断的 list/read/search 结果必须返回 `truncated=true`、实际范围和稳定继续参数；不允许截断的 patch、check 和 completion 结果超限时返回稳定错误，不能把部分结果伪装成完整结果。动作已成功执行但客观检查为 `FAIL` 时，`ActionResult.status=SUCCEEDED` 且 `CheckResult.status=FAIL`；只有动作未能按合同完成时才使用 `FAILED`。

### 4.2.3 动作—phase 矩阵

| Phase / 状态 | 模型动作 |
|---|---|
| `RUNNING(AGENT_LOOP)` | 六种动作；`RunCheckAction` 可选择四个冻结计划，但受剩余运行和检查预算约束 |
| `RUNNING(PREFLIGHT)`、`RUNNING(BASELINE)` | 无；由可信协调器执行 |
| `RUNNING(FORMAL_VALIDATION)` | 无；由可信协调器执行完整冻结计划 |
| `WAITING_USER`、`RUNNING(PERSISTENCE)`、`RECOVERY_REQUIRED` | 无 |

任何不在矩阵中的模型动作返回 `ACTION_NOT_ALLOWED_IN_PHASE`，不得进入策略批准。正式验证不得通过伪造 `RunCheckAction` 启动，也不消费 Agent turn。

### 4.2.4 `ContextProjection`

每轮上下文由控制面确定性组装，顺序固定为：

1. Harness 协议和动作 Schema；
2. 冻结任务、目标测试和运行预算；
3. 当前候选摘要、累计 `FinalDiff` 统计和最近动作结果；
4. 未消费反馈，按严重级别、生成时间和稳定 ID 排序；
5. 本次选中的仓库记忆；
6. 经工具显式读取的有界文件片段和搜索结果。

裁剪顺序固定为：先删除最旧记忆，再删除最旧成功动作摘要，再缩减非最近文件片段；Harness 协议、目标测试、当前候选绑定和最近失败反馈不得被裁掉。规范压缩后强制内容仍超过 64 KiB 时，以 `CONTEXT_BUDGET_EXCEEDED` 停止，不得静默截断成语义无效请求。

投影必须记录来源类别、相对路径、字节数、裁剪决定和按 §0.1 计算的规范摘要，以供披露授权和测试重放。

### 4.2.5 主循环行为

1. 同一运行任一时刻最多一个活动 `AgentTurn`。
2. 每轮基于当前候选、有限记忆、未消费反馈和预算生成一个 `ContextProjection`。
3. 每轮恰好调用一次 LLM，随后严格解析一个动作。
4. 动作依次经过 Schema、候选绑定、路径、阶段和策略校验，再分发。
5. 结果发布为结构化 `ActionResult`；下一 turn 原子绑定并消费选中的 `feedback_refs`。
6. `ProposeCompletionAction` 只请求进入 `FORMAL_VALIDATION`，不能声明成功。
7. `StopEvaluator` 只负责 `Continue | Validate | Stop`；它不能发布 `SUCCEEDED`。正式成功只能由 `PersistenceCoordinator` 在 §4.6 的全部条件满足后发布。

### 4.2.6 取消、预算与无进展

- 用户通过 `CancelRun` 提交取消请求。动作边界、等待用户状态以及持久化首次替换前是安全点。
- 若持久化已发生首个文件替换，取消保持待处理，必须先完成事务判定或进入恢复，不能中断并假定回滚成功。
- 相同候选上，相同规范动作得到相同结果连续 3 次时，以 `REPEATED_ACTION_LIMIT` 停止。
- 连续 6 个 turn 没有产生 `ProgressMarker` 时，以 `NO_PROGRESS_LIMIT` 停止。
- `ProgressMarker` 只包括：候选树摘要变化；当前候选产生此前未见的语义检查结果；进入正式验证。语义检查结果按 §0.1 计算，排除时间、随机 ID、容器 ID 和审计序号；单纯重复读取、搜索、相同失败或只改变易变字段不算进展。
- 冻结 `RunLimitsV1` 的 turn、LLM call 和总墙钟是整个正式运行的实际上限，且不得超过 §5.1 的内建硬上限；单动作、目标检查、用户等待和正式验证超时只是子上限，不能扩大总上限。Schema 无效、模型输出无效和 LLM 调用失败均消耗已开始的 turn/call；在预算不足以开始下一动作、等待或检查时必须于副作用前停止。

### 4.2.7 生命周期

    WaitKind = DISCLOSURE_GRANT | FINAL_WRITEBACK

    WaitContext {
      wait_id
      run_id
      wait_kind
      source_phase: AGENT_LOOP | FORMAL_VALIDATION
      subject_digest
      created_at
      expires_at
    }

- 有效创建：无 Run → `CREATED`。
- `CREATED` → `RUNNING(PREFLIGHT)` 或 `STOPPED`。
- `RUNNING(PREFLIGHT)` → `RUNNING(BASELINE)` 或 `STOPPED`。
- `RUNNING(BASELINE)` → `RUNNING(AGENT_LOOP)` 或 `STOPPED`。
- `RUNNING(AGENT_LOOP)` 可继续、以 `DISCLOSURE_GRANT` 进入 `WAITING_USER`、进入 `FORMAL_VALIDATION` 或 `STOPPED`。
- `RUNNING(FORMAL_VALIDATION)` 可回到新的 `AGENT_LOOP`、以 `FINAL_WRITEBACK` 进入 `WAITING_USER` 或 `STOPPED`。
- `DISCLOSURE_GRANT` 只能绑定 `source_phase=AGENT_LOOP`；`FINAL_WRITEBACK` 只能绑定 `source_phase=FORMAL_VALIDATION`。其他 wait kind/phase 组合在创建前拒绝。
- `DISCLOSURE_GRANT` 的 `subject_digest` 是所请求 LLM profile、来源范围/类别、redaction profile、累计预算和有效期的规范摘要；`FINAL_WRITEBACK` 的 `subject_digest` 是 §4.4.2 全部批准绑定的规范摘要。
- 用户决定必须同时绑定 `wait_id`、`run_id`、`wait_kind` 和 `subject_digest`。`expires_at = min(created_at + user_wait_timeout_seconds, run_deadline)`；若创建时已无正的等待区间，则在创建 `WaitContext` 前以总墙钟预算耗尽停止。
- `DISCLOSURE_GRANT` 等待被精确批准后回到来源 `AGENT_LOOP` 的新执行入口；`FINAL_WRITEBACK` 等待被精确批准后进入 `RUNNING(PERSISTENCE)`。
- 等待被拒绝、过期或取消时进入带稳定原因的 `STOPPED`。`WaitKind`、subject 或绑定变化使旧决定失效；只有来源 phase 重新产生新的 subject 后才可创建新等待。
- `WAITING_USER` 时间计入 `max_run_wall_clock_seconds`，但不消耗 Agent turn 或 LLM call。披露范围不足、累计预算不足、Grant 过期或撤销时，只要仍有正的等待区间就必须创建新的 `DISCLOSURE_GRANT` 等待；不得在“等待或停止”之间自由选择。
- 最终候选、Manifest 或验证证据变化时必须重新进入适用的 `AGENT_LOOP` 或 `FORMAL_VALIDATION`；工作区前映像、配置、策略、适配器或执行 profile 变化时停止，不得只创建新的最终批准。
- `RUNNING(PERSISTENCE)` 可进入 `SUCCEEDED`、`STOPPED` 或 `RECOVERY_REQUIRED`。
- `RECOVERY_REQUIRED` 只能由 §4.6 的恢复结果进入 `SUCCEEDED`、`STOPPED` 或保持不变。
- 非持久化阶段和两类 `WAITING_USER` 进程重启统一停止为 `PROCESS_RESTARTED_DURING_RUN`，不得恢复等待、turn 或重发 LLM 请求。

### 4.2.8 错误

- 模型输出无效：`MODEL_OUTPUT_INVALID`；连续两次无效则 `MODEL_OUTPUT_INVALID_LIMIT` 停止。
- 动作阶段不允许：`ACTION_NOT_ALLOWED_IN_PHASE`，形成反馈；硬 `DENY` 不进入审批。
- LLM 调用失败：`LLM_CALL_FAILED` 并停止；v1 不自动重试。
- 响应后控制面失败：`INTERNAL_ERROR` 并停止。
- 等待拒绝、过期和绑定变化分别使用 `WAIT_REJECTED`、`WAIT_EXPIRED`、`WAIT_STALE`。
- 预算、重复动作、无进展和取消使用各自稳定错误码。

### 确定性测试

脚本化 Mock LLM 依次返回读取、失败补丁、检查、修正补丁和 completion；断言动作顺序、上下文摘要、反馈消费、无进展谓词和停止结果完全可重复。

## 4.3 FR-WS：快照、路径、严格补丁和候选树

### 输入

已通过准入的 Git 工作区，以及符合 §4.2.2 的文件动作或 `ApplyCandidatePatchAction`。

### 行为

1. 从冻结 HEAD、经逐文件字节校验的工作区和仓库策略建立不可变 `SnapshotTree`。
2. `CandidateRevision` 从不可变父候选派生；不得原地修改 `SnapshotTree` 或权威工作区。
3. 所有 Agent 路径必须是使用 `/` 的规范相对路径；拒绝绝对路径、`..`、盘符、UNC、ADS、设备名、尾随点/空格和保留路径。
4. 文件访问在打开前后验证最终对象身份、授权根、reparse 状态和 link count；任一步不确定即拒绝。
5. 新文件必须位于允许源码根、未命中敏感/保护/保留路径，并在冻结 ignore 规则下为非忽略文件。

### `UNIFIED_DIFF_V1`

- patch 文档本身必须为无 BOM 的 UTF-8、使用 LF，并仅允许标准 `--- a/path`、`+++ b/path` 和 `@@ -old +new @@` hunk；新文件使用 `--- /dev/null`、`+++ b/path`。
- 禁止时间戳、rename/mode/binary 扩展头、`\ No newline at end of file`、删除文件和路径仅大小写变化。
- 每个 hunk 的旧范围、上下文行和删除行必须与 `base_candidate_digest` 指向的候选精确匹配。
- 不允许 fuzzy apply、自动 offset、自动冲突解决或“尽力应用”；任一 hunk 不匹配则整个动作无副作用失败。
- 现有文件保持 BOM、统一换行风格和末尾换行；新文件固定为 UTF-8、无 BOM、LF、末尾换行。
- `base_candidate_digest` 不等于当前候选时，以 `STALE_CANDIDATE` 拒绝。

每次动作后重新计算当前候选相对 `SnapshotTree` 的规范净差异并应用 §1.4.4 的累计限制。`FinalDiff` 定义为 `SnapshotTree → 最终 CandidateTree` 的规范树差异，不是历史 patch 文本的拼接。

### 输出

不可变 `SnapshotTree`、`CandidateRevision`、当前规范 `FinalDiff`，或一个无候选副作用的稳定错误。

### 错误

`PATH_INVALID`、`PATH_OUTSIDE_WORKSPACE`、`UNSUPPORTED_FILESYSTEM_OBJECT`、`SENSITIVE_PATH`、`PROTECTED_ARTIFACT_CHANGED`、`UNSUPPORTED_PATCH_OPERATION`、`PATCH_CONTEXT_MISMATCH`、`STALE_CANDIDATE`、`PATCH_LIMIT_EXCEEDED`、`TREE_INTEGRITY_FAILED`。

### 清理

执行副本删除前验证 UUID 根身份且不跟随链接。删除失败时记录精确残留路径、使该名称在当前进程生命周期内不可复用并停止当前运行；v1 不因此建立通用恢复状态机。持久化恢复所需工件不受普通清理影响。

### 确定性测试

构造绝对路径、父目录、ADS、设备名、symlink/reparse、hard link、敏感路径、陈旧候选、hunk 不匹配、多动作累计超限和 ignored 新文件；断言全部在文件访问或候选发布前被稳定拒绝。

## 4.4 FR-GOV：策略、动作批准与真实 LLM 披露

### 输入

规范化 `AgentAction`、当前运行/候选/Manifest/配置绑定、可选用户决定，以及真实请求的供应商、模型、来源和规范摘要。

### 4.4.1 动作策略

    PolicyEngine.evaluate(action, context) -> ALLOW | ASK | DENY

| 动作 | 默认决定 |
|---|---|
| 受限 list/read/literal search | ALLOW |
| 候选树内受支持补丁 | ALLOW |
| 选择预定义检查计划 | ALLOW |
| `ProposeCompletionAction` | ALLOW，但仅进入正式验证 |
| 最终权威写回 | ASK |
| 越界、敏感路径、任意命令、验收篡改、控制面修改 | DENY |

硬 `DENY` 列表由代码中的单一版本化策略定义。配置、提示、仓库文本、`DisclosureGrant` 和用户批准都不能改变 `DENY`。

### 4.4.2 `FinalWritebackApproval`

`FinalWritebackApproval` 只授权最终权威写回，不授权其他 `ASK`、本地工具、披露、Demo 决定或任何硬 `DENY`。最终持久化批准必须绑定：

- `run_id`、动作类型和规范动作摘要；
- 当前候选、`FinalDiff`、Manifest 和正式验证证据摘要；
- 工作区前映像；
- 配置、策略、适配器和执行 profile 摘要；
- 创建时间、到期时间和状态。

状态为 `PENDING | REJECTED | EXPIRED | CONSUMED`。只有当前 `PENDING` 且全部绑定仍匹配的批准可以在动作执行前通过一次原子更新变为 `CONSUMED`。消费失败不得执行动作；任何批准不得覆盖 `DENY`，也不得被转换为其他批准或授权类型。

### 4.4.3 `DisclosureGrant`

真实模式首次需要项目数据外发时，控制面展示并请求一个运行级 Grant：

    DisclosureGrant {
      run_id
      llm_profile_digest
      provider
      model
      allowed_source_paths[]
      allowed_source_categories[]
      redaction_profile_id: "NO_CONTENT_REDACTION_V1"
      cumulative_byte_budget
      consumed_bytes
      expires_at
      status: ACTIVE | REVOKED | EXPIRED | EXHAUSTED
    }

Grant 不绑定尚未形成的最终请求摘要，也不授权任何本地工具或持久化动作。`allowed_source_paths` 使用规范相对文件路径或目录前缀。供应商、模型和请求序列化方式来自冻结 `OpenAILLMProfileV1`，用户不能在 Grant 中改写。用户可以撤销；LLM profile、来源范围、数据类别、脱敏 profile、累计预算上限或有效期被修改，或者当前请求需要扩大这些范围时，必须创建新的等待和 Grant。正常的 `consumed_bytes` 增长不会使 Grant 失效。

`NO_CONTENT_REDACTION_V1` 不扫描、替换或声称识别用户源码中的任意秘密。凭据、会话令牌和其他控制面秘密必须在 `ContextProjection` 形成前通过类型和来源隔离保证不可进入；违反该不变量时失败关闭，不能把事后字符串替换当作补救。授权界面必须明确告知用户：被选择的项目正文将在规范裁剪后原样发送，敏感路径拒绝不等于通用秘密扫描。

### 4.4.4 逐请求授权记录

每次真实调用前：

1. 重新生成最终 `ContextProjection`，应用冻结的 `NO_CONTENT_REDACTION_V1` 并形成不可再扩张正文的 `PreparedModelRequest`；
2. 对实际发送的最终规范请求 UTF-8 字节计数，验证 LLM profile、全部实际来源、类别、redaction profile 应用结果和字节数均落在活动 Grant 内；
3. 在同一控制面事务中原子消费累计字节预算，并创建绑定精确请求的 `DisclosureAuthorizationRecord`；
4. 只有事务成功后，真实调用门才可把同一 `PreparedModelRequest` 和授权记录引用交给真实适配器；适配器不得追加项目正文、工具结果或记忆。

`PreparedModelRequest` 至少包含 LLM profile digest、provider、model、request serializer version、裁剪完成的消息、固定请求参数、实际来源元数据、redaction profile、规范字节数和按 §0.1 计算的 request digest。记录至少绑定：`grant_id`、LLM profile digest、provider、model、最终 request digest、实际来源路径/类别、规范字节数、redaction profile、创建时间。它证明该精确请求在调用前获得授权，不证明适配器被调用或供应商收到请求。适配器结果由独立 `LLMCallResult` 表示。

若请求摘要变化但仍在 Grant 范围和预算内，自动创建新的逐请求记录，不重新要求用户点击。超范围、预算不足、Grant 过期或撤销时严格按 §4.2.7 创建新的 `DISCLOSURE_GRANT` 等待；只有没有正的等待区间时才因总墙钟预算耗尽而停止。两种情况下真实适配器调用次数均为零。

预算消费表示一次真实发送尝试已经获准。事务提交后，即使进程在调用前崩溃、适配器返回错误或供应商是否收到请求无法证明，已消费字节也不退款；v1 不自动重发。`LLMCallResult` 必须区分 `NOT_ATTEMPTED | SUCCEEDED | FAILED | DELIVERY_UNKNOWN`，不得把授权记录显示为供应商已收到。

Mock 路线经过相同上下文裁剪、来源分类、Schema、策略和预算计算，但不读取凭据、不联网，也不创建真实披露 Grant/授权记录。

### 输出与错误

输出：`PolicyDecision`、`FinalWritebackApproval` 状态变化、`DisclosureGrant`、`DisclosureAuthorizationRecord`、`PreparedModelRequest` 或稳定拒绝。

错误：`ACTION_SCHEMA_INVALID`、`ACTION_DENIED`、`APPROVAL_REJECTED`、`APPROVAL_EXPIRED`、`APPROVAL_STALE`、`APPROVAL_ALREADY_CONSUMED`、`DISCLOSURE_GRANT_REQUIRED`、`DISCLOSURE_GRANT_REJECTED`、`DISCLOSURE_SCOPE_EXCEEDED`、`DISCLOSURE_BUDGET_EXCEEDED`、`DISCLOSURE_GRANT_EXPIRED`、`DISCLOSURE_GRANT_REVOKED`。

### 确定性测试

直接构造 `ALLOW`、`ASK`、`DENY`、批准竞态和 Grant 范围变化；断言硬拒绝不可覆盖，只有一个精确批准消费胜出，有效 Grant 内不同请求自动产生不同逐请求记录，未授权或超预算时真实适配器调用次数为零，失败/未知交付不退款且不能重用记录。

## 4.5 FR-VAL：Python 适配器、基线、检查、Manifest 和反馈

### 适配器边界

    ProjectAdapter {
      detect_static(snapshot, reference_manifest) -> StaticProjectProfileResult
      build_baseline_plan(static_profile, target_test_ids) -> CheckPlan
      evaluate_runtime_compatibility(baseline_evidence) -> RuntimeCompatibilityResult
      build_validation_plan(manifest, candidate) -> CheckPlan
      parse_check_result(raw_result) -> CheckResult
      protected_artifacts(static_profile) -> ProtectedArtifactSet
    }

`detect_static` 只能读取快照、Git 元数据和内置 manifest，不能执行项目代码。核心只理解 `CheckPlanId`、`CheckResult`、`TestIdentity`、`ProtectedArtifact`、`FailureFingerprintV1` 和 `ValidationManifestV1`。命令、argv、环境白名单和解析器属于 `PythonProjectAdapterV1`。

### `PytestEvidenceV1`

pytest 的权威输入是执行镜像内固定报告插件生成的完整 `PytestEvidenceV1`，至少包含：

- schema、插件版本、递增事件序号和正常结束标记；
- collect-only 或执行时的完整有序 node ID 集合；
- 每个 node ID 的 setup、call、teardown outcome、`wasxfail`、结构化异常字段和有界显示摘要；
- `SKIP`、`XFAIL`、`XPASS`、`DESELECTED`、collection/session/environment error 及其 `ErrorPhase`；
- pytest 退出码、事件数量和前序事件的完整性摘要。

缺少结束标记、事件序号断裂、重复或未知事件、报告截断、schema/插件版本不匹配、计划外 node ID、计划内 node ID 缺失，或事件摘要不一致时统一返回 `REPORTER_INVALID`。stdout/stderr 和 pytest 退出码不能补足或覆盖缺失的结构化事实。

Ruff 和 Mypy 必须分别使用由 profile 冻结的结构化或稳定格式及对应解析器。缺失、截断、未知诊断类别、工具/格式版本不匹配或解析器无法证明完整性时返回 `CHECK_ERROR`，不能仅按进程退出码判定 `PASS`。

### `FailureFingerprintV1` 与错误阶段

    ErrorPhase =
      COLLECTION | SETUP | CALL | TEARDOWN | ENVIRONMENT

    ProjectFrameSignatureV1 {
      relative_path
      function_name
      line_number
    }

    FailureFingerprintV1 {
      schema_version: 1
      node_id
      failure_phase: CALL
      exception_type
      normalized_message
      normalized_assertion_diff: UTF-8 | ABSENT
      project_frame_signatures[]
      digest
    }

只有完整 `PytestEvidenceV1` 中 outcome 为 `FAIL`、阶段为 `CALL` 且结构化异常字段齐全的目标才能产生指纹。collection、setup、teardown 和 environment error 使用 `TestStatus.ERROR + ErrorPhase`，不能伪装为目标失败。

规范化固定为：

1. node ID 使用 collect-only 返回的精确规范字符串；异常类型使用报告器给出的完整类型名。
2. 消息和断言差异统一为 LF；只把 Harness 已知的执行副本根、tmp 根、当前 run/container ID 和报告器结构化标记的运行时对象地址替换为固定占位符。
3. 项目栈帧只保留 `SnapshotTree` 内规范相对路径、函数名和行号，并保持调用顺序；pytest、标准库和 site-packages 帧不进入摘要。
4. 报告中的时间戳、耗时、事件序号和审计元数据不进入指纹。不得用宽泛正则删除用户消息中的任意数字、时间文本或十六进制值；无法安全规范化的易变正文必须导致 `TARGET_UNSTABLE`。
5. `normalized_message`、项目帧或适用的断言差异缺失、截断、解析失败时不能创建指纹；非断言异常必须显式记录 `normalized_assertion_diff=ABSENT`，不能省略字段。报告合同缺失返回 `REPORTER_INVALID`。

### 基线固定顺序

1. 在两个独立只读执行副本中分别运行 pytest collect-only，比较完整 node ID 集合；必须完全相同且非空。
2. 在第三个独立副本中运行一次完整 pytest，建立逐测试基线。
3. 在第四个独立副本中只运行目标集合；每个目标都必须与步骤 2 一致地在 `CALL` 阶段 `FAIL`，且 `FailureFingerprintV1.digest` 完全一致。
4. Ruff 和 Mypy 各在自己的全新副本/容器中运行一次。
5. 对步骤 1—4 的完整证据执行 `RuntimeCompatibilityCheckV1`；只能得到 `COMPATIBLE` 或 §1.4.1 定义的结构化 `BASELINE_BLOCKED`。

基线通过条件：

- 每个目标都存在并稳定产生相同 `CALL/FAIL` 指纹；任一目标 `PASS`、`ERROR`、缺失、未运行、无法指纹化或不稳定都拒绝整个 baseline。
- 非目标测试全部实际执行并 `PASS`。
- 不存在 `SKIP`、`XFAIL`、`XPASS`、`DESELECTED`、`NOT_RUN`、收集错误、setup/teardown 错误、环境错误或超时。
- Ruff 和 Mypy 均 `PASS`。
- `RuntimeCompatibilityResult` 为 `COMPATIBLE`。

基线成功后创建不可变 `ValidationManifestV1`，至少绑定：

- 完整 pytest node ID 集合、目标集合、逐测试状态、`ErrorPhase` 和目标 `FailureFingerprintV1`；
- §1.4.2 保护工件摘要；
- `ReferenceProfileManifestV1` digest、检查计划、适配器版本、Python/pytest/Ruff/Mypy/报告插件版本和 `PytestEvidenceV1` 完整性摘要；
- Docker 镜像摘要、资源参数、环境白名单和仓库策略摘要；
- `SnapshotTree` 摘要。

### 检查执行

- `RunCheckAction` 只能选择 §4.2.2 的封闭计划；适配器生成固定 argv，禁止 Shell。
- 每项检查使用全新容器；候选树只读挂载；缓存和临时文件进入 tmpfs。
- 机器可读报告是权威解析输入；stdout/stderr 只作为有界诊断工件，不能直接决定 PASS。
- 检查前后都重验候选树、保护工件和 Manifest 环境；项目树出现任何写入或漂移即 `EXECUTION_WORKSPACE_MUTATED`。

    CheckResult.status = PASS | FAIL | ERROR | TIMEOUT | NOT_RUN
    TestStatus = PASS | FAIL | SKIP | XFAIL | XPASS | DESELECTED | ERROR | NOT_RUN
    TestError = {status: ERROR, error_phase: ErrorPhase, stable_error, evidence_ref}

快速反馈可以只运行 `TARGET_TESTS`，但不能创建 `VerifiedCandidate` 或正式成功。

### 结构化反馈

- 反馈只从 `CheckResult`、`TestStatus`、`ErrorPhase`、`FailureFingerprintV1` 和稳定错误码生成。
- 下一 turn 最多接收 10 条、32 KiB；最近失败的分类、位置和有界摘要必须保留。
- 修改保护工件的候选直接 `DENY`，不运行检查。

### 正式成功谓词

完整正式验证只有在以下条件全部满足时才创建 `VerifiedCandidate`：

1. 最终 pytest 收集集合与 Manifest 完全一致；
2. 每个 node ID 都实际执行且为 `PASS`；
3. 不存在 skip、xfail、xpass、deselect、未执行、收集错误、setup/teardown 错误、环境错误或超时；
4. 所有目标测试由 Manifest 记录的稳定 `CALL/FAIL` 指纹变为最终 `PASS`；
5. Ruff 和 Mypy 均 `PASS`；
6. 保护工件、检查计划、工具版本、镜像摘要和环境摘要保持一致；
7. 候选项目树在所有检查后仍与正式验证输入完全一致。

pytest 退出码为 0 但上述任一条件不成立时，正式验证仍失败。

### 输出与错误

输出：`StaticProjectProfileResult`、`RuntimeCompatibilityResult`、`BaselineResult`、`PytestEvidenceV1`、`FailureFingerprintV1`、`ValidationManifestV1`、`CheckResult`、`FeedbackRecord`、`VerifiedCandidate`。

错误：`TARGET_NOT_FOUND`、`TARGET_NOT_REPRODUCED`、`TARGET_UNSTABLE`、`BASELINE_BLOCKED`、`REPORTER_INVALID`、`CHECK_ERROR`、`CHECK_TIMEOUT`、`PROTECTED_ARTIFACT_CHANGED`、`EXECUTION_WORKSPACE_MUTATED`、`VALIDATION_ENVIRONMENT_CHANGED`、`FORMAL_VALIDATION_FAILED`。

### 确定性测试

使用固定机器可读报告夹具覆盖全部目标稳定 `CALL/FAIL`、目标意外 PASS/ERROR、执行根和 run ID 变化但指纹相同、用户正文变化导致指纹不稳定、节点漂移、skip/xfail/xpass/deselect、五种 `ErrorPhase`、事件缺失/重复/截断、结束标记或摘要损坏、Ruff/Mypy 解析错误、保护工件变化、项目树写入和正式全通过；解析器单测不访问网络或真实 Docker。Docker 集成测试另见 §10.3。

## 4.6 FR-PERSIST：最终批准、受控写回与恢复

### 输入

`VerifiedCandidate`、规范 `FinalDiff`、`ValidationManifestV1`、正式验证证据、工作区前映像和最终 `FinalWritebackApproval`。

### 写回前置条件

1. `FinalDiff` 不超过 §1.4.4 的 3 文件限制。
2. `VerifiedCandidate` 精确绑定当前候选、Manifest 和 FinalDiff。
3. WebUI 同页展示精确 diff、Manifest 摘要和正式验证证据。
4. `FinalWritebackApproval` 已按 §4.4.2 原子消费。
5. 跨进程 workspace lease 仍由当前进程持有；权威工作区仍等于冻结前映像。

### 持久化事务

    PersistenceTransactionState =
      PREPARED | WRITING | COMMITTED | ROLLED_BACK | UNRESOLVED

    PreimageV1 =
      PRESENT {
        raw_bytes_digest
        text_metadata
        object_identity
      }
      | ABSENT

    PostimageV1 {
      raw_bytes_digest
      text_metadata
      required_object_policy_digest
    }

    PathWriteState =
      NOT_STARTED | REPLACED | VERIFIED | ROLLED_BACK

    PersistencePathRecord {
      path
      operation: CREATE | REPLACE
      preimage: PreimageV1
      postimage: PostimageV1
      sequence
      durable_state: PathWriteState
      backup_ref: artifact_ref | ABSENT
      last_evidence_digest: digest | ABSENT
    }

现有文件使用 `PRESENT` 前映像；本事务创建的新文件使用 `ABSENT`。`ABSENT` 是类型化哨兵，不是空文件摘要。`CREATE` 必须绑定 `ABSENT` 且 `backup_ref=ABSENT`；`REPLACE` 必须绑定 `PRESENT` 和有效备份引用。违反组合时事务不能进入 `PREPARED`。

1. 创建状态为 `PREPARED` 的本地事务日志，为每个目标路径写入完整 `PersistencePathRecord`；所有记录初始为 `NOT_STARTED`。
2. 每个文件写入前再次验证 workspace lease、目标前映像和路径对象身份。
3. 首次替换前转为 `WRITING`；使用同目录临时文件，写入后 flush 文件内容，在可用时同步目录元数据，然后执行原子替换。
4. 每次替换后，只有观察到当前对象精确匹配 postimage 且对象类型仍受支持，才能把该路径持久记录为 `REPLACED`；写后复验完成后记录为 `VERIFIED`。恢复前映像并复验后才可记录 `ROLLED_BACK`。
5. 正常写回只允许 `NOT_STARTED → REPLACED → VERIFIED`；恢复可在重新验证实际字节后从前三种状态进入 `ROLLED_BACK`。不得跳过证据直接前移状态，也不得从 `ROLLED_BACK` 返回写回状态。
6. `durable_state` 是最后一次成功持久化的进度事实，不是当前文件内容的权威替代。进程可能在文件替换与状态落盘之间崩溃；恢复必须重新读取当前字节、文本元数据和对象身份，并允许观测证据纠正滞后的状态。
7. 全部替换完成后，逐文件比较期望后映像，并重验未涉及 tracked 文件未变化。
8. 只有全部匹配时转为 `COMMITTED` 并由 `PersistenceCoordinator` 发布 `SUCCEEDED`；可证明全部恢复前映像时转为 `ROLLED_BACK`；其他未知或矛盾状态只能转为 `UNRESOLVED`。

事务数据库、前映像备份和恢复证据必须创建在当前 Windows 用户专属本地应用数据目录，并在写入前验证 ACL 只允许当前用户和操作系统必要主体访问。无法创建或证明安全 ACL 时以 `ARTIFACT_ACL_UNSAFE` 失败关闭，不得把源码备份写入目标仓库、通用临时目录或继承了宽权限的目录。

### 恢复入口

CLI 必须提供：

    vespercode recover --workspace <path>
    vespercode recover --workspace <path> --apply

不带 `--apply` 时只读取事务、备份和当前字节，展示逐路径前/后映像匹配、拟执行动作和预计结果，且不得修改工作区、事务状态或备份。`--apply` 在重新取得同一 workspace lease、重验对象身份和备份完整性后才执行恢复。

本地 WebUI 提供等价恢复页，先展示事务摘要、受影响路径、逐路径匹配状态和拟执行结果，再要求显式确认。不存在“忽略”“强制成功”或跳过未知路径的入口。

恢复只产生：

- `COMMITTED`：证明所有后映像匹配，重做写后核对；满足成功条件后进入 `SUCCEEDED`。
- `ROLLED_BACK`：证明所有路径恢复到前映像，进入 `STOPPED`。前映像为 `ABSENT` 时，只有当前文件精确匹配本事务 postimage、操作为 `CREATE` 且对象身份仍受支持，才允许删除该新文件；若文件被外部改写、变为链接/特殊对象或身份无法证明，则不得删除并进入 `UNRESOLVED`。
- `UNRESOLVED`：存在未知字节、缺失备份、矛盾证据或无法证明的对象身份，保持 `RECOVERY_REQUIRED`。

存在 `UNRESOLVED` 事务时，同一工作区的新运行必须被拒绝。只有 `COMMITTED` 或 `ROLLED_BACK` 后，才可以释放恢复阻断并按保留策略删除不再需要的正文备份；删除前必须保留足以证明终局的摘要记录。`UNRESOLVED` 的事务、备份和最小证据不受普通清理或 30 天审计清理影响。

若事务日志存在但尚无工作区写入，可安全结束为 `ROLLED_BACK`。取消、普通进程重启或用户声明放弃都不能把不确定事务改写为成功或安全停止。

### 输出与错误

输出：`PersistenceTransaction`、`RecoveryResult` 和 `SUCCEEDED | STOPPED | RECOVERY_REQUIRED`。

错误：`APPROVAL_STALE`、`WORKSPACE_CHANGED`、`WORKSPACE_LOCK_LOST`、`ARTIFACT_ACL_UNSAFE`、`PERSISTENCE_FAILED`、`PERSISTENCE_UNCERTAIN`、`WRITEBACK_MISMATCH`、`RECOVERY_UNRESOLVED`。

### 确定性测试

使用临时目录和逐故障点注入覆盖 preview 零写入、显式 apply、写入前失败、第一/第二文件替换后崩溃、文件替换后但 `REPLACED` 状态落盘前崩溃、三文件混合 `CREATE/REPLACE`、新文件精确 postimage 的 `ABSENT` 回滚、新文件被外部改写或替换为特殊对象、ACL 不安全、完整提交、前映像变化、可回滚和未知字节；断言状态滞后可由字节证据纠正，外部改写的新文件绝不删除，未知证据只能进入 `RECOVERY_REQUIRED`，且恢复阻断不能被普通启动绕过。

## 4.7 FR-MEM：记忆与审计

### 输入

规范化工作区身份、当前运行主体、用户记忆操作和控制面事件。

### 记忆写入权限

| 类型 | 唯一创建者 | 内容来源 |
|---|---|---|
| `PROJECT_CONVENTION` | 用户显式创建或确认 | 用户可见文本与来源 |
| `USER_DECISION` | 控制面根据真实用户决定创建 | 批准、拒绝或配置决定的结构化摘要 |
| `RUN_SUMMARY` | 控制面 | 已结束运行的结构化状态、动作和结果，不调用模型自由总结 |
| `KNOWN_FAILURE` | 控制面 | 结构化 `CheckResult` 和稳定失败指纹 |

模型不得调用通用记忆写入工具，也不得通过输出伪造来源。所有条目记录创建者、来源引用、创建/更新时间和不可信标记。

### 选择与清除

- 每次上下文最多选择 20 条、16 KiB；按当前仓库、类型优先级、更新时间和稳定 ID 确定性排序。
- 记忆不能修改策略、Manifest、审批、披露范围、配置或成功条件。
- 用户清除后，后续 turn 和运行不得再选择该条目；已完成的外部请求和审计不被追溯改写。
- 当前仓库字节和当前检查证据与记忆冲突时，以当前事实为准。

### 审计

- 记录生命周期、动作摘要、策略决定、FinalWritebackApproval、DisclosureGrant、逐请求披露授权元数据、检查结果、恢复和成功/停止证据。
- 不记录凭据、完整 LLM 请求/响应、完整文件正文或未截断工具输出。
- 审计事件不可由 Agent 修改；默认保留 30 天，用户可显式清除已结束运行的本地审计。

### 输出与错误

输出：`MemorySelection`、记忆查看/创建/确认/清除结果和按序 `AuditEvent`。

错误：`MEMORY_SCOPE_VIOLATION`、`MEMORY_WRITE_NOT_AUTHORIZED`、`MEMORY_CONTENT_REJECTED`、`MEMORY_STORE_FAILED`、`AUDIT_STORE_FAILED`。

### 确定性测试

使用两个临时工作区、固定时钟和内存 SQLite，验证来源权限、选择顺序、跨仓库隔离、清除效果、模型写入拒绝、秘密字段拒绝和审计序号单调。

## 4.8 FR-CRED：凭据生命周期

### 接口

    SetCredential(provider, secret) -> CredentialMutationResult
    GetCredentialStatus(provider) -> CredentialStatus
    ClearCredential(provider) -> CredentialMutationResult

### 行为

1. 只支持 `OPENAI` provider；秘密通过 WebUI password 控件进入后端，不允许通过 URL、CLI 参数或日志字段传递。
2. 启动时和每次写入后必须验证实际后端为 Windows Credential Manager，并进行写入/读取状态能力探测。
3. 若 keyring 退化为明文文件、环境模拟或其他不受支持后端，返回 `CREDENTIAL_BACKEND_UNSAFE`，不得存储。
4. `GetCredentialStatus` 只返回配置状态、provider 和更新时间，不返回 secret、secret 长度或可用于猜测的派生值。
5. 更新以新秘密覆盖旧条目；清除失败必须明确返回失败，不能假装已删除。

### 错误

`CREDENTIAL_INVALID`、`CREDENTIAL_BACKEND_UNSAFE`、`CREDENTIAL_STORE_FAILED`、`CREDENTIAL_CLEAR_FAILED`、`CREDENTIAL_MISSING`。

### 确定性测试

离线单测使用 `FakeCredentialStore` 验证录入、状态、覆盖、清除和日志脱敏；Windows 发布验证必须包含一次真实 Credential Manager smoke test，测试秘密在结束后清除。

## 4.9 FR-UI：本地 WebUI 与公网 Demo

### 本地模式

- CLI 启动绑定 `127.0.0.1` 的 WebUI。
- 使用随机本地会话令牌、严格 Host/Origin 校验和 CSRF 防护。
- 提供运行创建、预检、状态、diff、最终批准、披露 Grant、凭据状态、记忆、审计和恢复页面。
- 不可信文本以纯文本或安全转义方式渲染，不执行仓库 HTML。
- `CREATED`、各 `RUNNING` phase、`WAITING_USER`、`RECOVERY_REQUIRED`、`SUCCEEDED`、`STOPPED` 使用不同、无歧义的标签。

### 公网 Demo

- 独立进程只注册 Mock LLM、内置场景和 `DemoExecutor`。
- 不注册本地文件、Keyring、Docker、恢复或真实供应商适配器。
- 固定场景展示：硬 `DENY`；一次检查失败使下一动作改变；保护工件修改被拒绝；没有最终批准时不写回。
- Demo 只使用 `DemoRunStatus`；完成为 `DEMO_COMPLETED`，失败为 `DEMO_FAILED`。
- 模拟用户选择形成 `DemoDecision {demo_session_id, subject_digest, decision, created_at}`；它只推进固定 Demo 场景，不得转换为 `FinalWritebackApproval`、`DisclosureGrant` 或正式 `AuditEvent`。
- 会话有独立 UUID，最长 5 分钟；结束后丢弃。重置失败只使该会话失败，不创建跨进程恢复协议。

### 输出、错误与测试

输出安全渲染的状态、diff、授权、检查、记忆、恢复和审计页面。

Host/Origin/CSRF 校验失败、无效会话、Demo 非法场景或能力请求必须拒绝。使用测试客户端验证安全 header、HTML 转义和状态映射；固定 Demo 重复两次，断言关键动作、状态和终态一致且真实适配器调用次数为零。

# 5. 非功能需求与安全

## 5.1 NFR-PERF：性能与预算

- 内建硬上限为 20 个 Agent turn、20 次 LLM 调用和 900 秒总墙钟；实际上限使用冻结 `RunLimitsV1`。总墙钟从 `PREFLIGHT` 开始，到终态或 `RECOVERY_REQUIRED` 为止，并包含 `WAITING_USER`。
- 单工具动作、单目标检查和完整正式验证分别使用 `tool_timeout_seconds`、`target_check_timeout_seconds` 和 `formal_validation_timeout_seconds`。它们都是总运行预算内的子上限，剩余总墙钟更小时以剩余值为准。
- 单次 LLM 规范请求不超过 64 KiB，单次工具反馈不超过 32 KiB。
- 单次检查原始输出最多 4 MiB，超出即 `CHECK_OUTPUT_LIMIT_EXCEEDED`，不得把截断结果判为 PASS。
- 仓库、候选和 Docker 资源上限使用 §1.4.4—1.4.5。
- 公网 Demo 每会话最多 20 个动作、5 分钟；进程级并发上限 10。
- 达到上限必须在动作或调用前停止，不得把截断、未运行或部分结果视为成功。

## 5.2 NFR-REL：可靠性

- 相同 Mock 脚本、快照、配置、时钟、ID 生成器和用户决定必须产生相同关键动作、状态和终态。
- 相同语义对象在不同进程、映射插入顺序和易变运行元数据下必须产生相同 §0.1 摘要。
- 相同 `ReferenceProfileManifestV1`、LLM profile 和 target 集合必须形成相同冻结配置；profile digest 变化必须被视为环境变化。
- 所有核心机制使用离线、无网络的 Mock/Stub 单元测试。
- 未知、不完整或矛盾证据默认失败关闭。
- 只有权威工作区持久化允许恢复；其他重启统一停止。
- 工作区 lease、批准消费、披露预算消费和持久化事务必须通过存储事务或 Win32 原语实现明确并发边界。

## 5.3 NFR-USE：可用性

- 所有拒绝和停止结果必须包含稳定代码、用户可理解原因和下一步建议。
- WebUI 不直接暴露内部引用图或数据库字段。
- 用户必须能区分准备中、预检、运行中、等待决定、恢复阻塞、成功和停止。
- diff、批准对象、验证证据和工作区前映像状态必须在同一页面关联展示。
- 恢复页在执行前展示受影响路径和拟判定；不存在“忽略并继续”按钮。

## 5.4 NFR-OBS：可观测性

- 每个正式运行有唯一 `run_id` 和按顺序递增的审计序号；Demo 使用独立 `demo_session_id`。
- 日志使用结构化事件，并对路径、输出和错误文本执行长度限制与脱敏。
- 测试模式允许注入时钟、ID 生成器和故障点，以获得稳定快照。
- `.gitlab-ci.yml` 必须包含 §8.4 的三个精确 job 名称并遵守各自 push、merge request 和 main 触发合同。
- 发布证据必须区分离线单测、Windows 集成、Docker 集成、端到端 fixture 和公网 smoke test。

## 5.5 NFR-SEC：威胁模型

| 资产/风险 | 攻击者或来源 | 对策 | 残余风险 |
|---|---|---|---|
| OpenAI API Key | 仓库文本、日志、命令历史、Demo 用户 | Windows Credential Manager；后端探测；隐藏录入；禁止 CLI 参数和明文配置；日志白名单 | 同一 Windows 用户或管理员仍可能访问凭据 |
| 用户源码 | 恶意模型、提示注入、错误披露范围 | 本地读取与外发分离；冻结 LLM profile；运行级 Grant；逐请求授权记录；敏感 tracked 路径准入拒绝；明确 `NO_CONTENT_REDACTION_V1` 不扫描正文 | 被授权源码按范围原样外发；不能识别源码正文中的所有秘密 |
| 权威工作区 | 越界路径、reparse/hard link、陈旧批准、并发进程 | 句柄级身份检查、单链接画像、named mutex、前映像绑定、逐文件复核、写后核对 | 最后检查与替换间仍有短暂本机竞争窗口 |
| 验收契约 | 模型修改测试、配置或运行时篡改 | 不可变 Manifest、保护工件、只读候选挂载、全新容器、正式重验 | Manifest 只覆盖支持画像中已识别的入口 |
| 控制面数据 | 项目代码或容器读取宿主数据 | 无网络、非 root、只读根、候选只读挂载、tmpfs、无 Docker socket | Docker Desktop/宿主管理员不在威胁模型内 |
| WebUI | CSRF、恶意仓库 HTML、远程访问 | loopback、会话令牌、Host/Origin、CSRF、安全转义、CSP | 本机同用户恶意进程可能与服务竞争 |
| 公网 Demo | 越权到真实能力、跨会话数据 | 独立状态和能力注册表、固定场景、无凭据、无持久磁盘 | 部署平台管理员仍可访问运行环境 |
| 恢复工件 | 用户误删、未知外部修改 | 恢复阻断、前后映像、备份完整性、三值恢复结果 | 用户或管理员可在 Harness 外破坏恢复工件 |

安全属性必须表述为在上述前提下可测试的机制，不使用绝对安全或“识别所有攻击”的承诺。

## 5.6 NFR-PRIV：数据保留

- 凭据只存于 Windows Credential Manager。
- 运行数据库、记忆、审计和恢复工件位于当前 Windows 用户专属本地应用数据目录，不进入目标仓库；创建时必须验证仅当前用户和操作系统必要主体可访问的 ACL。
- 审计默认保留 30 天；普通执行副本在运行终止后立即尝试删除。
- 已形成 `COMMITTED` 或 `ROLLED_BACK` 的事务按保留策略删除正文备份并保留摘要证据；未解决事务的最小日志和备份必须保留到恢复形成终局，不能被普通清理删除。
- 公网 Demo 不接收用户仓库、真实凭据或任意文件上传，不挂载持久磁盘。

# 6. 系统架构

## 6.1 组件图

    Local WebUI                         Public Demo UI
         |                                    |
    Application Service                  Demo Service
         |                                    |
      Run Service                         Demo Loop
     /    |     \                             |
 Admission Agent Loop Recovery        Mock LLM + DemoExecutor
     |      /   |   \     |
 Workspace Context LLM Tools Persistence
     |       |    |    |       |
 Win32   SQLite Mock/OpenAI Policy  Transaction Log
 Lease              |       |
                 Disclosure  PythonProjectAdapterV1
                                |
                         DockerExecutorV1
                                |
                       Read-only CandidateTree

    CredentialService -> Windows Credential Manager
    Admission -> Built-in Reference/LLM Profile Registry
    PersistenceCoordinator -> Authoritative Workspace

依赖方向从应用服务指向核心端口，再指向适配器。LLM、Docker、Credential Store、数据库、Win32 文件系统和时钟必须可替换为测试 double。WebUI 不直接访问仓库、凭据或数据库。

## 6.2 正式修复数据流

    ValidateRunRequestV1
    → resolve Reference/LLM profile manifests + freeze RunLimitsV1
    → Create Run(CREATED) + freeze config
    → Start + PREFLIGHT static profile check
    → SnapshotTree
    → collect-only ×2 + full pytest + target rerun + Ruff + Mypy
    → RuntimeCompatibilityResult(COMPATIBLE)
    → ValidationManifestV1
    → Agent turn / governance / candidate patch / structured feedback loop
    → fresh read-only formal validation
    → VerifiedCandidate
    → user approves exact FinalDiff
    → persistence transaction + post-write verification
    → SUCCEEDED | STOPPED | RECOVERY_REQUIRED

## 6.3 真实 LLM 调用数据流

    frozen LLMProfileManifestV1 + ContextProjection draft
    → classify exact sources and bytes
    → active DisclosureGrant?
        no: WAITING_USER(DISCLOSURE_GRANT, bounded by run deadline)
        yes: apply NO_CONTENT_REDACTION_V1 and create exact PreparedModelRequest
    → atomically consume grant budget + create DisclosureAuthorizationRecord
    → pass the same authorized request to one OpenAI adapter call
    → LLMCallResult

授权事务提交后预算不退款。适配器调用失败、调用前崩溃或交付状态未知都不得重用授权记录或自动重发。

## 6.4 公网 Demo 数据流

    Fixed Scenario
    → Mock LLM script
    → shared action parser / policy / feedback core
    → DemoExecutor simulated result
    → Demo audit
    → DEMO_COMPLETED | DEMO_FAILED

Demo 不经过 Credential Store、真实 LLM、Docker、workspace lease、恢复或权威持久化。

## 6.5 外部依赖

- OpenAI：仅单轮生成接口；不使用 Agent runner。
- Docker Desktop：运行目标代码和正式检查。
- Windows Credential Manager：真实 API Key 存储。
- Win32 文件与同步 API：最终对象身份、hard link/reparse 检测和跨进程 named mutex。
- Git：只读准入、HEAD/blob 身份和 ignore/attribute 策略检查。
- pytest、机器可读 pytest 报告插件、Ruff、Mypy：由 Python 项目适配器调用并解析。

# 7. 数据模型

| 实体 | 关键字段 | 关系与约束 |
|---|---|---|
| Run | id、workspace_identity、status、phase、config_snapshot_id、started_at、run_deadline | `PREFLIGHT` 入口冻结 deadline；一个运行有多个 turn；终态不可重开 |
| RunLimitsV1 | turns、LLM calls、run wall clock、wait/tool/check timeouts | 全部必填且只能收紧内建硬上限 |
| ReferenceProfileManifestV1 | requirements/image/tool/check-plan versions、digest | `python-src-py312-v1` 的权威可交付映射 |
| LLMProfileManifestV1 | mode、provider/model 或 Mock script、adapter/serializer、fixed parameters、digest | 请求只选 profile id，不能覆盖 manifest 字段 |
| RunConfigSnapshot | target IDs、limits、LLM/reference/Docker profile digests、digest | 创建后不可变；不能包含秘密 |
| WorkspaceLease | workspace_identity、mutex_name、process_id、acquired_at | 正式工作区同一时刻最多一个持有者 |
| WaitContext | wait_id、run_id、wait_kind、source_phase、subject_digest、created_at、expires_at | 只允许 `DISCLOSURE_GRANT | FINAL_WRITEBACK`；决定绑定 wait 与 subject |
| SnapshotTree | root_digest、entries、repository_policy_digest | 一个运行一个权威基线快照 |
| RuntimeCompatibilityResult | status、violation_kind、evidence_refs | BASELINE 中产生；非 `COMPATIBLE` 不创建 Manifest |
| FailureFingerprintV1 | node、CALL phase、exception、message/diff、project frames、digest | 只由完整 pytest 证据创建；不安全规范化即不稳定 |
| ValidationManifestV1 | target IDs/fingerprints、test collection、protected/profile digests、check plan、environment digest | 由基线创建后不可变 |
| CandidateRevision | id、parent_id、tree_digest、final_diff_digest | 单父链；限制基于相对 Snapshot 的累计净差异 |
| AgentTurn | id、run_id、candidate_id、context_digest、consumed_feedback_refs、outcome | 同一运行最多一个活动 turn |
| ActionRecord | action_type、canonical_digest、policy_decision、result_ref | 动作输入与结果不可被 Agent 改写 |
| FeedbackRecord | source_ref、kind、bounded_payload、consumed_by_turn | 最多被一个下一 turn 消费 |
| FinalWritebackApproval | subject_digest、bindings、expires_at、status | 只授权最终权威写回；`PENDING` 只能一次转入一个终局状态 |
| DisclosureGrant | run/LLM profile/provider/model/scope/redaction/budget/expiry/status | v1 redaction 固定为 `NO_CONTENT_REDACTION_V1`；不授权工具 |
| DisclosureAuthorizationRecord | grant/profile ids、request digest、actual sources/categories、bytes | 逐请求精确记录，不含正文 |
| PreparedModelRequest | LLM profile、serializer、provider/model、messages、fixed parameters、sources/redaction/bytes、digest | profile 应用和裁剪完成后不可追加项目正文 |
| LLMCallResult | authorization_record_id、status、response_digest、error | `NOT_ATTEMPTED | SUCCEEDED | FAILED | DELIVERY_UNKNOWN`；不证明供应商交付 |
| PytestEvidenceV1 | schema/plugin、events、collection、exit、integrity_digest | 缺失、截断或完整性失败不能产生 PASS |
| CheckResult | check_kind、status、structured_findings、raw_digest | 原始输出作为有界本地工件 |
| VerifiedCandidate | candidate_id、manifest_id、formal_result_digest | 只有完整正式验证通过时创建 |
| PersistenceTransaction | final_diff_digest、path_records、state、backup_refs | `PREPARED | WRITING | COMMITTED | ROLLED_BACK | UNRESOLVED`；未解决时阻止新运行 |
| PersistencePathRecord | path、operation、PRESENT/ABSENT preimage、postimage、sequence、durable_state、evidence | 状态可滞后；恢复始终重验实际字节和对象身份 |
| RecoveryResult | transaction_id、disposition、evidence_digest | `COMMITTED | ROLLED_BACK | UNRESOLVED` |
| MemoryEntry | workspace_identity、kind、summary、creator、source、timestamps | 不保存秘密、权限或完整源码 |
| AuditEvent | run_id、sequence、event_type、redacted_payload | 每个运行序号唯一且单调 |
| DemoSession | id、scenario_version、status、state_digest、expires_at | 与正式 Run 和能力完全隔离 |
| DemoDecision | demo_session_id、subject_digest、decision、created_at | 只推进固定 Demo 场景，不能转换为正式授权 |

控制存储使用 SQLite 事务保证本地状态比较与更新。大文件、执行副本、补丁正文、原始检查输出和恢复备份存为当前用户 ACL 受限的本地工件，只在数据库保存摘要与精确引用；凭据从不进入 SQLite。所有 digest 使用 §0.1。

# 8. 凭据、分发与部署

## 8.1 凭据流程

1. 首次选择真实 LLM 时，WebUI 通过 password 输入控件收集 Key。
2. 后端验证 Windows Credential Manager backend 后直接写入；不经过命令行参数、URL 或日志。
3. 状态接口只返回配置状态、供应商和最近更新时间。
4. 更新使用新秘密覆盖旧条目，并返回明确结果。
5. 清除删除凭据条目；删除失败必须报告失败，不能假装成功。
6. 公网 Demo 构建不包含凭据管理和真实 LLM 适配器注册。

## 8.2 本地分发

- 发布 Python wheel，并将版本化 wheel 作为 GitHub Release 附件提供；Release 同时发布 SHA-256 摘要。
- README 必须记录 Release 下载位置、版本、摘要校验命令和从下载产物安装的步骤。
- 从本地构建产物安装的规范命令为：

      pipx install dist/vespercode-<version>-py3-none-any.whl

- 只有在包实际发布到配置的 Python 包索引后，README 才可以写：

      pipx install vespercode

- `vespercode serve` 启动本地 WebUI。
- `vespercode recover --workspace <path>` 只预览恢复；增加 `--apply` 后才执行。WebUI 提供等价的预览与显式确认入口。
- 目标机器前提：Windows 11 x64、Python 3.12、Git、Docker Desktop Linux 容器模式，以及预构建的 `python-src-py312-v1` 镜像。
- README 必须给出获取、安装、启动、凭据配置、reference/Docker/LLM profile manifest 与精确模型、`NO_CONTENT_REDACTION_V1` 外发提示、恢复、目录结构和已知限制。

## 8.3 公网 Demo 分发

- 使用独立 Docker 镜像启动 Mock Demo。
- 镜像不包含本地模式能力注册、真实凭据入口、恢复逻辑或 Docker socket。
- 部署平台为 Render Web Service，使用 Demo Dockerfile 从 main 分支构建。
- 容器读取平台注入的 `PORT` 并绑定 `0.0.0.0`，健康检查为 `GET /healthz`。
- 服务不挂载持久磁盘；会话状态只存在进程内，进程重启后全部丢弃。
- 环境不得配置真实 LLM Key、Docker socket 或目标仓库访问凭据。
- README 记录公开 URL、服务配置、健康检查和免费实例可能冷启动的限制。

## 8.4 发布构建要求

`.gitlab-ci.yml` 必须包含以下精确 job 名称；不能仅由人工发布脚本替代：

| Job | 触发条件 | 必须执行 |
|---|---|---|
| `unit-test` | 每次 push 和每个 merge request | 在锁定依赖环境中运行离线 `python -m pytest -q`，保存测试报告 |
| `wheel-build-smoke` | 每次 push 和每个 merge request | 构建 wheel、生成并校验 SHA-256，在干净受支持环境中从该 wheel 安装并运行 `vespercode --help` |
| `demo-image-build` | 每个 merge request 和 main 分支 push | 使用 Demo Dockerfile 真实构建 OCI 镜像，记录镜像摘要并运行容器级 `/healthz` smoke |

版本 tag/release 流水线复用通过验证的构建步骤，重新生成并校验版本化 wheel 和 SHA-256，创建或更新对应 GitHub Release 工件，并保存版本、Release URL、wheel 摘要、镜像摘要、测试与 smoke 证据。普通 push/MR 流水线不得创建 Release。

# 9. 技术选型

| 项目 | 选择 | 理由 |
|---|---|---|
| 语言 | Python 3.12 | 与目标 profile 和测试生态一致，适合可注入端口 |
| API/Web | FastAPI + Pydantic v2 | 严格请求 Schema、类型校验和本地/公网复用 |
| UI | 服务端 HTML + HTMX；Open Design 作为设计系统；使用 `ui-ux-pro-max` skill 做交互、可访问性和安全渲染审查 | 降低前端状态复杂度，满足 WebUI 与安全渲染要求 |
| 控制存储 | SQLite | 支持本地原子状态更新、无需额外服务 |
| Windows 边界 | pywin32/Win32 API 封装 | 处理最终对象身份、reparse/hard link 和 named mutex |
| 凭据 | keyring，且强制验证 Windows Credential Manager backend | 满足系统钥匙串要求并拒绝不安全 fallback |
| LLM | 自定义 `LLMAdapter`；冻结 `LLMProfileManifestV1`；Mock + OpenAI 单轮适配器 | 固定模型/Mock 脚本、适配器、请求序列化器和参数；不依赖高层 Agent 框架 |
| 执行 | Docker SDK for Python；固定 argv、无网络、只读根、候选只读挂载、tmpfs | 隔离项目代码并防止运行时临时篡改验收树 |
| 检查 | pytest + 固定机器可读报告插件、Ruff、Mypy | 提供测试、lint、类型和结构化反馈 |
| 测试 | pytest；单一离线命令 `python -m pytest -q` | 可注入、适合 TDD 与 Mock LLM |
| CI | `.gitlab-ci.yml`，包含 `unit-test`、`wheel-build-smoke`、`demo-image-build` | 冻结课程测试、wheel smoke 和 Demo 镜像构建的名称、触发与证据 |
| 包分发 | wheel + pipx | 适合 Windows 本地 CLI/WebUI |
| Demo | OCI 容器 | 与本地能力隔离，便于公网部署 |
| 公网部署 | Render Web Service；Docker runtime、`/healthz`、无持久磁盘 | 冻结公开 WebUI 的端口、健康检查和无状态边界 |

依赖必须锁定。不得引入 LangChain `AgentExecutor`、AutoGen、CrewAI、LlamaIndex Agent、OpenAI Agents SDK runner 或宿主编码智能体 runner 来替代自研主循环。

# 10. 验收标准与追踪

## 10.1 项目级验收

- **AC-01：** 路径逃逸、绝对路径、ADS、设备名、symlink/reparse、hard link 和敏感 tracked 路径全部确定性拒绝。
- **AC-02：** 硬 `DENY` 无法被配置、模型输出、DisclosureGrant 或批准覆盖。
- **AC-03：** 一次性 `FinalWritebackApproval` 在过期、绑定变化和重复消费时均不执行，且不能授权披露、Demo 或其他 `ASK`。
- **AC-04：** 修改测试、检查配置或 Manifest 保护工件的补丁不能进入检查或正式验证。
- **AC-05：** 注入固定检查失败后，Mock LLM 下一轮动作按脚本发生变化。
- **AC-06：** LLM completion 建议不能绕过正式成功谓词和最终批准。
- **AC-07：** 写回内容精确等于已批准 `FinalDiff`；外部工作区变化阻止写入。
- **AC-08：** 凭据录入、状态、更新、清除、后端探测和日志均不暴露测试秘密。
- **AC-09：** 相同 Demo 输入产生相同关键状态和动作序列，且只进入 `DemoRunStatus`。
- **AC-10：** `python -m pytest -q` 离线通过；`.gitlab-ci.yml` 的 `unit-test` 在每次 push 和 merge request 运行，最后一次记录通过。
- **AC-11：** `wheel-build-smoke` 在每次 push 和 merge request 构建 wheel、校验 SHA-256 并完成干净安装/CLI smoke；README 步骤可从发布产物启动 WebUI。
- **AC-12：** `demo-image-build` 在每个 merge request 和 main push 真实构建镜像并通过容器 `/healthz` smoke；公网 Mock Demo URL 可访问且无法使用本地、恢复或真实能力。
- **AC-13：** 未授权披露时真实适配器调用次数为零；有效 Grant 精确绑定冻结 LLM profile 和 `NO_CONTENT_REDACTION_V1`，不同请求生成不同逐请求授权记录；profile、范围、预算上限或有效期变化，或请求需要扩大范围时，在有正等待区间时要求新 Grant。
- **AC-14：** 两个工作区的记忆相互隔离；模型不能直接写记忆；用户清除后后续 turn 不再选择该条目。
- **AC-15：** 严格 `ValidateRunRequestV1` 拒绝重复/超量目标、未知 profile、缺失限制和放宽硬上限；有效请求先创建 `CREATED`，静态预检发生在 `PREFLIGHT` 且不运行项目代码，动态兼容性只在 `BASELINE` 判定。
- **AC-16：** 正式 Run 的六种状态和各 phase 显示正确；失败、超时、skip、xfail、xpass、deselect 和未运行不显示为通过。
- **AC-17：** 六种动作严格按 Schema 解析；`RunCheckAction` 无法携带 executable、argv 或命令文本；多动作和自由文本响应被拒绝。
- **AC-18：** 多次 patch action 不能绕过累计 3 文件/128 KiB 限制；`FinalDiff` 等于 Snapshot 到最终 CandidateTree 的规范净差异。
- **AC-19：** Docker 检查中候选树只读、缓存进入 tmpfs、无 Docker socket、无网络；`RuntimeCompatibilityCheckV1` 对收集漂移、项目树写入、报告不完整或检查环境错误返回结构化 `BASELINE_BLOCKED`。
- **AC-20：** 正式 pytest 只有在 node 集合一致、全部实际执行并 PASS、无所有禁止状态、Ruff/Mypy PASS、保护工件和环境一致时才创建 `VerifiedCandidate`。
- **AC-21：** 两个进程竞争同一工作区时最多一个获得 lease；未解决恢复事务阻止新的正式 Run。
- **AC-22：** 1—3 文件混合 `CREATE/REPLACE` 的故障注入只产生 `COMMITTED`、`ROLLED_BACK` 或 `UNRESOLVED`；`PersistencePathRecord` 状态滞后由实际字节证据纠正，`UNRESOLVED` 保持阻断且不能被忽略。
- **AC-23：** `PROJECT_CONVENTION`/`USER_DECISION` 与 `RUN_SUMMARY`/`KNOWN_FAILURE` 的创建权限严格按 §4.7 执行。
- **AC-24：** Windows、Docker、端到端和 §8.4 三个强制 CI job 均形成可保存证据；不能用解析器单测或人工发布脚本替代真实边界测试和镜像构建。
- **AC-25：** 每个目标在全量基线和独立复跑中都稳定产生相同 `CALL/FAIL` 与 `FailureFingerprintV1.digest`；任一目标 PASS/ERROR、缺失、未运行、无法安全规范化、不稳定、运行时不兼容或 `PytestEvidenceV1` 不完整时不创建 Manifest。
- **AC-26：** 相同语义对象、profile 和 target 集合在不同进程、映射插入顺序和易变元数据下产生相同 §0.1 摘要；profile 内容、路径别名、大小写/Unicode 碰撞或对象类型变化不能伪造绑定。
- **AC-27：** `DISCLOSURE_GRANT` 与 `FINAL_WRITEBACK` 等待的决定精确绑定 wait/run/kind/subject；拒绝、过期、取消、绑定变化、总墙钟耗尽和重启严格按 §4.2.7 转换，旧决定不能复用。
- **AC-28：** `RunLimitsV1` 的 turn/call/总墙钟和各子超时均在下一副作用前执行；等待计入总墙钟但不消耗 turn/call，进展使用排除时间、ID 和审计序号的语义摘要判断。
- **AC-29：** 恢复默认 preview 且零写入，只有显式 `--apply` 修改工作区；新文件只有仍精确匹配本事务 postimage 时才能恢复为 `ABSENT`，外部改写或未知对象绝不删除并只能进入 `UNRESOLVED`。

## 10.2 用户故事—合同—验收追踪

| 用户故事 | 权威功能合同 | 适用 NFR | 主要验收 |
|---|---|---|---|
| US-01 | FR-ADM、FR-LOOP | NFR-PERF、NFR-USE、NFR-SEC | AC-15、AC-16、AC-21、AC-26、AC-28 |
| US-02 | FR-CRED、§8.1 | NFR-SEC、NFR-PRIV | AC-08 |
| US-03 | FR-LOOP、FR-WS、FR-VAL | NFR-PERF、NFR-REL | AC-04—AC-06、AC-17—AC-20、AC-25、AC-26、AC-28 |
| US-04 | FR-GOV | NFR-SEC、NFR-PRIV | AC-13、AC-26、AC-27 |
| US-05 | FR-GOV | NFR-REL、NFR-SEC | AC-01—AC-03、AC-26、AC-27 |
| US-06 | FR-PERSIST | NFR-REL、NFR-SEC | AC-07、AC-21、AC-22、AC-26、AC-29 |
| US-07 | FR-MEM | NFR-OBS、NFR-PRIV | AC-14、AC-23 |
| US-08 | FR-LOOP、FR-MEM、FR-UI | NFR-USE、NFR-OBS | AC-06、AC-16、AC-27、AC-28 |
| US-09 | FR-UI | NFR-PERF、NFR-REL、NFR-SEC | AC-09、AC-12 |

## 10.3 验证环境矩阵

| 层次 | 环境 | 主要 AC | 必须证明 | 证据 |
|---|---|---|---|---|
| 离线核心单测 | 无网络；Fake FS/DB/Clock/LLM/Credential | AC-02、AC-03、AC-05、AC-06、AC-10、AC-13—AC-18、AC-20—AC-23、AC-25—AC-29 | profile/config 规范化、失败指纹、主循环、动作解析、策略、批准、带 deadline 的两类等待、Grant、反馈、记忆、停止和逐路径持久化故障注入 | `unit-test` job 日志与测试报告 |
| Windows 集成 | Windows 11 x64 | AC-01、AC-07、AC-08、AC-11、AC-21、AC-22、AC-24、AC-26、AC-29 | ADS、reparse、hard link、设备名、路径碰撞、Git EOL/encoding/filter 拒绝、最终对象身份、ACL、Credential Manager、named mutex 和新文件恢复 | Windows runner 或发布前保存的脚本日志；测试秘密已清除 |
| Docker 集成 | Docker Desktop Linux 模式 | AC-04、AC-19、AC-20、AC-24、AC-25 | `ReferenceProfileManifestV1` 映射、无网络、非 root、只读根、候选只读、tmpfs、资源限制、动态兼容性、`PytestEvidenceV1` 和真实 pytest/Ruff/Mypy | 固定执行镜像摘要和可重复 Docker 集成脚本/runner 报告 |
| 端到端 reference fixture | Windows + Docker + Mock LLM | AC-05—AC-07、AC-13、AC-15—AC-18、AC-20—AC-23、AC-25—AC-29 | 冻结 profiles/limits → 静态预检 → 动态兼容 → 全目标稳定指纹 → 错误补丁 → 反馈回灌 → 修正 → 正式验证 → 最终批准 → 精确写回，以及等待拒绝和未批准不写回 | 可重复 reference fixture 脚本、审计导出和最终摘要 |
| 恢复故障注入 | Windows 本地临时仓库 | AC-07、AC-21、AC-22、AC-24、AC-29 | 1—3 文件混合事务、状态落盘前崩溃、外部改写新文件、preview 零写入、显式 apply 和安全 `ABSENT` 回滚 | 故障点矩阵和恢复日志 |
| 包与发布 smoke | 干净受支持 Windows 环境 | AC-10、AC-11、AC-24 | `wheel-build-smoke`、从 GitHub Release 下载 wheel、校验 SHA-256、通过 pipx 安装并启动 WebUI | job 日志、Release URL、wheel 摘要、安装日志和环境版本 |
| 公网 smoke | `demo-image-build` + 部署后的 Demo | AC-09、AC-12、AC-24 | main/MR 镜像构建、容器及公网 `/healthz`、固定场景、`DemoDecision`、无真实能力 | job 日志、镜像摘要、部署记录与可访问 URL |

没有可用 Windows CI runner 时，Windows 集成可以作为发布前人工触发的可重复脚本，但其日志、环境版本和结果必须纳入最终交付证据；不能省略。

## 10.4 机制演示

离线脚本或测试必须在同一场景中展示：

1. Mock LLM 提出读取工作区外路径，治理护栏返回 `DENY`；
2. Mock LLM 提出合法但失败的候选补丁，pytest 失败被结构化回灌，下一轮动作改变；
3. Mock LLM 尝试修改受保护测试或 Ruff/Mypy 配置，Manifest 保护机制拒绝；
4. 修正后的候选通过正式验证，但没有最终批准时不会写入权威工作区；
5. 真实适配器 stub 在没有有效 Grant 或逐请求授权记录时调用次数为零。

# 11. 风险、关闭清单与未来工作

## 11.1 v1 风险

| 风险 | 概率/影响 | 触发信号 | 缓解或降级 |
|---|---|---|---|
| 参考 profile 与真实项目差异过大 | 中/中 | 外部试用频繁命中不支持或动态阻断 | 交付权威 manifest/reference fixture；区分静态不支持与动态不兼容；不临时扩张 |
| Win32 最终对象身份实现错误 | 中/高 | ADS/reparse/hard link 集成用例失败 | 使用 pywin32/Win32 API；失败关闭，不降级为字符串路径判断 |
| Docker Desktop 行为或性能不稳定 | 中/高 | 只读挂载、tmpfs、资源限制或 runtime compatibility 失败 | 固定 manifest/镜像摘要；动态证据失败关闭 |
| pytest/Ruff/Mypy 输出解析漂移 | 中/中 | 未知结果、指纹失败或解析错误 | 固定版本、机器可读报告和 `FailureFingerprintV1`；未知状态不通过 |
| 1—3 文件持久化中断 | 低/高 | 事务日志或逐路径状态未完成 | 类型化前映像、逐路径事实、实际字节复核、备份、三值恢复和工作区阻断 |
| 真实 LLM 泄露未识别秘密 | 中/高 | 被授权正文含未分类敏感值 | 敏感路径拒绝、冻结 profile、Grant、逐请求记录、体量限制；明确 `NO_CONTENT_REDACTION_V1` 残余风险 |
| SPEC 再次扩张 | 中/高 | 新增自然语言测试、多 Agent、通用恢复或大量兼容分支 | 所有新增先修改 §1.5/1.6 并经独立审查；PLAN 不得暗增 |
| 公网 Demo 被误认为正式验证 | 低/中 | UI 或审计缺少模拟标识 | 独立状态、持续标识、独立能力注册表 |

## 11.2 进入 PLAN 的关闭清单

本版已冻结以下此前存在歧义的架构决定：

- 请求校验、`CREATED`、`PREFLIGHT` 和正式生命周期的边界；
- 严格 `ValidateRunRequestV1`、`RunLimitsV1`、reference/LLM profile manifest 和 `NO_CONTENT_REDACTION_V1`；
- 六种 AgentAction 的字段、封闭检查计划、literal search 和严格 `UNIFIED_DIFF_V1`；
- `CanonicalizationV1`、确定性 `ContextProjection` 顺序、裁剪和预算失败行为；
- 运行级 `DisclosureGrant` 与逐请求 `DisclosureAuthorizationRecord`；
- `FinalWritebackApproval` 与带 wait/run/subject/deadline 绑定的两类 `WAITING_USER`；
- `PythonProjectProfileV1` 的静态准入、动态兼容性、Reference Profile Manifest、保护工件、Git 转换策略、敏感路径和资源上限；
- `PytestEvidenceV1`、`ErrorPhase`、`FailureFingerprintV1` 和所有目标稳定 `CALL/FAIL` 合同；
- Docker 候选树只读、tmpfs、无网络、资源限制、运行时兼容性和正式成功谓词；
- 跨进程 workspace lease、3 文件/1 新文件上限、`PersistencePathRecord`、恢复入口和三值恢复结果；
- 独立 `FR-CRED` 与记忆创建权限；
- 离线、Windows、Docker、reference fixture、恢复、包和公网验证矩阵；
- 三个强制 CI job、wheel 的 pipx 安装命令与发布 smoke 要求。

因此，PLAN 不得再让实现者自行选择上述语义。精确依赖 patch 版本、OpenAI model、镜像摘要和部署 URL 由发布 manifest、lock file、README 与流水线证据记录，并通过 digest 绑定到运行。

PLAN 的最前部必须安排三项技术验证任务，并采用失败关闭而不是放宽设计：

1. Win32 最终对象身份、hard link/reparse/ADS 与 named mutex 集成验证；
2. `ReferenceProfileManifestV1`/reference fixture 映射、Docker 只读候选树、tmpfs、缓存、资源限制、完整报告和失败指纹集成验证；
3. 1—3 文件持久化的逐故障点恢复验证。

若第三项无法证明 3 文件事务安全，必须停止后续实现和发布；不得在 PLAN 或代码中把正式范围隐式改为单文件。改变 3 文件/1 新文件范围前，必须正式修订本 SPEC、相关用户故事、AC、验证矩阵和 PLAN，并重新审查；不得删除恢复语义或把未知状态视为成功。

## 11.3 未来工作

- `NaturalLanguageDefect`、测试提案审批和 `ValidationManifestV2`。
- 更宽松但仍确定性的 skip/xfail 基线比较。
- 多语言 `ProjectAdapter` 和更多预构建 reference profile。
- 供应商请求重试、跨进程调用对账和普通 turn 恢复。
- 删除、重命名、二进制补丁和更广 Git 策略。
- 多用户部署、分布式配额和生产级工件清理。
- 超过 3 文件的持久化事务。

这些项目不得出现在 v1 的 PLAN、代码路径或验收门禁中。
