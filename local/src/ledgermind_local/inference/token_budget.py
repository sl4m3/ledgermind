"""Bounded conservative input-token estimation for provider requests."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from .providers.base import ChatMessage, ModelRequest


class InputBudgetExceededError(RuntimeError):
    """The request is too large to send to the configured provider profile."""

    code = "input_budget_exceeded"

    def __init__(self, estimated_tokens: int, max_input_tokens: int) -> None:
        self.estimated_tokens = estimated_tokens
        self.max_input_tokens = max_input_tokens
        self.profile_id: str | None = None
        super().__init__("model input token budget exceeded")


class OutputBudgetExceededError(RuntimeError):
    """The requested generation output exceeds the profile allowance."""

    code = "output_budget_exceeded"

    def __init__(self, requested_tokens: int, max_output_tokens: int) -> None:
        self.requested_tokens = requested_tokens
        self.max_output_tokens = max_output_tokens
        self.profile_id: str | None = None
        super().__init__("model output token budget exceeded")


@dataclass(frozen=True, slots=True)
class TokenBudgetEstimate:
    estimated_tokens: int
    bounded: bool


class TokenBudgetEstimator:
    """Estimate tokens without an unbounded tokenizer or prompt rewrite.

    ASCII/code characters use four characters per token and non-ASCII
    characters use two.  Once ``max_chars`` is crossed, estimation saturates
    at the configured bound instead of continuing to process attacker-sized
    input.
    """

    def __init__(self, *, max_chars: int = 1_000_000) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        self.max_chars = max_chars

    def estimate_text(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        ascii_chars = 0
        unicode_chars = 0
        for index, character in enumerate(text):
            if index >= self.max_chars:
                return self.max_chars
            if ord(character) < 128:
                ascii_chars += 1
            else:
                unicode_chars += 1
        # ceil(a / 4) + ceil(u / 2), with empty components kept at zero.
        return (ascii_chars + 3) // 4 + (unicode_chars + 1) // 2

    def estimate_messages(self, messages: Iterable[ChatMessage]) -> int:
        total = 0
        for message in messages:
            total = min(self.max_chars, total + self.estimate_text(message.content))
            if total >= self.max_chars:
                return self.max_chars
        return total

    def estimate_request(self, request: ModelRequest) -> TokenBudgetEstimate:
        total = self.estimate_messages(request.messages)
        contract = request.output_contract or request.response_format
        if contract is not None:
            contract_text = json.dumps(
                contract,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            total = min(self.max_chars, total + self.estimate_text(contract_text))
        if request.tool_name:
            total = min(self.max_chars, total + self.estimate_text(request.tool_name))
        return TokenBudgetEstimate(
            estimated_tokens=total,
            bounded=total < self.max_chars,
        )

    def ensure_within(self, request: ModelRequest, max_input_tokens: int) -> int:
        if max_input_tokens < 1:
            raise ValueError("max_input_tokens must be positive")
        estimate = self.estimate_request(request)
        if estimate.estimated_tokens > max_input_tokens:
            raise InputBudgetExceededError(
                estimate.estimated_tokens,
                max_input_tokens,
            )
        return estimate.estimated_tokens

    # Short aliases make the estimator convenient for callers that only have
    # text and preserve one implementation of the conservative formula.
    estimate = estimate_text


__all__ = [
    "InputBudgetExceededError",
    "OutputBudgetExceededError",
    "TokenBudgetEstimate",
    "TokenBudgetEstimator",
]
