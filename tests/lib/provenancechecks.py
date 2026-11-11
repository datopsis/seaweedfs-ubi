"""Check image inspection labels against independently supplied build inputs."""

import hashlib
import json
import pathlib
import re
import sys


REVISION = "org.opencontainers.image.revision"
LOCK = "io.datopsis.artifact-lock.sha256"


def validate(inspection, revision, lock_bytes):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("expected source revision must be a full commit SHA")
    if not isinstance(inspection, list) or len(inspection) != 1:
        raise ValueError("expected exactly one inspected image")
    labels = inspection[0].get("Config", {}).get("Labels") or {}
    expected = {REVISION: revision, LOCK: hashlib.sha256(lock_bytes).hexdigest()}
    for name, value in expected.items():
        actual = labels.get(name)
        if actual != value:
            raise ValueError(f"{name}: expected {value}, got {actual!r}")
    return expected


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: provenancechecks.py INSPECT_JSON SOURCE_COMMIT LOCK_FILE")
    try:
        labels = validate(
            json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")),
            sys.argv[2],
            pathlib.Path(sys.argv[3]).read_bytes(),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        sys.exit(f"REFUSED: image provenance: {error}")
    for name, value in labels.items():
        print(f"{name}={value}")


if __name__ == "__main__":
    main()
