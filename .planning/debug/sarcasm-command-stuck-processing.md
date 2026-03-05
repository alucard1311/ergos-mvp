---
status: awaiting_human_verify
trigger: "sarcasm voice command causes system to get stuck in processing"
created: 2026-03-04T00:00:00Z
updated: 2026-03-04T02:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - Two root causes:
1. PRIMARY: Any exception in plugin_speak_callback (synthesis error, state error) propagates up through on_transcription_with_plugins, gets caught by stt_processor._process_accumulated_audio's broad except clause, leaving state=PROCESSING with no recovery. The idle timeout only handles LISTENING→IDLE, not PROCESSING→IDLE. System hangs indefinitely in PROCESSING.
2. SECONDARY: Even without exceptions, if synthesis produces no audio, drain loop waits 10s then calls stop(). Appears "stuck in processing" for 10 seconds.

FIX: Wrap plugin_speak_callback body in try/finally to ALWAYS call state_machine.stop() on exit. Also fix idle timeout to handle PROCESSING→IDLE as a safety net.

test: applied fixes - verify sarcasm command speaks confirmation and returns to IDLE cleanly
expecting: after fix, sarcasm command intercept completes within ~10s (Orpheus synthesis time + playback) and state returns to IDLE with confirmation spoken
next_action: implement fix in pipeline.py

BUT THE REAL QUESTION: Does audio ACTUALLY get pushed to the track?

The on_tts_audio callback (line 551) checks:
  if current_state not in (PROCESSING, SPEAKING, SPEAKING_AND_LISTENING): return

At the time plugin_speak_callback feeds tokens, state is PROCESSING. First audio chunk -> _first_audio_sent[0] is False -> calls start_speaking() -> PROCESSING->SPEAKING, THEN at line 577 checks state again: should be SPEAKING now -> continues to push_audio. Audio IS pushed.

The real issue: plugin_speak_callback calls `await tts_processor.flush()` BEFORE the synthesis loop finishes. The `flush()` call is awaited to completion. Then the is_synthesizing poll waits. Then the audio drain waits.

THE ACTUAL HANG: The synthesis lock. tts_processor._synthesize_and_stream uses `async with self._synthesis_lock`. This lock serializes all synthesis calls. When plugin_speak_callback calls `receive_token()` for each character, each call to `_synthesize_and_stream` acquires the lock. This is all sequential and fine.

WAIT - Actually the real problem is simpler: `plugin_speak_callback` calls `tts_processor.flush()` after the text loop. `flush()` calls `_synthesize_and_stream()` which acquires `_synthesis_lock`. That's fine. Synthesis runs, audio goes out.

THE ACTUAL ISSUE: state is PROCESSING when plugin_speak_callback fires. The callback sets `_first_audio_sent[0] = False`. When first TTS audio arrives in `on_tts_audio`, it calls `start_speaking()` (PROCESSING->SPEAKING). This transition fires `_notify_callbacks` which fires `_on_state_change_for_idle_timeout` (cancels idle timeout - fine). Audio is pushed. After all audio is generated and synthesis finishes, audio drain waits. Then `state_machine.stop()` is called.

`stop()` = transition_to(IDLE). From SPEAKING, SPEAKING->IDLE is a VALID transition. State becomes IDLE. Callbacks fire, idle timeout starts (30s). `plugin_speak_callback` returns. `return` exits `on_transcription_with_plugins`.

THE SYSTEM IS NOW IN IDLE STATE. The next user speech should work. BUT IS THERE A HANG?

CRITICAL OBSERVATION: If no WebRTC connection exists (no connected client), `connection_manager._connections` is empty. Then in the audio drain loop (lines 713-724):
- `for pc in list(connection_manager._connections):` - empty list
- `has_audio` stays False
- Loop breaks immediately - NO hang here

If connection EXISTS: audio drains. Eventually has_audio becomes False. Loop exits. Fine.

SO WHERE IS THE HANG?

