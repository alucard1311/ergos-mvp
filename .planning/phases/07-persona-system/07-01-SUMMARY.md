---
phase: 07-persona-system
plan: 01
subsystem: persona
tags: [persona, yaml-config, system-prompt, dataclass]

# Dependency graph
requires:
  - phase: 05-llm-integration
    provides: LLMProcessor with system_prompt parameter
provides:
  - Persona dataclass with system_prompt property
  - YAML persona file loading with load_persona()
  - DEFAULT_PERSONA constant for fallback
  - PersonaConfig.persona_file path option
affects: [llm-integration, pipeline-coordinator, webrtc-transport]

# Tech tracking
tech-stack:
  added: []
  patterns: [yaml-config-loading, dataclass-with-property, fallback-defaults]

key-files:
  created:
    - src/ergos/persona/__init__.py
    - src/ergos/persona/types.py
    - src/ergos/persona/loader.py
  modified:
    - src/ergos/config.py

key-decisions:
  - "Persona uses dataclass pattern consistent with other types"
  - "system_prompt property generates prompt dynamically from attributes"
  - "load_persona returns DEFAULT_PERSONA on file not found or parse error"
  - "PersonaConfig supports both file-based and inline persona definition"

patterns-established:
  - "Dataclass with computed property for derived values"
  - "YAML loader with graceful fallback to defaults"

# Metrics
duration: 1min
completed: 2026-01-26
---

# Phase 7 Plan 1: Persona Types and Loader Summary

**Persona dataclass with YAML loading and system prompt generation for LLM personality configuration**

## Performance

- **Duration:** 1 min
- **Started:** 2026-01-26T20:47:33Z
- **Completed:** 2026-01-26T20:48:51Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Created Persona dataclass with name, description, personality_traits, voice, speaking_style
- Implemented system_prompt property that builds LLM prompt from persona attributes
- Created load_persona() function for YAML file loading with fallback to DEFAULT_PERSONA
- Added DEFAULT_PERSONA constant with sensible defaults
- Updated PersonaConfig to support persona_file path option for file-based personas
- Exported Persona, load_persona, DEFAULT_PERSONA from ergos.persona package

## Task Commits

1. **Task 1: Create persona types and loader** - `c5bf6a1` (feat)
2. **Task 2: Update config to use persona path** - `9e40d97` (feat)

## Files Created/Modified

- `src/ergos/persona/__init__.py` - Package exports for Persona, load_persona, DEFAULT_PERSONA
- `src/ergos/persona/types.py` - Persona dataclass with system_prompt property
- `src/ergos/persona/loader.py` - YAML loading with DEFAULT_PERSONA fallback
- `src/ergos/config.py` - Added persona_file path option to PersonaConfig

## Verification Results

All verification commands passed:
```
python -c "from ergos.persona import Persona, load_persona"
# Output: Success (no error)

python -c "from ergos.persona import Persona; p = Persona(name='Test', description='a test'); print(p.system_prompt)"
# Output: You are Test, a test. Keep responses concise for voice interaction.

python -c "from ergos.persona import load_persona, DEFAULT_PERSONA; p = load_persona('/nonexistent/path.yaml'); print(p.name == DEFAULT_PERSONA.name)"
# Output: True

python -c "from ergos.config import PersonaConfig; print('persona_file' in PersonaConfig.model_fields)"
# Output: True
```

## Decisions Made

- Used dataclass for Persona (consistent with Message, TranscriptionResult, etc.)
- DEFAULT_PERSONA has personality_traits=["helpful", "concise", "friendly"] and speaking_style="warm and conversational"
- system_prompt always ends with "Keep responses concise for voice interaction." for voice-optimized responses
- load_persona uses Path.expanduser() to support ~ in file paths
- PersonaConfig keeps name/system_prompt as inline fallbacks when persona_file is not specified

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all verifications passed.

## API Surface

```python
# Persona dataclass
@dataclass
class Persona:
    name: str
    description: str
    personality_traits: list[str] = []
    voice: str = "af_sarah"
    speaking_style: str = ""

    @property
    def system_prompt(self) -> str: ...

# Loader
DEFAULT_PERSONA: Persona
def load_persona(path: Path | str) -> Persona: ...

# Config
class PersonaConfig(BaseModel):
    persona_file: Optional[str] = None
    name: str = "Ergos"
    system_prompt: str = "You are a helpful voice assistant."
```

## YAML Persona Format

```yaml
name: "Aria"
description: "a knowledgeable and friendly assistant"
personality_traits:
  - helpful
  - patient
  - concise
voice: "af_sarah"
speaking_style: "warm and conversational"
```

## Next Phase Readiness

- Persona system ready for LLMProcessor integration
- load_persona can be called during server startup
- persona.system_prompt can replace LLMProcessor's default system_prompt
- persona.voice can configure TTSSynthesizer voice selection

---
*Phase: 07-persona-system*
*Completed: 2026-01-26*
