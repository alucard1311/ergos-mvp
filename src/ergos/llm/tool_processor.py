"""ToolCallProcessor: agentic loop with concurrent narration + tool execution.

Bridges LLM tool-calling, voice narration, and multi-step chaining into a single
processor that pipeline.py can wire.

Key design decisions (see RESEARCH.md):
- Qwen3 native tool calling: tools injected into system prompt as <tools> block,
  responses parsed from <tool_call> tags (llama-cpp-python's chatml format doesn't
  handle structured tool calling)
- Pitfall 3: Model lock held during create_chat_completion (no segfaults)
- Pitfall 6: Narration + execution run concurrently via asyncio.gather (no audible pause)
- Pitfall 7: Tool messages are ephemeral — only user+assistant go to LLM history
- Qwen3: /no_think appended to last user message to suppress chain-of-thought
"""

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Callable

from .generator import LLMGenerator

if TYPE_CHECKING:
    from .processor import LLMProcessor, Message
    from ergos.tools.executor import ToolExecutor
    from ergos.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Regex to extract <tool_call>...</tool_call> blocks from Qwen3 responses
_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)

# Map of tool name -> narration string spoken while tool executes.
# Each string MUST have >= 20 alphanumeric chars to avoid garbled Orpheus output
# (short fragments produce noise — see TTS _MIN_SPEAKABLE_CHARS).
_TOOL_NARRATIONS: dict[str, str] = {
    "file_read": "Let me take a look at that file for you.",
    "shell_run": "Let me run that command for you real quick.",
    "file_list": "Let me check what files are in there for you.",
}
_DEFAULT_NARRATION = "Let me take a look at that for you."


