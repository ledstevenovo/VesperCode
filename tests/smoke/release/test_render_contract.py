"""T36.3 legacy step 36.C: static Render deployment contract tests.

The exact displayed RED test ``test_render_contract_has_no_disk_or_real_provider_secret``
is copied from the T36.3 card with its body byte-identical.  The
already-RED matrix test ``test_render_deployment_matrix`` pins the PLAN
36.C row: the committed config/image contract contains the exact Task
34.B identity, platform PORT, ``/healthz``, no disk or real-provider
secret, and no formal/local/recovery endpoint; fake source/deployment/
image mismatches are rejected with zero external I/O; T36.3 performs no
Render mutation and writes no ``deployment-v1.json``.

The vocabulary (``RenderContractV1`` and the pure
``verify_render_deployment_observation`` verifier) is test-side because
the card owns exactly three files (``render.yaml`` plus the two static
contract test modules) and no ``src/`` module.  T37.1 deploys the
committed ``render.yaml`` alone and supplies the final merged
prerequisite main ``source_commit`` as the live observation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final, Literal, cast
from urllib.parse import urlsplit

import pytest

# The hash-locked gate toolchain does not install runtime
# dependencies (pydantic), so this module skips cleanly there
# instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")
from pydantic import (
    BaseModel,
    ConfigDict,
    HttpUrl,
    StrictBool,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]
_RENDER_YAML: Final = _REPO_ROOT / "render.yaml"

pytestmark = pytest.mark.deployment_smoke

_HEX_CHARS: Final = frozenset("0123456789abcdef")

# The exact Task 34.B Dockerfile path bound by the Render contract (the
# demo image is built locally as ``vespercode-demo:local``; the digest is
# T37.1's live observation, so the static contract binds the recipe path).
DEMO_DOCKERFILE_PATH_V1: Final = "containers/demo/Dockerfile"

# The platform-injected PORT the Demo app binds (SPEC §8.3; the
# Dockerfile EXPOSEs 8000 and the launcher reads ``PORT`` with default
# "8000", so the committed contract injects PORT=8000 exactly).
DEMO_PLATFORM_PORT_V1: Final = 8000

# The exact platform health check path of the Demo app (SPEC §8.3).
DEMO_HEALTH_PATH_V1: Final = "/healthz"

# The exact final prerequisite-main source published as v0.1.0.  Release,
# GHCR, and Render evidence must remain aligned to this immutable subject.
RELEASE_SOURCE_COMMIT_V1: Final = "d31bdeeafe8ad65b60fac213e23fcab9dffdd7aa"

# The closed route surface of the Task 34.B Demo app: the health route,
# the fixed scenario page, and the two session routes (``create_demo_app``
# registers exactly these and disables docs/redoc/openapi).  No formal,
# local, or recovery endpoint kind exists in the closed enumeration, so
# the no-formal/local/recovery-endpoint absence is enforced by
# construction and re-pinned by the model validator.
DemoEndpointKindV1 = Literal[
    "HEALTH",
    "SCENARIO_PAGE",
    "SESSION_CREATE",
    "SESSION_ADVANCE",
]
DEMO_ENDPOINT_KINDS_V1: Final[tuple[DemoEndpointKindV1, ...]] = (
    "HEALTH",
    "SCENARIO_PAGE",
    "SESSION_CREATE",
    "SESSION_ADVANCE",
)

# The closed render.yaml surface the contract parser accepts.  Anything
# else (a disk, secret file, build filter, auto-deploy override, extra
# top-level section, ...) fails closed before a contract is returned.
_TOP_LEVEL_KEYS_V1: Final[frozenset[str]] = frozenset({"services"})
_SERVICE_KEYS_V1: Final[frozenset[str]] = frozenset(
    {
        "type",
        "name",
        "runtime",
        "repo",
        "branch",
        "dockerfilePath",
        "dockerContext",
        "plan",
        "healthCheckPath",
        "envVars",
        "disk",
        "envVarsFromFile",
        "secretFiles",
    }
)

# A real-provider credential key pattern: any env key that names a real
# provider credential (API key, token, password, secret, credential) is a
# real-provider secret and must never appear in the committed contract.
_CREDENTIAL_KEY_RE: Final = re.compile(
    r"(API[_-]?KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL)", re.IGNORECASE
)


class RenderContractV1(BaseModel):
    """One closed static Render service contract for the Task 34.B Demo.

    Binds the exact image identity (the ``containers/demo/Dockerfile``
    recipe), the platform PORT, the ``/healthz`` health path, the
    source-commit slot T37.1 fills, the committed public repository URL,
    the prohibited no-disk/no-secret/no-repository-credential state
    (empty tuples), and the closed four-route endpoint surface — no
    formal/local/recovery endpoint is representable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    service_name: Literal["vespercode-demo"]
    image_dockerfile: Literal["containers/demo/Dockerfile"]
    platform_port: Literal[8000]
    health_path: Literal["/healthz"]
    source_commit: StrictStr
    repository_url: HttpUrl
    persistent_disks: tuple[StrictStr, ...]
    secret_names: tuple[StrictStr, ...]
    repository_credentials: tuple[StrictStr, ...]
    endpoint_kinds: tuple[DemoEndpointKindV1, ...]

    @field_validator("source_commit")
    @classmethod
    def _commit_form(cls, value: str) -> str:
        if len(value) != 40 or any(c not in _HEX_CHARS for c in value):
            raise ValueError("source_commit must be 40 lowercase hex characters")
        return value

    @model_validator(mode="after")
    def _exact_endpoint_surface(self) -> "RenderContractV1":
        if len(self.endpoint_kinds) != len(DEMO_ENDPOINT_KINDS_V1) or set(
            self.endpoint_kinds
        ) != set(DEMO_ENDPOINT_KINDS_V1):
            raise ValueError(
                "endpoint_kinds must be exactly the Task 34.B closed "
                "four-route surface (no formal/local/recovery endpoint, "
                "no duplicates)"
            )
        return self

    @model_validator(mode="after")
    def _empty_prohibited_state(self) -> "RenderContractV1":
        if self.persistent_disks or self.secret_names or self.repository_credentials:
            raise ValueError(
                "persistent_disks/secret_names/repository_credentials must "
                "be empty (no disk, no real-provider secret, no repository "
                "credential in the committed contract)"
            )
        return self


