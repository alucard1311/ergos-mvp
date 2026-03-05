"""Ergos prompt builder with section-based sarcasm blending.

Implements Pattern 1 (section-based blending) from Phase 16 research:
- Two template tiers: NEUTRAL (0%) and MAX_SARCASM (100%)
- Mid-range (21-79%) uses max identity/style, modulates humor frequency
- Voice command parser for live sarcasm adjustment
- Time context helper for context-aware personality hints
"""

import re
from datetime import datetime

# ---------------------------------------------------------------------------
# Section templates — sarcasm level 0 (neutral / serious mission mode)
# ---------------------------------------------------------------------------

ERGOS_NEUTRAL_SECTIONS = {
    "identity": (
        "You are {name}, a highly capable AI assistant. "
        "You are competent, direct, and precise."
    ),
    "style": (
        "Your output is spoken aloud by a text-to-speech engine. "
        "No markdown, bullet points, or numbered lists. "
        "Answer the question clearly and concisely."
    ),
    "emotion": "Omit emotion hints — this is serious mission mode.",
    "humor": "",  # No humor at 0%
}

# ---------------------------------------------------------------------------
# Section templates — sarcasm level 100 (full Ergos deadpan)
# ---------------------------------------------------------------------------

ERGOS_MAX_SARCASM_SECTIONS = {
    "identity": (
        "You are {name}, a highly capable AI assistant with a dry wit — "
        "with a dry wit and deadpan humor. Your humor is always "
        "understated, never mean-spirited."
    ),
    "style": (
        "Your output is spoken aloud by a text-to-speech engine. "
        "No markdown, bullet points, or numbered lists. "
        "Always answer the user's question with real substance first, "
        "then add personality. A witty non-answer is still a non-answer."
    ),
    "emotion": (
        "You may use ONE emotion hint per response at most — *sighs* or *chuckles* — "
        "placed at the start for tone-setting. Never scatter multiple hints across a response. "
        "Use ellipsis (...) for dramatic pauses instead of emotion tags."
    ),
    "humor": (
        "Inject dry humor naturally. Understatement is your weapon. "
        "But never sacrifice a real answer for the sake of a joke."
    ),
}


class ErgosPromptBuilder:
    """Builds Ergos system prompts with sarcasm level blending.

    Supports three tiers:
    - Level 0-20: Neutral (no humor, serious mission mode)
    - Level 21-79: Mid-range (max identity/style, modulated humor frequency)
    - Level 80-100: Max sarcasm (full deadpan, emotion hints, humor every turn)
    """

    def build(
        self,
        name: str,
        sarcasm_level: int,
        memories: list[str],
        time_context: str,
        capabilities: list[str] | None = None,
    ) -> str:
        """Build a complete Ergos system prompt.

        Args:
            name: Assistant name to substitute into the identity section.
            sarcasm_level: Integer 0-100 controlling humor intensity.
            memories: List of user memory strings to inject into the prompt.
            time_context: Natural-language time descriptor (e.g. "It is the morning on a Tuesday.").
            capabilities: Optional list of capability descriptions (tools, plugins, voice commands).

        Returns:
            Complete system prompt string ready for LLM configuration.
        """
        sarcasm_level = max(0, min(100, sarcasm_level))
        sections = self._select_sections(sarcasm_level)

        parts: list[str] = []

        # Identity with name substitution
        parts.append(sections["identity"].format(name=name))

        # Style is always present
        parts.append(sections["style"])

        # Emotion section (only if non-empty)
        if sections["emotion"]:
            parts.append(sections["emotion"])

        # Humor section (only if non-empty)
        if sections["humor"]:
            parts.append(sections["humor"])

        # Capabilities injection
        if capabilities:
            cap_block = "What you can do:\n" + "\n".join(
                f"- {c}" for c in capabilities
            )
            parts.append(cap_block)

        # Time context injection
        if time_context:
            parts.append(time_context)

        # Memory injection
        if memories:
            memory_block = "What you know about the user:\n" + "\n".join(
                f"- {m}" for m in memories
            )
            parts.append(memory_block)

        return "\n\n".join(parts)

    def _select_sections(self, sarcasm_level: int) -> dict[str, str]:
        """Select and return sections dict for the given sarcasm level."""
        if sarcasm_level <= 20:
            return ERGOS_NEUTRAL_SECTIONS.copy()

        if sarcasm_level >= 80:
            return ERGOS_MAX_SARCASM_SECTIONS.copy()

        # Mid-range (21-79): use max identity/style, modulate humor frequency
        frequency = "most" if sarcasm_level >= 50 else "some"
        sections = {
            "identity": ERGOS_MAX_SARCASM_SECTIONS["identity"],
            "style": ERGOS_MAX_SARCASM_SECTIONS["style"],
            "emotion": ERGOS_MAX_SARCASM_SECTIONS["emotion"],
            "humor": (
                f"Add dry humor to {frequency} responses, but always answer the question first. "
                "Understatement and deadpan delivery work best."
            ),
        }
        return sections


# ---------------------------------------------------------------------------
# Sarcasm voice command parser
# ---------------------------------------------------------------------------

# Pattern matches: "set sarcasm to 80%", "change sarcasm to 50 percent",
# "set sarcasm to -10%", "make sarcasm 30", etc.
# Uses (?<!\w) lookbehind so that negative numbers like "-10" are captured whole.
_SARCASM_COMMAND_RE = re.compile(
    r"\b(?:set|change|make|put)\b[^.]*?\bsarcasm\b[^.]*?(?<!\w)(-?\d{1,3})(?!\d)",
    re.IGNORECASE,
)


def try_sarcasm_command(text: str) -> int | None:
    """Parse a sarcasm level adjustment voice command.

    Recognises patterns like:
      - "set sarcasm to 80%"
      - "change sarcasm to 50 percent"
      - "make sarcasm 30"

    Args:
        text: Raw user speech text to parse.

    Returns:
        Clamped integer 0-100 if the text is a sarcasm command, else None.
    """
    match = _SARCASM_COMMAND_RE.search(text)
    if match is None:
        return None
    value = int(match.group(1))
    return max(0, min(100, value))


# ---------------------------------------------------------------------------
# Time context helper
# ---------------------------------------------------------------------------


def get_time_context() -> str:
    """Return a natural-language time descriptor based on current local time.

    Period mapping:
        hour < 6   -> "middle of the night"
        hour < 12  -> "morning"
        hour < 17  -> "afternoon"
        hour < 21  -> "evening"
        else       -> "late at night"

    Returns:
        String like "It is the morning on a Tuesday."
    """
    now = datetime.now()
    hour = now.hour
    day = now.strftime("%A")  # e.g. "Tuesday"

    if hour < 6:
        period = "middle of the night"
    elif hour < 12:
        period = "morning"
    elif hour < 17:
        period = "afternoon"
    elif hour < 21:
        period = "evening"
    else:
        period = "late at night"

    return f"It is the {period} on a {day}."
