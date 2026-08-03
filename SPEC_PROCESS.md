# SPEC 与 PLAN 协作过程记录

## 1. 记录范围与协作方式

本文记录 VesperCode 使用 Superpowers `brainstorming` 生成 `SPEC.md` 的过程。第 1 章“问题陈述”的初稿提交为 `9e1dc4a`（`完成spec文档第一节初稿`）；经过五轮外部 AI 审查、Codex 技术复核、用户逐轮决策和无上下文读者检查后，第 1 章确认稿提交为 `8ccc9d2`（`确认spec文档第一章`），并已推送至 `origin/main`。第 2 章“用户故事”随后完成逐项 brainstorming、外部审阅、用户确认并写入工作区。第 2 章最终审阅又促使用户授权重新打开第 1 章，澄清 Manifest 受控转换并移除首版 Native 执行路径；这些最新修改尚未提交。`PLAN.md` 尚未进入编写阶段。后续形成其他 SPEC 章节和计划时继续补充本文，不把尚未发生的过程写成既成事实。

协作采用两条互相校验的链路。第一条是“一个具体问题或一组紧密相关的审查意见 → Codex 解释方案和类似 Agent 模式 → 用户确认 → 更新待确认稿”。第二条由用户主动发起：用户将阶段性 `SPEC.md` 上传到网页版 GPT，取得独立审查意见，再把审查文本原样带回当前 Codex 对话；Codex 不把外部建议直接视为事实，而是逐条检查课程要求、内部一致性、可实现性和范围影响，给出采纳、受控采纳、后移或拒绝意见，最后由用户决定。章节未整体确认前不提交确认稿；确认后才提交并推送。

这里的“受控采纳”不是弱化建议，而是区分两类内容：影响第 1 章安全语义或实现一致性的高层合同立即写入；精确 schema、算法、参数矩阵和保留周期等细节登记为后续功能规约、非功能需求、系统架构、数据模型或“领域与机制设计”的强制输入，避免第 1 章继续膨胀或形成重复事实源。

## 2. Brainstorming 关键节点

| 关键节点 | 有价值的问题或判断 | 对原设想的修正 |
| --- | --- | --- |
| 用户与语言范围 | Windows 本地仓库是否等于只能修复 Python？Harness 内核和首版适配器是否应分开？ | 改为语言无关内核，首版仅提供有界、可测试的 Python 适配器。 |
| 工具边界与操作系统隔离 | 文件工具的路径围栏能否代表子进程也无法访问工作区外部？ | 明确工具级保证与 OS 级隔离不同；默认 Docker，Native 为显式未沙箱化模式。 |
| 客观反馈 | 怎样排除收集错误、依赖错误、超时和偶发失败，避免把假失败当成缺陷复现？ | 引入结构化检查状态、双执行副本复现、基线阻断和确定停止状态。 |
| 验收器防篡改 | Agent 能否通过删除测试、增加 `skip` 或修改 Ruff/Mypy 配置获得成功？ | 引入不可变、版本化的 `ValidationManifest` 和受保护验收契约。 |
| 补丁事务 | 候选补丁在哪里迭代，何时才可以写入用户工作区？ | 区分 `AuthoritativeWorkspace` 与 `ExecutionWorkspace`，采用验证后晋升的事务顺序。 |
| 权限默认值 | 哪些动作默认 `ALLOW / ASK / DENY`？批准能否重复使用？ | 建立默认动作矩阵；首版仅保留绑定完整上下文的一次性批准。 |
| 产品形态 | 公网 WebUI 如何访问 Windows 本地仓库，是否会迫使项目变成远程 Agent 平台？ | 采用本地真实 WebUI 与公网 Mock 演示双模式，不提供远程控制本地仓库。 |
| 首版范围收缩 | Native 诊断不能推进正式结果，是否值得承担独立的威胁模型、审批、终态和测试矩阵？ | 推翻早期“显式未沙箱化诊断模式”，首版改为 Docker-only；Native 明确列为非目标。 |

## 3. 关键迭代节选与处理决策

### 迭代一：从宽泛提问改为解释后选择

> 用户：“你问的问题太宽泛了，请先提供细致的问题而不是直接给我草案让我提问题；同时我对这一块完全不懂，如果你要让我选择方案需要解释方案。”

**处理决策：** 停止让用户从完整草案中自行找问题，改为一次只讨论一个具体决策。每组选项说明实现代价、课程符合度、Claude Code/OpenCode 属于哪种模式，以及模仿该模式在本项目中是否现实。这一反馈直接改变了后续全部 brainstorming 的交互方式。

### 迭代二：修正“Windows 本地 Python 仓库”的歧义

> 用户：“目标用户是维护 Windows 本地 Python 仓库的独立开发者。这句话什么意思，是指只能调试Python代码吗”

**处理决策：** 将宿主平台、Harness 内核和目标项目适配器拆开描述。目标用户维护 Windows 本地代码仓库；核心协议保持语言无关；首版只实现明确兼容性画像内的 pytest/Ruff/Mypy 适配器。“完整 Python 项目适配器”随后也被删除，以免隐含支持 Poetry、Conda、tox/nox、monorepo 和多解释器矩阵。

### 迭代三：修正无法兑现的安全承诺

> 用户转述网页版 GPT 审查意见：“1.3 与 1.6 的安全承诺存在冲突……仅设置工作目录并不等于文件系统隔离。”

**处理决策：** 接受该技术判断。文件读取和补丁工具只承诺规范化路径、重解析点检查和最终边界验证；不再声称获批子进程必然无法访问工作区外部。默认使用断网的 `DockerExecutor` 提供纵深防御；`NativeExecutor` 继承当前 Windows 用户权限，必须由用户另行显式启动，每次动作逐次审批，且 Docker 失败时不得静默降级。

### 迭代四：把“测试通过”改造成可判定契约

> 用户转述网页版 GPT 审查意见：“1.4 的‘可信失败测试’和成功状态还不可判定。”

**处理决策：** 将检查结果拆分为 `NOT_CONFIGURED / NOT_RUN / PASS / FAIL / TIMEOUT / ERROR`。已有目标必须被收集并稳定失败；目标不存在、全部通过或结果不稳定分别返回 `TARGET_NOT_FOUND`、`TARGET_NOT_REPRODUCED`、`TARGET_UNSTABLE`。目标外 pytest 及已配置 Ruff/Mypy 的基线失败以 `BASELINE_BLOCKED` 停止。自然语言复现需要在两个全新执行副本中产生相同的规范化失败指纹。这是当时的中间合同，后来被外审第三轮和第五轮进一步修订为试验 A/B、逐项检查独立副本和独立 `ReproductionEvaluation`；当前合同以 `SPEC.md` 1.4 为准。

### 迭代五：防止 Agent 修改验收器

> 用户转述网页版 GPT 审查意见：“必须补上‘验收契约不可篡改’……Agent 仍可能通过‘修改验收器’而不是修复缺陷来获得成功。”

**处理决策：** 采纳原则，但没有原样使用单一 Manifest。已有测试场景封存 `ValidationManifest v1`；自然语言场景确认复现后派生不可变的 `v2`，两个版本均保留。补丁触及已有测试、确认后的复现测试、收集配置、检查配置、检查动作或依赖清单时直接拒绝；内容漂移返回 `VALIDATION_TAMPERED`，工具或执行环境漂移单独返回 `VALIDATION_ENV_CHANGED`。

### 迭代六：明确候选验证与持久化顺序

> 用户转述网页版 GPT 审查意见：“候选补丁、持久化补丁和最终验证的顺序仍不清楚。”

**处理决策：** 没有采用“先写入权威工作区、失败后自动回滚”，因为多文件回滚可能覆盖并发修改。也没有只依赖迭代副本的摘要。最终方案是：从权威快照创建执行副本迭代；计算最终 diff 后，再从原始快照创建全新执行副本，重新应用同一 diff 并完成全部检查；用户批准精确 diff 后，确认权威工作区未变化，再持久化并核对摘要。首版要求干净 Git 工作区，否则返回 `WORKTREE_DIRTY`。

### 迭代七：解决 WebUI 交付要求

> 用户转述网页版 GPT 审查意见：“尚未处理课程要求的 WebUI 产品形态……一个公网 WebUI 不能直接读取用户的 Windows 本地仓库。”

**处理决策：** 重新检索 `AI4SE_Final_Project_通用要求.md` 和 `AI4SE_Final_Project_A_Coding_Agent_Harness(1).md`，确认纯 CLI 只影响 Open Design 条件要求，最终交付清单仍明确要求线上 URL 和可访问 WebUI。最终采用两个配置共享同一内核：本地 WebUI 仅绑定 `127.0.0.1`，执行真实仓库任务；公网 WebUI 只运行内置示例、Mock LLM 和 `DemoExecutor`，不接收用户仓库、代码或真实凭据，也不远程控制本机。

### 迭代八：澄清验收契约转换并移除首版 Native 路径

> 用户转述的外部审查：“明确 `ValidationManifest v1 → v2` 是验收契约不可修改规则的唯一受控例外”，“强烈建议把 `NativeExecutor` 移出首版必做范围”。

**处理决策：** 接受两项问题，但修正第一项的建模方式。Agent、普通工具动作或修复补丁修改当前验收契约仍始终为硬 `DENY`；`v1 → v2` 不实现为该规则的可批准例外，而是修复阶段前由可信控制面依据已批准且两阶段复现确认成功的 `ConfirmReproductionAction` 执行的独立状态转换。对于 Native，重新核算其用户价值、威胁模型和验证成本后，推翻早期“仅诊断模式”：它不能推进正式成功或持久化，却要求独立配置、审批、终态、审计、证据隔离和测试矩阵。用户授权重新打开第 1 章，首版收敛为 Docker-only，并同步修改第 2 章和过程记录。

## 4. 网页版 GPT 外部审查闭环

### 4.1 交互来源与责任边界

以下六轮意见均来自用户把当时版本的 `SPEC.md` 上传到网页版 GPT 后取得或直接粘贴的审查文本。网页版 GPT 扮演外部审阅者，当前 Codex 扮演技术复核与文档修改者，用户保留最终决策权。外部审查中的“必须修改”“有条件通过”等结论不会自动触发修改；只有经过 Codex 复核并由用户明确选择的内容才进入 `SPEC.md`。

第一至第三轮附件的本地记录时间分别为 2026-07-11 16:34、17:35 和 19:46；第五轮附件记录时间为 2026-07-12 17:02。第四轮和第六轮由用户直接粘贴，当前对话导出未提供可独立核验的精确时间。中间工作区快照没有逐轮提交，因此不能给出每轮独立 commit；每轮审查对象都是前一轮修改后的工作区版本，只有初稿 `9e1dc4a` 和第 1 章首次确认稿 `8ccc9d2` 具有 Git 标识。此限制保留在记录中，不补造中间版本号。

本节术语沿用 `SPEC.md`：pytest `node ID` 是单个已收集测试的稳定标识；`OperationalArtifact` 是仅为运行和恢复保留的本机工件；“密闭 Git”是禁用宿主 system/global 配置和外部扩展后的仓库预检语义；`ReproductionEvaluation` 是不覆盖原始检查状态的复现聚合结论。对应合同分别见 `SPEC.md` 1.2、1.3、1.4 和 1.5。

| 轮次 | 外部审查输入 | Codex 复核后的处理方式 | 用户明确决定 |
| --- | --- | --- | --- |
| 第一轮 | 快照/忽略文件、Manifest 保证范围、目标稳定性、持久化恢复、审批环境绑定等问题 | 关键语义立即修正；Docker 参数、状态枚举和支持矩阵细节后移 | “采取受控采纳” |
| 第二轮 | Native 信任边界、敏感 tracked 文件、忽略策略、复合审批、删除语义等问题 | Native 给出三种路线并推荐“仅诊断”；其余按首版范围收紧 | “选择方案1，采纳其他意见” |
| 第三轮 | 原始字节与二进制、逐测试状态、并发持久化承诺、复现 A/B 试验等问题 | 四项阻断全部采纳；提示注入、Git 策略和资源预算只在本章保留高层合同 | “按照你的方案修改” |
| 第四轮 | 本地读取与外部披露、固定复现计划、密闭 Git、补丁能力分离及三处一致性问题 | 全部认可，但将详细数据模型和参数表留给后续章节 | “全部受控采纳” |
| 第五轮 | 特殊 index 状态、纯文件执行副本、事务回滚删除、新鲜副本隔离等收口问题 | 修正四个阻断项，补齐必要语义，停止增加新治理子系统 | “选择受控收口” |
| 第六轮 | Manifest 防篡改与受控 `v1 → v2` 转换的歧义；Native 首版收益与安全成本失衡 | 将 Manifest 派生建模为可信控制面转换而非 `DENY` 例外；完整移除首版 Native 路径 | “授权” |

### 4.2 第一轮：建立可验证的树、验收与持久化语义

外部审查认为当时版本不应冻结，指出五个阻断项：已跟踪文件与忽略文件的关系不准确；测试运行时产物会污染“最终文件集合”比较；`ValidationManifest` 只防已有文件直接修改，未覆盖新增控制文件和运行期漂移；场景一只重跑首个失败目标；多文件持久化恢复仍是可选承诺；审批也没有绑定有效配置、策略、适配器和执行器 profile。审查还建议补回 Docker 最低硬化、固定公网部署模式、隔离跨项目记忆、明确不支持的修复类型并拆分状态空间。

Codex 复核后接受问题本身，但没有把所有建议原样堆入第 1 章。立即落地的内容包括：明确 `SnapshotTree / FinalDiff / CandidateTree`；比较规范化 `CandidateTree` 而非运行后的整个执行目录；对验收控制入口实施创建、修改、删除、重命名和检查前后完整性保护；重新运行全部失败目标并收紧混合状态；将崩溃一致恢复改为强制合同；让审批绑定有效安全环境。Docker 精确 flags、完整状态转换和 Manifest schema 被保留为后续章节的唯一详细定义。用户选择“采取受控采纳”。

### 4.3 第二轮：关闭 Native、敏感文件和仓库策略绕过面

第二轮确认上一轮大部分内容已落实，但发现新的边界冲突。最关键的问题是 `NativeExecutor` 继承当前 Windows 用户权限，因此“控制面未作为工具暴露”不能推出 Native 子进程无法访问控制面数据库、Keyring、Manifest 或事务工件。其余阻断项包括：敏感 tracked 文件虽然不能被文件工具读取，却可能被测试代码读取并打印；候选补丁可借修改 `.gitignore` 隐藏新增文件；一次复现批准与内部两次补丁应用在计数上冲突；`FinalDiff` 对删除和重命名的支持范围含糊。

Codex 为 Native 给出三条路线：仅作为诊断模式、使用独立低权限 Windows 身份、或缩小威胁模型。基于课程项目范围和可验证性，推荐方案 1。用户明确选择“方案1，采纳其他意见”。因此正式成功只接受 Docker；Native 标记为 `UNSANDBOXED_UNVERIFIED`，不得产生持久化授权。与此同时加入首次 LLM 调用和执行器启动前的敏感 tracked 路径预检、`OperationalArtifact` 生命周期、受保护仓库策略、一次消费的复合 `ConfirmReproductionAction`、仅支持创建或修改普通文本文件的 `FinalDiff`，并把 WebUI 不可信内容渲染和 Windows 特殊文件对象限制登记为安全设计输入。

### 4.4 第三轮：把成功条件收紧到原始字节和逐测试证据

第三轮认为第 1 章已达到“有条件确认”，但仍有四项冻结门槛。第一，快照对文本、二进制和 `HEAD` 来源的定义不一致；第二，“全量 pytest 为 PASS”无法阻止非目标测试退化为 `SKIPPED / XFAIL / DESELECTED`；第三，逐文件摘要检查与原子替换之间仍有 TOCTOU 窗口，不能承诺绝不覆盖任何并发编辑；第四，自然语言复现场景没有明确怎样同时证明失败稳定且未引入其他失败。附加建议还包括敏感路径写入拒绝、将仓库内容定义为 `UntrustedContext`、封存更广义的 Git 策略面、补充资源与披露预算以及统一术语。

Codex 复核后建议四个门槛全部修改：tracked 二进制可以进入执行副本但不能作为文本披露或由补丁修改；内容摘要基于原始字节；Manifest 记录完整 node ID 和逐测试结果，任何跳过或弱化均失败；并发合同降级为“阻止自身并发并检测已观察到的外部变化”，明确最后检查到替换之间的本机竞态不在首版保证内；复现试验 A 负责全量无回归，试验 B 负责目标失败指纹稳定。用户回复“按照你的方案修改”。敏感写入和 `UntrustedContext` 写入高层合同，Git 精确参数和资源数值预算后移。

### 4.5 第四轮：分离本地能力、数据披露和权威持久化

第四轮审查提出四个能力边界问题和三处一致性小修。第一，本地 `ReadFileAction` 的 `ALLOW` 不能自动授权把结果发送给外部 LLM，需要独立的 `DisclosurePolicy / DisclosureGrant / DisclosureRecord`。第二，`ConfirmReproductionAction` 不能声称 A/B 试验执行“相同内部子步骤”，而应绑定不可变的两阶段计划；首版复现测试还应限制为受支持测试目录中的单个普通、非参数化 pytest 函数。第三，Agent 文件工具的工作区边界与宿主级 Git 配置读取冲突，首版应采用隔离 HOME、禁用 system/global config 和外部 `core.excludesFile` 的密闭 Git 语义。第四，候选补丁应用与权威持久化不能共用一个对 LLM 暴露、可选择目标的能力接口，应拆分为 `ApplyCandidatePatchAction` 与仅由 Harness 生成的 `PersistVerifiedDiffAction`。小修包括首版绝对不支持 Git LFS、公网演示只能结束为 `DEMO_COMPLETED`，以及成功持久化后工作区会保持未提交修改、在用户处理前不能开始下一次正式运行。

Codex 判断这些建议与既有治理主线一致，但要求控制范围：本章写不可妥协的能力分离和失败关闭合同，完整披露数据模型、Git 参数及事务接口留到对应后续章节。用户选择“全部受控采纳”。落地后，本地动作授权、外部数据传输授权和副作用审批成为三个独立策略点；LLM 无法选择权威工作区作为补丁目标；演示证据也不能与正式 Docker 证据混用。

### 4.6 第五轮：受控收口并确认第 1 章

第五轮认为文本已接近冻结，只保留四个必须修正项：普通 Git status 不足以证明 `HEAD` 与工作区一致，必须拒绝 unmerged、非 stage-0、intent-to-add、`skip-worktree` 和 `assume-unchanged` 等特殊 index 状态；`ExecutionWorkspace` 必须是无任何 `.git` 元数据或指针的纯文件树；“不删除权威工作区内容”必须允许事务回滚删除由本事务创建且摘要未变化的新文件；复现试验 A 内的 pytest、Ruff 和 Mypy 仍应各自在独立新副本中运行，并用独立的 `ReproductionEvaluation` 表示“预期失败得到确认”，不能把 pytest 原始 `FAIL` 伪装成 `PASS`。

附加建议涉及 `ActionApproval` 与 `DisclosureGrant` 的关系、Native 对后续正式运行信任基础的污染、宿主 NTFS 支持范围、快照预检预算和章节迁移。Codex 推荐“受控收口”：修正四个阻断项，补齐动作批准与披露授权分离、Native 运行不可复用等必要语义；文件系统矩阵、规模预算和只移动不改语义的章节重组登记为后续强制工作，不再增加新的安全子系统。用户选择“受控收口”。

收口后进行了新鲜验证：`git diff --check` 通过；两个不携带此前对话内容、仅接收当时 `SPEC.md` 和审查问题的读者任务 `spec_round5_reader` 与 `spec_round6_reader` 分别返回“无阻断级或重要问题”，以及“1–6 项均明确满足、未发现阻断级或重要内部矛盾”。第二个读者同时指出当前文件只有第 1 章，后续安全设计、数据模型和功能规约仍不存在，因此不能确认完整 SPEC 的实现细节闭环。两次检查没有产生新的第 1 章修订。它们证明了第 1 章的无上下文可读性，但没有证据证明读者属于课程要求的“不同 Agent 类型”，也没有覆盖尚未完成的 `PLAN.md`；因此完整 `SPEC.md` 与 `PLAN.md` 获批后的正式异构 Agent 冷启动试验仍为待办，不能用本次检查替代。用户随后正式确认第 1 章，生成并推送提交 `8ccc9d2`（`确认spec文档第一章`）。

### 4.7 第六轮：在用户故事确认后重新收缩首版范围

第 2 章十条用户故事完成逐项确认和收口审阅后，外部审查只保留两个实质问题。第一，默认动作矩阵把“修改验收契约”统一列为 `DENY`，而自然语言场景又允许控制面从 `ValidationManifest v1` 派生 `v2`，陌生实现者可能把合法复现流程误判为策略例外。第二，Native 诊断继承宿主权限、不能进入正式成功或持久化、证据也不能复用，却扩大配置、审批、终态、审计、威胁模型和测试矩阵。

Codex 复核后采纳问题本身，但没有把 `v1 → v2` 写成通用 `DENY` 的“唯一例外”，而是明确为不属于 Agent 动作的可信控制面转换，避免策略引擎出现可批准绕过分支。对于 Native，Codex 不接受仅标为 stretch goal 的折中，因为保留该路径仍会污染 SPEC、PLAN 和验收边界；推荐完整移除。用户回复“授权”，允许重新打开此前冻结的第 1 章。随后 `SPEC.md` 收敛为首版只使用 `DockerExecutor`，Docker 不可用或不兼容时失败关闭，Native 列入非目标；第 2 章相关验收条件和 INVEST 表同步删除 Native 分支。

## 5. AI 建议的采纳、修正与推翻

### AI 提出或进一步细化并被采纳

- 将“Python 项目”拆成语言无关 Harness 内核与有限 Python 适配器，避免把首版支持范围误写成产品本质。
- 在用户转述的外部审查提出 Manifest 后增加 `v1/v2` 不可变版本链，并把环境漂移与内容篡改分成两个终止状态。
- 在场景一增加第二个全新执行副本，只重跑失败目标以确认稳定性，而不是相信单次失败。
- 用“全新副本最终复验 + 摘要绑定后持久化”替代“持久化后重跑并自动回滚”。
- 将一次性批准绑定到 run、动作、执行器、argv/diff、快照、Manifest、镜像、网络策略和有效期，并通过 SQLite 原子消费。
- 为本地 WebUI 增加会话令牌、Origin/Host 校验与 CSRF 防护；为公网演示增加固定场景和可丢弃状态。
- 将治理主贡献的第三个 Mock 演示确定为 `ValidationManifest` 防篡改，而不是重复演示普通命令黑名单。
- 将 `v1 → v2` 明确建模为可信控制面在修复阶段前执行的受控状态转换，而不是 Agent 修改验收契约这一硬 `DENY` 的批准例外。

### AI 草案中被用户推翻或要求修正

- **宽泛提问和草案先行：** 用户明确表示缺少领域知识，不能靠阅读整份草案找问题。后续改成细粒度、解释型选择。
- **过窄的目标用户表述：** “Windows 本地 Python 仓库”容易被理解为只能修 Python，最终改为 Windows 宿主上的本地代码仓库。
- **过强的路径安全承诺：** 最初措辞容易把工具路径围栏误解为 OS 沙箱，用户指出后改为分层承诺。
- **“完整 Python 适配器”：** 无法给出有限验收矩阵，改成明确兼容性画像，画像外返回 `UNSUPPORTED_PROJECT`。
- **有限会话授权：** 初稿曾保留该能力；用户指出范围匹配、撤销和并发消费成本后，首版删除，只实现一次性批准。
- **未限定的 Docker 失败关闭：** 中期版本曾只约束已选择 Docker 的运行，并允许用户另行启动 Native 诊断；第六轮审阅后该折中被推翻，首版改为 Docker-only。
- **保留 Native 高风险选项：** 中期版本曾把 Native 作为显式、逐次批准且不参与成功的诊断路径；重新核算用户价值、安全风险和测试成本后，用户授权将其移入非目标。

### 对用户或外部审查建议的技术核验

审查意见没有被机械照抄。例如，“删除失败测试让 CI 通过”被描述为课程中的明确示例，但在 `AI4SE_Final_Project_通用要求.md` 和 `AI4SE_Final_Project_A_Coding_Agent_Harness(1).md` 中没有检索到该原句，因此文档没有把它写成已核实事实；不过两份要求对客观、确定、可回灌机制的约束确实支持验收契约防篡改。又如，审查建议认为首版只做摘要绑定即可，最终方案增加了从原始快照重新验证的步骤；自动回滚方案则因可能破坏用户修改而被否决。

## 6. 对 Brainstorming 技能的反思

### 做得好的地方

- **增量确认有效控制了需求漂移。** 第 1 章在整体确认前始终停留在待确认稿，避免未经用户批准就提交确认版本。
- **把模糊安全目标转成可测试状态。** `WORKTREE_DIRTY`、`TARGET_NOT_FOUND`、`VALIDATION_TAMPERED`、`BUDGET_EXHAUSTED` 等状态使后续验收不再依赖 LLM 解释。
- **方案比较暴露了真实取舍。** Docker 与 Native、摘要绑定与重新验证、本地 WebUI 与远程 Agent 平台都经过替代方案比较，而不是只给一个结论。
- **能够在收到反例后回退并重构设计。** 路径围栏、验收契约和补丁事务均经过多次推翻，没有为了维护早期草案而拒绝修改。
- **重要事实经过原文核验。** WebUI 交付要求和课程机制要求通过读取本地课程文件确认，而不是仅凭记忆或用户转述。

### 让人不满或需要改进的地方

- **最初的问题过宽。** 对不熟悉 Agent Harness 的用户，直接给抽象 A/B/C 选项或完整草案会把审查责任推给用户；应更早提供术语解释和具体例子。
- **关键反例发现得偏晚。** 验收器篡改、脏工作区、候选补丁事务和 WebUI 交付冲突主要在用户追加审查意见后才暴露。更好的初次自审应主动检查这些失败模式。
- **过程较长且重复。** 每项建议都重新比较方案虽然提高了可靠性，但也增加交互轮数。后续章节应先建立统一术语表和跨章节约束表，减少重复解释。
- **第 1 章承载了较多机制细节。** 这些细节用于消除安全歧义是必要的，但后续独立“领域与机制设计”、安全和验收章节必须引用而不是复制，避免形成多份不一致的事实来源。
- **类似 Agent 的对照不是一开始就有。** 用户明确要求后才持续说明 Claude Code/OpenCode 的模式及可实现性；这一比较应在首次提供方案时默认出现。

## 7. 当前结果与后续记录

当前已完成：

- `SPEC.md` 第 1 章经过五轮网页版 GPT 外部审查、Codex 技术复核、用户逐轮决策和无上下文读者检查，已以 `8ccc9d2`（`确认spec文档第一章`）提交并推送；
- `SPEC.md` 第 2 章已形成 10 条经过逐项确认的 INVEST 用户故事并写入工作区；
- 第 2 章最终审阅触发了第 1 章的受控重开：Manifest 派生语义已澄清，首版已从 Docker + Native 诊断收敛为 Docker-only；这些最新修改尚未提交；
- 主要贡献确定为治理；
- 产品范围、工作区事务、验收契约、审批默认值、反馈状态、安全边界和 WebUI 双模式已形成基线。

尚未完成：

- 其余 SPEC 章节；
- `PLAN.md` 的任务拆分、依赖、TDD 验证步骤和并行计划。
- 完整 `SPEC.md` 与 `PLAN.md` 获批后的不同 Agent 类型冷启动试验；现有两个无上下文读者检查只覆盖第 1 章，不能替代该课程门槛。

后续每完成一个 SPEC 章节或 PLAN 的关键迭代，都应继续追加真实对话节选、被采纳或否决的建议及其理由。

## 8. 文件修改记录

自 2026-07-12 起，按用户要求，每次文件修改或创建均在本节记录实际操作、用户决策与验证结果；不补造未发生的操作。

### 2026-07-12T12:49:19Z｜统一“检查失败注入”术语

- **修改文件：** `SPEC.md`、`SPEC_PROCESS.md`。
- **原因与内容：** 外部审阅指出 `SPEC.md` 1.5 的“注入失败”与同句“提示注入”可能混淆。Codex 核验后采纳，将其改为“注入一次确定性检查失败后，Mock LLM 的下一步动作发生确定变化”，与 `US-10` 的反馈闭环语义一致；`SPEC_PROCESS.md` 新增本条真实修改记录。
- **用户决策：** 用户回复“执行”，授权修改并要求遵循逐次记录规则。
- **验证结果：** `git diff --check -- SPEC.md` 通过；旧短语“注入失败后”出现 0 次，新短语“注入一次确定性检查失败后”出现 2 次（第 1.5 节与 `US-10` 各 1 次）；`US-01` 至 `US-10` 共 10 条，数量未变化。

### 2026-07-12T12:58:26Z｜冻结第 1、2 章并请求提交

- **修改文件：** `SPEC_PROCESS.md`。
- **原因与内容：** 用户确认当前 `SPEC.md` 第 1、2 章没有其他实质性修改意见，可以冻结并继续后续章节；本条记录冻结决定、指定提交信息、推送要求以及第 3 章写作门禁。
- **用户决策：** 使用提交信息 `完成SPEC文档第二章初稿` 创建 commit 并 push；完成后停止，等待用户批准再开始第 3 章。
- **提交前验证：** 当前分支为 `main`，远端名为 `origin`；`git diff --check -- SPEC.md` 通过；`SPEC.md` 包含 10 条用户故事和 10 行 INVEST 自检；`SPEC.md` 与 `SPEC_PROCESS.md` 中占位符为 0，疑似真实凭据匹配为 0。

### 2026-07-13T14:44:42+08:00｜追加第 3 章功能规约 Brainstorming 过程证据

