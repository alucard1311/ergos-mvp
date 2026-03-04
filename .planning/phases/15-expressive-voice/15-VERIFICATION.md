---
phase: 15-expressive-voice
verified: 2026-03-03T00:00:00Z
status: human_needed
score: 9/10 must-haves verified
re_verification: false
human_verification:
  - test: "Listen to Orpheus TTS output vs Kokoro output"
    expected: "Orpheus voice sounds perceptibly more expressive — emotion tags render as audible laughter/sighs/chuckles, sarcastic responses have characteristic timing pauses with ellipsis-converted commas"
    why_human: "Audio quality difference is perceptual — cannot be verified by grep or import checks. Plan 02 Task 2 is explicitly a blocking human-verify checkpoint."
---

# Phase 15: Expressive Voice Verification Report

**Phase Goal:** Add expressive voice synthesis with emotion tags and sarcasm delivery timing
**Verified:** 2026-03-03
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

**From 15-01-PLAN.md must_haves:**

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | User can select engine='orpheus' in config.yaml and Ergos uses Orpheus TTS | VERIFIED | `config.yaml` has `orpheus_voice: tara`, `orpheus_n_gpu_layers: -1`. `TTSConfig.engine` comment updated to `"kokoro", "csm", or "orpheus"`. `pipeline.py` line 244-251: `elif config.tts.engine == "orpheus"` branch creates `OrpheusSynthesizer`. |
| 2 | Orpheus TTS produces 24kHz audio with emotion tags rendered as audible expression | VERIFIED (automated) / HUMAN NEEDED (perceptual) | `OrpheusSynthesizer.sample_rate` returns 24000. Emotion tags (`<laugh>`, `<sigh>`, etc.) are passed through to `orpheus_cpp.tts()` and `stream_tts()` unchanged. Perceptual rendering requires human listening test. |
| 3 | Orpheus model registers correct VRAM estimate and fits within 16GB budget | VERIFIED | `pipeline.py` line 251: `vram_monitor.register_model("orpheus-3b-q4", 2000.0, "tts")`. VRAM guard at line 152: `if config.tts.engine not in ("csm", "orpheus")` prevents double-counting Kokoro. Total: STT ~1GB + LLM ~5.2GB + TTS ~2GB = ~8.2GB — within 16GB budget. |
| 4 | Kokoro remains the default engine when no engine change is made | VERIFIED | `config.yaml` has `engine: kokoro`. `TTSConfig.engine` default is `"kokoro"`. 25 CSM tests still pass (no regression). |

**From 15-02-PLAN.md must_haves:**

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 5 | LLM output containing emotional cues gets Orpheus emotion tags injected before TTS | VERIFIED | `processor.py` line 111: `text = self._emotion_markup.process(text, engine=self.engine)` called in `_synthesize_and_stream` before synthesis. `EmotionMarkupProcessor.EMOTION_MAP` maps all 11 hint variants. Test `test_synthesize_calls_emotion_markup_when_orpheus` passes. |
| 6 | Sarcastic responses include timing pauses (ellipsis -> silence) for dry delivery | VERIFIED | `emotion_markup.py` `_inject_sarcasm_pauses()` replaces `...` with `, ` (comma+space). Manual verification: `e.process('Oh... sure... that is great', 'orpheus')` returns `'Oh, sure, that is great'`. 3 sarcasm pause tests pass. |
| 7 | Questions get natural rising intonation via no special markup (Orpheus handles naturally) | VERIFIED | `test_question_passes_through_unchanged` passes. `process("What is the weather?", "orpheus")` returns unchanged text. Perceptual verification of intonation is human-only. |
| 8 | Commands and imperative sentences get natural emphasis via Orpheus prosody (no special markup needed) | VERIFIED | `TestCommandPassthrough` — 4 tests pass. "Turn off the lights.", "Open the file now.", "Stop the music now." all pass through unchanged. |
| 9 | Emotion markup is only active when engine is orpheus — Kokoro text passes through unmodified | VERIFIED | `emotion_markup.py` line 52: `if engine != "orpheus": return text`. `TestEnginePassthrough` — 4 tests pass (kokoro, csm, default, unknown all get passthrough). |
| 10 | User can hear perceptible difference between flat Kokoro and expressive Orpheus output | HUMAN NEEDED | Perceptual audio quality cannot be verified programmatically. Plan 02 Task 2 is an explicit blocking human-verify checkpoint. SUMMARY notes "Human-verify checkpoint: APPROVED by user" — but this is a claim in the SUMMARY, not independently verifiable here. |

