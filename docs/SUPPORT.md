# Support contract

No supported container image has been released, and no image has been built from
this repository yet. Everything currently here is development material unless an
immutable release and its evidence are explicitly named by a published support
statement.

## Classification terms

- **Supported** means an exact immutable image digest, architecture, role
  profile, configuration profile, host and runtime combination, and support
  period passed the documented release gates and is named by a published support
  statement.
- **Compatible** means limited tests demonstrated a behavior, but the project
  makes no production-support or security-maintenance commitment for that
  combination.
- **Preview/unqualified** means material is available for evaluation while
  required tests, operational guidance, or review remain incomplete.
- **Unsupported** means the project does not intend to qualify or maintain the
  behavior within the stated release boundary.

Absence from a matrix means unqualified, not implicitly compatible. A source
revision, locally built image, pull-request artifact, or successful CI run is not
a supported release.

## Current development matrix

| Area | Current classification | Evidence or limitation |
| --- | --- | --- |
| Published images | Unsupported | No release has been published. |
| Repository development image | Unsupported | No image exists yet; the first lands in work package 3. |
| Native Linux AMD64 and ARM64 | Unsupported | No build, test, SBOM, or scan evidence exists. |
| Rootless Podman | Unsupported | Intended primary workflow; nothing exercised. |
| Docker | Unsupported | To be qualified independently of Podman in work package 7. |
| OpenShift arbitrary UID | Unsupported | Restricted-SCC behavior is a work package 7 preview target. |
| `master`, `volume`, `filer`, `s3` roles | Unsupported | In the proposed first-release boundary; unimplemented. |
| Single-container `server` profile | Unsupported | Its status is an open decision, recorded below. |
| S3 API compatibility | Unsupported | No conformance claim will be made without recorded per-operation results. |
| Client-facing TLS on the S3 listener | Unsupported | Planned in work package 4. |
| gRPC mTLS and volume JWTs between components | Unsupported | Planned in work package 4; upstream requires an operator-supplied `security.toml`. |
| Durability, replication, and failure behavior | Unsupported | Cluster properties; a single-container result will never establish them. |
| Backup and restore | Unsupported | Procedures for master metadata, filer metadata, and volume data are planned in work package 4. |
| Upstream version upgrade and rollback | Unsupported | Requires on-disk format and filer schema qualification per increment. |
| FUSE mounting (`weed mount`) | Unsupported | Requires device access and privileges the hardened runtime refuses. |
| Embedded Iceberg REST Catalog and Lance Namespace | Unsupported | Disabled by this image; `lakekeeper-ubi` owns the catalog role. |
| WebDAV, message broker and queue, admin and worker roles | Unsupported | No first-release use case. |
| Advanced IAM, STS, and credential vending | Unsupported | A wider trust model than static identities; deferred. |
| Erasure coding, remote tiering, cross-datacenter replication | Unsupported | May be documented as unqualified; not qualified for v1. |
| FIPS validation or approved mode | Unsupported | No cryptographic module or operational boundary has been validated. |
| STIG certification or system compliance | Unsupported | Tailored SCAP evidence will be report-only and bounded to selected image-filesystem checks. |

Every row is `Unsupported` today because no image exists. Rows move to
preview/unqualified, compatible, or supported only when their work package lands
evidence of matching scope.

## Upstream maintenance constrains what this project can promise

This is the most consequential difference between `seaweedfs-ubi` and the sibling
projects, and it has to be stated before any support period can be defined.

Upstream SeaweedFS publishes releases roughly every seven to ten days in a single
linear line — thirty consecutive increments with no patch release on any older
line — and its security policy states that **security fixes land in the latest
release**, with issues that reproduce only on older versions ineligible for a fix
or an advisory.

Three consequences follow, and none of them can be engineered away downstream:

1. **There is no maintained older version to pin to.** Unlike PostgreSQL, which
   publishes a maintained major line with a known end date, SeaweedFS offers no
   backport target. A security fix means a new upstream version.
2. **Security maintenance therefore means rolling forward.** This project cannot
   offer to patch a pinned older SeaweedFS version, because upstream does not
   produce the fix to package. Any support statement that implied otherwise would
   be false.
3. **Qualification depth and update latency are in direct tension.** The
   qualification a hardened image owes each increment — re-verifying asserted
   upstream behavior, re-measuring binary linkage, re-running both architectures,
   checking for new default listeners and on-disk format changes — cannot be
   completed within days, every week, indefinitely. A project that promised both
   would silently drop one.

