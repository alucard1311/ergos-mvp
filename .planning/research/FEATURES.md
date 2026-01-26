# Voice Assistant Feature Research

**Research Date:** 2026-01-26
**Domain:** Local-first voice assistant / Real-time AI audio pipeline
**Project Context:** Ergos - privacy-focused, local-only voice assistant

---

## Table Stakes (Users Expect These)

These are features users have come to expect from voice assistants. Missing any of these will make the product feel incomplete.

| Feature | Description | Complexity | Notes |
|---------|-------------|------------|-------|
| **Wake Word Detection** | Activate assistant with a spoken phrase ("Hey Ergos") | MEDIUM | Requires low false-positive rate (<0.5/hour) and false-reject rate (<5%). Models typically <100KB for on-device. |
| **Speech-to-Text (STT)** | Convert spoken commands to text | HIGH | Whisper base model minimum. 8 seconds on RPi4, <1 second on Intel NUC. Critical for responsiveness. |
| **Text-to-Speech (TTS)** | Speak responses back to user | MEDIUM | Piper TTS optimized for RPi4. Quality levels from 16kHz to 22.05kHz. |
| **Basic Commands** | Weather, time, timers, alarms, reminders | LOW | 57% of users use voice commands daily, primarily for simple tasks. |
| **Smart Home Control** | Control lights, switches, basic devices | MEDIUM | Users expect Matter/Thread/Zigbee support. Local control without cloud critical for privacy story. |
| **Music/Media Control** | Play, pause, skip, volume control | LOW | Integration with local media servers (e.g., Plex, Jellyfin) for privacy-focused users. |
| **Response Latency <1.5s** | Total time from speech end to response start | HIGH | >1.5s feels unnatural; <500ms is ideal for conversational flow. 300ms threshold for natural conversation. |
| **Noise Handling** | Work in moderately noisy environments | MEDIUM | Dual microphones with echo cancellation, noise reduction, auto gain control. |
| **Visual Feedback** | LED/display showing listening state | LOW | Critical for user trust - knowing when device is active. |

### Complexity Legend
- **LOW**: Well-understood problem, existing libraries, <1 week implementation
- **MEDIUM**: Requires integration work, some optimization, 1-4 weeks
- **HIGH**: Core technical challenge, significant R&D, 1+ month

---

## Differentiators (Competitive Advantage for Privacy-Focused Local Assistant)

