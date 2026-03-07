"""
Tests for MCP server auth configuration in main.py entrypoint.
Patches LiveKit and server dependencies to test the auth wiring in isolation.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_conf(auth_type, env_var):
    return {
        "name": "test-server",
        "type": "mcp",
        "url": "https://example.com/sse",
        "auth": {"type": auth_type, "env_var": env_var},
    }


def _make_fake_ctx():
    fake_ctx = MagicMock()
    fake_ctx.connect = AsyncMock()
    fake_ctx.room = MagicMock()
    return fake_ctx


def _make_fake_agent():
    fake_agent = MagicMock()
    fake_agent._tools = []
    fake_agent.speak = AsyncMock()
    return fake_agent


async def _run_entrypoint(conf, monkeypatch, env_value=None):
    """
    Runs entrypoint() with a single server config.
    Returns the MCPServerSse params captured during construction.
    """
    env_var = conf.get("auth", {}).get("env_var")
    if env_var:
        if env_value is not None:
            monkeypatch.setenv(env_var, env_value)
        else:
            monkeypatch.delenv(env_var, raising=False)

    captured = {}

    class FakeMCPServerSse:
        def __init__(self, params, cache_tools_list=True, name=None, sampling_llm=None):
            captured.update(params)
            self.name = name

        async def connect(self):
            pass

    fake_session = MagicMock()
    fake_session.start = AsyncMock()

    with patch("main.load_mcp_config", return_value=[conf]), \
         patch("main.create_llm", return_value=MagicMock()), \
         patch("main.MCPServerSse", FakeMCPServerSse), \
         patch("main.MCPClient"), \
         patch("main.A2AServerConfig"), \
         patch("main.MCPToolsIntegration.create_agent_with_tools",
               new_callable=AsyncMock, return_value=_make_fake_agent()), \
         patch("main.MCPToolsIntegration.prepare_dynamic_tools",
               new_callable=AsyncMock, return_value=[]), \
         patch("main.AgentSession", return_value=fake_session):
        from main import entrypoint
        await entrypoint(_make_fake_ctx())

    return captured


# ─── bearer auth ─────────────────────────────────────────────────────────────

async def test_bearer_sets_authorization_header(monkeypatch):
    params = await _run_entrypoint(_make_conf("bearer", "MY_TOKEN"), monkeypatch, "secret123")
    assert params["headers"]["Authorization"] == "Bearer secret123"


async def test_bearer_missing_token_omits_header(monkeypatch):
    params = await _run_entrypoint(_make_conf("bearer", "MY_TOKEN"), monkeypatch, None)
    assert "Authorization" not in params.get("headers", {})


# ─── secret_key auth ─────────────────────────────────────────────────────────

async def test_secret_key_uses_mcp_client(monkeypatch):
    conf = _make_conf("secret_key", "MY_HMAC_KEY")
    monkeypatch.setenv("MY_HMAC_KEY", "hmackey")

    fake_server = MagicMock()
    fake_server.name = "test-server"
    fake_server.connect = AsyncMock()
    fake_client = MagicMock()
    fake_client.server = fake_server
    fake_session = MagicMock()
    fake_session.start = AsyncMock()

    with patch("main.load_mcp_config", return_value=[conf]), \
         patch("main.create_llm", return_value=MagicMock()), \
         patch("main.MCPClient", return_value=fake_client) as mock_mcp_client, \
         patch("main.MCPServerSse") as mock_sse, \
         patch("main.A2AServerConfig"), \
         patch("main.MCPToolsIntegration.create_agent_with_tools",
               new_callable=AsyncMock, return_value=_make_fake_agent()), \
         patch("main.MCPToolsIntegration.prepare_dynamic_tools",
               new_callable=AsyncMock, return_value=[]), \
         patch("main.AgentSession", return_value=fake_session):
        from main import entrypoint
        await entrypoint(_make_fake_ctx())

    mock_mcp_client.assert_called_once_with(
        url="https://example.com/sse",
        secret_key="hmackey",
        headers={},
        name="test-server",
    )
    mock_sse.assert_not_called()


# ─── no auth ──────────────────────────────────────────────────────────────────

async def test_no_auth_creates_plain_sse_server(monkeypatch):
    conf = {"name": "plain", "type": "mcp", "url": "https://example.com/sse"}
    params = await _run_entrypoint(conf, monkeypatch)
    assert "Authorization" not in params.get("headers", {})
    assert params["url"] == "https://example.com/sse"
