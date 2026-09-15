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
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

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

    def __init__(self, endpoint: str, access_key: str | None, secret_key: str | None):
        self.endpoint = endpoint.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        parsed = urllib.parse.urlparse(self.endpoint)
        self.host = parsed.netloc

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
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                return Response(response.status, response.read(), dict(response.headers))
        except urllib.error.HTTPError as error:
            return Response(error.code, error.read(), dict(error.headers))
        except urllib.error.URLError as error:
            raise SystemExit(f"cannot reach {self.endpoint}: {error}") from error

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
    checks.expect_denied("a valid key with the wrong secret is refused", wrong.get_object("alpha", key).status)

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
