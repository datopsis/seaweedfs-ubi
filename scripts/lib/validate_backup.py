#!/usr/bin/env python3
"""Validate cold-backup tar archives before they enter restore evidence."""

from __future__ import annotations

import argparse
import pathlib
import tarfile


class BackupValidationError(ValueError):
    """The archive is absent, unsafe, empty, malformed, or contains a secret."""


def validate_archive(path: pathlib.Path, forbidden_values: tuple[bytes, ...] = ()) -> None:
    """Require a readable archive containing only safe directories and regular files."""

    if not path.is_file():
        raise BackupValidationError(f"backup archive does not exist: {path}")

    try:
        with tarfile.open(path, "r:*") as archive:
            members = archive.getmembers()
            regular_files = []
            for member in members:
                member_path = pathlib.PurePosixPath(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise BackupValidationError(
                        f"backup archive has an unsafe path: {member.name!r}"
                    )
                if not (member.isdir() or member.isfile()):
                    raise BackupValidationError(
                        f"backup archive has a special entry: {member.name!r}"
                    )
                if member.isfile():
                    regular_files.append(member)

            if not regular_files:
                raise BackupValidationError(f"backup archive has no files: {path}")

            for member in regular_files:
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise BackupValidationError(
                        f"backup archive file cannot be read: {member.name!r}"
                    )
                content = extracted.read()
                if any(value and value in content for value in forbidden_values):
                    raise BackupValidationError(
                        f"backup archive contains a forbidden runtime value: {path}"
                    )
    except (tarfile.TarError, OSError) as error:
        raise BackupValidationError(f"backup archive is not readable: {path}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=pathlib.Path)
    parser.add_argument("--forbid-value", action="append", default=[])
    args = parser.parse_args()
    forbidden_values = tuple(value.encode() for value in args.forbid_value)

    try:
        for archive in args.archives:
            validate_archive(archive, forbidden_values)
    except BackupValidationError as error:
        parser.exit(1, f"REFUSED: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
