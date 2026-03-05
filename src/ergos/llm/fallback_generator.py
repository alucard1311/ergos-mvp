"""Fallback LLM generator: cloud-first with local fallback."""

import logging
from collections.abc import AsyncIterator
from typing import Callable, Optional

from .types import CompletionResult, GenerationConfig

logger = logging.getLogger(__name__)


class FallbackLLMGenerator:
    """Wraps cloud + local generators with automatic failover.

    - Primary: cloud generator (RunPod vLLM)
    - Fallback: local generator (llama-cpp-python)
    - Health tracked per-session, reset on warm_up()

    Implements the same interface as LLMGenerator so it can be used
    as a drop-in replacement in LLMProcessor and ToolCallProcessor.
    """

    def __init__(self, cloud_generator, local_generator) -> None:
        self._cloud = cloud_generator
        self._local = local_generator
        self._cloud_healthy = True
        self._active_model: str = "cloud"
        self._on_model_change: Optional[Callable[[str], None]] = None

    def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
    ) -> CompletionResult:
        """Generate text, trying cloud first then falling back to local.

        Args:
            prompt: Chatml-formatted prompt string.
            config: Generation configuration.

        Returns:
            CompletionResult from whichever generator succeeded.
        """
        if self._cloud_healthy:
            try:
                result = self._cloud.generate(prompt, config)
                return result
            except Exception as e:
                logger.warning(f"Cloud LLM failed, falling back to local: {e}")
                self._switch_to_local()

        return self._local.generate(prompt, config)

    async def generate_stream(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
    ) -> AsyncIterator[str]:
        """Stream tokens, trying cloud first then falling back to local.

        Args:
            prompt: Chatml-formatted prompt string.
            config: Generation configuration.

        Yields:
            Generated tokens as strings.
        """
        if self._cloud_healthy:
            try:
                tokens_yielded = False
                async for token in self._cloud.generate_stream(prompt, config):
                    tokens_yielded = True
                    yield token
                if tokens_yielded:
                    return
                # If no tokens came out but no exception, still treat as failure
                logger.warning("Cloud LLM stream produced no tokens, falling back to local")
                self._switch_to_local()
            except Exception as e:
                logger.warning(f"Cloud LLM stream failed, falling back to local: {e}")
                self._switch_to_local()

        async for token in self._local.generate_stream(prompt, config):
            yield token

    @property
    def chat_format(self) -> str:
        return self._cloud.chat_format

    @property
    def model_loaded(self) -> bool:
        return self._cloud.model_loaded or self._local.model_loaded

    @property
    def context_size(self) -> int:
        return self._cloud.context_size

    def create_chat_completion_sync(
        self,
        messages: list[dict],
        max_tokens: int = 512,
    ) -> dict:
        """Sync chat completion with fallback.

        Args:
            messages: Chat messages list.
            max_tokens: Maximum tokens to generate.

        Returns:
            Dict matching llama-cpp format.
        """
        if self._cloud_healthy:
            try:
                return self._cloud.create_chat_completion_sync(messages, max_tokens)
            except Exception as e:
                logger.warning(f"Cloud LLM chat completion failed, falling back to local: {e}")
                self._switch_to_local()

        return self._local.create_chat_completion_sync(messages, max_tokens)

    @property
    def active_model(self) -> str:
        """Return which model is currently active: 'cloud' or 'local'."""
        return "cloud" if self._cloud_healthy else "local"

    def set_on_model_change(self, callback: Callable[[str], None]) -> None:
        """Set callback invoked when active model changes (cloud <-> local)."""
        self._on_model_change = callback

    def _switch_to_local(self) -> None:
        """Mark cloud as unhealthy and notify listener."""
        self._cloud_healthy = False
        self._active_model = "local"
        if self._on_model_change:
            self._on_model_change("local")

    def cancel(self) -> None:
        """Cancel ongoing generation on both generators."""
        self._cloud.cancel()
        self._local.cancel()

    async def warm_up(self) -> None:
        """Warm up cloud endpoint and reset health flag.

        Called on each WebRTC connect to give cloud a fresh chance
        even if it failed during a previous session.
        """
        self._cloud_healthy = True
        self._active_model = "cloud"
        try:
            await self._cloud.warm_up()
            logger.info("Fallback LLM: Cloud endpoint warmed up, cloud-first mode active")
            if self._on_model_change:
                self._on_model_change("cloud")
        except Exception as e:
            logger.warning(f"Fallback LLM: Cloud warm-up failed, using local only: {e}")
            self._switch_to_local()

    def close(self) -> None:
        """Release resources on both generators."""
        self._cloud.close()
        self._local.close()
