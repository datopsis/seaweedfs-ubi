# Changelog

All notable changes to this project are recorded in this file.

The project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
but container releases use the upstream-derived format documented in
`docs/VERSION.md` rather than Semantic Versioning. GitHub Releases correspond
only to published container images; repository-only changes remain under
`Unreleased` until the next image release.

## [Unreleased]

### Fixed

- Bound the generated secret to the backup-archive validator's option even
  when the secret begins with a hyphen, preserving the archive exclusion check.

- Set a TLS 1.2 minimum for the gRPC mTLS test client, removing the older
  protocol negotiation flagged by CodeQL without changing the test's
  client-certificate scope.
- Wait for the volume to appear in the master's topology before asserting
  initial separated-role readiness, using the existing bounded recovery probe.

### Added

- Started the SeaweedFS-specific L1/L2/L3 requirement tree and generated trace
  matrix, with fail-closed structural and Python test-link checks. The tree is
  incomplete, and a test link is not release-candidate evidence.

- Added pinned Trivy image scans of both native CI development images, with
  validated OS and language-package coverage and 14-day retained full JSON
  inventories. These report-only scans do not yet enforce the planned fixed
  High/Critical gate.

- Added main-only publication of per-architecture Grype SARIF to GitHub code
  scanning for triage, with SARIF retained alongside the full JSON inventory.
  Pull-request jobs remain read-only; alert publication is not a vulnerability
  gate.

- Added pinned Grype scans of both native CI development images, retaining
  complete per-architecture JSON vulnerability inventories for 14 days. These
  report-only scans do not yet enforce the planned fixed High/Critical gate.

- Added per-architecture SPDX SBOM generation for CI development images, with
  a checked SeaweedFS Go inventory and 14-day retained artifacts. Release-image
  SBOMs, vulnerability gates, provenance, and signing remain separate work.

- Added a pinned, read-only pull-request dependency review that blocks newly
  introduced High or Critical advisories across all dependency scopes visible
  to GitHub's dependency graph. The graph is enabled and the new check is
  required on the default branch. This is distinct from future image scanning.

- Recorded the initial and first follow-up OpenSSF Scorecard findings and roadmap,
  and documented the required `validation`, `native image`, and `codeql`
  default-branch checks.

- Added a pinned OpenSSF Scorecard workflow with scoped OIDC and SARIF upload
  permissions, five-day SARIF retention, and code-scanning publication. README
  badges now show the `main` workflow status for CI, CodeQL, and Scorecard
  without implying a supported image release or minimum security score.

- Added a separate CodeQL workflow for GitHub Actions and Python, with
  `security-extended` queries, immutable Action pins, least-privilege upload
  permissions, and a stable aggregate check. Results go to GitHub code scanning;
  a passing job does not assert that no findings exist.

- Added negative assembly checks to both native CI jobs. They prove that a
  missing or altered bundle, changed lock, or unavailable pinned base prevents
  a build, and that an admitted bundle reaches an offline, no-pull Podman build
  command. The separate real build remains the image-assembly evidence.

- Added native AMD64 and ARM64 image CI jobs. Each verifies the runner and image
  architecture, admits the locked binary through the signed-digest path,
  exercises negative acquisition checks, assembles with Podman's build network
  disabled, and runs the full available restricted-runtime suite. A stable
  `native image` aggregate fails unless both native jobs pass. Listener parsing
  is shared Python code rather than GNU-awk-specific behavior.

- Added the CI validation foundation with least-privilege triggers, immutable
  Action pins, hash-locked pre-commit tooling, deterministic unit and negative
  lock tests, zizmor workflow auditing, Trivy configuration scanning, and a
  stable `validation` aggregate for branch protection. Backup archive validation
  now shares one implementation between the restore fixture and eight negative
  and positive unit cases.

- Added a tested cold Podman backup and restore procedure. Master, volume, and
  embedded filer state are exported only after every role stops, the original
  volumes are deleted, and the archives are imported into different volume
  names. Replacement container IDs must return the original S3 object byte for
  byte; credentials are recreated separately and excluded from the archives.

- Added bounded storage-exhaustion evidence. A separated master/volume fixture
  verifies a 3 MiB `tmpfs`, drives assigned writes until byte exhaustion is
  visible to the client and volume logs, and proves `-max=1` admits one volume
  while explicitly refusing another. Inode exhaustion remains unqualified
  because the rootless Podman backend cannot create an inode-limited mount.

