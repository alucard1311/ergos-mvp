"""Persona type definitions for Ergos voice assistant."""

from dataclasses import dataclass, field


@dataclass
class Persona:
    """Persona configuration for assistant personality.

    A persona defines the assistant's identity, personality traits,
    and speaking style. It generates a system prompt for the LLM
    that shapes response behavior.

    Attributes:
        name: Display name of the assistant (e.g., "TARS", "Aria").
        description: Short bio/description of the assistant.
        personality_traits: List of traits like ["friendly", "concise", "helpful"].
        voice: TTS voice selection (Kokoro voice name).
        speaking_style: Optional style notes like "casual" or "professional".
        sarcasm_level: Humor intensity 0-100; 75 is TARS default.
        is_tars_persona: True when this persona uses the TARS prompt builder.
    """

    name: str
    description: str
    personality_traits: list[str] = field(default_factory=list)
    voice: str = "af_sarah"
    speaking_style: str = ""
    sarcasm_level: int = 75
    is_tars_persona: bool = False

    @property
    def system_prompt(self) -> str:
        """Generate system prompt from persona attributes.

        Builds a prompt that instructs the LLM to embody this persona's
        name, description, traits, and speaking style.

        Returns:
            System prompt string for LLM configuration.
        """
        parts = [f"You are {self.name}, {self.description}."]
        if self.personality_traits:
            traits = ", ".join(self.personality_traits)
            parts.append(f"Your personality is: {traits}.")
        if self.speaking_style:
            parts.append(f"Speaking style: {self.speaking_style}.")
        parts.append("Keep responses concise for voice interaction.")
        return " ".join(parts)
