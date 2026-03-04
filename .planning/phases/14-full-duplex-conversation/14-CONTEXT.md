# Phase 14: Full-Duplex Conversation - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Enable natural turn-taking in voice conversation: user can interrupt the AI mid-sentence, AI responds within 300ms of user finishing speech, and the system supports a SPEAKING_AND_LISTENING state for simultaneous output and input. Expressive voice and personality are separate phases (15, 16).

</domain>

<decisions>
## Implementation Decisions

### Barge-in sensitivity
- Instant trigger on any detected speech — no minimum duration threshold
- Audio stops abruptly (cut mid-word), no fade-out
- Cancel everything on barge-in: both LLM generation and TTS synthesis stop immediately
- Keep existing Flutter barge-in gesture (CLIENT-UI-03) alongside new voice-based detection

### Overlap behavior
- Brief overlap (~500ms): AI keeps talking for a short moment while starting to listen, then stops
- All speech treated as interruption — no backchannel detection (e.g., "mm-hmm" triggers interruption same as any speech)
- Echo cancellation handled client-side (Flutter) — rely on device's built-in AEC
- SPEAKING_AND_LISTENING is a visible state in Flutter client — orb shows unique animation (pulse + glow or similar)

### Post-interruption flow
- AI remembers what it was saying — partial response stays in conversation history
- Silent transition — no verbal acknowledgment ("okay", "go ahead") after interruption
- Fully switch topics — user's new input takes priority, previous topic dropped
- Partial response kept in LLM context so AI knows what the user already heard

### Silence & turn-taking
- Short VAD end-of-speech threshold (~500ms) for fast response
- Immediate start — begin speaking as soon as first TTS audio is ready, no artificial pause
- Timeout to idle after 30s of silence post-response
- Latency measured and logged using existing LatencyTracker infrastructure (P50/P95)

### Claude's Discretion
- Exact SPEAKING_AND_LISTENING state transition timing and edge cases
- STT/LLM/TTS pipeline optimizations to achieve sub-300ms target
- Audio buffer management during overlap period
- State machine transition validation rules for the new state
- Idle timeout implementation details

</decisions>

<specifics>
## Specific Ideas

- Target feel: like talking to a person who stops mid-sentence when you interrupt — instant, no awkwardness
- The 200ms barge-in requirement means from user speech detection to AI audio stop, not from user intent
- Sub-300ms P50 is measured from VAD speech_end to first TTS audio chunk (existing latency tracker definition)
- TARS personality is a later phase — this phase is purely about conversational mechanics

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ConversationStateMachine` (state/machine.py): Has barge_in() method, barge-in callbacks, transition validation. Needs SPEAKING_AND_LISTENING state added to enum and transition table
- `LatencyTracker` (metrics.py): Already tracks speech_end → first_audio. P50/P95 computation built in
- `TTSProcessor` (tts/processor.py): Has cancel(), clear_buffer(), reset_cancellation() — ready for barge-in
- `LLMGenerator`: Has cancel() method referenced in commented-out barge-in code
- Barge-in wiring code exists commented out in pipeline.py:451-461 — needs uncommenting and updating

### Established Patterns
- Callback-based wiring: pipeline.py wires components via async callbacks (on_vad_for_state, on_tts_audio, etc.)
- State-gated audio: on_incoming_audio() and on_vad_for_state() check current state before processing
- Synthesis lock: TTS uses asyncio.Lock to serialize synthesis calls
- Data channel: State changes broadcast to Flutter client via data_handler

### Integration Points
- `ConversationState` enum (state/events.py): Add SPEAKING_AND_LISTENING value
- `VALID_TRANSITIONS` table (state/machine.py): Add transitions to/from new state
- `on_vad_for_state` callback (pipeline.py:280-296): Currently ignores VAD during SPEAKING — needs to handle SPEAKING_AND_LISTENING
- `on_incoming_audio` callback (pipeline.py:609-648): Currently returns early during SPEAKING — needs to process audio in SPEAKING_AND_LISTENING
- `on_barge_in` callback (pipeline.py:451-461): Commented out — uncomment and wire with full cancel behavior
- Flutter client orb animation: Needs new visual state for SPEAKING_AND_LISTENING
- Data channel protocol: Needs to broadcast SPEAKING_AND_LISTENING state to client

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 14-full-duplex-conversation*
*Context gathered: 2026-03-03*
