import asyncio
import logging
from typing import Optional, AsyncIterator
from dataclasses import dataclass, field

from ergos.audio.types import AudioFrame, AudioChunk, CHUNK_SIZE, SAMPLE_WIDTH, CHANNELS

logger = logging.getLogger(__name__)


@dataclass
class AudioBuffer:
    """Thread-safe async buffer for audio frames."""
    max_size: int = 100  # Maximum frames to buffer
    _queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    _closed: bool = field(default=False, init=False)
    _sequence: int = field(default=0, init=False)

    def __post_init__(self):
        # Recreate queue with correct maxsize if different from default
        if self.max_size != 100:
            self._queue = asyncio.Queue(maxsize=self.max_size)

    async def put(self, frame: AudioFrame, timeout: Optional[float] = None) -> bool:
        """
        Add a frame to the buffer.

        Returns True if successful, False if buffer is closed or timeout.
        """
        if self._closed:
            return False

        chunk = AudioChunk(frame=frame, sequence=self._sequence)
        self._sequence += 1

        try:
            if timeout is not None:
                await asyncio.wait_for(self._queue.put(chunk), timeout=timeout)
            else:
                await self._queue.put(chunk)
            return True
        except asyncio.TimeoutError:
            logger.warning("Buffer put timeout - buffer may be full")
            return False
        except asyncio.QueueFull:
            logger.warning("Buffer full, dropping frame")
            return False

    async def get(self, timeout: Optional[float] = None) -> Optional[AudioChunk]:
        """
        Get a frame from the buffer.

        Returns None if buffer is closed and empty, or timeout.
        """
        try:
            if timeout is not None:
                return await asyncio.wait_for(self._queue.get(), timeout=timeout)
            else:
                return await self._queue.get()
        except asyncio.TimeoutError:
            return None

    def put_nowait(self, frame: AudioFrame) -> bool:
        """Non-blocking put. Returns False if full or closed."""
        if self._closed:
            return False

        chunk = AudioChunk(frame=frame, sequence=self._sequence)
        self._sequence += 1

        try:
            self._queue.put_nowait(chunk)
            return True
        except asyncio.QueueFull:
            logger.warning("Buffer full, dropping frame")
            return False

    def get_nowait(self) -> Optional[AudioChunk]:
        """Non-blocking get. Returns None if empty."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def drain(self) -> list[AudioChunk]:
        """Drain all frames from buffer."""
        frames = []
        while not self._queue.empty():
            try:
                frames.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return frames

    def close(self) -> None:
        """Close the buffer. No more puts allowed."""
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def is_empty(self) -> bool:
        return self._queue.empty()

    @property
    def is_full(self) -> bool:
        return self._queue.full()


class AudioInputStream:
    """Input stream for receiving audio from a source (e.g., WebRTC)."""

    def __init__(self, buffer_size: int = 100):
        self.buffer = AudioBuffer(max_size=buffer_size)
        self._total_frames = 0
        self._total_bytes = 0

    async def write(self, data: bytes) -> bool:
        """Write raw audio bytes to the stream."""
        frame = AudioFrame(data=data)
        success = await self.buffer.put(frame)
        if success:
            self._total_frames += 1
            self._total_bytes += len(data)
        return success

    async def read(self, timeout: Optional[float] = None) -> Optional[AudioChunk]:
        """Read next audio chunk from stream."""
        return await self.buffer.get(timeout=timeout)

    async def __aiter__(self) -> AsyncIterator[AudioChunk]:
        """Async iterator over audio chunks."""
        while not self.buffer.is_closed or not self.buffer.is_empty:
            chunk = await self.buffer.get(timeout=0.1)
            if chunk is not None:
                yield chunk
            elif self.buffer.is_closed:
                break

    def close(self) -> None:
        self.buffer.close()

    @property
    def stats(self) -> dict:
        return {
            "total_frames": self._total_frames,
            "total_bytes": self._total_bytes,
            "buffered_frames": self.buffer.size,
        }


class AudioOutputStream:
    """Output stream for sending audio to a sink (e.g., WebRTC)."""

    def __init__(self, buffer_size: int = 100):
        self.buffer = AudioBuffer(max_size=buffer_size)
        self._total_frames = 0
        self._total_bytes = 0

    async def write(self, frame: AudioFrame) -> bool:
        """Write an audio frame to the output buffer."""
        success = await self.buffer.put(frame)
        if success:
            self._total_frames += 1
            self._total_bytes += len(frame.data)
        return success

    async def read(self, timeout: Optional[float] = None) -> Optional[AudioChunk]:
        """Read next chunk to send."""
        return await self.buffer.get(timeout=timeout)

    def read_nowait(self) -> Optional[AudioChunk]:
        """Non-blocking read for output."""
        return self.buffer.get_nowait()

    async def __aiter__(self) -> AsyncIterator[AudioChunk]:
        """Async iterator for sending chunks."""
        while not self.buffer.is_closed or not self.buffer.is_empty:
            chunk = await self.buffer.get(timeout=0.1)
            if chunk is not None:
                yield chunk
            elif self.buffer.is_closed:
                break

    def close(self) -> None:
        self.buffer.close()

    @property
    def stats(self) -> dict:
        return {
            "total_frames": self._total_frames,
            "total_bytes": self._total_bytes,
            "buffered_frames": self.buffer.size,
        }
