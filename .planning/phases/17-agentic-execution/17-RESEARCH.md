# Phase 17: Agentic Execution - Research

**Researched:** 2026-03-05
**Domain:** LLM tool calling, agentic loop, YAML tool registry, voice narration
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AGENT-01 | AI can call tools (file operations, shell commands) via LLM function calling | `create_chat_completion(tools=...)` with llama-cpp-python 0.3.16; chatml-function-calling chat format |
| AGENT-02 | AI narrates what it's doing during tool execution ("Let me check that...") | Speak narration phrase immediately after detecting `finish_reason == "tool_calls"`, before executing; speak completion phrase after |
| AGENT-03 | AI can chain multiple tools to complete multi-step workflows | Agentic loop pattern: loop until `finish_reason != "tool_calls"`, append tool results as `role=tool` messages |
| AGENT-04 | Tool registry allows adding new tools without code changes | YAML registry loaded at startup; tools discovered and built into `ChatCompletionTool` list; file-watch optional for hot-reload |
</phase_requirements>

---

## Summary

Phase 17 adds agentic tool-calling to Ergos/TARS: the LLM can invoke tools (file reads, shell commands, etc.), narrate its actions aloud, chain multiple calls, and support new tools added via YAML without code changes.

The critical architectural finding is that **tool calling requires a different API surface than what `LLMProcessor` currently uses**. The existing pipeline calls `create_completion(prompt)` with a hand-built prompt string. Tool calling requires `create_chat_completion(messages, tools=...)` which handles the chatml-function-calling template internally. This means a new `ToolCallProcessor` (or a mode-switched path in `LLMProcessor`) is needed, taking messages as a list rather than a raw prompt.

The `chatml-function-calling` chat format in llama-cpp-python 0.3.16 works out of the box for Qwen3-8B. The format uses the model's chatml template but extends the system message with function schemas. When the model wants to call a tool, `finish_reason == "tool_calls"` and the result is in `choices[0]["message"]["tool_calls"]`. The agentic loop simply appends tool results as `role=tool` messages and re-invokes until the model responds without tool calls.

**Primary recommendation:** Add a `ToolCallProcessor` class that owns the agentic loop using `create_chat_completion`. Wire it into `pipeline.py` after STT transcription, upstream of the existing LLM flow (when tools are enabled). YAML registry files are scanned at startup from a configurable directory (default `~/.ergos/tools/`) and loaded into `ChatCompletionTool` objects. Narration phrases are spoken via the existing `speak_callback` immediately when a tool call is detected.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| llama-cpp-python | 0.3.16 (installed) | `create_chat_completion` with tool calling | Already in project; has full `tools` parameter support |
| llama_cpp.ChatCompletionTool | (bundled) | Tool schema type | OpenAI-compatible; works with chatml-function-calling format |
| pyyaml | 6.0+ (installed) | YAML tool registry loading | Already in project; `yaml.safe_load` for registry files |
| pydantic | 2.0+ (installed) | Tool definition validation | Already in project; validate registry entries before use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio.create_subprocess_exec | stdlib | Safe shell command execution | For `shell` tool type — replaces `os.system` for async safety |
| pathlib.Path | stdlib | File path operations | For `file_read`, `file_write`, `file_list` tools |
| json | stdlib | Tool argument parsing and result serialization | Arguments arrive as JSON strings from LLM |
| subprocess | stdlib | Shell execution with timeout | Enforce max_seconds on shell tool calls |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| chatml-function-calling | Raw prompt engineering with `<tool_call>` XML parsing | chatml-function-calling is built-in and tested; raw parsing is fragile |
| YAML tool registry | Python plugin class per tool | YAML satisfies AGENT-04 (no code changes); Python plugins are more powerful but require code |
| Custom agentic loop | LangChain/LlamaIndex agent | Zero new dependencies; LangChain adds 50+ packages for a 50-line loop |

**Installation:** No new packages needed. All dependencies are already present.

