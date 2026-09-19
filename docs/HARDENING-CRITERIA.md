# Provisional IMG criterion inventory

This is the first SeaweedFS crosswalk to the **34 required** IMG criteria in
the changing [`container-hardening` standard](https://github.com/datopsis/container-hardening/blob/main/docs/standard/criteria.md).
It is a work inventory, not a passing score. No criterion is marked met here:
the shared revision is not yet approved or pinned, criterion-specific evidence
has not been emitted, and release-candidate assessment does not exist. A linked
development test can establish only its own assertion and scope.

“Requirement area” points to the existing L1 requirement tree. A final
component definition needs appropriate L2/L3 obligations and exact verification
pointers for *every* image-owned control, not merely these broad parent links.
The next-proof column is the most important uncovered or unverified part, not
an exhaustive recitation of the criterion.

While the shared repository changes, run this read-only drift check against a
local checkout before editing this inventory or the source/control worksheet:

```console
python scripts/lib/check_standard_draft.py ../container-hardening
```

It compares required IDs, control-origination counts, and the four examined
SRG source digests. A pass means only that these *draft worksheets* match that
checkout's structure; it does not pin or approve the standard, review rules,
or validate conformance.

| Criterion | Requirement area | Existing starting point | Next proof or decision before a claim |
| --- | --- | --- | --- |
| IMG-01 Base pinned by digest | `L1-SUP-001` | Reviewed UBI lock and offline build path | Compare every build-stage `FROM` and manifest-list digest with the candidate lock on both architectures. |
| IMG-02 Every input pinned and verified | `L1-SUP-001` | Signed upstream OCI acquisition and negative lock/bundle checks | Prove complete installed/input closure, including CA bundle and binary, on exact candidate; distinguish tarball byte record from publisher identity. |
| IMG-03 Hermetic assembly | `L1-SUP-001` | No-pull, network-disabled native build and negative assembly tests | Retain candidate build invocation and static no-fetch/no-installer check; verify no external layer cache. |
| IMG-04 Reviewed input refresh | `L1-SUP-001` | Lock updates require review | Add read-only scheduled drift detection and evidence that it cannot change locks or merge unreviewed. |
| IMG-05 No build secrets | `L1-SUP-001`, `L1-EVD-001` | Build uses reviewed inputs | Test build args, layers, history and labels for secret-shaped values on the candidate. |
| IMG-06 No package manager | `L1-RUN-001` | UBI Micro design and native smoke | Inventory every forbidden binary, repository file, and signing key in both candidate architectures. |
| IMG-07 Only functional contents | `L1-RUN-001` | Supported-role allowlist and minimized image | Compare actual features, modules, compilers and retrieval tools with a committed per-role declaration. |
| IMG-08 Embedded package inventory | `L1-SUP-001`, `L1-EVD-001` | External SPDX development inventory exists | Define inventory for UBI packages *and* the upstream Go binary, embed read-only inventory, compare it with reviewed lock and SBOM. |
| IMG-09 No privilege-raising files | `L1-RUN-001` | Rootless runtime tests | Scan full candidate filesystem for setuid/setgid and undeclared world-writable paths. |
| IMG-10 Immutable software/configuration | `L1-RUN-001` | Read-only-root runtime tests | Prove every role cannot alter executable/config paths and list only explicit writable mounts. |
| IMG-11 No root or privilege transition | `L1-RUN-001` | Entrypoint and native role tests | Record per-process UIDs for every supported role on each candidate architecture. |
| IMG-12 Arbitrary UID | `L1-RUN-001` | OpenShift-compatible ownership design | Qualify arbitrary UID with actual writable mounts and both architectures; separate local compatibility from OpenShift admission. |
| IMG-13 No capabilities/new privileges | `L1-RUN-001` | Restricted Podman invocation | Read back process `CapEff` and `NoNewPrivs`; retain platform-enforcement handoff. |
| IMG-14 Unprivileged ports | `L1-RUN-001`, `L1-OBS-001` | Listener parser and role tests | Assert exact effective listeners per role/configuration, including optional metrics and standalone. |
| IMG-15 Read-only root | `L1-RUN-001`, `L1-DAT-001` | Native read-only-root suites | Check all supported roles and documented writable volumes against exact candidate. |
| IMG-16 Secrets as read-only files | `L1-CFG-001`, `L1-INT-001` | Runtime-mounted S3 and TLS examples | Resolve the supported environment-key option against this criterion; reject missing, writable, world-readable, or leaked secrets without weakening S3 fail-closed behavior. |
| IMG-17 Operator trust material | `L1-INT-001` | Ephemeral TLS/mTLS fixture | Verify no embedded private trust or keys, and document CA/cert/JWT rotation and revocation. |
| IMG-18 Fail closed | `L1-CFG-001` | S3, data-dir, role, and unsafe-TLS guards | Qualify every opt-out and missing/invalid configuration per role; prove no silent insecure fallback. |
| IMG-19 Logs to streams without secrets | `L1-OBS-001` | JSON logs and selected secret-leak tests | Test wider upstream error paths, identity attribution, collector handling, and candidate logs. |
| IMG-20 Lifecycle declared | `L1-OBS-001`, `L1-DAT-001` | Composite readiness and shutdown tests | Decide role-aware health contract and signal/graceful-stop evidence; a single `mini` health result is not a four-role result. |
| IMG-21 Bill of materials | `L1-EVD-001`, `L1-REL-001` | Native development SPDX on both architectures | Produce per-child and index-bound candidate SBOMs with Go and OS closure and durable retention. |
| IMG-22 Signed provenance | `L1-REL-001` | Digest-only signing primitive | Publish and independently verify multi-architecture index signature and provenance for exact candidate. |
| IMG-23 Identifying labels | `L1-SUP-001`, `L1-REL-001` | Build labels and artifact lock | Verify labels against exact release/tag/commit/lock and both image configs. |
| IMG-24 Immutable tags | `L1-REL-001` | Deterministic tag admission | Enforce registry immutability and promote the *same* qualified digest; do not infer atomic protection from a pre-push tag check. |
| IMG-25 Vulnerability gate/remediation | `L1-EVD-001`, `L1-REL-001` | Full Trivy/Grype inventories and fail-closed gate primitive | Block fixed High/Critical findings on exact candidate children; resolve known fixed Go findings and approve response timelines. |
| IMG-26 Expiring exceptions | `L1-EVD-001` | Qualification ledger schema | Establish reviewed, exact-digest exception process; do not create a blanket exception for known fixed findings. |
| IMG-27 No remote administration | `L1-RUN-001`, `L1-OBS-001` | Role allowlist and measured listeners | Inspect binary/entrypoint and enabled master/filer endpoints per role for administrative surfaces; distinguish unsupported Admin UI from management APIs. |
| IMG-28 Malware scan | `L1-EVD-001` | No malware gate yet | Add pinned full-file candidate scan with database provenance, false-positive process, and release gate. |
| IMG-29 Current base | `L1-SUP-001`, `L1-REL-001` | Digest-pinned UBI base | Record publisher-current digest and age; block candidate if the standard's limit is exceeded. |
| IMG-30 Declared behavior | `L1-RUN-001`, `L1-OBS-001` | Role/listener architecture and measured tests | Publish machine-readable per-role processes, listeners, paths, outbound calls, and standalone/separated topology variants. |
| IMG-31 Restricted-v2/PSS | `L1-RUN-001` | Native Ubuntu Podman restrictions | Exercise actual Kubernetes Restricted PSS and OpenShift restricted-v2, if in the selected support boundary; record environment and admission policy. |
| IMG-32 Restricted-v3 user namespace | `L1-RUN-001` | Arbitrary-UID design | Exercise actual OpenShift restricted-v3/user-namespace profile and both architectures as applicable; do not substitute a Podman flag test. |
| IMG-33 Protected source | `L1-REL-001` | Required branch checks and tag validation | Record review/ruleset evidence and verify release commit is the approved protected-main tip; avoid destructive test pushes. |
| IMG-34 Pre-build source/dependency scans | `L1-SUP-001`, `L1-EVD-001` | Secret detection, CodeQL, dependency review in separate workflows | Prove scans gate *before* build for the same commit; a later parallel green CodeQL run is not ordered pre-build evidence. |

The standard also has target criteria `IMG-T1`–`IMG-T4`; targets are not silently
promoted to required or counted as passed. Tailored SCAP remains a bounded,
report-only assessment until its rule selection and target are reviewed, and
neither it nor the crosswalk above constitutes STIG certification.
