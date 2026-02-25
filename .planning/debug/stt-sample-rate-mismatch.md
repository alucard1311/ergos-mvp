---
status: investigating
trigger: "Audio plays in slow motion - sample rate mismatch causing STT to fail"
created: 2026-01-28T13:20:00Z
updated: 2026-01-28T13:20:00Z
---

## Current Focus

hypothesis: Sample rate mismatch between WebRTC audio and server processing
test: Trace audio sample rate through entire pipeline
expecting: Find where assumed rate differs from actual rate
next_action: Check WebRTC frame sample rate vs assumed 48kHz

## Symptoms

expected: Audio plays at normal speed, STT transcribes correctly
actual: Audio plays in slow motion (user said "Can you give" and it plays slowed down), STT transcribes completely wrong words
errors: No errors - just wrong transcription
reproduction: Any speech input - always plays slow and transcribes wrong
started: Has been an issue throughout debugging session

## Key Evidence Already Known

1. Debug audio file is saved at 16kHz (verified with ffprobe)
2. Server logs show "Resampling from 48000Hz to 16000Hz"
3. When user plays /tmp/ergos_debug_audio.wav, it's in SLOW MOTION
4. User can make out their words but slowed down
5. OnePlus 10R phone - Flutter client with WebRTC

## Hypothesis

If audio plays SLOW at 16kHz, it means the original audio has MORE samples than expected.
- We assume source is 48kHz and resample to 16kHz (divide by 3)
- But if source is actually 96kHz, we'd be dividing by 3 when we should divide by 6
- Result: audio at 16kHz has 2x too many samples = plays at half speed

OR:
- WebRTC frame reports wrong sample_rate
- Actual audio is at different rate than frame.sample_rate reports

## Eliminated

- Source sample rate is NOT 96kHz (WebRTC/Opus uses 48kHz as standard)
- Channel extraction was happening but for wrong format type

## Evidence

1. VAD reported speech duration: 1482ms (~1.5s)
2. Server received 142,080 samples - at 48kHz this is 2.96s (2x expected)
3. aiortc Opus decoder outputs STEREO (2 channels) even for mono input
4. Opus decoder uses PACKED/INTERLEAVED format (s16, not s16p)
5. Packed stereo format: shape = (1, samples * channels) = (1, 1920) for 20ms
6. Code was doing `samples[0]` which gives all 1920 interleaved samples
7. Interleaved samples (LRLRLR...) were treated as mono = 2x sample count

## Root Cause

The audio format is **interleaved stereo** (packed format like `s16`), not planar.
- Packed stereo: `to_ndarray()` returns shape (1, 1920) for stereo 960-sample frame
- Code was taking `samples[0]` = 1920 interleaved L,R,L,R samples
- These were accumulated as if they were mono, causing 2x the samples
- Result: audio at 16kHz has 2x samples = plays at half speed

## Resolution

root_cause: Interleaved stereo audio was being treated as mono (2x samples)
fix: Check `frame.format.is_planar` and for packed stereo, take every other sample
verification: Re-run server, check debug audio plays at normal speed
files_changed: [src/ergos/transport/signaling.py]
