#!/usr/bin/env bash
#
# Bring up the separated-role topology and assert what only it can prove.
#
# The standalone profile in tests/smoke.sh is faster and covers functional
# behaviour and the guards. It cannot cover any of this, because inside one
# process there is no network between the roles: discovery, addressing, and the
# per-role listener sets simply do not exist there. That is why both fixtures
# exist rather than one.
#
# This is also the harness work package 4 extends for the S3 and Iceberg round
# trips, so it is built to be reused: --keep leaves the cluster running and
# prints how to reach it.
#
# Usage:
#   tests/cluster.sh [--keep]
#
# Environment:
#   CONTAINER_RUNTIME  podman (default) or docker
#   IMAGE              image under test (default localhost/seaweedfs-ubi:development)

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${LOCK_FILE:-${REPO_ROOT}/artifacts/seaweedfs.lock.json}"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"

# Container arguments are absolute paths inside the container and must arrive
# untouched; Git Bash would rewrite them. Inert on Linux.
runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)

SUFFIX="$$"
NETWORK="seaweedfs-ubi-net-${SUFFIX}"
MASTER="seaweedfs-ubi-master-${SUFFIX}"
VOLUME_ROLE="seaweedfs-ubi-volume-${SUFFIX}"
FILER="seaweedfs-ubi-filer-${SUFFIX}"
S3="seaweedfs-ubi-s3-${SUFFIX}"
VOLUMES=("vol-master-${SUFFIX}" "vol-volume-${SUFFIX}" "vol-filer-${SUFFIX}")

KEEP=false
[ "${1:-}" = "--keep" ] && KEEP=true

passed=0
failed=0