- Added the first replicated-volume topology evidence. Two volume servers occupy
  distinct logical racks with replication `010`; the suite verifies the written
  object's exact bytes on both replicas, continued S3 reads after one volume
  process stops, and refusal to acknowledge a new replicated write while that
  rack is absent. Both replicas remain on one host, so the result is explicitly
  not host-, node-, disk-, backend-, or zone-loss evidence.

- Added a structured logging and metrics profile. Server logs default to JSON
  with a strict text-format opt-out, while metrics require an explicit listener
  per role and are documented for operations-network exposure only. The
  separated-role suite proves metrics remain absent by default and verifies
  Prometheus exposition and exact listener inventories when enabled. Secret
  checks now cover generated S3 credentials, a rejected JWT, its signing key,
  private-key material, and a rejected S3 request body within the exercised
  paths.

- Added role-specific health and readiness qualification. Master and filer use
  their meaningful native checks; S3 readiness is an authenticated API
  operation; volume readiness combines local health with registration in master
  topology. The suite pins two native false positives by removing dependencies:
  S3 `/readyz` stays green without the filer, and volume `/readyz` stays green
  without the master.

- Added negative gRPC mTLS qualification. The inter-component suite now proves
  that a client certificate from the configured CA reaches the HTTP/2 protocol,
  while a client presenting no certificate and one signed by an unrelated CA
  are both refused before gRPC traffic is accepted.

- Expanded the package 5 roadmap from generic CI bullets into concrete,
  reviewable workflows modeled on `datopsis/nginx-ubi`: least-privilege CI,
  native architecture matrices, CodeQL for Actions and Python, OpenSSF
  Scorecard, dependency review, workflow/configuration scanning, image scanners,
  retained evidence, and stable aggregate checks for branch protection.
- Added the supported-profile and listener-exposure matrix. It records that only
  authenticated TLS S3 may face clients, and documents from the locked 4.46
  source why `-whiteList` is only defense in depth: empty allows all, it uses the
  socket peer address, selected handlers opt into it, and volume reads remain
  open.

- Added separated-role state-survival qualification. Acknowledged S3 objects are
  checked byte for byte after ordinary restart, graceful shutdown and container
  replacement, and an unclean stop, always under the restricted runtime and
  with the same explicit data volumes. The accompanying storage guidance states
  why this is not replication, node-loss, backup, or multi-node evidence.

- Added a fail-closed S3 TLS listener guard. The `s3` and `mini` profiles now
  refuse a certificate combined with a nonzero HTTPS port because upstream
  leaves the original S3 port serving plaintext. A deliberate dual-listener
  migration requires `SEAWEEDFS_UBI_ALLOW_PLAINTEXT_BESIDE_TLS=true`.

- Established the `seaweedfs-ubi` repository and planned GHCR image identity for
  a security-oriented, rootless SeaweedFS container on Red Hat UBI 9.
- Established repository guidance for secure, rootless image development and
  review, including the upstream characteristics that make this project differ
  from the organization's RPM-based UBI images and from `lakekeeper-ubi`.
- Recorded the upstream trust position: SeaweedFS release assets carry only an
  MD5 sidecar, with no SHA-256 manifest, detached signature, or provenance
  attestation, so a reviewed digest lock proves reviewed bytes rather than
  publisher identity.
- Defined the complete forward-looking work plan as eight dependency-ordered
  packages to a signed first release, with the working first-release boundary,
  the evidence lifecycle, explicit deferrals, the decisions that need a human,
  and the obligations owed at every upstream version bump.
- Documented the deployment-critical upstream behavior an operator cannot skip:
  the allow-all anonymous S3 default, durable state defaulting to the process
  temporary directory, unauthenticated and unencrypted inter-component paths
  without an operator-supplied `security.toml`, and the Iceberg REST Catalog and
  Lance Namespace listeners that the S3 role opens by default.
- Selected SeaweedFS 4.46 as the initial development baseline on UBI 9 and
  adapted the sibling projects' immutable container versioning approach to an
  upstream line that is not semantically versioned.
- Defined container and repository versioning: the immutable release tag form,
  the tag validation pattern, prohibited mutable tags, the separation of
  container releases from repository-only revisions, and the requirement that
  OCI metadata record the upstream release asset variant, because the release tag
  cannot encode it and two images sharing a tag with different variants would be
  indistinguishable.
