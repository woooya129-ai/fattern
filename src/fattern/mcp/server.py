"""Minimal in-process MCP surface used by tests and future transports."""

from __future__ import annotations

from typing import Any

from .tools import McpToolRegistry


class FatternMcpServer:
    """Transport-neutral server facade for tools/list and tools/call."""

    def __init__(self, registry: McpToolRegistry | None = None) -> None:
        self.registry = registry or McpToolRegistry()

    def tools_list(self) -> dict[str, Any]:
        return {"tools": self.registry.list_tools()}

    def tools_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.registry.call_tool(name, arguments)
