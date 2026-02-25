---
status: fix_applied
trigger: "Server crashes with segmentation fault during TTS playback, even after previous fix"
created: 2026-01-28T14:30:00Z
updated: 2026-01-28T15:00:00Z
prior_fix: segfault-tts-audio.md
---

## Current Focus

hypothesis: Concurrent native library access (ONNX/llama-cpp/PyAV) during TTS streaming causes segfault
test: Review thread safety of native library calls and check for GIL release issues
expecting: Native libraries may not be thread-safe when called concurrently from async context
next_action: Add memory safety guards and investigate concurrent access patterns

## Symptoms (Pre-filled)

expected: Server runs without crashing during TTS playback, all audio plays to client
actual: Segmentation fault (core dumped) during TTS streaming. Crash occurs while TTS is synthesizing multiple sentences and incoming audio frames are still being processed.
errors: "Segmentation fault (core dumped)" and warning "Invalid transition: listening → speaking"
reproduction: Connect client, speak to trigger TTS response, crash occurs during TTS synthesis
timeline: Previous fix was attempted in .planning/debug/segfault-tts-audio.md (status: fixed) but issue persists

**Key log observations:**
1. State machine warning: "Invalid transition: listening → speaking" at 14:11:06
2. VAD speech ended, transition listening → processing at 14:11:07
3. STT transcribed: "What does this all look like?"
4. TTS synthesizing multiple sentences (14:11:07 - 14:11:10)
5. Incoming audio frames still being received during TTS
6. SEGFAULT at 14:11:10

## Prior Fix Analysis

The previous fix (segfault-tts-audio.md) addressed:
1. Memory view aliasing - samples array escaping lock scope
2. Non-contiguous array after reshape
3. Added `.copy()` and `np.ascontiguousarray()`

**Verified: Fix IS in the code** (git diff shows changes in working directory)

Changes present in audio_track.py:
- Line 107: `samples = all_samples[:self._samples_per_frame].copy()`
- Line 112: `self._buffer = [remaining.copy()]`
- Lines 132-133: `if not samples.flags['C_CONTIGUOUS']: samples = np.ascontiguousarray(samples)`

## Investigation Progress

### Checked and Eliminated

1. **Array contiguity in recv()** - Fix is applied correctly
2. **Array memory aliasing in buffer** - Fix is applied correctly
3. **frame.to_ndarray() use-after-free** - Returns copy, not view
4. **Incoming audio non-contiguous** - `np.clip().astype()` creates contiguous copy
5. **PyAV thread safety** - Tested, works with concurrent threads
6. **push_audio memory** - All operations create new arrays (np.repeat, astype)

### New Areas to Investigate

1. **State machine race condition**
   - "Invalid transition: listening → speaking" indicates:
   - TTS audio callback tried to call `start_speaking()`
   - But state was already LISTENING (user started speaking again)
   - TTS continued anyway despite failed transition
   - Could lead to resource conflicts

2. **Concurrent native library access**
   - Multiple native libraries running simultaneously:
     - ONNX Runtime (TTS synthesis) - may have internal threading
     - llama-cpp-python (LLM) - uses ThreadPoolExecutor
     - PyAV (AudioFrame creation) - native ffmpeg code
     - aiortc (WebRTC) - native code for RTP/audio
   - GIL release during native calls could allow corruption

3. **LLM generator threading issue**
   - `generate_stream()` creates stream in ThreadPoolExecutor
   - Then iterates the generator in main async thread
   - Could cause issues if llama-cpp releases GIL during iteration

## Evidence

### Evidence 1: State Race Condition in Pipeline

In `/home/vinay/ergos/src/ergos/pipeline.py` lines 237-239:
```python
if not _first_audio_sent[0]:
    _first_audio_sent[0] = True
    await state_machine.start_speaking()  # Return value NOT checked!
```

The return value of `start_speaking()` is ignored. Even if state transition fails,
audio is still pushed to the track. This could cause:
- Audio being pushed while user is speaking (state is LISTENING)
- Conflicting audio streams (incoming + outgoing simultaneously)

### Evidence 2: _first_audio_sent Reset Race