- Defined the support contract: classification terms, the current development
  matrix, the proposed first-release boundary, the ownership boundary between the
  image, the host or orchestrator, and the storage operator, and the reporting
  route.
- Recorded that upstream releases roughly every seven to ten days in a single
  linear line and fixes only its latest release, so there is no maintained older
  version to pin to and security maintenance can only mean rolling forward. The
  support contract therefore defines no update cadence or security-response
  target yet, and states the tension between qualification depth and update
  latency as a decision that needs a human rather than resolving it silently.
- Defined the release qualification evidence record, including the scope rules
  that prevent a single-container, single-role, or single-client result from being
  read as evidence for a separated, replicated, or conformant one, and the two
  structural residual risks every candidate record must restate.
- Defined the badge policy: the approved inventory with the work package that
  enables each badge, and explicit prohibitions on S3-conformance,
  hardened/STIG/CIS, FIPS, and durability or uptime badges.
- Made the support contract the single authority for the first-release boundary,
  so that the scope statement cannot drift between documents.
- Documented upstream's build variants and recorded which one this project
  admits. The variant is a compile-time Go build tag, not a runtime option:
  `5BytesOffset` raises the per-volume ceiling from 32 GB to 8 TB by widening the
  on-disk index offset, so one image carries exactly one variant and switching is
  a data migration rather than a redeploy. `large_disk` is admitted; `full` is
  not, because the filer backends it adds are outside the boundary and the
  PostgreSQL backend this organization would use is already in the plain build.
- Recorded that the variant migration path is not yet qualified, and that no
  variant change may be offered as supported until it is.
- Added a plain-language summary of what each work package involves, what "done"
  looks like, its rough size, and what it needs from a human, so the shape of the
  remaining work is legible without reading every checklist.
- Recorded the chosen package order — a working, tested, automatically built image
  before the compliance package — and the reasoning for it.
- Scoped the first release to the Datopsis analytical stack's S3 backend, and
  documented the five places that scope differs from a general-purpose S3 store,
  which are reversible, and the rule that the difference must stay in what the
  project qualifies rather than in what the image can do.
- Added a decisions-taken record, so that reopening a settled decision is a
  deliberate act rather than a drift.
- Defined two deployment profiles served by one image: a separated-role
  production profile, and a single-container standalone profile for local
  development, small local use, and test fixtures. They are the same bytes and
  differ only in which role the container starts, so one image keeps one SBOM, one
  signature chain, and one qualification record. The standalone profile starts
  only when `SEAWEEDFS_UBI_STANDALONE` is explicitly set and will print a startup
  notice naming what it cannot provide.
- Documented what the standalone profile can never provide, as consequences of
  running one process rather than gaps to close later: inter-component mTLS and
  JWTs are inert, replication and therefore durability are unavailable, component
  failure modes cannot be produced, inter-role discovery and addressing never
  execute, and there is no per-role isolation or tuning.
- Recorded which profile a test may use, so a fast standalone fixture covers
  functional behavior and the guards while the separated-role fixture remains
  required for anything whose subject is the topology. A standalone result may
  never be cited as evidence for a clustered claim.
- Superseded an earlier decision to refuse the upstream `server` subcommand
  outright. Refusing it protected a security claim by pushing multi-container cost
  into every fixture, including ones needing only functional coverage, and denied a
  real local-development use case.
- Based the standalone profile on upstream's `mini` subcommand rather than
  `server`. `mini` exists for exactly this purpose and is what upstream's own image
  runs by default, and admitting only one of the two single-process commands avoids
  supporting two overlapping paths. The profile disables WebDAV and the Admin UI,
  which `mini` enables by default and which are outside the boundary, and requires
  an explicit data directory rather than accepting `mini`'s working-directory
  default.
- Recorded what upstream actually publishes and what may be trusted about it.
  Release tarballs carry an MD5 sidecar and nothing else, while container images
  are signed with keyless cosign bound to an organization-repository workflow
  identity and built from the exact released commit. Because those images are
  published to a personal rather than an organization namespace, pulling one by tag
  unverified is weaker than taking the tarball while pulling one by digest with the
  signature enforced is stronger, so verification is mandatory on that path rather
  than an enhancement to it.
