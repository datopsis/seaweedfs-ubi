# Go-core and Rust worker adoption plan

Status: plan and preliminary research, 2026-09-19. No Rust binary has been
admitted, no Rust role is enabled, and no Rust behavior or security property is
qualified. This plan does not change the first-release boundary or waive any
existing gate in the [work plan](README.md).

## Decision and scope

The direction after the initial plan is **keep the core production image Go-only**.
Continue to use `weed volume`; do not package or enable `weed-volume` in that
image. Rust volume substitution is deferred research, not a first-release
candidate. Explore `weed-worker` in a **separate, worker-only UBI image**. The
worker image does not need the `weed` executable; the Go admin scheduler it
depends on runs in a different container. Treat **packaged**, **launchable for
development**, and **supported for production** as separate decisions. This
direction supersedes the earlier same-image/two-Rust-binary proposal.

The current first-release S3 topology is `master` + Go `volume` + `filer` +
`s3`. A Rust worker requires a separately designed Go admin/plugin scheduler,
SeaweedFS Lance Namespace endpoint, access to table objects, and privileges to
change durable table data. Our Go image currently refuses the admin role and
disables its embedded Lance listener; Lakekeeper's Iceberg catalog is not an
assumed replacement for the worker's Lance Namespace API. The worker does
**not** become part of the production profile because a worker image is built.
Keep admin, Lance, and worker operation outside the support boundary until
their trust boundaries are approved and tested. The separate worker image has
its own digest, SBOM, scans, attestations, signature, and support statement.

`mini` stays the Go implementation in one process. Its existing worker gRPC
listener is not a qualified production admin deployment. Do not launch a Rust
executable implicitly, re-enable WebDAV/Admin UI, or treat mini evidence as
worker, replication, or multi-node evidence.
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

1. **Scope and acquisition design.** Record the Go-only core/worker-only image
   split and admin/Lance trust boundary in an ADR. Inventory `weed-worker` from
   the signed upstream image for native AMD64/ARM64: SHA-256, size, embedded
   version/commit, ELF interpreter, shared libraries, licenses, and exact
   source-to-prebuilt-to-image chain. Check it actually runs on UBI Micro;
   Alpine execution is not UBI compatibility evidence. Add a separate reviewed
   worker lock and fail-closed admission tests for absent, zero-byte,
   wrong-architecture, mismatched, or substituted input. Keep digest + cosign
   identity verification before extraction; tarball MD5 and locally recorded
   hashes are not publisher verification. Exit: verified worker input without
   changing the Go core image or its role allowlist.
2. **Build a separate worker image.** Use only admitted `weed-worker`, required
   runtime libraries and CA trust, and a narrowly scoped entrypoint; do not copy
   `weed` or `weed-volume`. Preserve non-root, read-only-root compatibility,
   explicit writable paths, no capabilities, and package-manager-free final
   runtime. Verify the worker runs as PID 1, has no unintended listeners, and
   fails closed on missing admin/namespace/security configuration. Measure
   compressed and unpacked size on both architectures. Give this distinct image
   its own SBOM, scan, attestation, signature and release admission.
3. **Go admin and Lance integration.** Design and separately qualify the Go
   admin role, its persistent state and restricted HTTP/gRPC listeners; do not
   use mini's admin listener as production evidence. Decide how the Go S3
   process exposes Lance Namespace without weakening S3 authentication or
   accidentally enabling the embedded Iceberg catalog. Verify the worker's
   exact Lance Namespace API and credential-vending assumptions; do not assume
   Lakekeeper is drop-in compatible. Update network policy, TLS/mTLS, identity,
   authorization, secret rotation, logging and fail-closed startup guards.
4. **Rust worker characterization.** Map actual 4.46 jobs and all admin,
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
   for the worker/admin/Lance paths. Add Rust dependency inventory from the *exact* upstream
   commit/Cargo.lock alongside binary/image SBOMs; evaluate RustSec, GitHub
   advisories, OSV and current image scanners, recording where binary scanners
   cannot see crates. Track each potential advisory with component, affected
   version, reachability, fix status, mitigation, owner, expiry and dashboard
   link; do not suppress unresolved findings to pass a gate. Assess Go admin
   and Rust worker TLS, crypto modules and FIPS boundary; **make no FIPS
   claim**. Review HTTP/gRPC authorization, SSRF, path traversal,
   secret leakage, worker supply chain, catalog access and destructive
   maintenance privileges. Re-run SCAP only for image-owned
   checks; do not mistake an image scan for deployment certification.
6. **Documentation, diagrams and release decision.** Complete the file review
   below with an explicit changed/not-applicable rationale in the PR. Create
   repository-native SVGs for image/artifact provenance and the admin/worker
   control and data flow. The [proposed host diagram](diagrams/proposed-production-lance.md)
   is a starting point, not qualification. Include text equivalents and
   link/render checks. Update release candidate admission, native/platform
   matrix, signature/SBOM/attestation binding, rollback and support statements
   to name exactly which image and role combination was assessed. No release
   claim may rely on merely packaging the Rust worker.

**Deferred Rust volume track.** Preserve the preliminary `weed-volume` issue
research below as watch items. Do not add it to either planned image or first
release. Reopen its acquisition, parity, failure, security, and data-format
qualification only after a deliberate new scope decision.

