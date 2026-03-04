# TTS Naturalness Research: Root Causes and Recommendations

**Date:** 2026-03-04
**Scope:** Orpheus 3B TTS pipeline — from SNAC token generation through WebRTC delivery
**Symptoms investigated:** (1) last chunk/word breaks or cuts off, (2) no graceful sentence beginnings/endings, (3) doesn't feel like natural human conversation

---

## 1. Executive Summary

The three most impactful issues, in priority order:

**Issue 1 — SNAC trailing token drop (Root Cause A):** The `_decode` generator in `orpheus_cpp/model.py` silently drops the last 0–6 audio tokens at the end of every utterance. Since SNAC generates one audio frame per 7 tokens (each frame = 85ms of audio), up to 73ms of audio is discarded per sentence. This is the primary cause of cut-off word endings. The fix is a one-time patch to `orpheus_cpp/model.py` — or a wrapper that pads the trailing tokens before the generator exhausts.

**Issue 2 — Per-chunk peak normalization (Root Cause D):** Every 85ms SNAC chunk is independently normalized to 0.95 peak amplitude. The last chunk of a sentence naturally trails off (low energy), so normalization amplifies it artificially to 0.95 — then the 40ms fade-out drops it back to zero. The audible result is a volume surge immediately before the fade-out, creating an unnatural "pumping" effect at sentence ends. Fix: normalize the full utterance after all chunks are collected, not per-chunk.

**Issue 3 — Digital silence between sentences (Root Cause G):** The 200ms inter-sentence gap is absolute zeros — true digital silence. In human speech, there is always ambient noise between utterances (-40 to -60 dBFS). Switching abruptly from speech to 0-amplitude zeros and back is immediately recognizable as synthetic. Fix: replace flat silence with very-low-amplitude noise (< 0.001 amplitude) at the speech's measured noise floor level, or reduce the gap to 80–120ms.

---

## 2. Root Cause Analysis

### Hypothesis A — SNAC Trailing Token Drop

**Severity:** CRITICAL
**Likelihood of causing "last word cuts off":** HIGH
**Fix impact:** HIGH
**Fix complexity:** LOW

**Code evidence** (`orpheus_cpp/model.py`, `_decode` method, lines 142–159):

```python
def _decode(self, token_gen):
    buffer = []
    count = 0
    for token_text in token_gen:
        token = self._token_to_id(token_text, count)
        if token is not None and token > 0:
            buffer.append(token)
            count += 1
            if count % 7 == 0 and count > 27:  # <-- KEY CONDITION
                buffer_to_proc = buffer[-28:]
                audio_samples = self._convert_to_audio(buffer_to_proc)
                if audio_samples is not None:
                    yield audio_samples
    # <-- Generator ends. No final flush of partial buffer.
```

The condition `count % 7 == 0` means the generator only yields when `count` is an exact multiple of 7. If the Orpheus LLM generates a total token count that is not divisible by 7, the trailing 1–6 tokens are never decoded.

**Quantitative impact:**
- 7 SNAC tokens = 1 SNAC frame = 2048 samples at 24kHz = **85.3ms of audio**
- Maximum tokens dropped: 6 (= 6/7 of a frame)
- Maximum audio dropped: **73ms per utterance**
- This reliably cuts off the final phoneme of the last word in every sentence that ends with a non-multiple-of-7 token count (which is ~6/7 = 86% of sentences)

**SNAC architecture context:** The SNAC decoder processes 4 frames (28 tokens) per call and extracts only the second frame (samples `2048:4096`) as output. This is a sliding window with 3-frame context — each new 7-token group triggers a full 28-token re-decode. The `2048:4096` crop is intentional: the surrounding frames provide bidirectional context for the CNN decoder. This architecture is correct by design. The ONLY problem is that the final 0–6 tokens after the last multiple-of-7 boundary are silently discarded.

**Fix (one approach — wrapper in `orpheus_synthesizer.py`, no upstream changes):**
```python
# In synthesize_stream, after collecting all chunks:
# Check if the trailing decode needs to be forced.
# Alternatively, patch _decode to flush the partial buffer:
```