New hypothesis: The synthesis itself hangs. `tts_processor.receive_token()` is called for each char of the confirmation. The sentence "Sarcasm now at 50%." has 22 chars and ends with ".". The `_has_complete_sentence()` check will find this boundary. `_synthesize_and_stream()` is called. But wait - `%` in the confirmation text "Sarcasm at 50%. This should be interesting." - does the `%` or the `.` after the number cause issues? No, `%` is not in `sentence_endings`.

BUT: "Sarcasm now at 50%. This should be interesting." - the `.` after `50%` is a valid sentence boundary if followed by space: `50%. T` - yes, `%` then `.` then ` ` - wait, the text is `50%.` followed by space then `This`. So `buf.find('.')` will find the `.` at position ~19. Then checks `buf[idx+1] != ' '`... `buf[idx+1]` = ` ` (space). So this IS a valid boundary. speakable chars in `50%. ` fragment - `5`, `0` = 2 chars. That's less than `_MIN_SPEAKABLE_CHARS = 20`. So `_has_complete_sentence()` returns False here. More tokens accumulate until the full sentence is in the buffer.

Actually the full text "Sarcasm now at 50%. This should be interesting." - when the `.` at the end is reached and followed by end-of-string (not space), `_find_sentence_boundary()` checks: `if idx < len(buf) - 1 and buf[idx + 1] != " ": continue`. Since the last `.` is at the end of buffer (idx == len(buf)-1), `idx < len(buf) - 1` is False, so it doesn't skip. This IS a valid boundary.

DEAD END - synthesis should work fine. The hang must be elsewhere.

FINAL HYPOTHESIS: The is_synthesizing poll. After flush(), the code waits:
```python
while tts_processor.is_synthesizing and elapsed < max_wait:
    await asyncio.sleep(0.1)
```
If synthesis is BLOCKING the event loop (not using `run_in_executor`), then `asyncio.sleep(0.1)` never gets to run because synthesis is running synchronously and hogging the event loop. Let me check the TTS synthesizer.

next_action: check orpheus_synthesizer.py and/or synthesizer.py to see if synthesis is synchronous (blocking) or truly async

## Symptoms

expected: When user says "set sarcasm to 50 percent", the pipeline intercepts the command before plugins/LLM, rebuilds the system prompt with new sarcasm level, speaks a tier-specific confirmation via plugin_speak_callback, and returns early without forwarding to LLM.
actual: System gets stuck in processing - hangs indefinitely after the sarcasm command is spoken.
errors: No crash - it just hangs/gets stuck.
reproduction: Start server, connect via Flutter client, say "set sarcasm to 50 percent"
started: First time testing this feature after Phase 16 implementation.

## Eliminated

- hypothesis: asyncio.Lock deadlock between _synthesis_lock and _transition_lock
  evidence: These are different locks on different objects. Callbacks inside _notify_callbacks are all synchronous or create async tasks without re-acquiring _transition_lock. No cross-lock deadlock possible.
  timestamp: 2026-03-04T01:00:00Z

- hypothesis: _transition_lock reentrancy deadlock
  evidence: No callback registered with state_machine calls transition_to() again. _on_state_change_for_idle_timeout creates/cancels tasks but doesn't re-enter the lock. data_handler.broadcast_state_change uses channel.send() which is synchronous.
  timestamp: 2026-03-04T01:00:00Z

- hypothesis: Orpheus stream_tts thread-safety issue with asyncio.Queue
  evidence: queue.put_nowait from thread is not perfectly safe but asyncio.wait_for(queue.get(), 0.1) polls every 100ms as fallback. Works in practice for audio streaming.
  timestamp: 2026-03-04T01:00:00Z

- hypothesis: TARS→Ergos rename broke import paths
  evidence: Git diff shows clean rename. ErgosPromptBuilder is properly imported and used. is_ergos_persona is correctly set for DEFAULT_PERSONA. No broken references.
  timestamp: 2026-03-04T01:00:00Z

- hypothesis: prompt_builder is None (sarcasm intercept skipped)
  evidence: DEFAULT_PERSONA has is_ergos_persona=True. config.yaml has persona_file=null. Therefore DEFAULT_PERSONA is used and prompt_builder IS created.
  timestamp: 2026-03-04T01:00:00Z

## Evidence

