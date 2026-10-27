"""Typed boundary for the installed Hermes plugin lifecycle API."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, TypedDict

HookCallback = Callable[..., Any]


class HermesPluginContext(Protocol):
    """Subset of Hermes ``hermes_cli.plugins.PluginContext`` we use."""

    profile_name: str

    def register_hook(self, hook_name: str, callback: HookCallback) -> None: ...


class PreLLMCallKwargs(TypedDict, total=False):
    session_id: str
    task_id: str
    turn_id: str
    user_message: object
    conversation_history: Sequence[Mapping[str, Any]]
    is_first_turn: bool
    model: str
    platform: str
    parent_session_id: str
    sender_id: str
    project_id: str
    repository_id: str
    conversation_id: str
    working_directory: str
    repository_root: str
    cwd: str
    metadata: Mapping[str, Any]
    session_metadata: Mapping[str, Any]
    started_at: str
    first_message_id: int | str
    last_message_id: int | str
    message_id: int | str
    user_message_id: int | str


class PostLLMCallKwargs(TypedDict, total=False):
    session_id: str
    task_id: str
    turn_id: str
    user_message: object
    assistant_response: str
    conversation_history: Sequence[Mapping[str, Any]]
    model: str
    platform: str
    started_at: str
    first_message_id: int | str
    last_message_id: int | str
    message_id: int | str
    user_message_id: int | str
    assistant_message_id: int | str
    project_id: str
    repository_id: str
    conversation_id: str
    working_directory: str
    repository_root: str
    cwd: str
    metadata: Mapping[str, Any]
    session_metadata: Mapping[str, Any]


class PreToolCallKwargs(TypedDict, total=False):
    tool_name: str
    args: Mapping[str, Any]
    task_id: str
    session_id: str
    tool_call_id: str
    turn_id: str
    api_request_id: str
    first_message_id: int | str
    last_message_id: int | str
    message_id: int | str
    project_id: str
    repository_id: str
    conversation_id: str
    working_directory: str
    repository_root: str
    cwd: str
    metadata: Mapping[str, Any]
    session_metadata: Mapping[str, Any]


class PostToolCallKwargs(PreToolCallKwargs, total=False):
    result: object
    duration_ms: int
    status: str
    error_type: str | None
    error_message: str | None


__all__ = [
    "HermesPluginContext",
    "HookCallback",
    "PostLLMCallKwargs",
    "PostToolCallKwargs",
    "PreLLMCallKwargs",
    "PreToolCallKwargs",
]
