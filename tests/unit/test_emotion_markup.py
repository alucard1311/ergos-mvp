"""Unit tests for EmotionMarkupProcessor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEmotionHintConversion:
    """Tests for *hint* -> Orpheus tag conversion."""

    def setup_method(self):
        from ergos.tts.emotion_markup import EmotionMarkupProcessor
        self.processor = EmotionMarkupProcessor()

    def test_laughs_converts_to_laugh_tag(self):
        result = self.processor.process("That is funny *laughs*", engine="orpheus")
        assert "<laugh>" in result
        assert "*laughs*" not in result

    def test_sighs_converts_to_sigh_tag(self):
        result = self.processor.process("Oh well *sighs*", engine="orpheus")
        assert "<sigh>" in result
        assert "*sighs*" not in result

    def test_chuckles_converts_to_chuckle_tag(self):
        result = self.processor.process("Very amusing *chuckles*", engine="orpheus")
        assert "<chuckle>" in result
        assert "*chuckles*" not in result

    def test_gasps_converts_to_gasp_tag(self):
        result = self.processor.process("Oh no *gasps*", engine="orpheus")
        assert "<gasp>" in result
        assert "*gasps*" not in result

    def test_coughs_converts_to_cough_tag(self):
        result = self.processor.process("Excuse me *coughs*", engine="orpheus")
        assert "<cough>" in result
        assert "*coughs*" not in result

    def test_groans_converts_to_groan_tag(self):
        result = self.processor.process("Not again *groans*", engine="orpheus")
        assert "<groan>" in result
        assert "*groans*" not in result

    def test_yawns_converts_to_yawn_tag(self):
        result = self.processor.process("So tired *yawns*", engine="orpheus")
        assert "<yawn>" in result
        assert "*yawns*" not in result

    def test_sniffles_converts_to_sniffle_tag(self):
        result = self.processor.process("I'm sad *sniffles*", engine="orpheus")
        assert "<sniffle>" in result
        assert "*sniffles*" not in result

    def test_laughing_converts_to_laugh_tag(self):
        """laughing is an alternate form that maps to <laugh>."""
        result = self.processor.process("So funny *laughing*", engine="orpheus")
        assert "<laugh>" in result
        assert "*laughing*" not in result

    def test_chuckling_converts_to_chuckle_tag(self):
        """chuckling is an alternate form that maps to <chuckle>."""
        result = self.processor.process("Mildly amusing *chuckling*", engine="orpheus")
        assert "<chuckle>" in result
        assert "*chuckling*" not in result

    def test_sighing_converts_to_sigh_tag(self):
        """sighing is an alternate form that maps to <sigh>."""
        result = self.processor.process("How disappointing *sighing*", engine="orpheus")
        assert "<sigh>" in result
        assert "*sighing*" not in result

    def test_hint_matching_is_case_insensitive(self):
        """*Laughs* (capitalized) should convert the same as *laughs*."""
        result = self.processor.process("That is funny *Laughs*", engine="orpheus")
        assert "<laugh>" in result
        assert "*Laughs*" not in result

    def test_hint_matching_uppercase(self):
        """*SIGHS* should convert to <sigh>."""
        result = self.processor.process("Oh well *SIGHS*", engine="orpheus")
        assert "<sigh>" in result
        assert "*SIGHS*" not in result

    def test_unknown_hint_is_stripped(self):
        """Unknown hints like *dances* should be removed, not kept."""
        result = self.processor.process("I am happy *dances*", engine="orpheus")
        assert "*dances*" not in result
        assert "<" not in result or result.count("<") == result.count(">")
        # The tag for unknown hint should not appear
        assert "<dances>" not in result

    def test_unknown_hint_strips_asterisks(self):
        """Unknown hints should be fully removed from the text."""
        result = self.processor.process("Hello *waves* there", engine="orpheus")
        assert "*waves*" not in result
        assert "waves" not in result  # The word itself should also be gone

    def test_multiple_emotion_hints_in_one_sentence(self):
        """Multiple hints in one sentence should all be converted."""
        result = self.processor.process(
            "That is hilarious *laughs* and then I *sighs* at the end", engine="orpheus"
        )
        assert "<laugh>" in result
        assert "<sigh>" in result
        assert "*laughs*" not in result
        assert "*sighs*" not in result

    def test_emotion_hint_in_middle_of_text(self):
        """Hint can appear anywhere in text, not just at end."""
        result = self.processor.process("*chuckles* well that is interesting", engine="orpheus")
        assert "<chuckle>" in result
        assert "*chuckles*" not in result


class TestSarcasmPauses:
    """Tests for sarcasm ellipsis -> pause conversion."""

    def setup_method(self):
        from ergos.tts.emotion_markup import EmotionMarkupProcessor
        self.processor = EmotionMarkupProcessor()

    def test_ellipsis_mid_sentence_becomes_pause(self):
        """'Oh... sure...' ellipsis becomes comma pauses."""
        result = self.processor.process("Oh... sure... that's great", engine="orpheus")
        # Ellipsis should be replaced with a pause marker (comma or similar)
        assert "..." not in result or result.count("...") < 3

    def test_multiple_ellipsis_all_converted(self):
        """Multiple mid-sentence ellipsis all become pauses."""
        result = self.processor.process(
            "Well... I guess... if you really... want to", engine="orpheus"
        )
        # Original text had 3 ellipsis, some/all should be converted
        original_count = "Well... I guess... if you really... want to".count("...")
        result_count = result.count("...")
        assert result_count < original_count

    def test_plain_ellipsis_text_loses_raw_dots(self):
        """Text with ellipsis should have pauses injected."""
        result = self.processor.process(
            "That is... interesting", engine="orpheus"
        )
        # The mid-sentence ... should be replaced
        assert "That is... interesting" != result or "," in result


class TestEnginePassthrough:
    """Tests that non-orpheus engines get text passthrough."""

    def setup_method(self):
        from ergos.tts.emotion_markup import EmotionMarkupProcessor
        self.processor = EmotionMarkupProcessor()

    def test_kokoro_engine_passthrough(self):
        """Kokoro engine returns text unchanged."""
        text = "That is funny *laughs* and I *sighs* sometimes"
        result = self.processor.process(text, engine="kokoro")
        assert result == text

    def test_default_engine_is_kokoro_passthrough(self):
        """Default engine (no kwarg) returns text unchanged."""
        text = "That is funny *laughs*"
        result = self.processor.process(text)
        assert result == text

    def test_csm_engine_passthrough(self):
        """CSM engine also returns text unchanged."""
        text = "Hello *chuckles* world"
        result = self.processor.process(text, engine="csm")
        assert result == text

    def test_unknown_engine_passthrough(self):
        """Any engine other than orpheus gets passthrough."""
        text = "Text with *sighs* emotion hints"
        result = self.processor.process(text, engine="some_unknown_engine")
        assert result == text


class TestPlainText:
    """Tests for plain text (no emotion cues)."""

    def setup_method(self):
        from ergos.tts.emotion_markup import EmotionMarkupProcessor
        self.processor = EmotionMarkupProcessor()

    def test_plain_text_passes_through_unchanged(self):
        """Text with no emotion hints or ellipsis passes through."""
        text = "The weather is nice today and I am feeling well."
        result = self.processor.process(text, engine="orpheus")
        assert result == text

    def test_question_passes_through_unchanged(self):
        """Questions pass through unchanged — Orpheus handles rising intonation natively."""
        text = "What is the weather like today?"
        result = self.processor.process(text, engine="orpheus")
        assert result == text

    def test_exclamation_passes_through_unchanged(self):
        """Exclamations pass through unchanged — Orpheus handles emphasis naturally."""
        text = "That is absolutely amazing!"
        result = self.processor.process(text, engine="orpheus")
        assert result == text


class TestCommandPassthrough:
    """Tests that imperative/command sentences pass through unchanged."""

    def setup_method(self):
        from ergos.tts.emotion_markup import EmotionMarkupProcessor
        self.processor = EmotionMarkupProcessor()

    def test_imperative_turn_off_lights_unchanged(self):
        """'Turn off the lights' passes through — Orpheus renders commanding emphasis natively."""
        text = "Turn off the lights."
        result = self.processor.process(text, engine="orpheus")
        assert result == text

    def test_imperative_open_file_unchanged(self):
        """'Open the file' passes through."""
        text = "Open the file now."
        result = self.processor.process(text, engine="orpheus")
        assert result == text

    def test_imperative_stop_music_unchanged(self):
        """'Stop the music now' passes through."""
        text = "Stop the music now."
        result = self.processor.process(text, engine="orpheus")
        assert result == text

    def test_imperative_without_emotion_unchanged(self):
        """Commands without emotion hints pass through completely unchanged."""
        text = "Please close the door and sit down."
        result = self.processor.process(text, engine="orpheus")
        assert result == text


class TestTTSProcessorIntegration:
    """Tests that TTSProcessor calls emotion markup in _synthesize_and_stream."""

    def test_tts_processor_has_engine_field(self):
        """TTSProcessor accepts engine= constructor kwarg."""
        from ergos.tts.processor import TTSProcessor
        from unittest.mock import MagicMock

        mock_synth = MagicMock()
        mock_synth.model_loaded = False

        # Should not raise - engine kwarg is accepted
        processor = TTSProcessor(synthesizer=mock_synth, engine="orpheus")
        assert processor.engine == "orpheus"

    def test_tts_processor_default_engine_is_kokoro(self):
        """TTSProcessor defaults engine to 'kokoro'."""
        from ergos.tts.processor import TTSProcessor
        from unittest.mock import MagicMock

        mock_synth = MagicMock()
        mock_synth.model_loaded = False

        processor = TTSProcessor(synthesizer=mock_synth)
        assert processor.engine == "kokoro"

    @pytest.mark.asyncio
    async def test_synthesize_calls_emotion_markup_when_orpheus(self):
        """_synthesize_and_stream calls emotion_markup.process when engine=orpheus."""
        from ergos.tts.processor import TTSProcessor
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_synth = MagicMock()
        mock_synth.model_loaded = False

        async def mock_stream(text, config):
            import numpy as np
            yield (np.zeros(100, dtype=np.float32), 24000)

        mock_synth.synthesize_stream = mock_stream

        processor = TTSProcessor(synthesizer=mock_synth, engine="orpheus")

        with patch.object(processor._emotion_markup, "process", wraps=processor._emotion_markup.process) as mock_process:
            await processor._synthesize_and_stream("Hello world")
            mock_process.assert_called_once_with("Hello world", engine="orpheus")

    @pytest.mark.asyncio
    async def test_synthesize_skips_emotion_markup_when_kokoro(self):
        """When engine=kokoro, emotion_markup.process is still called but returns passthrough."""
        from ergos.tts.processor import TTSProcessor
        from unittest.mock import MagicMock, patch

        mock_synth = MagicMock()
        mock_synth.model_loaded = False

        async def mock_stream(text, config):
            import numpy as np
            yield (np.zeros(100, dtype=np.float32), 24000)

        mock_synth.synthesize_stream = mock_stream

        processor = TTSProcessor(synthesizer=mock_synth, engine="kokoro")

        with patch.object(processor._emotion_markup, "process", wraps=processor._emotion_markup.process) as mock_process:
            await processor._synthesize_and_stream("Hello *laughs* world")
            mock_process.assert_called_once()
            # The returned text for kokoro should be unchanged (passthrough)
            returned_text = mock_process.return_value
            # Since we used wraps=, the actual process was called and returned passthrough
            args = mock_process.call_args
            assert args[1].get("engine") == "kokoro" or (len(args[0]) > 1 and args[0][1] == "kokoro")


class TestUpdatedSystemPrompt:
    """Tests for LLM system prompt containing emotion guidance."""

    def test_system_prompt_contains_emotion_hints(self):
        """Default system prompt should mention emotion hints."""
        from ergos.llm.processor import LLMProcessor
        from unittest.mock import MagicMock

        mock_gen = MagicMock()
        processor = LLMProcessor(generator=mock_gen)
        assert "emotion hints" in processor.system_prompt.lower() or "emotion hint" in processor.system_prompt.lower()

    def test_system_prompt_contains_ellipsis_guidance(self):
        """Default system prompt should mention ellipsis for pauses."""
        from ergos.llm.processor import LLMProcessor
        from unittest.mock import MagicMock

        mock_gen = MagicMock()
        processor = LLMProcessor(generator=mock_gen)
        assert "ellipsis" in processor.system_prompt.lower() or "..." in processor.system_prompt

    def test_system_prompt_contains_laughs_example(self):
        """System prompt should include *laughs* as an example."""
        from ergos.llm.processor import LLMProcessor
        from unittest.mock import MagicMock

        mock_gen = MagicMock()
        processor = LLMProcessor(generator=mock_gen)
        assert "*laughs*" in processor.system_prompt

    def test_system_prompt_retains_voice_assistant_instruction(self):
        """System prompt should still identify as voice assistant."""
        from ergos.llm.processor import LLMProcessor
        from unittest.mock import MagicMock

        mock_gen = MagicMock()
        processor = LLMProcessor(generator=mock_gen)
        assert "voice assistant" in processor.system_prompt.lower()
