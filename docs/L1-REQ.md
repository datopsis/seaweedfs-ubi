# SeaweedFS UBI: Level 1 product requirements

This is the first, deliberately incomplete reconstruction of product obligations
from the implemented image and the proposed first-release boundary in
[`SUPPORT.md`](SUPPORT.md). It does **not** approve that boundary, settle a cyber
baseline, or qualify a release. An unmet requirement is a finding to close or a
reviewed non-requirement to record, never a reason to soften its wording.

Identifiers remain stable once assigned. Retired identifiers are not reused.
L2 and L3 requirements decompose these obligations; the generated
[`TRACE-MATRIX.md`](TRACE-MATRIX.md) records test links and visible gaps. `Test`
means an executable check, `Analysis` a reasoned evaluation, `Inspection` a
review of an artifact, and `Demonstration` an exercise on an identified runtime.
A test link is not a passing release-candidate result.

## Supply chain

### L1-SUP-001

**Statement.** Every SeaweedFS binary, UBI base, and other build input SHALL
be admitted against reviewed, immutable identities before network-free
assembly. Source and build inputs SHALL undergo reviewed refresh and pre-build
security checks; the evidence SHALL distinguish byte integrity from publisher
identity.

**Verification.** Test, Analysis.

## Runtime boundary

### L1-RUN-001

**Statement.** The image SHALL contain only declared runtime contents and
behavior. Every admitted role SHALL remain non-root, operate with a read-only
root filesystem and no Linux capabilities, and refuse unsupported role or
listener expansion by default; platform compatibility SHALL be claimed only
where measured.

**Verification.** Test.

## Fail-closed configuration

### L1-CFG-001

**Statement.** The image SHALL refuse a missing S3 identity source, implicit or
temporary durable-data directory, and unsafe default listener configuration,
unless the exact documented operator opt-out is selected. Runtime secrets
SHALL be operator-controlled and their supported delivery modes SHALL be
assessed before a hardening claim.

**Verification.** Test.

## S3 client boundary

### L1-API-001

**Statement.** The qualified S3 profile SHALL exercise authenticated object
operations, refuse anonymous operations in the default profile, and state the
operations and clients for which compatibility evidence exists.

**Verification.** Test, Analysis.

## Inter-component boundary

### L1-INT-001

**Statement.** A qualified separated-role deployment SHALL protect the
master, volume, filer, and S3 paths with tested network restrictions, gRPC
mutual TLS, and volume write JWTs. Because read JWTs are unavailable in the
filer-backed S3 topology, direct filer and volume read paths SHALL be isolated
from client networks and the residual exposure SHALL be documented and
assessed. A standalone result SHALL NOT be used as evidence for these controls.

**Verification.** Test, Demonstration.

## Durable state

### L1-DAT-001

**Statement.** Every claimed durability and recovery behavior SHALL be tied to
an explicit storage layout, filer backend, replication topology, backup and
restore procedure, and failure domain tested at matching scope.

**Verification.** Test, Demonstration.

## Observability

### L1-OBS-001

**Statement.** Logs, metrics, and health or readiness surfaces SHALL have an
explicit exposure and ownership boundary, exclude secrets from project-owned
output, and be qualified for each supported role and platform.

**Verification.** Test, Demonstration.

## Assurance evidence

### L1-EVD-001

**Statement.** Every security and support claim SHALL cite evidence matching
its image digest, architecture, role, topology, configuration, platform, tool
inputs, and evidence level. Candidate vulnerability and malware gates and
expiring exceptions SHALL be separately dispositioned; an inventory SHALL NOT
be described as a passing gate or a tailored scan as certification.

**Verification.** Test, Inspection.

## Release

### L1-REL-001

**Statement.** A release SHALL be immutable, multi-architecture, scanned,
attested, signed, independently reviewed, and published only after matching
candidate and cyber-assessment evidence passes the approved release gates.

**Verification.** Test, Inspection, Demonstration.

## Explicit non-requirements for the proposed first release

These are not waivers for an implemented control or unreviewed exclusions from a
selected cyber baseline. The support boundary remains subject to human approval.

| ID | Non-requirement | Reason |
| --- | --- | --- |
| `NR-001` | A production claim for the single-container `mini` profile | It cannot exercise inter-component controls or replication. |
| `NR-002` | FIPS validation or STIG certification from UBI or tailored SCAP alone | Neither establishes the required system or cryptographic boundary. |
| `NR-003` | Broad S3 API conformance from one client's object-operation tests | Compatibility must name the tested operations and clients. |
| `NR-004` | Host-loss durability from a one-host replicated-volume test | Failure domains differ; multi-host evidence is required. |
