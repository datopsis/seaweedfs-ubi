# Supported profiles and network exposure

The first-release use case is an S3-compatible storage backend for the Datopsis
analytical stack. The image also provides a deliberately limited standalone
profile for local development and test fixtures. These profiles use the same
image bytes but do not provide the same security or durability evidence.

## Separated-role profile

Production-oriented deployments run `master`, `volume`, `filer`, and `s3` in
four containers with distinct addresses and no shared filesystem. This remains
the required shape even when all four containers run on one host.

Only the client-facing S3 listener may cross the client-network boundary, and it
should do so with TLS and configured identities. Every other listener stays on a
cluster network that clients and tenants cannot reach.

| Role and listener | Client network | Cluster network | Reason |
| --- | --- | --- | --- |
| S3 HTTP/TLS `8333` | permitted with TLS and identities | permitted | the supported client API |
| S3 gRPC `18333` | prohibited | permitted when required | not a qualified client API |
| master HTTP/gRPC `9333`/`19333` | prohibited | required | controls topology and volume assignment |
| volume HTTP/gRPC `8080`/`18080` | prohibited | required | direct reads bypass S3 identities; writes need separate controls |
| filer HTTP/gRPC `8888`/`18888` | prohibited | required | direct reads and namespace access bypass S3 identities |
| optional metrics listeners | prohibited | operations network only | operational data is not a client API |

The Compose fixture follows this boundary: only S3 is published, and only on
loopback. A real deployment must enforce the equivalent with runtime networks,
host firewalling, or orchestrator network policy. Container `EXPOSE` metadata is
documentation, not a firewall.

## Standalone profile

`mini` is an explicitly enabled local-development and fixture profile. It runs
all components in one process and therefore cannot evidence inter-component
mTLS, JWT-protected component traffic, replication, component failure isolation,
or multi-node addressing.

Only its S3 listener should be published, and only to the local client that
needs the fixture. Its master, volume, and filer listeners still exist and still
bypass S3 identities; placing them in one process does not make them safe to
expose. A standalone result never substitutes for separated-role evidence.

## What `-whiteList` does and does not do

SeaweedFS 4.46 exposes `-whiteList` on the master and volume roles, and a shared
form on `mini`. The locked source describes it as a comma-separated list of IP
addresses with write permission; CIDR entries are also parsed.

The implementation uses the connection's socket peer address. It deliberately
does not trust `X-Forwarded-For` or similar headers. Behind a proxy or network
address translation, the address being authorized may therefore be the proxy or
translated peer rather than the original workload.

Its security limits are material:

- an empty whitelist permits every address;
- it protects only handlers that upstream explicitly wraps with the guard;
- volume `GET` and `HEAD` remain open, so it does not prevent direct object reads;
- it supplies neither peer identity nor traffic encryption;
- an allowed address grants every guarded operation reachable from that address;
- shared nodes, proxies, address reuse, and compromised workloads can collapse
  the distinction an IP list was meant to provide; and
- it does not apply the S3 identity or tenant policy to direct component access.

`-whiteList` can be defense in depth for selected writes and administrative
operations. It is not a substitute for S3 authentication, gRPC mTLS, volume
write JWTs, or—most importantly—the network boundary that keeps component
listeners away from clients.

This interpretation is tied to the locked `4.46` commit: the upstream
[`Guard` implementation](https://github.com/seaweedfs/seaweedfs/blob/d997fba1575583a89cf0cc50dc0150642286c86d/weed/security/guard.go)
defines address parsing and the empty-list behavior, while the
[`volume` HTTP dispatcher](https://github.com/seaweedfs/seaweedfs/blob/d997fba1575583a89cf0cc50dc0150642286c86d/weed/server/volume_server_handlers.go)
shows writes and deletes passing through the guard and reads bypassing it.

## Explicitly unqualified uses

The first release does not qualify the embedded Iceberg catalog, Lance,
WebDAV, FUSE mounts, broker or queue roles, public component listeners, or the
standalone profile as a production deployment. Capability present in the
upstream binary does not become supported merely because an operator can pass a
flag that enables it.
