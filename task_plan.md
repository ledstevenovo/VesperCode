## 目标

将项目从：

> 内容寻址 + SHA-256 身份绑定 + fail-closed 严格门禁

迁移到：

> 普通运行时 ID + 最小必要状态检查 + 面向用户行为的安全控制

迁移后仍保留以下必要安全能力：

- 路径只能访问授权工作区；
- 不允许任意 Shell 或任意执行参数；
- `tests/`、配置和敏感文件不能被候选修改；
- 真实 LLM 外发仍需明确授权；
- 凭据不写入仓库、日志或数据库；
- 写回仍需用户批准；
- 写回失败仍能恢复或明确报告未决状态；
- Demo 不能获得正式 Harness 能力。

废除的是完整性哈希和过度的身份门禁，不是所有治理机制。

## 第一阶段：冻结旧版本

建立明确的迁移基线：

```text
v0.1.0 = SHA-256 强绑定版本
v0.2.0 = relaxed identity / relaxed gate 版本
```

在 `README.md` 中声明：

- `v0.1.0` 保留旧版哈希合同；
- `v0.2.0` 不再验证旧 digest；
- 两个版本的数据库、候选树和证据文件不保证互通；
- 旧版发布记录只作为历史交付证据，不参与新版本运行。

这一阶段不要修改旧版发布证据和历史归档。

## 第二阶段：重写规范合同

先修改 `SPEC.md` 和 `PLAN.md`，否则代码会继续被旧合同拉回去。

### 删除或废除的内容

重点处理：

- `SPEC.md` §0.1 `CanonicalizationV1`；
- 所有 `digest`、`sha256`、`*_digest`、`*_sha256` 作为安全绑定字段的定义；
- `ActionSemanticDigestV1`；
- `ActionInstanceDigestV1`；
- `CandidateIdentityV1` 的三重摘要绑定；
- `ValidationManifestV1` 的摘要绑定；
- `DisclosureAuthorizationRecordV1` 的请求摘要绑定；
- `FinalWritebackSubjectV1` 的摘要身份；
- `ReferenceProfileManifestV1` 的镜像、lock、策略摘要绑定；
- `requirements.lock` 和 Docker image digest 的强一致性门禁；
- 依赖锁文件中的 distribution hash 要求；
- `gate-toolchain-v1.json` 中的 SHA-256 字段；
- 所有“摘要不一致即停止”的验收条款；
- `FINAL_DELIVERY_POST_MERGE_V1` 中依赖 content-addressed evidence 的部分。

### 新的身份模型

用普通不可推导 ID 替代摘要：

```text
RunId          = UUID / 随机字符串
CandidateId    = UUID
ActionId       = Harness 生成的 UUID
ApprovalId     = UUID
DisclosureId   = UUID
ArtifactId     = UUID
TransactionId  = UUID
```

这些 ID 只负责数据库关联和日志关联，不表示内容完整性，也不承担安全证明。

应明确写入规范：

> ID 是引用键，不是内容认证。修改内容不会自动生成或验证内容摘要。

## 第三阶段：建立 v2 relaxed contracts

建议新增一个明确的配置或模块边界：

```text
src/vespercode/contracts/v2_identity.py
src/vespercode/governance/relaxed_policy.py
```

不要继续在旧 `DigestV1` 上打补丁。

### 旧模型到新模型的变化

例如：

```python
# v0.1
class CandidateIdentityV1:
    candidate_digest: str
    candidate_tree_digest: str
    final_diff_digest: str
```

迁移为：

```python
class CandidateIdentityV2:
    candidate_id: str
    snapshot_id: str
    revision: int
```

```python
# v0.1
class ActionInstanceV1:
    semantic_digest: str
    instance_digest: str
```

迁移为：

```python
class ActionInstanceV2:
    action_id: str
    action_type: str
```

```python
# v0.1
class FinalWritebackSubjectV1:
    subject_digest: str
```

迁移为：

