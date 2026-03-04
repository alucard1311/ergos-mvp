---
phase: 14
slug: full-duplex-conversation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-03
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7+ |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `python3 -m pytest tests/unit/test_full_duplex.py -x -q` |
| **Full suite command** | `python3 -m pytest tests/unit/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/unit/test_full_duplex.py -x -q`
- **After every plan wave:** Run `python3 -m pytest tests/unit/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 0 | VOICE-01, VOICE-02, VOICE-03 | unit | `python3 -m pytest tests/unit/test_full_duplex.py -x -q` | ❌ W0 | ⬜ pending |
| 14-02-01 | 02 | 1 | VOICE-02 | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_speaking_and_listening_state_exists -x` | ❌ W0 | ⬜ pending |
| 14-02-02 | 02 | 1 | VOICE-02 | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_state_transitions_speaking_and_listening -x` | ❌ W0 | ⬜ pending |
| 14-02-03 | 02 | 1 | VOICE-02 | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_audio_routing_speaking_and_listening -x` | ❌ W0 | ⬜ pending |
| 14-03-01 | 03 | 1 | VOICE-03 | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_barge_in_cancel_sequence -x` | ❌ W0 | ⬜ pending |
| 14-03-02 | 03 | 1 | VOICE-03 | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_barge_in_from_speaking_and_listening -x` | ❌ W0 | ⬜ pending |
| 14-03-03 | 03 | 1 | VOICE-03 | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_llm_generator_cancel_reset -x` | ❌ W0 | ⬜ pending |
| 14-04-01 | 04 | 1 | VOICE-01 | unit | `python3 -m pytest tests/unit/test_full_duplex.py::test_latency_tracker_p50 -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_full_duplex.py` — stubs for all VOICE-01/02/03 unit tests
- [ ] No conftest changes needed — existing `tests/unit/` pattern applies

*Existing infrastructure covers framework installation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Sub-300ms P50 latency end-to-end | VOICE-01 | Requires real model inference timing | Start voice conversation, measure speech-end to first-audio P50 across 10+ exchanges |
| Barge-in stops audio within 200ms | VOICE-03 | Requires real audio playback timing | Speak while AI is talking, verify audio stops within 200ms subjectively |
| SPEAKING_AND_LISTENING orb animation | VOICE-02 | Visual UI verification | Observe Flutter orb shows unique animation during overlap state |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
