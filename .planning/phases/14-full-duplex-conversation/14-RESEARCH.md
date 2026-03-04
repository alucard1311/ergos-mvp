# Phase 14: Full-Duplex Conversation - Research

**Researched:** 2026-03-03
**Domain:** Asyncio event-loop audio pipeline, WebRTC real-time conversation, state machine extension
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Barge-in sensitivity**
- Instant trigger on any detected speech — no minimum duration threshold
- Audio stops abruptly (cut mid-word), no fade-out
- Cancel everything on barge-in: both LLM generation and TTS synthesis stop immediately
- Keep existing Flutter barge-in gesture (CLIENT-UI-03) alongside new voice-based detection

**Overlap behavior**
- Brief overlap (~500ms): AI keeps talking for a short moment while starting to listen, then stops
- All speech treated as interruption — no backchannel detection (e.g., "mm-hmm" triggers interruption same as any speech)
- Echo cancellation handled client-side (Flutter) — rely on device's built-in AEC
- SPEAKING_AND_LISTENING is a visible state in Flutter client — orb shows unique animation (pulse + glow or similar)

**Post-interruption flow**
- AI remembers what it was saying — partial response stays in conversation history
- Silent transition — no verbal acknowledgment ("okay", "go ahead") after interruption
- Fully switch topics — user's new input takes priority, previous topic dropped
- Partial response kept in LLM context so AI knows what the user already heard

**Silence & turn-taking**
- Short VAD end-of-speech threshold (~500ms) for fast response
- Immediate start — begin speaking as soon as first TTS audio is ready, no artificial pause
- Timeout to idle after 30s of silence post-response
- Latency measured and logged using existing LatencyTracker infrastructure (P50/P95)

### Claude's Discretion
- Exact SPEAKING_AND_LISTENING state transition timing and edge cases
- STT/LLM/TTS pipeline optimizations to achieve sub-300ms target
- Audio buffer management during overlap period
- State machine transition validation rules for the new state
- Idle timeout implementation details

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VOICE-01 | User experiences zero awkward silence — sub-300ms from speech end to first AI audio (P50) | Latency bottleneck analysis: VAD→STT→LLM first-token→TTS first-chunk; existing LatencyTracker already measures this |
| VOICE-02 | User can talk while AI is speaking (full-duplex, SPEAKING_AND_LISTENING state) | New ConversationState enum value + transition rules + audio routing changes in on_incoming_audio and on_vad_for_state |
| VOICE-03 | User can interrupt mid-sentence and AI stops within 200ms | Uncomment on_barge_in; wire generator.cancel() + tts_processor.cancel() + track.clear() on SPEECH_START during SPEAKING_AND_LISTENING |
</phase_requirements>

---

## Summary

This phase activates full-duplex conversation by making three targeted changes to the existing Ergos pipeline: (1) adding a `SPEAKING_AND_LISTENING` state to the state machine, (2) enabling audio input and VAD processing while the AI is speaking, and (3) wiring the already-written but disabled barge-in cancellation path.

The codebase already contains all the necessary machinery. `ConversationStateMachine.barge_in()` exists and works. `LLMGenerator.cancel()`, `TTSProcessor.cancel()`, and `TTSAudioTrack.clear()` all exist. The barge-in wiring in `pipeline.py` lines 451-461 is commented out and ready to uncomment. The only new infrastructure needed is the `SPEAKING_AND_LISTENING` state enum value, its transition rules, and the Flutter orb animation for that state.

The 300ms P50 target is achievable without changing model inference — it is already the measured baseline for the system from Phase 13 context. The 200ms barge-in requirement is from `SPEECH_START` VAD event to AI audio stop (not from user intent), and is achievable because `track.clear()` is a synchronous buffer flush that takes ~1ms.

**Primary recommendation:** Activate the disabled barge-in path, add `SPEAKING_AND_LISTENING` state, modify the three audio-routing callbacks (`on_incoming_audio`, `on_vad_for_state`, `on_vad_reset_flags`), and update Flutter orb for the new state.

---

## Standard Stack

### Core (all already in the project)