def _parse_render_yaml(text: str) -> dict[str, object]:
    """Parse the closed render.yaml surface with the standard library.

    The committed render.yaml is a small, fully-closed YAML subset: one
    ``services`` list holding exactly one docker web service with scalar
    keys and a flat ``envVars`` list of ``{key, value}`` entries.  A
    hand-rolled indentation-aware parser keeps this task free of a
    PyYAML dependency — declaring one would cascade through the frozen
    gate/dependency-closure records (SPEC_PROCESS 52 gate contract),
    which is out of scope for T36.3's three owned files.
    """
    payload: dict[str, object] = {}
    services: list[dict[str, object]] | None = None
    service: dict[str, object] | None = None
    env_vars: list[dict[str, object]] | None = None
    env_entry: dict[str, object] | None = None

    def _scalar(value: str) -> object:
        value = value.strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            return value[1:-1]
        return value

    def _pair(content: str) -> tuple[str, object]:
        key, _, value = content.partition(":")
        return key, _scalar(value)

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        content = line.strip()
        if indent == 0:
            if content == "services:":
                services = []
                payload["services"] = services
                service = None
            elif ":" in content and service is None:
                key, value = _pair(content)
                payload[key] = value
            else:
                raise ValueError(f"unexpected render.yaml top-level line: {content!r}")
        elif indent == 2:
            if content.startswith("- ") and service is None:
                service = {}
                assert services is not None
                key, value = _pair(content[2:])
                service[key] = value
            elif ":" in content and service is not None:
                key, value = _pair(content)
                service[key] = value
            else:
                raise ValueError(f"unexpected render.yaml service line: {content!r}")
        elif indent == 4:
            if content == "envVars:" and service is not None:
                env_vars = []
                service["envVars"] = env_vars
                env_entry = None
            elif ":" in content and service is not None and env_vars is None:
                # Service scalar keys sit at indent 4 under the
                # ``- type: web`` list item (indent 2).
                key, value = _pair(content)
                service[key] = value
            else:
                raise ValueError(f"unexpected render.yaml env line: {content!r}")
        elif indent == 6:
            if content.startswith("- ") and env_vars is not None:
                env_entry = {}
                key, value = _pair(content[2:])
                env_entry[key] = value
                env_vars.append(env_entry)
            else:
                raise ValueError(f"unexpected render.yaml envVar line: {content!r}")
        elif indent == 8 and env_entry is not None:
            key, value = _pair(content)
            env_entry[key] = value
        else:
            raise ValueError(f"unexpected render.yaml indentation: {line!r}")
    if service is not None and services is not None:
        services.append(service)
    return payload


