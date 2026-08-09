"""T37.1 legacy step 37.A: README contract verifier (read-only, fail-closed).

Checks that ``README.md`` carries every required contract section — the
actionable release-digest verification instructions, installation, usage,
distribution, directory layout, secure key setup, limitations, CI/CD record,
and WebUI URL status.  The section headings form the single source of truth
for both the verifier and the test fixtures (``write_readme_without_section``
writes every section except the named one), so a missing heading is a
deterministic, reproducible failure.  The verifier never mutates the README
and performs no external I/O beyond reading the supplied file.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

# Ordered mapping of required README section headings to their fail-closed
# error codes.  The heading text is what both the real README and the test
# fixtures must use; the error code is what verifiers and consumers report.
README_SECTIONS: dict[str, str] = {
    "Reference image digest verification": (
        "README_REFERENCE_DIGEST_INSTRUCTIONS_MISSING"
    ),
    "Installation": "README_INSTALLATION_MISSING",
    "Usage": "README_USAGE_MISSING",
    "Distribution": "README_DISTRIBUTION_MISSING",
    "Directory layout": "README_DIRECTORY_LAYOUT_MISSING",
    "Secure key setup": "README_SECURE_KEY_SETUP_MISSING",
    "Limitations": "README_LIMITATIONS_MISSING",
    "CI/CD": "README_CI_RECORD_MISSING",
    "Web UI": "README_WEBUI_URL_MISSING",
}


class ReadmeContractResultV1(BaseModel):
    """The deterministic README contract verdict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    error_codes: tuple[str, ...] = ()


def _has_section_heading(text: str, title: str) -> bool:
    """True if *title* appears as any markdown heading (``#`` .. ``######``)."""
    return (
        re.search(r"^#{1,6}\s+" + re.escape(title) + r"\s*$", text, flags=re.MULTILINE)
        is not None
    )


def verify_readme_contract(path: Path | str) -> ReadmeContractResultV1:
    """Fail-closed README contract check.

    Every required section heading must be present; any missing heading is
    reported as its dedicated error code.  A missing file fails loudly with
    ``FileNotFoundError`` rather than returning a partial verdict.
    """
    readme = Path(path)
    if not readme.is_file():
        raise FileNotFoundError(f"missing README.md: {readme}")
    text = readme.read_text(encoding="utf-8")
    missing = tuple(
        code
        for title, code in README_SECTIONS.items()
        if not _has_section_heading(text, title)
    )
    return ReadmeContractResultV1(error_codes=missing)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: verify README.md; exit 0 only when every section passes."""
    parser = argparse.ArgumentParser(
        description="Verify the README contract (read-only)."
    )
    parser.add_argument("readme_path", type=Path, help="path to README.md to verify")
    args = parser.parse_args(argv)
    try:
        result = verify_readme_contract(args.readme_path)
    except Exception as exc:
        print(f"README contract REJECTED: {exc}")
        return 1
    if result.error_codes:
        print(f"README contract REJECTED: {', '.join(result.error_codes)}")
        return 1
    print("README contract ACCEPTED: all required sections present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
