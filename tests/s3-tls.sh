#!/usr/bin/env bash
#
# Qualify TLS on the client-facing S3 listener.
#
# Every other suite in this repository drives the S3 API over plain HTTP, so
# until now nothing has shown that the image can terminate TLS at all, or that a
# client verifying a private CA actually gets what it asked for.
#
# It also pins a configuration hazard. Supplying a certificate and key with no
# -port.https upgrades the main port to HTTPS and stops serving plaintext.
# Supplying -port.https as well leaves the plaintext port open beside the TLS
# one, which is easy to reach for and hard to notice. The entrypoint refuses
# that shape by default; this suite first asserts the refusal, then opts out so
# the measured upstream behavior remains pinned.
#
# Usage:
#   tests/s3-tls.sh
#
# Environment:
#   CONTAINER_RUNTIME  podman (default) or docker
#   IMAGE              image under test (default localhost/seaweedfs-ubi:development)

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"

PYTHON=""
WORK=""
SUFFIX="$$"
PREFIX="seaweedfs-ubi-tls-${SUFFIX}"
NETWORK="${PREFIX}-net"

# The certificate is issued for this name, and the client asks for this name, so
# hostname verification is genuinely exercised rather than bypassed.
GATEWAY_CN="seaweedfs-s3.test"
TLS_PORT=18601
PLAIN_PORT=18602

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

ssl() {
	MSYS2_ARG_CONV_EXCL='/CN=' openssl "$@"
}

RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)

passed=0
failed=0

