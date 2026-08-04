from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.gate_scan import GateScanHooksV1, run_gate_scan
from scripts.run_gate_checks import build_closed_argv, main, run_closed_command
from scripts.bootstrap_gate_env import (
    EvidenceInvalid,
    main as bootstrap_main,
    verify_evidence,
)

ROOT = Path(__file__).resolve().parents[3]


class AaIntegrityTests(unittest.TestCase):
    def test_gate_input_lists_exact_direct_requirements(self) -> None:
        expected = b"pytest>=8,<9\nruff\nmypy\npywin32\ndocker\n"
        self.assertEqual((ROOT / "requirements/gate.in").read_bytes(), expected)
        self.assertEqual((ROOT / ".gitignore").read_bytes(), b".venv-gate/\n")
        self.assertEqual(
            (ROOT / "gates/pytest.ini").read_bytes(),
            b"[pytest]\naddopts =\ntestpaths = tests\npython_files = test_*.py\n",
        )
        self.assertEqual(
            (ROOT / "gates/ruff.toml").read_bytes(),
            b'target-version = "py312"\nline-length = 88\n'
            b'extend-exclude = [".venv-gate", "*.md"]\n\n[format]\n'
            b'line-ending = "lf"\nquote-style = "double"\nindent-style = "space"\n\n'
            b'[lint]\nselect = ["E4", "E7", "E9", "F"]\n',
        )
        self.assertEqual(
            (ROOT / "gates/mypy.ini").read_bytes(),
            b"[mypy]\npython_version = 3.12\n"
            b"strict = True\nwarn_unused_configs = True\n",
        )

    def test_gate_runner_accepts_closed_command_and_separator(self) -> None:
        calls: list[tuple[str, ...]] = []

        def execute(argv: tuple[str, ...]) -> int:
            calls.append(argv)
            return 0

        self.assertEqual(run_closed_command("ruff-format", (".",), execute=execute), 0)
        self.assertEqual(run_closed_command("ruff-check", (".",), execute=execute), 0)
        self.assertEqual(
            run_closed_command(
                "pytest",
                ("tests/feasibility/gate/test_gate_bootstrap.py", "-q"),
                execute=execute,
            ),
            0,
        )
        self.assertNotIn("--", calls[0])
        self.assertEqual(calls[0][-1], ".")
        self.assertEqual(calls[1][-1], ".")
        self.assertEqual(
            calls[2][-2:],
            ("tests/feasibility/gate/test_gate_bootstrap.py", "-q"),
        )
        self.assertIn("gates/ruff.toml", calls[0])
        self.assertIn("gates/pytest.ini", calls[2])
        self.assertEqual(build_closed_argv("mypy", ("src",))[-1], "src")

    def test_gate_runner_rejects_unknown_command_or_missing_separator(self) -> None:
        calls: list[tuple[str, ...]] = []
        stdout = StringIO()
        stderr = StringIO()

        def record_unknown(argv: tuple[str, ...]) -> int:
            calls.append(argv)
            return 0

        with redirect_stdout(stdout), redirect_stderr(stderr):
            unknown_result = run_closed_command("shell", (), execute=record_unknown)
            with patch("scripts.run_gate_checks.run_closed_command") as wrapped:
                missing_separator_result = main(["pytest", "tests/test_example.py"])
                self.assertFalse(wrapped.called)
        self.assertEqual(unknown_result, 2)
        self.assertEqual(missing_separator_result, 2)
        self.assertEqual(calls, [])
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            stderr.getvalue(),
            "ERROR\tGATE_COMMAND_UNKNOWN\nERROR\tGATE_ARGUMENT_SEPARATOR_MISSING\n",
        )

    def test_gate_runner_rejects_argument_widening(self) -> None:
        forbidden = (
            "--config=other.ini",
            "--plugin=unsafe",
            "--python=other.exe",
            "PYTHONPATH=outside",
            "--rootdir=outside",
            "--cache-dir=cache",
            "--junitxml=report.xml",
            "--index-url=https://example.invalid",
            "tests/*.py",
            "../outside.py",
            "--maxfail=0",
        )
        calls: list[tuple[str, ...]] = []
        stdout = StringIO()
        stderr = StringIO()

        def record_forbidden(argv: tuple[str, ...]) -> int:
            calls.append(argv)
            return 0

        with redirect_stdout(stdout), redirect_stderr(stderr):
            results = tuple(
                run_closed_command(
                    "pytest",
                    (argument,),
                    execute=record_forbidden,
                )
                for argument in forbidden
            )
        self.assertEqual(results, (2,) * len(forbidden))
        self.assertEqual(calls, [])
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            stderr.getvalue(),
            "ERROR\tGATE_ARGUMENT_WIDENING\n" * len(forbidden),
        )

    def test_gate_scan_emits_sorted_redacted_rule_ids(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            payloads = {
                "staged.pem": (
                    b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----\n" + b"secret\n"
                ),
                "unstaged.txt": b"prefix " + b"API_" + b"KEY='do-not-print' suffix",
                "untracked.txt": (
                    b"https://user:" + b"do-not-print" + b"@example.invalid/"
                ),
            }
            hooks = GateScanHooksV1(
                enumerate_changed_paths=lambda unused_root: (
                    "untracked.txt",
                    "staged.pem",
                    "unstaged.txt",
                    "staged.pem",
                ),
                resolve_path=lambda active_root, path: active_root / path,
                is_regular_file=lambda path: True,
                read_bytes=lambda path: payloads[path.name],
            )
            result = run_gate_scan(root, hooks=hooks)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(
            result.stdout,
            "MATCH\tstaged.pem\tPRIVATE_KEY_BLOCK\n"
            "MATCH\tunstaged.txt\tGENERIC_API_KEY\n"
            "MATCH\tuntracked.txt\tCREDENTIAL_URL\n",
        )
        self.assertEqual(result.stderr, "")
        self.assertNotIn("do-not-print", result.stdout)
        wrapper = (ROOT / "scripts/scan_gate_changed_files.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("$args.Count", wrapper)
        self.assertIn(".venv-gate", wrapper)
        self.assertIn("Scripts", wrapper)
        self.assertIn("python.exe", wrapper)
        self.assertIn("gate_scan.py", wrapper)
        self.assertNotIn("PRIVATE_KEY_BLOCK", wrapper)
        self.assertNotIn("GENERIC_API_KEY", wrapper)

    def test_gate_scan_fails_closed_on_git_path_object_or_read_error(self) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory).resolve()
            outside_path = Path(outside).resolve() / "escaped.txt"

            def enumerate_changed_paths(unused_root: Path) -> tuple[str, ...]:
                return ("changed.txt",)

            def resolve_path(active_root: Path, path: str) -> Path:
                return active_root / path

            def is_regular_file(unused_path: Path) -> bool:
                return True

            def read_bytes(unused_path: Path) -> bytes:
                return b"API_" + b"KEY=must-not-appear"

            def fail_enumeration(unused_root: Path) -> tuple[str, ...]:
                raise OSError("injected failure")

            def resolve_outside(unused_root: Path, unused_path: str) -> Path:
                return outside_path

            def fail_read(unused_path: Path) -> bytes:
                raise OSError("injected failure")

            cases = (
                (
                    GateScanHooksV1(
                        enumerate_changed_paths=fail_enumeration,
                        resolve_path=resolve_path,
                        is_regular_file=is_regular_file,
                        read_bytes=read_bytes,
                    ),
                    "GATE_SCAN_GIT_ENUMERATION_FAILED",
                ),
                (
                    GateScanHooksV1(
                        enumerate_changed_paths=enumerate_changed_paths,
                        resolve_path=resolve_outside,
                        is_regular_file=is_regular_file,
                        read_bytes=read_bytes,
                    ),
                    "GATE_SCAN_PATH_ESCAPE",
                ),
                (
                    GateScanHooksV1(
                        enumerate_changed_paths=enumerate_changed_paths,
                        resolve_path=resolve_path,
                        is_regular_file=lambda unused_path: False,
                        read_bytes=read_bytes,
                    ),
                    "GATE_SCAN_NON_REGULAR_FILE",
                ),
                (
                    GateScanHooksV1(
                        enumerate_changed_paths=enumerate_changed_paths,
                        resolve_path=resolve_path,
                        is_regular_file=is_regular_file,
                        read_bytes=fail_read,
                    ),
                    "GATE_SCAN_READ_FAILED",
                ),
            )
            results = tuple(run_gate_scan(root, hooks=hooks) for hooks, _ in cases)
        self.assertEqual(tuple(result.exit_code for result in results), (2, 2, 2, 2))
        self.assertEqual(tuple(result.stdout for result in results), ("", "", "", ""))
        self.assertEqual(
            tuple(result.stderr for result in results),
            tuple(f"ERROR\t{code}\n" for _, code in cases),
        )
        self.assertTrue(
            all("must-not-appear" not in result.stderr for result in results)
        )


class AbAcIntegrityTests(unittest.TestCase):
    def test_bootstrap_cli_rejects_invalid_invocation_and_python(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            unknown_result = bootstrap_main(["explode"])
            bad_index_result = bootstrap_main(
                [
                    "resolve-lock",
                    "--input",
                    "requirements/gate.in",
                    "--lock",
                    "requirements/gate.lock",
                    "--index-url",
                    "https://example.invalid/simple",
                ]
            )
            missing_flags_result = bootstrap_main(["materialize"])
            wrong_python_result = bootstrap_main(
                [
                    "materialize",
                    "--lock",
                    "requirements/gate.lock",
                    "--evidence",
                    "gates/evidence/gate-toolchain-v1.json",
                ],
                python_version_info=(3, 11, 0),
            )
        self.assertEqual(
            (
                unknown_result,
                bad_index_result,
                missing_flags_result,
                wrong_python_result,
            ),
            (2, 2, 2, 3),
        )
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            stderr.getvalue(),
            "ERROR\tGATE_ARGUMENT_INVALID\n"
            "ERROR\tGATE_ARGUMENT_INVALID\n"
            "ERROR\tGATE_ARGUMENT_INVALID\n"
            "ERROR\tGATE_PYTHON_VERSION_MISMATCH\n",
        )

    def test_bootstrap_cli_rejects_malformed_lock_before_install(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            lock = root / "gate.lock"
            lock.write_bytes(b"--index-url https://pypi.org/simple\npytest==99.0\n")
            evidence = root / "evidence.json"
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = bootstrap_main(
                    [
                        "materialize",
                        "--lock",
                        str(lock),
                        "--evidence",
                        str(evidence),
                    ]
                )
            self.assertEqual(result, 4)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "ERROR\tGATE_LOCK_INVALID\n")
            self.assertFalse(evidence.exists())

    def test_bootstrap_cli_require_existing_evidence_rejects_missing(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            empty_lock = root / "gate.lock"
            empty_lock.write_bytes(b"--index-url https://pypi.org/simple\n")
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                missing_evidence_result = bootstrap_main(
                    [
                        "materialize",
                        "--lock",
                        str(empty_lock),
                        "--evidence",
                        str(root / "missing-evidence.json"),
                        "--require-existing-evidence",
                    ]
                )
                missing_lock_result = bootstrap_main(
                    [
                        "materialize",
                        "--lock",
                        str(root / "missing.lock"),
                        "--evidence",
                        str(root / "missing-evidence.json"),
                        "--require-existing-evidence",
                    ]
                )
            self.assertEqual(missing_evidence_result, 7)
            self.assertEqual(missing_lock_result, 4)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(
                stderr.getvalue(),
                "ERROR\tGATE_EVIDENCE_INVALID\nERROR\tGATE_LOCK_INVALID\n",
            )

    def test_gate_lock_is_pip_hash_locked_and_complete(self) -> None:
        text = (ROOT / "requirements/gate.lock").read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        lines = text.splitlines()
        self.assertEqual(lines[0], "--index-url https://pypi.org/simple")
        versions: dict[str, str] = {}
        order: list[str] = []
        for line in lines[1:]:
            if not line:
                continue
            for forbidden in (
                "--extra-index-url",
                "--find-links",
                "--trusted-host",
                "-e ",
                "file://",
                "git+",
            ):
                self.assertNotIn(forbidden, line)
            name, separator, remainder = line.partition("==")
            self.assertTrue(separator)
            normalized_chars = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
            self.assertTrue(name)
            self.assertTrue(all(char in normalized_chars for char in name))
            self.assertNotIn("@", remainder)
            pinned, _, hashes = remainder.partition(" --hash=")
            self.assertTrue(hashes)
            if ";" in pinned:
                pinned, _, marker = pinned.partition(";")
                self.assertTrue(marker.strip())
            self.assertTrue(pinned.strip())
            for token in hashes.split(" --hash="):
                self.assertEqual(token[:7], "sha256:")
                self.assertEqual(len(token[7:]), 64)
                int(token[7:], 16)
            versions[name] = pinned
            order.append(name)
        self.assertEqual(order, sorted(order))
        self.assertEqual(len(versions), len(set(versions)))
        self.assertEqual(
            versions,
            {
                "ast-serialize": "0.6.0",
                "certifi": "2026.7.22",
                "charset-normalizer": "3.4.9",
                "colorama": "0.4.6",
                "docker": "7.2.0",
                "idna": "3.18",
                "iniconfig": "2.3.0",
                "librt": "0.13.0",
                "mypy": "2.3.0",
                "mypy-extensions": "1.1.0",
                "packaging": "26.2",
                "pathspec": "1.1.1",
                "pluggy": "1.6.0",
                "pygments": "2.20.0",
                "pytest": "8.4.2",
                "pywin32": "312",
                "requests": "2.34.2",
                "ruff": "0.16.1",
                "typing-extensions": "4.16.0",
                "urllib3": "2.7.0",
            },
        )

    def test_gate_evidence_round_trip_binds_all_identities(self) -> None:
        evidence_path = ROOT / "gates/evidence/gate-toolchain-v1.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(evidence),
            {
                "schema_version",
                "evidence_type",
                "python_version",
                "pytest_version",
                "ruff_version",
                "mypy_version",
                "gate_input_sha256",
                "gate_lock_sha256",
                "pytest_config_sha256",
                "ruff_config_sha256",
                "mypy_config_sha256",
                "runner_sha256",
                "gate_scan_sha256",
                "gate_scan_core_sha256",
                "evidence_digest",
            },
        )
        self.assertEqual(evidence["schema_version"], 1)
        self.assertEqual(evidence["evidence_type"], "GATE_TOOLCHAIN_EVIDENCE_V1")
        self.assertRegex(evidence["python_version"], r"3\.12\.[0-9]+")
        digest_paths = {
            "gate_input_sha256": "requirements/gate.in",
            "gate_lock_sha256": "requirements/gate.lock",
            "pytest_config_sha256": "gates/pytest.ini",
            "ruff_config_sha256": "gates/ruff.toml",
            "mypy_config_sha256": "gates/mypy.ini",
            "runner_sha256": "scripts/run_gate_checks.py",
            "gate_scan_sha256": "scripts/scan_gate_changed_files.ps1",
            "gate_scan_core_sha256": "scripts/gate_scan.py",
        }
        for field, rel_path in digest_paths.items():
            self.assertRegex(evidence[field], r"[0-9a-f]{64}")
            digest = hashlib.sha256((ROOT / rel_path).read_bytes()).hexdigest()
            self.assertEqual(evidence[field], digest)
        without_digest = {
            key: value for key, value in evidence.items() if key != "evidence_digest"
        }
        canonical = json.dumps(without_digest, sort_keys=True, separators=(",", ":"))
        self.assertEqual(
            evidence["evidence_digest"],
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )
        with TemporaryDirectory():
            drifted = dict(evidence)
            drifted["gate_scan_core_sha256"] = "0" * 64
            with self.assertRaises(EvidenceInvalid):
                verify_evidence(drifted, ROOT / "requirements/gate.lock", ROOT)


if __name__ == "__main__":
    unittest.main()
