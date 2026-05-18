"""Hosted Web UI and remote MCP policy helpers."""

from __future__ import annotations

from urllib.parse import urljoin

from fattern import __version__

REMOTE_MCP_PATH = "/mcp"
HOSTING_POLICY_PATH = "/hosting/policy"
REMOTE_SERVER_MANIFEST_PATH = "/server.json"
MAX_REMOTE_MCP_BYTES = 16 * 1024 * 1024


def build_hosting_policy(
    *,
    public_base_url: str,
    remote_mcp_enabled: bool,
    auth_required: bool,
    max_upload_bytes: int = 12 * 1024 * 1024,
    max_mcp_bytes: int = MAX_REMOTE_MCP_BYTES,
) -> dict:
    """Return the explicit hosted-prep policy exposed by the Web UI."""

    return {
        "schema_version": "1.0",
        "product": "fattern",
        "version": __version__,
        "mode": "hosted_web_ui_remote_mcp_preparation",
        "web_ui": {
            "enabled": True,
            "public_base_url": public_base_url,
            "upload_endpoint": "/estimate",
            "max_upload_mb": round(max_upload_bytes / (1024 * 1024), 2),
            "default_input_dir": "input",
            "default_output_dir": "output",
        },
        "remote_mcp": {
            "enabled": remote_mcp_enabled,
            "endpoint": urljoin(public_base_url.rstrip("/") + "/", REMOTE_MCP_PATH.lstrip("/")),
            "transport": "streamable-http-json-response",
            "sse_streaming": False,
            "auth": "bearer_token" if auth_required else "disabled_for_local_development",
            "workspace_path_tools": False,
            "preferred_file_flow": "register_input_file.content_base64",
            "max_request_mb": round(max_mcp_bytes / (1024 * 1024), 2),
        },
        "data_policy": {
            "raw_dxf": "Processed by the deterministic Fattern engine.",
            "llm_context": "Optional Advisor receives sanitized result context, not raw DXF bytes by default.",
            "local_retention": "Local output folders remain until the user deletes them.",
            "hosted_retention_target": "Public hosted deployments must define short retention before launch.",
        },
        "security_policy": {
            "origin_validation": True,
            "public_bind_requires_token": True,
            "path_traversal_guard": True,
            "artifact_allowlist": True,
            "oauth_status": "not_implemented_in_v0.9.0_preparation",
        },
        "production_blockers": [
            "OAuth 2.1 protected-resource metadata and token validation are not implemented.",
            "User accounts, project isolation, retention jobs, and quota enforcement are not implemented.",
            "Remote MCP has not been submitted to a public connector directory.",
        ],
    }


def build_remote_server_manifest(*, public_base_url: str) -> dict:
    """Return a remote MCP server manifest for future registry/package work."""

    return {
        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
        "name": "io.github.woooya129-ai/fattern",
        "title": "Fattern",
        "description": "DXF rough marker yield and quotation yield estimator.",
        "version": __version__,
        "remotes": [
            {
                "type": "streamable-http",
                "url": urljoin(public_base_url.rstrip("/") + "/", REMOTE_MCP_PATH.lstrip("/")),
            }
        ],
    }