---

## Architecture Patterns

### Recommended Project Structure
```
src/ergos/
├── tools/                    # New: tool execution layer
│   ├── __init__.py           # ToolRegistry, ToolExecutor exports
│   ├── registry.py           # YAML registry loader → ChatCompletionTool list
│   ├── executor.py           # Dispatcher: name → implementation → result str
│   └── builtins.py           # Built-in implementations: file_read, shell, etc.
├── llm/
│   ├── processor.py          # Existing: unchanged (text-only path)
│   └── tool_processor.py     # New: ToolCallProcessor with agentic loop
└── pipeline.py               # Updated: wire ToolCallProcessor when tools enabled
~/.ergos/tools/               # User-editable tool registry files
│   └── default.yaml          # Shipped with project as example
```

### Pattern 1: YAML Tool Registry Format
**What:** Tools are defined as YAML files; each entry maps directly to an OpenAI-compatible function schema plus an `impl` field that names the executor.
**When to use:** Always — this is how AGENT-04 (no code changes for new tools) is satisfied.
**Example:**
```yaml
# ~/.ergos/tools/default.yaml
tools:
  - name: file_read
    description: "Read the contents of a file at the given path"
    impl: builtin.file_read
    parameters:
      type: object
      properties:
        path:
          type: string
          description: "Absolute or home-relative file path"
      required: [path]

  - name: shell_run
    description: "Run a shell command and return stdout. Timeout is 10 seconds."
    impl: builtin.shell_run
    parameters:
      type: object
      properties:
        command:
          type: string
          description: "Shell command to execute"
        timeout_seconds:
          type: integer
          description: "Max seconds to wait (default 10, max 30)"
      required: [command]

  - name: file_list
    description: "List files in a directory matching an optional glob pattern"
    impl: builtin.file_list
    parameters:
      type: object
      properties:
        directory:
          type: string
          description: "Directory to list"
        pattern:
          type: string
          description: "Optional glob pattern, e.g. '*.py'"
      required: [directory]
```

### Pattern 2: ToolCallProcessor Agentic Loop
**What:** Uses `create_chat_completion` with `tools=` and loops until no more tool calls.
**When to use:** When the LLM is operating in agentic mode (AGENT-01, AGENT-03).
**Example:**
```python
# Source: llama-cpp-python 0.3.16 create_chat_completion API + verified against source
import json
from llama_cpp import Llama

async def process_with_tools(
    model: Llama,
    messages: list[dict],
    tools: list[dict],       # ChatCompletionTool list built from YAML registry
    speak: Callable,         # pipeline speak_callback for narration (AGENT-02)
    executor: "ToolExecutor",
    max_steps: int = 8,
) -> str:
    """Agentic loop: call LLM, execute tool calls, loop until text response."""
    loop = asyncio.get_event_loop()

    for step in range(max_steps):
        # Run inference in thread pool (llama.cpp is blocking + not thread-safe)
        def _call():
            with model_lock:
                return model.create_chat_completion(
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=512,
                    temperature=0.2,
                    stop=["<|im_end|>", "<|endoftext|>"],
                    chat_format="chatml-function-calling",
                )
        response = await loop.run_in_executor(executor_pool, _call)

        choice = response["choices"][0]
        finish_reason = choice["finish_reason"]
        message = choice["message"]

        if finish_reason != "tool_calls":
            # Final text response — return it
            return message.get("content") or ""

        # Model wants to call tools — narrate (AGENT-02)
        tool_calls = message["tool_calls"]
        for tc in tool_calls:
            narration = _narration_before(tc["function"]["name"])
            await speak(narration)

        # Append assistant's tool-call message to history
        messages.append({
            "role": "assistant",
            "content": message.get("content"),  # May be None
            "tool_calls": tool_calls,
        })

        # Execute each tool call
        for tc in tool_calls:
            args = json.loads(tc["function"]["arguments"])
            result_str = await executor.execute(tc["function"]["name"], args)

            # Append tool result
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_str,
            })

            # Narrate completion (AGENT-02)
            await speak(_narration_after(tc["function"]["name"]))

    return "I hit the step limit trying to complete that."


def _narration_before(tool_name: str) -> str:
    phrases = {
        "file_read": "Let me read that file.",
        "shell_run": "Let me run that command.",
        "file_list": "Let me check what files are there.",
    }
    return phrases.get(tool_name, "Let me check that...")

def _narration_after(tool_name: str) -> str:
    return "Done."
```

