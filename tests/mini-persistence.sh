#!/usr/bin/env bash
#
# Development-only mini lifecycle evidence. This uses disposable named volumes
# and proves nothing about replication, backup, or multi-node failure.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"
S3_HOST_PORT="${S3_HOST_PORT:-18339}"
PYTHON=""
WORK=""
SUFFIX="$$-${RANDOM}"
CONTAINER="seaweedfs-ubi-mini-persistence-${SUFFIX}"
NETWORK="${CONTAINER}-net"
DATA_VOLUME="${CONTAINER}-data"
FRESH_VOLUME="${CONTAINER}-fresh"
INITIAL_CONFIG="${CONTAINER}-initial-config"
ROTATED_CONFIG="${CONTAINER}-rotated-config"
ENDPOINT="http://127.0.0.1:${S3_HOST_PORT}"
RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)
SHELL_DIRECTORY="/mini-persistence-${SUFFIX}"
CREATED_NETWORK=false
CREATED_DATA=false
CREATED_FRESH=false
CREATED_INITIAL_CONFIG=false
CREATED_ROTATED_CONFIG=false
OWN_CONTAINER=false

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

cleanup() {
	[ "$OWN_CONTAINER" = true ] && runtime rm -f "$CONTAINER" >/dev/null 2>&1 || true
	[ "$CREATED_DATA" = true ] && runtime volume rm "$DATA_VOLUME" >/dev/null 2>&1 || true
	[ "$CREATED_FRESH" = true ] && runtime volume rm "$FRESH_VOLUME" >/dev/null 2>&1 || true
	[ "$CREATED_INITIAL_CONFIG" = true ] && runtime volume rm "$INITIAL_CONFIG" >/dev/null 2>&1 || true
	[ "$CREATED_ROTATED_CONFIG" = true ] && runtime volume rm "$ROTATED_CONFIG" >/dev/null 2>&1 || true
	[ "$CREATED_NETWORK" = true ] && runtime network rm "$NETWORK" >/dev/null 2>&1 || true
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

make_identity() {
	"$PYTHON" - "$1" <<-'PYTHON'
		import json, secrets, sys
		from pathlib import Path

		stem = Path(sys.argv[1])
		access = "mini" + secrets.token_hex(8)
		secret = secrets.token_urlsafe(32)
		stem.with_suffix(".json").write_text(
		    json.dumps({"accessKey": access, "secretKey": secret}),
		    encoding="utf-8",
		)
		stem.with_suffix(".s3.json").write_text(
		    json.dumps({"identities": [{
		        "name": "standalone",
		        "credentials": [{"accessKey": access, "secretKey": secret}],
		        "actions": ["Admin", "Read", "List", "Tagging", "Write"],
		    }]}),
		    encoding="utf-8",
		)
	PYTHON
}

seed_config() {
	local volume="$1" source="$2" seeder
	seeder="$(runtime create -v "${volume}:/cfg" "$IMAGE" version)"
	"$PYTHON" - "${source}.s3.json" <<-'PYTHON' | runtime cp - "${seeder}:/cfg"
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
	runtime rm "$seeder" >/dev/null
}

start_mini() {
	local volume="$1" config_volume="$2"
	OWN_CONTAINER=true
	runtime run -d --name "$CONTAINER" --network "$NETWORK" \
		"${RESTRICTED[@]}" -v "${volume}:/data" \
		-v "${config_volume}:/etc/seaweedfs:ro" \
		-e SEAWEEDFS_UBI_STANDALONE=true \
		-p "127.0.0.1:${S3_HOST_PORT}:8333" \
		"$IMAGE" mini -dir=/data -ip.bind=0.0.0.0 \
		-s3.config=/etc/seaweedfs/s3.json >/dev/null || return 1
	local waited=0
	while [ "$waited" -lt 90 ]; do
		if curl --silent --max-time 3 --output /dev/null "$ENDPOINT/"; then
			return 0
		fi
		[ "$(runtime inspect "$CONTAINER" --format '{{.State.Status}}' 2>/dev/null)" = exited ] && return 1
		sleep 2
		waited=$((waited + 2))
	done
	return 1
}

client_check() {
	local action="$1" identity="$2" old_identity="${3:-}"
	"$PYTHON" - "$REPO_ROOT" "$ENDPOINT" "${identity}.json" "$action" "${old_identity}.json" <<-'PYTHON'
		import json, os, sys
		sys.path.insert(0, os.path.join(sys.argv[1], "tests", "lib"))
		from s3client import S3Client

		identity = json.load(open(sys.argv[3], encoding="utf-8"))
		client = S3Client(sys.argv[2], identity["accessKey"], identity["secretKey"])
		bucket, key = "mini-persistence", "exact-bytes.bin"
		payload = bytes(range(256)) * 16
		action = sys.argv[4]
		if action == "write":
		    response = client.create_bucket(bucket)
		    assert response.status in (200, 204), f"create bucket: HTTP {response.status}"
		    response = client.put_object(bucket, key, payload)
		    assert response.status in (200, 204), f"put object: HTTP {response.status}"
		if action in ("write", "read", "rotated"):
		    response = client.get_object(bucket, key)
		    assert response.status == 200 and response.body == payload, (
		        f"object mismatch: HTTP {response.status}, {len(response.body)} bytes"
		    )
		    anonymous = S3Client(sys.argv[2], None, None).get_object(bucket, key)
		    assert anonymous.status in (401, 403), f"anonymous read: HTTP {anonymous.status}"
		if action == "rotated":
		    prior = json.load(open(sys.argv[5], encoding="utf-8"))
		    old = S3Client(sys.argv[2], prior["accessKey"], prior["secretKey"])
		    denied = old.get_object(bucket, key)
		    assert denied.status in (401, 403), f"old credential: HTTP {denied.status}"
		if action == "absent":
		    response = client.get_object(bucket, key)
		    assert response.status == 404, f"fresh volume object: HTTP {response.status}"
	PYTHON
}

shell_command() {
	printf '%s\n' "$1" | runtime exec -i "$CONTAINER" \
		/usr/local/bin/seaweedfs-entrypoint shell \
		-master=127.0.0.1:9333 -filer=127.0.0.1:8888
}

shell_directory_exists() {
	local listing
	listing="$(shell_command 'fs.ls /')" || return 1
	printf '%s\n' "$listing" | grep -qF "${SHELL_DIRECTORY#/}"
}

diagnose() {
	printf 'Container state: ' >&2
	runtime inspect "$CONTAINER" --format '{{.State.Status}}' >&2 || true
}

assert_no_identity_in_logs() {
	runtime logs "$CONTAINER" 2>&1 | "$PYTHON" -c '
import json, sys
logs = sys.stdin.read()
identities = [json.load(open(path, encoding="utf-8")) for path in sys.argv[1:]]
found = False
for path in sys.argv[1:]:
    identity = json.load(open(path, encoding="utf-8"))
    for field in ("accessKey", "secretKey"):
        if identity[field] in logs:
            print(f"FAIL  {field} appeared in mini logs", file=sys.stderr)
            found = True
if found:
    for line in logs.splitlines():
        if any(value in line for identity in identities for value in identity.values()):
            for identity in identities:
                for value in identity.values():
                    line = line.replace(value, "[REDACTED]")
            print(line[:500], file=sys.stderr)
    raise SystemExit(1)
' "$WORK/initial.json" "$WORK/rotated.json"
}

main() {
	PYTHON="$(resolve_python)" || { printf 'REFUSED: Python 3 is required\n' >&2; exit 2; }
	command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1 || {
		printf 'REFUSED: %s is required\n' "$CONTAINER_RUNTIME" >&2; exit 2;
	}
	command -v curl >/dev/null 2>&1 || { printf 'REFUSED: curl is required\n' >&2; exit 2; }
	runtime image exists "$IMAGE" 2>/dev/null || {
		printf 'REFUSED: %s does not exist. Run scripts/build.sh first.\n' "$IMAGE" >&2; exit 2;
	}
	for resource in "$DATA_VOLUME" "$FRESH_VOLUME" "$INITIAL_CONFIG" "$ROTATED_CONFIG"; do
		if runtime volume exists "$resource"; then
			printf 'REFUSED: test volume already exists: %s\n' "$resource" >&2
			exit 2
		fi
	done
	if runtime container exists "$CONTAINER" || runtime network exists "$NETWORK"; then
		printf 'REFUSED: a generated container or network name already exists\n' >&2
		exit 2
	fi
	WORK="$(mktemp -d)"
	make_identity "$WORK/initial"
	make_identity "$WORK/rotated"
	runtime network create "$NETWORK" >/dev/null
	CREATED_NETWORK=true
	runtime volume create "$DATA_VOLUME" >/dev/null
	CREATED_DATA=true
	runtime volume create "$FRESH_VOLUME" >/dev/null
	CREATED_FRESH=true
	runtime volume create "$INITIAL_CONFIG" >/dev/null
	CREATED_INITIAL_CONFIG=true
	runtime volume create "$ROTATED_CONFIG" >/dev/null
	CREATED_ROTATED_CONFIG=true
	seed_config "$INITIAL_CONFIG" "$WORK/initial"
	seed_config "$ROTATED_CONFIG" "$WORK/rotated"
	printf 'Testing disposable standalone persistence (not cluster durability)\n\n'

	start_mini "$DATA_VOLUME" "$INITIAL_CONFIG" || { diagnose; exit 1; }
	client_check write "$WORK/initial"
	assert_no_identity_in_logs
	printf 'ok    authenticated object bytes are written; anonymous reads are denied\n'
	local shell_result
	shell_result="$(shell_command "fs.mkdir $SHELL_DIRECTORY")"
	if printf '%s\n' "$shell_result" | grep -qi 'error:' || ! shell_directory_exists; then
		printf 'FAIL  weed shell did not create the disposable filer directory\n' >&2
		exit 1
	fi
	printf 'ok    weed shell can create and list a filer directory\n'

	local first_id second_id
	first_id="$(runtime inspect "$CONTAINER" --format '{{.Id}}')"
	runtime stop --time 30 "$CONTAINER" >/dev/null
	runtime rm "$CONTAINER" >/dev/null
	OWN_CONTAINER=false
	start_mini "$DATA_VOLUME" "$INITIAL_CONFIG" || { diagnose; exit 1; }
	second_id="$(runtime inspect "$CONTAINER" --format '{{.Id}}')"
	[ "$first_id" != "$second_id" ] || { printf 'FAIL  container was not replaced\n' >&2; exit 1; }
	client_check read "$WORK/initial"
	assert_no_identity_in_logs
	shell_directory_exists || { printf 'FAIL  shell-created directory did not survive replacement\n' >&2; exit 1; }
	printf 'ok    object bytes and shell-created filer directory survive replacement\n'

	runtime stop --time 30 "$CONTAINER" >/dev/null
	runtime rm "$CONTAINER" >/dev/null
	OWN_CONTAINER=false
	start_mini "$DATA_VOLUME" "$ROTATED_CONFIG" || { diagnose; exit 1; }
	client_check rotated "$WORK/rotated" "$WORK/initial"
	assert_no_identity_in_logs
	printf 'ok    replacement reads external credentials: new key works, old key is denied\n'

	runtime stop --time 30 "$CONTAINER" >/dev/null
	runtime rm "$CONTAINER" >/dev/null
	OWN_CONTAINER=false
	start_mini "$FRESH_VOLUME" "$ROTATED_CONFIG" || { diagnose; exit 1; }
	client_check absent "$WORK/rotated"
	assert_no_identity_in_logs
	if shell_directory_exists; then
		printf 'FAIL  shell-created directory appeared on a fresh volume\n' >&2
		exit 1
	fi
	printf 'ok    fresh volume contains neither the old object nor filer directory\n'
}

main "$@"
