from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent / "lib"))

from spdxchecks import SbomValidationError, validate_spdx  # noqa: E402


def package(locator: str) -> dict[str, object]:
    return {
        "name": locator,
        "externalRefs": [
            {"referenceType": "purl", "referenceLocator": locator}
        ],
    }


class SpdxValidationTests(unittest.TestCase):
    def document(self) -> dict[str, object]:
        return {
            "spdxVersion": "SPDX-2.3",
            "packages": [
                package("pkg:golang/github.com/seaweedfs/seaweedfs@v4.46"),
                package("pkg:golang/golang.org/x/net@v0.0.0"),
            ],
        }

    # Requirements: L3-EVD-001
    def test_accepts_seaweedfs_and_go_inventory(self) -> None:
        self.assertEqual(validate_spdx(self.document()), (2, 2))

    def test_refuses_non_spdx_document(self) -> None:
        with self.assertRaisesRegex(SbomValidationError, "SPDX 2.3"):
            validate_spdx({"packages": []})

    def test_refuses_empty_package_list(self) -> None:
        with self.assertRaisesRegex(SbomValidationError, "no packages"):
            validate_spdx({"spdxVersion": "SPDX-2.3", "packages": []})

    # Requirements: L3-EVD-001
    def test_refuses_missing_go_inventory(self) -> None:
        document = self.document()
        document["packages"] = [package("pkg:rpm/redhat/ubi9@9.0")]
        with self.assertRaisesRegex(SbomValidationError, "no Go module"):
            validate_spdx(document)

    # Requirements: L3-EVD-001
    def test_refuses_missing_seaweedfs(self) -> None:
        document = self.document()
        document["packages"] = [package("pkg:golang/golang.org/x/net@v0.0.0")]
        with self.assertRaisesRegex(SbomValidationError, "SeaweedFS"):
            validate_spdx(document)

    # Requirements: L3-EVD-001
    def test_refuses_main_module_without_dependencies(self) -> None:
        document = self.document()
        document["packages"] = [
            package("pkg:golang/github.com/seaweedfs/seaweedfs@v4.46")
        ]
        with self.assertRaisesRegex(SbomValidationError, "no SeaweedFS dependencies"):
            validate_spdx(document)

    def test_refuses_malformed_reference(self) -> None:
        document = self.document()
        document["packages"] = [{"externalRefs": "not a list"}]
        with self.assertRaisesRegex(SbomValidationError, "externalRefs"):
            validate_spdx(document)


if __name__ == "__main__":
    unittest.main()
