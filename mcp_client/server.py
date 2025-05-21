import asyncio
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import Any, Dict, List, Optional, Tuple, Callable
import logging

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.types import CallToolResult, JSONRPCMessage, Tool as MCPTool
from mcp_client.sse_client import sse_client
from mcp.client.session import ClientSession

# Type for middleware function
ToolMiddleware = Callable[[str, Optional[Dict[str, Any]]], Dict[str, Any]]

# Base class for MCP servers
class MCPServer:
    async def connect(self):
        """Connect to the server."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        """A readable name for the server."""
        raise NotImplementedError

    async def list_tools(self) -> List[MCPTool]:
        """List the tools available on the server."""
        raise NotImplementedError

    async def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> CallToolResult:
        """Invoke a tool on the server."""
        raise NotImplementedError

    async def cleanup(self):
        """Cleanup the server."""
        raise NotImplementedError

# Base class for MCP servers that use a ClientSession
class _MCPServerWithClientSession(MCPServer):
    """Base class for MCP servers that use a ClientSession to communicate with the server."""

    def __init__(self, cache_tools_list: bool, middleware: Optional[List[ToolMiddleware]] = None, max_retries: int = 5, retry_delay: float = 2.0):
        """
        Args:
            cache_tools_list: Whether to cache the tools list. If True, the tools list will be
            cached and only fetched from the server once. If False, the tools list will be
            fetched from the server on each call to list_tools(). You should set this to True
            if you know the server will not change its tools list, because it can drastically
            improve latency.
            middleware: A list of middleware functions that will be applied to the arguments
            before calling a tool. Each middleware should be a function that takes a tool name
            and arguments and returns modified arguments.
            max_retries: Maximum number of connection attempts on failure.
            retry_delay: Delay (in seconds) between retries.
        """
        self.session: Optional[ClientSession] = None
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self.cache_tools_list = cache_tools_list
        self.middleware = middleware or []
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # The cache is always dirty at startup, so that we fetch tools at least once
        self._cache_dirty = True
        self._tools_list: Optional[List[MCPTool]] = None
        self.logger = logging.getLogger(__name__)

    def create_streams(
        self,
    ) -> AbstractAsyncContextManager[
        Tuple[
            MemoryObjectReceiveStream[JSONRPCMessage | Exception],
            MemoryObjectSendStream[JSONRPCMessage],
        ]
    ]:
        """Create the streams for the server."""
        raise NotImplementedError

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.cleanup()

    def invalidate_tools_cache(self):
        """Invalidate the tools cache."""
        self._cache_dirty = True

    async def connect(self):
        """Connect to the server with automatic reconnection on failure."""
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                transport = await self.exit_stack.enter_async_context(self.create_streams())
                read, write = transport
                session = await self.exit_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self.session = session
                self.logger.info(f"Connected to MCP server: {self.name}")
                return
            except Exception as e:
                last_exc = e
                self.logger.error(f"Error initializing MCP server (attempt {attempt}/{self.max_retries}): {e}")
                await self.cleanup()
                if attempt < self.max_retries:
                    self.logger.info(f"Retrying connection in {self.retry_delay} seconds...")
                    await asyncio.sleep(self.retry_delay)
        # If we get here, all retries failed
        self.logger.error(f"Failed to connect to MCP server after {self.max_retries} attempts.")
        raise last_exc

    async def list_tools(self) -> List[MCPTool]:
        """List the tools available on the server."""
        if not self.session:
            raise RuntimeError("Server not initialized. Make sure you call connect() first.")

        # Return from cache if caching is enabled, we have tools, and the cache is not dirty
        if self.cache_tools_list and not self._cache_dirty and self._tools_list:
            return self._tools_list

        # Reset the cache dirty to False
        self._cache_dirty = False

        try:
            # Fetch the tools from the server
            result = await self.session.list_tools()
            self._tools_list = result.tools
            return self._tools_list
        except Exception as e:
            self.logger.error(f"Error listing tools: {e}")
            raise

    async def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> CallToolResult:
        """Invoke a tool on the server with reconnection and retry logic."""
        arguments = arguments or {}
        processed_args = arguments
        for middleware in self.middleware:
            try:
                processed_args = await middleware(tool_name, processed_args)
            except Exception as e:
                self.logger.error(f"Error in middleware for tool {tool_name}: {e}")
                raise

        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if not self.session:
                    await self.connect()
                return await self.session.call_tool(tool_name, processed_args)
            except Exception as e:
                last_exc = e
                self.logger.error(f"Error calling tool {tool_name} (attempt {attempt}/{self.max_retries}): {e}")
                await self.cleanup()
                if attempt < self.max_retries:
                    self.logger.info(f"Reconnecting and retrying tool call in {self.retry_delay} seconds...")
                    await asyncio.sleep(self.retry_delay)
                    await self.connect()
                else:
                    self.logger.error(f"Max retries reached for tool {tool_name}.")
                    raise last_exc

    async def cleanup(self):
        """Cleanup the server."""
        async with self._cleanup_lock:
            try:
                await self.exit_stack.aclose()
                self.session = None
                self.logger.info(f"Cleaned up MCP server: {self.name}")
            except Exception as e:
                self.logger.error(f"Error cleaning up server: {e}")

# Define parameter types for clarity
MCPServerSseParams = Dict[str, Any]

# SSE server implementation
class MCPServerSse(_MCPServerWithClientSession):
    """MCP server implementation that uses the HTTP with SSE transport."""

    def __init__(
        self,
        params: MCPServerSseParams,
        cache_tools_list: bool = False,
        name: Optional[str] = None,
        middleware: Optional[List[ToolMiddleware]] = None,
        max_retries: int = 5,
        retry_delay: float = 2.0,
    ):
        """Create a new MCP server based on the HTTP with SSE transport.

        Args:
            params: The params that configure the server including the URL, headers,
                   timeout, and SSE read timeout.
            cache_tools_list: Whether to cache the tools list.
            name: A readable name for the server.
            middleware: A list of middleware functions that will be applied to the arguments
                        before calling a tool.
            max_retries: Maximum number of connection attempts on failure.
            retry_delay: Delay (in seconds) between retries.
        """
        super().__init__(cache_tools_list, middleware, max_retries=max_retries, retry_delay=retry_delay)
        self.params = params
        self._name = name or f"SSE Server at {self.params.get('url', 'unknown')}"

    def create_streams(
        self,
    ) -> AbstractAsyncContextManager[
        Tuple[
            MemoryObjectReceiveStream[JSONRPCMessage | Exception],
            MemoryObjectSendStream[JSONRPCMessage],
        ]
    ]:
        """Create the streams for the server."""
        return sse_client(
            url=self.params["url"],
            headers=self.params.get("headers"),
            timeout=self.params.get("timeout", 5),
            sse_read_timeout=self.params.get("sse_read_timeout", 60 * 5),
        )

    @property
    def name(self) -> str:
        """A readable name for the server."""
        return self._name