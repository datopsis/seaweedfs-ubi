"""Development evidence must remain scoped to the exact native CI run."""

from __future__ import annotations

import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "lib"))
from native_evidence import SUITES, make_record, reconcile  # noqa: E402

COMMIT = "a" * 40
IMAGE = "sha256:" + "b" * 64


class NativeEvidenceTests(unittest.TestCase):
    def test_recorded_suites_are_run_before_evidence_is_written(self):
        workflow = (pathlib.Path(__file__).resolve().parents[1] /
                    ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        record_step = workflow.index("- name: Record scoped native development evidence")
        for suite in SUITES:
            with self.subTest(suite=suite):
                command = f"run: bash tests/{suite}.sh"
                self.assertEqual(workflow.count(command), 1)
                self.assertLess(workflow.index(command), record_step)

    def records(self):
        return [make_record(arch, COMMIT, "12", "2", IMAGE)
                for arch in ("amd64", "arm64")]

    def test_reconciles_two_native_development_images(self):
        result = reconcile(self.records(), COMMIT, "12", "2")
        self.assertEqual(set(result["architectures"]), {"amd64", "arm64"})
        self.assertFalse(result["release_eligible"])
        self.assertEqual(result["standard_conformance"], "not assessed")

    def test_normalizes_podman_bare_image_id(self):
        record = make_record("amd64", COMMIT, "12", "2", "b" * 64)
        self.assertEqual(record["local_image_id"], IMAGE)

    def test_rejects_duplicate_architecture(self):
        records = self.records()
        records[1]["architecture"] = "amd64"
        with self.assertRaisesRegex(ValueError, "architecture"):
            reconcile(records, COMMIT, "12", "2")

    def test_rejects_stale_commit_or_run(self):
        for field, value in (("source_commit", "c" * 40),
                             ("github_run_id", 11), ("github_run_attempt", 1)):
            records = self.records()
            records[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                reconcile(records, COMMIT, "12", "2")

    def test_rejects_missing_suite_and_scope(self):
        for field, value in (("passed_suites", []), ("limitations", []),
                             ("evidence_level", "release-candidate")):
            records = self.records()
            records[0][field] = copy.deepcopy(value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                reconcile(records, COMMIT, "12", "2")

    def test_rejects_bad_identity(self):
        with self.assertRaisesRegex(ValueError, "Git SHA"):
            make_record("amd64", "short", "12", "2", IMAGE)
        with self.assertRaisesRegex(ValueError, "image ID"):
            make_record("amd64", COMMIT, "12", "2", "tag:mutable")


if __name__ == "__main__":
    unittest.main()
