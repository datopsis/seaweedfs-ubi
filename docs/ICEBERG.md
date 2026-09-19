# Iceberg storage-path development fixture

`tests/iceberg.sh` is the first in-repository end-to-end test of this image as
the object store beneath `lakekeeper-ubi`. It uses the image's explicitly
opted-in `mini` profile, PostgreSQL 17, and PyIceberg 0.12.0
with PyArrow 25.0.1. It runs on an isolated local container network with
generated credentials. The SeaweedFS, Lakekeeper and engine containers use
read-only roots, dropped capabilities and no-new-privileges; the disposable
upstream PostgreSQL fixture has its own initialization permissions. SeaweedFS
state and its S3 identity file are in separate named volumes; the identity
volume is mounted read-only and both are removed
after the run. PostgreSQL is disposable test state, not a deployment example.

The test creates a warehouse bucket, checks anonymous S3 access is denied,
confirms Lakekeeper rejects invalid storage credentials, and registers valid
ones. An independent PyIceberg client creates a table and writes three rows.
It reads the rows back, confirms the metadata JSON and Parquet objects exist
in SeaweedFS, restarts Lakekeeper, and reads the same rows again. It fails if
generated credentials appear in SeaweedFS or Lakekeeper logs. This does **not**
exercise SeaweedFS replication, separate roles, inter-component mTLS/JWTs,
multi-host failure, PostgreSQL durability, or a release candidate.

The S3 identity uses `s3.json`, not `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` in the SeaweedFS container environment. In the initial
local trial, upstream SeaweedFS 4.46 logged the access-key ID when loading the
environment-variable identity. The read-only file path avoided that log
exposure in the subsequent development run. The negative log assertion stays
in the fixture so a regression fails visibly.

## Local development run

Build this repository's development image using its verified artifact bundle.
Build a Lakekeeper development image from the sibling repository's verified
bundle, then run:

```console
LAKEKEEPER_IMAGE=localhost/lakekeeper-ubi9:development bash tests/iceberg.sh
```

`IMAGE` and `CONTAINER_RUNTIME` may select other already-built local images
and Podman or Docker. The script refuses to run without either application
image. It pulls only the digest-pinned PostgreSQL and Python fixture images;
it does not build or pull an unreviewed SeaweedFS or Lakekeeper application
image. The Python base is pinned to its multi-architecture OCI index digest.
The engine installs exact top-level PyIceberg/PyArrow versions into a temporary
filesystem once per run, but transitive Python wheels are **not** hash-locked.
That is a remaining reproducibility gap: the fixture is development evidence,
not an offline or release-candidate qualification procedure. Do not promote
its result to a release claim or a broad S3/Iceberg conformance claim.

The 2026-09-19 UTC local run used the clean sibling repository at commit
`ea53b21fc83d89de3d766a84614737ff57d5c230` to assemble Lakekeeper 0.13.4 from its
verified local bundle. It passed the table round trip and catalog restart on
an AMD64 Podman development host. This historical run is not evidence for
ARM64, a released image, or a multi-node topology.

## Work needed before closing package 4

1. Hash-lock all engine wheels for each native architecture or build a
   digest-pinned engine fixture from reviewed dependencies; record its full
   dependency inventory and version in retained evidence.
2. Build or obtain the exact Lakekeeper image under a reviewed, immutable
   cross-repository input contract. Run this test in protected native CI on
   both architectures and retain image digests and sanitized logs.
3. Repeat the object path against the separated-role SeaweedFS profile used
   for production, with the selected security and filer-backend profiles.
   Keep the standalone result separate from topology/durability evidence.
4. Bind final results to the candidate digest and qualification ledger, with
   negative and failure cases, before marking the roadmap gate complete.
