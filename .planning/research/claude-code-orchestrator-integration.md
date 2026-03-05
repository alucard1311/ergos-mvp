# Claude Code as Orchestrator for TARS Voice Assistant

**Research Date**: 2026-03-04
**Status**: Complete

## Executive Summary

There are **four viable integration approaches** for delegating complex tasks from TARS (local Qwen3-8B voice assistant) to Claude:

| Approach | Best For | Latency | Cost | Complexity |
|----------|----------|---------|------|------------|
| **Claude Agent SDK (Python)** | Production integration | Medium | API pricing | Medium |
| **Claude Code CLI subprocess** | Quick prototyping | Higher | CLI subscription | Low |
| **Anthropic API direct** | Maximum control | Lowest | API pricing | High |
| **MCP bidirectional** | Tool sharing | Variable | Mixed | High |

**Recommended approach**: Claude Agent SDK (Python) for production, with CLI subprocess as a fast MVP path.

---

## 1. Claude Code CLI Programmatic Usage

### 1.1 Core CLI Flags for Automation

The `claude` CLI supports full headless/non-interactive operation via `-p` (print mode):

```bash
# Basic one-shot query
claude -p "Explain the auth module" --output-format json

# With tool permissions and budget cap
claude -p "Fix the bug in auth.py" \
  --allowedTools "Read,Edit,Bash" \
  --max-turns 10 \
  --max-budget-usd 2.00 \
  --output-format json

# Pipe content into Claude
cat error_log.txt | claude -p "Diagnose this error" --output-format json

# Custom system prompt
claude -p "Research quantum computing" \
  --append-system-prompt "You are a research assistant. Be thorough." \
  --output-format json
```

### 1.2 Output Formats

| Format | Flag | Use Case |
|--------|------|----------|
| `text` | `--output-format text` | Human-readable (default) |
| `json` | `--output-format json` | Programmatic parsing - returns `{result, session_id, ...}` |
| `stream-json` | `--output-format stream-json` | Real-time streaming - newline-delimited JSON events |

**JSON output structure** (extractable with `jq`):
```bash
# Extract just the text result
claude -p "Summarize this project" --output-format json | jq -r '.result'

# Get structured output with schema validation
claude -p "Extract function names" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}}}'
```

**Stream-JSON for real-time token streaming**:
```bash
claude -p "Write a poem" --output-format stream-json --verbose --include-partial-messages | \
  jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'
```

### 1.3 Session Management

```bash
# Continue most recent conversation
claude -p "Follow up on the previous analysis" --continue

# Resume specific session by ID
session_id=$(claude -p "Start a review" --output-format json | jq -r '.session_id')
claude -p "Continue that review" --resume "$session_id"

# Resume by name
claude -r "auth-refactor" "Finish this PR"

# Fork a session (new ID, same context)
claude --resume abc123 --fork-session
```

### 1.4 Python Subprocess Integration

```python
import subprocess
import json

def invoke_claude(prompt: str, tools: list[str] = None, max_turns: int = 5) -> dict:
    """Invoke Claude Code CLI as a subprocess and return structured result."""
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--max-turns", str(max_turns),
    ]
    if tools:
        cmd.extend(["--allowedTools", ",".join(tools)])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )
    stdout, stderr = proc.communicate(timeout=300)

    if proc.returncode != 0:
        return {"error": stderr, "returncode": proc.returncode}

    return json.loads(stdout)


# Usage from TARS
result = invoke_claude(
    "Research the best approach for implementing WebSocket reconnection",
    tools=["WebSearch", "WebFetch", "Read"],
    max_turns=10,
)
print(result["result"])  # The text response
print(result["session_id"])  # For continuing later
```

### 1.5 Async Subprocess with Streaming

```python
import asyncio
import json

async def stream_claude(prompt: str) -> AsyncIterator[str]:
    """Stream Claude Code CLI output token by token."""
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose", "--include-partial-messages",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async for line in proc.stdout:
        try:
            event = json.loads(line.decode().strip())
            if (event.get("type") == "stream_event" and
                event.get("event", {}).get("delta", {}).get("type") == "text_delta"):
                yield event["event"]["delta"]["text"]
        except (json.JSONDecodeError, KeyError):
            continue

    await proc.wait()
```

