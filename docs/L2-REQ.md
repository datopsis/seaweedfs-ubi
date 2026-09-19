# SeaweedFS UBI: Level 2 requirements

These decompose [`L1-REQ.md`](L1-REQ.md). They are an initial slice, not a
complete first-release specification. A parent link is structural, not evidence.
The IMG-specific obligations below replace the detached `requirements.md`
draft. Their `Criterion` fields are crosswalk pointers, not passing results;
L3 decomposition and scope-matching test links remain open where the generated
trace matrix says so.

### L2-SUP-001

**Parent.** L1-SUP-001

**Statement.** Acquisition SHALL verify the exact reviewed architecture binary,
signature identity where the selected source supplies one, digest, size,
version, variant, and linkage before admitting it to the build bundle.

**Verification.** Test, Analysis.

### L2-SUP-002

**Parent.** L1-SUP-001

**Statement.** Assembly SHALL consume only lock-selected inputs and SHALL not
pull images, resolve a version, or use a package network during build.

**Verification.** Test.

### L2-RUN-001

**Parent.** L1-RUN-001

**Statement.** Every supported role SHALL run with a nonzero UID, zero effective
capabilities, `no-new-privileges`, and only documented writable mounts.

**Verification.** Test.

### L2-RUN-002

**Parent.** L1-RUN-001

**Statement.** The entrypoint SHALL admit only the reviewed role set and SHALL
refuse embedded services that bypass a supported role's guard.

**Verification.** Test.

### L2-CFG-001

**Parent.** L1-CFG-001

**Statement.** The S3 and standalone entrypoints SHALL refuse a missing identity
source by default and SHALL reject a named identity file that does not exist.

**Verification.** Test.

### L2-CFG-002

**Parent.** L1-CFG-001

**Statement.** Stateful roles SHALL refuse an unset, relative, or temporary
data directory; disabling that guard SHALL require an explicit operator choice.

**Verification.** Test.

### L2-CFG-003

**Parent.** L1-CFG-001

**Statement.** Unqualified Iceberg, Lance, WebDAV, Admin UI, and embedded
services SHALL not start through the default role profile.

**Verification.** Test.

### L2-API-001

**Parent.** L1-API-001

**Statement.** Positive and negative S3 tests SHALL record the authenticated
client, operations, and configuration tested without inferring general API
conformance.

**Verification.** Test, Analysis.

### L2-INT-001

**Parent.** L1-INT-001

**Statement.** Separated-role tests SHALL reject an untrusted gRPC peer and a
direct volume write lacking a valid JWT, and SHALL demonstrate that direct
filer and volume reads remain possible without a read JWT in the S3 topology.

**Verification.** Test.

### L2-INT-002

**Parent.** L1-INT-001

**Statement.** The deployment SHALL restrict master, volume, filer, and gRPC
listeners to the documented component or operations networks; clients SHALL
not reach direct filer or volume read paths that bypass S3 identities.

**Verification.** Demonstration.

### L2-DAT-001

**Parent.** L1-DAT-001

**Statement.** An acknowledged S3 write SHALL survive the documented container
replacement and cold backup/restore procedures at the recorded topology.

**Verification.** Test.

### L2-DAT-002

**Parent.** L1-DAT-001

**Statement.** A durability claim SHALL name and exercise its replication
setting, filer backend, storage mounts, and host or node failure domain.

**Verification.** Demonstration.

### L2-OBS-001

**Parent.** L1-OBS-001

**Statement.** Every role's logging, metrics, liveness, and composite readiness
profile SHALL be measured and bounded to an appropriate network and collector.

**Verification.** Test, Demonstration.

### L2-EVD-001

**Parent.** L1-EVD-001

**Statement.** Development-image SBOM and vulnerability inventories SHALL be
validated as complete inventories without being promoted to release evidence
or a passing vulnerability gate.

**Verification.** Test, Inspection.

### L2-EVD-002

**Parent.** L1-EVD-001

**Statement.** A candidate record SHALL bind every result to exact scope and
preserve limitations, failures, accepted risks, reviewers, and invalidation
triggers.

**Verification.** Inspection.

### L2-REL-001

**Parent.** L1-REL-001

**Statement.** Release-tag admission SHALL refuse an invalid date or sequence,
reused tag, mismatched lock version, or unpinned or mismatched UBI base.

**Verification.** Test.

### L2-REL-002

**Parent.** L1-REL-001

**Statement.** Publication SHALL require protected-main ancestry, exact
candidate evidence, native architecture results, vulnerability gates,
attestations, signatures, and independent release approval.

**Verification.** Test, Inspection, Demonstration.

