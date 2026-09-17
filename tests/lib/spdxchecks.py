"""Require a usable SPDX inventory for the reviewed SeaweedFS image."""

from __future__ import annotations

import json
import pathlib
import sys


class SbomValidationError(ValueError):
    """The generated image SBOM omits required evidence."""


def validate_spdx(document: object) -> tuple[int, int]:
    if not isinstance(document, dict) or document.get("spdxVersion") != "SPDX-2.3":
        raise SbomValidationError("expected an SPDX 2.3 JSON document")

    packages = document.get("packages")
    if not isinstance(packages, list) or not packages:
        raise SbomValidationError("SPDX document has no packages")

    go_modules = set()
    seaweedfs_modules = set()
    for package in packages:
        if not isinstance(package, dict):
            raise SbomValidationError("SPDX package must be an object")
        references = package.get("externalRefs", [])
        if not isinstance(references, list):
            raise SbomValidationError("SPDX package externalRefs must be a list")
        for reference in references:
            if not isinstance(reference, dict):
                raise SbomValidationError("SPDX external reference must be an object")
            if reference.get("referenceType") != "purl":
                continue
            locator = reference.get("referenceLocator", "")
            if isinstance(locator, str) and locator.startswith("pkg:golang/"):
                go_modules.add(locator)
                if "github.com/seaweedfs/seaweedfs" in locator.lower():
                    seaweedfs_modules.add(locator)

    if not go_modules:
        raise SbomValidationError("SPDX document has no Go module inventory")
    if not seaweedfs_modules:
        raise SbomValidationError("SPDX document does not identify SeaweedFS")
    return len(packages), len(go_modules)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: spdxchecks.py image.spdx.json", file=sys.stderr)
        return 2
    try:
        document = json.loads(pathlib.Path(argv[1]).read_text(encoding="utf-8"))
        package_count, go_count = validate_spdx(document)
    except (OSError, json.JSONDecodeError, SbomValidationError) as error:
        print(f"REFUSED: invalid image SBOM: {error}", file=sys.stderr)
        return 1
    print(f"ok    SPDX inventory has {package_count} packages and {go_count} Go modules")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
