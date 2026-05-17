"""MCP wrappers for Fattern."""

from .server import FatternMcpServer
from .tools import McpToolRegistry, tools_call, tools_list
from .runtime import McpToolResult, McpToolRuntime

__all__ = [
    "McpToolRegistry",
    "McpToolResult",
    "McpToolRuntime",
    "FatternMcpServer",
    "tools_call",
    "tools_list",
]