- **修改文件：** `SPEC_PROCESS.md`。
- **触发技能：** `brainstorming`；写入过程文档时使用 `doc-coauthoring`。
- **原因与内容：** 用户要求在继续审阅第 3.3 节期间，先把本轮第 3 章功能规约设计中的关键提问、用户决定、采纳与否决意见、冻结结果和待决事项按课程要求写入过程文档。本次只追加真实对话中已经发生的过程，不修改 `SPEC.md`，不生成实现代码，也不启动 `writing-plans`。
- **用户决策：** 第 3 章采用“规范合同优先的混合式结构”；3.1 和 3.2 已在对话中冻结；3.3 第一部分已完成收口，第二部分仍等待用户修改意见。
- **验证结果：** `git diff --check -- SPEC_PROCESS.md` 通过；受控差异仅包含 `SPEC_PROCESS.md`，共新增 166 行；新增内容中 `TODO / TBD / 待执行` 占位符为 0；3.3 第二部分被明确记录为“用户审阅中”，没有误记为已冻结。工作区原有的无关未跟踪文件保持不变。

## 9. 第 3 章“功能规约”Brainstorming 过程

### 9.1 本轮范围、输入与工作方式

用户明确要求本轮只设计 `SPEC.md` 第 3 章，不修改 `SPEC.md`，不生成实现代码，不启动 `writing-plans`。开始提问前，Codex 完整读取了：

- 当前 `SPEC.md`；仓库中没有单独的 `SPEC(9).md`，因此以现有文件为基线；
- `AI4SE_Final_Project_通用要求.md`；
- 仓库实际存在的 `AI4SE_Final_Project_A_Coding_Agent_Harness(1).md`；
- 用户指定的 Superpowers `brainstorming` 技能说明；
- 最近提交和工作区状态。

第 1、2 章继续视为冻结约束。第 3 章只能细化这些约束，不能重新开放支持范围、安全边界、审批语义、验收契约和成功条件。对话采用一次只讨论一个关键问题的方式；用户确认后再进入下一问题。所有设计先保留在对话中，没有提前写入 `SPEC.md`。

### 9.2 关键澄清问题与用户选择

| 主题 | Codex 推荐 | 用户决定 | 对第 3 章的影响 |
| --- | --- | --- | --- |
| 章节组织 | 生命周期与模块合同结合的混合式结构 | 选择推荐方案 | 3.2 提供唯一时间顺序，3.3—3.12 提供独立模块合同，3.8 用两类场景证明组合闭环 |
| 正式运行入口 | `ExistingFailure` 与 `NaturalLanguageDefect` 严格互斥 | 选择推荐方案 | 同时提供或均未提供时，在进入预检前拒绝 |
| 用户取消 | 安全点协作取消；持久化越过不可逆线后由事务恢复接管 | 选择推荐方案 | 取消请求成为正交控制面记录，不新增生命周期状态 |
| 无效模型输出与 `DENY` | 不执行动作，回灌结构化反馈；重复达到阈值后 `NO_PROGRESS` | 选择推荐方案 | 解析错误和策略拒绝可在预算内修正，但不能因“允许修正”执行原动作 |
| 检查请求 | LLM 只能选择适配器发布的检查能力 ID | 选择推荐方案 | LLM 不得提供程序、argv、工作目录、环境变量或 Shell 文本；正式验证由 Harness 自动编排 |
| 候选补丁格式 | 严格 unified diff，无 fuzz、偏移猜测或部分应用 | 选择推荐方案 | 补丁失败时当前候选树保持不变，成功后重新计算候选摘要 |
| 多轮候选管理 | 不可变 `CandidateRevision`，检查证据绑定精确修订 | 选择推荐方案 | 允许恢复当前运行内的旧修订；恢复可丢弃候选不等于允许 Agent 删除权威文件 |
| 复现方案被拒绝 | 拒绝原因可回灌并重新提出方案；过期停止；最终持久化拒绝不返回循环 | 选择推荐方案 | 原审批永久失效，新方案必须建立新审批和新绑定 |
| 完成判定 | 显式 `ProposeCompletionAction` 只请求 Harness 开始正式验证 | 选择推荐方案 | 模型不能携带权威 `success=true`，不能直接进入审批、持久化或 `SUCCEEDED` |

### 9.3 第 3 章骨架的确认与用户校正

Codex 首先提出 3.1—3.12 的“规范合同优先”骨架。用户确认总体结构，同时指出原骨架声称存在“两类场景流程”，却只显式列出自然语言复现流程。该意见被采纳，3.8 改为：

- 3.8.1 已有失败信号驱动的修复流程；
- 3.8.2 自然语言缺陷复现流程。

用户同时锁定四条写作规则：

1. 3.2 是运行状态转换的唯一规范来源；其他章节只能引用转换。
2. 每个合同只有一个权威定义位置，其他章节只能说明如何消费。
3. “可确定性验证点”必须写成可观察命题，不写测试文件或实现步骤。
4. 3.11 和 3.12 内部仍需拆成独立合同，不能把记忆、配置、凭据或可见性、审计、演示混写成一个合同。

该校正避免了目录承诺和实际章节不一致，也防止同一状态或实体在多节出现细微差异。

### 9.4 迭代一：冻结 3.1“规约约定与共同不变量”

初稿规定了规范词、统一模块合同格式、请求处理顺序、状态隔离、错误输出和确定性验证句式。用户给出附条件批准，并指出六类基础歧义：

- “应／建议／默认”等词可能被误当作规范要求；
- “控制面生成即可信”会把记录行为误写成事实证明；
- 通用处理顺序错误地假定所有动作都绑定候选修订和 Manifest；
- 执行前失败与请求发出后结果未知没有分离；
- 错误结果缺少统一信封，无法机械决定重试、等待或停止；
- “精确匹配”缺少版本化规范序列化与摘要规则。

Codex 全部接受并重写。3.1 最终锁定的共同规则包括：

- 只有“必须／不得／可以”承担规范效力；普通配置只能收紧显式开放参数；
- 模型只能提出请求或建议，不能签发审批、证据、绑定摘要或终态；
- 结构化请求依次完成 Schema、规范化、绑定、取消与预算、治理、授权、执行、后置验证和记录；
- 第 1—6 步失败不得开始执行；执行开始后的副作用状态分为 `NONE / COMMITTED / UNKNOWN`；
- 非成功结果使用统一错误信封，重试性不得从自由文本推断；
- 精确绑定基于版本化规范形式，旧证据不能证明新上下文，但继续保留为原上下文历史证据；
- 时钟、随机数、标识和调度等非确定性来源必须固定、注入或记录后重放。

用户随后正式确认 3.1 冻结，并明确后续章节不得重新定义或放宽这些共同规则。

### 9.5 迭代二：用“六状态 + 六阶段”冻结 3.2

Codex 推荐把生命周期状态与活动阶段分开，避免把失败原因、等待性质和执行位置混成一个巨大枚举。用户批准以下封闭模型：

```text
RunStatus =
  CREATED
  | RUNNING
  | WAITING_USER
  | RECOVERY_REQUIRED
  | SUCCEEDED
  | STOPPED

RunPhase =
  PREFLIGHT
  | BASELINE
  | REPRODUCTION
  | AGENT_LOOP
  | FORMAL_VALIDATION
  | PERSISTENCE
```

`RunState` 被收紧为以 `RunStatus` 为判别字段的封闭联合，`RunPhase` 只在 `RUNNING` 中存在。所有转换由控制面以预期状态、阶段、`lifecycle_revision` 和幂等事件 ID 执行 CAS；迟到事件只能形成忽略记录。取消请求、等待上下文、停止原因、预算和持久化恢复均为正交记录，不增加第七个状态或阶段。

转换矩阵进一步锁定：

- 正常成功只能从 `RUNNING(PERSISTENCE)` 进入 `SUCCEEDED`；恢复成功只能从 `RECOVERY_REQUIRED` 进入；
- `ProposeCompletionAction` 只能触发 `RUNNING(AGENT_LOOP) → RUNNING(FORMAL_VALIDATION)`；
- `WAITING_USER` 同时只能持有一个冻结对象和结果路由明确的 `WaitContext`；
- 审批、取消和超时竞争由控制面提交顺序与 CAS 决定，不依据客户端时间戳猜测；
- 外部长时执行不包含在状态事务中，控制面先持久化唯一逻辑执行尝试和调度意图，再由执行协调器领取；
- 相同事件 ID 与相同规范摘要属于幂等重放；相同 ID 与不同摘要返回 `EVENT_ID_REUSE_CONFLICT`；
- 非持久化 `UNKNOWN` 不滥用 `RECOVERY_REQUIRED`；恢复中的 `UNRESOLVED` 是递增修订号的正式自转换；
- 终态不可逆，演示完成只能得到 `STOPPED(DEMO_COMPLETED)`，不能生成正式 `SuccessRecord`。

### 9.6 迭代三：推翻“两次复现等待”，保持冻结章节一致

3.2 的中间矩阵一度包含 `REPRODUCTION_PLAN_APPROVAL` 和试验后的 `REPRODUCTION_TEST_CONFIRMATION`。附件审阅意见要求补齐这两个等待的进入、退出和 CAS 语义。Codex 逐条复核后指出，这不是单纯的状态机收口，而是新增第二个人工 Gate，与冻结第 1 章的合同冲突：当前第 1 章规定用户批准一个绑定测试补丁、目标、匹配器、环境和两阶段试验的 `ConfirmReproductionAction`；技术复现确认后由控制面派生 Manifest v2，没有试验后的第二次用户批准。

Codex 因此没有机械接受附件结论，而是推荐恢复单次审批。用户两次明确回复按 Codex 建议调整。最终可达等待类型收敛为：

```text
DISCLOSURE_AUTHORIZATION
CONFIRM_REPRODUCTION_APPROVAL
FINAL_PERSISTENCE_APPROVAL
```

复现流程最终为：冻结完整 `ConfirmReproductionAction` → 用户一次批准 → 控制面调度两阶段试验 → `CONFIRMED` 时直接派生 v2 并进入 `AGENT_LOOP`，`NOT_CONFIRMED` 时停止。通用 `ACTION_APPROVAL` 也没有为了未来扩展而留在 v1；只有 3.9 明确枚举新的 `ASK` 动作、来源阶段和结果路由后，才能通过版本化 Schema 新增等待类型。

该轮体现了本项目的责任边界：外部审查和 AI 结论都不是权威，必须与已冻结合同逐条核对；一项建议即使能让状态机更“完整”，只要悄然扩大产品流程，就不能作为文字修正合入。

### 9.7 迭代四：3.3 运行请求与准入合同

3.3 首轮设计把本地正式运行和公网演示请求分离，并把创建事务与运行内预检分开。附件审阅提出八项收口。Codex 复核后接受总体方向，但对四项作了技术修正：

- `target_node_ids` 必须使用数组保留重复信息；创建阶段只能检查数组、体量和基础语法，完整仓库相对路径规范化及语义重复检测必须等 `WorkspaceIdentityRef` 建立后在预检执行；
- 创建失败需要错误信封和无 `run_id` 审计，但审计不能默认保存低熵路径或缺陷描述的普通散列；幂等请求指纹与用户可见审计摘要必须分离；
- v1 接受“同一工作区最多一个非终态正式运行”的范围收紧，但准入租约必须带单调 fencing generation，贯穿快照、验证、持久化和恢复，而不是只在预检检查一次；
- 配置快照不得保存凭据值，预检调用方只能得到 `CONFIGURED / ABSENT / LOCKED / BACKEND_UNAVAILABLE`；底层凭据后端是否需要访问秘密以确定状态属于受控适配器实现问题，不能在功能规约中写成不一定可兑现的绝对承诺。

用户选择按 Codex 意见改进。3.3 第一部分据此锁定：请求公共信封只能声明 `request_type`，不能声明进程的 `DeploymentMode`；客户端路径只是 `workspace_locator`；创建失败保留拒绝证据；准入结果绑定版本化的本地或演示画像；预检只能调用 3.4 的 `SnapshotTree` 子合同，不能提前运行基线或派生 Manifest。

当前待确认的是 3.3 第二部分草案，内容包括本地正式准入检查表、工作区身份、准入租约、Git 三方一致性、敏感路径、Docker 准入和公网演示准入画像。用户尚未返回该部分修改意见，因此这些条款没有被记为已冻结，也没有写入 `SPEC.md`。

### 9.8 AI 建议的采纳、修正与否决

| 建议 | 处理结果 | 理由 |
| --- | --- | --- |
| 使用生命周期 + 模块合同的混合式章节结构 | 采纳 | 同时提供唯一顺序和独立可验证合同 |
| 使用不可变候选修订和严格 unified diff | 采纳 | 检查证据能够绑定精确候选，失败补丁不污染当前状态 |
| 用持久化保存的调度意图分离 CAS 与外部执行 | 采纳 | 避免把 Docker、LLM 或工作区写入错误地包进控制面事务 |
| 在功能规约中固定使用 outbox | 修正 | 只保留持久化调度意图的行为合同；outbox 属于后续架构选择 |
| 在复现技术确认后增加第二次人工语义确认 | 否决 | 与冻结第 1 章的单次 `ConfirmReproductionAction` 冲突，并新增未获批产品 Gate |
| 为未来普通 `ASK` 动作预留通用可达等待 | 否决 | v1 没有被 3.9 枚举的具体动作时，通配等待会扩大能力面 |
| 把客户端路径称为权威工作区路径 | 修正 | 请求路径不可信；只有预检形成的 `WorkspaceIdentityRef` 可以用于后续授权 |
| 允许同一工作区多个候选运行，只在最终写入时竞争 | 否决 | v1 选择单运行准入租约，降低快照失效和并发持久化复杂度 |

### 9.9 当前状态与下一步

截至本记录：

- 第 3 章正式骨架已经确认；
- 3.1 的共同不变量已在对话中冻结；
- 3.2 的生命周期、转换矩阵、等待、取消、恢复、终态和确定性验证语义已在对话中冻结；
- 3.3 第一部分已经收口；
- 3.3 第二部分仍处于用户审阅中；
- `SPEC.md` 尚未写入第 3 章正文；
- 没有生成实现代码，没有启动 `writing-plans`，也没有把当前过程记录当作课程要求的异构 Agent 冷启动试验。

下一步是在用户返回 3.3 第二部分意见后继续逐条技术复核。只有第 3 章全部分节确认后，才可以按用户后续明确授权把冻结内容写入 `SPEC.md`。

### 2026-07-13｜将已采纳的第 3 章设计同步至 `SPEC.md`

- **修改文件：** `SPEC.md`、`SPEC_PROCESS.md`。
- **触发技能：** `brainstorming`。
- **用户决策：** 用户明确要求先把当前已经采纳的设计写入 `SPEC.md`，以防长对话压缩造成关键合同丢失；该指令解除此前“第 3 章全部完成前不修改 `SPEC.md`”的临时协作门禁，但不授权生成代码或启动 `writing-plans`。
- **同步范围：** 3.1 共同规约、3.2 六状态与六阶段生命周期、3.3 运行请求与准入合同，以及 3.4 已采纳的仓库策略、预期树、快照封存和执行副本子合同。3.4 已合入快照错误码与停止原因分离、容量预留向权威容量的原子转换、接管后已发布工件的受控延续、物化尝试幂等和 `snapshot_content_ref` 完整性边界。
- **未同步范围：** 3.4 的基线证据和 `ValidationManifest v1/v2` 尚未完成共同设计；3.5—3.12 尚未起草，因此没有由 Codex 自行补全或假定冻结。
- **一致性边界：** 第 1、2 章保持冻结；复现流程仍为单次 `CONFIRM_REPRODUCTION_APPROVAL`，没有重新引入试验后的第二次人工确认；`ProposeCompletionAction` 仍只触发正式验证。

### 9.10 迭代五：将二值重试扩展为五值处置合同

3.4 快照错误设计暴露出原 `RETRYABLE / NOT_RETRYABLE` 无法区分传输重放、新逻辑 attempt、新运行和未知副作用对账。Codex 提出五值封闭模型，用户选择推荐方案 A：

~~~text
RetryDisposition =
  NO_RETRY
  | SAME_ATTEMPT_REPLAY
  | NEW_ATTEMPT_ALLOWED
  | NEW_RUN_REQUIRED
  | RECONCILIATION_REQUIRED
~~~

外部审查附条件批准，同时要求三项收口：五个值不是“最大处置范围”的大小顺序；`COMMITTED` 但权威结果不完整时必须对账；`UNKNOWN` 下的只读状态查询属于对账而不是重放。Codex 接受这些修正，用户确认冻结。

随后又受控补充事件幂等顺序：规范化和事件摘要之后，必须先查询 `(run_id, event_id)`，再检查动态 lifecycle、attempt、lease 和 generation 绑定。相同 ID 与相同摘要始终返回首次结果；同 ID 不同摘要返回复用冲突。这样避免 stale 事件在状态变化后被重新分类。

### 9.11 迭代六：快照来源、资源和支持矩阵错误

快照第一部分审查首先确认整体来源链：

~~~text
RepositoryPolicySnapshot
→ ExpectedWorktreeTree
→ SnapshotSealAttempt
→ SnapshotTree
→ MaterializationJob
→ MaterializationAttempt
→ ExecutionWorkspace
~~~

用户随后逐项选择推荐方案并确认以下边界：

- 快照资源错误与 `StopReason` 分离；容量不足统一命名为 `SNAPSHOT_STORAGE_CAPACITY_UNAVAILABLE`，控制面协议故障使用 `SNAPSHOT_STORE_ERROR`。
- `NEW_RUN_REQUIRED` 只有在 attempt、发布、容量和临时副作用全部安全关闭后才成立；完整补偿历史可以保持 `COMMITTED`。
- 初始完整稳定观察证明不一致时使用 `WORKTREE_DIRTY`；同一 attempt 的两次受控观察证明变化时继续使用 3.3 的 `WORKSPACE_MUTATED_DURING_ADMISSION` 顶层错误。
- 证据不足时使用 `SNAPSHOT_SOURCE_OBSERVATION_INCONCLUSIVE` 和 `AdmissionCheckResult = UNKNOWN`，不得猜测为脏工作区或正在变化。
- 不受支持来源分为仓库策略、文件系统对象、文本内容和保留路径冲突四个顶层错误，原因采用规范集合与版本化主原因顺序。
- v1 只支持根目录内真实、非重解析点的本地 `.git` 目录；任何 `.git` 普通文件／gitdir 指针布局均直接拒绝，控制面不得读取或跟随其目标。

外部审查提出把 `SNAPSHOT_SOURCE_CHANGED` 作为新顶层错误。Codex 没有直接采纳，因为 3.3 已冻结 `WORKSPACE_MUTATED_DURING_ADMISSION`；最终把 source-changed 收敛为强类型详情，避免两个稳定错误码表达同一事件。

### 9.12 迭代七：快照 execution generation 与安全恢复

用户确认一个运行内只有一个逻辑 `SnapshotSealAttempt`。执行进程中断时不创建第二个 attempt，而是在原 attempt 内递增 execution generation，并从头完成全量观察、二次摘要和封存。

外部附条件审查补齐了：

- attempt execution generation 与 workspace fencing generation 是独立计数器；
- 恢复使用两阶段 revocation gate，先以 CAS 撤销旧 generation 的权威提交资格，再在事务外终止或隔离旧进程；
- 新 generation 使用新临时命名空间，不复用正文、证明、游标或中间哈希；
- 旧 generation 的发布、结果、容量和清理提交全部拒绝；
- `submitted < current` 是非终止 stale，`submitted > current` 是协议违例，但必须安全关闭后才能形成运行终态；
- generation 比较必须发生在事件幂等查询之后并位于权威 CAS 边界。

`SNAPSHOT_SEAL_EXECUTION_INTERRUPTED` 被明确为非终止、非 `AdmissionCheckResult` 的尝试执行级错误，`stop_reason` 必须缺失。用户确认该结构并继续选择推荐方案。

### 9.13 迭代八：控制面对账和资源阻断

快照、物化和清理的不确定副作用采用共同四态 case：

~~~text
OPEN | RESOLVING | RESOLVED | BLOCKED
~~~

对账可以执行只读证据查询和版本化允许列表内的最小修复，但不能修改权威工作区、重新生成正文或由模型决定 disposition。中间证据修复与最终处置分离；阻断、fencing、case 终态和适用的 job/attempt 关闭必须原子衔接。

主体最初扩展为 `SnapshotSealSubject | MaterializationSubject`。附件建议无效 publication 后“保留发布历史，job 关闭”，Codex 指出这违反已经冻结的 `PUBLISHED` 不可逆终态，并提出：

- 已发布 attempt/job 始终保持 `PUBLISHED`；
- workspace 不可消费和 consumer 证据失效使用外部记录表达；
- 只有未发布 job 可以进入 `CLOSED`；
- 不新增 `RECONCILIATION_BLOCKED`，继续使用 `CONTROL_PLANE_ABORTED + block record`。

用户选择 A，确认不扩展 closure enum。

### 9.14 迭代九：`MaterializationJob`、consumer 与物化错误

用户确认 `MaterializationJob` 使用：

~~~text
PENDING | ACTIVE | PUBLISHED | CLOSED
~~~

只有 `NEW_ATTEMPT_ALLOWED` 触发 `ACTIVE → ACTIVE` 并增加 `attempt_count`；`SAME_ATTEMPT_REPLAY` 只递增 attempt execution generation。发布必须原子提交 attempt、job、`ExecutionWorkspaceRef` 和 publication record。job 固定绑定判别式源树和唯一逻辑 consumer。

物化瞬时错误被收敛为临时命名空间创建、临时文件写入和临时元数据应用三类，并且只能依据版本化 OS 错误允许列表。worker 中断不属于瞬时失败，而是同 attempt 恢复。

源内容对象或树结构的确定性完整性失效使用 `MATERIALIZATION_SOURCE_INTEGRITY_INVALID`。用户选择推荐方案 A，确认 attempt 失败、未发布 job 关闭、运行以 `INTERNAL_ERROR` 停止；直接 consumer 尚未开始时是 `NOT_RUN(CONTROL_PLANE_ABORTED)`，不是 `UNKNOWN`。阻断采用内容对象或树的最小依赖图作用域，不能改写原工件或从权威工作区补复制正文。

### 9.15 迭代十：`ExecutionWorkspaceLifecycle`

Codex 提出三种发布后生命周期模型，推荐三态 lifecycle 与独立清理 attempt。用户选择 A：

~~~text
AVAILABLE → REVOKED → RELEASED
~~~

外部审查附条件批准并补齐：

- lifecycle 与 publication、job、attempt、allocation 和不可替换 consumer binding 同时绑定；
- consumer claim 领取、结果提交和 workspace 撤销竞争同一 lifecycle revision CAS；
- `REVOKED` 只撤销未来访问，不自动否定此前完成的证据；
- `RELEASED` 只表示 workspace 专属目录、临时命名空间和容量已安全关闭，不删除源树、共享正文和历史元数据。

Codex进一步指出结果提交还必须原子终结并注销 claim，否则会留下“结果已提交但 claim 仍活动”的竞态。用户确认后，该 lifecycle 合同冻结。

### 9.16 迭代十一：单一逻辑清理 attempt

针对清理中断，Codex给出三种方案。用户选择 A：每次 revocation 只有一个逻辑 `ExecutionWorkspaceCleanupAttempt`，内部通过递增 execution generation 恢复，不创建多个 cleanup attempts。

附件附条件批准三态 attempt：

~~~text
PREPARING | SUCCEEDED | FAILED
~~~

并补充清理专用父绑定、资源绑定、generation 错误、部分删除的 `COMMITTED` 语义、独立 `CleanupRetryProfile`、no-follow 删除以及 `SUCCEEDED ≠ RELEASED`。命名空间采用永久 tombstone，不因物理释放而复用。根对象身份不匹配时不得删除或移动未知对象，必须对账和阻断。

### 9.17 迭代十二：运行级与资源级对账作用域

清理可能在原运行终态后继续，不能借用或重新打开运行生命周期。Codex给出三种协调方式，用户选择 A：

~~~text
ReconciliationCoordinationScope =
  RunScopedReconciliationScope
  | ResourceScopedReconciliationScope
~~~

快照和物化继续使用 run-scoped 单值门；清理使用 resource-scoped gate。附件附条件批准并要求资源依赖闭包、membership 注册表、直接资源授权门、无窗口 deferred-trigger handoff 和独立控制面预算。

Codex进一步指出“存在 active gate 时禁止所有读取”会使 resolver 自锁，因此增加：

~~~text
ResourceAccessAuthorization =
  NormalResourceAccess
  | ReconciliationResolverAccess
  | AuditMetadataRead
~~~

resolver 只能使用绑定 case、gate revision、claim、generation 和允许 operation kind 的专用授权；审计读取不能消费正文或形成正式证据。用户确认后，该协调合同冻结。

### 9.18 迭代十三：清理对账 disposition 与同步策略

Codex提出三种清理对账结果模型。用户先选择推荐方案 A，并随后明确要求将此前确定内容同步到 `SPEC.md`：

~~~text
CleanupReconciliationDisposition =
  RESUME_CLEANUP
  | FINALIZE_RELEASE
  | CONFIRM_ALREADY_RELEASED
  | ABORT_UNSAFE_CLEANUP
  | BLOCK_UNRESOLVED
~~~

五值模型保留“继续物理删除”“首次提交释放”“确认已提交释放”“确定性安全中止”和“无法安全判定”的差异，避免把 `COMMITTED` 结果再次执行。

本次同步没有生成实现代码，没有修改第 1、2 章，没有启动 `writing-plans`。基线证据与 `ValidationManifest v1/v2` 仍待后续共同设计。

用户随后修改后续协作门禁：收到“带条件批准”后，Codex必须先技术审阅条件、指出与冻结合同的冲突并形成修订建议，再把审阅后的结论同步写入 `SPEC.md` 与 `SPEC_PROCESS.md`；不能机械照抄附件，也无需在审阅完成后再次等待单独写入授权。该规则不包括尚未解决的开放问题，不授权实现代码、`PLAN.md` 或 `writing-plans`，也不允许重开第 1、2 章。

### 2026-07-14｜同步 3.1 重试处置与 3.4 恢复、物化、对账和清理合同

- **修改文件：** `SPEC.md`、`SPEC_PROCESS.md`。
- **触发技能：** `brainstorming`、`doc-coauthoring`。
- **用户决策：** 先同步此前确定内容；清理对账 disposition 选择 A；今后“带条件批准”即授权同步本轮已批准内容和条件。
- **同步范围：** 3.1 五值 `RetryDisposition` 与事件幂等顺序；3.4 来源和资源错误、execution generation、控制面对账、`MaterializationJob`、源完整性阻断、`ExecutionWorkspaceLifecycle`、单一清理 attempt、resource-scoped gate 和五值 cleanup disposition。
- **明确未完成：** 基线证据、`ValidationManifest v1/v2` 和 3.5—3.12；没有生成实现代码或计划。
- **验证结果：** `git diff --check -- SPEC.md SPEC_PROCESS.md` 通过；`SPEC.md` 的 3.4 标题从 3.4.1 连续到 3.4.21；旧错误名 `SNAPSHOT_STORAGE_ALLOCATION_UNAVAILABLE` 为 0；两份 Markdown 的代码围栏数量均为偶数。自审修正了资源级错误不应强制携带 `RunPhase`，以及活动 resolver 执行 `FINALIZE_RELEASE` 与普通“无活动对账”释放守卫之间的冲突。

### 9.19 迭代十四：基线执行架构与拒绝证据

Codex提出三种基线隔离粒度。用户选择 A：一个 `BaselineJob` 聚合多个独立检查 attempt，全量 pytest、每个已配置静态检查和目标稳定性重跑分别使用从同一快照物化的全新 workspace。

外部审查附条件批准，并提出不可变计划项账本、`BaselineDecision`、强类型 evidence refs、两场景判定和接受／拒绝／关闭三条路线。Codex审阅后采纳主体设计，但修正两处与冻结第 1 章冲突的建议：

1. 审查建议把目标重跑改为版本化任意次数 `N`。冻结第 1 章已经规定完整 pytest 提供第一次目标观察，另一个全新 workspace 的目标集合重跑提供第二次观察；v1 因此固定为两次，不新增任意 `N`。
2. 审查建议 ExistingFailure 的“每个目标均失败”。冻结合同允许目标稳定 `PASS` 或稳定 `FAIL`，只要求至少一个稳定失败；原本通过的目标也必须进入 Manifest 并在最终验证继续通过。

审阅后锁定：

- `BaselineJob=PUBLISHED` 表示完整基线判断已发布，可以对应 `ACCEPTED` 或 `REJECTED`；`CLOSED` 只表示判断未能发布。
- 证据完整但基线不成立时仍发布 `BaselineEvidenceSet` 和 `BaselineDecision(REJECTED)`，保留正式拒绝证据，但不生成 Manifest。
- 计划项使用 `PENDING / ACTIVE / COMPLETED / CLOSED`，一个计划项最多一个逻辑 check attempt、一个独立 materialization job 和一个权威结果。
- `BaselineEvidenceSet` 只引用 3.7 的权威结果，并验证结果提交时的 workspace publication、consumer claim、lifecycle revision、源树和环境绑定。
- 接受路线原子发布 evidence set、decision、Manifest v1、job 和场景对应生命周期转换；拒绝路线原子发布 evidence set、decision、job 与 `STOPPED(BASELINE_BLOCKED)`；取消或控制面中止先 fencing 子执行，再关闭 job 且不发布正式判断。

本轮同步仍不定义 3.7 的 `CheckResult`、失败指纹内部结构或 Manifest v1/v2 的完整 schema。

### 2026-07-14｜同步基线执行架构并更新“带条件批准”规则

- **修改文件：** `SPEC.md`、`SPEC_PROCESS.md`。
- **触发技能：** `brainstorming`、`doc-coauthoring`。
- **用户决策：** 基线隔离选择 A；“带条件批准”后必须先由 Codex 审阅并形成建议，再同步审阅后的结论。
- **同步范围：** `BaselineJob`、不可变计划项、两观察目标稳定性、`BaselineEvidenceSet`、`BaselineDecision`、场景判定和三条原子终态路线。
- **未同步范围：** Manifest 完整字段、v2 派生细节和 3.7 检查结果内部合同。
- **验证结果：** `git diff --check -- SPEC.md SPEC_PROCESS.md` 通过；3.4.20—3.4.25 标题连续；ExistingFailure 在第 1 章和 3.4 均保持“目标可稳定 PASS 或 FAIL，且至少一个 FAIL”；拒绝路线明确不生成 `ValidationManifestV1`；两份 Markdown 代码围栏成对。

