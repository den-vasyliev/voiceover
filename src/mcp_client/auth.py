import hmac
import hashlib
import json
import base64
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class HMACAuth:
    """HMAC authentication for MCP client requests."""

    def __init__(self, secret_key: str):
        """
        Initialize HMAC authentication.
        
        Args:
            secret_key: The secret key used for HMAC signing
        """
        try:
            # First decode the secret key from base64, matching Go's implementation
            self.secret_key = base64.b64decode(secret_key)
            logger.debug(f"Using base64 decoded key ({len(self.secret_key)} bytes)")
        except Exception as e:
            # Fallback to using the raw key if it's not valid base64
            logger.warning(f"Error decoding base64 key: {e}. Using raw key.")
            self.secret_key = secret_key.encode('utf-8')

    def sign_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sign the request parameters with HMAC.
        
        Args:
            params: The request parameters to sign
            
        Returns:
            A new dict with the original parameters plus the auth parameter
        """
        # Create a copy of params to avoid modifying the original
        params_copy = params.copy()
        
        # Make sure auth is not in the params for signing
        if 'auth' in params_copy:
            del params_copy['auth']
            
        # Convert params to JSON string for signing
        # Use sort_keys=True to ensure consistent ordering and no whitespace
        # This matches Go's json.Marshal behavior
        body_bytes = json.dumps(params_copy, sort_keys=True, separators=(',', ':')).encode('utf-8')
        
        # Debug output for troubleshooting
        logger.debug(f"Signing payload: {body_bytes}")
        
        # Create HMAC signature using base64 encoding
        hmac_digest = hmac.new(
            self.secret_key,
            body_bytes,
            hashlib.sha256
        ).digest()
        
        # Convert to base64 and keep the padding to match Go's encoding
        signature = base64.b64encode(hmac_digest).decode('utf-8')
        
        # Debug output for troubleshooting
        logger.debug(f"Generated signature: {signature}")
        
        # Add signature to original params
        result = params.copy()
        result['auth'] = signature
        
        return result


def create_auth_middleware(secret_key: str):
    """
    Create a middleware function that adds HMAC authentication to requests.
    
    Args:
        secret_key: The secret key used for HMAC signing
        
    Returns:
        A middleware function that can be used with MCPClient
    """
    auth = HMACAuth(secret_key)
    
    async def auth_middleware(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add authentication to the request arguments."""
        args = arguments or {}
        return auth.sign_request(args)
        
    return auth_middleware 