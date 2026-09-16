#!/usr/bin/env python3
"""Exercise client-certificate enforcement on a TLS-protected gRPC listener."""

from __future__ import annotations

import socket
import ssl
import sys


# HTTP/2 connection preface plus an empty SETTINGS frame. This reaches the
# protocol gRPC uses instead of stopping after a bare TLS handshake.
HTTP2_PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n\x00\x00\x00\x04\x00\x00\x00\x00\x00"


def attempt(
    host: str,
    port: int,
    ca_file: str,
    cert_file: str | None,
    key_file: str | None,
) -> tuple[bool, str]:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca_file)
    # This check isolates client authentication. Server hostname verification is
    # independently qualified by the S3 TLS suite with a SAN-bearing certificate.
    context.check_hostname = False
    context.set_alpn_protocols(["h2"])
    if cert_file and key_file:
        context.load_cert_chain(cert_file, key_file)

    try:
        with socket.create_connection((host, port), timeout=10) as raw:
            with context.wrap_socket(raw, server_hostname="master") as tls:
                tls.settimeout(10)
                tls.sendall(HTTP2_PREFACE)
                response = tls.recv(9)
                if response:
                    return True, f"accepted and returned {len(response)} HTTP/2 frame bytes"
                return False, "closed without returning an HTTP/2 frame"
    except (BrokenPipeError, ConnectionResetError, ssl.SSLError, TimeoutError) as error:
        return False, f"rejected: {type(error).__name__}: {error}"


def main(argv: list[str]) -> int:
    if len(argv) != 8:
        print(
            "usage: mtlschecks.py host port ca.crt valid.crt valid.key wrong.crt wrong.key",
            file=sys.stderr,
        )
        return 2

    host, port_text, ca_file, valid_cert, valid_key, wrong_cert, wrong_key = argv[1:]
    port = int(port_text)
    failed = 0

    accepted, detail = attempt(host, port, ca_file, valid_cert, valid_key)
    if accepted:
        print("ok    a client certificate from the configured CA reaches the gRPC listener")
    else:
        print("FAIL  a client certificate from the configured CA reaches the gRPC listener")
        print(f"      {detail}")
        failed += 1

    accepted, detail = attempt(host, port, ca_file, None, None)
    if not accepted:
        print("ok    a client presenting no certificate is refused")
    else:
        print("FAIL  a client presenting no certificate is refused")
        print(f"      {detail}")
        failed += 1

    accepted, detail = attempt(host, port, ca_file, wrong_cert, wrong_key)
    if not accepted:
        print("ok    a client certificate from an unrelated CA is refused")
    else:
        print("FAIL  a client certificate from an unrelated CA is refused")
        print(f"      {detail}")
        failed += 1

    print(f"\n{3 - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
