# Work plan and documentation index

This document is the plan of record for `seaweedfs-ubi`. It defines the
first-release boundary, the ordered work packages that must be completed to
reach it, what is deliberately excluded, and the decisions that still need a
human. It is forward looking: completed work moves to `CHANGELOG.md` and Git
history and is removed from here, except where a completed step has to stay
listed to make the ordering legible.

Nothing in this repository has been released, and no image has been built from
it yet. Treat every capability described below as planned until its package is
checked off and its evidence exists.

## Where to resume

**Next task: continue work package 4**, then implement the package 5 automation
specified below.

The hardened image, separated-role topology, authenticated S3 path, multipart
uploads, component-security measurements, client TLS, and state survival across
container lifecycle events are exercised. Package 4 still owes the table-format
path, replication and failure evidence, backup and restore, upgrade and rollback,
negative mTLS behavior, operational profiles, and the human decisions listed at
the end of this document.

Package 1 is complete. Its decisions are recorded under
[decisions taken](#decisions-taken), and the items still open are listed under
[decisions that need a human](#decisions-that-need-a-human) with the package each
one blocks. Nothing open blocks package 2.

Package 2 ranks next because package 3 cannot build an image without verified
bytes to build it from.

Its first task is the decision-shaped one: establish what upstream provenance is
actually available — whether any release asset carries a GitHub artifact
attestation, and whether a reproducible build from source is feasible — because
the answer determines whether the digest lock is the floor or the ceiling of this
project's provenance story.

Two items become due before the packages that need them:

- **Approve the first-release boundary** in
  [`docs/SUPPORT.md`](SUPPORT.md#proposed-first-release-boundary), due before
  package 3 fixes the supported role set in the entrypoint.
The single-container profile question is settled; see
[decisions taken](#decisions-taken).

## What each package involves

The detailed checklists later in this document are the authority on scope. This
section exists so that the shape and size of the remaining work is legible
without reading all of them.

| # | In plain terms | What "done" looks like | Rough size | Needs from a human |
| --- | --- | --- | --- | --- |
| 1 | **Write down the contract** | The scope, support, versioning, evidence, and badge rules are recorded and do not contradict each other | Complete except two decisions | Approve the boundary; decide the update cadence |
| 2 | **Get the binary in safely** | Scripts that fetch `weed`, verify it against a reviewed digest lock, refuse tampered or wrong-version input, and assemble the image with the network off | ~2–3 increments | Nothing; the variant decision is made |
| 3 | **Build the actual image** | A `Containerfile` and entrypoint that run each role non-root on a read-only root filesystem, refuse unsupported roles, refuse an unauthenticated S3 gateway, and refuse an implicit temporary data directory — with a smoke suite proving each refusal | ~3–4 increments | Nothing; the role set is decided |
| 4 | **Prove it works** | S3 exercised by a real client, TLS, mTLS and JWTs between components, data surviving restart and replacement, backup and restore, and the Iceberg path exercised end to end against `lakekeeper-ubi` | ~6–8 increments | Decide which filer backends and which durability claim |
| 5 | **Automate it** | CI on both architectures, SBOMs, Trivy and Grype gates, provenance, signing, and a release workflow that cannot publish without matching evidence | ~3–4 increments | Nothing |
| 6 | **The compliance package** | Threat model, OSCAL component definition, control matrix, SCAP profile, cryptographic boundary, and FIPS analysis — the artifacts a security reviewer consumes | ~4–6 increments, all writing | Two-person review of every control classification, per this project's own policy |
| 7 | **Prove it on real hosts** | Qualification on an exact RHEL 9, Podman, SELinux, and cgroup matrix, Docker compatibility, and an OpenShift restricted-SCC preview | ~3–4 increments | Real hosts; CI is not a substitute |
| 8 | **Ship it** | Inputs frozen, evidence regenerated against the candidate digest, findings dispositioned, publication rehearsed, then a signed immutable release verified from a clean environment | ~1–2 increments | Release approval; the cadence decision binds here |

Three things are worth knowing about that shape:

- **Package 3 is where this becomes useful.** At the end of it there is a working
  hardened image you can run, even though nothing is released or qualified.
- **Packages 4 and 6 are most of the remaining effort**, and they are different
  kinds of work: 4 is testing, 6 is analysis and writing. Neither can be
  shortened by doing the other.
- **Package 7 cannot be completed from CI.** It exists precisely to produce
  evidence from hosts that are not this project's build environment.

### Chosen order

Packages **2 → 3 → 4 → 5** proceed first, producing a working, tested, and
automatically built image. Packages 6, 7, and 8 are then reassessed against what
the image has become and who is asking for it. This ordering is deliberate: the
compliance package in 6 describes a boundary, and describing a boundary that is
still moving wastes the work.

## Documentation index

Only the documents that exist are linked. The rest are named so the work
packages can reference them and so a reviewer can see what is missing.

| Document | Status | Owning package |
| --- | --- | --- |
| `docs/README.md` — this work plan | Present | — |
| `CLAUDE.md` — implementation and security conventions | Present | — |
| `AGENTS.md` — agent guardrails | Present | — |
| `SECURITY.md` — private reporting and deployment-critical behavior | Present | 1, 4 |
| `THIRD_PARTY_NOTICES.md` — license and trademark boundary | Present | 1 |
| `CONTRIBUTING.md` — change, validation, and commit expectations | Present | 1 |
| `CHANGELOG.md` — notable completed changes | Present | 1 |
| `docs/VERSION.md` — container and repository versioning | Present | 1 |
| `docs/BUILD-VARIANTS.md` — which upstream build is admitted, and why | Present | 1, 2 |
| `docs/SUPPORT.md` — support classifications and lifecycle | Present | 1 |
| `docs/QUALIFICATION.md` — evidence ledger schema | Present | 1 |
| `docs/BADGING.md` — permitted public claims | Present | 1 |
| `docs/ARTIFACT-ACQUISITION.md` — lock, verification, trust limits | Present | 2 |
| `docs/HERMETIC-BUILD.md` — network-free assembly contract | Present | 2, 3 |
| `docs/CONFIGURATION.md` — variables this image adds and its guards | Present | 3 |
| `docs/ARCHITECTURE.md` — roles, listeners, data flow, trust boundaries | Present | 3 |
| `docs/USE-CASES.md` — supported profiles and listener exposure | Present | 4 |
| `docs/STORAGE.md` — measured state survival and durability boundary | Present | 4 |
| `docs/TLS.md` — client TLS and the inter-component boundary, both measured | Present | 4 |
| `docs/LOGGING.md` — log and metrics profiles | Planned | 4 |
| `docs/CI.md` — automation and local checks | Planned | 5 |
| `docs/THREAT-MODEL.md` — trust boundaries and risks | Planned | 6 |
| `docs/SECURITY-CONTROLS.md` — requirement sources and mapping | Planned | 6 |
| `docs/CONTROL-IMPLEMENTATION.md` — per-control justification | Planned | 6 |
| `docs/CRYPTOGRAPHIC-BOUNDARY.md` — where cryptography lives | Planned | 6 |
| `docs/FIPS.md` — why a FIPS claim is or is not possible | Planned | 6 |
| `docs/SCAP.md` — tailored profile, selections, exclusions | Planned | 6 |
| `docs/DEPLOYMENT.md` — qualified deployment procedures | Planned | 7 |
| `docs/PRODUCTION.md` — go-live evidence and operations | Planned | 7 |
| `docs/RELEASE.md` — release rehearsal and publication | Planned | 8 |

## Evidence lifecycle

Evidence is only meaningful when it is bound to exactly what was assessed.

- Development evidence is bound to a commit and a locally built image, is
  retained for review during the change that produced it, and is never a
  release claim.
- Integration evidence is bound to a commit, an architecture, and a CI run, and
  is retained for the CI retention window.
- Release-candidate evidence is bound to an image digest, a lock digest, a
  content and scanner version, and a host platform, and is retained with the
  release for as long as the release is supported.
- A claim may cite only evidence of matching scope. A passing single-node smoke
  test is not replication evidence; a passing scan on AMD64 is not ARM64
  evidence; a tailored SCAP pass is not a certification.

## First-release boundary

The boundary itself lives in
[`docs/SUPPORT.md`](SUPPORT.md#proposed-first-release-boundary), which is its
single authority, alongside the classification terms and the current development
matrix. It is deliberately recorded in one place: a scope statement duplicated
across two documents is a scope statement that will eventually disagree with
itself.

It remains a **proposal awaiting approval**. What follows here is only what the
work plan adds to it — why each exclusion is an exclusion.

**Out of scope, and stated as such in public documentation**

- Any support, FIPS, STIG, certification, or platform claim without matching
  evidence.
- Cluster sizing, capacity planning, or performance guarantees.
- Erasure coding, tiering to remote object stores, and cross-datacenter
  replication as *supported* configurations; they may be documented as
  unqualified.

### Deferred from the first release

Each item is deferred with a reason, so that a later reviewer does not read the
omission as an oversight.

- **FUSE mounting (`weed mount`).** Requires `/dev/fuse` access and privileges
  that the hardened runtime contract exists to refuse. Supporting it would mean
  publishing a second, materially weaker runtime profile.
- **The embedded Iceberg REST Catalog** that `weed s3` starts on port `8181` by
  default. `lakekeeper-ubi` is this organization's qualified Iceberg REST
  catalog. Shipping a second unqualified implementation on a default port would
  create an unreviewed trust boundary. The image disables it.
- **The Lance Namespace server** that `weed s3` starts on port `9101` by
  default. Same reasoning, no current use case. The image disables it.
- **WebDAV, the message broker and queue roles, and the admin and worker
  roles.** No first-release use case, and each adds listeners and privileges to
  qualify.
- **The advanced IAM and STS configuration**, including credential vending.
  Static identities cover the first-release use case; a token-vending trust
  model is a wider boundary that deserves its own qualification.
- **Filer store backends beyond those the object path needs**, including the
  external database and key-value backends. Each is a distinct dependency, a
  distinct failure mode, and a distinct credential to protect.
- **Kubernetes and OpenShift as supported platforms.** Package 7 may publish a
  restricted-SCC preview; a support claim requires evidence this project does
  not have yet.

## Immediate first-release sequence

Work proceeds in this dependency order. Later packages may be prepared in
parallel where they are purely analytical, but none may be declared complete
before the packages it depends on.

1. Repository contract, scope, support boundary, and evidence ownership.
2. Upstream artifact acquisition, lock, and hermetic assembly.
3. Rootless minimal image, role contract, and entrypoint guards.
4. Supported configuration and runtime qualification.
5. CI, supply chain, and release automation.
6. Security engineering and cyber-review package.
7. Deployment and platform qualification.
8. Signed first release.

Packages 1 through 5 are committed. Packages 6, 7, and 8 are reassessed once the
image exists, for the reason given under
[chosen order](#chosen-order).

## Package 1: repository contract, scope, and evidence ownership

- [ ] Approve the proposed first-release boundary in
      [`docs/SUPPORT.md`](SUPPORT.md#proposed-first-release-boundary), including
      the exact supported role set and every deferral, and remove the proposal
      notice when approved.
- [x] Write [`docs/VERSION.md`](VERSION.md), adapting the sibling projects'
      policy to a two-component upstream version that is not semantic. Defines
      the container tag form
      `v<seaweedfs-version>-ubi<ubi-major>-r<YYYYMMDD>.<sequence>`, prohibits
      mutable convenience tags, separates container releases from
      repository-only revisions, requires the release asset variant in OCI
      metadata because the tag cannot encode it, and states the upgrade policy
      for an upstream line that makes no compatibility promise.
- [x] Write [`docs/SUPPORT.md`](SUPPORT.md) with support classifications, the
      development matrix, the proposed first-release boundary, accountable
      ownership, and the reporting route.
- [ ] **Decide the update cadence and security-response targets**, which
      `docs/SUPPORT.md` deliberately leaves undefined. Upstream releases roughly
      weekly, fixes only the latest release, and offers no maintained older line
      to pin to, so qualification depth and update latency are in direct
      tension. See the decision recorded below; `docs/SUPPORT.md` cannot define a
      support period until it is settled.
- [x] Write [`docs/QUALIFICATION.md`](QUALIFICATION.md) defining the evidence
      ledger schema, including the scope rules that stop a single-container or
      single-client result from being over-read, and the two structural residual
      risks every candidate record must restate.
- [x] Write [`docs/BADGING.md`](BADGING.md) inventorying every proposed badge by
      exact claim and backing evidence, naming the package that enables each, and
      prohibiting the four claims a reader would plausibly expect this project to
      badge and it cannot support.
- [x] Write `CONTRIBUTING.md` covering change scope, validation, pull-request
      expectations, and the commit-trailer prohibition.
- [x] Add `.github/CODEOWNERS`, a security-aware pull request template, issue
      templates routing security reports to private advisories, and a
      `CHANGELOG.md` seeded with the work completed so far.
- [x] Add pinned local `pre-commit` checks for repository hygiene, shell code,
      container build files, GitHub Actions, private keys, and attribution
      trailers, with a hash-locked Python requirements file.
- [x] Add grouped Dependabot updates for Actions, pre-commit hooks, and the
      pinned CI Python environment.
- [x] Enable branch protection on `main`, secret scanning with push protection,
      and private vulnerability reporting.
- [ ] Add the required status checks to the `main` protection ruleset once
      package 5 publishes named CI check contexts. Protection currently requires
      a pull request, blocks force-pushes and deletion, and requires review
      threads to be resolved, but cannot require checks that do not exist yet.

**Exit criteria.** A reviewer can read the repository and state exactly what the
first release will support, what it will not, who owns each obligation, and
what evidence each claim will rest on, with no contradiction between documents.

## Package 2: upstream artifact acquisition, lock, and hermetic assembly

- [ ] Record the upstream trust analysis in `docs/ARTIFACT-ACQUISITION.md`:
      release assets carry only a `.md5` sidecar, with no SHA-256 manifest, no
      detached signature, and no provenance attestation. State plainly that MD5
      is not collision resistant, that a sidecar from the same origin is not an
      independent check, and that this project's lock proves reviewed bytes
      rather than publisher identity.
- [x] Decide which release asset variant is admitted, record what each variant
      changes, and record what switching would cost. Settled in
      [build variants](BUILD-VARIANTS.md): `large_disk` is admitted, `full` is
      not, and the choice is a compile-time build tag rather than a runtime
      option.
- [ ] Qualify the variant migration path that [build
      variants](BUILD-VARIANTS.md#what-switching-would-cost) currently leaves
      open: test whether a wider-offset build can read a narrower-offset volume,
      test the reverse, test a partially migrated data directory, and publish the
      result. Until this exists, no variant change may be offered as supported.
- [x] Investigate whether upstream publishes GitHub artifact attestations or a
      reproducible build path for any release asset, and record the finding either
      way. Recorded in
      [external artifact acquisition](ARTIFACT-ACQUISITION.md): tarballs carry an
      MD5 sidecar and nothing else, while container images are signed with keyless
      cosign bound to an organization-repository workflow identity, and are built
      from the exact released commit.
- [x] **Confirm the acquisition path.** The cosign-verified image, Path B, with
      the tarball retained as a documented fallback.
- [x] Prove `cosign verify` actually succeeds against the published `large_disk`
      digest for both architectures, rather than relying on the presence of a
      signing step in an upstream workflow. Verified for the index and both
      architecture manifests, with the certificate's workflow repository, ref, and
      commit recorded, and the commit independently cross-checked against the tag.
- [x] Create a lock under `artifacts/` for both architectures recording the
      release tag and commit, the variant and its build tags, the image repository
      and index digest, the cosign issuer and identity, and per architecture the
      manifest digest and the extracted binary's digest, size, ELF machine,
      linkage, embedded commit, and version string where captured.
- [x] Add validation of the lock, enforced by a local hook and available to CI, so
      a malformed or partially edited lock fails review rather than a build.
      Implemented as an explicit checker rather than JSON Schema: the dangerous
      failure is a half-edited lock that still parses, and the cross-field
      agreement checks that catch it — a bumped tag that misses the certificate
      identity, a commit that no longer prefixes the recorded one, a static binary
      that also lists needed libraries — cannot be expressed in JSON Schema. It
      also avoids adding a dependency to a hash-locked environment.
- [x] Measure and record the runtime linkage of the shipped binary. Both
      architectures are statically linked, with no `PT_INTERP` and no `PT_DYNAMIC`
      segment and therefore no glibc version requirement, measured by ELF
      inspection rather than assumed from upstream's build flags. The gate
      re-measures on every acquisition and refuses a change.
- [ ] Capture the arm64 version string on a native runner. The offline gate
      confirms the arm64 binary embeds the release commit and the variant marker,
      but the version number is computed at runtime and only execution reveals it.
- [x] Acquire artifacts outside the container build and fail closed on a size,
      digest, ELF machine, linkage, commit, or variant mismatch, and on a missing
      verification tool. Implemented by `scripts/fetch-artifacts.sh`, which fetches
      only by digest and never resolves a tag.
- [ ] Verify the bundle again at assembly time, so a bundle altered between
      acquisition and assembly is refused. This lands with the Containerfile in
      package 3, because assembly does not exist yet.
- [x] Add negative tests proving the gate refuses bad input. `tests/acquisition.sh`
      covers a tampered binary of the correct size, a truncated download, appended
      bytes, a binary offered as the wrong architecture, an architecture absent from
      the lock, a non-ELF file, a missing file, and an unparseable lock, all offline.
      `tests/acquisition-signature.sh` covers a different workflow identity, a
      different git ref, a different OIDC issuer, and an unsigned digest.
- [x] Record in [hermetic build](HERMETIC-BUILD.md) what the network-free assembly
      property does and does not defend against, including that it does not make
      upstream trustworthy, does not detect a compromised upstream signing
      identity, does not validate the base image's contents, and is not
      reproducibility.
- [ ] Prove assembly actually succeeds with the build network disabled. This
      cannot be done until package 3 creates something to assemble, and the Docker
      path needs a different mechanism than Podman's, which the support matrix will
      have to distinguish.
- [x] Implement a reviewed lock-update path that proposes changes for review and
      never resolves a version at build time. `scripts/update-lock.py` resolves the
      tag, verifies the signature, cross-checks the certificate's commit against
      the commit the tag resolves to, extracts and measures both architectures, and
      writes a lock whose diff a human reads. Regenerating the committed 4.46 lock
      reproduces it exactly, including the Rekor log index.
- [ ] Run the lock-update path in CI on a schedule so a new upstream release
      arrives as a reviewable pull request rather than as something someone has to
      remember to check. Belongs with the rest of the automation in package 5.
- [ ] Record source availability, redistribution terms, trademark boundaries,
      and the Apache 2.0 obligations in `THIRD_PARTY_NOTICES.md`.

**Exit criteria.** Every build consumes exactly the bytes recorded in a reviewed
lock, an unreviewed byte cannot enter the image, and the residual provenance
weakness is documented rather than obscured.

## Package 3: rootless minimal image, role contract, and entrypoint guards

- [x] Add a digest-pinned, package-manager-free UBI 9 Micro image carrying only
      the verified `weed` binary, the entrypoint, and a CA bundle. There is no
      compilation stage: the upstream binary is statically linked, so assembly
      needs no toolchain. UBI Minimal appears only as a source for trust material
      copied as a file, since Micro ships no CA bundle and an empty trust store
      fails confusingly.
- [x] Define the runtime identity: UID `1000` in group `0`, with `/data` owned
      `1000:0` mode `0770` so an arbitrary assigned UID also works. Asserted by the
      smoke suite, which reads the running process's uid rather than trusting the
      `USER` instruction.
- [x] Declare exactly one writable path, `/data`, and prove the image runs with a
      read-only root filesystem. Every smoke assertion runs with `--read-only`,
      `--cap-drop=ALL` and `no-new-privileges`, so an image that needed more would
      fail the suite rather than quietly get them.
- [x] Implement the entrypoint as a role dispatcher that `exec`s the server, with
      no phase that changes user or group. The suite reads `/proc/1/cmdline` to
      confirm PID 1 is the server and not a shell.
- [x] Enforce a supported-role allowlist: `master`, `volume`, `filer`, `s3` and
      the informational `version` and `shell` paths unconditionally, `mini` only
      when `SEAWEEDFS_UBI_STANDALONE` is set, everything else refused including
      `server`, `mount` and `webdav`.
      any other subcommand is refused with a diagnostic naming the supported
      set. Informational paths must keep working so a refused container stays
      diagnosable.
- [x] Implement the fail-closed S3 authentication guard,
      `SEAWEEDFS_UBI_REQUIRE_S3_AUTH`. A config flag naming a file that does not
      exist is refused too, since upstream would fall back to allow-all. An
      unrecognised toggle value is a startup failure rather than a silent default.
      The suite asserts the refusal, the diagnostic, and that the secret never
      reaches the logs.
- [x] Implement the explicit-data-directory guard,
      `SEAWEEDFS_UBI_REQUIRE_EXPLICIT_DATA_DIR`. The suite asserts both that it
      refuses and that opting out is honoured, so it is a control rather than a
      wall.
- [x] Disable the Iceberg REST Catalog and Lance Namespace listeners by default
      for both the `s3` and `mini` roles, behind `SEAWEEDFS_UBI_` opt-ins
      documented as unqualified. They were live in the standalone profile at first,
      because `mini` names those flags differently from `s3`; the measured listener
      assertion below is what found it.
- [x] Harden the standalone profile's own defaults and decide the two bucket
      behaviours. `-webdav` and `-admin.ui` are off, an explicit data directory is
      required, and `autoCreateBucket` and `allowDeleteBucketNotEmpty` are off for
      **both** the `s3` role and `mini` — the latter matters because upstream's
      default turns a `DeleteBucket` that the S3 API refuses into a silent deletion
      of every object in the bucket.
- [x] Account for the binary's size in the image contract. Measured in
      [architecture](ARCHITECTURE.md#size-measured): 232.5 MiB assembled, of which
      the binary is 209.8 MiB and the base 22.6 MiB, so everything this project adds
      beyond upstream is about 16 kB. Stripping would save roughly 62 MiB and is
      refused, because the shipped binary would no longer be the bytes that were
      verified.
- [x] Measure the standalone profile's listener set from a running container and
      assert in the suite that the Iceberg and Lance ports are absent and that no
      privileged port is opened. Recorded in
      [configuration](CONFIGURATION.md#the-standalone-profile), including that
      `mini` puts the volume server on 9340 rather than the volume role's 8080.
- [x] Extend the measured listener inventory to the separated roles and assert the
      full expected set rather than only the ports that must be absent.
      `tests/cluster.sh` pins each role's exact ports, so an upstream release that
      opens something new fails rather than shipping.
- [ ] Fix the default listener set and document it: master `9333`, volume
      `8080`, filer `8888`, S3 `8333`, and the gRPC companion ports upstream
      derives by adding `10000` to the HTTP port. Confirm no privileged port is
      used and that the pprof debug listener stays disabled.
- [x] Ensure logs go to the container streams with `-logtostderr=true`, so no
      writable log path is required. Metrics stay opt-in through upstream's
      `-metricsPort`; nothing is exposed by default.
- [x] Write [configuration](CONFIGURATION.md) covering every `SEAWEEDFS_UBI_`
      variable, each guard's exact behaviour, and what each guard does **not**
      check: the S3 guard cannot see filer-held identities and does not judge a
      key's strength, and the data directory guard cannot tell a persistent mount
      from a writable layer.
- [x] Add hardened Compose development stacks with no default credentials and no
      anonymous access: `compose.yaml` for the separated roles and
      `compose.standalone.yaml` for local use. Both publish only the S3 API, and
      only on loopback.
- [ ] Add Quadlet units for the rootless systemd path, and exercise the Compose
      stacks in CI. Neither has been run in the reference environment yet, so both
      are unverified.
- [ ] Implement the standalone profile gate, `SEAWEEDFS_UBI_STANDALONE`, unset by
      default: `mini` is refused unless it is explicitly set. When it is set,
      print a startup notice naming what the profile cannot provide — no
      inter-component authentication, no replication, no component isolation — so
      the limitation is visible in the logs of whatever is running it and not only
      in documentation. An unrecognized value is a startup failure.
- [x] Add a restricted-runtime suite with **two** fixtures, because they prove
      different things. `tests/smoke.sh` covers functional behaviour and the guards
      against the standalone profile; `tests/cluster.sh` brings up the four roles as
      separate containers on a real network and covers discovery, per-role listener
      sets, and the S3 role needing no writable path at all.
- [x] Assert authenticated S3 access and the refusal of anonymous access against
      a real S3 client. Delivered by `tests/s3.sh`.

**Exit criteria.** A container built from this repository runs every supported
role as a non-root process on a read-only root filesystem with no capabilities,
refuses to start in the two configurations that would silently be unsafe, and
proves it in an automated suite.

## Package 4: supported configuration and runtime qualification

### Object storage path

- [x] Qualify the S3 API against a real client for bucket and object create,
      read, list, delete, and error behaviour, and record the divergences found.
      `tests/s3.sh` drives a dependency-free SigV4 client against three
      identities. One divergence is recorded and asserted: a prefix leaves a
      directory entry behind, so a bucket whose listing is empty still cannot be
      deleted.
- [x] Qualify multipart upload, which the table-format path depends on for large
      objects. Exercised with parts at the 5 MiB minimum the S3 API imposes, using
      non-uniform content so that parts reassembled out of order would be caught
      rather than hidden by a run of identical bytes. Initiate, part upload,
      complete, byte-exact reassembly, abort, and the absence of an object after an
      abort are all asserted, as is a neighbouring tenant being refused when it
      tries to add a part to an upload it does not own.
- [ ] Qualify the table-format path end to end: write and read Iceberg tables
      through `lakekeeper-ubi` against this image, replacing the unhardened
      fixture that project uses today. Pin the engine toolchain so the result is
      reproducible.
- [x] Test identity isolation: two bucket-scoped identities, proving one cannot
      read, write, or list the other's bucket, alongside an anonymous caller and a
      valid key with the wrong secret being refused.
- [x] Qualify S3 listener TLS against a private CA chain and prove verification
      is not silently disabled: a client trusting only an unrelated CA is refused
      at the handshake, and a hostname the certificate does not cover is refused.
      Supplying a certificate without `-port.https` upgrades the listener and
      stops serving plaintext on it.
- [x] Refuse `-cert.file` together with a nonzero `-port.https` by default for
      both supported profiles. That combination starts TLS on the new port and
      leaves the original one serving plaintext. A deliberate migration can set
      `SEAWEEDFS_UBI_ALLOW_PLAINTEXT_BESIDE_TLS=true` to accept both listeners.
- [ ] Decide and document the supported position on anonymous read access.

### Cluster, durability, and state

- [x] Qualify the separated-role profile: `tests/cluster.sh` runs master,
      volume, filer, and S3 in distinct containers with explicit addresses and
      separate volumes, asserts discovery and listener sets, and proves the S3
      role needs no writable filesystem.
- [ ] Decide and document the supported filer metadata store backends, with the
      credential handling and failure behavior of each.
- [x] Prove data written through the S3 API survives container replacement,
      restart, and an unclean stop, and that acknowledged writes are not lost on
      graceful shutdown. `tests/state-survival.sh` exercises all four roles as
      separate containers, reuses only their declared named volumes, and keeps
      the result explicitly separate from replication or node-loss evidence.
- [ ] Qualify a replicated volume topology sufficient to make a durability
      statement, and state plainly which durability properties the first release
      does **not** claim.
- [ ] Test resource-exhaustion behavior: full disk, exhausted inodes, a bounded
      `tmpfs`, and the volume count limit, confirming each fails visibly.
- [ ] Define and test backup and restore procedures for master metadata, filer
      metadata, and volume data, including a restore into a replacement
      deployment.
- [ ] Define and test the upgrade and rollback procedure across an upstream
      version increment, including whether on-disk formats or the filer schema
      changed.

### Inter-component security

- [x] Provide a tested `security.toml` example enabling gRPC mTLS between master,
      volume, filer, and S3, and prove the cluster serves S3 with it in effect.
      `tests/inter-component.sh` generates a throwaway CA and per-role
      certificates and runs the cluster with them.
- [x] Prove a client connecting to a gRPC listener without a certificate, or
      with one from another CA, is refused. `tests/lib/mtlschecks.py` speaks the
      HTTP/2 connection preface used by gRPC: a client certificate from the
      configured CA receives a protocol frame, while both invalid cases are
      rejected before application traffic is accepted.
- [x] Provide a tested example enabling volume write JWTs, and prove a direct
      volume write without a token is refused: measured, HTTP 401.
- [x] Establish what the mitigation does **not** cover, which turned out to
      matter more. Read JWTs are unsupported alongside a filer and the S3 topology
      requires one, so three read paths stay open with `security.toml` in place:
      the filer discloses object locations, the filer serves object content, and
      volume servers serve bytes by file id. All three are asserted, and network
      isolation is documented as the only available control.
- [x] Document the `-whiteList` IP restriction, its limits, and why it is not a
      substitute for authentication. `docs/USE-CASES.md` ties the guidance to
      the exact 4.46 implementation: empty means allow-all, socket peer addresses
      are used, and volume reads remain outside the guard.
- [x] State clearly, for every supported profile, which listeners may face a
      client network and which must not. The separated-role matrix permits only
      authenticated TLS S3; the standalone profile is local-only and never
      production evidence.

### Operations

- [ ] Implement and test structured logging and metrics profiles for each role,
      and qualify that credentials, tokens, and keys never appear in a log line
      or error body.
- [x] Define and test health and readiness checks per role that reflect real
      service health rather than process liveness. `tests/cluster.sh` pins two
      native false positives: S3 `/readyz` stays green without its filer, and
      volume `/readyz` stays green without its master. Qualified readiness uses
      an authenticated S3 operation and volume registration in master topology,
      respectively; the complete role matrix is in `docs/CONFIGURATION.md`.
- [ ] Write `docs/USE-CASES.md`, `docs/STORAGE.md`, `docs/TLS.md`, and
      `docs/LOGGING.md` from the qualified results, and update `SECURITY.md`
      with the deployment-critical upstream behavior each one exposes.

**Exit criteria.** Every configuration this project intends to support has a
positive test, a negative test, an example, operational guidance, and a support
classification — and every configuration it does not support is named.

## Package 5: CI, supply chain, and release automation

- [ ] Add `.github/workflows/ci.yml`, modeled on the control shape used by
      `datopsis/nginx-ubi`: pull-request, `main`, scheduled, and manual triggers;
      least-privilege permissions; per-ref concurrency cancellation; immutable
      Action SHAs; pinned runners; timeouts; and hash-locked tooling. Give every
      required matrix a stable aggregate check name for branch protection.
- [ ] In that workflow, run pre-commit and zizmor, scan repository configuration
      with Trivy, validate the artifact lock, exercise the offline negative
      acquisition tests, and prove assembly re-verifies its bundle with the
      build network disabled.
- [ ] Build and execute natively on AMD64 and ARM64 rather than using emulation
      as runtime evidence. Run the restricted smoke suite on both; run the
      separated-role, authenticated S3, multipart, inter-component-security,
      client-TLS, and state-survival suites wherever their architecture and
      runtime prerequisites are met, without treating a skipped architecture as
      evidence for it.
- [ ] Add `.github/workflows/codeql.yml` for both GitHub Actions and the
      security-relevant Python acquisition, lock, and test tooling, using
      `security-extended`, read-only defaults, and only the `security-events`
      permission needed to publish results.
- [ ] Add `.github/workflows/scorecard.yml`, following the pinned OpenSSF
      Scorecard pattern in `datopsis/nginx-ubi`: `read-all` by default, narrowly
      scoped SARIF and OIDC permissions, scheduled and branch-protection
      triggers, retained SARIF, and code-scanning publication.
- [ ] Add dependency-review coverage for pull requests and keep workflow
      auditing, configuration scanning, and Scorecard findings separate from
      image vulnerability results so each required check has one meaning.
- [ ] Generate SPDX SBOMs with Syft for CI and release images, recording the
      `weed` binary and its resolvable Go dependency inventory as components.
- [ ] Add Trivy and Grype vulnerability gates that block fixed High and Critical
      findings, and retain the complete inventory including unfixed findings.
- [ ] Define the triage policy for findings against the Go dependency
      inventory, which are reported against upstream SeaweedFS rather than
      proven exploitable in this packaging.
- [ ] Produce BuildKit provenance and SBOM attestations, and digest-bound
      keyless Cosign signatures.
- [ ] Add a release workflow with strict tag validation that refuses to publish
      without matching candidate evidence.
- [ ] Prove release assembly cannot pull an image, reach a package network, or
      resolve a version at build time.
- [ ] Add monitored update proposals for the SeaweedFS release and the UBI base
      digests, landing as reviewable pull requests. Keep this scheduled update
      proposal separate from the release workflow: detecting a release must
      never publish or silently change the reviewed lock.
- [ ] Write `docs/CI.md` covering local checks, CI automation, where each piece
      of evidence lands, and how long it is kept.

**Exit criteria.** Every image this project publishes is built, tested,
inventoried, scanned, attested, and signed by automation that a reviewer can
read, with evidence retained to the lifecycle above.

## Package 6: security engineering and cyber-review package

- [ ] Establish the authoritative requirement-source register with publisher,
      title, version, release date, URL, retrieval date, and digest for each
      source.
- [ ] Compare applicable NIST SP 800-53 Rev. 5 controls and the applicable DISA
      Container Platform, Application Server, and general-purpose operating
      system requirements against this image's behavior. Record the storage and
      object-store specific requirements that no existing STIG covers directly.
- [ ] Classify each requirement as image-owned, deployment-supported,
      inherited, or not applicable, with a justification and a two-person review
      for every adoption and exclusion.
- [ ] Publish a schema-validated NIST OSCAL component definition and
      deterministically generate the control matrix views a cyber team imports.
- [ ] Give every supported control an examine, test, or interview assessment
      method, and link it to the automated test or evidence artifact that
      satisfies it.
- [ ] Publish `docs/THREAT-MODEL.md` covering build inputs, CI, the registry,
      image contents, the runtime identity, every inter-component path, the S3
      client boundary, durable state, and the operator.
- [ ] Publish `docs/CRYPTOGRAPHIC-BOUNDARY.md` identifying every place this
      image performs cryptography — S3 listener TLS, gRPC mTLS, JWT signing,
      and any at-rest feature — the implementation behind each, and who owns it.
- [ ] Publish `docs/FIPS.md` recording whether a FIPS claim is possible for a
      Go binary compiled upstream, and why running on a FIPS-enabled host does
      not by itself confer one.
- [ ] Perform SCAP discovery with pinned OpenSCAP and content versions on both
      architectures, select only image-owned rules, document every inclusion and
      exclusion, and keep results report-only until the tailored profile is
      reviewed.
- [ ] Publish architecture, assurance-pipeline, data-flow, and trust-boundary
      diagrams as repository-native sources.
- [ ] Document vulnerability triage, exception handling with expiry, and
      incident response.

**Exit criteria.** A consuming security team can take this repository's
artifacts as a usable component definition and assessment package, and every
statement in them cites evidence of matching scope.

## Package 7: deployment and platform qualification

- [ ] Publish supported, compatible, preview, and unsupported platform
      classifications, with the exact qualification matrix: RHEL version,
      kernel, Podman and OCI runtime versions, SELinux mode, cgroup version,
      storage driver, and architecture.
- [ ] Qualify the rootless single-node profile on an exact supported host, with
      systemd integration, restart behavior, and log persistence.
- [ ] Qualify the separated-role deployment across hosts, including the network
      policy each listener requires.
- [ ] Qualify Docker compatibility independently, and record every behavioral
      difference from Podman rather than assuming equivalence.
- [ ] Produce an OpenShift restricted-SCC preview with arbitrary-UID evidence,
      and decide the first-release support boundary from the actual result.
- [ ] Qualify the controlled-network path: acquisition on a connected host,
      assembly and deployment on a disconnected one.
- [ ] Test every supported configuration with positive, negative, restricted,
      and failure cases on a real host rather than only in CI.
- [ ] Define go-live evidence tied to an exact image digest, lock digest, and
      configuration, and complete `docs/DEPLOYMENT.md` and
      `docs/PRODUCTION.md`.

**Exit criteria.** Every platform this project names is either qualified with
host evidence or explicitly classified as unqualified, with nothing in between.

## Package 8: signed first release

- [ ] Freeze and review the current SeaweedFS release and UBI base digests
      against the newest available inputs, and record why the chosen versions
      are chosen.
- [ ] Regenerate all candidate-bound evidence against the exact release
      candidate digest.
- [ ] Disposition every outstanding vulnerability and licensing finding, with an
      owner and an expiry for each accepted one.
- [ ] Complete independent security and release review against
      `docs/QUALIFICATION.md`.
- [ ] Rehearse publication end to end without publishing, then publish the
      signed immutable GHCR digest, the annotated tag, the matching GitHub
      Release, and the retained evidence.
- [ ] Verify the published artifact from a clean environment: signature,
      attestations, digest, architectures, and a runtime smoke test against the
      published image rather than a local build.
- [ ] Update `README.md`, `docs/SUPPORT.md`, and `CHANGELOG.md` to describe a
      released and supported image, and only then publish the claims that
      release earns.

**Exit criteria.** A consumer can pin a digest, verify its signature and
provenance independently, read exactly what is supported, and find the evidence
behind every claim.

## Decisions taken

Recorded so that a later reviewer does not have to reconstruct them, and so that
reopening one is a deliberate act rather than a drift.

| Date | Decision | Reasoning |
| --- | --- | --- |
| 2026-09-12 | **Order: packages 2 → 3 → 4 → 5 first**, then reassess 6, 7, and 8 | A working, tested image is worth more now than a compliance package describing a boundary that is still moving. See [chosen order](#chosen-order). |
| 2026-09-12 | **Admit the `large_disk` build variant** | The workload is large Iceberg objects, the default 32 GB volume ceiling is low enough to hit accidentally, and this is the harder direction to reverse. Full reasoning and the switching cost are in [build variants](BUILD-VARIANTS.md). |
| 2026-09-12 | **Do not admit the `full` variant** | It adds five unqualified filer backends and two tiering integrations purely for capability outside the boundary. PostgreSQL, the backend this organization would actually use, is already in the plain build. |
| 2026-09-12 | **Ship two deployment profiles from one image**: a separated-role production profile, and a single-container standalone profile gated behind an explicit `SEAWEEDFS_UBI_STANDALONE` opt-in. **Supersedes** an earlier decision the same day to refuse the `server` subcommand outright. | Refusing it outright protected a security claim by pushing multi-container cost into every fixture, including ones needing only functional coverage, and denied a real local-development use case that MinIO serves with one container. One image rather than two is correct because the bytes are identical: separate images would mean two SBOMs, scan runs, signature sets, and ledger entries for a difference that is a command-line argument. What the standalone profile can never evidence is enumerated in [deployment profiles](SUPPORT.md#deployment-profiles). |
| 2026-09-12 | **Acquire the binary from the cosign-verified official container image** (Path B), pinned by digest, with the tarball retained as a documented fallback and a source build left open | The tarball has no publisher signal at all, while the image is signed with keyless cosign bound to an organization-repository workflow identity and built from the exact released commit. Because the images live in a personal namespace, verification is the reason to take that path rather than an enhancement to it. Building from source would be stronger still, but it turns this project from a packager of upstream releases into a builder of them. Recorded in [external artifact acquisition](ARTIFACT-ACQUISITION.md). |
| 2026-09-12 | **First-release consumer: the Datopsis analytical stack's S3 backend**, built so nothing precludes general use | The difference between the two is what gets *qualified*, not what the image can *do*; see [the support contract](SUPPORT.md#who-this-image-is-for). |
| 2026-09-15 | **Refuse a plaintext S3 listener beside TLS by default, with an explicit migration opt-out** | Upstream's `-port.https` adds TLS without removing plaintext from the original port. Failing closed matches the authentication and data-directory guards, while `SEAWEEDFS_UBI_ALLOW_PLAINTEXT_BESIDE_TLS=true` preserves the legitimate dual-listener migration shape. |

## Decisions that need a human

These cannot be settled by implementation work and should be recorded above with
their reasoning when they are made.

1. **Which filer metadata store backends are supported.** Each added backend is
   a dependency, a credential, and a failure mode to qualify. The plain build
   already compiles in PostgreSQL, MySQL, Redis, MongoDB, etcd, Cassandra, HBase,
   ArangoDB, FoundationDB, and embedded LevelDB, so this is a question of which to
   *qualify*, not which are available. Needed during package 4.
2. **What update cadence and security-response target will this project commit
   to?** [`docs/SUPPORT.md`](SUPPORT.md) cannot define a support period without
   it. Upstream releases roughly every seven to ten days in one linear line,
   fixes only the latest release, and maintains no older line, so there is no
   backport target and security maintenance necessarily means rolling forward.
   The qualification each increment owes cannot be completed weekly and
   indefinitely. The honest options are a defined qualification lag with a stated
   exposure window, a selective adoption policy that skips increments carrying no
   relevant fix, or a narrower support promise. Choosing none of them means the
   project drifts into one by accident. Deferred to package 8, where the real
   qualification cost will be visible; it binds nothing before then.
3. **How far to go on provenance.** Recording reviewed digests is the floor.
   Building from source in a controlled pipeline would be materially stronger
   and materially more work, and it changes what this project is.
4. **Whether anonymous read access is ever a supported configuration**, or
   always a deployment-owned deviation.
5. **Whether the embedded Iceberg REST Catalog is permanently out of scope** or
   a later qualification target, given that `lakekeeper-ubi` already owns that
   role in this organization.
6. **What durability the first release is willing to claim**, and therefore what
   replication topology has to be qualified before it can be published.

## Standing obligations at every upstream version bump

SeaweedFS releases often and promises nothing about compatibility. Each bump
owes all of the following, and a bump is not complete until they are done.

- Re-verify every upstream behavior asserted in `CLAUDE.md`, because each one is
  a read of a specific release: the S3 allow-all default, the default listener
  set including any newly default-enabled service, the temporary-directory data
  defaults, the `security.toml` contract, and the release asset layout.
- Re-measure the binary's runtime linkage and required glibc symbol version.
- Update the artifact lock through a reviewed change, never a build-time
  resolution.
- Re-run the full runtime, negative, and restricted-runtime suites on both
  architectures.
- Check for a new default-enabled listener or role, and disable anything outside
  the supported boundary.
- Check whether the on-disk volume format or filer schema changed, and qualify
  the upgrade and rollback path if so.
- Regenerate SBOMs and scans, and disposition new findings.
