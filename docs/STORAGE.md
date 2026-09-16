# Storage, state survival, and durability boundaries

This image makes persistent paths explicit. It does not make a single copy of
data durable, choose a replication policy, or turn container volumes into a
backup system.

## What is qualified

`tests/state-survival.sh` runs `master`, `volume`, `filer`, and `s3` as four
separate restricted containers. Master metadata, volume data, and filer metadata
each use a distinct named volume. The S3 gateway has no writable volume.

The suite writes and reads an object before treating it as acknowledged, then
confirms byte-for-byte recovery after:

- an ordinary restart of every role;
- graceful shutdown followed by replacement of every container; and
- an unclean stop followed by replacement of every container.

The containers are genuinely replaced, but the same named volumes remain. This
is evidence that state is stored in the declared persistent paths and can be
reopened after those lifecycle events.

`tests/replication.sh` adds a second, deliberately separate topology. Two volume
servers run in distinct logical racks in one data center, and the master selects
replication `010`. The suite does not infer placement from configuration: it
gets the written object's file ID from filer metadata, requires the master's
lookup to name both volume servers, and reads the expected bytes directly from
both replicas.

After one volume-server process stops, the acknowledged object remains readable
through S3 and directly from the surviving replica. A new write is refused while
the second required rack is absent instead of being acknowledged with only one
available copy. This qualifies the measured one-host process-loss behavior of
that exact topology.

## What that does not prove

The state-survival fixture has one volume server and keeps its underlying
storage throughout. The replication fixture has two volume servers but places
both containers and both named volumes on the same host. Together they provide
**no evidence** for:

- survival after loss or corruption of a volume, disk, host, or storage backend;
- host, node, disk, storage-backend, or availability-zone loss;
- quorum behavior, master high availability, or cross-host failover;
- crash consistency under every possible timing or partial-write condition;
- backup correctness, point-in-time recovery, or disaster recovery; or
- a multi-node topology.

An unclean-stop pass means only that the acknowledged objects in that measured
run survived process termination while their storage remained intact. The
replication pass means only that two copies were measured across logical racks
and one remained available after a volume process stopped. Neither result may be
presented as multi-node or physical-storage durability evidence.

## State ownership

| Role | Persistent state | Required path in the qualified fixture |
| --- | --- | --- |
| `master` | topology and volume-assignment metadata | `/data` via `-mdir=/data` |
| `volume` | object bytes and volume indexes | `/data` via `-dir=/data`; one volume per server in the replication fixture |
| `filer` | bucket and object namespace metadata | `/data` via `-defaultStoreDir=/data` |
| `s3` | none locally; identities are mounted configuration | no writable path |

Losing any one of the first three stores can make the object path incomplete
even when the other two remain. Copying only volume bytes is not a backup of an
S3 deployment, because the namespace and topology metadata are separate.

The qualified coordinated cold-backup procedure is documented in [cold backup
and restore](BACKUP-RESTORE.md). It stops all roles before exporting master,
volume, and embedded filer state, then proves restoration into new named volumes
and replacement containers. Runtime secrets remain outside the state archives.

## Resource exhaustion

`tests/resource-exhaustion.sh` runs master and volume as separate restricted
containers. One phase fixes the volume count at `-max=1`: the first volume-growth
request succeeds and the second is refused with an explicit API error. This
proves the configured limit is enforced and visible; it does not choose an
appropriate production limit.

The second phase mounts `/data` as a 3 MiB `tmpfs`, verifies the effective mount
and size through `/proc/mounts`, then sends real assigned-volume writes until the
filesystem fills. At least one write must succeed, a later write must fail, and
the volume-server logs must contain a full-filesystem diagnostic. A `tmpfs` is
used only to create deterministic byte pressure. It is not evidence for the
latency, filesystem behavior, or recovery characteristics of a physical disk,
CSI volume, or network storage backend.

Inode exhaustion is still unqualified. The rootless Podman 6.0.2 backend used
for this measurement rejects the `nr_inodes` tmpfs option, and manufacturing a
small inode-limited filesystem would require privileged mounting that violates
the runtime contract being tested. That case requires a real Linux qualification
host with a rootless-compatible inode-limited storage fixture.

## Work still required before a durability claim

The first release still needs a human decision on the durability statement it
is willing to make. The one-host `010` result is a lower bound, not a substitute
for the real-host topology that decision may require. The project also still
owes physical-loss and inode-exhaustion failure injection, backend-specific full
disk qualification, and backup qualification for any external filer backend the
project later supports.