| Component | File | Version | Role |
|-----------|------|---------|------|
| `ConversationStateMachine` | `src/ergos/state/machine.py` | v1 (existing) | State gating; has `barge_in()`, `_barge_in_callbacks` |
| `ConversationState` enum | `src/ergos/state/events.py` | v1 (existing) | Add `SPEAKING_AND_LISTENING = "speaking_and_listening"` |
| `LLMGenerator` | `src/ergos/llm/generator.py` | v1 (existing) | Has `cancel()` method (sets `_cancelled` flag) |
| `TTSProcessor` | `src/ergos/tts/processor.py` | v1 (existing) | Has `cancel()` (sets flag), `clear_buffer()`, `reset_cancellation()` |
| `TTSAudioTrack` | `src/ergos/transport/audio_track.py` | v1 (existing) | Has `clear()` — thread-safe buffer flush |
| `LatencyTracker` | `src/ergos/metrics.py` | v1 (existing) | Already measures speech_end → first_audio; P50/P95 |
| `VADProcessor` | `src/ergos/audio/vad.py` | v1 (existing) | Fires `SPEECH_START` / `SPEECH_END` events |
| `DataChannelHandler` | `src/ergos/transport/data_channel.py` | v1 (existing) | Broadcasts state to Flutter; already handles `barge_in` message type |

### Supporting (Flutter client)

| Component | File | Role |
|-----------|------|------|
| `ErgosOrb` | `client/lib/widgets/ergos_orb.dart` | Needs `SPEAKING_AND_LISTENING` case in `_updateForState` and `_colorForState` |
| `_sendBargeIn()` | `client/lib/main.dart:141` | Currently only sends on tap in `SPEAKING` — extend guard to include `SPEAKING_AND_LISTENING` |
| WebRTC data channel | `client/lib/services/webrtc_service.dart` | No change needed — already receives `state_change` messages and routes to `onServerStateChanged` |

---

## Architecture Patterns

### Recommended State Transition Graph

```
IDLE ──► LISTENING ──► PROCESSING ──► SPEAKING
  ▲          ▲               │             │
  │          │   (barge-in)  │   (barge-in / speech_start)
  │          └───────────────┘             │
  │                                        │
  │                               SPEAKING_AND_LISTENING
  │                                        │
  │          (speech_end → full barge-in)  │
  └──────────────────────────────────────◄─┘
```

**New transitions to add to `VALID_TRANSITIONS`:**

```python
# Additions only — existing entries unchanged
ConversationState.SPEAKING: {
    ConversationState.LISTENING,          # TTS complete or gesture barge-in (existing)
    ConversationState.IDLE,               # Stop (existing)
    ConversationState.SPEAKING_AND_LISTENING,  # NEW: voice detected while speaking
},
ConversationState.SPEAKING_AND_LISTENING: {
    ConversationState.LISTENING,          # NEW: speech_end → full barge-in
    ConversationState.SPEAKING,           # NEW: speech_end → no interruption (user stopped quickly)
    ConversationState.IDLE,               # NEW: stop / error recovery
},
```

### Pattern 1: SPEAKING → SPEAKING_AND_LISTENING Transition

**What:** When `SPEECH_START` VAD event fires while in `SPEAKING` state, transition to `SPEAKING_AND_LISTENING`. AI audio continues for ~500ms overlap, then barge-in is fully executed when `SPEECH_END` fires (or immediately via a 500ms timer, whichever comes first).

**The 500ms overlap window:** After transitioning to `SPEAKING_AND_LISTENING`, schedule an `asyncio.get_event_loop().call_later(0.5, _execute_barge_in)`. If `SPEECH_END` fires before the timer, cancel the timer and execute barge-in immediately from the `SPEECH_END` handler.

**Decision from CONTEXT.md:** The CONTEXT.md states "Brief overlap (~500ms): AI keeps talking for a short moment while starting to listen, then stops." This means the 500ms is AI audio overlap — NOT a threshold before barge-in fires. Barge-in (cancel LLM+TTS+audio) executes after the overlap period.

**Implementation in `on_vad_for_state`:**
```python
async def on_vad_for_state(event: VADEvent) -> None:
    current_state = state_machine.state

    if event.type == VADEventType.SPEECH_START:
        if current_state in (ConversationState.IDLE, ConversationState.LISTENING):
            await state_machine.start_listening()
        elif current_state == ConversationState.SPEAKING:
            # Transition to SPEAKING_AND_LISTENING (AI keeps talking ~500ms)
            await state_machine.transition_to(
                ConversationState.SPEAKING_AND_LISTENING,
                metadata={"trigger": "speech_start_during_speaking"}
            )
            # Schedule barge-in after overlap window
            _schedule_barge_in_after_overlap()

    elif event.type == VADEventType.SPEECH_END:
        if current_state in (
            ConversationState.LISTENING,
            ConversationState.SPEAKING_AND_LISTENING,
        ):
            if current_state == ConversationState.SPEAKING_AND_LISTENING:
                # Execute barge-in now (cancel LLM+TTS+audio), then transition
                await _execute_barge_in()
            await state_machine.start_processing()
```

