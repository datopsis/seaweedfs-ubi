# SeaweedFS UBI: Level 3 requirements

These are initial, directly verifiable implementation obligations derived from
[`L2-REQ.md`](L2-REQ.md). Missing test links remain visible in the generated
matrix. A linked unit test covers only the behavior it exercises, not an image,
topology, or release-candidate claim.

### L3-SUP-001

**Parent.** L2-SUP-001

**Statement.** Lock validation SHALL reject missing or inconsistent artifact
identity, architecture, digest, size, variant, commit, or linkage fields.

**Verification.** Test.

### L3-SUP-002

**Parent.** L2-SUP-002

**Statement.** An altered bundle SHALL be rejected again at assembly time.

**Verification.** Test.

### L3-RUN-001

**Parent.** L2-RUN-001

**Statement.** A running role SHALL report a nonzero UID and zero effective
capabilities under a read-only root filesystem.

**Verification.** Test.

### L3-RUN-002

**Parent.** L2-RUN-002

**Statement.** Unsupported subcommands and filer-embedded S3, WebDAV, IAM, and
SFTP enablement SHALL fail before the `weed` process starts.

**Verification.** Test.

### L3-CFG-001

**Parent.** L2-CFG-001

**Statement.** A missing S3 identity source or nonexistent named identity file
SHALL cause a configuration error rather than anonymous startup.

**Verification.** Test.

### L3-CFG-002

**Parent.** L2-CFG-002

**Statement.** `master` and `volume` SHALL refuse their upstream temporary
directory defaults when an explicit persistent path is absent.

**Verification.** Test.

### L3-API-001

**Parent.** L2-API-001

**Statement.** An authenticated client SHALL complete object put, get, list,
delete, and multipart operations while an anonymous client is refused.

**Verification.** Test.

### L3-INT-001

**Parent.** L2-INT-001

**Statement.** The separated-role fixture SHALL refuse a direct volume write
without the configured JWT and gRPC access without a trusted client certificate,
and SHALL record the unauthenticated direct read paths that still require
deployment network isolation.

**Verification.** Test.

### L3-DAT-001

**Parent.** L2-DAT-001

**Statement.** Cold backup validation SHALL refuse an archive path that escapes
the selected backup root through traversal, an absolute path, or a symlink.

**Verification.** Test.

### L3-OBS-001

**Parent.** L2-OBS-001

**Statement.** Listener inspection SHALL distinguish listening from
non-listening IPv4 and IPv6 sockets for the role's measured exposure set.

**Verification.** Test.

### L3-EVD-001

**Parent.** L2-EVD-001

**Statement.** A development SPDX inventory SHALL identify SeaweedFS and its
resolvable Go dependency inventory before the inventory is retained.

**Verification.** Test.

### L3-EVD-002

**Parent.** L2-EVD-001

**Statement.** A development image Trivy inventory SHALL include both OS and
language-package targets without treating the inventory as a passing gate.

**Verification.** Test.

### L3-EVD-003

**Parent.** L2-EVD-001

**Statement.** A binary govulncheck inventory SHALL record its tool and
database versions without treating the inventory as a passing gate.

**Verification.** Test.

### L3-REL-001

**Parent.** L2-REL-001

**Statement.** The deterministic release-tag validator SHALL refuse malformed,
reused, mistimed, or out-of-sequence tags and input-version mismatches.

**Verification.** Test.

## IMG criterion verification obligations (draft)

Each requirement below decomposes one IMG-mapped L2 requirement. Its test or
inspection link remains open unless the generated trace matrix says otherwise;
a link still does not establish candidate-level or cross-topology evidence.

### L3-SUP-003

**Parent.** L2-SUP-003

**Statement.** Candidate validation SHALL compare every build-stage `FROM`
and resolved architecture child digest with the reviewed base lock.

**Verification.** Test.

### L3-SUP-004

**Parent.** L2-SUP-004

