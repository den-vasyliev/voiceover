# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make venv       # Create virtual environment
make install    # Install dependencies via uv
make run        # Run the agent: python src/main.py console
make test       # Run tests: pytest
make certs-macos / make certs-linux  # Fix SSL certificate issues
```

Run a single test file: `pytest tests/test_a2a.py`
Run a specific test: `pytest tests/test_a2a.py::test_list_tools`

## Architecture Overview

Voiceover is a voice interface that bridges spoken commands to AI agents via the **A2A (Agent-to-Agent)** and **MCP (Model Context Protocol)** protocols.

```
User Speech
  → LiveKit Agent (STT: OpenAI Whisper, VAD: Silero)
  → LLM Backend (OpenAI / Anthropic / Google Gemini / Vertex AI / Ollama)
  → Tool Execution (A2A agents or MCP tool servers)
  → Voice Response (TTS: ElevenLabs)
```

### Key Components

**`src/main.py`** — Entry point. Loads `config.yaml`, authenticates to servers (OAuth or bearer token), fetches prompts from MCP servers to inject into system instructions, and starts the LiveKit agent with assembled tools.

**`src/agent_core.py`** — `FunctionAgent` class (extends LiveKit `Agent`). Manages STT/TTS/VAD/LLM configuration and wires them together. `create_llm()` is a factory for all supported backends (also reused for MCP sampling).

**`src/a2a.py`** — `A2AServerConfig` class. Implements the A2A protocol client: discovers agent skills via `/.well-known/agent.json`, sends tasks as JSON-RPC 2.0 `message/send`, and handles retries with exponential backoff.

**`src/mcp_client/server.py`** — MCP server base classes. `MCPServerSse` implements the Streamable HTTP transport (MCP spec 2025-03-26) with `list_tools()`, `call_tool()`, `list_prompts()`, `get_prompt()`, and MCP sampling via `sampling/createMessage` callback.

**`src/tool_integration.py`** — `filtered_prepare_dynamic_tools()`. Merges tools from all A2A and MCP servers, applies per-server `allowed_tools` filters (supports wildcards like `list_*`), and returns decorated tools for the LiveKit agent.

**`src/mcp_client/agent_tools.py`** — `MCPToolsIntegration`. Wraps MCP tools as LiveKit `FunctionTool` instances. Contains special-case handling for the Anthropic backend (typed function signatures required).

**`src/mcp_client/util.py`** — Schema utilities. `_normalize_schema()` adds `additionalProperties: false` to JSON schemas, which OpenAI requires.

### Configuration

**`config.yaml`** — Declares A2A and MCP servers with type, URL, optional bearer auth, and optional `allowed_tools` list. Environment variables are expanded via `${VAR_NAME}` syntax.

**`system_prompt.txt`** — System prompt loaded at startup. Currently tuned for an SRE assistant persona.

### Protocol Notes

- **A2A agents** expose a single `prompt` parameter tool; the full request is passed as a string.
- **MCP servers** expose typed multi-parameter tools that flow through as-is after filtering.
- Anthropic backend requires concrete typed signatures for function tools — `agent_tools.py` generates these dynamically.
- `pytest.ini` sets `asyncio_mode = auto` and `pythonpath = src`, so test imports resolve without `sys.path` hacks.
