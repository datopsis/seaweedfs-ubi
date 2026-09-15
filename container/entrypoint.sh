#!/usr/bin/env bash
#
# Role dispatcher and startup guards for seaweedfs-ubi.
#
# Three jobs, in order:
#   1. refuse a role this image does not support;
#   2. refuse a configuration that would be silently unsafe;
#   3. exec the server, so it runs as PID 1 and receives signals directly.
#
# There is no privileged phase. This script runs as the same non-root identity
# the server does, changes no ownership, and switches no user.
#
# Every variable this packaging adds uses the SEAWEEDFS_UBI_ prefix, so it can
# never collide with upstream's WEED_ configuration namespace.

set -euo pipefail

WEED=/usr/local/bin/weed

# EX_CONFIG from sysexits: the configuration is wrong, not the software.
EX_CONFIG=78

refuse() {
	printf 'seaweedfs-ubi: %s\n' "$1" >&2
	shift
	while [ "$#" -gt 0 ]; do
		printf 'seaweedfs-ubi:   %s\n' "$1" >&2
		shift
	done
	exit "$EX_CONFIG"
}

# A boolean this image defines is either true or false. A misspelling is a
# configuration error, never a silent fallback to the unsafe side.
boolean() {
	local name="$1" value="$2" default="$3"
	[ -n "$value" ] || value="$default"
	case "$value" in
	true | TRUE | True) return 0 ;;
	false | FALSE | False) return 1 ;;
	*)
		refuse "${name} is set to '${value}', which is not true or false." \
			"A misspelled toggle must not quietly disable a control, so this is refused." \
			"Set it to true or false, or unset it to use the default (${default})."
		;;
	esac
}

# Whether the operator already passed a flag, so an injected default never
# overrides an explicit choice.
has_flag() {
	local want="$1"
	shift
	local argument
	for argument in "$@"; do
		case "$argument" in
		"$want" | "$want"=*) return 0 ;;
		esac
	done
	return 1
}

# The value of -name=value or -name value, empty when absent.
flag_value() {
	local want="$1"
	shift
	local previous=""
	local argument
	for argument in "$@"; do
		case "$argument" in
		"$want"=*)
			printf '%s' "${argument#*=}"
			return 0
			;;
		esac
		if [ "$previous" = "$want" ]; then
			printf '%s' "$argument"
			return 0
		fi
		previous="$argument"
	done
	return 0
}

