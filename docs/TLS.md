# TLS and the boundary between the roles

What a `security.toml` actually closes, what it leaves open, and why the
difference matters more than the configuration itself.

Everything below was measured by `tests/inter-component.sh`, which runs the
cluster twice — once without the file and once with it — and probes the volume
server and filer directly each time.

## The short version

**A `security.toml` closes one of four direct-access paths.** It is worth
configuring, and it is not a substitute for network isolation.

| Path bypassing the S3 gateway | Without `security.toml` | With it |
| --- | --- | --- |
| The filer discloses an object's storage location | open | **still open** |
| The filer serves the object's content | open | **still open** |
| A volume server serves an object's bytes by file id | open | **still open** |
| A volume server accepts a write | open | **closed — HTTP 401** |

Anyone who can reach the filer or a volume server can still read every stored
object. The S3 identity model, tenant scoping included, applies only to callers
who arrive through the gateway.

## Why the read paths cannot be closed here

Not an oversight, and not something a future configuration change in this image
will fix. Upstream's own scaffold states it:

> `NOTE: jwt for read is only supported with master+volume setup. Filer does not
> support this mode.`

Read JWTs require a master-and-volume-only deployment. The S3 API requires a
filer. Those two facts are incompatible, so **in any topology that serves S3,
read JWTs are unavailable**, and direct reads stay open by construction.

Write JWTs have no such restriction, which is why the write path closes and the
read path does not.

## What this means for a deployment

The only control for the read paths is the network. That makes the following
requirements rather than recommendations:

- **The master, volume, and filer listeners must not be reachable from any
  network a client can reach.** Only the S3 API faces clients.
- **Reaching a volume server is equivalent to reading every object it holds.**
  Treat the cluster network as holding the same data as the buckets themselves.
- **A tenant boundary is a gateway boundary.** Two tenants isolated at the S3
  layer share one volume network underneath, so anything with cluster-network
  access has no tenant scoping at all.

The Compose stacks in this repository publish only the S3 API, and only on
loopback, for exactly this reason.

## What a `security.toml` does do

Two distinct things, worth separating because they protect different attacks.

**gRPC mTLS** authenticates and encrypts the connections the roles make to each
other. It does not touch the HTTP listeners, which is why it changes none of the
read paths above — those are plain HTTP on the volume and filer ports.

**Write JWTs** make the master the issuer of write authority. The master hands a
short-lived token with each write assignment, and the volume server refuses a
write that does not carry one. An attacker who can reach the volume server but
never received a token is refused, which the suite confirms with a real
untokened write returning `401`.

## A working example

This is the shape `tests/inter-component.sh` generates and exercises. Keys are
per-deployment; nothing here is a value to copy.

```toml
# Write authority. Short expiry is the point: a captured token is useful
# briefly rather than indefinitely.
[jwt.signing]
key = "<generate a unique value, for example: openssl rand -base64 32>"
expires_after_seconds = 10

# Deliberately absent: [jwt.signing.read]
# Upstream does not support read JWTs alongside a filer, and the S3 topology
# requires one. Adding this block does not protect reads in this deployment.

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

# Every role is also a gRPC client of the others.
[grpc.client]
cert = "/etc/seaweedfs/tls/client.crt"
key = "/etc/seaweedfs/tls/client.key"
```

Supply it read-only, alongside the certificates it references:

```console
podman run -d --name seaweedfs-volume \
  --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  -v seaweedfs-config:/etc/seaweedfs:ro \
  -v seaweedfs-volume:/data \
  ghcr.io/datopsis/seaweedfs-ubi:<tag> volume -dir=/data -mserver=master:9333
```

Every role needs the same file: the master issues tokens, the volume server
validates them, and both ends of every gRPC connection need their certificate.

## Certificate lifecycle

The suite generates a throwaway CA valid for one day, because a test key that
outlives the test is a key someone will reuse. A deployment needs more:

- certificates issued by a CA the deployment already trusts, not a per-cluster
  one, unless the cluster genuinely is its own trust domain;
- a rotation procedure that does not require stopping the cluster, which this
  project has **not** yet qualified; and
- the private keys mounted read-only and never baked into an image, which the
  image contract already requires.

## Client-facing TLS on the S3 listener

Measured by `tests/s3-tls.sh` against a private CA.

Supply a certificate and key and **omit `-port.https`**:

```console
podman run -d --name seaweedfs-s3   --read-only --cap-drop=ALL --security-opt=no-new-privileges   -v seaweedfs-config:/etc/seaweedfs:ro   ghcr.io/datopsis/seaweedfs-ubi:<tag> s3 -filer=filer:8888     -config=/etc/seaweedfs/s3.json     -cert.file=/etc/seaweedfs/gateway.crt     -key.file=/etc/seaweedfs/gateway.key
```

What that configuration was confirmed to do:

- a client trusting the private CA completes the handshake and round-trips an
  authenticated object;
- **a client trusting only an unrelated CA is refused at the handshake**, which
  is the check that makes the others mean anything, since a connection that
  succeeds for a client trusting everything proves nothing about the server;
- a hostname the certificate does not cover is refused, so the certificate needs
  a matching `subjectAltName` — a common name alone is ignored by modern
  clients; and
- the same port stops answering plain HTTP. Supplying a certificate upgrades the
  listener rather than adding a second one.

### The -port.https hazard

> [!WARNING]
> Adding `-port.https` does **not** move TLS to a second port. It starts TLS
> there and **leaves the original port serving plaintext**.

Confirmed: upstream with `-cert.file`, `-key.file` and `-port.https=8334`
listens on `8333`, `8334` and `18333`, and `8333` really does serve the S3 API
in the clear. An operator reaching for `-port.https` to "enable HTTPS" would
publish both.

The image refuses that combination by default for both `s3` and `mini`. The safe
shape is the one above: certificate and key, no `-port.https`. A deliberate
dual-listener migration must set
`SEAWEEDFS_UBI_ALLOW_PLAINTEXT_BESIDE_TLS=true`; doing so accepts responsibility
for keeping the plaintext port inside the intended migration boundary.

## What is not qualified yet

Stated plainly, because this document would otherwise read as more complete than
it is.

- **Certificate rotation** without downtime.
- **mTLS failure behaviour.** The suite proves the cluster works with mTLS
  configured; it does not yet prove a client presenting no certificate, or one
  from another CA, is refused. Demonstrating that needs a gRPC client the suite
  does not have.
- **HTTPS on the master, volume, and filer listeners**, which `security.toml`
  also supports and which would change the read-path analysis above.

The first and last of those are the ones that would most change this document,
and both are owed by work package 4.

## Related documents

- [The security policy](../SECURITY.md) — the deployment-critical upstream
  behaviour this document measures.
- [Architecture](ARCHITECTURE.md) — the trust boundaries and which listener
  faces what.
- [Configuration](CONFIGURATION.md) — the guards the image applies at startup.
