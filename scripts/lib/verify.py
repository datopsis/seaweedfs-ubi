#!/usr/bin/env python3
"""Verify an extracted SeaweedFS binary against the reviewed artifact lock.

Every check here is offline and deterministic, so the admission gate's own
refusals can be tested without a network or a registry. Signature verification
is deliberately not part of this module: it needs cosign and a registry, and it
runs in fetch-artifacts.sh before extraction.

Usage:
    verify.py <lock.json> <arch> <binary-path>

Exit status:
    0  every recorded measurement matched
    1  a measurement disagreed with the lock, or the lock has no such entry
    2  the invocation itself was wrong
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ELF_MACHINES = {0x03: "x86", 0x3E: "x86-64", 0xB7: "aarch64", 0x28: "arm"}
PT_INTERP = 3
PT_DYNAMIC = 2


class Refused(Exception):
    """A recorded measurement did not match, so the artifact is not admitted."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_elf(path: Path) -> dict:
    """Return the ELF facts the lock records, without shelling out to readelf."""
    with path.open("rb") as handle:
        header = handle.read(64)
        if len(header) < 64 or header[:4] != b"\x7fELF":
            raise Refused(f"{path} is not an ELF binary")
        if header[4] != 2:
            raise Refused(f"{path} is not ELF64")
        endian = "<" if header[5] == 1 else ">"
        machine = struct.unpack_from(endian + "H", header, 18)[0]
        phoff = struct.unpack_from(endian + "Q", header, 32)[0]
        phentsize, phnum = struct.unpack_from(endian + "HH", header, 54)
        if phentsize < 4 or phnum == 0:
            raise Refused(f"{path} has no usable program headers")
        handle.seek(phoff)
        table = handle.read(phentsize * phnum)
    if len(table) < phentsize * phnum:
        raise Refused(f"{path} program header table is truncated")
    kinds = {
        struct.unpack_from(endian + "I", table, index * phentsize)[0]
        for index in range(phnum)
    }
    return {
        "elfMachine": ELF_MACHINES.get(machine, hex(machine)),
        "staticallyLinked": PT_INTERP not in kinds and PT_DYNAMIC not in kinds,
    }


def embedded_commit(path: Path, expected: str) -> bool:
    """Look for the commit string the upstream build stamps into the binary.

    The version *number* is computed at runtime from a numeric constant and is
    therefore absent from the file, so the commit is the only identifier that can
    be checked without executing the binary.
    """
    pattern = re.compile(re.escape(expected).encode("ascii"))
    with path.open("rb") as handle:
        tail = b""
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            if pattern.search(tail + block):
                return True
            tail = block[-64:]
    return False


def verify(lock_path: Path, arch: str, binary: Path) -> list[str]:
    """Return the list of confirmed checks, or raise Refused on the first failure."""
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Refused(f"cannot read the artifact lock {lock_path}: {error}") from error

    entry = lock.get("architectures", {}).get(arch)
    if entry is None:
        known = ", ".join(sorted(lock.get("architectures", {}))) or "none"
        raise Refused(
            f"the artifact lock has no entry for architecture {arch!r} "
            f"(recorded architectures: {known})"
        )
    recorded = entry.get("binary", {})
    if not binary.is_file():
        raise Refused(f"{binary} does not exist, so nothing can be admitted")

    confirmed = []

    actual_size = binary.stat().st_size
    if actual_size != recorded.get("size"):
        raise Refused(
            f"size mismatch for {arch}: the lock records "
            f"{recorded.get('size')} bytes, the file is {actual_size} bytes"
        )
    confirmed.append(f"size {actual_size} bytes")

    actual_sha = sha256_of(binary)
    if actual_sha != recorded.get("sha256"):
        raise Refused(
            f"SHA-256 mismatch for {arch}:\n"
            f"  lock:  {recorded.get('sha256')}\n"
            f"  file:  {actual_sha}"
        )
    confirmed.append(f"sha256 {actual_sha}")

    elf = read_elf(binary)
    if elf["elfMachine"] != recorded.get("elfMachine"):
        raise Refused(
            f"ELF machine mismatch for {arch}: the lock records "
            f"{recorded.get('elfMachine')!r}, the file is {elf['elfMachine']!r}"
        )
    confirmed.append(f"ELF machine {elf['elfMachine']}")

    if elf["staticallyLinked"] != bool(recorded.get("staticallyLinked")):
        state = "statically" if elf["staticallyLinked"] else "dynamically"
        raise Refused(
            f"linkage mismatch for {arch}: the lock records "
            f"staticallyLinked={recorded.get('staticallyLinked')}, "
            f"the file is {state} linked. A dynamically linked upstream build "
            f"would change the runtime requirements of this image and must be "
            f"reviewed, not absorbed."
        )
    confirmed.append(
        "statically linked" if elf["staticallyLinked"] else "dynamically linked"
    )

    commit = recorded.get("embeddedCommit")
    if commit:
        if not embedded_commit(binary, commit):
            raise Refused(
                f"the {arch} binary does not contain the recorded commit "
                f"{commit!r}, so it was not built from the reviewed commit"
            )
        confirmed.append(f"embedded commit {commit}")

    marker = lock.get("variant", {}).get("versionMarker")
    if marker:
        if not embedded_commit(binary, marker):
            raise Refused(
                f"the {arch} binary does not contain the variant marker "
                f"{marker!r}, so it is not the "
                f"{lock.get('variant', {}).get('name')!r} build"
            )
        confirmed.append(f"variant marker {marker}")

    return confirmed


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        confirmed = verify(Path(argv[1]), argv[2], Path(argv[3]))
    except Refused as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1
    for check in confirmed:
        print(f"  verified: {check}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
