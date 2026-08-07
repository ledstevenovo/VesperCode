"""T04.2 legacy step 4.E: redacted changed-file credential scanner tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# The report models are pydantic runtime contracts; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from pydantic import ValidationError

from scripts.scan_credentials import (
    CredentialScanErrorV1,
    CredentialScanReportV1,
    _render_matches,
    scan_changed_files,
)


def test_scanner_reports_rule_without_matched_value(tmp_path: Path) -> None:
    candidate = tmp_path / "sample.txt"
    candidate.write_text("api_key" + "=" + "test-sentinel-value", encoding="utf-8")
    report = scan_changed_files((candidate,))
    rendered = report.model_dump_json()
    assert report.findings[0].rule_id == "GENERIC_API_KEY"
    assert "test-sentinel-value" not in rendered


def test_findings_are_sorted_deterministically(tmp_path: Path) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("SECRET_KEY" + "=" + "value-one", encoding="utf-8")
    second.write_text("AUTH_TOKEN" + "=" + "value-two", encoding="utf-8")
    report = scan_changed_files((second, first))
    assert [finding.path for finding in report.findings] == [str(first), str(second)]
    assert [finding.rule_id for finding in report.findings] == [
        "GENERIC_API_KEY",
        "GENERIC_API_KEY",
    ]
    rendered = report.model_dump_json()
    assert "value-one" not in rendered
    assert "value-two" not in rendered
    assert report.scanned_file_count == 2


def test_prefixed_environment_variable_names_are_detected(
    tmp_path: Path,
) -> None:
    # Env-var spellings with a prefix (OPENAI_API_KEY=, AWS_ACCESS_TOKEN=)
    # must match: the boundary rule allows an underscore prefix, so the
    # common prefixed secret assignment cannot evade the scanner.
    env = tmp_path / "env.txt"
    env.write_text(
        "OPENAI_API_KEY=sk-prefixed-secret\n"
        "AWS_SECRET_KEY=aws-secret-value\n"
        "AWS_ACCESS_TOKEN=aws-token-value\n",
        encoding="utf-8",
    )
    report = scan_changed_files((env,))
    # One finding per (file, rule): the file must be flagged as carrying
    # a generic API key (previously the underscore prefix evaded the rule
    # entirely and the file passed clean).
    assert [finding.rule_id for finding in report.findings] == ["GENERIC_API_KEY"]


def test_spaced_assignment_forms_are_detected(tmp_path: Path) -> None:
    # YAML/TOML-style assignments (`API_KEY = value`) must be detected:
    # the value pattern tolerates whitespace after the separator.
    spaced = tmp_path / "config.yaml"
    spaced.write_text(
        "api_key = sk-spaced-secret\nAWS_ACCESS_TOKEN: aws-token\n",
        encoding="utf-8",
    )
    report = scan_changed_files((spaced,))
    assert [finding.rule_id for finding in report.findings] == ["GENERIC_API_KEY"]
    rendered = report.model_dump_json()
    assert "sk-prefixed-secret" not in rendered
    assert "aws-secret-value" not in rendered
    assert "aws-token-value" not in rendered


def test_private_key_block_and_credential_url_rules(tmp_path: Path) -> None:
    key = tmp_path / "key.pem"
    key.write_text("-----BEGIN " + "RSA PRIVATE KEY-----" + "\nabc\n", encoding="utf-8")
    url = tmp_path / "url.txt"
    url.write_text("https://" + "user" + ":pass" + "@host/path", encoding="utf-8")
    report = scan_changed_files((url, key))
    assert [finding.rule_id for finding in report.findings] == [
        "PRIVATE_KEY_BLOCK",
        "CREDENTIAL_URL",
    ]
    assert report.scanned_file_count == 2


def test_binary_input_is_treated_as_non_text(tmp_path: Path) -> None:
    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\x00\x01\x02" + b"api_key" + b"=" + b"inside-binary")
    report = scan_changed_files((binary,))
    assert report.findings == ()
    assert report.scanned_file_count == 1


def test_empty_file_is_scanned_without_findings(tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    report = scan_changed_files((empty,))
    assert report.findings == ()
    assert report.scanned_file_count == 1


def test_empty_path_sequence_produces_empty_report() -> None:
    report = scan_changed_files(())
    assert report.findings == ()
    assert report.scanned_file_count == 0


def test_missing_path_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    with pytest.raises(CredentialScanErrorV1) as excinfo:
        scan_changed_files((missing,))
    assert excinfo.value.error_code == "CREDENTIAL_SCAN_NOT_REGULAR_FILE"


def test_directory_path_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(CredentialScanErrorV1) as excinfo:
        scan_changed_files((tmp_path,))
    assert excinfo.value.error_code == "CREDENTIAL_SCAN_NOT_REGULAR_FILE"


def test_report_model_is_an_immutable_ordered_sequence(tmp_path: Path) -> None:
    candidate = tmp_path / "sample.txt"
    candidate.write_text("api_key" + "=" + "x", encoding="utf-8")
    report = scan_changed_files((candidate,))
    assert isinstance(report, CredentialScanReportV1)
    assert isinstance(report.findings, tuple)
    assert report.model_config["frozen"] is True
    with pytest.raises(ValidationError):
        setattr(report, "findings", ())
    rendered = report.model_dump_json()
    assert '"path"' in rendered
    assert '"rule_id"' in rendered
    assert '"scanned_file_count"' in rendered


def test_cli_match_line_format_is_redacted_and_relative(tmp_path: Path) -> None:
    candidate = tmp_path / "sample.txt"
    candidate.write_text("api_key" + "=" + "line-value", encoding="utf-8")
    report = scan_changed_files((candidate,))
    rendered = _render_matches(report, tmp_path)
    assert rendered == "MATCH\tsample.txt\tGENERIC_API_KEY"
    assert "line-value" not in rendered


def test_cli_rejects_invalid_arguments() -> None:
    completed = subprocess.run(
        (sys.executable, "scripts/scan_credentials.py", "--changed", "--redact"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "CREDENTIAL_SCAN_INVALID_ARGUMENT" in completed.stderr
