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
image itself is current. They were read from the upstream `4.53` source and are
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

  These results describe the repository's write-JWT fixture. Upstream's 4.53
  scaffold still says volume read JWTs are unsupported with a filer, although
  read-signing paths exist in source. We have not qualified a read-JWT S3
  deployment. **Network isolation remains mandatory**; `-whiteList` does not
  protect volume reads. See [TLS and the boundary between the roles](docs/TLS.md).
- **Bucket safety defaults remain explicit.** Upstream 4.53 now defaults
  `allowDeleteBucketNotEmpty` to `false`, agreeing with this image's guard.
  Upstream still enables `autoCreateBucket`; this image disables it so a typo
  does not create a new bucket. Both remain explicit operator overrides.
- **`weed s3` opens more listeners than the S3 API.** In `4.53` it also starts
  an Iceberg REST Catalog on port `8181` and a Lance Namespace server on port
  `9101` unless each is explicitly disabled. This image disables both by
  default. An operator running upstream directly should know they are there.
- **Only the S3 listener is designed to face clients.** The master, volume, and
  filer listeners must not be reachable from an untrusted network.
- **Metrics are an unauthenticated operations endpoint.** They are disabled by
  default and must be enabled per role with an explicit bind address and port.
  Keep them on a protected operations network, never the client network. Server
  logs are JSON by default, but entrypoint messages remain plain text; collectors
  must accept both and logs must still be handled as sensitive operational data.
  See [logging and metrics](docs/LOGGING.md).
- **Log confidentiality still needs review.** Historical 4.46 tests observed
  access-key-ID disclosure. 4.53 masks rejected key IDs in
  `s3api/auth_credentials.go`, but environment bootstrap still logs the full ID
  and verbose config-load logs can expose it. Mounted static configuration
  avoids the environment-bootstrap path; keep verbosity low.
  The standalone lifecycle finding awaits a fresh dedicated credential-rotation
  run; restrict log access. See [logging](docs/LOGGING.md).
- **Upload admission limits can retain abandoned requests.** With either
  `-concurrentUploadLimitMB` or `-concurrentFileUploadLimit` enabled, a stalled
  volume server can cause unbounded socket/goroutine retention and memory growth
  in the S3 gateway. Both limits default to zero (off). This is the existing
  [upstream #12496](https://github.com/seaweedfs/seaweedfs/issues/12496), present
  in both 4.46 and 4.53. The code path was confirmed; it was **not reproduced
  here**. No binary patch, default change, or workaround is applied.

- **Master collection listing can deadlock.** Concurrent collection listing
  and deletion can deadlock a nested read lock and stall master assign/lookup
  calls ([upstream #12493](https://github.com/seaweedfs/seaweedfs/issues/12493)).
  The affected code is identical in 4.46 and 4.53; fix #12495 landed after
  4.53. This was confirmed in source, not reproduced here, and is not patched
  in this image. See [operator guidance](docs/CONFIGURATION.md#master-collection-listing-limitation).

The upstream `-whiteList` option does not change that boundary. In the locked
4.53 source it permits everyone when empty, applies only to selected handlers,
and does not guard volume reads. It is IP-based defense in depth, not workload
identity, encryption, or S3 authorization. The complete listener matrix and the
proxy/NAT limitations are in [`docs/USE-CASES.md`](docs/USE-CASES.md).

Every guard above is implemented and exercised: `tests/smoke.sh` asserts each
refusal and its diagnostic, `tests/cluster.sh` asserts the default per-role
listener sets from running containers, and `tests/inter-component.sh` measures
the `security.toml` boundary. Real-host and platform qualification remain future
work; container tests are not evidence for those environments.

## Scanner results require context

Red Hat can backport corrections without adopting the upstream version number a
scanner expects, so review the exact RPM build and Red Hat advisory data before
classifying a match against UBI content. Findings against the Go dependency
inventory of the `weed` binary must be reviewed against the upstream SeaweedFS
release rather than assumed exploitable in this packaging.

## Phase A native gRPC identity blocker

**SeaweedFS 4.53 does not satisfy strict target-hostname identity for gRPC.**
The pinned source uses `advancedtls.CertVerification` rather than hostname
verification in
[`loadClientTLS`](https://github.com/seaweedfs/seaweedfs/blob/4ab66fb76da83700739f5839e62fcaf15fb7d02a/weed/security/tls.go#L209-L310).
[`AuthenticateServer`](https://github.com/seaweedfs/seaweedfs/blob/4ab66fb76da83700739f5839e62fcaf15fb7d02a/weed/security/tls.go#L385-L410)
accepts any matching CN, DNS SAN or URI SAN. An allowed CN can therefore satisfy
the policy even with an incorrect DNS SAN. An allowlist is not equivalent to
verifying the dialed hostname. The
[4.53 scaffold](https://github.com/seaweedfs/seaweedfs/blob/4ab66fb76da83700739f5839e62fcaf15fb7d02a/weed/command/scaffold/security.toml#L102-L126)
also explicitly describes the missing hostname check.

`tests/tls/qualify.py` preserves exact-outcome native canaries, separate from
strict external-client certificate tests. Their expected acceptance is recorded
as **BLOCKER**, never a successful security requirement. Any changed outcome
fails the canary and requires investigation. No binary patch, relaxed identity
check, exemption, or Phase A completion claim is permitted. The complete
[profile and evidence boundary](docs/TLS-PHASE-A.md) distinguish native-client
results from direct listener tests and list remaining unverified edges.

This phase covers transport encryption and server/peer identity only. User
login and OpenID authentication belong to Phase B. HTTPS/mTLS does not make
filer/volume APIs enforce the S3 user/tenant authorization model.
