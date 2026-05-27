"""Base class for all Hermes tools."""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for tools that can be invoked by the LLM."""

    # Security & performance attributes (subclasses can override)
    requires_network: bool = False
    dangerous: bool = False
    timeout: int = 60  # default execution timeout in seconds

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier used in function calls."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description shown to the LLM."""

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema for the tool's parameters."""

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Execute the tool with the given arguments and return a string result."""

    def to_openai_tool(self) -> dict:
        """Return the tool definition in OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
