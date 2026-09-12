# External artifact acquisition

This document records where the upstream SeaweedFS binary comes from, what is
verified before it is admitted into an image, and — just as importantly — what
that verification does **not** prove.

Every statement below was read from upstream source, workflows, or release
metadata at tag `4.46`. Each is a read of one release and must be re-verified at
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
| Attestation | none | none (`provenance: false` is set explicitly) |
| Source ref | the release tag | `BRANCH=${{ github.sha }}`, the exact released commit |
| `large_disk` variant | yes | yes |
| Contents | `weed` only | `weed`, plus Rust `weed-volume` and `weed-worker` |

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

### Only `weed` is needed

The container image also carries two Rust binaries, `weed-volume` and
`weed-worker`. Neither is required:

- upstream's own entrypoint dispatches the `volume` role to `weed volume`, the Go
  implementation; `weed-volume` is reachable only under a *separate* role name, so
  the Rust volume server is an opt-in alternative rather than the default;
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

> [!IMPORTANT]
> The choice below is **proposed, not settled**. It corresponds to the "how far to
> go on provenance" decision in
> [the work plan](README.md#decisions-that-need-a-human). The scripts are not
> written until it is confirmed, because the choice determines what they do.

Three paths are genuinely available. All three admit only `weed`, and all three
record digests in a reviewed lock; they differ in what the lock can *claim*.

### Path A — the release tarball

Fetch `linux_<arch>_large_disk.tar.gz`, verify size and SHA-256 against the lock,
extract, verify the binary's SHA-256, measure linkage.

- Simplest, no new tooling, no registry dependency.
- Ships the artifact upstream officially publishes as *the release*.
- **Proves reviewed bytes only.** No publisher identity, ever.

### Path B — the cosign-verified container image *(recommended)*

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

**The recommendation is Path B**, with Path A retained and documented as a
fallback for an environment where pulling and verifying an image is impractical.
Path B is the largest available provenance improvement that does not change the
nature of the project, and Path C remains open as a later step rather than a
foreclosed one.

## What the lock records

Regardless of path, the reviewed lock under `artifacts/` records per
architecture:

- the upstream release tag, exactly as upstream published it, and the release
  commit SHA;
- the admitted asset variant, and the build tags it corresponds to;
- the acquisition source: archive URL, or image reference **by digest**;
- the archive or image digest, and its byte size;
- the upstream-published MD5, recorded as an upstream value and never treated as
  verification;
- the extracted `weed` binary's SHA-256 and size;
- the embedded commit string the binary reports;
- the measured linkage: static or dynamic, the highest required glibc symbol
  version if any, needed shared libraries, and anything loaded at runtime rather
  than linked.

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
