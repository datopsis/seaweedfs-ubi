#!/usr/bin/env bash
# Development-only Iceberg/S3 round trip against lakekeeper-ubi and this image.
# The SeaweedFS profile is standalone: this is not multi-host, replication, or
# inter-component security evidence. No image is published by this test.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"
LAKEKEEPER_IMAGE="${LAKEKEEPER_IMAGE:-localhost/lakekeeper-ubi9:development}"
POSTGRES_IMAGE="docker.io/library/postgres:17-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73"
ENGINE_IMAGE="docker.io/library/python:3.13.7-slim@sha256:5f55cdf0c5d9dc1a415637a5ccc4a9e18663ad203673173b8cda8f8dcacef689"
PREFIX="seaweedfs-ubi-iceberg-$$"
NETWORK="${PREFIX}-net"
STORAGE="${PREFIX}-storage"
DATABASE="${PREFIX}-db"
CATALOG="${PREFIX}-catalog"
ENGINE="${PREFIX}-engine"
DATA_VOLUME="${PREFIX}-data"
CONFIG_VOLUME="${PREFIX}-config"
PYTHON=""
S3_ENDPOINT=""
CATALOG_URL=""

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

cleanup() {
	runtime rm -f "$ENGINE" "$CATALOG" "$DATABASE" "$STORAGE" >/dev/null 2>&1 || true
	runtime volume rm -f "$DATA_VOLUME" >/dev/null 2>&1 || true
	runtime volume rm -f "$CONFIG_VOLUME" >/dev/null 2>&1 || true
	runtime network rm -f "$NETWORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT

refuse() {
	printf 'REFUSED: %s\n' "$*" >&2
	exit 2
}

wait_for() {
	local label="$1" waited=0
	shift
	while [ "$waited" -lt 90 ]; do
		if "$@" >/dev/null 2>&1; then return 0; fi
		sleep 2
		waited=$((waited + 2))
	done
	printf 'FAIL  %s did not become ready\n' "$label" >&2
	runtime logs "$label" 2>&1 | tail -20 >&2 || true
	return 1
}

s3_check() {
	"$PYTHON" - "$REPO_ROOT" "$S3_ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" "$@" <<-'PYTHON'
		import os, sys
		sys.path.insert(0, os.path.join(sys.argv[1], "tests", "lib"))
		from s3client import S3Client
		client = S3Client(sys.argv[2], sys.argv[3], sys.argv[4])
		mode = sys.argv[5]
		if mode == "create":
		    response = client.create_bucket("warehouse")
		    if response.status not in (200, 204, 409):
		        raise SystemExit(f"bucket create: HTTP {response.status} {response.text}")
		elif mode == "deny-anonymous":
		    response = S3Client(sys.argv[2], None, None).list_objects("warehouse")
		    if response.status not in (401, 403):
		        raise SystemExit(f"anonymous warehouse listing: HTTP {response.status}")
		elif mode == "head":
		    location = sys.argv[6]
		    if not location.startswith("s3://warehouse/"):
		        raise SystemExit(f"unexpected location: {location}")
		    key = location.removeprefix("s3://warehouse/")
		    response = client.request("HEAD", f"/warehouse/{key}")
		    if response.status != 200:
		        raise SystemExit(f"object head: HTTP {response.status} ({key})")
		else:
		    raise SystemExit(f"unknown S3 check: {mode}")
	PYTHON
}

api() {
	local method="$1" path="$2"
	shift 2
	curl --fail-with-body --silent --show-error --request "$method" "${CATALOG_URL}${path}" "$@"
}

start_engine() {
	# Runtime installation is a development fixture, not a hermetic or release
	# toolchain. Version and base-image pins are recorded; transitive wheels are
	# not yet hash-locked, so this result cannot close candidate evidence.
	runtime run -d --name "$ENGINE" --network "$NETWORK" --read-only \
		--user 1000:1000 --cap-drop=ALL --security-opt=no-new-privileges \
		--tmpfs /tmp:rw,nosuid,nodev,size=512m,mode=1777 \
		-e "CATALOG_URI=http://${CATALOG}:8181/catalog" \
		-e "S3_ENDPOINT=http://${STORAGE}:8333" \
		-e "S3_ACCESS_KEY_ID=${ACCESS_KEY}" \
		-e "S3_SECRET_ACCESS_KEY=${SECRET_KEY}" \
		-e PYTHONPATH=/tmp/iceberg \
		-e PIP_DISABLE_PIP_VERSION_CHECK=1 \
		-e PIP_NO_INPUT=1 \
		"$ENGINE_IMAGE" sleep infinity >/dev/null
	runtime exec "$ENGINE" pip install --quiet --no-input --no-cache-dir \
		--target /tmp/iceberg "pyiceberg[s3fs,pyarrow]==0.12.0" "pyarrow==25.0.1"
}

run_engine() {
	runtime exec -i "$ENGINE" python - "$1" \
		<"${REPO_ROOT}/tests/lib/iceberg_roundtrip.py"
}

seed_s3_config() {
	local seeder
	runtime volume create "$CONFIG_VOLUME" >/dev/null
	seeder="$(runtime create -v "${CONFIG_VOLUME}:/cfg" "$IMAGE" version)"
	"$PYTHON" - "$ACCESS_KEY" "$SECRET_KEY" <<-'PYTHON' | runtime cp - "${seeder}:/cfg"
		import io, json, sys, tarfile
		config = {"identities": [{
		    "name": "iceberg",
		    "credentials": [{"accessKey": sys.argv[1], "secretKey": sys.argv[2]}],
		    "actions": ["Admin", "Read", "Write", "List", "Tagging"],
		}]}
		data = json.dumps(config).encode()
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
	runtime rm -f "$seeder" >/dev/null
}

main() {
	for tool in "$CONTAINER_RUNTIME" curl; do
		command -v "$tool" >/dev/null 2>&1 || refuse "$tool is required"
	done
	for PYTHON in python3 python; do
		command -v "$PYTHON" >/dev/null 2>&1 && break
	done
	command -v "$PYTHON" >/dev/null 2>&1 || refuse "Python 3 is required"
	for image in "$IMAGE" "$LAKEKEEPER_IMAGE"; do
		runtime image exists "$image" || refuse "build $image before running this test"
	done
	ACCESS_KEY="iceberg$("$PYTHON" -c 'import secrets; print(secrets.token_hex(12))')"
	SECRET_KEY="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(36))')"
	POSTGRES_PASSWORD="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(36))')"
	ENCRYPTION_KEY="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(36))')"
	local database_url="postgres://lakekeeper:${POSTGRES_PASSWORD}@${DATABASE}:5432/lakekeeper"
	runtime network create "$NETWORK" >/dev/null
	runtime volume create "$DATA_VOLUME" >/dev/null
	seed_s3_config
	runtime run -d --name "$STORAGE" --network "$NETWORK" --network-alias "$STORAGE" \
		--read-only --cap-drop=ALL --security-opt=no-new-privileges \
		-v "${DATA_VOLUME}:/data" -v "${CONFIG_VOLUME}:/etc/seaweedfs:ro" \
		-p 127.0.0.1::8333 \
		-e SEAWEEDFS_UBI_STANDALONE=true \
		"$IMAGE" mini -dir=/data -s3.config=/etc/seaweedfs/s3.json >/dev/null
	local s3_binding
	s3_binding="$(runtime port "$STORAGE" 8333/tcp)"
	S3_ENDPOINT="http://127.0.0.1:${s3_binding##*:}"
	wait_for "$STORAGE" s3_check create
	s3_check deny-anonymous
	printf 'ok    authenticated warehouse bucket exists in guarded standalone S3\n'

	runtime run -d --name "$DATABASE" --network "$NETWORK" --network-alias "$DATABASE" \
		-e POSTGRES_USER=lakekeeper -e POSTGRES_DB=lakekeeper \
		-e "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" "$POSTGRES_IMAGE" >/dev/null
	wait_for "$DATABASE" runtime exec "$DATABASE" pg_isready -U lakekeeper -d lakekeeper
	runtime run --rm --network "$NETWORK" --read-only --cap-drop=ALL \
		--security-opt=no-new-privileges \
		-e "LAKEKEEPER__PG_DATABASE_URL_WRITE=${database_url}" \
		-e "LAKEKEEPER__PG_ENCRYPTION_KEY=${ENCRYPTION_KEY}" \
		"$LAKEKEEPER_IMAGE" migrate >/dev/null
	runtime run -d --name "$CATALOG" --network "$NETWORK" --network-alias "$CATALOG" \
		--read-only --cap-drop=ALL --security-opt=no-new-privileges \
		-p 127.0.0.1::8181 \
		-e "LAKEKEEPER__PG_DATABASE_URL_WRITE=${database_url}" \
		-e "LAKEKEEPER__PG_ENCRYPTION_KEY=${ENCRYPTION_KEY}" \
		"$LAKEKEEPER_IMAGE" serve >/dev/null
	wait_for "$CATALOG" runtime exec "$CATALOG" lakekeeper healthcheck -s
	local catalog_binding
	catalog_binding="$(runtime port "$CATALOG" 8181/tcp)"
	CATALOG_URL="http://127.0.0.1:${catalog_binding##*:}"
	api POST /management/v1/bootstrap -H 'content-type: application/json' \
		--data '{"accept-terms-of-use":true}' >/dev/null
	local profile rejected response warehouse_id
	profile="{\"type\":\"s3\",\"bucket\":\"warehouse\",\"region\":\"local\",\"sts-enabled\":false,\"flavor\":\"s3-compat\",\"endpoint\":\"http://${STORAGE}:8333\",\"path-style-access\":true}"
	rejected="$(printf '{"warehouse-name":"rejected","storage-profile":%s,"storage-credential":{"type":"s3","credential-type":"access-key","access-key-id":"wrong","secret-access-key":"wrong"}}' "$profile" |
		curl --silent --show-error --request POST "${CATALOG_URL}/management/v1/warehouse" -H 'content-type: application/json' --data-binary @- -o /dev/null -w '%{http_code}')"
	case "$rejected" in 200 | 201) refuse 'catalog accepted invalid S3 credentials' ;; esac
	response="$(printf '{"warehouse-name":"qualification","storage-profile":%s,"storage-credential":{"type":"s3","credential-type":"access-key","access-key-id":"%s","secret-access-key":"%s"}}' "$profile" "$ACCESS_KEY" "$SECRET_KEY" |
		api POST /management/v1/warehouse -H 'content-type: application/json' --data-binary @-)"
	warehouse_id="$(printf '%s' "$response" | "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get("warehouse-id", ""))')"
	[ -n "$warehouse_id" ] || refuse 'catalog did not register the warehouse'
	printf 'ok    Lakekeeper registered the S3 warehouse and rejected invalid credentials\n'

	local written metadata data_file reread
	start_engine
	written="$(run_engine write)"
	printf '%s\n' "$written"
	metadata="$(printf '%s\n' "$written" | sed -n 's/^metadata-location=//p' | head -1)"
	data_file="$(printf '%s\n' "$written" | sed -n 's/^data-file=//p' | head -1)"
	[ -n "$metadata" ] && [ -n "$data_file" ] || refuse 'engine omitted metadata or data file'
	s3_check head "$metadata"
	s3_check head "$data_file"
	printf 'ok    table metadata and Parquet data exist in SeaweedFS\n'
	runtime restart "$CATALOG" >/dev/null
	wait_for "$CATALOG" runtime exec "$CATALOG" lakekeeper healthcheck -s
	reread="$(run_engine read)"
	printf '%s\n' "$reread"
	grep -q 'read: 3 rows round-tripped through PyIceberg' <<<"$reread" || refuse 'rows did not survive catalog restart'
	printf 'ok    independent Iceberg client reread rows after catalog restart\n'
	local secret logs name label index
	local -a secret_values=("$ACCESS_KEY" "$SECRET_KEY" "$POSTGRES_PASSWORD" "$ENCRYPTION_KEY")
	local -a secret_labels=('S3 access-key ID' 'S3 secret key' 'database password' 'catalog encryption key')
	for index in "${!secret_values[@]}"; do
		secret="${secret_values[$index]}"
		label="${secret_labels[$index]}"
		for name in "$STORAGE" "$CATALOG"; do
			logs="$(runtime logs "$name" 2>&1)"
			if grep -Fq -- "$secret" <<<"$logs"; then
				refuse "${label} appeared in ${name} logs"
			fi
		done
	done
	printf 'PASS  development Iceberg/S3 round trip (standalone; not release-candidate evidence)\n'
}

main "$@"
