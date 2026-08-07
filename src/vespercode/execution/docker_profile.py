"""T18.1 legacy step 18.A: closed Docker execution request and readiness.

``ExecutionArgumentSequenceV1`` is the immutable ordered adapter-built
argv (the frozen executable is argv[0]; no executable field exists
anywhere in the request contract); ``DockerEnvironmentV1`` is the exact
§1.4.5 whitelist; ``DockerResourceLimitsV1`` pins the exact frozen
limits; ``DockerExecutionProfileV1`` closes every §1.4.5 isolation,
capability, mount, workdir, resource, and environment parameter;
``ExecutionRequestV1`` binds every request to the frozen built-in
reference profile, image, and execution-profile identities; and
``DockerReadinessService.verify`` fails closed on manifest, profile, or
daemon/image drift before any container creation (SPEC §4.1 step 11,
§8.2).  Tree materialization, container creation, output collection,
result interpretation, image build, and installation remain out of scope
(GREEN-4).
"""

from __future__ import annotations

from typing import Annotated, Callable, Literal, Protocol, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictStr,
    field_validator,
    model_validator,
)

from vespercode.contracts.evidence import _DIGEST_RE
from vespercode.contracts.optional import AbsentV1, PresentV1
from vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    _compute_manifest_digest,
)

# The frozen T02.4 manifest identity (SPEC §1.4.1/§1.4.5): the §0.1 digest
# and the bound docker image digest of
# reference/manifest/reference-profile-v1.json.  They are embedded here so
# a request or readiness verdict can never silently bind a drifted
# built-in; the T06.2 loader verifies the packaged bytes against its own
# gate identity constants.
_FROZEN_REFERENCE_PROFILE_DIGEST = (
    "896416f10ed751c4a2ebf763bb3cc6ba0ac90f0ca9e411bdc39c4ca0b93c4bca"
)
_FROZEN_DOCKER_IMAGE_DIGEST = (
    "385ffc69d83536e1874d73517b8b9ee2a0dce6166ca0f30c1f3b1021324ea1a8"
)
_FROZEN_EXECUTION_PROFILE_VERSION = 1

# The exact profile v1 environment whitelist (SPEC §1.4.5): the five frozen
# variables.  Profile v1 closed-defines the Harness report-channel variable
# set as empty: the fixed report channel is the container stdout stream
# (the T02.4-proven mechanism, because docker cp cannot cross tmpfs
# mounts), so v1 injects no additional environment variables; a future
# channel that needs env variables requires an execution-profile version
# bump.
_FROZEN_ENVIRONMENT_VARIABLES: tuple[tuple[str, str], ...] = (
    ("LANG", "C.UTF-8"),
    ("LC_ALL", "C.UTF-8"),
    ("PYTHONDONTWRITEBYTECODE", "1"),
    ("PYTHONHASHSEED", "0"),
    ("TZ", "UTC"),
)

# The exact profile v1 resource limits (SPEC §1.4.5): 2 CPU, 2 GiB memory,
# 256 PIDs, 256 MiB tmpfs, 4 MiB single-check output.
_FROZEN_CPUS = 2
_FROZEN_MEMORY_BYTES = 2 * 1024**3
_FROZEN_PIDS_LIMIT = 256
_FROZEN_TMPFS_SIZE_BYTES = 256 * 1024**2
_FROZEN_MAX_OUTPUT_BYTES = 4 * 1024**2


