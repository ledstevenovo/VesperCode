# SPEC v3 冷启动门禁修正与权威文件升格执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:using-git-worktrees` before execution, then use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正 `SPEC_v3.md` 的冷启动门禁和机制演示语义，并在逐字节保留旧规格的前提下，把修正后的 v3 升格为根目录唯一权威 `SPEC.md`。

**Architecture:** 两个任务严格顺序执行。Task 1 只修改 v3 中两处既有合同，并以文档断言和只读审查闭合语义；Task 2 不改正文，只用可逆 Git 移动完成旧版归档和 v3 升格，并以 Git blob 身份证明内容没有错配。

**Tech Stack:** Markdown、Git、PowerShell、`rg`、Superpowers worktree/review workflow。

## Global Constraints

- 本计划是文档修订计划，不是课程权威 `PLAN.md`，也不授权任何产品实现代码、实现测试、CI、发行或部署工作。
- 执行必须发生在独立 worktree；建议分支为 `codex/spec-v3-canonical-promotion`，建议 worktree 为 `D:\code\VesperCode\.worktrees\spec-v3-canonical-promotion`。
- 规划时基线为 `HEAD=83c5e29d5e8cfc70b63caee2fd8958c3e50c31d9`：
  - 旧 `SPEC.md` blob：`7568652e6b572c97677730650e6648edd6b55c14`；
  - `SPEC_v3.md` blob：`21bf737962a70ae677c290bd8d0ec050d55c9d67`；
  - `SPEC_legacy.md` 不存在。
- 创建 worktree 前必须重新核对以上内容身份。若任一 blob 已变化，停止执行并重新审阅差异；不得覆盖、回滚或假定新内容等价。
- 根 worktree 当前未跟踪的 `.gitignore`、`AGENTS.md`、`PLAN.md`、`REFLECTION.md`、`SPEC_v2.md` 属于用户现有文件。本计划不得复制、修改、暂存或提交这些文件。
- Task 1 只允许修改 `SPEC_v3.md`。Task 2 只允许改变 `SPEC.md`、`SPEC_v3.md`、`SPEC_legacy.md` 三个路径。
- `SPEC_legacy.md` 必须与执行 Task 2 前的旧 `SPEC.md` blob 完全相同；不得添加“已归档”标题、注释或任何换行改动。
- Task 2 完成后不得保留 `SPEC_v3.md` 路径；修正后的 v3 内容只能位于根目录 `SPEC.md`。
- 不使用 `git add -A`、`git add .`、`git reset --hard`、`git checkout --` 或批量删除命令。
- `README.md`、`PLAN.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md` 和 `TASK_HANDOFF.md` 的同步属于后续步骤，不在本计划中修改。Task 2 结束后分支保持未合并状态，等待后续同步计划继续工作。
- 两个任务各自形成一个提交。Task 1 未通过审查不得开始 Task 2。

---

### Task 1: 闭合冷启动门禁与 Demo 拒绝语义

**Files:**

- Modify: `SPEC_v3.md:3-4`
- Modify: `SPEC_v3.md:2043-2048`
- Test: PowerShell 文档合同断言，不新增测试文件

**Interfaces:**

- Consumes:
  - `SPEC_v3.md` blob `21bf737962a70ae677c290bd8d0ec050d55c9d67`；
  - §4.2.5 已冻结的处理顺序：Schema → 候选绑定 → 路径 → phase → policy → dispatch；
  - §4.3/§4.4/AC-31 已冻结的 `docs/** → DENY + PATCH_PATH_NOT_EDITABLE` 合同。
- Produces:
  - 明确禁止在精确 SPEC/PLAN 对获批并通过异构冷启动前开始正式实现的状态声明；
  - 唯一可执行的机制演示：使用结构合法、路径规范但越出 editable root 的 patch 进入 `PolicyEngine`，得到 `DENY` 和 `PATCH_PATH_NOT_EDITABLE`；
  - 供 Task 2 升格的已审查 `SPEC_v3.md` commit。

- [ ] **Step 1: 用 Superpowers 建立隔离执行现场**

