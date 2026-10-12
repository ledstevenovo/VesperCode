# zcode/new-ui 修复轮 v2 交付报告（FIX_REPORT）

- 分支：`zcode/new-ui`；基线 HEAD：`7221af5208e828b991360ec77d9d78af729c456d`（= 评审被测提交）
- 解释器：`.\.venv-formal\Scripts\python.exe`（Python 3.12.14，Windows / PowerShell）
- 轮次：round-2（T0 基线 → T1..T4 实现 → T5/T6 独立复核 → T7 总验收与交付）
- 本轮结论：**四项缺陷（P0-1 / P0-2 / P1-1 / P1-2）全部修复并红转绿；无新增红；决策 A（10 红挂账不修）成立。**
- **提交状态：c1–c5 已提交**（2026-10-13，captain 会话在用户批准的提权运行中执行 c1→c5 线性提交，无 merge、未 push；哈希见 §1 各节）。提交前阻断原委：验收成员（acceptor）所在会话的沙箱对 `.git` 整体拒写（`icacls .git` 显示对沙箱身份的 `(DENY)(W,D,Rc,DC)`，`.git`/`objects`/`refs`/`logs` 写入探针全部 DENY），`git add` 因 `Unable to create '.git/index.lock': Permission denied` 失败，且该委派会话审批关闭、明令不得申请提权。五个提交的命令与明确路径见 §5；各节哈希已回填，c5 哈希以 `git log -5` 为准。附：`git diff --stat` 已人工逐行过目，无密钥；`git status` 改动清单只含预期文件。

---

## 1. 缺陷逐项

### 1.1 P0-1（B1, high）同帧双键丢正文

**问题**：`src/vespercode/llm/v2_openai_adapter.py` 的 SSE 单行解析器先命中 `reasoning_content` 分支即 `return`，同一帧里同时出现的 `content` 被静默丢弃。02 附录 A 复现：同帧 `{reasoning_content:'let me think', content:'AAA'}` + `{'content':'BBB'}` ⇒ 聚合 `content='BBB'`，应为 `'AAABBB'`。

**改法**：`_event_from_sse_line()` → `_events_from_sse_line()`，返回 `(events, ended)`；每帧两字段都按序取，终止（`finish_reason` / `[DONE]`）只在事件吐出后生效；删除内部哨兵 `_StreamEnd`/`_STREAM_END`。`lastOne` 忽略语义与 1 MiB 上界不变。

**命令与真实输出**（红 → 绿）：
```powershell
# 红（修复前，.round2-baseline\t1-red.txt）
.\.venv-formal\Scripts\python.exe -m unittest tests.unit.v2.test_v2_openai_adapter_same_frame -v
#   AssertionError: 'BBB' != 'AAABBB'   files=6   Ran 10 tests / FAILED
# 绿（修复后，验收亲手重跑）
$env:PYTHONPATH='src'; .\.venv-formal\Scripts\python.exe -m unittest tests.unit.v2.test_v2_openai_adapter_same_frame -v
#   Ran 10 tests in 0.004s
#   OK
```
**提交哈希**：c1（`Fix same-frame dual-field content drop in the v2 OpenAI adapter (Line-1 implementer: line1-core)`）— `2b9d687da641b0c22223138b7ccf211c0405f124`。
**未完成项**：非法 UTF-8 仅覆盖 `U+FFFD` 替换路径；帧内 `choices[1]` 仍只取 `choices[0]`；1 MiB 上界只测 overshoot 行为（见 §4）。

### 1.2 P0-2（B2）CI 未装 textual，TUI 用例被静默 skip

**问题**：`.github/workflows/ci.yml` 单 job `unit-test` 全文 21 行，无任何 `pip install`；真实 CI runner 下 `test_v2_tui_app.py` 两用例以 `textual is not installed` skip（CI 实际 `skipped=4`，而非 AGENT_LOG 记载的 2），TUI 契约从未在 CI 执行。

**改法**：`unit-test` job 在 `actions/setup-python@v5` 之后、测试步骤之前插入两步：
```yaml
      - name: Install TUI test dependencies
        run: pip install textual==8.2.8
```
仍单 job、结构最小（1 file changed, 2 insertions(+)）。

