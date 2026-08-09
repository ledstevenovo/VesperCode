"""T37.1 legacy step 37.A: README contract verifier tests."""

from __future__ import annotations

from pathlib import Path

import pytest

# The report models are pydantic runtime contracts; the hash-locked gate
# toolchain does not install runtime dependencies, so this module skips
# cleanly there instead of failing at collection (formal env runs it fully).
pytest.importorskip("pydantic")

from conftest import write_readme_without_section  # type: ignore[import-not-found]  # noqa: E402

from scripts.verify_readme_contract import (  # noqa: E402
    README_SECTIONS,
    ReadmeContractResultV1,
    verify_readme_contract,
)


def test_readme_fails_when_release_digest_verification_is_missing(
    repository_copy: Path,
) -> None:
    write_readme_without_section(repository_copy, "Reference image digest verification")
    result = verify_readme_contract(repository_copy / "README.md")
    assert "README_REFERENCE_DIGEST_INSTRUCTIONS_MISSING" in result.error_codes


def test_full_contract_readme_passes(repository_copy: Path) -> None:
    # Every contract section present -> no error codes at all.
    write_readme_without_section(repository_copy, "")
    result = verify_readme_contract(repository_copy / "README.md")
    assert result.error_codes == ()


def test_missing_readme_fails_closed(repository_copy: Path) -> None:
    (repository_copy / "README.md").unlink()
    with pytest.raises(FileNotFoundError):
        verify_readme_contract(repository_copy / "README.md")


def test_each_section_maps_to_its_own_error_code(
    repository_copy: Path,
) -> None:
    for title, code in README_SECTIONS.items():
        write_readme_without_section(repository_copy, title)
        result = verify_readme_contract(repository_copy / "README.md")
        assert code in result.error_codes
        assert len(result.error_codes) == 1, (title, result.error_codes)


def test_heading_with_prefix_text_is_still_detected(repository_copy: Path) -> None:
    # A README that carries every section heading with surrounding prose
    # must pass; only missing headings fail.
    text = "\n\n".join(
        f"## {title}\n\nSome verified content for {title}." for title in README_SECTIONS
    )
    readme = repository_copy / "README.md"
    readme.write_text(text + "\n", encoding="utf-8")
    assert verify_readme_contract(readme).error_codes == ()


def test_result_model_is_an_immutable_ordered_sequence(
    repository_copy: Path,
) -> None:
    write_readme_without_section(repository_copy, "Installation")
    result = verify_readme_contract(repository_copy / "README.md")
    assert isinstance(result, ReadmeContractResultV1)
    assert isinstance(result.error_codes, tuple)
    assert result.model_config["frozen"] is True
    with pytest.raises(Exception):
        result.error_codes = ()
