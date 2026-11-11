#!/usr/bin/env bash
#
# Qualify STS credential vending in the separated-role production profile.
#
# The gateway runs with operator-supplied static identities (-config), an
# advanced IAM file holding the role, its permission policy, and the STS signing
# key (-iam.config), and a TLS certificate on its only client listener, which
# also serves STS. tests/lib/stschecks.py then attacks the vended sessions:
# table scoping, read-only scoping, policy intersection, trust, forgery,
# expiry, restart persistence, signing-key rotation, and PR 1's unverified
# DeleteObjects body. Every identity, key, certificate, and bucket is generated
# for this run and removed afterwards.
#
# The run takes about 17 minutes, most of it waiting for a 900-second session
# (the AssumeRole minimum) to expire.
#
# Usage:
#   tests/sts.sh
#
# Environment:
#   CONTAINER_RUNTIME  podman (default) or docker
#   IMAGE              image under test (default localhost/seaweedfs-ubi:development)
#   STS_HOST_PORT      host port for the TLS gateway (default 18603)
#   PROBE_HOST_PORT    host port for the default-profile probe (default 18604)

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
IMAGE="${IMAGE:-localhost/seaweedfs-ubi:development}"
STS_HOST_PORT="${STS_HOST_PORT:-18603}"
PROBE_HOST_PORT="${PROBE_HOST_PORT:-18604}"

PYTHON=""
WORK=""
SUFFIX="$$"
PREFIX="seaweedfs-ubi-sts-${SUFFIX}"
NETWORK="${PREFIX}-net"
GATEWAY="${PREFIX}-s3"
PROBE="${PREFIX}-probe"
GATEWAY_CN="seaweedfs-s3.test"

RESTRICTED=(--read-only --cap-drop=ALL --security-opt=no-new-privileges)

runtime() {
	MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$CONTAINER_RUNTIME" "$@"
}

ssl() {
	MSYS2_ARG_CONV_EXCL='/CN=' openssl "$@"
}

passed=0
failed=0

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

cleanup() {
	local name
	for name in "$GATEWAY" "$PROBE" "${PREFIX}-filer" "${PREFIX}-volume" "${PREFIX}-master"; do
		runtime rm -f "$name" >/dev/null 2>&1 || true
	done
	for name in master volume filer config rotated probe; do
		runtime volume rm -f "${PREFIX}-${name}" >/dev/null 2>&1 || true
	done
	runtime network rm -f "$NETWORK" >/dev/null 2>&1 || true
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
		printf 'REFUSED: %s did not start\n%s\n' "$name" "$(runtime logs "$name" 2>&1 | tail -8)" >&2
		exit 1
	}
}