使用 `superpowers:using-git-worktrees` 检查 `.worktrees` ignore 状态，从规划基线创建：

```powershell
git worktree add 'D:\code\VesperCode\.worktrees\spec-v3-canonical-promotion' -b 'codex/spec-v3-canonical-promotion' 83c5e29d5e8cfc70b63caee2fd8958c3e50c31d9
```

进入新 worktree 后运行：

```powershell
git status --short
git rev-parse HEAD
git hash-object -- SPEC.md
git hash-object -- SPEC_v3.md
if (Test-Path -LiteralPath 'SPEC_legacy.md') { throw 'SPEC_LEGACY_ALREADY_EXISTS' }
```

Expected:

- `git status --short` 无输出；
- `HEAD` 为 `83c5e29d5e8cfc70b63caee2fd8958c3e50c31d9`；
- 两个 blob 依次为 `7568652e6b572c97677730650e6648edd6b55c14` 和 `21bf737962a70ae677c290bd8d0ec050d55c9d67`；
- `SPEC_legacy.md` 不存在。

- [ ] **Step 2: 运行冷启动门禁与 Demo 合同的 RED 断言**

```powershell
$text = Get-Content -LiteralPath 'SPEC_v3.md' -Raw
$required = @(
  '除课程要求的隔离、可丢弃且不得合入的冷启动试作外',
  '不得开始或继续正式实现、CI、发行或部署',
  'docs/outside-scope.md',
  '稳定错误码为 `PATCH_PATH_NOT_EDITABLE`',
  '工具分发和 Candidate 发布次数均为零'
)
$missing = @($required | Where-Object { -not $text.Contains($_) })
if ($missing.Count -gt 0) {
  throw ('EXPECTED_RED_MISSING=' + ($missing -join '|'))
}
```

Expected: nonzero，错误以 `EXPECTED_RED_MISSING=` 开头，证明当前文档尚未包含目标合同。

- [ ] **Step 3: 最小修改状态声明**

用 `apply_patch` 将当前状态行：

```markdown
> 状态：SPEC v3 冻结稿，等待 PLAN 与陌生智能体冷启动验证。完成冷启动试验和本文 §10 的验证证据前，不得宣称实现完成。
```

精确替换为：

```markdown
> 状态：SPEC v3 冻结候选，等待与其内容寻址绑定的 `PLAN.md` 获批，并完成不同 Agent 类型、无先前对话或记忆上下文的冷启动试验。除课程要求的隔离、可丢弃且不得合入的冷启动试作外，在该精确 SPEC/PLAN 对获批并通过冷启动门禁前，不得开始或继续正式实现、CI、发行或部署；§10 的实现与发布证据只能在门禁通过后生成，不能替代该门禁。
```

该修改必须同时表达：

- 冷启动绑定精确 SPEC/PLAN 对；
- agent 类型不同且无历史对话或记忆；
- 只有隔离、可丢弃、不得合入的课程冷启动试作例外；
- 正式实现和发布活动在门禁前全部禁止；
- §10 证据不能反向替代门禁。

- [ ] **Step 4: 最小修改机制演示第 1 项**

用 `apply_patch` 将：

```markdown
1. Mock LLM 提出读取工作区外路径，治理护栏返回 `DENY`；
```

精确替换为：

```markdown
1. Mock LLM 提交结构合法、路径规范但尝试创建 `docs/outside-scope.md` 的 `ApplyCandidatePatchAction`；路径校验通过后，`PolicyEngine` 返回 `DENY`，稳定错误码为 `PATCH_PATH_NOT_EDITABLE`，并断言工具分发和 Candidate 发布次数均为零；
```

不要修改机制演示第 2—6 项。新用例必须复用既有 `docs/**` editable-policy 合同，不新增动作、错误码、状态或路径类别。

- [ ] **Step 5: 重跑同一合同断言并验证旧歧义消失**

