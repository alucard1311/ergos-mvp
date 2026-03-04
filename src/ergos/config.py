"""Configuration loading and validation for Ergos."""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = "0.0.0.0"
    port: int = 8765


class STTConfig(BaseModel):
    """Speech-to-text configuration."""

    model: str = "base"  # whisper model size
    device: str = "auto"  # auto, cuda, cpu
    compute_type: str = "auto"  # float32, float16, int8, auto


class LLMConfig(BaseModel):
    """Language model configuration."""

    model_path: Optional[str] = None
    context_length: int = 4096
    max_tokens: int = 512
    device: str = "auto"
    chat_format: str = "chatml"  # Chat template format: chatml (Qwen3), llama-3, etc.
    n_gpu_layers: int = -1  # GPU layers to offload: -1 means all layers


class TTSConfig(BaseModel):
    """Text-to-speech configuration."""

    engine: str = "kokoro"  # "kokoro", "csm", or "orpheus"
    voice: str = "af_heart"  # Kokoro voice ID
    speed: float = 1.0
    device: str = "auto"
    model_id: str = "sesame/csm-1b"  # HuggingFace model for CSM engine
    speaker_id: int = 0  # CSM speaker ID
    temperature: float = 0.9  # CSM/Orpheus sampling temperature
    top_k: int = 50  # CSM/Orpheus top-k sampling
    reference_audio: list[str] = []  # Paths to reference audio for voice conditioning
    # Orpheus engine fields
    orpheus_voice: str = "tara"  # Orpheus voice ID (tara, leah, jess, leo, dan, mia, zac, zoe)
    orpheus_n_gpu_layers: int = -1  # GPU layers for Orpheus: -1 means all GPU layers


class PersonaConfig(BaseModel):
    """Persona configuration.

    Supports two modes:
    1. File-based: Set persona_file to path of persona YAML file
    2. Inline: Set name and system_prompt directly (fallback if no file)

    Example YAML:
        persona:
          persona_file: "~/.ergos/personas/aria.yaml"

        OR

        persona:
          name: "Ergos"
          system_prompt: "You are a helpful voice assistant."
    """

    persona_file: Optional[str] = None  # Path to persona YAML file
    # Fallback values if no file specified
    name: str = "TARS"
    system_prompt: str = "You are a helpful voice assistant."
    sarcasm_level: int = Field(default=75, ge=0, le=100)  # Humor intensity 0-100


class Config(BaseModel):
    """Main configuration model for Ergos."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    persona: PersonaConfig = Field(default_factory=PersonaConfig)


def load_config(path: Path | str = "config.yaml") -> Config:
    """Load configuration from YAML file, falling back to defaults."""
    path = Path(path)
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return Config(**data)
    return Config()


def save_config(config: Config, path: Path | str = "config.yaml") -> None:
    """Save configuration to YAML file."""
    path = Path(path)
    with open(path, "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False)
