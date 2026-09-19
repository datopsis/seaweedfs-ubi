#!/usr/bin/env bash
# Inspect the exact filesystem exported from the locally built image.
# Run once per native architecture; an amd64 result never stands for arm64.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"
CONTAINER_ID=""

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

cleanup() {
	[ -z "$CONTAINER_ID" ] || runtime rm -f "$CONTAINER_ID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

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

# Requirements: L3-RUN-003 L3-RUN-005
main() {
	local python
	python="$(resolve_python)" || {
		printf 'REFUSED: a Python 3 interpreter is required\n' >&2
		exit 2
	}
	command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1 || {
		printf 'REFUSED: %s is required\n' "$CONTAINER_RUNTIME" >&2
		exit 2
	}
	runtime image exists "$IMAGE" || {
		printf 'REFUSED: image %s is not present\n' "$IMAGE" >&2
		exit 2
	}
	CONTAINER_ID="$(runtime create "$IMAGE" version)"
	runtime export "$CONTAINER_ID" |
		"$python" "${REPO_ROOT}/tests/lib/image_filesystem_checks.py" -
}

main "$@"
