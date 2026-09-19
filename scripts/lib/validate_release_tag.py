#!/usr/bin/env python3
"""Fail closed unless a proposed container release tag matches reviewed inputs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re


TAG_PATTERN = re.compile(
    r"^v(?P<seaweedfs>[0-9]+\.[0-9]+(?:\.[0-9]+)?)"
    r"-ubi(?P<ubi>[1-9][0-9]*)"
    r"-r(?P<date>[0-9]{8})\.(?P<sequence>[1-9][0-9]*)$"
)
BASE_ARGUMENTS = ("UBI_MINIMAL", "UBI_MICRO")
PINNED_BASE_PATTERN = re.compile(
    r"/ubi(?P<major>[1-9][0-9]*)(?:/|:)"
    r".*@sha256:[0-9a-f]{64}$"
)


class ReleaseTagError(ValueError):
    """The proposed tag or one of the reviewed inputs is not admissible."""


def parse_calendar_date(value: str, label: str) -> dt.date:
    """Parse an ISO date and report policy-oriented errors."""
    try:
        return dt.date.fromisoformat(value)
    except ValueError as error:
        raise ReleaseTagError(f"{label} {value!r} is not a real ISO calendar date") from error


def read_lock_version(path: pathlib.Path) -> str:
    """Return the reviewed upstream release tag from the artifact lock."""
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseTagError(f"cannot read artifact lock {path}: {error}") from error

    if not isinstance(lock, dict):
        raise ReleaseTagError(f"artifact lock {path} must contain a JSON object")
    upstream = lock.get("upstream")
    if not isinstance(upstream, dict):
        raise ReleaseTagError(f"artifact lock {path} has no upstream object")
    version = upstream.get("releaseTag")
    if not isinstance(version, str) or not version:
        raise ReleaseTagError(
            f"artifact lock {path} has no non-empty upstream.releaseTag"
        )
    return version


def read_ubi_major(path: pathlib.Path) -> int:
    """Require both Containerfile bases to be digest-pinned to one UBI major."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ReleaseTagError(f"cannot read Containerfile {path}: {error}") from error

    values: dict[str, str] = {}
    for line in lines:
        for name in BASE_ARGUMENTS:
            prefix = f"ARG {name}="
            if line.startswith(prefix):
                if name in values:
                    raise ReleaseTagError(f"Containerfile defines {name} more than once")
                values[name] = line.removeprefix(prefix).strip()

    majors: dict[str, int] = {}
    for name in BASE_ARGUMENTS:
        value = values.get(name)
        if value is None:
            raise ReleaseTagError(f"Containerfile has no {name} build argument")
        match = PINNED_BASE_PATTERN.search(value)
        if match is None:
            raise ReleaseTagError(
                f"Containerfile {name} is not a digest-pinned UBI image: {value!r}"
            )
        majors[name] = int(match.group("major"))

    if len(set(majors.values())) != 1:
        detail = ", ".join(f"{name}=UBI {major}" for name, major in majors.items())
        raise ReleaseTagError(f"Containerfile base UBI majors disagree: {detail}")
    return next(iter(majors.values()))


def validate_release_tag(
    tag: str,
    lock_path: pathlib.Path,
    containerfile_path: pathlib.Path,
    expected_date: dt.date,
    existing_tags: list[str],
) -> dict[str, object]:
    """Validate the local, deterministic portion of release-tag admission."""
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ReleaseTagError(
            f"tag {tag!r} does not match "
            "v<seaweedfs>-ubi<major>-r<YYYYMMDD>.<positive-sequence>"
        )

    date_digits = match.group("date")
    release_date = parse_calendar_date(
        f"{date_digits[0:4]}-{date_digits[4:6]}-{date_digits[6:8]}",
        "release date",
    )
    if release_date != expected_date:
        raise ReleaseTagError(
            f"tag release date {release_date.isoformat()} does not equal the "
            f"workflow UTC date {expected_date.isoformat()}; release tags cannot be "
            "backdated or future-dated"
        )

    seaweedfs_version = match.group("seaweedfs")
    locked_version = read_lock_version(lock_path)
    if seaweedfs_version != locked_version:
        raise ReleaseTagError(
            f"tag SeaweedFS version {seaweedfs_version!r} does not equal the "
            f"artifact lock version {locked_version!r}"
        )

    ubi_major = int(match.group("ubi"))
    locked_ubi_major = read_ubi_major(containerfile_path)
    if ubi_major != locked_ubi_major:
        raise ReleaseTagError(
            f"tag UBI major {ubi_major} does not equal the digest-pinned "
            f"Containerfile base major {locked_ubi_major}"
        )

    normalized_existing = [candidate.strip() for candidate in existing_tags if candidate.strip()]
    if tag in normalized_existing:
        raise ReleaseTagError(f"release tag {tag!r} already exists and is immutable")

    sequences = []
    for candidate in normalized_existing:
        existing_match = TAG_PATTERN.fullmatch(candidate)
        if existing_match is None or existing_match.group("date") != date_digits:
            continue
        sequences.append(int(existing_match.group("sequence")))

    sequence = int(match.group("sequence"))
    expected_sequence = max(sequences, default=0) + 1
    if sequence != expected_sequence:
        raise ReleaseTagError(
            f"tag daily sequence {sequence} is not the next sequence "
            f"{expected_sequence} for {release_date.isoformat()}; gaps cannot be filled"
        )

    return {
        "tag": tag,
        "seaweedfsVersion": seaweedfs_version,
        "ubiMajor": ubi_major,
        "releaseDate": release_date.isoformat(),
        "dailySequence": sequence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--lock", required=True, type=pathlib.Path)
    parser.add_argument("--containerfile", required=True, type=pathlib.Path)
    parser.add_argument(
        "--expected-date",
        required=True,
        help="UTC workflow date in YYYY-MM-DD form",
    )
    parser.add_argument(
        "--existing-tags-file",
        required=True,
        type=pathlib.Path,
        help="newline-delimited immutable repository tag snapshot",
    )
    args = parser.parse_args()

    try:
        expected_date = parse_calendar_date(args.expected_date, "expected date")
        existing_tags = args.existing_tags_file.read_text(encoding="utf-8").splitlines()
        result = validate_release_tag(
            args.tag,
            args.lock,
            args.containerfile,
            expected_date,
            existing_tags,
        )
    except (OSError, ReleaseTagError) as error:
        parser.exit(1, f"REFUSED: {error}\n")

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
