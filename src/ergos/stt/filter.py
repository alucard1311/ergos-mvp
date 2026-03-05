"""Intelligent STT transcription filter.

Cleans up garbled Whisper transcriptions before they reach the LLM.
Handles three classes of errors:

1. Hallucinations: Known phantom phrases Whisper produces on noise/silence
2. Low confidence: Garbled output where Whisper is uncertain about words
3. Repetitions: Whisper looping the same phrase multiple times
"""

import logging
import re
from dataclasses import dataclass, field

from .types import TranscriptionResult

logger = logging.getLogger(__name__)

# Known Whisper hallucination patterns (case-insensitive).
# These are well-documented phantom outputs that Whisper produces
# when given silence, noise, or ambiguous audio.
_HALLUCINATION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^thank you[. ]*$",
        r"^thanks for watching[. ]*$",
        r"^thank you for watching[. ]*$",
        r"^please subscribe[. ]*$",
        r"^(like and )?subscribe[. ]*$",
        r"^see you (next time|in the next)[. ]*$",
        r"^bye[. !]*$",
        r"^you$",
        r"^i'm going to",
        r"^okay[. ]*$",
        r"^so[. ]*$",
        r"^\.+$",
        r"^[♪♫🎵🎶\s]+$",  # Music note hallucinations
        r"^\s*\(.*\)\s*$",  # Parenthetical descriptions like "(upbeat music)"
        r"^[\u200f\u200e\u200b\u200c\u200d\s]+$",  # RTL/LTR/zero-width markers only
        r"^[†‡•§¶©®™\W\s]+$",  # Non-speech symbols only (daggers, bullets, etc.)
        r"^[^\w\s]{2,}$",  # Strings of 2+ non-word/non-space chars (garbage)
        r"^(ergos[,.]?\s*sarcasm[,.]?\s*)+$",  # Whisper echoing its own initial_prompt
    ]
]

# Minimum average word confidence to accept a transcription.
# Whisper word probabilities: >0.8 = good, 0.5-0.8 = uncertain, <0.5 = garbled.
_MIN_AVG_CONFIDENCE = 0.25

# Minimum per-word confidence. Words below this are likely hallucinated.
_MIN_WORD_CONFIDENCE = 0.15

# Maximum ratio of low-confidence words before rejecting the whole transcription.
_MAX_LOW_CONF_RATIO = 0.6


@dataclass
class TranscriptionFilter:
    """Filters garbled or hallucinated Whisper transcriptions.

    Sits between STT transcriber output and pipeline callbacks.
    Returns cleaned text or None if the transcription should be rejected.
    """

    # Track recent transcriptions to detect repetition loops
    _recent: list[str] = field(default_factory=list, init=False)
    _max_recent: int = 5

    def filter(self, result: TranscriptionResult) -> TranscriptionResult | None:
        """Filter a transcription result.

        Args:
            result: Raw transcription from Whisper.

        Returns:
            Cleaned TranscriptionResult, or None if rejected.
        """
        text = result.text.strip()

        if not text:
            return None

        # 1. Hallucination filter
        for pattern in _HALLUCINATION_PATTERNS:
            if pattern.match(text):
                logger.info("STT filter: rejected hallucination: %r", text)
                return None

        # 2. Confidence filter (only if we have word-level data)
        if result.segments:
            confidences = [s.confidence for s in result.segments if s.confidence > 0]
            if confidences:
                avg_conf = sum(confidences) / len(confidences)
                low_conf_count = sum(1 for c in confidences if c < _MIN_WORD_CONFIDENCE)
                low_conf_ratio = low_conf_count / len(confidences)

                if avg_conf < _MIN_AVG_CONFIDENCE:
                    logger.info(
                        "STT filter: rejected low confidence (avg=%.2f): %r",
                        avg_conf, text
                    )
                    return None

                if low_conf_ratio > _MAX_LOW_CONF_RATIO:
                    logger.info(
                        "STT filter: rejected too many low-confidence words "
                        "(%.0f%% below %.2f): %r",
                        low_conf_ratio * 100, _MIN_WORD_CONFIDENCE, text
                    )
                    return None

        # 3. Repetition filter — detect Whisper looping
        cleaned = self._strip_repetitions(text)
        if cleaned != text:
            logger.info("STT filter: stripped repetitions: %r -> %r", text, cleaned)
            text = cleaned

        if not text.strip():
            return None

        # 4. Track for cross-utterance repetition detection
        normalized = text.lower().strip()
        if self._recent.count(normalized) >= 2:
            logger.info("STT filter: rejected repeated utterance: %r", text)
            return None
        self._recent.append(normalized)
        if len(self._recent) > self._max_recent:
            self._recent.pop(0)

        # Return cleaned result
        if text != result.text.strip():
            return TranscriptionResult(
                text=text,
                segments=result.segments,
                language=result.language,
                duration_ms=result.duration_ms,
            )
        return result

    @staticmethod
    def _strip_repetitions(text: str) -> str:
        """Remove repeated phrases/sentences from transcription.

        Whisper sometimes loops, producing output like:
        "Tell me a joke. Tell me a joke. Tell me a joke."

        Detects repeated sentence-like chunks and keeps just the first.
        """
        # Split on sentence boundaries
        parts = re.split(r'(?<=[.!?])\s+', text)
        if len(parts) <= 1:
            return text

        # Check if all parts are the same (or nearly)
        normalized = [p.strip().lower().rstrip('.!? ') for p in parts]
        if len(set(normalized)) == 1 and len(normalized) > 1:
            return parts[0]

        # Check for repeated consecutive chunks
        seen = []
        for part in parts:
            norm = part.strip().lower().rstrip('.!? ')
            if not seen or norm != seen[-1]:
                seen.append(norm)
        if len(seen) < len(parts):
            # Reconstruct from unique consecutive parts
            unique_parts = []
            last_norm = None
            for part in parts:
                norm = part.strip().lower().rstrip('.!? ')
                if norm != last_norm:
                    unique_parts.append(part)
                    last_norm = norm
            return ' '.join(unique_parts)

        return text
