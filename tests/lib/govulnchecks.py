"""Validate retained govulncheck binary-mode JSON as evidence, not a gate."""

import json
import sys
from pathlib import Path


MESSAGE_KINDS = {"config", "progress", "SBOM", "osv", "finding"}


def parse_messages(raw: str) -> list[dict]:
    """Govulncheck streams JSON objects; it does not promise one per line."""
    decoder = json.JSONDecoder()
    messages = []
    offset = 0
    while offset < len(raw):
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        if offset == len(raw):
            break
        message, offset = decoder.raw_decode(raw, offset)
        if not isinstance(message, dict) or len(message) != 1:
            raise ValueError("each govulncheck message must have exactly one field")
        if next(iter(message)) not in MESSAGE_KINDS:
            raise ValueError("unknown govulncheck message kind")
        messages.append(message)
    if not messages:
        raise ValueError("empty govulncheck report")
    return messages


def validate(raw: str, expected_version: str) -> tuple[int, int]:
    messages = parse_messages(raw)
    config = messages[0].get("config")
    if not isinstance(config, dict):
        raise ValueError("first message must be the scanner configuration")
    if config.get("protocol_version") != "v1.0.0":
        raise ValueError("unexpected govulncheck JSON protocol")
    if config.get("scanner_name") != "govulncheck":
        raise ValueError("report was not produced by govulncheck")
    if expected_version not in config.get("scanner_version", ""):
        raise ValueError("govulncheck version does not match the pin")
    if config.get("scan_mode") != "binary" or config.get("scan_level") != "symbol":
        raise ValueError("report is not a binary symbol-level scan")
    if config.get("db") != "https://vuln.go.dev":
        raise ValueError("unexpected Go vulnerability database")
    if not config.get("db_last_modified"):
        raise ValueError("vulnerability database timestamp was not recorded")

    sboms = [message["SBOM"] for message in messages if "SBOM" in message]
    if len(sboms) != 1 or not isinstance(sboms[0], dict):
        raise ValueError("expected one binary SBOM message")
    if not isinstance(sboms[0].get("modules"), list) or not sboms[0]["modules"]:
        raise ValueError("binary module inventory is missing")
    if not isinstance(sboms[0].get("roots"), list) or not sboms[0]["roots"]:
        raise ValueError("binary scan root is missing")

    findings = [message["finding"] for message in messages if "finding" in message]
    if not all(isinstance(item, dict) and item.get("osv") for item in findings):
        raise ValueError("finding without an advisory identifier")
    return len(sboms[0]["modules"]), len(findings)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: govulnchecks.py REPORT EXPECTED_VERSION", file=sys.stderr)
        return 2
    try:
        raw = Path(sys.argv[1]).read_text(encoding="utf-8")
        modules, findings = validate(raw, sys.argv[2])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid govulncheck evidence: {exc}", file=sys.stderr)
        return 1
    print(f"validated govulncheck binary evidence: {modules} modules, {findings} findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