### 1.6 Key Limitations of CLI Approach

- **Token overhead**: Each subprocess invocation burns ~50K tokens on system prompt + MCP tool descriptions before doing actual work. Proper isolation reduces this to ~5K tokens.
- **Cold start**: Each invocation spawns a new process; no persistent connection.
- **No native async**: Must wrap in subprocess; no direct Python integration.
- **Cost**: Uses Claude Code subscription (Max plan at $100/mo or $200/mo for heavy use) rather than per-token API pricing.

---

## 2. Claude Agent SDK (Python)

### 2.1 Overview

The Claude Agent SDK (formerly "Claude Code SDK") exposes the same engine that powers Claude Code as a Python/TypeScript library. It provides the full agent loop with built-in tool execution.

```bash
pip install claude-agent-sdk
export ANTHROPIC_API_KEY=your-api-key
```

### 2.2 Two APIs: `query()` vs `ClaudeSDKClient`

| Feature | `query()` | `ClaudeSDKClient` |
|---------|-----------|-------------------|
| Session | New each time | Reuses same session |
| Conversation | Single exchange | Multi-turn in same context |
| Interrupts | Not supported | Supported |
| Continue Chat | No | Yes |
| Best For | One-off tasks | Ongoing conversations |

### 2.3 Basic Usage with `query()`

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage


async def delegate_to_claude(task: str) -> str:
    """Delegate a complex task to Claude and return the result."""
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
        system_prompt="You are TARS's research assistant. Provide concise, actionable answers.",
        max_turns=15,
    )

    result_text = ""
    async for message in query(prompt=task, options=options):
        if isinstance(message, ResultMessage) and message.subtype == "success":
            result_text = message.result

    return result_text


# Called from TARS pipeline
answer = asyncio.run(delegate_to_claude(
    "Research the latest approaches to WebSocket reconnection with exponential backoff"
))
```

### 2.4 Streaming Output for TTS Relay

```python
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import StreamEvent


async def stream_claude_to_tts(task: str, tts_callback):
    """Stream Claude's response directly to TTS for voice output."""
    options = ClaudeAgentOptions(
        include_partial_messages=True,
        allowed_tools=["Read", "WebSearch", "WebFetch"],
    )

    sentence_buffer = ""
    async for message in query(prompt=task, options=options):
        if isinstance(message, StreamEvent):
            event = message.event
            if event.get("type") == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    sentence_buffer += text

                    # Flush to TTS on sentence boundaries
                    if any(sentence_buffer.rstrip().endswith(p) for p in ".!?"):
                        await tts_callback(sentence_buffer.strip())
                        sentence_buffer = ""

    # Flush remaining text
    if sentence_buffer.strip():
        await tts_callback(sentence_buffer.strip())
```

### 2.5 Multi-Turn with `ClaudeSDKClient`

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock


async def persistent_claude_session():
    """Maintain a persistent Claude session across multiple voice interactions."""
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
    )

    async with ClaudeSDKClient(options=options) as client:
        # First task
        await client.query("Read the auth module and summarize it")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"Claude: {block.text}")

        # Follow-up (retains full context)
        await client.query("Now find all places that call it")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"Claude: {block.text}")

        # Can interrupt long-running tasks
        await client.query("Do a comprehensive security audit")
        await asyncio.sleep(30)
        await client.interrupt()  # User said "stop" via voice
```

### 2.6 Custom Tools via @tool Decorator

Ergos can expose its own capabilities as MCP tools that Claude can call:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, query, ClaudeAgentOptions


@tool("check_device_status", "Check status of a smart home device", {"device_name": str})
async def check_device(args):
    """Claude can call this to check home devices via Ergos."""
    device = args["device_name"]
    # Query Ergos's home automation integration
    status = await home_assistant.get_device_status(device)
    return {"content": [{"type": "text", "text": f"{device}: {status}"}]}