## Document-by-document review ledger

At the implementation PRs, review **every row**, mark changed or no change
with a reason, and check cross-document claims. This is an inventory and likely
impact, not a claim that every file must change. Regenerate `TRACE-MATRIX.md`
with `scripts/build-trace-matrix.py`; never hand-edit the generated matrix.

| Document | Review question / likely update |
| --- | --- |
| `AGENTS.md` | Preserve all non-negotiable acquisition, role, runtime and evidence guardrails. |
| `CLAUDE.md` | Update one-binary, role, architecture and verification descriptions if bytes/roles change. |
| `README.md` | Distinguish Go core and worker-only image contents, size and support status. |
| `SECURITY.md` | Add Rust/worker attack surfaces, reporting and active findings. |
| `CONTRIBUTING.md` | Add Rust-specific build, tests, issue triage and review expectations. |
| `CHANGELOG.md` | Record each completed increment only; no unsupported capability claim. |
| `THIRD_PARTY_NOTICES.md` | Assess Rust crates, licenses, attribution and redistribution. |
| `docs/README.md` | Track increments, gates, decisions and changes to first-release boundary. |
| `docs/ARCHITECTURE.md` | Keep the Go core manifest/size; show separate worker image and admin/Lance topology. |
| `docs/ARTIFACT-ACQUISITION.md` | Record exact provenance and trust limits of the worker binary. |
| `docs/BACKUP-RESTORE.md` | Check admin/worker state and maintained table data. |
| `docs/BADGING.md` | Confirm badges do not imply Rust qualification; add only evidence-backed status. |
| `docs/BUILD-VARIANTS.md` | Confirm the Go large-disk decision is unaffected; record worker architecture availability. |
| `docs/CI.md` | Add per-role native test, scan, SBOM and fail-closed gate descriptions. |
| `docs/CONFIGURATION.md` | Map Rust flags, data path, security file, role allowlist and defaults. |
| `docs/CYBER-CONTROLS.md` | Reassess SRG applicability/control ownership for new processes. |
| `docs/FUNCTIONAL-TEST-PLAN.md` | Add admin/Lance/worker, topology and fault cases without treating mini as production. |
| `docs/GO-VULNERABILITY-TRIAGE.md` | Keep Go scope precise; cross-link separate Rust crate/advisory triage. |
| `docs/HARDENING-CRITERIA.md` | Assess each criterion against the separate worker image and admin boundary. |
| `docs/HERMETIC-BUILD.md` | Describe separate verified worker input and no-network assembly. |
| `docs/ICEBERG.md` | Distinguish Lakekeeper path from optional worker/catalog jobs. |
| `docs/L1-REQ.md` | Add or revise top-level requirements only where scope warrants. |
| `docs/L2-REQ.md` | Decompose worker/admin/Lance security and behavior requirements. |
| `docs/L3-REQ.md` | Add testable binary, runtime, protocol and negative assertions. |
| `docs/LOGGING.md` | Assess Rust log format, IDs, secrets, audit and worker telemetry. |
| `docs/QUALIFICATION.md` | Bind evidence to executable, mode, version, architecture and topology. |
| `docs/RELEASE.md` | Require exact per-arch binary inventory, scans and signed candidate evidence. |
| `docs/SCORECARD.md` | Check whether new source/dependency process affects existing findings. |
| `docs/STANDALONE.md` | State mini remains Go and worker is not enabled by its listener. |
| `docs/STORAGE.md` | Review maintained Lance table versions, cleanup and rollback; keep Go volume claims unchanged. |
| `docs/SUPPORT.md` | Keep Rust volume deferred and classify the worker image separately. |
| `docs/THREAT-MODEL.md` | Add admin/worker/Lance assets, threats and residual risks. |
| `docs/TLS.md` | Assess worker-admin mTLS and namespace/S3 TLS negatives. |
| `docs/TRACE-MATRIX.md` | Regenerate and check trace links after requirements change. |
| `docs/USE-CASES.md` | State which use cases need or exclude Rust implementations. |
| `docs/VERSION.md` | Decide whether a Rust binary change is a new image revision/candidate. |
| `docs/RUST-ALTERNATIVES-PLAN.md` | Close each gate and replace hypotheses with evidence/decisions. |
| `.github/pull_request_template.md` | Ask for role scope, native Rust evidence, findings and document-review disposition. |

Also review `.github` issue templates, workflows, test instructions,
Compose examples, artifact-lock schema, and the diagram links whenever their
interfaces change; they are not exempt because they are not Markdown guides.

## Release gate

Before the worker image is claimed as supported: provenance/admission and native
runtime proof exist for both architectures; vulnerability and cyber findings
are dispositioned under the established policy; all required negative tests
pass; the applicable real-host topology is qualified; documentation and SVGs
match measured behavior; and the immutable candidate's per-architecture SBOM,
scan, attestation and signature bind to the worker's published digest. The
admin/Lance/worker scope expansion needs an explicit support and cyber-review
decision. If those gates cannot close alongside the first Go core release,
keep the separate worker image unpublished or development-only, leave admin
and Lance excluded, and make no Lance-maintenance support claim. Do not put
Rust binaries in the Go core candidate to bypass this boundary.
