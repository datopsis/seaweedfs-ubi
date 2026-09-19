# SeaweedFS on Red Hat UBI 9.
#
# There is no compilation stage. The upstream binary is statically linked and
# arrives already verified, through a named build context produced by
# scripts/fetch-artifacts.sh, so assembly needs no toolchain, no package
# manager, and no network.
#
# The only reason UBI Minimal appears here is to source trust material as a
# file. No package manager runs in either stage.
#
# Build inputs are pinned by digest. Update them through a reviewed change, not
# by moving a tag.

ARG UBI_MINIMAL=registry.access.redhat.com/ubi9/ubi-minimal@sha256:b061cda54b60dbe0c4746369a0af84b914af226e19cde4612b62e2e12e4371e6
ARG UBI_MICRO=registry.access.redhat.com/ubi9/ubi-micro@sha256:7a0454cbd9bd847e8f6a63b6f0254a6efbeb6e0ed71a5d824a4f6cccbe626650

# UBI Micro ships no CA bundle. A deployment that terminates or originates TLS
# against a publicly trusted certificate needs one, and an empty trust store
# fails in a way that is tedious to diagnose. Copying the extracted bundle out
# of a digest-pinned Minimal keeps the final image package-manager-free and the
# build hermetic. Operators mount their own trust material over this when they
# use a private CA.
FROM ${UBI_MINIMAL} AS trust

FROM ${UBI_MICRO}

# UBI Micro has no package-manager executable, but still carries DNF/YUM
# configuration and RPM signing keys. None are needed at runtime. /var/tmp is
# inherited as world-writable; this image declares /data and /tmp for writes.
RUN rm -rf -- /etc/dnf /etc/yum.repos.d /etc/pki/rpm-gpg && chmod 0755 /var/tmp

ARG SEAWEEDFS_VERSION
ARG SEAWEEDFS_VARIANT
ARG SEAWEEDFS_COMMIT
ARG SOURCE_REVISION
ARG BUILD_DATE

LABEL org.opencontainers.image.title="seaweedfs-ubi" \
      org.opencontainers.image.description="Security-oriented, rootless SeaweedFS on Red Hat UBI 9" \
      org.opencontainers.image.vendor="Datopsis" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/datopsis/seaweedfs-ubi" \
      org.opencontainers.image.documentation="https://github.com/datopsis/seaweedfs-ubi/blob/main/README.md" \
      org.opencontainers.image.base.name="registry.access.redhat.com/ubi9/ubi-micro" \
      org.opencontainers.image.version="${SEAWEEDFS_VERSION}" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      io.datopsis.seaweedfs.version="${SEAWEEDFS_VERSION}" \
      io.datopsis.seaweedfs.variant="${SEAWEEDFS_VARIANT}" \
      io.datopsis.seaweedfs.commit="${SEAWEEDFS_COMMIT}"

COPY --from=trust /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem /etc/pki/tls/certs/ca-bundle.crt

# The verified binary. The build context is produced by the admission gate and
# contains nothing else, so no other part of the working tree can reach the
# image.
#
# DL3022 is suppressed because `weed` is a named build context supplied with
# --build-context, not a stage alias. hadolint has no way to see it. Using a
# stage instead would mean copying the binary into the ordinary build context,
# which is exactly the exposure the named context avoids.
# hadolint ignore=DL3022
COPY --from=weed --chmod=0555 weed /usr/local/bin/weed

COPY --chmod=0555 container/entrypoint.sh /usr/local/bin/seaweedfs-entrypoint

# State lives here and nowhere else, so a read-only root filesystem needs
# exactly one writable mount. Group 0 with group-write is what makes an
# arbitrary assigned UID work on OpenShift; it is not a permission relaxation
# for the fixed identity below, which owns the directory anyway.
RUN mkdir -p /data && chown 1000:0 /data && chmod 0770 /data

# Non-root from the first instruction the container runs. There is no
# privileged phase and no user transition: the entrypoint execs the server, so
# it becomes PID 1 and receives signals directly.
USER 1000:0

WORKDIR /data

# Every listener is unprivileged. gRPC ports are the HTTP port plus 10000,
# which is upstream's convention when -port.grpc is left at 0.
#   master 9333/19333   volume 8080/18080   filer 8888/18888   s3 8333
EXPOSE 9333 19333 8080 18080 8888 18888 8333

ENTRYPOINT ["/usr/local/bin/seaweedfs-entrypoint"]

# No default role. Starting a distributed storage component is a deliberate
# choice, and a default here would make one of them an accident.
CMD []