### Pattern 2: Barge-in Execution (the core cancel sequence)

**Correct order matters** — cancel in this sequence to avoid race conditions:

```python
async def _execute_barge_in() -> None:
    """Cancel all AI output and clear buffers. Called from on_barge_in callback."""
    logger.info("Barge-in: executing cancel sequence")

    # 1. Cancel LLM generation (sets flag, generation loop sees it next iteration)
    generator.cancel()

    # 2. Cancel TTS synthesis (sets flag, synthesis loop sees it next chunk)
    await tts_processor.cancel()  # This also clears _buffer and yields to event loop

    # 3. Clear audio track buffers for all connections (immediate, thread-safe)
    for pc in list(connection_manager._connections):
        track = connection_manager.get_track(pc)
        if track is not None:
            track.clear()

    logger.info("Barge-in: cancel sequence complete")
```

**Register with state machine:**
```python
state_machine.add_barge_in_callback(_execute_barge_in)
```

This is what the commented-out code in `pipeline.py:451-461` was trying to do — it just needs uncommenting and updating to also call `generator.cancel()`.

### Pattern 3: Audio Routing in SPEAKING_AND_LISTENING

Two pipeline callbacks must accept the new state:

**`on_incoming_audio` (pipeline.py:609-648)** — currently returns early for non-IDLE/LISTENING states. Add `SPEAKING_AND_LISTENING` to the allowed set:
```python
if current_state not in (
    ConversationState.IDLE,
    ConversationState.LISTENING,
    ConversationState.SPEAKING_AND_LISTENING,  # ADD
):
    return
```

**`on_vad_for_state` (pipeline.py:280-296)** — currently ignores VAD in `PROCESSING` and `SPEAKING`. Add `SPEAKING_AND_LISTENING` handling as shown in Pattern 1.

**`on_tts_audio` (pipeline.py:373-429)** — currently only pushes audio in `PROCESSING` or `SPEAKING`. During `SPEAKING_AND_LISTENING`, audio should still play for the 500ms overlap window. Add `SPEAKING_AND_LISTENING` to the allowed set:
```python
if current_state not in (
    ConversationState.PROCESSING,
    ConversationState.SPEAKING,
    ConversationState.SPEAKING_AND_LISTENING,  # ADD — overlap window
):
    logger.debug(f"TTS audio discarded: state is {current_state.value}")
    return
```

### Pattern 4: Idle Timeout After Response

After the AI completes speaking and transitions to `IDLE` via `on_llm_complete`, an idle timeout timer should be set. If no speech is detected in 30s, reset to `IDLE` (which it already is, so this is a no-op). The timeout is needed to clear any "post-response listening" state. Simplest implementation: an `asyncio.Task` started when `on_llm_complete` fires, cancelled on the next `SPEECH_START`.

```python
_idle_timeout_task: Optional[asyncio.Task] = None

async def _idle_timeout_handler() -> None:
    await asyncio.sleep(30.0)
    if state_machine.state == ConversationState.IDLE:
        logger.debug("Idle timeout: already IDLE, no action needed")
    elif state_machine.state == ConversationState.LISTENING:
        logger.info("Idle timeout: 30s without speech, resetting to IDLE")
        await state_machine.stop()
```

### Pattern 5: Partial Response in History

When barge-in fires mid-generation, `LLMGenerator.cancel()` sets a flag, but `LLMProcessor.process_transcription()` still accumulates `full_response` until generation stops. The partial text already gets appended to `_history` by the existing code path in `LLMProcessor.process_transcription()` (line 90: `self._history.append(Message(role="assistant", content=full_response))`).

This means partial response preservation is **already handled** by the existing architecture — no special work needed. The LLM context will contain the partial response when the next user utterance is processed.

### Pattern 6: Reset Flags on New Utterance After Barge-in

After barge-in, the `_first_audio_sent` flag must be reset so the next TTS response properly triggers the `SPEAKING` transition. This is already handled in `on_vad_reset_flags` (pipeline.py:431-445) for `SPEECH_END` — but needs to also reset `tts_processor.reset_cancellation()` after barge-in.

