# Ergos Product Requirements Document

## Overview

**Product Name:** Ergos
**Tagline:** "Energy from the edge"
**Symbol:** ◐

Ergos is a local-first voice assistant that runs entirely on your hardware. No cloud. No subscriptions. No data leaving your machine.

## Problem Statement

Current voice assistants (Alexa, Siri, Google Assistant) require:
- Constant internet connectivity
- Sending all voice data to corporate servers
- Monthly subscriptions for advanced features
- No control over the AI's personality or behavior

Users who value privacy, customization, or offline capability have no good alternatives.

## Solution

A fully local voice assistant with:
- Sub-second response latency
- Complete privacy (all processing on-device)
- Customizable personality via personas
- Natural conversation with barge-in support
- Open source and extensible

## Target Users

1. **Privacy-conscious individuals** - Want voice control without surveillance
2. **Developers/tinkerers** - Want to customize and extend their assistant
3. **Offline users** - Need voice assistant without reliable internet
4. **Power users** - Want faster, more capable assistant than cloud offerings

## Key Features

### 1. Privacy-First Architecture
- All processing happens locally (STT, LLM, TTS)
- No network requests to external services
- No data collection or telemetry by default
- User owns all conversation data

### 2. Sub-Second Latency
- Optimized pipeline: VAD → STT → LLM → TTS
- Streaming responses (starts speaking before full response generated)
- Local models tuned for speed

### 3. Natural Conversation (Barge-In)
- User can interrupt AI mid-sentence
- AI stops immediately and listens
- Conversation flows naturally like human dialogue

### 4. Customizable Personality (Personas)
- YAML-based persona configuration
- Adjustable traits: humor, formality, verbosity, warmth
- Custom system prompts
- Multiple personas switchable on demand

### 5. Hardware Adaptive
- Auto-detects available hardware (NVIDIA GPU, Apple Silicon, CPU)
- Selects appropriate models for available resources
- Scales from laptop to workstation

## User Experience

### Voice Interaction Flow
1. User speaks to Ergos
2. Voice Activity Detection (VAD) triggers recording
3. Speech-to-Text converts audio to text
4. LLM generates response
5. Text-to-Speech converts response to audio
6. Audio plays back to user

### Barge-In Flow
1. Ergos is speaking a response
2. User starts speaking (interrupting)
3. Ergos immediately stops playback
4. Ergos listens to user's new input
5. Cycle continues

## Persona System

### Default Persona Traits
- **Concise**: 1-2 sentences unless asked for detail
- **Dry wit**: Subtle humor, not forced
- **Warm but not sycophantic**: Friendly without excessive praise
- **Honest**: Direct even when uncomfortable
- **Never says "As an AI..."**: Speaks naturally
- **Never apologizes unnecessarily**: Confident
- **Curious**: Shows interest in user's projects

### Configurable Attributes
| Attribute | Range | Default |
|-----------|-------|---------|
| Humor Level | 0-100 | 60 |
| Formality | 0-100 | 30 |
| Verbosity | 0-100 | 20 |
| Warmth | 0-100 | 70 |

## Hardware Requirements

| Tier | Hardware | Experience |
|------|----------|------------|
| Minimum | 8GB RAM, CPU only | Functional, slower responses |
| Recommended | 16GB RAM, NVIDIA RTX 3060+ | Good experience |
| Optimal | 32GB RAM, NVIDIA RTX 4080+ | Best experience |
| Apple | M1 Pro+ with 16GB+ | Good experience |

## Success Metrics

1. **Response latency** < 1 second (voice-to-voice)
2. **Transcription accuracy** > 95% for clear speech
3. **Barge-in response** < 100ms to stop playback
4. **Memory usage** < 8GB for full pipeline
5. **User satisfaction** - feels like natural conversation

## Out of Scope (v1.0)

- Multi-user support
- Wake word detection (future)
- Smart home integrations (future)
- Mobile apps (future)
- Multi-language support (English only for v1)

## Privacy Commitments

1. **No telemetry** by default
2. **No network requests** for core functionality
3. **Local storage only** for any saved data
4. **User controls** all data retention settings
5. **Open source** for full auditability