### Pattern 3: Registry Loading
**What:** Scan a directory for `*.yaml` files, parse tool definitions, validate, build `ChatCompletionTool` list.
**When to use:** At server startup (satisfies AGENT-04 without restart).
**Example:**
```python
# Source: verified against pydantic 2.0 and pyyaml 6.0 APIs
import yaml
from pathlib import Path
from llama_cpp import ChatCompletionTool, ChatCompletionToolFunction


def load_tool_registry(tools_dir: str = "~/.ergos/tools") -> list[dict]:
    """Load all .yaml files from tools_dir into ChatCompletionTool-compatible dicts."""
    tools_path = Path(tools_dir).expanduser()
    if not tools_path.exists():
        return []

    tools = []
    for yaml_file in sorted(tools_path.glob("*.yaml")):
        with open(yaml_file) as f:
            data = yaml.safe_load(f) or {}
        for entry in data.get("tools", []):
            tools.append({
                "type": "function",
                "function": {
                    "name": entry["name"],
                    "description": entry["description"],
                    "parameters": entry["parameters"],
                },
                # Store impl for executor dispatch (stripped before passing to LLM)
                "_impl": entry.get("impl", ""),
            })
    return tools
```

### Pattern 4: Narration Integration in Pipeline
**What:** The narration phrases (AGENT-02) are spoken through the existing TTS pipeline via `speak_callback`.
**When to use:** Immediately before calling executor (before tool), immediately after tool result received (after tool).
**Example:**
```python
# In pipeline.py — wiring ToolCallProcessor
async def on_transcription_agentic(result: TranscriptionResult) -> None:
    """Route transcription through agentic tool processor."""
    if not tool_processor.has_tools:
        # Fall back to existing LLM path
        await llm_processor.process_transcription(result)
        return

    # Convert history to messages format for create_chat_completion
    messages = tool_processor.build_messages(result.text)

    response_text = await tool_processor.process(
        messages=messages,
        speak=plugin_speak_callback,  # Reuse existing speak callback
    )

    # Stream response text through existing TTS path
    for token in response_text.split():
        await tts_token_callback(token + " ")
```

### Anti-Patterns to Avoid
- **Parsing `<tool_call>` XML manually:** The chatml-function-calling handler returns structured `tool_calls` already — don't attempt to parse raw generation text.
- **Using `create_completion` with a hand-crafted tool prompt:** Only `create_chat_completion` with `chat_format="chatml-function-calling"` produces proper tool call parsing.
- **Passing `tools=` to the existing `LLMProcessor.process_transcription`:** That uses `create_completion` (raw prompt), not `create_chat_completion`. They are different code paths.
- **Running shell commands with `os.system` or `subprocess.run` without timeout:** Agentic shell calls MUST have a timeout. A hung subprocess blocks the asyncio event loop if not run in executor.
- **Injecting `/no_think` into the messages when using `create_chat_completion`:** The `chatml-function-calling` handler builds its own template. The `/no_think` suffix applied in `_build_chatml_prompt` is NOT needed here — in fact, the `create_chat_completion` path bypasses `_build_chatml_prompt` entirely.
- **Passing `_impl` key inside the tool dict to the LLM:** Strip registry-internal fields before constructing `ChatCompletionTool` objects passed to the model.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tool call detection from raw LLM text | Custom XML/JSON parser on raw stream | `create_chat_completion` with `tools=` | Parser breaks on varied whitespace; the handler is tested across model versions |
| Agentic framework | LangChain Agent, LlamaIndex ReAct | Simple `while finish_reason == "tool_calls"` loop | Phase 17 needs 50 lines; adding LangChain adds 50+ packages and 200ms overhead |
| Tool schema validation | Custom validator | Pydantic model on YAML entries | Edge cases (missing fields, wrong types) already handled |
| Concurrent tool execution | Custom threading | `asyncio.gather` only when tools are independent | Most tool chains are sequential (read→summarize); parallel only adds complexity |
| Shell sandboxing | Custom seccomp/namespace | `timeout` + restricted PATH | This is a local dev assistant — full sandbox is out of scope for v2 |

