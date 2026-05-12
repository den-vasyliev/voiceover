import os
import re

import google.auth
import yaml
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.apps import App
from google.adk.events import Event
from google.adk.models import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types
from google.genai.types import Content, Part

_, project_id = google.auth.default()
if project_id:
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "europe-west4")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")

with open(_CONFIG_PATH) as f:
    _servers = yaml.safe_load(f).get("servers", [])


def _expand_env(value: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def _build_headers(server: dict) -> dict:
    headers = {}
    auth = server.get("auth", {})
    if auth.get("type") == "bearer":
        token = os.environ.get(auth.get("env_var", ""), "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    for k, v in server.get("headers", {}).items():
        headers[k] = _expand_env(v)
    return headers


def _recover_from_history(task) -> str | None:
    """Extract tool output from kagent history when state=failed.

    kagent marks tasks failed due to LLM API errors even when the underlying
    tool ran successfully. The result is in function_response parts in history.
    """
    history = task.history or []

    for msg in reversed(history):
        if getattr(msg, "role", None) != "agent":
            continue
        if (getattr(msg, "metadata", None) or {}).get("kagent_error_code") == "API_ERROR":
            continue
        for part in getattr(msg, "parts", []) or []:
            if getattr(part, "kind", None) == "text" and getattr(part, "text", None):
                return part.text

    for msg in history:
        for part in getattr(msg, "parts", []) or []:
            if getattr(part, "kind", None) != "data":
                continue
            if (getattr(part, "metadata", None) or {}).get("kagent_type") != "function_response":
                continue
            response = (getattr(part, "data", None) or {}).get("response", {})
            if response.get("isError"):
                continue
            for content in response.get("content", []):
                if content.get("type") == "text" and content.get("text"):
                    return content["text"]

    return None


class KagentRemoteA2aAgent(RemoteA2aAgent):
    """RemoteA2aAgent subclass that recovers results from kagent's failed tasks."""

    async def _handle_a2a_response(self, a2a_response, ctx) -> Event | None:
        if isinstance(a2a_response, tuple):
            task, update = a2a_response
            if (
                update is None
                and task is not None
                and task.status is not None
                and str(task.status.state) in ("TaskState.failed", "failed")
            ):
                text = _recover_from_history(task)
                if text:
                    return Event(
                        author=self.name,
                        invocation_id=ctx.invocation_id,
                        branch=ctx.branch,
                        content=Content(parts=[Part(text=text)]),
                    )
        return await super()._handle_a2a_response(a2a_response, ctx)


_a2a_tools: list = [
    AgentTool(
        KagentRemoteA2aAgent(
            name=s["name"].replace("-", "_"),
            description=f"A2A agent: {s['name']}",
            agent_card=f"{s['url'].rstrip('/')}/.well-known/agent.json",
        )
    )
    for s in _servers
    if s.get("type") == "a2a"
]

_mcp_toolsets: list = [
    McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=s["url"],
            headers=_build_headers(s),
        ),
        tool_filter=s.get("allowed_tools") or None,
    )
    for s in _servers
    if s.get("type") == "mcp"
]

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-live-2.5-flash-native-audio",
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
            )
        ),
    ),
    instruction="You are a helpful voice assistant for Kubernetes operations. Use available tools for any cluster questions. Answer concisely and clearly.",
    tools=[*_a2a_tools, *_mcp_toolsets],
)

app = App(
    root_agent=root_agent,
    name="adk_agent",
)
