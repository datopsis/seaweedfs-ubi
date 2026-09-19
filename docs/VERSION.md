# Versioning and releases

The published container image is versioned independently from repository
history. Git commits identify every repository revision; release versions
identify container artifacts that this project intentionally publishes and
supports.

## Container release format

Annotated release tags use:

```text
v<seaweedfs-version>-ubi<ubi-major>-r<YYYYMMDD>.<daily-sequence>
```

For example, `v4.46-ubi9-r20260912.1` would identify:

- SeaweedFS `4.46`;
- the UBI 9 runtime product line;
- a Datopsis container release created on 2026-09-12 UTC; and
- the first container release created on that UTC date.

The `r` distinguishes this project's container release from an upstream
SeaweedFS release. The eight-digit date is the UTC date on which the immutable
release tag is created. The sequence is a positive integer beginning at `1` and
increments for every additional container release created on the same UTC date,
regardless of SeaweedFS or UBI major version. Dates must not be backdated.

Upstream tags its releases without a leading `v`, as `4.46`. This project's tags
always carry the leading `v`, so a tag is unambiguous about which project
created it.

This upstream-derived format is not Semantic Versioning. The downstream release
suffix communicates release chronology; it does not claim API-compatibility
semantics.

The tag includes the UBI major version because changing that version changes the
runtime product line and its compatibility and support boundary. It deliberately
omits the UBI minor version: package updates can make the runtime filesystem
newer than the original base-image snapshot, and a named minor version does not
identify exact bytes. The exact UBI reference and digest remain required in OCI
metadata, the SBOM, provenance, and release evidence.

Release tags are immutable. Never move or reuse a release tag. Production
deployments should pin the OCI digest; a human-readable tag describes a release,
while its digest identifies exact image content.

The release workflow must accept only tags matching:

```regex
^v[0-9]+\.[0-9]+(\.[0-9]+)?-ubi[1-9][0-9]*-r[0-9]{8}\.[1-9][0-9]*$
```

The optional third component exists because SeaweedFS numbers releases in two
components today and this project must not need a policy change if upstream ever
publishes a third. It is permitted, not expected; the tag must reproduce the
upstream version exactly as upstream published it.

Pattern matching is only the first check. The workflow must also validate a real
UTC calendar date, the selected SeaweedFS version against the artifact lock, the
selected UBI major version against the locked base images, the daily sequence
against existing immutable tags, and that the tagged commit is the protected
`main` release commit.

The deterministic portion is implemented by
`scripts/lib/validate_release_tag.py`. A caller must provide the workflow's UTC
date and a newline-delimited snapshot of existing repository tags; the validator
refuses a backdated date, a reused or non-next sequence, a version that differs
from the artifact lock, a UBI major that differs from either Containerfile base,
or a base that is not digest-pinned. It emits the admitted fields as JSON for a
later workflow step. It deliberately performs no network lookup.

This validator is necessary but not sufficient release admission. The future
tag workflow must obtain a complete tag snapshot, prove the tagged commit is the
protected `main` release commit, require matching candidate evidence and all
release gates, and only then build or publish. Until that workflow exists and is
qualified, running the validator does not create a release candidate or grant
publication authority.

## Upstream makes no compatibility promise

SeaweedFS is past `1.0` but is not semantically versioned. Releases are numbered
in two components, arrive roughly weekly, and an increment carries no statement
about API, configuration, on-disk format, or behavioral compatibility. Upstream
also states that security fixes land only in the latest release, so there is no
maintained older line to pin to.

Every upstream increment is therefore a qualification event, not a routine
dependency bump. Each one owes:

- a read of the upstream release notes and commit range for behavioral change;
- re-verification of every upstream behavior this repository asserts, listed
  under
  [standing obligations](README.md#standing-obligations-at-every-upstream-version-bump);
- a reviewed artifact lock update, including re-measured binary linkage;
- the full runtime, negative, and restricted-runtime suites on both
  architectures;
- a check for any newly default-enabled listener or role, which must be disabled
  if it falls outside the supported boundary;
- a check for an on-disk volume format or filer schema change, and qualification
  of the upgrade and rollback path if either changed; and
- a consumer-visible break stated in the changelog entry for the release.

A downstream release tag never implies upstream compatibility. It records which
upstream version this project packaged and when.

## Artifact identity

The annotated Git tag and immutable GHCR image tag use the complete version,
including the leading `v`. OCI metadata records:

- `org.opencontainers.image.version` as the release identifier without the
  leading `v`;
- `org.opencontainers.image.revision` as the full Git commit SHA;
- `org.opencontainers.image.created` as the reproducible UTC creation time;
- the exact UBI base reference and manifest digest;
- the exact upstream SeaweedFS release tag, the **release asset variant**, the
  archive digest, and the extracted binary digest; and
- the artifact-lock digest used to prepare the build inputs.

The asset variant must appear in metadata because the release tag does not encode
it. Upstream publishes several Linux builds of the same version and they are not
interchangeable to an operator who has already stored data: the variant is a
compile-time build tag, and one of the tags changes the on-disk index format. Two
images carrying the same release tag but different variants would be
indistinguishable from the tag alone, which is exactly the ambiguity this section
exists to prevent. [Build variants](BUILD-VARIANTS.md) records which variant this
project admits, what each one changes, and what switching costs.

The image digest, not any label or tag, is the definitive artifact identity.

## When to change the container version

| Change | Version action |
| --- | --- |
| Change the SeaweedFS version | Use the new SeaweedFS version with the release date and next sequence for that UTC date. |
| Change the SeaweedFS release asset variant | Create a release using the current UTC date and next daily sequence, and state the variant change and its operator impact in the changelog. |
| Change the UBI major version | Use the new UBI major field with the SeaweedFS version, current UTC date, and next daily sequence. |
| Change only the UBI minor reference or digest | Keep the SeaweedFS and UBI major fields and create a release using the current UTC date and next daily sequence. |
| Change the artifact lock, runtime dependency set, runtime behavior, supported role set, default listeners, entrypoint or its guards, default configuration, build input, or release metadata | Create a release using the current UTC date and next daily sequence. |
| Deliberately rebuild otherwise unchanged inputs | Create a release using the current UTC date and next daily sequence. |
| Change only documentation, tests, development tooling, policies, examples not copied into the image, issue templates, or analysis workflows | Do not create or change a container release version unless an image is deliberately republished. |

Every newly published image receives a new immutable release tag. If more than
one release occurs on a UTC date, inspect existing tags and use the next unused
daily sequence; never fill an older gap or reuse a failed or withdrawn tag.

## Published tags

The first release publishes only:

- the immutable release tag, such as `v4.46-ubi9-r20260912.1`; and
- an immutable `sha-<short-commit>` traceability tag.

Mutable tags such as `latest`, `stable`, `4`, or `4.46` are not published. They
can be considered later only with documented movement, rollback, and
consumer-notification semantics. A mutable major tag is especially misleading for
an upstream line that makes no compatibility promise between increments.
Controlled deployments use an image digest.

## Repository-only revisions

A repository-only change is identified by its pull request and full Git commit
SHA. It does not become part of an existing supported container release merely
because it is merged to `main`.

This project does not create source-only GitHub Releases or tags. GitHub Releases
represent published container images. Use:

- a full commit SHA for an exact repository revision;
- `git describe --tags --always --dirty` for a convenient local identifier;
- the `Unreleased` section of `CHANGELOG.md` for notable changes intended for the
  next container release.

Not every repository-only change requires a changelog entry. Add one when an
operator, consumer, contributor, or security reviewer would reasonably need to
discover it. At the next image release, move accumulated entries into a dated
section named for the release tag.

## Release requirements

Before an annotated release tag is pushed:

1. Verify that the tag's SeaweedFS version and asset variant match the reviewed
   artifact lock, that its UBI major version matches the locked base images, and
   that release metadata records the exact UBI reference and digest.
2. Convert `Unreleased` changelog entries into a dated section for the tag and
   create a new empty `Unreleased` section.
3. Complete the applicable release gates in [the work plan](README.md) and the
   evidence record in [release qualification](QUALIFICATION.md).
4. Merge the reviewed release change to protected `main` with required checks
   passing.
5. Create the annotated tag from that exact `main` commit.
6. Allow the tag workflow to build, scan, attest, sign, publish, and create the
   GitHub Release.
7. Verify the manifest architectures, digest, signature, provenance, SBOM,
   labels, scan evidence, and release assets before announcing support.

The `sha-<short-commit>` tag supplements but never replaces the release tag and
digest.
