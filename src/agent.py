# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import os
import sys
from zoneinfo import ZoneInfo

import google.auth
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

# Allow importing from the project src for the A2A client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_, project_id = google.auth.default()
if project_id:
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "europe-west4")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")


def get_weather(query: str) -> str:
    """Get simulated weather for a location.

    Args:
        query: City or location name.

    Returns:
        Weather description string.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Get the current time for a city.

    Args:
        query: City name.

    Returns:
        Current time string for the city.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time in {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


from a2a import A2AServerConfig  # noqa: E402

_k8s_a2a = A2AServerConfig(
    base_url="https://agentgateway.example.com/api/a2a/kagent/k8s-agent",
    headers={},
    name="k8s_agent",
)


async def kubernetes_operations(query: str) -> str:
    """Perform Kubernetes cluster operations: list/describe resources, get logs, check events, troubleshoot pods.

    Args:
        query: Natural language request for the Kubernetes agent.

    Returns:
        Result from the Kubernetes agent.
    """
    return await _k8s_a2a.send_task_async(query)


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
    instruction="You are a helpful voice assistant for Kubernetes operations. Use the kubernetes_operations tool for any cluster questions. Answer concisely and clearly.",
    tools=[kubernetes_operations, get_weather, get_current_time],
)

app = App(
    root_agent=root_agent,
    name="src",
)
