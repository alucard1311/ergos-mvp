"""Latency tracking and metrics collection for voice-to-voice response time."""

import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LatencyMetrics:
    """Collects and computes latency statistics.

    Maintains a rolling window of the last 100 latency samples
    for percentile calculations.
    """

    count: int = 0
    total_ms: float = 0.0
    samples: list[float] = field(default_factory=list)

    # Maximum number of samples to keep for percentile calculation
    _max_samples: int = field(default=100, init=False, repr=False)

    def record(self, latency_ms: float) -> None:
        """Record a latency measurement.

        Args:
            latency_ms: Latency in milliseconds to record.
        """
        self.count += 1
        self.total_ms += latency_ms
        self.samples.append(latency_ms)

        # Trim to last 100 samples
        if len(self.samples) > self._max_samples:
            self.samples = self.samples[-self._max_samples:]

    def p50(self) -> float:
        """Compute median (50th percentile) latency.

        Returns:
            Median latency in ms, or 0 if no samples.
        """
        if not self.samples:
            return 0.0
        return statistics.median(self.samples)

    def p95(self) -> float:
        """Compute 95th percentile latency.

        Returns:
            95th percentile latency in ms, or 0 if no samples.
        """
        if not self.samples:
            return 0.0
        # quantiles requires at least 2 samples for n=20 (95th = 19/20)
        if len(self.samples) < 2:
            return self.samples[0]
        sorted_samples = sorted(self.samples)
        idx = int(0.95 * len(sorted_samples))
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    def mean(self) -> float:
        """Compute mean latency.

        Returns:
            Mean latency in ms, or 0 if no samples.
        """
        if self.count == 0:
            return 0.0
        return self.total_ms / self.count

    def to_dict(self) -> dict:
        """Return all statistics as a dictionary.

        Returns:
            Dictionary with count, total_ms, p50, p95, and mean.
        """
        return {
            "count": self.count,
            "total_ms": self.total_ms,
            "p50_ms": self.p50(),
            "p95_ms": self.p95(),
            "mean_ms": self.mean(),
        }


class LatencyTracker:
    """Tracks timing for a single voice-to-voice interaction cycle.

    Measures latency from speech_end (user stops speaking) to
    first_audio (first TTS audio chunk is ready). This represents
    the true "voice-to-voice" latency including STT, LLM, and TTS.
    """

    def __init__(self):
        self._speech_end_time: Optional[float] = None
        self._first_audio_time: Optional[float] = None
        self._metrics = LatencyMetrics()
        self._waiting_for_audio = False

    def mark_speech_end(self) -> None:
        """Record the time when user stops speaking.

        Call this when VAD emits SPEECH_END.
        """
        self._speech_end_time = time.monotonic()
        self._waiting_for_audio = True
        logger.debug("Latency: marked speech_end")

    def mark_first_audio(self) -> None:
        """Record the time when first TTS audio is ready.

        Call this when the first TTS audio chunk is emitted
        after speech_end.
        """
        if self._waiting_for_audio:
            self._first_audio_time = time.monotonic()
            self._waiting_for_audio = False
            logger.debug("Latency: marked first_audio")

    def compute_latency(self) -> Optional[float]:
        """Compute latency between speech_end and first_audio.

        Returns:
            Latency in milliseconds, or None if timing points not set.
        """
        if self._speech_end_time is None or self._first_audio_time is None:
            return None
        return (self._first_audio_time - self._speech_end_time) * 1000

    def reset(self) -> None:
        """Clear current cycle timing points.

        Call this after logging to prepare for next cycle.
        """
        self._speech_end_time = None
        self._first_audio_time = None
        self._waiting_for_audio = False

    def log_current(self) -> None:
        """Log current cycle latency and cumulative statistics.

        Records the current latency to metrics and logs a summary.
        """
        latency = self.compute_latency()
        if latency is not None:
            self._metrics.record(latency)
            logger.info(
                f"Latency: {latency:.0f}ms | "
                f"P50: {self._metrics.p50():.0f}ms | "
                f"P95: {self._metrics.p95():.0f}ms | "
                f"Mean: {self._metrics.mean():.0f}ms "
                f"(n={self._metrics.count})"
            )

    @property
    def metrics(self) -> LatencyMetrics:
        """Access the underlying metrics collector."""
        return self._metrics

    @property
    def is_waiting_for_audio(self) -> bool:
        """Whether we are waiting for first audio after speech_end."""
        return self._waiting_for_audio
