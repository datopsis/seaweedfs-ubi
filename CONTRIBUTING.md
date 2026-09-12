# Contributing

Contributions are welcome through GitHub pull requests. Security reports must
use the private process in [SECURITY.md](SECURITY.md), not a public issue.

## Before changing the repository

1. Read [the agent and contributor guidance](CLAUDE.md) and the
   [work plan](docs/README.md).
2. Keep runtime additions minimal and explain why each package, listener,
   writable path, capability, or network permission is required.
3. Pin base images and external inputs. Every upstream artifact change is a
   reviewed edit to the lock under `artifacts/`, never a build-time resolution.
   Never commit credentials, access keys, JWT signing keys, private CAs,
   internal repository locations, downloaded release archives, or SeaweedFS
   volume or filer state.
4. Add or update automated tests, operational guidance, security
   considerations, and support classification together when behavior changes.
5. Record notable completed work under `Unreleased` in `CHANGELOG.md` and remove
   completed work from `docs/README.md`; the work plan remains forward looking.

Do not weaken the non-root default, digest verification, the supported-role
allowlist, the fail-closed S3 authentication guard, the explicit-data-directory
requirement, vulnerability gates, read-only-root compatibility, the
dropped-capability and no-new-privileges baseline, or the signed-release process
merely to make a test pass.

## Verifying an upstream claim

This repository asserts specific upstream SeaweedFS behavior, and each assertion
is a read of one release. If a change depends on one of them, verify it against
the version in question and say so in the pull request. The assertions that need
this treatment are listed under **standing obligations** in
[the work plan](docs/README.md#standing-obligations-at-every-upstream-version-bump).

Upstream releases often and makes no compatibility promise, so a claim that was
true at `4.46` is not automatically true at the next increment.

## Validate a change

Install and run the pinned repository checks:

```console
python -m pip install --require-hashes --only-binary=:all: \
  --requirement .github/requirements/pre-commit.txt
pre-commit install --install-hooks
pre-commit run --all-files --show-diff-on-failure
```

Build and smoke commands will be added to `README.md` when the image lands in
work package 3. A local success does not replace native architecture CI or
release-candidate platform qualification, and a single-container result is not
evidence for a separated-role or replicated topology.

## Pull requests and commits

Develop on a feature branch taken from current `main`; `main` is protected and
accepts changes only through a pull request. Keep changes small and dependency
ordered — prefer one work-plan increment per pull request. Complete the pull
request template, identify image, runtime, security, documentation, and release
impact, and review logs and retained evidence rather than relying only on green
checkmarks.

Use concise Conventional Commit subjects such as `feat:`, `fix:`, `docs:`,
`test:`, `ci:`, `build:`, `refactor:`, or `chore:`. Do not add AI, assistant,
tool-attribution, or `Co-Authored-By` trailers to commits; a pinned
`commit-msg` hook rejects them.
