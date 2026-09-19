# SeaweedFS image-hardening requirements (draft)

These image-specific statements map one-to-one to the 34 required IMG criteria in
the `container-hardening` process as read at
`reference-web-server/v0.2.0` (`b255f915f880d624e2802521663af35fc2aa6b02`).
They are obligations for a future candidate, **not assertions that the criteria
are met**. The standard revision is not approved or pinned for conformance, and
no shared-profile deviation or release-eligibility decision is recorded here.
`docs/HARDENING-CRITERIA.md` tracks the outstanding proof and decisions.

An "Existing development check" below is a starting point only. A "Needed
check" is not implemented evidence. Future conformance evidence must identify
the tested commit, architecture, image ID, role and topology as applicable;
single-container evidence cannot satisfy a separated-role or replicated claim.
The requirement identifiers are stable verification pointers for later
component-control mapping.

### SWD-001

Every build-stage and runtime base shall use a reviewed UBI manifest-list digest
matching the candidate artifact lock on both supported architectures.

- Criterion: IMG-01
- Existing development check: `tests/lock.sh`, `tests/assembly.sh`
- Needed check: compare every candidate `FROM` and resolved child digest to the lock.

### SWD-002

Every acquired build input shall match the reviewed lock's size, digest,
version, and linkage measurements; the signed upstream OCI path shall verify
its expected publisher identity. Recorded tarball digests and upstream MD5
sidecars shall never be treated as publisher verification.

- Criterion: IMG-02
- Existing development check: `tests/acquisition.sh`, `tests/acquisition-signature.sh`
- Needed check: prove the complete installed-input closure on each candidate child.

### SWD-003

Image assembly shall use only previously admitted inputs, with networking and
pulls disabled, and shall fail when an input is absent.

- Criterion: IMG-03
- Existing development check: `tests/assembly.sh`
- Needed check: retain candidate build invocation and reject external layer cache or retrieval paths.

### SWD-004

Input-refresh automation shall report drift without changing locks; a reviewed
pull request shall be required before a new input is admitted.

- Criterion: IMG-04
- Needed check: read-only scheduled drift job and permissions test.

### SWD-005

No secret shall enter a build argument, image environment, layer, history,
label, or committed build context.

- Criterion: IMG-05
- Needed check: scan candidate build metadata and image layers for secret-shaped values.

### SWD-006

Neither candidate child shall contain a package manager, package repository
configuration, or package-signing key.

- Criterion: IMG-06
- Existing development check: `tests/smoke.sh`
- Needed check: full candidate filesystem inventory on amd64 and arm64.

### SWD-007

The image shall contain only files and SeaweedFS features needed by the
declared supported roles; compilers and retrieval tools shall be absent.

- Criterion: IMG-07
- Needed check: compare image contents and binary features with a per-role declaration.

### SWD-008

Each candidate child shall carry a read-only embedded inventory of UBI
packages and the admitted SeaweedFS binary that reconciles with the lock and
its SPDX bill of materials.

- Criterion: IMG-08
- Needed check: inspect embedded inventory, file permissions, lock, and SBOM together.

### SWD-009

The image shall have no setuid/setgid file or undeclared world-writable path.

- Criterion: IMG-09
- Needed check: scan the complete candidate filesystem on both architectures.

### SWD-010

Executable and configuration paths shall be immutable to every supported
runtime role, with writes confined to declared mounts.

- Criterion: IMG-10
- Existing development check: `tests/smoke.sh`
- Needed check: per-role candidate write attempts against software and configuration paths.

### SWD-011

Every supported role shall start and remain non-root without an entrypoint
privilege transition.

- Criterion: IMG-11
- Existing development check: `tests/smoke.sh`
- Needed check: retain per-process UID observations for every role and architecture.

### SWD-012

Every supported role shall function under an arbitrary non-root UID using
only declared writable mounts.

- Criterion: IMG-12
- Needed check: per-role arbitrary-UID candidate test; OpenShift admission remains separate.

### SWD-013

Every role shall run with all capabilities dropped, no-new-privileges, and an
enforced seccomp profile; these settings shall be read back from the process.

- Criterion: IMG-13
- Existing development check: `tests/smoke.sh`
- Needed check: record per-process `CapEff`, `NoNewPrivs`, and seccomp on candidate children.

### SWD-014

All effective role listeners, including optional metrics and standalone
listeners, shall be declared and shall use unprivileged ports.

- Criterion: IMG-14
- Existing development check: `tests/smoke.sh`, `tests/observability.sh`
- Needed check: compare actual listeners with each role/configuration declaration.

### SWD-015

Every supported role shall function with a read-only root filesystem and only
its explicitly declared writable data and temporary mounts.

- Criterion: IMG-15
- Existing development check: `tests/smoke.sh`, `tests/state-survival.sh`
- Needed check: repeat per role on both candidate architectures.

### SWD-016

The production deployment contract shall supply access keys, JWT keys, TLS
keys, and filer credentials from operator-controlled read-only files without
exposing values in arguments, logs, or image layers. The existing environment
key option needs a documented disposition against this criterion before a claim.

