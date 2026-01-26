"""LLM types for text generation results."""

from dataclasses import dataclass, field
from typing import Awaitable, Callable


@dataclass
class GenerationConfig:
    """Configuration for text generation."""

    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    stop_sequences: list[str] = field(default_factory=list)


@dataclass
class CompletionResult:
    """Result from LLM text generation."""

    text: str  # Generated text
    tokens_generated: int  # Number of tokens generated
    prompt_tokens: int  # Number of tokens in the prompt
    finish_reason: str = "stop"  # Reason for stopping: "stop", "length", etc.


# Type alias for async token streaming callback
TokenCallback = Callable[[str], Awaitable[None]]
