"""Regression tests for missing, inherited, and mismatched image provenance."""

import hashlib
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent / "lib"))

from provenancechecks import LOCK, REVISION, validate  # noqa: E402


class ProvenanceChecksTests(unittest.TestCase):
    revision = "1" * 40
    lock = b'{"architectures": {"amd64": {}, "arm64": {}}}\n'

    def inspection(self):
        return [{"Config": {"Labels": {
            REVISION: self.revision,
            LOCK: hashlib.sha256(self.lock).hexdigest(),
        }}}]

    def test_accepts_exact_source_revision_and_raw_lock_hash(self):
        validate(self.inspection(), self.revision, self.lock)

    def test_rejects_missing_empty_and_wrong_labels(self):
        for name in (REVISION, LOCK):
            for value in (None, "", "unknown", "9" * 40, "0" * 64):
                with self.subTest(name=name, value=value):
                    inspection = self.inspection()
                    labels = inspection[0]["Config"]["Labels"]
                    if value is None:
                        del labels[name]
                    else:
                        labels[name] = value
                    with self.assertRaisesRegex(ValueError, name):
                        validate(inspection, self.revision, self.lock)

    def test_rejects_inherited_ubi_revision(self):
        inspection = self.inspection()
        inspection[0]["Config"]["Labels"][REVISION] = "9d7bd388a99de116058bd54b77737e2863cb3d45"
        with self.assertRaisesRegex(ValueError, REVISION):
            validate(inspection, self.revision, self.lock)

    def test_rejects_absent_labels(self):
        for config in ({}, {"Labels": None}, {"Labels": {}}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate([{"Config": config}], self.revision, self.lock)

    def test_hashes_exact_bytes_including_whitespace(self):
        with self.assertRaisesRegex(ValueError, LOCK):
            validate(self.inspection(), self.revision, self.lock.rstrip())

    def test_rejects_a_different_selected_lock(self):
        with self.assertRaisesRegex(ValueError, LOCK):
            validate(self.inspection(), self.revision, b'{"baseline": true}\n')

    def test_rejects_invalid_expected_revision(self):
        for revision in ("", "unknown", self.revision[:7]):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                validate(self.inspection(), revision, self.lock)

    def test_rejects_missing_or_multiple_images(self):
        for inspection in ([], {}, self.inspection() * 2):
            with self.subTest(inspection=inspection), self.assertRaises(ValueError):
                validate(inspection, self.revision, self.lock)


if __name__ == "__main__":
    unittest.main()