@tool("set_timer", "Set a kitchen timer", {"minutes": int, "label": str})
async def set_timer(args):
    """Claude can set timers through Ergos."""
    await timer_manager.create_timer(args["minutes"], args["label"])
    return {"content": [{"type": "text", "text": f"Timer set: {args['label']} for {args['minutes']}min"}]}


# Bundle as an MCP server
ergos_tools = create_sdk_mcp_server(
    name="ergos",
    version="1.0.0",
    tools=[check_device, set_timer],
)

# Claude can now use Ergos's tools alongside its built-in ones
options = ClaudeAgentOptions(
    mcp_servers={"ergos": ergos_tools},
    allowed_tools=["Read", "WebSearch", "mcp__ergos__*"],
)
```

### 2.7 Session Management for Voice

```python
async def voice_claude_session():
    """Capture session ID for resuming across voice interactions."""
    session_id = None

    async for message in query(
        prompt="Analyze the error logs from today",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Glob"]),
    ):
        if hasattr(message, "subtype") and message.subtype == "init":
            session_id = message.session_id  # Save for later

    # User comes back 5 minutes later via voice: "continue that analysis"
    async for message in query(
        prompt="Now summarize the findings",
        options=ClaudeAgentOptions(resume=session_id),
    ):
        if isinstance(message, ResultMessage):
            return message.result
```

---

## 3. Anthropic API Direct

### 3.1 When to Use Direct API

- **Maximum control** over prompts, tool definitions, and conversation flow
- **Cost optimization** - no CLI overhead, precise token management
- **Custom tool loops** - implement your own agent loop
- **Lowest latency** - direct HTTP, no subprocess overhead

### 3.2 Basic Usage

```python
from anthropic import Anthropic

client = Anthropic()  # Uses ANTHROPIC_API_KEY env var

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system="You are TARS's research assistant. Be concise.",
    messages=[
        {"role": "user", "content": "Research WebSocket reconnection best practices"}
    ],
)
print(response.content[0].text)
```

### 3.3 Tool Use / Function Calling

```python
from anthropic import Anthropic

client = Anthropic()

tools = [
    {
        "name": "search_codebase",
        "description": "Search the Ergos codebase for relevant code",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "file_pattern": {"type": "string", "description": "Glob pattern"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the Ergos project",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
            },
            "required": ["path"],
        },
    },
]

# Multi-turn tool use loop
messages = [{"role": "user", "content": "Find and explain the VAD processor"}]

while True:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=tools,
        messages=messages,
    )

    # Check if Claude wants to use a tool
    if response.stop_reason == "tool_use":
        tool_use = next(b for b in response.content if b.type == "tool_use")
        tool_result = execute_tool(tool_use.name, tool_use.input)

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": tool_result}],
        })
    else:
        # Final text response
        print(response.content[0].text)
        break
```

### 3.4 Streaming for Voice

```python
from anthropic import Anthropic

client = Anthropic()

async def stream_to_tts(prompt: str, tts_callback):
    """Stream API response directly to TTS."""
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        buffer = ""
        for text in stream.text_stream:
            buffer += text
            if any(buffer.rstrip().endswith(p) for p in ".!?"):
                await tts_callback(buffer.strip())
                buffer = ""
        if buffer.strip():
            await tts_callback(buffer.strip())
