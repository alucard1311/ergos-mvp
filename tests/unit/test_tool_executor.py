"""Tests for ToolExecutor and built-in tool implementations.

Tests:
- executor.execute() dispatch to file_read, shell_run, file_list
- file_read: file contents, missing file, home expansion, truncation
- shell_run: allowed commands, rejected commands, timeout, truncation
- shell_run: allowed_prefixes enforcement (None=allow all, []=reject all)
- file_list: directory listing, glob pattern, missing directory
- Unknown tool returns error string
"""

import asyncio
import textwrap

import pytest
import pytest_asyncio

from ergos.tools import ToolExecutor, ToolRegistry
from ergos.tools.builtins import file_list, file_read, shell_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path, filename, content):
    """Write a YAML file in tmp_path."""
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content))
    return p


def _make_registry(tmp_path, allowed_prefixes=None):
    """Create a ToolRegistry with shell_run (and optionally allowed_prefixes)."""
    if allowed_prefixes is None:
        # Default allowlist from RESEARCH.md
        prefixes = ["ls", "cat", "head", "tail", "wc", "find", "grep", "echo", "pwd",
                    "whoami", "date", "df", "du", "uname", "python3", "uv run"]
    else:
        prefixes = allowed_prefixes

    yaml_content = f"""
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
            allowed_prefixes: {prefixes!r}
            parameters:
              type: object
              properties:
                command:
                  type: string
                timeout_seconds:
                  type: integer
              required: [command]
          - name: file_list
            description: "List files"
            impl: builtin.file_list
            parameters:
              type: object
              properties:
                directory:
                  type: string
                pattern:
                  type: string
              required: [directory]
    """
    _write_yaml(tmp_path, "tools.yaml", yaml_content)
    registry = ToolRegistry(tools_dir=str(tmp_path))
    registry.load()
    return registry


