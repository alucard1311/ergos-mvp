"""Unit tests for full-duplex conversation state machine and LLM cancel fix.

Covers:
  - VOICE-01: LatencyTracker records timestamps and computes P50
  - VOICE-02: SPEAKING_AND_LISTENING state machine transitions
  - VOICE-03: barge_in() from SPEAKING_AND_LISTENING, LLM cancel flag reset

All state machine tests depend on SPEAKING_AND_LISTENING existing in the enum
and updated transition table — these will be RED until Task 2 is applied.
Latency tracker tests should be GREEN immediately (existing infrastructure).
"""

import sys
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Dependency mocks — must be set up before any ergos submodule is imported so
# that ergos/__init__.py can load the full pipeline without hitting missing
# optional libraries (aiohttp, aiortc, llama_cpp, faster_whisper, etc.)
# ---------------------------------------------------------------------------

_aiortc_mock = MagicMock()
sys.modules.setdefault("aiortc", _aiortc_mock)
sys.modules.setdefault("aiortc.mediastreams", MagicMock())

for _mod in [
    "aiohttp",
    "faster_whisper",
    "llama_cpp",
    "kokoro_onnx",
    "av",
]:
    sys.modules.setdefault(_mod, MagicMock())

# ---------------------------------------------------------------------------
# Real imports (after mocks are in place)
# ---------------------------------------------------------------------------

import asyncio
import queue
import threading

import pytest
import pytest_asyncio

from ergos.metrics import LatencyMetrics, LatencyTracker
from ergos.state.events import ConversationState
from ergos.state.machine import VALID_TRANSITIONS, ConversationStateMachine

# ---------------------------------------------------------------------------
# Helper: transition machine from IDLE -> SPEAKING via standard path
# ---------------------------------------------------------------------------


async def _set_state_to_speaking(machine: ConversationStateMachine) -> None:
    """Transition a fresh machine from IDLE through to SPEAKING."""
    assert await machine.transition_to(ConversationState.LISTENING)
    assert await machine.transition_to(ConversationState.PROCESSING)
    assert await machine.transition_to(ConversationState.SPEAKING)


# ===========================================================================
# VOICE-02: State machine — SPEAKING_AND_LISTENING enum and transitions
# ===========================================================================


class TestSpeakingAndListeningEnum:
    """SPEAKING_AND_LISTENING must exist as a ConversationState enum value."""

    def test_speaking_and_listening_enum_value(self):
        """ConversationState.SPEAKING_AND_LISTENING has value 'speaking_and_listening'."""
        assert ConversationState.SPEAKING_AND_LISTENING.value == "speaking_and_listening"

    def test_five_conversation_states_exist(self):
        """ConversationState has exactly 5 members after adding SPEAKING_AND_LISTENING."""
        members = list(ConversationState)
        assert len(members) == 5
        names = {m.name for m in members}
        assert "SPEAKING_AND_LISTENING" in names


class TestValidTransitions:
    """VALID_TRANSITIONS table must include all new SPEAKING_AND_LISTENING entries."""

    def test_speaking_to_speaking_and_listening(self):
        """SPEAKING -> SPEAKING_AND_LISTENING is a valid transition."""
        assert (
            ConversationState.SPEAKING_AND_LISTENING
            in VALID_TRANSITIONS[ConversationState.SPEAKING]
        )

    def test_speaking_and_listening_to_listening(self):
        """SPEAKING_AND_LISTENING -> LISTENING is a valid transition."""
        assert (
            ConversationState.LISTENING
            in VALID_TRANSITIONS[ConversationState.SPEAKING_AND_LISTENING]
        )

    def test_speaking_and_listening_to_speaking(self):
        """SPEAKING_AND_LISTENING -> SPEAKING is a valid transition (user stops quickly)."""
        assert (
            ConversationState.SPEAKING
            in VALID_TRANSITIONS[ConversationState.SPEAKING_AND_LISTENING]
        )

    def test_speaking_and_listening_to_idle(self):
        """SPEAKING_AND_LISTENING -> IDLE is a valid transition (stop/error recovery)."""
        assert (
            ConversationState.IDLE
            in VALID_TRANSITIONS[ConversationState.SPEAKING_AND_LISTENING]
        )

    def test_speaking_and_listening_to_processing_is_invalid(self):
        """SPEAKING_AND_LISTENING -> PROCESSING is NOT a valid transition.

        Must go through LISTENING first to avoid skipping STT.
        """
        assert (
            ConversationState.PROCESSING
            not in VALID_TRANSITIONS[ConversationState.SPEAKING_AND_LISTENING]
        )

    def test_valid_transitions_has_five_entries(self):
        """VALID_TRANSITIONS has exactly 5 entries — one per ConversationState."""
        assert len(VALID_TRANSITIONS) == 5


