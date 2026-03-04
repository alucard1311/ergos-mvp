---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified: []
autonomous: true
requirements: []

must_haves:
  truths:
    - "Root causes of broken last word/chunk in each sentence are identified with evidence"
    - "Approaches for graceful sentence beginnings/endings are documented with tradeoffs"
    - "Concrete recommendations are prioritized by impact and complexity"
  artifacts:
    - path: ".planning/quick/1-research-smooth-human-like-tts-voice-tra/RESEARCH.md"
      provides: "Research findings and recommendations document"
      min_lines: 100
  key_links: []
---

<objective>
Research why TTS voice output sounds unnatural and identify solutions for smooth, human-like voice transitions.

Purpose: The user reports three specific issues: (1) last chunk/word of each sentence breaks or cuts off, (2) no graceful sentence beginnings/endings, (3) overall doesn't feel like natural human conversation. This research will identify root causes and recommend solutions WITHOUT implementing code changes.

Output: RESEARCH.md with root cause analysis, ranked solution recommendations, and implementation complexity estimates.
</objective>

<execution_context>
@/home/vinay/.claude/get-shit-done/workflows/execute-plan.md
@/home/vinay/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/ergos/tts/orpheus_synthesizer.py (Orpheus synthesizer with fade-in/out, per-chunk normalization)
@src/ergos/tts/processor.py (Sentence batching, inter-sentence silence)
@src/ergos/transport/audio_track.py (2x upsampling by sample repetition, WebRTC pacing)
@.venv/lib/python3.12/site-packages/orpheus_cpp/model.py (SNAC decoder, pre-buffer, stream_tts internals)

<interfaces>
<!-- Key code paths the researcher needs to understand -->

From orpheus_cpp/model.py — SNAC decoder crop (CRITICAL):
```python
# _convert_to_audio: takes 2048 samples starting at index 2048
audio_np = audio_hat[:, :, 2048:4096]
audio_int16 = (audio_np * 32767).astype(np.int16)
```

From orpheus_cpp/model.py — pre-buffer and chunking:
```python
# stream_tts_sync: buffers 1.5s before first yield, then yields per-SNAC-decode
pre_buffer_size = 24_000 * options.get("pre_buffer_size", 1.5)
# Each SNAC decode: 28 tokens -> 4 frames -> 2048 samples (~85ms at 24kHz)
if count % 7 == 0 and count > 27:
    buffer_to_proc = buffer[-28:]
    audio_samples = self._convert_to_audio(buffer_to_proc)
```

From orpheus_synthesizer.py — per-chunk normalization:
```python
# Each chunk independently normalized to 0.95 peak
peak = np.abs(audio_float32).max()
is_speech = peak >= self._MIN_SPEECH_PEAK  # 0.05
if is_speech:
    audio_float32 = audio_float32 * (0.95 / peak)
```

From audio_track.py — upsampling:
```python
# Simple 2x repetition: [a, b, c] -> [a, a, b, b, c, c]
samples = np.repeat(samples, 2)
```

