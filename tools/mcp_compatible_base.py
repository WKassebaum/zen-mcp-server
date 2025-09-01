"""
MCP-compatible base class that ensures tools have required attributes.
"""

from typing import Any, Dict, Optional
from abc import abstractmethod


class MCPCompatibleTool:
    """
    Base class that ensures MCP protocol compatibility.
    
    MCP server expects tools to have 'name' and 'description' as attributes,
    not just methods. This class bridges that gap.
    """
    
    def __init__(self):
        # Set attributes from methods to ensure MCP compatibility
        self.name = self.get_name()
        self.description = self.get_description()
        
        # Cache the input schema for efficiency
        self._input_schema_cache = None
    
    @abstractmethod
    def get_name(self) -> str:
        """Return the tool name."""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Return the tool description."""
        pass
    
    @abstractmethod
    def get_input_schema(self) -> Dict[str, Any]:
        """Return the JSON Schema for tool input."""
        pass
    
    def get_annotations(self) -> Dict[str, Any]:
        """Return tool annotations for MCP protocol."""
        return {"readOnlyHint": False}
    
    def requires_model(self) -> bool:
        """Whether this tool requires an AI model."""
        return False
    
    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> list:
        """Execute the tool with given arguments."""
        pass