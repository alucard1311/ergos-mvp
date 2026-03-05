"""Data channel handler for VAD events and state broadcasts."""

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

from ergos.audio.vad import VADProcessor
from ergos.state import ConversationStateMachine
from ergos.state.events import StateChangeEvent

logger = logging.getLogger(__name__)

# Type alias for text input callback
TextInputCallback = Callable[[str], Awaitable[None]]


class DataChannelHandler:
    """
    Handles data channel messages for VAD events and state broadcasts.

    Bridges data channel messages with pipeline components (VAD processor,
    state machine). Routes incoming messages to appropriate handlers and
    broadcasts state changes to all connected clients.
    """

    def __init__(
        self,
        vad_processor: VADProcessor,
        state_machine: ConversationStateMachine,
    ):
        """
        Initialize the data channel handler.

        Args:
            vad_processor: VAD processor for handling VAD events
            state_machine: State machine for barge-in handling
        """
        self._vad_processor = vad_processor
        self._state_machine = state_machine
        self._channels: set = set()
        self._text_input_callback: Optional[TextInputCallback] = None

    def register_channel(self, channel) -> None:
        """
        Register a data channel for message handling.

        Args:
            channel: The RTCDataChannel to register
        """
        self._channels.add(channel)
        logger.info(f"Data channel registered (total: {len(self._channels)})")

        @channel.on("message")
        async def on_message(message: str) -> None:
            await self.handle_message(message)

        @channel.on("close")
        def on_close() -> None:
            self._channels.discard(channel)
            logger.info(f"Data channel closed (remaining: {len(self._channels)})")

    def set_text_input_callback(self, callback: TextInputCallback) -> None:
        """
        Set the callback for handling text input messages.

        Args:
            callback: Async function to process text input (e.g., plugin router)
        """
        self._text_input_callback = callback

    async def handle_message(self, message: str) -> None:
        """
        Handle an incoming data channel message.

        Args:
            message: JSON string message from data channel
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON message: {e}")
            return

        msg_type = data.get("type")

        if msg_type == "vad_event":
            await self._handle_vad_event(data)
        elif msg_type == "barge_in":
            await self._handle_barge_in(data)
        elif msg_type == "text_input":
            await self._handle_text_input(data)
        elif msg_type == "mode_change":
            # Mode change is informational, logged but not processed
            mode = data.get("mode", "unknown")
            logger.info(f"Client mode changed to: {mode}")
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_vad_event(self, data: dict) -> None:
        """
        Handle a VAD event message.

        Args:
            data: Parsed message data containing VAD event
        """
        event_type = data.get("event")
        if not event_type:
            logger.warning("VAD event missing 'event' field")
            return

        await self._vad_processor.process_raw_event(event_type, data)

    async def _handle_barge_in(self, data: dict) -> None:
        """
        Handle a barge-in message.

        Args:
            data: Parsed message data for barge-in
        """
        logger.info("Barge-in request received, interrupting")
        await self._state_machine.barge_in()

    async def _handle_text_input(self, data: dict) -> None:
        """
        Handle a text input message (e.g., mode activation command).

        Args:
            data: Parsed message data containing text input
        """
        text = data.get("text", "")
        if not text:
            logger.warning("Text input message missing 'text' field")
            return

        logger.info(f"Text input received: {text}")

        if self._text_input_callback is not None:
            try:
                await self._text_input_callback(text)
            except Exception as e:
                logger.error(f"Text input callback error: {e}")
        else:
            logger.warning("No text input callback registered, ignoring message")

    async def broadcast_state_change(self, event: StateChangeEvent) -> None:
        """
        Broadcast a state change to all connected data channels.

        Args:
            event: The state change event to broadcast
        """
        message = json.dumps(event.to_dict())

        for channel in list(self._channels):
            try:
                if channel.readyState == "open":
                    channel.send(message)
            except Exception as e:
                logger.error(f"Failed to broadcast to channel: {e}")

    async def broadcast_transcription(self, text: str) -> None:
        """Broadcast transcription text to all connected data channels."""
        message = json.dumps({"type": "transcription", "text": text})
        for channel in list(self._channels):
            try:
                if channel.readyState == "open":
                    channel.send(message)
            except Exception as e:
                logger.error(f"Failed to broadcast transcription: {e}")

    async def broadcast_model_status(self, model: str) -> None:
        """Broadcast which LLM model is active to all connected data channels.

        Args:
            model: Either "cloud" or "local".
        """
        message = json.dumps({"type": "model_status", "model": model})
        for channel in list(self._channels):
            try:
                if channel.readyState == "open":
                    channel.send(message)
            except Exception as e:
                logger.error(f"Failed to broadcast model status: {e}")

    async def broadcast_warmup_status(self, status: str) -> None:
        """Broadcast LLM warm-up status to all connected data channels.

        Args:
            status: One of "started", "ready", or "failed".
        """
        message = json.dumps({"type": "warmup_status", "status": status})
        for channel in list(self._channels):
            try:
                if channel.readyState == "open":
                    channel.send(message)
            except Exception as e:
                logger.error(f"Failed to broadcast warmup status: {e}")

    async def broadcast_recording_status(self, recording: bool) -> None:
        """Broadcast meeting recording status to all connected data channels."""
        message = json.dumps({"type": "recording_status", "recording": recording})
        for channel in list(self._channels):
            try:
                if channel.readyState == "open":
                    channel.send(message)
            except Exception as e:
                logger.error(f"Failed to broadcast recording status: {e}")

    def get_state_callback(self) -> Callable[[StateChangeEvent], None]:
        """
        Get a callback for state machine registration.

        Returns:
            Async callback function that broadcasts state changes
        """

        async def callback(event: StateChangeEvent) -> None:
            await self.broadcast_state_change(event)

        return callback

    @property
    def stats(self) -> dict:
        """Get handler statistics."""
        open_channels = sum(
            1 for ch in self._channels if ch.readyState == "open"
        )
        return {
            "channel_count": len(self._channels),
            "open_channel_count": open_channels,
        }
