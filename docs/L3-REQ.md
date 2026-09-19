# SeaweedFS UBI: Level 3 requirements

These are initial, directly verifiable implementation obligations derived from
[`L2-REQ.md`](L2-REQ.md). Missing test links remain visible in the generated
matrix. A linked unit test covers only the behavior it exercises, not an image,
topology, or release-candidate claim.

### L3-SUP-001

**Parent.** L2-SUP-001

**Statement.** Lock validation SHALL reject missing or inconsistent artifact
identity, architecture, digest, size, variant, commit, or linkage fields.

**Verification.** Test.

### L3-SUP-002

**Parent.** L2-SUP-002

**Statement.** An altered bundle SHALL be rejected again at assembly time.

**Verification.** Test.

### L3-RUN-001

**Parent.** L2-RUN-001

**Statement.** A running role SHALL report a nonzero UID and zero effective
capabilities under a read-only root filesystem.

**Verification.** Test.

### L3-RUN-002

**Parent.** L2-RUN-002

**Statement.** Unsupported subcommands and filer-embedded S3, WebDAV, IAM, and
SFTP enablement SHALL fail before the `weed` process starts.

**Verification.** Test.

### L3-CFG-001

**Parent.** L2-CFG-001

**Statement.** A missing S3 identity source or nonexistent named identity file
SHALL cause a configuration error rather than anonymous startup.

**Verification.** Test.

### L3-CFG-002

**Parent.** L2-CFG-002

**Statement.** `master` and `volume` SHALL refuse their upstream temporary
directory defaults when an explicit persistent path is absent.

**Verification.** Test.

### L3-API-001

**Parent.** L2-API-001

**Statement.** An authenticated client SHALL complete object put, get, list,
delete, and multipart operations while an anonymous client is refused.

**Verification.** Test.

### L3-INT-001

**Parent.** L2-INT-001

**Statement.** The separated-role fixture SHALL refuse direct volume access
without the configured JWT and gRPC access without a trusted client certificate.

**Verification.** Test.

### L3-DAT-001

**Parent.** L2-DAT-001

**Statement.** Cold backup validation SHALL refuse an archive path that escapes
the selected backup root through traversal, an absolute path, or a symlink.

**Verification.** Test.

### L3-OBS-001

**Parent.** L2-OBS-001

**Statement.** Listener inspection SHALL distinguish listening from
non-listening IPv4 and IPv6 sockets for the role's measured exposure set.

**Verification.** Test.

### L3-EVD-001

**Parent.** L2-EVD-001

**Statement.** A development SPDX inventory SHALL identify SeaweedFS and its
resolvable Go dependency inventory before the inventory is retained.

**Verification.** Test.

### L3-EVD-002

**Parent.** L2-EVD-001

**Statement.** A development image Trivy inventory SHALL include both OS and
language-package targets without treating the inventory as a passing gate.

**Verification.** Test.

### L3-EVD-003

**Parent.** L2-EVD-001

**Statement.** A binary govulncheck inventory SHALL record its tool and
database versions without treating the inventory as a passing gate.

**Verification.** Test.

### L3-REL-001

**Parent.** L2-REL-001

**Statement.** The deterministic release-tag validator SHALL refuse malformed,
reused, mistimed, or out-of-sequence tags and input-version mismatches.

**Verification.** Test.
