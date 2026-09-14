#!/usr/bin/env python3
"""Validate the structure and internal consistency of an artifact lock.

The realistic failure this guards against is not a malformed file. It is a
half-edited one: a version bumped in the header but not in the certificate
identity, an architecture digest updated without its binary digest, a variant
renamed without its runtime marker. A lock like that is still valid JSON and
still parses, and the admission gate would happily enforce a contradiction.

So this checks shape *and* agreement between fields, and reports every problem
it finds rather than stopping at the first, because a reviewer fixing a lock
wants the whole list.

Implemented without a schema library on purpose. The pinned CI environment is
hash-locked, a dependency would have to be justified and maintained, and the
cross-field checks that catch the real failures cannot be expressed in JSON
Schema anyway.

Usage:
    check_artifact_lock.py <lock.json> [<lock.json> ...]

Exit status:
    0  every lock is well formed and self-consistent
    1  at least one problem was found
    2  the invocation itself was wrong
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SUPPORTED_SCHEMA_VERSIONS = {1}
SUPPORTED_PATHS = {"verified-container-image", "release-tarball"}


class Report:
    def __init__(self, name: str) -> None:
        self.name = name
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)

    def require(self, condition: bool, message: str) -> bool:
        if not condition:
            self.fail(message)
        return condition


def get(report: Report, obj: object, path: str) -> object | None:
    """Fetch a dotted key, reporting a precise location when it is absent."""
    current = obj
    for index, part in enumerate(path.split(".")):
        if not isinstance(current, dict) or part not in current:
            report.fail(f"missing key: {'.'.join(path.split('.')[: index + 1])}")
            return None
        current = current[part]
    return current


def check_upstream(report: Report, lock: dict) -> None:
    version = get(report, lock, "schemaVersion")
    if version is not None and version not in SUPPORTED_SCHEMA_VERSIONS:
        report.fail(
            f"schemaVersion {version!r} is not supported by this checker "
            f"(supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}). "
            f"A new schema version needs a reviewed checker update, not a bypass."
        )
    recorded = get(report, lock, "recordedOn")
    if isinstance(recorded, str) and not DATE.match(recorded):
        report.fail(f"recordedOn {recorded!r} is not an ISO calendar date")

    for key in ("project", "repository", "releaseTag", "releaseCommit", "license"):
        value = get(report, lock, f"upstream.{key}")
        if value is not None and (not isinstance(value, str) or not value.strip()):
            report.fail(f"upstream.{key} must be a non-empty string")

    commit = get(report, lock, "upstream.releaseCommit")
    if isinstance(commit, str) and not COMMIT.match(commit):
        report.fail(
            f"upstream.releaseCommit {commit!r} is not a full 40-character commit "
            f"SHA. A short SHA is ambiguous and must not identify a release."
        )


def check_variant(report: Report, lock: dict) -> None:
    name = get(report, lock, "variant.name")
    if name is not None and not isinstance(name, str):
        report.fail("variant.name must be a string")
    tags = get(report, lock, "variant.buildTags")
    if tags is not None and (
        not isinstance(tags, list) or not all(isinstance(t, str) for t in tags)
    ):
        report.fail("variant.buildTags must be a list of strings")
    marker = get(report, lock, "variant.versionMarker")
    if marker is not None and (not isinstance(marker, str) or not marker.strip()):
        report.fail(
            "variant.versionMarker must be a non-empty string. It is what proves "
            "the admitted build is the intended variant, so it cannot be blank."
        )


def check_acquisition(report: Report, lock: dict) -> None:
    path = get(report, lock, "acquisition.path")
    if path is not None and path not in SUPPORTED_PATHS:
        report.fail(
            f"acquisition.path {path!r} is not one of {sorted(SUPPORTED_PATHS)}"
        )

    if path == "verified-container-image":
        index = get(report, lock, "acquisition.indexDigest")
        if isinstance(index, str) and not DIGEST.match(index):
            report.fail(
                f"acquisition.indexDigest {index!r} is not a lowercase "
                f"sha256:<64 hex> digest"
            )
        for key in ("imageRepository", "imageTag", "binaryPathInImage"):
            value = get(report, lock, f"acquisition.{key}")
            if value is not None and (not isinstance(value, str) or not value.strip()):
                report.fail(f"acquisition.{key} must be a non-empty string")
        binary_path = get(report, lock, "acquisition.binaryPathInImage")
        if isinstance(binary_path, str) and not binary_path.startswith("/"):
            report.fail(
                f"acquisition.binaryPathInImage {binary_path!r} must be absolute"
            )
        for key in ("certificateOidcIssuer", "certificateIdentity"):
            value = get(report, lock, f"acquisition.signature.{key}")
            if isinstance(value, str) and not value.startswith("https://"):
                report.fail(f"acquisition.signature.{key} must be an https URL")
        keyless = get(report, lock, "acquisition.signature.keyless")
        if keyless is not None and not isinstance(keyless, bool):
            report.fail("acquisition.signature.keyless must be a boolean")


def check_architectures(report: Report, lock: dict) -> None:
    architectures = get(report, lock, "architectures")
    if not isinstance(architectures, dict) or not architectures:
        report.fail("architectures must be a non-empty object")
        return

    seen_binaries: dict[str, str] = {}
    seen_manifests: dict[str, str] = {}

    for arch, entry in sorted(architectures.items()):
        where = f"architectures.{arch}"
        if not isinstance(entry, dict):
            report.fail(f"{where} must be an object")
            continue

        platform = entry.get("platform")
        if not isinstance(platform, str) or platform != f"linux/{arch}":
            report.fail(
                f"{where}.platform is {platform!r} but the key is {arch!r}; "
                f"expected 'linux/{arch}'"
            )

        manifest = entry.get("manifestDigest")
        if not isinstance(manifest, str) or not DIGEST.match(manifest):
            report.fail(f"{where}.manifestDigest is not a sha256:<64 hex> digest")
        elif manifest in seen_manifests:
            report.fail(
                f"{where}.manifestDigest duplicates {seen_manifests[manifest]}; "
                f"two architectures cannot share one manifest"
            )
        else:
            seen_manifests[manifest] = where

        binary = entry.get("binary")
        if not isinstance(binary, dict):
            report.fail(f"{where}.binary must be an object")
            continue

        digest = binary.get("sha256")
        if not isinstance(digest, str) or not SHA256_HEX.match(digest):
            report.fail(f"{where}.binary.sha256 is not a lowercase 64-character hex digest")
        elif digest in seen_binaries:
            report.fail(
                f"{where}.binary.sha256 duplicates {seen_binaries[digest]}; "
                f"two architectures cannot share one binary"
            )
        else:
            seen_binaries[digest] = where

        size = binary.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            report.fail(f"{where}.binary.size must be a positive integer")

        if not isinstance(binary.get("elfMachine"), str):
            report.fail(f"{where}.binary.elfMachine must be a string")

        static = binary.get("staticallyLinked")
        if not isinstance(static, bool):
            report.fail(f"{where}.binary.staticallyLinked must be a boolean")

        needed = binary.get("neededLibraries")
        if not isinstance(needed, list) or not all(isinstance(n, str) for n in needed):
            report.fail(f"{where}.binary.neededLibraries must be a list of strings")
        elif static is True and needed:
            report.fail(
                f"{where} records staticallyLinked=true but also lists needed "
                f"libraries {needed}. Those cannot both be true."
            )

        glibc = binary.get("glibcMinimumVersion")
        if glibc is not None and not isinstance(glibc, str):
            report.fail(f"{where}.binary.glibcMinimumVersion must be a string or null")
        elif static is True and glibc is not None:
            report.fail(
                f"{where} records staticallyLinked=true but also a minimum glibc "
                f"version {glibc!r}. A static binary has no glibc requirement."
            )

        if "versionString" not in binary:
            report.fail(f"{where}.binary.versionString must be present (null is allowed)")
        elif binary["versionString"] is not None and not isinstance(
            binary["versionString"], str
        ):
            report.fail(f"{where}.binary.versionString must be a string or null")


def check_agreement(report: Report, lock: dict) -> None:
    """Cross-field checks. These catch the half-edited lock, which is the real risk."""
    upstream = lock.get("upstream", {})
    variant = lock.get("variant", {})
    acquisition = lock.get("acquisition", {})
    evidence = lock.get("evidence", {})
    architectures = lock.get("architectures", {})
    if not isinstance(architectures, dict):
        return

    tag = upstream.get("releaseTag")
    commit = upstream.get("releaseCommit")
    marker = variant.get("versionMarker")

    identity = acquisition.get("signature", {}).get("certificateIdentity")
    if isinstance(identity, str) and isinstance(tag, str):
        expected = f"@refs/tags/{tag}"
        if not identity.endswith(expected):
            report.fail(
                f"acquisition.signature.certificateIdentity ends with "
                f"{identity.rsplit('@', 1)[-1]!r} but upstream.releaseTag is {tag!r}. "
                f"A version bump that misses the identity would verify the wrong "
                f"release, so these must agree."
            )

    if isinstance(evidence, dict):
        recorded_sha = evidence.get("certificateWorkflowSha")
        if (
            isinstance(recorded_sha, str)
            and isinstance(commit, str)
            and recorded_sha != commit
        ):
            report.fail(
                f"evidence.certificateWorkflowSha {recorded_sha!r} does not equal "
                f"upstream.releaseCommit {commit!r}"
            )
        recorded_ref = evidence.get("certificateWorkflowRef")
        if (
            isinstance(recorded_ref, str)
            and isinstance(tag, str)
            and recorded_ref != f"refs/tags/{tag}"
        ):
            report.fail(
                f"evidence.certificateWorkflowRef {recorded_ref!r} does not match "
                f"upstream.releaseTag {tag!r}"
            )

    for arch, entry in sorted(architectures.items()):
        if not isinstance(entry, dict):
            continue
        binary = entry.get("binary")
        if not isinstance(binary, dict):
            continue

        embedded = binary.get("embeddedCommit")
        if isinstance(embedded, str) and isinstance(commit, str):
            if not commit.startswith(embedded):
                report.fail(
                    f"architectures.{arch}.binary.embeddedCommit {embedded!r} is not "
                    f"a prefix of upstream.releaseCommit {commit!r}"
                )

        version = binary.get("versionString")
        if isinstance(version, str):
            for label, expected in (
                ("release tag", tag),
                ("embedded commit", embedded),
                ("variant marker", marker),
                ("architecture", arch),
            ):
                if isinstance(expected, str) and expected not in version:
                    report.fail(
                        f"architectures.{arch}.binary.versionString {version!r} "
                        f"does not contain the {label} {expected!r}"
                    )


def check(path: Path) -> Report:
    report = Report(str(path))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        report.fail(f"cannot read: {error}")
        return report
    try:
        lock = json.loads(text)
    except json.JSONDecodeError as error:
        report.fail(f"is not valid JSON: {error}")
        return report
    if not isinstance(lock, dict):
        report.fail("top level must be an object")
        return report

    check_upstream(report, lock)
    check_variant(report, lock)
    check_acquisition(report, lock)
    check_architectures(report, lock)
    check_agreement(report, lock)
    return report


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    failed = False
    for name in argv[1:]:
        report = check(Path(name))
        if report.problems:
            failed = True
            print(f"{report.name}: {len(report.problems)} problem(s)")
            for problem in report.problems:
                print(f"  - {problem}")
        else:
            print(f"{report.name}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