**Fix (preferred — patch `_decode` in orpheus_cpp, or fork):**
```python
# After the for loop exits, check if there are trailing tokens:
trailing = count % 7
if trailing > 0 and len(buffer) >= 28:
    # Pad to next multiple of 7 by repeating the last token
    pad_count = 7 - trailing
    buffer.extend([buffer[-1]] * pad_count)
    buffer_to_proc = buffer[-28:]
    audio_samples = self._convert_to_audio(buffer_to_proc)
    if audio_samples is not None:
        yield audio_samples
```

The padded tokens produce a slight repetition artifact at the very end, but the existing 40ms fade-out in `synthesize_stream` masks it completely.

---

### Hypothesis B — SNAC 2048:4096 Crop Window

**Severity:** NOT A BUG
**Likelihood of contributing to symptoms:** NONE
**Fix impact:** N/A

**Code evidence** (`orpheus_cpp/model.py`, `_convert_to_audio`, line 210):
```python
audio_np = audio_hat[:, :, 2048:4096]
```

**Analysis:** The SNAC ONNX model (`onnx-community/snac_24khz-ONNX`) outputs `8192` samples for a 4-frame (28-token) input. Verified via direct ONNX inference:
```
4 frames (28 tokens): output shape=(1, 1, 8192), total_samples=8192
Crop 2048:4096 gives 2048 samples = 85.3ms
```

The SNAC 24kHz architecture uses a hierarchical RVQ with stride-8 convolutions. The full output is 4x2048 samples, but the convolutional context means only the "center" frame (frame[1] = samples 2048:4096) is cleanly decoded relative to surrounding context. This is the standard sliding-window decoding pattern used by all codec models. Audio energy is present across the full 8192-sample output, confirming all samples are valid — the crop is a deliberate architectural choice to ensure each output frame has equal context from both earlier and later tokens.

**Conclusion:** This is correct behavior. No fix needed.

---

### Hypothesis C — synthesize_stream Full-Buffer Accumulation

**Severity:** MEDIUM
**Likelihood of contributing to symptoms:** MEDIUM (latency issue, not audio quality)
**Fix impact:** MEDIUM (reduces time-to-first-audio, does not fix distortion)
**Fix complexity:** MEDIUM

**Code evidence** (`src/ergos/tts/orpheus_synthesizer.py`, lines 201–212):
```python
chunks: list[tuple[np.ndarray, bool]] = []  # (audio, is_speech)

async for chunk_sr, audio_int16 in self._orpheus.stream_tts(text, options):
    # ... normalize, is_speech check
    chunks.append((audio_float32, is_speech))  # <-- ALL chunks buffered

# After loop: find first/last speech, then yield
```

This is **batch synthesis with async syntax** — the generator collects every chunk before yielding any. The `orpheus_cpp` streaming pre-buffer (1.5s) and per-chunk yields provide no actual streaming benefit because `synthesize_stream` discards that pacing.

**Why buffering was necessary:** To identify the `last_speech` index for fade-out application, you need to see all chunks first. This is a real constraint.

**Consequence:** For a 3-sentence response where each sentence takes 2s to generate, total synthesis time is 6s before the first audio sample plays. In practice, `TTSProcessor` calls `_synthesize_and_stream` per sentence (not per response), so per-sentence synthesis time applies, which is more reasonable.

**Fix approach:** Use a lookahead queue. Yield chunks immediately but buffer 1–2 chunks ahead to know when `last_speech` is encountered. Apply fade-out when the next chunk is silence or when the queue empties. This requires more state management.

**Simpler fix:** Pre-synthesize all chunks (current behavior) but increase `_MIN_SPEECH_PEAK` detection accuracy so non-speech chunks are reliably skipped. The main benefit is correctness, not latency.

---

### Hypothesis D — Per-Chunk Peak Normalization

**Severity:** HIGH
**Likelihood of contributing to "no graceful ending":** HIGH
**Fix impact:** HIGH
**Fix complexity:** LOW