| Feature | Why It Matters | Implementation Notes | Priority |
|---------|----------------|---------------------|----------|
| **100% Local Processing** | Zero data leaves device. Cloud assistants send all audio to servers. 41% of users fear active listening. | All STT/TTS/LLM must run on-device. No fallback to cloud. | CRITICAL |
| **No Wake Word Cloud Upload** | Unlike Alexa/Google, wake word detection AND command processing stay local | openWakeWord or Porcupine for local detection | CRITICAL |
| **Transparent Data Handling** | Show exactly what's recorded, processed, stored | Local logs visible to user, no hidden telemetry | HIGH |
| **Offline Functionality** | Works without internet connection | Core commands, timers, smart home control must work offline | HIGH |
| **Open Source / Auditable** | Users can verify privacy claims | MIT/Apache license, clear architecture documentation | HIGH |
| **Custom Wake Words** | User chooses their own activation phrase | Training pipeline or flexible model like openWakeWord | MEDIUM |
| **Local LLM Integration** | Conversational AI without cloud | Ollama, llama.cpp, TinyLlama 1.1B minimum | MEDIUM |
| **HiveMind Architecture** | Distribute processing - satellites with low resources, central server with GPU | Reduces hardware requirements for individual rooms | LOW |
| **Voice Cloning** | Custom TTS voice (user's own voice or chosen persona) | Piper fine-tuning capability | LOW |
| **Multi-Language Without Cloud** | Support multiple languages locally | Whisper multilingual, Piper multilingual voices | MEDIUM |

---

## Anti-Features (Commonly Requested But Problematic)

These features seem desirable but create significant problems. Avoid or implement with extreme caution.

| Anti-Feature | Why It's Problematic | Alternative Approach |
|--------------|---------------------|---------------------|
| **Always-On Continuous Listening** | Users want "seamless" conversation but this requires constant audio processing, raising privacy concerns and battery/CPU usage. Even local always-listening violates trust model. | Use explicit wake word + configurable listen window. Implement "follow-up mode" with short timeout. |
| **Cloud Fallback for Better Accuracy** | Tempting to offer "enhanced mode" with cloud STT/LLM but destroys core privacy value proposition. Users may enable without understanding implications. | No cloud fallback. Improve local models instead. Be transparent about accuracy tradeoffs. |
| **100,000+ Skills Ecosystem** | Amazon's approach - massive skill library. Creates maintenance burden, security risks, quality control issues. Limited skills killed new Alexa launch. | Focus on high-quality core skills + simple, auditable skill API for power users. |
| **Proactive Suggestions** | "You usually order coffee at 8am" - requires behavior tracking and feels invasive to privacy-conscious users. | Explicit user-configured routines only. No implicit learning. |
| **Voice Purchasing** | Security nightmare. 22% of voice shoppers complete purchases directly - but this opens fraud vectors and accidental purchases. | Not appropriate for privacy-focused product. |
| **Over-Verbose Responses** | LLMs naturally produce long responses. "Who wants to listen to 30 seconds of voice assistant talking?" | Enforce concise response templates. Voice UI should be terse. |
| **Complex Multi-Step Wizards** | Voice is poor for complex configuration flows. Users don't remember menu structures. | Use companion app/web UI for configuration. Voice for execution. |
| **Accent/Voice Imitation** | Fun but creates deepfake concerns and potential misuse | Limit to predefined, clearly-synthetic voices |
| **Cross-Device Sync via Cloud** | Convenient but requires cloud infrastructure and data collection | Local network sync only (mDNS, local API) |
| **Conversation History Cloud Backup** | Users request it but defeats privacy purpose | Local-only encrypted storage with user-controlled export |

---

## Feature Dependencies

```
                    ┌─────────────────────────────────────────┐
                    │           AUDIO CAPTURE                 │
                    │    (Microphone, VAD, Noise Reduction)   │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │         WAKE WORD DETECTION             │
                    │   (openWakeWord / microWakeWord)        │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │          SPEECH-TO-TEXT                 │
                    │    (Whisper / faster-whisper)           │
                    └──────────────────┬──────────────────────┘
                                       │
              ┌────────────────────────┴────────────────────────┐
              │                                                 │
    ┌─────────▼─────────┐                         ┌─────────────▼──────────────┐
    │  INTENT PARSING   │                         │    LLM CONVERSATION        │
    │  (Rule-based/NLU) │                         │  (Ollama/llama.cpp)        │
    │  For: Commands    │                         │  For: Open-ended queries   │
    └─────────┬─────────┘                         └─────────────┬──────────────┘
              │                                                 │
              └────────────────────────┬────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │         SKILL EXECUTION                 │
                    │   (Timer, Smart Home, Media, etc.)      │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │         RESPONSE GENERATION             │
                    │      (Template or LLM-generated)        │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │           TEXT-TO-SPEECH                │
                    │              (Piper)                    │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │           AUDIO OUTPUT                  │
                    │     (Speaker / Audio Sink)              │
                    └─────────────────────────────────────────┘

    ═══════════════════════════════════════════════════════════

    SUPPORTING SYSTEMS (Run in Parallel)

    ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
    │   SMART HOME      │  │   CONFIGURATION   │  │   SKILL PLUGINS   │
    │   INTEGRATION     │  │   WEB UI          │  │   (Extensibility) │
    │ (Matter/Zigbee/   │  │                   │  │                   │
    │  Home Assistant)  │  │                   │  │                   │
    └───────────────────┘  └───────────────────┘  └───────────────────┘
```

### Critical Path Dependencies
1. **Audio Capture** must work before anything else
2. **Wake Word** depends on Audio Capture
3. **STT** depends on Wake Word (to know when to start)
4. **Intent/LLM** depends on STT output
5. **TTS** depends on Response Generation
6. **Audio Output** depends on TTS

### Parallel Development Possible
- Smart Home Integration (independent of core pipeline)
- Web UI Configuration (independent)
- Individual Skills (after Skill Execution framework exists)

---

## MVP Definition

### v1.0 - Minimum Viable Voice Assistant

**Goal:** Prove local-first voice assistant works. Target: Privacy-conscious tinkerers willing to configure.

| Component | Implementation | Why This Choice |
|-----------|---------------|-----------------|
| Wake Word | openWakeWord with "Hey Jarvis" default | Open source, customizable, low false-positive |
| STT | faster-whisper (base model) | 4x faster than original Whisper, runs on CPU |
| Intent Parsing | Rule-based with YAML grammar | Simple, fast, predictable for v1 commands |
| TTS | Piper (medium quality English) | Fast, local, sounds good on RPi4 |
| Skills | Timer, Alarm, Time, Weather (local cache), Simple math | Most common use cases (57% daily usage) |
| Smart Home | Home Assistant integration via local API | Existing ecosystem, avoids reinventing |
| UI | Terminal + simple LED feedback | Minimum viable, functional |
| Hardware Target | Raspberry Pi 4 (4GB) minimum | Common hobbyist hardware |

**v1.0 Response Time Target:** <3 seconds end-to-end (acceptable for early adopters)

**NOT in v1.0:**
- LLM conversation
- Multi-language
- Custom wake words (training)
- Mobile app
- Multi-room/satellite

---

### v1.x - Enhanced Local Assistant

**Goal:** Competitive with cloud assistants for common tasks. Target: Power users, home automation enthusiasts.

| Component | Enhancement | Rationale |
|-----------|-------------|-----------|
| STT | faster-whisper (small/medium model) | Better accuracy, still fast on NUC-class hardware |
| LLM | Ollama with TinyLlama/Phi-3.5 | Conversational responses, open-ended questions |
| Skills | Media control (Plex/Jellyfin), Shopping lists, Notes | Second-tier common use cases |
| Smart Home | Direct Matter/Thread support | Beyond Home Assistant dependency |
| Context | Multi-turn conversation (3-5 turns) | "Turn on the light" -> "Which one?" -> "Kitchen" |
| UI | Web configuration dashboard | Non-terminal users |
| Hardware | Intel NUC / Mini PC support | Faster processing, better LLM |

**v1.x Response Time Target:** <1.5 seconds end-to-end

**v1.1:** LLM integration + web UI
**v1.2:** Multi-turn context + expanded skills
**v1.3:** Matter/Thread direct integration

---

### v2+ - Full-Featured Privacy Assistant

**Goal:** Feature parity with cloud assistants where sensible. Target: Mainstream privacy-conscious users.

| Component | Enhancement | Rationale |
|-----------|-------------|-----------|
| Wake Word | Custom wake word training | Personal branding, accessibility |
| STT | Whisper large + faster-whisper turbo | Best accuracy locally achievable |
| LLM | Larger models (Llama 3 8B, Mistral 7B) | Complex reasoning, better conversation |
| Multi-room | HiveMind satellite architecture | Kitchen, bedroom, living room |
| Mobile | Companion app (Android/iOS) | Configuration, remote access on LAN |
| Voice | Custom voice cloning via Piper | Personalization |
| Accessibility | Screen reader integration, mobility support | 32% of disabled users rely on voice tech |
| Languages | 10+ language support | International users |

**v2+ Response Time Target:** <500ms (conversational-grade)

---

## Feature Prioritization Matrix

Using RICE scoring (Reach x Impact x Confidence / Effort)

| Feature | Reach | Impact | Confidence | Effort | Score | Priority |
|---------|-------|--------|------------|--------|-------|----------|
| Wake Word Detection | 10 | 10 | HIGH | 2 | 50 | P0 |
| Speech-to-Text (Whisper) | 10 | 10 | HIGH | 3 | 33 | P0 |
| Text-to-Speech (Piper) | 10 | 8 | HIGH | 2 | 40 | P0 |
| Timer/Alarm Skills | 8 | 7 | HIGH | 1 | 56 | P0 |
| Home Assistant Integration | 6 | 8 | HIGH | 2 | 24 | P1 |
| Local LLM (Ollama) | 7 | 9 | MEDIUM | 4 | 12 | P1 |
| Multi-turn Context | 5 | 7 | MEDIUM | 4 | 7 | P2 |
| Web Configuration UI | 6 | 6 | HIGH | 3 | 12 | P1 |
| Custom Wake Words | 3 | 5 | MEDIUM | 5 | 2 | P3 |
| Multi-room/Satellite | 4 | 6 | LOW | 6 | 3 | P3 |
| Matter/Thread Direct | 4 | 7 | LOW | 5 | 4 | P2 |
| Mobile Companion App | 5 | 5 | MEDIUM | 6 | 3 | P3 |
| Voice Cloning | 2 | 4 | LOW | 5 | 1 | P4 |

### Priority Legend
- **P0:** Must have for v1.0 launch
- **P1:** Target for v1.x (within 3 months post-launch)
- **P2:** Target for v1.5+ (within 6 months)
- **P3:** Target for v2.0
- **P4:** Nice to have, no timeline

---

## Hardware Requirements Summary

### Minimum (v1.0)
- Raspberry Pi 4 (4GB RAM)
- USB microphone with decent quality
- Speaker (3.5mm or USB)
- ~8 second command processing acceptable

### Recommended (v1.x)
- Intel N100 or equivalent (e.g., mini PC)
- Dual microphone array (for noise cancellation)
- 16GB RAM (for comfortable LLM operation)
- <1 second command processing

### Optimal (v2+)
- Intel NUC i5+ or equivalent
- 32-64GB RAM
- Optional: GPU for larger LLM models
- <500ms command processing

---

## Sources

### HIGH Confidence (Official Documentation, Peer-Reviewed Research)

- [Home Assistant Voice Preview Edition](https://www.home-assistant.io/voice-pe/) - Official Home Assistant documentation on local voice processing
- [OpenVoiceOS Official Site](https://www.openvoiceos.org/) - OVOS architecture and features
- [OpenVoiceOS GitHub](https://github.com/openVoiceOS) - Technical implementation details
- [Rhasspy Documentation](https://rhasspy.readthedocs.io/) - Rhasspy architecture and protocol specs
- [Piper TTS GitHub](https://github.com/rhasspy/piper) - Official Piper documentation
- [openWakeWord GitHub](https://github.com/dscripka/openWakeWord) - Wake word detection benchmarks
- [Whisper Large V3 Technical Analysis](https://localaimaster.com/models/whisper-large-v3) - Hardware requirements and performance
- [Matter Standard Wikipedia](https://en.wikipedia.org/wiki/Matter_(standard)) - Smart home protocol documentation
- [Home Assistant Matter Integration](https://www.home-assistant.io/integrations/matter/) - Matter implementation details
- [Picovoice Wake Word Benchmarking](https://picovoice.ai/blog/benchmarking-a-wake-word-detection-engine/) - Industry wake word accuracy benchmarks
- [PMC: Voice Assistant Usability Review](https://pmc.ncbi.nlm.nih.gov/articles/PMC9063617/) - Systematic review of voice assistant usability
- [Sensory Wake Word Accuracy Study](https://www.sensory.com/revisiting-wake-word-accuracy-and-privacy/) - Wake word accuracy comparison

### MEDIUM Confidence (Industry Reports, Developer Blogs, Community Research)

- [EMARKETER Voice Assistant Statistics](https://www.emarketer.com/learningcenter/guides/voice-assistants/) - Market data and user statistics
- [DemandSage Voice Search Statistics](https://www.demandsage.com/voice-search-statistics/) - Voice search adoption data
- [PwC Consumer Voice Study](https://www.pwc.com/us/en/services/consulting/library/consumer-intelligence-series/voice-assistants.html) - User behavior research
- [Fortune Alexa Memos Leak](https://fortune.com/2024/11/18/new-ai-alexa-latency-problems-echo-compatibility-uber-opentable/) - Internal Amazon findings on latency issues
- [Twilio Voice AI Latency Guide](https://www.twilio.com/en-us/blog/developers/best-practices/guide-core-latency-ai-voice-agents) - Latency requirements for conversational AI
- [AssemblyAI Low Latency Voice Agent](https://www.assemblyai.com/blog/how-to-build-lowest-latency-voice-agent-vapi) - Achieving 465ms latency
- [Modal Low Latency Voice Bot](https://modal.com/blog/low-latency-voice-bot) - 1-second voice-to-voice latency
- [Choosing Whisper Variants (Modal)](https://modal.com/blog/choosing-whisper-variants) - faster-whisper vs WhisperX comparison
- [AMD Whisper on NPU](https://www.amd.com/en/developer/resources/technical-articles/2025/unlocking-on-device-asr-with-whisper-on-ryzen-ai-npus.html) - Hardware acceleration options
- [CNX Software OpenVoiceOS Foundation](https://www.cnx-software.com/2025/02/24/the-openvoiceos-foundation-aims-to-enable-open-source-privacy-and-customization-for-voice-assistants/) - OVOS organization news
- [NPR Smart Speaker Statistics](https://www.npr.org/about-npr/1105579648/npr-edison-research-smart-speaker-ownership-reaches-35-of-americans) - Adoption statistics
- [TermsFeed Voice Privacy Issues](https://www.termsfeed.com/blog/voice-assistants-privacy-issues/) - Privacy concern analysis
- [CMSwire Alexa Analysis](https://www.cmswire.com/digital-experience/analyzing-alexa-voice-is-not-ready-for-prime-time-cx/) - Voice assistant pain points
- [SoundHound Accessibility](https://www.soundhound.com/voice-ai-blog/how-voice-assistants-improve-accessibility/) - Accessibility use cases
- [Battle for Blindness AI Voice Assistants](https://battleforblindness.org/voice-activated-assistants-how-ai-is-empowering-the-visually-impaired) - Accessibility research

### LOW Confidence (Blog Posts, Community Forums, Unverified Claims)

- [The Manifest Siri/Alexa Fails](https://themanifest.com/digital-marketing/resources/siri-alexa-fails-frustrations-with-voice-search) - User frustration anecdotes
- [Fleksy Voice Assistant Flaws](https://www.fleksy.com/blog/5-major-flaws-of-voice-assistant-technology-in-2022/) - General criticism (dated)
- [ThinkRobotics Offline Voice Tutorial](https://thinkrobotics.com/blogs/tutorials/building-an-offline-voice-assistant-with-local-llm-and-audio-processing) - Implementation guide
- [Dialzara Hardware Guide](https://dialzara.com/blog/ai-voice-hardware-requirements-compatibility-guide) - Hardware recommendations
- [Home Assistant Community Discussions](https://community.home-assistant.io/) - User experiences and troubleshooting
- Various comparison blogs (smarttechbase.com, pmsltech.net) - Feature comparisons

---

## Key Insights Summary

### What Users Actually Use Voice Assistants For
1. **Simple queries** - Weather, time, basic facts (most common)
2. **Timers and alarms** - Hands-free utility
3. **Music/media control** - Play, pause, volume
4. **Smart home** - Lights, thermostats, basic control
5. **Shopping** - Research more than purchase (51% vs 22%)

### What Users Complain About Most
1. **Misunderstanding commands** - Accents, background noise, similar words
2. **Slow responses** - >1.5 seconds feels broken
3. **Accidental activation** - 64% experience monthly false wakes
4. **Privacy fears** - 41% fear active listening
5. **Over-verbose responses** - Voice UI should be terse
6. **Forced updates** - Breaking familiar patterns

### What Differentiates Privacy-First Assistants
1. **Transparency** - Clear about what's processed and stored
2. **Local processing** - No cloud dependency for core functions
3. **Open source** - Auditable code
4. **User control** - Export, delete, own your data
5. **Offline capability** - Works without internet

### Critical Technical Thresholds
- **Wake word false positive:** <0.5 per hour acceptable
- **Wake word false reject:** <5% acceptable
- **Response latency:** <1.5s functional, <500ms ideal
- **STT accuracy:** 90%+ for common commands
- **RAM for LLM:** 16GB comfortable, 32GB recommended for 7B+ models