# Upstream defaults the master metadata directory and the volume data directory
# to the process temporary directory. On this image that is a tmpfs, so a
# forgotten flag produces a component that reports healthy and loses its state
# on restart. That is worse than a failure, so it is made into one.
require_data_directory() {
	local role="$1" flag="$2"
	shift 2
	local value
	value="$(flag_value "$flag" "$@")"

	if [ -z "$value" ]; then
		refuse "the ${role} role was started without ${flag}." \
			"Upstream would default it to the temporary directory, which on this image" \
			"is a tmpfs: the ${role} would start, report healthy, and lose its state on" \
			"restart. Pass ${flag}=/data/${role} and mount a volume there." \
			"To accept upstream's behaviour instead, set SEAWEEDFS_UBI_REQUIRE_EXPLICIT_DATA_DIR=false."
	fi

	case "$value" in
	/tmp | /tmp/* | /var/tmp | /var/tmp/* | . | ./*)
		refuse "the ${role} role was given ${flag}=${value}, which is a temporary path." \
			"Durable state stored there does not survive a restart." \
			"To accept that, set SEAWEEDFS_UBI_REQUIRE_EXPLICIT_DATA_DIR=false."
		;;
	esac
}

# With no configuration file and no identities, upstream treats every S3 request
# as an allow-all anonymous caller -- including writes. A configuration file
# that loads zero identities denies everything instead, so an empty secret mount
# already fails closed and only the missing one needs a guard.
require_s3_identities() {
	local role="$1" config_flag="$2"
	shift 2

	local config
	config="$(flag_value "$config_flag" "$@")"
	if [ -n "$config" ]; then
		if [ ! -f "$config" ]; then
			refuse "${config_flag}=${config} does not exist." \
				"Refusing rather than starting, because upstream would fall back to" \
				"allow-all anonymous access."
		fi
		return 0
	fi

	if has_flag -iam.config "$@" || has_flag -s3.iam.config "$@"; then
		return 0
	fi

	if [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ]; then
		return 0
	fi

	refuse "the ${role} role was started with no S3 identity source." \
		"Upstream would serve every request as an allow-all anonymous caller, which" \
		"permits writes and deletes, not just reads." \
		"Provide ${config_flag}=/path/to/s3.json, or set AWS_ACCESS_KEY_ID and" \
		"AWS_SECRET_ACCESS_KEY." \
		"If identities are held in the filer, this guard cannot see them; set" \
		"SEAWEEDFS_UBI_REQUIRE_S3_AUTH=false and rely on your own review."
}

# Two upstream S3 defaults diverge from the S3 API in ways a client will not
# expect, and one of them loses data.
#
#   allowDeleteBucketNotEmpty=true  DeleteBucket on a bucket that still holds
#                                   objects deletes all of them. The S3 API
#                                   answers BucketNotEmpty instead, so a client
#                                   written against S3 gets silent bulk deletion
#                                   where it expected an error.
#   autoCreateBucket=true           A PUT into a bucket that does not exist
#                                   creates it, for admin identities. The S3 API
#                                   answers NoSuchBucket, so a typo becomes a new
#                                   bucket rather than a failure.
#
# Both are turned off, for the standalone profile as well as the S3 role: a
# fixture that is more permissive than the thing it stands in for lets tests pass
# against behaviour production will not have. An operator who wants upstream's
# behaviour passes the flag explicitly, which is honoured.
apply_s3_bucket_defaults() {
	local prefix="$1"
	shift
	has_flag "-${prefix}allowDeleteBucketNotEmpty" "$@" ||
		injected+=("-${prefix}allowDeleteBucketNotEmpty=false")
	has_flag "-${prefix}autoCreateBucket" "$@" ||
		injected+=("-${prefix}autoCreateBucket=false")
}

usage() {
	cat >&2 <<-'USAGE'
		seaweedfs-ubi: no role given.

		Supported roles, each in its own container:
		  master   coordination and volume assignment   9333 / 19333
		  volume   object storage                       8080 / 18080
		  filer    file and bucket metadata             8888 / 18888
		  s3       the S3 API                           8333

		Informational:
		  version, shell

		Local development only, and never a production posture:
		  mini     every role in one process, requires SEAWEEDFS_UBI_STANDALONE=true

		Example:
		  master -mdir=/data -ip=seaweedfs-master
	USAGE
	exit "$EX_CONFIG"
}

main() {
	[ "$#" -gt 0 ] || usage

	local role="$1"
	shift

	local guard_dirs=true guard_auth=true
	boolean SEAWEEDFS_UBI_REQUIRE_EXPLICIT_DATA_DIR \
		"${SEAWEEDFS_UBI_REQUIRE_EXPLICIT_DATA_DIR:-}" true || guard_dirs=false
	boolean SEAWEEDFS_UBI_REQUIRE_S3_AUTH \
		"${SEAWEEDFS_UBI_REQUIRE_S3_AUTH:-}" true || guard_auth=false

	local injected=()

	case "$role" in
	master)
		[ "$guard_dirs" = true ] && require_data_directory master -mdir "$@"
		;;
	volume)
		[ "$guard_dirs" = true ] && require_data_directory volume -dir "$@"
		;;
	filer)
		# The filer's store location comes from filer.toml rather than a flag, so
		# there is nothing here to check. Its durability is the operator's, and it
		# is stated as such in docs/CONFIGURATION.md.
		;;
	s3)
		[ "$guard_auth" = true ] && require_s3_identities s3 -config "$@"

		# In 4.46 the S3 role also opens an Iceberg REST Catalog on 8181 and a
		# Lance Namespace server on 9101 unless each is given 0. Neither is in
		# this image's boundary, and lakekeeper-ubi is this organization's
		# qualified Iceberg catalog, so a second unqualified one must not appear
		# on a default port.
		if ! boolean SEAWEEDFS_UBI_ENABLE_ICEBERG_CATALOG \
			"${SEAWEEDFS_UBI_ENABLE_ICEBERG_CATALOG:-}" false; then
			has_flag -port.iceberg "$@" || injected+=(-port.iceberg=0)
		fi
		if ! boolean SEAWEEDFS_UBI_ENABLE_LANCE_NAMESPACE \
			"${SEAWEEDFS_UBI_ENABLE_LANCE_NAMESPACE:-}" false; then
			has_flag -port.lance "$@" || injected+=(-port.lance=0)
		fi

		apply_s3_bucket_defaults "" "$@"
		;;
	mini)
		if ! boolean SEAWEEDFS_UBI_STANDALONE "${SEAWEEDFS_UBI_STANDALONE:-}" false; then
			refuse "the standalone role 'mini' is not enabled." \
				"It runs every component in one process, which is useful locally and is" \
				"never a supported production posture: inter-component mTLS and volume" \
				"JWTs protect a network that does not exist inside one process, there is" \
				"no replication, and nothing separates the S3 API from stored bytes." \
				"To use it for local work or a test fixture, set SEAWEEDFS_UBI_STANDALONE=true."
		fi

		printf 'seaweedfs-ubi: starting the standalone profile.\n' >&2
		printf 'seaweedfs-ubi:   Not supported for production. In one process there is no\n' >&2
		printf 'seaweedfs-ubi:   inter-component authentication, no replication, and no\n' >&2
		printf 'seaweedfs-ubi:   isolation between the S3 API and stored data.\n' >&2

		[ "$guard_dirs" = true ] && require_data_directory mini -dir "$@"
		[ "$guard_auth" = true ] && require_s3_identities mini -s3.config "$@"

		# mini enables more than the object store by default. WebDAV and the
		# Admin UI are outside the boundary, so they are off unless asked for.
		has_flag -webdav "$@" || injected+=(-webdav=false)
		has_flag -admin.ui "$@" || injected+=(-admin.ui=false)

		# mini opens the Iceberg catalog and Lance namespace too, under its own
		# s3-prefixed flag names rather than the s3 role's. They were left running
		# here once, which is why tests/smoke.sh now asserts the listener set from
		# a running container instead of trusting this code to be complete.
		if ! boolean SEAWEEDFS_UBI_ENABLE_ICEBERG_CATALOG \
			"${SEAWEEDFS_UBI_ENABLE_ICEBERG_CATALOG:-}" false; then
			has_flag -s3.port.iceberg "$@" || injected+=(-s3.port.iceberg=0)
		fi
		if ! boolean SEAWEEDFS_UBI_ENABLE_LANCE_NAMESPACE \
			"${SEAWEEDFS_UBI_ENABLE_LANCE_NAMESPACE:-}" false; then
			has_flag -s3.port.lance "$@" || injected+=(-s3.port.lance=0)
		fi

		apply_s3_bucket_defaults "s3." "$@"
		;;
	version)
		exec "$WEED" version
		;;
	shell)
		exec "$WEED" shell "$@"
		;;
	-h | --help | help)
		usage
		;;
	*)
		refuse "'${role}' is not a role this image supports." \
			"Supported: master, volume, filer, s3, and the informational version and shell." \
			"The standalone role mini requires SEAWEEDFS_UBI_STANDALONE=true." \
			"Everything else, including server, webdav, iam, mount and the message" \
			"broker, is outside this image's qualified boundary and is refused rather" \
			"than started untested."
		;;
	esac

	# exec, so the server is PID 1 and receives signals directly. Logs go to the
	# container's streams; no writable log path is required.
	exec "$WEED" -logtostderr=true "$role" ${injected[@]+"${injected[@]}"} "$@"
}

main "$@"
