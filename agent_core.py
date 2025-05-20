"""
agent_core.py

Defines the FunctionAgent class, a LiveKit agent that uses MCP tools from one or more MCP servers. Handles LLM, STT, TTS, and VAD configuration, and customizes tool call behavior for voice interaction.
"""

import os
import logging
from livekit.agents.voice import Agent
from livekit.agents.llm import ChatChunk
from livekit.plugins import openai, silero, elevenlabs

class FunctionAgent(Agent):
    """
    A LiveKit agent that uses MCP tools from one or more MCP servers.

    This agent is configured for voice interaction and integrates with MCP tools for task execution.
    It customizes the LLM, STT, TTS, and VAD components, and overrides the llm_node method to provide
    user feedback when a tool call is detected.
    """

    def __init__(self):
        # Load system prompt from file if present, else from env, else use a minimal default
        prompt_path = os.environ.get("AGENT_SYSTEM_PROMPT_FILE", "system_prompt.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r") as f:
                instructions = f.read()
        else:
            instructions = os.environ.get("AGENT_SYSTEM_PROMPT", "You are a helpful assistant communicating through voice. Use the available MCP tools to answer questions.")
        # Make LLM model and backend configurable via env var
        llm_model = os.environ.get("AGENT_LLM_MODEL", "gpt-4.1-mini")
        llm_backend = os.environ.get("AGENT_LLM_BACKEND", "openai")  # 'openai' or 'ollama'
        if llm_backend == "ollama":
            llm = openai.LLM.with_ollama(
                model=llm_model,
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            )
        else:
            llm = openai.LLM(model=llm_model, timeout=60)
        super().__init__(
            instructions=instructions,
            stt=openai.STT(),
            llm=llm,
            tts=elevenlabs.TTS(),
            vad=silero.VAD.load(),
            allow_interruptions=True
        )

    async def llm_node(self, chat_ctx, tools, model_settings):
        """Override the llm_node to say a message when a tool call is detected."""
        activity = self._activity
        tool_call_detected = False

        # Get the original response from the parent class
        async for chunk in super().llm_node(chat_ctx, tools, model_settings):
            # Check if this chunk contains a tool call
            if isinstance(chunk, ChatChunk) and chunk.delta and chunk.delta.tool_calls and not tool_call_detected:
                # Say the checking message only once when we detect the first tool call
                tool_call_detected = True
                activity.say("Sure, I'll check that for you.")

            yield chunk 