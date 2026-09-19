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
		"$PYTHON" "${REPO_ROOT}/tests/lib/listening_ports.py" | tr -d '\r'
}

admin_http_status() {
	local path="$1"
	# Query from inside the container: the admin port must never be published
	# merely to make this assertion. Bash is already the image's entrypoint.
	# The quoted script expands $1 in the container, not on the host.
	# shellcheck disable=SC2016
	runtime exec "$CONTAINER" bash -c '
		exec 3<>/dev/tcp/127.0.0.1/23646 || exit 1
		printf "GET %s HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n" "$1" >&3
		IFS= read -r status <&3
		printf "%s\n" "$status"
	' bash "$path" 2>/dev/null | tr -d '\r'
}

# Requirements: L2-CFG-003 L3-RUN-001 L3-RUN-002 L3-CFG-001 L3-CFG-002
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
	local reported status
	set +e
	reported="$(runtime run --rm "${RESTRICTED[@]}" "$IMAGE" version 2>&1)"
	status=$?
	set -e
	if [ "$status" -ne 0 ]; then
		bad "the image starts and reports its version" \
			"runtime exited ${status}: ${reported}"
		printf '\n%s passed, %s failed\n' "$passed" "$failed"
		exit 1
	fi
	reported="${reported%%$'\n'*}"
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
	expect_refusal "filer cannot embed an unauthenticated S3 gateway" "embedded s3 service" \
		-- filer -s3=true
	expect_refusal "filer cannot embed WebDAV" "embedded webdav service" \
		-- filer -webdav
	expect_refusal "filer cannot embed IAM" "embedded iam service" \
		-- filer -iam=1
	expect_refusal "filer cannot embed SFTP" "embedded sftp service" \
		-- filer -sftp=true
	expect_refusal "filer cannot embed SFTP using a long flag" "embedded sftp service" \
		-- filer --sftp=true
	expect_refusal "a later SFTP enable cannot override a disable" "embedded sftp service" \
		-- filer -sftp=false -sftp=true

	# ---- the data directory guard -------------------------------------------
	expect_refusal "master without -mdir is refused" "without -mdir" -- master
	expect_refusal "volume without -dir is refused" "without -dir" -- volume
	expect_refusal "a temporary data directory is refused" "temporary path" -- master -mdir=/tmp

	# ---- the S3 authentication guard ----------------------------------------
	expect_refusal "s3 without an identity source is refused" "no S3 identity source" -- s3
	expect_refusal "s3 with a missing config file is refused" "does not exist" \
		-- s3 -config=/nonexistent/s3.json
	expect_refusal "mini with standalone enabled but no S3 identity is refused" \
		"no S3 identity source" -e SEAWEEDFS_UBI_STANDALONE=true \
		-- mini -dir=/data

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
	expect_refusal "mini cannot enable the Admin UI" "outside this image's supported boundary" \
		-e SEAWEEDFS_UBI_STANDALONE=true -e AWS_ACCESS_KEY_ID=smoke-key \
		-e AWS_SECRET_ACCESS_KEY=smoke-secret -- mini -dir=/data -admin.ui=true
	expect_refusal "mini cannot enable WebDAV using a later duplicate flag" "outside this image's supported boundary" \
		-e SEAWEEDFS_UBI_STANDALONE=true -e AWS_ACCESS_KEY_ID=smoke-key \
		-e AWS_SECRET_ACCESS_KEY=smoke-secret -- mini -dir=/data -webdav=false --webdav=true

	# ---- toggles fail closed --------------------------------------------------
	expect_refusal "an unrecognised boolean is refused, not ignored" "not true or false" \
		-e SEAWEEDFS_UBI_REQUIRE_S3_AUTH=yes -- s3
	expect_refusal "the TLS opt-out also rejects an unrecognised boolean" "not true or false" \
		-e SEAWEEDFS_UBI_ALLOW_PLAINTEXT_BESIDE_TLS=yes -- version
	expect_refusal "an unknown log format is refused" "not supported" \
		-e SEAWEEDFS_UBI_LOG_FORMAT=xml -- version

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
	if [[ " $cmdline " == *" -webdav=false "* && " $cmdline " == *" -admin.ui=false "* ]]; then
		ok "standalone disables WebDAV and the Admin UI by default"
	else
		bad "standalone disables WebDAV and the Admin UI by default" \
			"expected explicit disable flags in PID 1: $cmdline"
	fi

	local identity
	identity="$(runtime exec "$CONTAINER" cat /proc/1/status 2>/dev/null |
		awk '/^Uid:/ {print $2}')"
	if [ -n "$identity" ] && [ "$identity" != "0" ]; then
		ok "the server process runs as a non-root uid (${identity})"
	else
		bad "the server process runs as a non-root uid" "uid is ${identity:-unknown}"
	fi

	local effective_capabilities readonly_root
	effective_capabilities="$(runtime exec "$CONTAINER" cat /proc/1/status 2>/dev/null |
		awk '/^CapEff:/ {print $2}')"
	readonly_root="$(runtime inspect "$CONTAINER" --format '{{.HostConfig.ReadonlyRootfs}}' 2>/dev/null || true)"
	if [ "$effective_capabilities" = "0000000000000000" ] && [ "$readonly_root" = true ]; then
		ok "the running process has zero effective capabilities under a read-only root"
	else
		bad "the running process has zero effective capabilities under a read-only root" \
			"CapEff=${effective_capabilities:-unknown}, ReadonlyRootfs=${readonly_root:-unknown}"
	fi

	# Pin the actual mini listener set. The Admin UI is off, but upstream still
	# opens admin health/metrics HTTP and worker gRPC listeners.
	local actual_ports expected_ports
	actual_ports="$(listening_ports | tr '\n' ' ' | sed 's/ $//')"
	expected_ports="8333 8888 9333 9340 18333 18888 19333 19340 23646 33646"
	if [ "$actual_ports" = "$expected_ports" ]; then
		ok "standalone opens exactly its documented listeners"
	else
		bad "standalone opens exactly its documented listeners" \
			"expected: $expected_ports; actual: $actual_ports"
	fi
	local health_status api_status
	health_status="$(admin_http_status /health || true)"
	api_status="$(admin_http_status /api/cluster/topology || true)"
	if [[ "$health_status" == *" 200 "* && "$api_status" == *" 404 "* ]]; then
		ok "mini admin health remains live but management API routes are absent"
	else
		bad "mini admin health remains live but management API routes are absent" \
			"health: ${health_status:-no response}; API: ${api_status:-no response}"
	fi

	# Keep focused diagnostics for the two previously exposed services.
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
	local logs
	logs="$(runtime logs "$CONTAINER" 2>&1)"
	if printf '%s\n' "$logs" | "$PYTHON" -c '
import json, sys
records = []
for line in sys.stdin:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(record, dict):
        records.append(record)
raise SystemExit(0 if records else 1)
'; then
		ok "server logs use the default structured JSON profile"
	else
		bad "server logs use the default structured JSON profile" \
			"no JSON object was found in the server log"
	fi
	if printf '%s\n' "$logs" | grep -q 'smoke-secret'; then
		bad "the secret access key does not appear in the logs" \
			"it was found in container output"
	else
		ok "the secret access key does not appear in the logs"
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
