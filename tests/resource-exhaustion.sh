#!/usr/bin/env bash
#
# Exercise storage-capacity failures without relaxing the restricted runtime.
# These are master/volume tests: no single-container result is used as evidence
# for clustered behavior, and no tmpfs result is presented as physical-disk
# evidence.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"
MASTER_HOST_PORT="${MASTER_HOST_PORT:-19338}"
VOLUME_HOST_PORT="${VOLUME_HOST_PORT:-18085}"
PYTHON=""
SUFFIX="$$"
PREFIX="seaweedfs-ubi-resource-${SUFFIX}"
NETWORK="${PREFIX}-net"
MASTER="${PREFIX}-master"
VOLUME_ROLE="${PREFIX}-volume"
MASTER_DATA="${PREFIX}-master-data"
RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)
passed=0
failed=0

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

cleanup_pair() {
	runtime rm -f "$VOLUME_ROLE" "$MASTER" >/dev/null 2>&1 || true
	runtime volume rm -f "$MASTER_DATA" >/dev/null 2>&1 || true
}

cleanup() {
	cleanup_pair
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

resolve_python() {
	local candidate
	for candidate in python3 python; do
		if command -v "$candidate" >/dev/null 2>&1 &&
			"$candidate" -c 'import sys; raise SystemExit(sys.version_info[0] != 3)' >/dev/null 2>&1; then
			printf '%s' "$candidate"
			return 0
		fi
	done
	return 1
}

listening_ports() {
	runtime exec "$1" cat /proc/net/tcp /proc/net/tcp6 2>/dev/null |
		"$PYTHON" "${REPO_ROOT}/tests/lib/listening_ports.py"
}

wait_for_port() {
	local container="$1" port="$2" waited=0
	while [ "$waited" -lt 90 ]; do
		listening_ports "$container" | grep -qx "$port" && return 0
		[ "$(runtime inspect "$container" --format '{{.State.Status}}' 2>/dev/null)" = "exited" ] && return 1
		sleep 2
		waited=$((waited + 2))
	done
	return 1
}

wait_registered() {
	local waited=0
	while [ "$waited" -lt 60 ]; do
		curl -fsS --max-time 5 "http://127.0.0.1:${MASTER_HOST_PORT}/dir/status" 2>/dev/null |
			grep -Fq "$VOLUME_ROLE" && return 0
		sleep 2
		waited=$((waited + 2))
	done
	return 1
}

start_pair() {
	local tmpfs_size="$1" max_volumes="$2" volume_size_mb="$3"
	cleanup_pair
	runtime volume create "$MASTER_DATA" >/dev/null
	runtime run -d --name "$MASTER" --network "$NETWORK" --network-alias "$MASTER" \
		"${RESTRICTED[@]}" -v "${MASTER_DATA}:/data" \
		-p "127.0.0.1:${MASTER_HOST_PORT}:9333" \
		"$IMAGE" master -mdir=/data -ip="$MASTER" -peers=none \
		-volumeSizeLimitMB="$volume_size_mb" >/dev/null
	wait_for_port "$MASTER" 9333 || return 1

	runtime run -d --name "$VOLUME_ROLE" --network "$NETWORK" --network-alias "$VOLUME_ROLE" \
		"${RESTRICTED[@]}" --tmpfs "/data:rw,size=${tmpfs_size}" \
		-p "127.0.0.1:${VOLUME_HOST_PORT}:8080" \
		"$IMAGE" volume -dir=/data -ip="$VOLUME_ROLE" -master="${MASTER}:9333" \
		-max="$max_volumes" -minFreeSpace=0 >/dev/null
	wait_for_port "$VOLUME_ROLE" 8080 && wait_registered
}

grow_volume() {
	curl -sS --max-time 10 "http://127.0.0.1:${MASTER_HOST_PORT}/vol/grow?count=1"
}

fill_volume() {
	"$PYTHON" - "$MASTER_HOST_PORT" "$VOLUME_HOST_PORT" <<-'PYTHON'
		import json, sys, urllib.error, urllib.request

		master_port, volume_port = sys.argv[1:]
		payload = bytes((index * 17 + 3) % 251 for index in range(512 * 1024))
		successes = 0
		failure = "none"
		for index in range(20):
		    try:
		        with urllib.request.urlopen(
		            f"http://127.0.0.1:{master_port}/dir/assign", timeout=10
		        ) as response:
		            assignment = json.load(response)
		        fid = assignment["fid"]
		    except Exception as error:
		        failure = f"assign:{type(error).__name__}"
		        break

		    boundary = f"----seaweedfsubi{index}"
		    body = b"".join((
		        f"--{boundary}\r\n".encode(),
		        f'Content-Disposition: form-data; name="file"; filename="{index}.bin"\r\n'.encode(),
		        b"Content-Type: application/octet-stream\r\n\r\n",
		        payload,
		        f"\r\n--{boundary}--\r\n".encode(),
		    ))
		    request = urllib.request.Request(
		        f"http://127.0.0.1:{volume_port}/{fid}",
		        data=body,
		        method="POST",
		        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
		    )
		    try:
		        with urllib.request.urlopen(request, timeout=15) as response:
		            if response.status not in (200, 201):
		                failure = f"upload:{response.status}"
		                break
		        successes += 1
		    except urllib.error.HTTPError as error:
		        failure = f"upload:{error.code}"
		        break
		    except Exception as error:
		        failure = f"upload:{type(error).__name__}"
		        break
		print(f"{successes} {failure}")
		raise SystemExit(0 if 0 < successes < 20 and failure != "none" else 1)
	PYTHON
}

main() {
	PYTHON="$(resolve_python)" || {
		printf 'REFUSED: a Python 3 interpreter is required\n' >&2
		exit 2
	}
	runtime image exists "$IMAGE" 2>/dev/null || {
		printf 'REFUSED: %s does not exist. Run scripts/build.sh first.\n' "$IMAGE" >&2
		exit 2
	}

	printf 'Qualifying visible storage-exhaustion behavior\n\n'
	runtime network create "$NETWORK" >/dev/null

	start_pair 16m 1 1 || {
		printf 'REFUSED: the volume-count fixture did not start\n' >&2
		exit 1
	}
	local first_grow second_grow
	first_grow="$(grow_volume)"
	second_grow="$(grow_volume)"
	if printf '%s' "$first_grow" | grep -Fq '"count":1' &&
		printf '%s' "$second_grow" | grep -Fq 'only 0 volumes left'; then
		ok "the configured one-volume limit admits one volume and visibly refuses another"
	else
		bad "the configured one-volume limit admits one volume and visibly refuses another" \
			"first response: ${first_grow}" "second response: ${second_grow}"
	fi

	start_pair 3m 8 16 || {
		printf 'REFUSED: the bounded-tmpfs fixture did not start\n' >&2
		exit 1
	}
	local data_mount
	data_mount="$(runtime exec "$VOLUME_ROLE" cat /proc/mounts | awk '$2=="/data" {print}')"
	if printf '%s' "$data_mount" | grep -Fq 'tmpfs' &&
		printf '%s' "$data_mount" | grep -Fq 'size=3072k'; then
		ok "the volume data directory is a measured 3 MiB tmpfs"
	else
		bad "the volume data directory is a measured 3 MiB tmpfs" "$data_mount"
	fi

	local grow_response fill_result
	grow_response="$(grow_volume)"
	if ! printf '%s' "$grow_response" | grep -Fq '"count":1'; then
		bad "a volume is available before byte exhaustion" "$grow_response"
	elif fill_result="$(fill_volume)"; then
		ok "a bounded data filesystem accepts writes and then fails visibly when full"
	else
		bad "a bounded data filesystem accepts writes and then fails visibly when full" \
			"observed: ${fill_result:-no result}"
	fi

	local volume_logs
	volume_logs="$(runtime logs "$VOLUME_ROLE" 2>&1)"
	if printf '%s' "$volume_logs" | grep -Eqi 'no space left|disk.*full'; then
		ok "the full-filesystem failure is recorded in the volume-server logs"
	else
		bad "the full-filesystem failure is recorded in the volume-server logs" \
			"no full-filesystem diagnostic was found"
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
