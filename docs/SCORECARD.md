# OpenSSF Scorecard follow-up

The first published OpenSSF Scorecard run evaluated `main` at `de94e11` on
2026-09-17 UTC and reported **6.3/10**. This is a point-in-time measure of
repository practices, not an image vulnerability result or a release gate.
The [workflow run](https://github.com/datopsis/seaweedfs-ubi/actions/runs/35171944225)
and [published result](https://api.securityscorecards.dev/projects/github.com/datopsis/seaweedfs-ubi)
are the evidence; published results may be superseded by later runs. Scorecard
SARIF is retained by the workflow for five days. The ruleset below was added
*after* this scan, so the 6.3 score does not measure its effect.

A [second run](https://github.com/datopsis/seaweedfs-ubi/actions/runs/35175188541)
on merged `main` at `fc87d5e` on 2026-09-17 UTC reported **6.4/10**.
Branch Protection rose from 3 to 4 and CI Tests from 1 to 2, with 6 of 27
historical merged pull requests checked by CI. SAST remained 7. These are
observed changes, not proof that the required-checks ruleset caused every
score difference; coverage denominators also changed. Continue to assess
future runs against the exact evaluated commit and check details.

The initial run exposed these follow-ups:

| Check | Initial score | Finding and disposition |
| --- | ---: | --- |
| CI tests | 1 | Only 5 of 26 historical merged pull requests had CI. The [required-checks ruleset](https://github.com/datopsis/seaweedfs-ubi/rules/23575291) now requires `validation` and `native image` from GitHub Actions, with up-to-date branches. Prior merges cannot be backfilled; monitor coverage of future pull requests. |
| SAST | 7 | CodeQL was present, but only 2 of 26 historical commits had SAST. The same ruleset now requires the `codeql` aggregate check. Historical coverage cannot be backfilled; monitor new commits. |
| Branch protection | 3 | The scan reported no required checks, no required approvers or CODEOWNERS, and no stale-review dismissal or last-push approval. Required checks are now enforced by a separate ruleset; the original pull-request and history-protection ruleset is unchanged. Scorecard may have incomplete visibility into branch protection. Reassess after another scan. Human review and ownership settings require a governance decision before changing the current automated merge policy. |
| Code review | 0 | No approved changesets among 27 examined. Decide whether and how to require independent human approval, including reviewer availability and a CODEOWNERS policy. Do not manufacture approvals or silently block the approved merge workflow. |
| Fuzzing | 0 | No fuzzer integration. Add bounded, reproducible fuzzing of untrusted artifact-lock, admission, and configuration parsing, with a maintained corpus and CI evidence. Unit tests are not fuzzing evidence. |
| Best Practices | 0 | No OpenSSF Best Practices badge. Assess its criteria and apply only when the required evidence exists; do not add an unearned badge. |
| Maintained | 0 | The repository was less than 90 days old at the scan. This is time-bound and cannot be repaired by a code change. Continue normal maintenance and reassess when eligible. |

The second run also reported **Contributors 0** because it found contributors
from zero distinct organizations. This is a participation signal, not a reason
to manufacture contributors or grant repository access. Reassess as the project
gains genuine maintainers and external contributions. **Packaging -1** means
Scorecard did not detect a supported package workflow; do not equate that
heuristic with the container build evidence described in `CI.md`. **Signed
Releases -1** reflects that no release exists yet. Package 5 already requires
digest-bound signing before a release, and no source-only tag or release should
be created to improve this score.

The separate CodeQL `py/insecure-protocol` alert found that the gRPC mTLS
test client permitted TLS 1.0/1.1 negotiation. That client now sets a TLS 1.2
minimum. Its hostname-verification exception remains narrowly scoped to
testing client-certificate authentication; the S3 TLS suite separately checks
server identity with a SAN-bearing certificate. A successful CodeQL workflow
alone does not imply every code-scanning finding is resolved; verify the alert
state after analysis of the merged fix. The
[post-merge CodeQL run](https://github.com/datopsis/seaweedfs-ubi/actions/runs/35175188578)
passed and [the alert](https://github.com/datopsis/seaweedfs-ubi/security/code-scanning/1)
was marked fixed on 2026-09-17 UTC.

Each further reassessment should record its run ID, evaluated commit, score,
check-level changes, and any findings that remain. Do not infer a score change
solely from the ruleset configuration or treat an age-based or historical
metric as a current control failure.
