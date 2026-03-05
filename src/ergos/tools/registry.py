"""YAML tool registry loader -> ChatCompletionTool list.

Loads tool definitions from YAML files in a directory and provides them in
OpenAI-compatible ChatCompletionTool format for use with create_chat_completion.

Known YAML schema fields: name, description, parameters, impl.
Any additional top-level fields (e.g., allowed_prefixes) are stored as per-tool
config in _config, making the registry generic without code changes.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Fields that are part of the ChatCompletionTool schema
_SCHEMA_FIELDS = {"name", "description", "parameters", "impl"}


class ToolRegistry:
    """YAML registry loader that produces ChatCompletionTool-compatible dicts.

    Tool YAML files are scanned from tools_dir at load/reload time.
    Each file may contain a list under the 'tools' key.

    Usage:
        registry = ToolRegistry("~/.ergos/tools")
        registry.load()

        tools = registry.get_tools()          # Pass to create_chat_completion(tools=...)
        impl_map = registry.get_impl_map()    # Pass to ToolExecutor
        config = registry.get_tool_config("shell_run")  # e.g., allowed_prefixes
    """

    def __init__(self, tools_dir: str = "~/.ergos/tools") -> None:
        """Initialize registry with path to YAML tool directory.

        Args:
            tools_dir: Directory containing *.yaml tool definition files.
                       Supports ~ expansion. Directory may not exist yet.
        """
        self._tools_dir = Path(tools_dir).expanduser()
        # Internal storage: list of dicts with full fields including _impl/_config
        self._entries: list[dict] = []

    def load(self) -> None:
        """Scan tools_dir/*.yaml and load tool definitions.

        Validates each entry has name, description, parameters, impl.
        Skips invalid entries with a WARNING log.
        Any extra top-level fields are stored in _config for per-tool use.
        """
        self._entries = []

        if not self._tools_dir.exists():
            logger.debug("Tool registry directory does not exist: %s", self._tools_dir)
            return

        yaml_files = sorted(self._tools_dir.glob("*.yaml"))
        if not yaml_files:
            logger.debug("No YAML files found in tool registry: %s", self._tools_dir)
            return

        for yaml_file in yaml_files:
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Failed to parse YAML tool file %s: %s", yaml_file, e)
                continue

            for entry in data.get("tools", []):
                validated = self._validate_entry(entry, yaml_file)
                if validated is not None:
                    self._entries.append(validated)

        logger.info(
            "Loaded %d tools from %d YAML file(s) in %s",
            len(self._entries),
            len(yaml_files),
            self._tools_dir,
        )

    def reload(self) -> None:
        """Reload tool definitions from disk (alias for load()).

        Satisfies AGENT-04 hot-reload path: call reload() after adding new
        YAML files to make new tools available without server restart.
        """
        self.load()

    def get_tools(self) -> list[dict]:
        """Return ChatCompletionTool-compatible dicts for use with LLM.

        Strips _impl and _config from the returned dicts — these are
        registry-internal fields not accepted by create_chat_completion.

        Returns:
            List of dicts in ChatCompletionTool format:
            [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]
        """
        result = []
        for entry in self._entries:
            tool = {
                "type": "function",
                "function": {
                    "name": entry["name"],
                    "description": entry["description"],
                    "parameters": entry["parameters"],
                },
            }
            result.append(tool)
        return result

    def get_impl_map(self) -> dict[str, str]:
        """Return {tool_name: impl_string} mapping for executor dispatch.

        Returns:
            Dict mapping tool name to implementation string, e.g.
            {"file_read": "builtin.file_read", "shell_run": "builtin.shell_run"}
        """
        return {entry["name"]: entry["_impl"] for entry in self._entries}

    def get_tool_config(self, tool_name: str) -> dict:
        """Return per-tool config dict for the named tool.

        Returns extra fields beyond name/description/parameters/impl.
        For shell_run, this includes allowed_prefixes.
        Returns empty dict if tool not found or has no extra config.

        Args:
            tool_name: Name of the tool to look up.

        Returns:
            Dict of extra config fields, e.g. {"allowed_prefixes": ["ls", "cat"]}.
            Empty dict if tool not found or has no extra config.
        """
        for entry in self._entries:
            if entry["name"] == tool_name:
                return dict(entry.get("_config", {}))
        return {}

    @property
    def has_tools(self) -> bool:
        """True if any tools are loaded."""
        return len(self._entries) > 0

    def _validate_entry(self, entry: dict, source_file: Path) -> dict | None:
        """Validate a tool entry and return normalized internal dict or None.

        Required fields: name, description, parameters, impl.
        Extra fields are stored in _config.

        Args:
            entry: Raw dict from YAML.
            source_file: Source YAML file path (for logging).

        Returns:
            Normalized entry dict with _impl and _config, or None if invalid.
        """
        if not isinstance(entry, dict):
            logger.warning(
                "Skipping non-dict tool entry in %s: %r", source_file, entry
            )
            return None

        # Validate required fields
        for field in ("name", "description", "parameters"):
            if not entry.get(field):
                logger.warning(
                    "Skipping tool entry in %s: missing required field '%s'. Entry: %r",
                    source_file,
                    field,
                    entry,
                )
                return None

        if not entry.get("impl"):
            logger.warning(
                "Skipping tool '%s' in %s: missing 'impl' field",
                entry.get("name", "?"),
                source_file,
            )
            return None

        # Build normalized entry: known fields + _impl + _config for extras
        extra_config = {
            k: v for k, v in entry.items() if k not in _SCHEMA_FIELDS
        }

        return {
            "name": entry["name"],
            "description": entry["description"],
            "parameters": entry["parameters"],
            "_impl": entry["impl"],
            "_config": extra_config,
        }
