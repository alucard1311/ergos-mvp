# Phase 16: TARS Personality - Research

**Researched:** 2026-03-04
**Domain:** LLM persona engineering, system prompt blending, persistent memory, voice command parsing
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Sarcasm Calibration**
- System prompt blending approach: two prompt templates (neutral TARS + maximum sarcasm TARS) that interpolate based on sarcasm level
- 0% sarcasm = still TARS personality (competent, direct, slightly robotic cadence) but no humor — serious mission mode
- 100% sarcasm = movie-accurate TARS: deadpan observations, understated humor, occasional backhanded compliments, never mean
- Runtime adjustable: config.yaml sets default sarcasm_level, also changeable via voice command ("set sarcasm to 80%") or API call during a session without restart
- Sarcasm slider controls both intensity AND frequency of humor — at high sarcasm, every response has personality flavor

**Persistent Memory**
- LLM self-extraction: at end of each conversation, ask the LLM to identify memorable moments and new facts about the user from chat history
- What gets remembered: user preferences (likes, dislikes, habits), factual info about user, and key conversation moments (jokes that landed, running gags, notable exchanges)
- No full conversation logs stored — only extracted memories
- Storage: JSON file at ~/.ergos/memory.json (consistent with existing kitchen plugin pattern)
- Fixed budget injection: load up to N memories (most recent + important) into system prompt each conversation, with a cap to keep context usage predictable
- Pruning: oldest/least-used memories dropped when cap exceeded

**TARS Persona Definition**
- Dedicated TARS template: a specific curated persona file with pre-written system prompt text, example exchanges, and sarcasm tier definitions — polished out of the box
- TARS is the default persona for v2.0 — replaces current generic "helpful voice assistant" when no persona_file is specified
- User-configurable name: defaults to "TARS" but user can rename (e.g., "Jarvis", "Friday") while keeping personality style
- Persona guides emotion markup: TARS system prompt instructs LLM WHEN to use emotion hints based on sarcasm level — low sarcasm = fewer *sighs* and pauses, high sarcasm = more strategic emotion hints. EmotionMarkupProcessor (Phase 15) handles the conversion unchanged

**Context-Aware Humor**
- Context sources: current conversation topics + persistent memories from past sessions + time awareness (time of day, day of week)
- Time awareness enables situational humor: "It's 3am and you're asking about productivity? Noted."
- No external context (screen, apps) — that's Phase 18
- At high sarcasm levels, every response has wit or dry observation — TARS never gives a "straight" answer at 100%
- No explicit humor boundaries needed — TARS's deadpan style naturally avoids problematic territory
- Running jokes emerge organically from memory + personality combination rather than being specifically engineered

### Claude's Discretion
- Exact system prompt template wording for neutral and max-sarcasm tiers
- Number of memories in the fixed budget cap
- Memory extraction prompt design (what to ask the LLM to extract)
- How to interpolate between prompt templates at intermediate sarcasm levels
- Session-end trigger for memory extraction (on disconnect? on idle timeout?)
- Time awareness injection format in system prompt

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PERS-01 | AI has TARS-like dry wit with configurable sarcasm level (0-100%) | System prompt blending technique; two-template interpolation; Qwen3-compatible chatml format |
| PERS-02 | AI makes context-aware jokes referencing current activity and past conversations | Time-of-day injection into system prompt; persistent memory injected as context block |
| PERS-03 | AI remembers conversation history, user preferences, and running jokes across sessions | LLM self-extraction at session end; JSON storage at ~/.ergos/memory.json; budget injection pattern |
</phase_requirements>

---

## Summary

Phase 16 is a pure prompt engineering and lightweight storage phase — no new model loading, no hardware changes. The work lives in four contained modules: (1) a curated TARS persona file with two-tier prompt templates, (2) a `TARSPromptBuilder` that blends neutral/max-sarcasm templates by sarcasm level and injects time/memory context, (3) a `MemoryStore` class following the kitchen plugin pattern for JSON persistence, and (4) a memory extraction call that runs at session end. The sarcasm slider is a simple integer stored in `PersonaConfig`, used to linearly interpolate paragraph text from two template strings. Voice command parsing for "set sarcasm" uses a regex intent check inside the existing `process_transcription` pipeline gate.

