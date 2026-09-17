#!/usr/bin/env bash
# Prove assembly refuses altered inputs before it can invoke a container build.
# The runtime shim records commands; the native CI job separately performs the
# real offline Podman build and image qualification on each architecture.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_DIR="${BUNDLE_DIR:-${REPO_ROOT}/.artifact-bundle}"
LOCK_FILE="${LOCK_FILE:-${REPO_ROOT}/artifacts/seaweedfs.lock.json}"
WORK=""
passed=0
failed=0

cleanup() {
	[ -n "$WORK" ] && rm -rf -- "$WORK"
}
trap cleanup EXIT

host_arch() {
	case "$(uname -m)" in
	x86_64 | amd64) printf 'amd64' ;;
	aarch64 | arm64) printf 'arm64' ;;
	*) printf 'unsupported host architecture: %s\n' "$(uname -m)" >&2; return 1 ;;
	esac
}

ok() { printf 'ok    %s\n' "$1"; passed=$((passed + 1)); }
bad() { printf 'FAIL  %s\n      %s\n' "$1" "$2"; failed=$((failed + 1)); }

expect_refusal() {
	local description="$1" diagnostic="$2" bundle="$3" lock="$4" missing_base="$5"
	local output status
	: >"$WORK/calls"
	set +e
	output="$(BUNDLE_DIR="$bundle" LOCK_FILE="$lock" ASSEMBLY_MISSING_BASE="$missing_base" \
		CONTAINER_RUNTIME=podman PATH="$WORK/bin:$PATH" \
		bash "$REPO_ROOT/scripts/build-image.sh" "$arch" 2>&1)"
	status=$?
	set -e
	if [ "$status" -ne 1 ] || ! printf '%s\n' "$output" | grep -Fqi -- "$diagnostic"; then
		bad "$description" "expected exit 1 and '$diagnostic'; got exit $status: $output"
	elif grep -q '^build ' "$WORK/calls"; then
		bad "$description" "a container build was invoked after refusal"
	else
		ok "$description"
	fi
}

main() {
	arch="$(host_arch)" || exit 2
	local source="${BUNDLE_DIR}/${arch}/weed"
	[ -f "$source" ] || {
		printf 'REFUSED: no admitted binary at %s\n' "$source" >&2
		exit 2
	}
	WORK="$(mktemp -d)"
	mkdir -p "$WORK/bin" "$WORK/tampered/$arch"
	# The shim never contacts a registry or starts a container. It can simulate
	# an absent pinned base after the binary has passed re-verification.
	cat >"$WORK/bin/podman" <<'SHIM'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$ASSEMBLY_CALLS"
case "$1 $2" in
"image exists") [ "${ASSEMBLY_MISSING_BASE:-false}" != true ] ;;
"image inspect") exit 0 ;;
"build "*) exit 0 ;;
*) exit 99 ;;
esac
SHIM
	chmod +x "$WORK/bin/podman"
	export ASSEMBLY_CALLS="$WORK/calls"

	expect_refusal "a missing bundle is refused before runtime access" \
		"no verified binary" "$WORK/absent" "$LOCK_FILE" false
	[ ! -s "$WORK/calls" ] || bad "a missing bundle avoids runtime access" "runtime was called"

	cp -- "$source" "$WORK/tampered/$arch/weed"
	python3 - "$WORK/tampered/$arch/weed" <<'PYTHON'
import sys
with open(sys.argv[1], "r+b") as handle:
    handle.seek(1024 * 1024)
    value = handle.read(1)
    handle.seek(1024 * 1024)
    handle.write(bytes([value[0] ^ 0xFF]))
PYTHON
	expect_refusal "a changed bundle is refused before runtime access" \
		"bundle does not match the lock" "$WORK/tampered" "$LOCK_FILE" false
	[ ! -s "$WORK/calls" ] || bad "a changed bundle avoids runtime access" "runtime was called"

	python3 - "$LOCK_FILE" "$WORK/changed-lock.json" "$arch" <<'PYTHON'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    lock = json.load(handle)
lock["architectures"][sys.argv[3]]["binary"]["sha256"] = "0" * 64
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(lock, handle)
PYTHON
	expect_refusal "a changed lock is refused before runtime access" \
		"bundle does not match the lock" "$BUNDLE_DIR" "$WORK/changed-lock.json" false
	[ ! -s "$WORK/calls" ] || bad "a changed lock avoids runtime access" "runtime was called"

	expect_refusal "an unavailable pinned base is refused without building" \
		"base image not present locally" "$BUNDLE_DIR" "$LOCK_FILE" true

	: >"$WORK/calls"
	if BUNDLE_DIR="$BUNDLE_DIR" LOCK_FILE="$LOCK_FILE" ASSEMBLY_MISSING_BASE=false \
		CONTAINER_RUNTIME=podman PATH="$WORK/bin:$PATH" \
		bash "$REPO_ROOT/scripts/build-image.sh" "$arch" >"$WORK/output" 2>&1 &&
		grep -Fq -- '--network=none' "$WORK/calls" &&
		grep -Fq -- '--pull=never' "$WORK/calls" &&
		grep -Fq -- "--build-context weed=${BUNDLE_DIR}/${arch}" "$WORK/calls" &&
		[ "$(grep -c '^build ' "$WORK/calls")" -eq 1 ]; then
		ok "an admitted bundle reaches one offline, no-pull build invocation"
	else
		bad "an admitted bundle reaches one offline, no-pull build invocation" \
			"the build command or required flags were missing; see $WORK/output"
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ]
}

main "$@"