# ===========================================================================
# VOICE-02: ConversationStateMachine — actual transition execution
# ===========================================================================


class TestStateMachineTransitions:
    """State machine must execute SPEAKING_AND_LISTENING transitions correctly."""

    @pytest.mark.asyncio
    async def test_speaking_to_speaking_and_listening_transition(self):
        """State machine allows SPEAKING -> SPEAKING_AND_LISTENING transition."""
        machine = ConversationStateMachine()
        await _set_state_to_speaking(machine)

        result = await machine.transition_to(ConversationState.SPEAKING_AND_LISTENING)
        assert result is True
        assert machine.state == ConversationState.SPEAKING_AND_LISTENING

    @pytest.mark.asyncio
    async def test_speaking_and_listening_to_listening_transition(self):
        """State machine allows SPEAKING_AND_LISTENING -> LISTENING transition."""
        machine = ConversationStateMachine()
        await _set_state_to_speaking(machine)
        await machine.transition_to(ConversationState.SPEAKING_AND_LISTENING)

        result = await machine.transition_to(ConversationState.LISTENING)
        assert result is True
        assert machine.state == ConversationState.LISTENING

    @pytest.mark.asyncio
    async def test_speaking_and_listening_to_speaking_transition(self):
        """State machine allows SPEAKING_AND_LISTENING -> SPEAKING transition."""
        machine = ConversationStateMachine()
        await _set_state_to_speaking(machine)
        await machine.transition_to(ConversationState.SPEAKING_AND_LISTENING)

        result = await machine.transition_to(ConversationState.SPEAKING)
        assert result is True
        assert machine.state == ConversationState.SPEAKING

    @pytest.mark.asyncio
    async def test_speaking_and_listening_to_idle_transition(self):
        """State machine allows SPEAKING_AND_LISTENING -> IDLE transition."""
        machine = ConversationStateMachine()
        await _set_state_to_speaking(machine)
        await machine.transition_to(ConversationState.SPEAKING_AND_LISTENING)

        result = await machine.transition_to(ConversationState.IDLE)
        assert result is True
        assert machine.state == ConversationState.IDLE

    @pytest.mark.asyncio
    async def test_speaking_and_listening_to_processing_is_rejected(self):
        """State machine rejects SPEAKING_AND_LISTENING -> PROCESSING (invalid)."""
        machine = ConversationStateMachine()
        await _set_state_to_speaking(machine)
        await machine.transition_to(ConversationState.SPEAKING_AND_LISTENING)

        result = await machine.transition_to(ConversationState.PROCESSING)
        assert result is False
        # State must remain unchanged
        assert machine.state == ConversationState.SPEAKING_AND_LISTENING


# ===========================================================================
# VOICE-02 / VOICE-03: is_interruptible and barge_in()
# ===========================================================================


class TestIsInterruptible:
    """is_interruptible must return True for SPEAKING_AND_LISTENING."""

    @pytest.mark.asyncio
    async def test_is_interruptible_in_speaking_and_listening(self):
        """is_interruptible returns True when state is SPEAKING_AND_LISTENING."""
        machine = ConversationStateMachine()
        await _set_state_to_speaking(machine)
        await machine.transition_to(ConversationState.SPEAKING_AND_LISTENING)

        assert machine.is_interruptible is True

    @pytest.mark.asyncio
    async def test_is_interruptible_in_speaking(self):
        """is_interruptible still returns True in SPEAKING state."""
        machine = ConversationStateMachine()
        await _set_state_to_speaking(machine)

        assert machine.is_interruptible is True

    @pytest.mark.asyncio
    async def test_is_not_interruptible_in_listening(self):
        """is_interruptible returns False in LISTENING state."""
        machine = ConversationStateMachine()
        await machine.transition_to(ConversationState.LISTENING)

        assert machine.is_interruptible is False


