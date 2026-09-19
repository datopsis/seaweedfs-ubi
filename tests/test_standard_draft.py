"""The provisional standard drift check must notice changed source and scope."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
from check_standard_draft import check  # noqa: E402


class StandardDraftTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.standard = pathlib.Path(self.temporary.name) / "standard"
        artifacts = self.standard / "artifacts"
        artifacts.mkdir(parents=True)
        self.baseline = {
            "criteria": {f"IMG-{i:02d}": {"level": "required"} for i in range(1, 35)},
            "controls": [
                *[{"origination": "image-owned"}] * 20,
                *[{"origination": "deployment-configured"}] * 13,
                *[{"origination": "host-inherited"}] * 50,
                *[{"origination": "organization-inherited"}] * 228,
                *[{"origination": "not-applicable"}] * 11,
                *[{"origination": "research-required"}] * 57,
            ],
        }
        self.register = {"sources": [
            {"id": name, "sha256": digest} for name, digest in (
                ("disa-gpos-srg", "97026655bce18d91e12c9c0a9fd54288989f0b483d3b92ec615e2dc0544e6f24"),
                ("disa-container-platform-srg", "975a9e421e62e0ea52b1824e4a719aee87eed9070d5a3145fa9817f6498d99fe"),
                ("disa-application-server-srg", "ea33d7f18f950e86c9e0cc63835cf8802d319804ac143b2020b1fbac13ff2643"),
                ("disa-web-server-srg", "7345e31a61c162ee4ca0253e3f44b729c18bb45b3a17cb364e5d08422412b409"),
            )
        ]}
        self.write()

    def write(self):
        artifacts = self.standard / "artifacts"
        (artifacts / "control-baseline.json").write_text(json.dumps(self.baseline), encoding="utf-8")
        (artifacts / "sources.json").write_text(json.dumps(self.register), encoding="utf-8")

    def test_current_shape_matches_provisional_worksheets(self):
        self.assertEqual(check(self.standard), [])

    def test_changed_criterion_is_visible(self):
        self.baseline["criteria"]["IMG-35"] = {"level": "required"}
        self.write()
        self.assertIn("IMG inventory differs", " ".join(check(self.standard)))

    def test_changed_source_digest_requires_re_review(self):
        self.register["sources"][0]["sha256"] = "0" * 64
        self.write()
        self.assertIn("re-review applicability", " ".join(check(self.standard)))

    def test_changed_control_origination_count_is_visible(self):
        self.baseline["controls"][0]["origination"] = "research-required"
        self.write()
        self.assertIn("control count", " ".join(check(self.standard)))


if __name__ == "__main__":
    unittest.main()
