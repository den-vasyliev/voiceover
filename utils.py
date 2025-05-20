"""
utils.py

Provides utility functions for the agent system.
"""

import re

def sanitize_tool_name(name: str) -> str:
    """
    Sanitize a tool name by replacing non-alphanumeric, non-underscore, and non-hyphen characters with underscores.
    Returns the sanitized tool name.
    """
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name) 