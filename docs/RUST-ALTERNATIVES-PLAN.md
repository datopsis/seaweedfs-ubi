# Rust volume and worker adoption plan

Status: plan and preliminary research, 2026-09-19. No Rust binary has been
admitted, no Rust role is enabled, and no Rust behavior or security property is
qualified. This plan does not change the first-release boundary or waive any
existing gate in the [work plan](README.md).

## Decision and scope

The requested direction is to bring the two upstream Rust executables into a
development image and characterize them. Treat **packaged**, **launchable for
development**, and **supported for production** as three separate decisions.
The existing `weed volume` remains the default and the qualification baseline.
`weed-volume` is an alternative *volume server*, not a companion process to the
Go volume server. `weed-worker` is an alternative maintenance/plugin worker,
not another volume server. Upstream's `volume-rust` and `worker-rust` names are
entrypoint selectors for those executables, not flags to `weed`.

The current first-release S3 topology is `master` + Go `volume` + `filer` +
`s3`. Adding a Rust volume is a possible substitution in that topology. A Rust
worker requires a separately designed admin/plugin scheduler, privileges to
act on data, and possibly table-catalog services. It **does not** become part
of the production profile simply because its binary is packaged. Keep the
worker role refused until that trust boundary is approved and tested. Decide
before release whether carrying an unreachable ~large worker binary and its
vulnerabilities in the default image is acceptable, or whether a separate
digest-pinned development/worker flavor is warranted. Do not describe a flavor
split as the same-image/two-profile contract without revising that contract.

`mini` stays the Go implementation in one process. Adding `weed-volume` does
not replace mini's embedded Go volume server, and adding `weed-worker` does not
turn mini's existing worker gRPC listener into an external worker. Do not
launch either Rust executable implicitly, re-enable WebDAV/Admin UI, or treat
mini evidence as volume-replacement, worker, replication, or multi-node evidence.
Investigate mini's 23646/33646 admin/worker listener boundary separately.

## Preliminary upstream signals to track, not claims of completeness

Repeat this search against the selected tag, release notes, GitHub issues and
PRs, security advisories, RustSec, and the exact Cargo dependency graph at
every candidate update. Record affected versions, fix commit, exploitability,
reproducer, owner, disposition, and evidence. Search both open and closed
reports; a closed issue does not prove the admitted binary includes its fix.

