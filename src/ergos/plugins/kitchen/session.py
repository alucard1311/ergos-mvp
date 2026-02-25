"""Session state management for kitchen bot."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .types import Recipe, SkillLevel


class SessionPhase(Enum):
    """Current phase of the kitchen session."""

    AWAITING_SKILL = "awaiting_skill"  # Asking for skill level
    GENERATING_RECIPE = "generating_recipe"  # LLM generating recipe
    COOKING = "cooking"  # Stepping through recipe
    PAUSED = "paused"  # User paused
    COMPLETED = "completed"  # Recipe finished


@dataclass
class KitchenSession:
    """Manages state for an active cooking session.

    Tracks the current recipe, step progress, and session phase.
    """

    # User request that started the session
    original_request: str

    # Recipe being cooked
    recipe: Optional[Recipe] = None

    # Current step (0-indexed)
    current_step: int = 0

    # User's skill level for this session
    skill_level: SkillLevel = SkillLevel.INTERMEDIATE

    # Session phase
    phase: SessionPhase = SessionPhase.AWAITING_SKILL

    # Number of servings (may be scaled)
    servings: int = 4

    # Tracks if skill level was asked (to avoid asking again)
    skill_asked: bool = False

    # Previous phase (for pause/resume)
    _previous_phase: Optional[SessionPhase] = field(default=None, repr=False)

    @property
    def current_instruction(self) -> Optional[str]:
        """Get the current step's instruction.

        Returns:
            Current step instruction or None if no recipe/invalid step.
        """
        if self.recipe is None or self.current_step >= len(self.recipe.steps):
            return None
        return self.recipe.steps[self.current_step].instruction

    @property
    def current_step_number(self) -> int:
        """Get human-readable step number (1-indexed).

        Returns:
            Current step number for display.
        """
        return self.current_step + 1

    @property
    def total_steps(self) -> int:
        """Get total number of steps in the recipe.

        Returns:
            Number of steps or 0 if no recipe.
        """
        return len(self.recipe.steps) if self.recipe else 0

    @property
    def is_complete(self) -> bool:
        """Check if all steps have been completed.

        Returns:
            True if on or past the last step.
        """
        if self.recipe is None:
            return False
        return self.current_step >= len(self.recipe.steps)

    @property
    def is_last_step(self) -> bool:
        """Check if currently on the last step.

        Returns:
            True if on the final step.
        """
        if self.recipe is None:
            return False
        return self.current_step == len(self.recipe.steps) - 1

    @property
    def progress_fraction(self) -> float:
        """Get progress as fraction (0.0 to 1.0).

        Returns:
            Progress fraction.
        """
        if self.total_steps == 0:
            return 0.0
        return self.current_step / self.total_steps

    def advance(self) -> bool:
        """Advance to the next step.

        Returns:
            True if advanced successfully, False if already at end.
        """
        if self.recipe is None:
            return False

        if self.current_step < len(self.recipe.steps) - 1:
            self.current_step += 1
            return True

        # Mark as complete if advancing past last step
        if self.current_step == len(self.recipe.steps) - 1:
            self.current_step += 1  # Move past last step
            self.phase = SessionPhase.COMPLETED
            return True

        return False

    def go_back(self) -> bool:
        """Go back to the previous step.

        Returns:
            True if moved back, False if already at start.
        """
        if self.current_step > 0:
            self.current_step -= 1
            return True
        return False

    def pause(self) -> None:
        """Pause the session."""
        if self.phase != SessionPhase.PAUSED:
            self._previous_phase = self.phase
            self.phase = SessionPhase.PAUSED

    def resume(self) -> None:
        """Resume from pause."""
        if self.phase == SessionPhase.PAUSED and self._previous_phase:
            self.phase = self._previous_phase
            self._previous_phase = None

    def set_recipe(self, recipe: Recipe) -> None:
        """Set the recipe and transition to cooking phase.

        Args:
            recipe: The parsed recipe to cook.
        """
        self.recipe = recipe
        self.servings = recipe.servings
        self.current_step = 0
        self.phase = SessionPhase.COOKING

    def set_skill_level(self, level: SkillLevel) -> None:
        """Set user's skill level.

        Args:
            level: User's cooking skill level.
        """
        self.skill_level = level
        self.skill_asked = True
        # Transition to recipe generation
        self.phase = SessionPhase.GENERATING_RECIPE
