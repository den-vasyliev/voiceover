import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from a2a import A2AServerConfig
from tool_integration import filtered_prepare_dynamic_tools


# ─── helpers ──────────────────────────────────────────────────────────────────

def _a2a_server(name="agent", skills=None):
    server = A2AServerConfig(base_url="http://agent.example.com", headers={}, name=name)
    server.list_tools = AsyncMock(return_value=skills or [])
    return server


def _mcp_server(name="mcp-srv", tools=None):
    """Plain mock — NOT an A2AServerConfig instance."""
    server = MagicMock()
    server.name = name
    server.list_tools = AsyncMock(return_value=tools or [])
    return server


def _mcp_tool(name: str):
    t = MagicMock()
    t.name = name
    return t


# ─── A2A branch ───────────────────────────────────────────────────────────────

async def test_a2a_skills_create_one_tool_each():
    skills = [{"name": "summarise", "description": "d1"}, {"name": "translate", "description": "d2"}]
    server = _a2a_server(skills=skills)
    sentinel = MagicMock()

    with patch(
        "tool_integration.MCPToolsIntegration._create_decorated_tool",
        return_value=sentinel,
    ) as mock_create:
        result = await filtered_prepare_dynamic_tools([server], {})

    assert len(result) == 2
    assert mock_create.call_count == 2
    assert all(r is sentinel for r in result)


async def test_a2a_tool_name_sanitized():
    skills = [{"name": "my skill: v2", "description": ""}]
    server = _a2a_server(skills=skills)
    captured = []

    def capture(ft):
        captured.append(ft)
        return MagicMock()

    with patch("tool_integration.MCPToolsIntegration._create_decorated_tool", side_effect=capture):
        await filtered_prepare_dynamic_tools([server], {})

    assert captured[0].name == "my_skill__v2"


async def test_a2a_skill_name_falls_back_to_id():
    skills = [{"id": "skill-99", "description": ""}]
    server = _a2a_server(skills=skills)
    captured = []

    def capture(ft):
        captured.append(ft)
        return MagicMock()

    with patch("tool_integration.MCPToolsIntegration._create_decorated_tool", side_effect=capture):
        await filtered_prepare_dynamic_tools([server], {})

    assert captured[0].name == "skill-99"


async def test_a2a_allowed_tools_map_has_no_effect():
    """allowed_tools_map is ignored for A2A servers — all skills pass through."""
    skills = [{"name": "tool_a"}, {"name": "tool_b"}]
    server = _a2a_server(name="myagent", skills=skills)

    with patch(
        "tool_integration.MCPToolsIntegration._create_decorated_tool",
        return_value=MagicMock(),
    ) as mock_create:
        result = await filtered_prepare_dynamic_tools([server], {"myagent": {"tool_a"}})

    assert mock_create.call_count == 2


async def test_a2a_on_invoke_tool_calls_send_task_async():
    """The generated on_invoke_tool delegate calls send_task_async with the prompt."""
    skills = [{"name": "run", "description": ""}]
    server = _a2a_server(skills=skills)
    server.send_task_async = AsyncMock(return_value="done")
    captured = []

    def capture(ft):
        captured.append(ft)
        return MagicMock()

    with patch("tool_integration.MCPToolsIntegration._create_decorated_tool", side_effect=capture):
        await filtered_prepare_dynamic_tools([server], {})

    result = await captured[0].on_invoke_tool(None, '{"prompt": "do it"}')
    server.send_task_async.assert_awaited_once_with("do it")
    assert result == "done"


# ─── MCP branch ───────────────────────────────────────────────────────────────

async def test_mcp_allowed_filter_applied():
    tools = [_mcp_tool("list_pods"), _mcp_tool("delete_pod"), _mcp_tool("list_nodes")]
    server = _mcp_server(name="k8s", tools=tools)

    with patch("tool_integration.MCPUtil.to_function_tool", return_value=MagicMock()) as mock_to_ft, \
         patch("tool_integration.MCPToolsIntegration._create_decorated_tool", return_value=MagicMock()):
        await filtered_prepare_dynamic_tools([server], {"k8s": {"list_*"}})

    assert mock_to_ft.call_count == 2
    called_names = {call.args[0].name for call in mock_to_ft.call_args_list}
    assert called_names == {"list_pods", "list_nodes"}


async def test_mcp_no_filter_includes_all_tools():
    tools = [_mcp_tool("alpha"), _mcp_tool("beta")]
    server = _mcp_server(tools=tools)

    with patch("tool_integration.MCPUtil.to_function_tool", return_value=MagicMock()) as mock_to_ft, \
         patch("tool_integration.MCPToolsIntegration._create_decorated_tool", return_value=MagicMock()):
        await filtered_prepare_dynamic_tools([server], {})

    assert mock_to_ft.call_count == 2


async def test_mcp_create_decorated_tool_exception_skips_tool():
    """Exception in _create_decorated_tool skips that tool but continues."""
    tools = [_mcp_tool("good"), _mcp_tool("bad")]
    server = _mcp_server(tools=tools)
    call_n = [0]

    def create_side(ft):
        call_n[0] += 1
        if call_n[0] == 2:
            raise RuntimeError("decoration failed")
        return MagicMock()

    with patch("tool_integration.MCPUtil.to_function_tool", side_effect=[MagicMock(), MagicMock()]), \
         patch("tool_integration.MCPToolsIntegration._create_decorated_tool", side_effect=create_side):
        result = await filtered_prepare_dynamic_tools([server], {})

    assert len(result) == 1
