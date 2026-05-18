"""HTTP helpers for remote MCP preparation."""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
from urllib.parse import urlparse

from fattern.hosting import MAX_REMOTE_MCP_BYTES
from fattern.jobs import JobStore

from .server import FatternMcpServer
from .stdio import FatternStdioMcpServer, INVALID_REQUEST, JSONRPC_VERSION, PARSE_ERROR
from .tools import McpToolRegistry


@dataclass(frozen=True)
class RemoteMcpHttpConfig:
    bearer_token: str | None = None
    allowed_origins: tuple[str, ...] = ()
    max_body_bytes: int = MAX_REMOTE_MCP_BYTES


def build_remote_mcp_dispatcher(
    *,
    store: JobStore,
    output_root: Path,
    web_base_url: str,
    allow_workspace_paths: bool = False,
) -> FatternStdioMcpServer:
    registry = McpToolRegistry(
        store,
        output_root=output_root,
        web_base_url=web_base_url,
        persist_runs=True,
        allow_workspace_paths=allow_workspace_paths,
    )
    return FatternStdioMcpServer(FatternMcpServer(registry))


def send_mcp_get_not_supported(handler: BaseHTTPRequestHandler) -> None:
    body = json.dumps(
        {
            "error": "SSE streams are not implemented in this v0.9.0 preparation endpoint. Use HTTP POST.",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    handler.send_response(405)
    handler.send_header("Allow", "POST")
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_mcp_post(
    handler: BaseHTTPRequestHandler,
    *,
    dispatcher: FatternStdioMcpServer,
    config: RemoteMcpHttpConfig,
) -> None:
    if not _origin_allowed(handler.headers.get("Origin"), handler.headers.get("Host", ""), config.allowed_origins):
        _send_json_error(handler, 403, "Origin is not allowed.")
        return

    if not _authorized(handler.headers.get("Authorization"), config.bearer_token):
        _send_json_error(handler, 401, "Authorization bearer token is required.", authenticate=True)
        return

    if "application/json" not in (handler.headers.get("Content-Type", "").lower()):
        _send_json_error(handler, 415, "Content-Type must be application/json.")
        return

    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        _send_json_error(handler, 400, "Content-Length is invalid.")
        return
    if length <= 0:
        _send_json_error(handler, 400, "Request body is required.")
        return
    if length > config.max_body_bytes:
        _send_json_error(handler, 413, "MCP request body is too large.")
        return

    raw_body = handler.rfile.read(length)
    try:
        message = json.loads(raw_body)
    except json.JSONDecodeError:
        _send_json_rpc(handler, 400, _json_rpc_error(None, PARSE_ERROR, "Parse error."))
        return

    response = dispatcher.handle_message(message)
    if response is None:
        handler.send_response(202)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return
    _send_json_rpc(handler, 200, response)


def _origin_allowed(origin: str | None, host_header: str, allowed_origins: tuple[str, ...]) -> bool:
    if not origin:
        return True
    normalized_origin = origin.rstrip("/")
    if normalized_origin in {allowed.rstrip("/") for allowed in allowed_origins}:
        return True

    parsed = urlparse(normalized_origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.netloc == host_header:
        return True
    return parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def _authorized(authorization: str | None, bearer_token: str | None) -> bool:
    if not bearer_token:
        return True
    return authorization == f"Bearer {bearer_token}"


def _send_json_rpc(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_json_error(
    handler: BaseHTTPRequestHandler,
    status: int,
    message: str,
    *,
    authenticate: bool = False,
) -> None:
    payload = _json_rpc_error(None, INVALID_REQUEST, message)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    if authenticate:
        handler.send_header("WWW-Authenticate", 'Bearer realm="fattern"')
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _json_rpc_error(request_id: object, code: int, message: str) -> dict:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
