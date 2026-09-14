#!/usr/bin/env bash
#
# Acquire the upstream SeaweedFS binary and admit it only if every recorded
# measurement matches, and only if the publisher signature verifies.
#
# This script needs a network. Assembly does not: it consumes the bundle this
# produces, so acquisition and assembly can run on different hosts with
# different trust properties.
#
# Nothing here resolves a tag. Every reference comes from the reviewed lock as a
# digest, because a tag can move and a digest cannot. The tag in the lock is
# recorded for humans and is never used to fetch.
#
# Usage:
#   scripts/fetch-artifacts.sh [arch ...]      default: every architecture in the lock
#
# Environment:
#   CONTAINER_RUNTIME  podman (default) or docker
#   BUNDLE_DIR         output directory (default .artifact-bundle)
#   LOCK_FILE          lock path (default artifacts/seaweedfs.lock.json)
#   COSIGN             a local cosign binary to use instead of the pinned image

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${LOCK_FILE:-${REPO_ROOT}/artifacts/seaweedfs.lock.json}"
BUNDLE_DIR="${BUNDLE_DIR:-${REPO_ROOT}/.artifact-bundle}"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"

# Resolved in main(); declared here so its scope is obvious.
PYTHON=""

# Pinned by digest so the verification tool is itself a reviewed input.
COSIGN_IMAGE="ghcr.io/sigstore/cosign/cosign@sha256:68839b7f13dac5a6744a5d8818e984dd39183374e37855c19e14d623d9bc9037"

die() {
	printf 'REFUSED: %s\n' "$*" >&2
	exit 1
}

note() { printf '%s\n' "$*"; }

require() {
	command -v "$1" >/dev/null 2>&1 || die "$1 is required and was not found. Verification is never skipped because a tool is missing."
}

# Prefer python3, fall back to python. CI runners provide python3; a Windows
# contributor environment commonly provides only python, and a Microsoft Store
# shim named python3 that is not an interpreter.
resolve_python() {
	local candidate
	for candidate in python3 python; do
		if command -v "$candidate" >/dev/null 2>&1 &&
			"$candidate" -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
			printf '%s' "$candidate"
			return 0
		fi
	done
	return 1
}

# Read one dotted key out of the lock. Absent keys are an error, not an empty
# string, so a typo or a schema change cannot silently disable a check.
lock_get() {
	"$PYTHON" - "$LOCK_FILE" "$1" <<-'PYTHON'
		import json, sys
		data = json.load(open(sys.argv[1], encoding="utf-8"))
		for part in sys.argv[2].split("."):
		    if not isinstance(data, dict) or part not in data:
		        sys.exit(f"lock key not found: {sys.argv[2]}")
		    data = data[part]
		if data is None:
		    print("")
		elif isinstance(data, bool):
		    print("true" if data else "false")
		elif isinstance(data, (str, int, float)):
		    print(data)
		else:
		    print(json.dumps(data))
	PYTHON
}

lock_architectures() {
	"$PYTHON" - "$LOCK_FILE" <<-'PYTHON'
		import json, sys
		data = json.load(open(sys.argv[1], encoding="utf-8"))
		print(" ".join(sorted(data.get("architectures", {}))))
	PYTHON
}

cosign_verify() {
	local reference="$1" issuer="$2" identity="$3"
	if [ -n "${COSIGN:-}" ]; then
		"$COSIGN" verify \
			--certificate-oidc-issuer "$issuer" \
			--certificate-identity "$identity" \
			"$reference" >/dev/null
	else
		"$CONTAINER_RUNTIME" run --rm "$COSIGN_IMAGE" verify \
			--certificate-oidc-issuer "$issuer" \
			--certificate-identity "$identity" \
			"$reference" >/dev/null
	fi
}

main() {
	PYTHON="$(resolve_python)" ||
		die "a Python 3 interpreter is required and was not found as python3 or python. Verification is never skipped because a tool is missing."
	require "$CONTAINER_RUNTIME"
	[ -f "$LOCK_FILE" ] || die "the artifact lock $LOCK_FILE does not exist"

	local path repository index_digest binary_path issuer identity tag
	path="$(lock_get acquisition.path)"
	[ "$path" = "verified-container-image" ] ||
		die "this script implements the verified-container-image path, but the lock records '$path'"

	repository="$(lock_get acquisition.imageRepository)"
	tag="$(lock_get acquisition.imageTag)"
	index_digest="$(lock_get acquisition.indexDigest)"
	binary_path="$(lock_get acquisition.binaryPathInImage)"
	issuer="$(lock_get acquisition.signature.certificateOidcIssuer)"
	identity="$(lock_get acquisition.signature.certificateIdentity)"

	local requested
	if [ "$#" -gt 0 ]; then
		requested="$*"
	else
		requested="$(lock_architectures)"
	fi
	[ -n "$requested" ] || die "the lock records no architectures"

	note "SeaweedFS $(lock_get upstream.releaseTag) ($(lock_get variant.name)), commit $(lock_get upstream.releaseCommit)"
	note "Source image ${repository} (recorded tag ${tag}, fetched by digest only)"
	note ""

	# The index signature is checked first. Upstream signs recursively, so each
	# architecture manifest is checked again below rather than inferred from this.
	note "Verifying the image index signature"
	cosign_verify "${repository}@${index_digest}" "$issuer" "$identity" ||
		die "cosign could not verify ${repository}@${index_digest} against the recorded identity. Nothing is admitted."
	note "  verified: index ${index_digest}"
	note "  verified: identity ${identity}"
	note ""

	mkdir -p "$BUNDLE_DIR"

	local arch manifest_digest destination container
	for arch in $requested; do
		manifest_digest="$(lock_get "architectures.${arch}.manifestDigest")" ||
			die "the lock has no entry for architecture '$arch'"

		note "Architecture ${arch}"
		cosign_verify "${repository}@${manifest_digest}" "$issuer" "$identity" ||
			die "cosign could not verify the ${arch} manifest ${manifest_digest}"
		note "  verified: manifest ${manifest_digest}"

		"$CONTAINER_RUNTIME" pull --quiet "${repository}@${manifest_digest}" >/dev/null ||
			die "could not pull ${repository}@${manifest_digest}"

		destination="${BUNDLE_DIR}/${arch}"
		mkdir -p "$destination"

		# create, never run: a foreign-architecture image must not need emulation
		# merely to have a file copied out of it.
		container="$("$CONTAINER_RUNTIME" create "${repository}@${manifest_digest}")" ||
			die "could not create a container from ${repository}@${manifest_digest}"
		if ! "$CONTAINER_RUNTIME" cp "${container}:${binary_path}" "${destination}/weed"; then
			"$CONTAINER_RUNTIME" rm -f "$container" >/dev/null 2>&1 || true
			die "could not copy ${binary_path} out of the ${arch} image"
		fi
		"$CONTAINER_RUNTIME" rm -f "$container" >/dev/null 2>&1 || true

		"$PYTHON" "${REPO_ROOT}/scripts/lib/verify.py" "$LOCK_FILE" "$arch" "${destination}/weed" ||
			die "the extracted ${arch} binary does not match the lock"

		chmod 0755 "${destination}/weed"
		note "  admitted: ${destination}/weed"
		note ""
	done

	note "Every requested architecture was verified and admitted into ${BUNDLE_DIR}."
	note ""
	note "This proves reviewed bytes and a verifiable publisher identity. It does not"
	note "prove the signed image is free of defects, and the admitted binary is not the"
	note "release tarball upstream also publishes. See docs/ARTIFACT-ACQUISITION.md."
}

main "$@"