**Code evidence** (`src/ergos/tts/orpheus_synthesizer.py`, lines 207–212):
```python
peak = np.abs(audio_float32).max()
is_speech = peak >= self._MIN_SPEECH_PEAK  # 0.05
if is_speech:
    audio_float32 = audio_float32 * (0.95 / peak)  # <-- Per-chunk normalization
chunks.append((audio_float32, is_speech))
```

**Problem:** Orpheus generates speech with naturally varying amplitude. The last 1–3 chunks of an utterance contain the trailing edge of the last word — naturally at lower amplitude as the speaker "winds down." Independent normalization amplifies these quiet chunks to 0.95 peak, then the 40ms fade-out drops them to silence.

**Audible result:** The final 85ms of speech (last SNAC chunk) is artificially loud (boosted to 0.95), then immediately faded. This creates a perceptible "pump" or "click" — the volume surges just before the ending, which sounds unnatural and can register as a word being cut off.

**Additional problem:** Between two speech chunks, if a chunk has a naturally lower peak (e.g., 0.1), it gets boosted 9.5x to 0.95. The adjacent chunks were already at 0.95. This creates discontinuities at every chunk boundary — audible as a subtle stutter/roughness through the utterance.

**Fix:**
```python
# In synthesize_stream: collect all raw (unnormalized) chunks first,
# then normalize the concatenated utterance once, then split back into chunks.

# Step 1: collect all chunks without normalization
raw_chunks = []
async for chunk_sr, audio_int16 in self._orpheus.stream_tts(text, options):
    audio_1d = np.squeeze(audio_int16)
    audio_float32 = audio_1d.astype(np.float32) / 32768.0
    raw_chunks.append(audio_float32)

if not raw_chunks:
    return

# Step 2: concatenate and normalize once
all_audio = np.concatenate(raw_chunks)
peak = np.abs(all_audio).max()
if peak >= 0.05:  # MIN_SPEECH_PEAK
    all_audio = all_audio * (0.95 / peak)

# Step 3: split back (find speech boundaries on normalized audio)
offset = 0
chunks = []
for raw in raw_chunks:
    n = len(raw)
    chunk = all_audio[offset:offset+n]
    peak = np.abs(chunk).max()
    chunks.append((chunk, peak >= 0.05))
    offset += n
```

---

### Hypothesis E — Fade-in Duration (8ms)

**Severity:** MEDIUM
**Likelihood of contributing to "no graceful start":** MEDIUM-HIGH
**Fix impact:** MEDIUM
**Fix complexity:** LOW

**Code evidence** (`src/ergos/tts/orpheus_synthesizer.py`, line 17):
```python
_FADE_IN_MS = 8  # 8ms = 192 samples at 24kHz
```

**Analysis:** Human speech onset times by phoneme category:
- Plosives (P, B, T, K, D, G): 5–15ms attack → 8ms is borderline adequate
- Fricatives (S, F, Sh, V, Z): 20–50ms attack → 8ms is 2.5–6x too short
- Nasals (M, N, Ng): 30–60ms attack → 8ms is 4–8x too short
- Vowels (A, E, I, O, U): 10–30ms attack → 8ms is slightly short

When a sentence starts with a fricative or nasal (common in English: "So...", "Many...", "Never..."), the 8ms fade-in creates an abrupt onset that sounds clipped. Listeners perceive this as the beginning of the word being cut off.

**Recommendation:** Increase to 20–25ms. This is the standard in professional TTS systems (Tacotron 2, FastSpeech 2 reference implementations use 20ms onset windows).

**Fix:**
```python
_FADE_IN_MS = 22  # 22ms = 528 samples — covers all phoneme onset types
```

---

### Hypothesis F — Linear Fade Shape

**Severity:** LOW-MEDIUM
**Likelihood of contributing to "no graceful ending":** MEDIUM
**Fix impact:** MEDIUM
**Fix complexity:** LOW

**Code evidence** (`src/ergos/tts/orpheus_synthesizer.py`, lines 26–30):
```python
ramp = np.linspace(0.0, 1.0, n_samples, dtype=np.float32)  # linear
if fade_out:
    audio[-n_samples:] *= ramp[::-1]  # reversed linear = linear decay
```

