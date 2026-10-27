# LedgerMind Cloud Connector — installation channel

The **LedgerMind Cloud Connector** is the small local component that connects an
agent on your machine to the managed LedgerMind Cloud service with a workspace
API key. The managed service, its deployment configuration and all backend
source stay in the private platform repository; this directory is the public
delivery channel only.

## Install

```bash
curl -fsSL https://ledgermind.org/install-cloud.sh | sh
```

The script downloads the release archive from this repository's Releases,
verifies its SHA-256 checksum, creates an isolated Python environment under
`${XDG_DATA_HOME:-$HOME/.local/share}/ledgermind/cloud`, and links the
`ledgermind-cloud` command into `~/.local/bin`.

Requirements: Python 3.10 or newer, `curl`, and `sha256sum`.

Then create a workspace API key in the [Cloud dashboard](https://ledgermind.org/dashboard)
and connect an agent:

```bash
ledgermind-cloud connect AGENT
ledgermind-cloud doctor
```

Supported agents: `codex`, `claude-code`, `hermes`, `opencode`, `openclaw`.

`install-cloud.sh` in this directory is a byte-for-byte mirror of the served
script (`site/lib/install-cloud.sh` in the private platform repository). The
served copy is the canon; the release checklist below keeps both in sync.

## Verify a release manually

```bash
version=0.2.0b1
base=https://github.com/sl4m3/ledgermind/releases/download/cloud-v${version}
curl -fsSLO "$base/ledgermind-cloud-${version}.tar.gz"
curl -fsSLO "$base/ledgermind-cloud-${version}.tar.gz.sha256"
sha256sum -c "ledgermind-cloud-${version}.tar.gz.sha256"
```

Checksums published with each release are also recorded under `checksums/`.

The archive contains the connector wheel, the public integration and protocol
wheels, their third-party dependencies, and `source-manifest.json` with the
source revisions used for the build. It never contains the managed service: no
server package, worker, database schema, migrations, deployment files,
environment files, or provider credentials.

## Connector release checklist

1. Bump the version in `cloud-connector/pyproject.toml` in the platform
   repository and build the archive from a clean revision:
   `python cloud-connector/scripts/build-connector-release.py --output <dir>`.
2. Confirm the build script's guards passed: exactly one public entry point
   (`ledgermind-cloud`), no `ledgermind-cloud-*` private entry points, no
   server files in the client wheel.
3. Smoke-install the archive into a clean home:
   `LEDGERMIND_CLOUD_RELEASE_URL=<dir> sh cloud/install-cloud.sh --no-connect`
   and check `ledgermind-cloud --help` and `ledgermind-cloud doctor`.
4. Publish tag `cloud-vX.Y` with the archive and `.sha256` in **both**
   repositories while the transition window is open (see below). Use
   `--prerelease`: GitHub's `releases/latest/download` must keep resolving to
   the Local release, otherwise `install.sh` breaks.
5. Copy the checksum line into `cloud/checksums/cloud-vX.Y.sha256`.
6. Confirm `cloud/install-cloud.sh` matches `site/lib/install-cloud.sh`.
7. Record the release in the connector manifest and update
   `install-cloud.sh`'s default `VERSION` only when the previous version is
   deprecated.

## Transition window (`cloud-v*` dual publish)

Connector releases used to live in the `ledgermind-cloud` repository. From the
2026-10 migration onward, new `cloud-v*` tags are published in this repository.
For the transition, publish the next **2–3 releases (or three months,
whichever comes first)** to both repositories with identical tags, archives and
checksums; then stop dual publishing and leave `ledgermind-cloud` archived with
a stub README. Older releases and pinned installers keep working from the
archive.

`LEDGERMIND_CLOUD_RELEASE_URL` overrides the download base for testing or for a
pinned mirror.
