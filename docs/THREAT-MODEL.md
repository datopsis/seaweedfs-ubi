# SeaweedFS container threat model

This is the image project's working threat model for the proposed first-release
S3-backend use case. It is **not** an approved system threat model, an OSCAL
assessment, or release evidence. The deployment owner and independent cyber
reviewer must confirm the trust zones, selected storage and filer backend,
identity model, failure domains, and residual-risk decisions before release.
The supported boundary remains proposed in [SUPPORT.md](SUPPORT.md).

## Subjects, assets, and adversaries

The same image starts `master`, `volume`, `filer`, or `s3` as separate containers
in the intended production profile. `mini` is an opt-in, single-container
development profile; its result cannot evidence a distributed deployment.
`weed shell` and `version` are informational commands, not network services.
Other upstream roles and embedded services are outside the allowed entrypoint
boundary. See [ARCHITECTURE.md](ARCHITECTURE.md) and
[CONFIGURATION.md](CONFIGURATION.md) for the measured listeners and guards.

Assets are object bytes, bucket and filer metadata, master topology metadata,
S3 access keys, JWT signing keys, gRPC and HTTP private keys, backup archives,
reviewed build inputs, the image signing identity, and the evidence used to
authorize a release. Availability and recoverability matter as much as
confidentiality: an acknowledged write that disappears is a security failure.

Consider an unauthenticated client, a tenant with a valid but limited S3
identity, a workload that can reach a component network, a compromised image
registry or upstream artifact location, a malicious pull request, a compromised
CI or signing identity, and an operator mistake. A privileged host or
orchestrator compromise is outside what the image can prevent, but the
deployment must assess it rather than count image controls as host controls.

## Trust and failure boundaries

| Boundary | Allowed crossing | Ownership and critical limit |
| --- | --- | --- |
| Client to S3 gateway | Authenticated S3 over TLS in the proposed production profile | Image rejects a missing identity source and unsafe dual TLS/plaintext startup. Deployment supplies identities, certificate, ingress restriction, and authorization review. The guard does not assess key strength or grants. |
| Between S3, filer, master, and volume | Only named components on a restricted network | Deployment restricts reachability. gRPC mTLS authenticates gRPC peers when configured; it does not protect HTTP endpoints. |
| Direct filer and volume HTTP | Never reachable from the client network | In the filer-backed S3 topology, read JWTs are unavailable. Measured direct filer and volume read paths remain open even with `security.toml`; volume *writes* require JWTs when configured. Network isolation is a mandatory security boundary, not merely defense in depth. See [TLS.md](TLS.md). |
| Role to durable state | Explicit writable mount for stateful roles | Image refuses implicit master/volume temporary directories; deployment proves actual mount persistence, access control, encryption, capacity, and backup. A syntactically explicit path is not proof of persistence. |
| Filer to metadata backend | Embedded store or explicitly selected external backend | Deployment owns backend identity, TLS, backups, and recovery; no external backend is qualified by the one-host fixture. |
| Source and external bytes to image | Reviewed lock, verified acquisition, offline assembly | Image project owns digest and version checks and signature verification where the selected upstream OCI path supports it. Recorded tarball digests and upstream `.md5` are not publisher verification. |
| Image and evidence to registry and production | Exact candidate/index digest, signed provenance, admission policy | Image project owns publication; registry and platform owners enforce immutable, authenticated, digest-based admission. No release candidate or signed image exists yet. |
| Host, orchestrator, and network | Restricted runtime, secrets, policies, logging, storage | Deployment and host owners supply and verify these controls; image compatibility does not establish enforcement. |

The one-host separated-role fixture exercises component wiring and some
failure cases. It does not establish host, disk, zone, or multi-node durability.
Neither it nor `mini` may close a multi-host or platform assessment.

## Threats, controls, and open evidence

Each row is a scenario to assess, not a declaration that its controls pass.
`L1-*` identifiers point to product requirements; the matching L2/L3 and
test-level links are in [TRACE-MATRIX.md](TRACE-MATRIX.md). The evidence column
names current development checks or the missing qualification work.

