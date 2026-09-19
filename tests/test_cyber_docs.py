"""Keep the provisional threat worksheet tied to live product requirements."""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CyberDocumentationTests(unittest.TestCase):
    def test_image_requirements_cover_each_required_criterion_once(self):
        text = (ROOT / "docs" / "L2-REQ.md").read_text(encoding="utf-8")
        blocks = re.findall(
            r"^### (L2-[A-Z]{3}-\d{3})\s*\n(.*?)(?=^### L2-[A-Z]{3}-\d{3}\s*$|\Z)",
            text, re.M | re.S,
        )
        mapped = [re.findall(r"^\*\*Criterion\.\*\* (IMG-\d{2})$", body, re.M)
                  for _, body in blocks]
        self.assertTrue(all(len(criteria) <= 1 for criteria in mapped))
        identifiers = [criteria[0] for criteria in mapped if criteria]
        self.assertEqual(sorted(identifiers), [f"IMG-{number:02d}" for number in range(1, 35)])
        self.assertEqual(len(identifiers), len(set(identifiers)))
        mapped_l2 = {identifier for (identifier, _), criteria in zip(blocks, mapped) if criteria}
        l3 = (ROOT / "docs" / "L3-REQ.md").read_text(encoding="utf-8")
        l3_parents = set(re.findall(r"^\*\*Parent\.\*\* (L2-[A-Z]{3}-\d{3})$", l3, re.M))
        self.assertFalse(mapped_l2 - l3_parents,
                         f"IMG requirements without L3 decomposition: {mapped_l2 - l3_parents}")

    def test_all_required_criterion_rows_are_present_once(self):
        text = (ROOT / "docs" / "HARDENING-CRITERIA.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| (IMG-\d{2}) ", text, re.M)
        self.assertEqual(rows, [f"IMG-{number:02d}" for number in range(1, 35)])

    def test_criterion_requirement_areas_exist(self):
        text = (ROOT / "docs" / "HARDENING-CRITERIA.md").read_text(encoding="utf-8")
        requirements = (ROOT / "docs" / "L1-REQ.md").read_text(encoding="utf-8")
        existing = set(re.findall(r"^### (L1-[A-Z]+-\d{3})$", requirements, re.M))
        cited = set(re.findall(r"\bL1-[A-Z]+-\d{3}\b", text))
        self.assertTrue(cited)
        self.assertFalse(cited - existing, f"unknown L1 requirements: {cited - existing}")

    def test_threat_ids_are_unique_and_contiguous(self):
        text = (ROOT / "docs" / "THREAT-MODEL.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| (TM-\d{2}) \|", text, re.M)
        self.assertEqual(rows, [f"TM-{number:02d}" for number in range(1, 16)])

    def test_threat_requirements_exist(self):
        threat = (ROOT / "docs" / "THREAT-MODEL.md").read_text(encoding="utf-8")
        requirements = (ROOT / "docs" / "L1-REQ.md").read_text(encoding="utf-8")
        existing = set(re.findall(r"^### (L1-[A-Z]+-\d{3})$", requirements, re.M))
        cited = set(re.findall(r"\bL1-[A-Z]+-\d{3}\b", threat))
        self.assertTrue(cited)
        self.assertFalse(cited - existing, f"unknown L1 requirements: {cited - existing}")

    def test_direct_read_risk_is_not_overwritten_by_jwt_claim(self):
        for name in ("L1-REQ.md", "L2-REQ.md", "L3-REQ.md", "SUPPORT.md",
                     "ARCHITECTURE.md", "QUALIFICATION.md"):
            with self.subTest(document=name):
                text = (ROOT / "docs" / name).read_text(encoding="utf-8")
                self.assertNotIn("read and write JWTs", text)
                self.assertNotIn("read/write JWTs", text)


if __name__ == "__main__":
    unittest.main()
