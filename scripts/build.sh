#!/usr/bin/env bash
#
# Convenience wrapper over the three build phases.
#
# They are separate commands because they have different trust properties, and
# this wrapper does not blur that: it simply runs them in order on a host that
# has a network. On a controlled network, run the first two on the connected
# host, transfer the bundle and the base images, and run the third disconnected.
#
#   fetch-artifacts.sh     network: verify the signature and admit the binary
#   fetch-base-images.sh   network: pull the digest-pinned bases
#   build-image.sh         no network: verify again, then assemble
#
# A plain `podman build .` will not work, by design. The image cannot be
# assembled from inputs that have not been through the admission gate.
#
# Usage:
#   scripts/build.sh [arch]        default: the host architecture

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

host_arch() {
	case "$(uname -m)" in
	x86_64 | amd64) printf 'amd64' ;;
	aarch64 | arm64) printf 'arm64' ;;
	*) printf '%s' "$(uname -m)" ;;
	esac
}

main() {
	local arch="${1:-$(host_arch)}"

	printf '== Acquiring and verifying the upstream binary (%s)\n\n' "$arch"
	"${REPO_ROOT}/scripts/fetch-artifacts.sh" "$arch"

	printf '\n== Pulling the pinned base images\n\n'
	"${REPO_ROOT}/scripts/fetch-base-images.sh"

	printf '\n== Assembling the image\n\n'
	"${REPO_ROOT}/scripts/build-image.sh" "$arch"

	printf '\nNext: tests/smoke.sh\n'
}

main "$@"
