import json
from typing import Any, Dict, List

# Import from mcp libraries
from mcp.types import Tool as MCPTool, CallToolResult


def _normalize_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively ensure all object schemas have additionalProperties: false (required by OpenAI)."""
    if not isinstance(schema, dict):
        return schema
    schema = dict(schema)
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)
        schema.setdefault("properties", {})
        schema["properties"] = {
            k: _normalize_schema(v) for k, v in schema["properties"].items()
        }
    if "items" in schema:
        schema["items"] = _normalize_schema(schema["items"])
    if "anyOf" in schema:
        schema["anyOf"] = [_normalize_schema(s) for s in schema["anyOf"]]
    if "oneOf" in schema:
        schema["oneOf"] = [_normalize_schema(s) for s in schema["oneOf"]]
    return schema


# A minimal FunctionTool class used by the agent.
class FunctionTool:
    def __init__(self, name: str, description: str, params_json_schema: Dict[str, Any], on_invoke_tool, strict_json_schema: bool = False):
        self.name = name
        self.description = description
        self.params_json_schema = params_json_schema
        self.on_invoke_tool = on_invoke_tool  # This should be an async function.
        self.strict_json_schema = strict_json_schema

    def __repr__(self):
        return f"FunctionTool(name={self.name})"

class MCPUtil:
    @classmethod
    async def get_function_tools(cls, server, convert_schemas_to_strict: bool) -> List[FunctionTool]:
        tools = await server.list_tools()
        function_tools = []
        for tool in tools:
            ft = cls.to_function_tool(tool, server, convert_schemas_to_strict)
            function_tools.append(ft)
        return function_tools

    @classmethod
    def to_function_tool(cls, tool, server, convert_schemas_to_strict: bool) -> FunctionTool:
        schema = _normalize_schema(tool.inputSchema)

        # Use a default argument to capture the current tool correctly in the closure
        async def invoke_tool(context: Any, input_json: str, current_tool_name=tool.name) -> str:
            try:
                arguments = json.loads(input_json) if input_json else {}
            except Exception as e:
                # Return error message as string
                return f"Error parsing input JSON for tool '{current_tool_name}': {e}"
            try:
                result = await server.call_tool(current_tool_name, arguments)
                # Ensure the final return value is a string
                if "content" in result and isinstance(result["content"], list) and len(result["content"]) >= 1:
                     # Handle single or multiple content items - convert to string
                     if len(result["content"]) == 1:
                         content_item = result["content"][0]
                         # Convert simple types explicitly to string
                         if isinstance(content_item, (str, int, float, bool)):
                             return str(content_item)
                         # Convert complex types (like dict, list) to JSON string
                         else:
                             try:
                                 return json.dumps(content_item)
                             except TypeError:
                                 return str(content_item) # Fallback to default string representation
                     else:
                         # Multiple content items, return as JSON array string
                          try:
                              return json.dumps(result["content"])
                          except TypeError:
                              return str(result["content"]) # Fallback
                else:
                    # If 'content' is missing, not a list, or empty, return string representation of the whole result
                    try:
                        return json.dumps(result)
                    except TypeError:
                        return str(result) # Fallback
            except Exception as e:
                 # Catch errors during tool call itself
                 return f"Error calling tool '{current_tool_name}': {e}"

        return FunctionTool(
            name=tool.name,
            description=tool.description,
            params_json_schema=schema,
            on_invoke_tool=invoke_tool,
            strict_json_schema=convert_schemas_to_strict,
        )