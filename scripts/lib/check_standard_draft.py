"""Compare provisional SeaweedFS worksheets with a local standard checkout.

This is a drift check for research in progress. It does not approve or pin the
standard, assess criteria, or replace the shared conformance workflow.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_IDS = (
    "disa-gpos-srg",
    "disa-container-platform-srg",
    "disa-application-server-srg",
    "disa-web-server-srg",
)


def check(standard: Path, repository: Path = ROOT) -> list[str]:
    baseline = json.loads((standard / "artifacts" / "control-baseline.json").read_text(encoding="utf-8"))
    register = json.loads((standard / "artifacts" / "sources.json").read_text(encoding="utf-8"))
    criteria_doc = (repository / "docs" / "HARDENING-CRITERIA.md").read_text(encoding="utf-8")
    requirements_doc = (repository / "requirements.md").read_text(encoding="utf-8")
    controls_doc = (repository / "docs" / "CYBER-CONTROLS.md").read_text(encoding="utf-8")
    normalized_controls = re.sub(r"\s+", " ", controls_doc)
    problems: list[str] = []

    required = {key for key, value in baseline["criteria"].items() if value["level"] == "required"}
    rows = re.findall(r"^\| (IMG-\d{2}) ", criteria_doc, re.M)
    if len(rows) != len(set(rows)):
        problems.append("IMG inventory contains duplicate criterion rows")
    if set(rows) != required:
        problems.append("IMG inventory differs from the current required criteria: "
                        f"missing {sorted(required - set(rows))}, extra {sorted(set(rows) - required)}")

    requirements = re.findall(
        r"^### (SWD-\d{3})\s*\n(.*?)(?=^### SWD-\d{3}\s*$|\Z)",
        requirements_doc, re.M | re.S,
    )
    ids = [identifier for identifier, _ in requirements]
    mapped = [re.findall(r"^- Criterion: (IMG-\d{2})$", body, re.M)
              for _, body in requirements]
    if len(ids) != len(set(ids)) or any(len(criteria) != 1 for criteria in mapped):
        problems.append("image requirement IDs must be unique with exactly one IMG criterion each")
    mapped_ids = [criteria[0] for criteria in mapped if len(criteria) == 1]
    if len(mapped_ids) != len(set(mapped_ids)) or set(mapped_ids) != required:
        problems.append("image requirements differ from the current required criteria: "
                        f"missing {sorted(required - set(mapped_ids))}, "
                        f"extra {sorted(set(mapped_ids) - required)}")

    counts = Counter(control["origination"] for control in baseline["controls"])
    if f"contains {len(baseline['controls'])} control entries" not in normalized_controls:
        problems.append("control total in provisional worksheet is stale")
    for number, label in (
        (counts["image-owned"], "`image-owned`"),
        (counts["deployment-configured"], "`deployment-configured`"),
        (counts["host-inherited"], "`host-inherited`"),
        (counts["organization-inherited"], "`organization-inherited`"),
        (counts["not-applicable"], "`not-applicable`"),
        (counts["research-required"], "`research-required`"),
    ):
        if f"{number} {label}" not in normalized_controls:
            problems.append(f"control count for {label} is stale")

    sources = {source["id"]: source for source in register["sources"]}
    for identifier in SOURCE_IDS:
        if identifier not in sources:
            problems.append(f"source register no longer contains {identifier}")
        elif sources[identifier]["sha256"] not in controls_doc:
            problems.append(f"source digest for {identifier} changed; re-review applicability")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("standard", type=Path, help="path to a local container-hardening checkout")
    args = parser.parse_args()
    try:
        problems = check(args.standard)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    for problem in problems:
        print("draft drift: " + problem)
    if problems:
        return 1
    print("provisional worksheets match this local standard checkout; no approval or conformance implied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