| ID | Attack or failure path | Required treatment and owner | Evidence / remaining gap |
| --- | --- | --- | --- |
| TM-01 | An upstream tarball, OCI image, or UBI base is replaced, or a copied digest is mistaken for publisher identity. | Image project: verify selected source signature where available, all locked byte and linkage measurements, and refuse unreviewed input; separate acquisition from offline assembly (`L1-SUP-001`). | `tests/acquisition.sh`, `tests/assembly.sh`, native CI; candidate-bound provenance and source-build investigation remain open. See [ARTIFACT-ACQUISITION.md](ARTIFACT-ACQUISITION.md). |
| TM-02 | CI, a pull request, or a signing credential publishes an image from unreviewed code. | Image project and repository administrator: protected reviewed source, least-privilege jobs, exact candidate identity, independent cyber and release approval (`L1-REL-001`). | Branch checks and release-tag admission exist; release publication is intentionally blocked. A GitHub green check is not an approved candidate. |
| TM-03 | A mutable tag, registry substitution, or wrong architecture swaps the image after testing. | Release and platform owners: immutable digest promotion, verify index and both child digests, signature/provenance and admission policy (`L1-EVD-001`, `L1-REL-001`). | Candidate-index verifier exists; no published candidate, promotion rehearsal, or platform admission evidence. |
| TM-04 | The entrypoint starts an unsupported role, embedded listener, or accidentally enables permissive standalone mode. | Image project: allowlist, negative startup checks, explicit `mini` opt-in and visible limits (`L1-RUN-001`, `L1-CFG-001`). | `tests/smoke.sh`, `tests/cluster.sh`; recheck upstream defaults for each version. |
| TM-05 | Missing S3 configuration silently grants anonymous read, write, or delete; an overbroad valid key crosses tenants. | Image project refuses missing identity source; deployment owner reviews identity grants, key lifecycle, and bucket policy (`L1-CFG-001`, `L1-API-001`). | `tests/s3.sh` exercises positive/negative identities; the guard does not prove least privilege for operator-supplied policies. |
| TM-06 | A client reaches filer or volume HTTP directly and bypasses S3 authentication to read object bytes. | Deployment owner: deny client reachability to all internal HTTP/gRPC listeners and verify from a client-zone probe (`L1-INT-001`, `L2-INT-002`). Image project must keep documenting the read-JWT incompatibility. | `tests/inter-component.sh` demonstrates the bypass, not its network closure; real deployment isolation evidence is missing. This is release-critical. |
| TM-07 | A hostile peer impersonates a component or writes directly to a volume. | Deployment owner supplies gRPC mTLS identities and write-JWT keys; image project tests rejection of untrusted peers and unsigned direct writes (`L1-INT-001`). | `tests/inter-component.sh` covers a one-host fixture. Certificate/JWT rotation without downtime and multi-host identity behavior remain open. |
| TM-08 | A certificate/key is logged, baked into a layer, exposed in process arguments, or mounted too broadly. | Image and deployment owners: runtime-supplied read-only files, restrictive permissions, no layer/argument/log disclosure, rotation and revocation procedures (`L1-OBS-001`). | Selected log/error-body negative checks exist; complete secret-file permission, layer, and rotation assessment remains open. |
| TM-09 | A mistaken HTTPS flag leaves the original S3 listener in plaintext; a client trusts the wrong certificate. | Image project refuses unsafe dual-listener startup; deployment owner supplies matching certificates, trust roots, and network policy (`L1-CFG-001`). | `tests/s3-tls.sh` covers S3 TLS and negative trust; TLS on master/filer/volume HTTP and approved crypto boundary remain open. |
| TM-10 | A temporary or wrong data path appears healthy, then loses acknowledged writes after restart. | Image project refuses implicit/temporary master and volume paths; deployment owner proves persistent mounts and filer backend durability (`L1-CFG-001`, `L1-DAT-001`). | `tests/state-survival.sh` and cold restore cover the fixture only; real storage and backend evidence remain open. |
| TM-11 | One host, disk, or metadata backend fails; one-host replication is misreported as multi-node durability. | Deployment owner selects topology and failure domains; image project tests and records exact replication and backup scope (`L1-DAT-001`). | `tests/replication.sh`, `tests/backup-restore.sh` are one-host evidence. Multi-host, disk, zone, and backend failure tests remain open. |
| TM-12 | Resource exhaustion causes partial writes, silent loss, or prolonged outage. | Image and deployment owners: bounded limits, visible failure, capacity alerts, tested restoration (`L1-DAT-001`, `L1-OBS-001`). | `tests/resource-exhaustion.sh` uses bounded `tmpfs`; inode, physical disk, sustained load, and real-host alerts remain open. |
| TM-13 | Logs, metrics, readiness, or debug listeners leak topology or secrets or falsely report availability. | Image project limits listeners and tests secret redaction; deployment owner confines metrics, protects collectors, and uses composite readiness (`L1-OBS-001`). | `tests/observability.sh`, `tests/cluster.sh`; production collector, retention, authentication, and alert evidence remain open. |
| TM-14 | A scanner finding is hidden by alias/severity differences or development scans are promoted to release evidence. | Image project retains full per-architecture inventories and blocks fixed High/Critical findings on the exact candidate (`L1-EVD-001`, `L1-REL-001`). | Trivy/Grype inventories and a fail-closed decision primitive exist; candidate gate and known fixed High remediation remain open. No waiver is implied. |
| TM-15 | SCAP or an inherited platform control is mislabeled as image compliance. | Image and independent cyber reviewer: classify image, deployment, host, and organization responsibilities; qualify only the selected rules and exact target (`L1-EVD-001`). | Tailored SCAP and reviewed OSCAL component definition are pending. A passing subset is not STIG certification. |

## Review and invalidation

Review every row when the upstream binary/version, supported role, default
listener, storage backend, identity mechanism, deployment topology, base,
container runtime, standard source revision, or support boundary changes.
For each release candidate, carry its unresolved threats into the qualification
ledger with owner, reviewer, evidence, limitations, and disposition. A threat
row cannot be closed merely by a control mapping, a passing unit test, a
single-container run, or an exception in another repository.
