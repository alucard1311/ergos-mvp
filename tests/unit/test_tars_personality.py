"""Unit tests for TARS personality infrastructure.

Tests for TARSPromptBuilder, try_sarcasm_command, get_time_context,
PersonaConfig sarcasm_level field, and TARS default persona.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
import pydantic

from ergos.persona.builder import TARSPromptBuilder, get_time_context, try_sarcasm_command
from ergos.persona.loader import DEFAULT_PERSONA, load_persona
from ergos.config import PersonaConfig


class TestPromptBuilder:
    """Tests for TARSPromptBuilder.build()."""

    def setup_method(self):
        self.builder = TARSPromptBuilder()

    def test_neutral_prompt_has_no_humor(self):
        """Sarcasm level 0 produces a neutral prompt with no humor section."""
        prompt = self.builder.build(
            name="TARS",
            sarcasm_level=0,
            memories=[],
            time_context="",
        )
        # Identity: competent, direct
        assert "TARS" in prompt
        assert "competent" in prompt.lower() or "capable" in prompt.lower() or "direct" in prompt.lower()
        # No humor section
        assert "humor" not in prompt.lower() and "wit" not in prompt.lower() and "funny" not in prompt.lower()

    def test_max_sarcasm_prompt_has_humor(self):
        """Sarcasm level 100 produces a prompt with humor, deadpan style, emotion hints guidance."""
        prompt = self.builder.build(
            name="TARS",
            sarcasm_level=100,
            memories=[],
            time_context="",
        )
        # Should have humor-related content
        assert any(word in prompt.lower() for word in ["humor", "wit", "deadpan", "sarcasm", "dry"])
        # Should guide use of emotion hints
        assert any(word in prompt.lower() for word in ["sighs", "chuckles", "ellipsis", "emotion"])

    def test_mid_sarcasm_prompt(self):
        """Sarcasm level 50 produces a prompt with a frequency modifier for humor."""
        prompt = self.builder.build(
            name="TARS",
            sarcasm_level=50,
            memories=[],
            time_context="",
        )
        # Mid-range should have some humor with a frequency word
        assert any(word in prompt.lower() for word in ["most", "some", "occasional", "frequent"])

    def test_memories_injected(self):
        """When memories list is non-empty, the prompt contains the memory block."""
        memories = ["likes dark coffee", "works late"]
        prompt = self.builder.build(
            name="TARS",
            sarcasm_level=75,
            memories=memories,
            time_context="",
        )
        assert "What you know about the user:" in prompt
        assert "likes dark coffee" in prompt
        assert "works late" in prompt

    def test_empty_memories_omitted(self):
        """When memories list is empty, no memory block appears in the prompt."""
        prompt = self.builder.build(
            name="TARS",
            sarcasm_level=75,
            memories=[],
            time_context="",
        )
        assert "What you know about the user:" not in prompt

    def test_name_substitution(self):
        """Custom name is used instead of TARS in the prompt."""
        prompt = self.builder.build(
            name="Jarvis",
            sarcasm_level=75,
            memories=[],
            time_context="",
        )
        assert "Jarvis" in prompt
        # "TARS" should not appear as the persona name
        # (May appear in reference text like "like the TARS robot" — that's acceptable)
        assert "You are Jarvis" in prompt

    def test_time_context_injected(self):
        """When time_context is given, the prompt contains it."""
        time_ctx = "It is the morning on a Monday."
        prompt = self.builder.build(
            name="TARS",
            sarcasm_level=75,
            memories=[],
            time_context=time_ctx,
        )
        assert time_ctx in prompt


class TestSarcasmCommand:
    """Tests for try_sarcasm_command()."""

    def test_set_sarcasm_command_parsed(self):
        """Standard sarcasm voice commands are parsed correctly."""
        assert try_sarcasm_command("set sarcasm to 80%") == 80
        assert try_sarcasm_command("change sarcasm to 50 percent") == 50

    def test_non_sarcasm_input_returns_none(self):
        """Non-sarcasm input returns None."""
        assert try_sarcasm_command("what's the weather") is None
        assert try_sarcasm_command("play some music") is None
        assert try_sarcasm_command("hello there") is None

    def test_sarcasm_clamped(self):
        """Out-of-range sarcasm values are clamped to 0-100."""
        assert try_sarcasm_command("set sarcasm to 150%") == 100
        assert try_sarcasm_command("set sarcasm to -10%") == 0


class TestPersonaConfig:
    """Tests for PersonaConfig.sarcasm_level field."""

    def test_sarcasm_level_field(self):
        """PersonaConfig accepts sarcasm_level, defaults to 75."""
        cfg = PersonaConfig(sarcasm_level=80)
        assert cfg.sarcasm_level == 80

    def test_sarcasm_level_default(self):
        """PersonaConfig.sarcasm_level defaults to 75."""
        cfg = PersonaConfig()
        assert cfg.sarcasm_level == 75

    def test_sarcasm_level_rejects_over_100(self):
        """PersonaConfig rejects sarcasm_level > 100."""
        with pytest.raises(pydantic.ValidationError):
            PersonaConfig(sarcasm_level=101)

    def test_sarcasm_level_rejects_negative(self):
        """PersonaConfig rejects sarcasm_level < 0."""
        with pytest.raises(pydantic.ValidationError):
            PersonaConfig(sarcasm_level=-1)


class TestTimeContext:
    """Tests for get_time_context()."""

    def _mock_hour(self, hour: int) -> str:
        """Return time context string for a specific hour."""
        mock_dt = datetime(2026, 3, 4, hour, 0, 0)  # Tuesday
        with patch("ergos.persona.builder.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            return get_time_context()

    def test_time_context_periods(self):
        """Hours map to correct period strings."""
        result_3 = self._mock_hour(3)
        assert "middle of the night" in result_3

        result_9 = self._mock_hour(9)
        assert "morning" in result_9

        result_14 = self._mock_hour(14)
        assert "afternoon" in result_14

        result_19 = self._mock_hour(19)
        assert "evening" in result_19

        result_23 = self._mock_hour(23)
        assert "late at night" in result_23


class TestTARSPersona:
    """Tests for TARS as the default persona."""

    def test_tars_is_default(self):
        """When no persona_file is set, DEFAULT_PERSONA is TARS with is_tars_persona=True."""
        assert DEFAULT_PERSONA.name == "TARS"
        assert DEFAULT_PERSONA.is_tars_persona is True

    def test_custom_persona_file_overrides_default(self, tmp_path):
        """When persona_file is set, load_persona loads from file (TARS default not forced)."""
        persona_yaml = tmp_path / "custom.yaml"
        persona_yaml.write_text(
            "name: Aria\n"
            "description: a friendly assistant\n"
            "personality_traits:\n"
            "  - helpful\n"
            "voice: af_sarah\n"
            "speaking_style: warm\n"
        )
        persona = load_persona(persona_yaml)
        assert persona.name == "Aria"
        assert persona.is_tars_persona is False
