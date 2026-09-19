"""Negative and positive cases for the release ref and signing context."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
from admit_release_ref import admit  # noqa: E402
from release_signing_context import SigningContextError, identity_for  # noqa: E402
from validate_release_tag import ReleaseTagError  # noqa: E402

TAG = "v4.46-ubi9-r20260919.1"
IMAGE = "ghcr.io/datopsis/seaweedfs-ubi@sha256:" + "a" * 64


class ReleaseAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent)
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        (self.root / "artifacts").mkdir()
        (self.root / "artifacts/seaweedfs.lock.json").write_text(
            '{"upstream":{"releaseTag":"4.46"}}', encoding="utf-8"
        )
        digest = "a" * 64
        (self.root / "Containerfile").write_text(
            f"ARG UBI_MINIMAL=registry.access.redhat.com/ubi9/ubi-minimal@sha256:{digest}\n"
            f"ARG UBI_MICRO=registry.access.redhat.com/ubi9/ubi-micro@sha256:{digest}\n",
            encoding="utf-8",
        )
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Release Test")
        self.git("config", "user.email", "release-test@example.invalid")
        self.git("add", ".")
        self.git("commit", "-m", "fixture")
        self.git("tag", "-a", TAG, "-m", "fixture release")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def test_annotated_exact_main_tag_is_admitted(self) -> None:
        result = admit(self.root, TAG, "2026-09-19")
        self.assertEqual(result["commit"], self.git("rev-parse", "HEAD"))
        self.assertEqual(result["dailySequence"], 1)

    def test_lightweight_tag_is_refused(self) -> None:
        self.git("tag", "-d", TAG)
        self.git("tag", TAG)
        with self.assertRaisesRegex(ReleaseTagError, "annotated"):
            admit(self.root, TAG, "2026-09-19")

    def test_tag_not_at_current_main_tip_is_refused(self) -> None:
        (self.root / "new-file").write_text("new commit\n", encoding="utf-8")
        self.git("add", "new-file")
        self.git("commit", "-m", "later main commit")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        with self.assertRaisesRegex(ReleaseTagError, "tagged commit"):
            admit(self.root, TAG, "2026-09-19")

    def test_wrong_date_or_malformed_tag_is_refused(self) -> None:
        with self.assertRaisesRegex(ReleaseTagError, "workflow UTC date"):
            admit(self.root, TAG, "2026-09-18")
        with self.assertRaisesRegex(ReleaseTagError, "version contract"):
            admit(self.root, "not-a-release", "2026-09-19")


class SigningContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "datopsis/seaweedfs-ubi",
            "GITHUB_REF_NAME": TAG,
            "GITHUB_REF": f"refs/tags/{TAG}",
            "GITHUB_WORKFLOW_REF": (
                "datopsis/seaweedfs-ubi/.github/workflows/release.yml@"
                f"refs/tags/{TAG}"
            ),
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://example.invalid/oidc",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "test-token",
        }

    def test_exact_digest_and_workflow_identity(self) -> None:
        self.assertEqual(
            identity_for(IMAGE, self.environment),
            "https://github.com/datopsis/seaweedfs-ubi/.github/workflows/release.yml@"
            f"refs/tags/{TAG}",
        )

    def test_mutable_tag_and_wrong_workflow_are_refused(self) -> None:
        with self.assertRaisesRegex(SigningContextError, "SHA-256 digest"):
            identity_for("ghcr.io/datopsis/seaweedfs-ubi:latest", self.environment)
        self.environment["GITHUB_WORKFLOW_REF"] = "datopsis/seaweedfs-ubi/.github/workflows/ci.yml@refs/heads/main"
        with self.assertRaisesRegex(SigningContextError, "GITHUB_WORKFLOW_REF"):
            identity_for(IMAGE, self.environment)

    def test_missing_oidc_token_and_wrong_repository_are_refused(self) -> None:
        self.environment.pop("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
        with self.assertRaisesRegex(SigningContextError, "OIDC"):
            identity_for(IMAGE, self.environment)
        self.environment["ACTIONS_ID_TOKEN_REQUEST_TOKEN"] = "test-token"
        self.environment["GITHUB_REPOSITORY"] = "attacker/fork"
        with self.assertRaisesRegex(SigningContextError, "GITHUB_REPOSITORY"):
            identity_for(IMAGE, self.environment)


if __name__ == "__main__":
    unittest.main()