cleanup() {
	local name
	for name in s3tls s3plain filer volume master; do
		runtime rm -f "${PREFIX}-${name}" >/dev/null 2>&1 || true
	done
	for name in master volume filer config; do
		runtime volume rm -f "${PREFIX}-${name}" >/dev/null 2>&1 || true
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

# Two CAs. The second never signs anything used by the server, and exists so a
# client can be given a trust anchor that should not work -- the only way to show
# that verification is real rather than incidental.
generate_certificates() {
	local dir="$1" output
	for ca in ca other-ca; do
		if ! output="$(ssl req -x509 -newkey rsa:2048 -nodes -days 1 \
			-keyout "${dir}/${ca}.key" -out "${dir}/${ca}.crt" \
			-subj "/CN=seaweedfs-ubi-${ca}" 2>&1)"; then
			printf 'REFUSED: could not create %s\n%s\n' "$ca" "$output" >&2
			return 1
		fi
	done

	# A SAN is required: modern clients ignore the common name entirely.
	cat >"${dir}/gateway.cnf" <<-CNF
		[req]
		distinguished_name = dn
		[dn]
		[ext]
		subjectAltName = DNS:${GATEWAY_CN}, DNS:localhost, IP:127.0.0.1
		extendedKeyUsage = serverAuth
	CNF

	if ! output="$(ssl req -newkey rsa:2048 -nodes \
		-keyout "${dir}/gateway.key" -out "${dir}/gateway.csr" \
		-subj "/CN=${GATEWAY_CN}" -config "${dir}/gateway.cnf" 2>&1)"; then
		printf 'REFUSED: could not create the gateway key\n%s\n' "$output" >&2
		return 1
	fi
	if ! output="$(ssl x509 -req -in "${dir}/gateway.csr" -days 1 \
		-CA "${dir}/ca.crt" -CAkey "${dir}/ca.key" -CAcreateserial \
		-extfile "${dir}/gateway.cnf" -extensions ext \
		-out "${dir}/gateway.crt" 2>&1)"; then
		printf 'REFUSED: could not sign the gateway certificate\n%s\n' "$output" >&2
		return 1
	fi
}

seed_config_volume() {
	runtime volume create "${PREFIX}-config" >/dev/null
	local seeder
	seeder="$(runtime create -v "${PREFIX}-config:/cfg" "$IMAGE" version)"
	"$PYTHON" - "$WORK" <<-'PYTHON' | runtime cp - "${seeder}:/cfg"
		import io, os, sys, tarfile
		directory = sys.argv[1]
		buffer = io.BytesIO()
		with tarfile.open(fileobj=buffer, mode="w") as archive:
		    for name in ("s3.json", "gateway.crt", "gateway.key", "ca.crt"):
		        data = open(os.path.join(directory, name), "rb").read()
		        info = tarfile.TarInfo(name)
		        info.size = len(data)
		        info.mode = 0o644
		        archive.addfile(info, io.BytesIO(data))
		sys.stdout.buffer.write(buffer.getvalue())
	PYTHON
	runtime rm -f "$seeder" >/dev/null 2>&1 || true
}

main() {
	PYTHON="$(resolve_python)" || {
		printf 'REFUSED: a Python 3 interpreter is required\n' >&2
		exit 2
	}
	command -v openssl >/dev/null 2>&1 || {
		printf 'REFUSED: openssl is required\n' >&2
		exit 2
	}
	runtime image exists "$IMAGE" 2>/dev/null || {
		printf 'REFUSED: %s does not exist. Run scripts/build.sh first.\n' "$IMAGE" >&2
		exit 2
	}

	WORK="$(mktemp -d)"
	generate_certificates "$WORK"
	"$PYTHON" - "${WORK}/s3.json" <<-'PYTHON'
		import json, secrets, sys
		config = {"identities": [{
		    "name": "setup",
		    "credentials": [{
		        "accessKey": "tls" + secrets.token_hex(8),
		        "secretKey": secrets.token_urlsafe(32),
		    }],
		    "actions": ["Admin", "Read", "List", "Tagging", "Write"],
		}]}
		open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(config, indent=2))
	PYTHON

	printf 'Qualifying TLS on the S3 listener of %s\n\n' "$IMAGE"

	runtime network create "$NETWORK" >/dev/null
	local name
	for name in master volume filer; do
		runtime volume create "${PREFIX}-${name}" >/dev/null
	done
	seed_config_volume

	runtime run -d --name "${PREFIX}-master" --network "$NETWORK" \
		--network-alias "${PREFIX}-master" "${RESTRICTED[@]}" \
		-v "${PREFIX}-master:/data" \
		"$IMAGE" master -mdir=/data -ip="${PREFIX}-master" >/dev/null
	wait_for_port "${PREFIX}-master" 9333 || {
		printf 'REFUSED: master did not start\n' >&2
		exit 1
	}
	runtime run -d --name "${PREFIX}-volume" --network "$NETWORK" \
		--network-alias "${PREFIX}-volume" "${RESTRICTED[@]}" \
		-v "${PREFIX}-volume:/data" \
		"$IMAGE" volume -dir=/data -ip="${PREFIX}-volume" \
		-mserver="${PREFIX}-master:9333" -max=10 >/dev/null
	wait_for_port "${PREFIX}-volume" 8080 || {
		printf 'REFUSED: volume did not start\n' >&2
		exit 1
	}
	runtime run -d --name "${PREFIX}-filer" --network "$NETWORK" \
		--network-alias "${PREFIX}-filer" "${RESTRICTED[@]}" \
		-v "${PREFIX}-filer:/data" \
		"$IMAGE" filer -ip="${PREFIX}-filer" -master="${PREFIX}-master:9333" \
		-defaultStoreDir=/data >/dev/null
	wait_for_port "${PREFIX}-filer" 8888 || {
		printf 'REFUSED: filer did not start\n' >&2
		exit 1
	}

	# ---- shape 1: certificate and key, no -port.https ------------------------
	runtime run -d --name "${PREFIX}-s3tls" --network "$NETWORK" \
		--network-alias "${PREFIX}-s3tls" "${RESTRICTED[@]}" \
		-v "${PREFIX}-config:/etc/seaweedfs:ro" \
		-p "127.0.0.1:${TLS_PORT}:8333" \
		"$IMAGE" s3 -filer="${PREFIX}-filer:8888" -ip.bind=0.0.0.0 \
		-config=/etc/seaweedfs/s3.json \
		-cert.file=/etc/seaweedfs/gateway.crt \
		-key.file=/etc/seaweedfs/gateway.key >/dev/null
	wait_for_port "${PREFIX}-s3tls" 8333 || {
		printf 'REFUSED: the TLS gateway did not start\n%s\n' \
			"$(runtime logs "${PREFIX}-s3tls" 2>&1 | tail -8)" >&2
		exit 1
	}
	sleep 5

	# The sub-suite prints its own tally, so it is not folded into this one's
	# count; only its verdict matters here.
	if ! "$PYTHON" "${REPO_ROOT}/tests/lib/tlschecks.py" \
		"$GATEWAY_CN" "$TLS_PORT" "${WORK}/ca.crt" "${WORK}/other-ca.crt" \
		"${WORK}/s3.json"; then
		failed=$((failed + 1))
	fi

	printf '\nChecking the -port.https hazard\n\n'

	local refusal_output refusal_status
	set +e
	refusal_output="$(runtime run --rm --network "$NETWORK" "${RESTRICTED[@]}" \
		-v "${PREFIX}-config:/etc/seaweedfs:ro" \
		"$IMAGE" s3 -filer="${PREFIX}-filer:8888" -ip.bind=0.0.0.0 \
		-config=/etc/seaweedfs/s3.json \
		-cert.file=/etc/seaweedfs/gateway.crt \
		-key.file=/etc/seaweedfs/gateway.key \
		-port.https=8334 2>&1)"
	refusal_status=$?
	set -e
	if [ "$refusal_status" -eq 78 ] &&
		printf '%s' "$refusal_output" | grep -qi 'serving plaintext'; then
		ok "the entrypoint refuses the dual plaintext and TLS listener shape by default"
	else
		bad "the entrypoint refuses the dual plaintext and TLS listener shape by default" \
			"expected exit 78 and a plaintext diagnostic, got ${refusal_status}" \
			"${refusal_output}"
	fi

	# ---- shape 2: explicit opt-out exposes the measured upstream behavior ----
	runtime run -d --name "${PREFIX}-s3plain" --network "$NETWORK" \
		--network-alias "${PREFIX}-s3plain" "${RESTRICTED[@]}" \
		-v "${PREFIX}-config:/etc/seaweedfs:ro" \
		-e SEAWEEDFS_UBI_ALLOW_PLAINTEXT_BESIDE_TLS=true \
		-p "127.0.0.1:${PLAIN_PORT}:8333" \
		"$IMAGE" s3 -filer="${PREFIX}-filer:8888" -ip.bind=0.0.0.0 \
		-config=/etc/seaweedfs/s3.json \
		-cert.file=/etc/seaweedfs/gateway.crt \
		-key.file=/etc/seaweedfs/gateway.key \
		-port.https=8334 >/dev/null
	wait_for_port "${PREFIX}-s3plain" 8333 || {
		bad "with -port.https set, the behaviour of the plain port can be observed" \
			"the gateway did not start"
		printf '\n%s passed, %s failed\n' "$passed" "$failed"
		[ "$failed" -eq 0 ] || exit 1
		return 0
	}
	sleep 5

	local ports
	ports="$(listening_ports "${PREFIX}-s3plain" | tr '\n' ' ')"
	if printf '%s' "$ports" | grep -qw 8333 && printf '%s' "$ports" | grep -qw 8334; then
		ok "setting -port.https leaves the plaintext port listening beside the TLS one (${ports%% })"
	else
		bad "setting -port.https leaves the plaintext port listening beside the TLS one" \
			"observed ports: ${ports}" \
			"if plaintext is no longer served, upstream changed this: update docs/TLS.md"
	fi

	# Plaintext beside TLS is only a hazard if the plain port really serves the
	# API. Prove it does rather than inferring it from an open socket.
	if "$PYTHON" - "http://127.0.0.1:${PLAIN_PORT}" "${WORK}/s3.json" <<-'PYTHON'
		import json, sys
		sys.path.insert(0, "tests/lib")
		from s3client import S3Client
		config = json.load(open(sys.argv[2], encoding="utf-8"))
		c = config["identities"][0]["credentials"][0]
		client = S3Client(sys.argv[1], c["accessKey"], c["secretKey"])
		sys.exit(0 if client.list_objects("tlsprobe").status in (200, 404) else 1)
	PYTHON
	then
		ok "the plaintext port really does serve the S3 API, so the hazard is live"
	else
		bad "the plaintext port really does serve the S3 API, so the hazard is live" \
			"it did not respond, so the exposure may be narrower than documented"
	fi

	printf '\n%s passed, %s failed\n' "$passed" "$failed"
	[ "$failed" -eq 0 ] || exit 1
}

main "$@"
