#!/bin/sh
set -eu

# Bootstrap only: platform selection, download, and argument forwarding belong
# to the signed installer binary.  GitHub HTTPS is the initial trust anchor.
case "$(uname -s):$(uname -m)" in
  Linux:x86_64|Linux:amd64) asset="ledgermind-installer-linux-x86_64" ;;
  Linux:aarch64|Linux:arm64) asset="ledgermind-installer-linux-aarch64" ;;
  *)
    printf '%s\n' "LedgerMind supports Linux x86_64 and Linux aarch64 only" >&2
    exit 3
    ;;
esac

base_url=${LEDGERMIND_RELEASE_BASE_URL:-https://github.com/sl4m3/ledgermind/releases/latest/download}
destination=${TMPDIR:-/tmp}/"$asset.$$"
download_pid=
total_bytes=0
cleanup() {
  if [ -n "$download_pid" ]; then
    kill "$download_pid" 2>/dev/null || true
  fi
  rm -f "$destination"
}
trap cleanup EXIT INT TERM

download_with_status() {
  "$@" &
  download_pid=$!
  while kill -0 "$download_pid" 2>/dev/null; do
    if [ -f "$destination" ]; then
      bytes=$(wc -c < "$destination")
    else
      bytes=0
    fi
    mib=$((bytes / 1048576))
    if [ "$total_bytes" -gt 0 ]; then
      percent=$((bytes * 100 / total_bytes))
      if [ "$percent" -gt 100 ]; then percent=100; fi
      filled=$((percent * 28 / 100))
      empty=$((28 - filled))
      filled_bar=$(printf '%*s' "$filled" '' | tr ' ' '=')
      empty_bar=$(printf '%*s' "$empty" '' | tr ' ' '-')
      total_mib=$(((total_bytes + 1048575) / 1048576))
      printf '\r\033[2K  Downloading  [%s%s]  %3s%%  %s/%s MiB' \
        "$filled_bar" "$empty_bar" "$percent" "$mib" "$total_mib" >&2
    else
      printf '\r\033[2K  Downloading LedgerMind installer  %s MiB' "$mib" >&2
    fi
    sleep 0.15
  done
  if wait "$download_pid"; then
    download_pid=
    if [ "$total_bytes" -gt 0 ]; then
      total_mib=$(((total_bytes + 1048575) / 1048576))
      printf '\r\033[2K  Downloading  [============================]  100%%  %s/%s MiB\n' \
        "$total_mib" "$total_mib" >&2
    else
      printf '\r\033[2K  Installer downloaded\n' >&2
    fi
    return 0
  else
    status=$?
    download_pid=
    printf '\r\033[2K  [failed] Installer download failed\n' >&2
    return "$status"
  fi
}

printf '%s\n' 'LedgerMind Setup' >&2
if command -v curl >/dev/null 2>&1; then
  if [ -t 2 ]; then
    printf '%s' '  Preparing secure download…' >&2
    total_bytes=$(curl -fsSIL "$base_url/$asset" 2>/dev/null \
      | tr -d '\r' \
      | awk 'tolower($1) == "content-length:" && $2 + 0 > 0 { size=$2 } END { print size + 0 }')
    printf '\r\033[2K' >&2
    download_with_status curl -fsSL "$base_url/$asset" -o "$destination"
  else
    curl -fsSL "$base_url/$asset" -o "$destination"
  fi
elif command -v wget >/dev/null 2>&1; then
  if [ -t 2 ]; then
    download_with_status wget -qO "$destination" "$base_url/$asset"
  else
    wget -qO "$destination" "$base_url/$asset"
  fi
else
  printf '%s\n' "curl or wget is required" >&2
  exit 5
fi

chmod 700 "$destination"
export LEDGERMIND_RELEASE_BASE_URL="$base_url"

# When this bootstrap is streamed through `curl | sh`, stdin belongs to the
# shell reading the downloaded script rather than to the interactive wizard.
# Route interactive input to the user's terminal while leaving stdin untouched
# for explicitly non-interactive installs (for example token_stdin).
interactive=1
for arg in "$@"; do
  if [ "$arg" = "--non-interactive" ]; then
    interactive=0
    break
  fi
done

if [ "$interactive" -eq 1 ] && [ ! -t 0 ]; then
  if [ -r /dev/tty ]; then
    exec "$destination" "$@" </dev/tty
  fi
  printf '%s\n' "an interactive terminal is required; use --non-interactive with --config for piped installs" >&2
  exit 4
fi

exec "$destination" "$@"
