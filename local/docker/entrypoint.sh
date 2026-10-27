#!/bin/sh
set -eu

home="${LEDGERMIND_HOME:-/data/ledgermind}"
core_bin_dir="${LEDGERMIND_CORE_BIN_DIR:-$(dirname "$home")/core/bin}"
signature_file="${LEDGERMIND_CORE_SIGNATURE_FILE:-/run/secrets/ledgermind-core.sig}"
public_key_file="${LEDGERMIND_CORE_PUBLIC_KEY_FILE:-/run/secrets/ledgermind-core.pub}"

if [ ! -r "$signature_file" ] || [ ! -r "$public_key_file" ]; then
    printf '%s\n' \
        'signed Core artifacts are required:' \
        "mount $signature_file and $public_key_file for the exact image binary" >&2
    exit 78
fi

mkdir -p "$core_bin_dir"
install -m 0755 /opt/ledgermind-core/bin/ledgermind-core \
    "$core_bin_dir/ledgermind-core"
install -m 0644 "$signature_file" "$core_bin_dir/ledgermind-core.sig"
install -m 0644 "$public_key_file" "$core_bin_dir/ledgermind-core.pub"

exec "$@"