# Security policy

## Supported versions

No supported image has been published. The image builds and is exercised by an
automated suite, but nothing is released. Repository revisions are available for evaluation and receive no
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
- **Nothing between the components is authenticated by default, and a
  `security.toml` closes only part of it.** This has now been measured rather
  than assumed. Without the file, four paths bypass the S3 gateway entirely: the
  filer discloses an object's storage location, the filer serves its content, a
  volume server serves its bytes by file id, and a volume server accepts writes.
  With gRPC mTLS and write JWTs configured, **only the write path closes**. All
  three read paths stay open.

  That is not a configuration mistake. Upstream states that read JWTs are
  unsupported alongside a filer, and the S3 API requires a filer, so in any
  topology that serves S3 the read paths cannot be closed by configuration at
  all. **Network isolation is the only control for them**: reaching a volume
  server or the filer is equivalent to reading every object stored there, with no
  tenant scoping. The `-whiteList` IP restriction is empty by default and is not
  a substitute for authentication. See [TLS and the boundary between the
  roles](docs/TLS.md).
- **`DeleteBucket` deletes a non-empty bucket's contents.** Upstream defaults
  `allowDeleteBucketNotEmpty` to `true`, so a request that the S3 API answers with
  `BucketNotEmpty` instead removes every object in the bucket. A client written
  against S3 semantics can therefore destroy data with a call it expects to fail.
  This image turns it off by default, and also turns off `autoCreateBucket`, which
  upstream enables and which turns a mistyped bucket name into a new bucket rather
  than an error. Both are restored by passing the flag explicitly.
- **`weed s3` opens more listeners than the S3 API.** In `4.46` it also starts
  an Iceberg REST Catalog on port `8181` and a Lance Namespace server on port
  `9101` unless each is explicitly disabled. This image disables both by
  default. An operator running upstream directly should know they are there.
- **Only the S3 listener is designed to face clients.** The master, volume, and
  filer listeners must not be reachable from an untrusted network.

Every guard above is implemented and exercised: `tests/smoke.sh` asserts each
refusal and its diagnostic, and `tests/cluster.sh` asserts the per-role listener
sets from running containers. What remains unqualified is the deployment side of
the third item, since tested `security.toml` examples are owed by work package 4.

## Scanner results require context

Red Hat can backport corrections without adopting the upstream version number a
scanner expects, so review the exact RPM build and Red Hat advisory data before
classifying a match against UBI content. Findings against the Go dependency
inventory of the `weed` binary must be reviewed against the upstream SeaweedFS
release rather than assumed exploitable in this packaging.