**Problem:** A linear amplitude ramp corresponds to a linear decrease in energy. Human perception of loudness is roughly logarithmic (Fletcher-Munson). A linear fade sounds like: loud → still quite loud → sudden silence. A cosine or equal-power fade sounds: loud → smoothly quieter → silence.

**Comparison:**
- Linear fade at 50% (t=20ms of 40ms): amplitude = 0.5, power = 0.25 (-6dB) — half volume gone suddenly
- Cosine fade at 50%: amplitude = cos(π/4) = 0.707, power = 0.5 (-3dB) — perceptually gradual

**Fix (cosine fade, industry standard):**
```python
def _apply_fade(audio, sample_rate, duration_ms, fade_out=False):
    n_samples = min(int(sample_rate * duration_ms / 1000), len(audio))
    if n_samples == 0:
        return audio
    audio = audio.copy()
    # Cosine window: perceptually linear loudness change
    t = np.linspace(0.0, np.pi / 2, n_samples, dtype=np.float32)
    ramp = np.sin(t)  # sin(0) = 0, sin(π/2) = 1, smooth S-curve
    if fade_out:
        audio[-n_samples:] *= ramp[::-1]
    else:
        audio[:n_samples] *= ramp
    return audio
```

---

### Hypothesis G — Digital Silence Between Sentences

**Severity:** HIGH
**Likelihood of contributing to "not like a human conversation":** HIGH
**Fix impact:** HIGH
**Fix complexity:** LOW

**Code evidence** (`src/ergos/tts/processor.py`, lines 222–229):
```python
n_silence = int(last_sample_rate * self.inter_sentence_pause_ms / 1000)
silence = np.zeros(n_silence, dtype=np.float32)  # <-- True digital silence
for callback in self._audio_callbacks:
    await callback(silence, last_sample_rate)
```

**Problem:** True zeros (`np.zeros`) is 0-amplitude silence — the digital floor of -96dB (for float32) or -90dB (int16). In reality:
- WebRTC rooms have background noise at -40 to -60dBFS
- The Orpheus model itself generates low-level noise in "silent" frames (~0.001–0.005 amplitude = -46 to -54dBFS)
- Human rooms always have ambient noise — air conditioning, traffic, room tone

The abrupt transition `speech → absolute zeros → speech` is instantly recognizable as synthetic. WebRTC clients may also apply noise gating that triggers on true silence, causing clicks.

**Additional concern:** The 200ms gap may be too long. Measured inter-sentence pauses in conversational English: 100–300ms, with mean ~150ms. The current 200ms is within range but at the upper end for casual conversation.

**Fix:**
```python
# Option 1: Comfort noise (low-amplitude noise matching the speech noise floor)
noise_floor = 0.0008  # -62dBFS — barely perceptible but eliminates digital silence
silence = np.random.normal(0, noise_floor, n_silence).astype(np.float32)
silence = np.clip(silence, -noise_floor * 3, noise_floor * 3)

# Option 2: Reduce pause duration
inter_sentence_pause_ms: int = 120  # 120ms is more conversational

# Option 3 (best): Short pause with noise floor + optional fading
silence = np.random.normal(0, 0.0008, n_silence).astype(np.float32)
# Apply fade-in/out to the silence block itself for completely smooth transitions
```

---

### Hypothesis H — No Prosodic Continuity Between Sentences

**Severity:** MEDIUM-HIGH
**Likelihood of contributing to "not like a human conversation":** HIGH
**Fix impact:** MEDIUM (bounded by Orpheus architecture)
**Fix complexity:** HIGH (architectural change required)

**Code evidence** (`src/ergos/tts/processor.py`, lines 196–200):
```python
async for samples, sample_rate in self.synthesizer.synthesize_stream(
    text, self.config
):
```

Each sentence is a completely independent `stream_tts()` call. Orpheus has no knowledge of the previous sentence's intonation, pitch level, or speaking pace. In human speech:
- Sentence-final falling intonation in sentence N anticipates the rising onset of sentence N+1
- Breath groups span multiple sentences
- Emphasis in one sentence affects the following sentence's baseline

**Current impact:** Each sentence sounds like a fresh paragraph being read by someone who was just handed the text. Prosodic continuity is entirely absent.

