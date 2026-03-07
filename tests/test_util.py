import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_client.util import FunctionTool, MCPUtil, _normalize_schema


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_mcp_tool(name="my_tool", description="A tool", schema=None):
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.inputSchema = schema or {"type": "object", "properties": {}}
    return tool


def _make_server(return_value=None):
    server = MagicMock()
    server.call_tool = AsyncMock(return_value=return_value or {})
    return server


# ─── FunctionTool construction ────────────────────────────────────────────────

def test_to_function_tool_sets_attributes():
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    ft = MCPUtil.to_function_tool(
        _make_mcp_tool(name="search", description="Search docs", schema=schema),
        _make_server(),
        convert_schemas_to_strict=False,
    )
    assert ft.name == "search"
    assert ft.description == "Search docs"
    assert ft.params_json_schema["type"] == "object"
    assert ft.strict_json_schema is False


def test_to_function_tool_strict_flag_propagated():
    ft = MCPUtil.to_function_tool(_make_mcp_tool(), _make_server(), convert_schemas_to_strict=True)
    assert ft.strict_json_schema is True


# ─── invoke_tool: JSON parse error ───────────────────────────────────────────

async def test_invoke_tool_json_parse_error_returns_message():
    ft = MCPUtil.to_function_tool(_make_mcp_tool(name="t"), _make_server(), False)
    result = await ft.on_invoke_tool(None, "{bad json")
    assert "Error parsing input JSON" in result
    assert "'t'" in result


# ─── invoke_tool: content result variants ────────────────────────────────────

async def test_invoke_tool_single_string_content():
    ft = MCPUtil.to_function_tool(_make_mcp_tool(), _make_server({"content": ["hello"]}), False)
    assert await ft.on_invoke_tool(None, "{}") == "hello"


async def test_invoke_tool_single_int_content():
    ft = MCPUtil.to_function_tool(_make_mcp_tool(), _make_server({"content": [42]}), False)
    assert await ft.on_invoke_tool(None, "{}") == "42"


async def test_invoke_tool_single_dict_content():
    ft = MCPUtil.to_function_tool(_make_mcp_tool(), _make_server({"content": [{"key": "val"}]}), False)
    assert await ft.on_invoke_tool(None, "{}") == json.dumps({"key": "val"})


async def test_invoke_tool_multiple_content_items():
    ft = MCPUtil.to_function_tool(_make_mcp_tool(), _make_server({"content": ["a", "b"]}), False)
    assert await ft.on_invoke_tool(None, "{}") == json.dumps(["a", "b"])


async def test_invoke_tool_empty_content_list_returns_full_result():
    full = {"content": []}
    ft = MCPUtil.to_function_tool(_make_mcp_tool(), _make_server(full), False)
    assert await ft.on_invoke_tool(None, "{}") == json.dumps(full)


async def test_invoke_tool_missing_content_key_returns_full_result():
    full = {"data": "some output"}
    ft = MCPUtil.to_function_tool(_make_mcp_tool(), _make_server(full), False)
    assert await ft.on_invoke_tool(None, "{}") == json.dumps(full)


# ─── invoke_tool: empty input treated as empty dict ──────────────────────────

async def test_invoke_tool_empty_input_calls_with_empty_dict():
    server = _make_server({"content": ["ok"]})
    ft = MCPUtil.to_function_tool(_make_mcp_tool(name="t"), server, False)
    await ft.on_invoke_tool(None, "")
    server.call_tool.assert_awaited_once_with("t", {})


# ─── invoke_tool: call_tool raises exception ─────────────────────────────────

async def test_invoke_tool_call_tool_exception_returns_error_string():
    server = _make_server()
    server.call_tool.side_effect = RuntimeError("server exploded")
    ft = MCPUtil.to_function_tool(_make_mcp_tool(name="boom"), server, False)
    result = await ft.on_invoke_tool(None, "{}")
    assert "Error calling tool 'boom'" in result
    assert "server exploded" in result


# ─── _normalize_schema ────────────────────────────────────────────────────────

def test_normalize_schema_adds_additional_properties_to_object():
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    result = _normalize_schema(schema)
    assert result["additionalProperties"] is False


def test_normalize_schema_does_not_override_existing_additional_properties():
    schema = {"type": "object", "additionalProperties": True}
    result = _normalize_schema(schema)
    assert result["additionalProperties"] is True


def test_normalize_schema_recurses_into_properties():
    schema = {
        "type": "object",
        "properties": {
            "config": {"type": "object", "properties": {"key": {"type": "string"}}}
        },
    }
    result = _normalize_schema(schema)
    assert result["properties"]["config"]["additionalProperties"] is False


def test_normalize_schema_recurses_into_array_items():
    schema = {"type": "array", "items": {"type": "object", "properties": {}}}
    result = _normalize_schema(schema)
    assert result["items"]["additionalProperties"] is False


def test_normalize_schema_adds_empty_properties_when_missing():
    schema = {"type": "object"}
    result = _normalize_schema(schema)
    assert result["properties"] == {}
    assert result["additionalProperties"] is False


def test_normalize_schema_non_object_unchanged():
    schema = {"type": "string"}
    result = _normalize_schema(schema)
    assert result == {"type": "string"}
    assert "additionalProperties" not in result


def test_normalize_schema_applied_on_tool_schema():
    nested_schema = {
        "type": "object",
        "properties": {
            "config": {"type": "object", "properties": {"env": {"type": "string"}}}
        },
    }
    ft = MCPUtil.to_function_tool(_make_mcp_tool(schema=nested_schema), _make_server(), False)
    assert ft.params_json_schema["additionalProperties"] is False
    assert ft.params_json_schema["properties"]["config"]["additionalProperties"] is False
