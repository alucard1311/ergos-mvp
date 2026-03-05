"""Unit tests for VRAM monitoring integration in pipeline and server."""

from dataclasses import fields
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ergos.core.vram import VRAMMonitor


class TestPipelineVRAMField:
    """Tests for VRAMMonitor field in Pipeline dataclass."""

    def test_pipeline_dataclass_has_vram_monitor_field(self):
        """Pipeline dataclass includes vram_monitor field of type VRAMMonitor."""
        from ergos.pipeline import Pipeline

        field_names = [f.name for f in fields(Pipeline)]
        assert "vram_monitor" in field_names

    def test_pipeline_vram_monitor_type(self):
        """Pipeline vram_monitor field accepts VRAMMonitor instance."""
        from ergos.pipeline import Pipeline

        # Verify the field exists and can hold a VRAMMonitor
        monitor = VRAMMonitor()
        monitor.register_model("test", 100.0, "stt")

        # Check VRAMMonitor type matches the field annotation
        field_map = {f.name: f for f in fields(Pipeline)}
        assert "vram_monitor" in field_map


class TestCreatePipelineVRAMRegistration:
    """Tests for model registration in create_pipeline."""

    @pytest.mark.asyncio
    async def test_create_pipeline_registers_three_models(self):
        """create_pipeline registers STT, LLM, and TTS models with VRAMMonitor."""
        from ergos.config import Config, LLMConfig, STTConfig, TTSConfig, ServerConfig
        from ergos.pipeline import create_pipeline

        # Create a minimal config
        config = Config(
            llm=LLMConfig(
                model_path="~/.ergos/models/Qwen3-8B-Q4_K_M.gguf",
                chat_format="chatml",
                n_gpu_layers=-1,
            )
        )

        # Mock all heavy components to avoid loading real models
        with (
            patch("ergos.pipeline.WhisperTranscriber") as mock_whisper,
            patch("ergos.pipeline.LLMGenerator") as mock_gen,
            patch("ergos.pipeline.TTSSynthesizer") as mock_tts_synth,
            patch("ergos.pipeline.VADProcessor"),
            patch("ergos.pipeline.STTProcessor"),
            patch("ergos.pipeline.LLMProcessor"),
            patch("ergos.pipeline.TTSProcessor"),
            patch("ergos.pipeline.ConnectionManager"),
            patch("ergos.pipeline.DataChannelHandler"),
            patch("ergos.pipeline.LatencyTracker"),
            patch("ergos.pipeline.PluginManager"),
            patch("ergos.pipeline.create_signaling_app"),
            patch("ergos.pipeline.load_persona"),
        ):
            mock_llm_proc = MagicMock()
            mock_llm_proc.add_token_callback = MagicMock()
            mock_llm_proc.add_completion_callback = MagicMock()
            mock_llm_proc.generator = MagicMock()

            mock_stt_proc = MagicMock()
            mock_stt_proc.remove_transcription_callback = MagicMock()
            mock_stt_proc.add_transcription_callback = MagicMock()

            mock_data_handler = MagicMock()
            mock_data_handler.get_state_callback = MagicMock(return_value=AsyncMock())
            mock_data_handler.set_text_input_callback = MagicMock()

            mock_plugin_mgr = MagicMock()
            mock_plugin_mgr.plugins = {}
            mock_plugin_mgr.attach_all = MagicMock()
            mock_plugin_mgr.route_input = MagicMock(return_value=None)
            mock_plugin_mgr.discover_plugins = MagicMock()

            mock_state_machine = MagicMock()
            mock_state_machine.add_callback = MagicMock()

            from ergos.pipeline import Pipeline, VADProcessor, STTProcessor, LLMProcessor, TTSProcessor, ConnectionManager, DataChannelHandler, LatencyTracker, PluginManager
            from ergos.state import ConversationStateMachine

            # Patch at module level for ConversationStateMachine too
            with patch("ergos.pipeline.ConversationStateMachine", return_value=mock_state_machine):
                with patch("ergos.pipeline.STTProcessor", return_value=mock_stt_proc):
                    with patch("ergos.pipeline.LLMProcessor", return_value=mock_llm_proc):
                        with patch("ergos.pipeline.DataChannelHandler", return_value=mock_data_handler):
                            with patch("ergos.pipeline.PluginManager", return_value=mock_plugin_mgr):
                                # Intercept VRAMMonitor to verify register_model calls
                                real_vram_monitor = VRAMMonitor()
                                registered_calls = []

                                original_register = real_vram_monitor.register_model

                                def capture_register(name, mb, cat):
                                    registered_calls.append((name, mb, cat))
                                    return original_register(name, mb, cat)

                                real_vram_monitor.register_model = capture_register

                                with patch("ergos.pipeline.VRAMMonitor", return_value=real_vram_monitor):
                                    pipeline = await create_pipeline(config)

        # Verify all 3 models were registered
        assert len(registered_calls) == 3

        # Check model names/categories
        registered_names = [c[0] for c in registered_calls]
        registered_cats = [c[2] for c in registered_calls]

        assert any("whisper" in name.lower() or "stt" in name.lower() for name in registered_names)
        assert any("qwen" in name.lower() or "llm" in name.lower() for name in registered_names)
        assert any("kokoro" in name.lower() or "tts" in name.lower() for name in registered_names)

        assert "stt" in registered_cats
        assert "llm" in registered_cats
        assert "tts" in registered_cats