### 9.20 迭代十五：`ValidationManifestV1` 合同与摘要边界

Codex提出 Manifest 的三种证据组织方式，用户选择 A：正式验收语义直接内联，详细执行结果通过不可变强类型引用关联，原始日志不进入 Manifest。

外部审查附条件批准并提出七项收口。Codex审阅后采纳以下内容：

- 最终 pytest 状态只由 `PytestContract` 定义，场景合同不得重复保存；
- node IDs 使用无重复的规范 sequence，不使用“有序集合”混合类型；
- Manifest 绑定 pytest collection/execution 的结构化 capability、action、profile 和 configuration digest；
- 受保护工件覆盖测试源、fixture/support、`conftest.py`、检查配置、依赖、解释器、collection hook 和策略工件，并增加版本化 forbidden pattern；
- 所有来源和环境引用同时绑定对象类型、Schema 和语义摘要，fencing generation 只作为创建来源元数据；
- 使用独立 `ManifestCanonicalProjection`，发布键冲突返回 `VALIDATION_MANIFEST_PUBLICATION_CONFLICT`；
- v2 必须引用 v1 根摘要并单调增加获批复现约束，不能删除或放宽 v1。

Codex没有采纳附件第一项“全部显式目标必须稳定失败”。该建议与冻结第 1、2 章直接冲突：现有合同允许显式目标稳定 `PASS` 或稳定 `FAIL`，但至少一个目标稳定失败，原本通过的目标仍必须进入最终验收。审阅后的索引规则为：

~~~text
keys(baseline_target_status_index) = canonical_target_set
failing_target_set 非空
keys(stable_failure_fingerprint_index) = failing_target_set
~~~

另外完成两项命名和能力收缩：

- 两个正式场景均要求非空原始 pytest collection；继续使用已冻结错误 `BASELINE_NO_TESTS`，不新增同义 `NO_TESTS_COLLECTED`。
- v2 只能增加 `ConfirmReproductionAction` 明确批准且 extension policy 允许的复现补丁工件；“相关支持工件”不能自动获得写入或保护合同扩展权限。

最终写入的 Manifest v1 合同包括来源、pytest、场景、结构化检查、保护工件、验证环境、规范摘要投影、发布幂等和 v1→v2 单调边界。它继续只在 `BaselineDecision(ACCEPTED)` 的原子发布事务中形成。

### 2026-07-14｜同步 `ValidationManifestV1` 审阅结论

- **修改文件：** `SPEC.md`、`SPEC_PROCESS.md`。
- **触发技能：** `brainstorming`、`doc-coauthoring`。
- **用户决策：** Manifest 采用“规范合同内联、执行证据强类型引用”的 A 方案；附条件批准后按 Codex 技术审阅结论同步。
- **同步范围：** Manifest 核心 Schema、唯一 pytest 权威位置、场景联合、结构化能力动作、保护角色与禁止模式、环境摘要、规范投影、发布幂等和单调 v2 边界。
- **明确否决：** 不把 ExistingFailure 改成“全部显式目标必须失败”；不新增 `NO_TESTS_COLLECTED`；不允许未批准支持工件进入 v2。
- **验证结果：** `git diff --check -- SPEC.md SPEC_PROCESS.md` 通过；附件要求删除的三个重复最终状态字段均为 0；`NO_TESTS_COLLECTED` 为 0；Manifest 顶层来源、baseline job/evidence/decision 和环境引用均同时绑定语义摘要；Markdown 代码围栏成对。

### 9.21 迭代十六：`ValidationManifestV2` 单调派生

Codex提出三种 v2 表示方式，用户选择 A：父 v1、复现扩展 delta、派生证明和物化后的有效合同投影同时保留。该结构既避免完整复制父字段，又允许后续检查直接消费唯一有效合同。

外部审查附条件批准并提出七项收口。Codex审阅后采纳：

- 一次性人工批准在复现补丁应用和两阶段试验之前消费；v2 发布只验证批准消费记录，不再次消费批准，也不增加第二次确认；
- 只有两阶段结果完整且可确定解释时才能形成复现判定；证据缺失或 `UNKNOWN` 不能折算为 `NOT_CONFIRMED`；
- 复现补丁使用版本化加法策略、文件数和字节上限，所有新增工件立即成为不可削弱保护约束；
- 两类试验完整交叉绑定父 v1、候选树、目标集合、matcher、Docker、check profile 和 filesystem profile；
- effective contract 只能由控制面按 `inherit(v1) + apply(extension)` 计算；
- v2 发布键移除 action ref，固定为每个 owner run 和 parent v1 最多一个权威 v2；
- 成功发布原子提交 evaluation、extension、proof、effective contract、v2、accepted record、新 phase-entry 和 `RUNNING(AGENT_LOOP)`。

Codex在写入时做了两处权威边界修正：

1. `ReproductionEvaluation` 的状态和值继续由 3.8 唯一定义。3.4 只规定它何时可以存在以及 Manifest 发布如何消费其引用，避免同一状态空间出现两个权威位置。
2. v1 的 extension policy 不得覆盖既有 `PRESENT / ABSENT / forbidden pattern`。`conftest.py`、pytest/plugin/config、依赖、解释器、Ruff/Mypy 和 Git 策略入口在 v1 中硬拒绝。当时写入为允许 action 明确批准的测试源和策略允许的局部测试支持文件；该“局部测试支持文件”表述后来在 9.22 审查中被认定与冻结第 1 章冲突并撤销。

`reproduction_candidate_tree` 被锁定为 repair base，而原始 `SnapshotTree` 始终保持来源身份。3.4 不创建 `CandidateRevision`；3.6 后续只能根据这里冻结的 repair base 建立初始候选修订。最终 diff 仍必须相对原始快照表达复现补丁与生产代码修复的组合。

### 2026-07-14｜同步 `ValidationManifestV2` 审阅结论

- **修改文件：** `SPEC.md`、`SPEC_PROCESS.md`。
- **触发技能：** `brainstorming`、`doc-coauthoring`。
- **用户决策：** v2 采用“父 v1＋扩展 delta＋有效合同投影”的 A 方案；附条件批准后按 Codex 审阅结论同步。
- **同步范围：** 批准时点、复现补丁策略、两阶段交叉绑定、evaluation 存在边界、有效合同、派生证明、唯一发布键和 Agent-loop 阶段入口。
- **未越权定义：** 3.7 matcher/CheckResult、3.8 ReproductionEvaluation 状态和 3.6 CandidateRevision 仍留在各自权威章节。
- **验证结果：** `git diff --check -- SPEC.md SPEC_PROCESS.md` 通过（仅有 Git 的 LF→CRLF 工作区提示）；3.4.28—3.4.32 标题连续；反引号与波浪号代码围栏分别成对；3.4 未重新定义 `ReproductionEvaluation`；`VALIDATION_MANIFEST_V2_PUBLICATION_CONFLICT`、不含 action ref 的 v2 发布键及 `conftest.py` 硬拒绝均已落位。

### 9.22 迭代十七：Agent 单轮、动作信封与调用边界

进入 3.5 前，Codex完整复核了当前 `SPEC.md`、课程通用要求和 Coding Agent Harness 专项要求。审查结论是：3.1—3.4 已覆盖共同不变量、生命周期、准入以及快照／基线／Manifest，但 3.5—3.12 尚未覆盖主循环、工具、反馈、治理、持久化、记忆、配置和可见性。Codex建议允许结构性精简，用户选择 B：3.1—3.4 只修明确矛盾，不调整既有篇幅和结构。

随后采用逐题单选方式冻结 3.5 第一部分的主要决策：

- 每次通过 Schema 校验的 LLM 输出恰好包含一个结构化动作，不允许动作数组。
- 动作信封包含限长 `reason_summary`，但其不具授权或证据效力。
- Agent 请求检查时只能提交注册能力 ID 和受限参数；可信适配器生成 executable、argv、工作目录、超时和输出上限。
- `ApplyCandidatePatchAction` 可以携带原子多文件补丁；补丁绑定当前候选修订，成功后生成不可变子修订，陈旧补丁不得自动合并。
- 完成与停止分为 `ProposeCompletionAction` 和 `ProposeStopAction`；前者只能请求正式验证，后者只能请求非成功停止。
- 持久记忆由 Harness 按需选择并只从已验证事实形成，模型不能直接写入；完整原始对话历史不进入后续上下文。
- 上下文超限时按固定优先级整项淘汰可选投影；强制项仍超限则不调用 LLM，不增加额外真实 LLM 摘要步骤。
- v1 代码检查工具为 `ListFilesAction`、`ReadFileAction` 和只支持有界字面量的 `SearchTextAction`；不增加符号索引或正则搜索。
- pytest 只能选择 Harness 注册的目标集合或完整 Manifest 范围，不允许任意 node ID。
- 普通动作首次被 `DENY` 时回灌结构化拒绝并允许修正；只有控制面完整性、策略定义或安全绑定失效可以立即停止。相同候选和策略上下文中的规范动作—结果指纹重复用于确定性 `NO_PROGRESS` 判定。
- 自然语言场景使用独立 `ProposeReproductionAction`；失败匹配器只允许异常类型、消息字面片段、阶段和可选仓库相对栈帧，不接受正则。
- 合法 `ProposeStopAction` 在安全点形成非成功停止，权威 `StopReason` 仍由 Harness 决定。
- 无法解析的模型输出只生成结构化反馈，不执行动作、不从自由文本猜测；达到无效输出阈值后停止。

Codex随后提出三种轮次持久化方式。用户选择 C：混合式持久化。控制面持久化轮次起点、规范输出、绑定动作、权威结果和完成记录；上下文渲染等纯计算步骤根据已保存事实重建，不把每一步扩张成独立运行生命周期。

第一版章节设计收到外部“附条件批准”，共提出七项收口。Codex逐条审阅后的处理为：

1. 接受不可变记录链，但拒绝强制 `raw_response_ref`。完整原始模型响应与第 1 章默认不持久化原始输出的要求冲突，因此改为判别式输出结果，只持久化解析结果、脱敏摘要和必要摘要。
2. 接受 `ReproductionTurnSubject | RepairTurnSubject`。把含糊的当前复现提案可选引用改为受控 `reproduction_iteration_context_ref`；ExistingFailure 绑定 v1 和原始快照，NaturalLanguage 修复绑定 v2 和 reproduction candidate tree。
3. 完全接受“恰好一个动作只适用于被接受的有效输出”；调用或解析失败形成零动作。
4. 接受模型载荷与权威绑定分离，但不接受模型提供的阶段或摘要字段作为待校验声明。封闭 Schema 必须直接拒绝这些未知字段；阶段专用绑定统一通过判别式 turn subject 引用。
5. 完全接受单活动轮次、原子序号和 CAS；轮次不能跨越等待、新 phase-entry 或终态。
6. 完全接受按阶段锁定动作 allowlist。`REPRODUCTION` 禁止普通补丁和普通检查，防止绕过复现审批；`ConfirmReproductionAction` 明确不属于模型动作。
7. 接受精确披露与调用边界，但把 `ContextProjection` 和实际供应商请求分开：前者表示语义选择，后者通过 `RenderedLLMRequest` 绑定提示模板、动作 Schema、适配器和实际规范请求摘要。同时把“轮次如何完成”和“完成后去哪里”拆成 `AgentTurnCompletionKind` 与 `TurnContinuationDisposition`，避免 `STOP_PROPOSED`、`WAIT_CREATED` 等混合状态。

本轮还修正了 3.4.28 的明确跨章矛盾。冻结的第 1 章只允许新增一个普通测试模块和一个非参数化 pytest 测试函数，因此撤销 9.21 曾记录的 `REPRODUCTION_TEST_SUPPORT` 扩展，`ReproductionPatchPolicy` 收紧为一个 `REPRODUCTION_TEST_SOURCE`、一个新增文件和一个测试函数。该修正不重开第 1、2 章，而是使 3.4 与冻结合同一致。

### 2026-07-14｜同步 3.5 第一部分与复现补丁范围修正

- **修改文件：** `SPEC.md`、`SPEC_PROCESS.md`。
- **触发技能：** `brainstorming`、`doc-coauthoring`。
- **用户决策：** 确认 3.5 第一部分；采用单轮单动作、阶段判别主体、控制面动作绑定、单活动轮次 CAS、阶段 allowlist、精确渲染请求和混合式持久化。
- **同步范围：** 3.5 的不可变轮次记录链、上下文投影、LLM 请求边界、封闭动作联合、阶段允许列表、完成与后续处置、主循环顺序和可确定性验证点；同时删除 3.4.28 对测试支持工件的放宽。
- **未同步范围：** 3.6 候选修订完整合同、3.7 检查结果内部结构、3.8 场景编排、3.9 策略／审批／披露内部状态、3.10—3.12；没有生成实现代码或启动 `writing-plans`。
- **人工审查修正：** 不强制保存原始 LLM 响应；模型 Schema 不接受阶段或摘要声明；轮次完成类型与后续流向保持强类型分离。
- **验证结果：** `git diff --check -- SPEC.md SPEC_PROCESS.md` 通过；3.5.1—3.5.9 标题连续；`SPEC.md` 与 `SPEC_PROCESS.md` 的波浪号代码围栏均成对；`SPEC.md` 中 `REPRODUCTION_TEST_SUPPORT`、局部测试支持文件和 `raw_response_ref` 均为 0；占位符扫描为 0。回读时进一步修正了轮次完成与生命周期转换的原子窗口、取消发生在输出前时的条件引用，以及停止原因必须唯一选择的问题。

### 9.23 迭代十八：只读 Agent workspace 与确定性文件工具

3.5 第二部分继续采用逐题单选方式冻结文件检查和披露前置边界。用户确认：每个候选修订使用专用 Agent 工作副本；大文件按 `start_line + max_lines` 分段读取；列表支持受限深度、glob 和分页；搜索只支持区分大小写的单行字面量；本地读取成功但披露授权不足时必须进入披露等待；完整正文只存临时运行缓冲区；列表和搜索分页使用绑定修订与查询的 continuation cursor。

外部审查对该方向附条件批准并提出七项收口。Codex逐条技术审阅后的处理为：

1. 接受所有已发布 Agent workspace 只读且不可变，以及新候选、新 workspace、旧 workspace 撤销和补丁成功结果的原子激活。额外增加 `CurrentAgentWorkspaceBinding`：新 workspace 即使 lifecycle 为 `AVAILABLE`，在成为当前 binding 前也不能被工具领取。物化或 CAS 失败时旧候选和旧 workspace 保持有效。
2. 接受每个文件工具动作具有独立 attempt 和幂等结果，但修正“不可变工具尝试”的表述。attempt ID、绑定动作和规范输入不可变；`PREPARING → PUBLISHED / FAILED` 通过起始记录、至多一个终态记录和 CAS 表达，不把带状态聚合误称为整体不可变对象。
3. 接受版本化 `AgentFileToolProfile`。路径、glob、深度、页大小、单行、总字节和查询上限均由控制面绑定，普通配置只能收紧；模型输入不具授权效力，受限 glob 不交给 Shell 或宿主实现。
4. 接受固定文本行、UTF-8、BOM、CRLF／LF／CR、EOF、Unicode 和字面量匹配语义。除读取超长单行错误外，补充 `SEARCH_MATCH_LINE_TOO_LARGE`，避免搜索路线绕过相同体量边界。
5. 接受把列表和搜索改为 Start／Continue 判别联合。继续请求只能携带控制面签发的 opaque cursor，原查询由权威 cursor 取得；cursor 重放不消费、不推进，不能跨 workspace 或候选修订。
6. 接受临时正文 `AVAILABLE → RELEASED` 的不可逆生命周期、持久元数据隔离和精确 payload digest；不接受附件提出的“披露等待或其他不声称模型已看到正文的路线”。用户已经明确选择授权不足时进入披露等待，因此只能等待，或由取消、预算耗尽、控制面完整性失败等更高优先权威条件停止，不得静默省略正文继续。
7. 接受每次列表、读取和搜索重新验证 workspace 完整性。`TOOL_RESULT_INTEGRITY_INVALID` 必须阻止成功 payload 和披露、撤销 workspace，并与正常清理后的 `TRANSIENT_CONTENT_UNAVAILABLE` 保持不同。

为兼容冻结第 1 章中“`AGENT_LOOP` 工作副本允许文件检查和候选补丁”的表述，`ApplyCandidatePatchAction` 仍在动作与策略层绑定当前 Agent workspace，但 PatchEngine 只能基于其绑定的 `CandidateTree` 创建 staging tree 和新候选，绝不修改已发布 workspace。这样保留了动作目标绑定，同时落实“补丁失败后当前副本逐字节不变”。

最终写入的第二部分包括：Agent workspace publication 与当前绑定、候选原子激活、文件工具画像、attempt 幂等、列表／读取／搜索 Schema、严格文本语义、cursor 能力、临时正文生命周期、精确披露门、逐次完整性校验和十项 mock-LLM 可确定性验证点。本轮没有定义 3.6 PatchEngine 内部实现、3.9 `DisclosureGrant` 状态机或任何实现代码。

### 2026-07-14｜同步 3.5 第二部分审阅结论

- **修改文件：** `SPEC.md`、`SPEC_PROCESS.md`。
- **触发技能：** `brainstorming`、`doc-coauthoring`。
- **用户决策：** 确认专用只读 workspace、有界范围读取、受限列表和字面量搜索、绑定 cursor、临时正文隔离，以及授权不足时进入披露等待。
- **同步范围：** 3.5.10—3.5.19 的 workspace/current binding、候选原子激活、工具画像与 attempt、三个文件工具、分页、正文生命周期、披露和完整性门。
- **审阅修正：** attempt 采用不可变身份／输入加追加式状态记录；新 workspace 未成为当前 binding 前不可领取；搜索命中超长单行独立失败；删除未定义的披露替代路线。
- **未同步范围：** 3.6、3.9 及后续章节的内部合同；没有生成实现代码、没有启动 `writing-plans`、没有提交 Git。
- **验证结果：** `git diff --check -- SPEC.md SPEC_PROCESS.md` 通过（仅有 Git 的 LF→CRLF 工作区提示）；3.5.1—3.5.19 标题连续；`SPEC.md` 与 `SPEC_PROCESS.md` 的波浪号代码围栏分别为 186 和 20，均成对；新增区间无 `TODO / TBD / 待本次 / 待执行` 占位内容；补丁明确不得写入旧 workspace，授权不足只能进入披露等待或由更高优先权威条件停止。

### 9.24 迭代十九：反馈资格、精确作用域与适用性

3.5 第三部分开始设计结构化反馈闭环。Codex先明确：反馈只是控制面对既有权威结果生成的受限模型投影，不重新解释执行事实，不产生授权，也不能让模型决定哪些结果有效。用户通过逐题选择确认每个来源最多一条反馈、`source_kind` 与强类型 `feedback_body` 一一对应、控制面按版本化画像确定性投影，以及披露和上下文预算只在消费阶段处理。

本轮一度把外部审查拆成只剩单一接受选项，用户指出这不符合 brainstorming。Codex随后恢复每题提供三个真实方案、取舍和推荐，再由用户选择的方式；该过程修正不改变已经冻结的技术结论。

第一组外部审查对反馈权威边界附条件批准。Codex与用户逐项收口：

1. 接受不可变、唯一的 `FeedbackEligibilityRecord`，把“能否反馈”和“如何投影”拆成 `eligibility_profile` 与 `FeedbackProfile`。旧来源形成终局资格后不得因画像升级重新评估。
2. 接受由控制面强类型绑定目标 Agent scope，复用 3.5.2 的 `AgentTurnSubject`。补丁成功绑定新候选和已经激活的新 workspace；补丁失败绑定原候选；正式验证失败和用户修订绑定返回后的新 phase-entry。
3. 接受按同阶段继续、候选切换和阶段返回拆分原子事务；普通下一轮不能创建新 phase-entry。稳定 `INELIGIBLE` 不回滚候选或生命周期领域事实。
4. 接受发布与可消费分离。反馈始终不可变，后续来源或目标失效只能通过独立记录和消费资格门表达。
5. 接受规范摘要排除数据库 ID、存储地址和临时正文物理位置，只纳入对象类型、Schema 版本和语义摘要。
6. 接受机械化资格路线。可修正拒绝、补丁结果以及明确返回 Agent 的检查／正式验证失败可以有资格；停止、取消、预算、传输、内部完整性和敏感硬拒绝没有资格。

第二组资格与作用域审查进一步提出五项。用户确认：

- `AgentFeedbackRecord` 必须显式引用同一事务发布的唯一 `ELIGIBLE` 资格记录；`INELIGIBLE` 不生成反馈或目标作用域。
- 来源未完成、资格内部失败、绑定陈旧、目标未建立或 CAS 失败表示“尚无资格记录”，不能永久写成 `INELIGIBLE`。
- `AgentFeedbackTargetScopeBinding` 使用 `bound_target_scope_revision`，发布后不可修改；任何不同 phase-entry、Manifest、候选或 workspace 均不自动继承反馈，包括祖先—后代候选。
- workspace 绑定由版本化画像的 `REQUIRED / FORBIDDEN` 决定，模型、用户和发布调用方不能选择。
- 来源采用判别联合：解析、动作拒绝、文件工具、补丁和检查绑定来源 turn；用户修订只绑定 wait 与决定；正式验证绑定验证 subject 和结果。
- `reason_codes` 是按版本化严格全序排列的无重复序列：`ELIGIBLE` 为空，`INELIGIBLE` 非空。

用户正式批准并锁定该组合同。对话中曾出现“这是 5.4 吗”的编号疑问，最终澄清为 `SPEC.md` 第 3 章中 `3.5` 的第三部分，不是 5.4，也不是 3.5 的文件工具第二部分。

第三组审查聚焦原子发布与反馈适用性。Codex提供并由用户确认的最终结构为：

- `FeedbackApplicabilityPolicy = NEXT_TURN_ONLY | UNTIL_SUPERSEDED`；策略名称与保留期限分离。
- 每条反馈绑定强类型、版本化 `FeedbackSemanticSlot`；只有 slot 摘要完全相同的新权威结果才能 supersede，且新结果即使 `INELIGIBLE` 也可以结束旧反馈的适用性。
- continuation、supersession 和 invalidation 都是独立追加事实，不修改原反馈、不修改原目标作用域，也不能使旧反馈复活。
- 跨后代候选只能通过显式 continuation，必须具有 ancestry proof、重新验证来源与目标，不得成环或绕过披露、预算和来源失效检查。
- continuation 数量由版本化画像限制；超过上限时按严格顺序选择前 N 条并发布 `FeedbackContinuationSelectionRecord`。`LIMIT_EXCEEDED` 只是选择结果码，不阻止候选激活，也不是停止或重试错误。
- supersession 与 invalidation 通过 CAS 竞争；先形成的终止事实获胜，新反馈后来失效也不能回退选择旧反馈。

`NEXT_TURN_ONLY` 的基础语义同时锁定：ContextProjection 创建 reservation；只有精确目标 scope 内首个形成 `AcceptedTurnOutputRecord` 或 `RejectedTurnOutputRecord` 的后续 turn 完成消费。`LLMCallFailureRecord`、输出前取消和安全中止不消费；scope 仍有效时替代 turn 可以重新选择。Schema 无效但已经形成权威拒绝输出时会消费一次性反馈。

### 2026-07-14｜同步 3.5 第三部分前段

- **修改文件：** `SPEC.md`、`SPEC_PROCESS.md`。
- **触发技能：** `brainstorming`、`doc-coauthoring`、`verification-before-completion`。
- **同步范围：** `3.5.20—3.5.30` 的反馈权威边界、不可变资格记录、精确目标作用域、来源判别联合、反馈摘要、三条原子发布路线、适用策略、semantic slot、continuation／supersession／invalidation、消费资格门和 `NEXT_TURN_ONLY` 基础语义。
- **明确未同步：** 当前仍在附条件审查的反馈选择记录、消费清单、精确 `ContextProjectionPayload`、披露 draft、Reservation 完整记录结构与最终 CAS；这些内容继续逐题 brainstorming，不能从基础 reservation 语义自行推导。
- **边界保持：** 没有定义 3.6 候选内部实现、3.7 检查内部结构、3.9 披露授权状态机，没有修改第 1、2 章，没有生成实现代码、启动 `writing-plans` 或提交 Git。

### 9.25 迭代二十：反馈选择协议与 v1 范围重置

3.5 第三部分后段最初围绕反馈选择、精确投影、消费清单和 reservation 展开。用户逐题确认了以下基础方向：适用集合与最终选择分离；selection entry 与 consumption entry 分离；`SUMMARY_ONLY / SUMMARY_AND_DETAIL` 在选择阶段固定；真实调用使用专用 `ContextProjectionPayload`；consumption manifest 单向引用 projection；`NEXT_TURN_ONLY` 使用一次性 reservation；Accepted／Rejected 全量消费，终态调用失败和输出前终止全量关闭。

外部审查随后持续把可选的生产级可靠性增强升级为冻结条件，设计范围逐步扩张到 Stage2 processing claim、execution generation、撤权 gate、响应正文持久恢复、reconciliation case、persistent block、successor case、block handoff、恢复工件、prepared／published buffer、迟到 transport 兼容矩阵和多层 cleanup reconciliation。每个新增对象又引入唯一键、幂等、迟到结果、清理未知和对账问题，导致验收门槛持续后移。

用户明确指出该审查流程已经失控：功能规约被扩张成生产级崩溃一致工作流引擎，超过课程要求与个人项目周期。Codex接受该判断并停止继续增量补洞。由于这些 Stage2 设计尚未写入 `SPEC.md`，范围重置不需要回滚文件。

Codex提出三种收敛方向：直接冻结课程可实现 v1、把完整协议移入架构附录、或继续把完整协议作为 v1。用户确认采用第一种。双方固定七项封闭验收维度：功能闭环、权威边界、模型不参与授权、reservation 不部分消费、内部故障安全停止、Mock LLM 离线可测，以及单人课程周期内可实现。

最终 v1 保留：

- eligible、selected 与 excluded 的确定性区分；
- selection entry 与 consumption entry 分离；
- summary／detail 强类型选择及禁止发送时降级；
- 精确披露 draft、完整 `ContextProjection` 摘要和调用专用 payload；
- 每 turn 唯一 consumption manifest；
- `NEXT_TURN_ONLY` reservation 和 `UNTIL_SUPERSEDED` 无 reservation；
- Accepted／Rejected 全量消费，终态调用失败、取消和安全中止全量关闭；
- 响应后的不可恢复控制面故障以 `INTERNAL_ERROR` 失败关闭且不重新调用供应商；
- Mock 与真实适配器共享确定性控制面路径。

明确下放到架构、PLAN 或未来版本：

- Stage2 processing generation、claim takeover 和 revocation；
- 原始响应跨崩溃恢复和 response reconciliation；
- persistent processing block、successor case 与 handoff DAG；
- recovered response artifact 与 response publication 状态机；
- transport late-result 完整兼容矩阵；
- 多层资源清理对账。

用户审阅精简稿后正式批准。Codex同时把 3.5.29 中容易被理解为可变版本的 `reservation_revision` 收口为不可变创建绑定 `created_under_target_scope_revision`；v1 不引入 reservation generation。

### 2026-07-14｜同步 3.5 第三部分后段与范围重置

- **修改文件：** `SPEC.md`、`SPEC_PROCESS.md`。
- **触发技能：** `brainstorming`、`doc-coauthoring`、`verification-before-completion`。
- **同步范围：** `3.5.31—3.5.39` 的确定性选择、selection／consumption 分离、披露 draft、调用专用 payload、manifest 与 reservation、最终发布、输出终态、v1 内部故障关闭、非目标和十五项封闭验证门。
- **范围修正：** 未把此前讨论的 Stage2 generation、响应恢复、reconciliation、persistent block、successor handoff 和生产级迟到 transport 协议写入 v1。
- **既有合同修正：** `3.5.29` 的 `reservation_revision` 改为 `created_under_target_scope_revision`，避免暗示 reservation 可以原地更新。
- **边界保持：** 没有修改第 1、2 章，没有生成实现代码、启动 `writing-plans` 或提交 Git。
- **验证结果：** `git diff --check -- SPEC.md SPEC_PROCESS.md` 通过（仅有 Git 的 LF→CRLF 工作区提示）；`3.5.29—3.5.39` 标题连续；两份文档的波浪号代码围栏均成对；新增区间占位符为 0；旧 `reservation_revision` 为 0；被下放的 Stage2、response reconciliation、persistent block 和恢复工件 Schema 定义为 0。

## 10. 2026-07-15｜v1 范围收敛与 3.5 机械迁移

### 10.1 范围失控与封闭验收维度

回看 3.1—3.5 的形成过程，原本针对功能规约的审查逐步吸收了生产级工作流引擎问题：execution generation、资源 gate 与 block、claim takeover／revocation、物化 job、跨进程恢复、reconciliation case、持久处理阻断和多层 cleanup 对账。每增加一个对象，又继续派生唯一键、迟到结果、接管、清理未知和二次对账要求，导致课程 v1 的完成条件不断后移。该扩张不是实现 Agent 主循环、确定性 guardrail、反馈纠正和离线 Mock LLM 测试所必需的功能闭环。

本轮因此把以下七项固定为封闭验收维度，不再由生产级高可用建议继续扩张：

1. Coding Agent Harness 的最小功能闭环可运行；
2. 权威输入、结果与持久化边界可判定；
3. 模型不参与授权或安全事实判定；
4. feedback reservation 不部分消费或部分关闭；
5. 内部故障安全停止且不伪造成功；
6. 核心机制可用 Mock LLM 离线确定性测试；
7. 方案在单人课程项目周期内可实现、可演示和可验证。

### 10.2 v1 保留项与下放项