## IMG criterion obligations (draft)

These L2 requirements specialize the existing L1 product obligations. A
criterion mapping records intended coverage, not implementation or evidence.
The [criterion inventory](HARDENING-CRITERIA.md) identifies each next proof.

### L2-SUP-003

**Parent.** L1-SUP-001

**Criterion.** IMG-01

**Statement.** Every build-stage and runtime base SHALL use a reviewed UBI
manifest-list digest matching the candidate lock on both architectures.

**Verification.** Test, Inspection.

### L2-SUP-004

**Parent.** L1-SUP-001

**Criterion.** IMG-02

**Statement.** Every acquired input SHALL match the reviewed lock's size,
digest, version, and linkage; the signed upstream OCI path SHALL verify the
expected publisher identity. A recorded tarball digest or MD5 sidecar SHALL
NOT be represented as publisher verification.

**Verification.** Test, Analysis.

### L2-SUP-005

**Parent.** L1-SUP-001

**Criterion.** IMG-03

**Statement.** Assembly SHALL use only admitted inputs with networking and
pulls disabled, and SHALL fail when an input is absent.

**Verification.** Test.

### L2-SUP-006

**Parent.** L1-SUP-001

**Criterion.** IMG-04

**Statement.** Input-refresh automation SHALL report drift without changing
locks; a reviewed pull request SHALL be required to admit an input.

**Verification.** Test, Inspection.

### L2-SUP-007

**Parent.** L1-SUP-001

**Criterion.** IMG-05

**Statement.** No secret SHALL enter a build argument, image environment,
layer, history, label, or committed build context.

**Verification.** Test, Inspection.

### L2-SUP-008

**Parent.** L1-SUP-001

**Criterion.** IMG-08

**Statement.** Each candidate child SHALL carry a read-only embedded inventory
of its UBI packages and admitted SeaweedFS binary that reconciles with the
lock and SPDX bill of materials.

**Verification.** Test, Inspection.

### L2-SUP-009

**Parent.** L1-SUP-001

**Criterion.** IMG-29

**Statement.** The selected UBI base SHALL be compared with the
publisher-current digest and satisfy the standard's age limit at candidate
admission.

**Verification.** Test, Inspection.

### L2-SUP-010

**Parent.** L1-SUP-001

**Criterion.** IMG-34

**Statement.** Secret, dependency, and build-definition scans SHALL gate the
same source commit before candidate image assembly begins.

**Verification.** Test, Inspection.

### L2-RUN-003

**Parent.** L1-RUN-001

**Criterion.** IMG-06

**Statement.** Neither candidate child SHALL contain a package manager,
package repository configuration, or package-signing key.

**Verification.** Test.

### L2-RUN-004

**Parent.** L1-RUN-001

**Criterion.** IMG-07

**Statement.** The image SHALL contain only files and SeaweedFS features
needed by declared supported roles; compilers and retrieval tools SHALL be
absent.

**Verification.** Test, Inspection.

### L2-RUN-005

**Parent.** L1-RUN-001

**Criterion.** IMG-09

**Statement.** Neither candidate child SHALL contain a setuid/setgid file or
undeclared world-writable path.

**Verification.** Test.

### L2-RUN-006

**Parent.** L1-RUN-001

**Criterion.** IMG-10

**Statement.** Executable and configuration paths SHALL be immutable to every
supported role, with writes confined to declared mounts.

**Verification.** Test.

### L2-RUN-007

**Parent.** L1-RUN-001

**Criterion.** IMG-11

**Statement.** Every supported role SHALL start and remain non-root without
an entrypoint privilege transition.

**Verification.** Test.

### L2-RUN-008

**Parent.** L1-RUN-001

**Criterion.** IMG-12

**Statement.** Every supported role SHALL function under an arbitrary
non-root UID using only declared writable mounts.

**Verification.** Test, Demonstration.

### L2-RUN-009

**Parent.** L1-RUN-001

**Criterion.** IMG-13

**Statement.** Every role SHALL run with all capabilities dropped,
no-new-privileges, and an enforced seccomp profile, read back from the
running process.

**Verification.** Test.

### L2-RUN-010

**Parent.** L1-RUN-001

**Criterion.** IMG-14

**Statement.** All effective role listeners, including optional metrics and
standalone listeners, SHALL be declared and use unprivileged ports.

**Verification.** Test.

### L2-RUN-011

**Parent.** L1-RUN-001

**Criterion.** IMG-15

**Statement.** Every supported role SHALL function with a read-only root and
only explicitly declared writable data and temporary mounts.

**Verification.** Test.

### L2-RUN-012

