"""Orpheus 3B TTS synthesizer using orpheus-cpp (llama.cpp backend)."""

import logging
from collections.abc import AsyncIterator
from typing import Optional

import numpy as np

from .types import SynthesisConfig, SynthesisResult

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000

# Fade durations for smooth sentence transitions
_FADE_IN_MS = 22   # Covers fricatives/nasals (20-50ms onset)
_FADE_OUT_MS = 50   # Smooth cosine tail


def _apply_fade(audio: np.ndarray, sample_rate: int, duration_ms: int, fade_out: bool = False) -> np.ndarray:
    """Apply cosine (equal-power) fade for natural-sounding transitions."""
    n_samples = min(int(sample_rate * duration_ms / 1000), len(audio))
    if n_samples == 0:
        return audio
    audio = audio.copy()
    t = np.linspace(0.0, np.pi / 2, n_samples, dtype=np.float32)
    ramp = np.sin(t)  # 0→1 along sin curve (perceptually linear loudness)
    if fade_out:
        audio[-n_samples:] *= ramp[::-1]
    else:
        audio[:n_samples] *= ramp
    return audio


class OrpheusSynthesizer:
    """Orpheus 3B synthesizer with lazy loading and emotion tag support.

    Uses orpheus-cpp (llama.cpp backend) for expressive TTS with inline
    emotion tags: <laugh>, <chuckle>, <sigh>, <cough>, <sniffle>, <groan>,
    <yawn>, <gasp>.

    Model: isaiahbjork/orpheus-3b-0.1-ft-Q4_K_M-GGUF (~2GB VRAM at Q4_K_M)
    Output: 24kHz audio (matches Kokoro sample rate)

    The model is loaded lazily on first use via _ensure_model().
    """

    # orpheus-cpp hardcodes n_ctx=0 which inherits the model's 128K default,
    # creating a 14GB KV cache that OOMs on most machines. We patch it to a
    # sensible value for TTS (2048 tokens is plenty for single utterances).
    DEFAULT_N_CTX = 2048

    def __init__(
        self,
        n_gpu_layers: int = -1,
        n_ctx: int = DEFAULT_N_CTX,
        lang: str = "en",
        verbose: bool = False,
    ) -> None:
        """Initialize OrpheusSynthesizer with lazy loading.

        Args:
            n_gpu_layers: Number of GPU layers to offload. -1 means all layers.
                          Set to 0 for CPU-only.
            n_ctx: Context window size for KV cache. Default 2048 to avoid the
                   library's 128K default that requires 14GB+ RAM.
            lang: Language code for Orpheus model (default "en").
            verbose: Enable verbose llama.cpp output (default False).
        """
        self._n_gpu_layers = n_gpu_layers
        self._n_ctx = n_ctx
        self._lang = lang
        self._verbose = verbose

        self._orpheus = None

    def _ensure_model(self):
        """Lazy load Orpheus model via orpheus-cpp.

        Patches llama_cpp.Llama to override n_ctx before OrpheusCpp creates
        its model, then restores the original constructor.
        """
        if self._orpheus is not None:
            return self._orpheus

        logger.info(
            f"Loading Orpheus 3B model "
            f"(n_gpu_layers={self._n_gpu_layers}, n_ctx={self._n_ctx}, "
            f"lang={self._lang})..."
        )

        import llama_cpp
        from orpheus_cpp import OrpheusCpp

        _original_init = llama_cpp.Llama.__init__
        n_ctx = self._n_ctx

        def _patched_init(self_llama, *args, **kwargs):
            kwargs["n_ctx"] = n_ctx
            return _original_init(self_llama, *args, **kwargs)

        llama_cpp.Llama.__init__ = _patched_init
        try:
            self._orpheus = OrpheusCpp(
                n_gpu_layers=self._n_gpu_layers,
                lang=self._lang,
                verbose=self._verbose,
            )
        finally:
            llama_cpp.Llama.__init__ = _original_init

        # Monkey-patch _decode to flush trailing SNAC tokens.
        # The original only yields at count % 7 == 0, silently dropping
        # the last 1-6 tokens (~73ms of audio) at every sentence end.
        orpheus_inst = self._orpheus

        _original_decode = orpheus_inst._decode

        def _patched_decode(token_gen):
            buffer = []
            count = 0
            for token_text in token_gen:
                token = orpheus_inst._token_to_id(token_text, count)
                if token is not None and token > 0:
                    buffer.append(token)
                    count += 1
                    if count % 7 == 0 and count > 27:
                        buffer_to_proc = buffer[-28:]
                        audio_samples = orpheus_inst._convert_to_audio(buffer_to_proc)
                        if audio_samples is not None:
                            yield audio_samples
            # Flush trailing tokens by padding to next multiple of 7
            trailing = count % 7
            if trailing > 0 and len(buffer) >= 28:
                pad_needed = 7 - trailing
                buffer.extend([buffer[-1]] * pad_needed)
                buffer_to_proc = buffer[-28:]
                audio_samples = orpheus_inst._convert_to_audio(buffer_to_proc)
                if audio_samples is not None:
                    yield audio_samples

        import types
        orpheus_inst._decode = types.MethodType(
            lambda self, token_gen: _patched_decode(token_gen),
            orpheus_inst,
        )

        logger.info("Orpheus 3B model loaded successfully (with trailing token flush patch)")

        return self._orpheus

    def _build_options(self, config: SynthesisConfig) -> dict:
        """Build TTSOptions dict from SynthesisConfig."""
        return {
            "voice_id": config.orpheus_voice,
            "temperature": config.temperature,
            "top_k": config.top_k,
        }

    def synthesize(
        self,
        text: str,
        config: Optional[SynthesisConfig] = None,
    ) -> SynthesisResult:
        """Synthesize speech from text synchronously.

        Emotion tags in text are rendered as audible expression:
        <laugh>, <chuckle>, <sigh>, <cough>, <sniffle>, <groan>, <yawn>, <gasp>

        Args:
            text: Input text to synthesize (may contain emotion tags).
            config: Synthesis configuration. Uses defaults if None.

        Returns:
            SynthesisResult with float32 audio samples at 24kHz.
        """
        if config is None:
            config = SynthesisConfig()

        self._ensure_model()

        options = self._build_options(config)
        sample_rate, audio_int16 = self._orpheus.tts(text, options)

        # orpheus-cpp returns shape (1, N) — squeeze to 1D for playback/pipeline
        audio_int16 = np.squeeze(audio_int16)
        # Convert int16 -> float32 normalized to [-1, 1]
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        # Orpheus outputs quiet audio (~0.25 peak); normalize to ~0.95 peak
        peak = np.abs(audio_float32).max()
        if peak > 0:
            audio_float32 = audio_float32 * (0.95 / peak)
        duration_ms = (len(audio_float32) / SAMPLE_RATE) * 1000.0

        return SynthesisResult(
            audio_samples=audio_float32,
            sample_rate=SAMPLE_RATE,
            text=text,
            duration_ms=duration_ms,
        )

    # Fixed gain for true streaming (no global normalization pass).
    # Orpheus outputs at ~0.25 peak; 3.8x brings it to ~0.95 target.
    # np.clip ensures safety if a chunk happens to be louder.
    _FIXED_GAIN = 3.8

    # Raw peak threshold to skip SNAC warmup/silence frames.
    # Warmup noise is ~0.01 peak; real speech is ~0.25 peak.
    _RAW_NOISE_CEIL = 0.015

    # Window size for scanning within large pre-buffer chunks (85ms at 24kHz)
    _NOISE_SCAN_WINDOW = 2048

    def _trim_leading_noise(self, audio: np.ndarray) -> np.ndarray:
        """Trim leading warmup noise from a large audio chunk (pre-buffer).

        The first chunk from stream_tts is ~1.5s of pre-buffered audio that
        includes SNAC warmup noise at the start. This scans in 85ms windows
        to find where real speech begins and trims the leading noise.
        """
        w = self._NOISE_SCAN_WINDOW
        for i in range(0, len(audio) - w, w):
            window_peak = np.abs(audio[i:i + w]).max()
            if window_peak >= self._RAW_NOISE_CEIL:
                if i > 0:
                    logger.debug(f"Trimmed {i} samples ({i/SAMPLE_RATE*1000:.0f}ms) of leading noise from pre-buffer")
                return audio[i:]
        return audio

    async def synthesize_stream(
        self,
        text: str,
        config: Optional[SynthesisConfig] = None,
    ) -> AsyncIterator[tuple[np.ndarray, int]]:
        """Synthesize speech with true streaming — yield chunks as they arrive.

        Uses fixed gain instead of global normalization so chunks can be
        yielded immediately without waiting for the full utterance.

        One-ahead buffer: holds the current chunk and yields the previous one,
        so the very last chunk can have fade-out applied before yielding.

        Noise handling:
        - Leading: small chunks below _RAW_NOISE_CEIL are skipped entirely;
          large pre-buffer chunks are scanned to trim leading warmup noise.

        Args:
            text: Input text to synthesize (may contain emotion tags).
            config: Synthesis configuration. Uses defaults if None.

        Yields:
            Tuples of (audio_samples: np.ndarray[float32], sample_rate: int).
        """
        if config is None:
            config = SynthesisConfig()

        self._ensure_model()

        options = self._build_options(config)

        speech_started = False
        prev_chunk: Optional[np.ndarray] = None  # one-ahead buffer

        async for chunk_sr, audio_int16 in self._orpheus.stream_tts(text, options):
            audio_1d = np.squeeze(audio_int16)
            audio_f32 = audio_1d.astype(np.float32) / 32768.0

            # Skip leading silence/warmup frames before first speech
            if not speech_started:
                raw_peak = np.abs(audio_f32).max()
                if raw_peak < self._RAW_NOISE_CEIL:
                    continue
                # Large pre-buffer chunks contain warmup noise mixed with speech;
                # scan within the chunk to trim leading noise
                if len(audio_f32) > self._NOISE_SCAN_WINDOW * 2:
                    audio_f32 = self._trim_leading_noise(audio_f32)
                speech_started = True

            # Apply fixed gain + clip
            audio_f32 = np.clip(audio_f32 * self._FIXED_GAIN, -1.0, 1.0)

            if prev_chunk is None:
                # First speech chunk — apply fade-in, store in buffer
                prev_chunk = _apply_fade(audio_f32, SAMPLE_RATE, _FADE_IN_MS)
            else:
                # Yield the previous chunk, buffer the current one
                yield prev_chunk, SAMPLE_RATE
                prev_chunk = audio_f32

        # Yield the last chunk with fade-out
        if prev_chunk is not None:
            prev_chunk = _apply_fade(prev_chunk, SAMPLE_RATE, _FADE_OUT_MS, fade_out=True)
            yield prev_chunk, SAMPLE_RATE

    @property
    def model_loaded(self) -> bool:
        """Check if the Orpheus model is currently loaded."""
        return self._orpheus is not None

    @property
    def sample_rate(self) -> int:
        """Get the output sample rate (24000 Hz)."""
        return SAMPLE_RATE

    def close(self) -> None:
        """Release Orpheus model resources."""
        if self._orpheus is not None:
            self._orpheus = None
            logger.info("Orpheus 3B model released")
