"""Base plugin class for Ergos plugins."""

from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ergos.llm.generator import LLMGenerator
    from ergos.tts.processor import TTSProcessor
    from ergos.state import ConversationStateMachine

# Type alias for speak callback
SpeakCallback = Callable[[str], Awaitable[None]]


class BasePlugin(ABC):
    """Base class for Ergos plugins.

    Plugins extend Ergos functionality by handling specific types of
    user interactions. A plugin can activate based on user input and
    take over the conversation flow until it deactivates.

    Subclasses must implement:
        - name: Plugin identifier
        - activation_phrases: Phrases that trigger plugin activation
        - should_activate: Logic to determine if plugin should handle input
        - handle_input: Process user input when plugin is active
        - deactivate: Clean up when plugin deactivates
    """

    def __init__(self) -> None:
        """Initialize plugin with empty component references."""
        self._llm: Optional["LLMGenerator"] = None
        self._tts: Optional["TTSProcessor"] = None
        self._state_machine: Optional["ConversationStateMachine"] = None
        self._speak: Optional[SpeakCallback] = None
        self._is_active: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin identifier.

        Returns:
            A unique string identifying this plugin.
        """
        pass

    @property
    @abstractmethod
    def activation_phrases(self) -> list[str]:
        """Phrases that activate this plugin.

        Returns:
            List of phrases (lowercase) that should trigger plugin activation.
        """
        pass

    @abstractmethod
    def should_activate(self, text: str) -> bool:
        """Check if input should activate this plugin.

        Called by PluginManager to determine if this plugin should
        handle the given user input.

        Args:
            text: User's transcribed speech (lowercase).

        Returns:
            True if this plugin should activate and handle the input.
        """
        pass

    @abstractmethod
    async def handle_input(self, text: str) -> bool:
        """Handle user input when plugin is active.

        Process the user's input and generate appropriate responses.
        This method is called for all input while the plugin is active.

        Args:
            text: User's transcribed speech.

        Returns:
            True if input was handled, False to pass through to Ergos.
        """
        pass

    @abstractmethod
    async def deactivate(self) -> None:
        """Clean up when plugin deactivates.

        Called when the plugin is being deactivated, either by user
        request or programmatically. Should clean up any resources
        and reset internal state.
        """
        pass

    def attach(
        self,
        llm: "LLMGenerator",
        tts: "TTSProcessor",
        state_machine: "ConversationStateMachine",
        speak_callback: SpeakCallback,
    ) -> None:
        """Attach plugin to Ergos components.

        Called by PluginManager to provide access to Ergos subsystems.

        Args:
            llm: LLM generator for text generation.
            tts: TTS processor for speech synthesis.
            state_machine: Conversation state machine.
            speak_callback: Async function to speak text to user.
        """
        self._llm = llm
        self._tts = tts
        self._state_machine = state_machine
        self._speak = speak_callback

    @property
    def is_active(self) -> bool:
        """Whether this plugin is currently active.

        Returns:
            True if plugin is handling user interactions.
        """
        return self._is_active

    async def activate(self) -> None:
        """Activate the plugin.

        Called by PluginManager when plugin should start handling input.
        """
        self._is_active = True

    async def _speak_text(self, text: str) -> None:
        """Speak text to the user via TTS.

        Convenience method for subclasses to speak to the user.

        Args:
            text: Text to speak.
        """
        if self._speak is not None:
            await self._speak(text)
