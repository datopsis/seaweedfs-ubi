#!/usr/bin/env bash
# Sign and verify one approved registry digest, never a mutable tag.
# This is an execution primitive for a future gated release job, not a release
# authorization or publication workflow by itself.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_REF="${1:-}"
VERIFICATION_OUTPUT="${2:-}"

[ -n "$IMAGE_REF" ] && [ -n "$VERIFICATION_OUTPUT" ] || {
	printf 'Usage: sign-release-image.sh ghcr.io/datopsis/seaweedfs-ubi@sha256:<digest> OUTPUT\n' >&2
	exit 2
}

command -v python3 >/dev/null 2>&1 || {
	printf 'REFUSED: Python 3 is required\n' >&2
	exit 2
}
command -v cosign >/dev/null 2>&1 || {
	printf 'REFUSED: a pinned Cosign installation is required\n' >&2
	exit 2
}

IDENTITY="$(python3 "${REPO_ROOT}/scripts/lib/release_signing_context.py" "$IMAGE_REF")"
cosign sign --yes "$IMAGE_REF"
cosign verify \
	--certificate-identity "$IDENTITY" \
	--certificate-oidc-issuer https://token.actions.githubusercontent.com \
	"$IMAGE_REF" >"$VERIFICATION_OUTPUT"
