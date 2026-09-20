# Functional qualification plan

Status: plan only. No AWS resources, credentials, workflow, or release evidence
are created here. This is an execution design, not an S3 conformance claim.

## Release boundary

The first-release gates in the [work plan](README.md) and
[qualification ledger](QUALIFICATION.md) remain binding: the Iceberg path,
selected filer backend and durability claim, real-host multi-host failures,
native architectures, negative security cases, upgrade/rollback, and exact
release-candidate evidence cannot be replaced by local tests or deferred
merely because a larger suite is planned. Any excluded feature needs an
approved support classification and cannot be claimed. An unresolved security
requirement or failed gate is not waived by this plan.

The expanded suite is a coverage goal. Long-running soak, scale, broad client
compatibility, and unselected backends may follow release only if excluded
from first-release claims and accepted by the cyber reviewer. Record the
minimum and exclusions before qualification.

| Stage | Environment | Purpose | Release relationship |
| --- | --- | --- | --- |
| F0 | Native AMD64/ARM64 CI, separated roles on one host | Fast API, security, lifecycle and backup regressions | Development gate; never multi-host evidence |
| F1 | Exact RHEL 9/Podman/SELinux hosts, separated roles across hosts | Platform, failure, security and durability claims | Required for claimed production profile |
| F2 | Ephemeral AWS environment, if approved | Repeat F1 on disposable multi-AZ hosts; expand client, fault, soak and scale matrix | Optional infrastructure choice; only executed evidence counts |

F1 may use owned hosts or AWS EC2. If no suitable hosts exist, provision the
smallest approved F2 subset meeting F1. Run AMD64 and ARM64 natively and
separately; neither a single-container test nor Ubuntu CI closes F1.

## Case catalogue

Each accepted case becomes an executable test or repeatable manual procedure
with a stable ID, explicit assertions, timeout, cleanup, topology and evidence.
The first-release column combines existing work-plan obligations and proposed
coverage additions; review and classify each addition before making it a new
release gate. Existing obligations do not become optional during that review.

| Group | First-release cases to add or extend | Expanded cases; scope decision required |
| --- | --- | --- |
| S3-API | Two identities and anonymous denial; bucket/object create, head, list, read, delete; range and conditional reads; errors; multipart initiate, parts, list, complete, abort and byte-exact readback; selected clients over TLS | Versioning, tagging, metadata, checksums, copy, presigned URLs, streaming signatures, large objects, pagination, concurrency; classify unsupported semantics |
| ICE | Pin `lakekeeper-ubi` digest and one query engine/client; create namespace/table, write files, read rows, update metadata, restart components and read again; negative credentials and unavailable S3 | Schema/partition evolution, snapshots, concurrent writers, larger data, more engine versions; the embedded Iceberg catalog remains unsupported |
| SEC | Non-root, zero capabilities, read-only root and explicit data mounts for every role; wrong secret, cross-tenant access, untrusted TLS/gRPC certificates, absent/invalid volume-write JWT, extra-listener absence, and key exclusion from logs/layers | Rotation under load, expired certificates, malformed requests, bounded protocol fuzzing |
| DAT | Acknowledged writes through restart/replacement; cold backup/restore; chosen replica placement and read/write behavior after a host/volume loss; recovery limits | AZ failure, repeated partitions, disk/inode exhaustion, partial writes, restore on replacement hosts, soak |
| OPS | Master/filer/S3 loss and reconnect, readiness, logging/metrics, bounded startup/shutdown, upgrade and rollback across the chosen version pair | Restart cycles, latency/throughput, capacity trends; no performance SLA without separate evidence |
| DEV | In a disposable `mini` fixture, byte-exact authenticated object readback after container replacement with the same named `/data` volume and external identity source; safe `weed shell` administration and measured restart semantics | Configuration/credential rotation scenarios after the basic persistence case passes; standalone results remain development-only and never qualify replication or multi-node recovery |

Existing `tests/s3.sh` and `tests/lib/s3client.py` cover a subset of S3-API.
`tests/replication.sh` covers logical racks on one host, not host or AZ loss.
`tests/state-survival.sh` covers container lifecycle with intact storage.
`tests/mini-persistence.sh` reaches the DEV functional cases locally but its
strict access-key-ID log assertion fails after a removed identity is denied;
it is not passing qualification evidence or a native CI case yet.
Inventory actual assertions before adding cases. Select at least two
independent S3 clients for a compatibility claim and record their versions.
Define expectations from the chosen SeaweedFS version and supported subset,
not blanket AWS S3 conformance. Upstream 4.46 does not support volume-read
JWTs alongside the filer; the security case tests the configured write JWT and
records that residual boundary instead of claiming both directions.

## Candidate matrix and evidence

Freeze image index and architecture digests, artifact-lock digest, SeaweedFS
and UBI versions, filer backend/version, replication setting and actual
host/AZ placement, RHEL/Podman/SELinux/cgroup/storage stack, TLS/security
profile digest, client versions, fault method and recovery timeout. Review
version-specific replication semantics before choosing placement; replica
count alone says nothing about failure domains. Keep standalone, one-host
separated and multi-host results separate.

For each case retain procedure revision, UTC times, expected/actual result,
sanitized logs/metrics, topology map, architecture, digest, configuration,
failure-injection record, cleanup result, durable evidence URL, limitations,
owner and reviewer. Feed release-candidate results into
[`docs/QUALIFICATION.md`](QUALIFICATION.md). Failed and skipped cases stay
visible. Do not commit credentials, raw private logs, objects, scan caches or
volumes. A trace link is not a passing result.

## Optional AWS execution design (not provisioned)

1. Obtain owner approval for account, region, AZ count, RHEL 9 AMI/license,
   AMD64/ARM64 instance families, storage size/IOPS, run duration, cost ceiling,
   retention and who may run/destroy. Price the exact BOM, including endpoints
   and network charges, immediately before approval. Prefer a dedicated test
   account.
2. Review version-pinned IaC separately. Create private subnets across chosen
   AZs, narrow security groups, encrypted per-node EBS volumes and needed VPC
   endpoints. An EBS volume attaches only within its AZ
   ([AWS EBS](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-attaching-volume.html));
   it is not cross-AZ shared storage. Use private Systems Manager access, not
   public SSH; SSM needs no inbound management port and supports private
   endpoints ([AWS SSM](https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-create-vpc.html)).
3. Require IMDSv2 or disable metadata where feasible
   ([AWS EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-IMDS-new-instances.html)),
   encrypt volumes/logs, use synthetic data, least-privilege roles and limited
   egress. If GitHub Actions starts the stack, use a protected environment and
   short-lived OIDC role constrained to this repository/ref, not stored AWS
   keys ([AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html)).
4. Apply TTL/run-ID tags, maximum run duration, quotas, a budget alert and an
   independent orphan-resource check. Budget alerts are not real-time kill
   switches. Verify teardown after success, failure and cancellation; retain
   only sanitized evidence and a final resource/cost inventory.
5. Pull and verify the exact signed candidate digest on each native host.
   Deploy distinct master, volume, filer and S3 roles with production
   restrictions and the selected metadata backend. Place replicas on distinct
   hosts/AZs. Induce controlled process, host and network faults; restore,
   reconcile object bytes, metadata and replica placement, and label each loss
   as host-local, storage-local or AZ-level.

Do not provision until first-release support/durability and filer-backend
decisions, IaC and threat-model review, cost approval and teardown rehearsal
are complete. The next implementation slice is the pinned Iceberg path and
case IDs/fixtures; AWS provisioning comes later.
