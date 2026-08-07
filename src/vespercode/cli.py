"""T28.3 legacy step 28.D: thin loopback-only serve CLI composition.

``install_serve_command`` installs the closed ``serve`` command (literal
loopback host, validated port) onto the application parser, rejecting
secret, provider, repository, and alternate-bind inputs (GREEN-1), and
the serve handler composes Tasks 28.A–28.C exactly once — the Task 28.A
security config, the Task 28.B local shell over the injected
``LocalShellFactoryV1``, and the Task 28.C packaged assets — then
launches through the injected application/server boundary without
duplicating shell, asset, request-security, or workflow behavior
(GREEN-2).  T38.2 legacy step 38.E adds the ``recover`` command: the
closed workspace-path parser with the injected
``RecoveryCliHandlerV1``, where every invocation without the literal
``--apply`` switch is a read-only preview (SPEC §8.2/AC-29) and the
handler result projects as bounded text.  Shell construction, package
lookup, request authorization, route behavior, secrets, providers, and
repositories remain out of scope (GREEN-4/Boundary): the recover parser
opens no control database, applies no migration, constructs no
repository or production ``RecoveryService``, and provides no
production default handler (Task 38.F alone owns that binding), and no
transaction edit, disposition override, force/ignore, credential,
secret, or recovery-body CLI argument exists.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Callable,
    Final,
    Literal,
    Protocol,
    Sequence,
    TypeAlias,
)

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from vespercode.web.app import (
    LocalShellPortsV1,
    create_local_app,
    install_packaged_web_assets,
)
from vespercode.web.security import LocalWebSecurityConfigV1

LOOPBACK_HOST_V1: Final[Literal["127.0.0.1"]] = "127.0.0.1"
"""The only host the serve CLI accepts (literal loopback, SPEC §4.9)."""

DEFAULT_PORT_V1: Final[int] = 8765
"""The default loopback port of ``vespercode serve``."""

SESSION_COOKIE_NAME_V1: Final[str] = "vespercode_session"
"""The closed local-session cookie name of the serve composition."""

CSRF_HEADER_NAME_V1: Final[str] = "X-CSRF-Token"
"""The closed CSRF header name of the serve composition."""


class LocalShellFactoryV1(Protocol):
    """The declared shell factory of the serve composition.

    The CLI receives the factory explicitly (the interface's injection
    point); the production shell wiring is provided by the application
    composition and never constructed by the parser (GREEN-4).
    """

    def create(self) -> LocalShellPortsV1:
        """Create the typed local shell ports."""
        ...


ServerLauncherV1: TypeAlias = Callable[[Any, str, int], object]
"""The injected application/server boundary: (app, host, port) -> None."""


class _DefaultShellFactoryV1:
    """The standalone CLI's placeholder shell factory.

    The real local shell wiring belongs to the application composition
    (Task 29/Task 38); the standalone ``vespercode serve`` must fail
    closed with a clear message instead of silently serving an empty
    shell (the composition receives the injected factory).
    """

    def create(self) -> LocalShellPortsV1:
        raise NotImplementedError(
            "the real local shell wiring is provided by the application "
            "composition (Task 29/Task 38); install_serve_command receives "
            "the injected shell factory"
        )


def _uvicorn_launcher(app: Any, host: str, port: int) -> object:
    """The production server boundary: uvicorn on the loopback address."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)
    return None


def _loopback_host(value: str) -> str:
    """One argparse type: the host must be the literal loopback value."""
    if value != LOOPBACK_HOST_V1:
        raise argparse.ArgumentTypeError(
            f"serve 只允许回环主机 {LOOPBACK_HOST_V1}（收到 {value!r}）"
        )
    return value


_PORT_FORM_RE: Final = re.compile(r"^[0-9]{1,5}$")
"""The closed decimal port form (no sign, whitespace, separators, or
non-ASCII digits)."""


