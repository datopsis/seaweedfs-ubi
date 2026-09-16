#!/usr/bin/env bash
#
# Qualify state survival in the separated-role, single-volume topology.
# The same named data volumes are reused throughout. This proves container
# lifecycle survival, not replication, node-loss survival, or backup.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"
S3_HOST_PORT="${S3_HOST_PORT:-18335}"
PYTHON=""
WORK=""
SUFFIX="$$"
PREFIX="seaweedfs-ubi-state-${SUFFIX}"
NETWORK="${PREFIX}-net"
MASTER="${PREFIX}-master"
VOLUME_ROLE="${PREFIX}-volume"
FILER="${PREFIX}-filer"
GATEWAY="${PREFIX}-s3"
MASTER_VOLUME="${PREFIX}-master-data"
VOLUME_VOLUME="${PREFIX}-volume-data"
FILER_VOLUME="${PREFIX}-filer-data"
CONFIG_VOLUME="${PREFIX}-config"
ENDPOINT="http://127.0.0.1:${S3_HOST_PORT}"
RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)
passed=0
failed=0

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

cleanup() {
	local name
	for name in "$GATEWAY" "$FILER" "$VOLUME_ROLE" "$MASTER"; do
		runtime rm -f "$name" >/dev/null 2>&1 || true
	done
	for name in "$MASTER_VOLUME" "$VOLUME_VOLUME" "$FILER_VOLUME" "$CONFIG_VOLUME"; do
		runtime volume rm -f "$name" >/dev/null 2>&1 || true
	done
	runtime network rm -f "$NETWORK" >/dev/null 2>&1 || true
	[ -n "$WORK" ] && rm -rf "$WORK"
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
			"$candidate" -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
			printf '%s' "$candidate"
			return 0
		fi
	done
	return 1
}

