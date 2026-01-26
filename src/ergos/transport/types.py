"""Transport types for WebRTC signaling and data channel messages."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ergos.state.events import StateChangeEvent


@dataclass
class DataChannelMessage:
    """Base class for data channel messages."""

    type: str
    timestamp: float = field(default_factory=time.time)
    data: Optional[dict] = None

    @classmethod
    def from_json(cls, json_str: str) -> DataChannelMessage:
        """Parse a JSON string into a DataChannelMessage."""
        parsed = json.loads(json_str)
        return cls(
            type=parsed.get("type", ""),
            timestamp=parsed.get("timestamp", time.time()),
            data=parsed.get("data"),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(
            {
                "type": self.type,
                "timestamp": self.timestamp,
                "data": self.data,
            }
        )


@dataclass
class VADMessage:
    """VAD (Voice Activity Detection) event message."""

    event: str  # "speech_start" or "speech_end"
    timestamp: float = field(default_factory=time.time)
    probability: Optional[float] = None
    duration_ms: Optional[float] = None

    @classmethod
    def speech_start(cls, probability: Optional[float] = None) -> VADMessage:
        """Create a speech_start event."""
        return cls(event="speech_start", probability=probability)

    @classmethod
    def speech_end(cls, duration_ms: Optional[float] = None) -> VADMessage:
        """Create a speech_end event."""
        return cls(event="speech_end", duration_ms=duration_ms)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = {
            "type": "vad_event",
            "event": self.event,
            "timestamp": self.timestamp,
        }
        if self.probability is not None:
            data["probability"] = self.probability
        if self.duration_ms is not None:
            data["duration_ms"] = self.duration_ms
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> VADMessage:
        """Parse a JSON string into a VADMessage."""
        parsed = json.loads(json_str)
        return cls(
            event=parsed.get("event", ""),
            timestamp=parsed.get("timestamp", time.time()),
            probability=parsed.get("probability"),
            duration_ms=parsed.get("duration_ms"),
        )


@dataclass
class StateMessage:
    """State change message for client broadcast."""

    previous: str
    state: str
    timestamp: float = field(default_factory=time.time)
    metadata: Optional[dict] = None

    @classmethod
    def from_state_event(cls, event: StateChangeEvent) -> StateMessage:
        """Create a StateMessage from a StateChangeEvent."""
        return cls(
            previous=event.previous_state.value,
            state=event.new_state.value,
            timestamp=event.timestamp,
            metadata=event.metadata,
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(
            {
                "type": "state_change",
                "previous": self.previous,
                "state": self.state,
                "timestamp": self.timestamp,
                "metadata": self.metadata or {},
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> StateMessage:
        """Parse a JSON string into a StateMessage."""
        parsed = json.loads(json_str)
        return cls(
            previous=parsed.get("previous", ""),
            state=parsed.get("state", ""),
            timestamp=parsed.get("timestamp", time.time()),
            metadata=parsed.get("metadata"),
        )


@dataclass
class SignalingRequest:
    """WebRTC signaling request (SDP offer/answer)."""

    sdp: str
    type: str  # "offer" or "answer"

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps({"sdp": self.sdp, "type": self.type})

    @classmethod
    def from_json(cls, json_str: str) -> SignalingRequest:
        """Parse a JSON string into a SignalingRequest."""
        parsed = json.loads(json_str)
        return cls(sdp=parsed.get("sdp", ""), type=parsed.get("type", ""))


@dataclass
class SignalingResponse:
    """WebRTC signaling response (SDP offer/answer)."""

    sdp: str
    type: str  # "offer" or "answer"

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps({"sdp": self.sdp, "type": self.type})

    @classmethod
    def from_json(cls, json_str: str) -> SignalingResponse:
        """Parse a JSON string into a SignalingResponse."""
        parsed = json.loads(json_str)
        return cls(sdp=parsed.get("sdp", ""), type=parsed.get("type", ""))
