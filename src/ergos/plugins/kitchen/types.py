"""Data types for the kitchen bot plugin."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SkillLevel(Enum):
    """User's cooking skill level."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"

    @classmethod
    def from_string(cls, value: str) -> "SkillLevel":
        """Parse skill level from user input.

        Args:
            value: User's response (e.g., "beginner", "I'm a beginner").

        Returns:
            Matching SkillLevel, defaults to INTERMEDIATE.
        """
        value_lower = value.lower()
        if "beginner" in value_lower or "novice" in value_lower or "new" in value_lower:
            return cls.BEGINNER
        elif "expert" in value_lower or "advanced" in value_lower or "pro" in value_lower:
            return cls.EXPERT
        elif "intermediate" in value_lower or "average" in value_lower:
            return cls.INTERMEDIATE
        # Default to intermediate
        return cls.INTERMEDIATE


@dataclass
class Ingredient:
    """A recipe ingredient with quantity and unit."""

    name: str
    quantity: Optional[str] = None
    unit: Optional[str] = None

    def __str__(self) -> str:
        """Format ingredient for display."""
        parts = []
        if self.quantity:
            parts.append(self.quantity)
        if self.unit:
            parts.append(self.unit)
        parts.append(self.name)
        return " ".join(parts)


@dataclass
class RecipeStep:
    """A single step in a recipe."""

    number: int
    instruction: str
    duration_minutes: Optional[int] = None
    requires_timer: bool = False
    warning: Optional[str] = None  # Safety warnings (e.g., "Be careful, oil is hot")

    def __str__(self) -> str:
        """Format step for display."""
        time_str = f" ({self.duration_minutes} min)" if self.duration_minutes else ""
        return f"Step {self.number}: {self.instruction}{time_str}"


@dataclass
class Recipe:
    """A complete recipe with ingredients and steps."""

    name: str
    total_time_minutes: int
    servings: int
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[RecipeStep] = field(default_factory=list)
    notes: Optional[str] = None

    @classmethod
    def from_llm_response(cls, text: str) -> Optional["Recipe"]:
        """Parse recipe from LLM-generated text.

        Expected format:
            RECIPE: [Name]
            TOTAL TIME: [X minutes]
            SERVINGS: [N]

            INGREDIENTS:
            - [quantity] [ingredient]
            ...

            STEPS:
            1. [instruction] (TIME: X min)
            ...

        Args:
            text: LLM response text.

        Returns:
            Parsed Recipe or None if parsing fails.
        """
        try:
            lines = text.strip().split("\n")
            recipe_name = ""
            total_time = 30
            servings = 4
            ingredients: list[Ingredient] = []
            steps: list[RecipeStep] = []

            section = None  # Track current section

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Parse header fields
                if line.upper().startswith("RECIPE:"):
                    recipe_name = line.split(":", 1)[1].strip()
                elif line.upper().startswith("TOTAL TIME:"):
                    time_str = line.split(":", 1)[1].strip()
                    # Extract number from "30 minutes" or "30"
                    time_num = "".join(c for c in time_str.split()[0] if c.isdigit())
                    total_time = int(time_num) if time_num else 30
                elif line.upper().startswith("SERVINGS:"):
                    serv_str = line.split(":", 1)[1].strip()
                    serv_num = "".join(c for c in serv_str.split()[0] if c.isdigit())
                    servings = int(serv_num) if serv_num else 4

                # Track sections
                elif line.upper().startswith("INGREDIENTS:"):
                    section = "ingredients"
                elif line.upper().startswith("STEPS:"):
                    section = "steps"

                # Parse ingredients
                elif section == "ingredients" and line.startswith("-"):
                    ing_text = line[1:].strip()
                    # Simple parsing - just store the full text as name
                    ingredients.append(Ingredient(name=ing_text))

                # Parse steps
                elif section == "steps" and line[0].isdigit():
                    # Remove step number prefix (e.g., "1. " or "1) ")
                    step_text = line
                    for i, c in enumerate(line):
                        if c in ".):":
                            step_text = line[i + 1 :].strip()
                            break

                    # Extract time if present (e.g., "(TIME: 5 min)")
                    duration = None
                    if "(TIME:" in step_text.upper() or "(time:" in step_text.lower():
                        import re

                        time_match = re.search(r"\(TIME:\s*(\d+)", step_text, re.IGNORECASE)
                        if time_match:
                            duration = int(time_match.group(1))
                            # Remove time annotation from instruction
                            step_text = re.sub(
                                r"\s*\(TIME:\s*\d+\s*min\)", "", step_text, flags=re.IGNORECASE
                            ).strip()

                    steps.append(
                        RecipeStep(
                            number=len(steps) + 1,
                            instruction=step_text,
                            duration_minutes=duration,
                        )
                    )

            if not recipe_name or not steps:
                return None

            return cls(
                name=recipe_name,
                total_time_minutes=total_time,
                servings=servings,
                ingredients=ingredients,
                steps=steps,
            )

        except Exception:
            return None
