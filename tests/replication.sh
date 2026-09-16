#!/usr/bin/env bash
#
# Qualify a two-replica placement across two logical racks. Both volume servers
# run on one container host, so this is replica and process-loss evidence only;
# it is not evidence for host, node, disk, or availability-zone loss.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"
MASTER_HOST_PORT="${MASTER_HOST_PORT:-19337}"
VOLUME_A_HOST_PORT="${VOLUME_A_HOST_PORT:-18083}"
VOLUME_B_HOST_PORT="${VOLUME_B_HOST_PORT:-18084}"
FILER_HOST_PORT="${FILER_HOST_PORT:-18891}"
S3_HOST_PORT="${S3_HOST_PORT:-18337}"
PYTHON=""
WORK=""
SUFFIX="$$"
PREFIX="seaweedfs-ubi-replication-${SUFFIX}"
NETWORK="${PREFIX}-net"
MASTER="${PREFIX}-master"
VOLUME_A="${PREFIX}-volume-a"
VOLUME_B="${PREFIX}-volume-b"
FILER="${PREFIX}-filer"
GATEWAY="${PREFIX}-s3"
MASTER_VOLUME="${PREFIX}-master-data"
VOLUME_A_DATA="${PREFIX}-volume-a-data"
VOLUME_B_DATA="${PREFIX}-volume-b-data"
FILER_VOLUME="${PREFIX}-filer-data"
CONFIG_VOLUME="${PREFIX}-config"
RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)
passed=0
failed=0

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