```powershell
$text = Get-Content -LiteralPath 'SPEC_v3.md' -Raw
$required = @(
  '除课程要求的隔离、可丢弃且不得合入的冷启动试作外',
  '不得开始或继续正式实现、CI、发行或部署',
  'docs/outside-scope.md',
  '`PolicyEngine` 返回 `DENY`',
  '稳定错误码为 `PATCH_PATH_NOT_EDITABLE`',
  '工具分发和 Candidate 发布次数均为零'
)
$missing = @($required | Where-Object { -not $text.Contains($_) })
if ($missing.Count -gt 0) { throw ('CONTRACT_MISSING=' + ($missing -join '|')) }
$forbidden = @(
  '完成冷启动试验和本文 §10 的验证证据前，不得宣称实现完成',
  'Mock LLM 提出读取工作区外路径，治理护栏返回 `DENY`'
)
$residual = @($forbidden | Where-Object { $text.Contains($_) })
if ($residual.Count -gt 0) { throw ('OLD_CONTRACT_REMAINS=' + ($residual -join '|')) }
Write-Output 'SPEC_V3_TARGETED_CONTRACTS_OK'
```

Expected: exit 0，输出 `SPEC_V3_TARGETED_CONTRACTS_OK`。

- [ ] **Step 6: 复核邻接治理合同没有被重开**

```powershell
rg -n "动作依次经过 Schema|PATCH_PATH_NOT_EDITABLE|docs/outside-scope|README\\.md|PolicyEngine.*DENY" SPEC_v3.md
```

人工逐条确认：

- §4.2.5 仍规定 policy 在 dispatch 前；
- §4.3 仍规定 `docs/**` 返回 `PATCH_PATH_NOT_EDITABLE`；
- §4.4 仍规定 editable root 越界为不可覆盖的 `DENY`；
- AC-31 仍覆盖 `docs/**` 硬拒绝；
- §10.4 第 1 项不再要求无效路径先产生 `PolicyDecision.DENY`；
- 未新增 `RunStatus`、`RunPhase`、动作类型、错误码或 editable root。

- [ ] **Step 7: 运行文档结构和空白验证**

```powershell
$text = Get-Content -LiteralPath 'SPEC_v3.md' -Raw
$headingIds = [regex]::Matches($text, '(?m)^#{1,6}\s+(\d+(?:\.\d+)*)\b') |
  ForEach-Object { $_.Groups[1].Value } |
  Sort-Object -Unique
$refs = [regex]::Matches($text, '§(\d+(?:\.\d+)*)') |
  ForEach-Object { $_.Groups[1].Value } |
  Sort-Object -Unique
$missingRefs = @($refs | Where-Object { $_ -notin $headingIds })
if ($missingRefs.Count -gt 0) { throw ('MISSING_SECTION_REFS=' + ($missingRefs -join ',')) }
$acDefs = @([regex]::Matches($text, '\*\*AC-(\d{2})：\*\*') |
  ForEach-Object { [int]$_.Groups[1].Value })
$missingAc = @(1..31 | Where-Object { $_ -notin $acDefs })
$duplicateAc = @($acDefs | Group-Object | Where-Object Count -gt 1)
if ($missingAc.Count -gt 0) { throw ('MISSING_AC=' + ($missingAc -join ',')) }
if ($duplicateAc.Count -gt 0) { throw 'DUPLICATE_AC' }
Write-Output 'SPEC_STRUCTURE_OK'
git diff --check -- SPEC_v3.md
```

Expected:

- 输出 `SPEC_STRUCTURE_OK`；
- `git diff --check -- SPEC_v3.md` exit 0；
- 章节引用无缺失，AC-01—AC-31 连续且唯一。

- [ ] **Step 8: 运行窄范围凭据和占位符扫描**

```powershell
$placeholderMatches = rg -n -i "TODO|TBD|FIXME|PLACEHOLDER|待定|待补|待填写|尚未定义|<待" SPEC_v3.md
if ($LASTEXITCODE -eq 0) { throw ('PLACEHOLDER_FOUND=' + ($placeholderMatches -join '|')) }
if ($LASTEXITCODE -ne 1) { throw 'PLACEHOLDER_SCAN_FAILED' }
$secretMatches = rg -n -i "sk-[A-Za-z0-9_-]{16,}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY" SPEC_v3.md
if ($LASTEXITCODE -eq 0) { throw ('CREDENTIAL_PATTERN_FOUND=' + ($secretMatches -join '|')) }
if ($LASTEXITCODE -ne 1) { throw 'CREDENTIAL_SCAN_FAILED' }
Write-Output 'SPEC_CONTENT_SCAN_OK'
```