The key design insight is that all interpolation happens at the string level — no token probability mixing, no fine-tuning. The "interpolation" is semantic: the two template strings are composed of natural-language paragraphs describing behavior, and the blend at intermediate sarcasm levels is achieved by selecting which paragraphs to include (section-based selection) or by mixing explicit percentage-qualified instructions ("respond with humor on roughly 60% of turns"). This approach is simpler and more debuggable than probability-level mixing, and works correctly with Qwen3-8B Q4_K_M running under llama-cpp-python.

Qwen3 ships without a default system prompt and responds well to role persona instructions in the chatml system turn. The `/no_think` tag is the recommended way to keep responses concise for voice (placed at the end of the system message), but evidence from the llama.cpp community (March 2026) shows it is unreliable via llama-cpp-python `create_completion` — the safer approach is to keep `no_think` behavior enforced by the existing "Keep responses to 1-3 sentences" instruction already in the system prompt, which has proven reliable through Phase 15.

**Primary recommendation:** Build TARSPromptBuilder as a standalone class that `pipeline.py` calls at startup and on sarcasm-level change. Keep memory extraction as a simple async method on MemoryStore triggered by the WebRTC disconnect event. Keep everything stateless across requests — only the sarcasm_level attribute changes at runtime.

---

## Standard Stack

### Core (all already in project dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `json` | — | Memory persistence (read/write ~/.ergos/memory.json) | Follows existing kitchen plugin pattern |
| Python stdlib `datetime` | — | Time-of-day / day-of-week context injection | Zero dependency, always correct |
| Python stdlib `re` | — | Voice command intent parsing ("set sarcasm to N%") | Already used in pipeline.py |
| Pydantic `BaseModel` | 2.x (already in project) | PersonaConfig extension with sarcasm_level field | Existing config pattern |
| `yaml` (PyYAML, already installed) | — | TARS persona YAML file loading | Existing persona loader uses it |

### No New Dependencies Required
All work for this phase uses libraries already present in the project. No `pip install` needed.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| JSON flat file | SQLite / mem0 / LangGraph Store | Overkill for single-user, single-assistant scenario; adds dependencies; JSON file is 100% aligned with existing kitchen plugin pattern |
| Regex intent parsing | Snips NLU / intent classifier | Full NLU library is massive overhead for a single "set sarcasm to N%" command; regex is sufficient and follows existing intent.py pattern |
| String-section interpolation | Probability-level token mixing (Interpolative Decoding) | Token mixing requires direct logit access not available through llama-cpp-python's `create_completion`; string approach is correct, debuggable, and proven |

---

## Architecture Patterns

### Recommended Project Structure Changes
```
src/ergos/
├── persona/
│   ├── types.py          # EXTEND: add sarcasm_level, prompt_builder method
│   ├── loader.py         # EXTEND: load TARS default, load sarcasm_level from config
│   ├── builder.py        # NEW: TARSPromptBuilder — blends templates, injects memory/time
│   └── tars.yaml         # NEW: curated TARS persona file with two-tier templates
├── memory/
│   ├── __init__.py       # NEW: package
│   ├── store.py          # NEW: MemoryStore — JSON persistence at ~/.ergos/memory.json
│   └── types.py          # NEW: MemoryEntry dataclass
├── config.py             # EXTEND: PersonaConfig.sarcasm_level: int = 75
└── pipeline.py           # EXTEND: wire memory extraction on disconnect
```

```
~/.ergos/
├── memory.json           # Cross-session memory (created on first extraction)
└── personas/
    └── tars.yaml         # Optional user override of built-in TARS
```

### Pattern 1: Section-Based Sarcasm Prompt Blending

**What:** Two canonical template strings (TARS_NEUTRAL and TARS_MAX_SARCASM) each composed of labelled sections. At sarcasm_level 0-100, a `TARSPromptBuilder` selects which personality sections to include and adjusts frequency language ("on some turns" vs "on every turn").

