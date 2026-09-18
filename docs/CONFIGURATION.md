# Configuration

This document covers what this packaging adds on top of upstream SeaweedFS: the
roles it will start, the variables it defines, the guards those variables
control, and — at least as important — what each guard does **not** check.

Upstream's own configuration is unchanged and is documented upstream. Role
arguments are passed through except for the startup guards below and the
defaults listed under [injected defaults](#injected-defaults).

## Roles

The entrypoint is a dispatcher. The first argument is the role, and anything the
image does not support is refused rather than started untested.

| Role | Purpose | Default listeners |
| --- | --- | --- |
| `master` | Coordination and volume assignment | 9333, gRPC 19333 |
| `volume` | Object storage | 8080, gRPC 18080 |
| `filer` | File and bucket metadata | 8888, gRPC 18888 |
| `s3` | The S3 API | 8333, gRPC 18333 |
| `mini` | Every role in one process — local development only, opt-in | see [standalone profile](#the-standalone-profile) |
| `version`, `shell` | Informational, no guards | none |

gRPC ports are the HTTP port plus 10000, which is upstream's convention when
`-port.grpc` is left at `0`.

Every other subcommand is refused, including `server`, `webdav`, `iam`, `mount`,
and the message broker. `server` is refused specifically so there is one
supported single-process command rather than two overlapping ones; `mini` is it.

Upstream `filer` can also start embedded S3, WebDAV, IAM, or SFTP services.
This image refuses enabling them with `-s3`, `-webdav`, `-iam`, or `-sftp`
(including `--` spellings and true-valued assignments). They would bypass the
separated-role boundary; embedded S3 would also bypass the `s3` role's
identity-source guard.
Explicit `=false` or `=0` assignments remain valid. Use the separately
guarded `s3` role for the S3 API. The opt-in `mini` profile is a different,
development-only boundary, not a production substitute.

A refused role exits `78` (`EX_CONFIG`) and names what is supported. The
informational roles keep working regardless, so a container that refuses to start
can still be asked what it is.

## Variables this image adds

All of them use the `SEAWEEDFS_UBI_` prefix, so they cannot collide with
upstream's `WEED_` configuration namespace.

| Variable | Default | Effect |
| --- | --- | --- |
| `SEAWEEDFS_UBI_REQUIRE_S3_AUTH` | `true` | Refuse to start the S3 API with no identity source. |
| `SEAWEEDFS_UBI_REQUIRE_EXPLICIT_DATA_DIR` | `true` | Refuse a missing or temporary data directory. |
| `SEAWEEDFS_UBI_ALLOW_PLAINTEXT_BESIDE_TLS` | `false` | Permit the S3 API to serve plaintext on its original port while TLS listens on `-port.https`. |
| `SEAWEEDFS_UBI_STANDALONE` | unset (`false`) | Permit the `mini` role. |
| `SEAWEEDFS_UBI_ENABLE_ICEBERG_CATALOG` | `false` | Allow upstream's embedded Iceberg REST Catalog listener. |
| `SEAWEEDFS_UBI_ENABLE_LANCE_NAMESPACE` | `false` | Allow upstream's Lance Namespace listener. |
| `SEAWEEDFS_UBI_LOG_FORMAT` | `json` | Select structured `json` or traditional `text` server logs. |

The control variables are strictly `true` or `false`, and the log format is
strictly `json` or `text`. **Any other value is a startup failure**, so a
misspelling cannot quietly change a control or logging profile.

## The S3 authentication guard

With no configuration file and no identities, upstream treats every S3 request as
an allow-all anonymous caller. That includes **writes and deletes**, not only
reads, which is why this is a guard rather than a documentation note.

A configuration file that loads *zero* identities denies everything instead, so
an empty secret mount already fails closed and only the missing one needs
guarding.

The guard is satisfied by any of:

- `-config=<path>` for `s3`, or `-s3.config=<path>` for `mini`, pointing at a
  file that exists;
- `-iam.config` / `-s3.iam.config`; or
- both `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` set and non-empty.

A config flag naming a file that does not exist is refused rather than ignored,
because upstream would fall back to allow-all.

### What it does not check

- **It does not judge whether a key is strong, unique, or secret.** It checks
  that an identity source is configured, nothing more.
- **It cannot see identities held in the filer.** Upstream supports storing S3
  configuration there, and the guard has no way to know. A deployment relying on
  that must set `SEAWEEDFS_UBI_REQUIRE_S3_AUTH=false` and take on the review
  itself.
- **It does not evaluate the permissions those identities carry.** An identity
  with admin rights on every bucket satisfies it.

## The S3 TLS listener guard

With a certificate and key but no `-port.https`, upstream upgrades the main S3
listener to TLS. Adding `-port.https` does something materially different: it
starts TLS on that port and leaves the original S3 port serving plaintext.

The entrypoint therefore refuses `-cert.file` together with a nonzero
`-port.https` for `s3`, and the corresponding `-s3.cert.file` and
`-s3.port.https` flags for `mini`. Omit the HTTPS-port flag to serve TLS only.

A deliberate migration may need both listeners temporarily. Set
`SEAWEEDFS_UBI_ALLOW_PLAINTEXT_BESIDE_TLS=true` to accept that exposure. The
opt-out changes only the startup guard: the operator must still ensure that the
plaintext port is not published beyond the intended migration boundary.

An explicit HTTPS port of `0` is treated as disabled and is not refused.

## The data directory guard

`master -mdir` and `volume -dir` default to the process temporary directory. On
this image that resolves into a `tmpfs`, so an operator who omits the flag gets a
component that starts, reports healthy, and silently loses its state on restart.
A failure is better than that, so this makes one.

The guard refuses when the flag is absent, and when its value is `/tmp`,
`/var/tmp`, a path beneath either, or a relative path.

### What it does not check

- **It does not verify the path is actually a persistent mount.** A directory on
  the container's writable layer, or a mount that happens to be `tmpfs` at some
  other path, passes.
- **It does not apply to the filer.** The filer's store location comes from
  `filer.toml`, not a flag, so there is nothing here to inspect. Filer durability
  is the operator's responsibility.

## Injected defaults

The entrypoint adds a small number of flags, and only when the operator has not
already set them, so an explicit choice always wins.

| Role | Injected | Why |
| --- | --- | --- |
| `s3` | `-port.iceberg=0`, `-port.lance=0` | Both listeners are on by default upstream and are outside this image's boundary. |
| `mini` | `-s3.port.iceberg=0`, `-s3.port.lance=0` | Same, under `mini`'s differently named flags. |
| `mini` | `-webdav=false`, `-admin.ui=false` | Both default to `true` in `mini` and are outside the boundary. |
| `s3`, `mini` | `-allowDeleteBucketNotEmpty=false` | Upstream defaults it to `true`, which makes `DeleteBucket` on a bucket that still holds objects delete all of them. The S3 API answers `BucketNotEmpty`. |
| `s3`, `mini` | `-autoCreateBucket=false` | Upstream defaults it to `true`, which creates a bucket on upload if it does not exist. The S3 API answers `NoSuchBucket`. |

### The two bucket defaults

These are worth reading rather than skimming, because one of them loses data.

Upstream enables `allowDeleteBucketNotEmpty` by default. A `DeleteBucket` call
against a bucket that still holds objects **deletes every object in it**. The S3
API a client is written against answers `BucketNotEmpty` and deletes nothing, so
the same call that is a safe no-op against S3 is a silent bulk deletion here.
That is not a permission a storage image should grant by default.

Upstream also enables `autoCreateBucket` by default, so a `PUT` into a bucket
that does not exist creates it, for admin identities. The S3 API answers
`NoSuchBucket`. A typo in a bucket name becomes a new bucket instead of an error.

Both are turned off, for the standalone profile as well as the S3 role. A fixture
that is more permissive than the thing it stands in for lets tests pass against
behaviour production will not have, and there is no reason for the production
role to diverge from S3 semantics either. An operator who wants upstream's
behaviour passes the flag explicitly and it is honoured.

#### One consequence worth knowing about

SeaweedFS models a bucket as a directory, so a key containing a slash creates a
directory entry that outlives the object. Delete the only object under
`prefix/`, and the bucket's listing goes empty while `prefix/` remains.

With `allowDeleteBucketNotEmpty` off, which is this image's default, the bucket
then **cannot be deleted even though a client sees nothing in it**, and the
gateway answers `409`. That is a real divergence from the S3 API, and it is a
consequence of the safer default rather than a defect.

An operator meeting it has two honest options: remove the residual directories
through the filer, or pass `-allowDeleteBucketNotEmpty=true` for that deletion
and accept that it will remove anything still present. `tests/s3.sh` asserts this
behaviour rather than avoiding it, so an upstream change to directory cleanup
shows up as a failure to review instead of going unnoticed.

The Iceberg listener is disabled for a reason beyond surface area:
[`lakekeeper-ubi`](https://github.com/datopsis/lakekeeper-ubi) is this
organization's qualified Iceberg REST catalog, and a second unqualified
implementation must not appear on a default port. Enabling it is possible and is
documented as unqualified.

## The standalone profile

`mini` runs every component in one process. It exists for local development,
small local use, and test fixtures, and it is **never a supported production
posture**. It starts only when `SEAWEEDFS_UBI_STANDALONE=true`, and prints a
notice at every startup naming what it cannot provide, so the limitation appears
in the logs of whatever runs it rather than only here.

Its measured listener set, taken from a running container rather than read from
upstream's flags:

| Port | Service |
| --- | --- |
| 8333 / 18333 | S3 API and its gRPC companion |
| 8888 / 18888 | filer and its gRPC companion |
| 9333 / 19333 | master and its gRPC companion |
| 9340 / 19340 | volume and its gRPC companion — note `mini` uses 9340, not the volume role's 8080 |

Ports 8181 and 9101 are **absent**, which the smoke suite asserts. They were
present once: the entrypoint disabled them for the `s3` role and missed `mini`'s
differently named flags, and only reading the open ports out of a running
container caught it.

What the profile cannot provide, and why, is in
[the support contract](SUPPORT.md#deployment-profiles).

## Storage and the read-only root filesystem

The image runs with a read-only root filesystem. Exactly one path needs to be
writable, `/data`, and it is created owned by UID `1000`, group `0`, mode `0770`.

Group `0` with group-write is what makes an arbitrary assigned UID work under
OpenShift's restricted SCC. It is not a relaxation for the fixed identity, which
owns the directory anyway.

```console
podman run -d --name seaweedfs-master \
  --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  -v seaweedfs-master:/data \
  ghcr.io/datopsis/seaweedfs-ubi:<tag> master -mdir=/data
```

No image has been published yet, so that reference is illustrative.

The S3 role is the exception: it keeps no local state, so it needs no volume and
runs on a wholly read-only filesystem. The cluster fixture asserts that by
attempting a write and expecting it to fail.

## Development stacks

Two Compose files, matching the two profiles. Neither carries a default
credential; both read from a local `.env` that Git ignores.

```console
printf 'AWS_ACCESS_KEY_ID=%s\nAWS_SECRET_ACCESS_KEY=%s\n' \
  "$(openssl rand -hex 16)" "$(openssl rand -base64 32)" > .env

podman compose up -d                                  # separated roles
podman compose -f compose.standalone.yaml up -d       # one container
```

In both, only the S3 API is published, and only on the loopback address. The
master, volume, and filer listeners stay on the internal network, because without
a `security.toml` they are unauthenticated.

## Runtime identity and signals

The container starts as UID `1000`, GID `0`, and never transitions. There is no
privileged phase: the entrypoint runs as the same identity the server does,
changes no ownership, and switches no user.

The entrypoint `exec`s, so the server becomes PID 1 and receives signals
directly rather than through a shell that would swallow them.

## Logging

Server logs use upstream's JSON format by default. Set
`SEAWEEDFS_UBI_LOG_FORMAT=text` for the traditional format. Both go to the
container's streams with `-logtostderr=true`, so no writable log path is
required and no log rotation is the image's problem. Entrypoint messages emitted
before the server starts remain plain text.

Metrics are opt-in through upstream's `-metricsIp` and `-metricsPort`; nothing is
exposed by default. Give each role a distinct unprivileged port and expose it
only on a protected operations network because the endpoint is unauthenticated.
The measured profiles and evidence boundaries are in [logging and
metrics](LOGGING.md).

## Health and readiness

One image starts five materially different profiles, so it does not declare one
Dockerfile `HEALTHCHECK`. A single command would either probe the wrong role or
collapse liveness and readiness into the same weak signal. The runtime or
orchestrator must configure the role-specific probes below.

| Role | Liveness | Qualified readiness | Important limit |
| --- | --- | --- | --- |
| `master` | `GET /healthz` on `9333` | `GET /readyz` on `9333` | readiness requires a known leader and refuses a locked leader |
| `volume` | `GET /healthz` on `8080` | local `/readyz` **and** the volume present in the master's `/dir/status` topology | `/healthz` and `/readyz` share one handler; native `/readyz` remained `200` after the master stopped |
| `filer` | `GET /healthz` on `8888` | `GET /readyz` on `8888` | both routes use the same metadata-store query; neither proves master or volume reachability |
| `s3` | `GET /healthz` on `8333` | authenticated, signed `ListBuckets` (`GET /`) | native `/status`, `/healthz`, and `/readyz` are static `200` responses and stayed green with the filer down |
| `mini` | local-only use: `GET /healthz` on its S3 listener | an authenticated S3 operation appropriate to the fixture | one process cannot report component isolation or clustered readiness |

`tests/cluster.sh` measures both false-positive cases rather than inferring them
from route names. It stops the filer and proves S3's native `/readyz` stays green
while an authenticated operation fails. It separately stops the master and
proves the volume's native `/readyz` stays green while the composite registration
check fails. Both composites are then shown recovering when the dependency
returns.

The master, volume, and filer probe endpoints remain cluster-network surfaces;
they must not be published to a client network merely so an external monitor can
reach them. Run probes from the orchestrator or an operations network with the
same boundary described in [`USE-CASES.md`](USE-CASES.md).

## What is not configured here

TLS on the S3 listener, gRPC mTLS between components, volume read and write
JWTs, and the filer's metadata store are all upstream configuration, supplied by
the operator through flags, `security.toml`, and `filer.toml`. They are
deployment responsibilities, and tested examples for them are owed by work
package 4. Until those exist, treat inter-component security as unqualified here
and read
[the security policy](../SECURITY.md#known-deployment-critical-behavior).
