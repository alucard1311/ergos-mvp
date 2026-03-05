---
phase: 17
slug: agentic-execution
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-05
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.0+ (installed in dev deps) |
| **Config file** | `pyproject.toml` — `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/unit/test_tool_registry.py tests/unit/test_tool_executor.py tests/unit/test_tool_processor.py -x -q` |
| **Full suite command** | `uv run pytest tests/unit/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_tool_registry.py tests/unit/test_tool_executor.py tests/unit/test_tool_processor.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/unit/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 0 | AGENT-04 | unit | `uv run pytest tests/unit/test_tool_registry.py -x -q` | ❌ W0 | ⬜ pending |
| 17-01-02 | 01 | 0 | AGENT-01 | unit | `uv run pytest tests/unit/test_tool_executor.py -x -q` | ❌ W0 | ⬜ pending |
| 17-01-03 | 01 | 0 | AGENT-02, AGENT-03 | unit | `uv run pytest tests/unit/test_tool_processor.py -x -q` | ❌ W0 | ⬜ pending |
| 17-02-01 | 02 | 1 | AGENT-04 | unit | `uv run pytest tests/unit/test_tool_registry.py::test_yaml_loading -x -q` | ❌ W0 | ⬜ pending |
| 17-02-02 | 02 | 1 | AGENT-04 | unit | `uv run pytest tests/unit/test_tool_registry.py::test_tool_added_after_reload -x -q` | ❌ W0 | ⬜ pending |
| 17-03-01 | 03 | 1 | AGENT-01 | unit | `uv run pytest tests/unit/test_tool_executor.py::test_file_read -x -q` | ❌ W0 | ⬜ pending |
| 17-03-02 | 03 | 1 | AGENT-01 | unit | `uv run pytest tests/unit/test_tool_executor.py::test_shell_run_basic -x -q` | ❌ W0 | ⬜ pending |
| 17-04-01 | 04 | 2 | AGENT-02 | unit | `uv run pytest tests/unit/test_tool_processor.py::test_narration_before_tool -x -q` | ❌ W0 | ⬜ pending |
| 17-04-02 | 04 | 2 | AGENT-02 | unit | `uv run pytest tests/unit/test_tool_processor.py::test_narration_after_tool -x -q` | ❌ W0 | ⬜ pending |
| 17-04-03 | 04 | 2 | AGENT-03 | unit | `uv run pytest tests/unit/test_tool_processor.py::test_multi_step_chain -x -q` | ❌ W0 | ⬜ pending |
| 17-04-04 | 04 | 2 | AGENT-03 | unit | `uv run pytest tests/unit/test_tool_processor.py::test_max_steps_limit -x -q` | ❌ W0 | ⬜ pending |
| 17-05-01 | 05 | 3 | AGENT-01..04 | integration | `uv run pytest tests/unit/test_tool_processor.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_tool_registry.py` — stubs for AGENT-04 (registry loading, YAML parsing, reload)
- [ ] `tests/unit/test_tool_executor.py` — stubs for AGENT-01 (file_read, shell_run, file_list dispatch)
- [ ] `tests/unit/test_tool_processor.py` — stubs for AGENT-02, AGENT-03 (narration, agentic loop, max steps)
- [ ] `~/.ergos/tools/default.yaml` — example tool registry YAML

*No new framework install needed — pytest and uv are already configured.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Voice narration timing feels natural | AGENT-02 | Subjective audio quality | Ask "read my home directory", verify spoken "Let me check..." before and "Done." after |
| Multi-step chain completes end-to-end | AGENT-03 | Requires live LLM inference | Ask "find and read the config file", verify chained tool calls work |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
