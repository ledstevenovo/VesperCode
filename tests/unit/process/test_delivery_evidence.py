"""T37.1/37.C delivery process evidence and readiness gate tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# The report models are pydantic runtime contracts; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from conftest import (  # type: ignore[import-not-found]  # noqa: E402
    add_legacy_steps_line,
    remove_cold_start_record,
    remove_completion_commit_lines,
    remove_completion_review_marker,
    remove_document_check_body,
    remove_document_check_record,
    remove_v2_task_card,
    write_readme_without_section,
)

from scripts.verify_delivery import (  # noqa: E402
    DeliveryReadinessResultV1,
    verify_delivery,
)
from scripts.verify_process_evidence import (  # noqa: E402
    EXPECTED_LEGACY_STEP_COUNT,
    EXPECTED_TASK_COUNT,
    ProcessEvidenceResultV1,
    _expanded_legacy_steps,
    verify_process_evidence,
)


def test_process_evidence_requires_cold_start_record(
    repository_copy: Path,
) -> None:
    remove_cold_start_record(repository_copy / "SPEC_PROCESS.md")
    result = verify_process_evidence(repository_copy)
    assert "COLD_START_RECORD_MISSING" in result.error_codes


def test_full_repository_passes_process_evidence(repository_copy: Path) -> None:
    result = verify_process_evidence(repository_copy)
    assert result.error_codes == ()


def test_document_check_record_is_required(repository_copy: Path) -> None:
    remove_document_check_record(repository_copy / "SPEC_PROCESS.md")
    result = verify_process_evidence(repository_copy)
    assert "DOCUMENT_CHECK_RECORD_MISSING" in result.error_codes


def test_cold_start_record_rejects_failed_status(repository_copy: Path) -> None:
    # A corrupted record that says the cold start did NOT pass must not
    # satisfy the completion-record check.
    spec = repository_copy / "SPEC_PROCESS.md"
    text = spec.read_text(encoding="utf-8")
    text = text.replace(
        "## 40. 最终 bounded 1.Aa 冷启动通过与文档同步（2026-08-02）",
        "## 40. 最终 bounded 1.Aa 冷启动未通过与文档同步（2026-08-02）",
        1,
    )
    spec.write_text(text, encoding="utf-8")
    result = verify_process_evidence(repository_copy)
    assert "COLD_START_RECORD_MISSING" in result.error_codes


def test_document_check_record_requires_positive_result(
    repository_copy: Path,
) -> None:
    # A document-check heading with its result body stripped away must not
    # satisfy the completion-record check.
    remove_document_check_body(repository_copy / "SPEC_PROCESS.md")
    result = verify_process_evidence(repository_copy)
    assert "DOCUMENT_CHECK_RECORD_MISSING" in result.error_codes


def test_plan_task_count_is_pinned(repository_copy: Path) -> None:
    plan = repository_copy / "PLAN.md"
    text = plan.read_text(encoding="utf-8")
    # Remove one v2 task card heading so the count drops below the pinned 40.
    text = text.replace("## Task V2-01 — Identity and database boundary", "", 1)
    plan.write_text(text, encoding="utf-8")
    result = verify_process_evidence(repository_copy)
    assert "PLAN_TASK_COUNT_MISMATCH" in result.error_codes


def test_plan_legacy_step_count_is_pinned(repository_copy: Path) -> None:
    # Insert a v1-format legacy-steps line so the unique set no longer
    # matches the pinned 0.
    add_legacy_steps_line(repository_copy, "V2-01", "FAKE-STEP")
    result = verify_process_evidence(repository_copy)
    assert "PLAN_LEGACY_STEP_COUNT_MISMATCH" in result.error_codes


def test_completion_chronology_requires_valid_timestamps(
    repository_copy: Path,
) -> None:
    log = repository_copy / "AGENT_LOG.md"
    text = log.read_text(encoding="utf-8")
    text = text.replace(
        "**Timestamp (Asia/Taipei):** `2026-08-08T11:10:00+0800`",
        "**Timestamp (Asia/Taipei):** `not-a-timestamp`",
        1,
    )
    log.write_text(text, encoding="utf-8")
    result = verify_process_evidence(repository_copy)
    assert "AGENT_LOG_CHRONOLOGY_INVALID" in result.error_codes


def test_completion_chronology_rejects_distant_header_dates(
    repository_copy: Path,
) -> None:
    log = repository_copy / "AGENT_LOG.md"
    text = log.read_text(encoding="utf-8")
    # T35.1 anchor header says 20260808; give its timestamp a 2026-08-01
    # date (7 days off) so the entry no longer matches its header.
    text = text.replace(
        "## T35.1-COMPLETION-20260808\n",
        "## T35.1-COMPLETION-20260801\n",
        1,
    )
    log.write_text(text, encoding="utf-8")
    result = verify_process_evidence(repository_copy)
    assert "AGENT_LOG_CHRONOLOGY_INVALID" in result.error_codes


def test_completion_anchor_must_record_review_evidence(
    repository_copy: Path,
) -> None:
    remove_completion_review_marker(repository_copy / "AGENT_LOG.md", "T01.1")
    result = verify_process_evidence(repository_copy)
    assert "REVIEW_RECORD_MISSING:T01.1" in result.error_codes


def test_completion_anchor_must_record_commit_evidence(
    repository_copy: Path,
) -> None:
    remove_completion_commit_lines(repository_copy / "AGENT_LOG.md", "T01.1")
    result = verify_process_evidence(repository_copy)
    assert "COMMIT_RECORD_MISSING:T01.1" in result.error_codes


def test_recorded_pr_url_must_be_https(repository_copy: Path) -> None:
    log = repository_copy / "AGENT_LOG.md"
    text = log.read_text(encoding="utf-8")
    # Insert a recorded PR URL that is not https so the recorded-PR field
    # fails closed.
    text = text.replace(
        "## T35.1-COMPLETION-20260808\n",
        "## T35.1-COMPLETION-20260808\n- **PR URL:** http://example.invalid/pull/1\n",
        1,
    )
    log.write_text(text, encoding="utf-8")
    result = verify_process_evidence(repository_copy)
    assert "PR_RECORD_INVALID:T35.1" in result.error_codes


def test_recorded_pending_pr_narrative_is_accepted(
    repository_copy: Path,
) -> None:
    # T01.1/T01.2 honestly record "pending — human decision …" before a PR
    # exists; a narrative PR record must not be misread as a URL.
    log = repository_copy / "AGENT_LOG.md"
    text = log.read_text(encoding="utf-8")
    text = text.replace(
        "## T35.1-COMPLETION-20260808\n",
        "## T35.1-COMPLETION-20260808\n"
        "- **PR URL:** pending — deferred to WP closure.\n",
        1,
    )
    log.write_text(text, encoding="utf-8")
    result = verify_process_evidence(repository_copy)
    assert not any(code.startswith("PR_RECORD_INVALID:") for code in result.error_codes)


def test_recorded_human_intervention_must_not_be_empty(
    repository_copy: Path,
) -> None:
    log = repository_copy / "AGENT_LOG.md"
    text = log.read_text(encoding="utf-8")
    # Blank out one recorded human-intervention value.
    text = text.replace(
        "- **Human intervention:** 用户批准继续 T36.3（subagent 实现）——无其他。",
        "- **Human intervention:** ",
        1,
    )
    log.write_text(text, encoding="utf-8")
    result = verify_process_evidence(repository_copy)
    assert any(
        code.startswith("HUMAN_INTERVENTION_INVALID:") for code in result.error_codes
    )


def test_expanded_legacy_steps_from_committed_plan() -> None:
    plan = Path(__file__).resolve().parents[3] / "PLAN.md"
    tokens = _expanded_legacy_steps(plan.read_text(encoding="utf-8"))
    assert len(tokens) == EXPECTED_LEGACY_STEP_COUNT


def test_committed_plan_has_pinned_task_count() -> None:
    plan = Path(__file__).resolve().parents[3] / "PLAN.md"
    text = plan.read_text(encoding="utf-8")
    count = len(
        [
            m
            for m in re.finditer(
                r"^## Task [A-Z][A-Za-z0-9]+-[A-Za-z0-9]+[A-Za-z0-9]*\s",
                text,
                re.MULTILINE,
            )
        ]
    )
    assert count == EXPECTED_TASK_COUNT


def test_result_model_is_an_immutable_ordered_sequence(
    repository_copy: Path,
) -> None:
    result = verify_process_evidence(repository_copy)
    assert isinstance(result, ProcessEvidenceResultV1)
    assert isinstance(result.error_codes, tuple)
    assert result.model_config["frozen"] is True


def test_delivery_rejects_failed_process_evidence(
    repository_copy: Path,
    failed_process_evidence: ProcessEvidenceResultV1,
) -> None:
    result = verify_delivery(
        repository_copy,
        require_live=False,
        process_evidence_loader=lambda _: failed_process_evidence,
    )
    assert "PROCESS_EVIDENCE_INVALID" in result.error_codes


def test_delivery_rejects_incomplete_executable_child(repository_copy: Path) -> None:
    # v2 alignment: the delivery gate's per-card legacy-step checks read the
    # v1 ``### Task T`` blocks, so the v2-active fail-closed signal is the
    # PLAN card-count pin.  Deleting the V2-01 card drops the count from 40
    # to 39, so the process-evidence loader fails and the aggregate gate
    # reports PROCESS_EVIDENCE_INVALID.
    remove_v2_task_card(repository_copy, "V2-01")
    result = verify_delivery(repository_copy, require_live=False)
    assert "PROCESS_EVIDENCE_INVALID" in result.error_codes


def test_delivery_rejects_nonterminal_task(repository_copy: Path) -> None:
    # v2 alignment: same fail-closed path as the incomplete-child case —
    # removing the RA-01 card trips the PLAN task-count pin.
    remove_v2_task_card(repository_copy, "RA-01")
    result = verify_delivery(repository_copy, require_live=False)
    assert "PROCESS_EVIDENCE_INVALID" in result.error_codes


def test_delivery_rejects_terminal_card_without_completion_evidence(
    repository_copy: Path,
) -> None:
    # v2 alignment: the v1 test renamed a terminal card so its id had no
    # AGENT_LOG anchor.  The v2-active equivalent is deleting the B1-01 card
    # from the PLAN, which drops the card count below the pinned 40 and
    # fails the process-evidence loader.
    remove_v2_task_card(repository_copy, "B1-01")
    result = verify_delivery(repository_copy, require_live=False)
    assert "PROCESS_EVIDENCE_INVALID" in result.error_codes


def test_delivery_rejects_failed_readme_contract(repository_copy: Path) -> None:
    write_readme_without_section(repository_copy, "Distribution")
    result = verify_delivery(repository_copy, require_live=False)
    assert "README_CONTRACT_FAILED" in result.error_codes


def test_delivery_rejects_missing_reflection(repository_copy: Path) -> None:
    (repository_copy / "REFLECTION.md").unlink()
    result = verify_delivery(repository_copy, require_live=False)
    assert "REFLECTION_CONTRACT_FAILED" in result.error_codes


def test_delivery_without_live_skips_evidence_requirement(
    repository_copy: Path,
) -> None:
    result = verify_delivery(repository_copy, require_live=False)
    assert "DELIVERY_EVIDENCE_INVALID" not in result.error_codes


def test_delivery_live_rejects_drifting_source_commits(
    repository_copy: Path,
) -> None:
    evidence = repository_copy / "delivery" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    for name, char in (
        ("ci-v1.json", "a"),
        ("release-v1.json", "b"),
        ("deployment-v1.json", "c"),
    ):
        (evidence / name).write_text(
            json.dumps({"source_commit": char * 40}), encoding="utf-8"
        )
    result = verify_delivery(repository_copy, require_live=True)
    assert "SOURCE_COMMIT_DRIFT" in result.error_codes
    # The drift code is the specific verdict; the generic evidence code
    # must not shadow it.
    assert "DELIVERY_EVIDENCE_INVALID" not in result.error_codes


def test_delivery_live_rejects_invalid_evidence(repository_copy: Path) -> None:
    evidence = repository_copy / "delivery" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    for name in ("ci-v1.json", "release-v1.json", "deployment-v1.json"):
        (evidence / name).write_text("{not-json", encoding="utf-8")
    result = verify_delivery(repository_copy, require_live=True)
    assert "DELIVERY_EVIDENCE_INVALID" in result.error_codes


def test_delivery_live_rejects_undecodable_evidence(repository_copy: Path) -> None:
    evidence = repository_copy / "delivery" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    for name in ("ci-v1.json", "release-v1.json", "deployment-v1.json"):
        (evidence / name).write_bytes(b"\xff\xfe\x00")
    result = verify_delivery(repository_copy, require_live=True)
    assert "DELIVERY_EVIDENCE_INVALID" in result.error_codes


def test_delivery_rejects_deleted_completion_anchor(repository_copy: Path) -> None:
    # v2 alignment: the v1 test deleted the T01.1 AGENT_LOG anchor.  The
    # v2-active equivalent is deleting the B2-01 card from the PLAN, which
    # drops the card count below the pinned 40 and fails the
    # process-evidence loader.
    remove_v2_task_card(repository_copy, "B2-01")
    result = verify_delivery(repository_copy, require_live=False)
    assert "PROCESS_EVIDENCE_INVALID" in result.error_codes


def test_delivery_default_loader_reports_no_process_failure_on_clean_copy(
    repository_copy: Path,
) -> None:
    # Negative control: the copy's process records pass the v2 loader,
    # so the aggregate gate must not report the injected-loader failure
    # code.
    result = verify_delivery(repository_copy, require_live=False)
    assert "PROCESS_EVIDENCE_INVALID" not in result.error_codes


def test_delivery_accepts_fully_terminal_repository(
    ready_repository: Path,
) -> None:
    result = verify_delivery(ready_repository, require_live=False)
    assert result.error_codes == ()


def test_delivery_result_model_is_immutable(repository_copy: Path) -> None:
    result = verify_delivery(repository_copy, require_live=False)
    assert isinstance(result, DeliveryReadinessResultV1)
    assert isinstance(result.error_codes, tuple)
    assert result.model_config["frozen"] is True
