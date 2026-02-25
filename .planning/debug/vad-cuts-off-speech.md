---
status: fixed
trigger: "STT not transcribing speech properly - listening cuts off at brief pauses and starts processing fragments"
created: 2026-01-28T13:00:00Z
updated: 2026-01-28T13:15:00Z
---

## Current Focus

hypothesis: VAD speech_end triggers too quickly during brief pauses (<1 sec)
test: Examine VAD configuration and speech_end detection logic
expecting: Find sensitivity settings or timing thresholds that are too aggressive
next_action: Search for VAD configuration in client and server code

## Symptoms

expected: Full sentences transcribed even with brief natural pauses (e.g., "Hey... how are you" captured as one utterance)
actual: Speech cut off at brief pauses - "Hey" processed alone, then rest processed separately as second utterance
errors: None - server runs fine, just wrong behavior
reproduction: Speak a sentence with a brief pause (<1 sec) in the middle - it gets split into fragments
started: Never worked - has always had this behavior

## Additional Context

- User says "Hey... how are you" with brief pause
- System captures only "hey", processes it, speaks response
- Then processes remaining audio as separate utterance
- LLM responses seem unrelated (likely because only receiving fragments)
- User also interested in better STT model (defer until VAD fixed)

## Eliminated

[none yet]

## Evidence

1. **VAD startListening() call is missing `redemptionFrames` parameter**
   - File: `client/lib/services/vad_service.dart` line 83-89
   - Current configuration:
     ```dart
     await _vadHandler!.startListening(
       model: 'v5',
       frameSamples: 512, // 32ms frames at 16kHz
       positiveSpeechThreshold: 0.5,
       negativeSpeechThreshold: 0.35,
       preSpeechPadFrames: 10,
     );
     ```
   - Missing: `redemptionFrames` parameter

2. **What `redemptionFrames` does (from pub.dev documentation)**
   - "Redemption frames allow brief silence gaps within speech without triggering end detection"
   - Default value: 8 frames
   - At 32ms per frame (v5 model), 8 frames = 256ms of silence allowed
   - This is too short for natural speech pauses (typically 300-800ms)

3. **Frame timing calculation for v5 model**
   - frameSamples: 512 samples
   - Sample rate: 16kHz
   - Frame duration: 512 / 16000 = 32ms per frame
   - Current default (8 frames): 8 * 32ms = 256ms
   - Recommended (24 frames): 24 * 32ms = 768ms (~0.75 seconds)

## Resolution

root_cause: Missing `redemptionFrames` parameter in VAD startListening(). Default of 8 frames (256ms at 32ms/frame) is too aggressive, triggering speech_end on brief natural pauses.
fix: Add `redemptionFrames: 24` to allow ~750ms of silence before triggering speech_end
verification: User should be able to say "Hey... how are you" with brief pause and have it transcribed as one utterance
files_changed: [client/lib/services/vad_service.dart]