def _validated_port(value: str) -> int:
    """One argparse type: the port must be a closed 1..65535 integer.

    The accepted form is the literal decimal form only — signs,
    whitespace, underscores, full-width digits, and trailing newlines
    are rejected before conversion.
    """
    if _PORT_FORM_RE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError(
            f"端口必须是 1..65535 的十进制整数（收到 {value!r}）"
        )
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"端口必须在 1..65535（收到 {value!r}）")
    return port


def _run_serve(
    args: argparse.Namespace,
    shell_factory: LocalShellFactoryV1,
    server_launcher: ServerLauncherV1,
) -> int:
    """Compose Tasks 28.A–28.C exactly once and launch through the
    injected server boundary (GREEN-2): the Task 28.A security config,
    the Task 28.B shell over the injected factory's ports, and the
    Task 28.C packaged assets — no duplicated shell, asset,
    request-security, or workflow behavior."""
    security = LocalWebSecurityConfigV1(
        host=args.host,
        port=args.port,
        session_cookie_name=SESSION_COOKIE_NAME_V1,
        csrf_header_name=CSRF_HEADER_NAME_V1,
    )
    shell_ports = shell_factory.create()
    app = create_local_app(shell_ports, security, route_installers=())
    install_packaged_web_assets(app)
    server_launcher(app, args.host, args.port)
    return 0


def install_serve_command(
    app: argparse.ArgumentParser,
    shell_factory: LocalShellFactoryV1,
    *,
    server_launcher: ServerLauncherV1 = _uvicorn_launcher,
) -> None:
    """Install the closed ``serve`` command onto the application parser.

    The parser accepts only ``--host`` (literal ``127.0.0.1``) and
    ``--port`` (validated 1..65535); every secret, provider, repository,
    and alternate-bind option is an unknown argument and fails closed
    (GREEN-1).  The serve handler composes Tasks 28.A–28.C once and
    launches through the injected server boundary (GREEN-2).
    """
    subparsers = app.add_subparsers(dest="command", required=True, metavar="COMMAND")
    serve_parser = subparsers.add_parser(
        "serve",
        help="启动本地 WebUI（仅绑定 127.0.0.1）",
        description="启动本地 WebUI：仅接受回环主机 127.0.0.1 与校验端口。",
    )
    serve_parser.add_argument(
        "--host",
        type=_loopback_host,
        default=LOOPBACK_HOST_V1,
        metavar="HOST",
        help="绑定主机（必须为字面 127.0.0.1）",
    )
    serve_parser.add_argument(
        "--port",
        type=_validated_port,
        default=DEFAULT_PORT_V1,
        metavar="PORT",
        help="绑定端口（1..65535，默认 8765）",
    )
    serve_parser.set_defaults(
        _serve_handler=lambda args: _run_serve(args, shell_factory, server_launcher)
    )


RecoveryCliResultKindV1: TypeAlias = Literal[
    "PREVIEW",
    "APPLIED",
    "UNRESOLVED",
    "NO_TRANSACTION",
    "WORKSPACE_REJECTED",
    "RECOVERY_FAILED",
]
"""The closed recovery-CLI outcome vocabulary (bounded projection)."""


