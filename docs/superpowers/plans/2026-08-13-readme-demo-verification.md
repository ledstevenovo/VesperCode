# README 公网 Demo 验证指南实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 README 前部用中文提供可直接访问的项目链接、作品形态说明和完整公网 Demo 验证流程。

**Architecture:** 仅修改 `README.md` 的信息架构，在“当前状态”之后插入两个独立章节。复用已经通过 T37 验证的链接、状态词和健康检查结果，不改动后续安装、分发、限制或 Web UI 章节。

**Tech Stack:** Markdown、现有只读 README 合同验证器、凭据扫描器、Git diff 检查。

---

### Task 1: 补充中文项目链接与公网 Demo 验证流程

**Files:**
- Modify: `README.md`（在 `## 当前状态` 后插入）
- Verify: `scripts/verify_readme_contract.py`

- [ ] **Step 1: 记录修改前缺失基线**

Run:

```powershell
rg -n "^## 项目链接$|^## 公网 Demo 验证流程$" README.md
```

Expected: 无匹配，证明两个面向验收的章节尚未存在。

- [ ] **Step 2: 插入最小中文文档内容**

在 `## 当前状态` 的三条状态之后插入：

```markdown
## 项目链接

- **GitHub 源码仓库**：...
- **v0.1.0 Release**：...
- **公网 Demo**：...
- **健康检查**：...
- **最终 main CI**：...

## 公网 Demo 验证流程

> 作品主体是面向 Windows 本地 Git 仓库运行的 Coding Agent Harness；Render 站点只是无凭据、无真实仓库访问能力的固定模拟验收界面。

1. 打开公网 Demo，确认 `SIMULATION` 标识与输入安全边界。
2. 启动新会话。
3. 依次执行固定步骤并核对 `DENIED`、`DENIED`、`CHECK_FAILED`、`DENIED`。
4. 进入 `DEMO_WAITING_USER`，先拒绝并观察 `REJECTED`。
5. 再批准并观察 `COMPLETED`、`DEMO_COMPLETED` 与终态按钮禁用。
6. 打开 `/healthz`，核对 HTTP 200 与精确 simulation JSON。
```

同时写明 Render Free 空闲休眠可能导致首次访问等待 50 秒以上。

- [ ] **Step 3: 验证 README 合同与精确状态词**

Run:

```powershell
D:\code\VesperCode\.venv-formal\Scripts\python.exe scripts\verify_readme_contract.py README.md
rg -n "DENIED|CHECK_FAILED|DEMO_WAITING_USER|REJECTED|COMPLETED|DEMO_COMPLETED" README.md
```

Expected: README contract `ACCEPTED`；所有固定状态词均存在。

- [ ] **Step 4: 验证安全与 diff 范围**

Run:

```powershell
D:\code\VesperCode\.venv-formal\Scripts\python.exe scripts\scan_credentials.py --changed --redact --fail-on-match
git diff --check
git diff -- README.md
```

Expected: 凭据扫描 exit 0、diff check 无输出、README diff 只增加两个中文章节。

- [ ] **Step 5: 提交文档实现**

```powershell
git add -- README.md docs/superpowers/plans/2026-08-13-readme-demo-verification.md
git commit -m "docs(readme): add public demo verification guide"
```

Expected: 仅 README 和本实施计划进入实现提交；设计说明保留在前一提交中。
