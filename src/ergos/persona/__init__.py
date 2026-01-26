"""Persona system for configurable assistant personalities.

This module provides YAML-based persona configuration that affects
the assistant's system prompt, voice selection, and behavior.
"""

from .loader import DEFAULT_PERSONA, load_persona
from .types import Persona

__all__ = [
    "Persona",
    "load_persona",
    "DEFAULT_PERSONA",
]
