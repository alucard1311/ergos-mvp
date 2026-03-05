"""Tests for ToolCallProcessor: agentic loop, concurrent narration, multi-step, history isolation."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Helpers: mock response builders
# ---------------------------------------------------------------------------

def _make_tool_call_response(tool_name: str, arguments_json: str, tool_call_id: str = "call_001") -> dict:
    """Build a create_chat_completion response with finish_reason='tool_calls'."""
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": arguments_json,
                            },
                        }
                    ],
                },
            }
        ]
    }


def _make_text_response(text: str) -> dict:
    """Build a create_chat_completion response with finish_reason='stop'."""
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": text,
                    "tool_calls": None,
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
    # create_chat_completion_sync is called via run_in_executor so it's blocking
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
        """Single tool call: step 1 returns tool_calls, step 2 returns text."""
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response("file_read", json.dumps({"path": "/tmp/test.txt"})),
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
        """When finish_reason='stop', no tools are executed."""
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
            _make_tool_call_response("file_read", json.dumps({"path": "/tmp/test.txt"})),
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
        # If sequential: |execute_start - speak_start| >= EXECUTION_DELAY
        # If concurrent: |execute_start - speak_start| < EXECUTION_DELAY/2
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
            _make_tool_call_response("file_read", json.dumps({"path": "/tmp/test.txt"})),
            _make_text_response("All done"),
        ]

        # Track all speak calls in order
        speak_calls: list[str] = []

        async def record_speak(text: str):
            speak_calls.append(text)

        await processor.process("test", record_speak, mock_llm_processor)

        # "Done." must appear in speak calls and must not be the first call
        # First call should be the narration (e.g., "Let me read that file.")
        # "Done." should follow after asyncio.gather(narration, execution) completes
        assert "Done." in speak_calls, f"'Done.' never spoken. Speak calls: {speak_calls}"
        done_idx = speak_calls.index("Done.")
        assert done_idx > 0, f"'Done.' was the very first speak call — should come after narration. Calls: {speak_calls}"


class TestMultiStepChain:
    @pytest.mark.asyncio
    async def test_two_step_chain_executes_both_tools(
        self, processor, mock_generator, mock_executor, mock_llm_processor
    ):
        """Multi-step: tool_calls on step 1 and 2, text on step 3."""
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response("file_read", json.dumps({"path": "/a.txt"}), "call_001"),
            _make_tool_call_response("file_read", json.dumps({"path": "/b.txt"}), "call_002"),
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
            "file_read", json.dumps({"path": "/tmp/x.txt"})
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
        # Result must indicate step limit reached
        assert "step limit" in result.lower() or "limit" in result.lower()


class TestHistoryIsolation:
    @pytest.mark.asyncio
    async def test_only_user_and_final_assistant_in_history(
        self, processor, mock_generator, mock_executor, mock_llm_processor
    ):
        """After process(), _history contains only user message and final response."""
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response("file_read", json.dumps({"path": "/tmp/test.txt"})),
            _make_text_response("Here is the file content"),
        ]

        speak = AsyncMock()
        initial_history_len = len(mock_llm_processor._history)

        await processor.process("Read the file", speak, mock_llm_processor)

        # Should have added exactly 2 messages: user + assistant
        new_messages = mock_llm_processor._history[initial_history_len:]
        assert len(new_messages) == 2, f"Expected 2 new messages, got {len(new_messages)}: {new_messages}"

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
        """Tool call messages (role='assistant' with tool_calls, role='tool') are not in history."""
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response("file_read", json.dumps({"path": "/tmp/test.txt"})),
            _make_text_response("Done"),
        ]

        speak = AsyncMock()
        initial_len = len(mock_llm_processor._history)

        await processor.process("Read /tmp/test.txt", speak, mock_llm_processor)

        new_messages = mock_llm_processor._history[initial_len:]
        for msg in new_messages:
            assert msg.role in ("user", "assistant"), f"Unexpected role in history: {msg.role}"
            if msg.role == "assistant":
                # Should not have tool_calls attribute or it should be a plain content message
                assert not hasattr(msg, "tool_calls") or msg.content is not None


class TestNoThinkAppended:
    @pytest.mark.asyncio
    async def test_no_think_appended_to_last_user_message(
        self, processor, mock_generator, mock_llm_processor
    ):
        """The last user message in the messages list must end with ' /no_think'."""
        mock_generator.create_chat_completion_sync.return_value = _make_text_response("reply")

        speak = AsyncMock()
        captured_messages: list[list[dict]] = []

        def capture_call(messages, tools=None, max_tokens=512):
            captured_messages.append(messages)
            return _make_text_response("reply")

        mock_generator.create_chat_completion_sync.side_effect = capture_call

        await processor.process("What is 2+2?", speak, mock_llm_processor)

        assert len(captured_messages) >= 1
        messages = captured_messages[0]
        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) >= 1

        last_user_msg = user_messages[-1]
        assert last_user_msg["content"].endswith(" /no_think"), (
            f"Last user message content does not end with ' /no_think': {last_user_msg['content']!r}"
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


class TestToolResultRoleIsToolWithId:
    @pytest.mark.asyncio
    async def test_tool_result_uses_role_tool_with_call_id(
        self, processor, mock_generator, mock_executor, mock_llm_processor
    ):
        """Tool result messages sent to LLM must use role='tool' and matching tool_call_id."""
        tool_call_id = "call_abc123"
        mock_generator.create_chat_completion_sync.side_effect = [
            _make_tool_call_response(
                "file_read", json.dumps({"path": "/tmp/test.txt"}), tool_call_id
            ),
            _make_text_response("The file has content"),
        ]

        speak = AsyncMock()
        captured_second_call_messages: list[dict] = []

        call_count = 0

        def capture_second_call(messages, tools=None, max_tokens=512):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_tool_call_response(
                    "file_read", json.dumps({"path": "/tmp/test.txt"}), tool_call_id
                )
            # Second call: capture the messages
            captured_second_call_messages.extend(messages)
            return _make_text_response("The file has content")

        mock_generator.create_chat_completion_sync.side_effect = capture_second_call

        await processor.process("Read /tmp/test.txt", speak, mock_llm_processor)

        # Find the tool result message in the second call's messages
        tool_messages = [m for m in captured_second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) >= 1, "No role='tool' messages found in second LLM call"

        tool_msg = tool_messages[0]
        assert tool_msg["role"] == "tool"
        assert tool_msg.get("tool_call_id") == tool_call_id, (
            f"Expected tool_call_id={tool_call_id!r}, got {tool_msg.get('tool_call_id')!r}"
        )


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
