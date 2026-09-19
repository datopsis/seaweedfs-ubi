"""Record and reconcile native CI results without making release claims."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ARCHITECTURES = ("amd64", "arm64")
SUITES = (
    "smoke", "cluster", "s3", "s3-tls", "inter-component",
    "observability", "state-survival", "replication",
    "resource-exhaustion", "backup-restore",
)
SHA = re.compile(r"^[0-9a-f]{40}$")
IMAGE_ID = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
CANONICAL_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


def make_record(architecture: str, commit: str, run_id: str,
                run_attempt: str, image_id: str) -> dict:
    if architecture not in ARCHITECTURES:
        raise ValueError("unsupported architecture")
    if not SHA.fullmatch(commit):
        raise ValueError("commit must be a full Git SHA")
    if not run_id.isdecimal() or int(run_id) < 1:
        raise ValueError("run ID must be positive")
    if not run_attempt.isdecimal() or int(run_attempt) < 1:
        raise ValueError("run attempt must be positive")
    if not IMAGE_ID.fullmatch(image_id):
        raise ValueError("local image ID must be a SHA-256 digest")
    if not image_id.startswith("sha256:"):
        image_id = "sha256:" + image_id
    return {
        "schema_version": 1,
        "evidence_level": "development",
        "source_commit": commit,
        "github_run_id": int(run_id),
        "github_run_attempt": int(run_attempt),
        "architecture": architecture,
        "local_image_id": image_id,
        "passed_suites": list(SUITES),
        "limitations": [
            "Native CI development image, not a release candidate or published digest",
            "Suite-specific one-container or one-host topology; no multi-host claim",
            "No container-hardening criterion or control is asserted by this record",
        ],
    }


def reconcile(records: list[dict], commit: str, run_id: str,
              run_attempt: str) -> dict:
    if len(records) != len(ARCHITECTURES):
        raise ValueError("exactly two native records are required")
    expected = {"source_commit": commit, "github_run_id": int(run_id),
                "github_run_attempt": int(run_attempt), "schema_version": 1,
                "evidence_level": "development", "passed_suites": list(SUITES)}
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("native record must be an object")
        for key, value in expected.items():
            if record.get(key) != value:
                raise ValueError(f"native record has wrong {key}")
        architecture = record.get("architecture")
        if architecture not in ARCHITECTURES or architecture in seen:
            raise ValueError("missing, duplicate, or unsupported architecture")
        seen.add(architecture)
        if not CANONICAL_IMAGE_ID.fullmatch(str(record.get("local_image_id", ""))):
            raise ValueError("invalid local image ID")
        if not isinstance(record.get("limitations"), list) or not record["limitations"]:
            raise ValueError("scope limitations are required")
    return {
        "schema_version": 1,
        "evidence_level": "development",
        "source_commit": commit,
        "github_run_id": int(run_id),
        "github_run_attempt": int(run_attempt),
        "architectures": {r["architecture"]: r["local_image_id"] for r in records},
        "release_eligible": False,
        "standard_conformance": "not assessed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    write = subparsers.add_parser("write")
    write.add_argument("--architecture", required=True)
    write.add_argument("--image-id", required=True)
    verify = subparsers.add_parser("reconcile")
    verify.add_argument("records", nargs=2, type=Path)
    for sub in (write, verify):
        sub.add_argument("--commit", required=True)
        sub.add_argument("--run-id", required=True)
        sub.add_argument("--run-attempt", required=True)
        sub.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "write":
            result = make_record(args.architecture, args.commit, args.run_id,
                                 args.run_attempt, args.image_id)
        else:
            records = [json.loads(path.read_text(encoding="utf-8")) for path in args.records]
            result = reconcile(records, args.commit, args.run_id, args.run_attempt)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