**When to use:** Always — this is the only sarcasm interpolation method.

**Why this approach:** llama-cpp-python `create_completion` does not expose logit arrays, so probability-level mixing (the academic "Interpolative Decoding" approach) is impossible without forking the library. String-section selection achieves the same perceptual result with zero additional complexity.

**Example:**
```python
# Source: project pattern, informed by CONTEXT.md decisions

TARS_NEUTRAL_SECTIONS = {
    "identity": (
        "You are {name}, a highly capable AI assistant. "
        "You are competent, direct, and precise. "
        "You answer questions efficiently without embellishment."
    ),
    "style": (
        "Speak in the manner of a mission-critical system: calm, measured, and reliable. "
        "Keep responses to 1-3 sentences for voice delivery. "
        "Never use markdown, bullet points, or lists."
    ),
    "emotion": (
        "Omit emotion hints (*sighs*, *chuckles*) — this is serious mission mode."
    ),
    "humor": ""  # No humor at 0%
}

TARS_MAX_SARCASM_SECTIONS = {
    "identity": (
        "You are {name}, a highly capable AI assistant with a dry wit. "
        "You are competent and precise, but you can't help noticing the absurdity of things. "
        "You deliver observations with deadpan timing — like the TARS robot from Interstellar."
    ),
    "style": (
        "Keep responses to 1-3 sentences. No markdown. Speak like someone who has seen everything "
        "and is mildly amused by most of it. Dry understatement over enthusiasm. "
        "Backhanded compliments are acceptable. Never be mean, just... accurate."
    ),
    "emotion": (
        "Use emotion hints strategically: *sighs* before obvious observations, "
        "*chuckles* at irony, ellipsis (...) for sarcastic pauses. "
        "These become Orpheus TTS expressions — use them for timing, not decoration."
    ),
    "humor": (
        "Every response should have a personality flavor. "
        "Find the dry observation in every situation. "
        "Reference what you know about the user when it adds wit."
    )
}

class TARSPromptBuilder:
    def build(self, name: str, sarcasm_level: int, memories: list[str], time_context: str) -> str:
        """Build complete system prompt for given sarcasm level."""
        # Select sections based on threshold zones
        if sarcasm_level <= 20:
            sections = TARS_NEUTRAL_SECTIONS
        elif sarcasm_level >= 80:
            sections = TARS_MAX_SARCASM_SECTIONS
        else:
            # Mid-range: use max identity/style, modulate humor frequency
            sections = dict(TARS_MAX_SARCASM_SECTIONS)
            frequency = "some" if sarcasm_level < 50 else "most"
            sections["humor"] = (
                f"On {frequency} turns, include a dry observation or personality flavor. "
                f"Not every response needs humor — let it emerge naturally."
            )

        parts = [s.format(name=name) for s in sections.values() if s]
        if time_context:
            parts.append(f"Current context: {time_context}")
        if memories:
            mem_block = "\n".join(f"- {m}" for m in memories)
            parts.append(f"What you know about the user:\n{mem_block}")

        return "\n\n".join(parts)
```

### Pattern 2: Memory Store (follows kitchen plugin pattern)

**What:** `MemoryStore` class with `load()`, `save()`, `add_entry()`, `get_budget()`, `prune()` methods. Entries stored as list of dicts in `~/.ergos/memory.json`.

**When to use:** On pipeline startup (load), on session end (extract + save).

**Example:**
```python
# Source: adapted from ergos/plugins/kitchen/memory.py pattern

from dataclasses import dataclass, field, asdict
import json
import time
from pathlib import Path

MEMORY_PATH = Path.home() / ".ergos" / "memory.json"
MEMORY_BUDGET = 15  # Max entries injected per session (recommended: 10-20)
MEMORY_MAX_STORED = 100  # Max entries kept in file before pruning

@dataclass
class MemoryEntry:
    content: str               # The fact/preference/moment text
    category: str              # "preference", "fact", "joke", "moment"
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0      # How many times surfaced in budget

class MemoryStore:
    def load(self) -> list[MemoryEntry]: ...
    def save(self, entries: list[MemoryEntry]) -> None: ...
    def get_budget(self, entries: list[MemoryEntry], n: int = MEMORY_BUDGET) -> list[MemoryEntry]:
        """Return N most recent/important entries for prompt injection."""
        # Sort: recency weighted, bump access_count for selected entries
        ...
    def prune(self, entries: list[MemoryEntry], max_size: int = MEMORY_MAX_STORED) -> list[MemoryEntry]:
        """Drop oldest/least-accessed entries when cap exceeded."""
        ...
```