def _require_exact_int_one(value: object) -> int:
    """Reject bool/float/string spelling of the integer literal 1.

    Pydantic lax mode would otherwise coerce ``true`` or ``1.0`` into a
    ``Literal[1]`` field (T06.1 lesson); the closed T05.1 convention pins
    Strict on scalar fields, so every type-confused spelling rejects.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("value must be the decimal integer 1")
    return value


def _require_exact_bool(value: object) -> bool:
    """Reject int/float/string spelling of a boolean literal field."""
    if not isinstance(value, bool):
        raise ValueError("value must be the boolean literal")
    return value


def _require_digest_form(value: str) -> str:
    """Reject any spelling that is not exactly 64 lowercase hex chars."""
    if _DIGEST_RE.fullmatch(value) is None:
        raise ValueError("must be exactly 64 lowercase hexadecimal characters")
    return value


class ExecutionArgumentSequenceV1(BaseModel):
    """Immutable ordered adapter-built argv (SPEC §4.5: fixed argv, no shell).

    The frozen executable is argv[0]; there is no separate executable
    field anywhere in the request contract, so a model-supplied
    executable, argv, or shell cannot enter the closed contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    arguments: tuple[StrictStr, ...]

    @field_validator("arguments")
    @classmethod
    def _require_executable_and_non_empty_arguments(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if not value:
            raise ValueError("argv must contain at least the frozen executable")
        if any(argument == "" for argument in value):
            raise ValueError("argv arguments must be non-empty")
        return value


class DockerEnvironmentVariableV1(BaseModel):
    """One exact whitelist entry: name and value are both frozen."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: StrictStr
    value: StrictStr


class DockerEnvironmentV1(BaseModel):
    """The closed profile v1 environment whitelist (SPEC §1.4.5).

    The container environment must be exactly the frozen whitelist: any
    widened, narrowed, duplicated, or value-drifted set rejects
    deterministically.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    variables: tuple[DockerEnvironmentVariableV1, ...]

    @model_validator(mode="after")
    def _require_exact_frozen_whitelist(self) -> DockerEnvironmentV1:
        pairs = tuple((variable.name, variable.value) for variable in self.variables)
        if len(set(pairs)) != len(pairs):
            raise ValueError("environment variables must be unique")
        if set(pairs) != set(_FROZEN_ENVIRONMENT_VARIABLES):
            raise ValueError(
                "environment must be exactly the frozen profile v1 whitelist"
            )
        return self


class DockerResourceLimitsV1(BaseModel):
    """The exact frozen profile v1 resource limits (SPEC §1.4.5).

    Every limit is pinned to the frozen value; mutable or widened
    resources cannot exist in the closed contract.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    cpus: Annotated[int, Strict()]
    memory_bytes: Annotated[int, Strict()]
    pids_limit: Annotated[int, Strict()]
    tmpfs_size_bytes: Annotated[int, Strict()]
    max_output_bytes: Annotated[int, Strict()]

    @model_validator(mode="after")
    def _require_exact_frozen_limits(self) -> DockerResourceLimitsV1:
        if (
            self.cpus,
            self.memory_bytes,
            self.pids_limit,
            self.tmpfs_size_bytes,
            self.max_output_bytes,
        ) != (
            _FROZEN_CPUS,
            _FROZEN_MEMORY_BYTES,
            _FROZEN_PIDS_LIMIT,
            _FROZEN_TMPFS_SIZE_BYTES,
            _FROZEN_MAX_OUTPUT_BYTES,
        ):
            raise ValueError("resources must equal the frozen profile v1 limits")
        return self


class WorkspaceMountV1(BaseModel):
    """The sole candidate-tree mount: read-only /workspace (SPEC §1.4.5).

    The authoritative workspace, control-plane database, credentials, and
    transaction backups can never be mounted, because the mount set is
    closed to this single read-only bind.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    target: Literal["/workspace"]
    read_only: Literal[True]

    @field_validator("read_only", mode="before")
    @classmethod
    def _read_only_is_exact_bool(cls, value: object) -> object:
        return _require_exact_bool(value)


class TmpfsMountV1(BaseModel):
    """The sole bounded tmpfs mount: /tmp (SPEC §1.4.5, T02.2 evidence)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    path: Literal["/tmp"]


class DockerExecutionProfileV1(BaseModel):
    """The frozen Docker execution profile v1 (SPEC §1.4.5).

    Every isolation, capability, mount, workdir, resource, and
    environment parameter is closed to the frozen v1 values selected by
    ``ReferenceProfileManifestV1.docker_execution_profile_version=1``;
    profile drift can never validate.  The non-root user 10001:10001 is
    the frozen T02.2 real-container run parameter; the profile also pins
    fresh containers per check and disabled pytest plugin auto-loading.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    profile_version: Literal[1]
    network_mode: Literal["none"]
    user: Literal["10001:10001"]
    read_only_rootfs: Literal[True]
    capabilities_dropped: Literal["ALL"]
    docker_socket_mounted: Literal[False]
    workdir: Literal["/workspace"]
    workspace_mount: WorkspaceMountV1
    tmpfs_mount: TmpfsMountV1
    resources: DockerResourceLimitsV1
    environment: DockerEnvironmentV1
    fresh_container_per_check: Literal[True]
    pytest_plugin_autoload_disabled: Literal[True]

    @field_validator("schema_version", "profile_version", mode="before")
    @classmethod
    def _version_is_exact_int(cls, value: object) -> object:
        return _require_exact_int_one(value)

    @field_validator(
        "read_only_rootfs",
        "docker_socket_mounted",
        "fresh_container_per_check",
        "pytest_plugin_autoload_disabled",
        mode="before",
    )
    @classmethod
    def _flags_are_exact_bools(cls, value: object) -> object:
        return _require_exact_bool(value)


class ExecutionRequestV1(BaseModel):
    """The sole closed execution request bound to frozen built-ins.

    The request binds the frozen reference profile digest, the frozen
    docker image digest, and execution profile version 1 (SPEC §1.4.1/
    §1.4.5); a request that is not bound to those frozen built-ins
    rejects before any container creation.  argv is the only per-check
    variance and is always the adapter-built immutable sequence;
    model-supplied executable/argv/environment fields do not exist in
    the schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    request_id: StrictStr
    reference_profile_digest: StrictStr
    docker_image_digest: StrictStr
    docker_execution_profile_version: Literal[1]
    profile: DockerExecutionProfileV1
    argv: ExecutionArgumentSequenceV1

    @field_validator(
        "schema_version", "docker_execution_profile_version", mode="before"
    )
    @classmethod
    def _version_is_exact_int(cls, value: object) -> object:
        return _require_exact_int_one(value)

    @field_validator("reference_profile_digest", "docker_image_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @field_validator("request_id")
    @classmethod
    def _request_id_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("request id must be non-empty")
        return value

    @model_validator(mode="after")
    def _require_frozen_builtin_binding(self) -> ExecutionRequestV1:
        if self.reference_profile_digest != _FROZEN_REFERENCE_PROFILE_DIGEST:
            raise ValueError(
                "request must be bound to the frozen built-in reference profile"
            )
        if self.docker_image_digest != _FROZEN_DOCKER_IMAGE_DIGEST:
            raise ValueError(
                "request must be bound to the frozen reference image digest"
            )
        return self


ReadinessFailureReasonV1 = Literal[
    "MANIFEST_DIGEST_MISMATCH",
    "EXECUTION_PROFILE_VERSION_MISMATCH",
    "DAEMON_UNAVAILABLE",
    "IMAGE_NOT_FOUND",
    "IMAGE_DIGEST_MISMATCH",
]
"""Closed not-ready reasons (SPEC §4.1 step 11; §8.2 fail-closed)."""

OptionalReadinessFailureReasonV1: TypeAlias = Annotated[
    AbsentV1 | PresentV1[ReadinessFailureReasonV1],
    Field(discriminator="kind"),
]
"""Closed optional reason: ABSENT exactly when the result is READY."""


class ExecutionReadinessResultV1(BaseModel):
    """One readiness verdict bound to the manifest's declared digests.

    The digests are verified only when the verdict is READY; a NOT_READY
    verdict carries the manifest's declared values so the caller can see
    which identity drifted.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["READY", "NOT_READY"]
    reference_profile_digest: StrictStr
    docker_image_digest: StrictStr
    reason: OptionalReadinessFailureReasonV1

    @field_validator("reference_profile_digest", "docker_image_digest")
    @classmethod
    def _digests_have_exact_form(cls, value: str) -> str:
        return _require_digest_form(value)

    @model_validator(mode="after")
    def _require_exact_reason_presence(self) -> ExecutionReadinessResultV1:
        if self.status == "READY" and self.reason.kind != "ABSENT":
            raise ValueError("READY results must carry an ABSENT reason")
        if self.status == "NOT_READY" and self.reason.kind != "PRESENT":
            raise ValueError("NOT_READY results must carry a PRESENT reason")
        return self


class DockerDaemonUnavailableErrorV1(RuntimeError):
    """Closed probe failure: the Docker SDK or daemon is not available."""


class LocalImageDigestProbeV1(Protocol):
    """Read-only probe of the exact local image digest set.

    Implementations raise ``DockerDaemonUnavailableErrorV1`` when the
    daemon cannot be queried; the readiness service fails closed on that
    error.  Probing never creates containers or modifies the daemon.
    """

    def local_image_digests(self) -> frozenset[str]: ...


def _bare_digest_token(value: str) -> str | None:
    """The exact 64-hex token after a ``sha256:`` marker, else None.

    Handles both ``sha256:<hex>`` Ids and ``repo@sha256:<hex>`` RepoDigest
    spellings; any other token is ignored (never treated as a digest).
    """
    marker = "sha256:"
    index = value.rfind(marker)
    token = value[index + len(marker) :] if index >= 0 else value
    if _DIGEST_RE.fullmatch(token) is None:
        return None
    return token


class _SDKAPIClientV1(Protocol):
    """The Docker SDK low-level images-list surface used by the probe."""

    def images(self, all: bool = False) -> list[dict[str, object]]: ...


class _SDKClientV1(Protocol):
    """The Docker SDK high-level client surface used by the probe."""

    @property
    def api(self) -> _SDKAPIClientV1: ...


class DockerSDKImageProbeV1:
    """Real local-image probe over the Docker SDK (read-only, no containers).

    Collects the exact bare 64-hex digest tokens of every local image Id
    and RepoDigest through the low-level images endpoint; the client
    factory is injectable so the extraction logic runs deterministically
    offline.  Any SDK or daemon failure raises
    ``DockerDaemonUnavailableErrorV1``.
    """

    def __init__(
        self, client_factory: Callable[[], _SDKClientV1] | None = None
    ) -> None:
        self._client_factory = client_factory

    def local_image_digests(self) -> frozenset[str]:
        if self._client_factory is None:
            try:
                import docker  # type: ignore[import-untyped]
            except Exception as exc:
                raise DockerDaemonUnavailableErrorV1(
                    "Docker SDK is not available"
                ) from exc
            client_factory = docker.from_env
        else:
            client_factory = self._client_factory
        try:
            client = client_factory()
            digests: set[str] = set()
            for image in client.api.images(all=False):
                digest = _bare_digest_token(str(image.get("Id") or ""))
                if digest is not None:
                    digests.add(digest)
                for repo_digest in image.get("RepoDigests") or []:
                    digest = _bare_digest_token(str(repo_digest))
                    if digest is not None:
                        digests.add(digest)
            return frozenset(digests)
        except Exception as exc:
            raise DockerDaemonUnavailableErrorV1("Docker daemon query failed") from exc


class DockerReadinessService:
    """Fail-closed local reference-image readiness verification.

    ``verify`` checks the manifest's own digest binding, the frozen
    execution profile version, the frozen built-in manifest and image
    identities, then probes the local daemon for the exact image digest
    bound by the manifest (SPEC §4.1 step 11): manifest, profile, daemon,
    or image drift yields the closed NOT_READY result with its stable
    reason, and no container is ever created (GREEN-4).
    """

    def __init__(self, probe: LocalImageDigestProbeV1 | None = None) -> None:
        self._probe = probe if probe is not None else DockerSDKImageProbeV1()

    def verify(
        self, reference: ReferenceProfileManifestV1
    ) -> ExecutionReadinessResultV1:
        if reference.digest != _compute_manifest_digest(reference):
            return self._not_ready(reference, "MANIFEST_DIGEST_MISMATCH")
        if (
            reference.docker_execution_profile_version
            != _FROZEN_EXECUTION_PROFILE_VERSION
        ):
            return self._not_ready(reference, "EXECUTION_PROFILE_VERSION_MISMATCH")
        if reference.docker_image_digest != _FROZEN_DOCKER_IMAGE_DIGEST:
            return self._not_ready(reference, "IMAGE_DIGEST_MISMATCH")
        if reference.digest != _FROZEN_REFERENCE_PROFILE_DIGEST:
            return self._not_ready(reference, "MANIFEST_DIGEST_MISMATCH")
        try:
            local_digests = self._probe.local_image_digests()
        except DockerDaemonUnavailableErrorV1:
            return self._not_ready(reference, "DAEMON_UNAVAILABLE")
        target = reference.docker_image_digest
        if target in local_digests:
            return ExecutionReadinessResultV1(
                status="READY",
                reference_profile_digest=reference.digest,
                docker_image_digest=target,
                reason=AbsentV1(kind="ABSENT"),
            )
        if local_digests:
            return self._not_ready(reference, "IMAGE_DIGEST_MISMATCH")
        return self._not_ready(reference, "IMAGE_NOT_FOUND")

    def _not_ready(
        self,
        reference: ReferenceProfileManifestV1,
        reason: ReadinessFailureReasonV1,
    ) -> ExecutionReadinessResultV1:
        return ExecutionReadinessResultV1(
            status="NOT_READY",
            reference_profile_digest=reference.digest,
            docker_image_digest=reference.docker_image_digest,
            reason=PresentV1(kind="PRESENT", value=reason),
        )
