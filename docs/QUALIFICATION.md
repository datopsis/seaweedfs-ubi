# Release qualification evidence

No release candidate has been qualified. Native CI development images have been
built and tested, but they are not release-candidate evidence. This file defines
the evidence record that every candidate and supported release must complete.
Placeholder text, development CI, or an omitted field is not passing evidence.

## Evidence levels

- **Development** evidence is produced for a proposed revision or pull request.
- **Integration** evidence is produced for the exact revision merged to `main`.
- **Release-candidate** evidence is regenerated after the final image-affecting
  change and is bound to the exact candidate identifiers below.

Only release-candidate evidence can support a public release claim. Human review
and external-platform results must be recorded separately from automated jobs.

## Scope rules specific to a distributed system

These rules exist because SeaweedFS evidence is unusually easy to over-read.
Every recorded result must state which of them applies.

- A result from the single-container profile establishes nothing about a
  separated-role deployment, and neither establishes anything about a replicated
  one. Record the **topology** with every result.
- A result from one role says nothing about another. Record the **roles running**.
- A durability result is bound to the replication setting in effect. Record it,
  and record what the result does *not* establish.
- A result obtained with inter-component security disabled does not describe a
  deployment that enables it, and the reverse is also true. Record the
  `security.toml` state.
- An S3 result is bound to the client that produced it. One client agreeing with
  SeaweedFS does not establish conformance with the S3 API.

## Required record schema

Create one section per candidate. Every field is required; use `not applicable`
with a reviewed rationale instead of deleting a field.

### Candidate identity

| Field | Required value |
| --- | --- |
| Status | Proposed, failed, withdrawn, superseded, or released; never infer status from a tag. |
| Evidence level | Development, integration, or release-candidate. |
| Candidate/release identifier | Proposed identifier or immutable release tag. |
| Git commit | Full 40-character commit SHA and protected-main ancestry result. |
| Image index digest | Complete OCI index digest. |
| Architecture digests | Exact AMD64 and ARM64 manifest digests. |
| Artifact-lock digest | SHA-256 of the reviewed lock set and its schema version. |
| Role profile | Which roles the candidate is qualified for, and the topology of each qualifying deployment. |
| Configuration profile | Name and digest of every qualifying configuration and fixture, including the `security.toml` state. |
| Created and reviewed | UTC timestamps and reviewer identities. |
| Support period | Start, supersession date when known, and end-of-support date. |

For a future candidate, retain the raw OCI index, both architecture manifests,
both image configurations, and the result of
`scripts/lib/validate_candidate_index.py` against digests obtained independently
from the candidate registry. This validates the index-to-manifest-to-config
identity chain and platform mapping; it does not qualify layers, runtime
behavior, provenance, or the registry itself.

### Build and supplier inputs

Record the SeaweedFS release tag exactly as upstream published it, the **release
asset variant**, the archive URL, byte size, and SHA-256, the upstream-published
MD5 as a recorded value, the extracted binary size and SHA-256, the Go build
identifier, and the measured linkage facts: static or dynamic, the highest
required glibc symbol version if any, needed shared libraries, and any library
loaded at runtime rather than linked. Record the upstream release-note and
commit-range review, and the result of re-verifying every upstream behavior this
repository asserts.

Record the exact UBI references and manifest digests, the complete runtime
package closure, Red Hat errata review, and architecture. Link the
schema-validated locks and the verified acquisition result.

State explicitly, in every candidate record, that the recorded digests establish
reviewed bytes and **not** publisher identity, because upstream publishes no
signature and no SHA-256 manifest. A candidate record that omits this limitation
is incomplete.

Record every build, SBOM, scanner, signing, attestation, and SCAP tool version,
container image digest, rules and content digest, vulnerability database version
and timestamp, policy version, GitHub Actions workflow commit, and runner image.
`latest`, an unpinned action, or an unrecorded database cannot qualify a
candidate.

### Runtime and platform environment

For each claimed combination, record:

- architecture, host distribution and release, kernel, CPU, and time source;
- Podman or Docker client and server, OCI runtime, rootless mapping, cgroup
  version, seccomp profile, SELinux or AppArmor mode, and filesystem and storage
  type;
- the topology: single container, separated roles on one host, or separated roles
  across hosts, with the address and listener exposure of each role;
- the volume replication setting, volume count limit, and data directory mount
  type for every role holding durable state;
- the filer metadata store backend and its version;
- the S3 client and version used to exercise the API, and the table-format engine
  and version used to exercise the Iceberg path;
- OpenShift release, node release, SCC, namespace policy, CSI driver, and
  effective UID and GID when applicable;
- connected or controlled-network mode, registry and mirror digest mapping, trust
  anchors, and vulnerability-data age; and
- TLS library and provider versions, protocol and profile, certificate and trust
  fixture identifiers, and whether client certificates are in or out of scope.

Do not record private hostnames, credentials, access keys, JWT signing keys,
private keys, stored object contents, or sensitive environment details.

### Test and assessment results

Use one row per gate or platform result.