Expected: exit 0，输出 `SPEC_CONTENT_SCAN_OK`。

- [ ] **Step 9: 请求一次独立只读合同审查**

审查代理只读取：

- 当前 `SPEC_v3.md`；
- `AI4SE_Final_Project_通用要求.md:88-140`；
- `AI4SE_Final_Project_A_Coding_Agent_Harness(1).md:26-87`；
- 本计划 Task 1。

完整审查提示：

```text
只读审查，不修改文件。检查两项：
1. 状态声明是否明确禁止在精确 SPEC/PLAN 对获批且通过不同 Agent 类型、无历史上下文冷启动前开始正式实现，同时只为不可合入的隔离冷启动试作保留例外；
2. §10.4 第 1 项是否能按现有 Schema→路径→policy→dispatch 顺序执行，并与 §4.3、§4.4、AC-31 的 docs/** → DENY + PATCH_PATH_NOT_EDITABLE 合同一致。
同时检查是否误增动作、错误码、状态、editable root 或新验收维度。
输出严格为 PASS，或 FAIL 加逐项文件行号、反例和最小修正。
```

Expected: `PASS`。若为 `FAIL`，只处理有具体反例的既有合同问题，修复后重跑 Steps 5—9。

- [ ] **Step 10: 仅暂存并提交 Task 1**

```powershell
git add -- SPEC_v3.md
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 1 -or $staged[0] -ne 'SPEC_v3.md') {
  throw ('UNEXPECTED_STAGED_PATHS=' + ($staged -join ','))
}
git diff --cached --check
git diff --cached -- SPEC_v3.md
git commit -m "docs(spec): clarify cold-start and demo contracts"
```

Expected:

- 暂存区只有 `SPEC_v3.md`；
- staged diff 只有两处目标修改；
- commit 成功；
- commit 后 `git status --short` 无输出。

---

### Task 2: 逐字节归档旧 SPEC 并升格修正后的 v3

**Files:**

- Move without content change: `SPEC.md` → `SPEC_legacy.md`
- Move without content change: `SPEC_v3.md` → `SPEC.md`
- Test: Git blob 身份、路径集合和文档结构断言，不新增测试文件

**Interfaces:**

- Consumes:
  - Task 1 的已审查 commit；
  - Task 1 commit 中的 `HEAD:SPEC.md` 旧版 blob；
  - Task 1 commit 中的 `HEAD:SPEC_v3.md` 修正后 v3 blob。
- Produces:
  - 根目录 `SPEC.md`：内容精确等于 Task 1 commit 的 `SPEC_v3.md`；
  - 根目录 `SPEC_legacy.md`：内容精确等于 Task 1 commit 的旧 `SPEC.md`；
  - 不再存在 `SPEC_v3.md`；
  - 一个只包含三条 SPEC 路径变化的 promotion commit。

- [ ] **Step 1: 验证 Task 1 交付和 Task 2 前置条件**

```powershell
git status --short
$expectedLegacy = git rev-parse HEAD:SPEC.md
$expectedCanonical = git rev-parse HEAD:SPEC_v3.md
if ($expectedLegacy -ne '7568652e6b572c97677730650e6648edd6b55c14') {
  throw ('LEGACY_SOURCE_CHANGED=' + $expectedLegacy)
}
if (-not (Test-Path -LiteralPath 'SPEC.md')) { throw 'SPEC_SOURCE_MISSING' }
if (-not (Test-Path -LiteralPath 'SPEC_v3.md')) { throw 'SPEC_V3_SOURCE_MISSING' }
if (Test-Path -LiteralPath 'SPEC_legacy.md') { throw 'SPEC_LEGACY_TARGET_EXISTS' }
$v3Text = Get-Content -LiteralPath 'SPEC_v3.md' -Raw
if (-not $v3Text.Contains('除课程要求的隔离、可丢弃且不得合入的冷启动试作外')) {
  throw 'TASK1_STATUS_CONTRACT_MISSING'
}
if (-not $v3Text.Contains('docs/outside-scope.md')) {
  throw 'TASK1_DEMO_CONTRACT_MISSING'
}
Write-Output ('EXPECTED_LEGACY_BLOB=' + $expectedLegacy)
Write-Output ('EXPECTED_CANONICAL_BLOB=' + $expectedCanonical)
```

