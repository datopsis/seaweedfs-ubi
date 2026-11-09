#!/usr/bin/env bash
# Cold cross-version upgrade and rollback into restored pre-upgrade storage.
set -euo pipefail
: "${UPGRADE_FROM_IMAGE:?set the locally built, digest-verified baseline image}"
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export UPGRADE_FROM_IMAGE
exec bash "${REPO_ROOT}/tests/backup-restore.sh"
