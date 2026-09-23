# syntax=docker/dockerfile:1

FROM rust:1.95-slim-bookworm AS core-builder

WORKDIR /src/ledgermind-core

COPY ledgermind-core/Cargo.toml ledgermind-core/Cargo.lock ./
COPY ledgermind-core/crates ./crates
RUN cargo build --release --locked -p ledgermind-daemon --bin ledgermind-core

FROM python:3.12-slim

# Experimental/unsupported container artifact; not a secure deployment path.
LABEL io.ledgermind.deployment.status="experimental-unsupported" \
      io.ledgermind.secure-deployment="unsupported" \
      org.opencontainers.image.description="LedgerMind Local experimental/unsupported container; not a secure deployment path"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LEDGERMIND_HOME=/data/ledgermind

WORKDIR /app

COPY ledgermind-local/pyproject.toml /app/pyproject.toml
COPY ledgermind-local/README.md /app/README.md
COPY ledgermind-local/src /app/src
COPY ledgermind-integrations/protocol/python/pyproject.toml \
    /opt/ledgermind-protocol/pyproject.toml
COPY ledgermind-integrations/protocol/python/src /opt/ledgermind-protocol/src
RUN pip install --no-cache-dir /opt/ledgermind-protocol
RUN pip install --no-cache-dir /app

RUN useradd --system --uid 10001 --create-home --home-dir /home/ledger ledger \
    && mkdir -p /data/core/bin /data/ledgermind \
    && chown -R ledger:ledger /data

COPY --from=core-builder /src/ledgermind-core/target/release/ledgermind-core \
    /opt/ledgermind-core/bin/ledgermind-core
COPY ledgermind-local/docker/entrypoint.sh /usr/local/bin/ledgermind-entrypoint
RUN chmod 0755 /usr/local/bin/ledgermind-entrypoint

USER ledger

VOLUME ["/data"]

EXPOSE 8765

ENTRYPOINT ["/usr/local/bin/ledgermind-entrypoint"]
CMD ["python", "-m", "ledgermind_local.cli", "--home", "/data/ledgermind", "serve"]
