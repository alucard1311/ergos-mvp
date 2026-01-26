"""Server lifecycle management for Ergos."""

import asyncio
import logging
import os
import signal
from enum import Enum
from pathlib import Path
from typing import Optional

from ergos.config import Config

logger = logging.getLogger(__name__)

# PID file for tracking running server
PID_FILE = Path.home() / ".ergos" / "server.pid"


class ServerState(Enum):
    """Server state enumeration."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


class Server:
    """Ergos server lifecycle management."""

    def __init__(self, config: Config):
        self.config = config
        self.state = ServerState.STOPPED
        self._shutdown_event: Optional[asyncio.Event] = None

    async def start(self) -> None:
        """Start the server."""
        if self.state != ServerState.STOPPED:
            raise RuntimeError(f"Cannot start server in state: {self.state}")

        self.state = ServerState.STARTING
        logger.info("Starting Ergos server...")

        # Ensure PID directory exists
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Write PID file
        PID_FILE.write_text(str(os.getpid()))

        self._shutdown_event = asyncio.Event()

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        self.state = ServerState.RUNNING
        logger.info(
            f"Ergos server running on {self.config.server.host}:{self.config.server.port}"
        )

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        await self.stop()

    async def stop(self) -> None:
        """Stop the server gracefully."""
        if self.state == ServerState.STOPPED:
            return

        self.state = ServerState.STOPPING
        logger.info("Stopping Ergos server...")

        # Cleanup PID file
        if PID_FILE.exists():
            PID_FILE.unlink()

        self.state = ServerState.STOPPED
        logger.info("Ergos server stopped")

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        if self._shutdown_event:
            self._shutdown_event.set()

    @staticmethod
    def get_status() -> dict:
        """Get current server status."""
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            # Check if process is actually running
            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                return {
                    "state": ServerState.RUNNING.value,
                    "pid": pid,
                }
            except OSError:
                # PID file exists but process is dead
                PID_FILE.unlink()

        return {"state": ServerState.STOPPED.value, "pid": None}

    @staticmethod
    def send_stop_signal() -> bool:
        """Send stop signal to running server."""
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            try:
                os.kill(pid, signal.SIGTERM)
                return True
            except OSError:
                # Process already dead
                PID_FILE.unlink()
        return False
