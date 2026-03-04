"""Unit tests for Orpheus TTS synthesizer and engine selection."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import numpy as np
import pytest

from ergos.tts.types import SynthesisConfig, SynthesisResult
from ergos.config import TTSConfig


class TestOrpheusSynthesizer:
    """Tests for OrpheusSynthesizer (all model calls mocked)."""

    def _make_synth(self, **kwargs):
        from ergos.tts.orpheus_synthesizer import OrpheusSynthesizer
        return OrpheusSynthesizer(**kwargs)

    def test_init_defaults(self):
        """OrpheusSynthesizer initializes with default params without loading model."""
        synth = self._make_synth()
        assert synth._n_gpu_layers == -1
        assert synth._lang == "en"
        assert synth._verbose is False
        assert not synth.model_loaded

    def test_init_custom_params(self):
        """OrpheusSynthesizer accepts custom construction params."""
        synth = self._make_synth(n_gpu_layers=0, lang="es", verbose=True)
        assert synth._n_gpu_layers == 0
        assert synth._lang == "es"
        assert synth._verbose is True

    def test_model_loaded_false_before_ensure(self):
        """model_loaded returns False before _ensure_model is called."""
        synth = self._make_synth()
        assert synth.model_loaded is False

    def test_model_loaded_true_after_set(self):
        """model_loaded returns True after _orpheus is set."""
        synth = self._make_synth()
        synth._orpheus = MagicMock()
        assert synth.model_loaded is True

    def test_sample_rate_property(self):
        """sample_rate property returns 24000."""
        synth = self._make_synth()
        assert synth.sample_rate == 24000

    def test_synthesize_returns_result(self):
        """synthesize() returns SynthesisResult with correct fields."""
        synth = self._make_synth()

        # Mock _ensure_model and _orpheus.tts
        fake_audio_int16 = (np.random.randn(24000) * 32768).astype(np.int16)
        mock_orpheus = MagicMock()
        mock_orpheus.tts.return_value = (24000, fake_audio_int16)

        synth._ensure_model = MagicMock()
        synth._orpheus = mock_orpheus

        result = synth.synthesize("Hello world")

        assert isinstance(result, SynthesisResult)
        assert result.text == "Hello world"
        assert result.sample_rate == 24000
        assert isinstance(result.audio_samples, np.ndarray)
        assert result.audio_samples.dtype == np.float32
        assert result.duration_ms == pytest.approx(1000.0, rel=0.01)

    def test_synthesize_converts_int16_to_float32(self):
        """synthesize() converts int16 audio to float32 normalized to [-1, 1]."""
        synth = self._make_synth()

        # Use known int16 values
        int16_audio = np.array([0, 16384, -16384, 32767], dtype=np.int16)
        mock_orpheus = MagicMock()
        mock_orpheus.tts.return_value = (24000, int16_audio)

        synth._ensure_model = MagicMock()
        synth._orpheus = mock_orpheus

        result = synth.synthesize("test")

        assert result.audio_samples.dtype == np.float32
        np.testing.assert_allclose(result.audio_samples[0], 0.0, atol=1e-6)
        assert result.audio_samples[1] == pytest.approx(16384 / 32768.0, rel=1e-4)
        assert result.audio_samples[2] == pytest.approx(-16384 / 32768.0, rel=1e-4)

    def test_synthesize_passes_config_options(self):
        """synthesize() passes voice_id, temperature, top_k from config."""
        synth = self._make_synth()
        config = SynthesisConfig(orpheus_voice="leo", temperature=0.7, top_k=30)

        mock_orpheus = MagicMock()
        mock_orpheus.tts.return_value = (24000, np.zeros(100, dtype=np.int16))

        synth._ensure_model = MagicMock()
        synth._orpheus = mock_orpheus

        synth.synthesize("hello", config=config)

        call_kwargs = mock_orpheus.tts.call_args
        options_arg = call_kwargs[0][1] if call_kwargs[0] else call_kwargs[1].get("options")
        assert options_arg["voice_id"] == "leo"
        assert options_arg["temperature"] == 0.7
        assert options_arg["top_k"] == 30

    def test_synthesize_stream_yields_tuples(self):
        """synthesize_stream() yields (audio_samples, sample_rate) tuples."""
        synth = self._make_synth()

        chunk1 = np.zeros((1, 1000), dtype=np.int16)
        chunk2 = np.zeros((1, 500), dtype=np.int16)

        async def fake_stream_tts(text, options=None):
            yield (24000, chunk1)
            yield (24000, chunk2)

        mock_orpheus = MagicMock()
        mock_orpheus.stream_tts = fake_stream_tts

        synth._ensure_model = MagicMock()
        synth._orpheus = mock_orpheus

        async def run():
            chunks = []
            async for audio, sr in synth.synthesize_stream("Hello"):
                chunks.append((audio, sr))
            return chunks

        chunks = asyncio.run(run())
        assert len(chunks) == 2
        assert chunks[0][1] == 24000
        assert chunks[0][0].dtype == np.float32
        assert chunks[0][0].ndim == 1
        assert len(chunks[0][0]) == 1000

    def test_synthesize_stream_default_config(self):
        """synthesize_stream() works without explicit config (uses defaults)."""
        synth = self._make_synth()

        async def fake_stream_tts(text, options=None):
            yield (24000, np.zeros((1, 100), dtype=np.int16))

        mock_orpheus = MagicMock()
        mock_orpheus.stream_tts = fake_stream_tts

        synth._ensure_model = MagicMock()
        synth._orpheus = mock_orpheus

        async def run():
            chunks = []
            async for audio, sr in synth.synthesize_stream("Hello"):
                chunks.append((audio, sr))
            return chunks

        chunks = asyncio.run(run())
        assert len(chunks) == 1
        assert chunks[0][1] == 24000

    def test_close_resets_model(self):
        """close() sets _orpheus to None."""
        synth = self._make_synth()
        synth._orpheus = MagicMock()
        assert synth.model_loaded is True

        synth.close()

        assert synth._orpheus is None
        assert synth.model_loaded is False


class TestSynthesisConfigOrpheusFields:
    """Tests for orpheus_voice field on SynthesisConfig."""

    def test_orpheus_voice_default(self):
        """orpheus_voice defaults to 'tara'."""
        cfg = SynthesisConfig()
        assert cfg.orpheus_voice == "tara"

    def test_orpheus_voice_explicit(self):
        """orpheus_voice can be set explicitly."""
        cfg = SynthesisConfig(orpheus_voice="leo")
        assert cfg.orpheus_voice == "leo"

    def test_orpheus_voice_all_valid_voices(self):
        """All Orpheus voice IDs are accepted."""
        valid_voices = ["tara", "leah", "jess", "leo", "dan", "mia", "zac", "zoe"]
        for voice in valid_voices:
            cfg = SynthesisConfig(orpheus_voice=voice)
            assert cfg.orpheus_voice == voice

    def test_existing_fields_unchanged(self):
        """Existing SynthesisConfig fields retain their defaults."""
        cfg = SynthesisConfig()
        assert cfg.voice == "af_sarah"
        assert cfg.speed == 1.0
        assert cfg.lang == "en-us"
        assert cfg.speaker_id == 0
        assert cfg.temperature == 0.9
        assert cfg.top_k == 50


class TestTTSConfigOrpheusEngine:
    """Tests for Orpheus-related fields on TTSConfig."""

    def test_engine_default_still_kokoro(self):
        """Default engine is still 'kokoro', not changed by adding orpheus support."""
        cfg = TTSConfig()
        assert cfg.engine == "kokoro"

    def test_engine_orpheus_accepted(self):
        """engine='orpheus' is accepted."""
        cfg = TTSConfig(engine="orpheus")
        assert cfg.engine == "orpheus"

    def test_orpheus_voice_default_tara(self):
        """orpheus_voice defaults to 'tara'."""
        cfg = TTSConfig()
        assert cfg.orpheus_voice == "tara"

    def test_orpheus_voice_explicit(self):
        """orpheus_voice can be set explicitly."""
        cfg = TTSConfig(orpheus_voice="dan")
        assert cfg.orpheus_voice == "dan"

    def test_orpheus_n_gpu_layers_default_minus1(self):
        """orpheus_n_gpu_layers defaults to -1 (all GPU)."""
        cfg = TTSConfig()
        assert cfg.orpheus_n_gpu_layers == -1

    def test_orpheus_n_gpu_layers_explicit(self):
        """orpheus_n_gpu_layers can be overridden."""
        cfg = TTSConfig(orpheus_n_gpu_layers=0)
        assert cfg.orpheus_n_gpu_layers == 0

    def test_existing_tts_fields_unchanged(self):
        """Existing TTSConfig fields remain unchanged."""
        cfg = TTSConfig()
        assert cfg.voice == "af_heart"
        assert cfg.speed == 1.0
        assert cfg.device == "auto"
        assert cfg.model_id == "sesame/csm-1b"


class TestConfigYamlOrpheus:
    """Tests for config.yaml with Orpheus fields."""

    def test_config_yaml_engine_default_kokoro(self):
        """config.yaml engine defaults to 'kokoro'."""
        from ergos.config import load_config
        config = load_config("/home/vinay/ergos/config.yaml")
        assert config.tts.engine == "kokoro"

    def test_config_yaml_orpheus_voice_present(self):
        """config.yaml has orpheus_voice field."""
        from ergos.config import load_config
        config = load_config("/home/vinay/ergos/config.yaml")
        assert config.tts.orpheus_voice == "tara"

    def test_config_yaml_orpheus_n_gpu_layers_present(self):
        """config.yaml has orpheus_n_gpu_layers field."""
        from ergos.config import load_config
        config = load_config("/home/vinay/ergos/config.yaml")
        assert config.tts.orpheus_n_gpu_layers == -1

    def test_v1_config_without_orpheus_fields_loads_ok(self):
        """A v1 config dict without orpheus fields loads without error."""
        from ergos.config import Config
        v1_data = {
            "tts": {
                "voice": "af_heart",
                "speed": 1.0,
                "device": "auto",
            }
        }
        config = Config(**v1_data)
        assert config.tts.engine == "kokoro"
        assert config.tts.orpheus_voice == "tara"
        assert config.tts.orpheus_n_gpu_layers == -1

    def test_orpheus_optional_dep_in_pyproject(self):
        """orpheus-cpp is listed as an optional dependency under [orpheus] extra."""
        with open("/home/vinay/ergos/pyproject.toml") as f:
            content = f.read()
        assert "orpheus" in content
        assert "orpheus-cpp" in content


class TestPipelineOrpheusWiring:
    """Tests for Orpheus engine wiring in create_pipeline()."""

    def _make_orpheus_config(self):
        from ergos.config import Config, TTSConfig, STTConfig, LLMConfig
        return Config(
            tts=TTSConfig(engine="orpheus", orpheus_voice="tara", orpheus_n_gpu_layers=-1),
            stt=STTConfig(),
            llm=LLMConfig(model_path=""),
        )

    @patch("ergos.pipeline.VRAMMonitor")
    @patch("ergos.pipeline.ConversationStateMachine")
    @patch("ergos.pipeline.VADProcessor")
    @patch("ergos.pipeline.WhisperTranscriber")
    @patch("ergos.pipeline.STTProcessor")
    @patch("ergos.pipeline.LLMGenerator")
    @patch("ergos.pipeline.LLMProcessor")
    @patch("ergos.pipeline.TTSProcessor")
    @patch("ergos.pipeline.ConnectionManager")
    @patch("ergos.pipeline.DataChannelHandler")
    @patch("ergos.pipeline.LatencyTracker")
    @patch("ergos.pipeline.PluginManager")
    @patch("ergos.pipeline.create_signaling_app")
    def test_orpheus_engine_creates_orpheus_synthesizer(
        self,
        mock_signaling, mock_plugin_mgr, mock_lat, mock_dc,
        mock_conn, mock_tts_proc, mock_llm_proc, mock_llm_gen,
        mock_stt_proc, mock_whisper, mock_vad, mock_sm, mock_vram,
    ):
        """When engine='orpheus', pipeline creates OrpheusSynthesizer."""
        from ergos.tts.orpheus_synthesizer import OrpheusSynthesizer

        config = self._make_orpheus_config()

        with patch("ergos.tts.orpheus_synthesizer.OrpheusSynthesizer") as mock_orpheus_cls:
            mock_orpheus_instance = MagicMock()
            mock_orpheus_cls.return_value = mock_orpheus_instance

            mock_plugin_instance = MagicMock()
            mock_plugin_instance.plugins = []
            mock_plugin_mgr.return_value = mock_plugin_instance

            mock_sm_instance = MagicMock()
            mock_sm.return_value = mock_sm_instance

            mock_vram_instance = MagicMock()
            mock_vram.return_value = mock_vram_instance

            import asyncio
            asyncio.run(self._run_pipeline(config))

            mock_orpheus_cls.assert_called_once_with(
                n_gpu_layers=-1,
                lang="en",
                verbose=False,
            )

    @patch("ergos.pipeline.VRAMMonitor")
    @patch("ergos.pipeline.ConversationStateMachine")
    @patch("ergos.pipeline.VADProcessor")
    @patch("ergos.pipeline.WhisperTranscriber")
    @patch("ergos.pipeline.STTProcessor")
    @patch("ergos.pipeline.LLMGenerator")
    @patch("ergos.pipeline.LLMProcessor")
    @patch("ergos.pipeline.TTSProcessor")
    @patch("ergos.pipeline.ConnectionManager")
    @patch("ergos.pipeline.DataChannelHandler")
    @patch("ergos.pipeline.LatencyTracker")
    @patch("ergos.pipeline.PluginManager")
    @patch("ergos.pipeline.create_signaling_app")
    def test_orpheus_registers_vram_2000mb(
        self,
        mock_signaling, mock_plugin_mgr, mock_lat, mock_dc,
        mock_conn, mock_tts_proc, mock_llm_proc, mock_llm_gen,
        mock_stt_proc, mock_whisper, mock_vad, mock_sm, mock_vram,
    ):
        """When engine='orpheus', VRAM registers orpheus-3b-q4 at 2000MB."""
        config = self._make_orpheus_config()

        with patch("ergos.tts.orpheus_synthesizer.OrpheusSynthesizer"):
            mock_plugin_instance = MagicMock()
            mock_plugin_instance.plugins = []
            mock_plugin_mgr.return_value = mock_plugin_instance

            mock_sm_instance = MagicMock()
            mock_sm.return_value = mock_sm_instance

            mock_vram_instance = MagicMock()
            mock_vram.return_value = mock_vram_instance

            import asyncio
            asyncio.run(self._run_pipeline(config))

            # Verify orpheus-3b-q4 registered at 2000MB
            calls = mock_vram_instance.register_model.call_args_list
            orpheus_calls = [c for c in calls if "orpheus" in str(c)]
            assert len(orpheus_calls) == 1
            assert orpheus_calls[0][0][1] == 2000.0

    @patch("ergos.pipeline.VRAMMonitor")
    @patch("ergos.pipeline.ConversationStateMachine")
    @patch("ergos.pipeline.VADProcessor")
    @patch("ergos.pipeline.WhisperTranscriber")
    @patch("ergos.pipeline.STTProcessor")
    @patch("ergos.pipeline.LLMGenerator")
    @patch("ergos.pipeline.LLMProcessor")
    @patch("ergos.pipeline.TTSProcessor")
    @patch("ergos.pipeline.ConnectionManager")
    @patch("ergos.pipeline.DataChannelHandler")
    @patch("ergos.pipeline.LatencyTracker")
    @patch("ergos.pipeline.PluginManager")
    @patch("ergos.pipeline.create_signaling_app")
    def test_kokoro_not_registered_when_orpheus(
        self,
        mock_signaling, mock_plugin_mgr, mock_lat, mock_dc,
        mock_conn, mock_tts_proc, mock_llm_proc, mock_llm_gen,
        mock_stt_proc, mock_whisper, mock_vad, mock_sm, mock_vram,
    ):
        """When engine='orpheus', kokoro-82m is NOT registered in VRAM."""
        config = self._make_orpheus_config()

        with patch("ergos.tts.orpheus_synthesizer.OrpheusSynthesizer"):
            mock_plugin_instance = MagicMock()
            mock_plugin_instance.plugins = []
            mock_plugin_mgr.return_value = mock_plugin_instance

            mock_sm_instance = MagicMock()
            mock_sm.return_value = mock_sm_instance

            mock_vram_instance = MagicMock()
            mock_vram.return_value = mock_vram_instance

            import asyncio
            asyncio.run(self._run_pipeline(config))

            calls = mock_vram_instance.register_model.call_args_list
            kokoro_calls = [c for c in calls if "kokoro" in str(c)]
            assert len(kokoro_calls) == 0

    async def _run_pipeline(self, config):
        """Helper to run create_pipeline with heavy deps mocked."""
        from ergos.pipeline import create_pipeline
        with patch("ergos.pipeline.load_persona"), \
             patch("ergos.pipeline.DEFAULT_PERSONA"):
            pipeline = await create_pipeline(config)
        return pipeline
