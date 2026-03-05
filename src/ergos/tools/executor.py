"""Tool executor: dispatcher from tool name to implementation function.

Dispatches tool calls by name to built-in implementations and returns result
strings. All dispatch is async to support async built-in implementations.
"""

import logging
from typing import TYPE_CHECKING

from . import builtins

if TYPE_CHECKING:
    from .registry import ToolRegistry

logger = logging.getLogger(__name__)

# Built-in implementation dispatch table
_BUILTIN_DISPATCH = {
    "builtin.file_read": builtins.file_read,
    "builtin.shell_run": builtins.shell_run,
    "builtin.file_list": builtins.file_list,
}


class ToolExecutor:
    """Dispatcher from tool name -> implementation -> result string.

    Usage:
        executor = ToolExecutor(registry.get_impl_map(), registry)
        result = await executor.execute("file_read", {"path": "/tmp/foo.txt"})
    """

    def __init__(self, impl_map: dict[str, str], registry: "ToolRegistry") -> None:
        """Initialize executor with impl map and registry reference.

        Args:
            impl_map: Dict mapping tool name to impl string, e.g.
                      {"file_read": "builtin.file_read"}.
            registry: ToolRegistry instance for per-tool config lookup.
        """
        self._impl_map = impl_map
        self._registry = registry

    async def execute(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool by name with the given arguments.

        Dispatches to built-in implementations via the impl_map.
        For shell_run, injects allowed_prefixes from registry config.

        Args:
            tool_name: Name of the tool to execute (e.g., "file_read").
            arguments: Dict of arguments for the tool.

        Returns:
            Result string from the tool implementation.
            Returns "Error: unknown tool 'name'" for unknown tools.
        """
        impl_str = self._impl_map.get(tool_name)
        if impl_str is None:
            return f"Error: unknown tool '{tool_name}'"

        fn = _BUILTIN_DISPATCH.get(impl_str)
        if fn is None:
            return f"Error: no implementation found for '{impl_str}'"

        try:
            if tool_name == "shell_run" or impl_str == "builtin.shell_run":
                # Inject allowed_prefixes from registry config
                tool_config = self._registry.get_tool_config(tool_name)
                allowed_prefixes = tool_config.get("allowed_prefixes")
                return await fn(
                    **arguments,
                    allowed_prefixes=allowed_prefixes,
                )
            else:
                return await fn(**arguments)
        except Exception as e:
            logger.error("Error executing tool '%s': %s", tool_name, e, exc_info=True)
            return f"Error: tool execution failed: {e}"
