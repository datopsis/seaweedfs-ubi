# External artifact acquisition

This document records where the upstream SeaweedFS binary comes from, what is
verified before it is admitted into an image, and — just as importantly — what
that verification does **not** prove.

Every statement below was read from upstream source, workflows, or release
metadata at tag `4.53`. Each is a read of one release and must be re-verified at
every version bump.

## What upstream actually publishes

Upstream produces the same release through two independent pipelines, and they do
not have the same provenance.

| | **Release tarballs** | **Container images** |
| --- | --- | --- |
| Built by | `.github/workflows/binaries_release*.yml` | `.github/workflows/container_release_unified.yml` |
| Published to | GitHub Releases | `ghcr.io/chrislusf/seaweedfs` and Docker Hub `chrislusf/seaweedfs` |
| Integrity metadata | a `.md5` sidecar per asset | none of its own |
| Signature | **none** | **keyless cosign, verified in-pipeline** |
| Attestation | none | BuildKit provenance/SBOM plus digest-bound provenance and per-platform SBOM attestations |
| Source ref | the release tag | `BRANCH=${{ github.sha }}`, the exact released commit |
| `large_disk` variant | yes | yes |
| Contents | `weed` only | `weed`, plus Rust `weed-volume`, `weed-worker`, and `weed-vector` |

### The tarball provenance is effectively nil

Each asset has a `.md5` companion and nothing else. MD5 is not collision
resistant, and a sidecar served from the same origin as the artifact it describes
is not an independent check — an attacker who can replace one can replace both. It
is worth recording as an upstream-published value; it is worth nothing as an
integrity control.

### The container signature is real, and it is bound to the org

The image is signed with keyless cosign and then verified inside the same
workflow against:

- issuer `https://token.actions.githubusercontent.com`
- identity `https://github.com/seaweedfs/seaweedfs/.github/workflows/container_release_unified.yml@<ref>`

That identity is an **organization-repository workflow identity**. It cannot be
produced by someone who merely holds registry credentials.

### Why the namespace makes verification mandatory rather than optional

The images are published under `chrislusf`, a **personal** namespace, not the
`seaweedfs` organization namespace. It is nonetheless the official channel: the
publishing workflow lives in the official repository, and the project README
directs users to `chrislusf/seaweedfs`.

But push access to that namespace rests on one individual's account plus the
repository secrets `GHCR_USERNAME` and `DOCKER_USERNAME`. Anyone holding those
could push an image into the official-looking namespace without the official
workflow ever running.

This produces a conclusion worth stating plainly, because it inverts the usual
intuition:

> Pulling this image **by tag, unverified, is worse** than downloading the
> tarball — it is an unverified artifact from a personal namespace. Pulling it
> **by digest with `cosign verify` enforced against that exact identity and
> issuer** is meaningfully **better** than the tarball, because the tarball
> carries no publisher signal at all.

The signature is precisely the control that defends against the namespace being
personal. So on the image path, verification is not a hardening extra; it is the
entire reason the path is worth taking.

## What the binary actually is

From the upstream release Dockerfile, the Go binary is built as:

```console
CGO_ENABLED=0 go build -tags "$TAGS" \
  -ldflags "-extldflags -static -X ...version.COMMIT=$(git rev-parse --short HEAD)"
```

Three consequences matter to this project:

1. **It is statically linked and CGO-free.** There is no glibc version
   requirement, which is why it runs on UBI 9 Micro without rebuilding. This is
   measured per release rather than assumed.
2. **It embeds the short commit hash**, so `weed version` is an independent
   behavioral check that the binary came from the expected commit — not just the
   expected digest.
3. **`$TAGS` is the variant.** `5BytesOffset` for the admitted `large_disk`
   build. See [build variants](BUILD-VARIANTS.md).

There is a fourth difference between the two pipelines, found while measuring the
assembled image rather than while reading the workflows. The **tarball** build
passes `-s -w` and is stripped; the **container** build does not. The admitted
binary retains symbol-table and DWARF sections that the published tarball
does not. The earlier 62 MiB estimate described 4.46, not this binary.

