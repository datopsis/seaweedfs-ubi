from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent / "lib"))

from trivychecks import TrivyValidationError, validate_trivy  # noqa: E402


class TrivyValidationTests(unittest.TestCase):
    def document(self) -> dict[str, object]:
        return {
            "SchemaVersion": 2,
            "ArtifactType": "container_image",
            "Metadata": {
                "ImageID": "sha256:abc123",
                "OS": {"Family": "redhat", "Name": "9.8"},
            },
            "Results": [
                {"Target": "Red Hat", "Class": "os-pkgs", "Vulnerabilities": []},
                {
                    "Target": "usr/local/bin/weed",
                    "Class": "lang-pkgs",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "GO-2026-1234",
                            "Severity": "HIGH",
                            "FixedVersion": "1.2.3",
                        },
                        {
                            "VulnerabilityID": "GO-2026-5678",
                            "Severity": "HIGH",
                        },
                    ],
                },
            ],
        }

    # Requirements: L3-EVD-002
    def test_accepts_image_os_and_language_coverage(self) -> None:
        self.assertEqual(validate_trivy(self.document()), (2, 2, 1))

    def test_refuses_wrong_schema(self) -> None:
        document = self.document()
        document["SchemaVersion"] = 1
        with self.assertRaisesRegex(TrivyValidationError, "schema 2"):
            validate_trivy(document)

    def test_refuses_non_image_scan(self) -> None:
        document = self.document()
        document["ArtifactType"] = "filesystem"
        with self.assertRaisesRegex(TrivyValidationError, "container image"):
            validate_trivy(document)

    def test_refuses_missing_digest(self) -> None:
        document = self.document()
        document["Metadata"]["ImageID"] = ""  # type: ignore[index]
        with self.assertRaisesRegex(TrivyValidationError, "image digest"):
            validate_trivy(document)

    # Requirements: L3-EVD-002
    def test_refuses_missing_os(self) -> None:
        document = self.document()
        document["Metadata"]["OS"] = {}  # type: ignore[index]
        with self.assertRaisesRegex(TrivyValidationError, "OS identification"):
            validate_trivy(document)

    # Requirements: L3-EVD-002
    def test_refuses_missing_language_coverage(self) -> None:
        document = self.document()
        document["Results"] = [document["Results"][0]]  # type: ignore[index]
        with self.assertRaisesRegex(TrivyValidationError, "language package"):
            validate_trivy(document)

    def test_refuses_malformed_findings(self) -> None:
        document = self.document()
        document["Results"][1]["Vulnerabilities"] = "missing"  # type: ignore[index]
        with self.assertRaisesRegex(TrivyValidationError, "must be a list"):
            validate_trivy(document)


if __name__ == "__main__":
    unittest.main()