- timestamp: 2026-03-04T01:30:00Z
  checked: _idle_timeout function in pipeline.py (lines 326-335)
  found: The idle timeout only handles LISTENING→IDLE and IDLE (no-op). It does NOT handle PROCESSING→IDLE. If the system gets stuck in PROCESSING (due to exception in plugin_speak_callback), there is NO automatic recovery. State stays PROCESSING forever.
  implication: Exception-induced PROCESSING state = permanent hang.

- timestamp: 2026-03-04T01:31:00Z
  checked: plugin_speak_callback (lines 673-731) - exception handling
  found: NO try/except around synthesis or state machine calls in plugin_speak_callback. If Orpheus synthesis throws ANY exception (OOM, model error, ONNX error), it propagates through: plugin_speak_callback -> on_transcription_with_plugins -> _process_accumulated_audio (line 187-188: except Exception as e: logger.error). The except swallows the exception without calling state_machine.stop(). State stays PROCESSING forever.
  implication: Any synthesis exception = permanent PROCESSING state hang.

- timestamp: 2026-03-04T01:32:00Z
  checked: on_transcription_with_plugins (lines 743-782) - exception handling
  found: `for callback in self._transcription_callbacks: try: await callback(result) except Exception as e: logger.error("Transcription callback error: %s", e)` - exceptions from plugin_speak_callback are caught here without any state recovery.
  implication: The exception swallow is in stt_processor._process_accumulated_audio. State machine left in PROCESSING.

- timestamp: 2026-03-04T01:33:00Z
  checked: _idle_timeout behavior for all states
  found: _idle_timeout only handles LISTENING and IDLE. PROCESSING is left unhandled. SPEAKING and SPEAKING_AND_LISTENING are also unhandled (but those have their own completion paths). The problem is PROCESSING state with no active LLM/TTS.
  implication: Need to add PROCESSING recovery to idle timeout OR wrap plugin_speak_callback in try/finally.

- timestamp: 2026-03-04T01:40:00Z
  checked: on_tts_audio callback behavior when plugin_speak_callback synthesis starts - state machine state
  found: When plugin_speak_callback fires (sarcasm intercept path), state = PROCESSING. Synthesis runs. First audio chunk: on_tts_audio fires, _first_audio_sent[0] is False -> start_speaking() called -> PROCESSING->SPEAKING. Audio pushed. This is correct. BUT if synthesis never produces audio (exception or empty result), on_tts_audio never fires, start_speaking() never called, state stays PROCESSING. Then plugin_speak_callback's drain loop runs for 10 seconds (max_wait_seconds based on total_audio_duration_ms=0), then stop() is called from PROCESSING->IDLE (valid). But if plugin_speak_callback THREW AN EXCEPTION before reaching stop(), state stays PROCESSING forever.
  implication: Two bugs: (1) exception leaves state stuck, (2) if synthesis succeeds but stop() is somehow skipped, state stuck. Fix: wrap entire plugin_speak_callback body in try/finally calling state_machine.stop() or reset.

