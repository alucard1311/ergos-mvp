"""Custom AudioStreamTrack for streaming TTS audio to WebRTC."""

from __future__ import annotations

import asyncio
import fractions
import logging
import threading
import time
from typing import Optional, Union

import numpy as np
from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import AudioFrame

logger = logging.getLogger(__name__)

# 20ms per frame - standard for WebRTC audio pacing
AUDIO_PTIME = 0.020


class TTSAudioTrack(MediaStreamTrack):
    """
    Custom audio track that streams TTS audio to WebRTC.

    This track buffers audio samples and returns them in fixed-size frames
    (20ms) to aiortc. Audio is resampled from TTS output (24kHz) to WebRTC
    standard (48kHz).

    IMPORTANT: This track implements real-time pacing. The recv() method
    sleeps to maintain a 20ms interval between frames, matching the actual
    audio playback rate. Without pacing, frames would be sent at CPU speed,
    overwhelming the client decoder.

    Attributes:
        kind: Always "audio" for audio tracks.
    """

    kind = "audio"

    # WebRTC standard sample rate
    WEBRTC_SAMPLE_RATE = 48000

    def __init__(self, sample_rate: int = 24000) -> None:
        """
        Initialize the TTS audio track.

        Args:
            sample_rate: Sample rate of incoming TTS audio (default 24kHz).
                Audio will be resampled to 48kHz for WebRTC.
        """
        super().__init__()
        self._buffer: list[np.ndarray] = []  # Buffer for audio samples
        self._buffer_samples = 0  # Total samples in buffer
        self._buffer_lock = threading.Lock()  # Thread safety for buffer ops
        self._input_sample_rate = sample_rate
        self._sample_rate = self.WEBRTC_SAMPLE_RATE  # Output at 48kHz for WebRTC
        self._timestamp = 0
        self._samples_per_frame = int(self._sample_rate * AUDIO_PTIME)  # 960 samples for 20ms at 48kHz

        # Pacing state - track start time to maintain real-time frame rate
        self._start_time: Optional[float] = None

    async def recv(self) -> AudioFrame:
        """
        Return the next audio frame (20ms of audio at 48kHz = 960 samples).

        Called by aiortc's RTP sender in a tight loop. This method implements
        real-time pacing to return frames at exactly the playback rate (one
        20ms frame every 20ms). Without pacing, frames would be sent at CPU
        speed, causing the client decoder to fail or drop audio.

        Returns:
            An AudioFrame containing 20ms of audio.

        Raises:
            MediaStreamError: If the track is no longer live.
        """
        if self.readyState != "live":
            raise MediaStreamError

        # Implement real-time pacing (critical for correct playback)
        # Based on aiortc's AudioStreamTrack implementation
        if self._start_time is not None:
            # Calculate how long we should have been running based on timestamp
            elapsed_samples = self._timestamp
            expected_elapsed_time = elapsed_samples / self._sample_rate
            actual_elapsed_time = time.time() - self._start_time

            # Sleep until it's time for this frame
            wait_time = expected_elapsed_time - actual_elapsed_time
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        else:
            # First call - record start time
            self._start_time = time.time()

        # Check if we have enough samples in buffer (thread-safe)
        with self._buffer_lock:
            if self._buffer_samples >= self._samples_per_frame:
                # Concatenate buffer and extract one frame
                all_samples = np.concatenate(self._buffer)
                # CRITICAL: Use .copy() to create independent memory, not a view.
                # Views share memory with all_samples, which can cause segfaults
                # when the buffer is modified by push_audio() in another thread.
                samples = all_samples[:self._samples_per_frame].copy()
                remaining = all_samples[self._samples_per_frame:]

                # Update buffer with remaining samples (copy to avoid memory aliasing)
                if len(remaining) > 0:
                    self._buffer = [remaining.copy()]
                    self._buffer_samples = len(remaining)
                else:
                    self._buffer = []
                    self._buffer_samples = 0
            else:
                # Not enough samples, return silence
                samples = np.zeros(self._samples_per_frame, dtype=np.int16)

        # Ensure correct dtype
        if samples.dtype == np.float32:
            samples = (samples * 32767).astype(np.int16)
        elif samples.dtype != np.int16:
            samples = samples.astype(np.int16)

        # Reshape for mono layout: (1, num_samples)
        samples = samples.reshape(1, -1)

        # Ensure C-contiguous memory layout for native code (av/ffmpeg).
        # Non-contiguous arrays can cause segfaults in memcpy operations.
        if not samples.flags['C_CONTIGUOUS']:
            samples = np.ascontiguousarray(samples)

        # Create AudioFrame from numpy array
        frame = AudioFrame.from_ndarray(samples, format="s16", layout="mono")
        frame.pts = self._timestamp
        frame.sample_rate = self._sample_rate
        frame.time_base = fractions.Fraction(1, self._sample_rate)

        # Increment timestamp
        self._timestamp += self._samples_per_frame

        return frame

    # Maximum buffer size: 10 seconds at 48kHz (prevent runaway memory growth)
    MAX_BUFFER_SAMPLES = 48000 * 10

    def push_audio(self, samples: np.ndarray, input_sample_rate: int = 24000) -> None:
        """
        Push TTS audio samples to the buffer.

        Audio is upsampled from input rate to 48kHz for WebRTC compatibility.
        Uses simple sample repetition for 2x upsampling (24kHz -> 48kHz).

        Args:
            samples: Audio samples as a numpy array. Can be float32
                (TTS output format) or int16.
            input_sample_rate: Sample rate of input audio (default 24kHz for TTS).
        """
        # CRITICAL: Check if track is still live before modifying buffer.
        # This prevents segfaults when push_audio() is called after the
        # connection closes but before the track reference is cleaned up.
        if self.readyState != "live":
            logger.debug("TTSAudioTrack: Ignoring push_audio() - track not live")
            return

        # Convert float32 to int16 first
        if samples.dtype == np.float32:
            samples = (samples * 32767).astype(np.int16)

        # Simple 2x upsampling by repeating each sample (24kHz -> 48kHz)
        if input_sample_rate == 24000 and self._sample_rate == 48000:
            # Repeat each sample twice: [a, b, c] -> [a, a, b, b, c, c]
            samples = np.repeat(samples, 2)

        # Thread-safe buffer operations
        with self._buffer_lock:
            new_total = self._buffer_samples + len(samples)

            # Warn if buffer is getting large, skip if over limit
            if new_total > self.MAX_BUFFER_SAMPLES:
                logger.warning(
                    f"TTSAudioTrack: Buffer overflow, dropping {len(samples)} samples "
                    f"(buffer at {self._buffer_samples / self._sample_rate * 1000:.0f}ms)"
                )
                return

            logger.debug(
                f"TTSAudioTrack: Buffering {len(samples)} samples, "
                f"buffer now has {new_total} samples "
                f"({new_total / self._sample_rate * 1000:.0f}ms)"
            )

            # Add to buffer
            self._buffer.append(samples)
            self._buffer_samples += len(samples)

    def clear(self) -> None:
        """
        Clear the audio buffer.

        Call this on barge-in to immediately stop pending TTS audio
        and make room for new audio.
        """
        with self._buffer_lock:
            self._buffer = []
            self._buffer_samples = 0
        logger.debug("TTSAudioTrack: Buffer cleared")

    @property
    def buffer_duration_ms(self) -> float:
        """Get the current buffer duration in milliseconds."""
        with self._buffer_lock:
            return (self._buffer_samples / self._sample_rate) * 1000

    @property
    def has_audio(self) -> bool:
        """Check if there's audio in the buffer."""
        with self._buffer_lock:
            return self._buffer_samples > 0
