#!/usr/bin/env bash
# Exercise the separated roles with structured logs and one explicit metrics
# listener per role. The ordinary cluster suite keeps metrics disabled and pins
# the default listener inventory; this wrapper qualifies the opt-in profile.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export TEST_OBSERVABILITY=true
exec "${REPO_ROOT}/tests/cluster.sh" "$@"
