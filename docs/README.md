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

**Next task: work package 2**, upstream artifact acquisition and the digest lock.

Work package 1 is complete except for two items that only a human can close, and
neither of them blocks package 2:

- **Approve the proposed first-release boundary** in
  [`docs/SUPPORT.md`](SUPPORT.md#proposed-first-release-boundary). It is marked as
  a proposal and nothing depends on it being a commitment until package 3 fixes
  the supported role set in the entrypoint.
- **Decide the update cadence and security-response targets.** This one is worth
  reading the reasoning for before deciding, in
  [upstream maintenance constrains what this project can
  promise](SUPPORT.md#upstream-maintenance-constrains-what-this-project-can-promise).
  It is the sharpest constraint this project has and it has no comfortable
  answer.

Package 2 ranks next because package 3 cannot build an image without verified
bytes to build it from, and because the variant decision package 2 makes is one
the release contract already depends on.

Its first task is the decision-shaped one: establish what upstream provenance is
actually available — whether any release asset carries a GitHub artifact
attestation, and whether a reproducible build from source is feasible — because
the answer determines whether the lock is the floor or the ceiling of this
project's provenance story.

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
| `docs/SUPPORT.md` — support classifications and lifecycle | Present | 1 |
| `docs/QUALIFICATION.md` — evidence ledger schema | Present | 1 |
| `docs/BADGING.md` — permitted public claims | Present | 1 |
| `docs/ARTIFACT-ACQUISITION.md` — lock, verification, trust limits | Planned | 2 |
| `docs/HERMETIC-BUILD.md` — network-free assembly contract | Planned | 2 |
| `docs/CONFIGURATION.md` — variables this image adds and its guards | Planned | 3 |
| `docs/ARCHITECTURE.md` — roles, listeners, and data flow | Planned | 3 |
| `docs/USE-CASES.md` — supported profiles | Planned | 4 |
| `docs/STORAGE.md` — durability, replication, backup, restore | Planned | 4 |
| `docs/TLS.md` — client TLS and inter-component mTLS | Planned | 4 |
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

## Package 1: repository contract, scope, and evidence ownership

- [ ] Approve the proposed first-release boundary in
      [`docs/SUPPORT.md`](SUPPORT.md#proposed-first-release-boundary), including
      the exact supported role set, the single-container versus separated-role
      profiles, and every deferral, and remove the proposal notice when approved.
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
- [ ] Decide which release asset variant is admitted. Upstream publishes
      `linux_amd64`, `linux_amd64_full`, `linux_amd64_large_disk`,
      `linux_arm64`, `linux_arm64_large_disk`, and role-specific
      `weed-volume` and `weed-worker` builds. Record what each variant changes,
      why the chosen one is chosen, and what the `large_disk` decision costs an
      operator who later needs it.
- [ ] Investigate whether upstream publishes GitHub artifact attestations or a
      reproducible build path for any release asset, and record the finding
      either way. If one exists, verifying it becomes a required admission step.
- [ ] Create a schema-validated lock under `artifacts/` for both architectures
      containing the release tag, archive URL, archive size and SHA-256, the
      upstream-published MD5 as a recorded value, the extracted binary size and
      SHA-256, the Go build identifier, and the linkage facts below.
- [ ] Measure and record the runtime linkage of the shipped binary: whether it
      is statically or dynamically linked, the highest required glibc symbol
      version if any, the needed shared libraries, and every library glibc may
      load at runtime rather than link. Re-measure on every image build instead
      of assuming a future release keeps the same properties.
- [ ] Acquire artifacts outside the container build, verify before and after
      transfer, and fail closed on a size, digest, version, or linkage mismatch.
- [ ] Add negative tests proving the gate rejects a tampered archive, a
      tampered extracted binary, a wrong-version archive, a truncated download,
      and a missing lock entry.
- [ ] Prove assembly succeeds with the build network disabled, and record in
      `docs/HERMETIC-BUILD.md` what that property does and does not defend
      against.
- [ ] Implement a reviewed lock-update workflow that proposes changes on a
      branch, and never resolves a version at build time.
- [ ] Record source availability, redistribution terms, trademark boundaries,
      and the Apache 2.0 obligations in `THIRD_PARTY_NOTICES.md`.

**Exit criteria.** Every build consumes exactly the bytes recorded in a reviewed
lock, an unreviewed byte cannot enter the image, and the residual provenance
weakness is documented rather than obscured.

## Package 3: rootless minimal image, role contract, and entrypoint guards

- [ ] Add a digest-pinned UBI 9 build stage and a package-manager-free final
      stage, installing only the verified `weed` binary and the runtime files it
      needs.
- [ ] Define the runtime identity: a fixed non-root UID in group `0`, with
      group-writable state directories so an arbitrary assigned UID also works.
      Record the exact UID and the reason for it in `docs/ARCHITECTURE.md`.
- [ ] Declare the writable state directories explicitly — master metadata,
      volume data and index, and filer store — and prove the image runs with a
      read-only root filesystem and nothing else writable.
- [ ] Implement the entrypoint as a role dispatcher that `exec`s the server
      process so it runs as PID 1 and receives signals directly, with no phase
      that changes user or group.
- [ ] Enforce a supported-role allowlist. `master`, `volume`, `filer`, `s3`,
      `server`, and the informational `version` and `shell` paths are permitted;
      any other subcommand is refused with a diagnostic naming the supported
      set. Informational paths must keep working so a refused container stays
      diagnosable.
- [ ] Implement the fail-closed S3 authentication guard,
      `SEAWEEDFS_UBI_REQUIRE_S3_AUTH`, default `true`: starting the `s3` role
      with no identity source — no configuration file, no filer-held
      configuration, no credential environment — is a startup failure with exit
      status `78` (`EX_CONFIG`) and a diagnostic naming what to configure. An
      unrecognized value is also a failure, so a misspelled toggle cannot
      quietly disable the control. Never print a key or secret.
- [ ] Implement the explicit-data-directory guard,
      `SEAWEEDFS_UBI_REQUIRE_EXPLICIT_DATA_DIR`, default `true`: a `master` or
      `volume` role whose data directory is unset, or resolves to the process
      temporary directory, fails at startup rather than silently storing durable
      state on a `tmpfs`.
- [ ] Disable the `weed s3` Iceberg REST Catalog and Lance Namespace listeners
      by default by passing `0`, and gate re-enabling them behind explicit
      `SEAWEEDFS_UBI_` opt-ins that are documented as unqualified.
- [ ] Fix the default listener set and document it: master `9333`, volume
      `8080`, filer `8888`, S3 `8333`, and the gRPC companion ports upstream
      derives by adding `10000` to the HTTP port. Confirm no privileged port is
      used and that the pprof debug listener stays disabled.
- [ ] Ensure logs and metrics go to the container log streams and an explicit
      metrics port, with no writable log path required.
- [ ] Write `docs/CONFIGURATION.md` covering every `SEAWEEDFS_UBI_` variable,
      each guard's exact behavior, and — just as important — what each guard
      does **not** check. The S3 guard proves an identity source is configured;
      it does not judge whether a key is strong, unique, or secret.
- [ ] Add a hardened Compose or Quadlet development stack with no default
      credentials and no anonymous access.
- [ ] Add a restricted-runtime smoke suite that provisions its own fixtures and
      per-run credentials, and asserts non-root operation, zero capabilities,
      `no-new-privileges`, read-only root, the version match, authenticated S3
      access, refusal of anonymous access, and each negative startup case.

**Exit criteria.** A container built from this repository runs every supported
role as a non-root process on a read-only root filesystem with no capabilities,
refuses to start in the two configurations that would silently be unsafe, and
proves it in an automated suite.

## Package 4: supported configuration and runtime qualification

### Object storage path

- [ ] Qualify the S3 API against a real client for bucket and object create,
      read, list, multipart upload, delete, and error behavior, and record which
      S3 behaviors SeaweedFS implements differently from the reference service.
- [ ] Qualify the table-format path end to end: write and read Iceberg tables
      through `lakekeeper-ubi` against this image, replacing the unhardened
      fixture that project uses today. Pin the engine toolchain so the result is
      reproducible.
- [ ] Test identity isolation: two identities with distinct buckets and
      credentials, proving one cannot read or write the other's bucket.
- [ ] Qualify S3 listener TLS, including a private CA chain, and prove
      certificate verification is not silently disabled.
- [ ] Decide and document the supported position on anonymous read access.

### Cluster, durability, and state

- [ ] Qualify the separated-role profile: master, volume, filer, and S3 in
      distinct containers with explicit addresses and no shared filesystem.
- [ ] Decide and document the supported filer metadata store backends, with the
      credential handling and failure behavior of each.
- [ ] Prove data written through the S3 API survives container replacement,
      restart, and an unclean stop, and that acknowledged writes are not lost on
      graceful shutdown.
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

- [ ] Provide tested `security.toml` examples enabling gRPC mTLS between master,
      volume, filer, and S3, and prove a client without a valid certificate is
      refused.
- [ ] Provide tested examples enabling volume read and write JWTs, and prove a
      direct volume request without a token is refused.
- [ ] Document the `-whiteList` IP restriction, its limits, and why it is not a
      substitute for authentication.
- [ ] State clearly, for every supported profile, which listeners may face a
      client network and which must not.

### Operations

- [ ] Implement and test structured logging and metrics profiles for each role,
      and qualify that credentials, tokens, and keys never appear in a log line
      or error body.
- [ ] Define health and readiness checks per role that reflect real service
      health rather than process liveness.
- [ ] Write `docs/USE-CASES.md`, `docs/STORAGE.md`, `docs/TLS.md`, and
      `docs/LOGGING.md` from the qualified results, and update `SECURITY.md`
      with the deployment-critical upstream behavior each one exposes.

**Exit criteria.** Every configuration this project intends to support has a
positive test, a negative test, an example, operational guidance, and a support
classification — and every configuration it does not support is named.

## Package 5: CI, supply chain, and release automation

- [ ] Add least-privilege CI with native AMD64 and ARM64 builds and smoke runs,
      immutable third-party Action references, and hash-locked tooling.
- [ ] Add repository and workflow security analysis, including CodeQL for
      Actions, workflow auditing, configuration scanning, and OpenSSF Scorecard.
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
      digests, landing as reviewable pull requests.
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

## Decisions that need a human

These cannot be settled by implementation work and should be recorded with their
reasoning when they are made.

1. **What update cadence and security-response target will this project
   commit to?** This is the first decision to make, because
   [`docs/SUPPORT.md`](SUPPORT.md) cannot define a support period without it.
   Upstream releases roughly every seven to ten days in one linear line, fixes
   only the latest release, and maintains no older line, so there is no backport
   target and security maintenance necessarily means rolling forward. The
   qualification each increment owes cannot be completed weekly and indefinitely.
   The honest options are a defined qualification lag with a stated exposure
   window, a selective adoption policy that skips increments carrying no relevant
   fix, or a narrower support promise. Choosing none of them means the project
   drifts into one by accident.
2. **Is the single-container `server` profile supported, or development only?**
   It is genuinely useful for a single-node deployment and for the Iceberg test
   path, but it collapses every trust boundary the separated profile creates.
3. **Which release asset variant is admitted**, and whether the `large_disk`
   build is the safer default given that switching later is not a trivial
   migration for an operator who has already stored data.
4. **Which filer metadata store backends are supported.** Each added backend is
   a dependency, a credential, and a failure mode to qualify.
5. **How far to go on provenance.** Recording reviewed digests is the floor.
   Building from source in a controlled pipeline would be materially stronger
   and materially more work, and it changes what this project is.
6. **Whether anonymous read access is ever a supported configuration**, or
   always a deployment-owned deviation.
7. **Whether the embedded Iceberg REST Catalog is permanently out of scope** or
   a later qualification target, given that `lakekeeper-ubi` already owns that
   role in this organization.
8. **What durability the first release is willing to claim**, and therefore what
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