Expected:

- `git status --short` 无输出；
- legacy blob 仍为 `7568652e6b572c97677730650e6648edd6b55c14`；
- v3 blob 为 Task 1 commit 生成的新值；
- Task 1 两项合同存在；
- `SPEC_legacy.md` 不存在。

- [ ] **Step 2: 运行 canonical 文件布局的 RED 断言**

```powershell
$failures = @()
if (-not (Test-Path -LiteralPath 'SPEC_legacy.md')) { $failures += 'SPEC_LEGACY_MISSING' }
if (Test-Path -LiteralPath 'SPEC_v3.md') { $failures += 'SPEC_V3_STILL_PRESENT' }
$canonicalText = Get-Content -LiteralPath 'SPEC.md' -Raw
if (-not $canonicalText.Contains('> 版本：SPEC v3')) { $failures += 'SPEC_MD_NOT_V3' }
if ($failures.Count -gt 0) { throw ('EXPECTED_RED=' + ($failures -join '|')) }
```

Expected: nonzero，至少包含 `SPEC_LEGACY_MISSING`、`SPEC_V3_STILL_PRESENT` 和 `SPEC_MD_NOT_V3`。

- [ ] **Step 3: 按可逆顺序执行两个 Git 移动**

```powershell
git mv -- SPEC.md SPEC_legacy.md
git mv -- SPEC_v3.md SPEC.md
```

不要在两个命令之间编辑任何文件。若第二个命令失败，立即运行：

```powershell
git mv -- SPEC_legacy.md SPEC.md
```

Expected: 两个移动都成功，工作树存在 `SPEC.md` 和 `SPEC_legacy.md`，不再存在 `SPEC_v3.md`。

- [ ] **Step 4: 用 Task 1 commit 的树对象验证内容身份**

```powershell
$expectedLegacy = git rev-parse HEAD:SPEC.md
$expectedCanonical = git rev-parse HEAD:SPEC_v3.md
$actualLegacy = git hash-object -- SPEC_legacy.md
$actualCanonical = git hash-object -- SPEC.md
if ($actualLegacy -ne $expectedLegacy) {
  throw ("LEGACY_BLOB_MISMATCH expected=$expectedLegacy actual=$actualLegacy")
}
if ($actualCanonical -ne $expectedCanonical) {
  throw ("CANONICAL_BLOB_MISMATCH expected=$expectedCanonical actual=$actualCanonical")
}
if (Test-Path -LiteralPath 'SPEC_v3.md') { throw 'SPEC_V3_PATH_REMAINS' }
Write-Output 'SPEC_PROMOTION_BLOBS_OK'
```

Expected: exit 0，输出 `SPEC_PROMOTION_BLOBS_OK`。这一步是归档和升格正确性的权威判定，不依赖 Git 是否把 staged diff 显示成 rename。

若任一 blob 不匹配，不得继续编辑或提交。按以下顺序恢复路径：

```powershell
git mv -- SPEC.md SPEC_v3.md
git mv -- SPEC_legacy.md SPEC.md
```

恢复后重新核查原因；不得用 checkout/reset 覆盖内容。

- [ ] **Step 5: 重跑 canonical 文件布局的 GREEN 断言**