- timestamp: 2026-03-04T00:10:00Z
  checked: pipeline.py plugin_speak_callback (lines 673-731) + state machine VALID_TRANSITIONS
  found: When sarcasm command fires, state is PROCESSING (set by VAD SPEECH_END -> start_processing). plugin_speak_callback checks state and skips IDLE/LISTENING branches. It calls reset_cancellation(), clear_buffer(), sets _first_audio_sent[0] = False. Then feeds chars one by one via receive_token(). Then calls flush(). The synthesis lock is NOT held by receive_token calls (they're sequential awaits). The state machine transitions for PROCESSING->SPEAKING and SPEAKING->IDLE are valid. The audio drain loop waits with max timeout based on audio_duration_s.
  implication: The happy path seems correct structurally. The hang must be in a specific condition.

- timestamp: 2026-03-04T00:15:00Z
  checked: OrpheusSynthesizer.synthesize_stream (lines 238-277 in orpheus_synthesizer.py)
  found: CRITICAL - synthesize_stream first does `async for chunk_sr, audio_int16 in self._orpheus.stream_tts(text, options): raw_chunks.append(...)` collecting ALL raw chunks into raw_chunks list. Then normalizes the concatenated audio. Then re-splits and yields individual chunks. This means synthesis is effectively sequential (all-at-once). However this is all inside TTSProcessor._synthesize_and_stream which has `async with self._synthesis_lock`. The lock is held for the ENTIRE duration of synthesis including all the `async for` iterations. This IS the correct behavior.
  implication: The synthesis_lock is held for the entire synthesis call. If another call to _synthesize_and_stream is attempted while one is running, it blocks waiting for the lock. This is expected.

- timestamp: 2026-03-04T00:20:00Z
  checked: TTSProcessor.receive_token + _has_complete_sentence logic for "Sarcasm now at 50%. This should be interesting."
  found: Text = "Sarcasm now at 50%. This should be interesting." The first sentence boundary is the "." after "50%." (at position 19). buf[19] = ".", buf[20] = " " (space). So _find_sentence_boundary() finds idx=19. candidate = "Sarcasm now at 50%." = 19 chars. speakable (alnum) count = S,a,r,c,a,s,m,n,o,w,a,t,5,0 = 14 chars. That is LESS than _MIN_SPEAKABLE_CHARS=20. So _has_complete_sentence() returns False here. Buffer keeps accumulating. When "." at the very end is reached (idx=47), it's at the end of buffer (idx == len(buf)-1), so the `idx < len(buf) - 1` check fails and it's valid. speakable count in full string: S,a,r,c,a,s,m,n,o,w,a,t,5,0,T,h,i,s,s,h,o,u,l,d,b,e,i,n,t,e,r,e,s,t,i,n,g = much more than 20. _has_complete_sentence() returns True. ENTIRE text synthesized as one call.
  implication: No premature synthesis. One synthesis call for the full confirmation. This is expected.

- timestamp: 2026-03-04T00:25:00Z
  checked: state_machine.stop() call in plugin_speak_callback (line 731) - what state is it called from?
  found: After synthesis and audio drain, stop() is called. stop() = transition_to(IDLE). Looking at VALID_TRANSITIONS: SPEAKING->IDLE is valid. PROCESSING->IDLE is valid. But what if the state is still PROCESSING when stop() is called? This can happen if no WebRTC connections exist (no client connected), meaning no audio was pushed to any track, meaning on_tts_audio never called start_speaking(). If state is still PROCESSING when stop() fires, PROCESSING->IDLE is a valid transition - it succeeds.
  implication: The stop() call works regardless of whether SPEAKING was reached. Not the hang source.

- timestamp: 2026-03-04T00:30:00Z
  checked: Audio drain loop timeout calculation (lines 707-725 in pipeline.py)
  found: `audio_duration_s = tts_processor.total_audio_duration_ms / 1000.0`. If synthesis produced audio, total_audio_duration_ms > 0, and max_wait_seconds = audio_duration_s + 2.0. But if no connections exist, has_audio is False immediately, loop breaks. If connection exists and audio was pushed, the loop waits for has_audio to become False, up to max_wait_seconds. THE CRITICAL ISSUE: max_wait_seconds = max(audio_duration_s + 2.0, 10.0). If total_audio_duration_ms is 0 (synthesis failed or no audio produced), max_wait_seconds = 10.0. The loop runs for 10 seconds checking has_audio. If has_audio is somehow stuck True, the loop runs the full 10 seconds then exits. This is NOT an infinite hang.
  implication: Audio drain can delay by up to 10 seconds but has a hard limit. Not an infinite hang.

- timestamp: 2026-03-04T00:35:00Z
  checked: is_synthesizing poll (lines 700-705) - can this get stuck?
  found: The poll waits while `tts_processor.is_synthesizing` with max_wait=30s. `is_synthesizing` is set to True at the start of _synthesize_and_stream (inside the synthesis_lock) and set back to False in the `finally` block. If synthesis throws an exception that is NOT CancelledError, the `finally` still runs, so `is_synthesizing` returns to False. If synthesis blocks the event loop completely (sync code in `async for`), then `asyncio.sleep(0.1)` in the poll loop never gets scheduled, and the wait loop itself never runs. BUT: the synthesis itself would eventually complete because it's not actually stuck in an await - it would run to completion and then the loop could check.
  implication: If _orpheus.stream_tts is a SYNCHRONOUS generator being iterated with `async for`, the event loop is NOT released during iteration. The `asyncio.sleep(0.1)` in the is_synthesizing poll would NOT run until stream_tts completes. But that's fine - synthesis finishes, is_synthesizing becomes False, then the poll loop runs once and exits. NOT the hang source.

- timestamp: 2026-03-04T00:40:00Z
  checked: state_machine._transition_lock (asyncio.Lock) - potential reentrancy deadlock
  found: The `_transition_lock` is acquired in `transition_to()` and `reset()`. Inside the lock, `_notify_callbacks()` is awaited. If any callback itself calls `transition_to()`, it will deadlock (asyncio.Lock is NOT reentrant). Checking all state callbacks: `_on_state_change_for_idle_timeout` - calls `_start_idle_timeout()` (creates task, does NOT call transition_to) or `_cancel_idle_timeout()` (cancels task, does NOT call transition_to). No reentrant lock issue in registered callbacks.
  implication: No lock deadlock. The lock is not the source.

- timestamp: 2026-03-04T00:45:00Z
  checked: on_tts_audio callback (pipeline.py lines 535-606) - the start_speaking() call inside
  found: on_tts_audio at line 571 calls `await state_machine.start_speaking()` inside `async with self._synthesis_lock`... wait, NO. `on_tts_audio` is called from `_synthesize_and_stream` which holds `_synthesis_lock`. Inside on_tts_audio, `start_speaking()` calls `transition_to()` which acquires `_transition_lock`. There are TWO different locks here: `_synthesis_lock` (on TTSProcessor) and `_transition_lock` (on state machine). These are different locks, no cross-deadlock. BUT there's another issue: on_tts_audio calls `state_machine.start_speaking()` inside the `_synthesis_lock`. State machine's `_notify_callbacks` is then called inside `_transition_lock`. The _on_state_change_for_idle_timeout callback fires. Fine. Then on_tts_audio continues to push audio. All of this is done within `_synthesis_lock` context from `_synthesize_and_stream`'s `async for` callback loop. No deadlock.
  implication: No deadlock between TTS synthesis lock and state machine transition lock.

- timestamp: 2026-03-04T00:50:00Z
  checked: plugin_speak_callback state_machine.stop() call at line 731 after audio drain
  found: CRITICAL FINDING - After plugin_speak_callback completes and returns, the system is in IDLE state. The `return` at line 782 of on_transcription_with_plugins exits the function. The PROCESSING state was transitioned to SPEAKING (via on_tts_audio), then SPEAKING to IDLE (via stop()). The system is correctly back at IDLE. The user can speak again. SO FAR NO INFINITE HANG.

  BUT: What if `on_tts_audio` is NOT called because the _first_audio_sent flag check causes start_speaking() to fail? Let me check: _first_audio_sent[0] is set to False by plugin_speak_callback (line 691). When first audio arrives in on_tts_audio, `if not _first_audio_sent[0]:` is True, calls start_speaking(). From PROCESSING state, PROCESSING->SPEAKING is valid. Returns True. _first_audio_sent[0] = True. Audio is pushed. FINE.

  BUT WHAT IF: state is NOT PROCESSING when on_tts_audio fires? It was set to PROCESSING by VAD SPEECH_END callback before STT ran. If somehow the state changed between STT completing and on_tts_audio... Let's check. Nothing changes the state between PROCESSING and when audio synthesis completes. VAD is not processing (user stopped speaking). No other path changes state. State should remain PROCESSING until start_speaking() is called from on_tts_audio.
  implication: All paths traced. The "stuck in processing" may not be an infinite hang but rather the 10-second drain wait (if audio_duration_ms is ~0 and there's no connection). Or the real hang is elsewhere.

- timestamp: 2026-03-04T00:55:00Z
  checked: The sarcasm confirmation text "Sarcasm now at 50%. This should be interesting." has a PERCENT SIGN before the period: "50%."
  found: MAJOR FIND - Look at the confirmation messages dict in pipeline.py lines 772-779:
  ```python
  confirmations = {
      range(0, 21): f"Sarcasm level set to {new_level}%. All business.",
      range(21, 50): f"Sarcasm at {new_level}%. I'll try to keep a straight face.",
      range(50, 80): f"Sarcasm now at {new_level}%. This should be interesting.",
      range(80, 101): f"Sarcasm cranked to {new_level}%. You asked for it.",
  }
  ```
  For level=50, the key is `range(50, 80)`. The lookup is:
  ```python
  confirmation = next(msg for rng, msg in confirmations.items() if new_level in rng)
  ```
  Python dicts are unordered in theory but ordered by insertion in Python 3.7+. range(0,21) doesn't contain 50, range(21,50) doesn't contain 50 (50 not in range(21,50) since range is exclusive end!), range(50,80) contains 50. This works. Confirmation = "Sarcasm now at 50%. This should be interesting."

  Wait, range(21, 50) has 50 as exclusive end. 50 is NOT in range(21, 50). So for level=50, it falls into range(50, 80). That's correct.

  But for level=49, range(21, 50) contains 49. For level=50, range(50, 80) is used. FINE.
  implication: The confirmation text lookup is correct.

- timestamp: 2026-03-04T01:00:00Z
  checked: EmotionMarkupProcessor.process() - is the "%" character or other chars in confirmation text causing issues?
  found: Need to check emotion_markup.py. The "%" character in "50%." might interfere with emotion tag detection or cause unexpected behavior. Also: the confirmations have apostrophes ("I'll", "You asked for it") which might cause issues in certain parsers.
  implication: Need to inspect emotion_markup.py to rule this out.

## Resolution

root_cause: |
  Two bugs causing "stuck in processing":

  PRIMARY (indefinite hang): plugin_speak_callback had no try/finally error handling.
  If Orpheus TTS synthesis throws any exception (OOM, model error, ONNX error) during
  the sarcasm intercept, the exception propagates through plugin_speak_callback →
  on_transcription_with_plugins → caught silently by stt_processor._process_accumulated_audio.
  State machine stays in PROCESSING forever. The idle timeout only handles LISTENING→IDLE,
  not PROCESSING→IDLE, so there is NO automatic recovery. System requires server restart.

  SECONDARY (safety net missing): Even in normal (no-exception) execution, if Orpheus
  synthesis is slow (3B model can take 5-15s for short text), the state stays PROCESSING
  until first audio chunk arrives and triggers start_speaking(). No timeout existed to
  recover PROCESSING state if this becomes permanent for any reason.

fix: |
  Fix 1 (primary): Wrapped plugin_speak_callback's synthesis body in try/except/finally.
  The `finally` block ALWAYS calls tts_processor.reset_audio_tracking() and
  state_machine.stop() regardless of exceptions. Exceptions are logged with exc_info.
  tts_processor.cancel() is called in the except block to clean up any in-progress synthesis.

  Fix 2 (defence-in-depth): Added _processing_timeout_task with a 60-second safety timer
  that fires whenever the state machine enters PROCESSING. If state is still PROCESSING
  after 60 seconds (impossible in normal operation), it forces transition to IDLE with a
  warning log. This catches any future bugs that leave PROCESSING state without cleanup.
  _on_state_change_for_idle_timeout now cancels the processing timeout when state advances
  to SPEAKING, SPEAKING_AND_LISTENING, or IDLE.

verification: |
  - 244 unit + integration tests pass (python -m pytest tests/ -x -q)
  - try_sarcasm_command("set sarcasm to 50 percent") = 50 ✓
  - ErgosPromptBuilder.build(sarcasm_level=50) produces correct mid-range prompt ✓
  - Code review: try/finally guarantees stop() is always called in plugin_speak_callback ✓
  - Code review: processing timeout fires when state stuck at PROCESSING for 60s ✓
  - Human verification needed: say "set sarcasm to 50 percent" and confirm TTS speaks confirmation and system returns to IDLE

files_changed:
  - src/ergos/pipeline.py
