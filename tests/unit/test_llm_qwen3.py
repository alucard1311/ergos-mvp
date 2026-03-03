"""Unit tests for LLM Qwen3 chatml format support."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ergos.llm.generator import LLMGenerator
from ergos.llm.processor import LLMProcessor, Message


class TestLLMGeneratorChatFormat:
    """Tests for LLMGenerator chat_format parameter."""

    def test_generator_accepts_chat_format_parameter(self):
        """LLMGenerator.__init__ accepts chat_format parameter."""
        with patch("ergos.llm.generator.Llama"):
            gen = LLMGenerator(
                model_path="/tmp/fake.gguf",
                chat_format="chatml",
            )
        assert gen.chat_format == "chatml"

    def test_generator_chat_format_default_is_chatml(self):
        """LLMGenerator defaults to chatml format."""
        with patch("ergos.llm.generator.Llama"):
            gen = LLMGenerator(model_path="/tmp/fake.gguf")
        assert gen.chat_format == "chatml"

    def test_generator_phi3_format(self):
        """LLMGenerator stores phi3 format when specified."""
        with patch("ergos.llm.generator.Llama"):
            gen = LLMGenerator(
                model_path="/tmp/fake.gguf",
                chat_format="phi3",
            )
        assert gen.chat_format == "phi3"

    def test_generator_n_gpu_layers_stored(self):
        """LLMGenerator stores n_gpu_layers from constructor."""
        with patch("ergos.llm.generator.Llama"):
            gen = LLMGenerator(
                model_path="/tmp/fake.gguf",
                n_gpu_layers=32,
            )
        assert gen._n_gpu_layers == 32


class TestLLMProcessorChatFormat:
    """Tests for LLMProcessor chat_format field and prompt building."""

    def _make_processor(self, chat_format="chatml") -> LLMProcessor:
        """Create a processor with mocked generator."""
        mock_gen = MagicMock(spec=LLMGenerator)
        mock_gen.model_loaded = False
        mock_gen.chat_format = chat_format
        proc = LLMProcessor(
            generator=mock_gen,
            system_prompt="You are a test assistant.",
            chat_format=chat_format,
        )
        return proc

    def test_processor_accepts_chat_format(self):
        """LLMProcessor accepts chat_format parameter."""
        proc = self._make_processor(chat_format="chatml")
        assert proc.chat_format == "chatml"

    def test_processor_chat_format_default_is_chatml(self):
        """LLMProcessor defaults to chatml format."""
        mock_gen = MagicMock(spec=LLMGenerator)
        mock_gen.model_loaded = False
        proc = LLMProcessor(generator=mock_gen, system_prompt="test")
        assert proc.chat_format == "chatml"

    def test_build_prompt_chatml_format_basic(self):
        """_build_prompt generates chatml format with system and user messages."""
        proc = self._make_processor(chat_format="chatml")
        proc._history = [Message(role="user", content="Hello")]
        prompt = proc._build_prompt()

        assert "<|im_start|>system" in prompt
        assert "You are a test assistant." in prompt
        assert "<|im_end|>" in prompt
        assert "<|im_start|>user" in prompt
        assert "Hello" in prompt
        assert "<|im_start|>assistant" in prompt

    def test_build_prompt_chatml_format_exact_structure(self):
        """_build_prompt generates exact chatml template structure."""
        proc = self._make_processor(chat_format="chatml")
        proc._history = [Message(role="user", content="Hello")]
        prompt = proc._build_prompt()

        expected_system = "<|im_start|>system\nYou are a test assistant.<|im_end|>"
        expected_user = "<|im_start|>user\nHello<|im_end|>"
        expected_assistant_start = "<|im_start|>assistant\n"

        assert expected_system in prompt
        assert expected_user in prompt
        assert prompt.endswith(expected_assistant_start)

    def test_build_prompt_chatml_multi_turn_history(self):
        """_build_prompt generates chatml format with multi-turn conversation."""
        proc = self._make_processor(chat_format="chatml")
        proc._history = [
            Message(role="user", content="What is 2+2?"),
            Message(role="assistant", content="It is 4."),
            Message(role="user", content="And 3+3?"),
        ]
        prompt = proc._build_prompt()

        assert "<|im_start|>user\nWhat is 2+2?<|im_end|>" in prompt
        assert "<|im_start|>assistant\nIt is 4.<|im_end|>" in prompt
        assert "<|im_start|>user\nAnd 3+3?<|im_end|>" in prompt
        # Ends with assistant turn
        assert prompt.endswith("<|im_start|>assistant\n")

    def test_build_prompt_phi3_format_backward_compat(self):
        """_build_prompt generates phi3 format for backward compatibility."""
        proc = self._make_processor(chat_format="phi3")
        proc._history = [Message(role="user", content="Hello")]
        prompt = proc._build_prompt()

        assert "<|system|>" in prompt
        assert "You are a test assistant." in prompt
        assert "<|end|>" in prompt
        assert "<|user|>" in prompt
        assert "Hello" in prompt
        assert "<|assistant|>" in prompt
        # chatml tokens should NOT appear in phi3 format
        assert "<|im_start|>" not in prompt
        assert "<|im_end|>" not in prompt

    def test_build_prompt_phi3_ends_with_assistant(self):
        """_build_prompt phi3 format ends with <|assistant|>\\n."""
        proc = self._make_processor(chat_format="phi3")
        proc._history = [Message(role="user", content="Hello")]
        prompt = proc._build_prompt()

        assert prompt.endswith("<|assistant|>\n")

    def test_get_stop_sequences_chatml(self):
        """_get_stop_sequences returns chatml stop tokens."""
        proc = self._make_processor(chat_format="chatml")
        stops = proc._get_stop_sequences()

        assert "<|im_end|>" in stops
        assert "<|endoftext|>" in stops

    def test_get_stop_sequences_phi3(self):
        """_get_stop_sequences returns phi3 stop tokens."""
        proc = self._make_processor(chat_format="phi3")
        stops = proc._get_stop_sequences()

        assert "<|end|>" in stops
        # chatml tokens should not be in phi3 stops
        assert "<|im_end|>" not in stops

    def test_process_transcription_uses_format_stop_sequences(self):
        """process_transcription passes format-appropriate stop sequences to GenerationConfig."""
        import asyncio

        proc = self._make_processor(chat_format="chatml")

        # Capture the config passed to generate_stream
        captured_configs = []

        async def mock_generate_stream(prompt, config=None):
            captured_configs.append(config)
            # Return empty async generator
            return
            yield  # Make it a generator

        proc.generator.generate_stream = mock_generate_stream

        # Create a mock transcription result
        from ergos.stt.types import TranscriptionResult
        result = TranscriptionResult(
            text="Hello there",
            language="en",
        )

        async def run():
            await proc.process_transcription(result)

        asyncio.run(run())

        assert len(captured_configs) == 1
        config = captured_configs[0]
        assert config is not None
        assert "<|im_end|>" in config.stop_sequences


class TestLLMProcessorChatFormatNoModel:
    """Tests that verify format without loading any models."""

    def test_chatml_prompt_has_no_phi3_tokens(self):
        """Chatml prompt contains no phi3 special tokens."""
        mock_gen = MagicMock(spec=LLMGenerator)
        mock_gen.model_loaded = False
        proc = LLMProcessor(
            generator=mock_gen,
            system_prompt="System prompt here.",
            chat_format="chatml",
        )
        proc._history = [Message(role="user", content="User input")]
        prompt = proc._build_prompt()

        assert "<|system|>" not in prompt
        assert "<|user|>" not in prompt
        assert "<|end|>" not in prompt

    def test_phi3_prompt_has_no_chatml_tokens(self):
        """Phi3 prompt contains no chatml special tokens."""
        mock_gen = MagicMock(spec=LLMGenerator)
        mock_gen.model_loaded = False
        proc = LLMProcessor(
            generator=mock_gen,
            system_prompt="System prompt here.",
            chat_format="phi3",
        )
        proc._history = [Message(role="user", content="User input")]
        prompt = proc._build_prompt()

        assert "<|im_start|>" not in prompt
        assert "<|im_end|>" not in prompt
        assert "<|endoftext|>" not in prompt

    def test_generator_not_loaded_during_prompt_build(self):
        """_build_prompt does not trigger model loading."""
        mock_gen = MagicMock(spec=LLMGenerator)
        mock_gen.model_loaded = False
        proc = LLMProcessor(
            generator=mock_gen,
            system_prompt="test",
            chat_format="chatml",
        )
        proc._history = [Message(role="user", content="test")]
        proc._build_prompt()

        # _ensure_model should NOT have been called
        mock_gen._ensure_model.assert_not_called()
