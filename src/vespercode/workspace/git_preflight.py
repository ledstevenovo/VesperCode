"""T09.1 legacy step 9.C: sealed Git snapshot preflight.

``run_git_snapshot_prechecks`` invokes Git without a shell under a closed
configuration/environment and freezes the exact config, index, HEAD,
worktree, ignore, attribute, and conversion state before any Snapshot can
exist (T09.1 owns no Snapshot capability — GREEN-4).  Every unsupported
state — skip-worktree, assume-unchanged, intent-to-add, unmerged,
submodule, symlink, unsupported mode, case/Unicode collision, unstable
index, index drift, dirty tracked input, untracked non-ignored files,
sensitive tracked paths, forbidden conversions, external config, or
identity drift — rejects with a stable closed error and zero Snapshot
rows.  The result is sealed non-secret observations only; no repository
byte is ever written (``--no-optional-locks`` prevents index refresh).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Mapping, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    field_validator,
    model_validator,
)

from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.profiles.reference import ReferenceProfileManifestV1
from vespercode.workspace.identity_win32 import WorkspaceIdentityV1
from vespercode.workspace.path_guard import (
    IgnoreRuleV1,
    ignore_rules_digest,
    protected_artifact_path,
    sensitive_path_rule_id,
)

GitPreflightErrorCodeV1 = Literal[
    "UNSUPPORTED_REPOSITORY", "WORKTREE_DIRTY", "SENSITIVE_TRACKED_FILE"
]

_GIT_CAPS: Final = ("-c", "core.quotepath=false", "--no-pager", "--no-optional-locks")
_SUPPORTED_FILE_MODES: Final = frozenset({"100644", "100755"})
_SYMLINK_MODE: Final = "120000"
_GITLINK_MODE: Final = "160000"
# SPEC §1.4.4 repository hard caps.
_MAX_TRACKED_FILES: Final = 5_000
_MAX_TRACKED_TOTAL_BYTES: Final = 128 * 1024 * 1024
_MAX_SINGLE_TRACKED_BYTES: Final = 4 * 1024 * 1024


class GitPreflightError(Exception):
    """Closed failure when the sealed Git observation itself cannot run."""


class GitPreflightCollisionV1(Exception):
    """Closed structural collision that maps to UNSUPPORTED_REPOSITORY."""


class GitPreflightResultV1(BaseModel):
    """The sealed non-secret Git snapshot preflight result.

    On SUPPORTED every observation digest is present and the frozen
    ``repository_policy_digest`` binds the reference editable policy; on
    REJECTED the stable error code and reason are present and the
    observations gathered before the failing check remain sealed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    kind: Literal["SUPPORTED", "REJECTED"]
    error_code: GitPreflightErrorCodeV1 | None = None
    reason: str | None = None
    head_commit_digest: str | None = None
    index_digest: str | None = None
    worktree_digest: str | None = None
    ignore_rules_digest: str | None = None
    attributes_digest: str | None = None
    config_digest: str | None = None
    ignore_rules: tuple[IgnoreRuleV1, ...] = ()
    repository_policy_digest: str | None = None
    core_autocrlf_enabled: StrictBool = False
    core_eol_enabled: StrictBool = False
    external_attributesfile: StrictBool = False
    external_excludesfile: StrictBool = False
    conversion_attributes_present: StrictBool = False
    tracked_file_count: int | None = None
    tracked_byte_count: int | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_exact_int(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the decimal integer 1")
        return value

    @field_validator(
        "index_digest",
        "worktree_digest",
        "ignore_rules_digest",
        "attributes_digest",
        "config_digest",
        "repository_policy_digest",
        mode="before",
    )
    @classmethod
    def _sha256_hex_or_none(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            raise ValueError(
                "sealed digests must be exactly 64 lowercase hexadecimal characters"
            )
        return value

    @field_validator("head_commit_digest", mode="before")
    @classmethod
    def _git_sha_or_none(cls, value: object) -> object:
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or len(value) != 40
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("head commit digest must be a 40-character git object id")
        return value

    @field_validator("tracked_file_count", "tracked_byte_count", mode="before")
    @classmethod
    def _exact_int_or_none(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("tracked counts must be exact decimal integers")
        if value < 0:
            raise ValueError("tracked counts must not be negative")
        return value

    @model_validator(mode="after")
    def _require_exact_outcome(self) -> GitPreflightResultV1:
        if self.kind == "SUPPORTED":
            if self.error_code is not None or self.reason is not None:
                raise ValueError("SUPPORTED results must not carry rejection fields")
            if self.repository_policy_digest is None:
                raise ValueError("SUPPORTED results must bind the repository policy")
        elif self.error_code is None or self.reason is None:
            raise ValueError("REJECTED results require the error code and reason")
        return self


@dataclass(frozen=True)
class _IndexEntryV1:
    mode: str
    object_sha: str
    stage: int
    path: str


def _closed_env(home: Path) -> dict[str, str]:
    """One minimal deterministic Git environment.

    System/global configuration, external attributes/ignore files, and
    terminal prompts are disabled; only the platform variables Git needs
    on Windows survive, plus the fixed locale for stable output.
    """
    return {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "TEMP": os.environ.get("TEMP", str(home)),
        "TMP": os.environ.get("TMP", str(home)),
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "",
        "GIT_CONFIG_SYSTEM": "",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "LANG": "C",
    }


def _git(
    argv: Sequence[str], cwd: Path, env: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    """Invoke Git without a shell under the closed environment."""
    return subprocess.run(
        ["git", *_GIT_CAPS, *argv],
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )


def _git_checked(argv: Sequence[str], cwd: Path, env: Mapping[str, str]) -> str:
    """Run one observation command and fail closed on any non-zero exit.

    A failed observation must never be sealed as empty evidence (an
    empty flags map or a "clean" worktree digest would silently pass the
    structural gates).
    """
    completed = _git(argv, cwd, env)
    if completed.returncode != 0:
        raise GitPreflightError(
            f"git {' '.join(argv)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout


def _index_bytes(cwd: Path, env: Mapping[str, str]) -> bytes:
    """The exact ``git ls-files --stage`` bytes of the current index."""
    completed = _git(["ls-files", "--stage"], cwd, env)
    if completed.returncode != 0:
        raise GitPreflightError(
            f"git ls-files --stage failed: {completed.stderr.strip()}"
        )
    return completed.stdout.encode("utf-8")


def _parse_index(stage_text: str) -> list[_IndexEntryV1]:
    entries: list[_IndexEntryV1] = []
    for line in stage_text.splitlines():
        fields, path = line.split("\t", 1)
        mode, object_sha, stage = fields.split(" ")
        entries.append(
            _IndexEntryV1(
                mode=mode,
                object_sha=object_sha,
                stage=int(stage),
                path=path,
            )
        )
    return entries


def _parse_index_flags(flags_text: str) -> dict[str, str]:
    """Map each index path to its ``git ls-files -v`` flag letter.

    The observed letters on Windows Git 2.47 are: ``H`` cached,
    ``S`` skip-worktree, ``h`` assume-unchanged; the documented
    ``M``/``m`` spellings are accepted for assume-unchanged as well so
    the rejection does not depend on a single Git build's letters.
    """
    flags: dict[str, str] = {}
    for line in flags_text.splitlines():
        if len(line) >= 2 and line[1] == " ":
            flags[line[2:]] = line[0]
    return flags


def _parse_config(config_text: str) -> dict[str, str]:
    """Parse the NUL-delimited ``git config --list -z`` records.

    Each record is ``key\\nvalue\\0`` (multi-valued keys carry several
    newline-separated values); the last value of a key is the effective
    one for the closed conversion checks.
    """
    pairs: dict[str, str] = {}
    for chunk in config_text.split("\0"):
        if not chunk:
            continue
        lines = chunk.split("\n")
        pairs[lines[0]] = lines[-1] if len(lines) > 1 else ""
    return pairs


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_gitignore_rules(
    content: str, source: Literal["GITIGNORE", "INFO_EXCLUDE"], base: str
) -> list[IgnoreRuleV1]:
    rules: list[IgnoreRuleV1] = []
    for raw_line in content.splitlines():
        line = raw_line.rstrip("\r").strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        directory_only = line.endswith("/")
        if directory_only:
            line = line[:-1]
        if not line:
            continue
        rules.append(
            IgnoreRuleV1(
                schema_version=1,
                source=source,
                base_directory=base,
                pattern=line,
                negated=negated,
                directory_only=directory_only,
            )
        )
    return rules


def _enumerate_config_files(
    root: Path,
    tracked_paths: Sequence[str],
    untracked_paths: Sequence[str],
    filename: str,
    env: Mapping[str, str],
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Enumerate every ``filename`` file visible in the worktree.

    Returns (path, bytes) pairs in deterministic sorted order and the
    sorted path list, from tracked paths plus untracked non-ignored
    paths.
    """
    candidates = sorted(
        {path for path in tracked_paths if path.rsplit("/", 1)[-1] == filename}
        | {path for path in untracked_paths if path.rsplit("/", 1)[-1] == filename}
    )
    found: list[tuple[str, bytes]] = []
    for relative in candidates:
        target = root / relative
        try:
            found.append((relative, target.read_bytes()))
        except OSError as error:
            raise GitPreflightError(f"cannot read {relative}: {error}") from error
    return found, candidates


def _attributes_have_conversion(content: bytes) -> bool:
    """True when any attribute line enables a content conversion.

    Rejected conversion attributes per SPEC §1.4.1: ``eol``,
    ``working-tree-encoding``, and content ``filter``.  Line comments
    and whitespace are stripped before the attribute tokens are scanned.
    """
    for raw_line in content.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = line.split()
        for token in tokens[1:]:
            if (
                token in ("filter",)
                or token.startswith("eol=")
                or token.startswith("working-tree-encoding=")
                or token.startswith("filter=")
            ):
                return True
    return False


def _reject_result(
    error_code: GitPreflightErrorCodeV1,
    reason: str,
    seals: dict[str, object],
) -> GitPreflightResultV1:
    return GitPreflightResultV1.model_validate(
        {
            "schema_version": 1,
            "kind": "REJECTED",
            "error_code": error_code,
            "reason": reason,
            **seals,
        }
    )


def run_git_snapshot_prechecks(
    identity: WorkspaceIdentityV1, reference: ReferenceProfileManifestV1
) -> GitPreflightResultV1:
    """Freeze and validate the exact Git state before any Snapshot.

    The workspace root must match the sealed identity; HEAD must be
    valid; the index must be structurally supported and stable; the
    worktree must be byte-clean; every tracked path must be a supported
    single-link object that is neither sensitive nor converted; and the
    frozen ignore/attribute rules are sealed with the repository policy
    digest bound to ``reference.editable_path_policy.digest``.  Any
    violation rejects deterministically with zero Snapshot rows.
    """
    try:
        identity.verify_integrity()
    except ValueError as error:
        raise GitPreflightError("workspace identity is not sealed") from error
    repository_policy_digest = reference.editable_path_policy.digest
    root = Path(identity.canonical_absolute_path)
    if not root.is_dir():
        return GitPreflightResultV1(
            schema_version=1,
            kind="REJECTED",
            error_code="UNSUPPORTED_REPOSITORY",
            reason="the sealed workspace root does not exist",
            repository_policy_digest=repository_policy_digest,
        )
    home = Path(tempfile.mkdtemp(prefix="vespercode-git-home-"))
    try:
        env = _closed_env(home)
        worktree = _worktree_facts(root, env)
        if worktree is None:
            return _reject_result(
                "UNSUPPORTED_REPOSITORY",
                "the workspace is not a git worktree",
                {},
            )
        toplevel, git_dir, is_bare, is_inside = worktree
        if not is_inside or is_bare:
            return _reject_result(
                "UNSUPPORTED_REPOSITORY",
                "the workspace is not a non-bare git worktree",
                {},
            )
        if _abs_of_maybe_relative(git_dir, root) != os.path.normcase(
            os.path.abspath(str(root / ".git"))
        ):
            return _reject_result(
                "UNSUPPORTED_REPOSITORY",
                "the git directory is not the identity workspace root",
                {},
            )
        if os.path.normcase(os.path.abspath(toplevel)) != os.path.normcase(
            identity.canonical_absolute_path
        ):
            return _reject_result(
                "UNSUPPORTED_REPOSITORY",
                "git workspace root drifted from the sealed identity",
                {},
            )
        head = _head_digest(root, env)
        if head is None:
            return _reject_result("UNSUPPORTED_REPOSITORY", "HEAD is unborn", {})
        config = _read_config(root, env)
        config_digest = _digest(config.encode("utf-8"))
        config_flags = _parse_config(config)
        first_stage = _index_bytes(root, env)
        second_stage = _index_bytes(root, env)
        if first_stage != second_stage:
            return _reject_result(
                "UNSUPPORTED_REPOSITORY",
                "the index changed between two sealed reads",
                {
                    "head_commit_digest": head,
                    "config_digest": config_digest,
                    "repository_policy_digest": repository_policy_digest,
                    "core_autocrlf_enabled": _autocrlf_enabled(config_flags),
                    "core_eol_enabled": "core.eol" in config_flags,
                    "external_attributesfile": "core.attributesfile" in config_flags,
                    "external_excludesfile": "core.excludesfile" in config_flags,
                },
            )
        index_digest = _digest(first_stage)
        entries = _parse_index(first_stage.decode("utf-8"))
        flags = _parse_index_flags(_git_checked(["ls-files", "-v"], root, env))
        untracked = _git_checked(
            ["ls-files", "--others", "--exclude-standard"], root, env
        ).splitlines()
        ignored = _git_checked(
            ["ls-files", "--others", "--exclude-standard", "--ignored"], root, env
        ).splitlines()
        status = _git_checked(
            ["status", "--porcelain", "--untracked-files=all"], root, env
        )
        worktree_digest = _digest(status.encode("utf-8"))
        ignore_files, ignore_paths = _enumerate_config_files(
            root, [entry.path for entry in entries], untracked, ".gitignore", env
        )
        attribute_files, attribute_paths = _enumerate_config_files(
            root, [entry.path for entry in entries], untracked, ".gitattributes", env
        )
        rules = _seal_ignore_rules(root, ignore_files, env)
        ignore_digest = ignore_rules_digest(rules)
        attributes_digest = _digest(
            b"\n".join(content for _, content in attribute_files)
        )
        conversion_present = any(
            _attributes_have_conversion(content) for _, content in attribute_files
        )
        autocrlf = _autocrlf_enabled(config_flags)
        eol_present = "core.eol" in config_flags
        external_attributes = "core.attributesfile" in config_flags
        external_excludes = "core.excludesfile" in config_flags
        tracked_count, tracked_bytes, tracked_largest = _tracked_totals(
            root, entries, env
        )
        seals: dict[str, object] = {
            "head_commit_digest": head,
            "index_digest": index_digest,
            "worktree_digest": worktree_digest,
            "ignore_rules_digest": ignore_digest,
            "attributes_digest": attributes_digest,
            "config_digest": config_digest,
            "ignore_rules": rules,
            "repository_policy_digest": repository_policy_digest,
            "core_autocrlf_enabled": autocrlf,
            "core_eol_enabled": eol_present,
            "external_attributesfile": external_attributes,
            "external_excludesfile": external_excludes,
            "conversion_attributes_present": conversion_present,
            "tracked_file_count": tracked_count,
            "tracked_byte_count": tracked_bytes,
        }
        structural = _structural_index_error(entries, flags, status)
        if structural is not None:
            return _reject_result("UNSUPPORTED_REPOSITORY", structural, seals)
        if _has_gitmodules(entries, root):
            return _reject_result(
                "UNSUPPORTED_REPOSITORY",
                "submodule configuration is not supported",
                seals,
            )
        if _index_drifted(root, env):
            return _reject_result(
                "UNSUPPORTED_REPOSITORY", "the index tree drifted from HEAD", seals
            )
        # Forbidden conversions are repository-structure facts and are
        # checked before worktree dirtiness: an enabled conversion (e.g.
        # ``eol=crlf``) itself makes git report a converted worktree as
        # dirty, and the conversion is the determinable root cause.
        if (
            autocrlf
            or eol_present
            or external_attributes
            or external_excludes
            or conversion_present
        ):
            return _reject_result(
                "UNSUPPORTED_REPOSITORY",
                "a forbidden Git conversion or external configuration is enabled",
                seals,
            )
        if tracked_count > _MAX_TRACKED_FILES:
            return _reject_result(
                "UNSUPPORTED_REPOSITORY",
                f"tracked file count {tracked_count} exceeds the 5,000 cap",
                seals,
            )
        if tracked_bytes > _MAX_TRACKED_TOTAL_BYTES:
            return _reject_result(
                "UNSUPPORTED_REPOSITORY",
                f"tracked byte total {tracked_bytes} exceeds the 128 MiB cap",
                seals,
            )
        if tracked_largest > _MAX_SINGLE_TRACKED_BYTES:
            return _reject_result(
                "UNSUPPORTED_REPOSITORY",
                f"a single tracked file of {tracked_largest} bytes exceeds the 4 MiB cap",
                seals,
            )
        worktree_error = _worktree_status_error(status)
        if worktree_error is not None:
            code, reason = worktree_error
            return _reject_result(code, reason, seals)
        for entry in entries:
            if sensitive_path_rule_id(entry.path) is not None:
                return _reject_result(
                    "SENSITIVE_TRACKED_FILE",
                    f"tracked path {entry.path!r} is sensitive",
                    seals,
                )
        for path in ignored:
            if sensitive_path_rule_id(path) is not None or protected_artifact_path(
                path
            ):
                return _reject_result(
                    "UNSUPPORTED_REPOSITORY",
                    f"untracked path {path!r} hits a sensitive or protected rule",
                    seals,
                )
        return GitPreflightResultV1.model_validate(
            {
                "schema_version": 1,
                "kind": "SUPPORTED",
                **seals,
            }
        )
    finally:
        shutil.rmtree(home, ignore_errors=True)


def _worktree_facts(
    root: Path, env: Mapping[str, str]
) -> tuple[str, str, bool, bool] | None:
    """The four root facts, or None when the path is not a worktree."""
    completed = _git(
        [
            "rev-parse",
            "--show-toplevel",
            "--git-dir",
            "--is-bare-repository",
            "--is-inside-work-tree",
        ],
        root,
        env,
    )
    if completed.returncode != 0:
        return None
    lines = completed.stdout.splitlines()
    if len(lines) != 4:
        raise GitPreflightError("git rev-parse returned an unexpected shape")
    return lines[0], lines[1], lines[2] == "true", lines[3] == "true"


def _abs_of_maybe_relative(path: str, root: Path) -> str:
    """One absolute normalized path, resolving git-relative output
    against the workspace root (never the harness process cwd)."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    return os.path.normcase(os.path.abspath(str(candidate)))


def _head_digest(root: Path, env: Mapping[str, str]) -> str | None:
    completed = _git(["rev-parse", "--verify", "HEAD"], root, env)
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value if len(value) == 40 else None


def _read_config(root: Path, env: Mapping[str, str]) -> str:
    completed = _git(["config", "--local", "--list", "-z"], root, env)
    if completed.returncode != 0:
        raise GitPreflightError(
            f"git config --local --list failed: {completed.stderr.strip()}"
        )
    return completed.stdout


def _autocrlf_enabled(config_flags: dict[str, str]) -> bool:
    """True unless core.autocrlf is absent or exactly ``false``.

    Any other value (``true``, ``input``, ``1``) enables line-ending
    conversion and is unsupported per SPEC §1.4.1.
    """
    return config_flags.get("core.autocrlf") not in (None, "false")


def _seal_ignore_rules(
    root: Path,
    ignore_files: list[tuple[str, bytes]],
    env: Mapping[str, str],
) -> tuple[IgnoreRuleV1, ...]:
    rules: list[IgnoreRuleV1] = []
    for relative, content in ignore_files:
        base = relative[: -len(".gitignore")].rstrip("/")
        rules.extend(
            _parse_gitignore_rules(
                content.decode("utf-8", errors="replace"), "GITIGNORE", base
            )
        )
    exclude_path = root / ".git" / "info" / "exclude"
    try:
        exclude_bytes = exclude_path.read_bytes()
    except OSError as error:
        raise GitPreflightError(
            f"cannot read the sealed info/exclude rules: {error}"
        ) from error
    rules.extend(
        _parse_gitignore_rules(
            exclude_bytes.decode("utf-8", errors="replace"), "INFO_EXCLUDE", ""
        )
    )
    return tuple(rules)


def _tracked_totals(
    root: Path, entries: Sequence[_IndexEntryV1], env: Mapping[str, str]
) -> tuple[int, int, int]:
    """The sealed tracked count, raw byte total, and largest single file
    (SPEC §1.4.4: at most 5,000 files, 128 MiB total, 4 MiB each)."""
    blob_shas = [
        entry.object_sha
        for entry in entries
        if entry.mode not in (_GITLINK_MODE,) and len(entry.object_sha) == 40
    ]
    total = 0
    largest = 0
    if blob_shas:
        completed = subprocess.run(
            [
                "git",
                *_GIT_CAPS,
                "cat-file",
                "--batch-check=%(objectname) %(objectsize)",
            ],
            cwd=root,
            env=dict(env),
            input="\n".join(blob_shas) + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise GitPreflightError(
                f"git cat-file --batch-check failed: {completed.stderr.strip()}"
            )
        for line in completed.stdout.splitlines():
            _, _, size = line.partition(" ")
            try:
                total += int(size)
                largest = max(largest, int(size))
            except ValueError:
                raise GitPreflightError(
                    f"git cat-file returned an unexpected line: {line!r}"
                ) from None
    return len(entries), total, largest


def _structural_index_error(
    entries: Sequence[_IndexEntryV1],
    flags: Mapping[str, str],
    status: str,
) -> str | None:
    """The first structural index violation, or None when supported."""
    for entry in entries:
        if entry.stage != 0:
            return f"index entry {entry.path!r} is unmerged"
    for entry in entries:
        letter = flags.get(entry.path, "H")
        if letter in ("S", "s"):
            return f"index entry {entry.path!r} has skip-worktree set"
    for entry in entries:
        letter = flags.get(entry.path, "H")
        if letter in ("h", "M", "m"):
            return f"index entry {entry.path!r} has assume-unchanged set"
    for entry in entries:
        if entry.mode == _GITLINK_MODE:
            return f"index entry {entry.path!r} is a submodule gitlink"
        if entry.mode == _SYMLINK_MODE:
            return f"index entry {entry.path!r} is a symlink"
        if entry.mode not in _SUPPORTED_FILE_MODES:
            return f"index entry {entry.path!r} has unsupported mode {entry.mode}"
    try:
        _reject_path_collisions(entries)
    except GitPreflightCollisionV1 as error:
        return str(error)
    for line in status.splitlines():
        if len(line) >= 4 and line[0] == " " and line[1] == "A":
            return f"index entry {line[3:].strip()!r} is intent-to-add"
    return None


def _reject_path_collisions(entries: Sequence[_IndexEntryV1]) -> None:
    """Reject two distinct index paths that Windows case-fold or NFC
    collide (SPEC §4.1: Windows/Unicode path collisions are unsupported)."""
    folded: dict[str, str] = {}
    for entry in entries:
        key = entry.path.casefold()
        if key in folded and folded[key] != entry.path:
            raise GitPreflightCollisionV1(
                f"index paths {folded[key]!r} and {entry.path!r} case-collide"
            )
        folded[key] = entry.path
    normalized: dict[str, str] = {}
    for entry in entries:
        key = unicodedata.normalize("NFC", entry.path)
        if key in normalized and normalized[key] != entry.path:
            raise GitPreflightCollisionV1(
                f"index paths {normalized[key]!r} and {entry.path!r} unicode-collide"
            )
        normalized[key] = entry.path


def _has_gitmodules(entries: Sequence[_IndexEntryV1], root: Path) -> bool:
    if any(entry.path == ".gitmodules" for entry in entries):
        return True
    return (root / ".gitmodules").exists()


def _index_drifted(root: Path, env: Mapping[str, str]) -> bool:
    completed = _git(["diff", "--cached", "--quiet", "HEAD"], root, env)
    if completed.returncode == 1:
        return True
    if completed.returncode != 0:
        raise GitPreflightError(f"git diff --cached failed: {completed.stderr.strip()}")
    return False


def _worktree_status_error(
    status: str,
) -> tuple[GitPreflightErrorCodeV1, str] | None:
    """The first worktree violation, or None when the worktree is clean."""
    for line in status.splitlines():
        if len(line) < 4:
            continue
        index_letter = line[0]
        worktree_letter = line[1]
        path = line[3:].strip()
        if index_letter in ("M", "A", "D", "R", "C", "T"):
            return (
                "UNSUPPORTED_REPOSITORY",
                f"index entry {path!r} drifted from HEAD",
            )
        if worktree_letter in ("M", "D", "R", "T"):
            return (
                "WORKTREE_DIRTY",
                f"tracked file {path!r} drifted from its HEAD blob",
            )
    for line in status.splitlines():
        if len(line) >= 4 and line[0] == "?" and line[1] == "?":
            return (
                "WORKTREE_DIRTY",
                f"untracked non-ignored file {line[3:].strip()!r}",
            )
    return None
