"""Route A / A1: real path/object boundary for v2 filesystem access.

The boundary is the only component that turns a model-supplied relative
path into a real filesystem object reference.  It fails closed on every
aliasing or traversal hazard: noncanonical spellings, workspace escape,
symlinks and Windows reparse points (including junctions, which
``Path.is_symlink`` does not report), directory targets, missing parents,
Windows reserved device names, and Windows trailing-dot/space stripping.
A final ``recheck_before_mutation`` re-runs the whole validation to shrink
the TOCTOU window immediately before a write.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from vespercode.workspace.v2_boundary import (
    ResolvedPathV2,
    WorkspaceBoundaryError,
    WorkspaceBoundaryV2,
)

IS_WINDOWS = sys.platform == "win32"


class WorkspaceBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.boundary = WorkspaceBoundaryV2(self.root)
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("print('app')\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._directory.cleanup()

    def test_resolves_canonical_relative_paths_inside_the_workspace(self) -> None:
        resolved = self.boundary.resolve("src/app.py")
        self.assertIsInstance(resolved, ResolvedPathV2)
        self.assertEqual(resolved.relative.as_posix(), "src/app.py")
        self.assertEqual(
            resolved.absolute,
            (self.root / "src" / "app.py").resolve(strict=False),
        )

    def test_rejects_noncanonical_and_absolute_spellings(self) -> None:
        for bad in (
            "",
            "src//app.py",
            "./src/app.py",
            "src/./app.py",
            "src/../app.py",
            "../escape.py",
            "src\\app.py",
            "/absolute.py",
            "C:/absolute.py",
            "src/app\x00.py",
            "src/\napp.py",
            "src/app.py:",
        ):
            with self.assertRaises(WorkspaceBoundaryError, msg=repr(bad)):
                self.boundary.resolve(bad)

    def test_rejects_paths_that_leave_the_workspace_after_resolution(self) -> None:
        with self.assertRaises(WorkspaceBoundaryError):
            self.boundary.resolve("src/../../outside.py")

    def test_rejects_escape_through_a_symlinked_directory(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="vesper-outside-"))
        try:
            link = self.root / "src" / "linked"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable")
            with self.assertRaisesRegex(WorkspaceBoundaryError, "link"):
                self.boundary.resolve("src/linked/secret.py")
        finally:
            for child in outside.iterdir():
                child.unlink()
            outside.rmdir()

    def test_rejects_missing_or_non_directory_workspace_root(self) -> None:
        with self.assertRaises(WorkspaceBoundaryError):
            WorkspaceBoundaryV2(self.root / "does-not-exist").resolve("src/app.py")
        (self.root / "plain-file").write_text("x", encoding="utf-8")
        with self.assertRaises(WorkspaceBoundaryError):
            WorkspaceBoundaryV2(self.root / "plain-file").resolve("src/app.py")

    def test_check_read_distinguishes_clean_absence_and_reports_files(self) -> None:
        self.assertIsNone(self.boundary.check_read("src/missing.py"))
        resolved = self.boundary.check_read("src/app.py")
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.relative.as_posix(), "src/app.py")

    def test_check_read_rejects_directories(self) -> None:
        with self.assertRaisesRegex(WorkspaceBoundaryError, "regular file"):
            self.boundary.check_read("src")

    def test_check_write_target_requires_existing_parent_directory(self) -> None:
        with self.assertRaisesRegex(WorkspaceBoundaryError, "parent"):
            self.boundary.check_write_target("missing-dir/new.py", "CREATE")

    def test_check_write_target_create_requires_absent_regular_target(self) -> None:
        resolved = self.boundary.check_write_target("src/new.py", "CREATE")
        self.assertEqual(resolved.relative.as_posix(), "src/new.py")
        with self.assertRaisesRegex(WorkspaceBoundaryError, "CREATE"):
            self.boundary.check_write_target("src/app.py", "CREATE")
        with self.assertRaisesRegex(WorkspaceBoundaryError, "CREATE"):
            self.boundary.check_write_target("src", "CREATE")

    def test_check_write_target_replace_requires_existing_regular_file(self) -> None:
        resolved = self.boundary.check_write_target("src/app.py", "REPLACE")
        self.assertEqual(resolved.relative.as_posix(), "src/app.py")
        with self.assertRaisesRegex(WorkspaceBoundaryError, "REPLACE"):
            self.boundary.check_write_target("src/missing.py", "REPLACE")
        with self.assertRaisesRegex(WorkspaceBoundaryError, "REPLACE"):
            self.boundary.check_write_target("src", "REPLACE")

    def test_check_write_target_rejects_unknown_action_types(self) -> None:
        with self.assertRaises(WorkspaceBoundaryError):
            self.boundary.check_write_target("src/new.py", "DELETE")

    def test_recheck_before_mutation_revalidates_and_catches_toctou_changes(self) -> None:
        resolved = self.boundary.check_write_target("src/app.py", "REPLACE")
        self.boundary.recheck_before_mutation(resolved, "REPLACE")

        # A file created after the first check must fail the CREATE recheck.
        late = self.boundary.check_write_target("src/late.py", "CREATE")
        (self.root / "src" / "late.py").write_text("race", encoding="utf-8")
        with self.assertRaises(WorkspaceBoundaryError):
            self.boundary.recheck_before_mutation(late, "CREATE")

        # A target replaced by a directory after the check must fail REPLACE.
        hijacked = self.boundary.check_write_target("src/hijack.py", "REPLACE") \
            if (self.root / "src" / "hijack.py").exists() else None
        if hijacked is None:
            (self.root / "src" / "hijack.py").write_text("x", encoding="utf-8")
            hijacked = self.boundary.check_write_target("src/hijack.py", "REPLACE")
        (self.root / "src" / "hijack.py").unlink()
        (self.root / "src" / "hijack.py").mkdir()
        try:
            with self.assertRaises(WorkspaceBoundaryError):
                self.boundary.recheck_before_mutation(hijacked, "REPLACE")
        finally:
            (self.root / "src" / "hijack.py").rmdir()


@unittest.skipUnless(IS_WINDOWS, "Windows reserved device names and aliasing rules")
class WindowsBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.boundary = WorkspaceBoundaryV2(self.root)
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("print('app')\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._directory.cleanup()

    def test_rejects_windows_reserved_device_names(self) -> None:
        for name in ("CON", "con.py", "PRN.txt", "AUX", "NUL", "COM1.log", "lpt9"):
            with self.assertRaisesRegex(WorkspaceBoundaryError, "reserved", msg=name):
                self.boundary.resolve(f"src/{name}")

    def test_rejects_trailing_dots_and_spaces_stripped_by_win32(self) -> None:
        for name in ("trailing.", "trailing ", "trailing... ", "a.b."):
            with self.assertRaises(WorkspaceBoundaryError, msg=repr(name)):
                self.boundary.resolve(f"src/{name}")

    def test_rejects_escape_through_a_directory_junction(self) -> None:
        try:
            import _winapi  # noqa: PLC0415 - Windows-only private hook
        except ImportError:
            self.skipTest("_winapi is unavailable")
        outside = Path(tempfile.mkdtemp(prefix="vesper-outside-"))
        junction = self.root / "junction"
        try:
            try:
                _winapi.CreateJunction(str(outside), str(junction))
            except OSError:
                self.skipTest("junction creation is unavailable")
            # A junction is a reparse point that Path.is_symlink() does NOT
            # report; the boundary must refuse it via the reparse attribute.
            self.assertFalse(junction.is_symlink())
            with self.assertRaisesRegex(WorkspaceBoundaryError, "link"):
                self.boundary.resolve("junction/inside.py")
            with self.assertRaisesRegex(WorkspaceBoundaryError, "link"):
                self.boundary.check_write_target("junction/new.py", "CREATE")
        finally:
            try:
                os.rmdir(junction)
            except OSError:
                pass
            for child in outside.iterdir():
                child.unlink()
            outside.rmdir()

    def test_rejects_reads_through_a_directory_junction(self) -> None:
        try:
            import _winapi  # noqa: PLC0415 - Windows-only private hook
        except ImportError:
            self.skipTest("_winapi is unavailable")
        outside = Path(tempfile.mkdtemp(prefix="vesper-outside-"))
        (outside / "secret.py").write_text("secret", encoding="utf-8")
        junction = self.root / "junction"
        try:
            try:
                _winapi.CreateJunction(str(outside), str(junction))
            except OSError:
                self.skipTest("junction creation is unavailable")
            with self.assertRaises(WorkspaceBoundaryError):
                self.boundary.check_read("junction/secret.py")
        finally:
            try:
                os.rmdir(junction)
            except OSError:
                pass
            (outside / "secret.py").unlink()
            outside.rmdir()


if __name__ == "__main__":
    unittest.main()
