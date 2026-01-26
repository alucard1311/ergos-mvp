"""LLM generator wrapper for llama-cpp-python."""

import asyncio
import logging
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from llama_cpp import Llama

from .types import CompletionResult, GenerationConfig

logger = logging.getLogger(__name__)


class LLMGenerator:
    """Wrapper for llama-cpp-python model inference with lazy loading."""

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 2048,
        n_gpu_layers: int = -1,
    ) -> None:
        """Initialize generator with model path and config.

        Args:
            model_path: Path to the GGUF model file.
            n_ctx: Context window size (default 2048 for Phi-3 Mini).
            n_gpu_layers: Number of layers to offload to GPU (-1 = all).
        """
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._model: Optional[Llama] = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    def _ensure_model(self) -> Llama:
        """Lazy load the model on first use.

        Returns:
            The loaded Llama model.
        """
        if self._model is None:
            logger.info(f"Loading LLM model from {self._model_path}...")
            self._model = Llama(
                model_path=self._model_path,
                n_ctx=self._n_ctx,
                n_gpu_layers=self._n_gpu_layers,
                n_threads=4,
                verbose=False,
            )
            logger.info("LLM model loaded successfully")
        return self._model

    def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
    ) -> CompletionResult:
        """Generate text from a prompt synchronously.

        Args:
            prompt: The input prompt for generation.
            config: Generation configuration (uses defaults if None).

        Returns:
            CompletionResult with generated text and token counts.
        """
        if config is None:
            config = GenerationConfig()

        model = self._ensure_model()

        result = model.create_completion(
            prompt,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            stop=config.stop_sequences if config.stop_sequences else None,
        )

        # Extract result data
        text = result["choices"][0]["text"]
        finish_reason = result["choices"][0].get("finish_reason", "stop")
        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

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
        """Generate text from a prompt with streaming.

        Yields tokens as they are generated. Runs model inference
        in a thread pool to avoid blocking the event loop.

        Args:
            prompt: The input prompt for generation.
            config: Generation configuration (uses defaults if None).

        Yields:
            Generated tokens as strings.
        """
        if config is None:
            config = GenerationConfig()

        model = self._ensure_model()

        # Create streaming completion in thread pool
        loop = asyncio.get_event_loop()

        def create_stream():
            return model.create_completion(
                prompt,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
                stop=config.stop_sequences if config.stop_sequences else None,
                stream=True,
            )

        stream = await loop.run_in_executor(self._executor, create_stream)

        # Yield tokens from the stream
        for chunk in stream:
            token = chunk["choices"][0].get("text", "")
            if token:
                yield token

    @property
    def model_loaded(self) -> bool:
        """Check if the model is currently loaded.

        Returns:
            True if model is loaded, False otherwise.
        """
        return self._model is not None

    @property
    def context_size(self) -> int:
        """Get the configured context window size.

        Returns:
            The context window size in tokens.
        """
        return self._n_ctx

    def close(self) -> None:
        """Release model resources."""
        if self._model is not None:
            # llama-cpp-python handles cleanup on del
            self._model = None
            logger.info("LLM model released")
        self._executor.shutdown(wait=False)