```python
class FinalWritebackSubjectV2:
    subject_id: str
    candidate_id: str
    expires_at: str
```

`candidate_id`、`subject_id` 和 `action_id` 只能用于查找记录，不能用于证明内容未改变。

## 第四阶段：降低校验强度

### 保留的校验

这些属于行为安全，不应删除：

- Pydantic 基础类型校验；
- 未知字段拒绝或允许，按 v2 简化后的 API 选择；
- 路径必须位于工作区；
- 敏感路径拒绝；
- 编辑路径限制；
- 操作类型限制；
- 请求大小和超时上限；
- 状态转换合法性；
- 一次性批准不能重复消费；
- 外部 LLM 授权范围；
- 数据库事务原子性；
- 写回前后的文件存在性和类型检查。

### 建议删除或降级为日志的校验

- 内容 SHA-256；
- canonical JSON；
- digest 自绑定；
- digest 之间的交叉绑定；
- lock file distribution hash；
- Docker manifest digest；
- gate evidence digest；
- 每个内部对象的重复完整性重算；
- “同一内容必须在多个模型中产生相同 digest”的测试；
- 仅为证明摘要稳定性而存在的测试矩阵；
- “未知摘要格式”专门错误码；
- 以摘要变化作为 ProgressMarker 的唯一依据。

### 内容变化检测替代方案

如果仍需要判断候选是否变化，不用哈希，可采用简单的版本号：

```text
CandidateTree.revision: int
CandidateTree.parent_revision: int | None
```

每次成功应用补丁：

```text
revision += 1
```

候选是否变化：

```python
current_revision != previous_revision
```

这只能表示控制面记录的版本变化，不提供跨进程或跨机器的内容认证。规范必须接受这个边界。

## 第五阶段：简化执行和发布门禁

### Docker

从：

```text
必须使用固定 image digest
必须证明 OCI manifest 三方一致
必须使用 lock digest
```

改成：

```text
必须使用声明的镜像名称和版本
镜像能正常启动
执行参数满足 network/user/read-only/mount 约束
```

保留容器隔离本身，因为它是执行边界，不是内容哈希门禁。

### 依赖

从：

```text
完整 requirements hash lock
--require-hashes
```

改成：

```text
requirements.txt 或普通 requirements.lock
固定 major/minor 范围
CI 中安装并运行测试
```

可以保留版本锁定，但不再要求每个 distribution hash。

### CI

保留：

- `unit-test`；
- 基础 lint；
- 类型检查；
- 安全扫描；
- 关键集成测试。

删除：

- gate-toolchain SHA 比较；
- lock file SHA 比较；
- 镜像 digest 三方比较；
- 交付证据的 content-addressed 校验；
- 仅验证摘要一致性的 CI job。

CI 应从“所有身份不可漂移”转向“核心行为可运行”。

## 第六阶段：数据库和历史数据

不建议直接把旧数据库中的 SHA 字段“伪装成普通 ID”。那会造成语义混淆。

推荐方案：

### 方案 A：新建 v2 数据库，最简单

```text
vespercode-v1.sqlite 只读保留
vespercode-v2.sqlite 全新创建
```

优点：

- 不需要伪造旧字段含义；
- 不会把旧摘要误当成新 ID；
- 迁移逻辑最少。

缺点：

- 旧运行记录不能直接在 v2 中继续运行；
- 历史记录需要通过只读查看器访问。

### 方案 B：显式数据迁移

如果必须保留旧记录：

```text
old digest -> legacy_reference_id
new UUID   -> new entity id
```

例如：

```text
legacy_candidate_digest
candidate_id
legacy_source = "v1"
```

旧 digest 只能作为历史显示字段，不能再参与权限、批准或运行判断。

迁移期间必须禁止：

- 用旧 digest 生成新审批；
- 用旧 digest 作为 v2 对象主键；
- 用旧 digest 证明文件内容没有变化。

对于当前课程项目，我建议使用方案 A。

