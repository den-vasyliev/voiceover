"""
a2a.py

Provides the A2AServerConfig class for A2A server integration and the send_a2a_task function for sending tasks to A2A agents.
"""

import requests
import uuid
import httpx

class A2AServerConfig:
    """
    Represents an A2A server configuration for tool integration.
    Provides methods to list available tools and connect (no-op).
    """
    def __init__(self, base_url, headers, name):
        self.type = "a2a"
        self.base_url = base_url
        self.headers = headers
        self.name = name

    async def list_tools(self):
        """
        Fetch the list of available skills/tools from the A2A agent.
        Returns a list of skills.
        """
        agent_card_url = f"{self.base_url}/.well-known/agent.json"
        async with httpx.AsyncClient() as client:
            response = await client.get(agent_card_url, headers=self.headers, timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to get agent card: {response.status_code}")
        agent_card = response.json()
        return agent_card.get("skills", [])

    async def connect(self):
        """
        No-op for A2A servers, required for interface compatibility.
        """
        return

def send_a2a_task(agent_base_url, user_text):
    """
    Send a task to an A2A agent and return the agent's reply as text.
    Raises RuntimeError on failure or incomplete response.
    """
    agent_card_url = f"{agent_base_url}/.well-known/agent.json"
    response = requests.get(agent_card_url, timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to get agent card: {response.status_code}")
    # agent_card = response.json()  # Not used further

    task_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    task_payload = {
        "id": task_id,
        "sessionId": session_id,
        "acceptedOutputModes": ["text"],
        "message": {
            "role": "user",
            "parts": [
                {"type": "text", "text": user_text}
            ]
        }
    }
    jsonrpc_payload = {
        "jsonrpc": "2.0",
        "id": task_id,
        "method": "tasks/send",
        "params": task_payload
    }

    tasks_send_url = f"{agent_base_url}/tasks/send"
    result = requests.post(tasks_send_url, json=jsonrpc_payload, timeout=10)
    if result.status_code != 200:
        raise RuntimeError(f"Task request failed: {result.status_code}, {result.text}")
    task_response = result.json()
    result_obj = task_response.get("result", {})

    if result_obj.get("status", {}).get("state") == "completed":
        messages = result_obj.get("messages", [])
        if not messages and "status" in result_obj and "message" in result_obj["status"]:
            agent_message = result_obj["status"]["message"]
            messages = [agent_message]
        if messages:
            agent_message = messages[-1]
            agent_reply_text = ""
            for part in agent_message.get("parts", []):
                if "text" in part:
                    agent_reply_text += part["text"]
            return agent_reply_text
        else:
            return "No messages in response!"
    else:
        return f"Task did not complete. Status: {result_obj.get('status')}" 