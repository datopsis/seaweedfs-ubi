#!/usr/bin/env bash
#
# Prove the admission gate refuses bad input.
#
# A gate that has never been observed refusing is not known to refuse, so every
# check in scripts/lib/verify.py gets a negative case here. These cases are
# offline and deterministic: they operate on copies of an already-admitted
# binary, so the suite needs no network and no registry.
#
# Signature verification is covered separately, because it needs cosign and a
# registry. Run tests/acquisition-signature.sh for that.
#
# Usage:
#   tests/acquisition.sh [path-to-an-admitted-weed-binary]
#
# With no argument it uses .artifact-bundle/<host arch>/weed, so the usual
# sequence is scripts/fetch-artifacts.sh followed by this.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${LOCK_FILE:-${REPO_ROOT}/artifacts/seaweedfs.lock.json}"
VERIFY="${REPO_ROOT}/scripts/lib/verify.py"
BUNDLE_DIR="${BUNDLE_DIR:-${REPO_ROOT}/.artifact-bundle}"

# Resolved in main(); declared here so its scope is obvious.
PYTHON=""

passed=0
failed=0
WORK=""

cleanup() {
	[ -n "$WORK" ] && rm -rf "$WORK"
}
trap cleanup EXIT

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

host_arch() {
	case "$(uname -m)" in
	x86_64 | amd64) printf 'amd64' ;;
	aarch64 | arm64) printf 'arm64' ;;
	*) printf '%s' "$(uname -m)" ;;
	esac
}

# A case passes when the gate refuses with status 1 and its diagnostic mentions
# the thing that was wrong. Refusing for an unrelated reason is not a pass.
expect_refusal() {
	local description="$1" expected="$2" arch="$3" file="$4"
	local output status
	set +e
	output="$("$PYTHON" "$VERIFY" "$LOCK_FILE" "$arch" "$file" 2>&1)"
	status=$?
	set -e
	if [ "$status" -ne 1 ]; then
		printf 'FAIL  %s\n      expected exit 1, got %s\n' "$description" "$status"
		failed=$((failed + 1))
		return
	fi
	if ! printf '%s' "$output" | grep -qi -- "$expected"; then
		printf 'FAIL  %s\n      refused, but the diagnostic did not mention %s\n      got: %s\n' \
			"$description" "$expected" "$output"
		failed=$((failed + 1))
		return
	fi
	printf 'ok    %s\n' "$description"
	passed=$((passed + 1))
}

expect_admission() {
	local description="$1" arch="$2" file="$3"
	if "$PYTHON" "$VERIFY" "$LOCK_FILE" "$arch" "$file" >/dev/null 2>&1; then
		printf 'ok    %s\n' "$description"
		passed=$((passed + 1))
	else
		printf 'FAIL  %s\n      expected admission, got a refusal\n' "$description"
		failed=$((failed + 1))
	fi
}

main() {
	local arch source
	arch="$(host_arch)"
	source="${1:-${BUNDLE_DIR}/${arch}/weed}"

	if [ ! -f "$source" ]; then
		printf 'REFUSED: no admitted binary at %s\n' "$source" >&2
		printf 'Run scripts/fetch-artifacts.sh first, or pass a path.\n' >&2
		exit 2
	fi

	PYTHON="$(resolve_python)" || {
		printf 'REFUSED: a Python 3 interpreter is required and was not found as python3 or python\n' >&2
		exit 2
	}

	WORK="$(mktemp -d)"
	printf 'Testing the admission gate for %s against %s\n\n' "$arch" "$source"

	# The control. If this fails, every refusal below is meaningless.
	expect_admission "an unmodified admitted binary is accepted" "$arch" "$source"

	# A single flipped byte in the middle, leaving the size unchanged, so this
	# isolates the digest check rather than also tripping the size check.
	cp -- "$source" "${WORK}/tampered"
	"$PYTHON" - "${WORK}/tampered" <<-'PYTHON'
		import sys
		path = sys.argv[1]
		with open(path, "r+b") as handle:
		    handle.seek(1024 * 1024)
		    original = handle.read(1)
		    handle.seek(1024 * 1024)
		    handle.write(bytes([original[0] ^ 0xFF]))
	PYTHON
	expect_refusal "a tampered binary of the correct size is refused" \
		"SHA-256 mismatch" "$arch" "${WORK}/tampered"

	# Truncation, which a partial or interrupted download produces.
	head -c 1048576 -- "$source" >"${WORK}/truncated"
	expect_refusal "a truncated download is refused" \
		"size mismatch" "$arch" "${WORK}/truncated"

	# Extra trailing bytes, which an appended payload produces.
	cp -- "$source" "${WORK}/extended"
	printf 'appended' >>"${WORK}/extended"
	expect_refusal "a binary with appended bytes is refused" \
		"size mismatch" "$arch" "${WORK}/extended"

	# The wrong architecture's entry, which catches a bundle assembled for one
	# architecture being admitted as another.
	case "$arch" in
	amd64) other="arm64" ;;
	*) other="amd64" ;;
	esac
	expect_refusal "a binary offered as the wrong architecture is refused" \
		"mismatch" "$other" "$source"

	# An architecture the lock says nothing about.
	expect_refusal "an architecture absent from the lock is refused" \
		"no entry for architecture" "riscv64" "$source"

	# Something that is not an ELF binary at all, such as an error page saved
	# over the download.
	printf '<html><body>404 Not Found</body></html>' >"${WORK}/notelf"
	expect_refusal "a non-ELF file is refused" \
		"size mismatch" "$arch" "${WORK}/notelf"

	# A missing file, rather than a wrong one.
	expect_refusal "a missing file is refused" \
		"does not exist" "$arch" "${WORK}/absent"

	# A lock that does not parse must fail closed rather than admitting anything.
	printf '{ this is not json' >"${WORK}/broken.json"
	local output status
	set +e
	output="$(LOCK_FILE="${WORK}/broken.json" "$PYTHON" "$VERIFY" "${WORK}/broken.json" "$arch" "$source" 2>&1)"
	status=$?
	set -e
	if [ "$status" -eq 1 ] && printf '%s' "$output" | grep -qi 'cannot read the artifact lock'; then
		printf 'ok    %s\n' "an unparseable lock is refused"
		passed=$((passed + 1))
	else
		printf 'FAIL  %s\n      got exit %s: %s\n' "an unparseable lock is refused" "$status" "$output"
		failed=$((failed + 1))
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