Resolving that tension is a decision for a human, recorded in
[the work plan](README.md#decisions-that-need-a-human). Until it is resolved,
this document defines no update cadence and no security-response target. The
honest options are a defined qualification lag with a stated exposure window, a
selective adoption policy that skips increments without relevant fixes, or a
narrower support promise — and each has a real cost that the person accountable
for it should choose knowingly.

## Proposed first-release boundary

> [!IMPORTANT]
> This boundary is a **proposal awaiting approval**. It is the one item of work
> package 1 that implementation cannot settle. Nothing below is a commitment
> until it is approved and this notice is removed.

The first release would qualify:

- one reviewed SeaweedFS release on UBI 9, with one reviewed asset variant;
- native `linux/amd64` and `linux/arm64` images;
- an exact rootless Podman, RHEL 9, SELinux-enforcing, cgroup-v2 baseline;
- the `master`, `volume`, `filer`, and `s3` roles as separate containers;
- S3 object storage with configured static identities and anonymous access
  refused;
- an operator-mounted TLS profile on the S3 listener;
- gRPC mTLS and volume read and write JWTs between components, with tested
  examples;
- explicitly declared writable volumes for master metadata, volume data, and
  filer store data, on a read-only root filesystem;
- the Apache Iceberg storage path exercised end to end against
  [`lakekeeper-ubi`](https://github.com/datopsis/lakekeeper-ubi);
- logical backup and restoration of master metadata, filer metadata, and volume
  data;
- verified connected and controlled-network acquisition and deployment
  procedures;
- digest-pinned deployment from immutable GHCR release tags; and
- tailored, explicitly bounded image-filesystem security evidence.

Docker would remain a separately recorded compatibility claim. OpenShift would
remain preview/unqualified unless an exact release passes the restricted-SCC
procedure before the candidate is frozen.

The image will not claim Red Hat support for SeaweedFS or for this assembled
community image. Red Hat support, where a customer is eligible, is limited by the
Red Hat container support policy to covered Red Hat platform and UBI components.
Passing scans, using UBI, or producing SCAP results does not make the image FIPS
validated, STIG certified, or system-authorized.

## Ownership boundary

**The image project owns** verified build inputs, image userspace, the supported
role set, non-root defaults, the entrypoint and its guards, declared writable
paths and listeners, tests, release metadata, SBOM, provenance, signatures, and
image vulnerability response.

**The host or orchestrator owns** the kernel, container runtime, namespaces,
cgroups, seccomp, SELinux or AppArmor enforcement, network policy, firewall and
ingress, DNS, secrets delivery, certificate and trust material, persistent
storage, backup destinations, monitoring, log retention, time synchronization,
node vulnerability management, and decommissioning.

**The storage operator owns** the cluster topology and its replication settings,
S3 identities and their permissions, bucket layout and data classification,
the `security.toml` that authenticates and encrypts the paths between components,
network segmentation of the master, volume, and filer listeners, capacity
planning, volume growth and compaction, backup policy and *successful
restoration*, upgrade approval, and incident integration.

Two boundary statements deserve emphasis because a distributed storage system
makes them easy to get wrong:

- **Most of the security surface is between the components, and it belongs to the
  operator.** The image can ship the guards, examples, and tests; it cannot
  supply the certificates or enforce the network boundary.
- **A replicated volume is not a backup, and neither is a persistent volume.**
  Replication protects against a lost disk. It does not protect against a deleted
  bucket, a corrupted write, or a bad upgrade.

## Support lifetime

No support period is defined yet, because defining one requires the cadence
decision above.

When it is defined, each immutable Datopsis release will be supported from its
public support announcement until the earliest of:

- a stated interval after a qualified successor is announced;
- withdrawal for a security, integrity, licensing, or distribution issue; or
- loss of a required upstream input or support basis that cannot be replaced.

Because upstream fixes only the latest release, an older Datopsis release can
receive packaging and UBI corrections but **cannot** receive a SeaweedFS security
fix that upstream has not published for that version. That limitation must appear
in every release support statement, not only here.

End-of-support dates are recorded in each release's support statement and
qualification record.

## Reporting

Security concerns follow the private process in [SECURITY.md](../SECURITY.md) and
must never appear in a public issue. Upstream asks for the same detail this
project's bug template collects — which components are running, which ports an
attacker can reach, what authentication is enabled, and which trust boundary is
crossed — so a report prepared for one is usable for the other.

## References

- [SeaweedFS security policy](https://github.com/seaweedfs/seaweedfs/blob/master/SECURITY.md)
- [SeaweedFS releases](https://github.com/seaweedfs/seaweedfs/releases)
- [Red Hat container support policy](https://access.redhat.com/articles/2726611)
- [Red Hat Enterprise Linux life cycle](https://access.redhat.com/support/policy/updates/errata)