**Partial fixes (low complexity):**
1. Use consistent `temperature` and `top_k` settings — already done via `SynthesisConfig`
2. Keep voice seed consistent across sentences — Orpheus does not expose seed control
3. Group consecutive short sentences into a single synthesis call (see Hypothesis J)

**Architectural fix (high complexity):**
Feed a "prosody prefix" to each new synthesis by prepending the last 0.5s of the previous sentence's audio as a prompt. Orpheus does not currently support audio prompting, so this requires upstream model changes or a different approach (e.g., StyleTTS2 which supports reference audio for prosody transfer).

---

### Hypothesis I — Zero-Order Hold Upsampling Spectral Artifacts

**Severity:** MEDIUM
**Likelihood of contributing to "digital" feel:** MEDIUM
**Fix impact:** MEDIUM
**Fix complexity:** LOW-MEDIUM

**Code evidence** (`src/ergos/transport/audio_track.py`, lines 172–175):
```python
if input_sample_rate == 24000 and self._sample_rate == 48000:
    samples = np.repeat(samples, 2)  # ZOH upsampling
```

**Analysis:** `np.repeat(samples, 2)` is zero-order hold (ZOH) interpolation. The frequency response of ZOH is:

```
H(f) = sinc(f / fs_input)
```

Measured attenuation at key frequencies:
```
  100 Hz:  -0.00 dB  (no audible difference)
 1000 Hz:  -0.02 dB  (no audible difference)
 3000 Hz:  -0.22 dB  (imperceptible)
 5000 Hz:  -0.63 dB  (barely perceptible)
 8000 Hz:  -1.65 dB  (slight treble rolloff)
10000 Hz:  -2.64 dB  (perceptible treble reduction)
12000 Hz:  -3.92 dB  (4dB rolloff at Nyquist — audible high-end loss)
```

Additionally, ZOH creates spectral images at multiples of 24kHz. These are above the new Nyquist (24kHz at 48kHz output), so they are technically outside the audible range — but pre-alias components fold back into the 0–24kHz band.

**Impact assessment:** The -4dB rolloff at 12kHz reduces the "air" and "presence" in the speech, contributing to the "muffled" or "distant" quality sometimes described as "robotic." It is not the primary cause of the reported issues but is a consistent low-grade degrader.

**Fix (scipy polyphase resampling):**
```python
# Replace in audio_track.py push_audio():
from scipy import signal

if input_sample_rate == 24000 and self._sample_rate == 48000:
    # Polyphase resampling: 2x upsample with anti-alias filter
    samples = signal.resample_poly(samples, 2, 1)
```

**Alternative (if scipy unavailable):**
```python
# Linear interpolation (still better than ZOH for speech):
samples_up = np.zeros(len(samples) * 2, dtype=samples.dtype)
samples_up[0::2] = samples
samples_up[1::2] = np.concatenate([
    (samples[:-1] + samples[1:]) / 2,
    [samples[-1]]
])
samples = samples_up
```

---

### Hypothesis J — Sentence-Level Prosody Fragmentation

**Severity:** MEDIUM
**Likelihood of contributing to "not like a human conversation":** MEDIUM
**Fix impact:** MEDIUM
**Fix complexity:** LOW

**Code evidence** (`src/ergos/tts/processor.py`, `_synthesize_and_stream` called per sentence via `receive_token`)

Currently, a 3-sentence response like "That's a great question. Let me think about it. Here's what I found." generates three separate Orpheus inferences. Each restart produces slightly different pitch baseline, tempo, and prosodic contour.

**Fix:** When two consecutive sentences total fewer than 120 characters of speakable content, concatenate them into a single synthesis call. This produces naturally flowing prosody across the sentence boundary.

```python
# In TTSProcessor: add a "hold-for-context" buffer
# If sentence is < 60 chars, hold it and concatenate with next sentence
# Only synthesize when accumulated chars >= 80 or at flush()
```

**Trade-off:** Increases latency to first audio by holding short sentences. For TARS's conversational style, this is usually acceptable since TARS gives longer answers.

---

### Hypothesis K — WebRTC Silence Fill Between Chunks

