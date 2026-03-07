import os
import pytest
import yaml
from mcp_config import load_mcp_config, expand_env_vars

def test_load_mcp_config_success(tmp_path):
    config_content = """
servers:
  - name: github
    url: https://github-mcp.example.com
    allowed_tools: [repo_search, issue_create]
  - name: flux
    url: https://flux-mcp.example.com
    allowed_tools: [deploy, status]
"""
    config_file = tmp_path / "mcp_servers.yaml"
    config_file.write_text(config_content)
    servers = load_mcp_config(str(config_file))
    assert len(servers) == 2
    assert servers[0]["name"] == "github"
    assert servers[0]["allowed_tools"] == ["repo_search", "issue_create"]
    assert servers[1]["url"] == "https://flux-mcp.example.com"
    assert servers[1]["allowed_tools"] == ["deploy", "status"]

def test_load_mcp_config_with_wildcard(tmp_path):
    config_content = """
servers:
  - name: k8s
    url: http://localhost:8092/sse
    allowed_tools: [list_*, describe_*]
"""
    config_file = tmp_path / "mcp_servers.yaml"
    config_file.write_text(config_content)
    servers = load_mcp_config(str(config_file))
    assert servers[0]["allowed_tools"] == ["list_*", "describe_*"]

def test_load_mcp_config_no_allowed_tools(tmp_path):
    config_content = """
servers:
  - name: all-tools
    url: http://localhost:8092/sse
"""
    config_file = tmp_path / "mcp_servers.yaml"
    config_file.write_text(config_content)
    servers = load_mcp_config(str(config_file))
    assert "allowed_tools" not in servers[0]

def test_load_mcp_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_mcp_config("nonexistent.yaml")

def test_load_mcp_config_malformed(tmp_path):
    config_file = tmp_path / "mcp_servers.yaml"
    config_file.write_text("not: valid: yaml: : :")
    with pytest.raises(yaml.YAMLError):
        load_mcp_config(str(config_file))

def test_load_mcp_config_missing_servers_key(tmp_path):
    config_file = tmp_path / "mcp_servers.yaml"
    config_file.write_text("foo: bar\n")
    with pytest.raises(ValueError, match="'servers'"):
        load_mcp_config(str(config_file))

def test_expand_env_vars_replaces_known_var(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "abc123")
    assert expand_env_vars("Bearer ${MY_TOKEN}") == "Bearer abc123"

def test_expand_env_vars_missing_var_becomes_empty():
    # Unset variable should expand to empty string
    os.environ.pop("UNDEFINED_VAR_XYZ", None)
    assert expand_env_vars("prefix_${UNDEFINED_VAR_XYZ}_suffix") == "prefix__suffix"

def test_expand_env_vars_no_placeholder():
    assert expand_env_vars("no-substitution-here") == "no-substitution-here"

def test_expand_env_vars_multiple_placeholders(monkeypatch):
    monkeypatch.setenv("HOST", "localhost")
    monkeypatch.setenv("PORT", "8080")
    assert expand_env_vars("http://${HOST}:${PORT}/sse") == "http://localhost:8080/sse" 