```powershell
$failures = @()
if (-not (Test-Path -LiteralPath 'SPEC.md')) { $failures += 'SPEC_MD_MISSING' }
if (-not (Test-Path -LiteralPath 'SPEC_legacy.md')) { $failures += 'SPEC_LEGACY_MISSING' }
if (Test-Path -LiteralPath 'SPEC_v3.md') { $failures += 'SPEC_V3_STILL_PRESENT' }
$canonicalText = Get-Content -LiteralPath 'SPEC.md' -Raw
if (-not $canonicalText.Contains('> 版本：SPEC v3')) { $failures += 'SPEC_MD_NOT_V3' }
if (-not $canonicalText.Contains('除课程要求的隔离、可丢弃且不得合入的冷启动试作外')) {
  $failures += 'SPEC_MD_MISSING_COLD_START_GATE'
}
if (-not $canonicalText.Contains('docs/outside-scope.md')) {
  $failures += 'SPEC_MD_MISSING_DEMO_FIX'
}
if ($failures.Count -gt 0) { throw ('PROMOTION_FAILED=' + ($failures -join '|')) }
Write-Output 'SPEC_CANONICAL_LAYOUT_OK'
```

Expected: exit 0，输出 `SPEC_CANONICAL_LAYOUT_OK`。

- [ ] **Step 6: 在新 canonical 路径重跑结构验证**

```powershell
$text = Get-Content -LiteralPath 'SPEC.md' -Raw
$headingIds = [regex]::Matches($text, '(?m)^#{1,6}\s+(\d+(?:\.\d+)*)\b') |
  ForEach-Object { $_.Groups[1].Value } |
  Sort-Object -Unique
$refs = [regex]::Matches($text, '§(\d+(?:\.\d+)*)') |
  ForEach-Object { $_.Groups[1].Value } |
  Sort-Object -Unique
$missingRefs = @($refs | Where-Object { $_ -notin $headingIds })
if ($missingRefs.Count -gt 0) { throw ('MISSING_SECTION_REFS=' + ($missingRefs -join ',')) }
$acDefs = @([regex]::Matches($text, '\*\*AC-(\d{2})：\*\*') |
  ForEach-Object { [int]$_.Groups[1].Value })
$missingAc = @(1..31 | Where-Object { $_ -notin $acDefs })
$duplicateAc = @($acDefs | Group-Object | Where-Object Count -gt 1)
if ($missingAc.Count -gt 0) { throw ('MISSING_AC=' + ($missingAc -join ',')) }
if ($duplicateAc.Count -gt 0) { throw 'DUPLICATE_AC' }
Write-Output 'CANONICAL_SPEC_STRUCTURE_OK'
git diff --cached --check
```

Expected:

- 输出 `CANONICAL_SPEC_STRUCTURE_OK`；
- AC-01—AC-31 连续且唯一；
- 所有 `§` 引用均解析到现有标题；
- staged diff 无空白错误。

- [ ] **Step 7: 验证暂存范围精确**

`git mv` 会自动暂存路径变化。运行：

```powershell
$actual = @(git diff --cached --no-renames --name-only | Sort-Object)
$expected = @('SPEC.md', 'SPEC_legacy.md', 'SPEC_v3.md') | Sort-Object
$delta = @(Compare-Object -ReferenceObject $expected -DifferenceObject $actual)
if ($delta.Count -gt 0) {
  throw ('UNEXPECTED_STAGED_PATHS=' + (($delta | ForEach-Object { $_.InputObject + ':' + $_.SideIndicator }) -join ','))
}
git diff --cached --check
git diff --cached --stat
git diff --cached --find-renames --summary
```

Expected:

- staged path 集合精确为 `SPEC.md`、`SPEC_legacy.md`、`SPEC_v3.md`；
- 无 README、PLAN、日志或根 worktree 未跟踪文件；
- diff check exit 0。

Git 的 rename 展示只是辅助证据；Step 4 的 blob 等式才是内容身份的权威证据。

- [ ] **Step 8: 请求一次独立只读 promotion 审查**

审查代理只读取 staged diff、本计划 Task 2 和下列命令输出：

```powershell
git diff --cached --name-status
git diff --cached --find-renames --summary
git rev-parse HEAD:SPEC.md
git rev-parse HEAD:SPEC_v3.md
git hash-object -- SPEC_legacy.md
git hash-object -- SPEC.md
```

完整审查提示：

