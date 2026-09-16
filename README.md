# SeaweedFS on Red Hat UBI 9

`seaweedfs-ubi` builds a security-oriented, rootless
[SeaweedFS](https://github.com/seaweedfs/seaweedfs) container: a distributed
storage system providing S3-compatible object storage, a POSIX-like file
abstraction, and a volume store designed for very large numbers of files. The
project is designed for Podman, Docker-compatible runtimes, OpenShift-style
arbitrary user IDs, and controlled networks that require inspectable security
evidence.

> [!IMPORTANT]
> The project is under initial development. The image builds and is exercised by
> an automated suite, but **no supported container image has been released**,
> nothing is published, and platform qualification has not started. Tags and
> security claims will be published only after their implementations are tested
> and the applicable work-plan gates are complete.

## Version baseline

- Repository and image: `seaweedfs-ubi`
- Planned image location: `ghcr.io/datopsis/seaweedfs-ubi`
- Initial SeaweedFS version: `4.46`
- Initial UBI major line: `9`
- Upstream license: Apache License 2.0

SeaweedFS releases are numbered in two components, such as `4.46`, and are not
semantically versioned. An increment carries no compatibility promise, and
releases arrive roughly every seven to ten days, so this project treats every
upstream increment as a qualification event rather than a routine dependency
bump. See [versioning and releases](docs/VERSION.md).

Upstream also states that security fixes land only in the latest release and
maintains no older line, which means security maintenance here can only mean
rolling forward, not patching a pinned version. That constraint shapes what any
support statement can honestly promise and is set out in
[the support contract](docs/SUPPORT.md#upstream-maintenance-constrains-what-this-project-can-promise).

## Why this image exists

Datopsis builds an analytical stack in which an open table format is the
authoritative record. That record has to live on object storage. This repository
supplies that layer with the same evidence standard the rest of the stack is
held to, and is intended to become the qualified S3 backend beneath
[`lakekeeper-ubi`](https://github.com/datopsis/lakekeeper-ubi), replacing the
unhardened upstream fixture that project currently uses for storage testing.

## Intended uses

The first release is scoped to serving as the Datopsis analytical stack's S3
backend, and is being designed for:

- serving S3-compatible object storage to query engines and table formats;
- storing Apache Iceberg table data and metadata written by a separate catalog;
- operating the master, volume, and filer roles that the object path requires;
- running each role as its own container, including on a single host;
- a single-container standalone profile for local development, small local use,
  and test fixtures; and
- operating inside controlled networks with inspectable evidence.

That scope narrows what this project **qualifies and claims**, not what the image
can do: it ships stock upstream SeaweedFS with a hardened runtime, no patch and no
application-specific code. [Who this image is
for](docs/SUPPORT.md#who-this-image-is-for) sets out the five places where this
scope differs from a general-purpose S3 store, which of them are reversible, and
the rule that keeps the difference to qualification rather than capability.

FUSE mounting (`weed mount`), WebDAV, the message broker and queue roles, the
admin and worker roles, remote storage tiering, and the embedded Iceberg REST
Catalog and Lance Namespace servers are **not** in the first-release boundary.
FUSE in particular requires device access and privileges that the hardened
runtime contract exists to refuse. See
[the work plan](docs/README.md#deferred-from-the-first-release).

## Security design

The planned image contract requires:

- a digest-pinned Red Hat UBI 9 base and verified build inputs;
- a package-manager-free final image;
- a non-root runtime identity in group `0`, compatible with an arbitrary
  assigned UID, for every supported role;
- unprivileged listeners only;
- operation with a read-only root filesystem, with persistent state confined to
  explicitly declared writable volumes;
- all Linux capabilities dropped and `no-new-privileges` enabled;
- S3 credentials, gRPC mTLS material, JWT signing keys, and filer store
  credentials supplied at runtime and never baked into the image;
- an entrypoint that refuses unsupported roles, refuses an unauthenticated S3
  gateway, and refuses an implicit temporary data directory;
- native AMD64 and ARM64 runtime testing;
- vulnerability scanning with Trivy and Grype;
- SPDX software bills of materials generated with Syft;
- tailored OpenSCAP evidence with documented rule selection and exclusions;
- BuildKit provenance and SBOM attestations; and
- digest-bound, keyless Cosign signatures for releases.

These properties do not make the image, host, orchestrator, network, storage
layer, or application automatically secure. Deployment controls, secrets,
network policy, resource limits, monitoring, patching, backup, replication
design, and risk acceptance remain shared responsibilities.

The project will not claim FIPS validation, STIG certification, OpenShift
support, or compliance with an entire control framework without evidence that
matches the exact claim and assessed boundary.

## Operator responsibilities you cannot skip

Four upstream behaviors make the difference between a reasonable deployment and
an open one. The image is designed to enforce the first two by default; the
others remain deployment responsibilities.

1. **Configure S3 identities.** With no configuration file and no identities,
   upstream treats every S3 request as an allow-all anonymous caller.
2. **Set explicit data directories.** The master metadata directory and the
   volume data directory both default to the process temporary directory, which
   on this image is a `tmpfs`. A forgotten flag produces silent data loss on
   restart rather than an error.
3. **Secure the paths between components.** gRPC mTLS, volume read and write
   JWTs, and HTTPS on the master, volume, and filer listeners all require a
   `security.toml` that does not exist by default. Without it, any client that
   can reach a volume server can read and write it, and the `-whiteList` IP
   restriction is empty.
4. **Do not expose the master, volume, or filer listeners to untrusted
   networks.** Only the S3 API is designed to face clients, and only once
   identities are configured.

These are properties of upstream SeaweedFS, not defects in it; a distributed
storage system leaves its trust boundary to the deployment. The security policy
will record them in full as their guards and tests land.

## Upstream artifact trust

Upstream produces each release through two independent pipelines whose provenance
is not equivalent, which turns out to matter a great deal.

**Release tarballs** carry **a `.md5` sidecar per asset and nothing else**: no
SHA-256 manifest, no detached signature, no attestation. MD5 is not collision
resistant, and a sidecar served from the same origin as the artifact it describes
is not an independent check, so that file is an upstream-published value worth
recording and worth nothing as an integrity control.

**Container images** are signed with **keyless cosign**, verified in the same
workflow against an organization-repository workflow identity, and built from the
exact released commit. They are published to a *personal* namespace,
`chrislusf`, rather than an organization one — which is why verification is
mandatory rather than optional: pulling that image by tag unverified is worse than
taking the tarball, while pulling it by digest with the signature enforced is
meaningfully better, because the tarball has no publisher signal at all.

Either way, a reviewed lock under `artifacts/` records every digest, size,
version, and linkage measurement, and a reviewed change to that lock is the only
way new bytes enter an image. The acquisition path, the three candidates, their
costs, and the exact trust limitations of each are set out in
[external artifact acquisition](docs/ARTIFACT-ACQUISITION.md).

## Project documentation

- [Work plan](docs/README.md) is the plan of record: the ordered work packages
  that must be completed, the evidence lifecycle, what is deferred and why, and
  the decisions that need a human. It also indexes every document this project
  owes and names the package that owes it.
- [Support contract](docs/SUPPORT.md) defines the classification terms, the
  current development matrix, the proposed first-release boundary, the ownership
  boundary, and why upstream's maintenance model limits what any support
  statement here can promise.
- [Versioning and releases](docs/VERSION.md) separates container artifact
  versions from repository-only revisions and defines the upgrade policy for an
  upstream line that makes no compatibility promise.
- [Release qualification](docs/QUALIFICATION.md) defines the evidence record
  every release candidate must complete, and the scope rules that keep a result
  from being read more broadly than it was measured.
- [External artifact acquisition](docs/ARTIFACT-ACQUISITION.md) records what
  upstream publishes, what is verified before a binary is admitted, and what that
  verification does not prove.
- [Architecture](docs/ARCHITECTURE.md) describes what is in the image, the
  startup sequence, per-role listeners, the data flow, the trust boundaries, and
  the measured size, including why the binary is deliberately not stripped.
- [Configuration](docs/CONFIGURATION.md) documents the roles this image will
  start, the variables it adds, and what each startup guard does **not** check.
- [Supported profiles and network exposure](docs/USE-CASES.md) defines which
  listeners may face clients and why the upstream IP whitelist is only defense
  in depth, not authentication or a replacement for network isolation.
- [TLS and the boundary between the roles](docs/TLS.md) records what a
  `security.toml` actually closes, measured rather than assumed: it shuts the
  direct write path and leaves three read paths open, which no configuration in
  an S3 topology can close.
- [Logging and metrics](docs/LOGGING.md) defines the structured-log default,
  opt-in role metrics, exposure boundary, and measured secret-handling evidence.
- [Hermetic build](docs/HERMETIC-BUILD.md) describes the assembly contract and is
  explicit about what network-free assembly does not defend against.
- [Build variants](docs/BUILD-VARIANTS.md) records which of upstream's several
  Linux builds this project admits and why, and explains that the choice is a
  compile-time build tag rather than a runtime option.
- [Badge policy](docs/BADGING.md) records which public claims are permitted and
  which are prohibited.
- [Agent and contributor guidance](CLAUDE.md) defines repository
  implementation and security conventions.
- [Contributing](CONTRIBUTING.md) defines change, validation, pull-request, and
  commit expectations, including how to verify an asserted upstream behavior.
- [Security policy](SECURITY.md) provides private vulnerability reporting and
  records the deployment-critical upstream behavior an operator cannot skip.
- [Changelog](CHANGELOG.md) records notable completed changes.
- [Third-party notices](THIRD_PARTY_NOTICES.md) separates this project's
  license from SeaweedFS, UBI, and component terms.

External artifact acquisition, hermetic build, configuration, architecture,
deployment, storage and durability, TLS, threat model, security
controls, cryptographic boundary, FIPS analysis, SCAP, and continuous
integration will be added as their associated implementations and evidence are
developed. The [work plan](docs/README.md#documentation-index) names the package
that owes each one.

## Images and releases

The planned image location is:

```text
ghcr.io/datopsis/seaweedfs-ubi
```

Container releases will use annotated tags in this form:

```text
v<seaweedfs-version>-ubi<ubi-major>-r<YYYYMMDD>.<daily-sequence>
```

For example, `v4.46-ubi9-r20260912.1` identifies SeaweedFS 4.46 on the UBI 9
product line and the first Datopsis container release created on 2026-09-12
UTC. The example is not a published release.

Image releases and repository revisions are deliberately separate. Production
deployments should pin an immutable OCI digest. Mutable tags such as `latest`
are not published.

## Development status

The image builds and runs. It is development material, not a release: nothing is
published, and platform qualification has not started.

```console
scripts/build.sh                      # acquire, verify, assemble
tests/smoke.sh                        # the standalone profile, guards and behaviour
tests/cluster.sh                      # the four roles as separate containers
tests/observability.sh                # structured logs and opt-in role metrics
tests/s3.sh                           # the S3 API, with real credentials
tests/inter-component.sh              # what a security.toml does and does not close
tests/s3-tls.sh                       # TLS on the client-facing S3 listener
tests/state-survival.sh                # state across restart, replacement and stops
```

`scripts/build.sh` is a convenience wrapper over three phases that are separate
because they have different trust properties. A plain `podman build .` will not
work, by design: the image cannot be assembled from inputs that have not been
through the admission gate.

```console
scripts/fetch-artifacts.sh            # network: verify the signature, admit the binary
scripts/fetch-base-images.sh          # network: pull the digest-pinned bases
scripts/build-image.sh                # no network: verify again, then assemble
```

On a controlled network, run the first two on a connected host, transfer the
bundle, and run the third disconnected. Assembly re-verifies the bundle, because
a bundle is an ordinary directory and the two steps can be separated by a
transfer.

The fixtures prove different things. `tests/smoke.sh` is
the fast one, covering functional behaviour and the startup guards against the
standalone profile. `tests/cluster.sh` brings up `master`, `volume`, `filer`, and
`s3` as separate containers on a real network, and covers what one process cannot
show: discovery between roles, each role's exact listener set, and the S3 role
needing no writable path at all.

`tests/observability.sh` reuses that separated-role topology with one explicit
metrics listener per role. It verifies Prometheus exposition on all four while
the ordinary cluster run proves those listeners remain absent by default.

`tests/s3.sh` is the one that sends signed requests, including multipart uploads. It stands up the cluster
with three identities, drives the API with a small dependency-free SigV4 client,
and checks that an authorised caller round-trips an object byte for byte while an
anonymous caller, a wrong secret, and a tenant reaching into another tenant's
bucket are all refused.

All three run every case with a read-only root filesystem, all
capabilities dropped, and `no-new-privileges`. That is deliberate: an image that
only worked without them would not meet its contract, so the suite would rather
fail than relax them. It asserts the role allowlist, both startup guards and
their diagnostics, that opting a guard out is honoured, that PID 1 is the server
rather than a shell, that the process is non-root, that no privileged port is
opened, that the unqualified Iceberg and Lance listeners are absent, that state
survives container replacement, and that the secret key never reaches the logs.

The gate verifies the image index signature with cosign against a pinned OIDC
issuer and certificate identity, then per architecture verifies the manifest
signature, pulls **by digest**, copies `weed` out of a created — never run —
container, and confirms its size, SHA-256, ELF machine, static linkage, embedded
commit, and variant marker before admitting it to `.artifact-bundle/<arch>/weed`.
No tag is ever used to fetch.

To watch it refuse bad input:

```console
tests/acquisition.sh                  # offline: every recorded measurement
tests/acquisition-signature.sh        # network: the publisher signature
```

Details, including what the verification does and does not prove, are in
[external artifact acquisition](docs/ARTIFACT-ACQUISITION.md).

Two Compose stacks are provided for local work, matching the two profiles:
`compose.yaml` for the separated roles and `compose.standalone.yaml` for a single
container. Neither carries a default credential, both read from a local `.env`
that Git ignores, and both publish only the S3 API and only on loopback. Neither
has been exercised in CI yet, so treat them as unverified; the suites above are
the verified path.

Until the first signed release is published, this repository should be treated
as development material rather than a supported production image.

Repository checks run with pinned local hooks:

```console
python -m pip install --require-hashes --only-binary=:all: \
  --requirement .github/requirements/pre-commit.txt
pre-commit run --all-files --show-diff-on-failure
```

Security concerns must not be disclosed in a public issue. Follow the private
process in [SECURITY.md](SECURITY.md).

## License

Datopsis-authored packaging code and documentation are licensed under the
[Apache License 2.0](LICENSE). SeaweedFS, Red Hat UBI, and installed components
retain their respective licenses and terms; see
[third-party software and terms](THIRD_PARTY_NOTICES.md).