| Field | Required value |
| --- | --- |
| Gate | Stable test, control, or review identifier. |
| Scope | Digest, architecture, role profile, topology, configuration profile, platform, and relevant input versions. |
| Method | Automated test, examine, interview, manual procedure, or external-platform exercise. |
| Result | Pass, fail, not applicable, blocked, or accepted risk. |
| Evidence | Durable URL, release asset, signed attestation, or repository path plus content digest. |
| Tool/input metadata | Exact tool and database or content versions and timestamps. |
| Limitations | What the result does not establish. |
| Owner and reviewer | Accountable owner plus independent reviewer when required. |
| Executed/reviewed | UTC dates. |
| Valid until | Expiry or invalidation trigger. |

At minimum, results must cover:

- hermetic acquisition and assembly, including the negative cases for a tampered
  archive, a tampered binary, a wrong version, a truncated download, and a
  missing lock entry;
- native AMD64 and ARM64 runtime behavior for every supported role;
- non-root and arbitrary-UID operation, zero capabilities,
  `no-new-privileges`, and a read-only root filesystem with only the declared
  writable volumes;
- the reported server version matching the locked upstream version;
- the supported-role allowlist refusing an unsupported subcommand;
- authenticated S3 access succeeding **and** anonymous access being refused, with
  the fail-closed guard's negative case exercised directly;
- the explicit-data-directory guard refusing an unset or temporary data
  directory;
- the Iceberg REST Catalog and Lance Namespace listeners being absent by default;
- identity isolation between two S3 identities with distinct buckets;
- gRPC mTLS refusing a client without a valid certificate, a direct volume
  write without a JWT being refused, and direct filer/volume read paths being
  blocked from client networks by the qualified deployment;
- data written through the S3 API surviving container replacement, restart, and
  an unclean stop, with no acknowledged write lost on graceful shutdown;
- the Iceberg storage path exercised end to end against a real catalog;
- resource-exhaustion behavior failing visibly rather than silently;
- backup and restoration of master metadata, filer metadata, and volume data,
  verified by a restore into a replacement deployment;
- the upgrade and rollback path across an upstream increment, including any
  on-disk format or filer schema change;
- secrets absent from logs, error bodies, and image layers;
- complete SBOM and license review, and Trivy and Grype triage;
- provenance, signature, and attestation verification;
- rootless RHEL Podman, Docker compatibility, controlled-network operation, and
  the selected OpenShift status;
- tailored SCAP results with their selections and exclusions;
- repository settings and protection rules; and
- a documentation rehearsal proving the published procedures work as written.

### Findings, exceptions, and residual risk

Record every fixed and unfixed finding, scanner disagreement, failed or
not-applicable control, unsupported claim, and accepted residual risk. Each entry
includes exact digest and architecture, advisory, control or threat ID, component,
vendor status, exposure and reachability, decision, rationale, compensating
control, owner, approver, decision date, expiry, and rescan or reassessment
trigger.

Findings against the Go module inventory of the `weed` binary must record whether
the affected code path is reachable in the supported role set, and must not be
assumed exploitable in this packaging merely because the module is present.

Two residual risks are structural rather than incidental and must be restated in
every candidate record until they change:

1. **Upstream provenance.** Release assets carry only an MD5 sidecar. The lock
   proves reviewed bytes, not publisher identity.
2. **Upstream maintenance.** Security fixes land only in the latest upstream
   release, so a supported older release cannot receive an upstream SeaweedFS
   security fix. See [the support contract](SUPPORT.md).

An empty findings section must state who reviewed the complete outputs and where
they are retained. A zero exit code or empty SARIF file is not a human triage
record.

### Approval and publication

Record:

- security and release reviewers and their decision;
- required checks and protected-main and ruleset verification;
- failed-candidate or prior-digest disposition;
- public GHCR index digest and immutable tags;
- Cosign issuer, identity, and digest verification, and bundle location;
- SBOM, provenance, attestation, scan, lock, source, license, and support links;
- published limitations, accepted risks, rollback path, security contact, and
  incident and release contacts; and
- post-publication verification on native AMD64 and ARM64, performed against the
  published image rather than a local build.

The image index, architecture manifests, GitHub Release, support statement, SBOM,
provenance, signatures, attestations, and this ledger must identify the same
approved commit and artifact.

## Invalidation and retention

Every record lists its invalidation triggers. At minimum, changing the SeaweedFS
version or asset variant, the UBI inputs, the package closure, image contents,
the entrypoint or its guards, the supported role set, the default listeners, the
runtime behavior, the storage or TLS defaults, the release workflow, the scanner
database, the SCAP content or tailoring, the qualification procedure, or a claimed
platform invalidates the affected candidate evidence.

Because upstream releases roughly weekly and each increment is a qualification
event, candidate evidence has a short useful life by construction. Record the
upstream version the evidence was produced against and treat a newer upstream
release as an invalidation trigger for any claim that implies currency.

Historical evidence remains labeled and available for comparison but cannot be
silently reused. Durable release evidence must not depend only on expiring
workflow artifacts.
