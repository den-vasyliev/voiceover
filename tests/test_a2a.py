import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from a2a import (
    _extract_parts_text,
    A2AServerConfig,
    A2AConnectionError,
    A2ATaskError,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_server():
    return A2AServerConfig(
        base_url="http://agent.example.com",
        headers={"X-Token": "test"},
        name="test-agent",
    )


def _make_response(status_code: int, body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = json.dumps(body)
    return resp


def _a2a_result(state: str, artifacts=None, history=None, status_message=None) -> dict:
    status = {"state": state}
    if status_message is not None:
        status["message"] = status_message
    result = {"status": status}
    if artifacts is not None:
        result["artifacts"] = artifacts
    if history is not None:
        result["history"] = history
    return {"jsonrpc": "2.0", "id": "x", "result": result}


# ─── _extract_parts_text ──────────────────────────────────────────────────────

def test_extract_parts_text_joins_text_parts():
    parts = [
        {"kind": "text", "text": "hello "},
        {"kind": "data", "text": "ignored"},
        {"kind": "text", "text": "world"},
    ]
    assert _extract_parts_text(parts) == "hello world"


def test_extract_parts_text_empty_list():
    assert _extract_parts_text([]) == ""


def test_extract_parts_text_no_matching_kind():
    assert _extract_parts_text([{"kind": "image", "text": "nope"}]) == ""


def test_extract_parts_text_part_missing_text_key():
    assert _extract_parts_text([{"kind": "text"}]) == ""


# ─── list_tools ───────────────────────────────────────────────────────────────

async def test_list_tools_returns_skills():
    server = _make_server()
    skills = [{"name": "summarise", "description": "Summarise text"}]
    mock_client = AsyncMock()
    mock_client.get.return_value = _make_response(200, {"skills": skills})

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        result = await server.list_tools()

    assert result == skills
    mock_client.get.assert_awaited_once_with(
        "http://agent.example.com/.well-known/agent.json",
        headers={"X-Token": "test"},
    )


async def test_list_tools_non_200_raises_connection_error():
    server = _make_server()
    mock_client = AsyncMock()
    mock_client.get.return_value = _make_response(404, {})

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        with pytest.raises(A2AConnectionError, match="404"):
            await server.list_tools()


async def test_list_tools_network_error_raises_connection_error():
    server = _make_server()
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.ConnectError("refused")

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        with pytest.raises(A2AConnectionError, match="Network error"):
            await server.list_tools()


# ─── send_task_async ──────────────────────────────────────────────────────────

async def test_send_task_artifacts_path():
    server = _make_server()
    artifact = {"parts": [{"kind": "text", "text": "artifact reply"}]}
    body = _a2a_result("completed", artifacts=[artifact])
    mock_client = AsyncMock()
    mock_client.post.return_value = _make_response(200, body)

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        result = await server.send_task_async("hello", max_retries=0)

    assert result == "artifact reply"


async def test_send_task_history_fallback():
    server = _make_server()
    history = [
        {"role": "user",  "parts": [{"kind": "text", "text": "user msg"}]},
        {"role": "agent", "parts": [{"kind": "text", "text": "history reply"}]},
    ]
    body = _a2a_result("completed", artifacts=[], history=history)
    mock_client = AsyncMock()
    mock_client.post.return_value = _make_response(200, body)

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        result = await server.send_task_async("hello", max_retries=0)

    assert result == "history reply"


async def test_send_task_completed_no_content():
    server = _make_server()
    body = _a2a_result("completed", artifacts=[], history=[])
    mock_client = AsyncMock()
    mock_client.post.return_value = _make_response(200, body)

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        result = await server.send_task_async("hello", max_retries=0)

    assert result == "Task completed but no response found"


async def test_send_task_failed_with_parts():
    server = _make_server()
    fail_msg = {"parts": [{"kind": "text", "text": "something went wrong"}]}
    body = _a2a_result("failed", status_message=fail_msg)
    mock_client = AsyncMock()
    mock_client.post.return_value = _make_response(200, body)

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        with pytest.raises(A2ATaskError, match="something went wrong"):
            await server.send_task_async("hello", max_retries=0)


async def test_send_task_failed_plain_status():
    server = _make_server()
    body = _a2a_result("failed", status_message="plain error string")
    mock_client = AsyncMock()
    mock_client.post.return_value = _make_response(200, body)

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        with pytest.raises(A2ATaskError, match="Task failed"):
            await server.send_task_async("hello", max_retries=0)


async def test_send_task_timeout_retried_then_raises():
    server = _make_server()
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.TimeoutException("timed out")

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        with patch("a2a.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(A2AConnectionError, match="timed out"):
                await server.send_task_async("hello", max_retries=2)

    assert mock_client.post.await_count == 3
    assert mock_sleep.await_count == 2


async def test_send_task_connect_error_retried_then_raises():
    server = _make_server()
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        with patch("a2a.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(A2AConnectionError, match="Failed to connect"):
                await server.send_task_async("hello", max_retries=1)

    assert mock_client.post.await_count == 2
    assert mock_sleep.await_count == 1


async def test_send_task_rpc_error_not_retried():
    server = _make_server()
    body = {"jsonrpc": "2.0", "id": "x", "error": {"message": "RPC error"}}
    mock_client = AsyncMock()
    mock_client.post.return_value = _make_response(200, body)

    with patch.object(server, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        with pytest.raises(A2ATaskError, match="RPC error"):
            await server.send_task_async("hello", max_retries=2)

    assert mock_client.post.await_count == 1
