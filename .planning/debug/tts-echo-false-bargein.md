---
status: awaiting_human_verify
trigger: "tts-echo-false-bargein"
created: 2026-03-04T00:00:00Z
updated: 2026-03-04T00:05:00Z
symptoms_prefilled: true
---

## Current Focus

hypothesis: CONFIRMED and FIXED
test: 208 unit tests pass including 10 new echo suppression tests
expecting: User verification that TTS responses now play to completion without echo-triggered barge-in
next_action: User to verify fix end-to-end

## Symptoms

expected: TTS speaks full response without being interrupted by echo
actual: TTS starts speaking, ~1-2 seconds later VAD detects the TTS output as "speech", triggers SPEAKING_AND_LISTENING overlap, then barge-in cancels TTS. User hears only first few words.
errors: |
  16:10:05 - state transition: processing → speaking
  16:10:06 - VAD: Speech started
  16:10:06 - state transition: speaking → speaking_and_listening
  16:10:07 - Overlap timeout: executing barge-in after 500ms
  16:10:07 - Barge-in: executing cancel sequence
  16:10:07 - TTS: Synthesis cancelled
reproduction: Every single TTS response triggers this. Speak → get 1-2 seconds of response → barge-in cuts it off.
started: Happens with Orpheus TTS engine on a Linux laptop where speakers are close to mic. No AEC/echo cancellation.

## Eliminated

- hypothesis: Server-side VAD processing leaked audio causes the event
  evidence: VADProcessor processes events from data channel only (process_raw_event). Server never processes microphone audio directly — audio goes through on_incoming_audio → stt_processor only. The VAD events come exclusively from the Flutter client.
  timestamp: 2026-03-04T00:01:00Z

- hypothesis: on_incoming_audio feeds audio to VAD during SPEAKING
  evidence: on_incoming_audio in pipeline.py explicitly filters: only processes audio in IDLE, LISTENING, or SPEAKING_AND_LISTENING states. During SPEAKING it returns early. So the false VAD event is NOT from server-side audio processing.
  timestamp: 2026-03-04T00:01:00Z

## Evidence

- timestamp: 2026-03-04T00:01:00Z
  checked: DataChannelHandler._handle_vad_event (data_channel.py line 100-112)
  found: Client VAD events arrive as JSON {"type": "vad_event", "event": "speech_start"} and are forwarded unconditionally to vad_processor.process_raw_event() with no state check
  implication: No filtering exists — any client VAD event (including echo) goes straight to VAD callbacks

- timestamp: 2026-03-04T00:01:00Z
  checked: on_vad_for_state in pipeline.py (lines 358-418)
  found: On SPEECH_START during SPEAKING, immediately transitions to SPEAKING_AND_LISTENING and starts a 500ms overlap timer. Timer fires → barge-in unconditionally.
  implication: 500ms is shorter than typical echo propagation delay (~1s) + VAD processing delay. Echo triggers this every time.

- timestamp: 2026-03-04T00:01:00Z
  checked: VADService in client (vad_service.dart, startListening config)
  found: positiveSpeechThreshold=0.6, minSpeechFrames=5 (~160ms). VAD runs on microphone audio which is picking up TTS from speakers. No AEC in the pipeline. Echo from speakers easily crosses 0.6 threshold.
  implication: Client VAD cannot distinguish echo from real speech — needs server-side state awareness.

- timestamp: 2026-03-04T00:01:00Z
  checked: main.dart VAD callback
  found: onVADEvent sends ALL VAD events unconditionally regardless of server state. Client knows server state (via _serverState) but does NOT check it before forwarding events.
  implication: Client could filter based on _serverState, but server-side fix is safer and simpler.

- timestamp: 2026-03-04T00:01:00Z
  checked: Echo timing from log
  found: TTS starts at 16:10:05, VAD fires at 16:10:06 (~1s later), barge-in at 16:10:07. Echo takes ~1s to trigger VAD (speaker → mic → Silero processing). Overlap timer is 500ms.
  implication: Fix must handle: echo fires ~1s into TTS, triggers 500ms timer. Real barge-in: user speaks during TTS, echo ALSO fires but user's voice sustains longer. Need to differentiate.

- timestamp: 2026-03-04T00:05:00Z
  checked: Secondary side effect in on_vad_reset_flags
  found: on_vad_reset_flags always resets _first_audio_sent[0]=False on SPEECH_END. In echo suppression case, state is restored to SPEAKING but _first_audio_sent would be False → next TTS audio chunk would call start_speaking() from SPEAKING → invalid transition → audio discarded.
  implication: Also patched on_vad_reset_flags to skip the reset when state is already SPEAKING (echo suppression restored it).

## Resolution

root_cause: |
  Client Silero VAD (positiveSpeechThreshold=0.6, minSpeechFrames=5) picks up TTS audio echoing
  from laptop speakers. This fires speech_start via data channel ~1s after TTS begins. The server
  DataChannelHandler forwards it unconditionally to VADProcessor, which triggers on_vad_for_state.
  The handler transitions to SPEAKING_AND_LISTENING and starts a 500ms overlap timer. Since echo
  is still ongoing at 500ms, the timer fires and executes barge-in — cancelling TTS. The echo is
  indistinguishable from real speech to the VAD, but it ends quickly (< 800ms total duration in
  the overlap state), unlike real user barge-in which sustains speech.

fix: |
  Two changes in src/ergos/pipeline.py on_vad_for_state:

  1. Overlap window: 500ms → 1500ms (_OVERLAP_WINDOW_S)
     - Echo that sustains through 500ms will not sustain through 1500ms

  2. Echo suppression via duration gate on SPEECH_END:
     - Track when SPEAKING_AND_LISTENING was entered (_overlap_entry_time)
     - On SPEECH_END: measure how long we were in overlap state
     - If < 800ms (_MIN_BARGE_IN_DURATION_S): echo → restore SPEAKING, TTS continues
     - If >= 800ms: real user barge-in → execute immediately

  3. Side effect fix in on_vad_reset_flags:
     - Skip _first_audio_sent reset when SPEECH_END occurs and state is already SPEAKING
     - (Means echo suppression restored SPEAKING; TTS is still active, don't break audio flow)

verification: 208/208 unit tests pass including 10 new echo suppression tests in test_echo_suppression.py

files_changed:
  - src/ergos/pipeline.py
  - tests/unit/test_echo_suppression.py (new)
