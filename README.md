# VesperCode

VesperCode 是一个面向 Windows 本地代码仓库的 Coding Agent Harness 课程项目。它不是把现成的 Agent 框架换一层包装，而是自行实现一套可测试、可审计、以治理为核心的 Agent 内核：让 LLM 在受控工作区中检查代码、提出候选补丁、运行结构化验证，并根据客观反馈继续修正，同时限制路径、工具、审批、凭据和数据披露风险。

本文档内容全部基于本仓库已提交的实现与验证证据，不包含任何未经终端验证的外部结果。

## 当前状态

- 实现已交付并通过门禁：`FORMAL_READY`（2026-08-03）之后的实现工作已交付；`PLAN.md` 的 68 张任务卡与 141 个唯一 legacy steps 计数契约，以及过程记录（冷启动、文档检查、AGENT_LOG 完成锚点）由 `scripts/verify_process_evidence.py` 逐项复核通过；T37.1 的 README 契约（37.A）与过程证据（37.B）验证器已实现并通过测试。
- 包、镜像与 CI 契约已验证：wheel 打包与 pipx 安装（T33.1/T33.2）、跨平台确定性参考镜像（T35.1）、CI 契约（T35.1）与交付证据 schema（T36.1/T36.2/T36.3）均已落地。
- 最终发布与公网演示已完成：受保护 workflow 发布 `v0.1.0`、wheel 与 GHCR reference 镜像；Render Free 服务已上线并通过 `/healthz` 与固定场景验证。发布、部署与同源证据见 `delivery/evidence/`。

## Reference image digest verification

本仓库的参考镜像身份在 Windows formal 环境与 GitHub Linux runner 上字节一致复现（SPEC_PROCESS 86），冻结身份为：

- manifest 摘要：`cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823`
- profile 摘要：`d0700f00f5ae2501ac9be7fbdd66d20e76c16a6c6f9ab7893c1aea71d57e927e`

按以下步骤验证已发布镜像未被篡改（可操作指令）：

1. `docker pull ghcr.io/ledstevenovo/vespercode-reference@sha256:cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823`。
2. 计算拉取镜像的 manifest 与 profile 摘要，与上方冻结身份逐字节比对；任一不一致即判定镜像无效，停止使用。
3. 用 T36.2 的 `verify_release_publication_result`（`src/vespercode/delivery/publication.py`，输入为冻结的 `FrozenReleaseInputsV1` 与观测的 `ObservedReleaseResultV1`，按 36.B GREEN-2 确定性顺序比对）复核发布结果，三方摘要（release 记录、GHCR RepoDigest、本地拉取）必须相等。

发布结果的证据验证入口是 `scripts/verify_release_evidence.py --live <evidence_root>`（T36.1，`--live` 要求终态成功与 24 小时新鲜度）；`delivery/evidence/` 下的三条 JSON 记录只在终端事实确认后写入。镜像自身的复现与 digest 验证入口是 `scripts/run_reference_image_smoke.py`（T34.2）。

## Installation

- 运行环境：Python 3.12（本项目在 Windows 11 与 Linux 上开发与验证；`dev.lock` 锁定依赖，含 `pywin32`，只能在 Windows 安装）。
- 从源码构建 wheel：`python -m build`（T33.1 验证 wheel 恰好一个，成员清单与 `RECORD` 自洽）。
- 安装：`pip install dist/vespercode-*.whl`，或隔离安装 `pipx install dist/vespercode-*.whl`（T33.2 验证 `vespercode --help` 退出码 0、不泄漏源码 checkout 导入）。
- 开发安装：`pip install -e .` 后 `pytest`（完整离线套件基线 `1549 passed`，T35.1 记录）。

## Usage

安装后有两个入口：

- **本地实际使用模式**（Windows 本机）：`vespercode` 启动只绑定 `127.0.0.1` 的本地 WebUI，处理用户指定的本地 Git 工作区。所有路径、工具、审批与凭据披露均受治理判定约束。
- **公网演示模式**：只使用内置示例仓库、预定义场景、Mock LLM 与受限 `DemoExecutor`，不读取本地文件、不接收任意仓库或真实凭据、不执行任意命令或对外网络请求。演示结果始终标记为模拟运行，终态为 `DEMO_COMPLETED`。

两种模式共享状态模型与 Harness 核心，但进程启动后模式不可切换。

## Directory layout

```
src/vespercode/        # 包源码（cli、loop、governance、persistence、
                       #   recovery、delivery、storage 等模块）
scripts/               # 只读验证器与工具（scan_credentials、verify_*）
tests/                 # unit / e2e / smoke / integration 测试
gates/                 # 冻结的 gate 工具链与证据
delivery/evidence/     # 交付证据 schema 与记录槽位（ci/release/deployment）
SPEC.md                # 规格（§1.6、§5.x、§8.x、§10.1 验收标准）
PLAN.md                # 68 张任务卡、38 里程碑、141 唯一 legacy steps
SPEC_PROCESS.md        # 追加式过程记录（含冷启动与文档检查记录）
AGENT_LOG.md           # 追加式执行日志（含每任务 COMPLETION 锚点）
render.yaml            # Render Free 公网 Demo 部署契约（已上线）
.github/workflows/     # GitHub Actions（T35.1，三 job 契约）
.gitlab-ci.yml         # GitLab CI（T35.1，四 job 契约，无项目未运行）
```