```python
async def on_vad_reset_audio_flag(event: VADEvent) -> None:
    if event.type == VADEventType.SPEECH_START:
        _first_audio_sent[0] = False  # Reset happens on speech start
```

If TTS is still generating when user speaks again:
1. SPEECH_START fires → `_first_audio_sent[0] = False`
2. TTS still running → next audio chunk → `start_speaking()` called again
3. State is LISTENING → Invalid transition
4. But audio still gets pushed → concurrent streams

### Evidence 3: Barge-in Disabled for Debugging

In `/home/vinay/ergos/src/ergos/transport/data_channel.py` lines 102-104:
```python
async def _handle_barge_in(self, data: dict) -> None:
    # TEMPORARILY DISABLED for STT debugging
    logger.info("Barge-in request received but DISABLED for debugging")
    # await self._state_machine.barge_in()
```

Barge-in is disabled, which means TTS is NOT stopped when user speaks.
This explains why TTS continues generating during incoming speech.

## Hypotheses

### Hypothesis A: TTS not stopped on barge-in (HIGH CONFIDENCE)
- Barge-in is disabled in data_channel.py
- When user speaks during TTS, the TTS keeps generating
- Two audio streams (incoming + outgoing) process simultaneously
- Native code in PyAV or aiortc may not handle this correctly

### Hypothesis B: ONNX Runtime threading conflict
- ONNX runtime uses internal threads for inference
- Concurrent TTS synthesis + other processing may conflict
- Need to check ONNX session options for thread safety

### Hypothesis C: AudioFrame concurrent access
- recv() creates AudioFrames from buffer
- push_audio() modifies buffer
- Even with lock, the numpy operations outside lock could conflict

## Resolution

root_cause: Multiple concurrent issues causing segfault

The segfault was caused by a combination of issues:

1. **Barge-in was disabled** - TTS continued generating even when user spoke again
2. **No state check before pushing audio** - Audio was pushed regardless of state
3. **TTS synthesis couldn't be cancelled** - Once started, synthesis ran to completion
4. **LLM stream blocked event loop** - Token iteration was synchronous, blocking async tasks

These issues combined meant that:
- TTS audio was generated and pushed while user was speaking (incoming audio)
- Multiple concurrent native library calls (PyAV, ONNX, llama-cpp, aiortc)
- Event loop starvation prevented proper async task scheduling
- Memory corruption from concurrent access to native resources

fix:
Applied 4 fixes to address the root causes:

### Fix 1: Re-enabled barge-in (data_channel.py)
```python
# Was: # await self._state_machine.barge_in()
# Now:
await self._state_machine.barge_in()
```

### Fix 2: State check before pushing audio (pipeline.py)
```python
# Only push audio if state is PROCESSING or SPEAKING
if current_state not in (ConversationState.PROCESSING, ConversationState.SPEAKING):
    logger.debug(f"TTS audio discarded: state is {current_state.value}")
    return
```

### Fix 3: TTS cancellation support (tts/processor.py)
Added `_cancelled` flag and methods:
- `cancel()` - Sets flag and clears buffer
- `reset_cancellation()` - Resets flag for new utterance
- `_synthesize_and_stream()` checks flag between chunks

### Fix 4: Async LLM streaming (llm/generator.py)
Changed from blocking iteration:
```python
# Was: for chunk in stream: yield token
# Now: Each chunk fetched via run_in_executor to avoid blocking
while True:
    chunk = await loop.run_in_executor(self._executor, get_next_chunk, stream_iter)
    if chunk is None: break
    yield token
```

files_changed:
- /home/vinay/ergos/src/ergos/transport/data_channel.py - Re-enabled barge-in
- /home/vinay/ergos/src/ergos/pipeline.py - State check, use TTS cancel()
- /home/vinay/ergos/src/ergos/tts/processor.py - Added cancellation support
- /home/vinay/ergos/src/ergos/llm/generator.py - Made stream iteration async

## Verification

To verify the fix:
1. Start server: `python -m ergos.cli serve`
2. Connect client and speak
3. While TTS is playing, speak again (barge-in)
4. Verify:
   - TTS stops (barge-in works)
   - No segfault occurs
   - New response is generated correctly
5. Test sustained conversation with overlapping speech/TTS
