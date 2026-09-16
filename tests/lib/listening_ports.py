"""Print decimal listening ports from Linux /proc/net/tcp and /proc/net/tcp6.

This avoids GNU awk's non-portable strtonum, since CI runners can use mawk.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable


def listening_ports(lines: Iterable[str]) -> list[int]:
    ports: set[int] = set()
    for line in lines:
        fields = line.split()
        if len(fields) < 4 or fields[3] != "0A":
            continue
        _, port = fields[1].rsplit(":", 1)
        ports.add(int(port, 16))
    return sorted(ports)


def main() -> None:
    for port in listening_ports(sys.stdin):
        print(port)


if __name__ == "__main__":
    main()
