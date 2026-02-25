"""Plugin system for Ergos extensibility.

The plugin system allows extending Ergos with custom functionality
without modifying core code. Plugins can activate based on user input
and handle conversations until they deactivate.

Example usage:
    from ergos.plugins import PluginManager

    # Create manager and discover plugins
    manager = PluginManager()
    manager.discover_plugins()

    # Attach to Ergos components
    manager.attach_all(llm, tts, state_machine, speak_callback)

    # Route input through plugins
    plugin = manager.route_input(user_text)
    if plugin:
        handled = await plugin.handle_input(user_text)
"""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Callable, Awaitable, Optional, TYPE_CHECKING

from ergos.plugins.base import BasePlugin, SpeakCallback

if TYPE_CHECKING:
    from ergos.llm.generator import LLMGenerator
    from ergos.tts.processor import TTSProcessor
    from ergos.state import ConversationStateMachine

logger = logging.getLogger(__name__)

__all__ = [
    "BasePlugin",
    "SpeakCallback",
    "PluginManager",
]


class PluginManager:
    """Discovers and manages Ergos plugins.

    The PluginManager handles plugin lifecycle:
    - Discovery: Finds plugins in the plugins/ directory
    - Registration: Tracks available plugins
    - Routing: Determines which plugin should handle input
    - Activation: Manages the currently active plugin

    Only one plugin can be active at a time. When active, it receives
    all user input until it deactivates.
    """

    def __init__(self) -> None:
        """Initialize plugin manager with empty registry."""
        self._plugins: dict[str, BasePlugin] = {}
        self._active_plugin: Optional[BasePlugin] = None
        self._attached: bool = False

    @property
    def plugins(self) -> dict[str, BasePlugin]:
        """Get registered plugins.

        Returns:
            Dictionary mapping plugin names to plugin instances.
        """
        return dict(self._plugins)

    @property
    def active_plugin(self) -> Optional[BasePlugin]:
        """Get currently active plugin.

        Returns:
            Active plugin instance or None if no plugin is active.
        """
        return self._active_plugin

    def discover_plugins(self) -> None:
        """Auto-discover and register plugins in plugins/ directory.

        Scans the plugins directory for packages containing a class
        that extends BasePlugin. Each discovered plugin is instantiated
        and registered.
        """
        plugins_dir = Path(__file__).parent

        for finder, name, ispkg in pkgutil.iter_modules([str(plugins_dir)]):
            # Skip non-packages and the base module
            if not ispkg or name == "base":
                continue

            try:
                # Import the plugin package
                module = importlib.import_module(f"ergos.plugins.{name}")

                # Look for a plugin class (ending with 'Plugin' and extending BasePlugin)
                for attr_name in dir(module):
                    if attr_name.endswith("Plugin") and attr_name != "BasePlugin":
                        cls = getattr(module, attr_name)
                        if isinstance(cls, type) and issubclass(cls, BasePlugin):
                            plugin = cls()
                            self.register_plugin(plugin)
                            logger.info(f"Discovered plugin: {plugin.name}")
                            break

            except Exception as e:
                logger.error(f"Failed to load plugin '{name}': {e}")

    def register_plugin(self, plugin: BasePlugin) -> None:
        """Register a plugin instance.

        Args:
            plugin: Plugin instance to register.
        """
        if plugin.name in self._plugins:
            logger.warning(f"Plugin '{plugin.name}' already registered, replacing")
        self._plugins[plugin.name] = plugin

    def unregister_plugin(self, name: str) -> bool:
        """Unregister a plugin by name.

        Args:
            name: Name of the plugin to unregister.

        Returns:
            True if plugin was found and removed.
        """
        if name in self._plugins:
            del self._plugins[name]
            return True
        return False

    def attach_all(
        self,
        llm: "LLMGenerator",
        tts: "TTSProcessor",
        state_machine: "ConversationStateMachine",
        speak_callback: SpeakCallback,
    ) -> None:
        """Attach all plugins to Ergos components.

        Must be called before routing input to plugins.

        Args:
            llm: LLM generator for text generation.
            tts: TTS processor for speech synthesis.
            state_machine: Conversation state machine.
            speak_callback: Async function to speak text to user.
        """
        for plugin in self._plugins.values():
            plugin.attach(llm, tts, state_machine, speak_callback)
        self._attached = True
        logger.info(f"Attached {len(self._plugins)} plugins to Ergos components")

    def route_input(self, text: str) -> Optional[BasePlugin]:
        """Determine which plugin should handle input.

        If a plugin is already active, returns that plugin. Otherwise,
        checks each registered plugin to see if it should activate.

        Args:
            text: User's transcribed speech.

        Returns:
            Plugin that should handle input, or None for normal Ergos processing.
        """
        # If a plugin is already active, continue using it
        if self._active_plugin is not None and self._active_plugin.is_active:
            return self._active_plugin

        # Check each plugin for activation
        text_lower = text.lower()
        for plugin in self._plugins.values():
            if plugin.should_activate(text_lower):
                self._active_plugin = plugin
                return plugin

        return None

    async def deactivate_current(self) -> None:
        """Deactivate the currently active plugin."""
        if self._active_plugin is not None:
            await self._active_plugin.deactivate()
            logger.info(f"Deactivated plugin: {self._active_plugin.name}")
            self._active_plugin = None

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Get a plugin by name.

        Args:
            name: Plugin name.

        Returns:
            Plugin instance or None if not found.
        """
        return self._plugins.get(name)
