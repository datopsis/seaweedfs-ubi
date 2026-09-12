# Upstream build variants

Upstream publishes several different Linux builds of the same SeaweedFS release.
They are not interchangeable, and choosing between them is a decision this
project has to make once and record, because it is baked into the binary.

## The short answer: this is not a runtime flag

**The variant is a compile-time Go build tag, not an option you pass to the
container.** There is no environment variable, no command-line flag, and no
configuration file that switches between variants. Upstream compiles a separate
binary for each combination of tags and publishes each as its own release asset.

That means:

- one image contains exactly one variant, fixed when the image is built;
- switching variants means building and deploying a **different image**; and
- because one of the tags changes the on-disk storage format, switching is a data
  migration, not a redeploy.

This is why [versioning and releases](VERSION.md#artifact-identity) requires the
variant to appear in OCI metadata. The release tag records the SeaweedFS version
but cannot encode the variant, so two images carrying the same tag could
otherwise differ in a way that matters to stored data.

## What each variant actually changes

Verified from the upstream release workflows and source at tag `4.46`. Re-verify
at every version bump; upstream could add or retag assets.

| Asset | Build tags | What it changes |
| --- | --- | --- |
| `linux_amd64`, `linux_arm64` | *(none)* | Baseline. Maximum **32 GB** per volume. |
| `linux_amd64_large_disk`, `linux_arm64_large_disk` | `5BytesOffset` | Maximum **8 TB** per volume. |
| `linux_amd64_full` | `elastic,gocdk,rclone,sqlite,tarantool,tikv,ydb` | Adds optional filer and remote-storage backends. 32 GB volumes. |
| `linux_amd64_full_large_disk` | all of the above plus `5BytesOffset` | Both. |
| `weed-volume_*`, `weed-worker_*` | varies | Single-role binaries rather than the full `weed` command. Not used by this project, which ships one binary and selects the role at runtime. |

Every variant is linked with `-extldflags -static`, so the binary is statically
linked and carries no glibc version requirement. That is why it runs on UBI 9
Micro without rebuilding, and it is measured and recorded per release rather than
assumed.

### The volume size tag, in detail

`5BytesOffset` widens the needle offset stored in a volume's index from 4 bytes
to 5. Upstream's constant makes the effect exact:

- without the tag: `MaxPossibleVolumeSize = 4 GiB * 8 = 32 GB`
- with the tag: `MaxPossibleVolumeSize = 4 GiB * 8 * 256 = 8 TB`

Three things about this are easy to misread:

1. **It is a per-volume ceiling, not a capacity limit.** A cluster with 32 GB
   volumes stores more than 32 GB; it simply creates more volumes. What changes
   is how many volumes you need for a given capacity.
2. **The practical default is smaller than it looks.** A volume server defaults
   to `-max 8`, so a default-build volume server holds roughly 256 GB before you
   tune it, against roughly 64 TB for a `large_disk` build.
3. **It costs index memory per stored object.** Every needle's index entry grows
   by one byte. That is irrelevant for a few million large objects and
   meaningful for the billions of small files SeaweedFS is also designed for.

### The `full` tag list, in detail

`full` does **not** add storage capability or performance. It compiles in
optional backends that upstream excludes by default purely because their
dependencies make the binary much larger — the upstream package stubs say so
directly.

`full` adds these filer metadata backends: **Elasticsearch v7, SQLite, TiKV,
YDB, Tarantool**, plus the `gocdk` and `rclone` remote-storage integrations used
for tiering.

It is worth being precise about what is *already* present without it, because
this is the part that usually drives the decision. The plain and `large_disk`
builds already include these filer backends:

- embedded: `leveldb`, `leveldb2`, `leveldb3`
- **PostgreSQL: `postgres`, `postgres2`**
- MySQL: `mysql`, `mysql2`
- Redis: `redis`, `redis2`, `redis3`
- also `mongodb`, `etcd`, `cassandra`, `cassandra2`, `hbase`, `arangodb`,
  `foundationdb`

`rocksdb` is gated behind its own separate `rocksdb` tag and is not part of
`full` either.

## The selected variant

This project admits **`large_disk`** — `linux_amd64_large_disk` and
`linux_arm64_large_disk`.

The reasoning, recorded so a later reviewer does not have to reconstruct it:

- **The intended workload is large objects.** This image exists to hold Apache
  Iceberg table data: Parquet files and manifests, measured in megabytes to
  gigabytes, not billions of small files. The index-size cost of the wider offset
  lands on the case this project does not optimize for, and the volume-count
  benefit lands on the case it does.
- **The default ceiling is low enough to be hit accidentally.** Roughly 256 GB
  per volume server before tuning is within reach of a single table, and
  discovering that after data exists is the expensive way to learn it.
- **It is the harder direction to reverse.** Of the two, being on `large_disk`
  and not needing it costs one byte per index entry. Being on the default build
  and needing 8 TB volumes costs a migration.
- **`full` buys nothing this project wants.** The backend this organization would
  actually use for filer metadata is PostgreSQL, which is already in the plain
  build — the org runs [`postgresql-ubi`](https://github.com/datopsis/postgresql-ubi),
  and an Iceberg deployment already requires PostgreSQL for the catalog. Taking
  `full` would add five unqualified backends and two tiering integrations to the
  binary, enlarging it and widening the code present in a hardened image, in
  exchange for capability outside the first-release boundary.

## What switching would cost

> [!IMPORTANT]
> The exact migration path is **not yet qualified**. This section states what is
> known from the format change and what must be tested before any switch is
> attempted or documented as supported. Work package 4 owes that qualification.

What is known: the tag changes the width of offsets written into a volume's index
file. A build that expects 4-byte offsets and a build that expects 5-byte offsets
do not agree on the layout of an existing index, so the on-disk state written by
one is not automatically readable by the other.

What follows from that:

- **Changing variant is not a redeploy.** Pointing a new image at an existing
  data directory is not a supported operation in either direction until tested.
- **The conservative path is a data migration, not an in-place upgrade.** Stand
  up a second cluster on the new variant and copy data across through the S3 API,
  then cut over. This treats the object store as the interface, which is the only
  layer whose compatibility this project intends to qualify.
- **Direction matters and must be measured.** Whether a wider-offset build can
  read a narrower-offset volume is a question about upstream's index reading
  code, not something to assume from the constant. Package 4 must test both
  directions and record the result, including what happens on a *partial*
  migration.

Until that evidence exists, the operator-facing rule is simply: **choose the
variant before storing data you intend to keep.** This document exists so that
choice is made with the tradeoff visible rather than by accepting a default.

## If this decision needs to be revisited

Reopening it is legitimate; doing it silently is not. A change of variant
requires:

1. a recorded decision here, with the reasoning and the date;
2. a reviewed update to the artifact lock, since the admitted asset changes;
3. a new container release under [versioning and releases](VERSION.md), which
   lists an asset-variant change as requiring one, with the operator impact
   stated in the changelog;
4. the migration procedure qualified and published before, not after, the image
   is offered; and
5. an update to the support matrix in [the support contract](SUPPORT.md), because
   a variant change alters what stored data an image can serve.

## References

- Upstream release workflows, which define the tag sets per asset:
  [`binaries_release*.yml`](https://github.com/seaweedfs/seaweedfs/tree/master/.github/workflows)
- Upstream volume offset constants:
  [`weed/storage/types/offset_4bytes.go`](https://github.com/seaweedfs/seaweedfs/blob/master/weed/storage/types/offset_4bytes.go)
  and
  [`offset_5bytes.go`](https://github.com/seaweedfs/seaweedfs/blob/master/weed/storage/types/offset_5bytes.go)
