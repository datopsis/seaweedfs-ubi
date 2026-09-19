#!/usr/bin/env python3
"""Fail-closed tag/ref admission before any release credential is granted."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess

from validate_release_tag import TAG_PATTERN, ReleaseTagError, parse_calendar_date, validate_release_tag

ROOT = pathlib.Path(__file__).resolve().parents[2]


def git(root: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ReleaseTagError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def admit(root: pathlib.Path, tag: str, expected_date: str) -> dict[str, object]:
    """Require an annotated tag on the exact fetched main tip and reviewed lock."""
    if not TAG_PATTERN.fullmatch(tag):
        raise ReleaseTagError("release ref name does not match the version contract")
    if git(root, "cat-file", "-t", f"refs/tags/{tag}") != "tag":
        raise ReleaseTagError("release ref must be an annotated tag")
    tagged_commit = git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}")
    checkout_commit = git(root, "rev-parse", "HEAD")
    main_commit = git(root, "rev-parse", "refs/remotes/origin/main")
    if tagged_commit != checkout_commit:
        raise ReleaseTagError("checked-out commit differs from the tagged commit")
    if tagged_commit != main_commit:
        raise ReleaseTagError("tagged commit is not the exact protected-main tip")
    all_tags = git(root, "tag", "--list").splitlines()
    if all_tags.count(tag) != 1:
        raise ReleaseTagError("release tag is missing from the complete local tag snapshot")
    existing_tags = [name for name in all_tags if name != tag]
    admitted = validate_release_tag(
        tag,
        root / "artifacts" / "seaweedfs.lock.json",
        root / "Containerfile",
        parse_calendar_date(expected_date, "workflow UTC date"),
        existing_tags,
    )
    admitted["commit"] = tagged_commit
    return admitted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--expected-date", required=True, help="workflow UTC date, YYYY-MM-DD")
    args = parser.parse_args()
    try:
        result = admit(ROOT, args.tag, args.expected_date)
    except ReleaseTagError as error:
        parser.exit(1, f"REFUSED: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
