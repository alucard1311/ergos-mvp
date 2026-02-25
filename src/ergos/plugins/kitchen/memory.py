"""User preferences and memory for kitchen bot."""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default storage path for kitchen preferences
MEMORY_PATH = Path.home() / ".ergos" / "plugins" / "kitchen"


@dataclass
class UserPrefs:
    """User preferences for the kitchen bot.

    Stores cooking skill level, allergies/dietary restrictions,
    and other preferences that persist across sessions.
    """

    skill_level: str = "intermediate"
    allergies: list[str] = field(default_factory=list)
    dietary_restrictions: list[str] = field(default_factory=list)
    preferred_units: str = "metric"  # "metric" or "imperial"
    verbosity: str = "normal"  # "concise", "normal", "detailed"

    def has_allergy(self, ingredient: str) -> bool:
        """Check if user is allergic to an ingredient.

        Args:
            ingredient: Ingredient name to check.

        Returns:
            True if ingredient matches any allergy.
        """
        ingredient_lower = ingredient.lower()
        return any(allergy.lower() in ingredient_lower for allergy in self.allergies)


@dataclass
class RecipeHistory:
    """Record of a cooked recipe."""

    recipe_name: str
    timestamp: float
    completed: bool = False
    rating: Optional[int] = None  # 1-5 stars


@dataclass
class UserMemory:
    """Full user memory including preferences and history.

    Persists to disk and loads on startup.
    """

    prefs: UserPrefs = field(default_factory=UserPrefs)
    recipe_history: list[RecipeHistory] = field(default_factory=list)
    favorite_recipes: list[str] = field(default_factory=list)


class UserMemoryStore:
    """Manages persistence of user preferences and history.

    Stores data as JSON in ~/.ergos/plugins/kitchen/memory.json
    """

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        """Initialize memory store.

        Args:
            storage_path: Custom storage directory (uses default if None).
        """
        self._path = storage_path or MEMORY_PATH
        self._memory: Optional[UserMemory] = None

    @property
    def memory(self) -> UserMemory:
        """Get loaded memory, loading from disk if needed.

        Returns:
            User memory instance.
        """
        if self._memory is None:
            self._memory = self.load()
        return self._memory

    @property
    def prefs(self) -> UserPrefs:
        """Get user preferences.

        Returns:
            User preferences.
        """
        return self.memory.prefs

    def load(self) -> UserMemory:
        """Load memory from disk.

        Returns:
            Loaded UserMemory or new instance if file doesn't exist.
        """
        memory_file = self._path / "memory.json"

        if not memory_file.exists():
            logger.info("No existing kitchen memory, using defaults")
            return UserMemory()

        try:
            data = json.loads(memory_file.read_text())

            # Parse preferences
            prefs_data = data.get("prefs", {})
            prefs = UserPrefs(
                skill_level=prefs_data.get("skill_level", "intermediate"),
                allergies=prefs_data.get("allergies", []),
                dietary_restrictions=prefs_data.get("dietary_restrictions", []),
                preferred_units=prefs_data.get("preferred_units", "metric"),
                verbosity=prefs_data.get("verbosity", "normal"),
            )

            # Parse history
            history = []
            for h in data.get("recipe_history", []):
                history.append(
                    RecipeHistory(
                        recipe_name=h["recipe_name"],
                        timestamp=h["timestamp"],
                        completed=h.get("completed", False),
                        rating=h.get("rating"),
                    )
                )

            memory = UserMemory(
                prefs=prefs,
                recipe_history=history,
                favorite_recipes=data.get("favorite_recipes", []),
            )

            logger.info(f"Loaded kitchen memory from {memory_file}")
            return memory

        except Exception as e:
            logger.warning(f"Failed to load kitchen memory: {e}, using defaults")
            return UserMemory()

    def save(self) -> None:
        """Save memory to disk."""
        if self._memory is None:
            return

        try:
            # Ensure directory exists
            self._path.mkdir(parents=True, exist_ok=True)

            memory_file = self._path / "memory.json"

            # Convert to serializable dict
            data = {
                "prefs": asdict(self._memory.prefs),
                "recipe_history": [asdict(h) for h in self._memory.recipe_history],
                "favorite_recipes": self._memory.favorite_recipes,
            }

            memory_file.write_text(json.dumps(data, indent=2))
            logger.info(f"Saved kitchen memory to {memory_file}")

        except Exception as e:
            logger.error(f"Failed to save kitchen memory: {e}")

    def update_skill_level(self, skill_level: str) -> None:
        """Update and persist skill level.

        Args:
            skill_level: New skill level string.
        """
        self.memory.prefs.skill_level = skill_level
        self.save()

    def add_allergy(self, allergy: str) -> None:
        """Add an allergy.

        Args:
            allergy: Allergy to add.
        """
        if allergy not in self.memory.prefs.allergies:
            self.memory.prefs.allergies.append(allergy)
            self.save()

    def remove_allergy(self, allergy: str) -> None:
        """Remove an allergy.

        Args:
            allergy: Allergy to remove.
        """
        if allergy in self.memory.prefs.allergies:
            self.memory.prefs.allergies.remove(allergy)
            self.save()

    def add_recipe_to_history(
        self,
        recipe_name: str,
        completed: bool = False,
        rating: Optional[int] = None,
    ) -> None:
        """Add a recipe to history.

        Args:
            recipe_name: Name of the recipe.
            completed: Whether the recipe was completed.
            rating: Optional rating (1-5).
        """
        import time

        self.memory.recipe_history.append(
            RecipeHistory(
                recipe_name=recipe_name,
                timestamp=time.time(),
                completed=completed,
                rating=rating,
            )
        )

        # Keep only last 50 recipes
        if len(self.memory.recipe_history) > 50:
            self.memory.recipe_history = self.memory.recipe_history[-50:]

        self.save()

    def add_favorite(self, recipe_name: str) -> None:
        """Add a recipe to favorites.

        Args:
            recipe_name: Recipe name to favorite.
        """
        if recipe_name not in self.memory.favorite_recipes:
            self.memory.favorite_recipes.append(recipe_name)
            self.save()

    def remove_favorite(self, recipe_name: str) -> None:
        """Remove a recipe from favorites.

        Args:
            recipe_name: Recipe name to unfavorite.
        """
        if recipe_name in self.memory.favorite_recipes:
            self.memory.favorite_recipes.remove(recipe_name)
            self.save()