def _service_of(path: Path) -> dict[str, object]:
    """The one closed service mapping of a render.yaml payload.

    Fails closed on any structural deviation: a non-mapping payload, an
    unknown top-level or service key, or any service other than the
    exact single docker web service rejects before any contract is built.
    """
    payload = _parse_render_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("render.yaml must be a mapping")
    extra_top = sorted(set(payload) - _TOP_LEVEL_KEYS_V1)
    if extra_top:
        raise ValueError(
            f"unknown render.yaml top-level key(s): {', '.join(extra_top)}"
        )
    services = payload.get("services")
    if not isinstance(services, list) or len(services) != 1:
        raise ValueError("render.yaml must declare exactly one service")
    service = services[0]
    if not isinstance(service, dict):
        raise ValueError("render.yaml service must be a mapping")
    extra_keys = sorted(set(service) - _SERVICE_KEYS_V1)
    if extra_keys:
        raise ValueError(f"unknown render.yaml service key(s): {', '.join(extra_keys)}")
    if service.get("type") != "web" or service.get("runtime") != "docker":
        raise ValueError("render.yaml must declare a docker web service")
    return service


def _env_var(service: dict[str, object], key: str) -> dict[str, object]:
    """The env-var entry with the exact key (closed helper for tests)."""
    env_vars = service["envVars"]
    assert isinstance(env_vars, list)
    for entry in env_vars:
        assert isinstance(entry, dict)
        if entry.get("key") == key:
            return entry
    raise AssertionError(f"render.yaml envVars must declare {key}")