## 第七阶段：代码迁移顺序

建议按以下顺序实施：

1. 新增 v2 配置和身份类型；
2. 修改运行、候选、动作、批准、披露、持久化数据模型；
3. 修改 SQLite migration，建立 v2 schema；
4. 修改主循环上下文和结果反馈；
5. 修改 CandidateTree 和 FinalDiff；
6. 修改 writeback approval；
7. 修改 disclosure ledger；
8. 修改 LLM 请求和审计记录；
9. 修改 Docker/reference profile；
10. 删除旧 digest 计算和校验模块；
11. 删除旧 digest 测试；
12. 更新 WebUI、CLI、Demo；
13. 更新 README、SPEC、PLAN、交付说明；
14. 最后删除旧版 v1 代码，或保留为只读 legacy package。

不要一开始就全仓库搜索替换 `digest`。因为有些字段是普通业务名，有些是旧版安全绑定，有些是结果引用，必须逐模块判断。

## 第八阶段：测试迁移

测试从“完整性证明”改成“行为证明”。

### 删除或改写的测试

删除：

- canonical JSON 向量测试；
- SHA-256 向量测试；
- digest 自绑定测试；
- digest 交叉漂移矩阵；
- lock/image digest 比较测试；
- content-addressed release 测试；
- digest 格式错误码测试。

改写：

```text
旧：candidate digest 改变后审批失效
新：candidate revision 改变后审批失效
```

```text
旧：action semantic digest 必须匹配
新：action_id 必须属于当前 run，action_type 必须在允许集合
```

```text
旧：manifest digest 漂移停止
新：reference profile version 不匹配时停止
```

```text
旧：FinalDiff digest 变化拒绝写回
新：candidate_id、revision 或 diff record 版本变化时拒绝写回
```

### 保留的核心测试

仍应保留：

- 越界路径拒绝；
- 敏感路径拒绝；
- 受保护测试/配置拒绝；
- DENY 不可覆盖；
- 外发无授权不调用 LLM；
- 一次性批准；
- feedback correction；
- stop behavior；
- writeback fault recovery；
- memory isolation；
- Demo capability isolation；
- WebUI CSRF、loopback 和 secret redaction。

## 第九阶段：验收标准

v2 的最小验收标准可以压缩为：

### 核心功能

- 可创建运行；
- Mock LLM 能执行主循环；
- 工具 dispatch 正常；
- 失败反馈能驱动下一轮动作；
- 可进入 formal validation；
- 用户批准后才能写回；
- 写回失败可恢复；
- Demo 可重复运行。

### 核心安全

- 任意路径不能越界；
- 任意命令不能执行；
- 受保护文件不能修改；
- 无授权不能外发；
- 凭据不出现在输出；
- 拒绝动作无法被批准覆盖；
- Demo 无正式能力；
- 未决事务阻止冲突写回。

### 明确不再验收

- 跨对象 SHA-256 一致性；
- canonical digest 向量；
- Docker manifest 摘要一致性；
- 依赖 distribution hash；
- 证据文件内容摘要；
- 旧版 v1 digest 的继续可验证性。

## 第十阶段：迁移完成条件

满足以下条件，才宣布 SHA-256 迁移完成：

- `SPEC.md` 不再把 SHA-256 定义为 v2 身份基础；
- `PLAN.md` 不再要求 hash gate；
- `src/vespercode` 不再导入 `hashlib`，除非有明确的非身份用途；
- 业务模型不再有 `*_digest` / `*_sha256` 安全绑定字段；
- SQLite v2 schema 不再依赖旧摘要字段；
- 新版运行不读取旧版摘要作为权限条件；
- 所有核心行为测试通过；
- README 已说明 v1/v2 不兼容；
- 新版本号和新数据库路径明确；
- 旧版发布记录仍保持只读；
- 没有把“哈希被删除”误写成“系统仍提供同等级完整性保证”。

## 推荐落地策略

