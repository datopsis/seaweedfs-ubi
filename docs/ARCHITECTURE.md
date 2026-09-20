# Architecture

What is in the image, what runs when it starts, how the roles reach each other,
and where the trust boundaries fall.

For the proposed, **unqualified** multi-host topology that adds a separate
Rust Lance maintenance worker while retaining Go storage roles, see the
[SVG deployment diagram](diagrams/proposed-production-lance.svg) and its
[text description](diagrams/proposed-production-lance.md). It is not the
current production profile or release evidence.

## The image

There is no compilation stage. The upstream binary is statically linked, so the
image is a digest-pinned UBI 9 Micro plus three files.

| Path | Source | Purpose |
| --- | --- | --- |
| `/usr/local/bin/weed` | the verified bundle | every supported role |
| `/usr/local/bin/seaweedfs-entrypoint` | this repository | role dispatch and startup guards |
| `/etc/pki/tls/certs/ca-bundle.crt` | digest-pinned UBI Minimal | TLS trust for outbound connections |
| `/data` | created empty | the one writable path |

UBI Minimal appears in the build only as a source for the CA bundle, copied as a
file. Micro ships no trust store, and an empty one fails in a way that is tedious
to diagnose. No package manager runs in either stage, so the final image has none
and assembly stays hermetic.

### Size, measured

| Component | Size | Share |
| --- | --- | --- |
| `weed` binary | 209.8 MiB | 90.2% |
| UBI 9 Micro base | 22.6 MiB | 9.7% |
| CA bundle | 14.3 kB | — |
| entrypoint | 1.5 kB | — |
| **assembled image** | **232.5 MiB** | |

This is not a small image, and a package-manager-free Micro base does not make it
one. Everything this project adds beyond the upstream binary is about 16 kB. Any
meaningful reduction has to come from the binary.

### Why the binary is not stripped

The admitted binary carries roughly 62 MiB that a `strip` would remove: 18.4 MiB
`.strtab`, 5.4 MiB `.symtab`, and about 38 MiB of DWARF `.debug_*` sections.
Removing them would take the image from 232.5 MiB to roughly 171 MiB, a 26%
reduction. The `.gopclntab` section, 56.5 MiB on its own, is required by the Go
runtime and cannot be removed at all.

It is left alone, deliberately. Stripping would mean the binary in the image is
no longer the bytes whose digest and signature were verified, and the provenance
chain would end at the moment this project modified it. A 26% size reduction does
not justify breaking the property the project exists to provide. It also keeps
stack traces symbolised, which is worth something when diagnosing a storage
system.

Worth knowing: upstream's **tarball** build passes `-s -w` and is stripped, while
the **container** build does not. So the fallback acquisition path in
[external artifact acquisition](ARTIFACT-ACQUISITION.md) would yield a smaller
binary, and a smaller image, with weaker provenance. That trade is recorded
rather than taken.

## Runtime identity

The container starts as UID `1000`, GID `0`, and never transitions. There is no
privileged phase: the entrypoint runs as the same identity the server does,
changes no ownership, and switches no user.

`/data` is owned `1000:0` with mode `0770`. Group `0` with group-write is what
lets an arbitrary assigned UID work under OpenShift's restricted SCC, where the
UID is chosen by the platform and only the group is predictable. It is not a
relaxation for the fixed identity, which owns the directory anyway.

The entrypoint `exec`s, so the server becomes PID 1 and receives signals
directly rather than through a shell that would swallow them.

## Startup

```text
container start
      │
      ▼
seaweedfs-entrypoint
      │
      ├── role in the allowlist?            no ──▶ exit 78, naming what is supported
      │
      ├── mini, and standalone enabled?     no ──▶ exit 78
      │
      ├── data directory explicit?          no ──▶ exit 78   (master, volume, mini)
      │
      ├── S3 identity source configured?    no ──▶ exit 78   (s3, mini)
      │
      ├── inject boundary defaults: Iceberg and Lance off,
      │   bucket auto-create and recursive delete off,
      │   WebDAV and Admin UI off for mini
      │
      ▼
exec weed <role> …          ← PID 1, non-root, no capabilities
```

