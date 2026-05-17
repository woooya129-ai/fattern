"""Compatibility runtime facade for MCP wrapper tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fattern.jobs import JobStore

from .tools import McpToolRegistry


@dataclass(frozen=True)
class McpToolResult:
    ok: bool
    data: dict[str, Any]
    messages: list[dict[str, str]]


class McpToolRuntime:
    def __init__(self, store: JobStore | None = None) -> None:
        self.registry = McpToolRegistry(store)

    def list_tools(self) -> list[dict]:
        return self.registry.list_tools()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> McpToolResult:
        response = self.registry.call_tool(name, arguments)
        errors = response.get("errors", [])
        warnings = response.get("warnings", [])
        data = {key: value for key, value in response.items() if key not in {"errors", "warnings"}}
        if "piece_summary" in data and "pieces" not in data:
            data["pieces"] = data["piece_summary"]
        if "piece_metrics" in data and "metrics" not in data:
            data["metrics"] = data["piece_metrics"]
        return McpToolResult(ok=not errors, data=data, messages=[*errors, *warnings])