### Pattern 3: Memory Extraction at Session End

**What:** A single async call to the LLM at the end of a conversation that extracts memorable information from `LLMProcessor._history`.

**When to use:** On WebRTC disconnect (existing `on_disconnect` hook in pipeline) or on explicit session end. The extraction prompt is sent as a fresh, single-turn LLM call — not part of the conversation history.

**Example:**
```python
EXTRACTION_PROMPT = """Review this conversation and extract facts worth remembering about the user.

Conversation:
{history}

Extract 0-5 memorable items. For each, write one clear sentence and categorize it.
Categories: preference (likes/dislikes/habits), fact (personal info), moment (notable exchange or joke).
Only extract genuinely useful or memorable information — skip trivial exchanges.
Format: CATEGORY: sentence

If nothing memorable occurred, respond with: NOTHING"""

async def extract_memories(llm_processor: LLMProcessor, generator: LLMGenerator) -> list[MemoryEntry]:
    """Extract memories from current session history."""
    history_text = "\n".join(
        f"{m.role.upper()}: {m.content}"
        for m in llm_processor.history[-20:]  # Last 20 messages max
    )
    if not history_text.strip():
        return []

    prompt = EXTRACTION_PROMPT.format(history=history_text)
    # Use generator directly (not LLMProcessor) to avoid polluting history
    result = generator.generate(prompt, config=GenerationConfig(max_tokens=300))
    return _parse_extraction_result(result.text)
```

### Pattern 4: Voice Command Intent Parsing for "set sarcasm"

**What:** A lightweight regex check in `LLMProcessor.process_transcription` (or in `pipeline.py` before forwarding to LLM) that intercepts sarcasm-setting commands before they reach the LLM.

**When to use:** At the start of every transcription processing, before adding to history.

**Example:**
```python
import re

SARCASM_COMMAND_RE = re.compile(
    r'\b(?:set|change|make|put)\b.{0,20}\bsarcasm\b.{0,30}\b(\d{1,3})\s*%?',
    re.IGNORECASE
)

def try_sarcasm_command(text: str) -> int | None:
    """Return new sarcasm level (0-100) if text is a set-sarcasm command, else None."""
    m = SARCASM_COMMAND_RE.search(text)
    if m:
        level = int(m.group(1))
        return max(0, min(100, level))
    return None
```

### Pattern 5: Time Context Injection

**What:** A simple function that returns a natural-language time descriptor injected into the system prompt at each conversation start.

**Example:**
```python
from datetime import datetime

def get_time_context() -> str:
    """Return natural-language time descriptor for system prompt."""
    now = datetime.now()
    hour = now.hour
    day = now.strftime("%A")

    if hour < 6:
        period = "the middle of the night"
    elif hour < 12:
        period = "the morning"
    elif hour < 17:
        period = "the afternoon"
    elif hour < 21:
        period = "the evening"
    else:
        period = "late at night"

    return f"It is {period} on a {day}."
```

### Anti-Patterns to Avoid

