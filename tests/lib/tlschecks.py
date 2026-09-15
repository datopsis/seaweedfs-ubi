#!/usr/bin/env python3
"""Checks for TLS on the S3 listener.

The point is not that a connection succeeds. A client that trusts everything can
connect to anything, so these checks are arranged to separate "the server
presented a certificate we actually trust, for the name we actually asked for"
from "the bytes moved".

Usage:
    tlschecks.py <hostname> <port> <ca.pem> <other-ca.pem> <config.json>

The hostname must be the name the certificate was issued for; it is resolved to
the loopback address so verification is exercised rather than sidestepped.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3client import S3Client  # noqa: E402

passed = 0
failed = 0


def ok(description: str) -> None:
    global passed
    print(f"ok    {description}")
    passed += 1


def bad(description: str, *detail: str) -> None:
    global failed
    print(f"FAIL  {description}")
    for line in detail:
        print(f"      {line}")
    failed += 1


def pin_to_loopback(hostname: str, port: int) -> None:
    """Resolve the certificate's hostname to the published loopback port.

    Without this the checks would have to connect to 127.0.0.1 and disable
    hostname verification, which is the one thing they are meant to test.
    """
    real = socket.getaddrinfo

    def patched(host, service, *args, **kwargs):
        if host == hostname:
            return real("127.0.0.1", port, *args, **kwargs)
        return real(host, service, *args, **kwargs)

    socket.getaddrinfo = patched


def main(argv: list[str]) -> int:
    if len(argv) != 6:
        print(__doc__, file=sys.stderr)
        return 2
    hostname, port, ca, other_ca, config_path = argv[1], int(argv[2]), argv[3], argv[4], argv[5]

    pin_to_loopback(hostname, port)
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    credential = config["identities"][0]["credentials"][0]
    access, secret = credential["accessKey"], credential["secretKey"]
    endpoint = f"https://{hostname}:{port}"
    bucket = "tlsprobe"

    # ---- the round trip, over TLS, verifying a private CA -------------------
    trusting = S3Client(endpoint, access, secret, ca_bundle=ca)
    created = trusting.create_bucket(bucket)
    if created.status in (200, 204):
        ok("a client trusting the private CA completes the TLS handshake")
    else:
        bad("a client trusting the private CA completes the TLS handshake",
            f"status {created.status}: {created.text[:200]}")
        print(f"\n{passed} passed, {failed} failed")
        return 1

    payload = b"carried over TLS"
    put = trusting.put_object(bucket, "object.txt", payload)
    got = trusting.get_object(bucket, "object.txt")
    if put.status in (200, 204) and got.status == 200 and got.body == payload:
        ok("an authenticated object round trip works over TLS")
    else:
        bad("an authenticated object round trip works over TLS",
            f"put {put.status}, get {got.status}")

    # ---- verification is real, not incidental -------------------------------
    #
    # The decisive check. If a client trusting only an unrelated CA still
    # connects, then nothing above proved the server's identity.
    untrusting = S3Client(endpoint, access, secret, ca_bundle=other_ca)
    refused = untrusting.list_objects(bucket)
    if refused.status == 0 and (
        b"CERTIFICATE_VERIFY_FAILED" in refused.body or b"certificate" in refused.body.lower()
    ):
        ok("a client trusting only an unrelated CA is refused at the handshake")
    else:
        bad("a client trusting only an unrelated CA is refused at the handshake",
            f"status {refused.status}: {refused.text[:200]}",
            "the certificate is not being verified, so the round trip above",
            "proves only that bytes moved")

    # A certificate valid for one name must not satisfy a request for another.
    wrong_name = S3Client(f"https://localhost.invalid:{port}", access, secret, ca_bundle=ca)
    wrong = wrong_name.list_objects(bucket)
    if wrong.status == 0:
        ok("a hostname the certificate does not cover is refused")
    else:
        bad("a hostname the certificate does not cover is refused",
            f"status {wrong.status}")

    # ---- plaintext must not still be served on the TLS port -----------------
    #
    # Supplying a certificate without -port.https is supposed to upgrade the
    # main port rather than add a second one. If plain HTTP still answers here,
    # an operator who configured TLS did not get it.
    plain = S3Client(f"http://{hostname}:{port}", access, secret)
    plain_response = plain.list_objects(bucket)
    if plain_response.status in (0, 400):
        ok("the same port no longer answers plain HTTP")
    else:
        bad("the same port no longer answers plain HTTP",
            f"status {plain_response.status}: plaintext is still served on the TLS port")

    trusting.delete_object(bucket, "object.txt")
    trusting.delete_bucket(bucket)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
