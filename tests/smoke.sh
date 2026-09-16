#!/usr/bin/env bash
#
# Exercise the built image under the restricted runtime it is designed for.
#
# Every run here uses a read-only root filesystem, all capabilities dropped, and
# no-new-privileges. That is not a hardening flourish for the test: if the image
# only works without those, it does not meet its contract, and the suite should
# say so rather than quietly relaxing them.
#
# The listener assertion exists because this image once shipped the standalone
# profile with an Iceberg catalog and a Lance namespace server listening, while
# the documentation said both were disabled. The entrypoint disabled them for the
# s3 role and missed mini's differently named flags. Reading the open ports out
# of a running container is the only check that would have caught it, so it is
# measured here rather than inferred from the entrypoint's source.
#
# Usage:
#   tests/smoke.sh
#
# Environment:
#   CONTAINER_RUNTIME  podman (default) or docker
#   IMAGE              image under test (default localhost/seaweedfs-ubi:development)
#   LOCK_FILE          lock path (default artifacts/seaweedfs.lock.json)

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${LOCK_FILE:-${REPO_ROOT}/artifacts/seaweedfs.lock.json}"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"

# Container arguments like /data are absolute paths to the container and must
# reach it untouched, but Git Bash rewrites them into Windows paths. Scope the
# suppression to container calls only: applying it globally would also break the
# Python invocations below, which need ordinary shell paths. Both variables are
# inert on Linux.
runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)
CONTAINER="seaweedfs-ubi-smoke-$$"
VOLUME="seaweedfs-ubi-smoke-$$"

PYTHON=""
passed=0
failed=0