**Score: 9/10 truths verified (1 requires human confirmation)**

---

## Required Artifacts

### Plan 01 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/ergos/tts/orpheus_synthesizer.py` | OrpheusSynthesizer wrapper with lazy loading and streaming | VERIFIED | EXISTS, 187 lines. Substantive: implements `synthesize()`, `synthesize_stream()`, `model_loaded`, `sample_rate`, `close()`, `_ensure_model()`. Wired: imported in `tts/__init__.py`, used in `pipeline.py` line 245. |
| `src/ergos/tts/types.py` | Updated SynthesisConfig with orpheus_voice field | VERIFIED | EXISTS. Contains `orpheus_voice: str = "tara"` at line 29. Comment lists all valid voice IDs. |
| `src/ergos/config.py` | TTSConfig with engine='orpheus' option | VERIFIED | EXISTS. `orpheus_voice: str = "tara"`, `orpheus_n_gpu_layers: int = -1`, engine comment includes "orpheus". |
| `tests/unit/test_tts_orpheus.py` | Unit tests for OrpheusSynthesizer and engine selection | VERIFIED | EXISTS, 438 lines (min_lines: 80 satisfied). 30 tests across 5 test classes. All 30 pass. |

### Plan 02 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/ergos/tts/emotion_markup.py` | EmotionMarkupProcessor with emotion tag conversion | VERIFIED | EXISTS, 109 lines (min_lines: 60 satisfied). Exports `EmotionMarkupProcessor`. EMOTION_MAP has 11 entries. Implements `process()`, `_convert_emotion_hints()`, `_inject_sarcasm_pauses()`. |
| `tests/unit/test_emotion_markup.py` | Unit tests for emotion markup transformation rules | VERIFIED | EXISTS, 349 lines (min_lines: 80 satisfied). 39 tests across 7 test classes. All 39 pass. |

---

## Key Link Verification

### Plan 01 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/ergos/pipeline.py` | `src/ergos/tts/orpheus_synthesizer.py` | `engine=='orpheus'` branch in `create_pipeline` | WIRED | `pipeline.py` line 244: `elif config.tts.engine == "orpheus": from ergos.tts.orpheus_synthesizer import OrpheusSynthesizer`. Pattern "OrpheusSynthesizer" confirmed. |
| `src/ergos/tts/orpheus_synthesizer.py` | `orpheus-cpp` | `OrpheusCpp` import in `_ensure_model` | WIRED | `orpheus_synthesizer.py` line 74: `from orpheus_cpp import OrpheusCpp`. Import is inside `_ensure_model()` (lazy — correct). |
| `src/ergos/pipeline.py` | `src/ergos/core/vram.py` | `register_model` for orpheus-3b | WIRED | `pipeline.py` line 251: `vram_monitor.register_model("orpheus-3b-q4", 2000.0, "tts")`. Pattern "register_model.*orpheus" confirmed. |

