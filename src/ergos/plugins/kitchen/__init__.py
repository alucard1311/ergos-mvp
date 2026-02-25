"""Kitchen bot plugin for Ergos.

Provides step-by-step cooking guidance with voice acknowledgment,
timers, and intelligent assistance.

Activation phrases:
- "let's cook", "help me make", "recipe for", "kitchen mode"
- "what can I cook with", "I want to make"

Example conversation:
    User: "Hey Ergos, let's make pasta carbonara"
    Chef: "Pasta carbonara, great choice! Are you a beginner,
           intermediate, or expert cook?"
    User: "Intermediate"
    Chef: "Perfect! This'll take about 25 minutes. Step one:
           Fill a large pot with water, add salt, and bring to
           a boil. Say next when your water's heating up."
    User: "Done"
    Chef: "Nice! Step two: ..."
"""

import logging
from typing import Optional

from ergos.plugins.base import BasePlugin
from ergos.llm.types import GenerationConfig

from .intent import IntentClassifier, KitchenIntent
from .memory import UserMemoryStore
from .prompts import (
    RECIPE_GENERATION_PROMPT,
    STEP_SPEAK_PROMPT,
    CLARIFY_PROMPT,
    SUBSTITUTE_PROMPT,
    UNKNOWN_INTENT_PROMPT,
)
from .session import KitchenSession, SessionPhase
from .timers import TimerManager
from .types import Recipe, SkillLevel

logger = logging.getLogger(__name__)

__all__ = ["KitchenPlugin"]

# Phrases that activate the kitchen plugin
ACTIVATION_PHRASES = [
    "let's cook",
    "lets cook",
    "help me make",
    "recipe for",
    "kitchen mode",
    "what can i cook",
    "i want to make",
    "how do i make",
    "how do i cook",
    "teach me to make",
    "teach me to cook",
    "start cooking",
    "cooking mode",
    "chef mode",
]


