# UBI fix-availability evaluation

Reference: [sail-ubi 861d92f](https://github.com/datopsis/sail-ubi/commit/861d92fb12e1a8b25c728da93129efdc770fd540).

## Repository identity and live queries

Evaluated on 2026-11-13 using fresh DNF metadata, an empty install root,
and native librpm comparisons. Repository files were extracted separately
from each architecture of the exact UBI Micro digest in `Containerfile`.
The base enables BaseOS, AppStream, and CodeReady Builder. All three loaded
successfully for each architecture; the host repository configuration was not used.

The input versions below are installed RPM EVRs from the actual Trivy baseline
inventory, used as version thresholds to exercise the query. They are not
claims that these packages have fixable vulnerabilities. Each successful
query found a matching binary/noarch version at or above the input threshold.

| Package | Baseline installed EVR | Published AMD64 EVR | Published ARM64 EVR |
| --- | --- | --- | --- |
| basesystem | 0:11-13.el9 | 0:11-13.el9 | 0:11-13.el9 |
| bash | 0:5.1.8-9.el9 | 0:5.1.8-9.el9 | 0:5.1.8-9.el9 |
| coreutils-single | 0:8.32-41.el9_8.1 | 0:8.32-43.el9 | 0:8.32-43.el9 |
| filesystem | 0:3.16-5.el9 | 0:3.16-5.el9 | 0:3.16-5.el9 |
| glibc | 0:2.34-283.el9_8 | 0:2.34-290.el9_9 | 0:2.34-290.el9_9 |
| glibc-common | 0:2.34-283.el9_8 | 0:2.34-290.el9_9 | 0:2.34-290.el9_9 |
| glibc-minimal-langpack | 0:2.34-283.el9_8 | 0:2.34-290.el9_9 | 0:2.34-290.el9_9 |
| libacl | 0:2.4.0-1.el9_8 | 0:2.4.0-2.el9 | 0:2.4.0-2.el9 |
| libattr | 0:2.6.0-1.el9_8 | 0:2.6.0-2.el9 | 0:2.6.0-2.el9 |
| libcap | 0:2.48-10.el9_8.1 | 0:2.48-10.el9_8.1 | 0:2.48-10.el9_8.1 |
| libgcc | 0:11.5.0-14.el9 | 0:11.5.0-17.el9_9 | 0:11.5.0-17.el9_9 |
| libselinux | 0:3.6-3.el9 | 0:3.6-4.el9 | 0:3.6-4.el9 |

24/24 complete-EVR live cases found an available version. An earlier probe
with the same 24 package records but without their release fields returned
24/24 parse errors, never a deferral. Unit tests additionally cover absent
candidates, unavailable fixed versions, query exceptions/timeouts, missing or
modified repositories, non-RPM types, wrong architectures, and multi-branch
fixes. Native librpm tests cover epoch, numeric release ordering, tilde/caret,
and `2.37.4-28.el9_9` versus `2.37.4-28.el9_9.1`.

## Baseline scanner evidence

[Main CI run 42962739858](https://github.com/datopsis/seaweedfs-ubi/actions/runs/42962739858)
at commit `fd9b0001ee86a432faf773d40ab6f528dbfdad67` supplied both architectures.
Both full Trivy and Grype JSON inventories were downloaded and parsed.
Counts below are HIGH/CRITICAL records; Grype retains the highest related
advisory severity, as the existing evaluator did. Scanner aliases are not
collapsed across tools. Prior native CI retained inventories but did not run
the evaluator; “blocking” means the evaluator would refuse these findings.

| Scanner | Architecture | Fixable-blocking | Deferred | Unfixed |
| --- | --- | ---: | ---: | ---: |
| Trivy | AMD64 | 1 | 0 | 0 |
| Trivy | ARM64 | 1 | 0 | 0 |
| Grype | AMD64 | 5 | 0 | 7 |
| Grype | ARM64 | 5 | 0 | 7 |

All fixable baseline HIGH/CRITICAL findings are non-RPM Go-module records.
No baseline RPM finding qualifies for deferral. Full lower-severity and
unfixed inventories remain in the CI artifacts.

## Verification boundary

Native PR CI is the authority for the final architecture builds and scans.
The PR description records the completed-run URLs and before/after counts;
scanner databases can change between runs. No RPM lock exists to refresh:
assembly inherits pinned base-image RPMs and installs none. This change does
not update the binary or base digests.

The issue tracker is tested for create/change/no-change/resolve/reopen and
missing-evidence refusal. Its live write path is intentionally not exercised
from a PR. It runs only on scheduled main-branch CI after merge.
Release admission and publication remain disabled.
