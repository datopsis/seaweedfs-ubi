"""Require a usable Trivy image vulnerability inventory."""

from __future__ import annotations

import json
import pathlib
import sys


class TrivyValidationError(ValueError):
    """The generated image scan omits required evidence."""


def validate_trivy(document: object) -> tuple[int, int, int]:
    if not isinstance(document, dict) or document.get("SchemaVersion") != 2:
        raise TrivyValidationError("expected a Trivy schema 2 JSON document")
    if document.get("ArtifactType") != "container_image":
        raise TrivyValidationError("expected a container image scan")

    metadata = document.get("Metadata")
    if not isinstance(metadata, dict):
        raise TrivyValidationError("image metadata is missing")
    image_id = metadata.get("ImageID")
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        raise TrivyValidationError("image digest is missing")
    os_info = metadata.get("OS")
    if not isinstance(os_info, dict) or not os_info.get("Family"):
        raise TrivyValidationError("image OS identification is missing")

    results = document.get("Results")
    if not isinstance(results, list) or not results:
        raise TrivyValidationError("image has no scan results")

    classes = set()
    vulnerabilities = 0
    fixed_high = 0
    for result in results:
        if not isinstance(result, dict) or not result.get("Target"):
            raise TrivyValidationError("scan result has no target")
        classes.add(result.get("Class"))
        findings = result.get("Vulnerabilities", [])
        if not isinstance(findings, list):
            raise TrivyValidationError("vulnerabilities must be a list")
        for finding in findings:
            if not isinstance(finding, dict) or not finding.get("VulnerabilityID"):
                raise TrivyValidationError("vulnerability has no identifier")
            vulnerabilities += 1
            if finding.get("Severity") in ("HIGH", "CRITICAL") and finding.get(
                "FixedVersion"
            ):
                fixed_high += 1

    if not {"os-pkgs", "lang-pkgs"}.issubset(classes):
        raise TrivyValidationError("image lacks OS or language package coverage")
    return len(results), vulnerabilities, fixed_high


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: trivychecks.py image.trivy.json", file=sys.stderr)
        return 2
    try:
        document = json.loads(pathlib.Path(argv[1]).read_text(encoding="utf-8"))
        targets, vulnerabilities, fixed_high = validate_trivy(document)
    except (OSError, json.JSONDecodeError, TrivyValidationError) as error:
        print(f"REFUSED: invalid Trivy image report: {error}", file=sys.stderr)
        return 1
    print(
        f"ok    Trivy scanned {targets} targets with {vulnerabilities} findings "
        f"({fixed_high} fixed High/Critical); inventory only, not a gate"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