v1 保留：顺序单轮 Agent 主循环、封闭动作联合、确定性动作绑定与 guardrail、精确 `SnapshotTree | CandidateTree` 来源绑定、硬容量限制、不得部分发布、一次性全新执行副本、`ExecutionWorkspaceEvidence`、`ExecutionWorkspaceCleanupResult` 与 quarantine 记录、结构化反馈资格／选择／消费、临时正文隔离、披露前置门、Mock LLM 离线测试以及 3.10 专用持久化恢复边界。

下放到架构说明、实施 PLAN 或未来增强的内容包括：数据库与对象存储物理布局、分布式 execution／fencing generation、长期资源 allocation、物化 job 调度、claim takeover／revocation、资源 gate／block 图、通用 reconciliation engine、Stage2 响应处理、原始响应跨崩溃恢复、persistent processing block、successor／handoff DAG 和多层 cleanup reconciliation。这些内容可以作为后续设计材料，但不再成为 v1 功能规约、冻结或课程完成的前置条件；本轮没有因此修改 `PLAN.md`。

本轮采纳的建议是：保留确定性安全门、强类型来源、精确摘要、硬容量、原子发布、一次性执行证据与清理证明，并让这些机制在替换真实 LLM 后仍可独立测试。拒绝升级为 v1 条件的建议是：把每个本地 attempt 建模为持久 job／generation，把物理目录生命周期当作 Agent 的长期权威状态，以及要求通用 takeover、block handoff 或 reconciliation 工作流才能完成课程验收。

### 10.3 3.1—3.5 的实际收敛结果

- **3.1：** 保留共同请求顺序、事件幂等、错误信封、规范化与摘要、状态空间隔离和可确定性验证；不再把普通 attempt 扩张为带多 generation、takeover 和资源阻断图的执行引擎。
- **3.2：** 保留运行状态、阶段、三类等待、取消、停止和转换矩阵；`RecoveryDisposition` 只服务于 3.10 权威工作区持久化专用的三结果语义，不泛化到 LLM、文件工具、披露或普通清理失败。
- **3.3：** 保留请求、静态校验、工作区身份、OS 排他锁、旧运行门、正式创建和准入结果；不再建立资源级 reconciliation gate、run-resource block binding 或通用接管图。
- **3.4：** 收敛为 `RepositoryPolicySnapshot → SnapshotTree → ExecutionWorkspaceEvidence → BaselineEvidenceSet → BaselineDecision → ValidationManifestV1 → ReproductionEvaluation(CONFIRMED) → ValidationManifestV2` 的完整权威链；执行 consumer 使用独立全新副本，受硬容量约束，并在 consumer 启动前形成不可变 `ExecutionWorkspaceEvidence`；consumer 完成 post-run 验证且必要 payload 转存后形成 `ExecutionWorkspaceCleanupResult`，满足这些绑定后才允许原子发布。`MaterializationPublicationRecord` 的规范职责由 `ExecutionWorkspaceEvidence` 承担；旧 `WorkspaceReleaseRecord`／cleanup attempt 由 cleanup result 与 quarantine 记录承担；不再保留 `AuthoritativeArtifactAllocation` 这一长期 allocation 对象，但硬容量与不得部分发布行为仍保留。
- **3.5：** 只做与上述已冻结 3.4 对象一致的机械迁移：把旧 Agent physical workspace publication／lifecycle／current binding 重绑为逻辑 `AgentWorkspacePublication`、`CurrentAgentSourceBinding`、精确 source tree ref／digest，以及产生具体工具结果的一次性 `ExecutionWorkspaceEvidence` 与 cleanup result。动作联合、反馈 reservation、LLM 输出联合、选择／消费和故障关闭行为均未重新设计。

### 10.4 自动引用清单与处理分类

本轮先从 `2864a53^:SPEC.md` 自动截取旧 3.4，使用正则提取反引号代码跨度内的标识符、PascalCase 类型、全大写枚举，以及名称中含 generation／gate／block／claim／lifecycle／cleanup／reconciliation 的词项，再与任务给定种子表取并集。并集共 339 个候选；编辑前扫描当前 `SPEC.md` 实际命中 170 个、扫描 `SPEC_PROCESS.md` 实际命中 129 个。计数是候选名称去重后的文件级命中，不把未出现的种子误报为当前依赖。

实际命中按以下三类处理：

1. **从当前规范删除：** physical Agent workspace lifecycle、workspace fencing generation、长期 claim／revocation、工具恢复／对账依赖，以及不再承担 v1 职责的旧 allocation／job／gate／block／release／cleanup-attempt 对象。
2. **替换为 v1 简化对象：** Agent 当前视图改绑 `CurrentAgentSourceBinding` 与精确 `SnapshotTree | CandidateTree`；`MaterializationPublicationRecord` 职责改由 `ExecutionWorkspaceEvidence` 表达；release／cleanup attempt 改由 `ExecutionWorkspaceCleanupResult` 和 quarantine 记录表达。硬容量、完整副本、必要正文先转存和不得部分发布语义继续保留。
3. **仅保留历史或未来增强说明：** Stage2 多 generation、恢复响应、persistent processing block、claim takeover、response reconciliation 和多层 cleanup reconciliation 只在 3.5.8 明确非目标或本过程文档的历史记录中出现；`RecoveryDisposition` 只保留 3.10 持久化专用三结果语义。

旧 9.13—9.18、9.23、9.25 等记录中的 `MaterializationJob`、`ExecutionWorkspaceLifecycle`、cleanup attempt、generation、gate、claim、reconciliation、Stage2 等术语是当时讨论与审查轨迹，保留原文用于证明迭代过程。它们在 `SPEC_PROCESS.md` 中出现不构成当前规范对象、实现义务或 v1 验收条件。

### 10.5 证据边界

本轮范围收敛的前序步骤实际重写、审查并提交了 3.1—3.4，对应提交为 `856a8f0`、`0e6845c`、`2864a53`，并可引用 checkpoint `3640de6`；进入本步骤的 3.5 机械引用迁移时，3.1—3.4 才已经冻结，本步骤未再修改其正文。本节不宣称尚未发生的新冷启动审查、PR、实现验证或最终 SPEC／PLAN 批准，也不把此前历史讨论改写成当前规范；这些后续事项仍须按各自真实发生的证据另行记录，且不得为本步骤虚构新的提交哈希。

### 10.6 范围冷审记录

一个无背景代理仅依据课程源文档、`3640de6..414bc65` diff 和当前文档，对 3.1—3.5 的范围收敛结果执行了范围冷审。初审唯一发现是第 1 章正式引用的 `ExpectedWorktreeTree` 在重写后成为悬空名称；本轮采纳修复，将其明确为由 sealed HEAD tree 与 `RepositoryPolicySnapshot` 纯确定性计算、仅供 Snapshot 构建使用的未发布投影，没有恢复生产级持久对象、job、lifecycle 或恢复机制。

修复后，同一无背景代理复核该引用及其余封闭问题，结果为 `PASS`；该 `PASS` 只覆盖本次 3.1—3.5 范围，不替代未来完整 SPEC／PLAN 冷启动验收。

### 10.7 v1 审查准入、分类与退出规则

第 10 节当前规则对 v1 审查的效力优先于第 546 行所记录的历史“带条件批准”同步规则。第 546 行保持原文，仅作为当时协作过程的历史证据，不再被解释为允许审查自动扩张当前 v1 冻结范围。

“带条件批准”只授权对审查意见做技术分类，以及修复既有七项封闭验收维度内、受既有冻结合同约束的验收问题；它不自动创建新的冻结条件，也不授权把新对象、新机制、新字段、新状态或新记录升级为 v1 准入门槛。

每条阻断意见必须同时引用：七项封闭验收维度之一、受影响冻结合同、能够触发该合同失败的具体反例，以及不扩张验收范围的最小修复。任一项缺失时，该意见不得阻断 v1。无法映射到七项封闭验收维度及既有冻结合同的意见统一归类为过程标签 `NON_BLOCKING_ENHANCEMENT`；该标签只用于记录审查处置，不是运行时枚举、状态或功能合同，也不产生实现或验收义务。

只有发现直接合同矛盾、可证明无法实现，或具有具体攻击路径的严重安全漏洞时，才可以提出重开冻结内容。已映射问题全部关闭后必须判定通过，不得从修复中出现的新对象继续派生新的审查门槛。任何新增验收维度都必须由用户显式批准，审查者或执行代理不得自行增加。

## 11. 2026-07-15｜3.5 v1 范围重置与固定验收

### 11.1 两阶段授权与隔离

用户选择两阶段路线：Phase 1 先修复 baseline rejection 与审查准入规则，并停在人工检查点；用户明确批准 Phase 1 后，才授权开始 Phase 2。

Phase 2 从获批提交 `1759f0fcb96ee6f6e31fb2e2ee07beebaa832c67` 建立独立分支与 worktree：分支为 `codex/spec-v1-stage35-reset`，路径为 `D:\code\VesperCode\.worktrees\spec-v1-stage35-reset`。

### 11.2 v1 保留与下放边界

- 3.5 文件工具改为直接读取精确不可变 `SnapshotTree | CandidateTree`，不再依赖 Agent workspace publication、物化目录、attempt/cursor 状态机或临时 detail 正文。
- feedback continuation、supersession/invalidation、`UNTIL_SUPERSEDED`、summary/detail 双模式和持久 detail 已移出 v1；v1 只保留精确下一轮 `NEXT_TURN_ONLY` 有界摘要。
- v1 保留顺序单轮主循环、`ContextProjection`、单动作、八值动作及阶段矩阵、不可变树文件读取、reservation/Manifest、Accepted/Rejected 消费、失败/取消/中止关闭、Mock/真实同控制面和安全失败关闭。
- Stage2 generation、响应跨崩溃恢复、persistent block、successor reconciliation、handoff、完整迟到兼容矩阵、跨候选 feedback continuation 和资源级清理对账下放到未来增强；它们不再是 v1 冻结或验收的前置条件。

### 11.3 固定验收与审查边界

3.5 只以 3.5.9 固定编号 1—21 为冻结清单。任何新阻断意见仍受 10.7 的准入、分类和退出规则约束；无法映射者归类为过程标签 `NON_BLOCKING_ENHANCEMENT`，不得升级为新的运行时对象或冻结条件。

### 11.4 已发生的提交证据

- `2d49d76` — `Simplify agent turn contracts`
- `8043396` — `Polish simplified turn contracts`
- `3b5a4cb` — `Read agent files from immutable trees`
- `430db2d` — `Align file pagination token binding`
- `0e41050` — `Clarify immutable tool result consumption`
- `8414139` — `Reduce feedback to next-turn summaries`
- `62de758` — `Clarify feedback source derivation`

### 11.5 历史证据边界

旧第 9 节历史记录保留原样，用于证明当时的讨论、审查和迭代过程；其中出现的旧类型或机制不再构成当前规范依赖。本节不回写、重述或伪造旧历史。

## 12. 2026-07-15｜第三章合同交叉审阅修正

### 12.1 记录方法与证据边界

本节只追加记录本轮对 3.1—3.5 交叉审阅意见的处置，不回写第 1—11 节的历史原文。每项都按 10.7 的门禁规则记录门禁分类、能够触发既有合同失败的具体反例、不扩大 v1 范围的最小修复，以及采纳或收敛理由。过程标签 `NON_BLOCKING_ENHANCEMENT` 仍不构成运行时枚举或新增验收义务。

截至本节撰写时，`SPEC.md` 的修正已经分别形成 `3f0f9fc`、`ccc59b7`、`ef5a843` 和 `5c37431` 四个提交。本节只证明这些修正和处置判断已经发生，不宣称本轮规范符合性审查、文档质量审查、无背景范围冷审或完整第三章交叉审查已经通过，也不提前把 3.1—3.5 重新锁定。相关审查只有在实际执行后才能另行追加证据。

### 12.2 十四项门禁处置

#### 12.2.1 同 attempt replay 语义

- **门禁分类：** `CONTRACT_CONTRADICTION`。
- **具体反例：** 首次供应商调用已经发生但尚无权威 outcome 时，如果 `SAME_ATTEMPT_REPLAY` 被解释为“安全传输重放”，同一 attempt 可以再次请求供应商并产生第二次外部调用；这与单 attempt 单一权威结果及不得重复外部副作用的合同冲突。
- **最小修复：** `SAME_ATTEMPT_REPLAY` 只允许相同标识和相同规范输入返回首次已经形成的同一权威结果；尚无结果时分别走 checkpoint 前取消／内部中止、checkpoint 后 `LLMCallFailureRecord` 或收到响应后的 `TurnProcessingFailureRecord`，绝不重发适配器调用。
- **采纳与收敛理由：** 该修复直接关闭重复外部调用反例，并复用既有失败路线，不新增 replay 状态、传输恢复协议或跨进程状态机。

#### 12.2.2 `DisclosureGrant` 与 `DisclosureRecord` 边界

- **门禁分类：** `CONTRACT_CONTRADICTION`。
- **具体反例：** 如果运行级 grant 必须在批准时绑定尚未装配完成的最终请求摘要，批准依赖未来值而无法实现；如果实现忽略这一绑定，则实际发送的来源、体量或脱敏结果又可能与获批范围不一致。
- **最小修复：** `DisclosureGrant` 只绑定当前运行、供应商、端点、模型、允许来源范围与数据类别、脱敏规则、累计预算和有效期；每次既有 `DisclosureRecord` 逐次绑定最终请求摘要、实际来源、实际体量、脱敏结果和本次消费的 grant。
- **采纳与收敛理由：** 运行级授权和逐次发送事实各自只有一个权威对象，既可实现又可审计；v1 不为此新增 `DisclosureAttempt` 持久类型。

#### 12.2.3 授权前孤立 turn

- **门禁分类：** `PROVABLY_UNIMPLEMENTABLE`。
- **具体反例：** 控制面若先创建 `AgentTurn`、attempt、`AgentFeedbackConsumptionManifest` 或 reservations，再发现真实披露尚未授权并进入等待，用户永久不批准时会遗留没有合法调用、outcome 或消费终态的孤立 turn。
- **最小修复：** 授权前只计算非权威、非持久且无授权效力的 `ContextProjectionDraft`；授权不足只创建 `WaitContext`。授权满足后在新的可执行 phase-entry 全量重算，再原子创建最终投影、turn、attempt、适用 feedback records、`AgentFeedbackConsumptionManifest` 和 reservations。
- **采纳与收敛理由：** 修复给出可执行的对象创建顺序，并用既有等待对象表达授权不足，不新增半创建状态或孤立对象清理协议。

#### 12.2.4 三值 outcome 的响应处理缺口

- **门禁分类：** `CONTRACT_CONTRADICTION`。
- **具体反例：** 供应商响应已经收到，但控制面在规范化、解析器执行或权威发布时发生不可恢复内部故障；该事实既不是 Accepted、Rejected，也不是适配器调用失败，原三值联合无法诚实表示轮次终局。
- **最小修复：** 增加 `TurnProcessingFailureRecord`，把 `AgentTurnOutcome` 固定为四值联合；该结果形成 `TURN_ABORTED + STOPPED(INTERNAL_ERROR)`，不得产生动作或重发供应商调用。
- **采纳与收敛理由：** 只扩充既有结果联合的一个必要分支，闭合真实失败空间，避免把控制面故障伪装成模型拒绝或网络失败。

#### 12.2.5 feedback reservation 消费边界

- **门禁分类：** `CONTRACT_CONTRADICTION`。
- **具体反例：** 适配器请求已经发出且供应商可能已经看见 feedback，随后调用返回失败或响应处理失败；若 reservations 被关闭但标记为未消费，同一 feedback 可以在下一 turn 再次投影，形成已经使用却可重用的矛盾事实。
- **最小修复：** 在任何真实或 Mock 适配器调用前提交确定性 dispatch checkpoint，并立即原子、全量消费 `AgentFeedbackConsumptionManifest` 的 ACTIVE reservations；Accepted、Rejected、调用失败和响应处理失败都不退回。只有 checkpoint 前取消或内部中止才全量关闭且不消费。
- **采纳与收敛理由：** 消费边界落在控制面可确定的本地事实上，不依赖不可判定的网络到达状态，同时保持全量消费或全量关闭，不引入部分状态。

#### 12.2.6 物理删除承诺

- **门禁分类：** `CONTRACT_CONTRADICTION`。
- **具体反例：** 文件锁、权限故障或介质错误可能使执行根无法物理删除；如果运行终态仍承诺必然清除，实现只能伪造成功、永久阻塞，或在后续启动错误复用残留根。
- **最小修复：** 终态必须撤销运行、consumer、mount 和 allocator 的可达性及复用资格；边界可证明但删除失败时允许精确残留根永久 `QUARANTINED`，allocator 跨重启永久拒绝该 instance/root，且不承诺以后再次删除。
- **采纳与收敛理由：** 安全不变量收敛为可证明的不复用和隔离，而不是操作系统无法保证的物理删除；未解决的 3.10 恢复工件仍保留并继续阻断。

#### 12.2.7 `REPOSITORY_STATE` 与 `SNAPSHOT_TREE` 双权威

- **门禁分类：** `CONTRACT_CONTRADICTION`。
- **具体反例：** `REPOSITORY_STATE` 先把工作区判为 clean，文件随后在 `SNAPSHOT_TREE` 物化前改变；如果两阶段都对实际字节或 clean 状态作权威判断，就可能同时发布互相冲突的准入结果。
- **最小修复：** `REPOSITORY_STATE` 只负责 HEAD/index 可解析性、受支持结构与策略机制，并发布 `RepositoryPolicySnapshotRef`；`SNAPSHOT_TREE` 唯一判定 HEAD/index 清洁性、非忽略未跟踪状态、tracked 实际字节与 mode，并通过双观察区分初始不一致和观察期间变化。
- **采纳与收敛理由：** 每类事实只有一个权威阶段；既保留廉价结构门，又把实际工作区时间性检查集中在唯一 Snapshot 发布边界。

#### 12.2.8 Demo 重启生命周期

- **门禁分类：** `PROVABLY_UNIMPLEMENTABLE`。
- **具体反例：** 旧进程退出后，Demo 运行仍持久显示非终态，但新进程既没有旧会话令牌和内存资源，也没有生产级接管机制；继续运行或恢复该会话都无法实现。
- **最小修复：** 新进程启动时把旧进程拥有的非终态 Demo 运行原子终止，形成 `error_code = DEMO_SESSION_INVALIDATED`、`StopReason = INTERNAL_ERROR` 和完整 `StopRecord`。
- **采纳与收敛理由：** 该路线对用户可见、确定且可离线测试，不引入 generation、takeover、分布式配额或 Demo 恢复协议。

#### 12.2.9 `error_code` 与 `StopReason` 混用

- **门禁分类：** `CONTRACT_CONTRADICTION`。
- **具体反例：** 同一失败在一处把 `WORKSPACE_CHANGED`、`BUDGET_EXHAUSTED` 或 `NO_PROGRESS` 当细分错误码，在另一处又把它当停止原因；调用方无法同时满足错误信封和封闭 `StopReason` 联合。
- **最小修复：** 在 3.2.6 固定带适用上下文的稳定 `error_code → StopReason` 映射，修正第 1、2 章全部混用；保留既有 `StopReason` 集合，不新增同名第二套状态。
- **采纳与收敛理由：** 细分诊断与生命周期原因重新分层，外部接口可机械验证，并与已冻结的状态空间隔离原则一致。

#### 12.2.10 模型停止动作

- **门禁分类：** `PROVABLY_UNIMPLEMENTABLE`。
- **具体反例：** 如果 `ProposeStopAction` 能由模型输出，模型就可以绕过预算、无进展、策略和成功验证等确定性控制面谓词；如果它不能导致停止，则该动作又没有可观察的合法完成处置。
- **最小修复：** 从 v1 `AgentAction` 和阶段矩阵删除 `ProposeStopAction`，动作联合固定为七值；运行停止只由 Harness 控制面的既有确定性谓词触发。
- **采纳与收敛理由：** 修复恢复“模型无生命周期权力”的单一所有权，不建立建议停止与正式停止之间的第二套审批或反馈协议。

#### 12.2.11 3.1.2 实现层次

- **门禁分类：** `NON_BLOCKING_ENHANCEMENT`。
- **具体反例：** 若把 3.1.2 的原子性措辞解释为必须在功能规约中列出数据库字段、CAS revision、摘要 DAG 和多对象事务拓扑，尚未进入架构与 PLAN 阶段就会产生无法由用户故事直接验收的实现前置条件。
- **最小修复：** 明确 3.1.2 只冻结语义输入、权威输出、绑定、原子可观察边界和稳定错误；存储布局与事务实现下放到架构、数据模型和 `PLAN.md`。
- **采纳与收敛理由：** 该意见不构成阻断，但澄清能防止后续审查重新扩大 v1；没有增加运行时对象或验收维度。

#### 12.2.12 UTF-8/BOM 支持范围

- **门禁分类：** `NON_BLOCKING_ENHANCEMENT`。
- **具体反例：** “支持矩阵稍后列明编码”允许一个实现接受 UTF-16 或本地代码页、另一个实现拒绝；BOM 是否参与摘要和行列又会改变相同文件的工具结果与补丁字节。
- **最小修复：** 冻结 `TextContentProfile = UTF8 | UTF8_BOM`；BOM 计入原始字节长度和摘要，在逻辑文本投影前移除，后续补丁序列化恢复相同画像，其他语义文本编码拒绝。
- **采纳与收敛理由：** 这是对既有受支持文本范围的确定性收敛，不是新增编码能力；它让文件读取、摘要、分页和补丁测试具有唯一结果。

#### 12.2.13 `CONFIG_SNAPSHOT` 读取目标仓库

- **门禁分类：** `CONCRETE_SECURITY_PATH`。
- **具体反例：** 如果 `CONFIG_SNAPSHOT` 在敏感路径检查和 `SnapshotTree` 发布前直接打开目标仓库的 `pyproject.toml` 或工具配置，恶意仓库可以通过该前置读取绕过快照完整性、披露来源和双观察边界，并制造 TOCTOU 输入。
- **最小修复：** `CONFIG_SNAPSHOT` 只能读取目标仓库外的 VesperCode 控制面配置；仓库内 pytest、Ruff、Mypy、依赖和项目入口配置只能在 Snapshot 发布后，由 `PROJECT_PROFILE` 从精确不可变快照读取。
- **采纳与收敛理由：** 该最小切分直接关闭具体的预快照仓库读取路径，同时复用现有 `SnapshotTree` 和 `PROJECT_PROFILE`，不新增配置恢复或第二套仓库扫描机制。

#### 12.2.14 3.4 与 3.10 恢复冲突

- **门禁分类：** `CONTRACT_CONTRADICTION`。
- **具体反例：** 3.4 若把所有工件故障都规定为无恢复停止，或允许用户“明确放弃”后清除，便可能删除 3.10 权威持久化事务恢复所需日志与备份，同时解除本应继续存在的同工作区阻断。
- **最小修复：** 把 3.4 的无恢复安全失败关闭限定为 Snapshot、执行副本和普通 consumer；3.10 保持权威持久化恢复的唯一例外，并删除用户取消或声明放弃即可清除未解决恢复工件的路线。
- **采纳与收敛理由：** 修复消除跨章节冲突并保住持久化安全承诺，同时没有把普通 turn、披露、工具或清理失败扩张为通用恢复状态机。

### 12.3 本轮收敛结果与未完成边界

十四项处置均映射回既有七项封闭验收维度或固定清单，没有新增 `RunStatus`、`WaitKind`、`StopReason`、generation、takeover、通用 reconciliation、persistent block 或跨进程供应商重发机制。`AgentAction` 收敛为七值，`AgentTurnOutcome` 闭合为四值，披露授权与逐次披露事实分离，dispatch checkpoint 成为唯一 feedback 消费边界，仓库结构门与实际 Snapshot 权威分离，恢复只保留 3.10 的既有专用边界。

本轮下一项规格任务仍是 3.6 `CandidateRevision`、恢复修订与 `FinalDiff`。在本轮只读审查实际通过前，3.1—3.5 不能重新锁定；即使之后重新锁定，完整第三章仍须等待 3.6—3.12 完成并执行全章交叉审查。课程 `PLAN.md`、实现代码、最终冷启动实现试验和相关审查日志均不在本步骤中创建或提前记录。

### 12.4 `a125dfe` 后审查发现与本轮最小修复

- `bd50d82` 闭合了正式路线 3.3.7 的启动重启窗口；随后只读审查发现 3.3.14 Demo 启动失效没有同构闭合 Admission、turn 与反馈消费对象。
- `a125dfe` 完成了 Demo 路线的同构修复。固定 `a125dfe` 后，规范符合性审查返回 `PASS`；该结论只覆盖当时的规范符合性检查，不代表后续质量门禁已经通过。
- 文档质量审查随后发现活动 `WaitContext` 未随两条启动终止路线闭合、反馈消费 `Manifest` 类型未写全、3.5.9 使用提前锁定措辞，以及过程证据和交接冷启动阅读范围仍有缺口。无背景冷审另发现创建前 `UNSUPPORTED_FILESYSTEM_OBJECT` 尚无 `RunState`，却同时要求 `StopReason` 的矛盾。
- 因此固定 `a125dfe` 后的总体状态仍是 `NEEDS_CHANGES`。本提交只修复上述缺口，不新增持久类型、状态机、恢复路线或实现代码；修改完成后仍须对新的提交 SHA 重新执行规范、文档质量与无背景冷审，不在本节记录最终 `PASS`，也不声称完整第三章已经锁定。

### 12.5 固定 `83746d7` 后的最终审查与重新锁定

本轮被审查内容最终固定为 `83746d7599ed0f09e10ad15b2e6215378a226cb4`（`83746d7`），无背景累计冷审范围为 `cf720407af69aaac235b2bb0f7923fecd0544c68..83746d7599ed0f09e10ad15b2e6215378a226cb4`（`cf720407..83746d7`）。针对该固定内容，三项最终只读审查均已实际完成：

- `/root/review_fix_spec_review`：`✅ Spec compliant`；
- `/root/review_fix_doc_quality`：无 Critical、Important 或 Minor 问题，结论为 `PASS / Ready to proceed: Yes`；
- `/root/cold_review_83746d7`：累计范围冷审 `PASS`，没有符合五字段准入格式的阻断项，置信度高。

这些结论关闭了本轮 3.1—3.5 的阻断项，因此只把 3.1—3.5 重新锁定。完整第三章仍未锁定：3.6—3.12 尚未完成，完成后仍须执行全章交叉审查。课程权威 `PLAN.md` 尚未批准或创建，最终冷启动实现试验尚未执行，实现阶段也没有开始。

本节以及对应 `AGENT_LOG.md` 的证据记录发生在固定内容 SHA `83746d7` 之后，原无背景冷审不覆盖承载这些追加证据的后续提交。该后续证据提交只需接受窄范围真实性与格式复核；本节不声称该窄范围复核已经发生，也不把它解释为完整第三章审查或实现准入。

## 13. 2026-07-16 第三章 3.1—3.5 二次交叉审阅

### 13.1 审阅范围、RED 基线与历史证据边界

本节只追加记录固定 83746d7 后又发现的 3.1—3.5 合同问题、最小修复和执行前方案审阅，不回写或改写第 1—12 节。第 12.5 节记录的三项审查结论仍是当时固定内容的真实历史；本轮新增发现发生在其后，因此后续合同修订覆盖旧结论的当前效力，但不删除、伪造或倒签旧审查证据。

修改前按当前文档扫描口径执行了三组 RED：

1. SPEC.md 与 TASK_HANDOFF.md 的旧负向措辞扫描在 TASK_HANDOFF.md 命中三处：唯一的 21 项固定验收清单、每次实际发送、3.5 的细化门禁只来自 3.5.9；SPEC.md 为零命中。
2. 新合同正向词在 SPEC.md 已出现权威生命周期转换矩阵、PROCESS_RESTARTED_DURING_RUN、FormalValidationResult、ConfirmReproductionAction、固定最低验收清单、side_effect_status、LLM_ADAPTER_CALL_FAILED、完成真实适配器调用前调度提交和恢复阻塞；TASK_HANDOFF.md 只出现 PROCESS_RESTARTED_DURING_RUN，其他当前合同尚未同步。
3. TASK_HANDOFF.md 对不新增 3.5.10、初始 CandidateRevision、首个 RepairTurnSubject、局部锁定、3.9 的 DisclosureGrant 与披露预算账本、3.12 的 DisclosureRecord 展示边界，以及适配器调用与交付状态未知均为零命中。

修改前两份目标文件均为无 BOM 的 UTF-8 且只有 CRLF 行尾：SPEC_PROCESS.md 为 114810 字节、1041 个 CRLF，TASK_HANDOFF.md 为 32099 字节、593 个 CRLF。该基线用于检查本轮只追加、局部同步和无整文件行尾改写。

本轮六项意见中，第 5 项是 NON_BLOCKING_ENHANCEMENT，不重开冻结；其余五项满足既有阻断准入格式并重开 3.1—3.5 的相关冻结内容。以下每项均显式记录 classification、acceptance_dimension、affected_contract、可执行反例、最小修复和处置理由。

### 13.2 六项门禁处置

#### 13.2.1 正式进程重启缺少生命周期规范来源

- **classification：** CONTRACT_CONTRADICTION。
- **acceptance_dimension：** 3.2 生命周期唯一来源／3.2.6 稳定映射／3.3.16 第 5 项。
- **affected_contract：** 3.2.7 声称是生命周期转换的唯一规范来源，但当时没有列出正式运行的进程重启终止；3.3.7 和 3.3.16 第 5 项又要求该终止发生。
- **可执行反例：** 旧正式运行停在 RUNNING(AGENT_LOOP)，新进程取得工作区锁后必须形成 PROCESS_RESTARTED_DURING_RUN、INTERNAL_ERROR 和完整 StopRecord；如果 3.2.7 没有对应矩阵行且 3.2.6 没有稳定映射，实现既无法合法转换，也无法满足“唯一规范来源”。
- **最小修复：** 在 3.2.6 增加 PROCESS_RESTARTED_DURING_RUN → INTERNAL_ERROR 稳定映射；把 3.2.7 明确命名为权威生命周期转换矩阵，增加覆盖七项非持久化非终态的正式重启行，并引用 3.3.7 的对象级闭合细节。
- **采纳／澄清理由：** 采纳。修复只补齐既有正式启动终止的规范入口和映射，不新增 RunStatus、RunPhase、StopReason 或恢复状态。