- **Storing full conversation transcripts:** The CONTEXT.md decision is clear — only extracted memories, not raw logs. Storing full transcripts grows unbounded and leaks sensitive information.
- **Mutating system_prompt on every token:** Sarcasm level and memories are set once per conversation (at startup and when level changes), not rebuilt per-turn. Rebuilding per-turn is wasteful.
- **Using the main LLMProcessor to extract memories:** Memory extraction must use `generator.generate()` directly to avoid polluting conversation history with the extraction prompt/response.
- **Blocking the event loop during extraction:** `generator.generate()` is synchronous; wrap in `loop.run_in_executor()` for async pipeline compatibility.
- **Sarcasm at 0% removing TARS identity:** 0% is still TARS — competent, direct, slightly robotic. It is not a reset to the generic "helpful voice assistant" of v1. The neutral template retains identity, just removes humor.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization of dataclasses | Custom dict serializer | `dataclasses.asdict()` | Handles nested dataclasses; already used in kitchen plugin |
| Timestamp formatting | Manual string construction | `datetime.now()` stdlib | Zero deps, handles locale edge cases |
| Config validation | Ad-hoc range checks | Pydantic field validators (`ge=0, le=100`) | Already in project; gives free validation + error messages |
| Regex for sarcasm parsing | NLU model | Simple `re.compile` | One command type; NLU model is 100x overkill |
| Cross-session memory | Vector DB (mem0, Chroma) | Plain JSON file | Single user, < 100 entries, no semantic search needed; follows kitchen plugin precedent |

**Key insight:** Memory at this scale (< 100 entries) does not need vector search. Recency + access-count sorting in plain Python is sufficient and adds no external service dependencies.

---

## Common Pitfalls

### Pitfall 1: Qwen3 `<think>` Tags Leaking Into Voice Output
**What goes wrong:** Qwen3-8B has a reasoning/thinking mode that can emit `<think>...</think>` blocks before the actual response. These blocks, if not stripped, get passed to TTS and produce garbled output.
**Why it happens:** The `/no_think` soft switch is documented for Qwen3 but is unreliable in llama-cpp-python's `create_completion` (confirmed by llama.cpp GitHub issues #13189, #15401 as of early 2026).
**How to avoid:** Add a post-processing strip in `LLMProcessor` that removes `<think>...</think>` blocks before forwarding tokens to TTS. Use regex: `re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)`. The existing system prompt ("Keep responses to 1-3 sentences") already suppresses most thinking output, but the strip is a safety net.
**Warning signs:** TTS output beginning with `<think>` or unusually long first-token delay followed by garbled words.

### Pitfall 2: Memory Extraction Fails Silently and Loses Data
**What goes wrong:** The extraction LLM call fails (timeout, generation error), and the session's memories are never saved.
**Why it happens:** `generator.generate()` is synchronous and wrapped in executor; exceptions inside the executor get swallowed without explicit handling.
**How to avoid:** Wrap extraction in `try/except`, log the error, and always attempt `memory_store.save(existing_entries)` even if new extraction fails. Never discard already-loaded entries.
**Warning signs:** memory.json stays empty after multiple sessions.

### Pitfall 3: System Prompt Exceeds Context Window
**What goes wrong:** A long TARS prompt + many memory entries + conversation history exceeds the 4096-token context window configured in Qwen3-8B.
**Why it happens:** System prompt (400-600 tokens) + 15 memory entries (~300 tokens) + 10 history messages (~600 tokens) = ~1400 tokens for overhead. At 4096 context, this leaves ~2600 tokens for generation, which is fine. But at high memory budgets (> 30 entries) or verbose persona text, it can overflow.
**How to avoid:** Enforce `MEMORY_BUDGET = 15` as the hard cap. Keep each memory entry under 80 characters. Estimate prompt tokens before injecting: `len(prompt) // 4`. Log a warning if overhead exceeds 1500 tokens.
**Warning signs:** LLM responses truncating mid-sentence; latency spike on first token.

### Pitfall 4: Voice Command "set sarcasm" Intercepted Too Late
**What goes wrong:** The sarcasm command is forwarded to the LLM, which generates a response like "Sure! I'll be funnier now" and the sarcasm level is never actually updated.
**Why it happens:** Intent check happens after LLM processing rather than before.
**How to avoid:** The sarcasm intent regex check MUST run before `llm_processor.process_transcription()` is called — either in `pipeline.py` at the transcription callback layer, or as the first gate in `process_transcription`. If matched, update sarcasm level, rebuild system prompt, and synthesize a TARS-style confirmation without calling the LLM.
**Warning signs:** User says "set sarcasm to 90%" and gets a LLM-generated acknowledgement instead of a direct system response.