**Statement.** Candidate acquisition SHALL reject wrong bytes or measurements
and SHALL separately verify the expected upstream OCI signature identity;
tarball digest or MD5 agreement SHALL NOT be called publisher verification.

**Verification.** Test, Analysis.

### L3-SUP-005

**Parent.** L2-SUP-005

**Statement.** Candidate assembly SHALL retain a no-network/no-pull build
record and reject a missing input or external retrieval path.

**Verification.** Test.

### L3-SUP-006

**Parent.** L2-SUP-006

**Statement.** A scheduled drift job SHALL hold read permission only, report
new inputs, and leave the reviewed lock unchanged.

**Verification.** Test, Inspection.

### L3-SUP-007

**Parent.** L2-SUP-007

**Statement.** Candidate source, build invocation, history, labels, and
layers SHALL be inspected for secret-shaped values and credential-bearing
build arguments.

**Verification.** Test, Inspection.

### L3-SUP-008

**Parent.** L2-SUP-008

**Statement.** The embedded inventory in each candidate child SHALL be
read-only and reconcile with its reviewed lock and generated SPDX inventory.

**Verification.** Test.

### L3-SUP-009

**Parent.** L2-SUP-009

**Statement.** Candidate admission SHALL record publisher-current UBI digest
and age and reject a base older than the selected standard's limit.

**Verification.** Test, Inspection.

### L3-SUP-010

**Parent.** L2-SUP-010

**Statement.** CI SHALL prove source-secret, dependency, and build-definition
gates completed for the same commit before candidate build starts.

**Verification.** Test.

### L3-RUN-003

**Parent.** L2-RUN-003

**Statement.** Full candidate filesystem inspection on both architectures
SHALL find no package-manager executable, repository file, or package key.

**Verification.** Test.

### L3-RUN-004

**Parent.** L2-RUN-004

**Statement.** Candidate contents and binary features SHALL match a committed
per-role declaration and exclude compilers and retrieval tools.

**Verification.** Test, Inspection.

### L3-RUN-005

**Parent.** L2-RUN-005

**Statement.** Full candidate filesystem inspection SHALL find no setuid or
setgid file and no world-writable path outside an explicit declaration.

**Verification.** Test.

### L3-RUN-006

**Parent.** L2-RUN-006

**Statement.** Every role SHALL fail to write executable and configuration
paths while writes to only its documented mounts succeed.

**Verification.** Test.

### L3-RUN-007

**Parent.** L2-RUN-007

**Statement.** Candidate evidence SHALL record the configured UID and the
running UID of every supported role on each architecture, with none equal to
zero or changed by the entrypoint.

**Verification.** Test.

### L3-RUN-008

**Parent.** L2-RUN-008

**Statement.** Every role SHALL start under a non-default arbitrary non-root
UID with the documented mounts and complete its role-specific readiness test.

**Verification.** Test.

### L3-RUN-009

**Parent.** L2-RUN-009

**Statement.** Every candidate role process SHALL report zero effective
capabilities, `NoNewPrivs` enabled, and an active seccomp filter.

**Verification.** Test.

### L3-RUN-010

**Parent.** L2-RUN-010

**Statement.** Measured sockets for each role and supported configuration
SHALL equal the declared listeners and use ports at or above 1024.

**Verification.** Test.

### L3-RUN-011

**Parent.** L2-RUN-011

**Statement.** Every role SHALL start and exercise its core operation with a
read-only root and only declared data and temporary mounts.

**Verification.** Test.

### L3-RUN-012

**Parent.** L2-RUN-012

**Statement.** Per-role candidate inspection SHALL find no remote admin
daemon and SHALL inventory master and filer management endpoints for review.

**Verification.** Test, Inspection.

### L3-RUN-013

**Parent.** L2-RUN-013

**Statement.** Measured processes, sockets, writable paths, and outbound
calls SHALL match declarations separately for standalone and separated-role
topologies.