**Parent.** L1-RUN-001

**Criterion.** IMG-27

**Statement.** No unsupported remote administration daemon or unreviewed
management endpoint SHALL be exposed by a supported role.

**Verification.** Test, Inspection.

### L2-RUN-013

**Parent.** L1-RUN-001

**Criterion.** IMG-30

**Statement.** Processes, listeners, writable paths, and outbound
destinations SHALL match machine-readable declarations for every supported
role and topology.

**Verification.** Test, Inspection.

### L2-RUN-014

**Parent.** L1-RUN-001

**Criterion.** IMG-31

**Statement.** Where Kubernetes or OpenShift is in the approved support
boundary, the image SHALL be admitted unchanged under Restricted PSS and
restricted-v2 SCC; those platforms remain unqualified until measured.

**Verification.** Demonstration.

### L2-RUN-015

**Parent.** L1-RUN-001

**Criterion.** IMG-32

**Statement.** Where restricted-v3 is in the approved support boundary, every
role SHALL function in its user namespace without host-root equivalence.

**Verification.** Demonstration.

### L2-CFG-004

**Parent.** L1-CFG-001

**Criterion.** IMG-16

**Statement.** The production contract SHALL supply access keys, JWT keys,
TLS keys, and filer credentials from operator-controlled read-only files
without leaking values into arguments, logs, or image layers. The existing
environment-key option requires disposition before a claim.

**Verification.** Test, Analysis.

### L2-CFG-005

**Parent.** L1-CFG-001

**Criterion.** IMG-18

**Statement.** Missing or invalid required role configuration SHALL fail
closed with a useful diagnostic; every insecure opt-out SHALL be explicit
and bounded.

**Verification.** Test.

### L2-INT-003

**Parent.** L1-INT-001

**Criterion.** IMG-17

**Statement.** The image SHALL embed no private trust material;
operator-supplied CA, TLS, mTLS, and JWT material SHALL have a documented
rotation and revocation path.

**Verification.** Test, Inspection, Demonstration.

### L2-OBS-002

**Parent.** L1-OBS-001

**Criterion.** IMG-19

**Statement.** Role logs SHALL go to standard streams without disclosing
access keys, private keys, JWT secrets, or filer credentials.

**Verification.** Test.

### L2-OBS-003

**Parent.** L1-OBS-001

**Criterion.** IMG-20

**Statement.** Each role SHALL have a declared readiness and shutdown
contract that reports unhealthy states and preserves acknowledged writes
through graceful stop.

**Verification.** Test, Demonstration.

### L2-EVD-003

**Parent.** L1-EVD-001

**Criterion.** IMG-21

**Statement.** Each release child SHALL have an SPDX bill of materials
covering its OS and Go contents, retained and attested to its exact digest.

**Verification.** Test, Inspection.

### L2-EVD-004

**Parent.** L1-EVD-001

**Criterion.** IMG-25

**Statement.** No candidate child SHALL be released with an undispositioned
fixed High or Critical vulnerability; Trivy and Grype findings SHALL be
retained for both architectures.

**Verification.** Test, Inspection.

### L2-EVD-005

**Parent.** L1-EVD-001

**Criterion.** IMG-26

**Statement.** Every accepted exception SHALL name exact affected bytes,
owner, rationale, and expiry and SHALL fail release admission after expiry.

**Verification.** Test, Inspection.

### L2-EVD-006

**Parent.** L1-EVD-001

**Criterion.** IMG-28

**Statement.** Each candidate image and input bundle SHALL pass a malware
scan with pinned tooling and recorded, current signature database provenance.

**Verification.** Test, Inspection.

### L2-REL-003

**Parent.** L1-REL-001

**Criterion.** IMG-22

**Statement.** The published index and every child SHALL be signed, and
provenance SHALL verify against the authorized release identity and exact
digest.

**Verification.** Test, Inspection.

### L2-REL-004

**Parent.** L1-REL-001

**Criterion.** IMG-23

**Statement.** Both child image configs SHALL identify source, revision,
version, creation time, base digest, and artifact-lock digest accurately.

**Verification.** Test, Inspection.

### L2-REL-005

**Parent.** L1-REL-001

**Criterion.** IMG-24

**Statement.** Published version tags SHALL be immutable, and promotion
SHALL name the exact qualified index digest without rebuilding or
substituting children.

**Verification.** Test, Inspection.

### L2-REL-006

**Parent.** L1-REL-001

**Criterion.** IMG-33

**Statement.** Release candidates SHALL come only from reviewed commits on
protected main, with effective rules and required checks independently
recorded.

**Verification.** Test, Inspection.
