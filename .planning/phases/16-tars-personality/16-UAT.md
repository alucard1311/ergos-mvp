---
status: testing
phase: 16-tars-personality
source: [16-01-SUMMARY.md, 16-02-SUMMARY.md, 16-03-SUMMARY.md]
started: 2026-03-04T06:00:00Z
updated: 2026-03-04T23:50:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 2
name: Sarcasm Voice Command Changes Level
expected: |
  During a voice session, say "set sarcasm to 50%". The system should intercept this as a command (NOT pass it to the LLM), and speak an Ergos-style confirmation acknowledging the new sarcasm level. The command should not appear as a regular conversation turn.
awaiting: user response

## Tests

### 1. Ergos Persona Loads as Default
expected: Start the server with `ergos start`. Check logs or config output — the default persona should be "Ergos". The persona should have is_ergos_persona: true and sarcasm_level: 75 by default.
result: issue
reported: "Default persona was named TARS instead of Ergos — all TARS references renamed to Ergos"
severity: major

### 2. Sarcasm Voice Command Changes Level
expected: During a voice session, say "set sarcasm to 50%". The system should intercept this as a command (NOT pass it to the LLM), and speak an Ergos-style confirmation acknowledging the new sarcasm level. The command should not appear as a regular conversation turn.
result: issue
reported: "Said set sarcasm to 50 percent and it got stuck in processing"
severity: blocker

### 3. Sarcasm Level Affects Response Tone
expected: At sarcasm level 0%, responses should be neutral and helpful. At sarcasm level 100%, responses should have maximum dry wit — noticeably different tone, with sarcastic observations and deadpan humor.
result: [pending]

### 4. Cross-Session Memory Persists
expected: After having a conversation where you mention a personal preference (e.g., "I prefer Python over JavaScript"), disconnect. Check that ~/.ergos/memory.json exists and contains extracted memories from the session. Reconnect — the AI should be able to reference things from the previous session without being re-told.
result: [pending]

### 5. Memory Extraction on Peer Disconnect
expected: Have a conversation with at least 4 exchanges. Disconnect the WebRTC session. Check server logs — memory extraction should run in the background (via generator.generate). The extraction should NOT block or delay the disconnect. ~/.ergos/memory.json should be updated with new entries.
result: [pending]

### 6. Unit Tests All Pass
expected: Run `.venv/bin/pytest tests/unit/test_ergos_personality.py tests/unit/test_ergos_memory.py -v`. All 30 tests (17 personality + 13 memory) should pass with no failures or errors.
result: [pending]

## Summary

total: 6
passed: 0
issues: 1
pending: 5
skipped: 0

## Gaps

- truth: "Default persona should be named Ergos with is_ergos_persona: true"
  status: resolved
  reason: "User reported: default persona was named TARS instead of Ergos — renamed all TARS references to Ergos"
  severity: major
  test: 1
  root_cause: "Phase 16 used TARS as placeholder name; project is named Ergos"
  artifacts:
    - path: "src/ergos/persona/builder.py"
      issue: "Class and constants named TARS*"
    - path: "src/ergos/persona/loader.py"
      issue: "DEFAULT_PERSONA.name was TARS"
    - path: "src/ergos/persona/types.py"
      issue: "is_tars_persona field"
  missing: []