**命令与真实输出**（干净环境背靠背，唯一变量 = textual）：
```powershell
.\.venv-formal\Scripts\python.exe -m venv .venv-ci-clean2     # 之后 import textual -> ModuleNotFoundError
$env:PYTHONPATH='src'; .\.venv-ci-clean2\Scripts\python.exe -m unittest discover -s tests\unit\v2 -v
#   test_ctrl_c_cancels_the_running_turn ... skipped 'textual is not installed'
#   test_demo_run_streams_tokens_and_summarizes_turns ... skipped 'textual is not installed'
#   Ran 678 tests / FAILED (errors=295, skipped=2)
# 装入 textual 8.2.8（离线闭包 8 发行版 / 1706 文件，干净 venv 无 pip）后复跑同一命令：
#   test_ctrl_c_cancels_the_running_turn ... Executing <Task pending ... test_v2_tui_app.py:119>
#   test_demo_run_streams_tokens_and_summarizes_turns ... ERROR
#   Ran 678 tests / FAILED (errors=297)
```
→ 本机坐实 **skipped 2 → 0**，两用例真执行；+2 ERROR 经实读为 `%TEMP%` 沙箱伪错（`tempfile.py:286 _resetperms` → `PermissionError [WinError 5]`），与代码无关。T4 新增 CLI 用例不依赖 textual（腿 A skipped 仍为 2），无 +1 口径。

**提交哈希**：c3（`Install textual in the CI unit-test job so the TUI tests execute (Line-2 implementer: line2-ci-cli)`）— `e5faa0fa3e74d4c18a373e8cbdaf05cecb6d0533`。
**未完成项**：完整 **4→2** 口径中另有 2 个 skip 是 `tests/unit/v2/test_relaxed_policy.py:88` / `tests/unit/v2/test_v2_boundary.py:79` 的 symlink-unavailable 守卫（Linux CI 特有，Windows 不触发），与 textual 无关；**完整 4→2 需 push 后由真实 CI 日志最终确认**（本轮不 push）。

### 1.3 P1-1（M1）引擎吞异常，error=None

**问题**：`src/vespercode/loop/v2_engine.py` 的 LLM 调用失败分支 `except Exception:` 构造 `V2ToolResult("FAILED", "LLM call failed")`，异常对象被丢弃 ⇒ 下游 `error` 恒为 `None`，失败原因不可诊断。

**改法**：`except Exception as exc:` → `V2ToolResult("FAILED", "LLM call failed", error=exc)`（仅 1 行改动，停止语义/结果结构不变）。

**命令与真实输出**（红 → 绿）：
```powershell
# 红（修复前，.round2-baseline\t2-red.txt）
#   AssertionError: unexpectedly None : the engine must propagate the exception object, not None
#   tests\unit\v2\test_v2_engine_error_propagation.py:64   Ran 8 tests / FAILED (failures=4)
# 绿（修复后，验收亲手重跑）
$env:PYTHONPATH='src'; .\.venv-formal\Scripts\python.exe -m unittest tests.unit.v2.test_v2_engine_error_propagation -v
#   Ran 8 tests in 0.008s
#   OK
```
**提交哈希**：c2（`Propagate the LLM call exception on the v2 engine failure path (Line-1 implementer: line1-core)`）— `d5ebf7fca2781da8364a160cd0e26e214217c153`。
**未完成项**：真实 Windows 控制台下的 Ctrl+C 中断路径仍无断言覆盖（见 §4）。

### 1.4 P1-2（low）`python -m vespercode.cli_v2` 是 no-op

**问题**：`src/vespercode/cli_v2.py` 无 `if __name__ == "__main__"` 入口，模块以 `-m` 运行时 argv 非空即执行完毕、**零输出零退出码**，README 记录的 16 条文档命令全部静默失效。

**改法**：文件末尾追加 4 行 `if __name__ == "__main__":  # pragma: no cover - exercised via a real subprocess` + `raise SystemExit(main())`。README **零改动**（守卫使文档命令恢复真实行为）。

