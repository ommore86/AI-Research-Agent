"""
Base tool interface and execution wrapper with timeouts, retries, and error isolation.
"""

from abc import ABC, abstractmethod
import time
from typing import Any, Dict, Optional
from agent.models import ToolResult


class BaseTool(ABC):
    """Abstract base class for all tools available to the research agent."""

    name: str = "base_tool"
    description: str = "Base tool description"
    parameters: Dict[str, Any] = {}

    def __init__(self, timeout_seconds: float = 12.0, max_retries: int = 2):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Core tool logic implemented by individual tools."""
        pass

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Executes the tool with defensive error handling, timing, and retry logic.
        Guarantees that a failing tool never raises an unhandled exception into the agent loop.
        """
        start_time = time.time()
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                # Subclasses execute their logic
                raw_output = self.run(**kwargs)
                duration = time.time() - start_time
                return ToolResult(
                    tool_name=self.name,
                    arguments=kwargs,
                    success=True,
                    output=raw_output,
                    execution_time_seconds=round(duration, 3),
                    cached=False
                )
            except Exception as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    # Brief sleep between retries with backoff
                    time.sleep(0.5 * attempt)
                    continue

        duration = time.time() - start_time
        error_msg = f"{type(last_exception).__name__}: {str(last_exception)}" if last_exception else "Unknown error"
        return ToolResult(
            tool_name=self.name,
            arguments=kwargs,
            success=False,
            output=None,
            error_message=error_msg,
            execution_time_seconds=round(duration, 3),
            cached=False
        )
