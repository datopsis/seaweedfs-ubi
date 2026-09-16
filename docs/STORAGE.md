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

## What that does not prove

The fixture has one volume server and keeps its underlying storage throughout.
It therefore provides **no evidence** for:

- survival after loss or corruption of a volume, disk, host, or storage backend;
- replication, quorum behavior, failover, or availability during an outage;
- crash consistency under every possible timing or partial-write condition;
- backup correctness, point-in-time recovery, or disaster recovery; or
- a multi-node topology.

An unclean-stop pass means only that the acknowledged objects in this measured
run survived process termination while their storage remained intact. It must
not be presented as a durability or replication claim.

## State ownership

| Role | Persistent state | Required path in the qualified fixture |
| --- | --- | --- |
| `master` | topology and volume-assignment metadata | `/data` via `-mdir=/data` |
| `volume` | object bytes and volume indexes | `/data` via `-dir=/data` |
| `filer` | bucket and object namespace metadata | `/data` via `-defaultStoreDir=/data` |
| `s3` | none locally; identities are mounted configuration | no writable path |

Losing any one of the first three stores can make the object path incomplete
even when the other two remain. Copying only volume bytes is not a backup of an
S3 deployment, because the namespace and topology metadata are separate.

## Work still required before a durability claim

The first release still needs a human decision on the durability statement it
is willing to make. That decision determines the replication topology that must
be qualified. The project also still owes failure-injection coverage, backup and
restore procedures, and restore evidence against replacement storage.