class TestBargeIn:
    """barge_in() must work from SPEAKING_AND_LISTENING and invoke callbacks."""

    @pytest.mark.asyncio
    async def test_barge_in_from_speaking_and_listening_returns_true(self):
        """barge_in() returns True when state is SPEAKING_AND_LISTENING."""
        machine = ConversationStateMachine()
        await _set_state_to_speaking(machine)
        await machine.transition_to(ConversationState.SPEAKING_AND_LISTENING)

        result = await machine.barge_in()
        assert result is True

    @pytest.mark.asyncio
    async def test_barge_in_from_speaking_and_listening_transitions_to_listening(self):
        """barge_in() transitions to LISTENING when state is SPEAKING_AND_LISTENING."""
        machine = ConversationStateMachine()
        await _set_state_to_speaking(machine)
        await machine.transition_to(ConversationState.SPEAKING_AND_LISTENING)

        await machine.barge_in()
        assert machine.state == ConversationState.LISTENING

    @pytest.mark.asyncio
    async def test_barge_in_invokes_callbacks_from_speaking_and_listening(self):
        """barge_in() invokes registered barge-in callbacks from SPEAKING_AND_LISTENING."""
        machine = ConversationStateMachine()
        await _set_state_to_speaking(machine)
        await machine.transition_to(ConversationState.SPEAKING_AND_LISTENING)

        callback_called = []

        async def my_callback():
            callback_called.append(True)

        machine.add_barge_in_callback(my_callback)
        await machine.barge_in()

        assert len(callback_called) == 1, "Barge-in callback was not invoked"

    @pytest.mark.asyncio
    async def test_barge_in_from_idle_returns_false(self):
        """barge_in() returns False when state is IDLE (no-op)."""
        machine = ConversationStateMachine()
        result = await machine.barge_in()
        assert result is False


# ===========================================================================
# VOICE-03: LLM Generator — _cancelled flag reset and _generating flag
# ===========================================================================


class TestLLMGeneratorCancelReset:
    """LLMGenerator.generate_stream() must reset _cancelled and set _generating."""

    def _make_generator_with_mock_model(self):
        """Create LLMGenerator with mocked _ensure_model to avoid loading real model."""
        from ergos.llm.generator import LLMGenerator

        gen = LLMGenerator(model_path="/tmp/fake.gguf")

        # Build a mock Llama that yields one token then stops
        def _fake_stream(*args, **kwargs):
            yield {"choices": [{"text": "hello"}]}
            yield {"choices": [{"text": " world"}]}

        mock_model = MagicMock()
        mock_model.create_completion = MagicMock(side_effect=_fake_stream)

        # Patch _ensure_model to return our mock
        gen._ensure_model = MagicMock(return_value=mock_model)
        gen._model = mock_model  # Also set to avoid lazy load
        return gen

    @pytest.mark.asyncio
    async def test_generate_stream_resets_cancelled_flag(self):
        """generate_stream() resets _cancelled to False at the start."""
        gen = self._make_generator_with_mock_model()

        # Simulate that a previous barge-in left _cancelled = True
        gen._cancelled = True

        tokens = []
        async for token in gen.generate_stream("hello"):
            tokens.append(token)
            break  # Just check the first iteration

        # After generation starts, _cancelled must have been reset
        # We check by verifying tokens were produced (would be empty if not reset)
        assert len(tokens) > 0, "_cancelled was not reset — no tokens produced"

    @pytest.mark.asyncio
    async def test_generate_stream_sets_generating_flag(self):
        """generate_stream() sets _generating to True during streaming."""
        from ergos.llm.generator import LLMGenerator

        gen = LLMGenerator(model_path="/tmp/fake.gguf")

        # Track whether _generating was True during iteration
        generating_during = []

        real_done = threading.Event()

        def _fake_stream(*args, **kwargs):
            real_done.wait(timeout=5)  # Wait until test checks _generating
            yield {"choices": [{"text": "tok"}]}

        mock_model = MagicMock()
        mock_model.create_completion = MagicMock(side_effect=_fake_stream)
        gen._ensure_model = MagicMock(return_value=mock_model)
        gen._model = mock_model

        async def _collect():
            async for token in gen.generate_stream("hello"):
                generating_during.append(gen._generating)

        task = asyncio.create_task(_collect())
        # Give time for the task to start and for the thread to block in _fake_stream
        await asyncio.sleep(0.05)

        # At this point the thread is blocked in _fake_stream (before yielding)
        # _generating should be True
        assert gen._generating is True, "_generating was not set to True during stream"

        # Unblock the stream
        real_done.set()
        await task

    @pytest.mark.asyncio
    async def test_generate_stream_after_cancel_produces_tokens(self):
        """After cancel() + new generate_stream(), tokens are produced (cancel resets)."""
        gen = self._make_generator_with_mock_model()

        # Simulate a prior cancel
        gen._cancelled = True
        gen._generating = False

        tokens = []
        async for token in gen.generate_stream("continue please"):
            tokens.append(token)

        assert len(tokens) > 0, (
            "After cancel() + re-invoke, generate_stream() produced no tokens "
            "— _cancelled flag was not reset"
        )