def load_render_contract(path: str | Path) -> RenderContractV1:
    """Parse one committed render.yaml into the closed static contract
    (36.C GREEN-2; zero I/O beyond reading the file).

    The deterministic bindings come only from the committed file: the
    Task 34.B Dockerfile path, the platform PORT, ``/healthz``, the
    SOURCE_COMMIT slot, the public repository URL, the empty
    no-disk/no-secret/no-repository-credential tuples, and the exact
    closed four-route endpoint surface (the Task 34.B route set, a
    fake/static observation — no network, platform query, deployment,
    or evidence write is ever performed).
    """
    service = _service_of(Path(path))
    env_vars = service.get("envVars")
    if not isinstance(env_vars, list):
        raise ValueError("render.yaml envVars must be a list")
    env_by_key = {
        str(entry["key"]): str(entry["value"])
        for entry in env_vars
        if isinstance(entry, dict) and "key" in entry and "value" in entry
    }
    port = env_by_key.get("PORT")
    source_commit = env_by_key.get("SOURCE_COMMIT")
    if port is None or source_commit is None:
        raise ValueError(
            "render.yaml must inject the platform PORT and SOURCE_COMMIT env vars"
        )

    disks = service.get("disk")
    if disks is not None and not isinstance(disks, list):
        raise ValueError("render.yaml disk must be a list")
    if disks:
        names = ", ".join(
            str(disk.get("name", "?")) for disk in disks if isinstance(disk, dict)
        )
        raise ValueError(f"render.yaml must not declare a persistent disk: {names}")

    env_from_file = service.get("envVarsFromFile")
    secret_files = service.get("secretFiles")
    if env_from_file is not None and not isinstance(env_from_file, list):
        raise ValueError("render.yaml envVarsFromFile must be a list")
    if secret_files is not None and not isinstance(secret_files, list):
        raise ValueError("render.yaml secretFiles must be a list")
    env_from_file = env_from_file or []
    secret_files = secret_files or []
    secret_names = tuple(
        str(entry["envVarKey"])
        for entry in env_from_file
        if isinstance(entry, dict) and "envVarKey" in entry
    ) + tuple(
        str(secret["name"]) for secret in secret_files if isinstance(secret, dict)
    )
    credential_env_keys = tuple(
        sorted(key for key in env_by_key if _CREDENTIAL_KEY_RE.search(key))
    )
    secret_names += credential_env_keys
    if secret_names:
        raise ValueError(
            "render.yaml must not declare a real provider secret: "
            + ", ".join(secret_names)
        )

    repo = service.get("repo")
    if not isinstance(repo, str):
        raise ValueError("render.yaml must declare the public repository URL")
    repository_credentials: tuple[str, ...] = ()
    if urlsplit(repo).username is not None:
        repository_credentials = ("repo:userinfo",)
        raise ValueError(
            "render.yaml must not carry a repository credential: repo:userinfo"
        )

    return RenderContractV1.model_validate(
        {
            "service_name": str(service.get("name", "")),
            "image_dockerfile": str(service.get("dockerfilePath", "")),
            "platform_port": int(port),
            "health_path": str(service.get("healthCheckPath", "")),
            "source_commit": source_commit,
            "repository_url": repo,
            "persistent_disks": (),
            "secret_names": (),
            "repository_credentials": repository_credentials,
            "endpoint_kinds": DEMO_ENDPOINT_KINDS_V1,
        }
    )


RenderDeploymentErrorCodeV1 = Literal[
    "SOURCE_COMMIT_MISMATCH",
    "IMAGE_DOCKERFILE_MISMATCH",
    "IMAGE_DIGEST_MISSING",
    "HEALTHZ_NOT_OK",
]


class ObservedRenderDeploymentV1(BaseModel):
    """One immutable observed terminal deployment result (fake in tests).

    ``source_commit`` is the final merged prerequisite main commit T37.1
    deploys, ``image_dockerfile`` the recipe the deployed image was built
    from, ``demo_image_digest`` T37.1's confirmed content-addressed image
    digest (raw ``sha256:``-prefixed registry form, per the T36.2
    precedent), and ``healthz_ok`` the live ``/healthz`` 200 observation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_commit: StrictStr
    image_dockerfile: StrictStr
    demo_image_digest: StrictStr
    healthz_ok: StrictBool


class RenderDeploymentAcceptedV1(BaseModel):
    """Closed acceptance: exact complete alignment, evidence allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["ACCEPTED"] = "ACCEPTED"
    evidence_write_allowed: Literal[True] = True


