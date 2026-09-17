# Continuous integration

CI runs deterministic repository validation and a native image matrix on AMD64
and ARM64. A green matrix demonstrates the listed tests on GitHub-hosted Ubuntu
runners for the reviewed development image. It is not release-image, RHEL,
OpenShift, multi-host, vulnerability-gate, release-SBOM, provenance, or signing
evidence.

## Triggers and authority

`.github/workflows/ci.yml` runs for pull requests, pushes to `main`, a weekly
schedule, and manual dispatch. Its default token permission is read-only
repository content. Jobs have explicit timeouts, use immutable Action commit
SHAs, disable persisted checkout credentials, and cancel obsolete runs for the
same workflow and ref.

The stable `validation` and `native image` aggregate jobs each depend on every
job in their scope. Branch protection can require those two names without
depending on matrix job names that may change later. A failed or unavailable
architecture makes the `native image` aggregate fail; no architecture is
silently skipped.

An active ruleset on the default branch requires `validation`, `native image`,
`codeql`, and `dependency review` from the GitHub Actions app, with the pull
request branch up to date before merge. The existing pull-request and
history-protection ruleset remains in place. These required checks apply to
future merges; they cannot retroactively validate earlier commits or pull
requests.

## Current automated checks

The repository-validation job:

- installs pre-commit and its dependencies from the hash-locked requirements
  file using binary wheels only;
- runs every pre-commit check, including shellcheck, actionlint, Containerfile
  linting, private-key detection, and artifact-lock validation;
- runs deterministic Python unit tests, including negative backup-archive cases;
- runs `tests/lock.sh`, which proves realistic inconsistent artifact locks are
  refused; and
- audits workflow security with zizmor.

The configuration-security job scans repository configuration with Trivy and
fails on High or Critical findings. It is deliberately separate from future
image vulnerability scanning: those results describe different subjects and
must remain independently reviewable.

## Native image matrix

The native matrix uses `ubuntu-24.04` for AMD64 and `ubuntu-24.04-arm` for
ARM64. Each job checks `uname -m` before acquisition, and checks the assembled
image architecture before running it. The jobs do not install emulators.

For each architecture, CI validates the reviewed lock, verifies the signed
upstream image index and architecture manifest, extracts the binary by digest,
and runs negative admission and assembly tests. The assembly tests verify that
a missing or altered bundle, changed lock, or unavailable pinned base prevents
a build invocation. A runtime shim also checks the `--pull=never` and
`--network=none` command arguments; it does not substitute for the real build.
CI pulls digest-pinned UBI bases in a separate networked step, then invokes
`scripts/build-image.sh`, which re-verifies the bundle, forbids pulling, and
disables Podman's build network. The development image is not published by
these jobs.

Every native job then runs the restricted-runtime smoke, separated-role cluster,
authenticated S3 and multipart, S3 TLS, inter-component security, observability,
state-survival, one-host replication, bounded resource-exhaustion, and cold
backup/restore suites. These retain their individual scope limits: the
one-host replication test is not multi-node durability evidence, and a bounded
`tmpfs` is not a physical-disk failure test.

After assembly, each native job saves its development image as a local OCI
archive and scans that archive with pinned Syft. It validates the SPDX 2.3
document for a SeaweedFS Go module and Go dependency inventory, then retains
the per-architecture SPDX JSON as a CI artifact for 14 days. The OCI archive
itself is temporary and is not published. These are image-inventory artifacts
for the tested development builds; they are not vulnerability scan results,
release-image SBOMs, provenance, or signatures.

Each native job also scans that same local OCI archive with pinned Grype and
retains the complete JSON vulnerability inventory for 14 days. This first
inventory run does not suppress unfixed findings or fail on vulnerable packages;
its purpose is to expose and triage the actual image findings before enforcing
the planned fixed High/Critical gate. A green CI result therefore means the
scan ran and produced a parseable report, not that the image is vulnerability
free. The reports describe development images only, not release candidates.

The common listener parser is Python-based so results do not depend on the
runner's default `awk` implementing GNU-only `strtonum`.

## Code scanning

`.github/workflows/codeql.yml` analyzes GitHub Actions workflows and the
repository's Python tooling in separate jobs using the `security-extended`
query suite. It runs for pull requests, pushes to `main`, weekly schedules,
and manual dispatch. Checkout does not persist credentials; the CodeQL jobs
have read-only repository and Actions access, with `security-events: write`
as their sole write permission for code-scanning publication. A stable
`codeql` aggregate fails if either language analysis fails or is skipped.

Results are published to GitHub code scanning, not committed to the repository.
A successful workflow means both analyses ran and uploaded; it does not mean
the code has no findings, and it is not an image vulnerability scan.

## Repository security posture

`.github/workflows/dependency-review.yml` runs only for pull requests with a
read-only token. It compares dependencies recognized by GitHub's dependency
graph between the base and proposed revisions, and fails on newly introduced
High or Critical advisories in runtime, development, or unknown scopes. It
does not waive lower-severity findings, establish a license policy, inspect
the prebuilt `weed` binary's Go dependency inventory, or scan the assembled
image. GitHub's dependency graph was enabled after the first PR attempt
reported it unavailable; the [rerun](https://github.com/datopsis/seaweedfs-ubi/actions/runs/35176565149)
passed. The stable `dependency review` job is now required by the default-branch
ruleset. An empty or incomplete graph is not evidence that the image has no
vulnerable components; SBOM and image scanners remain separate work.

`.github/workflows/scorecard.yml` runs OpenSSF Scorecard on pushes to `main`,
weekly schedules, branch-protection-rule changes, and manual dispatch. It uses
read-only workflow defaults and narrows the analysis job to repository read,
OIDC publication, and code-scanning upload permissions. It publishes its
results to the OpenSSF service and uploads SARIF to GitHub code scanning. The
SARIF is also retained as a workflow artifact for five days. Scorecard does not
run on pull requests because published Scorecard results have stricter workflow
requirements; the normal CI and CodeQL workflows still validate the PR.

Scorecard evaluates repository practices, not the built image. Its code-scanning
category remains distinct from CodeQL and future image vulnerability results.
The default GitHub token may not expose every classic branch-protection setting
to Scorecard, so a partial branch-protection result must not be treated as proof
that no protection exists.
The first published Scorecard run and its findings are tracked in
[`SCORECARD.md`](SCORECARD.md); score changes are assessed from later runs,
not inferred from a ruleset edit.

## Local equivalent

```console
python -m pip install --require-hashes --only-binary=:all: \
  --requirement .github/requirements/pre-commit.txt
pre-commit run --all-files --show-diff-on-failure
python -m unittest discover --start-directory tests --pattern 'test_*.py' --verbose
bash tests/lock.sh
```

After acquiring an admitted binary with `scripts/fetch-artifacts.sh`, run
`bash tests/assembly.sh` to exercise the offline assembly refusals. This test
uses a runtime shim and does not build an image; the native CI jobs also run
the real Podman assembly.

Trivy and zizmor are pinned CI Actions in this increment; local invocations are
not documented as equivalent until their installation and version pins have a
repository-owned command.

## Work still required

CI still needs release-image SBOM generation, Trivy and Grype image gates,
release evidence retention,
provenance, signing, and release automation. The lock's publisher-signature
negative cases remain a separate networked suite; acquisition itself verifies
the index and architecture manifest positively in each native job. A skipped or
unimplemented job is never evidence for that scope.