The cleanest location is in `_execute_barge_in()` itself — do NOT call `reset_cancellation()` there (that would re-enable synthesis during the barge-in window). Call it in the `SPEECH_END` handler after barge-in transitions to `PROCESSING`, or reuse the existing `on_vad_reset_flags` callback which already calls `reset_cancellation()` on `SPEECH_START` for IDLE/LISTENING states. Add `SPEAKING_AND_LISTENING` to that guard.

### Flutter Orb: SPEAKING_AND_LISTENING State

The `ErgosOrb` widget uses a `switch` on `serverState` string. The new state string `"speaking_and_listening"` needs:
1. A new `case 'speaking_and_listening':` in `_updateForState()` — use a dual animation (fast pulse + glow) to suggest simultaneous output and input.
2. A new `case 'speaking_and_listening':` in `_colorForState()` — use a cyan/teal color distinct from `SPEAKING` (green) and `LISTENING` (blue).
3. Tappable during `speaking_and_listening` (same as `SPEAKING`) — update `onTap` guard in `build()`.
4. Update `_sendBargeIn()` guard in `main.dart` to include `'speaking_and_listening'`.

**Suggested animation:** Use a second `AnimationController` with a faster period (400ms) layered over the existing scale animation, or use `_controller.repeat(period: const Duration(milliseconds: 400))` to get a rapid pulse that visually distinguishes this state.

### Anti-Patterns to Avoid

- **Calling `generator.cancel()` and waiting for generation to stop before clearing audio buffers.** The LLM cancel is a flag — generation continues for 1-2 more tokens before the thread checks it. Clear audio buffers immediately and independently.
- **Resetting `_cancelled` flag inside `_execute_barge_in()`.** Call `reset_cancellation()` only when a new response starts (on `SPEECH_START` for a new utterance), not at barge-in time.
- **Adding SPEECH_START → PROCESSING transition from SPEAKING_AND_LISTENING.** The correct flow is SPEECH_START → SPEAKING_AND_LISTENING, then SPEECH_END → execute barge-in → PROCESSING.
- **Waiting for synthesis lock release before executing barge-in.** The cancellation flag approach bypasses the lock — `_cancelled = True` is seen at the next chunk boundary without needing the lock.
- **Calling `state_machine.barge_in()` from the VAD callback.** The existing `barge_in()` method transitions SPEAKING → LISTENING, skipping PROCESSING. For voice-triggered barge-in, drive the state transitions directly in `on_vad_for_state` to support the new SPEAKING_AND_LISTENING intermediate step.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread-safe audio buffer clear | Custom locking | `TTSAudioTrack.clear()` | Already has `threading.Lock`, handles edge cases |
| TTS synthesis interruption | Async task cancellation | `TTSProcessor.cancel()` | Handles lock, flag, and event-loop yield correctly |
| LLM generation interruption | Thread join / queue flush | `LLMGenerator.cancel()` | Sets `_cancelled` flag checked per-token |
| State broadcast to Flutter | Custom WebSocket | `DataChannelHandler.broadcast_state_change()` | Already wired; handles channel readyState check |
| VAD event routing | Custom WebRTC data channel parser | Existing `VADProcessor.process_raw_event()` | Handles all VAD event types |
| Latency measurement | Custom timer | `LatencyTracker` with `mark_speech_end()` / `mark_first_audio()` | P50/P95 already computed |

**Key insight:** Every piece of cancellation and audio management machinery already exists. This phase is wiring activation, not building new infrastructure.

---

## Common Pitfalls

### Pitfall 1: `is_interruptible` Check in Existing `barge_in()`

**What goes wrong:** `ConversationStateMachine.barge_in()` (machine.py:183-217) checks `self._state == ConversationState.SPEAKING` as a guard. After adding `SPEAKING_AND_LISTENING`, the old Flutter gesture barge-in path (`_handle_barge_in` in data_channel.py) will call `state_machine.barge_in()`, which will return `False` if state is `SPEAKING_AND_LISTENING` (voice barge-in already moved state there).

**Why it happens:** The gesture path and the voice path can race. If the user taps while voice barge-in is already in progress, state is `SPEAKING_AND_LISTENING` and the existing `barge_in()` method ignores it.

**How to avoid:** Update `ConversationStateMachine.barge_in()` to also handle `SPEAKING_AND_LISTENING → LISTENING` transition. Or: add `SPEAKING_AND_LISTENING` to the `is_interruptible` property check.

**Warning signs:** Flutter tap-to-barge-in stops working after adding new state.

### Pitfall 2: `_first_audio_sent` Flag Stuck After Barge-in

**What goes wrong:** After barge-in, if `_first_audio_sent[0]` is `True` from the cancelled response, the next response will never call `state_machine.start_speaking()` and the orb stays stuck in `PROCESSING`.

