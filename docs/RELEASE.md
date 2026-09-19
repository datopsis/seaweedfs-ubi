# Release admission and image signing

No SeaweedFS UBI image has been released. The current
[`release.yml`](../.github/workflows/release.yml) is an admission-only workflow:
it validates a pushed release tag and then **fails deliberately**. It has no
registry-write or OIDC permission and cannot publish or sign an image. Do not
create a release tag to test it; tags are immutable under [`VERSION.md`](VERSION.md).

## What is implemented

The tag job fetches all tags and the current `main` tip, then requires an
annotated tag on both the checked-out commit and that exact tip. It applies the
UTC date, repository-wide daily sequence, artifact-lock version, and
digest-pinned UBI-major checks in `scripts/lib/validate_release_tag.py`.
`tests/test_release_admission.py` covers positive admission and negative ref,
date, and signing-context cases. This is source/ref validation only; it is not
candidate qualification or proof that branch protection was enforced.

`scripts/sign-release-image.sh` is a future release-job primitive. It accepts
only `ghcr.io/datopsis/seaweedfs-ubi@sha256:<64 lowercase hex digits>`, checks
the exact repository, tag ref, release workflow identity, and availability of
GitHub OIDC, then runs keyless `cosign sign` and verifies the signature against
the expected workflow certificate identity and GitHub OIDC issuer. It never
signs a mutable tag. The caller must install a pinned Cosign version and retain
the verification output as release evidence. The script's context checks are
defense in depth, **not** release authorization: only a job downstream of all
candidate gates may receive `id-token: write` and registry-write permission.
See [Sigstore's container signing guide](https://docs.sigstore.dev/cosign/signing/signing_with_containers/)
and [verification guide](https://docs.sigstore.dev/cosign/verifying/verify/).

## Required publication sequence (not yet implemented)

1. Build candidate image indexes through the reviewed, network-restricted
   assembly path. Record the exact index and architecture digests, source
   commit, artifact-lock digest, base digests, build inputs, tool versions, and
   provenance. Candidate location and retention must allow testing *that same
   digest* without presenting it as a published release.
2. Run fixed High/Critical Trivy **and** Grype gates, retain full inventories
   and release-digest-bound SPDX SBOMs, and resolve or formally disposition
   findings under the existing policy. The current development-image scans
   are report-only and have known fixed High findings; they cannot be reused
   as a passing release gate. The paired-inventory evaluator in
   `tests/lib/vulnerability_gate.py` is available but is not yet connected to
   candidate admission.
3. Run both-architecture, real-host, security, and topology qualification
   against the candidate digest. Complete requirements/control mapping,
   independent cyber review, and the SCAP evidence boundary. A single-container
   test cannot qualify replication or multi-node behavior.
4. Rehearse promotion and clean-environment verification. Obtain explicit
   release approval that names the candidate index digest and evidence bundle.
   Revalidate the protected main tip, immutable tag, and candidate binding
   immediately before promotion. No release credential is available to a job
   before these checks succeed.
5. Promote the **same qualified index digest** to an immutable GHCR release
   tag, without rebuilding it. Attach digest-bound provenance and SBOM
   attestations, sign the index digest keylessly from the approved workflow,
   verify the signature and attestations from a clean environment, then create
   the corresponding GitHub Release with evidence links and support scope.
   [GitHub's container attestation guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
   describes the permissions and subject-digest binding for that future job.

The candidate registry/storage design, evidence schema and retention,
vulnerability gate, human approval mechanism, and digest-preserving promotion
must be settled before enabling publication. An image rebuilt after testing
would have a different digest and require fresh qualification. Until then, the
intentional failure step in `release.yml` is a release safety control, not a
temporary waiver.
