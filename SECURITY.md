# Security policy

## Supported versions

No supported image has been published, and no image has been built from this
repository yet. Repository revisions are available for evaluation and receive no
security-support commitment. Each future release will document its exact support
status and supersession policy; support must not be inferred from a tag, a
branch, a successful build, or a scanner result.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use the repository's
**Security** tab and select **Report a vulnerability** to submit a private
security advisory:

<https://github.com/datopsis/seaweedfs-ubi/security/advisories/new>

Include the affected image tag and digest when available, architecture, runtime
and host versions, the SeaweedFS version, which roles were running, the
configuration profile, reproduction steps, and whether the issue appears to
originate in this packaging, SeaweedFS itself, or UBI. Remove S3 access keys,
JWT signing keys, private keys, filer store credentials, tokens, internal
hostnames, customer data, and other secrets before submitting.

Upstream vulnerabilities should also follow the applicable upstream process:

- SeaweedFS: <https://github.com/seaweedfs/seaweedfs/security>
- Red Hat: <https://access.redhat.com/security/team/contact>

## Handling and disclosure

Maintainers will acknowledge a private report when practical, validate its
scope, coordinate with upstream suppliers when appropriate, and agree on a
disclosure plan before publishing details. No response or remediation SLA is
promised until the first supported release defines one.

## Known deployment-critical behavior

These are properties of upstream SeaweedFS that operators must handle. They are
documented here because a deployment that ignores them is insecure even when the
image itself is current. They were read from the upstream `4.46` source and are
re-verified at every version bump.

- **The S3 gateway is unauthenticated by default.** With no configuration file
  and no identities, upstream treats every request as an allow-all anonymous
  caller. A configuration file that loads zero identities denies every request
  instead — so an empty secret mount fails closed, while a *missing* one fails
  open. This image is designed to refuse to start the S3 role with no identity
  source, controlled by `SEAWEEDFS_UBI_REQUIRE_S3_AUTH`. That guard proves an
  identity source is configured; it does not judge whether a key is strong,
  unique, or secret.
- **Durable state defaults to the temporary directory.** The master metadata
  directory and the volume data directory both default to the process temporary
  directory, which on this image is a `tmpfs`. A forgotten flag produces a
  cluster that reports healthy and loses its topology or its data on restart.
  This image is designed to refuse that configuration, controlled by
  `SEAWEEDFS_UBI_REQUIRE_EXPLICIT_DATA_DIR`.
- **Nothing between the components is authenticated or encrypted by default.**
  gRPC mTLS between the master, volume, filer, and S3 roles, volume read and
  write JWTs, and HTTPS on the master, volume, and filer listeners are all
  configured through a `security.toml` that does not exist unless an operator
  supplies one. Without it, any client that can reach a volume server can read
  and write it directly, bypassing the S3 identity model entirely. The
  `-whiteList` IP restriction is empty by default and is not a substitute for
  authentication.
- **`weed s3` opens more listeners than the S3 API.** In `4.46` it also starts
  an Iceberg REST Catalog on port `8181` and a Lance Namespace server on port
  `9101` unless each is explicitly disabled. This image disables both by
  default. An operator running upstream directly should know they are there.
- **Only the S3 listener is designed to face clients.** The master, volume, and
  filer listeners must not be reachable from an untrusted network.

These guards are described as designed rather than delivered until work package
3 in [the work plan](docs/README.md) lands and its tests exist.

## Scanner results require context

Red Hat can backport corrections without adopting the upstream version number a
scanner expects, so review the exact RPM build and Red Hat advisory data before
classifying a match against UBI content. Findings against the Go dependency
inventory of the `weed` binary must be reviewed against the upstream SeaweedFS
release rather than assumed exploitable in this packaging.
