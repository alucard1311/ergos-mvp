"""Built-in tool implementations for agentic execution.

Provides:
- file_read: Read a file and return its contents (truncated to 4096 chars)
- shell_run: Execute a shell command with timeout and allowlist enforcement
- file_list: List directory contents with optional glob pattern

All functions are async and return result strings (never raise exceptions
to callers — errors are returned as "Error: ..." strings).
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_OUTPUT_CHARS = 4096
_MAX_TIMEOUT_SECONDS = 30


async def file_read(path: str) -> str:
    """Read the contents of a file at the given path.

    Expands ~ in path. Truncates output to 4096 characters.

    Args:
        path: Absolute or home-relative file path.

    Returns:
        File contents as string, or "Error: ..." string on failure.
    """
    expanded = Path(path).expanduser()
    try:
        content = expanded.read_text(encoding="utf-8", errors="replace")
        if len(content) > _MAX_OUTPUT_CHARS:
            content = content[:_MAX_OUTPUT_CHARS] + f"\n[... truncated at {_MAX_OUTPUT_CHARS} chars]"
        return content
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except PermissionError:
        return f"Error: permission denied reading file: {path}"
    except Exception as e:
        return f"Error: could not read file {path}: {e}"


async def shell_run(
    command: str,
    timeout_seconds: int = 10,
    allowed_prefixes: list[str] | None = None,
) -> str:
    """Run a shell command and return stdout+stderr.

    Security: If allowed_prefixes is provided (even empty list), the command
    must start with one of the allowed prefixes. If None, all commands are
    allowed (backwards-compatible for user-defined tools).

    Args:
        command: Shell command to execute.
        timeout_seconds: Max seconds to wait (default 10, capped at 30).
        allowed_prefixes: List of allowed command prefixes. None = allow all.
                          Empty list = reject all commands.

    Returns:
        Command output (stdout+stderr) as string, or "Error: ..." on failure.
    """
    # Validate against allowlist if provided
    if allowed_prefixes is not None:
        stripped = command.lstrip()
        allowed = any(stripped.startswith(prefix) for prefix in allowed_prefixes)
        if not allowed:
            prefixes_str = ", ".join(allowed_prefixes) if allowed_prefixes else "(none)"
            logger.warning(
                "Rejected shell command (not in allowlist): %r. Permitted prefixes: %s",
                command,
                prefixes_str,
            )
            return f"Error: command not allowed. Permitted prefixes: {prefixes_str}"

    # Cap timeout
    timeout_seconds = min(timeout_seconds, _MAX_TIMEOUT_SECONDS)

    logger.info("Executing shell command: %r (timeout=%ds)", command, timeout_seconds)

    try:
        proc = await asyncio.create_subprocess_exec(
            "/bin/sh",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(timeout_seconds),
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()  # Clean up
            logger.warning("Shell command timed out after %ds: %r", timeout_seconds, command)
            return f"Error: command timed out after {timeout_seconds}s"

        output = (stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")).strip()
        logger.info(
            "Shell command completed: %r -> %d chars output",
            command,
            len(output),
        )

        if len(output) > _MAX_OUTPUT_CHARS:
            output = output[:_MAX_OUTPUT_CHARS] + f"\n[... truncated at {_MAX_OUTPUT_CHARS} chars]"

        return output

    except Exception as e:
        logger.error("Shell command failed: %r -> %s", command, e)
        return f"Error: {e}"


async def file_list(directory: str, pattern: str = "*") -> str:
    """List files in a directory matching an optional glob pattern.

    Args:
        directory: Directory to list (supports ~ expansion).
        pattern: Optional glob pattern, e.g. '*.py'. Default is '*' (all files).

    Returns:
        Newline-joined list of file names, or "Error: ..." on failure.
    """
    expanded = Path(directory).expanduser()
    try:
        if not expanded.exists():
            return f"Error: directory not found: {directory}"
        if not expanded.is_dir():
            return f"Error: not a directory: {directory}"

        matches = sorted(expanded.glob(pattern))
        if not matches:
            return f"(no files matching '{pattern}' in {directory})"

        lines = [str(p.name) for p in matches]
        result = "\n".join(lines)

        if len(result) > _MAX_OUTPUT_CHARS:
            result = result[:_MAX_OUTPUT_CHARS] + f"\n[... truncated at {_MAX_OUTPUT_CHARS} chars]"

        return result

    except PermissionError:
        return f"Error: permission denied listing directory: {directory}"
    except Exception as e:
        return f"Error: could not list directory {directory}: {e}"
