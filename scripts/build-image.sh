#!/usr/bin/env bash
#
# Assemble the image from already-verified inputs.
#
# This step reaches nothing. The binary arrives through a named build context
# produced by the admission gate, the base images are pinned by digest and must
# already be present locally, and the build runs with its network disabled where
# the runtime supports it.
#
# The bundle is verified again here. Acquisition and assembly can be separated
# by a transfer, a different host, or an interval of time, and a bundle is an
# ordinary directory that anything with write access can alter.
#
# Usage:
#   scripts/build-image.sh [arch]        default: the host architecture
#
# Environment:
#   CONTAINER_RUNTIME  podman (default) or docker
#   IMAGE              image reference to build (default localhost/seaweedfs-ubi:development)
#   BUNDLE_DIR         verified bundle (default .artifact-bundle)
#   LOCK_FILE          lock path (default artifacts/seaweedfs.lock.json)

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${LOCK_FILE:-${REPO_ROOT}/artifacts/seaweedfs.lock.json}"
BUNDLE_DIR="${BUNDLE_DIR:-${REPO_ROOT}/.artifact-bundle}"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"

# Resolved in main(); declared here so its scope is obvious.
PYTHON=""

die() {
	printf 'REFUSED: %s\n' "$*" >&2
	exit 1
}

note() { printf '%s\n' "$*"; }

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

lock_get() {
	"$PYTHON" - "$LOCK_FILE" "$1" <<-'PYTHON'
		import json, sys
		data = json.load(open(sys.argv[1], encoding="utf-8"))
		for part in sys.argv[2].split("."):
		    if not isinstance(data, dict) or part not in data:
		        sys.exit(f"lock key not found: {sys.argv[2]}")
		    data = data[part]
		print("" if data is None else data)
	PYTHON
}

host_arch() {
	case "$(uname -m)" in
	x86_64 | amd64) printf 'amd64' ;;
	aarch64 | arm64) printf 'arm64' ;;
	*) printf '%s' "$(uname -m)" ;;
	esac
}

# The digests the Containerfile pins, read from the Containerfile itself so
# there is one source of truth rather than two that can drift.
base_image() {
	local name="$1"
	sed -n "s/^ARG ${name}=\(.*\)$/\1/p" "${REPO_ROOT}/Containerfile" | head -1
}

main() {
	PYTHON="$(resolve_python)" || die "a Python 3 interpreter is required"
	command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1 || die "$CONTAINER_RUNTIME is required"

	local arch="${1:-$(host_arch)}"
	local binary="${BUNDLE_DIR}/${arch}/weed"

	[ -f "$binary" ] || die "no verified binary at ${binary}. Run scripts/fetch-artifacts.sh first."

	note "Re-verifying the bundle before assembly"
	"$PYTHON" "${REPO_ROOT}/scripts/lib/verify.py" "$LOCK_FILE" "$arch" "$binary" ||
		die "the bundle does not match the lock. It was altered after acquisition, or the lock changed."
	note ""

	local minimal micro
	minimal="$(base_image UBI_MINIMAL)"
	micro="$(base_image UBI_MICRO)"
	[ -n "$minimal" ] && [ -n "$micro" ] || die "could not read the pinned base images from the Containerfile"

	# Assembly must not pull. Requiring the bases up front turns a missing
	# prefetch into a clear message rather than a silent network fetch.
	local image
	for image in "$minimal" "$micro"; do
		"$CONTAINER_RUNTIME" image exists "$image" 2>/dev/null ||
			die "base image not present locally: ${image}. Run scripts/fetch-base-images.sh first."
	done

	local network_flag=()
	if [ "$CONTAINER_RUNTIME" = "podman" ]; then
		network_flag=(--network=none)
	else
		note "Note: this runtime has no per-build network switch, so assembly is not"
		note "      proven network-free here. See docs/HERMETIC-BUILD.md."
		note ""
	fi

	note "Assembling ${IMAGE} for ${arch}"
	"$CONTAINER_RUNTIME" build \
		--file "${REPO_ROOT}/Containerfile" \
		--tag "$IMAGE" \
		--build-context "weed=${BUNDLE_DIR}/${arch}" \
		--build-arg "SEAWEEDFS_VERSION=$(lock_get upstream.releaseTag)" \
		--build-arg "SEAWEEDFS_VARIANT=$(lock_get variant.name)" \
		--build-arg "SEAWEEDFS_COMMIT=$(lock_get upstream.releaseCommit)" \
		--build-arg "SOURCE_REVISION=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || printf 'unknown')" \
		--build-arg "BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
		--pull=never \
		${network_flag[@]+"${network_flag[@]}"} \
		"$REPO_ROOT"

	note ""
	note "Built ${IMAGE}"
	"$CONTAINER_RUNTIME" image inspect "$IMAGE" \
		--format '  size: {{.Size}} bytes' 2>/dev/null || true
}

main "$@"
