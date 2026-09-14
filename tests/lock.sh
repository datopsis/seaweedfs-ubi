#!/usr/bin/env bash
#
# Prove the artifact lock checker refuses an inconsistent lock.
#
# The lock is what stands between a build and unreviewed bytes. Its dangerous
# failure mode is not a malformed file, which any parser catches, but a
# half-edited one that still parses: a version bumped in the header but not in
# the certificate identity, an architecture updated without its binary digest.
# Each case below is a plausible mistake during a real version bump.
#
# Offline and deterministic. No network, no registry, no container runtime.
#
# Usage:
#   tests/lock.sh

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${LOCK_FILE:-${REPO_ROOT}/artifacts/seaweedfs.lock.json}"
CHECKER="${REPO_ROOT}/.github/scripts/check_artifact_lock.py"

# Resolved in main(); declared here so its scope is obvious.
PYTHON=""

passed=0
failed=0
WORK=""

cleanup() {
	[ -n "$WORK" ] && rm -rf "$WORK"
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

# Produce a copy of the real lock with one edit applied, expressed as a short
# Python snippet operating on `lock`.
mutate() {
	local name="$1" snippet="$2"
	"$PYTHON" - "$LOCK_FILE" "${WORK}/${name}.json" "$snippet" <<-'PYTHON'
		import json, sys
		lock = json.loads(open(sys.argv[1], encoding="utf-8").read())
		exec(sys.argv[3])
		open(sys.argv[2], "w", encoding="utf-8").write(json.dumps(lock, indent=2))
	PYTHON
}

expect_refusal() {
	local description="$1" expected="$2" file="$3"
	local output status
	set +e
	output="$("$PYTHON" "$CHECKER" "$file" 2>&1)"
	status=$?
	set -e
	if [ "$status" -ne 1 ]; then
		printf 'FAIL  %s\n      expected exit 1, got %s\n' "$description" "$status"
		failed=$((failed + 1))
		return
	fi
	if ! printf '%s' "$output" | grep -qi -- "$expected"; then
		printf 'FAIL  %s\n      refused, but not for the expected reason\n      wanted: %s\n      got: %s\n' \
			"$description" "$expected" "$output"
		failed=$((failed + 1))
		return
	fi
	printf 'ok    %s\n' "$description"
	passed=$((passed + 1))
}

main() {
	PYTHON="$(resolve_python)" || {
		printf 'REFUSED: a Python 3 interpreter is required\n' >&2
		exit 2
	}
	[ -f "$LOCK_FILE" ] || {
		printf 'REFUSED: no lock at %s\n' "$LOCK_FILE" >&2
		exit 2
	}

	WORK="$(mktemp -d)"
	printf 'Testing the artifact lock checker against %s\n\n' "$LOCK_FILE"

	# The control.
	if "$PYTHON" "$CHECKER" "$LOCK_FILE" >/dev/null 2>&1; then
		printf 'ok    %s\n' "the committed lock is well formed and self-consistent"
		passed=$((passed + 1))
	else
		printf 'FAIL  %s\n' "the committed lock is well formed and self-consistent"
		failed=$((failed + 1))
	fi

	# The realistic version bump: the header is updated and something else is not.
	mutate tag-only 'lock["upstream"]["releaseTag"] = "9.99"'
	expect_refusal "a release tag bumped without the certificate identity is refused" \
		"certificateIdentity" "${WORK}/tag-only.json"

	mutate commit-only 'lock["upstream"]["releaseCommit"] = "0" * 40'
	expect_refusal "a release commit changed without the architecture entries is refused" \
		"is not a prefix of" "${WORK}/commit-only.json"

	# Contradictions that would let the gate enforce something impossible.
	mutate static-with-libs \
		'lock["architectures"]["arm64"]["binary"]["neededLibraries"] = ["libc.so.6"]'
	expect_refusal "a statically linked binary that also needs libraries is refused" \
		"cannot both be true" "${WORK}/static-with-libs.json"

	mutate static-with-glibc \
		'lock["architectures"]["arm64"]["binary"]["glibcMinimumVersion"] = "2.34"'
	expect_refusal "a statically linked binary with a glibc floor is refused" \
		"no glibc requirement" "${WORK}/static-with-glibc.json"

	# A copy-paste between architecture entries.
	mutate duplicate-binary \
		'lock["architectures"]["arm64"]["binary"]["sha256"] = lock["architectures"]["amd64"]["binary"]["sha256"]'
	expect_refusal "two architectures sharing one binary digest is refused" \
		"cannot share one binary" "${WORK}/duplicate-binary.json"

	mutate duplicate-manifest \
		'lock["architectures"]["arm64"]["manifestDigest"] = lock["architectures"]["amd64"]["manifestDigest"]'
	expect_refusal "two architectures sharing one manifest digest is refused" \
		"cannot share one manifest" "${WORK}/duplicate-manifest.json"

	# Shape problems that would weaken a check rather than break it.
	mutate short-commit 'lock["upstream"]["releaseCommit"] = "d997fba15"'
	expect_refusal "a short release commit is refused" \
		"40-character commit" "${WORK}/short-commit.json"

	mutate blank-marker 'lock["variant"]["versionMarker"] = ""'
	expect_refusal "a blank variant marker is refused" \
		"versionMarker" "${WORK}/blank-marker.json"

	mutate uppercase-digest \
		'lock["architectures"]["amd64"]["binary"]["sha256"] = lock["architectures"]["amd64"]["binary"]["sha256"].upper()'
	expect_refusal "an uppercase digest is refused" \
		"lowercase" "${WORK}/uppercase-digest.json"

	mutate platform-mismatch \
		'lock["architectures"]["arm64"]["platform"] = "linux/amd64"'
	expect_refusal "an architecture whose platform disagrees with its key is refused" \
		"but the key is" "${WORK}/platform-mismatch.json"

	mutate unknown-schema 'lock["schemaVersion"] = 99'
	expect_refusal "an unsupported schema version is refused rather than assumed" \
		"reviewed checker update" "${WORK}/unknown-schema.json"

	mutate missing-key 'del lock["variant"]["versionMarker"]'
	expect_refusal "a missing required key is refused" \
		"missing key" "${WORK}/missing-key.json"

	printf '{ not json' >"${WORK}/broken.json"
	expect_refusal "an unparseable lock is refused" \
		"not valid JSON" "${WORK}/broken.json"

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