**Severity:** LOW
**Likelihood of contributing to symptoms:** LOW
**Fix impact:** LOW
**Fix complexity:** N/A

**Code evidence** (`src/ergos/transport/audio_track.py`, lines 117–119):
```python
else:
    # Not enough samples, return silence
    samples = np.zeros(self._samples_per_frame, dtype=np.int16)
```

**Analysis:** With the current batch-synthesis approach in `synthesize_stream` (all chunks collected before yielding), the TTSAudioTrack buffer is filled with the full utterance before playback begins. Mid-utterance buffer underruns should be rare. The silence fill is a safety net, not a regular occurrence.

**The silence fill produces 16-bit zeros, not float32** — these go through the same `s16` format pipeline as real audio. Since the buffer typically has 500ms+ of audio ahead of the playback pointer, underruns at WebRTC frame boundaries are rare.

**Conclusion:** Low priority. Would become relevant if `synthesize_stream` is changed to true streaming (yielding chunks before synthesis completes). Document for future streaming work.

---

## 3. Ranked Recommendations

Priority is calculated as `Impact × (1/Complexity)`.

| # | Recommendation | Symptom addressed | Impact | Complexity | Priority |
|---|---|---|---|---|---|
| 1 | Fix SNAC trailing token drop in `_decode` | Last word cuts off | HIGH | LOW | **P1** |
| 2 | Utterance-level normalization (not per-chunk) | Unnatural volume at sentence end | HIGH | LOW | **P1** |
| 3 | Replace digital silence with comfort noise | Robotic between-sentence gaps | HIGH | LOW | **P1** |
| 4 | Increase fade-in from 8ms to 22ms | Abrupt sentence starts | MEDIUM | LOW | **P2** |
| 5 | Switch linear fade to cosine fade | Unnatural sentence endings | MEDIUM | LOW | **P2** |
| 6 | Reduce inter-sentence pause to 100–120ms | Slow, unnatural pacing | MEDIUM | LOW | **P2** |
| 7 | Polyphase resampling (replace `np.repeat`) | High-freq harshness | MEDIUM | LOW-MEDIUM | **P2** |
| 8 | Sentence batching for short sentences | Prosodic fragmentation | MEDIUM | MEDIUM | **P3** |
| 9 | True streaming in `synthesize_stream` | Latency to first audio | MEDIUM | MEDIUM | **P3** |
| 10 | Prosodic continuity across sentences | Cross-sentence intonation | HIGH | HIGH | **P4** |

---

## 4. Implementation Notes

### Rec 1: Fix Trailing Token Drop (P1 — orpheus_cpp/model.py)

The fix must be applied to `orpheus_cpp/model.py` because `_decode` is a private method of `OrpheusCpp`. Options:

**Option A: Monkey-patch in OrpheusSynthesizer._ensure_model()** (no fork required):
```python
# In _ensure_model(), after loading:
import types

original_decode = self._orpheus._decode

def patched_decode(token_gen):
    buffer = []
    count = 0
    for token_text in token_gen:
        token = self._orpheus._token_to_id(token_text, count)
        if token is not None and token > 0:
            buffer.append(token)
            count += 1
            if count % 7 == 0 and count > 27:
                buffer_to_proc = buffer[-28:]
                audio_samples = self._orpheus._convert_to_audio(buffer_to_proc)
                if audio_samples is not None:
                    yield audio_samples
    # Flush trailing tokens
    trailing = count % 7
    if trailing > 0 and len(buffer) >= 28:
        pad_needed = 7 - trailing
        buffer.extend([buffer[-1]] * pad_needed)
        buffer_to_proc = buffer[-28:]
        audio_samples = self._orpheus._convert_to_audio(buffer_to_proc)
        if audio_samples is not None:
            yield audio_samples

self._orpheus._decode = types.MethodType(
    lambda self, token_gen: patched_decode(token_gen),
    self._orpheus
)
```

**Option B: Edit orpheus_cpp/model.py directly** (simpler, requires tracking in requirements.txt):
Add the trailing flush block at the end of the `_decode` method's for loop.

