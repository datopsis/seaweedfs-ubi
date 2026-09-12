# Repository badges

Badges are compact links to evidence, not security claims. The README uses only
badges maintained by GitHub, OpenSSF, Shields.io, or a factual static project
label. A badge must link to the page where a contributor can inspect the
underlying result.

## Current state

`README.md` carries **no badges today**, which is correct: there is no CI
workflow, no release, and no published evidence for a badge to link to. A badge
whose destination shows nothing is worse than no badge, because it implies a
result exists.

Badges are added as the evidence they link to becomes real, not in advance.

## Approved inventory

Each badge below is approved for use **once its evidence exists**. The enabling
work package is named; adding a badge before its package lands is a policy
violation, not an oversight.

| Badge | Evidence and destination | Enabled by | Maintenance |
| --- | --- | --- | --- |
| CI | Status of `.github/workflows/ci.yml` on `main`; links to its workflow runs. | Package 5 | GitHub updates it after each run. |
| CodeQL | Status of `.github/workflows/codeql.yml` on `main`; links to its workflow runs. | Package 5 | GitHub updates it after each run. |
| OpenSSF Scorecard | Public Scorecard result for this repository; links to the detailed viewer. | Package 5 | The scheduled workflow publishes results; the public cache may lag. |
| Latest release | Highest GitHub release; links to the releases page. | Package 8 | It reports no release until the first tag workflow succeeds. |
| License | Repository-detected license; links to `LICENSE`. | Available now | GitHub and Shields derive it from repository content. |
| UBI 9 | Factual base-family label; links to Red Hat's UBI documentation. | Package 3 | Update manually only if the runtime base family changes. |
| SPDX SBOM | Factual statement that CI produces SPDX JSON; links to `CI.md`. | Package 5 | Keep only while CI and releases produce the documented artifact. |

The CI and CodeQL badges are scoped to `branch=main`; a green badge therefore
describes the default branch, not an unmerged pull request. Scanner findings are
represented through CI rather than a separate "secure" badge, because a
vulnerability database and image contents both change over time.

## Prohibited badges

Do not add download counts, stars, "production ready", vulnerability-free,
compliance, coverage, or generic "passing" badges without stable
machine-verifiable evidence. Do not expose tokens through custom badge endpoints.
An OpenSSF score is a point-in-time measurement and must never be restated as
certification.

Four prohibitions are specific to this project, because each corresponds to a
claim a reader would plausibly expect and this project cannot support:

- **No "S3 compatible" or "S3 conformant" badge.** There is no conformance suite
  behind such a claim. S3 behavior is recorded per operation in
  [release qualification](QUALIFICATION.md), and the differences from the
  reference service are documented rather than badged away.
- **No "hardened", "rootless", "CIS", or "STIG" badge.** These describe an
  assessed boundary, not a repository. The runtime contract is stated in
  `README.md` and evidenced per release; a badge would compress a bounded
  assessment into an unbounded claim.
- **No "FIPS" badge** in any form, including "FIPS-ready" or "FIPS-capable".
- **No durability, availability, or uptime badge.** Those are properties of a
  deployed topology, not of an image.

## Source markup

The canonical badge markup lives at the top of `README.md`. When changing it:

1. use HTTPS for both the image and the destination;
2. link workflow badges to the workflow page, not to a single run;
3. keep repository coordinates explicit as `datopsis/seaweedfs-ubi`;
4. URL-encode static badge labels and values;
5. preview links while signed out so badges do not depend on private credentials;
   and
6. update this inventory in the same pull request.

## Troubleshooting

- A workflow badge can remain stale briefly because of CDN caching. Open the
  linked workflow before treating it as a current result.
- The release badge will show that no release exists until the tag workflow
  creates the first GitHub release.
- If the license badge is unknown, confirm that the root `LICENSE` remains
  recognizable as Apache-2.0.
- If the Scorecard badge is missing or stale, inspect the `OpenSSF Scorecard`
  workflow and its publishing step before editing the badge URL.

## References

- [GitHub workflow status badges](https://docs.github.com/en/actions/how-tos/monitor-workflows/add-a-status-badge)
- [OpenSSF Scorecard badge](https://github.com/ossf/scorecard-action#scorecard-badge)
- [Shields.io GitHub badges](https://shields.io/badges)
- [Red Hat Universal Base Images](https://developers.redhat.com/products/rhel/ubi)
