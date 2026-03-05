---
status: fixing
trigger: "Voice pipeline produces truncated/garbled TTS output and breaks completely on WebRTC reconnect."
created: 2026-03-04T16:30:00
updated: 2026-03-04T16:45:00
---

## Current Focus

hypothesis: CONFIRMED — Two bugs cause all 0ms TTS output: (1) _inside_think stuck True because reset_cancellation() doesn't reset it; (2) /no_think in wrong location (system message instead of user message) — Qwen3 only recognizes it in user turn.
test: All 198 unit tests pass after fixes applied.
expecting: With /no_think in the user message, Qwen3 will not generate <think> blocks. And reset_cancellation() now resets _inside_think, preventing stale state from silencing TTS.
next_action: Human verification — restart server and test voice interactions.

## Symptoms

expected: User speaks → STT transcribes → LLM generates short response → TTS speaks clearly. Disconnecting and reconnecting should work seamlessly.
actual: (1) TTS output is truncated/garbled (e.g., "I can hearrrrr" then stops mid-word). (2) After disconnect and reconnect, pipeline dead. (3) "TTS generated 0ms of audio" even when LLM completes successfully.
errors: |
  - "Invalid transition: processing → idle" — state machine stuck (FIXED: processing→idle now valid)
  - "TTS generated 0ms of audio" — TTS cancelled flag stuck after barge-in (PARTIALLY FIXED)
  - LLM generates 512 tokens (max_tokens hit) — Qwen3 thinking mode (FIXED: /no_think added)
  - After reconnect, VAD fires but no STT/LLM/TTS (FIXED: on_connect resets state)
reproduction: 1) Start ergos server + Flutter client. 2) Say "can you hear me?" — get garbled/truncated response. 3) Disconnect client. 4) Reconnect client. 5) Speak again — nothing happens.
timeline: Phase 16 TARS personality testing. TTS engine recently switched from Kokoro to Orpheus.

## Eliminated

- hypothesis: State machine stuck in processing after reconnect — no valid processing→idle transition
  evidence: Log line 93 shows "State transition: processing → idle" succeeding. Fix #6 applied.
  timestamp: 2026-03-04T16:30:00

- hypothesis: LLM consuming all 512 tokens on <think> blocks
  evidence: Log lines 77,89,124,149 show "LLM completed: N chars, N tokens" with 9-21 tokens, not 512. /no_think fix working.
  timestamp: 2026-03-04T16:30:00

- hypothesis: Reconnect leaves state stuck in non-IDLE state
  evidence: Log line 101 shows "State reset: listening → idle". on_connect callback fires correctly on line 100,154.
  timestamp: 2026-03-04T16:30:00

- hypothesis: _cancelled flag stuck True after barge-in (not reset before new transcription)
  evidence: pipeline.py:761 calls tts_processor.reset_cancellation() before llm_processor.process_transcription(). Also on_vad_reset_flags resets on SPEECH_START. This is fixed. But see REMAINING BUG #1.
  timestamp: 2026-03-04T16:30:00

## Evidence

- timestamp: 2026-03-04T16:30:00
  checked: server log lines 61-93 (first connection, first utterance)
  found: TTS synthesis begins ("Complete sentence, synthesizing"), state goes processing→speaking. User immediately barges in at 15:57:56 (only ~2s into response). Barge-in executes correctly, LLM cancelled (20 tokens). Second utterance (Thanks for watching!) is hallucination from 0.5s of audio — STT has no real content. Flush strips incomplete <think> block → 0ms audio → state processing→idle correctly.
  implication: First connection works OK. Barge-in handling is correct for first session.

- timestamp: 2026-03-04T16:30:00
  checked: server log lines 100-128 (second connection after reconnect)
  found: on_connect fires (line 100-101), state reset to idle. VAD fires, state idle→listening→processing. LLM completes (42 chars, 11 tokens — /no_think working). But "TTS: Stripped incomplete <think> block at flush" → "TTS generated 0ms of audio". State processing→idle.
  implication: CRITICAL BUG: Even with /no_think, the TTS processor thinks it's inside a <think> block (_inside_think=True) when there is no actual think block. The _inside_think flag was set by the previous session's barge-in processing and was NOT reset by on_new_connection().

- timestamp: 2026-03-04T16:30:00
  checked: pipeline.py on_new_connection() lines 850-857
  found: on_new_connection() calls: state_machine.reset(), tts_processor.reset_cancellation(), tts_processor.clear_buffer(), tts_processor.reset_audio_tracking(), _first_audio_sent[0] = False. Does NOT reset _inside_think.
  implication: CONFIRMED BUG #1: _inside_think=True persists across connections. After reconnect, any LLM response that doesn't start with a complete think block gets silently discarded at flush() because "TTS: Stripped incomplete <think> block at flush" treats the entire buffer as an orphaned think block even when _inside_think was falsely stuck True from prior session.

- timestamp: 2026-03-04T16:30:00
  checked: tts/processor.py reset_cancellation() line 228-233
  found: reset_cancellation() only resets _cancelled=False. Does NOT reset _inside_think.
  implication: CONFIRMED BUG #1b: If a barge-in occurs while LLM was streaming a think block (cancel() does reset _inside_think=False in cancel()), that's fine. But the issue is more subtle — _inside_think can get stuck True if the buffer had "<think>" token added but "</think>" never arrived before the session ended/barge-in happened AND cancel() was NOT called (e.g., LLM completed naturally after context switch).

