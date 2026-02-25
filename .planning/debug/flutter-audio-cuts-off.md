---
status: fix_implemented
trigger: "No audio heard in Flutter app - only one word plays then silence"
created: 2026-01-28T11:45:00Z
updated: 2026-01-28T12:15:00Z
---

## Current Focus

hypothesis: TTSAudioTrack.recv() lacks pacing - frames are produced faster than real-time
test: Compare our implementation with aiortc base AudioStreamTrack
expecting: Missing pacing causing timestamp/timing issues on client
next_action: Add proper real-time pacing to recv() method

## Symptoms

expected: TTS audio plays fully in Flutter app - all sentences audible
actual: Only ONE word is heard, then silence. Server logs show TTS synthesizing multiple sentences successfully.
errors: No errors in server logs. Pipeline completes normally (processing → speaking → idle)
reproduction: Connect Flutter client, speak to trigger response, hear only first word of TTS response
started: Partial - one word plays, suggesting audio path works but something cuts it off

## Key log observations

1. Server successfully processes: STT → LLM → TTS
2. TTS synthesizes multiple sentences over ~4 seconds (11:42:49 to 11:42:53)
3. State transitions correctly: processing → speaking → idle
4. LLM completed: 138 chars, 35 tokens
5. No errors or crashes - server stays running
6. User hears ONE word then silence

## Hypotheses to explore

1. ~~WebRTC audio track not continuously sending frames~~
2. ~~Flutter client stops listening after first audio chunk~~
3. **Buffer underrun - recv() returning silence before TTS data arrives** - LIKELY ROOT CAUSE
4. Audio track being cleared prematurely (barge-in triggered?)
5. Sample rate mismatch causing playback issues

## Eliminated

1. Flutter client issue - client receives audio, track is enabled
2. Server pipeline issue - TTS synthesis completes successfully

## Evidence

### Key Finding: Missing Pacing in TTSAudioTrack.recv()

1. **aiortc base AudioStreamTrack.recv()** (mediastreams.py:81-108) implements pacing:
   ```python
   wait = self._start + (self._timestamp / sample_rate) - time.time()
   await asyncio.sleep(wait)
   ```

2. **Our TTSAudioTrack.recv()** (audio_track.py:56-117) returns immediately with no pacing:
   - When buffer has data: returns frame immediately
   - When buffer is empty: returns silence immediately
   - NO asyncio.sleep() for timing control

3. **RTCRtpSender._run_rtp()** (rtcrtpsender.py:357-424) calls recv() in tight loop:
   - Line 371: `enc_frame = await self._next_encoded_frame(codec)`
   - Line 298: `data = await self.__track.recv()`
   - No sleep between iterations - relies on track.recv() for pacing

4. **Impact**: Without pacing:
   - When buffer is empty (before TTS data arrives), silence frames are produced at CPU speed
   - Thousands of silence frames sent before first audio chunk
   - This likely overwhelms the client or causes decoder issues
   - First word plays (initial buffered data), then something breaks

### Why One Word Plays

1. First TTS chunk arrives, gets pushed to buffer
2. recv() returns buffered data (one word worth)
3. Client plays that audio correctly
4. TTS synthesis continues but buffer drains faster than fill rate (no pacing)
5. Subsequent audio either gets lost or client decoder fails

## Resolution

root_cause: TTSAudioTrack.recv() lacks real-time pacing - returns frames at CPU speed instead of 20ms intervals, causing timestamp/timing issues
fix: Add pacing logic similar to base AudioStreamTrack - track start time and sleep to maintain real-time frame rate
verification:
  - [x] Python import test passed
  - [x] Pacing verified: second recv() waits ~20ms
  - [ ] Flutter client test pending user verification
files_changed:
  - /home/vinay/ergos/src/ergos/transport/audio_track.py

### Fix Details

Added to `TTSAudioTrack`:
1. New instance variable `_start_time: Optional[float] = None`
2. Pacing logic in `recv()`:
   ```python
   if self._start_time is not None:
       elapsed_samples = self._timestamp
       expected_elapsed_time = elapsed_samples / self._sample_rate
       actual_elapsed_time = time.time() - self._start_time
       wait_time = expected_elapsed_time - actual_elapsed_time
       if wait_time > 0:
           await asyncio.sleep(wait_time)
   else:
       self._start_time = time.time()
   ```

### Verification Test Output
```
Track created: sample_rate=48000, samples_per_frame=960
Start time: None
After push: buffer_samples=9600
First recv: pts=0, samples=960
Start time after first recv: 1769619040.6232595
Second recv: pts=960, wait_time=0.020s
Test passed!
```
