# Cold backup and restore

The qualified procedure is a **cold Podman named-volume backup** of a
single-master deployment using the embedded filer metadata store. It captures
master metadata, every volume server's data, and filer metadata as separate tar
archives, then restores them together into newly created volumes.

This is a consistency procedure, not an availability feature. S3 is unavailable
from the beginning of the stop sequence until the restored deployment passes
readiness checks.

## Before backup

Record all information needed to reconstruct the deployment:

- the immutable image digest and SeaweedFS version;
- master, filer, and volume-server arguments;
- every named volume and the role and `/data` path it belongs to;
- topology, replication setting, data-center and rack assignments, and volume
  count limits;
- the filer metadata backend and version; and
- configuration and secret references.

Runtime S3 credentials, TLS private keys, and JWT signing keys are not state
archives. Back them up through the deployment's secret-management system, with
their own access controls and recovery procedure. Do not add them to the data
tarballs merely to make restoration convenient.

## Create a cold backup

Quiesce clients first. Then stop the gateway before the state-bearing roles so
no new S3 write can cross the backup boundary:

```console
podman stop --time 30 seaweedfs-s3 seaweedfs-filer seaweedfs-volume seaweedfs-master
podman rm seaweedfs-s3 seaweedfs-filer seaweedfs-volume seaweedfs-master
```

Export each state volume independently. Repeat the volume-data command for every
volume server in the topology.

```console
podman volume export seaweedfs-master-data > master.tar
podman volume export seaweedfs-volume-data > volume-1.tar
podman volume export seaweedfs-filer-data > filer.tar
sha256sum master.tar volume-1.tar filer.tar > SHA256SUMS
```

The archives contain sensitive topology, namespace, and object data. Store them
in an access-controlled backup destination with encryption, retention, and an
independent copy appropriate to the deployment's threat model. A checksum
detects accidental change; it is not authentication unless the checksum record
is protected separately.

Do not call three archives taken at different live instants a backup. This
procedure's measured consistency boundary is the successful graceful stop of all
roles before any export begins.

## Restore into replacement storage

Verify archive checksums before import. Create new, empty volumes and import the
matching archive into each one:

```console
sha256sum --check SHA256SUMS
podman volume create restored-master-data
podman volume create restored-volume-1-data
podman volume create restored-filer-data
podman volume import restored-master-data master.tar
podman volume import restored-volume-1-data volume-1.tar
podman volume import restored-filer-data filer.tar
```

Re-provision configuration and secrets from their authoritative systems. Start
master, volume servers, filer, then S3 using the recorded image digest and
arguments, substituting the restored volume names. Require the role-specific
readiness checks in [configuration](CONFIGURATION.md#health-and-readiness), then
verify bucket listings and sample or inventory object content rather than
treating process startup as restoration success.

`tests/backup-restore.sh` automates this sequence. It writes and reads an object,
stops every role, exports three non-empty archives, deletes the original volumes,
imports into different volume names, recreates credentials separately, starts
replacement container IDs, and reads the original bytes through S3.

## Evidence boundary

The measured result does not establish:

- a crash-consistent or live snapshot procedure;
- incremental backup, point-in-time recovery, or a recovery-time objective;
- restore after physical media corruption, host loss, or a regional event;
- backup of an external filer database; that backend's native consistent backup
  and restore procedure is required instead;
- Docker volume backup compatibility; Docker does not provide the Podman volume
  export/import interface used here; or
- correctness of an archive that has not been restored and checked.

Test restoration regularly. Archive creation without restoration evidence is an
untested recovery hope, not a backup qualification result.