**命令与真实输出**（红 → 绿）：
```powershell
.\.venv-formal\Scripts\python.exe -m vespercode.cli_v2 --help
#   修复前：stdout 0 字节、exit=0（no-op 坐实，.round2-baseline\t4-before-help.txt）
#   修复后：exit=0、951 字节真实 usage，8 个文档子命令全部在列（.round2-baseline\t4-after-help.txt）
$env:PYTHONPATH='src'; .\.venv-formal\Scripts\python.exe -m unittest tests.unit.v2.test_v2_cli_module_entry -v
#   Ran 3 tests / OK   （subprocess 真跑 -m；修复前 3 failed）
```
**提交哈希**：c4（`Make python -m vespercode.cli_v2 run the CLI instead of exiting silently (Line-2 implementer: line2-ci-cli)`）— `e07786a047a3bb95f1940991308ee1ede2f918bf`。
**未完成项**：无（README 文案未改）。

---

## 2. 独立复核（不自证）

| 复核任务 | 复核者 | 结论 | 证据 |
|----------|--------|------|------|
| T5 = 复核 T1（P0-1 adapter） | auditor（模型异于实现者 line1-core） | pass | `.round2-baseline\t5-review.md`（自写 MyFakeTransport 复现 02 附录 A + diff 审查） |
| T6 = 复核 T2（P1-1 engine） | auditor（模型异于实现者 line1-core） | pass | `.round2-baseline\t6-review.md`（异常注入重验 + diff 审查） |

验收成员（acceptor）另做总验收：九道门槛逐条亲手实跑（见 `.round2-baseline\t7-acceptance.md`），不采信任何成员自证，并自写沙箱归因探针（`.round2-baseline\t7_sandbox_probe.py`）。

---

## 3. 决策 A 判定与测试计数

- 决策 A（默认）：**本轮只修四项缺陷，10 个既有红挂账不修**；完成标准 = `reds ≤ 10` 且与基线清单逐项一致、无新增。
- v2 套件（`discover -s tests/unit/v2`）：**Ran 678** = 657（文档基线）+ 10（T1 新测试）+ 8（T2 新测试）+ 3（T4 新测试），逐项可解释；错误集与 `.round2-baseline\error-ids.txt` 逐 id 一致（263 唯一 id，对称差 0）。
- 全量 `pytest -q --basetemp=D:\pytest-bt`：`365 failed, 1517 passed, 6 skipped, 123 deselected, 438 errors`。分类（`.round2-baseline\t7-logs\t7-full-classify.txt`）：命中 §2b 十红清单 **10**（3 FAILED + 7 ERROR）、沙箱噪声 **677**、环境伪错 **116**（102 × `v2_database.py:1642 OperationalError`、14 × `test_baseline.py TREE_INTEGRITY_FAILED`）、**修复引入新红 = 0**。
- 116 与环境伪错的归因由 acceptor 自写探针独立坐实：沙箱对 `mkdtemp` 目录内的 `os.mkdir`/写文件/`chmod`/`rmtree` 一律 `WinError 5`；**零 VesperCode 代码**的 `sqlite3` 建库同样 `OperationalError`；`allocate_execution_root`（`materialization.py:324`）在此环境抛 `MaterializationError: WRITABLE_SOURCE … [WinError 5]`，正是 `baseline.py:866→883` 返回 `TREE_INTEGRITY_FAILED` 的路径。
- 评审环境的绿色基线（`10 failed, 2255 passed, 6 skipped, 0 errors`）在成员沙箱内**无法复现**：DSH 沙箱对 `%TEMP%` 的 ACL 注入是唯一原因；`TEMP`/`TMP` 重定向对照实验复现同一批失败，排除其它解释。captain 会话 2026-10-13 提权真跑（沙箱外）全量实测：`10 failed, 2276 passed, 6 skipped, 123 deselected, 1 warning in 300.30s (0:05:00)`，完整输出 `.round2-baseline/captain-tier1-fullpytest.txt`；与 §2b 十红的逐项比对由 t13 终验回贴。

---

## 4. 挂账项（照录，本轮不修）

