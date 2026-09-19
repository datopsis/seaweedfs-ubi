"""Generate a conservative product-requirement trace view.

Only an immediately preceding ``# Requirements: ID ...`` comment on a Python
``test_*`` method or shell ``main()`` is treated as a test link. Shell links
identify a suite, not an individual assertion. Links say nothing about results,
architecture, topology, or release-candidate evidence.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ID = re.compile(r"L([123])-[A-Z]{3}-\d{3}")
HEADING = re.compile(r"^### (L[123]-[A-Z]{3}-\d{3})\s*$", re.MULTILINE)
FIELD = re.compile(r"^\*\*(Parent|Statement|Verification)\.\*\*\s*(.*)$", re.MULTILINE)
METHODS = {"Test", "Analysis", "Inspection", "Demonstration"}


@dataclass(frozen=True)
class Requirement:
    identifier: str
    parent: str | None
    statement: str
    methods: tuple[str, ...]


def parse_document(path: Path, level: int) -> dict[str, Requirement]:
    source = path.read_text(encoding="utf-8")
    headings = list(HEADING.finditer(source))
    if not headings:
        raise ValueError(f"{path.name}: no requirement headings")
    found: dict[str, Requirement] = {}
    for index, heading in enumerate(headings):
        identifier = heading.group(1)
        if int(ID.fullmatch(identifier).group(1)) != level:
            raise ValueError(f"{path.name}: wrong level for {identifier}")
        if identifier in found:
            raise ValueError(f"{path.name}: duplicate {identifier}")
        end = headings[index + 1].start() if index + 1 < len(headings) else len(source)
        body = source[heading.end() : end]
        field_pairs = FIELD.findall(body)
        fields = dict(field_pairs)
        if len(field_pairs) != len(fields):
            raise ValueError(f"{identifier}: duplicate metadata field")
        if not fields.get("Statement") or "SHALL" not in body:
            raise ValueError(f"{identifier}: missing SHALL statement")
        method_list = tuple(part.strip().rstrip(".") for part in fields.get("Verification", "").split(","))
        if not method_list or any(method not in METHODS for method in method_list):
            raise ValueError(f"{identifier}: invalid verification methods")
        parent = fields.get("Parent")
        if level == 1 and parent:
            raise ValueError(f"{identifier}: L1 must not have a parent")
        if level > 1 and (not parent or not ID.fullmatch(parent)):
            raise ValueError(f"{identifier}: missing or malformed parent")
        found[identifier] = Requirement(identifier, parent, fields["Statement"], method_list)
    return found


def load_requirements(root: Path) -> dict[str, Requirement]:
    found: dict[str, Requirement] = {}
    for level in (1, 2, 3):
        part = parse_document(root / "docs" / f"L{level}-REQ.md", level)
        found.update(part)
    for requirement in found.values():
        if requirement.parent:
            parent = found.get(requirement.parent)
            if parent is None:
                raise ValueError(f"{requirement.identifier}: unknown parent {requirement.parent}")
            if int(requirement.parent[1]) != int(requirement.identifier[1]) - 1:
                raise ValueError(f"{requirement.identifier}: parent is not the preceding level")
            if requirement.parent[3:6] != requirement.identifier[3:6]:
                raise ValueError(f"{requirement.identifier}: parent category differs")
    return found


def collect_test_links(root: Path, requirements: dict[str, Requirement]) -> dict[str, list[str]]:
    links: dict[str, list[str]] = defaultdict(list)

    def add_marker(path: Path, line: int, marker: str, target: str) -> None:
        identifiers = marker.removeprefix("# Requirements:").split()
        if not identifiers:
            raise ValueError(f"{path.name}:{line}: empty marker")
        for identifier in identifiers:
            if not ID.fullmatch(identifier):
                raise ValueError(f"{path.name}:{line}: malformed marker {identifier}")
            if identifier not in requirements:
                raise ValueError(f"{path.name}:{line}: unknown marker {identifier}")
            if "Test" not in requirements[identifier].methods:
                raise ValueError(f"{path.name}:{line}: {identifier} does not declare Test")
            links[identifier].append(f"tests/{path.name}:{line} ({target})")

    for path in sorted((root / "tests").glob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        functions = {}
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {ast.unparse(base) for base in node.bases}
            if not bases.intersection({"unittest.TestCase", "TestCase"}):
                continue
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name.startswith("test_"):
                    functions[method.lineno] = method
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT or not token.string.startswith("# Requirements:"):
                continue
            line, column = token.start
            function = functions.get(line + 1)
            if function is None or function.col_offset != column:
                raise ValueError(f"{path.name}:{line}: marker must immediately precede a discovered unittest test method")
            add_marker(path, line, token.string, function.name)
    for path in sorted((root / "tests").glob("*.sh")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not line.startswith("# Requirements:"):
                continue
            if index + 1 >= len(lines) or lines[index + 1] != "main() {":
                raise ValueError(f"{path.name}:{index + 1}: shell marker must immediately precede main()")
            add_marker(path, index + 1, line, "main suite")
    return links


def render(root: Path) -> str:
    requirements = load_requirements(root)
    links = collect_test_links(root, requirements)
    children: dict[str, list[str]] = defaultdict(list)
    for item in requirements.values():
        if item.parent:
            children[item.parent].append(item.identifier)
    leaves = [item for item in requirements.values() if not children[item.identifier]]
    linked = [item for item in leaves if links[item.identifier]]
    missing = [item for item in leaves if "Test" in item.methods and not links[item.identifier]]
    manual = [item for item in leaves if "Test" not in item.methods]
    lines = [
        "# SeaweedFS UBI requirement trace matrix",
        "",
        "**Generated; do not edit.** Run `python scripts/build-trace-matrix.py` to regenerate.",
        "CI checks for drift and broken links. It does not require all gaps to be closed yet.",
        "",
        "Python method and selected shell-suite markers are indexed. Shell markers",
        "identify entire suites, not particular assertions. Other shell suites and",
        "manual assessment records are not indexed yet; a missing link",
        "may mean existing evidence has not been traced, not that no test exists.",
        "",
        "A test link means only that a named test is intended to verify the stated",
        "behavior. It is not a passing test result, a release-candidate assessment,",
        "or evidence for another architecture, role, topology, or platform.",
        "`Decomposed` means a child exists, not that the parent is satisfied.",
        "Manual methods need separately reviewed evidence in the qualification ledger.",
        "",
        "## Initial trace state",
        "",
        "| Measure | Count |",
        "| --- | ---: |",
        f"| L1 / L2 / L3 requirements | {sum(key.startswith('L1') for key in requirements)} / {sum(key.startswith('L2') for key in requirements)} / {sum(key.startswith('L3') for key in requirements)} |",
        f"| Leaf requirements linked to a test | {len(linked)} |",
        f"| Testable leaves missing a test link | {len(missing)} |",
        f"| Leaves awaiting manual evidence | {len(manual)} |",
        "",
    ]
    for level in (1, 2, 3):
        lines.extend([f"## L{level} requirements", "", "| ID | Parent | Methods | Test links | Trace state |", "| --- | --- | --- | --- | --- |"])
        for identifier, item in sorted(requirements.items()):
            if not identifier.startswith(f"L{level}-"):
                continue
            parent = f"`{item.parent}`" if item.parent else "—"
            methods = ", ".join(item.methods)
            test_links = "<br>".join(f"`{link}`" for link in sorted(links[identifier])) or "—"
            state = "decomposed" if children[identifier] else ("test linked" if links[identifier] else ("missing test link" if "Test" in item.methods else "manual evidence pending"))
            lines.append(f"| `{identifier}` | {parent} | {methods} | {test_links} | {state} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on structural error or matrix drift")
    args = parser.parse_args()
    try:
        content = render(ROOT)
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    path = ROOT / "docs" / "TRACE-MATRIX.md"
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            print("docs/TRACE-MATRIX.md is out of date", file=sys.stderr)
            return 1
        print("docs/TRACE-MATRIX.md is up to date")
        return 0
    path.write_text(content, encoding="utf-8", newline="\n")
    print("wrote docs/TRACE-MATRIX.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
