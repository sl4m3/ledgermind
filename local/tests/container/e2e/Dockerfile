# syntax=docker/dockerfile:1

FROM python:3.12-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        bubblewrap \
        ca-certificates \
        curl \
        jq \
        openssl \
        sqlite3 \
        tini \
        zstd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        "pydantic>=2.7,<3" \
        "cryptography>=42,<49" \
        "httpx>=0.27,<1" \
        "fastapi>=0.111,<1" \
        "PyYAML>=6.0,<7" \
        "zstandard>=0.23,<1" \
        "uvicorn>=0.30,<1" \
        "pytest>=8,<9" \
        "ruff>=0.6" \
        "jsonschema>=4,<5"

RUN useradd --create-home --uid 10001 --shell /bin/bash e2e

ENTRYPOINT ["/usr/bin/tini", "--"]
