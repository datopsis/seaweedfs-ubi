# Phase A: verified TLS qualification of SeaweedFS 4.53

**Phase A is blocked, not complete.** The pinned, unmodified binary's gRPC
client policy checks certificate chains and an identity allowlist but does not
bind the server certificate's DNS SAN to the target hostname. The native
correct-CN/wrong-SAN tests are exact-outcome canaries: they require the observed
acceptance with a real object write/read/delete, record `BLOCKER`, and fail if
that behavior changes. A green canary suite is not TLS acceptance.

This work implements dispatch item 2 of the
[lakehouse TLS plan](https://github.com/datopsis/lakehouse-integration/blob/main/docs/TLS-PLAN.md).
Its scope is transport encryption and server/peer identity. **User authentication
via OpenID belongs to Phase B.** Existing S3 credentials remain necessary; TLS
client identity does not implement user authorization or tenant isolation on
filer/volume APIs. Their private-network boundary remains mandatory.

## Profile and listeners

`tests/tls/qualify.py` generates a fresh CA and separate serverAuth and
clientAuth leaves per role on every run. HTTPS and gRPC use independently
mutable server files so a test can isolate one protocol. The four role
containers receive only their own server/client keys and the public CA. The
CA key, unrelated root, and adversarial certificates stay outside the cluster.
No key or raw container log is uploaded or committed. Filer and S3 also share a
throwaway filer-admin JWT signing key so a valid application token can accompany
the S3 administrative RPC probe; this avoids confusing application authorization
with TLS enforcement. Tokens travel through a private header file, not command
arguments. Role logs are checked for private-key and signing-secret disclosure.

| Role | HTTPS | gRPC | Inbound gRPC client CNs (plus the test provisioner) |
| --- | --- | --- | --- |
| master | 9333 | 19333 | master-client, volume-client, filer-client |
| volume | 8080 | 18080 | master-client, filer-client, s3-client |
| filer | 8888 | 18888 | filer-client, s3-client |
| S3 | 8333 | 18333 | filer-client |

`probe-client` is a separate test provisioner identity admitted for direct
listener operations. The actual roles never share that identity. The filer
uses per-target master/volume/S3 server allowlists. Volume permits master;
S3's generic `grpc.client` permits filer. Master uses `master,volume` because
its single native client option serves both targets; it cannot express a
per-call target restriction in this path. No wildcard allowlist is used.

Every role enables `https.client` with CA verification and its own client leaf.
Master, volume, and filer use `https.<role>.cert/key/ca`. The filer explicitly
keeps `disable_tls_verify_client_cert=false`. S3 uses `-cert.file`, `-key.file`,
`-cacert.file`, and `-tlsVerifyClientCert=true`, with **no `-port.https`**.
Unlike the plan's external S3 recommendation, this qualification requires S3
client certificates to meet the owner's stricter every-listener decision.
External lakehouse clients without a client-certificate configuration cannot
use this stricter profile; that integration contract remains unresolved.

Containers retain non-root UID 1000, read-only root, no capabilities, and
no-new-privileges. Only declared data volumes are writable. Exact TCP listener
inventories are read from both `/proc/net/tcp` and `/proc/net/tcp6`. External
probes use both IPv4 and IPv6 published loopback addresses with identical
assertions; extra
listeners, including metrics, debugging, Iceberg or Lance, fail the test.

## Fail-closed preflight

`scripts/lib/tls_profile.py` is a **host-side validator**, not a new image
entrypoint guard. The qualification harness calls it before starting anything.
The image's existing defaults and guards remain unchanged. An arbitrary
operator deployment that does not run preflight has no new guard from this PR.

The bounded recipe is defined by `security(role)` and `arguments(role)` in that
module. The validator parses TOML and compares the complete role policy,
including target allowlists, HTTPS verification, exact command arguments, and
empty environment overrides. It rejects missing/malformed material, mismatched
keys, wrong roles, untrusted/expired leaves, hostname mismatches, unexpected
files, symlinks, extra flags, duplicate flags, alternate Go flag spellings,
extra listeners, and environment-based policy overrides. It validates chain,
purpose and hostname with OpenSSL. A valid profile still cannot repair native
gRPC hostname verification.

For an already rendered role directory and a JSON manifest containing `argv`
and `environment`, run:

```console
python3 scripts/lib/tls_profile.py /path/to/role-config filer /path/to/launch.json
```

Only the bounded recipe is accepted. This is not a general TOML linter or a
production deployment launcher. Keep configuration immutable between preflight
and startup; do not introduce higher-priority `security.toml` files in `/data`
or `$HOME/.seaweedfs` or inject `WEED_` environment overrides.

## Test oracles and evidence

Both native CI architectures run the same Python harness in the reusable
`tls.yml` workflow against images assembled by the existing verified
acquisition/offline build. The `native image` aggregate requires this TLS matrix
as well as the existing native functional/scanner matrix and its evidence
reconciliation. All existing
functional tests and scanner inventory steps remain intact.

The artifact `development-tls-<architecture>` contains only a JSON coverage
manifest with source revision, lock digest, architecture, expected and actual
outcomes, and explicit blockers. It always records `phase_a_complete=false`.
CI uploads it on failure as well. Private PKI and raw logs are deleted during
cleanup. Runtime findings are provisional until the actual PR run is inspected.

- Fresh curl processes exercise actual unary RPCs on all four gRPC listeners,
  requiring `grpc-status: 0`; HTTPS uses a real health route. These are separate
  from the signed S3 write, byte-exact read, delete, and post-delete 404 checks.
- Every listener refuses no client certificate, wrong-root and expired clients,
  a wrong client trust bundle, and plaintext, including a separate plaintext S3 root POST. A certificate failure must be a
  TLS-specific error, never an application 403 or a timeout. Each negative has
  valid operations immediately before and after it.
- Every gRPC listener additionally refuses an actual disallowed role's client
  certificate from the trusted CA. HTTPS has no native CN role allowlist;
  client-certificate chain verification is its peer boundary.
- Every listener is restarted with correct-CN/wrong-SAN, wrong-root, expired, and swapped-role
  server leaves. The strict external client must report certificate verification
  failure. These probes do not qualify SeaweedFS's own outbound verifier.
- Native gRPC canaries replace only the master's, volume's or filer's gRPC
  server SAN and restart all role processes to clear cached connections. Real
  S3 write/read/delete must still succeed, proving the native gap. Restoring
  valid leaves must restore the positive controls too.

## Remaining evidence and blockers

- Correct-CN/wrong-SAN native gRPC acceptance blocks Phase A. Changing policy
  to accept that outcome as secure or patching the admitted binary is forbidden.
  A separately reviewed upstream fix/release is required.
- Native outgoing S3 gRPC callback identity mutations are not yet verified;
  direct strict-client probes of 18333 cannot substitute for that evidence.
- The full native per-edge wrong-root/expiry/role-swap matrix, redirect and
  advertised-address coverage, and post-recreation plaintext coverage must not
  be inferred from external curl probes or the cluster success control.
- STS credential vending and real verified AssumeRole remain with held PR #80;
  this work does not implement or duplicate them. PR #79 is also untouched.
- Certificate rotation/revocation, multi-host behavior, and production platform
  qualification remain outside this one-host development result.

See [SECURITY.md](../SECURITY.md#phase-a-native-grpc-identity-blocker) for pinned
source references and the native-policy limitation.
