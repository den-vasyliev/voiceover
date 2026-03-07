"""
a2a.py

Provides the A2AServerConfig class for A2A server integration.
"""

import asyncio
import json
import uuid
import httpx
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class TaskState(Enum):
    """A2A task states as defined in the protocol."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

def _extract_parts_text(parts: List[Dict[str, Any]]) -> str:
    """Extract concatenated text from A2A message parts."""
    return "".join(
        part["text"]
        for part in parts
        if part.get("kind") == "text" and "text" in part
    )


class A2AError(Exception):
    """Base exception for A2A protocol errors."""
    pass

class A2AConnectionError(A2AError):
    """Raised when connection to A2A agent fails."""
    pass

class A2ATaskError(A2AError):
    """Raised when task execution fails."""
    pass

class A2AServerConfig:
    """
    Represents an A2A server configuration for tool integration.
    Provides methods to list available tools and connect (no-op).
    Refactored for Google ADK compatibility with improved error handling.
    """
    def __init__(self, base_url: str, headers: Optional[Dict[str, str]], name: str):
        self.type = "a2a"
        self.base_url = base_url.rstrip('/')
        self.headers = headers or {}
        self.name = name
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an async HTTP client with improved timeout configuration."""
        if self._client is None:
            # Use more granular timeout configuration
            timeout = httpx.Timeout(
                connect=10.0,  # Connection timeout
                read=60.0,     # Read timeout (increased for long-running tasks)
                write=10.0,    # Write timeout
                pool=5.0       # Pool timeout
            )
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                follow_redirects=True
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        Fetch the list of available skills/tools from the A2A agent.
        Returns a list of skills with improved error handling.
        """
        agent_card_url = f"{self.base_url}/.well-known/agent.json"
        
        try:
            client = await self._get_client()
            response = await client.get(agent_card_url, headers=self.headers)
            
            if response.status_code != 200:
                raise A2AConnectionError(
                    f"Failed to get agent card: {response.status_code} - {response.text}"
                )
            
            agent_card = response.json()
            skills = agent_card.get("skills", [])
            
            logger.info(f"Retrieved {len(skills)} skills from A2A agent {self.name}")
            return skills
            
        except httpx.RequestError as e:
            raise A2AConnectionError(f"Network error connecting to A2A agent: {e}")
        except json.JSONDecodeError as e:
            raise A2AConnectionError(f"Invalid JSON response from agent card: {e}")

    async def connect(self):
        """
        No-op for A2A servers, required for interface compatibility.
        """
        return

    async def send_task_async(self, user_text: str, session_id: Optional[str] = None, max_retries: int = 2) -> str:
        """
        Send a task to an A2A agent asynchronously and return the agent's reply as text.
        Updated to use the correct A2A protocol based on Google ADK documentation.
        Includes retry logic for handling temporary network issues.
        """
        if not session_id:
            session_id = str(uuid.uuid4())
        
        task_id = str(uuid.uuid4())
        
        # Create message following A2A protocol
        # Based on testing, A2A uses message/send with parts using "kind" field
        message_payload = {
            "message": {
                "role": "user",
                "parts": [
                    {"kind": "text", "text": user_text}
                ]
            }
        }
        
        jsonrpc_payload = {
            "jsonrpc": "2.0",
            "id": task_id,
            "method": "message/send",
            "params": message_payload
        }
        
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                client = await self._get_client()
                # Try the main A2A endpoint first
                a2a_url = f"{self.base_url}/"
                
                logger.info(f"Sending A2A message to {a2a_url} (attempt {attempt + 1}/{max_retries + 1})")
                response = await client.post(
                    a2a_url, 
                    json=jsonrpc_payload, 
                    headers=self.headers
                )
                
                logger.info(f"A2A response status: {response.status_code}")
                
                if response.status_code != 200:
                    raise A2ATaskError(
                        f"Task request failed: {response.status_code} - {response.text}"
                    )
                
                task_response = response.json()
                
                # Check for JSON-RPC errors
                if "error" in task_response:
                    error = task_response["error"]
                    raise A2ATaskError(f"JSON-RPC error: {error.get('message', 'Unknown error')}")
                
                # Process the response - A2A protocol returns task result with artifacts
                result = task_response.get("result", {})
                status = result.get("status", {})

                if status.get("state") == "completed":
                    # Extract response from artifacts
                    for artifact in result.get("artifacts", []):
                        text = _extract_parts_text(artifact.get("parts", []))
                        if text:
                            logger.info(f"A2A response extracted from artifacts: {len(text)} chars")
                            return text

                    # Fallback: check history for most recent agent message
                    for msg in reversed(result.get("history", [])):
                        if msg.get("role") == "agent":
                            text = _extract_parts_text(msg.get("parts", []))
                            if text:
                                logger.info(f"A2A response extracted from history: {len(text)} chars")
                                return text

                    return "Task completed but no response found"
                elif status.get("state") == "failed":
                    error_msg = status.get("message", {})
                    if isinstance(error_msg, dict):
                        error_text = _extract_parts_text(error_msg.get("parts", []))
                        if error_text:
                            raise A2ATaskError(f"Task failed: {error_text}")
                    raise A2ATaskError(f"Task failed: {status}")
                else:
                    return f"Task did not complete. Status: {status}"
                    
            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(f"A2A request timed out (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    logger.error(f"A2A request timed out after {max_retries + 1} attempts")
                    raise A2AConnectionError(f"Request timed out after {max_retries + 1} attempts. The A2A agent may be overloaded or experiencing issues.")
            except httpx.ConnectError as e:
                last_exception = e
                logger.warning(f"A2A connection error (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    logger.error(f"A2A connection failed after {max_retries + 1} attempts")
                    raise A2AConnectionError(f"Failed to connect to A2A agent after {max_retries + 1} attempts: {e}")
            except httpx.RequestError as e:
                last_exception = e
                logger.warning(f"A2A request error (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    logger.error(f"A2A request failed after {max_retries + 1} attempts")
                    raise A2AConnectionError(f"Network error sending task to A2A agent after {max_retries + 1} attempts: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"A2A JSON decode error: {e}")
                raise A2AConnectionError(f"Invalid JSON response from task endpoint: {e}")
            except A2ATaskError:
                # Don't retry task errors, they're not network issues
                raise
        
        # This should never be reached, but just in case
        raise A2AConnectionError(f"Unexpected error after {max_retries + 1} attempts: {last_exception}")
