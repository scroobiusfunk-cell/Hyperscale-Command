"""The Anthropic provider.

The only module in the platform that imports the Anthropic SDK. Model ids are
pinned per prompt version in `PromptSpec`, never chosen here, so the eval
harness can compare two versions by swapping the spec and nothing else.

Every call is logged through `external_call` with the prompt id, prompt version,
model and latency, per the logging rule in CLAUDE.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.llm.base import (
    LLMError,
    LLMProvider,
    LLMRefusalError,
    PromptSpec,
    SchemaT,
    StructuredResult,
)
from app.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from anthropic import Anthropic

log = get_logger(__name__)

#: The default for new prompt specs. Individual specs pin their own model, and
#: a spec that moves to a different model gets a new version.
DEFAULT_MODEL = "claude-opus-5"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, client: Anthropic | None = None, *, api_key: str | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            import anthropic

            # A bare constructor also resolves an OAuth profile, so an unset
            # api_key is not necessarily an error.
            self._client = (
                anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
            )

    def complete_structured(
        self,
        spec: PromptSpec,
        user_content: str,
        schema: type[SchemaT],
        *,
        context: dict[str, Any] | None = None,
    ) -> StructuredResult[SchemaT]:
        from anthropic import APIError

        request: dict[str, Any] = {
            "model": spec.model,
            "max_tokens": spec.max_tokens,
            "system": spec.system,
            "messages": [{"role": "user", "content": user_content}],
            "output_format": schema,
        }
        if spec.thinking:
            request["thinking"] = {"type": "adaptive"}

        from app.logging import external_call

        with external_call(
            "llm",
            "complete_structured",
            version=f"{spec.prompt_id}@{spec.version}",
            model=spec.model,
            schema=schema.__name__,
            **(context or {}),
        ) as record:
            try:
                response = self._client.messages.parse(**request)
            except APIError as exc:
                raise LLMError(f"{spec.prompt_id}@{spec.version} failed: {exc}") from exc

            # A refusal arrives as a successful HTTP response, so it has to be
            # checked rather than caught. Treating it as a transport error would
            # send it round a retry loop that cannot succeed.
            if getattr(response, "stop_reason", None) == "refusal":
                details = getattr(response, "stop_details", None)
                category = getattr(details, "category", None)
                record["refused"] = True
                raise LLMRefusalError(
                    f"{spec.prompt_id}@{spec.version} was refused"
                    + (f" ({category})" if category else "")
                )

            parsed = getattr(response, "parsed_output", None)
            if parsed is None:
                raise LLMError(
                    f"{spec.prompt_id}@{spec.version} returned no parsed output "
                    f"(stop_reason={getattr(response, 'stop_reason', None)})"
                )

            usage = getattr(response, "usage", None)
            record["input_tokens"] = getattr(usage, "input_tokens", None)
            record["output_tokens"] = getattr(usage, "output_tokens", None)

            return StructuredResult(
                output=parsed,
                prompt_id=spec.prompt_id,
                prompt_version=spec.version,
                model=spec.model,
                input_tokens=record["input_tokens"],
                output_tokens=record["output_tokens"],
            )
