"""Data channel handler for VAD events and state broadcasts."""

import asyncio
import json
import logging
from typing import Callable, Optional

from ergos.audio.vad import VADProcessor
from ergos.state import ConversationStateMachine
from ergos.state.events import StateChangeEvent

logger = logging.getLogger(__name__)


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
        logger.info("Barge-in request received via data channel")
        await self._state_machine.barge_in()

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
