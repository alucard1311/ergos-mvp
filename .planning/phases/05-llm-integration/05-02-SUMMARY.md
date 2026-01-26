---
phase: 05-llm-integration
plan: 02
subsystem: llm
tags: [llm-processor, conversation-history, phi3-chat-format, streaming-callbacks]

# Dependency graph
requires:
  - phase: 05-01
    provides: LLMGenerator and CompletionResult types
  - phase: 03-stt-pipeline
    provides: TranscriptionResult input type
provides:
  - LLMProcessor for conversation management
  - Message dataclass for history entries
  - Phi-3 chat format prompt building
  - Token and completion callback registration
affects: [webrtc-transport, tts-pipeline, pipeline-coordinator]

# Tech tracking
tech-stack:
  added: []
  patterns: [conversation-history, chat-prompt-format, bounded-history, callback-registry]

key-files:
  created:
    - src/ergos/llm/processor.py
  modified:
    - src/ergos/llm/__init__.py

key-decisions:
  - "Phi-3 chat format: <|system|>, <|user|>, <|assistant|> with <|end|> delimiters"
  - "max_history_messages=10 default to bound memory usage"
  - "History trimmed when exceeds 2x max to prevent unbounded growth"
  - "Token estimation at ~4 chars per token for context monitoring"

patterns-established:
  - "Async callback pattern for streaming tokens to TTS"
  - "History bounded by message count for predictable memory"
  - "Processor wraps generator adding conversation context"

# Metrics
duration: 4min
completed: 2026-01-26
---

# Phase 5 Plan 2: LLM Processor Summary

**LLMProcessor integrating with STT output, managing conversation history, and streaming tokens**

## Performance

- **Duration:** 4 min
- **Started:** 2026-01-26T20:30:00Z
- **Completed:** 2026-01-26T20:34:00Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- Created Message dataclass with role, content, and timestamp fields
- Created LLMProcessor dataclass wrapping LLMGenerator
- Implemented process_transcription() accepting TranscriptionResult
- Built Phi-3 chat format prompt builder with system/user/assistant tags
- Added bounded conversation history with configurable max_history_messages
- Implemented token callback registration for streaming to TTS
- Implemented completion callback for full response notification
- Added stats property, history property, and estimate_context_tokens()
- Updated ergos.llm package exports to include LLMProcessor and Message

## Task Commits

1. **Tasks 1-3: Create LLM processor** - `e2cca17` (feat)

## Files Created/Modified

- `src/ergos/llm/processor.py` - LLMProcessor class with conversation history and streaming
- `src/ergos/llm/__init__.py` - Added LLMProcessor and Message to exports

## Verification Results

All verification commands passed:
```
python -c "from ergos.llm.processor import LLMProcessor; print('LLMProcessor importable')"
# Output: LLMProcessor importable

python -c "from ergos.llm import LLMProcessor, LLMGenerator, CompletionResult, Message; print('All LLM exports work')"
# Output: All LLM exports work

python -c "from ergos.llm import LLMProcessor; print('stats' in dir(LLMProcessor))"
# Output: True
```

## Decisions Made

- Used dataclass for Message (consistent with other types)
- Default system prompt: "You are a helpful voice assistant. Keep responses concise and conversational."
- max_history_messages=10 (keeps ~20 messages before trimming)
- Estimated 4 chars per token for context monitoring
- Callbacks wrapped in try/except to prevent callback errors from breaking generation

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all verifications passed.

## API Surface

```python
# Message for conversation history
@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str
    timestamp: float

# Processor wrapping generator with context
@dataclass
class LLMProcessor:
    generator: LLMGenerator
    system_prompt: str = "..."
    max_history_messages: int = 10
    max_context_tokens: int = 1500

    # Core methods
    async def process_transcription(result: TranscriptionResult) -> CompletionResult
    def clear_history() -> None

    # Callbacks
    def add_token_callback(callback: TokenCallback) -> None
    def add_completion_callback(callback) -> None

    # Properties
    @property stats: dict
    @property history: list[Message]
    def estimate_context_tokens() -> int
```

## Next Phase Readiness

- LLMProcessor ready for pipeline integration
- Token streaming ready for TTS connection
- Conversation history enables multi-turn dialogue
- Stats and monitoring available for debugging

---
*Phase: 05-llm-integration*
*Completed: 2026-01-26*