#### 13.2.2 真实调用与披露记录／预算缺少持久提交点

- **classification：** PROVABLY_UNIMPLEMENTABLE。
- **acceptance_dimension：** 第 1 章披露承诺／US-05／3.1.3／3.2.3／3.5.3／3.5.7。
- **affected_contract：** 既有文字要求按真实发送记录披露事实和预算，却没有定义在外部调用之前能够持久证明授权、预算和 feedback 消费的提交点。
- **可执行反例：** adapter 已收到控制流或下游请求后进程立即崩溃；如果 DisclosureRecord、披露预算和 feedback 消费尚未提交，新进程既不能证明这些事实，也不能在不重复外部副作用的前提下安全补写或重发。
- **最小修复：** 对真实路线，在尝试调用适配器前的 dispatch checkpoint 以同一 pre-dispatch commit 全有或全无地重验 DisclosureGrant、消费披露预算、创建并绑定 DisclosureRecord，以及消费全部 feedback reservations；提交成功后才允许尝试真实调用。DisclosureRecord 只证明授权和真实适配器调用前调度提交，不证明适配器实际被调用或供应商已收到、处理、返回。Mock 路线只豁免 DisclosureRecord 与真实披露预算，仍经过同一 checkpoint 和 feedback 消费。
- **采纳／澄清理由：** 采纳并收敛到既有 dispatch checkpoint；不新增 DisclosureAttempt、外部送达确认、对账或供应商恢复协议。

#### 13.2.3 LLM 调用失败没有稳定后续路线

- **classification：** CONTRACT_CONTRADICTION。
- **acceptance_dimension：** 3.1.2／3.5.1／3.5.4／3.5.8。
- **affected_contract：** LLMCallFailureRecord 已表示适配器终态失败，但未冻结对应完成类别、后续处置、错误码和运行终态。
- **可执行反例：** 一个实现把 LLMCallFailureRecord 解释为可以 CREATE_NEXT_TURN，另一个实现立即停止；两者会对同一不确定下游效果产生相反的重发行为，且都能声称符合旧文字。
- **最小修复：** 固定 LLM_ADAPTER_CALL_FAILED、side_effect_status = UNKNOWN、LLM_CALL_FAILED + RUN_STOPPED 和 STOPPED(EXECUTION_TERMINATED)，retry_disposition 为 NEW_RUN_REQUIRED，当前运行不得重试或重发；在 3.5.8 封闭最小错误路由表。
- **采纳／澄清理由：** 采纳。只为既有 LLMCallFailureRecord 选择唯一安全后续，不增加 attempt 状态机、恢复队列或供应商对账。

#### 13.2.4 三类 UI 与 RECOVERY_REQUIRED 非终态冲突

- **classification：** CONTRACT_CONTRADICTION。
- **acceptance_dimension：** US-08／2.7／3.2.1／3.2.9。
- **affected_contract：** 旧 UI 只允许正在执行、正在等待用户和已经停止三类展示，但 RECOVERY_REQUIRED 既不是普通执行或等待，也尚未形成 SUCCEEDED 或 STOPPED。
- **可执行反例：** RecoveryDisposition = UNRESOLVED 时运行必须保持 RECOVERY_REQUIRED；UI 无法合法把它归入等待用户或已结束，把它归入执行中又会掩盖同工作区被恢复门阻断的事实。
- **最小修复：** 用户可见状态固定为执行中、等待用户、恢复阻塞、已结束四类；RECOVERY_REQUIRED 映射恢复阻塞且明确为非终态。
- **采纳／澄清理由：** 采纳。只是把既有 RunStatus 联合准确投影到 UI，不新增生命周期状态。

#### 13.2.5 实现技术非目标可能被误读为排除原子验收

- **classification：** NON_BLOCKING_ENHANCEMENT。
- **acceptance_dimension：** 3.5.1 范围／3.5.7 可观察原子性。
- **affected_contract：** 3.5 排除数据库事务拓扑、WAL/outbox 等实现技术，可能被审阅者误读为连全有或全无、单一胜出等可观察合同也不验收。
- **可执行反例：** 审阅者据“事务拓扑不属于功能规约”接受一个会部分创建 turn、部分消费 feedback 或在调用后才补写 checkpoint 的实现，从而放过可观察的不一致。
- **最小修复：** 明确不验收具体实现技术，但继续验收权威结果全有或全无、单一终态胜出、无部分可见、消费不可回退，以及真实调用前 checkpoint 的可观察顺序。
- **采纳／澄清理由：** 该意见不是阻断，只作澄清；它没有新增对象、字段、状态、机制或验收维度。

#### 13.2.6 “完整且唯一”清单排除了未重复规范

- **classification：** CONTRACT_CONTRADICTION。
- **acceptance_dimension：** 3.5.1—3.5.8 的 MUST／MUST NOT 合同与 3.5.9 范围。
- **affected_contract：** 把 3.5.9 称为完整且唯一的验收清单，会把 3.5.1—3.5.8 中未逐项复写的规范性合同排除在验收之外。
- **可执行反例：** 实现持久化完整原始 LLM 响应，直接违反 3.5.1 的数据最小化边界；若 1—21 项没有完整重复这条禁令，旧“唯一清单”措辞会让该违反无法成为验收失败。
- **最小修复：** 3.5.9 改为固定最低验收清单和最低必测集合；3.5.1—3.5.8 的其他规范性合同继续有效，清单不得被解释为排除未逐项重复的要求。
- **采纳／澄清理由：** 采纳。该修复只纠正验收范围量词，不增加第 22 项、不新增 3.5.10，也不创造运行时机制。

### 13.3 四项 3.5 收口与 3.6 下游门禁

本轮涉及 3.5 的四项收口是：LLM 适配器失败的稳定终止路线、可观察原子性边界、固定最低验收清单，以及真实调用前记录／预算／feedback 的 pre-dispatch commit。四项都只封闭既有对象和顺序，不增加新机制。3.5 写作结构仍止于 3.5.9，不新增 3.5.10；这四项通过后续审查后可以局部锁定，但该局部锁定不等于首轮 RepairTurnSubject 的端到端闭环已经验证。

初始 CandidateRevision 是 3.6 的 PROVABLY_UNIMPLEMENTABLE 下游门禁，不是第七项 3.5 审阅意见，也不是第五项 3.5 阻断修复；以下以五字段完整记录该 3.6 阻断门禁：

- **classification：** PROVABLY_UNIMPLEMENTABLE。
- **acceptance_dimension：** 七项封闭验收维度第 1 项“最小功能闭环可运行”与第 2 项“权威输入、结果与持久化边界可判定”；具体落点为 3.5.2 `RepairTurnSubject` 与未来 3.6 `CandidateRevision` 的端到端绑定。
- **affected_contract：** ExistingFailure 和 NaturalLanguageDefect 两类 repair base 进入 AGENT_LOOP 后，3.5 的 RepairTurnSubject 必须绑定 current_candidate_revision_ref 与 CandidateTree；当前 3.6 尚未定义首个候选的发布来源和失败关闭。
- **可执行反例：** 系统已经进入首个 AGENT_LOOP phase-entry，却没有任何 CandidateRevision 或 CandidateTree；此时无法创建合法的首个 RepairTurnSubject，也不能执行读取、补丁或正式验证。
- **3.6 最小修复：** 两类 repair base 在进入可创建 turn 的 AGENT_LOOP 前，都必须全有或全无地发布唯一、非空且非占位的初始 CandidateRevision 与 CandidateTree；并发发布必须单一胜出，发布失败不得进入能够创建首个 turn 的 AGENT_LOOP。

因此下一规格任务仍是 3.6。它的固定验收问题必须覆盖两类 repair base、初始候选全有或全无、并发单一胜出、禁止空值或占位引用，以及发布失败不得进入可创建 turn 的 AGENT_LOOP。

### 13.4 执行前方案审阅的六项修正

#### 13.4.1 3.2.11 编号

- **当前反例：** 若把新增正式重启验证点误记为 3.2.10，读者会落到生命周期流程示例而不是可确定性验证点，交接检查也无法定位机械测试。
- **具体修正：** 转换合同保留在 3.2.7；对应机械验证写入 3.2.11 第 12 项，所有当前引用均指向 3.2.11。
- **不新增机制理由：** 只修正章节编号和交叉引用，运行时行为不变。

#### 13.4.2 矩阵名称、七态与恢复排除

- **当前反例：** “正常转换矩阵”或未封闭的“任意非终态”会让实现把 RUNNING(PERSISTENCE) 或 RECOVERY_REQUIRED 当作普通重启终止，绕过 3.10 的持久化恢复。
- **具体修正：** 统一名称为权威生命周期转换矩阵；正式 PROCESS_RESTART_DETECTED 行只覆盖 CREATED、WAITING_USER、RUNNING(PREFLIGHT)、RUNNING(BASELINE)、RUNNING(REPRODUCTION)、RUNNING(AGENT_LOOP) 和 RUNNING(FORMAL_VALIDATION) 七项，明确排除 RUNNING(PERSISTENCE) 与 RECOVERY_REQUIRED。
- **不新增机制理由：** 只是封闭既有转换的源状态集合，并保持 3.2.9／3.10 的恢复所有权。

#### 13.4.3 DisclosureRecord 的证明范围

- **当前反例：** 如果 UI 或审计把 DisclosureRecord 显示为“已发送”或“供应商已收到”，进程在 pre-dispatch commit 后、适配器调用前退出时就会展示未经证明的外部事实。
- **具体修正：** DisclosureRecord 只证明授权和 pre-dispatch commit 已完成；适配器是否实际调用、供应商是否收到、处理或返回必须保持未知，除非另有可验证执行事实。
- **不新增机制理由：** 收窄既有记录语义，不建立送达回执或新记录类型。

#### 13.4.4 错误表的 side_effect_status

- **当前反例：** 只写 UNKNOWN 而不写判定对象时，调用方可能把“Harness 已进入 adapter 方法”误当作供应商下游效果已 COMMITTED，也可能把已发生的模型响应处理误当作 NONE。
- **具体修正：** 3.5.8 错误表逐行冻结场景、稳定 error_code、副作用判定对象、side_effect_status、完成处置、retry_disposition 和运行路线；LLM_ADAPTER_CALL_FAILED 的判定对象是该调用封装的下游请求效果。
- **不新增机制理由：** 只把既有统一错误信封字段的解释绑定到具体操作。

#### 13.4.5 FormalValidationResult 与反馈职责

- **当前反例：** 若 3.10 在 FORMAL_VALIDATION_FAILED 转换时直接形成结构化失败反馈，此时尚无下一 RepairTurnSubject，反馈会没有合法目标，或与 3.5 创建 turn 时再次生成的反馈重复。
- **具体修正：** 仅在 `FORMAL_VALIDATION_FAILED → AGENT_LOOP` 的下一轮反馈所有权边界内，3.10 形成并封存 `FormalValidationResult`，3.5 在原子创建下一 `AgentTurn` 时从该结果确定性生成并绑定有界下一轮反馈。3.10 仍拥有正式验证、持久化事务／恢复领域证据、事务事实、`RecoveryDisposition` 与守卫；所有 `RunState` 目标状态映射均由 3.2 拥有。
- **不新增机制理由：** 使用既有正式验证结果、反馈和 turn 创建边界，只消除双重所有权。

#### 13.4.6 US-06 与 US-07 所有权

- **当前反例：** 若 US-06 同时拥有所有高风险动作批准和最终持久化批准，ConfirmReproductionAction 与 PersistVerifiedDiffAction 会被通用批准语义合并，导致一次性复现批准能够被误用于权威写入。
- **具体修正：** US-06 只覆盖 ConfirmReproductionAction 的一次性批准和通用 DENY；最终持久化批准及其绑定由 US-07 负责。
- **不新增机制理由：** 只是把现有两个批准用途分回既有用户故事，不增加 WaitKind 或动作类型。

#### 13.4.7 事件级生命周期权威分工

- **当前反例：** 若把 3.2.7 无范围地称为全部生命周期转换的唯一来源，取消与跨阶段终止的通用规则会与 3.2.8 双写，`RecoveryDisposition` 目标状态映射会与 3.2.9 双写；若只查 3.2.7，又会漏掉合法取消或持久化恢复。
- **具体修正：** 所有 `RunState` 目标状态映射仍只由 3.2 拥有。3.2.7 只拥有它明确列出的转换行；3.2.8 拥有取消与跨阶段终止的通用规则和守卫，3.2.7 表内 `CANCEL_ACCEPTED` 行只承载相应状态转换，不得重实现 3.2.8 规则；3.2.9 独占 `RecoveryDisposition` 目标状态映射，3.2.7 不得复制该恢复映射。
- **不新增机制理由：** 只明确既有三节的事件级权威边界，不增加状态、事件、守卫或恢复处置。

### 13.5 当前结论与后续边界

第 12 节及更早章节全部原样保留，其旧结论是对应时间点和固定提交的过程证据；本轮五项阻断发现使相关冻结重新打开，第 5 项 NON_BLOCKING_ENHANCEMENT 不阻断。只有本轮合同修复接受新的只读审查并通过后，四项 3.5 收口才可局部锁定。

本轮没有增加 RunStatus、RunPhase、WaitKind、StopReason、AgentAction、generation、takeover、reconciliation、persistent block 或供应商送达协议。3.5 是唯一的组合 dispatch checkpoint 编排权威，拥有调用时点、最终绑定和 feedback reservations 消费。3.9 拥有权威披露子操作及其 `DisclosureGrant` 校验语义、披露预算账本、`DisclosureRecord` 领域／证明语义、发布键与幂等；该披露子操作只能全有或全无地加入 3.5 编排的同一提交，不得在 checkpoint 之外先行、独立或另行提交。3.5 不得重实现或放宽 3.9 的这些语义。3.12 后续只能把 `DisclosureRecord` 展示为“已完成调用前调度提交；适配器调用与交付状态未知”，不得无条件显示“已发送”或“供应商已收到”。本轮不编写 3.9 或 3.12 正文。

下一任务仍是 3.6 CandidateRevision、恢复修订与 FinalDiff，并必须先关闭初始 CandidateRevision／CandidateTree 的下游门禁。完整第三章仍未锁定，课程 PLAN.md 和实现阶段仍未获准开始。

## 14. PLAN readiness gate 与执行合同收口（2026-07-26）

### 14.1 触发与事实核对

外部审查建议在正式 Task 1 前增加 `M0：SPEC readiness gate`，并指出双 CI、List/Search continuation、运行期凭据清除和 PLAN 执行跟踪摘要四类风险。用户随后明确选择 `OD-01=A`（canonical List/Search cursor）与 `OD-02=B`（只排除枚举执行跟踪字段的 PLAN 语义摘要），撤回此前“执行 2”的指令，要求先不要开始实现，最后批准按该建议修改文档。

审查材料所称当前 SPEC 仍锁定旧 blob `5ff2086e131165e6954edbb4635c6d574625d867` 不符合本轮修改前的仓库事实：修改前正式 `SPEC.md` 的实际 `git hash-object` 为 `b11a55bb0ed1d79a2f7c654ee51a238ee12841d5`，原 `PLAN.md` 中也不存在 `5ff2086e...`。本轮拒绝把该旧值描述成当前事实，但采纳“所有身份必须运行时计算、不得在计划正文预埋历史 hash”的原则。

### 14.2 已采纳的合同修改

1. `SPEC.md` §11.2 改为 M0 门禁：唯一解析正式 SPEC，运行时计算 SHA-256、`git hash-object --no-filters` 和当前 commit，对照课程/Harness/仓库规则，核对已知阻断项，并要求人工批准精确 SPEC 身份。失败返回 SPEC 修订/澄清，禁止冻结 PLAN、冷启动和 Task 1。
2. `SPEC.md` §4.2.2 增加独立 `ListFilesCursorV1`/`SearchTextCursorV1`、cursor-free query digest、visible-tree/query/位置/自身摘要绑定、严格 `truncated`/`next_cursor` 组合、`CONTINUATION_STALE`/`CONTINUATION_INVALID` 零部分结果及 1024-byte Search excerpt 上限。
3. `SPEC.md` §4.4.4 与 FR-CRED 增加每次真实调用前的 Windows Credential Manager backend probe 和 `get_for_call("OPENAI")`。该检查位于 Grant 消费、durable authorization record、turn/call 和网络之前；凭据缺失/清除或后端不安全时停止当前 Run、零副作用且不自动重试。
4. `SPEC.md` §5、§8—§10 增加 GitHub Actions 与 GitLab CI 双平台闭环。GitHub 每次 push/PR 运行 `unit-test`、`reference-image-build`、`demo-image-build` 且无发布凭据/发布动作；GitLab 保留四个精确 job，并独占受保护 tag 发布。
5. `PlanSemanticDigestV1` 使用 `VesperCode\0PLAN_SEMANTIC_CONTRACT_V1\0` 域，只在正式 Task 区域排除 `Status`、checkbox 状态和单行 `Completion evidence`。其他任意 PLAN 变化都要求重新语义批准和冷启动；完整 PLAN SHA-256 始终保留为证据快照身份。
6. `PLAN.md` 保留已按 writing-plans 重写的 38 个正式 Task 与 Task 1—3 技术门禁，同步 Task 11/16/17/25/27/31/32/35—37、DAG、waves、文件所有权、FR/NFR/AC 和测试/发布矩阵。此前 OD-01/OD-02 不再是开放实现选择。

### 14.3 当前内容地址与门禁状态

- 规划基线 commit：`f6aa9897ca8e9f3cab86143b880a306d96a252e1`。
- 当前正式 SPEC：`SPEC.md`。
- 当前 SPEC SHA-256：`2aa8f8cbc386693ca6288f97525b66a94a38ca3548444d07f4ba80dccd7ad4de`。
- 当前 SPEC Git blob：`ddc2aff270eb6041a86da479aa43185950fb0ce2`。
- 当前完整 PLAN SHA-256：`80217294c1531ad61b87f9af7d6b35d83fd43b73c0ced914232cd18e2b7040ff`。
- 当前 `PlanSemanticDigestV1`：`25a9d20436b70564bd770b4897d6c72b32b48927fe0ba5728faf3005b0c58405`。

上述值是修改后机械计算的候选身份，不是人工批准证据。M0 人工批准、PLAN 语义批准和异构 Agent 冷启动试作均未执行、未通过，也没有开始 Task 1 或任何实现。后续若 `SPEC.md` 或 PLAN 非跟踪字段发生变化，必须重算并废弃本节相应候选身份。

### 14.4 机械自审结果

`PLAN.md` 含 38 个连续正式 Task、494 个 checkbox、22 个 dependency waves，其中声明 11 个 parallel waves；Task 1—3 仍为三个串行 GO/NO-GO 技术门禁。FR 9/9、NFR 6/6、AC 31/31 均有覆盖矩阵行；placeholder 扫描无命中。此次只修改规格、计划与过程证据，没有创建实现代码、测试、CI 文件、worktree、branch、commit、PR、tag 或发布/部署工件。

## 15. Task 1—3 可复现 gate bootstrap 收口（2026-07-26）

### 15.1 触发、核对与技术判断

外部审查指出 Task 1—3 已要求执行 pytest、Ruff、Mypy、pytest marker、Docker 机器报告和稳定失败输入，但原 PLAN 直到 Task 4 才首次创建 `pyproject.toml`、`requirements/dev.lock`、正式 marker/config 和凭据扫描脚本；Task 2 的文件所有权也没有明确的 gate 报告器或指纹比较模块。用户先询问该建议是否成立，随后批准执行文档修改。

仓库核对确认核心阻断成立：原 Task 1 从第一个技术门禁就调用未锁定的 pytest/Ruff/Mypy，Task 2 要求完整机器报告和稳定失败输入，但只拥有 `probe.py`/`report.py`，Task 4 才首次创建正式项目配置。审查意见中“Task 1—3 完全缺少凭据扫描”的表述不准确，因为三个任务已有 filename-only PowerShell 扫描；本轮保留该扫描，不把它误报为缺失项。真正需要关闭的是 gate 工具链、marker/config、显式报告插件和稳定输入比较的可复现性。

### 15.2 采纳的最小合同

1. `SPEC.md` §11.2 与 AC-24 增加 gate bootstrap 门禁：Task 1 在首次 RED 前拥有 hash 锁定的 `requirements/gate.lock`、独立 pytest/Ruff/Mypy 配置和唯一 runner；Task 2/3 只消费同一身份，不依赖全局工具或 Task 4。
2. PLAN 预先分配 `requirements/gate.lock`、`gates/pytest.ini`、`gates/ruff.toml`、`gates/mypy.ini`、`scripts/run_gate_checks.py` 的单一职责和 Task 1 所有权。Task 1 GO 记录 Python、pytest、Ruff、Mypy 版本及全部 lock/config/runner SHA-256。
3. Task 2 独占 gate-only `pytest_reporter.py` 和 `failure_fingerprint_probe.py`。报告器必须显式加载且插件 autoload 关闭；探针只构造、规范化和比较 Task 19 所需的稳定 `CALL/FAIL` 输入，不得冒充正式 `PytestEvidenceV1`/`FailureFingerprintV1` 实现。
4. Task 2 的 GO 报告绑定 Task 1 工具链、reporter/probe 版本与 SHA-256、实际镜像和完整报告；Task 3 GO 重复验证同一 Task 1 身份。任何漂移、隐式加载、截断报告或不稳定输入均为 NO-GO。
5. Task 4 将已验证的版本、marker 和静态规则提升到 `pyproject.toml`/`requirements/dev.lock`，不是首次建立测试环境。任何有意差异必须记录并重新执行受影响的 Task 1—3；静默漂移失败关闭，gate 工件和 GO 证据保留到 Task 37。
6. 未在 PLAN 正文猜测时间敏感的具体 patch 版本。Task 1 必须形成包含全部直接/传递依赖精确版本与分发 hash 的完整 lock，并由 GO 报告和审查冻结；Task 2/3 禁止重新解析或升级。

### 15.3 同步范围

除 Task 1—4 外，本轮同步了 M0 known blockers、planned repository structure、DAG/直接依赖、waves、文件所有权、NFR-REL、AC-24/AC-25、Test Environment Matrix、Task 37 delivery verifier 和 Release Readiness Gate。正式 Task 数、Task 1—3 的最前顺序、依赖 waves 和 checkbox 数均不因本轮合同修订而改变。

### 15.4 当前候选身份与未完成门禁

- 规划基线 commit：`f6aa9897ca8e9f3cab86143b880a306d96a252e1`。
- 当前正式 SPEC：`SPEC.md`。
- 当前 SPEC SHA-256：`75794cdefc7801aa8620b22c529528efe2af06cf36ffc447e570a8eb3be3a7cd`。
- 当前 SPEC Git blob：`a688434c80ff63e1b39e30283ffed966e92b162b`。
- 当前完整 PLAN SHA-256：`71c61a1cdc8b043504b49c256d8553817de269e6f2d430793072b144b4556c20`。
- 当前 `PlanSemanticDigestV1`：`84103c09b55a65536fd5135bb51c29f2bfdcb6fa1620e44567661bf2fc64c6f3`。

这些值是本轮修改后的机械候选身份，不是 M0 或 PLAN 人工批准。M0、PLAN 语义批准和异构 Agent 冷启动试作仍未执行、未通过；Task 1 和所有实现仍被阻断。本轮没有安装依赖，没有创建任何 gate/实现/测试/CI 文件，没有创建 worktree、branch、commit、PR、tag、发布或部署。

### 15.5 机械自审结果

最终只读检查确认：38 个 Task 连续编号 1—38；494 个 checkbox；dependency 和 ownership 表均各有连续 1—38；22 个 waves 连续编号 0—21，表中多任务 waves 精确为 4、5、6、8、9、10、11、12、14、15、18，共 11 个；FR 9/9、NFR 6/6、AC 31/31；Task 1—3 区域没有裸 `python -m pytest|ruff|mypy` 命令；七个新增 gate 规划路径均已在目录/任务/所有权中出现；PLAN placeholder 扫描和四文档高置信凭据格式扫描均为零。

第一次 parallel-wave 校验用过窄的字面量 `Parallel:` 匹配，漏掉写为 `Parallel after ...:` 的 Wave 5/6 并触发断言；改为按 waves 表第二列的 `Tasks ...` 多任务单元格识别后，得到上述精确 11 个 waves。该失败属于校验脚本假阴性，没有据此修改 PLAN 拓扑。

`git diff --check -- SPEC.md SPEC_PROCESS.md AGENT_LOG.md` 退出 0；未跟踪 `PLAN.md` 的 `git diff --no-index --check -- NUL PLAN.md` 只因内容差异退出 1，均仅报告工作树未来 LF→CRLF warning，没有 whitespace error。最终工作区状态与本轮开始相比只在既定四文档内发生内容变化，没有新增实现工件。

## 16. Task 2 loopback registry 与 OCI digest 前置门禁收口（2026-07-26）

### 16.1 触发与决策

外部审查指出：SPEC §11.2 把 GHCR digest 交付列入第二项前置技术验证，但 Task 2 同时禁止 push，真实 GHCR RepoDigest、按 digest 重拉和发布验证又被放到 Task 36；本地 image ID 不能证明 GHCR 交付。核对后确认该阻断成立，同时发现“在不修改 SPEC 的情况下让 Task 2 真实推送 GHCR”会违反 §5.5/§8.4 的另一项硬合同：GHCR 凭据只能进入受保护 GitLab tag release job。

因此没有选择提前开放 GHCR 凭据。用户批准的最小方案是：Task 2 使用本机无凭据临时 registry 完成 OCI manifest 内容寻址和 registry round-trip；Task 36 仍是唯一真实 GHCR push/交付门禁。

### 16.2 冻结的最小合同

1. `ReferenceProfileManifestV1.docker_image_digest` 唯一表示固定单平台 OCI manifest 原始字节的 `sha256:<64 lowercase hex>`，本地 image ID、config digest、tag 和 index digest都不是该身份。
2. Task 2 固定 target platform、builder、media type、压缩和 attestation 参数，导出一个 OCI manifest；使用 digest-pinned registry image 在 `127.0.0.1` 的 OS-assigned 端口启动无凭据临时 registry。
3. Task 2 必须证明 `local_oci_manifest_digest == registry_repo_digest == digest_pull_repo_digest`，再生成 `ReferenceProfileManifestV1`，并要求其 `docker_image_digest` 等于上述值。
4. 为消除 digest cycle，最终 manifest 及任何包含其 digest/image digest 的文件不得进入所绑定镜像的 build context、层、config、annotation 或 attestation。镜像只能携带不引用最终 manifest 的工具/profile 版本证据。
5. 临时 registry 不读取 Docker Desktop credential store、不监听 LAN/公网、不推送外部 registry；成功、失败、超时、取消和异常路径均必须删除容器与数据。重拉后的检查容器仍使用 `--network none`。
6. Task 34 只复现 Task 2 已证明的 builder/registry/manifest 流程；任何 cycle 或 digest 差异都使原 Task 2 GO 无效并重新打开 Task 2/6，不能到 Task 34 才首次判断可行性。
7. GitHub Actions 和普通 GitLab CI 可以运行同一无凭据 loopback round-trip，但不得登录或推送外部 registry。Task 36 以受保护凭据推送 Task 2 冻结的同一 manifest/blobs，要求 Task 2、Task 34、wheel manifest、GHCR 和目标机 pull digest 全部一致。

### 16.3 同步范围与候选身份

本轮同步修改了 SPEC manifest 语义、release credential/CI 边界、AC-24/AC-30、验证矩阵和 §11.2；PLAN 同步 M0、Global Constraints、Task 2/34/35/36、Task 37、ownership、NFR、AC、Test Environment Matrix 和 Release Readiness Gate。没有新增 Task、wave 或 checkbox。

- 规划基线 commit：`f6aa9897ca8e9f3cab86143b880a306d96a252e1`。
- 当前正式 SPEC：`SPEC.md`。
- 当前 SPEC SHA-256：`80ccc86d9c06bdf7b4fed8673e2e6879942ca2cbc2b07c91bf1276b19a7447aa`。
- 当前 SPEC Git blob：`2cc522eeb2eb61e75ce96b6500ebbfdf8db18499`。
- 当前完整 PLAN SHA-256：`f713f5885482dd38ef66fa23998677a8cfc409d1784c1a0df50fdab12d5916a0`。
- 当前 `PlanSemanticDigestV1`：`f7ea14dfb0b8cc8c56a96e7f92d4f83aca58098d3ecedf910e18b8a09b9e457c`。

以上仍是机械候选身份，不是 M0、PLAN 人工批准或冷启动通过证据。本轮没有运行 Docker/registry、没有使用凭据、没有安装依赖、没有创建实现文件、worktree、branch、commit、PR、tag、release 或 deployment；正式实现继续被 M0、重新批准和冷启动门禁阻断。

### 16.4 机械自审结果

最终检查确认：38 个连续 Task、494 个 checkbox、38/38 dependency rows、38/38 ownership rows、22 个 waves 和既有 11 个 parallel waves均未改变；FR 9/9、NFR 6/6、AC 31/31。旧短语 `GHCR digest 交付` 和旧字段 `image_repo_digest` 均为零；Task 2 的三个 digest、零外部 push、清理和 manifest-output 字段齐全；Task 34 明确只复现；Task 35 明确 loopback-only/禁止外部 registry；Task 36 明确唯一真实 GHCR push。PLAN placeholder 和四文档高置信凭据格式扫描均为零。

第一次 self-reference 字面量检查因 PowerShell 将 Python 命令字符串中的 Markdown backtick 当作转义符而出现假阴性；直接读取文件并改用不含 backtick 的正则后，最终 manifest 排除、三方一致后生成和 GHCR 保留到 §8.4 三项均通过。该校验错误没有引起文档合同修改。

