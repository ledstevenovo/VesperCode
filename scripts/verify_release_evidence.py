"""T36.1 legacy step 36.A: read-only release-evidence verifier CLI.

Reads ``ci-v1.json``, ``release-v1.json``, and ``deployment-v1.json``
from the evidence root and verifies the closed schemas plus the exact
alignment rules; ``--live`` additionally requires terminal-success and
fresh records.  The verifier never mutates the evidence store and
performs zero external I/O beyond reading the three files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from vespercode.delivery.evidence import load_and_verify_release_evidence  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the frozen delivery evidence (read-only)."
    )
    parser.add_argument(
        "evidence_root",
        type=Path,
        help="directory holding ci-v1.json, release-v1.json, deployment-v1.json",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="require terminal-success and fresh (24 h) records",
    )
    args = parser.parse_args(argv)
    try:
        bundle = load_and_verify_release_evidence(
            args.evidence_root, require_live=args.live
        )
    except Exception as exc:
        print(f"release evidence REJECTED: {exc}")
        return 1
    print(
        f"release evidence ACCEPTED: source_commit={bundle.release.source_commit} "
        f"tag={bundle.release.tag_name} wheel={bundle.release.wheel_sha256[:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
