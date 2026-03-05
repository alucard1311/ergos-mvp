"""ToolCallProcessor: agentic loop with concurrent narration + tool execution.

Bridges LLM tool-calling (create_chat_completion), voice narration, and multi-step
chaining into a single processor that pipeline.py can wire.

Key design decisions (see RESEARCH.md):
- Pitfall 2: Tool result messages use role='tool' with tool_call_id (not role='user')
- Pitfall 3: Model lock held during create_chat_completion (no segfaults)
- Pitfall 6: Narration + execution run concurrently via asyncio.gather (no audible pause)
- Pitfall 7: Tool messages are ephemeral — only user+assistant go to LLM history
- Qwen3: /no_think appended to last user message to suppress chain-of-thought
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Callable

from .generator import LLMGenerator

if TYPE_CHECKING:
    from .processor import LLMProcessor, Message
    from ergos.tools.executor import ToolExecutor
    from ergos.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Map of tool name -> narration string spoken while tool executes
_TOOL_NARRATIONS: dict[str, str] = {
    "file_read": "Let me read that file.",
    "shell_run": "Let me run that command.",
    "file_list": "Let me check what files are there.",
}
_DEFAULT_NARRATION = "Let me check that..."


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
        # Build initial messages list: system + conversation history + new user message
        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt}
        ]

        # Add conversation history from llm_processor
        for msg in llm_processor._history[-llm_processor.max_history_messages:]:
            messages.append({"role": msg.role, "content": msg.content})

        # Add user message — append /no_think to suppress Qwen3 chain-of-thought
        # (Pitfall: Qwen3 only recognizes /no_think in the user turn, not system message)
        user_message = {"role": "user", "content": f"{user_text} /no_think"}
        messages.append(user_message)

        tools = self._registry.get_tools()
        loop = asyncio.get_event_loop()
        final_text = f"Reached step limit of {self._max_steps} steps without a final response."

        for step in range(self._max_steps):
            # create_chat_completion_sync is blocking — run in thread executor
            response = await loop.run_in_executor(
                None,
                lambda msgs=messages, t=tools: self._generator.create_chat_completion_sync(
                    messages=msgs,
                    tools=t,
                    max_tokens=512,
                ),
            )

            choice = response["choices"][0]
            finish_reason = choice["finish_reason"]
            message = choice["message"]

            if finish_reason != "tool_calls":
                # Model returned plain text — we're done
                final_text = message.get("content") or ""
                break

            # Model wants to call tools
            tool_calls = message.get("tool_calls") or []

            # Append the assistant's tool_calls message to local messages (ephemeral)
            messages.append({
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls,
            })

            # Process each tool call: narrate + execute concurrently (Pitfall 6)
            for tc in tool_calls:
                fn = tc["function"]
                tool_name = fn["name"]
                args = json.loads(fn["arguments"])
                tool_call_id = tc["id"]

                narration = self._narration_before(tool_name)

                # Concurrent: speak narration while tool executes
                # This avoids audible pause (Pitfall 6 from RESEARCH.md)
                _, result_str = await asyncio.gather(
                    speak(narration),
                    self._executor.execute(tool_name, args),
                )

                # Speak completion AFTER both narration and execution finish
                await speak("Done.")

                logger.debug(
                    "Tool '%s' result (step %d): %s",
                    tool_name,
                    step + 1,
                    result_str[:100] if len(result_str) > 100 else result_str,
                )

                # Append tool result to local messages (ephemeral — not in history)
                # Use role='tool' with tool_call_id (Pitfall 2: not role='user')
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_str,
                })

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
