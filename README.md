# SeaweedFS on Red Hat UBI 9

`seaweedfs-ubi` builds a security-oriented, rootless
[SeaweedFS](https://github.com/seaweedfs/seaweedfs) container: a distributed
storage system providing S3-compatible object storage, a POSIX-like file
abstraction, and a volume store designed for very large numbers of files. The
project is designed for Podman, Docker-compatible runtimes, OpenShift-style
arbitrary user IDs, and controlled networks that require inspectable security
evidence.

> [!IMPORTANT]
> The project is under initial development. No supported container image has
> been released, and no image has been built from this repository yet. Commands,
> tags, and security claims will be published only after their implementations
> are tested and the applicable work-plan gates are complete.

## Version baseline

- Repository and image: `seaweedfs-ubi`
- Planned image location: `ghcr.io/datopsis/seaweedfs-ubi`
- Initial SeaweedFS version: `4.46`
- Initial UBI major line: `9`
- Upstream license: Apache License 2.0

SeaweedFS releases are numbered in two components, such as `4.46`, and are not
semantically versioned. An increment carries no compatibility promise, and
releases arrive frequently, so this project treats every upstream increment as a
qualification event rather than a routine dependency bump.

## Why this image exists

Datopsis builds an analytical stack in which an open table format is the
authoritative record. That record has to live on object storage. This repository
supplies that layer with the same evidence standard the rest of the stack is
held to, and is intended to become the qualified S3 backend beneath
[`lakekeeper-ubi`](https://github.com/datopsis/lakekeeper-ubi), replacing the
unhardened upstream fixture that project currently uses for storage testing.

## Intended uses

The first release is being designed for:

- serving S3-compatible object storage to query engines and table formats;
- storing Apache Iceberg table data and metadata written by a separate catalog;
- operating the master, volume, and filer roles that the object path requires;
- running a single-node profile for development and small deployments, and a
  separated-role profile for real ones; and
- operating inside controlled networks with inspectable evidence.

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

SeaweedFS publishes release tarballs on GitHub with **a `.md5` sidecar per asset
and nothing else**: no SHA-256 manifest, no detached signature, and no
provenance attestation. MD5 is not collision resistant, and a sidecar published
from the same place as the artifact is not an independent check, so that file is
an upstream-published value worth recording and not an integrity control.

This project will therefore record the archive digest, the extracted binary
digest, sizes, and build identifiers in a reviewed lock under `artifacts/`, and
a reviewed change to that lock will be the point at which new bytes are
admitted. That proves every build used exactly the reviewed bytes. It does
**not** independently prove publisher identity, and it is weaker than
vendor-signed RPM provenance. Improving it — upstream attestations, a reproduced
build from source, or both — is a tracked item in the work plan.

## Project documentation

- [Work plan](docs/README.md) is the plan of record: the first-release
  boundary, the ordered work packages that must be completed, the evidence
  lifecycle, what is deferred, and the decisions that need a human. It also
  indexes every document this project owes and names the package that owes it.
- [Agent and contributor guidance](CLAUDE.md) defines repository
  implementation and security conventions.
- [Contributing](CONTRIBUTING.md) defines change, validation, pull-request, and
  commit expectations, including how to verify an asserted upstream behavior.
- [Security policy](SECURITY.md) provides private vulnerability reporting and
  records the deployment-critical upstream behavior an operator cannot skip.
- [Changelog](CHANGELOG.md) records notable completed changes.
- [Third-party notices](THIRD_PARTY_NOTICES.md) separates this project's
  license from SeaweedFS, UBI, and component terms.

Versioning and releases, external artifact acquisition, configuration, hermetic
build, architecture, deployment, storage and durability, TLS, logging, threat
model, security controls, cryptographic boundary, FIPS analysis, SCAP, support
definitions, the qualification ledger, and continuous integration will be added
as their associated implementations and evidence are developed.

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

There is no build, test, or run command yet. The current contents are the
project contract and the work plan; the first image lands in work package 3.
Until the first signed release is published, this repository should be treated
as development material rather than a supported production image.

Repository checks will be run with pinned local hooks once work package 1 lands:

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
