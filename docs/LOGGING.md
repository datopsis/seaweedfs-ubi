# Logging and metrics

This image defines an operations profile without turning observability endpoints
into client-facing services. SeaweedFS server logs are structured JSON by
default, while Prometheus metrics are disabled unless each role is given an
explicit listener.

## Logs

`SEAWEEDFS_UBI_LOG_FORMAT=json` is the default and adds upstream's global
`-log_json=true` flag. Set the variable to `text` for upstream's traditional
text format. Any other value is refused at startup so a misspelling cannot
silently change the format.

Both formats retain `-logtostderr=true`. Logs therefore go to the container
streams and require no writable log directory; collection, retention, and
rotation belong to the container runtime or logging platform. Entrypoint
refusals and notices happen before SeaweedFS starts and remain plain text. A
collector must consequently tolerate those startup records alongside the
server's JSON records.

The tests inspect generated S3 secrets, a rejected token-shaped JWT, the JWT
signing key, and a private-key fragment. They assert that those
values do not appear in the measured role logs. The S3 qualification also
asserts that a rejected request does not echo its access key, supplied secret,
or configured secret in the error body. This is evidence for the exercised
paths, not proof that every upstream error path can never disclose a value.

The standalone persistence test found two upstream 4.46 log paths that disclose
access-key **IDs**: environment-variable bootstrap logs the configured ID at
startup, and a request signed with a removed ID logs that attempted ID when
authentication fails. Its strict ID-log check therefore fails after credential
replacement. A mounted static `s3.json` avoids the startup path, but does not
fix the rejected-request path. No secret-key value was observed in those
measured logs. This is an open release finding, not a log-safety claim; restrict
log access and retention while it is unresolved.

The test proves JWT enforcement by denying direct writes without a valid token; the
successful S3 path proves the components can still obtain and use tokens
internally, but the test does not capture or independently validate an issued
JWT.
Treat logs as sensitive operational data and keep secret values out of
command-line flags,
which runtimes and process inspectors may expose independently of logging.

## Metrics

Metrics remain off by default. Enable them per role with upstream's
`-metricsIp` and `-metricsPort` flags, using a distinct unprivileged port for
each role. For example:

```console
podman run ... seaweedfs-ubi master -mdir=/data \
  -metricsIp=0.0.0.0 -metricsPort=9324
```

The metrics endpoint has no authentication layer of its own and exposes
operational and topology information. Bind or publish it only on a protected
operations network, never the client network. Firewall policy or a separate
authenticated proxy is still required when that network is not fully trusted.

`tests/cluster.sh` proves the ordinary profile has only the role's HTTP and gRPC
listeners. `tests/observability.sh` reruns the separated four-role topology with
one metrics listener per role, checks each exact listener inventory, and
requires each `/metrics` endpoint to return Prometheus exposition data. This is
separated-role evidence; the standalone profile is not a substitute for it.

Debug and pprof endpoints are outside this profile and remain unqualified.
