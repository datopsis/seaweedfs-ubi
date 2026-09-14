#!/usr/bin/env bash
#
# Pull the digest-pinned base images.
#
# Separate from assembly on purpose: this is the only step in the build that
# reaches a registry, so assembly can then run with its network closed. On a
# controlled network this runs on the connected host and the images travel with
# the bundle.
#
# The digests come from the Containerfile, so there is one source of truth.
#
# Usage:
#   scripts/fetch-base-images.sh
#
# Environment:
#   CONTAINER_RUNTIME  podman (default) or docker

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"

die() {
	printf 'REFUSED: %s\n' "$*" >&2
	exit 1
}

base_image() {
	sed -n "s/^ARG ${1}=\(.*\)$/\1/p" "${REPO_ROOT}/Containerfile" | head -1
}

main() {
	command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1 || die "$CONTAINER_RUNTIME is required"

	local name image
	for name in UBI_MINIMAL UBI_MICRO; do
		image="$(base_image "$name")"
		[ -n "$image" ] || die "could not read ${name} from the Containerfile"
		case "$image" in
		*@sha256:*) ;;
		*) die "${name} is not pinned by digest: ${image}" ;;
		esac
		printf 'Pulling %s\n' "$image"
		"$CONTAINER_RUNTIME" pull --quiet "$image" >/dev/null ||
			die "could not pull ${image}"
	done

	printf '\nBase images are present. Assembly can now run without a network.\n'
}

main "$@"