- Established that the single Go `weed` binary covers every supported role. The
  Rust `weed-volume` and `weed-worker` binaries in upstream's image are opt-in
  alternative roles, reachable only under separate role names in upstream's own
  entrypoint, and the Lance worker is outside the boundary.
- Established that upstream's image cannot serve as a base layer or a behavioral
  model: it is Alpine-based and its entrypoint starts as root, recursively chowns
  the data directory, and drops privileges with `su-exec`, which is the startup
  privilege transition this project's contract forbids.
- Documented three candidate acquisition paths with their costs — the release
  tarball, the cosign-verified container image, and building from upstream source —
  and recommended the verified image, leaving a source build open as a later step
  rather than a foreclosed one.
- Recorded that upstream's Dockerfile claims Go FIPS 140-3 mode is on by default
  while its build sets no `GOFIPS140` and the Go default is off, so the claim must
  not be repeated and the real determination is owed by work package 6.
- Chose the cosign-verified official container image as the acquisition path,
  pinned by digest, with the release tarball retained as a documented fallback and
  a source build left open rather than foreclosed.
- Added the reviewed artifact lock for SeaweedFS 4.46 `large_disk` on both
  architectures, recording the release tag and commit, the variant and its build
  tags, the image index digest, the cosign issuer and certificate identity, and per
  architecture the manifest digest and the extracted binary's digest, size, ELF
  machine, linkage, and embedded commit.
- Added the artifact admission gate. It verifies the image index and each
  architecture manifest with cosign against a pinned identity and issuer, fetches
  only by digest and never resolves a tag, copies the binary out of a created
  rather than a running container so a foreign architecture needs no emulation, and
  refuses on any mismatch of size, digest, ELF machine, linkage, embedded commit, or
  variant marker, or on a missing verification tool.
- Verified the provenance claim rather than asserting it: the index and both
  architecture manifests verify against the recorded identity, the signing
  certificate names the `seaweedfs/seaweedfs` organization repository at
  `refs/tags/4.46`, and its recorded commit was independently cross-checked against
  the commit that the release tag resolves to.
- Confirmed both binaries are statically linked by ELF inspection rather than by
  trusting upstream's build flags, so neither carries a glibc version requirement.
- Confirmed the admitted build is the `large_disk` variant from the artifact itself:
  the binary reports its maximum volume size at runtime, `8000GB` rather than the
  default build's `30GB`, so the variant is measured rather than inferred from a tag
  name.
- Added a lock checker that validates agreement between fields, not only shape,
  because the dangerous failure is a half-edited lock that still parses: a tag
  bumped without the certificate identity, a commit that no longer prefixes the
  recorded one, a statically linked binary that also lists needed libraries. It
  reports every problem at once rather than stopping at the first, and runs as a
  local hook. Written without a schema library, since the cross-field checks that
  catch the real failures cannot be expressed in JSON Schema and a hash-locked
  environment should not gain a dependency for a single-file check.
- Added a reviewed lock-update path. `scripts/update-lock.py` resolves the release
  tag, verifies the signature, cross-checks the certificate's commit against the
  commit the tag resolves to, extracts and measures both architectures, and writes
  a lock whose diff a human reads. Resolution happens there and nowhere else, so a
  moved tag cannot change what a build admits. Regenerating the committed 4.46 lock
  reproduces it exactly, including the Rekor log index.
- Added the hermetic build contract, stating what network-free assembly defends
  against and — at greater length — what it does not: it does not make upstream
  trustworthy, does not detect a compromised upstream signing identity, does not
  protect the acquisition host, does not validate the base image's contents, and is
  not reproducibility.
- Added negative tests so the gate is observed refusing rather than assumed to.
  Offline: a tampered binary of the correct size, a truncated download, appended
  bytes, a binary offered as the wrong architecture, an architecture absent from the
  lock, a non-ELF file, a missing file, and an unparseable lock. With a network: a
  different workflow identity, a different git ref, a different OIDC issuer, and an
  unsigned digest.
- Added the Apache License 2.0 for Datopsis-authored work, third-party notices
  separating packaging terms from SeaweedFS and UBI terms, contribution
  guidance, and a private vulnerability-reporting policy.
- Added Code Owners, a security-aware pull request template that requires
  upstream-claim verification, and structured public bug-report and private
  security-reporting routes.
- Added pinned local pre-commit checks for repository hygiene, shell code,
  container build files, GitHub Actions, private keys, and attribution
  trailers, with a hash-locked Python requirements file.