```text
只读审查，不修改文件。确认：
1. SPEC_legacy.md 与 Task 2 前 HEAD:SPEC.md blob 完全相同；
2. 新 SPEC.md 与 Task 2 前 HEAD:SPEC_v3.md blob 完全相同；
3. SPEC_v3.md 路径被移除；
4. staged path 只有 SPEC.md、SPEC_legacy.md、SPEC_v3.md；
5. 没有把 README/PLAN/日志同步或任何实现工作混入本任务。
输出严格为 PASS，或 FAIL 加命令证据和最小恢复步骤。
```

Expected: `PASS`。若为 `FAIL`，先恢复到 Task 2 前路径布局，再调查；不得通过修改 legacy 正文消除差异。

- [ ] **Step 9: 提交 promotion**

```powershell
git diff --cached --check
git commit -m "docs(spec): promote v3 as canonical specification"
```

Expected: commit 成功，提交只涉及三条 SPEC 路径。

- [ ] **Step 10: 验证提交后的跨 commit blob 传承**

```powershell
$legacy = git rev-parse HEAD:SPEC_legacy.md
$canonical = git rev-parse HEAD:SPEC.md
$priorLegacy = git rev-parse HEAD^:SPEC.md
$priorCandidate = git rev-parse HEAD^:SPEC_v3.md
if ($legacy -ne $priorLegacy) {
  throw ("POST_COMMIT_LEGACY_MISMATCH expected=$priorLegacy actual=$legacy")
}
if ($canonical -ne $priorCandidate) {
  throw ("POST_COMMIT_CANONICAL_MISMATCH expected=$priorCandidate actual=$canonical")
}
git cat-file -e HEAD:SPEC_v3.md 2>$null
if ($LASTEXITCODE -eq 0) { throw 'POST_COMMIT_SPEC_V3_PATH_REMAINS' }
if ($LASTEXITCODE -ne 128) { throw ('UNEXPECTED_CAT_FILE_STATUS=' + $LASTEXITCODE) }
git status --short
Write-Output 'SPEC_PROMOTION_COMMIT_OK'
```

Expected:

- legacy blob 等于 Task 1 commit 的旧 `SPEC.md`；
- canonical blob 等于 Task 1 commit 的修正后 `SPEC_v3.md`；
- `HEAD:SPEC_v3.md` 不存在；
- `git status --short` 无输出；
- 输出 `SPEC_PROMOTION_COMMIT_OK`。

- [ ] **Step 11: 停在后续文档同步检查点**

记录但暂不写入仓库：

- Task 1 commit SHA；
- Task 2 commit SHA；
- 旧 SPEC blob；
- 修正后 canonical SPEC blob；
- 两次只读 reviewer 结果；
- Task 1/2 全部验证输出。

不要 merge、push 或创建最终 PR。保留 `codex/spec-v3-canonical-promotion` worktree/分支，交给后续“按 v3 重写课程 `PLAN.md`、执行冷启动、同步 README/过程日志”的计划继续使用。

## Final Completion Condition

本计划只有在以下条件全部满足时完成：

1. Task 1 和 Task 2 各有一个独立提交；
2. 新 `SPEC.md` 包含修正后的冷启动门禁和可执行 Demo `DENY` 用例；
3. `SPEC_legacy.md` blob 精确等于规划时旧 `SPEC.md` blob `7568652e6b572c97677730650e6648edd6b55c14`；
4. 新 `SPEC.md` blob 精确等于 Task 1 commit 中 `SPEC_v3.md` 的 blob；
5. `SPEC_v3.md` 路径不存在；
6. AC-01—AC-31、全部章节引用、占位符扫描、凭据模式扫描和 `git diff --check` 均通过；
7. 两次只读审查均为 PASS；
8. 根 worktree 的 `.gitignore`、`AGENTS.md`、`PLAN.md`、`REFLECTION.md`、`SPEC_v2.md` 没有被修改、暂存或提交；
9. 没有开始产品实现，没有修改后续同步范围内的 README、PLAN、过程日志或 handoff；
10. 分支保持未合并、未推送，等待后续步骤继续闭合完整交付链。
