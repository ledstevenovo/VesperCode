"""Route B / B3: the closed local v2 CLI surface.

``vespercode.cli_v2`` is the standard-library-only v2 command line
(``vespercode-v2``): a closed argparse grammar — ``run``, ``status``,
``writeback``, ``recovery``, ``credential-status``, ``disclosure-status``,
``serve``, and ``tui`` — where every argument is bounded and typed, and
no shell, argv passthrough, secret, policy, or profile option exists.  Writeback and recovery are preview-by-default and require the
explicit ``--apply`` switch; the agent loop runs only behind an
injected LLM boundary (no real provider transport exists in this
slice, so the shipped default composition fails runs closed).

Every projection is bounded and non-revealing: opaque IDs, closed
statuses, revisions, timestamps, and counts.  The legacy v1 ``vespercode``
CLI is a separate frozen module (``vespercode.cli``) that remains
untouched read-only legacy; nothing here imports it or replaces it.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable, Sequence, TextIO, cast

from vespercode.llm.v2_openai_adapter import V2OpenAIAdapterError
from vespercode.loop.v2_engine import V2LLM
from vespercode.shell_v2 import V2LocalShell, V2ShellError
from vespercode.web.v2_app import V2LocalWebApp
from vespercode.web.v2_forms import V2_IDENTIFIER_RE, V2_TASK_MAX_CHARS
from vespercode.web.v2_security import V2_LOOPBACK_BIND_HOST
from vespercode.web.v2_server import v2_serve_forever

V2_CLI_DEFAULT_PORT = 8766
"""The default loopback port of ``vespercode-v2 serve``."""

V2_CLI_MAX_TURNS_MAX = 1000
"""The closed upper bound of the ``--max-turns`` argument."""

_DEFAULT_MAX_TURNS = 20
_DECIMAL_RE = re.compile(r"^[0-9]{1,5}$")


def _existing_directory(value: str) -> Path:
    path = Path(value)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(
            f"workspace must be an existing directory: {value}"
        )
    return path


def _cli_task(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise argparse.ArgumentTypeError("task must not be empty")
    if len(value) > V2_TASK_MAX_CHARS:
        raise argparse.ArgumentTypeError(
            f"task must be at most {V2_TASK_MAX_CHARS} characters"
        )
    if "\x00" in value:
        raise argparse.ArgumentTypeError("task must not contain NUL")
    return value


def _cli_max_turns(value: str) -> int:
    if re.fullmatch(r"[0-9]{1,4}", value) is None:
        raise argparse.ArgumentTypeError("max turns must be a decimal count")
    turns = int(value)
    if not 1 <= turns <= V2_CLI_MAX_TURNS_MAX:
        raise argparse.ArgumentTypeError(
            f"max turns must be between 1 and {V2_CLI_MAX_TURNS_MAX}"
        )
    return turns


def _cli_identifier(value: str) -> str:
    if V2_IDENTIFIER_RE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("the value must be a short opaque identifier")
    return value


def _cli_port(value: str) -> int:
    if _DECIMAL_RE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("port must be a 1..65535 decimal integer")
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _cli_loopback_host(value: str) -> str:
    if value != V2_LOOPBACK_BIND_HOST:
        raise argparse.ArgumentTypeError(
            f"serve binds the literal loopback host only: {V2_LOOPBACK_BIND_HOST}"
        )
    return value


def build_v2_cli_parser() -> argparse.ArgumentParser:
    """Build the closed v2 CLI grammar (no handler binding)."""

    parser = argparse.ArgumentParser(
        prog="vespercode-v2",
        description=(
            "VesperCode v2 local CLI: closed, loopback-only, offline. "
            "Writeback and recovery are previews unless --apply is given."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run_parser = subparsers.add_parser(
        "run",
        help="run the composed agent loop over one workspace",
    )
    run_parser.add_argument(
        "--workspace", type=_existing_directory, required=True, metavar="DIR"
    )
    run_parser.add_argument("--task", type=_cli_task, required=True, metavar="TEXT")
    run_parser.add_argument(
        "--max-turns",
        type=_cli_max_turns,
        default=_DEFAULT_MAX_TURNS,
        metavar="N",
    )

    status_parser = subparsers.add_parser("status", help="project recorded v2 runs")
    status_parser.add_argument(
        "--workspace", type=_existing_directory, required=True, metavar="DIR"
    )
    status_parser.add_argument(
        "--run-id", type=_cli_identifier, default=None, metavar="ID"
    )

    writeback_parser = subparsers.add_parser(
        "writeback",
        help="stage a candidate and preview (or --apply) its writeback",
    )
    writeback_parser.add_argument(
        "--workspace", type=_existing_directory, required=True, metavar="DIR"
    )
    writeback_parser.add_argument(
        "--task", type=_cli_task, required=True, metavar="TEXT"
    )
    writeback_parser.add_argument(
        "--max-turns",
        type=_cli_max_turns,
        default=_DEFAULT_MAX_TURNS,
        metavar="N",
    )
    writeback_parser.add_argument(
        "--apply",
        action="store_true",
        help="create the explicit approval and apply the writeback",
    )

    recovery_parser = subparsers.add_parser(
        "recovery",
        help="preview durable recovery (apply only with --apply)",
    )
    recovery_parser.add_argument(
        "--workspace", type=_existing_directory, required=True, metavar="DIR"
    )
    recovery_parser.add_argument(
        "--transaction-id", type=_cli_identifier, default=None, metavar="ID"
    )
    recovery_parser.add_argument(
        "--apply",
        action="store_true",
        help="apply one pending transaction (requires --transaction-id)",
    )

    credential_parser = subparsers.add_parser(
        "credential-status",
        help="project the non-revealing credential status of one provider",
    )
    credential_parser.add_argument(
        "--workspace", type=_existing_directory, required=True, metavar="DIR"
    )
    credential_parser.add_argument(
        "--provider", type=_cli_identifier, required=True, metavar="NAME"
    )

    disclosure_parser = subparsers.add_parser(
        "disclosure-status",
        help="project bounded disclosure grant summaries",
    )
    disclosure_parser.add_argument(
        "--workspace", type=_existing_directory, required=True, metavar="DIR"
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="serve the v2 local WebUI on 127.0.0.1 only",
    )
    serve_parser.add_argument(
        "--workspace", type=_existing_directory, required=True, metavar="DIR"
    )
    serve_parser.add_argument(
        "--host",
        type=_cli_loopback_host,
        default=V2_LOOPBACK_BIND_HOST,
        metavar="HOST",
    )
    serve_parser.add_argument(
        "--port",
        type=_cli_port,
        default=V2_CLI_DEFAULT_PORT,
        metavar="PORT",
    )

    tui_parser = subparsers.add_parser(
        "tui",
        help=(
            "interactive streaming TUI over the v2 loop "
            "(scripted offline LLM by default; no API key needed)"
        ),
    )
    tui_parser.add_argument(
        "--workspace", type=_existing_directory, required=True, metavar="DIR"
    )
    tui_parser.add_argument("--task", type=_cli_task, default=None, metavar="TEXT")
    tui_parser.add_argument(
        "--max-turns",
        type=_cli_max_turns,
        default=_DEFAULT_MAX_TURNS,
        metavar="N",
    )
    tui_parser.add_argument(
        "--llm",
        choices=("scripted", "openai"),
        default="scripted",
        help=(
            "scripted: offline deterministic streaming mock (no key); "
            "openai: real streaming adapter (key from VESPERCODE_V2_API_KEY)"
        ),
    )
    tui_parser.add_argument(
        "--base-url",
        default=None,
        metavar="URL",
        help="OpenAI-compatible base URL (env VESPERCODE_V2_BASE_URL)",
    )
    tui_parser.add_argument(
        "--model",
        default=None,
        metavar="NAME",
        help="model name (env VESPERCODE_V2_MODEL)",
    )
    return parser


class V2CliComposition:
    """The injectable composition behind the v2 CLI commands.

    ``llm_factory`` produces one fresh LLM boundary per run (``None``
    composes no LLM: runs and writebacks fail closed with
    ``NO_LLM_BOUNDARY``).  ``shell_factory`` builds the local shell for
    one command (the default composes a real ``V2LocalShell`` over the
    workspace with its control database under ``.vespercode``).
    ``web_launcher`` bridges the serve command (the default serves the
    v2 local WebUI through the standard-library loopback server).
    Output streams are injectable so every behavior is testable
    offline.
    """

    def __init__(
        self,
        *,
        llm_factory: Callable[[], V2LLM] | None = None,
        shell_factory: Callable[[Path, int], V2LocalShell] | None = None,
        web_launcher: Callable[[V2LocalWebApp, str, int], None] = v2_serve_forever,
        tui_launcher: Callable[[object], int] | None = None,
        stream: TextIO | None = None,
        error_stream: TextIO | None = None,
    ) -> None:
        self._llm_factory = llm_factory
        self._shell_factory = shell_factory
        self._web_launcher = web_launcher
        self._tui_launcher = tui_launcher
        self._stream: TextIO = stream if stream is not None else sys.stdout
        self._error_stream: TextIO = (
            error_stream if error_stream is not None else sys.stderr
        )
        self._parser: argparse.ArgumentParser | None = None

    # ------------------------------------------------------------------
    # composition helpers
    # ------------------------------------------------------------------

    def _build_shell(self, workspace: Path, max_turns: int) -> V2LocalShell:
        if self._shell_factory is not None:
            return self._shell_factory(workspace, max_turns)
        return V2LocalShell(
            workspace=workspace,
            llm_factory=self._llm_factory,
            max_turns=max_turns,
        )

    def _emit(self, line: str) -> None:
        print(line, file=self._stream)

    def _emit_error(self, code: str, message: str) -> None:
        print(f"error: {code} - {message}", file=self._error_stream)

    def _shell_error(self, exc: V2ShellError) -> int:
        self._emit_error(exc.code, str(exc))
        return 1

    def _usage_error(self, message: str) -> None:
        assert self._parser is not None
        self._parser.error(message)

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def run(self, argv: Sequence[str] | None = None) -> int:
        self._parser = build_v2_cli_parser()
        args = self._parser.parse_args(argv)
        handler = cast(
            "Callable[[argparse.Namespace], int]",
            getattr(self, f"_run_{args.command.replace('-', '_')}"),
        )
        return handler(args)

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------

    def _run_run(self, args: argparse.Namespace) -> int:
        shell = self._build_shell(args.workspace, args.max_turns)
        try:
            outcome = shell.start_run(args.task)
        except V2ShellError as exc:
            return self._shell_error(exc)
        finally:
            shell.close()
        self._emit(f"run_id: {outcome.run_id}")
        self._emit(f"candidate_id: {outcome.candidate_id}")
        self._emit(f"candidate_revision: {outcome.candidate_revision}")
        self._emit(f"loop_status: {outcome.loop_status}")
        self._emit(f"stop_reason: {outcome.stop_reason}")
        self._emit(f"turns: {outcome.turns}")
        return 0

    def _run_status(self, args: argparse.Namespace) -> int:
        shell = self._build_shell(args.workspace, _DEFAULT_MAX_TURNS)
        try:
            if args.run_id is not None:
                run = shell.run_detail(args.run_id)
                if run is None:
                    self._emit_error(
                        "UNKNOWN_RUN",
                        "the run is unknown to this v2 control database",
                    )
                    return 1
                runs = [run]
            else:
                runs = list(shell.recent_runs())
        finally:
            shell.close()
        if not runs:
            self._emit("no runs recorded")
            return 0
        for run in runs:
            phase = run.phase if run.phase is not None else "-"
            self._emit(
                f"run {run.run_id} status={run.status} "
                f"phase={phase} revision={run.revision}"
            )
        return 0

    def _run_writeback(self, args: argparse.Namespace) -> int:
        shell = self._build_shell(args.workspace, args.max_turns)
        try:
            outcome = shell.start_run(args.task)
            operations = shell.staged_operations(outcome.run_id)
            if not args.apply:
                self._emit(f"staged writes: {len(operations)}")
                for operation in operations:
                    self._emit(f"preview {operation.action_type} {operation.path}")
                self._emit("approval: not created")
                self._emit("workspace: not written (pass --apply)")
                return 0
            approval_id = shell.create_writeback_approval(
                run_id=outcome.run_id,
                candidate_id=outcome.candidate_id,
                candidate_revision=outcome.candidate_revision,
            )
            result = shell.request_writeback(
                run_id=outcome.run_id,
                candidate_id=outcome.candidate_id,
                candidate_revision=outcome.candidate_revision,
                approval_id=approval_id,
            )
        except V2ShellError as exc:
            return self._shell_error(exc)
        finally:
            shell.close()
        self._emit(f"approval_id: {approval_id}")
        self._emit(f"writeback: {result.status}")
        if result.transaction_id is not None:
            self._emit(f"transaction_id: {result.transaction_id}")
        self._emit(result.message)
        return 0 if result.status == "COMMITTED" else 1

    def _run_recovery(self, args: argparse.Namespace) -> int:
        if args.apply and args.transaction_id is None:
            self._usage_error("--apply requires an explicit --transaction-id")
        shell = self._build_shell(args.workspace, _DEFAULT_MAX_TURNS)
        try:
            if args.apply:
                assert args.transaction_id is not None
                outcome = shell.recovery_apply(args.transaction_id)
                self._emit(f"recovery: {outcome.status}")
                self._emit(f"transaction_id: {outcome.transaction_id}")
                self._emit(outcome.message)
                return 0 if outcome.status == "APPLIED" else 1
            if args.transaction_id is not None:
                preview = shell.recovery_preview(args.transaction_id)
                self._emit(f"transaction: {preview.transaction_id}")
                self._emit(f"state: {preview.transaction_state}")
                blocked = "yes" if preview.blocked else "no"
                self._emit(f"blocked: {blocked}")
                for item in preview.items:
                    self._emit(
                        f"item {item.position} {item.action_type} "
                        f"{item.path} {item.state}"
                    )
                return 0
            transaction_ids = shell.pending_transaction_ids()
            self._emit(f"pending transactions: {len(transaction_ids)}")
            for transaction_id in transaction_ids:
                self._emit(f"transaction: {transaction_id}")
            return 0
        except V2ShellError as exc:
            return self._shell_error(exc)
        finally:
            shell.close()

    def _run_credential_status(self, args: argparse.Namespace) -> int:
        shell = self._build_shell(args.workspace, _DEFAULT_MAX_TURNS)
        try:
            status = shell.credential_status(args.provider)
        except V2ShellError as exc:
            return self._shell_error(exc)
        finally:
            shell.close()
        configured = "yes" if status.configured else "no"
        updated = status.updated_at if status.updated_at is not None else "-"
        self._emit(f"provider: {status.provider}")
        self._emit(f"configured: {configured}")
        self._emit(f"updated_at: {updated}")
        return 0

    def _run_disclosure_status(self, args: argparse.Namespace) -> int:
        shell = self._build_shell(args.workspace, _DEFAULT_MAX_TURNS)
        try:
            grants = list(shell.disclosure_grant_summaries())
        finally:
            shell.close()
        if not grants:
            self._emit("disclosure grants: none recorded")
            return 0
        for grant in grants:
            self._emit(
                f"grant {grant.grant_id} run={grant.run_id} "
                f"status={grant.status} expires={grant.expires_at} "
                f"budget={grant.byte_budget} consumed={grant.consumed_bytes}"
            )
        return 0

    def _run_serve(self, args: argparse.Namespace) -> int:
        shell = self._build_shell(args.workspace, _DEFAULT_MAX_TURNS)
        app = V2LocalWebApp(shell)
        try:
            self._web_launcher(app, args.host, args.port)
        finally:
            shell.close()
        return 0

    def _run_tui(self, args: argparse.Namespace) -> int:
        # The TUI is a lazily-shipped surface: nothing in this module (or
        # the stdlib-only launch/view-model modules) imports textual at
        # module level; the import happens only when the command runs.
        from vespercode.tui.v2_launch import (
            DEFAULT_DEMO_TASK,
            V2TuiLaunchSpec,
            build_demo_llm_factory,
        )

        llm_factory: Callable[[], object] | None = None
        if args.llm == "openai":
            try:
                adapter = self._build_openai_adapter(args)
            except V2OpenAIAdapterError as exc:
                self._emit_error(exc.code, str(exc))
                return 1
            llm_factory = lambda: adapter  # noqa: E731 - stateless, one instance
        spec = V2TuiLaunchSpec(
            workspace=args.workspace,
            task=args.task if args.task is not None else DEFAULT_DEMO_TASK,
            max_turns=args.max_turns,
            llm_factory=(
                llm_factory if llm_factory is not None else build_demo_llm_factory()
            ),
        )
        launcher = self._tui_launcher
        if launcher is None:
            launcher = _default_tui_launcher
        return launcher(spec)

    @staticmethod
    def _build_openai_adapter(args: argparse.Namespace) -> object:
        # Imported lazily as well: the real adapter is only needed for
        # this one option, and its missing-key failure is a CLI error.
        from vespercode.llm.v2_openai_adapter import V2OpenAICompatLLM

        return V2OpenAICompatLLM(base_url=args.base_url, model=args.model)


def _default_tui_launcher(spec: object) -> int:
    """Run the textual streaming TUI (textual imported only here)."""

    from vespercode.tui.v2_app import run_v2_tui

    return run_v2_tui(spec)


def main(argv: Sequence[str] | None = None) -> int:
    """The ``vespercode-v2`` console entry point (offline, no secrets)."""

    return V2CliComposition().run(argv)


__all__ = [
    "V2_CLI_DEFAULT_PORT",
    "V2CliComposition",
    "build_v2_cli_parser",
    "main",
]


if __name__ == "__main__":  # pragma: no cover - exercised via a real subprocess
    raise SystemExit(main())
