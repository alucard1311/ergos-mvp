"""LLM generator wrapper for llama-cpp-python."""

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from llama_cpp import Llama

from .types import CompletionResult, GenerationConfig

logger = logging.getLogger(__name__)


class GenerationCancelled(Exception):
    """Raised when generation is cancelled (e.g., barge-in)."""
    pass


class LLMGenerator:
    """Wrapper for llama-cpp-python model inference with lazy loading."""

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 2048,
        n_gpu_layers: int = -1,
        chat_format: str = "chatml",
    ) -> None:
        """Initialize generator with model path and config.

        Args:
            model_path: Path to the GGUF model file.
            n_ctx: Context window size (default 2048).
            n_gpu_layers: Number of layers to offload to GPU (-1 = all).
            chat_format: Chat template format to use ("chatml" for Qwen3,
                         "phi3" for Phi-3 legacy). Default is "chatml".
        """
        import os
        self._model_path = os.path.expanduser(model_path)
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._chat_format = chat_format
        self._model: Optional[Llama] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        # Lock to prevent concurrent access to llama_cpp model
        # llama_cpp is NOT thread-safe - concurrent sampling causes segfaults
        self._model_lock = threading.Lock()
        # Cancellation flag for current generation
        self._cancelled = False
        self._generating = False

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
                n_batch=512,  # Larger batch for faster prompt processing
                flash_attn=True,  # Flash attention for faster inference
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

        # Lock to prevent concurrent model access (llama_cpp is not thread-safe)
        with self._model_lock:
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
        # Reset cancellation state for new generation
        # (fixes Pitfall 3: cancel flag stuck after barge-in, silently killing next generation)
        self._cancelled = False
        self._generating = True

        if config is None:
            config = GenerationConfig()

        model = self._ensure_model()

        # Queue to pass tokens from thread to async
        import queue
        token_queue: queue.Queue = queue.Queue()
        generation_done = threading.Event()

        def run_streaming_generation():
            """Run streaming generation with lock held, putting tokens in queue."""
            with self._model_lock:
                stream = model.create_completion(
                    prompt,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    top_p=config.top_p,
                    stop=config.stop_sequences if config.stop_sequences else None,
                    stream=True,
                )
                for chunk in stream:
                    if self._cancelled:
                        break
                    token = chunk["choices"][0].get("text", "")
                    if token:
                        token_queue.put(token)
            generation_done.set()

        # Start generation in background thread
        self._executor.submit(run_streaming_generation)

        # Yield tokens as they arrive
        try:
            while not generation_done.is_set() or not token_queue.empty():
                try:
                    token = token_queue.get(timeout=0.05)
                    yield token
                    if self._cancelled:
                        logger.info("LLM: Generation cancelled mid-stream")
                        break
                except queue.Empty:
                    if self._cancelled:
                        break
                    await asyncio.sleep(0.01)
        finally:
            self._generating = False

    @property
    def chat_format(self) -> str:
        """Get the configured chat format.

        Returns:
            The chat format string (e.g., "chatml", "phi3").
        """
        return self._chat_format

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

    def cancel(self) -> None:
        """Cancel any ongoing generation (for barge-in support)."""
        if self._generating:
            logger.info("LLM: Cancel requested")
            self._cancelled = True

    def close(self) -> None:
        """Release model resources."""
        self.cancel()
        if self._model is not None:
            # llama-cpp-python handles cleanup on del
            self._model = None
            logger.info("LLM model released")
        self._executor.shutdown(wait=False)
