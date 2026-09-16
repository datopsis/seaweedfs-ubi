#!/usr/bin/env bash
#
# Qualify a cold backup and restore of every state-bearing role. Podman's native
# named-volume archive commands are used so no unpinned helper image enters the
# evidence path. Credentials are recreated separately and are not backup data.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"
S3_HOST_PORT="${S3_HOST_PORT:-18339}"
PYTHON=""
WORK=""
SUFFIX="$$"
PREFIX="seaweedfs-ubi-backup-${SUFFIX}"
NETWORK="${PREFIX}-net"
MASTER="${PREFIX}-master"
VOLUME_ROLE="${PREFIX}-volume"
FILER="${PREFIX}-filer"
GATEWAY="${PREFIX}-s3"
SOURCE_MASTER="${PREFIX}-source-master"
SOURCE_VOLUME="${PREFIX}-source-volume"
SOURCE_FILER="${PREFIX}-source-filer"
SOURCE_CONFIG="${PREFIX}-source-config"
RESTORED_MASTER="${PREFIX}-restored-master"
RESTORED_VOLUME="${PREFIX}-restored-volume"
RESTORED_FILER="${PREFIX}-restored-filer"
RESTORED_CONFIG="${PREFIX}-restored-config"
RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)
passed=0
failed=0

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

remove_containers() {
	local name
	for name in "$GATEWAY" "$FILER" "$VOLUME_ROLE" "$MASTER"; do
		runtime rm -f "$name" >/dev/null 2>&1 || true
	done
}

