"""Non-interactive config loading with no hidden prompts."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TextIO

from .errors import ConfigurationError
from .models import InstallerConfig
from .permissions import assert_private


def load_non_interactive_config(
    path: str | Path | None,
    *,
    stdin: TextIO | None = None,
) -> tuple[InstallerConfig, str | None, str | None]:
    if path is None:
        raise ConfigurationError("--config is required in non-interactive mode")
    target = Path(path).expanduser()
    try:
        assert_private(target, directory=False)
    except Exception as exc:
        raise ConfigurationError("--config must be a 0600 private file") from exc
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"cannot read install config: {target}") from exc
    try:
        config = InstallerConfig.model_validate(payload)
    except ValueError as exc:
        raise ConfigurationError(f"install config is invalid: {exc}") from exc
    generation_stdin: str | None = None
    embedding_stdin: str | None = None
    if config.generation.token_stdin:
        stream = stdin or sys.stdin
        generation_stdin = stream.readline().rstrip("\r\n")
        if not generation_stdin:
            raise ConfigurationError(
                "generation token_stdin was requested but stdin is empty"
            )
    if (
        config.embedding.mode == "api"
        and config.embedding.api is not None
        and config.embedding.api.token_stdin
    ):
        stream = stdin or sys.stdin
        embedding_stdin = stream.readline().rstrip("\r\n")
        if not embedding_stdin:
            raise ConfigurationError(
                "embedding token_stdin was requested but stdin is empty"
            )
    for env_name in (config.generation.token_env,):
        if env_name and not os.environ.get(env_name):
            raise ConfigurationError(
                f"required secret environment variable is empty: {env_name}"
            )
    if config.embedding.mode == "api" and config.embedding.api is not None:
        env_name = config.embedding.api.token_env
        if env_name and not os.environ.get(env_name):
            raise ConfigurationError(
                f"required secret environment variable is empty: {env_name}"
            )
    if config.reranker.mode == "api" and config.reranker.api is not None:
        env_name = config.reranker.api.token_env
        if env_name and not os.environ.get(env_name):
            raise ConfigurationError(
                f"required secret environment variable is empty: {env_name}"
            )
    return config, generation_stdin, embedding_stdin


__all__ = ["load_non_interactive_config"]
