#!/usr/bin/env bash
#
# Qualify the S3 API against a real client, with real credentials.
#
# tests/cluster.sh proves the roles start and reach each other. It does not send
# a single signed request, so it cannot tell a gateway that authenticates from
# one that merely refused to start without a config file. This does: it drives
# the API with three identities and an unsigned caller, and checks that the
# right ones are allowed and the rest are refused.
#
# It also verifies the two upstream defaults this image turns off, at the API
# level rather than by reading the process arguments. A flag that is passed but
# has no effect would look identical in /proc/1/cmdline.
#
# Usage:
#   tests/s3.sh [--keep]
#
# Environment:
#   CONTAINER_RUNTIME  podman (default) or docker
#   IMAGE              image under test (default localhost/seaweedfs-ubi:development)
#   S3_HOST_PORT       host port for the gateway (default 18333)

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"
S3_HOST_PORT="${S3_HOST_PORT:-18333}"

PYTHON=""
WORK=""

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)

SUFFIX="$$"
NETWORK="seaweedfs-ubi-s3net-${SUFFIX}"
MASTER="seaweedfs-ubi-s3-master-${SUFFIX}"
VOLUME_ROLE="seaweedfs-ubi-s3-volume-${SUFFIX}"
FILER="seaweedfs-ubi-s3-filer-${SUFFIX}"
GATEWAY="seaweedfs-ubi-s3-gateway-${SUFFIX}"
VOLUMES=("s3vol-master-${SUFFIX}" "s3vol-volume-${SUFFIX}" "s3vol-filer-${SUFFIX}")
CONFIG_VOLUME="s3vol-config-${SUFFIX}"

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
	# The config holds real credentials for the life of the run, so it goes
	# whether or not the cluster is kept.
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