SPEC/PLAN 摘要和 Git blob 已重新计算并与 PLAN、过程记录和日志一致。tracked `git diff --check` 退出 0；未跟踪 PLAN 的 no-index check 仅因内容差异退出 1，均只有 LF→CRLF warning，没有 whitespace error。最终 `git status` 与本轮开始相比没有新增实现或外部工件。

## 17. 公网 Demo shared core 复用收口（2026-07-26）

### 17.1 触发、核对与技术判断

外部审查指出 SPEC §6.4 明确要求公网 Demo 经过 `shared action parser / policy / feedback core`，但原 Task 30 只依赖 Tasks 4–5、只消费 canonical/closed-schema 基础，并由 `DemoExecutor.advance` 自行推进场景；原 Task 32 只比较 formal trace 与 Demo labels 的语义对齐。用户要求先判断问题是否存在，随后批准执行不新增正式 Task 的最小修复。

仓库核对确认该阻断成立。标签和最终表现一致只能证明两个实现行为相似，不能证明公网 Demo 运行时调用 Task 13/17/24/25 的正式纯核心。原 Task 30 的依赖、接口、测试和并行 wave 都允许其在 PolicyEngine、action parser/dispatcher、feedback 和 stopping 完成前独立实现，因此与 SPEC §6.4 不一致。

### 17.2 采纳的最小合同

1. 保留 38 个正式 Task 和现有编号，不修改 `SPEC.md`。Task 30 的直接依赖改为 Tasks 4–5、13、17、24–25，并在 Task 25 后与 Task 29 并行；Task 32 在 Task 30 后与 Task 38 并行。
2. Task 30 新增 `demo/runner.py` 和 `tests/demo/test_shared_core_composition.py`。`DemoScenarioV1` 只保存固定 Mock responses、模拟结果 fixtures 和展示标签；`DemoExecutor` 只适配 Task 17 `ToolPortsV1` 并返回固定模拟结果；`DemoScenarioRunner` 按固定顺序调用正式 `ActionParser.parse`、`bind_action`、`PolicyEngine.evaluate`、`ToolDispatcher.dispatch`、Task 24 feedback functions 和 `StopEvaluator.evaluate`。
3. Demo 只把 `DemoExecutor`、内存 session store 和 renderer 注册为能力适配器。内存 session store 仅为五分钟会话实现 Task 24 feedback repository port，不写磁盘或数据库；Demo 不构造正式 `AgentLoopEngine`、Run repository、Approval、Grant、AuditEvent、恢复或持久化生命周期。
4. Task 30 的 RED/GREEN 和 review gate 改为运行时 call-recording proof：必须证明 shared core 真实被调用、只有 Demo tool ports 执行、所有文件/WinCred/Docker/OpenAI/SQLite/recovery/persistence adapters 的调用计数为零。类名、源码字符串或 label alignment 不能作为复用证据。
5. Task 32 新增 `test_shared_core_reuse.py`，同时运行 formal harness 和 Task 30 headless runner，比较实际实现引用与调用序列；label alignment 只保留为独立展示一致性证据，Demo 与正式状态/执行端口仍不互相转换。
6. Task 34 的 curated Demo image 合同同步为包含 Task 30 `DEMO_SHARED_CORE_MODULES_V1` 和必要 canonical/contract import closure，同时继续排除 file action implementations、WinCred/OpenAI/Docker/recovery/persistence adapters 和正式 wheel。镜像检查必须同时证明 shared pure core 存在与被禁止适配器不存在。
7. DAG、直接依赖、waves、文件 ownership、FR-UI、NFR-REL、AC-02/AC-05/AC-09/AC-17 和 Public Mock Demo smoke 证据同步更新。依赖 waves 仍为 22 个，其中并行 implementation waves 从 11 个变为 12 个。

### 17.3 当前候选身份与未完成门禁

- 规划基线 commit：`f6aa9897ca8e9f3cab86143b880a306d96a252e1`。
- 正式 SPEC 路径：`SPEC.md`。
- SPEC SHA-256：`80ccc86d9c06bdf7b4fed8673e2e6879942ca2cbc2b07c91bf1276b19a7447aa`。
- SPEC Git blob：`2cc522eeb2eb61e75ce96b6500ebbfdf8db18499`。
- 完整 PLAN SHA-256：`19ce93606c77c2b36b40ef3301a662f77113e3b945b0949b3a604cbd54fcc98f`。
- `PlanSemanticDigestV1`：`786b87767842824fae6ffca0f504de69c360bf107a3b545c4327424d2d8cbed6`。

SPEC 身份未因本轮变化；旧 PLAN SHA-256 `f713f5885482dd38ef66fa23998677a8cfc409d1784c1a0df50fdab12d5916a0` 和旧 `PlanSemanticDigestV1` `f7ea14dfb0b8cc8c56a96e7f92d4f83aca58098d3ecedf910e18b8a09b9e457c` 已被语义修改废弃。新值只是机械候选身份，不是人工批准证据。M0 人工批准、PLAN 语义批准和异构 Agent 冷启动试作仍未执行；正式实现继续被阻断。

### 17.4 机械自审

修改后共有 38 个连续正式 Task、494 个步骤 checkbox、38/38 direct dependency rows、38/38 ownership rows、22 个 waves 和 12 个 parallel waves（4、5、6、8、9、10、11、12、14、15、16、18）。`DemoExecutor.advance`、Task 30 仅依赖 Tasks 4–5、`T5 --> T30`、旧 Waves 4/15 分配以及 label-only reuse 表述均为 0；新增 runner、shared-core tests、Task 25 → Task 30 DAG edge、Task 30 direct dependencies 和 curated image assertions 均存在。PLAN placeholder 和四文档高置信凭据格式扫描均为 0；tracked `git diff --check` 退出 0，未跟踪 PLAN 的 no-index check 仅因内容差异退出 1并产生一条 LF→CRLF warning，whitespace error 为 0。三份本轮修改文档均为严格 UTF-8、无 BOM、无裸 CR、无尾空格。本轮未创建实现代码、测试、镜像、CI、branch、worktree、commit、PR、发布或部署工件。

## 18. PLAN 执行合同与证据闭环收口（2026-08-01—2026-08-02）

### 18.1 触发与范围

用户带回的 PLAN 审查指出 T04.1 Python mismatch fixture、T37.2 post-merge delivery、evidence commit SHA、Atomic verification 绑定及少量 authoring wording 存在可执行性或内部一致性缺口。Codex 对照 PLAN、AGENT_LOG.md 和现有课程流程合同逐项核对后，用户授权执行最小修复。

本轮 PLAN 修复只修改 `PLAN.md` 和 `AGENT_LOG.md`，不新增产品任务、Work Package、实现代码、验证器、依赖或发布流程。逐次执行记录保留在 `AGENT_LOG.md` 的对应条目中，本节只记录规划决策和结果。

### 18.2 采纳的最小修复

| 审查主题 | 决策 | PLAN 修订 |
| --- | --- | --- |
| T04.1 Python mismatch | 采纳 | 使用完整、自洽、digest-valid 的 synthetic terminal GO fixture；loader 校验后再进入 exact Python patch mismatch 分支，且优先于 lock 检查和环境创建。 |
| T37.2 delivery | 采纳 | 增加非任务门禁 `FINAL_DELIVERY_POST_MERGE_V1`，区分 `source_commit` 与 `delivery_head`，并将最终 CI、delivery verifier 和 reflection verifier 放到 WP37 merge 之后。 |
| evidence commit SHA | 采纳 | evidence commit 只记录既有 implementation SHA；自身 evidence-commit SHA 在提交后由 Git 历史机械派生，不嵌入自身内容。 |
| PEX-06 Atomic binding | 采纳 | 每条非 `Expected` 命令必须唯一绑定到逐字 checkbox、明确 profile command 或中央 derived action；32 条缺失命令补入 23 个已有 session task 的 canonical checkbox。 |
| authoring/order wording | 采纳 | 增加 `superpowers:writing-plans` provenance，并将 WP05 registry 顺序改为 `5.A, 5.D, 5.B, 5.C, 5.E`。 |
| evidence workflow 残留措辞 | 采纳 | Step 10 明确允许 executed task-step checkbox states；证据定义明确区分 commit 内记录与提交后派生的 SHA。 |

### 18.3 未采纳的扩大方案

本轮没有新增产品 task 或 Work Package，没有把 430 条 Atomic 命令拆成新任务，没有把 evidence SHA 写入自身 commit，也没有使用“适用真实环境检查”作为隐含绑定。最终交付和 Delivery/Reflection 使用显式 final gate 承接。

### 18.4 机械结果与门禁状态

Atomic verification 复算结果为：430 条非 `Expected` 命令、114 条 Matrix derived binding、316 条非 Matrix 命令，其中新增 32 条 canonical checkbox，缺失绑定为 0。`git diff --check -- PLAN.md AGENT_LOG.md` 通过；本轮没有可运行实现，因此未执行 runtime tests。

这些 PLAN 非 tracking 语义修改使旧 PLAN semantic digest、approval、A/B review、cold-start 和 baseline 结果失效；后续必须重新计算并重新执行相应门禁。详细命令、文件差异和执行边界见 `AGENT_LOG.md` 对应条目。

## 19. T37.2 session task 与 legacy step 术语收口（2026-08-02）

### 19.1 触发与核对

PLAN 审查发现 T37.2 多处把 141 个 legacy TDD steps 称为 `executable Tasks`，并用 `EXECUTABLE_TASK_INCOMPLETE:38.G` 表示一个 legacy step。该表述与 PLAN 的执行单元定义冲突：68 个 `TNN.X` 才是具有 Status、completion evidence 和 session-level execution identity 的 session tasks；141 个 legacy IDs 是其内部原子 TDD microcycles，不是独立 task、subagent、commit 或 evidence 单元。

### 19.2 采纳的最小修复

采纳该术语一致性问题，不新增 Task、Work Package 或独立 legacy 状态。T37.2 改为要求全部 68 个 session tasks terminal and identity-aligned，同时要求全部 141 个 legacy TDD steps 精确映射一次且其 Target/Domain/profile evidence PASS。`EXECUTABLE_TASK_INCOMPLETE:38.G` 改为 `LEGACY_STEP_INCOMPLETE:38.G`，并同步更新 RED 断言、Expected、GREEN 合同、质量审查焦点和执行 checkbox。

### 19.3 验证与门禁状态

本轮只修改 PLAN 术语和对应过程证据，没有实现代码或运行时测试。`git diff --check -- PLAN.md AGENT_LOG.md SPEC_PROCESS.md` 通过；本次 PLAN 非 tracking 语义修改使旧 PLAN semantic digest、approval、A/B review、cold-start 和 baseline 结果失效，后续必须重新计算并重新执行相应门禁。详细执行记录见 `AGENT_LOG.md` 的 `PLAN-T37-2-SESSION-LEGACY-TERM-CLOSURE` 条目。

## 20. SPEC/PLAN 发布所有权与 4.F Bootstrap 最小修复（2026-08-02）

### 20.1 触发与核对

本轮核对发现两项确定问题。第一，SPEC §11.2 仍把真实 GHCR 交付归给 Task 36，而当前 PLAN 已将 WP36/T36.2 限定为 zero-I/O verifier，并将 GitHub Release、GHCR、Render 和终态证据归给 T37.1。第二，PEX-06 的绑定键是 `(task_id, legacy_id, atomic_label)`；`Bootstrap (4.F)` 虽存在于 T04.1 Atomic verification，但只有 4.A Step 5 包含相同 raw command，不能跨 `legacy_id` 借用。

### 20.2 采纳的最小修复

不把 `T37.1` 写入 SPEC。SPEC §11.2 改为任务无关的 §8.4 受保护 release-gate 约束：最终源提交 SHA 冻结且同一 SHA CI 通过后，才可使用受保护凭据执行真实 GHCR 交付。PLAN 不新增任务或重编号，只把 T04.1 Step 13 改为 named remaining-Atomic checkbox，逐字执行 `python scripts/bootstrap_formal_env.py --root . --gate-evidence gates/evidence/workspace-boundary-go-v1.json`，确认 Task 1.E toolchain identity 后再运行 4.F RED。

### 20.3 被拒绝的方案与验证状态

拒绝把 `T37.1` 任务编号写入 SPEC，也拒绝把 Bootstrap 加入全局 `FORMAL_OFFLINE_V1` 或新增任务；这些方案会扩大跨文档绑定或产生重复 binding。核心文本修复在 SPEC/PLAN 各只有一处目标语义行变化，随后仅刷新 PLAN 的当前 SPEC SHA、Git blob 和最后语义修订时间三项 provenance 字段。4.F Bootstrap 逐字命令在 Step 13 中且先于 RED，T36.2 zero-I/O 与 T37.1 发布所有权未被削弱，`git diff --check` 通过。该修复尚未重新计算 PLAN semantic digest，也未重新执行 M0、approval、独立 A/B review、cold-start 或 baseline。

### 20.4 身份刷新与独立 fresh reviewer 结果

为避免 PLAN 自身身份审计继续读取旧 SPEC，刷新了 `Authoritative SPEC SHA-256`、`Authoritative SPEC Git blob` 和最后语义修订时间。当前候选身份为：SPEC SHA-256 `712619a07b9bcfc02bb9835c17c0123dd2079d9cbf8f18276b39d1f1ec0bf250`、SPEC Git blob `e1a79152bde8ff7578e74e6e6a3b2b3bfd9b1ef8`、PLAN 完整 SHA-256 `684b657eb1dfb8f44d057768d193904504995f1aef1087aa17d58153f4cb8f73`、`PlanSemanticDigestV2` `397944858819aedcf634cbe4bd46aeb07dbf245ffecc674557c1eb2834acf93e`、Git HEAD `7b4ea480cb724484f40f380b3c64f600a1c2f4ea`。

一个无历史上下文的 fresh reviewer 复核了两处目标修复并返回文档一致性 `PASS/PASS`，同时对正式准入总门禁返回 `FAIL`：当前文档仍是 Candidate，且没有 M0、PLAN A/B、独立审查、人类批准、cold-start 或 baseline formal evidence。该 reviewer 结果只证明目标修复的文本一致性，不替代任何正式门禁；本轮没有伪造或写入 approval/baseline 结果。

### 20.5 稳定状态行后的身份刷新

用户随后要求先完成稳定 SPEC 顶部状态行，再继续刷新身份。SPEC 顶部已改为不内嵌或推断当前准入状态的外部证据驱动表述；本轮据此将 `PLAN.md` 的 Authoritative SPEC SHA-256 更新为 `556fb14ec8dc6c22834d1611f721316559600fd0bc2f6823ee8cfa7812c23ca8`，Git blob 更新为 `23ff5eb32b87f0d48c011a7535094cf7345bb451`，最后语义修订时间更新为 `2026-08-02T11:39:36+08:00`。

按 PLAN §8.3 / SPEC §11.2 的唯一投影规则重新计算：候选 `PLAN.md` 完整 SHA-256 为 `95559c42b500aa7ff6a413f210ecf01ee1ea835c4175f9973e4c23594de362f1`，`PlanSemanticDigestV2` 为 `90e6a2f9df91d680a844cbbd91dd0863cf0f65cc2ac895f39a04ecfd3d73688f`，Git HEAD 为 `7b4ea480cb724484f40f380b3c64f600a1c2f4ea`。旧身份记录保留为历史记录，不覆盖；本轮没有 M0、PLAN A/B、独立审查、人类批准、cold-start 或 baseline formal evidence，因此不能据此声称准入通过。

### 20.6 外部候选身份重算记录

按用户要求重新从当前 `PLAN.md` 原始字节计算候选身份，不读取旧记录中的摘要作为输入。当前 SPEC SHA-256 为 `556fb14ec8dc6c22834d1611f721316559600fd0bc2f6823ee8cfa7812c23ca8`，SPEC Git blob 为 `23ff5eb32b87f0d48c011a7535094cf7345bb451`；当前候选 PLAN 完整 SHA-256 为 `95559c42b500aa7ff6a413f210ecf01ee1ea835c4175f9973e4c23594de362f1`，`PlanSemanticDigestV2` 为 `90e6a2f9df91d680a844cbbd91dd0863cf0f65cc2ac895f39a04ecfd3d73688f`，Git HEAD 为 `7b4ea480cb724484f40f380b3c64f600a1c2f4ea`。

计算拒绝 BOM 和裸 CR，按正式 Task 区域归一化 68 条 Status、68 条 Completion evidence 与 1750 个 checkbox token；Node crypto 与 WebCrypto 的语义摘要结果一致。该记录只证明当前候选身份，不能替代任何正式 admission 门禁。

### 20.7 文档一致性审查复核

按用户要求重新运行了 document-only consistency review，而不是 code review。无历史上下文的独立 reviewer 确认：SPEC 顶部稳定状态行、SPEC §11.2 的任务无关 release-gate 语义、T36.2/WP36 的 zero-I/O verifier 边界和 T37.1 的最终发布所有权没有发现冲突。Reviewer 未能在其定点读取中独立证明 4.F PEX-06 绑定和四项摘要，因此按 fail-closed 原则没有把这两项判为 PASS；定点核对随后确认 4.F Bootstrap 命令在 PLAN 第 2097 行，并由第 2111 行专属 remaining-Atomic checkbox 在 RED 前执行，当前候选摘要也已由本地两种 SHA-256 实现交叉一致。

该复核不等于 formal `PLAN_SPEC_COMPLIANCE`、`PLAN_EXECUTABILITY`、M0、PLAN A/B、人工批准、异构 cold-start 或 `APPROVED_DOCUMENT_BASELINE_V3`。正式 evidence 未出现前，继续禁止正式实现、CI、发行和部署；人工仍必须审核并批准精确 SPEC/PLAN 候选身份及文档内容。

### 20.8 M0 readiness review 尝试

用户授权执行 SPEC §11.2 M0。独立、无历史上下文的 document-only reviewer `019fc0b8-ef88-72f1-b627-ca7bc21f282c`（Confucius）只读检查后返回 fail-closed `FAIL`，原因是它未完成原始 SPEC SHA-256、PLAN provenance、课程/Harness 逐项覆盖、SPEC 内部一致性和 §11.2 关闭清单；它没有修改文件，也没有声称发现 SPEC 内容缺陷。

本地只读预检确认：正式 SPEC 为 `SPEC.md`，SHA-256 为 `556fb14ec8dc6c22834d1611f721316559600fd0bc2f6823ee8cfa7812c23ca8`，Git blob 为 `23ff5eb32b87f0d48c011a7535094cf7345bb451`，Git HEAD 为 `7b4ea480cb724484f40f380b3c64f600a1c2f4ea`，且 PLAN provenance 与 SPEC SHA/blob 一致；SPEC 具备 9 个用户故事及 FR、NFR、架构、数据模型、威胁模型、分发、技术选型、验收、风险和 Harness 机制章节。但由于独立 M0 checklist 未完成且人类尚未批准精确身份，M0 总体不能判 PASS。

本次不创建或登记伪造的 `m0.json`/admission PASS。M0 需要重新完成独立 checklist，并由人类批准上述精确 SPEC path/SHA/blob/HEAD；在 M0 及其余 formal gates 通过前不得开始正式实现、CI、发行或部署。

### 20.9 M0 独立 checklist 重试结果

新的无历史上下文 document-only reviewer `019fc12c-624e-70f0-a9b4-52e22abba059`（Einstein）完整返回 M0-01 至 M0-06：M0-01 `FAIL`、M0-02 `PASS`、M0-03 `PASS`、M0-04 `FAIL`、M0-05 `PASS`、M0-06 `FAIL`，总体 reviewer recommendation 为 `FAIL`。

M0-01 的实际阻断已独立核实：PLAN 声明的 planning baseline `2521bd2e09874bad308545883d83e43224433594` 中 `SPEC.md` Git blob 为 `27bba78767edf69826e62dbff0e2d2eb11b7a580`，而当前正式 SPEC `D:\code\VesperCode\SPEC.md` 的 SHA-256 为 `556fb14ec8dc6c22834d1611f721316559600fd0bc2f6823ee8cfa7812c23ca8`、Git blob 为 `23ff5eb32b87f0d48c011a7535094cf7345bb451`。当前 PLAN provenance 虽与工作树 SPEC 一致，但与其声明 baseline 的 SPEC blob 不一致，违反 PLAN §8.2 的 planning-input identity 要求。

M0-02 确认 SPEC 覆盖用户故事、FR/NFR、架构、数据模型、凭据威胁模型、分发、技术选型、验收、风险和 Harness 机制；M0-03 未发现已读取语义冲突；M0-05 确认 Task 34 只复现、T36/WP36 zero-I/O、T37.1 独占外部发布和受保护凭据边界。M0-04 的独立技术门禁/冷启动/loopback 关闭证据和 M0-06 的人工批准仍缺失，因此不能生成 M0 PASS 或 admission evidence。

## 21. M0-04 关闭矩阵（当前候选）

### 21.1 绑定身份与审查规则

本矩阵绑定当前未批准的候选身份：SPEC SHA-256 `556fb14ec8dc6c22834d1611f721316559600fd0bc2f6823ee8cfa7812c23ca8`、SPEC Git blob `23ff5eb32b87f0d48c011a7535094cf7345bb451`、PLAN 完整 SHA-256 `8ddb16c96d674d4c9dc0ffd83446992e0fdee18d5b4b2bfd16d269d5d0d4bb94`、`PlanSemanticDigestV2` `0b7b0de39dd7cd618f5957e2ca23130560646260a5b27886d9143424cd81c938`、AGENTS SHA-256 `f4e68e302cfb9cc9f383704ef3be9eb8975277a0715e5357e65070cad2738656`。矩阵只记录 M0-04 所需的可观察关闭证据；“计划已规定”不等于“证据已出现”。正式 evidence root 当前不存在，因此缺失、未运行或未批准均保持 `FAIL`，不创建伪造的 `m0.json` 或 admission PASS。

### 21.2 逐项关闭矩阵

| M0-04 项目 | SPEC 章节/AC | PLAN 所有者 | 可观察关闭约束 | 预期正式证据路径 | 当前证据与状态 | Reviewer 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| 双平台 CI 闭环 | §8—§10；AC-10、AC-11、AC-24、AC-30 | T35.1 / T37.1 | GitHub Actions 与 GitLab CI 的 unit-test、reference-image-build、demo-image-build 和最终 source-aligned 记录必须绑定精确提交；普通 CI 无发布凭据，最终发布只在受保护 gate 中发生。 | `process/evidence/admission-v3/8ddb16c96d674d4c9dc0ffd83446992e0fdee18d5b4b2bfd16d269d5d0d4bb94/m0.json`；`delivery/evidence/ci-v1.json` | `.github/workflows/ci.yml`、`.gitlab-ci.yml`、真实 job/pipeline 记录和 delivery evidence 均不存在；当前未运行。`FAIL` | M0-04 `FAIL`：只有 PLAN 设计合同，没有双平台运行闭环证据。 |
| List/Search canonical cursor | §4.3；AC-17 | T11.1 | 分页与不分页结果必须一致；cursor 必须绑定可见树摘要、无 cursor 查询摘要、稳定扫描位置和自身摘要；过期/无效 cursor 返回零部分结果。 | `process/evidence/admission-v3/8ddb16c96d674d4c9dc0ffd83446992e0fdee18d5b4b2bfd16d269d5d0d4bb94/m0.json`；T11.1 completion/target evidence | `src/`、`tests/` 和 T11.1 evidence 尚不存在；没有可运行的 cursor round-trip/stale/invalid 证据。`FAIL` | M0-04 `FAIL`：合同可追踪，但行为关闭证据缺失。 |
| 每次真实调用前凭据复验 | §4.4.4、§4.8；AC-13、AC-27 | T25.2 / T27.1 | 每次真实 OpenAI 调用在 Grant、authorization record、turn/call 计数和网络副作用前重新探测安全后端并执行 `get_for_call("OPENAI")`；缺失或不安全时零增量、无自动重试。 | `process/evidence/admission-v3/8ddb16c96d674d4c9dc0ffd83446992e0fdee18d5b4b2bfd16d269d5d0d4bb94/m0.json`；T25.2/T27.1 test and review evidence | Credential Manager adapter、调用门和对应测试尚不存在；没有真实调用前序列断言或 Windows evidence。`FAIL` | M0-04 `FAIL`：安全语义已写入 SPEC/PLAN，但未有独立执行证据。 |
| PlanSemanticDigestV2 规则 | SPEC §11.2；PLAN §8.3–§8.4 | PLAN_AUDIT_V3_A / PLAN_AUDIT_V3_B | 两套独立 verifier 必须对完整 PLAN、身份、指标、问题列表和 `PlanSemanticDigestV2` 达成字段级一致；私有负测试必须通过；结果必须绑定当前候选身份。 | `process/evidence/admission-v3/8ddb16c96d674d4c9dc0ffd83446992e0fdee18d5b4b2bfd16d269d5d0d4bb94/plan-audit-a.json`；`plan-audit-b.json` | 本地 Node 摘要核算得到 `0b7b0de3…c938`，但独立 A/B verifier、私有负测试和正式 JSON 均不存在。候选身份核对不构成 A/B 关闭。`FAIL` | M0-04 `FAIL`：摘要数值可复算，正式双 verifier 证据缺失。 |
| 前三项技术门禁与锁定 toolchain 可由获准文档 cold-start | SPEC §11.2；AC-24 | T01.1–T03.2 | 冷启动 agent 必须从精确批准的 SPEC/PLAN 身份检索 T01.1/T38.2；T01.1 先完成 1.A bootstrap、锁定 toolchain 和 identity，再执行 1.B RED；不得依赖历史上下文，且只能在隔离丢弃 worktree 试作。 | `process/evidence/admission-v3/8ddb16c96d674d4c9dc0ffd83446992e0fdee18d5b4b2bfd16d269d5d0d4bb94/cold-start-retrieval.json`；`cold-start-execution.json`；`gates/evidence/gate-toolchain-v1.json` | 无 formal cold-start artifact、gate lock/config/runner evidence 或可接受的异构试作；正式实现前置条件仍未满足。`FAIL` | M0-04 `FAIL`：未有无历史上下文 cold-start 和锁定 toolchain 证据。 |
| Task 2 无凭据 loopback registry 与 OCI digest round-trip | SPEC §8.2、§8.4；AC-24、AC-30 | T02.1–T02.4；Task 34 仅复现 | registry 必须只绑定 `127.0.0.1` 动态端口、不接收凭据、不向检查容器供网；本地 OCI manifest、registry RepoDigest 和 digest pull 的原始 manifest bytes 必须三方相同，并在所有路径清理容器/数据。 | `process/evidence/admission-v3/8ddb16c96d674d4c9dc0ffd83446992e0fdee18d5b4b2bfd16d269d5d0d4bb94/m0.json`；T02.2/T02.4 feasibility and GO evidence | `spikes/`、Docker probe、reference profile 和 `gates/evidence` 均不存在；没有 loopback/OCI round-trip 运行记录。`FAIL` | M0-04 `FAIL`：设计约束存在，但无独立可观察关闭证据。 |
| GHCR 仅属于受保护 release gate | §8.4、§11.2；AC-10、AC-11、AC-24、AC-30 | T35.1 / T37.1；WP36/T36.2 为 pure zero-I/O verifier | 普通 CI、WP36/T36.2 和 Task 34 不得发布；最终 source commit 冻结、同 SHA CI 通过且受保护 release gate 放行后，才可使用受保护凭据执行真实 GHCR；T37.1 独占外部操作与终态证据。 | `process/evidence/admission-v3/8ddb16c96d674d4c9dc0ffd83446992e0fdee18d5b4b2bfd16d269d5d0d4bb94/m0.json`；未来 `delivery/evidence/release-v1.json` | 当前文本交叉核对未发现所有权冲突，但没有 T35/T37 implementation、protected gate、同 SHA CI、release 或 GHCR evidence；不得进行外部发布。`FAIL` | M0-04 `FAIL`：语义边界已确认，受保护发布关闭证据仍缺失。 |

### 21.3 矩阵结论

七项中没有一项具备完整、可接受、独立且绑定当前候选身份的正式关闭证据；本矩阵的总体结论为 `M0-04=FAIL`。这不是把“尚未实现”当成产品缺陷，也不是把计划文本当成运行证据；它表示在 SPEC M0、人工批准、PLAN A/B、独立 PLAN 审查、异构 cold-start 和 Approved-document Baseline 之前，正式实现、CI、发行和部署仍被禁止。

## 22. 候选冻结身份登记

候选文档冻结提交为 `040ad83b98a1a91a48c823aedd7314dada906da4`，提交信息为 `docs: freeze VesperCode specification and implementation plan candidate`。该提交是可供后续审查引用的 `candidate_freeze_commit`，不是 `approved_document_commit`；后者只有在全部门禁通过并由人工批准精确身份后才能成立。

冻结提交后的精确身份如下：

| Object | Raw SHA-256 | Git blob / commit |
| --- | --- | --- |
| `SPEC.md` | `556fb14ec8dc6c22834d1611f721316559600fd0bc2f6823ee8cfa7812c23ca8` | `23ff5eb32b87f0d48c011a7535094cf7345bb451` |
| `PLAN.md` | `8ddb16c96d674d4c9dc0ffd83446992e0fdee18d5b4b2bfd16d269d5d0d4bb94` | `c4a1517b0afae1c0891bf2d90054c11b7ceb0944` |
| `AGENTS.md` | `f4e68e302cfb9cc9f383704ef3be9eb8975277a0715e5357e65070cad2738656` | `2ae9ac8dd10cd1d70ba71fa80458693bba4f4305` |
| Candidate Git HEAD | — | `040ad83b98a1a91a48c823aedd7314dada906da4` |

两套独立摘要 verifier 均从冻结后的 `PLAN.md` 原始字节计算出 `PlanSemanticDigestV2=0b7b0de39dd7cd618f5957e2ca23130560646260a5b27886d9143424cd81c938`：Verifier A 使用 Node `crypto.createHash` 的行索引投影；Verifier B 使用 Node `webcrypto.subtle.digest` 的行映射投影。两者窗口均为第 687 行（含）至第 11046 行（不含），均确认无 BOM、无裸 CR。

