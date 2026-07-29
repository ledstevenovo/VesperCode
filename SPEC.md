# VesperCode v1 规格说明

> 版本：SPEC v3  
> 状态：SPEC v3 冻结候选，等待与其内容寻址绑定的 `PLAN.md` 获批，并完成不同 Agent 类型、无先前对话或记忆上下文的冷启动试验。除课程要求的隔离、可丢弃且不得合入的冷启动试作外，在该精确 SPEC/PLAN 对获批并通过冷启动门禁前，不得开始或继续正式实现、CI、发行或部署；§10 的实现与发布证据只能在门禁通过后生成，不能替代该门禁。

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

所有用于身份、重放、策略、批准、披露、验证和持久化绑定的摘要统一使用 SHA-256。摘要输入字节精确定义为：

    UTF8("VesperCode")
    || 0x00
    || UTF8(object_type)
    || 0x00
    || ASCII(decimal_schema_version)
    || 0x00
    || canonical_json_utf8

`object_type` 必须是本文声明的精确类型名；schema 版本使用无前导零十进制。摘要输出为 64 个小写十六进制字符。不同对象类型或 schema 版本即使规范 JSON 完全相同，也不得产生可互换的绑定摘要。

规范 JSON 使用无 BOM UTF-8：不保留无意义空白；整数使用十进制；禁止浮点数、`NaN` 和无穷值；数组保持各合同规定的规范顺序。未被具体合同声明为绑定字段的进程 ID、随机 ID、时间、审计序号和显示文本不得进入语义重放摘要。

字符串不执行 Unicode normalization。输入必须是 Unicode scalar value 序列：拒绝孤立 surrogate；若宿主表示先提供合法 surrogate pair，必须先还原为对应 scalar。`"` 和 `\` 分别编码为 `\"` 和 `\\`；U+0008、U+0009、U+000A、U+000C、U+000D 分别编码为 `\b`、`\t`、`\n`、`\f`、`\r`；其余 U+0000—U+001F 使用小写四位 `\u00xx`。除上述双引号、反斜杠和 U+0000—U+001F 的指定转义外，所有其余 Unicode scalar（包括普通 ASCII、U+007F 和非 ASCII）必须直接按 UTF-8 输出，禁止用 `\uXXXX` 或 `\/` 表示这些 scalar；`/`、U+2028 和 U+2029 不转义。对象键使用相同编码规则，并按未经 normalization 的 Unicode scalar（code point）序列升序排序。

`CanonicalTimestampV1` 是所有进入规范 JSON 的时间字段唯一合同：格式必须精确为 `YYYY-MM-DDTHH:MM:SS.sssZ`，固定三位毫秒并使用大写 `T` 和 `Z`。年份必须为 `0001`—`9999`，日期必须是有效 Gregorian 日期，小时只能为 `00`—`23`，分钟和秒只能为 `00`—`59`，不支持 leap second。`+00:00`、无小数秒、非三位小数秒和小写 `z` 等非规范形式必须在摘要前拒绝。内部时钟统一使用 UTC epoch milliseconds；更细精度必须在进入规范对象前向下截断至毫秒。

所有参与安全绑定的 v1 Schema 都是封闭字段集合：全部声明字段必须出现，未知字段一律拒绝，不允许实现自行选择是否把扩展字段纳入摘要。可选语义必须使用合同声明的判别联合，例如 `{"kind":"ABSENT"}` 或 `{"kind":"PRESENT","value":...}`；不得通过字段缺失或 `null` 表示。`ABSENT`、空字符串和空数组是三个不同值，只有具体 Schema 明确允许时才有效。除具体 Schema 明确声明的自身 `digest` 字段外，全部字段进入规范 JSON；自身 `digest` 不进入自身摘要。

`CanonicalRelativePathV1` 是仓库内实际文件或目录位置的唯一字符串合同：必须是使用 `/` 的非空仓库相对路径，不得以前导或尾随 `/` 表示。路径解析必须拒绝 `.`/`..` 段、空段、绝对路径、盘符、UNC、ADS、设备路径、尾随点/空格、保留设备名、Unicode 或 Windows 大小写折叠后碰撞，以及多个输入解析到同一最终对象的别名。仓库根不属于 `CanonicalRelativePathV1`，不得用空字符串、`.`、`./` 或 `/` 表示。工作区身份绑定规范绝对路径、卷标识和最终目录对象身份；仅对路径字符串做大小写转换不构成身份验证。

需要表示仓库根的合同必须使用以下封闭联合，不得引入字符串哨兵：

    RepositoryLocationV1 =
      ROOT { kind: "ROOT" }
      | PATH {
          kind: "PATH"
          path: CanonicalRelativePathV1
        }

下列对象的摘要输入必须唯一：

- `ActionSemanticDigestV1`：拒绝未知字段后的封闭语义动作；模型路线为完整规范 `AgentAction`，最终写回路线为 §4.4.2 的封闭协调器动作，两者都不含 Harness 生成的 `action_id`；
- `ActionInstanceDigestV1`：`schema_version`、Harness 生成的 `action_id` 和 `semantic_digest`；
- `ContextProjection`：裁剪完成、来源和裁剪决定已固定的最终投影；
- `ReferenceProfileManifestV1` 和 `LLMProfileManifestV1`：除自身 `digest` 外的全部规范字段；
- `MockPreparedModelRequestV1` 和 `OpenAIPreparedModelRequestV1`：分别以自身具体类型名作为 `object_type`，排除自身 `digest` 后绑定全部模式专属字段；联合别名 `PreparedModelRequestV1` 不具有独立摘要域；
- `ValidationManifestV1`：全部规范字段，不含显示文本；
- `FailureFingerprintV1`：规范测试身份、调用阶段失败事实、异常类型、规范消息、断言差异和项目栈帧；
- `CandidateIdentityV1`：§4.3 定义的 Snapshot、CandidateTree 和规范 `FinalDiffV1` 三重绑定，排除自身 `digest`；
- `FinalDiffV1`：§4.3 定义的封闭结构化净差异，排除自身 `digest`；
- 工作区前/后映像：规范路径、`ABSENT` 或原始文件字节摘要、文本元数据和最终对象身份；
- 语义检查结果：检查类型、输入树、环境、逐测试/诊断事实和稳定错误；排除执行时间、容器 ID 与审计序号。

规范编码器必须至少通过 CTV-01—CTV-07。`CanonicalizationProbeV1` 是仅用于兼容性测试的封闭 Schema：`{schema_version: 1, label: UTF-8 string, tags: UTF-8 string[], optional_note: ABSENT | PRESENT(UTF-8 string)}`，不进入业务数据模型。`CanonicalTimeProbeV1` 也仅用于兼容性测试，且为封闭 Schema：`{schema_version: 1, expires_at: CanonicalTimestampV1}`，不进入业务数据模型。

