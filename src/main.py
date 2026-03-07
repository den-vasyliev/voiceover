"""
main.py

Main entrypoint for the agent. Handles server setup, configuration loading, and orchestration of the agent lifecycle.
"""

import os
import logging
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.voice import AgentSession
from mcp_client import MCPClient, MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration
from agent_core import FunctionAgent, create_llm
from mcp_config import load_mcp_config, expand_env_vars
from a2a import A2AServerConfig
from tool_integration import filtered_prepare_dynamic_tools
import asyncio

async def _fetch_server_prompts(servers) -> str:
    """Fetch all prompts from MCP servers and return them as a formatted string."""
    sections = []
    for server in servers:
        if not hasattr(server, "list_prompts"):
            continue
        try:
            prompts = await server.list_prompts()
        except Exception as e:
            logging.warning(f"Could not list prompts from '{getattr(server, 'name', '')}': {e}")
            continue
        for prompt in prompts:
            # Skip prompts that require arguments — they need runtime context
            required_args = [a for a in (prompt.arguments or []) if getattr(a, "required", False)]
            if required_args:
                logging.debug(f"Skipping prompt '{prompt.name}' from '{server.name}' (requires args: {[a.name for a in required_args]})")
                continue
            try:
                result = await server.get_prompt(prompt.name)
                text_parts = []
                for msg in result.messages:
                    content = msg.content
                    if hasattr(content, "text"):
                        text_parts.append(content.text)
                if text_parts:
                    sections.append(f"### {prompt.name}\n" + "\n".join(text_parts))
                    logging.info(f"Loaded prompt '{prompt.name}' from '{server.name}'")
            except Exception as e:
                logging.warning(f"Could not get prompt '{prompt.name}' from '{getattr(server, 'name', '')}': {e}")
    return "\n\n".join(sections)


async def entrypoint(ctx: JobContext):
    """
    Main entrypoint for the LiveKit agent application.
    Loads configuration, sets up MCP and A2A servers, prepares tools, and starts the agent session.
    """
    # Create LLM once — shared between the agent and MCP sampling callbacks
    llm = create_llm()

    # Load MCP server configs
    mcp_configs = load_mcp_config()
    mcp_servers = []
    allowed_tools_map = {}
    
    for conf in mcp_configs:
        server_type = conf.get("type", "mcp")
        headers = {}
        for k, v in conf.get("headers", {}).items():
            headers[k] = expand_env_vars(v)
        server_name = conf.get("name", "")
        server_url = conf["url"]

        if server_type == "mcp":
            if "auth" in conf:
                auth_type = conf["auth"].get("type", "")
                env_var_name = conf["auth"].get("env_var", "")
                token = os.environ.get(env_var_name, "")
                if not token:
                    logging.warning(f"{env_var_name} not set, authentication will not be used for {server_name}")
                if auth_type == "bearer" and token:
                    headers["Authorization"] = f"Bearer {token}"
                    logging.info(f"MCP server '{server_name}' Authorization header set from {env_var_name}")
                    server = MCPServerSse(
                        params={"url": server_url, "headers": headers},
                        cache_tools_list=True,
                        name=server_name,
                        sampling_llm=llm,
                    )
                elif auth_type == "secret_key" and token:
                    logging.info(f"Using {env_var_name} for HMAC authentication with {server_name}")
                    client = MCPClient(
                        url=server_url,
                        secret_key=token,
                        headers=headers,
                        name=server_name
                    )
                    server = client.server
                else:
                    server = MCPServerSse(
                        params={"url": server_url, "headers": headers},
                        cache_tools_list=True,
                        name=server_name,
                        sampling_llm=llm,
                    )
            else:
                server = MCPServerSse(
                    params={"url": server_url, "headers": headers},
                    cache_tools_list=True,
                    name=server_name,
                    sampling_llm=llm,
                )
        elif server_type == "a2a":
            # Only set Authorization header if auth is enabled in config
            env_var_name = conf.get("auth", {}).get("env_var")
            if env_var_name:
                jwt_token = os.environ.get(env_var_name)
                if jwt_token:
                    headers["Authorization"] = f"Bearer {jwt_token}"
                    logging.info(f"A2A server '{server_name}' Authorization header set from {env_var_name}")
                else:
                    logging.warning(f"JWT env var '{env_var_name}' is configured for '{server_name}' but not set in environment.")
            else:
                # Ensure no Authorization header is present if auth is not enabled
                headers.pop("Authorization", None)
            server = A2AServerConfig(
                base_url=server_url,
                headers=headers,
                name=server_name
            )
        else:
            raise ValueError(f"Unknown server type: {server_type}")

        mcp_servers.append(server)
        if "allowed_tools" in conf:
            allowed_tools_map[server_name] = set(conf["allowed_tools"])

    # Patch MCPToolsIntegration to filter tools per server
    MCPToolsIntegration.prepare_dynamic_tools = lambda mcp_servers, convert_schemas_to_strict=True, auto_connect=True: filtered_prepare_dynamic_tools(mcp_servers, allowed_tools_map, convert_schemas_to_strict, auto_connect)

    # Connect servers first so we can fetch prompts
    for server in mcp_servers:
        try:
            await server.connect()
        except Exception as e:
            logging.error(f"Failed to connect to server '{getattr(server, 'name', '')}': {e}")

    # Fetch prompts from all MCP servers and inject into agent instructions
    prompt_context = await _fetch_server_prompts(mcp_servers)

    agent = await MCPToolsIntegration.create_agent_with_tools(
        agent_class=FunctionAgent,
        mcp_servers=mcp_servers,
        agent_kwargs={"extra_instructions": prompt_context, "llm": llm},
        auto_connect=False,
    )

    await ctx.connect()
    session = AgentSession()
    logging.info("Agent is ready.")
    # Optionally, greet via voice if possible
    if hasattr(agent, 'speak') and callable(getattr(agent, 'speak', None)):
        await agent.speak("Hello! How can I help you today?")

    # Robust session loop with reconnection
    max_retries = 10
    retry_delay = 3
    for attempt in range(1, max_retries + 1):
        try:
            await session.start(agent=agent, room=ctx.room)
            break  # Exit if session ends cleanly
        except Exception as exc:
            logging.error(f"Agent session error (attempt {attempt}/{max_retries}): {exc}")
            # Reconnect all MCP servers
            for server in mcp_servers:
                try:
                    await server.connect()
                except Exception as conn_exc:
                    logging.error(f"Failed to reconnect MCP server {getattr(server, 'name', '')}: {conn_exc}")
            if attempt < max_retries:
                logging.info(f"Retrying agent session in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logging.error("Max session retries reached. Exiting.")
                raise

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint)) 