class RenderDeploymentRejectedV1(BaseModel):
    """Closed rejection: any mismatch, evidence writing forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["REJECTED"] = "REJECTED"
    error_code: RenderDeploymentErrorCodeV1
    evidence_write_allowed: Literal[False] = False


RenderDeploymentVerificationV1 = RenderDeploymentAcceptedV1 | RenderDeploymentRejectedV1


def verify_render_deployment_observation(
    frozen: RenderContractV1,
    observed: ObservedRenderDeploymentV1,
) -> RenderDeploymentVerificationV1:
    """Compare the observed deployment facts against the frozen static
    contract in the declared deterministic order (36.C GREEN-2).

    Order: source commit, image recipe, confirmed image digest presence,
    live health.  Any mismatch returns ``REJECTED`` with
    ``evidence_write_allowed=False``; only exact complete alignment
    returns ``ACCEPTED``.  The verifier is pure: zero network, platform
    query, deployment, or evidence write.
    """
    if observed.source_commit != frozen.source_commit:
        return RenderDeploymentRejectedV1(error_code="SOURCE_COMMIT_MISMATCH")
    if observed.image_dockerfile != frozen.image_dockerfile:
        return RenderDeploymentRejectedV1(error_code="IMAGE_DOCKERFILE_MISMATCH")
    if not observed.demo_image_digest:
        return RenderDeploymentRejectedV1(error_code="IMAGE_DIGEST_MISSING")
    if not observed.healthz_ok:
        return RenderDeploymentRejectedV1(error_code="HEALTHZ_NOT_OK")
    return RenderDeploymentAcceptedV1()


@pytest.fixture()
def render_contract() -> RenderContractV1:
    """The static Render contract parsed from the committed render.yaml."""
    return load_render_contract(_RENDER_YAML)


def test_render_contract_has_no_disk_or_real_provider_secret(
    render_contract: RenderContractV1,
) -> None:
    assert render_contract.persistent_disks == ()
    assert render_contract.secret_names == ()


def test_committed_render_contract_uses_release_source_commit(
    render_contract: RenderContractV1,
) -> None:
    assert render_contract.source_commit == RELEASE_SOURCE_COMMIT_V1


def _dump_render_yaml(payload: dict[str, object]) -> str:
    """Serialize the closed render.yaml surface (stdlib only).

    Symmetric to ``_parse_render_yaml``: one ``services`` list of one
    docker web service with scalar keys and a flat ``envVars`` list of
    ``{key, value}`` entries (values quoted as strings).
    """
    lines: list[str] = ["services:"]
    services = payload["services"]
    assert isinstance(services, list)
    for service in services:
        assert isinstance(service, dict)
        for index, (key, value) in enumerate(service.items()):
            if key == "envVars":
                lines.append("    envVars:")
                env_vars = value
                assert isinstance(env_vars, list)
                for entry in env_vars:
                    assert isinstance(entry, dict)
                    for entry_index, (entry_key, entry_value) in enumerate(
                        entry.items()
                    ):
                        if entry_index == 0:
                            lines.append(f"      - {entry_key}: {entry_value}")
                        else:
                            lines.append(f'        {entry_key}: "{entry_value}"')
            elif index == 0:
                lines.append(f"  - {key}: {value}")
            else:
                lines.append(f"    {key}: {value}")
    return "\n".join(lines) + "\n"


def _base_yaml(tmp_path: Path) -> Path:
    """One fake committed render.yaml in *tmp_path* (36.C matrix base)."""
    path = tmp_path / "render.yaml"
    path.write_text(
        _dump_render_yaml(
            {
                "services": [
                    {
                        "type": "web",
                        "name": "vespercode-demo",
                        "runtime": "docker",
                        "repo": "https://github.com/ledstevenovo/VesperCode",
                        "branch": "main",
                        "dockerfilePath": DEMO_DOCKERFILE_PATH_V1,
                        "dockerContext": ".",
                        "plan": "free",
                        "healthCheckPath": DEMO_HEALTH_PATH_V1,
                        "envVars": [
                            {"key": "PORT", "value": "8000"},
                            {"key": "SOURCE_COMMIT", "value": "0" * 40},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _rewrite_service(path: Path, service: dict[str, object]) -> None:
    """Rewrite one fake render.yaml from its closed service mapping."""
    path.write_text(
        _dump_render_yaml({"services": [service]}),
        encoding="utf-8",
    )


def test_render_deployment_matrix(tmp_path: Path) -> None:
    """PLAN 36.C row (Expected 36.C): the committed config/image contract
    contains the exact Task 34.B identity, platform PORT, ``/healthz``,
    no disk or real-provider secret, and no formal/local/recovery
    endpoint; fake source/deployment/image mismatches are rejected with
    zero external I/O; T36.3 performs no Render mutation and writes no
    ``deployment-v1.json``.
    """
    # Baseline: the committed render.yaml parses into the exact static
    # contract — identity, PORT, health path, source-commit slot form,
    # and the prohibited no-disk/no-secret/no-repository-credential state.
    loaded = load_render_contract(_RENDER_YAML)
    assert loaded.service_name == "vespercode-demo"
    assert loaded.image_dockerfile == DEMO_DOCKERFILE_PATH_V1
    assert loaded.platform_port == DEMO_PLATFORM_PORT_V1
    assert loaded.health_path == DEMO_HEALTH_PATH_V1
    assert loaded.persistent_disks == ()
    assert loaded.secret_names == ()
    assert loaded.repository_credentials == ()
    assert set(loaded.endpoint_kinds) == set(DEMO_ENDPOINT_KINDS_V1)

    # Row 1: a persistent disk in the yaml rejects before any contract
    # is returned (SPEC §8.3 no persistent disk / §5.6).
    disk_path = _base_yaml(tmp_path)
    service = _service_of(disk_path)
    # The injected key is placed FIRST so the loader's own disk check
    # fires (not the parser's structural error).  The serializer
    # stringifies the nested list, so the loader's list-type branch
    # ("disk must be a list") is what fires — still a closed rejection
    # of any disk declaration; the model validator additionally rejects
    # a non-empty persistent_disks tuple.
    service = {"disk": [{"name": "data"}], **service}
    _rewrite_service(disk_path, service)
    with pytest.raises(ValueError, match="disk"):
        load_render_contract(disk_path)

    # Row 2: a secret file (envVarsFromFile) rejects — a real provider
    # secret never enters the committed contract.
    secret_path = _base_yaml(tmp_path)
    service = _service_of(secret_path)
    service = {
        "envVarsFromFile": [{"envVarKey": "OPENAI_API_KEY", "filePath": "/secret"}],
        **service,
    }
    _rewrite_service(secret_path, service)
    # The serializer stringifies the nested list, so the loader's
    # list-type branch fires — a closed rejection of any secret-file
    # declaration (the model validator additionally rejects a non-empty
    # secret_names tuple).
    with pytest.raises(ValueError, match="envVarsFromFile"):
        load_render_contract(secret_path)

    # Row 3: an env key naming a real provider credential rejects.
    env_secret_path = _base_yaml(tmp_path)
    service = _service_of(env_secret_path)
    cast(list[dict[str, object]], service["envVars"]).append(
        {"key": "OPENAI_API_KEY", "value": "sk-fake"}
    )
    _rewrite_service(env_secret_path, service)
    with pytest.raises(ValueError, match="provider secret"):
        load_render_contract(env_secret_path)

    # Row 4: a repository credential (repo URL userinfo) rejects.  The
    # fake credential URL is assembled from parts so the fixed rule
    # table never sees a literal credential value (the
    # test_authorization.py fake-secret convention).
    repo_secret_path = _base_yaml(tmp_path)
    service = _service_of(repo_secret_path)
    service["repo"] = (
        "https://" + "token:secret@" + "github.com/ledstevenovo/VesperCode"
    )
    _rewrite_service(repo_secret_path, service)
    with pytest.raises(ValueError, match="repository credential"):
        load_render_contract(repo_secret_path)

    # Row 5: identity drift — a different Dockerfile path rejects (the
    # image identity is exact Task 34.B).
    drifted = _base_yaml(tmp_path)
    service = _service_of(drifted)
    service["dockerfilePath"] = "containers/other"
    _rewrite_service(drifted, service)
    with pytest.raises(ValidationError):
        load_render_contract(drifted)

    # Row 6: a different health path rejects.
    drifted = _base_yaml(tmp_path)
    service = _service_of(drifted)
    service["healthCheckPath"] = "/live"
    _rewrite_service(drifted, service)
    with pytest.raises(ValidationError):
        load_render_contract(drifted)

    # Row 7: a different platform PORT rejects.
    drifted = _base_yaml(tmp_path)
    service = _service_of(drifted)
    _env_var(service, "PORT")["value"] = "8080"
    _rewrite_service(drifted, service)
    with pytest.raises(ValidationError):
        load_render_contract(drifted)

    # Row 8: a non-hex source-commit slot rejects (T37.1 fills the
    # placeholder with the real final merged main commit).
    drifted = _base_yaml(tmp_path)
    service = _service_of(drifted)
    _env_var(service, "SOURCE_COMMIT")["value"] = "not-a-commit"
    _rewrite_service(drifted, service)
    with pytest.raises(ValidationError):
        load_render_contract(drifted)

    # Row 9: the closed contract surface rejects unknown keys — a build
    # override or other section can never be smuggled into the committed
    # configuration.
    for extra_key in ("build", "invented", "autoDeploy"):
        drifted = _base_yaml(tmp_path)
        service = _service_of(drifted)
        # Injected first so the service-key whitelist check fires.
        service = {extra_key: True, **service}
        _rewrite_service(drifted, service)
        with pytest.raises(ValueError, match="unknown render.yaml service key"):
            load_render_contract(drifted)
    drifted = _base_yaml(tmp_path)
    payload = _parse_render_yaml(drifted.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    # An extra top-level section (e.g. ``databases``) is outside the
    # closed surface and must reject.  The section is placed FIRST so
    # ``_service_of``'s top-level whitelist check fires (not the
    # parser's structural error).
    drifted.write_text(
        "databases: []\n" + _dump_render_yaml(payload),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown render.yaml top-level key"):
        load_render_contract(drifted)

    # Row 10: the model itself rejects a non-empty prohibited state
    # (no disk, no real-provider secret, no repository credential).
    with pytest.raises(ValidationError):
        RenderContractV1.model_validate(
            {
                "service_name": "vespercode-demo",
                "image_dockerfile": DEMO_DOCKERFILE_PATH_V1,
                "platform_port": DEMO_PLATFORM_PORT_V1,
                "health_path": DEMO_HEALTH_PATH_V1,
                "source_commit": "0" * 40,
                "repository_url": "https://github.com/ledstevenovo/VesperCode",
                "persistent_disks": ("data",),
                "secret_names": (),
                "repository_credentials": (),
                "endpoint_kinds": DEMO_ENDPOINT_KINDS_V1,
            }
        )

    # Row 12 the closed endpoint enumeration has no formal/local/
    # recovery kind — such a kind is unrepresentable and rejects.
    with pytest.raises(ValidationError):
        RenderContractV1.model_validate(
            {
                "service_name": "vespercode-demo",
                "image_dockerfile": DEMO_DOCKERFILE_PATH_V1,
                "platform_port": DEMO_PLATFORM_PORT_V1,
                "health_path": DEMO_HEALTH_PATH_V1,
                "source_commit": "0" * 40,
                "repository_url": "https://github.com/ledstevenovo/VesperCode",
                "persistent_disks": (),
                "secret_names": (),
                "repository_credentials": (),
                "endpoint_kinds": (
                    "HEALTH",
                    "SCENARIO_PAGE",
                    "SESSION_CREATE",
                    "FORMAL_RUN",
                ),
            }
        )

    # Row 12 a subset route surface rejects (the deployed surface must
    # be exactly the Task 34.B four routes).
    with pytest.raises(ValidationError):
        RenderContractV1.model_validate(
            {
                "service_name": "vespercode-demo",
                "image_dockerfile": DEMO_DOCKERFILE_PATH_V1,
                "platform_port": DEMO_PLATFORM_PORT_V1,
                "health_path": DEMO_HEALTH_PATH_V1,
                "source_commit": "0" * 40,
                "repository_url": "https://github.com/ledstevenovo/VesperCode",
                "persistent_disks": (),
                "secret_names": (),
                "repository_credentials": (),
                "endpoint_kinds": ("HEALTH",),
            }
        )

    # Row 13 fake observed deployment facts — exact complete alignment
    # against the frozen contract accepts with evidence writing allowed.
    frozen = load_render_contract(_RENDER_YAML)
    aligned = ObservedRenderDeploymentV1(
        source_commit=frozen.source_commit,
        image_dockerfile=frozen.image_dockerfile,
        demo_image_digest="sha256:" + "d" * 64,
        healthz_ok=True,
    )
    accepted = verify_render_deployment_observation(frozen, aligned)
    assert isinstance(accepted, RenderDeploymentAcceptedV1)
    assert accepted.kind == "ACCEPTED"
    assert accepted.evidence_write_allowed is True

    # Row 14 fake source mismatch -> SOURCE_COMMIT_MISMATCH (first
    # priority).
    mismatched = aligned.model_copy(update={"source_commit": "1" * 40})
    result = verify_render_deployment_observation(frozen, mismatched)
    assert isinstance(result, RenderDeploymentRejectedV1)
    assert result.error_code == "SOURCE_COMMIT_MISMATCH"
    assert result.evidence_write_allowed is False

    # Row 15 fake image mismatch (the deployed image was built from a
    # different recipe) -> IMAGE_DOCKERFILE_MISMATCH.
    mismatched = aligned.model_copy(update={"image_dockerfile": "containers/other"})
    result = verify_render_deployment_observation(frozen, mismatched)
    assert isinstance(result, RenderDeploymentRejectedV1)
    assert result.error_code == "IMAGE_DOCKERFILE_MISMATCH"

    # Row 16 an observation without the confirmed image digest is not a
    # verifiable deployment -> IMAGE_DIGEST_MISSING.
    mismatched = aligned.model_copy(update={"demo_image_digest": ""})
    result = verify_render_deployment_observation(frozen, mismatched)
    assert isinstance(result, RenderDeploymentRejectedV1)
    assert result.error_code == "IMAGE_DIGEST_MISSING"

    # Row 17 a failed live health check rejects -> HEALTHZ_NOT_OK.
    mismatched = aligned.model_copy(update={"healthz_ok": False})
    result = verify_render_deployment_observation(frozen, mismatched)
    assert isinstance(result, RenderDeploymentRejectedV1)
    assert result.error_code == "HEALTHZ_NOT_OK"

    # Row 18 deterministic priority — source mismatch shadows every
    # later mismatch.
    mismatched = aligned.model_copy(
        update={
            "source_commit": "2" * 40,
            "image_dockerfile": "containers/other",
            "healthz_ok": False,
        }
    )
    result = verify_render_deployment_observation(frozen, mismatched)
    assert isinstance(result, RenderDeploymentRejectedV1)
    assert result.error_code == "SOURCE_COMMIT_MISMATCH"

    # Row 19 the contracts are closed and immutable — invented fields,
    # undeclared error codes, and mutation reject.
    with pytest.raises(ValidationError):
        RenderContractV1.model_validate(
            {
                **frozen.model_dump(),
                "invented": True,
            }
        )
    with pytest.raises(ValidationError):
        ObservedRenderDeploymentV1.model_validate(
            {
                **aligned.model_dump(),
                "invented": True,
            }
        )
    with pytest.raises(ValidationError):
        RenderDeploymentRejectedV1.model_validate({"error_code": "INVENTED"})
    with pytest.raises(ValidationError):
        frozen.source_commit = "0" * 40
    with pytest.raises(ValidationError):
        accepted.kind = "REJECTED"  # type: ignore[assignment]

    # Row 20 zero external I/O — no deployment evidence was written
    # anywhere (the only files on disk are the fake yamls this test
    # itself created in tmp_path).
    assert not (tmp_path / "deployment-v1.json").exists()
    assert not (_REPO_ROOT / "deployment-v1.json").exists()
