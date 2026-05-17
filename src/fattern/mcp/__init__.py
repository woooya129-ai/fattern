"""MCP wrappers for Fattern."""

from .server import FatternMcpServer
from .stdio import FatternStdioMcpServer, serve_stdio
from .tools import McpToolRegistry, tools_call, tools_list
from .runtime import McpToolResult, McpToolRuntime

__all__ = [
    "McpToolRegistry",
    "McpToolResult",
    "McpToolRuntime",
    "FatternMcpServer",
    "FatternStdioMcpServer",
    "serve_stdio",
    "tools_call",
    "tools_list",
]
