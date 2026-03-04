---
phase: 16
slug: tars-personality
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-04
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` — `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/python -m pytest tests/unit/test_tars_personality.py tests/unit/test_tars_memory.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest tests/unit/ -q --ignore=test_combined.py --ignore=test_local.py` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/unit/test_tars_personality.py tests/unit/test_tars_memory.py -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/unit/ -q --ignore=test_combined.py --ignore=test_local.py`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 16-01-01 | 01 | 1 | PERS-01 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestPromptBuilder::test_neutral_prompt_has_no_humor -x` | ❌ W0 | ⬜ pending |
| 16-01-02 | 01 | 1 | PERS-01 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestPromptBuilder::test_max_sarcasm_prompt_has_humor -x` | ❌ W0 | ⬜ pending |
| 16-01-03 | 01 | 1 | PERS-01 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestPromptBuilder::test_mid_sarcasm_prompt -x` | ❌ W0 | ⬜ pending |
| 16-01-04 | 01 | 1 | PERS-01 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestSarcasmCommand::test_set_sarcasm_command_parsed -x` | ❌ W0 | ⬜ pending |
| 16-01-05 | 01 | 1 | PERS-01 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestPersonaConfig::test_sarcasm_level_field -x` | ❌ W0 | ⬜ pending |
| 16-02-01 | 02 | 1 | PERS-02 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestTimeContext::test_time_context_periods -x` | ❌ W0 | ⬜ pending |
| 16-02-02 | 02 | 1 | PERS-02 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestPromptBuilder::test_memories_injected -x` | ❌ W0 | ⬜ pending |
| 16-03-01 | 03 | 2 | PERS-03 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryStore::test_load_empty -x` | ❌ W0 | ⬜ pending |
| 16-03-02 | 03 | 2 | PERS-03 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryStore::test_roundtrip -x` | ❌ W0 | ⬜ pending |
| 16-03-03 | 03 | 2 | PERS-03 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryStore::test_prune -x` | ❌ W0 | ⬜ pending |
| 16-03-04 | 03 | 2 | PERS-03 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryStore::test_budget -x` | ❌ W0 | ⬜ pending |
| 16-03-05 | 03 | 2 | PERS-03 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryExtraction::test_parse_categories -x` | ❌ W0 | ⬜ pending |
| 16-03-06 | 03 | 2 | PERS-03 | unit | `.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryExtraction::test_skip_short_history -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_tars_personality.py` — stubs for PERS-01 (prompt builder, sarcasm command, PersonaConfig, time context), PERS-02 (memory injection into prompt)
- [ ] `tests/unit/test_tars_memory.py` — stubs for PERS-03 (MemoryStore CRUD, prune, budget, extraction parsing)

*Existing infrastructure covers framework — no new installs needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Sarcasm tone audibly changes at different levels | PERS-01 | Subjective audio quality assessment | Set sarcasm_level to 0, 50, 100; verify response tone differs |
| Context-aware humor references current conversation | PERS-02 | Requires live LLM conversation | Chat about a topic, verify TARS references it humorously |
| Cross-session memory recall | PERS-03 | Requires two separate sessions | Share a preference in session 1, verify recall in session 2 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
