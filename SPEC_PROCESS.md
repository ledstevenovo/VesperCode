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
3. **仅保留历史或未来增强说明：** Stage2 多 generation、恢复响应、persistent processing block、claim takeover、response reconciliation 和多层 cleanup reconciliation 只在 3.5.38 明确非目标或本过程文档的历史记录中出现；`RecoveryDisposition` 只保留 3.10 持久化专用三结果语义。

旧 9.13—9.18、9.23、9.25 等记录中的 `MaterializationJob`、`ExecutionWorkspaceLifecycle`、cleanup attempt、generation、gate、claim、reconciliation、Stage2 等术语是当时讨论与审查轨迹，保留原文用于证明迭代过程。它们在 `SPEC_PROCESS.md` 中出现不构成当前规范对象、实现义务或 v1 验收条件。

### 10.5 证据边界

本轮范围收敛的前序步骤实际重写、审查并提交了 3.1—3.4，对应提交为 `856a8f0`、`0e6845c`、`2864a53`，并可引用 checkpoint `3640de6`；进入本步骤的 3.5 机械引用迁移时，3.1—3.4 才已经冻结，本步骤未再修改其正文。本节不宣称尚未发生的新冷启动审查、PR、实现验证或最终 SPEC／PLAN 批准，也不把此前历史讨论改写成当前规范；这些后续事项仍须按各自真实发生的证据另行记录，且不得为本步骤虚构新的提交哈希。
