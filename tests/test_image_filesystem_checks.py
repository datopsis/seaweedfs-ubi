"""Image filesystem checks refuse package-manager residue and unsafe modes."""

from __future__ import annotations

import importlib.util
import io
import pathlib
import stat
import sys
import tarfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests" / "lib" / "image_filesystem_checks.py"
SPEC = importlib.util.spec_from_file_location("image_filesystem_checks", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
filesystem_checks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = filesystem_checks
SPEC.loader.exec_module(filesystem_checks)


def archive(*entries: tuple[str, int, bytes | None]) -> io.BytesIO:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        for name, mode, data in entries:
            item = tarfile.TarInfo(name)
            item.mode = mode
            if data is None:
                item.type = tarfile.DIRTYPE
            else:
                item.size = len(data)
            tar.addfile(item, io.BytesIO(data) if data is not None else None)
    output.seek(0)
    return output


class ImageFilesystemTests(unittest.TestCase):
    def test_minimal_runtime_and_declared_tmp_are_accepted(self) -> None:
        count, findings = filesystem_checks.inspect_export(archive(
            ("usr/local/bin/weed", 0o555, b"weed"),
            ("etc/pki/tls/certs/ca-bundle.crt", 0o444, b"ca"),
            ("tmp", 0o1777, None),
        ))
        self.assertEqual(count, 3)
        self.assertEqual(findings, [])

    def test_package_managers_and_repository_residue_are_refused(self) -> None:
        _, findings = filesystem_checks.inspect_export(archive(
            ("usr/bin/dnf", 0o755, b"tool"),
            ("bin/rpm", 0o755, b"tool"),
            ("usr/libexec/dnf5", 0o755, b"tool"),
            ("etc/yum.repos.d/ubi.repo", 0o644, b"repo"),
            ("etc/pki/rpm-gpg/RPM-GPG-KEY", 0o644, b"key"),
        ))
        self.assertEqual(sum("package manager" in item for item in findings), 3)
        self.assertEqual(sum("repository or key" in item for item in findings), 2)

    def test_privilege_bits_and_undeclared_world_writes_are_refused(self) -> None:
        _, findings = filesystem_checks.inspect_export(archive(
            ("usr/bin/helper", 0o755 | stat.S_ISUID, b"binary"),
            ("usr/bin/second", 0o755 | stat.S_ISGID, b"binary"),
            ("var/cache", 0o777, None),
            ("etc/config", 0o666, b"config"),
        ))
        self.assertEqual(sum("setuid/setgid" in item for item in findings), 2)
        self.assertEqual(sum("world-writable" in item for item in findings), 2)

    def test_empty_export_is_not_a_pass(self) -> None:
        _, findings = filesystem_checks.inspect_export(archive())
        self.assertIn("empty image filesystem export", findings)

    def test_absolute_and_traversal_paths_are_refused(self) -> None:
        _, findings = filesystem_checks.inspect_export(archive(
            ("/etc/hidden", 0o644, b"bad"),
            ("etc/../hidden", 0o644, b"bad"),
        ))
        self.assertEqual(sum("unsafe archive path" in item for item in findings), 2)

    def test_malformed_export_does_not_pass(self) -> None:
        with self.assertRaises(tarfile.TarError):
            filesystem_checks.inspect_export(io.BytesIO(b"not a tar archive"))


if __name__ == "__main__":
    unittest.main()