| 向量 | 输入 | 期望结果 |
|---|---|---|
| CTV-01 | `object_type=CanonicalizationProbeV1`；`{"tags":[],"schema_version":1,"optional_note":{"kind":"ABSENT"},"label":"x"}` | 规范字节为 `{"label":"x","optional_note":{"kind":"ABSENT"},"schema_version":1,"tags":[]}`；摘要 `1923bd578b2110ae145622050b4b6d10171c4b8fca4a383be06fa9f78d1ca782` |
| CTV-02 | 与 CTV-01 字段顺序不同但值相同 | 规范字节和摘要必须与 CTV-01 完全相同 |
| CTV-03 | `object_type=CanonicalizationProbeV1`；`{"label":"x","optional_note":{"kind":"PRESENT","value":""},"schema_version":1,"tags":[]}` | 摘要 `a9242ff2226e5d78c5efb1f8fb9adfe6c5a5c217d104c14691c38d3b95d10a3f`，且不得等于 CTV-01 |
| CTV-04 | CTV-01 增加未知字段、把 `optional_note` 写成 `null` 或省略该字段 | 在计算摘要前拒绝，不产生摘要 |
| CTV-05 | `object_type=CanonicalizationProbeV1`；`label` 依次为 `中文`、`"`、`\`、换行、`/`、分解形式 `e` + U+0301；其余字段为 `{"schema_version":1,"tags":[],"optional_note":{"kind":"ABSENT"}}` | 规范 JSON 为 `{"label":"中文\"\\\n/é","optional_note":{"kind":"ABSENT"},"schema_version":1,"tags":[]}`；完整 UTF-8 hex 为 `7b226c6162656c223a22e4b8ade696875c225c5c5c6e2f65cc81222c226f7074696f6e616c5f6e6f7465223a7b226b696e64223a22414253454e54227d2c22736368656d615f76657273696f6e223a312c2274616773223a5b5d7d`；按 §0.1 域分隔计算的 SHA-256 为 `1c757fec0a18509fe01156d8e7e359cc948d9abf1abcac0c999e00e15ed56a3a` |
| CTV-06 | `object_type=CanonicalTimeProbeV1`；`{"schema_version":1,"expires_at":"2026-07-24T09:30:15.123Z"}` | 规范 JSON 为 `{"expires_at":"2026-07-24T09:30:15.123Z","schema_version":1}`；完整 UTF-8 hex 为 `7b22657870697265735f6174223a22323032362d30372d32345430393a33303a31352e3132335a222c22736368656d615f76657273696f6e223a317d`；按 §0.1 域分隔计算的 SHA-256 为 `277d8e57122ba6ce91dfe28d5b724b2e5b0a85c3b9e33e951b19adcd86786125` |
| CTV-07 | 孤立 surrogate；或 `CanonicalTimestampV1` 使用 `+00:00`、无小数秒、1/2/4 位小数秒、小写 `z` 或 leap second | 必须在计算摘要前拒绝，且不产生摘要 |

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
    → 用户批准精确 FinalDiffV1
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
| 执行 | `ReferenceProfileManifestV1` 锁定的预构建、无网络、候选树只读执行镜像 | 宿主执行、运行中构建镜像或安装依赖 |
| LLM | 可注入 Mock LLM；一个 OpenAI 单轮适配器 | 高层 Agent 框架、自动重试与跨崩溃调用恢复 |
| WebUI | 本地 WebUI；公网 Mock Demo | 公网读取本地仓库、上传任意仓库、公网真实凭据 |

发布时必须在 lock file 和 README 的兼容性表中记录通过验证的精确依赖版本、Docker 镜像摘要和 Windows/Docker Desktop 环境。超出画像的输入以明确的不支持结果停止，不得静默降级。

### 1.4.1 `PythonProjectProfileV1`

v1 只支持 profile id 为 `python-src-py312-v1` 的参考画像：

#### `EditablePathPolicyV1`

    EditableOperationV1 =
      "CREATE" | "REPLACE"

    EditablePathPolicyV1 {
      schema_version: 1
      policy_id: "PYTHON_SRC_ONLY_V1"
      editable_directory_roots:
        exactly [CanonicalRelativePathV1("src")]
      allowed_operations:
        exactly ["CREATE", "REPLACE"], sorted CREATE < REPLACE
      digest
    }

全部字段必填并拒绝未知字段；`digest` 按 §0.1 对除自身外的全部字段计算。v1 只有上述发布包内建、只读实例，用户请求、普通配置、模型输出和仓库文本均不得提供、覆盖或扩大 editable roots、operation、policy id 或 digest；v1 不支持自定义根、glob、排除规则、临时例外、`DELETE` 或 `RENAME`。

`FinalDiffEntryV1.path` 只有在完成 `CanonicalRelativePathV1`、Windows/Unicode 别名和对象安全校验后，才可执行 editable root 匹配。对目录根 `root`，唯一匹配谓词是 `path` 以 `root + "/"` 开头；不得使用普通字符串前缀，且文件条目不得等于目录根本身。因此 `src/a.py` 和 `src/pkg/a.py` 匹配，`src`、`src-old/a.py`、`src2/a.py` 和路径别名不匹配。

`EditablePathPolicyV1` 只约束 Candidate 的 `CREATE`/`REPLACE`、验证和权威写回，不限制 `ListFilesAction`、`ReadFileAction` 或 `SearchTextAction`；读取仍受 Snapshot、路径安全、ContextProjection 和真实 LLM 披露规则约束。`EditablePathPolicyV1.digest` 必须进入 `ReferenceProfileManifestV1.digest`、`SnapshotTree.repository_policy_digest` 和治理 `policy_digest`，后三者只绑定同一内建实例，不能分别解析独立策略。

#### `ReferenceProfileManifestV1`

参考画像不是仅靠字符串约定的规则集合。发布包必须内置且只读地提供：

    ReferenceProfileManifestV1 {
      schema_version: 1
      profile_id: "python-src-py312-v1"
      requirements_lock_digest
      docker_image_digest
      docker_execution_profile_version: 1
      python_version
      pytest_version
      report_plugin_version
      ruff_version
      mypy_version
      check_plan_version
      editable_path_policy: EditablePathPolicyV1
      digest
    }

`digest` 按 §0.1 对除自身外的全部字段计算，因此自动绑定完整 `EditablePathPolicyV1`。目标仓库的 `requirements.lock` 必须精确匹配该 manifest 的 `requirements_lock_digest`；仅提供相同 profile id 不构成匹配。预检、基线、正式验证和发布证据必须使用同一个 manifest digest、editable policy digest 和 Docker image digest。用户请求只选择 `reference_profile_id`；editable policy、镜像和 execution profile 不能被独立选择。

`docker_image_digest` 唯一表示固定单平台 OCI manifest 原始字节的 `sha256:<64 lowercase hex>`，不得使用本地 image ID、image config digest、tag、manifest list/index digest或尚未由 registry 接受的显示值替代。Task 2 必须以固定 builder/output/media-type/压缩/attestation 参数导出该 manifest，把完全相同的 manifest 与 blobs 推送到仅监听 loopback、无凭据、任务结束即删除的临时 registry，证明本地 OCI manifest digest、registry 返回 RepoDigest 和按 digest 重拉后的 RepoDigest 三者完全一致，再生成绑定该 digest 的最终 `ReferenceProfileManifestV1`。

为避免自引用，最终 `ReferenceProfileManifestV1` 及任何包含其 `digest`/`docker_image_digest` 的文件不得进入它所绑定镜像的 build context、层、config、annotation 或 attestation；镜像只携带不引用最终 manifest 的工具和 execution-profile 版本证据。正式镜像的 GHCR 分发发生在 §8.4 的受保护 release gate，必须推送 Task 2 已冻结的同一 OCI manifest bytes，并证明 GHCR RepoDigest 仍等于 `docker_image_digest`。Task 2 的 loopback registry round-trip 不是发布，不使用或放宽 GHCR 凭据边界。正式镜像的构建、GHCR digest 分发和 wheel/manifest 一致性合同见 §8.2、§8.4 和 AC-30。

交付仓库必须提供一个与该 manifest 匹配、能走完基线、错误补丁反馈、修正、正式验证和写回流程的 reference fixture。该 fixture 是实现和端到端验收工件，不扩大正式输入范围。

#### `StaticProjectProfileCheckV1`

静态预检不运行项目代码，只验证可由本次 `RUNNING(PREFLIGHT)` 已创建并封存的唯一 `SnapshotTree`、其绑定的 `repository_policy_digest`、内置 manifest 和可信 Docker 配置证明的事实。Git 干净状态、工作区原始字节、文件系统对象和敏感路径属于 Snapshot 前置检查，不由 `detect_static` 重新判断：

| 项目 | 静态冻结要求 |
|---|---|
| Snapshot 身份 | 必须是当前 Run 在 PREFLIGHT 内创建并封存的唯一 `SnapshotTree`；`repository_policy_digest` 必须等于 Snapshot 前置检查冻结值 |
| 根目录文件 | 必须存在 `pyproject.toml` 和 `requirements.lock` |
| 源码布局 | 业务源码位于 `src/`；测试位于 `tests/` |
| Python 与工具 | 宿主适配器、容器和工具版本精确匹配 `ReferenceProfileManifestV1` |
| pytest | 配置只来自 `pyproject.toml`；允许内建插件及执行镜像内固定的机器可读报告插件 |
| Ruff / Mypy | 均必须在 `pyproject.toml` 中显式配置；未配置视为不支持，而不是跳过 |
| 依赖 | `requirements.lock` 摘要精确匹配 manifest；运行中不得安装或更新 |
| 文本 | 可编辑文件必须为 UTF-8 或 UTF-8 BOM、统一 LF/CRLF、具有末尾换行；混合换行文件不可编辑 |
| pytest 扩展 | 不支持自定义收集插件、动态下载插件或入口点自动加载 |

    StaticProjectProfileResult =
      SUPPORTED {
        profile_id
        reference_profile_digest
        snapshot_root_digest
        repository_policy_digest
      }
      | UNSUPPORTED_PROJECT {
        reference_profile_digest
        snapshot_root_digest
        repository_policy_digest
        reasons[]
      }

`ProjectAdapter.detect_static` 必须逐项验证静态画像并把输入 `SnapshotTree.root_digest` 写入结果。任何一项无法证明时返回上述 `UNSUPPORTED_PROJECT`，不得猜测、运行项目代码、重新读取权威工作区、重新执行 Git 干净检查、创建第二份 Snapshot 或跳过检查。Python/工具和 Docker 项只验证内建声明、版本与摘要的一致性；镜像和 execution profile 的实际可用性由 §4.1 的后续 readiness 检查负责。

以下规则由 §4.1 的 Snapshot 前置检查唯一负责：未跟踪文件只有在冻结 ignore 规则下被忽略且不命中 §1.4.2—1.4.3 时才允许存在；它们不得进入 `SnapshotTree`、容器、披露来源或最终差异。Git index、工作树和 HEAD 的比较必须禁用宿主 system/global 配置、外部 attributes/ignore 和可改变内容的 filter。任意规范路径在 Windows 大小写或 Unicode 折叠后发生碰撞时返回 `UNSUPPORTED_REPOSITORY`。

同一 Snapshot 前置检查还必须证明：index tree 等于 HEAD；不存在 unmerged、非 stage-0、intent-to-add、skip-worktree、assume-unchanged、tracked 字节漂移或不允许的 untracked 文件；有效 Git 配置满足 `core.autocrlf=false`，且 repository config 或 `.gitattributes` 未为任一 tracked 路径启用 `core.eol`、`eol`、`working-tree-encoding` 或内容 filter 转换。CRLF 文件只有在 HEAD blob 本身使用一致 CRLF、工作区原始字节与 blob 完全相同且补丁保持该换行风格时受支持；不能依赖 checkout 转换制造 CRLF 工作树。

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

### 1.4.2 可编辑路径、受保护验收与仓库策略工件

Candidate 中每个 `CREATE` 和 `REPLACE` 都必须命中冻结 `EditablePathPolicyV1`；以下保护集合是在 editable allowlist 之外继续执行的附加硬拒绝，不构成可编辑路径白名单。若同一条目同时违反保护集合和 editable policy，错误优先级以 §4.3 为准，返回 `PROTECTED_ARTIFACT_CHANGED`：

下列路径或类别在基线建立后不得由候选创建、修改、删除或重命名：

- `tests/**`；
- 根目录 `pyproject.toml`、`requirements.lock`；
- 任意 `conftest.py`、`sitecustomize.py`、`usercustomize.py`；
- `pytest.ini`、`tox.ini`、`setup.cfg`、`mypy.ini`、`.ruff.toml`、`ruff.toml`；
- `poetry.lock`、`uv.lock`、`pdm.lock`、`requirements*.txt`；
- `.gitignore`、`.gitattributes`、`.gitmodules`；
- 适配器识别出的其他会改变 pytest 收集、解释器启动、依赖解析、Ruff 或 Mypy 行为的入口。

根据唯一 `PYTHON_SRC_ONLY_V1`，`tests/**`、全部仓库根文件、`README*`、`docs/**`、`.github/**`、`.gitlab-ci.yml`、`Dockerfile*`、`scripts/**` 以及其他不属于 `src/**` 的路径都不可由 Candidate 创建或替换；该列表只用于说明，权威判定仍是上文目录段匹配算法。

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
- 当前候选规范 `FinalDiffV1` 中所有 `CREATE`/`REPLACE` 条目的完整 postimage 原始字节总量最多 128 KiB。
- 规范相对路径最多 240 个字符，单路径段最多 100 个字符。
- 执行副本与容器临时数据合计不得超过 512 MiB。
- 新文件在冻结的 Git ignore 规则下必须为非忽略文件。

限制作用于当前候选的累计净差异，而不是单次 `ApplyCandidatePatchAction`，因此不能通过多个小动作绕过。

### 1.4.5 `DockerExecutionProfileV1`

正式检查和 Agent 请求的检查都使用 `ReferenceProfileManifestV1.docker_image_digest` 指定的同一个锁定镜像；执行参数由同一 manifest 的 `docker_execution_profile_version=1` 唯一选择，并满足：

- `--network none`；非 root 用户；只读容器根文件系统；`cap-drop=ALL`；不挂载 Docker socket；
- 候选项目树挂载到 `/workspace` 且为只读；权威工作区、控制面数据库、凭据和事务备份不得挂载；
- `/tmp` 与工具缓存目录使用有界 tmpfs；Python bytecode、pytest cache、Ruff cache 和 Mypy cache 不写入项目树；
- 上限为 2 CPU、2 GiB 内存、256 PIDs、256 MiB tmpfs；单检查输出最多 4 MiB；
- 环境白名单固定且只允许 `PYTHONHASHSEED=0`、`TZ=UTC`、`LANG=C.UTF-8`、`LC_ALL=C.UTF-8`、`PYTHONDONTWRITEBYTECODE=1` 与 Harness 为固定报告通道注入的显式变量；变量名、值和报告变量集合由 execution profile v1 封闭定义，并禁用 pytest 插件自动加载；
- 每项检查使用全新容器和全新物化候选树，不共享 cache、字节码或运行时文件。

若参考项目无法在只读项目树下运行，它不属于 v1 支持画像；不得为兼容该项目把候选挂载改为可写。

## 1.5 v1 目标

- 自行实现顺序 Agent 主循环和可注入 LLM 抽象。
- 提供受路径围栏约束的 list、read、literal search、apply patch、run check 和 propose completion 动作。
- 用确定性代码实现 `ALLOW / ASK / DENY`、一次性动作批准和硬拒绝。
- 用运行级 `DisclosureGrant` 与逐请求 `DisclosureAuthorizationRecordV1` 控制真实 LLM 外发。
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
- Agent/Harness 正式运行中自动 commit、push、PR、依赖安装、镜像构建或对外发布；§8.4 的项目交付 CI 不属于 Agent 能力。
- 识别所有秘密格式、消除所有提示注入或对恶意宿主管理员提供隔离。
- 验证以破坏 Python 解释器、pytest、固定报告插件、容器内报告通道或检查进程为目的的主动恶意项目代码。
- 删除、重命名、二进制修改、文件模式变更或超过 3 文件的持久化事务。

# 2. 用户故事

## 2.1 US-01 配置并安全启动运行

作为受支持仓库的开发者，我希望先创建一个可见的准备中运行，再由系统执行静态预检和隔离的运行时兼容性验证，以便在任何模型调用或持久修改前发现不支持、不兼容或不安全的条件。

验收结果：

- 无效请求 Schema 在创建运行前被拒绝，不产生 `run_id`。
- 有效请求创建 `CREATED` 运行并冻结配置；用户能看到工作区、规范目标集合、reference/LLM profile digest 和 `RunLimitsV1` 摘要；reference profile 同时展示其绑定的执行镜像 digest。
- 启动后进入 `RUNNING(PREFLIGHT)`；脏仓库、不支持的 Git/项目画像、危险文件对象、未解决恢复、缺失 reference profile、其锁定执行镜像或凭据会使该运行进入 `STOPPED`。
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

- 首次真实请求前，用户看到冻结 LLM profile、供应商、模型、`endpoint_id = OPENAI_PUBLIC_API_V1`、由可信内建 endpoint 映射解析的目的主机 `api.openai.com`、允许的来源路径/类别、`NO_CONTENT_REDACTION_V1` 的明确含义、累计字节预算和有效期，并可批准或拒绝 `DisclosureGrant`；显示值不得来自环境、请求、普通配置或 DNS 文本。
- 用户拒绝或没有有效 Grant 时不得调用真实适配器。
- Grant 只对当前运行有效；LLM profile、endpoint、来源范围、数据类别、redaction profile、累计预算或有效期变化时，在总墙钟仍有正等待区间时重新进入精确绑定的 `WAITING_USER`。
- `DisclosureGrantSubjectV1` 不含 `consumed_bytes` 或 Grant 状态；正常预算消费不改变用户批准的 subject。
- 在有效 Grant 范围内，每个请求由控制面自动创建绑定精确请求摘要、实际来源和字节数的 `DisclosureAuthorizationRecordV1`，不要求用户逐请求点击。
- 请求摘要变化本身不会使 Grant 失效，但每个精确请求都必须有独立授权记录。
- 审计只保存摘要和元数据，不保存完整请求、完整响应或凭据。

## 2.5 US-05 依赖确定性护栏和一次性动作审批

作为监督 Agent 的用户，我希望硬拒绝动作始终被阻止，而最终写回批准只执行一次，以便权限不能由模型、仓库文本、披露 Grant 或旧批准扩大。

验收结果：

- `DENY` 不可被模型输出、配置、`DisclosureGrant` 或任何批准覆盖。
- `ASK` 展示完整动作语义摘要、不可变 `FinalWritebackSubjectV1`、理由和有效期；批准记录状态不属于 subject。
- 拒绝、过期、上下文变化或重复消费均不执行动作。
- `FinalWritebackApproval` 只被精确绑定的最终写回原子消费一次，状态变化不改变 subject digest。
- `FinalWritebackApproval` 与 `DisclosureGrant` 是独立类型，不能互相授权。

## 2.6 US-06 审查、持久化并恢复已验证 diff

作为开发者，我希望在原仓库发生修改前查看精确 diff 和验证证据，并在写回中断后使用明确恢复入口，以便写回内容与我批准的内容一致，且不确定状态不会被伪装成成功。

验收结果：

- 用户拒绝时权威工作区保持不变。
- 候选、`FinalDiffV1`、Manifest、验证证据、策略或工作区前映像变化使批准失效。
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
      reference_profile_id: "python-src-py312-v1"
      limits: RunLimitsV1
    }

    RunLimitsV1 {
      max_turns: 1..20
      max_llm_calls: 1..20
      max_run_wall_clock_seconds: 1..900
      user_wait_timeout_seconds: 1..300
      tool_timeout_seconds: 1..60
      target_check_timeout_seconds: 1..120
      full_check_timeout_seconds: 1..300
      baseline_timeout_seconds: 1..600
      formal_validation_timeout_seconds: 1..600
    }

    OptionalTemperatureMilliV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value_milli: 0..2000 }

    OptionalTopPMilliV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value_milli: 0..1000 }

    OptionalIntegerParameterV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: signed 64-bit integer }

    OpenAIFixedParametersV1 {
      schema_version: 1
      max_output_tokens: 1..8192
      temperature: OptionalTemperatureMilliV1
      top_p: OptionalTopPMilliV1
      seed: OptionalIntegerParameterV1
      response_format: "JSON_OBJECT"
    }

    OpenAIEndpointV1 = {
      endpoint_id: "OPENAI_PUBLIC_API_V1"
      scheme: "https"
      host: "api.openai.com"
      effective_port: 443
      base_path: "/v1"
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
        endpoint_id: "OPENAI_PUBLIC_API_V1"
        model
        adapter_version
        request_serializer_version
        fixed_parameters: OpenAIFixedParametersV1
        redaction_profile_id: "NO_CONTENT_REDACTION_V1"
        digest
      }

    validate_request(request) -> ValidatedRunRequest | CONFIG_INVALID
    create_run(validated_request) -> Run(CREATED, frozen_config)
    start_run(run_id) -> RUNNING(PREFLIGHT) | STOPPED

### 行为

1. `validate_request` 使用拒绝未知字段的版本化 Schema，只做语法、类型、枚举和基础值域校验；全部字段必填，解析器不得静默补默认值。单个 target node ID 必须为非空且不超过 1024 个 UTF-8 字节；重复值返回 `CONFIG_INVALID`，规范请求按 §0.1 排序后绑定。
2. 发布包内置只读、封闭的 v1 endpoint 映射 `OpenAIEndpointV1`；origin 比较精确按 `(scheme, host, effective_port)` 进行。`llm_profile_id` 和 `reference_profile_id` 必须解析到发布包内置的只读 manifest，且 OpenAI endpoint 只能由所选 `OpenAILLMProfileV1.endpoint_id` 在该映射中解析。请求、普通配置、环境变量和用户输入均不得修改 endpoint 映射或 origin。`ReferenceProfileManifestV1` 是 requirements lock、Docker image、Docker execution profile、工具版本、检查计划和 `EditablePathPolicyV1` 的唯一执行身份；不得再解析、选择或冻结第二个 execution 或 editable policy manifest/digest。精确模型、endpoint、适配器、请求序列化器、封闭固定参数、Mock 脚本、工具版本、镜像摘要和 Candidate 可编辑范围由两个 manifest 决定，不能由请求自由覆盖。serializer 只能把 `value_milli / 1000` 映射为供应商参数；所选模型不支持任一 `PRESENT` 参数时 profile 无效，不得静默删除。v1 不支持自定义 endpoint、其他真实 LLM provider 或自定义 editable root/policy；用户请求或普通配置提交 `base_url`、任意 URL、自定义 endpoint、未知 endpoint id、editable root、operation 或 policy 字段时，封闭 Schema 必须以 `CONFIG_INVALID` 在创建摘要或调用前拒绝。
3. `RunLimitsV1` 每个值只能等于或低于内建硬上限；WebUI 可以预填上述最大值，但 API 请求仍必须显式提交。子超时始终受剩余总墙钟约束。
4. `create_run` 冻结规范 target 集合、`RunLimitsV1`、LLM profile digest 和唯一的 `ReferenceProfileManifestV1.digest`，形成不含秘密的 `RunConfigSnapshot` 并创建 `CREATED`。
5. `start_run` 以原子状态转换进入 `RUNNING(PREFLIGHT)`，同时冻结 `started_at` 和 `run_deadline = started_at + max_run_wall_clock_seconds`，然后严格按以下顺序执行 Snapshot 前置检查、Snapshot 创建、静态项目画像和 readiness 检查；不得在预检运行项目代码。
6. 规范化工作区身份后，使用以该身份摘要为键的 Windows named mutex 或等价 Win32 跨进程锁；仅“当前进程内锁”不合格。
7. 若存在未解决 `PersistenceTransaction`，拒绝新运行并指向恢复入口。
8. 执行 Snapshot 前置检查：冻结有效 HEAD、repository config、`.gitattributes`、ignore 规则和 repository policy；`repository_policy_digest` 与治理 `policy_digest` 必须绑定冻结 `ReferenceProfileManifestV1.editable_path_policy.digest`，不得再解析其他 editable policy。验证 index tree 等于 HEAD、tracked 工作区原始字节与 HEAD blob 一致、不存在 unmerged、非 stage-0、intent-to-add、skip-worktree、assume-unchanged 或不允许的 untracked 文件，并拒绝不支持的 Git 转换、文件系统对象、敏感路径及 Windows/Unicode 路径碰撞。任一前置检查失败时不得创建 `SnapshotTree`、调用 `detect_static`、执行 readiness 检查或进入 `BASELINE`。
9. 只有全部 Snapshot 前置检查通过后，才从同一冻结 HEAD、已验证的 tracked 工作区原始字节和 repository policy 创建并封存本次 Run 唯一的不可变 `SnapshotTree`；允许的 ignored untracked 文件不进入 Snapshot。Snapshot 创建或完整性验证失败时以 `TREE_INTEGRITY_FAILED` 失败关闭，不得调用后续检查或创建第二份 Snapshot。
10. 只把第 9 步封存的 `SnapshotTree` 和冻结 `ReferenceProfileManifestV1` 交给 `ProjectAdapter.detect_static`。所有结果的 `snapshot_root_digest`、`reference_profile_digest` 和 `repository_policy_digest` 必须分别等于输入 Snapshot、冻结 manifest 和前置检查冻结值。静态画像失败以 `UNSUPPORTED_PROJECT` 停止，且不执行后续 readiness 或 `BASELINE`。
11. 静态画像通过后，验证 `ReferenceProfileManifestV1`、其绑定的镜像摘要、execution profile 版本和能力参数满足 §1.4.1 与 §1.4.5；该步骤验证实际 reference image/execution profile readiness，不重新创建或修改 Snapshot。
12. 只有选中的 LLM profile 为 `OpenAILLMProfileV1` 时才检查凭据状态和安全后端，并验证 profile 的 `endpoint_id` 能唯一解析为 `OpenAIEndpointV1`、OpenAI 适配器的有效目标与该可信映射一致；检查不读取或记录秘密。
13. 上述步骤全部通过后进入 `RUNNING(BASELINE)`，由 §4.5 在同一 `SnapshotTree` 上执行 `RuntimeCompatibilityCheckV1`；静态预检失败和动态基线阻断必须使用不同证据与错误语义。

### 输出

- 请求无效：`CONFIG_INVALID`，无 `run_id`。
- 请求有效：`RunCreated(run_id, config_snapshot_id, status=CREATED)`；快照绑定 LLM profile digest 和唯一的 reference profile digest。
- 预检：`AdmissionResult = ACCEPTED | REJECTED(error)`，并形成相应生命周期结果。

### 错误

`CONFIG_INVALID`、`LLM_ENDPOINT_MISMATCH`、`WORKTREE_DIRTY`、`UNSUPPORTED_REPOSITORY`、`UNSUPPORTED_PROJECT`、`UNSUPPORTED_FILESYSTEM_OBJECT`、`SENSITIVE_TRACKED_FILE`、`TREE_INTEGRITY_FAILED`、`EXECUTION_PROFILE_UNAVAILABLE`、`CREDENTIAL_MISSING`、`CREDENTIAL_BACKEND_UNSAFE`、`RECOVERY_BLOCKS_NEW_RUN`、`WORKSPACE_LOCKED`。

所有预检拒绝发生在 LLM 调用、项目执行和权威工作区修改前。

### 确定性测试

- 无效 Schema 不产生 Run。
- 有效请求先产生 `CREATED`，再进入 `PREFLIGHT`。
- 重复、超过 20 个、超长 target ID，未知 profile、遗漏限制字段和放宽硬上限均为 `CONFIG_INVALID`；target 输入排列不同但集合相同时形成相同规范摘要。
- 用户请求或普通配置含 `base_url`、自定义 URL 或未知 endpoint id 时为 `CONFIG_INVALID`，且不创建摘要或 Run。
- 用户请求或普通配置含 editable root、operation、policy id/digest 或其他策略覆盖字段时为 `CONFIG_INVALID`；内建 `ReferenceProfileManifestV1` 缺少或篡改 `EditablePathPolicyV1` 时同样以 `CONFIG_INVALID` 拒绝，且不得创建 Run。
- 冻结 profile 的 endpoint、可信映射解析或 OpenAI 适配器有效目标在预检不一致时为 `LLM_ENDPOINT_MISMATCH`；断言 LLM/网络、Grant 消费、authorization record 创建和 turn/call 增量均为零。
- 为每种预检拒绝使用固定仓库或 stub；断言 LLM、项目执行容器和持久化调用次数均为零，reference image/execution profile readiness probe 只在其有序步骤实际到达时调用。
- 预检不得调用 pytest、Ruff、Mypy 或导入目标项目；运行时兼容性只在 `BASELINE` 检查。
- 使用记录调用顺序的 stub 断言成功路径严格为 workspace identity/lease → recovery gate → Snapshot 前置检查 → 创建并封存唯一 `SnapshotTree` → `detect_static` → reference image/execution profile readiness → OpenAI 模式 credential/endpoint readiness → `BASELINE`，且 `detect_static` 精确接收刚封存的 Snapshot。
- Snapshot 前置检查失败时，Snapshot 创建、`detect_static`、readiness 和 `BASELINE` 调用次数均为零；Snapshot 创建或完整性验证失败时返回 `TREE_INTEGRITY_FAILED` 且后三者均为零；静态画像失败时 Snapshot 创建次数为一且 readiness/`BASELINE` 为零；readiness 失败时不进入 `BASELINE`。
- `detect_static` 尝试读取权威工作区、重新执行 Git 干净检查或创建第二份 Snapshot 时失败；即使 Snapshot 已在 PREFLIGHT 建立，任何 Agent 文件动作和 `ApplyCandidatePatchAction` 在完整 PREFLIGHT 与 BASELINE 通过前仍不得分发。
- 两个进程竞争同一规范工作区时最多一个获得 lease。

## 4.2 FR-LOOP：主循环、动作协议、上下文和停止

### 4.2.1 核心接口与状态

    LLMAdapter.generate(PreparedModelRequestV1) -> ModelResponse
    ActionParser.parse(ModelResponse) -> AgentAction | ParseError
    ToolDispatcher.dispatch(AgentAction, RunContext) -> ActionResult
    StopEvaluator.evaluate(RunState, Evidence) -> Continue | Validate | Stop

`PreparedModelRequestV1` 是 `MockPreparedModelRequestV1 | OpenAIPreparedModelRequestV1` 的封闭联合。Mock adapter 只接受 `mode=MOCK` 变体，OpenAI adapter 只接受 `mode=OPENAI` 变体；控制面必须在 turn/call 计数前验证所选 adapter、冻结 profile 与具体请求变体一致。

正式运行状态：

    RunStatus = CREATED | RUNNING | WAITING_USER | RECOVERY_REQUIRED | SUCCEEDED | STOPPED
    RunPhase  = PREFLIGHT | BASELINE | AGENT_LOOP | FORMAL_VALIDATION | PERSISTENCE

公网 Demo 使用独立状态：

    DemoRunStatus = DEMO_CREATED | DEMO_RUNNING | DEMO_WAITING_USER | DEMO_COMPLETED | DEMO_FAILED

`DEMO_COMPLETED` 不是正式 `RunStatus`，不能生成 `VerifiedCandidate`、`FinalWritebackApproval`、`DisclosureGrant` 或权威工作区写入。

### 4.2.2 封闭动作 Schema

所有模型响应必须是一个 JSON 对象，且只包含一个动作；动作外自由文本、未知字段和多个动作均为无效输出。公共字段和具体动作字段位于同一个拒绝未知字段的对象中，所有下列字段均为必填字段，不应用解析器默认值补齐。

模型提交的公共信封：

    ActionEnvelope {
      schema_version: 1
      action_type: closed literal
    }

封闭联合及字段：

    ListFilesQueryV1 {
      schema_version: 1
      root: RepositoryLocationV1
      recursive: bool
      max_entries: 1..500
      digest
    }

    SearchTextQueryV1 {
      schema_version: 1
      query: literal UTF-8 string, 1..256 bytes
      roots[]: 1..8 unique RepositoryLocationV1
      case_sensitive: bool
      context_lines: 0..2
      max_results: 1..100
      digest
    }

    ListFilesCursorV1 {
      schema_version: 1
      cursor_type: "LIST_FILES_CURSOR_V1"
      visible_tree_digest
      query_digest
      next_directory_rank: 0 | 1
      next_canonical_path: CanonicalRelativePathV1
      digest
    }

    SearchTextCursorV1 {
      schema_version: 1
      cursor_type: "SEARCH_TEXT_CURSOR_V1"
      visible_tree_digest
      query_digest
      next_canonical_path: CanonicalRelativePathV1
      next_match_index: non-negative integer
      digest
    }

    OptionalListFilesCursorV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: ListFilesCursorV1 }

    OptionalSearchTextCursorV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: SearchTextCursorV1 }

    ListFilesAction = ActionEnvelope & {
      action_type: "list_files"
      root: RepositoryLocationV1
      recursive: bool
      max_entries: 1..500
      cursor: OptionalListFilesCursorV1
    }

    ReadFileAction = ActionEnvelope & {
      action_type: "read_file"
      path: CanonicalRelativePathV1
      start_line: >=1
      line_count: 1..400
      max_bytes: 1..32768
    }

    SearchTextAction = ActionEnvelope & {
      action_type: "search_text"
      query: literal UTF-8 string, 1..256 bytes
      roots[]: 1..8 unique RepositoryLocationV1
      case_sensitive: bool
      context_lines: 0..2
      max_results: 1..100
      cursor: OptionalSearchTextCursorV1
    }

    ApplyCandidatePatchAction = ActionEnvelope & {
      action_type: "apply_candidate_patch"
      base_candidate_digest
      patch_format: "UNIFIED_DIFF_V1"
      patch_text: UTF-8, <=128 KiB
    }

`ApplyCandidatePatchAction` 不携带 editable root、operation allowlist 或 policy digest；控制面只能从当前 Run 冻结的 `ReferenceProfileManifestV1.editable_path_policy` 取得这些值。

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

`RepositoryLocationV1.ROOT` 精确表示整个 `SnapshotTree`。`ListFilesAction.root=PATH` 时该路径必须指向现有目录；`SearchTextAction.roots[].PATH` 可以指向现有、对象类型受支持的普通文件或目录，普通文件是否属于可搜索文本由下文唯一的 `SupportedTextFileV1` 分类器决定。直接指向 `NON_TEXT_FILE` 的 search 成功返回零匹配并令本次 `skipped_non_text_count=1`，不得把同一文件改为动作 Schema 错误。`SearchTextAction.roots[]` 包含 `ROOT` 时，`ROOT` 必须是唯一元素；其他组合不得为空、重复或在 Windows/Unicode 折叠规则下形成别名。`ReadFileAction`、补丁中的文件路径和其他实际仓库对象路径继续使用 `CanonicalRelativePathV1`。

文件工具结果的顺序分别冻结：`ListFilesResult.entries[]` 使用下文 `(directory_rank, canonical_path)`；`ReadFileResult` 正文保持原文件递增源码行顺序；`SearchTextResult.matches[]` 按 `(canonical_path, line, column)` 排序。Search v1 只支持字面量，不支持正则表达式。Search 先把所有 roots 覆盖的普通文件按规范路径去重并排序，再逐文件按递增 `(line, column)` 扫描；因此重叠 roots 不会产生重复匹配或重复 `skipped_non_text_count`。

模型不得提交 `action_id`。`ActionParser` 成功得到封闭 `AgentAction` 后，Harness 使用可注入 ID 生成器创建：

    ActionInstanceV1 {
      schema_version: 1
      action_id: Harness-generated non-empty UTF-8 string, <=128 bytes
      action: AgentAction
      semantic_digest
      instance_digest
    }

`semantic_digest` 使用 `ActionSemanticDigestV1` 域对包含 `cursor` 在内的精确 `AgentAction` 计算；`instance_digest` 使用 `ActionInstanceDigestV1` 域对 `{schema_version, action_id, semantic_digest}` 计算。`ListFilesQueryV1.digest` 和 `SearchTextQueryV1.digest` 分别只绑定动作中除 `cursor` 外的对应查询字段；查询摘要不能被 continuation 自身改变。ID 只负责审计和动作—结果关联，不能影响重复动作、策略缓存、无进展或语义重放判断。注入时钟和 ID 生成器时，相同脚本必须可重复产生相同实例序列。

    OptionalArtifactRefV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: artifact_ref }

    ActionErrorV1 {
      error_code
      bounded_message
      evidence_ref: OptionalArtifactRefV1
    }

    OptionalActionErrorV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: ActionErrorV1 }

动作结果使用公共信封：

    ActionResult {
      schema_version: 1
      action_id: Harness-generated
      instance_digest
      semantic_digest
      status: SUCCEEDED | REJECTED | FAILED
      result_type
      payload_ref: OptionalArtifactRefV1
      error: OptionalActionErrorV1
    }

List、Read 和 Search 必须共享唯一的 `SupportedTextFileV1` 分类器，并只对当前动作可见的 `SnapshotTree` 或 `CandidateTree` 原始文件字节分类。只有同时满足以下条件的单链接普通文件才是受支持文本文件：

1. 原始字节以零个或一个 UTF-8 BOM 开始，移除该可选 BOM 后可按严格 UTF-8 解码为 Unicode scalar value 序列；
2. 解码正文不含 U+0000；
3. 换行只使用统一 LF 或统一 CRLF，不含裸 CR 或混合换行；
4. 正文具有末尾换行，因而能唯一构造 §4.3 的 `TextMetadataV1`。

空文件、没有末尾换行、混合换行、包含 U+0000、无效 UTF-8 或其他无法构造 `TextMetadataV1` 的普通文件都分类为 `NON_TEXT_FILE`。该名称只表示“不满足 v1 受支持文本合同”，不声称文件一定是二进制，也不构成仓库准入拒绝；非文本 tracked 普通文件仍可进入 Snapshot 和 List，但不能由 Read/Search 解释为正文，也不会因此获得二进制补丁能力。

    ListFilesEntryV1 =
      DIRECTORY {
        path: CanonicalRelativePathV1
        kind: "DIRECTORY"
        size_bytes: ABSENT
        text_profile: ABSENT
      }
      | TEXT_FILE {
        path: CanonicalRelativePathV1
        kind: "TEXT_FILE"
        size_bytes: PRESENT(non-negative integer)
        text_profile: PRESENT(TextMetadataV1)
      }
      | NON_TEXT_FILE {
        path: CanonicalRelativePathV1
        kind: "NON_TEXT_FILE"
        size_bytes: PRESENT(non-negative integer)
        text_profile: ABSENT
      }

`ListFilesEntryV1` 的全部字段必填并拒绝未知字段；三种变体以外的字段组合在结果发布前以 `INTERNAL_ERROR` 失败关闭，不得返回部分结果。`size_bytes` 是当前动作可见树中该普通文件完整原始字节的长度。List 的稳定排序键为 `(directory_rank, canonical_path)`：目录的 `directory_rank=0`，两种普通文件均为 `1`，因此目录整体优先，全部普通文件不按文本类型分组而只按规范路径排序。`ListFilesCursorV1` 指向下一条尚未返回的严格排序键；续接从该键开始，跨页不得重复或遗漏。

各动作的规范结果为：

- `ListFilesResult`：`entries: ListFilesEntryV1[]`、`truncated` 与 `next_cursor: OptionalListFilesCursorV1`；每个返回条目都使用上述封闭变体和稳定排序。
- `ReadFileResult`：`path`、`file_digest`、实际 `start_line/end_line`、`eof` 和有界正文。Read 只接受分类为 `TEXT_FILE` 的普通文件；目标通过路径和对象安全检查但分类为 `NON_TEXT_FILE` 时返回 `FILE_NOT_TEXT`，`ActionResult.status=FAILED`、`payload_ref=ABSENT`、`error=PRESENT(ActionErrorV1.error_code=FILE_NOT_TEXT)`，且不得返回正文或部分 `ReadFileResult`。`FILE_NOT_TEXT` 优先于行范围检查；受支持文本的 `start_line` 超过文件末行返回 `READ_RANGE_OUT_OF_BOUNDS`，请求范围越过 EOF 时返回已有内容并令 `eof=true`。
- `SearchTextResult`：`matches[{path, line, column, excerpt}]`、`truncated`、`next_cursor: OptionalSearchTextCursorV1` 和 `skipped_non_text_count`；只搜索同一分类器判定的 `TEXT_FILE`。每个 `excerpt` 是从匹配行及请求的 context 行确定性截取的至多 1024 个无 BOM UTF-8 字节，并只能在 Unicode scalar 边界截断。每个按稳定遍历顺序实际检查、并在本次结果继续点之前跳过的 `NON_TEXT_FILE` 使 `skipped_non_text_count` 增加一次；目录不计数。`SearchTextCursorV1` 绑定下一规范文件路径和该文件内下一零基 match index；对无匹配和非文本文件也必须推进文件位置，跨页不得重复或遗漏匹配或重复计数同一非文本文件。
- `ApplyCandidatePatchResult`：新 `candidate_digest`、规范 `FinalDiffV1.digest`、累计文件数和累计字节数。
- `RunCheckResult`：对应 `CheckResult` 引用；原始输出不直接内嵌进模型上下文。
- `ProposeCompletionResult`：`VALIDATION_REQUESTED` 或结构化拒绝；它不是成功记录。

面向模型的单个结果正文统一不超过 32 KiB。List/Search 因条目、匹配或正文上限截断且仍有可扫描内容时，必须返回 `truncated=true` 与类型匹配的 `next_cursor=PRESENT`；完整结果必须返回 `truncated=false` 与 `next_cursor=ABSENT`，其他组合在发布前以 `INTERNAL_ERROR` 失败关闭。Read 通过实际 `start_line/end_line/eof` 继续，不使用 cursor。每个 cursor 都以自身具体类型名作为 §0.1 `object_type`，摘要排除自身并绑定 `schema_version`、`cursor_type`、当前动作可见的 `SnapshotTree` 或 `CandidateTree` 摘要、query digest 和下一扫描位置；List/Search cursor 不能互换。cursor 的 tree digest 与当前可见树不同时返回 `CONTINUATION_STALE`；类型、摘要、query digest、位置或规范编码非法时返回 `CONTINUATION_INVALID`。两类错误均为 `ActionResult.status=FAILED`、`payload_ref=ABSENT`，不得返回或持久化部分结果。不允许截断的 patch、check 和 completion 结果超限时返回稳定错误，不能把部分结果伪装成完整结果。动作已成功执行但客观检查为 `FAIL` 时，`ActionResult.status=SUCCEEDED` 且 `CheckResult.status=FAIL`；只有动作未能按合同完成时才使用 `FAILED`。

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
3. 当前候选摘要、累计 `FinalDiffV1` 统计和最近动作结果；
4. 未消费反馈，按严重级别、生成时间和稳定 ID 排序；
5. 本次选中的仓库记忆；
6. 经工具显式读取的有界文件片段和搜索结果。

裁剪顺序固定为：先删除最旧记忆，再删除最旧成功动作摘要，再缩减非最近文件片段；Harness 协议、目标测试、当前候选绑定和最近失败反馈不得被裁掉。规范压缩后强制内容仍超过 64 KiB 时，以 `CONTEXT_BUDGET_EXCEEDED` 停止，不得静默截断成语义无效请求。

投影必须按 §4.4.4 输出带来源的 `RequestContentSegmentV1`；每段正文、类别、相对路径、字节数和摘要在裁剪完成后同时冻结，以供披露授权和测试重放。

### 4.2.5 主循环行为

1. 同一运行任一时刻最多一个活动 `AgentTurn`。
2. 每轮基于当前候选、有限记忆、未消费反馈和预算生成一个 `ContextProjection`。
3. Mock 模式只有在 `MockPreparedModelRequestV1` 已冻结、其 profile/script/adapter 绑定已验证且即将调用 Mock adapter 时，控制面才原子创建 `AgentTurn` 并递增 turn/call；真实模式只有在有效 Grant、`OpenAIPreparedModelRequestV1` 和逐请求授权事务完成且即将调用 OpenAI adapter 时才执行同一计数点。该原子点之前的投影准备、请求冻结、授权展示和 `WAITING_USER` 均不创建 turn 或消耗 call。计数成功后，即使适配器调用前发生可捕获控制面失败、真实进程崩溃、调用失败或输出无效，该 turn/call 也已消费且不得重用；可捕获的调用前失败可记录 `NOT_ATTEMPTED`，真实进程崩溃不产生原进程调用结果，重启按 §4.2.7 停止且不恢复 turn。
4. 动作依次经过 Schema、候选绑定、路径、阶段和策略校验，再分发。
5. 结果发布为结构化 `ActionResult`；下一 turn 原子绑定并消费选中的 `feedback_refs`。
6. `ProposeCompletionAction` 只请求进入 `FORMAL_VALIDATION`，不能声明成功。
7. `StopEvaluator` 只负责 `Continue | Validate | Stop`；它不能发布 `SUCCEEDED`。正式成功只能由 `PersistenceCoordinator` 在 §4.6 的全部条件满足后发布。

### 4.2.6 取消、预算与无进展

- 用户通过 `CancelRun` 提交取消请求。动作边界、等待用户状态以及持久化首次替换前是安全点。
- 若持久化已发生首个文件替换，取消保持待处理，必须先完成事务判定或进入恢复，不能中断并假定回滚成功。
- `run_deadline` 在持久化中的唯一安全点和过期结果由 §4.6 定义；通用超时规则不得授权 deadline 后继续修改权威工作区。
- 相同候选上，相同 `ActionSemanticDigestV1` 得到相同语义结果连续 3 次时，以 `REPEATED_ACTION_LIMIT` 停止；更换 Harness 实例 ID 不会重置计数。
- 连续 6 个 turn 没有产生 `ProgressMarker` 时，以 `NO_PROGRESS_LIMIT` 停止。
- `ProgressMarker` 只包括：候选树摘要变化；当前候选产生此前未见的语义检查结果；进入正式验证。语义检查结果按 §0.1 计算，排除时间、随机 ID、容器 ID 和审计序号；单纯重复读取、搜索、相同失败或只改变易变字段不算进展。
- 冻结 `RunLimitsV1` 的 turn、LLM call 和总墙钟是整个正式运行的实际上限，且不得超过 §5.1 的内建硬上限；单动作、目标检查、用户等待和正式验证超时只是子上限，不能扩大总上限。Schema 无效、模型输出无效和 LLM 调用失败均消耗已开始的 turn/call；在预算不足以开始下一动作、等待或检查时必须于副作用前停止。

超时映射是封闭的，不允许适配器自行选择：

| 操作 | 子超时 |
|---|---|
| Agent `list/read/search/apply patch/propose completion` | `tool_timeout_seconds` |
| Agent `TARGET_TESTS` | `target_check_timeout_seconds` |
| Agent `FULL_PYTEST`、`RUFF`、`MYPY` | `full_check_timeout_seconds` |
| BASELINE 的每次 collect-only、完整 pytest、目标复跑、Ruff、Mypy | 单项 `full_check_timeout_seconds`，且共同受 `baseline_timeout_seconds` 限制 |
| BASELINE 整体 | `baseline_timeout_seconds` |
| FORMAL_VALIDATION 的每个 pytest/Ruff/Mypy 子检查 | 单项 `full_check_timeout_seconds`，且共同受 `formal_validation_timeout_seconds` 限制 |
| FORMAL_VALIDATION 整体 | `formal_validation_timeout_seconds` |
| 用户等待 | `user_wait_timeout_seconds` |
| 全部正常操作 | 同时受剩余 `run_deadline` 限制；取适用限制中的最小正值；持久化过期按 §4.6 失败关闭 |

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
- `DISCLOSURE_GRANT.subject_digest` 必须精确等于 §4.4.3 的 `DisclosureGrantSubjectV1.digest`；`FINAL_WRITEBACK.subject_digest` 必须精确等于 §4.4.2 的 `FinalWritebackSubjectV1.digest`。两类 subject 都不含可变状态或消费计数。
- 用户决定必须同时绑定 `wait_id`、`run_id`、`wait_kind` 和 `subject_digest`。`WaitContext.expires_at = min(created_at + user_wait_timeout_seconds, run_deadline)`，并必须等于对应 subject 的 `expires_at`；若创建时已无正的等待区间，则在创建 subject 或 `WaitContext` 前以总墙钟预算耗尽停止。
- `DISCLOSURE_GRANT` 等待被精确批准后回到来源 `AGENT_LOOP` 的新执行入口；`FINAL_WRITEBACK` 等待被精确批准后进入 `RUNNING(PERSISTENCE)`。
- 等待被拒绝、过期或取消时进入带稳定原因的 `STOPPED`。`WaitKind`、subject 或绑定变化使旧决定失效；只有来源 phase 重新产生新的 subject 后才可创建新等待。
- `WAITING_USER` 时间计入 `max_run_wall_clock_seconds`，但不创建 `AgentTurn`，也不消耗 LLM call。披露范围不足、累计预算不足、Grant 过期或撤销时，只要仍有正的等待区间就必须创建新的 `DISCLOSURE_GRANT` 等待；不得在“等待或停止”之间自由选择。
- 最终候选、Manifest 或验证证据变化时必须重新进入适用的 `AGENT_LOOP` 或 `FORMAL_VALIDATION`；工作区前映像、配置、策略、适配器或执行 profile 变化时停止，不得只创建新的最终批准。
- `RUNNING(PERSISTENCE)` 可进入 `SUCCEEDED`、`STOPPED` 或 `RECOVERY_REQUIRED`。
- `RECOVERY_REQUIRED` 只能由 §4.6 的恢复结果进入 `SUCCEEDED`、`STOPPED` 或保持不变。
- 非持久化阶段和两类 `WAITING_USER` 进程重启统一停止为 `PROCESS_RESTARTED_DURING_RUN`，不得恢复等待、turn 或重发 LLM 请求。

### 4.2.8 错误

- 模型输出无效：`MODEL_OUTPUT_INVALID`；连续两次无效则 `MODEL_OUTPUT_INVALID_LIMIT` 停止。
- 动作阶段不允许：`ACTION_NOT_ALLOWED_IN_PHASE`，形成反馈；硬 `DENY` 不进入审批。
- Read 的目标通过路径和对象安全检查但不是 `SupportedTextFileV1` 时返回 `FILE_NOT_TEXT`，不得发布正文或部分 `ReadFileResult`。
- List/Search continuation 的可见树变化返回 `CONTINUATION_STALE`；cursor 类型、摘要、查询或位置非法返回 `CONTINUATION_INVALID`；两者都不得发布部分 payload。
- Harness 构造的动作结果违反封闭结果 Schema 时以 `INTERNAL_ERROR` 失败关闭，不得把非法组合或部分 payload 发布给下一 turn。
- LLM 调用失败：`LLM_CALL_FAILED` 并停止；v1 不自动重试。
- 准备请求与冻结 profile/adapter 不一致，或响应后控制面失败：`INTERNAL_ERROR` 并停止；前者必须发生在请求摘要、turn/call 计数和适配器调用前。
- 等待拒绝、过期和绑定变化分别使用 `WAIT_REJECTED`、`WAIT_EXPIRED`、`WAIT_STALE`。
- 预算、重复动作、无进展和取消使用各自稳定错误码。

### 确定性测试

脚本化 Mock LLM 依次返回读取、失败补丁、检查、修正补丁和 completion；每轮必须从冻结 Mock profile 构造不含任何 OpenAI 字段的 `MockPreparedModelRequestV1`，由控制面记录 `authorization_record_ref=ABSENT` 的 `LLMCallResultV1`，并断言凭据、Grant、authorization record 与网络调用次数均为零。相同 Mock profile、消息和来源产生相同 request digest 与 `canonical_byte_count`；script、消息或来源变化使 digest 变化。Mock 请求加入 endpoint/model/fixed parameters、OpenAI 请求加入 script 字段，或具体变体与 profile/adapter 不一致，均在请求摘要、turn/call 计数和适配器调用前拒绝；控制面尝试为 Mock 构造 `authorization_record_ref=PRESENT` 或 `DELIVERY_UNKNOWN` 的结果候选时，以 `INTERNAL_ERROR` 阻止结果发布，已消费的一次 turn/call 不回退且不得重试。另断言动作顺序、上下文摘要、反馈消费、无进展谓词和停止结果完全可重复；以模型提交 `action_id` 断言 Schema 拒绝，并让可注入 ID 生成器为同一语义动作产生不同实例 ID，断言 `semantic_digest` 不变、`instance_digest` 不同且第三次相同语义结果触发 `REPEATED_ACTION_LIMIT`。文件动作测试必须覆盖 list/search 使用 `ROOT`、使用 `PATH("src")`、list 的 `PATH` 指向非目录、search 的 `PATH` 指向文本文件、非文本普通文件或目录，以及空字符串、`.`、`./`、`/`、`src/` 和 `[ROOT, PATH(...)]` 在动作执行前被拒绝；直接搜索非文本普通文件必须成功返回零匹配和 `skipped_non_text_count=1`。使用 FakeClock/Executor 逐项命中 §4.2.6 的每个子超时和更短 `run_deadline`，并断言披露等待、授权不足、具体请求尚未冻结或请求/profile/adapter 尚未匹配时 turn/call 计数不变，越过原子计数点后的失败则精确增加一次。

文件结果测试另使用同一 Fake Tree 构造目录、UTF-8 LF、UTF-8 BOM + CRLF、PNG/随机二进制、无效 UTF-8、U+0000、混合换行、无末尾换行和空文件。断言前三类分别形成 `DIRECTORY`、`TEXT_FILE`、`TEXT_FILE`，其余普通文件形成 `NON_TEXT_FILE`；所有普通文件的 `size_bytes` 等于完整原始字节长度。未知 `kind`、目录携带 `size_bytes`、`TEXT_FILE` 缺少 `text_profile`、`NON_TEXT_FILE` 携带 `text_profile` 或任一其他非法组合均以 `INTERNAL_ERROR` 阻止整个结果发布。对同一文件，List、Read 和 Search 必须得到相同分类；Read 非文本文件返回 `FILE_NOT_TEXT` 且无正文，Search 只对实际检查并跳过的非文本普通文件增加 `skipped_non_text_count`。相同树、query 和边界必须产生相同 cursor、条目、匹配、类型与计数；逐页收集结果必须与未分页结果完全相同且无重复/遗漏。另分别篡改 cursor 类型、自身摘要、query digest、位置和 visible tree digest，断言前四者返回 `CONTINUATION_INVALID`、树变化返回 `CONTINUATION_STALE`，全部零部分结果；Search 覆盖重叠 roots、无匹配文本、非文本文件、单条长行和 32 KiB 截断，证明扫描位置总能推进且 excerpt 不超过 1024 字节。

## 4.3 FR-WS：快照、路径、严格补丁和候选树

### 输入

Snapshot 创建入口是已取得 workspace lease、通过 §4.1 Snapshot 前置检查并冻结 HEAD、tracked 工作区原始字节和 repository policy 的 Git 工作区；该入口不要求静态画像、readiness 或完整 PREFLIGHT 已经通过。

Candidate 操作入口是本次 Run 已封存的唯一 `SnapshotTree`，以及符合 §4.2.2 的文件动作或 `ApplyCandidatePatchAction`；只有完整 PREFLIGHT 和 BASELINE 已通过且当前 phase 允许 Candidate 操作时，才可使用该入口。

### 行为

1. 在 `RUNNING(PREFLIGHT)` 内，从同一冻结 HEAD、经逐文件原始字节校验的 tracked 工作区和 repository policy 创建并封存本次 Run 唯一的不可变 `SnapshotTree`；创建后不得重新读取权威工作区形成第二份 Snapshot。
2. Snapshot 的创建不开放 Candidate 操作；完整 PREFLIGHT 和 BASELINE 通过前，任何 Agent 文件动作或 `ApplyCandidatePatchAction` 都必须拒绝且无候选副作用。
3. `CandidateRevision` 从不可变父候选派生；不得原地修改 `SnapshotTree` 或权威工作区。
4. 所有 Agent 路径必须是使用 `/` 的规范相对路径；拒绝绝对路径、`..`、盘符、UNC、ADS、设备名、尾随点/空格和保留路径。
5. 文件访问在打开前后验证最终对象身份、授权根、reparse 状态和 link count；任一步不确定即拒绝。
6. `ApplyCandidatePatchAction` 必须先完整解析全部 patch 条目，再按固定优先级执行 patch/Schema、规范路径与工作区边界、文件系统对象与敏感路径、保护工件、`EditablePathPolicyV1` 和候选硬上限检查；只有全部条目通过后才可原子派生一个 `CandidateRevision`。任一条目失败时整个动作无候选副作用，不得先应用合法条目。
7. `CREATE` 和 `REPLACE` 使用同一冻结 editable root 与 operation 检查；每个条目都必须是 `src/` 的严格后代。`CREATE` 还必须在冻结 Git ignore 规则下为非忽略文件；现有文件不会因为已在 Snapshot 中就获得 `src/**` 之外的替换权限。
8. 每次 Candidate 派生后，Harness 必须从当前 `CandidateTree` 重算完整 `FinalDiffV1`，并在发布 Candidate 前重新验证每个 entry 的 operation/path 与冻结 `EditablePathPolicyV1`。任一越界 entry 返回 `PATCH_PATH_NOT_EDITABLE` 且不发布该 Candidate；Snapshot、reference manifest、repository/governance policy digest 不一致则返回 `TREE_INTEGRITY_FAILED`。

候选的安全绑定只使用以下语义身份：

    CandidateIdentityV1 {
      schema_version: 1
      snapshot_tree_digest
      candidate_tree_digest
      final_diff_digest
      digest
    }

`candidate_digest` 精确等于 `CandidateIdentityV1.digest`。`CandidateRevision.id`、`parent_id` 和易变元数据仅用于审计，不进入该摘要；同一 Snapshot 上相同 CandidateTree 与 `FinalDiffV1` 必须恢复相同摘要。`base_candidate_digest`、completion、验证和最终批准只引用该身份；三项输入任一变化都使旧引用陈旧。

### `UNIFIED_DIFF_V1`

- patch 文档本身必须为无 BOM 的 UTF-8、使用 LF，并仅允许标准 `--- a/path`、`+++ b/path` 和 `@@ -old +new @@` hunk；新文件使用 `--- /dev/null`、`+++ b/path`。
- 禁止时间戳、rename/mode/binary 扩展头、`\ No newline at end of file`、删除文件和路径仅大小写变化。
- 每个 hunk 的旧范围、上下文行和删除行必须与 `base_candidate_digest` 指向的候选精确匹配。
- 不允许 fuzzy apply、自动 offset、自动冲突解决或“尽力应用”；任一 hunk 不匹配则整个动作无副作用失败。
- 现有文件保持 BOM、统一换行风格和末尾换行；新文件固定为 UTF-8、无 BOM、LF、末尾换行。
- `base_candidate_digest` 不等于当前候选时，以 `STALE_CANDIDATE` 拒绝。

路径拒绝优先级固定为：patch/Schema 错误 → `PATH_INVALID`/`PATH_OUTSIDE_WORKSPACE` 和路径别名 → `UNSUPPORTED_FILESYSTEM_OBJECT`/`SENSITIVE_PATH` → `PROTECTED_ARTIFACT_CHANGED` → `PATCH_PATH_NOT_EDITABLE`。因此 `tests/test_a.py` 继续返回保护工件错误，结构合法但不属于 `src/**` 的 `README.md`、`docs/**`、`.github/**`、`.gitlab-ci.yml`、`Dockerfile*` 和 `scripts/**` 返回 `PATCH_PATH_NOT_EDITABLE`；用户批准和其他策略不能改变优先级或结果。

### `FinalDiffV1`

补丁是输入格式；批准、验证和持久化只绑定以下封闭结构：

    TextMetadataV1 {
      encoding: "UTF8" | "UTF8_BOM"
      newline: "LF" | "CRLF"
      final_newline: true
    }

    FinalDiffPreimageV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT {
          kind: "PRESENT"
          content_digest
          text_metadata: TextMetadataV1
        }

    FinalDiffEntryV1 {
      operation: "CREATE" | "REPLACE"
      path: CanonicalRelativePathV1
      preimage: FinalDiffPreimageV1
      postimage_digest
      postimage_text_metadata: TextMetadataV1
    }

    FinalDiffV1 {
      schema_version: 1
      snapshot_tree_digest
      entries: 0..3 unique FinalDiffEntryV1, sorted by canonical path
      added_and_replacement_text_bytes: 0..131072
      digest
    }

`CREATE` 必须绑定 `ABSENT`，`REPLACE` 必须绑定 `PRESENT`；其他组合在生成摘要前拒绝。每次动作后重新计算当前候选相对 `SnapshotTree` 的完整 `FinalDiffV1`，对全部 entries 重新应用同一 `EditablePathPolicyV1` 和 §1.4.4 的累计限制；它不是历史 patch 文本的拼接。`snapshot_tree_digest` 必须解析到包含同一 `EditablePathPolicyV1.digest` 的 `repository_policy_digest`，策略变化使旧 `FinalDiffV1` 失效。

`added_and_replacement_text_bytes` 是 Harness 派生字段，不接受模型、UI 或 patch 文本提供的值，其唯一计算式为：

    FinalDiffV1.added_and_replacement_text_bytes
    = Σ len(entry 对应的完整 postimage 原始字节)

求和覆盖全部 `CREATE` 和 `REPLACE` 条目，字节序列必须与相应 `postimage_digest` 的输入完全相同，包括 UTF-8 BOM、非 ASCII 字符的 UTF-8 多字节、CRLF 的两个字节和末尾换行；`entries=[]` 时结果为 `0`。即使只替换一个字符或新旧文件等长，`REPLACE` 仍计算完整 postimage。该值不得使用 unified diff 文本、`+` 行、仅变化片段或历史 patch 累计长度计算。重算值超过 131072 时返回 `PATCH_LIMIT_EXCEEDED`；记录值与当前 `CandidateTree` 重算结果不一致时返回 `TREE_INTEGRITY_FAILED`。

`digest` 按 §0.1 对除自身外的全部字段计算。WebUI 展示的 unified diff 必须由同一 `FinalDiffV1` 和可验证的 Snapshot/Candidate 字节确定性渲染；展示文本本身不作为批准、字节统计或持久化身份。

### 输出

不可变 `SnapshotTree`、`CandidateRevision`、当前规范 `FinalDiffV1`，或一个无候选副作用的稳定错误。

### 错误

`PATH_INVALID`、`PATH_OUTSIDE_WORKSPACE`、`UNSUPPORTED_FILESYSTEM_OBJECT`、`SENSITIVE_PATH`、`PROTECTED_ARTIFACT_CHANGED`、`PATCH_PATH_NOT_EDITABLE`、`UNSUPPORTED_PATCH_OPERATION`、`PATCH_CONTEXT_MISMATCH`、`STALE_CANDIDATE`、`PATCH_LIMIT_EXCEEDED`、`TREE_INTEGRITY_FAILED`。

### 清理

执行副本删除前验证 UUID 根身份且不跟随链接。删除失败时记录精确残留路径、使该名称在当前进程生命周期内不可复用并停止当前运行；v1 不因此建立通用恢复状态机。持久化恢复所需工件不受普通清理影响。

### 确定性测试

构造绝对路径、父目录、ADS、设备名、symlink/reparse、hard link、敏感路径、陈旧候选、hunk 不匹配、多动作累计超限和 ignored 新文件；断言全部在文件访问或候选发布前被稳定拒绝。`REPLACE src/a.py` 与 `CREATE src/new.py` 必须通过 editable gate；`README.md`、`docs/a.md`、`.github/workflows/x.yml`、`.gitlab-ci.yml`、`Dockerfile`、`scripts/x.py`、`src`、`src-old/a.py`、`src2/a.py` 和大小写/Unicode 路径别名必须拒绝，且 `tests/test_a.py` 仍优先返回 `PROTECTED_ARTIFACT_CHANGED`。合法与非法 entry 混合的单次 patch 整体无候选副作用，多次 patch 也不能产生越界的累计 `FinalDiffV1`。另构造 `CREATE`/`REPLACE` 混合候选，使用 UTF-8 BOM、中文、CRLF 和末尾换行复算完整 postimage 原始字节；断言单字符替换仍统计完整文件、`entries=[]` 为零、展示用 unified diff 不参与统计、越界 entry 返回 `PATCH_PATH_NOT_EDITABLE`、policy/Snapshot 绑定篡改返回 `TREE_INTEGRITY_FAILED`，以及重算结果超过 131072 时返回 `PATCH_LIMIT_EXCEEDED`。`CandidateIdentityV1` 测试还必须证明三项输入任一变化使旧引用陈旧，易变 revision 元数据不改变摘要，内容与 `FinalDiffV1` 恢复旧值时恢复原摘要。

## 4.4 FR-GOV：策略、动作批准与真实 LLM 披露

### 输入

规范化 `AgentAction`、当前运行/候选/Manifest/配置绑定、可选用户决定，以及真实请求的供应商、模型、来源和规范摘要。

### 4.4.1 动作策略

    PolicyEngine.evaluate(action, context) -> ALLOW | ASK | DENY

| 动作 | 默认决定 |
|---|---|
| 受限 list/read/literal search | ALLOW |
| 候选树内、全部条目命中冻结 `EditablePathPolicyV1` 的受支持补丁 | ALLOW |
| 选择预定义检查计划 | ALLOW |
| `ProposeCompletionAction` | ALLOW，但仅进入正式验证 |
| 最终权威写回 | ASK |
| editable root 越界、敏感路径、任意命令、验收篡改、控制面修改 | DENY |

硬 `DENY` 列表由代码中的单一版本化策略定义，治理 `policy_digest` 必须绑定 `ReferenceProfileManifestV1.editable_path_policy.digest`。配置、提示、仓库文本、`DisclosureGrant` 和用户批准都不能改变 `DENY`；任一 Candidate entry 越出 `src/**` 都是不可批准的硬拒绝。

### 4.4.2 `FinalWritebackApproval`

`FinalWritebackApproval` 只授权最终权威写回，不授权其他 `ASK`、本地工具、披露、Demo 决定或任何硬 `DENY`。批准身份由不可变 subject 定义：

    FinalWritebackSubjectV1 {
      schema_version: 1
      run_id
      action_type: "final_writeback"
      action_semantic_digest
      candidate_digest
      final_diff_digest
      validation_manifest_digest
      formal_evidence_digest
      workspace_preimage_digest
      run_config_digest
      policy_digest
      reference_profile_digest
      expires_at
      digest
    }

    FinalWritebackApproval {
      schema_version: 1
      approval_id
      subject_digest
      created_at
      status: PENDING | REJECTED | EXPIRED | CONSUMED
    }

`action_semantic_digest` 对封闭的 `{schema_version: 1, action_type: "final_writeback", candidate_digest, final_diff_digest}` 使用 `ActionSemanticDigestV1` 域计算。`FinalWritebackSubjectV1.digest` 排除自身 `digest`，并作为 `subject_digest`；`created_at` 和可变 `status` 不属于 subject。项目适配器身份已由包含 `adapter_version` 的 `validation_manifest_digest` 唯一传递，subject 不定义第二个 adapter identity。创建 subject 前必须重算 `FinalDiffV1`，验证其全部 entries 命中冻结 `EditablePathPolicyV1`，并验证 `policy_digest`、`reference_profile_digest`、`validation_manifest_digest` 和 `run_config_digest` 传递的是同一 editable policy identity；路径越界返回 `PATCH_PATH_NOT_EDITABLE`，identity 不一致返回 `TREE_INTEGRITY_FAILED`，两者都不得创建等待或批准。只有当前 `PENDING`、subject 未过期且全部 subject 字段仍匹配的批准可以在动作执行前通过一次原子更新变为 `CONSUMED`。消费动作不能改变 subject；消费失败不得执行写回。任何批准不得覆盖 `DENY`，也不得被转换为其他批准或授权类型。

### 4.4.3 `DisclosureGrant`

真实模式首次需要项目数据外发时，控制面展示并请求一个运行级不可变 subject：

    RequestSourceCategoryV1 =
      HARNESS_PROTOCOL | TASK | FILE_CONTENT | TOOL_RESULT | MEMORY | FEEDBACK

    DisclosurePathScopeV1 =
      ROOT { kind: "ROOT" }
      | FILE {
          kind: "FILE"
          path: CanonicalRelativePathV1
        }
      | DIRECTORY {
          kind: "DIRECTORY"
          path: CanonicalRelativePathV1
        }

    DisclosureGrantSubjectV1 {
      schema_version: 1
      run_id
      llm_profile_digest
      provider
      endpoint_id: "OPENAI_PUBLIC_API_V1"
      model
      request_serializer_version
      allowed_source_paths: 0..500 unique DisclosurePathScopeV1,
        sorted by ROOT < FILE < DIRECTORY, then path
      allowed_source_categories: 1..6 unique RequestSourceCategoryV1, sorted by enum order
      redaction_profile_id: "NO_CONTENT_REDACTION_V1"
      cumulative_byte_budget: 1..1310720
      expires_at
      digest
    }

    DisclosureGrant {
      schema_version: 1
      grant_id
      subject_digest
      created_at
      consumed_bytes
      status: ACTIVE | REVOKED | EXPIRED | EXHAUSTED
    }

`DisclosurePathScopeV1.ROOT` 匹配任意 `source_path=PRESENT` 的规范路径；`FILE(path)` 只匹配完全相等的路径；`DIRECTORY(path)` 匹配路径自身，或匹配以 `path + "/"` 开头的后代路径。目录匹配不得退化为普通字符串前缀，因此 `DIRECTORY("src")` 不匹配 `src-old/a.py`。所有 `path` 都是不带尾随 `/` 的 `CanonicalRelativePathV1`。`ROOT` 出现时必须是唯一 scope；其余 scope 拒绝重复值以及 Windows/Unicode 折叠后的路径别名。

`allowed_source_paths=[]` 精确表示不授权任何带路径来源，绝不表示全部仓库路径；只要来源类别合同允许，无路径来源仍可由 `allowed_source_categories` 独立授权。类别被允许不等于路径被允许，任一带路径来源必须额外命中至少一个 scope。

`DisclosureGrantSubjectV1.digest` 排除自身 `digest`。Grant 不绑定尚未形成的最终请求摘要，也不授权任何本地工具或持久化动作。供应商、endpoint、模型和请求序列化方式来自冻结 `OpenAILLMProfileV1`，用户不能在 Grant 中改写。用户可以撤销；LLM profile、endpoint、路径 scope、数据类别、脱敏 profile、累计预算上限或有效期被修改，或者当前请求需要扩大这些范围时，必须创建新的 subject、等待和 Grant。旧 Grant、`OpenAIPreparedModelRequestV1` 和 authorization record 不得在 endpoint 变化后复用。`consumed_bytes` 与 `status` 是可变记录字段，不进入 subject；正常预算消费不会使 subject 失效。

`NO_CONTENT_REDACTION_V1` 不扫描、替换或声称识别用户源码中的任意秘密。凭据、会话令牌和其他控制面秘密必须在 `ContextProjection` 形成前通过类型和来源隔离保证不可进入；违反该不变量时失败关闭，不能把事后字符串替换当作补救。授权界面必须明确告知用户：被选择的项目正文将在规范裁剪后原样发送，敏感路径拒绝不等于通用秘密扫描。

在创建或复用 `DisclosureGrant` 的授权界面，控制面必须显示 `endpoint_id = OPENAI_PUBLIC_API_V1` 与由可信内建 `OpenAIEndpointV1` 映射解析的目的主机 `api.openai.com`；显示值不得来自环境、请求、普通配置或 DNS 文本。路径 scope 必须分别显示为“整个仓库”“单个文件：<path>”或“目录及其后代：<path>”，不得向用户显示或接受尾随 `/` 字符串哨兵。

### 4.4.4 准备请求、调用结果与逐请求授权记录

    OptionalCanonicalPathV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: CanonicalRelativePathV1 }

    RequestContentSegmentV1 {
      source_category: RequestSourceCategoryV1
      source_path: OptionalCanonicalPathV1
      content: UTF-8 string
      content_digest
      byte_count: 0..65536
    }

    RequestMessageV1 {
      role: "SYSTEM" | "USER"
      segments: 1..1024 ordered RequestContentSegmentV1
    }

    RequestSourceV1 {
      message_index: 0..127
      segment_index: 0..1023
      source_category: RequestSourceCategoryV1
      source_path: OptionalCanonicalPathV1
      content_digest
      byte_count: 0..65536
    }

    MockAdapterPayloadV1 {
      schema_version: 1
      script_id
      script_digest
      messages: 1..128 ordered RequestMessageV1
    }

    PreparedModelRequestV1 =
      MockPreparedModelRequestV1 {
        schema_version: 1
        mode: MOCK
        llm_profile_digest
        script_id
        script_digest
        messages: 1..128 ordered RequestMessageV1
        canonical_byte_count: 1..65536
        digest
      }
      | OpenAIPreparedModelRequestV1 {
        schema_version: 1
        mode: OPENAI
        llm_profile_digest
        provider: "openai"
        endpoint_id: "OPENAI_PUBLIC_API_V1"
        model
        request_serializer_version
        messages: 1..128 ordered RequestMessageV1
        fixed_parameters: OpenAIFixedParametersV1
        redaction_profile_id: "NO_CONTENT_REDACTION_V1"
        canonical_byte_count: 1..65536
        digest
      }

    DisclosureAuthorizationRecordV1 {
      schema_version: 1
      authorization_record_id
      grant_id
      grant_subject_digest
      llm_profile_digest
      provider
      endpoint_id: "OPENAI_PUBLIC_API_V1"
      model
      request_serializer_version
      request_digest
      actual_sources: 1..1024 RequestSourceV1
      canonical_byte_count: 1..65536
      redaction_profile_id: "NO_CONTENT_REDACTION_V1"
      created_at
    }

    OptionalAuthorizationRecordRefV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT {
          kind: "PRESENT"
          authorization_record_id
        }

    OptionalResponseDigestV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT {
          kind: "PRESENT"
          value: 64 lowercase hexadecimal SHA-256
        }

    OptionalLLMCallErrorV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT {
          kind: "PRESENT"
          stable_error_code
        }

    LLMCallResultV1 {
      schema_version: 1
      mode: MOCK | OPENAI
      llm_profile_digest
      request_digest
      authorization_record_ref: OptionalAuthorizationRecordRefV1
      status: NOT_ATTEMPTED | SUCCEEDED | FAILED | DELIVERY_UNKNOWN
      response_digest: OptionalResponseDigestV1
      error: OptionalLLMCallErrorV1
    }

消息和其中 segments 都保持发送顺序，每个具体请求的 segment 总数必须为 1..1024。`content_digest` 是 segment `content` 的无 BOM UTF-8 原始字节 SHA-256，`byte_count` 是同一字节序列长度；不一致时在请求摘要前拒绝。上述 Schema 全部拒绝未知字段，声明字段全部必填。`MockPreparedModelRequestV1` 只能由冻结 `MockLLMProfileV1` 构造，`mode`、`llm_profile_digest`、`script_id` 和 `script_digest` 必须完全一致，并禁止 provider、endpoint、model、serializer、OpenAI fixed parameters 和 redaction profile 字段。`OpenAIPreparedModelRequestV1` 只能由冻结 `OpenAILLMProfileV1` 构造，禁止 `script_id` 和 `script_digest`。任一模式、profile digest 或模式专属字段不一致，均在请求摘要、turn/call 计数和适配器调用前以 `INTERNAL_ERROR` 失败关闭；OpenAI endpoint 或有效目标不一致仍使用 `LLM_ENDPOINT_MISMATCH`。

两个具体准备请求分别以自身类型名作为 §0.1 的 `object_type`，各自的 `digest` 排除自身且绑定其余全部字段；`PreparedModelRequestV1` 只是封闭联合别名，不产生第三种摘要。`DisclosureAuthorizationRecordV1.request_digest` 只能引用 `OpenAIPreparedModelRequestV1.digest`。`endpoint_id` 依 §0.1 自动进入 `OpenAILLMProfileV1`、`DisclosureGrantSubjectV1`、`OpenAIPreparedModelRequestV1` 和 `DisclosureAuthorizationRecordV1` 各自的规范摘要，四个对象的 endpoint 必须完全相同。

`MockPreparedModelRequestV1.canonical_byte_count` 是按 §0.1 规则编码 `MockAdapterPayloadV1` 所得规范 JSON 的无 BOM UTF-8 字节长度，不包括摘要域分隔前缀；`MockAdapterPayloadV1` 是 Mock adapter 实际解释的完整负载。OpenAI serializer 对每条消息按 segment 顺序直接拼接 `content`，不插入隐式分隔符，也不把来源元数据写入 HTTP 正文；`OpenAIPreparedModelRequestV1.canonical_byte_count` 是该 serializer 实际交给 transport 的最终 UTF-8 请求体字节数。两者都是各自模式的真实适配器负载大小，不要求跨模式相等，也不是 UI 展示长度。

`LLMCallResultV1.mode`、`llm_profile_digest` 和 `request_digest` 必须与被调用的具体准备请求一致。Mock 结果的 `request_digest` 必须引用 `MockPreparedModelRequestV1.digest`，`authorization_record_ref` 必须为 `ABSENT`，且不得使用 `DELIVERY_UNKNOWN`；OpenAI 结果的 `request_digest` 必须引用 `OpenAIPreparedModelRequestV1.digest`，`authorization_record_ref` 必须为 `PRESENT` 并指向 request digest 相同的已持久化 `DisclosureAuthorizationRecordV1`。`SUCCEEDED` 必须组合 `response_digest=PRESENT` 与 `error=ABSENT`；其他状态必须组合 `response_digest=ABSENT` 与 `error=PRESENT`。模式、请求、状态组合或授权记录引用不一致时，以 `INTERNAL_ERROR` 阻止结果发布；已消费的 turn/call 不回退，且不得重试适配器调用。

`RequestContentSegmentV1.source_path` 的存在性由来源类别和可信来源分类器共同冻结：

- `HARNESS_PROTOCOL`、`TASK` 和 `MEMORY` 必须为 `ABSENT`；
- `FILE_CONTENT` 必须为 `PRESENT`；
- `TOOL_RESULT` 和 `FEEDBACK` 的正文或事实可归属于一个具体仓库路径时必须为 `PRESENT`；只有纯运行级、检查级或控制面事实才允许为 `ABSENT`；
- 一段正文包含多个仓库路径时，必须拆分为多个按路径绑定的 segment，公共无路径元数据另建 `ABSENT` segment；List/Read/Search 产生的文件名、文件正文摘录或匹配结果必须绑定对应路径，不得把整个结果降级为无路径 `TOOL_RESULT`。

来源类别与 `source_path` 存在性合同适用于两个具体准备请求；违反该合同属于控制面构造错误，必须在具体请求摘要、turn/call 计数和适配器调用前以 `INTERNAL_ERROR` 失败关闭。只有 `OpenAIPreparedModelRequestV1` 需要 Disclosure Grant：每个 segment 必须命中 `allowed_source_categories`，`source_path=PRESENT` 时还必须按 §4.4.3 的精确算法命中至少一个 `allowed_source_paths`；类别或路径未命中活动 Grant 时以 `DISCLOSURE_SCOPE_EXCEEDED` 在 Grant 消费、durable authorization record 创建、turn/call 计数和网络调用前失败关闭，且这些副作用增量全部为零。Mock 不执行 Disclosure Grant 类别/scope、外发预算或 redaction 授权，但仍执行相同 ContextProjection 裁剪、segment 来源分类、路径存在性和 64 KiB 请求上限。

`DisclosureAuthorizationRecordV1.actual_sources` 不是第二份调用输入。控制面必须对请求中每个 segment 生成且只生成一个 `RequestSourceV1`，使用从零开始的 `message_index`/`segment_index`，复制其类别、路径、摘要和字节数，并按该二元组排序；缺失、重复、多余或内容不一致的投影必须在 Grant 消费和持久化前以 `INTERNAL_ERROR` 拒绝。由此，准备请求正文是唯一来源事实，authorization record 只保存无正文、可验证的派生索引。

每次 Mock 调用前：

1. 从冻结 `MockLLMProfileV1` 和最终 `ContextProjection` 构造 `MockAdapterPayloadV1`，复算 `canonical_byte_count`，形成不可再追加正文的 `MockPreparedModelRequestV1`；
2. 在请求摘要和计数前验证 request 的 `mode`、`llm_profile_digest`、`script_id`、`script_digest` 与冻结 profile 完全一致，且所选 adapter 精确为冻结 `adapter_version` 对应的 Mock adapter；
3. 只有全部验证通过且 turn、LLM call 与剩余总墙钟允许时，才按 §4.2.5 原子创建计数点并把该请求交给 Mock adapter；
4. 结果必须是 `mode=MOCK`、绑定同一 profile/request digest 且 `authorization_record_ref=ABSENT` 的 `LLMCallResultV1`。Mock 不读取凭据、不创建 Disclosure Grant/authorization record、不应用外发 redaction profile，也不访问网络。

每次真实调用前：

1. 创建或复用真实 Grant 时，调用门只验证冻结 `OpenAILLMProfileV1`、待创建或活动的 `DisclosureGrantSubjectV1`、可信内建 `OpenAIEndpointV1` 映射与 OpenAI 适配器的有效目标一致；此阶段 `OpenAIPreparedModelRequestV1` 与 authorization record 尚未形成，不得引用或验证它们。适配器必须显式仅由内建映射构造客户端，不得读取、接受或继承 `OPENAI_BASE_URL` 或 SDK 的等价自定义 base URL 设置。
2. 重新生成最终 `ContextProjection`，应用冻结的 `NO_CONTENT_REDACTION_V1` 并形成不可再扩张正文的 `OpenAIPreparedModelRequestV1`。在 Grant 消费事务前，只从该请求的 segments 派生完整但未持久化的 `DisclosureAuthorizationRecordV1` candidate 字段；candidate 不是 durable authorization record，不得落库、写入审计记录或作为已创建 authorization record 返回。
3. 在消费事务开始前，验证冻结 profile、活动 Grant subject、`OpenAIPreparedModelRequestV1`、未持久化 candidate 字段的 `endpoint_id` 与预期内建 `OpenAIEndpointV1` 一致，并验证适配器有效目标一致；再按固定来源路径存在性合同和 scope 匹配算法验证全部 segments 及其精确派生投影、redaction profile 应用结果和字节数均落在活动 Grant 内，且 turn、LLM call 和剩余总墙钟仍允许到达 §4.2.5 的计数点。
4. 紧接 Grant 消费事务之前，重新执行 Windows Credential Manager 安全后端探测并调用 `CredentialStorePortV1.get_for_call("OPENAI")`；启动/PREFLIGHT 的 credential readiness 不能替代本步骤。只有本次探测仍为受支持的 Windows Credential Manager 且本次读取返回非序列化 `SecretCredentialV1` 时才能继续。凭据已清除或缺失时以 `CREDENTIAL_MISSING` 停止当前 Run；后端不安全时以 `CREDENTIAL_BACKEND_UNSAFE` 停止当前 Run。两种失败均不自动重试，并且本次尝试的 Grant 消费、durable authorization record、turn/call 增量和网络调用全部为零。
5. 令 `charge_bytes = OpenAIPreparedModelRequestV1.canonical_byte_count`。只有前述全部验证和逐调用凭据复验通过，且 `consumed_bytes + charge_bytes <= cumulative_byte_budget` 时，才在同一控制面事务中原子执行 `consumed_bytes := consumed_bytes + charge_bytes`，等于预算上限时转为 `EXHAUSTED`，并只用已验证的 candidate 字段持久化 `DisclosureAuthorizationRecordV1`；否则零消费、零 durable record，并按 §4.2.7 处理预算不足。相同正文或请求再次获准发送仍重新按其完整 `charge_bytes` 扣减。
6. 只有该事务成功后，按 §4.2.5 原子创建 turn/call 计数点，真实调用门才可把同一 `OpenAIPreparedModelRequestV1`、已持久化 authorization record 引用和第 4 步刚取得的内存凭据交给真实适配器；适配器不得再次读取凭据，不得追加项目正文、工具结果或记忆。

`DisclosureAuthorizationRecordV1` 证明该精确 OpenAI 请求在调用前获得授权，不证明适配器被调用或供应商收到请求。控制面记录的 OpenAI 调用结果必须是 `mode=OPENAI`、绑定同一 profile/request digest 且 `authorization_record_ref=PRESENT` 的 `LLMCallResultV1`。

若请求摘要变化但仍在 Grant 范围和预算内，自动创建新的逐请求记录，不重新要求用户点击。来源本身符合类别/路径存在性合同、但其类别或路径超出活动 Grant 时，以 `DISCLOSURE_SCOPE_EXCEEDED` 拒绝复用旧 Grant，并严格按 §4.2.7 创建新的 `DISCLOSURE_GRANT` 等待；预算不足、Grant 过期或撤销同样遵循该生命周期。只有没有正的等待区间时才因总墙钟预算耗尽而停止。上述情况下真实适配器调用次数均为零。来源本身违反类别/路径存在性合同不能通过扩大 Grant 修复，必须直接失败关闭。

静态 endpoint/有效目标不一致或逐调用凭据复验失败必须以对应稳定错误失败关闭，且必须发生在 Grant 预算消费、durable authorization record 创建、turn/call 计数和网络请求之前；candidate 字段也不得落库。这些计数、durable record 和网络调用次数均为零。初次请求仅可发送到内建允许 origin；若初次请求已发送到该 origin 后收到跨 origin redirect，适配器必须在重发前以 `LLM_ENDPOINT_MISMATCH` 失败，不得跟随 redirect 或第二次发送正文。初次发送已按既有规则消费的 Grant/turn/call 不退款。

预算消费表示一次真实发送尝试已经获准。事务提交后，即使进程在调用前崩溃、适配器返回错误或供应商是否收到请求无法证明，已消费字节也不退款；除上述禁止跨 origin redirect 重发外，v1 不自动重发。OpenAI `LLMCallResultV1` 可使用 `NOT_ATTEMPTED | SUCCEEDED | FAILED | DELIVERY_UNKNOWN`，但不得把授权记录显示为供应商已收到；Mock 结果只允许前三种状态。

### 输出与错误

输出：`PolicyDecision`、`FinalWritebackSubjectV1`、`FinalWritebackApproval` 状态变化、`DisclosureGrantSubjectV1`、`DisclosureGrant`、`DisclosureAuthorizationRecordV1`、具体 `PreparedModelRequestV1`、`LLMCallResultV1` 或稳定拒绝。

错误：`ACTION_SCHEMA_INVALID`、`ACTION_DENIED`、`PATCH_PATH_NOT_EDITABLE`、`TREE_INTEGRITY_FAILED`、`APPROVAL_REJECTED`、`APPROVAL_EXPIRED`、`APPROVAL_STALE`、`APPROVAL_ALREADY_CONSUMED`、`DISCLOSURE_GRANT_REQUIRED`、`DISCLOSURE_GRANT_REJECTED`、`DISCLOSURE_SCOPE_EXCEEDED`、`DISCLOSURE_BUDGET_EXCEEDED`、`DISCLOSURE_GRANT_EXPIRED`、`DISCLOSURE_GRANT_REVOKED`、`CREDENTIAL_MISSING`、`CREDENTIAL_BACKEND_UNSAFE`、`LLM_ENDPOINT_MISMATCH`、`INTERNAL_ERROR`。

### 确定性测试

直接构造 `ALLOW`、`ASK`、`DENY`、批准竞态和 Grant 范围变化；断言硬拒绝不可覆盖，只有一个精确批准消费胜出，Approval/Grant 的状态与消费计数变化不改变 subject digest，任一 subject 字段变化使旧决定陈旧；越界 `FinalDiffV1` 以 `PATCH_PATH_NOT_EDITABLE`、editable policy identity 不一致以 `TREE_INTEGRITY_FAILED` 拒绝，且均不创建 `FINAL_WRITEBACK` 等待或 subject，已存在的旧批准也不能复用。Grant 测试按请求 `canonical_byte_count` 精确复算单次和重复发送消费，覆盖恰好耗尽、差一字节超限和并发竞争；未授权、超预算或 turn/call 预算不足时真实适配器调用次数为零，失败/未知交付不退款且不能重用记录。

路径 scope 测试必须证明：`FILE("src/a.py")` 只匹配该文件；`DIRECTORY("src")` 匹配 `src` 与 `src/a.py` 但不匹配 `src-old/a.py`；`ROOT` 匹配任意规范路径且必须是唯一 scope；空 scope 拒绝全部 `PRESENT` segment 但允许类别合同支持的合法 `ABSENT` segment。另覆盖正文摘要/字节数不一致、`FILE_CONTENT + ABSENT`、`HARNESS_PROTOCOL`/`TASK`/`MEMORY + PRESENT`、应带路径的 `TOOL_RESULT`/`FEEDBACK` 被降级为 `ABSENT`、多路径正文未拆分，以及 authorization candidate 来源投影缺失、重复、多余或索引错误；这些构造错误在具体请求摘要或 Grant 消费前以 `INTERNAL_ERROR` 拒绝。合法但超出 Grant 类别或路径 scope 的 segment 以 `DISCLOSURE_SCOPE_EXCEEDED` 在消费、record、计数和网络前拒绝；Grant UI 只显示“整个仓库 / 单个文件 / 目录及其后代”。

准备请求与结果 Schema 测试必须分别构造合法 Mock/OpenAI 变体，并拒绝缺少 `mode`、跨模式字段、profile/script/request digest 不一致以及非法 authorization record 引用。相同 Mock adapter payload 的字段插入顺序变化不得改变 `canonical_byte_count`，segment/message/script 变化必须改变 payload 字节或 request digest；两个具体 request 即使共享字段值相同也必须因不同 `object_type` 不可互换。Mock 成功、失败和计数后适配器调用前的可捕获控制面失败分别产生合法 `SUCCEEDED`、`FAILED`、`NOT_ATTEMPTED`，且 authorization record 始终为 `ABSENT`；真实进程崩溃只产生重启停止证据，不要求调用结果，Mock 的 `DELIVERY_UNKNOWN` 必须拒绝。

离线可注入 HTTP transport 测试必须断言：设置恶意 `OPENAI_BASE_URL` 后，有效请求仍只指向 `https://api.openai.com/v1`；缺少 `endpoint_id`、未知 endpoint、`base_url` 或自定义 URL 在摘要或调用前以 `CONFIG_INVALID` 拒绝；profile、Grant subject、`OpenAIPreparedModelRequestV1`、未持久化 candidate 字段、适配器目标或已持久化 durable record 任一 endpoint 不一致时以 `LLM_ENDPOINT_MISMATCH` 拒绝。candidate 字段篡改与 durable record 不一致必须分别测试：candidate 篡改路径的 durable record 数为零，candidate 不得落库、进入审计或被当作已创建 record；durable record 不一致路径不创建新的 record。两类不一致尝试均断言本次尝试的网络调用、Grant 消费、durable record 创建与 turn/call 增量为零；合法 OpenAI 结果必须使用 `authorization_record_ref=PRESENT` 并绑定相同 request digest；跨 origin redirect 不被跟随、不重发正文，初次调用消费不退款；Grant UI 显示 endpoint ID 和 `api.openai.com`。每次调用都记录 credential backend probe 与 `get_for_call("OPENAI")` 的先后顺序；在 PREFLIGHT 成功后清除凭据或把后端切换为不安全，断言分别以 `CREDENTIAL_MISSING`、`CREDENTIAL_BACKEND_UNSAFE` 停止，且发生在 Grant 消费、record、turn/call 和 transport 之前，全部本次增量为零且没有自动重试。

## 4.5 FR-VAL：Python 适配器、基线、检查、Manifest 和反馈

### 适配器边界

    ProjectAdapter {
      detect_static(
        snapshot: SnapshotTree,
        reference_manifest: ReferenceProfileManifestV1
      ) -> StaticProjectProfileResult
      build_baseline_plan(static_profile, target_test_ids) -> CheckPlan
      evaluate_runtime_compatibility(baseline_evidence) -> RuntimeCompatibilityResult
      build_validation_plan(manifest, candidate) -> CheckPlan
      parse_check_result(raw_result) -> CheckResult
      protected_artifacts(static_profile) -> ProtectedArtifactSet
    }

`detect_static` 只能读取当前 Run 已封存的唯一 `SnapshotTree`、其中绑定的 repository policy 元数据和内置 manifest，不能读取权威工作区、重新查询可变 Git 状态、创建第二份 Snapshot 或执行项目代码。所有结果都必须原样绑定输入 Snapshot 的 `root_digest` 和 `repository_policy_digest`，以及输入 manifest 的 `digest`。绑定不一致时失败关闭，不得构造基线计划。核心只理解 `CheckPlanId`、`CheckResult`、`TestIdentity`、`ProtectedArtifact`、`FailureFingerprintV1` 和 `ValidationManifestV1`。命令、argv、环境白名单和解析器属于 `PythonProjectAdapterV1`。

### `PytestEvidenceV1`

v1 假设目标项目可能包含缺陷、提示注入文本和非预期副作用，但不包含以破坏 Python 解释器、pytest、固定报告插件、容器内报告通道或检查进程为目的的主动恶意代码。只有在这一信任假设下，执行镜像内固定报告插件生成的完整 `PytestEvidenceV1` 才是权威检查输入；主动攻击测试运行器的项目在 v1 中不受支持。

    ErrorPhase =
      COLLECTION | SETUP | CALL | TEARDOWN | ENVIRONMENT

    TestStatus =
      PASS | FAIL | SKIP | XFAIL | XPASS | DESELECTED | ERROR | NOT_RUN

    OptionalTextV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: UTF-8 string }

    OptionalBooleanV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: bool }

    OptionalErrorPhaseV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: ErrorPhase }

    OptionalTestStatusV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: TestStatus }

    StructuredExceptionV1 {
      exception_type
      normalized_message
      normalized_assertion_diff: OptionalTextV1
      project_frames[]: ordered {
        relative_path: CanonicalRelativePathV1
        function_name
        line_number
      }
    }

    OptionalStructuredExceptionV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: StructuredExceptionV1 }

    PytestEventV1 {
      sequence: positive integer
      event_type: SESSION_START | COLLECTION_ITEM | TEST_PHASE | DESELECTED | SESSION_ERROR | SESSION_END
      node_id: OptionalTextV1
      phase: OptionalErrorPhaseV1
      outcome: OptionalTestStatusV1
      wasxfail: OptionalBooleanV1
      exception: OptionalStructuredExceptionV1
      display_summary: OptionalTextV1
    }

    PytestEvidenceV1 {
      schema_version: 1
      report_plugin_version
      run_kind: COLLECT_ONLY | FULL_PYTEST | TARGET_TESTS
      planned_node_ids[]: ordered exact pytest node IDs
      collected_node_ids[]: ordered exact pytest node IDs
      events[]: ordered PytestEventV1
      pytest_exit_code
      event_count
      normal_end_marker: true
      integrity_digest
    }

所有字段必填并拒绝未知字段。事件类型与字段组合由固定插件 Schema 封闭校验：不适用字段必须显式为 `ABSENT`；`TEST_PHASE` 必须有 node、phase 和 outcome；失败/错误必须有结构化异常；`SESSION_END` 必须是最后事件。`integrity_digest` 按 §0.1 对除自身外的全部字段计算。

缺少结束标记、事件序号断裂、重复或未知事件、报告截断、schema/插件版本不匹配、计划外 node ID、计划内 node ID 缺失，或事件摘要不一致时统一返回 `REPORTER_INVALID`。stdout/stderr 和 pytest 退出码不能补足或覆盖缺失的结构化事实。

Ruff 和 Mypy 必须分别使用由 profile 冻结的结构化或稳定格式及对应解析器。缺失、截断、未知诊断类别、工具/格式版本不匹配或解析器无法证明完整性时返回 `CHECK_ERROR`，不能仅按进程退出码判定 `PASS`。

### `FailureFingerprintV1` 与错误阶段

    ProjectFrameSignatureV1 {
      relative_path: CanonicalRelativePathV1
      function_name
      line_number
    }

    FailureFingerprintV1 {
      schema_version: 1
      node_id
      failure_phase: CALL
      exception_type
      normalized_message
      normalized_assertion_diff: OptionalTextV1
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

基线成功后创建以下封闭、不可变对象：

    OptionalDigestV1 =
      ABSENT { kind: "ABSENT" }
      | PRESENT { kind: "PRESENT", value: digest }

    BaselineTestRecordV1 {
      node_id
      status: TestStatus
      error_phase: OptionalErrorPhaseV1
      failure_fingerprint_digest: OptionalDigestV1
    }

    ValidationManifestV1 {
      schema_version: 1
      target_test_ids[]: sorted exact node IDs
      collected_node_ids[]: ordered exact node IDs
      baseline_test_records[]: sorted by node_id
      protected_artifact_set_digest
      reference_profile_digest
      check_plan_version
      adapter_version
      python_version
      pytest_version
      report_plugin_version
      ruff_version
      mypy_version
      collect_only_evidence_digests: exactly 2 digests in execution ordinal order
      full_pytest_evidence_digest
      target_rerun_evidence_digest
      ruff_result_digest
      mypy_result_digest
      docker_image_digest
      docker_execution_profile_version: 1
      resource_parameters_digest
      environment_whitelist_digest
      repository_policy_digest
      snapshot_tree_digest
      digest
    }

所有字段必填并拒绝未知字段。只有目标 `CALL/FAIL` 记录允许 `failure_fingerprint_digest=PRESENT`；其他记录必须为 `ABSENT`，且 `error_phase` 与 `TestStatus` 组合必须符合封闭状态表。`ValidationManifestV1.digest` 按 §0.1 对除自身外的全部字段计算。工具、镜像和 execution profile 字段必须与同一 `reference_profile_digest` 解析出的 `ReferenceProfileManifestV1` 完全一致；`repository_policy_digest` 和 `snapshot_tree_digest` 必须传递该 manifest 内同一 `EditablePathPolicyV1.digest`，不能形成第二套 profile 或 editable policy 身份。

### 检查执行

- `RunCheckAction` 只能选择 §4.2.2 的封闭计划；适配器生成固定 argv，禁止 Shell。
- 任一快速或正式检查创建容器前，必须重算当前 `FinalDiffV1` 并验证全部 entries 命中冻结 `EditablePathPolicyV1`，且 manifest/Snapshot/repository/governance policy digest 一致；越界路径以 `PATCH_PATH_NOT_EDITABLE` 硬拒绝，policy identity 不一致以 `TREE_INTEGRITY_FAILED` 失败，检查容器调用次数均为零。
- 每项检查使用全新容器；候选树只读挂载；缓存和临时文件进入 tmpfs。
- 机器可读报告是权威解析输入；stdout/stderr 只作为有界诊断工件，不能直接决定 PASS。
- 检查前后都重验候选树、保护工件和 Manifest 环境；项目树出现任何写入或漂移即 `EXECUTION_WORKSPACE_MUTATED`。

    CheckResult.status = PASS | FAIL | ERROR | TIMEOUT | NOT_RUN
    TestError = {status: ERROR, error_phase: ErrorPhase, stable_error, evidence_ref}

快速反馈可以只运行 `TARGET_TESTS`，但不能创建 `VerifiedCandidate` 或正式成功。

### 结构化反馈

- 反馈只从 `CheckResult`、`TestStatus`、`ErrorPhase`、`FailureFingerprintV1` 和稳定错误码生成。
- 下一 turn 最多接收 10 条、32 KiB；最近失败的分类、位置和有界摘要必须保留。
- 修改保护工件或越出 editable roots 的候选直接 `DENY`，不运行检查。

### 正式成功谓词

完整正式验证只有在以下条件全部满足时才创建 `VerifiedCandidate`：

1. 重算 `FinalDiffV1` 的每个 entry 都命中同一冻结 `EditablePathPolicyV1`，且 manifest/Snapshot/repository/governance policy digest 一致；
2. 最终 pytest 收集集合与 Manifest 完全一致；
3. 每个 node ID 都实际执行且为 `PASS`；
4. 不存在 skip、xfail、xpass、deselect、未执行、收集错误、setup/teardown 错误、环境错误或超时；
5. 所有目标测试由 Manifest 记录的稳定 `CALL/FAIL` 指纹变为最终 `PASS`；
6. Ruff 和 Mypy 均 `PASS`；
7. 保护工件、检查计划、工具版本、镜像摘要和环境摘要保持一致；
8. 候选项目树在所有检查后仍与正式验证输入完全一致。

pytest 退出码为 0 但上述任一条件不成立时，正式验证仍失败。

### 输出与错误

输出：`StaticProjectProfileResult`、`RuntimeCompatibilityResult`、`BaselineResult`、`PytestEvidenceV1`、`FailureFingerprintV1`、`ValidationManifestV1`、`CheckResult`、`FeedbackRecord`、`VerifiedCandidate`。

错误：`TARGET_NOT_FOUND`、`TARGET_NOT_REPRODUCED`、`TARGET_UNSTABLE`、`BASELINE_BLOCKED`、`REPORTER_INVALID`、`CHECK_ERROR`、`CHECK_TIMEOUT`、`PROTECTED_ARTIFACT_CHANGED`、`PATCH_PATH_NOT_EDITABLE`、`TREE_INTEGRITY_FAILED`、`EXECUTION_WORKSPACE_MUTATED`、`VALIDATION_ENVIRONMENT_CHANGED`、`FORMAL_VALIDATION_FAILED`。

### 确定性测试

使用固定机器可读报告夹具覆盖全部目标稳定 `CALL/FAIL`、目标意外 PASS/ERROR、执行根和 run ID 变化但指纹相同、用户正文变化导致指纹不稳定、节点漂移、skip/xfail/xpass/deselect、五种 `ErrorPhase`、事件缺失/重复/截断、结束标记或摘要损坏、未知/缺失 Schema 字段、Ruff/Mypy 解析错误、保护工件变化、项目树写入和正式全通过；另篡改 Candidate/FinalDiff 插入越界路径或替换 policy digest，断言所有快速/正式检查、`VerifiedCandidate` 创建和容器调用次数均为零。解析器单测不访问网络或真实 Docker。Docker 集成测试另见 §10.3。主动恶意代码攻击报告通道不作为通过用例，因为它明确超出 v1 信任边界。

## 4.6 FR-PERSIST：最终批准、受控写回与恢复

### 输入

`VerifiedCandidate`、规范 `FinalDiffV1`、`ValidationManifestV1`、正式验证证据、工作区前映像和最终 `FinalWritebackApproval`。

### 写回前置条件

1. 在消费批准前重算 `FinalDiffV1`，验证每个 entry 都命中冻结 `EditablePathPolicyV1`，且 `ReferenceProfileManifestV1`、`SnapshotTree.repository_policy_digest`、`ValidationManifestV1.repository_policy_digest` 和 `FinalWritebackSubjectV1.policy_digest` 绑定同一 policy digest；越界时返回 `PATCH_PATH_NOT_EDITABLE`，identity 不一致时返回 `TREE_INTEGRITY_FAILED`，均不消费批准或写入文件。
2. `FinalDiffV1` 不超过 §1.4.4 的 3 文件限制，且 `entries` 非空。
3. `VerifiedCandidate` 精确绑定当前候选、Manifest 和 `FinalDiffV1.digest`。
4. WebUI 同页展示精确 diff、Manifest 摘要和正式验证证据。
5. `FinalWritebackApproval` 已按 §4.4.2 原子消费。
6. 跨进程 workspace lease 仍由当前进程持有；权威工作区仍等于冻结前映像。

### 持久化事务

    PersistenceTransactionState =
      PREPARED | WRITING | COMMITTED | ROLLED_BACK | UNRESOLVED

    PreimageV1 =
      PRESENT {
        kind: "PRESENT"
        raw_bytes_digest
        text_metadata: TextMetadataV1
        object_identity_digest
      }
      | ABSENT { kind: "ABSENT" }

    PostimageV1 {
      raw_bytes_digest
      text_metadata: TextMetadataV1
      required_object_policy_digest
    }

    PathWriteState =
      NOT_STARTED | REPLACED | VERIFIED | ROLLED_BACK

    PersistencePathRecord {
      schema_version: 1
      path
      operation: CREATE | REPLACE
      preimage: PreimageV1
      postimage: PostimageV1
      sequence
      durable_state: PathWriteState
      backup_ref: OptionalArtifactRefV1
      last_evidence_digest: OptionalDigestV1
    }

现有文件使用 `PRESENT` 前映像；本事务创建的新文件使用 `ABSENT`。`ABSENT` 是类型化哨兵，不是空文件摘要。`CREATE` 必须绑定 `ABSENT` 且 `backup_ref=ABSENT`；`REPLACE` 必须绑定 `PRESENT` 和有效备份引用。违反组合时事务不能进入 `PREPARED`。

1. 创建 `PREPARED` 前只从冻结 manifest 解析 `EditablePathPolicyV1`，重验全部 `PersistencePathRecord.operation/path` 与已批准 `FinalDiffV1` 一致且可编辑；不得读取配置、用户输入或仓库文本形成第二套策略。
2. 创建状态为 `PREPARED` 的本地事务日志，为每个目标路径写入完整 `PersistencePathRecord`；所有记录初始为 `NOT_STARTED`。
3. 首次工作区写入前再次验证 workspace lease、目标前映像、路径对象身份、全部 path 的 editable 匹配和 policy digest；此时失败必须保持全部 `durable_state=NOT_STARTED`、零文件写入且不得恢复已消费批准或自动重试。
4. 每个文件写入前再次验证 workspace lease、目标前映像和路径对象身份。
5. 首次替换前转为 `WRITING`；使用同目录临时文件，写入后 flush 文件内容，在可用时同步目录元数据，然后执行原子替换。
6. 每次替换后，只有观察到当前对象精确匹配 postimage 且对象类型仍受支持，才能把该路径持久记录为 `REPLACED`；写后复验完成后记录为 `VERIFIED`。恢复前映像并复验后才可记录 `ROLLED_BACK`。
7. 正常写回只允许 `NOT_STARTED → REPLACED → VERIFIED`；恢复可在重新验证实际字节后从前三种状态进入 `ROLLED_BACK`。不得跳过证据直接前移状态，也不得从 `ROLLED_BACK` 返回写回状态。
8. `durable_state` 是最后一次成功持久化的进度事实，不是当前文件内容的权威替代。进程可能在文件替换与状态落盘之间崩溃；恢复必须重新读取当前字节、文本元数据和对象身份，并允许观测证据纠正滞后的状态。
9. 全部替换完成后，逐文件比较期望后映像，并重验未涉及 tracked 文件未变化。
10. 只有全部匹配时转为 `COMMITTED` 并由 `PersistenceCoordinator` 发布 `SUCCEEDED`；可证明全部恢复前映像时转为 `ROLLED_BACK`；其他未知或矛盾状态只能转为 `UNRESOLVED`。
11. 每次权威工作区写入前检查 `run_deadline`。首次写入前过期时保持全部路径 `NOT_STARTED`、零工作区写入，将无写入事务结束为 `ROLLED_BACK` 并令 Run `STOPPED`；任一路径可能已替换后过期时，禁止继续写入或自动回滚，事务转为 `UNRESOLVED`，Run 转为 `RECOVERY_REQUIRED`，后续只能由显式 recovery 判定 `COMMITTED` 或 `ROLLED_BACK`。deadline 后只允许持久化该控制面终态，不得再修改权威工作区。

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

错误：`APPROVAL_STALE`、`PATCH_PATH_NOT_EDITABLE`、`TREE_INTEGRITY_FAILED`、`WORKSPACE_CHANGED`、`WORKSPACE_LOCK_LOST`、`ARTIFACT_ACL_UNSAFE`、`PERSISTENCE_FAILED`、`PERSISTENCE_UNCERTAIN`、`WRITEBACK_MISMATCH`、`RECOVERY_UNRESOLVED`。

### 确定性测试

使用临时目录和逐故障点注入覆盖 preview 零写入、显式 apply、写入前失败、第一/第二文件替换后崩溃、文件替换后但 `REPLACED` 状态落盘前崩溃、首次写入前和首次替换后 deadline 到期、三文件混合 `CREATE/REPLACE`、新文件精确 postimage 的 `ABSENT` 回滚、新文件被外部改写或替换为特殊对象、ACL 不安全、完整提交、前映像变化、可回滚和未知字节；另篡改已验证 Candidate、`FinalDiffV1`、`PersistencePathRecord` 或 policy digest 注入非 `src/**` 路径，断言批准消费前路径失败不消费批准，批准消费后的首次写入前复验失败保持全部 `NOT_STARTED` 且工作区零写入。deadline 在首次写入前过期时同样零写入并停止，替换后过期时不再修改工作区且只能进入 `RECOVERY_REQUIRED`；状态滞后可由字节证据纠正，外部改写的新文件绝不删除，未知证据不能被普通启动绕过。

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
    GetCredentialForCall(provider) -> SecretCredentialV1 | CredentialError
    ClearCredential(provider) -> CredentialMutationResult

### 行为

1. 只支持 `OPENAI` provider；秘密通过 WebUI password 控件进入后端，不允许通过 URL、CLI 参数或日志字段传递。
2. 启动时和每次写入后必须验证实际后端为 Windows Credential Manager，并进行写入/读取状态能力探测。
3. 若 keyring 退化为明文文件、环境模拟或其他不受支持后端，返回 `CREDENTIAL_BACKEND_UNSAFE`，不得存储。
4. `GetCredentialStatus` 只返回配置状态、provider 和更新时间，不返回 secret、secret 长度或可用于猜测的派生值。
5. 更新以新秘密覆盖旧条目；清除失败必须明确返回失败，不能假装已删除。
6. `GetCredentialForCall("OPENAI")` 每次都重新验证实际后端并从 Windows Credential Manager 读取本次调用所需的非序列化内存包装；不得复用启动/PREFLIGHT 的“已配置”状态、缓存 secret 或跳过后端探测。缺失/已清除返回 `CREDENTIAL_MISSING`，不安全后端返回 `CREDENTIAL_BACKEND_UNSAFE`。
7. `GetCredentialForCall` 只允许由 §4.4.4 真实调用门在 Grant 消费、authorization record、turn/call 和网络之前调用；失败停止当前 Run 且不自动重试。Mock 模式不得调用该接口。

### 错误

`CREDENTIAL_INVALID`、`CREDENTIAL_BACKEND_UNSAFE`、`CREDENTIAL_STORE_FAILED`、`CREDENTIAL_CLEAR_FAILED`、`CREDENTIAL_MISSING`。

### 确定性测试

离线单测使用 `FakeCredentialStore` 验证录入、状态、覆盖、清除、逐调用安全后端复验、清除后的 `get_for_call` 失败和日志脱敏；Windows 发布验证必须包含一次真实 Credential Manager smoke test，测试秘密在结束后清除。调用门测试必须证明 PREFLIGHT 后清除凭据会使下一次真实调用以零 Grant/record/turn/call/网络副作用停止。

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
- 子上限最大值为：用户等待 300 秒、普通工具 60 秒、目标检查 120 秒、完整单项检查 300 秒、baseline 整体 600 秒、正式验证整体 600 秒；精确映射使用 §4.2.6 的封闭表。任何子上限都不能扩大另一适用上限或剩余总墙钟。
- `AgentTurn` 和 LLM call 只在 §4.2.5 的原子计数点消费；真实模式在 Grant、`OpenAIPreparedModelRequestV1` 和逐请求授权完成前，Mock 模式在 `MockPreparedModelRequestV1` 冻结且 profile/script/adapter 匹配前，以及任何 `WAITING_USER` 期间均不消费。计数点之后的崩溃、调用错误或无效输出仍占用预算。
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
- `.github/workflows/ci.yml` 必须在每次 push 和 pull request 运行 `unit-test`、`reference-image-build` 与 `demo-image-build`，且普通 workflow 不注入发布凭据、不推送镜像、不创建 Release；`.gitlab-ci.yml` 必须包含 §8.4 的四个精确 job 名称并遵守各自 push、merge request、main 和 release 触发合同。
- 发布证据必须区分离线单测、Windows 集成、Docker 集成、端到端 fixture 和公网 smoke test。

## 5.5 NFR-SEC：威胁模型

| 资产/风险 | 攻击者或来源 | 对策 | 残余风险 |
|---|---|---|---|
| OpenAI API Key | 仓库文本、日志、命令历史、Demo 用户 | Windows Credential Manager；后端探测；隐藏录入；禁止 CLI 参数和明文配置；日志白名单 | 同一 Windows 用户或管理员仍可能访问凭据 |
| Release/GHCR 凭据 | 恶意 PR/MR、fork pipeline、日志或构建工件 | 独立最小权限 token；GitLab masked/protected variables；只注入受保护 GitLab tag job；GitHub Actions、Task 2 loopback registry 与普通 GitLab 流水线均禁止注入 GHCR 凭据或推送外部 registry | GitLab/GitHub 管理员和受保护 runner 管理员仍在平台信任边界内 |
| 用户源码 | 恶意模型、提示注入、错误披露范围 | 本地读取与外发分离；冻结 LLM profile；运行级 Grant；逐请求授权记录；敏感 tracked 路径准入拒绝；明确 `NO_CONTENT_REDACTION_V1` 不扫描正文 | 被授权源码按范围原样外发；不能识别源码正文中的所有秘密 |
| 权威工作区 | 越界路径、reparse/hard link、陈旧批准、并发进程 | 句柄级身份检查、单链接画像、named mutex、前映像绑定、逐文件复核、写后核对 | 最后检查与替换间仍有短暂本机竞争窗口 |
| 验收契约 | 模型修改测试/配置、缺陷项目代码或非预期副作用 | 不可变 Manifest、保护工件、只读候选挂载、全新容器、正式重验 | 同一解释器/容器用户信任域中的主动恶意候选仍可能 monkeypatch pytest/报告插件、篡改 tmpfs 报告、伪造事件或干预退出流程 |
| 控制面数据 | 项目代码或容器读取宿主数据 | 无网络、非 root、只读根、候选只读挂载、tmpfs、无 Docker socket | Docker Desktop/宿主管理员不在威胁模型内 |
| WebUI | CSRF、恶意仓库 HTML、远程访问 | loopback、会话令牌、Host/Origin、CSRF、安全转义、CSP | 本机同用户恶意进程可能与服务竞争 |
| 公网 Demo | 越权到真实能力、跨会话数据 | 独立状态和能力注册表、固定场景、无凭据、无持久磁盘 | 部署平台管理员仍可访问运行环境 |
| 恢复工件 | 用户误删、未知外部修改 | 恢复阻断、前后映像、备份完整性、三值恢复结果 | 用户或管理员可在 Harness 外破坏恢复工件 |

`PytestEvidenceV1` 的事件序号、结束标记和摘要只能检测信任假设内的缺失、损坏和普通漂移，不能证明抵御同信任域主动攻击。对主动攻击测试运行器的项目进行验证属于未来工作；v1 不通过增加哈希、事件编号或只读项目挂载声称解决该问题。

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
    → Start + RUNNING(PREFLIGHT)
    → workspace identity + lease + recovery gate
    → Git / filesystem object / sensitive-path / clean-state Snapshot prechecks
    → create and seal the run's only SnapshotTree
    → ProjectAdapter.detect_static(SnapshotTree, ReferenceProfileManifestV1)
    → reference image / execution profile readiness
    → OpenAI credential / endpoint readiness when applicable
    → RUNNING(BASELINE)
    → collect-only ×2 + full pytest + target rerun + Ruff + Mypy
    → RuntimeCompatibilityResult(COMPATIBLE)
    → ValidationManifestV1
    → Agent turn / governance / parse candidate patch
    → frozen EditablePathPolicyV1 gate + atomic Candidate/FinalDiffV1 publish
    → structured feedback loop
    → editable-policy recheck + fresh read-only formal validation
    → VerifiedCandidate
    → editable-policy-bound subject + user approves exact FinalDiffV1
    → pre-write editable-policy recheck + persistence transaction + post-write verification
    → SUCCEEDED | STOPPED | RECOVERY_REQUIRED

## 6.3 LLM 调用数据流

Mock 正式运行：

    frozen MockLLMProfileV1 + ContextProjection
    → classify exact sources, CanonicalRelativePathV1 bindings and bytes
    → create MockAdapterPayloadV1
    → freeze MockPreparedModelRequestV1
    → verify mode + profile/script/adapter binding
    → atomically create AgentTurn and consume turn/call budgets
    → pass the same request to the Mock adapter
    → LLMCallResultV1(mode=MOCK, authorization_record_ref=ABSENT)

Mock 路线不读取凭据、不创建 Disclosure Grant 或 authorization record、不应用外发 redaction profile，且不访问网络；其来源路径存在性、ContextProjection 裁剪和请求大小限制仍与公共合同一致。

OpenAI 真实运行：

    frozen OpenAILLMProfileV1 + trusted OpenAIEndpointV1 + ContextProjection draft
    → classify exact sources, CanonicalRelativePathV1 bindings and bytes
    → create/reuse Grant: verify only profile + pending/active Grant subject + trusted mapping + adapter effective target
    → active DisclosureGrant?
        no: WAITING_USER(DISCLOSURE_GRANT, bounded by run deadline)
        yes: apply NO_CONTENT_REDACTION_V1 and create exact OpenAIPreparedModelRequestV1
    → assemble non-persisted authorization-record candidate fields
    → verify profile + Grant subject + request + candidate + source categories/path scopes + adapter effective target
    → atomically consume grant budget + persist DisclosureAuthorizationRecordV1 from verified candidate fields
    → atomically create AgentTurn and consume turn/call budgets
    → pass the same authorized request to one OpenAI adapter call at https://api.openai.com:443/v1
    → LLMCallResultV1(mode=OPENAI, authorization_record_ref=PRESENT)

授权事务提交后预算不退款。endpoint/目标不一致在提交前失败且零消费、零 durable record、零计数、零网络，candidate 不得落库；跨 origin redirect 在初次允许发送后失败且不得重发正文。适配器调用失败、调用前崩溃或交付状态未知都不得重用授权记录或自动重发。

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
| RunLimitsV1 | turns、LLM calls、run wall clock、wait/tool/target/full/baseline/formal timeouts | 全部必填且只能收紧内建硬上限；操作映射由 §4.2.6 封闭定义 |
| EditablePathPolicyV1 | policy_id、exactly `src` directory root、`CREATE/REPLACE`、digest | 发布包唯一内建可编辑策略；路径按目录段匹配，不能由请求、配置、模型或仓库文本覆盖 |
| ReferenceProfileManifestV1 | requirements/image/execution-profile/tool/check-plan versions、editable_path_policy、digest | `python-src-py312-v1` 的唯一权威可交付映射；执行身份和 Candidate 可编辑范围由该 digest 统一绑定 |
| LLMProfileManifestV1 | mode、provider/model/endpoint_id 或 Mock script、adapter/serializer、fixed parameters、digest | 请求只选 profile id，不能覆盖 manifest 字段；OpenAI 只可解析内建 `OPENAI_PUBLIC_API_V1` |
| RunConfigSnapshot | target IDs、limits、LLM/reference profile digests、digest | 创建后不可变；reference digest 已唯一绑定 execution image/profile 和 editable policy；不能包含秘密 |
| WorkspaceLease | workspace_identity、mutex_name、process_id、acquired_at | 正式工作区同一时刻最多一个持有者 |
| WaitContext | wait_id、run_id、wait_kind、source_phase、subject_digest、created_at、expires_at | 只允许 `DISCLOSURE_GRANT | FINAL_WRITEBACK`；决定绑定 wait 与 subject |
| SnapshotTree | root_digest、entries、repository_policy_digest | Snapshot 前置检查通过后在 PREFLIGHT 内创建并封存；`root_digest` 绑定 entries 和含 editable policy digest 的 repository policy；一个运行只能有一个权威基线快照 |
| StaticProjectProfileResult | `SUPPORTED(profile_id, reference_profile_digest, snapshot_root_digest, repository_policy_digest)` 或 `UNSUPPORTED_PROJECT(reference_profile_digest, snapshot_root_digest, repository_policy_digest, reasons)` | 只由 `detect_static` 基于当前 Run 的已封存 Snapshot 产生；两种结果都绑定 manifest/Snapshot/policy，失败结果阻止 readiness 与 BASELINE |
| RepositoryLocationV1 | `ROOT` 或 `PATH(CanonicalRelativePathV1)` | 只供需要表达仓库根的 list/search 动作使用；实际文件路径不使用字符串哨兵 |
| ListFilesEntryV1 | `DIRECTORY | TEXT_FILE | NON_TEXT_FILE` 封闭变体、size/text profile | List、Read、Search 共享 `SupportedTextFileV1` 分类；非文本普通文件可列出但不能作为正文读取或搜索 |
| RuntimeCompatibilityResult | status、violation_kind、evidence_refs | BASELINE 中产生；非 `COMPATIBLE` 不创建 Manifest |
| FailureFingerprintV1 | node、CALL phase、exception、message/diff、project frames、digest | 只由完整 pytest 证据创建；不安全规范化即不稳定 |
| ValidationManifestV1 | §4.5 的完整封闭字段、digest | 由基线创建后不可变；未知字段拒绝；reference、repository policy 与 Snapshot 身份绑定同一 editable policy |
| FinalDiffV1 | snapshot digest、排序 entries、完整 postimage 原始字节总量、digest | Harness 从 CandidateTree 重算并对每个 entry 重验冻结 editable policy；结构化净差异是批准、验证和持久化身份 |
| CandidateIdentityV1 | snapshot_tree_digest、candidate_tree_digest、final_diff_digest、digest | Candidate 的唯一语义身份；相同三重绑定产生相同 `candidate_digest` |
| CandidateRevision | id、parent_id、candidate_digest | 单父审计链；ID 和父链不进入候选语义摘要 |
| AgentTurn | id、run_id、candidate_id、context_digest、consumed_feedback_refs、outcome | 只在 §4.2.5 原子计数点创建；同一运行最多一个活动 turn |
| ActionRecord | action_id、action_type、instance_digest、semantic_digest、policy_decision、result_ref | 实例摘要用于审计关联，语义摘要用于重复/策略/进展；动作输入与结果不可被 Agent 改写 |
| FeedbackRecord | source_ref、kind、bounded_payload、consumed_by_turn | 最多被一个下一 turn 消费 |
| FinalWritebackSubjectV1 | §4.4.2 的不可变绑定、expires_at、digest | 项目 adapter 由 validation manifest 传递绑定，不定义第二个 adapter identity；Wait 与批准引用同一 digest |
| FinalWritebackApproval | approval_id、subject_digest、created_at、status | 只授权最终权威写回；`PENDING` 只能一次转入一个终局状态 |
| DisclosureGrantSubjectV1 | run/profile/provider/endpoint_id/model/serializer/category/path scope/redaction/budget/expiry/digest | `ROOT/FILE/DIRECTORY` 精确绑定带路径来源，空路径 scope 不授权任何带路径正文；endpoint 或授权范围变化必须新授权 |
| DisclosureGrant | grant_id、subject_digest、created_at、consumed_bytes、status | 可变预算记录；不授权本地工具或写回 |
| RequestContentSegmentV1 | category、path、content、content digest/bytes | 请求正文与来源的唯一事实；消息按 segment 顺序发送 |
| MockAdapterPayloadV1 | script_id、script_digest、messages | Mock adapter 解释带来源 segments 的规范负载 |
| PreparedModelRequestV1 | `MockPreparedModelRequestV1 | OpenAIPreparedModelRequestV1` | 独立摘要域和模式字段；OpenAI serializer 只投影 segment 正文 |
| DisclosureAuthorizationRecordV1 | §4.4.4 的字段与派生 `actual_sources` | 只记录 OpenAI 授权；来源索引必须精确投影 request segments |
| LLMCallResultV1 | mode、profile/request digest、authorization_record_ref、status、response/error | Mock 必须 `ABSENT` 且禁止 `DELIVERY_UNKNOWN`；OpenAI 必须 `PRESENT`；不把授权记录等同于供应商交付 |
| PytestEvidenceV1 | §4.5 的完整封闭字段、integrity_digest | 在非主动恶意项目假设下权威；缺失、截断或完整性失败不能产生 PASS |
| CheckResult | check_kind、status、structured_findings、raw_digest | 原始输出作为有界本地工件 |
| VerifiedCandidate | candidate_id、manifest_id、formal_result_digest | 只有完整正式验证通过时创建 |
| PersistenceTransaction | final_diff_digest、path_records、state、backup_refs | `PREPARED | WRITING | COMMITTED | ROLLED_BACK | UNRESOLVED`；未解决时阻止新运行 |
| PersistencePathRecord | path、operation、PRESENT/ABSENT preimage、postimage、sequence、durable_state、evidence | 状态可滞后；恢复始终重验实际字节和对象身份 |
| RecoveryResult | transaction_id、disposition、evidence_digest | `COMMITTED | ROLLED_BACK | UNRESOLVED` |
| MemoryEntry | workspace_identity、kind、summary、creator、source、timestamps | 不保存秘密、权限或完整源码 |
| AuditEvent | run_id、sequence、event_type、redacted_payload | 每个运行序号唯一且单调 |
| DemoSession | id、scenario_version、status、state_digest、expires_at | 与正式 Run 和能力完全隔离 |
| DemoDecision | demo_session_id、subject_digest、decision、created_at | 只推进固定 Demo 场景，不能转换为正式授权 |

`StaticProjectProfileResult`、基线 `CheckPlan`、`RuntimeCompatibilityResult`、`ValidationManifestV1`、`CandidateRevision` 和 `FinalDiffV1` 必须直接或经不可变父引用传递同一 `SnapshotTree.root_digest`；任何阶段不得以当前权威工作区重新解析或替换该身份。

控制存储使用 SQLite 事务保证本地状态比较与更新。大文件、执行副本、补丁正文、原始检查输出和恢复备份存为当前用户 ACL 受限的本地工件，只在数据库保存摘要与精确引用；凭据从不进入 SQLite。所有 digest 使用 §0.1。

## 7.1 跨实现会话的稳定契约

本节是多个实现会话和组件共同消费的稳定边界索引。规范性内容仍由表中引用章节的输入、输出、状态转换、不变量、错误优先级和验收条件定义；本索引不创建第二套数据模型。

| 契约族 | 跨组件稳定语义 | 规范来源 |
|---|---|---|
| 规范字节与身份 | strict UTF-8、规范 JSON、时间、相对路径、domain-separated digest 和身份连续性；同一语义输入必须产生同一摘要，非法或不完整输入不得产生替代身份 | §0–§0.1 |
| Profile、配置与准入 | 请求只能选择内建 profile；解析后的 manifest、editable policy、limits 和 RunConfigSnapshot 冻结；准入按规定顺序失败关闭且不得留下下游副作用 | §1.4、§4.1、§7 |
| Run、phase、wait 与计数 | Run/phase/终态、单活动 turn、turn/call 计数点、deadline、wait subject 和 restart 语义由封闭状态机统一解释 | §4.2.1、§4.2.3、§4.2.5–§4.2.8、§7 |
| Workspace、Snapshot 与 Candidate | Win32 最终对象身份、workspace lease、SnapshotTree、Content Object、CandidateTree、FinalDiffV1 与 CandidateIdentityV1 的不可变绑定跨读取、补丁、验证和写回保持一致 | §4.1、§4.3、§4.6、§7 |
| Action、Policy 与 Dispatch | 动作 schema、instance/semantic digest、phase 矩阵、`ALLOW/ASK/DENY` 优先级和“先绑定身份与策略、后 dispatch”顺序是所有 loop、Demo 与工具适配器的共同边界 | §4.2.2–§4.2.3、§4.4.1 |
| LLM 请求与披露授权 | segment 来源、PreparedModelRequest、profile/endpoint/model/serializer、Grant subject、授权预算、授权记录、调用结果和未知交付状态必须逐请求一致绑定；未经授权不得发送正文 | §4.4.3–§4.4.4、§6.3、§7 |
| 验证与反馈 | 静态支持结果、Baseline、PytestEvidenceV1、FailureFingerprintV1、ValidationManifestV1、CheckResult、VerifiedCandidate 和 FeedbackRecord 共享同一 Snapshot/profile/policy/candidate 身份链 | §4.5、§7 |
| 最终批准与写回 | FinalWritebackSubjectV1、一次性批准、VerifiedCandidate、FinalDiffV1、workspace identity 和 persistence transaction 必须在写回前重新一致；批准不能覆盖 `DENY` | §4.4.2、§4.6、§7 |
| 持久化与恢复 | 事务、path record、pre/postimage、对象身份、deadline、外部变化和 `COMMITTED/ROLLED_BACK/UNRESOLVED` 三值分类在 fault port、生产适配器、CLI 和 WebUI 中含义相同 | §4.6、§5.2、§7 |
| 记忆、审计与可见性 | workspace 隔离、创建/选择/清除权限、审计单调序号、redaction、retention 和用户可见投影必须由同一 durable facts 派生 | §4.7、§5.4、§5.6、§7 |
| 凭据 | 状态只暴露非秘密元数据；获取、更新、删除和每次真实调用前重新读取的失败语义一致；秘密不得进入配置、SQLite、日志、证据或命令行 | §4.8、§5.5–§5.6、§8.1 |
| UI、Demo 与交付证据 | 本地控制面只投影正式服务；公网 Demo 使用固定场景和共享纯核心但没有正式能力；CI、wheel、OCI、release 和 live evidence 必须绑定同一 source/digest 身份 | §4.9、§6.4、§8、§10 |

跨会话消费者只能依赖上述可观察语义和被引用的规范字段，不得依赖某个 PLAN task 曾列出的 Python 类名、helper 名、参数顺序或模块内组织。只在单一实现会话内使用的私有函数、局部类和测试 fixture 不是 SPEC 契约，由实现者在不改变可观察行为、身份、不变量、错误和验收条件的前提下决定。若两个实现会话需要新增共享字段、序列化形式、状态转换、错误码或身份输入，必须先修改 SPEC 并重新执行 M0；不能只在 PLAN 或实现中约定。

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
- 正式 reference execution image 发布到与仓库同一所有者下的 GitHub Container Registry，规范引用为 `ghcr.io/ledstevenovo/vespercode-reference@sha256:<digest>`；tag 不构成运行身份，运行和证据只接受 digest。
- README 必须给出 `docker pull ghcr.io/ledstevenovo/vespercode-reference@sha256:<digest>`、本地 RepoDigest 核验、镜像内 profile/version smoke，以及确认 wheel 内置 `ReferenceProfileManifestV1.docker_image_digest` 与所拉取 digest 完全一致的命令。无法获得或匹配镜像时本地正式运行失败关闭。
- 从本地构建产物安装的规范命令为：

      pipx install dist/vespercode-<version>-py3-none-any.whl

- 只有在包实际发布到配置的 Python 包索引后，README 才可以写：

      pipx install vespercode

- `vespercode serve` 启动本地 WebUI。
- `vespercode recover --workspace <path>` 只预览恢复；增加 `--apply` 后才执行。WebUI 提供等价的预览与显式确认入口。
- 目标机器前提：Windows 11 x64、Python 3.12、Git、Docker Desktop Linux 容器模式，以及按不可变 digest 拉取并核验的 `python-src-py312-v1` reference execution image。
- README 必须给出获取、安装、启动、凭据配置、reference/LLM profile manifest、执行镜像 digest 与精确模型、`NO_CONTENT_REDACTION_V1` 外发提示、恢复、目录结构和已知限制。

## 8.3 公网 Demo 分发

- 使用独立 Docker 镜像启动 Mock Demo。
- 镜像不包含本地模式能力注册、真实凭据入口、恢复逻辑或 Docker socket。
- 部署平台为 Render Web Service，使用 Demo Dockerfile 从 main 分支构建。
- 容器读取平台注入的 `PORT` 并绑定 `0.0.0.0`，健康检查为 `GET /healthz`。
- 服务不挂载持久磁盘；会话状态只存在进程内，进程重启后全部丢弃。
- 环境不得配置真实 LLM Key、Docker socket 或目标仓库访问凭据。
- README 记录公开 URL、服务配置、健康检查和免费实例可能冷启动的限制。

## 8.4 发布构建要求

GitHub 仓库是源码、版本 tag、Release 和 GHCR package 的发布权威，并由 `.github/workflows/ci.yml` 对每次 push 和 pull request 形成课程要求的 GitHub Actions 自动测试闭环；GitLab 项目运行 `.gitlab-ci.yml` 的完整 CI、Windows wheel 和受保护发布闭环。README 必须记录两端项目 URL、镜像方向和最后验证的同步方式。普通 CI 不反向改写 GitHub；受保护 release pipeline 只有在 GitLab `CI_COMMIT_SHA`、GitHub 同名 tag commit 和待发布 wheel 源提交三者一致时才可发布，任一查询失败或摘要不一致均停止。

- README 必须分别为容器化 reference execution image 和 Demo image 提供可复制的本地 `docker build` 与 `docker run` 命令；每组命令必须明确 Dockerfile、build context、镜像 tag/digest、必要端口与 health check，以及适用的运行安全参数，且不得包含凭据。reference image 的本地 build/run 仅用于复现与诊断，不能替代 Task 2、CI 或受保护 release 的 immutable digest evidence；只有其 digest 身份满足 §8.2、§8.4 与 AC-24/AC-30 的既有一致性合同时，才可声称与正式 image 等价。Demo 命令必须继续满足 §8.3 的无真实能力、无 secret、无 Docker socket 边界。

`.github/workflows/ci.yml` 必须包含以下三个精确 job 名称：

| Job | 触发条件 | 必须执行 |
|---|---|---|
| `unit-test` | 每次 push 和每个 pull request | 在锁定 Python 3.12 依赖环境中运行离线 `python -m pytest -q` 并保存测试报告 |
| `reference-image-build` | 每次 push 和每个 pull request | 从固定 recipe、基础镜像 digest 和 lock 构建 reference OCI image，记录 digest并运行 reference fixture smoke；允许复用 Task 2 的无凭据 loopback registry round-trip，但不得登录或推送任何外部 registry |
| `demo-image-build` | 每次 push 和每个 pull request | 真实构建 Demo OCI image，记录摘要并运行容器 `/healthz` 与能力隔离 smoke，但不得推送 |

GitHub Actions workflow 不接受、读取或注入 GitHub Release、GHCR、Render 或其他发布凭据，不运行发布命令，不创建 Release，不登录或推送任何外部 registry。Task 2/34 的无凭据 loopback registry 只用于同一 job 内的临时内容寻址验证，不构成发布，结束时必须删除。fork pull request 的权限必须为只读且三个 job 仍可在无 secret 条件下完成或明确失败关闭；不得用跳过 job 伪造闭环。

`.gitlab-ci.yml` 必须包含以下四个精确 job 名称；不能仅由人工发布脚本替代：

| Job | 触发条件 | 必须执行 |
|---|---|---|
| `unit-test` | 每次 push 和每个 merge request | 在锁定依赖环境中运行离线 `python -m pytest -q`，保存测试报告 |
| `wheel-build-smoke` | 每次 push 和每个 merge request | 在项目专属 Windows 11 x64 GitLab Runner 上构建 wheel、生成并校验 SHA-256，在全新 venv/pipx 环境中从该 wheel 安装并运行 `vespercode --help` |
| `reference-image-build` | 每次 push、每个 merge request 和受保护版本 tag | 从固定 recipe、基础镜像 digest 和 lock 构建 reference OCI image，记录 digest，核验内置工具/execution profile并运行 reference fixture smoke；普通 push/MR 可执行无凭据 loopback registry round-trip但不得推送外部 registry，受保护 tag 才推送 GHCR |
| `demo-image-build` | 每个 merge request 和 main 分支 push | 使用 Demo Dockerfile 真实构建 OCI 镜像，记录镜像摘要并运行容器级 `/healthz` smoke |

版本 tag/release 流水线复用通过验证的构建步骤，重新生成并校验版本化 wheel 和 SHA-256，重建或导入 Task 2 已冻结的完全相同 OCI manifest 与 blobs；本地重建摘要不等于 Task 2 `docker_image_digest` 时必须在任何发布前失败。随后把该 reference image 推送到 GHCR，按 registry 返回的不可变 digest 重拉并 smoke，校验 Task 2 loopback RepoDigest、wheel 内置 manifest 的 `docker_image_digest`、GHCR RepoDigest 和目标机实际拉取 RepoDigest 四者一致，然后创建或更新对应 GitHub Release wheel 工件。保存版本、Release URL、wheel 摘要、GHCR RepoDigest、Demo 镜像摘要、测试与 smoke 证据。

GitHub Release 与 GHCR 使用彼此独立的最小权限发布凭据：前者只允许目标仓库 release/content 写入，后者只允许目标 package 写入。两者只能通过 GitLab masked、protected CI variable 注入受保护 tag job；不得提供给 GitHub Actions、普通 GitLab push、merge request 或 fork pipeline，不得进入镜像层、日志、工件或 wheel。GitHub Actions 和普通 GitLab push/MR 流水线不得登录或推送外部 registry，也不得创建 Release；无凭据 loopback registry round-trip 仅是临时测试夹具。项目必须提供项目专属 Windows 11 x64 GitLab Runner；runner 不可用时 `wheel-build-smoke` 失败并阻断 merge/release，不得以 Linux smoke 或发布前人工日志替代。

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
| CI | `.github/workflows/ci.yml`，包含 `unit-test`、`reference-image-build`、`demo-image-build`；`.gitlab-ci.yml`，包含 `unit-test`、`wheel-build-smoke`、`reference-image-build`、`demo-image-build` | 同时满足 GitHub Actions 每次 push/PR 自动测试与 GitLab 强制 job，冻结无凭据普通构建、Windows wheel smoke、正式执行镜像、Demo 镜像及受保护发布证据 |
| 包分发 | wheel + pipx | 适合 Windows 本地 CLI/WebUI |
| Demo | OCI 容器 | 与本地能力隔离，便于公网部署 |
| 公网部署 | Render Web Service；Docker runtime、`/healthz`、无持久磁盘 | 冻结公开 WebUI 的端口、健康检查和无状态边界 |

依赖必须锁定。不得引入 LangChain `AgentExecutor`、AutoGen、CrewAI、LlamaIndex Agent、OpenAI Agents SDK runner 或宿主编码智能体 runner 来替代自研主循环。

# 10. 验收标准与追踪

## 10.1 项目级验收

- **AC-01：** 路径逃逸、绝对路径、ADS、设备名、symlink/reparse、hard link 和敏感 tracked 路径全部确定性拒绝。
- **AC-02：** 硬 `DENY` 无法被配置、模型输出、DisclosureGrant 或批准覆盖。
- **AC-03：** `FinalWritebackSubjectV1` 在过期或任一不可变字段变化时产生不同/陈旧 subject；项目 adapter 由 `validation_manifest_digest` 传递绑定，不存在第二个 adapter digest。`FinalWritebackApproval.status` 不进入 subject，且过期、绑定变化和重复消费时均不执行，也不能授权其他 `ASK`。
- **AC-04：** 修改测试、检查配置或 Manifest 保护工件的补丁不能进入检查或正式验证。
- **AC-05：** 注入固定检查失败后，Mock LLM 下一轮动作按脚本发生变化；每轮都能只由冻结 Mock profile 构造合法 `MockPreparedModelRequestV1`，Mock request/result 不含 OpenAI 字段且 `authorization_record_ref=ABSENT`，凭据、Grant、authorization record 和网络调用次数均为零。
- **AC-06：** LLM completion 建议不能绕过正式成功谓词和最终批准。
- **AC-07：** 写回内容精确等于已批准的结构化 `FinalDiffV1`；展示用 unified diff 不能改变批准身份，外部工作区变化阻止写入。
- **AC-08：** 凭据录入、状态、更新、清除、后端探测和日志均不暴露测试秘密。
- **AC-09：** 相同 Demo 输入产生相同关键状态和动作序列，且只进入 `DemoRunStatus`。
- **AC-10：** `python -m pytest -q` 离线通过；`.github/workflows/ci.yml` 的 `unit-test` 在每次 push 和 pull request 运行，`.gitlab-ci.yml` 的 `unit-test` 在每次 push 和 merge request 运行，两个平台最后一次适用运行均有可保存的通过记录。
- **AC-11：** `wheel-build-smoke` 在每次 push 和 merge request 的项目专属 Windows 11 x64 runner 上构建 wheel、校验 SHA-256 并完成全新 pipx 安装/CLI smoke；runner 缺失或不可用时 job 失败，README 步骤可从发布产物启动 WebUI。
- **AC-12：** `demo-image-build` 在每个 merge request 和 main push 真实构建镜像并通过容器 `/healthz` smoke；公网 Mock Demo URL 可访问且无法使用本地、恢复或真实能力。
- **AC-13：** 真实请求的全部正文都来自带类别和路径的 `RequestContentSegmentV1`；authorization record 的 `actual_sources` 必须逐段精确派生，缺失、多余或错配时零消费、零 record、零计数、零网络。每个 segment 必须命中 Grant 类别与 `ROOT/FILE/DIRECTORY` scope，空 scope 不授权带路径正文；每次获准发送按 `canonical_byte_count` 原子扣减，重复发送重复扣减且并发不能超预算。profile、endpoint、request、record 和结果必须一致，恶意 base URL 或跨 origin redirect 不能改变或重发正文；未授权披露时真实适配器调用次数为零。每次真实调用还必须在 Grant 消费前重新验证 Windows Credential Manager 后端并读取本次凭据；PREFLIGHT 后凭据被清除或后端变得不安全时分别以 `CREDENTIAL_MISSING`/`CREDENTIAL_BACKEND_UNSAFE` 停止，且本次消费、record、计数和网络增量均为零。
- **AC-14：** 两个工作区的记忆相互隔离；模型不能直接写记忆；用户清除后后续 turn 不再选择该条目。
- **AC-15：** 严格 `ValidateRunRequestV1` 拒绝重复/超量目标、未知 profile、缺失限制和放宽硬上限；有效请求先创建 `CREATED`，再严格按 workspace identity/lease → recovery gate → Snapshot 前置检查 → 创建并封存本次 Run 唯一 `SnapshotTree` → `detect_static` → reference image/execution profile readiness → OpenAI 模式 credential/endpoint readiness 的顺序完成 `PREFLIGHT`，最后才进入 `BASELINE`。任一阶段失败均不调用后续阶段；静态画像不运行项目代码、不重读权威工作区或创建第二份 Snapshot，动态兼容性只在 `BASELINE` 判定，Candidate 文件动作在完整 PREFLIGHT 与 BASELINE 通过前不可分发。
- **AC-16：** 正式 Run 的六种状态和各 phase 显示正确；失败、超时、skip、xfail、xpass、deselect 和未运行不显示为通过。
- **AC-17：** 六种动作及结果严格按封闭 Schema 解析；list/search 只能用 `RepositoryLocationV1.ROOT` 表示仓库根，空字符串、`.`、`./`、`/`、尾随 `/` 和 `[ROOT, PATH(...)]` 被拒绝。List/Search 使用各自不可互换、绑定 visible tree/query/下一扫描位置/自身摘要的 canonical cursor；逐页结果与未分页结果相同且无重复遗漏，`truncated` 与 `next_cursor` 组合严格，tree 变化返回 `CONTINUATION_STALE`，非法 cursor 返回 `CONTINUATION_INVALID`，二者均零部分结果。`ListFilesEntryV1` 只能使用 `DIRECTORY | TEXT_FILE | NON_TEXT_FILE` 及各自固定的 size/text profile 组合，List/Read/Search 对同一原始字节使用同一 `SupportedTextFileV1` 分类；非文本普通文件可列出，Read 以 `FILE_NOT_TEXT` 且零正文失败，Search 稳定计入 `skipped_non_text_count` 且 excerpt 不超过 1024 字节。模型提交 `action_id`、`RunCheckAction` 携带 executable/argv/命令文本、多动作或自由文本响应均被拒绝；Harness 生成的实例 ID 只影响 `instance_digest`，不影响 `semantic_digest`。
- **AC-18：** 多次 patch action 不能绕过累计 3 文件/128 KiB 限制；`FinalDiffV1` 由 Harness 重算完整 postimage 字节。`candidate_digest` 只由 Snapshot、CandidateTree 和该 FinalDiff 的封闭 `CandidateIdentityV1` 产生；任一输入变化使旧补丁、completion、验证和批准陈旧，revision ID/父链不改变语义摘要。
- **AC-19：** Docker 检查中候选树只读、缓存进入 tmpfs、无 Docker socket、无网络；`RuntimeCompatibilityCheckV1` 对收集漂移、项目树写入、报告不完整或检查环境错误返回结构化 `BASELINE_BLOCKED`。
- **AC-20：** 正式 pytest 只有在 node 集合一致、全部实际执行并 PASS、无所有禁止状态、Ruff/Mypy PASS、保护工件和环境一致时才创建 `VerifiedCandidate`。
- **AC-21：** 两个进程竞争同一工作区时最多一个获得 lease；未解决恢复事务阻止新的正式 Run。
- **AC-22：** 1—3 文件混合 `CREATE/REPLACE` 的故障注入只产生 `COMMITTED`、`ROLLED_BACK` 或 `UNRESOLVED`；deadline 在首次写入前到期时零写入停止，任一路径可能已替换后到期时不再修改工作区并进入 `RECOVERY_REQUIRED`。状态滞后由字节证据纠正，`UNRESOLVED` 保持阻断。
- **AC-23：** `PROJECT_CONVENTION`/`USER_DECISION` 与 `RUN_SUMMARY`/`KNOWN_FAILURE` 的创建权限严格按 §4.7 执行。
- **AC-24：** Task 1—3 使用同一 hash 锁定 gate toolchain，并保存 lock/config/runner/reporter/fingerprint-probe 摘要及三项 GO 证据；Task 2 还必须保存无凭据 loopback registry 的固定镜像身份、监听/清理证据、OCI manifest digest、registry 返回 RepoDigest、digest-pull RepoDigest 和 smoke，三种 digest 必须一致。Windows、Docker、端到端、GitHub Actions 三个强制 job 和 GitLab CI 四个强制 job 均形成可保存证据。不能用全局未锁定工具、Task 4 后补配置、本地 image ID、解析器单测、单一 CI 平台、Linux wheel smoke 或人工发布脚本替代可复现门禁、registry round-trip、真实 Windows 边界测试和镜像构建。
- **AC-25：** 每个目标在全量基线和独立复跑中都稳定产生相同 `CALL/FAIL` 与 `FailureFingerprintV1.digest`；任一目标 PASS/ERROR、缺失、未运行、无法安全规范化、不稳定、运行时不兼容或 `PytestEvidenceV1` 不完整时不创建 Manifest。
- **AC-26：** CTV-01—CTV-07 通过；相同 `CandidateIdentityV1`、profile、具体 Prepared request 和 target 集合跨进程产生相同 §0.1 摘要。Mock/OpenAI request 使用独立 `object_type`，segment 内容/来源进入具体请求绑定；未知字段、跨模式字段、非规范输入、路径别名或对象类型变化不能伪造身份。
- **AC-27：** `DISCLOSURE_GRANT` 与 `FINAL_WRITEBACK` 等待的决定精确绑定 wait/run/kind 和对应不可变 subject digest；可变 Grant/Approval 状态不改变 subject，拒绝、过期、取消、绑定变化、总墙钟耗尽和重启严格按 §4.2.7 转换，旧决定不能复用。
- **AC-28：** turn/call/墙钟和子超时都在下一副作用前执行；只有冻结具体请求、授权和 adapter 绑定完整、逐调用凭据复验通过且即将调用时才原子计数。凭据复验发生在 Grant 消费、authorization record 和计数之前；失败零副作用并停止。计数后调用前的可捕获控制面失败产生 `NOT_ATTEMPTED`，真实进程崩溃只由重启停止证据表示；两者均保留已消费计数且不重试。等待不消费，进展排除实例 ID、时间和审计序号。
- **AC-29：** 恢复默认 preview 且零写入，只有显式 `--apply` 修改工作区；新文件只有仍精确匹配本事务 postimage 时才能恢复为 `ABSENT`，外部改写或未知对象绝不删除并只能进入 `UNRESOLVED`。
- **AC-30：** Task 2 先以无凭据 loopback registry 冻结无自引用的单平台 OCI manifest digest并按 digest 重拉 smoke；`reference-image-build` 在普通 push/MR 无发布凭据地重建并 smoke 同一 digest。受保护 tag 仅在 GitLab commit、GitHub tag 和 wheel 源提交一致时将完全相同的 manifest/blobs 推送到 GHCR、按不可变 digest 重拉，且 Task 2 loopback RepoDigest、发布 wheel 内置 `ReferenceProfileManifestV1.docker_image_digest`、GHCR RepoDigest 和目标机实际拉取 digest 四者完全一致。
- **AC-31：** 唯一内建 `EditablePathPolicyV1` 只允许 `CREATE`/`REPLACE` `src/**` 文件，已有文件与新文件使用同一目录段匹配规则；`src-old/**`、仓库根、文档、CI、Docker 和 scripts 路径均以 `PATCH_PATH_NOT_EDITABLE` 拒绝，保护工件仍优先使用 `PROTECTED_ARTIFACT_CHANGED`。合法/非法混合 patch 整体零候选副作用，多次 patch、篡改 Candidate/FinalDiff、检查、批准和持久化均不能绕过复验；manifest/repository/governance policy digest 必须绑定同一策略，变化使旧 Candidate、验证和批准失效。list/read/search 不受 editable policy 限制，用户或配置提交自定义策略时不创建 Run。

## 10.2 用户故事—合同—验收追踪

| 用户故事 | 权威功能合同 | 适用 NFR | 主要验收 |
|---|---|---|---|
| US-01 | FR-ADM、FR-LOOP | NFR-PERF、NFR-USE、NFR-SEC | AC-15、AC-16、AC-21、AC-26、AC-28、AC-30、AC-31 |
| US-02 | FR-CRED、§8.1 | NFR-SEC、NFR-PRIV | AC-08 |
| US-03 | FR-LOOP、FR-WS、FR-VAL | NFR-PERF、NFR-REL | AC-04—AC-06、AC-17—AC-20、AC-25、AC-26、AC-28、AC-31 |
| US-04 | FR-GOV | NFR-SEC、NFR-PRIV | AC-13、AC-26、AC-27 |
| US-05 | FR-GOV | NFR-REL、NFR-SEC | AC-01—AC-03、AC-26、AC-27、AC-31 |
| US-06 | FR-PERSIST | NFR-REL、NFR-SEC | AC-07、AC-21、AC-22、AC-26、AC-29、AC-31 |
| US-07 | FR-MEM | NFR-OBS、NFR-PRIV | AC-14、AC-23 |
| US-08 | FR-LOOP、FR-MEM、FR-UI | NFR-USE、NFR-OBS | AC-06、AC-16、AC-27、AC-28 |
| US-09 | FR-UI | NFR-PERF、NFR-REL、NFR-SEC | AC-09、AC-12 |

## 10.3 验证环境矩阵

| 层次 | 环境 | 主要 AC | 必须证明 | 证据 |
|---|---|---|---|---|
| 可行性 gate bootstrap | Windows 11 x64、Python 3.12、Task 1 创建的隔离 venv；只从 hash 锁定 gate dependency lock 安装，并由唯一 runner 显式选择 gate pytest/Ruff/Mypy 配置；Task 2 另启动固定 digest、仅 loopback、无凭据的临时 registry | AC-01、AC-19、AC-21、AC-22、AC-24、AC-25、AC-30 | Task 1 冻结 lock、marker/config、runner 和工具版本；Task 2/3 只消费同一摘要；Task 2 显式加载报告器、比较稳定 `CALL/FAIL` 输入，并证明 OCI export → loopback RepoDigest → digest pull 三方一致且无最终 manifest 自引用；Task 4 提升已验证配置且不静默漂移 | Python/tool 版本、lock/config/runner/reporter/probe SHA-256、临时 registry image/config/监听/清理证据、三方 digest、隔离环境安装记录及 Task 1—3 GO 报告 |
| 离线核心单测 | 无网络；Fake FS/DB/Clock/LLM/Credential/HTTP transport | AC-02、AC-03、AC-05、AC-06、AC-10、AC-13—AC-18、AC-20—AC-23、AC-25—AC-29、AC-31 | 封闭 Schema/canonicalization 向量（包含未经 normalization 的 scalar/key 排序、surrogate 拒绝、普通 ASCII/U+007F 直接 UTF-8、非强制转义 scalar 禁止 `\uXXXX`/`\/` 替代、UTF-8 与控制字符转义、`/`/U+2028/U+2029 不转义，以及 `CanonicalTimestampV1` 格式、日期、小时 `00`—`23`、分钟/秒 `00`—`59`、UTC epoch 毫秒向下截断和摘要前拒绝）、Mock/OpenAI Prepared request 封闭联合、模式专属 byte count 与摘要域、`LLMCallResultV1` 的 ABSENT/PRESENT authorization record 和状态约束、PREFLIGHT 的 Snapshot 前置检查/唯一 Snapshot/静态画像/readiness 顺序及每个失败点的零下游调用、`EditablePathPolicyV1` 的 `src/**` 目录段匹配、错误优先级、摘要传播、混合 patch 原子拒绝、读取不受限和 Candidate/验证/批准/持久化复验、`RepositoryLocationV1` 根/路径联合与字符串哨兵拒绝、`ListFilesEntryV1` 三变体字段组合、共享 `SupportedTextFileV1` 分类、`FILE_NOT_TEXT` 零正文和稳定 `skipped_non_text_count`、`ROOT/FILE/DIRECTORY` scope 及带路径/无路径来源矩阵、完整 postimage 原始字节统计、profile/config（含缺少/未知 endpoint、`base_url`/自定义 URL 和 editable policy 覆盖拒绝）、四对象 endpoint 摘要绑定、恶意 `OPENAI_BASE_URL` 仍固定 `https://api.openai.com/v1`、endpoint 不一致零消费/零记录/零计数/零网络、跨 origin redirect 不跟随且初次消费不退款、Grant UI endpoint 显示、失败指纹、主循环、实例/语义动作摘要、策略、不可变 subject、批准、带 deadline 的两类等待、Grant、反馈、记忆、停止和逐路径持久化故障注入 | `unit-test` job 日志与测试报告 |
| 离线 continuation 与真实调用门 | Fake Tree/Credential/HTTP transport | AC-13、AC-17、AC-28 | List/Search cursor 的 query/tree/位置/自身摘要绑定、逐页与未分页等价、stale/invalid 零部分结果、1024 字节 excerpt；PREFLIGHT 后清除凭据或切换不安全后端时，逐调用复验在 Grant/record/turn/call/网络前以零副作用停止 | 两个平台 `unit-test` 报告中的命名测试与调用顺序 trace |
| Windows 集成 | 项目专属 Windows 11 x64 GitLab Runner | AC-01、AC-07、AC-08、AC-11、AC-13、AC-21、AC-22、AC-24、AC-26、AC-28—AC-31 | ADS、reparse、hard link、设备名、路径碰撞、`src` 与大小写/Unicode/`src-old` editable policy 边界、Git EOL/encoding/filter 拒绝、最终对象身份、ACL、Credential Manager 生命周期及逐调用读取、named mutex、新文件恢复和发布 wheel pipx smoke | Windows runner job 日志、安装日志和环境版本；测试秘密已清除 |
| Docker 集成 | Docker Desktop Linux 模式 | AC-04、AC-19、AC-20、AC-24、AC-25、AC-30 | `ReferenceProfileManifestV1` 唯一映射、固定单平台 OCI digest、无自引用 build context、Task 2 loopback registry round-trip、检查容器无网络/非 root/只读根/候选只读/tmpfs/资源限制、动态兼容性、`PytestEvidenceV1` 和真实 pytest/Ruff/Mypy | 固定执行镜像摘要、loopback registry 三方 digest/清理证据和可重复 Docker 集成脚本/runner 报告 |
| 端到端 reference fixture | Windows + Docker + Mock LLM | AC-05—AC-07、AC-13、AC-15—AC-18、AC-20—AC-23、AC-25—AC-29、AC-31 | 冻结 profiles/limits/editable policy → Snapshot 前置检查 → 创建并封存唯一 Snapshot → 静态画像 → readiness → 动态兼容 → 全目标稳定指纹 → 越界补丁硬拒绝 → `src/**` 错误补丁 → 反馈回灌 → 修正 → editable-policy 复验 → 正式验证 → 最终批准 → 写回前复验与精确写回，以及等待拒绝和未批准不写回 | 可重复 reference fixture 脚本、审计导出和最终摘要 |
| 恢复故障注入 | Windows 本地临时仓库 | AC-07、AC-21、AC-22、AC-24、AC-29、AC-31 | 1—3 文件混合事务、policy/路径记录篡改零写入、状态落盘前崩溃、外部改写新文件、preview 零写入、显式 apply 和安全 `ABSENT` 回滚 | 故障点矩阵和恢复日志 |
| GitHub Actions | GitHub-hosted Linux runner + Docker；每次 push/PR | AC-10、AC-12、AC-24、AC-30 | `unit-test`、`reference-image-build`、`demo-image-build` 三个精确 job；无发布凭据、无 registry push、无 Release，真实构建与 smoke | workflow run URL、三个 job 结果、测试报告、两类本地镜像摘要和 smoke 工件 |
| GitLab CI | Linux Docker runner + 项目专属 Windows 11 x64 runner；push/MR/main/protected tag | AC-10—AC-12、AC-24、AC-30 | `unit-test`、`wheel-build-smoke`、`reference-image-build`、`demo-image-build` 四个精确 job及受保护发布边界 | pipeline/job URL、测试/安装/镜像/发布工件和凭据边界检查 |
| 包与正式镜像发布 smoke | 项目专属 Windows 11 runner + Docker + GHCR | AC-10、AC-11、AC-24、AC-30 | `wheel-build-smoke`、`reference-image-build`、从 GitHub Release 下载 wheel并校验 SHA-256、从 GHCR 按 digest 拉取 reference image、核对 wheel manifest、通过 pipx 安装并启动 WebUI | job 日志、Release URL、GHCR RepoDigest、wheel/manifest 摘要、安装日志和环境版本 |
| 公网 smoke | `demo-image-build` + 部署后的 Demo | AC-09、AC-12、AC-24 | main/MR 镜像构建、容器及公网 `/healthz`、固定场景、`DemoDecision`、无真实能力 | job 日志、镜像摘要、部署记录与可访问 URL |

没有可用的项目专属 Windows CI runner 时，`wheel-build-smoke`、merge 和 release 必须失败关闭；人工日志或 Linux smoke 只能作为诊断，不能替代强制证据。

## 10.4 机制演示

离线脚本或测试必须在同一场景中展示：

1. Mock LLM 提交结构合法、路径规范但尝试创建 `docs/outside-scope.md` 的 `ApplyCandidatePatchAction`；路径校验通过后，`PolicyEngine` 返回 `DENY`，稳定错误码为 `PATCH_PATH_NOT_EDITABLE`，并断言工具分发和 Candidate 发布次数均为零；
2. Mock LLM 可读取 `README.md`，但尝试修改它时以 `PATCH_PATH_NOT_EDITABLE` 硬拒绝；
3. Mock LLM 提出合法但失败的 `src/**` 候选补丁，pytest 失败被结构化回灌，下一轮动作改变；
4. Mock LLM 尝试修改受保护测试或 Ruff/Mypy 配置，Manifest 保护机制拒绝；
5. 修正后的候选通过 editable-policy 复验和正式验证，但没有最终批准时不会写入权威工作区；
6. 真实适配器 stub 在没有有效 Grant 或逐请求授权记录时调用次数为零。

# 11. 风险、关闭清单与未来工作

## 11.1 v1 风险

| 风险 | 概率/影响 | 触发信号 | 缓解或降级 |
|---|---|---|---|
| 参考 profile 与真实项目差异过大 | 中/中 | 外部试用频繁命中不支持或动态阻断 | 交付权威 manifest/reference fixture；区分静态不支持与动态不兼容；不临时扩张 |
| Win32 最终对象身份实现错误 | 中/高 | ADS/reparse/hard link 集成用例失败 | 使用 pywin32/Win32 API；失败关闭，不降级为字符串路径判断 |
| Docker Desktop 行为或性能不稳定 | 中/高 | 只读挂载、tmpfs、资源限制或 runtime compatibility 失败 | 固定 manifest/镜像摘要；动态证据失败关闭 |
| 正式执行镜像未发布或摘要错配 | 中/高 | wheel manifest、GHCR RepoDigest 或目标机拉取结果不一致 | `reference-image-build`、受保护发布、按 digest 重拉和 AC-30 三方核验 |
| pytest/Ruff/Mypy 输出解析漂移 | 中/中 | 未知结果、指纹失败或解析错误 | 固定版本、机器可读报告和 `FailureFingerprintV1`；未知状态不通过 |
| 候选代码主动攻击 pytest/报告通道 | 低/高 | monkeypatch、报告文件伪造、运行时 hook 或异常退出干预 | 输入限定为课程/reference fixture 并明确不作对抗性保证；不以同信任域哈希冒充隔离；进程外认证报告通道列为未来工作 |
| 1—3 文件持久化中断 | 低/高 | 事务日志或逐路径状态未完成 | 类型化前映像、逐路径事实、实际字节复核、备份、三值恢复和工作区阻断 |
| 真实 LLM 泄露未识别秘密 | 中/高 | 被授权正文含未分类敏感值 | 敏感路径拒绝、冻结 profile、Grant、逐请求记录、体量限制；明确 `NO_CONTENT_REDACTION_V1` 残余风险 |
| SPEC 再次扩张 | 中/高 | 新增自然语言测试、多 Agent、通用恢复或大量兼容分支 | 所有新增先修改 §1.5/1.6 并经独立审查；PLAN 不得暗增 |
| 公网 Demo 被误认为正式验证 | 低/中 | UI 或审计缺少模拟标识 | 独立状态、持续标识、独立能力注册表 |

## 11.2 M0：SPEC Readiness Gate 与进入 PLAN 的关闭清单

M0 是 PLAN 生成、冻结和冷启动之前的人工准入门禁，不是实现 Task，也不产生实现 commit。执行者必须从用户本次指定、文件状态声明和当前 Git/文件系统事实中唯一解析正式 SPEC 路径；若存在内容不同且无法唯一判定的候选，M0 失败并返回 SPEC/文件身份澄清。

M0 必须在运行时对唯一正式 SPEC 执行并记录：

1. 以无 BOM UTF-8 原始文件计算 SHA-256；
2. 执行 `git hash-object --no-filters <正式 SPEC 路径>` 计算 Git blob；
3. 执行 `git rev-parse HEAD` 记录当前 Git commit；
4. 对照 `AI4SE_Final_Project_通用要求.md`、`AI4SE_Final_Project_A_Coding_Agent_Harness(1).md` 和适用 `AGENTS.md`，逐项确认课程与 Harness 强制要求没有被 SPEC 降级或遗漏；
5. 明确核对已知阻断项已经关闭：GitHub Actions 与 GitLab CI 双平台闭环；List/Search canonical cursor；每次真实调用前凭据复验；下述 `PlanSemanticDigestV1` 执行跟踪排除规则；前三项技术门禁可从仅有获准 SPEC/PLAN 的冷启动环境建立并复现同一锁定 gate toolchain；Task 2 以无凭据 loopback registry 证明 OCI digest round-trip 和无自引用流程，而 GHCR 凭据与真实发布仍只属于受保护 release gate；
6. 由人类批准上述精确 SPEC 路径、SHA-256、Git blob 和基线 commit。

M0 的摘要和批准记录必须写入外部批准记录及随后生成的 PLAN 元数据，不得把摘要写回被摘要的 `SPEC.md`。任何命令失败、内容冲突、阻断项未关闭或人类未批准都使 M0 失败：流程必须返回修改/澄清 SPEC，不得继续生成或冻结 PLAN，不得开始冷启动或 Task 1。

本版供 M0 核对的关闭合同包括：

- 准入、profiles、Snapshot 与生命周期：§4.1—§4.2，AC-15、AC-16、AC-21、AC-28、AC-30；
- 动作、路径、List/Search cursor、Candidate identity 与 editable policy：§4.2—§4.3，AC-01、AC-17、AC-18、AC-26、AC-31；
- 批准、披露、Prepared requests、逐调用凭据复验与调用结果：§4.4、§4.8，AC-02、AC-03、AC-08、AC-13、AC-27、AC-28；
- 项目验证、证据与受控持久化恢复：§4.5—§4.6，AC-04、AC-07、AC-19—AC-22、AC-25、AC-29；
- 凭据、记忆和 UI 权限边界：§4.7—§4.9，AC-08、AC-09、AC-14、AC-23；
- GitHub Actions、GitLab CI、分发与验证矩阵：§8—§10，AC-10—AC-12、AC-24、AC-30。
- 可行性门禁启动环境：Task 1 拥有精确版本、完整传递依赖和 hash 锁定的 gate dependency lock、独立 pytest marker/config、Ruff/Mypy config 与唯一 gate runner；Task 2/3 只能消费 Task 1 冻结的同一工具链，不得依赖全局 pytest/Ruff/Mypy 或 Task 4 文件。

因此，PLAN 不得再让实现者自行选择上述语义。精确依赖 patch 版本、OpenAI model、镜像摘要和部署 URL 由发布 manifest、lock file、README 与流水线证据记录，并通过 digest 绑定到运行。

获准的 PLAN 使用 `PlanSemanticDigestV1` 区分语义合同与执行跟踪。该摘要不得写入 `PLAN.md` 自身，必须存入外部批准记录，并按以下唯一投影计算：

1. 输入必须是无 BOM UTF-8；所有 CRLF 先规范为 LF，裸 CR 拒绝。
2. 正式 Task 区域精确定义为从完整行 `## Formal Tasks` 起，到下一完整行 `## Task Dependency DAG` 之前。只在该区域执行三种替换：
   - 每个完整行前缀为 `**Status:** ` 的行统一替换为 `**Status:** TRACKING_STATUS_EXCLUDED_V1`；
   - 所有 checkbox token `[ ]` 与 `[x]` 统一为 `[ ]`，步骤正文仍参与摘要；
   - 每个完整单行前缀为 `**Completion evidence:** ` 的行统一替换为 `**Completion evidence:** TRACKING_EVIDENCE_EXCLUDED_V1`。
3. 除上述精确替换外，PLAN 的其他全部字节都参与摘要；不得排除 task 标题、Goal、依赖、文件、接口、实现点、测试、命令、review gate、矩阵、门禁或人工动作。
4. 对投影后的无 BOM UTF-8 字节计算 `SHA-256(b"VesperCode\0PLAN_SEMANTIC_CONTRACT_V1\0" + projected_plan_bytes)`。
5. 仅 task 状态、checkbox 勾选和单行 completion evidence 的变化不要求重新进行 PLAN 语义批准或冷启动；任何其他字节变化都必须生成新的 `PlanSemanticDigestV1`、重新人工批准并重新通过冷启动门禁。
6. 完整 PLAN 文件 SHA-256 始终作为每次证据更新的审计身份记录，但不取代 `PlanSemanticDigestV1`，也不因合法执行跟踪更新使既有语义批准失效。

通过 M0 和 PLAN 人工批准后，PLAN 的最前部仍必须安排三项技术验证任务，并采用失败关闭而不是放宽设计：

1. Win32 最终对象身份、hard link/reparse/ADS 与 named mutex 集成验证；
2. `ReferenceProfileManifestV1`/reference fixture 映射、固定单平台 OCI manifest 构建、无凭据 loopback registry push → RepoDigest → digest pull → smoke、无最终 manifest 自引用、Docker 只读候选树、tmpfs、缓存、资源限制、完整报告和失败指纹集成验证；真实 GHCR 交付保留给 §8.4 受保护 release gate；
3. 1—3 文件持久化的逐故障点恢复验证。

三项门禁必须共享同一可复现的最小启动合同。Task 1 在其首次 RED 前建立并审查 gate lock、独立 pytest marker/config、Ruff/Mypy config 和唯一 runner；lock 必须冻结所有直接/传递依赖的精确版本与分发 hash，GO 报告必须记录 Python、pytest、Ruff、Mypy、lock/config/runner 摘要。Task 2 和 Task 3 必须通过该 runner 显式选择 gate config 执行，禁止读取全局工具配置或等待 Task 4 创建 `pyproject.toml`、`requirements/dev.lock`、marker 和静态检查配置。

Task 2 还必须拥有可通过显式 pytest `-p` 或等价封闭入口加载的 gate 专用机器报告器，以及只负责构造、规范化和比较稳定 `CALL/FAIL` 输入的 gate 指纹探针。Docker gate 报告必须把 reporter/probe 的版本与摘要、gate lock/config 摘要、固定 builder/output 参数、实际镜像身份和临时 registry 身份绑定为同一 GO 证据；缺失、截断、摘要不一致或隐式插件加载均为 NO-GO。该 reporter/probe 只证明 Task 2 可行性，不得提前声明或替代 Task 19 的正式 `PytestEvidenceV1`、`FailureFingerprintV1` 和生产验证模块。

Task 2 的临时 registry 必须使用 digest-pinned registry image，只监听 `127.0.0.1` 的动态空闲端口，不接受凭据、不暴露到 LAN/公网、不复用 Docker Desktop 已登录状态，并在成功、失败、取消和异常路径删除容器与数据。推送前生成的本地 OCI manifest digest、registry 返回 RepoDigest 和按 digest 重拉后的 RepoDigest 必须完全一致；检查容器在重拉后仍以 `--network none` 执行。最终 `ReferenceProfileManifestV1` 只能在三方一致后生成，且不得作为其绑定镜像的构建输入。任何 digest 转换、自引用、临时 registry 残留或外部 registry 尝试均为 NO-GO；Task 34 只能复现该已证明流程，Task 36 才能使用受保护凭据执行真实 GHCR 交付。

Task 4 必须把 Task 1—3 已验证的 Python/tool 版本、marker 和静态检查规则提升为正式 `pyproject.toml`、`requirements/dev.lock` 和统一开发命令，而不是首次建立测试环境。正式配置与冻结 gate 配置如有任何有意差异，必须明确记录、重新执行受影响的 Task 1—3 并取得新 GO；未解释或未复验的漂移失败关闭。gate lock、config、runner、报告器、指纹探针和三项 GO 摘要必须保留到最终交付，以便从门禁证据独立复现。

若第三项无法证明 3 文件事务安全，必须停止后续实现和发布；不得在 PLAN 或代码中把正式范围隐式改为单文件。改变 3 文件/1 新文件范围前，必须正式修订本 SPEC、相关用户故事、AC、验证矩阵和 PLAN，并重新审查；不得删除恢复语义或把未知状态视为成功。

## 11.3 未来工作

- `NaturalLanguageDefect`、测试提案审批和 `ValidationManifestV2`。
- 更宽松但仍确定性的 skip/xfail 基线比较。
- 多语言 `ProjectAdapter` 和更多预构建 reference profile。
- 供应商请求重试、跨进程调用对账和普通 turn 恢复。
- 删除、重命名、二进制补丁和更广 Git 策略。
- 多用户部署、分布式配额和生产级工件清理。
- 独立低权限测试用户、进程外认证报告通道或更强沙箱，用于验证主动攻击 Python/pytest/报告插件的项目。
- 超过 3 文件的持久化事务。

这些项目不得出现在 v1 的 PLAN、代码路径或验收门禁中。
