# Agent guidance

Follow the repository guidance in `CLAUDE.md`, including its security,
verification, documentation, and Git conventions.

Do not weaken the rootless runtime, read-only-root compatibility, the locked
and digest-verified artifact policy, the supported-role allowlist, the
fail-closed S3 authentication guard, the explicit-data-directory requirement,
vulnerability gates, the SCAP evidence boundary, or the signed-release process
merely to make a test or release pass.

Never present the recorded upstream tarball digests as publisher verification,
and never present the upstream `.md5` sidecar as an integrity control. Upstream
publishes no signature and no SHA-256 manifest; `docs/ARTIFACT-ACQUISITION.md`
will state the resulting limitation and it must stay accurate.

Never let a single-container test result stand in as evidence for a replicated
or multi-node topology.

Never add `Co-Authored-By`, AI, assistant, or tool-attribution trailers to
commits. Tool attribution belongs in tool logs, not Git history.
