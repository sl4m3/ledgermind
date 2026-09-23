from __future__ import annotations

from collections.abc import Callable
from typing import Any, get_type_hints

from ledgermind_integrations.adapters.hermes.hook_contracts import (
    HermesPluginContext,
    PostLLMCallKwargs,
    PostToolCallKwargs,
    PreLLMCallKwargs,
    PreToolCallKwargs,
)


def test_context_protocol_describes_registration_surface() -> None:
    hints = get_type_hints(HermesPluginContext)
    assert "profile_name" in hints
    assert callable(HermesPluginContext.register_hook)


def test_hook_contracts_keep_verified_fields_typed() -> None:
    assert get_type_hints(PreLLMCallKwargs)["session_id"] is str
    assert get_type_hints(PreLLMCallKwargs)["user_message"] is object
    assert get_type_hints(PostLLMCallKwargs)["assistant_response"] is str
    assert "args" in get_type_hints(PreToolCallKwargs)
    assert get_type_hints(PostToolCallKwargs)["result"] is object


def test_fake_context_can_implement_protocol() -> None:
    callbacks: dict[str, Callable[..., Any]] = {}

    class FakeContext:
        profile_name = "default"

        def register_hook(self, hook_name: str, callback: Callable[..., Any]) -> None:
            callbacks[hook_name] = callback

    context: HermesPluginContext = FakeContext()
    context.register_hook("pre_llm_call", lambda **_: None)
    assert callbacks["pre_llm_call"]() is None
