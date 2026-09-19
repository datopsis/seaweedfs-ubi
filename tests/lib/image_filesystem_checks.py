"""Inspect an exported image filesystem without extracting its contents.

This checks two narrow image-owned properties (IMG-06 and IMG-09). It is not
an SBOM, a malware scan, a package inventory, or release-candidate evidence.
"""

from __future__ import annotations

import argparse
import stat
import sys
import tarfile
from pathlib import PurePosixPath
from typing import BinaryIO

PACKAGE_TOOLS = {"dnf", "dnf5", "microdnf", "yum", "rpm", "rpm-ostree", "rpmkeys", "repoquery"}
FORBIDDEN_CONFIGURATION = (
    "etc/yum.repos.d/",
    "etc/dnf/",
    "etc/yum/",
    "etc/rpm/",
    "etc/pki/rpm-gpg/",
    "etc/yum.conf",
)


def inspect_export(stream: BinaryIO) -> tuple[int, list[str]]:
    """Return the number of entries and deterministic, bounded findings."""

    findings: list[str] = []
    count = 0
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for entry in archive:
            count += 1
            name = entry.name.removeprefix("./").rstrip("/")
            path = PurePosixPath(name)
            if not name or path.is_absolute() or ".." in path.parts:
                findings.append(f"unsafe archive path: {entry.name}")
                continue
            if path.name in PACKAGE_TOOLS and (entry.isfile() or entry.issym() or entry.islnk()):
                findings.append(f"package manager in runtime: {name}")
            if any(name == prefix.rstrip("/") or name.startswith(prefix)
                   for prefix in FORBIDDEN_CONFIGURATION):
                findings.append(f"package repository or key material: {name}")
            if entry.isfile() and entry.mode & (stat.S_ISUID | stat.S_ISGID):
                findings.append(f"setuid/setgid file: {name}")
            if (entry.isfile() or entry.isdir()) and entry.mode & stat.S_IWOTH:
                if name != "tmp" and not name.startswith("tmp/"):
                    findings.append(f"undeclared world-writable path: {name}")
    if count == 0:
        findings.append("empty image filesystem export")
    return count, findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", help="path to a Podman/Docker image export tar, or - for stdin")
    args = parser.parse_args()
    try:
        if args.export == "-":
            count, findings = inspect_export(sys.stdin.buffer)
        else:
            with open(args.export, "rb") as stream:
                count, findings = inspect_export(stream)
    except (OSError, EOFError, tarfile.TarError) as error:
        print(f"image filesystem inspection failed: {error}", file=sys.stderr)
        return 1
    for finding in findings:
        print(f"image filesystem: {finding}", file=sys.stderr)
    if findings:
        return 1
    print(f"image filesystem: inspected {count} entries; no package-manager residue or privilege-raising modes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
