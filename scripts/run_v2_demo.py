"""Run the bounded v2 mechanism demo without network or credentials."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from vespercode.llm.v2 import ScriptedLLMV2
from vespercode.runtime_v2 import V2Harness, V2HarnessConfig


def run_demo() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="vespercode-v2-demo-") as directory:
        root = Path(directory)
        harness = V2Harness(V2HarnessConfig(root, root / "control", max_turns=5))
        try:
            result = harness.run(
                "repair the failing example",
                ScriptedLLMV2(
                    [
                        {
                            "action_type": "REPLACE",
                            "path": "tests/test_example.py",
                            "content": "blocked",
                        },
                        {
                            "action_type": "REPLACE",
                            "path": "src/example.py",
                            "content": "corrected",
                        },
                        {"action_type": "DONE"},
                    ]
                ),
            )
            return {
                "schema_version": 2,
                "run_id": result.run_id,
                "status": result.loop.status,
                "stop_reason": result.loop.stop_reason,
                "turns": result.loop.turns,
                "stages": [
                    {"status": item.status, "message": item.message}
                    for item in result.loop.results
                ],
                "corrected_paths": sorted(harness.workspace_port.files),
                "v2_mechanism": "revision-bound behavior governance",
            }
        finally:
            harness.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run_demo()
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.report is None:
        print(encoded, end="")
    else:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
        print(f"wrote {args.report} ({len(encoded.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
