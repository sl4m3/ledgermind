#!/bin/sh
set -eu

# Pre-filled by https://ledgermind.org/install-cloud.sh?agent=<id>. The link
# serves this same script with the chosen agent, so `curl <link> | sh` installs
# and connects without extra flags.
DEFAULT_AGENT=""

VERSION="${LEDGERMIND_CLOUD_VERSION:-0.2.0b1}"
BASE_URL="${LEDGERMIND_CLOUD_RELEASE_URL:-https://github.com/sl4m3/ledgermind/releases/download/cloud-v${VERSION}}"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/ledgermind/cloud"
BIN_DIR="${HOME}/.local/bin"
ARCHIVE="ledgermind-cloud-${VERSION}.tar.gz"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

usage() {
  cat <<'EOF'
Usage: install-cloud.sh [--agent AGENT] [--no-connect]

Installs the LedgerMind Cloud Connector. With --agent, the installer also
connects that agent and asks for the workspace API key.

  --agent AGENT   codex, claude-code, hermes, opencode, or openclaw
  --no-connect    install only and print the connect command
  -h, --help      show this help

Download link (preselects the agent):
  https://ledgermind.org/install-cloud.sh?agent=codex

Streamed usage:
  curl -fsSL "https://ledgermind.org/install-cloud.sh?agent=codex" | sh
EOF
}

agent="$DEFAULT_AGENT"
connect=auto
while [ "$#" -gt 0 ]; do
  case "$1" in
    --agent)
      [ "$#" -ge 2 ] || { echo "--agent requires a value" >&2; exit 2; }
      agent=$2
      [ -n "$agent" ] || { echo "--agent requires a value" >&2; exit 2; }
      shift 2
      ;;
    --agent=*)
      agent=${1#*=}
      [ -n "$agent" ] || { echo "--agent requires a value" >&2; exit 2; }
      shift
      ;;
    --connect)
      connect=yes
      shift
      ;;
    --no-connect)
      connect=no
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$agent" in
  '') ;;
  codex|claude-code|hermes|opencode|openclaw) ;;
  *)
    echo "Unsupported agent: $agent" >&2
    usage >&2
    exit 2
    ;;
esac
if [ -n "$agent" ] && [ "$connect" = auto ]; then
  connect=yes
fi
if [ "$connect" = yes ] && [ -z "$agent" ]; then
  echo "--connect requires --agent" >&2
  exit 2
fi

command -v python3 >/dev/null 2>&1 || { echo "LedgerMind Cloud requires Python 3.10+." >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "LedgerMind Cloud requires curl." >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo "LedgerMind Cloud requires sha256sum." >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "LedgerMind Cloud requires Python 3.10+." >&2; exit 1; }
python3 -c 'import ensurepip, venv' >/dev/null 2>&1 || { echo "LedgerMind Cloud requires the Python venv and ensurepip modules (Debian/Ubuntu: apt install python3-venv)." >&2; exit 1; }
mkdir -p "$DATA_DIR" "$BIN_DIR"
curl -fsSL --retry 3 --retry-delay 2 "$BASE_URL/$ARCHIVE" -o "$TMP_DIR/$ARCHIVE"
curl -fsSL --retry 3 --retry-delay 2 "$BASE_URL/$ARCHIVE.sha256" -o "$TMP_DIR/$ARCHIVE.sha256"
(cd "$TMP_DIR" && sha256sum -c "$ARCHIVE.sha256")
tar -xzf "$TMP_DIR/$ARCHIVE" -C "$TMP_DIR"
python3 -m venv "$DATA_DIR/venv"
# The archive ships pinned dependency wheels, but pydantic-core is compiled per
# Python ABI. Pin the bundled pydantic release so the dependency set is decided
# by the archive, while pip is still allowed to fetch the matching ABI-specific
# pydantic-core build for the local interpreter from PyPI.
pydantic_requirement=
for wheel in "$TMP_DIR"/pydantic-*.whl; do
  [ -f "$wheel" ] || continue
  wheel_name=${wheel##*/}
  wheel_version=${wheel_name#pydantic-}
  pydantic_requirement="pydantic==${wheel_version%%-*}"
  break
done
"$DATA_DIR/venv/bin/pip" install --disable-pip-version-check --force-reinstall \
  --find-links "$TMP_DIR" $pydantic_requirement "$TMP_DIR"/ledgermind_cloud-*.whl
ln -sf "$DATA_DIR/venv/bin/ledgermind-cloud" "$BIN_DIR/ledgermind-cloud"

echo "LedgerMind Cloud Connector installed."
if [ "$connect" = yes ]; then
  # The script itself was streamed through stdin, so the connector prompt must
  # read the API key from the terminal. /dev/tty exists as a node even without a
  # controlling terminal, so probe that it can actually be opened.
  if (: </dev/tty) 2>/dev/null; then
    "$DATA_DIR/venv/bin/ledgermind-cloud" connect "$agent" </dev/tty
    echo
    echo "Run ledgermind-cloud doctor to verify the connection."
  else
    echo "No terminal is attached, so the agent was not connected." >&2
    echo "Finish with: ledgermind-cloud connect $agent" >&2
  fi
elif [ -n "$agent" ]; then
  echo "Connect it with: ledgermind-cloud connect $agent"
else
  echo "Create an API key in your dashboard, then connect an agent:"
  echo "  ledgermind-cloud connect AGENT"
  echo "Supported agents: codex, claude-code, hermes, opencode, openclaw"
fi

echo "Ensure $BIN_DIR is on your PATH. Then run ledgermind-cloud doctor to check connectivity."
