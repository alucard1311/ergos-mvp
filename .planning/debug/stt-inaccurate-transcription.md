---
status: fixed
trigger: "STT transcription is completely wrong, LLM responses don't match input"
created: 2026-01-28T13:30:00Z
updated: 2026-01-28T14:25:00Z
resolved: 2026-01-28T14:25:00Z
---

## Resolution

### Root Cause

The primary issue was in `src/ergos/transport/signaling.py` where incoming WebRTC audio was assumed to always be int16 format. The code used:

```python
samples = np.clip(samples, -32768, 32767).astype(np.int16)
```

This pattern fails silently when audio is in float format ([-1, 1] range):
- `clip(-32768, 32767)` does nothing to values in [-1, 1]
- `astype(np.int16)` rounds all values to 0 or -1
- Result: Whisper receives essentially silence, causing hallucinated transcription

### Secondary Issue (Latent Bug)

The partial transcription loop in `src/ergos/stt/processor.py` passed raw 48kHz audio buffer to the transcriber without resampling, and used default sample_rate=16000. This would cause severe pitch/speed distortion if partial callbacks were enabled.

### Fixes Applied

**1. signaling.py - Proper dtype handling:**
```python
# Handle both int16 and float audio formats from WebRTC
if samples.dtype in (np.float32, np.float64):
    # Float audio in [-1, 1] range - convert to int16
    samples = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
elif samples.dtype != np.int16:
    # Other integer types - clip and convert
    samples = np.clip(samples, -32768, 32767).astype(np.int16)
# else: already int16, use as-is
```

**2. stt/processor.py - Partial transcription resampling:**
- Added proper resampling from source rate (48kHz) to target rate (16kHz)
- Now passes correct sample_rate to transcriber
- Fixed minimum audio length calculation for source sample rate

### Files Changed

1. `src/ergos/transport/signaling.py` (lines 44-57): Added dtype detection and proper conversion for float audio
2. `src/ergos/stt/processor.py` (lines 172-217): Added resampling to partial transcription loop

### Verification Steps

1. Run server with DEBUG logging: `python -m ergos.cli --log-level DEBUG`
2. Connect with mobile app and speak
3. Check logs for:
   - "Converting float audio" message (if float was the issue)
   - "STT: Raw transcription result:" showing actual transcription
4. Verify transcription matches spoken words
5. Listen to `/tmp/ergos_debug_audio.wav` to confirm audio quality

---

## Investigation Summary

### Audio Flow Traced

1. Flutter client captures audio via `getUserMedia()` at device sample rate
2. WebRTC/Opus transmits audio (encoded at client, decoded at server)
3. `signaling.py` `_process_incoming_audio()` converts frame to numpy array **[FIX HERE]**
4. `pipeline.py` `on_incoming_audio()` wraps in AudioChunk with sample rate
5. `stt/processor.py` accumulates audio when VAD indicates speech
6. `stt/processor.py` `_process_accumulated_audio()` resamples 48kHz->16kHz and transcribes
7. `stt/transcriber.py` normalizes to float32 [-1,1] and calls faster-whisper

### Verified Correct

- Sample rate conversion: `resample_poly(audio, up=1, down=3)` for 48kHz->16kHz
- VAD event flow: Flutter sends correct JSON, server parses correctly
- Whisper normalization: `audio_float = audio_array.astype(np.float32) / 32768.0`
- Model configuration: "base" model is adequate for basic transcription

### Eliminated

- Resampling math errors
- VAD event parsing issues
- Whisper configuration problems
- Model file corruption