## Secure key setup

- 仓库凭据红线由 `scripts/scan_credentials.py` 强制：任何变更文件中的 API key、私钥块、带凭据 URL 都会在提交前被扫描拦截（`CREDENTIAL_SCAN_*` 错误码），报告只给出规则与路径、绝不回显匹配值。
- 本地模式下 WebUI 只监听 `127.0.0.1`，不对外暴露。
- 持久化与凭据存储受 NTFS ACL 保护；身份校验与排他互斥由真实 Windows 对象实现（`tests/integration/windows/test_persistence_acl_and_identity.py`）。
- 公网演示进程不注册本地文件系统、凭据管理、Docker 执行器或真实 LLM 供应商能力。

## Distribution

- 分发形态：wheel（`pyproject.toml` 冻结 console 入口 `vespercode = vespercode.cli:main`，T33.1 验证 164 个 wheel 成员双向一致）+ 参考镜像（上文冻结身份）。
- `v0.1.0` 的版本化 wheel 已作为 [GitHub Release](https://github.com/ledstevenovo/VesperCode/releases/tag/v0.1.0) 附件发布，SHA-256 为 `ad6706009653a57253c0732037cd643c753416d28f58137543df3771cee86356`；下载后先用 `sha256sum <wheel>`（Windows PowerShell：`Get-FileHash <wheel> -Algorithm SHA256`）核验，再以 `pipx install <wheel>` 安装。本项目未发布到 Python 包索引，不能使用 `pipx install vespercode`。
- 正式 reference 镜像发布到与仓库同一所有者下的 `ghcr.io/ledstevenovo/vespercode-reference`，规范引用为 `ghcr.io/ledstevenovo/vespercode-reference@sha256:cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823`；tag 不构成运行身份，运行与证据只接受 digest。
- 镜像验证链（按序执行，任一失败即本地正式运行失败关闭）：
  1. `docker pull ghcr.io/ledstevenovo/vespercode-reference@sha256:cf0b6c5ccac588fccd07c3b9f050bff4daf550ac6e518fd06efb6e988ab1d823`；
  2. `docker image inspect <image> --format '{{json .RepoDigests}}'` 必须恰好等于该 digest（本地 RepoDigest 核验）；
  3. 镜像内 profile/version smoke：`scripts/run_reference_image_smoke.py`（T34.2；重建与 loopback 拉取的 manifest digest 均与冻结 digest 逐字节比对）；
  4. 确认 wheel 内置 `reference-profile-v1.json` 的 `docker_image_digest` 与所拉取 digest 完全一致：
     `python -c "import glob,json,zipfile; m=json.load(zipfile.ZipFile(glob.glob('dist/vespercode-*.whl')[0]).read('vespercode/profiles/builtin/reference-profile-v1.json')); print(m['docker_image_digest'])"`
- 可复制的本地 `docker build` / `docker run`（复现与诊断用；参考镜像的正式身份只有上方不可变 digest，本地重建必须经 digest 比对后才可声称与正式镜像等价）：
  - **参考镜像**（Dockerfile `containers/reference/Dockerfile`；build context 必须含冻结的 `fixture/` 与 `requirements.lock`，即 Task 2 配方上下文——`scripts/run_reference_image_smoke.py` 自动装配该上下文并重建、比对 digest）：
    `docker build --no-cache -f containers/reference/Dockerfile -t vespercode-reference:repro <context>`；
    `docker run --rm --network none --user vesper vespercode-reference:repro python --version`。
  - **Demo 镜像**（Dockerfile `containers/demo/Dockerfile`；build context 为仓库根；容器读平台注入的 `PORT` 并绑定 `0.0.0.0:PORT`，健康检查 `GET /healthz`）：
    `docker build --no-cache -f containers/demo/Dockerfile -t vespercode-demo:local .`；
    `docker run --rm -p 8000:8000 -e PORT=8000 --user vesper vespercode-demo:local`，随后 `curl http://127.0.0.1:8000/healthz`。以上命令均不含凭据；Demo 镜像无真实能力、无 secret、无 Docker socket（SPEC §8.3）。
- 发布流程契约由 T36.2 的 `verify_release_publication_result` 定义（7 个封闭错误码、确定性优先级 source→tag→wheel→manifest-vs-GHCR→pulled→install→smoke）；`v0.1.0` 于 2026-08-12 由受保护 GitHub workflow 发布，tag 指向冻结 `source_commit` `d31bdeeafe8ad65b60fac213e23fcab9dffdd7aa`，workflow run 为 [31613220901](https://github.com/ledstevenovo/VesperCode/actions/runs/31613220901)。
- 发布必须使用只读权限的 CI（无发布秘密）与 fail-closed 的受保护 tag 规则（T35.1）。
- 本地运行前提：Windows 11 x64、Python 3.12、Git、Docker Desktop Linux 容器模式，以及按不可变 digest 拉取并核验的 `python-src-py312-v1` reference 执行镜像（`src/vespercode/profiles/builtin/reference-profile-v1.json`）。
- 凭据配置：本地模式凭据经系统凭据存储（keyring）读取，WebUI 只绑定 `127.0.0.1`；LLM profile 为 `openai-single-turn-v1`（精确模型 `gpt-4.1-mini`，`src/vespercode/profiles/builtin/openai-single-turn-v1.json`）；外发请求按所选 profile 声明的 `NO_CONTENT_REDACTION_V1` 契约披露——所选项目正文在规范裁剪后原样发送、不做正文扫描，外发前经 `src/vespercode/web/disclosure_workflow.py` 向用户披露。
- 恢复：`vespercode recover --workspace <path>` 只预览恢复；增加 `--apply` 后才执行；WebUI 提供等价的预览与显式确认入口（SPEC §8.2）。

## Limitations

- **平台**：主运行环境是 Windows 11；`pywin32` 锁在 `dev.lock` 中，Linux 上无法安装，因此本仓库在 Linux 只能运行不依赖 Windows 对象的测试子集。
- **Render Free 限制**：公网 Demo 使用免费实例；空闲时会休眠，首次请求可能延迟 50 秒以上。该站点仅为无凭据、无真实仓库、无真实 LLM 的固定模拟场景，不是 Windows 本地 Harness 的托管替代品。
- **GitLab**：GitLab 无项目，其四 job 契约只做过静态验证与本地 dind 演练，从未在 GitLab 运行。
- **平台验证边界**：Windows 专属测试在 Windows 环境运行；Linux CI 不安装 `pywin32`，只运行不依赖 Windows 对象的测试与镜像构建 job。
- **首版能力边界**：只支持创建/修改支持矩阵内的普通文本文件；删除、重命名、二进制修改、文件模式变化、任意 Shell 与通用联网均拒绝（见 SPEC 与 PLAN）。

## CI/CD

- **GitHub Actions**（T35.1）：`unit-test` / `reference-image-build` / `demo-image-build` 三 job，在每次 push 与 PR 上运行；权限只读、零发布秘密；reference job 在 Linux runner 上重建冻结 digest（跨平台确定性已证明）。近期 push/PR 运行均成功（`AGENT_LOG.md` 的 T35.1 记录）。
- **GitLab CI**（T35.1）：四 job 契约与 dind 拓扑 loopback 绑定已提交；无项目未运行（见 Limitations）。
- **两端项目 URL 与镜像方向**（SPEC §8.4）：GitHub 仓库 `https://github.com/ledstevenovo/VesperCode` 是源码、版本 tag、Release 与 GHCR package 的发布权威，GitHub Actions 三 job 在每次 push 与 PR 上运行；GitLab 无项目，其完整 CI/Windows wheel/受保护发布闭环契约已提交但从未运行。普通 CI 不反向改写 GitHub；受保护 release pipeline 只有在 GitLab `CI_COMMIT_SHA`、GitHub 同名 tag commit 与待发布 wheel 源提交三者一致时才可发布，任一查询失败或摘要不一致即停止。
- **本地验证链**：`scripts/scan_credentials.py`（凭据扫描）、`scripts/verify_readme_contract.py`（README 契约）、`scripts/verify_process_evidence.py`（过程记录）、`scripts/verify_release_evidence.py --live`（交付证据，终端事实后使用）组成只读、fail-closed 的收尾验证链。

## Web UI

- **本地 WebUI**：本地实际使用模式下由 `vespercode serve` 启动，只绑定 `127.0.0.1`，不对外暴露，也不提供公网健康检查端点。
- **公网演示模式**：[https://vespercode-demo.onrender.com](https://vespercode-demo.onrender.com) 运行 `src/vespercode/demo/app.py`，只使用内置示例仓库与 Mock LLM。`GET /healthz` 返回 HTTP 200 与 `{"status":"ok","mode":"simulation"}`。
- **部署记录**：Render Free deploy `dep-d9ut99tg1s2s73e8u0vg` 当前为 Live；平台实际构建配置提交 `8b596b0bf0c09ce46d11ee90927cf63a42c1de21`，交付产品身份仍为 release `source_commit` `d31bdeeafe8ad65b60fac213e23fcab9dffdd7aa`。公网浏览器固定场景已验证 DENIED / CHECK_FAILED / 等待用户 / REJECTED / COMPLETED 全状态链，终态控制全部禁用。