Every guard is a startup failure rather than a warning, because each one guards a
configuration that otherwise looks healthy while being unsafe or lossy. The exact
behaviour and the limits of each are in [configuration](CONFIGURATION.md).

## Roles and listeners

Measured from running containers, not read from upstream's flag defaults.

| Role | HTTP | gRPC | State | Reaches |
| --- | --- | --- | --- | --- |
| `master` | 9333 | 19333 | `/data` | — |
| `volume` | 8080 | 18080 | `/data` | master |
| `filer` | 8888 | 18888 | `/data` or an external store | master, volume |
| `s3` | 8333 | 18333 | **none** | filer |

gRPC ports are the HTTP port plus 10000, upstream's convention when `-port.grpc`
is left at `0`.

The S3 role keeps no local state at all: everything it knows lives in the filer.
It therefore needs no volume and runs on a wholly read-only filesystem, which the
cluster fixture asserts by trying to write and expecting failure.

The standalone profile collapses all four into one process and uses different
ports for the volume server; its measured set is in
[configuration](CONFIGURATION.md#the-standalone-profile).

## Data flow

```text
S3 client
    │  authenticated S3 API, port 8333
    ▼
  s3  ──── gRPC / HTTP ────▶  filer  ────▶  master   (where are the volumes?)
                                │
                                └──────────▶  volume  (the bytes themselves)
```

An object write is assigned a volume by the master, the bytes land on a volume
server, and the filer records the path-to-object mapping. Reading reverses it.

## Trust boundaries

The boundary that matters most is the one inside the cluster, and it is the
operator's.

```text
┌─ client network ──────────────────────────────────────────┐
│  S3 clients ─── authenticated, TLS if the operator adds it │
└──────────────┬─────────────────────────────────────────────┘
               │  only this listener is designed to face clients
┌──────────────▼─── cluster network ─────────────────────────┐
│   s3 ──── filer ──── master ──── volume                    │
│                                                            │
│   Unauthenticated and unencrypted unless the operator       │
│   supplies security.toml. Anything that reaches a volume     │
│   server can read and write stored bytes directly,           │
│   bypassing S3 identities entirely.                          │
└────────────────────────────────────────────────────────────┘
```

| Boundary | Owned by | Enforced by |
| --- | --- | --- |
| S3 client to gateway | the image, partly | the fail-closed identity guard; TLS is the operator's |
| Between roles | **the operator** | `security.toml`: gRPC mTLS and volume write JWTs; network isolation is still required because direct HTTP reads remain open |
| Role to its data | the runtime | read-only root, one writable mount, non-root uid |
| Build inputs to image | the image | the admission gate and the reviewed lock |
| Network reachability | the operator | network policy; the image cannot enforce it |

The image can ship the guards, the examples, and the tests. It cannot supply
certificates, and it cannot stop a deployment from putting a volume server on an
untrusted network. That asymmetry is why
[the support contract](SUPPORT.md#ownership-boundary) splits ownership three ways
rather than two.

## What is deliberately absent

- No package manager, so nothing can be installed at runtime.
- No shell in the supported start path — the entrypoint `exec`s away.
- No default role: starting a storage component is a deliberate act, and a
  default would make one of them an accident.
- No privileged port, and no capability that would permit one.
- No Iceberg REST Catalog and no Lance Namespace listener, which upstream starts
  by default. `lakekeeper-ubi` is this organization's qualified Iceberg catalog.
- No bucket auto-creation and no recursive bucket deletion, both of which
  upstream enables by default and neither of which matches the S3 API.

## Related documents

- [Configuration](CONFIGURATION.md) — roles, variables, guards, and their limits.
- [Build variants](BUILD-VARIANTS.md) — which upstream build is admitted.
- [External artifact acquisition](ARTIFACT-ACQUISITION.md) — how the binary is
  verified before it reaches this image.
- [Hermetic build](HERMETIC-BUILD.md) — the assembly contract.
- [The support contract](SUPPORT.md) — profiles, classifications, ownership.
