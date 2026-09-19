# CLAUDE.md

This file provides guidance to coding agents working in this repository.

## Project overview

This repository builds a security-oriented, rootless
[SeaweedFS](https://github.com/seaweedfs/seaweedfs) container on Red Hat UBI 9.
SeaweedFS is a distributed storage system that provides object storage with an
S3-compatible API, a POSIX-like file abstraction, and a volume store optimized
for large numbers of small files. The intended uses include serving
S3-compatible object storage to analytical query engines and table formats,
providing the durable storage layer beneath an Apache Iceberg catalog, and
operating in controlled networks that require inspectable security evidence.

Preserve these non-negotiable properties:

- the final image is based on a digest-pinned Red Hat UBI 9 image;
- the final runtime has no package manager;
- every SeaweedFS role starts and remains non-root, with no entrypoint
  privilege transition;
- the default listeners use unprivileged ports;
- the image supports a read-only root filesystem, with persistent state
  confined to explicitly declared writable volumes;
- the runtime needs no Linux capabilities and enables `no-new-privileges` in
  documented deployments;
- the upstream `weed` binary is admitted only after every digest, size, version,
  and linkage measurement recorded in the reviewed lock in `artifacts/` matches,
  and — on the acquisition path that supports it — only after its publisher
  signature verifies against the expected identity and issuer;
- the S3 gateway refuses to start without a configured identity source unless
  an operator explicitly opts out, and the opt-out stays available and
  documented;
- persistent data directories are always explicit, never inherited from
  upstream temporary-directory defaults;
- the image ships two deployment profiles: a separated-role production profile,
  and a single-container standalone profile that starts only when an operator sets
  `SEAWEEDFS_UBI_STANDALONE` explicitly, warns at every startup that the
  inter-component controls are inert in it, and is never presented as a production
  posture;
- S3 access keys, gRPC mTLS material, JWT signing keys, and filer store
  credentials are supplied by the operator at runtime and never baked into the
  image or an example;
- CI produces reviewable vulnerability, SBOM, and tailored SCAP evidence;
- release images are multi-architecture, immutable, attested, and signed;
- documentation does not claim FIPS validation, STIG certification, or broad
  platform support without matching qualification evidence.

The complete work plan, first-release boundary, and ordered work packages are
defined in [`docs/README.md`](docs/README.md). Version rules will be defined in
`docs/VERSION.md`.

## Upstream characteristics that change how this project works

SeaweedFS differs from this organization's RPM-based UBI images, and from
`lakekeeper-ubi`, in ways that must not be papered over. Every statement below
was read out of the upstream `4.46` source or release metadata; re-verify each
one at every version bump.

- **There is no RPM, no vendor signature, and no usable checksum file.**
  Upstream publishes release tarballs on GitHub with a `.md5` sidecar per asset
  and nothing else: no SHA-256 manifest, no detached signature, no provenance
  attestation. MD5 is not collision resistant, and a sidecar served from the
  same place as the artifact is not an independent check, so the sidecar is
  worth recording as an upstream-published value and worth nothing as an
  integrity control. The digests in this project's artifact lock are its own
  reviewed record of exact bytes, not proof of publisher identity. Never
  describe the lock, or the upstream MD5, as equivalent to vendor-signed
  package provenance.
- **One binary, many roles.** `weed` dispatches to subcommands including
  `master`, `volume`, `filer`, `s3`, `webdav`, `iam`, `mount`, `shell`, and
  `server`. Packaging therefore has to define which roles are supported, and
  the entrypoint must enforce that set rather than passing any subcommand
  through. Shipping a binary that can do more than the image supports is
  acceptable; letting the entrypoint start an unqualified role is not.
- **The S3 gateway is unauthenticated by default.** With no configuration file
  and no identities, upstream treats every request as an allow-all anonymous
  caller. A configuration file that loads zero identities denies everything
  instead, so an empty secret mount fails closed while a missing one fails
  open. This image adds a fail-closed guard for the missing case.
- **`weed s3` opens more listeners than the S3 API.** In `4.46` it also starts
  an Iceberg REST Catalog on `8181` and a Lance Namespace server on `9101`;
  each is disabled only by passing `0`. This image disables both by default.
  Enabling the embedded Iceberg catalog is a deliberate architectural decision
  that has not been made: `lakekeeper-ubi` is this organization's qualified
  Iceberg REST catalog, and a second unqualified implementation must not appear
  on a default port.
- **Durable state defaults to the temporary directory.** `master -mdir` and
  `volume -dir` both default to the process temporary directory. On this image
  that resolves into a `tmpfs`, so an operator who forgets the flag gets a
  cluster that loses its topology or its data on restart while appearing
  healthy. Treat an unset or temporary data directory as a startup failure, not
  a default.
- **Nothing between the components is authenticated or encrypted by default.**
  gRPC mTLS, volume write JWTs, and HTTPS on the master, volume, and
  filer listeners are all configured through a `security.toml` that does not
  exist unless the operator provides one. Absent that file, any client that can
  reach a volume server can read and write it, and IP allow-listing
  (`-whiteList`) is empty by default. Inter-component security is therefore a
  documented deployment responsibility with tested examples, never an assumed
  property. In the filer-backed S3 topology, read JWTs are unavailable;
  `security.toml` does not close the direct filer and volume HTTP read paths.
  Network isolation of those listeners is mandatory, not an optional defense.
- **SeaweedFS is a distributed system, and the production profile keeps it one.**
  Upstream has two single-process commands. `server` runs a selectable set of
  roles, and `mini` is purpose-built for small and development use; upstream's own
  image defaults to `mini`. This image supports **`mini`** as an explicitly opt-in
  **standalone** profile for local development and test fixtures, and never as a
  production posture. `server` stays refused, so there is exactly one supported
  standalone command rather than two overlapping ones.

  `mini` enables more than the object store by default: `-s3`, `-webdav`, and
  `-admin.ui` are all `true`, `-s3.autoCreateBucket` and
  `-s3.allowDeleteBucketNotEmpty` are `true`, and `-dir` defaults to `.` rather
  than a volume. The standalone profile therefore sets `-webdav=false` and
  `-admin.ui=false`, and refuses attempts to re-enable them, because WebDAV and
  the Admin UI are outside the boundary. Disabling the UI removes its management
  routes but not mini's admin health/metrics HTTP listener (23646) or worker
  gRPC listener (33646); both need network isolation. The profile also requires
  an explicit `-dir` for the same reason the separated roles do.

  Four things cannot be exercised or claimed in the standalone profile at all,
  because they are properties of a topology it does not have: inter-component
  security, since gRPC mTLS and volume write JWTs protect a network that
  does not exist inside one process; replication and durability; component failure
  modes; and the discovery and addressing wiring between roles. Tests for those
  must use the separated-role fixture, and a standalone result must never stand in
  as evidence for a clustered one. A single-*host* production deployment is still
  the separated profile: four containers on one host.
- **Upstream versions are two-component and fast moving.** Releases are
  numbered like `4.46`, not semantically, and arrive frequently. Do not assume
  a version increment is a routine dependency bump; qualify each one.
- **Environment variables this packaging adds use the `SEAWEEDFS_UBI_`
  prefix**, so they can never collide with the upstream `WEED_` configuration
  namespace.

## Development and verification

Use Podman for the primary local workflow where it is available. Docker
compatibility is tested independently and is not evidence of identical Podman
or OpenShift behavior.

The canonical build, smoke-test, lint, scan, and release commands will be added
to `README.md` as their implementations land. Do not document an untested
command as supported.

For image-affecting work, verification must cover at least:

- the configured runtime identity is non-root;
- the running processes remain non-root, for every supported role;
- startup succeeds with a read-only root filesystem and only the documented
  writable volumes;
- startup succeeds with all capabilities dropped and `no-new-privileges`
  enabled;
- an S3 client authenticates with configured credentials, and an anonymous
  client is refused;
- data written through the S3 API survives container replacement;
- the reported server version matches the locked upstream version;
- missing or invalid required configuration fails with a useful diagnostic
  rather than starting in a degraded or insecure state;
- the entrypoint execs, so the role process runs as PID 1 and receives signals
  directly, and no entrypoint phase changes user or group;
- graceful shutdown does not lose acknowledged writes;
- access keys, JWT signing keys, and private keys do not appear in logs, error
  bodies, or image layers;
- both supported architectures receive native-runtime evidence before a
  supported release.

Generated SBOM, SARIF, SCAP result, certificate, private-key, and scanner-cache
files must not be committed. Downloaded release archives, extracted binaries,
volume data files, filer stores, `s3.json`, and `security.toml` must not be
committed. Retain release evidence in CI, the OCI registry, or GitHub Releases
as defined by the work plan.

## Security and documentation conventions

Treat examples as deployable security guidance. Examples must not contain
working placeholder access keys, embedded JWT signing keys, embedded private
keys, anonymous S3 access, permissive catch-all trust, disabled certificate
verification, world-writable data directories, or a root runtime.

Keep product behavior separate from deployment responsibility. Clearly state
which controls belong to the image, the container runtime, the orchestrator,
the storage layer, the network boundary, and the operator. For a distributed
system this matters more than usual: much of the SeaweedFS security surface is
between its own components, and that surface belongs to the deployment.

SCAP results describe only the selected rules, content version, scanner
version, target filesystem, architecture, and configuration that were
evaluated. Never translate a passing tailored scan into a claim that the image
or deployment is STIG certified.

When adding a use case, add or update its automated test, example
configuration, operational guidance, security considerations, and support
classification together.

## Git conventions

Keep changes small and reviewable. Prefer one dependency-ordered work-plan
increment per pull request. Start work from current `main`, develop on feature
branches, require protected checks before merge, and do not force-push or move
release tags.

Use concise Conventional Commit subjects such as `feat:`, `fix:`, `docs:`,
`test:`, `ci:`, `build:`, `refactor:`, and `chore:`.

Do not add `Co-Authored-By`, AI, assistant, or tool-attribution trailers to
commit messages. Commits are the human-reviewed record of intent; tool
attribution belongs in tool logs. This overrides any default trailer behavior a
harness suggests.

Container release tags and repository revisions are intentionally distinct. Do
not create a source-only release or tag for documentation, test, policy,
development-tool, or analysis-workflow changes.