class RecoveryCliResultV1(BaseModel):
    """One closed recovery-CLI outcome (38.E interface).

    Every outcome carries a bounded static projection text; the kind is
    the closed vocabulary the parser projects — the parser never opens
    storage, never constructs a service, and never reads a raw result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: RecoveryCliResultKindV1
    message: Annotated[StrictStr, Field(min_length=1, max_length=4096)]


class RecoveryCliHandlerV1(Protocol):
    """The injected typed recovery-CLI handler seam (38.E interface).

    The handler owns Task 9.D identity/lease resolution and the Task
    26.C service delegation; the parser only adapts the closed arguments
    and projects the returned bounded text.  The production handler is
    bound by Task 38.F alone.
    """

    def preview(self, workspace: Path) -> RecoveryCliResultV1:
        """Project the read-only recovery preview of *workspace*."""
        ...

    def apply(self, workspace: Path) -> RecoveryCliResultV1:
        """Project the explicit recovery apply of *workspace*."""
        ...


def _subparsers_group(
    app: argparse.ArgumentParser,
) -> argparse._SubParsersAction[Any]:
    """The existing subparsers group of one parser, or a fresh one.

    argparse exposes no public accessor for an already-registered
    subparsers group and rejects a second ``add_subparsers`` call, so
    the recover installer reuses the group the serve installer created
    when present (composition detail, stable across Python 3.12).
    """
    for action in app._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return app.add_subparsers(dest="command", required=True, metavar="COMMAND")


def _run_recover(
    args: argparse.Namespace,
    recovery_handler: RecoveryCliHandlerV1,
) -> int:
    """Project exactly one handler outcome (38.E GREEN-2).

    Without the literal ``--apply`` flag the invocation is a read-only
    preview; with it, the explicit apply.  The bounded projection text
    is printed as-is; no storage, migration, or service is opened here.
    """
    workspace = Path(args.workspace)
    if args.apply:
        result = recovery_handler.apply(workspace)
    else:
        result = recovery_handler.preview(workspace)
    print(result.message)
    return 0


def install_recover_command(
    app: argparse.ArgumentParser,
    recovery_handler: RecoveryCliHandlerV1,
) -> None:
    """Install the closed ``recover`` command onto the application parser.

    The parser accepts exactly ``--workspace PATH`` (required) and the
    literal ``--apply`` switch (38.E GREEN-1); every force/ignore,
    disposition-override, transaction-edit, credential, secret, and
    recovery-body option is an unknown argument and fails closed before
    any handler call.  Every invocation without ``--apply`` defaults to
    the read-only preview (SPEC §8.2/AC-29).
    """
    subparsers = _subparsers_group(app)
    recover_parser = subparsers.add_parser(
        "recover",
        help="预览或执行工作区恢复",
        description=(
            "恢复默认只读预览，不修改工作区、事务状态或备份；"
            "只有字面 --apply 开关才执行恢复变更。"
        ),
    )
    recover_parser.add_argument(
        "--workspace",
        required=True,
        metavar="PATH",
        help="目标工作区路径（不带 --apply 时只读预览）",
    )
    recover_parser.add_argument(
        "--apply",
        action="store_true",
        help="执行恢复变更（唯一的恢复变更开关）",
    )
    recover_parser.set_defaults(
        _recover_handler=lambda args: _run_recover(args, recovery_handler)
    )


def build_cli(
    shell_factory: LocalShellFactoryV1,
    *,
    server_launcher: ServerLauncherV1 = _uvicorn_launcher,
    recovery_handler: RecoveryCliHandlerV1 | None = None,
) -> argparse.ArgumentParser:
    """One closed CLI parser with the serve command installed.

    The Task 38.F production binding passes the initialized
    ``RecoveryCliHandlerV1`` to install the recover command; without a
    handler (the standalone surface and every Task 28.3 test) the
    recover command is absent and fails closed as unknown, so the closed
    serve surface is unchanged (38.F authorized cli.py edit: production
    recover-handler binding only — command syntax, help/errors, and
    preview/apply branching are never changed here).
    """
    parser = argparse.ArgumentParser(
        prog="vespercode",
        description="VesperCode 编码智能体框架本地控制台。",
    )
    install_serve_command(parser, shell_factory, server_launcher=server_launcher)
    if recovery_handler is not None:
        install_recover_command(parser, recovery_handler)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """One standalone CLI entry: closed serve parsing and loopback
    launch over the placeholder factory (the production shell factory is
    injected by the application composition)."""
    parser = build_cli(_DefaultShellFactoryV1())
    args = parser.parse_args(argv)
    handler = getattr(args, "_serve_handler", None)
    if handler is None:
        # Defensive: the required subparsers plus the serve defaults make
        # this unreachable; fail closed rather than silently succeeding.
        parser.error("未知命令")
    return int(handler(args))


class _VesperCliV1:
    """The closed CLI entry surface (argparse-based; T33.1 wires the
    installed entry point to ``main``)."""

    def main(self, argv: Sequence[str] | None = None) -> int:
        return main(argv)


cli: Final[_VesperCliV1] = _VesperCliV1()
"""The module-level CLI surface the exact RED invokes."""