对这个项目，建议采用：

```text
v0.1.0：冻结，不改
v0.2.0-alpha：新 v2 relaxed contracts + 新数据库
v0.2.0-beta：核心流程迁移完成
v0.2.0：删除旧 digest 运行路径
```

第一步只改文档和迁移设计，不直接删除代码。确认 v2 合同后，再按“身份模型 → 数据库 → 主循环 → 治理 → 执行 → 测试 → 发布”的顺序实施。

当前最重要的决策是：

> 是要完全删除内容完整性能力，还是只删除“摘要作为权限和流程门禁”的用途？

如果目标是降低复杂度，推荐后者：删除 SHA-256 的身份绑定和严苛门禁，但保留必要的路径、权限、审批、凭据和事务安全。

---

## 当前执行进度（2026-10-11）

> 本节是对上方迁移计划的追加执行记录，不修改原计划。实现位于隔离
> worktree/分支 `codex/relaxed-v2-migration`，尚未合并到 `main`，也尚未创建提交。
>
> 状态更正（2026-10-11）：上面"尚未合并、尚未创建提交"的描述已过时。
> 全部 v2 迁移实现已经由 PR #14（squash 合并提交 `b436ad3`）合入 `main`，
> `main` 随后在 `2aef9d7` 中对 `src/vespercode/validation/python_adapter.py`
> 做了后续重构并加入本文件。隔离 worktree 与分支
> `codex/relaxed-v2-migration`（本地与 origin）已在确认其内容全部被
> `main` 包含后删除；下文所有"尚未提交或合并"的表述一律以本更正为准。

### 已完成：V2-01 身份模型与数据库边界

- 新增 `src/vespercode/contracts/v2_identity.py`：
  - UUID/随机 opaque reference factories：Run、Candidate、Snapshot、Action、Approval、Disclosure、Artifact、Transaction、Subject；
  - `CandidateIdentityV2(candidate_id, snapshot_id, revision)`；
  - `ActionInstanceV2(action_id, action_type)`；
  - `FinalWritebackSubjectV2(subject_id, candidate_id, expires_at)`；
  - 明确这些 ID 只用于数据库/日志关联，不提供内容完整性认证。
- 新增 `src/vespercode/storage/v2_database.py`：
  - 独立数据库文件名 `vespercode-v2.sqlite`；
  - 新 v2 schema：runs、snapshots、candidates、actions、disclosures、artifacts、writeback_approvals、transactions、v2_schema_meta；
  - v1 `schema_migrations` 数据库拒绝复用，混合 v1/v2 标记也拒绝；
  - v2 metadata、表集合、关键列和 schema version fail-closed 校验；
  - run 状态转换使用 revision CAS；
  - revision 必须为非负整数；
  - candidate/snapshot、approval/candidate/run、transaction/candidate/run 的归属关系均在事务内校验；
  - approval 创建和消费均要求 candidate revision 与当前控制面状态一致。
- 新增测试：`tests/unit/v2/test_identity.py`、`test_database.py`。

### 已完成：V2-02 relaxed behavior governance

- 新增 `src/vespercode/governance/relaxed_policy.py`：
  - 工作区边界检查；
  - 原始路径词法检查，拒绝 `//`、`.`、`..`、反斜杠、盘符和空段别名；
  - sensitive path/secret-like extension 拒绝；
  - tests、配置、控制面、依赖、delivery、gates 等 protected write 拒绝；
  - 大小写变体保护；
  - `src` 根目录自身不可作为写入文件；
  - protected 文件仍可被明确 read action 读取；
  - policy DENY 不接受 approval 或模型字段覆盖。
- 新增 `tests/unit/v2/test_relaxed_policy.py`，包含路径别名、大小写、敏感路径、protected path 和 symlink 可用性边界。

### 已完成：V2-03 Harness 主循环与机制切片

