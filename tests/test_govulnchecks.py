"""Regression tests for govulncheck evidence validation."""

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent / "lib"))

from govulnchecks import validate  # noqa: E402


CONFIG = {
    "protocol_version": "v1.0.0",
    "scanner_name": "govulncheck",
    "scanner_version": "v1.8.0",
    "scan_mode": "binary",
    "scan_level": "symbol",
    "db": "https://vuln.go.dev",
    "db_last_modified": "2026-09-18T00:00:00Z",
}
SBOM = {"modules": [{"path": "golang.org/x/crypto", "version": "v0.55.0"}], "roots": ["github.com/seaweedfs/seaweedfs/weed"]}


def stream(*messages):
    return "\n".join(json.dumps(message) for message in messages)


class GovulncheckEvidenceTests(unittest.TestCase):
    def test_accepts_stream_with_findings(self):
        report = stream({"config": CONFIG}, {"SBOM": SBOM}, {"finding": {"osv": "GO-2026-6354"}})
        self.assertEqual(validate(report, "v1.8.0"), (1, 1))

    def test_accepts_clean_scan_without_turning_inventory_into_gate(self):
        report = stream({"config": CONFIG}, {"SBOM": SBOM})
        self.assertEqual(validate(report, "v1.8.0"), (1, 0))

    def test_rejects_module_only_scan(self):
        config = dict(CONFIG, scan_level="module")
        with self.assertRaisesRegex(ValueError, "binary symbol-level"):
            validate(stream({"config": config}, {"SBOM": SBOM}), "v1.8.0")

    def test_rejects_missing_database_timestamp(self):
        config = dict(CONFIG)
        del config["db_last_modified"]
        with self.assertRaisesRegex(ValueError, "timestamp"):
            validate(stream({"config": config}, {"SBOM": SBOM}), "v1.8.0")

    def test_rejects_missing_binary_inventory(self):
        with self.assertRaisesRegex(ValueError, "SBOM"):
            validate(stream({"config": CONFIG}), "v1.8.0")

    def test_rejects_wrong_tool_version(self):
        with self.assertRaisesRegex(ValueError, "version"):
            validate(stream({"config": CONFIG}, {"SBOM": SBOM}), "v1.9.0")

    def test_rejects_truncated_json(self):
        with self.assertRaises(json.JSONDecodeError):
            validate(stream({"config": CONFIG}, {"SBOM": SBOM}) + "{", "v1.8.0")


if __name__ == "__main__":
    unittest.main()