**Key insight:** The agentic loop is genuinely simple when using `create_chat_completion`. The complexity is in the integration points (narration, state machine transitions, history management), not in the loop itself.

---

## Common Pitfalls

### Pitfall 1: `create_completion` vs `create_chat_completion` Confusion
**What goes wrong:** Developer tries to pass `tools=` to `create_completion` or hand-builds a chatml prompt with tool schemas — neither produces parseable tool call responses.
**Why it happens:** `LLMProcessor` currently uses `create_completion` (raw prompt). The tool call API is exclusively on `create_chat_completion`.
**How to avoid:** `ToolCallProcessor` must call `generator._model.create_chat_completion(...)` directly (or add a new method to `LLMGenerator` that wraps `create_chat_completion`). Do NOT reuse `generate_stream`.
**Warning signs:** LLM generates text like `functions.read_file:\n{...}` but code doesn't see `tool_calls` in the response.

### Pitfall 2: History Format Mismatch
**What goes wrong:** After a tool call, developer appends the result as `{"role": "user", "content": result}` — this confuses the model about who is speaking and degrades multi-step accuracy.
**Why it happens:** The `role: tool` message type is new (not used anywhere in the existing codebase). It's easy to fall back to the familiar `role: user`.
**How to avoid:** Tool results MUST use `{"role": "tool", "tool_call_id": <id>, "content": <result_str>}`. The `tool_call_id` must match the `id` field from the tool call request.
**Warning signs:** Model asks to call the same tool repeatedly, or refuses to synthesize an answer.

### Pitfall 3: `model_lock` Not Held During `create_chat_completion`
**What goes wrong:** `ToolCallProcessor` calls `create_chat_completion` from the asyncio loop concurrently with a `generate_stream` call (e.g., during barge-in recovery). llama.cpp is not thread-safe — this causes segfaults.
**Why it happens:** `ToolCallProcessor` is a new code path that may not reuse `generator._model_lock`.
**How to avoid:** All calls to `generator._model` (both `create_completion` and `create_chat_completion`) MUST acquire `generator._model_lock` before calling. Pass the lock reference into `ToolCallProcessor` or add a method to `LLMGenerator` that wraps `create_chat_completion` with the lock held.
**Warning signs:** Server segfaults during barge-in while a tool call is in progress.

### Pitfall 4: State Machine Stuck in PROCESSING During Multi-Step Tool Calls
**What goes wrong:** The existing 60-second PROCESSING timeout fires during a slow multi-step tool chain (e.g., a shell command that runs for 15s × 4 steps). System transitions to IDLE mid-execution.
**Why it happens:** The safety timeout was designed for single-turn LLM generation, not multi-step agentic workflows.
**How to avoid:** Either (a) extend the timeout to 5 minutes during agentic mode, or (b) reset/extend the processing timeout after each successful tool step. Option (b) is cleaner.
**Warning signs:** AI stops mid-workflow with no explanation; logs show "Processing timeout: stuck in PROCESSING."

