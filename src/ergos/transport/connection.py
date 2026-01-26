"""Connection manager for WebRTC peer connections."""

from __future__ import annotations

import asyncio
import logging
from typing import Set

from aiortc import RTCPeerConnection

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebRTC peer connection lifecycle.

    This class handles creation, tracking, and cleanup of RTCPeerConnection
    instances and their associated data channels.

    Attributes:
        _connections: Set of active peer connections.
        _data_channels: Set of active data channels.
    """

    def __init__(self) -> None:
        """Initialize the connection manager."""
        self._connections: Set[RTCPeerConnection] = set()
        self._data_channels: Set = set()

    async def create_connection(self) -> RTCPeerConnection:
        """
        Create a new RTCPeerConnection and track it.

        The connection is registered with a state change handler that
        automatically removes it from tracking when closed or failed.

        Returns:
            A new RTCPeerConnection instance.
        """
        pc = RTCPeerConnection()
        self._connections.add(pc)

        @pc.on("connectionstatechange")
        async def on_connection_state_change() -> None:
            state = pc.connectionState
            logger.debug(f"Connection state changed to: {state}")
            if state in ("failed", "closed"):
                self._connections.discard(pc)
                logger.info(f"Connection removed from tracking (state: {state})")

        logger.info("Created new RTCPeerConnection")
        return pc

    def track_data_channel(self, channel) -> None:
        """
        Track a data channel for management.

        Registers a close handler to automatically remove the channel
        from tracking when it closes.

        Args:
            channel: The data channel to track.
        """
        self._data_channels.add(channel)

        @channel.on("close")
        def on_close() -> None:
            self._data_channels.discard(channel)
            logger.debug("Data channel removed from tracking")

        logger.debug(f"Tracking data channel: {channel.label}")

    def get_open_channels(self) -> list:
        """
        Get all currently open data channels.

        Returns:
            List of data channels with readyState == "open".
        """
        return [ch for ch in self._data_channels if ch.readyState == "open"]

    async def broadcast_message(self, message: str) -> None:
        """
        Send a message to all open data channels.

        Args:
            message: The message string to send.
        """
        open_channels = self.get_open_channels()
        for channel in open_channels:
            try:
                channel.send(message)
            except Exception as e:
                logger.warning(f"Failed to send to channel {channel.label}: {e}")

    async def close_all(self) -> None:
        """
        Close all connections and clear tracking sets.

        This should be called during application shutdown to ensure
        all WebRTC resources are properly released.
        """
        logger.info(f"Closing {len(self._connections)} connections")

        # Close all connections
        close_tasks = [pc.close() for pc in list(self._connections)]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        # Clear tracking sets
        self._connections.clear()
        self._data_channels.clear()
        logger.info("All connections closed")

    @property
    def stats(self) -> dict:
        """
        Get connection statistics.

        Returns:
            Dictionary with connection_count and channel_count.
        """
        return {
            "connection_count": len(self._connections),
            "channel_count": len(self._data_channels),
        }
