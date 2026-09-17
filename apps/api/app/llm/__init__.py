"""Model provider adapter.

Import `LLMProvider`, `PromptSpec` and the error types from here. Do not import
a provider SDK anywhere else in the platform.
"""

from app.llm.base import (
    LLMError,
    LLMProvider,
    LLMRefusalError,
    PromptSpec,
    StructuredResult,
)

__all__ = [
    "LLMError",
    "LLMProvider",
    "LLMRefusalError",
    "PromptSpec",
    "StructuredResult",
]