### Pitfall 5: Shell Tool Security Scope Creep
**What goes wrong:** `shell_run` tool lets the LLM execute arbitrary system commands. A hallucinated or confused tool call runs `rm -rf ~` or `sudo reboot`.
**Why it happens:** No allowlist on shell commands.
**How to avoid:** Shell tool MUST have: (a) configurable allowlist of permitted command prefixes in YAML, (b) hard timeout of 30s max, (c) run as current user (no sudo), (d) log every invocation. Default YAML ships with a conservative allowlist.
**Warning signs:** Commands running outside expected scope appear in logs.

### Pitfall 6: Narration TTS Blocks the Agentic Loop
**What goes wrong:** `await speak("Let me check that...")` sends text to TTS which synthesizes a full audio chunk — during this time the tool is not yet executing, creating a noticeable pause.
**Why it happens:** Narration is injected synchronously before tool execution.
**How to avoid:** Start tool execution AND narration concurrently: `await asyncio.gather(speak(narration), executor.execute(name, args))`. This overlaps TTS synthesis with tool execution. Only applies to tools with non-trivial execution time (>500ms). For fast tools (<200ms), sequential is fine.
**Warning signs:** Audible 1-2 second silence between narration phrase and first tool result.

### Pitfall 7: LLM History Pollution from Agentic Turns
**What goes wrong:** All tool call messages (including intermediate assistant + tool role messages) get appended to `LLMProcessor._history` — on the next regular conversation turn, the history is bloated with JSON tool schemas and raw file contents.
**Why it happens:** `ToolCallProcessor` and `LLMProcessor` share history state.
**How to avoid:** `ToolCallProcessor` manages its OWN message list for the current agentic turn. Only the final user request + final AI response get added to `LLMProcessor._history` (the same way any turn is recorded). Intermediate tool messages are ephemeral.
**Warning signs:** Context window fills up rapidly; LLM starts hallucinating file paths it "remembers" from previous sessions.

---

## Code Examples

Verified patterns from the installed llama-cpp-python 0.3.16 source and type definitions:

### Build ChatCompletionTool from YAML Entry
```python
# Source: verified against llama_cpp types (ChatCompletionTool, ChatCompletionToolFunction)
from llama_cpp import ChatCompletionTool, ChatCompletionToolFunction

def yaml_entry_to_tool(entry: dict) -> ChatCompletionTool:
    """Convert a YAML registry entry to a ChatCompletionTool dict."""
    return {
        "type": "function",
        "function": {
            "name": entry["name"],
            "description": entry["description"],
            "parameters": entry["parameters"],
        },
    }
```

### Detect and Extract Tool Calls from Response
```python
# Source: verified against llama_cpp.llama_chat_format.chatml_function_calling source
def get_tool_calls(response: dict) -> list[dict] | None:
    """Return tool_calls list if model wants to call tools, else None."""
    choice = response["choices"][0]
    if choice.get("finish_reason") != "tool_calls":
        return None
    return choice["message"].get("tool_calls", [])


def get_response_text(response: dict) -> str:
    """Extract final text from a non-tool-call response."""
    return response["choices"][0]["message"].get("content") or ""
```

### Append Tool Result to Messages
```python
# Source: verified against llama_cpp.ChatCompletionRequestToolMessage type annotations
def append_tool_result(
    messages: list[dict],
    tool_call_id: str,
    result: str,
) -> None:
    """Append a tool result message in the format llama_cpp expects."""
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": result,
    })
```

### Safe Shell Execution
```python
# Source: asyncio.create_subprocess_exec stdlib documentation
import asyncio

async def run_shell_command(command: str, timeout_seconds: int = 10) -> str:
    """Run a shell command and return stdout+stderr. Hard timeout enforced."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "/bin/sh", "-c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_seconds,
        )
        output = (stdout.decode() + stderr.decode()).strip()
        return output[:4096]  # Truncate large outputs
    except asyncio.TimeoutError:
        proc.kill()
        return f"Error: command timed out after {timeout_seconds}s"
    except Exception as e:
        return f"Error: {e}"
```

