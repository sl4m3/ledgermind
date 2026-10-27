# LedgerMind Local — installation channel

`local/` in this repository is the complete Busl-1.1 source of the LedgerMind
Local 4.x product: CLI, local service, installer, release scripts, tests and
product documentation. This page covers the release channel; the product guide
is [`local/README.md`](README.md), and the end-to-end installation guide is in
the repository README (`## Installation`).

## Install

```bash
curl -fsSL https://github.com/sl4m3/ledgermind/releases/latest/download/install.sh | sh
```

This URL is stable and does not change with the two-repository reorganization.
The bootstrap script selects the platform, downloads the signed installer for
the current architecture from `releases/latest/download`, and hands the
installation to it. Supported hosts: Linux x86_64 (4.1.0 publishes x86_64 only;
the aarch64 package is not part of this release).

Requirements are listed in the repository README. In short: Linux x86_64 with
glibc 2.31+, `bubblewrap` for fail-closed Core isolation, a supported agent, and
a generation/embedding provider or the signed local runtime.

`local/install.sh` is a byte-for-byte mirror of the product bootstrap script
(`local/scripts/install.sh`). The product copy is the canon; they are kept in
sync by the release checklist.

## Verify a release manually

```bash
version=4.1.0
base=https://github.com/sl4m3/ledgermind/releases/download/v${version}
curl -fsSLO "$base/install.sh"
curl -fsSLO "$base/ledgermind-installer-linux-x86_64"
curl -fsSLO "$base/ledgermind-installer-linux-x86_64.json"
```

Signed sizes, hashes and signatures are published in the release assets
(`install-manifest.json`, `install-manifest.sig`, `ledgermind-release.pub`).
Checksums recorded by this repository live under `checksums/`.

## Dependency delivery (binary, reproducible per release)

The Busl source in this directory is complete, but one runtime dependency is
proprietary and is **not** published as source: `ledgermind-inference==0.1.0`
(embeddings, reranking and provider transports). Official releases ship it as a
prebuilt wheel:

- `local/release/dependency-wheels.json` records the wheel name, version and
  SHA-256 for each release line;
- the wheel itself is attached to the public release as
  `ledgermind_inference-<version>-py3-none-any.whl`;
- installers embed the same wheel inside the signed payload, so installation
  never needs PyPI for it.

Building Local from this tree therefore requires that wheel (for the exact
release) or an equivalent private installation. The public CI downloads the
wheel from the matching release; local development may point
`LEDGERMIND_INFERENCE_WHEEL` at a wheel built from the private platform.

## Source access and licence

`local/` is licensed under Business Source License 1.1 — see `local/LICENSE`.
Source access is deliberate: the licence requires the source to be available,
while the proprietary inference boundary stays binary-only.

## Container artifact

`local/Dockerfile` is the experimental, explicitly unsupported Local container.
It builds Core from the private platform sources (`core/`), so it is not
buildable from this repository alone; the supported Linux installation path is
the signed installer above.
