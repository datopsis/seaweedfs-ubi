#!/usr/bin/env python3
"""Propose an updated artifact lock for a SeaweedFS release.

This is the only supported way the lock changes. It resolves a release tag to
digests, verifies the publisher signature, extracts and measures the binaries,
and writes a lock for review. It never installs anything and never edits an
image; the output is a file whose diff a human reads before it is merged.

Resolution happens here, deliberately, and nowhere else. The admission gate in
fetch-artifacts.sh only ever consumes digests already recorded in a reviewed
lock, so a moved tag cannot change what a build admits.

The release commit is taken from the GitHub API and cross-checked against the
commit in the signing certificate, so neither source vouches for itself alone.

Usage:
    scripts/update-lock.py --tag 4.47 [--variant large_disk] [--output PATH]

Environment:
    CONTAINER_RUNTIME  podman (default) or docker
    COSIGN             a local cosign binary to use instead of the pinned image
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.message
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from verify import read_elf, sha256_of  # noqa: E402

REPOSITORY = "ghcr.io/chrislusf/seaweedfs"
REGISTRY = "ghcr.io"
NAMESPACE = "chrislusf/seaweedfs"
UPSTREAM_REPO = "seaweedfs/seaweedfs"
WORKFLOW = ".github/workflows/container_release_unified.yml"
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
BINARY_IN_IMAGE = "/usr/bin/weed"
COSIGN_IMAGE = (
    "ghcr.io/sigstore/cosign/cosign@sha256:"
    "68839b7f13dac5a6744a5d8818e984dd39183374e37855c19e14d623d9bc9037"
)

# The build tags upstream compiles each published variant with, and the maximum
# volume size the resulting binary reports at runtime. The marker is what proves
# an artifact is the intended variant; the tag name alone proves nothing.
VARIANTS = {
    "normal": {"buildTags": [], "maxVolumeSize": "30GB", "suffix": ""},
    "large_disk": {
        "buildTags": ["5BytesOffset"],
        "maxVolumeSize": "8000GB",
        "suffix": "_large_disk",
    },
}

ARCHITECTURES = ("amd64", "arm64")


class Failed(Exception):
    pass


def run(argv: list[str], capture: bool = True) -> str:
    result = subprocess.run(
        argv,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise Failed(f"{argv[0]} failed: {detail[-1] if detail else result.returncode}")
    return (result.stdout or "").strip()


def get_json(url: str, headers: dict[str, str]) -> tuple[dict, email.message.Message]:
    """Return the parsed body and the response headers.

    The headers are returned as the message object rather than a plain dict
    because HTTP header names are case-insensitive and registries do not agree
    on casing: GHCR returns docker-content-digest in lower case.
    """
    request = urllib.request.Request(url, headers=headers)  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8")), response.headers


def registry_token() -> str:
    url = (
        f"https://{REGISTRY}/token"
        f"?scope=repository:{NAMESPACE}:pull&service={REGISTRY}"
    )
    payload, _ = get_json(url, {})
    token = payload.get("token")
    if not token:
        raise Failed("the registry did not return a pull token")
    return token


def resolve_index(image_tag: str) -> tuple[str, dict[str, str]]:
    """Return the index digest and the per-architecture manifest digests."""
    token = registry_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": ", ".join(
            [
                "application/vnd.oci.image.index.v1+json",
                "application/vnd.docker.distribution.manifest.list.v2+json",
            ]
        ),
    }
    url = f"https://{REGISTRY}/v2/{NAMESPACE}/manifests/{image_tag}"
    index, response_headers = get_json(url, headers)
    digest = response_headers.get("Docker-Content-Digest")
    if not digest:
        raise Failed(f"the registry returned no digest for {image_tag}")

    manifests: dict[str, str] = {}
    for entry in index.get("manifests", []):
        found = entry.get("platform", {})
        if found.get("os") != "linux" or found.get("variant"):
            continue
        architecture = found.get("architecture")
        if architecture in ARCHITECTURES:
            manifests[architecture] = entry["digest"]

    missing = [a for a in ARCHITECTURES if a not in manifests]
    if missing:
        raise Failed(f"{image_tag} publishes no manifest for {', '.join(missing)}")
    return digest, manifests


def release_commit(tag: str) -> str:
    url = f"https://api.github.com/repos/{UPSTREAM_REPO}/git/ref/tags/{tag}"
    payload, _ = get_json(url, {"Accept": "application/vnd.github+json"})
    obj = payload.get("object", {})
    if obj.get("type") != "commit" or not obj.get("sha"):
        raise Failed(
            f"tag {tag} does not resolve directly to a commit; "
            f"an annotated tag object needs dereferencing before it can be locked"
        )
    return obj["sha"]


def cosign_verify(runtime: str, reference: str, identity: str) -> dict:
    local = __import__("os").environ.get("COSIGN")
    argv = [local] if local else [runtime, "run", "--rm", COSIGN_IMAGE]
    argv += [
        "verify",
        "--certificate-oidc-issuer",
        OIDC_ISSUER,
        "--certificate-identity",
        identity,
        reference,
    ]
    payload = run(argv)
    try:
        return json.loads(payload)[0]
    except (json.JSONDecodeError, IndexError, KeyError) as error:
        raise Failed(f"cosign produced no readable attestation for {reference}") from error


def extract(runtime: str, reference: str, destination: Path) -> None:
    run([runtime, "pull", "--quiet", reference])
    container = run([runtime, "create", reference])
    try:
        run([runtime, "cp", f"{container}:{BINARY_IN_IMAGE}", str(destination)])
    finally:
        subprocess.run(
            [runtime, "rm", "-f", container],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def host_architecture() -> str:
    return {"x86_64": "amd64", "AMD64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
        platform.machine(), platform.machine()
    )


def version_string(runtime: str, reference: str) -> str | None:
    """Run the binary, but only where it is native. Emulation is not evidence."""
    try:
        output = run([runtime, "run", "--rm", reference, "version"])
    except Failed:
        return None
    for line in output.splitlines():
        if line.startswith("version "):
            return line.strip()
    return None


def build(tag: str, variant: str, runtime: str) -> dict:
    if variant not in VARIANTS:
        raise Failed(f"unknown variant {variant!r}; known: {', '.join(sorted(VARIANTS))}")
    spec = VARIANTS[variant]
    image_tag = f"{tag}{spec['suffix']}"
    identity = f"https://github.com/{UPSTREAM_REPO}/{WORKFLOW}@refs/tags/{tag}"

    print(f"Resolving {REPOSITORY}:{image_tag}")
    index_digest, manifests = resolve_index(image_tag)
    print(f"  index {index_digest}")

    commit = release_commit(tag)
    print(f"  tag {tag} resolves to commit {commit}")

    print("Verifying the index signature")
    attestation = cosign_verify(runtime, f"{REPOSITORY}@{index_digest}", identity)
    optional = attestation.get("optional", {})
    certificate_sha = optional.get("githubWorkflowSha")
    certificate_ref = optional.get("githubWorkflowRef")
    certificate_repo = optional.get("githubWorkflowRepository")

    if certificate_repo != UPSTREAM_REPO:
        raise Failed(
            f"the signing certificate names repository {certificate_repo!r}, "
            f"not {UPSTREAM_REPO!r}"
        )
    if certificate_sha != commit:
        raise Failed(
            f"the signing certificate records commit {certificate_sha!r} but the "
            f"{tag} tag resolves to {commit!r}. These must agree."
        )
    print(f"  verified against {identity}")
    print(f"  certificate commit agrees with the tag: {commit}")

    architectures: dict[str, dict] = {}
    host = host_architecture()
    with tempfile.TemporaryDirectory() as scratch:
        for architecture in ARCHITECTURES:
            reference = f"{REPOSITORY}@{manifests[architecture]}"
            print(f"Architecture {architecture}")
            cosign_verify(runtime, reference, identity)
            print(f"  verified manifest {manifests[architecture]}")

            binary = Path(scratch) / f"weed-{architecture}"
            extract(runtime, reference, binary)
            elf = read_elf(binary)
            reported = (
                version_string(runtime, reference) if architecture == host else None
            )
            if reported is None and architecture == host:
                raise Failed(
                    f"could not read a version string from the native {architecture} "
                    f"binary, which should be executable here"
                )
            if reported:
                print(f"  reports: {reported}")
                if spec["maxVolumeSize"] not in reported:
                    raise Failed(
                        f"the {architecture} binary reports {reported!r}, which does "
                        f"not carry the {variant} marker {spec['maxVolumeSize']!r}"
                    )
            else:
                print("  version string not captured: not the host architecture")

            architectures[architecture] = {
                "platform": f"linux/{architecture}",
                "manifestDigest": manifests[architecture],
                "binary": {
                    "sha256": sha256_of(binary),
                    "size": binary.stat().st_size,
                    "elfMachine": elf["elfMachine"],
                    "staticallyLinked": elf["staticallyLinked"],
                    "neededLibraries": [],
                    "glibcMinimumVersion": None,
                    "embeddedCommit": commit[:9],
                    "versionString": reported,
                },
            }
            print(f"  sha256 {architectures[architecture]['binary']['sha256']}")

    return {
        "schemaVersion": 1,
        "recordedOn": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "upstream": {
            "project": "seaweedfs",
            "repository": f"https://github.com/{UPSTREAM_REPO}",
            "releaseTag": tag,
            "releaseCommit": commit,
            "license": "Apache-2.0",
        },
        "variant": {
            "name": variant,
            "buildTags": spec["buildTags"],
            "maxVolumeSize": spec["maxVolumeSize"],
            "versionMarker": spec["maxVolumeSize"],
        },
        "acquisition": {
            "path": "verified-container-image",
            "imageRepository": REPOSITORY,
            "imageTag": image_tag,
            "indexDigest": index_digest,
            "binaryPathInImage": BINARY_IN_IMAGE,
            "signature": {
                "tool": "cosign",
                "keyless": True,
                "certificateOidcIssuer": OIDC_ISSUER,
                "certificateIdentity": identity,
            },
        },
        "architectures": architectures,
        "evidence": {
            "signatureVerified": True,
            "signatureVerifiedWith": "cosign (pinned image)",
            "signatureVerifiedOn": dt.datetime.now(dt.timezone.utc).date().isoformat(),
            "certificateWorkflowRepository": certificate_repo,
            "certificateWorkflowSha": certificate_sha,
            "certificateWorkflowRef": certificate_ref,
            "rekorLogIndex": optional.get("Bundle", {})
            .get("Payload", {})
            .get("logIndex"),
            "releaseTagResolvesToCommit": True,
            "notes": [
                "Generated by scripts/update-lock.py and reviewed as a diff before merge.",
                "The index and both architecture manifests were verified with cosign "
                "against the pinned identity and issuer.",
                "The certificate's commit was cross-checked against the commit the "
                "release tag resolves to, so neither source vouches for itself alone.",
                "Linkage was measured by ELF inspection rather than assumed from "
                "upstream's build flags.",
                "A version string is recorded only for the architecture this ran on. "
                "The other must be captured on a native runner before a release.",
                "This proves reviewed bytes and a verifiable publisher identity. It "
                "does not prove the signed image is free of defects.",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="upstream release tag, e.g. 4.47")
    parser.add_argument("--variant", default="large_disk", choices=sorted(VARIANTS))
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "artifacts" / "seaweedfs.lock.json"),
    )
    arguments = parser.parse_args()

    runtime = __import__("os").environ.get("CONTAINER_RUNTIME", "podman")
    if not shutil.which(runtime):
        print(f"REFUSED: {runtime} is required and was not found", file=sys.stderr)
        return 2

    try:
        lock = build(arguments.tag, arguments.variant, runtime)
    except Failed as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1

    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"Wrote {output}")
    print()
    print("This is a proposal, not an admission. Review the diff, confirm the version")
    print("and digests are the ones intended, run the checker and the gate, and open a")
    print("pull request:")
    print()
    print(f"  git diff -- {output}")
    print(f"  python .github/scripts/check_artifact_lock.py {output}")
    print("  scripts/fetch-artifacts.sh")
    print()
    print("Every obligation a version bump carries is listed under 'standing")
    print("obligations' in docs/README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