```

### 3.5 Pricing (as of March 2026)

| Model | Input | Output | Cache Hits | Best For |
|-------|-------|--------|------------|----------|
| Claude Opus 4.6 | $5/MTok | $25/MTok | $0.50/MTok | Complex reasoning, coding |
| Claude Sonnet 4.6 | $3/MTok | $15/MTok | $0.30/MTok | Balanced quality/cost |
| Claude Haiku 4.5 | $1/MTok | $5/MTok | $0.10/MTok | Fast, simple tasks |

**Cost optimization strategies**:
- **Prompt caching**: Cache hits cost 10x less than base input. First cache write is 1.25x, but pays off after one reuse.
- **Batch API**: 50% discount for non-real-time tasks (Opus 4.6: $2.50/$12.50 per MTok).
- **Model routing**: Use Haiku for classification/routing, Sonnet for most tasks, Opus for hard problems.
- **For TARS**: A typical voice interaction (500 input + 500 output tokens) costs ~$0.012 with Sonnet 4.6.

### 3.6 Direct API vs Agent SDK vs CLI

| Dimension | Direct API | Agent SDK | CLI Subprocess |
|-----------|-----------|-----------|----------------|
| Tool execution | You implement | Built-in (Read, Edit, Bash, etc.) | Built-in |
| Agent loop | You implement | Automatic | Automatic |
| Streaming | Native | Native | Via stream-json |
| Session mgmt | Manual | Built-in | Via --resume |
| File operations | You implement | Automatic | Automatic |
| Cost | Per-token API | Per-token API | CLI subscription |
| Latency | Lowest | Low | Higher (process spawn) |
| Complexity | Highest | Medium | Lowest |

---

## 4. Integration Patterns for Voice + Orchestrator

### 4.1 Task Classification: Local vs Delegate

TARS needs a fast classifier to decide whether to handle locally or delegate:

```python
# Classification keywords/patterns for delegation
DELEGATE_SIGNALS = {
    "high_complexity": [
        "research", "analyze", "investigate", "compare", "debug",
        "refactor", "implement", "design", "architect", "plan",
        "write code", "fix the bug", "review", "audit", "optimize",
    ],
    "multi_step": [
        "step by step", "first...then", "create a plan",
        "look into", "figure out", "deep dive",
    ],
    "external_knowledge": [
        "what's the latest", "search for", "find out about",
        "look up", "documentation for", "how does...work",
    ],
    "code_tasks": [
        "edit the file", "change the code", "add a feature",
        "write a test", "create a script", "commit",
    ],
}

LOCAL_SIGNALS = [
    "what time", "set timer", "what's the weather",
    "turn on", "turn off", "play music",
    "hello", "how are you", "tell me a joke",
    "thank you", "goodbye", "sarcasm level",
]


def should_delegate_to_claude(text: str) -> bool:
    """Fast heuristic: does this need Claude Code?"""
    text_lower = text.lower()

    # Check local-only patterns first (fast path)
    for pattern in LOCAL_SIGNALS:
        if pattern in text_lower:
            return False

    # Check delegation signals
    for category, patterns in DELEGATE_SIGNALS.items():
        for pattern in patterns:
            if pattern in text_lower:
                return True

    # Length heuristic: long complex requests likely need Claude
    if len(text.split()) > 30:
        return True

    return False
```

**Advanced: Use Qwen3 itself as the classifier** (better accuracy, ~200ms overhead):

```python
CLASSIFIER_PROMPT = """Classify this user request. Reply with ONLY one word: LOCAL or DELEGATE.

LOCAL = simple question, greeting, timer, device control, chitchat, jokes
DELEGATE = coding, research, multi-step analysis, debugging, writing, complex reasoning

User: {text}
Classification:"""


async def classify_with_llm(text: str, llm_generator) -> bool:
    """Use Qwen3 to classify whether to delegate. ~200ms overhead."""
    prompt = CLASSIFIER_PROMPT.format(text=text)
    result = await llm_generator.generate(prompt, max_tokens=5)
    return "DELEGATE" in result.upper()
```

### 4.2 Streaming Long-Form Output Through TTS

The challenge: Claude may produce paragraphs of text, but TTS should deliver sentence by sentence.

```python
class ClaudeToTTSBridge:
    """Bridge between Claude's streaming output and TARS's TTS pipeline."""

    def __init__(self, tts_processor, state_machine):
        self.tts = tts_processor
        self.state = state_machine
        self.sentence_buffer = ""
        self.is_cancelled = False

    async def on_claude_token(self, token: str):
        """Called for each streaming token from Claude."""
        if self.is_cancelled:
            return

        self.sentence_buffer += token

        # Detect sentence boundaries
        for terminator in [".", "!", "?", ":\n", "\n\n"]:
            if self.sentence_buffer.rstrip().endswith(terminator):
                sentence = self.sentence_buffer.strip()
                if sentence and len(sentence) > 3:  # Skip trivial fragments
                    await self.tts.synthesize_and_play(sentence)
                self.sentence_buffer = ""
                break

    async def flush(self):
        """Flush remaining buffer at end of response."""
        if self.sentence_buffer.strip() and not self.is_cancelled:
            await self.tts.synthesize_and_play(self.sentence_buffer.strip())
        self.sentence_buffer = ""

    def cancel(self):
        """User barged in - stop relaying."""
        self.is_cancelled = True
        self.sentence_buffer = ""