class KitchenPlugin(BasePlugin):
    """Kitchen bot plugin for step-by-step cooking guidance.

    Features:
    - Generates recipes using existing Phi-3 LLM
    - Walks through recipes step-by-step with voice acknowledgment
    - Supports timers, substitutions, clarifications
    - Remembers user skill level and preferences
    """

    def __init__(self) -> None:
        """Initialize kitchen plugin."""
        super().__init__()
        self._session: Optional[KitchenSession] = None
        self._memory = UserMemoryStore()
        self._timer_manager: Optional[TimerManager] = None

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "kitchen"

    @property
    def activation_phrases(self) -> list[str]:
        """Phrases that activate this plugin."""
        return ACTIVATION_PHRASES

    def should_activate(self, text: str) -> bool:
        """Check if input should activate this plugin.

        Args:
            text: User's transcribed speech (lowercase).

        Returns:
            True if any activation phrase is found.
        """
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in ACTIVATION_PHRASES)

    async def activate(self) -> None:
        """Activate the plugin and set up timer manager."""
        await super().activate()

        # Create timer manager with speak callback
        self._timer_manager = TimerManager(alert_callback=self._speak_text)
        logger.info("Kitchen plugin activated")

    async def handle_input(self, text: str) -> bool:
        """Handle user input when plugin is active.

        Args:
            text: User's transcribed speech.

        Returns:
            True if input was handled.
        """
        # Activate if not already active
        if not self._is_active:
            await self.activate()
            # Create session with user's request
            self._session = KitchenSession(original_request=text)

            # Check if we have stored skill level
            stored_skill = self._memory.prefs.skill_level
            if stored_skill and stored_skill != "unknown":
                # Use stored skill level
                skill = SkillLevel.from_string(stored_skill)
                self._session.skill_level = skill
                self._session.skill_asked = True
                self._session.phase = SessionPhase.GENERATING_RECIPE

                # Extract recipe name from request
                recipe_name = self._extract_recipe_name(text)
                await self._speak_text(
                    f"{recipe_name}, great choice! Let me put together a recipe for you."
                )

                # Generate recipe
                await self._generate_recipe()
            else:
                # Ask for skill level
                recipe_name = self._extract_recipe_name(text)
                await self._speak_text(
                    f"{recipe_name}, great choice! Are you a beginner, "
                    "intermediate, or expert cook?"
                )
            return True

        # Classify intent
        intent, data = IntentClassifier.classify(text)
        logger.info(f"Kitchen intent: {intent.value}, data: {data}")

        # Handle based on session phase and intent
        if self._session is None:
            # Shouldn't happen, but recover
            self._session = KitchenSession(original_request=text)

        # Handle exit intent (always available)
        if intent == KitchenIntent.EXIT:
            await self._handle_exit()
            return True

        # Handle based on current phase
        phase = self._session.phase

        if phase == SessionPhase.AWAITING_SKILL:
            return await self._handle_skill_response(text)

        elif phase == SessionPhase.COOKING:
            return await self._handle_cooking_intent(intent, text, data)

        elif phase == SessionPhase.PAUSED:
            if intent == KitchenIntent.RESUME:
                self._session.resume()
                await self._speak_current_step()
            else:
                await self._speak_text(
                    "We're paused. Say continue when you're ready."
                )
            return True

        elif phase == SessionPhase.COMPLETED:
            await self._speak_text(
                "The recipe is complete! Say exit kitchen to leave, "
                "or tell me another dish you'd like to make."
            )
            # Check if they want to cook something else
            if self.should_activate(text.lower()):
                self._session = KitchenSession(original_request=text)
                return await self.handle_input(text)
            return True

        return True

    async def deactivate(self) -> None:
        """Clean up when plugin deactivates."""
        # Cancel all timers
        if self._timer_manager:
            await self._timer_manager.cancel_all()
            self._timer_manager = None

        # Save recipe to history if we have one
        if self._session and self._session.recipe:
            self._memory.add_recipe_to_history(
                recipe_name=self._session.recipe.name,
                completed=self._session.is_complete,
            )

        self._session = None
        self._is_active = False
        logger.info("Kitchen plugin deactivated")

    # ========== Intent Handlers ==========

    async def _handle_skill_response(self, text: str) -> bool:
        """Handle response to skill level question.

        Args:
            text: User's response.

        Returns:
            True (always handles).
        """
        skill = SkillLevel.from_string(text)
        self._session.set_skill_level(skill)

        # Save to memory
        self._memory.update_skill_level(skill.value)

        await self._speak_text(
            f"Got it, {skill.value} level. Let me put together a recipe for you."
        )

        # Generate recipe
        await self._generate_recipe()
        return True

    async def _handle_cooking_intent(
        self,
        intent: KitchenIntent,
        text: str,
        data: Optional[str],
    ) -> bool:
        """Handle intents during cooking phase.

        Args:
            intent: Classified intent.
            text: Original user input.
            data: Extracted data from intent classification.

        Returns:
            True (always handles).
        """
        if intent == KitchenIntent.ADVANCE:
            await self._handle_advance()

        elif intent == KitchenIntent.REPEAT:
            await self._speak_current_step()

        elif intent == KitchenIntent.PAUSE:
            self._session.pause()
            await self._speak_text(
                "Okay, I'll pause here. Say continue when you're ready."
            )

        elif intent == KitchenIntent.TIMER:
            await self._handle_timer(data)

        elif intent == KitchenIntent.SUBSTITUTE:
            await self._handle_substitute(text)

        elif intent == KitchenIntent.CLARIFY:
            await self._handle_clarify(text)

        elif intent == KitchenIntent.LIST_INGREDIENTS:
            await self._handle_list_ingredients()

        elif intent == KitchenIntent.NUTRITION:
            await self._speak_text(
                "I don't have detailed nutrition info, but I can tell you "
                "this recipe serves {self._session.servings}."
            )

        elif intent == KitchenIntent.SCALE:
            await self._speak_text(
                "Recipe scaling coming soon! For now, the recipe serves "
                f"{self._session.servings}."
            )

        else:
            # Unknown intent - use LLM for interpretation
            await self._handle_unknown(text)

        return True

    async def _handle_advance(self) -> None:
        """Handle advancing to next step."""
        if self._session.advance():
            if self._session.is_complete:
                await self._speak_text(
                    f"Congratulations! Your {self._session.recipe.name} is ready. "
                    "Enjoy your meal! Say exit kitchen when you're done."
                )
                self._session.phase = SessionPhase.COMPLETED
            else:
                await self._speak_current_step()
        else:
            await self._speak_text(
                "That was the last step! Your dish is ready. Enjoy!"
            )
            self._session.phase = SessionPhase.COMPLETED

    async def _handle_timer(self, duration_str: Optional[str]) -> None:
        """Handle timer request.

        Args:
            duration_str: Parsed duration string (e.g., "5 minutes").
        """
        if not duration_str:
            await self._speak_text(
                "How long should I set the timer for? "
                "Say something like set timer for 5 minutes."
            )
            return

        if self._timer_manager:
            # Create label from current step
            label = f"step {self._session.current_step_number}"
            timer = await self._timer_manager.create_timer(duration_str, label)

            if timer:
                await self._speak_text(
                    f"Got it, {duration_str} timer starting now. "
                    "I'll let you know when it's done."
                )
            else:
                await self._speak_text(
                    f"I couldn't understand that duration. "
                    "Try saying something like 5 minutes or 30 seconds."
                )

    async def _handle_substitute(self, text: str) -> None:
        """Handle ingredient substitution request.

        Args:
            text: User's substitution request.
        """
        if self._llm is None:
            await self._speak_text(
                "I'm not able to suggest substitutes right now. "
                "A common substitution might work though!"
            )
            return

        prompt = SUBSTITUTE_PROMPT.format(
            recipe_name=self._session.recipe.name if self._session.recipe else "the recipe",
            current_instruction=self._session.current_instruction or "",
            user_input=text,
            skill_level=self._session.skill_level.value,
        )

        response = self._llm.generate(
            prompt,
            config=GenerationConfig(max_tokens=150, temperature=0.7),
        )
        await self._speak_text(response.text.strip())

    async def _handle_clarify(self, text: str) -> None:
        """Handle clarification question.

        Args:
            text: User's question.
        """
        if self._llm is None:
            await self._speak_text(
                "I can't provide more details right now, but "
                "the step instructions should guide you through it."
            )
            return

        prompt = CLARIFY_PROMPT.format(
            recipe_name=self._session.recipe.name if self._session.recipe else "the recipe",
            step_num=self._session.current_step_number,
            total_steps=self._session.total_steps,
            current_instruction=self._session.current_instruction or "",
            question=text,
            skill_level=self._session.skill_level.value,
        )

        response = self._llm.generate(
            prompt,
            config=GenerationConfig(max_tokens=150, temperature=0.7),
        )
        await self._speak_text(response.text.strip())

    async def _handle_list_ingredients(self) -> None:
        """List all recipe ingredients."""
        if not self._session.recipe or not self._session.recipe.ingredients:
            await self._speak_text("I don't have the ingredient list available.")
            return

        ingredients = self._session.recipe.ingredients
        count = len(ingredients)

        # For voice, summarize rather than listing all
        if count <= 5:
            names = [ing.name for ing in ingredients]
            await self._speak_text(
                f"You'll need {count} ingredients: {', '.join(names)}."
            )
        else:
            # Just give count and offer to repeat
            await self._speak_text(
                f"This recipe uses {count} ingredients. "
                "Would you like me to go through them?"
            )

    async def _handle_unknown(self, text: str) -> None:
        """Handle unknown intent using LLM.

        Args:
            text: User's input.
        """
        if self._llm is None:
            await self._speak_text(
                "I didn't catch that. Say next to continue, "
                "repeat to hear the step again, or exit kitchen to leave."
            )
            return

        prompt = UNKNOWN_INTENT_PROMPT.format(
            user_input=text,
            recipe_name=self._session.recipe.name if self._session.recipe else "the recipe",
            step_num=self._session.current_step_number,
            total_steps=self._session.total_steps,
            current_instruction=self._session.current_instruction or "",
        )

        response = self._llm.generate(
            prompt,
            config=GenerationConfig(max_tokens=100, temperature=0.7),
        )
        await self._speak_text(response.text.strip())

    async def _handle_exit(self) -> None:
        """Handle exit request."""
        await self._speak_text("Kitchen mode ended. What else can I help with?")
        await self.deactivate()

    # ========== Recipe Generation ==========

    async def _generate_recipe(self) -> None:
        """Generate recipe using LLM."""
        if self._llm is None:
            await self._speak_text(
                "I'm not able to generate recipes right now. "
                "Please try again later."
            )
            self._session.phase = SessionPhase.COMPLETED
            return

        # Build prompt
        allergies = ", ".join(self._memory.prefs.allergies) or "none"
        restrictions = ", ".join(self._memory.prefs.dietary_restrictions) or "none"

        prompt = RECIPE_GENERATION_PROMPT.format(
            user_request=self._session.original_request,
            servings=self._session.servings,
            skill_level=self._session.skill_level.value,
            allergies=allergies,
            dietary_restrictions=restrictions,
        )

        # Generate recipe
        response = self._llm.generate(
            prompt,
            config=GenerationConfig(max_tokens=800, temperature=0.7),
        )

        # Parse recipe
        recipe = Recipe.from_llm_response(response.text)

        if recipe is None:
            logger.warning(f"Failed to parse recipe from: {response.text[:200]}...")
            await self._speak_text(
                "I had trouble creating that recipe. "
                "Could you try asking for something else?"
            )
            self._session.phase = SessionPhase.COMPLETED
            return

        # Store recipe and start cooking
        self._session.set_recipe(recipe)

        # Announce recipe
        await self._speak_text(
            f"Perfect! {recipe.name} coming up. "
            f"This will take about {recipe.total_time_minutes} minutes "
            f"and serves {recipe.servings}. "
            "Let's get started!"
        )

        # Speak first step
        await self._speak_current_step()

    async def _speak_current_step(self) -> None:
        """Speak the current recipe step in a conversational way."""
        if not self._session or not self._session.recipe:
            return

        instruction = self._session.current_instruction
        if not instruction:
            return

        step = self._session.recipe.steps[self._session.current_step]

        # For simple cases, just speak directly
        if self._llm is None:
            step_text = (
                f"Step {self._session.current_step_number}: {instruction}. "
                "Say next when ready."
            )
            await self._speak_text(step_text)
            return

        # Use LLM to make it conversational
        warning_note = f"Safety note: {step.warning}" if step.warning else ""

        prompt = STEP_SPEAK_PROMPT.format(
            step_num=self._session.current_step_number,
            total_steps=self._session.total_steps,
            instruction=instruction,
            skill_level=self._session.skill_level.value,
            warning_note=warning_note,
        )

        response = self._llm.generate(
            prompt,
            config=GenerationConfig(max_tokens=150, temperature=0.7),
        )

        await self._speak_text(response.text.strip())

    # ========== Helpers ==========

    def _extract_recipe_name(self, text: str) -> str:
        """Extract recipe name from activation request.

        Args:
            text: User's request (e.g., "let's make pasta carbonara").

        Returns:
            Extracted recipe name or generic "That".
        """
        text_lower = text.lower()

        # Remove activation phrases to get dish name
        for phrase in ACTIVATION_PHRASES:
            if phrase in text_lower:
                # Get text after the phrase
                idx = text_lower.find(phrase)
                after = text[idx + len(phrase):].strip()
                if after:
                    # Clean up common words
                    for word in ["a ", "an ", "some ", "the "]:
                        if after.lower().startswith(word):
                            after = after[len(word):]
                    return after.strip().title() or "That"

        return "That"
