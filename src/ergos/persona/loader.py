"""Persona loading from YAML files."""

import logging
from pathlib import Path

import yaml

from .types import Persona

logger = logging.getLogger(__name__)


# Default persona: Ergos — used when no persona_file is specified
DEFAULT_PERSONA = Persona(
    name="Ergos",
    description="a highly capable AI assistant with dry wit and deadpan humor",
    personality_traits=["precise", "reliable", "drily observational", "never mean", "understated"],
    voice="af_heart",
    speaking_style="deadpan and direct",
    sarcasm_level=75,
    is_ergos_persona=True,
)


def load_persona(path: Path | str) -> Persona:
    """Load persona configuration from a YAML file.

    YAML format:
        name: "Aria"
        description: "a knowledgeable and friendly assistant"
        personality_traits:
          - helpful
          - patient
          - concise
        voice: "af_sarah"
        speaking_style: "warm and conversational"

    Args:
        path: Path to the persona YAML file.

    Returns:
        Persona loaded from file, or DEFAULT_PERSONA if file not found.
    """
    path = Path(path).expanduser()

    if not path.exists():
        logger.info(f"Persona file not found: {path}, using default persona")
        return DEFAULT_PERSONA

    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        # Map YAML keys to Persona fields
        persona = Persona(
            name=data.get("name", DEFAULT_PERSONA.name),
            description=data.get("description", DEFAULT_PERSONA.description),
            personality_traits=data.get(
                "personality_traits", DEFAULT_PERSONA.personality_traits
            ),
            voice=data.get("voice", DEFAULT_PERSONA.voice),
            speaking_style=data.get("speaking_style", DEFAULT_PERSONA.speaking_style),
            sarcasm_level=data.get("sarcasm_level", DEFAULT_PERSONA.sarcasm_level),
            is_ergos_persona=data.get("is_ergos_persona", False),
        )

        logger.info(f"Loaded persona '{persona.name}' from {path}")
        return persona

    except yaml.YAMLError as e:
        logger.error(f"Failed to parse persona YAML: {e}, using default persona")
        return DEFAULT_PERSONA
    except Exception as e:
        logger.error(f"Error loading persona: {e}, using default persona")
        return DEFAULT_PERSONA