```

### 4.3 Handling Long-Running Tasks

Claude Code can take minutes for complex tasks. TARS should handle this gracefully:

```python
class ClaudeDelegation:
    """Manages delegated tasks with progress updates and cancellation."""

    def __init__(self, speak_callback, tts_bridge):
        self.speak = speak_callback
        self.bridge = tts_bridge
        self.active_task = None

    async def delegate(self, task: str):
        """Delegate task with acknowledgment and progress."""
        # Immediate acknowledgment via local TTS
        await self.speak("On it. Let me work on that for you.")

        # Start Claude in background
        self.active_task = asyncio.create_task(
            self._run_claude_task(task)
        )

        # User can still talk to TARS while Claude works
        return self.active_task

    async def _run_claude_task(self, task: str):
        """Run Claude task with streaming output to TTS."""
        try:
            options = ClaudeAgentOptions(
                include_partial_messages=True,
                allowed_tools=["Read", "Edit", "Bash", "WebSearch"],
                max_turns=20,
            )

            tool_in_progress = False
            async for message in query(prompt=task, options=options):
                if self.bridge.is_cancelled:
                    break

                if isinstance(message, StreamEvent):
                    event = message.event
                    event_type = event.get("type")

                    # Track tool usage for progress updates
                    if event_type == "content_block_start":
                        content = event.get("content_block", {})
                        if content.get("type") == "tool_use":
                            tool_in_progress = True
                            # Optional: announce tool usage
                            # await self.speak(f"Searching with {content.get('name')}...")

                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta" and not tool_in_progress:
                            await self.bridge.on_claude_token(delta.get("text", ""))

                    elif event_type == "content_block_stop":
                        tool_in_progress = False

                elif isinstance(message, ResultMessage):
                    await self.bridge.flush()
                    await self.speak("Done. Is there anything else?")

        except asyncio.CancelledError:
            await self.speak("Task cancelled.")
        except Exception as e:
            await self.speak(f"Sorry, I ran into an error: {str(e)[:100]}")

    async def cancel(self):
        """Cancel the active task (e.g., user barge-in)."""
        self.bridge.cancel()
        if self.active_task and not self.active_task.done():
            self.active_task.cancel()
```

### 4.4 Summarization for Voice

Claude's written output is often too verbose for voice. Add a summarization layer:

```python
async def summarize_for_voice(long_text: str, llm_generator) -> str:
    """Use local Qwen3 to compress Claude's output for voice delivery."""
    if len(long_text.split()) < 50:
        return long_text  # Short enough already

    prompt = f"""Summarize this for spoken delivery. Keep it under 3 sentences.
Be conversational, not formal. Skip code blocks and technical details.

Text: {long_text}

Spoken summary:"""

    return await llm_generator.generate(prompt, max_tokens=150)
```

### 4.5 Context Sharing Between TARS and Claude

```python
class ConversationBridge:
    """Share context between TARS (Qwen3) and Claude sessions."""

    def __init__(self):
        self.claude_session_id = None
        self.tars_context = []  # Recent TARS conversation turns

    def get_context_for_claude(self) -> str:
        """Build context string from recent TARS conversation."""
        if not self.tars_context:
            return ""

        context = "Recent voice conversation context:\n"
        for turn in self.tars_context[-10:]:  # Last 10 turns
            role = "User" if turn["role"] == "user" else "TARS"
            context += f"{role}: {turn['content']}\n"
        return context

    async def delegate_with_context(self, task: str) -> str:
        """Delegate to Claude with TARS conversation context."""
        context = self.get_context_for_claude()
        full_prompt = f"{context}\n\nNew task: {task}"

        options = ClaudeAgentOptions(
            allowed_tools=["Read", "WebSearch"],
            append_system_prompt=(
                "The user is speaking through a voice assistant called TARS. "
                "Recent conversation context is provided above. "
                "Keep responses concise and suitable for voice delivery."
            ),
        )

        if self.claude_session_id:
            options.resume = self.claude_session_id

        async for message in query(prompt=full_prompt, options=options):
            if hasattr(message, "session_id"):
                self.claude_session_id = message.session_id
            if isinstance(message, ResultMessage):
                return message.result