### LLMGenerator Wrapper for create_chat_completion
```python
# New method to add to LLMGenerator — keeps lock discipline consistent
def create_chat_completion_sync(
    self,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 512,
) -> dict:
    """Call create_chat_completion with lock held. Blocking (call from executor)."""
    model = self._ensure_model()
    with self._model_lock:
        return model.create_chat_completion(
            messages=messages,
            tools=tools or [],
            tool_choice="auto" if tools else "none",
            max_tokens=max_tokens,
            temperature=0.2,
            stop=["<|im_end|>", "<|endoftext|>"],
        )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Prompt engineering `<tool_call>` XML in system prompt | `create_chat_completion(tools=)` with OpenAI-compatible schema | llama-cpp-python 0.2+ | Reliable parsing; no need to parse raw text |
| LangChain ReAct agent for local tool use | Direct loop with `create_chat_completion` | 2024-2025 | Removes 50+ dependencies; no overhead |
| Static Python tool definitions | YAML registry with dynamic loading | Emerging pattern 2025 | Satisfies hot-reload without code changes |

**Deprecated/outdated:**
- `functions` parameter (deprecated): llama-cpp-python still accepts it but it's superseded by `tools`. Use `tools` exclusively.
- Separate `chatml` + manual tool prompt engineering: `chatml-function-calling` format is the correct choice for Qwen3-8B.

---

## Open Questions

1. **Qwen3-8B Q4_K_M tool-calling accuracy**
   - What we know: Qwen3-8B has native tool-calling support; Q4_K_M quantization slightly degrades capability; `chatml-function-calling` format works with Qwen3 chatml template
   - What's unclear: Whether Q4_K_M degrades tool-call F1 enough to require a different temperature or grammar constraint
   - Recommendation: Test during Wave 0 with a simple `file_read` call; if accuracy is low, add `grammar=LlamaGrammar.from_json_schema(...)` to the `create_chat_completion` call for structured output

2. **Hot-reload of tool registry (AGENT-04 scope)**
   - What we know: AGENT-04 says "without restarting the server" — the YAML is loaded at startup today
   - What's unclear: Does "without restarting" mean file-watcher for hot-reload, or simply no code changes needed (restart still OK)?
   - Recommendation: Interpret as "no code changes required; restart IS acceptable." Implement hot-reload as a stretch goal only if startup interpretation is confirmed.

3. **`/no_think` interaction with `create_chat_completion`**
   - What we know: The existing `_build_chatml_prompt` appends `/no_think` to disable Qwen3 chain-of-thought. `create_chat_completion` builds its own prompt, bypassing `_build_chatml_prompt`.
   - What's unclear: Whether `chatml-function-calling` handler will trigger Qwen3's `<think>` block without `/no_think` in user message.
   - Recommendation: In `create_chat_completion` messages, set the last user message content to `{text} /no_think` explicitly to maintain consistent behavior.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.0+ (installed in dev deps) |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` testpaths=["tests"], pythonpath=["src"] |
