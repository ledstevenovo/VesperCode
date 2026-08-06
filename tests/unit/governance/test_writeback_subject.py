"""T14.1 legacy step 14.A: immutable final-writeback subject/binding tests.

Pins the closed binding/subject schema (every subject field except the
self-digest is bound by the §0.1 identity), the aggregation of the exact
current Run, Candidate identity/FinalDiff, frozen editable policy,
formal validation evidence, frozen workspace preimage, frozen run
config, and expiry facts, the editable-policy revalidation of every
FinalDiff entry (``PATCH_PATH_NOT_EDITABLE``), the same-editable-policy
identity chain (``TREE_INTEGRITY_FAILED``), the SPEC §4.4.2 action
semantic digest domain, and the bound-fact drift matrix (PLAN Registry
row 14.A).  Wait creation, decision persistence, approval consumption,
policy override, and workspace writes remain out of scope (GREEN-4).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import pytest

# The builder consumes pydantic runtime contracts; the hash-locked gate
# toolchain installs no runtime dependencies, so this module skips cleanly
# there (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from src.vespercode.candidate.final_diff import (
    FinalDiffEntryV1,
    FinalDiffPreimageV1,
    FinalDiffV1,
)
from src.vespercode.canonical.digest import domain_digest
from src.vespercode.canonical.json_v1 import CanonicalValueV1
from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1
from src.vespercode.canonical.timestamp_v1 import CanonicalTimestampV1
from src.vespercode.governance.writeback_subject import (
    FinalWritebackBindingV1,
    FinalWritebackSubjectError,
    FinalWritebackSubjectV1,
    build_final_writeback_subject,
)
from src.vespercode.profiles.reference import (
    ReferenceProfileManifestV1,
    load_reference_profile,
)
from src.vespercode.trees.text_classifier import TextMetadataV1

_CREATED_AT = CanonicalTimestampV1("2026-08-05T09:00:00.000Z")
_EXPIRES_AT = CanonicalTimestampV1("2026-08-05T09:05:00.000Z")
_REFERENCE_MANIFEST = (
    Path(__file__).resolve().parents[3] / "reference/manifest/reference-profile-v1.json"
)

_SNAPSHOT_DIGEST = hashlib.sha256(b"sealed-snapshot").hexdigest()
_CANDIDATE_DIGEST = hashlib.sha256(b"candidate-identity").hexdigest()
_VALIDATION_DIGEST = hashlib.sha256(b"validation-manifest").hexdigest()
_FORMAL_EVIDENCE_DIGEST = hashlib.sha256(b"formal-evidence").hexdigest()
_PREIMAGE_DIGEST = hashlib.sha256(b"workspace-preimage").hexdigest()
_RUN_CONFIG_DIGEST = hashlib.sha256(b"run-config").hexdigest()


def manifest() -> ReferenceProfileManifestV1:
    """The frozen packaged reference profile (digest-verified)."""
    loaded = load_reference_profile(_REFERENCE_MANIFEST.read_bytes())
    assert isinstance(loaded, ReferenceProfileManifestV1)
    return loaded


_MANIFEST = manifest()
_EDITABLE_DIGEST = _MANIFEST.editable_path_policy.digest


def _entry(path: str, raw: bytes, operation: str = "REPLACE") -> FinalDiffEntryV1:
    """One closed net-diff row with the exact preimage/postimage identity."""
    return FinalDiffEntryV1(
        operation=cast(Any, operation),
        path=CanonicalRelativePathV1(path),
        preimage=FinalDiffPreimageV1(
            kind="PRESENT",
            content_digest=hashlib.sha256(raw).hexdigest(),
            text_metadata=TextMetadataV1(
                encoding="UTF8", newline="LF", final_newline=True
            ),
        ),
        postimage_digest=hashlib.sha256(raw).hexdigest(),
        postimage_text_metadata=TextMetadataV1(
            encoding="UTF8", newline="LF", final_newline=True
        ),
    )


def _canonical_entry(entry: FinalDiffEntryV1) -> dict[str, CanonicalValueV1]:
    """The §0.1 canonical value shape of one sealed diff row."""
    if entry.preimage.kind == "ABSENT":
        preimage: CanonicalValueV1 = {"kind": "ABSENT"}
    else:
        content_digest = entry.preimage.content_digest
        metadata = entry.preimage.text_metadata
        assert content_digest is not None
        assert metadata is not None
        preimage = {
            "kind": "PRESENT",
            "content_digest": content_digest,
            "text_metadata": {
                "encoding": metadata.encoding,
                "newline": metadata.newline,
                "final_newline": metadata.final_newline,
            },
        }
    post_metadata = entry.postimage_text_metadata
    return {
        "operation": entry.operation,
        "path": entry.path.value,
        "preimage": preimage,
        "postimage_digest": entry.postimage_digest,
        "postimage_text_metadata": {
            "encoding": post_metadata.encoding,
            "newline": post_metadata.newline,
            "final_newline": post_metadata.final_newline,
        },
    }


def final_diff(
    *,
    path: str = "src/a.py",
    raw: bytes = b"x = 1\n",
    snapshot_tree_digest: str = _SNAPSHOT_DIGEST,
) -> FinalDiffV1:
    """One sealed current FinalDiff whose digest binds its exact rows."""
    entry = _entry(path, raw)
    digest = domain_digest(
        "FinalDiffV1",
        1,
        {
            "schema_version": 1,
            "snapshot_tree_digest": snapshot_tree_digest,
            "entries": tuple(_canonical_entry(entry) for entry in (entry,)),
            "added_and_replacement_text_bytes": len(raw),
        },
    )
    return FinalDiffV1(
        schema_version=1,
        snapshot_tree_digest=snapshot_tree_digest,
        entries=(entry,),
        added_and_replacement_text_bytes=len(raw),
        digest=digest,
    )


def binding(
    tag: str = "a",
    *,
    run_id: str = "run-1",
    path: str = "src/a.py",
    snapshot_tree_digest: str = _SNAPSHOT_DIGEST,
    candidate_digest: str = _CANDIDATE_DIGEST,
    validation_manifest_digest: str = _VALIDATION_DIGEST,
    formal_evidence_digest: str = _FORMAL_EVIDENCE_DIGEST,
    workspace_preimage_digest: str = _PREIMAGE_DIGEST,
    run_config_digest: str = _RUN_CONFIG_DIGEST,
    reference_profile_digest: str | None = None,
    reference_policy_digest: str | None = None,
    validation_repository_policy_digest: str | None = None,
    run_config_reference_profile_digest: str | None = None,
    run_config_policy_id: str = "PYTHON_SRC_ONLY_V1",
) -> FinalWritebackBindingV1:
    """One exact current-fact binding; *tag* varies the FinalDiff postimage."""
    reference = (
        _MANIFEST.digest
        if reference_profile_digest is None
        else reference_profile_digest
    )
    raw = b"x = 1\n" if tag == "a" else b"x = 2\n"
    return FinalWritebackBindingV1(
        run_id=run_id,
        candidate_digest=candidate_digest,
        final_diff=final_diff(
            path=path, raw=raw, snapshot_tree_digest=snapshot_tree_digest
        ),
        validation_manifest_digest=validation_manifest_digest,
        validation_repository_policy_digest=(
            _EDITABLE_DIGEST
            if validation_repository_policy_digest is None
            else validation_repository_policy_digest
        ),
        formal_evidence_digest=formal_evidence_digest,
        workspace_preimage_digest=workspace_preimage_digest,
        run_config_digest=run_config_digest,
        run_config_reference_profile_digest=(
            reference
            if run_config_reference_profile_digest is None
            else run_config_reference_profile_digest
        ),
        run_config_policy_id=run_config_policy_id,
        reference_profile_digest=reference,
        reference_policy_digest=(
            _EDITABLE_DIGEST
            if reference_policy_digest is None
            else reference_policy_digest
        ),
        policy=_MANIFEST.editable_path_policy,
    )


def build_subject(
    b: FinalWritebackBindingV1, expires_at: CanonicalTimestampV1 = _EXPIRES_AT
) -> FinalWritebackSubjectV1:
    """The pure subject builder over one exact binding."""
    return build_final_writeback_subject(b, expires_at)


def test_subject_digest_changes_when_final_diff_changes() -> None:
    assert (
        build_subject(binding("a")).subject_digest
        != build_subject(binding("b")).subject_digest
    )


def test_subject_binds_the_exact_current_facts() -> None:
    """GREEN-1: one immutable subject over the exact Run/Candidate/diff/
    policy/validation/preimage/config/expiry facts."""
    subject = build_subject(binding())
    assert subject.schema_version == 1
    assert subject.action_type == "final_writeback"
    assert subject.run_id == "run-1"
    assert subject.candidate_digest == _CANDIDATE_DIGEST
    assert subject.final_diff_digest == binding().final_diff.digest
    assert subject.validation_manifest_digest == _VALIDATION_DIGEST
    assert subject.formal_evidence_digest == _FORMAL_EVIDENCE_DIGEST
    assert subject.workspace_preimage_digest == _PREIMAGE_DIGEST
    assert subject.run_config_digest == _RUN_CONFIG_DIGEST
    assert subject.policy_digest == _EDITABLE_DIGEST
    assert subject.reference_profile_digest == _MANIFEST.digest
    assert subject.expires_at == _EXPIRES_AT
    # The subject digest serves as subject_digest (SPEC §4.4.2) and
    # excludes the digest itself and all mutable approval data.
    assert subject.subject_digest == subject.digest
    assert (
        subject.digest
        != hashlib.sha256(subject.model_dump_json().encode("utf-8")).hexdigest()
    )


def test_action_semantic_digest_uses_the_exact_domain() -> None:
    """SPEC §4.4.2: the closed ActionSemanticDigestV1 domain over
    {schema_version, action_type, candidate_digest, final_diff_digest}."""
    subject = build_subject(binding())
    expected = domain_digest(
        "ActionSemanticDigestV1",
        1,
        {
            "schema_version": 1,
            "action_type": "final_writeback",
            "candidate_digest": _CANDIDATE_DIGEST,
            "final_diff_digest": binding().final_diff.digest,
        },
    )
    assert subject.action_semantic_digest == expected
    # A drifted candidate identity rotates the semantic digest too.
    drifted = build_subject(
        binding(candidate_digest=hashlib.sha256(b"other").hexdigest())
    )
    assert drifted.action_semantic_digest != subject.action_semantic_digest


def test_non_editable_final_diff_entry_rejects_before_subject() -> None:
    """SPEC §4.4.2: an out-of-scope entry returns PATCH_PATH_NOT_EDITABLE
    and no subject exists."""
    with pytest.raises(FinalWritebackSubjectError) as exc:
        build_subject(binding(path="docs/outside.md"))
    assert exc.value.error_code == "PATCH_PATH_NOT_EDITABLE"
    with pytest.raises(FinalWritebackSubjectError) as exc:
        build_subject(binding(path="src-old/a.py"))
    assert exc.value.error_code == "PATCH_PATH_NOT_EDITABLE"


def test_policy_identity_drift_rejects_before_subject() -> None:
    """SPEC §4.4.2: identity mismatch returns TREE_INTEGRITY_FAILED before
    any subject exists."""
    drift_cases = [
        dict(reference_policy_digest=hashlib.sha256(b"other").hexdigest()),
        dict(validation_repository_policy_digest=hashlib.sha256(b"other").hexdigest()),
        dict(run_config_reference_profile_digest=hashlib.sha256(b"other").hexdigest()),
        dict(run_config_policy_id="NOT_THE_BUILTIN"),
    ]
    for overrides in drift_cases:
        with pytest.raises(FinalWritebackSubjectError) as exc:
            build_subject(binding(**overrides))
        assert exc.value.error_code == "TREE_INTEGRITY_FAILED"


def test_subject_schema_is_closed() -> None:
    """The subject rejects unknown fields, wrong digests, and mutable
    approval data (AC-03: FinalWritebackApproval.status never enters)."""
    subject = build_subject(binding())
    with pytest.raises(ValidationError):
        FinalWritebackSubjectV1.model_validate(
            {**subject.model_dump(), "status": "PENDING"}
        )
    with pytest.raises(ValidationError):
        FinalWritebackSubjectV1.model_validate(
            {**subject.model_dump(), "created_at": _CREATED_AT.value}
        )
    with pytest.raises(ValidationError):
        FinalWritebackSubjectV1.model_validate(
            {**subject.model_dump(), "digest": "0" * 64}
        )
    with pytest.raises(ValidationError):
        FinalWritebackSubjectV1.model_validate({**subject.model_dump(), "digest": "x"})
    with pytest.raises(ValidationError):
        FinalWritebackSubjectV1.model_validate({**subject.model_dump(), "run_id": ""})
    assert subject.model_dump(exclude={"digest"}) == dict(
        schema_version=1,
        run_id="run-1",
        action_type="final_writeback",
        action_semantic_digest=subject.action_semantic_digest,
        candidate_digest=_CANDIDATE_DIGEST,
        final_diff_digest=binding().final_diff.digest,
        validation_manifest_digest=_VALIDATION_DIGEST,
        formal_evidence_digest=_FORMAL_EVIDENCE_DIGEST,
        workspace_preimage_digest=_PREIMAGE_DIGEST,
        run_config_digest=_RUN_CONFIG_DIGEST,
        policy_digest=_EDITABLE_DIGEST,
        reference_profile_digest=_MANIFEST.digest,
        expires_at={"value": _EXPIRES_AT.value},
    )


def test_writeback_subject_bound_fact_matrix() -> None:
    """PLAN Registry row 14.A.

    Subject digest changes for any Run, Snapshot, Candidate, FinalDiff,
    verification, path, or expiry change; identical bound facts produce
    identical bytes/digest.  The writeback subject binds no endpoint —
    the adapter identity is transmitted only through
    ``validation_manifest_digest`` (SPEC §4.4.2) — and mutable approval
    state never enters the subject (AC-03).
    """
    baseline = build_subject(binding())

    # Identical bound facts produce identical bytes and digest.
    assert baseline.subject_digest == build_subject(binding()).subject_digest
    assert baseline.model_dump_json() == build_subject(binding()).model_dump_json()

    # Run drift.
    assert (
        build_subject(binding(run_id="run-2")).subject_digest != baseline.subject_digest
    )

    # Snapshot drift (the FinalDiff's sealed snapshot identity).
    assert (
        build_subject(
            binding(snapshot_tree_digest=hashlib.sha256(b"other-snapshot").hexdigest())
        ).subject_digest
        != baseline.subject_digest
    )

    # Workspace preimage drift (the frozen preflight preimage fact).
    assert (
        build_subject(
            binding(
                workspace_preimage_digest=hashlib.sha256(b"other-preimage").hexdigest()
            )
        ).subject_digest
        != baseline.subject_digest
    )

    # Candidate identity drift.
    assert (
        build_subject(
            binding(candidate_digest=hashlib.sha256(b"other-candidate").hexdigest())
        ).subject_digest
        != baseline.subject_digest
    )

    # FinalDiff drift (postimage bytes change the diff digest).
    assert build_subject(binding("b")).subject_digest != baseline.subject_digest

    # Path drift (the FinalDiff entry path changes the diff digest).
    assert (
        build_subject(binding(path="src/b.py")).subject_digest
        != baseline.subject_digest
    )

    # Verification drift: the validation manifest digest.
    assert (
        build_subject(
            binding(
                validation_manifest_digest=hashlib.sha256(b"other-manifest").hexdigest()
            )
        ).subject_digest
        != baseline.subject_digest
    )

    # Verification drift: the formal evidence digest.
    assert (
        build_subject(
            binding(
                formal_evidence_digest=hashlib.sha256(b"other-evidence").hexdigest()
            )
        ).subject_digest
        != baseline.subject_digest
    )

    # Frozen run-config drift.
    assert (
        build_subject(
            binding(run_config_digest=hashlib.sha256(b"other-config").hexdigest())
        ).subject_digest
        != baseline.subject_digest
    )

    # Reference-profile drift (kept identity-consistent so the builder
    # accepts it and the digest rotates).
    other_reference = hashlib.sha256(b"other-reference").hexdigest()
    drifted = binding(
        reference_profile_digest=other_reference,
        run_config_reference_profile_digest=other_reference,
    )
    assert build_subject(drifted).subject_digest != baseline.subject_digest

    # Expiry drift.
    assert (
        build_subject(
            binding(), expires_at=CanonicalTimestampV1("2026-08-05T09:10:00.000Z")
        ).subject_digest
        != baseline.subject_digest
    )

    # Every drift also rotates the self-digest (subject_digest is exactly
    # the self-digest), and no drift produces a different subject for the
    # same digest: the digest is a pure function of the bound facts.
    assert baseline.digest == baseline.subject_digest
    assert build_subject(binding()).digest == baseline.digest
