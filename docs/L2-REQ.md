# SeaweedFS UBI: Level 2 requirements

These decompose [`L1-REQ.md`](L1-REQ.md). They are an initial slice, not a
complete first-release specification. A parent link is structural, not evidence.

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
direct volume request lacking a valid read or write JWT.

**Verification.** Test.

### L2-INT-002

**Parent.** L1-INT-001

**Statement.** The deployment SHALL restrict master, volume, filer, and gRPC
listeners to the documented component or operations networks.

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