**Why it happens:** `on_vad_reset_flags` resets `_first_audio_sent[0] = False` on `SPEECH_END`. But barge-in may occur without a clean `SPEECH_END` sequence if the state machine transitions bypass normal `SPEECH_END` handling.

**How to avoid:** Also reset `_first_audio_sent[0] = False` inside `_execute_barge_in()` after cancellation. This is safe because barge-in means "start fresh."

**Warning signs:** AI appears to process (PROCESSING state) but never transitions to SPEAKING after barge-in.

### Pitfall 3: LLM Generator Cancel Flag Not Reset

**What goes wrong:** `LLMGenerator.cancel()` sets `self._cancelled = True`. But `generate_stream()` does NOT reset this flag before starting a new generation. A cancelled generator will silently produce no tokens on the next invocation.

**Why it happens:** `cancel()` is a one-way flag with no automatic reset. The existing comment-out of barge-in code means this code path was never exercised.

**How to avoid:** Reset `generator._cancelled = False` and `generator._generating` at the start of `generate_stream()`, OR add a `reset()` method and call it at the start of each `process_transcription()` call. Check generator code at line 201: `cancel()` sets `_cancelled = True` but `generate_stream()` does not reset it.

**Warning signs:** After first barge-in, all subsequent LLM calls produce empty responses. STT works (transcription logs appear), but no tokens ever reach TTS.

### Pitfall 4: VAD Events During 500ms Overlap Window

**What goes wrong:** During `SPEAKING_AND_LISTENING`, if `SPEECH_END` fires very quickly (user said one short word), the overlap timer fires ~500ms later after the state has already moved to `PROCESSING`. The timer callback calls `_execute_barge_in()` on the wrong state.

**Why it happens:** `asyncio.call_later` callbacks are not automatically cancelled.

**How to avoid:** Track the overlap timer handle and cancel it in the `SPEECH_END` handler. Check current state before executing barge-in in the timer callback.

```python
_overlap_timer_handle: Optional[asyncio.Handle] = None

def _schedule_barge_in_after_overlap():
    nonlocal _overlap_timer_handle
    loop = asyncio.get_event_loop()
    _overlap_timer_handle = loop.call_later(0.5, lambda: asyncio.ensure_future(_execute_barge_in()))

def _cancel_overlap_timer():
    nonlocal _overlap_timer_handle
    if _overlap_timer_handle is not None:
        _overlap_timer_handle.cancel()
        _overlap_timer_handle = None
```

**Warning signs:** Barge-in appears to fire twice; second AI response is immediately cancelled; OR barge-in fires after user has already stopped speaking.

### Pitfall 5: TTS Synthesis Lock Blocks Audio Drain

