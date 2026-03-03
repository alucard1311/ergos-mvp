"""Unit tests for v2 config schema extensions."""

from pathlib import Path

import pytest

from ergos.config import Config, LLMConfig, STTConfig, load_config


class TestSTTConfigV2:
    """Tests for STTConfig v2 fields."""

    def test_compute_type_default(self):
        """STTConfig has compute_type field defaulting to 'auto'."""
        cfg = STTConfig()
        assert cfg.compute_type == "auto"

    def test_compute_type_explicit(self):
        """STTConfig accepts explicit compute_type values."""
        for ct in ("auto", "int8", "float16", "float32"):
            cfg = STTConfig(compute_type=ct)
            assert cfg.compute_type == ct

    def test_model_default_unchanged(self):
        """STTConfig model default is still 'base' for backward compat."""
        cfg = STTConfig()
        assert cfg.model == "base"

    def test_device_default_unchanged(self):
        """STTConfig device default is still 'auto'."""
        cfg = STTConfig()
        assert cfg.device == "auto"


class TestLLMConfigV2:
    """Tests for LLMConfig v2 fields."""

    def test_chat_format_default(self):
        """LLMConfig has chat_format field defaulting to 'chatml'."""
        cfg = LLMConfig()
        assert cfg.chat_format == "chatml"

    def test_n_gpu_layers_default(self):
        """LLMConfig has n_gpu_layers field defaulting to -1."""
        cfg = LLMConfig()
        assert cfg.n_gpu_layers == -1

    def test_chat_format_explicit(self):
        """LLMConfig accepts explicit chat_format value."""
        cfg = LLMConfig(chat_format="llama-3")
        assert cfg.chat_format == "llama-3"

    def test_n_gpu_layers_explicit(self):
        """LLMConfig accepts explicit n_gpu_layers."""
        cfg = LLMConfig(n_gpu_layers=32)
        assert cfg.n_gpu_layers == 32

    def test_existing_fields_unchanged(self):
        """LLMConfig existing fields still have correct defaults."""
        cfg = LLMConfig()
        assert cfg.context_length == 4096
        assert cfg.max_tokens == 512
        assert cfg.device == "auto"
        assert cfg.model_path is None


class TestBackwardCompatibility:
    """Tests for backward compatibility with v1 config format."""

    def test_v1_config_dict_loads(self):
        """Loading a v1-style config dict (no v2 fields) still works via Pydantic defaults."""
        v1_data = {
            "stt": {
                "model": "tiny.en",
                "device": "auto",
                # No compute_type — should use default
            },
            "llm": {
                "model_path": "/path/to/model.gguf",
                "context_length": 1024,
                "max_tokens": 256,
                "device": "auto",
                # No chat_format or n_gpu_layers — should use defaults
            },
        }
        config = Config(**v1_data)

        # New v2 fields get defaults
        assert config.stt.compute_type == "auto"
        assert config.llm.chat_format == "chatml"
        assert config.llm.n_gpu_layers == -1

        # Old fields preserved
        assert config.stt.model == "tiny.en"
        assert config.llm.context_length == 1024
        assert config.llm.max_tokens == 256

    def test_v2_config_dict_loads(self):
        """Loading a v2-style config dict with all new fields works."""
        v2_data = {
            "stt": {
                "model": "small.en",
                "device": "auto",
                "compute_type": "int8",
            },
            "llm": {
                "model_path": "/path/to/qwen3.gguf",
                "context_length": 4096,
                "max_tokens": 512,
                "device": "auto",
                "chat_format": "chatml",
                "n_gpu_layers": -1,
            },
        }
        config = Config(**v2_data)

        assert config.stt.model == "small.en"
        assert config.stt.compute_type == "int8"
        assert config.llm.chat_format == "chatml"
        assert config.llm.n_gpu_layers == -1


class TestConfigYaml:
    """Tests for config.yaml v2 defaults."""

    def test_config_yaml_loads(self):
        """config.yaml can be loaded without errors."""
        config = load_config("/home/vinay/ergos/config.yaml")
        assert config is not None

    def test_config_yaml_stt_model(self):
        """config.yaml uses small.en STT model."""
        config = load_config("/home/vinay/ergos/config.yaml")
        assert config.stt.model == "small.en"

    def test_config_yaml_stt_compute_type(self):
        """config.yaml sets stt.compute_type to int8."""
        config = load_config("/home/vinay/ergos/config.yaml")
        assert config.stt.compute_type == "int8"

    def test_config_yaml_llm_chat_format(self):
        """config.yaml sets llm.chat_format to chatml."""
        config = load_config("/home/vinay/ergos/config.yaml")
        assert config.llm.chat_format == "chatml"

    def test_config_yaml_llm_n_gpu_layers(self):
        """config.yaml sets llm.n_gpu_layers to -1."""
        config = load_config("/home/vinay/ergos/config.yaml")
        assert config.llm.n_gpu_layers == -1

    def test_config_yaml_llm_context_length(self):
        """config.yaml llm.context_length is 4096 (upgraded from 1024)."""
        config = load_config("/home/vinay/ergos/config.yaml")
        assert config.llm.context_length == 4096