# ===========================================================================
# VOICE-01: LatencyTracker — timestamps and P50 computation
# ===========================================================================


class TestLatencyTrackerTimestamps:
    """LatencyTracker must correctly record speech_end and first_audio timestamps."""

    def test_mark_speech_end_sets_waiting_for_audio(self):
        """mark_speech_end() sets is_waiting_for_audio to True."""
        tracker = LatencyTracker()
        assert tracker.is_waiting_for_audio is False

        tracker.mark_speech_end()
        assert tracker.is_waiting_for_audio is True

    def test_mark_first_audio_clears_waiting_flag(self):
        """mark_first_audio() clears is_waiting_for_audio after mark_speech_end()."""
        tracker = LatencyTracker()
        tracker.mark_speech_end()
        tracker.mark_first_audio()

        assert tracker.is_waiting_for_audio is False

    def test_mark_first_audio_records_latency_sample(self):
        """mark_first_audio() records a latency sample in metrics."""
        tracker = LatencyTracker()
        tracker.mark_speech_end()
        tracker.mark_first_audio()
        tracker.log_current()  # Commits the computed latency to metrics

        assert tracker.metrics.count == 1
        assert tracker.metrics.samples[0] >= 0

    def test_mark_first_audio_without_speech_end_is_noop(self):
        """mark_first_audio() without prior mark_speech_end() does not record."""
        tracker = LatencyTracker()
        tracker.mark_first_audio()  # Should be a no-op

        assert tracker.is_waiting_for_audio is False
        assert tracker.metrics.count == 0

    def test_latency_computed_is_positive(self):
        """Computed latency between speech_end and first_audio is positive."""
        import time

        tracker = LatencyTracker()
        tracker.mark_speech_end()
        time.sleep(0.001)  # 1 ms gap
        tracker.mark_first_audio()

        latency = tracker.compute_latency()
        assert latency is not None
        assert latency > 0


class TestLatencyMetricsP50:
    """LatencyMetrics.p50() must return the correct median."""

    def test_p50_of_three_samples(self):
        """p50() returns 200.0 for samples [100, 200, 300] (odd count)."""
        metrics = LatencyMetrics()
        metrics.record(100.0)
        metrics.record(200.0)
        metrics.record(300.0)

        assert metrics.p50() == 200.0

    def test_p50_of_four_samples(self):
        """p50() returns 250.0 for samples [100, 200, 300, 400] (even count → mean of middle two)."""
        metrics = LatencyMetrics()
        metrics.record(100.0)
        metrics.record(200.0)
        metrics.record(300.0)
        metrics.record(400.0)

        assert metrics.p50() == 250.0

    def test_p50_empty_returns_zero(self):
        """p50() returns 0.0 when no samples have been recorded."""
        metrics = LatencyMetrics()
        assert metrics.p50() == 0.0

    def test_p50_single_sample(self):
        """p50() returns the single sample value when count == 1."""
        metrics = LatencyMetrics()
        metrics.record(350.0)

        assert metrics.p50() == 350.0

    def test_p50_target_sub_300ms(self):
        """p50() is under 300 ms for simulated best-case latency samples."""
        # Simulating 10 fast responses around 250 ms
        metrics = LatencyMetrics()
        for latency in [240.0, 250.0, 255.0, 260.0, 248.0, 252.0, 245.0, 258.0, 262.0, 247.0]:
            metrics.record(latency)

        # P50 should be well under 300 ms target
        assert metrics.p50() < 300.0, f"P50 {metrics.p50()}ms exceeds 300ms target"