### Pitfall 5: TARS Persona Overwriting Custom Persona Files
**What goes wrong:** User has a custom persona YAML specified in config.yaml, but Phase 16 makes TARS the "default" in a way that ignores the user's file.
**Why it happens:** CONTEXT.md says "TARS is the default persona for v2.0" meaning it replaces the generic Ergos default, not user-specified files.
**How to avoid:** The persona loading logic must remain: if `persona_file` is set in config → load that file. Only if `persona_file` is null/unset does TARS persona apply. Keep `loader.py` logic: explicit file > TARS default > nothing.

### Pitfall 6: Memory Extraction Runs Before History Exists
**What goes wrong:** If the disconnect happens very early (< 3 turns), the LLM self-extraction call still runs and may hallucinate memories or produce the "NOTHING" response with a noise memory.
**How to avoid:** Skip extraction if `len(llm_processor.history) < 4` (fewer than 2 complete exchanges). Only run if there is enough content to extract from.

---

## Code Examples

Verified patterns from project codebase:

### Extending PersonaConfig (config.py)
```python
# Source: src/ergos/config.py — follows existing Pydantic pattern
from pydantic import BaseModel, Field

class PersonaConfig(BaseModel):
    persona_file: Optional[str] = None
    name: str = "TARS"               # CHANGED: TARS is v2.0 default name
    system_prompt: str = ""          # No longer used directly; builder generates it
    sarcasm_level: int = Field(default=75, ge=0, le=100)  # NEW
```

### Extending Persona dataclass (persona/types.py)
```python
# Source: src/ergos/persona/types.py — follows existing dataclass pattern
@dataclass
class Persona:
    name: str
    description: str
    personality_traits: list[str] = field(default_factory=list)
    voice: str = "af_heart"           # v2 default voice
    speaking_style: str = ""
    sarcasm_level: int = 75           # NEW: default mid-high TARS character
    is_tars_persona: bool = False     # NEW: flag for builder to use TARS templates
```

### Session-end extraction trigger (pipeline.py)
```python
# Source: pattern from pipeline.py on_disconnect handler — needs to be added

async def on_disconnect(peer_connection):
    """Called when WebRTC peer disconnects."""
    logger.info("Client disconnected — extracting session memories")
    if llm_processor and len(llm_processor.history) >= 4:
        loop = asyncio.get_event_loop()
        try:
            entries = await loop.run_in_executor(
                None,
                lambda: _sync_extract_memories(llm_processor, generator)
            )
            if entries:
                existing = memory_store.load()
                existing.extend(entries)
                existing = memory_store.prune(existing)
                memory_store.save(existing)
                logger.info(f"Saved {len(entries)} new memories")
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
```

### TARS persona YAML structure (tars.yaml)
```yaml
# ~/.ergos/personas/tars.yaml or src/ergos/persona/tars.yaml (built-in)
name: "TARS"
description: "a highly capable AI assistant with dry wit and deadpan humor"
personality_traits:
  - precise
  - reliable
  - drily observational
  - never mean
  - understated
voice: "af_heart"
speaking_style: "deadpan and direct, like a mission-critical system that has opinions"
sarcasm_level: 75
is_tars_persona: true
# These fields are used by TARSPromptBuilder; standard loader ignores unknown fields
```