- Added grouped Dependabot updates for Actions, pre-commit hooks, and the
  pinned CI Python environment.
- Enabled a protected default branch, secret scanning with push protection, and
  private vulnerability reporting.
- Added the container image: a digest-pinned, package-manager-free UBI 9 Micro
  runtime carrying only the verified `weed` binary, an entrypoint, and a CA
  bundle. There is no compilation stage, because the upstream binary is
  statically linked; UBI Minimal appears solely as a source of trust material
  copied as a file, since Micro ships none and an empty trust store fails
  confusingly.
- Added the entrypoint: a role dispatcher that enforces the supported-role
  allowlist, applies the two fail-closed startup guards, disables the listeners
  outside the boundary, and `exec`s the server so it becomes PID 1 and receives
  signals directly. It runs as the same non-root identity as the server, changes
  no ownership, and switches no user.
- Added the build phases as separate commands, because acquisition and assembly
  have different trust properties: acquisition and base-image pulls reach the
  network, assembly does not and re-verifies the bundle before using it, since a
  bundle is an ordinary directory and the two steps can be separated by a
  transfer.
- Added the smoke suite, which runs every case with a read-only root filesystem,
  all capabilities dropped, and `no-new-privileges`, so an image needing more
  fails rather than quietly receiving them. Twenty assertions covering the role
  allowlist, both guards and their diagnostics, that opting a guard out is
  honoured, PID 1, the non-root uid, the absent listeners, no privileged port,
  survival across container replacement, and secrets staying out of the logs.
- Fixed the standalone profile shipping the Iceberg REST Catalog and Lance
  Namespace listeners while the documentation said both were disabled. The
  entrypoint disabled them for the `s3` role and missed that `mini` names the same
  flags differently. Reading the open ports out of a running container is what
  found it, so that measurement is now an assertion rather than a one-off check.
- Recorded the measured listener set for the standalone profile, including that
  `mini` places the volume server on 9340 rather than the volume role's 8080.
- Added the configuration reference, covering every variable this packaging adds,
  each guard's behaviour, and what each guard does not check: the S3 guard cannot
  see filer-held identities and does not judge a key's strength, and the data
  directory guard cannot tell a persistent mount from a writable layer.
- Added the separated-role fixture, which brings up `master`, `volume`, `filer`,
  and `s3` as four containers on a real network and asserts what one process
  cannot show: that the roles discover and reach each other by address, each
  role's exact listener set, that no role opens a privileged port or runs as
  root, and that the S3 role needs no writable path at all because its state
  lives in the filer.
- Added hardened Compose stacks for both profiles, with no default credential in
  either. Only the S3 API is published, and only on loopback: without a
  `security.toml` the master, volume, and filer listeners are unauthenticated, so
  they stay on the internal network.
- Turned off `allowDeleteBucketNotEmpty` and `autoCreateBucket` for the S3 role
  and the standalone profile alike. Upstream enables both. The first makes
  `DeleteBucket` against a bucket that still holds objects delete every one of
  them, where the S3 API answers `BucketNotEmpty` and deletes nothing, so a client
  written against S3 semantics can destroy data with a call it expects to fail.
  The second turns a mistyped bucket name into a new bucket rather than an error.
  Passing either flag explicitly restores upstream's behaviour.
- Added the architecture reference: image contents, startup sequence, per-role
  listeners, data flow, and the trust boundaries, including that the boundary
  between the roles belongs to the operator and not to the image.
- Measured the image rather than describing it: 232.5 MiB assembled, of which the
  upstream binary is 209.8 MiB and the UBI Micro base 22.6 MiB, leaving about
  16 kB for everything this project adds. A package-manager-free Micro base does
  not make this a small image.
- Recorded why the binary is not stripped. It carries roughly 62 MiB of symbol
  table and DWARF sections, and removing them would take the image to about
  171 MiB, but the shipped binary would no longer be the bytes whose digest and
  signature were verified. The provenance chain is worth more than 26% of the
  size. Related: upstream's tarball build is stripped while its container build is
  not, so the fallback acquisition path would produce a smaller image with weaker
  provenance.
- Added S3 API qualification against a real client. `tests/s3.sh` stands up the
  separated-role cluster with three identities and drives the API with a
  dependency-free SigV4 client, so the gateway is proven to authenticate rather
  than merely to have refused to start without a config file. An authorised
  identity round-trips an object byte for byte and sees it in a listing; an
  anonymous caller is refused on read, write, and list; a valid access key with
  the wrong secret is refused; and a bucket-scoped tenant cannot read, write, or
  list another tenant's bucket.