**Verification.** Test.

### L3-RUN-014

**Parent.** L2-RUN-014

**Statement.** An actual Kubernetes and OpenShift admission and runtime
exercise SHALL identify the exact Restricted PSS and restricted-v2 policies,
architecture, roles, and configuration tested before a platform claim.

**Verification.** Demonstration.

### L3-RUN-015

**Parent.** L2-RUN-015

**Statement.** An actual restricted-v3/user-namespace exercise SHALL show
every claimed role functioning without host-root equivalence; Podman flags
alone SHALL NOT substitute for the platform result.

**Verification.** Demonstration.

### L3-CFG-003

**Parent.** L2-CFG-004

**Statement.** Candidate role tests SHALL verify secret-file permissions,
missing and unsafe-file refusals, and the absence of credential values from
arguments, logs, and layers; the environment-key option SHALL be explicitly
dispositioned before claiming IMG-16.

**Verification.** Test, Analysis.

### L3-CFG-004

**Parent.** L2-CFG-005

**Statement.** A negative matrix for every supported role SHALL show missing
and invalid required configuration exits nonzero without opening an insecure
listener; each documented opt-out SHALL be exercised separately.

**Verification.** Test.

### L3-INT-002

**Parent.** L2-INT-003

**Statement.** Candidate inspection SHALL find no embedded private key or
trust anchor, and an operator procedure SHALL demonstrate CA, certificate,
and JWT-key replacement and revocation at the declared topology.

**Verification.** Test, Inspection, Demonstration.

### L3-OBS-002

**Parent.** L2-OBS-002

**Statement.** Role-specific normal and failure paths SHALL emit logs only
to standard streams without S3 keys, JWT keys, TLS private keys, or filer
credentials.

**Verification.** Test.

### L3-OBS-003

**Parent.** L2-OBS-003

**Statement.** Every role's health response and signal handling SHALL be
measured, and graceful shutdown SHALL preserve acknowledged writes at the
topology for which durability is claimed.

**Verification.** Test, Demonstration.

### L3-EVD-004

**Parent.** L2-EVD-003

**Statement.** Candidate child SPDX inventories SHALL cover OS and Go
contents, attach to each exact digest, and be independently retrievable.

**Verification.** Test, Inspection.

### L3-EVD-005

**Parent.** L2-EVD-004

**Statement.** The candidate gate SHALL retain full Trivy and Grype findings
for both children and reject an undispositioned fixed High or Critical
finding on either architecture.

**Verification.** Test.

### L3-EVD-006

**Parent.** L2-EVD-005

**Statement.** An exception validator SHALL reject missing ownership,
rationale, affected digest, or expiry and SHALL reject an expired exception.

**Verification.** Test.

### L3-EVD-007

**Parent.** L2-EVD-006

**Statement.** Candidate inputs and both child filesystems SHALL be scanned
with a pinned malware scanner and recorded current signature database;
findings SHALL be dispositioned before release.

**Verification.** Test, Inspection.

### L3-REL-002

**Parent.** L2-REL-003

**Statement.** Clean-environment verification SHALL validate signatures on
the exact index and children and provenance bound to the authorized release
identity and published digests.

**Verification.** Test, Demonstration.

### L3-REL-003

**Parent.** L2-REL-004

**Statement.** Candidate admission SHALL compare required labels in both
child configs with the release tag, source commit, base digest, and lock.

**Verification.** Test.

### L3-REL-004

**Parent.** L2-REL-005

**Statement.** A publication rehearsal SHALL reject an existing version tag
and promote only the already-qualified index digest without rebuilding or
substituting a child.

**Verification.** Test, Demonstration.

### L3-REL-005

**Parent.** L2-REL-006

**Statement.** Release admission SHALL record effective branch rules,
required checks, review, and the candidate's protected-main ancestry at the
exact release commit.

**Verification.** Test, Inspection.
