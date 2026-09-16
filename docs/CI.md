# Continuous integration

The initial CI foundation runs deterministic repository validation. It does not
yet build or qualify release images, and its green status must not be read as
native AMD64/ARM64 runtime, vulnerability, SBOM, provenance, signing, or release
evidence.

## Triggers and authority

`.github/workflows/ci.yml` runs for pull requests, pushes to `main`, a weekly
schedule, and manual dispatch. Its default token permission is read-only
repository content. Jobs have explicit timeouts, use immutable Action commit
SHAs, disable persisted checkout credentials, and cancel obsolete runs for the
same workflow and ref.

The stable `validation` aggregate job depends on every foundation job. Branch
protection can require that one name without depending on matrix or internal job
names that may change later.

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

## Local equivalent

```console
python -m pip install --require-hashes --only-binary=:all: \
  --requirement .github/requirements/pre-commit.txt
pre-commit run --all-files --show-diff-on-failure
python -m unittest discover --start-directory tests --pattern 'test_*.py' --verbose
bash tests/lock.sh
```

Trivy and zizmor are pinned CI Actions in this increment; local invocations are
not documented as equivalent until their installation and version pins have a
repository-owned command.

## Work still required

CI still needs native image jobs on AMD64 and ARM64, networked artifact
acquisition followed by offline assembly, the complete restricted-runtime suite,
CodeQL, Scorecard, dependency review, SBOM generation, Trivy and Grype image
gates, evidence retention, provenance, signing, and release automation. A skipped
architecture or unimplemented job is never evidence for that scope.
