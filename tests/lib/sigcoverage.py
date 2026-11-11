#!/usr/bin/env python3
"""Measure which parts of a SigV4-signed request the S3 gateway really checks.

Remote signing hands a client a signature it did not compute. The client then
sends the request itself, so the signature is the only thing binding what was
approved to what arrives. If the gateway leaves part of the request outside its
check, the client can change that part after signing and keep the signature.

Each case below signs one request, sends it unchanged, then sends the *same
signature* with exactly one component changed. The secure outcome is a
rejection. Where SeaweedFS does not reject, the case is an exact-outcome canary:
it asserts precisely what is observed today, fails on any other outcome, and
fails with a NOTICE if SeaweedFS starts rejecting, so the documentation that
describes the gap cannot silently go stale.

Two identities are used, both created by the calling script for this run only:
`setup` seeds and inspects objects as ground truth, and `signer` plays the
remote signer (a Lakekeeper-style warehouse identity with bucket-wide rights).
Two prefixes in one test bucket play two tables.

Usage:
    sigcoverage.py <endpoint> <config.json> <bucket>
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import http.client
import json
import sys
import urllib.parse
import uuid
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from xml.etree import ElementTree

from s3client import REGION, Checks, S3Client, _signing_key, identities, xml_text

TABLE_A = "tables/a/"
TABLE_B = "tables/b/"
UNRESERVED = "-_.~"


@dataclass(frozen=True)
class Wire:
    """One request exactly as it goes on the wire."""

    method: str
    path: str
    query: tuple[tuple[str, str], ...] = ()
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


@dataclass(frozen=True)
class Reply:
    status: int
    body: bytes
    headers: dict[str, str]

    @property
    def code(self) -> str | None:
        return xml_text(self.body, "Code")


def _query_string(query: tuple[tuple[str, str], ...]) -> str:
    return "&".join(
        f"{urllib.parse.quote(k, safe=UNRESERVED)}={urllib.parse.quote(v, safe=UNRESERVED)}"
        for k, v in sorted(query)
    )


class Signer:
    """Signs a request the way a remote signing service would, and nothing more."""

    def __init__(self, host: str, access_key: str, secret_key: str, service: str = "s3"):
        self.host = host
        self.access_key = access_key
        self.secret_key = secret_key
        self.service = service

    def sign(
        self,
        method: str,
        path: str,
        query: tuple[tuple[str, str], ...] = (),
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        payload_hash: str | None = None,
        when: dt.datetime | None = None,
        payload_header: bool = True,
    ) -> Wire:
        """payload_header=False signs the body hash without sending it as a
        header, as AWS SDKs do for STS; the server must then hash the body."""
        when = when or dt.datetime.now(dt.timezone.utc)
        amz_date = when.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = when.strftime("%Y%m%d")
        payload_hash = payload_hash or hashlib.sha256(body).hexdigest()
        signed = {name.lower(): value for name, value in (headers or {}).items()}
        signed.setdefault("host", self.host)
        if payload_header:
            signed["x-amz-content-sha256"] = payload_hash
        signed["x-amz-date"] = amz_date

        names = sorted(signed)
        canonical_request = "\n".join(
            [
                method,
                path,
                _query_string(query),
                "".join(f"{name}:{' '.join(signed[name].split())}\n" for name in names),
                ";".join(names),
                payload_hash,
            ]
        )
        scope = f"{date_stamp}/{REGION}/{self.service}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signature = hmac.new(
            _signing_key(self.secret_key, date_stamp, self.service),
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()
        signed["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={';'.join(names)}, Signature={signature}"
        )
        return Wire(method, path, tuple(query), signed, body)


def send(endpoint: str, wire: Wire, context=None) -> Reply:
    """Send exactly these headers. http.client adds nothing it is not told to."""
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme == "https":
        connection = http.client.HTTPSConnection(parsed.netloc, timeout=30, context=context)
    else:
        connection = http.client.HTTPConnection(parsed.netloc, timeout=30)
    target = wire.path
    if wire.query:
        target = f"{target}?{_query_string(wire.query)}"
    try:
        connection.putrequest(wire.method, target, skip_host=True, skip_accept_encoding=True)
        for name, value in wire.headers.items():
            connection.putheader(name, value)
        if wire.body or wire.method in ("PUT", "POST"):
            connection.putheader("content-length", str(len(wire.body)))
        connection.endheaders(wire.body or None)
        response = connection.getresponse()
        return Reply(response.status, response.read(), dict(response.getheaders()))
    except OSError as error:
        return Reply(0, str(error).encode(), {})
    finally:
        connection.close()


def with_header(wire: Wire, name: str, value: str | None) -> Wire:
    """A copy of wire with one header changed, added, or (value None) removed."""
    headers = {k: v for k, v in wire.headers.items() if k.lower() != name.lower()}
    if value is not None:
        headers[name.lower()] = value
    return replace(wire, headers=headers)


def delete_body(*keys: str) -> bytes:
    objects = "".join(f"<Object><Key>{key}</Key></Object>" for key in keys)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Delete><Quiet>false</Quiet>{objects}</Delete>"
    ).encode()


def delete_result(body: bytes) -> tuple[list[str], list[tuple[str, str]]]:
    """(deleted keys, [(error key, error code)]) from a DeleteObjects response."""
    deleted: list[str] = []
    errors: list[tuple[str, str]] = []
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return deleted, errors
    for element in root:
        tag = element.tag.rsplit("}", 1)[-1]
        values = {child.tag.rsplit("}", 1)[-1]: (child.text or "") for child in element}
        if tag == "Deleted":
            deleted.append(values.get("Key", ""))
        elif tag == "Error":
            errors.append((values.get("Key", ""), values.get("Code", "")))
    return deleted, errors


class Coverage:
    """Collects the per-component verdicts the documentation is written from."""

    def __init__(self, checks: Checks) -> None:
        self.checks = checks
        self.rows: list[tuple[str, str, str]] = []

    def control(self, description: str, reply: Reply, *statuses: int) -> bool:
        return self.checks.expect(f"control: {description}", reply.status, *statuses)

    def rejected(
        self, component: str, description: str, reply: Reply, status: int, code: str
    ) -> bool:
        """The secure outcome: the changed request is refused with this exact error."""
        label = f"[{component}] {description}"
        if reply.status == status and reply.code == code:
            self.checks.ok(f"{label} -> {status} {code}")
            self.rows.append((component, "verified", f"{status} {code}"))
            return True
        self.checks.bad(
            label,
            f"expected HTTP {status} {code}, got HTTP {reply.status} {reply.code}",
            "SeaweedFS accepted or mis-handled a request changed after signing.",
        )
        self.rows.append((component, "NOT VERIFIED (regression)", f"{reply.status} {reply.code}"))
        return False

    def canary(
        self,
        component: str,
        description: str,
        reply: Reply,
        accepted: bool,
        detail: str,
    ) -> None:
        """An exact-outcome canary for a component SeaweedFS does not verify."""
        label = f"[{component}] CANARY {description}"
        if accepted:
            self.checks.ok(f"{label} -> accepted ({detail})")
            self.rows.append((component, "not verified (canary)", detail))
            return
        if (reply.status, reply.code) in (
            (403, "SignatureDoesNotMatch"),
            (400, "XAmzContentSHA256Mismatch"),
            (400, "BadDigest"),
            (400, "InvalidDigest"),
        ):
            self.checks.bad(
                label,
                f"NOTICE: SeaweedFS now REJECTS this change (HTTP {reply.status} {reply.code}).",
                "That is the secure behaviour and an improvement. Turn this canary into a",
                "secure assertion and update docs/REMOTE-SIGNING.md, SECURITY.md,",
                "docs/THREAT-MODEL.md (TM-16), and docs/SUPPORT.md, which describe the gap.",
            )
            self.rows.append((component, "NOW VERIFIED (update docs)", f"{reply.status} {reply.code}"))
            return
        self.checks.bad(
            label,
            f"unexpected outcome HTTP {reply.status} {reply.code}: {detail}",
            "Neither the documented gap nor a clean rejection; investigate before",
            "changing any documentation.",
        )
        self.rows.append((component, "UNEXPECTED", f"{reply.status} {reply.code}"))

    def summary(self) -> None:
        print("\nSignature coverage summary (this run):")
        width = max(len(row[0]) for row in self.rows) if self.rows else 10
        for component, verdict, observed in self.rows:
            print(f"  {component:<{width}}  {verdict:<28}  {observed}")


def run(endpoint: str, config_path: Path, bucket: str) -> int:
    creds = identities(json.loads(config_path.read_text(encoding="utf-8")))
    for required in ("setup", "signer"):
        if required not in creds:
            raise SystemExit(f"the config has no credentials for {required!r}")

    host = urllib.parse.urlparse(endpoint).netloc
    setup = S3Client(endpoint, *creds["setup"])
    signer_client = S3Client(endpoint, *creds["signer"])
    signer = Signer(host, *creds["signer"])
    checks = Checks()
    coverage = Coverage(checks)
    run_tag = uuid.uuid4().hex[:8]

    def obj(prefix: str, name: str) -> str:
        return f"/{bucket}/{prefix}{name}"

    def ground_truth(prefix: str, name: str) -> tuple[int, bytes]:
        reply = setup.get_object(bucket, f"{prefix}{name}")
        return reply.status, reply.body

    # ---- the test bucket and its two "tables" ------------------------------
    if not checks.expect("setup creates the run's test bucket", setup.create_bucket(bucket).status, 200):
        return 1
    content_a = f"table A row {run_tag}".encode()
    secret_b = f"table B secret {run_tag}".encode()
    seeds = {
        (TABLE_A, "data.txt"): content_a,
        (TABLE_B, "data.txt"): secret_b,
        (TABLE_A, "victim-path.txt"): b"a",
        (TABLE_B, "victim-path.txt"): b"b",
    }
    for variant in ("sha", "md5", "crc"):
        seeds[(TABLE_A, f"victim-{variant}.txt")] = b"a"
        seeds[(TABLE_B, f"victim-{variant}.txt")] = b"b"
    for (prefix, name), data in seeds.items():
        checks.expect(
            f"setup seeds {prefix}{name}",
            setup.put_object(bucket, f"{prefix}{name}", data).status,
            200,
        )

    # ---- control ----------------------------------------------------------
    get_a = signer.sign("GET", obj(TABLE_A, "data.txt"))
    reply = send(endpoint, get_a)
    if reply.status == 200 and reply.body == content_a:
        checks.ok("control: a correctly signed request is accepted and returns table A")
    else:
        checks.bad(
            "control: a correctly signed request is accepted and returns table A",
            f"HTTP {reply.status} {reply.code}; every later verdict would be meaningless",
        )
        return 1

    # ---- 1. HTTP method ----------------------------------------------------
    coverage.control("signed GET of table A", send(endpoint, get_a), 200)
    coverage.rejected(
        "method",
        "a signed GET replayed as DELETE",
        send(endpoint, replace(get_a, method="DELETE")),
        403,
        "SignatureDoesNotMatch",
    )
    status, _ = ground_truth(TABLE_A, "data.txt")
    checks.expect("  table A object survives the method change", status, 200)

    # ---- 2. Path -----------------------------------------------------------
    reply = send(endpoint, replace(get_a, path=obj(TABLE_B, "data.txt")))
    coverage.rejected("path", "a signed GET of table A redirected to table B", reply, 403, "SignatureDoesNotMatch")
    if secret_b in reply.body:
        checks.bad("  table B content is not disclosed by the redirected GET")
    else:
        checks.ok("  table B content is not disclosed by the redirected GET")

    delete_a = signer.sign("DELETE", obj(TABLE_A, "victim-path.txt"))
    coverage.control("signed DELETE inside table A", send(endpoint, delete_a), 204)
    coverage.rejected(
        "path",
        "a signed DELETE in table A redirected to table B",
        send(endpoint, replace(delete_a, path=obj(TABLE_B, "victim-path.txt"))),
        403,
        "SignatureDoesNotMatch",
    )
    status, _ = ground_truth(TABLE_B, "victim-path.txt")
    checks.expect("  table B object survives the redirected DELETE", status, 200)

    # ---- 3. Query string ---------------------------------------------------
    list_a = signer.sign("GET", f"/{bucket}", query=(("list-type", "2"), ("prefix", TABLE_A)))
    reply = send(endpoint, list_a)
    if coverage.control("signed listing of table A", reply, 200) and TABLE_B.encode() in reply.body:
        checks.bad("  the table A listing names no table B key")
    coverage.rejected(
        "query: value changed",
        "a signed listing of table A re-pointed at table B",
        send(endpoint, replace(list_a, query=(("list-type", "2"), ("prefix", TABLE_B)))),
        403,
        "SignatureDoesNotMatch",
    )
    coverage.rejected(
        "query: parameter removed",
        "a signed listing of table A with its prefix removed",
        send(endpoint, replace(list_a, query=(("list-type", "2"),))),
        403,
        "SignatureDoesNotMatch",
    )
    coverage.rejected(
        "query: parameter added",
        "a signed listing of table A with a parameter added",
        send(endpoint, replace(list_a, query=list_a.query + (("start-after", TABLE_A),))),
        403,
        "SignatureDoesNotMatch",
    )

    # ---- 4. Signed headers -------------------------------------------------
    copy_source_a = f"/{bucket}/{TABLE_A}data.txt"
    copy_source_b = f"/{bucket}/{TABLE_B}data.txt"
    copy = signer.sign(
        "PUT", obj(TABLE_A, "copy.txt"), headers={"x-amz-copy-source": copy_source_a}
    )
    coverage.control("signed CopyObject inside table A", send(endpoint, copy), 200)
    coverage.rejected(
        "signed header: value changed",
        "a signed copy inside table A re-sourced from table B",
        send(endpoint, with_header(copy, "x-amz-copy-source", copy_source_b)),
        403,
        "SignatureDoesNotMatch",
    )
    status, data = ground_truth(TABLE_A, "copy.txt")
    if status == 200 and data == content_a:
        checks.ok("  table A's copy still holds table A data, not table B's")
    else:
        checks.bad("  table A's copy still holds table A data, not table B's", f"HTTP {status}")

    plain = signer.sign("PUT", obj(TABLE_A, "plain.txt"), body=b"plain")
    coverage.control("signed PutObject inside table A", send(endpoint, plain), 200)
    coverage.rejected(
        "unsigned x-amz header added",
        "a signed PUT with an unsigned x-amz-copy-source from table B added",
        send(endpoint, with_header(plain, "x-amz-copy-source", copy_source_b)),
        403,
        "SignatureDoesNotMatch",
    )
    status, data = ground_truth(TABLE_A, "plain.txt")
    if status == 200 and data == b"plain":
        checks.ok("  the target still holds what was signed, not a copy of table B")
    else:
        checks.bad("  the target still holds what was signed, not a copy of table B", f"HTTP {status}")

    ranged = signer.sign("GET", obj(TABLE_A, "data.txt"), headers={"range": "bytes=0-3"})
    coverage.control("signed ranged GET", send(endpoint, ranged), 206)
    coverage.rejected(
        "signed header: removed",
        "a signed ranged GET with its signed Range header removed",
        send(endpoint, with_header(ranged, "range", None)),
        403,
        "SignatureDoesNotMatch",
    )
    other_host = "localhost:" + host.rsplit(":", 1)[1] if ":" in host else "localhost"
    coverage.rejected(
        "signed header: host",
        "a signed GET sent with a different Host",
        send(endpoint, with_header(get_a, "host", other_host)),
        403,
        "SignatureDoesNotMatch",
    )
    earlier = (
        dt.datetime.strptime(get_a.headers["x-amz-date"], "%Y%m%dT%H%M%SZ") - dt.timedelta(seconds=1)
    ).strftime("%Y%m%dT%H%M%SZ")
    coverage.rejected(
        "signed header: x-amz-date",
        "a signed GET with its x-amz-date moved one second",
        send(endpoint, with_header(get_a, "x-amz-date", earlier)),
        403,
        "SignatureDoesNotMatch",
    )

    # ---- 5. Payload hash: the declared value -------------------------------
    declared = signer.sign("PUT", obj(TABLE_A, "declared.txt"), body=b"declared")
    coverage.control("signed PutObject with a declared payload hash", send(endpoint, declared), 200)
    coverage.rejected(
        "payload hash: declared value changed",
        "the signed x-amz-content-sha256 replaced with UNSIGNED-PAYLOAD",
        send(endpoint, with_header(declared, "x-amz-content-sha256", "UNSIGNED-PAYLOAD")),
        403,
        "SignatureDoesNotMatch",
    )

    # ---- 6. Payload: the body against its declared hash --------------------
    body_one, body_two = b"signed body one", b"swapped body 2!"
    put = signer.sign("PUT", obj(TABLE_A, "put-body.txt"), body=body_one)
    coverage.control("signed PutObject with a declared body hash", send(endpoint, put), 200)
    coverage.rejected(
        "body: PutObject",
        "a signed PutObject sent with a different body of the same length",
        send(endpoint, replace(put, body=body_two)),
        400,
        "XAmzContentSHA256Mismatch",
    )
    status, data = ground_truth(TABLE_A, "put-body.txt")
    if status == 200 and data == body_one:
        checks.ok("  the stored object is still the signed body")
    else:
        checks.bad("  the stored object is still the signed body", f"HTTP {status}, {data!r}")

    initiated = signer_client.initiate_multipart(bucket, f"{TABLE_A}multipart.bin")
    upload_id = xml_text(initiated.body, "UploadId")
    if upload_id:
        part = signer.sign(
            "PUT",
            obj(TABLE_A, "multipart.bin"),
            query=(("partNumber", "1"), ("uploadId", upload_id)),
            body=body_one,
        )
        coverage.control("signed UploadPart with a declared body hash", send(endpoint, part), 200)
        coverage.rejected(
            "body: UploadPart",
            "a signed UploadPart sent with a different body of the same length",
            send(endpoint, replace(part, body=body_two)),
            400,
            "XAmzContentSHA256Mismatch",
        )
        signer_client.abort_multipart(bucket, f"{TABLE_A}multipart.bin", upload_id)
    else:
        checks.bad("control: a multipart upload can be initiated in table A", f"HTTP {initiated.status}")

    # DeleteObjects carries its keys in the body. A remote signer authorizes the
    # keys it is shown; the gateway must bind the body to that signature or the
    # client can delete keys the signer never saw.
    def delete_objects_case(
        variant: str, extra: Callable[[bytes], dict[str, str]] | None, binding: str
    ) -> None:
        a_key, b_key = f"{TABLE_A}victim-{variant}.txt", f"{TABLE_B}victim-{variant}.txt"
        body_a, body_b = delete_body(a_key), delete_body(b_key)
        headers = dict(extra(body_a)) if extra else {}
        signed = signer.sign("POST", f"/{bucket}", query=(("delete", ""),), headers=headers, body=body_a)
        reply = send(endpoint, signed)
        deleted, errors = delete_result(reply.body)
        if reply.status == 200 and deleted == [a_key] and not errors:
            checks.ok(f"control: signed DeleteObjects for table A ({binding}) deletes only {a_key}")
        else:
            checks.bad(
                f"control: signed DeleteObjects for table A ({binding}) deletes only {a_key}",
                f"HTTP {reply.status}, deleted {deleted}, errors {errors}",
            )
        reply = send(endpoint, replace(signed, body=body_b))
        deleted, errors = delete_result(reply.body)
        b_status, _ = ground_truth(TABLE_B, f"victim-{variant}.txt")
        accepted = reply.status == 200 and deleted == [b_key] and not errors and b_status == 404
        coverage.canary(
            f"body: DeleteObjects ({binding})",
            "the signed table A key list swapped for a table B key",
            reply,
            accepted,
            f"HTTP {reply.status}; response lists {deleted or 'nothing'} deleted;"
            f" table B object now answers HTTP {b_status}",
        )

    delete_objects_case("sha", None, "x-amz-content-sha256 only")
    delete_objects_case(
        "md5",
        lambda body: {"content-md5": base64.b64encode(hashlib.md5(body).digest()).decode()},  # noqa: S324
        "plus signed Content-MD5",
    )
    delete_objects_case(
        "crc",
        lambda body: {
            "x-amz-checksum-crc32": base64.b64encode(zlib.crc32(body).to_bytes(4, "big")).decode(),
            "x-amz-sdk-checksum-algorithm": "CRC32",
        },
        "plus signed x-amz-checksum-crc32",
    )

    # ---- 7. UNSIGNED-PAYLOAD -----------------------------------------------
    # SigV4 by design leaves the body out when the signer signs UNSIGNED-PAYLOAD.
    # Recorded so the boundary is explicit: the change stays on the signed key.
    unsigned = signer.sign(
        "PUT", obj(TABLE_A, "unsigned.txt"), body=body_one, payload_hash="UNSIGNED-PAYLOAD"
    )
    coverage.control("signed PutObject with UNSIGNED-PAYLOAD", send(endpoint, unsigned), 200)
    reply = send(endpoint, replace(unsigned, body=body_two))
    status, data = ground_truth(TABLE_A, "unsigned.txt")
    coverage.canary(
        "body: UNSIGNED-PAYLOAD PutObject",
        "the body of an UNSIGNED-PAYLOAD PUT swapped after signing (SigV4 by design)",
        reply,
        reply.status == 200 and status == 200 and data == body_two,
        f"HTTP {reply.status}; the signed key in table A now holds the swapped body",
    )

    coverage.summary()
    print(f"\n{checks.passed} passed, {checks.failed} failed")
    return 1 if checks.failed else 0


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    return run(argv[1], Path(argv[2]), argv[3])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