# A private CA valid for one day and a gateway certificate with the SANs the
# client uses. Nothing here outlives the run.
generate_certificates() {
	local dir="$1" output
	if ! output="$(ssl req -x509 -newkey rsa:2048 -nodes -days 1 \
		-keyout "${dir}/ca.key" -out "${dir}/ca.crt" \
		-subj "/CN=seaweedfs-ubi-sts-ca" 2>&1)"; then
		printf 'REFUSED: could not create the CA\n%s\n' "$output" >&2
		return 1
	fi
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

# The static identities, the role, and two STS signing keys (the second for the
# rotation check). The signing key is operator secret material: it is generated
# here, mounted read-only, and never placed in an image or an argument.
write_configs() {
	"$PYTHON" - "$WORK" <<-'PYTHON'
		import base64, json, os, secrets, sys

		work = sys.argv[1]
		tag = secrets.token_hex(4)
		bucket, other = f"sts-warehouse-{tag}", f"sts-other-{tag}"

		def identity(name, actions):
		    return {"name": name, "actions": actions, "credentials": [{
		        "accessKey": f"{name}{secrets.token_hex(8)}",
		        "secretKey": secrets.token_urlsafe(32)}]}

		s3 = {"identities": [
		    identity("setup", ["Admin", "Read", "List", "Tagging", "Write"]),
		    # The catalog's own identity: it reads and writes table metadata in
		    # the warehouse bucket itself, and vends sessions through the role.
		    identity("vendor", [f"{a}:{bucket}" for a in ("Read", "List", "Tagging", "Write")]),
		    identity("outsider", [f"Read:{other}"]),
		]}

		role_arn = "arn:aws:iam::000000000000:role/lakekeeper-vended"
		warehouse = {"Version": "2012-10-17", "Statement": [
		    {"Effect": "Allow",
		     "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:DeleteObject",
		                "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"],
		     "Resource": [f"arn:aws:s3:::{bucket}/tables/*"]},
		    {"Effect": "Allow", "Action": ["s3:ListBucket"],
		     "Resource": [f"arn:aws:s3:::{bucket}"],
		     "Condition": {"StringLike": {"s3:prefix": ["tables/*"]}}},
		    {"Effect": "Allow", "Action": ["s3:GetBucketLocation"],
		     "Resource": [f"arn:aws:s3:::{bucket}"]},
		]}
		trust = {"Version": "2012-10-17", "Statement": [{
		    "Effect": "Allow",
		    "Principal": {"AWS": "arn:aws:iam::000000000000:user/vendor"},
		    "Action": ["sts:AssumeRole"]}]}

		def iam(key):
		    return {
		        "sts": {"tokenDuration": "1h", "maxSessionLength": "12h",
		                "issuer": "seaweedfs-ubi-sts-qualification",
		                "signingKey": base64.b64encode(key).decode()},
		        "policy": {"defaultEffect": "Deny", "storeType": "memory"},
		        "policies": [{"name": "warehouse-tables", "document": warehouse}],
		        "roles": [{"roleName": "lakekeeper-vended", "roleArn": role_arn,
		                   "trustPolicy": trust, "attachedPolicies": ["warehouse-tables"]}],
		    }

		first, second = secrets.token_bytes(32), secrets.token_bytes(32)
		os.makedirs(os.path.join(work, "rotated"))
		for path, data in (
		    ("s3.json", s3), ("iam.json", iam(first)),
		    (os.path.join("rotated", "iam.json"), iam(second)),
		    ("run.json", {"bucket": bucket, "other_bucket": other}),
		):
		    with open(os.path.join(work, path), "w", encoding="utf-8") as handle:
		        json.dump(data, handle, indent=2)
		# Kept only so the log check can search for both keys.
		with open(os.path.join(work, "signing-keys"), "w", encoding="utf-8") as handle:
		    for key in (first, second):
		        handle.write(base64.b64encode(key).decode() + "\n")
		# A security.toml that makes a signing key available to upstream's
		# implicit STS path, for the default-profile probe.
		with open(os.path.join(work, "security.toml"), "w", encoding="utf-8") as handle:
		    handle.write('[jwt.filer_signing]\nkey = "%s"\n' % secrets.token_urlsafe(32))
	PYTHON
}

# Seed a named volume from a tar stream: portable across rootless runtimes.
seed_volume() {
	local volume="$1" directory="$2"
	shift 2
	runtime volume create "$volume" >/dev/null
	local seeder
	seeder="$(runtime create -v "${volume}:/cfg" "$IMAGE" version)"
	"$PYTHON" - "$directory" "$@" <<-'PYTHON' | runtime cp - "${seeder}:/cfg"
		import io, os, sys, tarfile
		directory, names = sys.argv[1], sys.argv[2:]
		buffer = io.BytesIO()
		with tarfile.open(fileobj=buffer, mode="w") as archive:
		    for name in names:
		        source, _, target = name.partition("=")
		        data = open(os.path.join(directory, source), "rb").read()
		        info = tarfile.TarInfo(target or source)
		        info.size = len(data)
		        info.mode = 0o644
		        archive.addfile(info, io.BytesIO(data))
		sys.stdout.buffer.write(buffer.getvalue())
	PYTHON
	runtime rm -f "$seeder" >/dev/null 2>&1 || true
}

