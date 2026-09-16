#!/usr/bin/env bash
#
# Qualify the security boundary between the roles.
#
# SECURITY.md tells operators that without a security.toml anyone who reaches a
# volume server can read and write stored bytes directly, bypassing the S3
# identity model. That claim has never been tested, and neither has the
# mitigation. This does both: it runs the cluster twice, once without the file
# and once with it, and probes the volume server directly each time.
#
# The second run is the one that matters, and not because it is reassuring.
# Upstream states that read JWTs are not supported alongside a filer, and the S3
# topology requires a filer, so a supported deployment can close direct writes
# and cannot close direct reads. The suite asserts that asymmetry rather than
# implying a security.toml settles the question.
#
# Usage:
#   tests/inter-component.sh
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
PHASE_PREFIX="seaweedfs-ubi-ic-${SUFFIX}"

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)

total_failed=0

teardown_phase() {
	local phase="$1" name
	for name in s3 filer volume master; do
		runtime rm -f "${PHASE_PREFIX}-${phase}-${name}" >/dev/null 2>&1 || true
	done
	for name in master volume filer config; do
		runtime volume rm -f "${PHASE_PREFIX}-${phase}-${name}" >/dev/null 2>&1 || true
	done
	runtime network rm -f "${PHASE_PREFIX}-${phase}" >/dev/null 2>&1 || true
}