```

---

## 5. MCP (Model Context Protocol) Integration

### 5.1 Ergos as MCP Server (Claude Connects to Ergos)

Ergos can expose its capabilities as an MCP server that Claude Code connects to:

```python
# ergos_mcp_server.py - Run alongside Ergos
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

app = Server("ergos-assistant")


@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="speak",
            description="Speak text to the user through TARS voice assistant",
            inputSchema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        ),
        Tool(
            name="get_conversation_history",
            description="Get recent voice conversation history with the user",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="check_home_device",
            description="Check status of a smart home device",
            inputSchema={
                "type": "object",
                "properties": {"device": {"type": "string"}},
                "required": ["device"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "speak":
        await tts_pipeline.speak(arguments["text"])
        return [TextContent(type="text", text="Spoken to user")]
    elif name == "get_conversation_history":
        history = conversation_store.get_recent(10)
        return [TextContent(type="text", text=str(history))]
    elif name == "check_home_device":
        status = await home_assistant.query(arguments["device"])
        return [TextContent(type="text", text=status)]


async def main():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())
```

**Configure Claude Code to connect**:
```bash
claude mcp add --transport stdio ergos-assistant -- python /path/to/ergos_mcp_server.py
```

### 5.2 Claude Code as MCP Server (Ergos Connects to Claude)

Claude Code can expose its own tools as an MCP server:

```bash
claude mcp serve
```

This exposes Claude Code's tools (Read, Write, Edit, Bash, Glob, Grep, etc.) via stdio MCP protocol. Ergos could connect as an MCP client, but this is less practical because:
- Ergos would need to implement an MCP client
- The tools are designed for Claude's agent loop, not direct invocation
- Better to use the Agent SDK directly

### 5.3 In-Process MCP (Agent SDK Custom Tools)

The most practical MCP pattern uses the Agent SDK's `@tool` decorator for in-process tools:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, query, ClaudeAgentOptions


@tool("query_ergos_memory", "Search TARS's conversation memory", {"query": str})
async def query_memory(args):
    results = await memory_store.search(args["query"], limit=5)
    formatted = "\n".join([f"- {r.text} ({r.timestamp})" for r in results])
    return {"content": [{"type": "text", "text": formatted}]}


@tool("get_system_status", "Get Ergos system status", {})
async def get_status(args):
    status = {
        "uptime": get_uptime(),
        "active_connections": webrtc_manager.connection_count,
        "gpu_usage": vram_monitor.usage_percent,
        "active_timers": timer_manager.active_count,
    }
    return {"content": [{"type": "text", "text": json.dumps(status, indent=2)}]}


ergos_server = create_sdk_mcp_server("ergos", tools=[query_memory, get_status])

# Use in delegation
options = ClaudeAgentOptions(
    mcp_servers={"ergos": ergos_server},
    allowed_tools=["Read", "WebSearch", "mcp__ergos__*"],
)
```

### 5.4 Bidirectional MCP Architecture

```
                    MCP Protocol
    +----------+  <------------>  +-------------+
    |  Ergos/  |  Claude calls    | Claude Code |
    |  TARS    |  Ergos tools     | Agent SDK   |
    |          |  (speak, memory) |             |
    | MCP      |  <------------>  | MCP Client  |
    | Server   |  Ergos calls     |             |
    |          |  Claude tools    | Built-in    |
    | MCP      |  (Read, Search)  | Tools       |
    | Client   |                  |             |
    +----------+                  +-------------+
```

In practice, the **Agent SDK with @tool decorators** is the simplest way to achieve this bidirectional integration without running separate MCP server processes.

---

## 6. Recommended Architecture for TARS + Claude Code

### 6.1 Architecture Overview

```
User Voice Input
       |
       v
  [STT: Whisper]
       |
       v
  [Qwen3-8B: Fast Classifier]
       |
       +-- LOCAL --> [Qwen3-8B: Generate Response] --> [TTS: Orpheus]
       |
       +-- DELEGATE --> [Claude Agent SDK]
                            |
                            +-- Streaming tokens --> [Sentence Splitter]
                            |                            |
                            |                            v
                            |                      [TTS: Orpheus]
                            |
                            +-- Tool results --> [Qwen3 Summarizer] --> [TTS]
                            |
                            +-- Session stored for --resume
```

### 6.2 Implementation Plan

**Phase 1: MVP (CLI Subprocess)**
- Add `should_delegate_to_claude()` heuristic classifier
- Invoke `claude -p` via subprocess with `--output-format json`
- Summarize response with Qwen3 before TTS
- No streaming, no session management

**Phase 2: Agent SDK Integration**
- Replace subprocess with `claude-agent-sdk` Python package
- Add streaming via `include_partial_messages=True`
- Implement sentence-boundary TTS streaming
- Add session persistence via `ClaudeSDKClient`

**Phase 3: Full Integration**
- Custom MCP tools (@tool decorator) for Ergos capabilities
- LLM-based task classifier (Qwen3)
- Context sharing between TARS and Claude sessions
- Barge-in cancellation via `client.interrupt()`
- Progress announcements for long tasks

**Phase 4: MCP Ecosystem**
- Ergos as standalone MCP server
- Connect to external MCP servers (GitHub, databases)
- Tool search for dynamic capability discovery

### 6.3 Where This Fits in Ergos Codebase

The integration would be implemented as an Ergos plugin:

```
src/ergos/plugins/claude_orchestrator/
    __init__.py          # ClaudeOrchestratorPlugin (extends BasePlugin)
    classifier.py        # Task classification (local vs delegate)
    delegation.py        # Claude Agent SDK integration
    tts_bridge.py        # Streaming output to TTS
    session_manager.py   # Cross-session context management
    mcp_tools.py         # Custom @tool definitions for Ergos
```

The plugin hooks into the existing `PluginManager.route_input()` flow. When `should_activate()` detects a complex task, it takes over the conversation, delegates to Claude, and streams the response back through TTS.

### 6.4 Cost Estimates

| Usage Pattern | Model | Monthly Cost |
|---------------|-------|-------------|
| 10 delegations/day, ~2K tokens each | Sonnet 4.6 | ~$2.70/mo |
| 10 delegations/day, ~2K tokens each | Opus 4.6 | ~$9.00/mo |
| 50 delegations/day, ~5K tokens each | Sonnet 4.6 | ~$67.50/mo |
| CLI subscription (alternative) | Max plan | $100-200/mo |

**Recommendation**: Use Anthropic API via Agent SDK with Sonnet 4.6 as the default model, escalating to Opus 4.6 for tasks explicitly requiring maximum reasoning capability. This is significantly cheaper than the CLI subscription model for typical voice assistant usage.

---

## Sources

- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference)
- [Run Claude Code Programmatically](https://code.claude.com/docs/en/headless)
- [Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Agent SDK Python Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Agent SDK Streaming Output](https://platform.claude.com/docs/en/agent-sdk/streaming-output)
- [Agent SDK MCP Integration](https://platform.claude.com/docs/en/agent-sdk/mcp)
- [Agent SDK Python on GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- [Claude Code MCP Documentation](https://code.claude.com/docs/en/mcp)
- [Anthropic API Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Anthropic API Tool Use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)
- [MCP Protocol](https://modelcontextprotocol.io/)
- [Claude Code Voice Mode (TechCrunch)](https://techcrunch.com/2026/03/03/claude-code-rolls-out-a-voice-mode-capability/)
- [Claude Agent SDK Tutorial (DataCamp)](https://www.datacamp.com/tutorial/how-to-use-claude-agent-sdk)
- [Claude Code as MCP Server Guide](https://www.ksred.com/claude-code-as-an-mcp-server-an-interesting-capability-worth-understanding/)
- [Building Claude Code Wrappers (DEV)](https://dev.to/jungjaehoon/why-claude-code-subagents-waste-50k-tokens-per-turn-and-how-to-fix-it-41ma)
