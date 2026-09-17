from __future__ import annotations

import io
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "scripts" / "lib"))

from validate_backup import BackupValidationError, validate_archive  # noqa: E402


class BackupArchiveValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            dir=pathlib.Path(__file__).parent
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = pathlib.Path(self.temporary_directory.name)

    def archive_with(self, name: str, content: bytes = b"state") -> pathlib.Path:
        path = self.directory / "backup.tar"
        with tarfile.open(path, "w") as archive:
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
        return path

    def test_accepts_a_regular_relative_file(self) -> None:
        validate_archive(self.archive_with("data/state.db"))

    def test_refuses_a_missing_archive(self) -> None:
        with self.assertRaisesRegex(BackupValidationError, "does not exist"):
            validate_archive(self.directory / "missing.tar")

    def test_refuses_a_malformed_archive(self) -> None:
        path = self.directory / "backup.tar"
        path.write_bytes(b"not a tar archive")
        with self.assertRaisesRegex(BackupValidationError, "not readable"):
            validate_archive(path)

    def test_refuses_an_empty_archive(self) -> None:
        path = self.directory / "backup.tar"
        with tarfile.open(path, "w"):
            pass
        with self.assertRaisesRegex(BackupValidationError, "has no files"):
            validate_archive(path)

    def test_refuses_parent_traversal(self) -> None:
        with self.assertRaisesRegex(BackupValidationError, "unsafe path"):
            validate_archive(self.archive_with("../outside"))

    def test_refuses_an_absolute_path(self) -> None:
        with self.assertRaisesRegex(BackupValidationError, "unsafe path"):
            validate_archive(self.archive_with("/outside"))

    def test_refuses_a_symbolic_link(self) -> None:
        path = self.directory / "backup.tar"
        with tarfile.open(path, "w") as archive:
            entry = tarfile.TarInfo("link")
            entry.type = tarfile.SYMTYPE
            entry.linkname = "target"
            archive.addfile(entry)
        with self.assertRaisesRegex(BackupValidationError, "special entry"):
            validate_archive(path)

    def test_refuses_a_forbidden_runtime_value(self) -> None:
        path = self.archive_with("data/state.db", b"prefix generated-secret suffix")
        with self.assertRaisesRegex(BackupValidationError, "forbidden runtime value"):
            validate_archive(path, (b"generated-secret",))

    def test_cli_refuses_a_forbidden_value_starting_with_a_hyphen(self) -> None:
        path = self.archive_with("data/state.db", b"prefix -leading-secret suffix")
        validator = pathlib.Path(__file__).parents[1] / "scripts" / "lib" / "validate_backup.py"
        result = subprocess.run(
            [
                sys.executable,
                str(validator),
                "--forbid-value=-leading-secret",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("forbidden runtime value", result.stderr)


if __name__ == "__main__":
    unittest.main()
