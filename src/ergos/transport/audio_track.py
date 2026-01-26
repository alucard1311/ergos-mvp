"""Custom AudioStreamTrack for streaming TTS audio to WebRTC."""

from __future__ import annotations

import asyncio
import fractions
from typing import Union

import numpy as np
from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import AudioFrame

# 20ms per frame - standard for WebRTC audio pacing
AUDIO_PTIME = 0.020


class TTSAudioTrack(MediaStreamTrack):
    """
    Custom audio track that streams TTS audio to WebRTC.

    This track pulls audio samples from an internal queue and returns
    AudioFrame objects to aiortc. If no audio is available, it returns
    silence to avoid blocking the WebRTC connection.

    Attributes:
        kind: Always "audio" for audio tracks.
    """

    kind = "audio"

    def __init__(self, sample_rate: int = 24000) -> None:
        """
        Initialize the TTS audio track.

        Args:
            sample_rate: Sample rate for the audio output. Kokoro TTS
                outputs 24kHz, so this defaults to 24000.
        """
        super().__init__()
        self._queue: asyncio.Queue[Union[np.ndarray, None]] = asyncio.Queue()
        self._sample_rate = sample_rate
        self._timestamp = 0
        self._samples_per_frame = int(sample_rate * AUDIO_PTIME)

    async def recv(self) -> AudioFrame:
        """
        Return the next audio frame.

        Called by aiortc at regular intervals. This method MUST NOT block
        indefinitely - if no audio is available, it returns silence.

        Returns:
            An AudioFrame containing either TTS audio or silence.

        Raises:
            MediaStreamError: If the track is no longer live.
        """
        if self.readyState != "live":
            raise MediaStreamError

        # Try to get audio from queue with timeout
        samples: Union[np.ndarray, None] = None
        try:
            samples = await asyncio.wait_for(
                self._queue.get(),
                timeout=AUDIO_PTIME,
            )
        except asyncio.TimeoutError:
            samples = None

        # Generate silence if no audio available
        if samples is None:
            samples = np.zeros(self._samples_per_frame, dtype=np.int16)

        # Ensure correct dtype (convert float32 to int16 if needed)
        if samples.dtype == np.float32:
            # TTS output is typically float32 in [-1, 1] range
            samples = (samples * 32767).astype(np.int16)
        elif samples.dtype != np.int16:
            samples = samples.astype(np.int16)

        # Reshape for mono layout: (1, num_samples)
        if samples.ndim == 1:
            samples = samples.reshape(1, -1)

        # Create AudioFrame from numpy array
        frame = AudioFrame.from_ndarray(samples, format="s16", layout="mono")
        frame.pts = self._timestamp
        frame.sample_rate = self._sample_rate
        frame.time_base = fractions.Fraction(1, self._sample_rate)

        # Increment timestamp by number of samples
        self._timestamp += samples.shape[1]

        return frame

    def push_audio(self, samples: np.ndarray) -> None:
        """
        Push TTS audio samples to the queue.

        This method is non-blocking and will discard samples if the
        queue is full (which shouldn't happen under normal operation).

        Args:
            samples: Audio samples as a numpy array. Can be float32
                (TTS output format) or int16.
        """
        try:
            self._queue.put_nowait(samples)
        except asyncio.QueueFull:
            # Queue is full, discard oldest and add new
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(samples)
            except asyncio.QueueEmpty:
                pass

    def clear(self) -> None:
        """
        Clear the audio queue.

        Call this on barge-in to immediately stop pending TTS audio
        and make room for new audio.
        """
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
