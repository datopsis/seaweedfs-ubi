#!/usr/bin/env python3
"""Adversarial qualification of STS credential vending on the real gateway.

Credential vending is only a table-isolation control if a session restricted to
one table cannot reach another, cannot be widened, cannot be forged, and stops
working when it should. Every check here asserts the exact secure outcome; any
other outcome fails the run. Nothing is reported as a pass by elimination.

The gateway serves S3 and STS on one TLS listener. Identities, roles, buckets,
and keys are created by tests/sts.sh for this run only:

    setup     administrator; seeds and inspects objects as ground truth
    vendor    the catalog's identity (a Lakekeeper stand-in): trusted by the role
    outsider  a valid identity the role's trust policy does not name

The role grants `tables/*` in the warehouse bucket. Each table-scoped session
policy has the exact shape Lakekeeper 0.13 sends (`get_sts_policy_string`).

Usage:
    stschecks.py <phase> <endpoint> <ca.crt> <s3.json> <run.json> <state.json>

    phase  issue    run every check, mint the long-lived sessions, save state
           restart  after a gateway restart with the same signing key
           expire   after the short session's DurationSeconds has elapsed
           rotated  after a restart with a new STS signing key
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import secrets
import ssl
import sys
import time
import urllib.parse
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree

from s3client import Checks, xml_text
from sigcoverage import Reply, Signer, Wire, delete_body, delete_result, send

TABLE_A = "tables/a/"
TABLE_B = "tables/b/"
SIBLING = "tables/a-evil/"
OUTSIDE = "outside/"
ROLE_NAME = "lakekeeper-vended"
ROLE_ARN = f"arn:aws:iam::000000000000:role/{ROLE_NAME}"
SHORT_DURATION = 900  # the AssumeRole minimum, so the expiry check is real

READ_WRITE_DELETE = [
    "s3:GetObject",
    "s3:GetObjectVersion",
    "s3:PutObject",
    "s3:DeleteObject",
    "s3:AbortMultipartUpload",
    "s3:ListMultipartUploadParts",
]
READ_ONLY = ["s3:GetObject", "s3:GetObjectVersion"]


def table_policy(bucket: str, prefix: str, actions: list[str]) -> str:
    """The session policy Lakekeeper builds for one table location."""
    bucket_arn = f"arn:aws:s3:::{bucket}"
    key_wildcard = f"{prefix}*"
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Sid": "TableAccess", "Effect": "Allow", "Action": actions,
                 "Resource": f"{bucket_arn}/{key_wildcard}"},
                {"Sid": "ListBucketForFolder", "Effect": "Allow", "Action": "s3:ListBucket",
                 "Resource": bucket_arn,
                 "Condition": {"StringLike": {"s3:prefix": key_wildcard}}},
                {"Sid": "GetBucketLocation", "Effect": "Allow", "Action": "s3:GetBucketLocation",
                 "Resource": bucket_arn},
            ],
        },
        separators=(",", ":"),
    )


WIDE_POLICY = json.dumps(
    {"Version": "2012-10-17",
     "Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": ["arn:aws:s3:::*"]}]},
    separators=(",", ":"),
)


class Endpoint:
    def __init__(self, url: str, ca_file: str) -> None:
        self.url = url
        self.host = urllib.parse.urlparse(url).netloc
        self.context = ssl.create_default_context(cafile=ca_file)

    def send(self, wire: Wire) -> Reply:
        return send(self.url, wire, self.context)


class Principal:
    """Anyone who signs: a static identity, or a vended session with its token."""

    def __init__(self, endpoint: Endpoint, access_key: str, secret_key: str,
                 token: str | None = None) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.token = token

    def wire(self, method: str, path: str, query=(), body: bytes = b"",
             headers: dict[str, str] | None = None) -> Wire:
        headers = dict(headers or {})
        if self.token:
            headers["x-amz-security-token"] = self.token
        return Signer(self.endpoint.host, self.access_key, self.secret_key).sign(
            method, path, query=tuple(query), headers=headers, body=body
        )

    def call(self, method: str, path: str, query=(), body: bytes = b"",
             headers: dict[str, str] | None = None) -> Reply:
        return self.endpoint.send(self.wire(method, path, query, body, headers))

    def sts(self, params: dict[str, str]) -> Reply:
        """An STS query-API call shaped like an AWS SDK's: a form body, service
        `sts`, and no x-amz-content-sha256 header, so the gateway hashes the
        body it receives rather than trusting a declared value."""
        body = urllib.parse.urlencode({"Version": "2011-06-15", **params}).encode()
        headers = {"content-type": "application/x-www-form-urlencoded; charset=utf-8"}
        if self.token:
            headers["x-amz-security-token"] = self.token
        signer = Signer(self.endpoint.host, self.access_key, self.secret_key, service="sts")
        return self.endpoint.send(
            signer.sign("POST", "/", headers=headers, body=body, payload_header=False))


def assume_role(principal: Principal, policy: str | None = None,
                duration: int | None = None, role_arn: str | None = ROLE_ARN,
                session: str = "qualification") -> tuple[Reply, dict[str, str] | None]:
    params = {"Action": "AssumeRole", "RoleSessionName": session}
    if role_arn is not None:
        params["RoleArn"] = role_arn
    if policy is not None:
        params["Policy"] = policy
    if duration is not None:
        params["DurationSeconds"] = str(duration)
    reply = principal.sts(params)
    if reply.status != 200:
        return reply, None
    fields = {name: xml_text(reply.body, name) for name in
              ("AccessKeyId", "SecretAccessKey", "SessionToken", "Expiration")}
    if not all(fields.values()):
        return reply, None
    return reply, fields  # type: ignore[return-value]


def session_of(endpoint: Endpoint, creds: dict[str, str]) -> Principal:
    return Principal(endpoint, creds["AccessKeyId"], creds["SecretAccessKey"],
                     creds["SessionToken"])


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Run:
    def __init__(self, endpoint: Endpoint, s3_config: dict, run_config: dict,
                 checks: Checks) -> None:
        self.endpoint = endpoint
        self.bucket = run_config["bucket"]
        self.other = run_config["other_bucket"]
        self.checks = checks
        found = {}
        for identity in s3_config["identities"]:
            credential = identity["credentials"][0]
            found[identity["name"]] = Principal(endpoint, credential["accessKey"],
                                                credential["secretKey"])
        self.setup = found["setup"]
        self.vendor = found["vendor"]
        self.outsider = found["outsider"]

    # ---- helpers ------------------------------------------------------------

    def path(self, prefix: str, name: str, bucket: str | None = None) -> str:
        return f"/{bucket or self.bucket}/{prefix}{name}"

    def truth(self, prefix: str, name: str, bucket: str | None = None) -> Reply:
        return self.setup.call("GET", self.path(prefix, name, bucket))

    def expect(self, description: str, reply: Reply, status: int, code: str | None = None) -> bool:
        if reply.status == status and (code is None or reply.code == code):
            self.checks.ok(f"{description} -> {status}{' ' + code if code else ''}")
            return True
        wanted = f"{status}{' ' + code if code else ''}"
        self.checks.bad(description, f"expected HTTP {wanted}, got HTTP {reply.status} {reply.code}")
        return False

    def denied(self, description: str, reply: Reply) -> bool:
        return self.expect(description, reply, 403, "AccessDenied")

    def survives(self, description: str, prefix: str, name: str, content: bytes,
                 bucket: str | None = None) -> None:
        reply = self.truth(prefix, name, bucket)
        if reply.status == 200 and reply.body == content:
            self.checks.ok(f"  {description}")
        else:
            self.checks.bad(f"  {description}", f"ground truth HTTP {reply.status}")

    def absent(self, description: str, prefix: str, name: str, bucket: str | None = None) -> None:
        reply = self.truth(prefix, name, bucket)
        self.expect(f"  {description}", reply, 404)

    # ---- phase: issue -------------------------------------------------------

    def seed(self) -> dict[str, bytes]:
        content = {
            "a": b"table A data " + secrets.token_hex(4).encode(),
            "b": b"table B secret " + secrets.token_hex(4).encode(),
            "outside": b"outside the role " + secrets.token_hex(4).encode(),
            "other": b"another bucket " + secrets.token_hex(4).encode(),
        }
        for bucket in (self.bucket, self.other):
            self.expect(f"setup creates bucket {bucket}", self.setup.call("PUT", f"/{bucket}"), 200)
        for prefix, key in ((TABLE_A, "a"), (TABLE_B, "b"), (OUTSIDE, "outside"), (SIBLING, "b")):
            self.expect(f"setup seeds {prefix}data.txt",
                        self.setup.call("PUT", self.path(prefix, "data.txt"), body=content[key]), 200)
        for prefix in (TABLE_A, TABLE_B):
            self.expect(f"setup seeds {prefix}victim.txt",
                        self.setup.call("PUT", self.path(prefix, "victim.txt"), body=b"victim"), 200)
        self.expect("setup seeds the other bucket",
                    self.setup.call("PUT", self.path("", "data.txt", self.other), body=content["other"]), 200)
        return content

    def tls(self) -> None:
        plain = send(f"http://{self.endpoint.host}", self.vendor_plain_assume())
        if plain.status == 400 and b"HTTP request to an HTTPS server" in plain.body \
                and b"AssumeRoleResponse" not in plain.body:
            self.checks.ok("STS is not served in plaintext: an HTTP AssumeRole gets the TLS "
                           "listener's 400 and no credentials")
        else:
            self.checks.bad("STS is not served in plaintext",
                            f"HTTP {plain.status}: {plain.body[:120]!r}")

    def vendor_plain_assume(self) -> Wire:
        body = urllib.parse.urlencode({"Version": "2011-06-15", "Action": "AssumeRole",
                                       "RoleArn": ROLE_ARN, "RoleSessionName": "plain"}).encode()
        signer = Signer(self.endpoint.host, self.vendor.access_key, self.vendor.secret_key, "sts")
        return signer.sign("POST", "/", headers={"content-type": "application/x-www-form-urlencoded"},
                           body=body, payload_header=False)

    def trust(self) -> None:
        reply, _ = assume_role(self.outsider)
        self.denied("trust: a valid identity the trust policy does not name cannot assume the role",
                    reply)
        anonymous = self.endpoint.send(Wire(
            "POST", "/", (),
            {"host": self.endpoint.host, "content-type": "application/x-www-form-urlencoded"},
            urllib.parse.urlencode({"Version": "2011-06-15", "Action": "AssumeRole",
                                    "RoleArn": ROLE_ARN, "RoleSessionName": "anon"}).encode()))
        self.denied("trust: an unsigned AssumeRole is refused", anonymous)
        reply, _ = assume_role(self.vendor, role_arn=None)
        self.denied("trust: the vendor cannot assume itself without a RoleArn", reply)
        reply, _ = assume_role(self.vendor,
                               role_arn="arn:aws:iam::000000000000:role/does-not-exist")
        self.denied("trust: the vendor cannot assume a role that does not exist", reply)
        reply = self.vendor.sts({"Action": "GetFederationToken", "Name": "escape"})
        self.denied("trust: the vendor cannot mint a federation token", reply)

    def scoped(self, content: dict[str, bytes]) -> dict[str, str] | None:
        reply, creds = assume_role(
            self.vendor, table_policy(self.bucket, TABLE_A, READ_WRITE_DELETE), session="table-a")
        if not self.expect("vend: the vendor assumes the role with a table A session policy",
                           reply, 200) or creds is None:
            return None
        session = session_of(self.endpoint, creds)

        # Inside table A: the operations an Iceberg writer needs.
        self.expect("A: PUT inside table A", session.call(
            "PUT", self.path(TABLE_A, "new.txt"), body=b"written by the session"), 200)
        got = session.call("GET", self.path(TABLE_A, "data.txt"))
        if got.status == 200 and got.body == content["a"]:
            self.checks.ok("A: GET inside table A returns table A data -> 200")
        else:
            self.checks.bad("A: GET inside table A returns table A data", f"HTTP {got.status} {got.code}")
        listing = session.call("GET", f"/{self.bucket}",
                               query=(("list-type", "2"), ("prefix", TABLE_A)))
        if self.expect("A: LIST with the table A prefix", listing, 200) and \
                f"{TABLE_A}data.txt".encode() not in listing.body:
            self.checks.bad("  the table A listing names table A's object")
        self.expect("A: CopyObject within table A", session.call(
            "PUT", self.path(TABLE_A, "copy.txt"),
            headers={"x-amz-copy-source": f"/{self.bucket}/{TABLE_A}data.txt"}), 200)
        self.multipart_inside(session)
        self.expect("A: DELETE inside table A", session.call(
            "DELETE", self.path(TABLE_A, "new.txt")), 204)

        # Table B and every other way out.
        self.denied("B: GET table B", session.call("GET", self.path(TABLE_B, "data.txt")))
        self.denied("B: PUT into table B", session.call(
            "PUT", self.path(TABLE_B, "intruder.txt"), body=b"intruder"))
        self.absent("table B gained no object", TABLE_B, "intruder.txt")
        self.denied("B: DELETE in table B", session.call("DELETE", self.path(TABLE_B, "victim.txt")))
        self.survives("table B's object survives", TABLE_B, "victim.txt", b"victim")
        self.denied("B: LIST with the table B prefix", session.call(
            "GET", f"/{self.bucket}", query=(("list-type", "2"), ("prefix", TABLE_B))))
        self.denied("B: LIST of the whole bucket", session.call(
            "GET", f"/{self.bucket}", query=(("list-type", "2"),)))
        self.denied("B: CopyObject from table B into table A", session.call(
            "PUT", self.path(TABLE_A, "stolen.txt"),
            headers={"x-amz-copy-source": f"/{self.bucket}/{TABLE_B}data.txt"}))
        self.absent("table A gained no copy of table B", TABLE_A, "stolen.txt")
        self.denied("B: initiate a multipart upload into table B", session.call(
            "POST", self.path(TABLE_B, "upload.bin"), query=(("uploads", ""),)))
        foreign = self.setup.call("POST", self.path(TABLE_B, "foreign.bin"), query=(("uploads", ""),))
        upload_id = xml_text(foreign.body, "UploadId")
        if upload_id:
            self.denied("B: upload a part into a table B multipart upload", session.call(
                "PUT", self.path(TABLE_B, "foreign.bin"),
                query=(("partNumber", "1"), ("uploadId", upload_id)), body=b"part"))
            self.setup.call("DELETE", self.path(TABLE_B, "foreign.bin"),
                            query=(("uploadId", upload_id),))
        else:
            self.checks.bad("setup initiates a table B multipart upload", f"HTTP {foreign.status}")
        self.denied("B: GET a sibling prefix that shares table A's name prefix",
                    session.call("GET", self.path(SIBLING, "data.txt")))
        self.denied("B: GET in a bucket outside the role",
                    session.call("GET", self.path("", "data.txt", self.other)))
        self.unverified_body_under_vending(session)
        return creds

    def multipart_inside(self, session: Principal) -> None:
        key = "multipart.bin"
        started = session.call("POST", self.path(TABLE_A, key), query=(("uploads", ""),))
        upload_id = xml_text(started.body, "UploadId")
        if not (self.expect("A: initiate a multipart upload inside table A", started, 200) and upload_id):
            return
        part = b"x" * (5 * 1024 * 1024)
        uploaded = session.call("PUT", self.path(TABLE_A, key),
                                query=(("partNumber", "1"), ("uploadId", upload_id)), body=part)
        etag = uploaded.headers.get("ETag") or uploaded.headers.get("Etag") or ""
        self.expect("A: upload a part inside table A", uploaded, 200)
        body = ('<?xml version="1.0" encoding="UTF-8"?><CompleteMultipartUpload>'
                f"<Part><PartNumber>1</PartNumber><ETag>{etag}</ETag></Part>"
                "</CompleteMultipartUpload>").encode()
        self.expect("A: complete the multipart upload inside table A", session.call(
            "POST", self.path(TABLE_A, key), query=(("uploadId", upload_id),), body=body), 200)

    def unverified_body_under_vending(self, session: Principal) -> None:
        """PR 1's attack, replayed with vended credentials.

        The DeleteObjects body is still not bound to the signature, so the
        swapped request is accepted at the signature layer. The difference is
        whose authority it carries: the session's, which ends at table A.
        """
        a_key, b_key = f"{TABLE_A}victim.txt", f"{TABLE_B}victim.txt"
        signed = session.wire("POST", f"/{self.bucket}", query=(("delete", ""),),
                              body=delete_body(a_key))
        swapped = self.endpoint.send(replace(signed, body=delete_body(b_key)))
        deleted, errors = delete_result(swapped.body)
        survivor = self.truth(TABLE_B, "victim.txt")
        if swapped.status == 200 and not deleted and errors == [(b_key, "AccessDenied")] \
                and survivor.status == 200:
            self.checks.ok("unverified component: a table A DeleteObjects signature with its body "
                           "swapped for a table B key deletes nothing (per-key AccessDenied)")
        else:
            self.checks.bad(
                "unverified component: a swapped DeleteObjects body cannot reach table B",
                f"HTTP {swapped.status}, deleted {deleted}, errors {errors}, "
                f"table B object answers HTTP {survivor.status}")
        honest = self.endpoint.send(signed)
        deleted, errors = delete_result(honest.body)
        if honest.status == 200 and deleted == [a_key] and not errors:
            self.checks.ok("  control: the unchanged signature deletes the table A key")
        else:
            self.checks.bad("  control: the unchanged signature deletes the table A key",
                            f"HTTP {honest.status}, deleted {deleted}, errors {errors}")

    def read_only(self, content: dict[str, bytes]) -> None:
        reply, creds = assume_role(self.vendor, table_policy(self.bucket, TABLE_A, READ_ONLY),
                                   session="read-only")
        if not self.expect("read-only: the vendor assumes the role with a read-only policy",
                           reply, 200) or creds is None:
            return
        session = session_of(self.endpoint, creds)
        self.expect("read-only: GET inside table A", session.call(
            "GET", self.path(TABLE_A, "data.txt")), 200)
        self.denied("read-only: PUT inside table A", session.call(
            "PUT", self.path(TABLE_A, "readonly.txt"), body=b"x"))
        self.absent("no object was written", TABLE_A, "readonly.txt")
        self.denied("read-only: DELETE inside table A", session.call(
            "DELETE", self.path(TABLE_A, "data.txt")))
        self.survives("table A's object survives", TABLE_A, "data.txt", content["a"])

    def intersection(self, content: dict[str, bytes]) -> None:
        reply, creds = assume_role(self.vendor, WIDE_POLICY, session="wide")
        if not self.expect("intersection: a session policy allowing s3:* on every bucket is "
                           "accepted", reply, 200) or creds is None:
            return
        session = session_of(self.endpoint, creds)
        self.expect("intersection: inside the role, the wide session reads table B",
                    session.call("GET", self.path(TABLE_B, "data.txt")), 200)
        self.denied("intersection: GET outside the role's prefix",
                    session.call("GET", self.path(OUTSIDE, "data.txt")))
        self.denied("intersection: PUT outside the role's prefix",
                    session.call("PUT", self.path(OUTSIDE, "escape.txt"), body=b"x"))
        self.absent("nothing was written outside the role", OUTSIDE, "escape.txt")
        self.denied("intersection: GET in a bucket the role does not name",
                    session.call("GET", self.path("", "data.txt", self.other)))
        self.denied("intersection: create a bucket", session.call(
            "PUT", f"/{self.bucket}-escape"))

        reply, creds = assume_role(self.vendor, session="unrestricted")
        if self.expect("control: without a session policy the vendor assumes the role",
                       reply, 200) and creds:
            plain = session_of(self.endpoint, creds)
            self.expect("control: the unrestricted session reads table B, so the table A "
                        "denials come from the session policy",
                        plain.call("GET", self.path(TABLE_B, "data.txt")), 200)
            self.denied("control: the unrestricted session is still bounded by the role",
                        plain.call("GET", self.path(OUTSIDE, "data.txt")))

    def forgery(self, creds: dict[str, str]) -> None:
        token = creds["SessionToken"]
        header, payload, signature = token.split(".")
        claims = json.loads(unb64url(payload))
        session_id = claims.get("sid", "")
        if "spol" not in claims:
            self.checks.bad("the table A session token carries its session policy (spol claim)")
        widened = dict(claims)
        widened.pop("spol", None)
        widened_payload = b64url(json.dumps(widened, separators=(",", ":")).encode())

        def with_token(value: str, access: str | None = None, secret: str | None = None) -> Reply:
            principal = Principal(self.endpoint, access or creds["AccessKeyId"],
                                  secret or creds["SecretAccessKey"], value)
            return principal.call("GET", self.path(TABLE_B, "data.txt"))

        self.expect("forgery: a token with its session policy removed and the original signature",
                    with_token(f"{header}.{widened_payload}.{signature}"), 403, "InvalidAccessKeyId")
        forged_mac = hmac.new(secrets.token_bytes(32), f"{header}.{widened_payload}".encode(),
                              hashlib.sha256).digest()
        self.expect("forgery: the same claims signed with a key the attacker chose",
                    with_token(f"{header}.{widened_payload}.{b64url(forged_mac)}"),
                    403, "InvalidAccessKeyId")
        none_header = b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        self.expect("forgery: the same claims with alg none and no signature",
                    with_token(f"{none_header}.{widened_payload}."), 403, "InvalidAccessKeyId")
        self.expect("forgery: the right token with a wrong secret",
                    with_token(token, secret=secrets.token_urlsafe(30)), 403, "SignatureDoesNotMatch")
        guessed = base64.b64encode(hashlib.sha256(f"secret-key:{session_id}".encode()).digest()).decode()
        self.expect("forgery: a secret derived from the token without the STS signing key",
                    with_token(token, secret=guessed), 403, "SignatureDoesNotMatch")
        _, other = assume_role(self.vendor, table_policy(self.bucket, TABLE_B, READ_WRITE_DELETE),
                               session="table-b")
        if other:
            self.expect("forgery: table B's access key and secret presented with table A's token",
                        with_token(token, other["AccessKeyId"], other["SecretAccessKey"]),
                        403, "InvalidAccessKeyId")
        no_token = Principal(self.endpoint, creds["AccessKeyId"], creds["SecretAccessKey"])
        self.expect("forgery: temporary keys without their session token",
                    no_token.call("GET", self.path(TABLE_A, "data.txt")), 403, "InvalidAccessKeyId")
        chained, _ = assume_role(session_of(self.endpoint, creds), session="chained")
        self.denied("forgery: a vended session cannot re-assume the role to shed its policy", chained)

    def short_session(self) -> dict[str, str] | None:
        before = dt.datetime.now(dt.timezone.utc)
        reply, creds = assume_role(self.vendor, table_policy(self.bucket, TABLE_A, READ_ONLY),
                                   duration=SHORT_DURATION, session="short")
        if not self.expect(f"expiry: the vendor assumes the role for DurationSeconds={SHORT_DURATION}",
                           reply, 200) or creds is None:
            return None
        expires = dt.datetime.fromisoformat(creds["Expiration"].replace("Z", "+00:00"))
        lifetime = (expires - before).total_seconds()
        if SHORT_DURATION - 5 <= lifetime <= SHORT_DURATION + 5:
            self.checks.ok(f"expiry: Expiration is DurationSeconds after issue ({lifetime:.0f}s)")
        else:
            self.checks.bad("expiry: Expiration is DurationSeconds after issue", f"{lifetime:.0f}s")
        self.expect("expiry: the short session works when issued",
                    session_of(self.endpoint, creds).call("GET", self.path(TABLE_A, "data.txt")), 200)
        return creds


def wait_until(moment: dt.datetime) -> None:
    remaining = (moment - dt.datetime.now(dt.timezone.utc)).total_seconds()
    if remaining > 0:
        print(f"      waiting {remaining:.0f}s", flush=True)
        time.sleep(remaining)


def main(argv: list[str]) -> int:
    if len(argv) != 7:
        print(__doc__, file=sys.stderr)
        return 2
    phase, url, ca_file, s3_path, run_path, state_path = argv[1:]
    endpoint = Endpoint(url, ca_file)
    s3_config = json.loads(Path(s3_path).read_text(encoding="utf-8"))
    run_config = json.loads(Path(run_path).read_text(encoding="utf-8"))
    checks = Checks()
    run = Run(endpoint, s3_config, run_config, checks)
    state_file = Path(state_path)

    if phase == "issue":
        short = run.short_session()
        content = run.seed()
        run.tls()
        run.trust()
        scoped = run.scoped(content)
        run.read_only(content)
        run.intersection(content)
        if scoped:
            run.forgery(scoped)
        state_file.write_text(json.dumps({
            "short": short, "scoped": scoped,
            "content_a": content["a"].decode(),
        }), encoding="utf-8")
    else:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        scoped, short = state.get("scoped"), state.get("short")
        content_a = state["content_a"].encode()
        if not scoped or not short:
            checks.bad(f"{phase}: sessions from the issue phase are available")
        elif phase == "restart":
            session = session_of(endpoint, scoped)
            got = session.call("GET", run.path(TABLE_A, "data.txt"))
            if got.status == 200 and got.body == content_a:
                checks.ok("restart: a session issued before the restart still reads table A -> 200")
            else:
                checks.bad("restart: a session issued before the restart still reads table A",
                           f"HTTP {got.status} {got.code}")
            run.denied("restart: and is still denied table B",
                       session.call("GET", run.path(TABLE_B, "data.txt")))
        elif phase == "expire":
            expires = dt.datetime.fromisoformat(short["Expiration"].replace("Z", "+00:00"))
            session = session_of(endpoint, short)
            wait_until(expires - dt.timedelta(seconds=60))
            run.expect("expiry: 60s before Expiration the short session still works",
                       session.call("GET", run.path(TABLE_A, "data.txt")), 200)
            wait_until(expires + dt.timedelta(seconds=15))
            run.expect("expiry: 15s after Expiration the short session is refused",
                       session.call("GET", run.path(TABLE_A, "data.txt")), 403, "InvalidAccessKeyId")
        elif phase == "rotated":
            run.expect("rotation: a session signed with the previous STS key is refused",
                       session_of(endpoint, scoped).call("GET", run.path(TABLE_A, "data.txt")),
                       403, "InvalidAccessKeyId")
            reply, creds = assume_role(run.vendor, table_policy(run.bucket, TABLE_A, READ_ONLY),
                                       session="after-rotation")
            if run.expect("rotation: the vendor obtains a new session under the new key", reply, 200) \
                    and creds:
                run.expect("rotation: the new session reads table A",
                           session_of(endpoint, creds).call("GET", run.path(TABLE_A, "data.txt")), 200)
        else:
            print(f"unknown phase {phase!r}", file=sys.stderr)
            return 2

    print(f"\n{checks.passed} passed, {checks.failed} failed")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