cleanup() {
	remove_containers
	local name
	for name in "$SOURCE_MASTER" "$SOURCE_VOLUME" "$SOURCE_FILER" "$SOURCE_CONFIG" \
		"$RESTORED_MASTER" "$RESTORED_VOLUME" "$RESTORED_FILER" "$RESTORED_CONFIG"; do
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

seed_config() {
	local config="$1" volume_name="$2" seeder
	runtime volume create "$volume_name" >/dev/null
	seeder="$(runtime create -v "${volume_name}:/cfg" "$IMAGE" version)"
	"$PYTHON" - "$config" <<-'PYTHON' | runtime cp - "${seeder}:/cfg"
		import io, sys, tarfile
		data = open(sys.argv[1], "rb").read()
		buffer = io.BytesIO()
		with tarfile.open(fileobj=buffer, mode="w") as archive:
		    info = tarfile.TarInfo("s3.json")
		    info.size = len(data)
		    info.mode = 0o640
		    info.uid = 1000
		    info.gid = 0
		    archive.addfile(info, io.BytesIO(data))
		sys.stdout.buffer.write(buffer.getvalue())
	PYTHON
	runtime rm -f "$seeder" >/dev/null 2>&1 || true
}

start_cluster() {
	local master_data="$1" volume_data="$2" filer_data="$3" config_data="$4"
	runtime run -d --name "$MASTER" --network "$NETWORK" --network-alias "$MASTER" \
		"${RESTRICTED[@]}" -v "${master_data}:/data" \
		"$IMAGE" master -mdir=/data -ip="$MASTER" -peers=none >/dev/null
	wait_for_port "$MASTER" 9333 || return 1

	runtime run -d --name "$VOLUME_ROLE" --network "$NETWORK" --network-alias "$VOLUME_ROLE" \
		"${RESTRICTED[@]}" -v "${volume_data}:/data" \
		"$IMAGE" volume -dir=/data -ip="$VOLUME_ROLE" \
		-master="${MASTER}:9333" -max=4 >/dev/null
	wait_for_port "$VOLUME_ROLE" 8080 || return 1

	runtime run -d --name "$FILER" --network "$NETWORK" --network-alias "$FILER" \
		"${RESTRICTED[@]}" -v "${filer_data}:/data" \
		"$IMAGE" filer -ip="$FILER" -master="${MASTER}:9333" \
		-defaultStoreDir=/data >/dev/null
	wait_for_port "$FILER" 8888 || return 1

	runtime run -d --name "$GATEWAY" --network "$NETWORK" --network-alias "$GATEWAY" \
		"${RESTRICTED[@]}" -v "${config_data}:/etc/seaweedfs:ro" \
		-p "127.0.0.1:${S3_HOST_PORT}:8333" \
		"$IMAGE" s3 -filer="${FILER}:8888" -ip.bind=0.0.0.0 \
		-config=/etc/seaweedfs/s3.json >/dev/null
	wait_for_port "$GATEWAY" 8333
}

s3_object() {
	local operation="$1" config="$2" payload="$3"
	"$PYTHON" - "$REPO_ROOT" "http://127.0.0.1:${S3_HOST_PORT}" \
		"$config" "$operation" "$payload" <<-'PYTHON'
		import json, os, sys
		sys.path.insert(0, os.path.join(sys.argv[1], "tests", "lib"))
		from s3client import S3Client
		config = json.load(open(sys.argv[3], encoding="utf-8"))
		credential = config["identities"][0]["credentials"][0]
		client = S3Client(sys.argv[2], credential["accessKey"], credential["secretKey"])
		expected = sys.argv[5].encode()
		if sys.argv[4] == "write":
		    created = client.create_bucket("backup")
		    if created.status not in (200, 204, 409):
		        raise SystemExit(f"create bucket returned HTTP {created.status}")
		    written = client.put_object("backup", "object.txt", expected)
		    if written.status not in (200, 204):
		        raise SystemExit(f"put returned HTTP {written.status}")
		read = client.get_object("backup", "object.txt")
		if read.status != 200 or read.body != expected:
		    raise SystemExit(f"get returned HTTP {read.status} and {len(read.body)} bytes")
	PYTHON
}

wait_for_object() {
	local config="$1" payload="$2" waited=0
	while [ "$waited" -lt 60 ]; do
		s3_object read "$config" "$payload" >/dev/null 2>&1 && return 0
		sleep 2
		waited=$((waited + 2))
	done
	return 1
}

export_volume() {
	local volume_name="$1" archive="$2"
	runtime volume export "$volume_name" >"$archive"
}

import_volume() {
	local volume_name="$1" archive="$2"
	runtime volume create "$volume_name" >/dev/null
	runtime volume import "$volume_name" - <"$archive" >/dev/null
}

archives_are_complete() {
	local master_archive="$1" volume_archive="$2" filer_archive="$3" secret="$4"
	"$PYTHON" "${REPO_ROOT}/scripts/lib/validate_backup.py" \
		--forbid-value "$secret" \
		"$master_archive" "$volume_archive" "$filer_archive"
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
	if ! runtime volume export --help >/dev/null 2>&1 ||
		! runtime volume import --help >/dev/null 2>&1; then
		printf 'REFUSED: %s does not support named-volume export and import\n' \
			"$CONTAINER_RUNTIME" >&2
		exit 2
	fi

	WORK="$(mktemp -d)"
	local config="${WORK}/s3.json" payload="bytes recovered from three restored state archives"
	local secret
	secret="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(32))')"
	"$PYTHON" - "$config" "$secret" <<-'PYTHON'
		import json, secrets, sys
		config = {"identities": [{
		    "name": "backup",
		    "credentials": [{
		        "accessKey": "backup" + secrets.token_hex(8),
		        "secretKey": sys.argv[2],
		    }],
		    "actions": ["Admin", "Read", "List", "Tagging", "Write"],
		}]}
		open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(config))
	PYTHON

	printf 'Qualifying cold backup and restore into replacement storage\n\n'
	runtime network create "$NETWORK" >/dev/null
	local name
	for name in "$SOURCE_MASTER" "$SOURCE_VOLUME" "$SOURCE_FILER"; do
		runtime volume create "$name" >/dev/null
	done
	seed_config "$config" "$SOURCE_CONFIG"
	start_cluster "$SOURCE_MASTER" "$SOURCE_VOLUME" "$SOURCE_FILER" "$SOURCE_CONFIG" || {
		printf 'REFUSED: the source cluster did not start\n' >&2
		exit 1
	}

	if s3_object write "$config" "$payload"; then
		ok "the source deployment acknowledges and reads the object before backup"
	else
		bad "the source deployment acknowledges and reads the object before backup"
	fi

	local source_master_id source_volume_id source_filer_id source_gateway_id
	source_master_id="$(runtime inspect "$MASTER" --format '{{.Id}}')"
	source_volume_id="$(runtime inspect "$VOLUME_ROLE" --format '{{.Id}}')"
	source_filer_id="$(runtime inspect "$FILER" --format '{{.Id}}')"
	source_gateway_id="$(runtime inspect "$GATEWAY" --format '{{.Id}}')"
	if runtime stop --time 30 "$GATEWAY" "$FILER" "$VOLUME_ROLE" "$MASTER" >/dev/null; then
		ok "all roles stop cleanly before the cold backup boundary"
	else
		bad "all roles stop cleanly before the cold backup boundary"
	fi
	remove_containers

	local master_archive="${WORK}/master.tar"
	local volume_archive="${WORK}/volume.tar"
	local filer_archive="${WORK}/filer.tar"
	export_volume "$SOURCE_MASTER" "$master_archive"
	export_volume "$SOURCE_VOLUME" "$volume_archive"
	export_volume "$SOURCE_FILER" "$filer_archive"
	if archives_are_complete "$master_archive" "$volume_archive" "$filer_archive" "$secret"; then
		ok "master, volume, and filer archives are non-empty and exclude runtime S3 credentials"
	else
		bad "master, volume, and filer archives are non-empty and exclude runtime S3 credentials"
	fi

	for name in "$SOURCE_MASTER" "$SOURCE_VOLUME" "$SOURCE_FILER" "$SOURCE_CONFIG"; do
		runtime volume rm -f "$name" >/dev/null
	done
	import_volume "$RESTORED_MASTER" "$master_archive"
	import_volume "$RESTORED_VOLUME" "$volume_archive"
	import_volume "$RESTORED_FILER" "$filer_archive"
	seed_config "$config" "$RESTORED_CONFIG"
	start_cluster "$RESTORED_MASTER" "$RESTORED_VOLUME" "$RESTORED_FILER" \
		"$RESTORED_CONFIG" || {
		printf 'REFUSED: the restored cluster did not start\n' >&2
		exit 1
	}

	local replacement_ids=true current_id expected_id
	for current_id in \
		"$(runtime inspect "$MASTER" --format '{{.Id}}')" \
		"$(runtime inspect "$VOLUME_ROLE" --format '{{.Id}}')" \
		"$(runtime inspect "$FILER" --format '{{.Id}}')" \
		"$(runtime inspect "$GATEWAY" --format '{{.Id}}')"; do
		for expected_id in "$source_master_id" "$source_volume_id" "$source_filer_id" \
			"$source_gateway_id"; do
			[ "$current_id" = "$expected_id" ] && replacement_ids=false
		done
	done
	if [ "$replacement_ids" = true ]; then
		ok "the restored roles are replacement containers using new volume names"
	else
		bad "the restored roles are replacement containers using new volume names"
	fi

	if wait_for_object "$config" "$payload"; then
		ok "the replacement deployment reads the restored object byte for byte through S3"
	else
		bad "the replacement deployment reads the restored object byte for byte through S3"
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