start_gateway() {
	local volume="$1"
	start_role "$GATEWAY" 8333 -v "${volume}:/etc/seaweedfs:ro" \
		-p "127.0.0.1:${STS_HOST_PORT}:8333" \
		"$IMAGE" s3 -filer="${PREFIX}-filer:8888" -ip.bind=0.0.0.0 \
		-config=/etc/seaweedfs/s3.json -iam.config=/etc/seaweedfs/iam.json \
		-cert.file=/etc/seaweedfs/gateway.crt -key.file=/etc/seaweedfs/gateway.key
	local waited=0
	while [ "$waited" -lt 60 ]; do
		curl -s -o /dev/null --max-time 5 --cacert "${WORK}/ca.crt" \
			"https://127.0.0.1:${STS_HOST_PORT}/" && return 0
		sleep 2
		waited=$((waited + 2))
	done
	printf 'REFUSED: the TLS gateway did not answer\n%s\n' "$(runtime logs "$GATEWAY" 2>&1 | tail -8)" >&2
	exit 1
}

checks() {
	"$PYTHON" "${REPO_ROOT}/tests/lib/stschecks.py" "$1" \
		"https://127.0.0.1:${STS_HOST_PORT}" "${WORK}/ca.crt" "${WORK}/s3.json" \
		"${WORK}/run.json" "${WORK}/state.json"
}

# The default image profile, with a signing key made available through
# security.toml, must not serve STS: the entrypoint disables upstream's
# implicit IAM/STS unless the operator configures it explicitly.
probe_default_profile() {
	seed_volume "${PREFIX}-probe" "$WORK" s3.json security.toml
	start_role "$PROBE" 8333 -v "${PREFIX}-probe:/etc/seaweedfs:ro" \
		-p "127.0.0.1:${PROBE_HOST_PORT}:8333" \
		"$IMAGE" s3 -filer="${PREFIX}-filer:8888" -ip.bind=0.0.0.0 -config=/etc/seaweedfs/s3.json
	local cmdline
	cmdline="$(runtime exec "$PROBE" cat /proc/1/cmdline 2>/dev/null | tr '\0' ' ')"
	if [[ " $cmdline " == *" -iam=false "* ]]; then
		ok "the default s3 profile disables upstream's implicit IAM and STS (-iam=false)"
	else
		bad "the default s3 profile disables upstream's implicit IAM and STS (-iam=false)" "$cmdline"
	fi
	local status=0
	"$PYTHON" - "http://127.0.0.1:${PROBE_HOST_PORT}" "${WORK}/s3.json" 		"${REPO_ROOT}/tests/lib" <<-'PYTHON' || status=$?
		import json, sys, urllib.parse
		sys.path.insert(0, sys.argv[3])
		from sigcoverage import Signer, send
		endpoint, config = sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))
		setup = next(i for i in config["identities"] if i["name"] == "setup")["credentials"][0]
		host = urllib.parse.urlparse(endpoint).netloc
		failures = 0
		for action in ("AssumeRole", "GetCallerIdentity"):
		    body = urllib.parse.urlencode({"Version": "2011-06-15", "Action": action,
		                                   "RoleSessionName": "probe"}).encode()
		    signer = Signer(host, setup["accessKey"], setup["secretKey"], service="sts")
		    reply = send(endpoint, signer.sign(
		        "POST", "/", headers={"content-type": "application/x-www-form-urlencoded"},
		        body=body, payload_header=False))
		    served = reply.status == 200 or b"<Credentials>" in reply.body \
		        or b"GetCallerIdentityResult" in reply.body
		    verdict = "FAIL " if served else "ok   "
		    failures += served
		    print(f"{verdict} the default profile does not serve STS {action} to an admin "
		          f"over plaintext (HTTP {reply.status})")
		sys.exit(1 if failures else 0)
	PYTHON
	if [ "$status" -eq 0 ]; then
		passed=$((passed + 2))
	else
		failed=$((failed + 1))
	fi
	runtime rm -f "$PROBE" >/dev/null 2>&1 || true
}

