"""Fail-closed structural tests for the generated requirement trace view."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-trace-matrix.py"
SPEC = importlib.util.spec_from_file_location("build_trace_matrix", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
trace = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = trace
SPEC.loader.exec_module(trace)


class TraceMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent)
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        (self.root / "docs").mkdir()
        (self.root / "tests").mkdir()
        self.write("docs/L1-REQ.md", """### L1-SUP-001

**Statement.** Inputs SHALL be reviewed.

**Verification.** Test.
""")
        self.write("docs/L2-REQ.md", """### L2-SUP-001

**Parent.** L1-SUP-001

**Statement.** Inputs SHALL be pinned.

**Verification.** Test.
""")
        self.write("docs/L3-REQ.md", """### L3-SUP-001

**Parent.** L2-SUP-001

**Statement.** Tampering SHALL fail.

**Verification.** Test.
""")

    def write(self, relative: str, content: str) -> None:
        (self.root / relative).write_text(content, encoding="utf-8")

    def test_unlinked_test_is_visible_not_reported_as_covered(self) -> None:
        matrix = trace.render(self.root)
        self.assertIn("| Testable leaves missing a test link | 1 |", matrix)
        self.assertIn("| `L3-SUP-001` | `L2-SUP-001` | Test | — | missing test link |", matrix)
        self.assertIn("| `L1-SUP-001` | — | Test | — | decomposed |", matrix)

    def test_exact_test_comment_is_linked_without_claiming_a_pass(self) -> None:
        self.write("tests/test_sample.py", """import unittest

class Sample(unittest.TestCase):
    # Requirements: L3-SUP-001
    def test_rejects_tampering(self):
        pass
""")
        matrix = trace.render(self.root)
        self.assertIn("| Leaf requirements linked to a test | 1 |", matrix)
        self.assertIn("test linked", matrix)
        self.assertIn("It is not a passing test result", matrix)

    def test_duplicate_identifier_is_refused(self) -> None:
        path = self.root / "docs/L1-REQ.md"
        path.write_text(path.read_text(encoding="utf-8") * 2, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate L1-SUP-001"):
            trace.render(self.root)

    def test_unknown_parent_is_refused(self) -> None:
        path = self.root / "docs/L2-REQ.md"
        path.write_text(path.read_text(encoding="utf-8").replace("L1-SUP-001", "L1-SUP-999"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown parent L1-SUP-999"):
            trace.render(self.root)

    def test_unknown_and_dangling_test_markers_are_refused(self) -> None:
        self.write("tests/test_sample.py", """import unittest

class Sample(unittest.TestCase):
    # Requirements: L3-SUP-999
    def test_sample(self):
        pass
""")
        with self.assertRaisesRegex(ValueError, "unknown marker L3-SUP-999"):
            trace.render(self.root)
        self.write("tests/test_sample.py", "# Requirements: L3-SUP-001\n\n")
        with self.assertRaisesRegex(ValueError, "must immediately precede"):
            trace.render(self.root)

    def test_marker_on_function_not_discovered_by_unittest_is_refused(self) -> None:
        self.write("tests/test_sample.py", """# Requirements: L3-SUP-001
def test_not_a_unittest_method():
    pass
""")
        with self.assertRaisesRegex(ValueError, "must immediately precede"):
            trace.render(self.root)

    def test_shell_suite_marker_is_linked_only_as_a_suite(self) -> None:
        self.write("tests/s3.sh", "# Requirements: L3-SUP-001\nmain() {\n    :\n}\n")
        matrix = trace.render(self.root)
        self.assertIn("tests/s3.sh:1 (main suite)", matrix)
        self.assertIn("not particular assertions", matrix)

    def test_shell_marker_must_precede_main_and_name_a_test_requirement(self) -> None:
        self.write("tests/s3.sh", "# Requirements: L3-SUP-001\nhelper() {\n    :\n}\n")
        with self.assertRaisesRegex(ValueError, "shell marker must immediately precede main"):
            trace.render(self.root)
        self.write("tests/s3.sh", "# Requirements: L3-SUP-999\nmain() {\n    :\n}\n")
        with self.assertRaisesRegex(ValueError, "unknown marker L3-SUP-999"):
            trace.render(self.root)

    def test_actual_matrix_matches_checked_in_sources(self) -> None:
        self.assertEqual(
            (ROOT / "docs/TRACE-MATRIX.md").read_text(encoding="utf-8"),
            trace.render(ROOT),
        )


if __name__ == "__main__":
    unittest.main()