**What goes wrong:** `TTSProcessor._synthesis_lock` serializes all synthesis calls. If a large sentence is in synthesis when barge-in fires, the lock is held by the synthesis thread (via `asyncio.Lock` — actually it's in the same event loop). The cancel flag is checked per-chunk, not before acquiring the lock.

**Why it happens:** The synthesis loop checks `_cancelled` after acquiring the lock at line 124: `if self._cancelled: return`. But the lock must be awaited first. If synthesis is in the middle of a 2-second sentence chunk (Kokoro streams incrementally, so this is rare but possible), the caller waits.

**How to avoid:** The Kokoro synthesizer already streams in small chunks (`synthesize_stream` is an async generator). The `_cancelled` check on line 123 fires after each chunk. Each chunk is ~50-100ms of audio. So maximum delay before cancellation is one chunk duration (~100ms). This is within the 200ms barge-in budget. No additional changes needed.

**Warning signs:** Barge-in takes >200ms to stop audio in rare cases with long sentences. Monitor chunk sizes in TTS logs.

### Pitfall 6: Flutter State String Mismatch

**What goes wrong:** Server broadcasts `"speaking_and_listening"` (Python enum: `ConversationState.SPEAKING_AND_LISTENING = "speaking_and_listening"`). Flutter `_updateForState()` has no case for this string, falls through to `default:` which stops the animation. Orb appears frozen.

**Why it happens:** The Flutter client does a string switch — any unrecognized state hits the default case.

**How to avoid:** Add the case before implementing server-side state. Test with a manual state broadcast first.

**Warning signs:** Orb stops animating during barge-in overlap window despite active conversation.

---

## Code Examples

### Example 1: Adding SPEAKING_AND_LISTENING to State Machine

```python
# src/ergos/state/events.py
class ConversationState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    SPEAKING_AND_LISTENING = "speaking_and_listening"  # ADD: full-duplex overlap state
```

```python
# src/ergos/state/machine.py — VALID_TRANSITIONS additions
VALID_TRANSITIONS: dict[ConversationState, set[ConversationState]] = {
    ConversationState.IDLE: {
        ConversationState.LISTENING,
    },
    ConversationState.LISTENING: {
        ConversationState.PROCESSING,
        ConversationState.IDLE,
    },
    ConversationState.PROCESSING: {
        ConversationState.SPEAKING,
        ConversationState.LISTENING,
    },
    ConversationState.SPEAKING: {
        ConversationState.LISTENING,
        ConversationState.IDLE,
        ConversationState.SPEAKING_AND_LISTENING,   # NEW
    },
    ConversationState.SPEAKING_AND_LISTENING: {     # NEW
        ConversationState.LISTENING,
        ConversationState.SPEAKING,
        ConversationState.IDLE,
    },
}
```

Also update `barge_in()` method to handle the new state:
```python
async def barge_in(self) -> bool:
    if self._state in (
        ConversationState.SPEAKING,
        ConversationState.SPEAKING_AND_LISTENING,   # ADD
    ):
        for callback in self._barge_in_callbacks:
            try:
                await callback()
            except Exception as e:
                logger.error(f"Barge-in callback error: {e}")
        await self.transition_to(
            ConversationState.LISTENING,
            metadata={"trigger": "barge_in"}
        )
        logger.info(f"Barge-in: interrupted {self._state.value}, now listening")
        return True
    elif self._state == ConversationState.PROCESSING:
        await self.transition_to(
            ConversationState.LISTENING,
            metadata={"trigger": "barge_in"}
        )
        logger.info("Barge-in: interrupted processing, now listening")
        return True
    return False
```

### Example 2: on_barge_in Callback (uncomment + extend in pipeline.py)

```python
# pipeline.py — replace the commented-out block at lines 451-461
async def on_barge_in() -> None:
    """Cancel LLM generation, TTS synthesis, and clear audio buffers on barge-in.

    Called by state_machine.barge_in() before transitioning to LISTENING.
    Execution order matters: cancel flag must be set before clearing buffers
    to prevent re-queuing of audio by still-running synthesis.
    """
    logger.info("Barge-in: executing cancel sequence")

    # 1. Cancel LLM (flag-based, generation stops at next token check)
    generator.cancel()

    # 2. Cancel TTS (flag-based + clears text buffer, yields to event loop)
    await tts_processor.cancel()

    # 3. Reset _first_audio_sent so next response triggers SPEAKING transition
    _first_audio_sent[0] = False

    # 4. Clear audio track buffers (thread-safe, immediate)
    for pc in list(connection_manager._connections):
        track = connection_manager.get_track(pc)
        if track is not None:
            track.clear()

    logger.info("Barge-in: cancel sequence complete")

state_machine.add_barge_in_callback(on_barge_in)
logger.debug("Barge-in callback wired: LLM cancel + TTS cancel + track clear")
```

### Example 3: Modified on_vad_for_state (pipeline.py)

```python
_overlap_timer_handle: Optional[asyncio.Handle] = None

async def on_vad_for_state(event: VADEvent) -> None:
    nonlocal _overlap_timer_handle
    current_state = state_machine.state

    if event.type == VADEventType.SPEECH_START:
        if current_state in (ConversationState.IDLE, ConversationState.LISTENING):
            await state_machine.start_listening()

        elif current_state == ConversationState.SPEAKING:
            # Transition to full-duplex overlap state; AI audio continues briefly
            success = await state_machine.transition_to(
                ConversationState.SPEAKING_AND_LISTENING,
                metadata={"trigger": "speech_start_during_speaking"}
            )
            if success:
                # Schedule barge-in after ~500ms overlap window
                loop = asyncio.get_event_loop()
                _overlap_timer_handle = loop.call_later(
                    0.5,
                    lambda: asyncio.ensure_future(state_machine.barge_in())
                )
                logger.debug("SPEAKING_AND_LISTENING: 500ms overlap timer started")

        else:
            logger.debug(f"Ignoring SPEECH_START in state {current_state.value}")

    elif event.type == VADEventType.SPEECH_END:
        # Cancel overlap timer if it's pending (SPEECH_END fires before 500ms)
        if _overlap_timer_handle is not None:
            _overlap_timer_handle.cancel()
            _overlap_timer_handle = None
            logger.debug("SPEAKING_AND_LISTENING: overlap timer cancelled by SPEECH_END")

        if current_state == ConversationState.SPEAKING_AND_LISTENING:
            # User stopped speaking — execute barge-in now and start processing
            await state_machine.barge_in()  # Cancels LLM+TTS, transitions to LISTENING
            await state_machine.start_processing()

        elif current_state in (ConversationState.LISTENING,):
            await state_machine.start_processing()
```

### Example 4: LLM Generator Reset (fix for Pitfall 3)

The current `generate_stream()` does not reset the cancelled flag. Add a reset at the start:

```python
# src/ergos/llm/generator.py — modify generate_stream()
async def generate_stream(self, prompt: str, config=None) -> AsyncIterator[str]:
    # Reset cancellation state for new generation
    self._cancelled = False   # ADD THIS LINE
    self._generating = True   # ADD THIS LINE (set before submitting to executor)
    ...
    # (rest of existing implementation)
```

Or add a dedicated `reset()` method and call it from `LLMProcessor.process_transcription()`:
```python
def reset(self) -> None:
    """Reset cancellation flag for new generation."""
    self._cancelled = False
    self._generating = False
```

### Example 5: Flutter Orb SPEAKING_AND_LISTENING State (Dart)

```dart
// client/lib/widgets/ergos_orb.dart

// In _updateForState():
case 'speaking_and_listening':
  // Fast pulse to indicate simultaneous speaking + listening
  _controller.repeat(
    reverse: true,
    period: const Duration(milliseconds: 400),
  );
  break;

// In _colorForState() normal mode:
case 'speaking_and_listening':
  return const Color(0xFF06B6D4); // Cyan — distinct from green (SPEAKING) and blue (LISTENING)

// In build() — make tappable during this state too:
onTap: (widget.serverState == 'SPEAKING' || widget.serverState == 'speaking_and_listening')
    ? widget.onBargeIn
    : null,
```

```dart
// client/lib/main.dart — update _sendBargeIn() guard:
void _sendBargeIn() {
  if (_serverState == 'SPEAKING' || _serverState == 'speaking_and_listening') {
    _webRTCService.sendDataChannelMessage({
      'type': 'barge_in',
      'timestamp': DateTime.now().millisecondsSinceEpoch / 1000,
    });
  }
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Half-duplex (SPEAKING blocks LISTENING) | Full-duplex via SPEAKING_AND_LISTENING state | Phase 14 | Natural interruption |
| Barge-in disabled (pipeline.py:451) | Barge-in active with LLM+TTS+audio cancel | Phase 14 | AI stops within 200ms |
| No idle timeout | 30s post-response idle timeout | Phase 14 | Clean state management |
| TTS completes before IDLE | Immediate cancel on barge-in | Phase 14 | Responsive interruption |

**Currently disabled/not-yet-activated:**
- `on_barge_in` callback (pipeline.py:451-461): Commented out — activate in this phase
- `SPEAKING_AND_LISTENING` state: Does not exist yet in enum or transition table

---

## Open Questions

1. **500ms overlap: call_later vs dedicated asyncio.Task**
   - What we know: `loop.call_later()` schedules a synchronous callback; to call async code it needs `asyncio.ensure_future()`. A `asyncio.Task` with `asyncio.sleep(0.5)` is more cancellable.
   - What's unclear: Whether `call_later` + `ensure_future` is clean enough, or if a tracked Task is cleaner for cancellation.
   - Recommendation: Use `asyncio.create_task(asyncio.sleep(0.5))` with `.cancel()` for clean cancellation. Store as `_overlap_timer_task`.

2. **LLM cancel flag reset location**
   - What we know: `LLMGenerator.cancel()` sets `_cancelled = True`; `generate_stream()` does not reset it.
   - What's unclear: Whether resetting inside `generate_stream()` is safe or if `LLMProcessor.process_transcription()` is a better location.
   - Recommendation: Add `generator._cancelled = False` at the top of `generate_stream()` — it's the safest location since it's called per-generation.

3. **VAD redemptionFrames and 500ms speech_end threshold**
   - What we know: The Flutter VAD service uses `redemptionFrames: 45` (~1.4s) — this is the time after speech stops before `SPEECH_END` fires. The CONTEXT.md says "short VAD end-of-speech threshold (~500ms)".
   - What's unclear: Whether to change `redemptionFrames` from 45 to ~16 (16 * 32ms = 512ms ≈ 500ms) for faster response, or leave it at 1.4s.
   - Recommendation: Reduce `redemptionFrames` to 16 (512ms) in `vad_service.dart` to hit the 500ms end-of-speech target. This is a Flutter client change within scope.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, `pythonpath = ["src"]` |
| Quick run command | `python3 -m pytest tests/unit/test_full_duplex.py -x -q` |
| Full suite command | `python3 -m pytest tests/unit/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VOICE-01 | sub-300ms speech_end → first_audio (P50) | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_latency_tracker_p50 -x` | ❌ Wave 0 |
| VOICE-02 | SPEAKING_AND_LISTENING state exists in enum | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_speaking_and_listening_state_exists -x` | ❌ Wave 0 |
| VOICE-02 | Valid transitions to/from SPEAKING_AND_LISTENING | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_state_transitions_speaking_and_listening -x` | ❌ Wave 0 |
| VOICE-02 | on_incoming_audio passes audio in SPEAKING_AND_LISTENING | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_audio_routing_speaking_and_listening -x` | ❌ Wave 0 |
| VOICE-03 | Barge-in cancels LLM + TTS + audio track | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_barge_in_cancel_sequence -x` | ❌ Wave 0 |
| VOICE-03 | barge_in() works from SPEAKING_AND_LISTENING | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_barge_in_from_speaking_and_listening -x` | ❌ Wave 0 |
| VOICE-03 | LLMGenerator.cancel() flag resets on new generation | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_llm_generator_cancel_reset -x` | ❌ Wave 0 |
| All | SPEAKING_AND_LISTENING state transition log correctness | unit | `python3 -m pytest tests/unit/test_full_duplex.py -x -q` | ❌ Wave 0 |

Note: VOICE-01 (sub-300ms P50) cannot be automatically validated in isolation — it depends on real model inference timing. The unit test validates that LatencyTracker correctly measures and computes P50. The actual 300ms target requires end-to-end integration testing (manual-only with live models).

### Sampling Rate

- **Per task commit:** `python3 -m pytest tests/unit/test_full_duplex.py -x -q`
- **Per wave merge:** `python3 -m pytest tests/unit/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/unit/test_full_duplex.py` — covers all VOICE-01/02/03 unit tests listed above
- [ ] No conftest changes needed — existing `tests/unit/` pattern (no shared fixtures) applies

---

## Sources

### Primary (HIGH confidence)

- Codebase direct inspection — `src/ergos/state/machine.py` (ConversationStateMachine, barge_in, VALID_TRANSITIONS)
- Codebase direct inspection — `src/ergos/state/events.py` (ConversationState enum)
- Codebase direct inspection — `src/ergos/pipeline.py` (wiring pattern, commented on_barge_in lines 451-461)
- Codebase direct inspection — `src/ergos/tts/processor.py` (cancel, clear_buffer, reset_cancellation, synthesis lock)
- Codebase direct inspection — `src/ergos/llm/generator.py` (cancel flag, generate_stream, _cancelled not reset)
- Codebase direct inspection — `src/ergos/transport/audio_track.py` (TTSAudioTrack.clear() thread safety)
- Codebase direct inspection — `src/ergos/metrics.py` (LatencyTracker existing implementation)
- Codebase direct inspection — `client/lib/widgets/ergos_orb.dart` (state string switch, AnimationController)
- Codebase direct inspection — `client/lib/main.dart` (_sendBargeIn, _serverState, serverState == 'SPEAKING' guard)
- Codebase direct inspection — `client/lib/services/vad_service.dart` (redemptionFrames=45, positiveSpeechThreshold=0.6)
- Codebase direct inspection — `client/lib/services/webrtc_service.dart` (state_change data channel message routing)
- Codebase direct inspection — `14-CONTEXT.md` (locked decisions, specifics)

### Secondary (MEDIUM confidence)

- Python asyncio documentation (loop.call_later vs asyncio.create_task for cancellable timers) — well-established behavior
- aiortc threading model — TTSAudioTrack uses `threading.Lock` correctly per buffer access pattern

### Tertiary (LOW confidence)

- None — all findings are directly code-verified from the codebase

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all components read directly from source
- Architecture: HIGH — transition table and callback wiring read from source; patterns derived from existing code structure
- Pitfalls: HIGH — each pitfall is grounded in a specific line of code (e.g., `generate_stream()` not resetting `_cancelled`, `on_incoming_audio` SPEAKING guard, etc.)
- Flutter changes: HIGH — orb code read directly; state string switch verified

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable codebase — 30 day window)
