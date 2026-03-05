"""Tests for STT transcription filter."""

import pytest

from ergos.stt.filter import TranscriptionFilter
from ergos.stt.types import TranscriptionResult, TranscriptionSegment


def _make_result(text: str, word_confs: list[float] | None = None) -> TranscriptionResult:
    """Helper to create TranscriptionResult with optional word confidences."""
    segments = []
    if word_confs is not None:
        words = text.split()
        for i, (word, conf) in enumerate(zip(words, word_confs)):
            segments.append(TranscriptionSegment(
                text=word, start=i * 0.5, end=(i + 1) * 0.5, confidence=conf
            ))
    return TranscriptionResult(text=text, segments=segments, duration_ms=1000.0)


class TestHallucinationFilter:
    """Test known Whisper hallucination pattern rejection."""

    def test_rejects_thank_you(self):
        f = TranscriptionFilter()
        assert f.filter(_make_result("Thank you.")) is None

    def test_rejects_thanks_for_watching(self):
        f = TranscriptionFilter()
        assert f.filter(_make_result("Thanks for watching.")) is None

    def test_rejects_subscribe(self):
        f = TranscriptionFilter()
        assert f.filter(_make_result("Subscribe")) is None

    def test_rejects_music_notes(self):
        f = TranscriptionFilter()
        assert f.filter(_make_result("♪ ♫ ♪")) is None

    def test_rejects_parenthetical(self):
        f = TranscriptionFilter()
        assert f.filter(_make_result("(upbeat music)")) is None

    def test_rejects_single_you(self):
        f = TranscriptionFilter()
        assert f.filter(_make_result("you")) is None

    def test_accepts_real_speech(self):
        f = TranscriptionFilter()
        result = _make_result("Tell me a joke about programming")
        assert f.filter(result) is not None

    def test_accepts_sentence_with_thank_you(self):
        """'Thank you' inside a real sentence should NOT be rejected."""
        f = TranscriptionFilter()
        result = _make_result("Thank you for helping me with that problem")
        assert f.filter(result) is not None


class TestConfidenceFilter:
    """Test confidence-based filtering."""

    def test_rejects_low_avg_confidence(self):
        f = TranscriptionFilter()
        result = _make_result("garbled nonsense words", [0.2, 0.3, 0.1, 0.4])
        # avg = 0.25, below 0.45 threshold
        assert f.filter(result) is None

    def test_accepts_high_confidence(self):
        f = TranscriptionFilter()
        result = _make_result("tell me a joke", [0.95, 0.90, 0.88, 0.92])
        assert f.filter(result) is not None

    def test_rejects_too_many_low_words(self):
        f = TranscriptionFilter()
        # 4/5 words below 0.15 = 80% ratio, above 60% threshold
        result = _make_result("a b c d good", [0.05, 0.08, 0.10, 0.07, 0.95])
        assert f.filter(result) is None

    def test_no_segments_skips_confidence_check(self):
        """Without word-level data, skip confidence filtering."""
        f = TranscriptionFilter()
        result = _make_result("some text without segments")
        assert f.filter(result) is not None


class TestRepetitionFilter:
    """Test repetition detection."""

    def test_strips_repeated_sentences(self):
        f = TranscriptionFilter()
        result = _make_result("Tell me a joke. Tell me a joke. Tell me a joke.")
        filtered = f.filter(result)
        assert filtered is not None
        assert filtered.text == "Tell me a joke."

    def test_keeps_different_sentences(self):
        f = TranscriptionFilter()
        result = _make_result("Hello there. How are you?")
        filtered = f.filter(result)
        assert filtered is not None
        assert filtered.text == "Hello there. How are you?"

    def test_rejects_cross_utterance_repetition(self):
        """Same utterance 3 times across calls should be rejected."""
        f = TranscriptionFilter()
        r1 = _make_result("hello")
        r2 = _make_result("hello")
        r3 = _make_result("hello")
        assert f.filter(r1) is not None
        assert f.filter(r2) is not None
        assert f.filter(r3) is None  # Third time rejected


class TestEmptyInput:
    """Test edge cases."""

    def test_rejects_empty(self):
        f = TranscriptionFilter()
        assert f.filter(_make_result("")) is None

    def test_rejects_whitespace(self):
        f = TranscriptionFilter()
        assert f.filter(_make_result("   ")) is None

    def test_rejects_dots_only(self):
        f = TranscriptionFilter()
        assert f.filter(_make_result("...")) is None