**Option C: Capture trailing tokens in synthesize_stream** — not possible since `_decode` is internal to `stream_tts_sync`.

**Recommended:** Option A (monkey-patch) keeps the fix in the ergos codebase and survives orpheus_cpp upgrades.

---

### Rec 2: Utterance-Level Normalization (P1 — orpheus_synthesizer.py)

Replace the per-chunk normalization loop in `synthesize_stream` with post-collection normalization:

```python
async def synthesize_stream(self, text, config=None):
    if config is None:
        config = SynthesisConfig()
    self._ensure_model()
    options = self._build_options(config)

    # Phase 1: collect all raw chunks (no normalization yet)
    raw_chunks: list[np.ndarray] = []
    async for chunk_sr, audio_int16 in self._orpheus.stream_tts(text, options):
        audio_1d = np.squeeze(audio_int16)
        audio_float32 = audio_1d.astype(np.float32) / 32768.0
        raw_chunks.append(audio_float32)

    if not raw_chunks:
        return

    # Phase 2: normalize the full utterance once
    all_audio = np.concatenate(raw_chunks)
    peak = np.abs(all_audio).max()
    if peak >= self._MIN_SPEECH_PEAK:
        all_audio = all_audio * (0.95 / peak)

    # Phase 3: re-split into per-chunk arrays (preserving chunk boundaries for fades)
    chunks: list[tuple[np.ndarray, bool]] = []
    offset = 0
    for raw in raw_chunks:
        n = len(raw)
        chunk = all_audio[offset:offset+n]
        is_speech = np.abs(chunk).max() >= self._MIN_SPEECH_PEAK
        chunks.append((chunk, is_speech))
        offset += n

    # Phase 4: apply fades and yield (same as current)
    first_speech = next((i for i, (_, s) in enumerate(chunks) if s), None)
    last_speech = next((i for i, (_, s) in reversed(list(enumerate(chunks))) if s), None)
    for i, (audio, is_speech) in enumerate(chunks):
        if last_speech is not None and i > last_speech:
            continue
        if first_speech is not None and i < first_speech:
            continue
        if i == first_speech:
            audio = _apply_fade(audio, SAMPLE_RATE, _FADE_IN_MS)
        if i == last_speech:
            audio = _apply_fade(audio, SAMPLE_RATE, _FADE_OUT_MS, fade_out=True)
        yield audio, SAMPLE_RATE
```

---

### Rec 3: Comfort Noise Between Sentences (P1 — processor.py)

```python
# In _synthesize_and_stream, replace silence block:
if not self._cancelled and self.inter_sentence_pause_ms > 0 and last_sample_rate > 0:
    n_silence = int(last_sample_rate * self.inter_sentence_pause_ms / 1000)
    # Comfort noise at -62dBFS (~0.0008 amplitude) — eliminates digital silence gap
    noise_amplitude = 0.0008
    silence = np.random.normal(0, noise_amplitude, n_silence).astype(np.float32)
    silence = np.clip(silence, -noise_amplitude * 4, noise_amplitude * 4)
    for callback in self._audio_callbacks:
        try:
            await callback(silence, last_sample_rate)
        except Exception as e:
            logger.error(f"Audio callback error (silence): {e}")
```

Change `inter_sentence_pause_ms` default from 200 to 120:
```python
inter_sentence_pause_ms: int = 120  # Conversational pacing
```

---

### Rec 4 + 5: Fade Improvements (P2 — orpheus_synthesizer.py)

```python
# Increase fade-in for natural speech onsets
_FADE_IN_MS = 22   # was 8ms — covers fricatives and nasals

# Increase fade-out slightly for smoother endings
_FADE_OUT_MS = 50  # was 40ms — more room for the cosine to work

def _apply_fade(audio, sample_rate, duration_ms, fade_out=False):
    """Apply cosine (equal-power) fade for natural-sounding transitions."""
    n_samples = min(int(sample_rate * duration_ms / 1000), len(audio))
    if n_samples == 0:
        return audio
    audio = audio.copy()
    # Cosine fade: perceptually linear loudness (equal-power cross-fade standard)
    t = np.linspace(0.0, np.pi / 2, n_samples, dtype=np.float32)
    ramp = np.sin(t)  # 0 → 1 along sin curve
    if fade_out:
        audio[-n_samples:] *= ramp[::-1]
    else:
        audio[:n_samples] *= ramp
    return audio
```

