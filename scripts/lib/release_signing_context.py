#!/usr/bin/env python3
"""Validate the exact GitHub workflow identity allowed to sign a release digest."""

from __future__ import annotations

import argparse
import os
import re

from validate_release_tag import TAG_PATTERN

REPOSITORY = "datopsis/seaweedfs-ubi"
IMAGE = "ghcr.io/datopsis/seaweedfs-ubi"
IMAGE_PATTERN = re.compile(rf"^{re.escape(IMAGE)}@sha256:[0-9a-f]{{64}}$")


class SigningContextError(ValueError):
    """Signing was requested outside the narrowly scoped release workflow."""


def identity_for(image_ref: str, environment: dict[str, str]) -> str:
    if not IMAGE_PATTERN.fullmatch(image_ref):
        raise SigningContextError("image must be the approved GHCR repository at a SHA-256 digest")
    tag = environment.get("GITHUB_REF_NAME", "")
    if not TAG_PATTERN.fullmatch(tag):
        raise SigningContextError("release ref name does not match the version contract")
    ref = f"refs/tags/{tag}"
    workflow_ref = f"{REPOSITORY}/.github/workflows/release.yml@{ref}"
    required = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REF": ref,
        "GITHUB_WORKFLOW_REF": workflow_ref,
    }
    for name, expected in required.items():
        if environment.get(name) != expected:
            raise SigningContextError(f"{name} is not the approved release context")
    if not environment.get("ACTIONS_ID_TOKEN_REQUEST_URL") or not environment.get(
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN"
    ):
        raise SigningContextError("GitHub OIDC token request is unavailable")
    return f"https://github.com/{workflow_ref}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_ref")
    args = parser.parse_args()
    try:
        print(identity_for(args.image_ref, dict(os.environ)))
    except SigningContextError as error:
        parser.exit(1, f"REFUSED: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