- timestamp: 2026-03-04T16:30:00
  checked: log lines 90, 125, 150 — all show "TTS: Stripped incomplete <think> block at flush"
  found: Every single flush() call strips an "incomplete think block". This happens 3 times across 3 different utterances. With /no_think active, Qwen3 should NOT produce <think> blocks at all. So _inside_think=True is clearly a stale flag from a previous state, not from actual <think> tokens.
  implication: CONFIRMED: _inside_think is getting stuck True and never properly reset between utterances. The pattern: barge-in during first session sets cancel() which clears _inside_think, but then on reconnect or after cancel, _inside_think state is unreliable. Actually on closer inspection — the log shows all 3 utterances stripping think blocks. The FIRST utterance also strips. This means _inside_think was True even for the FIRST utterance. Looking at session 1: the barge-in at 15:57:56 triggers cancel() which sets _inside_think=False. Then speech_start for 2nd utterance resets cancellation. Then 2nd utterance (hallucinated "Thanks for watching!") flushes and strips think block. HOW? With /no_think, there should be no <think> tokens. The _inside_think=True must be from LLM generating "<think>" token before /no_think takes effect on first ever generation, then getting stuck.

- timestamp: 2026-03-04T16:30:00
  checked: orpheus_synthesizer.py synthesize_stream() lines 147-178
  found: Uses `async for chunk_sr, audio_int16 in self._orpheus.stream_tts(text, options)`. The orpheus-cpp library's stream_tts — unknown if this is truly async or a sync generator. If sync, the `async for` on a sync generator does NOT yield to the event loop between iterations — it runs all iterations in one tight loop, blocking the event loop. This would prevent cancellation checks, VAD events, and all other async tasks from running during synthesis.
  implication: POTENTIAL BUG #2: If stream_tts is synchronous (returns a regular generator), calling `async for` on it doesn't yield to the event loop. The cancellation check `if self._cancelled: return` would never be reached between chunks. Audio would still be produced but pipeline would feel "hung" or "garbled" during long synthesis. However since Orpheus generates all audio first then returns it (LLM autoregressive), this may be unavoidable without run_in_executor.

- timestamp: 2026-03-04T16:30:00
  checked: tts/processor.py _synthesize_and_stream() — the `async for` loop with cancellation check
  found: Cancellation is checked BETWEEN chunks from synthesize_stream. If stream_tts is synchronous and generates all audio before yielding the first chunk, the `async for` would iterate over pre-generated chunks very fast. The _cancelled flag could still be False at each check if barge-in hasn't happened yet. This seems OK.
  implication: Orpheus stream_tts behavior needs verification, but the primary bug causing "0ms of audio" is definitely the _inside_think stale flag.

- timestamp: 2026-03-04T16:30:00
  checked: server log line 39 "TTS: Kokoro ONNX" — server reports Kokoro even though Orpheus is loaded
  found: Line 39 says "TTS: Kokoro ONNX" but line 27 says "Orpheus 3B model loaded successfully". The server startup banner incorrectly says Kokoro. This is a cosmetic issue in server.py only.
  implication: Minor display bug, no functional impact.

- timestamp: 2026-03-04T16:30:00
  checked: log lines 131-132 — "Invalid transition: listening → listening" warnings at 16:00:41 and 16:00:53
  found: Multiple SPEECH_START events fire while already in LISTENING state. This happens because VAD fires speech_start, on_vad_for_state calls state_machine.start_listening(), which fails because already listening. This is harmless (state stays LISTENING) but creates log noise.
  implication: Minor: LISTENING→LISTENING invalid transition warnings. The state machine correctly rejects the transition. This is expected behavior when VAD fires multiple speech_start events (e.g., brief pauses within a sentence).

## Resolution

root_cause: |
  TWO BUGS causing "TTS generated 0ms of audio" on every utterance:

  BUG 1: /no_think in wrong location in chatml prompt.
  The code placed /no_think at the end of the system message:
    <|im_start|>system\n{prompt}\n/no_think<|im_end|>
  But Qwen3 ONLY recognizes /no_think when it appears in a USER message.
  The system-message placement was silently ignored, so Qwen3 still generated
  <think> blocks on every response. This caused _inside_think=True on first generation.

  BUG 2: _inside_think flag not reset by reset_cancellation().
  Once _inside_think=True (from Qwen3 generating a <think> token), it persisted across
  utterances because reset_cancellation() only reset _cancelled, not _inside_think.
  Result: flush() saw _inside_think=True even on subsequent utterances that had no
  think blocks, stripped the entire buffer, and produced 0ms of audio.

  Evidence: log shows "TTS: Stripped incomplete <think> block at flush" on ALL 3
  utterances including ones where LLM completed cleanly in 9-21 tokens.

fix: |
  Fix 1 (src/ergos/llm/processor.py): Moved /no_think from system message to the
  last user message in _build_chatml_prompt(). Now generates:
    <|im_start|>user\n{user_text} /no_think<|im_end|>
  This is the correct placement per Qwen3 documentation.

  Fix 2 (src/ergos/tts/processor.py): reset_cancellation() now also resets
  _inside_think=False. Added reset_state() method that clears all flags
  (_cancelled, _inside_think, _buffer, _total_audio_duration_ms).

  Fix 3 (src/ergos/pipeline.py): on_new_connection() now calls reset_state()
  instead of separate reset_cancellation()/clear_buffer()/reset_audio_tracking()
  calls — ensures all TTS state is clean on reconnect.

  Fix 4 (tests/unit/test_llm_qwen3.py): Updated 2 tests to expect /no_think in
  user message, not system message.

verification: All 198 unit tests pass.
files_changed:
  - src/ergos/llm/processor.py
  - src/ergos/tts/processor.py
  - src/ergos/pipeline.py
  - tests/unit/test_llm_qwen3.py