cleanup() {
	[ "$KEEP" = true ] && return 0
	local name
	for name in "$S3" "$FILER" "$VOLUME_ROLE" "$MASTER"; do
		runtime rm -f "$name" >/dev/null 2>&1 || true
	done
	for name in "${VOLUMES[@]}"; do
		runtime volume rm -f "$name" >/dev/null 2>&1 || true
	done
	runtime network rm -f "$NETWORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT

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

listening_ports() {
	runtime exec "$1" cat /proc/net/tcp /proc/net/tcp6 2>/dev/null |
		awk '$4=="0A" {split($2,a,":"); print strtonum("0x" a[2])}' | sort -n -u
}

wait_for_port() {
	local container="$1" port="$2" waited=0
	while [ "$waited" -lt 90 ]; do
		if listening_ports "$container" | grep -qx "$port"; then return 0; fi
		if [ "$(runtime inspect "$container" --format '{{.State.Status}}' 2>/dev/null)" = "exited" ]; then
			return 1
		fi
		sleep 2
		waited=$((waited + 2))
	done
	return 1
}

start_role() {
	local name="$1" volume="$2"
	shift 2
	runtime run -d --name "$name" --network "$NETWORK" --network-alias "$name" \
		"${RESTRICTED[@]}" \
		${volume:+-v "${volume}:/data"} \
		"$@" >/dev/null
}

# Exactly the ports a role should open, and nothing more. An upstream release
# that starts something new fails here rather than shipping.
assert_listeners() {
	local description="$1" container="$2" expected="$3"
	local actual
	actual="$(listening_ports "$container" | tr '\n' ' ' | sed 's/ $//')"
	if [ "$actual" = "$expected" ]; then
		ok "$description"
	else
		bad "$description" "expected: ${expected}" "actual:   ${actual}"
	fi
}

main() {
	command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1 || {
		printf 'REFUSED: %s is required\n' "$CONTAINER_RUNTIME" >&2
		exit 2
	}
	runtime image exists "$IMAGE" 2>/dev/null || {
		printf 'REFUSED: %s does not exist. Run scripts/build.sh first.\n' "$IMAGE" >&2
		exit 2
	}

	printf 'Bringing up the separated-role topology from %s\n\n' "$IMAGE"

	runtime network create "$NETWORK" >/dev/null
	local name
	for name in "${VOLUMES[@]}"; do
		runtime volume create "$name" >/dev/null
	done

	# Each role in its own container, addressed by name over a real network.
	# None of this is exercised by the standalone profile.
	start_role "$MASTER" "${VOLUMES[0]}" "$IMAGE" \
		master -mdir=/data -ip="$MASTER"
	if wait_for_port "$MASTER" 9333; then
		ok "the master starts and listens"
	else
		bad "the master starts and listens" "$(runtime logs "$MASTER" 2>&1 | tail -5)"
		printf '\n%s passed, %s failed\n' "$passed" "$failed"
		exit 1
	fi

	start_role "$VOLUME_ROLE" "${VOLUMES[1]}" "$IMAGE" \
		volume -dir=/data -ip="$VOLUME_ROLE" -mserver="${MASTER}:9333" -max=4
	if wait_for_port "$VOLUME_ROLE" 8080; then
		ok "the volume server starts and registers with the master over the network"
	else
		bad "the volume server starts and registers with the master over the network" \
			"$(runtime logs "$VOLUME_ROLE" 2>&1 | tail -5)"
	fi

	start_role "$FILER" "${VOLUMES[2]}" "$IMAGE" \
		filer -ip="$FILER" -master="${MASTER}:9333" -defaultStoreDir=/data
	if wait_for_port "$FILER" 8888; then
		ok "the filer starts and reaches the master"
	else
		bad "the filer starts and reaches the master" "$(runtime logs "$FILER" 2>&1 | tail -5)"
	fi

	# Environment flags belong to the runtime and must precede the image; the role
	# and its arguments follow it.
	start_role "$S3" "" \
		-e AWS_ACCESS_KEY_ID=cluster-key \
		-e AWS_SECRET_ACCESS_KEY=cluster-secret \
		"$IMAGE" s3 -filer="${FILER}:8888" -ip.bind=0.0.0.0
	local s3_up=false
	if wait_for_port "$S3" 8333; then
		ok "the S3 gateway starts against a separate filer"
		s3_up=true
	else
		bad "the S3 gateway starts against a separate filer" "$(runtime logs "$S3" 2>&1 | tail -5)"
	fi

	# The S3 role needs no writable volume at all: its state lives in the filer.
	# The container has to be running for this to mean anything -- a failed exec
	# against a dead container would otherwise look exactly like a refused write.
	if [ "$s3_up" != true ]; then
		bad "the S3 gateway runs on a fully read-only filesystem with no volume" \
			"skipped: the gateway is not running, so the probe would prove nothing"
	elif runtime exec "$S3" sh -c 'touch /probe' >/dev/null 2>&1; then
		bad "the S3 gateway runs on a fully read-only filesystem with no volume" \
			"the root filesystem accepted a write"
	else
		ok "the S3 gateway runs on a fully read-only filesystem with no volume"
	fi

	# Per-role listener inventories, measured. The standalone profile cannot show
	# these, because in one process every port belongs to the same process.
	assert_listeners "the master opens only its HTTP and gRPC ports" \
		"$MASTER" "9333 19333"
	assert_listeners "the volume server opens only its HTTP and gRPC ports" \
		"$VOLUME_ROLE" "8080 18080"
	assert_listeners "the filer opens only its HTTP and gRPC ports" \
		"$FILER" "8888 18888"
	# 18333 is the S3 role's gRPC companion, derived as 8333+10000 because
	# -port.grpc is left at 0. It belongs here; 8181 and 9101 do not.
	assert_listeners "the S3 gateway opens only its own ports, with Iceberg and Lance absent" \
		"$S3" "8333 18333"

	# Every role, in a topology where they are genuinely separate.
	local role privileged all_ok=true
	for role in "$MASTER" "$VOLUME_ROLE" "$FILER" "$S3"; do
		privileged="$(listening_ports "$role" | awk '$1 < 1024' | tr '\n' ' ')"
		[ -z "$privileged" ] || {
			bad "no role opens a privileged port" "${role}: ${privileged}"
			all_ok=false
			break
		}
	done
	[ "$all_ok" = true ] && ok "no role opens a privileged port"

	local uid
	all_ok=true
	for role in "$MASTER" "$VOLUME_ROLE" "$FILER" "$S3"; do
		uid="$(runtime exec "$role" cat /proc/1/status 2>/dev/null | awk '/^Uid:/ {print $2}')"
		[ -n "$uid" ] && [ "$uid" != "0" ] || {
			bad "every role runs as a non-root uid" "${role}: uid=${uid:-unknown}"
			all_ok=false
			break
		}
	done
	[ "$all_ok" = true ] && ok "every role runs as a non-root uid"

	all_ok=true
	for role in "$MASTER" "$VOLUME_ROLE" "$FILER" "$S3"; do
		if runtime logs "$role" 2>&1 | grep -q 'cluster-secret'; then
			bad "no role writes the secret access key to its logs" "found in ${role}"
			all_ok=false
			break
		fi
	done
	[ "$all_ok" = true ] && ok "no role writes the secret access key to its logs"

	if [ "$KEEP" = true ]; then
		printf '\nCluster left running (--keep).\n'
		printf '  network:   %s\n' "$NETWORK"
		printf '  s3:        %s:8333  (key cluster-key / cluster-secret)\n' "$S3"
		printf '  filer:     %s:8888\n' "$FILER"
		printf '  master:    %s:9333\n' "$MASTER"
		printf '  tear down: %s rm -f %s %s %s %s && %s network rm %s\n' \
			"$CONTAINER_RUNTIME" "$S3" "$FILER" "$VOLUME_ROLE" "$MASTER" \
			"$CONTAINER_RUNTIME" "$NETWORK"
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