cleanup() {
	teardown_phase baseline
	teardown_phase secured
	# The CA key and the JWT signing key live here.
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

# A subject like /CN=name looks like an absolute path to Git Bash, which rewrites
# it into a Windows path before openssl sees it. Suppressing conversion wholesale
# is the wrong fix: the -keyout and -out paths genuinely do need converting, or a
# native openssl cannot write them. Exclude only the subject. Inert on Linux.
ssl() {
	MSYS2_ARG_CONV_EXCL='/CN=' openssl "$@"
}

# A throwaway CA and one certificate per role. Generated per run and never
# committed: a checked-in key would be a key everyone has.
#
# Failures are reported rather than swallowed. Silencing openssl once cost an
# afternoon to a subject string the shell had quietly rewritten.
generate_certificates() {
	local dir="$1" output
	if ! output="$(ssl req -x509 -newkey rsa:2048 -nodes -days 1 \
		-keyout "${dir}/ca.key" -out "${dir}/ca.crt" \
		-subj "/CN=seaweedfs-ubi-test-ca" 2>&1)"; then
		printf 'REFUSED: could not create the test CA\n%s\n' "$output" >&2
		return 1
	fi

	local role
	for role in master volume filer s3 client; do
		if ! output="$(ssl req -newkey rsa:2048 -nodes \
			-keyout "${dir}/${role}.key" -out "${dir}/${role}.csr" \
			-subj "/CN=${role}" 2>&1)"; then
			printf 'REFUSED: could not create the %s key\n%s\n' "$role" "$output" >&2
			return 1
		fi
		if ! output="$(ssl x509 -req -in "${dir}/${role}.csr" -days 1 \
			-CA "${dir}/ca.crt" -CAkey "${dir}/ca.key" -CAcreateserial \
			-out "${dir}/${role}.crt" 2>&1)"; then
			printf 'REFUSED: could not sign the %s certificate\n%s\n' "$role" "$output" >&2
			return 1
		fi
	done

	# A second trust domain exists only for the negative client-authentication
	# check. The server never trusts this CA.
	if ! output="$(ssl req -x509 -newkey rsa:2048 -nodes -days 1 \
		-keyout "${dir}/other-ca.key" -out "${dir}/other-ca.crt" \
		-subj "/CN=seaweedfs-ubi-untrusted-ca" 2>&1)"; then
		printf 'REFUSED: could not create the unrelated test CA\n%s\n' "$output" >&2
		return 1
	fi
	if ! output="$(ssl req -newkey rsa:2048 -nodes \
		-keyout "${dir}/other-client.key" -out "${dir}/other-client.csr" \
		-subj "/CN=untrusted-client" 2>&1)"; then
		printf 'REFUSED: could not create the unrelated client key\n%s\n' "$output" >&2
		return 1
	fi
	if ! output="$(ssl x509 -req -in "${dir}/other-client.csr" -days 1 \
		-CA "${dir}/other-ca.crt" -CAkey "${dir}/other-ca.key" -CAcreateserial \
		-out "${dir}/other-client.crt" 2>&1)"; then
		printf 'REFUSED: could not sign the unrelated client certificate\n%s\n' "$output" >&2
		return 1
	fi
}

write_security_toml() {
	local dir="$1" signing_key
	signing_key="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(32))')"
	cat >"${dir}/security.toml" <<-TOML
		# Generated per test run. The signing key and the CA key are ephemeral.
		#
		# jwt.signing protects writes to the volume servers. There is deliberately
		# no jwt.signing.read block: upstream does not support read JWTs alongside
		# a filer, and this topology requires one.
		[jwt.signing]
		key = "${signing_key}"
		expires_after_seconds = 10

		[grpc]
		ca = "/etc/seaweedfs/tls/ca.crt"

		[grpc.master]
		cert = "/etc/seaweedfs/tls/master.crt"
		key = "/etc/seaweedfs/tls/master.key"

		[grpc.volume]
		cert = "/etc/seaweedfs/tls/volume.crt"
		key = "/etc/seaweedfs/tls/volume.key"

		[grpc.filer]
		cert = "/etc/seaweedfs/tls/filer.crt"
		key = "/etc/seaweedfs/tls/filer.key"

		[grpc.s3]
		cert = "/etc/seaweedfs/tls/s3.crt"
		key = "/etc/seaweedfs/tls/s3.key"

		[grpc.client]
		cert = "/etc/seaweedfs/tls/client.crt"
		key = "/etc/seaweedfs/tls/client.key"
	TOML
}

# Configuration reaches the containers as a tar stream, for the same reason as
# in tests/s3.sh: a bind mount depends on host paths the engine may not see.
seed_config_volume() {
	local volume_name="$1" dir="$2" with_security="$3"
	runtime volume create "$volume_name" >/dev/null
	local seeder
	seeder="$(runtime create -v "${volume_name}:/cfg" "$IMAGE" version)"
	"$PYTHON" - "$dir" "$with_security" <<-'PYTHON' | runtime cp - "${seeder}:/cfg"
		import io, os, sys, tarfile
		directory, with_security = sys.argv[1], sys.argv[2] == "true"
		buffer = io.BytesIO()
		with tarfile.open(fileobj=buffer, mode="w") as archive:
		    def add(name, path):
		        data = open(path, "rb").read()
		        info = tarfile.TarInfo(name)
		        info.size = len(data)
		        info.mode = 0o644
		        archive.addfile(info, io.BytesIO(data))
		    add("s3.json", os.path.join(directory, "s3.json"))
		    if with_security:
		        add("security.toml", os.path.join(directory, "security.toml"))
		        for role in ("ca", "master", "volume", "filer", "s3", "client"):
		            for suffix in ("crt", "key"):
		                add(f"tls/{role}.{suffix}", os.path.join(directory, f"{role}.{suffix}"))
		sys.stdout.buffer.write(buffer.getvalue())
	PYTHON
	runtime rm -f "$seeder" >/dev/null 2>&1 || true
}

# SeaweedFS reads security.toml from the working directory or /etc/seaweedfs.
# Mounting the whole directory read-only is how an operator would supply it.
run_phase() {
	local phase="$1" with_security="$2" master_port="$3" volume_port="$4" filer_port="$5" s3_port="$6"
	local master_grpc_port="$7"
	local network="${PHASE_PREFIX}-${phase}"
	local cfg="${PHASE_PREFIX}-${phase}-config"
	local m="${PHASE_PREFIX}-${phase}-master"
	local v="${PHASE_PREFIX}-${phase}-volume"
	local f="${PHASE_PREFIX}-${phase}-filer"
	local s="${PHASE_PREFIX}-${phase}-s3"

	runtime network create "$network" >/dev/null
	local name
	for name in master volume filer; do
		runtime volume create "${PHASE_PREFIX}-${phase}-${name}" >/dev/null
	done
	seed_config_volume "$cfg" "$WORK" "$with_security"

	local config_mount=(-v "${cfg}:/etc/seaweedfs:ro")

	runtime run -d --name "$m" --network "$network" --network-alias "$m" \
		"${RESTRICTED[@]}" "${config_mount[@]}" \
		-v "${PHASE_PREFIX}-${phase}-master:/data" \
		-p "127.0.0.1:${master_port}:9333" \
		-p "127.0.0.1:${master_grpc_port}:19333" \
		"$IMAGE" master -mdir=/data -ip="$m" >/dev/null
	wait_for_port "$m" 9333 || {
		printf 'REFUSED: master did not start in %s\n%s\n' "$phase" "$(runtime logs "$m" 2>&1 | tail -8)" >&2
		return 1
	}

	runtime run -d --name "$v" --network "$network" --network-alias "$v" \
		"${RESTRICTED[@]}" "${config_mount[@]}" \
		-v "${PHASE_PREFIX}-${phase}-volume:/data" \
		-p "127.0.0.1:${volume_port}:8080" \
		"$IMAGE" volume -dir=/data -ip="$v" -mserver="${m}:9333" -max=10 >/dev/null
	wait_for_port "$v" 8080 || {
		printf 'REFUSED: volume did not start in %s\n%s\n' "$phase" "$(runtime logs "$v" 2>&1 | tail -8)" >&2
		return 1
	}

	runtime run -d --name "$f" --network "$network" --network-alias "$f" \
		"${RESTRICTED[@]}" "${config_mount[@]}" \
		-v "${PHASE_PREFIX}-${phase}-filer:/data" \
		-p "127.0.0.1:${filer_port}:8888" \
		"$IMAGE" filer -ip="$f" -master="${m}:9333" -defaultStoreDir=/data >/dev/null
	wait_for_port "$f" 8888 || {
		printf 'REFUSED: filer did not start in %s\n%s\n' "$phase" "$(runtime logs "$f" 2>&1 | tail -8)" >&2
		return 1
	}

	runtime run -d --name "$s" --network "$network" --network-alias "$s" \
		"${RESTRICTED[@]}" "${config_mount[@]}" \
		-p "127.0.0.1:${s3_port}:8333" \
		"$IMAGE" s3 -filer="${f}:8888" -ip.bind=0.0.0.0 -config=/etc/seaweedfs/s3.json >/dev/null
	wait_for_port "$s" 8333 || {
		printf 'REFUSED: s3 did not start in %s\n%s\n' "$phase" "$(runtime logs "$s" 2>&1 | tail -8)" >&2
		return 1
	}

	local waited=0
	while [ "$waited" -lt 40 ]; do
		curl -s -o /dev/null --max-time 5 "http://127.0.0.1:${s3_port}/" && break
		sleep 2
		waited=$((waited + 2))
	done
	return 0
}

main() {
	PYTHON="$(resolve_python)" || {
		printf 'REFUSED: a Python 3 interpreter is required\n' >&2
		exit 2
	}
	command -v openssl >/dev/null 2>&1 || {
		printf 'REFUSED: openssl is required to generate the test CA\n' >&2
		exit 2
	}
	runtime image exists "$IMAGE" 2>/dev/null || {
		printf 'REFUSED: %s does not exist. Run scripts/build.sh first.\n' "$IMAGE" >&2
		exit 2
	}

	WORK="$(mktemp -d)"
	generate_certificates "$WORK"
	write_security_toml "$WORK"

	# One admin identity is enough here; tenant isolation is tests/s3.sh's job.
	"$PYTHON" - "${WORK}/s3.json" <<-'PYTHON'
		import json, secrets, sys
		config = {"identities": [{
		    "name": "setup",
		    "credentials": [{
		        "accessKey": "probe" + secrets.token_hex(8),
		        "secretKey": secrets.token_urlsafe(32),
		    }],
		    "actions": ["Admin", "Read", "List", "Tagging", "Write"],
		}]}
		open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(config, indent=2))
	PYTHON

	local bucket="probe" key="object.txt"

	# ---------------- phase 1: the exposure, demonstrated -------------------
	printf 'Phase 1: no security.toml -- demonstrating the documented exposure\n\n'
	run_phase baseline false 19333 18080 18888 18333 29333 || exit 1
	"$PYTHON" - "http://127.0.0.1:18333" "${WORK}/s3.json" "$bucket" "$key" <<-'PYTHON'
		import json, sys
		sys.path.insert(0, "tests/lib")
		from s3client import S3Client
		config = json.load(open(sys.argv[2], encoding="utf-8"))
		c = config["identities"][0]["credentials"][0]
		client = S3Client(sys.argv[1], c["accessKey"], c["secretKey"])
		client.create_bucket(sys.argv[3])
		response = client.put_object(sys.argv[3], sys.argv[4], b"bytes behind the gateway")
		sys.exit(0 if response.status in (200, 204) else 1)
	PYTHON
	"$PYTHON" "${REPO_ROOT}/tests/lib/directaccess.py" baseline \
		"http://127.0.0.1:19333" "http://127.0.0.1:18080" "http://127.0.0.1:18888" \
		"$bucket" "$key" || total_failed=$((total_failed + 1))
	teardown_phase baseline

	# ---------------- phase 2: the mitigation, and its limit ----------------
	printf '\nPhase 2: security.toml with gRPC mTLS and write JWTs\n\n'
	run_phase secured true 19334 18081 18889 18334 29334 || exit 1
	"$PYTHON" "${REPO_ROOT}/tests/lib/mtlschecks.py" \
		127.0.0.1 29334 "${WORK}/ca.crt" \
		"${WORK}/client.crt" "${WORK}/client.key" \
		"${WORK}/other-client.crt" "${WORK}/other-client.key" ||
		total_failed=$((total_failed + 1))
	if "$PYTHON" - "http://127.0.0.1:18334" "${WORK}/s3.json" "$bucket" "$key" <<-'PYTHON'
		import json, sys
		sys.path.insert(0, "tests/lib")
		from s3client import S3Client
		config = json.load(open(sys.argv[2], encoding="utf-8"))
		c = config["identities"][0]["credentials"][0]
		client = S3Client(sys.argv[1], c["accessKey"], c["secretKey"])
		client.create_bucket(sys.argv[3])
		put = client.put_object(sys.argv[3], sys.argv[4], b"bytes behind the gateway")
		got = client.get_object(sys.argv[3], sys.argv[4])
		sys.exit(0 if put.status in (200, 204) and got.status == 200 else 1)
	PYTHON
	then
		printf 'ok    the cluster still serves S3 with mTLS and write JWTs enabled\n'
	else
		printf 'FAIL  the cluster still serves S3 with mTLS and write JWTs enabled\n'
		total_failed=$((total_failed + 1))
	fi
	"$PYTHON" "${REPO_ROOT}/tests/lib/directaccess.py" secured \
		"http://127.0.0.1:19334" "http://127.0.0.1:18081" "http://127.0.0.1:18889" \
		"$bucket" "$key" || total_failed=$((total_failed + 1))

	printf '\n'
	if [ "$total_failed" -eq 0 ]; then
		printf 'Both phases behaved as documented.\n'
	else
		printf '%s phase(s) did not behave as documented.\n' "$total_failed"
	fi
	[ "$total_failed" -eq 0 ] || exit 1
}

main "$@"