From processor.py — sentence-level synthesis:
```python
# Each sentence = separate stream_tts() call
inter_sentence_pause_ms: int = 200  # flat silence gap
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Analyze root causes of broken audio at sentence boundaries</name>
  <files>.planning/quick/1-research-smooth-human-like-tts-voice-tra/RESEARCH.md</files>
  <action>
Investigate the full audio path from Orpheus token generation through WebRTC delivery, focusing on these specific hypotheses for each reported symptom:

**Symptom 1: "Last chunk of last word breaks"**

Investigate these causes IN ORDER of likelihood:

A. SNAC decoder hard crop at `audio_hat[:, :, 2048:4096]` in orpheus_cpp `_convert_to_audio()`:
   - The SNAC decoder outputs a fixed-size tensor. The code takes a 2048-sample slice (indices 2048-4096).
   - For the FINAL decode of an utterance, the model may produce fewer meaningful tokens, meaning the audio energy may extend beyond index 4096 or the 2048:4096 window may contain a truncated waveform.
   - Check: Does the SNAC ONNX model always output the same tensor shape? Is the 2048:4096 slice always the correct "valid audio" window? Are the samples before 2048 and after 4096 truly always garbage/padding?
   - Read the SNAC paper/docs to understand the decoder output format. The SNAC (Multi-Scale Neural Audio Codec) architecture may have a specific output structure where only certain indices are valid.

B. Per-chunk peak normalization creating discontinuities:
   - Each chunk is independently normalized to 0.95 peak. If the last chunk has a lower natural peak (trailing off), its quiet samples get amplified to 0.95, creating an unnatural volume spike at the end.
   - The 40ms fade-out is applied AFTER normalization, partially mitigating this, but if the chunk itself is very short, the fade-out may not have enough samples to work with.
   - Calculate: Given that each SNAC decode produces ~2048 samples (~85ms at 24kHz), and fade-out is 40ms (960 samples), what fraction of the last chunk is faded? Is this enough?

C. Pre-buffer flush behavior:
   - In `stream_tts_sync`, if total audio < 1.5s, the pre_buffer is yielded at the end (`if not started_playback: yield pre_buffer`). This means ALL audio comes as one chunk, and the fade-in/fade-out logic in `synthesize_stream` only applies to that single chunk. This is fine.
   - But if total audio > 1.5s, the pre_buffer is yielded first (1.5s), then individual ~85ms SNAC chunks follow. The LAST of these small chunks may be very short (partial SNAC decode). Check if orpheus_cpp handles the final partial set of tokens.

D. The `_decode` generator's final iteration behavior:
   - `_decode` only yields when `count % 7 == 0 and count > 27`. This means the last 1-27 tokens are SILENTLY DROPPED if total token count is not divisible by 7. These lost tokens may contain the end of the last word.
   - Calculate: 7 tokens per SNAC frame, buffer processes 28 tokens (4 frames) at a time. Tokens after the last multiple of 7 are lost. At typical Orpheus generation rate, how much audio could be lost?

**Symptom 2: "No graceful start and end"**

Investigate:

E. Fade-in (8ms) is extremely short for a natural-sounding onset. Human speech has attack times of 20-50ms. Compare with professional TTS systems.

F. Fade-out (40ms) applied with linear ramp. Human speech trails off with an exponential decay, not linear. Linear fade sounds like a hard cut softened slightly.

G. Inter-sentence silence is flat zeros (200ms). Real speech has ambient room tone between sentences, not digital silence. The transition from speech -> absolute silence -> speech creates an obvious "digital" feel.

H. No prosodic continuity between sentences. Each sentence is a completely independent `stream_tts()` call. Orpheus has no context from the previous sentence, so intonation, pitch, and pace restart from scratch each time. In human speech, sentences flow with continuous prosody.

**Symptom 3: "Doesn't feel like a human conversation"**

Investigate:

I. Sample repetition upsampling (`np.repeat(samples, 2)` for 24kHz->48kHz). This is zero-order hold, which introduces spectral imaging (aliasing) at the Nyquist frequency. The result is a subtle harshness/buzziness that the ear perceives as "digital". Compare with proper sinc interpolation or polyphase filter upsampling.

J. Sentence chunking granularity. The `_MIN_SPEAKABLE_CHARS = 20` threshold and sentence-ending detection means short phrases get batched, but each sentence still gets independent synthesis. Multi-sentence prosody (paragraph-level intonation contour) is completely lost.

K. WebRTC 20ms frame pacing with silence fill. When the TTS buffer runs dry between chunks, `recv()` returns silence frames. These micro-gaps may be audible as tiny clicks or brief dropouts.

For each hypothesis, document:
- Evidence from code analysis
- Likelihood of contributing to the reported symptom (HIGH/MEDIUM/LOW)
- Impact if fixed (HIGH/MEDIUM/LOW)
- Implementation complexity (LOW/MEDIUM/HIGH)

Then write up the RESEARCH.md with findings structured as:
1. Executive Summary (top 3 issues)
2. Root Cause Analysis (detailed per-hypothesis findings)
3. Ranked Recommendations (by impact/effort ratio)
4. Implementation Notes (specific code changes needed for each recommendation)
5. External References (SNAC paper, Orpheus model card, upsampling best practices)

The RESEARCH.md should be detailed enough that a developer could implement fixes without additional research.
  </action>
  <verify>
    <automated>test -f .planning/quick/1-research-smooth-human-like-tts-voice-tra/RESEARCH.md && wc -l .planning/quick/1-research-smooth-human-like-tts-voice-tra/RESEARCH.md | awk '{if ($1 >= 100) print "PASS"; else print "FAIL: only " $1 " lines"}'</automated>
  </verify>
  <done>RESEARCH.md exists with 100+ lines covering all three reported symptoms, root cause analysis for each hypothesis (A-K), ranked recommendations with impact/effort ratings, and specific implementation notes</done>
</task>

</tasks>

<verification>
- RESEARCH.md covers all three user-reported symptoms
- Each hypothesis has evidence, likelihood, and impact ratings
- Recommendations are ranked by impact/effort ratio
- Implementation notes are specific enough to code from
</verification>

<success_criteria>
- Root causes of "last chunk breaking" are identified with code-level evidence
- At least 3 concrete recommendations for natural-sounding transitions are documented
- Each recommendation has clear implementation path and complexity estimate
- Research covers the full audio path: Orpheus generation -> SNAC decode -> normalization -> upsampling -> WebRTC delivery
</success_criteria>

<output>
After completion, create `.planning/quick/1-research-smooth-human-like-tts-voice-tra/1-SUMMARY.md`
</output>
