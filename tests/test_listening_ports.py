"""Native listener-inventory parsing must not depend on GNU awk."""

from __future__ import annotations

import unittest

from lib.listening_ports import listening_ports


class ListeningPortsTests(unittest.TestCase):
    def test_decodes_ipv4_and_ipv6_listeners_and_sorts_them(self) -> None:
        lines = [
            "  sl  local_address rem_address   st\n",
            "   0: 00000000:2475 00000000:0000 0A 0 0 0\n",
            "   1: 00000000000000000000000000000000:1F90 0000:0000 0A 0\n",
            "   2: 00000000:2475 00000000:0000 0A 0 0 0\n",
            "   3: 00000000:0035 00000000:0000 01 0 0 0\n",
        ]
        self.assertEqual(listening_ports(lines), [8080, 9333])

    def test_empty_and_non_listening_input_has_no_ports(self) -> None:
        self.assertEqual(listening_ports(["", "header", "0: 00000000:1F90 x 01"]), [])


if __name__ == "__main__":
    unittest.main()
