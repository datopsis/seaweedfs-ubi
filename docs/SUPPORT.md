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

## Deployment profiles

One image ships two profiles. They are the same bytes — the same `weed` binary,
the same layers, the same digest — and differ only in which role the container
starts and what this project claims about it.

| | **Production profile** | **Standalone profile** |
| --- | --- | --- |
| Shape | `master`, `volume`, `filer`, and `s3` each in its own container | all roles in one container |
| Invocation | one role per container | `server` with an explicit data directory and `-s3` |
| Enabled by | the default | setting `SEAWEEDFS_UBI_STANDALONE` explicitly |
| Intended for | real deployments, including a single host | local development, small local use, and test fixtures |
| Support intent | the first-release boundary | **never supported for production** |

The standalone profile exists because a single container is a genuinely useful
local object store, in the same way `minio server /data` is, and refusing to ship
one would have denied that use case while making nothing safer.

### What the standalone profile cannot provide

These are not gaps to be closed later. They are consequences of running one
process, and no amount of configuration changes them.

| Limitation | Why |
| --- | --- |
| **Inter-component security is inert** | gRPC mTLS and volume read and write JWTs authenticate and encrypt the network between roles. Inside one process there is no such network. A `security.toml` here protects nothing. |
| **No replication, so no durability** | One volume server cannot satisfy a replication setting. Loss of the disk is loss of the data. |
| **No component failure modes** | You cannot stop the filer and observe S3 degrade, or lose a volume server and watch the master reassign. |
| **Discovery and addressing are untested** | Roles find each other in-process, so the inter-role wiring, gRPC addressing, and name resolution never execute — which is the class of defect most likely to appear first on a real deployment. |
| **No per-role isolation or tuning** | A defect in the S3 API shares a process with the volume server holding raw bytes, and all roles share one container's limits. |

Everything else behaves the same, because it is the same binary: non-root
operation, read-only root filesystem, dropped capabilities, the entrypoint
guards, S3 authentication, the S3 API itself, and the on-disk format.

### Which profile a test may use

The rule follows directly from the table above, and
[release qualification](QUALIFICATION.md#scope-rules-specific-to-a-distributed-system)
enforces it by requiring every recorded result to name its topology.

- **Standalone is valid for** functional S3 behavior, the Apache Iceberg round
  trip, version checks, the entrypoint guards and their negative cases, and the
  restricted-runtime assertions. It is the fast fixture and should be the default
  for these.
- **The separated-role fixture is required for** inter-component security,
  replication and durability, component failure modes, inter-role discovery, and
  anything else whose subject is the topology rather than the object store.

A standalone result may never be cited as evidence for a clustered claim.

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
| Single-container standalone profile | Unsupported for production, by design | Planned for local development and test fixtures behind an explicit `SEAWEEDFS_UBI_STANDALONE` opt-in. Inter-component mTLS and JWTs are inert inside one process, and replication, component failure modes, and inter-role discovery cannot be exercised. See [deployment profiles](#deployment-profiles). |
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

## Who this image is for

The first release is scoped to **the Datopsis analytical stack's S3 backend**:
the object storage layer beneath an Apache Iceberg catalog, replacing the
unhardened SeaweedFS fixture that
[`lakekeeper-ubi`](https://github.com/datopsis/lakekeeper-ubi) uses for storage
testing today. The standalone profile makes that a single-container drop-in for
lakekeeper's functional storage tests, while its inter-component security,
replication, and failure-mode tests need the separated-role fixture. See
[deployment profiles](#deployment-profiles).

That scope was chosen over a general-purpose hardened S3 store for one reason
that is worth stating carefully, because it sounds like a limitation and mostly
is not: **the difference between the two is what gets qualified, not what the
image can do.**

The image contains stock upstream SeaweedFS. This project adds no patch, no fork,
and no application-specific code — only a hardened runtime, an entrypoint that
refuses unsafe configurations, verified build inputs, and evidence. Nothing about
serving this organization's Iceberg workload makes the image worse at general S3
work, and a general-purpose scope can be adopted later by adding qualification
rather than by changing the product.

### Where the two scopes actually diverge

Five choices differ between them. Four are "this project tests and claims less",
which a later package can extend. One is baked into the image and cannot be.

| # | Choice | Effect on a general S3 consumer | Reversible later? |
| --- | --- | --- | --- |
| 1 | **Filer metadata backend.** One backend is qualified; the plain build compiles in PostgreSQL, MySQL, Redis, MongoDB, etcd, Cassandra, HBase, ArangoDB, FoundationDB, and embedded LevelDB. | An unqualified backend still functions; it is simply unsupported and untested. Someone wanting single-node embedded LevelDB with no external database is not blocked, just unqualified. | Yes — add qualification |
| 2 | **Anonymous read access is not supported.** The fail-closed guard refuses an S3 gateway with no identity source. | Real friction. A legitimate general use case — public datasets, public static assets — must consciously set `SEAWEEDFS_UBI_REQUIRE_S3_AUTH=false` to get upstream's behavior. The guard exists because the upstream default is allow-all *anonymous write*, not merely anonymous read, and the two are not separable in upstream's default. | Yes — a narrower guard could distinguish read from write |
| 3 | **The embedded Iceberg REST Catalog and Lance Namespace listeners are disabled.** | Irrelevant to general S3 use. A removal only for someone who specifically wanted SeaweedFS's own Iceberg catalog rather than a separate one, and that path needs an explicit opt-in. | Yes — opt-in exists by design |
| 4 | **Qualified S3 operation coverage.** What Iceberg engines use: put, get, head, delete, list, multipart. | Versioning, lifecycle rules, object tagging, ACLs, presigned URLs, CORS, and conditional writes would be unqualified. Unqualified is not broken — upstream implements much of this — but it is unclaimed, and any S3 behavioral difference in those areas would be undiscovered. | Yes — add qualification |
| 5 | **The `large_disk` build variant.** | This is the one constraint that is genuinely baked in. It suits large objects, and a consumer storing billions of small files would prefer the default build's narrower index entries. Changing it means a different image and a data migration. See [build variants](BUILD-VARIANTS.md). | **No** — compile-time |

### The rule this implies

Because item 5 is the only irreversible one, and items 1 through 4 are
qualification scope rather than capability, the operating rule for every later
package is:

> Narrow what this project *claims* to the analytical-stack use case freely.
> Never narrow what the image *can do* to that use case.

Concretely: no Iceberg-specific or Datopsis-specific code, configuration
hardcoding, or removed capability may enter the image to serve this scope. If a
choice would foreclose general S3 use rather than merely leave it unqualified, it
needs the same explicit decision and reasoning the build variant received.

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
