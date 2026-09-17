"""A provider for tests.

Deterministic and offline. Every test that exercises extraction uses this, so
the test suite never depends on a network, an API key, or a model's mood.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider, PromptSpec, SchemaT, StructuredResult


class FakeProvider(LLMProvider):
    """Returns queued responses, or raises queued errors, in order."""

    name = "fake"

    def __init__(
        self,
        responses: list[BaseModel | Exception] | None = None,
        *,
        handler: Callable[[PromptSpec, str], BaseModel] | None = None,
    ) -> None:
        self._responses: list[BaseModel | Exception] = list(responses or [])
        self._handler = handler
        self.calls: list[tuple[PromptSpec, str]] = []

    def complete_structured(
        self,
        spec: PromptSpec,
        user_content: str,
        schema: type[SchemaT],
        *,
        context: dict[str, Any] | None = None,
    ) -> StructuredResult[SchemaT]:
        self.calls.append((spec, user_content))

        if self._handler is not None:
            produced: BaseModel | Exception = self._handler(spec, user_content)
        elif self._responses:
            produced = self._responses.pop(0)
        else:
            raise LLMError("FakeProvider has no queued response for this call")

        if isinstance(produced, Exception):
            raise produced
        if not isinstance(produced, schema):
            raise LLMError(
                f"FakeProvider was queued a {type(produced).__name__} "
                f"but the call expects {schema.__name__}"
            )

        return StructuredResult(
            output=produced,
            prompt_id=spec.prompt_id,
            prompt_version=spec.version,
            model=spec.model,
        )
