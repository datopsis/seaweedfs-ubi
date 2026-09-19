# Provisional cyber-control adoption

This is an analyst worksheet, **not** an approved hardening profile, OSCAL
component definition, SSP, assessment result, or release waiver. It applies the
current structure of [`datopsis/container-hardening`](https://github.com/datopsis/container-hardening)
to SeaweedFS while that standard is changing. No revision of the shared
workflow is pinned here, no source exclusion is approved, and no baseline
control is marked satisfied. An independent cyber reviewer must decide the
final catalogue revision, applicability, control origination, and evidence.

## Source applicability to review

The shared source register currently treats the General Purpose Operating
System (GPOS) and Container Platform SRGs as baseline inputs and the Web Server
and Application Server SRGs as conditional. The releases and digests below
identify the material examined for this *draft*; they are not a pinned or
approved standard revision. Re-evaluate them when the shared register changes.

| Source | Observed revision | Proposed treatment for this image |
| --- | --- | --- |
| [GPOS SRG](https://github.com/datopsis/container-hardening/blob/main/docs/srg/general-purpose-operating-system-srg/README.md) | V3R3; source SHA-256 `97026655bce18d91e12c9c0a9fd54288989f0b483d3b92ec615e2dc0544e6f24` | Review image-filesystem and runtime-relevant rules against UBI Micro and this image. Host login, kernel, account, and patch operations remain host handoffs; a container image cannot claim them. |
| [Container Platform SRG](https://github.com/datopsis/container-hardening/blob/main/docs/srg/container-platform-srg/README.md) | V2R4; source SHA-256 `975a9e421e62e0ea52b1824e4a719aee87eed9070d5a3145fa9817f6498d99fe` | Treat as required deployment/platform obligations. The image can demonstrate compatibility with restrictions but cannot claim to enforce admission, namespace policy, storage encryption, network policy, or host settings. |
| [Application Server SRG](https://github.com/datopsis/container-hardening/blob/main/docs/srg/application-server-srg/README.md) | V4R5; source SHA-256 `ea33d7f18f950e86c9e0cc63835cf8802d319804ac143b2020b1fbac13ff2643` | **Candidate applicable; no exclusion proposed.** SeaweedFS processes object requests, authenticates S3 identities, and exposes internal management/coordination APIs. The static-web-server rationale for excluding this SRG does not transfer. Review all 137 rules by subject and ownership. |
| [Web Server SRG](https://github.com/datopsis/container-hardening/blob/main/docs/srg/web-server-srg/README.md) | V3R3; source SHA-256 `7345e31a61c162ee4ca0253e3f44b729c18bb45b3a17cb364e5d08422412b409` | **Potentially applicable; do not exclude yet.** S3, filer, master, and volume expose HTTP(S) endpoints, but the image is an object-storage application rather than a general website/reverse proxy. Review all 102 rules to distinguish HTTP transport requirements from website/session and hosted-content assumptions. |

The source packages are not committed here. The rule text and counts above are
from the shared repository's rendered catalogues and
[`artifacts/sources.json`](https://github.com/datopsis/container-hardening/blob/main/artifacts/sources.json).
The source digests are a record of what was inspected, not an approval to keep
using that release after the register or applicability changes.

### First rule clusters to disposition

These are high-consequence examples, not a substitute for the full rule-by-rule
ledger. “Open” means neither pass nor not-applicable. The independent reviewer
must examine each source rule's actual check and fix text, not just its title.

| Rules in the observed SRGs | Why they matter here | Current disposition / owner |
| --- | --- | --- |
| Application Server `V-204712`, `V-204745`, `V-204746`, `V-204747` | S3 authorization and identity; privileged account/MFA questions depend on whether operator-supplied S3 identities are treated as application accounts and whether an administrative interface is in the supported boundary. | Open. Image project describes the guard and supported identities; deployment and cyber reviewers decide account/MFA obligations. Do not reuse the reference web server's “no accounts” determination. |
| Application Server `V-204717`–`V-204726`, `V-204828`–`V-204830` | Request, access, and identity audit requirements; some mention a management interface. | Open. Measure event coverage and fields per role and determine whether master/filer APIs are management interfaces. Log collection/retention is a deployment handoff. |
| Application Server `V-204758`, `V-204766`, `V-204812`, `V-204813`, `V-204816`, `V-204817` | Crypto module, random/session, at-rest protection, and TLS are CAT I or sensitive obligations. | Open. No FIPS validation claim; assess upstream Go crypto, deployment TLS and storage encryption separately. S3 TLS tests do not establish every internal HTTP path. |
| Application Server `V-278967` | Vendor-supported version requirement against SeaweedFS's fast, latest-only release model. | Open. Requires an approved update/support cadence and an exact supported release, not merely a pinned 4.46 binary. |
| Web Server `V-206350`–`V-206357`, `V-206390`, `V-206399`, `V-206434` | Session limits, access, logging, crypto, and TLS may reach the HTTP APIs even if website-specific wording does not. | Open pending rule-by-rule applicability and overlap analysis with Application Server SRG. |
| GPOS `V-203695`, `V-203720` and image-related filesystem/privilege rules | Privilege prevention, verified inputs, and read-only/no-package-manager behavior cross the image boundary. | Image contribution has development checks; exact candidate and host-owned portions remain open. A recorded tarball digest is not publisher signature verification. |
| Container Platform `V-233185`, `V-233224`, `V-233289`, `V-233290` | Privileged workload admission, transmitted data and crypto policy are platform/deployment obligations. | Open handoff. The platform must prove enforcement; image tests prove only that the image can run within selected restrictions. |

This review must also include object-store concerns not fully covered by any
generic SRG: direct filer/volume reads bypassing S3 identity, metadata-store
consistency, replica placement and failure domain, durable-data mount identity,
backup and restore, two-tenant authorization, access-key and JWT-key rotation,
and the risk of an upstream release changing listeners or defaults. Those are
explicit in [THREAT-MODEL.md](THREAT-MODEL.md) and must not vanish when the
generic control baseline is imported.

## NIST control origination triage

The shared High-baseline-derived model currently contains 379 control entries:
20 `image-owned`, 13 `deployment-configured`, 50 `host-inherited`, 228
`organization-inherited`, 11 `not-applicable`, and **57 `research-required`**.
Those counts are a provisional observation from the shared baseline, not a
completed SeaweedFS component definition. In particular, the 57 open entries
cannot be copied from a static web server: SeaweedFS has identities, object
authorization, mutable state, and internal APIs.

| Control(s) | Shared baseline position | SeaweedFS investigation before origination can be decided |
| --- | --- | --- |
| AC-2, IA-2, IA-5 | Research required | Separate operator-managed S3 identities, application handling of credentials, master/filer management paths, and platform/service accounts. Decide account lifecycle, identity proof, key storage, rotation, and MFA scope with the deploying organization. |
| AC-3, AC-14 | Research required | Test two-identity bucket isolation and anonymous denial; examine explicit anonymous opt-out and filer/volume bypass. The deployment chooses privileges; the image guard does not prove authorization policy. |
| AC-6, CM-7 | Image-owned starting point | Verify every role and both native architectures under non-root/no capabilities, feature allowlist, exact listeners, and no package manager. Preserve deployment handoffs for admission and networking. Do not mark met from one smoke test. |
| AU-2, AU-3, AU-10, AU-12 | Research required | Inventory per-role security events and fields, missing identity in shared-key requests, startup refusals, direct read paths, collector retention, and non-repudiation limitations. Static S3 keys do not establish an individual actor. |
| CM-6 | Research required | Enumerate upstream defaults, packaging overrides, `security.toml`, S3 identity files, filer backend, and every role flag; prove configuration drift and restart behavior. Tailored SCAP remains report-only until rule selection and review. |
| CP-9, CP-10 | Organization-inherited starting point | Image supplies documented backup/restore compatibility; the organization and deployment own backups, recovery objectives, offsite protection, and actual recovery exercises. One-host cold restore is not disaster recovery. |
| RA-5, SI-4 | Host-inherited starting point | Image project supplies full scanner inventories and metrics/logging; host and security operations own continuous monitoring and alert response. Development scans cannot satisfy release-candidate vulnerability gates. |
| SC-8, SC-8(1), SC-13 | Research required | Separate S3 TLS, gRPC mTLS, direct HTTP paths, cryptographic module provenance, FIPS claims, and approved algorithms. Internal read paths need network isolation even with gRPC mTLS. |
| SC-28, SC-28(1) | Host-inherited / deployment-configured starting points | Read-only-root compatibility does not encrypt or protect object data at rest. Assess volume, filer metadata, backup encryption, key ownership, and storage service controls. |
| SI-10, SI-11 | Research required | Test malformed S3, filer, and administrative inputs and error responses by role; do not infer upstream validation from entrypoint flag parsing. |

Every final `image-owned` row will require a SeaweedFS requirement identifier,
a required IMG criterion, a scope-matching test or assessment, and explicit
limitations. Other rows must name the deployment, host, or organization
handoff. The approved component definition must account for **every** control
in the selected baseline and be checked with the shared validator; this
worksheet does not substitute for it.

## Next review gates

1. Cyber reviewer selects the authoritative source revisions and confirms
   applicability of both conditional SRGs; record rule-by-rule inclusion,
   exclusion, handoff, and unresolved items with Group IDs.
2. Map every applicable rule through the shared crosswalk to NIST controls and
   through this image's requirements to evidence of matching role, topology,
   architecture, and candidate digest. A title match is not evidence.
3. Decide all 57 research-required control originations, resolving any
   departure from the common baseline through the shared deviation process.
4. Generate the OSCAL component definition and human-readable matrix from one
   source, validate schema and semantic checks, then obtain independent review.
5. Only after the shared workflow and source register settle, pin a reviewed
   standard revision and call it from this repository. Until then, keep this
   work explicitly provisional and the release workflow blocked.
