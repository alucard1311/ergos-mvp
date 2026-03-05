"""Cloud LLM generator using OpenAI-compatible API (RunPod vLLM endpoint)."""

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from typing import Optional

from .types import CompletionResult, GenerationConfig

logger = logging.getLogger(__name__)

# Parse chatml prompt back into messages list
# Matches: <|im_start|>role\ncontent<|im_end|>
_CHATML_RE = re.compile(
    r"<\|im_start\|>(\w+)\n(.*?)(?:<\|im_end\|>|$)", re.DOTALL
)


def _parse_chatml_to_messages(prompt: str) -> list[dict]:
    """Convert a chatml-formatted prompt string back into OpenAI messages list.

    Args:
        prompt: Chatml formatted string with <|im_start|>role\\ncontent<|im_end|> blocks.

    Returns:
        List of {"role": ..., "content": ...} dicts.
    """
    messages = []
    for match in _CHATML_RE.finditer(prompt):
        role = match.group(1).strip()
        content = match.group(2).strip()
        if role and content:
            messages.append({"role": role, "content": content})
    return messages


class CloudLLMGenerator:
    """LLM generator using an OpenAI-compatible cloud endpoint (e.g. RunPod vLLM).

    Implements the same interface as LLMGenerator so it can be used as a drop-in
    replacement in LLMProcessor and ToolCallProcessor.
    """

    def __init__(
        self,
        endpoint_url: str,
        api_key: str,
        model_name: str = "Qwen/Qwen3-32B",
        timeout: float = 60.0,
        chat_format: str = "chatml",
        n_ctx: int = 16384,
        max_tokens: int = 512,
    ) -> None:
        from openai import AsyncOpenAI, OpenAI

        self._model_name = model_name
        self._chat_format = chat_format
        self._n_ctx = n_ctx
        self._max_tokens = max_tokens
        self._cancelled = False
        self._generating = False

        # Sync client for generate() and create_chat_completion_sync()
        self._sync_client = OpenAI(
            base_url=endpoint_url,
            api_key=api_key or "none",
            timeout=timeout,
        )
        # Async client for generate_stream()
        self._async_client = AsyncOpenAI(
            base_url=endpoint_url,
            api_key=api_key or "none",
            timeout=timeout,
        )
        logger.info(f"CloudLLMGenerator initialized: {endpoint_url} model={model_name}")

    def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
    ) -> CompletionResult:
        """Generate text synchronously via cloud endpoint.

        Args:
            prompt: Chatml-formatted prompt string.
            config: Generation configuration (uses defaults if None).

        Returns:
            CompletionResult with generated text and token counts.
        """
        if config is None:
            config = GenerationConfig()

        messages = _parse_chatml_to_messages(prompt)
        if not messages:
            messages = [{"role": "user", "content": prompt}]

        response = self._sync_client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            stop=config.stop_sequences if config.stop_sequences else None,
        )

        choice = response.choices[0]
        text = choice.message.content or ""
        finish_reason = choice.finish_reason or "stop"
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        return CompletionResult(
            text=text,
            tokens_generated=completion_tokens,
            prompt_tokens=prompt_tokens,
            finish_reason=finish_reason,
        )

    async def generate_stream(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
    ) -> AsyncIterator[str]:
        """Generate text with streaming via cloud endpoint.

        Args:
            prompt: Chatml-formatted prompt string.
            config: Generation configuration (uses defaults if None).

        Yields:
            Generated tokens as strings.
        """
        self._cancelled = False
        self._generating = True

        if config is None:
            config = GenerationConfig()

        messages = _parse_chatml_to_messages(prompt)
        if not messages:
            messages = [{"role": "user", "content": prompt}]

        try:
            stream = await self._async_client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
                stop=config.stop_sequences if config.stop_sequences else None,
                stream=True,
            )

            async for chunk in stream:
                if self._cancelled:
                    await stream.close()
                    logger.info("Cloud LLM: Generation cancelled mid-stream")
                    break
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception:
            if not self._cancelled:
                raise
        finally:
            self._generating = False

    @property
    def chat_format(self) -> str:
        return self._chat_format

    @property
    def model_loaded(self) -> bool:
        return True  # Cloud is always "loaded"

    @property
    def context_size(self) -> int:
        return self._n_ctx

    def create_chat_completion_sync(
        self,
        messages: list[dict],
        max_tokens: int = 512,
    ) -> dict:
        """Sync chat completion matching llama-cpp-python's return format.

        Args:
            messages: List of message dicts in chat format.
            max_tokens: Maximum tokens to generate.

        Returns:
            Dict matching llama-cpp format: {"choices": [{"message": {"role", "content"}}]}
        """
        response = self._sync_client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
            stop=["<|im_end|>", "<|endoftext|>"],
        )

        choice = response.choices[0]
        return {
            "choices": [{
                "message": {
                    "role": choice.message.role,
                    "content": choice.message.content or "",
                },
                "finish_reason": choice.finish_reason or "stop",
            }],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }

    def cancel(self) -> None:
        """Cancel any ongoing generation (for barge-in support)."""
        if self._generating:
            logger.info("Cloud LLM: Cancel requested")
            self._cancelled = True

    async def warm_up(self) -> None:
        """Send a minimal request to wake up a serverless worker.

        RunPod serverless workers can have 5-15s cold start. Calling this
        on WebRTC connect pre-warms the endpoint so first real request is fast.
        """
        try:
            response = await self._async_client.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            logger.info("Cloud LLM: Endpoint warmed up successfully")
        except Exception as e:
            logger.warning(f"Cloud LLM: Warm-up failed: {e}")

    def close(self) -> None:
        """Release resources."""
        self.cancel()
        self._sync_client.close()
        # AsyncOpenAI close needs to be called from async context
        # It will be garbage collected properly
        logger.info("Cloud LLM generator closed")
