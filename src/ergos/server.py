"""Server lifecycle management for Ergos."""

import asyncio
import logging
import os
import signal
from enum import Enum
from pathlib import Path
from typing import Optional

from aiohttp import web

from ergos.config import Config
from ergos.pipeline import Pipeline, create_pipeline

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
        self._pipeline: Optional[Pipeline] = None
        self._runner: Optional[web.AppRunner] = None

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

        # Create and start the pipeline
        self._pipeline = await create_pipeline(self.config)

        # Pre-load all AI models to eliminate first-request latency
        await self._pipeline.preload_models()

        # Log VRAM report with per-model breakdown
        vram_report = self._pipeline.vram_monitor.report()
        logger.info("VRAM model estimates:")
        for name, profile in vram_report["models"].items():
            logger.info(
                f"  [{profile['category'].upper()}] {name}: ~{profile['estimated_mb']:.0f}MB"
            )
        logger.info(f"  Total estimated: ~{vram_report['total_estimated_mb']:.0f}MB")

        # Create aiohttp runner and site
        self._runner = web.AppRunner(self._pipeline.app)
        await self._runner.setup()
        site = web.TCPSite(
            self._runner,
            self.config.server.host,
            self.config.server.port,
        )
        await site.start()

        self.state = ServerState.RUNNING

        # Log startup information
        logger.info(
            f"Ergos server running on {self.config.server.host}:{self.config.server.port}"
        )
        logger.info("Pipeline initialized")
        logger.info(f"  STT: faster-whisper ({self.config.stt.model})")
        if self.config.llm.model_path:
            logger.info(f"  LLM: llama.cpp ({self.config.llm.model_path})")
        else:
            logger.info("  LLM: not configured")
        logger.info("  TTS: Kokoro ONNX")

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        await self.stop()

    async def stop(self) -> None:
        """Stop the server gracefully."""
        if self.state == ServerState.STOPPED:
            return

        self.state = ServerState.STOPPING
        logger.info("Stopping Ergos server...")

        # Cleanup aiohttp runner
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

        # Cleanup pipeline connections
        if self._pipeline is not None:
            await self._pipeline.connection_manager.close_all()
            self._pipeline = None

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
