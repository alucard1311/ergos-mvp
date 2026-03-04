# Phase 16: TARS Personality - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

AI has consistent TARS-like dry wit, context-aware humor, and persistent memory across sessions. Delivers configurable sarcasm level (0-100%), context-aware jokes referencing conversation topics and time of day, cross-session memory of user preferences and key moments, and a TARS persona that loads from configuration and overrides default system prompt behavior. Vision-based context (screen awareness) is Phase 18 — not in scope here.

</domain>

<decisions>
## Implementation Decisions

### Sarcasm Calibration
- System prompt blending approach: two prompt templates (neutral TARS + maximum sarcasm TARS) that interpolate based on sarcasm level
- 0% sarcasm = still TARS personality (competent, direct, slightly robotic cadence) but no humor — serious mission mode
- 100% sarcasm = movie-accurate TARS: deadpan observations, understated humor, occasional backhanded compliments, never mean
- Runtime adjustable: config.yaml sets default sarcasm_level, also changeable via voice command ("set sarcasm to 80%") or API call during a session without restart
- Sarcasm slider controls both intensity AND frequency of humor — at high sarcasm, every response has personality flavor

### Persistent Memory
- LLM self-extraction: at end of each conversation, ask the LLM to identify memorable moments and new facts about the user from chat history
- What gets remembered: user preferences (likes, dislikes, habits), factual info about user, and key conversation moments (jokes that landed, running gags, notable exchanges)
- No full conversation logs stored — only extracted memories
- Storage: JSON file at ~/.ergos/memory.json (consistent with existing kitchen plugin pattern)
- Fixed budget injection: load up to N memories (most recent + important) into system prompt each conversation, with a cap to keep context usage predictable
- Pruning: oldest/least-used memories dropped when cap exceeded

### TARS Persona Definition
- Dedicated TARS template: a specific curated persona file with pre-written system prompt text, example exchanges, and sarcasm tier definitions — polished out of the box
- TARS is the default persona for v2.0 — replaces current generic "helpful voice assistant" when no persona_file is specified
- User-configurable name: defaults to "TARS" but user can rename (e.g., "Jarvis", "Friday") while keeping personality style
- Persona guides emotion markup: TARS system prompt instructs LLM WHEN to use emotion hints based on sarcasm level — low sarcasm = fewer *sighs* and pauses, high sarcasm = more strategic emotion hints. EmotionMarkupProcessor (Phase 15) handles the conversion unchanged

### Context-Aware Humor
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

</decisions>

<specifics>
## Specific Ideas

- TARS at 100% should feel like the movie character: "I have a cue light I can turn on when I'm joking, if you want." Dry, not mean.
- 0% sarcasm is TARS in serious mission mode — still competent and direct, just without the humor
- Memory should enable "remember when" callbacks but not feel forced — organic callbacks only
- v2.0 IS the TARS milestone — TARS as default persona is the correct default

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Persona` dataclass (persona/types.py): Has name, description, personality_traits, voice, speaking_style, and system_prompt property. Needs extension for sarcasm_level and richer prompt generation
- `load_persona()` (persona/loader.py): Loads from YAML, falls back to DEFAULT_PERSONA. Can be extended to load TARS template
- `PersonaConfig` (config.py): Pydantic model with name, persona_file, system_prompt fields. Needs sarcasm_level field
- `UserMemoryStore` (plugins/kitchen/memory.py): JSON-based persistence pattern at ~/.ergos/ — reusable pattern for general memory store
- `EmotionMarkupProcessor` (tts/emotion_markup.py): Already handles emotion hint → Orpheus tag conversion. TARS persona just controls when hints appear in LLM output

### Established Patterns
- Persona → system_prompt: Persona.system_prompt property generates prompt from attributes. TARS needs a richer version with sarcasm-level-dependent prompt blending
- Config cascade: config.yaml → PersonaConfig → pipeline.py reads persona and builds LLM system prompt. Same flow, just richer persona
- Plugin memory: kitchen plugin uses JSON file at ~/.ergos/plugins/kitchen/memory.json with dataclass → dict serialization. General memory can follow same pattern at ~/.ergos/memory.json
- LLM conversation history: LLMProcessor._history stores in-memory Message list with role, content, timestamp. Memory extraction reads this at session end

### Integration Points
- `pipeline.py:176-227`: Persona loading and system prompt construction — this is where TARS persona overrides current behavior
- `LLMProcessor.system_prompt`: Currently a static string set at init — needs to accept dynamic sarcasm-level-adjusted prompts
- `LLMProcessor._history`: Source for memory extraction at session end
- `config.yaml persona section`: Add sarcasm_level field
- `PersonaConfig`: Add sarcasm_level: int = 75 (default)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 16-tars-personality*
*Context gathered: 2026-03-04*
