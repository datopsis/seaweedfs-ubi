# Standalone `mini` for local development

Status: development guide, not a released or production-qualified deployment.
The local lifecycle test observed object bytes and a shell-created filer
directory across container replacement with the same named data volume, but
the full test is **not passing**: SeaweedFS 4.46 logs an access-key ID on an
invalid-key request during credential replacement. Do not treat this guide or
the lifecycle result as a production security or durability claim.

Run these examples from the repository root in a Bash-compatible shell, after
building the local development image. Podman Compose and Python 3 are required.
The Compose profile publishes only S3 on `127.0.0.1:8333`, but its other
listeners remain reachable to containers on the development network. Do not
connect untrusted peers or use host networking.

## Create the external identity file

Create `s3.json` only if it does not already exist. The file is Git-ignored and
must stay outside the image; protect it with host permissions and backups under
your local secrets policy. The code uses exclusive creation so rerunning it
cannot silently replace credentials for existing data.

```bash
umask 077
python - <<'PY'
import json
import secrets
from pathlib import Path

identity = {
    "identities": [{
        "name": "local-admin",
        "credentials": [{
            "accessKey": "mini" + secrets.token_hex(8),
            "secretKey": secrets.token_urlsafe(32),
        }],
        "actions": ["Admin", "Read", "List", "Tagging", "Write"],
    }],
}
with Path("s3.json").open("x", encoding="utf-8") as output:
    json.dump(identity, output)
PY
podman compose -f compose.standalone.yaml up -d
```

On Windows, verify that the file's ACL is limited to your account; `umask` is
not an ACL control there. The container receives the file read-only at
`/etc/seaweedfs/s3.json`. Keep it available across container replacement.
Using `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as `mini` bootstrap
variables is supported by the image but is **not** used in this profile:
upstream 4.46 writes the access-key ID to its startup log on that path.

## Check the S3 path and administer the filer

The repository's small SigV4 client can make an authenticated round trip
without printing either credential or placing it in command arguments:

```bash
python - <<'PY'
import json
import secrets
import sys

sys.path.insert(0, "tests/lib")
from s3client import S3Client

identity = json.load(open("s3.json", encoding="utf-8"))["identities"][0]
credential = identity["credentials"][0]
client = S3Client("http://127.0.0.1:8333", credential["accessKey"], credential["secretKey"])
bucket = "mini-guide-" + secrets.token_hex(4)
payload = bytes(range(256))
assert client.create_bucket(bucket).status in (200, 204)
assert client.put_object(bucket, "roundtrip.bin", payload).status in (200, 204)
read = client.get_object(bucket, "roundtrip.bin")
assert read.status == 200 and read.body == payload
print("Authenticated S3 round trip succeeded in", bucket)
PY
```

Yes, `weed shell` normally means executing the administrative client inside
the running container. It is a client that talks to the local master and filer,
not the disabled Admin UI. For a read-only inspection:

```bash
container_id="$(podman compose -f compose.standalone.yaml ps -q seaweedfs)"
printf 'fs.ls /\n' | podman exec -i "$container_id" /usr/local/bin/seaweedfs-entrypoint shell \
  -master=127.0.0.1:9333 -filer=127.0.0.1:8888
```

This direct `podman exec` form was exercised by the lifecycle test. The
Windows Compose provider did not complete a piped `podman compose exec -T`
invocation in the local check, so that form is not presented as verified.

`weed shell` can mutate data and configuration. The disposable lifecycle test
measured that a directory created with `fs.mkdir` remains in filer metadata
after container replacement with the same `/data` volume. That result does
**not** establish persistence or live propagation of every shell command.
In particular, do not rely on `s3.configure` for persistent credentials here;
the mounted `s3.json` is the startup source of truth. Dynamic S3 identity
propagation needs separate qualification.

## Restart, change credentials, and retain data

`podman compose -f compose.standalone.yaml down` stops and removes the
container and development network but retains Compose's named `/data` volume.
Restart with `up -d` and the same `s3.json`; a replacement container can read
objects already written. The lifecycle test checks the bytes, not merely that
the process starts.

To change startup credentials, stop the profile, replace `s3.json` securely
with another valid file of the same shape and restrictive permissions, then
start it again. The local lifecycle test observed that a new static identity
could read the retained object and the old one was denied after replacement,
but its strict log assertion failed on the denied request. Keep
container logs access-restricted; do not send raw logs to an untrusted sink.
Do not put secrets in shell command arguments or commit the identity file.

```bash
podman compose -f compose.standalone.yaml down
# Replace s3.json using your secrets-management procedure; retain the data volume.
podman compose -f compose.standalone.yaml up -d
podman compose -f compose.standalone.yaml ps
podman compose -f compose.standalone.yaml logs --tail=30 seaweedfs
```

Never use `down -v` on a profile whose data you want to retain: it removes the
named volume. A persistent volume is not a backup, and `mini` has no qualified
backup, replication, host-loss recovery, or production posture. Use the
separated-role profile and its distinct qualification work for those claims.