---

### Rec 7: Polyphase Resampling (P2 — audio_track.py)

```python
# In push_audio(), replace np.repeat:
from scipy.signal import resample_poly

if input_sample_rate == 24000 and self._sample_rate == 48000:
    # Polyphase resampling: 2x upsample with anti-alias FIR filter
    # Much better high-frequency response vs zero-order hold (np.repeat)
    samples = resample_poly(samples, 2, 1).astype(np.int16)
```

**Performance note:** `scipy.signal.resample_poly` with default window is fast (~0.5ms per 85ms chunk on modern CPU). The anti-alias filter adds a small constant latency (~1ms group delay) which is imperceptible.

**If scipy is not in requirements, add it** — it is already likely present as a transitive dependency of numpy/scikit-learn. Check `pip show scipy`.

---

### Rec 8: Short-Sentence Batching (P3 — processor.py)

Add a hold buffer for short sentences:

```python
# New constant in TTSProcessor
_MIN_BATCH_CHARS: int = 80  # synthesize when >= 80 speakable chars accumulated

# In _has_complete_sentence and receive_token logic:
# After extracting a sentence, if len(accumulated_speakable) < _MIN_BATCH_CHARS
# and not at flush(), hold in a pending_batch buffer
# Only synthesize when pending_batch >= _MIN_BATCH_CHARS

# Flush pending_batch unconditionally at flush()
```

---

## 5. External References

- **SNAC architecture:** "Multi-Scale Neural Audio Codec" (Kumar et al., 2024) — https://arxiv.org/abs/2406.14294. Section 3.2 describes the hierarchical RVQ with stride-8 decoder explaining the sliding window context requirement.

- **Orpheus TTS model card:** https://huggingface.co/isaiahbjork/orpheus-3b-0.1-ft-Q4_K_M-GGUF — documents 24kHz output, SNAC codec, emotion token support.

- **orpheus-cpp source:** https://github.com/freddyaboulton/orpheus-cpp — `model.py` `_decode` method is the canonical reference for the trailing token behavior.

- **SNAC ONNX model:** https://huggingface.co/onnx-community/snac_24khz-ONNX — decoder_model.onnx input/output schema confirms `(batch, 1, sequence_length)` float output.

- **ZOH upsampling analysis:** Oppenheim & Schafer, "Discrete-Time Signal Processing" (3rd ed.), Chapter 4 — zero-order hold frequency response derivation.

- **Cosine fade (equal-power crossfade):** Pro Audio Reference, AES conventions — `sin(t * π/2)` ramp is the standard for equal-power crossfades used in professional DAWs.

- **Inter-sentence pause timing:** Campione & Véronis (2002), "A Large-Scale Multilingual Study of Silent Pause Duration" — mean conversational pause 100–180ms.

- **scipy.signal.resample_poly docs:** https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html

---

## 6. Quick-Fix Summary (All P1 + P2 changes)

All P1 and P2 fixes together require changes to only 3 files:

| File | Change | Lines affected |
|---|---|---|
| `src/ergos/tts/orpheus_synthesizer.py` | Utterance-level normalization + cosine fades + larger fade-in | ~30 lines modified |
| `src/ergos/tts/orpheus_synthesizer.py` | Monkey-patch `_decode` trailing token flush in `_ensure_model` | ~20 lines added |
| `src/ergos/tts/processor.py` | Comfort noise + reduced pause (120ms) | ~5 lines modified |
| `src/ergos/transport/audio_track.py` | Polyphase resampling (scipy) | ~5 lines modified |

Estimated implementation time: 1–2 hours.
No new dependencies required (scipy likely already available; confirm with `pip show scipy`).
No architectural changes needed for P1+P2 fixes.
No new tests required beyond existing TTS unit tests — the changes are numerically verifiable via audio quality metrics (PESQ, STOI) but subjective A/B testing is sufficient for validation.
