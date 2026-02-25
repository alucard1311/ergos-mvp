"""Intent classification for kitchen bot commands."""

from enum import Enum
from typing import Optional, Tuple


class KitchenIntent(Enum):
    """Recognized intents in kitchen conversations."""

    ADVANCE = "advance"  # "done", "next", "okay", "ready"
    REPEAT = "repeat"  # "repeat", "again", "what?"
    CLARIFY = "clarify"  # Questions about current step
    SCALE = "scale"  # "double it", "half the recipe"
    SUBSTITUTE = "substitute"  # "I don't have X"
    TIMER = "timer"  # "set timer for 5 minutes"
    PAUSE = "pause"  # "pause", "hold on"
    RESUME = "resume"  # "continue", "unpause"
    EXIT = "exit"  # "exit kitchen", "stop cooking"
    NUTRITION = "nutrition"  # "how many calories"
    LIST_INGREDIENTS = "list_ingredients"  # "what ingredients do I need"
    SKILL_RESPONSE = "skill_response"  # Response to skill level question
    UNKNOWN = "unknown"  # Unrecognized intent


# Keyword mappings for fast intent classification
ADVANCE_KEYWORDS = [
    "done",
    "next",
    "okay",
    "ok",
    "got it",
    "ready",
    "continue",
    "finished",
    "check",
    "yep",
    "yes",
    "yeah",
    "alright",
    "move on",
]

REPEAT_KEYWORDS = [
    "repeat",
    "again",
    "what was that",
    "say again",
    "what",
    "huh",
    "sorry",
    "one more time",
    "say that again",
    "didn't catch",
]

PAUSE_KEYWORDS = [
    "pause",
    "hold on",
    "wait",
    "stop",
    "one moment",
    "one second",
    "just a sec",
    "hang on",
]

RESUME_KEYWORDS = [
    "continue",
    "unpause",
    "go ahead",
    "resume",
    "back",
    "i'm back",
]

EXIT_KEYWORDS = [
    "exit kitchen",
    "stop cooking",
    "exit",
    "quit",
    "leave kitchen",
    "done cooking",
    "cancel recipe",
    "end",
]

TIMER_KEYWORDS = [
    "set timer",
    "timer for",
    "start timer",
    "countdown",
    "remind me in",
]

SUBSTITUTE_KEYWORDS = [
    "don't have",
    "substitute",
    "instead of",
    "replacement",
    "alternative",
    "what if i don't have",
    "can i use",
    "swap",
]

SCALE_KEYWORDS = [
    "double",
    "half",
    "triple",
    "scale",
    "more servings",
    "fewer servings",
    "for more people",
]

CLARIFY_KEYWORDS = [
    "how do i",
    "what does",
    "how long",
    "how much",
    "what is",
    "explain",
    "show me",
    "help with",
]

NUTRITION_KEYWORDS = [
    "calories",
    "nutrition",
    "protein",
    "carbs",
    "fat",
    "healthy",
    "nutritional",
]

LIST_INGREDIENTS_KEYWORDS = [
    "ingredients",
    "what do i need",
    "shopping list",
    "list ingredients",
]

SKILL_KEYWORDS = [
    "beginner",
    "intermediate",
    "expert",
    "novice",
    "advanced",
    "amateur",
    "pro",
    "professional",
    "new to cooking",
]


class IntentClassifier:
    """Classifies user input into kitchen-related intents.

    Uses fast keyword matching for common intents. For ambiguous
    cases, the classifier returns UNKNOWN and the plugin may
    use LLM for deeper understanding.
    """

    @staticmethod
    def classify(text: str) -> Tuple[KitchenIntent, Optional[str]]:
        """Classify user input into an intent.

        Args:
            text: User's transcribed speech.

        Returns:
            Tuple of (intent, extracted_data) where extracted_data
            contains relevant parsed information (e.g., timer duration).
        """
        text_lower = text.lower().strip()

        # Check for exit intent first (important to not trap users)
        if any(kw in text_lower for kw in EXIT_KEYWORDS):
            return KitchenIntent.EXIT, None

        # Check for timer intent and extract duration
        for kw in TIMER_KEYWORDS:
            if kw in text_lower:
                duration = IntentClassifier._extract_duration(text_lower)
                return KitchenIntent.TIMER, duration

        # Check for skill level response
        if any(kw in text_lower for kw in SKILL_KEYWORDS):
            return KitchenIntent.SKILL_RESPONSE, text_lower

        # Check for substitute intent
        if any(kw in text_lower for kw in SUBSTITUTE_KEYWORDS):
            return KitchenIntent.SUBSTITUTE, text_lower

        # Check for scale intent
        if any(kw in text_lower for kw in SCALE_KEYWORDS):
            return KitchenIntent.SCALE, text_lower

        # Check for nutrition intent
        if any(kw in text_lower for kw in NUTRITION_KEYWORDS):
            return KitchenIntent.NUTRITION, None

        # Check for list ingredients intent
        if any(kw in text_lower for kw in LIST_INGREDIENTS_KEYWORDS):
            return KitchenIntent.LIST_INGREDIENTS, None

        # Check for clarify intent (questions)
        if any(kw in text_lower for kw in CLARIFY_KEYWORDS) or text_lower.endswith("?"):
            return KitchenIntent.CLARIFY, text_lower

        # Check for pause/resume
        if any(kw in text_lower for kw in PAUSE_KEYWORDS):
            return KitchenIntent.PAUSE, None

        if any(kw in text_lower for kw in RESUME_KEYWORDS):
            return KitchenIntent.RESUME, None

        # Check for repeat intent
        if any(kw in text_lower for kw in REPEAT_KEYWORDS):
            return KitchenIntent.REPEAT, None

        # Check for advance intent (most common during cooking)
        if any(kw in text_lower for kw in ADVANCE_KEYWORDS):
            return KitchenIntent.ADVANCE, None

        # Short confirmations are likely advance intents
        if len(text_lower) <= 15 and text_lower in [
            "done",
            "next",
            "ok",
            "okay",
            "yes",
            "yeah",
            "yep",
            "got it",
            "ready",
        ]:
            return KitchenIntent.ADVANCE, None

        return KitchenIntent.UNKNOWN, text_lower

    @staticmethod
    def _extract_duration(text: str) -> Optional[str]:
        """Extract timer duration from text.

        Args:
            text: Text containing timer request.

        Returns:
            Duration string (e.g., "5 minutes") or None.
        """
        import re

        # Match patterns like "5 minutes", "10 min", "30 seconds"
        patterns = [
            r"(\d+)\s*(minutes?|mins?)",
            r"(\d+)\s*(seconds?|secs?)",
            r"(\d+)\s*(hours?|hrs?)",
            r"for\s+(\d+)",  # "timer for 5"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                num = match.group(1)
                # Determine unit
                if "second" in text or "sec" in text:
                    return f"{num} seconds"
                elif "hour" in text or "hr" in text:
                    return f"{num} hours"
                else:
                    return f"{num} minutes"

        return None
