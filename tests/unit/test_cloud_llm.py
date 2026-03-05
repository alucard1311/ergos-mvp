"""Tests for CloudLLMGenerator and FallbackLLMGenerator."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock the openai module before any imports of cloud_generator
# ---------------------------------------------------------------------------

_mock_openai = MagicMock()
sys.modules.setdefault("openai", _mock_openai)


# ---------------------------------------------------------------------------
# Chatml parsing tests
# ---------------------------------------------------------------------------

class TestChatmlParsing:
    """Test _parse_chatml_to_messages extracts roles and content correctly."""

    def test_simple_conversation(self):
        from ergos.llm.cloud_generator import _parse_chatml_to_messages

        prompt = (
            "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n"
            "<|im_start|>user\nHello!<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        messages = _parse_chatml_to_messages(prompt)
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "You are a helpful assistant."}
        assert messages[1] == {"role": "user", "content": "Hello!"}

    def test_multiline_content(self):
        from ergos.llm.cloud_generator import _parse_chatml_to_messages

        prompt = (
            "<|im_start|>system\nLine one.\nLine two.\nLine three.<|im_end|>\n"
            "<|im_start|>user\nWhat is 2+2?<|im_end|>\n"
        )
        messages = _parse_chatml_to_messages(prompt)
        assert len(messages) == 2
        assert "Line one.\nLine two.\nLine three." == messages[0]["content"]

    def test_empty_prompt(self):
        from ergos.llm.cloud_generator import _parse_chatml_to_messages

        assert _parse_chatml_to_messages("") == []

    def test_tool_defs_in_system(self):
        """System prompt with <tools> block should parse correctly."""
        from ergos.llm.cloud_generator import _parse_chatml_to_messages

        prompt = (
            "<|im_start|>system\nYou are an assistant.\n\n"
            "# Tools\n<tools>\n[{\"type\": \"function\"}]\n</tools><|im_end|>\n"
            "<|im_start|>user\nRun a command<|im_end|>\n"
        )
        messages = _parse_chatml_to_messages(prompt)
        assert len(messages) == 2
        assert "<tools>" in messages[0]["content"]

    def test_trailing_assistant_tag(self):
        """Prompt ending with <|im_start|>assistant\\n should not produce empty message."""
        from ergos.llm.cloud_generator import _parse_chatml_to_messages

        prompt = (
            "<|im_start|>system\nHi<|im_end|>\n"
            "<|im_start|>user\nHello<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        messages = _parse_chatml_to_messages(prompt)
        assert len(messages) == 2


# ---------------------------------------------------------------------------
# Helper: create a CloudLLMGenerator with mock clients injected
# ---------------------------------------------------------------------------

def _make_mock_choice(content="Hello!", finish_reason="stop"):
    choice = MagicMock()
    choice.message.content = content
    choice.message.role = "assistant"
    choice.finish_reason = finish_reason
    return choice


def _make_mock_response(content="Hello!", prompt_tokens=10, completion_tokens=5):
    response = MagicMock()
    response.choices = [_make_mock_choice(content)]
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    return response


def _make_cloud_generator(sync_client=None, async_client=None):
    """Create a CloudLLMGenerator with mock clients injected directly."""
    from ergos.llm.cloud_generator import CloudLLMGenerator

    gen = CloudLLMGenerator.__new__(CloudLLMGenerator)
    gen._model_name = "test-model"
    gen._chat_format = "chatml"
    gen._n_ctx = 16384
    gen._max_tokens = 512
    gen._cancelled = False
    gen._generating = False
    gen._sync_client = sync_client or MagicMock()
    gen._async_client = async_client or AsyncMock()
    return gen


# ---------------------------------------------------------------------------
# CloudLLMGenerator tests
# ---------------------------------------------------------------------------

class TestCloudGenerator:
    """Test CloudLLMGenerator with mocked OpenAI clients."""

    def test_generate_sync(self):
        mock_sync = MagicMock()
        mock_sync.chat.completions.create.return_value = _make_mock_response("World!")
        gen = _make_cloud_generator(sync_client=mock_sync)

        prompt = "<|im_start|>user\nHello<|im_end|>\n<|im_start|>assistant\n"
        result = gen.generate(prompt)
        assert result.text == "World!"
        assert result.tokens_generated == 5

        # Verify messages were parsed from chatml
        call_kwargs = mock_sync.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    def test_create_chat_completion_sync(self):
        mock_sync = MagicMock()
        mock_sync.chat.completions.create.return_value = _make_mock_response("Tool result")
        gen = _make_cloud_generator(sync_client=mock_sync)

        messages = [{"role": "user", "content": "hello"}]
        result = gen.create_chat_completion_sync(messages, max_tokens=100)

        # Must match llama-cpp format
        assert "choices" in result
        assert result["choices"][0]["message"]["content"] == "Tool result"
        assert result["choices"][0]["message"]["role"] == "assistant"

    def test_properties(self):
        gen = _make_cloud_generator()
        gen._chat_format = "chatml"
        gen._n_ctx = 8192
        assert gen.chat_format == "chatml"
        assert gen.model_loaded is True
        assert gen.context_size == 8192

    @pytest.mark.asyncio
    async def test_generate_stream(self):
        async def mock_stream():
            for text in ["Hello", " world", "!"]:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = text
                yield chunk

        mock_async = AsyncMock()
        mock_async.chat.completions.create = AsyncMock(return_value=mock_stream())
        gen = _make_cloud_generator(async_client=mock_async)

        tokens = []
        async for token in gen.generate_stream("<|im_start|>user\nHi<|im_end|>\n"):
            tokens.append(token)

        assert tokens == ["Hello", " world", "!"]

    @pytest.mark.asyncio
    async def test_cancel_stops_stream(self):
        """Cancelling mid-stream should stop yielding tokens."""
        class MockStream:
            def __init__(self):
                self._items = ["one", "two", "three", "four"]
                self._index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._items):
                    raise StopAsyncIteration
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = self._items[self._index]
                self._index += 1
                return chunk

            async def close(self):
                pass

        mock_async = AsyncMock()
        mock_async.chat.completions.create = AsyncMock(return_value=MockStream())
        gen = _make_cloud_generator(async_client=mock_async)

        tokens = []
        async for token in gen.generate_stream("<|im_start|>user\nHi<|im_end|>\n"):
            tokens.append(token)
            if len(tokens) == 2:
                gen.cancel()

        # Should have stopped after cancel
        assert len(tokens) <= 3

    @pytest.mark.asyncio
    async def test_warm_up(self):
        mock_async = AsyncMock()
        mock_async.chat.completions.create = AsyncMock(return_value=MagicMock())
        gen = _make_cloud_generator(async_client=mock_async)

        await gen.warm_up()
        mock_async.chat.completions.create.assert_called_once()
        call_kwargs = mock_async.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 1


# ---------------------------------------------------------------------------
# FallbackLLMGenerator tests
# ---------------------------------------------------------------------------

class TestFallbackGenerator:
    """Test FallbackLLMGenerator cloud-first with local fallback."""

    def test_generate_uses_cloud_when_healthy(self):
        from ergos.llm.fallback_generator import FallbackLLMGenerator
        from ergos.llm.types import CompletionResult

        cloud = MagicMock()
        cloud.generate.return_value = CompletionResult(
            text="cloud response", tokens_generated=10, prompt_tokens=5
        )
        local = MagicMock()

        gen = FallbackLLMGenerator(cloud, local)
        result = gen.generate("prompt")

        assert result.text == "cloud response"
        cloud.generate.assert_called_once()
        local.generate.assert_not_called()

    def test_generate_falls_back_on_cloud_error(self):
        from ergos.llm.fallback_generator import FallbackLLMGenerator
        from ergos.llm.types import CompletionResult

        cloud = MagicMock()
        cloud.generate.side_effect = ConnectionError("timeout")
        local = MagicMock()
        local.generate.return_value = CompletionResult(
            text="local response", tokens_generated=8, prompt_tokens=5
        )

        gen = FallbackLLMGenerator(cloud, local)
        result = gen.generate("prompt")

        assert result.text == "local response"
        assert gen._cloud_healthy is False

    def test_generate_skips_cloud_after_failure(self):
        """Once cloud is marked unhealthy, subsequent calls go straight to local."""
        from ergos.llm.fallback_generator import FallbackLLMGenerator
        from ergos.llm.types import CompletionResult

        cloud = MagicMock()
        cloud.generate.side_effect = ConnectionError("down")
        local = MagicMock()
        local.generate.return_value = CompletionResult(
            text="local", tokens_generated=5, prompt_tokens=5
        )

        gen = FallbackLLMGenerator(cloud, local)
        gen.generate("first")
        cloud.generate.reset_mock()

        gen.generate("second")
        cloud.generate.assert_not_called()
        assert local.generate.call_count == 2

    def test_create_chat_completion_sync_fallback(self):
        from ergos.llm.fallback_generator import FallbackLLMGenerator

        cloud = MagicMock()
        cloud.create_chat_completion_sync.side_effect = RuntimeError("network")
        local = MagicMock()
        local.create_chat_completion_sync.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "local"}}]
        }

        gen = FallbackLLMGenerator(cloud, local)
        result = gen.create_chat_completion_sync([{"role": "user", "content": "hi"}])

        assert result["choices"][0]["message"]["content"] == "local"

    def test_cancel_cancels_both(self):
        from ergos.llm.fallback_generator import FallbackLLMGenerator

        cloud = MagicMock()
        local = MagicMock()
        gen = FallbackLLMGenerator(cloud, local)

        gen.cancel()
        cloud.cancel.assert_called_once()
        local.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_warm_up_resets_health(self):
        from ergos.llm.fallback_generator import FallbackLLMGenerator

        cloud = MagicMock()
        cloud.warm_up = AsyncMock()
        local = MagicMock()

        gen = FallbackLLMGenerator(cloud, local)
        gen._cloud_healthy = False

        await gen.warm_up()
        assert gen._cloud_healthy is True
        cloud.warm_up.assert_called_once()

    @pytest.mark.asyncio
    async def test_warm_up_marks_unhealthy_on_failure(self):
        from ergos.llm.fallback_generator import FallbackLLMGenerator

        cloud = MagicMock()
        cloud.warm_up = AsyncMock(side_effect=ConnectionError("unreachable"))
        local = MagicMock()

        gen = FallbackLLMGenerator(cloud, local)
        await gen.warm_up()
        assert gen._cloud_healthy is False

    @pytest.mark.asyncio
    async def test_stream_falls_back_on_error(self):
        from ergos.llm.fallback_generator import FallbackLLMGenerator

        cloud = MagicMock()

        async def cloud_stream(*a, **kw):
            raise ConnectionError("stream failed")
            yield  # noqa: unreachable - makes it an async generator

        cloud.generate_stream = cloud_stream

        local = MagicMock()

        async def local_stream(*a, **kw):
            for t in ["local", " tokens"]:
                yield t

        local.generate_stream = local_stream

        gen = FallbackLLMGenerator(cloud, local)
        tokens = []
        async for token in gen.generate_stream("prompt"):
            tokens.append(token)

        assert tokens == ["local", " tokens"]
        assert gen._cloud_healthy is False

    def test_properties_delegate_to_cloud(self):
        from ergos.llm.fallback_generator import FallbackLLMGenerator

        cloud = MagicMock()
        cloud.chat_format = "chatml"
        cloud.model_loaded = True
        cloud.context_size = 16384
        local = MagicMock()
        local.model_loaded = False

        gen = FallbackLLMGenerator(cloud, local)
        assert gen.chat_format == "chatml"
        assert gen.model_loaded is True
        assert gen.context_size == 16384


# ---------------------------------------------------------------------------
# Config integration test
# ---------------------------------------------------------------------------

class TestConfigFields:
    """Test that LLMConfig accepts cloud fields."""

    def test_cloud_fields_default_none(self):
        from ergos.config import LLMConfig
        cfg = LLMConfig()
        assert cfg.cloud_endpoint_url is None
        assert cfg.cloud_api_key is None
        assert cfg.cloud_model_name == "Qwen/Qwen3-32B"
        assert cfg.cloud_timeout == 60.0

    def test_cloud_fields_set(self):
        from ergos.config import LLMConfig
        cfg = LLMConfig(
            cloud_endpoint_url="http://example.com/v1",
            cloud_api_key="key123",
            cloud_model_name="Qwen/Qwen3-14B",
            cloud_timeout=30.0,
        )
        assert cfg.cloud_endpoint_url == "http://example.com/v1"
        assert cfg.cloud_api_key == "key123"
        assert cfg.cloud_model_name == "Qwen/Qwen3-14B"
        assert cfg.cloud_timeout == 30.0
