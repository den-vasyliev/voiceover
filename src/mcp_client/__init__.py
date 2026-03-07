from mcp_client.server import MCPServerSse, MCPServer
from mcp_client.auth import HMACAuth, create_auth_middleware

# Define MCPClient class here since client.py doesn't exist
class MCPClient:
    def __init__(self, url, secret_key, headers=None, name=None):
        """
        Create an authenticated MCP client.
        
        Args:
            url: The URL of the MCP server
            secret_key: The secret key for authentication
            headers: Additional headers to include in requests
            name: Optional name for the client
        """
        from mcp_client.auth import create_auth_middleware
        
        self.url = url
        self.name = name
        self.headers = headers or {}
        
        # Create authentication middleware
        auth_middleware = create_auth_middleware(secret_key)
        
        # Create server with authentication middleware
        self.server = MCPServerSse(
            params={"url": url, "headers": self.headers},
            cache_tools_list=True,
            name=name,
            middleware=[auth_middleware]
        )

__all__ = ["MCPClient", "MCPServerSse", "MCPServer", "HMACAuth", "create_auth_middleware"]