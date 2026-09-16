#!/usr/bin/env python3
"""Probe what a client that reaches a volume server directly can actually do.

This is the boundary SECURITY.md warns about. The S3 gateway authenticates its
callers, but the volume servers underneath it speak plain HTTP, and whether they
authenticate anyone depends entirely on an operator-supplied security.toml.

The probes bypass the gateway on purpose. They ask the master for a write
assignment and then use it *without* the token the master hands back, and they
read a stored object straight off the volume server by file id. What each one
returns is the real answer to "what does reaching a volume server get you".

Usage:
    directaccess.py <mode> <master-url> <volume-url> <filer-url> <bucket> <key> [token-out]

    mode: baseline  no security.toml is in effect
          secured   write JWTs are configured

Exit status is 0 when the observed behaviour matches what the mode expects.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

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


def fetch(url: str, method: str = "GET", body: bytes | None = None,
          headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(  # noqa: S310
        url, data=body, method=method, headers=headers or {}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except urllib.error.URLError as error:
        return 0, str(error).encode()


def file_id(filer: str, bucket: str, key: str) -> tuple[str | None, str]:
    """Ask the filer where an object's bytes live.

    S3 buckets live under /buckets on the filer. Plain GET returns the object's
    content; ?metadata=true returns the entry, whose chunks carry the file id the
    volume server answers to.
    """
    for path in (f"/buckets/{bucket}/{key}", f"/{bucket}/{key}"):
        status, body = fetch(f"{filer}{path}?metadata=true")
        if status != 200:
            continue
        try:
            document = json.loads(body)
        except json.JSONDecodeError:
            continue
        for chunk in document.get("chunks") or []:
            if chunk.get("file_id"):
                return chunk["file_id"], path
    return None, ""


def filer_serves_content(filer: str, bucket: str, key: str, expected: bytes) -> bool:
    """Whether the filer hands an object's bytes to an unauthenticated caller.

    This is a shorter path to the data than the volume server: no file id lookup,
    no knowledge of the storage layout, just the object's name.
    """
    status, body = fetch(f"{filer}/buckets/{bucket}/{key}")
    return status == 200 and expected in body


def multipart_body(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----seaweedfsubiprobe"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return body, f"multipart/form-data; boundary={boundary}"


def main(argv: list[str]) -> int:
    if len(argv) not in (7, 8):
        print(__doc__, file=sys.stderr)
        return 2
    mode, master, volume, filer, bucket, key = argv[1:7]
    token_out = argv[7] if len(argv) == 8 else None

    # ---- reading an object straight off the volume server -------------------
    fid, path = file_id(filer, bucket, key)
    if not fid:
        bad("the object's file id can be looked up through the filer",
            "no chunk metadata was returned, so the read probe cannot run")
        return 1
    ok(f"the filer discloses the object's location without authentication ({path})")

    # A shorter path to the same data, worth measuring separately: the filer will
    # simply hand over the object.
    serves = False
    for _ in range(10):
        serves = filer_serves_content(filer, bucket, key, b"bytes behind the gateway")
        if serves:
            break
        time.sleep(1)
    if serves:
        ok("the filer serves the object's content without authentication")
    else:
        bad("the filer serves the object's content without authentication",
            "it did not, which is better than documented -- verify and update",
            "SECURITY.md and docs/TLS.md, which both say this path is open")

    read_status, read_body = fetch(f"{volume}/{fid}")

    # ---- writing to the volume server without the master's token ------------
    #
    # Ask in the bucket's own collection first. S3 buckets get a collection of
    # their own, so the default collection may have no writable volume even
    # though the cluster is perfectly healthy -- and an attacker would target the
    # collection that already holds data anyway.
    assignment = {}
    assign_status, assign_body = 0, b""
    for attempt in range(10):
        for query in (f"?collection={bucket}", ""):
            assign_status, assign_body = fetch(f"{master}/dir/assign{query}")
            if assign_status == 200:
                try:
                    assignment = json.loads(assign_body)
                except json.JSONDecodeError:
                    assignment = {}
                if assignment.get("fid"):
                    break
        if assignment.get("fid"):
            break
        if attempt < 9:
            time.sleep(1)

    write_status = None
    if assignment.get("fid"):
        content, content_type = multipart_body("probe.txt", b"written without a token")
        # The master returns an "auth" token when write JWTs are configured. It is
        # deliberately not sent: the question is what an attacker who never had it
        # can do.
        write_status, _ = fetch(
            f"{volume}/{assignment['fid']}",
            method="POST",
            body=content,
            headers={"Content-Type": content_type},
        )

    if write_status is None:
        # Distinguish "the probe could not run" from "the write was refused".
        # Reporting None as a refusal would turn a broken probe into a pass.
        print(f"      note: no write probe ran. /dir/assign returned HTTP "
              f"{assign_status}: {assign_body[:160]!r}")

    print(f"      observed: direct read HTTP {read_status}, direct write HTTP {write_status}")
    if mode == "baseline":
        # This is the exposure the documentation warns about. It has to be shown
        # before the mitigation can be said to change anything.
        if read_status == 200 and read_body:
            ok("without a security.toml, anyone reaching a volume server reads stored objects")
        else:
            bad("without a security.toml, anyone reaching a volume server reads stored objects",
                f"expected HTTP 200 with a body, got {read_status}")
        if write_status in (200, 201):
            ok("without a security.toml, anyone reaching a volume server writes to it")
        else:
            bad("without a security.toml, anyone reaching a volume server writes to it",
                f"expected HTTP 200 or 201, got {write_status}")

    elif mode == "secured":
        if write_status in (401, 403):
            ok("with write JWTs configured, an untokened direct write is refused")
        else:
            bad("with write JWTs configured, an untokened direct write is refused",
                f"expected HTTP 401 or 403, got {write_status}",
                "the volume server is accepting writes from anyone who can reach it")

        rejected_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJmaWQiOiJzZWF3ZWVkZnMtdWJpLW5vbi1kaXNjbG9zdXJlIn0."
            "invalid-signature"
        )
        if token_out:
            with open(token_out, "w", encoding="utf-8") as token_file:
                token_file.write(rejected_token)
        if assignment.get("fid"):
            rejected_status, rejected_body = fetch(
                f"{volume}/{assignment['fid']}",
                method="POST",
                body=content,
                headers={
                    "Authorization": f"Bearer {rejected_token}",
                    "Content-Type": content_type,
                },
            )
        else:
            rejected_status, rejected_body = None, b""
        if (rejected_status in (401, 403)
                and rejected_token.encode() not in rejected_body):
            ok("a rejected JWT is denied without being echoed in the error body")
        else:
            bad("a rejected JWT is denied without being echoed in the error body",
                f"expected HTTP 401 or 403 without the token, got {rejected_status}")

        # The residual risk, asserted rather than hoped away. Upstream states that
        # read JWTs are not supported alongside a filer, and the S3 topology needs
        # a filer, so this path cannot be closed by configuration in a supported
        # deployment. Network isolation is the only control left for it.
        if read_status == 200:
            ok("direct reads remain possible, which is the residual risk this "
               "topology cannot configure away")
        elif read_status in (401, 403):
            bad("direct reads remain possible, which is the residual risk this "
                "topology cannot configure away",
                "reads were refused, so upstream now supports read JWTs with a filer.",
                "That is an improvement: update SECURITY.md and docs/TLS.md, which",
                "both currently state this path stays open.")
        else:
            bad("direct reads remain possible, which is the residual risk this "
                "topology cannot configure away",
                f"unexpected HTTP {read_status}")
    else:
        print(f"unknown mode {mode!r}", file=sys.stderr)
        return 2

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
