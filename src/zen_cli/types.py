"""
Types for the standalone Zen CLI.

This module provides types that were previously imported from MCP
but are needed for the standalone CLI to work.
"""

from dataclasses import dataclass
from typing import Optional, Any, Dict


@dataclass
class TextContent:
    """A simple text content container compatible with MCP's TextContent."""
    text: str
    type: str = "text"  # MCP compatibility
    metadata: Optional[Dict[str, Any]] = None
    
    def __str__(self):
        return self.text