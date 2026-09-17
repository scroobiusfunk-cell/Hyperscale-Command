"""The Anthropic adapter, driven against a stub client.

No network and no API key. What is being tested is the adapter's handling of the
SDK's response shapes, which is where the mistakes live — particularly a
refusal, which arrives as a *successful* response and so has to be checked
rather than caught.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx2
import pytest
from anthropic import APIConnectionError
from pydantic import BaseModel

from app.llm.anthropic_provider import DEFAULT_MODEL, AnthropicProvider
from app.llm.base import LLMError, LLMRefusalError, PromptSpec


class Answer(BaseModel):
    value: str


SPEC = PromptSpec(
    prompt_id="test.prompt",
    version="1.0.0",
    model=DEFAULT_MODEL,
    system="be useful",
)


@dataclass
class StubUsage:
    input_tokens: int = 120
    output_tokens: int = 34


@dataclass
class StubStopDetails:
    category: str = "cyber"


class StubResponse:
    def __init__(
        self,
        parsed_output: BaseModel | None = None,
        stop_reason: str = "end_turn",
        stop_details: StubStopDetails | None = None,
    ) -> None:
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason
        self.stop_details = stop_details
        self.usage = StubUsage()


class StubMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.last_request: dict[str, Any] | None = None

    def parse(self, **kwargs: Any) -> Any:
        self.last_request = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class StubClient:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.messages = StubMessages(response, error)


def test_a_valid_answer_comes_back_with_its_pinned_identity() -> None:
    client = StubClient(StubResponse(parsed_output=Answer(value="ok")))
    provider = AnthropicProvider(client=client)  # type: ignore[arg-type]

    result = provider.complete_structured(SPEC, "question", Answer)

    assert result.output.value == "ok"
    assert result.prompt_id == "test.prompt"
    assert result.prompt_version == "1.0.0"
    assert result.model == DEFAULT_MODEL
    assert result.input_tokens == 120
    assert result.output_tokens == 34


def test_a_refusal_raises_its_own_error_type() -> None:
    """A refusal is not a transport failure and must not be retried as one."""
    client = StubClient(
        StubResponse(stop_reason="refusal", stop_details=StubStopDetails(category="cyber"))
    )
    provider = AnthropicProvider(client=client)  # type: ignore[arg-type]

    with pytest.raises(LLMRefusalError, match="cyber"):
        provider.complete_structured(SPEC, "question", Answer)


def test_a_refusal_is_checked_before_the_output_is_read() -> None:
    """It arrives as a 200, so nothing catches it unless the adapter looks."""
    client = StubClient(StubResponse(parsed_output=Answer(value="ok"), stop_reason="refusal"))
    provider = AnthropicProvider(client=client)  # type: ignore[arg-type]

    with pytest.raises(LLMRefusalError):
        provider.complete_structured(SPEC, "question", Answer)


def test_a_missing_parsed_output_is_an_error_not_an_empty_answer() -> None:
    client = StubClient(StubResponse(parsed_output=None, stop_reason="max_tokens"))
    provider = AnthropicProvider(client=client)  # type: ignore[arg-type]

    with pytest.raises(LLMError, match="max_tokens"):
        provider.complete_structured(SPEC, "question", Answer)


def test_an_sdk_error_is_wrapped_rather_than_leaking() -> None:
    """Callers depend on LLMError; they should not import the SDK to catch things."""
    error = APIConnectionError(message="boom", request=httpx2.Request("POST", "https://x"))
    provider = AnthropicProvider(client=StubClient(error=error))  # type: ignore[arg-type]

    with pytest.raises(LLMError, match=re.escape("test.prompt@1.0.0")):
        provider.complete_structured(SPEC, "question", Answer)


def test_the_request_carries_the_pinned_model_prompt_and_schema() -> None:
    client = StubClient(StubResponse(parsed_output=Answer(value="ok")))
    provider = AnthropicProvider(client=client)  # type: ignore[arg-type]

    provider.complete_structured(SPEC, "question", Answer)

    request = client.messages.last_request
    assert request is not None
    assert request["model"] == DEFAULT_MODEL
    assert request["system"] == "be useful"
    assert request["output_format"] is Answer
    assert request["messages"] == [{"role": "user", "content": "question"}]
    assert request["thinking"] == {"type": "adaptive"}


def test_a_spec_with_thinking_off_omits_the_parameter() -> None:
    client = StubClient(StubResponse(parsed_output=Answer(value="ok")))
    provider = AnthropicProvider(client=client)  # type: ignore[arg-type]

    provider.complete_structured(
        PromptSpec(prompt_id="p", version="1.0.0", model=DEFAULT_MODEL, system="s", thinking=False),
        "question",
        Answer,
    )

    assert "thinking" not in (client.messages.last_request or {})
