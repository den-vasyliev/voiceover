import os

import google.auth
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import AgentTool
from google.genai import types

_, project_id = google.auth.default()
if project_id:
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "europe-west4")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

# A2A remote agents
k8s_agent = RemoteA2aAgent(
    name="k8s_agent",
    description="Kubernetes cluster operations: list/describe resources, get logs, check events, troubleshoot pods.",
    agent_card="https://agentgateway.example.com/api/a2a/kagent/k8s-agent/.well-known/agent.json",
)

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
    instruction="You are a helpful voice assistant for Kubernetes operations. Use the k8s_agent tool for any cluster questions. Answer concisely and clearly.",
    tools=[AgentTool(k8s_agent)],
)

app = App(
    root_agent=root_agent,
    name="adk_agent",
)