cleanup() {
	runtime rm -f "$CONTAINER" >/dev/null 2>&1 || true
	runtime volume rm -f "$VOLUME" >/dev/null 2>&1 || true
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

lock_get() {
	"$PYTHON" - "$LOCK_FILE" "$1" <<-'PYTHON'
		import json, sys
		data = json.load(open(sys.argv[1], encoding="utf-8"))
		for part in sys.argv[2].split("."):
		    data = data[part]
		print("" if data is None else data)
	PYTHON
}

ok() {
	printf 'ok    %s\n' "$1"
	passed=$((passed + 1))
}

bad() {
	printf 'FAIL  %s\n' "$1"
	shift
	while [ "$#" -gt 0 ]; do
		printf '      %s\n' "$1"
		shift
	done
	failed=$((failed + 1))
}

# A guard passes only when it refuses with EX_CONFIG *and* says why. A refusal
# for an unrelated reason is a different bug wearing the same exit status.
#
# Arguments before a literal -- are runtime flags and must precede the image;
# arguments after it are the container's own and must follow it. Getting that
# order wrong makes the runtime treat a role name as an image and try to pull it,
# which hangs rather than fails, so the split is explicit.
expect_refusal() {
	local description="$1" expected="$2"
	shift 2

	local flags=() args=() seen_separator=false argument
	for argument in "$@"; do
		if [ "$argument" = "--" ] && [ "$seen_separator" = false ]; then
			seen_separator=true
			continue
		fi
		if [ "$seen_separator" = true ]; then
			args+=("$argument")
		else
			flags+=("$argument")
		fi
	done

	local output status
	set +e
	output="$(runtime run --rm "${RESTRICTED[@]}" ${flags[@]+"${flags[@]}"} \
		"$IMAGE" ${args[@]+"${args[@]}"} 2>&1)"
	status=$?
	set -e
	if [ "$status" -ne 78 ]; then
		bad "$description" "expected exit 78 (EX_CONFIG), got ${status}" "${output}"
		return
	fi
	if ! printf '%s' "$output" | grep -qi -- "$expected"; then
		bad "$description" "refused, but the diagnostic did not mention: ${expected}" "${output}"
		return
	fi
	ok "$description"
}

listening_ports() {
	runtime exec "$CONTAINER" cat /proc/net/tcp /proc/net/tcp6 2>/dev/null |
		awk '$4=="0A" {split($2,a,":"); print strtonum("0x" a[2])}' | sort -n -u
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
	runtime image exists "$IMAGE" 2>/dev/null || {
		printf 'REFUSED: %s does not exist. Run scripts/build.sh first.\n' "$IMAGE" >&2
		exit 2
	}

	local version variant commit marker
	version="$(lock_get upstream.releaseTag)"
	variant="$(lock_get variant.name)"
	commit="$(lock_get upstream.releaseCommit)"
	marker="$(lock_get variant.versionMarker)"

	printf 'Smoke testing %s (SeaweedFS %s, %s)\n\n' "$IMAGE" "$version" "$variant"

	# ---- identity and provenance -------------------------------------------
	local reported
	reported="$(runtime run --rm "${RESTRICTED[@]}" "$IMAGE" version 2>&1 | head -1)"
	if [ "${reported#*"$version"}" != "$reported" ] &&
		[ "${reported#*"$marker"}" != "$reported" ] &&
		[ "${reported#*"${commit:0:9}"}" != "$reported" ]; then
		ok "the image reports the locked version, variant and commit"
	else
		bad "the image reports the locked version, variant and commit" \
			"wanted ${version}, ${marker} and ${commit:0:9} in: ${reported}"
	fi

	# ---- the role allowlist -------------------------------------------------
	expect_refusal "no role is refused with usage" "no role given"
	expect_refusal "an unsupported role is refused" "is not a role this image supports" -- server
	expect_refusal "the mount role is refused" "is not a role this image supports" -- mount
	expect_refusal "webdav is refused" "is not a role this image supports" -- webdav

	# ---- the data directory guard -------------------------------------------
	expect_refusal "master without -mdir is refused" "without -mdir" -- master
	expect_refusal "volume without -dir is refused" "without -dir" -- volume
	expect_refusal "a temporary data directory is refused" "temporary path" -- master -mdir=/tmp

	# ---- the S3 authentication guard ----------------------------------------
	expect_refusal "s3 without an identity source is refused" "no S3 identity source" -- s3
	expect_refusal "s3 with a missing config file is refused" "does not exist" \
		-- s3 -config=/nonexistent/s3.json

	# ---- the plaintext-beside-TLS guard -------------------------------------
	expect_refusal "s3 refuses a plaintext listener beside TLS" "serving plaintext" \
		-e AWS_ACCESS_KEY_ID=smoke-key -e AWS_SECRET_ACCESS_KEY=smoke-secret \
		-- s3 -cert.file=/tls/server.crt -key.file=/tls/server.key -port.https=8334
	expect_refusal "mini refuses a plaintext listener beside TLS" "serving plaintext" \
		-e SEAWEEDFS_UBI_STANDALONE=true \
		-e AWS_ACCESS_KEY_ID=smoke-key -e AWS_SECRET_ACCESS_KEY=smoke-secret \
		-- mini -dir=/data -s3.cert.file=/tls/server.crt \
		-s3.key.file=/tls/server.key -s3.port.https=8334

	# ---- the standalone gate -------------------------------------------------
	expect_refusal "mini without the standalone opt-in is refused" "not enabled" -- mini -dir=/data

	# ---- toggles fail closed --------------------------------------------------
	expect_refusal "an unrecognised boolean is refused, not ignored" "not true or false" \
		-e SEAWEEDFS_UBI_REQUIRE_S3_AUTH=yes -- s3
	expect_refusal "the TLS opt-out also rejects an unrecognised boolean" "not true or false" \
		-e SEAWEEDFS_UBI_ALLOW_PLAINTEXT_BESIDE_TLS=yes -- version

	# ---- opting out is honoured, so the guard is a control and not a wall -----
	#
	# This one starts a server rather than being refused, so it runs detached.
	# Running it in the foreground would block until the master exits, which it
	# never does. A tmpfs is mounted because the point is to reach the state the
	# guard would have prevented, not to test whether /tmp is writable.
	local optout="${CONTAINER}-optout"
	runtime run -d --name "$optout" "${RESTRICTED[@]}" --tmpfs /tmp \
		-e SEAWEEDFS_UBI_REQUIRE_EXPLICIT_DATA_DIR=false \
		"$IMAGE" master -mdir=/tmp >/dev/null 2>&1 || true
	sleep 5
	local optout_code
	optout_code="$(runtime inspect "$optout" --format '{{.State.ExitCode}}' 2>/dev/null || printf 'unknown')"
	runtime rm -f "$optout" >/dev/null 2>&1 || true
	if [ "$optout_code" != "78" ]; then
		ok "the data directory guard can be turned off deliberately"
	else
		bad "the data directory guard can be turned off deliberately" \
			"it still refused with EX_CONFIG when opted out"
	fi

	# ---- a real run under the restricted runtime ------------------------------
	runtime volume create "$VOLUME" >/dev/null
	runtime run -d --name "$CONTAINER" "${RESTRICTED[@]}" \
		-v "${VOLUME}:/data" \
		-e SEAWEEDFS_UBI_STANDALONE=true \
		-e AWS_ACCESS_KEY_ID=smoke-key \
		-e AWS_SECRET_ACCESS_KEY=smoke-secret \
		"$IMAGE" mini -dir=/data >/dev/null

	local waited=0
	while [ "$waited" -lt 60 ]; do
		if listening_ports | grep -qx 8333; then break; fi
		sleep 2
		waited=$((waited + 2))
	done

	if listening_ports | grep -qx 8333; then
		ok "the standalone profile starts on a read-only root with no capabilities"
	else
		bad "the standalone profile starts on a read-only root with no capabilities" \
			"$(runtime logs "$CONTAINER" 2>&1 | tail -5)"
	fi

	local cmdline
	cmdline="$(runtime exec "$CONTAINER" cat /proc/1/cmdline 2>/dev/null | tr '\0' ' ')"
	case "$cmdline" in
	*/weed*)
		ok "the entrypoint execs, so the server is PID 1 and receives signals directly"
		;;
	*)
		bad "the entrypoint execs, so the server is PID 1 and receives signals directly" \
			"PID 1 is: ${cmdline}"
		;;
	esac

	local identity
	identity="$(runtime exec "$CONTAINER" cat /proc/1/status 2>/dev/null |
		awk '/^Uid:/ {print $2}')"
	if [ -n "$identity" ] && [ "$identity" != "0" ]; then
		ok "the server process runs as a non-root uid (${identity})"
	else
		bad "the server process runs as a non-root uid" "uid is ${identity:-unknown}"
	fi

	# The regression this suite exists for.
	local open_extra=""
	for port in 8181 9101; do
		if listening_ports | grep -qx "$port"; then
			open_extra="${open_extra} ${port}"
		fi
	done
	if [ -z "$open_extra" ]; then
		ok "the Iceberg catalog and Lance namespace listeners are absent"
	else
		bad "the Iceberg catalog and Lance namespace listeners are absent" \
			"these are listening and should not be:${open_extra}" \
			"all open ports: $(listening_ports | tr '\n' ' ')"
	fi

	# No privileged port may be opened, since the runtime grants no capability
	# that would allow it and a deployment must never need one.
	local privileged
	privileged="$(listening_ports | awk '$1 < 1024' | tr '\n' ' ')"
	if [ -z "$privileged" ]; then
		ok "no privileged port is opened"
	else
		bad "no privileged port is opened" "privileged: ${privileged}"
	fi

	# ---- state survives container replacement ---------------------------------
	runtime rm -f "$CONTAINER" >/dev/null 2>&1
	runtime run -d --name "$CONTAINER" "${RESTRICTED[@]}" \
		-v "${VOLUME}:/data" \
		-e SEAWEEDFS_UBI_STANDALONE=true \
		-e AWS_ACCESS_KEY_ID=smoke-key \
		-e AWS_SECRET_ACCESS_KEY=smoke-secret \
		"$IMAGE" mini -dir=/data >/dev/null

	waited=0
	while [ "$waited" -lt 60 ]; do
		if listening_ports | grep -qx 8333; then break; fi
		sleep 2
		waited=$((waited + 2))
	done
	if listening_ports | grep -qx 8333; then
		ok "a replacement container starts against the existing data volume"
	else
		bad "a replacement container starts against the existing data volume" \
			"$(runtime logs "$CONTAINER" 2>&1 | tail -5)"
	fi

	# ---- secrets must not appear in the logs ----------------------------------
	if runtime logs "$CONTAINER" 2>&1 | grep -q 'smoke-secret'; then
		bad "the secret access key does not appear in the logs" \
			"it was found in container output"
	else
		ok "the secret access key does not appear in the logs"
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
