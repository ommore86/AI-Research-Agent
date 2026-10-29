"""
Tool Registry for dynamic tool discovery, execution, caching, and introspection.
"""

from typing import Any, Dict, List, Optional
from agent.models import ToolResult
from agent.tools.base import BaseTool
from agent.tools.cache import ToolCache
from agent.tools.search import WebSearchTool
from agent.tools.scraper import WebScraperTool
from agent.tools.wikipedia import WikipediaTool


class ToolRegistry:
    """Manages the collection of active tools available to the agent."""

    def __init__(self, cache_enabled: bool = True, cache_ttl_seconds: int = 3600):
        self._tools: Dict[str, BaseTool] = {}
        self.cache = ToolCache(default_ttl_seconds=cache_ttl_seconds, enabled=cache_enabled)

    def register_tool(self, tool: BaseTool) -> None:
        """Adds a tool to the registry."""
        self._tools[tool.name] = tool

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Retrieves a tool by name."""
        return self._tools.get(tool_name)

    def list_tools(self) -> List[str]:
        """Returns names of all registered tools."""
        return list(self._tools.keys())

    def get_tool_descriptions(self) -> str:
        """Formats tool names and descriptions for LLM prompts."""
        lines = []
        for name, tool in self._tools.items():
            params = tool.parameters.get("properties", {})
            param_str = ", ".join([f"{k}: {v.get('type')}" for k, v in params.items()])
            lines.append(f"- **{name}**({param_str}): {tool.description}")
        return "\n".join(lines)

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Executes a registered tool by name with cache check and defensive error handling.
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                tool_name=tool_name,
                arguments=arguments,
                success=False,
                output=None,
                error_message=f"Tool '{tool_name}' is not registered. Available tools: {self.list_tools()}",
                execution_time_seconds=0.0,
                cached=False
            )

        # 1. Check cache
        cached_output = self.cache.get(tool_name, arguments)
        if cached_output is not None:
            return ToolResult(
                tool_name=tool_name,
                arguments=arguments,
                success=True,
                output=cached_output,
                execution_time_seconds=0.001,
                cached=True
            )

        # 2. Execute live
        result = tool.execute(**arguments)

        # 3. Cache successful output
        if result.success and result.output is not None:
            self.cache.set(tool_name, arguments, result.output)

        return result


def create_default_registry(cache_enabled: bool = True, timeout_seconds: float = 12.0) -> ToolRegistry:
    """Factory creating registry populated with standard production tools."""
    registry = ToolRegistry(cache_enabled=cache_enabled)
    registry.register_tool(WebSearchTool(timeout_seconds=timeout_seconds))
    registry.register_tool(WebScraperTool(timeout_seconds=timeout_seconds))
    registry.register_tool(WikipediaTool(timeout_seconds=timeout_seconds))
    return registry
