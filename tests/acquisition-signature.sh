#!/usr/bin/env bash
#
# Prove the publisher signature check is load bearing.
#
# The offline suite in tests/acquisition.sh covers every measurement the lock
# records. It cannot cover the signature, because that needs cosign, a registry,
# and a transparency log. This suite does, so the control that makes the verified
# image path worth taking is observed working and observed refusing.
#
# It needs a network.
#
# Usage:
#   tests/acquisition-signature.sh
#
# Environment:
#   CONTAINER_RUNTIME  podman (default) or docker
#   LOCK_FILE          lock path (default artifacts/seaweedfs.lock.json)
#   COSIGN             a local cosign binary to use instead of the pinned image

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${LOCK_FILE:-${REPO_ROOT}/artifacts/seaweedfs.lock.json}"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
COSIGN_IMAGE="ghcr.io/sigstore/cosign/cosign@sha256:68839b7f13dac5a6744a5d8818e984dd39183374e37855c19e14d623d9bc9037"

# Resolved in main(); declared here so its scope is obvious.
PYTHON=""

passed=0
failed=0

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

cosign_verify() {
	local reference="$1" issuer="$2" identity="$3"
	if [ -n "${COSIGN:-}" ]; then
		"$COSIGN" verify --certificate-oidc-issuer "$issuer" \
			--certificate-identity "$identity" "$reference" >/dev/null 2>&1
	else
		"$CONTAINER_RUNTIME" run --rm "$COSIGN_IMAGE" verify \
			--certificate-oidc-issuer "$issuer" \
			--certificate-identity "$identity" "$reference" >/dev/null 2>&1
	fi
}

record() {
	local outcome="$1" description="$2"
	if [ "$outcome" = "ok" ]; then
		printf 'ok    %s\n' "$description"
		passed=$((passed + 1))
	else
		printf 'FAIL  %s\n' "$description"
		failed=$((failed + 1))
	fi
}

main() {
	PYTHON="$(resolve_python)" || {
		printf 'REFUSED: a Python 3 interpreter is required\n' >&2
		exit 2
	}
	command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1 || {
		printf 'REFUSED: %s is required\n' "$CONTAINER_RUNTIME" >&2
		exit 2
	}

	local repository index issuer identity
	repository="$(lock_get acquisition.imageRepository)"
	index="$(lock_get acquisition.indexDigest)"
	issuer="$(lock_get acquisition.signature.certificateOidcIssuer)"
	identity="$(lock_get acquisition.signature.certificateIdentity)"

	printf 'Testing signature verification for %s@%s\n\n' "$repository" "$index"

	# The control. Everything below is meaningless if the real signature does not
	# verify against the recorded identity and issuer.
	if cosign_verify "${repository}@${index}" "$issuer" "$identity"; then
		record ok "the recorded digest verifies against the recorded identity"
	else
		record fail "the recorded digest verifies against the recorded identity"
	fi

	# A different repository's workflow. This is the case that matters most: it is
	# what an attacker who obtained push access to the personal namespace, but not
	# the organization's workflow identity, would be unable to satisfy.
	if cosign_verify "${repository}@${index}" "$issuer" \
		"https://github.com/datopsis/seaweedfs-ubi/.github/workflows/ci.yml@refs/heads/main"; then
		record fail "a signature from a different workflow identity is refused"
	else
		record ok "a signature from a different workflow identity is refused"
	fi

	# The right workflow, the wrong ref. Catches a signature produced by a branch
	# build or a different release being accepted for this one.
	if cosign_verify "${repository}@${index}" "$issuer" \
		"https://github.com/seaweedfs/seaweedfs/.github/workflows/container_release_unified.yml@refs/heads/master"; then
		record fail "a signature for a different git ref is refused"
	else
		record ok "a signature for a different git ref is refused"
	fi

	# A non-GitHub issuer, so the issuer is proven to be checked and not ignored.
	if cosign_verify "${repository}@${index}" "https://accounts.google.com" "$identity"; then
		record fail "a signature from a different OIDC issuer is refused"
	else
		record ok "a signature from a different OIDC issuer is refused"
	fi

	# An unsigned digest in the same repository. The tarball-era images and any
	# unsigned push would look like this.
	local unsigned="sha256:0000000000000000000000000000000000000000000000000000000000000000"
	if cosign_verify "${repository}@${unsigned}" "$issuer" "$identity"; then
		record fail "a digest with no signature is refused"
	else
		record ok "a digest with no signature is refused"
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
