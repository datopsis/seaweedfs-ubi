# Changelog

All notable changes to this project are recorded in this file.

The project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
but container releases use the upstream-derived format documented in
`docs/VERSION.md` rather than Semantic Versioning. GitHub Releases correspond
only to published container images; repository-only changes remain under
`Unreleased` until the next image release.

## [Unreleased]

### Added

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