- 新增 `src/vespercode/llm/v2.py`：注入式 `ScriptedLLMV2`。
- 新增 `src/vespercode/memory/v2.py`：run-scoped feedback memory；拒绝 `api_key`、token、Bearer、password、private-key 等 secret-like 内容。
- 新增 `src/vespercode/tools/v2_dispatcher.py`：policy-first dispatcher 和 in-memory workspace port；拒绝未知字段、模型自带 action ID、未实现动作和危险路径。
- 新增 `src/vespercode/loop/v2_engine.py`：
  - context assembly；
  - 每轮一次 LLM call；
  - action parse；
  - dispatch；
  - feedback；
  - DONE/最大 turn 停止；
  - LLM/provider 异常转为 `LLM_CALL_FAILED`，不自动重试、不泄漏原始异常。
- 新增 `src/vespercode/runtime_v2.py`：组合数据库、memory、policy、dispatcher 和 loop；unexpected loop failure 会把 persisted run 收束为 STOPPED；终态转换读取当前 revision，不硬编码 revision `2`。
- 新增 `scripts/run_v2_demo.py`：重复机制 Demo，展示 `DENIED → SUCCESS → DONE`，不读取真实工作区、不使用凭据或网络。
- 新增 `tests/unit/v2/test_runtime.py`、`test_composition.py`。

### 已完成：V2-04 版本、文档与 CI 合同

- `src/vespercode/__init__.py` 暴露 v2 alpha version `0.2.0a0`，同时保留 `LEGACY_VERSION = 0.1.0`。
- `pyproject.toml` version 更新为 `0.2.0a0`；现有 console entry point 明确仍是 legacy v1 CLI，不冒充 v2 CLI。
- 重写当前有效合同：`SPEC.md`、`PLAN.md`、`README.md`。
- v1 文档只读冻结副本：`SPEC_v1_frozen.md`、`PLAN_v1_frozen.md`、`README_v1_frozen.md`。
- GitHub CI 当前只运行 v2 standard-library `unit-test` job：
  `PYTHONPATH=src python -m unittest discover -s tests/unit/v2 -v`。
- 更新 package smoke 版本期待和 v2 CI 静态合同。
- 将本轮过程、取舍和限制追加到 `SPEC_PROCESS.md`、`AGENT_LOG.md`。

### 当前验证结果

- v2 离线单元测试：**29 passed，1 controlled skip**；skip 原因是当前主机不允许创建 symlink。
- `python -m compileall`：通过。
- `git diff --check`：无 whitespace error；仅有 Git 的 LF→CRLF 工作树提示。
- v2 Demo：重复运行均为 `DENIED → SUCCESS → DONE`，3 turns，只有内存 workspace 中的 `src/example.py` 被写入。
- changed-file 基础 credential pattern scan：通过。
- README 标题合同 spot-check：通过。
- Pydantic-dependent 的历史 README/credential 官方扫描脚本在当前环境无法启动，因为环境未安装 Pydantic；没有将其记录为通过。

### 尚未完成：V2-05 后续集成

以下内容明确保持未开始，不在本轮假称完成：

- 真实文件系统 candidate materialization 和 writeback；
- v2 disclosure ledger、真实 provider、外发授权和凭据调用路径；
- v2 WebUI/CLI 正式入口；
- v2 Docker/reference execution profile；
- v2 alpha wheel、release workflow 和公网部署；
- 删除或迁移旧 v1 digest 运行路径；
- Windows 专属 symlink/reparse、ACL 和真实 filesystem integration tests。

### 重要边界

- v2 revision 只能表示控制面记录发生变化，不能宣称提供 SHA-256 同等级的跨进程/跨机器内容完整性证明。
- v1 发布记录、旧数据库、旧 reference image 和旧 digest 测试保留为历史只读材料；v2 不读取旧 digest 作为权限条件。
- 本轮未在 `main` 上覆盖或清理用户已有修改；所有实现改动都在隔离 worktree 中。

### Route A 状态更正与完成记录（2026-10-11）