- Verified at the API level that the two upstream defaults this image disables
  actually take effect. A flag that is passed but ignored would look identical in
  the process arguments, so a write to a missing bucket is confirmed to fail
  rather than create it, and deleting a non-empty bucket is confirmed to be
  refused rather than to remove its contents.
- Wrote the test client rather than pulling one in. A large CLI image would put
  an unpinned third party inside the one suite whose job is to prove the access
  controls work, and it would make the suite awkward to run on a controlled
  network.
- Recorded and asserted a divergence from the S3 API rather than working around
  it. SeaweedFS models a bucket as a directory, so a key containing a slash leaves
  a directory entry that outlives the object: the listing goes empty while the
  bucket does not, and with recursive bucket deletion disabled the bucket then
  cannot be deleted even though a client sees nothing in it. The suite pins that
  behaviour so an upstream change to directory cleanup surfaces as a failure to
  review.
- Seeded test configuration through a tar stream into a volume rather than a host
  bind mount or a host-path copy, neither of which is portable: a rootless machine
  VM sees only part of the host filesystem, so both fail wherever the engine
  cannot resolve the path the shell produced.
- Qualified multipart upload, which the table-format path depends on because
  Parquet files routinely exceed what a single PUT carries. Initiate, part upload,
  complete, and abort are all exercised, with parts at the 5 MiB minimum the S3
  API imposes rather than three tiny parts that would not touch the same path.
  The reassembled object is compared by digest, not only by length, and the part
  content is non-uniform so that parts reassembled out of order are caught instead
  of being hidden by a run of identical bytes. An aborted upload is confirmed to
  leave no readable object, and a neighbouring tenant is refused when it tries to
  add a part to an upload it does not own.
- Measured the security boundary between the roles instead of describing it.
  `tests/inter-component.sh` runs the cluster twice, once without a
  `security.toml` and once with gRPC mTLS and write JWTs, and probes the filer
  and volume servers directly in both. The result corrects what the security
  policy previously implied: a `security.toml` closes one of four paths that
  bypass the S3 gateway.
- Established that three read paths stay open even with a `security.toml` in
  place. The filer discloses an object's storage location, the filer serves its
  content, and a volume server serves its bytes by file id. This is structural,
  not a misconfiguration: upstream does not support read JWTs alongside a filer,
  and the S3 API requires a filer, so no configuration in a topology that serves
  S3 can close them. Network isolation is the only remaining control, which makes
  keeping the master, volume, and filer listeners off client-reachable networks a
  requirement rather than a recommendation.
- Confirmed the mitigation that does work: with write JWTs configured, a direct
  write to a volume server without the master's token is refused with HTTP 401,
  where the same request succeeds with HTTP 201 in the baseline.
- Confirmed the cluster still serves S3 with gRPC mTLS and write JWTs in effect,
  using a throwaway CA and per-role certificates generated for each run.
- Added the TLS and inter-component boundary reference, including a working
  `security.toml` example, the certificate lifecycle expectations, and an explicit
  list of what is still unqualified: client-facing TLS on the S3 listener,
  certificate rotation, mTLS rejection behaviour, and HTTPS on the master, volume,
  and filer listeners.
- Qualified TLS on the client-facing S3 listener against a private CA. A client
  trusting the CA completes the handshake and round-trips an authenticated
  object, and the same port stops answering plain HTTP, so supplying a
  certificate upgrades the listener rather than adding a second one.
- Proved the verification is real rather than incidental. A client trusting only
  an unrelated CA is refused at the handshake, and a hostname the certificate
  does not cover is refused, so the successful round trip says something about
  the server's identity instead of only about bytes moving. The certificate needs
  a matching `subjectAltName`; a common name alone is ignored.
- Recorded a configuration hazard, measured rather than inferred. Adding
  `-port.https` does not move TLS to a second port: it starts TLS there and leaves
  the original port serving the S3 API in plaintext. With a certificate, a key and
  `-port.https=8334` the container listens on 8333, 8334 and 18333, and the
  plaintext port really does serve the API. Whether the entrypoint should refuse
  that combination is recorded as a decision for a human rather than settled
  unilaterally.