| Quick run command | `uv run pytest tests/unit/test_tools*.py -x -q` |
| Full suite command | `uv run pytest tests/unit/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AGENT-01 | `file_read` tool call is detected and executed from mocked `create_chat_completion` response | unit | `uv run pytest tests/unit/test_tool_registry.py tests/unit/test_tool_executor.py -x -q` | Wave 0 |
| AGENT-01 | `shell_run` tool executes a safe command and returns stdout | unit | `uv run pytest tests/unit/test_tool_executor.py::test_shell_run_basic -x -q` | Wave 0 |
| AGENT-02 | Narration phrase spoken before tool execution (mock speak_callback) | unit | `uv run pytest tests/unit/test_tool_processor.py::test_narration_before_tool -x -q` | Wave 0 |
| AGENT-02 | "Done." spoken after tool result received | unit | `uv run pytest tests/unit/test_tool_processor.py::test_narration_after_tool -x -q` | Wave 0 |
| AGENT-03 | Two-step tool chain completes: step 1 returns tool_calls, step 2 returns text | unit | `uv run pytest tests/unit/test_tool_processor.py::test_multi_step_chain -x -q` | Wave 0 |
| AGENT-03 | Max step limit (8) is enforced — loop exits without infinite recursion | unit | `uv run pytest tests/unit/test_tool_processor.py::test_max_steps_limit -x -q` | Wave 0 |
| AGENT-04 | YAML registry loads tool definitions and builds correct ChatCompletionTool list | unit | `uv run pytest tests/unit/test_tool_registry.py::test_yaml_loading -x -q` | Wave 0 |
| AGENT-04 | Tool added to YAML file is available in registry after `reload()` | unit | `uv run pytest tests/unit/test_tool_registry.py::test_tool_added_after_reload -x -q` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_tool_registry.py tests/unit/test_tool_executor.py tests/unit/test_tool_processor.py -x -q`
- **Per wave merge:** `uv run pytest tests/unit/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_tool_registry.py` — covers AGENT-04 (registry loading, YAML parsing)
- [ ] `tests/unit/test_tool_executor.py` — covers AGENT-01 (file_read, shell_run, file_list dispatch)
- [ ] `tests/unit/test_tool_processor.py` — covers AGENT-02, AGENT-03 (narration, agentic loop, max steps)
- [ ] `~/.ergos/tools/default.yaml` — example registry shipped with project

*(No new framework install needed — pytest and uv are already configured.)*

---

## Sources

### Primary (HIGH confidence)
- llama-cpp-python 0.3.16 source — `llama_chat_format.chatml_function_calling` function, `ChatCompletionTool`, `ChatCompletionRequestToolMessage` type annotations — verified by direct inspection with `uv run python3 -c "..."` in the project virtualenv
- llama-cpp-python 0.3.16 `create_chat_completion` signature — verified: `tools: Optional[List[ChatCompletionTool]]`, `tool_choice: Optional[ChatCompletionToolChoiceOption]` params confirmed
- Project codebase — `src/ergos/llm/generator.py` (model lock pattern, `_executor` thread pool), `src/ergos/llm/processor.py` (history format, `max_history_messages`), `src/ergos/pipeline.py` (speak callback wiring), `src/ergos/plugins/base.py` (plugin architecture)
- Project `pyproject.toml` — dependencies confirmed: pydantic 2.0+, pyyaml 6.0+, llama-cpp-python 0.2+ (actual 0.3.16), pytest dev dep

### Secondary (MEDIUM confidence)
- [llama-cpp-python function calling docs](https://llama-cpp-python.readthedocs.io/) — confirmed `chatml-function-calling` chat format exists; `tool_choice="auto"` pattern
- [Qwen3 function calling guide](https://qwen.readthedocs.io/en/latest/framework/function_call.html) — confirmed Qwen3-Instruct uses standard JSON tool definitions wrapped in `<tool_call>` style; chatml-function-calling handler is the appropriate wrapper
- [llama.cpp function calling docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md) — confirmed Qwen2.5/Qwen3 uses Hermes-2 Pro format handler internally; `--jinja` flag advised for server mode (not relevant for llama-cpp-python direct use)

### Tertiary (LOW confidence — not needed, informational only)
- DeepWiki llama-cpp-python function calling — agentic loop structure cross-reference

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies already installed; API verified against installed source
- Architecture: HIGH — `create_chat_completion` API verified; loop pattern confirmed from handler source
- Pitfalls: HIGH — Pitfalls 1-4 verified from existing code patterns; Pitfall 5-7 are design-time reasoning with HIGH plausibility
- YAML registry pattern: HIGH — pyyaml + pydantic both in project; pattern is straightforward

**Research date:** 2026-03-05
**Valid until:** 2026-06-05 (stable — llama-cpp-python API surface is stable; Qwen3 tool format is established)
