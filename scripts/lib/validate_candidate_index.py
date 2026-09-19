#!/usr/bin/env python3
"""Bind an OCI candidate index to exact AMD64 and ARM64 child manifest bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re

INDEX_MEDIA_TYPE = "application/vnd.oci.image.index.v1+json"
MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
CONFIG_MEDIA_TYPE = "application/vnd.oci.image.config.v1+json"
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
PLATFORMS = {"amd64": "linux/amd64", "arm64": "linux/arm64"}


class CandidateIndexError(ValueError):
    """The candidate identity does not match the independently named digests."""


def require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value):
        raise CandidateIndexError(f"{label} must be a lowercase SHA-256 digest")
    return value


def decode(document: bytes, label: str) -> dict:
    def unique_keys(pairs: list[tuple[str, object]]) -> dict:
        value = {}
        for key, item in pairs:
            if key in value:
                raise CandidateIndexError(f"{label} has duplicate JSON key {key}")
            value[key] = item
        return value

    def invalid_constant(value: str) -> None:
        raise CandidateIndexError(f"{label} contains non-JSON value {value}")

    try:
        value = json.loads(document, object_pairs_hook=unique_keys, parse_constant=invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CandidateIndexError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise CandidateIndexError(f"{label} must be a JSON object")
    return value


def verify_bytes(document: bytes, expected: str, label: str) -> dict:
    expected = require_digest(expected, label)
    measured = f"sha256:{hashlib.sha256(document).hexdigest()}"
    if measured != expected:
        raise CandidateIndexError(f"{label} bytes do not match {expected}")
    return decode(document, label)


def require_blob_descriptor(value: object, label: str, media_type: str | None = None) -> None:
    if not isinstance(value, dict):
        raise CandidateIndexError(f"{label} descriptor is missing")
    require_digest(value.get("digest"), label)
    if not isinstance(value.get("size"), int) or isinstance(value["size"], bool) or value["size"] <= 0:
        raise CandidateIndexError(f"{label} descriptor has no positive byte size")
    if media_type is not None and value.get("mediaType") != media_type:
        raise CandidateIndexError(f"{label} has an unexpected media type")
    if media_type is None and not isinstance(value.get("mediaType"), str):
        raise CandidateIndexError(f"{label} has no media type")


def validate_manifest(document: dict, architecture: str, config_bytes: bytes) -> None:
    if document.get("schemaVersion") != 2 or document.get("mediaType") != MANIFEST_MEDIA_TYPE:
        raise CandidateIndexError(f"{architecture} is not an OCI image manifest")
    if "artifactType" in document or "subject" in document:
        raise CandidateIndexError(f"{architecture} is an artifact, not an image manifest")
    config_descriptor = document.get("config")
    require_blob_descriptor(config_descriptor, f"{architecture} config", CONFIG_MEDIA_TYPE)
    if config_descriptor["size"] != len(config_bytes):
        raise CandidateIndexError(f"{architecture} config byte size differs from manifest descriptor")
    config = verify_bytes(config_bytes, config_descriptor["digest"], f"{architecture} config")
    if config.get("os") != "linux" or config.get("architecture") != architecture:
        raise CandidateIndexError(f"{architecture} config platform disagrees with index")
    layers = document.get("layers")
    if not isinstance(layers, list) or not layers:
        raise CandidateIndexError(f"{architecture} manifest has no layers")
    for index, layer in enumerate(layers):
        require_blob_descriptor(layer, f"{architecture} layer {index}")
    rootfs = config.get("rootfs")
    diff_ids = rootfs.get("diff_ids") if isinstance(rootfs, dict) else None
    if not isinstance(rootfs, dict) or rootfs.get("type") != "layers" or not isinstance(diff_ids, list):
        raise CandidateIndexError(f"{architecture} config has no layer rootfs inventory")
    if len(diff_ids) != len(layers):
        raise CandidateIndexError(f"{architecture} config layer count differs from manifest")
    for index, diff_id in enumerate(diff_ids):
        require_digest(diff_id, f"{architecture} uncompressed layer {index}")


def validate(
    index_bytes: bytes,
    expected_index_digest: str,
    child_bytes: dict[str, bytes],
    config_bytes: dict[str, bytes],
    expected_child_digests: dict[str, str],
) -> dict[str, object]:
    if any(set(values) != set(PLATFORMS) for values in (child_bytes, config_bytes, expected_child_digests)):
        raise CandidateIndexError("exactly AMD64 and ARM64 child, config, and digest inputs are required")
    index = verify_bytes(index_bytes, expected_index_digest, "index")
    if index.get("schemaVersion") != 2 or index.get("mediaType") != INDEX_MEDIA_TYPE:
        raise CandidateIndexError("candidate is not an OCI image index")
    descriptors = index.get("manifests")
    if not isinstance(descriptors, list) or len(descriptors) != 2:
        raise CandidateIndexError("index must contain exactly two image manifests")
    seen: set[str] = set()
    for descriptor in descriptors:
        require_blob_descriptor(descriptor, "index child", MANIFEST_MEDIA_TYPE)
        platform = descriptor.get("platform")
        if not isinstance(platform, dict) or set(platform) != {"os", "architecture"}:
            raise CandidateIndexError("index child needs an exact OS/architecture platform")
        architecture = platform.get("architecture")
        if platform.get("os") != "linux" or architecture not in PLATFORMS or architecture in seen:
            raise CandidateIndexError("index has an unsupported or duplicate platform")
        seen.add(architecture)
        expected = require_digest(expected_child_digests[architecture], f"{architecture} manifest")
        if descriptor["digest"] != expected:
            raise CandidateIndexError(f"index descriptor disagrees with {architecture} manifest digest")
        document = child_bytes[architecture]
        if descriptor["size"] != len(document):
            raise CandidateIndexError(f"{architecture} manifest byte size differs from index descriptor")
        child = verify_bytes(document, expected, f"{architecture} manifest")
        validate_manifest(child, architecture, config_bytes[architecture])
    if seen != set(PLATFORMS):
        raise CandidateIndexError("index omits a required architecture")
    return {"indexDigest": expected_index_digest, "manifests": expected_child_digests}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=pathlib.Path, required=True)
    parser.add_argument("--index-digest", required=True)
    for architecture in PLATFORMS:
        parser.add_argument(f"--{architecture}-manifest", type=pathlib.Path, required=True)
        parser.add_argument(f"--{architecture}-config", type=pathlib.Path, required=True)
        parser.add_argument(f"--{architecture}-digest", required=True)
    args = parser.parse_args()
    try:
        result = validate(
            args.index.read_bytes(),
            args.index_digest,
            {arch: getattr(args, f"{arch}_manifest").read_bytes() for arch in PLATFORMS},
            {arch: getattr(args, f"{arch}_config").read_bytes() for arch in PLATFORMS},
            {arch: getattr(args, f"{arch}_digest") for arch in PLATFORMS},
        )
    except (OSError, CandidateIndexError) as error:
        parser.exit(1, f"REFUSED: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
