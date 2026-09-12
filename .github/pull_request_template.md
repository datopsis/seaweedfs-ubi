## Summary

Describe the user-facing or operational outcome and why the change is needed.

## Validation

- [ ] I ran the pinned local checks (`pre-commit run --all-files`).
- [ ] I reviewed logs, warnings, annotations, skipped steps, and retained
      evidence rather than relying only on green status checks.
- [ ] I added or updated tests for behavior changes, including the negative
      case where a guard is supposed to refuse.
- [ ] I updated user and operator documentation where needed.
- [ ] I recorded notable completed work in `CHANGELOG.md` and removed it from
      the forward-looking work plan in `docs/README.md` where applicable.
- [ ] I did not weaken a security or release control without documenting the
      threat, rationale, compensating control, owner, and expiry.

## Security and release impact

State whether this changes image contents, runtime behavior, the supported role
set, listener exposure, supported scope, or release evidence. If it changes a
published artifact, identify the required version action under
`docs/VERSION.md`. List accepted findings or write `None`.

## Upstream verification

If this change touches an asserted upstream SeaweedFS behavior — the S3
allow-all default, the default listener set, the temporary-directory data
defaults, the `security.toml` contract, or the release asset layout — state the
upstream version you verified it against and how.
