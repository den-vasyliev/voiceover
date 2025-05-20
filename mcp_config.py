"""
mcp_config.py

Handles loading of MCP server configuration and expansion of environment variables in config values.
"""

import os
import yaml
import re

def load_mcp_config(config_path="mcp_servers.yaml"):
    """
    Load MCP server configuration from a YAML file.
    Raises FileNotFoundError if the config file does not exist.
    Returns a list of server configurations.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"MCP config file not found: {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)["servers"]

def expand_env_vars(value):
    """
    Replace ${VARNAME} in the input string with the value from the environment.
    Returns the expanded string.
    """
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value) 