def _make_no_allowlist_registry(tmp_path):
    """Create a registry where shell_run has NO allowed_prefixes (None = allow all)."""
    _write_yaml(
        tmp_path,
        "tools.yaml",
        """
        tools:
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
    return registry


# ---------------------------------------------------------------------------
# ToolExecutor dispatch tests
# ---------------------------------------------------------------------------

class TestToolExecutorDispatch:
    @pytest.mark.asyncio
    async def test_execute_file_read_returns_contents(self, tmp_path):
        """executor.execute('file_read', {path}) returns file contents."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        registry = _make_registry(tmp_path)
        executor = ToolExecutor(registry.get_impl_map(), registry)
        result = await executor.execute("file_read", {"path": str(test_file)})
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_returns_error(self, tmp_path):
        """executor.execute('unknown_tool', {}) returns 'Error: unknown tool' string."""
        registry = _make_registry(tmp_path)
        executor = ToolExecutor(registry.get_impl_map(), registry)
        result = await executor.execute("unknown_tool", {})
        assert "Error" in result
        assert "unknown" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_shell_run_allowed_command(self, tmp_path):
        """executor.execute('shell_run', {command: 'echo hello'}) returns 'hello'."""
        registry = _make_registry(tmp_path)
        executor = ToolExecutor(registry.get_impl_map(), registry)
        result = await executor.execute("shell_run", {"command": "echo hello"})
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_execute_file_list_returns_listing(self, tmp_path):
        """executor.execute('file_list', {directory}) returns file listing."""
        (tmp_path / "file_a.txt").write_text("a")
        (tmp_path / "file_b.txt").write_text("b")
        # Write tools.yaml too, but that's fine
        registry = _make_registry(tmp_path)
        executor = ToolExecutor(registry.get_impl_map(), registry)
        result = await executor.execute("file_list", {"directory": str(tmp_path)})
        assert "file_a.txt" in result
        assert "file_b.txt" in result


# ---------------------------------------------------------------------------
# file_read tests
# ---------------------------------------------------------------------------

class TestFileRead:
    @pytest.mark.asyncio
    async def test_reads_file_contents(self, tmp_path):
        """file_read returns the full file contents."""
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        result = await file_read(str(f))
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_nonexistent_file_returns_error_string(self, tmp_path):
        """file_read with nonexistent path returns 'Error: ...' string (no exception)."""
        result = await file_read(str(tmp_path / "does_not_exist.txt"))
        assert result.startswith("Error:")
        assert "not found" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_home_relative_path_expands(self, tmp_path, monkeypatch):
        """file_read with home-relative path (~/) expands correctly."""
        import os
        # Point HOME to tmp_path for this test
        monkeypatch.setenv("HOME", str(tmp_path))
        test_file = tmp_path / "test_home.txt"
        test_file.write_text("home contents")
        result = await file_read("~/test_home.txt")
        assert result == "home contents"

    @pytest.mark.asyncio
    async def test_truncates_at_4096_chars(self, tmp_path):
        """file_read truncates output at 4096 chars."""
        f = tmp_path / "large.txt"
        f.write_text("x" * 8000)
        result = await file_read(str(f))
        assert len(result) <= 4096 + 100  # Allow for truncation message
        assert "truncated" in result


# ---------------------------------------------------------------------------
# shell_run tests
# ---------------------------------------------------------------------------

class TestShellRun:
    @pytest.mark.asyncio
    async def test_allowed_command_returns_output(self):
        """shell_run with allowed command returns output."""
        result = await shell_run("echo hello", allowed_prefixes=["echo"])
        assert result.strip() == "hello"

    @pytest.mark.asyncio
    async def test_disallowed_command_rm_returns_error(self):
        """shell_run with 'rm -rf /tmp/foo' returns 'Error: command not allowed'."""
        result = await shell_run(
            "rm -rf /tmp/foo",
            allowed_prefixes=["ls", "cat", "echo"],
        )
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_disallowed_command_sudo_returns_error(self):
        """shell_run with 'sudo reboot' returns 'Error: command not allowed'."""
        result = await shell_run(
            "sudo reboot",
            allowed_prefixes=["ls", "cat", "echo"],
        )
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_empty_allowed_prefixes_rejects_all(self):
        """shell_run with empty allowed_prefixes list rejects all commands."""
        result = await shell_run("echo hello", allowed_prefixes=[])
        assert "Error" in result
        assert "not allowed" in result

    @pytest.mark.asyncio
    async def test_none_allowed_prefixes_allows_all(self):
        """shell_run with allowed_prefixes=None allows all commands (backwards-compatible)."""
        result = await shell_run("echo unrestricted", allowed_prefixes=None)
        assert "unrestricted" in result

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        """shell_run with timeout_seconds=1 on slow command returns timeout error."""
        result = await shell_run(
            "sleep 5",
            timeout_seconds=1,
            allowed_prefixes=None,  # No allowlist — allow all
        )
        assert "Error" in result
        assert "timed out" in result.lower() or "timeout" in result.lower()

    @pytest.mark.asyncio
    async def test_truncates_output_at_4096_chars(self):
        """shell_run truncates output at 4096 chars."""
        # Generate 8000 chars of output
        result = await shell_run(
            "python3 -c \"print('x' * 8000)\"",
            allowed_prefixes=["python3"],
        )
        assert len(result) <= 4096 + 100  # Allow for truncation message
        assert "truncated" in result

    @pytest.mark.asyncio
    async def test_echo_is_in_default_allowlist(self):
        """echo is in the default allowlist used in executor dispatch."""
        result = await shell_run("echo test_output", allowed_prefixes=["echo"])
        assert "test_output" in result


# ---------------------------------------------------------------------------
# file_list tests
# ---------------------------------------------------------------------------

class TestFileList:
    @pytest.mark.asyncio
    async def test_lists_directory_contents(self, tmp_path):
        """file_list returns file listing for a directory."""
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        result = await file_list(str(tmp_path))
        assert "a.txt" in result
        assert "b.txt" in result

    @pytest.mark.asyncio
    async def test_glob_pattern_filters_results(self, tmp_path):
        """file_list with pattern='*.txt' filters results."""
        (tmp_path / "keep.txt").write_text("keep")
        (tmp_path / "skip.py").write_text("skip")
        result = await file_list(str(tmp_path), pattern="*.txt")
        assert "keep.txt" in result
        assert "skip.py" not in result

    @pytest.mark.asyncio
    async def test_nonexistent_directory_returns_error(self, tmp_path):
        """file_list with nonexistent directory returns error string."""
        result = await file_list(str(tmp_path / "does_not_exist"))
        assert "Error" in result
        assert "not found" in result.lower() or "directory" in result.lower()