> 本节 supersede 上方“V2-05 尚未开始”列表中关于真实文件系统写回的部分；原文保留作为历史进度记录。

路线 A 已由 `moma/glm-5.3#max` 子 agent 实现，并经过主线程多轮独立审查、打回和复核，当前审查通过。实现仍在隔离 worktree `codex/relaxed-v2-migration`，尚未提交或合并。

#### Route A 已完成范围

- A0：新增冻结 v2 写回合同：`PlannedWriteV2`、`JournalEntryV2`、`WritebackRequestV2`、`WritebackOutcomeV2`、`RecoveryPreviewV2`、`RecoveryOutcomeV2`、`V2WorkspacePort`。
- A1：新增真实路径/对象边界：工作区 confinement、canonical relative path、symlink/junction/reparse refusal、regular-file 类型检查、CREATE/REPLACE target 检查、publish 前 boundary recheck。
- A2：新增真实磁盘 atomic writeback：
  - CREATE 使用 no-clobber link；
  - REPLACE 使用 temp file + fsync + compare-and-publish + atomic replace；
  - explicit approval + candidate revision 绑定；
  - stale/denied/mismatch/duplicate/secret-like content 均在 journal/写入前拒绝；
  - approval consumption 与 transaction journal 在一个 SQLite transaction 中完成。
- A3：新增 durable recovery：`PREPARED → WRITING → COMMITTED/UNRESOLVED/ROLLED_BACK`；支持 fresh-process preview/apply/rollback；空 journal、非法 position、错误 transaction binding、错误 row shape 均 fail-closed；rollback 使用 compare-and-delete 或 compare-and-restore，不删除/覆盖外部修改内容。
- A4：`V2Harness` 已接入真实 `LocalDiskWorkspacePort`、`V2WritebackService` 和 `V2RecoveryService`；loop 仍使用 in-memory staging port，真实写入只能经过显式 writeback approval。
- RA-08：新增保守 secret-content scanner，journal 前拒绝 assignment markers、Bearer、PEM private key 和常见 provider token 形状；scanner 只返回固定 marker，不返回秘密值。
- RA-09：将全部 14 个 v2 production modules 加入 wheel package contract，并新增标准库离线 wheel contract tests，防止 source tests 通过但 wheel 缺少 Route A 模块。

#### Route A 最终验证

- `PYTHONPATH=src python -m unittest discover -s tests/unit/v2 -v`：**145 tests passed，2 controlled skips**；skip 是当前主机无法创建 symlink。
- `python -m compileall -q src tests/unit/v2`：通过。
- `git diff --check`：通过，无 whitespace error；仅保留 Git 的 LF→CRLF 工作树提示。
- v2 mechanism Demo：重复运行 `DENIED → SUCCESS → DONE`，3 turns，确定性通过。
- changed-file 基础 credential pattern scan：通过。
- 主线程已独立复核并修复/确认：REPLACE content TOCTOU、rollback compare-and-delete、v2 schema 全表列校验、journal corruption、secret journal leakage、Route A wheel membership、CI v2 unit-test boundary。

#### 当前真正未完成：Route B

路线 A 完成后，原计划剩余重点为 Route B，全量迁移仍未完成：

- disclosure ledger、真实 provider、外发授权和 secure credential call path；
- candidate/validation/reference profile 的 v2 identity 迁移；
- v2 WebUI 和正式 v2 CLI；
- v2 Docker/reference execution profile；
- v2 alpha wheel 实际构建、安装 smoke、release workflow 和公网部署；
- 旧 v1 digest runtime path 的最终拆分/删除；
- Windows ACL、正式 symlink privilege、filesystem integration 与正式环境验证。

#### 当前结论

```text
v1 freeze                         DONE
v2 relaxed contracts              DONE
v2 offline Harness core           DONE
Route A real writeback/recovery   DONE
Route B full migration            NOT STARTED
Full original task_plan.md       NOT COMPLETE
```