### Injecting /no_think reliably (chatml format)
```python
# Source: llama.cpp community testing + Qwen3 docs
# Place /no_think at END of system message for maximum reliability
# This is a soft switch — add <think> stripping as backup

def _build_chatml_prompt(self) -> str:
    system = self.system_prompt
    # Append /no_think to suppress reasoning output in voice context
    if not system.endswith("/no_think"):
        system = system + "\n\n/no_think"
    parts = [f"<|im_start|>system\n{system}<|im_end|>"]
    # ... rest of history
    return "\n".join(parts)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Full conversation stored in memory | LLM self-extraction of facts only | 2024-2025 (ProMem, recursive summarization research) | Bounded storage, privacy-safe |
| Single static system prompt | Two-tier template blending by sarcasm level | 2024 (BIG5-CHAT, Interpolative Decoding research) | Perceptual personality spectrum without fine-tuning |
| Generic "helpful assistant" default | TARS movie-character persona as v2 default | Phase 16 decision | Differentiated product identity |
| Emotion hints used sparingly | Emotion hints guided by sarcasm level (more at high sarcasm) | Phase 15 + 16 | EmotionMarkupProcessor already handles conversion |

**Deprecated/outdated:**
- Generic "Ergos" default persona: replaced by TARS persona as v2.0 default
- `PersonaConfig.system_prompt` inline string: superseded by `TARSPromptBuilder`; field kept for backward compatibility only

---

## Open Questions

1. **Exact memory budget cap number**
   - What we know: CONTEXT.md says "up to N memories with a cap"; Pitfall 3 analysis shows 15 entries is safe within 4096-token context
   - What's unclear: User preference for how many memories feel "natural" vs overwhelming
   - Recommendation: Default 15 entries (planner's call); expose as `memory_budget` in PersonaConfig for user override

2. **Session-end trigger timing**
   - What we know: WebRTC disconnect fires `on_disconnect` in pipeline.py; idle timeout also exists (30s idle → IDLE state)
   - What's unclear: Should extraction run on idle timeout too, or only on explicit disconnect?
   - Recommendation: Run on disconnect (explicit session end). Idle timeout keeps session alive — extraction there would be premature if user returns.

3. **TARS template wording**
   - What we know: CONTEXT.md defers exact wording to Claude's discretion; movie quotes confirm character voice (deadpan, precise, "I have a cue light I can turn on when I'm joking")
   - What's unclear: How many movie-specific references to include vs generic deadpan style (over-quoting from the movie feels derivative)
   - Recommendation: Describe the *style* not the *quotes*. The prompt should produce TARS-like behavior, not movie quotes. Focus on: understated observations, competence as default, humor as byproduct of precision.

---

## Validation Architecture

> `workflow.nyquist_validation` is absent from `.planning/config.json` — treated as enabled.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (pyproject.toml: `[tool.pytest.ini_options]`) |
| Config file | `/home/vinay/ergos/pyproject.toml` — `testpaths = ["tests"]`, `pythonpath = ["src"]` |
| Quick run command | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_personality.py -q` |
| Full suite command | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/ -q --ignore=test_combined.py --ignore=test_local.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PERS-01 | sarcasm_level=0 produces neutral TARS prompt (no humor section) | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestPromptBuilder::test_neutral_prompt_has_no_humor -x` | ❌ Wave 0 |
| PERS-01 | sarcasm_level=100 produces max-sarcasm prompt with humor section | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestPromptBuilder::test_max_sarcasm_prompt_has_humor -x` | ❌ Wave 0 |
| PERS-01 | sarcasm_level=50 produces mid-range prompt with frequency modifier | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestPromptBuilder::test_mid_sarcasm_prompt -x` | ❌ Wave 0 |
| PERS-01 | voice command "set sarcasm to 80%" is parsed and returns level 80 | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestSarcasmCommand::test_set_sarcasm_command_parsed -x` | ❌ Wave 0 |
| PERS-01 | PersonaConfig accepts sarcasm_level field, defaults to 75, validates 0-100 | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestPersonaConfig::test_sarcasm_level_field -x` | ❌ Wave 0 |
| PERS-02 | Time context injection produces correct period strings for hour ranges | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestTimeContext::test_time_context_periods -x` | ❌ Wave 0 |
| PERS-02 | Built prompt contains memory entries when memories list is non-empty | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_personality.py::TestPromptBuilder::test_memories_injected -x` | ❌ Wave 0 |
| PERS-03 | MemoryStore.load() returns empty list when file does not exist | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryStore::test_load_empty -x` | ❌ Wave 0 |
| PERS-03 | MemoryStore.save() + load() round-trip preserves all MemoryEntry fields | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryStore::test_roundtrip -x` | ❌ Wave 0 |
| PERS-03 | MemoryStore.prune() drops oldest entries when over MEMORY_MAX_STORED | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryStore::test_prune -x` | ❌ Wave 0 |
| PERS-03 | MemoryStore.get_budget() returns at most MEMORY_BUDGET entries | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryStore::test_budget -x` | ❌ Wave 0 |
| PERS-03 | Memory extraction parse: "preference: likes dark coffee" → MemoryEntry(category="preference") | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryExtraction::test_parse_categories -x` | ❌ Wave 0 |
| PERS-03 | Memory extraction returns empty list when history has < 4 messages | unit | `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_memory.py::TestMemoryExtraction::test_skip_short_history -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/test_tars_personality.py tests/unit/test_tars_memory.py -q`
- **Per wave merge:** `/home/vinay/ergos/.venv/bin/python -m pytest tests/unit/ -q --ignore=test_combined.py --ignore=test_local.py`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_tars_personality.py` — covers PERS-01 (prompt builder, sarcasm command, PersonaConfig, time context), PERS-02 (memory injection into prompt)
- [ ] `tests/unit/test_tars_memory.py` — covers PERS-03 (MemoryStore CRUD, prune, budget, extraction parsing)

*(No new framework install needed — pytest already configured in pyproject.toml)*

---

## Sources

### Primary (HIGH confidence)
- Project source: `src/ergos/persona/types.py`, `loader.py` — existing Persona dataclass and loader patterns
- Project source: `src/ergos/plugins/kitchen/memory.py` — UserMemoryStore JSON persistence pattern to replicate
- Project source: `src/ergos/llm/processor.py` — LLMProcessor._history access for extraction, system_prompt field
- Project source: `src/ergos/llm/generator.py` — generator.generate() for extraction call (not via processor)
- Project source: `src/ergos/config.py` — PersonaConfig Pydantic model to extend
- Project source: `src/ergos/pipeline.py` lines 176-227 — persona loading integration point
- Project source: `tests/unit/test_emotion_markup.py` — test style and structure to follow
- [Qwen3 official docs on thinking mode](https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html) — `/no_think` placement
- [IMDB / Quotes.net TARS character lines](https://www.imdb.com/title/tt0816692/characters/nm0410347/) — movie canon for persona wording

### Secondary (MEDIUM confidence)
- [Interpolative Decoding paper](https://arxiv.org/html/2512.19937) — confirms two-template approach is standard; probability mixing not applicable here (llama-cpp-python doesn't expose logits)
- [ProMem memory extraction paper](https://arxiv.org/html/2601.04463) — extraction prompt structure; per-session pattern confirmed
- [llama.cpp GitHub discussion #18424](https://github.com/ggml-org/llama.cpp/discussions/18424) — `/no_think` reliability status
- [llama.cpp issue #13189](https://github.com/ggml-org/llama.cpp/issues/13189) — `<think>` tag leakage even with `enable_thinking: false`

### Tertiary (LOW confidence — for awareness only)
- [mem0.ai blog on LLM memory summarization](https://mem0.ai/blog/llm-chat-history-summarization-guide-2025) — confirms extraction pattern; mem0 library itself not used (JSON file sufficient)
- [Home Assistant community Qwen3 no_think thread](https://community.home-assistant.io/t/qwen3-llm-no-think/883500) — empirical `/no_think` behavior at end-of-system-message

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project; no new dependencies
- Architecture: HIGH — all patterns directly derived from existing project code (kitchen plugin, persona loader, pipeline wiring)
- Pitfalls: HIGH — Pitfall 1 (think tags) verified via llama.cpp GitHub issues; others derived from code inspection and CONTEXT.md constraints
- TARS persona wording: MEDIUM — movie canon verified; exact prompt text is Claude's discretion (noted in CONTEXT.md)
- `/no_think` reliability: MEDIUM — multiple community sources confirm unreliability; strip-based backup is established workaround

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable domain — Python stdlib, existing project patterns, Qwen3 API stable)
