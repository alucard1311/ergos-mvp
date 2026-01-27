"""Integration tests for Ergos voice assistant pipeline.

These tests verify that components wire together correctly.
Full end-to-end testing requires actual WebRTC which is tested manually.
"""

import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from ergos.config import Config, load_config
from ergos.server import Server, ServerState
from ergos.pipeline import Pipeline, create_pipeline
from ergos.transport.connection import ConnectionManager
from ergos.transport.data_channel import DataChannelHandler
from ergos.transport.signaling import create_signaling_app
from ergos.audio.vad import VADProcessor
from ergos.state import ConversationStateMachine


class TestServerInstantiation:
    """Test that Server can be instantiated with config."""

    def test_server_instantiation_with_default_config(self):
        """Server instantiates with default configuration."""
        config = Config()
        server = Server(config)

        assert server.config == config
        assert server.state == ServerState.STOPPED

    def test_server_instantiation_with_loaded_config(self, tmp_path):
        """Server instantiates with loaded configuration file."""
        # Create a temporary config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
server:
  host: "127.0.0.1"
  port: 9000
stt:
  model: "small"
  device: "cpu"
""")

        config = load_config(config_file)
        server = Server(config)

        assert server.config.server.host == "127.0.0.1"
        assert server.config.server.port == 9000
        assert server.config.stt.model == "small"


class TestPipelineImports:
    """Test that pipeline components can be imported."""

    def test_pipeline_import(self):
        """Pipeline can be imported from ergos."""
        from ergos import Pipeline
        assert Pipeline is not None

    def test_create_pipeline_import(self):
        """create_pipeline can be imported from ergos."""
        from ergos import create_pipeline
        assert create_pipeline is not None

    def test_all_pipeline_components_importable(self):
        """All pipeline component modules are importable."""
        from ergos.stt.transcriber import WhisperTranscriber
        from ergos.stt.processor import STTProcessor
        from ergos.llm.generator import LLMGenerator
        from ergos.llm.processor import LLMProcessor
        from ergos.tts.synthesizer import TTSSynthesizer
        from ergos.tts.processor import TTSProcessor
        from ergos.transport.audio_track import TTSAudioTrack
        from ergos.transport.connection import ConnectionManager
        from ergos.transport.signaling import create_signaling_app
        from ergos.metrics import LatencyTracker

        assert WhisperTranscriber is not None
        assert STTProcessor is not None
        assert LLMGenerator is not None
        assert LLMProcessor is not None
        assert TTSSynthesizer is not None
        assert TTSProcessor is not None
        assert TTSAudioTrack is not None
        assert ConnectionManager is not None
        assert create_signaling_app is not None
        assert LatencyTracker is not None


class TestSignalingEndpoint(AioHTTPTestCase):
    """Test the signaling endpoint with mock SDP."""

    async def get_application(self):
        """Create test application with signaling routes."""
        manager = ConnectionManager()
        vad_processor = VADProcessor()
        state_machine = ConversationStateMachine()
        data_handler = DataChannelHandler(
            vad_processor=vad_processor,
            state_machine=state_machine,
        )

        app = create_signaling_app(
            manager=manager,
            data_handler=data_handler,
        )
        return app

    async def test_offer_endpoint_exists(self):
        """POST /offer endpoint exists and responds."""
        # Send a minimal SDP offer
        mock_sdp = """v=0
o=- 0 0 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0
m=audio 9 UDP/TLS/RTP/SAVPF 111
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:test
a=ice-pwd:testpassword1234567890
a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00
a=setup:actpass
a=mid:0
a=sendrecv
a=rtpmap:111 opus/48000/2
"""

        response = await self.client.post(
            "/offer",
            json={"sdp": mock_sdp, "type": "offer"},
        )

        # Should get a response (may be error due to aiortc internals,
        # but endpoint is reachable)
        assert response.status in (200, 500)

    async def test_offer_endpoint_rejects_invalid_json(self):
        """POST /offer rejects invalid JSON."""
        response = await self.client.post(
            "/offer",
            data="not json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status == 400
        data = await response.json()
        assert "error" in data

    async def test_offer_endpoint_requires_sdp(self):
        """POST /offer requires sdp field."""
        response = await self.client.post(
            "/offer",
            json={"type": "offer"},
        )

        assert response.status == 400
        data = await response.json()
        assert "sdp" in data["error"].lower()

    async def test_offer_endpoint_requires_offer_type(self):
        """POST /offer requires type to be 'offer'."""
        response = await self.client.post(
            "/offer",
            json={"sdp": "test", "type": "answer"},
        )

        assert response.status == 400
        data = await response.json()
        assert "offer" in data["error"].lower()


class TestPipelineWiring:
    """Test that pipeline components wire together correctly."""

    @pytest.mark.asyncio
    async def test_create_pipeline_returns_pipeline(self):
        """create_pipeline returns a Pipeline instance."""
        config = Config()
        pipeline = await create_pipeline(config)

        assert isinstance(pipeline, Pipeline)
        assert pipeline.config == config

    @pytest.mark.asyncio
    async def test_pipeline_has_all_components(self):
        """Pipeline contains all required components."""
        config = Config()
        pipeline = await create_pipeline(config)

        assert pipeline.state_machine is not None
        assert pipeline.vad_processor is not None
        assert pipeline.stt_processor is not None
        assert pipeline.llm_processor is not None
        assert pipeline.tts_processor is not None
        assert pipeline.connection_manager is not None
        assert pipeline.data_handler is not None
        assert pipeline.latency_tracker is not None
        assert pipeline.app is not None

    @pytest.mark.asyncio
    async def test_pipeline_state_machine_has_callbacks(self):
        """State machine has registered callbacks."""
        config = Config()
        pipeline = await create_pipeline(config)

        # State machine should have at least one callback (data channel broadcast)
        assert len(pipeline.state_machine._callbacks) >= 1

    @pytest.mark.asyncio
    async def test_pipeline_vad_has_callbacks(self):
        """VAD processor has registered callbacks."""
        config = Config()
        pipeline = await create_pipeline(config)

        # VAD should have callbacks (STT processor, latency tracker)
        assert len(pipeline.vad_processor._callbacks) >= 2

    @pytest.mark.asyncio
    async def test_pipeline_stt_has_transcription_callback(self):
        """STT processor has transcription callback registered."""
        config = Config()
        pipeline = await create_pipeline(config)

        # STT should have at least one transcription callback (LLM processor)
        assert len(pipeline.stt_processor._transcription_callbacks) >= 1

    @pytest.mark.asyncio
    async def test_pipeline_llm_has_token_callback(self):
        """LLM processor has token callback registered."""
        config = Config()
        pipeline = await create_pipeline(config)

        # LLM should have at least one token callback (TTS processor)
        assert len(pipeline.llm_processor._token_callbacks) >= 1

    @pytest.mark.asyncio
    async def test_pipeline_tts_has_audio_callback(self):
        """TTS processor has audio callback registered."""
        config = Config()
        pipeline = await create_pipeline(config)

        # TTS should have at least one audio callback (WebRTC tracks)
        assert len(pipeline.tts_processor._audio_callbacks) >= 1

    @pytest.mark.asyncio
    async def test_pipeline_signaling_app_has_offer_route(self):
        """Signaling app has /offer route."""
        config = Config()
        pipeline = await create_pipeline(config)

        # Check that /offer route exists
        routes = [r.resource.canonical for r in pipeline.app.router.routes()]
        assert "/offer" in routes
