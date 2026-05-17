"""MCP stdio transport for Fattern.

The transport reads newline-delimited JSON-RPC messages from stdin and writes
only JSON-RPC messages to stdout. Logs must use stderr to avoid corrupting the
stdio protocol stream.
"""

from __future__ import annotations

import json
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Any, TextIO

from .server import FatternMcpServer

JSONRPC_VERSION = "2.0"
DEFAULT_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"})

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class FatternStdioMcpServer:
    """Small JSON-RPC dispatcher for the MCP stdio transport."""

    def __init__(self, server: FatternMcpServer | None = None) -> None:
        self.server = server or FatternMcpServer()

    def handle_message(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return _error_response(None, INVALID_REQUEST, "Invalid JSON-RPC request.")
        if message.get("jsonrpc") != JSONRPC_VERSION or not isinstance(message.get("method"), str):
            return _error_response(message.get("id"), INVALID_REQUEST, "Invalid JSON-RPC request.")

        request_id = message.get("id")
        is_notification = "id" not in message
        method = message["method"]
        params = message.get("params", {})

        try:
            result = self._dispatch(method, params, is_notification=is_notification)
        except InvalidParams:
            return None if is_notification else _error_response(request_id, INVALID_PARAMS, "Invalid params.")
        except MethodNotFound:
            return None if is_notification else _error_response(request_id, METHOD_NOT_FOUND, "Method not found.")
        except Exception:
            return None if is_notification else _error_response(request_id, INTERNAL_ERROR, "Internal error.")

        if is_notification:
            return None
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}

    def _dispatch(self, method: str, params: Any, *, is_notification: bool) -> dict[str, Any]:
        if method == "initialize":
            if not isinstance(params, dict):
                raise InvalidParams
            return _initialize_result(params)
        if method == "notifications/initialized":
            if not is_notification:
                return {}
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            if params is not None and not isinstance(params, dict):
                raise InvalidParams
            return self.server.tools_list()
        if method == "tools/call":
            if not isinstance(params, dict):
                raise InvalidParams
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise InvalidParams
            return _tool_call_result(self.server.tools_call(name, arguments))
        if method == "prompts/list":
            if params is not None and not isinstance(params, dict):
                raise InvalidParams
            return self.server.prompts_list()
        if method == "prompts/get":
            if not isinstance(params, dict):
                raise InvalidParams
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise InvalidParams
            try:
                return self.server.prompts_get(name, arguments)
            except KeyError as exc:
                raise InvalidParams from exc
        raise MethodNotFound


class InvalidParams(ValueError):
    pass


class MethodNotFound(ValueError):
    pass


def serve_stdio(
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    server: FatternStdioMcpServer | None = None,
) -> int:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    active_server = server or FatternStdioMcpServer()

    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _write_message(output_stream, _error_response(None, PARSE_ERROR, "Parse error."))
            continue

        response = active_server.handle_message(message)
        if response is not None:
            _write_message(output_stream, response)

    error_stream.flush()
    return 0


def main() -> int:
    return serve_stdio()


def _initialize_result(params: dict[str, Any]) -> dict[str, Any]:
    requested_version = params.get("protocolVersion")
    protocol_version = requested_version if requested_version in SUPPORTED_PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
    return {
        "protocolVersion": protocol_version,
        "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
        "serverInfo": {
            "name": "fattern",
            "title": "Fattern",
            "version": _package_version(),
        },
        "instructions": (
            "Use Fattern tools for DXF rough marker estimation. "
            "If the client exposes MCP prompts through slash UI, use /fattern for the start guide. "
            "Do not provide path inputs; register DXF content with register_input_file first."
        ),
    }


def _tool_call_result(response: dict[str, Any]) -> dict[str, Any]:
    is_error = any(error.get("severity") == "blocker" for error in response.get("errors", []))
    text = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": response,
        "isError": is_error,
    }


def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _write_message(output_stream: TextIO, message: dict[str, Any]) -> None:
    output_stream.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    output_stream.flush()


def _package_version() -> str:
    try:
        return version("fattern")
    except PackageNotFoundError:
        return "0.7.1"


if __name__ == "__main__":
    raise SystemExit(main())
