"""LLM processor for conversation management and response generation."""

import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ergos.stt.types import TranscriptionResult

from .generator import LLMGenerator
from .types import CompletionResult, TokenCallback

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A message in the conversation history."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class LLMProcessor:
    """Processor for LLM-based conversation with history and streaming.

    Manages conversation history, builds prompts in Phi-3 chat format,
    and streams response tokens to registered callbacks.
    """

    generator: LLMGenerator
    system_prompt: str = (
        "You are a helpful voice assistant. Keep responses concise and conversational."
    )

    # Configuration
    max_history_messages: int = 10  # Keep last N messages for context
    max_context_tokens: int = 1500  # Reserve tokens for history

    # Internal state (not init parameters)
    _history: list[Message] = field(default_factory=list, init=False)
    _token_callbacks: list[TokenCallback] = field(default_factory=list, init=False)
    _completion_callbacks: list[Callable[[CompletionResult], Awaitable[None]]] = field(
        default_factory=list, init=False
    )

    async def process_transcription(
        self, result: TranscriptionResult
    ) -> CompletionResult:
        """Process STT result and generate response.

        Args:
            result: Transcription result from speech-to-text.

        Returns:
            CompletionResult with generated response text.
        """
        # Add user message to history
        self._history.append(Message(role="user", content=result.text))

        # Build prompt with history
        prompt = self._build_prompt()

        # Generate response with streaming
        full_response = ""
        tokens_generated = 0

        async for token in self.generator.generate_stream(prompt):
            full_response += token
            tokens_generated += 1
            for callback in self._token_callbacks:
                try:
                    await callback(token)
                except Exception as e:
                    logger.error(f"Token callback error: {e}")

        # Add assistant response to history
        self._history.append(Message(role="assistant", content=full_response))

        # Trim history if too long
        self._trim_history()

        # Create completion result
        # Note: prompt_tokens is an estimate since we're streaming
        estimated_prompt_tokens = len(prompt) // 4
        completion = CompletionResult(
            text=full_response,
            tokens_generated=tokens_generated,
            prompt_tokens=estimated_prompt_tokens,
            finish_reason="stop",
        )

        # Notify completion callbacks
        for callback in self._completion_callbacks:
            try:
                await callback(completion)
            except Exception as e:
                logger.error(f"Completion callback error: {e}")

        return completion

    def _build_prompt(self) -> str:
        """Build prompt with system message and conversation history.

        Uses Phi-3 chat format:
        <|system|>\\n{system_prompt}<|end|>\\n
        <|user|>\\n{user_msg}<|end|>\\n
        <|assistant|>\\n

        Returns:
            Formatted prompt string.
        """
        parts = [f"<|system|>\n{self.system_prompt}<|end|>"]

        for msg in self._history[-self.max_history_messages :]:
            role_tag = "<|user|>" if msg.role == "user" else "<|assistant|>"
            parts.append(f"{role_tag}\n{msg.content}<|end|>")

        parts.append("<|assistant|>\n")
        return "\n".join(parts)

    def _trim_history(self) -> None:
        """Keep history within bounds."""
        if len(self._history) > self.max_history_messages * 2:
            self._history = self._history[-self.max_history_messages :]

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._history.clear()
        logger.info("LLM: Conversation history cleared")

    # Callback registration methods

    def add_token_callback(self, callback: TokenCallback) -> None:
        """Register a callback for streaming tokens.

        Args:
            callback: Async function called with each generated token.
        """
        self._token_callbacks.append(callback)

    def remove_token_callback(self, callback: TokenCallback) -> None:
        """Remove a token callback.

        Args:
            callback: The callback to remove.
        """
        if callback in self._token_callbacks:
            self._token_callbacks.remove(callback)

    def add_completion_callback(
        self, callback: Callable[[CompletionResult], Awaitable[None]]
    ) -> None:
        """Register a callback for completed responses.

        Args:
            callback: Async function called with the full CompletionResult.
        """
        self._completion_callbacks.append(callback)

    def remove_completion_callback(
        self, callback: Callable[[CompletionResult], Awaitable[None]]
    ) -> None:
        """Remove a completion callback.

        Args:
            callback: The callback to remove.
        """
        if callback in self._completion_callbacks:
            self._completion_callbacks.remove(callback)

    # Stats and monitoring

    @property
    def stats(self) -> dict:
        """Get processor statistics.

        Returns:
            Dictionary with processor state information.
        """
        return {
            "history_length": len(self._history),
            "token_callbacks": len(self._token_callbacks),
            "completion_callbacks": len(self._completion_callbacks),
            "model_loaded": self.generator.model_loaded,
        }

    @property
    def history(self) -> list[Message]:
        """Get conversation history (read-only copy).

        Returns:
            Copy of the conversation history.
        """
        return list(self._history)

    def estimate_context_tokens(self) -> int:
        """Estimate tokens used by current history.

        Returns:
            Approximate token count (assumes ~4 chars per token).
        """
        # Rough estimate: ~4 chars per token
        total_chars = sum(len(m.content) for m in self._history)
        return total_chars // 4