That is a real cost of this acquisition path: Path A would produce a smaller
image with weaker provenance. The trade is recorded and taken knowingly, and the
reasoning for not stripping afterwards is in
[architecture](ARCHITECTURE.md#why-the-binary-is-not-stripped).

### Only `weed` is needed

The container image also carries three Rust binaries, `weed-volume`,
`weed-worker`, and `weed-vector`. None is required:

- upstream's own entrypoint dispatches the `volume` role to `weed volume`, the Go
  implementation; `weed-volume` is reachable only under a *separate* role name, so
  the Rust volume server is an opt-in alternative rather than the default;
- `weed-vector` implements the unqualified S3 Vectors backend;
- `weed-worker` serves Lance table buckets, which are outside this project's
  boundary and disabled by this image.

So the single Go `weed` binary covers every supported role — `master`, `volume`,
`filer`, `s3`, and the standalone profile. Whichever acquisition path is chosen,
this project admits `weed` and nothing else.

### Upstream's image cannot be used as a base, and its entrypoint cannot be reused

Upstream's image is Alpine-based and its entrypoint starts as root, runs
`chown -R seaweed:seaweed /data`, then drops privileges with `su-exec`. That is a
privilege transition during startup, which
[this project's contract](../CLAUDE.md) forbids: our roles start non-root and
never transition. The image is therefore a **source of a verified binary**, never
a base layer and never a behavioral model.

## The acquisition path

**Path B is the decided path**, recorded in
[decisions taken](README.md#decisions-taken) and implemented by
`scripts/fetch-artifacts.sh`. Path A is retained below as a documented fallback,
and Path C remains open as a later step rather than a foreclosed one.

Three paths were genuinely available. All three admit only `weed`, and all three
record digests in a reviewed lock; they differ in what the lock can *claim*.

### Path A — the release tarball

Fetch `linux_<arch>_large_disk.tar.gz`, verify size and SHA-256 against the lock,
extract, verify the binary's SHA-256, measure linkage.

- Simplest, no new tooling, no registry dependency.
- Ships the artifact upstream officially publishes as *the release*.
- **Proves reviewed bytes only.** No publisher identity, ever.

### Path B — the cosign-verified container image *(chosen, implemented)*

Resolve the `large_disk` tag to a digest, `cosign verify` that digest against the
exact issuer and identity above, extract `/usr/bin/weed` from the verified image,
verify its SHA-256 against the lock, confirm `weed version` reports the expected
commit, measure linkage.

- **Adds cryptographic publisher verification**, which Path A can never have.
- Built from the exact released commit, pinned by SHA rather than a mutable tag.
- Costs: `cosign` becomes an acquisition dependency; a registry pull joins the
  acquisition step; and the admitted binary is *not* the artifact published as the
  release tarball, which must be stated wherever the release is described.

### Path C — build from the upstream source

Clone the official organization repository at the exact release commit and run the
single CGO-free `go build` above in a pinned toolchain.

- **Strongest provenance**: source from the organization repository at an
  immutable commit, compiled in a build this project controls.
- Feasible in a way it would not be for a complex build — one command, no CGO.
- Costs: this project owns the Go toolchain, its updates, and its
  vulnerabilities; the shipped binary is no longer any artifact upstream
  published, so upstream's (already minimal) support basis no longer applies to
  it; and it materially changes what this project *is*, from a packager of
  upstream releases to a builder of them.

Path B was chosen: it is the largest available provenance improvement that does
not change the nature of the project. Path A is retained and documented as a
fallback for an environment where pulling and verifying an image is impractical.

## Verified evidence for the current lock

The 4.53 `large_disk` lock is a proposal awaiting owner review. Its index
`sha256:c272ca3b913a8d9f8f843d42553874f70d41ae0611a1bf8e28d80a7da72d7d51` and both architecture manifests verified
with Cosign v2.6.1 against the recorded workflow identity and GitHub issuer.
The certificate SHA and GitHub tag API independently agree on
`4ab66fb76da83700739f5839e62fcaf15fb7d02a`. The Rekor log index is
`3759071801`.

`scripts/update-lock.py` supplied resolution, signature/certificate checks,
ELF measurement, and lock generation. Podman is blocked locally by the sandbox's
user-namespace restriction. A temporary acquisition adapter used Skopeo 1.9.3
`copy --preserve-digests` by signed manifest digest, checked the manifest and
layer SHA-256 values, and extracted only `/usr/bin/weed`. It used authenticated
`gh api` for the GitHub tag query after the unauthenticated API was rate-limited.
This changes the extraction transport, not the verification policy. Native CI
independently repeated ordinary Podman acquisition on each architecture in
run 42550436459.

Both binaries have no ELF interpreter or dynamic segment, no needed libraries,
and no glibc requirement. Go build information reports Go 1.26.10,
`CGO_ENABLED=0`, and `-tags=5BytesOffset` on both. The native ARM64 execution
reports `version 8000GB 4.53 4ab66fb76 linux arm64`. Native AMD64 CI
[run 42550436459](https://github.com/datopsis/seaweedfs-ubi/actions/runs/42550436459)
executed the digest-verified binary and reports
`version 8000GB 4.53 4ab66fb76 linux amd64`; that measurement is now recorded
in the lock. Neither execution used emulation.

The 4.53 upstream workflow now enables BuildKit provenance and SBOM generation,
attests the merged index, and attaches per-platform SPDX attestations. This
repository verified the image signatures; it has **not** verified those new
attestation predicates. Tarballs still have only MD5 sidecars. The container
signature proves publisher identity, not freedom from defects. See the
[qualification record](UPGRADE-4.53.md).

## Running the gate

Acquisition needs a network; assembly does not, which is the whole point of
separating them.

```console
scripts/fetch-artifacts.sh            # every architecture in the lock
scripts/fetch-artifacts.sh amd64      # or a subset
```

It verifies the index signature, then per architecture verifies the manifest
signature, pulls **by digest**, copies the binary out of a created — never run —
container so a foreign architecture needs no emulation, and checks every recorded
measurement before admitting it to `.artifact-bundle/<arch>/weed`.

No tag is ever used to fetch. The tag in the lock is recorded for humans; a tag
can move and a digest cannot.

To see the gate refuse:

```console
tests/acquisition.sh                  # offline: every recorded measurement
tests/acquisition-signature.sh        # network: the publisher signature
```

The offline suite tampers with a byte while preserving the size, truncates,
appends, offers a binary as the wrong architecture, asks for an architecture the
lock does not record, substitutes a non-ELF file, points at a missing file, and
supplies an unparseable lock. The signature suite substitutes a different
workflow identity, a different git ref, a different OIDC issuer, and an unsigned
digest.

The different-workflow-identity case is the one worth understanding: it is
precisely what an attacker holding push access to the personal namespace, but not
the organization's workflow identity, would be unable to satisfy.

## What the lock records

The reviewed lock at
[`artifacts/seaweedfs.lock.json`](../artifacts/seaweedfs.lock.json) records:

- the upstream release tag, exactly as upstream published it, and the release
  commit SHA;
- the admitted asset variant, the build tags it corresponds to, and the runtime
  marker that confirms it;
- the acquisition path, the image repository, and the index digest;
- the cosign issuer and certificate identity that a signature must carry;
- the path of the binary inside the image;
- per architecture: the manifest digest, and the extracted binary's SHA-256,
  size, ELF machine, linkage, needed libraries, minimum glibc version, embedded
  commit, and version string where one has been captured;
- the evidence that the lock was verified, including the certificate's workflow
  repository, ref, and commit, the Rekor log index, and the notes recording what
  the evidence does and does not establish.

On the Path A fallback, the lock would instead record the archive URL and digest
and the upstream-published MD5 — the latter as an upstream value, never as
verification.

A reviewed change to that lock is the only way new bytes enter an image. Nothing
is resolved at build time.

## Verification must fail closed

The admission gate refuses, with a non-zero exit and a diagnostic, when any of
these holds: a size mismatch, a digest mismatch on the archive or image, a digest
mismatch on the extracted binary, a missing lock entry for the architecture, a
version or commit string that disagrees with the lock, a linkage measurement that
disagrees with the lock, an absent verification tool, or — on Path B — a cosign
verification failure for any reason including a missing signature.

Negative tests for each of those cases are a work package 2 deliverable. A gate
that has never been observed refusing is not known to refuse.

## Stated trust limitations

These must remain accurate, and must appear in release documentation rather than
only here.

1. **On Path A, digests prove reviewed bytes, not publisher identity.** Upstream
   publishes no signature for tarballs and no SHA-256 manifest.
2. **On Path B, the signature proves who built the image, not that the image is
   free of defects**, and the admitted binary is not the published release
   tarball.
3. **The upstream MD5 sidecar is never an integrity control** in either
   direction.
4. **Upstream fixes only its latest release**, so a locked older version cannot
   receive an upstream security fix. See [the support contract](SUPPORT.md).
5. **An upstream claim is not evidence.** Upstream's Dockerfile states that Go
   FIPS 140-3 mode is on by default; its build sets no `GOFIPS140`, and the Go
   default is off. This project must not repeat that claim, and work package 6
   owes the actual determination in `docs/FIPS.md`.

## References

- Release workflows:
  [`binaries_release*.yml`](https://github.com/seaweedfs/seaweedfs/tree/master/.github/workflows)
- Container release workflow and signing action:
  [`container_release_unified.yml`](https://github.com/seaweedfs/seaweedfs/blob/master/.github/workflows/container_release_unified.yml),
  [`.github/actions/sign-image`](https://github.com/seaweedfs/seaweedfs/tree/master/.github/actions/sign-image)
- Release image build:
  [`docker/Dockerfile.go_build`](https://github.com/seaweedfs/seaweedfs/blob/master/docker/Dockerfile.go_build)
- Upstream entrypoint role dispatch:
  [`docker/entrypoint.sh`](https://github.com/seaweedfs/seaweedfs/blob/master/docker/entrypoint.sh)