冻结后工作区 `git status --short` 为空。此身份登记只记录候选输入和可重复核验结果；M0-01—M0-06、人工批准、PLAN A/B、独立 PLAN 审查、cold-start 和 Approved-document Baseline 仍未通过。

## 23. 独立 M0 checklist 重跑结果

本轮由新的无历史上下文 document-only reviewer `019fc14f-5d02-7543-9bde-5860c0c5ed93`（Singer）针对候选冻结提交 `040ad83b98a1a91a48c823aedd7314dada906da4` 执行完整 M0-01—M0-06。身份登记提交 `e5bb452cdc44c63b1819d6e4abcae448ea9027ca` 仅追加 `AGENT_LOG.md`/`SPEC_PROCESS.md`，不改变候选 SPEC/PLAN/AGENTS 字节。

| M0 项目 | 结论 | 依据 |
| --- | --- | --- |
| M0-01 identity/provenance | `PASS` | SPEC-only planning baseline `cf4bcab...` 的 SPEC blob 为 `23ff5eb32b87f0d48c011a7535094cf7345bb451`；PLAN provenance、课程文件和 AGENTS 身份与候选一致。 |
| M0-02 course/Harness coverage | `PASS` | SPEC 覆盖问题/范围、9 个用户故事、FR/NFR、Harness 机制、架构/数据模型、凭据威胁模型、分发、验收、风险和机制演示。 |
| M0-03 SPEC internal consistency | `PASS` | 未发现范围、架构、数据、安全、凭据、验证、非目标或验收之间的内部冲突。 |
| M0-04 known closure evidence | `FAIL` | §21 七项矩阵逐项为 FAIL：双平台 CI、cursor、逐调用凭据复验、正式双 verifier、T01–T03/toolchain cold-start、Task 2 loopback/OCI round-trip、GHCR protected gate 均无正式绑定证据。 |
| M0-05 publication ownership | `PASS` | Task 34 只复现，T36/T36.2/WP36 为 pure zero-I/O verifier，T37.1 独占 GitHub Release/GHCR/Render 和终态外部操作。 |
| M0-06 human approval | `FAIL` | 未找到人工批准精确 SPEC path、SPEC SHA-256、SPEC blob 和候选 Git HEAD 的记录；候选登记和 agent reviewer 不能代替人工批准。 |

Reviewer 的总体 recommendation 为 `FAIL`。Reviewer 明确未将“尚未实现”当作 SPEC 内容缺陷；M0-04 的 FAIL 是正式关闭证据缺失，M0-06 的 FAIL 是人工决策缺失。由于六项未全部 PASS，本轮不进入人工 M0 批准、PLAN A/B、PLAN_SPEC_COMPLIANCE、PLAN_EXECUTABILITY、cold-start 或 baseline，也不创建 `m0.json`、任何 admission PASS artifact 或其他 formal evidence。

## 24. M0-04 formal fail-closed artifact 登记

已将当前候选的 M0-04 逐项矩阵写入并提交：

- **Artifact:** `process/evidence/admission-v3/8ddb16c96d674d4c9dc0ffd83446992e0fdee18d5b4b2bfd16d269d5d0d4bb94/m0-04-closure-matrix.json`
- **Artifact commit:** `c11932c`（`docs: record fail-closed M0-04 evidence`）
- **Artifact SHA-256:** `32fd9c58bdb4fa9a13faa77abf5f3e76cd8fcf208bdd9371b8111877859d938`
- **Schema:** `M0_04_CLOSURE_MATRIX_V1`
- **Bound candidate:** SPEC SHA/blob、PLAN SHA/blob、`PlanSemanticDigestV2`、AGENTS SHA 和 candidate freeze commit 均与 §22/§23 相同。
- **Result:** 7 个 check 全部为 `FAIL`，`decision=FAIL`；其中 7 个文档合同存在，但没有一项拥有足以关闭 M0-04 的正式运行/批准证据。

该 artifact 是可追溯的失败尝试记录，不是 PLAN §1.2 所称的 accepted ten-artifact set，不是 `m0.json`，不构成 M0 PASS、人工批准或实现授权。后续若补充真实证据，必须以同一候选身份重新生成并由独立 reviewer 复核；任何身份变化都使本 artifact 失效。

## 25. M0-04 formal artifact 独立复核结果

新的无历史上下文 document-only reviewer `019fc166-b66c-7090-8f07-ddd0a4deda77`（Kuhn）复核了当前候选身份和 §24 的 `M0_04_CLOSURE_MATRIX_V1`。复核确认：candidate freeze 为 `040ad83b98a1a91a48c823aedd7314dada906da4`，复核时 HEAD 为 `766374c`，SPEC/PLAN/AGENTS 字节与冻结提交一致，工作区干净。

复核结果：M0-01 `PASS`、M0-02 `PASS`、M0-03 `PASS`、M0-04 `FAIL`、M0-05 `PASS`、M0-06 `FAIL`，总体 recommendation 为 `FAIL`。M0-04 artifact 的 schema、7 个 check、候选身份绑定和 `closure_pass_count=0` 均通过结构核验，但 artifact 的 `decision=FAIL` 不能被解释成 M0-04 通过；M0-06 仍缺少人工对精确 SPEC path/SHA/blob/candidate Git HEAD 的批准。

本次复核不生成或声称 `m0.json`、`human-approval.json` 的 APPROVE、PLAN A/B PASS、PLAN review PASS、cold-start PASS、`baseline.json` 或任何实现/发布成功证据。M0 全部通过前继续禁止正式实现、CI、发行和部署。

## 26. 当前轻量冷启动前文档检查（2026-08-02）

### 26.1 当前流程取代旧 admission 设计

本条依据当前 `SPEC.md` §11.2 和 `PLAN.md` §1、§8、§9 记录。前文旧 M0、双审计、语义摘要审批、formal JSON admission evidence 和三提交 baseline 记录均属于历史过程，不是当前冷启动前置条件；本条不重新执行或认可那些旧门槛。

### 26.2 检查结果

1. **SPEC 覆盖：通过。** 当前 `SPEC.md` 可定位问题范围、9 个用户故事、FR/NFR、架构、数据模型、凭据威胁模型、分发/部署、技术选型、验收标准、风险，以及 Coding Agent Harness 的 domain/mechanism design。
2. **选定 task 卡：通过（针对本次试作范围）。** `PLAN.md` 当前 `T01.1` 卡包含目标、SPEC contracts、Files、Depends、Parallelization、Interfaces、RED/GREEN、Atomic verification、review/completion steps；当前 `T37.2` 卡同样包含这些字段，并明确了 `PROCESS_EVIDENCE_INVALID` 和 `LEGACY_STEP_INCOMPLETE:38.G` 的 RED 断言与验证命令。
3. **试作范围：已选定。** 选择 `T01.1` 的 bounded Gate bootstrap 子范围（std-lib probe、gate environment/config/runner/gate-scan identity 检查，直到确认能否进入首个行为 RED），以及 `T37.2` 当前 task card。试作不承担完整正式依赖链，也不执行 T37.1 的真实发布。
4. **未决歧义：已登记。** `T01.1` 的 Windows 11/Python 3.12/Docker 与锁定依赖环境尚未在当前工作区建立；`T37.2` 的部分 fixture/helper 和 T37.1 process-evidence 输入尚不存在；PLAN 中保留的历史附录可能造成误读。陌生 Agent 必须对这些问题暂停提问，不得猜测、伪造 fixture、绕过依赖或把计划文本当成运行证据。
5. **人工启动确认：已记录。** 用户当前指令“执行两阶段方案”明确要求继续执行冷启动验证。本记录只把该指令作为冷启动启动确认，不推断任何 M0、身份批准或正式实现授权。

### 26.3 冷启动执行约束

当前结论为 **可以启动 disposable cold-start，不能开始正式实现**。冷启动 Agent 将使用与主 Agent 不同的模型类型 `gpt-5.6-luna`，`fork_context=false` 开启全新 session；提示中只提供 `SPEC.md`、`PLAN.md` 和上述两个选定范围，要求它遇到不确定内容立即暂停提问。试作上限约 1—2 小时，运行在可丢弃隔离环境；其代码、提交和分支不进入正式实现。

## 27. 冷启动反馈与提示修正（2026-08-02）

### 27.1 试作结果

- 第一次 session `Hubble`（`gpt-5.6-luna`）在返回结论前发生服务流断开；没有可用试作结果，也没有工作区改动。
- 第二次 session `Raman`（`gpt-5.4-mini`）为全新、无历史上下文 session，成功返回文档审阅结果，但由于启动提示错误地禁止读取源码、测试、配置和其他仓库文件，它只能验证文档可读性，不能完成真正的实现/命令发现/RED 验证。因此该次结果是**受提示限制的部分冷启动反馈**，不是完整 cold-start PASS。
- `Raman` 确认 `T01.1` 的 1.A bootstrap 与 1.B 首个行为 RED 顺序清楚；确认当前 `T37.2` 是依赖 `T37.1` 的 final readiness gate，范围过大且不适合作为陌生 Agent 首次试作；确认现行 T37.2 与历史附录卡片的并存会增加误选风险。

### 27.2 已采纳修正

1. `PLAN.md` 明确 `T01.1`：1.A 只验证 pre-RED bootstrap 完整性，1.B 才是第一个行为 RED。
2. `PLAN.md` 明确 `T37.2` 是 final readiness gate，不是 cold-start candidate；下一次试作只选 `T01.1` bounded bootstrap 子范围。
3. 下一次冷启动提示只提供当前 `SPEC.md`/`PLAN.md` 作为初始规范和上下文，但允许 Agent 在隔离试作 worktree 中自行搜索仓库文件、定位接口、运行 PLAN 声明的命令并尝试实现；“遇到不确定内容暂停提问”不等于禁止正常仓库探索。
4. 下一次试作仍必须是不同模型类型、全新 session、无历史/memory、约 1—2 小时、可丢弃，代码/提交/分支不得进入正式实现。

### 27.3 当前状态

当前没有 cold-start PASS，也没有正式实现授权。因试作提示设计导致执行性验证不足，必须按修订后的 T01.1 范围重新启动一次冷启动；在该反馈记录和文档修订完成前不进入正式 worktree/subagent/TDD 实现流程。

## 28. 冷启动候选基线阻塞（2026-08-02）

修订提示后的第三次冷启动 Agent `Dalton`（`gpt-5.6-terra`，全新无历史 session）只读取了当前 `SPEC.md` 和 `PLAN.md`，随后正确暂停：当前候选文档仍是工作区未提交修改，原生 Git disposable worktree 从 `HEAD` 建立会得到旧版 SPEC/PLAN，无法证明试作依据当前文档。它未运行 1.A、1.B、依赖物化或测试，也未修改任何文件。

该暂停是有效的过程反馈，不是 T01.1 可执行性 FAIL。为解决它，先建立一个只含当前文档和过程记录的候选提交（不含实现代码），再从该精确提交创建干净 disposable worktree，重新启动只选 `T01.1` bounded bootstrap 的冷启动。候选提交不是人工批准、不是正式实现提交，也不把任何试作代码合入主线。

## 29. 冷启动 T01.1 合同缺口反馈（2026-08-02）

### 29.1 试作身份与执行范围

- **Agent:** `Wegener`（`019fc1bf-2211-7a13-84da-c104a6230117`），类型为 `gpt-5.4`，与主开发 Agent 类型不同。
- **Session:** 全新、无历史上下文、`fork_context=false`；初始规范只提供当前 `SPEC.md` 和 `PLAN.md`。
- **Worktree:** `D:\code\VesperCode\.worktrees\_cold-start-trials\cold-start-v3-3b68389`，从候选文档提交创建的 disposable worktree。
- **范围:** 只尝试 `T01.1` 的 1.A bounded gate bootstrap，并在满足前置条件时进入 1.B；不读取 `SPEC_PROCESS.md`、`AGENT_LOG.md` 或 Git 历史，不执行正式实现流程。
- **代码边界:** 没有修改文件、创建试作提交或生成正式证据。

### 29.2 实际检查结果

1. PATH Python probe 通过：`C:\ProgramData\anaconda3\python.exe`，Python `3.12.4`，`sys.version_info[:2] == (3, 12)`。
2. 候选 worktree 中 `requirements/`、`scripts/`、`gates/`、`tests/`、`spikes/`、`src/` 和 `pyproject.toml` 均不存在；因此不能把缺少实现骨架误报为行为 RED。
3. `T01.1` 的 1.A/1.B 顺序可理解：1.A 是 pre-RED prerequisite，1.B 才是第一个行为 RED。
4. `T01.1` 要求固定 gate-scan 规则和 stable `rule_id`，但当前 `SPEC.md` 和 T01.1 没有规则表、命名集合、匹配边界或错误优先级。后续 `4.E` 中出现的 `GENERIC_API_KEY` 不能作为 T01.1 的隐式输入。
5. `GateToolchainEvidenceV1` 没有在 `SPEC.md` 或 T01.1 中闭合定义，却被后续 `1.E`、`2.G`、`4.F` 和 `4.A` 消费；因此 1.A 不能无猜测创建 `gates/evidence/gate-toolchain-v1.json`。
6. `scripts/run_gate_checks.py` 的命令集合存在概述，但参数转发、固定配置不可覆盖边界和稳定错误/输出语义仍不完整。

### 29.3 结论与文档修订

结论为 **T01.1 1.A 合同不自足，不能合法进入 1.B RED**。这不是环境失败，也不是要求 Agent 编写占位代码；它是对 SPEC/PLAN 隐含假设的有效冷启动发现。问题的主要性质不是任务数量过大，而是 pre-RED contract 缺少两个核心产物的精确定义。

已接受以下修订：

- 在 T01.1 内联 `GateToolchainEvidenceV1` 的完整字段、额外字段拒绝规则、原始文件 digest 绑定、canonical `evidence_digest` 和 exact `python_version` 语义；
- 在 T01.1 内联 gate-scan 的固定 `rule_id` 集合、原始字节匹配边界、文本/二进制处理、路径/对象/读取失败语义、输出排序、退出码和无值输出规则；
- 明确 `run_gate_checks.py` 的四个命令 token、固定解释器/配置、`--` 分隔符、可转发参数范围和禁止配置/执行环境扩展的稳定错误；
- 明确冷启动在真实环境缺失或上述合同仍无法满足时必须暂停报告，不得创建假 lock、占位 evidence 或无效 RED。

这些是 T01.1 的实质合同变更，故文档修订完成后必须从新的候选文档提交建立新的 disposable worktree，并重新进行 T01.1 冷启动。当前仍未获得 cold-start PASS，也未授权正式实现。
这些是 T01.1 的实质合同变更，故文档修订完成后必须从新的候选文档提交建立新的 disposable worktree，并重新进行 T01.1 冷启动。当前仍未获得 cold-start PASS，也未授权正式实现。

## 30. 第二次 T01.1 冷启动的 profile 参数冲突（2026-08-02）

### 30.1 试作结果

新的陌生 Agent `Einstein`（`019fc1d7-a9a4-7872-9389-79a76c7fbf8f`，`gpt-5.4`）在全新、无历史上下文的 disposable worktree `D:\code\VesperCode\.worktrees\_cold-start-trials\cold-start-v4-e0fba46` 中执行。它只读取 `SPEC.md` 和 `PLAN.md`，没有读取 `SPEC_PROCESS.md`、`AGENT_LOG.md` 或 Git 历史，没有修改或提交任何文件。

它确认：

- PATH Python `3.12.4` 和精确候选 `HEAD=e0fba46fb4bf145cc209e83726731251e240e9e1` 有效；
- `https://pypi.org/simple` 返回 `200`，因此本次不是 Python 或解析源不可用；
- `requirements/`、`gates/`、`scripts/`、`tests/feasibility/`、`spikes/` 均不存在，尚未创建任何试作骨架；
- 1.A 尚未完整通过，故 1.B 没有执行资格。

### 30.2 新的 BLOCKING 发现

`PLAN.md` 同时规定了互相冲突的 Mypy 参数边界：

1. T01.1 的 closed pre-RED contract 只允许 `src`、`tests` 或其后代；
2. §3.4 的 `GATE_OFFLINE_V1` 明确要求执行
   `.venv-gate\\Scripts\\python.exe scripts/run_gate_checks.py mypy -- spikes tests/feasibility scripts/run_gate_checks.py scripts/bootstrap_gate_env.py`；
3. T01.1 Step 5 又要求该 profile 的精确 Mypy 命令通过后才可进入 1.B。

这三条不能同时成立。Agent 按“遇到 material uncertainty 暂停，不得猜测”的要求停止；该结果是 PLAN 内部合同冲突，而不是可通过实现选择解决的细节。

### 30.3 采纳修订与后续

采纳以既有 `GATE_OFFLINE_V1` 固定命令为权威，将 T01.1 runner 的 Mypy 白名单统一为：目录根 `spikes`、`tests/feasibility`、`src`、`tests` 及其后代，另加两个固定 gate 文件 `scripts/run_gate_checks.py` 和 `scripts/bootstrap_gate_env.py`。其他路径和配置/环境扩展仍拒绝。该修订只解决当前已存在的命令冲突，不扩大到任意 repository path。

由于选定 task 的 runner 合同再次发生实质变化，必须建立新的候选文档提交和新的 disposable worktree，并重新执行 T01.1 冷启动。当前仍没有 cold-start PASS，也没有正式实现授权。

## 31. 第三次 T01.1 冷启动的 lock、CLI 与任务粒度反馈（2026-08-02）

### 31.1 试作身份与已验证事实

- **Agent:** `Popper`（`019fc1e0-7c54-7f02-860c-e10073c40e4c`），`gpt-5.4`，全新 session、无历史上下文。
- **Worktree:** `D:\code\VesperCode\.worktrees\_cold-start-trials\cold-start-v5-82ae8ba`，精确绑定候选提交 `82ae8ba110d1ff80a1e6dffb3e8d5cb36ce9f9ec`。
- **Initial context:** 只读取 `SPEC.md` 和 `PLAN.md`；没有读取 `SPEC_PROCESS.md`、`AGENT_LOG.md`、Git 历史或其他过程证据。
- **Environment:** Python `3.12.4`、PyPI `https://pypi.org/simple/` 可达、worktree 干净；`requirements/`、`gates/`、`scripts/`、`tests/feasibility/`、`spikes/` 尚不存在。
- **Boundary:** 未创建、修改或提交任何文件；没有进入 1.B 或正式实现。

### 31.2 新的 BLOCKING 反馈

Popper 确认上一轮 Mypy profile 冲突已经消失，但发现 T01.1 仍有三类执行性缺口：

1. `requirements/gate.lock` 只规定了“完整版本、marker、source、normalized names 和 hashes”，没有说明 pip requirements 落盘格式、支持 profile 的 hash 范围、依赖图完整性如何映射到文件，或禁止哪些 source/options。
2. `scripts/bootstrap_gate_env.py` 没有闭合每个子命令的输入/输出、成功/失败退出码、stdout/stderr、是否允许 pip、lock 原子写入和失败保留策略。
3. 1.A 把输入/配置、runner、gate-scan、lock resolve/review、environment materialization、evidence freeze 和完整性验证绑在一个冷启动范围；正向完整性测试只有覆盖目标，没有最小测试名称和首断言边界。Agent 判断该范围对陌生 Agent 偏大。

这些问题均属于文档合同缺口，不能靠实现者自行选择；Agent 按要求暂停，1.A 未通过，1.B 没有资格开始。

### 31.3 已采纳修订

已在 `PLAN.md` 中：

- 将 1.A 明确拆为 `1.Aa`（固定输入、runner、scan 和最小完整性测试）、`1.Ab`（lock resolve/review）和 `1.Ac`（materialize/evidence/profile closure）三个有明确边界的顺序子切片；下一轮 cold-start 只选择 `1.Aa`；
- 冻结 `requirements/gate.in` 五条 direct requirements 及 `requirements/gate.lock` 的 pip requirements/hash/source/marker/排序/原子写入格式；
- 冻结 `resolve-lock`、首次 `materialize` 和后续 `--require-existing-evidence` 的网络、安装、失败关闭和 stdout/stderr/exit-code 语义；
- 为 `tests/feasibility/gate/test_gate_bootstrap.py` 指定八个最小稳定测试名及首断言边界，区分 1.Aa 的前六个测试与 1.Ab/1.Ac 的后两个测试；
- 保留“1.A 全部成功后才可添加/运行 1.B RED”的顺序，且不把这些子切片变成新的 M0、独立 admission 或产品任务。

由于这次修订改变了选定 cold-start 的 task contract 和范围，必须从新的候选文档提交建立新的 disposable worktree，再以全新 session 重跑。当前没有 cold-start PASS，也没有正式实现授权。

## 32. 第四次 T01.1 冷启动的 Ruff 根路径边界反馈（2026-08-02）

### 32.1 试作身份与执行范围

- **Agent:** `Beauvoir`（`019fc1ed-b92d-7341-af00-848f866d9a11`，`gpt-5.4`），全新 session、无历史上下文。
- **Worktree:** `D:\code\VesperCode\.worktrees\_cold-start-trials\cold-start-v6-a959510`，从候选文档提交 `a9595108e2a6d508d67be9e312a008f132e95a2f` 创建的 disposable worktree。
- **Initial context:** 只向 Agent 提供当前 `SPEC.md` 和 `PLAN.md`；未提供 `SPEC_PROCESS.md`、`AGENT_LOG.md`、先前对话或 memory。
- **范围:** 仅尝试 `T01.1` 的 bounded `1.Aa` gate bootstrap；未进入 `1.B`，未进入正式实现流程。

### 32.2 新的执行性歧义

Beauvoir 对照了 T01.1 runner 合同和 `GATE_OFFLINE_V1` 的精确命令，发现：

1. runner 文字原先规定两个 Ruff 命令只能接收 repository-relative paths；
2. `GATE_OFFLINE_V1` 的权威命令明确要求 `ruff-format -- .` 和 `ruff-check -- .`；
3. 因而陌生 Agent 无法确定 `.` 是应被拒绝的非路径 token，还是必须支持的仓库根输入。该选择会直接改变 runner 行为和最小完整性测试的断言。

Agent 未猜测、未创建占位文件、未修改或提交任何代码，正确暂停在 `1.Aa` 合同核对阶段。该问题属于 `BLOCKING` 文档合同歧义，不是环境失败。

### 32.3 采纳修订与后续

已采纳现有 `GATE_OFFLINE_V1` 精确命令为权威，并在 `PLAN.md` T01.1 runner 合同中明确：两个 Ruff 命令可以接收精确的 `.` 仓库根哨兵或 repository-relative paths；`.` 是唯一允许的非路径根哨兵，并作为一个 argv 元素转发。最小完整性测试同步要求验证 `ruff-format -- .` 和 `ruff-check -- .` 均被接受；其他参数关闭边界不变。

这是选定冷启动 task 的 runner 接口和测试合同的实质变化。必须从该修订后的候选文档提交创建新的 disposable worktree，并用全新、无历史上下文的不同类型 Agent 重跑 `T01.1` bounded `1.Aa`。当前仍没有 cold-start PASS，也没有正式实现授权；本次修订不引入 M0、双审计、语义摘要审批、JSON admission evidence 或 baseline 要求。

## 33. 第五次 T01.1 冷启动的 1.Aa 执行边界反馈（2026-08-02）

### 33.1 试作身份与执行范围

- **Agent:** `Carver`（`019fc201-8f38-7ad0-8abe-cf639eaa147d`，`gpt-5.6-luna`），全新 session、`fork_context=false`、无历史上下文。
- **Worktree:** `D:\code\VesperCode\.worktrees\_cold-start-trials\cold-start-v7-cc12380`，精确绑定候选提交 `cc123806a3620788ddc98960af8bdeab60bd8c01`。
- **Initial context:** 只读取 `SPEC.md` 和 `PLAN.md`；未读取 `SPEC_PROCESS.md`、`AGENT_LOG.md`、其他 worktree、父工作区文件、Git 历史或本对话内容。
- **范围:** 只尝试 `T01.1` bounded `1.Aa`；未进入 `1.Ab`、`1.Ac` 或 `1.B`，未修改或提交任何文件。

### 33.2 新的 BLOCKING 反馈

Carver 实际核对并暂停，结论为 `BLOCKING`：

1. `1.Aa` 只有完整 1.A bootstrap 的 `.venv-gate` integrity 命令，没有一个在“不物化环境”边界内运行前六个测试的专用命令；
2. 测试要求注入 Git enumeration、path、object、read failure，但没有定义可观察的函数、模块或测试替身接口；
3. 当前候选工作树中没有 `1.Aa` 声明的实现/测试文件，不能把缺失文件当成既有 fixture 或偷偷依赖后续任务；
4. PATH 环境为 Python `3.12.4`、pytest `7.4.4`、Mypy `1.10.0` 且未安装 Ruff，不满足 gate profile；但 `1.Aa` 又没有说明是否允许使用标准库路径来验证其自身合同。

Carver 运行了 Python/Git/工具版本和工作树状态检查，发现工作树干净，未猜测接口、未创建占位 lock/evidence、未进入 `1.B`。这些是 `1.Aa` 合同和环境边界的文档问题，不是可由实现者自行选择解决的环境问题。

### 33.3 采纳修订与后续

已在 `PLAN.md` 中采纳以下最小修订：

- 将 `1.Aa` 明确为 PATH Python `3.12` 的标准库-only `unittest` slice；新增精确 Python probe 和 `AaIntegrityTests` 命令。该 slice 不接触 PyPI、不调用第三方 test runner/Ruff/Mypy、不创建 `.venv-gate`、不解析 lock、不写 evidence；
- 为 `run_gate_checks.py` 定义 `build_closed_argv`/`run_closed_command` 的可注入 subprocess seam；
- 新增 Task 1-owned `scripts/gate_scan.py`，定义 `GateScanHooksV1`、`GateScanRunResultV1` 和 `run_gate_scan` seam；`scan_gate_changed_files.ps1` 仅作为无参数入口委托给默认 hooks；同时在 `GateToolchainEvidenceV1` 中分别绑定 PowerShell 入口和 Python 核心的 raw-file SHA-256；
- 将前六个完整性测试归入 `AaIntegrityTests`，后两个归入 `AbAcIntegrityTests`，并把完整 gate integrity 命令保留到 `1.Ac`；
- 将新增 helper 纳入文件所有权和 T01.1 提交清单。

这是选定冷启动 task 的测试运行边界、环境前提和测试接口的实质变化，必须从修订后的新候选提交建立 disposable worktree，并用全新、无历史上下文的不同类型 Agent 重跑 `T01.1` bounded `1.Aa`。当前仍没有 cold-start PASS，也没有正式实现授权；本次修订不引入 M0、双审计、语义摘要审批、JSON admission evidence 或 baseline 要求。

## 34. 第六次 T01.1 冷启动尝试：服务断开与初始文件状态边界（2026-08-02）

### 34.1 Russell 尝试

- **Agent:** `Russell`（`019fc211-cecd-7340-ae84-2d470a0513eb`，`gpt-5.4`），在候选提交 `820f32fe195b3f6a840e6cd2a13cc285f2c98df0` 的 disposable worktree `cold-start-v8-820f32f` 中以全新、无历史上下文 session 启动。
- **结果:** session 在返回报告前发生 `stream disconnected before completion`。没有可用的任务判断、测试结果或代码提交；只读检查确认 worktree 没有未提交改动。该尝试不构成 PASS、BLOCKING 文档结论或正式证据。

### 34.2 Laplace 反馈

- **Agent:** `Laplace`（`019fc217-1abd-7ce0-b3ec-8df1d728efac`，`gpt-5.6-terra`），同一候选提交和 worktree 上的全新、无历史上下文 session；只读取 `SPEC.md` 和 `PLAN.md`，未修改或提交文件。
- **已验证:** PATH Python `3.12.4` probe 通过；`1.Aa` 的标准库限制、精确命令、runner seam、gate-scan seam 和不进入 `1.Ab/1.Ac/1.B` 的边界均可定位。
- **观察:** 在干净候选中直接运行 `python -m unittest -v tests.feasibility.gate.test_gate_bootstrap.AaIntegrityTests` 得到 `ModuleNotFoundError: No module named 'tests.feasibility'`，因为 `1.Aa` 声明的测试和实现文件尚未由 Step 1 创建。Laplace 依据 PLAN 中过宽的“missing declared file is BLOCKING”措辞停止，没有猜测或补写文件。
- **结论:** 这是 `PLAN.md` 执行顺序措辞问题：冷启动应先执行 Step 1 的 pre-RED 文件创建和 seam 实现，再执行 Step 1.Aa；干净候选在 Step 1 之前缺少这些文件是预期状态，不应直接判为阻塞。`1.Aa` 的 task 范围本身没有因此变大，也没有进入后续切片。

### 34.3 采纳修订与后续

已在 `PLAN.md` 中明确：声明文件在冷启动初始状态可以不存在；Step 1 负责创建它们，Step 1.Aa 命令只在 Step 1 后运行；只有 Step 1 后仍缺文件、seam 不可用、Python probe 失败或出现未定义歧义才是 `BLOCKING`。下一轮提示将明确要求 Agent 先执行 Step 1，再运行 1.Aa 命令。

该修订仍属于选定 task 的执行顺序合同变化，必须从新候选文档提交创建 disposable worktree，并由全新、无历史上下文的不同类型 Agent 重跑 `T01.1` bounded `1.Aa`。当前没有 cold-start PASS，也没有正式实现授权；Russell 的服务失败不计入成功尝试。

## 35. 第七次 T01.1 冷启动的 PASS 复核与 gate-scan 输出偏差（2026-08-02）

### 35.1 Dirac 试作结果

