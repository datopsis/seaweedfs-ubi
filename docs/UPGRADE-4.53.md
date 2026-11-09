# SeaweedFS 4.46 to 4.53 development qualification

Status: proposed development upgrade; **awaiting owner review**. This is not a
release-candidate approval or platform qualification. No human sign-off is
carried forward. The selected variant remains `large_disk` (`5BytesOffset`).

## Inputs and release review

The source comparison is
[`d997fba15` (4.46) to `4ab66fb76` (4.53)](https://github.com/seaweedfs/seaweedfs/compare/4.46...4.53),
1,020 commits. The 4.53 release was published on 2026-11-08 at 18:10:39 UTC.
Release notes and the commit ranges were inspected for all seven increments;
4.49 has no release-note body, so its commit range is the primary record.
The following changes matter to this packaging, beyond dependency updates:

| Increment | Changes and operator impact |
| --- | --- |
| [4.47](https://github.com/seaweedfs/seaweedfs/releases/tag/4.47) | Identity explicit Deny wins over bucket Allow; unsupported policy conditions fail closed; `aws:SourceIp` uses the TCP peer; forwarded-host bucket retargeting is refused. Remote fetch SSRF checks expand. PostgreSQL `createTable` can initialize `filemeta`. Volume copy validation and faulty-media handling change. |
| [4.48](https://github.com/seaweedfs/seaweedfs/releases/tag/4.48) | Explicit trusted-proxy allowlists; dedicated Object Lock permissions; stronger STS checks; atomic multipart completion and safer handling of ambiguous filer writes. Empty intermediate directories no longer prevent deleting an otherwise empty bucket (#11491). Filer shutdown drains metadata logs. `large_disk` compaction fixes five-byte offset corruption (#11411); CRC failures no longer complete successful reads. |
| [4.49](https://github.com/seaweedfs/seaweedfs/compare/4.48...4.49) | Admin defaults move to 12535/22535 with legacy listeners, and unauthenticated mini admin binds to loopback. Recursive bucket deletion defaults off. S3 shutdown drains requests; ACL, conditional-write, proxy, and versioning checks tighten. Pending chunk deletions persist in a filer ledger; topology identity and maximum-volume-ID mirrors protect rebuilt masters; duplicate volume IDs are quarantined. Remote-cache eviction defaults to 90% disk use. Volume startup repairs unindexed tails; fsync rules gain end-to-end enforcement. |
| [4.50](https://github.com/seaweedfs/seaweedfs/releases/tag/4.50) | Volume adds companion loopback listeners; optional local socket bind failures no longer kill services. Filer `fsync` rule presence now distinguishes inheritance from explicit false. Volume fsync batching defaults to a 500 microsecond gather window. Single-node masters stop automatically admitting peers. Container provenance/SBOM attestations are added. |
| [4.51](https://github.com/seaweedfs/seaweedfs/releases/tag/4.51) | Explicit `-ip.bind` suppresses extra loopback listeners. Filer commit records auto-enable for peers with separate stores. S3 stops echoing internal metadata and stored tags; OIDC single-use token behavior is removed. Delete-marker responses and If-Range behavior change. |
| [4.52](https://github.com/seaweedfs/seaweedfs/releases/tag/4.52) | Configured gRPC TLS fails closed on errors and verifies the dialed server identity. S3 Vectors routes share the S3 port; upstream adds a Rust vector binary, which this image does not admit. Filer metadata adds commit stamps/nanosecond delete conditions. Read-only data mounts can serve existing data, with a temporary master-state copy; this is not a newly qualified deployment profile. Incremental backup uses index position and carries tombstones. Lifecycle configuration requires Admin; conditional S3 writes check under the object lock. |
| [4.53](https://github.com/seaweedfs/seaweedfs/releases/tag/4.53) | Replica writes retain primary compression/metadata and have bounded forwarding; JSON compression changes. Vacuum/read and concurrent-delete races are fixed. CORS/versioning need their own actions; per-bucket Block Public Access supports BlockPublicAcls/IgnorePublicAcls. S3 encryption follows the filer. Versioned PUT IDs are minted at commit, delete-marker commits are transactional, and overlapping filer registrations no longer remove the live filer from the lock ring. |

Policy tightening can turn formerly accepted requests into denials. Review
client permissions, trusted proxies, and TLS identities before deployment.
Bucket auto-creation and recursive-delete settings in this image remain explicit
and off. No mixed-version rolling upgrade is claimed.

## Re-verification of upstream assertions

All paths below refer to the exact 4.53 source commit, not moving `master`.

| Assertion | Source/metadata check and result |
| --- | --- |
| Supplier/provenance | Release asset API still lists tarballs and MD5 sidecars, without a tarball signature or SHA-256 manifest. Container workflow still signs recursively against the organization workflow identity. It now enables BuildKit provenance/SBOM and digest-bound attestations; those predicates were not verified here. |
| Build/variant | `docker/Dockerfile.go_build`, release matrices, and `storage/types/offset_5bytes.go`: CGO disabled, `5BytesOffset`, unchanged five-byte index offset and 8 TB ceiling. Both extracted binaries were measured static, not assumed static. The full backend tags remain separate; PostgreSQL is included without `full`. |
| Binary/entrypoint | `weed/weed.go` and `docker/entrypoint.sh`: one Go dispatcher, additional unsupported commands, Alpine upstream runtime with root ownership repair and `su-exec`, default `mini`. Only Go `weed` is copied into this image; Rust volume, worker, and vector binaries remain excluded. |
| S3 auth | `s3api/auth_credentials.go`: no identities/config means auth off; an explicitly supplied empty config enables enforcement. This image's missing-source guard remains necessary. |
| S3 listeners | `command/s3.go`: Iceberg 8181 and Lance 9101 still default on and accept zero to disable. No new separate S3 listener. Vectors dispatches on the existing port's SigV4 service scope; upstream has no disable flag. This is an unqualified API extension, not a newly supported role; no vector worker is shipped. |
| Data paths | `command/master.go`, `volume.go`, `mini.go`: `-mdir`/`-dir` still default to temp for separated storage roles and `.` for mini. Explicit persistent paths remain required. |
| Component security | `security/tls.go`, `guard.go`, scaffold `security.toml`: no credentials still means unauthenticated component traffic; whitelist is empty and does not protect volume reads. Configured TLS now fails closed. Our write-JWT fixture does not authenticate reads; the upstream read-JWT support comment is retained but is not treated as proof of all code paths. Network isolation remains mandatory. |
| Mini | `command/mini.go`, `admin.go`: S3/WebDAV/admin UI and auto-create still default on; recursive deletion now defaults off. New admin 12535/22535 plus 23646/33646 compatibility listeners are prevented by explicit `-admin.port=23646 -admin.port.legacy=0`. UI/WebDAV remain disabled. Unauthenticated admin HTTP and worker gRPC now bind loopback by default. |
| Version/config namespace | `util/version`, `util/config.go`: two-component upstream version, numeric version at runtime, embedded commit, and `WEED_` config prefix remain. Packaging retains `SEAWEEDFS_UBI_`. |

## Storage change and upgrade/rollback boundary

**Filer metadata changed.** `filer.proto` adds `Entry.commit_ts_ns` (field 6)
and additive transaction/delete/log fields; `Entry` conversion persists the
commit stamp. `FilerConf` advances from version 1 to 2: `PathConf.fsync` becomes optional,
preserving explicit false versus inheritance. Old version-1 false values are
read as unset, while new explicit false overrides are retained. The new default-enabled deletion ledger stores
`filer.deleteQueue.ledger.v1` KV records. Master/volume identity mirrors add
persistent state. PostgreSQL startup DDL behavior changes, although the default
`filemeta` column layout remains unchanged. PostgreSQL and multi-filer migration
are not qualified by this development fixture.

No needle version or five-byte index layout change was found: the offset types,
needle writer, and superblock layout are unchanged. Superblock reading,
compaction, recovery, CRC, and EC behavior do change. EC and alternate filer
backends remain outside this qualification. Additive protobuf fields do **not**
establish safe downgrade: an old writer can drop new metadata or miss pending
cleanup and topology safeguards.

The development-qualified path is **cold upgrade, rollback by restoring the
entire pre-upgrade backup**, not by running 4.46 on state mutated by 4.53:

1. Stop writes and gracefully stop S3, filer, volume, then master. Export all
   three state volumes together; preserve the operator configuration separately.
2. Start 4.53 with the existing state and unchanged `large_disk` variant. Check
   old object contents, new writes, authentication, and service health before
   restoring client traffic. Keep the old image and backup through validation.
3. To roll back, stop all roles; restore all three pre-upgrade archives to fresh
   volumes and run 4.46 with its matching configuration. Writes after the backup
   are absent. Keep traffic stopped or reconcile those writes through S3 before
   accepting that rollback boundary. Never mix old/new state snapshots.

`tests/backup-restore.sh` with `UPGRADE_FROM_IMAGE` exercises this path using
separated master/volume/filer/S3 containers, one host, replication `000`, the
embedded LevelDB2 filer, static S3 identities, and no `security.toml`. Both image
versions use read-only roots, non-root users, dropped capabilities, and
no-new-privileges. It writes multi-MiB data on 4.46, backs up every state role,
reads and overwrites it on 4.53, then restores into fresh volumes on 4.46 and
checks the original bytes. This proves neither multi-host migration nor an
in-place downgrade. CI acquires the historical lock fixture by signature and
digest and assembles it with the same current packaging/UBI inputs.

## Regressions and verification status

The upstream issue search on 2026-11-09 covered `4.53` and issues created since
2026-11-08. #12491 and #12481 describe fixes included in 4.53. Open
[#12496](https://github.com/seaweedfs/seaweedfs/issues/12496) is an existing
upload-limit defect: the circuit-breaker blob is identical in 4.46/4.53 and
both upload paths discard request cancellation. Limits default off. The source
path was confirmed, **not reproduced**. It is documented in configuration and
security guidance, without changing upstream code or defaults. No newly
introduced blocking regression was found in that search; a one-day-old release
has limited field evidence. The refreshed search also checked closed
[#12493](https://github.com/seaweedfs/seaweedfs/issues/12493): collection listing
can deadlock behind a writer because it nests the map read lock. The affected
`Topology.ListCollections` and `ConcurrentReadMap.Items` code is identical
in 4.46 and 4.53. Fix `5c910ad54634ebd44b6e34e791ed86eeceef0f53` (#12495)
landed after the release and is not in 4.53. This existing limitation is
documented in operator/security guidance; it was not reproduced or patched.

Local Podman builds/runtime tests are blocked (`cannot clone: Operation not
permitted`). Lock verification and source/binary inspection are local evidence;
container runtime, upgrade/rollback, SBOM, and scanner evidence comes from
[PR run 42550436459](https://github.com/datopsis/seaweedfs-ubi/actions/runs/42550436459).
Both native AMD64 and ARM64 jobs passed all twelve recorded suites:
image filesystem, smoke/restricted runtime, cluster, S3/multipart, S3 TLS,
inter-component security, observability, state survival, one-host replication,
resource exhaustion, backup/restore, and cross-version upgrade/backup rollback.
The upgrade fixture passed seven checks on each architecture. Signature
acquisition, admission/assembly negatives, SBOM validation, and native evidence
reconciliation also passed. The reconciled record identifies test merge commit
`8638f09206105b7fe472937238aca4468181e283` for PR head
`27ca2945a48de1f176ae62af1f9081fdff347f20`. Results and remaining vulnerabilities
are recorded in [Go vulnerability triage](GO-VULNERABILITY-TRIAGE.md).
These automated results do not complete the required human artifact-lock review.

Release-candidate digest binding, human lock/security review, dedicated
standalone credential-rotation and Iceberg lifecycle requalification,
multi-host/backend migration, and external platform qualification remain owed.
Release publication remains disabled. No FIPS, STIG, or platform support claim
is made by this upgrade.

The first native run exposed the intentionally pinned 4.46 empty-prefix bucket
refusal in the S3 suite: 4.53 correctly deleted the empty bucket. The expectation
and configuration guidance now require success while retaining the separate
non-empty-bucket refusal. This is an upstream improvement, not a weakened test
or a newly introduced defect. Both architectures passed the complete rerun
linked above. Subsequent PR revisions must retain passing native CI; the PR
records final-head results separately from this scoped development evidence.