class ToolCallProcessor:
    """Agentic loop processor: LLM calls tools, narrates aloud, chains steps.

    Usage:
        processor = ToolCallProcessor(generator, registry, executor, system_prompt)
        result = await processor.process(user_text, speak_callback, llm_processor)
    """

    def __init__(
        self,
        generator: "LLMGenerator",
        registry: "ToolRegistry",
        executor: "ToolExecutor",
        system_prompt: str,
        max_steps: int = 8,
    ) -> None:
        """Initialize ToolCallProcessor.

        Args:
            generator: LLMGenerator instance (provides create_chat_completion_sync).
            registry: ToolRegistry instance (provides get_tools()).
            executor: ToolExecutor instance (provides execute(name, args)).
            system_prompt: System prompt string (same as LLMProcessor uses).
            max_steps: Maximum agentic loop steps before forcing termination (default 8).
        """
        self._generator = generator
        self._registry = registry
        self._executor = executor
        self._system_prompt = system_prompt
        self._max_steps = max_steps

    @property
    def has_tools(self) -> bool:
        """True if any tools are registered."""
        return self._registry.has_tools

    def _format_tools_for_prompt(self) -> str:
        """Format tool definitions in Qwen3's native <tools> XML format.

        llama-cpp-python's chatml chat format doesn't inject tools into the prompt,
        so we do it manually using the format Qwen3 was trained on.

        Returns:
            Tool definitions string to append to system prompt.
        """
        tools = self._registry.get_tools()
        if not tools:
            return ""

        tool_defs = "\n".join(json.dumps(t, separators=(",", ":")) for t in tools)
        return (
            "\n\n# Tools\n\n"
            "You are provided with function signatures within <tools></tools> XML tags:\n"
            f"<tools>\n{tool_defs}\n</tools>\n\n"
            "For each function call, return a JSON object with function name and arguments "
            "within <tool_call></tool_call> XML tags:\n"
            "<tool_call>\n"
            '{"name": "<function-name>", "arguments": <args-json-object>}\n'
            "</tool_call>"
        )

    def _parse_tool_calls(self, content: str) -> list[dict]:
        """Parse <tool_call> blocks from Qwen3 response content.

        Args:
            content: Raw response content from the model.

        Returns:
            List of parsed tool call dicts with 'name' and 'arguments' keys.
            Empty list if no tool calls found.
        """
        results = []
        for match in _TOOL_CALL_RE.finditer(content):
            try:
                tc = json.loads(match.group(1))
                if "name" in tc:
                    results.append(tc)
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse tool_call JSON: %s", e)
        return results

    def _narration_before(self, tool_name: str) -> str:
        """Return spoken narration for a tool call (before execution).

        Args:
            tool_name: Name of the tool being called.

        Returns:
            Human-readable narration string.
        """
        return _TOOL_NARRATIONS.get(tool_name, _DEFAULT_NARRATION)

    async def process(
        self,
        user_text: str,
        speak: Callable,
        llm_processor: "LLMProcessor",
    ) -> str:
        """Execute the agentic loop for a user request.

        Builds a messages list from history, calls the LLM with tools, executes
        tool calls concurrently with narration, and chains until the model returns
        a plain text response (or max_steps reached).

        History isolation: tool messages are ephemeral. Only the original user
        message and final assistant response are appended to llm_processor._history.

        Args:
            user_text: The user's transcribed speech.
            speak: Async callback to speak text aloud (async def speak(text: str)).
            llm_processor: LLMProcessor instance for history and system prompt access.

        Returns:
            Final assistant response text.
        """
        # Build initial messages list: system (with tools) + conversation history + user
        # Inject tool definitions into system prompt using Qwen3's native format
        # (llama-cpp-python's chatml format doesn't handle structured tool calling)
        system_content = self._system_prompt + self._format_tools_for_prompt()
        messages: list[dict] = [
            {"role": "system", "content": system_content}
        ]

        # Add conversation history from llm_processor
        for msg in llm_processor._history[-llm_processor.max_history_messages:]:
            messages.append({"role": msg.role, "content": msg.content})

        # Add user message — append /no_think to suppress Qwen3 chain-of-thought
        # (Pitfall: Qwen3 only recognizes /no_think in the user turn, not system message)
        user_message = {"role": "user", "content": f"{user_text} /no_think"}
        messages.append(user_message)

        loop = asyncio.get_event_loop()
        final_text = f"Reached step limit of {self._max_steps} steps without a final response."

        for step in range(self._max_steps):
            # create_chat_completion_sync is blocking — run in thread executor
            # Don't pass tools/tool_choice — chatml ignores them; we use native format
            response = await loop.run_in_executor(
                None,
                lambda msgs=messages: self._generator.create_chat_completion_sync(
                    messages=msgs,
                    max_tokens=512,
                ),
            )

            choice = response["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""

            # Parse Qwen3 native <tool_call> blocks from response content
            parsed_tool_calls = self._parse_tool_calls(content)

            if not parsed_tool_calls:
                # No tool calls — plain text response, we're done
                final_text = content
                break

            logger.info("Step %d: %d tool call(s) detected", step + 1, len(parsed_tool_calls))

            # Append the assistant's message to local messages (ephemeral)
            messages.append({"role": "assistant", "content": content})

            # Process each tool call: narrate + execute concurrently (Pitfall 6)
            tool_results = []
            for tc in parsed_tool_calls:
                tool_name = tc["name"]
                args = tc.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)

                narration = self._narration_before(tool_name)

                # Concurrent: speak narration while tool executes
                # This avoids audible pause (Pitfall 6 from RESEARCH.md)
                _, result_str = await asyncio.gather(
                    speak(narration),
                    self._executor.execute(tool_name, args),
                )

                # No completion narration — "Done." is too short for Orpheus
                # (produces garbled audio and triggers false barge-in from echo)

                logger.info(
                    "Tool '%s' result (step %d): %s",
                    tool_name,
                    step + 1,
                    result_str[:100] if len(result_str) > 100 else result_str,
                )

                tool_results.append({"name": tool_name, "result": result_str})

            # Append tool results as user message with clear formatting
            # (Qwen3 native format: tool results go in a user turn, not role=tool)
            results_text = "\n".join(
                f"<tool_response>\n{json.dumps({'name': r['name'], 'content': r['result']})}\n</tool_response>"
                for r in tool_results
            )
            messages.append({"role": "user", "content": results_text})

        # History isolation (Pitfall 7): only user + final assistant go to _history
        # This ensures tool messages never pollute conversation history
        from .processor import Message
        llm_processor._history.append(
            Message(role="user", content=user_text)
        )
        llm_processor._history.append(
            Message(role="assistant", content=final_text)
        )
        llm_processor._trim_history()

        return final_text