# Credentials are generated per run and never committed. Two tenants scoped to
# their own bucket, plus an administrator that creates them, which is what makes
# the isolation check meaningful rather than a test of one identity against
# itself.
write_config() {
	"$PYTHON" - "$1" <<-'PYTHON'
		import json, secrets, sys

		def identity(name, bucket=None):
		    entry = {
		        "name": name,
		        "credentials": [{
		            "accessKey": f"{name}{secrets.token_hex(8)}",
		            "secretKey": secrets.token_urlsafe(32),
		        }],
		    }
		    if bucket is None:
		        entry["actions"] = ["Admin", "Read", "List", "Tagging", "Write"]
		    else:
		        entry["actions"] = [
		            f"{action}:{bucket}"
		            for action in ("Admin", "Read", "List", "Tagging", "Write")
		        ]
		    return entry

		config = {"identities": [
		    identity("setup"),
		    identity("alpha", "alpha"),
		    identity("beta", "beta"),
		]}
		open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(config, indent=2))
	PYTHON
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

	WORK="$(mktemp -d)"
	local config="${WORK}/s3.json"
	write_config "$config"
	chmod 0644 "$config"

	printf 'Qualifying the S3 API of %s\n\n' "$IMAGE"

	runtime network create "$NETWORK" >/dev/null
	local name
	for name in "${VOLUMES[@]}"; do
		runtime volume create "$name" >/dev/null
	done

	runtime run -d --name "$MASTER" --network "$NETWORK" --network-alias "$MASTER" \
		"${RESTRICTED[@]}" -v "${VOLUMES[0]}:/data" \
		"$IMAGE" master -mdir=/data -ip="$MASTER" >/dev/null
	wait_for_port "$MASTER" 9333 || {
		printf 'REFUSED: the master did not start\n%s\n' "$(runtime logs "$MASTER" 2>&1 | tail -5)" >&2
		exit 1
	}

	runtime run -d --name "$VOLUME_ROLE" --network "$NETWORK" --network-alias "$VOLUME_ROLE" \
		"${RESTRICTED[@]}" -v "${VOLUMES[1]}:/data" \
		"$IMAGE" volume -dir=/data -ip="$VOLUME_ROLE" -mserver="${MASTER}:9333" -max=4 >/dev/null
	wait_for_port "$VOLUME_ROLE" 8080 || {
		printf 'REFUSED: the volume server did not start\n%s\n' "$(runtime logs "$VOLUME_ROLE" 2>&1 | tail -5)" >&2
		exit 1
	}

	runtime run -d --name "$FILER" --network "$NETWORK" --network-alias "$FILER" \
		"${RESTRICTED[@]}" -v "${VOLUMES[2]}:/data" \
		"$IMAGE" filer -ip="$FILER" -master="${MASTER}:9333" -defaultStoreDir=/data >/dev/null
	wait_for_port "$FILER" 8888 || {
		printf 'REFUSED: the filer did not start\n%s\n' "$(runtime logs "$FILER" 2>&1 | tail -5)" >&2
		exit 1
	}

	# The config reaches the gateway through a volume, seeded from a tar stream on
	# stdin. Neither a bind mount nor a host-path copy is portable: a rootless
	# machine VM sees only part of the host filesystem, so both fail wherever the
	# engine cannot resolve the path the shell produced. A stream has no path to
	# resolve and behaves identically on every runtime and in CI.
	runtime volume create "$CONFIG_VOLUME" >/dev/null
	local seeder
	seeder="$(runtime create -v "${CONFIG_VOLUME}:/cfg" "$IMAGE" version)"
	"$PYTHON" - "$config" <<-'PYTHON' | runtime cp - "${seeder}:/cfg"
		import io, sys, tarfile
		data = open(sys.argv[1], "rb").read()
		buffer = io.BytesIO()
		with tarfile.open(fileobj=buffer, mode="w") as archive:
		    info = tarfile.TarInfo("s3.json")
		    info.size = len(data)
		    # World readable, owned by root: the gateway runs as uid 1000 and only
		    # needs to read it, and a volume seeded as root cannot be altered by
		    # the running container.
		    info.mode = 0o644
		    archive.addfile(info, io.BytesIO(data))
		sys.stdout.buffer.write(buffer.getvalue())
	PYTHON
	runtime rm -f "$seeder" >/dev/null 2>&1 || true

	# Mounted read-only, which is how an operator should supply it.
	runtime run -d --name "$GATEWAY" --network "$NETWORK" --network-alias "$GATEWAY" \
		"${RESTRICTED[@]}" \
		-v "${CONFIG_VOLUME}:/etc/seaweedfs:ro" \
		-p "127.0.0.1:${S3_HOST_PORT}:8333" \
		"$IMAGE" s3 -filer="${FILER}:8888" -ip.bind=0.0.0.0 -config=/etc/seaweedfs/s3.json >/dev/null
	wait_for_port "$GATEWAY" 8333 || {
		printf 'REFUSED: the S3 gateway did not start\n%s\n' "$(runtime logs "$GATEWAY" 2>&1 | tail -5)" >&2
		exit 1
	}

	# The gateway can be listening before the filer is ready to serve it.
	local waited=0
	while [ "$waited" -lt 40 ]; do
		curl -s -o /dev/null --max-time 5 "http://127.0.0.1:${S3_HOST_PORT}/" && break
		sleep 2
		waited=$((waited + 2))
	done

	local status=0
	"$PYTHON" "${REPO_ROOT}/tests/lib/s3client.py" \
		"http://127.0.0.1:${S3_HOST_PORT}" "$config" || status=$?

	if [ "$status" -ne 0 ]; then
		printf '\nGateway log tail:\n%s\n' "$(runtime logs "$GATEWAY" 2>&1 | tail -15)"
	fi

	# A credential must not reach a log, and this is the run where real ones exist.
	local secret
	secret="$("$PYTHON" -c "import json,sys; print(json.load(open(sys.argv[1]))['identities'][1]['credentials'][0]['secretKey'])" "$config")"
	if runtime logs "$GATEWAY" 2>&1 | grep -qF "$secret"; then
		printf 'FAIL  a tenant secret key never appears in the gateway log\n'
		status=1
	else
		printf 'ok    a tenant secret key never appears in the gateway log\n'
	fi

	if [ "$KEEP" = true ]; then
		printf '\nCluster left running (--keep). S3 on http://127.0.0.1:%s\n' "$S3_HOST_PORT"
		printf 'Credentials were in %s and have been removed.\n' "$config"
	fi

	return "$status"
}

main "$@"