| Signal | Why it matters / required follow-up |
| --- | --- |
| [Upstream 4.46 release](https://github.com/seaweedfs/seaweedfs/releases/tag/4.46) includes Rust durable-write/index-flush fixes and introduces the Rust Lance plugin worker | Compare their exact commits with the locked image; test acknowledged-write durability and define the worker's actual job set and side effects. |
| [Rust EC degraded-read report #10181](https://github.com/seaweedfs/seaweedfs/issues/10181), reported against 4.37 and shown closed | Determine the fixing commit and whether 4.46 contains it; reproduce degraded reads and EC health under the selected index/layout before any EC claim. EC remains outside the current first-release support boundary. |
| [Critical volume SSRF advisory GHSA-87fv-vqqr-m4jr](https://github.com/seaweedfs/seaweedfs/security/advisories/GHSA-87fv-vqqr-m4jr) says Rust endpoint validation was mirrored | Verify the exact Rust gRPC implementation and negative SSRF/auth tests in the locked revision; do not infer protection solely from the Go package advisory or a scanner's package match. |
| [4.47 release notes](https://github.com/seaweedfs/seaweedfs/releases/tag/4.47) describe later Rust volume fixes for phantom volumes, EC buffer retention, and tail behavior | Triage against 4.46; decide whether a version update is prerequisite to Rust qualification. A newer release existing is not proof that 4.46 is safe or unsafe. |
| [Iceberg maintenance metadata-path report #10357](https://github.com/seaweedfs/seaweedfs/issues/10357) concerns worker-produced table metadata, not yet established as a `weed-worker` bug | Test worker outputs with independent clients; do not attribute a Go worker issue to Rust without a reproducer. It illustrates the risk of maintenance jobs changing durable metadata. |

This is a targeted initial search, **not** an exhaustive issue or CVE inventory.
No absence-of-vulnerabilities claim follows from it. The upstream
[Dockerfile](https://github.com/seaweedfs/seaweedfs/blob/4.46/docker/Dockerfile.go_build)
and [entrypoint](https://github.com/seaweedfs/seaweedfs/blob/4.46/docker/entrypoint.sh)
are the starting point for exact binary and invocation analysis.

## Ordered increments and gates

1. **Scope and acquisition design.** Record an ADR for same-image versus
   separate-flavor packaging and worker/admin boundary, without changing
   defaults. Inventory the signed upstream 4.46 image per native AMD64/ARM64
   manifest: `weed`, `weed-volume`, `weed-worker`, their SHA-256, sizes,
   versions/embedded commit markers, ELF interpreter and shared libraries,
   licenses, and large-disk behavior. Check that Rust binaries actually run on
   UBI Micro; Alpine execution is not UBI compatibility evidence. Inspect the
   source-to-prebuilt-to-image chain for each Rust binary. Extend the reviewed
   artifact lock and negative admission tests so an absent, zero-byte,
   wrong-architecture, mismatched, or substituted binary fails closed. Keep
   digest + cosign identity verification before extraction, and preserve the
   documented limitation that tarball MD5 and locally recorded hashes are not
   publisher verification. Exit: reviewed trust record and native runtime
   proof for each binary, without broadening the role allowlist.
2. **Package without silent activation.** Update the hermetic build context,
   Containerfile, filesystem manifest, notices, and SBOM assertions for the
   selected image shape. Preserve non-root, read-only root, no capability,
   explicit writable data, and package-manager-free final runtime. Measure
   per-architecture uncompressed and compressed image size, per-binary growth,
   cold start and memory; compare the *same* executable/role scope with the
   official image. Fail if unexpected ELF dependencies or extra files appear.
   Exit: development image contains only approved binaries and all old roles
   behave exactly as before.
3. **Rust volume characterization.** Add a distinct, explicit `volume-rust`
   development selector only after mapping Rust CLI flags and startup defaults
   to our guards; refuse missing/temporary data directories and insecure
   configuration just as for Go. Run identical Go/Rust suites on both native
   architectures: PID 1/UID/capabilities/read-only root; listener inventory;
   TLS/mTLS and invalid-trust negatives; volume write JWT and direct-read
   boundary; gRPC admin authorization/SSRF negatives; S3 byte-exact CRUD,
   multipart and Iceberg path; state across restart/replacement; graceful
   shutdown/fsync/crash/disk-full/index-flush; backup/restore; upgrade and
   rollback. Compare Go-created volumes read and written by Rust, then reverse,
   on disposable copies only; test large-disk format and refuse mixed-version
   or destructive migration assumptions. Run replication, volume loss, network
   partition and EC cases with the required topology, explicitly separating
   one-host development results from multi-host durability evidence. Record
   behavioral differences and supported/non-supported flags. Exit: rust-volume
   support decision with evidence per architecture/topology; default stays Go
   until specifically approved.
4. **Rust worker characterization.** First map actual 4.46 jobs and all admin,
   filer, S3, catalog, credential, and filesystem dependencies. Design a
   separated admin/worker network and identity boundary; the existing mini
   listener is not a qualified admin deployment. Prove authentication and
   authorization of worker registration, scheduling, job configuration and
   execution; mTLS/secret handling; no unintended public listeners; explicit
   writable working directory; bounded CPU/memory/temp storage; health,
   readiness and metrics. Use disposable table data to test job idempotence,
   retry/cancel/crash recovery, least privilege, auditability, and byte/metadata
   correctness with independent Iceberg/Lance readers as applicable. Explicitly
   test that an Iceberg job cannot alter Lance data or another tenant's bucket.
   Decide whether embedded catalog/advanced IAM/STS is actually required; if
   so, that is a separate scope and cyber approval, not a side effect of adding
   the binary. Exit: documented allow/refuse decision for `worker-rust`; no
   production claim until the admin path and job-specific test matrix pass.
5. **Cyber and vulnerability assurance.** Update threat model, L1/L2/L3
   requirements, applicable SRGs/control ownership, and generated trace matrix
   for both Rust paths. Add Rust dependency inventory from the *exact* upstream
   commit/Cargo.lock alongside binary/image SBOMs; evaluate RustSec, GitHub
   advisories, OSV and current image scanners, recording where binary scanners
   cannot see crates. Track each potential advisory with component, affected
   version, reachability, fix status, mitigation, owner, expiry and dashboard
   link; do not suppress unresolved findings to pass a gate. Compare Go TLS/JWT
   behavior with Rust TLS/JWT, crypto modules and FIPS boundary; **make no FIPS
   claim** for either. Review HTTP/gRPC authorization, SSRF, path traversal,
   secret leakage, config reload, volume-file parsing, worker supply-chain and
   destructive maintenance privileges. Re-run SCAP only for image-owned
   checks; do not mistake an image scan for deployment certification.
6. **Documentation, diagrams and release decision.** Complete the file review
   below with an explicit changed/not-applicable rationale in the PR. Create
   repository-native SVGs (none currently exist) for image/artifact provenance,
   Go-versus-Rust volume substitution and its data/trust boundaries, and the
   optional admin/worker control and data flow. Include text equivalents and
   link/render checks. Update release candidate admission, native/platform
   matrix, signature/SBOM/attestation binding, rollback and support statements
   to name exactly which binary/role combination was assessed. No release
   claim may rely on merely packaging Rust binaries.

## Document-by-document review ledger

At the implementation PRs, review **every row**, mark changed or no change
with a reason, and check cross-document claims. This is an inventory and likely
impact, not a claim that every file must change. Regenerate `TRACE-MATRIX.md`
with `scripts/build-trace-matrix.py`; never hand-edit the generated matrix.

| Document | Review question / likely update |
| --- | --- |
| `AGENTS.md` | Preserve all non-negotiable acquisition, role, runtime and evidence guardrails. |
| `CLAUDE.md` | Update one-binary, role, architecture and verification descriptions if bytes/roles change. |
| `README.md` | Explain new image contents, explicit selectors, default Go behavior, size and support status. |
| `SECURITY.md` | Add Rust/worker attack surfaces, reporting and active findings. |
| `CONTRIBUTING.md` | Add Rust-specific build, tests, issue triage and review expectations. |
| `CHANGELOG.md` | Record each completed increment only; no unsupported capability claim. |
| `THIRD_PARTY_NOTICES.md` | Assess Rust crates, licenses, attribution and redistribution. |
| `docs/README.md` | Track increments, gates, decisions and changes to first-release boundary. |
| `docs/ARCHITECTURE.md` | Replace one-binary manifest/size; show alternative volume and worker topology. |
| `docs/ARTIFACT-ACQUISITION.md` | Record exact provenance and trust limits of both Rust binaries. |
| `docs/BACKUP-RESTORE.md` | Check cross-implementation data/metadata restore and worker state. |
| `docs/BADGING.md` | Confirm badges do not imply Rust qualification; add only evidence-backed status. |
| `docs/BUILD-VARIANTS.md` | Verify Rust large-disk offset/format and architecture selection. |
| `docs/CI.md` | Add per-role native test, scan, SBOM and fail-closed gate descriptions. |
| `docs/CONFIGURATION.md` | Map Rust flags, data path, security file, role allowlist and defaults. |
| `docs/CYBER-CONTROLS.md` | Reassess SRG applicability/control ownership for new processes. |
| `docs/FUNCTIONAL-TEST-PLAN.md` | Add Go/Rust differential, worker, topology and fault cases. |
| `docs/GO-VULNERABILITY-TRIAGE.md` | Keep Go scope precise; cross-link separate Rust crate/advisory triage. |
| `docs/HARDENING-CRITERIA.md` | Assess each criterion against both binaries and new worker boundary. |
| `docs/HERMETIC-BUILD.md` | Describe multi-binary verified input and no-network assembly. |
| `docs/ICEBERG.md` | Distinguish Lakekeeper path from optional worker/catalog jobs. |
| `docs/L1-REQ.md` | Add or revise top-level requirements only where scope warrants. |
| `docs/L2-REQ.md` | Decompose Rust volume and worker security/behavior requirements. |
| `docs/L3-REQ.md` | Add testable binary, runtime, protocol and negative assertions. |
| `docs/LOGGING.md` | Assess Rust log format, IDs, secrets, audit and worker telemetry. |
| `docs/QUALIFICATION.md` | Bind evidence to executable, mode, version, architecture and topology. |
| `docs/RELEASE.md` | Require exact per-arch binary inventory, scans and signed candidate evidence. |
| `docs/SCORECARD.md` | Check whether new source/dependency process affects existing findings. |
| `docs/STANDALONE.md` | State mini remains Go and worker is not enabled by its listener. |
| `docs/STORAGE.md` | Cover Go/Rust format interoperability, fsync, replication and migrations. |
| `docs/SUPPORT.md` | Classify packaged versus qualified Rust volume/worker separately. |
| `docs/THREAT-MODEL.md` | Add Rust volume and admin/worker assets, threats and residual risks. |
| `docs/TLS.md` | Compare Rust/Go crypto and negative mTLS/JWT behaviors. |
| `docs/TRACE-MATRIX.md` | Regenerate and check trace links after requirements change. |
| `docs/USE-CASES.md` | State which use cases need or exclude Rust implementations. |
| `docs/VERSION.md` | Decide whether a Rust binary change is a new image revision/candidate. |
| `docs/RUST-ALTERNATIVES-PLAN.md` | Close each gate and replace hypotheses with evidence/decisions. |
| `.github/pull_request_template.md` | Ask for role scope, native Rust evidence, findings and document-review disposition. |

Also review `.github` issue templates, workflows, test instructions,
Compose examples, artifact-lock schema, and the diagram links whenever their
interfaces change; they are not exempt because they are not Markdown guides.

## Release gate

Before a Rust mode is claimed as supported: provenance/admission and native
runtime proof exist for both architectures; vulnerability and cyber findings
are dispositioned under the established policy; all required negative tests
pass; the applicable real-host topology is qualified; documentation and SVGs
match measured behavior; and the immutable candidate's per-architecture SBOM,
scan, attestation and signature bind to the published digest. A worker/admin
scope expansion needs an explicit support and cyber-review decision. If those
gates cannot close before the first release, retain the Go profile and classify
Rust as development-only or keep its binaries out of the release candidate,
with the exact choice recorded before publication.
