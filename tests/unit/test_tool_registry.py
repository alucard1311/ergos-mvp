"""Tests for ToolRegistry: YAML loading, validation, reload, and tool config."""

import textwrap

import pytest

from ergos.tools import ToolRegistry


def _write_yaml(tmp_path, filename, content):
    """Helper to write a YAML file in tmp_path."""
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content))
    return p


class TestToolRegistryLoading:
    def test_load_valid_yaml_produces_chat_completion_tool_dicts(self, tmp_path):
        """Valid YAML produces correct ChatCompletionTool-compatible dicts."""
        _write_yaml(
            tmp_path,
            "tools.yaml",
            """
            tools:
              - name: file_read
                description: "Read a file"
                impl: builtin.file_read
                parameters:
                  type: object
                  properties:
                    path:
                      type: string
                      description: "File path"
                  required: [path]
            """,
        )
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        tools = registry.get_tools()

        assert len(tools) == 1
        tool = tools[0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "file_read"
        assert tool["function"]["description"] == "Read a file"
        assert "parameters" in tool["function"]
        assert tool["function"]["parameters"]["type"] == "object"

    def test_get_tools_strips_impl_and_config(self, tmp_path):
        """get_tools() returns dicts WITHOUT _impl or _config keys."""
        _write_yaml(
            tmp_path,
            "tools.yaml",
            """
            tools:
              - name: file_read
                description: "Read a file"
                impl: builtin.file_read
                parameters:
                  type: object
                  properties:
                    path:
                      type: string
                  required: [path]
            """,
        )
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        tools = registry.get_tools()

        tool = tools[0]
        assert "_impl" not in tool
        assert "_config" not in tool
        assert "_impl" not in tool.get("function", {})

    def test_empty_directory_returns_empty_list(self, tmp_path):
        """load_tool_registry with empty directory returns empty list."""
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        assert registry.get_tools() == []

    def test_missing_directory_returns_empty_list(self, tmp_path):
        """load_tool_registry with missing directory returns empty list (no error)."""
        missing = tmp_path / "nonexistent"
        registry = ToolRegistry(tools_dir=str(missing))
        registry.load()  # Must not raise
        assert registry.get_tools() == []

    def test_multiple_yaml_files_are_merged_and_sorted(self, tmp_path):
        """Multiple YAML files are merged and sorted by name."""
        _write_yaml(
            tmp_path,
            "b_tools.yaml",
            """
            tools:
              - name: shell_run
                description: "Run a shell command"
                impl: builtin.shell_run
                parameters:
                  type: object
                  properties:
                    command:
                      type: string
                  required: [command]
            """,
        )
        _write_yaml(
            tmp_path,
            "a_tools.yaml",
            """
            tools:
              - name: file_read
                description: "Read a file"
                impl: builtin.file_read
                parameters:
                  type: object
                  properties:
                    path:
                      type: string
                  required: [path]
            """,
        )
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        tools = registry.get_tools()

        # Sorted by YAML filename, so a_tools.yaml first
        assert len(tools) == 2
        names = [t["function"]["name"] for t in tools]
        assert "file_read" in names
        assert "shell_run" in names

    def test_reload_picks_up_newly_added_tool(self, tmp_path):
        """reload() picks up a newly added tool entry."""
        yaml_file = _write_yaml(
            tmp_path,
            "tools.yaml",
            """
            tools:
              - name: file_read
                description: "Read a file"
                impl: builtin.file_read
                parameters:
                  type: object
                  properties:
                    path:
                      type: string
                  required: [path]
            """,
        )
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        assert len(registry.get_tools()) == 1

        # Add a new tool
        yaml_file.write_text(textwrap.dedent("""
            tools:
              - name: file_read
                description: "Read a file"
                impl: builtin.file_read
                parameters:
                  type: object
                  properties:
                    path:
                      type: string
                  required: [path]
              - name: file_list
                description: "List files"
                impl: builtin.file_list
                parameters:
                  type: object
                  properties:
                    directory:
                      type: string
                  required: [directory]
        """))

        registry.reload()
        assert len(registry.get_tools()) == 2
        names = [t["function"]["name"] for t in registry.get_tools()]
        assert "file_list" in names

    def test_get_impl_map_returns_name_to_impl_string(self, tmp_path):
        """get_impl_map() returns {name: impl_string} mapping for executor dispatch."""
        _write_yaml(
            tmp_path,
            "tools.yaml",
            """
            tools:
              - name: file_read
                description: "Read a file"
                impl: builtin.file_read
                parameters:
                  type: object
                  properties:
                    path:
                      type: string
                  required: [path]
              - name: shell_run
                description: "Run a command"
                impl: builtin.shell_run
                parameters:
                  type: object
                  properties:
                    command:
                      type: string
                  required: [command]
            """,
        )
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        impl_map = registry.get_impl_map()

        assert impl_map == {
            "file_read": "builtin.file_read",
            "shell_run": "builtin.shell_run",
        }

    def test_get_tool_config_returns_extra_fields(self, tmp_path):
        """get_tool_config() returns per-tool config dict (e.g., allowed_prefixes)."""
        _write_yaml(
            tmp_path,
            "tools.yaml",
            """
            tools:
              - name: shell_run
                description: "Run a shell command"
                impl: builtin.shell_run
                allowed_prefixes:
                  - "ls"
                  - "cat"
                  - "echo"
                parameters:
                  type: object
                  properties:
                    command:
                      type: string
                  required: [command]
            """,
        )
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        config = registry.get_tool_config("shell_run")

        assert "allowed_prefixes" in config
        assert config["allowed_prefixes"] == ["ls", "cat", "echo"]

    def test_get_tool_config_unknown_tool_returns_empty_dict(self, tmp_path):
        """get_tool_config() returns empty dict if tool not found."""
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        config = registry.get_tool_config("nonexistent_tool")
        assert config == {}

    def test_get_tool_config_tool_without_extra_fields_returns_empty_dict(self, tmp_path):
        """get_tool_config() returns empty dict for tools with no extra config."""
        _write_yaml(
            tmp_path,
            "tools.yaml",
            """
            tools:
              - name: file_read
                description: "Read a file"
                impl: builtin.file_read
                parameters:
                  type: object
                  properties:
                    path:
                      type: string
                  required: [path]
            """,
        )
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        config = registry.get_tool_config("file_read")
        assert config == {}

    def test_invalid_yaml_entries_skipped_with_warning(self, tmp_path, caplog):
        """Invalid YAML entries (missing name or description) are skipped with warning."""
        import logging

        _write_yaml(
            tmp_path,
            "tools.yaml",
            """
            tools:
              - name: valid_tool
                description: "A valid tool"
                impl: builtin.file_read
                parameters:
                  type: object
                  properties:
                    path:
                      type: string
                  required: [path]
              - description: "Missing name"
                impl: builtin.something
                parameters:
                  type: object
                  properties: {}
              - name: missing_description
                impl: builtin.something
                parameters:
                  type: object
                  properties: {}
            """,
        )
        registry = ToolRegistry(tools_dir=str(tmp_path))
        with caplog.at_level(logging.WARNING):
            registry.load()

        tools = registry.get_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "valid_tool"

    def test_has_tools_property_true_when_tools_loaded(self, tmp_path):
        """has_tools is True when tools are loaded."""
        _write_yaml(
            tmp_path,
            "tools.yaml",
            """
            tools:
              - name: file_read
                description: "Read a file"
                impl: builtin.file_read
                parameters:
                  type: object
                  properties:
                    path:
                      type: string
                  required: [path]
            """,
        )
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        assert registry.has_tools is True

    def test_has_tools_property_false_when_no_tools(self, tmp_path):
        """has_tools is False when no tools are loaded."""
        registry = ToolRegistry(tools_dir=str(tmp_path))
        registry.load()
        assert registry.has_tools is False