- **Agent:** `Dirac`（`019fc21d-3756-7f90-8d95-19bcdab1ae43`，`gpt-5.4-mini`），全新、无历史上下文 session；候选提交为 `82af24150dd1da5f8a6ccb6ecdcc3c03f6a6c697`，worktree 为 `D:\code\VesperCode\.worktrees\_cold-start-trials\cold-start-v9-82af241`。
- **执行:** Agent 先按 Step 1 创建了 1.Aa 验证性文件，再运行 Python 3.12 probe 和 `python -m unittest -v tests.feasibility.gate.test_gate_bootstrap.AaIntegrityTests`。第一次测试因自身 runner 对 Ruff `--config` 的判断过宽而失败，修正后报告 6/6 通过；未进入 `1.Ab/1.Ac/1.B`，未提交。
- **独立复核:** 主 Agent 在同一 disposable worktree 重跑两个约定命令，probe exit `0`，`AaIntegrityTests` 显示 6 tests、`OK`；确认 `requirements/gate.lock`、gate evidence 和 1.B evaluator/test 文件均不存在。该复核证明命令可运行和任务边界可执行，但不自动证明试作实现符合所有 PLAN 输出合同。

### 35.2 新的 BLOCKING 偏差

Dirac 的正向测试和实现把 credential match 的结果写成 `stderr="ERROR\\tGATE_SCAN_CREDENTIAL_MATCH\\n"`。但当前 `PLAN.md` 的 gate-scan contract 明确规定：match 时退出码为 `1`，stdout 只包含 `MATCH<TAB>path<TAB>rule_id` 行，stderr 必须为空；稳定 `ERROR<TAB>...` 只属于退出码 `2` 的 operational/invocation error。该偏差不是规范允许的另一种命名，而是实现和正向测试遗漏了既有 output contract。

因此本次 Dirac 报告不能作为最终 cold-start PASS。它有效证明了：Agent 能找到 Step 1、创建 1.Aa 文件并运行命令；同时暴露了 1.Aa 最小正向测试没有把 match 的空 stderr 断言写成明确完成条件，允许错误理解通过。

### 35.3 采纳修订与后续

已将 `test_gate_scan_emits_sorted_redacted_rule_ids` 的首断言边界补强为：match exit `1`、仅有精确 `MATCH<TAB>path<TAB>rule_id` stdout、stderr 精确为空、不得泄露值。保留现有 operational error 的稳定 `ERROR` 断言。Dirac 的代码和测试均为 disposable 验证性试作，不合并、不采纳。

这是选定冷启动 task 的完成条件实质修订，必须从新候选文档提交创建 disposable worktree，并以全新、无历史上下文的不同类型 Agent 重跑 `T01.1` bounded `1.Aa`。当前仍没有 cold-start PASS，也没有正式实现授权。

## 36. 第八次 T01.1 冷启动的命令可执行但 Aa 合同未满足（2026-08-02）

### 36.1 Lagrange 执行环境失败

- **Agent:** `Lagrange`（`019fc241-c894-7082-b3b8-cf0a1ce474d2`，`gpt-5.6-luna`），全新、无历史上下文 session；worktree 为 `D:\code\VesperCode\.worktrees\_cold-start-trials\cold-start-v10-93f2fb7`。
- **结果:** Agent 在指定 worktree 和仓库根目录执行只读命令时均遇到 `CreateProcessAsUserW failed: 5`，未读取 `SPEC.md`/`PLAN.md`，未创建文件，未运行验证命令，也未修改文件。
- **分类:** 环境失败，不是 SPEC/PLAN 发现，也不计为 PASS。主 Agent 随后确认 v10 worktree 可读、HEAD 为候选文档提交 `93f2fb7d030385c1f0729b727f47bd58c9dc1519`；该次 session 的代码没有留下。

### 36.2 Aquinas 试作与独立复核

- **Agent:** `Aquinas`（`019fc243-5135-7fb1-b309-4f91d8503e87`，`gpt-5.4-mini`），全新、无历史上下文 session；初始只提供 `SPEC.md` 和 `PLAN.md`，worktree 为同一 v10 disposable worktree。
- **执行:** Agent 按 Step 1 创建了 gate 输入、配置、runner、gate-scan 和 `AaIntegrityTests` 文件；未进入 `1.Ab/1.Ac/1.B`，未提交、未合并。Python 3.12 probe 为 `exit=0`；`python -m unittest -v tests.feasibility.gate.test_gate_bootstrap.AaIntegrityTests` 报告 6 tests、`OK`。
- **独立复核:** 主 Agent 使用同两条精确命令得到 probe `exit=0` 和 6 tests `OK`。但实际测试方法为 `test_changed_file_enumeration_is_deterministic`、`test_format_match_is_exact_and_ordered` 等，缺少 PLAN 要求的六个规范方法，包括 `test_gate_scan_emits_sorted_redacted_rule_ids`；测试也未断言 match 的 `exit=1`、精确 stdout 和空 stderr。
- **结论:** 这是“命令可执行但验证性实现未遵守已明确的 Aa 完成合同”，不是允许 Agent 猜测的文档歧义，因此 Aquinas 轮不能作为 cold-start PASS。disposable 文件和修改均不采纳。

### 36.3 修订与后续

已在 `PLAN.md` 明确：六个 `AaIntegrityTests` 方法名及其首断言是规范合同，不是示例；替换方法名、只测试 helper 或遗漏 exit/stdout/stderr/error 断言均不满足 1.Aa。该修订仍需从新的候选文档提交创建 disposable worktree，并用全新、无历史上下文的不同类型 Agent 重跑；当前没有正式实现授权。

## 37. 第九次 T01.1 冷启动的 1.Aa 文件边界与配置内容歧义（2026-08-02）

### 37.1 Kuhn 独立冷启动结果

- **Agent:** `Kuhn`（`019fc24e-a352-7350-a35b-b8f42269650d`，`gpt-5.6-terra`），全新、无历史上下文 session；候选提交为 `f33c04be8a7a0e005e9fcd989911b6dbf6d87fbc`，worktree 为 `D:\code\VesperCode\.worktrees\_cold-start-trials\cold-start-v11-f33c04b`。
- **执行:** Agent 仅读取 `SPEC.md`/`PLAN.md`，定位到 T01.1 和 1.Aa 步骤；未修改文件，未运行 Python probe 或 unittest，未进入 `1.Ab/1.Ac/1.B`，未提交或合并。
- **Finding 1:** 1.Aa 的 Own 文件清单排除了 `scripts/bootstrap_gate_env.py`，但 Step 1 的文字要求创建 bootstrap command；同时 bootstrap 又包含 1.Ab/1.Ac 的 lock/materialize 接口，无法在不猜测的情况下决定 Aa 是否应创建完整文件。
- **Finding 2:** `gates/pytest.ini`、`gates/ruff.toml`、`gates/mypy.ini` 只定义了职责和文件名，没有定义可直接执行的具体配置内容；Agent 若自行选择配置会违反暂停而不猜测的规则。

### 37.2 独立复核与修订

主 Agent 对照 v11 PLAN 原文确认两点均成立。已将 `1.Aa` 明确限定为 gate input/config/runner/scan 文件；`scripts/bootstrap_gate_env.py`、`requirements/gate.lock` 和 gate evidence 明确归入 `1.Ab/1.Ac`。同时在 `PLAN.md` 写入三个配置文件的完整最小内容、编码/换行/禁止额外设置合同，并要求 Aa 完整性测试验证其原始字节。

该修订改变了选定冷启动 task 的文件边界和可执行合同，必须从新的候选文档提交创建 disposable worktree，并由全新、无历史上下文的不同类型 Agent 重跑 `T01.1/1.Aa`。当前没有 cold-start PASS，也没有正式实现授权。

## 38. 独立 worktree 冷启动完成与 CREDENTIAL_URL 边界澄清（2026-08-02）

### 38.1 独立线程结果

- **Agent:** 新线程 `019fc262-f40d-7aa2-a3a2-762b7ea9d225`，`gpt-5.6-sol`，独立 worktree `C:\Users\tongshuo\.codex\worktrees\820d\VesperCode`；初始只提供 `SPEC.md` 和 `PLAN.md`，基于候选文档提交 `55a0bebc9965b6768e57bbc1da0f35d385d293ea`。
- **执行:** Agent 创建了完整的 1.Aa Own 文件，未创建 `.venv-gate`、`requirements/gate.lock`、gate evidence、`scripts/bootstrap_gate_env.py` 或任何 1.B 文件；未提交、未合并、未联网、未调用第三方测试器。
- **验证:** Python 3.12 probe `exit=0`；首次 Aa unittest 因自身 `CREDENTIAL_URL` 正则尾部处理失败而为 `5/6`，Agent 修复后精确命令 `exit=0`，六个规范 `AaIntegrityTests` 全部通过。主 Agent 在同一 worktree 独立复跑两条命令，得到相同结果。
- **副作用:** worktree 仅留下 Own 文件及测试产生的未跟踪 `__pycache__/*.pyc`；这些 disposable 产物不进入正式成果。

### 38.2 剩余文档歧义与处理

Agent 指出 `CREDENTIAL_URL` 的通用 token-boundary 句可能被理解为要求匹配在 `@` 后立即结束，而普通 credential URL 的 hostname 会位于其后。独立审阅确认该文字歧义，但当前测试和实现的意图一致：规则只报告包含凭据的 `scheme://user:password@` 前缀，hostname/path 不进入 matched fact。已在 `PLAN.md` 明确该规则只要求 leading boundary、匹配在 `@` 结束且不要求 `@` 后 trailing boundary。

这次仅澄清了已执行合同，没有改变产品范围；为保持冷启动证据与最新文档一致，仍需从新的候选文档提交建立 disposable worktree，并由全新 Agent 重跑一次 Aa。完成前不授权正式实现。

## 39. 最终复验发现 Aa 测试代码与 runner 观测接口未完整下沉（2026-08-02）

### 39.1 最终复验线程结果

- **Agent:** 新线程 `019fc271-a273-7392-8fcf-53c52bb40cde`，`gpt-5.6-terra`，独立 worktree `C:\Users\tongshuo\.codex\worktrees\8732\VesperCode`；初始只提供最新 `SPEC.md` 和 `PLAN.md`，候选提交为 `c86d14a40ad50ea1240676ad0b7efeac6a924888`。
- **执行:** Agent 成功运行 Python 3.12 probe（`exit=0`），确认 1.Aa Own 文件在干净 worktree 中不存在；未修改文件，未运行 unittest，未进入 `1.Ab/1.Ac/1.B`，未提交或合并。
- **Finding:** PLAN 给出了六个方法名和若干首断言，但没有给出可直接复制的完整 `AaIntegrityTests` 模块；同时 `run_closed_command` 只返回 `int`，PLAN 没有明确测试如何观察其稳定 stderr 输出。继续实现会要求 Agent 猜测测试代码或额外观测接口，因此 Agent 正确暂停。

### 39.2 修订

已在 `PLAN.md` 下沉一份完整的标准库 `AaIntegrityTests` 测试模块，覆盖四个 runner 错误输出、配置原始字节、match 的 exit/stdout/空 stderr/脱敏和四类 gate-scan fail-closed 注入；并明确通过 `redirect_stdout`/`redirect_stderr` 观察现有 `run_closed_command`/`main`，不新增接口。

该修订改变了选定冷启动 task 的执行细节，必须从新的候选文档提交创建 disposable worktree，并由全新、无历史上下文的不同类型 Agent 重跑 `T01.1/1.Aa`。当前没有 cold-start PASS，也没有正式实现授权。

## 40. 最终 bounded 1.Aa 冷启动通过与文档同步（2026-08-02）

### 40.1 最终复验结果

- **Agent/session:** `gpt-5.6-luna`，线程 `019fc279-f31a-7191-8502-481960459a19`；全新、无历史上下文 session，运行于 `C:\Users\tongshuo\.codex\worktrees\e7e6\VesperCode`，候选文档提交为 `3f87813457052dc569386b9fc4b72c15468d057d`。
- **输入边界:** 初始只提供 `SPEC.md` 和 `PLAN.md`；明确要求只执行 T01.1 bounded `1.Aa`，先执行 Step 1，再运行两条精确验证命令；遇到不确定内容必须暂停，不得猜测；不得进入 `1.Ab`、`1.Ac` 或 `1.B`，不得提交或合并。
- **Agent 执行:** 按 PLAN 创建了 8 个 `1.Aa` Own 文件：`requirements/gate.in`、三个 `gates/*.ini|toml` 配置、`scripts/run_gate_checks.py`、`scripts/gate_scan.py`、`scripts/scan_gate_changed_files.ps1` 和 `tests/feasibility/gate/test_gate_bootstrap.py`。Agent 在自身实现复验中修正了配置路径和 PowerShell 错误输出中的局部问题，未提出新的 SPEC/PLAN 歧义。
- **范围边界:** 未创建 `.venv-gate`、`requirements/gate.lock`、`gates/evidence`、`scripts/bootstrap_gate_env.py` 或任何 `1.B` 文件；未访问 PyPI、未运行第三方 gate runner、未提交、未合并。

### 40.2 主 Agent 独立复验

- `python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 3)"`：退出码 `0`。
- `python -m unittest -v tests.feasibility.gate.test_gate_bootstrap.AaIntegrityTests`：6 个规范方法全部 `OK`，退出码 `0`。
- 独立检查确认冷启动 worktree 的未跟踪文件只包含上述 8 个 `1.Aa` Own 文件；复验产生的 3 个 `.pyc` 已从 disposable worktree 清理。
- 独立检查确认禁止路径全部不存在：`.venv-gate`、`requirements/gate.lock`、`gates/evidence`、`scripts/bootstrap_gate_env.py`、`spikes/win32_workspace_boundary/evaluator.py` 和对应 `1.B` 测试。

该轮视为选定 `T01.1/1.Aa` 的冷启动可执行性验证 **PASS**。Agent 在目标完成后提前结束 bounded session，未人为延长时间窗；没有未解决的关键歧义，因此不需要新的 SPEC/PLAN 修订。所有试作文件仍是 disposable 验证产物，不进入正式实现。

### 40.3 阶段切换

至此，SPEC/PLAN 的轻量文档检查、选定 task 的陌生 Agent 冷启动、冷启动反馈记录和独立复验均已完成。正式实现仍未开始；下一阶段才可按 PLAN 进入隔离 worktree、fresh subagent、TDD、SPEC 合规评审、代码质量评审和分支完成流程。

## 41. 最小流程同步修订（2026-08-02）

### 41.1 修订范围

- 根据复审结论，`SPEC.md` §7.1 删除旧的 M0 重试要求，改为记录 SPEC 变更，并仅在变更影响已选冷启动 task 时重试该 task 的冷启动。
- `PLAN.md` 规范正文删除旧的 `§11.2 item` 技术门禁归因和 `renewed admission`，并同步 Milestone 1、2、3、37 与当前 task card。
- `T01.1/1.Aa` 明确采用测试先行的 utility RED/GREEN；`1.B` 仍是第一个 Task 1 产品行为 RED。
- 冷启动目标改为选择完整 `T01.1`，`1.Aa` 仅是起始 checkpoint。第 40 节的结果保留为 bounded `1.Aa` 子范围证据，不升级为完整 `T01.1` 冷启动 PASS。
- 历史 Appendix A–D 未删除；其历史、非规范性质保持不变，以避免扩大本次最小修订范围。

### 41.2 边界与后续

- 本次只修改规格、计划和过程记录，未创建或接受任何正式实现代码、测试代码、提交、PR 或合并。
- 文档修订完成后，若要取得课程层面的 task 冷启动结论，必须从新候选文档和全新不同类型 session 重新尝试 `T01.1`，不得复用第 40 节的 bounded 结果作为完整 task 证据。

## 42. 冷启动前历史附录迁移修订（2026-08-03）

本轮复审对当前 handoff 做了最小范围收口：

- 冷启动范围统一为完整 task `T01.1`，`1.Aa` 仍只是起始 checkpoint；这一点已在 PLAN §1.2 和 T01.1 task card 中一致表达。
- `1.Aa` 已保持 test-first 的 utility RED → runner/scan GREEN 顺序；初始缺少 task-owned runner/scan 模块是预期 RED，不是成功状态。
- PLAN 中旧 admission gate、PlanAuditContractV3、前版 T37.1 和前版 T37.2 四个历史附录已从当前 handoff 移出，原文归档于 `docs/process/superseded-plan-history.md`。
- 归档内容仅用于过程历史，不属于冷启动 Agent 的输入、当前 task contract、验收标准或正式实现前置条件。
- 本轮没有修改 SPEC 的产品、接口、安全或验收语义，也没有创建或接受正式实现代码；冷启动启动仍需人工确认。

## 43. Claude Code 冷启动前确认（2026-08-03）

- **主开发 Agent：** OpenAI Codex
- **冷启动 Agent：** Claude Code
- **选定任务：** `T01.1`
- **起始 checkpoint：** `1.Aa`
- **时间限制：** 约 1—2 小时
- **试作目录：** `D:\coldstarts\VesperCode-claude-t01-1`
- **试作分支：** `coldstart/claude-t01-1-20260803`
- **试作结果：** 不得合并或作为正式任务完成证据
- **已知未解决歧义：** 无
- **人工确认：** 允许开始冷启动

## 44. CS-01 Claude Code 冷启动结果：过程有效但阻断（2026-08-03）

### 44.1 结论与范围

- **结果：** `BLOCKING`；`T01.1` 正式实现授权仍为 **NO**。
- **Agent：** Claude Code；与主开发 Agent OpenAI Codex 类型不同，使用全新 session，无历史对话或 memory；初始输入仅为 `SPEC.md` 和 `PLAN.md`。
- **任务与边界：** 选定 `T01.1`，从 `1.Aa` 开始；试作目录为 `D:\coldstarts\VesperCode-claude-t01-1`，试作分支为 `coldstart/claude-t01-1-20260803`。试作代码、提交和分支均为验证性产物，不得合并或作为正式完成证据。
- **实际进度：** `1.Aa` 完成，`1.Ab` 完成，`1.Ac` 部分完成，`1.B` 未开始。

### 44.2 实际验证结果

- Python 3.12 probe：通过。
- `1.Aa` RED/GREEN：通过。
- `resolve-lock`：首次因 Agent 自身的直接依赖名称归一化错误失败，修正后通过。
- materialize：通过。
- `1.Ac` integrity：8/8 通过。
- changed-file Gate scan：失败，20 个匹配。
- Ruff 根目录扫描：失败。
- Mypy：因 `spikes` 尚未创建而失败。
- `git diff --check`：通过。

### 44.3 阻断与非阻断发现

阻断发现如下：

1. **B1：** `AaIntegrityTests` 源码本身包含完整凭据样本，Gate scan 扫描自身会命中。
2. **B2：** `.gitignore` 为空，仓库内 `.venv-gate` 因而进入 changed-file union。
3. **B3：** Ruff 使用 `-- .`，PLAN 未明确排除 `.venv-gate`，导致扫描第三方虚拟环境文件。
4. **C1：** `1.Ac` 在 `1.B` 创建 `spikes` 前要求执行包含 `spikes` 的 Mypy 命令。
5. **C2：** PowerShell wrapper 使用 PATH Python，与后续 Gate 命令必须使用冻结 `.venv-gate` 解释器的合同冲突。

非阻断发现如下：

- Agent 曾将 direct dependency 名称归一化错误，之后已自行修正。
- Agent 曾修正 Ab/Ac 测试断言错误；这不改变上述文档阻断。

### 44.4 时间、环境与裁决

- 开始时间：`2026-08-03 11:45:33 +08:00`。
- 停止时间：`2026-08-03 15:27:36 +08:00`。
- 报告称活跃执行时间约 40 分钟；墙钟时长与活跃时间不一致，可能受到机器休眠影响，因此不宣称严格满足完整 1–2 小时时间窗。
- 环境本身没有造成此次结果的阻断；阻断来自任务合同、扫描范围和验证顺序。
- 主仓库未接受试作代码，未创建正式实现提交、合并或 PR；试作产物不复用。

### 44.5 处理决定

本次冷启动过程有效，但未通过。已据此对 `PLAN.md` 做最小合同修订：将测试凭据样本改为运行时字节拼接，令 T01.1 明确拥有 `.gitignore` 的 `.venv-gate/` 条目，给 Ruff 增加 `.venv-gate` 排除，新增只针对已存在路径的 `GATE_BOOTSTRAP_OFFLINE_V1`，将完整 `GATE_OFFLINE_V1` 延后到 `1.B` 文件存在后，并要求 wrapper 使用冻结 `.venv-gate\Scripts\python.exe`。该修订不改变 `SPEC.md` 产品语义。

下一步必须从修订后的候选文档、新的 disposable worktree 和全新无历史上下文的 Claude Code session 重新尝试 `T01.1`；在重新冷启动结果记录完成前，不得开始正式实现。

## 45. CS-02 Claude Code 冷启动结果与最小规则修订（2026-08-03）

### 45.1 试作范围与过程裁决

- **报告：** `CS-02`，任务 `T01.1`，从 `1.Aa` 开始。
- **Agent 与环境：** Claude Code；试作目录为 `D:\coldstarts\VesperCode-claude-t01-1-r2`，分支为 `coldstart/claude-t01-1-20260803-r2`；报告记录 PATH Python 3.12.4。
- **时间：** 报告记录开始 `2026-08-03T18:07:32+08:00`，停止 `2026-08-03T19:05:54+08:00`，约 59 分钟。
- **试作边界：** 无提交、无合并；试作文件、分支和 evidence 不得作为正式实现或完成证据。
- **过程结论：** `TRIAL_COMPLETE`。Agent 在出现实质性阻断后停止是允许的；这不等同于 `COLD_START_PASS`。
- **证据补充：** 报告正文没有独立列出“全新 session、无历史 memory、初始只提供 `SPEC.md`/`PLAN.md`”三项启动事实；正式过程证据应保留启动提示或 session 记录，不能只由试作结果反推。

### 45.2 实际进度与发现分级

- `1.Aa`：probe、预期 RED、GREEN 后 6/6 `AaIntegrityTests` 通过。
- `1.Ab`：lock 解析、21 条目审查通过。
- `1.Ac`：materialize、evidence、pytest、Ruff check、gate scan 和 `git diff --check` 通过；Ruff format/Mypy 未通过。
- `1.B`：预期 RED 和 Target GREEN 通过；Domain 未完成。

本次发现按新的冷启动规则分级：

1. **F1：`NON-BLOCKING`/`CLARIFY`。** Ab/Ac 测试需要规定覆盖和通过条件，但不需要把所有辅助测试源码逐行预写；Agent 可在不改变契约的前提下完成 typed/formatted 测试。
2. **F2：`BLOCKING`。** PLAN 原先要求的精确测试源码与 Ruff format closure 不相容，属于不可通过的文档组合。
3. **F3：`BLOCKING`。** 同一精确测试源码与 strict Mypy closure 不相容，属于不可通过的文档组合。
4. **F4：`BLOCKING`。** 1.B 要求六类稳定结果，但只定义了一个稳定码；Agent 不能自行发明其余公开或 task-local taxonomy。
5. **F5：`NON-BLOCKING`。** Mypy 的重复模块发现是本地模块输入选择问题，已通过唯一 Mypy 源路径规则处理。
6. **F6：`NON-BLOCKING`。** 字节码污染是运行环境实现细节；已明确直接 Python 命令和 wrapper 使用 `PYTHONDONTWRITEBYTECODE=1`。
7. **F7：`NON-BLOCKING`。** 未跟踪目录聚合是 Git 枚举实现细节；已明确使用文件级未跟踪输出并解析嵌套路径。

### 45.3 采用的最小 PLAN 修订

- 增加 `BLOCKING`、`CLARIFY`、`NON-BLOCKING` 的判定边界，以及 `TRIAL_COMPLETE`、`COLD_START_PASS`、`FORMAL_READY` 的区别。
- 保留六个 Aa 测试的精确源代码；将 Ab/Ac 改为名称、覆盖和通过条件合同，并明确添加时点。
- 修正 Aa 测试中的回调类型和 fixture 构造，使精确测试块可满足 Ruff/Mypy closure；Mypy 不再重复传入 `scripts/gate_scan.py`。
- 增加 task-local 的六行 1.B 稳定 taxonomy、固定优先级和 Domain 覆盖要求；未扩展 SPEC 的公开错误接口。
- 增加字节码防止和文件级 Git 未跟踪枚举的实现备注；这些备注不是额外审批门禁。
- 本轮未修改 `SPEC.md`，未创建、接受或合并正式实现代码。

### 45.4 下一步

CS-02 的试作记录有效，但不能作为冷启动 PASS。完成本轮文档提交后，必须由全新无历史上下文的 Claude Code session 按预先记录的 cold-start boundary 重试；在 `COLD_START_PASS` 和人工确认之前，正式实现仍禁止开始。

## 46. CS-03 Claude Code 冷启动验证完成（2026-08-03）

### 46.1 试作范围与过程裁决

- **报告：** `CS-03 Cold-Start Verification Report — T01.1, Boundary 1.Aa → 1.B Domain`。
- **Agent 与隔离环境：** Claude Code；试作目录为 `D:\coldstarts\VesperCode-claude-t01-1-r3`，分支为 `coldstart/claude-t01-1-20260803-r3`；主分支为 `main`。试作代码、分支、虚拟环境和 evidence 均为验证性产物，不得合并或作为正式任务完成证据。
- **选定范围：** `T01.1`，从 `1.Aa` 开始，声明边界为 `1.Aa → 1.B Domain`。本节只裁决该预先声明的边界，不把它升级为完成整个 T01.1 正式任务。
- **环境：** Python `3.12.4`；报告称所有验证命令均设置 `PYTHONDONTWRITEBYTECODE=1`。
- **过程结果：** 试作达到声明边界；边界裁决为 `COLD_START_PASS`。主仓库未接受试作代码，未创建正式实现提交、PR 或合并。

### 46.2 边界验证结果

- Python 3.12 probe：退出码 `0`。
- `AaIntegrityTests`：`6/6` 通过。
- 1.Ac integrity：`8/8` 通过。
- Ruff format、Ruff check、Mypy：均退出码 `0`；Mypy 使用 PLAN 规定的 `.venv-gate` runner 命令，检查 `tests/feasibility/gate` 和 `scripts/bootstrap_gate_env.py`，无重复传入 `scripts/gate_scan.py`。
- Gate scan：退出码 `0`，stdout/stderr 为空，凭据匹配数为 `0`。
- `git diff --check`：退出码 `0`；报告中的 LF/CRLF 提示不构成失败。
- 1.B Target：`1/1` 通过。
- 1.B Domain：`3/3` 通过，覆盖六项 task-local taxonomy 和 combined-observation precedence。
- `requirements/gate.lock`：20 条 hash-locked 条目，包含 5 个直接依赖；报告记录的 lock digest 与 evidence 一致。
- 清理后，试作目录中没有项目树 `.pyc` 或 `__pycache__`；`.venv-gate` 内部缓存属于隔离环境，不进入 changed-file union。

主 Agent 对试作目录做了只读复核：`.gitignore` 的 `.venv-gate/` 条目存在，lock/evidence 文件存在，Git 状态仅包含本次试作的预期文件集合；未发现正式仓库被修改。

### 46.3 Findings 与处理

1. **F1：`NON-BLOCKING`。** `scripts/__init__.py`、`tests/__init__.py`、`tests/feasibility/__init__.py` 和 `tests/feasibility/gate/__init__.py` 为 0 字节包发现辅助文件。它们未导出接口、未添加行为、未改变安全边界。它们不是正式完成证据；正式任务仍以 T01.1 声明的文件所有权和提交范围为准。
2. **F2：`NON-BLOCKING`。** `git diff --check` 报告的 LF/CRLF advisory 是 Windows Git 换行配置提示，命令退出码为 `0`，不构成任务阻断。

本轮没有发现 `BLOCKING` 或 `CLARIFY` finding；没有改变 SPEC 的产品语义，也没有需要同步到 PLAN 的行为、接口、依赖、验证命令或完成条件变更。

### 46.4 启动证据与阶段切换

- §43 已记录主开发 Agent、冷启动 Agent、任务、起始 checkpoint、试作目录/分支、禁止合并和人工允许启动等 pre-flight 信息。
- CS-03 收尾报告本身主要记录验证结果，没有重复附上完整启动提示、session/memory 状态和初始输入 transcript。正式过程归档时仍应保留该启动记录，以证明“全新 session、无历史 memory、初始仅提供 `SPEC.md`/`PLAN.md`”，不能仅由测试结果反推。
- 当前阶段裁决为：选定冷启动边界已通过；`FORMAL_READY` 尚未确认。正式实现仍需人工明确确认，之后才可进入正式 worktree、fresh subagent、TDD、两阶段评审和分支完成流程。

### 46.5 CS-03 启动证据

- **Session:** `6aeab697-6b09-4e05-afdc-8ab0199e5086`；Claude Code `2.1.220`；启动时间 `2026-08-03T12:11:53.656Z`（本地时间 `2026-08-03 20:11:53 CST`）。
- **运行身份：** PID `21356`；工作目录 `D:\coldstarts\VesperCode-claude-t01-1-r3`；分支 `coldstart/claude-t01-1-20260803-r3`。
- **新 session：** 是；session metadata 与 transcript 首条用户消息均被列为证据来源。
- **历史上下文与 memory：** transcript 首条用户消息明确声明未提供 prior conversation 或 memory。
- **初始项目输入：** transcript 首条用户消息明确声明初始 planning inputs 仅为当前 `SPEC.md` 和 `PLAN.md`。
- **任务与边界：** `T01.1`，从 `1.Aa` 开始，边界为 `1.Aa → 1.B Domain`。
- **不确定性规则：** transcript 首条用户消息要求遇到 material behavior、safety rule、interface、stable taxonomy、command 或 completion condition 不清楚/矛盾时暂停提问，不得猜测。
- **证据来源：** `C:\Users\tongshuo\.claude\sessions\21356.json`；`C:\Users\tongshuo\.claude\projects\D--coldstarts-VesperCode-claude-t01-1-r3\6aeab697-6b09-4e05-afdc-8ab0199e5086.jsonl`。本仓库只记录元数据和关键事实，不复制完整 transcript。
- **证据性质：** 这是 CS-03 启动过程的可追溯记录，不是产品实现或测试证据；试作代码、提交、分支和环境仍不得合并或作为正式任务完成证据。