cleanup() {
	local name
	for name in "$GATEWAY" "$FILER" "$VOLUME_B" "$VOLUME_A" "$MASTER"; do
		runtime rm -f "$name" >/dev/null 2>&1 || true
	done
	for name in "$MASTER_VOLUME" "$VOLUME_A_DATA" "$VOLUME_B_DATA" \
		"$FILER_VOLUME" "$CONFIG_VOLUME"; do
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

wait_http() {
	local url="$1" waited=0
	while [ "$waited" -lt 60 ]; do
		curl -fsS --max-time 5 "$url" >/dev/null 2>&1 && return 0
		sleep 2
		waited=$((waited + 2))
	done
	return 1
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
		    created = client.create_bucket("replication")
		    if created.status not in (200, 204, 409):
		        raise SystemExit(f"create bucket returned HTTP {created.status}")
		    written = client.put_object("replication", "object.txt", expected)
		    if written.status not in (200, 204):
		        raise SystemExit(f"put returned HTTP {written.status}")
		read = client.get_object("replication", "object.txt")
		if read.status != 200 or read.body != expected:
		    raise SystemExit(f"get returned HTTP {read.status} and {len(read.body)} bytes")
	PYTHON
}

s3_put_status() {
	local config="$1" key="$2" payload="$3"
	"$PYTHON" - "$REPO_ROOT" "http://127.0.0.1:${S3_HOST_PORT}" \
		"$config" "$key" "$payload" <<-'PYTHON'
		import json, os, sys
		sys.path.insert(0, os.path.join(sys.argv[1], "tests", "lib"))
		from s3client import S3Client
		config = json.load(open(sys.argv[3], encoding="utf-8"))
		credential = config["identities"][0]["credentials"][0]
		client = S3Client(sys.argv[2], credential["accessKey"], credential["secretKey"])
		response = client.put_object("replication", sys.argv[4], sys.argv[5].encode())
		print(response.status)
	PYTHON
}

inspect_placement() {
	local payload="$1"
	"$PYTHON" - "$MASTER_HOST_PORT" "$FILER_HOST_PORT" "$VOLUME_A_HOST_PORT" \
		"$VOLUME_B_HOST_PORT" "$VOLUME_A" "$VOLUME_B" "$payload" <<-'PYTHON'
		import json, sys, urllib.request
		master, filer, port_a, port_b = sys.argv[1:5]
		name_a, name_b, expected = sys.argv[5:8]
		with urllib.request.urlopen(
		    f"http://127.0.0.1:{filer}/buckets/replication/object.txt?metadata=true",
		    timeout=10,
		) as response:
		    metadata = json.load(response)
		file_id = next(chunk["file_id"] for chunk in metadata["chunks"] if chunk.get("file_id"))
		volume_id = file_id.split(",", 1)[0]
		with urllib.request.urlopen(
		    f"http://127.0.0.1:{master}/dir/lookup?volumeId={volume_id}", timeout=10
		) as response:
		    lookup = json.load(response)
		locations = json.dumps(lookup.get("locations", []))
		if name_a not in locations or name_b not in locations:
		    raise SystemExit(f"volume {volume_id} locations were {locations}")
		with urllib.request.urlopen(
		    f"http://127.0.0.1:{master}/dir/status", timeout=10
		) as response:
		    topology = json.dumps(json.load(response))
		for marker in ("rack-a", "rack-b", name_a, name_b):
		    if marker not in topology:
		        raise SystemExit(f"topology did not contain {marker!r}")
		for port in (port_a, port_b):
		    with urllib.request.urlopen(
		        f"http://127.0.0.1:{port}/{file_id}", timeout=10
		    ) as response:
		        body = response.read()
		    if expected.encode() not in body:
		        raise SystemExit(f"replica on port {port} did not return expected bytes")
		print(file_id)
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

	WORK="$(mktemp -d)"
	local config="${WORK}/s3.json" payload="replicated bytes survive one process loss"
	"$PYTHON" - "$config" <<-'PYTHON'
		import json, secrets, sys
		config = {"identities": [{
		    "name": "replication",
		    "credentials": [{
		        "accessKey": "replication" + secrets.token_hex(8),
		        "secretKey": secrets.token_urlsafe(32),
		    }],
		    "actions": ["Admin", "Read", "List", "Tagging", "Write"],
		}]}
		open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(config))
	PYTHON

	printf 'Qualifying a two-replica, two-rack volume topology\n\n'
	runtime network create "$NETWORK" >/dev/null
	local name
	for name in "$MASTER_VOLUME" "$VOLUME_A_DATA" "$VOLUME_B_DATA" "$FILER_VOLUME"; do
		runtime volume create "$name" >/dev/null
	done
	seed_config "$config"

	runtime run -d --name "$MASTER" --network "$NETWORK" --network-alias "$MASTER" \
		"${RESTRICTED[@]}" -v "${MASTER_VOLUME}:/data" \
		-p "127.0.0.1:${MASTER_HOST_PORT}:9333" \
		"$IMAGE" master -mdir=/data -ip="$MASTER" -defaultReplication=010 >/dev/null
	wait_for_port "$MASTER" 9333 || exit 1

	runtime run -d --name "$VOLUME_A" --network "$NETWORK" --network-alias "$VOLUME_A" \
		"${RESTRICTED[@]}" -v "${VOLUME_A_DATA}:/data" \
		-p "127.0.0.1:${VOLUME_A_HOST_PORT}:8080" \
		"$IMAGE" volume -dir=/data -ip="$VOLUME_A" -master="${MASTER}:9333" \
		-dataCenter=dc1 -rack=rack-a -max=4 >/dev/null
	wait_for_port "$VOLUME_A" 8080 || exit 1

	runtime run -d --name "$VOLUME_B" --network "$NETWORK" --network-alias "$VOLUME_B" \
		"${RESTRICTED[@]}" -v "${VOLUME_B_DATA}:/data" \
		-p "127.0.0.1:${VOLUME_B_HOST_PORT}:8080" \
		"$IMAGE" volume -dir=/data -ip="$VOLUME_B" -master="${MASTER}:9333" \
		-dataCenter=dc1 -rack=rack-b -max=4 >/dev/null
	wait_for_port "$VOLUME_B" 8080 || exit 1

	runtime run -d --name "$FILER" --network "$NETWORK" --network-alias "$FILER" \
		"${RESTRICTED[@]}" -v "${FILER_VOLUME}:/data" \
		-p "127.0.0.1:${FILER_HOST_PORT}:8888" \
		"$IMAGE" filer -ip="$FILER" -master="${MASTER}:9333" \
		-defaultStoreDir=/data >/dev/null
	wait_for_port "$FILER" 8888 || exit 1

	runtime run -d --name "$GATEWAY" --network "$NETWORK" --network-alias "$GATEWAY" \
		"${RESTRICTED[@]}" -v "${CONFIG_VOLUME}:/etc/seaweedfs:ro" \
		-p "127.0.0.1:${S3_HOST_PORT}:8333" \
		"$IMAGE" s3 -filer="${FILER}:8888" -ip.bind=0.0.0.0 \
		-config=/etc/seaweedfs/s3.json >/dev/null
	wait_for_port "$GATEWAY" 8333 || exit 1

	if s3_object write "$config" "$payload"; then
		ok "S3 acknowledges and reads an object with replication 010 selected"
	else
		bad "S3 acknowledges and reads an object with replication 010 selected"
	fi

	local file_id
	if file_id="$(inspect_placement "$payload")"; then
		ok "the object's volume is present on both logical racks and serves from both replicas"
	else
		bad "the object's volume is present on both logical racks and serves from both replicas"
		file_id=""
	fi

	runtime stop --time 30 "$VOLUME_A" >/dev/null
	if wait_http "http://127.0.0.1:${MASTER_HOST_PORT}/dir/status" &&
		s3_object read "$config" "$payload"; then
		ok "S3 reads the acknowledged object while one volume-server process is stopped"
	else
		bad "S3 reads the acknowledged object while one volume-server process is stopped"
	fi

	if [ -n "$file_id" ] && curl -fsS --max-time 10 \
		"http://127.0.0.1:${VOLUME_B_HOST_PORT}/${file_id}" | grep -Fq "$payload"; then
		ok "the surviving replica serves the expected bytes directly"
	else
		bad "the surviving replica serves the expected bytes directly"
	fi

	local degraded_write_status
	degraded_write_status="$(s3_put_status "$config" degraded.txt \
		"this write must not be acknowledged with one rack absent")"
	if [ "$degraded_write_status" != 200 ] && [ "$degraded_write_status" != 204 ]; then
		ok "a new replicated write is not acknowledged while one required rack is absent"
	else
		bad "a new replicated write is not acknowledged while one required rack is absent" \
			"the S3 API returned HTTP ${degraded_write_status}"
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
