"""The provider adapter boundary.

CLAUDE.md: "LLM calls go through the provider adapter with prompt, schema, and
model version pinned per grader version. No direct SDK calls elsewhere."

Everything the model sees is pinned together in a `PromptSpec`: the prompt text,
the output schema, the model id, and a version string that changes whenever any
of those change. That triple is what the eval harness compares providers on, so
it cannot be assembled ad hoc at the call site.

Nothing in this module imports a provider SDK. The concrete providers do.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMError(RuntimeError):
    """Any failure to get a usable structured answer out of a provider.

    Callers are expected to treat this as "no answer", never as "no requirement".
    """


class LLMRefusalError(LLMError):
    """The provider declined the request.

    A separate type because a refusal is not a transport failure and must not be
    retried as one.
    """


@dataclass(frozen=True)
class PromptSpec:
    """One pinned prompt, schema and model, versioned as a unit."""

    prompt_id: str
    version: str
    model: str
    system: str
    max_tokens: int = 16_000
    #: Adaptive thinking on current models; see docs/adr if this ever changes.
    thinking: bool = True

    def identity(self) -> dict[str, str]:
        """The fields that go into every log line and every stored record."""
        return {
            "prompt_id": self.prompt_id,
            "prompt_version": self.version,
            "model": self.model,
        }


@dataclass(frozen=True)
class StructuredResult[SchemaT: BaseModel]:
    """A validated structured answer plus everything needed to audit it."""

    output: SchemaT
    prompt_id: str
    prompt_version: str
    model: str
    request_id: uuid.UUID = field(default_factory=uuid.uuid4)
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(Protocol):
    """What the rest of the platform is allowed to know about a model provider."""

    name: str

    def complete_structured(
        self,
        spec: PromptSpec,
        user_content: str,
        schema: type[SchemaT],
        *,
        context: dict[str, Any] | None = None,
    ) -> StructuredResult[SchemaT]:
        """Return a validated instance of `schema`, or raise `LLMError`.

        Implementations must never return a partially valid object, and must
        never invent a value to satisfy the schema. Raising is correct; guessing
        is not.
        """
        ...
