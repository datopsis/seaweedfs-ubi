#!/usr/bin/env python3
"""A minimal AWS Signature Version 4 client, and the S3 checks built on it.

Written rather than pulled in for two reasons. A test client is a build input
like any other, and adding a large CLI image to reach the S3 API would put an
unpinned third party inside the one suite whose job is to prove the access
controls work. It also keeps the suite runnable on a controlled network, where
fetching a client is the awkward part.

It implements only what the checks need: path-style addressing, unsigned-payload
avoidance by hashing the body, and the handful of verbs S3 qualification starts
with. It is not an S3 SDK and should not grow into one.

Usage:
    s3client.py <endpoint> <config.json>

The config is the same file the gateway reads, so the checks use exactly the
identities the server was given.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from xml.etree import ElementTree

REGION = "us-east-1"
SERVICE = "s3"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class Response:
    def __init__(self, status: int, body: bytes, headers: dict[str, str]) -> None:
        self.status = status
        self.body = body
        self.headers = headers

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date: str) -> bytes:
    key = _sign(f"AWS4{secret}".encode("utf-8"), date)
    key = _sign(key, REGION)
    key = _sign(key, SERVICE)
    return _sign(key, "aws4_request")


class S3Client:
    """Path-style S3 over plain HTTP, signed with SigV4."""

    def __init__(
        self,
        endpoint: str,
        access_key: str | None,
        secret_key: str | None,
        ca_bundle: str | None = None,
        verify: bool = True,
    ):
        """ca_bundle trusts a private CA; verify=False disables checking entirely.

        Both exist so the TLS checks can tell "the server presented a certificate
        we trust" apart from "the connection happened to work". A client that
        trusts everything proves nothing about the server's identity.
        """
        self.endpoint = endpoint.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        parsed = urllib.parse.urlparse(self.endpoint)
        self.host = parsed.netloc
        self.context = None
        if parsed.scheme == "https":
            if not verify:
                self.context = ssl._create_unverified_context()  # noqa: S323
            else:
                self.context = ssl.create_default_context(cafile=ca_bundle)

    def request(
        self,
        method: str,
        path: str = "/",
        body: bytes = b"",
        query: dict[str, str] | None = None,
    ) -> Response:
        query = query or {}
        # Only the path is encoded here; the checks use simple keys on purpose,
        # so the signer stays small enough to read in one sitting.
        canonical_uri = urllib.parse.quote(path, safe="/")
        canonical_query = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted(query.items())
        )
        payload_hash = hashlib.sha256(body).hexdigest() if body else EMPTY_SHA256

        now = dt.datetime.now(dt.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        headers = {
            "host": self.host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }

        # An unsigned request is a real case the checks exercise, so signing is
        # conditional rather than assumed.
        if self.access_key and self.secret_key:
            signed_headers = ";".join(sorted(headers))
            canonical_headers = "".join(
                f"{name}:{headers[name].strip()}\n" for name in sorted(headers)
            )
            canonical_request = "\n".join(
                [
                    method,
                    canonical_uri,
                    canonical_query,
                    canonical_headers,
                    signed_headers,
                    payload_hash,
                ]
            )
            scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
            string_to_sign = "\n".join(
                [
                    "AWS4-HMAC-SHA256",
                    amz_date,
                    scope,
                    hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
                ]
            )
            signature = hmac.new(
                _signing_key(self.secret_key, date_stamp),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["Authorization"] = (
                f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            )

        url = f"{self.endpoint}{canonical_uri}"
        if canonical_query:
            url = f"{url}?{canonical_query}"

        request = urllib.request.Request(  # noqa: S310
            url, data=body or None, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=30, context=self.context
            ) as response:
                return Response(response.status, response.read(), dict(response.headers))
        except urllib.error.HTTPError as error:
            return Response(error.code, error.read(), dict(error.headers))
        except urllib.error.URLError as error:
            # A refused TLS handshake is a result the checks care about, not a
            # crash. Surface it as status 0 with the reason in the body.
            return Response(0, str(error.reason).encode(), {})

    # Convenience wrappers, named for the S3 operation rather than the verb.
    def create_bucket(self, bucket: str) -> Response:
        return self.request("PUT", f"/{bucket}")

    def delete_bucket(self, bucket: str) -> Response:
        return self.request("DELETE", f"/{bucket}")

    def put_object(self, bucket: str, key: str, body: bytes) -> Response:
        return self.request("PUT", f"/{bucket}/{key}", body=body)

    def get_object(self, bucket: str, key: str) -> Response:
        return self.request("GET", f"/{bucket}/{key}")

    def delete_object(self, bucket: str, key: str) -> Response:
        return self.request("DELETE", f"/{bucket}/{key}")

    def list_objects(self, bucket: str) -> Response:
        return self.request("GET", f"/{bucket}", query={"list-type": "2"})

    # ---- multipart upload --------------------------------------------------
    #
    # The table-format path needs this: Parquet files routinely exceed what a
    # single PUT carries, so an object store that round-trips small objects but
    # mishandles multipart would fail on the first real dataset rather than in a
    # smoke test.

    def initiate_multipart(self, bucket: str, key: str) -> Response:
        return self.request("POST", f"/{bucket}/{key}", query={"uploads": ""})

    def upload_part(
        self, bucket: str, key: str, upload_id: str, part_number: int, body: bytes
    ) -> Response:
        return self.request(
            "PUT",
            f"/{bucket}/{key}",
            body=body,
            query={"partNumber": str(part_number), "uploadId": upload_id},
        )

    def complete_multipart(
        self, bucket: str, key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> Response:
        entries = "".join(
            f"<Part><PartNumber>{number}</PartNumber><ETag>{etag}</ETag></Part>"
            for number, etag in parts
        )
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<CompleteMultipartUpload>{entries}</CompleteMultipartUpload>"
        ).encode("utf-8")
        return self.request(
            "POST", f"/{bucket}/{key}", body=body, query={"uploadId": upload_id}
        )

    def abort_multipart(self, bucket: str, key: str, upload_id: str) -> Response:
        return self.request(
            "DELETE", f"/{bucket}/{key}", query={"uploadId": upload_id}
        )


def xml_text(body: bytes, tag: str) -> str | None:
    """Pull one element's text out of an S3 XML response.

    S3 responses carry a default namespace, and matching on the local name keeps
    this from depending on which namespace URI a given server emits.
    """
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return None
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == tag:
            return (element.text or "").strip()
    return None


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def ok(self, description: str) -> None:
        print(f"ok    {description}")
        self.passed += 1

    def bad(self, description: str, *detail: str) -> None:
        print(f"FAIL  {description}")
        for line in detail:
            print(f"      {line}")
        self.failed += 1

    def expect(self, description: str, actual: int, *allowed: int) -> bool:
        if actual in allowed:
            self.ok(description)
            return True
        wanted = " or ".join(str(code) for code in allowed)
        self.bad(description, f"expected HTTP {wanted}, got {actual}")
        return False

    # A denial must be a denial, not an accident. 404 would mean the object was
    # missing rather than the caller refused, and 5xx would mean the server fell
    # over, both of which would pass a naive "not 200" assertion.
    def expect_denied(self, description: str, actual: int) -> bool:
        if actual in (401, 403):
            self.ok(description)
            return True
        self.bad(description, f"expected HTTP 401 or 403, got {actual}")
        return False


def identities(config: dict) -> dict[str, tuple[str, str]]:
    found = {}
    for identity in config.get("identities", []):
        for credential in identity.get("credentials", []):
            found[identity["name"]] = (
                credential["accessKey"],
                credential["secretKey"],
            )
            break
    return found


def run(endpoint: str, config_path: Path) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    creds = identities(config)
    for required in ("setup", "alpha", "beta"):
        if required not in creds:
            raise SystemExit(f"the config has no credentials for {required!r}")

    setup = S3Client(endpoint, *creds["setup"])
    alpha = S3Client(endpoint, *creds["alpha"])
    beta = S3Client(endpoint, *creds["beta"])
    anonymous = S3Client(endpoint, None, None)
    wrong = S3Client(endpoint, creds["alpha"][0], "not-the-right-secret")

    checks = Checks()
    payload = f"seaweedfs-ubi round trip {uuid.uuid4()}".encode("utf-8")
    key = "object.txt"

    # ---- an administrator prepares the tenants' buckets -------------------
    checks.expect("an admin identity creates a bucket", setup.create_bucket("alpha").status, 200, 204)
    setup.create_bucket("beta")

    # ---- the authenticated round trip -------------------------------------
    checks.expect("an authorised identity writes an object", alpha.put_object("alpha", key, payload).status, 200, 204)

    got = alpha.get_object("alpha", key)
    if got.status == 200 and got.body == payload:
        checks.ok("the object reads back byte for byte")
    else:
        checks.bad(
            "the object reads back byte for byte",
            f"status {got.status}, {len(got.body)} bytes, expected {len(payload)}",
        )

    listing = alpha.list_objects("alpha")
    if listing.status == 200 and key in listing.text:
        checks.ok("the object appears in a bucket listing")
    else:
        checks.bad("the object appears in a bucket listing", f"status {listing.status}")

    # ---- access control ----------------------------------------------------
    checks.expect_denied("an anonymous read is refused", anonymous.get_object("alpha", key).status)
    checks.expect_denied("an anonymous write is refused", anonymous.put_object("alpha", "anon.txt", b"x").status)
    checks.expect_denied("an anonymous bucket listing is refused", anonymous.list_objects("alpha").status)
    rejected = wrong.get_object("alpha", key)
    checks.expect_denied("a valid key with the wrong secret is refused", rejected.status)
    sensitive_values = (*creds["alpha"], "not-the-right-secret")
    if any(value.encode() in rejected.body for value in sensitive_values):
        checks.bad("a rejected request does not echo credentials in its error body")
    else:
        checks.ok("a rejected request does not echo credentials in its error body")

    # The reason two identities exist. A tenant confined to its own bucket must
    # not reach another's, which is the boundary a shared catalog depends on.
    checks.expect_denied("one tenant cannot read another tenant's object", beta.get_object("alpha", key).status)
    checks.expect_denied("one tenant cannot write into another tenant's bucket", beta.put_object("alpha", "intruder.txt", b"x").status)
    checks.expect_denied("one tenant cannot list another tenant's bucket", beta.list_objects("alpha").status)

    # ---- the two upstream defaults this image turns off ---------------------
    missing = alpha.put_object("no-such-bucket", "k.txt", b"x")
    if missing.status in (403, 404):
        checks.ok("a write to a missing bucket fails rather than creating it")
    else:
        checks.bad(
            "a write to a missing bucket fails rather than creating it",
            f"got HTTP {missing.status}; autoCreateBucket may be enabled",
        )

    non_empty = setup.delete_bucket("alpha")
    if non_empty.status in (409, 403):
        checks.ok("deleting a non-empty bucket is refused rather than deleting its contents")
    else:
        checks.bad(
            "deleting a non-empty bucket is refused rather than deleting its contents",
            f"got HTTP {non_empty.status}; allowDeleteBucketNotEmpty may be enabled",
        )
        # If the bucket really was removed, say whether the data went with it.
        after = alpha.get_object("alpha", key)
        checks.bad(
            "  consequence",
            f"the object now reads back as HTTP {after.status}",
        )

    # ---- multipart upload ---------------------------------------------------
    #
    # Exercised with parts at the 5 MiB minimum the S3 API imposes on every part
    # but the last, because a test that uploads three tiny parts would not touch
    # the path a real Parquet write takes.
    multipart_key = "large.bin"
    part_size = 5 * 1024 * 1024
    # Deterministic but not uniform: a run of identical bytes would hide a server
    # that reassembled the parts in the wrong order.
    part_one = bytes((i * 7 + 1) % 251 for i in range(part_size))
    part_two = bytes((i * 13 + 2) % 251 for i in range(part_size))
    part_three = b"tail" * 1024
    expected = part_one + part_two + part_three
    expected_digest = hashlib.sha256(expected).hexdigest()

    initiated = alpha.initiate_multipart("alpha", multipart_key)
    upload_id = xml_text(initiated.body, "UploadId") if initiated.status == 200 else None
    if upload_id:
        checks.ok("a multipart upload can be initiated")
    else:
        checks.bad(
            "a multipart upload can be initiated",
            f"status {initiated.status}, no UploadId in the response",
        )

    if upload_id:
        etags: list[tuple[int, str]] = []
        failed_part = None
        for number, chunk in enumerate((part_one, part_two, part_three), start=1):
            response = alpha.upload_part("alpha", multipart_key, upload_id, number, chunk)
            etag = response.headers.get("ETag") or response.headers.get("Etag")
            if response.status != 200 or not etag:
                failed_part = (number, response.status)
                break
            etags.append((number, etag))

        if failed_part is None:
            checks.ok("every part uploads and returns an ETag")
        else:
            checks.bad(
                "every part uploads and returns an ETag",
                f"part {failed_part[0]} returned HTTP {failed_part[1]}",
            )

        # A part belongs to the upload, and the upload belongs to a tenant. A
        # neighbour who learns the upload id must still be refused.
        checks.expect_denied(
            "another tenant cannot add a part to an upload it does not own",
            beta.upload_part("alpha", multipart_key, upload_id, 99, b"intruder").status,
        )

        if failed_part is None:
            completed = alpha.complete_multipart("alpha", multipart_key, upload_id, etags)
            checks.expect("the multipart upload completes", completed.status, 200)

            fetched = alpha.get_object("alpha", multipart_key)
            if fetched.status != 200:
                checks.bad(
                    "the reassembled object matches what was uploaded",
                    f"status {fetched.status}",
                )
            elif len(fetched.body) != len(expected):
                checks.bad(
                    "the reassembled object matches what was uploaded",
                    f"got {len(fetched.body)} bytes, expected {len(expected)}",
                )
            elif hashlib.sha256(fetched.body).hexdigest() != expected_digest:
                # Same length, different bytes: parts reassembled out of order or
                # a part silently truncated and padded.
                checks.bad(
                    "the reassembled object matches what was uploaded",
                    "the length is right but the content differs, so the parts were",
                    "not reassembled in order",
                )
            else:
                checks.ok(
                    f"the reassembled object matches what was uploaded "
                    f"({len(expected) // 1024} KiB over {len(etags)} parts)"
                )

            checks.expect(
                "the multipart object deletes",
                alpha.delete_object("alpha", multipart_key).status,
                200,
                204,
            )

    # An abandoned upload must not leave a readable object behind.
    aborted_key = "abandoned.bin"
    abort_initiated = alpha.initiate_multipart("alpha", aborted_key)
    abort_id = xml_text(abort_initiated.body, "UploadId")
    if abort_id:
        alpha.upload_part("alpha", aborted_key, abort_id, 1, part_three)
        checks.expect(
            "an abandoned multipart upload can be aborted",
            alpha.abort_multipart("alpha", aborted_key, abort_id).status,
            200,
            204,
        )
        after_abort = alpha.get_object("alpha", aborted_key)
        if after_abort.status == 404:
            checks.ok("an aborted upload leaves no object behind")
        else:
            checks.bad(
                "an aborted upload leaves no object behind",
                f"the key still answers HTTP {after_abort.status}",
            )
    else:
        checks.bad("an abandoned multipart upload can be aborted", "could not initiate")

    # ---- cleanup is part of the contract too -------------------------------
    checks.expect("an authorised identity deletes its object", alpha.delete_object("alpha", key).status, 200, 204)
    checks.expect("an emptied bucket can then be deleted", setup.delete_bucket("alpha").status, 200, 204)

    # ---- a documented divergence from the S3 API ----------------------------
    #
    # SeaweedFS models a bucket as a directory, so a key containing a slash
    # creates a directory entry that outlives the object. The listing goes empty,
    # but the bucket does not, and with allowDeleteBucketNotEmpty off -- which is
    # this image's default -- the bucket then cannot be deleted even though a
    # client sees nothing in it.
    #
    # This is asserted rather than avoided. It is a real consequence of a default
    # this image chose, an operator will meet it, and pinning it means an upstream
    # change to directory cleanup surfaces here as a failure to review instead of
    # going unnoticed.
    nested = "prefix/nested.txt"
    beta.put_object("beta", nested, b"nested payload")
    beta.delete_object("beta", nested)

    listing_after = beta.list_objects("beta")
    if listing_after.status == 200 and nested not in listing_after.text:
        checks.ok("a deleted object under a prefix leaves no object in the listing")
    else:
        checks.bad(
            "a deleted object under a prefix leaves no object in the listing",
            f"status {listing_after.status}",
        )

    residual = setup.delete_bucket("beta")
    if residual.status == 409:
        checks.ok("a bucket whose listing is empty is still refused while a prefix directory remains")
    elif residual.status in (200, 204):
        checks.bad(
            "a bucket whose listing is empty is still refused while a prefix directory remains",
            "the bucket deleted cleanly, so upstream now removes empty prefix",
            "directories. That is an improvement: update this expectation and the",
            "note in docs/CONFIGURATION.md rather than leaving them stale.",
        )
    else:
        checks.bad(
            "a bucket whose listing is empty is still refused while a prefix directory remains",
            f"expected HTTP 409, got {residual.status}",
        )

    print(f"\n{checks.passed} passed, {checks.failed} failed")
    return 1 if checks.failed else 0


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    return run(argv[1], Path(argv[2]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
