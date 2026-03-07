<p align="center">
  <img src="img/logo.png" alt="Voiceover Logo" width="340" />
</p>

# Voiceover: Voice Interface for Kagent

<p align="center">
  <img src="img/kagent.png" alt="Voiceover + Kagent" width="740" />
</p>

**Voiceover** gives you a voice interface to any AI agent running in [kagent](https://kagent.dev/). Talk to your Kubernetes, Helm, Istio, Cilium, and observability agents — hands-free, in plain English.

[▶️ Watch a quick demo](https://youtube.com/shorts/3cU2NpGXqRk)

---

## How It Works

Voiceover connects to kagent agents over the [A2A (Agent-to-Agent) protocol](https://google.github.io/A2A/). Each kagent agent exposes its skills via A2A — Voiceover discovers them automatically and makes them available as voice commands.

```
You (voice) → Whisper STT → GPT-4.1 → A2A → kagent agent → cluster
                                            ↑
                              skill discovery via /.well-known/agent.json
```

**Stack:**
- Speech-to-text: OpenAI Whisper
- LLM: OpenAI GPT-4.1-mini
- Text-to-speech: ElevenLabs
- Voice activity detection: Silero VAD
- Agent framework: [LiveKit Agents](https://docs.livekit.io/agents/)
- Agent backend: [kagent](https://kagent.dev/)

---

## Quick Start

### Prerequisites

- Python 3.9+
- A running [kagent](https://kagent.dev/) installation in your cluster
- API keys: OpenAI, ElevenLabs, LiveKit

### Install

```sh
make venv
source venv/bin/activate
make install
```

### Configure

Set environment variables:

```sh
export OPENAI_API_KEY=your_openai_api_key
export ELEVEN_API_KEY=your_elevenlabs_api_key
export LIVEKIT_URL=wss://your-livekit-server
export LIVEKIT_API_KEY=your_livekit_api_key
export LIVEKIT_API_SECRET=your_livekit_api_secret
```

Point `mcp_servers.yaml` at your kagent instance. The agents below are the standard kagent agents — adjust the base URL to your cluster:

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

  - name: istio-agent
    type: a2a
    url: https://kagent.example.com/api/a2a/kagent/istio-agent

  - name: cilium-manager-agent
    type: a2a
    url: https://kagent.example.com/api/a2a/kagent/cilium-manager-agent
```

### Run

```sh
make run
```

---

## Kagent Setup

### 1. Deploy kagent

Follow the [kagent installation docs](https://kagent.dev/docs/getting-started/installation).

### 2. Expose the A2A API

Create an HTTPRoute for `/api/a2a` pointing to the kagent controller:

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

### 3. Add a2aConfig to your agents

Each kagent agent needs an `a2aConfig` block so Voiceover can discover its skills:

```yaml
apiVersion: kagent.dev/v1alpha2
kind: Agent
metadata:
  name: k8s-agent
  namespace: kagent
spec:
  declarative:
    # ... existing config ...
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
        - "Get recent events in kube-system"
```

---

## Available Kagent Agents

Out of the box, kagent ships with agents for:

| Agent | Skills |
|---|---|
| `k8s-agent` | Pod/deployment/resource management, events, logs |
| `helm-agent` | Helm release lifecycle, repo management |
| `observability-agent` | Prometheus queries, Grafana dashboards, Loki logs |
| `promql-agent` | PromQL generation from natural language |
| `istio-agent` | Service mesh config, traffic management, mTLS |
| `kgateway-agent` | Gateway API resources, routing, troubleshooting |
| `cilium-manager-agent` | Cilium install, upgrade, ClusterMesh, Hubble |
| `cilium-policy-agent` | CiliumNetworkPolicy generation |
| `cilium-debug-agent` | Cilium endpoint/BPF/encryption diagnostics |
| `argo-rollouts-conversion-agent` | Convert Deployments to Argo Rollouts |

---

## Example Voice Commands

- _"Get all pods in the default namespace"_
- _"Show me the error rate for the payments service"_
- _"Convert deployment my-app to an Argo Rollout with canary strategy"_
- _"Generate a PromQL query for 95th percentile latency"_
- _"Create a network policy to isolate namespace production"_
- _"List all Helm releases and check if any failed"_
- _"Enable Hubble observability on the cluster"_
- _"Show Istio waypoint status"_

---

## Configuration Reference

### A2A Servers

```yaml
servers:
  - name: my-agent          # display name
    type: a2a               # use a2a for kagent agents
    url: https://...        # /api/a2a/kagent/<agent-name>
    auth:                   # optional
      type: bearer
      env_var: MY_TOKEN
```

### MCP Servers (also supported)

```yaml
servers:
  - name: my-mcp-server
    type: mcp               # default if omitted
    url: https://.../sse
    allowed_tools: [tool1, tool2]
    auth:
      type: bearer          # or: secret_key (HMAC-SHA256)
      env_var: MY_TOKEN
```

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
├── mcp_servers.yaml          # Agent configuration
├── system_prompt.txt         # LLM system prompt
├── requirements.txt
└── Makefile
```

---

## Testing

```sh
make test
```

52 unit tests covering A2A client, auth, tool integration, and MCP utilities.

---

## Troubleshooting

### SSL errors

```sh
make certs-macos   # macOS
make certs-linux   # Linux
```

### Agent not responding

- Check the HTTPRoute for `/api/a2a` is accepted by your gateway
- Verify the agent has `a2aConfig.skills` set (see [Kagent Setup](#kagent-setup))
- Confirm `/.well-known/agent.json` is reachable: `curl https://kagent.example.com/api/a2a/kagent/k8s-agent/.well-known/agent.json`

---

## Contributing

Contributions are welcome! Please open an issue first for major changes.

1. Fork the repo
2. Create a branch: `git checkout -b my-feature`
3. Commit your changes
4. Open a Pull Request

---

## License

[MIT License](LICENSE)

---

## Acknowledgements

- [kagent](https://kagent.dev/) — the Kubernetes-native AI agent framework this project is built for
- [LiveKit Agents](https://docs.livekit.io/agents/) — voice agent framework
- [OpenAI](https://openai.com/) — Whisper STT and GPT-4.1
- [ElevenLabs](https://elevenlabs.io/) — text-to-speech
- [Silero VAD](https://github.com/snakers4/silero-vad) — voice activity detection
- [A2A Protocol](https://google.github.io/A2A/) — agent interoperability standard
- DeepLearning.AI course: [Building AI Voice Agents for Production](https://www.deeplearning.ai/short-courses/building-ai-voice-agents-for-production/)
