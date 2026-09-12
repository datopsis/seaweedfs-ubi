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