1. **TUI O(n²) 全量重建渲染**：`textual` TUI 每帧重建整棵树，规模增长时渲染复杂度为 O(n²)；本轮未触及渲染架构。
2. **AGENT_LOG.md:4515-4517 口径出入**：原文称 CI `unit-test` job「657 tests, 2 controlled skips / fully green」，真实 CI runner（无 textual）为 **skipped=4**（2 symlink-unavailable + 2 textual）。本轮只记录、不改历史条目。
3. **非法 UTF-8**：adapter 仅覆盖 `decoder.decode` 的 `U+FFFD` 替换路径，无「非法字节序列在帧中间截断」的专项断言。
4. **`choices[1]`**：SSE 帧只消费 `choices[0]`，多 choice 载荷被忽略，无断言。
5. **1 MiB 上界**：只测 overshoot 行为，未测恰好等于上界的边界。
6. **真实 Windows 控制台 Ctrl+C**：`test_v2_tui_app.py:112` 的 Ctrl+C 用例在 CI 走 `textual` 路径，但真实控制台中断（SIGINT/CTRL_C_EVENT）无断言覆盖。

---

## 5. 提交计划（c1–c5，已执行；阻断与执行原委见文首）

```powershell
# 前置：git branch --show-current  (zcode/new-ui)   git status --porcelain=v1
git add src/vespercode/llm/v2_openai_adapter.py tests/unit/v2/test_v2_openai_adapter_same_frame.py
git commit -m "Fix same-frame dual-field content drop in the v2 OpenAI adapter (Line-1 implementer: line1-core)"
git add src/vespercode/loop/v2_engine.py tests/unit/v2/test_v2_engine_error_propagation.py
git commit -m "Propagate the LLM call exception on the v2 engine failure path (Line-1 implementer: line1-core)"
git add .github/workflows/ci.yml
git commit -m "Install textual in the CI unit-test job so the TUI tests execute (Line-2 implementer: line2-ci-cli)"
git add src/vespercode/cli_v2.py tests/unit/v2/test_v2_cli_module_entry.py
git commit -m "Make python -m vespercode.cli_v2 run the CLI instead of exiting silently (Line-2 implementer: line2-ci-cli)"
git add reviews/zcode-new-ui/v2/FIX_REPORT.md AGENT_LOG.md
git commit -m "Record the round-2 fix report and agent log for the zcode/new-ui review defects (verifier: acceptor)"
# 零删除零弱化核查（每个修复提交逐个贴输出）
git show <c1|c2|c3|c4> -- tests/
```
禁用 `git add -A` / `git add .`；不提交 `.round2-baseline/`、`.venv-ci-clean*/`、`.pytest-bt*/`、`.agent-teams/`、`.codegraph/`、`.cursor/`、`.mimosa/`、`.zcodeignore`、`GOAL_v2_streaming_tui.md`、两个 submission zip、`notes.md`、`submission.jsonc`；**绝不 push**。

**执行记录（2026-10-13）**：c1–c5 已由 captain 会话在用户批准的提权运行中按上述命令逐条执行（成员会话对 `.git` 结构性拒写、审批关闭，故由具备写权限的 captain 会话代执；无 merge、未 push）；c1=`2b9d687da641b0c22223138b7ccf211c0405f124`、c2=`d5ebf7fca2781da8364a160cd0e26e214217c153`、c3=`e5faa0fa3e74d4c18a373e8cbdaf05cecb6d0533`、c4=`e07786a047a3bb95f1940991308ee1ede2f918bf`、c5=本报告提交（哈希以 `git log -5` 为准）；逐提交 `git show <c> -- tests/` 核查输出由 t13 终验回贴。

---

## 6. 需 CI / 真机确认清单

1. **完整 skip 4→2**：需 push 后真实 GitHub Actions 日志（本机只能坐实 2→0；另 2 个 symlink skip 为 Linux 特有）。
2. **全量 pytest 绿色基线**（`10 failed, 2255 passed, 6 skipped, 0 errors`）：成员沙箱内无法复现（`%TEMP%` ACL 注入）；captain 会话 2026-10-13 提权真跑（沙箱外）：`10 failed, 2276 passed, 6 skipped, 123 deselected, 1 warning in 300.30s (0:05:00)`（原始输出 `.round2-baseline/captain-tier1-fullpytest.txt`），十红逐项比对由 t13 终验回贴。
3. **CI `unit-test` job 结果**：需 CI 日志确认 `pip install textual==8.2.8` 在 Linux runner 上装上并令 TUI 两用例真执行（本机以离线闭包替代 pip，等价性已记录）。
4. **真实 Windows 控制台 Ctrl+C**：需真机交互确认中断语义。
