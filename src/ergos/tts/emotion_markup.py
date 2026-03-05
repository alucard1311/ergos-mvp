"""Emotion markup preprocessing for Orpheus TTS.

Transforms LLM text containing emotion hints and ellipsis patterns
into Orpheus-compatible emotion-tagged text for expressive synthesis.
"""

import re


class EmotionMarkupProcessor:
    """Transforms LLM text into Orpheus-compatible emotion-tagged text.

    Handles:
    - Emotion hint conversion: *laughs* -> <laugh>, *sighs* -> <sigh>, etc.
    - Sarcasm pause injection: "Oh... sure..." -> "Oh, sure," with natural pauses
    - Passthrough for non-orpheus engines

    Note: Orpheus 3B natively handles prosody variation for questions
    (rising intonation), exclamations (emphasis), and imperative/command
    sentences (commanding tone) — no special markup needed for these.
    """

    # Map of LLM emotion hints to Orpheus tags
    EMOTION_MAP = {
        "laughs": "<laugh>",
        "laughing": "<laugh>",
        "chuckles": "<chuckle>",
        "chuckling": "<chuckle>",
        "sighs": "<sigh>",
        "sighing": "<sigh>",
        "gasps": "<gasp>",
        "coughs": "<cough>",
        "groans": "<groan>",
        "yawns": "<yawn>",
        "sniffles": "<sniffle>",
    }

    def process(self, text: str, engine: str = "kokoro") -> str:
        """Process text for emotion markup.

        Only transforms when engine is "orpheus". Other engines get passthrough.
        Questions, exclamations, and commands pass through unchanged —
        Orpheus renders these with natural prosody variation automatically.

        Args:
            text: The input text to process.
            engine: The TTS engine name. Only "orpheus" triggers transformation.

        Returns:
            Transformed text for Orpheus, or original text for all other engines.
        """
        if engine != "orpheus":
            return text

        result = self._convert_emotion_hints(text)
        result = self._inject_sarcasm_pauses(result)
        return result

    # Maximum emotion tags per synthesis call to prevent erratic tone shifts
    MAX_EMOTION_TAGS: int = 1

    def _convert_emotion_hints(self, text: str) -> str:
        """Convert *hint* patterns to Orpheus tags.

        Uses regex to find *word* patterns and map to known tags.
        Only keeps the first MAX_EMOTION_TAGS known tags — excess tags
        are stripped to prevent erratic tonal shifts within a sentence.
        Unknown hints are stripped entirely (not spoken by TTS).

        Args:
            text: Text containing potential *hint* patterns.

        Returns:
            Text with first known hint replaced by tag, rest stripped.
        """
        tag_count = 0

        def replace_hint(match: re.Match) -> str:
            nonlocal tag_count
            word = match.group(1).lower()
            if word in self.EMOTION_MAP:
                if tag_count < self.MAX_EMOTION_TAGS:
                    tag_count += 1
                    return self.EMOTION_MAP[word]
                return ""  # Over limit — strip
            return ""  # Unknown hint — strip

        result = re.sub(r"\*(\w+)\*", replace_hint, text)
        result = re.sub(r"  +", " ", result).strip()
        return result

    def _inject_sarcasm_pauses(self, text: str) -> str:
        """Convert ellipsis patterns to Orpheus-friendly pause markers.

        "Oh... sure... that's great" becomes "Oh, sure, that's great"
        with strategic commas that Orpheus renders as natural pauses.

        Triple dots (...) become a comma+space for a brief hesitation pause.
        This gives sarcastic delivery its characteristic timing.

        Trailing ellipsis at the end of a sentence is also converted to
        a comma for a natural trailing-off effect.

        Args:
            text: Text potentially containing ellipsis patterns.

        Returns:
            Text with ellipsis replaced by comma-based pause markers.
        """
        # Replace all "..." occurrences with ", " for natural pause cadence
        # This handles both mid-sentence and trailing ellipsis
        result = re.sub(r"\.\.\.", ", ", text)
        # Clean up any double spaces from adjacent ellipsis replacements
        result = re.sub(r"  +", " ", result).strip()
        # Clean up trailing comma-space if at end
        result = re.sub(r",\s*$", "", result).strip()
        return result
