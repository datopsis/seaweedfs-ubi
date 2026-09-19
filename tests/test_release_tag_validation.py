from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "scripts" / "lib"))

from validate_release_tag import ReleaseTagError, validate_release_tag  # noqa: E402


class ReleaseTagValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lock = pathlib.Path("seaweedfs.lock.json")
        self.containerfile = pathlib.Path("Containerfile")
        self.write_lock("4.46")
        self.write_containerfile(9, 9)
        self.today = dt.date(2026, 9, 18)

    def write_lock(self, version: str) -> None:
        self.lock_text = json.dumps({"upstream": {"releaseTag": version}})

    def write_containerfile(
        self, minimal_major: int, micro_major: int, *, pinned: bool = True
    ) -> None:
        suffix = "@sha256:" + "a" * 64 if pinned else ":latest"
        self.containerfile_text = (
            f"ARG UBI_MINIMAL=registry.example/ubi{minimal_major}/ubi-minimal{suffix}\n"
            f"ARG UBI_MICRO=registry.example/ubi{micro_major}/ubi-micro{suffix}\n"
        )

    def validate(self, tag: str, existing_tags: list[str] | None = None) -> dict[str, object]:
        def read_text(path: pathlib.Path, **_: object) -> str:
            if path == self.lock:
                return self.lock_text
            if path == self.containerfile:
                return self.containerfile_text
            raise AssertionError(f"unexpected test path: {path}")

        with mock.patch.object(pathlib.Path, "read_text", read_text):
            return validate_release_tag(
                tag,
                self.lock,
                self.containerfile,
                self.today,
                existing_tags or [],
            )

    def test_accepts_first_release_for_locked_inputs(self) -> None:
        result = self.validate("v4.46-ubi9-r20260918.1")
        self.assertEqual(result["seaweedfsVersion"], "4.46")
        self.assertEqual(result["dailySequence"], 1)

    def test_accepts_next_sequence_across_other_product_versions(self) -> None:
        result = self.validate(
            "v4.46-ubi9-r20260918.3",
            [
                "v4.45-ubi9-r20260918.1",
                "v4.47-ubi10-r20260918.2",
                "unrelated-source-tag",
            ],
        )
        self.assertEqual(result["dailySequence"], 3)

    # Requirements: L3-REL-001
    def test_refuses_malformed_tags(self) -> None:
        tags = (
            "4.46-ubi9-r20260918.1",
            "v4-ubi9-r20260918.1",
            "v4.46-ubi09-r20260918.1",
            "v4.46-ubi9-r20260918.0",
            "v4.46-ubi9-r20260918.01",
            "v4.46-ubi9-r20260918.1-extra",
        )
        for tag in tags:
            with self.subTest(tag=tag), self.assertRaisesRegex(
                ReleaseTagError, "does not match"
            ):
                self.validate(tag)

    def test_refuses_impossible_calendar_date(self) -> None:
        with self.assertRaisesRegex(ReleaseTagError, "not a real ISO calendar date"):
            self.validate("v4.46-ubi9-r20260230.1")

    # Requirements: L3-REL-001
    def test_refuses_backdated_or_future_date(self) -> None:
        for date in ("20260917", "20260919"):
            with self.subTest(date=date), self.assertRaisesRegex(
                ReleaseTagError, "backdated or future-dated"
            ):
                self.validate(f"v4.46-ubi9-r{date}.1")

    def test_refuses_malformed_or_incomplete_artifact_lock(self) -> None:
        for lock_text, message in (
            ("{", "cannot read artifact lock"),
            (json.dumps({"upstream": {}}), "no non-empty upstream.releaseTag"),
        ):
            with self.subTest(lock_text=lock_text), self.assertRaisesRegex(
                ReleaseTagError, message
            ):
                self.lock_text = lock_text
                self.validate("v4.46-ubi9-r20260918.1")

    # Requirements: L3-REL-001
    def test_refuses_version_not_in_artifact_lock(self) -> None:
        with self.assertRaisesRegex(ReleaseTagError, "artifact lock version"):
            self.validate("v4.47-ubi9-r20260918.1")

    def test_refuses_ubi_major_not_in_containerfile(self) -> None:
        with self.assertRaisesRegex(ReleaseTagError, "Containerfile base major"):
            self.validate("v4.46-ubi10-r20260918.1")

    # Requirements: L3-REL-001
    def test_refuses_disagreeing_base_majors(self) -> None:
        self.write_containerfile(9, 10)
        with self.assertRaisesRegex(ReleaseTagError, "base UBI majors disagree"):
            self.validate("v4.46-ubi9-r20260918.1")

    def test_refuses_missing_or_duplicate_base_arguments(self) -> None:
        minimal = "ARG UBI_MINIMAL=registry.example/ubi9/ubi-minimal@sha256:" + "a" * 64
        for containerfile_text, message in (
            (minimal + "\n", "no UBI_MICRO"),
            (minimal + "\n" + minimal + "\n", "defines UBI_MINIMAL more than once"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(
                ReleaseTagError, message
            ):
                self.containerfile_text = containerfile_text
                self.validate("v4.46-ubi9-r20260918.1")

    # Requirements: L3-REL-001
    def test_refuses_unpinned_base(self) -> None:
        self.write_containerfile(9, 9, pinned=False)
        with self.assertRaisesRegex(ReleaseTagError, "not a digest-pinned UBI image"):
            self.validate("v4.46-ubi9-r20260918.1")

    # Requirements: L3-REL-001
    def test_refuses_reused_immutable_tag(self) -> None:
        tag = "v4.46-ubi9-r20260918.1"
        with self.assertRaisesRegex(ReleaseTagError, "already exists"):
            self.validate(tag, [tag])

    # Requirements: L3-REL-001
    def test_refuses_skipped_or_filled_sequence(self) -> None:
        existing = [
            "v4.45-ubi9-r20260918.1",
            "v4.45-ubi9-r20260918.3",
        ]
        for sequence in (2, 5):
            with self.subTest(sequence=sequence), self.assertRaisesRegex(
                ReleaseTagError, "next sequence 4"
            ):
                self.validate(f"v4.46-ubi9-r20260918.{sequence}", existing)

    def test_cli_emits_machine_readable_admission(self) -> None:
        root = pathlib.Path(__file__).parents[1]
        validator = root / "scripts" / "lib" / "validate_release_tag.py"
        result = subprocess.run(
            [
                sys.executable,
                str(validator),
                "v4.46-ubi9-r20260918.1",
                "--lock",
                str(root / "artifacts" / "seaweedfs.lock.json"),
                "--containerfile",
                str(root / "Containerfile"),
                "--expected-date",
                "2026-09-18",
                "--existing-tags-file",
                str(root / "tests" / "fixtures" / "repository-tags.txt"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["tag"], "v4.46-ubi9-r20260918.1")


if __name__ == "__main__":
    unittest.main()