# Requirements: L3-API-003
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
	write_configs
	cp "${WORK}/gateway.crt" "${WORK}/gateway.key" "${WORK}/rotated/"
	cp "${WORK}/s3.json" "${WORK}/rotated/"

	printf 'Qualifying STS credential vending on %s\n\n' "$IMAGE"

	runtime network create "$NETWORK" >/dev/null
	local name
	for name in master volume filer; do
		runtime volume create "${PREFIX}-${name}" >/dev/null
	done
	start_role "${PREFIX}-master" 9333 -v "${PREFIX}-master:/data" \
		"$IMAGE" master -mdir=/data -ip="${PREFIX}-master"
	start_role "${PREFIX}-volume" 8080 -v "${PREFIX}-volume:/data" \
		"$IMAGE" volume -dir=/data -ip="${PREFIX}-volume" -mserver="${PREFIX}-master:9333" -max=8
	start_role "${PREFIX}-filer" 8888 -v "${PREFIX}-filer:/data" \
		"$IMAGE" filer -ip="${PREFIX}-filer" -master="${PREFIX}-master:9333" -defaultStoreDir=/data

	probe_default_profile

	seed_volume "${PREFIX}-config" "$WORK" s3.json iam.json gateway.crt gateway.key
	seed_volume "${PREFIX}-rotated" "${WORK}/rotated" s3.json iam.json gateway.crt gateway.key
	start_gateway "${PREFIX}-config"

	local ports
	ports="$(listening_ports "$GATEWAY" | sort -n | tr '\n' ' ')"
	if [ "$ports" = "8333 18333 " ]; then
		ok "the STS-enabled gateway listens only on 8333 (TLS, S3 and STS) and 18333 (gRPC)"
	else
		bad "the STS-enabled gateway listens only on 8333 and 18333" "listening: ${ports}"
	fi

	local status=0
	checks issue || status=$?

	printf '\nRestarting the gateway with the same signing key\n'
	runtime restart "$GATEWAY" >/dev/null
	wait_for_port "$GATEWAY" 8333 || bad "the gateway restarts"
	sleep 3
	checks restart || status=$?

	printf '\nWaiting for the short session to expire\n'
	checks expire || status=$?

	# Logs are checked before the rotation restart replaces the container.
	local secret leaked=false
	while IFS= read -r secret; do
		[ -n "$secret" ] || continue
		runtime logs "$GATEWAY" 2>&1 | grep -qF -- "$secret" && leaked=true
	done < <(cat "${WORK}/signing-keys"; "$PYTHON" - "${WORK}/s3.json" "${WORK}/state.json" <<-'PYTHON'
		import json, sys
		for identity in json.load(open(sys.argv[1], encoding="utf-8"))["identities"]:
		    print(identity["credentials"][0]["secretKey"])
		state = json.load(open(sys.argv[2], encoding="utf-8"))
		for name in ("scoped", "short"):
		    if state.get(name):
		        print(state[name]["SecretAccessKey"])
		        print(state[name]["SessionToken"])
	PYTHON
	)
	if [ "$leaked" = true ]; then
		bad "no signing key, static secret, session secret, or session token appears in the gateway log"
	else
		ok "no signing key, static secret, session secret, or session token appears in the gateway log"
	fi

	printf '\nRotating the STS signing key\n'
	runtime rm -f "$GATEWAY" >/dev/null
	start_gateway "${PREFIX}-rotated"
	checks rotated || status=$?

	if [ "$status" -ne 0 ] || [ "$failed" -ne 0 ]; then
		printf '\nGateway log tail:\n%s\n' "$(runtime logs "$GATEWAY" 2>&1 | tail -20)"
	fi
	printf '\nShell-level checks: %s passed, %s failed\n' "$passed" "$failed"
	[ "$status" -eq 0 ] && [ "$failed" -eq 0 ]
}

main "$@"
