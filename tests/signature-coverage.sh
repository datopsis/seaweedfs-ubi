#!/usr/bin/env bash
#
# Measure which parts of a SigV4-signed request the S3 gateway verifies.
#
# Remote signing (for example Lakekeeper's Iceberg sign endpoint) gives a client
# a signature over a request it then sends itself. Whatever the gateway leaves
# outside its signature check, the client can change after signing. This suite
# changes one canonical-request component at a time and records the result:
# rejection where SeaweedFS verifies the component, an exact-outcome canary
# where it does not. docs/REMOTE-SIGNING.md is written from these results.
#
# It runs the separated-role production topology, as tests/s3.sh does, with a
# test bucket and identities generated for this run only.
#
# Usage:
#   tests/signature-coverage.sh [--keep]
#
# Environment:
#   CONTAINER_RUNTIME  podman (default) or docker
#   IMAGE              image under test (default localhost/seaweedfs-ubi:development)
#   S3_HOST_PORT       host port for the gateway (default 18335)

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"
S3_HOST_PORT="${S3_HOST_PORT:-18335}"

PYTHON=""
WORK=""

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)

SUFFIX="$$"
NETWORK="seaweedfs-ubi-signet-${SUFFIX}"
MASTER="seaweedfs-ubi-sig-master-${SUFFIX}"
VOLUME_ROLE="seaweedfs-ubi-sig-volume-${SUFFIX}"
FILER="seaweedfs-ubi-sig-filer-${SUFFIX}"
GATEWAY="seaweedfs-ubi-sig-gateway-${SUFFIX}"
VOLUMES=("sigvol-master-${SUFFIX}" "sigvol-volume-${SUFFIX}" "sigvol-filer-${SUFFIX}")
CONFIG_VOLUME="sigvol-config-${SUFFIX}"

KEEP=false
[ "${1:-}" = "--keep" ] && KEEP=true

cleanup() {
	if [ "$KEEP" != true ]; then
		local name
		for name in "$GATEWAY" "$FILER" "$VOLUME_ROLE" "$MASTER"; do
			runtime rm -f "$name" >/dev/null 2>&1 || true
		done
		for name in "${VOLUMES[@]}" "$CONFIG_VOLUME"; do
			runtime volume rm -f "$name" >/dev/null 2>&1 || true
		done
		runtime network rm -f "$NETWORK" >/dev/null 2>&1 || true
	fi
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

start_role() {
	local name="$1" port="$2"
	shift 2
	runtime run -d --name "$name" --network "$NETWORK" --network-alias "$name" \
		"${RESTRICTED[@]}" "$@" >/dev/null
	wait_for_port "$name" "$port" || {
		printf 'REFUSED: %s did not start\n%s\n' "$name" "$(runtime logs "$name" 2>&1 | tail -5)" >&2
		exit 1
	}
}

# Two identities, generated per run and never committed. `setup` is the ground
# truth for seeding and inspecting objects; `signer` plays a remote signer such
# as Lakekeeper's warehouse identity, with read, write, and list over the whole
# test bucket, which is exactly the authority a remote signer lends a client.
write_config() {
	"$PYTHON" - "$1" "$2" <<-'PYTHON'
		import json, secrets, sys

		path, bucket = sys.argv[1], sys.argv[2]

		def identity(name, actions):
		    return {
		        "name": name,
		        "credentials": [{
		            "accessKey": f"{name}{secrets.token_hex(8)}",
		            "secretKey": secrets.token_urlsafe(32),
		        }],
		        "actions": actions,
		    }

		config = {"identities": [
		    identity("setup", ["Admin", "Read", "List", "Tagging", "Write"]),
		    identity("signer", [f"{a}:{bucket}" for a in ("Read", "List", "Tagging", "Write")]),
		]}
		open(path, "w", encoding="utf-8").write(json.dumps(config, indent=2))
	PYTHON
}

seed_config_volume() {
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

# Requirements: L3-API-002
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

	WORK="$(mktemp -d)"
	local config="${WORK}/s3.json"
	local bucket
	bucket="sigcov-$("$PYTHON" -c 'import secrets; print(secrets.token_hex(4))')"
	write_config "$config" "$bucket"
	chmod 0644 "$config"

	printf 'Measuring SigV4 signature coverage of %s\n\n' "$IMAGE"

	runtime network create "$NETWORK" >/dev/null
	local name
	for name in "${VOLUMES[@]}"; do
		runtime volume create "$name" >/dev/null
	done

	start_role "$MASTER" 9333 -v "${VOLUMES[0]}:/data" \
		"$IMAGE" master -mdir=/data -ip="$MASTER"
	start_role "$VOLUME_ROLE" 8080 -v "${VOLUMES[1]}:/data" \
		"$IMAGE" volume -dir=/data -ip="$VOLUME_ROLE" -mserver="${MASTER}:9333" -max=4
	start_role "$FILER" 8888 -v "${VOLUMES[2]}:/data" \
		"$IMAGE" filer -ip="$FILER" -master="${MASTER}:9333" -defaultStoreDir=/data

	seed_config_volume "$config"
	start_role "$GATEWAY" 8333 \
		-v "${CONFIG_VOLUME}:/etc/seaweedfs:ro" -p "127.0.0.1:${S3_HOST_PORT}:8333" \
		"$IMAGE" s3 -filer="${FILER}:8888" -ip.bind=0.0.0.0 -config=/etc/seaweedfs/s3.json

	local waited=0
	while [ "$waited" -lt 40 ]; do
		curl -s -o /dev/null --max-time 5 "http://127.0.0.1:${S3_HOST_PORT}/" && break
		sleep 2
		waited=$((waited + 2))
	done

	local status=0
	"$PYTHON" "${REPO_ROOT}/tests/lib/sigcoverage.py" \
		"http://127.0.0.1:${S3_HOST_PORT}" "$config" "$bucket" || status=$?

	if [ "$status" -ne 0 ]; then
		printf '\nGateway log tail:\n%s\n' "$(runtime logs "$GATEWAY" 2>&1 | tail -15)"
	fi

	local secret
	secret="$("$PYTHON" -c "import json,sys; print(json.load(open(sys.argv[1]))['identities'][1]['credentials'][0]['secretKey'])" "$config")"
	if runtime logs "$GATEWAY" 2>&1 | grep -qF "$secret"; then
		printf 'FAIL  the signer secret key never appears in the gateway log\n'
		status=1
	else
		printf 'ok    the signer secret key never appears in the gateway log\n'
	fi

	return "$status"
}

main "$@"
