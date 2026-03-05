"""Tests for ToolCallProcessor: agentic loop, concurrent narration, multi-step, history isolation.

Tests use Qwen3 native tool calling format: <tool_call> tags in response content
instead of structured tool_calls (llama-cpp-python chatml doesn't support structured
tool calling).
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Helpers: mock response builders (Qwen3 native format)
# ---------------------------------------------------------------------------

def _make_tool_call_response(tool_name: str, arguments: dict) -> dict:
    """Build a create_chat_completion response with <tool_call> in content."""
    args_json = json.dumps(arguments)
    content = f'<tool_call>\n{{"name": "{tool_name}", "arguments": {args_json}}}\n</tool_call>'
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                },
            }
        ]
    }


def _make_text_response(text: str) -> dict:
    """Build a create_chat_completion response with plain text content."""
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": text,
                },
            }
        ]
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_registry():
    """Mock ToolRegistry with file_read tool."""
    registry = MagicMock()
    registry.has_tools = True
    registry.get_tools.return_value = [
        {
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]
    return registry


@pytest.fixture
def mock_executor():
    """Mock ToolExecutor that returns a canned result."""
    executor = MagicMock()
    executor.execute = AsyncMock(return_value="file contents here")
    return executor


@pytest.fixture
def mock_generator():
    """Mock LLMGenerator with create_chat_completion_sync as a regular Mock."""
    generator = MagicMock()
    generator.create_chat_completion_sync = MagicMock()
    return generator


@pytest.fixture
def mock_llm_processor(mock_generator):
    """Real-ish LLMProcessor backed by a mock generator for history isolation tests."""
    from ergos.llm import LLMProcessor
    processor = LLMProcessor(generator=mock_generator, system_prompt="You are a test assistant.")
    return processor


@pytest.fixture
def processor(mock_generator, mock_registry, mock_executor):
    """ToolCallProcessor with mock dependencies."""
    from ergos.llm.tool_processor import ToolCallProcessor
    return ToolCallProcessor(
        generator=mock_generator,
        registry=mock_registry,
        executor=mock_executor,
        system_prompt="You are a test assistant.",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSingleToolCall:
    @pytest.mark.asyncio
    async def test_single_tool_call_executes_tool_and_returns_text(
        self, processor, mock_generator, mock_executor, mock_llm_processor
    ):
        """Single tool call: step 1 has <tool_call>, step 2 returns plain text."""
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response("file_read", {"path": "/tmp/test.txt"}),
            _make_text_response("The file contains: file contents here"),
        ]

        speak = AsyncMock()
        result = await processor.process("Read /tmp/test.txt", speak, mock_llm_processor)

        assert result == "The file contains: file contents here"
        mock_executor.execute.assert_called_once_with("file_read", {"path": "/tmp/test.txt"})

    @pytest.mark.asyncio
    async def test_text_only_response_skips_tool_execution(
        self, processor, mock_generator, mock_executor, mock_llm_processor
    ):
        """When response has no <tool_call>, no tools are executed."""
        mock_generator.create_chat_completion_sync.return_value = _make_text_response("Hello world")

        speak = AsyncMock()
        result = await processor.process("Hello", speak, mock_llm_processor)

        assert result == "Hello world"
        mock_executor.execute.assert_not_called()


class TestConcurrentNarrationAndExecution:
    @pytest.mark.asyncio
    async def test_narration_and_execution_run_concurrently(
        self, processor, mock_generator, mock_llm_processor
    ):
        """speak and executor.execute must start concurrently (not sequentially)."""
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response("file_read", {"path": "/tmp/test.txt"}),
            _make_text_response("Done reading"),
        ]

        speak_start_time: list[float] = []
        execute_start_time: list[float] = []
        EXECUTION_DELAY = 0.1  # 100ms delay for executor to simulate real work

        async def slow_speak(text: str):
            if text == "Let me read that file.":
                speak_start_time.append(time.monotonic())
                await asyncio.sleep(EXECUTION_DELAY * 1.5)  # speak is slower

        async def slow_execute(tool_name: str, arguments: dict) -> str:
            execute_start_time.append(time.monotonic())
            await asyncio.sleep(EXECUTION_DELAY)
            return "contents"

        processor._executor = MagicMock()
        processor._executor.execute = slow_execute

        await processor.process("Read file", slow_speak, mock_llm_processor)

        # Both must have started
        assert len(speak_start_time) == 1
        assert len(execute_start_time) == 1

        # Start times must be close (concurrent), not sequential
        time_diff = abs(execute_start_time[0] - speak_start_time[0])
        assert time_diff < EXECUTION_DELAY * 0.8, (
            f"speak and execute were NOT concurrent: time_diff={time_diff:.3f}s "
            f"(expected < {EXECUTION_DELAY * 0.8:.3f}s)"
        )


class TestDoneSpokenAfterToolResult:
    @pytest.mark.asyncio
    async def test_done_spoken_after_tool_completes(
        self, processor, mock_generator, mock_llm_processor
    ):
        """'Done.' must be spoken AFTER asyncio.gather(speak, execute) completes."""
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response("file_read", {"path": "/tmp/test.txt"}),
            _make_text_response("All done"),
        ]

        speak_calls: list[str] = []

        async def record_speak(text: str):
            speak_calls.append(text)

        await processor.process("test", record_speak, mock_llm_processor)

        assert "Done." in speak_calls, f"'Done.' never spoken. Speak calls: {speak_calls}"
        done_idx = speak_calls.index("Done.")
        assert done_idx > 0, f"'Done.' was the very first speak call — should come after narration. Calls: {speak_calls}"


class TestMultiStepChain:
    @pytest.mark.asyncio
    async def test_two_step_chain_executes_both_tools(
        self, processor, mock_generator, mock_executor, mock_llm_processor
    ):
        """Multi-step: tool calls on step 1 and 2, text on step 3."""
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response("file_read", {"path": "/a.txt"}),
            _make_tool_call_response("file_read", {"path": "/b.txt"}),
            _make_text_response("Files processed"),
        ]

        speak = AsyncMock()
        result = await processor.process("Process both files", speak, mock_llm_processor)

        assert result == "Files processed"
        assert mock_executor.execute.call_count == 2
        calls = mock_executor.execute.call_args_list
        assert calls[0][0] == ("file_read", {"path": "/a.txt"})
        assert calls[1][0] == ("file_read", {"path": "/b.txt"})


class TestMaxStepsLimit:
    @pytest.mark.asyncio
    async def test_max_steps_limit_prevents_infinite_loop(
        self, mock_generator, mock_registry, mock_executor, mock_llm_processor
    ):
        """Loop must exit after max_steps and return a limit message."""
        from ergos.llm.tool_processor import ToolCallProcessor

        # Always returns tool_calls — never settles on text
        mock_generator.create_chat_completion_sync.return_value = _make_tool_call_response(
            "file_read", {"path": "/tmp/x.txt"}
        )

        processor = ToolCallProcessor(
            generator=mock_generator,
            registry=mock_registry,
            executor=mock_executor,
            system_prompt="test",
            max_steps=3,
        )

        speak = AsyncMock()
        result = await processor.process("Loop forever", speak, mock_llm_processor)

        # Must have stopped after max_steps (3)
        assert mock_generator.create_chat_completion_sync.call_count == 3
        assert "step limit" in result.lower() or "limit" in result.lower()


class TestHistoryIsolation:
    @pytest.mark.asyncio
    async def test_only_user_and_final_assistant_in_history(
        self, processor, mock_generator, mock_executor, mock_llm_processor
    ):
        """After process(), _history contains only user message and final response."""
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response("file_read", {"path": "/tmp/test.txt"}),
            _make_text_response("Here is the file content"),
        ]

        speak = AsyncMock()
        initial_history_len = len(mock_llm_processor._history)

        await processor.process("Read the file", speak, mock_llm_processor)

        new_messages = mock_llm_processor._history[initial_history_len:]
        assert len(new_messages) == 2, f"Expected 2 new messages, got {len(new_messages)}"

        user_msg = new_messages[0]
        assistant_msg = new_messages[1]

        assert user_msg.role == "user"
        assert user_msg.content == "Read the file"
        assert assistant_msg.role == "assistant"
        assert assistant_msg.content == "Here is the file content"

    @pytest.mark.asyncio
    async def test_tool_messages_not_in_history(
        self, processor, mock_generator, mock_executor, mock_llm_processor
    ):
        """Tool response messages are not in LLM history."""
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response("file_read", {"path": "/tmp/test.txt"}),
            _make_text_response("Done"),
        ]

        speak = AsyncMock()
        initial_len = len(mock_llm_processor._history)

        await processor.process("Read /tmp/test.txt", speak, mock_llm_processor)

        new_messages = mock_llm_processor._history[initial_len:]
        for msg in new_messages:
            assert msg.role in ("user", "assistant"), f"Unexpected role in history: {msg.role}"
            # No tool_response content should leak into history
            assert "<tool_response>" not in msg.content


class TestNoThinkAppended:
    @pytest.mark.asyncio
    async def test_no_think_appended_to_last_user_message(
        self, processor, mock_generator, mock_llm_processor
    ):
        """The last user message in the messages list must end with ' /no_think'."""
        captured_messages: list[list[dict]] = []

        def capture_call(messages, max_tokens=512):
            captured_messages.append(messages)
            return _make_text_response("reply")

        mock_generator.create_chat_completion_sync.side_effect = capture_call

        speak = AsyncMock()
        await processor.process("What is 2+2?", speak, mock_llm_processor)

        assert len(captured_messages) >= 1
        messages = captured_messages[0]
        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) >= 1

        last_user_msg = user_messages[-1]
        assert last_user_msg["content"].endswith(" /no_think"), (
            f"Last user message does not end with ' /no_think': {last_user_msg['content']!r}"
        )


class TestHasToolsProperty:
    def test_has_tools_delegates_to_registry(self, mock_generator, mock_executor):
        """has_tools property mirrors registry.has_tools."""
        from ergos.llm.tool_processor import ToolCallProcessor

        registry_true = MagicMock()
        registry_true.has_tools = True

        registry_false = MagicMock()
        registry_false.has_tools = False

        p_true = ToolCallProcessor(
            generator=mock_generator,
            registry=registry_true,
            executor=mock_executor,
            system_prompt="test",
        )
        p_false = ToolCallProcessor(
            generator=mock_generator,
            registry=registry_false,
            executor=mock_executor,
            system_prompt="test",
        )

        assert p_true.has_tools is True
        assert p_false.has_tools is False


class TestToolResultInMessages:
    @pytest.mark.asyncio
    async def test_tool_result_sent_as_tool_response_in_user_message(
        self, processor, mock_generator, mock_executor, mock_llm_processor
    ):
        """Tool results are sent to LLM as <tool_response> in a user message."""
        captured: list[list[dict]] = []
        call_count = 0

        def capture_calls(messages, max_tokens=512):
            nonlocal call_count
            call_count += 1
            captured.append(list(messages))
            if call_count == 1:
                return _make_tool_call_response("file_read", {"path": "/tmp/test.txt"})
            return _make_text_response("The file has content")

        mock_generator.create_chat_completion_sync.side_effect = capture_calls

        speak = AsyncMock()
        await processor.process("Read /tmp/test.txt", speak, mock_llm_processor)

        # Second call should contain the tool response
        assert len(captured) == 2
        second_call_msgs = captured[1]
        # Find user message with tool_response
        tool_result_msgs = [m for m in second_call_msgs if "<tool_response>" in m.get("content", "")]
        assert len(tool_result_msgs) >= 1, "No <tool_response> message found in second LLM call"
        assert "file contents here" in tool_result_msgs[0]["content"]


class TestNarrationMessages:
    @pytest.mark.asyncio
    async def test_narration_messages_for_known_tools(
        self, mock_generator, mock_registry, mock_executor, mock_llm_processor
    ):
        """_narration_before returns expected strings for known tool names."""
        from ergos.llm.tool_processor import ToolCallProcessor

        processor = ToolCallProcessor(
            generator=mock_generator,
            registry=mock_registry,
            executor=mock_executor,
            system_prompt="test",
        )

        assert "read" in processor._narration_before("file_read").lower()
        assert "run" in processor._narration_before("shell_run").lower() or \
               "command" in processor._narration_before("shell_run").lower()
        assert "file" in processor._narration_before("file_list").lower() or \
               "check" in processor._narration_before("file_list").lower()
        # Unknown tool
        narration = processor._narration_before("unknown_tool")
        assert isinstance(narration, str) and len(narration) > 0


class TestHistoryUsedInMessages:
    @pytest.mark.asyncio
    async def test_existing_history_included_in_messages_to_llm(
        self, processor, mock_generator, mock_llm_processor
    ):
        """Existing conversation history from llm_processor is included in messages list."""
        from ergos.llm.processor import Message

        mock_llm_processor._history.append(Message(role="user", content="Hello"))
        mock_llm_processor._history.append(Message(role="assistant", content="Hi there!"))

        captured_messages: list[list[dict]] = []

        def capture_call(messages, max_tokens=512):
            captured_messages.append(list(messages))
            return _make_text_response("reply")

        mock_generator.create_chat_completion_sync.side_effect = capture_call

        speak = AsyncMock()
        await processor.process("How are you?", speak, mock_llm_processor)

        assert len(captured_messages) >= 1
        messages = captured_messages[0]

        # System message first
        assert messages[0]["role"] == "system"

        # Find the history user message (not the current request)
        history_user_msgs = [m for m in messages if m["role"] == "user" and "Hello" in m["content"]]
        assert len(history_user_msgs) == 1

    @pytest.mark.asyncio
    async def test_system_prompt_includes_tools(
        self, processor, mock_generator, mock_llm_processor
    ):
        """System prompt must include tool definitions in Qwen3 <tools> format."""
        captured_messages: list[list[dict]] = []

        def capture_call(messages, max_tokens=512):
            captured_messages.append(list(messages))
            return _make_text_response("reply")

        mock_generator.create_chat_completion_sync.side_effect = capture_call

        speak = AsyncMock()
        await processor.process("test request", speak, mock_llm_processor)

        assert len(captured_messages) >= 1
        first_msg = captured_messages[0][0]
        assert first_msg["role"] == "system"
        assert "You are a test assistant." in first_msg["content"]
        # Tool definitions should be in the system prompt
        assert "<tools>" in first_msg["content"]
        assert "file_read" in first_msg["content"]


class TestToolCallParsing:
    def test_parse_single_tool_call(self, processor):
        """Parse a single <tool_call> block."""
        content = '<tool_call>\n{"name": "file_read", "arguments": {"path": "/tmp/test.txt"}}\n</tool_call>'
        result = processor._parse_tool_calls(content)
        assert len(result) == 1
        assert result[0]["name"] == "file_read"
        assert result[0]["arguments"] == {"path": "/tmp/test.txt"}

    def test_parse_no_tool_calls(self, processor):
        """No <tool_call> tags returns empty list."""
        result = processor._parse_tool_calls("Just a normal response.")
        assert result == []

    def test_parse_malformed_json(self, processor):
        """Malformed JSON inside <tool_call> is skipped."""
        content = '<tool_call>\n{not valid json}\n</tool_call>'
        result = processor._parse_tool_calls(content)
        assert result == []

    def test_parse_multiple_tool_calls(self, processor):
        """Parse multiple <tool_call> blocks in one response."""
        content = (
            '<tool_call>\n{"name": "file_read", "arguments": {"path": "/a.txt"}}\n</tool_call>\n'
            '<tool_call>\n{"name": "shell_run", "arguments": {"command": "ls"}}\n</tool_call>'
        )
        result = processor._parse_tool_calls(content)
        assert len(result) == 2
        assert result[0]["name"] == "file_read"
        assert result[1]["name"] == "shell_run"


class TestToolExecutionErrorHandling:
    @pytest.mark.asyncio
    async def test_tool_error_string_passed_as_tool_result(
        self, mock_generator, mock_registry, mock_executor, mock_llm_processor
    ):
        """If executor returns an error string, it should be passed as tool result."""
        from ergos.llm.tool_processor import ToolCallProcessor

        mock_executor.execute = AsyncMock(return_value="Error: file not found: /nonexistent.txt")

        captured: list[list[dict]] = []
        call_count = 0

        def capture_calls(messages, max_tokens=512):
            nonlocal call_count
            call_count += 1
            captured.append(list(messages))
            if call_count == 1:
                return _make_tool_call_response("file_read", {"path": "/nonexistent.txt"})
            return _make_text_response("Sorry, I couldn't read that file")

        mock_generator.create_chat_completion_sync.side_effect = capture_calls

        processor = ToolCallProcessor(
            generator=mock_generator,
            registry=mock_registry,
            executor=mock_executor,
            system_prompt="test",
        )

        speak = AsyncMock()
        result = await processor.process("Read /nonexistent.txt", speak, mock_llm_processor)

        assert result == "Sorry, I couldn't read that file"
        # The second call should contain the error in a tool_response
        assert len(captured) == 2
        second_call_msgs = captured[1]
        tool_result_msgs = [m for m in second_call_msgs if "<tool_response>" in m.get("content", "")]
        assert len(tool_result_msgs) == 1
        assert "Error" in tool_result_msgs[0]["content"]