listening_ports() {
	runtime exec "$1" cat /proc/net/tcp /proc/net/tcp6 2>/dev/null |
		awk '$4=="0A" {split($2,a,":"); print strtonum("0x" a[2])}' | sort -n -u
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

seed_config() {
	local config="$1" seeder
	runtime volume create "$CONFIG_VOLUME" >/dev/null
	seeder="$(runtime create -v "${CONFIG_VOLUME}:/cfg" "$IMAGE" version)"
	"$PYTHON" - "$config" <<-'PYTHON' | runtime cp - "${seeder}:/cfg"
		import io, sys, tarfile
		data = open(sys.argv[1], "rb").read()
		buffer = io.BytesIO()
		with tarfile.open(fileobj=buffer, mode="w") as archive:
		    info = tarfile.TarInfo("s3.json")
		    info.size = len(data)
		    info.mode = 0o644
		    archive.addfile(info, io.BytesIO(data))
		sys.stdout.buffer.write(buffer.getvalue())
	PYTHON
	runtime rm -f "$seeder" >/dev/null 2>&1 || true
}

start_cluster() {
	runtime run -d --name "$MASTER" --network "$NETWORK" --network-alias "$MASTER" \
		"${RESTRICTED[@]}" -v "${MASTER_VOLUME}:/data" \
		"$IMAGE" master -mdir=/data -ip="$MASTER" >/dev/null
	wait_for_port "$MASTER" 9333 || return 1

	runtime run -d --name "$VOLUME_ROLE" --network "$NETWORK" --network-alias "$VOLUME_ROLE" \
		"${RESTRICTED[@]}" -v "${VOLUME_VOLUME}:/data" \
		"$IMAGE" volume -dir=/data -ip="$VOLUME_ROLE" \
		-mserver="${MASTER}:9333" -max=4 >/dev/null
	wait_for_port "$VOLUME_ROLE" 8080 || return 1

	runtime run -d --name "$FILER" --network "$NETWORK" --network-alias "$FILER" \
		"${RESTRICTED[@]}" -v "${FILER_VOLUME}:/data" \
		"$IMAGE" filer -ip="$FILER" -master="${MASTER}:9333" \
		-defaultStoreDir=/data >/dev/null
	wait_for_port "$FILER" 8888 || return 1

	runtime run -d --name "$GATEWAY" --network "$NETWORK" --network-alias "$GATEWAY" \
		"${RESTRICTED[@]}" -v "${CONFIG_VOLUME}:/etc/seaweedfs:ro" \
		-p "127.0.0.1:${S3_HOST_PORT}:8333" \
		"$IMAGE" s3 -filer="${FILER}:8888" -ip.bind=0.0.0.0 \
		-config=/etc/seaweedfs/s3.json >/dev/null
	wait_for_port "$GATEWAY" 8333 || return 1
}

remove_containers() {
	local name
	for name in "$GATEWAY" "$FILER" "$VOLUME_ROLE" "$MASTER"; do
		runtime rm -f "$name" >/dev/null
	done
}

s3_operation() {
	local operation="$1" config="$2" key="$3" payload="$4"
	"$PYTHON" - "$REPO_ROOT" "$ENDPOINT" "$config" "$operation" "$key" "$payload" <<-'PYTHON'
		import json, os, sys
		sys.path.insert(0, os.path.join(sys.argv[1], "tests", "lib"))
		from s3client import S3Client

		config = json.load(open(sys.argv[3], encoding="utf-8"))
		credential = config["identities"][0]["credentials"][0]
		client = S3Client(sys.argv[2], credential["accessKey"], credential["secretKey"])
		operation, key, expected = sys.argv[4], sys.argv[5], sys.argv[6].encode()
		if operation == "write":
		    created = client.create_bucket("survival")
		    if created.status not in (200, 204, 409):
		        raise SystemExit(f"create bucket returned HTTP {created.status}")
		    written = client.put_object("survival", key, expected)
		    if written.status not in (200, 204):
		        raise SystemExit(f"put returned HTTP {written.status}")
		read = client.get_object("survival", key)
		if read.status != 200 or read.body != expected:
		    raise SystemExit(f"get returned HTTP {read.status} and {len(read.body)} bytes")
	PYTHON
}

wait_for_object() {
	local config="$1" key="$2" payload="$3" waited=0
	while [ "$waited" -lt 60 ]; do
		s3_operation read "$config" "$key" "$payload" >/dev/null 2>&1 && return 0
		sleep 2
		waited=$((waited + 2))
	done
	return 1
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

	WORK="$(mktemp -d)"
	local config="${WORK}/s3.json"
	"$PYTHON" - "$config" <<-'PYTHON'
		import json, secrets, sys
		config = {"identities": [{
		    "name": "survival",
		    "credentials": [{
		        "accessKey": "state" + secrets.token_hex(8),
		        "secretKey": secrets.token_urlsafe(32),
		    }],
		    "actions": ["Admin", "Read", "List", "Tagging", "Write"],
		}]}
		open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(config))
	PYTHON

	printf 'Qualifying state survival in the separated-role topology\n\n'
	runtime network create "$NETWORK" >/dev/null
	local name
	for name in "$MASTER_VOLUME" "$VOLUME_VOLUME" "$FILER_VOLUME"; do
		runtime volume create "$name" >/dev/null
	done
	seed_config "$config"
	start_cluster || {
		printf 'REFUSED: the initial cluster did not start\n' >&2
		exit 1
	}

	if s3_operation write "$config" restart.txt "acknowledged before ordinary restart"; then
		ok "an object is acknowledged before an ordinary restart"
	else
		bad "an object is acknowledged before an ordinary restart"
	fi

	for name in "$MASTER" "$VOLUME_ROLE" "$FILER" "$GATEWAY"; do
		runtime restart "$name" >/dev/null
		case "$name" in
		"$MASTER") wait_for_port "$name" 9333 ;;
		"$VOLUME_ROLE") wait_for_port "$name" 8080 ;;
		"$FILER") wait_for_port "$name" 8888 ;;
		"$GATEWAY") wait_for_port "$name" 8333 ;;
		esac
	done
	if wait_for_object "$config" restart.txt "acknowledged before ordinary restart"; then
		ok "acknowledged data survives an ordinary restart of every role"
	else
		bad "acknowledged data survives an ordinary restart of every role"
	fi

	s3_operation write "$config" replacement.txt "acknowledged before graceful replacement"
	local old_master
	old_master="$(runtime inspect "$MASTER" --format '{{.Id}}')"
	if runtime stop --time 30 "$GATEWAY" "$FILER" "$VOLUME_ROLE" "$MASTER" >/dev/null; then
		ok "every role accepts a graceful shutdown"
	else
		bad "every role accepts a graceful shutdown"
	fi
	remove_containers
	start_cluster || {
		printf 'REFUSED: the replacement cluster did not start\n' >&2
		exit 1
	}
	local new_master
	new_master="$(runtime inspect "$MASTER" --format '{{.Id}}')"
	if [ "$old_master" != "$new_master" ]; then
		ok "the roles are replacement containers, not restarted instances"
	else
		bad "the roles are replacement containers, not restarted instances"
	fi
	if wait_for_object "$config" replacement.txt "acknowledged before graceful replacement"; then
		ok "acknowledged data survives graceful shutdown and container replacement"
	else
		bad "acknowledged data survives graceful shutdown and container replacement"
	fi

	s3_operation write "$config" unclean.txt "acknowledged before unclean stop"
	if runtime kill "$GATEWAY" "$FILER" "$VOLUME_ROLE" "$MASTER" >/dev/null; then
		ok "the unclean-stop scenario kills every role without a shutdown window"
	else
		bad "the unclean-stop scenario kills every role without a shutdown window"
	fi
	remove_containers
	start_cluster || {
		printf 'REFUSED: the post-kill replacement cluster did not start\n' >&2
		exit 1
	}
	if wait_for_object "$config" unclean.txt "acknowledged before unclean stop"; then
		ok "acknowledged data survives an unclean stop when storage remains intact"
	else
		bad "acknowledged data survives an unclean stop when storage remains intact"
	fi
	if s3_operation read "$config" restart.txt "acknowledged before ordinary restart" &&
		s3_operation read "$config" replacement.txt "acknowledged before graceful replacement"; then
		ok "the recovered namespace retains objects from every lifecycle phase"
	else
		bad "the recovered namespace retains objects from every lifecycle phase"
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
