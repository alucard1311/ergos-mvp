"""WebRTC transport module for Ergos."""

from ergos.transport.audio_track import AUDIO_PTIME, TTSAudioTrack
from ergos.transport.connection import ConnectionManager
from ergos.transport.data_channel import DataChannelHandler
from ergos.transport.signaling import create_signaling_app
from ergos.transport.types import (
    DataChannelMessage,
    SignalingRequest,
    SignalingResponse,
    StateMessage,
    VADMessage,
)

__all__ = [
    # Types
    "DataChannelMessage",
    "VADMessage",
    "StateMessage",
    "SignalingRequest",
    "SignalingResponse",
    # Audio track
    "TTSAudioTrack",
    "AUDIO_PTIME",
    # Connection management
    "ConnectionManager",
    # Signaling
    "create_signaling_app",
    # Data channel
    "DataChannelHandler",
]