- Criterion: IMG-16
- Needed check: file permissions, missing/writable/world-readable input refusals, and leakage probes.

### SWD-017

The image shall embed no private trust material; operator-supplied CA, TLS,
mTLS, and JWT material shall have a documented rotation and revocation path.

- Criterion: IMG-17
- Existing development check: `tests/inter-component.sh`, `tests/s3-tls.sh`
- Needed check: candidate image inspection and rotation/revocation procedure test.

### SWD-018

Missing or invalid required role configuration shall fail closed with a useful
diagnostic; every insecure opt-out shall be explicit and bounded.

- Criterion: IMG-18
- Existing development check: `tests/smoke.sh`, `tests/inter-component.sh`, `tests/s3-tls.sh`
- Needed check: complete role/configuration negative matrix on candidate children.

### SWD-019

Role logs shall go to standard streams without disclosing access keys,
private keys, JWT secrets, or filer credentials.

- Criterion: IMG-19
- Existing development check: `tests/observability.sh`
- Needed check: upstream failure-path leakage and identity-attribution probes.

### SWD-020

Each role shall have a declared readiness and shutdown contract that reports
unhealthy states and preserves acknowledged writes through graceful stop.

- Criterion: IMG-20
- Existing development check: `tests/observability.sh`, `tests/state-survival.sh`
- Needed check: per-role candidate health and signal observations; standalone is separate.

### SWD-021

Each release child shall have an SPDX bill of materials covering its OS and Go
contents, retained and attested to the exact published digest.

- Criterion: IMG-21
- Existing development check: `tests/test_spdxchecks.py`
- Needed check: candidate child/index attachment and clean-environment retrieval.

### SWD-022

The published index and every child shall be signed, and provenance shall
verify against the authorized release identity and exact digest.

- Criterion: IMG-22
- Existing development check: `scripts/sign-release-image.sh`
- Needed check: release publication and independent clean-environment verification.

### SWD-023

Both child image configs shall identify source, revision, version, creation
time, base digest, and artifact-lock digest accurately.

- Criterion: IMG-23
- Needed check: inspect both candidate configs against commit, tag, and lock.

### SWD-024

Published version tags shall be immutable, and promotion shall name the exact
qualified index digest without rebuilding or substituting child images.

- Criterion: IMG-24
- Existing development check: `tests/test_release_admission.py`, `tests/test_candidate_index.py`
- Needed check: registry immutability and publication rehearsal.

### SWD-025

No candidate child shall be released with an undispositioned fixed High or
Critical vulnerability; Trivy and Grype findings shall be retained for both
architectures.

- Criterion: IMG-25
- Existing development check: `tests/test_vulnerability_gate.py`, `tests/test_govulnchecks.py`
- Needed check: apply the fail-closed gate to exact candidate children and resolve fixed Go findings.

### SWD-026

Every accepted exception shall name exact affected bytes, an owner, rationale,
and expiry, and shall fail the release gate after expiry.

- Criterion: IMG-26
- Needed check: reviewed exception record and expiry validation; no blanket exception.

### SWD-027

No unsupported remote administration daemon or unreviewed management endpoint
shall be exposed by a supported role.

- Criterion: IMG-27
- Existing development check: `tests/smoke.sh`
- Needed check: per-role binary, listener, and master/filer endpoint inspection.

### SWD-028

Each candidate image and input bundle shall pass a malware scan with pinned
tooling and recorded, current signature database provenance.

- Criterion: IMG-28
- Needed check: candidate malware gate, including false-positive disposition.

### SWD-029

The selected UBI base shall be compared with the publisher-current digest and
shall satisfy the standard's age limit at candidate admission.

- Criterion: IMG-29
- Needed check: read-only base-drift measurement and candidate release gate.

### SWD-030

Processes, listeners, writable paths, and outbound destinations shall match
machine-readable declarations for every supported role and topology.

- Criterion: IMG-30
- Needed check: declare and test separated-role and standalone variants separately.

### SWD-031

Where the first-release support boundary includes Kubernetes or OpenShift,
the image shall be admitted unchanged under Restricted PSS and restricted-v2
SCC; until measured, those platforms remain unqualified.

- Criterion: IMG-31
- Needed check: actual platform admission and runtime test for each claimed architecture.

### SWD-032

Where the support boundary includes restricted-v3, every supported role shall
function in its user namespace without host-root equivalence.

- Criterion: IMG-32
- Needed check: actual restricted-v3 admission and role tests; Podman flags are not equivalent.

### SWD-033

Release candidates shall come only from reviewed commits on protected main,
with effective rules and required checks independently recorded.

- Criterion: IMG-33
- Needed check: read-only branch/ruleset audit bound to the release commit.

### SWD-034

Secret, dependency, and build-definition scanning shall gate the same source
commit before candidate image assembly starts.

- Criterion: IMG-34
- Existing development check: `.github/workflows/ci.yml`, `.github/workflows/codeql.yml`
- Needed check: prove ordered pre-build gating rather than parallel green workflows.
