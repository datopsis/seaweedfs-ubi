# Hermetic build

This document describes the assembly contract: what the build is allowed to
reach, why acquisition and assembly are separate steps, and what the property is
worth. It is deliberately explicit about what hermetic assembly does **not**
defend against, because the phrase is often used to imply more than it delivers.

## Status

Partly implemented. Acquisition exists and is enforced; assembly does not exist
yet, because there is no Containerfile until work package 3.

| Property | State |
| --- | --- |
| Acquisition is a separate step producing a reviewable bundle | Implemented, `scripts/fetch-artifacts.sh` |
| Nothing is admitted without a signature and every recorded measurement | Implemented, and observed refusing |
| Nothing is resolved from a tag at any point in a build | Implemented; the gate consumes digests only |
| Assembly consumes only the bundle and digest-pinned base images | Owed by package 3 |
| Assembly succeeds with the build network disabled | Owed by package 3 |
| The bundle is verified again at assembly time | Owed by package 3 |

Nothing below should be read as a claim about the assembled image until the
right-hand column says so.

## Why acquisition and assembly are separate

They have different trust properties, and collapsing them hides that.

**Acquisition** reaches the network. It talks to a registry, a transparency log,
and a certificate authority. It is the step that decides whether bytes are
admitted at all, and it is the step an attacker would most like to influence.

**Assembly** should reach nothing. It takes already-verified bytes and a
digest-pinned base image and produces a container. If assembly can fetch, then a
build can differ from the reviewed inputs without any reviewed change, and the
lock stops meaning anything.

Separating them also makes a controlled-network deployment ordinary rather than
special: acquisition runs on a connected host, the bundle is transferred, and
assembly runs disconnected. The same two commands work in both cases, so the
disconnected path is not a second, less-tested procedure.

## What the build may reach

Once package 3 lands, assembly may read exactly two things:

1. the verified bundle produced by acquisition, entering the build as a named
   build context so nothing else in the working tree can reach the image; and
2. Red Hat UBI base images, referenced by digest and pulled in a separate step
   before the network is closed.

It may not resolve a tag, contact a package repository, fetch a script, or read
credentials. The final image has no package manager, so it cannot acquire
anything at runtime either.

## What this property defends against

- **A build that quietly differs from the reviewed inputs.** If assembly cannot
  fetch, the image contains what the lock says and nothing else.
- **A moved or re-pointed tag.** Nothing resolves a tag at build time, so
  repointing `4.46_large_disk` at different bytes changes nothing until a human
  updates the lock and a reviewer reads the diff.
- **A compromised mirror or a hostile network during assembly.** There is no
  traffic to intercept.
- **Accidental drift.** A build on a developer's machine and a build in CI
  consume the same bundle, so "works here" and "works in CI" cannot diverge
  because of what got downloaded.

## What this property does not defend against

This list matters more than the one above, because these are the gaps a reader
might otherwise assume are covered.

- **It does not make upstream trustworthy.** A hermetic build of a malicious
  input produces a reliably malicious image. Verification decides *whether* bytes
  are good; hermeticity only guarantees *which* bytes were used.
- **It does not detect a compromised upstream signing identity.** If upstream's
  workflow identity were misused to sign a bad image, the gate would verify it
  correctly and admit it. The signature proves who built it, not that it is safe.
- **It does not protect the acquisition host.** That host reaches the network by
  design. Its compromise is a real risk and is a deployment concern, not
  something assembly can address.
- **It does not validate the contents of the UBI base image.** A digest pins
  *which* base is used; the vulnerability scanning and SBOM work in package 5 is
  what says anything about what is in it.
- **It is not reproducibility.** Two hermetic builds of the same inputs are not
  guaranteed to produce identical image digests; timestamps, layer ordering, and
  build tooling all intervene. Bit-for-bit reproducibility is a separate property
  that this project does not currently claim.
- **It does not make the image smaller, safer to run, or correctly configured.**
  Those are the runtime contract, not the build.

## Verification at both ends

Acquisition verifies before writing the bundle. Assembly must verify again
before using it, because the two steps can be separated by a transfer, a
different host, or an interval of time, and a bundle is an ordinary directory
that anything with write access can alter.

Re-verification is cheap: the same offline checks in `scripts/lib/verify.py`,
against the same reviewed lock. It is owed by package 3 and is listed there.

## Docker and Podman differ here

Podman supports disabling the network for a build directly. Docker's BuildKit
backend has no straightforward per-build equivalent, so proving the property
under Docker needs a different mechanism — a network-isolated builder instance,
or running assembly inside an already-isolated container.

Until that is settled and tested, the hermetic-assembly claim will be scoped to
the Podman path, and the Docker path will be described as compatible but not
carrying the same evidence. Deciding and testing that mechanism is part of
package 3, and the resulting distinction belongs in the support matrix rather
than in a footnote.

## Related documents

- [External artifact acquisition](ARTIFACT-ACQUISITION.md) — what is fetched,
  what is verified, and the limits of that verification.
- [Build variants](BUILD-VARIANTS.md) — which upstream build is admitted.
- [The work plan](README.md) — the packages that owe the unimplemented rows
  above.