### Plan 02 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/ergos/tts/processor.py` | `src/ergos/tts/emotion_markup.py` | `EmotionMarkupProcessor` called before synthesis | WIRED | `processor.py` line 7: `from .emotion_markup import EmotionMarkupProcessor`. Line 34: `_emotion_markup: EmotionMarkupProcessor = field(default_factory=EmotionMarkupProcessor, init=False)`. Line 111: `text = self._emotion_markup.process(text, engine=self.engine)`. |
| `src/ergos/llm/processor.py` | system prompt | Updated prompt instructs LLM to use emotion hints | WIRED | `llm/processor.py` lines 36-42: system_prompt contains "emotion hints like *laughs*, *sighs*, *chuckles*" and "Use ellipsis (...) for dramatic pauses or sarcastic timing." Pattern "emotion" confirmed. |
| `src/ergos/pipeline.py` | `src/ergos/tts/processor.py` | `engine=config.tts.engine` kwarg to TTSProcessor | WIRED | `pipeline.py` line 270: `tts_processor = TTSProcessor(synthesizer=tts_synthesizer, config=tts_config, engine=config.tts.engine)`. Pattern `engine=config\.tts\.engine` confirmed. |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| VOICE-04 | 15-01, 15-02 | AI voice has natural prosody with emotion, pauses, and timed delivery for sarcasm | SATISFIED (automated) / HUMAN NEEDED (perceptual) | OrpheusSynthesizer passes emotion tags to orpheus-cpp. EmotionMarkupProcessor converts `*laughs*` -> `<laugh>`, ellipsis -> comma pauses. System prompt guides LLM to emit emotion hints. All 69 related tests pass. Perceptual quality requires human confirmation. |

No orphaned requirements: VOICE-04 is the sole requirement claimed by both plans. REQUIREMENTS.md line 189 confirms `VOICE-04 | Phase 15 | Complete`.

---

## Anti-Patterns Found

No anti-patterns detected in any of the modified files:
- `src/ergos/tts/orpheus_synthesizer.py` — No TODOs, no stubs, no empty implementations
- `src/ergos/tts/emotion_markup.py` — No TODOs, no stubs, no placeholders
- `src/ergos/tts/processor.py` — No TODOs, no stubs
- `src/ergos/llm/processor.py` — No TODOs, no stubs
- `src/ergos/pipeline.py` — No TODOs, no stubs

---

## Test Suite Results

```
tests/unit/test_tts_orpheus.py    30 passed
tests/unit/test_emotion_markup.py 39 passed
tests/unit/test_tts_csm.py        25 passed (no regression)
Total: 69 phase-15 tests pass, 25 CSM tests pass without regression
```

---

## Human Verification Required

### 1. Perceptual Expressiveness Comparison

**Test:** With Orpheus model downloaded (pip install ergos[orpheus], ~2GB download), set config.yaml `tts.engine: orpheus`, start Ergos, connect with Flutter client. Have a conversation that includes something funny. Then switch back to `engine: kokoro` and compare the same response.

**Expected:** Orpheus voice sounds perceptibly more expressive than Kokoro. Responses including `*laughs*` in LLM output should produce audible laughter. Sarcastic responses with ellipsis should have characteristic timing pauses. Questions should have natural rising intonation. Commands should sound firm.

**Why human:** Audio expressiveness is perceptual. No automated test can verify that a model "sounds more natural." This is a fundamental limitation of text-based verification.

**Note:** The 15-02-SUMMARY.md records "Human-verify checkpoint: APPROVED by user" (line 114). This is a SUMMARY claim. Whether this approval occurred for the actual running system cannot be verified programmatically.

---

## Verification Summary

Phase 15 is **functionally complete** from a code perspective. All automated checks pass:

- OrpheusSynthesizer: EXISTS, SUBSTANTIVE (187 lines, full implementation), WIRED (imported in `__init__.py`, used in `pipeline.py`)
- EmotionMarkupProcessor: EXISTS, SUBSTANTIVE (109 lines, 11-entry EMOTION_MAP, regex conversion + sarcasm pauses), WIRED (called in `TTSProcessor._synthesize_and_stream`)
- Config support: `TTSConfig.engine='orpheus'` works, `orpheus_voice` and `orpheus_n_gpu_layers` fields present
- Pipeline wiring: `engine=config.tts.engine` passes through to TTSProcessor; VRAM registered at 2000MB
- System prompt: Updated with emotion hint guidance and ellipsis examples
- No regressions: Kokoro remains default, CSM tests all pass
- No anti-patterns: No TODOs, stubs, or placeholders

The sole outstanding item is the perceptual audio quality check (Plan 02, Task 2, human-verify checkpoint), which cannot be automated. The SUMMARY records user approval of this checkpoint.

---

_Verified: 2026-03-03_
_Verifier: Claude (gsd-verifier)_