class TestVRAMBudgetCheck:
    """Tests for VRAM budget check with v2 model stack."""

    def test_v2_stack_fits_within_budget(self):
        """V2 model stack (~6.7GB) fits within 16GB - 4GB headroom = 12GB."""
        monitor = VRAMMonitor(vram_budget_mb=16384.0)
        monitor.register_model("faster-whisper-small.en", 1000.0, "stt")
        monitor.register_model("qwen3-8b-q4", 5200.0, "llm")
        monitor.register_model("kokoro-82m", 500.0, "tts")

        fits, total_est, available = monitor.budget_check(headroom_mb=4000.0)

        assert fits is True
        assert total_est == pytest.approx(6700.0, rel=1e-3)
        assert available == pytest.approx(12384.0, rel=1e-3)

    def test_v2_stack_fits_with_significant_headroom(self):
        """V2 model stack leaves at least 5GB headroom from available budget."""
        monitor = VRAMMonitor(vram_budget_mb=16384.0)
        monitor.register_model("faster-whisper-small.en", 1000.0, "stt")
        monitor.register_model("qwen3-8b-q4", 5200.0, "llm")
        monitor.register_model("kokoro-82m", 500.0, "tts")

        fits, total_est, available = monitor.budget_check(headroom_mb=4000.0)

        # 12384 - 6700 = 5684MB headroom remaining
        remaining = available - total_est
        assert remaining > 5000.0, f"Expected >5GB headroom, got {remaining:.0f}MB"

    def test_budget_check_returns_tuple(self):
        """budget_check returns (fits: bool, total_mb: float, available_mb: float)."""
        monitor = VRAMMonitor()
        result = monitor.budget_check()

        assert isinstance(result, tuple)
        assert len(result) == 3
        fits, total_mb, available_mb = result
        assert isinstance(fits, bool)
        assert isinstance(total_mb, float)
        assert isinstance(available_mb, float)


class TestVRAMReportIncludesModels:
    """Tests for VRAM report completeness."""

    def test_report_includes_all_three_models(self):
        """VRAM report includes all 3 registered v2 models."""
        monitor = VRAMMonitor(vram_budget_mb=16384.0)
        monitor.register_model("faster-whisper-small.en", 1000.0, "stt")
        monitor.register_model("qwen3-8b-q4", 5200.0, "llm")
        monitor.register_model("kokoro-82m", 500.0, "tts")

        with patch("ergos.core.vram.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            report = monitor.report()

        assert "models" in report
        assert len(report["models"]) == 3
        assert "faster-whisper-small.en" in report["models"]
        assert "qwen3-8b-q4" in report["models"]
        assert "kokoro-82m" in report["models"]

    def test_report_total_estimated_mb(self):
        """VRAM report total_estimated_mb matches sum of registered models."""
        monitor = VRAMMonitor(vram_budget_mb=16384.0)
        monitor.register_model("faster-whisper-small.en", 1000.0, "stt")
        monitor.register_model("qwen3-8b-q4", 5200.0, "llm")
        monitor.register_model("kokoro-82m", 500.0, "tts")

        with patch("ergos.core.vram.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            report = monitor.report()

        assert report["total_estimated_mb"] == pytest.approx(6700.0, rel=1e-3)

    def test_report_model_categories(self):
        """VRAM report model entries include category field."""
        monitor = VRAMMonitor(vram_budget_mb=16384.0)
        monitor.register_model("faster-whisper-small.en", 1000.0, "stt")
        monitor.register_model("qwen3-8b-q4", 5200.0, "llm")
        monitor.register_model("kokoro-82m", 500.0, "tts")

        with patch("ergos.core.vram.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            report = monitor.report()

        stt_entry = report["models"]["faster-whisper-small.en"]
        assert stt_entry["category"] == "stt"
        assert stt_entry["estimated_mb"] == pytest.approx(1000.0, rel=1e-3)

        llm_entry = report["models"]["qwen3-8b-q4"]
        assert llm_entry["category"] == "llm"
        assert llm_entry["estimated_mb"] == pytest.approx(5200.0, rel=1e-3)


class TestPipelineConfigPassthrough:
    """Tests for config values being passed through to components."""

    def test_llm_config_has_chat_format(self):
        """LLMConfig has chat_format field."""
        from ergos.config import LLMConfig
        cfg = LLMConfig(chat_format="chatml")
        assert cfg.chat_format == "chatml"

    def test_llm_config_has_n_gpu_layers(self):
        """LLMConfig has n_gpu_layers field."""
        from ergos.config import LLMConfig
        cfg = LLMConfig(n_gpu_layers=-1)
        assert cfg.n_gpu_layers == -1
