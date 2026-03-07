<p align="center">
  <img src="img/logo.svg" alt="Voiceover Logo" width="340" />
</p>

# Voiceover: Voice Interface for Any AI Agent

<p align="center">
  <img src="img/kagent.png" alt="Voiceover Architecture" width="740" />
</p>

**Voiceover** turns any AI agent or MCP server into a voice-controlled assistant — in any language. Connect it to [kagent](https://kagent.dev/), your own agents, or any MCP-compatible tool server and start talking.

[▶️ Watch a quick demo](https://youtube.com/shorts/3cU2NpGXqRk)

---

## How It Works

Voiceover bridges your voice to agents via the [A2A (Agent-to-Agent)](https://google.github.io/A2A/) and [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) protocols. Skills and tools are discovered automatically — just configure a URL and talk.

```
You (voice) → Whisper STT → GPT-4.1 → A2A / MCP → your agent
                    ↑                        ↑
              any language         auto skill discovery
```

**Stack:**
- Speech-to-text: OpenAI Whisper (multilingual)
- LLM: OpenAI GPT-4.1-mini
- Text-to-speech: ElevenLabs Multilingual v2 (30+ languages)
- Voice activity detection: Silero VAD
- Agent framework: [LiveKit Agents](https://docs.livekit.io/agents/)

---

## Quick Start

### Prerequisites

- Python 3.9+
- API keys: OpenAI, ElevenLabs, LiveKit

### Install

```sh
make venv
source venv/bin/activate
make install
```

### Configure

```sh
export OPENAI_API_KEY=your_openai_api_key
export ELEVEN_API_KEY=your_elevenlabs_api_key
```

Edit `config.yaml` to point at your agents or MCP servers (see [Configuration](#configuration)).

### Run

```sh
make run
```

The console UI supports both voice and text input:

- **`Ctrl+B`** — toggle between Audio and Text mode
- **`Q`** — quit

---

## Configuration

### A2A Agents

Connect to any agent that implements the [A2A protocol](https://google.github.io/A2A/). Skills are discovered automatically via `/.well-known/agent.json`.

```yaml
servers:
  - name: k8s-agent
    type: a2a
    url: https://kagent.example.com/api/a2a/kagent/k8s-agent
    auth:                   # optional
      type: bearer
      env_var: KAGENT_TOKEN
```

### MCP Servers

Connect to any [MCP](https://modelcontextprotocol.io/)-compatible tool server over Streamable HTTP.

```yaml
servers:
  - name: my-mcp-server
    type: mcp               # default if omitted
    url: https://my-server.example.com/mcp
    allowed_tools: [tool1, tool2]   # optional — omit to load all
    auth:
      type: bearer
      env_var: MCP_TOKEN
```

### Authentication

```yaml
auth:
  type: bearer        # sets Authorization: Bearer <token>
  env_var: MY_TOKEN
```

---

## Example: Kagent Integration

[kagent](https://kagent.dev/) is an open-source framework for running AI agents in Kubernetes. Voiceover connects to kagent agents as A2A servers, giving you a voice interface to your entire cluster.

### 1. Expose the kagent A2A API

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: kagent-a2a-route
  namespace: kagent
spec:
  hostnames:
  - kagent.example.com
  parentRefs:
  - kind: Gateway
    name: your-gateway
    namespace: your-gateway-namespace
    sectionName: https
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /api/a2a
    backendRefs:
    - name: kagent-controller
      port: 8083
```

### 2. Add a2aConfig to your agents

```yaml
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: k8s-agent
  namespace: kagent
spec:
  declarative:
    a2aConfig:
      skills:
      - id: k8s-operations-skill
        name: Kubernetes Operations
        description: Kubernetes cluster operations, troubleshooting, and maintenance.
        inputModes: [text]
        outputModes: [text]
        tags: [k8s, kubernetes]
        examples:
        - "Get all pods in the default namespace"
        - "Describe deployment nginx"
```

### 3. Configure config.yaml

```yaml
servers:
  - name: k8s-agent
    type: a2a
    url: https://kagent.example.com/api/a2a/kagent/k8s-agent

  - name: helm-agent
    type: a2a
    url: https://kagent.example.com/api/a2a/kagent/helm-agent

  - name: observability-agent
    type: a2a
    url: https://kagent.example.com/api/a2a/kagent/observability-agent
```

kagent ships with agents for Kubernetes, Helm, Istio, Cilium, Argo Rollouts, Prometheus/Grafana, and more. See the [kagent docs](https://kagent.dev/docs/) for the full list.

---

## Project Structure

```
voiceover/
├── src/
│   ├── main.py               # Entry point
│   ├── agent_core.py         # LiveKit agent loop
│   ├── a2a.py                # A2A protocol client
│   ├── mcp_config.py         # Config loader
│   ├── tool_integration.py   # Dynamic tool registration
│   └── mcp_client/
│       ├── server.py         # MCP server connection
│       ├── sse_client.py     # HTTP/SSE transport
│       ├── auth.py           # Bearer + HMAC auth
│       ├── agent_tools.py    # LiveKit tool helpers
│       └── util.py           # Shared utilities
├── tests/
├── config.yaml          # Agent/server configuration
├── system_prompt.txt         # LLM system prompt
├── requirements.txt
└── Makefile
```

---

## Testing

```sh
make test
```

---

## Troubleshooting

**SSL errors:**
```sh
make certs-macos   # macOS
make certs-linux   # Linux
```

**Agent not responding:**
- Verify the A2A endpoint: `curl https://your-agent/.well-known/agent.json`
- Check the agent has `a2aConfig.skills` configured
- For MCP: confirm the SSE endpoint is reachable

---

## Contributing

Contributions are welcome! Please open an issue first for major changes.

1. Fork the repo
2. Create a branch: `git checkout -b my-feature`
3. Commit and open a Pull Request

---

## License

[MIT License](LICENSE)

---

## Acknowledgements

- [kagent](https://kagent.dev/) — Kubernetes-native AI agent framework
- [LiveKit Agents](https://docs.livekit.io/agents/) — voice agent framework
- [A2A Protocol](https://google.github.io/A2A/) — agent interoperability standard
- [Model Context Protocol](https://modelcontextprotocol.io/) — tool server standard
- [OpenAI](https://openai.com/) — Whisper STT and GPT-4.1
- [ElevenLabs](https://elevenlabs.io/) — multilingual text-to-speech
- [Silero VAD](https://github.com/snakers4/silero-vad) — voice activity detection
- DeepLearning.AI course: [Building AI Voice Agents for Production](https://www.deeplearning.ai/short-courses/building-ai-voice-agents-for-production/)
